"""Writes an approved contract's content into the live catalogue (Glossary: Apply).

`plan_apply(contract, client)` and `apply(contract, client, ...)` share one
private step-builder, `_build_write_steps`, so the SQL a caller sees printed
before merge (`plan_apply`) and the SQL that actually runs on merge (`apply`)
can never silently diverge into two implementations: both call the same
`UCClient` write method with the same arguments, `plan_apply` with
`dry_run=True` and `apply` with `dry_run=False` (`uc_client.py`'s dry-run seam).

What gets written where, and why -- the mapping from `models.Contract` fields to
`UCClient` write calls, since neither `models.py` nor `uc_client.py` dictates
this on its own:

- `dataset.description` -> `set_table_comment`. `column.description` ->
  `set_column_comment`, one call per column that has a description.
- The four human-declared dataset commitments that have no natural comment/tag
  home -- `certification`, `retention_days`, `refresh.cadence`,
  `refresh.sla_minutes` -- plus the owner pointer's `business_application_id`,
  go to `set_table_properties` under a `uc_metadata.*` namespace. These are
  structured facts about the table, not governance labels a consumer searches
  by, which is the same distinction Unity Catalog itself draws between
  properties and tags.
- `dataset.sensitivity` and, per column, `column.pii`, `column.sensitivity` and
  `column.business_term` go to `set_table_tags`/`set_column_tags` as real
  key/value tags (`{"sensitivity": "confidential"}`, `{"pii": "true"}`,
  `{"business_term": "customer-contact-email"}`). These are exactly the kind of
  governance/classification labels a consumer filters or searches on, which is
  what Unity Catalog tags are for.
- `column.tags: List[str]` (models.py: free-form labels like `[primary_key]`,
  matching the guide's own example) is the carried-forward tags type
  mismatch this module resolves: `UCClient.set_table_tags`/`set_column_tags`
  take `Mapping[str, str]`, because real UC tags are key/value. The chosen
  translation is `{label: "" for label in column.tags}` -- each free-form label
  becomes a key with an empty-string value, never a synthesized value like
  `{label: label}`. A free-form label genuinely has no second component; giving
  it a fabricated value (its own name, or `"true"`) would read, in the catalogue
  UI, as if that value carried information it does not. An empty-string value is
  Unity Catalog's own idiom for a key-only/flag tag, so `primary_key` renders as
  a flag, not as `primary_key = "primary_key"`. If a label collides with one of
  the governance keys above (e.g. a free-form tag literally named `pii`), the
  governance entry wins -- it carries an actual value and is filled in after the
  free-form labels when the merged dict is built (`_column_tags`).

Refusal (SC-001-03) -- `apply()` calls `validate.validate(contract, client)`
itself and refuses the whole contract, writing nothing, if it is not `ok`. This
is deliberate defence in depth: `validate.py`'s own docstring notes it is what
the provisioning/grant gate calls, and Rules & Constraints requires that "if
such a contract reaches the apply step by any other route, apply refuses the
whole contract" -- so `apply()` never trusts a caller to have validated first,
even though a well-behaved CLI always will have.

Partial-failure policy -- Unity Catalog's DDL is not transactional across
multiple statements, and there is no staging metastore in this prototype to
rehearse against (spec Non-functional Requirements). True rollback on a
mid-apply failure is therefore not attempted; claiming atomicity this module
cannot deliver would be a fabricated guarantee, worse than the truth. Instead,
`apply()` attempts every planned write in order, catches a failure on any one
of them, and keeps going rather than aborting -- so one bad write (a transient
network blip, a permissions gap on one column) never hides whether the writes
before and after it landed. Every write's outcome (succeeded or failed, with
its label and, on failure, its error) is collected and both returned in
`ApplyResult` and recorded in the release log as `partial_failure` (some
writes landed, some did not), `failed` (none landed) or `success` (all landed).
A caller that wants "did this fully apply" has exactly one field to check
(`ApplyResult.status`); a caller that needs to know exactly what to retry has
`writes_succeeded`/`writes_failed` naming precisely which write labels are in
which state, never an opaque "apply failed" exception swallowing that detail.

What this module does not yet do: `validate.py`'s certification-vs-evidence
check is not wired in (`dq_registry.py`/`coverage.py` now exist and expose the
pieces it needs -- see `coverage.py`'s "integration point for validate.py"
note -- but `validate.py` does not call them yet), so neither `validate()` nor
`apply()` can refuse a tier claim the quality evidence does not support yet.
Once that check is wired into `validate.py`, `apply()` needs no change to pick
it up -- it already refuses on any `validate()` failure, not on a
hand-maintained list of which checks count.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Union

from uc_metadata.models import Column, Contract, Dataset
from uc_metadata.release_log import DeploymentStatus, ReleaseRecord, publish_release_record
from uc_metadata.uc_client import UCClient, UCClientError
from uc_metadata.validate import validate

# Namespace for the dataset commitments that land in TBLPROPERTIES -- see this
# module's docstring for why these four (plus the owner pointer) go here rather
# than to a tag.
_PROPERTY_PREFIX = "uc_metadata"


@dataclass(frozen=True)
class WriteAttempt:
    """One catalogue write's outcome, in the order it was attempted.

    `label` is a human-readable name for the write (e.g. `"table comment"`,
    `"column comment: email"`) -- what a reviewer or the release log names, not
    a code-level identifier. `sql` is the exact statement planned for/executed
    by this write (from the same SQL-building code `plan_apply` uses).
    `error` is `None` on success, or the write's failure message.
    """

    label: str
    sql: str
    error: Optional[str] = None


@dataclass(frozen=True)
class ApplyResult:
    """What a caller of `apply()` needs to know: did it apply, and exactly what
    happened to each write.

    `status` is the single field a caller branches on: `success` (every write
    landed), `partial_failure` (some did, some did not), `failed` (none did),
    or `refused` (validation failed before any write was attempted -- SC-001-03).
    `problems` is `validate()`'s problem list, non-empty only when `status` is
    `refused`. `writes_succeeded`/`writes_failed` are the full `WriteAttempt`
    record for every write this call attempted, in attempted order.
    """

    status: DeploymentStatus
    problems: List[str] = field(default_factory=list)
    writes_succeeded: List[WriteAttempt] = field(default_factory=list)
    writes_failed: List[WriteAttempt] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == DeploymentStatus.SUCCESS


@dataclass(frozen=True)
class _WriteStep:
    """One planned write: a human-readable label, the SQL it would run (built via
    `dry_run=True`, so `plan_apply` never has to execute anything to know it),
    and the zero-argument callable that performs the real write when `apply()`
    decides to run it."""

    label: str
    sql: str
    execute: Callable[[], str]


# ---- pure planning: shared by plan_apply and apply -------------------------------


def plan_apply(contract: Contract, client: UCClient) -> List[str]:
    """Return the exact ordered list of SQL statements applying `contract` would
    execute against `client`, performing no writes at all.

    Precondition: `contract.dataset.qualifier.full_name` names a table `client`
    can resolve (`plan_apply` itself does not check this again -- every
    `dry_run=True` write call below still validates its own three-part-name
    precondition and raises if malformed, but does not require the table to
    exist, since building SQL from already-known values needs no catalogue
    read). Postcondition: `client`'s catalogue state is byte-for-byte unchanged
    by this call (every underlying write ran with `dry_run=True`) -- this is
    the "print the full set of catalogue writes it would perform before it can
    be merged" requirement (Rules & Constraints), satisfied by construction
    rather than by a second SQL-building implementation.
    """
    return [step.sql for step in _build_write_steps(contract, client)]


def _build_write_steps(contract: Contract, client: UCClient) -> List[_WriteStep]:
    """Build the ordered list of writes `plan_apply`/`apply` share: table
    comment, each column comment, table properties, table tags, column tags --
    the order the `apply.py` build verdict names and every demo print/log
    reflects."""
    full_name = contract.dataset.qualifier.full_name
    dataset = contract.dataset
    steps: List[_WriteStep] = []

    steps.append(_table_comment_step(client, full_name, dataset))
    for column in contract.columns:
        step = _column_comment_step(client, full_name, column)
        if step is not None:
            steps.append(step)
    steps.append(_table_properties_step(client, full_name, dataset))
    table_tags_step = _table_tags_step(client, full_name, dataset)
    if table_tags_step is not None:
        steps.append(table_tags_step)
    for column in contract.columns:
        step = _column_tags_step(client, full_name, column)
        if step is not None:
            steps.append(step)
    return steps


def _table_comment_step(client: UCClient, full_name: str, dataset: Dataset) -> _WriteStep:
    sql = client.set_table_comment(full_name, dataset.description, dry_run=True)
    return _WriteStep(
        label="table comment",
        sql=sql,
        execute=lambda: client.set_table_comment(full_name, dataset.description),
    )


def _column_comment_step(client: UCClient, full_name: str, column: Column) -> Optional[_WriteStep]:
    if column.description is None:
        return None
    comment = column.description.value
    sql = client.set_column_comment(full_name, column.name, comment, dry_run=True)
    return _WriteStep(
        label=f"column comment: {column.name}",
        sql=sql,
        execute=lambda: client.set_column_comment(full_name, column.name, comment),
    )


def _table_properties(dataset: Dataset) -> Dict[str, str]:
    """The dataset's human-declared commitments and owner pointer, namespaced as
    TBLPROPERTIES keys. See this module's docstring for why these five fields
    go here rather than to a tag."""
    return {
        f"{_PROPERTY_PREFIX}.certification": dataset.certification.value,
        f"{_PROPERTY_PREFIX}.retention_days": str(dataset.retention_days),
        f"{_PROPERTY_PREFIX}.refresh_cadence": dataset.refresh.cadence,
        f"{_PROPERTY_PREFIX}.refresh_sla_minutes": str(dataset.refresh.sla_minutes),
        f"{_PROPERTY_PREFIX}.owner_business_application_id": dataset.owner.business_application_id,
    }


def _table_properties_step(client: UCClient, full_name: str, dataset: Dataset) -> _WriteStep:
    properties = _table_properties(dataset)
    sql = client.set_table_properties(full_name, properties, dry_run=True)
    return _WriteStep(
        label="table properties",
        sql=sql,
        execute=lambda: client.set_table_properties(full_name, properties),
    )


def _table_tags(dataset: Dataset) -> Dict[str, str]:
    """The dataset-level governance tag(s): sensitivity, when one has been
    declared. Empty if `dataset.sensitivity` is still unset -- a freshly
    harvested or not-yet-classified contract has nothing to tag yet."""
    if dataset.sensitivity is None:
        return {}
    return {"sensitivity": dataset.sensitivity.value.value}


def _table_tags_step(client: UCClient, full_name: str, dataset: Dataset) -> Optional[_WriteStep]:
    tags = _table_tags(dataset)
    if not tags:
        return None
    sql = client.set_table_tags(full_name, tags, dry_run=True)
    return _WriteStep(
        label="table tags",
        sql=sql,
        execute=lambda: client.set_table_tags(full_name, tags),
    )


def _tags_from_labels(labels: List[str]) -> Dict[str, str]:
    """Translate `models.Column.tags` (`List[str]`, free-form labels) into the
    `Mapping[str, str]` `UCClient.set_column_tags`/`set_table_tags` need. Each
    label becomes a key-only/flag tag: an empty-string value, not a
    synthesized one -- see this module's docstring for the full reasoning."""
    return {label: "" for label in labels}


def _column_tags(column: Column) -> Dict[str, str]:
    """The full tag map for one column: free-form labels first, then the
    governance classifications (`pii`, `sensitivity`, `business_term`) that
    have real values -- governance entries are applied last, so they win any
    key collision with a free-form label of the same name."""
    tags = _tags_from_labels(column.tags)
    if column.pii is not None:
        tags["pii"] = str(column.pii.value).lower()
    if column.sensitivity is not None:
        tags["sensitivity"] = column.sensitivity.value.value
    if column.business_term is not None:
        tags["business_term"] = column.business_term.value
    return tags


def _column_tags_step(client: UCClient, full_name: str, column: Column) -> Optional[_WriteStep]:
    tags = _column_tags(column)
    if not tags:
        return None
    sql = client.set_column_tags(full_name, column.name, tags, dry_run=True)
    return _WriteStep(
        label=f"column tags: {column.name}",
        sql=sql,
        execute=lambda: client.set_column_tags(full_name, column.name, tags),
    )


# ---- the real thing ---------------------------------------------------------------


def apply(
    contract: Contract,
    client: UCClient,
    *,
    approved_by: str,
    log_path: Optional[Union[str, Path]] = None,
) -> ApplyResult:
    """Apply `contract` to the catalogue `client` is backed by, for real.

    Precondition: `approved_by` names the human whose approval authorizes this
    apply (a future CLI resolves this from the merged PR; this function trusts
    its caller for that resolution, the same boundary `release_log.py`'s
    docstring describes). Postcondition, on every call: exactly one
    `ReleaseRecord` is published (success, partial failure, failure, or
    refusal -- never silently skipped) and the returned `ApplyResult.status`
    matches it.

    Refuses the whole contract, writing nothing, if `validate(contract,
    client)` is not `ok` (SC-001-03, defence in depth -- see module docstring).
    Otherwise attempts every planned write in order, in `_build_write_steps`'s
    order, continuing past a failed write rather than aborting (see module
    docstring for the partial-failure policy), and returns/logs exactly which
    writes succeeded and which did not.
    """
    validation = validate(contract, client)
    if not validation.ok:
        return _refuse(contract, client, approved_by, validation.problems, log_path)

    steps = _build_write_steps(contract, client)
    succeeded: List[WriteAttempt] = []
    failed: List[WriteAttempt] = []
    for step in steps:
        try:
            executed_sql = step.execute()
        except Exception as exc:  # noqa: BLE001 -- deliberate: see module docstring's partial-failure policy
            failed.append(WriteAttempt(label=step.label, sql=step.sql, error=str(exc)))
        else:
            succeeded.append(WriteAttempt(label=step.label, sql=executed_sql))

    status = _deployment_status(succeeded, failed)
    record = ReleaseRecord.now(
        full_name=contract.dataset.qualifier.full_name,
        contract_version=contract.version,
        summary=_summary(succeeded, failed),
        approved_by=approved_by,
        deployment_status=status,
        writes_succeeded=[attempt.label for attempt in succeeded],
        writes_failed=[f"{attempt.label}: {attempt.error}" for attempt in failed],
    )
    publish_release_record(record, log_path=log_path)
    return ApplyResult(status=status, writes_succeeded=succeeded, writes_failed=failed)


def _refuse(
    contract: Contract,
    client: UCClient,
    approved_by: str,
    problems: List[str],
    log_path: Optional[Union[str, Path]],
) -> ApplyResult:
    """Refuse the whole contract (SC-001-03) before any write is attempted.

    Still publishes a release record: a refusal is a real, notable event on
    this contract's history ("an apply was attempted and refused, here is
    exactly why"), and omitting it would leave the release log silent about
    every change request that never should have reached apply -- the same
    survivorship-bias risk this module's docstring names for write outcomes.
    """
    record = ReleaseRecord.now(
        full_name=contract.dataset.qualifier.full_name,
        contract_version=contract.version,
        summary=f"refused: {len(problems)} validation problem(s), no writes attempted",
        approved_by=approved_by,
        deployment_status=DeploymentStatus.REFUSED,
        problems=problems,
    )
    publish_release_record(record, log_path=log_path)
    return ApplyResult(status=DeploymentStatus.REFUSED, problems=problems)


def _deployment_status(succeeded: List[WriteAttempt], failed: List[WriteAttempt]) -> DeploymentStatus:
    if not failed:
        return DeploymentStatus.SUCCESS
    if succeeded:
        return DeploymentStatus.PARTIAL_FAILURE
    return DeploymentStatus.FAILED


def _summary(succeeded: List[WriteAttempt], failed: List[WriteAttempt]) -> str:
    if not failed:
        return f"applied {len(succeeded)} write(s)"
    return f"applied {len(succeeded)} write(s), {len(failed)} write(s) failed: " + "; ".join(
        f"{attempt.label} ({attempt.error})" for attempt in failed
    )

"""Adversarial / boundary tests for `validate.py` and `apply.py` -- the refusal
gate, drift detection, idempotency, reversibility and partial-failure
guarantees the whole design rests on.

Constructor's `test_validate.py`/`test_apply.py` prove the happy paths and the
single documented partial-failure case; both modules' docstrings explicitly
say adversarial/boundary cases belong here instead. This file goes after:

  - all three of validate()'s refusal reasons firing at once, to confirm none
    of them short-circuits or hides the others (they don't -- confirmed, not
    a finding);
  - what happens when `contract.dataset.qualifier.full_name` names a table the
    catalogue simply does not have -- a real, currently-unhandled defect;
  - a TOCTOU window between `apply()`'s own `validate()` call and the writes
    it then executes;
  - several (not just one) writes failing mid-sequence, named precisely;
  - what happens when `release_log.publish_release_record` itself fails after
    catalogue writes have already landed -- a real, currently-unhandled
    defect, and the sharpest finding in this file, because `apply.py`'s own
    docstring states the postcondition this violates in so many words.

No fixes are made here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from uc_metadata.apply import ApplyResult, apply
from uc_metadata.fake_uc import FakeUCClient
from uc_metadata.harvest import harvest
from uc_metadata.models import CertificationTier, Contract, Proposed, Refresh, Sensitivity
from uc_metadata.release_log import DeploymentStatus, read_release_log
from uc_metadata.uc_client import UCClient, UCTableNotFoundError, UCWriteError
from uc_metadata.validate import validate, validate_yaml

TABLE = "workspace.analytics.customers"
KNOWN_BA_ID = "BA-10231"
APPROVER = "hector"


def _fully_reviewed_contract(client: UCClient, full_name: str = TABLE) -> Contract:
    """Same helper `test_validate.py`/`test_apply.py` use: a harvested,
    fully-reviewed, drift-free, silver-certified contract. `customers` has two
    DQ rules registered (`dq_registry.yaml`) that genuinely pass against the
    seeded fixture rows, so `silver` clears the certification-evidence check
    cleanly -- deliberately not `bronze`: `harvest.PLACEHOLDER_CERTIFICATION`
    is itself `bronze`, so a `bronze` claim here would collide with the
    placeholder-sentinel check's known value-equality limitation
    (`validate.py`'s own docstring) and pollute the "which checks fired"
    assertions below with a spurious placeholder problem.
    """
    contract = harvest(
        full_name,
        client,
        KNOWN_BA_ID,
        description="Customer master records for the direct-to-consumer storefront.",
        refresh=Refresh(cadence="daily", sla_minutes=120),
        retention_days=730,
        certification=CertificationTier.SILVER,
    )
    reviewed_columns = [
        column.model_copy(
            update={
                "description": Proposed.accepted(f"{column.name} column."),
                "pii": Proposed.accepted(False),
                "sensitivity": Proposed.accepted(Sensitivity.INTERNAL),
            }
        )
        for column in contract.columns
    ]
    dataset = contract.dataset.model_copy(update={"sensitivity": Proposed.accepted(Sensitivity.INTERNAL)})
    return contract.model_copy(update={"dataset": dataset, "columns": reviewed_columns})


# ---- three refusal reasons at once: none of them hides the others -----------------


def test_validate_names_unreviewed_and_placeholder_and_drift_simultaneously():
    """A contract that is simultaneously (a) still carrying harvest's
    placeholders, (b) carrying one unreviewed AI-proposed field, and (c)
    drifted from the catalogue, must report all three kinds of problem in one
    call -- `validate()`'s own docstring promises "every one of the four
    checks below runs regardless of whether an earlier one failed". Confirmed
    here under all three firing together, not just any two at a time
    (`test_validate.py`'s own "multiple simultaneous failures" test only
    combines placeholder + drift + unreviewed via a *different* combination
    path; this isolates that no single check's early return starves a later
    one when everything is broken at once)."""
    client = FakeUCClient()
    contract = harvest(TABLE, client, KNOWN_BA_ID)  # (a) all 4 placeholders present, no overrides

    columns = [column for column in contract.columns if column.name != "signup_date"]  # (c) drift: removed
    columns = [
        column.model_copy(update={"sensitivity": Proposed.proposed(Sensitivity.CONFIDENTIAL)})
        if column.name == "email"
        else column
        for column in columns
    ]  # (b) unreviewed
    contract = contract.model_copy(update={"columns": columns})

    result = validate(contract, client)

    assert result.ok is False
    kinds = {problem.split(":")[0] for problem in result.problems}
    assert kinds == {"placeholder", "drift", "unreviewed"}, (
        "expected all three failure kinds named together, got only: " + ", ".join(sorted(kinds))
    )
    assert len([p for p in result.problems if p.startswith("placeholder:")]) == 4
    assert len([p for p in result.problems if p.startswith("drift:")]) == 1
    assert len([p for p in result.problems if p.startswith("unreviewed:")]) == 1


# ---- validate() / validate_yaml() against a table that does not exist -------------


def test_validate_raises_instead_of_returning_a_verdict_for_a_missing_table():
    """`validate()`'s postcondition (module docstring) is a machine-readable
    `ValidationResult` for a named dataset's contract -- explicitly what the
    provisioning/grant gate this stands in for would call. `_drift_problems`
    calls `client.get_table(full_name)` with no try/except; if the table named
    by `contract.dataset.qualifier` does not exist in the catalogue at all
    (renamed, dropped, or a contract authored before the table was actually
    provisioned), `UCTableNotFoundError` propagates straight out of
    `validate()` instead of becoming a `ValidationResult(ok=False, ...)`.

    This directly undercuts the one thing `validate.py`'s own docstring says
    it is for: "the function the provisioning and grant gates would call to
    get a machine-readable verdict". A gate that gets an unhandled exception
    instead of a verdict cannot make a provisioning/grant decision at all --
    it can only crash. This test encodes the *desired* contract (a verdict is
    always returned) and is expected to fail against the current
    implementation, which raises instead.
    """
    client = FakeUCClient()
    contract = _fully_reviewed_contract(client)
    renamed_qualifier = contract.dataset.qualifier.model_copy(update={"table": "table_that_was_never_provisioned"})
    contract = contract.model_copy(update={"dataset": contract.dataset.model_copy(update={"qualifier": renamed_qualifier})})

    result = validate(contract, client)  # should return a verdict naming the missing table

    assert result.ok is False
    assert any("table_that_was_never_provisioned" in problem for problem in result.problems)


def test_validate_yaml_raises_instead_of_returning_a_verdict_for_a_missing_table(tmp_path: Path):
    """The same gap via the CLI-facing entry point. `validate_yaml`'s own
    docstring promises a `ValidationResult` for *every* well-formed-YAML input
    ("if the file fails schema validation ... returns a failed
    ValidationResult ... otherwise, delegates to validate(contract, client)")
    -- but "delegates to validate()" inherits validate()'s own unhandled-
    exception gap for a missing table, so a CI check running `ucmeta validate`
    against a contract for a dropped/renamed table would crash with a raw
    traceback instead of printing `FAIL: ... -- 1 problem(s)`."""
    client = FakeUCClient()
    contract = _fully_reviewed_contract(client)
    renamed_qualifier = contract.dataset.qualifier.model_copy(update={"table": "does_not_exist_at_all"})
    contract = contract.model_copy(update={"dataset": contract.dataset.model_copy(update={"qualifier": renamed_qualifier})})
    path = tmp_path / "orphaned.yaml"
    contract.to_yaml(path)

    result = validate_yaml(path, client)

    assert result.ok is False


def test_apply_refuses_gracefully_instead_of_crashing_for_a_missing_table(tmp_path: Path):
    """The most consequential version of the same gap: `apply()` calls
    `validate(contract, client)` itself as its refusal gate (module docstring:
    "apply() never trusts a caller to have validated first"). If that call
    raises instead of returning a verdict, `apply()`'s own stated postcondition
    -- "exactly one ReleaseRecord is published ... never silently skipped" --
    is violated for this input: nothing is published, and the caller gets an
    unhandled `UCTableNotFoundError` instead of a `REFUSED` `ApplyResult`. A
    CI job invoking `ucmeta apply` on a merge for a dataset whose table was
    renamed or dropped between review and merge crashes instead of cleanly
    refusing and logging why.
    """
    client = FakeUCClient()
    contract = _fully_reviewed_contract(client)
    renamed_qualifier = contract.dataset.qualifier.model_copy(update={"table": "gone_before_merge"})
    contract = contract.model_copy(update={"dataset": contract.dataset.model_copy(update={"qualifier": renamed_qualifier})})
    log_path = tmp_path / "release_log.jsonl"

    result = apply(contract, client, approved_by=APPROVER, log_path=log_path)  # should refuse, not raise

    assert result.status == DeploymentStatus.REFUSED
    records = read_release_log(log_path)
    assert len(records) == 1  # apply()'s own postcondition: exactly one record, never silently skipped


# ---- TOCTOU: catalogue drifts between apply()'s validate() call and its writes ------


class _DropsColumnOnFirstRealWrite(FakeUCClient):
    """Simulates a concurrent writer dropping a column from the live table in
    the narrow window between `apply()`'s own upfront `validate()` call and
    the write loop that follows it: the moment the *first* real (non-dry-run)
    write executes, this fake removes `region` from its own backing table --
    modelling a second process's `ALTER TABLE ... DROP COLUMN` landing after
    this `apply()` call already got a clean `ValidationResult`, but before its
    writes finished.

    `apply()`'s only re-validation happens once, at the very top of `apply()`
    (`validate(contract, client)`) -- there is no per-write re-check in the
    loop `_build_write_steps` drives, so this is a real, not merely
    theoretical, TOCTOU window. What this test actually proves is which of
    two outcomes it produces: silently applying stale data as if nothing
    changed, or naming the now-missing column as a failed write. A live,
    genuinely concurrent two-writer scenario is what would prove this against
    a real warehouse under real contention; this unit test establishes the
    single-process, single-client behaviour that a live integration test
    would need to build on, not a substitute for one.
    """

    def __init__(self) -> None:
        super().__init__()
        self._dropped = False

    def set_table_comment(self, full_name: str, comment: str, *, dry_run: bool = False) -> str:
        if not dry_run and not self._dropped:
            self._dropped = True
            table = self._tables[full_name]
            table.columns = [c for c in table.columns if c.name != "region"]
        return super().set_table_comment(full_name, comment, dry_run=dry_run)


def test_apply_names_a_column_dropped_between_validate_and_its_own_write_as_a_failure(tmp_path: Path):
    client = _DropsColumnOnFirstRealWrite()
    contract = _fully_reviewed_contract(client)

    result = apply(contract, client, approved_by=APPROVER, log_path=tmp_path / "release_log.jsonl")

    # validate() ran clean (nothing was refused) -- the drift happened after.
    assert result.status == DeploymentStatus.PARTIAL_FAILURE
    assert result.problems == []
    # The dropped column's own write is named as a failure, not silently
    # skipped and not silently "succeeding" against stale in-memory state.
    failed_labels = {attempt.label for attempt in result.writes_failed}
    assert "column comment: region" in failed_labels
    # Everything unrelated to the dropped column still lands -- one missing
    # column mid-apply does not take down the whole write sequence.
    succeeded_labels = {attempt.label for attempt in result.writes_succeeded}
    assert "table comment" in succeeded_labels
    assert "column comment: customer_id" in succeeded_labels


# ---- several (not one) writes fail mid-sequence, named precisely -------------------


class _FailOnSeveralWrites(FakeUCClient):
    """Fails one column comment write *and* the table tags write, so
    `apply()`'s partial-failure reporting can be proven correct under more
    than one simultaneous failure -- constructor's own `_FailOnColumnComment`
    (test_apply.py) only ever fails exactly one write."""

    def set_column_comment(self, full_name: str, column_name: str, comment: str, *, dry_run: bool = False) -> str:
        if not dry_run and column_name == "email":
            raise UCWriteError("synthetic: email comment write failed")
        return super().set_column_comment(full_name, column_name, comment, dry_run=dry_run)

    def set_table_tags(self, full_name: str, tags, *, dry_run: bool = False) -> str:
        if not dry_run:
            raise UCWriteError("synthetic: table tags write failed")
        return super().set_table_tags(full_name, tags, dry_run=dry_run)


def test_apply_names_several_simultaneous_write_failures_precisely(tmp_path: Path):
    client = _FailOnSeveralWrites()
    contract = _fully_reviewed_contract(client)
    log_path = tmp_path / "release_log.jsonl"

    result = apply(contract, client, approved_by=APPROVER, log_path=log_path)

    assert result.status == DeploymentStatus.PARTIAL_FAILURE
    failed_labels = {attempt.label for attempt in result.writes_failed}
    assert failed_labels == {"column comment: email", "table tags"}
    succeeded_labels = {attempt.label for attempt in result.writes_succeeded}
    assert "table comment" in succeeded_labels
    assert "table properties" in succeeded_labels
    assert "column comment: customer_id" in succeeded_labels  # other columns still landed
    # No write silently disappears from both lists.
    total_steps = len(result.writes_succeeded) + len(result.writes_failed)
    assert total_steps >= 1 + len(contract.columns) + 1  # table comment + column comments + table properties, at least

    records = read_release_log(log_path)
    assert len(records) == 1
    record = records[0]
    assert record.deployment_status == DeploymentStatus.PARTIAL_FAILURE
    assert any(entry.startswith("table tags:") for entry in record.writes_failed)
    assert any(entry.startswith("column comment: email:") for entry in record.writes_failed)
    assert "table comment" in record.writes_succeeded


# ---- release-log write failure after catalogue writes already landed --------------


def test_release_log_write_failure_leaves_a_mutated_catalogue_with_no_audit_trail(tmp_path: Path, monkeypatch):
    """Fixed: `apply.py`'s "Release-log write failure" policy (module
    docstring) is that a `publish_release_record` failure -- a real
    possibility for a local append-only file: a read-only filesystem, a
    disk-full condition, a path an unprivileged process cannot create -- never
    escapes as a raw exception. `apply()` catches it and returns the same
    `ApplyResult` it would have returned on a clean publish (`status`,
    `writes_succeeded`, `writes_failed` all still accurately describe what
    happened to the catalogue), with `release_log_error` naming this attempt
    as needing manual audit reconstruction, plus the underlying error.

    This test used to encode the gap this policy closes: a caller getting a
    raw `OSError` instead of an `ApplyResult`, losing the structured
    `writes_succeeded`/`writes_failed` detail entirely. It now proves the
    fix: the caller still gets that detail, still learns the catalogue
    mutation landed, and is explicitly told the release log does not have a
    record of it.
    """
    import uc_metadata.apply as apply_module

    def _boom(record, log_path=None):
        raise OSError("simulated: release log write failed (disk full / unwritable path)")

    monkeypatch.setattr(apply_module, "publish_release_record", _boom)

    client = FakeUCClient()
    contract = _fully_reviewed_contract(client)
    log_path = tmp_path / "release_log.jsonl"
    before = client.get_table(TABLE)
    assert before.comment != contract.dataset.description  # not yet applied

    result = apply(contract, client, approved_by=APPROVER, log_path=log_path)  # must not raise

    # The catalogue write already landed -- apply()'s partial-failure policy
    # for writes did its job of not rolling back.
    after = client.get_table(TABLE)
    assert after.comment == contract.dataset.description

    # The ApplyResult still accurately reports the catalogue outcome...
    assert result.status == DeploymentStatus.SUCCESS
    assert result.writes_succeeded  # the structured detail was not lost

    # ...and names the release-log failure explicitly, rather than hiding it.
    assert result.release_log_error is not None
    assert "MANUAL AUDIT ACTION REQUIRED" in result.release_log_error
    assert "simulated: release log write failed" in result.release_log_error

    # The release log genuinely has nothing for this attempt -- that is the
    # one thing this policy cannot fix from inside apply() itself, which is
    # exactly why release_log_error exists: to make the gap loud, not silent.
    assert read_release_log(log_path) == []

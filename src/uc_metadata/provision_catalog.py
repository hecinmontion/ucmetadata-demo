"""Turns a `catalog-requests/*.yaml` request file into a Unity Catalog catalog
and a first schema inside it (Glossary: Provision; spec F-PLATFORM-004).

This module deliberately shares nothing with `apply.py` but the discipline it
already established -- validate, then refuse or plan, then execute, then
record, in that order, every time (F-PLATFORM-004 Rules & Constraints). It
does not import from `apply.py`: a catalog request is a different input, a
catalog-plus-schema-plus-label is a different kind of write, and the two
modules would gain nothing by sharing code beyond the shape of the discipline
itself. `_WriteStep`, `WriteAttempt` and the plan/execute/report loop below
are therefore a second, independent implementation of that shape, not an
import of `apply.py`'s.

What gets written, in what order, and why -- `_build_write_steps`'s three
possible steps, each a single call to one of the three `UCClient` methods
`uc_client.py` added for this feature:

- `create_catalog(catalog_name, description)` -- always first; nothing else
  can exist until the catalog does.
- `create_schema(catalog_name, default_schema)` -- always second; a catalog
  with no schema in it is not something a team can use (Rules & Constraints:
  "a catalog with no schema in it is not a provisioned catalog").
- `set_catalog_tags(catalog_name, {"sensitivity": ...})` -- only when the
  request declared a `sensitivity`; the create-only rule's single named
  exception, since this is the one write in the plan that is re-applied (and
  converges on the current value) on every run, not just the first.

Refusal (SC-004-03) -- validation runs, and the whole request is refused with
zero writes, before any statement in the plan above is even built. Unlike
`apply()`'s refusal (which trusts its caller to have already loaded a
well-formed `Contract`, since `Contract.from_yaml` raising is a bug-shaped
input, not a request-shaped one), this module's own entry point,
`load_catalog_request`, is itself the thing SC-004-03 requires to never raise:
a request file that is not valid YAML at all, or that fails Pydantic
validation, is refused the same way a request that resolves to no known
business application is -- one problem list, one refusal record, regardless
of which validation layer caught it. This is stricter than `apply.py`'s own
precedent (a malformed contract there propagates straight out with no
release-log entry at all) because SC-004-03 asks for it explicitly: "if the
file [is] not parseable as YAML at all" is one of the ways a request is
named as malformed, and every one of those ways still gets a refusal record.

Identity fallback for an unparseable request -- a `ReleaseRecord` needs a
`full_name` even when the request could not be parsed far enough to know its
own `catalog_name` (the file is not valid YAML, or `catalog_name` itself is
the missing/invalid field). `load_catalog_request` falls back to
`f"<unparseable: {path.name}>"` in that case -- a deliberate choice, not an
oversight, so a human reading the release log still learns which file the
refusal was about, even when the request had nothing else to offer.

Partial-failure policy -- identical to `apply.py`'s, inherited as a
consequence of `default_schema` turning provisioning into an ordered list of
writes (F-PLATFORM-004 rev 3): every planned write is attempted in order, a
failure on one does not abort the rest or roll back what already landed
(there is no transaction across `CREATE CATALOG`/`CREATE SCHEMA`/`ALTER
CATALOG ... SET TAGS`), and the outcome is reported as `success`,
`partial_failure` or `failed` depending on exactly which writes landed
(SC-004-06). A caller that wants to know whether provisioning fully completed
checks `ProvisionResult.ok`; a caller that needs to know what to retry has
`writes_succeeded`/`writes_failed` naming precisely which write labels are in
which state.

Idempotence (SC-004-02) -- every write this module plans is idempotent in
effect on the `UCClient` side (see `uc_client.py`'s docstrings for
`create_catalog`/`create_schema`/`set_catalog_tags`), so re-running the same
request -- because the same merge is re-processed, because the request was
reverted and re-merged, or because the catalog already existed for an
unrelated reason -- succeeds and reports which of the three writes actually
changed anything, rather than refusing on an object that is already there.

Release-log write failure -- same policy as `apply.py`'s: a release-log write
failure never escapes as a raw exception. `_publish_or_flag` catches it and
returns a human-readable "MANUAL AUDIT ACTION REQUIRED" message for
`ProvisionResult.release_log_error`, so a caller that only checks `.ok` still
gets an accurate verdict about the catalogue.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Tuple, Union

import yaml
from pydantic import BaseModel, Field, ValidationError

from uc_metadata.models import CertificationTier, Sensitivity
from uc_metadata.owner_registry import UnknownBusinessApplicationError, resolve_owner
from uc_metadata.release_log import DeploymentStatus, ReleaseRecord, publish_release_record
from uc_metadata.uc_client import UCClient, require_single_part_name

# The catalog-request file's own schema version -- distinct from
# `models.CONTRACT_SCHEMA_VERSION`, since a request file and a contract are
# different documents with independent evolution. Reused as `ReleaseRecord`'s
# `contract_version` for every provisioning run (F-PLATFORM-004 Rules &
# Constraints: "the request-file schema version" goes in that field).
CATALOG_REQUEST_SCHEMA_VERSION = 1


class CatalogRequest(BaseModel):
    """One catalog request, as authored in `catalog-requests/<name>.yaml`
    (spec F-PLATFORM-004, Data: "The request file, concretely").

    `sensitivity` reuses `models.Sensitivity` and `environment` reuses
    `models.CertificationTier` by import, not by declaring parallel
    enumerations -- the same controlled vocabularies a contract's dataset and
    columns already use (Rules & Constraints: "one vocabulary means one
    meaning"). `region` and `sensitivity` are the only two optional fields;
    every other field is required. Unknown fields are rejected (`extra:
    "forbid"`), so a misspelled field name fails the request rather than
    silently doing nothing.
    """

    model_config = {"extra": "forbid"}

    catalog_name: str = Field(min_length=1, description="The catalog to create. Authored explicitly, never derived.")
    business_application_id: str = Field(
        min_length=1, description="Resolved against the owner registry, never copied as a free-text owner."
    )
    business_area: str = Field(min_length=1, description="Free text, validated for presence only.")
    region: Optional[str] = Field(default=None, description="Recorded only; nothing in this feature enacts it.")
    description: str = Field(min_length=1, description="What the catalog is for; carried into its comment.")
    default_schema: str = Field(min_length=1, description="The schema created inside the catalog on day one.")
    sensitivity: Optional[Sensitivity] = Field(
        default=None, description="Catalog-level classification, if the requester declared one."
    )
    requested_by: str = Field(min_length=1, description="The person who authored this request.")
    environment: CertificationTier = Field(description="The medallion tier this catalog serves (not a deploy env).")

    @classmethod
    def from_yaml(cls, path: Union[str, Path]) -> "CatalogRequest":
        """Load, parse and validate a request from a YAML file. Raises on a
        malformed file -- `load_catalog_request` below is the entry point that
        catches those failures and turns them into a refusal; this method is
        the straightforward, exception-raising counterpart `Contract.from_yaml`
        already establishes the shape of, kept for symmetry and for any future
        caller (e.g. authoring tooling) that wants that shape instead."""
        path = Path(path)
        raw = yaml.safe_load(path.read_text())
        if not isinstance(raw, dict):
            raise ValueError(f"{path}: expected a YAML mapping at the document root, got {type(raw).__name__}")
        return cls.model_validate(raw)

    def to_yaml(self, path: Union[str, Path]) -> None:
        """Serialize this request back to YAML, omitting fields that are still
        blank rather than writing them out as `null` -- mirrors
        `Contract.to_yaml` exactly."""
        path = Path(path)
        data = self.model_dump(mode="json", by_alias=True, exclude_none=True)
        path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))


@dataclass(frozen=True)
class WriteAttempt:
    """One catalogue write's outcome, in the order it was attempted --
    independent of, but shaped exactly like, `apply.WriteAttempt` (see this
    module's docstring for why the two are not shared)."""

    label: str
    sql: str
    error: Optional[str] = None


@dataclass(frozen=True)
class ProvisionResult:
    """What a caller of `provision()` needs to know: did the request end up
    provisioned, and exactly what happened to each planned write.

    `catalog_name` is the identity this run was about -- the request's own
    `catalog_name` when the request parsed far enough to have one, or the
    unparseable-file fallback identity otherwise (see `load_catalog_request`)
    -- carried here so a caller (the CLI) can report an outcome without also
    having to hold onto a `CatalogRequest` that, on a refusal, may not exist.
    `status` is the field to branch on: `success` (every write landed),
    `partial_failure` (some did, some did not -- SC-004-06), `failed` (none
    did), or `refused` (validation failed before any write was attempted --
    SC-004-03). `problems` is non-empty only when `status` is `refused`.
    """

    status: DeploymentStatus
    catalog_name: str
    problems: List[str] = field(default_factory=list)
    writes_succeeded: List[WriteAttempt] = field(default_factory=list)
    writes_failed: List[WriteAttempt] = field(default_factory=list)
    release_log_error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.status == DeploymentStatus.SUCCESS


@dataclass(frozen=True)
class _WriteStep:
    """One planned write: a human-readable label, the SQL it would run (built
    via `dry_run=True`), and the zero-argument callable that performs the real
    write when `provision()` decides to run it -- shaped exactly like
    `apply.py`'s `_WriteStep`, reimplemented independently here (see this
    module's docstring)."""

    label: str
    sql: str
    execute: Callable[[], str]


# ---- pure planning: shared by plan_provision and provision -----------------------


def plan_provision(request: CatalogRequest, client: UCClient) -> List[str]:
    """Return the exact ordered list of SQL statements provisioning `request`
    would execute against `client`, performing no writes at all.

    Postcondition: `client`'s catalogue state is byte-for-byte unchanged by
    this call (every underlying write ran with `dry_run=True`) -- printed as
    the plan before execution (SC-004-01: "the full set of writes is planned
    as an ordered list before any of them runs, and that plan is printed").
    """
    return [step.sql for step in _build_write_steps(request, client)]


def _build_write_steps(request: CatalogRequest, client: UCClient) -> List[_WriteStep]:
    """Build the ordered list of writes `plan_provision`/`provision` share:
    create the catalog, create its default schema, and -- only if a
    sensitivity was declared -- label the catalog. This order is the one
    SC-004-01 names explicitly."""
    catalog_name = request.catalog_name
    steps: List[_WriteStep] = [
        _create_catalog_step(client, catalog_name, request.description),
        _create_schema_step(client, catalog_name, request.default_schema),
    ]
    if request.sensitivity is not None:
        steps.append(_set_sensitivity_tag_step(client, catalog_name, request.sensitivity))
    return steps


def _create_catalog_step(client: UCClient, catalog_name: str, description: str) -> _WriteStep:
    sql = client.create_catalog(catalog_name, description, dry_run=True)
    return _WriteStep(
        label="create catalog",
        sql=sql,
        execute=lambda: client.create_catalog(catalog_name, description),
    )


def _create_schema_step(client: UCClient, catalog_name: str, schema_name: str) -> _WriteStep:
    sql = client.create_schema(catalog_name, schema_name, dry_run=True)
    return _WriteStep(
        label="create schema",
        sql=sql,
        execute=lambda: client.create_schema(catalog_name, schema_name),
    )


def _set_sensitivity_tag_step(client: UCClient, catalog_name: str, sensitivity: Sensitivity) -> _WriteStep:
    tags = {"sensitivity": sensitivity.value}
    sql = client.set_catalog_tags(catalog_name, tags, dry_run=True)
    return _WriteStep(
        label="set catalog sensitivity label",
        sql=sql,
        execute=lambda: client.set_catalog_tags(catalog_name, tags),
    )


# ---- validation: never raises, always returns a problem list ---------------------


def load_catalog_request(path: Union[str, Path]) -> Tuple[Optional[CatalogRequest], List[str], str]:
    """Load and fully validate one catalog request file, never raising on a
    malformed one (SC-004-03: every way a request can be malformed still
    produces a named refusal, not an exception).

    Returns `(request, problems, identity)`. `request` is the validated
    `CatalogRequest`, or `None` if the file could not be parsed as YAML, did
    not contain a mapping, or failed Pydantic validation. `problems` is a
    list of human-readable field-level problems -- non-empty exactly when the
    request should be refused, whether that is a parse failure, a Pydantic
    error, or (once Pydantic has produced a valid-shaped model) an illegal
    catalog/schema identifier or an unresolvable business application.
    `identity` is `request.catalog_name` when it is known, or the
    `<unparseable: ...>` fallback naming the file itself when it is not (see
    this module's docstring) -- always a usable string for a `ReleaseRecord`,
    even when `request` is `None`.

    Precondition: none beyond `path` being a path-like value -- a genuinely
    missing file still raises `FileNotFoundError`, since "the file does not
    exist at all" is a different failure than "the file exists and is
    malformed" and is left to the CLI's ordinary error handling, the same way
    `Contract.from_yaml` already treats a missing contract file.
    """
    path = Path(path)
    fallback_identity = f"<unparseable: {path.name}>"

    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        return None, [f"request file is not valid YAML: {exc}"], fallback_identity

    if not isinstance(raw, dict):
        problem = f"expected a YAML mapping at the document root, got {type(raw).__name__}"
        return None, [problem], fallback_identity

    try:
        request = CatalogRequest.model_validate(raw)
    except ValidationError as exc:
        problems = [_format_validation_error(error) for error in exc.errors()]
        raw_catalog_name = raw.get("catalog_name")
        identity = raw_catalog_name if isinstance(raw_catalog_name, str) and raw_catalog_name else fallback_identity
        return None, problems, identity

    problems = _validate_business_rules(request)
    return request, problems, request.catalog_name


def _format_validation_error(error: dict) -> str:
    """Render one `pydantic.ValidationError.errors()` entry as one
    human-readable line -- `<dotted.field.path>: <message>`, or just the
    message when the error has no field path (e.g. "extra fields not
    permitted" at the document root)."""
    loc = ".".join(str(part) for part in error["loc"])
    return f"{loc}: {error['msg']}" if loc else str(error["msg"])


def _validate_business_rules(request: CatalogRequest) -> List[str]:
    """The checks Pydantic's field-level validation cannot express on its
    own: identifier legality (SC-004-03: "the catalog or schema name not a
    legal single-part identifier") and owner resolution (SC-004-03: "the
    business-application identifier unresolvable"). Runs only once
    `request` is already a valid-shaped `CatalogRequest`."""
    problems: List[str] = []
    try:
        require_single_part_name(request.catalog_name)
    except ValueError as exc:
        problems.append(f"catalog_name: {exc}")
    try:
        require_single_part_name(request.default_schema)
    except ValueError as exc:
        problems.append(f"default_schema: {exc}")
    try:
        resolve_owner(request.business_application_id)
    except UnknownBusinessApplicationError as exc:
        problems.append(str(exc))
    return problems


# ---- the real thing ---------------------------------------------------------------


def provision(
    request_path: Union[str, Path],
    client: UCClient,
    *,
    approved_by: str,
    log_path: Optional[Union[str, Path]] = None,
) -> ProvisionResult:
    """Provision the catalog `request_path` describes against the catalogue
    `client` is backed by, for real.

    Precondition: `approved_by` names the human whose merge authorised this
    run (the CLI resolves this from the merge event; this function trusts its
    caller for that resolution, the same boundary `apply()` and
    `release_log.py` already draw). Postcondition, on every call: exactly one
    `ReleaseRecord` is attempted for publication (success, partial failure,
    failure, or refusal -- never silently skipped), and the returned
    `ProvisionResult.status` matches it; if publishing that record itself
    fails, `ProvisionResult.release_log_error` names that failure rather than
    raising (see module docstring's "Release-log write failure" policy).

    Refuses the whole request, writing nothing, if `load_catalog_request`
    reports any problem at all -- a parse failure, a Pydantic error, an
    illegal identifier, or an unresolvable business application (SC-004-03).
    Otherwise attempts every planned write in order (`_build_write_steps`'s
    order), continuing past a failed write rather than aborting (SC-004-06),
    and returns/logs exactly which writes succeeded and which did not.
    """
    request, problems, identity = load_catalog_request(request_path)
    if problems:
        return _refuse(identity, problems, approved_by, request, log_path)

    assert request is not None  # no problems means load_catalog_request found a valid request
    steps = _build_write_steps(request, client)
    succeeded: List[WriteAttempt] = []
    failed: List[WriteAttempt] = []
    try:
        for step in steps:
            try:
                executed_sql = step.execute()
            except Exception as exc:  # noqa: BLE001 -- deliberate: see apply.py's identical partial-failure policy
                failed.append(WriteAttempt(label=step.label, sql=step.sql, error=str(exc)))
            else:
                succeeded.append(WriteAttempt(label=step.label, sql=executed_sql))
    except BaseException:
        # A KeyboardInterrupt/SystemExit escaping the loop, not an ordinary
        # write failure (those are caught above). Still publish the audit
        # trail for whatever landed before re-raising unchanged -- same
        # policy as apply.py's own "Interrupted mid-apply" handling.
        _publish_record(
            request, approved_by, DeploymentStatus.PARTIAL_FAILURE, succeeded, failed, log_path,
            summary_suffix=" (interrupted before completion)",
        )
        raise

    status = _deployment_status(succeeded, failed)
    release_log_error = _publish_record(request, approved_by, status, succeeded, failed, log_path)
    return ProvisionResult(
        status=status,
        catalog_name=request.catalog_name,
        writes_succeeded=succeeded,
        writes_failed=failed,
        release_log_error=release_log_error,
    )


def _refuse(
    identity: str,
    problems: List[str],
    approved_by: str,
    request: Optional[CatalogRequest],
    log_path: Optional[Union[str, Path]],
) -> ProvisionResult:
    """Refuse the whole request (SC-004-03) before any write is attempted.

    `request` is `None` when the refusal is a parse/YAML/Pydantic failure and
    a `CatalogRequest` when it is a business-rule failure (an illegal
    identifier or an unresolvable owner) -- in the latter case `requested_by`
    is still known and worth recording, even though the request as a whole is
    refused."""
    record = ReleaseRecord.now(
        full_name=identity,
        contract_version=CATALOG_REQUEST_SCHEMA_VERSION,
        summary=f"refused: {len(problems)} validation problem(s), no writes attempted",
        approved_by=approved_by,
        deployment_status=DeploymentStatus.REFUSED,
        problems=problems,
        requested_by=request.requested_by if request is not None else None,
    )
    release_log_error = _publish_or_flag(record, log_path)
    return ProvisionResult(
        status=DeploymentStatus.REFUSED,
        catalog_name=identity,
        problems=problems,
        release_log_error=release_log_error,
    )


def _publish_record(
    request: CatalogRequest,
    approved_by: str,
    status: DeploymentStatus,
    succeeded: List[WriteAttempt],
    failed: List[WriteAttempt],
    log_path: Optional[Union[str, Path]],
    *,
    summary_suffix: str = "",
) -> Optional[str]:
    """Build and publish the `ReleaseRecord` for one provisioning attempt
    (ordinary completion or an interrupted one), returning
    `_publish_or_flag`'s verdict."""
    record = ReleaseRecord.now(
        full_name=request.catalog_name,
        contract_version=CATALOG_REQUEST_SCHEMA_VERSION,
        summary=_summary(succeeded, failed) + summary_suffix,
        approved_by=approved_by,
        deployment_status=status,
        writes_succeeded=[attempt.label for attempt in succeeded],
        writes_failed=[f"{attempt.label}: {attempt.error}" for attempt in failed],
        requested_by=request.requested_by,
    )
    return _publish_or_flag(record, log_path)


def _publish_or_flag(record: ReleaseRecord, log_path: Optional[Union[str, Path]]) -> Optional[str]:
    """Publish `record`, returning `None` on success. Never raises -- see
    module docstring's "Release-log write failure" policy, identical to
    `apply.py`'s."""
    try:
        publish_release_record(record, log_path=log_path)
    except Exception as exc:  # noqa: BLE001 -- deliberate, see module docstring
        return (
            f"MANUAL AUDIT ACTION REQUIRED: catalogue changes for {record.full_name!r} "
            f"(deployment_status={record.deployment_status.value}) were applied, but the "
            f"release record failed to persist: {exc}"
        )
    return None


def _deployment_status(succeeded: List[WriteAttempt], failed: List[WriteAttempt]) -> DeploymentStatus:
    if not failed:
        return DeploymentStatus.SUCCESS
    if succeeded:
        return DeploymentStatus.PARTIAL_FAILURE
    return DeploymentStatus.FAILED


def _summary(succeeded: List[WriteAttempt], failed: List[WriteAttempt]) -> str:
    if not failed:
        return f"provisioned {len(succeeded)} write(s)"
    return f"provisioned {len(succeeded)} write(s), {len(failed)} write(s) failed: " + "; ".join(
        f"{attempt.label} ({attempt.error})" for attempt in failed
    )

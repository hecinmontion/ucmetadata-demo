"""The immutable, append-only account of every apply attempt (Rules & Constraints:
"every apply publishes one immutable, append-only release record -- what changed,
who approved it, when, and the deployment outcome").

This module is deliberately narrow: one record shape (`ReleaseRecord`), one write
function (`publish_release_record`) and one read function (`read_release_log`).
It knows nothing about pull requests, GitHub, or how "who approved it" was
established -- `approved_by` is a plain string the caller (today: `apply.py`;
later: a CLI reading a merged PR's reviewers) supplies. Wiring that resolution up
is that caller's job, not this module's.

The production adapter this stands in for is named rather than built (spec
Out of Scope: "a real central release-log service ... the production adapter
swaps the writer, not the record's shape"): here, the writer is a local
append-only JSON-lines file (`release_log.jsonl`, one JSON object per line, one
line per apply attempt), reached through this module's two functions so that a
future central service can replace the file-based writer/reader without any
caller changing.

Every apply attempt is published here -- success, failure, partial failure, and
a refusal before any write was attempted. Logging only successes would make this
an advertisement, not an audit trail; a reviewer asking "was this ever applied
and did it work" needs the failures and refusals on the record too.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import List, Optional, Union

from pydantic import BaseModel, Field

# release_log.jsonl at the repository root, resolved relative to this file so it
# works regardless of the caller's working directory -- same technique as
# `models.SCHEMA_PATH`. Callers that want an isolated log (every test in this
# codebase) pass their own `log_path` rather than relying on this default.
DEFAULT_LOG_PATH = Path(__file__).resolve().parents[2] / "release_log.jsonl"


class DeploymentStatus(str, Enum):
    """The deployment outcome of one apply attempt (Rules & Constraints: "whether
    it deployed")."""

    SUCCESS = "success"
    PARTIAL_FAILURE = "partial_failure"
    FAILED = "failed"
    REFUSED = "refused"


class ReleaseRecord(BaseModel):
    """One immutable record: what changed, who approved it, when, and whether it
    deployed (Rules & Constraints, verbatim).

    `full_name` and `contract_version` are the contract's identity -- which
    dataset, which schema revision. `summary` is a short, human-readable account
    of what changed (a caller may pass a one-line description or a joined list of
    field paths; this module does not prescribe which). `writes_succeeded` and
    `writes_failed` name exactly which catalogue writes landed and which did not
    -- required for `partial_failure` to mean something more specific than
    "something went wrong somewhere" (Rules & Constraints: the deployment outcome
    must be honest about a partial write, never silently upgraded to `success`
    or silently swallowed).

    Reused, with two field meanings widened, by `provision_catalog.py` (spec
    F-PLATFORM-004): a catalog-provisioning run's `full_name` carries the
    catalog's name and `contract_version` carries the request-file schema
    version (`provision_catalog.CATALOG_REQUEST_SCHEMA_VERSION`), rather than a
    dataset's three-part name and a contract's version -- one audit trail is
    worth more than two tidier ones (F-PLATFORM-004 Rules & Constraints). That
    feature also adds the one field below that is additive to this record
    (`requested_by`): existing log lines still parse, since it is optional and
    defaults to absent, and nothing that reads the log today looks for it.
    """

    full_name: str = Field(min_length=1, description="The contract's catalog.schema.table identity.")
    contract_version: int = Field(description="The contract schema version applied, models.Contract.version.")
    summary: str = Field(min_length=1, description="What changed, in one human-readable account.")
    approved_by: str = Field(min_length=1, description="The human who approved this change (caller-supplied).")
    timestamp: datetime = Field(description="When this apply attempt happened, UTC.")
    deployment_status: DeploymentStatus
    writes_succeeded: List[str] = Field(
        default_factory=list, description="Labels of the catalogue writes that landed, in attempted order."
    )
    writes_failed: List[str] = Field(
        default_factory=list,
        description="Labels of the catalogue writes that did not land, each with its error, in attempted order.",
    )
    problems: List[str] = Field(
        default_factory=list,
        description="Validation problems that caused a refusal; empty unless deployment_status is 'refused'.",
    )
    requested_by: Optional[str] = Field(
        default=None,
        description=(
            "The human who asked for this change, when that is a fact distinct from who "
            "approved it (spec F-PLATFORM-004: a catalog request's requester). Absent for "
            "every apply attempt that predates this field or has no separate requester to "
            "record -- optional and additive, so existing log lines still parse."
        ),
    )

    @classmethod
    def now(
        cls,
        *,
        full_name: str,
        contract_version: int,
        summary: str,
        approved_by: str,
        deployment_status: DeploymentStatus,
        writes_succeeded: Optional[List[str]] = None,
        writes_failed: Optional[List[str]] = None,
        problems: Optional[List[str]] = None,
        requested_by: Optional[str] = None,
    ) -> "ReleaseRecord":
        """Build a record timestamped at the moment of the call -- the constructor
        every apply attempt actually uses, so "when" is never a caller-supplied
        guess."""
        return cls(
            full_name=full_name,
            contract_version=contract_version,
            summary=summary,
            approved_by=approved_by,
            timestamp=datetime.now(timezone.utc),
            deployment_status=deployment_status,
            writes_succeeded=writes_succeeded or [],
            writes_failed=writes_failed or [],
            problems=problems or [],
            requested_by=requested_by,
        )


def publish_release_record(record: ReleaseRecord, log_path: Optional[Union[str, Path]] = None) -> None:
    """Append `record` as one JSON line to the release log. Never rewrites,
    reorders or removes a line already present -- append-only, per Rules &
    Constraints ("immutable, append-only release record").

    Precondition: `record` is a fully-built `ReleaseRecord` (Pydantic has already
    validated it). Postcondition: `log_path` (or `DEFAULT_LOG_PATH`) exists and
    has exactly one more line than before, containing `record`'s JSON
    serialization; every line already in the file is untouched.
    """
    path = Path(log_path) if log_path is not None else DEFAULT_LOG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(record.model_dump_json())
        handle.write("\n")


def read_release_log(log_path: Optional[Union[str, Path]] = None) -> List[ReleaseRecord]:
    """Read every record back, in the order they were appended.

    Postcondition: returns `[]` if the log does not exist yet (never raises for
    "no releases published yet"); otherwise one `ReleaseRecord` per non-blank
    line, in file order.
    """
    path = Path(log_path) if log_path is not None else DEFAULT_LOG_PATH
    if not path.exists():
        return []
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [ReleaseRecord.model_validate_json(line) for line in lines]

"""Publishes one coverage run's findings into the durable, append-only
coverage-history table (spec: F-PLATFORM-002; ADR-008 -- "the substance of
this feature is the table, the dashboard is what the table makes possible").

`publish_coverage_history(report, client, run_id)` is the one write function
this module exposes. It is invoked *after* `coverage.compute_coverage(...)`
has already produced a `CoverageReport` -- publishing history is a separate
step behind one narrow interface, the same shape as
`release_log.publish_release_record(...)` (spec Rules & Constraints: "the
history publish is a separate step behind one narrow interface, invoked after
the coverage computation, exactly as the release log is"). Coverage
computation itself acquires no dependency on this module or on a warehouse; a
caller with no catalogue access can compute coverage and simply never call
this function. `ucmeta coverage`'s `--publish-history` flag is the only thing
that ever does (see `cli.py`), off by default, so the offline path never even
imports this far into the call graph on a run that didn't ask for it
(SC-002-03).

*Granularity* (ADR-008, resolved): one row per dataset per run, and nothing
else -- no pre-aggregated run-level or per-team summary rows. Every aggregate
a dashboard might want (per team, per run, overall) is derived at query time
from these rows, which is what keeps "exactly one coverage computation" true:
a stored aggregate would be a second place for a number to be computed, and
therefore a second place for it to disagree with `coverage.py`.

*Append-only, by construction*: this module contains no `UPDATE`, no
`DELETE`, and builds no SQL of its own -- the only statement it ever sends is
`UCClient.insert_rows`'s single multi-row `INSERT`, built by
`uc_client.build_insert_sql`.

*Whole-run-or-nothing* (Rules & Constraints: "a half-written run in the table
is worse than no run, because it reads as a real coverage drop"): every
dataset's row for a run is sent to `UCClient.insert_rows` in one call, which
renders exactly one SQL statement with one `VALUES` tuple per dataset.
Databricks executes that statement as a single transaction, so the atomicity
this feature needs comes from the *shape* of the write -- one statement, not
one write per dataset -- rather than from a rollback/retry loop this module
would otherwise have to reimplement (the same "trust the platform for what it
already guarantees" reasoning `RealUCClient`'s other writes rely on). This is
a stronger and simpler guarantee than `apply.py`'s partial-failure policy
needs to make: `apply()` genuinely cannot make its five-or-so independent
catalogue writes atomic (Unity Catalog's DDL is not transactional across
statements, per `apply.py`'s own docstring), so it names exactly which writes
landed instead. A coverage-history run has no such structural constraint --
every row is the same shape, going to the same table, in the same statement
-- so this module chooses atomicity over partial bookkeeping. If that one
statement fails (warehouse unreachable, credential expired, the table not
bootstrapped yet), `publish_coverage_history` raises
`CoverageHistoryPublishError` naming the run id and the underlying failure,
and zero rows have landed -- it never catches that error and calls it a
partial success. That exception is also structurally distinct from "history
publishing was not requested" (this function is simply never called on that
path), so a scheduled run that silently stopped recording history cannot be
mistaken for one that was never asked to (spec SC-002-04).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from uc_metadata.coverage import CoverageReport, DatasetCoverage
from uc_metadata.uc_client import UCClient, UCClientError

# workspace.platform: a schema created and owned by the platform team,
# separate from the data-product schemas the contracts describe (Rules &
# Constraints: "coverage measurement is platform infrastructure, not a data
# product, and should not sit inside the estate it measures"). Bootstrapped
# once by scripts/bootstrap_coverage_history.sql -- see that file for the
# full column-by-column rationale, mirrored in `_history_row` below.
DEFAULT_COVERAGE_HISTORY_TABLE = "workspace.platform.coverage_history"


class CoverageHistoryPublishError(UCClientError):
    """The history write for one run did not land -- zero rows were appended
    (see module docstring's whole-run-or-nothing reasoning). Names the run id
    and the underlying failure, so a scheduled run whose history publish
    failed is distinguishable in the logs from one that was never asked to
    publish at all (spec SC-002-04)."""


def generate_run_id() -> str:
    """A fresh run id: a UTC timestamp prefix (so a human paging through the
    table can sort and read run ids without a join back to `run_timestamp`)
    plus 8 hex characters of a UUID4 (so two runs starting within the same
    second never collide). Every caller of `publish_coverage_history` that
    does not already have a run id of its own (today: only `cli.py`) should
    call this rather than inventing another id shape.
    """
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{uuid.uuid4().hex[:8]}"


def publish_coverage_history(
    report: CoverageReport,
    client: UCClient,
    run_id: str,
    *,
    table_name: str = DEFAULT_COVERAGE_HISTORY_TABLE,
) -> None:
    """Append one row per dataset in `report` to `table_name`, all in a
    single `INSERT` statement.

    Precondition: `report` is an already-computed `CoverageReport` -- Rules &
    Constraints' "coverage is never published without at least one outcome
    measure" is already enforced by `CoverageReport.outcome_measures`'
    `min_length=1`, so this function trusts that rather than re-checking it;
    `run_id` identifies this run and is written identically into every row
    this call produces, so every row from one run can be grouped and ordered
    against every other run's by `run_id`/`run_timestamp` alone.

    Postcondition: `report.dataset_count` new rows exist in `table_name`, or
    none do (see module docstring for why a single multi-row `INSERT` is what
    makes that guarantee true rather than aspirational). Raises
    `CoverageHistoryPublishError` naming `run_id` and the underlying failure
    if the write does not land -- never returns normally on a partial write.
    A `report` with zero datasets is a no-op (nothing to append), not an
    error, matching `compute_coverage([])`'s own "empty is not an error"
    convention.
    """
    if not report.datasets:
        return
    rows = [_history_row(dataset, report, run_id) for dataset in report.datasets]
    try:
        client.insert_rows(table_name, rows)
    except Exception as exc:  # noqa: BLE001 -- deliberate: see module docstring
        raise CoverageHistoryPublishError(
            f"coverage history publish for run {run_id!r} did not land "
            f"({report.dataset_count} row(s) attempted against {table_name!r}): {exc}"
        ) from exc


def _history_row(dataset: DatasetCoverage, report: CoverageReport, run_id: str) -> Dict[str, Any]:
    """One dataset's history row, matching
    `scripts/bootstrap_coverage_history.sql`'s column list exactly.

    `dataset_fill_rate` is this dataset's own mean across the four fill-rate
    dimensions -- the per-dataset "overall fill rate" the spec's Data section
    names -- deliberately distinct from `DatasetCoverage.is_fully_covered`,
    which is `True` only when every dimension is filled at once; the history
    table keeps both the continuous figure and the four booleans it is
    derived from, so a dashboard can chart "how covered" as well as "covered
    or not" without recomputing either from the other.

    The outcome measure carried into every row is `report.outcome_measures`'
    first entry: `compute_coverage` never returns zero of them, and this
    prototype only ever produces one (`time_to_first_query_days`), so "first"
    and "only" coincide today. A future second measure would need its own
    column pair, named here as an implementation detail rather than solved --
    the one-row-per-dataset granularity this table commits to has no natural
    home for a second measure without either widening the row or adding a
    measure-keyed table, and neither is needed by anything this prototype
    ships.
    """
    dimensions = (dataset.has_owner, dataset.has_description, dataset.has_sensitivity, dataset.has_dq_rules)
    outcome = report.outcome_measures[0]
    return {
        "run_id": run_id,
        "run_timestamp": report.generated_at,
        "full_name": dataset.full_name,
        "team": dataset.team,
        "has_owner": dataset.has_owner,
        "has_description": dataset.has_description,
        "has_sensitivity": dataset.has_sensitivity,
        "has_dq_rules": dataset.has_dq_rules,
        "dataset_fill_rate": sum(dimensions) / len(dimensions),
        "certification_tier": dataset.certification,
        "certification_supported_by_evidence": dataset.certification_supported_by_evidence,
        "outcome_measure_name": outcome.name,
        "outcome_measure_value": outcome.value,
        "outcome_measure_unit": outcome.unit,
        "outcome_measure_simulated": outcome.simulated,
    }

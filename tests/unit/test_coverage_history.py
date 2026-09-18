"""Happy-path tests for `coverage_history.py`: two coverage runs against the
fake produce two rows per dataset with the earlier run's rows left exactly
as written (SC-002-01), a run whose history write cannot land raises loudly
and leaves zero rows behind (SC-002-04, whole-run-or-nothing), and the
offline default never constructs a real client or touches the history table
at all (SC-002-03) -- the mechanical guard the spec calls "the only thing
that makes the guarantee enforceable rather than aspirational".

Two structural checks close the append-only claim (Rules & Constraints:
"coverage history is append-only ... never updated, never deleted, never
rewritten"): `coverage_history.py`'s own source never calls any `UCClient`
write method other than `insert_rows`, and the bootstrap DDL contains no
`UPDATE`/`DELETE` statement.

Adversarial and boundary cases (a row whose keys don't match another row's,
a run_id collision, a malformed table name) belong to the adversary
persona -- see `test_coverage.py`'s module docstring for the same scoping
note this codebase already uses.

Runs entirely offline against `fake_uc.FakeUCClient`; no network anywhere in
this file.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from test_coverage import CAMPAIGNS, CUSTOMERS, _contract

from dashboard import app as dashboard_app
from uc_metadata import cli, coverage_history, harvest, uc_client
from uc_metadata.coverage import compute_coverage
from uc_metadata.coverage_history import (
    DEFAULT_COVERAGE_HISTORY_TABLE,
    CoverageHistoryPublishError,
    generate_run_id,
    publish_coverage_history,
)
from uc_metadata.fake_uc import FakeUCClient
from uc_metadata.uc_client import UCWriteError

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = Path(__file__).parent / "fixtures"


class _FailingInsertClient(FakeUCClient):
    """A `FakeUCClient` whose real (non-dry-run) `insert_rows` always fails,
    simulating an unreachable warehouse -- the one seam
    `publish_coverage_history`'s whole-run-or-nothing guarantee needs to be
    exercised without a live network."""

    def insert_rows(self, full_name, rows, *, dry_run: bool = False) -> str:
        if not dry_run:
            raise UCWriteError("synthetic warehouse-unreachable failure")
        return super().insert_rows(full_name, rows, dry_run=dry_run)


# ---- happy path: two runs become a trend (SC-002-01) -----------------------------


@pytest.mark.scenario("SC-002-01")
def test_two_runs_append_one_row_per_dataset_leaving_the_earlier_run_unchanged():
    client = FakeUCClient()
    not_yet_described = _contract(CAMPAIGNS, "BA-20144", description=harvest.PLACEHOLDER_DESCRIPTION)
    steady = _contract(CUSTOMERS, "BA-10231")

    report_1 = compute_coverage([not_yet_described, steady])
    run_id_1 = generate_run_id()
    publish_coverage_history(report_1, client, run_id_1)

    now_described = _contract(CAMPAIGNS, "BA-20144")  # description filled in between runs
    report_2 = compute_coverage([now_described, steady])
    run_id_2 = generate_run_id()
    publish_coverage_history(report_2, client, run_id_2)

    rows = client.inserted_rows(DEFAULT_COVERAGE_HISTORY_TABLE)
    assert len(rows) == 4  # 2 datasets x 2 runs
    assert run_id_1 != run_id_2
    assert [row["run_id"] for row in rows] == [run_id_1, run_id_1, run_id_2, run_id_2]  # append order, not resorted

    campaigns_run_1 = next(r for r in rows if r["run_id"] == run_id_1 and r["full_name"] == CAMPAIGNS)
    campaigns_run_2 = next(r for r in rows if r["run_id"] == run_id_2 and r["full_name"] == CAMPAIGNS)
    assert campaigns_run_1["has_description"] is False  # first run's entry: not yet covered
    assert campaigns_run_2["has_description"] is True  # second run's entry: now covered
    assert campaigns_run_1["has_description"] is False  # the first run's row was never rewritten by the second publish

    for row in rows:
        assert row["outcome_measure_simulated"] is True  # the simulated label survives into every row


@pytest.mark.scenario("SC-002-01")
def test_history_row_carries_the_per_dataset_fill_dimensions_and_evidence_verdict():
    client = FakeUCClient()
    contract = _contract(CUSTOMERS, "BA-10231")
    report = compute_coverage([contract], client=client)
    run_id = generate_run_id()

    publish_coverage_history(report, client, run_id)

    row = client.inserted_rows(DEFAULT_COVERAGE_HISTORY_TABLE)[0]
    assert row["full_name"] == CUSTOMERS
    assert row["team"] == "Customer Analytics"
    assert row["has_owner"] is True
    assert row["has_description"] is True
    assert row["has_sensitivity"] is True
    assert row["has_dq_rules"] is True
    assert row["dataset_fill_rate"] == 1.0
    assert row["certification_tier"] == "bronze"
    assert row["certification_supported_by_evidence"] is True
    assert row["outcome_measure_name"] == "time_to_first_query_days"
    assert row["outcome_measure_value"] == report.outcome_measures[0].value


def test_publish_coverage_history_over_zero_datasets_is_a_no_op():
    client = FakeUCClient()
    report = compute_coverage([])

    publish_coverage_history(report, client, generate_run_id())

    assert client.inserted_rows(DEFAULT_COVERAGE_HISTORY_TABLE) == []


# ---- whole-run-or-nothing: the publish fails loudly, no partial rows (SC-002-04) -


@pytest.mark.scenario("SC-002-04")
def test_a_failed_publish_leaves_zero_rows_and_names_the_run():
    client = _FailingInsertClient()
    report = compute_coverage([_contract(CUSTOMERS, "BA-10231"), _contract(CAMPAIGNS, "BA-20144")])
    run_id = generate_run_id()

    with pytest.raises(CoverageHistoryPublishError) as exc_info:
        publish_coverage_history(report, client, run_id)

    assert run_id in str(exc_info.value)
    assert "synthetic warehouse-unreachable failure" in str(exc_info.value)
    assert client.inserted_rows(DEFAULT_COVERAGE_HISTORY_TABLE) == []  # not even the first dataset's row landed


@pytest.mark.scenario("SC-002-04")
def test_a_failed_publish_does_not_stop_a_later_successful_one():
    """A run whose publish failed is distinguishable from one that landed --
    a subsequent successful run's rows are unaffected by the earlier
    failure."""
    report = compute_coverage([_contract(CUSTOMERS, "BA-10231")])

    failing_client = _FailingInsertClient()
    with pytest.raises(CoverageHistoryPublishError):
        publish_coverage_history(report, failing_client, generate_run_id())

    client = FakeUCClient()
    run_id = generate_run_id()
    publish_coverage_history(report, client, run_id)

    rows = client.inserted_rows(DEFAULT_COVERAGE_HISTORY_TABLE)
    assert len(rows) == 1
    assert rows[0]["run_id"] == run_id


# ---- append-only enforcement: structural, not just behavioural -------------------


def test_coverage_history_module_only_ever_calls_insert_rows_on_the_client():
    """The only `UCClient` write method `coverage_history.py`'s source ever
    calls is `insert_rows` -- a future edit that adds a
    `client.set_*`/any update-shaped call against this table fails this
    check rather than being discovered by a reviewer reading SQL logs."""
    source = Path(coverage_history.__file__).read_text()
    calls = re.findall(r"\bclient\.(\w+)\(", source)
    assert calls == ["insert_rows"]


def test_bootstrap_ddl_contains_no_update_or_delete_statements():
    ddl_path = REPO_ROOT / "scripts" / "bootstrap_coverage_history.sql"
    code_lines = [
        line for line in ddl_path.read_text().splitlines() if line.strip() and not line.strip().startswith("--")
    ]
    joined = "\n".join(code_lines).upper()
    assert "UPDATE " not in joined
    assert "DELETE " not in joined
    assert "CREATE SCHEMA" in joined
    assert "CREATE TABLE" in joined


# ---- the offline guarantee: no credentials, no warehouse, no history (SC-002-03) -


@pytest.mark.scenario("SC-002-03")
def test_offline_default_never_constructs_a_real_client_or_reaches_history(tmp_path, monkeypatch):
    """A reviewer with no Databricks account, no credentials and no network
    runs the default (non-`--live`, `--publish-history` omitted) loop and
    gets the same point-in-time report and static page as before this
    feature existed. `RealUCClient.__init__` is patched to raise, so any
    future change that quietly couples the default path to a real client --
    and therefore to a warehouse or the history table -- fails this test
    immediately rather than only being discovered by a reviewer who cannot
    run the demo."""
    for var in ("ANTHROPIC_API_KEY", "DATABRICKS_HOST", "DATABRICKS_TOKEN", "DATABRICKS_CONFIG_PROFILE"):
        monkeypatch.delenv(var, raising=False)

    def _fail_if_constructed(self, *args, **kwargs):
        raise AssertionError("RealUCClient must never be constructed on the default offline path (SC-002-03)")

    monkeypatch.setattr(uc_client.RealUCClient, "__init__", _fail_if_constructed)

    report_path = tmp_path / "coverage_report.json"
    exit_code = cli.main(["coverage", str(FIXTURES_DIR), "-o", str(report_path)])  # --publish-history omitted

    assert exit_code == 0
    assert report_path.exists()
    raw_report = json.loads(report_path.read_text())
    assert raw_report["dataset_count"] == 3
    assert raw_report["outcome_measures"][0]["simulated"] is True

    html_path = tmp_path / "index.html"
    dashboard_exit_code = dashboard_app.main([str(report_path), "-o", str(html_path)])

    assert dashboard_exit_code == 0
    document = html_path.read_text()
    assert document.startswith("<!DOCTYPE html>")
    assert document.count("<tr") >= 3
    assert "SIMULATED" in document

"""Happy-path tests for `dashboard/app.py`: a `CoverageReport` renders to a
non-trivial, well-formed static HTML page that shows overall/dimension/team
fill rate, marks a fully-covered dataset visibly differently from a
not-fully-covered one, and -- the one thing this module exists to get right --
never strips the `simulated=True` / caveat labeling `coverage.py` attaches to
every outcome measure.

Adversarial and boundary cases (a malformed/missing input JSON file, a report
with zero datasets, HTML-unsafe characters in a dataset name) belong to the
adversary persona -- see `test_coverage.py`'s module docstring for the same
scoping note this codebase already uses.

The last test in this file is a real smoke test, not a fixture-built one: it
runs `ucmeta coverage` against `tests/unit/fixtures/` to produce a real
`coverage_report.json`, exactly the file the CI `coverage.yml` workflow
produces, then feeds that real file through `dashboard/app.py` for real.
"""

from __future__ import annotations

import html
import json
import subprocess
import sys
from pathlib import Path

from test_coverage import CAMPAIGNS, CUSTOMERS, _contract

from dashboard import app as dashboard_app
from uc_metadata import cli
from uc_metadata.coverage import compute_coverage
from uc_metadata.models import CertificationTier

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---- rendering against a small in-memory report -----------------------------------


def test_render_dashboard_shows_overall_dimension_and_team_fill_rates():
    fully_covered = _contract(CUSTOMERS, "BA-10231")  # -> Customer Analytics, has DQ rules registered
    missing_sensitivity = _contract(CAMPAIGNS, "BA-20144", sensitivity=None)  # -> Marketing Growth

    report = compute_coverage([fully_covered, missing_sensitivity])
    document = dashboard_app.render_dashboard(report)

    assert "<html" in document
    assert "50%" in document  # overall fill rate: 1 of 2 fully covered
    assert "Customer Analytics" in document
    assert "Marketing Growth" in document
    assert CUSTOMERS in document
    assert CAMPAIGNS in document


def test_render_dashboard_marks_covered_dataset_distinctly_from_not_covered():
    fully_covered = _contract(CUSTOMERS, "BA-10231")
    not_covered = _contract(CAMPAIGNS, "BA-20144", sensitivity=None)

    report = compute_coverage([fully_covered, not_covered])
    document = dashboard_app.render_dashboard(report)

    assert 'class="pill pill-covered"' in document
    assert 'class="pill pill-not-covered"' in document
    # The row itself carries a distinct class too, not just the pill.
    assert 'class="row-covered"' in document
    assert 'class="row-not-covered"' in document


def test_render_dashboard_a_dataset_flipping_to_covered_changes_its_pill():
    # The static legend text in the "Datasets" section intro always mentions both
    # pill classes -- assert against the dataset table row, not the whole document,
    # so this test is about the per-dataset state actually flipping, not prose.
    still_missing_sensitivity = _contract(CAMPAIGNS, "BA-20144", sensitivity=None)
    report_before = compute_coverage([still_missing_sensitivity])
    row_before = _dataset_table_body(dashboard_app.render_dashboard(report_before))
    assert 'class="row-not-covered"' in row_before
    assert 'class="row-covered"' not in row_before

    now_covered = _contract(CAMPAIGNS, "BA-20144")  # sensitivity now set -> fully covered
    report_after = compute_coverage([now_covered])
    row_after = _dataset_table_body(dashboard_app.render_dashboard(report_after))
    assert 'class="row-covered"' in row_after
    assert 'class="row-not-covered"' not in row_after


def _dataset_table_body(document: str) -> str:
    return document.split('<tbody>', 1)[1].split('</tbody>', 1)[0]


def test_render_dashboard_never_drops_the_simulated_outcome_measure_caveat():
    report = compute_coverage([_contract(CUSTOMERS, "BA-10231")])

    document = dashboard_app.render_dashboard(report)

    assert "SIMULATED" in document
    measure = report.outcome_measures[0]
    # Rendered verbatim (HTML-escaped, since it lands inside a <p>), not paraphrased
    # or dropped -- this is the exact string a future edit must not silently strip.
    assert html.escape(measure.caveat) in document
    assert "no real consumption telemetry" in document


def test_render_dashboard_evidence_unsupported_gold_reads_clearly():
    unsupported = _contract(CAMPAIGNS, "BA-20144", certification=CertificationTier.GOLD)

    report = compute_coverage([unsupported])  # no client -> certification_supported_by_evidence is None
    document = dashboard_app.render_dashboard(report)

    assert "gold" in document
    assert "not verified (no client)" in document


# ---- load_report: the exact JSON shape `ucmeta coverage -o` writes ---------------


def test_load_report_reads_back_exactly_what_ucmeta_coverage_writes(tmp_path):
    report = compute_coverage([_contract(CUSTOMERS, "BA-10231")])
    report_path = tmp_path / "coverage_report.json"
    report_path.write_text(report.model_dump_json(indent=2) + "\n")

    loaded = dashboard_app.load_report(report_path)

    assert loaded.dataset_count == report.dataset_count
    assert loaded.overall_fill_rate == report.overall_fill_rate
    assert loaded.outcome_measures[0].simulated is True


def test_main_writes_an_html_file_from_a_json_report(tmp_path):
    report = compute_coverage([_contract(CUSTOMERS, "BA-10231")])
    report_path = tmp_path / "coverage_report.json"
    report_path.write_text(report.model_dump_json(indent=2) + "\n")
    output_path = tmp_path / "index.html"

    exit_code = dashboard_app.main([str(report_path), "-o", str(output_path)])

    assert exit_code == 0
    assert output_path.exists()
    assert "SIMULATED" in output_path.read_text()


# ---- real smoke test: real ucmeta coverage output, real dashboard render --------


def test_smoke_ucmeta_coverage_then_dashboard_produces_a_real_nontrivial_page(tmp_path):
    """Runs the actual two-step flow a reviewer would run: `ucmeta coverage`
    against a real contracts directory (fixtures/), then `dashboard/app.py`
    against that real JSON file -- not a fixture `CoverageReport` built in
    memory, the same JSON bytes CI's coverage.yml workflow would produce."""
    report_path = tmp_path / "coverage_report.json"
    exit_code = cli.main(["coverage", str(FIXTURES_DIR), "-o", str(report_path)])
    assert exit_code == 0
    assert report_path.exists()

    raw_report = json.loads(report_path.read_text())
    assert raw_report["dataset_count"] == 3
    assert raw_report["outcome_measures"][0]["simulated"] is True

    output_path = tmp_path / "index.html"
    dashboard_exit_code = dashboard_app.main([str(report_path), "-o", str(output_path)])
    assert dashboard_exit_code == 0

    document = output_path.read_text()
    assert document.startswith("<!DOCTYPE html>")
    assert document.count("<tr") >= 3  # one row per dataset, not an empty shell
    assert "SIMULATED" in document
    assert "workspace.sales.orders" in document
    assert "</html>" in document


def test_smoke_dashboard_runnable_as_a_standalone_subprocess(tmp_path):
    """`python dashboard/app.py <report> -o <output>` -- the exact invocation
    the module docstring documents -- actually runs, with no package install
    step beyond what the repo's own `.venv` already provides."""
    report_path = tmp_path / "coverage_report.json"
    cli_exit_code = cli.main(["coverage", str(FIXTURES_DIR), "-o", str(report_path)])
    assert cli_exit_code == 0

    output_path = tmp_path / "index.html"
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "dashboard" / "app.py"), str(report_path), "-o", str(output_path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert output_path.exists()
    assert "SIMULATED" in output_path.read_text()

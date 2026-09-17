"""Renders a `coverage_report.json` (the exact output of `ucmeta coverage
<dir> -o coverage_report.json`, `coverage.py`'s `CoverageReport.model_dump_json()`
-- consumed here as-is, never re-derived) into a single static HTML file
(spec: F-PLATFORM-001, `dashboard/app.py` build verdict -- "static generated
page ... trivially runnable on a reviewer's laptop and cannot fail live for
reasons unrelated to the design").

Deliberately a standalone script, not a `ucmeta` verb: `cli.py`'s own
docstring scopes it to "one entry point, five verbs" backed by modules that
already do the real work, and every one of those verbs is pure wiring around
existing business logic with no templating of its own. HTML rendering is a
new kind of output, not a thin composition of an existing module the way
`harvest`/`propose`/`validate`/`apply`/`coverage` are -- adding it as a sixth
capability (even behind a `--html` flag on `coverage`) would blur that count
and give `_cmd_coverage` a second responsibility (JSON serialization *and*
HTML templating) that its docstring doesn't currently carry. The
`coverage.yml` workflow already treats the two as decoupled steps for the
same reason ("wiring up an actual dashboard page is `dashboard/app.py`'s job
... not this workflow's"). So: run `ucmeta coverage contracts/ -o
coverage_report.json` first, then this script against that file --
`python dashboard/app.py coverage_report.json -o dashboard/index.html`. No
web server, no JS framework: inline CSS, and a small amount of vanilla JS
only for the one interactive affordance (sortable dataset table) that a
static file can offer without a server.

The one semantic rule this module exists to enforce: every `OutcomeMeasure`
`coverage.py` returns already carries `simulated=True` and a caveat string
naming why (module docstring: "no caller ... can present it as an observed
fact by accident"). This renderer is that caller's last stop before a human
reads the number, so it must not be the place that accident finally happens
-- every outcome measure is rendered inside a visibly-labeled "SIMULATED"
callout, never as a bare figure indistinguishable from the real fill-rate
numbers above it.
"""

from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path
from typing import List, Optional, Sequence

from uc_metadata.coverage import CoverageReport, DatasetCoverage, OutcomeMeasure, TeamCoverage

# Repo root, resolved the same way cli.py's _REPO_ROOT / models.SCHEMA_PATH are:
# relative to this file, so it works regardless of the caller's cwd.
_REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_PATH = _REPO_ROOT / "coverage_report.json"
DEFAULT_OUTPUT_PATH = Path(__file__).resolve().parent / "index.html"

_DIMENSION_LABELS = {
    "owner": "Owner",
    "description": "Description",
    "sensitivity": "Sensitivity",
    "dq_rules": "DQ rule(s) attached",
}


# ---- entry point -----------------------------------------------------------------


def render_dashboard(report: CoverageReport) -> str:
    """Render a `CoverageReport` to a complete, self-contained HTML document.

    Precondition: `report` is a `CoverageReport` already validated by
    Pydantic construction (loaded via `load_report`, or built directly by a
    caller such as a test) -- this function trusts the type and does not
    re-check its shape, the same boundary `coverage.py`'s own functions
    trust once past their own construction. Postcondition: the returned
    string is a complete `<html>` document; every element of
    `report.outcome_measures` appears inside a callout carrying the word
    "SIMULATED" and its `caveat` text verbatim -- this function has no code
    path that renders an outcome measure without both.
    """
    sections = [
        _render_header(report),
        _render_overall_fill_rate(report),
        _render_dimension_breakdown(report),
        _render_team_breakdown(report.by_team),
        _render_outcome_measures(report.outcome_measures),
        _render_dataset_table(report.datasets),
    ]
    return _PAGE_TEMPLATE.format(
        generated_at=html.escape(report.generated_at.isoformat()),
        body="\n".join(sections),
        script=_SORT_SCRIPT,
    )


def load_report(path: Path) -> CoverageReport:
    """Load a `CoverageReport` from the JSON file at `path` -- the exact
    shape `ucmeta coverage -o <path>` writes via `model_dump_json()`.

    Precondition: `path` exists and contains one JSON object matching
    `CoverageReport`'s schema. Raises `FileNotFoundError` (with `path` named)
    if it does not exist, and lets Pydantic's `ValidationError` propagate
    unmodified for malformed content -- both are a caller mistake to fix, not
    a state this function papers over.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"{path}: no coverage report here. Run `ucmeta coverage <contracts_dir> -o {path}` first."
        )
    return CoverageReport.model_validate_json(path.read_text())


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    report = load_report(Path(args.input))
    html_document = render_dashboard(report)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_document)
    print(f"Wrote coverage dashboard for {report.dataset_count} dataset(s) to {output_path}")
    return 0


def _parse_args(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="dashboard/app.py",
        description=(
            "Render a ucmeta coverage JSON report (ucmeta coverage <dir> -o coverage_report.json) "
            "into a single static HTML dashboard. No server -- open the output file directly in a "
            "browser, or serve it from any static host."
        ),
        epilog="Example: python dashboard/app.py coverage_report.json -o dashboard/index.html",
    )
    parser.add_argument(
        "input",
        nargs="?",
        default=str(DEFAULT_INPUT_PATH),
        help=f"Path to a coverage_report.json produced by `ucmeta coverage` (default: {DEFAULT_INPUT_PATH}).",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=str(DEFAULT_OUTPUT_PATH),
        help=f"Path to write the generated HTML dashboard to (default: {DEFAULT_OUTPUT_PATH}).",
    )
    return parser.parse_args(argv)


# ---- section renderers -------------------------------------------------------------
# Each takes report data and returns an HTML fragment. Kept small and single-purpose
# rather than one long template string, so a future field addition touches one
# function instead of hunting through a wall of markup.


def _render_header(report: CoverageReport) -> str:
    return f"""
    <header>
      <h1>UC Metadata Coverage Dashboard</h1>
      <p class="generated-at">Generated at {html.escape(report.generated_at.isoformat())}
        &middot; {report.dataset_count} dataset(s)</p>
    </header>
    """


def _render_overall_fill_rate(report: CoverageReport) -> str:
    pct = _pct(report.overall_fill_rate)
    return f"""
    <section class="card">
      <h2>Overall fill rate</h2>
      <p class="big-number">{pct}</p>
      <p class="subtext">Share of datasets with an owner, a description, a sensitivity
        classification, and at least one DQ rule attached, all at once.
        <strong>Fill is not correctness</strong> -- see the dataset table below for
        datasets that are fully covered but quality-red.</p>
    </section>
    """


def _render_dimension_breakdown(report: CoverageReport) -> str:
    rows = "\n".join(
        f'<div class="bar-row"><span class="bar-label">{html.escape(_DIMENSION_LABELS.get(dimension, dimension))}'
        f'</span>{_bar(rate)}<span class="bar-value">{_pct(rate)}</span></div>'
        for dimension, rate in report.fill_rate_by_dimension.items()
    )
    return f"""
    <section class="card">
      <h2>Fill rate by dimension</h2>
      {rows}
    </section>
    """


def _render_team_breakdown(teams: List[TeamCoverage]) -> str:
    if not teams:
        return '<section class="card"><h2>Fill rate by team</h2><p class="subtext">No datasets.</p></section>'
    rows = "\n".join(
        f'<div class="bar-row"><span class="bar-label">{html.escape(team.team)} '
        f'<span class="muted">({team.dataset_count} dataset(s))</span></span>'
        f"{_bar(team.fill_rate)}<span class=\"bar-value\">{_pct(team.fill_rate)}</span></div>"
        for team in teams
    )
    return f"""
    <section class="card">
      <h2>Fill rate by team</h2>
      {rows}
    </section>
    """


def _render_outcome_measures(measures: List[OutcomeMeasure]) -> str:
    cards = "\n".join(_render_one_outcome_measure(measure) for measure in measures)
    return f"""
    <section class="card outcome-section">
      <h2>Outcome measure(s)</h2>
      {cards}
    </section>
    """


def _render_one_outcome_measure(measure: OutcomeMeasure) -> str:
    # The load-bearing part of this whole module: a SIMULATED badge and the
    # caveat text, rendered next to the number, not in a footnote -- see the
    # module docstring's "semantic rule this module exists to enforce".
    badge = '<span class="badge badge-simulated">SIMULATED</span>' if measure.simulated else ""
    return f"""
      <div class="outcome-measure">
        <div class="outcome-headline">
          <span class="outcome-name">{html.escape(_humanize(measure.name))}</span>
          {badge}
        </div>
        <p class="big-number">{measure.value:g} {html.escape(measure.unit)}
          <span class="muted">(n={measure.sample_size})</span></p>
        <p class="caveat">{html.escape(measure.caveat)}</p>
      </div>
    """


def _render_dataset_table(datasets: List[DatasetCoverage]) -> str:
    rows = "\n".join(_render_dataset_row(dataset) for dataset in datasets)
    return f"""
    <section class="card">
      <h2>Datasets</h2>
      <p class="subtext">Click a column header to sort. A dataset that just gained its
        last missing dimension flips from <span class="pill pill-not-covered">not
        covered</span> to <span class="pill pill-covered">covered</span> here.</p>
      <table id="dataset-table">
        <thead>
          <tr>
            <th data-sort="text">Dataset</th>
            <th data-sort="text">Team</th>
            <th data-sort="bool">Covered</th>
            <th data-sort="bool">Owner</th>
            <th data-sort="bool">Description</th>
            <th data-sort="bool">Sensitivity</th>
            <th data-sort="bool">DQ rules</th>
            <th data-sort="text">Certification</th>
            <th data-sort="bool">Evidence-backed</th>
          </tr>
        </thead>
        <tbody>
          {rows}
        </tbody>
      </table>
    </section>
    """


def _render_dataset_row(dataset: DatasetCoverage) -> str:
    covered_pill = (
        '<span class="pill pill-covered">covered</span>'
        if dataset.is_fully_covered
        else '<span class="pill pill-not-covered">not covered</span>'
    )
    return f"""
          <tr class="{'row-covered' if dataset.is_fully_covered else 'row-not-covered'}">
            <td>{html.escape(dataset.full_name)}</td>
            <td>{html.escape(dataset.team)}</td>
            <td data-value="{int(dataset.is_fully_covered)}">{covered_pill}</td>
            <td data-value="{int(dataset.has_owner)}">{_check(dataset.has_owner)}</td>
            <td data-value="{int(dataset.has_description)}">{_check(dataset.has_description)}</td>
            <td data-value="{int(dataset.has_sensitivity)}">{_check(dataset.has_sensitivity)}</td>
            <td data-value="{int(dataset.has_dq_rules)}">{_check(dataset.has_dq_rules)}</td>
            <td>{html.escape(dataset.certification)}</td>
            <td data-value="{_evidence_sort_value(dataset.certification_supported_by_evidence)}">
              {_evidence_label(dataset.certification_supported_by_evidence)}</td>
          </tr>
    """


# ---- small formatting helpers -------------------------------------------------------


def _pct(rate: float) -> str:
    return f"{rate:.0%}"


def _bar(rate: float) -> str:
    width_pct = max(0.0, min(1.0, rate)) * 100
    return f'<span class="bar-track"><span class="bar-fill" style="width: {width_pct:.1f}%"></span></span>'


def _check(value: bool) -> str:
    return '<span class="check-yes">&#10003;</span>' if value else '<span class="check-no">&#10007;</span>'


def _evidence_label(supported) -> str:
    if supported is None:
        return '<span class="muted">not verified (no client)</span>'
    return _check(supported)


def _evidence_sort_value(supported) -> int:
    if supported is None:
        return -1
    return int(supported)


def _humanize(name: str) -> str:
    return name.replace("_", " ")


# ---- page template ------------------------------------------------------------------


_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>UC Metadata Coverage Dashboard</title>
<style>
  :root {{
    --covered: #1a7f37;
    --not-covered: #b42318;
    --simulated: #9a6700;
    --card-bg: #ffffff;
    --page-bg: #f4f5f7;
    --border: #d9dce1;
    --text: #1f2328;
    --muted: #6b7280;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    background: var(--page-bg);
    color: var(--text);
    margin: 0;
    padding: 2rem;
  }}
  header h1 {{ margin-bottom: 0.25rem; }}
  .generated-at {{ color: var(--muted); margin-top: 0; }}
  .card {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 1.25rem 1.5rem;
    margin-bottom: 1.5rem;
  }}
  .card h2 {{ margin-top: 0; }}
  .big-number {{ font-size: 2.25rem; font-weight: 700; margin: 0.25rem 0; }}
  .subtext {{ color: var(--muted); }}
  .muted {{ color: var(--muted); font-weight: 400; }}
  .bar-row {{ display: grid; grid-template-columns: 12rem 1fr 4rem; align-items: center; gap: 0.75rem; margin: 0.5rem 0; }}
  .bar-label {{ font-weight: 600; }}
  .bar-track {{ display: block; height: 0.75rem; background: #e8eaed; border-radius: 999px; overflow: hidden; }}
  .bar-fill {{ display: block; height: 100%; background: var(--covered); border-radius: 999px; }}
  .bar-value {{ text-align: right; font-variant-numeric: tabular-nums; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; }}
  th, td {{ text-align: left; padding: 0.5rem 0.6rem; border-bottom: 1px solid var(--border); }}
  th {{ cursor: pointer; user-select: none; color: var(--muted); font-size: 0.85rem; text-transform: uppercase; }}
  th:hover {{ color: var(--text); }}
  tr.row-covered {{ background: rgba(26, 127, 55, 0.06); }}
  tr.row-not-covered {{ background: rgba(180, 35, 24, 0.05); }}
  .pill {{ display: inline-block; padding: 0.15rem 0.6rem; border-radius: 999px; font-size: 0.8rem; font-weight: 600; }}
  .pill-covered {{ background: rgba(26, 127, 55, 0.15); color: var(--covered); }}
  .pill-not-covered {{ background: rgba(180, 35, 24, 0.12); color: var(--not-covered); }}
  .check-yes {{ color: var(--covered); font-weight: 700; }}
  .check-no {{ color: var(--not-covered); font-weight: 700; }}
  .outcome-section {{ border: 2px solid var(--simulated); background: #fff9ec; }}
  .outcome-measure {{ padding: 0.5rem 0; }}
  .outcome-headline {{ display: flex; align-items: center; gap: 0.75rem; }}
  .outcome-name {{ font-weight: 600; text-transform: capitalize; }}
  .badge {{ display: inline-block; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 0.75rem; font-weight: 700; letter-spacing: 0.04em; }}
  .badge-simulated {{ background: var(--simulated); color: #ffffff; }}
  .caveat {{ color: #6b4e00; background: #fff3d6; border: 1px solid var(--simulated); border-radius: 6px; padding: 0.6rem 0.8rem; margin-top: 0.4rem; }}
</style>
</head>
<body>
{body}
<script>
{script}
</script>
</body>
</html>
"""

# Small vanilla-JS table sort: click a <th> to sort #dataset-table by that column.
# `data-sort` on each <th> picks text vs. numeric/bool comparison; `data-value` on
# each <td> (when present) is the value actually sorted on, so a rendered pill/check
# glyph doesn't have to also be a sortable string.
_SORT_SCRIPT = """
(function () {
  var table = document.getElementById('dataset-table');
  if (!table) return;
  var headers = table.querySelectorAll('th');
  headers.forEach(function (header, columnIndex) {
    header.addEventListener('click', function () {
      var tbody = table.querySelector('tbody');
      var rows = Array.prototype.slice.call(tbody.querySelectorAll('tr'));
      var ascending = header.getAttribute('data-sort-dir') !== 'asc';
      var sortType = header.getAttribute('data-sort') || 'text';
      rows.sort(function (rowA, rowB) {
        var cellA = rowA.children[columnIndex];
        var cellB = rowB.children[columnIndex];
        var valueA = cellA.getAttribute('data-value');
        var valueB = cellB.getAttribute('data-value');
        if (valueA === null) valueA = cellA.textContent.trim();
        if (valueB === null) valueB = cellB.textContent.trim();
        if (sortType === 'bool') {
          valueA = Number(valueA);
          valueB = Number(valueB);
          return ascending ? valueA - valueB : valueB - valueA;
        }
        return ascending ? valueA.localeCompare(valueB) : valueB.localeCompare(valueA);
      });
      headers.forEach(function (h) { h.removeAttribute('data-sort-dir'); });
      header.setAttribute('data-sort-dir', ascending ? 'asc' : 'desc');
      rows.forEach(function (row) { tbody.appendChild(row); });
    });
  });
})();
"""


if __name__ == "__main__":
    sys.exit(main())

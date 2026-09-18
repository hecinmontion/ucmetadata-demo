"""Validates dashboards/coverage.lvdash.json (ADR-008, F-PLATFORM-002).

Two tiers, matching this project's established real/fake split:

- Offline (always runs): the definition is well-formed JSON, every widget's
  `datasetName` reference resolves to a real dataset, and every dataset carries a
  non-empty SELECT. Cheap, no credentials, catches a corrupted or hand-edited file.
- Live (`uc_live`, `UC_LIVE_TESTS=1`): each dataset's underlying SQL actually executes
  against the real workspace and returns rows without error. This is the honest limit
  of what can be verified without eyes on the rendered page (see dashboards/README.md)
  -- it proves the queries are correct, not that the widgets visually render correctly.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from uc_metadata.uc_client import RealUCClient

DASHBOARD_PATH = Path(__file__).resolve().parents[2] / "dashboards" / "coverage.lvdash.json"
UC_LIVE_TESTS_ENABLED = os.environ.get("UC_LIVE_TESTS") == "1"


def _load_definition() -> dict:
    return json.loads(DASHBOARD_PATH.read_text())


def _dataset_queries(definition: dict) -> dict:
    """Map dataset name -> its SQL, joining `queryLines` if that's the shape the API
    normalised it to, or falling back to a plain `query` string."""
    queries = {}
    for dataset in definition["datasets"]:
        if "queryLines" in dataset:
            queries[dataset["name"]] = "\n".join(dataset["queryLines"])
        else:
            queries[dataset["name"]] = dataset["query"]
    return queries


def test_dashboard_definition_file_exists_and_parses():
    assert DASHBOARD_PATH.exists(), f"expected a committed dashboard definition at {DASHBOARD_PATH}"
    definition = _load_definition()
    assert "datasets" in definition and "pages" in definition


def test_every_widget_dataset_reference_resolves_to_a_real_dataset():
    definition = _load_definition()
    dataset_names = {d["name"] for d in definition["datasets"]}
    assert dataset_names, "dashboard defines zero datasets"

    referenced = set()
    for page in definition["pages"]:
        for entry in page["layout"]:
            widget = entry["widget"]
            for query in widget.get("queries", []):
                referenced.add(query["query"]["datasetName"])

    unresolved = referenced - dataset_names
    assert not unresolved, f"widget(s) reference dataset name(s) not defined anywhere: {unresolved}"


def test_every_dataset_has_a_non_empty_select():
    definition = _load_definition()
    queries = _dataset_queries(definition)
    assert queries, "no datasets found"
    for name, sql in queries.items():
        assert sql.strip(), f"dataset {name!r} has an empty query"
        assert sql.strip().upper().startswith("SELECT"), f"dataset {name!r}'s query is not a SELECT: {sql!r}"


def test_outcome_measure_dataset_title_names_it_as_simulated():
    """Mechanical guard for the project-wide rule that a simulated figure is never
    presented as observed -- this dashboard is a second surface for that rule
    (ADR-008), so its own title has to carry the label, not just the underlying data."""
    definition = _load_definition()
    outcome_dataset = next(d for d in definition["datasets"] if d["name"] == "ds_outcome")
    assert "simulated" in outcome_dataset["displayName"].lower()

    outcome_widget = next(
        entry["widget"]
        for page in definition["pages"]
        for entry in page["layout"]
        if entry["widget"]["name"] == "w_outcome_counter"
    )
    assert "simulated" in outcome_widget["spec"]["frame"]["title"].lower()


@pytest.mark.uc_live
@pytest.mark.skipif(not UC_LIVE_TESTS_ENABLED, reason="set UC_LIVE_TESTS=1 to run against the real workspace")
def test_every_dataset_query_executes_against_the_live_workspace():
    """Proves the SQL behind every widget is actually correct against real data --
    the honest limit of verification available without a way to see the page render
    (dashboards/README.md explains the gap and what to do about it)."""
    client = RealUCClient(profile="ucmeta")
    definition = _load_definition()
    queries = _dataset_queries(definition)

    for name, sql in queries.items():
        rows = client._run_query(sql)  # noqa: SLF001 -- no public generic-query method exists; see uc_client.py
        assert isinstance(rows, list), f"dataset {name!r} query did not return rows: {sql!r}"

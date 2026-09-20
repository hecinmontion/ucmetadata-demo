"""Happy-path tests for `provision_catalog.py`: a valid request plans and
provisions a catalog and its schema (SC-004-01), re-provisioning an existing
catalog is an idempotent no-op except that the sensitivity label converges on
a changed value (SC-004-02), a malformed or unresolvable request is refused
whole with zero writes (SC-004-03), and a mid-plan failure is reported as a
named partial success that a re-run then completes (SC-004-06).

Adversarial and boundary cases belong to the adversary persona, not here --
see `test_apply.py`'s module docstring for the same scoping note this
codebase already uses. SC-004-05 (the live path) is deliberately unbound: it
belongs to F-PLATFORM-005, not this feature.

Runs entirely against `fake_uc.FakeUCClient` (no network); F-PLATFORM-004 has
no live path for this module to exercise even optionally (see
`provision_catalog.py`'s own module docstring).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest
import yaml

from uc_metadata.fake_uc import FakeUCClient
from uc_metadata.provision_catalog import (
    CATALOG_REQUEST_SCHEMA_VERSION,
    load_catalog_request,
    plan_provision,
    provision,
)
from uc_metadata.release_log import DeploymentStatus, read_release_log
from uc_metadata.uc_client import UCClientError

KNOWN_BA_ID = "BA-10231"  # owner_registry: Customer Analytics
APPROVER = "hector"


def _request_fields(**overrides: Any) -> Dict[str, Any]:
    fields: Dict[str, Any] = {
        "catalog_name": "analytics_ba10231",
        "business_application_id": KNOWN_BA_ID,
        "business_area": "analytics",
        "region": None,
        "description": "Analytics tables for the customer-analytics team.",
        "default_schema": "default",
        "sensitivity": None,
        "requested_by": "Priya Natarajan",
        "environment": "bronze",
    }
    fields.update(overrides)
    return fields


def _write_request(path: Path, *, omit: tuple = (), **overrides: Any) -> Path:
    fields = _request_fields(**overrides)
    for key in omit:
        fields.pop(key, None)
    path.write_text(yaml.safe_dump(fields, sort_keys=False, allow_unicode=True))
    return path


class _FailOnCreateSchema(FakeUCClient):
    """A `FakeUCClient` that fails one specific real (non-dry-run) schema
    creation, so `provision()`'s partial-failure path (SC-004-06) can be
    exercised without a live network. `fail` is a plain attribute a test can
    flip between calls, to exercise "re-running the same request afterwards
    completes the job" (SC-004-06) against the very same catalogue state that
    the first, failing run already produced."""

    def __init__(self, *, fail: bool = True) -> None:
        super().__init__()
        self.fail = fail

    def create_schema(self, catalog_name: str, schema_name: str, *, dry_run: bool = False) -> str:
        if not dry_run and self.fail:
            raise UCClientError("synthetic scenario-test failure creating schema")
        return super().create_schema(catalog_name, schema_name, dry_run=dry_run)


# ---- SC-004-01: happy path --------------------------------------------------------


@pytest.mark.scenario("SC-004-01")
def test_valid_request_plans_and_provisions_catalog_schema_and_label(tmp_path: Path):
    client = FakeUCClient()
    request_path = _write_request(
        tmp_path / "analytics_ba10231.yaml",
        sensitivity="confidential",
        requested_by="Priya Natarajan",
    )
    log_path = tmp_path / "release_log.jsonl"

    request, problems, identity = load_catalog_request(request_path)
    assert problems == []
    assert identity == "analytics_ba10231"

    plan = plan_provision(request, client)
    assert plan[0].startswith("CREATE CATALOG IF NOT EXISTS")
    assert plan[1].startswith("CREATE SCHEMA IF NOT EXISTS")
    assert "ALTER CATALOG" in plan[2] and "SET TAGS" in plan[2]
    assert client.catalog_exists("analytics_ba10231") is False  # planning wrote nothing

    result = provision(request_path, client, approved_by=APPROVER, log_path=log_path)

    assert result.status == DeploymentStatus.SUCCESS
    assert result.ok is True
    assert [attempt.sql for attempt in result.writes_succeeded] == plan
    assert client.catalog_exists("analytics_ba10231") is True
    assert client.schema_exists("analytics_ba10231", "default") is True
    assert client.catalog_tags("analytics_ba10231")["sensitivity"] == "confidential"

    records = read_release_log(log_path)
    assert len(records) == 1
    record = records[0]
    assert record.full_name == "analytics_ba10231"
    assert record.deployment_status == DeploymentStatus.SUCCESS
    assert record.approved_by == APPROVER
    assert record.requested_by == "Priya Natarajan"  # requester and approver: two separate facts
    assert record.contract_version == CATALOG_REQUEST_SCHEMA_VERSION
    assert len(record.writes_succeeded) == 3


# ---- SC-004-02: re-provisioning an existing catalog is an idempotent no-op -------


@pytest.mark.scenario("SC-004-02")
def test_reprovisioning_leaves_the_catalog_as_is_but_converges_the_label(tmp_path: Path):
    client = FakeUCClient()
    request_path = tmp_path / "analytics_ba10231.yaml"
    log_path = tmp_path / "release_log.jsonl"
    _write_request(request_path, description="Original description.", sensitivity="internal")

    first = provision(request_path, client, approved_by=APPROVER, log_path=log_path)
    assert first.status == DeploymentStatus.SUCCESS

    # Edited after the catalog already exists: a changed description and a
    # changed sensitivity.
    _write_request(request_path, description="Edited description -- must not overwrite the comment.", sensitivity="confidential")
    second = provision(request_path, client, approved_by=APPROVER, log_path=log_path)

    assert second.status == DeploymentStatus.SUCCESS
    assert second.ok is True
    # Create-only: the description is never re-applied to a catalog that already exists.
    assert client.catalog_comment("analytics_ba10231") == "Original description."
    # The one named exception: the sensitivity label converges on the current value.
    assert client.catalog_tags("analytics_ba10231")["sensitivity"] == "confidential"

    records = read_release_log(log_path)
    assert len(records) == 2
    assert all(r.deployment_status == DeploymentStatus.SUCCESS for r in records)


@pytest.mark.scenario("SC-004-02")
def test_reprovisioning_completes_a_catalog_left_with_no_schema(tmp_path: Path):
    """A request whose catalog exists but whose schema does not -- the state
    SC-004-06 can leave behind -- completes the job on this run, creating the
    missing schema and reporting that it did."""
    client = FakeUCClient()
    client.create_catalog("analytics_ba10231", "Created by hand before the request existed.")
    request_path = _write_request(tmp_path / "analytics_ba10231.yaml")
    log_path = tmp_path / "release_log.jsonl"

    result = provision(request_path, client, approved_by=APPROVER, log_path=log_path)

    assert result.status == DeploymentStatus.SUCCESS
    assert client.schema_exists("analytics_ba10231", "default") is True
    succeeded_labels = {attempt.label for attempt in result.writes_succeeded}
    assert "create schema" in succeeded_labels


# ---- SC-004-03: a malformed request is refused before anything is created -------


@pytest.mark.scenario("SC-004-03")
def test_unparseable_yaml_is_refused_with_zero_writes(tmp_path: Path):
    client = FakeUCClient()
    request_path = tmp_path / "broken.yaml"
    request_path.write_text("catalog_name: [this is not: valid yaml")
    log_path = tmp_path / "release_log.jsonl"

    result = provision(request_path, client, approved_by=APPROVER, log_path=log_path)

    assert result.status == DeploymentStatus.REFUSED
    assert result.writes_succeeded == []
    assert result.writes_failed == []
    assert len(result.problems) >= 1

    records = read_release_log(log_path)
    assert len(records) == 1
    assert records[0].deployment_status == DeploymentStatus.REFUSED
    assert records[0].full_name == "<unparseable: broken.yaml>"
    assert records[0].problems == result.problems


@pytest.mark.scenario("SC-004-03")
def test_request_missing_a_required_field_is_refused_and_names_the_problem(tmp_path: Path):
    client = FakeUCClient()
    request_path = _write_request(tmp_path / "analytics_ba10231.yaml", omit=("requested_by",))
    log_path = tmp_path / "release_log.jsonl"

    result = provision(request_path, client, approved_by=APPROVER, log_path=log_path)

    assert result.status == DeploymentStatus.REFUSED
    assert any("requested_by" in problem for problem in result.problems)
    assert client.catalog_exists("analytics_ba10231") is False

    records = read_release_log(log_path)
    assert len(records) == 1
    assert records[0].deployment_status == DeploymentStatus.REFUSED
    # catalog_name itself was present and valid, so the record still names the
    # catalog the refused request was about, not the unparseable-file fallback.
    assert records[0].full_name == "analytics_ba10231"


@pytest.mark.scenario("SC-004-03")
def test_request_with_unresolvable_business_application_is_refused(tmp_path: Path):
    client = FakeUCClient()
    request_path = _write_request(tmp_path / "analytics_unknown.yaml", business_application_id="BA-99999")
    log_path = tmp_path / "release_log.jsonl"

    result = provision(request_path, client, approved_by=APPROVER, log_path=log_path)

    assert result.status == DeploymentStatus.REFUSED
    assert any("BA-99999" in problem for problem in result.problems)
    assert client.catalog_exists("analytics_ba10231") is False


@pytest.mark.scenario("SC-004-03")
def test_batch_with_one_bad_and_one_good_request_processes_both_independently(tmp_path: Path):
    """If a push contains several request files and only one is bad, the
    others are still processed -- each `provision()` call is independent, so
    one refused request never blocks or hides another's success."""
    client = FakeUCClient()
    log_path = tmp_path / "release_log.jsonl"
    good_path = _write_request(tmp_path / "analytics_ba10231.yaml", catalog_name="analytics_ba10231")
    bad_path = _write_request(
        tmp_path / "marketing_bad.yaml", catalog_name="marketing_bad", omit=("business_area",)
    )

    good_result = provision(good_path, client, approved_by=APPROVER, log_path=log_path)
    bad_result = provision(bad_path, client, approved_by=APPROVER, log_path=log_path)

    assert good_result.status == DeploymentStatus.SUCCESS
    assert bad_result.status == DeploymentStatus.REFUSED
    assert client.catalog_exists("analytics_ba10231") is True
    assert client.catalog_exists("marketing_bad") is False

    records = read_release_log(log_path)
    assert len(records) == 2
    assert {r.deployment_status for r in records} == {DeploymentStatus.SUCCESS, DeploymentStatus.REFUSED}


# ---- SC-004-06: the catalog is created and the schema is not --------------------


@pytest.mark.scenario("SC-004-06")
def test_schema_creation_failure_reports_partial_success_and_a_rerun_completes_it(tmp_path: Path):
    client = _FailOnCreateSchema()
    request_path = _write_request(tmp_path / "analytics_ba10231.yaml")
    log_path = tmp_path / "release_log.jsonl"

    first = provision(request_path, client, approved_by=APPROVER, log_path=log_path)

    assert first.status == DeploymentStatus.PARTIAL_FAILURE
    assert first.ok is False
    assert {attempt.label for attempt in first.writes_succeeded} == {"create catalog"}
    assert {attempt.label for attempt in first.writes_failed} == {"create schema"}
    assert "synthetic scenario-test failure" in first.writes_failed[0].error
    assert client.catalog_exists("analytics_ba10231") is True  # not rolled back
    assert client.schema_exists("analytics_ba10231", "default") is False

    client.fail = False  # the transient/rejected-name condition has cleared
    second = provision(request_path, client, approved_by=APPROVER, log_path=log_path)

    assert second.status == DeploymentStatus.SUCCESS
    assert client.schema_exists("analytics_ba10231", "default") is True

    records = read_release_log(log_path)
    assert len(records) == 2
    assert records[0].deployment_status == DeploymentStatus.PARTIAL_FAILURE
    assert any(entry.startswith("create schema:") for entry in records[0].writes_failed)
    assert records[1].deployment_status == DeploymentStatus.SUCCESS

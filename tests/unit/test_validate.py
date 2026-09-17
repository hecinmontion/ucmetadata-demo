"""Happy-path tests for `validate.py`'s four checks (schema well-formedness via
`validate_yaml`, drift, unreviewed markers, placeholder sentinels).

Adversarial and boundary cases (a table that vanishes mid-validate, a contract
whose qualifier names a table the client can't reach, a `change_classes.yaml`
with a syntax error, etc.) belong to the adversary persona, not here. These
tests confirm each check does what it was designed to do -- passes clean on a
fully-reviewed, drift-free contract, and each of the four failure modes is
named specifically and collected alongside any others rather than stopping at
the first.

Runs against `fake_uc.FakeUCClient`'s default fixture (mirrors the live
workspace, no network) -- see this phase's report for the separate live drift
check against the real Free Edition workspace.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from uc_metadata.fake_uc import FakeUCClient
from uc_metadata.harvest import harvest
from uc_metadata.models import CertificationTier, Column, Contract, Proposed, Refresh, Sensitivity
from uc_metadata.uc_client import RealUCClient, UCClient
from uc_metadata.validate import validate, validate_yaml

FIXTURES_DIR = Path(__file__).parent / "fixtures"
KNOWN_BA_ID = "BA-10231"
TABLE = "workspace.analytics.customers"
UC_LIVE_TESTS_ENABLED = os.environ.get("UC_LIVE_TESTS") == "1"


def _fully_reviewed_contract(client: UCClient, full_name: str = TABLE) -> Contract:
    """A harvested-then-fully-reviewed contract for `full_name`: every human-
    declared dataset field carries a real value (no placeholders), every
    judgment field is an accepted (`ai_proposed=False`) `Proposed` value, and the
    column list matches the catalogue exactly (no drift). The clean baseline
    every failure-mode test below mutates one thing away from.
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


def _problems_with_prefix(problems, prefix: str):
    return [problem for problem in problems if problem.startswith(prefix)]


# ---- happy path -----------------------------------------------------------------


def test_validate_passes_a_fully_reviewed_drift_free_contract():
    client = FakeUCClient()
    contract = _fully_reviewed_contract(client)

    result = validate(contract, client)

    assert result.ok is True
    assert bool(result) is True
    assert result.problems == []


# ---- unreviewed AI-proposed markers (SC-001-03) ----------------------------------


@pytest.mark.scenario("SC-001-03")
def test_validate_names_the_specific_unreviewed_field():
    client = FakeUCClient()
    contract = _fully_reviewed_contract(client)
    unreviewed_columns = [
        column.model_copy(update={"sensitivity": Proposed.proposed(Sensitivity.CONFIDENTIAL)})
        if column.name == "email"
        else column
        for column in contract.columns
    ]
    contract = contract.model_copy(update={"columns": unreviewed_columns})
    assert contract.has_unreviewed_fields is True
    expected_path = contract.unreviewed_field_paths[0]

    result = validate(contract, client)

    assert result.ok is False
    unreviewed_problems = _problems_with_prefix(result.problems, "unreviewed:")
    assert len(unreviewed_problems) == 1
    assert expected_path in unreviewed_problems[0]
    # Isolated: this mutation alone must not also trip drift or placeholder checks.
    assert _problems_with_prefix(result.problems, "drift:") == []
    assert _problems_with_prefix(result.problems, "placeholder:") == []


# ---- placeholder sentinels (carried-forward finding from harvest.py) ------------


def test_validate_names_every_placeholder_field_on_an_unfilled_skeleton():
    """A freshly harvested skeleton (no caller-supplied dataset overrides) has no
    `Proposed` markers at all -- judgment fields are `None`, not AI-proposed --
    so this isolates the placeholder-sentinel check from the unreviewed-marker
    check by construction, proving the two are genuinely separate."""
    client = FakeUCClient()
    contract = harvest(TABLE, client, KNOWN_BA_ID)  # no overrides: all four placeholders apply
    assert contract.has_unreviewed_fields is False  # confirms the isolation

    result = validate(contract, client)

    assert result.ok is False
    placeholder_problems = _problems_with_prefix(result.problems, "placeholder:")
    assert len(placeholder_problems) == 4
    joined = " ".join(placeholder_problems)
    assert "dataset.description" in joined
    assert "dataset.refresh.cadence" in joined
    assert "dataset.retention_days" in joined
    assert "dataset.certification" in joined
    # Isolated: no drift (just harvested, matches the catalogue) and no
    # unreviewed markers (confirmed above) alongside the placeholder failures.
    assert _problems_with_prefix(result.problems, "drift:") == []
    assert _problems_with_prefix(result.problems, "unreviewed:") == []


def test_validate_placeholder_check_is_separate_from_the_unreviewed_marker_check():
    """A contract with zero unreviewed markers can still fail validation purely
    on placeholder grounds -- the two checks are independent, not two names for
    the same failure."""
    client = FakeUCClient()
    contract = harvest(TABLE, client, KNOWN_BA_ID)

    result = validate(contract, client)

    assert contract.has_unreviewed_fields is False
    assert result.ok is False
    assert any(problem.startswith("placeholder:") for problem in result.problems)


# ---- drift (SC-001-02) -----------------------------------------------------------


@pytest.mark.scenario("SC-001-02")
def test_validate_names_added_removed_and_retyped_columns_on_drift():
    client = FakeUCClient()
    contract = _fully_reviewed_contract(client)

    columns = [column for column in contract.columns if column.name != "region"]  # removed from contract
    columns = [
        column.model_copy(update={"data_type": "string_but_wrong"}) if column.name == "email" else column
        for column in columns
    ]  # retyped in the contract, no longer matches the catalogue
    columns.append(
        Column(name="loyalty_tier", data_type="string", nullable=True, partition_key=False)
    )  # exists in the contract, not in the catalogue
    contract = contract.model_copy(update={"columns": columns})

    result = validate(contract, client)

    assert result.ok is False
    drift_problems = _problems_with_prefix(result.problems, "drift:")
    assert len(drift_problems) == 3
    joined = " ".join(drift_problems)
    assert "'region'" in joined and "missing from the contract" in joined
    assert "'loyalty_tier'" in joined and "no longer exists in the catalogue" in joined
    assert "'email'" in joined and "has changed" in joined
    # Isolated: everything else about this contract is still fully reviewed.
    assert _problems_with_prefix(result.problems, "unreviewed:") == []
    assert _problems_with_prefix(result.problems, "placeholder:") == []


# ---- multiple simultaneous failures ----------------------------------------------


@pytest.mark.scenario("SC-001-02")
@pytest.mark.scenario("SC-001-03")
def test_validate_collects_every_failure_from_every_check_not_just_the_first():
    client = FakeUCClient()
    contract = harvest(TABLE, client, KNOWN_BA_ID)  # 4 placeholder problems, no drift, no unreviewed yet

    columns = [column for column in contract.columns if column.name != "region"]  # drift: removed
    columns = [
        column.model_copy(update={"description": Proposed.proposed("An email address.")})
        if column.name == "email"
        else column
        for column in columns
    ]  # unreviewed: newly proposed, not accepted
    contract = contract.model_copy(update={"columns": columns})

    result = validate(contract, client)

    assert result.ok is False
    assert len(_problems_with_prefix(result.problems, "placeholder:")) == 4
    assert len(_problems_with_prefix(result.problems, "drift:")) == 1
    assert len(_problems_with_prefix(result.problems, "unreviewed:")) == 1
    # All four checks ran and reported, not just whichever failed first.
    assert len(result.problems) == 6


# ---- validate_yaml: the not-yet-validated entry point ----------------------------


def test_validate_yaml_delegates_to_validate_for_a_well_formed_contract(tmp_path):
    client = FakeUCClient()
    contract = _fully_reviewed_contract(client)
    contract_path = tmp_path / "workspace.analytics.customers.yaml"
    contract.to_yaml(contract_path)

    result = validate_yaml(contract_path, client)

    assert result.ok is True
    assert result.problems == []


def test_validate_yaml_reports_schema_well_formedness_failures_without_raising(tmp_path):
    """A file that does not even parse as a legal `Contract` (here: missing the
    required `dataset` section) comes back as a failed `ValidationResult`, not a
    raised `pydantic.ValidationError` -- so a CI caller can treat every failure
    mode the same way."""
    malformed_path = tmp_path / "not_a_contract.yaml"
    malformed_path.write_text("version: 1\n")  # no `dataset` key at all

    result = validate_yaml(malformed_path, FakeUCClient())

    assert result.ok is False
    assert len(result.problems) == 1
    assert "not well-formed" in result.problems[0]


# ---- live drift check (SC-001-02), against the real Free Edition workspace ------
#
# Needs network and the `ucmeta` OAuth profile, so it is marked `uc_live` and
# skipped unless `UC_LIVE_TESTS=1` is set -- the same opt-in convention
# `test_uc_client_contract.py` and `test_propose.py`'s `llm_live` test use.
#
# Deliberately does not run a real `ALTER TABLE` against the live table: that
# choreography (genuinely alter a live column, rerun harvest, show the drift) is
# reserved for the live demo/e2e phase (`tests/e2e/demo_scenario.py --live`).
# This test proves the *check* -- `validate()`'s drift comparison -- is correct
# against real `RealUCClient.get_table(...)` data, by harvesting a real table and
# then constructing, in memory only, a contract that no longer matches it.


@pytest.mark.uc_live
@pytest.mark.scenario("SC-001-02")
@pytest.mark.skipif(
    not UC_LIVE_TESTS_ENABLED,
    reason="set UC_LIVE_TESTS=1 to run this against the live Free Edition workspace",
)
def test_validate_detects_real_drift_against_the_live_workspace():
    client = RealUCClient()
    full_name = "workspace.analytics.orders"
    contract = _fully_reviewed_contract(client, full_name=full_name)

    columns = [column for column in contract.columns if column.name != "channel"]  # removed from the contract
    columns = [
        column.model_copy(update={"data_type": "string_but_wrong"}) if column.name == "amount" else column
        for column in columns
    ]  # retyped in the contract, no longer matches the live table
    columns.append(
        Column(name="not_a_real_column", data_type="string", nullable=True, partition_key=False)
    )  # exists in the contract, not on the live table
    contract = contract.model_copy(update={"columns": columns})

    result = validate(contract, client)

    assert result.ok is False
    drift_problems = _problems_with_prefix(result.problems, "drift:")
    assert len(drift_problems) == 3
    joined = " ".join(drift_problems)
    assert "'channel'" in joined and "missing from the contract" in joined
    assert "'not_a_real_column'" in joined and "no longer exists in the catalogue" in joined
    assert "'amount'" in joined and "has changed" in joined

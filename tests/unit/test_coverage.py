"""Happy-path tests for `coverage.py`: fill-rate math is correct against a small
set of fixture contracts (some fully covered, one missing sensitivity, one still
carrying harvest's placeholder description, one whose table has no DQ rules
attached), the certification-tier-vs-evidence check correctly flags an unsupported
gold/silver claim and correctly clears a supported one, and the outcome measure is
always present and always labeled simulated.

Adversarial and boundary cases (a contracts/ directory with a malformed contract
file, a `dq_results` list naming the wrong dataset, a coverage run over a contract
whose business-application id is unregistered) belong to the adversary persona --
see `test_validate.py`'s module docstring for the same scoping note this codebase
already uses. `_team_for`'s unknown-owner fallback is exercised only implicitly
here (every fixture contract below uses a real, registered `business_application_id`).

Runs entirely offline: `FakeUCClient`'s default fixture for the DQ-evaluation
tests, no live workspace needed.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from uc_metadata import harvest
from uc_metadata.coverage import (
    CoverageReport,
    compute_coverage,
    compute_coverage_for_directory,
    load_contracts,
    tier_is_supported_by_evidence,
)
from uc_metadata.dq_registry import evaluate_rules
from uc_metadata.fake_uc import FakeUCClient
from uc_metadata.models import (
    CertificationTier,
    Column,
    Contract,
    Dataset,
    OwnerPointer,
    Proposed,
    Qualifier,
    Refresh,
    Sensitivity,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
CUSTOMERS = "workspace.analytics.customers"
CAMPAIGNS = "workspace.marketing.campaigns"
ORDERS = "workspace.analytics.orders"


def _contract(
    full_name: str,
    business_application_id: str,
    *,
    description: str = "A real, human-written dataset description.",
    sensitivity: Optional[Sensitivity] = Sensitivity.INTERNAL,
    certification: CertificationTier = CertificationTier.BRONZE,
    columns: Optional[List[Column]] = None,
) -> Contract:
    """Build a self-contained fixture contract with no client/harvest needed --
    fast to vary one coverage dimension at a time for each test below."""
    catalog, schema, table = full_name.split(".")
    dataset = Dataset(
        qualifier=Qualifier(catalog=catalog, schema=schema, table=table),
        owner=OwnerPointer(business_application_id=business_application_id),
        refresh=Refresh(cadence="daily", sla_minutes=60),
        retention_days=365,
        certification=certification,
        description=description,
        sensitivity=Proposed.accepted(sensitivity) if sensitivity is not None else None,
    )
    return Contract(dataset=dataset, columns=columns or [])


# ---- fill-rate coverage math -----------------------------------------------------


def test_compute_coverage_fill_rate_math_across_a_mixed_fixture_set():
    fully_covered = _contract(CUSTOMERS, "BA-10231")  # customers: 2 DQ rules registered
    missing_sensitivity = _contract(CAMPAIGNS, "BA-20144", sensitivity=None)  # campaigns: 2 DQ rules registered
    missing_description = _contract(ORDERS, "BA-30587", description=harvest.PLACEHOLDER_DESCRIPTION)  # orders: 2 rules
    no_dq_rules = _contract("workspace.other.untracked_table", "BA-40092")  # no rules registered for this table

    report = compute_coverage([fully_covered, missing_sensitivity, missing_description, no_dq_rules])

    assert isinstance(report, CoverageReport)
    assert report.dataset_count == 4
    # Dataset.owner is a required model field: always present for any constructable Contract.
    assert report.fill_rate_by_dimension["owner"] == 1.0
    assert report.fill_rate_by_dimension["description"] == 0.75  # 3 of 4 real, 1 placeholder
    assert report.fill_rate_by_dimension["sensitivity"] == 0.75  # 3 of 4 set, 1 None
    assert report.fill_rate_by_dimension["dq_rules"] == 0.75  # 3 of 4 have >=1 rule attached
    # Only `fully_covered` clears all four dimensions at once.
    assert report.overall_fill_rate == 0.25
    fully_covered_entry = next(d for d in report.datasets if d.full_name == CUSTOMERS)
    assert fully_covered_entry.is_fully_covered is True
    missing_sensitivity_entry = next(d for d in report.datasets if d.full_name == CAMPAIGNS)
    assert missing_sensitivity_entry.is_fully_covered is False
    assert missing_sensitivity_entry.has_sensitivity is False


def test_compute_coverage_groups_fill_rate_by_team():
    fully_covered = _contract(CUSTOMERS, "BA-10231")  # -> Customer Analytics
    missing_sensitivity = _contract(CAMPAIGNS, "BA-20144", sensitivity=None)  # -> Marketing Growth

    report = compute_coverage([fully_covered, missing_sensitivity])

    by_team = {team.team: team for team in report.by_team}
    assert by_team["Customer Analytics"].dataset_count == 1
    assert by_team["Customer Analytics"].fill_rate == 1.0
    assert by_team["Marketing Growth"].dataset_count == 1
    assert by_team["Marketing Growth"].fill_rate == 0.0


def test_compute_coverage_over_zero_contracts_returns_zero_fill_rates_not_an_error():
    report = compute_coverage([])

    assert report.dataset_count == 0
    assert report.overall_fill_rate == 0.0
    assert report.fill_rate_by_dimension == {"owner": 0.0, "description": 0.0, "sensitivity": 0.0, "dq_rules": 0.0}
    assert report.by_team == []
    # Still never published without an outcome measure, even with zero datasets.
    assert len(report.outcome_measures) >= 1


def test_compute_coverage_column_description_fill_rate():
    described = Column(name="a", data_type="string", nullable=True, description=Proposed.accepted("a column."))
    undescribed = Column(name="b", data_type="string", nullable=True)
    contract = _contract("workspace.other.partial_columns", "BA-10231", columns=[described, undescribed])

    report = compute_coverage([contract])

    assert report.datasets[0].column_description_fill_rate == 0.5


def test_compute_coverage_column_description_fill_rate_is_1_with_no_columns():
    contract = _contract("workspace.other.no_columns", "BA-10231", columns=[])

    report = compute_coverage([contract])

    assert report.datasets[0].column_description_fill_rate == 1.0


# ---- certification tier vs. DQ evidence ------------------------------------------


def test_tier_is_supported_by_evidence_bronze_is_always_supported():
    contract = _contract(CUSTOMERS, "BA-10231", certification=CertificationTier.BRONZE)

    assert tier_is_supported_by_evidence(contract, []) is True


def test_tier_is_supported_by_evidence_silver_supported_when_every_attached_rule_passes():
    client = FakeUCClient()
    contract = _contract(CUSTOMERS, "BA-10231", certification=CertificationTier.SILVER)
    dq_results = evaluate_rules(CUSTOMERS, client)

    assert tier_is_supported_by_evidence(contract, dq_results) is True


def test_tier_is_supported_by_evidence_gold_unsupported_when_an_attached_rule_fails():
    client = FakeUCClient()
    contract = _contract(CAMPAIGNS, "BA-20144", certification=CertificationTier.GOLD)
    dq_results = evaluate_rules(CAMPAIGNS, client)  # both campaigns rules fail on the seeded fixture

    assert tier_is_supported_by_evidence(contract, dq_results) is False


def test_tier_is_supported_by_evidence_silver_unsupported_with_no_rules_attached():
    contract = _contract(CUSTOMERS, "BA-10231", certification=CertificationTier.SILVER)

    assert tier_is_supported_by_evidence(contract, []) is False


def test_compute_coverage_with_a_client_evaluates_certification_evidence_for_real():
    client = FakeUCClient()
    supported = _contract(CUSTOMERS, "BA-10231", certification=CertificationTier.SILVER)
    unsupported = _contract(CAMPAIGNS, "BA-20144", certification=CertificationTier.GOLD)

    report = compute_coverage([supported, unsupported], client=client)

    supported_entry = next(d for d in report.datasets if d.full_name == CUSTOMERS)
    unsupported_entry = next(d for d in report.datasets if d.full_name == CAMPAIGNS)
    assert supported_entry.certification_supported_by_evidence is True
    assert supported_entry.dq_rules_evaluated == 2
    assert supported_entry.dq_rules_passed == 2
    assert unsupported_entry.certification_supported_by_evidence is False
    assert unsupported_entry.dq_rules_evaluated == 2
    assert unsupported_entry.dq_rules_passed == 0


def test_compute_coverage_without_a_client_cannot_verify_silver_gold_evidence():
    contract = _contract(CUSTOMERS, "BA-10231", certification=CertificationTier.GOLD)

    report = compute_coverage([contract])  # no client supplied

    assert report.datasets[0].certification_supported_by_evidence is None
    assert report.datasets[0].dq_rules_evaluated == 0


def test_compute_coverage_without_a_client_bronze_still_reports_supported():
    contract = _contract(CUSTOMERS, "BA-10231", certification=CertificationTier.BRONZE)

    report = compute_coverage([contract])

    assert report.datasets[0].certification_supported_by_evidence is True


# ---- outcome measure: present and honestly labeled -------------------------------


def test_compute_coverage_always_includes_at_least_one_outcome_measure():
    report = compute_coverage([_contract(CUSTOMERS, "BA-10231")])

    assert len(report.outcome_measures) >= 1


def test_outcome_measure_is_named_and_labeled_simulated_never_presented_as_observed():
    report = compute_coverage([_contract(CUSTOMERS, "BA-10231")])

    measure = report.outcome_measures[0]
    assert measure.name == "time_to_first_query_days"
    assert measure.unit == "days"
    assert measure.value > 0
    assert measure.simulated is True
    assert "simulated" in measure.caveat.lower()
    assert "no real consumption telemetry" in measure.caveat.lower()


# ---- JSON-friendly report shape (a later dashboard phase renders this) ----------


def test_coverage_report_serializes_to_json_friendly_dict():
    report = compute_coverage([_contract(CUSTOMERS, "BA-10231")])

    dumped = report.model_dump(mode="json")

    assert dumped["dataset_count"] == 1
    assert isinstance(dumped["generated_at"], str)  # datetime serialized, not a raw object
    assert dumped["outcome_measures"][0]["simulated"] is True


# ---- loading contracts from a directory ------------------------------------------


def test_load_contracts_loads_every_contract_yaml_under_a_directory():
    contracts = load_contracts(FIXTURES_DIR)

    assert len(contracts) == 3  # valid_contract.yaml, contract_v1_backcompat.yaml, contract_with_unreviewed_fields.yaml
    assert all(isinstance(contract, Contract) for contract in contracts)


def test_load_contracts_returns_empty_list_for_a_directory_that_does_not_exist_yet(tmp_path):
    """contracts/ ships no real files until a later phase (this phase's own
    scope note) -- loading from a not-yet-populated directory is a valid state,
    not an error."""
    assert load_contracts(tmp_path / "contracts") == []


def test_load_contracts_skips_schema_and_template_files(tmp_path):
    contracts_dir = tmp_path / "contracts"
    team_dir = contracts_dir / "analytics"
    team_dir.mkdir(parents=True)
    schema_dir = contracts_dir / "_schema"
    schema_dir.mkdir(parents=True)

    real_contract = Contract.from_yaml(FIXTURES_DIR / "valid_contract.yaml")
    real_contract.to_yaml(team_dir / "orders.yaml")
    (contracts_dir / "_template.yaml").write_text((FIXTURES_DIR / "valid_contract.yaml").read_text())
    (schema_dir / "contract.schema.json").write_text("{}")

    contracts = load_contracts(contracts_dir)

    assert len(contracts) == 1
    assert contracts[0].dataset.qualifier.full_name == real_contract.dataset.qualifier.full_name


def test_compute_coverage_for_directory_chains_load_and_compute():
    report = compute_coverage_for_directory(FIXTURES_DIR)

    assert report.dataset_count == 3

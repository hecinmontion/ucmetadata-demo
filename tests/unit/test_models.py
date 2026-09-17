"""Happy-path tests for the contract model foundation (src/uc_metadata/models.py).

Adversarial and boundary cases (malformed YAML, illegal enum values, a genuinely
breaking schema change, etc.) belong to the adversary persona, not here. These tests
confirm the model does what it was designed to do: round-trip a contract losslessly,
answer "is anything still unreviewed" cheaply, validate enums, and keep loading an
old contract once the schema has more optional fields than that contract used.

Spec binding: F-PLATFORM-001's scenarios (SC-001-01/02/03) exercise the full
harvest -> propose -> review -> apply loop, which this phase underpins but does not
itself implement. `test_unreviewed_field_paths_names_the_specific_fields` is marked
against SC-001-03 because it proves the exact mechanism that scenario's refusal
depends on (the marker is representable and queryable); the refusal behaviour itself
belongs to validate.py/apply.py in a later phase. The remaining tests are foundational
model correctness with no single scenario ID of their own.
"""

from pathlib import Path

import pytest
import yaml

from uc_metadata.models import (
    CertificationTier,
    Column,
    Contract,
    Proposed,
    Sensitivity,
    validate_against_json_schema,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_contract_round_trips_yaml_to_pydantic_to_yaml_losslessly(tmp_path):
    """YAML -> Contract -> YAML -> Contract yields two equal, fully-reviewed contracts."""
    original = Contract.from_yaml(FIXTURES_DIR / "valid_contract.yaml")

    written_path = tmp_path / "roundtrip.yaml"
    original.to_yaml(written_path)
    reloaded = Contract.from_yaml(written_path)

    assert reloaded == original
    assert reloaded.dataset.qualifier.full_name == "workspace.sales.orders"
    assert reloaded.columns[0].name == "order_id"
    assert reloaded.has_unreviewed_fields is False
    assert reloaded.unreviewed_field_paths == []


def test_round_trip_written_yaml_uses_producer_facing_field_names(tmp_path):
    """to_yaml() writes `schema:`, not the Python attribute name `schema_name:`."""
    contract = Contract.from_yaml(FIXTURES_DIR / "valid_contract.yaml")

    written_path = tmp_path / "roundtrip.yaml"
    contract.to_yaml(written_path)
    raw = yaml.safe_load(written_path.read_text())

    assert raw["dataset"]["qualifier"]["schema"] == "sales"
    assert "schema_name" not in raw["dataset"]["qualifier"]


@pytest.mark.scenario("SC-001-03")
def test_unreviewed_field_paths_names_the_specific_fields():
    """A contract with two AI-proposed fields reports exactly those two paths.

    SC-001-03: "the checks fail, name the specific fields that remain unreviewed" —
    this is the query validate.py will call to do that naming.
    """
    contract = Contract.from_yaml(FIXTURES_DIR / "contract_with_unreviewed_fields.yaml")

    assert contract.has_unreviewed_fields is True
    assert contract.unreviewed_field_paths == [
        "dataset.sensitivity",
        "columns[1].sensitivity",
    ]


def test_reviewing_a_field_clears_it_from_the_unreviewed_list():
    """Flipping ai_proposed to False on the one remaining field empties the list."""
    contract = Contract.from_yaml(FIXTURES_DIR / "contract_with_unreviewed_fields.yaml")
    assert contract.has_unreviewed_fields is True

    contract.dataset.sensitivity.ai_proposed = False
    contract.columns[1].sensitivity.ai_proposed = False

    assert contract.has_unreviewed_fields is False
    assert contract.unreviewed_field_paths == []


def test_certification_and_sensitivity_enums_validate():
    """Only the documented enum values are accepted; the parsed value is a real enum."""
    contract = Contract.from_yaml(FIXTURES_DIR / "valid_contract.yaml")

    assert contract.dataset.certification is CertificationTier.SILVER
    assert contract.dataset.sensitivity.value is Sensitivity.INTERNAL
    assert contract.columns[1].sensitivity.value is Sensitivity.CONFIDENTIAL


def test_proposed_helper_constructors_set_the_marker_correctly():
    """Proposed.proposed() marks unreviewed; Proposed.accepted() marks reviewed."""
    drafted = Proposed[str].proposed("a guess", note="ambiguous name")
    human_authored = Proposed[str].accepted("a certainty")

    assert drafted.ai_proposed is True
    assert drafted.note == "ambiguous name"
    assert human_authored.ai_proposed is False
    assert human_authored.note is None


def test_backwards_compatibility_v1_skeleton_contract_still_loads():
    """A minimal, freshly-harvested v1 contract (no judgment fields filled in at all)
    still loads under the current model. This fixture is the backwards-compatibility
    canary described in its own file header: it must keep loading once a v2 schema
    exists, so today's "optional" design for every judgment field is what lets an old,
    sparse v1 document keep validating rather than tripping a newly-required field.
    """
    contract = Contract.from_yaml(FIXTURES_DIR / "contract_v1_backcompat.yaml")

    assert contract.version == 1
    assert contract.dataset.sensitivity is None
    assert len(contract.columns) == 2

    order_id, customer_email = contract.columns
    assert isinstance(order_id, Column)
    assert order_id.description is None
    assert order_id.pii is None
    assert order_id.tags == []
    assert customer_email.nullable is True

    # A skeleton contract has nothing to review yet -- absence, not an unreviewed
    # marker, is how "left blank" (Behaviour section) is represented.
    assert contract.has_unreviewed_fields is False


def test_valid_contract_fixture_also_satisfies_the_json_schema():
    """Cross-check: the same fixture that validates under Pydantic also validates
    under contracts/_schema/contract.schema.json, so the two definitions of the
    contract shape stay in sync.
    """
    raw = yaml.safe_load((FIXTURES_DIR / "valid_contract.yaml").read_text())

    validate_against_json_schema(raw)  # raises on failure

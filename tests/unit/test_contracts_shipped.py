"""Happy-path tests for the three contracts shipped under `contracts/` (spec:
`contracts/` build verdict -- "2-3 contracts, one deliberately messy ... with
columns still undescribed").

These tests confirm each shipped file is what it claims to be, not just that it
parses: `customers.yaml` and `campaigns.yaml` are fully reviewed and pass
`validate()`; `orders.yaml` is genuinely pre-review and `validate()` fails
against it, naming the placeholder/unreviewed problems that prove it -- a
polished file dressed up as unfinished would pass here by accident, which is
exactly what this test guards against.

Also mechanically backs the honesty constraint this phase was built under: no
shipped contract may contain `ai_proposed: true` anywhere, because no AI drafter
was ever run against any of them (see README "What's mocked" and
`contracts/analytics/orders.yaml`'s own header for the still-open TODO to run
`ucmeta propose` for real before the interview).

Runs entirely against `fake_uc.FakeUCClient`'s default fixture -- its three
fixture tables mirror the live workspace's schemas exactly (same names, types,
nullability), so `validate()`'s drift check behaves identically here and
offline as it did when these files were authored against the real workspace.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from uc_metadata.fake_uc import FakeUCClient
from uc_metadata.models import Contract
from uc_metadata.validate import validate

CONTRACTS_DIR = Path(__file__).resolve().parents[2] / "contracts"

CUSTOMERS_PATH = CONTRACTS_DIR / "analytics" / "customers.yaml"
CAMPAIGNS_PATH = CONTRACTS_DIR / "marketing" / "campaigns.yaml"
ORDERS_PATH = CONTRACTS_DIR / "analytics" / "orders.yaml"

ALL_SHIPPED_CONTRACT_PATHS = [CUSTOMERS_PATH, CAMPAIGNS_PATH, ORDERS_PATH]


# ---- parsing and qualifiers -----------------------------------------------------


@pytest.mark.scenario("SC-001-01")
def test_customers_contract_parses_and_targets_the_right_table():
    contract = Contract.from_yaml(CUSTOMERS_PATH)

    assert contract.dataset.qualifier.full_name == "workspace.analytics.customers"
    assert contract.dataset.owner.business_application_id == "BA-10231"


def test_campaigns_contract_parses_and_targets_the_right_table():
    contract = Contract.from_yaml(CAMPAIGNS_PATH)

    assert contract.dataset.qualifier.full_name == "workspace.marketing.campaigns"
    assert contract.dataset.owner.business_application_id == "BA-20144"


def test_orders_contract_parses_and_targets_the_right_table():
    contract = Contract.from_yaml(ORDERS_PATH)

    assert contract.dataset.qualifier.full_name == "workspace.analytics.orders"
    assert contract.dataset.owner.business_application_id == "BA-30587"


# ---- validate(): the happy-path contracts pass -----------------------------------


@pytest.mark.scenario("SC-001-01")
def test_customers_contract_passes_validate():
    client = FakeUCClient()
    contract = Contract.from_yaml(CUSTOMERS_PATH)

    result = validate(contract, client)

    assert result.ok, result.problems


def test_campaigns_contract_passes_validate():
    """`campaigns.yaml` is the well-covered-but-quality-red adversarial demo:
    it passes validate() (metadata coverage/review is complete) even though
    its DQ rules fail -- coverage measures fill, not correctness, and that gap
    is proven in `tests/unit/test_dq_registry.py`, not re-proven here."""
    client = FakeUCClient()
    contract = Contract.from_yaml(CAMPAIGNS_PATH)

    result = validate(contract, client)

    assert result.ok, result.problems


# ---- validate(): the grandfathered contract genuinely fails ---------------------


def test_orders_contract_fails_validate_as_genuinely_pre_review():
    """`orders.yaml` is deliberately grandfathered and unreviewed -- this proves
    it, rather than asserting it in prose. The specific placeholder problems
    named are what distinguish "never touched since harvest" from "a human
    reviewed this and it still doesn't validate"."""
    client = FakeUCClient()
    contract = Contract.from_yaml(ORDERS_PATH)

    result = validate(contract, client)

    assert not result.ok
    joined_problems = " ".join(result.problems)
    assert "placeholder: dataset.description" in joined_problems
    assert "placeholder: dataset.refresh.cadence" in joined_problems
    assert "placeholder: dataset.retention_days" in joined_problems
    assert "placeholder: dataset.certification" in joined_problems


def test_orders_contract_has_no_reviewed_judgment_fields():
    """Every column judgment field on `orders.yaml` is still `None` -- harvested
    and never touched, not merely `ai_proposed: true` somewhere."""
    contract = Contract.from_yaml(ORDERS_PATH)

    for column in contract.columns:
        assert column.description is None
        assert column.business_term is None
        assert column.pii is None
        assert column.sensitivity is None
    assert contract.dataset.sensitivity is None


# ---- honesty constraint: no shipped contract was AI-drafted ---------------------


@pytest.mark.parametrize("path", ALL_SHIPPED_CONTRACT_PATHS, ids=lambda p: p.name)
def test_shipped_contract_contains_no_ai_proposed_content(path: Path):
    """Mechanical backstop for this phase's honesty constraint: no field in any
    shipped contract may carry `ai_proposed: true`, because no AI drafter was
    ever run against any of them (no `ANTHROPIC_API_KEY` was available when
    these were authored -- see README "What's mocked"). Checked both on the
    raw YAML text and on the parsed model, so a stray `ai_proposed: true`
    cannot hide behind a field `Contract` doesn't happen to walk.
    """
    raw_text = path.read_text()
    assert "ai_proposed: true" not in raw_text

    contract = Contract.from_yaml(path)
    assert contract.unreviewed_field_paths == []

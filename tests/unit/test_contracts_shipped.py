"""Happy-path tests for the three contracts shipped under `contracts/` (spec:
`contracts/` build verdict -- "2-3 contracts, one deliberately messy ... with
columns still undescribed").

These tests confirm each shipped file is what it claims to be, not just that it
parses: `customers.yaml` is fully reviewed and passes `validate()` outright;
`campaigns.yaml` is equally fully reviewed (no unreviewed markers, no
placeholders, no drift) but fails `validate()` for exactly one reason -- the
certification-vs-evidence check, wired into `validate()` once
`dq_registry.py`/`coverage.py` existed to support it, correctly catches its
deliberate `silver` claim against two genuinely failing DQ rules (see
`campaigns.yaml`'s own header comment). `orders.yaml` is genuinely pre-review
and `validate()` fails against it for a different reason entirely, naming the
placeholder/unreviewed problems that prove it -- a polished file dressed up as
unfinished would pass here by accident, which is exactly what this test guards
against.

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
from uc_metadata.validate import validate, validate_yaml

CONTRACTS_DIR = Path(__file__).resolve().parents[2] / "contracts"

CUSTOMERS_PATH = CONTRACTS_DIR / "analytics" / "customers.yaml"
CAMPAIGNS_PATH = CONTRACTS_DIR / "marketing" / "campaigns.yaml"
ORDERS_PATH = CONTRACTS_DIR / "analytics" / "orders.yaml"

ALL_SHIPPED_CONTRACT_PATHS = [CUSTOMERS_PATH, CAMPAIGNS_PATH, ORDERS_PATH]

# Every real contract file that ships in this repo, discovered by glob rather than
# hand-listed: `_template.yaml` is the starter shape, not a real dataset's contract,
# and `_schema/` holds the JSON Schema those contracts validate against, not a
# contract itself -- both carved out the same way `change_classes.yaml` routes them
# to the "schema" change class in `test_change_routing.py`.
ALL_CONTRACT_PATHS = sorted(
    path
    for path in CONTRACTS_DIR.rglob("*.yaml")
    if path.name != "_template.yaml" and "_schema" not in path.parts
)


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


# ---- validate(): the happy-path contract passes outright -------------------------


@pytest.mark.scenario("SC-001-01")
def test_customers_contract_passes_validate():
    client = FakeUCClient()
    contract = Contract.from_yaml(CUSTOMERS_PATH)

    result = validate(contract, client)

    assert result.ok, result.problems


# ---- validate(): the adversarial demo contract fails, for exactly one reason -----


def test_campaigns_contract_fails_validate_solely_on_certification_evidence():
    """`campaigns.yaml` is the well-covered-but-quality-red adversarial demo:
    metadata coverage and review are complete (no drift, no unreviewed marker,
    no placeholder), but its `silver` claim is not backed by its DQ evidence --
    two attached rules genuinely fail against its seeded rows (a negative
    budget, an `end_date` before `start_date`). `validate()`'s
    certification-vs-evidence check catches exactly that, and nothing else
    about this contract is wrong -- the DQ failures themselves are proven in
    `tests/unit/test_dq_registry.py`, not re-proven here."""
    client = FakeUCClient()
    contract = Contract.from_yaml(CAMPAIGNS_PATH)

    result = validate(contract, client)

    assert result.ok is False
    assert len(result.problems) == 1
    assert result.problems[0].startswith("certification:")
    assert "silver" in result.problems[0]


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


# ---- safety net: every shipped contract's table resolves against FakeUCClient ---


@pytest.mark.parametrize("path", ALL_CONTRACT_PATHS, ids=lambda p: str(p.relative_to(CONTRACTS_DIR)))
def test_every_shipped_contract_resolves_against_fake_uc_client(path: Path):
    """No spec scenario names this directly (ADR-004's "the fake must not drift
    from real Unity Catalog semantics" is the source, not a Scenario), so this
    carries no `@pytest.mark.scenario`, following `test_change_routing.py`'s
    precedent for ADR-derived, non-scenario-bound assertions.

    Regression test for the exact failure PR #12's `validate.yml` run hit:
    `contracts/demo/pipeline_runs.yaml` and `contracts/demo/data_quality_checks.yaml`
    were the first contracts ever written for a table outside `FakeUCClient`'s
    three-table fixture set (`data_platform_demo.demo`, a catalog provisioned live
    by F-PLATFORM-004/005, not by `scripts/seed_demo_data.sql`) -- `validate.yml`
    is deliberately, permanently credential-free (F-PLATFORM-001's fork-safety
    guarantee: it never passes `--live`), so a contract whose table the fixture
    doesn't know about fails CI with an unhandled `UCTableNotFoundError`
    (surfaced via `_certification_evidence_problems` -> `sample_rows`) rather
    than a readable `FAIL` verdict. This walks every real contract under
    `contracts/` and asserts `validate_yaml` returns a verdict -- pass or fail on
    its merits -- without raising, so the next new table is caught here, fast
    and offline, instead of on a real PR's CI run against a real workspace.
    """
    client = FakeUCClient()

    result = validate_yaml(path, client)

    assert isinstance(result.ok, bool)

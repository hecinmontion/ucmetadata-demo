"""Happy-path tests for `propose.py`, against `llm_fixture_transport`'s
fixture-backed replay client -- offline, deterministic, and (today) built
against hand-authored placeholder fixtures because this environment has no
`ANTHROPIC_API_KEY` (see `tests/fixtures/llm/README.md`). One `llm_live`-marked
test at the bottom is the real recording pass, correctly written and ready to
run once a key is available, but skipped by default.

Covers SC-001-01's "AI proposes the missing fields" step: harvest, then
propose, populates every blank judgment field as an AI-proposed, unreviewed
`Proposed` value, with a valid glossary-backed business term where one is
proposed at all.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from llm_fixture_transport import LLM_LIVE_TESTS_ENABLED, build_llm_client
from uc_metadata.fake_uc import FakeUCClient
from uc_metadata.glossary import load_glossary
from uc_metadata.harvest import harvest
from uc_metadata.models import Sensitivity
from uc_metadata.propose import propose

CUSTOMERS_FIXTURE = "customers_propose__PLACEHOLDER_NOT_RECORDED"
CAMPAIGNS_FIXTURE = "campaigns_propose__PLACEHOLDER_NOT_RECORDED"
ORDERS_FIXTURE = "orders_propose__PLACEHOLDER_NOT_RECORDED"


def _harvested_contract(table: str, business_application_id: str):
    return harvest(table, FakeUCClient(), business_application_id)


@pytest.mark.scenario("SC-001-01")
def test_propose_populates_every_blank_column_field_as_ai_proposed():
    """Every judgment field on every column comes back wrapped as `Proposed`
    with `ai_proposed=True`, and harvested facts (name/data_type/nullable) are
    left untouched."""
    contract = _harvested_contract("workspace.analytics.customers", "BA-10231")
    llm_client = build_llm_client(CUSTOMERS_FIXTURE)

    result = propose(contract, FakeUCClient(), llm_client=llm_client)

    assert len(result.contract.columns) == len(contract.columns)
    for original, updated in zip(contract.columns, result.contract.columns):
        assert updated.name == original.name
        assert updated.data_type == original.data_type
        assert updated.nullable == original.nullable

        assert updated.description is not None
        assert updated.description.ai_proposed is True
        assert updated.description.value  # non-empty string

        assert updated.pii is not None
        assert updated.pii.ai_proposed is True

        assert updated.sensitivity is not None
        assert updated.sensitivity.ai_proposed is True
        assert isinstance(updated.sensitivity.value, Sensitivity)


@pytest.mark.scenario("SC-001-01")
def test_propose_sets_dataset_sensitivity_as_ai_proposed():
    """The dataset-level sensitivity roll-up is also wrapped as an AI-proposed,
    unreviewed value -- SC-001-01: 'proposes ... business-term links and
    sensitivity'."""
    contract = _harvested_contract("workspace.analytics.customers", "BA-10231")
    llm_client = build_llm_client(CUSTOMERS_FIXTURE)

    result = propose(contract, FakeUCClient(), llm_client=llm_client)

    dataset_sensitivity = result.contract.dataset.sensitivity
    assert dataset_sensitivity is not None
    assert dataset_sensitivity.ai_proposed is True
    assert isinstance(dataset_sensitivity.value, Sensitivity)


@pytest.mark.scenario("SC-001-01")
def test_customers_dataset_with_a_pii_column_is_floored_to_at_least_confidential():
    """Behaviour: 'a dataset with a PII column is at least confidential' --
    exercised here against the real customers fixture, where email/first_name/
    last_name are all proposed `pii=True`."""
    contract = _harvested_contract("workspace.analytics.customers", "BA-10231")
    llm_client = build_llm_client(CUSTOMERS_FIXTURE)

    result = propose(contract, FakeUCClient(), llm_client=llm_client)

    pii_columns = [c for c in result.contract.columns if c.pii.value is True]
    assert pii_columns  # the fixture proposes at least one PII column
    assert result.contract.dataset.sensitivity.value in (
        Sensitivity.CONFIDENTIAL,
        Sensitivity.STRICTLY_CONFIDENTIAL,
    )


@pytest.mark.scenario("SC-001-01")
@pytest.mark.parametrize(
    "table,business_application_id,fixture_name",
    [
        ("workspace.analytics.customers", "BA-10231", CUSTOMERS_FIXTURE),
        ("workspace.marketing.campaigns", "BA-20144", CAMPAIGNS_FIXTURE),
        ("workspace.analytics.orders", "BA-30587", ORDERS_FIXTURE),
    ],
)
def test_proposed_business_terms_only_ever_reference_real_glossary_keys(
    table, business_application_id, fixture_name
):
    """Data section: 'a proposed business_term link must resolve to a real
    glossary entry' -- never an invented one, on any of the three seeded
    tables."""
    glossary = load_glossary()
    contract = _harvested_contract(table, business_application_id)
    llm_client = build_llm_client(fixture_name)

    result = propose(contract, FakeUCClient(), llm_client=llm_client)

    for column in result.contract.columns:
        if column.business_term is None:
            continue  # "explicitly none if nothing fits" is a legal outcome
        assert column.business_term.value in glossary


@pytest.mark.scenario("SC-001-01")
def test_call_metrics_are_computed_and_non_negative():
    """Non-functional Requirements: 'its latency and cost are printed' -- and,
    per this module's `propose()` docstring, also returned to the caller."""
    contract = _harvested_contract("workspace.analytics.customers", "BA-10231")
    llm_client = build_llm_client(CUSTOMERS_FIXTURE)

    result = propose(contract, FakeUCClient(), llm_client=llm_client)

    assert result.metrics.model
    assert result.metrics.input_tokens > 0
    assert result.metrics.output_tokens > 0
    assert result.metrics.cost_usd >= 0
    assert result.metrics.latency_seconds >= 0


@pytest.mark.scenario("SC-001-01")
def test_pii_looking_sample_values_are_masked_before_being_sent():
    """Rules & Constraints: 'sensitive column values are never sent to the AI
    drafter unmasked.' Asserted against what the fake transport actually
    received, not against what it returned -- masking happens in `propose.py`
    before the request is ever built, so a masking bug would leak real customer
    data into the request even though the (fixture) response looks fine."""
    contract = _harvested_contract("workspace.analytics.customers", "BA-10231")
    captured_requests = []
    llm_client = build_llm_client(CUSTOMERS_FIXTURE, captured_requests=captured_requests)

    propose(contract, FakeUCClient(), llm_client=llm_client)

    assert len(captured_requests) == 1
    sent_body = captured_requests[0].content.decode("utf-8")

    # Real sample values for email/first_name/last_name (the PII-suspect
    # columns) must never appear in what was sent...
    assert "amara.diallo@example.com" not in sent_body
    assert "Amara" not in sent_body
    assert "Diallo" not in sent_body
    # ...while the masking marker, and a non-sensitive column's real values,
    # both do -- proving this is masking, not an empty/broken request.
    assert "MASKED" in sent_body
    assert "EMEA" in sent_body


@pytest.mark.scenario("SC-001-01")
def test_orders_state_column_is_flagged_ambiguous_via_note():
    """The `orders.state` column is deliberately ambiguous (order status vs. US
    state abbreviation; see `scripts/seed_demo_data.sql` and
    `glossary/terms.yaml`'s `order_status` entry). The hand-authored orders
    fixture demonstrates the drafter naming that ambiguity explicitly via
    `Proposed.note` rather than silently picking a reading -- this is what
    `propose.py`'s prompt is designed to elicit from a real model, and what
    this test proves the wiring actually surfaces to a reviewer once the
    drafter does say so."""
    contract = _harvested_contract("workspace.analytics.orders", "BA-30587")
    llm_client = build_llm_client(ORDERS_FIXTURE)

    result = propose(contract, FakeUCClient(), llm_client=llm_client)

    state_column = next(c for c in result.contract.columns if c.name == "state")
    assert state_column.description.note is not None
    assert "ambiguous" in state_column.description.note.lower()
    # Every other column in this fixture is unambiguous and carries no note.
    unambiguous_columns = [c for c in result.contract.columns if c.name != "state"]
    assert all(c.description.note is None for c in unambiguous_columns)


@pytest.mark.scenario("SC-001-01")
def test_repropose_leaves_already_reviewed_columns_untouched():
    """Precondition documented on `propose()`: a column that already carries a
    description (i.e. already proposed or reviewed) is left untouched by a
    second `propose()` call, so re-running propose on a partially-reviewed
    contract is safe."""
    contract = _harvested_contract("workspace.analytics.customers", "BA-10231")
    first_pass = propose(contract, FakeUCClient(), llm_client=build_llm_client(CUSTOMERS_FIXTURE))

    # Simulate a human reviewer accepting `region`'s proposal as-is.
    from uc_metadata.models import Proposed

    reviewed_region = next(c for c in first_pass.contract.columns if c.name == "region")
    reviewed_columns = [
        c.model_copy(update={"description": Proposed.accepted(c.description.value)})
        if c.name == "region"
        else c
        for c in first_pass.contract.columns
    ]
    partially_reviewed = first_pass.contract.model_copy(update={"columns": reviewed_columns})

    # A second propose() call should be a no-op: nothing is left blank to draft.
    second_pass = propose(partially_reviewed, FakeUCClient(), llm_client=build_llm_client(CUSTOMERS_FIXTURE))

    region_after = next(c for c in second_pass.contract.columns if c.name == "region")
    assert region_after.description.ai_proposed is False
    assert region_after.description.value == reviewed_region.description.value
    assert second_pass.metrics.input_tokens == 0  # no drafter call was made


# ---- audit persistence (Rules & Constraints: "every AI proposal is auditable") --


def test_propose_writes_an_audit_record_next_to_the_contract_when_given_a_path(tmp_path: Path):
    """Given `contract_path`, `propose()` writes `<name>.audit.json` right next
    to it, recording the model, a timestamp, and the column-level inputs sent
    -- names and masked sample values, never a raw PII value."""
    contract = _harvested_contract("workspace.analytics.customers", "BA-10231")
    llm_client = build_llm_client(CUSTOMERS_FIXTURE)
    contract_path = tmp_path / "customers.yaml"

    result = propose(contract, FakeUCClient(), llm_client=llm_client, contract_path=contract_path)

    audit_path = tmp_path / "customers.audit.json"
    assert audit_path.exists()
    audit = json.loads(audit_path.read_text())

    assert audit["dataset_full_name"] == "workspace.analytics.customers"
    assert audit["model"] == result.metrics.model
    assert audit["input_tokens"] == result.metrics.input_tokens
    assert audit["output_tokens"] == result.metrics.output_tokens
    assert audit["generated_at"]  # a real timestamp was recorded
    assert audit["system_prompt"]
    assert audit["user_prompt"]

    columns_by_name = {entry["column_name"]: entry for entry in audit["columns_proposed"]}
    assert set(columns_by_name) == {column.name for column in contract.columns}

    # Acceptance state is deliberately not recorded here -- see propose.py's
    # module docstring for the design choice (read live from the contract
    # instead of duplicating it here, where it could drift).
    for entry in audit["columns_proposed"]:
        assert "accepted" not in entry
        assert "ai_proposed" not in entry


def test_propose_audit_record_never_leaks_a_raw_value_for_a_pii_flagged_column(tmp_path: Path):
    """Same masking discipline the request itself already proves
    (`test_pii_looking_sample_values_are_masked_before_being_sent`), now
    asserted against what actually landed on disk in the audit record."""
    contract = _harvested_contract("workspace.analytics.customers", "BA-10231")
    llm_client = build_llm_client(CUSTOMERS_FIXTURE)
    contract_path = tmp_path / "customers.yaml"

    propose(contract, FakeUCClient(), llm_client=llm_client, contract_path=contract_path)

    audit = json.loads((tmp_path / "customers.audit.json").read_text())
    columns_by_name = {entry["column_name"]: entry for entry in audit["columns_proposed"]}

    for pii_column in ("email", "first_name", "last_name"):
        entry = columns_by_name[pii_column]
        assert entry["samples_masked"] is True
        assert entry["masked_sample_values"]
        assert all(value == "***MASKED***" for value in entry["masked_sample_values"])

    assert "amara.diallo@example.com" not in audit["user_prompt"]
    assert "Amara" not in audit["user_prompt"]
    assert "Diallo" not in audit["user_prompt"]

    # A non-sensitive column's real sample values are still recorded (this is
    # an audit of what was sent, not a second layer of redaction).
    region_entry = columns_by_name["region"]
    assert region_entry["samples_masked"] is False
    assert "EMEA" in region_entry["masked_sample_values"]


def test_propose_writes_no_audit_record_when_nothing_needs_proposing(tmp_path: Path):
    """No drafter call means nothing to audit -- `contract_path` is accepted
    but no file is written, the same "no call was made" posture `metrics`
    already takes for this case."""
    contract = _harvested_contract("workspace.analytics.customers", "BA-10231")
    first_pass = propose(contract, FakeUCClient(), llm_client=build_llm_client(CUSTOMERS_FIXTURE))
    contract_path = tmp_path / "customers.yaml"

    propose(first_pass.contract, FakeUCClient(), llm_client=build_llm_client(CUSTOMERS_FIXTURE), contract_path=contract_path)

    assert not (tmp_path / "customers.audit.json").exists()


def test_propose_does_not_write_an_audit_record_when_contract_path_is_omitted(tmp_path: Path):
    """The default, unchanged behaviour every pre-existing call site in this
    file relies on: omitting `contract_path` skips audit persistence entirely."""
    contract = _harvested_contract("workspace.analytics.customers", "BA-10231")
    llm_client = build_llm_client(CUSTOMERS_FIXTURE)

    propose(contract, FakeUCClient(), llm_client=llm_client)

    assert list(tmp_path.iterdir()) == []


@pytest.mark.llm_live
@pytest.mark.skipif(
    not (LLM_LIVE_TESTS_ENABLED and os.environ.get("ANTHROPIC_API_KEY")),
    reason="set LLM_LIVE_TESTS=1 and ANTHROPIC_API_KEY to record a real fixture against the live Anthropic API",
)
def test_propose_records_a_real_customers_fixture():
    """Not a fixture-backed assertion test: this *is* the recording pass. Running
    it with `LLM_LIVE_TESTS=1` and a real `ANTHROPIC_API_KEY` makes one real,
    billed Anthropic call and overwrites the customers placeholder fixture with
    the genuine recorded response (see `tests/fixtures/llm/README.md` for the
    full recording procedure, including the required manual rename step
    afterwards).
    """
    contract = _harvested_contract("workspace.analytics.customers", "BA-10231")
    llm_client = build_llm_client(CUSTOMERS_FIXTURE)

    result = propose(contract, FakeUCClient(), llm_client=llm_client)

    assert result.contract.dataset.sensitivity is not None
    assert result.metrics.input_tokens > 0
    assert result.metrics.output_tokens > 0

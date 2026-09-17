"""Happy-path tests for `harvest.py`, `owner_registry.py` and `glossary.py`.

Adversarial and boundary cases (a table that vanishes mid-harvest, a malformed
glossary file, a business-application id that is present but empty, etc.) belong
to the adversary persona, not here. These tests confirm each module does what it
was designed to do: harvest builds a skeleton with the right facts and blank
judgments, owner resolution works for a known id and fails clearly for an
unknown one, and the glossary loader returns the sample terms.

Harvest tests run against `fake_uc.FakeUCClient`'s default fixture, which mirrors
the three real tables `scripts/seed_demo_data.sql` seeds into the live workspace
(same names, same columns, same types) -- no separate fixture set invented here.

Spec binding: SC-001-01's "When the producer harvests the dataset" step is what
`test_harvest_*` exercises; the rest of that scenario (propose, review, apply)
belongs to later phases.
"""

from __future__ import annotations

import pytest

from uc_metadata.fake_uc import FakeUCClient
from uc_metadata.glossary import load_glossary
from uc_metadata.harvest import (
    PLACEHOLDER_CERTIFICATION,
    PLACEHOLDER_DESCRIPTION,
    PLACEHOLDER_RETENTION_DAYS,
    harvest,
)
from uc_metadata.models import CertificationTier, Refresh
from uc_metadata.owner_registry import Owner, UnknownBusinessApplicationError, resolve_owner

KNOWN_BA_ID = "BA-10231"


# ---- harvest ------------------------------------------------------------------


@pytest.mark.scenario("SC-001-01")
def test_harvest_customers_produces_skeleton_with_harvested_facts_and_blank_judgments():
    """`workspace.analytics.customers`'s skeleton has the right harvested column
    facts, in position order, and every judgment field left `None`."""
    client = FakeUCClient()

    contract = harvest("workspace.analytics.customers", client, KNOWN_BA_ID)

    assert contract.dataset.qualifier.catalog == "workspace"
    assert contract.dataset.qualifier.schema_name == "analytics"
    assert contract.dataset.qualifier.table == "customers"
    assert contract.dataset.qualifier.full_name == "workspace.analytics.customers"
    assert contract.dataset.owner.business_application_id == KNOWN_BA_ID
    assert contract.dataset.sensitivity is None

    column_names = [column.name for column in contract.columns]
    assert column_names == [
        "customer_id",
        "email",
        "first_name",
        "last_name",
        "region",
        "signup_date",
        "lifetime_value",
    ]
    lifetime_value = next(c for c in contract.columns if c.name == "lifetime_value")
    assert lifetime_value.data_type == "decimal(10,2)"
    assert lifetime_value.nullable is True
    assert lifetime_value.partition_key is False

    for column in contract.columns:
        assert column.description is None
        assert column.business_term is None
        assert column.pii is None
        assert column.sensitivity is None
        assert column.tags == []

    # Skeleton contracts have nothing AI-authored yet -- absence, not an
    # unreviewed marker, is how "left blank" is represented (mirrors
    # test_models.py's v1-backcompat skeleton assertion).
    assert contract.has_unreviewed_fields is False


@pytest.mark.scenario("SC-001-01")
def test_harvest_campaigns_produces_skeleton_with_harvested_facts():
    """`workspace.marketing.campaigns`'s skeleton reflects its own column shape,
    not `customers`'s -- guards against a hard-coded/copy-pasted assertion."""
    client = FakeUCClient()

    contract = harvest("workspace.marketing.campaigns", client, KNOWN_BA_ID)

    assert contract.dataset.qualifier.full_name == "workspace.marketing.campaigns"
    column_names = [column.name for column in contract.columns]
    assert column_names == ["campaign_id", "name", "channel", "budget", "start_date", "end_date", "active"]
    active = next(c for c in contract.columns if c.name == "active")
    assert active.data_type == "boolean"
    assert all(column.description is None for column in contract.columns)


@pytest.mark.scenario("SC-001-01")
def test_harvest_orders_produces_skeleton_with_harvested_facts():
    """`workspace.analytics.orders`'s skeleton reflects its own column shape,
    including the deliberately ambiguous `state` column (harvested as a plain
    fact -- disambiguating it is propose.py's job, not harvest's)."""
    client = FakeUCClient()

    contract = harvest("workspace.analytics.orders", client, KNOWN_BA_ID)

    assert contract.dataset.qualifier.full_name == "workspace.analytics.orders"
    column_names = [column.name for column in contract.columns]
    assert column_names == ["order_id", "customer_id", "state", "amount", "order_ts", "channel"]
    order_ts = next(c for c in contract.columns if c.name == "order_ts")
    assert order_ts.data_type == "timestamp"
    assert all(column.sensitivity is None for column in contract.columns)


def test_harvest_leaves_unsupplied_dataset_fields_as_unmistakable_placeholders():
    """When a caller supplies no overrides, the four human-declared dataset
    fields come back as the documented placeholders, not a guessed value."""
    client = FakeUCClient()

    contract = harvest("workspace.analytics.customers", client, KNOWN_BA_ID)

    assert contract.dataset.description == PLACEHOLDER_DESCRIPTION
    assert contract.dataset.description.startswith("TODO(human):")
    assert contract.dataset.retention_days == PLACEHOLDER_RETENTION_DAYS
    assert contract.dataset.certification == PLACEHOLDER_CERTIFICATION


def test_harvest_uses_caller_supplied_overrides_for_dataset_fields_when_given():
    """A caller who already knows the human-declared commitments can supply them
    directly, and harvest writes those through instead of the placeholders."""
    client = FakeUCClient()

    contract = harvest(
        "workspace.analytics.customers",
        client,
        KNOWN_BA_ID,
        description="Customer master records for the direct-to-consumer storefront.",
        refresh=Refresh(cadence="daily", sla_minutes=120),
        retention_days=730,
        certification=CertificationTier.SILVER,
    )

    assert contract.dataset.description == "Customer master records for the direct-to-consumer storefront."
    assert contract.dataset.refresh == Refresh(cadence="daily", sla_minutes=120)
    assert contract.dataset.retention_days == 730
    assert contract.dataset.certification is CertificationTier.SILVER


def test_harvest_fails_fast_on_an_unknown_business_application_id():
    """An unresolvable owner id fails harvest immediately, before a contract
    nothing could ever resolve gets built."""
    client = FakeUCClient()

    with pytest.raises(UnknownBusinessApplicationError):
        harvest("workspace.analytics.customers", client, "BA-does-not-exist")


# ---- owner_registry -------------------------------------------------------


def test_resolve_owner_returns_the_registered_owner_for_a_known_id():
    owner = resolve_owner(KNOWN_BA_ID)

    assert isinstance(owner, Owner)
    assert owner.team == "Customer Analytics"
    assert "@" in owner.solution_owner
    assert owner.contact_channel.startswith("#")


def test_resolve_owner_raises_a_clear_error_for_an_unknown_id():
    with pytest.raises(UnknownBusinessApplicationError, match="BA-does-not-exist"):
        resolve_owner("BA-does-not-exist")


# ---- glossary ---------------------------------------------------------------


def test_load_glossary_returns_a_non_empty_dict_of_the_sample_terms():
    terms = load_glossary()

    assert isinstance(terms, dict)
    assert len(terms) >= 8
    for expected_term in ("customer", "email", "lifetime_value", "campaign", "channel", "order"):
        assert expected_term in terms
        assert isinstance(terms[expected_term], str)
        assert terms[expected_term].strip() != ""

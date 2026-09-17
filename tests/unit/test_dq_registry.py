"""Happy-path tests for `dq_registry.py`: the registry loads the rules
`dq_registry.yaml` declares, a rule correctly passes against clean fixture data
and correctly catches the two violations `fake_uc.py`'s default fixture and the
live `campaigns` table were both seeded with on purpose, and the small predicate
interpreter evaluates the `IS [NOT] NULL` / comparison / `AND` grammar it claims
to support.

Adversarial and boundary cases (a malformed registry file, an unsupported
predicate clause, a table `sample_rows` cannot resolve) belong to the adversary
persona, not here -- see `test_validate.py`'s module docstring for the same
scoping note this codebase already uses.

Runs against `fake_uc.FakeUCClient`'s default fixture (no network); a separate
`uc_live` test at the bottom runs the same rules for real against the live
Free Edition workspace's seeded `campaigns` and `customers` tables.
"""

from __future__ import annotations

import os

import pytest

from uc_metadata.dq_registry import (
    DQRule,
    evaluate_rule,
    evaluate_rules,
    load_dq_registry,
    rules_for_table,
)
from uc_metadata.fake_uc import FakeUCClient
from uc_metadata.uc_client import RealUCClient

CUSTOMERS = "workspace.analytics.customers"
CAMPAIGNS = "workspace.marketing.campaigns"
ORDERS = "workspace.analytics.orders"
UC_LIVE_TESTS_ENABLED = os.environ.get("UC_LIVE_TESTS") == "1"


# ---- loading the registry --------------------------------------------------------


def test_load_dq_registry_loads_every_rule_declared_in_dq_registry_yaml():
    rules = load_dq_registry()

    assert len(rules) == 6
    assert all(isinstance(rule, DQRule) for rule in rules)
    ids = {rule.id for rule in rules}
    assert "campaigns-budget-non-negative" in ids
    assert "campaigns-end-date-not-before-start-date" in ids
    assert "customers-email-present" in ids
    assert "customers-lifetime-value-non-negative" in ids


def test_rules_for_table_filters_to_the_named_table_only():
    rules = load_dq_registry()

    campaigns_rules = rules_for_table(CAMPAIGNS, rules)

    assert {rule.id for rule in campaigns_rules} == {
        "campaigns-budget-non-negative",
        "campaigns-end-date-not-before-start-date",
    }
    assert all(rule.full_name == CAMPAIGNS for rule in campaigns_rules)


def test_rules_for_table_returns_empty_for_a_table_with_no_rules_registered():
    rules = load_dq_registry()

    assert rules_for_table("workspace.some_schema.untracked_table", rules) == []


# ---- evaluating a passing rule ----------------------------------------------------


def test_evaluate_rule_passes_cleanly_against_the_clean_customers_fixture():
    client = FakeUCClient()
    rules = load_dq_registry()
    lifetime_value_rule = next(r for r in rules if r.id == "customers-lifetime-value-non-negative")

    result = evaluate_rule(lifetime_value_rule, client)

    assert result.passed is True
    assert result.violation_count == 0
    assert result.rows_checked == 5  # fake_uc.py's default customers fixture: 5 seeded rows


def test_evaluate_rules_all_pass_for_the_clean_customers_table():
    client = FakeUCClient()

    results = evaluate_rules(CUSTOMERS, client)

    assert len(results) == 2  # email-present, lifetime-value-non-negative
    assert all(result.passed for result in results)
    assert all(result.violation_count == 0 for result in results)


# ---- evaluating a rule that catches the seeded campaigns violations --------------


def test_evaluate_rule_catches_the_seeded_negative_budget_violation():
    client = FakeUCClient()
    rules = load_dq_registry()
    budget_rule = next(r for r in rules if r.id == "campaigns-budget-non-negative")

    result = evaluate_rule(budget_rule, client)

    assert result.passed is False
    assert result.violation_count == 1  # campaign 5003, budget -500.00


def test_evaluate_rule_catches_the_seeded_end_before_start_violation():
    client = FakeUCClient()
    rules = load_dq_registry()
    date_rule = next(r for r in rules if r.id == "campaigns-end-date-not-before-start-date")

    result = evaluate_rule(date_rule, client)

    assert result.passed is False
    assert result.violation_count == 1  # campaign 5004, end_date before start_date


def test_evaluate_rules_reports_both_campaigns_violations_by_rule_id():
    client = FakeUCClient()

    results = evaluate_rules(CAMPAIGNS, client)

    failing = {result.rule_id: result for result in results if not result.passed}
    assert set(failing) == {"campaigns-budget-non-negative", "campaigns-end-date-not-before-start-date"}
    assert all(result.violation_count == 1 for result in failing.values())


def test_evaluate_rules_orders_rules_pass_against_the_uncontracted_but_clean_orders_data():
    """orders is deliberately messy/uncontracted (spec: two-speed rollout
    evidence dataset), but its DQ data itself was not seeded with violations --
    only campaigns and customers-vs-sensitivity get that treatment. Confirms
    the two `orders` rules pass cleanly on the fixture data as seeded."""
    client = FakeUCClient()

    results = evaluate_rules(ORDERS, client)

    assert len(results) == 2
    assert all(result.passed for result in results)


# ---- the predicate interpreter's grammar (IS [NOT] NULL, comparisons, AND) -------


def test_predicate_interpreter_evaluates_is_not_null():
    client = FakeUCClient()
    rule = DQRule(
        id="test-email-present",
        full_name=CUSTOMERS,
        description="test",
        predicate="email IS NOT NULL",
    )

    result = evaluate_rule(rule, client)

    assert result.passed is True


def test_predicate_interpreter_evaluates_a_two_column_comparison():
    client = FakeUCClient()
    rule = DQRule(
        id="test-end-after-start",
        full_name=CAMPAIGNS,
        description="test",
        predicate="end_date >= start_date",
    )

    result = evaluate_rule(rule, client)

    assert result.passed is False
    assert result.violation_count == 1


def test_predicate_interpreter_evaluates_an_and_joined_predicate():
    client = FakeUCClient()
    # Every campaigns row has a non-negative budget except 5003, and every row has
    # a non-empty channel -- an AND-joined predicate should catch exactly the one
    # row that fails the first clause and still pass the rows that satisfy both.
    rule = DQRule(
        id="test-and-clause",
        full_name=CAMPAIGNS,
        description="test",
        predicate="budget >= 0 AND channel IS NOT NULL",
    )

    result = evaluate_rule(rule, client)

    assert result.passed is False
    assert result.violation_count == 1


# ---- live: real evaluation against the Free Edition workspace -------------------
#
# Needs network and the `ucmeta` OAuth profile, gated by UC_LIVE_TESTS=1 -- same
# opt-in convention as test_validate.py's / test_apply.py's live tests. Proves the
# rules evaluate correctly against real Unity Catalog data, not just the fake:
# campaigns' two seeded violations (negative budget, end before start) are caught
# by rule id and count, and customers -- seeded clean -- passes every rule.


@pytest.mark.uc_live
@pytest.mark.skipif(
    not UC_LIVE_TESTS_ENABLED,
    reason="set UC_LIVE_TESTS=1 to run this against the live Free Edition workspace",
)
def test_live_dq_rules_catch_the_seeded_campaigns_violations_and_customers_passes_clean():
    client = RealUCClient()

    campaigns_results = {result.rule_id: result for result in evaluate_rules(CAMPAIGNS, client)}
    customers_results = evaluate_rules(CUSTOMERS, client)

    assert campaigns_results["campaigns-budget-non-negative"].passed is False
    assert campaigns_results["campaigns-budget-non-negative"].violation_count == 1
    assert campaigns_results["campaigns-end-date-not-before-start-date"].passed is False
    assert campaigns_results["campaigns-end-date-not-before-start-date"].violation_count == 1
    assert campaigns_results["campaigns-budget-non-negative"].rows_checked == 6  # all 6 seeded campaigns rows

    assert len(customers_results) == 2
    assert all(result.passed for result in customers_results)
    assert all(result.rows_checked == 8 for result in customers_results)  # all 8 seeded customers rows

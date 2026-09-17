"""Shared behavioural contract for every `uc_client.UCClient` implementation.

Every test in this module runs twice -- once against `fake_uc.FakeUCClient`, once
against `uc_client.RealUCClient` pointed at the live Free Edition workspace -- via the
`uc_client` fixture, parametrized below. This is what ADR-004 means by "a shared
contract-test suite runs against both so the fake cannot quietly drift from real
Unity Catalog semantics": the assertions are identical, only the implementation under
test differs.

The fake-backed parametrization always runs (offline, deterministic, part of the fast
inner loop). The live-backed parametrization needs network and a valid `ucmeta` OAuth
profile, so it is marked `uc_live` and skipped unless `UC_LIVE_TESTS=1` is set --
matching the same opt-in convention `tests/e2e/demo_scenario.py --live` uses for the
same reason (spec: F-PLATFORM-001, `tests/e2e/demo_scenario.py` build verdict).

Both implementations are seeded with (or pointed at) the same table:
`workspace.analytics.customers`, which exists for real in the live workspace
(`scripts/seed_demo_data.sql`) and is also `FakeUCClient`'s default fixture. Writes in
this suite use an obviously-a-test marker string so a live run leaves the real table
in a harmless, clearly-attributable state rather than overwriting anything meaningful.
"""

from __future__ import annotations

import os

import pytest

from uc_metadata.fake_uc import FakeUCClient
from uc_metadata.uc_client import RealUCClient, UCClient, UCTableNotFoundError

TABLE = "workspace.analytics.customers"
UC_LIVE_TESTS_ENABLED = os.environ.get("UC_LIVE_TESTS") == "1"


def _fake_client() -> UCClient:
    return FakeUCClient()


def _real_client() -> UCClient:
    return RealUCClient()


_live_param_marks = [
    pytest.mark.uc_live,
    pytest.mark.skipif(
        not UC_LIVE_TESTS_ENABLED,
        reason="set UC_LIVE_TESTS=1 to run this against the live Free Edition workspace",
    ),
]


@pytest.fixture(
    params=[
        pytest.param(_fake_client, id="fake"),
        pytest.param(_real_client, id="real", marks=_live_param_marks),
    ]
)
def client(request) -> UCClient:
    """One `UCClient` instance per test: a fresh `FakeUCClient`, or a `RealUCClient`
    against the live workspace when `UC_LIVE_TESTS=1` is set."""
    return request.param()


def test_get_table_returns_customers_columns_in_position_order(client: UCClient):
    """`get_table` returns the seeded/real `customers` columns, in position order,
    with the harvested facts harvest.py will need: name, SQL-text data type,
    nullability and partition status."""
    table = client.get_table(TABLE)

    assert table.full_name == TABLE
    column_names = [column.name for column in table.columns]
    assert column_names == [
        "customer_id",
        "email",
        "first_name",
        "last_name",
        "region",
        "signup_date",
        "lifetime_value",
    ]
    assert [column.position for column in table.columns] == list(range(7))
    # None of customers' columns are partition keys, on the fake or the real table.
    assert all(column.partition_key is False for column in table.columns)

    lifetime_value = next(c for c in table.columns if c.name == "lifetime_value")
    assert lifetime_value.data_type == "decimal(10,2)"
    signup_date = next(c for c in table.columns if c.name == "signup_date")
    assert signup_date.data_type == "date"


def test_get_table_on_unknown_table_raises_not_found(client: UCClient):
    """A three-part name with no matching table raises `UCTableNotFoundError` on
    both implementations, so callers can catch one exception type regardless of
    which `UCClient` they were handed."""
    with pytest.raises(UCTableNotFoundError):
        client.get_table("workspace.analytics.does_not_exist_xyz")


def test_set_table_comment_is_idempotent(client: UCClient):
    """Setting the same table comment twice succeeds both times and leaves the same
    comment in place -- the idempotency `apply.py` will depend on later."""
    comment = "Managed by uc-metadata-platform (contract test)."

    first_sql = client.set_table_comment(TABLE, comment)
    client.set_table_comment(TABLE, comment)  # must not raise the second time

    assert "COMMENT ON TABLE" in first_sql
    assert comment in first_sql
    assert client.get_table(TABLE).comment == comment


def test_set_column_comment_lands_on_the_named_column_only(client: UCClient):
    """Setting one column's comment does not touch any other column's comment."""
    comment = "Customer email address (contract test)."

    client.set_column_comment(TABLE, "email", comment)
    table = client.get_table(TABLE)

    email = next(c for c in table.columns if c.name == "email")
    other = next(c for c in table.columns if c.name == "first_name")
    assert email.comment == comment
    assert other.comment != comment


def test_set_table_properties_merges_without_dropping_existing_keys(client: UCClient):
    """`set_table_properties` merges the given keys in rather than replacing the
    whole properties map: two properties set in two separate calls both survive
    together, and the key set already present before either call is not shrunk.

    Deliberately does not assert every pre-existing value is byte-identical
    afterwards: on the real workspace, `delta.lastCommitTimestamp` (and other
    Delta-internal bookkeeping keys) legitimately change on *every* write, including
    an unrelated `ALTER TABLE ... SET TBLPROPERTIES` -- that is Unity Catalog's own
    behaviour, not something this client should paper over, and a stricter assertion
    here was a genuine false positive caught by running this suite live rather than
    only against the fake.
    """
    before_keys = set(client.get_table(TABLE).properties)

    first_sql = client.set_table_properties(TABLE, {"uc_metadata.contract_test_a": "first"})
    second_sql = client.set_table_properties(TABLE, {"uc_metadata.contract_test_b": "second"})
    after = client.get_table(TABLE).properties

    assert "SET TBLPROPERTIES" in first_sql
    assert "SET TBLPROPERTIES" in second_sql
    assert after["uc_metadata.contract_test_a"] == "first"
    assert after["uc_metadata.contract_test_b"] == "second"
    assert before_keys <= set(after)  # nothing that existed before was dropped


def test_set_table_tags_is_idempotent_and_readable_back(client: UCClient):
    """Table tags set via `set_table_tags` are readable back on `get_table`, and
    re-setting the same tag does not error."""
    client.set_table_tags(TABLE, {"uc_metadata_contract_test": "true"})
    client.set_table_tags(TABLE, {"uc_metadata_contract_test": "true"})  # idempotent

    assert client.get_table(TABLE).tags["uc_metadata_contract_test"] == "true"


def test_set_column_tags_is_scoped_to_the_named_column(client: UCClient):
    """Column tags land on the named column's `tags` dict, not on other columns or
    on the table-level tags."""
    client.set_column_tags(TABLE, "email", {"pii_contract_test": "true"})
    table = client.get_table(TABLE)

    email = next(c for c in table.columns if c.name == "email")
    other = next(c for c in table.columns if c.name == "first_name")
    assert email.tags["pii_contract_test"] == "true"
    assert "pii_contract_test" not in other.tags
    assert "pii_contract_test" not in table.tags


def test_write_methods_reject_empty_property_and_tag_maps(client: UCClient):
    """Precondition: `set_table_properties`/`set_table_tags` refuse an empty
    mapping rather than emitting `SET TBLPROPERTIES ()`, which is not valid DDL."""
    with pytest.raises(ValueError):
        client.set_table_properties(TABLE, {})
    with pytest.raises(ValueError):
        client.set_table_tags(TABLE, {})

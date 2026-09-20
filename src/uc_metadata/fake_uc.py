"""`FakeUCClient`: a fast, offline, in-memory implementation of `uc_client.UCClient`.

This is what unit tests and the default (non-`--live`) e2e run talk to (build-verdict
table: "kept, but no longer the product's target ... so unit tests are fast, offline
and deterministic"). It is seeded with a fixture set of tables that mirror the shape
of the three real tables seeded into the live workspace by
`scripts/seed_demo_data.sql` -- same names, same columns, same types -- but with no
real data volume and no network involved.

Its surface is defined entirely by `UCClient`; `tests/unit/test_uc_client_contract.py`
runs the same behavioural assertions against this class and against `RealUCClient` so
this fake cannot quietly drift away from real Unity Catalog semantics (ADR-004).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

from uc_metadata.uc_client import (
    UCClientError,
    UCColumn,
    UCTable,
    UCTableNotFoundError,
    build_insert_sql,
    kv_clause,
    quote_full_name,
    quote_ident,
    quote_literal,
    require_single_part_name,
    require_three_part_name,
)


@dataclass
class _FakeColumn:
    """Mutable in-memory state backing one `UCColumn`."""

    name: str
    data_type: str
    nullable: bool
    position: int
    partition_key: bool = False
    comment: str | None = None
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class _FakeTable:
    """Mutable in-memory state backing one `UCTable`."""

    comment: str | None = None
    columns: List[_FakeColumn] = field(default_factory=list)
    properties: Dict[str, str] = field(default_factory=dict)
    tags: Dict[str, str] = field(default_factory=dict)
    rows: List[Dict[str, Any]] = field(default_factory=list)


def _column(name: str, data_type: str, position: int, nullable: bool = True) -> _FakeColumn:
    return _FakeColumn(name=name, data_type=data_type, nullable=nullable, position=position)


def _default_sample_rows() -> Dict[str, List[Dict[str, Any]]]:
    """Real representative sample rows for each fixture table -- the first five rows
    `scripts/seed_demo_data.sql` inserts into the live workspace for each table,
    verified against the live workspace on 2026-09-17 (`customers`) and transcribed
    from the seed script for `campaigns`/`orders`.

    Values are strings, matching the wire format Unity Catalog's statement execution
    API actually renders (its default `JSON_ARRAY` result format -- verified live),
    so `sample_rows` looks the same shape on `FakeUCClient` as on `RealUCClient`. The
    `orders` rows deliberately keep the mix of order-status words ('shipped',
    'pending', 'refunded') and US-state abbreviations ('CA', 'NY') that makes `state`
    the intentionally ambiguous column the AI drafter is meant to flag (spec: Q&A
    "AI confidently produces a wrong answer" moment; see also `glossary/terms.yaml`'s
    `order_status` entry).
    """
    return {
        "workspace.analytics.customers": [
            {
                "customer_id": "100001",
                "email": "amara.diallo@example.com",
                "first_name": "Amara",
                "last_name": "Diallo",
                "region": "EMEA",
                "signup_date": "2023-02-14",
                "lifetime_value": "1240.50",
            },
            {
                "customer_id": "100002",
                "email": "jin.park@example.com",
                "first_name": "Jin",
                "last_name": "Park",
                "region": "APAC",
                "signup_date": "2023-05-03",
                "lifetime_value": "340.00",
            },
            {
                "customer_id": "100003",
                "email": "lucas.oliveira@example.com",
                "first_name": "Lucas",
                "last_name": "Oliveira",
                "region": "LATAM",
                "signup_date": "2022-11-21",
                "lifetime_value": "5620.75",
            },
            {
                "customer_id": "100004",
                "email": "freya.johansen@example.com",
                "first_name": "Freya",
                "last_name": "Johansen",
                "region": "EMEA",
                "signup_date": "2024-01-09",
                "lifetime_value": "90.25",
            },
            {
                "customer_id": "100005",
                "email": "wei.chen@example.com",
                "first_name": "Wei",
                "last_name": "Chen",
                "region": "APAC",
                "signup_date": "2023-08-30",
                "lifetime_value": "2100.00",
            },
        ],
        "workspace.marketing.campaigns": [
            {
                "campaign_id": "5001",
                "name": "Spring Launch",
                "channel": "email",
                "budget": "12000.00",
                "start_date": "2026-03-01",
                "end_date": "2026-03-31",
                "active": "false",
            },
            {
                "campaign_id": "5002",
                "name": "Summer Push",
                "channel": "social",
                "budget": "8000.00",
                "start_date": "2026-06-01",
                "end_date": "2026-06-30",
                "active": "false",
            },
            {
                "campaign_id": "5003",
                "name": "Back to School",
                "channel": "search",
                "budget": "-500.00",
                "start_date": "2026-08-15",
                "end_date": "2026-09-01",
                "active": "false",
            },
            {
                "campaign_id": "5004",
                "name": "Holiday Blitz",
                "channel": "email",
                "budget": "25000.00",
                "start_date": "2026-11-20",
                "end_date": "2026-11-10",
                "active": "false",
            },
            {
                "campaign_id": "5005",
                "name": "New Year Retention",
                "channel": "lifecycle",
                "budget": "4000.00",
                "start_date": "2027-01-02",
                "end_date": "2027-01-31",
                "active": "true",
            },
        ],
        "workspace.analytics.orders": [
            {
                "order_id": "900001",
                "customer_id": "100001",
                "state": "shipped",
                "amount": "84.00",
                "order_ts": "2026-04-02 10:15:00",
                "channel": "web",
            },
            {
                "order_id": "900002",
                "customer_id": "100003",
                "state": "CA",
                "amount": "210.50",
                "order_ts": "2026-04-03 09:02:00",
                "channel": "web",
            },
            {
                "order_id": "900003",
                "customer_id": "100002",
                "state": "pending",
                "amount": "19.99",
                "order_ts": "2026-04-04 14:22:00",
                "channel": "mobile",
            },
            {
                "order_id": "900004",
                "customer_id": "100005",
                "state": "NY",
                "amount": "560.00",
                "order_ts": "2026-04-05 11:47:00",
                "channel": "web",
            },
            {
                "order_id": "900005",
                "customer_id": "100007",
                "state": "refunded",
                "amount": "120.00",
                "order_ts": "2026-04-06 08:30:00",
                "channel": "mobile",
            },
        ],
    }


def default_fixture_tables() -> Dict[str, _FakeTable]:
    """The fixture set `FakeUCClient` seeds itself with by default: the same three
    tables `scripts/seed_demo_data.sql` creates in the live workspace, same shapes,
    plus the first five rows each table is seeded with (`_default_sample_rows`), so
    `sample_rows` has real representative data to hand back offline. Kept as a free
    function (rather than inlined in `__init__`) so a test can import and mutate a
    fresh copy without reaching into a live `FakeUCClient`.
    """
    sample_rows = _default_sample_rows()
    return {
        "workspace.analytics.customers": _FakeTable(
            comment=None,
            columns=[
                _column("customer_id", "bigint", 0),
                _column("email", "string", 1),
                _column("first_name", "string", 2),
                _column("last_name", "string", 3),
                _column("region", "string", 4),
                _column("signup_date", "date", 5),
                _column("lifetime_value", "decimal(10,2)", 6),
            ],
            rows=sample_rows["workspace.analytics.customers"],
        ),
        "workspace.marketing.campaigns": _FakeTable(
            comment=None,
            columns=[
                _column("campaign_id", "bigint", 0),
                _column("name", "string", 1),
                _column("channel", "string", 2),
                _column("budget", "decimal(10,2)", 3),
                _column("start_date", "date", 4),
                _column("end_date", "date", 5),
                _column("active", "boolean", 6),
            ],
            rows=sample_rows["workspace.marketing.campaigns"],
        ),
        "workspace.analytics.orders": _FakeTable(
            comment=None,
            columns=[
                _column("order_id", "bigint", 0),
                _column("customer_id", "bigint", 1),
                _column("state", "string", 2),
                _column("amount", "decimal(10,2)", 3),
                _column("order_ts", "timestamp", 4),
                _column("channel", "string", 5),
            ],
            rows=sample_rows["workspace.analytics.orders"],
        ),
    }


class FakeUCClient:
    """In-memory `UCClient`. No network, no auth, deterministic.

    Every write method builds and returns the same SQL string shape `RealUCClient`
    would run (via the same `uc_client.quote_*`/`kv_clause` helpers), so tests that
    assert on "exact COMMENT ON string" (the `apply.py` build verdict's requirement)
    get the same string offline as they would against the live workspace. Every
    write method also accepts the same `dry_run` keyword `RealUCClient` does: the
    SQL is built the same way regardless, and mutating `self._tables` is the only
    step `dry_run=True` skips.
    """

    def __init__(self, tables: Dict[str, _FakeTable] | None = None) -> None:
        self._tables: Dict[str, _FakeTable] = tables if tables is not None else default_fixture_tables()
        # In-memory backing for `insert_rows` -- a plain append-only row store
        # keyed by full name, distinct from `self._tables` (which models a
        # dataset's columns/comment/tags, not arbitrary inserted rows). This
        # is what `coverage_history.publish_coverage_history` writes into
        # under the fake, and `inserted_rows` below is the only way to read
        # it back -- there is no `insert_rows`-side `get_table` equivalent,
        # because this store never claims to be a real dataset's schema.
        self._row_tables: Dict[str, List[Dict[str, Any]]] = {}
        # In-memory backing for `create_catalog`/`create_schema`/`set_catalog_tags`
        # (added for `provision_catalog.py`, spec F-PLATFORM-004) -- the fake had
        # no notion of a catalog or a schema at all before this, following the
        # same precedent `_row_tables` set: a second piece of state plus its own
        # accessors, kept separate from `self._tables` (which models a table's
        # own columns/comment/tags, not the catalog/schema namespace above it).
        self._catalogs: Dict[str, Optional[str]] = {}
        self._catalog_schemas: Dict[str, set] = {}
        self._catalog_tags: Dict[str, Dict[str, str]] = {}

    # ---- reads -----------------------------------------------------------------

    def get_table(self, full_name: str) -> UCTable:
        require_three_part_name(full_name)
        table = self._require_table(full_name)
        columns = [
            UCColumn(
                name=column.name,
                data_type=column.data_type,
                nullable=column.nullable,
                position=column.position,
                partition_key=column.partition_key,
                comment=column.comment,
                tags=dict(column.tags),
            )
            for column in table.columns
        ]
        return UCTable(
            full_name=full_name,
            comment=table.comment,
            columns=columns,
            properties=dict(table.properties),
            tags=dict(table.tags),
        )

    def sample_rows(self, full_name: str, limit: int = 5) -> List[Dict[str, Any]]:
        require_three_part_name(full_name)
        if limit <= 0:
            raise ValueError(f"limit must be a positive integer, got {limit!r}")
        table = self._require_table(full_name)
        return [dict(row) for row in table.rows[:limit]]

    # ---- writes ------------------------------------------------------------------

    def set_table_comment(self, full_name: str, comment: str, *, dry_run: bool = False) -> str:
        require_three_part_name(full_name)
        sql = f"COMMENT ON TABLE {quote_full_name(full_name)} IS {quote_literal(comment)}"
        if dry_run:
            return sql
        table = self._require_table(full_name)
        table.comment = comment
        return sql

    def set_column_comment(
        self, full_name: str, column_name: str, comment: str, *, dry_run: bool = False
    ) -> str:
        require_three_part_name(full_name)
        sql = (
            f"COMMENT ON COLUMN {quote_full_name(full_name)}.{quote_ident(column_name)} "
            f"IS {quote_literal(comment)}"
        )
        if dry_run:
            return sql
        column = self._require_column(full_name, column_name)
        column.comment = comment
        return sql

    def set_table_properties(
        self, full_name: str, properties: Mapping[str, str], *, dry_run: bool = False
    ) -> str:
        require_three_part_name(full_name)
        if not properties:
            raise ValueError("properties must not be empty")
        sql = f"ALTER TABLE {quote_full_name(full_name)} SET TBLPROPERTIES ({kv_clause(properties)})"
        if dry_run:
            return sql
        table = self._require_table(full_name)
        table.properties.update(properties)  # merge, same semantics as SET TBLPROPERTIES
        return sql

    def set_table_tags(self, full_name: str, tags: Mapping[str, str], *, dry_run: bool = False) -> str:
        require_three_part_name(full_name)
        if not tags:
            raise ValueError("tags must not be empty")
        sql = f"ALTER TABLE {quote_full_name(full_name)} SET TAGS ({kv_clause(tags)})"
        if dry_run:
            return sql
        table = self._require_table(full_name)
        table.tags.update(tags)  # merge, same semantics as SET TAGS
        return sql

    def set_column_tags(
        self, full_name: str, column_name: str, tags: Mapping[str, str], *, dry_run: bool = False
    ) -> str:
        require_three_part_name(full_name)
        if not tags:
            raise ValueError("tags must not be empty")
        sql = (
            f"ALTER TABLE {quote_full_name(full_name)} ALTER COLUMN {quote_ident(column_name)} "
            f"SET TAGS ({kv_clause(tags)})"
        )
        if dry_run:
            return sql
        column = self._require_column(full_name, column_name)
        column.tags.update(tags)  # merge, same semantics as ALTER COLUMN ... SET TAGS
        return sql

    def insert_rows(self, full_name: str, rows: List[Dict[str, Any]], *, dry_run: bool = False) -> str:
        sql = build_insert_sql(full_name, rows)  # validates shape identically to RealUCClient
        if dry_run:
            return sql
        self._row_tables.setdefault(full_name, []).extend(dict(row) for row in rows)
        return sql

    def inserted_rows(self, full_name: str) -> List[Dict[str, Any]]:
        """Test-only accessor: every row `insert_rows` has actually appended
        to `full_name` (real writes only, `dry_run=True` never lands here),
        in append order. Not part of `UCClient` -- `RealUCClient` has no
        equivalent, since asserting on real warehouse state means running a
        `SELECT` instead; this exists so a unit test can assert exactly what
        a run would have appended with no network, matching this module's own
        docstring's reason for existing at all."""
        return [dict(row) for row in self._row_tables.get(full_name, [])]

    # ---- catalog/schema writes (added for provision_catalog.py, F-PLATFORM-004) --

    def create_catalog(self, name: str, comment: Optional[str] = None, *, dry_run: bool = False) -> str:
        require_single_part_name(name)
        sql = f"CREATE CATALOG IF NOT EXISTS {quote_ident(name)}"
        if comment is not None:
            sql += f" COMMENT {quote_literal(comment)}"
        if dry_run:
            return sql
        if name not in self._catalogs:
            # Create-only: a catalog that already exists is left exactly as it
            # is -- the comment is never re-applied on re-run (Rules &
            # Constraints), so this branch is the only place a comment is ever
            # recorded at all.
            self._catalogs[name] = comment
            self._catalog_schemas[name] = set()
        return sql

    def create_schema(self, catalog_name: str, schema_name: str, *, dry_run: bool = False) -> str:
        require_single_part_name(catalog_name)
        require_single_part_name(schema_name)
        sql = f"CREATE SCHEMA IF NOT EXISTS {quote_ident(catalog_name)}.{quote_ident(schema_name)}"
        if dry_run:
            return sql
        if catalog_name not in self._catalogs:
            # Honest failure mode for a real metastore's own referential
            # constraint -- should never trigger in practice, since the plan
            # always creates the catalog before the schema (provision_catalog.py),
            # but a fake that silently accepted this would hide a real bug.
            raise UCClientError(
                f"cannot create schema {schema_name!r}: catalog {catalog_name!r} does not exist"
            )
        self._catalog_schemas.setdefault(catalog_name, set()).add(schema_name)
        return sql

    def set_catalog_tags(self, catalog_name: str, tags: Mapping[str, str], *, dry_run: bool = False) -> str:
        require_single_part_name(catalog_name)
        if not tags:
            raise ValueError("tags must not be empty")
        sql = f"ALTER CATALOG {quote_ident(catalog_name)} SET TAGS ({kv_clause(tags)})"
        if dry_run:
            return sql
        if catalog_name not in self._catalogs:
            raise UCClientError(f"cannot set tags on catalog {catalog_name!r}: it does not exist")
        self._catalog_tags.setdefault(catalog_name, {}).update(tags)  # merge, same semantics as SET TAGS
        return sql

    def catalog_exists(self, name: str) -> bool:
        """Test-only accessor: whether `create_catalog` has actually created
        `name` (real writes only). Not part of `UCClient`, following the
        `inserted_rows` precedent above."""
        return name in self._catalogs

    def catalog_comment(self, name: str) -> Optional[str]:
        """Test-only accessor: the comment `name` was created with, or `None`
        if it was created with no comment, or if it does not exist at all
        (both cases the caller can already tell apart via `catalog_exists`)."""
        return self._catalogs.get(name)

    def schema_exists(self, catalog_name: str, schema_name: str) -> bool:
        """Test-only accessor: whether `create_schema` has actually created
        `schema_name` inside `catalog_name`."""
        return schema_name in self._catalog_schemas.get(catalog_name, set())

    def catalog_tags(self, name: str) -> Dict[str, str]:
        """Test-only accessor: every tag `set_catalog_tags` has actually
        written on catalog `name`, merged across every call so far."""
        return dict(self._catalog_tags.get(name, {}))

    # ---- internal lookups ----------------------------------------------------

    def _require_table(self, full_name: str) -> _FakeTable:
        table = self._tables.get(full_name)
        if table is None:
            raise UCTableNotFoundError(f"no table found at {full_name!r}")
        return table

    def _require_column(self, full_name: str, column_name: str) -> _FakeColumn:
        table = self._require_table(full_name)
        for column in table.columns:
            if column.name == column_name:
                return column
        raise UCTableNotFoundError(f"no column {column_name!r} on table {full_name!r}")

"""The one seam every later module (`harvest.py`, `apply.py`, `provision_catalog.py`)
talks to for Unity Catalog reads and writes.

`UCClient` is a `Protocol` describing that seam: list a table's columns and current
comment, read its properties and tags, write a comment, properties or tags back, and
-- added for `provision_catalog.py`, spec F-PLATFORM-004 -- create a catalog, create a
schema inside it, and write a tag at catalog granularity. Two implementations exist
behind it (ADR-004): `RealUCClient`, a thin translation layer over `databricks-sdk`
against the live Free Edition workspace, and `fake_uc.FakeUCClient`, a fast in-memory
stand-in for unit tests. Neither module imports the other; both import this one, so
`harvest.py`/`apply.py`/`provision_catalog.py` can depend on `UCClient` alone and take
either implementation as a constructor argument.

Design decisions worth stating rather than leaving implicit:

- Reads return `UCTable`/`UCColumn`, not `databricks-sdk`'s own `TableInfo`/
  `ColumnInfo` dataclasses, so nothing above this module needs to know the SDK's
  shape (e.g. that its `type_name` is a driver-internal enum and the SQL-facing type
  string is `type_text`, or that tags never appear on `TablesAPI.get`'s response at
  all -- verified against the live workspace, see `RealUCClient` below).
- Writes execute real SQL DDL (`COMMENT ON TABLE/COLUMN`, `ALTER TABLE ... SET
  TBLPROPERTIES`, `ALTER TABLE ... SET TAGS`) rather than a metadata-only REST PATCH,
  and every write method returns the exact SQL string it ran, so callers and tests
  can assert on it (the build-verdict table's own requirement for `apply.py`).
- Every write method is idempotent in effect: `COMMENT ON ... IS '<same value>'` and
  `SET TBLPROPERTIES (...)`/`SET TAGS (...)` with the same key/value both re-run
  cleanly with no error and no observable change (verified against the live
  workspace) -- `apply.py`'s idempotency claim rests on that being true here, not
  rediscovered there.
- Every write method takes a keyword-only `dry_run: bool = False`. With
  `dry_run=True`, the method validates its own preconditions (three-part name,
  non-empty properties/tags mapping) and returns the exact SQL string it would
  run, but never touches catalogue state -- no statement is submitted on
  `RealUCClient`, no in-memory table is mutated on `FakeUCClient`. This is the
  one seam `apply.py`'s `plan_apply` needs (spec Rules & Constraints: "every
  change request prints the full set of catalogue writes it would perform
  before it can be merged") without duplicating any SQL-building logic: each
  write method builds its `sql` variable exactly once, from the same code path,
  before either returning it (`dry_run=True`) or executing it and then
  returning it -- so a planned statement and the statement that later actually
  runs can never silently diverge into two implementations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Protocol, runtime_checkable

# The Free Edition workspace this prototype targets (spec: F-PLATFORM-001, Rules &
# Constraints). Documented here once rather than duplicated at every call site;
# callers needing a different workspace pass their own `profile`/`warehouse_id`.
DEFAULT_UC_PROFILE = "ucmeta"
DEFAULT_WAREHOUSE_ID = "66fca89a60cb0837"


class UCClientError(Exception):
    """Base class for errors this seam raises, so callers can catch one type rather
    than reaching into `databricks-sdk`'s exception hierarchy."""


class UCTableNotFoundError(UCClientError):
    """No table exists in Unity Catalog at the given three-part name."""


class UCWriteError(UCClientError):
    """A write (comment/property/tag) did not reach a successful terminal state."""


class UCReadError(UCClientError):
    """A read (e.g. a tags lookup) did not reach a successful terminal state."""


@dataclass(frozen=True)
class UCColumn:
    """One column's harvested facts, as Unity Catalog reports them.

    `data_type` is the SQL type text Unity Catalog itself renders (e.g.
    `"decimal(10,2)"`), not a driver-internal type enum -- that is what a human
    reading a harvested contract skeleton expects to see, and what `harvest.py` will
    write straight into `models.Column.data_type`.
    """

    name: str
    data_type: str
    nullable: bool
    position: int
    partition_key: bool
    comment: Optional[str] = None
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class UCTable:
    """One table's harvested facts: identity, columns, comment, properties, tags."""

    full_name: str
    comment: Optional[str]
    columns: List[UCColumn] = field(default_factory=list)
    properties: Dict[str, str] = field(default_factory=dict)
    tags: Dict[str, str] = field(default_factory=dict)


@runtime_checkable
class UCClient(Protocol):
    """The narrow interface `harvest.py`/`apply.py` depend on instead of a specific
    Unity Catalog transport.

    Precondition on every method: `full_name` is a non-empty `catalog.schema.table`
    three-part name (this is what `models.Qualifier.full_name` already produces).
    Postcondition on every `get_*`: raises `UCTableNotFoundError` if no such table
    exists, never returns a partial/`None` result silently. Postcondition on every
    `set_*`: either the write lands and the exact SQL string executed is returned, or
    a `UCWriteError` is raised -- never a partial write. Postcondition on every
    `set_*` called with `dry_run=True`: no catalogue state changes (no statement
    submitted, no in-memory table mutated), and the exact SQL string that write
    would execute is returned.
    """

    def get_table(self, full_name: str) -> UCTable:
        """Return the table's columns, comment, properties and tags."""
        ...

    def sample_rows(self, full_name: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Return up to `limit` rows as column-name-keyed dicts, for `propose.py`'s
        AI drafter to read as retrieval context (masked/redacted by the caller for
        any column that looks sensitive before it ever reaches the drafter).

        Precondition: `limit` is a positive integer. Postcondition: returns at most
        `limit` rows, each a `{column_name: value}` mapping over every column in the
        table; an empty table returns an empty list, never `None`. Values come back
        as the strings Unity Catalog's statement execution API itself renders (its
        default `JSON_ARRAY` result format), not driver-native Python types -- the
        same shape on `RealUCClient` and `FakeUCClient`, verified against the live
        workspace.
        """
        ...

    def set_table_comment(self, full_name: str, comment: str, *, dry_run: bool = False) -> str:
        """Set the table-level comment/description. Returns the SQL executed
        (or, if `dry_run=True`, the SQL that would be executed, with no write made).
        """
        ...

    def set_column_comment(
        self, full_name: str, column_name: str, comment: str, *, dry_run: bool = False
    ) -> str:
        """Set one column's comment/description. Returns the SQL executed
        (or, if `dry_run=True`, the SQL that would be executed, with no write made).
        """
        ...

    def set_table_properties(
        self, full_name: str, properties: Mapping[str, str], *, dry_run: bool = False
    ) -> str:
        """Merge `properties` into the table's TBLPROPERTIES (existing keys not
        named in `properties` are left untouched). Returns the SQL executed
        (or, if `dry_run=True`, the SQL that would be executed, with no write made).
        Precondition: `properties` is non-empty.
        """
        ...

    def set_table_tags(self, full_name: str, tags: Mapping[str, str], *, dry_run: bool = False) -> str:
        """Merge `tags` into the table's tags. Returns the SQL executed
        (or, if `dry_run=True`, the SQL that would be executed, with no write made).
        Precondition: `tags` is non-empty.
        """
        ...

    def set_column_tags(
        self, full_name: str, column_name: str, tags: Mapping[str, str], *, dry_run: bool = False
    ) -> str:
        """Merge `tags` into one column's tags. Returns the SQL executed
        (or, if `dry_run=True`, the SQL that would be executed, with no write made).
        Precondition: `tags` is non-empty.
        """
        ...

    def insert_rows(self, full_name: str, rows: List[Mapping[str, Any]], *, dry_run: bool = False) -> str:
        """Append every row in `rows` to `full_name` via one multi-row `INSERT
        INTO ... VALUES` statement -- the one write shape none of the methods
        above cover, since every other write mutates a table's own comment,
        properties or tags rather than appending data rows (added for
        `coverage_history.publish_coverage_history`; see `build_insert_sql`
        below for the shared SQL-building code both implementations use).
        Returns the SQL executed (or, if `dry_run=True`, the SQL that would be
        executed, with no write made).

        Precondition: `rows` is non-empty and every row has exactly the same
        set of keys (order-independent) -- those keys become the INSERT's
        explicit column list, in the first row's key order. Postcondition: on
        success, every row in `rows` lands or none do -- one SQL statement
        with multiple `VALUES` tuples is atomic at the warehouse, which is
        what makes an append-only, whole-run-or-nothing write possible
        without this seam reimplementing rollback.
        """
        ...

    def create_catalog(self, name: str, comment: Optional[str] = None, *, dry_run: bool = False) -> str:
        """Create a catalog named `name` if it does not already exist, optionally
        setting its comment at creation time (added for `provision_catalog.py`,
        spec F-PLATFORM-004). Returns the SQL executed (or, if `dry_run=True`,
        the SQL that would be executed, with no write made).

        Precondition: `name` is a legal single-part identifier (see
        `require_single_part_name`). Postcondition: idempotent in effect --
        calling this again for a catalog that already exists succeeds and
        changes nothing (create-only, per Rules & Constraints: the comment is
        never re-applied to a catalog that already exists, unlike a real
        `CREATE CATALOG IF NOT EXISTS ... COMMENT ...` statement's own
        no-op-on-exists semantics, which this mirrors).
        """
        ...

    def create_schema(self, catalog_name: str, schema_name: str, *, dry_run: bool = False) -> str:
        """Create a schema named `schema_name` inside `catalog_name` if it does
        not already exist (added for `provision_catalog.py`, spec F-PLATFORM-004).
        Returns the SQL executed (or, if `dry_run=True`, the SQL that would be
        executed, with no write made).

        Precondition: `catalog_name` and `schema_name` are each a legal
        single-part identifier. Postcondition: idempotent in effect -- calling
        this again for a schema that already exists succeeds and changes
        nothing.
        """
        ...

    def set_catalog_tags(self, catalog_name: str, tags: Mapping[str, str], *, dry_run: bool = False) -> str:
        """Merge `tags` into the catalog's tags (added for
        `provision_catalog.py`, spec F-PLATFORM-004, mirroring `set_table_tags`
        exactly and differing only in the object it targets -- writing a tag at
        catalog granularity is a genuinely new capability, not a variant of the
        table-tag method). Returns the SQL executed (or, if `dry_run=True`, the
        SQL that would be executed, with no write made).

        Precondition: `catalog_name` is a legal single-part identifier;
        `tags` is non-empty. Postcondition: existing keys not named in `tags`
        are left untouched (merge, not replace) -- this is the create-only
        rule's one named exception (Rules & Constraints): a request whose
        declared sensitivity changed moves the catalog's label to the new
        value on the next run, rather than the label being fixed forever at
        creation time.
        """
        ...


# ---- SQL-building helpers shared by both implementations (identical quoting rules
# so the SQL strings FakeUCClient hands back for assertions look like RealUCClient's) --


def require_three_part_name(full_name: str) -> None:
    """Precondition check shared by both implementations. Raises `ValueError` if
    `full_name` is not a non-empty `catalog.schema.table` name."""
    parts = full_name.split(".")
    if len(parts) != 3 or not all(part.strip() for part in parts):
        raise ValueError(f"expected a catalog.schema.table three-part name, got {full_name!r}")


def require_single_part_name(name: str) -> None:
    """Precondition check for a catalog or schema name (added for
    `provision_catalog.py`, spec F-PLATFORM-004 Rules & Constraints: "every
    name that reaches a statement builder is validated as an identifier
    first"). Raises `ValueError` if `name` is empty or contains a `.` -- a
    legal single-part identifier never needs to be split, and a name
    containing a `.` would be silently mis-parsed as a multi-part name by
    whatever eventually reads it back."""
    if not name or not name.strip() or "." in name:
        raise ValueError(f"expected a legal single-part identifier, got {name!r}")


def quote_ident(identifier: str) -> str:
    """Backtick-quote one SQL identifier, escaping any embedded backtick."""
    return f"`{identifier.replace('`', '``')}`"


def quote_full_name(full_name: str) -> str:
    """Backtick-quote each part of a `catalog.schema.table` name."""
    return ".".join(quote_ident(part) for part in full_name.split("."))


def quote_literal(value: str) -> str:
    """Single-quote a SQL string literal, escaping embedded backslashes and single
    quotes by doubling each (backslashes first, so a backslash introduced ahead of
    an escaped quote is never itself left unescaped).

    The backslash-doubling was added after a live-confirmed bug: this session's
    warehouse parses string literals in `escapedStringLiterals=true`-style legacy
    mode, where a lone backslash immediately before the closing `'` is read as an
    escape for that quote character, leaving the DDL statement's string literal
    unterminated (`PARSE_SYNTAX_ERROR`) -- reproduced live via `COMMENT ON TABLE
    ... IS '...ends in a backslash\\'`, the exact grammar context every write in
    this module uses (`COMMENT ON ... IS`, `SET TBLPROPERTIES`/`SET TAGS`).
    Doubling every backslash first, then doubling every single quote, round-trips
    correctly against the live warehouse for a plain backslash, a trailing
    backslash, multiple consecutive backslashes, and a backslash immediately
    followed by a quote, without regressing the already-verified cases (single
    quote, backtick, semicolon, SQL comment marker, Unicode) -- confirmed live via
    `RealUCClient.set_table_comment`/`get_table` round-trips, not by reasoning
    about the SQL standard alone (a bare `SELECT '...'` literal parses these same
    inputs differently on this warehouse, which is why the probe went through the
    actual DDL code path rather than a `SELECT`).
    """
    escaped = str(value).replace("\\", "\\\\").replace("'", "''")
    return "'" + escaped + "'"


def kv_clause(mapping: Mapping[str, str]) -> str:
    """Render a `{key: value}` mapping as the `'key' = 'value', ...` clause
    `SET TBLPROPERTIES (...)` and `SET TAGS (...)` both expect."""
    return ", ".join(f"{quote_literal(k)} = {quote_literal(v)}" for k, v in mapping.items())


def render_sql_value(value: Any) -> str:
    """Render one Python value as a SQL literal for an `INSERT ... VALUES`
    tuple (`insert_rows`' one caller, `build_insert_sql`, below).

    `None` -> `NULL`. `bool` -> `TRUE`/`FALSE`, checked before `int` because
    `bool` is an `int` subclass in Python and would otherwise render as `0`/
    `1`. `int`/`float` -> the number itself, unquoted. `datetime` -> a quoted
    `TIMESTAMP` literal via its ISO 8601 string. Anything else -> `str(value)`
    through `quote_literal`, reusing this module's own escaping -- including
    the live-confirmed backslash-doubling `quote_literal`'s own docstring
    describes, so a value written through `insert_rows` gets that fix for
    free rather than needing a second, unescaped string-building path.
    """
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, datetime):
        return f"TIMESTAMP {quote_literal(value.isoformat())}"
    return quote_literal(str(value))


def build_insert_sql(full_name: str, rows: List[Mapping[str, Any]]) -> str:
    """Build one multi-row `INSERT INTO <full_name> (<columns>) VALUES (...),
    (...)` statement -- the SQL-building code `insert_rows` on both
    `RealUCClient` and `FakeUCClient` share, so a planned/executed statement
    can never silently diverge into two implementations (the same discipline
    `_build_write_steps` in `apply.py` uses for its writes).

    Precondition: `full_name` is a three-part name; `rows` is non-empty and
    every row has exactly the same set of keys -- raises `ValueError` naming
    the mismatch otherwise, since a caller passing rows with different shapes
    would otherwise produce a statement whose columns silently don't line up
    with its values row to row.
    """
    require_three_part_name(full_name)
    if not rows:
        raise ValueError("rows must not be empty")
    columns = list(rows[0].keys())
    expected_keys = set(columns)
    for row in rows:
        if set(row.keys()) != expected_keys:
            raise ValueError(
                f"every row passed to insert_rows must have the same columns; "
                f"expected {sorted(expected_keys)}, got {sorted(row.keys())}"
            )
    column_clause = ", ".join(quote_ident(column) for column in columns)
    values_clauses = [
        "(" + ", ".join(render_sql_value(row[column]) for column in columns) + ")" for row in rows
    ]
    return f"INSERT INTO {quote_full_name(full_name)} ({column_clause}) VALUES " + ", ".join(values_clauses)


# Polling budget for a write/read whose warehouse is still cold-starting. A serverless
# 2X-Small warehouse can take longer than a single `wait_timeout` to spin up on a cold
# first query; a bounded poll loop below covers that without either failing spuriously
# or hanging forever if the warehouse is genuinely stuck.
_STATEMENT_WAIT_TIMEOUT = "30s"
_STATEMENT_POLL_INTERVAL_SECONDS = 2
_STATEMENT_MAX_WAIT_SECONDS = 120


class RealUCClient:
    """Thin translation layer over `databricks-sdk`'s `WorkspaceClient`, implementing
    `UCClient` against the real Free Edition workspace.

    Reads go through `WorkspaceClient().tables.get(full_name=...)` (`TablesAPI.get`,
    verified against the live workspace on 2026-09-17) for columns/comment/properties,
    plus two `information_schema.table_tags` / `information_schema.column_tags`
    queries for tags -- `TablesAPI.get`'s response has no tags field at all, which is
    not documented anywhere obvious and was only found by calling the live API (see
    this phase's report for the full list of such surprises). `sample_rows` also goes
    through statement execution (`SELECT * FROM <table> LIMIT <n>`): the API's default
    `JSON_ARRAY` result format renders every cell as a string regardless of its SQL
    type (verified live), which is why `UCClient.sample_rows`'s postcondition
    documents string values rather than driver-native Python types.

    Writes go through `WorkspaceClient().statement_execution.execute_statement(...)`
    against `warehouse_id` and emit real DDL (`COMMENT ON TABLE/COLUMN`, `ALTER TABLE
    ... SET TBLPROPERTIES`, `ALTER TABLE ... SET TAGS`) rather than a metadata-only
    REST PATCH: a full-replace PATCH would be dangerous here, because
    `tables.get(...).properties` is dominated by Delta/statistics-internal keys
    (`spark.sql.statistics.*`, `delta.*`) that Unity Catalog itself manages, and a
    naive "set properties to exactly this dict" call would silently drop them.
    `SET TBLPROPERTIES`/`SET TAGS` merge into the existing map instead, which is also
    what makes re-running the same write idempotent in effect.

    Auth: `WorkspaceClient(profile=profile)` resolves host and a short-lived OAuth
    token from `~/.databrickscfg` / the OS keychain. No token or host is hard-coded
    beyond the documented `DEFAULT_UC_PROFILE`/`DEFAULT_WAREHOUSE_ID` module
    constants, and no PAT is used anywhere.
    """

    def __init__(
        self,
        profile: str = DEFAULT_UC_PROFILE,
        warehouse_id: str = DEFAULT_WAREHOUSE_ID,
    ) -> None:
        # Imported lazily so importing this module (e.g. from fake-only unit tests)
        # never requires `databricks-sdk` to be installed or a network to exist.
        from databricks.sdk import WorkspaceClient

        self._workspace = WorkspaceClient(profile=profile)
        self._warehouse_id = warehouse_id

    # ---- reads -----------------------------------------------------------------

    def get_table(self, full_name: str) -> UCTable:
        require_three_part_name(full_name)
        from databricks.sdk.errors import NotFound

        try:
            table = self._workspace.tables.get(full_name=full_name)
        except NotFound as exc:
            raise UCTableNotFoundError(f"no table found at {full_name!r}") from exc

        table_tags = self._read_table_tags(full_name)
        column_tags = self._read_column_tags(full_name)
        columns = [
            UCColumn(
                name=column.name,
                data_type=column.type_text,
                nullable=bool(column.nullable),
                position=column.position if column.position is not None else index,
                partition_key=column.partition_index is not None,
                comment=column.comment,
                tags=column_tags.get(column.name, {}),
            )
            for index, column in enumerate(table.columns or [])
        ]
        return UCTable(
            full_name=table.full_name or full_name,
            comment=table.comment,
            columns=columns,
            properties=dict(table.properties or {}),
            tags=table_tags,
        )

    def _read_table_tags(self, full_name: str) -> Dict[str, str]:
        catalog, schema, table = full_name.split(".")
        sql = (
            f"SELECT tag_name, tag_value FROM {quote_ident(catalog)}.information_schema.table_tags "
            f"WHERE catalog_name = {quote_literal(catalog)} AND schema_name = {quote_literal(schema)} "
            f"AND table_name = {quote_literal(table)}"
        )
        rows = self._run_query(sql)
        return {tag_name: tag_value for tag_name, tag_value in rows}

    def _read_column_tags(self, full_name: str) -> Dict[str, Dict[str, str]]:
        catalog, schema, table = full_name.split(".")
        sql = (
            f"SELECT column_name, tag_name, tag_value FROM "
            f"{quote_ident(catalog)}.information_schema.column_tags "
            f"WHERE catalog_name = {quote_literal(catalog)} AND schema_name = {quote_literal(schema)} "
            f"AND table_name = {quote_literal(table)}"
        )
        rows = self._run_query(sql)
        result: Dict[str, Dict[str, str]] = {}
        for column_name, tag_name, tag_value in rows:
            result.setdefault(column_name, {})[tag_name] = tag_value
        return result

    def sample_rows(self, full_name: str, limit: int = 5) -> List[Dict[str, Any]]:
        require_three_part_name(full_name)
        if limit <= 0:
            raise ValueError(f"limit must be a positive integer, got {limit!r}")
        sql = f"SELECT * FROM {quote_full_name(full_name)} LIMIT {int(limit)}"
        response = self._run_read_statement(sql)
        schema = response.manifest.schema if response.manifest is not None else None
        columns = schema.columns if schema is not None else None
        if not columns or response.result is None or response.result.data_array is None:
            return []
        column_names = [column.name for column in columns]
        return [dict(zip(column_names, row)) for row in response.result.data_array]

    # ---- writes ------------------------------------------------------------------

    def set_table_comment(self, full_name: str, comment: str, *, dry_run: bool = False) -> str:
        require_three_part_name(full_name)
        sql = f"COMMENT ON TABLE {quote_full_name(full_name)} IS {quote_literal(comment)}"
        if dry_run:
            return sql
        self._run_statement(sql)
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
        self._run_statement(sql)
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
        self._run_statement(sql)
        return sql

    def set_table_tags(self, full_name: str, tags: Mapping[str, str], *, dry_run: bool = False) -> str:
        require_three_part_name(full_name)
        if not tags:
            raise ValueError("tags must not be empty")
        sql = f"ALTER TABLE {quote_full_name(full_name)} SET TAGS ({kv_clause(tags)})"
        if dry_run:
            return sql
        self._run_statement(sql)
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
        self._run_statement(sql)
        return sql

    def insert_rows(self, full_name: str, rows: List[Mapping[str, Any]], *, dry_run: bool = False) -> str:
        sql = build_insert_sql(full_name, rows)
        if dry_run:
            return sql
        self._run_statement(sql)
        return sql

    def create_catalog(self, name: str, comment: Optional[str] = None, *, dry_run: bool = False) -> str:
        require_single_part_name(name)
        sql = f"CREATE CATALOG IF NOT EXISTS {quote_ident(name)}"
        if comment is not None:
            sql += f" COMMENT {quote_literal(comment)}"
        if dry_run:
            return sql
        self._run_statement(sql)
        return sql

    def create_schema(self, catalog_name: str, schema_name: str, *, dry_run: bool = False) -> str:
        require_single_part_name(catalog_name)
        require_single_part_name(schema_name)
        sql = f"CREATE SCHEMA IF NOT EXISTS {quote_ident(catalog_name)}.{quote_ident(schema_name)}"
        if dry_run:
            return sql
        self._run_statement(sql)
        return sql

    def set_catalog_tags(self, catalog_name: str, tags: Mapping[str, str], *, dry_run: bool = False) -> str:
        require_single_part_name(catalog_name)
        if not tags:
            raise ValueError("tags must not be empty")
        sql = f"ALTER CATALOG {quote_ident(catalog_name)} SET TAGS ({kv_clause(tags)})"
        if dry_run:
            return sql
        self._run_statement(sql)
        return sql

    # ---- statement execution plumbing --------------------------------------------

    def _run_statement(self, sql: str) -> None:
        """Execute DDL that returns no rows. Raises `UCWriteError` on failure."""
        response = self._execute_and_await(sql)
        if response.status.state.value != "SUCCEEDED":
            raise UCWriteError(
                f"{sql!r} did not succeed (state={response.status.state}): {response.status.error}"
            )

    def _run_read_statement(self, sql: str):
        """Execute a read-only statement and return its raw terminal-state response,
        columns and all -- shared by `_run_query` (rows only) and `sample_rows`
        (rows plus column names). Raises `UCReadError` on failure."""
        response = self._execute_and_await(sql)
        if response.status.state.value != "SUCCEEDED":
            raise UCReadError(
                f"{sql!r} did not succeed (state={response.status.state}): {response.status.error}"
            )
        return response

    def _run_query(self, sql: str) -> List[tuple]:
        """Execute a `SELECT` and return its rows. Raises `UCReadError` on failure."""
        response = self._run_read_statement(sql)
        if response.result is None or response.result.data_array is None:
            return []
        return response.result.data_array

    def _execute_and_await(self, sql: str):
        """Run `sql` on the configured warehouse and poll until it reaches a
        terminal state, covering a warehouse that is still cold-starting."""
        import time

        from databricks.sdk.service.sql import StatementState

        response = self._workspace.statement_execution.execute_statement(
            statement=sql,
            warehouse_id=self._warehouse_id,
            wait_timeout=_STATEMENT_WAIT_TIMEOUT,
        )
        elapsed = 0
        while response.status.state in (StatementState.PENDING, StatementState.RUNNING):
            if elapsed >= _STATEMENT_MAX_WAIT_SECONDS:
                raise UCWriteError(
                    f"statement {response.statement_id!r} ({sql!r}) did not reach a "
                    f"terminal state within {_STATEMENT_MAX_WAIT_SECONDS}s"
                )
            time.sleep(_STATEMENT_POLL_INTERVAL_SECONDS)
            elapsed += _STATEMENT_POLL_INTERVAL_SECONDS
            response = self._workspace.statement_execution.get_statement(response.statement_id)
        return response

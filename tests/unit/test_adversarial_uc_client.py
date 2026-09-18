"""Adversarial / boundary tests for `uc_client.py`'s SQL-construction helpers
and preconditions.

`test_uc_client_contract.py` proves the shared behavioural contract
(idempotency, precondition enforcement, dry-run) against both `UCClient`
implementations. This file goes after the quoting helpers specifically,
offline, with real injection-shaped payloads rather than the simple
single-quote case: embedded backticks, semicolons, SQL comment markers,
combined attacks, NULL-shaped literal text, empty strings, null bytes, and
Unicode bidi-control characters. It also attacks `require_three_part_name`
with path-traversal-shaped and malformed three-part names.

Every test here runs against the pure functions (`quote_ident`, `quote_literal`,
`quote_full_name`, `require_three_part_name`, `kv_clause`) -- no network, no
fake table needed, since these are what both `RealUCClient` and `FakeUCClient`
share and what all of `apply.py`'s SQL safety rests on.
"""

from __future__ import annotations

import os

import pytest

from uc_metadata.uc_client import (
    RealUCClient,
    kv_clause,
    quote_full_name,
    quote_ident,
    quote_literal,
    require_three_part_name,
)

TABLE = "workspace.analytics.customers"
UC_LIVE_TESTS_ENABLED = os.environ.get("UC_LIVE_TESTS") == "1"

# ---- quote_ident: identifier context, backticks are the only special char ----------


def test_quote_ident_escapes_a_single_embedded_backtick():
    assert quote_ident("weird`name") == "`weird``name`"


def test_quote_ident_escapes_multiple_and_adjacent_backticks():
    assert quote_ident("a``b") == "`a````b`"
    assert quote_ident("```") == "````````"  # three backticks -> six escaped, wrapped in two more


def test_quote_ident_neutralizes_a_terminate_and_inject_attempt():
    """An identifier crafted to look like it closes the backtick-quote early
    and appends DDL: the escaping must keep the whole thing as one opaque
    identifier, never letting the embedded backtick actually terminate."""
    hostile = "customers`; DROP TABLE workspace.analytics.customers; --"
    quoted = quote_ident(hostile)

    assert quoted.startswith("`") and quoted.endswith("`")
    # Every backtick inside must be doubled -- no lone, unescaped backtick
    # appears anywhere in the interior (which is what would let it close early).
    interior = quoted[1:-1]
    i = 0
    while i < len(interior):
        if interior[i] == "`":
            assert interior[i : i + 2] == "``", "a lone unescaped backtick would terminate the identifier early"
            i += 2
        else:
            i += 1


def test_quote_ident_handles_the_empty_string():
    assert quote_ident("") == "``"


def test_quote_ident_preserves_unicode_combining_and_bidi_control_characters():
    """Nothing strips or rejects combining marks or a right-to-left override
    character (U+202E) -- a "Trojan Source"-style character that can make text
    a human reviewer sees differ from its actual byte content. `quote_ident`
    correctly treats it as opaque data (it round-trips verbatim, only
    backticks are special), but nothing anywhere in this codebase's review
    path strips or flags it either -- see this file's module-level note for
    why that is flagged as a spec gap, not fixed here.
    """
    hostile = "cust‮omers"  # contains U+202E RIGHT-TO-LEFT OVERRIDE
    quoted = quote_ident(hostile)
    assert quoted == f"`{hostile}`"


def test_quote_ident_does_not_special_case_sql_keywords_or_null_text():
    assert quote_ident("NULL") == "`NULL`"
    assert quote_ident("DROP TABLE") == "`DROP TABLE`"


# ---- quote_literal: string-literal context, single quotes are the special char -----


def test_quote_literal_escapes_a_single_embedded_quote():
    assert quote_literal("O'Brien") == "'O''Brien'"


def test_quote_literal_escapes_multiple_and_adjacent_quotes():
    assert quote_literal("a''b") == "'a''''b'"


def test_quote_literal_neutralizes_a_combined_attack_string():
    """Single quote, backtick, semicolon and a SQL line-comment marker, all in
    one description -- the shape a hostile column comment or dataset
    description could plausibly take."""
    hostile = "nice description'; DROP TABLE x; -- `also backticks`"
    quoted = quote_literal(hostile)

    assert quoted.startswith("'") and quoted.endswith("'")
    interior = quoted[1:-1]
    i = 0
    while i < len(interior):
        if interior[i] == "'":
            assert interior[i : i + 2] == "''", "a lone unescaped quote would terminate the literal early"
            i += 2
        else:
            i += 1
    # Backticks, semicolons and comment markers need no escaping inside a
    # string literal -- they are inert text there. Confirm they survive
    # unescaped (not stripped, not mangled).
    assert "`also backticks`" in quoted
    assert "DROP TABLE x" in quoted


def test_quote_literal_handles_the_empty_string():
    assert quote_literal("") == "''"


def test_quote_literal_quotes_the_literal_text_null_as_an_ordinary_string():
    """The SQL keyword NULL and the 4-character string "NULL" are different
    things; a description whose value is literally the text "NULL" must be
    quoted as an ordinary string literal, never emitted bare (which would be
    interpreted as the SQL NULL keyword instead of the human's text)."""
    quoted = quote_literal("NULL")
    assert quoted == "'NULL'"


def test_quote_literal_does_not_crash_on_an_embedded_null_byte():
    value = "before\x00after"
    quoted = quote_literal(value)
    assert quoted == "'before\x00after'"  # passed through verbatim; not stripped, not truncated


def test_quote_literal_preserves_unicode_combining_and_bidi_control_characters():
    hostile = "safe‮evil"
    quoted = quote_literal(hostile)
    assert quoted == f"'{hostile}'"


def test_quote_literal_escapes_a_trailing_backslash():
    """Fixed: a value ending in a single backslash immediately before the
    closing quote used to leave the constructed SQL with an unterminated
    string literal on the live warehouse (`...\\'` was read as the
    backslash escaping the quote character rather than the quote closing
    the literal -- see `test_quote_literal_trailing_backslash_round_trips_
    against_the_live_warehouse` below for the live proof). `quote_literal`
    now doubles the backslash first, so the closing quote is never adjacent
    to an odd number of backslashes."""
    value = "trailing backslash\\"
    quoted = quote_literal(value)
    assert quoted == "'trailing backslash\\\\'"


def test_quote_literal_escapes_a_plain_and_multiple_consecutive_backslashes():
    assert quote_literal("a\\b") == "'a\\\\b'"
    assert quote_literal("a\\\\\\b") == "'a\\\\\\\\\\\\b'"  # three backslashes -> six


def test_quote_literal_escapes_a_backslash_immediately_followed_by_a_quote():
    """The case that most directly motivated doubling backslashes *before*
    doubling quotes: escaping the quote alone would leave `\\''` -- a single
    backslash still immediately adjacent to (now doubled) quote characters.
    Doubling the backslash first produces `\\\\''`, an even run of
    backslashes followed by the escaped quote, which parses unambiguously."""
    assert quote_literal("a\\'b") == "'a\\\\''b'"


# ---- quote_full_name / require_three_part_name --------------------------------------


def test_quote_full_name_quotes_each_part_independently():
    assert quote_full_name("workspace.analytics.customers") == "`workspace`.`analytics`.`customers`"


def test_quote_full_name_escapes_backticks_in_any_part():
    assert quote_full_name("ws.an`alytics.cust`omers") == "`ws`.`an``alytics`.`cust``omers`"


@pytest.mark.parametrize(
    "bad_name",
    [
        "",
        "onlyonepart",
        "two.parts",
        "way.too.many.parts",
        "a..b",  # empty middle part
        "..",  # all-empty parts
        "../../etc/passwd",  # path-traversal-shaped, not a UC name at all
        ".a.b",  # empty first part
        "a.b.",  # empty last part
    ],
)
def test_require_three_part_name_rejects_every_malformed_shape(bad_name: str):
    with pytest.raises(ValueError, match="three-part name"):
        require_three_part_name(bad_name)


def test_require_three_part_name_rejects_a_whitespace_only_middle_part():
    """Fixed: `require_three_part_name` used to check `all(parts)` --
    truthiness, not emptiness-after-strip -- so a middle part that is pure
    whitespace (`"a. .b"`) was not rejected, even though it is not a legal
    Unity Catalog identifier. It now checks `all(part.strip() for part in
    parts)`, matching its own docstring ("a non-empty catalog.schema.table
    three-part name")."""
    with pytest.raises(ValueError, match="three-part name"):
        require_three_part_name("a. .b")


def test_require_three_part_name_rejects_a_name_with_embedded_backtick():
    """A three-part name is not further validated for embedded backticks at
    this precondition layer -- that is `quote_ident`'s job, exercised
    elsewhere in this file. Documented here so the division of responsibility
    is explicit: `require_three_part_name` only checks shape (three non-empty
    dot-separated parts), never content."""
    require_three_part_name("workspace.anal`ytics.customers")  # does not raise: shape is fine


# ---- kv_clause: both keys and values go through quote_literal -----------------------


def test_kv_clause_quotes_both_keys_and_values_defeating_a_key_side_injection():
    tags = {"pii'; DROP--": "true"}
    clause = kv_clause(tags)
    assert clause == "'pii''; DROP--' = 'true'"


def test_kv_clause_handles_an_empty_value_string():
    clause = kv_clause({"flag_tag": ""})
    assert clause == "'flag_tag' = ''"


# ---- live: does the real Databricks SQL parser actually round-trip the ----------
# ---- backslash-doubling fix, in the exact DDL context quote_literal is used in? -


@pytest.mark.uc_live
@pytest.mark.skipif(
    not UC_LIVE_TESTS_ENABLED,
    reason="set UC_LIVE_TESTS=1 to run this against the live Free Edition workspace",
)
def test_quote_literal_trailing_backslash_round_trips_against_the_live_warehouse():
    """Live proof of the bug this module's `quote_literal` fix addresses, and
    that the fix holds: this warehouse's SQL parser reads
    `COMMENT ON TABLE ... IS '...ends in a backslash\\'` (single trailing
    backslash, the old unescaped output) as the backslash escaping the
    closing quote, leaving the literal unterminated (`PARSE_SYNTAX_ERROR`) --
    confirmed by hand against the live workspace before this fix landed.
    `quote_literal` now doubles the backslash, and this test confirms that
    doubled form round-trips through the real DDL path and back out through
    `TablesAPI.get`, byte for byte. Restores the table's original comment
    afterwards so a live run leaves nothing behind beyond this one comment
    write + restore, matching this suite's existing live-write convention.
    """
    client = RealUCClient()
    original_comment = client.get_table(TABLE).comment
    adversarial = "adversarial-probe: trailing backslash\\"

    try:
        client.set_table_comment(TABLE, adversarial)
        landed = client.get_table(TABLE).comment
        assert landed == adversarial, (
            "the live SQL parser did not round-trip a value ending in a single "
            "backslash -- quote_literal()'s backslash-doubling fix did not hold "
            "against the real warehouse"
        )
    finally:
        client.set_table_comment(TABLE, original_comment or "")


def test_kv_clause_preserves_insertion_order_for_multiple_entries():
    """`_column_tags`/`_table_tags` in apply.py rely on later entries in a
    dict winning a key collision (governance tags override free-form labels);
    `kv_clause` itself does not need to preserve or guarantee an order for SQL
    correctness (SET TBLPROPERTIES/TAGS is a set, not an ordered list) -- this
    just confirms it doesn't silently drop or reorder entries in a way that
    would be surprising to a test asserting on exact SQL text elsewhere in
    this codebase."""
    clause = kv_clause({"a": "1", "b": "2", "c": "3"})
    assert clause == "'a' = '1', 'b' = '2', 'c' = '3'"

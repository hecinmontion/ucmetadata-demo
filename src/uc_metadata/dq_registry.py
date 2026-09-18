"""A small stand-in data-quality rule registry (Glossary: none named directly, but
this is "the data-quality rule registry" the Data table's "Quality-rule coverage per
dataset/column" row reads from).

`load_dq_registry()` reads `dq_registry.yaml` -- one rule per row: a target table, a
human description, and a predicate every row is expected to satisfy.
`evaluate_rules(full_name, client)` runs every rule registered for `full_name`
against `client` and returns one `DQRuleResult` per rule: pass/fail, and for a
failing rule, how many rows violate it.

The one design decision worth stating rather than leaving implicit: a rule's
predicate is evaluated the *same way* against `FakeUCClient` and `RealUCClient`,
because both expose `sample_rows(full_name, limit=...)` returning `{column: value}`
row dicts with string-rendered values (`uc_client.UCClient`'s own documented
postcondition), and this module reads through that seam rather than through raw SQL
execution -- `UCClient` has no "run this predicate" method, and adding one just for
this would be a second write-shaped hole in a read-only seam. The predicate string
in `dq_registry.yaml` is interpreted in Python by `_predicate_holds` below, once, for
both backends, so there is exactly one rule language rather than a SQL dialect that
only `RealUCClient` understands and a hand-written Python check that only the fake
does. The trade-off, named rather than hidden: the predicate grammar this module's
interpreter understands is deliberately small (see `_predicate_holds`'s docstring),
and `evaluate_rules` pulls every row up to `_EVALUATION_ROW_LIMIT` into memory to
check it -- an honest stand-in at this prototype's scale (Non-functional
Requirements: "2-3 contracts, ~10-40 columns each"), not a real streaming
data-quality engine (Out of Scope: "A data-quality engine ... no rule execution
[invented] from scratch" -- this module is exactly that named exception, in scope,
kept deliberately light).
"""

from __future__ import annotations

import operator
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Union

import yaml

from uc_metadata.uc_client import UCClient

# dq_registry.yaml at the repository root, resolved relative to this file so it
# works regardless of the caller's working directory (same pattern as
# `models.SCHEMA_PATH` / `glossary.GLOSSARY_PATH`).
DQ_REGISTRY_PATH = Path(__file__).resolve().parents[2] / "dq_registry.yaml"

# Cap on rows pulled per rule evaluation. Generous relative to every seeded demo
# table (6-10 rows) without pretending this is a streaming engine that could
# check a production-scale table this way -- see this module's docstring.
_EVALUATION_ROW_LIMIT = 10_000


@dataclass(frozen=True)
class DQRule:
    """One rule from `dq_registry.yaml`: which table it applies to, a
    human-readable description, and the predicate every row must satisfy."""

    id: str
    full_name: str
    description: str
    predicate: str


@dataclass(frozen=True)
class DQRuleResult:
    """One rule's outcome against a live (or fake) table's current rows.

    `violation_count` is always populated (0 when `passed`), rather than only
    on failure, since it is cheap to compute alongside `passed` in this
    prototype's row-in-memory evaluation -- the "real signal for the
    adversarial demo, not just a bare boolean" this phase asks for.
    """

    rule_id: str
    full_name: str
    description: str
    passed: bool
    rows_checked: int
    violation_count: int


def load_dq_registry(path: Optional[Union[str, Path]] = None) -> List[DQRule]:
    """Load every rule from `dq_registry.yaml` (or `path`, if given).

    Precondition: `path` (or the default `dq_registry.yaml`) is a YAML file
    containing a top-level `rules` list, each entry with non-empty `id`,
    `full_name`, `description` and `predicate` strings. Postcondition: returns
    one `DQRule` per entry, in file order; raises `ValueError` naming the
    problem if the file is missing that shape -- a caller should never
    silently get an empty or malformed registry instead of a loud failure.
    """
    resolved_path = Path(path) if path is not None else DQ_REGISTRY_PATH
    raw = yaml.safe_load(resolved_path.read_text())
    if not isinstance(raw, dict) or not isinstance(raw.get("rules"), list):
        raise ValueError(f"{resolved_path}: expected a YAML mapping with a top-level 'rules' list")

    rules: List[DQRule] = []
    for index, entry in enumerate(raw["rules"]):
        if not isinstance(entry, dict):
            raise ValueError(f"{resolved_path}: rules[{index}] must be a mapping, got {type(entry).__name__}")
        rules.append(_rule_from_entry(resolved_path, index, entry))
    return rules


def _rule_from_entry(path: Path, index: int, entry: Dict[str, Any]) -> DQRule:
    for field_name in ("id", "full_name", "description", "predicate"):
        value = entry.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{path}: rules[{index}].{field_name} must be a non-empty string")
    return DQRule(
        id=entry["id"],
        full_name=entry["full_name"],
        description=entry["description"],
        predicate=entry["predicate"],
    )


def rules_for_table(full_name: str, rules: Optional[List[DQRule]] = None) -> List[DQRule]:
    """The subset of `rules` (or the full loaded registry, if `rules` is
    omitted) registered against `full_name`, in registry order.

    Cheap and client-free on purpose: "does this dataset have at least one
    quality rule attached" (a fill-rate question `coverage.py` asks) needs
    only this lookup, never a live table read.
    """
    all_rules = rules if rules is not None else load_dq_registry()
    return [rule for rule in all_rules if rule.full_name == full_name]


def evaluate_rule(rule: DQRule, client: UCClient) -> DQRuleResult:
    """Run one rule's predicate against every row `client` currently reports
    for `rule.full_name`.

    Precondition: `rule.full_name` names a table `client` can resolve
    (`client.sample_rows` raises `UCTableNotFoundError` otherwise, the same
    contract every other `UCClient` read makes). Postcondition: `passed` is
    `True` iff every row read satisfies `rule.predicate`; `violation_count`
    names exactly how many did not, out of `rows_checked` rows read (never a
    guess or an estimate at this prototype's scale).
    """
    rows = client.sample_rows(rule.full_name, limit=_EVALUATION_ROW_LIMIT)
    violation_count = sum(1 for row in rows if not _predicate_holds(rule.predicate, row))
    return DQRuleResult(
        rule_id=rule.id,
        full_name=rule.full_name,
        description=rule.description,
        passed=violation_count == 0,
        rows_checked=len(rows),
        violation_count=violation_count,
    )


def evaluate_rules(
    full_name: str, client: UCClient, rules: Optional[List[DQRule]] = None
) -> List[DQRuleResult]:
    """Evaluate every rule registered for `full_name` against `client`.

    Precondition: `full_name` is a `catalog.schema.table` three-part name.
    Postcondition: returns one `DQRuleResult` per rule registered for
    `full_name` (via `rules_for_table`), in registry order; returns `[]` if no
    rule is registered for this table -- never raises for "no rules defined",
    the same "empty, not an error" convention `release_log.read_release_log`
    uses for "nothing published yet".
    """
    return [evaluate_rule(rule, client) for rule in rules_for_table(full_name, rules)]


# ---- predicate interpreter --------------------------------------------------------
#
# One small, safe interpreter for the grammar described in dq_registry.yaml's own
# header comment: `clause (AND clause)*`, where a clause is either
# `<column> IS [NOT] NULL` or `<column> <op> <value_or_column>`. Deliberately no OR,
# no parentheses, no nested expressions -- every rule this registry currently
# declares is a single comparison, and a bigger grammar is exactly the "invent a
# rule execution engine from scratch" Out of Scope already declines to build.

_IS_NOT_NULL_RE = re.compile(r"^(?P<col>[A-Za-z_][A-Za-z0-9_]*)\s+IS\s+NOT\s+NULL$", re.IGNORECASE)
_IS_NULL_RE = re.compile(r"^(?P<col>[A-Za-z_][A-Za-z0-9_]*)\s+IS\s+NULL$", re.IGNORECASE)
_COMPARISON_RE = re.compile(
    r"^(?P<lhs>[A-Za-z_][A-Za-z0-9_]*)\s*(?P<op>>=|<=|!=|=|>|<)\s*"
    r"(?P<rhs>'[^']*'|-?\d+(?:\.\d+)?|[A-Za-z_][A-Za-z0-9_]*)$"
)
_NUMBER_RE = re.compile(r"^-?\d+(?:\.\d+)?$")

_COMPARISON_OPS: Dict[str, Callable[[Any, Any], bool]] = {
    ">=": operator.ge,
    "<=": operator.le,
    "!=": operator.ne,
    "=": operator.eq,
    ">": operator.gt,
    "<": operator.lt,
}


def _predicate_holds(predicate: str, row: Mapping[str, Any]) -> bool:
    """`True` iff `row` satisfies every `AND`-joined clause in `predicate`.

    Precondition: `predicate` matches the grammar this module's docstring
    describes -- one or more clauses joined by the literal word `AND`
    (case-insensitive), each an `IS [NOT] NULL` check or a two-operand
    comparison. Raises `ValueError` naming the offending clause if a clause
    matches neither shape, rather than silently treating an unsupported
    predicate as always-true.
    """
    clauses = [clause.strip() for clause in re.split(r"\bAND\b", predicate, flags=re.IGNORECASE)]
    return all(_clause_holds(clause, row) for clause in clauses)


def _clause_holds(clause: str, row: Mapping[str, Any]) -> bool:
    is_not_null = _IS_NOT_NULL_RE.match(clause)
    if is_not_null:
        return row.get(is_not_null.group("col")) is not None

    is_null = _IS_NULL_RE.match(clause)
    if is_null:
        return row.get(is_null.group("col")) is None

    comparison = _COMPARISON_RE.match(clause)
    if not comparison:
        raise ValueError(f"dq_registry: unsupported predicate clause: {clause!r}")

    lhs = _resolve_operand(comparison.group("lhs"), row)
    rhs = _resolve_operand(comparison.group("rhs"), row)
    if lhs is None or rhs is None:
        # SQL's three-valued logic would make a NULL comparison UNKNOWN (excluded
        # from a `WHERE NOT (...)` violation count, not counted either way). This
        # light interpreter simplifies that to "does not hold" -- a NULL operand
        # counts as a violation of a non-null-check comparison -- documented here
        # as a deliberate simplification, not rediscovered by a reader later.
        return False
    return _COMPARISON_OPS[comparison.group("op")](lhs, rhs)


def _resolve_operand(token: str, row: Mapping[str, Any]) -> Any:
    """Resolve one comparison operand: a quoted string literal, a numeric
    literal, or a column reference into `row` -- in that order, matching the
    grammar `dq_registry.yaml`'s rules actually use (`budget >= 0`,
    `end_date >= start_date`)."""
    if len(token) >= 2 and token.startswith("'") and token.endswith("'"):
        return token[1:-1]
    if _NUMBER_RE.match(token):
        return float(token)
    return _coerce_scalar(row.get(token))


def _coerce_scalar(raw: Any) -> Any:
    """Coerce one row value for comparison: numeric-looking strings become
    `float` (so `'-500.00' >= 0` compares numerically, not lexically); anything
    else -- including `None` and ISO-formatted date/timestamp strings, which
    sort correctly as plain strings -- is left as-is."""
    if raw is None or isinstance(raw, (int, float)):
        return raw
    text = str(raw)
    if _NUMBER_RE.match(text):
        return float(text)
    return text

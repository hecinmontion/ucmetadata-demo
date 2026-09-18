"""Adversarial / boundary tests for `owner_registry.py`, `dq_registry.py`,
`change_routing.py` and the `cli.py` argument surface.

Each of `test_dq_registry.py`/`test_change_routing.py` explicitly scopes
adversarial cases to this persona (module docstrings say so). This file
covers: a path-traversal-shaped business-application id (owner_registry, held
up fine), a malformed `dq_registry.yaml` and an unsupported predicate clause
(dq_registry, held up fine), a malformed `change_classes.yaml` (held up fine)
and -- the one genuine finding in this file -- a path-traversal-shaped changed
file path that the glob-to-regex matcher misclassifies as the fast content
path (change_routing, a real gap). It also covers CLI-level contract
violations: the `--in-place`/`-o` mutually exclusive group, a
shell-metacharacter-looking contract path, an extremely long CLI argument, and
a `KeyboardInterrupt` raised mid-write inside `apply()` -- which finds a
second, independent way to violate the same "exactly one ReleaseRecord is
published, never silently skipped" postcondition
`test_adversarial_validate_apply.py`'s disk-full test already found, this
time via `except Exception` not catching `BaseException`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from uc_metadata import cli
from uc_metadata.apply import apply
from uc_metadata.change_routing import classify_change
from uc_metadata.dq_registry import _predicate_holds, evaluate_rules, load_dq_registry
from uc_metadata.fake_uc import FakeUCClient
from uc_metadata.harvest import harvest
from uc_metadata.models import CertificationTier, Proposed, Refresh, Sensitivity
from uc_metadata.owner_registry import UnknownBusinessApplicationError, resolve_owner
from uc_metadata.release_log import read_release_log
from uc_metadata.uc_client import UCTableNotFoundError

TABLE = "workspace.analytics.customers"
KNOWN_BA_ID = "BA-10231"
APPROVER = "hector"


def _fully_reviewed_contract(client, full_name: str = TABLE):
    contract = harvest(
        full_name,
        client,
        KNOWN_BA_ID,
        description="Customer master records for the direct-to-consumer storefront.",
        refresh=Refresh(cadence="daily", sla_minutes=120),
        retention_days=730,
        certification=CertificationTier.SILVER,
    )
    reviewed_columns = [
        column.model_copy(
            update={
                "description": Proposed.accepted(f"{column.name} column."),
                "pii": Proposed.accepted(False),
                "sensitivity": Proposed.accepted(Sensitivity.INTERNAL),
            }
        )
        for column in contract.columns
    ]
    dataset = contract.dataset.model_copy(update={"sensitivity": Proposed.accepted(Sensitivity.INTERNAL)})
    return contract.model_copy(update={"dataset": dataset, "columns": reviewed_columns})


# ==== owner_registry.py ==============================================================


def test_resolve_owner_rejects_empty_string():
    with pytest.raises(ValueError):
        resolve_owner("")


def test_resolve_owner_on_a_path_traversal_shaped_id_raises_unknown_not_a_filesystem_error():
    """`_OWNER_REGISTRY` is a plain in-memory dict; `resolve_owner` performs no
    filesystem or path interpretation on `business_application_id` at all.
    A `../../etc/passwd`-shaped id (or any other injection-shaped string)
    simply fails an ordinary dict lookup and raises the documented
    `UnknownBusinessApplicationError`, naming the id verbatim -- confirmed
    here as a non-finding: there is no path-traversal surface in this module
    to attack."""
    hostile_id = "../../etc/passwd"
    with pytest.raises(UnknownBusinessApplicationError, match="no owner registered"):
        resolve_owner(hostile_id)


def test_resolve_owner_on_a_sql_injection_shaped_id_also_just_raises_unknown():
    hostile_id = "BA-10231'; DROP TABLE owners; --"
    with pytest.raises(UnknownBusinessApplicationError):
        resolve_owner(hostile_id)


def test_harvest_with_a_path_traversal_shaped_business_application_id_fails_fast(tmp_path: Path):
    """The same id, exercised through `harvest()` (the actual caller):
    `resolve_owner` is called before any table read, so this fails
    immediately with the same clean, named error -- never produces a
    contract with a bogus owner pointer."""
    client = FakeUCClient()
    with pytest.raises(UnknownBusinessApplicationError):
        harvest(TABLE, client, "../../etc/passwd")


# ==== dq_registry.py ===================================================================


def test_load_dq_registry_rejects_a_non_mapping_document_root(tmp_path: Path):
    path = tmp_path / "bad.yaml"
    path.write_text("- just\n- a\n- list\n")

    with pytest.raises(ValueError, match="expected a YAML mapping"):
        load_dq_registry(path)


def test_load_dq_registry_rejects_a_missing_rules_key(tmp_path: Path):
    path = tmp_path / "bad.yaml"
    path.write_text("not_rules: []\n")

    with pytest.raises(ValueError, match="top-level 'rules' list"):
        load_dq_registry(path)


def test_load_dq_registry_rejects_a_rule_entry_that_is_not_a_mapping(tmp_path: Path):
    path = tmp_path / "bad.yaml"
    path.write_text("rules:\n  - just a string\n")

    with pytest.raises(ValueError, match=r"rules\[0\] must be a mapping"):
        load_dq_registry(path)


@pytest.mark.parametrize("missing_field", ["id", "full_name", "description", "predicate"])
def test_load_dq_registry_rejects_a_rule_missing_any_required_field(tmp_path: Path, missing_field: str):
    entry = {"id": "r1", "full_name": TABLE, "description": "d", "predicate": "x IS NOT NULL"}
    del entry[missing_field]
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump({"rules": [entry]}))

    with pytest.raises(ValueError, match=f"rules\\[0\\].{missing_field} must be a non-empty string"):
        load_dq_registry(path)


def test_load_dq_registry_rejects_an_empty_string_field_not_just_a_missing_one(tmp_path: Path):
    entry = {"id": "", "full_name": TABLE, "description": "d", "predicate": "x IS NOT NULL"}
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump({"rules": [entry]}))

    with pytest.raises(ValueError, match=r"rules\[0\].id must be a non-empty string"):
        load_dq_registry(path)


def test_evaluate_rules_on_a_table_the_client_cannot_resolve_raises_not_found(tmp_path: Path):
    """Precondition, honoured: `rule.full_name` names a table `client` can
    resolve, or `UCTableNotFoundError` -- confirmed as a real, enforced
    precondition (this propagates from `client.sample_rows`, not silently
    swallowed into an empty/false result)."""
    entry = {"id": "r1", "full_name": "workspace.does.not_exist", "description": "d", "predicate": "x IS NOT NULL"}
    path = tmp_path / "reg.yaml"
    path.write_text(yaml.safe_dump({"rules": [entry]}))
    rules = load_dq_registry(path)

    with pytest.raises(UCTableNotFoundError):
        evaluate_rules("workspace.does.not_exist", FakeUCClient(), rules=rules)


def test_predicate_interpreter_raises_a_named_error_for_an_unsupported_clause():
    with pytest.raises(ValueError, match="unsupported predicate clause"):
        _predicate_holds("some_col LIKE '%x%'", {"some_col": "x"})


def test_predicate_interpreter_silently_misparses_an_or_joined_predicate_instead_of_rejecting_it():
    """Real finding, softer than the others in this file: the grammar is
    documented as `AND`-only ("no OR, no parentheses ... a bigger grammar is
    exactly the 'invent a rule execution engine from scratch' Out of Scope
    already declines to build"), which reads as a deliberate limitation a
    rule author should get a clear error against if they hit it. They don't.

    `_predicate_holds` only splits on `\\bAND\\b`; a clause with no `AND` at
    all is handed whole to `_COMPARISON_RE`, whose right-hand-side group is
    `.+` (greedy, matches everything to end of line). For `"a > 0 OR b > 0"`
    this makes `rhs` the literal 10-character string `"0 OR b > 0"` -- not
    rejected as malformed, just resolved as "not a quoted literal, not
    numeric, and no such column in the row" -> `None`, which
    `_clause_holds`'s own NULL-operand simplification then turns into "does
    not hold" for *every* row, silently. A DQ rule author who writes `OR`
    thinking it is supported (a reasonable assumption from `AND` being
    supported) gets a rule that always fails with a violation count equal to
    every row, and no error message anywhere pointing at `OR` as the actual
    problem -- exactly the class of failure `_predicate_holds`'s own
    docstring says it exists to avoid ("raises... rather than silently
    treating an unsupported predicate as always-true"); it does not raise
    here, and it is not "always-true", but "always-false-with-no-diagnostic"
    is not meaningfully safer for someone debugging a certification tier
    that mysteriously never earns its evidence.
    """
    row = {"a": "1", "b": "1"}  # would satisfy `a > 0 OR b > 0` under real OR semantics

    holds = _predicate_holds("a > 0 OR b > 0", row)

    assert holds is False  # no exception, no diagnostic -- just silently "does not hold"


def test_predicate_interpreter_treats_a_null_operand_as_a_violation_not_a_crash():
    """Documented simplification (dq_registry.py's own comment): a NULL
    operand in a non-null-check comparison counts as "does not hold" rather
    than SQL's three-valued UNKNOWN. Confirmed it does not raise or silently
    pass."""
    assert _predicate_holds("amount >= 0", {"amount": None}) is False


# ==== change_routing.py ================================================================


REPO_CHANGE_CLASSES_PATH = Path(__file__).resolve().parents[2] / "change_classes.yaml"


def test_classify_change_rejects_a_change_classes_yaml_with_a_non_mapping_root(tmp_path: Path):
    path = tmp_path / "change_classes.yaml"
    path.write_text("- just\n- a\n- list\n")

    with pytest.raises(ValueError, match="expected a YAML mapping"):
        classify_change(["contracts/foo.yaml"], path)


def test_classify_change_on_a_change_classes_yaml_with_no_declared_lists_fails_closed(tmp_path: Path):
    """An empty/near-empty declaration file still produces a usable classifier
    -- everything just falls into the "matches neither declared class" branch,
    which is documented to fail closed to `schema`. Confirms the fail-closed
    default holds even in this degenerate case, not just the populated one
    `test_change_routing.py` exercises."""
    path = tmp_path / "change_classes.yaml"
    path.write_text("{}\n")

    assert classify_change(["contracts/foo.yaml"], path) == "schema"


def test_classify_change_on_a_change_classes_yaml_missing_the_file_entirely(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        classify_change(["contracts/foo.yaml"], tmp_path / "does_not_exist.yaml")


def test_classify_change_rejects_a_nonempty_but_whitespace_only_path():
    """A changed-paths entry that is just whitespace matches no glob and
    correctly fails closed to `schema` rather than crashing on an empty
    pattern match -- confirmed, not a finding."""
    assert classify_change(["   "], REPO_CHANGE_CLASSES_PATH) == "schema"


def test_classify_change_path_traversal_shaped_path_is_misclassified_as_content():
    """Real finding: `_glob_to_regex` translates `contracts/**/*.yaml` into a
    plain regex over the literal path *string* -- it never normalizes `..`
    segments the way `os.path.normpath`/`pathlib.Path.resolve()` would. A
    changed path containing a literal `..` component that still happens to
    start with `contracts/` and end in `.yaml` textually matches the content
    glob and is routed to the fast, code-owners-only path, even though the
    same string also textually contains the platform-owned
    `src/uc_metadata/models.py` path segment `classify_change` would route to
    `schema` if it appeared as its own changed-path entry.

    Whether this is exploitable in production depends entirely on whether
    upstream `git diff --name-only` (this module's own stated precondition
    for what a caller passes in) can ever emit a path containing a literal
    `..` path component for a *tracked* file -- git itself resists creating
    such tree entries in normal use, which is why this is reported as a real,
    demonstrated gap in the classifier's own defence-in-depth rather than as
    a proven end-to-end exploit. A mechanical router whose entire job is a
    trust boundary (fast vs. slow review) arguably should not rely on an
    upstream tool's cooperation as its only defence against a crafted path.
    This test encodes the *safe* expectation (fail closed to schema for
    anything containing `..`) and is expected to fail against the current
    implementation.
    """
    hostile_path = "contracts/../../src/uc_metadata/models.py.yaml"

    classification = classify_change([hostile_path], REPO_CHANGE_CLASSES_PATH)

    assert classification == "schema", (
        f"expected a path containing '..' to fail closed to the slow path, "
        f"got {classification!r} for {hostile_path!r}"
    )


# ==== cli.py ============================================================================


def test_propose_rejects_in_place_and_output_together(tmp_path: Path, capsys):
    """`--in-place` and `-o/--output` are declared as a `required=True`
    mutually exclusive group (cli.py's `_add_propose_parser`) -- confirmed
    here that passing both really does raise argparse's `SystemExit(2)`
    rather than silently picking one, since this specific pairing is named
    explicitly in this phase's brief as something to verify, not assume."""
    contract_path = tmp_path / "c.yaml"
    contract_path.write_text("version: 1\n")  # content irrelevant; argparse fails before any file is read

    with pytest.raises(SystemExit) as exc_info:
        cli.main(["propose", str(contract_path), "--in-place", "-o", str(tmp_path / "out.yaml")])

    assert exc_info.value.code == 2
    assert "not allowed with argument" in capsys.readouterr().err


def test_propose_rejects_neither_in_place_nor_output(tmp_path: Path, capsys):
    """The mutually exclusive group is also `required=True` -- omitting both
    must fail too, not silently default to one of them."""
    contract_path = tmp_path / "c.yaml"
    contract_path.write_text("version: 1\n")

    with pytest.raises(SystemExit) as exc_info:
        cli.main(["propose", str(contract_path)])

    assert exc_info.value.code == 2


def test_apply_on_a_shell_metacharacter_looking_contract_path_fails_cleanly_not_a_traceback(capsys):
    """Never shelled out (`cli.py` uses `Path.read_text`/PyYAML directly, no
    subprocess), so a path that merely *looks* like a shell injection attempt
    is just an ordinary nonexistent-file path -- confirmed it produces the
    same clean, low-severity `Error: ...` + exit code 2 as any other missing
    file, via `_EXPECTED_ERRORS`, never a raw traceback and never any sign of
    the metacharacters being interpreted."""
    hostile_path = "$(rm -rf /); echo pwned; `id`.yaml"

    exit_code = cli.main(["apply", hostile_path, "--approved-by", APPROVER])

    assert exit_code == 2
    err = capsys.readouterr().err
    assert err.startswith("Error:")
    assert "Traceback" not in err


def test_harvest_with_an_extremely_long_full_name_argument_fails_cleanly_not_a_crash(tmp_path: Path, capsys):
    absurdly_long_name = "workspace.analytics." + ("x" * 100_000)

    exit_code = cli.main(
        ["harvest", absurdly_long_name, "--ba-id", KNOWN_BA_ID, "-o", str(tmp_path / "out.yaml")]
    )

    assert exit_code == 2
    err = capsys.readouterr().err
    assert err.startswith("Error:")
    assert "Traceback" not in err


def test_harvest_cadence_without_sla_minutes_is_rejected(tmp_path: Path, capsys):
    """`_parse_refresh`'s own stated precondition: both `--cadence` and
    `--sla-minutes`, or neither. Confirmed enforced, not just documented."""
    exit_code = cli.main(
        ["harvest", TABLE, "--ba-id", KNOWN_BA_ID, "--cadence", "daily", "-o", str(tmp_path / "out.yaml")]
    )

    assert exit_code == 2
    assert "must be given together" in capsys.readouterr().err


# ---- KeyboardInterrupt mid-write: a second route to the same lost-audit-trail gap ----


class _RaisesKeyboardInterruptOnSecondColumn(FakeUCClient):
    """`apply()`'s write loop is `except Exception as exc: ...` -- deliberate,
    per its own docstring, for ordinary write failures. `KeyboardInterrupt`
    (Ctrl-C) is a `BaseException`, not an `Exception` subclass, so it is not
    caught by that clause at all: it propagates immediately out of the loop,
    skipping every write after it *and* the `publish_release_record` call
    that would otherwise follow. This fake raises `KeyboardInterrupt` on the
    second column-comment write to land inside the loop, simulating an
    operator hitting Ctrl-C mid-apply.
    """

    def __init__(self) -> None:
        super().__init__()
        self._column_comment_calls = 0

    def set_column_comment(self, full_name: str, column_name: str, comment: str, *, dry_run: bool = False) -> str:
        if not dry_run:
            self._column_comment_calls += 1
            if self._column_comment_calls == 2:
                raise KeyboardInterrupt()
        return super().set_column_comment(full_name, column_name, comment, dry_run=dry_run)


def test_keyboard_interrupt_mid_apply_leaves_writes_landed_but_publishes_no_release_record(tmp_path: Path):
    """Confirms the interrupt is *worse* than the documented partial-failure
    path, not merely different: a write that raises an ordinary `Exception`
    mid-loop still gets `apply()` all the way to `publish_release_record`
    with a `PARTIAL_FAILURE` record naming exactly what landed
    (`test_apply_names_several_simultaneous_write_failures_precisely`,
    `test_apply.py`'s own `_FailOnColumnComment` test). A `KeyboardInterrupt`
    at the same point in the same loop gets none of that: whatever writes
    already landed (here: the table comment and the first column's comment)
    stay applied with no rollback, exactly one column's write is genuinely
    mid-flight/unknown, and *zero* release records are published for an
    apply attempt that demonstrably mutated the catalogue -- the same
    "exactly one ReleaseRecord ... never silently skipped" postcondition
    violation `test_adversarial_validate_apply.py`'s disk-full test found,
    reached here through the write loop's exception handling instead of
    through `publish_release_record` itself.
    """
    client = _RaisesKeyboardInterruptOnSecondColumn()
    contract = _fully_reviewed_contract(client)
    log_path = tmp_path / "release_log.jsonl"

    with pytest.raises(KeyboardInterrupt):
        apply(contract, client, approved_by=APPROVER, log_path=log_path)

    # The table comment (the first write) already landed.
    assert client.get_table(TABLE).comment == contract.dataset.description
    # ...but there is no release record at all for this apply attempt --
    # worse than the named PARTIAL_FAILURE case, which always gets one.
    assert read_release_log(log_path) == []

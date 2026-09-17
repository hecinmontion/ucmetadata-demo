"""The automated checks a change request runs (Glossary: none named here directly,
but this is "the automated checks" every Scenario refers to) -- the function the
provisioning and grant gates would call to get a machine-readable verdict for a
named dataset's contract (spec: Provisioning / grant gate build verdict, "what is
built is the thing those gates would call").

`validate(contract, client) -> ValidationResult` runs four independent checks and
collects every failure from all of them, rather than stopping at the first:

- *Drift* (SC-001-02): does the contract's column list still match what the
  catalogue actually contains, right now. Names exactly what changed -- a column
  the catalogue has that the contract doesn't, one the contract has that the
  catalogue doesn't, or a type/nullability mismatch on a column present in both.
  A check, never a mutation: this module never edits `contract` to match reality.
- *Unreviewed markers* (SC-001-03): does `contract` still carry any field with
  the AI-proposed marker set. Names every such field by its dotted/indexed path
  (`Contract.unreviewed_field_paths`), because "the checks ... name the specific
  fields that remain unreviewed" is the scenario's own wording, not a paraphrase.
- *Placeholder sentinels*: does `contract` still carry one of `harvest.py`'s four
  unmistakable placeholders for the dataset fields harvest cannot know
  (description, refresh cadence, retention, certification). This is a genuinely
  separate check from the one above, on purpose -- see `_placeholder_sentinel_problems`'s
  docstring for why the unreviewed-marker check cannot catch this by construction,
  not just by omission.
- *Certification-vs-evidence* (Rules & Constraints: "a tier claim that the quality
  and coverage evidence does not support fails validation") is deliberately NOT
  built here. It needs a data-quality/coverage evidence source (`dq_registry.yaml`,
  `coverage.py`) that does not exist yet as of this phase. Wiring it in is that
  later phase's job, and this module's docstring records the gap explicitly rather
  than leaving it to be rediscovered.

What this module deliberately does not do: it does not print the exact catalogue
writes a merge would perform (that is `apply.py`'s planning/dry-run function, a
later phase) -- `validate.py` is pure checks, no dry-run diff printing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Union

from uc_metadata import harvest
from uc_metadata.models import Column, Contract
from uc_metadata.uc_client import UCClient, UCColumn


@dataclass(frozen=True)
class ValidationResult:
    """The machine-readable verdict `validate()` returns.

    `ok` is the single yes/no a caller (a future CLI, or the provisioning/grant
    gate this function stands in for) branches on. `problems` is every specific,
    human-readable failure collected across all four checks -- empty exactly when
    `ok` is `True`. Deliberately flat (a list of strings, not one object per
    check): SC-001-02 and SC-001-03 both require naming the *specific* thing that
    is wrong, and a flat list of already-formatted sentences is the cheapest shape
    that satisfies both scenarios and stays trivial to print from a CLI.
    """

    ok: bool
    problems: List[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.ok


def validate(contract: Contract, client: UCClient) -> ValidationResult:
    """Run every automated check against `contract` and collect every failure.

    Precondition: `contract` is already a validated `Contract` instance --
    schema well-formedness (every required field present, every enum value
    legal, a supported `version`) was already enforced by Pydantic on
    construction (`Contract.model_validate`, used by `Contract.from_yaml`), so
    this function trusts the type rather than re-checking it (CC Ch. 8: validate
    at the boundary, trust the type once inside it). A caller that only has a
    not-yet-validated raw file on disk should call `validate_yaml` instead, which
    surfaces a schema-well-formedness failure as a `ValidationResult` rather than
    letting Pydantic's exception propagate. `client` is used read-only, via
    `client.get_table(...)`, to compare against the catalogue's current state.

    Postcondition: every one of the four checks below runs regardless of whether
    an earlier one failed, and every problem found by every check is present in
    the returned `ValidationResult.problems` -- a caller never has to fix one
    failure, re-run, and discover the next.
    """
    problems: List[str] = []
    problems.extend(_drift_problems(contract, client))
    problems.extend(_unreviewed_field_problems(contract))
    problems.extend(_placeholder_sentinel_problems(contract))
    return ValidationResult(ok=not problems, problems=problems)


def validate_yaml(path: Union[str, Path], client: UCClient) -> ValidationResult:
    """Convenience entry point for a contract that has not yet been parsed and
    validated at all -- e.g. a CLI handed a raw file path from a change request.

    Precondition: `path` is a path to a YAML file, not necessarily one that
    parses as a legal `Contract`. Postcondition: if the file fails schema
    validation (malformed YAML, a missing required field, an illegal enum value,
    an unsupported `version`), returns a failed `ValidationResult` naming that
    failure -- the "schema well-formedness" check re-stated as a `ValidationResult`
    rather than a raised `pydantic.ValidationError`/`yaml.YAMLError` -- and does
    not attempt the other three checks, since they need a `Contract` to run
    against. Otherwise, delegates to `validate(contract, client)`.
    """
    try:
        contract = Contract.from_yaml(path)
    except Exception as exc:  # pydantic.ValidationError, yaml.YAMLError, ValueError
        return ValidationResult(ok=False, problems=[f"{path}: contract is not well-formed: {exc}"])
    return validate(contract, client)


# ---- drift (SC-001-02) ---------------------------------------------------------


def _drift_problems(contract: Contract, client: UCClient) -> List[str]:
    """Compare `contract.columns` against `client.get_table(...)`'s columns right
    now, on name, data_type and nullable. Never mutates `contract` -- this is a
    read-only comparison, the same "detected, never auto-corrected" posture the
    spec's Glossary entry for Drift describes.
    """
    full_name = contract.dataset.qualifier.full_name
    catalogue_columns = {column.name: column for column in client.get_table(full_name).columns}
    contract_columns = {column.name: column for column in contract.columns}

    problems: List[str] = []
    for name in sorted(catalogue_columns.keys() - contract_columns.keys()):
        problems.append(
            f"drift: column {name!r} exists in the catalogue but is missing from the contract"
        )
    for name in sorted(contract_columns.keys() - catalogue_columns.keys()):
        problems.append(
            f"drift: column {name!r} is declared in the contract but no longer exists in the catalogue"
        )
    for name in sorted(catalogue_columns.keys() & contract_columns.keys()):
        problems.extend(_column_drift_problem(name, contract_columns[name], catalogue_columns[name]))
    return problems


def _column_drift_problem(name: str, contract_column: Column, catalogue_column: UCColumn) -> List[str]:
    """One column present on both sides: report a mismatch on `data_type` or
    `nullable`, naming both the contract's claim and the catalogue's current
    fact, or nothing if the two already agree."""
    if contract_column.data_type == catalogue_column.data_type and contract_column.nullable == catalogue_column.nullable:
        return []
    return [
        f"drift: column {name!r} has changed -- contract declares "
        f"data_type={contract_column.data_type!r}, nullable={contract_column.nullable!r}; "
        f"catalogue now reports data_type={catalogue_column.data_type!r}, nullable={catalogue_column.nullable!r}"
    ]


# ---- unreviewed AI-proposed markers (SC-001-03) --------------------------------


def _unreviewed_field_problems(contract: Contract) -> List[str]:
    """One problem per field still carrying the AI-proposed marker, naming its
    exact dotted/indexed path (`Contract.unreviewed_field_paths`) -- SC-001-03's
    "name the specific fields that remain unreviewed", not a generic refusal."""
    return [
        f"unreviewed: {path} is still AI-proposed and must be reviewed and accepted by a human "
        "before this contract can be applied"
        for path in contract.unreviewed_field_paths
    ]


# ---- placeholder sentinels (carried-forward finding from harvest.py) -----------


def _placeholder_sentinel_problems(contract: Contract) -> List[str]:
    """One problem per dataset-level field still carrying one of `harvest.py`'s
    unmistakable placeholders.

    Deliberately separate from `_unreviewed_field_problems`, not a variant of it:
    `dataset.description`, `.refresh`, `.retention_days` and `.certification` are
    the four fields `models.Dataset` declares as human-declared-only -- plain
    values, never wrapped in `Proposed[T]` (models.py: "a human-declared value
    carries no marker the way an AI-proposed one does"). `has_unreviewed_fields`
    walks the `Proposed` tree and structurally cannot see these fields at all, so
    this check cannot be folded into that one; it exists because harvest.py's own
    docstring names it as a gap "a later phase's validate.py is the natural place
    to refuse" and nothing before this phase enforced it.

    Known limitation, stated rather than hidden: this check is a value-equality
    test against the placeholder sentinel, so it cannot distinguish "harvest never
    filled this in" from "a human genuinely declared the same value the sentinel
    happens to use" (e.g. a real 1-day retention commitment, or a real, deliberate
    `bronze` certification claim). The sentinels were chosen in harvest.py to make
    that collision as unlikely as a plain value comparison can make it; it is not
    eliminated.
    """
    dataset = contract.dataset
    problems: List[str] = []
    if dataset.description == harvest.PLACEHOLDER_DESCRIPTION:
        problems.append(
            "placeholder: dataset.description still carries harvest's placeholder text and has not "
            "been declared by a human"
        )
    if dataset.refresh.cadence == harvest.PLACEHOLDER_REFRESH.cadence:
        problems.append(
            "placeholder: dataset.refresh.cadence still carries harvest's placeholder cadence and has "
            "not been declared by a human"
        )
    if dataset.retention_days == harvest.PLACEHOLDER_RETENTION_DAYS:
        problems.append(
            "placeholder: dataset.retention_days still carries harvest's placeholder value and has not "
            "been declared by a human"
        )
    if dataset.certification == harvest.PLACEHOLDER_CERTIFICATION:
        problems.append(
            "placeholder: dataset.certification still carries harvest's placeholder tier (bronze) and "
            "has not been declared by a human"
        )
    return problems

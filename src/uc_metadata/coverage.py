"""Computes coverage: what share of datasets have an owner, a description, a
sensitivity classification and quality rules attached (Glossary: Coverage -- "a
measure of fill, explicitly not a measure of correctness"), broken out per team,
alongside a certification-tier-vs-evidence check and at least one outcome measure
(Rules & Constraints: "coverage is never published without at least one outcome
measure beside it").

`compute_coverage(contracts, ...)` is the entry point. It takes an in-memory list of
already-loaded `Contract` objects -- `load_contracts(contracts_dir)` is the sibling
function that loads a directory of contract YAML files for a caller who has one
(`contracts/` ships no real files until a later phase; this module works against
either shape, per this phase's own build verdict). `compute_coverage_for_directory`
is a one-line convenience that chains the two for a caller who does not need the
intermediate list.

Three things this module is careful to get right, each worth stating rather than
leaving to be rediscovered:

- *Fill-rate coverage* is computed per dataset on four boolean dimensions -- owner,
  description, sensitivity, DQ rules attached -- and both an overall figure and a
  per-team breakdown are returned. Team is resolved via
  `owner_registry.resolve_owner(...).team`, not by reading a `contracts/<team>/...`
  file path: `contracts/` has no real files yet (this phase's own scope note), so a
  path-shape-dependent grouping would have nothing to group by today, and would
  silently stop working the day a contract moves between directories for reasons
  that have nothing to do with which team owns it. Owner-registry resolution works
  identically whether `contracts` came from `load_contracts`, an in-memory list a
  test built, or (once phase 11 ships them) real files under `contracts/<team>/...`.
- *Certification-tier-vs-evidence* is `tier_is_supported_by_evidence`, a pure
  function taking a `Contract` and the `DQRuleResult`s already computed for it --
  this is the check `validate.py`'s docstring names as deferred pending this module
  existing (see this module's `# ---- integration point for validate.py` note
  below and `validate.py`'s own docstring, which now points back here).
- *The outcome measure is honestly labeled as simulated.* This prototype has no
  real downstream query log (Out of Scope: no metrics harvester, same posture as
  freshness -- "declared, not observed"). `sample_outcome_events.yaml` is a small,
  clearly-synthetic fixture representing what a real telemetry feed would
  eventually supply; every `OutcomeMeasure` this module returns carries
  `simulated=True` and a caveat string naming the fixture it came from, so no
  caller -- and no dashboard a later phase renders this into -- can present it as
  an observed fact by accident.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Union

import yaml
from pydantic import BaseModel, Field

from uc_metadata import harvest
from uc_metadata.dq_registry import (
    DQRule,
    DQRuleResult,
    evaluate_rules,
    load_dq_registry,
    rules_for_table,
)
from uc_metadata.models import CertificationTier, Column, Contract
from uc_metadata.owner_registry import UnknownBusinessApplicationError, resolve_owner
from uc_metadata.uc_client import UCClient

# sample_outcome_events.yaml at the repository root -- same resolution pattern as
# `dq_registry.DQ_REGISTRY_PATH` / `glossary.GLOSSARY_PATH`.
DEFAULT_OUTCOME_EVENTS_PATH = Path(__file__).resolve().parents[2] / "sample_outcome_events.yaml"

_OUTCOME_MEASURE_CAVEAT = (
    "simulated -- no real consumption telemetry is wired up in this prototype "
    "(spec Out of Scope: no metrics harvester; same 'declared, not observed' "
    "posture as freshness). Computed from a synthetic fixture "
    "(sample_outcome_events.yaml), never from an actual query log."
)

# Directory entries that live under contracts/ but are not a contract instance --
# skipped by load_contracts the same way change_classes.yaml's content_exclude
# carves them out of the content change class.
_NON_CONTRACT_NAMES = {"_schema", "_template.yaml"}


# ---- report shape (JSON-friendly: a later phase's dashboard renders this) --------


class DatasetCoverage(BaseModel):
    """One dataset's fill-rate and evidence picture."""

    full_name: str
    team: str = Field(description="Resolved via owner_registry, not a contracts/<team>/ file path -- see module docstring.")
    has_owner: bool
    has_description: bool
    has_sensitivity: bool
    has_dq_rules: bool = Field(description="At least one dq_registry.yaml rule is registered for this table.")
    column_description_fill_rate: float = Field(
        ge=0.0, le=1.0, description="Share of this dataset's columns that carry a description. 1.0 if it has no columns."
    )
    certification: str
    certification_supported_by_evidence: Optional[bool] = Field(
        default=None,
        description=(
            "tier_is_supported_by_evidence(...)'s verdict. None means it could not be "
            "computed -- a silver/gold claim was evaluated with no UCClient supplied, so "
            "DQ rules could not actually be run; bronze is always True with no client needed."
        ),
    )
    dq_rules_attached: int
    dq_rules_evaluated: int = Field(description="0 if no UCClient was supplied to compute_coverage.")
    dq_rules_passed: int

    @property
    def is_fully_covered(self) -> bool:
        """The four fill-rate dimensions this phase's spec names, all at once:
        owner, description, sensitivity, DQ rules attached."""
        return self.has_owner and self.has_description and self.has_sensitivity and self.has_dq_rules


class TeamCoverage(BaseModel):
    """One team's aggregate fill rate, for a scoreboard grouped by team."""

    team: str
    dataset_count: int
    fill_rate: float = Field(ge=0.0, le=1.0)


class OutcomeMeasure(BaseModel):
    """One outcome measure (Glossary: "a measure of whether better metadata
    changed behaviour"), always labeled as simulated in this prototype -- see
    module docstring."""

    name: str
    value: float
    unit: str
    sample_size: int
    simulated: bool = True
    caveat: str = _OUTCOME_MEASURE_CAVEAT


class CoverageReport(BaseModel):
    """The full coverage run: fill rate overall, per dimension, per team, per
    dataset, plus at least one outcome measure -- never published without one
    (Rules & Constraints)."""

    generated_at: datetime
    dataset_count: int
    overall_fill_rate: float = Field(ge=0.0, le=1.0)
    fill_rate_by_dimension: Dict[str, float]
    by_team: List[TeamCoverage]
    datasets: List[DatasetCoverage]
    outcome_measures: List[OutcomeMeasure] = Field(
        min_length=1, description="Never empty -- Rules & Constraints: coverage is never published without one."
    )


# ---- loading contracts -------------------------------------------------------------


def load_contracts(contracts_dir: Union[str, Path]) -> List[Contract]:
    """Load every contract YAML file under `contracts_dir`, recursively.

    Precondition: `contracts_dir` is a directory (may be empty, or may not
    exist yet -- `contracts/` ships no real files until a later phase; see
    module docstring). Postcondition: returns one `Contract` per `*.yaml` file
    found, skipping `_schema/` and `_template.yaml` the same way
    `change_classes.yaml`'s `content_exclude` carves them out of the content
    change class -- neither is a contract instance. Returns `[]` if the
    directory does not exist or contains no contract files, never raises for
    "nothing to load yet".
    """
    path = Path(contracts_dir)
    if not path.exists():
        return []
    contracts: List[Contract] = []
    for yaml_path in sorted(path.rglob("*.yaml")):
        relative_parts = yaml_path.relative_to(path).parts
        if relative_parts[0] in _NON_CONTRACT_NAMES:
            continue
        contracts.append(Contract.from_yaml(yaml_path))
    return contracts


# ---- the real thing ------------------------------------------------------------


def compute_coverage(
    contracts: List[Contract],
    *,
    client: Optional[UCClient] = None,
    dq_rules: Optional[List[DQRule]] = None,
    outcome_events_path: Optional[Union[str, Path]] = None,
) -> CoverageReport:
    """Compute a `CoverageReport` over `contracts`.

    Precondition: `contracts` is a list of already-validated `Contract`
    instances (every element already passed Pydantic construction, so this
    function trusts the type rather than re-checking schema well-formedness --
    the same boundary `validate.py`'s docstring describes). `client`, if
    supplied, is used read-only to actually run each dataset's DQ rules
    (`dq_registry.evaluate_rules`); without one, "has at least one DQ rule
    attached" is still computed (a registry lookup needs no live read), but a
    silver/gold certification claim cannot be confirmed as *passing* evidence,
    only as attached, and `DatasetCoverage.certification_supported_by_evidence`
    is `None` for those datasets rather than a guessed verdict.

    Postcondition: returns a `CoverageReport` with exactly one `DatasetCoverage`
    per element of `contracts`, in the same order, and at least one
    `OutcomeMeasure` -- never zero, per Rules & Constraints. `contracts == []`
    is a valid input (a coverage run over zero datasets), returning zero-valued
    fill rates rather than raising a division error.
    """
    registry = dq_rules if dq_rules is not None else load_dq_registry()
    dataset_coverages = [_dataset_coverage(contract, client=client, dq_rules=registry) for contract in contracts]

    return CoverageReport(
        generated_at=datetime.now(timezone.utc),
        dataset_count=len(dataset_coverages),
        overall_fill_rate=_mean(dc.is_fully_covered for dc in dataset_coverages),
        fill_rate_by_dimension=_fill_rate_by_dimension(dataset_coverages),
        by_team=_group_by_team(dataset_coverages),
        datasets=dataset_coverages,
        outcome_measures=_load_outcome_measures(outcome_events_path),
    )


def compute_coverage_for_directory(
    contracts_dir: Union[str, Path],
    *,
    client: Optional[UCClient] = None,
    dq_rules: Optional[List[DQRule]] = None,
    outcome_events_path: Optional[Union[str, Path]] = None,
) -> CoverageReport:
    """Convenience: `compute_coverage(load_contracts(contracts_dir), ...)` in
    one call, for a caller that has a directory rather than an in-memory
    list."""
    return compute_coverage(
        load_contracts(contracts_dir),
        client=client,
        dq_rules=dq_rules,
        outcome_events_path=outcome_events_path,
    )


# ---- certification tier vs. DQ evidence -----------------------------------------
#
# ---- integration point for validate.py ----
# `validate.py`'s docstring names this exact check as deferred pending this module
# existing (Rules & Constraints: "a tier claim that the quality and coverage
# evidence does not support fails validation"). This is now a pure function
# `validate.validate(...)` could call once it also has a `List[DQRule]`/`UCClient`
# to pass it: `tier_is_supported_by_evidence(contract, dq_registry.evaluate_rules(
# contract.dataset.qualifier.full_name, client))`. Not wired in this phase --
# `validate.py`'s own docstring has been updated to point here rather than leaving
# the gap to be rediscovered; wiring it is a follow-on change to `validate.py`
# (new problem-collecting helper plus its own test), not a one-line addition, so it
# is left as a documented integration point rather than made here.


def tier_is_supported_by_evidence(contract: Contract, dq_results: List[DQRuleResult]) -> bool:
    """`True` iff `contract.dataset.certification` is backed by DQ evidence.

    Precondition: every element of `dq_results` was evaluated for
    `contract.dataset.qualifier.full_name` -- raises `ValueError` naming the
    mismatch if any result names a different table, since a caller silently
    passing another dataset's results would produce a verdict about the wrong
    dataset. Postcondition: `bronze` makes no evidentiary claim and is always
    supported, including by an empty `dq_results` (this is also harvest.py's
    own placeholder tier -- an unfilled skeleton must not be flagged as
    *unsupported* by this check; the placeholder itself is
    `validate.py`'s `_placeholder_sentinel_problems`' job, not this one's).
    `silver`/`gold` are supported iff `dq_results` is non-empty and every rule
    in it passed -- an unattached silver/gold claim (no rules at all) is
    unsupported, the same as an attached one with a failing rule.
    """
    full_name = contract.dataset.qualifier.full_name
    mismatched = [result.full_name for result in dq_results if result.full_name != full_name]
    if mismatched:
        raise ValueError(
            f"dq_results for {mismatched[0]!r} do not describe {full_name!r} -- "
            "tier_is_supported_by_evidence needs results for this contract's own dataset"
        )
    if contract.dataset.certification == CertificationTier.BRONZE:
        return True
    return bool(dq_results) and all(result.passed for result in dq_results)


# ---- per-dataset coverage -----------------------------------------------------


def _dataset_coverage(
    contract: Contract, *, client: Optional[UCClient], dq_rules: List[DQRule]
) -> DatasetCoverage:
    full_name = contract.dataset.qualifier.full_name
    attached_rules = rules_for_table(full_name, dq_rules)

    dq_results: List[DQRuleResult] = []
    if client is not None and attached_rules:
        dq_results = evaluate_rules(full_name, client, dq_rules)

    certification_supported: Optional[bool]
    if contract.dataset.certification == CertificationTier.BRONZE:
        certification_supported = True
    elif client is not None:
        certification_supported = tier_is_supported_by_evidence(contract, dq_results)
    else:
        certification_supported = None  # cannot verify a silver/gold claim with no client to run the rules

    return DatasetCoverage(
        full_name=full_name,
        team=_team_for(contract),
        has_owner=True,  # models.Dataset.owner is a required field: always true for any valid Contract
        has_description=_has_real_description(contract.dataset.description),
        has_sensitivity=contract.dataset.sensitivity is not None,
        has_dq_rules=bool(attached_rules),
        column_description_fill_rate=_column_description_fill_rate(contract.columns),
        certification=contract.dataset.certification.value,
        certification_supported_by_evidence=certification_supported,
        dq_rules_attached=len(attached_rules),
        dq_rules_evaluated=len(dq_results),
        dq_rules_passed=sum(1 for result in dq_results if result.passed),
    )


def _has_real_description(description: str) -> bool:
    """A description "fills" the coverage dimension only if a human ever
    declared one -- `harvest.py`'s unmistakable placeholder text is present
    but not a real declaration, reusing the same constant `validate.py`'s
    placeholder-sentinel check compares against rather than redeclaring it."""
    return bool(description) and description != harvest.PLACEHOLDER_DESCRIPTION


def _column_description_fill_rate(columns: List[Column]) -> float:
    if not columns:
        return 1.0
    described = sum(1 for column in columns if column.description is not None)
    return described / len(columns)


def _team_for(contract: Contract) -> str:
    """Resolve the owning team via `owner_registry` -- see module docstring
    for why this, not a `contracts/<team>/...` file path, is the grouping
    key. Falls back to `"unknown-owner"` rather than raising, so one contract
    with a stale/unregistered business-application id does not take down an
    entire coverage run."""
    try:
        return resolve_owner(contract.dataset.owner.business_application_id).team
    except UnknownBusinessApplicationError:
        return "unknown-owner"


# ---- aggregation ---------------------------------------------------------------


def _mean(values) -> float:
    """Mean of a boolean/numeric iterable, `0.0` on empty input rather than a
    `ZeroDivisionError` -- a coverage run over zero datasets is a valid, if
    uninteresting, state (same "empty is not an error" convention
    `release_log.read_release_log` uses)."""
    values = list(values)
    if not values:
        return 0.0
    return sum(values) / len(values)


def _fill_rate_by_dimension(dataset_coverages: List[DatasetCoverage]) -> Dict[str, float]:
    return {
        "owner": _mean(dc.has_owner for dc in dataset_coverages),
        "description": _mean(dc.has_description for dc in dataset_coverages),
        "sensitivity": _mean(dc.has_sensitivity for dc in dataset_coverages),
        "dq_rules": _mean(dc.has_dq_rules for dc in dataset_coverages),
    }


def _group_by_team(dataset_coverages: List[DatasetCoverage]) -> List[TeamCoverage]:
    by_team: Dict[str, List[DatasetCoverage]] = {}
    for dataset_coverage in dataset_coverages:
        by_team.setdefault(dataset_coverage.team, []).append(dataset_coverage)
    return [
        TeamCoverage(
            team=team,
            dataset_count=len(members),
            fill_rate=_mean(member.is_fully_covered for member in members),
        )
        for team, members in sorted(by_team.items())
    ]


# ---- outcome measures (simulated -- see module docstring) -----------------------


def _load_outcome_measures(path: Optional[Union[str, Path]] = None) -> List[OutcomeMeasure]:
    """Load `sample_outcome_events.yaml` (or `path`) and reduce it to at
    least one `OutcomeMeasure`.

    Precondition: `path` (or the default) is a YAML file with a top-level
    `events` list, each entry carrying a numeric `days_to_first_query`.
    Postcondition: returns exactly one `OutcomeMeasure` named
    `time_to_first_query_days`, its `value` the mean across every event, its
    `simulated` flag and `caveat` always set -- this function has no code
    path that returns an unlabeled figure.
    """
    resolved_path = Path(path) if path is not None else DEFAULT_OUTCOME_EVENTS_PATH
    raw = yaml.safe_load(resolved_path.read_text())
    events = raw.get("events") if isinstance(raw, dict) else None
    if not events:
        raise ValueError(f"{resolved_path}: expected a non-empty top-level 'events' list")

    days = [float(event["days_to_first_query"]) for event in events]
    return [
        OutcomeMeasure(
            name="time_to_first_query_days",
            value=round(_mean(days), 2),
            unit="days",
            sample_size=len(days),
        )
    ]

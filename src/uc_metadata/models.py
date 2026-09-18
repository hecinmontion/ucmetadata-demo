"""The contract model: the Python-side source of truth for a UC metadata contract.

A contract is the single authoring surface for one dataset's metadata (Glossary:
Contract) — ownership, refresh commitments, retention, certification tier,
sensitivity, and a description per column. Every other module in this codebase
(harvest, propose, validate, apply, coverage, the CLI) imports `Contract` from here
rather than reading or writing YAML directly.

Source of truth, stated deliberately rather than left for a reader to guess:
this module's Pydantic models are what every Python caller actually validates
against, via `Contract.model_validate(...)` (used by `Contract.from_yaml`).
`contracts/_schema/contract.schema.json` is kept as a second, language-agnostic
definition of the same shape — useful for editors, CI steps or tooling that never
imports Python, and for the shared fixture in tests/unit/test_models.py that checks
the two haven't drifted apart. It is deliberately *not* invoked automatically inside
`Contract.from_yaml`: doing so would mean paying for, and trusting, two validators on
every load, with no clear answer to "which one wins" when they disagree. Pydantic
wins here; call `validate_against_json_schema` explicitly if you need the second,
language-agnostic check (e.g. to validate a YAML file with no Python runtime at all).
Every model below sets `model_config = {"extra": "forbid"}` so an unknown or
misspelled field (e.g. a typo'd `pii`) is rejected by the one validator actually
enforced at runtime, matching the `additionalProperties: false` posture
`contract.schema.json` already declares at every level -- closing a parity gap the
two validators previously had (Pydantic's own default, `extra="ignore"`, silently
dropped anything it did not recognise).

The AI-proposed / unreviewed marker (Glossary) is the load-bearing design decision in
this module: every judgment field the AI drafter may fill in is wrapped in
`Proposed[T]`, a small generic envelope carrying the value plus a review flag. That
makes "does this contract have any unreviewed field left" a generic tree-walk
(`Contract.has_unreviewed_fields`, `Contract.unreviewed_field_paths`) rather than a
hand-maintained list of field names that `validate.py` and `apply.py` would each have
to keep in sync with schema changes.
"""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Any, Generic, Iterator, List, Optional, TypeVar, Union

import yaml
from pydantic import BaseModel, Field, field_validator

# Contract schema version this module implements. Bumping it is a schema/tooling
# change (ADR-006): it takes the platform team's slow path, needs a matching bump to
# contracts/_schema/contract.schema.json's "version" enum, and a migration plan for
# every contract already in the repository.
CONTRACT_SCHEMA_VERSION = 1
SUPPORTED_CONTRACT_VERSIONS = {1}

# contracts/_schema/contract.schema.json, resolved relative to the repo root so it
# works regardless of the caller's working directory.
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "contracts" / "_schema" / "contract.schema.json"


class CertificationTier(str, Enum):
    """A coarse trust label on a dataset, earned from evidence (Glossary)."""

    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"


class Sensitivity(str, Enum):
    """How restricted a dataset or column is (Glossary: Sensitivity)."""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    STRICTLY_CONFIDENTIAL = "strictly_confidential"


T = TypeVar("T")


class Proposed(BaseModel, Generic[T]):
    """A judgment value that may still carry the AI-proposed / unreviewed marker.

    Wraps every field the AI drafter is allowed to fill in (Behaviour section):
    a column's description, its business-term link, its personal-data flag and its
    sensitivity classification, plus the dataset-level sensitivity classification.
    Harvested facts (schema, types, partitioning) are never wrapped in this type,
    because they are never AI-authored and never need review (Rules & Constraints:
    "harvested facts are never hand-authored").

    `ai_proposed=True` means the AI drafter wrote this value and no named human has
    accepted it yet. `validate.py` names any field still in that state and fails the
    change request (SC-001-03); `apply.py` refuses the whole contract rather than
    applying the reviewed parts and skipping the rest. A human reviewing the value
    corrects it if needed and flips the marker to `False` — that flip is what "taking
    ownership of it" (Glossary: Review) means in this codebase.
    """

    model_config = {"extra": "forbid"}

    value: T
    ai_proposed: bool = True
    note: Optional[str] = Field(
        default=None,
        description=(
            "Set by the drafter when it had to guess between two plausible meanings, "
            "so a reviewer's attention lands where it matters. Never set on a "
            "human-authored value."
        ),
    )

    @classmethod
    def accepted(cls, value: T) -> "Proposed[T]":
        """Build an already-reviewed value, e.g. for a human-authored field."""
        return cls(value=value, ai_proposed=False)

    @classmethod
    def proposed(cls, value: T, note: Optional[str] = None) -> "Proposed[T]":
        """Build an AI-drafted, not-yet-reviewed value."""
        return cls(value=value, ai_proposed=True, note=note)


class Qualifier(BaseModel):
    """The dataset's three-part Unity Catalog identity. Harvested, never hand-authored."""

    catalog: str = Field(min_length=1)
    schema_name: str = Field(min_length=1, alias="schema")
    table: str = Field(min_length=1)

    model_config = {"populate_by_name": True, "extra": "forbid"}

    @property
    def full_name(self) -> str:
        return f"{self.catalog}.{self.schema_name}.{self.table}"


class OwnerPointer(BaseModel):
    """Ownership recorded as a reference, never copied as free text (Glossary: Owner pointer).

    `business_application_id` is resolved to a team, solution owner and contact
    channel by `owner_registry.resolve_owner(...)` (a later phase) at read time. The
    contract itself never stores those resolved values, so they cannot silently rot.
    """

    business_application_id: str = Field(min_length=1)

    model_config = {"extra": "forbid"}


class Refresh(BaseModel):
    """A human-declared refresh commitment. Declared, never measured (Out of Scope)."""

    cadence: str = Field(min_length=1, description="e.g. 'hourly', 'daily', 'weekly'")
    sla_minutes: int = Field(gt=0, description="Minutes past the cadence boundary before it's a breach")

    model_config = {"extra": "forbid"}


class Dataset(BaseModel):
    """The dataset-level half of a contract."""

    model_config = {"extra": "forbid"}

    qualifier: Qualifier
    owner: OwnerPointer
    refresh: Refresh
    retention_days: int = Field(gt=0, description="Human-declared retention commitment, in days")
    certification: CertificationTier
    description: str = Field(
        min_length=1,
        description="Human-declared dataset summary. Never AI-authored, so it carries no marker.",
    )
    sensitivity: Optional[Proposed[Sensitivity]] = Field(
        default=None,
        description="AI-suggested, human-decided dataset-level sensitivity classification.",
    )


class Column(BaseModel):
    """One column's harvested facts plus its human/AI judgment fields.

    `name`, `data_type`, `nullable` and `partition_key` are harvested facts — the tool
    fills them in from the catalogue and a human never hand-types them. `description`,
    `business_term`, `pii` and `sensitivity` are judgment fields: absent on a freshly
    harvested skeleton ("left blank", per Behaviour), populated by `propose.py` as
    `Proposed` values, and reviewed by a human before merge.
    """

    model_config = {"extra": "forbid"}

    name: str = Field(min_length=1)
    data_type: str = Field(min_length=1)
    nullable: bool
    partition_key: bool = False

    description: Optional[Proposed[str]] = None
    business_term: Optional[Proposed[str]] = Field(
        default=None,
        description="Glossary term id/slug this column is linked to, once one has been proposed or chosen.",
    )
    pii: Optional[Proposed[bool]] = None
    sensitivity: Optional[Proposed[Sensitivity]] = None

    tags: List[str] = Field(default_factory=list)


def _iter_unreviewed_paths(node: Any, path: str) -> Iterator[str]:
    """Yield the dotted/indexed path of every `Proposed` value under `node` with
    `ai_proposed=True`.

    Generic on purpose: it walks any `BaseModel`/list/dict shape by introspecting
    `model_fields` rather than a hand-maintained list of field names, so a schema
    change that adds a new `Proposed[...]` field anywhere in the tree is covered for
    free — no second place to remember to update it.
    """
    if isinstance(node, Proposed):
        if node.ai_proposed:
            yield path
        return
    if isinstance(node, BaseModel):
        for field_name in node.__class__.model_fields:
            child_path = f"{path}.{field_name}" if path else field_name
            yield from _iter_unreviewed_paths(getattr(node, field_name), child_path)
        return
    if isinstance(node, (list, tuple)):
        for index, item in enumerate(node):
            yield from _iter_unreviewed_paths(item, f"{path}[{index}]")
        return
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _iter_unreviewed_paths(value, f"{path}.{key}")
        return
    # Plain scalars (str, int, bool, enum members) and None carry nothing to review.


class Contract(BaseModel):
    """One dataset's complete, versioned metadata contract.

    Precondition for `from_yaml`: `path` points to a YAML file containing a single
    mapping matching this shape. Postcondition: the returned `Contract` has passed
    full Pydantic validation — every required field present, every enum value legal,
    every `version` one this module declares support for.
    """

    model_config = {"extra": "forbid"}

    version: int = Field(
        default=CONTRACT_SCHEMA_VERSION,
        ge=1,
        description=(
            "Contract schema version this document conforms to. Bumping it is a "
            "schema/tooling change (ADR-006): the platform team's slow path, a semver "
            "tag, and a migration plan for every contract already in the repository."
        ),
    )
    dataset: Dataset
    columns: List[Column] = Field(default_factory=list)

    @field_validator("version")
    @classmethod
    def _version_is_supported(cls, value: int) -> int:
        if value not in SUPPORTED_CONTRACT_VERSIONS:
            raise ValueError(
                f"contract declares schema version {value}, but this build of "
                f"uc_metadata only understands {sorted(SUPPORTED_CONTRACT_VERSIONS)}. "
                "Upgrade uc_metadata, or check the contract was not written for a "
                "newer schema than this tool supports."
            )
        return value

    # ---- YAML round-trip -----------------------------------------------------

    @classmethod
    def from_yaml(cls, path: Union[str, Path]) -> "Contract":
        """Load, parse and validate a contract from a YAML file."""
        path = Path(path)
        raw = yaml.safe_load(path.read_text())
        if not isinstance(raw, dict):
            raise ValueError(f"{path}: expected a YAML mapping at the document root, got {type(raw).__name__}")
        return cls.model_validate(raw)

    def to_yaml(self, path: Union[str, Path]) -> None:
        """Serialize this contract back to YAML, using the field names a producer
        would hand-edit (e.g. `schema:`, not `schema_name:`) and omitting fields that
        are still blank rather than writing them out as `null`.
        """
        path = Path(path)
        data = self.model_dump(mode="json", by_alias=True, exclude_none=True)
        path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))

    # ---- review status ---------------------------------------------------------

    @property
    def unreviewed_field_paths(self) -> List[str]:
        """Dotted/indexed paths of every field still carrying the AI-proposed marker.

        e.g. `["dataset.sensitivity", "columns[2].description"]`. Empty once every
        proposed field has been reviewed and accepted.
        """
        return list(_iter_unreviewed_paths(self, ""))

    @property
    def has_unreviewed_fields(self) -> bool:
        """Cheap yes/no version of `unreviewed_field_paths`, for `apply.py`'s gate."""
        return next(_iter_unreviewed_paths(self, ""), None) is not None


def validate_against_json_schema(data: dict, schema_path: Optional[Union[str, Path]] = None) -> None:
    """Validate a raw contract mapping against contracts/_schema/contract.schema.json.

    This is the secondary, language-agnostic check described in this module's
    docstring: kept for parity with any non-Python tooling that reads the same schema
    file, and exercised in tests/unit/test_models.py to keep the JSON Schema and the
    Pydantic models from drifting apart. `Contract.from_yaml` does not call this
    automatically — Pydantic validation is the one enforced at runtime.

    Raises `jsonschema.exceptions.ValidationError` on failure.
    """
    import jsonschema  # imported lazily: only this optional check needs it

    resolved_path = Path(schema_path) if schema_path else SCHEMA_PATH
    schema = json.loads(resolved_path.read_text())
    jsonschema.validate(instance=data, schema=schema)

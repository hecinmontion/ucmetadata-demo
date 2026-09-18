"""Adversarial / boundary tests for `models.py` (the Contract primitive).

Constructor's `test_models.py` proves the model does what it was designed to
do. This file attacks the edges: malformed YAML shapes, an unsupported
version, an empty column list, a `Proposed.note` under stress, the
`_iter_unreviewed_paths` walk against edge shapes, and -- the highest-signal
finding in this file -- the gap between what `Contract.from_yaml` (Pydantic,
the validator this module's own docstring says "wins") actually enforces and
what `contracts/_schema/contract.schema.json` (the secondary, not-auto-invoked
check) enforces. They are not in parity on unknown/misspelled fields, and that
divergence is a real, silent-acceptance hole in the one authoring surface the
whole design rests on ("every dataset's metadata lives in exactly one contract
file").

No fixes are made here. Every assertion either documents current behaviour
that held up under attack, or encodes the behaviour the contract *should* have
and is expected to fail until a constructor addresses it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from uc_metadata.models import (
    CONTRACT_SCHEMA_VERSION,
    CertificationTier,
    Column,
    Contract,
    Dataset,
    OwnerPointer,
    Proposed,
    Qualifier,
    Refresh,
    Sensitivity,
    validate_against_json_schema,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _minimal_dataset(**overrides) -> Dataset:
    base = dict(
        qualifier=Qualifier(catalog="workspace", schema_name="analytics", table="customers"),
        owner=OwnerPointer(business_application_id="BA-10231"),
        refresh=Refresh(cadence="daily", sla_minutes=60),
        retention_days=30,
        certification=CertificationTier.BRONZE,
        description="A dataset.",
        sensitivity=None,
    )
    base.update(overrides)
    return Dataset(**base)


# ---- malformed YAML at the document root -----------------------------------------


@pytest.mark.parametrize(
    "raw_yaml",
    [
        "- just\n- a\n- list\n",  # a sequence, not a mapping
        '"just a scalar string"\n',  # a bare scalar
        "42\n",  # a bare int
        "",  # empty file -> yaml.safe_load returns None
        "null\n",  # explicit null
    ],
    ids=["sequence", "scalar-string", "scalar-int", "empty-file", "explicit-null"],
)
def test_from_yaml_rejects_a_non_mapping_document_root(tmp_path: Path, raw_yaml: str):
    path = tmp_path / "bad.yaml"
    path.write_text(raw_yaml)

    with pytest.raises(ValueError, match="expected a YAML mapping"):
        Contract.from_yaml(path)


def test_from_yaml_on_a_nonexistent_path_raises_a_clear_filesystem_error(tmp_path: Path):
    """`Contract.from_yaml` does not swallow a missing file into some generic
    parse error -- it should surface as the ordinary `FileNotFoundError`
    `Path.read_text()` raises, which the CLI's `_EXPECTED_ERRORS` tuple already
    knows how to catch and print cleanly."""
    missing = tmp_path / "does" / "not" / "exist.yaml"

    with pytest.raises(FileNotFoundError):
        Contract.from_yaml(missing)


def test_from_yaml_rejects_syntactically_invalid_yaml(tmp_path: Path):
    path = tmp_path / "broken.yaml"
    path.write_text("dataset: [unterminated\n  - nested: yes\n")

    with pytest.raises(yaml.YAMLError):
        Contract.from_yaml(path)


# ---- version handling --------------------------------------------------------------


def test_from_yaml_rejects_an_unsupported_future_version(tmp_path: Path):
    contract = Contract.from_yaml(FIXTURES_DIR / "valid_contract.yaml")
    raw = yaml.safe_load((FIXTURES_DIR / "valid_contract.yaml").read_text())
    raw["version"] = CONTRACT_SCHEMA_VERSION + 1
    path = tmp_path / "future_version.yaml"
    path.write_text(yaml.safe_dump(raw))

    with pytest.raises(ValidationError, match="only understands"):
        Contract.from_yaml(path)
    del contract  # only loaded to keep the fixture read pattern consistent


def test_version_zero_is_rejected():
    """`version` also has a `ge=1` field constraint; 0 should never reach the
    custom "supported versions" validator's error message and instead be
    rejected by the boundary constraint -- either way it must not validate."""
    raw = yaml.safe_load((FIXTURES_DIR / "valid_contract.yaml").read_text())
    raw["version"] = 0

    with pytest.raises(ValidationError):
        Contract.model_validate(raw)


def test_negative_version_is_rejected():
    raw = yaml.safe_load((FIXTURES_DIR / "valid_contract.yaml").read_text())
    raw["version"] = -1

    with pytest.raises(ValidationError):
        Contract.model_validate(raw)


def test_non_integer_version_is_rejected():
    raw = yaml.safe_load((FIXTURES_DIR / "valid_contract.yaml").read_text())
    raw["version"] = "one"

    with pytest.raises(ValidationError):
        Contract.model_validate(raw)


# ---- zero columns / all-None judgment fields ---------------------------------------


def test_contract_with_zero_columns_validates_and_has_nothing_to_review():
    """Nothing in `models.py` requires at least one column. A contract for a
    table with no columns at all (or one harvested before any column existed)
    is legal, and correctly reports nothing unreviewed."""
    contract = Contract(dataset=_minimal_dataset(), columns=[])

    assert contract.columns == []
    assert contract.has_unreviewed_fields is False
    assert contract.unreviewed_field_paths == []


def test_contract_where_every_judgment_field_is_none_has_nothing_unreviewed():
    column = Column(name="c1", data_type="string", nullable=True)
    contract = Contract(dataset=_minimal_dataset(sensitivity=None), columns=[column])

    assert column.description is None
    assert column.business_term is None
    assert column.pii is None
    assert column.sensitivity is None
    assert contract.has_unreviewed_fields is False
    assert contract.unreviewed_field_paths == []


# ---- Proposed.note under stress -----------------------------------------------------


def test_proposed_note_none_is_fine_and_omitted_on_round_trip(tmp_path: Path):
    column = Column(
        name="c1",
        data_type="string",
        nullable=True,
        description=Proposed.proposed("a guess"),  # note left as the default None
    )
    contract = Contract(dataset=_minimal_dataset(), columns=[column])
    path = tmp_path / "c.yaml"
    contract.to_yaml(path)
    raw = yaml.safe_load(path.read_text())

    assert "note" not in raw["columns"][0]["description"]  # exclude_none on to_yaml
    reloaded = Contract.from_yaml(path)
    assert reloaded.columns[0].description.note is None


def test_proposed_note_tolerates_a_very_long_adversarial_string(tmp_path: Path):
    """A drafter (or a hostile column comment feeding it, per the structural
    defence named in Out of Scope) could produce an enormous `note`. Nothing in
    `Proposed`/`Contract` bounds its length -- confirm at least that it does
    not silently truncate or choke on round-trip, since apply.py never reads
    `note` at all (it is reviewer-facing only) and this field is exactly the
    kind of free text most likely to be pasted from somewhere hostile."""
    adversarial_note = "A" * 200_000 + "\n\t<script>evil</script>\x00" + "B" * 50_000
    column = Column(
        name="c1",
        data_type="string",
        nullable=True,
        description=Proposed.proposed("a guess", note=adversarial_note),
    )
    contract = Contract(dataset=_minimal_dataset(), columns=[column])
    path = tmp_path / "c.yaml"
    contract.to_yaml(path)

    reloaded = Contract.from_yaml(path)
    assert reloaded.columns[0].description.note == adversarial_note  # byte-for-byte, not truncated


# ---- _iter_unreviewed_paths against edge shapes --------------------------------------


def test_unreviewed_paths_indexes_columns_correctly_when_multiple_are_unreviewed():
    columns = [
        Column(name="a", data_type="string", nullable=True, pii=Proposed.proposed(True)),
        Column(name="b", data_type="string", nullable=True, pii=Proposed.accepted(False)),
        Column(name="c", data_type="string", nullable=True, sensitivity=Proposed.proposed(Sensitivity.CONFIDENTIAL)),
    ]
    contract = Contract(dataset=_minimal_dataset(), columns=columns)

    paths = contract.unreviewed_field_paths
    assert paths == ["columns[0].pii", "columns[2].sensitivity"]


def test_unreviewed_paths_names_dataset_level_sensitivity_too():
    contract = Contract(
        dataset=_minimal_dataset(sensitivity=Proposed.proposed(Sensitivity.STRICTLY_CONFIDENTIAL)),
        columns=[],
    )
    assert contract.unreviewed_field_paths == ["dataset.sensitivity"]


# ---- duplicate keys and anchors/aliases in YAML ---------------------------------------


def test_duplicate_top_level_keys_silently_resolve_to_the_last_one(tmp_path: Path):
    """PyYAML's `safe_load` has no duplicate-key detection: the second
    occurrence of a mapping key silently wins with no warning. A producer who
    pastes a merge conflict badly, or a change that concatenates two YAML
    fragments, gets no signal at all that a whole `dataset:` block was
    discarded. This is standard PyYAML behaviour, not something `models.py`
    introduces, but it is a real, silent-loss failure mode for the one
    authoring surface this design depends on ("no editing metadata directly
    in the catalogue" only means something if the file itself is trustworthy).
    """
    raw_yaml = (FIXTURES_DIR / "valid_contract.yaml").read_text()
    duplicated = raw_yaml + "\nversion: 999\n"  # a second top-level `version:` key
    path = tmp_path / "dup.yaml"
    path.write_text(duplicated)

    # The last `version:` value silently wins -- and it is an unsupported one,
    # so this particular duplication happens to be caught downstream. A
    # duplicated *dataset* block (discarding real content) would not be.
    with pytest.raises(ValidationError, match="only understands"):
        Contract.from_yaml(path)


def test_yaml_anchors_and_aliases_expand_and_validate_normally(tmp_path: Path):
    """YAML anchors/aliases are a legitimate feature PyYAML's `safe_load`
    supports; confirm a contract using them for repeated structure parses to
    the same result as writing the value out twice, and does not choke or
    silently duplicate a reference in a way that corrupts the model.

    Not exercised here: pathological "billion laughs"-style exponential alias
    expansion. That is a real YAML-parser denial-of-service class
    (`yaml.safe_load` offers no built-in expansion-size guard the way some XML
    parsers do), but deliberately building an exhausting payload to prove it
    in a unit test would be an irresponsible thing to run in CI. Flagged in
    the adversary report as a spec gap worth a bounded loader limit, not
    proven destructively here.
    """
    raw_yaml = """
version: 1
dataset:
  qualifier: &q
    catalog: workspace
    schema: analytics
    table: customers
  owner:
    business_application_id: BA-10231
  refresh:
    cadence: daily
    sla_minutes: 60
  retention_days: 30
  certification: bronze
  description: "Uses an anchor for its own qualifier, aliased below for columns' sake."
columns: []
"""
    path = tmp_path / "anchors.yaml"
    path.write_text(raw_yaml)

    contract = Contract.from_yaml(path)
    assert contract.dataset.qualifier.full_name == "workspace.analytics.customers"


# ---- the Pydantic-vs-JSON-Schema parity gap: unknown/misspelled fields ---------------


def test_pydantic_rejects_an_unknown_top_level_field_the_json_schema_also_rejects(tmp_path: Path):
    """Fixed: `models.py`'s own docstring: "Pydantic wins here" --
    `Contract.from_yaml` is the one validator actually enforced at runtime;
    `validate_against_json_schema` is a secondary, not-auto-invoked check kept
    "so the two haven't drifted apart" (per the module docstring and
    `test_valid_contract_fixture_also_satisfies_the_json_schema`).

    They used to drift apart on exactly the dimension that matters most for a
    hand-edited authoring surface: `contract.schema.json` declares
    `additionalProperties: false` at every level, but no model set
    `model_config = {"extra": "forbid"}`, so Pydantic's default
    (`extra="ignore"`) silently dropped anything it did not recognise. Every
    model now sets `extra="forbid"`, so a producer who mistypes a top-level
    key gets a loud `pydantic.ValidationError` from the one validator that is
    actually enforced, matching what the secondary JSON Schema already caught.
    """
    raw = yaml.safe_load((FIXTURES_DIR / "valid_contract.yaml").read_text())
    raw["dataset_typo_should_have_been_dataset_extra"] = {"whoops": True}

    # Pydantic: now rejects it too, parity restored with the JSON Schema.
    with pytest.raises(ValidationError):
        Contract.model_validate(raw)

    # The secondary, language-agnostic schema: also rejects the same input.
    import jsonschema

    with pytest.raises(jsonschema.exceptions.ValidationError):
        validate_against_json_schema(raw)


def test_pydantic_rejects_a_misspelled_judgment_field_on_a_column(tmp_path: Path):
    """Fixed: the sharper version of the same gap. A producer meaning to
    review a column's `pii` flag but typing `piii` (a single-letter typo)
    used to get a contract Pydantic considered perfectly valid, with the real
    `pii` field silently left at its default `None` -- indistinguishable from
    "not yet proposed", and invisible to every later stage (`validate.py`,
    `apply.py`). With `extra="forbid"` on `Column`, the same typo is now
    rejected outright at load time, before it can silently carry a
    sensitive-data flag the author believed they set.
    """
    raw = yaml.safe_load((FIXTURES_DIR / "valid_contract.yaml").read_text())
    raw["columns"][1]["piii"] = raw["columns"][1].pop("pii")  # typo'd key, real content moved with it

    with pytest.raises(ValidationError):
        Contract.model_validate(raw)

    import jsonschema

    with pytest.raises(jsonschema.exceptions.ValidationError):
        validate_against_json_schema(raw)

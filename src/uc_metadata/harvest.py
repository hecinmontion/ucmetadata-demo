"""Turns catalogue facts into a contract skeleton (Glossary: Harvest).

`harvest(full_name, client, business_application_id)` reads a table's columns,
their SQL types, nullability and partitioning, and its current comment, through
the `UCClient` seam -- it works identically against `RealUCClient` (the live Free
Edition workspace) and `FakeUCClient` (the in-memory test double), since both
satisfy the same `UCClient` Protocol and this module never checks which one it
was handed.

What lands in the returned `Contract`, by field:

- Harvested facts (`Column.name`, `.data_type`, `.nullable`, `.partition_key`, and
  `Dataset.qualifier`) are always filled in from `client.get_table(...)`. Never
  hand-authored (Rules & Constraints: "harvested facts are never hand-authored").
- Judgment fields (`Column.description`, `.business_term`, `.pii`, `.sensitivity`,
  and `Dataset.sensitivity`) are always left `None` -- "left blank" per the
  Behaviour section. `propose.py` (a later phase) is the only thing that fills
  these in, always as `Proposed` values a human must then review.
- `Dataset.owner` is always an `OwnerPointer(business_application_id=...)`. This
  module calls `owner_registry.resolve_owner(...)` once, purely as a precondition
  check that the id names a real, known owner -- it deliberately discards the
  resolved `Owner` rather than writing it into the contract, because
  `OwnerPointer` is designed to store only the pointer and re-resolve at read
  time (Glossary: Owner pointer). An unknown business-application id fails
  harvest immediately rather than producing a contract nothing can ever resolve.

The one genuine design call in this module is what to do about `Dataset`'s four
other fields -- `description`, `refresh`, `retention_days`, `certification`. The
Data section is explicit that these are human-declared, with no harvested source
at all; nothing UC can tell us determines a retention commitment or a
certification claim. But `models.Dataset` also declares all four as *required*
(not `Optional`, and never wrapped in `Proposed`, on purpose: Rules & Constraints
says a human-declared value "carries no marker" the way an AI-proposed one does)
-- so a `Contract` cannot be constructed at all without some value for them, and
harvest has no honest value to invent for "what certification tier does this
dataset deserve". This module resolves that tension with keyword-only optional
overrides: a caller who already knows these commitments (a CLI flag, or a
re-harvest that carries forward a previous declaration) can supply them directly;
anything left unsupplied is filled with a placeholder built to be unmistakable
and impossible to merge by accident -- `PLACEHOLDER_DESCRIPTION` reads as a TODO
in the description field itself, `PLACEHOLDER_CERTIFICATION` is the lowest tier
(bronze), never a tier the placeholder could be mistaken for having earned. This
was chosen over always requiring the four as caller-supplied arguments because
that would block the "point the tool at a dataset, get a skeleton back"
one-command flow the Behaviour section describes for a producer who has not yet
decided a retention policy; it was chosen over silently guessing a "real-looking"
value because that would be indistinguishable from an actual human declaration
once written to YAML, which is precisely the failure `validate.py`/review is
supposed to catch. A later phase's `validate.py` is the natural place to refuse a
contract that still carries one of these placeholders, the same way it refuses an
unreviewed `Proposed` marker -- that check is not built here.
"""

from __future__ import annotations

from typing import Optional

from uc_metadata.models import (
    CertificationTier,
    Column,
    Contract,
    Dataset,
    OwnerPointer,
    Qualifier,
    Refresh,
)
from uc_metadata.owner_registry import resolve_owner
from uc_metadata.uc_client import UCClient, UCColumn

# Unmistakable placeholders for the four dataset-level fields harvest cannot
# know. Every one is deliberately implausible as a real declaration -- see this
# module's docstring for why harvest fills these in at all rather than requiring
# them as arguments.
PLACEHOLDER_DESCRIPTION = "TODO(human): describe this dataset -- harvest cannot know this; it is never harvested."
PLACEHOLDER_REFRESH = Refresh(cadence="TODO(human): declare a cadence, e.g. daily", sla_minutes=1)
PLACEHOLDER_RETENTION_DAYS = 1
PLACEHOLDER_CERTIFICATION = CertificationTier.BRONZE


def harvest(
    full_name: str,
    client: UCClient,
    business_application_id: str,
    *,
    description: Optional[str] = None,
    refresh: Optional[Refresh] = None,
    retention_days: Optional[int] = None,
    certification: Optional[CertificationTier] = None,
) -> Contract:
    """Read `full_name` back from `client` and build a skeleton `Contract`.

    Precondition: `full_name` is a `catalog.schema.table` three-part name that
    exists in whatever catalogue `client` is backed by (`client.get_table` raises
    `UCTableNotFoundError` otherwise); `business_application_id` names a real
    entry in `owner_registry` (raises `UnknownBusinessApplicationError`
    otherwise). Postcondition: returns a `Contract` whose harvested facts (`
    dataset.qualifier`, every `columns[i].name/.data_type/.nullable/
    .partition_key`) reflect exactly what `client` reported, whose judgment
    fields are all `None`, and whose four human-declared dataset fields carry
    either the caller-supplied override or an unmistakable placeholder -- never
    a value invented to look plausible.
    """
    resolve_owner(business_application_id)  # fail fast on an unknown id; see module docstring
    table = client.get_table(full_name)

    dataset = Dataset(
        qualifier=_qualifier_from_full_name(table.full_name),
        owner=OwnerPointer(business_application_id=business_application_id),
        refresh=refresh if refresh is not None else PLACEHOLDER_REFRESH,
        retention_days=retention_days if retention_days is not None else PLACEHOLDER_RETENTION_DAYS,
        certification=certification if certification is not None else PLACEHOLDER_CERTIFICATION,
        description=description if description is not None else PLACEHOLDER_DESCRIPTION,
        sensitivity=None,
    )
    columns = [_harvest_column(column) for column in table.columns]
    return Contract(dataset=dataset, columns=columns)


def _qualifier_from_full_name(full_name: str) -> Qualifier:
    """Split a harvested `catalog.schema.table` name into a `Qualifier`.

    Precondition: `full_name` is already a validated three-part name -- true of
    every `UCTable.full_name` a `UCClient` implementation returns, since both
    implementations validate it on the way in (`require_three_part_name`).
    """
    catalog, schema, table = full_name.split(".")
    return Qualifier(catalog=catalog, schema_name=schema, table=table)


def _harvest_column(column: UCColumn) -> Column:
    """Build one skeleton `Column` from a harvested `UCColumn`: facts filled in,
    every judgment field left `None` (Behaviour: "the human judgments left
    blank")."""
    return Column(
        name=column.name,
        data_type=column.data_type,
        nullable=column.nullable,
        partition_key=column.partition_key,
    )

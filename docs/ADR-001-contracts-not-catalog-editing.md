# ADR-001: Contracts in version control, not catalogue editing

- **Status:** Accepted
- **Date:** 2026-09-17
- **Decider:** hector (solo prototype; no separate approver)
- **Affects:** `src/uc_metadata/models.py`, `contracts/`, `apply.py`, `validate.py`

## Context

Metadata on a Unity Catalog platform can be authored in the catalogue itself: a producer
opens the table in the workspace UI, types a description, sets a tag, done. That path is
frictionless and it is the reason the metadata estate is in the state the README's Problem
section describes. A description typed into a catalogue UI has no diff, no reviewer, no
history beyond "last modified by", and no owner who can be asked why it says what it says.
Worse, the target environment has a *single global production metastore* — there is no
staging tier. Every keystroke in that UI is an unreviewed production change to a governance
artifact.

The second force is that metadata is not one kind of thing. Some of it the platform can read
for free (columns, types, partitioning, last write); some of it is a human judgment
(description, sensitivity, certification claim, refresh commitment). Those two need different
treatment, and an authoring surface that cannot tell them apart will happily let a human
hand-type a column type that the catalogue already knows — creating a second, rotting copy of
a fact.

## Decision

Exactly one human-readable contract file per dataset, in version control, is the **only**
authoring surface for metadata. The catalogue is a read source and a write target, never an
authoring surface.

Concretely:

- Harvested facts are read from the catalogue into the contract and never hand-authored
  (`harvest.py`). If the catalogue can tell us, the contract does not ask a human.
- Judgment fields are authored in the file, reviewed in a change request, and only then
  written outward.
- Apply is strictly one-way: contract → catalogue. There is no read-back-and-merge step.
- Because apply is one-way and repeatable, it must be idempotent (re-applying an unchanged
  contract writes nothing observable) and reversible (revert the merge, re-apply, previous
  state restored). Both are proven against real Unity Catalog, not just the fake.

## Consequences

- Review, diff, history, blame, revert and per-area ownership come for free, from a tool every
  producer already uses. None of it had to be built.
- Drift becomes a first-class concept rather than an accident: the catalogue *can* change under
  a contract (a pipeline adds a column), so `validate.py` compares the two on every change
  request and every scheduled harvest, and names the specific mismatch. See ADR-007 for why
  drift is detected rather than prevented.
- A producer who edits the catalogue directly will see their edit overwritten by the next apply.
  This is a real cost, stated plainly rather than papered over: the design's answer is that the
  contract is where you win the argument, not the UI.
- The contract file, not the catalogue, is the audit record. Combined with the append-only
  release log (`release_log.jsonl`), "who changed this, when, on whose approval" is answerable
  without trusting either the catalogue's own history or the repository's.

## Alternatives considered

- **Catalogue UI as source of truth, git as a backup/export.** Rejected: no reviewer, no diff,
  no approval gate, and on a single global metastore every edit is an unreviewed production
  change. This is the status quo the prototype exists to argue against.
- **Bidirectional sync between contract and catalogue.** Rejected: two writers means conflict
  resolution has to be invented, and "which one is right" has no principled answer. One-way
  apply plus drift *detection* gets the same visibility with none of the ambiguity.
- **Metadata declared inline in pipeline code (dbt-style docs, `COMMENT` in DDL).** Rejected,
  though it is the closest serious rival. It works for descriptions, but it couples a metadata
  correction to a pipeline deployment, it gives the platform no choke point of its own (see
  ADR-007), and it puts sensitivity classification inside the producer's repository where the
  second-approver rule cannot be enforced. Declaring sensitivity in the same place and by the
  same approval as the code that writes the data defeats the point of classifying it.

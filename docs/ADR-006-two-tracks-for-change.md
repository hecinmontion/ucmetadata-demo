# ADR-006: Two tracks for change — content edits are pre-approved by class, schema and tooling changes go through platform release review

- **Status:** Accepted
- **Date:** 2026-09-17
- **Decider:** hector
- **Affects:** `change_classes.yaml`, `src/uc_metadata/change_routing.py`,
  `.github/workflows/validate.yml` (the "Classify change" step)

## Context

A reviewer will ask, sooner or later: *does a one-word fix to a column description go through
the same approval as a change to the contract format itself?* Both answers to that question are
bad if given uniformly.

If every change takes the heavy path — platform release review, a version tag, a migration plan —
then correcting a typo in a description costs a release. Metadata authoring becomes slow, the
slowness is felt on exactly the low-value high-frequency changes, and producers stop bothering.
That is the "go tag your tables" failure with extra process.

If every change takes the light path — code owners and automated checks only — then adding a
field that every team's contract could then carry, or narrowing a controlled list's allowed
values, lands with two approvals from one team and breaks everyone else's contracts and the
tooling that reads them.

## Decision

Two classes of change, two paths, and the class is decided mechanically.

- **Content edit → fast path.** A data team changing its own contract's descriptions,
  personal-data flags, business-term links, certification claim or refresh commitments. It is
  pre-approved *as a class*: that contract's named code owners plus the automated checks, then
  merge, then apply. No per-release approval gate.
- **Schema or tooling change → slow path.** Adding a field a contract may carry, changing an
  allowed value of a controlled list, or anything else that could break an existing contract or
  the tool that reads it. Platform team's own release review, a semantic version tag, and a
  migration plan for every contract already in the repository.
- **The split is declared once, by file-path pattern**, in `change_classes.yaml`. CI lists the
  changed paths and `change_routing.classify_change(paths)` selects the path. A change touching
  both classes is treated as a schema change.
- `change_classes.yaml` classifies *itself* as a schema artifact, because changing it changes the
  review path every other change gets. So do `contracts/_schema/**`, `contracts/_template.yaml`
  and `models.py` — the platform-owned shape that happens to sit under `contracts/`.

**The asymmetry is blast radius, not trust.** A content edit affects one dataset and its
consumers. A schema change affects every team's contracts and the tooling. The fast path is not a
statement that data teams are more trustworthy; it is a statement that the consequences of being
wrong are bounded and reversible, and that the code owners of that one dataset are the people
best placed to judge it.

## Consequences

- The routing decision is visible on the change request's checks tab (a GitHub Actions notice
  annotation), so nobody has to read a log to find out which path they are on.
- Because the declaration is mechanical, the class cannot be negotiated per change request. That
  matters more than it sounds: a class that is argued each time is a queue, and a queue is what
  killed the tagging campaigns this design exists to replace. The point of writing it down once is
  to remove the conversation, not to document it.
- Treating "touches both classes" as a schema change means a change request that sneaks a format
  change in beside a description edit is routed to the heavy path automatically, without anyone
  having to spot it.
- The cost is that the declaration has to be maintained. A new platform-owned file under
  `contracts/` that nobody adds to `content_exclude` silently gets the fast path. That is a real
  failure mode; it is bounded by the fact that the file is short, reviewed, and itself on the slow
  path.
- What is *not* built: the slow path's own machinery — the release review ceremony, the version
  tagging, the migration runner for contracts already written, deprecation windows. The routing
  that selects the slow path is real and enforced; the process it selects is described.

## Alternatives considered

- **One uniform review path for everything.** Rejected, and the cost is asymmetric, which is the
  whole argument. Set the bar at the schema-change level and a column description costs a release;
  set it at the content level and a breaking format change gets two approvals from one team and no
  safety net. There is no single bar that is right for both.
- **Judge the class per change request (a human decides "is this a big one?").** Rejected: that is
  the queue described above, and it makes the answer depend on who is reviewing. It also means the
  design could not honestly claim the split is enforced — an unenforced split is indistinguishable
  from "one flow for everything", which is exactly the answer this ADR exists to avoid giving.
- **Route by change size (lines changed, number of files).** Rejected: blast radius does not
  correlate with diff size. A one-line change to an allowed value in the schema is the most
  dangerous change in the repository.
- **Separate repositories for schema and contracts, so the boundary is physical.** Rejected for
  now: it achieves the same separation at the cost of a cross-repository change for anything
  touching both, and the path-pattern declaration gives the same mechanical guarantee within the
  central layout ADR-005 chose.

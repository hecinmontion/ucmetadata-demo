# ADR-005: One central contract repository, split later if change-request volume proves it

- **Status:** Accepted
- **Date:** 2026-09-17
- **Decider:** hector
- **Affects:** `contracts/` layout, per-area code ownership, `.github/workflows/*`, `change_classes.yaml`

## Context

Contracts have to live somewhere, and the choice is between one central repository holding every
team's contracts and one repository per producing team (typically their existing pipeline repo).

The pull toward per-team repositories is real: it matches how the platform is actually
organised, since data teams own their own data products, and it removes any possibility of one
team's change request waiting behind another's. The pull toward central is that everything this
design depends on — discovery, one validation pipeline, one place to compute coverage across
teams, one place to ship a change to the contract format — is easier when the contracts are in
one place.

This is a decision about which direction is cheaper to reverse, not about which is nicer.

## Decision

Start central: a single `contracts/` folder, organised by area (`contracts/analytics/`,
`contracts/marketing/`), with per-area code owners naming who must approve changes in each — the
folder layout is shipped and is what the ownership mapping would key on; the code-owners file
itself is a named placeholder, not shipped (README "What I didn't do"). One validation workflow,
one apply workflow, one coverage run.

The flip trigger is named in advance: **sustained change-request queueing or review contention in
the contract folder.** If contracts start waiting on each other or on reviewers who are not the
relevant owners, split the folder into per-team repositories.

## Consequences

- Contracts are discoverable by browsing one tree. Coverage across teams is a directory scan
  (`ucmeta coverage contracts/`), not a federation problem.
- A change to the contract format ships once, with one migration over one set of files. Under
  per-team repositories, a schema change becomes N coordinated migrations in N repositories owned
  by N teams — which is what makes ADR-006's slow path viable here and expensive there.
- The known cost is contention in a shared folder: a single CODEOWNERS file, review load that can
  bunch up, and merge conflicts on shared files (not on the contracts themselves, which are one
  file per dataset and therefore naturally conflict-free).
- The autonomy cost is real but currently unpaid: a team cannot move its contract without
  touching a repository the platform team also owns. At three contracts this is invisible; at
  three hundred it may not be.
- **Why this is the reversible direction:** splitting one folder into per-team repositories is
  mechanical — `git filter-repo` (or simply moving files), copy the workflow, split the code-owners
  file. Consolidating N repositories that have each drifted into their own conventions, CI
  variants and schema versions is not mechanical; it is a migration project. So central is the
  decision that can be undone cheaply, and it is taken for that reason as much as for its direct
  benefits.

## Alternatives considered

- **One repository per producing team, contracts beside the pipeline code.** Rejected *for now*,
  explicitly not on principle. It buys autonomy the prototype does not yet need, and it spreads
  schema migration, workflow maintenance and coverage collection across repositories the platform
  team does not own. Its genuine advantage — a contract sitting next to the code that produces the
  data, so a schema change and a contract change can be one change request — is acknowledged, and
  it is precisely the advantage that would matter if a producer-repo CI check were ever adopted
  (see ADR-007's deferred alternative). If that happens, the flip becomes more attractive than
  queueing alone would make it.
- **A hybrid: central schema and tooling, per-team contract repositories from day one.** Rejected
  as premature: it takes on the coordination cost of the split before there is any contention to
  justify it, and the split remains available at any time.
- **Contracts published as artifacts to a registry rather than held as files.** Rejected: it
  discards the review gate that ADR-003 gets for free, and re-creates it as something to build.

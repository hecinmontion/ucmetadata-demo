# Planning specs — a point-in-time snapshot

The five files in this folder (`F-PLATFORM-001` through `F-PLATFORM-005`, plus their
`index.md`) are the planning specs behind this prototype: the business context, users and
roles, Given/When/Then scenarios, data tables, rules and constraints, trade-offs, and — for
each — a revision history recording exactly what was decided, when, and why. Every scenario
ID a docstring or a `@pytest.mark.scenario(...)` marker cites in this codebase (`SC-001-01`,
`SC-004-03`, `SC-005-02`, and so on) is defined in one of these five documents.

**This is a snapshot, not a living document.** These specs were authored and revised in a
separate internal planning workspace, over the course of building this prototype, using a
lead-and-personas process (an architect persona drafts and revises each spec; a lead session
resolves open questions with the project owner; a reconciler flags drift between spec and
code). That planning workspace is where any future spec would continue to be authored and
revised — it is not this repository, and it is not kept in sync with these files after the
fact. What's copied here is the state of all five specs as of **2026-09-20**, the day
F-PLATFORM-004 and F-PLATFORM-005 were built and live-verified.

They're included here, in the product repository, for one practical reason: this is a public
repository demonstrating a real interview submission, and a reader has no way to verify a
scenario-ID citation in the code against a spec they can't see. Copying the finished specs in
as a dated archive closes that gap without turning this repository into the live planning
surface — the two stay genuinely different things. If a spec is ever revised after
2026-09-20, this folder will read as history, not as the current plan, and that's the
intended failure mode: a stale archived spec is honestly out of date, which is a better
property than a spec silently pretending to be current.

## What's here

| File | Status as of this snapshot | Covers |
|---|---|---|
| `F-PLATFORM-001-uc-metadata-contracts.md` | in-progress | The contract model, the harvest → propose → validate → apply → coverage pipeline — see [`docs/architecture/harvest-and-metadata.md`](../architecture/harvest-and-metadata.md) for how it's actually built. |
| `F-PLATFORM-002-coverage-history-and-native-dashboard.md` | in-progress | Coverage history as an append-only table, plus the native AI/BI dashboard over it (ADR-008). |
| `F-PLATFORM-003-ci-only-apply-enforcement.md` | in-progress | The `ucmeta-ci-apply` service principal and the boundary it puts on the human's own write access (ADR-009). |
| `F-PLATFORM-004-catalog-provisioning-requests.md` | draft, implemented | The `catalog-requests/` pipeline and the fake-client-only minimal demo — see [`docs/architecture/catalog-provisioning.md`](../architecture/catalog-provisioning.md) for how it's actually built. |
| `F-PLATFORM-005-live-catalog-provisioning.md` | in-progress, live-verified | The `ucmeta-ci-provision` service principal and the live path (ADR-011). |
| `index.md` | — | One-line-per-spec index, as it stood on 2026-09-20. |

For the decisions themselves, argued and recorded as durable, shipped artifacts rather than
planning-process documents, see [`docs/adrs/`](../adrs/) — the ADRs are the right place to
start if you want *why*, not *how the discussion went*.

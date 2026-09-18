# ADR-007: Gate provisioning and grants, not schema changes — the forcing function

- **Status:** Accepted
- **Date:** 2026-09-17
- **Decider:** hector
- **Affects:** `src/uc_metadata/validate.py` (the machine-readable verdict the gates call),
  `coverage.py` (the only pressure on the grandfathered estate)

## Context

Start from the diagnosis. Metadata is missing not because producers are lazy and not because
tooling is unavailable, but because **authoring metadata is decoupled from every workflow a
producer is already obliged to complete.** Publishing a table, cutting a release and getting
access granted all succeed whether or not a single column is described. So "go tag your tables"
campaigns spend goodwill and leave nothing durable behind.

That diagnosis is also a test that any proposed solution must pass: *any design whose motive
force is producer goodwill reproduces the failure it claims to fix.* A better authoring
experience, an AI drafter, a coverage dashboard — none of those answer the question "what makes a
producer start this loop at all?" They only make the loop cheaper once started.

So the mechanism has to hang the contract off an obligation the producer already has, on a step
the platform genuinely controls.

## Decision

Gate the two choke points the platform actually owns:

1. **Provisioning.** A new dataset is not provisioned unless a contract file exists for it, is
   linked to the provisioning request, and passes the automated checks.
2. **Read grants.** No consumer read grant is issued for a dataset that has no validated
   contract.

Both are steps the producer already had to take: they go through central provisioning to get a
table, and through grant issuance to get anyone to use it. Metadata rides along on those
obligations rather than competing with them for attention. The producer gets their dataset and
their consumers *as a by-product* of authoring the contract. That is the difference from a tagging
campaign: the campaign asks for goodwill, the gate asks for nothing.

**What the gate explicitly does not claim.** It does not block schema changes. A producer altering
a column inside their own ETL or pipeline repository is outside anything this platform controls,
and no claim is made otherwise. For datasets with contracts, such a change is *detected* on the
next harvest — drift is reported naming the added column or the changed type, coverage drops
because a column now exists with no description, and an open change request carrying the same
mismatch fails its checks. Detected, not prevented.

**Two speeds, deliberately.** The gate applies to newly provisioned datasets. The existing estate
is grandfathered: no retroactive block. The pressure on it is visibility (coverage published per
team) plus drift reporting. `contracts/analytics/orders.yaml` ships in exactly that state — a real
harvested skeleton that `ucmeta validate` fails today — so the two-speed rollout is something a
reviewer can open rather than something the README asserts.

## Consequences

- "Valid contract" has to mean something executable, so `validate.py` returns a machine-readable
  verdict (`ValidationResult.ok` plus specific named problems) rather than printing prose. That
  function *is* the integration point; wiring it into the provisioning flow and the grant flow is
  a one-call integration into flows that already exist.
- The prototype builds the check, not the gates. Provisioning and grant issuance belong to the
  target organisation's platform, and the natural home for both is Terraform, not this codebase —
  `databricks_catalog`/`databricks_schema` for provisioning a new dataset, `databricks_grants`/
  `databricks_grant` for read-grant issuance, both real resources in the official Databricks
  Terraform provider. That is not a guess at what production would look like: `dc-managed-services`
  already provisions Databricks workspaces and storage this way, keyed to the same
  business-application id this prototype's contracts already carry. The gate, concretely, is a
  Terraform plan that runs `ucmeta validate <contract>` (or calls `validate.validate_yaml` from a
  wrapping script) before a `databricks_catalog`/`databricks_schema`/`databricks_grants` resource
  is allowed to apply — a `terraform plan` output, or a CI check gating `terraform apply`, refusing
  to proceed while the linked contract fails.
- **Deliberately not built, and not a gap the rest of this codebase should imitate.** Provisioning
  and grants are infrequent, deliberate, state-tracked changes — exactly what Terraform's
  plan/apply/state model is for. Applying a contract's *content* (`apply.py`, via `uc_client.py`)
  is the opposite: high-frequency, driven by arbitrary human-reviewed text, and expected to run the
  moment a PR merges. Routing that through Terraform would mean generating `.tf` files per
  contract, maintaining a state file that drifts from reality between every merge, and paying a
  plan/apply cycle for what one `COMMENT ON` statement already does directly — the over-engineering
  this prototype's own "refuses to over-engineer" trade-off argues against elsewhere. Terraform is
  right for the boundary this ADR gates; it would be wrong for the content this platform authors.
  Building the Terraform side now would also add a second toolchain (state backend, provider
  credentials) to maintain before the walkthrough, for a component nobody in the room can watch
  run — the check it would gate on (`validate.py`) is already real and already demonstrated.
- **Residual gap, stated plainly:** an existing dataset whose owner never needs a new grant is
  untouched by the gate. It will be moved, if at all, by coverage visibility. And on contracted
  datasets, drift is detected rather than prevented — a column can exist undescribed for as long
  as it takes someone to act on the report.
- Detect-only is the honest position there rather than a weakness to hide. Claiming a block the
  platform cannot enforce would make the strongest part of the design — that the forcing function
  is attached to something real — indistinguishable from the tagging campaigns it replaces. A
  design that names where its leverage ends is more credible than one that claims leverage
  everywhere.

## Alternatives considered

- **(a) Soft levers only — coverage dashboards, certification tiers, nudges, league tables.**
  Rejected: this is the tagging campaign with better graphics. The whole point of the diagnosis is
  that visibility without obligation does not move producers. Note that coverage is still built
  and still published — but as the pressure on the *grandfathered* estate, where no gate applies
  by design, not as the mechanism for new datasets.
- **(b) Hard-block schema changes in producer repositories** — a CI check in each producing team's
  own ETL repository that fails the build when a schema change has no matching contract change.
  This is the strongest lever available in principle, and it was **deferred, not rejected on
  merit.** It requires every producing team to adopt something in a repository this platform does
  not own, which makes it a cross-team negotiation with an unbounded adoption timeline rather than
  an engineering task a prototype can demonstrate. Drift detection is the standing answer for
  contracted datasets in the meantime. If it were ever adopted, it would also make per-team
  contract repositories more attractive (see ADR-005).
- **(c) Gate schema changes centrally.** Rejected because it would be false: the platform has no
  central interception point for a pipeline's DDL. A `CREATE OR REPLACE TABLE` inside a producer's
  own job does not pass through anything this platform owns. Asserting that gate would be claiming
  a control that does not exist.
- **(d) Block reads at query time for uncontracted datasets.** Rejected: it punishes consumers for
  a producer's omission, and it breaks existing workloads on the grandfathered estate — the exact
  retroactive block the two-speed rule exists to avoid.

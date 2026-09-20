---
id: F-PLATFORM-001
title: UC metadata contracts — harvest, AI-propose, review, apply, measure
status: in-progress
owner: hector
approvers: []
created: 2026-09-15
last-updated: 2026-09-20
---

# Feature: UC metadata contracts — harvest, AI-propose, review, apply, measure

> *Scope of this document.* This is our internal planning artifact for building the
> `uc-metadata-platform` prototype. It is not shipped into that repo. The candidate-facing
> repo stays lean on purpose — strong README, a handful of ADRs, the contract schema, working
> code. Formal spec folders there would read as template-mimicry rather than design.

## Business Context

On a Databricks + Unity Catalog platform where data teams own their own data products, most
datasets end up with almost no useful metadata. The reason is not laziness and not tooling
availability — it is that describing a dataset is decoupled from every workflow a producer is
already obliged to complete. Publishing a table, cutting a release, or getting access granted
all succeed whether or not a single column is described, so "go tag your tables" campaigns
consume goodwill and produce nothing durable. The consequence is paid downstream: consumers
cannot find datasets, cannot tell two similar tables apart, re-ingest sources that already
exist, and cannot judge whether data is trustworthy or sensitive. This feature attacks the
cause rather than the symptom: it makes metadata a versioned, reviewed artifact that sits on
the path a producer already walks, uses AI to remove the blank-page cost of authoring it, and
publishes coverage so the gap is visible rather than assumed.

"Sits on the path a producer already walks" is the load-bearing clause, so it is named
concretely rather than left as an aspiration. The mechanism is a gate on two things this
platform actually owns: a new dataset cannot be *provisioned* without a valid contract, and no
consumer gets a *read grant* on a dataset that has no validated contract. Producers already
have to go through provisioning to get a table, and already have to go through grants to get
anyone to use it; metadata rides along on those existing obligations rather than competing with
them for attention. That is the difference between this design and a tagging campaign: the
campaign asks for goodwill, the gate asks for nothing — the producer gets their dataset and
their consumers as a by-product of authoring the contract. Where the platform does *not* own a
choke point it does not pretend to: schema changes inside a producer's own pipeline repository
are detected as drift, never blocked. See Rules & Constraints for the precise claim and its
limits.

## Stakeholders
- Owner: hector
- Approvers: hector (self-approving; this is a solo interview submission)
- Last reviewed: 2026-09-17

## Revision History
| Rev | Date         | Author | Change |
|-----|--------------|--------|--------|
| 1   | 2026-09-15   | hector | Initial draft — flow, scenarios, and component mock-vs-build map |
| 2   | 2026-09-17   | hector | Catalogue target changed from hand-written mock to a real Unity Catalog workspace (Databricks Free Edition, OAuth CLI profile `ucmeta`). Updated the harvest / apply / fake-catalogue build verdicts, moved "real UC integration" out of Out of Scope and replaced it with a fidelity caveat, restated the catalogue-target and credential rules, added the Free Edition environment limits to non-functional requirements, reframed ADR-004, and opened one question on whether the live interview walkthrough hits the network. |
| 3   | 2026-09-17   | hector | Resolved the live-walkthrough open question: hector presents from his own laptop/network, so the demo runs live against the Free Edition workspace by default, with the fake kept wired as a rehearsed one-flag fallback rather than the primary path. |
| 4   | 2026-09-17   | hector | Added the two-track change-approval model — content edits take a fast, class-pre-approved path; schema and tooling changes take the platform team's slow release path — with the split declared mechanically by file-path pattern rather than argued per change request. Added the immutable release log as a new component (local append-only file behind a real `publish_release_record()` interface), a build verdict for the change-class routing check, ADR-006, a release-log out-of-scope bullet, and two depth-of-build open questions. Interview-specific Q&A and calibration material deliberately not imported — this spec plans the build, not the conversation. |
| 5   | 2026-09-17   | hector | Every open question resolved in conversation with hector, and one new foundational decision added that no question had captured: the *forcing function*. The Behaviour section described the authoring mechanics but never the obligation they hang off — the same "go tag your tables" failure the Business Context paragraph diagnoses. Resolved by gating dataset provisioning and consumer read grants on a valid contract, the two choke points this platform genuinely owns, and by stating explicitly what the gate does *not* claim: schema changes in producer-owned repositories stay detect-only via drift, as does the grandfathered estate. Added two Rules & Constraints bullets, a Business Context paragraph and a Behaviour paragraph tying the gate back to the diagnosis, a glossary entry, an Out of Scope bullet for the deferred producer-repo hard block, and ADR-007. Also: ADR-005 settled (central repository, split later if change-request volume proves it) and no longer a candidate; the Regulatory requirement rewritten to assume no validated regime at all, with the audit trail rejustified as ordinary hygiene rather than as anticipating a regime; prompt-injection test and discovery stub both named as not built; DQ registry, real glossary retrieval, mock owner resolver, full-depth applier, live drift demo, static coverage page, wired release log and CI-enforced fast/slow routing all settled as built; the adversarial quality-red case, the 2–3 contracts with one deliberately grandfathered, and the second deliberately-open change request added as build verdicts. Frontmatter moved from `draft` to `in-progress`: every decision the build depends on is now made, so the document's job shifts from deciding to guiding construction. Build-verdict rows previously worded as leanings were tightened to read as settled, and rows added for the provisioning/grant gate, the prompt-injection test, the deferred producer-repo check, the shipped contract set and the demo change requests. |
| 6   | 2026-09-20   | hector | *An assumption this document made silently, and a later feature quietly falsified.* The credential-free guarantee — clone the repository with no Databricks account and still get a real, working `validate.yml` run — was built on `FakeUCClient` being seeded with the three demo tables (`workspace.analytics.customers`, `workspace.analytics.orders`, `workspace.marketing.campaigns`). That was not stated as an assumption anywhere, because at the time it was not one: the three tables were the whole documented estate, so "every contract resolves against the fake" and "the fake holds three tables" were the same sentence. F-PLATFORM-004 and F-PLATFORM-005 made the platform able to provision entirely new real catalogs on demand, and nobody came back here to notice that the sentence had split in two. It was found the hard way today, on the first contract ever written for a table in a dynamically-provisioned catalog: `data_platform_demo.demo.pipeline_runs` failed `validate.yml` outright with `Error: no table found at 'data_platform_demo.demo.pipeline_runs'`. Nothing was wrong with the contract, the workflow, or the fake — the fake simply had no entry for a table that had not existed when its fixture set was written. The fix rejected is worth recording: letting `validate.yml` skip, warn, or degrade for contracts outside the fixture set would have made the error go away and hollowed out the guarantee, leaving a fork whose CI silently checks a shrinking subset of the repository. Hector's position was that validate must fully work — every contract in the repository, whichever catalog its table lives in, genuinely checkable offline. So `FakeUCClient`'s fixture set is reclassified: it is not a fixed three-table demo prop, it is a *living mirror of every table that has ever been given a contract*, and documenting a new real table now carries an obligation to seed a matching fixture entry with it. Added as a Rules & Constraints bullet naming F-PLATFORM-004/005 as what moved the ground; the `fake_uc.py`, `validate.yml` and `tests/unit/` build verdicts reworded to match; a safety-net unit test added to the build verdicts so a missing fixture entry fails offline in seconds rather than surfacing as a CI failure on someone's pull request. Status stays `in-progress`: this corrects an assumption inside a spec already being built against, and changes nothing about what is decided or what remains to build. |

## Users & Roles

- *Data producer (data team member)* — owns a dataset. Runs harvest and propose for their own
  datasets, reviews and corrects what the AI drafted, opens and merges the contract PR. Owns
  all content.
- *Platform engineer* — owns the contract shape, the command-line tool, the automated checks,
  the applier, and the coverage report. Owns zero content.
- *Data steward / data office* — owns the shared vocabulary: the glossary of business terms,
  the sensitivity levels, and what each certification tier means.
- *Data consumer* — reads metadata to find and trust a dataset; can flag a description as
  wrong, which routes back to the producer as a proposed change.
- *Reviewer / approver* — a named human (per area of the contract folder) who must approve
  before anything reaches the catalogue. For sensitivity decisions this is a second, distinct
  approver.
- *Interview panel (for the prototype specifically)* — must be able to clone the repo and run
  the full loop on a laptop with no Databricks account of their own; the default run uses the
  in-repo fake catalogue. That guarantee is only as wide as the fake's fixture set, so the fake
  covers *every* table that has a contract in the repository — not a fixed set of demo tables
  (see Rules & Constraints). Runs against the live free-tier workspace need the owner's OAuth
  profile and are the owner's to demonstrate.

## Behaviour

The feature turns dataset metadata into a reviewed document that lives alongside code.

The loop starts because it has to, not because someone asked nicely. A producer who wants a new
dataset provisioned goes through the platform's central provisioning flow, and that flow will
not create the dataset without a contract file linked to it that passes the automated checks. A
producer who wants anyone to actually read their dataset needs a read grant issued for a
consumer, and grants are not issued for datasets without a validated contract. Both of those
are steps the producer already had to take and the platform already controls, so authoring
metadata stops being an extra errand and becomes part of getting the thing they came for. For
datasets that already exist, the gate is not applied retroactively — those stay grandfathered,
and the pressure on them is visibility (coverage, published per team) plus drift reporting
rather than a block.

A producer points the tool at a dataset that already exists in the catalogue. The tool reads
back everything the platform already knows for free — the dataset's fully-qualified name, its
columns and their types, how it is partitioned — and writes that out as a skeleton contract:
a human-readable file with the technical facts filled in and the human judgments left blank.

The producer then asks the tool to propose the blanks. An AI drafter reads each column's name,
the surrounding dataset, a small sample of values, and the shared glossary, and writes a
candidate description for each column, a candidate business-term link, and a candidate
sensitivity classification flagging anything that looks like personal data. Every proposed
value is explicitly marked as AI-proposed and unreviewed. Where the drafter had to guess
between two plausible meanings it says so, so the reviewer's attention lands where it matters.

The producer opens a change request containing the contract. This is the *content* path — a
data team editing the descriptions, classifications, term links and commitments inside their
own contract — and it is deliberately the fast one: it is pre-approved as a class of change,
so it needs that contract's named code owners and the automated checks, and nothing else.
Changes to the contract *format itself* — adding a field every team's contract could then
carry, changing an allowed value of a controlled list, or anything that breaks existing
contracts — are a different and heavier flow, owned by the platform team, versioned and
accompanied by a migration plan for contracts already in the repository. This document
specifies the contracts data teams write; how the platform team ships changes to the tooling
is named here as a separate track and not detailed further.

Automated checks run on the change request. Which path the change takes is decided by the
checks themselves, from the file paths the change touches, against a declaration of the two
classes that is written down once rather than negotiated per change request. On the content
path the checks then verify that the contract is well-formed, that it still matches what the
catalogue actually contains, and that it satisfies the platform's policies. They also print exactly what would be written to the
catalogue if this change were merged — nothing is applied yet. A human reads the draft, fixes
what the AI got wrong, and clears the AI-proposed marker on each field they accept
responsibility for. Sensitivity changes need a second approver.

On merge, the platform applies the contract to the catalogue: dataset and column descriptions,
tags, and properties are written to the live catalogue. Applying the same contract twice
changes nothing the second time, and reverting the change request reverses it. Each apply also
appends one record to a release log — what changed, who approved it, when, and whether the
write succeeded — kept as an append-only account that stands beside version history rather
than relying on it, so the trail survives a disputed or rewritten repository.

Separately and on a schedule, the platform recomputes coverage — what share of datasets have
an owner, a description, a sensitivity classification, and quality rules attached — and
publishes it per team alongside a small number of outcome measures, so that "coverage went up"
can be checked against "anything got better".

## Glossary

- *Contract*: one human-readable, version-controlled file per dataset holding everything the
  platform and its consumers need to know about that dataset — ownership, refresh commitments,
  retention, certification tier, sensitivity, and a description per column. The single
  primitive this whole feature hangs off.
- *Harvest*: reading facts back out of the catalogue and into a contract skeleton. Harvested
  facts are free and never hand-written — schema, types, partitioning, last write.
- *Propose*: the AI drafting step. Fills the judgment fields — descriptions, business-term
  links, sensitivity — as suggestions, never as decisions.
- *Review*: a named human reading a proposal, correcting it, and taking ownership of it by
  clearing its AI-proposed marker.
- *Apply*: writing an approved contract's content into the live catalogue so it appears where
  consumers actually look.
- *Coverage*: the share of datasets (and of columns) whose required metadata is present. A
  measure of fill, explicitly not a measure of correctness.
- *Outcome measure*: a measure of whether better metadata changed behaviour — how long a new
  consumer takes to run their first useful query, how often the same source gets ingested
  twice, how often consumers report reading the wrong table.
- *Certification tier*: a coarse trust label on a dataset (bronze / silver / gold) earned from
  evidence — quality rules attached and passing, ownership present, description coverage — not
  self-awarded.
- *Sensitivity*: how restricted a dataset or column is (public / internal / confidential /
  strictly confidential), including whether it holds personal data. AI-suggested, always
  human-decided.
- *AI-proposed / unreviewed marker*: a flag on any field the AI wrote that no human has yet
  accepted. Its presence blocks apply.
- *Forcing function*: the reason a producer starts this loop at all. Here it is two gates on
  steps the platform already owns — a new dataset is not provisioned without a valid contract,
  and no consumer read grant is issued for a dataset without one. It is not a gate on schema
  changes, which the platform does not control.
- *Drift*: a disagreement between what the catalogue actually contains and what the contract
  claims — typically a column added, removed, or retyped without a matching contract change.
- *Code owners file*: the file that names who must approve changes to each area of the
  contract folder. Stands in for production identity-group mapping.
- *Owner pointer*: ownership recorded as a reference to the authoritative upstream system
  rather than copied into the contract, so it cannot silently rot.
- *Business term*: an entry in the shared glossary that a column can be linked to, giving one
  organisation-wide meaning to a concept rather than one per dataset.

## Scenarios

Conventions for binding tests to scenarios:
- *Backend (pytest)*: `@pytest.mark.scenario("SC-001-01")`, fallback `test_..._sc_001_01`.
- *End-to-end demo*: scenario ID in the test name and in the walkthrough script.

### SC-001-01 — Happy path: one dataset goes from undocumented to covered

- *Given* a dataset exists in the catalogue with columns and types but no descriptions, no
  sensitivity classification, and no contract in the repository
- *And* the shared glossary contains the business terms relevant to that dataset
- *When* the producer harvests the dataset, asks the AI to propose the missing descriptions,
  business-term links and sensitivity, opens a change request, corrects the two descriptions
  the AI got wrong, accepts the rest, obtains the required approvals including a second
  approver for the sensitivity fields, and merges
- *Then* the automated checks pass and print the exact set of catalogue writes before merge
- *And* on merge the platform writes the dataset description, every column description, the
  tags and the sensitivity classification into the catalogue
- *And* no field still carries the AI-proposed marker
- *And* the next coverage run shows that dataset as fully covered and its team's coverage
  figure rises accordingly
- *And* re-running apply on the unchanged contract writes nothing further

### SC-001-02 — Edge case: the catalogue has drifted away from the contract

- *Given* a dataset already has a reviewed and applied contract
- *And* the producing pipeline has since added a new column and changed the type of an existing
  one, with no matching contract change
- *When* the scheduled harvest runs
- *Then* the platform reports drift for that dataset, naming the added column and the changed
  type rather than just failing
- *And* the dataset's coverage drops, because a column now exists with no description
- *And* nothing already applied to the catalogue is removed or overwritten as a side effect
- *And* a producer can run propose to draft the missing column's metadata and close the gap
  through the normal review path
- *And* if the same drift is present in an open change request, the automated checks fail that
  change request with the specific mismatch named

### SC-001-03 — Failure case: apply refuses an unreviewed AI proposal

- *Given* a change request containing a contract in which at least one field — say a column's
  sensitivity classification — is still marked AI-proposed and unreviewed
- *When* the automated checks run on that change request
- *Then* the checks fail, name the specific fields that remain unreviewed, and state that a
  human must accept them
- *And* the change cannot be merged and therefore nothing is written to the catalogue
- *And* if such a contract reaches the apply step by any other route, apply refuses the whole
  contract rather than applying the reviewed parts and skipping the rest

## Data

| Data | Source | Direction | Sensitivity |
|------|--------|-----------|-------------|
| Dataset identity (catalogue/schema/table name, region) | Unity Catalog | Read | Internal |
| Column list, types, nullability, partitioning | Unity Catalog | Read | Internal |
| Last-write timestamp, row/size estimates | Unity Catalog | Read | Internal |
| Dataset description, certification tier, retention, refresh commitment | Contract (human-declared) | Write to catalogue | Internal |
| Column descriptions and business-term links | AI-proposed, human-reviewed | Write to catalogue | Internal |
| Column and dataset sensitivity / personal-data flags | AI-suggested, human-decided | Write to catalogue | Confidential (the classification itself is sensitive information) |
| Sample values shown to the AI drafter | Unity Catalog | Read (transient) | Potentially PII — must be masked, hashed or excluded for sensitive columns |
| Ownership (team, solution owner, contact channel) | Upstream identity/service registry, referenced by business-application id | Read (resolved, not copied) | Internal |
| Business glossary terms | Glossary source owned by the data office | Read | Public |
| Quality-rule coverage per dataset/column | Data-quality rule registry | Read | Internal |
| AI proposal audit record (model, version, prompt, inputs, timestamp, approver) | Generated at propose time | Write (stored beside the contract) | Internal |
| Coverage and outcome figures per team and per catalogue | Computed from contracts + catalogue + registries | Write (published report) | Internal |
| Applied catalogue mutations (descriptions, tags, properties) | Contract, on merge | Write | Internal |

## Rules & Constraints

- Every dataset's metadata lives in exactly one contract file, and that file is the only
  authoring surface. No editing metadata directly in the catalogue.
- *The forcing function is provisioning and grants.* A new dataset is not provisioned unless a
  contract file exists for it, is linked to the provisioning request, and passes the automated
  checks; and no consumer read grant is issued for a dataset that has no validated contract.
  These are the two choke points the platform genuinely owns — the centrally-owned
  Terraform/business-application-id provisioning flow, and grant issuance — and they are
  deliberately chosen over asking producers to volunteer, which is the failure mode named in
  Business Context. Nothing else in this design assumes producer goodwill as its motive force.
- *What the gate explicitly does not claim to block.* It does not block schema changes. A
  producer changing a column inside their own ETL or pipeline repository is outside anything
  this platform controls, and no claim is made otherwise: for datasets with contracts, such a
  change is *detected* as drift on the next harvest and surfaced (coverage drops, drift is
  reported by name, an open change request carrying the same mismatch fails), not prevented. A
  check that producers could adopt inside their own repositories to fail a build on
  uncontracted schema change is named as future work requiring cross-team buy-in; it is not
  built and not assumed. Existing, grandfathered datasets are likewise detect-only, per the
  two-speed rollout rule below.
- Harvested facts are never hand-authored. If the catalogue can tell us, the contract does not
  ask a human.
- The AI proposes; it never publishes. Every AI-written value carries an unreviewed marker.
- Apply refuses any contract that still contains an unreviewed marker, and refuses it whole —
  no partial application.
- Apply runs only on merge to the main branch. Change requests may validate and dry-run, never
  apply.
- Every change request prints the full set of catalogue writes it would perform before it can
  be merged.
- Apply is idempotent: applying an unchanged contract twice produces no second effect.
- Apply is reversible: reverting the merge and re-applying restores the previous catalogue
  state.
- There is a single global production metastore, so every apply is a production change. That
  is why dry-run, idempotency, reversibility, and second approval on sensitivity are
  non-negotiable rather than nice-to-have.
- Sensitivity and personal-data classifications require a second, distinct approver.
- Changes come in two kinds and take two different review paths. A *content edit* — a data team
  changing its own contract's descriptions, personal-data flags, business-term links,
  certification claim or refresh commitments — takes the fast path: pre-approved as a class,
  reviewed by that contract's named code owners only, merged, applied, with no per-release
  approval gate. A *schema or tooling change* — adding a field to what a contract may contain,
  changing the allowed values of a controlled list, or any breaking change to the contract
  format or the tool — takes the slow path: the platform team's own release review, a semantic
  version tag, and a migration plan for every contract already in the repository. The
  justification for the asymmetry is blast radius: a content edit affects one dataset, a schema
  change affects every team's contracts and the tooling that reads them.
- Which path a change takes is decided mechanically, not argued per change request. The two
  classes are declared once, by file-path pattern, in a single checked-in file; the automated
  checks read the set of changed paths and select the path from that declaration. A change
  touching both classes is treated as a schema change.
- Every apply publishes one immutable, append-only release record — what changed, who approved
  it, when, and the deployment outcome. It stands beside version history rather than depending
  on it, so the audit trail survives a rewritten or disputed repository. It is written through
  one narrow publish interface, so the production writer can be a central release-log service
  without changing the record's shape or any caller.
- Ownership is stored as a pointer to the authoritative upstream system, never copied as a
  free-text value.
- Certification tier is earned from evidence, not self-declared: a tier claim that the quality
  and coverage evidence does not support fails validation.
- Every AI proposal is auditable: model, version, prompt, inputs, timestamp, and the human who
  accepted it are recorded and survive as long as the contract.
- Sensitive column values are never sent to the AI drafter unmasked.
- Column-level metadata is required for newly registered datasets and grandfathered for
  existing ones; the transitional two-speed state is accepted deliberately.
- Coverage is never published without at least one outcome measure beside it.
- The prototype's catalogue target is a real Unity Catalog workspace — a personal Databricks
  Free Edition workspace, reached through `databricks-sdk` — not a hand-written mock. It is
  still confined behind one client-shaped interface, so swapping it for the target
  organisation's production metastore is a small, contained change, and so unit tests can run
  against a fast in-repo fake instead of the network.
- *The fake catalogue's fixture set is a living mirror of the documented estate, not a fixed
  demo set.* Every dataset that has a contract in the repository must have a corresponding
  `FakeUCClient` fixture entry — its schema, plus representative sample rows close enough to
  the real table that quality and DQ-evidence checks behave the same way under the fake as
  under the live workspace. Whoever documents a new real table owes it a fixture entry in the
  same change; a contract without one is an incomplete change, not a later chore. This is what
  keeps the credential-free guarantee true rather than nominally true: the automated checks
  must fully validate *every* contract in the repository for someone with no Databricks
  credentials at all, so skipping, warning or degrading for contracts outside some known
  fixture set is explicitly rejected — it would leave a fork's CI quietly checking a shrinking
  subset of the repository while still reporting green. The rule is stated here because the
  assumption it replaces was never stated: when this document was written the documented estate
  *was* the three demo tables, so "the fake holds the demo tables" and "the fake holds every
  contracted table" were indistinguishable. F-PLATFORM-004 and F-PLATFORM-005 separated them by
  making the platform able to provision new real catalogs on demand, and the first contract
  written for a table in one of them failed validation for no reason other than a missing
  fixture entry.
- Credentials for that workspace come from an OAuth user-to-machine CLI profile
  (`databricks auth login`, profile `ucmeta`), never from a long-lived personal access token.
  This is the same "no PATs" rule stated under Security, and it now has teeth rather than being
  an untested claim: no token exists anywhere in the repository or the developer's environment
  to leak.

## Non-functional Requirements

Honest framing: this is a ten-day, spare-time prototype whose job is to make a design legible
and demonstrable, not to carry platform load. Where a real deployment would need a number, the
requirement below states the prototype's target and the production consideration separately.

- *Performance (prototype)*: the full demo loop — harvest, propose, validate, apply, coverage —
  completes in under two minutes on a laptop against the live workspace, including real Unity
  Catalog API round trips, with AI calls served from recorded fixtures in automated checks so
  they are deterministic and free. Unit tests run against the in-repo fake catalogue and need
  no network at all, so the fast inner loop stays fast. A live AI proposal for one dataset of
  ~20 columns returns in under 30 seconds, and its latency and cost are printed.
- *Performance (production consideration, not built)*: harvest and coverage are batch and
  scheduled, so minutes are fine; apply sits in the merge path, so it needs to finish in the
  time a merge check is tolerable — roughly under a minute per contract.
- *Scale (prototype)*: 2–3 contracts, ~10–40 columns each, one real catalogue (the `workspace`
  managed catalogue of a personal Databricks Free Edition workspace), a glossary of 8–12 terms.
  Deliberately small enough to read end to end, and deliberately not uniformly tidy: one of the
  contracts ships in the grandfathered, partially-covered state so the two-speed rollout is
  visible in the repository rather than only claimed in prose.
- *Environment (prototype, actual)*: Databricks Free Edition — serverless compute only, a
  single workspace, a 2X-Small SQL warehouse, and a ceiling of five concurrent job tasks. Free
  Edition is licensed for non-commercial and learning use, and Databricks may reclaim an
  inactive account, so the workspace is treated as disposable: everything needed to rebuild it
  is a script, and nothing in the repository depends on a specific workspace id surviving.
  These limits are real and they shape the demo — they are not the target organisation's
  constraints, and no claim is made that anything here was exercised at production scale,
  production concurrency, or under a multi-region metastore configuration.
- *Environment (production consideration, not built)*: the target organisation runs a single
  global production metastore. That is a harder and different constraint from Free Edition's
  size limits — it is not about throughput but about blast radius, since every apply is a
  production change with no staging metastore to rehearse in. The Free Edition workspace gives
  the prototype a real API surface and real semantics; it does not give it a staging tier, and
  the dry-run, idempotency, reversibility and second-approver rules exist precisely because
  production will not have one either.
- *Scale (production consideration, not built)*: thousands of datasets. The design point that
  matters is that harvest and coverage are per-dataset and independent, so they parallelise;
  the single shared contract folder is the known scaling risk, mitigated by per-area ownership
  and, if change-request volume proves it, by splitting the folder.
- *Retention*: every contract version and every AI audit record is preserved for as long as
  the repository exists — version history is the audit trail. Coverage reports keep the latest
  run plus enough history to show direction; the prototype keeps the last run only.
- *Availability*: the tool degrades rather than fails. If the AI provider is unavailable,
  harvest, validate, apply and coverage all still work and propose reports a clear failure —
  the AI is an accelerator, never a dependency of the critical path. If the catalogue is
  unavailable, apply fails loudly and leaves nothing half-written; harvest reports stale rather
  than guessing. Automated checks never require a live AI provider.
- *Security*: no long-lived personal access tokens. Locally, credentials come from an OAuth
  user-to-machine CLI profile that stores a short-lived, refreshable token outside the
  repository; in automation they would come from the automation environment's own identity. The
  repository holds a profile name and a workspace host, never a secret. Sampled data reaching
  the AI drafter is masked or excluded for sensitive columns. The prototype ships no
  credentials, and the data in the live workspace is Databricks sample data or synthetic, never
  real business data.
- *Regulatory*: no validated regime is assumed, and none is designed for. The prototype
  makes no claim about, and takes no position on, what a regulated change-control record would
  have to look like; inventing a compliance format for a regime nobody has stated applies would
  be fabricated rigor. The audit discipline that *is* built — recording the model, version,
  prompt, inputs, timestamp and accepting human for every AI proposal, and appending one
  immutable release record per apply — is there because a platform that writes to a single
  global production metastore should be able to answer "who changed this, when, and on whose
  approval" as a matter of ordinary engineering hygiene. It is general good practice, justified
  on its own terms, and deliberately not framed as anticipating a regulatory regime. If a
  specific regime is ever named by the target organisation, the recorded material is a
  reasonable starting point for whatever format that regime prescribes — but that is an
  observation, not a design goal.

## Out of Scope

- *Production-metastore fidelity.* Real Unity Catalog integration is now in scope — harvest and
  apply read and write a live workspace through `databricks-sdk`. What stays out of scope is any
  claim that this is the target organisation's environment. The workspace is a personal
  Databricks Free Edition account: one workspace, serverless-only, a 2X-Small warehouse, no
  staging metastore, no region topology, no organisation-scale dataset count, no real identity
  groups, and no production governance policies to comply with. So the prototype proves the API
  surface and the semantics — that idempotency, drift and reversibility behave as claimed
  against real Unity Catalog — and proves nothing about behaviour at the target org's scale or
  under its region and metastore configuration. The client-shaped seam is what carries the
  argument that moving to that environment is a contained change; it is not evidence that the
  move has been made.
- *Freshness observation.* Refresh cadence and service levels are declared in the contract,
  never measured. No history introspection, no metrics harvester. Some declared commitments
  will therefore be untrue, and that is an accepted, named gap.
- *Bulk migration tooling for the existing estate.* Existing datasets are grandfathered. No
  mass-backfill runner, no prioritisation engine — the migration argument is made in words,
  not in code.
- *A standalone personal-data detection engine.* The AI suggests and a human decides, with at
  most a simple pattern-matching fallback. No claim of compliance-grade classification.
- *A prompt-injection test against the drafter.* A hostile column comment or sample value
  attempting to steer the proposal is a real and cheap-to-add test, and it is not built this
  round — it was deprioritised against the core loop, not judged unimportant. The structural
  defence that *is* present is that the drafter cannot publish anything: every proposed value
  carries an unreviewed marker and apply refuses the contract whole until a human clears it, so
  a successful injection produces a bad suggestion, not a bad catalogue entry. Naming the gap
  is the honest position; claiming the marker makes injection harmless would not be.
- *The provisioning and grant gates as running integrations.* The forcing function is a design
  claim about two flows the target organisation owns — Terraform provisioning keyed on a
  business-application id, and grant issuance. Neither is the prototype's to build or to
  simulate convincingly. What is built is the check those gates would call: validation that
  returns a machine-readable verdict for a named dataset's contract. The argument is that
  wiring it in is a one-call integration; the integration itself is described, not shown.
- *A hard block on schema changes in producer-owned repositories.* The forcing function gates
  provisioning and grants, both of which this platform owns. A check inside each producer's own
  ETL repository that fails their build when a schema change has no matching contract change
  was considered and deliberately deferred: it needs every producing team to adopt something in
  their pipeline, which is a cross-team negotiation, not an engineering task. For contracted
  datasets the change is detected as drift instead. See ADR-007.
- *Business glossary curation.* The glossary is assumed to exist elsewhere and is represented
  by a small realistic sample used as context for the drafter.
- *Access control beyond a code-owners placeholder.* Who may edit which contract is expressed
  as a code-owners file. Production would map this to identity groups; that mapping is not
  built.
- *A discovery or search experience.* Discovery is downstream of good metadata, not this
  feature. Nothing at all is built — not even a stub page. A half-built discovery surface costs
  walkthrough time and invites questions about a layer the prototype is not arguing about;
  naming it here as the intended consumer of this metadata is the whole treatment it gets.
- *A web authoring form.* Files plus change requests are the authoring surface. A lightweight
  form that opens a change request on the producer's behalf is the obvious follow-on and is
  deliberately not built.
- *A data-quality engine.* Quality rules are read from a small stand-in registry. No rule
  execution, no quality scoring engine invented from scratch.
- *A real central release-log service.* Apply publishes a release record through a real
  interface, but the writer behind it is a local append-only file. No central service, no
  retention policy, no tamper-evident storage, no cross-team query surface — the production
  adapter swaps the writer, not the record's shape, and that swap is not made here.
- *The platform team's own release process.* The slow path for schema and tooling changes is
  named, and the mechanical routing that selects it is in scope, but the release review itself —
  versioning ceremony, migration runner for contracts already written, deprecation windows — is
  described rather than built.
- *Observability of the tooling itself.* No metrics exporters, no dashboards about the tool.
- *Lineage capture and lineage-based inference.* Lineage is named as valuable context for the
  drafter; harvesting it is not built.
- *Multi-region or multi-cloud enactment.* Region is addressable in the contract; no
  region-specific apply paths exist.
- *Consumer feedback routing.* The "this description is wrong" loop is designed and described;
  no mechanism is implemented.

## Dependencies

- *Related features*: none at the time of writing. Added rev 6, because they changed something
  this document assumed rather than merely building on it: *F-PLATFORM-004* (catalog
  provisioning via `catalog-requests/`) and *F-PLATFORM-005* (live catalog provisioning) made
  the set of real, documented tables open-ended, which is what turned this spec's unstated
  "the fake holds the demo tables" into the explicit living-mirror rule in Rules & Constraints.
  Any future feature that can bring a new real dataset into existence inherits that rule.
  Likely follow-ons: freshness observation, consumer feedback routing, web authoring form,
  bulk migration.
- *ADRs*: to be written in the prototype repo, not here — proposed set:
  - ADR-001 Contracts in version control, not catalogue editing
  - ADR-002 AI proposes, humans approve
  - ADR-003 Files and change requests, not a user interface
  - ADR-004 Real free-tier Unity Catalog workspace behind a client-shaped interface — with the
    interface kept for two reasons that outlive the free tier: unit tests get a fast,
    deterministic in-memory fake instead of the network, and repointing at the target
    organisation's production metastore stays a configuration change rather than a rewrite. The
    ADR must record what the free-tier workspace is *not* (not a production stand-in, not
    scale-representative) and why OAuth user-to-machine was chosen over a personal access token.
  - ADR-005 Central contract repository, split later if change-request volume proves it —
    decided, not left as a tie. The ADR must record that the choice is a reversible one taken in
    the cheaper direction: one folder with per-area code owners gives discoverable contracts, a
    single validation pipeline and one place to ship a schema migration, and the known cost is
    change-request contention in the shared folder. Per-team repositories were rejected *for
    now* on the grounds that they buy autonomy the prototype does not yet need while spreading
    schema migration across N repositories. The ADR must name the trigger that would flip the
    decision — sustained change-request queueing or review contention in the contract folder —
    and the fact that splitting a folder into repositories is a mechanical move whereas
    consolidating N repositories is not, which is why central is the reversible starting point.
  - ADR-006 Two tracks for change: content edits are pre-approved by class, schema and tooling
    changes go through platform release review — and the split is declared by file-path pattern
    in one checked-in file rather than judged per change request. The ADR must record why the
    asymmetry is blast radius rather than trust, why the declaration is mechanical (a class
    negotiated per change request is a queue, and a queue is what killed the "go tag your
    tables" campaigns this feature exists to replace), and what the rejected alternative — one
    uniform review path for everything — costs in each direction: too heavy if the schema-change
    bar is applied to a column description, no safety net if the content bar is applied to a
    format change.
  - ADR-007 Gate provisioning and grants, not schema changes — the forcing function. The ADR
    must start from the diagnosis in Business Context: metadata is missing because authoring it
    is decoupled from every obligation a producer already has, so any design whose motive force
    is goodwill reproduces the failure. The chosen mechanism is to attach the contract to two
    obligations the platform genuinely owns — dataset provisioning and consumer read grants —
    so the producer gets their table and their consumers as a by-product of authoring. The ADR
    must record the alternatives and why they were rejected: (a) *soft levers only* — coverage
    dashboards, certification tiers, nudges — rejected because it is the tagging campaign with
    better graphics, and the Business Context paragraph exists to say that does not work;
    (b) *hard-block schema changes in producer repositories* — the strongest lever available in
    principle, and explicitly deferred rather than chosen, because it requires every producing
    team to adopt a check in a repository this platform does not own, making it a cross-team
    negotiation with an unbounded adoption timeline rather than something a prototype can
    demonstrate; (c) *gate schema changes centrally* — rejected because the platform has no
    central interception point for a pipeline's DDL, so the claim would be false. The ADR must
    be explicit about the residual gap this leaves — an existing dataset whose owner never
    wants a new grant is untouched by the gate, and drift on contracted datasets is detected,
    not prevented — and about why detect-only is the honest position there rather than a
    weakness to paper over. It should also note the two-speed consequence: the gate applies to
    newly provisioned datasets, while the grandfathered estate is moved by visibility and drift
    reporting, which is the same asymmetry already recorded in Rules & Constraints.
- *Code modules*: the table below is the core deliverable of this spec. Each component is
  mapped to a build verdict so the build order and the honesty of the "what's mocked" story are
  settled before any code is written.

### Build verdicts per component

Principle: *mock the systems you cannot touch; build the primitives the design depends on;
never mock the thing being evaluated — and when a system turns out to be reachable for free,
touch it rather than imitating it.* Unity Catalog moved from the first category to the last on
2026-09-17: a personal Databricks Free Edition workspace (host `dbc-ab209fc8-6e67`, OAuth CLI
profile `ucmeta`, real `workspace` managed catalogue) is live and free, so the catalogue target
is now real. The client-shaped seam survives the change; the hand-written imitation behind it
does not.

| Component | Verdict | Rationale (one line) |
|---|---|---|
| `src/uc_metadata/models.py` | *Real* | The contract is the primitive the entire design rests on; a typed model plus a versioned schema, with a backwards-compatibility test, is the thing being evaluated. |
| `src/uc_metadata/harvest.py` | *Real code, real source* | Real logic for turning catalogue facts into a contract skeleton, reading a live Unity Catalog workspace through the client interface via `databricks-sdk`. The harvest-vs-declare split is the design argument, and it is now settled by what the real API actually returns rather than by what a hand-written mock chose to offer. Unit tests read the in-memory fake; the demo and manual runs read the Free Edition workspace. |
| `src/uc_metadata/propose.py` | *Real* | The case explicitly probes judgment about AI; mocking the model erases the signal. Small cheap model, structured output, recorded fixtures for deterministic checks, printed latency and cost per proposal. |
| `src/uc_metadata/validate.py` | *Real* | Schema, drift and policy enforcement are where the guardrails actually live, including the refusal that makes "AI proposes, humans approve" more than a slogan. Drift detection is built, not described: the demo proves it by genuinely altering a column on the live workspace and rerunning harvest, so SC-001-02 rests on real Unity Catalog behaviour rather than a mutated fixture. It is also the function the provisioning and grant gates call — "valid contract" has to mean something executable for the forcing function to be real. |
| `src/uc_metadata/apply.py` | *Real code, real target* | Translating a contract into catalogue operations is a senior signal, and the operations now land on a real metastore: descriptions, column comments, tags and properties written to the live `workspace` catalogue. Full depth is settled: dataset descriptions, column comments, tags and properties, not table-comment-only — bounded only by what the Free Edition workspace's admin permissions actually permit, and anything the live API refuses is written up as a named limitation rather than guessed at or quietly dropped. Tests assert the exact operations emitted against the fake and prove idempotency; the demo proves the same two claims — idempotent re-apply and revert-restores — against real Unity Catalog, which is the stronger evidence and the reason the swap was worth making. Never a "would apply" print. |
| `src/uc_metadata/coverage.py` | *Real, minimal* | The case asks how success is measured, so coverage must be computed rather than described — including at least one outcome measure beside the fill rate. Built, not described: it is also the only pressure on the grandfathered estate, which the provisioning gate by design does not touch. |
| `src/uc_metadata/release_log.py` — `publish_release_record(...)` writing `release_log.jsonl` (not in the strawman tree — add it) | *Mock writer, real interface, really wired* | An immutable record of what changed, who approved it, when and whether it deployed is a governance requirement, not a log line; here it is a local append-only file behind a real publish interface, so the production adapter swaps the writer, not the shape — the same discipline as `uc_client.py` / `fake_uc.py`. Settled: `apply.py` calls it on every apply, so every demo apply appends an actual record and the walkthrough has a visible artifact that is not version history. |
| `src/uc_metadata/uc_client.py` (replaces `mock_uc.py` as the default target) | *Real, thin* | The one narrow interface every other module talks to — list columns, read and write descriptions, tags and properties — implemented over `databricks-sdk` against the live workspace. Thin on purpose: it translates, it does not decide. Configuration is a profile name and three-part catalogue path, so repointing at the target organisation's metastore is a config change. |
| `src/uc_metadata/fake_uc.py` (the former `mock_uc.py`, demoted) | *Fake, test-only* | Kept, but no longer the product's target — it exists so unit tests are fast, offline and deterministic, and so the seam stays honest by having two implementations rather than one. Its surface is defined by `uc_client.py`'s interface, and a shared contract-test suite runs against both so the fake cannot quietly drift from real Unity Catalog semantics. It is also the fallback path if the Free Edition account is reclaimed or unreachable. *Its fixture set is maintained, not fixed* (rev 6): it mirrors every table that has a contract in the repository, growing whenever a new real dataset is documented, because the credential-free guarantee is worth exactly as much as the fake's coverage of the contracts actually present. |
| `cli/ucmeta` | *Real* | One entry point, five verbs — harvest, propose, validate, apply, coverage. Discipline signal; scattered scripts read as weaker. |
| `.github/workflows/validate.yml` | *Real* | The design is change-request-gated, so the gate must actually run. A workflow file with no successful runs is worse than none. It runs credential-free against `fake_uc.py` so a fork with no Databricks account still gets a genuine check — which makes it the consumer of the living-mirror rule: it validates *every* contract in the repository, whichever catalog the table lives in, and never skips or degrades for one it cannot resolve. A contract it cannot resolve is a missing fixture entry to fix, not a case to special-case. |
| `change_classes.yaml` + a change-class routing step in `.github/workflows/validate.yml` (not in the strawman tree — add it) | *Real, minimal* | Declares by file-path pattern which changes are content edits (fast path, code owners only) and which are schema or tooling changes (slow path, platform release review), and a workflow step reads the changed paths and selects the path. Cheap — a glob check over the diff — and it is what turns the two-track model from an assertion in a README into something enforced, which is the difference between a weak and a strong answer to "does a column-description edit go through the same approval as a contract-schema change?". |
| `.github/workflows/apply.yml` | *Real* | Apply-on-merge is the forcing function; it has to be demonstrably wired to merge, not to a manual button. |
| `.github/workflows/coverage.yml` | *Real, minimal* | Scheduled recompute and publish. Cheap to build, and it proves coverage is a running process rather than a one-off screenshot. |
| `dashboard/app.py` | *Real, minimal* | Demo-ability matters: the dataset visibly flipping to covered is the payoff of the walkthrough. Settled as a static generated page rather than a served app, so it is trivially runnable on a reviewer's laptop and cannot fail live for reasons unrelated to the design. |
| `src/uc_metadata/owner_registry.py` (not in the strawman tree — add it) | *Mock behind a seam* | Ownership must resolve from an upstream identity source, not be invented. Settled shape: `resolve_owner(ba_id) -> Owner`, backed by a small hard-coded table, with the production mapping (business-application id to the authoritative identity/service registry) named in the docstring. A literal owner string in the contract with no resolver is a named red flag; the seam is what makes "owner pointer, not copied value" true in code rather than in prose. |
| `glossary/` sample terms (not in the strawman tree — add it) | *Mock data, real retrieval* | 8–12 realistic terms, and the drafter genuinely retrieves from them — RAG-lite: relevant terms are selected and passed as context, and a proposed business-term link must resolve to a real glossary entry. Settled against the cheaper option of a business-term field with a glossary sitting inertly beside it, which is a visible hole in exactly the place the case probes. |
| `dq_registry.yaml` (not in the strawman tree — add it) | *Mock, light — in scope* | Links metadata to trust, which is the whole certification story. Settled as in scope rather than described-only, because it is what makes the certification tier earnable from evidence and what makes the adversarial demo possible: one dataset that is well-covered but quality-red, with rules attached and failing. |
| Adversarial demo case (one dataset well-covered but quality-red) | *Real, small* | Deliberate counterweight to a clean demo: coverage is a measure of fill, not of correctness, and the fastest way to prove the design knows that is to show a dataset passing every coverage check while its quality rules fail. Pairs directly with `dq_registry.yaml`. |
| Provisioning / grant gate (the forcing function itself) | *Described, on a real check* | The centrally-owned Terraform provisioning flow and grant issuance are not the prototype's to build or simulate — they belong to the target organisation's platform. What is built is the thing those gates would call: `validate.py` returning a machine-readable pass/fail for a named dataset's contract. The argument is that the gate is a one-call integration into flows that already exist; the integration itself is described, not demonstrated, and ADR-007 says so plainly. |
| Personal-data detection | *Mock, light* | AI proposal plus a simple pattern fallback, with no autonomy claimed. A real detection engine is a project unto itself. |
| Freshness observation | *Skip (declared only)* | Real observation needs table-history introspection and would eat the budget; named explicitly as not done. |
| Discovery / search experience | *Skip (declared only, no stub)* | Downstream of coverage; a half-built discovery experience at the expense of the core loop is a known failure mode. Settled as nothing built, not even the one-page stub previously floated — it named itself in Out of Scope more cheaply than it would have rendered. |
| Prompt-injection test against the drafter | *Skip (named in Out of Scope)* | Cheap to add later and worth adding, but not prioritised this round against the core loop. The structural mitigation already present is that the drafter cannot publish: unreviewed markers block apply whole, so injection yields a bad suggestion rather than a bad catalogue entry. Named as a gap, not argued away. |
| Producer-repo CI hard-block on uncontracted schema change | *Skip (deferred, named in ADR-007)* | The strongest available lever and the one that needs a repository this platform does not own; adoption is a cross-team negotiation, not a build task. Deferred explicitly, with drift detection as the standing answer for contracted datasets. |
| Tooling observability | *Skip* | Out of scope for a ten-day prototype; mentioned only as not done. |
| `tests/unit/` | *Real, against the fake* | Where the boundary claims get proven — exact emitted operations, idempotency, drift detection, refusal of unreviewed fields, schema compatibility. Runs offline against `fake_uc.py` so it is fast and deterministic, plus one shared contract-test suite that runs against both implementations to keep the fake faithful. |
| Fixture-coverage safety net over every shipped contract (added rev 6 — lives with the shipped-contract tests in `tests/unit/`) | *Real, small* | The mechanical enforcement of the living-mirror rule, and the reason that rule is not merely good intentions in a document. It walks every contract file in the repository, resolves each one's dataset against `FakeUCClient`, and fails if any raises `UCTableNotFoundError` — so a contract shipped without its fixture entry is an offline unit-test failure in seconds, on the author's own machine, instead of a `validate.yml` failure discovered on someone else's pull request. Deliberately discovery-based over the contracts directory rather than a hand-listed set of table names, since a hand-listed set would rot in exactly the way the rule exists to prevent. Constructor-side naming is theirs to settle; what this spec requires is that the assertion exists and runs in the default offline suite. |
| `tests/e2e/demo_scenario.py` | *Real, two modes* | This is SC-001-01 executed as code. Default mode runs entirely against the fake, so the walkthrough is reproducible on a reviewer's laptop with no Databricks account; a `--live` mode runs the same scenario against the Free Edition workspace using the `ucmeta` OAuth profile. The same scenario file serves both, which is itself the demonstration that the seam works. The `--live` run includes the real drift step: alter a column on the workspace, rerun harvest, show the mismatch named. |
| `contracts/` — the shipped set | *Real, 2–3* | Settled at two or three contracts, one of which deliberately shows the untidy transitional state: grandfathered, partially covered, with columns still undescribed. All-finished contracts would make the two-speed rollout claim an assertion; one visibly mid-migration contract makes it evidence. Consistent with the Scale (prototype) figure. |
| Demo change requests in the public repository | *Real, one merged and one left open* | The merged one proves apply-on-merge and the release record; a second left deliberately open, with the automated checks visible on it, proves the review gate runs and refuses rather than being described as running. Cheap, and it is the only artifact that shows the checks from a reviewer's own side of the screen. |

## Open Questions

No rows remain open as of revision 5. Resolved rows are kept rather than deleted, because the
reasoning behind a settled decision is the part that is expensive to reconstruct later — and
several of these are questions an interview panel is likely to ask directly.

| Question | Owner | Due | Status |
|----------|-------|-----|--------|
| Do we spend real money on real AI calls, or mock the drafter entirely? (Leaning real, with recorded fixtures for deterministic checks — the case explicitly probes judgment about AI, and a fully mocked drafter erases that signal. Needs a decision on model, budget and whether cost/latency are printed.) | hector | 2026-09-17 | *resolved: real calls, with recorded fixtures.* Live proposals for the demo and manual runs; fixtures replayed in automated checks so they stay deterministic, free and offline. A mocked drafter would erase precisely the signal the case is probing, and latency and cost are printed so the economics are stated rather than hidden. |
| Is the data-quality registry link in scope, or does it stay a described-only integration? (Leaning a light stand-in registry, because the metadata-to-trust link carries the certification story — but it costs build days.) | hector | 2026-09-17 | *resolved: in scope, as a light stand-in registry.* `dq_registry.yaml` with a handful of rules and results. It is what makes certification tier earnable from evidence instead of self-declared, and it is the prerequisite for the adversarial well-covered-but-quality-red demo; described-only would have left the trust half of the story unbuilt. |
| Is the coverage view built or only described? (Leaning built-but-minimal, ideally a generated static page rather than a served app, because the dataset flipping to covered is the walkthrough's payoff.) | hector | 2026-09-17 | *resolved: built, minimal, as a static generated page.* A served app adds a runtime that can fail live for reasons unrelated to the design; a generated page is trivially runnable by a reviewer and still delivers the walkthrough's payoff — the dataset visibly flipping to covered. |
| Central contract repository or per-team repositories — and do we take a position or deliberately argue both sides in the walkthrough? | hector | 2026-09-17 | *resolved: start central, split later if change-request volume proves it a bottleneck.* A position is taken rather than both sides argued, and ADR-005 moves from candidate to settled. Central is the reversible direction — splitting one folder into repositories is mechanical, re-consolidating N repositories is not — and the flip trigger (sustained review contention in the contract folder) is named in the ADR. |
| Does the prototype include a glossary at all, and if so does the drafter genuinely retrieve from it, or is the business-term link left unsupported? | hector | 2026-09-17 | *resolved: real retrieval over the 8–12 term sample.* The drafter selects relevant terms and passes them as context (RAG-lite), and a proposed term link must resolve to a real entry. A glossary present as a schema field with nothing behind it is a hole in the exact place the case looks. |
| Does ownership resolve through a mock resolver seam, or stay a literal value in the contract? (A hard-coded owner with no resolver is a named red flag.) | hector | 2026-09-17 | *resolved: mock resolver behind a real seam.* `owner_registry.py` exposing `resolve_owner(ba_id) -> Owner` over a small hard-coded table, with the production mapping named in the docstring. This is what makes "ownership is a pointer, never a copied value" true in code rather than only in the rules. |
| How far does the applier go — dataset-level description only, or descriptions plus column comments plus tags plus properties? (Table-comment-only is a named weak signal. Now partly answerable by experiment rather than opinion: what a Free Edition managed catalogue actually permits an admin to write sets the floor, and anything the real API refuses becomes a named limitation instead of a guess.) | hector | 2026-09-17 | *resolved: full depth.* Dataset descriptions, column comments, tags and properties — bounded only by what the real Free Edition workspace's admin permissions actually allow. Anything the live API refuses is recorded as a named limitation with the refusal quoted, not guessed at and not silently narrowed: an empirical ceiling is a stronger answer than a chosen one. |
| Do we build the drift-detection path, or only describe it? It is the honest answer to "what if schema changes without a contract change", and SC-001-02 depends on it. (The real workspace makes this cheap and convincing to demonstrate — genuinely `ALTER TABLE` a column in and rerun harvest, rather than mutating a fixture.) | hector | 2026-09-17 | *resolved: build it, and demonstrate it against the live workspace.* The demo genuinely alters a column on the real catalogue and reruns harvest. SC-001-02 depends on it, and drift is now also the standing answer to the one thing the forcing function deliberately does not gate — schema changes in producer-owned repositories — so describing it was no longer an option. |
| Do we assume a validated regulatory regime and build a change-control record format, or record the raw audit material and flag the format as an open question? | hector | 2026-09-17 | *resolved: assume no validated regime at all.* Stronger than merely deferring the format question: no regulatory regime is assumed, designed for, or anticipated, and the previous conditional hedge is removed from Non-functional Requirements. The audit rigor stays — model, prompt, inputs, timestamp, approver, plus the immutable release record — but justified as ordinary engineering hygiene for a platform writing to a single global production metastore. Designing to a regime nobody has stated applies would be fabricated rigor. |
| Do we include an adversarial demo case — well-covered but quality-red, or a deliberately ambiguous column the drafter gets wrong — or keep the demo clean and fast? | hector | 2026-09-17 | *resolved: yes — one dataset well-covered but quality-red.* Rules attached and failing, made possible by the now-in-scope DQ registry. Coverage is a measure of fill and not of correctness; the fastest way to prove the design knows that is to show a dataset that passes every coverage check while its quality evidence says do not trust it. |
| How many contracts ship in the repository, and do any of them deliberately show the untidy transitional state (grandfathered, partially covered) rather than all being finished? | hector | 2026-09-17 | *resolved: 2–3 contracts, one deliberately messy.* One ships grandfathered and partially covered, with columns still undescribed. An all-finished set would leave the two-speed rollout as an assertion; one visibly mid-migration contract turns it into evidence a reviewer can open. |
| Does the prototype ship a discovery stub page, or nothing at all with discovery named only as out of scope? | hector | 2026-09-17 | *resolved: nothing built.* Not even the one-page stub previously floated. Discovery stays named in Out of Scope as the downstream consumer of this metadata; a stub would cost walkthrough time and invite questions about a layer the prototype is not arguing about. |
| Is the demo change request left open and visible in the public repository as evidence the flow ran, in addition to the merged one? | hector | 2026-09-17 | *resolved: yes, one left open alongside the merged one.* The merged change request proves apply-on-merge and the release record; the open one, with check results visible on it, proves the gate actually runs and refuses. It is the only artifact that shows the checks from the reviewer's own side of the screen. |
| Do we build a prompt-injection test against the drafter (e.g. a hostile column comment or sample value), or name it as not done? | hector | 2026-09-17 | *resolved: not built; named explicitly in Out of Scope.* Cheap to add later and genuinely worth adding, but it was not prioritised against the core loop this round — stated as a deprioritisation, not as a judgment that it does not matter. The structural mitigation already present is that the drafter cannot publish: unreviewed markers block apply whole, so a successful injection yields a bad suggestion rather than a bad catalogue entry. |
| How deep does the fast-path / slow-path split go — documented in ADR-006 plus the README, or actually enforced by a check that reads the changed file paths against `change_classes.yaml` and selects the workflow? (Leaning enforced, because it is a glob check in a workflow step and an unenforced split is exactly the "same flow for everything" answer the design is arguing against — but it needs a second contract-folder path pattern and a schema-change example in the repository to demonstrate against, which is not free.) | hector | 2026-09-17 | *resolved: enforced by the automated check.* A workflow step reads the changed paths against `change_classes.yaml` and selects the path, with a change touching both classes treated as a schema change. An unenforced split is indistinguishable from "one flow for everything", which is the answer the design exists to argue against, so the extra path pattern and schema-change example are worth their cost. |
| Is the release log wired into `apply.py` for real — every demo apply appends a record to `release_log.jsonl` — or does it stay a described-only interface named on the "what I did and didn't do" slide? (Leaning wired, because the cost is one append and the walkthrough gains a visible artifact that is not git history; the risk is that a half-built audit trail invites questions the prototype cannot answer about retention and tamper evidence.) | hector | 2026-09-17 | *resolved: wired for real.* Every apply, including every demo apply, appends an actual record through `publish_release_record(...)`. The cost is one append; the gain is an audit artifact that does not depend on version history. The retention and tamper-evidence questions are answered by scoping them out loud in Out of Scope — the production adapter swaps the writer, not the record's shape. |
| Is the catalogue target a mock or a real Unity Catalog? | hector | 2026-09-17 | *resolved: real.* A Databricks Free Edition workspace is free, needs no card, has no trial clock, and was verified reachable with OAuth user-to-machine auth and a writable `workspace` catalogue. The original "nobody has a catalogue to hit" premise no longer holds, so the hand-written mock is demoted to a test-only fake and the real workspace becomes the target behind the same seam. |
| Does the interview walkthrough itself hit the live workspace, or run against the fake with the live run shown as a recording? | hector | 2026-09-17 | *resolved: live, option (a).* Hector will present from his own laptop, on his own network — the two biggest sources of "borrowed environment" risk (unfamiliar wifi, no local CLI auth, someone else's cold warehouse) are off the table. The demo runs live against the Free Edition workspace by default; the fake (`fake_uc.py` / non-`--live` e2e mode) stays wired as a one-flag rehearsed fallback, not removed — an expired OAuth token or a reclaimed Free Edition account are still real, if smaller, failure modes worth a rehearsed recovery line rather than a silent hope. `tests/e2e/demo_scenario.py --live` run through once the night before and once same-day is the rehearsal, not just a read-through. |
| What makes a producer start this loop at all, and what stops them skipping it? (Raised in revision 5 as a gap: the Behaviour section described the authoring mechanics but never the obligation they hang off, which is the "go tag your tables" failure mode the Business Context paragraph diagnoses. The source guide's real-world answer — producers already author interface-agreement YAML to obtain access grants, so metadata rides along — is not available to this prototype, so an equivalent had to be designed.) | hector | 2026-09-17 | *resolved: gate provisioning and grants, not schema changes.* A new dataset is not provisioned without a linked, valid contract, and no consumer read grant is issued for a dataset without one — two choke points the platform genuinely owns. Explicitly not claimed: any block on schema changes inside a producer's own pipeline repository, which stays detect-only via drift, as does the grandfathered estate. Soft levers alone were rejected as the tagging campaign in better clothes; the producer-repo CI hard-block was considered and deferred as a cross-team negotiation rather than a build task. Recorded as ADR-007. |

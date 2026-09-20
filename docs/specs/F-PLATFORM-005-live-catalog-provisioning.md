---
id: F-PLATFORM-005
title: Live catalog provisioning — a metastore-level grant decision, and the first real catalog
status: in-progress
owner: hector
approvers: []
created: 2026-09-20
last-updated: 2026-09-20
---

# Feature: Live catalog provisioning — a metastore-level grant decision, and the first real catalog

> *Scope of this document.* Internal planning artifact for the `uc-metadata-platform` prototype,
> same convention as F-PLATFORM-001 through F-PLATFORM-004: it plans a build that happens in that
> repository, and nothing from this folder is shipped into it. Nothing in this feature has been
> built or executed yet — every statement below is a proposal, and no scenario here is a report of
> something that already ran. Two things make this document unusual among the five. First, most of
> the mechanism it needs already exists and was deliberately built without it, so the build-verdict
> table below is dominated by a column of rows that read *nothing to do*. Second, the one decision
> it exists to make is not a code decision at all, and it is left open on purpose — see Open
> Questions, and see F-PLATFORM-003's Layer 2 for the precedent on why a decision like this gets
> its own approval rather than riding along with a document.

## Business Context

F-PLATFORM-004 built a catalog-provisioning pipeline that has never provisioned a catalog. That is
not a criticism of it — it is exactly what that feature promised, in as many words: *"There is no
live path in this feature — not disabled, not optional, not one flag away; it is F-PLATFORM-005's
whole subject."* A business stakeholder can author a request file, a reviewer can approve it, a
merge can trigger the pipeline, the request is validated for real, an ordered plan of three
statements is built for real, and those statements execute against an in-memory fake. The
mechanism is complete and tested. The thing it exists to do has never happened.

The reason it stopped there is a single sentence in ADR-009, the decision record F-PLATFORM-003
shipped when it gave continuous integration an identity of its own: *"It is granted nothing else.
No create or drop anywhere, no administrative standing at account, workspace or metastore level."*
Creating a catalog requires precisely the standing that sentence rules out. So the prototype
arrived at a genuine fork rather than a missing feature: either that sentence stops being true, or
a second identity exists for which a different sentence is written. F-PLATFORM-004 refused to make
that choice in passing, on the grounds that approving a demo mechanism and approving a privilege
widening are different decisions that should not ride on one approval. This feature is where the
choice gets made deliberately, with the argument written down, and then executed.

**It has now been made, and the sentence stands.** A second, provisioning-only service principal —
`ucmeta-ci-provision` — is created and granted the metastore-level privilege to create catalogs,
and nothing else. `ucmeta-ci-apply` is not widened, not re-granted, not touched; it keeps writing
table metadata and remains unable to create anything anywhere, exactly as ADR-009 describes it. The
two identities are separated by function, which is the same argument F-PLATFORM-003 made when it
separated the machine from the human, applied one level further in. The cost is a second principal
to create, grant, document, credential and rotate, and it is accepted: a prototype whose whole
thesis is least-privilege separation should not make its first exception at the first moment
separation becomes inconvenient. The reasoning is recorded in revision 2 and in this feature's ADR,
not left to be inferred from a grant script.

What makes it worth doing rather than leaving as a documented gap is the difference F-PLATFORM-003
already demonstrated between a stated capability and a verified one. That feature's own value came
from actually running a live apply as a machine identity and discovering something the design
discussion had predicted wrongly — that a metastore admin's tag writes bypass the boundary
entirely. A provisioning pipeline that has only ever created catalogs in a Python dictionary is in
the same epistemic position ADR-009 was in before it was executed: probably right, unverified. The
`CREATE CATALOG` statement this repository builds has never been parsed by a real warehouse. The
privilege error it would get without a grant has never been read. Whether `ALTER CATALOG ... SET
TAGS` behaves the way the table-tag equivalent does is, today, an assumption. Those are cheap
things to find out and expensive things to be wrong about in front of a reviewer.

So this feature's deliverable is small and specific: make one real catalog exist, created by
automation, from a reviewed and merged request file, with a real audit record behind it — and
know, from having done it rather than from having reasoned about it, what that actually takes.

## Stakeholders
- Owner: hector
- Approvers: hector (self-approving; this is a solo interview submission) — and, for the identity
  decision specifically, a second and explicit approval recorded as a dated entry in this
  document's Revision History before any metastore-level grant is made. This is the same ceremony
  F-PLATFORM-003 required for its Layer 2, for the same reason: see Rules & Constraints.
  **That ceremony is satisfied. Revision 2 below is it** — dated, explicit, naming the option
  chosen and the reasoning behind it. What it authorises is the design: the grant may now be
  built as specified. Executing it against the live workspace remains a separate step hector
  asks for explicitly, and no part of this document is permission to run it unprompted.
- Last reviewed: 2026-09-20

## Revision History
| Rev | Date         | Author | Change |
|-----|--------------|--------|--------|
| 1   | 2026-09-20   | hector | Initial draft, written against the code as it actually stands after F-PLATFORM-004 shipped rather than against that feature's draft-era assumptions. Confirms by inspection what already exists and therefore is *not* this feature's work: `create_catalog`, `create_schema` and `set_catalog_tags` on both the `UCClient` protocol and `RealUCClient`; the whole `provision_catalog.py` module including its refusal, ordered-plan, partial-failure and release-log discipline; the `ucmeta provision-catalog` verb with `--live`/`--profile` *already wired* through the shared client arguments; and `provision-catalog.yml`'s changed-path diff, template carve-out and approver resolution. Scopes this feature to five things that genuinely do not exist: the metastore-level privilege decision and its execution, the grant script that expresses it, the workflow's live branch, the first verified real catalog, and an ADR that either amends or leaves standing ADR-009's least-privilege claim depending on which way the decision goes. Five scenarios. **The identity choice is left open, deliberately and as the headline open question** — it is the one thing this feature exists to decide and the one thing a spec should not decide on its author's behalf. |
| 2   | 2026-09-20   | hector | **The identity decision is made, and this entry is the explicit, dated approval Stakeholders and Rules & Constraints require before any metastore-level grant may be built.** *Option B: a new, provisioning-only service principal, `ucmeta-ci-provision`.* `ucmeta-ci-apply` is not widened and is not touched by this feature, so ADR-009's Layer 1 claim — "It is granted nothing else. No create or drop anywhere, no administrative standing at account, workspace or metastore level." — remains true without qualification, and **the amendment obligation F-PLATFORM-004 handed here is discharged by not needing to be met**. Each credential's blast radius stays legible on its own: one identity writes table metadata and cannot create anything; the other creates catalogs and cannot touch a table's metadata. The accepted cost is a second principal to create, grant, document, credential and eventually rotate — real overhead for a solo maintainer, chosen anyway, because a prototype whose entire argument is least-privilege separation by function should not make its first exception the moment separation becomes inconvenient. Two consequences follow rather than being separately argued: the grant script becomes a **new sibling file** alongside `provision_ci_apply_identity.sh` rather than an edit to it, and a second set of automation secrets is needed rather than none. Also resolved: the first real catalog **stays in the workspace permanently as standing evidence** — no manual cleanup step in the live-verification procedure, which is consistent with the create-only rule rather than an exception to it (declining to invent an out-of-band deletion step is not the same as building a deletion capability). Every "Option A / Option B", "whichever identity" and "either way" hedge in Behaviour, Glossary, Rules & Constraints, Out of Scope, Dependencies and both build-verdict tables tightened to describe the one identity that is now real. Zero open questions remain. Frontmatter stays `draft`: the decisions are settled, but nothing here has been built and the build is a step hector asks for explicitly. |
| 3   | 2026-09-20   | hector | **Built and live-verified. The feature's actual deliverable exists: `data_platform_demo`, the first catalog this platform has ever created for real.** Executed by hand against the live Free Edition workspace: `scripts/provision_ci_provision_identity.sh` created `ucmeta-ci-provision` (application ID `b0047725-775f-455e-8b6a-7186fdb4b9b0`), granted it `CREATE_CATALOG` on metastore `metastore_aws_us_east_2` and `CAN_USE` on the warehouse; the credential was minted by hand and stored as three GitHub Actions secrets. **SC-005-02 ran first, deliberately, to capture the pre-grant state before it stopped existing**: as `ucmeta-ci-apply` the run came back `failed` with `PERMISSION_DENIED: User does not have CREATE CATALOG on Metastore 'metastore_aws_us_east_2'`, and the schema and tag writes then failed with `NO_SUCH_CATALOG_EXCEPTION` — a cascade worth recording as evidence rather than noise, because it is the first live proof that the ordered three-step plan F-PLATFORM-004 introduced has a real dependency chain rather than an asserted one. `ucmeta-ci-apply` ended that run holding exactly its original grants: the separation is now a tested property, not a designed one. **SC-005-01 then succeeded as `ucmeta-ci-provision`** — all three writes landed, and re-running produced an identical clean success with no duplicate-object errors, confirming idempotency live rather than only against the fake; re-running the grant script did the same (SC-005-04). Three release-log entries carry `requested_by` distinct from `approved_by`, confirming F-PLATFORM-004's rev-3 audit decision holds live. **One real finding, operational rather than architectural**: the credential was minted with a 30-day lifetime (expires 2026-10-20), not the ~2-year one `ucmeta-ci-apply` uses, so the sibling document's "rotation will most likely never be exercised" reasoning does not carry over and is not copied — this credential genuinely needs rotating. Nothing about the architecture surprised anyone, which is itself the honest headline and is recorded as such in ADR-011 rather than a surprise being manufactured. ADR-011 moved to "Accepted, built, and live"; `docs/ci-service-principal-provision.md`'s first-real-catalog section filled in. Frontmatter moves `draft` → `in-progress`: see the note below the table. |

*On the status change.* `draft` was doing a specific job on this document: it marked the identity
decision as unmade, and then — through revision 2 — as made but unexecuted. Both are now false.
The design is settled, the build exists, and it has run against the live workspace, which is the
same state F-PLATFORM-001, F-PLATFORM-002 and F-PLATFORM-003 describe with `in-progress`. It is
deliberately not `implemented`: two things named in this document have genuinely not happened. The
pipeline has never provisioned a catalog *through a merge* — every live run so far was by hand,
which is the same shape of gap F-PLATFORM-003 recorded as its Layer 3 — and the credential's
30-day lifetime means a rotation falls due on 2026-10-20 that nobody has performed. Calling this
`implemented` would paper over both.

## Users & Roles

- *Platform engineer / account administrator (hector)* — made the identity decision this document
  deliberately declined to make for him (revision 2), runs the grant script that executes it,
  stores the new identity's credential, and performs the first live verification by hand before
  anything is trusted to run unattended. He is the only identity in the workspace that can create a
  catalog today, which is the entire reason this feature exists.
- *`ucmeta-ci-provision` (the new machine identity this feature creates)* — does not exist yet.
  Holds the metastore-level privilege to create catalogs and nothing else: it cannot write a
  table's comment, properties or tags, cannot reach the coverage-history table, and has no
  administrative standing anywhere. It runs the provisioning pipeline's live branch and nothing
  else in this repository. Its credentials belong to no person.
- *`ucmeta-ci-apply` (the existing machine identity)* — created by F-PLATFORM-003, holds
  catalog-, schema-, table- and warehouse-scoped privileges and nothing else, and already has a
  working credential wired into the automation environment. **Untouched by this feature.** It does
  not gain the ability to create catalogs, and it does not run the provisioning pipeline. That is
  the decision revision 2 records, and keeping this bullet short is the point: the most useful
  thing this feature does to `ucmeta-ci-apply` is nothing at all.
- *Requester and reviewer of a catalog request* — unchanged from F-PLATFORM-004 in every respect.
  They author and approve the same file, through the same change request, reviewed the same way.
  The only difference this feature makes to them is that the catalog they asked for afterwards
  actually exists.
- *Interview panel* — must continue to be able to clone or fork the repository, add a request file,
  and watch the provisioning mechanism run to completion with no Databricks account and no secrets
  configured. This is the constraint F-PLATFORM-001 set and every feature since has honoured. It is
  under more pressure here than anywhere else, because this is the feature that gives
  `provision-catalog.yml` a credential-dependent branch for the first time, and a workflow with two
  paths is a workflow that can take the wrong one.

## Behaviour

*A second identity is created, and it does one thing.* Creating a catalog is permitted by a
privilege granted against the metastore as a whole, not against any catalog, schema or table inside
it. No automated identity in this workspace holds one, and rather than giving that standing to the
identity that already writes table metadata, this feature creates a new service principal that has
no other job. `ucmeta-ci-provision` can create catalogs, create schemas inside them and label them.
It cannot write a comment, a property or a tag onto a table; it cannot read or write the platform's
own coverage history; it has no administrative standing anywhere; and no human logs in as it. The
identity that applies contract metadata keeps exactly the privileges F-PLATFORM-003 gave it and
gains none, so the sentence in ADR-009 that says so stays true without a footnote. Two narrow
identities, separated by what they do, is more moving parts than one identity that does both — and
that cost was weighed and accepted, because separation by function is the argument this platform
has been making since F-PLATFORM-003 and the first place to abandon it should not be the first
place it costs something.

*The grant is expressed as a script, not as a memory — and it is a new file.* Because the decision
creates a principal rather than extending one, the script that provisions it is a new sibling
alongside `scripts/provision_ci_apply_identity.sh`, not an edit to it. That follows from the
identity decision rather than being a separate preference: a single script standing up two
identities with two unrelated privilege sets would be harder to read than two scripts each
describing one, and the existing script's own framing — it presents itself as implementing
ADR-009's least-privilege arrangement — stays accurate precisely because nothing is added to it.
The new script is idempotent, takes no credential as input, runs as whatever profile is already
authenticated, and never mints or prints a secret, all in the existing script's style. The rule
this obeys is F-PLATFORM-001's: the workspace is disposable and must be rebuildable from the
repository. A privilege granted by hand in a console and never written down reintroduces exactly
the exception F-PLATFORM-003's grant script was written to close.

*Then the pipeline gains a second path.* Today `provision-catalog.yml` has exactly one branch and
says so loudly in its own output, because F-PLATFORM-004 had no live path to hide. This feature
gives it the shape `apply.yml` already has: a step that reports only whether the necessary
credentials are configured, and two mutually exclusive steps gated on that report — one that
provisions live as `ucmeta-ci-provision`, one that demonstrates the mechanism against the fake and
says plainly that it is doing so. The two are separate steps rather than one step branching
internally, so which one ran is visible in the job's step list and not only in its log text. No
step ever echoes a secret's value.

*Then a real catalog gets created, and somebody watches it happen.* Before the pipeline is trusted
to do this unattended, the same command is run by hand against the live workspace as
`ucmeta-ci-provision`, twice — once to create, once to prove that re-running changes nothing. This
mirrors how F-PLATFORM-003 verified its own live apply, and it exists because the alternative is
discovering whatever the workspace actually does from a failed CI run. Three statements have never
touched a real warehouse: the catalog creation, the schema creation, and the catalog tag write. Any
of them can turn out to behave differently from its table-level cousin, and if one does, the
finding is recorded the way ADR-009 recorded its own surprise — in the document, as what was found,
not smoothed into what was expected.

*And then that catalog stays.* It is not cleaned up afterwards, and that is a decision rather than
an oversight (revision 2). It remains in the workspace as standing evidence that this path really
works — the one artifact a reviewer can be shown that no amount of passing tests substitutes for.
The reasoning is worth being precise about, because there is an apparent tension with
F-PLATFORM-004's create-only rule and it resolves cleanly: keeping the catalog does not add a
delete capability, and deleting it would not have used one either — it would have meant inventing
an out-of-band manual cleanup step that this feature does not otherwise need and that nothing in
the platform performs. Declining to invent that step is consistent with create-only, not an
exception to it. The catalog is named so that it is unmistakably what it is, and its existence is
recorded in this feature's documentation so that nobody later finds it and wonders who made it.

*Then the audit trail carries it.* Nothing about the release record changes. The same append-only
log gets the same shape of line it already gets for a fake provisioning run — which catalog, who
asked, who approved, which writes landed, what the outcome was — except that this time the writes
landed on a real metastore. That continuity is deliberate: a reviewer should not be able to tell,
from the record's shape, that one of these runs was a rehearsal and the other was real, because the
record's job is to describe what changed and not to reassure anybody.

*What does not change, and is worth saying because it would be easy to assume otherwise.* The
request file's shape, the validation that refuses a malformed one, the ordered plan, the
partial-failure semantics, the create-only rule and its single catalog-label exception (which
F-PLATFORM-004 rev 4 widened from `sensitivity` alone to all three classification fields, through
the same one merge write), the idempotence of every statement, and the CLI's behaviour are all
F-PLATFORM-004's and are inherited untouched. In particular, validation remains completely independent of identity: a request that
fails validation is refused identically whether it is being processed by a fake client on a
stranger's laptop or by a privileged service principal against production. That independence was
already proven for apply in SC-003-06 and for provisioning in F-PLATFORM-004's own refusal
scenario; this feature asserts it again under the new identity rather than assuming it survived.

## Glossary

- *Metastore-level privilege*: a permission granted against the metastore as a whole rather than
  against a catalog, schema or table within it. Creating a catalog needs one. Every privilege
  F-PLATFORM-003 granted is scoped below that level, which is why none of them helps here.
- *`ucmeta-ci-provision`*: the provisioning identity this feature creates — a service principal
  holding the metastore-level privilege to create catalogs and nothing else. It runs the live
  branch of the provisioning pipeline and has no other job anywhere in this repository. Settled in
  revision 2; before that this term was written as a placeholder for "whichever identity ends up
  holding the privilege", and it is now a name rather than a role.
- *Separation by function*: the reason there are two machine identities rather than one with two
  jobs. `ucmeta-ci-apply` writes metadata onto tables that already exist and cannot create
  anything; `ucmeta-ci-provision` creates namespaces and cannot write metadata. Neither can do the
  other's work, so neither credential's blast radius has to be explained in terms of the other's.
- *Live branch*: the step in `provision-catalog.yml` that runs `ucmeta provision-catalog --live`
  as `ucmeta-ci-provision`. Does not exist today. Conditional on credentials by construction.
- *Fake branch*: the step that runs the same command without `--live`, against the in-repository
  fake catalogue. Exists today as the workflow's only step; becomes one of two.
- *First real catalog*: the first catalog this platform creates in the live Free Edition workspace
  through the reviewed request-file path. A one-time event this feature exists to produce, and —
  because F-PLATFORM-004 is create-only with no deletion path — an object that then persists.
  Revision 2 settled that it persists *deliberately*, as standing evidence, rather than being
  cleaned up by hand afterwards.
- *Blast radius*: everything an attacker could reach if a specific credential leaked. The unit in
  which the identity decision was argued, exactly as ADR-009 argued its own. Under the decision
  made, there are now two small radii rather than one larger one.
- *Amendment obligation*: F-PLATFORM-004's standing instruction that if this feature closed the gap
  by widening `ucmeta-ci-apply`, ADR-009's least-privilege claim must be amended rather than
  silently outgrown. **Discharged in revision 2 by not arising**: the chosen decision widens
  nothing, so the claim stands unamended. Kept in the glossary because "the obligation was met by
  the decision making it moot" is a materially different outcome from "the obligation was
  forgotten", and only one of those is visible if the term disappears.
- *Fork-safe*: a workflow that still runs, and still demonstrates something real, for somebody who
  clones or forks the repository with no secrets. A hard constraint since F-PLATFORM-001, and the
  property most at risk in this particular feature.

## Scenarios

Conventions for binding tests to scenarios:
- *Backend (pytest)*: `@pytest.mark.scenario("SC-005-01")`, fallback `test_..._sc_005_01`.
- *Workflow-shape assertions*: scenario ID in the test name in the workflow-YAML test module, the
  same binding `apply.yml`'s own credential-gate tests already use.
- *Live verification*: three of these could only be proven against the real workspace, and all
  three were executed by hand on 2026-09-20. What each one actually produced is recorded in its
  own text below rather than only in the Revision History, the same discipline F-PLATFORM-003 used
  once its own live layers ran.

### SC-005-01 — Happy path: the first real catalog, created by automation from a merged request

*Executed live, 2026-09-20 — partially.* The provisioning half of this scenario ran for real and
produced `data_platform_demo`; the *merge-triggered* half did not. Every live run so far has been
a hand-run of the same command the workflow's live branch invokes, which is the same shape of gap
F-PLATFORM-003 recorded as its own Layer 3: the mechanism is wired and proven, and it has never
yet been set off by somebody merging something. The bullets below are marked accordingly rather
than the whole scenario being claimed as passing.

- *Given* `ucmeta-ci-provision` exists, holds the metastore-level creation privilege and nothing
  else, and its credentials are stored in the automation environment's secret store — **true as of
  2026-09-20**: application ID `b0047725-775f-455e-8b6a-7186fdb4b9b0`, `CREATE_CATALOG` on
  metastore `metastore_aws_us_east_2`, `CAN_USE` on the warehouse, three GitHub Actions secrets
  set
- *And* `ucmeta-ci-apply` is untouched and still cannot create anything anywhere — **confirmed
  empirically by SC-005-02 below, not merely by reading the grant script**
- *And* a catalog request file has been authored, opened as a change request, reviewed and approved
  — `catalog-requests/data-platform-demo.yaml` exists in the repository
- *When* the change request is merged into the main branch — **not yet exercised**; every live run
  so far invoked the command directly
- *Then* the provisioning pipeline starts because of the merge, not because anybody ran anything by
  hand — **not yet exercised**, for the same reason
- *And* it reports that a provisioning credential is configured, and takes the live branch — which
  of the two branches ran is visible in the job's own step list, not merely in its log text —
  **not yet exercised live**; the branch exists and its shape is asserted by the workflow tests
- *And* it authenticates as `ucmeta-ci-provision`, never as any person and never as the
  metadata-apply identity — **confirmed**: the live run authenticated through the
  `ucmeta-ci-provision` profile
- *And* the request passes validation, the ordered plan is built and printed, and the three
  statements execute in order against the real workspace — **confirmed**,
  `deployment_status: success`
- *And* afterwards the catalog genuinely exists in the live metastore, the schema named in the
  request exists inside it, and the catalog carries the labels the request declared, each confirmed
  by reading the workspace back rather than by trusting the job's exit code
  — **confirmed**: catalog `data_platform_demo`, schema `demo`, tag `sensitivity: internal`, all
  three writes reported `OK`. *Note, added after this run:* at the time of the live verification the
  tag write carried `sensitivity` only, and only when declared; F-PLATFORM-004 rev 4 subsequently
  widened it to carry `business_area` and `environment` too and made it unconditional. That changes
  what the third statement contains, not that there are three statements or that this one landed —
  the live evidence above stands as recorded.
- *And* one release record is appended naming the catalog, the human who asked, the human whose
  merge authorised it, which writes landed, and the outcome — the same record shape a fake run
  produces, because the record describes what changed and not how convincing the run was —
  **confirmed**, with one honest qualification: `requested_by` and `approved_by` are present as
  separate fields and both read `hectormb.9@gmail.com`, because these were hand-runs with no
  separate reviewer. The distinction is structural and holds; a merge-triggered run is where the
  two fields carry two different names, and that run has not happened yet
- *And* re-running the same provisioning changes nothing further: the catalog is not recreated, the
  schema is not recreated, and the run reports success with nothing new landed — **confirmed**: the
  second run was an identical clean success with no duplicate-object errors. This claim had only
  ever been proven against the in-memory fake before
- *And* this is verified by hand first, twice, before the pipeline is trusted to do it unattended,
  the same way F-PLATFORM-003 verified its own live apply before wiring it to a trigger —
  **done, and it is what the confirmations above are**

### SC-005-02 — Failure case: live provisioning attempted by an identity that has not been granted the privilege

*This is the scenario F-PLATFORM-004 wrote as SC-004-05 and explicitly handed here; that
document's SC-004-05 is now a pointer to this one. It is no longer an inherited placeholder, and
revision 2's decision changed what it is for. When the two options were still open it proved a
transitional state — what things looked like before the grant. Now that the grant goes to a
separate identity, it proves something permanent instead: that `ucmeta-ci-apply` cannot create a
catalog, today and after this feature ships. It is the executable form of the claim ADR-009 makes
in prose, and it is worth running rather than reasoning about, because the exact refusal a real
metastore gives is the evidence that the separation is real.*

***Executed live, 2026-09-20, and deliberately run first** — before the grant existed, because the
pre-grant state is the one piece of evidence that stops being available the moment the feature
works. It passed exactly as written, including the refusal message.*

- *Given* an identity that can reach the workspace and use the warehouse but holds no
  metastore-level creation privilege — which is the state `ucmeta-ci-apply` is actually in, and,
  now that revision 2 has settled the identity decision, the state it **permanently remains in**:
  this scenario is no longer a description of a transitional "before", it is a standing property of
  the metadata-apply identity that should keep passing forever
- *When* a live provisioning run is attempted as that identity — done, as
  `ucmeta provision-catalog catalog-requests/data-platform-demo.yaml --live --profile ucmeta-ci`
- *Then* the request still passes validation, because the request is fine — validation is a content
  layer and access control is a different one, and the failure happens at the write, which is where
  it belongs — **confirmed**: the run reached the write stage, so the plan was built from a request
  the validator accepted
- *And* the catalog creation is refused by the metastore with a permission error naming the identity
  that was refused and the privilege it lacked — **confirmed, verbatim**:
  `ServiceError(error_code=BAD_REQUEST, message="PERMISSION_DENIED: User does not have CREATE CATALOG on Metastore 'metastore_aws_us_east_2'.")`
- *And* the run's outcome is a failure, reported as a failure, recorded in the audit trail, and the
  job exits non-zero — not swallowed, not downgraded, and not retried into looking like something
  else — **confirmed**: `deployment_status: failed`, with a release-log entry
- *And* the error is legible as a *metastore-level privilege* problem rather than anything to do
  with the request file — **confirmed**, and more so than predicted: the message names the missing
  privilege *and* the securable, which is how the metastore's own name
  (`metastore_aws_us_east_2`) was learned in the first place
- *And* **the two writes behind the first one also failed, with `NO_SUCH_CATALOG_EXCEPTION`** — the
  catalog was never created, so the schema and the tag had nothing to attach to. This was not
  predicted in so many words, and it is worth keeping rather than treating as noise: it is the
  first live evidence that the ordered three-step plan F-PLATFORM-004 introduced (rev 3, when
  `default_schema` turned provisioning from one statement into a list) has a **real dependency
  chain** rather than an asserted one. Until this run, step ordering had only ever been exercised
  against a fake that had no way to enforce it. A real metastore enforced it. The all-writes-failed
  outcome also confirms the partial-failure machinery reports `failed` rather than rounding it to
  something tidier
- *And* the exact refusal the workspace actually produces is recorded, rather than the refusal this
  document predicts it will produce — **done, and the prediction was right**. Unlike ADR-009, whose
  live execution overturned its own prediction, nothing about this refusal surprised anyone. That
  is recorded as the finding rather than a surprise being manufactured for symmetry
- *And* because this is now a permanent property rather than a transitional one, it is worth
  re-checking after the grant script has run: the script must leave `ucmeta-ci-apply` exactly as it
  found it, and this scenario passing afterwards is how that is confirmed rather than assumed —
  **confirmed**: `ucmeta-ci-apply` ended the session holding exactly the grants F-PLATFORM-003 gave
  it, and the run itself changed no state at all. The separation is now a tested property rather
  than a designed one

### SC-005-03 — Edge case: somebody forks the repository with no credentials at all

- *Given* a reviewer has cloned or forked the repository, has no Databricks account, and has no
  secrets configured
- *When* they add a request file to the request folder and push to their own main branch
- *Then* the provisioning pipeline runs, does not fail, and does not attempt a live provisioning it
  has no credentials for
- *And* it states plainly that no provisioning credential is configured and that it is therefore
  demonstrating the mechanism against the in-repository fake catalogue
- *And* the catalog and its schema genuinely appear in that in-memory catalogue and the run can say
  so — still a real demonstration of the mechanism, not a dry-run print
- *And* the distinction between "no credential configured, so this ran against the fake" and "a
  credential was configured and the live provisioning failed" is unmistakable in the job's output,
  because those two outcomes must never be confused with each other
- *And* every other credential-free path is untouched
- *This scenario matters more here than it did in F-PLATFORM-004, and the reason is worth stating:
  that feature was fork-safe trivially, because the workflow had no live branch to take by mistake.
  This feature removes that guarantee-by-construction and replaces it with a guarantee-by-condition.
  The workflow-shape tests that currently assert `provision-catalog.yml` contains no `--live`
  anywhere will become false and must be narrowed rather than deleted — exactly the move
  F-PLATFORM-003 made when it narrowed the same assertion for `apply.yml`, and for exactly the same
  reason*

### SC-005-04 — Edge case: the grant script is re-run against an already-provisioned workspace

*Executed live, 2026-09-20. The script was run twice against the real workspace and the second run
was a clean no-op, which is the only way this property can actually be established.*

- *Given* the new sibling grant script has already been run once, and `ucmeta-ci-provision`, its
  entitlements and its metastore-level privilege are all in place
- *When* somebody runs the script again — rebuilding the workspace, verifying the script still
  works, or simply not remembering whether it was run
- *Then* it succeeds, changes nothing further, and says so — **confirmed**: the second run reported
  "Already exists: id=… Skipping creation", entitlements "present (… no-op)", and re-applied every
  grant without error
- *And* creating the identity is guarded by a lookup first rather than attempted blindly, and every
  grant is expressed as an additive change, which is how the existing grant script already achieves
  this property — **confirmed** by the output above
- *And* running it does not touch `ucmeta-ci-apply` in any way — the two scripts provision two
  identities and neither reaches into the other's, which is the practical form of the separation
  revision 2 chose and the reason this is a sibling file rather than an extension — **confirmed**,
  and SC-005-02's post-grant re-check is the assertion that proves it rather than the script's own
  output being taken at its word
- *And* running *both* scripts, in either order, against a workspace rebuilt from nothing
  reproduces the entire arrangement — that is what "rebuildable from the repository" has to mean
  once there are two identities rather than one. **Not exercised**: the workspace has not been torn
  down and rebuilt from empty, and doing so to prove this would cost more than the claim is worth
  right now. What *is* established is that each script is individually idempotent against a
  workspace where its own identity already exists, which is the weaker half of the claim. The
  stronger half remains reasoned rather than tested, and is named here as such
- *And* the script never mints, reads or prints a credential — that remains a deliberate manual,
  once-only act performed through the workspace's own console, for the same reason F-PLATFORM-003
  gave: scripting it would require a credential strictly worse to have lying around than the one it
  would produce
- *And* the whole arrangement this feature creates can be rebuilt from the repository alone, so the
  disposable-workspace rule survives this feature rather than acquiring a second exception

### SC-005-05 — Failure case: a merged request fails validation, and the privileged identity refuses it identically

- *Given* a request file that fails validation — a missing required field, an illegal catalog or
  schema name, an unresolvable business application, or a file that does not parse at all — reaches
  the main branch
- *When* the live pipeline processes it as `ucmeta-ci-provision`
- *Then* the request is refused whole, before any statement is built or executed, and zero writes
  of any kind reach the metastore
- *And* the refusal is byte-for-byte the same refusal a fake run would produce, naming the same
  problems: the elevated privilege this feature grants is an access-control capability and does not
  bypass, weaken or shortcut the validation gate
- *And* a refusal record is still published, and the job still exits non-zero
- *And* this composes for free rather than needing new code — the refusal happens in the
  provisioning module before any client method is called, so it cannot depend on which client is
  behind the seam. The scenario exists to *prove* that rather than to assert it, which is the same
  reason SC-003-06 exists: a privileged identity that skipped validation because it was privileged
  would mean this feature had quietly traded one gap for another

## Data

| Data | Source | Direction | Sensitivity |
|------|--------|-----------|-------------|
| The identity decision itself — that a second principal holds the creation privilege, and why | Recorded in this document's Revision History (rev 2) and in this feature's ADR | Write (as documentation) | Internal |
| `ucmeta-ci-provision` (display name and application identifier) | Created in the workspace by the new sibling grant script | Read (referenced by that script, by the workflow and by documentation) | Internal |
| Machine credential for `ucmeta-ci-provision` | Minted once by the workspace, by hand — a second credential, distinct from `ucmeta-ci-apply`'s and never shared with it | Write (into the automation secret store only) | Confidential — never in the repository, never in logs, never in a job's output |
| Credential expiry date | Returned when the credential is minted | Read (recorded in documentation so rotation is not a surprise) | Internal |
| The metastore-level creation privilege grant | Declared in the new checked-in sibling script, applied to the workspace | Write (to the workspace), R/W (as a repository file) | Internal |
| Whether a provisioning credential is configured | The automation environment's secret store — presence only, never the value. A second set of secrets, separate from the apply identity's three | Read | Confidential (the values; the presence flag is Internal) |
| The catalog request being provisioned | An authored, reviewed, merged request file | Read | Internal |
| The first real catalog, its schema and its label | Created in the live metastore, and retained there permanently as standing evidence (rev 2) | Write | Internal |
| The exact statements executed against the real warehouse | Built by the client seam and returned by it, unchanged from F-PLATFORM-004 | Read (printed as a plan, then executed) | Internal |
| The refusal a metastore actually gives an ungranted identity | Observed during SC-005-02, recorded verbatim | Read (recorded as evidence) | Internal |
| Provisioning audit record | Generated per run, unchanged in shape from F-PLATFORM-004 | Write | Internal |

## Rules & Constraints

- *The metastore-level privilege goes to a new, provisioning-only identity — settled in revision 2,
  with its reasoning recorded there rather than only in its outcome.* `ucmeta-ci-provision` is
  created for this purpose; `ucmeta-ci-apply` is not widened. That entry is the dated, explicit
  approval this feature required before any grant could be designed, the same ceremony
  F-PLATFORM-003 used for its Layer 2 and for the same reason: this is a change to who may do what
  on a live workspace, it is cheap to make and awkward to unmake, and a decision of that shape
  should not be inferable only from a diff.
- *`ucmeta-ci-apply` is not modified by this feature, in any respect.* Not widened, not re-granted,
  not renamed, not reused for provisioning. ADR-009's Layer 1 claim about what it holds stays
  literally true and needs no amendment. If an implementer finds themselves editing
  `scripts/provision_ci_apply_identity.sh`, that is the signal the decision has been misread.
  SC-005-02 exists partly to catch exactly that by re-checking the property after the new script
  has run.
- *Approving this document is not permission to execute the grant against the live workspace.*
  Revision 2 approves the design — which identity, holding what, expressed how. Creating the
  principal and running the grant against the real workspace is a step hector asks for explicitly.
  Anyone reading this section looking for standing permission to run a `GRANT CREATE CATALOG`
  should not find it here.
- *The grant is expressed in a checked-in script, and that script is a new sibling file.* Not an
  extension of the apply identity's script. This follows from the identity decision rather than
  being an independent preference: two identities with two unrelated privilege sets are easier to
  read as two scripts, and the existing script's own self-description — it presents itself as
  implementing ADR-009's least-privilege arrangement — stays accurate only because nothing is added
  to it. Both scripts together must reproduce the whole arrangement from an empty workspace, which
  is what F-PLATFORM-001's disposable-workspace rule now requires of a two-identity setup.
- *The grant made is the narrowest one that lets the pipeline do its job, and nothing that is
  merely convenient.* Provisioning performs three statements: create a catalog, create a schema
  inside it, and set tags on the catalog. `ucmeta-ci-provision` gets what those need and stops — no
  table privileges, nothing on the coverage-history table, no administrative standing anywhere. The
  narrowness is the same deliverable it was in F-PLATFORM-003, and a provisioning identity granted
  metastore administration would be a personal access token with extra steps.
- *The script never mints or prints a secret.* Inherited verbatim from F-PLATFORM-003. Credential
  creation stays a manual, once-only act through the workspace's own console, and the repository
  holds only the *names* of the secrets it expects — now two sets of names rather than one, kept
  visibly distinct so that a credential for one identity can never be pasted into the other's slot
  without it being obvious.
- *The workflow's live branch is conditional on credentials, and the two branches are mutually
  exclusive steps rather than one step branching internally.* This is `apply.yml`'s shape and it is
  copied rather than reinvented, because the property it buys — which branch ran being visible in
  the job's step list — is the property SC-005-03 depends on. No step echoes a secret's value.
- *Fork-safety stops being free in this feature, and the tests must change to match.* The
  workflow-shape test module currently lists `provision-catalog.yml` among the workflows that never
  pass `--live`, and carries three further assertions that it has no live path at all. Every one of
  those becomes false. They must be *narrowed* — replaced by the conditional-gate and
  no-secret-echoed assertions that already exist for `apply.yml` — and not deleted, which is the
  precise move F-PLATFORM-003 made when this same assertion first stopped being true for
  `apply.yml`. Deleting an assertion that has become inconvenient is how a test suite stops meaning
  anything.
- *The first live run is performed by hand before the pipeline is trusted with it.* Twice: once to
  create, once to prove re-running changes nothing. Three statements in this pipeline have never
  been parsed by a real warehouse, and discovering their behaviour from a red CI run is strictly
  worse than discovering it from a terminal.
- *Whatever the live workspace actually does is what gets recorded, including if it contradicts
  this document.* ADR-009's most valuable content is the paragraph describing the thing its authors
  predicted wrongly. If `ALTER CATALOG ... SET TAGS` behaves unlike its table-level cousin, if the
  creation privilege turns out to be named or scoped differently than expected, or if the refusal in
  SC-005-02 is not the refusal predicted here, the finding is written up as found. A scenario that
  describes a cleaner outcome than the one the workspace produces is worse than no scenario.
- *Nothing about F-PLATFORM-004's behaviour changes.* Not the request shape, not the validation,
  not the ordered plan, not the partial-failure semantics, not the create-only rule and its single
  catalog-label exception, not idempotence, not the release-record shape, not the CLI. This
  feature adds an identity, a grant, a branch and a verification. If the build finds itself editing
  `provision_catalog.py`, that is a signal something has been misunderstood.
- *Validation stays independent of identity.* The privilege this feature grants is an
  access-control capability only. It does not bypass, weaken or shortcut the content gate, and
  SC-005-05 exists to prove that rather than assert it.
- *No manual trigger, no break-glass path.* The live branch fires on merge, like everything else.
  No workflow dispatch, no "provision this one by hand because it is urgent". The same rule
  F-PLATFORM-003 and F-PLATFORM-004 both state, for the same reason.
- *The first real catalog is kept, deliberately and permanently — settled in revision 2.* It is not
  cleaned up after verification, and no manual deletion step forms part of this feature's
  procedure. It stays as standing evidence that the path works, which is the one artifact a
  reviewer can be shown that a green test run does not substitute for. **This is consistent with
  F-PLATFORM-004's create-only rule rather than an exception to it**, and the distinction is worth
  being exact about: keeping the catalog adds no delete capability, and deleting it would not have
  used one either — it would have meant inventing an out-of-band manual cleanup step that nothing
  in this platform performs and that this feature does not otherwise need. Create-only constrains
  what the *software* may do; it says nothing about whether a human tidies up afterwards, and
  declining to invent that chore is not a loophole. What the rule does still demand is that the
  object not be a mystery: it is named so its purpose is unmistakable, and its existence is
  recorded in this feature's documentation so nobody finds it later and wonders who made it.

## Non-functional Requirements

Brief. This feature adds one identity, one grant, one branch and one credential to a prototype; the
substance was in the decision, not in the engineering.

- *Security — the whole point, and now decided.* `ucmeta-ci-provision`'s credential, if it leaked,
  would let an attacker create catalogs and schemas in a free, disposable, non-commercial workspace
  containing no business data, and label what they created. It could not read or write a single
  table's data or metadata, could not touch the platform's coverage history, could not reach the
  account, and could not impersonate a person. `ucmeta-ci-apply`'s credential, if it leaked, would
  let an attacker vandalise the metadata on three synthetic tables — exactly as before this
  feature, unchanged. The two radii are small, disjoint and separately revocable, which is the
  property the decision bought and the reason the second credential's overhead was accepted. Each
  credential lives only in the automation environment's secret store, is entered by hand once, is
  never in the repository or a job's output, and is revocable in one call.
- *Security — what this feature does not claim.* No separation of duties between *people* (the same
  person holds every role in a solo prototype — the separation here is between machine identities
  by function, which is a different and weaker claim), no short-lived credential, no secret
  scanning, no automatic rotation, no leak detection. All are real production requirements; none is
  built. Same position F-PLATFORM-003 took and for the same reasons.
- *Performance.* Three statements per request against a serverless warehouse, dominated
  entirely by cold-start. (Read "two or three" here before F-PLATFORM-004 rev 4 made the tag write
  unconditional; the count this feature actually ran was three.) Nothing here threatens any budget
  this project has set.
- *Scale.* One new identity, one grant, one credential, one catalog — and, across the repository as
  a whole, two machine identities rather than one. Deliberately small. The question this feature
  answers is whether the thing works at all, not how it behaves at volume; the question the
  *second* identity raises — whether a maintainer can keep two credentials straight — is answered
  by documenting both in the same place rather than by any mechanism.
- *Availability.* Degrades the way provisioning already degrades: unreachable workspace means a
  loud failure with the reason named and an audit record saying what happened; a missing or expired
  credential fails at authentication with a message that does not look like a permissions problem;
  a fork with no credential does not fail at all and runs the mechanism against the fake.
- *Retention.* Unchanged for audit records: one per attempt, kept for as long as the repository
  exists. The first real catalog is retained indefinitely *on purpose* (rev 2) rather than by
  default — it is evidence, and evidence that gets tidied away stops being evidence.
- *Regulatory.* None assumed, consistent with all four preceding specs.

## Out of Scope

- *Any change to F-PLATFORM-004's provisioning behaviour.* The request shape, validation, plan,
  partial-failure handling, create-only rule, idempotence, audit record and CLI are all inherited
  untouched and are not this feature's to revisit.
- *A deletion or lifecycle path for catalogs.* Still create-only. This feature makes the
  consequences of that rule concrete by creating something real and then deliberately keeping it
  (rev 2), but it does not build a delete verb and does not add a manual cleanup step in place of
  one. That remains a separate feature with its own security argument.
- *Widening `ucmeta-ci-apply`, now or as a later convenience.* Ruled out in revision 2, not merely
  passed over. A future change that quietly grants that identity creation rights would undo the
  separation this feature is built on and would falsify ADR-009 without anybody having decided to
  — named here so that a later implementer looking for the cheap path finds it explicitly closed.
- *Granting the requesting team any access to the catalog they asked for.* The gap F-PLATFORM-004
  named between "a catalog and a schema exist" and "the team can use them" is unchanged by this
  feature. Provisioning an object and granting somebody access to it are different acts, and only
  the first is here.
- *Additional schemas, tables, or anything else inside the new catalog.* Exactly one schema, the one
  the request names.
- *Removing the owner from the metastore-admin group.* ADR-009's documented, unclosed gap — the
  metastore-admin tag-write bypass — is untouched, unaffected and out of scope, exactly as
  F-PLATFORM-003 left it.
- *OpenID Connect federation instead of a stored secret.* Still the better production answer and
  still deliberately not built. Worth noting that the identity decision makes it slightly more
  attractive rather than less: there are now two stored secrets that federation would remove
  instead of one. Named as the direction of travel, as it already is in ADR-009.
- *Secret rotation as an operational practice.* A procedure and an expiry date get written down for
  the new credential as they were for the existing one; no scheduled rotation, no expiry-check
  step, for either. This was written expecting the minimal position F-PLATFORM-003 settled on to
  apply twice over. **Live minting partly invalidated that**: the new credential came out with a
  30-day lifetime rather than a ~2-year one, and F-PLATFORM-003's reasoning for the minimal
  position — that rotation would probably never be exercised because the credential would outlive
  the workspace — depends on a lifetime this one does not have. So the *procedure* stays out of
  scope as automation, but a real rotation falls due on 2026-10-20, and
  `docs/ci-service-principal-provision.md` records it as something that will have to happen rather
  than something that probably will not.
- *Applying the same treatment to any other workflow.* `validate.yml` and `coverage.yml` keep their
  credential-free character and are not this feature's business.
- *Retrofitting live provisioning into the demo's critical path.* Whether the interview walkthrough
  actually performs a live provisioning, or shows the fake path and refers to the one real catalog
  as evidence, is a rehearsal decision and not a build decision. Nothing here assumes the former.

## Dependencies

- *Related features*:
  - *F-PLATFORM-004* — this feature's charter. It built everything this one composes and explicitly
    named, deferred and handed over everything this one does: its Out of Scope says the live path
    "belongs to F-PLATFORM-005" in every form, its build-verdict table carries three rows marked
    *Move to F-PLATFORM-005*, and its SC-004-05 was written to be inherited here. The reasoning
    behind the split is recorded there and is not re-derived in this document. Its "not yet drafted"
    references become pointers to this spec.
  - *F-PLATFORM-003* — supplies the grant-script pattern this feature copies into a sibling file,
    the credential-gated two-branch workflow shape it copies, the live verification discipline it
    copies, and the least-privilege argument it **honours by separation rather than amending**. It
    also supplies the identity this feature deliberately leaves alone: `ucmeta-ci-apply` is a
    dependency in the sense that its untouched state is a property SC-005-02 asserts, not in the
    sense that anything here modifies it. It is the precedent for gating a consequential permission
    change on its own explicit, dated approval rather than on approval of the document describing
    it — a precedent this feature followed in revision 2.
  - *F-PLATFORM-001* — the disposable-workspace rule this feature must not violate, the
    interview-panel fork-safety guarantee it puts under more pressure than any previous feature,
    and the no-long-lived-personal-tokens position that makes a service principal the only
    acceptable shape for what is being granted.
  - *Consequence found later, recorded in F-PLATFORM-001 rev 6 (2026-09-20).* The fork-safety
    guarantee this feature puts under pressure turned out to be already broken by the real catalog
    it produced: the first contract written for a table in `data_platform_demo` failed the
    credential-free `validate.yml` path outright, because `FakeUCClient` had no fixture entry for a
    table that did not exist when its fixture set was written. Fixed in F-PLATFORM-001, not here —
    the fake's fixture set is now a maintained mirror of every contracted table. Noted so the link
    is discoverable from this end; no decision of this feature's changes.
  - Likely follow-ons: granting requesting teams access to the catalogs they receive; catalog
    lifecycle beyond creation; OpenID Connect federation replacing the stored secret.
- *ADRs*:
  - *ADR-009* (*A machine identity for apply, and taking the human's write access away*) —
    **untouched, and that is the outcome rather than an omission.** Its Layer 1 section states, of
    `ucmeta-ci-apply`: *"It is granted nothing else. No create or drop anywhere, no administrative
    standing at account, workspace or metastore level."* Revision 2's decision leaves that sentence
    literally true, so the amendment obligation F-PLATFORM-004 handed to this feature is discharged
    by not arising. No edit is made to ADR-009 by this feature, and an implementer who finds
    themselves opening it to soften a claim has taken a path this spec rules out. What ADR-011 owes
    it instead is a forward reference, so a reader of ADR-009 learns that a second identity exists
    and why it was not this one.
  - *ADR-010* — proposed by F-PLATFORM-004 and, per the repository's `docs/` as it stands, not yet
    written. Noted here so it is not assumed to exist. Whether it is written before or alongside
    this feature's own ADR is a sequencing detail, not a dependency.
  - *ADR-011 (proposed) — A second machine identity, so the first one did not have to grow.* The
    decision is made; the ADR is written when the feature is built. It must record: both options
    and the case for each, argued as fairly as they are in this document's Open Questions rather
    than retrofitted to justify the winner — the rejected option was genuinely cheaper, and an ADR
    that hides that is not worth writing; the decision and its actual reasoning, including the part
    that is about not wanting to falsify a claim the project had just finished making, which is a
    legitimate reason and not merely an aesthetic one; the overhead accepted in exchange — a second
    principal, a second credential, a second set of secrets, a second rotation date — stated
    plainly rather than minimised, since a solo maintainer carrying two credentials is a real cost
    and the reader should be able to judge whether it was worth it; what each identity can reach if
    its credential leaks, stated as concretely as ADR-009 stated its own, and noting that the two
    radii are disjoint; that ADR-009 is left intact and why that was a goal rather than a
    coincidence, with a forward reference added there; and whatever the live workspace turned out
    to actually do that this document predicted wrongly. That last section is the one a reviewer
    will find most interesting, on the evidence of ADR-009.
- *Code modules* (in `uc-metadata-platform`), separated into what this feature changes and what it
  deliberately does not:
  - `scripts/provision_ci_provision_identity.sh` (or a name that reads better beside it) — a **new
    file**, sibling to `provision_ci_apply_identity.sh`. Creates `ucmeta-ci-provision` idempotently,
    adds the entitlements a service principal needs before it can call any workspace API at all
    (the existing script records this as a real finding worth not rediscovering), grants the
    metastore-level creation privilege and the warehouse `CAN_USE` the statements execute through,
    and nothing else.
  - `scripts/provision_ci_apply_identity.sh` — **not edited.** Listed explicitly among the changed
    files so its absence from the diff is a deliberate, checkable fact rather than an oversight.
  - `.github/workflows/provision-catalog.yml` — gains a credential-check step and two mutually
    exclusive provisioning steps; loses its unconditional "no live path" declaration.
  - `tests/unit/test_workflows_yaml.py` — `provision-catalog.yml` comes out of the
    credential-free list, and its three no-live-path assertions are replaced by the
    conditional-gate and no-secret-echoed assertions `apply.yml` already has.
  - `docs/` — a record of `ucmeta-ci-provision`: its display name, application identifier, every
    grant and why, its credential expiry, the rotation procedure and the manual secret-entry steps.
    Mirrors `ci-service-principal.md`'s structure. One judgment call for the implementer, flagged
    rather than dictated: a sibling document keeps each identity's story self-contained, while
    extending the existing one puts both credentials on a single page — which, now that a
    maintainer has two to keep straight, may be the more useful property. Either satisfies this
    spec; whichever is chosen, both identities must be findable from one place.
  - `catalog-requests/` — one real request file, if the live verification is driven through the
    merge path rather than by hand. Today this folder contains only its template.
  - **Untouched, and that is the point**: `src/uc_metadata/uc_client.py`,
    `src/uc_metadata/provision_catalog.py`, `src/uc_metadata/fake_uc.py`,
    `src/uc_metadata/cli.py`, `src/uc_metadata/release_log.py`, `change_classes.yaml`,
    `catalog-requests/_template.yaml`.

### Build verdicts per component

Principle for this table specifically: *most of this feature is already built, and saying so
precisely is more useful than listing it as work.* The first table is what F-PLATFORM-004 already
delivered and this feature must not rebuild — every row was confirmed by reading the current code,
not inferred from that spec's promises. The second is the actual work. **As of revision 3 the
second table is a record rather than a plan**: every row in it has been built, and the ones that
could only be proven against the real workspace were executed by hand on 2026-09-20. Rows that
remain undone say so explicitly rather than being quietly marked complete.

**Already built under F-PLATFORM-004 — nothing to do here**

| Component | Verdict | Confirmed by reading the code |
|---|---|---|
| `create_catalog` on the `UCClient` protocol and on `RealUCClient` | *Exists — do not rebuild* | Both present. The real implementation emits `CREATE CATALOG IF NOT EXISTS <ident>` plus an optional `COMMENT`, honours `dry_run`, and returns the statement either way. Never yet executed against a live warehouse — which is this feature's job, not a gap in the method. |
| `create_schema` on the protocol and on `RealUCClient` | *Exists — do not rebuild* | Both present; emits `CREATE SCHEMA IF NOT EXISTS <catalog>.<schema>`, same `dry_run` and return discipline. |
| `set_catalog_tags` on the protocol and on `RealUCClient` | *Exists — do not rebuild; and its live behaviour is now settled* | Both present; emits `ALTER CATALOG <ident> SET TAGS (...)` with merge semantics, mirroring the table-tag method. Flagged in revision 1 as the statement of the three whose live behaviour was least certain — it turned out to be the least eventful: the label landed on the first live run with no dialect or granularity difference from `set_table_tags`. |
| `src/uc_metadata/provision_catalog.py` in full | *Exists — do not rebuild, and do not edit* | The request model, `load_catalog_request` (never raises; every malformed-file path produces a named refusal), `plan_provision`, `provision`, the ordered three-step plan, partial-failure handling, refusal-before-write, and release-record publication for every outcome. Note for the implementer: `provision()` takes a *request path*, not a pre-loaded request — a deliberate deviation from `apply()`'s shape, documented in the module, and the live branch must call it the same way. |
| `ucmeta provision-catalog` CLI verb, including `--live` and `--profile` | *Exists — and this is the pleasant surprise* | The verb already wires the shared client arguments, so `ucmeta provision-catalog <path> --live --profile <name>` is already a working command. F-PLATFORM-003's finding that `RealUCClient` resolves an arbitrary named profile with zero code changes holds here unchanged. **No CLI work at all is needed for the live path** — only a workflow that passes the flags and an identity permitted to use them. |
| `provision-catalog.yml`'s changed-path diff, template carve-out, per-file loop and approver resolution | *Exists — extend, do not replace* | The push trigger, `git diff` against the push event's SHAs with the first-push guard, the `catalog-requests/*.yaml` filter excluding `_template.yaml`, the loop, and `--approved-by ${{ github.actor }}` are all in place and identical in shape to `apply.yml`'s. This feature adds a branch beside them; it does not touch them. |
| Release-record integration | *Exists — unchanged* | Every outcome already publishes one record through the existing append-only log, including the requester field. A live run produces the same record shape as a fake one, deliberately. |
| `catalog-requests/_template.yaml`, `change_classes.yaml` routing, the fake implementation and its tests | *Exists — untouched* | The authoring surface, the slow-path routing declaration, and the entire offline test suite are unaffected by this feature. |

**This feature's actual new work**

| Component | Verdict | Rationale (one line) |
|---|---|---|
| The identity decision | *Done — resolved in revision 2, no build attached* | Option B: a new, provisioning-only `ucmeta-ci-provision`. The only row in this table that was work for hector rather than for an implementer, and it is closed. Every row below is now shaped by it. |
| `ucmeta-ci-provision`, created in the workspace | *Built — created live, 2026-09-20* | Application ID `b0047725-775f-455e-8b6a-7186fdb4b9b0`, workspace-internal ID `75972948747339`. A second service principal whose entire job is creating catalogs. Default-deny at birth, so everything it holds is something the grant script deliberately added. |
| The metastore-level grant to `ucmeta-ci-provision`, executed against the live workspace | *Built — granted live, and it worked on the first attempt* | `CREATE_CATALOG` on metastore `metastore_aws_us_east_2` (`84f1ebb2-8db7-4748-9e66-c03d091fd89c`) plus warehouse `CAN_USE`, and nothing else. The grant type, the securable it attaches to and the SDK constant names were all exactly as predicted from reading the SDK source — no scoping or naming surprise to record. |
| A **new sibling** grant script, `scripts/provision_ci_provision_identity.sh` | *Built — and run live twice, second run a clean no-op* | Keeps the workspace rebuildable from the repository. Idempotency confirmed live (SC-005-04), not only reasoned: "Already exists … skipping creation", entitlements "present (… no-op)", grants re-applied without error. |
| `scripts/provision_ci_apply_identity.sh` | *Untouched — and now verified so, not just asserted* | The existing script is unchanged. More usefully, `ucmeta-ci-apply` was confirmed after the session to hold exactly the grants F-PLATFORM-003 gave it, via SC-005-02's post-grant re-check — the separation is a tested property rather than a property of a diff nobody read. |
| `provision-catalog.yml`'s credential check and two mutually exclusive branches | *Built — but the live branch has never fired* | `apply.yml`'s exact pattern, and the three secrets it reads are now configured on the real repository. What has not happened is a merge actually triggering it: every live provisioning so far invoked the command by hand. Same shape of gap F-PLATFORM-003 recorded as its Layer 3, and named rather than glossed. |
| Narrowing the workflow-shape tests | *Built* | `provision-catalog.yml` left the credential-free list and its three no-live-path assertions were replaced by the conditional-gate and no-secret-echoed assertions `apply.yml` already carries — narrowed, not deleted, which was the whole reason the row called it out. |
| A second set of automation secrets, for `ucmeta-ci-provision` | *Done — set on the real repository* | `DATABRICKS_CI_PROVISION_HOST` / `_CLIENT_ID` / `_CLIENT_SECRET`, set by hand via `gh secret set`, deliberately distinct from the apply identity's three. The secret value never entered a transcript, a file or a log. |
| Live verification by hand, twice, before trusting the pipeline | *Done — and it is the evidence* | Both runs succeeded identically; the second produced no duplicate-object errors, confirming idempotent creation live rather than only against the fake. Mirrors how F-PLATFORM-003 verified its own live apply. |
| SC-005-02 executed as `ucmeta-ci-apply`, both before and after the grant | *Done — and it produced the run's most quotable artifact* | `PERMISSION_DENIED: User does not have CREATE CATALOG on Metastore 'metastore_aws_us_east_2'`, plus two cascading `NO_SUCH_CATALOG_EXCEPTION` failures that turned out to be the first live proof the ordered plan's dependency chain is real. Run before the grant, which is the only time that evidence is obtainable. |
| The first real catalog, kept | *Done — `data_platform_demo` exists* | Catalog `data_platform_demo`, schema `demo`, tag `sensitivity: internal`, created 2026-09-20 from `catalog-requests/data-platform-demo.yaml` (`BA-40092`, requested by `hectormb.9@gmail.com`, `bronze`). Kept permanently as standing evidence, recorded in `docs/ci-service-principal-provision.md` so nobody later wonders who made it. No cleanup step. |
| `docs/` record of `ucmeta-ci-provision` | *Built — `docs/ci-service-principal-provision.md`* | A sibling document rather than an extension, with cross-links both ways so either identity is findable from the other. Carries one finding the design did not anticipate: the credential's **30-day** lifetime, and an explicit note that `ucmeta-ci-apply`'s "rotation will probably never happen" reasoning does not carry over to it. |
| Rotating the provisioning credential before 2026-10-20 | *Outstanding — the one live task this feature leaves behind* | Not a design gap; a consequence of the credential's actual 30-day lifetime. Either mint a longer-lived replacement matching the apply identity's convention, or accept a real rotation cadence. Undecided, and deliberately left to whoever maintains this past that date. |
| ADR-011 | *Built — shipped, and now updated with the live findings* | Status moved to "Accepted, built, and live". **ADR-009 is not amended** — the decision left its claim intact, discharging the amendment obligation by not raising it, and ADR-011 owes it only a forward reference. Its "what the live workspace actually did" section is filled in, and its honest headline is that there was no architectural surprise — unusual for this project, and recorded as the finding rather than a surprise being manufactured for symmetry with ADR-009. |
| Updating F-PLATFORM-004's "not yet drafted" pointers | *Done* | Its SC-004-05, Dependencies entry and index line now point here. |
| A catalog deletion path, or a manual cleanup step standing in for one | *Skip — named in Out of Scope* | Create-only is a deliberate security property, not a missing feature. Revision 2 answered the cleanup question by keeping the catalog, so neither a delete verb nor an out-of-band tidying chore is built. |
| Widening `ucmeta-ci-apply` | *Skip — ruled out, not passed over* | The cheaper option, considered fairly and rejected in revision 2. Named as a skip so a later implementer looking for the shortcut finds it explicitly closed rather than merely unmentioned. |
| Any change to `provision_catalog.py` or `uc_client.py` | *Skipped — and it held through live execution* | Neither file was touched at any point. The three client methods F-PLATFORM-004 built ran against a real warehouse for the first time with no modification at all, which is the strongest available evidence that the seam was drawn in the right place. |

## Open Questions

No rows remain open as of revision 2. All three were answered in one pass, and the first of them —
the identity choice — was the whole reason this feature exists as a separate document:
F-PLATFORM-004 declined to settle it in passing so that it would not ride on the wrong approval,
this spec declined to settle it on its author's behalf, and hector settled it deliberately with the
reasoning recorded. Resolved rows are kept rather than deleted, following the convention
F-PLATFORM-001, F-PLATFORM-003 and F-PLATFORM-004 all set: the argument behind a settled decision
is the expensive part to reconstruct later, and the rejected option here was genuinely the cheaper
one, which is exactly the kind of thing a reader six months from now will want to see was weighed
rather than overlooked. The document stays `draft`: the decisions are settled, but nothing has been
built and the build is a step hector asks for explicitly.

| Question | Owner | Due | Status |
|----------|-------|-----|--------|
| **Which identity holds the metastore-level `CREATE CATALOG` privilege?** *Option A — widen `ucmeta-ci-apply`.* Cheapest by a distance: the identity exists, its credential is already minted and stored, its GitHub secrets are already wired, its local profile already works, and the workflow already knows its name. One grant and it is done, with no second credential to store, document, rotate or keep straight. The cost is precise and it is not small: ADR-009's Layer 1 says of this identity, in as many words, *"It is granted nothing else. No create or drop anywhere, no administrative standing at account, workspace or metastore level."* Option A makes that sentence false. The blast radius of that one credential grows from "vandalise the metadata on three synthetic tables" to "create arbitrary namespaces in the metastore", and the ADR must be amended to admit the claim narrowed and to say why that was acceptable. The honest framing is that it trades a documented least-privilege property for operational simplicity. *Option B — a second, provisioning-only identity (`ucmeta-ci-provision`).* Preserves ADR-009's claim completely intact: the apply identity keeps doing exactly what it always did, and the new identity does one thing and holds one privilege, so each credential's blast radius stays legible on its own. It is also the shape the production answer would take, since separation by function is the whole argument F-PLATFORM-003 made. The cost is a second service principal to create, grant, document, credential, store secrets for and eventually rotate — real overhead for a solo maintainer, and more moving parts in a prototype whose other virtue is that a reviewer can hold all of it in their head. A fair summary of the trade: Option A is cheaper to build and more expensive to explain; Option B is more expensive to build and defends itself. Both are reversible, though not equally — Option A is undone by revoking a grant and re-amending an ADR, Option B by deleting a principal nobody depended on. | hector | 2026-09-20 | *resolved: Option B — a new, provisioning-only `ucmeta-ci-provision`.* `ucmeta-ci-apply` is not widened and is not touched, so ADR-009's Layer 1 claim stays literally true and the amendment obligation is discharged by not arising. The cheaper option was rejected knowingly: a prototype whose entire argument is least-privilege separation by function should not make its first exception at the first moment separation costs something, and falsifying a claim the project had just finished making would have been a worse trade than carrying a second credential. The overhead — a second principal, credential, secret set and rotation date — is accepted and named rather than minimised. This resolution is also the dated approval Stakeholders and Rules & Constraints require before any grant may be designed; executing it against the live workspace remains a separately-requested step. |
| Does the grant script extend `scripts/provision_ci_apply_identity.sh`, or become a sibling script of its own? Largely settled by the answer above, and flagged separately because the two cases differ. Under Option A, extending the existing script keeps one file describing one identity, at the cost of that script's own framing — it currently presents itself as implementing ADR-009's least-privilege arrangement, and the grant being added is the one that arrangement excluded. Under Option B, a sibling is close to forced, since it provisions a different principal with a different purpose, and a single script creating two identities with two unrelated privilege sets would be harder to read than two scripts. A secondary consideration either way: the existing script's closing output describes the exact boundary it does and does not achieve, and whatever is written must keep that habit rather than quietly inheriting a summary that is no longer accurate. | hector | 2026-09-20 | *resolved: a new sibling script — and resolved as a consequence, not as a preference.* Hector's instruction was to let this follow from the identity choice rather than fixing a rule independently, and since that choice creates a principal rather than extending one, a sibling file is what follows: `scripts/provision_ci_apply_identity.sh` is not edited at all. Two properties come free from that: the existing script's self-description as ADR-009's least-privilege arrangement stays accurate because nothing is added to it, and each script describes exactly one identity. What does not come free, and is carried forward as a requirement: the new script must keep the existing one's habit of closing with an honest summary of the boundary it does and does not achieve, and the two scripts together must rebuild the whole arrangement from an empty workspace (SC-005-04). |
| What happens to the first real catalog after it is created? F-PLATFORM-004 is create-only by deliberate design and ships no deletion path, so a catalog created during live verification persists in the workspace until a human removes it through the console or the CLI. Three defensible answers. *Keep it, deliberately* — name it something unmistakably demonstrative, leave it, and treat it as standing evidence that the pipeline really did this; it costs nothing in a Free Edition workspace and it is the most reviewable outcome. *Delete it by hand afterwards and record that* — keeps the workspace tidy and makes the point that this platform can create but not remove, which is itself worth demonstrating. *Provision something genuinely useful instead* — if a fourth catalog has a real purpose in the demo estate, make the first real provisioning produce that rather than a throwaway. The only unacceptable answer is not deciding: an unowned catalog nobody remembers creating is exactly the kind of artifact this project's whole argument is against. Related sub-question with the same owner: does the live verification run through a real merged request file (which then lives in `catalog-requests/` permanently as the record of the request) or by hand from a local path? | hector | 2026-09-20 | *resolved: keep it, deliberately and permanently.* The catalog stays in the workspace as standing evidence that the path really works — the one artifact no amount of passing tests substitutes for — and no manual cleanup step forms part of this feature's live-verification procedure. **This is consistent with the create-only rule, not an exception to it**: keeping the catalog adds no delete capability, and deleting it would not have used one either — it would have meant inventing an out-of-band manual chore that nothing in this platform performs and this feature does not otherwise need. Create-only constrains what the software may do; it takes no position on whether a human tidies up afterwards. What the rule still demands, and this resolution honours, is that the object not be a mystery: it is named so its purpose is unmistakable, and its existence is recorded in `docs/` alongside the identity that made it. The sub-question follows: driving the verification through a real merged request file is the better of the two, since that file then persists in `catalog-requests/` as the permanent record of who asked — the same reasoning that keeps the catalog keeps the request beside it. |

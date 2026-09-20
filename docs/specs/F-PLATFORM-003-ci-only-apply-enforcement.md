---
id: F-PLATFORM-003
title: CI-only apply — a real service-principal identity, and taking the laptop's write access away
status: in-progress
owner: hector
approvers: []
created: 2026-09-19
last-updated: 2026-09-19
---

# Feature: CI-only apply — a real service-principal identity, and taking the laptop's write access away

> *Scope of this document.* Internal planning artifact, same as F-PLATFORM-001 and
> F-PLATFORM-002, not shipped into the `uc-metadata-platform` repo. Unlike those two, part of
> what this feature proposes is not a code change at all: it is a change to who holds which
> permission on a live workspace, including the owner's own. That makes this spec a decision
> record as much as a build plan, and it is why the middle layer below is gated on a separate,
> explicit sign-off rather than carried along by approval of the document as a whole.

## Business Context

F-PLATFORM-001 states a hard rule: *apply runs only on merge to the main branch; change
requests may validate and dry-run, never apply.* That rule is the spine of the whole
governance argument — it is what makes "reviewed, approved, then written to production" a
property of the system rather than a description of good intentions. It is also, today, not
true in the sense that matters. It is stated, documented and honoured in practice, and nothing
technically enforces it. Anyone holding the owner's Databricks credentials — which, on this
prototype, means the owner sitting at his own laptop — can run the live apply command against
the real workspace with no pull request, no review, no merge and no record of approval beyond
whatever name they type into the approval flag.

The way this was found matters more than the finding. It did not come out of a design review
or a checklist; it came out of the owner rehearsing the demo by actually running the tool,
watching a real apply land on real tables from a shell prompt, and noticing that the thing he
had just done was the exact thing his own spec says cannot happen. That is the difference
between a stated control and an enforced one, and it is a gap worth closing precisely because
a reviewer is entitled to ask "what stops you doing it anyway?" and "we wrote it down" is a
weak answer for a platform whose entire pitch is that gates beat goodwill.

Closing it properly means two separate things, and conflating them is how this kind of work
goes wrong. The first is giving continuous integration an identity of its own — a non-human
service principal with its own credentials and only the permissions the applier actually
needs — so that CI *can* apply. The second is taking the ambient write access away from the
human, so that the laptop *cannot*. Only the second one makes the rule true, and only the
second one changes how the owner works day to day. They are built and approved separately here
for that reason. A third piece — the merge trigger itself firing on a real merged pull request
— is already wired in code and waits on something outside this feature entirely: the repository
does not yet have a remote to merge anything into.

## Stakeholders
- Owner: hector
- Approvers: hector (self-approving; this is a solo interview submission) — and, for Layer 2
  specifically, a second and explicit approval from hector recorded in this document's
  Revision History before any grant is revoked. See Rules & Constraints.
- Last reviewed: 2026-09-19

## Revision History
| Rev | Date         | Author | Change |
|-----|--------------|--------|--------|
| 1   | 2026-09-19   | hector | Initial draft. Splits enforcement of F-PLATFORM-001's apply-on-merge rule into three separately-gated layers: a real CI service principal with least-privilege grants (buildable now), removal of the owner's own standing write access to the three demo tables (described, awaiting separate approval), and the real merge trigger (blocked on the pending repository-push decision). Records the live-verified facts the feature rests on — service-principal creation, secret minting, the OAuth machine-to-machine token exchange, and the default-deny 403 a fresh principal receives. Names two structural findings that shape the work: revoking a privilege from a table's *owner* is a no-op, so Layer 2 needs an ownership move rather than a revoke, and an account admin can always re-grant themselves, so Layer 2 removes ambient authority rather than making the act impossible. Four open questions, one of which (does Layer 2 happen at all) gates that layer entirely. |
| 2   | 2026-09-19   | hector | Added SC-003-06: a merged change request that fails validation must still be refused by apply, identically regardless of which identity is running it. Proves access control (this feature's whole subject) and content validation (F-PLATFORM-001's gate) are independent layers — the service principal's elevated grants are an access-control concern only and do not bypass, weaken or shortcut the validation gate. |
| 3   | 2026-09-19   | hector | **Layer 2 approved and executed against the live workspace.** Explicit instruction: the laptop must not write real Unity Catalog metadata; the in-repository fake stays fully usable regardless, since it has no relationship to Databricks permissions at all. `ucmeta-ci-apply` created for real (not a probe), granted `USE_CATALOG`, `USE_SCHEMA` on both demo schemas, `CAN_USE` on the warehouse; ownership of all three demo tables transferred to it; hector's own identity re-granted `SELECT` only. Live-verified: `COMMENT ON TABLE` and `SET TBLPROPERTIES` are cleanly refused for hector's identity (`PERMISSION_DENIED: User does not have MODIFY`), naming the exact missing privilege. **A real, empirically-discovered gap, not papered over**: `SET`/`UNSET TAGS` still succeeds for hector's identity with zero explicit grant, because he is a metastore-admin (`admins` group) and Unity Catalog gives metastore admins an implicit bypass for tag operations specifically, separate from and not gated by `MODIFY`. Effective-privilege check confirmed `SELECT` is the *only* thing explicitly granted; the tag write still landed anyway. Decision: document this precisely rather than pursue the only fix that would close it (removing hector from the `admins` group entirely), which is a materially bigger, harder-to-reverse change affecting the whole account, not just these three tables, and out of scope for what was asked. See the sharpened Rules & Constraints, Behaviour and SC-003-03 below — this is Layer 2's real, precise boundary, not its aspirational one. |
| 4   | 2026-09-19   | hector | Resolved the two remaining open questions. Rotation: minimal prototype answer — record the expiry date, write the procedure down, no scheduled rotation or workflow expiry-check. Sequencing: finish Layer 1's code-side artifacts (grant script, `apply.yml` wiring, local verification) before pushing to GitHub, shared with F-PLATFORM-002's own pending push decision, so the first real merge exercises the complete real pipeline in one shot. Zero open questions remain; the next work is Layer 1's code-side build. |
| 5   | 2026-09-19   | hector | **Layer 1's code-side build complete.** `scripts/provision_ci_apply_identity.sh` written and run live twice against the real workspace with byte-identical output, confirming both idempotency and correctness. `.github/workflows/apply.yml` wired to `ucmeta apply --live --profile ucmeta-ci-apply`, gated fork-safe (SC-003-04) on three named secrets via a `steps.credential.outputs.configured` check, with mutually exclusive live/fake steps so the outcome is visible in the job's step list. `docs/ci-service-principal.md` written, naming the identity, every grant, the 2028-09-18 expiry, the rotation procedure, and the manual secret-entry steps. `tests/unit/test_workflows_yaml.py`'s no-`--live` assertion narrowed to `validate.yml`/`coverage.yml`; three new tests bind SC-003-04 to `apply.yml`'s actual shape. The one seam question resolved with no code change: a local `ucmeta-ci` profile proved `RealUCClient`/`cli.py` need nothing new — `ucmeta apply ... --live --profile ucmeta-ci` ran twice end-to-end as `ucmeta-ci-apply`, both `success`, second run idempotent. Full unit suite: 247 passed. ADR-009's "What is not yet true" section is now stale and corrected to match. Not yet pushed to GitHub — that remains outside this feature, per Layer 3 and the shared F-PLATFORM-002 push decision. |

## Users & Roles

- *Continuous integration (the new non-human actor)* — the identity this feature creates. Holds
  its own credentials, applies approved contracts to the catalogue on merge, and can do nothing
  else in the workspace. It is the only identity that routinely writes metadata to the demo
  tables once this feature is complete. It reviews nothing, decides nothing, and holds no
  credentials that belong to a person.
- *Platform engineer / repository owner (hector)* — creates the service principal, decides its
  grants, stores its credentials in the automation environment, and — under Layer 2 — gives up
  his own standing ability to write metadata to the demo tables. Afterwards he authors, harvests,
  proposes, validates and dry-runs locally exactly as before, and reaches the catalogue's
  metadata through a merged change request rather than through his own shell.
- *Account administrator (also hector, wearing a different hat)* — the identity that owns the
  workspace and can grant or revoke anything, including granting himself back what Layer 2 takes
  away. Named explicitly because pretending otherwise would overstate what this feature achieves:
  it removes ambient authority, it does not create an impossibility. See Rules & Constraints.
- *Data producer (in the production shape this stands in for)* — never had write access to the
  catalogue's metadata in the first place under F-PLATFORM-001's design, and still does not. This
  feature makes the platform engineer's access look like everybody else's rather than creating a
  new restriction for producers.
- *Reviewer of a change request* — unchanged, except that their approval now genuinely is the
  only route by which a metadata change reaches the catalogue, rather than the intended route
  among several.
- *Interview panel* — unaffected by every layer. The default offline path, the fake catalogue,
  the static coverage page and the whole clone-and-run loop require no credentials before this
  feature and require none after it. A fork of the repository must keep working with no secrets
  configured at all; that is a hard constraint, not a hope.

## Behaviour

Today, one identity does everything: a person's own workspace login authors contracts, reads
the catalogue, and writes to it. The feature separates those.

*Layer 1 — continuous integration gets an identity of its own.* A non-human account is created
in the workspace with its own credentials, distinct from any person's. It is granted exactly
what the applier needs to do its job on the three datasets the prototype ships contracts for:
enough to see those datasets, to read them back for validation, to write dataset and column
descriptions, to set governance labels, and to record the dataset's declared commitments. It is
granted nothing else — it cannot create or drop anything, cannot reach any other part of the
estate, cannot read the coverage history the platform keeps about itself, and has no
administrative standing anywhere. Its credentials are stored in the automation environment's own
secret store and exist nowhere in the repository. The apply job, which until now has run against
the in-repository fake and printed what it would have done, runs for real as this identity.

A fresh non-human account starts with no access to anything at all, which was confirmed rather
than assumed: before any permission was granted, a token issued to a newly-created principal was
refused outright when it asked the catalogue to list itself. Everything it can eventually do is
therefore something somebody deliberately granted, which is the property that makes a
least-privilege claim checkable rather than rhetorical.

*Layer 2 — the laptop mostly stops being able to write, and exactly where it doesn't is written
down.* **Executed against the live workspace on 2026-09-19, not merely designed.** The owner's
own identity had standing write access to the three demo datasets' metadata through table
ownership, which is how every rehearsal so far had worked. Ownership of all three tables moved to
the continuous-integration identity; the owner was re-granted `SELECT` only. He keeps everything
he needs to author, to read the catalogue, to validate a contract against it and to print exactly
what an apply would do. Running the live apply command from his own shell afterwards no longer
lands the writes it used to: a comment write and a table-properties write are both cleanly
refused, each naming the exact table and the exact missing privilege (`MODIFY`), and each is
recorded in the same audit trail every other apply outcome goes to, as a `partial_failure` rather
than a silent nothing.

*The word "mostly" above is load-bearing, and the reason is stated here rather than in a
footnote.* Comments and properties are genuinely blocked. Tag writes are not: `SET TAGS` and
`UNSET TAGS` still succeed for the owner's identity with no explicit grant at all — confirmed by
reading his effective privileges directly, which show `SELECT` and nothing else, immediately
before and after a tag write that landed anyway. The explanation is that the owner remains a
metastore administrator (there is no other person to hold that role in a solo, personal Free
Edition account), and Unity Catalog gives metastore admins an implicit bypass for tag operations
specifically — a different code path from the `MODIFY` privilege that gates comments and
properties, and not something any grant this feature makes can switch off. A real apply run from
the laptop today would come back `partial_failure`: comment and property writes named and
refused, tag writes silently landed on the real catalogue anyway. That is a materially different,
and more precisely true, claim than "the laptop cannot write" — it is "the laptop cannot write
comments or properties; its tag writes are not yet gated, because gating them would mean removing
the owner's own admin status, which is a larger and separately-decided change this feature does
not make." Getting a fully-applied, fully-attributed metadata change into the catalogue still
requires a real merged change request; getting a partial, tags-only one does not, and that gap is
this layer's honest, tested boundary rather than its aspiration.

*Layer 3 — the trigger becomes real.* The apply job already fires on a push to the main branch,
which is what a merged change request produces. That mechanism is built, tested and, in every
respect the repository can verify on its own, finished. What it has never done is run in
response to somebody actually merging something, because the repository has no remote and
nothing has ever been merged into one. This layer is that first real merge, and it depends
entirely on a decision that belongs to another conversation — whether and when this repository
is pushed somewhere public. Nothing in Layers 1 and 2 waits for it, and this feature does not
assume it will happen.

The three layers compose but do not depend on each other in a line. Layer 1 without Layer 2
means CI can apply and so can the laptop — an improvement in capability and in credential
hygiene, and no enforcement at all. Layer 2 without Layer 1 would mean nothing can apply, which
is why the order is fixed even though the approvals are separate. Layer 3 without either is what
exists today.

## Glossary

- *Service principal*: an identity in the workspace that belongs to an automated process rather
  than a person. It has credentials of its own, it is granted permissions of its own, and no
  human logs in as it. The platform's own tooling recommends exactly this split — production
  writes performed by service principals, so that interactive users need no write access to
  production at all.
- *Machine-to-machine credentials*: the client identifier and secret a service principal uses to
  obtain a short-lived access token without a human present. Verified working against the real
  workspace on 2026-09-19.
- *Least privilege*: granting an identity only the permissions its actual job requires, and
  nothing that merely happens to be convenient. Checkable here because a new service principal
  begins with nothing — every capability it ends up with was deliberately added.
- *Default deny*: the starting state of a freshly-created service principal — access refused to
  everything until explicitly granted. Confirmed live, not assumed.
- *Standing access*: a permission somebody holds all the time, whether or not they are currently
  doing the thing it permits. The thing Layer 2 removes from the owner's identity.
- *Ambient authority*: the ability to do something simply because of who you already are, with
  no deliberate step in between. What makes an accidental out-of-band apply possible today.
- *Ownership (of a catalogue object)*: the standing of the identity that created an object.
  Ownership carries full control implicitly and cannot be revoked by taking a permission away —
  it can only be transferred. This is why Layer 2 is an ownership move and not merely a revoke.
- *Secret rotation*: replacing a credential with a new one before the old one expires or after it
  is suspected compromised, ideally with both valid at once so nothing breaks in between.
- *Blast radius*: everything an attacker could reach if a specific credential leaked. The unit in
  which this feature's security argument is made.
- *Fork-safe*: a workflow that still runs, and still means something, for somebody who clones or
  forks the repository with none of its secrets. A hard requirement carried forward from
  F-PLATFORM-001's interview-panel constraint.

## Scenarios

Conventions for binding tests to scenarios:
- *Backend (pytest)*: `@pytest.mark.scenario("SC-003-01")`, fallback `test_..._sc_003_01`.
- *Workflow-shape assertions*: scenario ID in the test name in the workflow-YAML test module.
- *End-to-end / manual verification*: scenario ID in the verification script and in the
  walkthrough notes, since two of these scenarios can only be proven against the live workspace.

### SC-003-01 — Happy path: a merged change request applies for real, as the machine

- *Given* the continuous-integration identity exists, holds only the permissions the applier
  needs on the three demo datasets, and its credentials are stored in the automation
  environment's secret store
- *And* a contract change has been opened as a change request, has passed every automated check,
  has printed exactly the catalogue writes it would perform, and has been approved
- *When* the change request is merged into the main branch
- *Then* the apply job starts because of the merge, not because anybody ran anything by hand
- *And* it authenticates as the continuous-integration identity, not as any person
- *And* it applies only the contracts the merge actually changed, and the writes land on the live
  catalogue
- *And* the audit record for the apply names the approving human, while the writes themselves
  were performed by the machine identity — the two are recorded separately because they are
  different facts
- *And* re-running the same merge's apply changes nothing further, because idempotency is a
  property of the applier and is not affected by which identity performs the write

### SC-003-02 — Edge case: the machine credential is expiring or has to be replaced

- *Given* the continuous-integration identity's credential has a fixed expiry roughly two years
  out, and that date is written down somewhere a human will actually see it
- *And* the credential may also need replacing early — because it was exposed, or because
  somebody wants to prove rotation works
- *When* rotation is performed
- *Then* a second credential is created for the same identity while the first is still valid, so
  both work at once
- *And* the automation environment's stored secret is updated to the new one, and the next apply
  succeeds using it
- *And* only then is the old credential deleted, so no window exists in which the identity has no
  working credential and a merge would fail for a reason unrelated to the change being merged
- *And* the identity itself, and therefore every permission granted to it, survives the rotation
  untouched — rotation replaces a secret, never the principal
- *And* if the credential is ever allowed to expire without replacement, the failure is a clean
  authentication error naming the expired credential, not a permissions error that would send
  somebody looking in the wrong place

### SC-003-03 — Failure case: somebody runs a live apply from a laptop after Layer 2

Rewritten on 2026-09-19 to match what was actually found on the live workspace, not the cleaner
outcome the design discussion predicted before execution. The predicted version of this scenario
described a uniform refusal on the first write. That is not what happens, and the difference is
the whole reason SC-003-03 is worth keeping accurate rather than aspirational.

- *Given* Layer 2 is in place: the owner's own identity can read the demo datasets and validate
  contracts against them, holds no explicit grant beyond `SELECT`, and — confirmed live — is
  still a metastore administrator, which matters to what follows
- *When* he runs the live apply command from his own shell against one of those datasets
- *Then* validation passes, because the contract is fine and reading is still permitted — the
  failure, where it happens, happens at the write, which is where it belongs
- *And* the table comment write and the table-properties write are each refused by the catalogue
  with a permission error naming the identity that was refused, the object it tried to write and
  the privilege it lacked (`MODIFY`)
- *And* the table-tags and column-tags writes are **not** refused — they land on the real
  catalogue, because a metastore administrator's tag operations bypass the `MODIFY` gate this
  layer otherwise relies on, confirmed by reading the identity's effective privileges immediately
  before and after and finding `SELECT` and nothing else throughout
- *And* the result is therefore `partial_failure`, not a clean uniform refusal: some of what the
  contract asked for landed on the real catalogue without any change request, review, or merge
- *And* the tool still reports this correctly rather than papering over the mixed outcome — the
  existing partial-failure machinery names exactly which writes succeeded and which were refused
  and why, which is the same mechanism that already handles a mid-run network failure; this
  scenario is what proves that machinery also does the right thing when the *cause* of the mix is
  a permission boundary rather than an outage
- *And* the distinction between "you are not allowed to do this" (comments, properties) and "this
  was never gated for you" (tags) is visible in the result, because collapsing them into one
  generic failure would hide exactly the fact this scenario exists to surface
- *And* the attempt still produces an audit record naming the mixed outcome, so an out-of-band
  apply attempt is visible afterwards rather than leaving a trace only for the part that failed
- *And* what is **not** true, and is not claimed to be true: that nothing is left half-written.
  Something is. That is Layer 2's honest, tested boundary on this specific environment, not its
  aspiration — see Rules & Constraints and Behaviour for why, and Out of Scope for what closing it
  fully would actually require

### SC-003-04 — Edge case: somebody forks the repository with no secrets at all

- *Given* a reviewer has forked or cloned the repository and has no Databricks account, no
  credentials and no secrets configured
- *When* they push to their own main branch and the apply job runs
- *Then* the job does not fail, and does not attempt a live apply it has no credentials for
- *And* it states plainly that no automation credential is configured and that it is therefore
  demonstrating the apply mechanism against the in-repository fake rather than writing to a real
  catalogue
- *And* the distinction between "no credential configured, so this ran against the fake" and "a
  credential was configured and the live apply failed" is unmistakable in the job's output,
  because those two outcomes must never be confused with each other
- *And* every other path a credential-less reviewer uses — the offline loop, the fake catalogue,
  the static coverage page — is untouched

### SC-003-05 — Failure case: the machine identity is missing one privilege it turns out to need

- *Given* the continuous-integration identity has been granted what was believed to be the
  minimal set, and one write the applier performs needs a privilege that was not granted
- *When* a merge triggers a real apply
- *Then* the writes that are permitted land and the one that is not is refused, which is the
  applier's existing partial-failure behaviour and not new work
- *And* the job fails, because a partial apply is not a success
- *And* the audit record and the job output name exactly which write was refused and why, so the
  fix is "grant this specific privilege" rather than "grant it everything and move on"
- *And* the missing privilege is added to the grant script in the repository, not applied by hand
  to the live workspace and forgotten, so the workspace stays rebuildable from the repository

### SC-003-06 — Failure case: a merged change request fails validation, and no write happens

- *Given* a contract that fails `validate()` reaches `main` — a check was bypassed, branch
  protection was not configured, or the table drifted between the change request's own validate
  step and the merge
- *When* the merge triggers `apply.yml`, which now runs as the continuous-integration identity
  rather than the fake
- *Then* `apply()` runs its own internal validation before attempting any write — inherited
  unchanged from F-PLATFORM-001's "apply refuses the whole contract if it reaches apply by any
  route other than a clean validate" rule — and refuses the contract
- *And* this refusal is identical regardless of which identity is running apply: the elevated
  grants this feature gives the service principal are an access-control layer, not a content
  layer, and do not bypass, weaken or shortcut the validation gate. The two are independent
  controls, and this scenario is what proves that rather than asserting it — a privileged
  identity that skipped validation because it was privileged would mean this feature had quietly
  traded one gap for another
- *And* zero catalogue writes happen, not a partial set — the whole-or-nothing refusal already
  proven under the owner's own identity holds under the machine identity unchanged
- *And* an audit record is still published for the refused run (`deployment_status=refused`),
  naming the specific validation problems, so a refused CI run is visible in the same audit trail
  as every other outcome, not a silent no-op
- *And* the CI job itself fails (non-zero exit), so the refusal is visible in the workflow run's
  status in GitHub Actions, not only to someone who later goes looking in `release_log.jsonl`

## Data

| Data | Source | Direction | Sensitivity |
|------|--------|-----------|-------------|
| Service-principal identity (its application identifier and display name) | Created in the workspace | Read (referenced by the grant script and documentation) | Internal |
| Machine credential (client secret) | Minted once by the workspace when the principal is created | Write (into the automation secret store only) | Confidential — never in the repository, never in logs, never in a job's output |
| Credential expiry date | Returned when the credential is minted | Read (recorded in documentation so rotation is not a surprise) | Internal |
| Short-lived access token | Exchanged at run time from the machine credential | Transient | Confidential |
| Workspace host | Configuration | Read | Internal |
| The grant set — which identity may do what to which dataset | Declared in a checked-in script, applied to the workspace | Write (to the workspace), R/W (as a repository file) | Internal |
| Catalogue metadata writes (descriptions, labels, declared commitments) | The approved contract, on merge | Write | Internal |
| Apply audit record (what changed, who approved, outcome) | Generated per apply, unchanged from F-PLATFORM-001 | Write | Internal |
| The approving human's name | The merge event | Read (recorded in the audit record) | Internal |

## Rules & Constraints

- *The continuous-integration identity is granted the minimum the applier actually performs, and
  the grant set is named rather than gestured at.* What the applier does, per its own code, is:
  read a table back (to validate the contract against it, and to read its current labels through
  the catalogue's own information views), write the table's comment, write a comment per
  described column, merge a set of declared properties onto the table, and set labels on the
  table and on individual columns. The corresponding grants on the three demo datasets, and
  nothing beyond them, are: the right to use the catalogue; the right to use each of the two
  schemas that hold them; the right to read each of the three tables; the right to modify each of
  the three tables, which is what carries comment writes; and the right to apply labels to each
  of the three tables, which is a distinct named privilege in this catalogue and not implied by
  the modify right. Plus one workspace-level permission that is not a catalogue grant at all: the
  right to use the SQL warehouse the applier executes its statements through, without which every
  grant above is inert.
- *What the identity is explicitly not granted.* No right to create or drop anything anywhere. No
  administrative standing at the account, workspace or metastore level. Nothing on any catalogue
  or schema other than the two that hold the demo datasets. Nothing on the platform's own
  coverage-history table, which is a different feature's write path and a different identity's
  job. No entitlement it does not need in order to execute a statement on the warehouse. If a
  broader grant would be convenient, it is still not made — the value of this layer is entirely
  in the narrowness, and a service principal granted everything is a personal access token with
  extra steps.
- *One privilege question is open and is settled by experiment, not by argument.* Whether merging
  a set of declared properties onto a table requires only the modify right, or requires ownership
  of the table, is not something to guess at from documentation. It is probed against the live
  workspace as the first build step of Layer 1 — grant the believed-minimal set, attempt the
  write as the service principal, read the refusal if there is one. Whatever the workspace
  actually says becomes the answer and is recorded, the same empirical discipline this project
  already used for the applier's depth and for the SQL-escaping fix. If ownership turns out to be
  required, that is a material input to Layer 2 and must be resolved before Layer 2 is approved,
  not after.
- *Credentials never enter the repository.* Not in a workflow file, not in a configuration file,
  not in a committed example, not in a test fixture, not in a job's printed output. The
  repository holds a workspace host, a warehouse identifier and the *names* of the secrets it
  expects. The automation environment's own secret store holds the values. This is the same rule
  F-PLATFORM-001 already states and honours; this feature is the first time the project has a
  secret at all, so it is the first time the rule is load-bearing rather than free.
- *The machine credential is long-lived, and that tension is named rather than smoothed over.*
  F-PLATFORM-001's security position is "no long-lived personal access tokens", and it has been
  honoured because nothing needed a stored credential. A machine credential with a roughly
  two-year expiry is long-lived by any reasonable reading. The distinction being claimed is not
  "this is short-lived" — it is that the credential belongs to a non-human identity with five
  narrow grants on three synthetic tables, is stored in a managed secret store rather than on a
  laptop, is revocable in one call without disturbing any person's access, and is rotatable
  without downtime. A personal access token is a human's full standing in the workspace in a
  string. These are different risks that happen to share the word "long-lived", and the spec says
  so rather than relying on the reader not to notice.
- *Rotation is a named plan with a date attached, not an intention.* The credential's expiry date
  is recorded in the repository's documentation at the moment it is minted. The rotation
  procedure — mint the replacement while the current one still works, update the stored secret,
  verify one apply, then delete the old one — is written down before it is needed, because a
  procedure invented during an outage is not a procedure. For a prototype of this lifespan the
  honest position is that rotation will most likely never be exercised for real, and the spec's
  requirement is therefore that the plan and the date exist and are findable, not that a rotation
  is scheduled.
- *Layer 2 is a separate decision and requires its own explicit approval.* Approving this
  document does not approve revoking the owner's write access. That revocation is recorded as
  approved only by a dated entry in this document's Revision History that says so in as many
  words. The reason for the ceremony is proportionality: Layer 1 adds a capability and can be
  undone by deleting a principal, whereas Layer 2 removes a capability from the person who has to
  work in this repository every day, and undoing it means re-granting privileges on a live
  workspace under time pressure — reversible, but not trivially, and not at two in the morning
  before a walkthrough.
- *Layer 2 is an ownership move, not merely a revocation.* The demo tables were created by the
  owner's identity, which makes that identity their owner, and ownership carries full control
  implicitly — revoking a privilege from an owner changes nothing at all. For Layer 2 to have any
  effect, ownership of the three tables must move to another identity, which in practice means
  the continuous-integration principal or a group. This is the single most consequential
  mechanical detail in the feature and the one most likely to be discovered late if it is not
  written down here.
- *Layer 2 does not claim to bind an administrator, and the live workspace confirmed this in a
  more specific and more useful way than the design discussion predicted.* Before execution, the
  predicted limit was that the owner could *deliberately* re-grant himself what Layer 2 removed.
  What was found instead is narrower and stranger: for one specific operation — tag writes — no
  deliberate act is needed at all. `SET TAGS`/`UNSET TAGS` succeed for the owner's identity today
  with zero explicit grant, purely because metastore admin status carries an implicit bypass for
  tag operations that sits outside the `MODIFY` privilege gating everything else. This was
  confirmed, not inferred: the owner's effective privileges were read directly immediately before
  and after a tag write that landed anyway, and showed `SELECT` and nothing else throughout. So
  the honest claim has two parts, not one — comments and properties require a deliberate,
  self-aware act of privilege escalation to bypass (re-granting `MODIFY` to himself, a visible
  act); tags require no act at all, because they were never actually gated by anything this
  feature controls. The prototype claims the design, demonstrates the mechanism for two of three
  write types, and states plainly that the third is not gated on this specific environment and
  why. In the target organisation the platform engineer and the metastore administrator are
  different people, the account-level bypass does not apply, and all three write types would be
  genuinely blocked.
- *Layer 2 does not touch anything outside the three demo datasets' metadata.* The owner keeps
  every ability the rest of the project depends on: creating and dropping tables (the workspace
  must stay rebuildable from scripts), altering table structure (the live drift demonstration
  genuinely alters a column and would otherwise break), writing the platform's coverage-history
  table, and reading everything. The scope of the revocation is metadata writes on
  `workspace.analytics.customers`, `workspace.analytics.orders` and
  `workspace.marketing.campaigns`, and nothing else. A broader revocation would break two other
  features to make a point this one already makes.
- *A failed apply must be attributable.* When a write is refused for permissions, the tool's
  output and its audit record say which identity was refused, on which object, and for want of
  which privilege. "Apply failed" with the cause swallowed turns a correctly-working control into
  something a person debugs for an hour. The applier's existing behaviour already collects
  per-write outcomes and reasons; this rule is a requirement that the failure surface preserves
  that detail, not a request to build a new one.
- *The workflow stays fork-safe.* A clone or fork with no secrets configured must still run the
  apply job, still demonstrate the mechanism against the in-repository fake, and still exit
  successfully. The live path is conditional on the credential being present, and the two
  outcomes are distinguishable in the job's output. This is F-PLATFORM-001's interview-panel
  guarantee applied to the one workflow that now has a real credential, and it is the reason the
  live apply cannot simply be turned on unconditionally.
- *Apply remains the only write path, and merge remains its only trigger.* Nothing in this
  feature adds a manual apply button, a workflow dispatch, or an escape hatch "for emergencies".
  An emergency escape hatch is the mechanism by which every apply-only-on-merge rule in history
  has stopped being true.
- *The grant set lives in the repository as a script.* Every permission this feature creates is
  expressed in a checked-in script that can recreate the whole arrangement from nothing, because
  F-PLATFORM-001 treats the workspace as disposable and reclaimable. A permission applied by hand
  in a console and never written down makes the workspace unrebuildable, which is a worse defect
  than the one this feature fixes.

## Non-functional Requirements

Same framing as the previous two specs: this is a spare-time prototype, and where a real
deployment would need a number, the prototype's target and the production consideration are
stated separately. Security is the load-bearing section here rather than one of several, because
this feature's entire substance is who may do what.

- *Security — credential storage.* One secret exists and it lives in exactly one place: the
  automation environment's own secret store, entered by hand through that environment's
  interface. It is not in the repository, not in a local configuration file committed by
  accident, not in shell history in a form that survives, and not printed by any job. The
  repository refers to it by name only. Local verification of the service principal, which Layer
  1 requires before the workflow is ever pushed anywhere, uses the credential through the
  environment or a credentials file outside the repository tree, and that file is removed
  afterwards.
- *Security — blast radius if the machine credential leaks.* An attacker holding it can, on three
  synthetic tables in a free, disposable, non-commercial workspace containing no business data:
  read those tables, rewrite their descriptions, and set labels on them. They cannot create or
  delete anything, cannot reach any other schema or catalogue, cannot read the platform's own
  coverage history, cannot touch the account, cannot incur a cost beyond a 2X-Small warehouse's
  free-tier usage, and cannot impersonate a person. The damage is vandalism of metadata that is
  version-controlled in the repository and can be re-applied by a merge. The response is one
  call to delete the credential.
- *Security — blast radius if the owner's personal credential leaks, which is the current state.*
  An attacker holding it has the account owner's full standing: every catalogue and schema, table
  creation and deletion, the platform's own coverage history, workspace administration, identity
  administration, and the ability to grant themselves anything further. The comparison is the
  whole argument for this feature. Layer 1 alone does not reduce this, because the personal
  credential still exists and still has everything; Layer 1 plus Layer 2 reduces what an
  automated write path needs a human's credentials for to nothing, which is the direction the
  platform's own guidance points.
- *Security — rotation.* Procedure written down at minting time, expiry date recorded alongside
  it, overlapping validity so rotation causes no outage, and the principal itself untouched by
  rotation. Exercised at most once as a demonstration; not scheduled.
- *Security — what this feature does not claim.* It does not claim a hard separation of duties,
  because the same person holds both roles here. It does not claim the credential is short-lived.
  It does not claim secret scanning, automatic rotation, or detection of a leaked credential; all
  three are real production requirements and none is built.
- *Performance (prototype).* Authenticating as the service principal adds one token exchange to
  the apply job — under a second, against a job whose warehouse cold start already dominates it.
  Nothing in the demo loop's under-two-minutes budget is affected. Locally, nothing changes at
  all: harvest, propose, validate and dry-run keep running exactly as they do today.
- *Performance (production consideration, not built).* Token exchange per job invocation is fine
  at any volume a merge-triggered workflow reaches. A busier platform would want the credential
  managed by the CI platform's own identity federation — GitHub's OpenID Connect against a
  workspace-side trust — rather than a stored secret at all, which removes rotation as a concern
  entirely. That is the correct production answer, it is meaningfully more setup, and it is named
  here rather than built.
- *Scale.* One service principal, one credential, five grants, three tables, one workspace.
  Deliberately small. The design question this feature answers is not how it scales but whether
  the separation is real.
- *Availability.* The apply job degrades the way the applier already degrades: if the warehouse
  or catalogue is unreachable, writes fail, the job fails loudly, and the audit record says what
  happened. A missing or expired credential fails at authentication with a clear message rather
  than looking like a permissions problem. A fork with no credential does not fail at all — it
  runs the mechanism against the fake and says so.
- *Retention.* Unchanged from F-PLATFORM-001: every apply, including every refused one, appends
  one audit record that is kept for as long as the repository exists. An out-of-band apply
  attempt that gets refused after Layer 2 leaves a record, which is part of why it is refused at
  the write rather than blocked earlier.
- *Regulatory.* None assumed, same as the previous two specs. Separating a machine identity from
  a human one is ordinary engineering hygiene and is justified on those grounds alone. It happens
  to be what most control frameworks ask for; that is an observation, not a design goal.

## Out of Scope

- *Any grant broader than the three demo datasets need.* No catalogue-wide or metastore-wide
  grant to the service principal, however much simpler it would make the script. The narrowness
  is the deliverable.
- *Automating the creation of the automation environment's secret.* Entering a secret into a CI
  platform's secret store is a deliberate manual act performed once through that platform's own
  interface. Scripting it would require a credential capable of writing repository secrets, which
  is a strictly worse credential to have lying around than the one being stored. Manual, once,
  documented.
- *Account-level service-principal management.* The principal is created and lives at the
  workspace level. Account-level principals, service-principal federation, group membership
  management and identity provisioning are the target organisation's problem and are not modelled
  here.
- *Multi-workspace or multi-environment identity.* One principal, one workspace, one set of
  grants. A real platform has an identity per environment with a promotion path between them;
  that shape is named in the ADR and not built.
- *OpenID Connect federation between the CI platform and the workspace.* The better production
  answer, because it removes the stored secret entirely. Not built: it needs a trust relationship
  configured workspace-side and is meaningfully more setup than the thing it improves on, for a
  prototype whose secret lives for two years and guards three synthetic tables. Named in the ADR
  as the direction of travel.
- *Secret scanning, leak detection, or automatic rotation.* Named as real requirements, none
  built.
- *Revoking the owner's access to anything beyond the three demo datasets' metadata.* Explicitly
  excluded so that a future implementer reading this section for permission finds none. Table
  creation, structural alteration, the coverage-history write path and every read stay exactly as
  they are.
- *Removing the owner from the metastore-admin group to close the tag-write gap.* This is the only
  change that would fully block his identity's tag writes — the admin bypass Layer 2's execution
  found is not something any table- or schema-level grant can switch off. Deliberately not done:
  it is a materially larger and harder-to-reverse change than anything else in this feature,
  affects the whole account rather than three tables, and was explicitly out of scope for what was
  asked. Named here, not silently avoided, because a future implementer needs to know this is the
  actual remaining lever, not an oversight waiting to be found.
- *A break-glass or emergency manual apply path.* Deliberately not built, per Rules & Constraints.
- *Changing who the applier records as the approver.* The audit record continues to name the
  human whose merge authorised the change. The service principal is who performed the write, not
  who approved it, and collapsing those two into one field would destroy the distinction this
  feature exists to create.
- *Applying the same treatment to the validate and coverage workflows.* Validation reads and the
  coverage workflow writes the platform's own history table; neither writes contract metadata to
  the catalogue and neither is what F-PLATFORM-001's rule is about. Giving them machine
  identities too is a reasonable follow-on and is not this feature.
- *Pushing the repository to a public remote.* Layer 3 depends on it. It is a separate, pending
  decision discussed elsewhere, and this feature neither makes it nor assumes it.

## Dependencies

- *Related features*: F-PLATFORM-001 (this feature enforces its apply-on-merge rule and uses its
  applier, audit trail and workflow unchanged in every respect except which identity runs them);
  F-PLATFORM-002 (shares the same pending repository-push prerequisite for anything that has to
  happen on a real remote, and owns the coverage-history table this feature's principal is
  deliberately not granted access to). Likely follow-ons: OpenID Connect federation replacing the
  stored secret, machine identities for the remaining workflows.
- *ADRs*:
  - ADR-009 *A machine identity for apply, and taking the human's write access away* — to be
    written in the prototype repo's `docs/`, and a genuine deliverable rather than planning-only
    content, on the same grounds as ADR-008. The ADR must lead with the diagnosis, which is the
    part a reviewer will find most interesting: a stated control that nothing enforced, found by
    the author using his own tool rather than by reviewing his own document. It must record the
    alternatives and why they were rejected: (a) *document the rule and rely on discipline* —
    the status quo, rejected because it is precisely the goodwill-as-motive-force failure the
    whole project's Business Context diagnoses, and a governance prototype that relies on
    discipline for its own core control is arguing against itself; (b) *store the owner's own
    credentials as the CI secret* — rejected because it puts an administrator's full standing in
    a CI secret store, makes every apply indistinguishable from a human's action in the audit
    trail, and would make the security section worse than the status quo rather than better;
    (c) *a personal access token for CI* — rejected against the project's existing no-PATs rule
    and the platform vendor's own explicit recommendation to use service principals for
    production writes; (d) *OpenID Connect federation with no stored secret at all* — the
    strongest option and deliberately deferred, on setup cost against a two-year secret guarding
    three synthetic tables, and named as the production direction rather than dismissed. The ADR
    must also record the two honesty points that make the piece credible rather than
    self-congratulatory: that an administrator can re-grant himself what Layer 2 removes, so what
    is achieved is the removal of ambient authority rather than a hard boundary; and that the
    machine credential is long-lived, so the improvement over a personal access token is about
    what the identity can reach and how cheaply it can be revoked, not about credential lifetime.
    Finally it must record the reversibility shape of each layer, because that is what justifies
    approving them separately.
- *Code modules*: `.github/workflows/apply.yml` (the one workflow that changes);
  `src/uc_metadata/uc_client.py` (`RealUCClient`'s authentication path — see the build verdict
  below, which is the one genuine seam question in this feature);
  `tests/unit/test_workflows_yaml.py` (currently asserts that *no* workflow passes `--live`, an
  assertion Layer 1 makes false and which must be narrowed rather than deleted); a new grant
  script under `scripts/`; documentation of the identity, its grants and its credential expiry.

### Build verdicts per component

Principle carried over, with one addition this feature needs: *a component that changes a live
workspace's permissions carries its approval gate in its verdict, not in a note beside it.* Three
of the rows below are ordinary work; one is gated on a decision hector has not made; one is gated
on a decision that belongs to another conversation entirely.

| Component | Verdict | Rationale (one line) |
|---|---|---|
| Service-principal creation and credential minting (Layer 1) | *Real, and already proven possible* | Creating a principal, minting a secret, exchanging it for a token and confirming the token is refused everything until granted were all executed live against the real workspace on 2026-09-19, then cleaned up. The build is re-doing deliberately what was done as a probe, and keeping it this time. |
| `scripts/` grant script for the service principal (Layer 1) | *Built — `scripts/provision_ci_apply_identity.sh`, run live twice, byte-identical output* | Recreates the entire arrangement from nothing: idempotent service-principal creation, both entitlements, `USE_CATALOG`/`USE_SCHEMA`/warehouse `CAN_USE`, ownership transfer of all three tables, and hector's re-grant of `SELECT`-only. Contains no secret value and takes no credential as input — it runs using whatever profile is already authenticated. Closes ADR-009's "What is not yet true" gap: the workspace is now rebuildable from the repository, no longer the one exception to F-PLATFORM-001's disposable-workspace rule. Documented in `docs/ci-service-principal.md`. |
| Empirical privilege probe: does merging declared properties onto a table need ownership or only the modify right? (Layer 1, first step) | *Real, and it runs before anything else* | The one genuinely unknown fact in the grant set, and the answer changes both the grant script and Layer 2's ownership question. Settled by attempting the write as the principal and reading what the workspace says — the same discipline that produced the applier's depth ceiling and the SQL-escaping fix. Guessing from documentation here would be exactly the kind of untested claim this feature exists to eliminate. |
| `RealUCClient`'s authentication path for a non-interactive identity | *Resolved: no code changes needed* | Confirmed live, 2026-09-19: a local `ucmeta-ci` profile (OAuth M2M, `client_id`/`client_secret`/`host`) was created by hand in `~/.databrickscfg`, and `ucmeta apply contracts/analytics/customers.yaml --live --profile ucmeta-ci` ran end-to-end as the `ucmeta-ci-apply` service principal — real writes landed, and a second run was byte-identical, proving idempotency at the CLI level, not just at the raw-SQL level. `RealUCClient.__init__(profile=...)` already resolves an arbitrary named profile with zero changes; the "seam" was never a code seam, only a question of which profile name CI's own credentials-writing step uses. `uc_client.py` and `cli.py` are untouched by this feature. |
| `.github/workflows/apply.yml` — live apply as the service principal (Layer 1) | *Built* | The job now runs `ucmeta apply --live --profile ucmeta-ci-apply` as `ucmeta-ci-apply` when `DATABRICKS_CI_HOST`/`DATABRICKS_CI_CLIENT_ID`/`DATABRICKS_CI_CLIENT_SECRET` are configured, writing a `~/.databrickscfg` profile from those secrets before the apply step runs. Stays fork-safe (SC-003-04): a `steps.credential.outputs.configured` check gates two mutually exclusive steps (live vs. fake-fallback), so which one ran is visible directly in the job's step list, not only in log text; no step echoes a secret value (verified by a dedicated test, see below). Not yet pushed — verified locally per the row below, verified for real once pushed. |
| Narrowing `tests/unit/test_workflows_yaml.py`'s no-`--live` assertion | *Built* | The existing test's no-`--live` assertion is now scoped to `_CREDENTIAL_FREE_WORKFLOW_FILES = ["validate.yml", "coverage.yml"]`, where the property still holds. Three new `apply.yml`-specific tests replace it: the live step(s) must be gated on the credential-configured check, a fake-fallback step gated on the same check (negated) must exist, and no `run:` line may echo a `secrets.*` value. All bound to SC-003-04. Full suite: 247 passed, 21 deselected (`uv run pytest tests/unit -m "not uc_live and not llm_live" -q`). |
| Local verification of the whole Layer 1 path before any push | *Done* | `uv run ucmeta apply contracts/analytics/customers.yaml --live --profile ucmeta-ci --approved-by hectormb.9@gmail.com` run twice against the real workspace, authenticated as `ucmeta-ci-apply` via the local `ucmeta-ci` profile: both runs `success`, all 17 writes `OK`, second run byte-identical to the first. `release_log.jsonl` shows both as `deployment_status: success`, `approved_by: hectormb.9@gmail.com` — approval and machine authorship recorded as separate facts, as SC-003-01 requires. Proves the identity, the grants and the command end-to-end — everything except the trigger, which is Layer 3's job. |
| Documentation of the identity, its grants, and its credential expiry date | *Built — `docs/ci-service-principal.md`* | Names the display name, application ID, every grant and why (tied to what `apply.py` does), the 2028-09-18 expiry, the rotation procedure (SC-003-02), and the manual secret-entry procedure naming exactly which three GitHub secrets to create and where. The secret value itself is never in this repository, only entered by hand once through GitHub's own UI, per Out of Scope. |
| Ownership transfer of the three demo tables (Layer 2) | *Real — approved and executed 2026-09-19* | Done live: all three tables' ownership moved to `ucmeta-ci-apply`, confirmed by reading each table's `owner` field back. The mechanical finding recorded in Rules & Constraints predicted this was necessary before it was attempted, not after. |
| Revocation of the owner's standing metadata-write access on the three demo tables (Layer 2) | *Real, partial — comments and properties genuinely blocked; tags are not* | Executed live: hector's identity re-granted `SELECT` only. Comment and property writes confirmed refused (`PERMISSION_DENIED: ... MODIFY`). Tag writes confirmed to still succeed via a metastore-admin bypass this feature cannot switch off — see Rules & Constraints and Behaviour for the full finding. The verdict is honestly split because the outcome is: two of three write types are enforced, one is not, and neither half should be described as the whole. |
| Verification that a laptop apply now fails correctly (SC-003-03) | *Real — and the result rewritten to match what was actually found* | Executed live against all three tables. The evidence is a `partial_failure`, not a clean refusal — SC-003-03 was rewritten in place (not left as the pre-execution prediction) once the tag-write gap was confirmed, because a scenario that describes a cleaner outcome than what the workspace actually does is worse than no scenario at all. |
| The real merge trigger firing on a merged change request (Layer 3) | *Blocked — depends on a pending decision outside this feature* | The mechanism is already built, already tested for shape, and already triggers on a push to main. What is missing is a remote and a merge, which depends on whether this repository is pushed publicly — a decision already under discussion, shared with F-PLATFORM-002, and not made here. Verdict names the dependency rather than assuming it resolves. |
| ADR-009 in the prototype's `docs/` | *Real — a shipped deliverable* | The diagnosis, the rejected alternatives and the two honesty points are exactly what an ADR is for, and this is the decision a reviewer is most likely to probe. Content spelled out above. |
| OpenID Connect federation instead of a stored secret | *Skip (named in Out of Scope and in the ADR)* | The better production answer, deliberately not built, named as the direction of travel rather than quietly omitted. |
| Machine identities for `validate.yml` and `coverage.yml` | *Skip (named in Out of Scope)* | Neither writes contract metadata to the catalogue, so neither is what the rule being enforced is about. Obvious follow-on, not this feature. |
| Automated creation of the CI secret | *Skip (manual by design)* | Scripting it needs a credential that can write repository secrets, which is a worse thing to hold than the secret being stored. One manual step, documented. |

## Open Questions

These must be resolved before the corresponding layer is built. The first is the one that
actually gates work, and it is the one hector needs to think about rather than merely answer.

| Question | Owner | Due | Status |
|----------|-------|-----|--------|
| Does Layer 2 get built now, later, or not at all? | hector | 2026-09-19 | *resolved: now.* Executed live against the real workspace. The laptop's comment and property writes are genuinely blocked; its tag writes are not, for the metastore-admin-bypass reason recorded in Rules & Constraints and Behaviour. Decided that documenting this precise, tested boundary is worth more than deferring for a cleaner-sounding but unverified claim. |
| Exact grant granularity: schema-level grants, or per-table grants on just the three demo tables? | hector | 2026-09-19 | *resolved: per-table for content privileges (`SELECT` on each of the three tables specifically, ownership on each transferred individually), schema-level only where the privilege type has no finer grain (`USE_SCHEMA`, `USE_CATALOG`, which are inherently schema/catalog-scoped and grant no content access by themselves). This is what was actually executed, not a separate design choice made afterward — recorded here so the ADR states what happened rather than what was planned. |
| Secret rotation policy for a credential expiring roughly two years out: is anything beyond the minimal prototype answer warranted? | hector | 2026-09-19 | *resolved: minimal.* Record the expiry date, write the rotation procedure down, revisit if the prototype outlives the interview. No scheduled rotation, no expiry-check workflow step — that would be operational machinery for a workspace Databricks may reclaim for inactivity long before two years is out, the over-engineering this project's own trade-offs already argue against elsewhere. |
| Should this feature's Layer 3 be sequenced before or after F-PLATFORM-002's own pending push to a public remote? | hector | 2026-09-19 | *resolved: finish Layer 1's code-side work first, then push.* Commit the grant script, wire `apply.yml` to the service principal, verify the whole path locally — only then push to GitHub, shared with F-PLATFORM-002's own pending push decision. The first real merge this repository ever sees then exercises the complete real pipeline (CI identity + Layer 2 enforcement) in one shot, rather than a partial version needing a follow-up PR to become real. |

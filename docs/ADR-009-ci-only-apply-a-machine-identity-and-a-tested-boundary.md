# ADR-009: CI-only apply — a machine identity for the write path, and a tested boundary on the human's

- **Status:** Accepted, and built. The workspace side is live: service principal
  `ucmeta-ci-apply` exists and holds the applier's grants; ownership of all three demo tables was
  transferred to it and the owner's own identity re-granted `SELECT` only, executed and verified
  against the real workspace on 2026-09-19. **The repository side is built too**, as of the same
  day: `scripts/provision_ci_apply_identity.sh` recreates the whole arrangement from nothing and
  was run live twice with byte-identical output; `.github/workflows/apply.yml` is wired to
  `ucmeta apply --live --profile ucmeta-ci-apply`, gated fork-safe on three named GitHub secrets;
  `RealUCClient` needed no authentication-path change at all (see "What was not yet true, and is
  now closed" below for why); `tests/unit/test_workflows_yaml.py` now asserts `apply.yml`'s live path
  is conditional on the credential and that no secret value is ever echoed, narrowed rather than
  weakened for the two workflows where "never passes `--live`" still holds. The real merge trigger
  remains blocked on a pending repository-push decision outside this ADR — the only thing left.
- **Date:** 2026-09-19
- **Decider:** hector
- **Affects:** the live workspace's grants and ownership on `workspace.analytics.customers`,
  `workspace.analytics.orders` and `workspace.marketing.campaigns` (**already changed**);
  `.github/workflows/apply.yml`, `tests/unit/test_workflows_yaml.py` and
  `scripts/provision_ci_apply_identity.sh` (**already changed**); `src/uc_metadata/uc_client.py`
  explicitly unchanged — confirmed unnecessary, see "What was not yet true, and is now closed"
  below; `apply.py` and `release_log.py` explicitly unchanged

## Context

Start from the diagnosis, and from how it was found, because the second part is the more
interesting half.

ADR-001 and this repository's README both state a hard rule: **a change request may validate and
dry-run; apply happens only on merge to `main`.** That rule is the spine of the governance
argument — it is what makes "reviewed, approved, then written to the catalogue" a property of the
system rather than a description of good intentions. It was true in practice and it was honoured
every single time. **Nothing enforced it.** Anyone holding the owner's Databricks credentials —
which, on this prototype, means the owner sitting at his own laptop — could run
`ucmeta apply --live` against the real workspace with no change request, no review, no merge and
no record of approval beyond whatever name they typed into `--approved-by`.

It was not a design review that found this, and not a checklist. It was the owner rehearsing the
walkthrough by *actually running the tool* — watching a real `COMMENT ON` land on a real table from
a shell prompt — and noticing that the thing he had just done was the exact thing his own design
says cannot happen. That is the whole difference between a stated control and an enforced one, and
it is worth closing precisely because a reviewer is entitled to ask "what stops you doing it
anyway?" and *"we wrote it down"* is a weak answer from a platform whose entire pitch is that gates
beat goodwill.

ADR-007 states the test every design in this project has to pass: *any design whose motive force is
goodwill reproduces the failure it claims to fix.* That test does not stop applying at the boundary
of the platform's own controls. A governance prototype that gates other people's workflows and
leaves its own core control resting on the author's discipline is arguing against itself, in the
one place a reviewer will look hardest.

Closing it properly means two separate things, and conflating them is how this kind of work goes
wrong. The first is giving continuous integration an identity of its own, so that CI **can** apply.
The second is taking the ambient write access away from the human, so that the laptop **cannot**.
Only the second makes the rule true, and only the second changes how the owner works day to day.

One mechanical fact shaped the second half before anything was attempted, and it is the detail most
likely to be discovered late by someone who does not write it down first: **revoking a privilege
from an object's owner is a no-op.** The three demo tables were created by the owner's identity,
which makes that identity their owner, and ownership carries full control implicitly rather than
through a grant that can be taken away. For the revocation to have any effect at all, ownership had
to *move*. This is an ownership transfer, not a `REVOKE`.

## Decision

**Continuous integration gets a non-human identity of its own, and the human's standing ability to
write metadata to the demo tables is taken away by transferring ownership rather than by revoking a
grant.** Built and approved in layers, because their reversibility differs sharply.

### Layer 1 — a machine identity, least-privileged

A workspace-level service principal, `ucmeta-ci-apply`, with credentials of its own that belong to
no person. It is granted exactly what the applier performs and nothing that is merely convenient:
`USE_CATALOG` on `workspace`, `USE_SCHEMA` on `workspace.analytics` and `workspace.marketing`,
ownership of each of the three demo tables (which is what now carries its comment, property and tag
writes), and — not a catalogue grant at all, and inert without it — `CAN_USE` on the SQL warehouse
the applier executes its statements through.

It is granted nothing else. No create or drop anywhere, no administrative standing at account,
workspace or metastore level, nothing on any other catalogue or schema, and nothing on
`workspace.platform.coverage_history` — that is ADR-008's write path and a different identity's
job. A service principal granted everything is a personal access token with extra steps; the
narrowness is the deliverable.

That the starting point is genuinely default-deny was confirmed rather than assumed: before any
grant existed, a token minted for a freshly-created principal was refused outright when it asked the
catalogue to list itself. Every capability the identity ends up with is therefore something somebody
deliberately added, which is what makes the least-privilege claim checkable instead of rhetorical.

**Grant granularity is per-table where the privilege has a table grain** (`SELECT` granted
explicitly on each of the three tables; ownership transferred table by table) **and
schema- or catalogue-level only where the privilege type has no finer grain** (`USE_CATALOG`,
`USE_SCHEMA`, neither of which grants any content access by itself). That is what was executed, not
a tidier description of it written afterwards.

### Layer 2 — the laptop stops being able to write, and exactly where it doesn't is written down

Executed live on 2026-09-19. Ownership of all three demo tables moved to `ucmeta-ci-apply`,
confirmed by reading each table's owner back. The owner's own identity was then re-granted `SELECT`
on each of the three tables, explicitly and individually — enough to harvest, to validate a contract
against the live table, and to print exactly what an apply would do, and nothing more.

**What this achieved, verified rather than asserted:** `COMMENT ON TABLE` and `SET TBLPROPERTIES`
are now cleanly refused for the owner's identity, with the workspace naming the identity, the object
and the missing privilege — `PERMISSION_DENIED: User does not have MODIFY on Table '...'`. That is
the failure surface this project asks for: a refused write that tells you which privilege was
missing is a working control; "apply failed" with the cause swallowed is an hour of debugging a
control that was doing its job.

### The part that did not work, recorded first rather than buried

**`SET TAGS` and `UNSET TAGS` still succeed for the owner's identity, with zero explicit grant.**

This was not inferred from documentation and it was not predicted by the design discussion. The
owner's effective privileges on the table were read directly — `databricks grants get-effective` —
immediately before and immediately after a tag write, and showed `SELECT` and nothing else
throughout. The tag write landed anyway, on the real catalogue.

The explanation is that the owner remains a member of the workspace's `admins` group — a metastore
administrator, because on a solo, personal Free Edition account there is nobody else to hold that
role — and Unity Catalog gives metastore admins an implicit bypass for tag operations specifically.
It is a different code path from the `MODIFY` privilege that correctly gates comments and
properties, and it is not something any table- or schema-level grant this decision makes can switch
off.

So the honest statement of what a live apply from the owner's laptop does today is not "it is
refused". It is: **`partial_failure`** — the comment write and the property write are named and
refused, and the tag writes silently land on the real catalogue with no change request, no review
and no merge. That is a materially different and more precisely true claim than the one this
decision set out to make, and stating it is worth more than stating the cleaner one.

Two things follow that are worth recording rather than glossing.

First, the empirical method is the point, and it is the same discipline ADR-004 and ADR-008 already
used where documentation was insufficient: **read the effective privileges back from the system,
before and after, rather than reasoning about what the grants ought to imply.** Had the grant list
been trusted instead of the behaviour, this ADR would be claiming a uniform block that does not
exist.

Second, `apply.py`'s existing partial-failure machinery handles this correctly without a line of
change. It was built in an earlier phase for a different cause — a mid-run failure such as an
unreachable warehouse — and it collects per-write outcomes and reasons, so it reports exactly which
writes succeeded, which were refused, and why. That it does the right thing when the cause of the
mix is a permission boundary rather than an outage is evidence that per-write outcome reporting was
the right shape to begin with. It is **not** a claim that it was designed for this; it was not.

### Why the remaining gap is documented and not closed

There is exactly one lever that would close it: **removing the owner from the `admins` group.** No
grant-level change can, because the bypass sits above the grant model.

That is deliberately not done, and it is named here so a future implementer finds a decision rather
than an oversight. It is a materially larger and harder-to-reverse change than anything else in this
decision: it affects the entire account rather than three tables, it would have to be undone through
a path that no longer runs as an administrator, and it was explicitly outside what this piece of
work was asked to do. The other changes here are scoped to three synthetic tables' metadata; this
one is not comparable to them and should not be smuggled through on the same approval.

In the organisation this prototype stands in for, the platform engineer and the metastore
administrator are different people, the account-level bypass does not apply to the engineer's
identity, and all three write types would be genuinely blocked. The mechanism demonstrated here is
the right one; on this specific environment it covers two of the three write types, and the third is
open for a reason that is environmental rather than a flaw in the design.

### Reversibility, which is why the layers were approved separately

This is the part that justifies the ceremony, so it is stated explicitly rather than left implied.

**Layer 1 is cheap to undo.** It adds a capability. Deleting the service principal is one call, it
disturbs nobody's access, and nothing else in the workspace changes. A decision that can be reversed
by deleting one object does not need a gate in front of it.

**Layer 2 is reversible but not trivially.** It removes a capability from the person who has to work
in this repository every day, and undoing it means transferring ownership of three tables back on a
live workspace — a real live action performed per table, not a configuration toggle, and not
something anyone should be doing at two in the morning before a walkthrough. That asymmetry is why
Layer 2 required its own separate, dated, explicit approval instead of riding along on approval of
the plan as a whole. Approving a design is not the same act as agreeing to give up your own write
access to a live system, and treating them as one act is how this sort of change gets made without
anyone noticing they made it.

## Consequences

- **The rule now has a mechanism behind it for two of the three write types, and the gap is
  documented for the third.** Getting a fully-applied, fully-attributed metadata change into the
  catalogue requires a merged change request. Getting a partial, tags-only one does not. Both halves
  of that sentence are true and neither is a summary of the other.
- **Approval and authorship stay separate facts.** The audit record continues to name the human
  whose merge authorised the change; the machine identity is who performed the write. Collapsing
  those into one field would destroy the distinction this decision exists to create.
- **Access control and content validation are independent layers, and neither substitutes for the
  other.** The service principal's elevated grants are an access-control concern. `apply()` still
  runs its own validation before attempting any write and still refuses the whole contract — whole,
  not partially — if it arrives by any route other than a clean validate. A privileged identity that
  skipped validation because it was privileged would mean this decision had traded one gap for
  another.
- **An out-of-band attempt is visible afterwards.** The refusal happens at the write, inside the
  applier, so the attempt still appends an audit record naming the mixed outcome. A control that
  blocks earlier and leaves no trace would be tidier and less useful.
- **Fork-safety is unchanged and non-negotiable.** A clone or fork with no secrets configured must
  still run the apply workflow, still demonstrate the mechanism against `FakeUCClient`, and still
  exit successfully — and the difference between "no credential configured, so this ran against the
  fake" and "a credential was configured and the live apply failed" has to be unmistakable in the
  job output. The in-repository fake is untouched by all of this; it has no relationship to
  Databricks permissions at all.
- **Blast radius moves in the right direction.** The owner's personal credential is the account
  owner's full standing in a string: every catalogue, table creation and deletion, the platform's
  own coverage history, workspace and identity administration, and the ability to grant itself
  anything further. The machine credential, if it leaked, buys an attacker the ability to read three
  synthetic tables in a free, disposable workspace and rewrite their descriptions and labels. It
  cannot create or delete anything, reach any other schema, read the coverage history, touch the
  account, or impersonate a person. The response is one call to delete it.
- **Rotation is a written procedure with a date attached, not an intention.** Mint the replacement
  while the current credential still works, update the stored secret, verify one apply, then delete
  the old one — so no window exists in which the identity has no working credential. The expiry date
  is recorded next to the grant script at the moment of minting, because a date nobody wrote down is
  a date nobody meets. For a prototype of this lifespan, rotation will most likely never be exercised
  for real; the requirement is that the plan and the date exist and are findable.
- **No break-glass path, deliberately.** No manual apply button, no workflow dispatch, no escape
  hatch "for emergencies". An emergency escape hatch is the mechanism by which every
  apply-only-on-merge rule in history has stopped being true.
- **Nothing outside the three demo tables' metadata changed.** Table creation and deletion (the
  workspace has to stay rebuildable from scripts), structural alteration (the live drift
  demonstration genuinely alters a column), the coverage-history write path and every read all stay
  exactly as they were. A broader revocation would have broken two other features to make a point
  this one already makes.

### What was not yet true, and is now closed

Stated plainly at the time this ADR was first written, because this decision's own stated principle
is that a permission applied by hand in a console and never written down makes the workspace
unrebuildable — which is a worse defect than the one being fixed. Kept here, in the past tense,
rather than deleted, because the gap and its closing are both part of the record.

**At first writing, the permission changes above existed only as manual changes against the live
workspace, not yet captured as a re-runnable script in this repository.** There was no grant script
under `scripts/`; `apply.yml` still ran against `FakeUCClient` and was not wired to the service
principal; and `tests/unit/test_workflows_yaml.py` still asserted that *no* workflow passes
`--live`. For that period, the workspace was **not** rebuildable from the repository — the single,
temporary exception to the disposable-workspace rule ADR-004 and `seed_demo_data.sql` otherwise
honour.

**All three are now built, the same day.** `scripts/provision_ci_apply_identity.sh` recreates the
entire arrangement from nothing — idempotent service-principal creation, both entitlements,
`USE_CATALOG`/`USE_SCHEMA`/warehouse `CAN_USE`, ownership transfer of the three tables, and the
owner's `SELECT`-only re-grant — run live twice against the real workspace with byte-identical
output. `.github/workflows/apply.yml` runs `ucmeta apply --live --profile ucmeta-ci-apply` when a
CI apply credential is configured, and falls back to the in-repository fake, unmistakably, when it
is not (SC-003-04). `tests/unit/test_workflows_yaml.py`'s no-`--live` assertion is narrowed to the
two workflows where it still holds, and replaced for `apply.yml` with assertions that its live path
is conditional on the credential and that no step ever echoes a secret value. The grant set, the
identity, its expiry and its rotation procedure are documented in `docs/ci-service-principal.md`.

**The seam question this section originally posed answered itself empirically, with no code
change.** The predicted two options were: CI writes a credentials-file profile of the expected name
before the job runs (no production code change), or `RealUCClient` grows a fallback authentication
path when no profile is named (tidier, touches the one module every other module depends on). The
first was not just preferred in the abstract — it was proven directly: a local profile named
`ucmeta-ci` was hand-authenticated in `~/.databrickscfg`, and
`ucmeta apply contracts/analytics/customers.yaml --live --profile ucmeta-ci` ran end-to-end as
`ucmeta-ci-apply` against the real workspace, twice, with the second run byte-identical to the
first. `RealUCClient.__init__(profile=...)` already accepts an arbitrary profile name; there was
never a code seam to close, only a decision about which profile name CI's own credential-writing
step should use. `uc_client.py` and `cli.py` remain unchanged by this decision.

### What this decision explicitly does not claim

Three things, all worth saying before a reviewer has to ask.

**First, an account administrator can always re-grant himself what was taken away.** This was
predicted before execution and remains true: the same person holds both the platform-engineer and
the metastore-administrator role here, so what Layer 2 removes is *ambient authority* — the ability
to write simply because of who you already are, with no deliberate step in between — not the
possibility of writing. Bypassing the comment and property block requires a visible, self-aware act
of privilege escalation. That is a real improvement and it is not a hard boundary, and the two
should not be confused.

**Second, and this was not predicted: one entire class of write was never gated by anything this
decision controls.** Tag writes need no re-escalation, no deliberate act, and no grant. They simply
work, for the reason given above. The difference between the two honesty points matters: the first
says the boundary can be crossed by someone who chooses to; the second says that for one operation
there was no boundary to cross. Only one of those was anticipated, and pretending otherwise would be
the "we knew all along" move this project's ADRs have avoided elsewhere.

**Third, the machine credential is long-lived, and that tension is named rather than smoothed over.**
ADR-004's position is "no long-lived personal access tokens", and it has been honoured because until
now nothing in this project needed a stored credential at all. A machine credential with a roughly
two-year expiry is long-lived by any reasonable reading. The claim being made is not that it is
short-lived. It is that it belongs to a non-human identity with a handful of narrow grants on three
synthetic tables, lives in a managed secret store rather than on a laptop, is revocable in one call
without disturbing any person's access, and is rotatable without downtime — whereas a personal
access token is a human's entire standing in the workspace in a string. Different risks that happen
to share the word "long-lived", and the difference is in reach and revocability, not lifetime.

## Alternatives considered

- **(a) Document the rule and rely on discipline — the status quo.** Rejected, and named first
  because it is what was actually in place and it had worked flawlessly in practice. It is
  *precisely* the goodwill-as-motive-force failure this project's own diagnosis is built on: ADR-007
  argues that any design whose motive force is goodwill reproduces the failure it claims to fix, and
  the README opens by saying that "go tag your tables" campaigns spend goodwill and leave nothing
  durable behind. A platform making that argument about other people's workflows, while its own
  central control rests on the author remembering not to type a command, is arguing against itself
  in the place it can least afford to. The cost of rejecting it is real — the owner gave up
  convenience he had every day — and it is the whole point.
- **(b) Store the owner's own credentials as the CI secret.** Rejected, and it would have been by
  far the fastest route to a working live apply in CI. It puts an account administrator's full
  standing into a CI secret store, which inverts the blast-radius argument above: an attacker with
  that secret gets everything, not three tables' descriptions. It makes every apply in the audit
  trail indistinguishable from a human's own action, destroying the separation between who approved
  a change and who performed it — the distinction this decision exists to create. And it would make
  the security posture *worse* than the status quo rather than better, since today that credential
  at least never leaves the laptop. "CI can apply" achieved this way is not the control being asked
  for; it is the same ambient authority with a second copy of the key.
- **(c) A personal access token for CI.** Rejected against ADR-004's no-PATs rule, which this
  project has actually honoured rather than merely claimed — there is no long-lived token anywhere
  in it today, which is why the rule has teeth. A PAT is a durable secret carrying a human's full
  workspace standing, with no grant model of its own to narrow it. Databricks' own guidance points
  the same way: production writes performed by service principals, so interactive users need no
  write access to production at all. Rejecting (c) is what makes the long-lived-credential admission
  in (iii) above a narrow one rather than a retreat from the rule.
- **(d) OpenID Connect federation between the CI platform and the workspace, with no stored secret
  at all.** **The strongest option, and deliberately deferred rather than rejected on merit.** It
  removes the stored secret entirely, which removes rotation, expiry and leak-of-a-stored-credential
  as concerns in one move — every weakness admitted in the third honesty point above is a weakness
  this alternative does not have. It was not built because it needs a trust relationship configured
  workspace-side and is meaningfully more setup than the thing it improves on, for a prototype whose
  secret guards three synthetic tables in a free, disposable workspace and expires in two years.
  **This is the production direction of travel**, named here so that the choice reads as a
  scope decision with a known better answer rather than as ignorance of one. An organisation
  adopting this design should start here and skip the stored secret altogether.

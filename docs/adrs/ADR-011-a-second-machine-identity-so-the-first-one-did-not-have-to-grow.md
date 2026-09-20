# ADR-011: A second machine identity, so the first one did not have to grow

- **Status:** Accepted, built, and **live**. The identity decision was made and dated
  (F-PLATFORM-005, Revision History rev 2, 2026-09-20) before this ADR was written, and this
  document records the reasoning behind it rather than reopening it. The workspace side is now
  real, executed 2026-09-20: `ucmeta-ci-provision` exists as an actual service principal
  (application ID `b0047725-775f-455e-8b6a-7186fdb4b9b0`), holds `CREATE_CATALOG` on metastore
  `metastore_aws_us_east_2` and `CAN_USE` on the warehouse, and its credential is minted and
  stored as three GitHub Actions secrets. Both live scenarios ran: `ucmeta-ci-apply` was
  refused (`PERMISSION_DENIED`, SC-005-02) and `ucmeta-ci-provision` succeeded (SC-005-01),
  producing the first real catalog this platform has ever created — `data_platform_demo`.
  The grant script and the provisioning run were each executed twice with identical results,
  confirming idempotency live rather than only against the fake. See "What the live workspace
  actually did" below, which is no longer a placeholder.
- **Date:** 2026-09-20 (decided, built and live-verified the same day)
- **Decider:** hector
- **Affects:** a new service principal, `ucmeta-ci-provision`, and its grants (**created and
  granted live**); `scripts/provision_ci_provision_identity.sh` (**new file, built, run live
  twice**);
  `.github/workflows/provision-catalog.yml` (**built**: gains a credential check and two
  mutually exclusive branches); `tests/unit/test_workflows_yaml.py` (**built**: narrowed, not
  deleted); `docs/ci-service-principal-provision.md` (**built**); `docs/ci-service-principal.md`
  (one cross-reference line added); this document adds one forward-reference sentence to
  ADR-009 and changes nothing else in it. `src/uc_metadata/uc_client.py`,
  `src/uc_metadata/provision_catalog.py`, `src/uc_metadata/cli.py`,
  `src/uc_metadata/fake_uc.py`, `src/uc_metadata/release_log.py`, `change_classes.yaml` and
  `scripts/provision_ci_apply_identity.sh` are **all explicitly unaffected** — the last one's
  absence from this ADR's diff is a checkable fact, not an oversight.

## Context

F-PLATFORM-004 built a catalog-provisioning pipeline with a mechanism complete enough to
validate a request, build an ordered plan of three statements, and execute them — against an
in-memory fake. It never provisioned a real catalog, and that was not an oversight: the one
sentence that made a live path impossible without a further decision is in ADR-009's own
Layer 1 section, describing `ucmeta-ci-apply`: *"It is granted nothing else. No create or drop
anywhere, no administrative standing at account, workspace or metastore level."* Creating a
catalog needs exactly the standing that sentence rules out, and `ucmeta-ci-apply` is the only
automated identity this workspace has.

So the choice was genuinely binary, and it is worth stating the rejected option's case fully
before explaining why it lost, because it was not a weak case.

**Option A — widen `ucmeta-ci-apply` to also hold the metastore-level `CREATE_CATALOG`
privilege.** This is the cheap option, and cheap in every dimension that matters to a solo
maintainer: the identity already exists, its credential is already minted and stored as three
GitHub secrets, its local profile already works, and `provision-catalog.yml` already knows its
name from `apply.yml`'s pattern. One grant, applied through the same script that already
manages this principal's other grants, and the live path exists. No second principal to create,
no second credential to mint and store, no second rotation date to track, no second document to
keep in sync with the first. Reversibility is good too: undoing it means revoking one grant and
re-amending one ADR paragraph.

The cost of Option A is precise, not vague, which is what makes it worth taking seriously rather
than dismissing by reflex. ADR-009's Layer 1 sentence would become false the moment the grant
landed, and the ADR would need an amendment admitting the least-privilege claim had narrowed.
The blast radius of `ucmeta-ci-apply`'s credential — today "vandalise the metadata on three
synthetic tables" — would grow to "vandalise the metadata on three synthetic tables, and create
arbitrary namespaces in the metastore." Two unrelated capabilities behind one credential is
already a cost independent of the amendment; the amendment is the honesty tax on top of it.

**Option B — a new, provisioning-only service principal, `ucmeta-ci-provision`.** More
expensive to build: a second principal to create and grant, a second script (a sibling, not an
edit, since a single script standing up two identities with two unrelated privilege sets reads
worse than two scripts each describing one), a second document, a second set of three GitHub
secrets, a second rotation date to eventually track. Real overhead, named plainly rather than
minimized, for a solo maintainer who now has two credentials to keep straight instead of one.

What Option B buys in exchange: ADR-009's Layer 1 claim about `ucmeta-ci-apply` stays literally
true, with no footnote. Each identity's blast radius stays legible entirely on its own —
`ucmeta-ci-apply` still means "three tables' metadata, nothing more"; `ucmeta-ci-provision`
means "creates catalogs and schemas, nothing more" — and a reader does not have to hold both
identities' histories in mind to understand either one. It is also the shape a production
answer would take, since separation by function is the exact argument F-PLATFORM-003 made when
it gave CI an identity distinct from the human's in the first place; Option B is that argument
applied one level further in, not a new argument invented to justify a preference.

A fair summary, stated without retrofitting the winner as obviously correct: **Option A is
cheaper to build and more expensive to explain; Option B is more expensive to build and defends
itself.** Both are reversible, though not equally — Option A is undone by revoking a grant and
re-amending an ADR; Option B is undone by deleting a principal nobody else depended on, which is
the easier of the two undos.

## Decision

**Option B.** A second, provisioning-only service principal, `ucmeta-ci-provision`, is created
and granted the metastore-level `CREATE_CATALOG` privilege plus the warehouse `CAN_USE` its
statements execute through, and nothing else. `ucmeta-ci-apply` is not widened, not re-granted,
not renamed, not reused for provisioning, and this ADR changes not one line of code that
identity touches.

The reasoning is not merely "separation is nicer." It is specifically this: **a prototype whose
entire argument is least-privilege separation by function should not make its first exception at
the first moment separation costs something.** ADR-009 exists because "we wrote it down" was
recognized as a weak answer to "what stops the ambient-authority failure from recurring," and the
project's whole pitch since then has been that gates beat goodwill and narrow grants beat
convenient ones. Widening `ucmeta-ci-apply` here would not be a neutral engineering trade-off; it
would be the platform's first live demonstration that its own stated principle bends the first
time bending is cheaper than holding it. That is a legitimate reason to reject the cheaper
option, not merely an aesthetic one — a prototype's credibility with a reviewer rests partly on
whether its own automation follows the rule it's arguing other people's workflows should follow.

### The overhead, stated plainly

- A second service principal to create, grant and eventually delete.
- A second checked-in grant script (`scripts/provision_ci_provision_identity.sh`), sibling to
  `provision_ci_apply_identity.sh` rather than a change to it.
- A second credential, minted separately, stored under three GitHub secret names distinct
  enough from `ucmeta-ci-apply`'s that one cannot be pasted into the other's slot unnoticed
  (`DATABRICKS_CI_PROVISION_HOST` / `DATABRICKS_CI_PROVISION_CLIENT_ID` /
  `DATABRICKS_CI_PROVISION_CLIENT_SECRET`, next to `DATABRICKS_CI_HOST` /
  `DATABRICKS_CI_CLIENT_ID` / `DATABRICKS_CI_CLIENT_SECRET`).
- A second rotation date to record and eventually act on. This bullet assumed, when written,
  that the second credential would simply inherit `ucmeta-ci-apply`'s minimal,
  no-scheduled-rotation policy (F-PLATFORM-003 Open Questions rev 4) and differ only by having
  two dates instead of one. **Live minting proved otherwise** — the credential came out with a
  30-day lifetime rather than a ~2-year one, so the overhead here is materially larger than
  predicted: a near-term rotation that actually has to happen, not a date that will probably
  never come due. See "What the live workspace actually did" below; the cost is left as found
  rather than the original estimate being quietly corrected.
- A second document, `docs/ci-service-principal-provision.md`, to keep in sync with the first.
- One more thing for a solo maintainer to hold in their head when reasoning about "what can this
  automation actually do." This is a real cost, not a hypothetical one, in a project whose other
  stated virtue is that a reviewer can hold the whole system in their head at once.

None of this is minimized. It is accepted because the alternative was cheaper to build and more
expensive to defend, and defending the design is the part of this prototype that matters most.

## Blast radius, stated concretely, and why the two are disjoint

- **`ucmeta-ci-apply`**, if its credential leaked: an attacker can read three synthetic tables in
  a free, disposable, non-commercial workspace, rewrite their descriptions, properties and tags.
  They cannot create or delete anything anywhere, cannot reach any other catalog or schema,
  cannot touch the platform's own coverage history, cannot reach the account, and cannot
  impersonate a person. Unchanged by this ADR — see `docs/ci-service-principal.md`'s own Blast
  radius section for the full statement.
- **`ucmeta-ci-provision`**, if its credential leaked: an attacker can create catalogs and
  schemas in the same workspace and label what they created. They cannot read or write a single
  table's data or metadata, cannot touch the coverage history, cannot reach the account, and
  cannot impersonate a person.
- **The two radii do not overlap at all.** Neither credential can do anything the other's
  credential can do. An attacker holding both gains the union of two small, disjoint
  capabilities rather than one materially larger one — which is exactly the property a single
  widened `ucmeta-ci-apply` credential would not have had: Option A's one credential would have
  carried both radii at once, in one string, one leak away from both.

## ADR-009 is left intact, deliberately

ADR-009's Layer 1 section states, of `ucmeta-ci-apply`: *"It is granted nothing else. No create
or drop anywhere, no administrative standing at account, workspace or metastore level."* This
decision leaves that sentence literally true — not narrowed, not re-scoped, not requiring a
footnote — because `ucmeta-ci-apply` gains nothing from this ADR. That was a goal of this
decision, not an incidental side effect of it: F-PLATFORM-004 explicitly handed this feature an
"amendment obligation" — if the gap were closed by widening `ucmeta-ci-apply`, ADR-009's claim
would need amending. Choosing Option B discharges that obligation by making it moot rather than
by satisfying it, which is a materially different outcome from the obligation being forgotten,
and is worth being precise about for exactly that reason.

ADR-009 itself is edited by exactly one sentence as a consequence of this ADR — a forward
reference noting that a second identity was later introduced for catalog creation specifically,
so a reader arriving at ADR-009 first is not left thinking its Layer 1 claim is the whole story
of this workspace's automation. Nothing else in that document changes.

## What the live workspace actually did

Executed 2026-09-20 against the real Free Edition workspace. This section was written as a
placeholder in the expectation that it would record a surprise, because ADR-009's own most
valuable section is the one recording what its authors predicted wrongly. **The honest headline
this time is that there was no architectural surprise at all**, and saying so plainly is more
useful than manufacturing one: every claim this ADR makes about the identity separation held
exactly as designed on the first attempt. The interesting finding is real but it is operational
rather than architectural, and it is recorded below alongside the things that simply worked.

### The architecture behaved exactly as predicted

- **`ucmeta-ci-provision` was created, granted and used successfully on the first attempt.** The
  grant type, the securable it attaches to, and the SDK constant names were all as this document
  predicted from reading `databricks/sdk/service/catalog.py`: `CREATE_CATALOG` granted against
  `SecurableType.METASTORE`, addressed by the metastore's ID. No scoping surprise, no naming
  surprise, nothing that had to be discovered by trial.
- **The metastore is `metastore_aws_us_east_2`, ID `84f1ebb2-8db7-4748-9e66-c03d091fd89c`.**
  Recorded here for the same reason ADR-009 names its own workspace, warehouse and table
  specifics — a decision record that describes "the metastore" abstractly is harder to verify
  later than one that names it. The *name* was in fact learned from the live permission-denied
  message rather than looked up, which is a small illustration of how much a well-formed error
  message carries.
- **`ALTER CATALOG ... SET TAGS` behaved like its table-level cousin.** The sensitivity label
  landed on the first run, with no dialect or granularity difference from `set_table_tags`. This
  was the statement of the three whose live behaviour F-PLATFORM-005 judged least certain; it
  turned out to be the least eventful.
- **Idempotency held live, in both senses and without special handling.** Re-running the same
  provisioning command produced an identical clean `success` with all three writes reported `OK`
  again and no duplicate-object errors; re-running the grant script produced "Already exists …
  skipping creation", "entitlements present … no-op", and cleanly re-applied grants. Both claims
  had only ever been proven against the in-memory fake and in unit tests before this.

### The refusal, verbatim — and the cascade behind it

SC-005-02 ran first, deliberately, as `ucmeta-ci-apply`, to capture the pre-grant state before it
stopped existing. The result was `deployment_status: failed`, with the create-catalog step
refused exactly as predicted:

```
ServiceError(error_code=BAD_REQUEST,
  message="PERMISSION_DENIED: User does not have CREATE CATALOG on Metastore 'metastore_aws_us_east_2'.")
```

That message names the identity's missing privilege and the securable it was missing it on, which
is precisely the legibility F-PLATFORM-005's Rules & Constraints asked for: nobody reading it
would go looking in the request file for the problem.

**The two failures behind it are worth recording as evidence rather than noise.** The schema write
and the tag write also failed, with `NO_SUCH_CATALOG_EXCEPTION` — the catalog was never created,
so nothing downstream of it could succeed. That cascade is not a defect and it is not incidental:
it is the first live demonstration that the ordered three-step plan F-PLATFORM-004 introduced
(rev 3, when `default_schema` turned provisioning from one statement into a list) has a *real*
dependency chain, not merely an asserted one. Until this run, the ordering claim had been proven
only by unit tests against a fake that had no way to enforce it. A real metastore enforced it.
The run also confirmed the partial-failure machinery reports a genuine all-writes-failed outcome
as `failed` rather than rounding it to something tidier.

`ucmeta-ci-apply` ended that run holding exactly the grants F-PLATFORM-003 gave it and nothing
else. No state changed. That is the empirical confirmation of this ADR's central claim — the
grant script for one identity never reaches into the other's — and it is now a tested property
rather than a designed one.

### The one real finding: a 30-day credential nobody chose

The credential minted by hand for `ucmeta-ci-provision` has a **30-day lifetime** (minted
2026-09-20, expires 2026-10-20), not the roughly two-year lifetime `ucmeta-ci-apply`'s credential
has and that this ADR's "second rotation date to record and eventually act on" bullet silently
assumed it would match.

This matters more than its size suggests, for two reasons. First, the *reasoning* recorded for
`ucmeta-ci-apply`'s minimal-rotation policy does not survive the change: that position rested on a
two-year credential plausibly outliving this disposable workspace, so "rotation will most likely
never be exercised for real" was a defensible conclusion. Copy-pasting that conclusion onto a
30-day credential would have been reasoning by analogy from a premise that no longer held. The
honest statement is that this credential **will** need rotating within 30 days if the live path is
meant to keep working, and `docs/ci-service-principal-provision.md` records it that way rather
than inheriting the sibling document's more comfortable conclusion.

Second, and more interesting as a process observation: this was discovered only *because* the
secret is minted by hand. Nothing in this repository chose 30 days; it is what the console
offered and what was accepted in the moment. A scripted mint would have made the lifetime an
explicit parameter somebody had to type — but scripting it is exactly what F-PLATFORM-003's Out
of Scope rules out, for the good reason that it needs a credential worse than the one it would
produce. So the finding is a genuine trade-off surfacing rather than a mistake: the manual step
that keeps a dangerous credential from existing is the same manual step that let an unchosen
expiry slip in unnoticed. Recorded here rather than quietly fixed, because the next person to
mint a credential in this project should know to look at the lifetime field.

### The first real catalog

`data_platform_demo`, containing schema `demo`, tagged `sensitivity: internal`, created
2026-09-20 by `ucmeta-ci-provision` from `catalog-requests/data-platform-demo.yaml`
(`business_application_id: BA-40092`, `requested_by: hectormb.9@gmail.com`,
`environment: bronze`). Kept permanently as standing evidence, per F-PLATFORM-005 revision 2;
see `docs/ci-service-principal-provision.md` for the record of what it is and who made it.

Three entries were appended to `release_log.jsonl` by this session — the refused run and the two
successful ones — each carrying `requested_by` as a field distinct from `approved_by`. That
confirms F-PLATFORM-004's rev-3 audit-record decision (widen the existing record rather than
introduce a second type) holds under a live run and not only under the fake. Both fields read
`hectormb.9@gmail.com` here, because these were manual local runs with no separate reviewer in
the loop; the distinction between the two fields is structural, and a merge-triggered run is
where it carries two different names.

## Alternatives considered

- **(A) Widen `ucmeta-ci-apply` to also hold `CREATE_CATALOG`.** Rejected. The cheaper option in
  every dimension except the one this project has staked its argument on — see Context and
  Decision above for the full case, argued fairly rather than retrofitted as an obvious loser.
  Named here again because Out of Scope closes it explicitly: a later implementer looking for
  the cheap path should find it closed, not merely unmentioned.
- **(B) A second, provisioning-only identity (`ucmeta-ci-provision`).** Chosen. See Decision.
- **(c) OpenID Connect federation instead of a stored secret, for either or both identities.**
  Still the better production answer, per ADR-009's own Alternative (d), and this decision makes
  it marginally more attractive rather than less — there are now two stored secrets federation
  would remove instead of one. Not built here for the same reason ADR-009 deferred it: it needs a
  trust relationship configured workspace-side, and is meaningfully more setup than the thing it
  improves on for a prototype whose secrets guard a free, disposable workspace. Named as the
  direction of travel, not reconsidered on its merits here.
- **(d) A break-glass manual trigger for provisioning, bypassing the merge-only rule for
  urgency.** Not seriously considered. F-PLATFORM-003 and F-PLATFORM-004 both already rule this
  out for the same reason ADR-009's Consequences state it: an emergency escape hatch is the
  mechanism by which every merge-only rule in this project's history would stop being true.

## Consequences

- **Two machine identities exist in this workspace instead of one, each legible on its own.**
  Understanding what either credential can do never requires reasoning about the other.
- **The workspace remains rebuildable from the repository with two identities instead of one.**
  `scripts/provision_ci_apply_identity.sh` and `scripts/provision_ci_provision_identity.sh`,
  run together in either order against an empty workspace, reproduce the entire two-identity
  arrangement (F-PLATFORM-005 SC-005-04) — neither script reaches into the other's identity.
- **Fork-safety now has two conditional branches to get right instead of one.** `apply.yml` and
  `provision-catalog.yml` both take the shape of a credential check plus two mutually exclusive
  steps; `tests/unit/test_workflows_yaml.py` asserts the same three properties (conditional live
  path, fake fallback, no secret ever echoed) for both files now.
- **A solo maintainer carries more operational overhead** — two credentials, two rotation dates,
  two documents — in exchange for a claim ADR-009 already made staying true without qualification.
  Whether that trade was worth it is exactly the question this ADR exists to let a reader judge
  for themselves, which is why the overhead is stated above rather than minimized. Live execution
  made that overhead concretely larger than predicted, via the 30-day credential lifetime: the
  second identity now carries a rotation that will genuinely fall due on 2026-10-20, where the
  first identity's has always been theoretical. A reader weighing this decision should weigh that
  version of the cost, not the estimate written before it was known.
- **The separation is now a tested property, not a designed one.** SC-005-02 executed live as
  `ucmeta-ci-apply` and was refused by the metastore; the same request executed live as
  `ucmeta-ci-provision` and succeeded. Neither identity can do the other's job, and that sentence
  is now backed by two runs rather than by two grant scripts read side by side.

# ADR-010: Catalog provisioning by request file, and why it is create-only and fake-only

- **Status:** Accepted and built. Every component this decision describes exists on `main` and
  works: `catalog-requests/` with its nine-field template, `src/uc_metadata/provision_catalog.py`,
  three new methods on the `UCClient` seam implemented on both sides, the `provision-catalog.yml`
  workflow, the `change_classes.yaml` declaration, the release-record widening, and the
  scenario-bound tests. **One qualification, stated rather than rounded up:** the source spec,
  F-PLATFORM-004, still carries `status: draft` in its own frontmatter. That is a known and
  deliberately-untouched loose end rather than a signal that anything here is unsettled — the
  feature was built, revised through four revisions, and has since had its mechanism exercised
  against a real metastore. "Accepted and built" describes the decision and the code; `draft`
  describes a frontmatter field nobody bumped. Both are true and the second is not worth
  laundering into the first.
- **Date:** 2026-09-19 (decided and built), with revision 4's tag widening decided 2026-09-20
- **Decider:** hector
- **Affects:** `catalog-requests/` and `catalog-requests/_template.yaml` (**new**);
  `src/uc_metadata/provision_catalog.py` (**new**); `src/uc_metadata/uc_client.py` (**three new
  methods** on the protocol and on `RealUCClient`: `create_catalog`, `create_schema`,
  `set_catalog_tags`); `src/uc_metadata/fake_uc.py` (**the same three methods**, plus a real notion
  of catalogs and schemas and accessors to read them back);
  `.github/workflows/provision-catalog.yml` (**new**); `change_classes.yaml` (**one declaration
  added**); `src/uc_metadata/cli.py` (**one new verb**); `src/uc_metadata/release_log.py` (**two
  documented field-meaning widenings plus one additive optional field**); `tests/unit/`.
  `src/uc_metadata/models.py` and `src/uc_metadata/owner_registry.py` are **imported from and not
  modified** — the request model reuses the contract schema's `Sensitivity` and
  `CertificationTier` enumerations rather than declaring parallel ones, and the
  business-application identifier resolves through the existing `resolve_owner`.
  `scripts/provision_ci_apply_identity.sh` is **explicitly untouched**: this decision grants no
  identity anything (see "Why this feature stops where it does").
- **Sequel:** [ADR-011](ADR-011-a-second-machine-identity-so-the-first-one-did-not-have-to-grow.md)
  owns the identity decision that made the live path possible, and F-PLATFORM-005 owns the live
  path itself. See "What is true today, and what this feature's own scope was" below — the live
  path now exists and has created real catalogs, which was not true when this decision was made.

## Context

Everything this platform did before this feature happened *inside* containers somebody else had
already made. A contract names a dataset by its three-part `catalog.schema.table` name, harvest
reads that table, apply writes comments, properties and tags onto it, and coverage counts how many
such tables are described. Every one of those operations presupposes that the catalog and the
schema already exist because a human created them by hand, out of band, before the platform was
ever pointed at them. The prototype's entire surface was metadata *about* objects, with no way to
bring an object into existence.

That is a visible hole in the story the platform tells, and it sits directly under ADR-007's
forcing function. ADR-007 rests on the claim that *a new dataset is not provisioned without a valid
contract* — but provisioning itself was described as somebody else's flow, a centrally-owned
Terraform pipeline this prototype explicitly does not build or simulate. A reviewer is entitled to
ask the obvious next question: if a business team needs a new top-level catalog for their area,
what actually happens? The honest answer was **"they ask hector, and he types `CREATE CATALOG` into
a SQL editor."**

That is the same untracked, unreviewed, unrecorded act this project had spent three features
arguing against everywhere else. ADR-009 exists because the owner noticed he could write metadata
to a live table from a shell prompt with no merge behind it; this is the identical failure one
level up, on a bigger object, and it had gone unremarked because creating a catalog was never
framed as something the platform did at all.

### The mechanism question, which is the real decision here

Closing the hole means picking a mechanism by which a team asks for a catalog and somebody approves
it. Four were genuinely available, and the file only wins if the other three are stated fairly.

**A ticket in a tracker.** The most common real-world answer, and the one with the lowest adoption
cost for the requester — everybody already has a tracker and already knows how to file a ticket.
Its fatal property here is that the request and the thing that acts on the request live in two
systems that do not know about each other. Approval means a human moved a card, and the link
between "the card was approved" and "this catalog exists" is somebody's memory. It also reproduces
the queue: a ticket is a request for somebody else's attention, and ADR-006 already records that a
queue is what killed the "go tag your tables" campaigns this project exists to replace.

**A web form.** Better than a ticket in that it can act directly. Worse in every other dimension
that matters to this prototype: it is new infrastructure to build, host, authenticate and keep
running; the request stops being a reviewable artifact and becomes a row in whatever the form wrote
to; and ADR-003 has already taken this exact position for contracts — files plus change requests
are the authoring surface — so building a form here would mean the platform argues one thing about
metadata and the opposite about provisioning, in the same repository.

**Grant the requesting teams `CREATE CATALOG` directly.** The genuinely decentralised option, and
it deserves more credit than it usually gets: it removes the platform from the critical path
entirely, which is what a team waiting on a catalog actually wants. It is rejected because it
removes the review rather than relocating it. A team with the privilege creates catalogs with no
artifact, no approval and no record — which is precisely today's failure mode, redistributed to
more people. It would also be the first place this platform handed out a metastore-level privilege
to a human identity, which is the opposite direction from everything ADR-009 argued.

**A file in the repository, reviewed as a change request and acted on by merge.** Chosen. Three
properties win it, and none of them are aesthetic:

1. *It is the mechanism this repository already uses.* Contracts work this way, `apply.yml` works
   this way, the two-class routing in ADR-006 works this way. Provisioning becomes one more path
   filter on a shape that already runs, rather than a second governance model to keep consistent
   with the first.
2. *It makes the request reviewable as an artifact.* The reviewer approves a specific, diffable,
   permanently-recorded statement of what was asked for and by whom — not a summary of it. The file
   is the request, the review of that file is the approval, and the merge is the authorisation.
   Those three facts are the same object, so they cannot drift apart.
3. *It costs no new infrastructure.* No service, no database, no form, no second identity system.
   For a prototype whose credibility rests partly on a reviewer being able to hold the whole thing
   in their head, adding zero moving parts is worth more than it sounds.

## Decision

**A team asks for a catalog by adding a YAML file to `catalog-requests/`. Merging that file to
`main` is the approval and the authorisation, and a pipeline then validates the request and
executes an ordered three-statement plan: create the catalog, create a schema inside it, label the
catalog.** The verb is create-only, with the catalog's labels as its single named exception, and —
in this feature — it runs against the in-repository fake and nothing else.

The sub-decisions below are the ones worth recording, because each had a cheaper alternative that
was examined and lost for a stated reason.

### Idempotent no-op when the catalog already exists, not refusal

A request whose catalog already exists produces a successful run in which nothing changed, not a
failure. Refusal is the tidier-sounding option — "this catalog already exists, I will not pretend
to create it" — and it was rejected on the strength of two concrete cases rather than on principle.

*The re-run case.* Workflow runs get re-run from the Actions UI, routinely, for reasons that have
nothing to do with the request: a flaky step, a cancelled job, somebody checking whether a fix
took. A pipeline that refuses on re-run turns an ordinary operational gesture into a red X that
somebody then has to interpret. The moment a person is least equipped to distinguish "this failed
because something is wrong" from "this failed because it already worked" is the moment they are
re-running a job to find out what happened.

*The revert-and-re-merge case.* This one is sharper, because it interacts with an asymmetry this
feature deliberately accepts. Reverting the merge that created a catalog does **not** delete the
catalog — there is no delete path. So a revert followed by a re-merge is a perfectly reachable
sequence in which the request lands a second time against a catalog that already exists. Under
refusal semantics, the repository would contain a merged request whose pipeline failed, with the
catalog sitting there anyway. That is a worse state to explain than a clean no-op.

There is also a consistency argument that would have been sufficient on its own: every other write
path in this system is idempotent by design, and apply's whole reversibility claim rests on it. A
provisioning step that refused on re-run would be the single exception, and the exception would
have to be remembered by everyone reasoning about the system.

**What is explicitly not claimed:** the pipeline cannot tell whether the pre-existing catalog is
the one this request meant. A catalog created by hand, or by a different team's request, with the
same name is indistinguishable to this feature. That limitation is named in Out of Scope rather
than papered over with a check this feature does not perform.

### Create-only, with the catalog's labels as the single named exception

The verb's powers are: create a catalog, create a schema inside it, write the catalog's
classification labels. No deletion, no rename, no ownership mutation, and no re-application of a
changed description over a catalog that already exists.

**What a delete path would have required in exchange, and why it was not taken.** It would have
bought one real thing: reversibility parity with apply, whose central claim is that reverting the
merge reverses the effect. Today that parity does not hold — removing a request file does nothing,
and reverting the merge that created a catalog leaves the catalog standing — and this ADR names
that asymmetry rather than hiding it. The price was judged far too high. A provisioning tool that
can also destroy is a **materially different security object** from one that can only create: the
identity behind it would need `DROP` standing at metastore level, turning a leaked credential from
"can create namespaces" into "can destroy namespaces and everything inside them". Worse, the
reversibility that would justify it is exactly what makes it dangerous — a revert-triggered
deletion is a catastrophic operation fired by an ordinary git gesture, on an object that may by
then contain other teams' tables. Anything beyond creation is a separate feature with a separate
and much more careful security argument, and it should not ride in on this one's approval.

**Why labels are the exception.** Two reasons were given when the exception was one field
(sensitivity), and they are not equally strong:

- *Recoverability.* If the label statement is the one that fails — the state SC-004-06 leaves
  behind — a create-only label could never be applied afterwards. The catalog would carry a wrong
  or missing classification permanently, with no path back through the reviewed mechanism. Making
  the label write converge on re-run means the fix is simply to run it again.
- *An uncorrectable classification gets corrected unofficially.* This was the stronger argument at
  the time and it is about urgency, not tidiness. A wrong sensitivity label is a live governance
  defect. Somebody will fix it. If the reviewed path cannot, they will open a SQL editor — which is
  the precise behaviour this entire project exists to remove. An exception that keeps the
  correction inside the governance model is worth more than a purity rule that pushes it outside.

The exception is scoped narrowly on purpose: **one statement, one merge, one converging set of
labels on one object.** The description stays create-only, and that remaining asymmetry is
defensible rather than accidental — tags merge key by key, while a comment replaces wholesale, so
re-applying a description would silently overwrite whatever a human may have written on the catalog
since. Convergence is safe where the write is a merge on a key this platform owns, and unsafe where
it is a replace on a field anybody can edit.

### Revision 4 widened the exception from one field to three — and two got in on the weaker argument

Through revision 3, `business_area` and `environment` were required on every request, read by a
reviewer, recorded in the request file and the audit log, and **written nowhere in Unity Catalog at
all**. Two required fields cost a requester real attention and bought them nothing visible.
Revision 4 put both on the catalog as tags, alongside `sensitivity`, in the same single tag-merge
statement.

This is recorded as a widening of an existing exception rather than as three exceptions, because
mechanically it is one: one statement, one merge, one object. But "three now instead of one" is not
an argument, and the two reasons above do not transfer equally — which is the part worth being
honest about:

- **Recoverability transfers identically to all three, and gets stronger.** All three fields ride
  the same tag-merge statement, so all three share exactly the same failure mode and exactly the
  same fix. It gets stronger because the statement is now unconditional: through rev 3, a request
  declaring no sensitivity had no label statement at all and therefore no failed-label case;
  every request now has one.
- **The uncorrectable-classification argument holds for `sensitivity` and holds only weakly for the
  other two.** A catalog filed under the wrong business area is untidy, not unsafe, and nobody
  bypasses review over it. For those two fields the exception rests on recoverability and on
  mechanism-uniformity — they share a statement with a field that *must* converge, and splitting the
  merge so one key converges and two do not would be a bespoke rule inside a single `SET TAGS`
  call, more machinery for less clarity.

**So two of the current three got in on the weaker argument.** That is stated rather than smoothed
over for a specific future reader: whoever is deciding whether a *fourth* field may join this
exception should know that the bar it would have to clear is "recoverability and mechanism
uniformity", not "it is a classification like sensitivity is", because only one of the three
current members actually qualifies on the latter.

One consequence rev 3 never had to face: `environment` is required, so it always has a value and
that value can legitimately change — a catalog genuinely gets re-tiered from bronze to silver.
Converging it is therefore not merely tolerable but useful, and it stays inside the governance
model, because the way it changes is still "edit the request file, have it reviewed, merge it".
**The exception widens what can move on re-run; it does not widen who may move it.**

### Tags, not properties — and why `region` was excluded from the same widening

The mechanical precedent argued for properties: the applier sends `certification` — the very same
controlled vocabulary `environment` reuses — to `TBLPROPERTIES` at table level. Following it would
have been the consistent-looking move. It was examined and rejected, because it reads the applier's
own rule too broadly.

The rule the applier's docstring actually states is about **searchability**, and the properties
bucket in practice holds two kinds of thing: pointers and references that must be re-resolved
elsewhere to mean anything (`business_application_id` resolves against the owner registry), and
declared commitments nobody searches by (retention, refresh cadence, SLA). `business_area` and
`environment` are neither. They are plain classification values, complete in themselves, with
nothing to re-resolve and every reason to be searched by. Structurally they are `sensitivity` —
which has always been a tag. Unity Catalog's own affordances point the same way: tags are the
searchable, filterable, ABAC-eligible mechanism, and being findable by business area or medallion
tier is the entire reason to record either one.

Two supporting facts, neither load-bearing alone: nothing in this codebase writes catalog
*properties*, so there was no existing catalog-granularity properties path to stay consistent with;
and `set_catalog_tags` already existed, so this widened a step known to work rather than adding one
that was not. Each field's own name is the tag key, verbatim and unprefixed, so the same concept is
searchable under the same key at every granularity.

**`region` was considered for the same promotion and deliberately left behind.** It stays recorded
in the request file and in the audit trail, and stays off the catalog. The reason is not oversight
and not inconsistency: a tag is a searchable, filterable fact about the object, so a catalog
carrying `region: eu-west-1` invites somebody to filter on it and conclude the platform places
catalogs by region. **It does not, and in this workspace it cannot** — Free Edition is a
single-region, managed-storage environment, and real regional provisioning needs storage
credentials, external locations and a metastore-per-region topology that does not exist here. A
declared-but-inert field is already a mild hazard; a declared-but-inert field made *searchable* is a
claim. Region stays off the catalog until something actually enacts it.

### A required default schema, which turned one statement into a plan

`default_schema` is required, not optional. The reasoning is that the thing a requesting team
actually needs is somewhere to put a table, and handing them an empty namespace means the next
thing they do is ask a human for a second favour — which is the manual, out-of-band step this
feature exists to remove. Making it optional would have made the common case the one that does not
work.

The consequence was larger than the field, and is the reason this sub-decision is recorded at all:
**it turned provisioning from one statement into an ordered plan, and pulled partial-failure
semantics in with it.** Each step is attempted in order, each succeeds or fails on its own, and a
failure part-way through neither aborts the remainder nor rolls back what already landed. That is
not a mechanism invented here — it is exactly what the applier already does when it plans seventeen
writes for a contract, so the outcome vocabulary is the applier's, unchanged: success, partial
failure, failure, refused. Reusing that machinery rather than writing a bespoke two-step sequencer
was the whole point, and it is also what made SC-004-06 (catalog created, schema not) a case with a
defined answer rather than an undefined one.

From revision 4 the plan is **always exactly three statements**, because the labelling step stopped
being conditional on a sensitivity having been declared. Every valid request therefore has the same
plan shape — one fewer branch to reason about, not one more.

### Three narrow one-statement client methods, not one compound `create_catalog`

`create_catalog`, `create_schema` and `set_catalog_tags` are three separate methods on the
`UCClient` protocol, implemented on both the real and the fake side. The rejected alternative was a
single `create_catalog` taking the schema and the labels and emitting everything at once — fewer
methods, one call site, and superficially the tidier seam.

It lost on two grounds:

1. **The seam's existing contract is one method, one statement, one returned string.** A compound
   method would have to return several statements or a joined blob, which breaks the postcondition
   every other write method honours — and with it the plan/execute equivalence that rests on that
   postcondition. That equivalence is not decorative: it is what lets the planned statements be
   printed in a change request and *trusted* to be what actually runs. Breaking it here to save two
   method definitions would have traded a load-bearing property for a cosmetic one.
2. **Creating a schema is a capability worth having on its own.** Schema provisioning is already
   named as a follow-on, and a schema-creating method that existed only inside catalog creation
   would have to be prised back out when that arrives.

The compact statement of it: **three narrow methods compose into one plan; one compound method does
not decompose.** Each of the three follows the existing write-method shape exactly — keyword-only
`dry_run` defaulting to false, returns the exact statement string either way, builds that statement
once from a single code path so a planned statement and an executed one cannot diverge, idempotent
in effect.

Writing a label on a catalog is treated as a genuinely new capability rather than a variant of the
table-tag method, because assuming otherwise would be wrong at the SQL level and wrong at the
privilege level.

### One audit record, two widened field meanings, one additive optional field

Every outcome — success, no-op, refusal, failure — publishes one record, in the existing record
shape, through the existing append-only log. The existing record carries a dataset's three-part
identity and a contract version, neither of which a catalog request has in the same sense. Rather
than introduce a second record type, the catalog's name goes in the identity field, the
request-file schema version goes in the contract-version field, and **both fields' documented
meanings are widened to say so.**

The reasoning is that one audit trail is worth more than two tidier ones. Every consumer of that
log reads it as "things that were changed, by whom, with what outcome", which a catalog creation
genuinely is; splitting the trail by object type would mean anyone auditing the platform has to
know to look in two places.

**The cost is named rather than hidden: widening a shared field's meaning to fit a second use is
how shared shapes rot.** The widening is therefore a deliberate, documented act, and the moment a
*third* kind of thing wants into this log is the moment to stop widening and split the type
properly. That trigger is written down here so the next person meets a decision instead of a
precedent.

Revision 3 then added one thing revision 2 had said it would not: **an additive optional field for
the requester.** Folding the requester's name into the record's free-text summary was considered
and rejected on the record's own design argument — ADR-009 insisted the approving human and the
machine identity that performed the write be two separate fields precisely because they are two
separate facts. A catalog request has a third such fact (*who asked*), and burying it in prose
would make it unqueryable while every other party to the same event stays structured. The
compatibility claim is narrower than rev 2's but still holds: existing log lines parse unchanged
because the field is optional, and nothing that reads the log today looks for it. This is recorded
as an **amendment** to rev 2 rather than presented as consistent with it, because it is not quite —
rev 2 said the field set would not change, and it changed by one field, for a reason rev 2's own
reasoning produced.

### Why this feature stops where it does: the live path split out

Creating a catalog needs a metastore-level privilege that no identity in this workspace's
automation held. ADR-009 granted `ucmeta-ci-apply` the right to use the catalog, use two schemas,
own three specific tables and use a warehouse — and stated plainly that *"it is granted nothing
else. No create or drop anywhere, no administrative standing at account, workspace or metastore
level."* Creating a catalog needs exactly the standing that sentence rules out.

Closing that gap meant either widening `ucmeta-ci-apply` or introducing a second, differently-scoped
identity. **F-PLATFORM-004 makes neither choice and builds neither path**, and that is a decision
rather than an omission: it is a security argument with its own case to make, not a checkbox to tick
on the way past. Adding a metastore-level creation privilege to the applier's identity would widen a
leaked credential's blast radius from "vandalise three tables' metadata" to "create namespaces in
the metastore" — and would falsify a sentence ADR-009 had already published. That deserved its own
dated approval, following the same precedent ADR-009 itself set when it separated "give CI an
identity" from "take the human's write access away" and gated them on separate approvals.

So this feature has **no live path at all** — not a disabled one, not an optional one, not one flag
away. It runs against the in-repository fake, which is a deliverable here rather than a fallback:
the feature is done when a request file landing on `main` causes a catalog to be created in the
fake and a record to be published, with no credentials anywhere. That is also what keeps
F-PLATFORM-001's fork-safety guarantee intact — a reviewer with no Databricks account can run this
pipeline, watch the mechanism work, and get a green job.

## What is true today, and what this feature's own scope was

This section exists because the brief F-PLATFORM-004 wrote for this ADR contained a sentence that
was true when it was written and is not true now, and carrying it forward unexamined would have
made this document wrong on its first reading.

That brief asked this ADR to record *"the honest note that a pipeline which has never created a
real catalog is a mechanism demonstration, not a provisioning system, and should be described as
the former wherever it is shown."* At the time — F-PLATFORM-004 revision 3, before F-PLATFORM-005
existed — that was exactly right, and the discipline behind it is worth keeping: a mechanism that
has only ever run against an in-memory fake should be described as a mechanism, because the gap
between "the plan executes" and "a real metastore accepted these statements" is precisely where
this kind of prototype usually overclaims.

**The premise has since changed.** The pipeline described in this ADR has created real catalogs, as
of 2026-09-20. Two exist in the live workspace and are kept permanently as standing evidence:

- **`data_platform_demo`** — the first real catalog this platform ever created, from
  `catalog-requests/data-platform-demo-bronze.yaml`, containing schema `demo`. The release log
  carries it twice, seconds apart, which is the live idempotency proof: two runs, both
  `deployment_status: success`, both reporting `create catalog`, `create schema` and
  `set catalog tags` as `OK`, with no duplicate-object error on the second.
- **`data_platform_demo_silver`** — from `catalog-requests/data-platform-demo-silver.yaml`, same
  three-statement plan, same clean result.

Three things follow, and keeping them distinct is the point of this section:

1. **F-PLATFORM-004's own scope really was fake-only, by design, and that is not retroactively
   embarrassing.** The rule was stated as a rule precisely so the build could not quietly slide
   into a grant negotiation halfway through. It held.
2. **The live path is a different decision, recorded elsewhere.** How an identity came to hold
   `CREATE_CATALOG` — and specifically why `ucmeta-ci-apply` was *not* widened to hold it — is
   ADR-011's subject and F-PLATFORM-005's feature. It is deliberately not re-argued here; a reader
   who wants that half of the story should go to
   [ADR-011](ADR-011-a-second-machine-identity-so-the-first-one-did-not-have-to-grow.md), which
   also records what the live workspace actually did.
3. **The description discipline still applies, just with the qualifier moved.** The right sentence
   is no longer "this has never created a real catalog". It is: *this feature built the mechanism
   and proved it against the fake; the live path that proved it against a real metastore is
   F-PLATFORM-005's, and it worked.* What must still not be claimed is that any of this is a
   production provisioning system — there is no deletion, no lifecycle, no quota, no naming policy,
   no grant to the requesting team, and no region enactment.

One thing the live runs settled that the fake never could: the ordered three-step plan has a **real
dependency chain**, not merely an asserted one. When the refused run executed as an identity
without `CREATE_CATALOG`, the schema and tag writes failed behind it with
`NO_SUCH_CATALOG_EXCEPTION` — the catalog was never created, so nothing downstream of it could
succeed. Until a real metastore enforced that ordering, it had only ever been proven by unit tests
against a fake with no way to enforce it.

## Consequences

- **The platform can now bring an object into existence, not just describe one.** The hole ADR-007
  left — provisioning is somebody else's flow — is partially closed by the platform owning a real
  provisioning path of its own, on the same file-review-merge shape as everything else.
- **"They ask hector and he types `CREATE CATALOG`" is replaced by an artifact.** Every catalog this
  mechanism creates has a merged file naming what was asked for, who asked, who approved it, and a
  log line recording what happened. That is the same standard ADR-009 imposed on metadata writes,
  applied one level up.
- **Reverting a catalog request does not remove the catalog, and this breaks parity with apply's
  reversibility claim.** Named here rather than buried: apply is reversible, provisioning is not.
  The asymmetry is the price of refusing a delete path, and it is the single most important thing a
  reader should take away about what this verb is not.
- **The release log now carries two kinds of event behind one record shape.** One audit trail, at
  the cost of two field meanings that are broader than they were. The documented trigger for
  stopping — a third kind of thing wanting in — is recorded above so the next widening is a decision
  rather than a habit.
- **The contract schema's controlled vocabularies are now load-bearing for two file formats.** The
  request reuses `Sensitivity` and `CertificationTier` rather than forking parallel enumerations, so
  a "confidential" catalog and a "confidential" column are confidential in the same sense. The cost
  is that changing an allowed value now ripples into catalog requests too — a reason to be careful
  with those lists, not a reason to fork them.
- **Catalog requests route to the slow path explicitly, not by accident.** Paths matching no
  declared class already fell through to the slow path, which happened to be the right answer; the
  folder is declared anyway, on blast-radius grounds — a description edit affects one dataset, while
  creating a top-level catalog creates a namespace every team can see and that nothing in this
  feature can remove. "Correct by luck" is not a property this repository's routing module claims
  anywhere else.
- **The fake gained a real notion of catalogs and schemas.** It was previously a flat dictionary of
  tables keyed by full name. It now models created catalogs, the schemas within them and
  catalog-level tags, with accessors for tests to read each back — without which "the catalog and
  its schema were created" would have been unassertable and this feature's headline scenario would
  have had nothing to prove itself with.
- **`environment` is a name this project will have to live with.** It means the medallion tier and
  has nothing to do with dev/staging/prod. Reusing an established controlled list was judged worth
  more than coining a more precise but novel field name, and the ambiguity is documented loudly — in
  the glossary and in the template's own comments — rather than quietly tolerated. If it does get
  misread in practice, renaming it is a slow-path schema change with a migration for every request
  file already written: cheap now, less cheap later.

## Alternatives considered

- **(a) A ticket in a tracker.** Rejected. The request and the thing that acts on it live in two
  systems that do not know about each other, so the link between approval and effect is somebody's
  memory. It also reproduces the queue ADR-006 identifies as what killed the tagging campaigns this
  project exists to replace. See Context for the full case.
- **(b) A web form that provisions directly.** Rejected. New infrastructure to build, host,
  authenticate and run; the request stops being a reviewable artifact; and it would contradict
  ADR-003's identical position for contracts inside the same repository.
- **(c) Granting requesting teams `CREATE CATALOG` directly.** Rejected, and the strongest of the
  rejected options on responsiveness grounds — it takes the platform off the critical path
  entirely. It removes the review rather than relocating it: catalogs get created with no artifact,
  no approval and no record, which is today's failure mode redistributed to more people. It would
  also hand a metastore-level privilege to human identities, the opposite direction from ADR-009.
- **(d) A file in `catalog-requests/`, reviewed and merged.** Chosen. See Decision.
- **(e) Refuse, rather than no-op, when the catalog already exists.** Rejected on the re-run and
  revert-and-re-merge cases. See Decision.
- **(f) One compound `create_catalog` method doing all three statements.** Rejected: it would break
  the seam's one-method-one-statement postcondition and the plan/execute equivalence that rests on
  it, and would bury a reusable schema-creation capability inside catalog creation.
- **(g) Write `business_area` and `environment` as catalog properties, following the table-level
  `TBLPROPERTIES` precedent for `certification`.** Rejected: that precedent reads the applier's rule
  too broadly. Properties hold pointers needing re-resolution and unsearched declared commitments;
  these two are plain classification values that exist to be searched by, which is what tags are
  for.
- **(h) A second audit-record type for provisioning events.** Rejected in favour of widening two
  field meanings on the existing record, so the platform has one audit trail rather than two tidier
  ones. The condition under which this alternative becomes the right answer — a third event kind —
  is named in the Decision rather than left to be rediscovered.
- **(i) Build the live path here, by granting the existing CI identity `CREATE_CATALOG`.** Rejected
  and deferred whole to F-PLATFORM-005, which chose a second identity instead. See ADR-011 — not
  re-argued here.
- **(j) A delete or full lifecycle path, for reversibility parity with apply.** Rejected. It would
  require `DROP` standing at metastore level, turning a leaked credential from "can create
  namespaces" into "can destroy namespaces and everything in them", and would make a catastrophic
  operation fire from an ordinary revert. A separate feature with a separate and much more careful
  security argument.

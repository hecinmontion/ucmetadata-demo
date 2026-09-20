---
id: F-PLATFORM-004
title: Catalog provisioning via catalog-requests — a request-file-triggered pipeline that creates a new Unity Catalog catalog
status: draft
owner: hector
approvers: []
created: 2026-09-19
last-updated: 2026-09-20
---

# Feature: Catalog provisioning via catalog-requests — a request-file-triggered pipeline that creates a new Unity Catalog catalog

> *Scope of this document.* Internal planning artifact for the `uc-metadata-platform`
> prototype, same convention as F-PLATFORM-001 through F-PLATFORM-003: it plans a build that
> happens in that repository, and nothing from this folder is shipped into it. Unlike
> F-PLATFORM-003, nothing here had been executed when this was written. Every statement below is a
> proposal about what the feature should do, written before any of it existed — no scenario in this
> document is a report of something that already ran, and none should be rewritten into that voice
> until it actually has.
>
> *One correction to that framing, added at revision 4.* The build has since happened, and
> F-PLATFORM-005 provisioned the first real catalog on 2026-09-20. Revision 4 is therefore the
> first change to this document that comes from *observing the built system* rather than from
> reasoning about a proposal: the trigger was noticing that a provisioned catalog carried only a
> sensitivity tag, with two other required, reviewed fields written nowhere in Unity Catalog at
> all. The proposal voice below is left intact rather than rewritten — the scenarios still say what
> the feature should do, and the record of what actually ran lives in F-PLATFORM-005.

## Business Context

Everything the platform does today happens *inside* containers somebody else already made. A
contract names a dataset by its three-part `catalog.schema.table` name, harvest reads that table,
apply writes comments, properties and tags onto it, and coverage counts how many such tables are
described. Every one of those operations presupposes that the catalog and the schema exist and
that a human created them by hand, out of band, before the platform was ever pointed at them. The
prototype's whole surface is metadata *about* objects, and it has no way to bring an object into
existence.

That is a visible hole in the story the platform tells. F-PLATFORM-001's forcing function rests
on the claim that "a new dataset is not provisioned without a valid contract" — but provisioning
itself is described as somebody else's flow, a centrally-owned Terraform pipeline the prototype
explicitly does not build or simulate. A reviewer is entitled to ask the obvious next question: if
a business team needs a new top-level catalog for their area, what do they do? Today the honest
answer is "they ask hector, and he types `CREATE CATALOG` into a SQL editor". That is the same
untracked, unreviewed, unrecorded act this project spent three features arguing against everywhere
else.

This feature closes that hole in the smallest way that is still real. A business team that wants a
catalog writes a short YAML file describing what they need and drops it into a new top-level
`catalog-requests/` folder. When that file lands on the main branch, a pipeline picks it up,
validates it, creates the catalog named in it along with a first schema inside it so the team can
actually use it, and appends a record to the same append-only audit trail every apply already
writes to. The request file is the request, the review of that file is
the approval, and the merge is the authorisation — exactly the shape the rest of the repository
already uses for metadata, applied for the first time to something other than metadata.

*What "minimal" means here, stated up front because it bounds everything below.* The target of
this spec is a demo-scoped version, not a production provisioning workflow. Concretely: the
pipeline runs against the in-repository fake catalogue by default, the way `validate.yml` already
does, and proves the mechanism end to end — a request file appears, the pipeline detects exactly
which files changed, the named catalog and its schema get created in the fake in-memory catalogue,
a release record is published, and the job's output says plainly which path it took. The live path — the
same command writing a real catalog into the real Free Edition workspace — is *named and designed
here and built elsewhere*: as of revision 2 it belongs to a future F-PLATFORM-005, not to this
feature. The reason is recorded in Rules & Constraints and is concrete: creating a catalog needs a
metastore-level privilege that F-PLATFORM-003's service principal was deliberately not granted,
and granting it is a security decision with its own argument to make, not a checkbox this feature
ticks on the way past. F-PLATFORM-004 therefore has no live path at all — not a disabled one, not
an optional one, not one flag away.

*On difficulty, since that is the question this spec was commissioned to answer.* Almost all of
this is composition of patterns the repository already has working. The workflow is
`apply.yml`'s changed-path diff with one glob changed. The CLI verb is another `argparse`
subparser wired the way the other five are. The module is `apply.py`'s validate-plan-execute-log
discipline applied to three statements instead of seventeen. The genuinely new capability is three
new methods on the `UCClient` seam — creating a catalog, creating a schema inside it, and writing
tags at catalog granularity — each implemented on both implementations, and each a short SQL
builder on the real side plus a little in-memory state on the fake side. Revision 3 raised that
count from one method to three, and the honest consequence is that this is no longer a
one-statement feature: it plans and executes an ordered list of writes, which means it inherits
the applier's partial-failure machinery rather than sidestepping it. Revision 4 changes no
method count and no mechanism — it only widens what the third statement carries, from one
classification field to three — but it does make that statement unconditional, so every valid
request now plans exactly three writes rather than two or three depending on what it declared.
That removes a branch rather than adding one. The realistic cost is still
measured in hours rather than days, and the expensive part of it is still the tests and the
honesty about what it does not do. The part that is genuinely hard is not in this scope at all: it
is the live grant, it is hard for organisational reasons rather than technical ones, and it is
F-PLATFORM-005's problem.

## Stakeholders
- Owner: hector
- Approvers: hector (self-approving; this is a solo interview submission)
- Last reviewed: 2026-09-20

## Revision History
| Rev | Date         | Author | Change |
|-----|--------------|--------|--------|
| 1   | 2026-09-19   | hector | Initial draft. Proposes a request-file-triggered catalog-provisioning path: a new top-level `catalog-requests/` folder, one YAML file per requested catalog, a push-triggered workflow filtered to that folder, a new `ucmeta provision-catalog` verb, and one new `create_catalog` method on the `UCClient` seam. Scopes the build explicitly to a fake-client-only minimal demo, with the live path and its metastore-level grant named as a deferred follow-on rather than assumed. Records the corrected field spelling (`business_area`, not `bussines_area`) and the decision to carry `catalog_name` as an explicit authored field rather than deriving it from the business-application id or the business area. Five scenarios, four open questions. |
| 2   | 2026-09-19   | hector | All four open questions resolved; zero remain. Trigger breadth stays as drafted — any push to `main` touching a request file, added or modified alike — recorded explicitly as a deliberate placeholder ("any push for now"), not a settled final position, so a later narrowing to added-only is a revisit rather than a reversal. `region` confirmed optional. The provisioning audit record reuses the existing `ReleaseRecord` shape with two field meanings widened, rather than introducing a second record type — one audit trail, not two tidier ones. **The live path is now out of scope entirely, not merely deferred**: the metastore-level `CREATE CATALOG` grant, the identity choice behind it, and the first real catalog provisioned against the workspace all move to a future, not-yet-drafted F-PLATFORM-005, on the same grounds F-PLATFORM-003 separated its own layers — approving a demo mechanism and approving a privilege widening are different decisions and must not ride on one approval. F-PLATFORM-004's scope is therefore unambiguously fake-client-only. SC-004-05 kept in place but re-framed as inherited-by-F-PLATFORM-005 rather than as behaviour this feature builds; every "recommended"/"if reused" hedge in Rules & Constraints, Out of Scope, Dependencies and the build-verdict tables tightened to state the decision. Frontmatter stays `draft`: resolving open questions is part of hector's review, not approval to build. |
| 3   | 2026-09-20   | hector | **Request-file shape finalised at nine fields; four added.** `default_schema` (required) — a catalog with no schemas in it is not demoable, so provisioning now creates a schema alongside the catalog, which turns the provisioning write from one statement into an ordered list and pulls the applier's partial-failure machinery into this feature for the first time (new SC-004-06 covers the half-provisioned outcome that makes possible). `sensitivity` (optional, reusing the existing `Sensitivity` enum) — a catalog-level classification, needing a tag write at catalog granularity that nothing in the codebase does today. `requested_by` (required) — the request's author, a genuinely third party alongside the approver and the machine that performs the write; recorded as its own additive optional field on the audit record rather than buried in free text, which amends rev 2's "field set unchanged" in the one direction rev 2's own reasoning requires (see Rules & Constraints). `environment` (required, reusing `CertificationTier`) — the medallion tier, *not* a deployment environment, a naming tension recorded in the Glossary rather than left for a future reader to trip over. Consequently, and settled here rather than left open: the seam gains **three** new `UCClient` methods rather than one — `create_catalog`, `create_schema` and a catalog-granularity tag write — as three separate one-statement methods rather than one compound method, because the seam's one-method-one-statement contract is what makes a printed plan trustworthy and because schema creation is a capability worth having on its own; the build-verdict table now carries protocol/real/fake rows covering all three, plus a row for the ordered write plan itself. One further decision this forced: the sensitivity label is the **single named exception** to create-only — it is written on every run and converges on the currently-declared value, because a classification that cannot be corrected through the reviewed path gets corrected through an unreviewed one, and because labelling at creation time only would leave SC-004-06's failed-label case unrecoverable. Out of Scope's "the catalog arrives empty" bullet narrowed rather than deleted (one schema, still no second schema, no table, no grant); a concrete nine-field example added under Data and named as what `_template.yaml` ships. Frontmatter still `draft`. |
| 4   | 2026-09-20   | hector | **`business_area` and `environment` are now written as catalog tags, alongside `sensitivity`. The tag write becomes unconditional: every valid request plans exactly three statements, not two or three.** The trigger was an observation from the first live catalog (F-PLATFORM-005): after provisioning, the only thing visible anywhere in Databricks was the sensitivity tag. `business_area` and `environment` are required on every request, a reviewer approves them, and they were then recorded nowhere but the request file and the audit log — enacted as nothing, which made them a slightly more expensive version of `region`. **Why not properties.** The obvious mechanical precedent pointed the other way: `apply.py` sends `certification` — the same `CertificationTier` vocabulary `environment` reuses — to `TBLPROPERTIES`, so the table-level analogue of `environment` is a property, not a tag. That precedent was examined and rejected, because the actual rule the properties bucket encodes is narrower than "declared facts go to properties". `apply.py`'s own docstring splits on *searchability*: things a consumer filters or searches by are tags; structured facts with no natural tag home — and, crucially, the owner *pointer* `business_application_id`, which is a reference that has to be re-resolved against the registry to mean anything — are properties. `business_area` and `environment` are plain classification values with no pointer semantics and nothing to re-resolve; structurally they are `sensitivity`, which already gets a tag. **Why tags are also the right answer on Unity Catalog's own terms.** Tags are the searchable, filterable, ABAC-eligible mechanism in UC; properties are not surfaced for discovery in the same way. Recording a business area and a medallion tier exists precisely so somebody can later find catalogs by them, so writing them where they cannot be found would defeat the point of collecting them. The catalog-level precedent is also thinner than it looks — nothing in the codebase writes catalog *properties* at all, so there was no existing catalog-granularity properties path to be consistent with; `set_catalog_tags` already exists and is already live-verified, so this widens an existing step rather than adding a new one or a new seam method. **Why `region` is excluded.** Deliberately, not by omission: tagging a region would advertise a placement fact the platform does not enact and cannot honour — a single-region, managed-storage Free Edition workspace with no external locations — and a searchable `region` tag invites somebody to filter on it and conclude the platform is region-aware. `region` keeps its "recorded, not enacted" treatment unchanged, and the Data table now says so in the same words the other two rows have stopped using. **Consequence for create-only.** The single named exception becomes three fields converging through one tag-merge write. The recoverability half of rev 3's argument transfers identically to all three; the "an uncorrectable classification gets corrected through an unreviewed path" half is strongest for `sensitivity` and weaker for the other two, and that asymmetry is stated in Rules & Constraints rather than smoothed over. No new client method, no new statement, no change to the plan's order, no change to the audit record. Frontmatter stays `draft`. |

## Users & Roles

- *Requester — the business stakeholder who authors the request (the new actor)* — the reason this
  feature exists. Writes one short YAML file naming the catalog they want, the business application
  it belongs to, the schema they want inside it and the tier it serves, opens a change request
  containing that file, and gets a usable catalog as a result of it being merged. They do not run
  anything, hold no workspace credentials, and never touch a SQL editor. The file is their whole
  interface, and they name themselves in it — the request records who asked, which is not
  necessarily who merges it.
- *Reviewer of a catalog request* — reads the request file and approves or rejects it. This is the
  only human judgment in the loop, and it is deliberately the same judgment the rest of the
  repository already uses: a change request, reviewed by a named human, merged. What they are
  approving is materially heavier than a description edit — a new top-level namespace in the
  metastore — which is why the routing decision in Rules & Constraints puts it on the slow path
  rather than the fast one. They are frequently not the requester, which is exactly why the request
  records both.
- *Platform engineer (hector)* — owns the request file's shape, the validation, the pipeline and
  the new client methods. Owns none of the request content. He is also, today, the only identity in
  this workspace holding the privilege that creates catalogs at all — which is why a live path
  exists nowhere in this feature and is F-PLATFORM-005's subject.
- *Continuous integration (`ucmeta-ci-apply`)* — the machine identity F-PLATFORM-003 created. It
  runs this pipeline, and under this feature's scope it runs it against the fake catalogue only. It
  was deliberately granted table-level privileges and a warehouse, and creating a catalog is not
  among them. Whether it should be granted that privilege, or whether catalog provisioning should
  run as a different and more-privileged identity, is a question this feature raises, refuses to
  answer in passing, and hands to F-PLATFORM-005.
- *Interview panel* — must be able to clone the repository, add a file to `catalog-requests/`, run
  the pipeline and see a catalog and its schema get created, all with no Databricks account and no secrets
  configured. This is F-PLATFORM-001's constraint carried forward unchanged, and in this feature it
  is not merely preserved — it is the actual delivery target.

## Behaviour

A business team that needs a new catalog writes one file. The file says what the catalog should be
called, which business application it belongs to, which business area it serves, what it is for in
a sentence, which schema should exist inside it on day one, which tier of the medallion
architecture it serves, and who is asking. Two things are optional: the region it relates to, and
how sensitive its contents are expected to be. It goes in a new top-level folder that exists for
exactly this purpose and holds nothing else — one file per requested catalog, named after the
catalog it requests. The folder is the queue, and its contents are the record of every catalog the
platform was ever asked to create.

The team opens a change request containing that file. A reviewer reads nine short fields and
decides. Nothing has happened to the workspace at this point, and nothing can: the request file is
inert on its own, and the only thing that acts on it is the pipeline that runs after a merge.

When the change request merges, the pipeline wakes up. It looks at exactly which files the merge
moved, keeps only the ones under the request folder, ignores the folder's own template, and
processes each remaining file in turn. For each one it validates the request before doing anything
at all — the required fields are present, the catalog name is a legal single-part identifier and
not something that would need quoting or escaping to be safe, the business-application identifier
resolves against the same owner registry every contract already resolves against. If the request
does not pass, the pipeline refuses it, writes nothing, records the refusal in the audit trail
naming each specific problem, and fails loudly. A malformed request produces a failed job and an
audit record, never a half-created catalog.

If the request does pass, the pipeline provisions what was asked for. *This is more than one
write, and revision 3 is where that became true.* An empty catalog is not something anybody can
use — a team handed a namespace with nothing in it still cannot put a table anywhere — so
provisioning creates the catalog, then creates the schema the request named inside it, and then
labels the catalog with the classification values the request carries. *Revision 4 widened that
last step and made it unconditional.* The labels are the business area the catalog serves, the
medallion tier it serves, and — when the request declared one — how sensitive its contents are
expected to be. Because two of those three are required on every request, there is always
something to label, so the labelling step is always in the plan: every valid request is exactly
three statements, not two or three depending on what it declared. They are planned as an ordered
list before any of them runs, executed in order, each succeeding
or failing on its own. That is not a new mechanism: it is exactly how applying a contract already
works, where seventeen writes are planned, attempted in order, and reported individually. The
consequence worth stating plainly is that this feature can now end in a partial state — a catalog
that exists whose schema does not — and it reports that honestly rather than rounding it to
success or failure. See SC-004-06.

Every one of those statements is written so that re-running it is harmless. Creating a catalog
that already exists is not an error and is not treated as one: it is left exactly as it is and the
run reports that nothing changed. The same holds for the schema and for the labels. That is
deliberate and matches every other write in this system — applying an unchanged contract twice
already changes nothing the second time, and a provisioning step that failed on re-run would break
the first time somebody re-runs a workflow, reverts and re-merges, or lands two requests in one
push.

Whatever happens, the attempt is recorded, and it is recorded in the same place and in the same
shape as everything else the platform writes. The existing append-only audit trail that holds
every metadata apply gets one more line: which catalog, who asked for it, who approved it, when,
which of the writes landed, and whether the run created something, found it already there, was
refused, partly succeeded or failed. *Who asked* and *who approved* are recorded as two separate
facts, because in a catalog request they are routinely two different people — the same discipline
F-PLATFORM-003 established when it insisted the approving human and the machine that performed the
write be recorded separately, extended by one party. There is no outcome that leaves no trace,
which is the same rule apply already honours, and there is no second trail to go looking in — a
deliberate decision, recorded in Rules & Constraints, that one audit trail is worth more than two
tidier ones.

*Where this runs, and what it writes to.* By default — and, in this feature's scope, always in
automation — the pipeline runs against the in-repository fake catalogue. The request is parsed for
real, the validation runs for real, every statement in the plan is built for real and is exactly
what a live run would one day execute, and the catalog and its schema appear in an in-memory
catalogue that the run can then be asked about. What does not happen, anywhere in this feature, is
a write to a real metastore. A reviewer with no Databricks account gets the entire mechanism,
end to end, and a job whose output says in as many words that it ran against the fake because no
automation credential was configured. That is the same distinction `apply.yml` already draws
between its two mutually exclusive paths, and it is drawn the same way here so the two cannot be
confused.

*What the live path would be, and why it is a different feature.* Exactly the same command with
one flag, run by an identity that holds the privilege to create a catalog at the metastore level.
Nobody holds that privilege today except hector's own account, because F-PLATFORM-003's service
principal was granted table-level privileges and a warehouse, and nothing else — on purpose, since
narrowness was that feature's entire deliverable. Making the live path work therefore means either
granting a metastore-level creation privilege to an identity that currently cannot create anything
anywhere, or introducing a second, more-privileged identity used only for provisioning. Both are
real options and both have consequences worth arguing about properly. As of revision 2 that
argument has an owner and a home: it is F-PLATFORM-005 (drafted 2026-09-20), and it takes the grant
decision, the identity choice and the first real catalog with it. The separation is the same one
F-PLATFORM-003 made between its own layers, for the same reason — approving a demo mechanism and
approving a privilege widening are different decisions, and a single approval that silently
carried both would be exactly the kind of thing this project keeps arguing against.

## Glossary

- *Catalog*: the top-level container in Unity Catalog's three-level namespace
  (`catalog.schema.table`). Everything the platform has managed until now lives inside one; this
  feature is the first time the platform makes one.
- *Catalog request*: one YAML file in the request folder describing a catalog somebody wants.
  It is a request, not a declaration of state — it names what should be created, and the file
  continues to exist afterwards as the record of who asked and why.
- *Request folder*: the new top-level `catalog-requests/` directory. Holds one request file per
  requested catalog, plus a template that is not a request. Nothing else.
- *Provision*: to bring a catalog into existence in the metastore *and to leave it usable* —
  which, from revision 3, means creating the catalog and a first schema inside it, and, from
  revision 4, always labelling the catalog with the classification values the request declared.
  Distinct from *apply*, which writes metadata onto objects that already exist — this is the
  distinction the whole feature turns on.
- *Default schema*: the schema created alongside the catalog so that the catalog is usable the
  moment it exists. Required in every request, because a catalog containing no schemas is a
  namespace nobody can put anything into, and handing a team one of those is not provisioning.
- *Idempotent creation*: creating a catalog, or a schema, in a way that succeeds and changes
  nothing when the thing is already there. The property that lets the same merge be processed
  twice safely, and it must hold for every statement in the plan, not just the first.
- *Requester*: the person who authored the request file and is named in it. Distinct from the
  approver (whoever merges the change request) and from the identity that performs the writes.
  Three different facts about one provisioning event, recorded separately for the same reason
  F-PLATFORM-003 refused to collapse the approving human and the machine identity into one field.
- *Environment (as the request file uses the word)*: **the medallion tier — bronze, silver or
  gold — and not a deployment environment.** The field is called `environment`, it reuses the
  existing certification-tier vocabulary rather than inventing a parallel one, and it has nothing
  to do with dev/staging/prod. The tension between the field's name and its meaning is deliberate
  and is recorded here rather than left as a trap: reusing an established controlled list was
  judged worth more than a more precise but novel field name. A reader who expects
  `environment: prod` to mean something about deployment is the exact reader this entry exists
  for.
- *Catalog-level classification*: the set of labels applied to the catalog itself rather than to a
  table or a column. As of revision 4 there are three of them — the business area the catalog
  serves, the medallion tier it serves, and, when declared, how sensitive its contents are
  expected to be. Two of the three draw on the same controlled vocabularies the contract schema
  already uses for datasets and columns; the business area is free text. They are written at a
  granularity nothing in the codebase writes today, and they are written as tags rather than as
  properties because tags are what a consumer searches and filters by — see Rules & Constraints
  for why the table-level precedent that would have sent the medallion tier to properties was
  examined and rejected. *On naming*: each field's own name is used verbatim as its tag key, so
  the catalog carries `business_area`, `environment` and `sensitivity` — the same
  field-name-is-tag-key convention the contract applier already uses when it writes `sensitivity`
  and `pii` onto tables, chosen so that the same concept is searchable under the same key whether
  it was declared on a catalog or on a table. No prefix, no namespace: the `uc_metadata.*`
  namespacing in this codebase belongs to properties, not to tags.
- *Metastore-level privilege*: a permission granted against the metastore as a whole rather than
  against one catalog, schema or table. Creating a catalog needs one; every privilege
  F-PLATFORM-003 granted is table-, schema-, catalog- or warehouse-scoped, which is a different
  and strictly narrower class.
- *Refusal*: rejecting a request before any write is attempted, with the specific problems named.
  Inherited wholesale from apply's existing behaviour, not invented here.
- *Fork-safe*: a workflow that runs, and still demonstrates something real, for somebody who
  clones or forks the repository with no secrets at all. A hard constraint carried from
  F-PLATFORM-001's interview-panel guarantee, and in this feature the primary delivery target
  rather than a fallback.
- *Minimal demo scope*: the fake-client-only version of this feature — every component in the
  in-scope build-verdict table and nothing in the handed-on one. As of revision 2 this is not a
  subset of the feature, it *is* the feature; everything that would touch a real metastore lives
  in F-PLATFORM-005.

## Scenarios

Conventions for binding tests to scenarios:
- *Backend (pytest)*: `@pytest.mark.scenario("SC-004-01")`, fallback `test_..._sc_004_01`.
- *Workflow-shape assertions*: scenario ID in the test name in the workflow-YAML test module, the
  same binding `apply.yml`'s fork-safety tests already use.

### SC-004-01 — Happy path: a request file lands and a usable catalog is created

- *Given* the request folder contains no file for the catalog `analytics_ba10231`
- *And* a business stakeholder has written a request file naming that catalog, its business
  application, its business area, what it is for, the schema it should contain on day one, the
  medallion tier it serves, and themselves as the requester
- *And* that request has been opened as a change request and approved by a reviewer who is not the
  requester
- *When* the change request is merged into the main branch
- *Then* the pipeline starts because of the merge, not because anybody ran anything by hand
- *And* it identifies exactly the request files the merge moved, ignoring every other changed path
  in the same push
- *And* the request passes validation: required fields present, catalog and schema names legal
  identifiers, business application resolvable, medallion tier a recognised value
- *And* the full set of writes is planned as an ordered list *before any of them runs*, and that
  plan is printed — the catalog, then the schema inside it, then the catalog's labels: its
  business area, its medallion tier, and its sensitivity if the request declared one
- *And* that plan is exactly three statements, every time — the labelling step is not conditional,
  because the business area and the medallion tier are required on every request, so there is
  always something to label
- *And* those writes are executed in that order, and each is reported individually
- *And* the catalog named in the file exists afterwards, and the schema named in the file exists
  inside it, so the requesting team can put a table somewhere without asking for anything further
- *And* the catalog carries, as searchable labels on the object itself, the business area and the
  medallion tier the request declared — so the classification a reviewer approved is visible to
  somebody browsing the catalogue, not only to somebody reading the request file
- *And* every statement executed is exactly the statement that was planned, and exactly what a
  live run would execute
- *And* one record is appended to the audit trail naming the catalog, the human who asked for it,
  the human whose merge authorised it, the time, which writes landed, and the outcome — with the
  requester and the approver recorded as separate facts rather than one "who was involved" field
- *And* the job's output states which catalogue it wrote to, so "created in the fake" is never
  mistakable for "created in the real workspace"
- *And* the job exits successfully

### SC-004-02 — Edge case: the requested catalog already exists

- *Given* a request file for a catalog that already exists — because the same merge is being
  re-run, because the request was reverted and re-merged, because the file was edited after the
  catalog was already created, or because somebody created the catalog by hand before the request
  was written
- *When* the pipeline processes that request
- *Then* the run succeeds rather than failing, and the catalog is left exactly as it is — no
  properties overwritten, no comment replaced, no ownership changed, and in particular the
  description in the request file is *not* re-applied over whatever comment the catalog carries now
- *And* every other statement in the plan is equally harmless on re-run: the schema is created only
  if it is missing, and labels already carrying the requested values are a no-op — with the one
  named exception that a label whose requested value has *changed* converges on the new one, which
  from revision 4 covers all three labelled fields (business area, medallion tier, sensitivity)
  through the same single tag-merge statement, per the create-only rule's carve-out
- *And* a request whose catalog exists but whose schema does not — the state SC-004-06 can leave
  behind — completes the job on this run, creating the missing schema and reporting that it did
- *And* the outcome is recorded in the audit trail as a successful run in which nothing changed,
  distinguishable from a run that genuinely created something, because "we made this" and "this was
  already here" are different facts and collapsing them would make the trail less useful than no
  trail
- *And* this is a deliberate choice of idempotent no-op over refusal: every other write path in this
  system is idempotent by design, and a provisioning step that refused on re-run would fail the
  first time a workflow is re-run from the Actions UI or a merge is reverted and re-landed — which
  is precisely when a person least wants a spurious failure to interpret
- *And* what is explicitly **not** claimed: that the pipeline can tell whether the pre-existing
  catalog is the one this request meant. It cannot. A catalog created by hand, or by a different
  team's request, with the same name is indistinguishable to this feature, and that limitation is
  named in Out of Scope rather than papered over with a check this feature does not do

### SC-004-03 — Failure case: a malformed request is refused before anything is created

- *Given* a request file that is not valid — a required field missing (including the schema name,
  the requester or the medallion tier, all of which are required), the catalog or schema name not a
  legal single-part identifier, the medallion tier or sensitivity not one of the recognised values,
  an unexpected extra field present, the business-application identifier unresolvable, or the file
  not parseable as YAML at all
- *When* the pipeline processes it
- *Then* validation runs before any statement is built or executed, and the request is refused whole
- *And* zero writes happen — no catalog, no schema, no labels; not a partial creation, not a catalog
  created and then found to have a bad owner reference, nothing. Refusal is the one path that
  guarantees a clean slate, which is precisely why it happens before the plan is executed rather
  than during it
- *And* the refusal names each specific problem, so the fix is "add this field" rather than "the
  request was rejected"
- *And* a record is still appended to the audit trail marking the run as refused and carrying those
  same problems, so a refused request is visible in the same trail as a successful one rather than
  being a silent non-event
- *And* the job exits non-zero, so the refusal is visible in the workflow run's status, not only to
  somebody who later goes looking in the audit log
- *And* if a push contains several request files and only one of them is bad, the others are still
  processed and the job still fails — the same partial-outcome honesty apply already has, rather
  than aborting the whole batch on the first bad file or hiding one failure behind several successes

### SC-004-04 — Edge case: somebody forks the repository with no credentials at all

- *Given* a reviewer has cloned or forked the repository, has no Databricks account, and has no
  secrets configured
- *When* they add a request file to the request folder and push to their own main branch
- *Then* the pipeline runs, does not fail, and does not attempt a live catalog creation it has no
  credentials for
- *And* it states plainly that no automation credential is configured and that it is therefore
  demonstrating the provisioning mechanism against the in-repository fake catalogue
- *And* the catalog, and the schema inside it, genuinely appear in that in-memory catalogue and the
  run can say so — this is a real demonstration of the mechanism, not a dry-run print
- *And* the distinction between "no credential configured, so this ran against the fake" and "a
  credential was configured and the live provisioning failed" is unmistakable in the job's output,
  because those two outcomes must never be confused with each other
- *And* every other credential-free path — the offline loop, the contract fake, the static coverage
  page — is untouched by this feature's existence
- *This scenario mirrors SC-003-04 deliberately, and for this feature it is the primary delivery
  target rather than a fallback branch: this feature's definition of done is that this scenario
  passes. There is no live path for it to be a fallback from*

### SC-004-05 — Failure case: a live run as an identity that cannot create catalogs (inherited by F-PLATFORM-005)

*Retained here, not built here — and now superseded.* Revision 2 moved the live path out of this
feature entirely, so nothing in F-PLATFORM-004 exercises this scenario and no test in this feature
binds to it. It stayed in this document because the analysis behind it is the reason the split
happened, and so that F-PLATFORM-005 would start from a scenario that already existed rather than
rediscovering it. **That feature was drafted on 2026-09-20 and took this scenario over as its own
SC-005-02**, rewritten there as a deliberate proof of the pre-grant state rather than an inherited
placeholder. What follows is kept for the record of where the reasoning came from; the live
version of it lives in `F-PLATFORM-005-live-catalog-provisioning.md`.

- *Given* somebody enables the live path and runs it as `ucmeta-ci-apply`, the machine identity
  F-PLATFORM-003 created, which holds catalog-, schema-, table- and warehouse-scoped privileges and
  no metastore-level privilege at all
- *When* the pipeline attempts to create the catalog for real
- *Then* the request still passes validation, because the request is fine — the failure happens at
  the write, which is where it belongs, and the two layers stay independent exactly as SC-003-06
  established for apply
- *And* the creation is refused by the metastore with a permission error naming the identity that
  was refused and the privilege it lacked
- *And* the failure is reported as a failure and recorded in the audit trail, not swallowed or
  downgraded, and the job exits non-zero
- *And* the error message makes clear that this is a missing *metastore-level* grant rather than
  anything to do with the request file, so nobody spends an hour editing YAML to fix a permissions
  problem
- *And* this scenario is the concrete reason the live path became a separate feature: it describes
  the expected behaviour of a path that is designed but deliberately not built here, and closing it
  means making a grant decision that is F-PLATFORM-005's to make, not this one's

### SC-004-06 — Edge case: the catalog is created and the schema is not

*Added in revision 3, because `default_schema` made this possible for the first time.* Until the
provisioning write became an ordered list, the only outcomes were "nothing happened" and
"everything happened". Now there is a third, and a scenario that pretended otherwise would be
describing a cleaner system than the one being proposed.

- *Given* a valid request whose catalog does not yet exist
- *When* the pipeline runs the plan and the catalog is created successfully, but the statement
  creating the schema inside it fails — a transient error, a name the metastore rejects for a
  reason validation did not catch, or, once F-PLATFORM-005 exists, a missing privilege
- *Then* the run does not roll the catalog back, because there is no transaction across these
  statements and pretending otherwise would be worse than admitting it
- *And* the outcome is reported as a partial success, not rounded up to success or down to failure
  — the same three-way honesty the applier already has when some of a contract's writes land and
  others do not
- *And* the audit record names exactly which writes landed and which did not, and why, so the state
  of the world is reconstructable from the trail rather than by going and looking at the metastore
- *And* the job exits non-zero, because a half-provisioned catalog is not a success
- *And* re-running the same request afterwards completes the job rather than failing on the catalog
  that now exists — every statement in the plan is independently idempotent precisely so that
  recovery from this state is "run it again" rather than "clean up by hand first" (SC-004-02)
- *And* what is **not** claimed: that this state cannot occur, or that the feature cleans it up
  automatically. It can occur, the fix is a re-run, and the catalog left behind in the meantime is
  real. Naming that is the honest position; a rollback claim this design cannot honour would not be

## Data

| Data | Source | Direction | Sensitivity |
|------|--------|-----------|-------------|
| Requested catalog name | The request file, authored by the requesting team | Read (and written into the metastore as an object name) | Internal |
| Business-application identifier | The request file; resolved against the existing owner registry, never copied as a free-text owner | Read | Internal |
| Business area | The request file | Read (and written as a tag on the catalog — rev 4; was recorded-only through rev 3) | Internal |
| Region | The request file, optional (resolved rev 2) | Read (recorded only, never enacted — **deliberately excluded from rev 4's tag widening**, because a searchable region label would advertise region-aware provisioning this platform does not do; see Rules & Constraints) | Internal |
| Description of what the catalog is for | The request file | Read (and carried into the creation statement as the catalog's comment — set at creation only, never re-applied to a catalog that already exists, per the create-only rule) | Internal |
| Name of the schema to create inside the new catalog | The request file, required (added rev 3) | Read (and written into the metastore as an object name) | Internal |
| Expected sensitivity of the catalog's contents | The request file, optional (added rev 3); drawn from the same controlled vocabulary the contract schema already uses for datasets and columns | Read (and written as a tag on the catalog) | Confidential — the classification itself is sensitive information, the same position F-PLATFORM-001 takes for dataset sensitivity |
| Name of the person who asked for the catalog | The request file, required (added rev 3); authored by the requester, never inferred | Read (recorded in the audit record as its own fact) | Internal |
| Medallion tier the catalog serves | The request file, required (added rev 3); one of the existing certification-tier values, *not* a deployment environment — see Glossary | Read (and written as a tag on the catalog — rev 4; was recorded-only through rev 3. Still not enacted as any access or placement decision: it is a searchable label, not a rule anything obeys) | Internal |
| The set of request files changed by a push | The push event's own diff, the same mechanism `apply.yml` uses | Read | Internal |
| The new catalog itself | Created in the in-memory fake catalogue; a real metastore only under F-PLATFORM-005 | Write | Internal |
| The new schema inside it | Created in the same run, immediately after the catalog (added rev 3) | Write | Internal |
| The catalog's labels | One tag-merge write carrying the business area, the medallion tier, and the sensitivity when one was declared (added rev 3 for sensitivity alone; widened to all three and made unconditional in rev 4). `region` is not among them, on purpose | Write | Confidential (the sensitivity value; the other two are Internal) |
| The ordered list of statements that was (or would be) executed | Built by the client seam and returned by it, one statement per write, the same shape every existing write method returns | Read (printed as a plan before execution, asserted on in tests) | Internal |
| Provisioning audit record (which catalog, who asked, who approved, when, which writes landed, outcome) | Generated per run, published through the existing append-only release log as a `ReleaseRecord` with two field meanings widened (rev 2) and one additive optional field for the requester (rev 3) | Write | Internal |
| The requesting human's name | The request file itself | Read (recorded in the audit record, distinct from the approver) | Internal |
| The approving human's name | The merge event, the same way apply already resolves it | Read (recorded in the audit record) | Internal |
| Whether an automation credential is configured | The automation environment's secret store — presence only, never the value | Read | Confidential (the values; the presence flag is Internal) |

### The request file, concretely

The Data table above stays deliberately in plain language, per this folder's template. This block
is the one place the spec names the authored shape directly, because the request file *is* the
feature's whole user interface and a reviewer of this document should be able to see what a
business stakeholder actually types. It is illustrative of the shape agreed in revision 3; the
authoritative definition is the request model in the prototype repository.

```yaml
catalog_name: analytics_ba10231
business_application_id: BA-10231
business_area: analytics
region:
description:
default_schema: default
sensitivity:
requested_by:
environment: bronze
```

This is also what `catalog-requests/_template.yaml` ships: every field present, the three with
sensible defaults (`catalog_name`'s illustrative form, `default_schema: default`,
`environment: bronze`) filled in, and the rest left blank for the requester. The two optional
fields — `region` and `sensitivity` — stay in the template precisely *because* they are optional:
a field a requester never sees is a field they never consider. Unknown fields are rejected rather
than ignored, so a typo in a field name fails the request rather than silently dropping whatever
the requester meant by it.

## Rules & Constraints

- *The scope is the fake path, and it is a deliverable rather than a fallback.* The feature is done
  when a request file landing on the main branch causes a catalog to be created in the
  in-repository fake catalogue and a record to be published, with no credentials anywhere. There is
  no live path in this feature — not disabled, not optional, not one flag away; it is
  F-PLATFORM-005's whole subject. Stating this as a rule rather than an aspiration is what stops
  the build quietly sliding into a grant negotiation halfway through.
- *The trigger is a push to the main branch whose changed paths include a request file, and the
  spec says so plainly rather than describing it as "when a file appears".* GitHub Actions has no
  file-creation event; the closest real primitive is `on: push` with a path filter, which is exactly
  what `apply.yml` and `validate.yml` already use for contracts. This feature reuses that shape
  filtered to the request folder rather than inventing a second CI mechanism, which also keeps it
  consistent with the repository's whole governance model: things happen on merge, after review, or
  they do not happen.
- *Added and modified request files are treated identically — decided in revision 2, and decided as
  a placeholder rather than a final position.* The changed-path diff reports both, and the creation
  statement is idempotent, so processing a modified file costs a no-op rather than a surprise. The
  decision is "any push, for now": it is deliberately the broader and simpler option, taken because
  it matches every other workflow in the repository and because idempotency makes the extra breadth
  harmless. Narrowing to added-only is a one-flag change (`--diff-filter=A`) and stays a legitimate
  revisit, not a reversal — recorded that way so a later change reads as the plan working rather
  than as somebody overturning a settled rule.
- *The catalog name is authored explicitly, never derived.* An earlier sketch of the request file
  left the catalog's name implicit in the business-application identifier and the business area,
  which meant the name a team would get was a function of a rule nobody had written down. Carrying
  `catalog_name` as its own required field makes the requested name reviewable as itself — the
  reviewer approves a name, not a derivation — and removes an entire class of "why is it called
  that?" ambiguity. A convention may still be *recommended* in the template; it is not enforced by
  construction.
- *The field is spelled `business_area`.* The originating sketch spelled it `bussines_area`. Fixing
  it now costs nothing; fixing it after the first request file is written costs a migration of
  every file already authored, for a typo. Recorded here so the correction is a decision with a
  reason attached rather than a silent divergence from the source sketch.
- *Region is optional, recorded, and not enacted — settled in revision 2.* The request file carries
  region as an optional declared field and nothing in this feature does anything with it. Optional
  rather than required precisely because nothing enacts it: a required field that changes no
  behaviour teaches people to fill in fields that do not matter, which is a habit that survives
  long after the field stops being inert. Mapping a region to a storage location, a metastore assignment or
  a regional catalog is real provisioning work that the Free Edition workspace cannot demonstrate
  at all — it is a single-region, managed-storage environment. This is the same position
  F-PLATFORM-001 already takes ("region is addressable in the contract; no region-specific apply
  paths exist"), stated once more here because a declared-but-unused field is exactly the kind of
  thing that later gets mistaken for a working one. **Revision 4 considered region for the tag
  widening and excluded it explicitly.** `business_area` and `environment` moved from
  recorded-to-enacted-as-labels; `region` did not, and the reason is the sentence above rather
  than an oversight. A tag is a searchable, filterable, ABAC-eligible fact about the object, so a
  catalog carrying `region: eu-west-1` invites somebody to filter on it and conclude the platform
  places catalogs by region. It does not, cannot in this workspace, and the whole point of this
  bullet is to stop that inference. Region stays recorded in the request file and in the audit
  trail and stays off the catalog until something actually enacts it.
- *Provisioning is more than one write, and it is planned as an ordered list before any of it runs
  — a revision 3 consequence of requiring a default schema.* The plan is: create the catalog,
  create the schema inside it, and label the catalog. **From revision 4 the plan is always exactly
  three statements**: the labelling step used to be conditional on a sensitivity having been
  declared, and is not any more, because the business area and the medallion tier are required on
  every request and are now labelled too. Every valid request therefore has the same plan shape,
  which is one fewer branch to reason about, not one more.
  Each step is attempted in order, each succeeds or fails on its own, and a failure part
  way through does not abort the remainder or roll back what already landed. This is not a new
  mechanism invented here: it is exactly what the applier already does when it plans seventeen
  writes for a contract, and reusing that machinery rather than writing a bespoke two-step
  sequencer is the whole point. The outcome vocabulary is therefore the applier's, unchanged:
  success, partial failure, failure, refused.
- *A catalog with no schema in it is not a provisioned catalog.* `default_schema` is required, not
  optional, because the thing a requesting team actually needs is somewhere to put a table, and
  handing them an empty namespace means the next thing they do is ask a human for a second favour
  — which is the manual, out-of-band step this feature exists to remove. Making it optional would
  have made the common case the one that does not work.
- *Three new client methods, each mapping to exactly one statement — not one compound method.*
  Creating a catalog, creating a schema and writing tags at catalog granularity are three separate
  methods on the `UCClient` protocol, implemented on both the real and fake implementations. The
  alternative considered and rejected was a single `create_catalog` that also took the schema and
  the label and emitted everything at once. It was rejected on two grounds. First, the seam's
  existing contract is one method, one statement, one returned string — a compound method would
  have to return several statements or a joined blob, breaking the postcondition every other write
  method honours and the plan/execute equivalence that rests on it. Second, creating a schema is a
  capability worth having on its own: schema provisioning is already named as a follow-on, and a
  schema-creating method that only exists inside catalog creation would have to be prised back out
  when that arrives. Three narrow methods compose into one plan; one compound method does not
  decompose.
- *Every new client method follows the existing write-method shape exactly, with no exceptions.*
  Keyword-only `dry_run` defaulting to false, returns the exact statement string either way, builds
  that statement once from a single code path so a planned statement and an executed one can never
  diverge, and is idempotent in effect. This is not a preference — it is the property that lets the
  planned statements be printed in a change request and trusted to be what actually runs, and every
  existing write method already honours it.
- *Writing a label on a catalog is a genuinely new capability, not a variant of an existing one.*
  The codebase writes tags on tables and on columns. Nothing writes them on a catalog, and
  assuming the table-tag method covers it would be wrong at the SQL level and wrong at the
  privilege level. It gets its own method, mirroring the table-tag method's shape exactly —
  `dry_run`, idempotent merge rather than replace, returns the statement — so the only thing new
  about it is the object it targets. Revision 4 widens what that one method is *given* — three
  key/value pairs instead of one — and changes nothing about the method, the statement count or
  the seam. That is the point: a widening that fits inside an existing step is reversible in a way
  that a fourth statement would not be.
- *Three classification fields are written as catalog tags — `business_area`, `environment` and
  `sensitivity` — and the properties alternative was examined against this codebase's own rule and
  rejected. Revision 4.* Through revision 3, `business_area` and `environment` were required on
  every request, read by a reviewer, recorded in the request file and the audit log, and written
  nowhere in Unity Catalog at all — which made two required fields cost a requester real attention
  and buy them nothing visible. The mechanical precedent argued for properties: the applier sends
  `certification` — the very same controlled vocabulary `environment` reuses — to `TBLPROPERTIES`
  at table level. That precedent was rejected because it reads the applier's rule too broadly. The
  rule the applier's own docstring states is about *searchability*, and the properties bucket in
  practice holds two things: pointers and references that have to be re-resolved elsewhere to mean
  anything (`business_application_id` resolves against the owner registry), and declared
  commitments nobody searches by (retention, refresh cadence, SLA). `business_area` and
  `environment` are neither — they are plain classification values, complete in themselves, with
  nothing to re-resolve and every reason to be searched by. Structurally they are `sensitivity`,
  which has always been a tag. Unity Catalog's own affordances point the same way: tags are the
  searchable, filterable, ABAC-eligible mechanism, and being findable by business area or by
  medallion tier is the actual reason to record either. Two supporting facts, neither load-bearing
  on its own: nothing in this codebase writes catalog *properties*, so there was no existing
  catalog-granularity properties path to be consistent with; and `set_catalog_tags` already exists
  and is already live-verified, so this widens a step that is known to work rather than adding one
  that is not. Each field's own name is the tag key, verbatim and unprefixed — `business_area`,
  `environment`, `sensitivity` — the same convention the applier uses at table and column level, so
  the same concept is searchable under the same key at every granularity.
- *The fake implementation gains a real notion of catalogs and schemas, and something to assert
  against.* Today the fake is a flat dictionary of tables keyed by full name with no concept of a
  catalog or a schema at all. It needs both — the names it has been asked to create, the labels it
  has been asked to write on them, and accessors for tests to read all of it back, following the
  precedent the row-insert method already set when it added a second piece of state and an accessor
  beside it. Without that, "the catalog and its schema were created in the fake" is unassertable,
  and this feature's headline scenario has nothing to prove itself with.
- *The request reuses the contract schema's controlled vocabularies rather than inventing parallel
  ones, and the coupling that creates is named rather than discovered later.* The sensitivity
  values and the medallion-tier values are the same enumerations the contract schema already uses
  for datasets and columns. The benefit is that one vocabulary means one meaning: a "confidential"
  catalog and a "confidential" column are confidential in the same sense, which is exactly what a
  shared glossary is for. The cost, stated plainly, is that those enumerations are now load-bearing
  for two file formats instead of one — changing an allowed value is already a slow-path change
  under the existing routing declaration, and from revision 3 it ripples into catalog requests too.
  That is a reason to be careful with those lists, not a reason to fork them.
- *`environment` means the medallion tier, and the name is a deliberate compromise rather than an
  accident.* The field reuses the existing bronze/silver/gold vocabulary and has nothing to do with
  dev/staging/prod. Reusing an established controlled list was judged worth more than coining a
  more precise but novel field name, and the tension is recorded in the Glossary and in the
  template's own comments rather than left for a future reader to misread. If it ever does get
  misread in practice, renaming the field is a slow-path schema change with a migration for every
  request file already written — cheap now, less cheap later, and that asymmetry is the reason the
  ambiguity is documented loudly instead of quietly tolerated.
- *Create only, with exactly one named exception — one write, now carrying three fields. Never
  drop.* The new verb's powers are creating a catalog, creating a schema inside it, and writing the
  catalog's classification labels. No deletion path, no rename, no ownership mutation, no
  re-application of a changed description over a catalog that already exists. A provisioning tool
  that can also destroy is a materially different security object from one that can only create,
  and this one is deliberately the second kind.
- *The exception is the catalog's labels, and revision 4 widened it from one field to three.* The
  label write is in the plan on every run — unconditionally, from revision 4 — and uses the same
  merge semantics the existing tag writes use, which means a request whose declared `sensitivity`,
  `business_area` or `environment` has changed will move the corresponding label to the new value.
  That is technically an alteration of an existing object. It remains **one exception, not three**:
  one statement, one merge, one converging set of labels on one object. Everything else — the
  catalog's name, its comment, its schema, its ownership — stays create-only.
- *Whether rev 3's reasoning for that exception survives the widening, field by field, because
  "three now instead of one" is not an argument.* Rev 3 gave two reasons. They do not transfer
  equally, and pretending they do would hide the one place this widening genuinely changes the
  shape of the rule.
  - *Recoverability — transfers identically to all three, and gets stronger.* The argument was that
    labelling at creation time only leaves SC-004-06's failed-label case unrecoverable: if the
    label statement is the one that fails, a create-only label can never be applied. All three
    fields ride the same single tag-merge statement, so all three share exactly that failure mode,
    and the fix for all three is the same re-run. It gets stronger because the statement is now
    unconditional: through rev 3 a request declaring no sensitivity had no label statement and so
    no failed-label case at all, whereas every request now has one. Recoverability was the weaker
    of rev 3's two reasons and is now the load-bearing one.
  - *Uncorrectable-classification-gets-corrected-unofficially — holds for `sensitivity`, holds
    weakly for the other two, and the difference is worth naming.* The force behind it was urgency:
    a wrong sensitivity label is a live governance defect, somebody will fix it, and if the
    reviewed path cannot they will open a SQL editor — which is the exact behaviour this whole
    project exists to remove. That pressure is real for `sensitivity` and much milder for
    `business_area` and `environment`: a catalog filed under the wrong business area is untidy, not
    unsafe, and nobody bypasses review over it. So for those two the exception is justified on
    recoverability and on mechanism-uniformity — they share a statement with a field that must
    converge, and splitting the merge so that one key converges and two do not would be a bespoke
    rule inside a single `SET TAGS` call, more machinery for less clarity — rather than on urgency.
    Stated rather than smoothed over, because a future reader deciding whether a *fourth* field may
    join the exception should know that two of the current three got in on the weaker argument.
  - *One consequence rev 3 did not have to face.* `environment` is required, so it always has a
    value and that value can legitimately change: a catalog genuinely gets re-tiered from bronze to
    silver. Converging it is therefore not just tolerable but useful — and it stays inside the
    governance model, because the way it changes is still "edit the request file, have it reviewed,
    merge it". The exception widens what can move on re-run; it does not widen who may move it.
  - *What the exception still does not cover.* The description remains create-only and is not
    re-applied to an existing catalog, which is now an asymmetry worth seeing plainly: three fields
    converge and one does not. It is defensible rather than accidental — tags merge key by key,
    while a comment replaces wholesale, so re-applying a description silently overwrites whatever a
    human may have written on the catalog since. Convergence is safe where the write is a merge on
    a key this platform owns, and unsafe where it is a replace on a field anybody can edit.
- *Validate, then refuse or plan, then execute, then record — in that order, every time.* The same
  discipline apply already enforces: nothing is written if validation fails, a record is published
  for every outcome including refusals and failures, and no outcome is silently skipped. The
  feature inherits this rather than reimplementing it, and any deviation from it in the new module
  is a defect.
- *Every outcome publishes one audit record, in the existing record shape, through the existing
  append-only log — settled in revision 2.* Success, no-op, refusal and failure all produce a line.
  The existing record carries a dataset's three-part identity and a contract version, neither of
  which a catalog request has in the same sense. The decision is to reuse that record rather than
  introduce a second type: the catalog's name goes in the identity field and the request-file
  schema version in the contract-version field, and both fields' *documented meanings* are widened
  to say so — the field set does not change, so nothing that reads the log today breaks. The
  reasoning is that one audit trail is worth more than two tidier ones: every consumer of that log
  reads it as "things that were changed, by whom, with what outcome", which a catalog creation
  genuinely is, and splitting the trail by object type would mean anybody auditing the platform has
  to know to look in two places. The cost is accepted and named rather than hidden — widening a
  shared field's meaning to fit a second use is how shared shapes rot, so the widening is a
  deliberate, documented act here, and the moment a third kind of thing wants into this log is the
  moment to stop widening and split the type properly.
- *The requester gets its own field on the audit record, and revision 2's "field set unchanged"
  is amended by exactly that one field.* Revision 3 considered folding the requester's name into
  the record's free-text summary and rejected it. The reason is the record's own design argument:
  F-PLATFORM-003 insisted that the approving human and the machine identity that performed the
  write be recorded as two separate fields precisely because they are two separate facts, and
  collapsing them would destroy the distinction that feature existed to create. A catalog request
  has a third such fact — who asked — and burying it in prose would make it unqueryable while
  every other party to the same event stays structured. So one optional field is added, defaulting
  to absent. The compatibility claim is narrower than rev 2's but still holds: existing log lines
  parse unchanged because the field is optional, and existing readers are unaffected because
  nothing that reads the log today looks for it. This is stated as an amendment rather than
  presented as consistent with rev 2, because it is not quite — rev 2 said the field set would not
  change, and it now changes by one additive optional field, for a reason rev 2's own reasoning
  produces.
- *Every name that reaches a statement builder is validated as an identifier first.* The catalog
  name and the schema name must each be a legal single-part name and are rejected otherwise —
  this is a validation rule and not merely a quoting concern, but the statement builders still
  quote through the same helper every other write uses, because defence in depth costs one function
  call here. The repository has already been bitten once by a live-confirmed string-escaping bug in
  this exact code path; re-deriving that lesson on a `CREATE` statement would be careless. The
  description and the label value are free text and are escaped rather than restricted, the same
  way a contract's description already is.
- *Unknown fields in a request are rejected, not ignored.* A request file carrying a field the
  model does not know about fails validation rather than being silently dropped. With nine fields,
  four of them added in one revision, a misspelled field name is a realistic authoring mistake, and
  the failure mode of ignoring it is the worst kind: the request succeeds, and the thing the
  requester asked for quietly did not happen.
- *The request folder gets the same template-and-carve-out treatment the contracts folder has.* A
  template file lives in the folder as the authoring starting point, and the pipeline's path filter
  excludes it explicitly, the same way both existing workflows exclude the contract template and
  schema directory. A template that gets processed as a real request is a self-inflicted failure the
  repository already knows how to avoid.
- *The change-routing declaration is updated explicitly rather than left to fall through.* Paths
  matching no declared class today route to the slow path by default, which happens to be the right
  answer for a catalog request — but by accident, not by declaration, and "correct by luck" is not
  a property this repository's own routing module claims anywhere else. The request folder is
  therefore declared explicitly on the slow path, on blast-radius grounds: a description edit
  affects one dataset, while creating a top-level catalog creates a namespace in the metastore that
  every team can see and that nothing in this feature can remove. Whether that eventually warrants
  a third change class of its own, rather than being filed under the existing platform-change
  class, rides with F-PLATFORM-005 (see Open Questions, rev 2) — the two-class declaration is
  correct and sufficient for this feature as built.
- *Creating a catalog needs a privilege nobody in this workspace's automation holds, and that is
  why this feature stops where it does.* F-PLATFORM-003's service principal was granted the right
  to use the catalog, the right to use two schemas, ownership of three specific tables and the
  right to use a warehouse. Creating a catalog is a metastore-level privilege and is not in that
  set, deliberately — that feature's entire thesis was that the identity should hold only what the
  applier actually performs. Closing that gap means either adding a metastore-level creation
  privilege to that identity, which widens the blast radius of a leaked credential from "vandalise
  three tables' metadata" to "create namespaces in the metastore", or introducing a second,
  differently-scoped provisioning identity, which preserves least privilege at the cost of a second
  credential to manage. **F-PLATFORM-004 makes neither choice and builds neither path.** Both, and
  the first real catalog that results, belong to F-PLATFORM-005. No line is added to the existing
  grant script by this feature, and no implementer of this feature has permission to add one.
- *Fork-safe by construction, not by oversight.* A clone or fork with no secrets must run this
  pipeline, demonstrate the mechanism, and exit successfully. This is F-PLATFORM-001's
  interview-panel guarantee, it applies to every workflow in this repository without exception, and
  in this feature it is also the definition of done.
- *No manual trigger, no break-glass path.* No workflow dispatch button, no "provision this one by
  hand because it is urgent" escape hatch. The same rule F-PLATFORM-003 states for apply, for the
  same reason: an emergency escape hatch is the mechanism by which every merge-only rule in history
  has stopped being true.

## Non-functional Requirements

Brief by design — this is a small feature with three statements at the end of it, and
inventing numbers for it would be fabricated rigor.

- *Performance.* One request file is exactly three statements, every time — revision 4 made the
  label write unconditional, so the old "two, or three when it declares a sensitivity" no longer
  describes anything. Against the fake — which is where this feature runs, always — all three are
  instantaneous. Whenever F-PLATFORM-005 points it at a real metastore they become three warehouse
  round trips, dominated entirely by a cold serverless warehouse start, which is already the demo
  loop's largest cost; the extra statements are noise against that, and revision 4 adds no round
  trip at all — it puts two more key/value pairs into a `SET TAGS` call that was already being
  made. Nothing here changes the under-two-minutes budget F-PLATFORM-001 set.
- *Scale.* A handful of request files, at most one new catalog per merge in any realistic demo. The
  design question is whether the mechanism is real, not whether it scales — and the pipeline is a
  loop over changed paths, so the shape scales fine regardless.
- *Retention.* Request files stay in the repository forever as the record of who asked for what;
  the audit trail keeps one line per attempt for as long as the repository exists. Neither is
  cleaned up, and the request file is deliberately not deleted after processing — a queue that
  empties itself loses the history that made it worth having.
- *Availability.* Degrades the way apply already degrades: if the catalogue is unreachable the run
  fails loudly with the reason named, and the audit record says what happened. With no credential
  configured — which is every run of this feature — nothing fails at all: the pipeline runs the
  mechanism against the fake and says so in its own output.
- *Security.* No new credential is introduced by this feature, and no new privilege is granted to
  any identity. The security argument for provisioning against a real metastore is the privilege
  question in Rules & Constraints, and it is exactly why that work is F-PLATFORM-005 rather than a
  section of this one. No secret value is ever printed, and the pipeline reports only whether a
  credential is configured, never what it is.
- *Regulatory.* None assumed, same as the previous three specs. Recording who asked for a namespace
  and who approved it is ordinary engineering hygiene and is justified on those grounds alone.

## Out of Scope

- *The live path, in every form — it belongs to F-PLATFORM-005 (drafted 2026-09-20).* Not "deferred
  within this feature", not "enabled by a flag if somebody has credentials": absent. The command
  that writes a real catalog into a real metastore, the identity that would be allowed to run it,
  and the first catalog actually provisioned against the workspace are all that future feature's
  content. SC-004-05 is retained in this document as the scenario that feature should start from,
  and is explicitly not exercised here.
- *Granting a metastore-level creation privilege to any identity — also F-PLATFORM-005.* Whether
  `ucmeta-ci-apply` gains the privilege or a second provisioning-only identity is introduced is a
  security decision with its own argument, and it is not made here. No line is added to the
  existing grant script by this feature, and a future implementer reading this section for
  permission finds none.
- *Catalog deletion, renaming or any other lifecycle operation.* Create only. Removing a request
  file does nothing; reverting the merge that created a catalog does not remove the catalog, which
  is an asymmetry with apply's reversibility claim and is named here rather than hidden. Anything
  beyond creation is a separate feature with a separate and much more careful security argument.
- *Reconciling an existing catalog against its request file.* If somebody edits a request file
  after the catalog exists, the pipeline re-runs an idempotent plan and changes nothing that is
  already there, with one deliberate exception. A changed description is not re-applied, and a
  renamed `default_schema` creates the new schema while leaving the old one in place. The exception
  is the catalog's labels — business area, medallion tier and sensitivity — which converge on
  whatever the request currently declares, through one tag-merge write (widened from sensitivity
  alone in rev 4); see the create-only rule for why those fields are allowed to move and the
  description is not. Beyond that, the pipeline does not
  detect or report the divergence between what the file now says and what the catalog now is.
  Drift detection for catalogs is a real idea and is not this feature.
- *Detecting whether a pre-existing catalog is the one the request meant.* Named in SC-004-02. This
  feature treats name collision as a successful no-op and cannot distinguish "already
  provisioned by this mechanism" from "somebody made a catalog with that name for unrelated
  reasons".
- *Region-to-storage-location mapping — and, from revision 4, region as a catalog tag either.*
  Region is recorded and not enacted. Real regional provisioning needs storage credentials,
  external locations and a metastore-per-region topology that the Free Edition workspace does not
  have and cannot demonstrate. When `business_area` and `environment` were promoted to catalog
  tags, `region` was considered and deliberately left behind: a searchable region label would
  imply region-aware placement the platform does not perform.
- *Validating the business area against a real registry.* Business area is free text validated for
  presence only. A controlled list resolved against an authoritative source is the right production
  answer and would need that source to exist; the business-application identifier, which *is*
  resolved against the existing owner registry, already carries the ownership half of this
  concern.
- *Any schema beyond the one the request names, and any table or grant at all.* Revision 3 narrowed
  this bullet rather than deleting it: exactly one schema is created, the one named in
  `default_schema`, because a catalog with nothing in it is not usable. A second schema, any table,
  and — importantly — any grant are still out. In particular this feature does not grant the
  requesting team any access to the catalog it just asked for, which remains a genuine gap between
  "the catalog and a schema exist" and "the team can use them", and is named rather than glossed.
  A request file that wanted to declare a list of schemas, or the grants that should accompany the
  catalog, is a reasonable next shape and is not this one.
- *Quota, cost or naming-policy enforcement.* No limit on how many catalogs a team may request, no
  enforced naming convention beyond identifier legality, no chargeback. A real platform needs all
  three; none is built.
- *A web form or any authoring surface other than a file and a change request.* Same position
  F-PLATFORM-001 takes for contracts, for the same reasons.
- *Extending the coverage or dashboard features to count catalogs.* Coverage measures metadata fill
  on datasets. A provisioned catalog is not a dataset and is not counted; making it one would
  change what the coverage number means, which is a bigger decision than it looks.

## Dependencies

- *Related features*:
  - *F-PLATFORM-001* — supplies nearly everything this feature composes: the client seam and its
    two implementations, the plan/apply/refuse discipline, the append-only release log, the owner
    registry the business-application identifier resolves against, the CLI's one-verb-per-module
    shape and credential-free default, the template-plus-carve-out pattern for authored YAML, and
    the interview-panel constraint that makes the fake path the delivery target. It is also the
    feature whose forcing-function argument this one partially closes: provisioning stops being
    entirely somebody else's flow.
  - *F-PLATFORM-003* — supplies the CI trigger shape this feature copies (changed-path diff,
    per-file loop, fork-safe credential check with two mutually exclusive paths), and supplies the
    constraint that pushed the live path out of this feature entirely: the machine identity it
    created holds table-scoped privileges by design and cannot create a catalog. This feature must
    not undo that narrowness casually, which is the whole reason the grant work became its own
    feature rather than a build step here. It is also the precedent for the split — F-PLATFORM-003
    separated "give CI an identity" from "take the human's access away" and gated them on separate
    approvals, for exactly the reason the mechanism and the privilege widening are separated here.
  - *F-PLATFORM-005 (drafted 2026-09-20 — `F-PLATFORM-005-live-catalog-provisioning.md`)* — the named follow-on that owns everything this feature
    deliberately does not do on the live side: the metastore-level `CREATE CATALOG` privilege
    decision, the choice between widening `ucmeta-ci-apply` and introducing a provisioning-only
    identity, wiring the live branch of the workflow, and the first real catalog provisioned
    against the workspace. It inherits SC-004-05 as its starting scenario and inherits the
    privilege argument stated in this document's Rules & Constraints. Named here as a forward
    reference only — drafting it is not part of this feature.
  - *Consequence found later, recorded in F-PLATFORM-001 rev 6 (2026-09-20).* Making catalogs
    provisionable on demand silently invalidated an assumption F-PLATFORM-001 had never written
    down — that every contract describes one of the three fixture tables `FakeUCClient` holds, so
    the credential-free `validate.yml` path can always fully check the repository. The first
    contract for a table in a provisioned catalog failed validation on the missing fixture entry
    alone. Fixed there, not here: the fake's fixture set is now a maintained mirror of every
    contracted table. Noted so the link is discoverable from this end; no decision of this
    feature's changes.
  - Other likely follow-ons: additional schemas beyond the single default one this feature creates;
    granting the requesting team access to the catalog they asked for; catalog lifecycle beyond
    creation.
- *ADRs*:
  - *ADR-009* (shipped with F-PLATFORM-003, *A machine identity for apply, and taking the human's
    write access away*) — untouched by this feature, and deliberately so: nothing here changes any
    identity's privileges. It is directly implicated by F-PLATFORM-005, not by this one — if that
    feature closes the gap by widening `ucmeta-ci-apply`, ADR-009's least-privilege claim needs
    amending rather than silently outgrowing, and that belongs in a superseding or amending ADR
    rather than a commit message. Recorded here so the obligation travels with the forward
    reference instead of being rediscovered later.
  - *ADR-010 (proposed) — Catalog provisioning by request file, and why it is create-only and
    fake-only.* Worth writing when this feature is approved, not before. It should record: the
    choice of a file-and-merge request mechanism over a ticket, a form or a direct SQL grant to
    requesting teams, and why the file wins here (it is the mechanism the repository already uses,
    it makes the request reviewable as an artifact, and it costs no new infrastructure); the choice
    of idempotent no-op over refusal when the catalog already exists, with the re-run and
    revert-and-re-merge cases as the deciding evidence; the decision to make the pipeline
    create-only *with the catalog's labels as its single named exception*, what a delete path
    would have required in exchange, and why an uncorrectable classification was judged the worse
    failure — including rev 4's widening of that exception from one field to three, and the honest
    note that two of the three got in on the recoverability argument rather than the
    uncorrectable-classification one; the rev 4 decision to write `business_area` and `environment`
    as catalog tags rather than catalog properties, why the table-level `TBLPROPERTIES` precedent
    for `certification` was examined and rejected, and why `region` was excluded from the same
    widening; the decision to require a default schema, which turned provisioning from one statement
    into a plan and pulled partial-failure semantics in with it; the decision to add three narrow
    one-statement client methods rather than one compound `create_catalog`, and why the seam's
    one-method-one-statement contract made that the cheaper shape to live with; the decision to
    reuse the existing release record with two widened field meanings plus one additive optional
    field, and the named cost of that widening; and the decision to split the live path out into
    F-PLATFORM-005 rather than carry it here — including the honest note that a pipeline which has
    never created a real catalog is a mechanism demonstration, not a provisioning system, and
    should be described as the former wherever it is shown.
- *Code modules* (in `uc-metadata-platform`; all paths are proposals, none exist yet unless noted).
  Named at method granularity rather than file granularity, because this list is the first thing a
  future implementer scans and "touches `uc_client.py`" tells them nothing:
  - `catalog-requests/` — new top-level folder, plus `catalog-requests/_template.yaml` carrying all
    nine fields.
  - `src/uc_metadata/uc_client.py` (exists) — **three** new methods on the `UCClient` protocol and
    on `RealUCClient`, one per statement, each following the existing write-method shape:
    `create_catalog` (catalog plus its comment, at creation), `create_schema` (the request's
    `default_schema`, inside the new catalog), and a catalog-granularity tag write — named here as
    `set_catalog_tags` for concreteness, mirroring `set_table_tags` exactly and differing only in
    the object it targets. Nothing in the existing seam writes at catalog granularity today, so all
    three are additions rather than adaptations.
  - `src/uc_metadata/fake_uc.py` (exists) — the same three methods, plus the in-memory state they
    need — created catalog names, schema names within them, and catalog-level tags — plus accessors
    for tests to read each back, following the `inserted_rows` precedent.
  - `src/uc_metadata/provision_catalog.py` — new module holding the nine-field request model, its
    validation, and the validate/refuse/plan/execute/record flow over the ordered write list. From
    rev 4 its tag step builds `{"business_area": ..., "environment": ..., "sensitivity": ...}` —
    the last key present only when declared — and is always in the plan; the field-name-as-tag-key
    convention lives here, in the one place that maps request fields onto writes, the same way
    `apply.py` owns the equivalent mapping for contracts.
  - `src/uc_metadata/models.py` (exists) — **imported from, not modified**: the request model reuses
    `Sensitivity` and `CertificationTier` rather than declaring parallel enumerations. Listed here
    so the coupling is visible to whoever next changes either list.
  - `src/uc_metadata/owner_registry.py` (exists) — imported from, not modified: the
    business-application identifier resolves through the existing `resolve_owner`.
  - `src/uc_metadata/cli.py` (exists) — one new verb, wired the same way the existing five are.
  - `.github/workflows/provision-catalog.yml` — new workflow, `apply.yml`'s shape with a different
    path filter.
  - `change_classes.yaml` (exists) — one declaration added for the request folder.
  - `src/uc_metadata/release_log.py` (exists) — one documented field-meaning widening on two fields
    (rev 2), plus one additive optional field for the requester (rev 3).
  - `tests/unit/` — scenario-bound tests for SC-004-01, SC-004-02, SC-004-03, SC-004-04 and
    SC-004-06, plus workflow-shape assertions for the fork-safety branch. SC-004-05 is deliberately
    unbound here; it belongs to F-PLATFORM-005.

### Build verdicts per component

Principle carried over from the previous three specs, with this feature's own addition: *the table
separates what this feature actually builds from what is named and handed onward, and a handed-on
row says where it went rather than leaving it to be inferred.* Nothing in this table has been
built or run — these are proposals, and the verdicts say what should be built, not what was.

**In scope**

| Component | Verdict | Rationale (one line) |
|---|---|---|
| `catalog-requests/` folder and `_template.yaml` | *Build — real, tiny* | The authoring surface and the whole user-facing interface of the feature; the template mirrors the contracts folder's existing pattern so the carve-out in the path filter has something to exclude. |
| Request file shape: nine fields — `catalog_name`, `business_application_id`, `business_area`, `region`, `description`, `default_schema`, `sensitivity`, `requested_by`, `environment` | *Build — real (shape finalised rev 3; unchanged by rev 4)* | Every shape decision settled: explicit `catalog_name`, corrected `business_area` spelling, `region` and `sensitivity` optional, the other seven required, unknown fields rejected rather than ignored. `sensitivity` and `environment` reuse the contract schema's existing controlled lists rather than forking them — with the coupling that creates named in Rules & Constraints. Rev 4 changed what three of these fields *do*, not what they are: no field added, removed or renamed. Still short enough that a reviewer reads a request in under a minute, which is the point. |
| Three new methods on the `UCClient` protocol: `create_catalog`, `create_schema`, `set_catalog_tags` | *Build — real; the genuinely new capability, and it is three things not one* | This is the only place the platform gains powers it did not have: nothing today creates a catalog, creates a schema, or writes a tag at catalog granularity. Three separate one-statement methods rather than one compound method, for the seam-contract and reusability reasons argued in Rules & Constraints. Each must follow the existing write-method shape exactly: keyword-only `dry_run`, returns the statement string either way, single statement-building code path, idempotent in effect. |
| The same three methods on the real implementation | *Build — real, thin; built but never exercised live here* | Each is a short statement builder over the existing execution plumbing, quoting identifiers through the same helper every other write uses and escaping free text through the same one. Deliberately never run against a real metastore by this feature — they exist so the seam has two implementations and so F-PLATFORM-005 has something to switch on, not so this feature can quietly reach the workspace. |
| The same three methods on the fake implementation | *Build — real, and it needs three new pieces of state* | The fake is a flat dictionary of tables today, with no concept of a catalog, a schema or a catalog-level tag. It needs all three — created catalog names, schema names within them, and catalog tags — each with an accessor for tests to read back, following the precedent set when row inserts added their own state and accessor. Without this, every claim SC-004-01 and SC-004-06 make about what ended up existing is unassertable. |
| `src/uc_metadata/provision_catalog.py` | *Build — real* | Request loading, validation, refusal-before-write, ordered-plan construction, execution, and one audit record per outcome. Deliberately a new module rather than a verb inside the applier: it operates on a different input, produces a different kind of write, and shares nothing but discipline. |
| The ordered write plan (catalog, then schema, then labels) and its partial-failure handling | *Build — real; new in rev 3, and the reason SC-004-06 exists. Rev 4: exactly three statements, always* | `default_schema` turned provisioning from one statement into a list, which means this feature now inherits the applier's plan-then-execute-then-report-each-step machinery rather than sidestepping it. Reusing `_build_write_steps`' shape is the whole point — a bespoke two-step sequencer would be a second mechanism doing the same job slightly differently. Brings `partial_failure` into this feature's outcome vocabulary for the first time. Rev 4 removes the plan's one conditional branch: the label step is no longer gated on a declared sensitivity, because `business_area` and `environment` are required and are now labelled too, so the plan is the same three statements for every valid request. |
| Catalog labels: `business_area`, `environment` and `sensitivity` written as tags in one merge write | *Build — real; widened in rev 4 from `sensitivity` alone* | Fits entirely inside the existing `set_catalog_tags` step — no new seam method, no new statement, no change to the plan's order, no change to the audit record. Each field's own name is the tag key, verbatim and unprefixed. Properties were considered, because the table-level applier sends `certification` (the same vocabulary `environment` reuses) to `TBLPROPERTIES`, and rejected: the properties bucket is for pointers that must be re-resolved and for commitments nobody searches by, while these are plain classification values whose whole purpose is to be searchable. `region` is excluded on purpose. |
| `ucmeta provision-catalog <path>` CLI verb | *Build — real, thin wiring* | One more `argparse` subparser with the shared live/profile flags, defaulting to the fake like every other verb. The CLI stays pure wiring; no logic lands here that is not already proven in the module. |
| `.github/workflows/provision-catalog.yml` | *Build — real, copied shape* | The existing changed-path diff, path-glob filter, per-file loop and fork-safe credential branch, pointed at the request folder. Reusing the shape rather than inventing a trigger is the point — a second CI mechanism would be a new seam for no gain. |
| Template carve-out in the workflow's path filter | *Build — real, one line* | The same exclusion both existing workflows already apply to the contract template. Cheap, and its absence is a self-inflicted failure the repository has already learned to avoid. |
| Fork-safe two-branch structure (SC-004-04) | *Build — real, and it is the delivery target* | Two mutually exclusive steps gated on whether a credential is configured, so which one ran is visible in the job's step list rather than only in log text. In this feature the fake branch is the only one that ever runs; the live branch is F-PLATFORM-005's to wire. |
| Release record per outcome, reusing `ReleaseRecord` with two widened field meanings plus one additive optional field | *Build — real (rev 2 decision, amended rev 3)* | One append per run, covering success, no-op, refusal, partial failure and failure. Reuses the existing append-only log and record type rather than starting a second trail: catalog name in the identity field, request-file schema version in the contract-version field. Rev 3 adds one optional `requested_by` field, because who asked is a third fact alongside who approved and who wrote — the same argument F-PLATFORM-003 used to keep approver and machine identity separate. Existing lines still parse; the amendment to rev 2's "field set unchanged" is stated as an amendment in Rules & Constraints rather than glossed. |
| `change_classes.yaml` declaration for the request folder | *Build — real, two lines* | Makes the routing decision explicit rather than correct-by-fall-through. Declared on the slow path, on blast-radius grounds. Two classes suffice here; a possible third rides with F-PLATFORM-005. |
| Scenario-bound unit tests for SC-004-01, -02, -03, -04 and -06 | *Build — real* | Where the claims get proven: the exact ordered list of statements emitted — three of them, for a request that declares a sensitivity and for one that does not alike — the catalog *and* schema existing afterwards, the catalog carrying all three labels under their own field names as tag keys and carrying no `region` tag, the no-op on re-run, the converging labels, the refusal with problems named and zero writes of any kind, the half-provisioned outcome reported as partial rather than rounded, and an audit record for every outcome. Runs offline against the fake, like every other unit test here. SC-004-05 is deliberately unbound — it is F-PLATFORM-005's. |
| Workflow-shape test for the fork-safe branch | *Build — real, small* | The same kind of assertion the existing workflow tests already make for `apply.yml`'s credential gate. Cheap insurance against the one property this feature promises a credential-less reviewer. |

**Handed to F-PLATFORM-005 (drafted 2026-09-20), or skipped outright**

| Component | Verdict | Rationale (one line) |
|---|---|---|
| The live path actually creating a real catalog | *Move to F-PLATFORM-005 (resolved rev 2)* | Not deferred inside this feature — removed from it. Blocked on a privilege decision, not on code: the command and the flag would be identical; what is missing is an identity permitted to run it. SC-004-05 is retained here as that feature's starting scenario. |
| A metastore-level creation grant for `ucmeta-ci-apply` | *Move to F-PLATFORM-005 — a security decision, not a build step* | Widens the machine identity's blast radius from "vandalise three tables' metadata" to "create namespaces in the metastore", against a feature whose whole premise was narrowness. Explicitly not added to the existing grant script by this feature, and no implementer of this feature is authorised to add it. |
| A separate, provisioning-only identity | *Move to F-PLATFORM-005 — the alternative to the row above* | Preserves least privilege by function, at the cost of a second credential to store, document and rotate. The better production answer and the more expensive one; named so the hand-off is a choice between two live options rather than an absence. |
| Catalog deletion or any lifecycle operation beyond creation | *Skip — named in Out of Scope* | A provisioning tool that can also destroy is a materially different security object. Create-only — with the catalog's labels as its one named exception, covering three fields through one merge write since rev 4 — is a deliberate property of this feature, not a missing one. |
| Drift/reconciliation between a request file and the catalog it made | *Skip — named in Out of Scope* | Real and useful; a separate feature with its own detection semantics. This feature re-runs an idempotent plan, converges the three labels and changes nothing else. |
| Region-to-storage-location mapping, and region as a catalog tag | *Skip — undemonstrable in this environment; tag excluded on purpose in rev 4* | Needs storage credentials, external locations and a regional metastore topology the Free Edition workspace does not have. Region stays recorded and unenacted, exactly as contracts already treat it — and stays off the catalog when `business_area` and `environment` went on, because a searchable region label would imply placement behaviour that does not exist. |
| Business-area validation against a controlled registry | *Skip — the source does not exist* | Presence-checked only. The ownership half of this concern is already carried by the business-application identifier, which does resolve against a real registry. |
| Additional schemas, any table, and any grant inside the new catalog | *Skip — narrowed in rev 3, not deleted* | Exactly one schema is created, the one the request names. Beyond that the schema arrives empty and nobody is granted access to anything — a genuine remaining gap between "a catalog and a schema exist" and "the team can use them", named rather than glossed. |
| Quota, naming policy and cost controls | *Skip — named in Out of Scope* | Real production requirements, none built, none pretended. |
| ADR-010 | *Write when approved, not before* | The decisions worth recording are listed in Dependencies. Writing the ADR before the feature is approved would record a decision nobody has made. |

## Open Questions

No rows remain open as of revision 2, and revision 3 opened none: the four fields it added were
settled in conversation before they reached this document, and the decisions they forced — the
three-method seam shape, the label exception to create-only, and the additive audit field — are
recorded in Rules & Constraints as decisions rather than parked here as questions. Resolved rows
are kept rather than deleted, following the convention F-PLATFORM-001 and F-PLATFORM-003 already
set: the reasoning behind a settled decision is the expensive part to reconstruct later, and two
of these are decisions a reviewer is likely to ask about directly. The document stays `draft` —
resolving these questions was part of hector's review, not approval to build.

| Question | Owner | Due | Status |
|----------|-------|-----|--------|
| Does the trigger stay "any push to main that touches a request file" (added or modified alike, idempotent by construction), or narrow to newly-added files only? The recommendation is to keep it as written — it matches the existing workflows exactly, and idempotent creation makes a modified file a harmless no-op — but the narrower filter is a one-flag change and better matches the literal phrasing "only triggers when there is a document inside the folder", so the choice is recorded rather than assumed. | hector | 2026-09-19 | *resolved: any push, for now.* Stays as drafted — added and modified request files treated identically. Recorded deliberately as a placeholder rather than a final position: it is the broader, simpler option, chosen because it matches every other workflow in the repository and because idempotent creation makes the extra breadth harmless. Narrowing to added-only (`--diff-filter=A`) remains a legitimate revisit, and a later change should read as the plan working rather than as overturning a settled rule. |
| Is `region` required or optional? Recommendation: optional, since nothing enacts it and a required field that changes no behaviour trains people to fill in fields that do not matter. The counter-argument is realism — a production request would certainly require it, and leaving it optional makes the demo's request file slightly less convincing as a stand-in for a real one. | hector | 2026-09-19 | *resolved: optional.* The recommendation confirmed as the decision, on its own reasoning: nothing in this feature's scope enacts region, and a required-but-inert field teaches a habit that outlives the field's inertness. It stays declared and recorded so the shape is right when something eventually does enact it. |
| Does the provisioning audit record reuse the existing release-record shape with its dataset-identity field carrying a catalog name and its contract-version field carrying the request-file version, or does it get a record type of its own? Recommendation: reuse, and widen the documented meaning of those two fields — one audit trail is worth more than two tidier ones, and every consumer of the log today reads it as a list of "things that were changed, by whom, with what outcome", which a catalog creation genuinely is. The counter-argument is that widening a field's meaning to fit a second use is how shared shapes rot, and a distinct record type costs little. Flagged rather than decided because it changes an artifact three features already depend on. | hector | 2026-09-19 | *resolved: reuse `ReleaseRecord`, widen the two field meanings.* No second record type. The field set is unchanged, so nothing that reads the log today breaks; only the documented meaning of the identity and version fields widens. The counter-argument is accepted rather than dismissed and written into Rules & Constraints as a named cost: the widening is a deliberate documented act, and a third kind of thing wanting into this log is the signal to stop widening and split the type properly. |
| Does the live path — the metastore-level grant decision, the identity choice, and the first real catalog created against the workspace — happen inside this feature once the minimal version is proven, or as a separate F-PLATFORM-005? Recommendation: separate, on the same grounds F-PLATFORM-003 separated its own layers — approving a demo mechanism and approving a privilege widening are different decisions and should not ride on one approval. Deciding this also settles whether the request folder ought to have a third change-routing class of its own rather than being filed under the existing platform-change class. | hector | 2026-09-19 | *resolved: separate — F-PLATFORM-005, drafted 2026-09-20.* The grant decision, the identity choice, the live branch of the workflow and the first real catalog all leave this feature entirely. F-PLATFORM-004 is now unambiguously fake-client-only: no live path, disabled or otherwise. SC-004-05 is retained here as the scenario F-PLATFORM-005 starts from, and ADR-009's amendment obligation travels with it. The third change-routing class question rides along to that feature; the existing two-class declaration is correct and sufficient for what this feature builds. |

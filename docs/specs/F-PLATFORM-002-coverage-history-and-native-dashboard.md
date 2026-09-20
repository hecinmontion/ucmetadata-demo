---
id: F-PLATFORM-002
title: Coverage history as a table — plus a Unity-Catalog-native dashboard over it
status: in-progress
owner: hector
approvers: []
created: 2026-09-18
last-updated: 2026-09-18
---

# Feature: Coverage history as a table — plus a Unity-Catalog-native dashboard over it

> *Scope of this document.* This is our internal planning artifact, the same as F-PLATFORM-001,
> and it is not shipped into the `uc-metadata-platform` repo. Its relationship to that repo's
> own documentation is, however, different from F-PLATFORM-001's in one respect worth stating
> up front: this feature genuinely produces a decision that belongs in the candidate-facing
> `docs/` folder. Choosing Databricks' native AI/BI Dashboards over a bolted-on second
> observability tool is exactly the kind of technology choice an ADR exists to record, so
> ADR-008 is a *deliverable of this feature*, not planning-only content. The spec plans; the
> ADR ships.

## Business Context

The prototype already publishes coverage, and that was the right first move — the gap has to be
visible before anyone will close it. But the way it is published today is a point-in-time
artifact: a coverage run computes a report, writes it to a JSON file, and a script renders that
one file into an HTML page. The next run overwrites the file. Every number the page shows is
true, and none of it has a yesterday. That is fine for the thing the static page was built for —
a reviewer with no Databricks account seeing a dataset flip to covered — and it is not what
production observability is.

The diagnosis is narrow and worth stating plainly: *the problem is not how the number is
rendered, it is that the number is a file rather than a table.* Every question a platform team
actually asks about coverage is a question about change over time — is this team's coverage
rising or flat, did the gate we introduced last month move anything, which datasets have been
stuck uncovered for three months, did coverage go up while the outcome measure went sideways.
None of those are answerable from a document that is overwritten on every run, no matter how
good the rendering is. They are all trivially answerable from an append-only table with one row
per dataset per run. So the substance of this feature is the table; the dashboard is what the
table makes possible, not the other way round.

Given a table, the dashboard question becomes a tool choice, and for this specific organisation
shape the answer follows from things that are already true about this project rather than from
tool preference. Three of them. First, the data already lives in Unity Catalog, so a dashboard
built on Databricks' own AI/BI Dashboards inherits Unity Catalog's grants directly: whoever can
read the coverage table can see the dashboard, and there is no second permission system to keep
in sync with the first. Bolting on an external tool such as Grafana means standing up a second
identity and authorisation surface next to the one the platform already governs, and a
governance prototype whose own observability sits outside its governance model is arguing
against itself. Second, this project's whole posture is GitOps — contracts are files, change
classes are a checked-in declaration, approvals are code owners, applies happen on merge. An
AI/BI Dashboard is a JSON definition that lives in the repository and moves through the same
pull-request path, so it extends the existing pattern instead of becoming the one exception to
it. Third, the credential rule: no long-lived personal access tokens anywhere. A native
dashboard queries the warehouse as the viewer, through the workspace's own OAuth identity; an
external tool needs a service credential minted, stored and rotated somewhere, which is exactly
the thing this project has spent effort not having. Grafana is the better answer for a shop with
a heterogeneous metric estate and an existing Grafana practice. This is not that shop.

The last thing this feature does is refuse to trade one audience for another. The static page
exists because the interview panel must be able to clone the repo and see coverage on a laptop
with no Databricks account at all, and that requirement has not changed. So this is additive: the
static page stays exactly as it is, and the native dashboard stands beside it as the thing that
answers the production question.

## Stakeholders
- Owner: hector
- Approvers: hector (self-approving; this is a solo interview submission)
- Last reviewed: 2026-09-18

## Revision History
| Rev | Date         | Author | Change |
|-----|--------------|--------|--------|
| 1   | 2026-09-18   | hector | Initial draft. Splits the production-observability answer out of F-PLATFORM-001's `dashboard/app.py` verdict, which settled a static page and deliberately said nothing about time series. Records the "the metric needs to be a table, not a file" diagnosis, the AI/BI-Dashboards-over-Grafana reasoning for this org shape, the additive-not-replacement constraint on the existing static dashboard, an append-only-and-never-pruned position on history rows for removed or renamed datasets, unbounded retention for the prototype with the production rollup named but not built, and four open questions — the dashboard construction method (genuinely unresolved), Free Edition's AI/BI availability, the history table's granularity, and whether dashboard sharing mirrors the `CODEOWNERS` split. |
| 2   | 2026-09-18   | hector | Resolved the Free Edition availability question: confirmed live via `databricks lakeview list`/`create` against the real workspace and warehouse — a genuine `dashboard_id` and `.lvdash.json` path were returned for a minimal probe, then trashed. The dashboard half of this feature is no longer environment-gated. Updated the corresponding Open Questions row and the AI/BI Dashboard build-verdict row to reflect this; the construction-method question is unchanged and remains the one thing still gating work. |
| 3   | 2026-09-18   | hector | Resolved the remaining three open questions. Construction method: route (a), iterate against the live API, with route (c) (manual UI build, export, commit) as the named fallback if iteration cannot produce a verifiably correct definition. History granularity: one row per dataset per run only, no pre-aggregated summary rows. Dashboard visibility: mirrors `CODEOWNERS` in the honest, no-row-filtering sense — any team with read access sees every team's coverage, which is the deliberate transparency choice, not a limitation. Zero open questions remain; ADR-008 is being written next. |
| 4   | 2026-09-18   | hector | Both halves built. Coverage-history table + write path: bootstrapped for real, live-verified across two real runs (six rows, append-only, simulated label carried through). Along the way, a real CI-breaking bug was found and fixed outside this feature's own scope — `pytest`'s `pythonpath` was missing the repo root, so the exact command `.github/workflows/validate.yml` runs (`uv run pytest ...`) failed to collect `test_dashboard.py`, invisible until now because local testing happened to go through `python -m pytest` instead. AI/BI Dashboard: built via route (a) exactly as decided, every dataset's SQL verified standalone first, definition created and published against the real workspace with zero errors, committed at `dashboards/coverage.lvdash.json` with a tested redeploy script. Updated the dashboard build-verdict row to *real, built and published*. |

## Users & Roles

- *Platform engineer* — owns the coverage history table, its write path, and the dashboard
  definition. Reads the dashboard to answer "is coverage moving", which is the question the
  static page cannot answer.
- *Data producer (data team member)* — reads their own team's coverage trend and sees whether
  their contract work is visible in the aggregate. Writes nothing here.
- *Data steward / data office* — reads coverage trend across teams as the standing evidence that
  the metadata programme is or is not working. This is the audience the "coverage went up, did
  anything get better" pairing is aimed at.
- *Interview panel (for the prototype specifically)* — unchanged from F-PLATFORM-001 and
  explicitly protected by this feature: must be able to clone the repo and run the full loop,
  including the static coverage page, on a laptop with no Databricks account. The panel never
  needs the native dashboard to understand the design; they see it demonstrated, they do not run
  it.
- *Dataset owner (as a viewer of the native dashboard)* — sees the dashboard only if Unity
  Catalog already grants them read on the underlying table. Visibility is a consequence of an
  existing grant, never a separately-administered dashboard permission.

## Behaviour

A coverage run does everything it does today, and then one more thing: it records what it found.

The run computes coverage exactly as before — fill rate per dataset across the same dimensions,
per-team aggregates, the certification-versus-evidence check, and at least one outcome measure
carrying its simulated label. It still writes that result out as a document, and the static page
still renders that document. Nothing in that path changes.

In addition, the run appends its findings to a durable coverage-history table in the catalogue:
one row per dataset per run, stamped with when the run happened and which run it belongs to.
Appended, never overwritten and never edited. A dataset that was uncovered in March and covered
in April has two rows that disagree, and both are correct — that disagreement is the entire
product. The same run also records the outcome measure it published, carrying forward the
"this figure is simulated" label into the table so the caveat survives the trip and cannot be
lost between the report and a chart.

The history table is a first-class catalogued object, not a side file. It lives in the same
metastore as the datasets it describes, which means it is discoverable, queryable by anyone who
can already query the platform, and governed by the same grants as everything else. Whoever can
read it can chart it; whoever cannot, cannot.

On top of that table sits a dashboard built with the platform's own native dashboarding — the
same product a Databricks shop already uses for every other business question. It queries the
history table live, so it is current whenever someone opens it, with no publishing step and no
copy of the data anywhere else. It shows coverage over time overall and per team, which datasets
are currently uncovered and how long they have been, and the outcome measure beside the fill
rate with its simulated label intact. Its definition is a file in the repository and changes to
it go through the same review path as any other change of its class, so the dashboard is
versioned and reviewable rather than being a thing someone clicked together once and nobody can
reconstruct.

The static page is untouched and keeps working exactly as before, with no credentials, no
network and no account. This is a guarantee rather than a happy accident: the two surfaces read
the same computed result, and the history table and the native dashboard are strictly additional
consumers of it. Someone who clones the repository and runs the loop offline gets the same page
they got before this feature existed. The trade this deliberately makes is that the offline
reviewer sees one snapshot and the native dashboard sees the trend — two audiences, two
surfaces, one computation, and no pretence that either one replaces the other.

Honesty about what the trend actually shows at this size is part of the behaviour, not a
footnote. With two or three contracts, a coverage trend is a demonstration of a mechanism, not a
finding. The dashboard says what it is.

## Glossary

- *Coverage history*: the append-only record of what every coverage run found — one entry per
  dataset per run. The durable thing this feature adds. Distinct from *coverage*, which is the
  single-run figure F-PLATFORM-001 already defines.
- *Coverage run*: one execution of the coverage computation, scheduled or manual, identified so
  that every entry it produced can be grouped and ordered against other runs.
- *Point-in-time report*: the existing single-run coverage document. Still produced, still
  rendered by the static page, and now also the input to a history entry.
- *Static coverage page*: the existing generated HTML file. Zero-credential, offline, one
  snapshot. Protected by this feature, not replaced by it.
- *Native dashboard*: a dashboard built with the data platform's own dashboarding product,
  querying the catalogue directly, governed by the catalogue's own grants, and defined by a file
  kept in version control.
- *Current estate*: the set of datasets the most recent coverage run saw. The correct scope for
  any "what is our coverage now" question — as opposed to every dataset that has ever appeared
  in history, which includes ones that no longer exist.
- *Historical record*: an entry for a dataset that no longer exists in the catalogue. Still
  true about the moment it describes, never deleted, and deliberately excluded from
  current-estate figures rather than pruned from the table.
- *Retention*: how long history entries are kept and at what granularity. Named here because a
  table that grows on every run forever is a decision, not a default.

## Scenarios

Conventions for binding tests to scenarios:
- *Backend (pytest)*: `@pytest.mark.scenario("SC-002-01")`, fallback `test_..._sc_002_01`.
- *End-to-end demo*: scenario ID in the test name and in the walkthrough script.

### SC-002-01 — Happy path: two runs become a trend

- *Given* a coverage history table exists in the catalogue and is empty
- *And* three datasets have contracts, one of which is missing its description and is therefore
  not fully covered
- *When* a coverage run executes, and then a producer fills in the missing description through
  the normal review and apply path, and a second coverage run executes
- *Then* the history table holds one entry per dataset per run — two runs' worth, with the
  earlier run's entries unchanged by the second
- *And* the dataset that gained its description reads as not covered in the first run's entries
  and covered in the second
- *And* the native dashboard, queried after the second run, shows overall coverage rising between
  the two runs and attributes the rise to the correct team
- *And* the outcome measure recorded for each run is still marked as simulated wherever it is
  displayed
- *And* the point-in-time report and the static page produced by the second run are identical in
  form to what they would have been before this feature existed

### SC-002-02 — Edge case: a dataset disappears between runs

- *Given* the history table holds entries for a dataset from several earlier runs
- *And* that dataset has since been deleted from the catalogue, or renamed, so the next coverage
  run does not see it under the name it used before
- *When* the next coverage run executes
- *Then* the run records entries only for the datasets it actually saw, and writes no entry for
  the vanished one
- *And* the vanished dataset's earlier entries remain in the table exactly as written — they are
  not deleted, not backfilled with a "removed" entry, and not rewritten to point at a new name,
  because each one is a true statement about the run it belongs to
- *And* the dashboard's current-coverage figures are scoped to the most recent run, so the
  departed dataset neither counts against present-day coverage nor silently vanishes from
  history
- *And* a rename appears in history as one dataset's entries ending and another's beginning, with
  no claim that the two are the same dataset — correlating them needs a stable dataset identity
  this prototype does not have, and that limitation is stated on the dashboard rather than
  guessed around
- *And* nothing about this case requires a human to prune the table

### SC-002-03 — Guarantee: the static page still works with no Databricks account at all

- *Given* a reviewer who has cloned the repository on a laptop with no Databricks account, no
  credentials configured, no authenticated CLI profile and no network access to any workspace
- *When* they run the loop in its default offline mode and then render the static coverage page
- *Then* the coverage computation completes and writes its point-in-time report, using the
  in-repo fake catalogue exactly as before
- *And* the static page renders from that report alone and shows every section it showed before
  this feature existed, including the simulated-outcome-measure callout
- *And* no step attempts to reach a warehouse, write a history entry, or read the history table,
  and nothing in the run warns, degrades or exits non-zero on account of history publishing
  being unavailable
- *And* the static renderer's input remains the single-run report, so it has acquired no
  dependency on the history table, on the catalogue, or on any credential
- *And* an automated test asserts this whole path with no credentials present in the
  environment, so a future change that quietly couples the static page to the history table
  fails a check rather than being discovered by a reviewer who cannot run the demo

### SC-002-04 — Failure case: the history write cannot reach the catalogue

- *Given* a coverage run configured to publish history
- *And* the warehouse is unreachable, the credential has expired, or the history table does not
  exist
- *When* the run executes
- *Then* coverage is still computed and the point-in-time report is still written, because
  publishing history is a step after the measurement, not a precondition of it
- *And* the history publish fails loudly, naming what it could not reach, and does not leave a
  partial run in the table — either every entry for that run is present or none of them are
- *And* the failure is distinguishable from "history publishing was not requested", so a
  scheduled run that silently stopped recording cannot be mistaken for one that was never asked
  to
- *And* re-running publication for the same computed report does not produce a second set of
  entries for a run that already landed

## Data

| Data | Source | Direction | Sensitivity |
|------|--------|-----------|-------------|
| Computed coverage figures per dataset (fill dimensions, column fill rate, certification claim, evidence verdict) | The existing coverage computation | Write (appended to the history table) | Internal |
| Run identity and run timestamp | Generated at coverage-run time | Write | Internal |
| Dataset identity as seen at run time (fully-qualified name, owning team) | Resolved during the coverage run | Write | Internal |
| Outcome measure and its simulated label | The existing coverage computation, from a synthetic fixture | Write (carried into the history table) | Internal |
| Coverage history, read back | The history table in the catalogue | Read (by the dashboard, and by anyone with the grant) | Internal |
| Dashboard definition | Version-controlled file in the repository | R/W (authored by the platform team, reviewed on merge) | Internal |
| Dashboard viewer identity and grants | The catalogue's own permission model | Read (enforced, never duplicated) | Internal |
| Point-in-time coverage report | The existing coverage computation | Write (unchanged) | Internal |

## Rules & Constraints

- *The existing static dashboard is not replaced, not removed, and not modified in a way that
  adds a credential.* `dashboard/app.py` keeps working exactly as it does today: its input stays
  the single-run coverage report, it reaches no network, it requires no Databricks account, no
  authenticated profile and no warehouse, and it stays runnable by anyone who can clone the
  repository. This is a hard rule and the first thing to check when reviewing any change made
  under this feature. The reason is the reason it was built — the interview panel must be able to
  see coverage on their own laptop — and that requirement is unchanged. A change that makes the
  static page depend on the history table, the catalogue, or any credential is a regression of
  this feature's core constraint, not an improvement to it, and SC-002-03 exists to catch it.
- Coverage history is append-only. Entries are never updated, never deleted and never rewritten,
  including when the dataset they describe is renamed or dropped. An entry is a statement about
  a past run, and a past run does not change.
- No pruning of orphaned entries. A dataset that no longer exists keeps its history, and the
  correctness of present-day figures is achieved by *scoping* to the latest run rather than by
  deleting the past. Pruning would make coverage history the one artifact in this project that
  quietly rewrites itself, which is the opposite of everything else here.
- "Current coverage" always means the most recent run's entries. Any figure presented as current
  that is computed over the whole table is wrong, because it includes datasets that no longer
  exist.
- The history publish is a separate step behind one narrow interface, invoked after the coverage
  computation, exactly as the release log is. Coverage computation does not acquire a dependency
  on a warehouse, and a caller with no catalogue access can compute coverage and skip publishing.
  The seam is what keeps the offline path offline.
- Publishing history is off by default in offline runs and on in the scheduled and live paths. It
  is opt-in at the point of invocation rather than inferred from whether a credential happens to
  be lying around.
- A run's entries land whole or not at all. A half-written run in the table is worse than no run,
  because it reads as a real coverage drop.
- The simulated label on any outcome measure survives into the table and into the dashboard. The
  existing rule that no caller may present a simulated figure as observed applies to the native
  dashboard identically to the static page; the dashboard being a different product is not an
  exemption.
- Coverage is never published without at least one outcome measure beside it — the same
  F-PLATFORM-001 rule, restated because a new surface is a new opportunity to break it.
- The native dashboard's authorisation is the catalogue's authorisation. No separate user list,
  no service credential embedded in the dashboard, no second permission system to keep in sync.
  If someone can see a number on the dashboard, it is because they were already granted read on
  the table underneath it.
- No long-lived personal access tokens, for the dashboard or for the history write path. The same
  rule as F-PLATFORM-001's, and the main reason an external dashboarding tool was not chosen.
- The dashboard definition is version-controlled and changes to it are reviewed. A dashboard that
  exists only as workspace state, with no reviewable definition, is not acceptable here — it
  would be the single exception to this project's GitOps posture, sitting in the observability
  layer where auditability matters most.
- The history table is created and owned by the platform team, in a platform-owned schema,
  separate from the data-product schemas the contracts describe. Coverage measurement is platform
  infrastructure, not a data product, and should not sit inside the estate it measures.
- The dashboard reads the table; it does not recompute coverage. There is exactly one coverage
  computation, and every surface renders its output. A dashboard query that re-derives a fill
  rate with its own logic is a second implementation waiting to disagree with the first.

## Non-functional Requirements

Same honest framing as F-PLATFORM-001: this is a spare-time prototype whose job is to make a
design legible, and where a real deployment would need a number, the prototype's target and the
production consideration are stated separately.

- *Performance (prototype)*: publishing one run's history adds a single append to the existing
  coverage run and should not change the demo loop's under-two-minutes budget by more than a few
  seconds, warehouse cold start aside. The dashboard opens and renders inside the time a live
  walkthrough can tolerate — a handful of seconds against a 2X-Small warehouse over a table of a
  few dozen rows.
- *Performance (production consideration, not built)*: with thousands of datasets and daily runs
  the history table grows by thousands of rows a day, which is still trivially small; the
  dashboard's queries would want the table partitioned or clustered by run date so a
  twelve-month trend chart does not scan the whole history.
- *Scale (prototype), and the honest limit of the trend story*: two or three contracts and
  however many runs the demo and the schedule produce — tens of rows, not thousands. This needs
  saying without hedging: at this size the time-series story is *illustrative, not load-bearing*.
  A trend line over three datasets and four runs demonstrates that the mechanism works and that
  the right thing is being recorded; it demonstrates nothing about whether coverage actually
  improves at organisational scale, and no claim to the contrary should appear on the dashboard,
  in the README or in the walkthrough. The argument this feature makes is architectural — the
  metric is durable, queryable and governed — and that argument does not need a convincing
  trend line to stand up. Overclaiming here would undercut the part that is genuinely strong.
- *Retention (prototype)*: unbounded and deliberately so. Every entry from every run is kept, no
  retention job, no rollup, no pruning — at this data volume a retention policy would cost build
  days to save kilobytes, and the append-only-never-pruned position in Rules & Constraints is the
  more interesting thing to be able to defend. What the prototype does owe is knowing what it
  would do next, which is the following bullet rather than silence.
- *Retention (production consideration, not built)*: raw per-dataset-per-run entries kept for a
  bounded window (a year is a reasonable default — long enough for an annual comparison), rolled
  up beyond that into per-team-per-day aggregates so the long trend survives without the row
  count. The rollup is the part that needs designing, because it must preserve the
  "coverage rose while the outcome measure did not" pairing rather than averaging it away. Not
  built, named.
- *Availability*: the coverage run degrades rather than fails. If the catalogue or warehouse is
  unavailable, coverage is still computed and the point-in-time report and static page are still
  produced; only the history publish fails, and it fails loudly with what it could not reach
  named. If the history table is unavailable the native dashboard is simply unavailable, which is
  acceptable precisely because the static page does not depend on it. The offline path has no
  availability dependency at all, by construction.
- *Security*: no long-lived personal access tokens. The history write path uses the same OAuth
  user-to-machine profile as every other catalogue write locally, and would use the automation
  environment's own identity in a scheduled run. The dashboard authorises through the catalogue's
  grants as the viewer, so no credential is embedded in the dashboard definition and none is
  stored in the repository. Coverage history contains no business data — dataset names, team
  names, boolean fill dimensions and a simulated figure — but it is a reasonable map of which
  parts of the estate are poorly governed, which is mildly sensitive reconnaissance, so it is
  treated as internal and grant-controlled rather than open.
- *Regulatory*: none assumed, same as F-PLATFORM-001. No validated or GxP regime is designed
  for. The history table happens to be a durable record of when coverage changed, which would be
  useful evidence under such a regime, but that is an observation and not a design goal.

## Out of Scope

- *Replacing the static dashboard.* Stated in Rules & Constraints as a hard rule and repeated
  here because Out of Scope is where a future implementer looks for permission. There is none.
- *Migrating the static page onto the history table.* Rendering a sparkline into the static HTML
  from a committed history extract was considered and is not built: it would either need a
  credential at render time, which breaks the zero-credential guarantee, or a committed copy of
  the history data, which introduces a second source of truth for the metric this feature exists
  to make single-sourced. Snapshot for the offline reviewer, trend for the dashboard.
- *A retention or rollup job.* Named as a production consideration above; not built, not
  scheduled, not stubbed.
- *Backfilling history from before this feature existed.* There is no historical record to
  recover — the previous coverage runs overwrote their output, which is the entire diagnosis.
  History starts at the first run after this feature lands, and the dashboard will show a short
  history at first. That is the honest state and needs no apology.
- *Stable dataset identity across renames.* A renamed dataset reads as two dataset lineages in
  history. Correlating them needs an identity that survives a rename, which the contracts do not
  currently carry; it is named as a limitation on the dashboard rather than solved.
- *Alerting on coverage regressions.* A dashboard is not an alert. Scheduled queries, thresholds
  and notifications on "team X's coverage dropped" are an obvious follow-on and are not built.
- *Dashboards about the tooling itself.* Unchanged from F-PLATFORM-001: no metrics exporters, no
  operational dashboards about the platform's own health. This feature is a dashboard about
  coverage, which is a product metric, not a tooling metric.
- *An external dashboarding tool, evaluated in code.* Grafana and equivalents are considered and
  rejected in reasoning and in ADR-008; no proof-of-concept is built to compare against, and no
  claim is made that the comparison was made empirically.
- *Row-level or column-level security on the history table.* Access is table-level through
  ordinary grants. Restricting a team to only its own coverage rows is a plausible production
  requirement and is not built.
- *Embedding the native dashboard anywhere.* No iframe into a portal, no public sharing link, no
  scheduled PDF. It is opened in the workspace by someone who has access.
- *Multi-workspace or multi-metastore history.* One table in one metastore. The production shape
  of "coverage across every workspace" is a different problem and is not addressed.

## Dependencies

- *Related features*: F-PLATFORM-001 (this feature consumes its coverage computation and is
  bound by its zero-credential static-dashboard requirement). Likely follow-ons: alerting on
  coverage regression, retention and rollup, per-team row-level access.
- *ADRs*:
  - ADR-008 *Coverage history as a Unity Catalog table, with a native AI/BI dashboard over it* —
    to be written in the prototype repo's `docs/`, and a genuine deliverable of this feature
    rather than planning-only content. The ADR must lead with the diagnosis that the metric being
    a file rather than a table is the actual defect, so that the tool choice reads as a
    consequence rather than a preference. It must record the alternatives and the grounds for
    rejecting them: (a) *keep the JSON file and render history from a committed series of
    reports* — rejected because it makes version history the metric store, which cannot be
    queried, joined or aggregated, and because it puts a growing data artifact in the code
    repository; (b) *an external dashboarding tool such as Grafana over the same table* —
    rejected for this organisation shape on three specific grounds, each traceable to something
    already true here: it needs a second authorisation surface next to Unity Catalog's, which a
    governance prototype should not be the first thing to introduce; it needs a stored service
    credential, which contradicts the no-PATs rule that this project has actually honoured rather
    than merely claimed; and it would be the one part of the system not defined by a
    version-controlled, pull-requested file, in the layer where reviewability matters most. The
    ADR must say plainly that Grafana is the right answer for a heterogeneous metric estate with
    an existing Grafana practice, so the rejection reads as fit-for-this-context rather than as a
    verdict on the tool; (c) *a served web application of our own* — rejected on the same grounds
    F-PLATFORM-001 rejected it for the static page, with the addition that building a charting
    surface a vendor already ships is not a senior signal. The ADR must also record the
    reversibility argument, which is the strongest part of the case: because the durable artifact
    is a Unity Catalog table and not a dashboard, swapping the dashboard for any other tool later
    is a re-point, not a migration — the expensive decision is where the data lives, and that
    decision is made in the direction that keeps every rendering choice cheap. Finally it must
    record what is *not* claimed: that a trend over three datasets proves anything about
    coverage improving, and that the construction method for the dashboard definition was
    settled at decision time (see Open Questions).
- *Code modules*: the table below is the core deliverable of this spec, in the same form as
  F-PLATFORM-001's.

### Build verdicts per component

Principle carried over from F-PLATFORM-001, with one addition this feature needs: *where a
component's build method is genuinely unverified, say so in the verdict rather than in a
footnote.* Two of the components below are well-understood work over patterns already proven in
this repository; one is not, and its verdict says which.

| Component | Verdict | Rationale (one line) |
|---|---|---|
| History-write path in `src/uc_metadata/coverage.py` (or a sibling publisher module it calls) | *Real* | Turning a computed report into appended history entries is the substance of this feature; it reuses the SQL-execution pattern already proven throughout `uc_client.py`, so the risk is low and the work is understood. Invoked after the computation, behind one narrow publish interface, so the offline path stays offline — the same discipline as `release_log.publish_release_record(...)`. |
| The coverage history table and its bootstrap DDL (a platform-owned schema, e.g. `workspace.platform.coverage_history`) | *Real* | The durable artifact the whole feature rests on and the thing that makes every rendering choice reversible. Created by a checked-in bootstrap step so the workspace stays rebuildable from the repository, consistent with F-PLATFORM-001's disposable-workspace rule. Exact granularity is an open question below; that the table exists and is append-only is not. |
| Publish-history invocation (`ucmeta coverage` flag plus a step in `.github/workflows/coverage.yml`) | *Real, minimal* | History that only gets written when someone remembers is not history. Opt-in at the point of invocation — on in the scheduled and live paths, off in the offline default — so publishing is never inferred from whether a credential happens to be present. |
| Offline-path fake for the history writer (`fake_uc.py`-backed) | *Real interface, fake behind it* | Unit tests must be able to assert the exact entries a run would append without a network, and the seam stays honest by having two implementations rather than one. The same argument that kept `fake_uc.py` alive in F-PLATFORM-001. |
| The AI/BI Dashboard definition (`.lvdash.json` in the repository) | *Real, built and published* | Built via route (a): every dataset's SQL verified standalone against the real `coverage_history` table first, then the full definition created and published against the real workspace — both calls succeeded with zero errors. The API's own normalisation (rewriting a single `query` string into `queryLines`, among other things) supplied real schema signal no documentation gave. Committed at `dashboards/coverage.lvdash.json`, redeployed via `scripts/deploy_coverage_dashboard.sh` (create and update paths both tested for real). Honest limit, stated in `dashboards/README.md`: CLI/API round-tripping proves the definition is valid and queryable, not that it visually renders correctly — that needs one look in the workspace before presenting. |
| Dashboard version control and workspace sync | *Real for the file, best-effort for the sync* | The definition file living in the repository and moving through review is the load-bearing claim and is achievable regardless. Hosting it in a Databricks Git folder so the workspace object and the repository are the same artifact is the stronger demonstration and depends on what the Free Edition workspace supports; if it does not, the file stays authoritative in the repository and the workspace copy is documented as created from it. |
| Simulated-label carry-through (history entries and dashboard) | *Real, small* | F-PLATFORM-001's one semantic rule for the static renderer — no caller may present a simulated figure as observed — now has a second surface to hold it. Cheap to build, and the exact kind of thing that gets lost when a number moves into a chart, which is why it is a named component rather than an assumed behaviour. |
| Regression test for the zero-credential static path (SC-002-03) | *Real* | The hard rule of this feature needs a mechanical guard, not a sentence. A test that computes coverage and renders the static page with no credentials in the environment is what stops a future change coupling the page to the table. Cheap now, and the only thing that makes the guarantee enforceable rather than aspirational. |
| ADR-008 in the prototype's `docs/` | *Real — a shipped deliverable* | The AI/BI-over-Grafana choice is exactly the kind of decision `docs/` exists for, and it is the artifact a panel is most likely to read. Named as a dependency the same way F-PLATFORM-001 named ADR-001 through ADR-007, with its required content spelled out above. |
| `dashboard/app.py` (the existing static page) | *Unchanged — protected, not extended* | Listed deliberately with a verdict of *no change*, so that "this component is in the blast radius and must come out identical" is recorded rather than inferred. Its input stays the single-run report; it gains no credential, no network call and no dependency on the history table. |
| Dashboard sharing and permissions | *Described, resting on real grants* | Authorisation is Unity Catalog's, which is the whole argument for the native tool, so nothing needs building for it to be true. Whether the dashboard's visibility mirrors the `CODEOWNERS` team split or stays platform-team-only is an open question; either way the mechanism is existing grants and not a new permission system. |
| Live dashboard in the walkthrough | *Real, live, with a rehearsed fallback* | Hector demonstrates the dashboard in his own workspace, on his own laptop and network — the same posture F-PLATFORM-001 settled for the live demo. The static page is the fallback and needs no rehearsal because it is the path that cannot fail. A screenshot of the dashboard committed to the repository covers the case where the workspace is unreachable on the day. |
| Retention / rollup job | *Skip (declared only)* | Unbounded retention is the prototype's deliberate position; the production rollup shape is named in Non-functional Requirements and not built. |
| Alerting on coverage regression | *Skip (named in Out of Scope)* | Obvious follow-on, not this feature. A dashboard is not an alert, and half an alerting path invites questions about a layer that is not being argued. |
| Backfill of pre-feature history | *Skip (impossible by construction)* | The old runs overwrote their own output; there is nothing to recover. Worth listing so the short initial history reads as expected rather than as a bug. |

## Open Questions

These must be resolved before the corresponding component is built. The first is the one that
actually gates work.

| Question | Owner | Due | Status |
|----------|-------|-----|--------|
| How is the AI/BI Dashboard definition actually constructed? | hector | 2026-09-18 | *resolved: route (a), construct the JSON against the API and iterate.* Chosen as the easiest route available without adding tooling: no browser-automation capability is confirmed in this environment (route b), and iterating against the live API follows the exact empirical-verification discipline already proven in this project (the `quote_literal` fix, the demo-data seeding) — try an input, read back what the API actually normalised or rejected, adjust. Route (c) (build once by hand in the UI) stays the named fallback if iteration cannot produce something that renders correctly and there is no way to verify that from the CLI alone; if that happens, the dashboard is built manually once, exported, committed, and the export step documented, exactly as (c) describes. All three routes, including the two not chosen, are recorded with their trade-offs in ADR-008. |
| Are AI/BI Dashboards and the `lakeview` API actually available and usable on a Databricks Free Edition workspace with a 2X-Small serverless warehouse? | hector | 2026-09-18 | *resolved: yes, confirmed live.* `databricks lakeview list -p ucmeta` returned a real (empty) list, not an error, and `databricks lakeview create` against warehouse `66fca89a60cb0837` returned a genuine `dashboard_id`, a real `.lvdash.json` workspace path, and the API's own normalisation of a minimal input (it added `"pageType": "PAGE_TYPE_CANVAS"` unasked — one real data point on the undocumented schema). The probe dashboard was trashed immediately after, no residue left. This closes the fallback branch entirely: the dashboard half of this feature is not blocked by the Free Edition environment, only by the still-open construction-method question below. |
| What exactly is a history entry — one row per dataset per run only, or also a run-level summary row and/or per-team rows? | hector | 2026-09-18 | *resolved: one row per dataset per run only.* No pre-aggregated run-level or per-team summary rows — every aggregate (per-team, per-run, overall) is derived at query time from the same normalised rows, which is what keeps "exactly one coverage computation" true rather than giving the dashboard a second place to disagree with `coverage.py`. The exact column shape for the fill dimensions (separate booleans vs. one structure) is left as an implementation detail for whoever builds the table's DDL, not a further open question. |
| Does the dashboard's visibility mirror the `CODEOWNERS` team split, or is it platform-team-only? | hector | 2026-09-18 | *resolved: mirrors the `CODEOWNERS` split, in the honest sense the spec already named — not per-team row filtering (Out of Scope excludes that), but read access granted the same way `CODEOWNERS` grants review access: any team with read on the coverage history table sees the whole dashboard, every other team's coverage included. That transparency is the point, not a limitation to apologise for — it is what keeps the visibility half of the forcing-function story (peer-comparable coverage) intact for the grandfathered estate, the same argument F-PLATFORM-001 already relies on. Row-level scoping stays out of scope, unchanged. |

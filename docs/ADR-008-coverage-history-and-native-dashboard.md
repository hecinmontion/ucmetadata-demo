# ADR-008: Coverage history as a Unity Catalog table, with a native AI/BI dashboard over it

- **Status:** Accepted; table and publish step built (`workspace.platform.coverage_history`,
  `coverage_history.py`, `ucmeta coverage --publish-history`, live-verified with two real runs).
  The dashboard definition (`.lvdash.json`) is a separate, later phase and is not built yet —
  `dashboard/app.py` is unchanged and stays that way
- **Date:** 2026-09-18
- **Decider:** hector
- **Affects:** `src/uc_metadata/coverage.py` (a publish-history step behind one narrow interface),
  a coverage-history table in a platform-owned schema, a checked-in `.lvdash.json` dashboard
  definition, `.github/workflows/coverage.yml`; `dashboard/app.py` explicitly unchanged

## Context

Start from the diagnosis, because the tool choice everyone reaches for first is downstream of it.

Coverage is already computed and already published: `ucmeta coverage` writes a report and
`dashboard/app.py` renders that report into a static page. That was the right first move — ADR-007
leans on coverage published per team as the standing pressure on the grandfathered estate, and the
gap has to be visible before anyone will close it. But **the defect is not how the number is rendered, it
is that the number is a file rather than a table.** The next run overwrites the report. Every
figure on the page is true and none of it has a yesterday.

Every question a platform team actually asks about coverage is a question about change over time.
Is this team's coverage rising or flat. Did the gate we introduced last month move anything. Which
datasets have been stuck uncovered for three months. Did coverage go up while the outcome measure
went sideways. None of those are answerable from a document that is overwritten on every run, no
matter how good the renderer is; all of them are trivially answerable from an append-only table
with one row per dataset per run. So the substance of this decision is the table. The dashboard is
what the table makes possible, not the thing being chosen.

Given a table, the dashboard becomes a tool choice, and for this organisation shape the answer
follows from three things that are already true in this repository rather than from tool taste.
The data already lives in Unity Catalog, so a dashboard built on Databricks' own AI/BI Dashboards
inherits Unity Catalog's grants directly and there is no second permission system to keep in sync.
This project's whole posture is GitOps (ADR-003, ADR-006) — contracts are files, change classes
are a checked-in declaration, approvals are code owners, applies happen on merge — and an AI/BI
Dashboard is a JSON definition that can live in the repository and move through the same
pull-request path. And the credential rule from ADR-004 is real rather than aspirational: there is
no personal access token anywhere in this project, and a native dashboard queries the warehouse as
the viewer through the workspace's own OAuth identity, so it needs none.

One requirement is not negotiable and constrains everything below: the interview panel must be
able to clone this repository and see coverage on a laptop with no Databricks account at all. That
is why the static page exists and it has not changed. So this decision is additive.

## Decision

**Coverage history is a Unity Catalog table. The dashboard over it is Databricks' native AI/BI
Dashboards, defined by a file in this repository.** The static page stays exactly as it is.

- A coverage run does everything it does today, and then appends what it found to a durable
  coverage-history table in a platform-owned schema — one row per dataset per run, stamped with
  the run and when it happened. Appended, never overwritten, never edited, never pruned. A dataset
  that was uncovered in March and covered in April has two rows that disagree and both are
  correct; that disagreement is the entire product.
- The publish is a separate step behind one narrow interface, invoked *after* the computation, the
  same shape as `release_log.publish_release_record(...)`. Coverage computation acquires no
  dependency on a warehouse. Publishing is opt-in at the point of invocation — on in the scheduled
  and live paths, off in the offline default — never inferred from whether a credential happens to
  be lying around. A run's rows land whole or not at all, because a half-written run reads as a
  real coverage drop.
- "Current coverage" always means the most recent run's rows. Datasets that have left the estate
  keep their history and are excluded by *scoping*, not by deletion.
- The dashboard reads the table; it does not recompute anything. There is exactly one coverage
  computation and every surface renders its output.
- `dashboard/app.py` is untouched: its input stays the single-run report, it reaches no network, it
  needs no account, and a regression test asserts that whole path with no credentials present in
  the environment. A change that couples the static page to the history table is a regression of
  this decision, not an extension of it.

Availability on this workspace is settled rather than assumed. `databricks lakeview list` returned
a real (empty) list and `databricks lakeview create` returned a genuine `dashboard_id` and
`.lvdash.json` workspace path against the Free Edition workspace and its 2X-Small warehouse on
2026-09-18; the probe was trashed immediately. Free Edition is not a blocker.

### The construction method for the dashboard definition

This ADR records a second real decision, because *how* the definition gets authored was genuinely
open when the first half was settled. The widget and chart schema inside `serialized_dashboard` is
not publicly documented in enough depth to hand-construct with confidence, so building one blind
risks shipping a dashboard that exists and does not render, with no cheap way to find out. Three
routes were available:

- **(a) Construct the JSON against the live `lakeview` API and iterate** — send a definition, read
  back what the API normalised, rejected or silently added, adjust, repeat until the definition is
  correct.
- **(b) Drive the workspace UI with browser automation** — build the dashboard programmatically
  through the interface, then export the known-good definition.
- **(c) Build it once by hand in the workspace UI, export it, commit the export, and document the
  export step** so the definition in the repository stays authoritative and reproducible.

**Chosen: (a).** It needs no new tooling — browser automation is not confirmed available in this
environment, so (b) would mean buying a capability before knowing it exists — and it is the same
empirical-verification discipline this project has already used where documentation was
insufficient: `quote_literal`'s backslash-escaping behaviour, found and fixed by running statements
against the real warehouse rather than by reading about its literal parsing; the semantics ADR-004
settled by experiment; the demo-data seeding. Try it against the real system, read back what
actually happened, do not guess from documentation alone. The API's own normalisation is evidence
about the schema and it is free to collect; the first probe already produced one data point by
adding `"pageType": "PAGE_TYPE_CANVAS"` unasked.

**(c) is the named fallback, not a consolation.** If iteration cannot produce a definition that is
*verifiably* correct — because there is no way to see the thing render from the CLI alone — then
the dashboard is built by hand once in the UI, exported, committed, and the export step documented.
The load-bearing claim is that the definition is a reviewed file in this repository, and (c)
satisfies that claim identically; only the authoring ergonomics differ. What would not be
acceptable is a dashboard existing solely as workspace state, which would make the observability
layer the single exception to this project's GitOps posture — in exactly the place auditability
matters most.

### Who can see the dashboard

Read access mirrors `CODEOWNERS` in the sense that matters, and it is worth being precise about
which sense that is. It does **not** mean per-team row filtering: no row-level or column-level
security is built, and restricting a team to only its own coverage rows is explicitly out of scope.
It means grant-based access, granted the same way `CODEOWNERS` grants review access — **any team
with read on the coverage-history table sees every team's coverage, not just its own.**

That is a deliberate transparency choice, not an oversight in the permission model. ADR-007
grandfathers the existing estate on purpose and names visibility — coverage published per team —
as the standing pressure on it. Visibility that each team can only see about itself is
not social pressure, it is a private report card, and it does not do the job ADR-007 is relying on
it to do. Peer-comparable coverage is the mechanism. Narrowing the dashboard to "your team's rows
only" would quietly remove half of the forcing function while looking like better hygiene.

The cost is stated rather than implied: coverage history is a reasonable map of which parts of the
estate are poorly governed, which is mildly sensitive reconnaissance. It is therefore internal and
grant-controlled rather than open — whoever can read the table can see the dashboard, whoever
cannot, cannot — and the mechanism is existing Unity Catalog grants, never a new permission system.

### History granularity

One row per dataset per run, and nothing else. No pre-aggregated run-level rows, no per-team
summary rows. Every aggregate — per team, per run, overall — is derived at query time from the same
normalised rows. This is what keeps "exactly one coverage computation" true: a stored per-team
total is a second place for a number to be computed, and therefore a second place for it to
disagree with `coverage.py`. The exact column shape for the fill dimensions (separate booleans
versus one structure) is an implementation detail for whoever writes the DDL, not a further
decision. The simulated label on the outcome measure travels into the table and out onto the
dashboard: the existing rule that no caller may present a simulated figure as observed does not
get an exemption for being a different product.

## Consequences

- The metric becomes a first-class catalogued object: discoverable, queryable by anyone who can
  already query the platform, and governed by the same grants as everything else. "Which datasets
  have been uncovered for three months" stops being a design question and becomes a `WHERE` clause.
- **Reversibility, which is the strongest part of this case.** The durable artifact is a Unity
  Catalog table, not a dashboard. Swapping AI/BI Dashboards for Grafana, for a notebook, for a
  vendor tool nobody has heard of yet, or for whatever the target organisation already standardises
  on is a *re-point*, not a migration: the new tool queries the same table and the old dashboard
  definition is deleted. The expensive decision here is where the data lives, and it is made in the
  direction that keeps every rendering choice cheap. Note that the rejected alternatives invert
  this — with the metric stuck in a JSON file, every rendering choice is a data-migration project.
- Two surfaces, one computation. The offline reviewer sees a snapshot and the dashboard sees the
  trend, and neither pretends to replace the other. Rendering a sparkline into the static page was
  considered and rejected: it would need either a credential at render time, breaking the
  zero-credential guarantee, or a committed copy of the history data, which reintroduces the second
  source of truth this decision exists to remove.
- The coverage run degrades rather than fails. If the warehouse is unreachable, coverage is still
  computed and the report and static page are still produced; only the publish fails, loudly,
  naming what it could not reach — and distinguishably from "history publishing was not requested",
  so a scheduled run that silently stopped recording cannot be mistaken for one that was never
  asked to.
- History starts at the first run after this lands. There is nothing to backfill, because the
  earlier runs overwrote their own output — which is the diagnosis restated. The dashboard will
  show a short history at first and that needs no apology.
- Retention is unbounded and deliberately so: no retention job, no rollup, no pruning. At tens of
  rows a retention policy would cost build days to save kilobytes. What production would need is
  named rather than silent — raw rows for a bounded window, rolled up beyond it into
  per-team-per-day aggregates, with the rollup designed to preserve the "coverage rose while the
  outcome measure did not" pairing rather than averaging it away.
- A renamed dataset reads as two dataset lineages in history, because correlating them needs a
  dataset identity that survives a rename and the contracts do not carry one. That limitation is
  stated on the dashboard rather than guessed around.
- A dashboard is not an alert. Thresholds and notifications on "team X's coverage dropped" are the
  obvious follow-on and are not built.

**What this decision explicitly does not claim.** Two things, both worth saying before a reviewer
has to ask.

First, **a trend over three datasets proves nothing about coverage improving.** At this size the
time-series story is *illustrative, not load-bearing*: it demonstrates that the mechanism works and
that the right thing is being recorded, and it demonstrates exactly nothing about whether coverage
improves at organisational scale. No claim to the contrary belongs on the dashboard, in the README
or in the walkthrough. The argument being made here is architectural — the metric is durable,
queryable and governed — and that argument does not need a convincing trend line to stand up.
Overclaiming would undercut the part that is genuinely strong.

Second, **the choice of tool was settled before the construction method was.** When the first half
of this decision was taken, how to author a correct `.lvdash.json` was an open question and was
recorded as one rather than papered over; it is resolved above, with a named fallback. That
sequence is the honest one — the table-versus-file diagnosis does not depend on knowing how to
draw a chart — but it is recorded here so that "we knew all along" is not implied.

## Alternatives considered

- **(a) Keep the JSON report and render history from a committed series of reports.** Rejected on
  two grounds. It makes version-control history the metric store, and a metric store that cannot be
  queried, joined or aggregated is not one — "which datasets have been uncovered for three months"
  becomes a script that walks commits and re-parses documents, and joining coverage to anything
  else in the catalogue becomes impossible. And it puts a growing data artifact in a code
  repository: every run adds a file forever, in the place this project keeps contracts and
  tooling. Cheapest to build, and it would have left the diagnosis — the metric is a file — fully
  intact while looking like it had been addressed.
- **(b) An external dashboarding tool such as Grafana over the same table.** Rejected for this
  organisation shape, on three grounds each traceable to something already true here. It needs a
  second authorisation surface next to Unity Catalog's, with its own user list to keep in sync — and
  a governance prototype whose own observability sits outside its governance model is arguing
  against itself; it should not be the first thing to introduce a parallel permission system. It
  needs a stored service credential, minted and rotated somewhere, which contradicts the no-PATs
  rule of ADR-004 that this project has actually honoured rather than merely claimed: there is no
  long-lived token anywhere in it today. And it would be the one part of the system not defined by
  a version-controlled, pull-reviewed file, in the layer where reviewability matters most — the
  single exception to ADR-003 and ADR-006. To be plain about what this is not: **Grafana is the
  right answer for a heterogeneous metric estate with an existing Grafana practice**, where one
  pane of glass over warehouses, clusters and application metrics is worth a second auth surface
  and a service credential. This is not that estate. The rejection is fit-for-this-context, not a
  verdict on the tool — and by the reversibility argument above, an organisation that already runs
  Grafana can point it at the same table and delete the `.lvdash.json`.
- **(c) A served web application of our own.** Rejected on the same grounds ADR-003 rejected a
  served application for the static page: it would need hosting, authentication and securing before
  it showed anyone a single number, and the review, history and access model it would have to
  invent are things the existing tooling gives away. With one addition specific to this decision —
  building a charting surface a vendor already ships, and ships integrated with the catalogue's
  own grants, is not a senior signal. It is the expensive way to demonstrate the weakest part of
  the design.
- **(d) A dashboard clicked together in the workspace and left there.** Rejected, and named as an
  alternative rather than a non-option because it is what actually happens by default. It gives the
  same charts for none of the work, and it makes the dashboard the one artifact in this project
  that nobody can review, diff or reconstruct. The definition being a file is the claim; see the
  construction-method section for how it is honoured either way.

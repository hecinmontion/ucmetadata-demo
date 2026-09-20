# UC Metadata Platform — what we have

A working prototype for improving metadata quality and coverage on a Databricks + Unity Catalog
platform, where data teams own their datasets and a platform team provides shared guardrails. It
ships **two solutions**, both real and both load-bearing — not one primary feature with an
afterthought bolted on:

- **The harvester** (F-PLATFORM-001) turns an existing, undocumented dataset into a governed,
  reviewed, coverage-measured asset.
- **The catalog provider** (F-PLATFORM-004/005) turns catalog creation itself — today an
  out-of-band, hand-run administrative action — into the same reviewed-file-then-merge governance
  model as everything else.

Metadata is a versioned, reviewed file. An AI drafter removes the blank-page cost of writing it.
A human approves every judgment before anything reaches the catalogue. Coverage is published so
the gap is visible rather than assumed — the same discipline both solutions share.

Design decisions for both solutions live under [`docs/adrs/`](docs/adrs/) as ADRs, listed below.
How each solution is actually put together — its components, what runs where, what talks to what
— is described in [`docs/architecture/`](docs/architecture/). The planning specs behind both
solutions — business context, Given/When/Then scenarios, the source of every `SC-NNN-NN` a test
or docstring cites — are archived in [`docs/specs/`](docs/specs/), a dated snapshot from the
project's own planning process rather than a live document; see that folder's own README for what
that distinction means.

| ADR | Decision |
|---|---|
| [ADR-001](docs/adrs/ADR-001-contracts-not-catalog-editing.md) | Contracts in version control, not catalogue editing |
| [ADR-002](docs/adrs/ADR-002-ai-proposes-humans-approve.md) | AI proposes, humans approve |
| [ADR-003](docs/adrs/ADR-003-files-and-change-requests-not-a-ui.md) | Files and change requests, not a user interface |
| [ADR-004](docs/adrs/ADR-004-real-free-tier-workspace-behind-a-client-shaped-interface.md) | A real free-tier Unity Catalog workspace, behind a client-shaped interface |
| [ADR-005](docs/adrs/ADR-005-central-contract-repository.md) | One central contract repository, split later if volume proves it |
| [ADR-006](docs/adrs/ADR-006-two-tracks-for-change.md) | Two tracks for change: content edits vs. schema/tooling changes |
| [ADR-007](docs/adrs/ADR-007-gate-provisioning-and-grants.md) | Gate provisioning and grants, not schema changes (the forcing function) |
| [ADR-008](docs/adrs/ADR-008-coverage-history-and-native-dashboard.md) | Coverage history as a Unity Catalog table, with a native AI/BI dashboard over it |
| [ADR-009](docs/adrs/ADR-009-ci-only-apply-a-machine-identity-and-a-tested-boundary.md) | CI-only apply: a machine identity for the write path, and a tested boundary on the human's |
| [ADR-011](docs/adrs/ADR-011-a-second-machine-identity-so-the-first-one-did-not-have-to-grow.md) | A second machine identity, `ucmeta-ci-provision`, for catalog creation — so `ucmeta-ci-apply`'s least-privilege claim didn't have to widen |

## The problem, and two solutions

On a Unity Catalog platform where data teams own their own data products, most datasets end up
with almost no useful metadata. The cause is not laziness and not missing tooling: describing a
dataset is **decoupled from every workflow a producer is already obliged to complete.** You can
publish a table, cut a release and get access granted without describing a single column. So
"go tag your tables" campaigns spend goodwill and leave nothing durable behind — and the bill is
paid downstream, by consumers who cannot find datasets, cannot tell two similar tables apart,
re-ingest a source that already exists, and cannot judge whether data is trustworthy or sensitive.

This prototype attacks that cause with two solutions, not one solution and an addendum.

### The harvester (F-PLATFORM-001)

Turns an existing, undocumented dataset into a governed, reviewed, coverage-measured asset, in
three moves:

1. **Put the metadata on the path the producer already walks.** The design: a new dataset should
   not be provisioned without a valid contract, and no consumer read grant should be issued for a
   dataset that has none — both are steps the platform genuinely owns, so authoring metadata stops
   being an extra errand and becomes part of getting the thing the producer came for. What's
   actually built in this codebase is the machine-readable verdict (`validate.py`) that gate would
   call on every provisioning/grant request; wiring it into a real Terraform provisioning pipeline
   is the target organisation's job, not this prototype's — ADR-007 names exactly where that
   boundary sits, and "What's mocked" below calls it out as described, not enforced.
2. **Remove the blank-page cost.** An AI drafter proposes a description, a business-term link and
   a sensitivity classification for every column. It proposes; it never publishes (ADR-002).
3. **Make the gap visible.** Coverage is computed and published per team, next to an outcome
   measure, so "coverage went up" can be checked against "anything got better".

Where the platform does not own a choke point, it does not pretend to: a schema change inside a
producer's own pipeline repository is **detected as drift, never blocked** — see ADR-007 for why
detect-only is the honest position there.

Stated plainly: this solution attacks the actual cause of poor metadata — decoupling from the
producer's obligations — not the symptom, and it works on the estate that already exists. Harvest
reads facts for free, an AI drafter removes the blank-page cost, a human clears every judgment
field, and apply writes only on merge.

### The catalog provider (F-PLATFORM-004/005)

All three moves above assume a catalog to describe already exists. Today, bringing a catalog into
existence at all is an out-of-band, unreviewed action — "ask the platform team to run
`CREATE CATALOG` by hand" — with no review, no audit trail, and no relationship to the contract
discipline above. F-PLATFORM-001's own Business Context named this as somebody else's problem: the
provisioning/grant gate's build verdict there describes "the centrally-owned Terraform
provisioning flow and grant issuance" as things that "are not the prototype's to build or
simulate — they belong to the target organisation's platform." F-PLATFORM-004/005 is this
prototype deciding to build a piece of it after all.

A team writes a nine-field request file, a human reviews it in a change request, a merge
provisions it live against the real workspace, and the audit trail names who asked and who
approved — the same reviewed-file-then-merge model as everything else here, applied one level
earlier than a dataset.

Stated plainly: this solution extends the "no dataset without a contract" forcing function one
step earlier, to "no catalog without a reviewed request" — closing a gap the original design
explicitly named as out of scope, not adding a fourth move onto the three moves above. It is a
second, smaller loop alongside the harvester's, not a variant of it: no propose stage (a catalog
request has no AI-drafted judgment field) and no coverage stage (nothing to compute a fill rate
over) — see [`docs/architecture/catalog-provisioning.md`](docs/architecture/catalog-provisioning.md)
for exactly how it's built.

## This repo runs two ways

**Local, credential-free.** Every verb defaults to `FakeUCClient`, the in-repo fake catalogue,
whose fixture tables mirror the live workspace's schemas exactly. No Databricks account, no API
key, nothing to authenticate — this is what CI runs by default (`validate.yml`, `coverage.yml`,
and `apply.yml`/`provision-catalog.yml` on any fork with no CI credentials configured) and what a
reviewer gets on a fresh clone, deterministic every time. `propose` is the one exception — it
makes a real AI call — and it is clearly marked wherever it appears below.

**Real, against an actual workspace.** Every verb also takes `--live` (and `--profile`, default
`ucmeta`), which swaps the fake for `RealUCClient` against a real Databricks Free Edition
workspace over `databricks-sdk`. Both solutions were live-verified this session, each behind its
own machine identity — deliberately two separate identities, not one doing both (ADR-009,
ADR-011):

- `ucmeta-ci-apply` — writes table/column metadata (comments, tags, properties). Holds nothing
  else: no create or drop privilege anywhere.
- `ucmeta-ci-provision` — creates catalogs and schemas and tags them. Holds the metastore-level
  `CREATE_CATALOG` privilege and nothing on any table.

Each identity has its own re-runnable grant script — `scripts/provision_ci_apply_identity.sh` and
`scripts/provision_ci_provision_identity.sh` — so the workspace side of this project is rebuildable
from the repository, not just described in prose.

**To replicate this yourself:**

1. `databricks auth login` for a personal profile (OAuth user-to-machine, never a personal access
   token) — see ADR-004 and `scripts/seed_demo_data.sql` for the workspace this targets.
2. Run both grant scripts, as an account admin, to create the two service principals and their
   grants.
3. Mint each identity's credential and store it as its own set of GitHub Actions secrets. This
   step stays manual by design; see [`docs/ci-service-principal.md`](docs/ci-service-principal.md)
   and [`docs/ci-service-principal-provision.md`](docs/ci-service-principal-provision.md) for the
   exact steps and the reasoning for keeping them manual.

Note that `--live` apply no longer fully works from the author's own laptop, on purpose. Since
2026-09-19 three of the four demo tables (`customers`, `orders`, `campaigns` — see
`scripts/provision_ci_apply_identity.sh`) are owned by `ucmeta-ci-apply` and the author's personal
identity holds `SELECT` on them and nothing else, so a local `ucmeta apply --live` against any of
those three returns `partial_failure`: the comment and property writes are refused by Unity
Catalog naming the missing `MODIFY` privilege, while tag writes still land via a metastore-admin
bypass that no grant can switch off. That split outcome — what is enforced, what is not, and why —
is ADR-009. `marketing.leads` (added after that provisioning script was written) is the one demo
table this boundary does **not** yet cover — it is still owned by the author's own identity, a
known, not-yet-closed gap rather than an oversight (the fix is re-running the provisioning script
with a fourth table name added to its list).

## Quick example

Both solutions are CLI verbs of the same tool:

```bash
# The harvester: validate a reviewed contract, then apply it on merge.
ucmeta validate contracts/analytics/customers.yaml
ucmeta apply contracts/analytics/customers.yaml --approved-by "your name" --dry-run

# The catalog provider: plan a catalog into existence from a reviewed request.
ucmeta provision-catalog catalog-requests/_template.yaml --approved-by "your name" --dry-run
```

See [`docs/examples/`](docs/examples/) for the full set of 8 runnable, real-output demos (4 fake,
4 live) covering both solutions.

## Approach

One human-readable contract file per dataset is the only authoring surface. Facts the catalogue
already knows are harvested into it and never hand-typed; judgments are drafted by the AI, cleared
by a named human, reviewed in a change request, and applied to the live catalogue only on merge.
Two gates are meant to make that loop start at all (provisioning, grants — the design ADR-007
argues for, resting on a real verdict function but not yet wired into any real provisioning
pipeline) and two more actually make it safe today (the unreviewed-marker refusal, and
apply-on-merge-only, both enforced and demonstrated). Everything is files, a six-verb CLI, and CI.

```
                       ┌──────────────────────────────────────────────┐
                       │       Unity Catalog (live workspace)         │
                       └──────────────────────────────────────────────┘
                            │ facts (columns, types, partitioning)   ▲
                            │                                        │ writes: comments,
                            ▼                                        │ tags, properties
        ┌───────────┐   ┌───────────┐   ┌────────────┐   ┌───────────┴───┐
        │  harvest  │──▶│  propose  │──▶│  validate  │──▶│     apply     │
        │ skeleton  │   │ AI drafts │   │  the gate  │   │ on merge only │
        └───────────┘   └───────────┘   └────────────┘   └───────────────┘
              │               │                │                 │
              ▼               ▼                │                 ▼
        contracts/*.yaml  ai_proposed:true     │          release_log.jsonl
        (the one          markers on every     │          (append-only:
         authoring         drafted field       │           what, who, when,
         surface)                              │           outcome)
                                               ▼
                                   ┌──────────────────────────┐
                                   │ coverage  ──▶ dashboard  │
                                   │ fill rate per team +     │
                                   │ one outcome measure      │
                                   └──────────────────────────┘

  FORCING FUNCTIONS (design — not wired         GATES (why it is safe, today)
  into a real gate in this repo; see below)     · any ai_proposed marker left → apply refuses,
  · no contract  → no dataset provisioned         whole contract, no partial writes
  · no contract  → no consumer read grant       · change requests may validate and dry-run,
    (both would call validate()'s verdict —       never apply; apply is wired to merge on main
     that verdict is real, the calling gate     · every change request prints every planned write
     is not built — ADR-007)                    · content edits take the fast path, schema/tooling
  · grandfathered estate: drift + coverage,       changes the slow one — routed by file path,
    never a retroactive block                     never argued per change request (ADR-006)
```

The diagram above is the *describe-a-dataset* loop. A second, smaller loop exists alongside it,
for bringing a catalog into existence in the first place:
`catalog-requests/*.yaml` → `provision-catalog` → the same live-or-fake `UCClient` seam →
`release_log.jsonl`. It has no propose or coverage stage of its own — a catalog request has no
AI-drafted judgment field and nothing to compute a fill rate over — so it doesn't earn a second
box this size; see "Full command reference" below for the `provision-catalog` step's actual
commands, and `docs/architecture/catalog-provisioning.md` for how it's built.

## Full command reference

No Databricks account or API key is needed for any command below except `propose` — see
"This repo runs two ways" above for why, and for how to point any of them at the real workspace.

```bash
git clone https://github.com/hecinmontion/ucmetadata-demo.git
cd ucmetadata-demo

# Set up the environment — pick ONE of the two options below.

# Option A — uv (this is exactly what CI runs)
uv sync --extra dev
source .venv/bin/activate

# Option B — pip
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# The test suite: offline, no credentials, no network.
pytest -m "not uc_live and not llm_live"
```

With the environment active, `ucmeta` is on your PATH. Every command below also works as
`./cli/ucmeta <verb> ...` (a no-install wrapper around the same `main()`), or as
`uv run ucmeta <verb> ...` without activating anything.

```bash
# 1. HARVEST — read a table's facts out of the catalogue into a skeleton contract.
#    Judgment fields are left blank on purpose; placeholders are unmistakable.
ucmeta harvest workspace.analytics.orders --ba-id BA-30587 -o /tmp/orders-skeleton.yaml

# 2. PROPOSE — the AI drafter fills the blanks, marking every value ai_proposed: true.
#    The only step that needs a key (ANTHROPIC_API_KEY) and the only one that costs money;
#    it prints its model, token counts, dollar cost and latency.
ucmeta propose /tmp/orders-skeleton.yaml -o /tmp/orders-proposed.yaml
#    ...or edit a contract in place:  ucmeta propose <contract> --in-place

# 3. VALIDATE — the automated checks, plus every catalogue write a merge would perform.
#    Exit code 0 on pass, 1 on failure: this is the CI gate, and the verdict the
#    provisioning/grant gates would call.
ucmeta validate contracts/analytics/customers.yaml   # PASS  (reviewed and complete)
ucmeta validate contracts/analytics/orders.yaml      # FAIL  (grandfathered, pre-review)

# 4. APPLY — write the contract to the catalogue. Refuses the whole contract if it does
#    not validate; --dry-run prints the plan and writes nothing.
ucmeta apply contracts/analytics/customers.yaml --approved-by "your name" --dry-run
ucmeta apply contracts/analytics/customers.yaml --approved-by "your name" \
  --log-path /tmp/release_log.jsonl
#    (drop --log-path to append to the repository's own release_log.jsonl)
#    Re-run it: apply is idempotent in effect — the same statements are issued and
#    nothing observable changes (COMMENT ON / SET TAGS / SET TBLPROPERTIES all re-run
#    cleanly). Verified against the live workspace, not just the fake, which starts
#    from a clean in-memory catalogue in every new process.

# 5. COVERAGE — fill rate per dimension and per team, plus one (clearly labelled
#    simulated) outcome measure. Then render it as a static page.
ucmeta coverage contracts/ -o /tmp/coverage_report.json
python dashboard/app.py /tmp/coverage_report.json -o /tmp/coverage.html

# 6. PROVISION-CATALOG — bring a catalog into existence (its first schema, plus
#    business_area/environment/sensitivity as catalog tags), from a reviewed
#    request file rather than hand-run administration. Same discipline as apply:
#    refuses the whole request, writing nothing, if it fails validation;
#    --dry-run prints the plan and writes nothing.
ucmeta provision-catalog docs/examples/fixtures/example-catalog-request.yaml \
  --approved-by "your name" --dry-run
#    Copy catalog-requests/_template.yaml to author a real request of your own.
#    --live --profile ucmeta-ci-provision provisions for real, through the one
#    metastore-level privilege this project's automation didn't hold before
#    F-PLATFORM-005 (CREATE_CATALOG) — see ADR-011 for why that's a second
#    identity, not a widened ucmeta-ci-apply.
```

Also worth opening, because they are the artifacts rather than the prose:
`contracts/analytics/customers.yaml` (the happy path), `contracts/marketing/campaigns.yaml`
(well-covered but quality-red — fully reviewed, yet fails `validate()` because its `silver` claim
outruns its own DQ evidence), `contracts/analytics/orders.yaml` (grandfathered, still failing
validation for a different reason — genuinely pre-review), `contracts/marketing/leads.yaml` (the
opposite extreme from `orders`: never harvested until this write-up, still carrying every
placeholder harvest left it with — the lowest-scoring dataset coverage shows, and the concrete
example behind the "can fill rate ever be 0%?" question answered below), `change_classes.yaml` (the
two-track declaration) and `release_log.jsonl`. [`docs/examples/`](docs/examples/) captures eight of
these paths as runnable demos with real, actually-captured output: `01`-`04` for
`provision-catalog` (fake and live, success and refusal), `05`-`08` for the harvest → document →
apply → validate loop.

## What's mocked

The rule this build followed: *mock the systems you cannot touch; build the primitives the design
depends on; never mock the thing being evaluated — and when a system turns out to be reachable for
free, touch it rather than imitating it.*

| Component | Status | Notes |
|---|---|---|
| Contract model + JSON Schema (`models.py`, `contracts/_schema/`) | **Real** | The primitive everything else rests on, with a backwards-compatibility test. |
| `uc_client.py` (`UCClient` protocol + `RealUCClient`) | **Real, against a real workspace** | Thin `databricks-sdk` translation: it translates, it does not decide (ADR-004). |
| `uc_client.py`'s three catalog-provisioning methods (`create_catalog`, `create_schema`, `set_catalog_tags`) | **Real, against a real workspace** | The first operations this platform performs on something other than an already-existing table (`CREATE CATALOG` / `CREATE SCHEMA` / `ALTER CATALOG ... SET TAGS`, through the same statement-execution seam every other write uses). Live-verified twice, once per real catalog. |
| `fake_uc.py` | **Fake, test-only** | Not the product's target. Exists so tests are offline and deterministic, and so the seam has two implementations; a shared contract-test suite runs against both. |
| `harvest.py` | **Real logic, real source** | Ran for real against the live workspace; the three shipped contracts were harvested from it. |
| `propose.py` | **Real (real model, real calls)** | `claude-haiku-4-5`, structured output, masked samples, glossary-grounded term links. Recorded fixtures in CI. Every real call writes a `<name>.audit.json` next to the contract (model, timestamp, both prompts, masked column-level inputs — never raw PII). See the open gap below. |
| `validate.py` | **Real** | Drift, unreviewed markers, placeholder sentinels, and certification-vs-evidence (calls `dq_registry.evaluate_rules` + `coverage.tier_is_supported_by_evidence`). This is why `contracts/marketing/campaigns.yaml` now fails `validate()`/`apply()` — see below. |
| `apply.py` | **Real, real target** | Table comment, column comments, tags, properties. Idempotency and revert-restores proven against live Unity Catalog. |
| `provision_catalog.py` | **Real, real target** | Same validate → refuse-or-plan → execute → log discipline `apply.py` established, reimplemented independently against a catalog request rather than a contract (F-PLATFORM-004 shares nothing with `apply.py` but that discipline, on purpose). A fixed three-statement ordered plan — create catalog, create schema, set catalog tags — idempotent and partial-failure-aware, live-verified end to end as `ucmeta-ci-provision`. |
| `catalog-requests/` + `_template.yaml` | **Real authoring surface** | The second authoring surface, sibling to `contracts/`: one nine-field YAML request per catalog. Two requests shipped and both provisioned live (`data-platform-demo-bronze.yaml`, `data-platform-demo-silver.yaml`) — the second via an actual merged PR, not a hand-run command. |
| `release_log.py` | **Mock writer, real interface, really wired** | Every apply, and every `provision-catalog` run, appends a record. The writer is a local `release_log.jsonl`; the production adapter swaps the writer, not the record's shape. |
| `coverage.py` + `dashboard/app.py` | **Real, minimal** | Fill rate per dimension and team, computed not described. Rendered as a static generated page — no served app to fail live. The static page is unchanged and stays zero-credential (spec F-PLATFORM-002 SC-002-03, mechanically enforced by a test). |
| `coverage_history.py` + `dashboards/coverage.lvdash.json` (**ADR-008**) | **Real, both halves built** | The point-in-time report is now also durable: `workspace.platform.coverage_history`, one row per dataset per run, appended (never `UPDATE`d/`DELETE`d) via `ucmeta coverage --publish-history`, off by default. Bootstrapped by `scripts/bootstrap_coverage_history.sql`, confirmed live with real runs. A native AI/BI Dashboard queries that table — built by iterating against the live `lakeview` API (ADR-008's chosen route), created and published against the real workspace with zero errors, redeployable via `scripts/deploy_coverage_dashboard.sh`. All four widgets are confirmed rendering correctly in the browser. One honest scar: a `table` widget for "coverage by dataset" went through two API-accepted, hand-guessed column-schema definitions that both still failed to render — "Invalid widget definition is imported" — so it was rebuilt by hand through the workspace's own dashboard editor as a bar chart instead, then re-exported from the live dashboard back into `coverage.lvdash.json` to keep the file as source of truth. See `dashboards/README.md`. |
| Outcome measure | **Simulated, labelled** | Computed from `sample_outcome_events.yaml`; every measure carries `simulated=True` and a caveat naming the fixture, so no caller can present it as observed. |
| `owner_registry.py` | **Mock behind a seam** | `resolve_owner(ba_id) -> Owner` over four hard-coded entries. Contracts store only the business-application id pointer, never a copied owner string. |
| `glossary/terms.yaml` + `glossary.py` | **Mock data, real grounding** | Twelve sample terms, loaded and passed to the drafter as context; a proposed term link is dropped unless it resolves to a real entry. At this size the whole glossary fits in the prompt, so there is no retrieval ranking to speak of — that would be the next step at real glossary scale. |
| `dq_registry.yaml` + `dq_registry.py` | **Mock registry, real evaluation** | Six rules with a small predicate grammar, evaluated in Python over sampled rows — one rule language for both clients. No rule-execution engine. |
| `change_classes.yaml` + `change_routing.py` | **Real, enforced** | The two-track split is a glob match over the change request's diff, not a paragraph in this README. |
| CI workflows (`validate`, `apply`, `coverage`, `provision-catalog`) | **Real, fake-backed** | See below. |
| Provisioning / grant gates | **Described, on a real check** | The gates belong to the target organisation's platform. What is built is the machine-readable verdict they would call. |
| Personal-data detection | **Mock, light** | AI proposal plus conservative name/value-shape masking. No compliance-grade classifier. |

One call worth stating here rather than only in a workflow comment: `validate.yml` and
`coverage.yml` always run `ucmeta` against `FakeUCClient`. `apply.yml` is different: it is wired
(ADR-009 Layer 1, `apply.yml` itself, `scripts/provision_ci_apply_identity.sh`) to apply live as
`ucmeta-ci-apply` — a real, least-privileged service principal that owns three of the four demo
tables — whenever `DATABRICKS_CI_HOST` / `DATABRICKS_CI_CLIENT_ID` / `DATABRICKS_CI_CLIENT_SECRET`
are configured as repository secrets; without them (any fork) it falls back to the exact same
apply-on-merge mechanism against `FakeUCClient`, and which branch ran is unmistakable in the job's
own printed output.

**Those three secrets are configured on `hecinmontion/ucmetadata-demo`, and the live branch now
works end to end through GitHub Actions — closed 2026-09-20 (see ADR-009's "What was not yet
working on 2026-09-19, and is now closed" for the full record).** The original 2026-09-19 entry
here described a live-apply run dying around the five-minute mark inside `WorkspaceClient`'s own
auth resolution, not reproducing locally, and left "not root-caused further" as the honest
position at the time — three real merges (naming `auth_type = oauth-m2m`, then `discovery_url`)
hadn't fixed it. What actually closed it, found while diagnosing a similar failure on
`provision-catalog.yml`, was two ordinary, stacked bugs in the stored CI secrets, not the SDK or
the network: `DATABRICKS_CI_HOST` was missing its `https://` scheme (the SDK silently repairs a
bare `host` field internally but passes `discovery_url` through raw, so one malformed secret
produced one working value and one broken one — `Invalid URL '.../oidc/...': No scheme supplied`),
and, revealed only once that was fixed, `DATABRICKS_CI_CLIENT_SECRET` was stale
(`invalid_client: Client authentication failed`, with `DATABRICKS_CI_CLIENT_ID` independently
confirmed correct). Fixing both, a real merge's `apply.yml` run applied both changed contracts
live as `ucmeta-ci-apply` — every write `OK` — in 1m 8s, no five-minute delay at all. Whether this
is the *same* root cause as the original five-minute hang is deliberately not claimed as proven:
today's failures were both fast, clean, immediate errors, not a hang, and GitHub exposes no secret
history to confirm when the host secret actually became malformed. See the ADR for the full,
hedged reasoning.

**`provision-catalog.yml`'s live branch worked the first time, and that contrast with `apply.yml`'s
is itself worth stating plainly rather than letting a reader assume every live path here was
equally shaky.** No five-minute mystery, no stacked secret bugs, nothing to root-cause: the three
`ucmeta-ci-provision` secrets (`DATABRICKS_CI_PROVISION_HOST` / `_CLIENT_ID` / `_CLIENT_SECRET`,
deliberately distinct names from `ucmeta-ci-apply`'s three so one credential can never be pasted
into the other's slot unnoticed) were configured once, correctly, and the first real push to touch
`catalog-requests/` — merging `catalog-requests/data-platform-demo-silver.yaml` — provisioned
`data_platform_demo_silver` live as `ucmeta-ci-provision` on the first try: create catalog, create
schema, set catalog tags, all `OK`, `deployment_status: success`. That is the first time this
mechanism fired from an actual push rather than a hand-run command (a prior hand-run created the
first catalog, `data_platform_demo`, while standing up the identity itself). See ADR-011 for the
identity behind it — a second, provisioning-only service principal holding only the metastore-level
`CREATE_CATALOG` privilege and warehouse `CAN_USE`, deliberately not a widened `ucmeta-ci-apply`,
so ADR-009's least-privilege claim about that identity stays true without a footnote. Both real
catalogs are kept permanently as standing evidence rather than cleaned up — this platform's
provisioning has no delete path, by design — and both already carry real tables documented through
the *existing* harvest → document → apply loop (`pipeline_runs` and `data_quality_checks` inside
`data_platform_demo.demo`, contracts at `contracts/demo/*.yaml`), which is the concrete proof that
the two paths compose rather than living in separate demos.

**AI-proposed content is verified working, deliberately not baked into the shipped contracts.**
`ucmeta propose contracts/analytics/orders.yaml --live` was run for real on 2026-09-19 against a
real `ANTHROPIC_API_KEY` and the live workspace ($0.0038, 4.36s) — the drafter, unprompted, flagged
`orders.state` as ambiguous (order status vs. US state abbreviation), the exact low-confidence
behaviour that column was seeded to test. A second, independent recording
(`tests/fixtures/llm/orders_propose.json`) reproduced the same judgment call, so this is the
model's genuine behaviour, not a scripted demo. Every contract shipped under `contracts/` still
stays human-authored rather than being overwritten with that output: the walkthrough runs
`ucmeta propose` live, in front of the panel, per the original script — real proposal on stage
beats pre-baked in the repo.

Three further gaps were named here in an earlier phase and are now closed, worth recording rather
than quietly deleting:

- **The certification-vs-evidence check is now wired into `validate()`.** It calls
  `dq_registry.evaluate_rules` and `coverage.tier_is_supported_by_evidence`, exactly at the
  integration point a prior phase documented ahead of time. The direct, intended consequence:
  `contracts/marketing/campaigns.yaml`'s `silver` claim is no longer accepted — `validate()` and
  `apply()` both now refuse it, naming the two failing DQ rules by id. That contract is left
  failing on purpose (see its own header comment); coverage measuring fill and not correctness is
  now a caught failure, not only an asserted one.
- **`tests/e2e/demo_scenario.py` is now built.** One scenario file, two modes: the default runs
  entirely against `FakeUCClient`; `--live` runs the same steps against the real Free Edition
  workspace and doubles as confirmation that `workspace.analytics.customers`'s previously-applied
  state is still correct. Runnable directly as a script or collectible under `pytest`.
- **`CODEOWNERS` ships at the repository root.** Per-area review ownership, referenced by
  ADR-003/005/006, keyed on the `contracts/<area>/` layout.

## Trade-offs

Every one of these is a decision with a cost, and the cost is stated rather than implied.

- **GitOps YAML, not a UI** (ADR-003). *Why:* review, approval, history, diff, revert and
  ownership come free from a tool producers already use, and the gate lands where they already
  work. *Cost:* non-engineer authors — stewards, business owners — are shut out, and YAML
  indentation errors are a real class of mistake a form would have prevented. A form that writes
  the same YAML is the deliberate follow-on; the file staying the substrate is what keeps that
  move cheap.
- **The AI proposes, it never publishes** (ADR-002). *Why:* the blank page is the actual barrier,
  but descriptions become the organisation's vocabulary and sensitivity labels drive access — on a
  single global production metastore with no staging tier. *Cost:* a human must clear every marker,
  so the drafter accelerates the work without removing it, and the residual risk moves from model
  error to reviewer fatigue. Rubber-stamping forty markers produces exactly the outcome the rule
  exists to prevent, and nothing here measures review quality.
- **One central contract repository** (ADR-005). *Why:* discoverable contracts, one validation
  pipeline, one place to ship a schema migration — and it is the reversible direction, since
  splitting a folder is mechanical while consolidating N drifted repositories is a project.
  *Cost:* review contention in a shared folder, and producer autonomy that is currently unpaid for.
  The flip trigger is named in advance: sustained change-request queueing in `contracts/`.
- **Two tracks for change, routed by file path** (ADR-006). *Why:* blast radius is asymmetric — a
  content edit affects one dataset, a schema change affects every team's contracts — and a class
  argued per change request is a queue, which is what killed the tagging campaigns. *Cost:* the
  path-pattern declaration has to be maintained; a new platform-owned file under `contracts/` that
  nobody adds to `content_exclude` silently gets the fast path.
- **Gate provisioning and grants, not schema changes** (ADR-007). *Why:* these are the two choke
  points this platform genuinely owns, so the contract rides along on obligations the producer
  already has. *Cost:* an honest hole — a producer's own pipeline can change a schema and the
  platform can only *detect* it (drift, coverage drop, a failing change request), and an existing
  dataset whose owner never needs a new grant is untouched by the gate. The stronger lever, a CI
  check inside each producer's repository, needs cross-team adoption and was deferred, not
  dismissed.
- **Column-level metadata required for new datasets, grandfathered for existing ones.** *Why:* a
  retroactive block would break working pipelines and buy nothing; the estate moves by visibility
  and drift reporting instead. *Cost:* a transitional two-speed state that is genuinely untidy —
  `contracts/analytics/orders.yaml` ships failing validation to prove it is real rather than
  claimed — and no bound on how long the grandfathered tail persists.
- **A real free-tier workspace behind a client-shaped seam** (ADR-004). *Why:* several semantic
  questions (idempotency of `COMMENT ON`, tags absent from the table read, type rendering) were
  settled by experiment rather than by a mock's author guessing. *Cost:* two implementations of the
  seam to keep honest (mitigated by a shared contract-test suite), and zero claim to production
  fidelity — Free Edition is serverless-only, one workspace, three tables, no staging metastore,
  no identity groups.
- **A six-verb CLI over a framework or a service.** *Why:* `argparse`, one entry point, no
  dependency the project does not otherwise need; the same `main()` behind `./cli/ucmeta`, the
  `ucmeta` script and CI. *Cost:* no interactive affordances, and `ucmeta` remains a local tool
  rather than a service anything else can call.
- **A second, provisioning-only machine identity (`ucmeta-ci-provision`), rather than a widened
  `ucmeta-ci-apply`** (ADR-011). *Why:* the alternative was cheaper to build — one grant, no new
  principal, no new credential — but it would have made ADR-009's least-privilege claim about
  `ucmeta-ci-apply` false the moment the grant landed; keeping the two identities' blast radii
  disjoint (`ucmeta-ci-apply` can vandalise three tables' metadata and create nothing anywhere;
  `ucmeta-ci-provision` can create catalogs and touch no table) was judged worth the extra
  identity. *Cost:* a second credential to store and eventually rotate, a second grant script, a
  second document to keep in sync with the first — real overhead for a solo maintainer, and larger
  than planned: the live credential came out with a 30-day lifetime rather than the ~2-year one
  `ucmeta-ci-apply` holds, so this rotation is a real near-term chore, not a theoretical one.

## What I didn't do

Deliberate omissions. Each is a scope decision, not an oversight — and a few are gaps rather than
choices, marked as such.

- **Production-metastore fidelity.** Real Unity Catalog integration is in scope and real; the claim
  that this is the target organisation's environment is not. No scale, no region topology, no
  staging tier, no real identity groups, no governance policies to comply with. The seam is
  evidence that moving is contained, not evidence that it has been done.
- **Freshness observation.** Refresh cadence and SLAs are *declared* in the contract, never
  measured. No table-history introspection, no metrics harvester. Some declared commitments will
  therefore be untrue — an accepted, named gap.
- **Bulk migration tooling for the existing estate.** No mass-backfill runner, no prioritisation
  engine. The migration argument is made in words, not in code.
- **RBAC beyond a code-owners placeholder.** Who may edit and approve which contract is expressed
  as per-area code ownership (`CODEOWNERS`, shipped at the repository root). Production would map
  that to identity groups; that mapping is not built.
- **A discovery or search experience.** Nothing at all, not even a stub page. Discovery is the
  downstream consumer of good metadata, not this feature; a half-built discovery surface would cost
  walkthrough time and invite questions about a layer this prototype is not arguing about.
- **Catalogue-wide discovery of uncontracted tables.** `UCClient` has no `list_tables`/`list_catalogs`
  method — every verb takes an already-known `catalog.schema.table` name, and `coverage.py` only
  ever reads `contracts/`. A table that exists in Unity Catalog with no contract file is therefore
  completely invisible to this tool: not counted, not flagged, not in any report — the two-speed
  rollout's "grandfathered but visible" story (ADR-007) only covers tables someone already chose to
  harvest. Closing this is a real, named gap (a `ucmeta scan --live` reconciliation verb that diffs
  a live catalogue listing against `contracts/`), not a design decision — it just is not built.
- **Provisioning a catalog does not grant anyone access to it.** `provision-catalog` creates a
  catalog and its default schema and nothing else — no `USE_CATALOG`, no `USE_SCHEMA` granted to
  the requesting team automatically, on top of no second schema, no table and no grant of any kind
  inside it (F-PLATFORM-004/005's own Out of Scope names this plainly: "a catalog and a schema
  exist" is not the same as "the team can use them"). This was found live, not reasoned about in
  advance — hector went looking for his own newly-provisioned catalog in the workspace UI and could
  not see it. Closing it needs a grant step this feature deliberately does not build; a genuine
  remaining gap, not a design decision.
- **A prompt-injection test against the drafter.** A hostile column comment or sample value trying
  to steer the proposal is cheap to test and genuinely worth testing. It was deprioritised against
  the core loop, not judged unimportant. The structural defence that *is* present is that the
  drafter cannot publish: a successful injection yields a bad suggestion, not a bad catalogue entry.
  Claiming that makes injection harmless would be overstating it.
- **The producer-repo CI hard-block on uncontracted schema changes.** Deferred, not rejected — it
  is the strongest lever available in principle and it needs every producing team to adopt a check
  in a repository this platform does not own. That is a cross-team negotiation, not a build task.
  Drift detection is the standing answer meanwhile (ADR-007).
- **A real data-quality engine.** Rules come from a small stand-in registry with a deliberately
  tiny predicate grammar, evaluated over sampled rows. No rule scheduler, no scoring engine. The
  certification-vs-evidence check built on top of it is wired into `validate()`, not merely ready
  to be.
- **Business glossary curation.** The glossary is assumed to exist elsewhere and is represented by
  a dozen realistic sample terms used as drafter context.
- **A real central release-log service.** Apply publishes through a real interface; the writer
  behind it is a local append-only file. No retention policy, no tamper-evident storage, no
  cross-team query surface.
- **The platform team's own release process.** The slow path is named and the routing that selects
  it is enforced; the release review, version tagging, migration runner and deprecation windows are
  described, not built.
- **Observability of the tooling itself, lineage capture, multi-region apply paths, and consumer
  feedback routing.** All designed or named, none implemented.
- **A bounded YAML loader.** `Contract.from_yaml` uses `yaml.safe_load`, which has no built-in
  limit on anchor/alias expansion — a maliciously crafted contract file could expand a few KB of
  text into gigabytes in memory ("billion laughs"). `validate.yml` parses every PR's changed
  contracts unattended, before a human looks at them, so this isn't purely theoretical if the
  repository ever accepts PRs from people who haven't already been vetted through `CODEOWNERS`.
  Not built here — the fix is a size/depth-bounded loader (or simply rejecting any contract that
  contains an anchor or alias at all, since contracts have no legitimate use for either).
- **Unicode bidi-control character handling in reviewed text.** Characters like U+202E
  (right-to-left override) can make what a reviewer *sees* in a diff differ from the actual bytes —
  the "Trojan Source" class of attack. This matters specifically because SC-001-03's whole safety
  argument rests on a human genuinely reading what they're clearing the `ai_proposed` marker on.
  Nothing today strips, flags, or rejects these characters in `description`/`note` fields. Not
  built here — the fix is a lint/validate-time check that flags or rejects bidi-control code points
  in any human-reviewable text field.

Both of the above were found, not invented, by an adversarial test pass — deliberately scoped out
rather than fixed, on the judgment that a CODEOWNERS-gated prototype reviewed by people who already
trust each other doesn't need them yet, not on the judgment that they don't matter.

Two process notes, for the same reason everything else here is stated plainly. A stray test
artifact was committed and had to be cleaned up before push (the shipped-contracts commit is
amended for that reason), and the repository's default branch was created as `master` and renamed
to `main` before anything was pushed — both caught locally, and both the sort of thing worth
naming rather than quietly tidying out of the history.

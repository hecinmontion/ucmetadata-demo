# UC Metadata Platform

A working prototype for improving metadata quality and coverage on a Databricks + Unity Catalog
platform, where data teams own their datasets and a platform team provides shared guardrails.

Metadata is a versioned, reviewed file. An AI drafter removes the blank-page cost of writing it.
A human approves every judgment before anything reaches the catalogue. Coverage is published so
the gap is visible rather than assumed.

Design decisions live in [`docs/`](docs/) as ADRs:

| ADR | Decision |
|---|---|
| [ADR-001](docs/ADR-001-contracts-not-catalog-editing.md) | Contracts in version control, not catalogue editing |
| [ADR-002](docs/ADR-002-ai-proposes-humans-approve.md) | AI proposes, humans approve |
| [ADR-003](docs/ADR-003-files-and-change-requests-not-a-ui.md) | Files and change requests, not a user interface |
| [ADR-004](docs/ADR-004-real-free-tier-workspace-behind-a-client-shaped-interface.md) | A real free-tier Unity Catalog workspace, behind a client-shaped interface |
| [ADR-005](docs/ADR-005-central-contract-repository.md) | One central contract repository, split later if volume proves it |
| [ADR-006](docs/ADR-006-two-tracks-for-change.md) | Two tracks for change: content edits vs. schema/tooling changes |
| [ADR-007](docs/ADR-007-gate-provisioning-and-grants.md) | Gate provisioning and grants, not schema changes (the forcing function) |
| [ADR-008](docs/ADR-008-coverage-history-and-native-dashboard.md) | Coverage history as a Unity Catalog table, with a native AI/BI dashboard over it |
| [ADR-009](docs/ADR-009-ci-only-apply-a-machine-identity-and-a-tested-boundary.md) | CI-only apply: a machine identity for the write path, and a tested boundary on the human's |

## Problem

On a Unity Catalog platform where data teams own their own data products, most datasets end up
with almost no useful metadata. The cause is not laziness and not missing tooling: describing a
dataset is **decoupled from every workflow a producer is already obliged to complete.** You can
publish a table, cut a release and get access granted without describing a single column. So
"go tag your tables" campaigns spend goodwill and leave nothing durable behind — and the bill is
paid downstream, by consumers who cannot find datasets, cannot tell two similar tables apart,
re-ingest a source that already exists, and cannot judge whether data is trustworthy or sensitive.

This prototype attacks the cause rather than the symptom, in three moves:

1. **Put the metadata on the path the producer already walks.** The design: a new dataset should
   not be provisioned without a valid contract, and no consumer read grant should be issued for a
   dataset that has none — both are steps the platform genuinely owns, so authoring metadata stops
   being an extra errand and becomes part of getting the thing the producer came for. What's
   actually built in this codebase is the machine-readable verdict (`validate.py`) that gate would
   call on every provisioning/grant request; wiring it into a real Terraform provisioning pipeline
   is the target organisation's job, not this prototype's — ADR-007 names exactly where that
   boundary sits, and the README's "What's mocked" table calls it out as described, not enforced.
2. **Remove the blank-page cost.** An AI drafter proposes a description, a business-term link and
   a sensitivity classification for every column. It proposes; it never publishes (ADR-002).
3. **Make the gap visible.** Coverage is computed and published per team, next to an outcome
   measure, so "coverage went up" can be checked against "anything got better".

Where the platform does *not* own a choke point, it does not pretend to. A schema change inside a
producer's own pipeline repository is **detected as drift, never blocked** — see ADR-007 for why
detect-only is the honest position there.

## Approach

One human-readable contract file per dataset is the only authoring surface. Facts the catalogue
already knows are harvested into it and never hand-typed; judgments are drafted by the AI, cleared
by a named human, reviewed in a change request, and applied to the live catalogue only on merge.
Two gates are meant to make that loop start at all (provisioning, grants — the design ADR-007
argues for, resting on a real verdict function but not yet wired into any real provisioning
pipeline) and two more actually make it safe today (the unreviewed-marker refusal, and
apply-on-merge-only, both enforced and demonstrated). Everything is files, a five-verb CLI, and CI.

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

## Quickstart

No Databricks account and no API key are needed: every verb defaults to the in-repo fake
catalogue (`FakeUCClient`), whose fixture tables mirror the live workspace's schemas
exactly. `propose` is the one exception — it makes a real AI call — and it is clearly marked below.

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
```

**Running against a real workspace.** Every verb takes `--live` (and `--profile`, default
`ucmeta`), which swaps the fake for `RealUCClient` against a real Unity Catalog workspace over
`databricks-sdk`. It expects an already-authenticated Databricks CLI profile
(`databricks auth login` — OAuth user-to-machine, never a personal access token); the repository
holds a profile name and a host, never a secret. Set-up of that workspace is out of scope for this
README — see ADR-004 and `scripts/seed_demo_data.sql`.

**Note that `--live` apply no longer fully works from the author's own laptop, on purpose.** Since
2026-09-19 three of the four demo tables (`customers`, `orders`, `campaigns` — see
`scripts/provision_ci_apply_identity.sh`) are owned by a real service principal
(`ucmeta-ci-apply`) and the author's personal identity holds `SELECT` on them and nothing else, so
a local `ucmeta apply --live` against any of those three returns `partial_failure`: the comment and
property writes are refused by Unity Catalog naming the missing `MODIFY` privilege, while tag
writes still land via a metastore-admin bypass that no grant can switch off. That split outcome —
what is enforced, what is not, and why — is ADR-009. `marketing.leads` (added after that
provisioning script was written) is the one demo table this boundary does **not** yet cover — it is
still owned by the author's own identity, a known, not-yet-closed gap rather than an oversight (the
fix is re-running the provisioning script with a fourth table name added to its list).

Also worth opening, because they are the artifacts rather than the prose:
`contracts/analytics/customers.yaml` (the happy path), `contracts/marketing/campaigns.yaml`
(well-covered but quality-red — fully reviewed, yet fails `validate()` because its `silver` claim
outruns its own DQ evidence), `contracts/analytics/orders.yaml` (grandfathered, still failing
validation for a different reason — genuinely pre-review), `contracts/marketing/leads.yaml` (the
opposite extreme from `orders`: never harvested until this write-up, still carrying every
placeholder harvest left it with — the lowest-scoring dataset coverage shows, and the concrete
example behind the "can fill rate ever be 0%?" question answered below), `change_classes.yaml` (the
two-track declaration) and `release_log.jsonl`.

## What's mocked

The rule this build followed: *mock the systems you cannot touch; build the primitives the design
depends on; never mock the thing being evaluated — and when a system turns out to be reachable for
free, touch it rather than imitating it.*

| Component | Status | Notes |
|---|---|---|
| Contract model + JSON Schema (`models.py`, `contracts/_schema/`) | **Real** | The primitive everything else rests on, with a backwards-compatibility test. |
| `uc_client.py` (`UCClient` protocol + `RealUCClient`) | **Real, against a real workspace** | Thin `databricks-sdk` translation: it translates, it does not decide (ADR-004). |
| `fake_uc.py` | **Fake, test-only** | Not the product's target. Exists so tests are offline and deterministic, and so the seam has two implementations; a shared contract-test suite runs against both. |
| `harvest.py` | **Real logic, real source** | Ran for real against the live workspace; the three shipped contracts were harvested from it. |
| `propose.py` | **Real (real model, real calls)** | `claude-haiku-4-5`, structured output, masked samples, glossary-grounded term links. Recorded fixtures in CI. Every real call writes a `<name>.audit.json` next to the contract (model, timestamp, both prompts, masked column-level inputs — never raw PII). See the open gap below. |
| `validate.py` | **Real** | Drift, unreviewed markers, placeholder sentinels, and certification-vs-evidence (calls `dq_registry.evaluate_rules` + `coverage.tier_is_supported_by_evidence`). This is why `contracts/marketing/campaigns.yaml` now fails `validate()`/`apply()` — see below. |
| `apply.py` | **Real, real target** | Table comment, column comments, tags, properties. Idempotency and revert-restores proven against live Unity Catalog. |
| `release_log.py` | **Mock writer, real interface, really wired** | Every apply appends a record. The writer is a local `release_log.jsonl`; the production adapter swaps the writer, not the record's shape. |
| `coverage.py` + `dashboard/app.py` | **Real, minimal** | Fill rate per dimension and team, computed not described. Rendered as a static generated page — no served app to fail live. The static page is unchanged and stays zero-credential (spec F-PLATFORM-002 SC-002-03, mechanically enforced by a test). |
| `coverage_history.py` + `dashboards/coverage.lvdash.json` (**ADR-008**) | **Real, both halves built** | The point-in-time report is now also durable: `workspace.platform.coverage_history`, one row per dataset per run, appended (never `UPDATE`d/`DELETE`d) via `ucmeta coverage --publish-history`, off by default. Bootstrapped by `scripts/bootstrap_coverage_history.sql`, confirmed live with real runs. A native AI/BI Dashboard queries that table — built by iterating against the live `lakeview` API (ADR-008's chosen route), created and published against the real workspace with zero errors, redeployable via `scripts/deploy_coverage_dashboard.sh`. All four widgets are confirmed rendering correctly in the browser. One honest scar: a `table` widget for "coverage by dataset" went through two API-accepted, hand-guessed column-schema definitions that both still failed to render — "Invalid widget definition is imported" — so it was rebuilt by hand through the workspace's own dashboard editor as a bar chart instead, then re-exported from the live dashboard back into `coverage.lvdash.json` to keep the file as source of truth. See `dashboards/README.md`. |
| Outcome measure | **Simulated, labelled** | Computed from `sample_outcome_events.yaml`; every measure carries `simulated=True` and a caveat naming the fixture, so no caller can present it as observed. |
| `owner_registry.py` | **Mock behind a seam** | `resolve_owner(ba_id) -> Owner` over four hard-coded entries. Contracts store only the business-application id pointer, never a copied owner string. |
| `glossary/terms.yaml` + `glossary.py` | **Mock data, real grounding** | Twelve sample terms, loaded and passed to the drafter as context; a proposed term link is dropped unless it resolves to a real entry. At this size the whole glossary fits in the prompt, so there is no retrieval ranking to speak of — that would be the next step at real glossary scale. |
| `dq_registry.yaml` + `dq_registry.py` | **Mock registry, real evaluation** | Six rules with a small predicate grammar, evaluated in Python over sampled rows — one rule language for both clients. No rule-execution engine. |
| `change_classes.yaml` + `change_routing.py` | **Real, enforced** | The two-track split is a glob match over the change request's diff, not a paragraph in this README. |
| CI workflows (`validate`, `apply`, `coverage`) | **Real, fake-backed** | See below. |
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

**Those three secrets are now configured on `hecinmontion/ucmetadata-demo` (2026-09-19), and the
live branch genuinely does not work yet — a real, open gap, not a hidden one.** Three real merges
to `main`, each gated by CI and each a genuine attempt (not a rehearsed sequence), tried to fix it:
naming `auth_type = oauth-m2m` explicitly, then setting `discovery_url` explicitly after reading
the installed Databricks SDK's own source (`_resolve_host_metadata`, which the SDK's own comment
admits "blocks `Config()` initialization for ~5 minutes when the host is unreachable" when neither
is set). Both attempts still failed the same way: a real live-apply run against
`workspace.analytics.customers` dies around the five-minute mark inside `WorkspaceClient(profile=
"ucmeta-ci-apply")`'s own auth resolution, on this specific GitHub-Actions-to-Free-Edition network
path, in a way that does not reproduce locally against the same credential (confirmed working
in under 2 seconds from a local machine). The credential is not the problem; something about
Databricks SDK auth resolution specifically on a GitHub-hosted runner reaching this workspace is.
Not root-caused further — three ~5-minute CI round-trips chasing SDK internals stopped being time
well spent for this prototype, and the honest position is naming the gap plainly rather than a
fourth guess. The service principal's own credential values are confirmed good: constructing a
client from them locally, under a differently-named local profile (`ucmeta-ci`, not
`ucmeta-ci-apply` — never tested under that exact name outside CI), authenticates in under two
seconds. It is specifically something about auth resolution on a GitHub-hosted runner reaching
this workspace, not the credential.

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
- **A five-verb CLI over a framework or a service.** *Why:* `argparse`, one entry point, no
  dependency the project does not otherwise need; the same `main()` behind `./cli/ucmeta`, the
  `ucmeta` script and CI. *Cost:* no interactive affordances, and `ucmeta` remains a local tool
  rather than a service anything else can call.

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

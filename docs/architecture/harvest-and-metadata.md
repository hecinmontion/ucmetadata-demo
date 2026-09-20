# Architecture: harvest and metadata (F-PLATFORM-001/002/003)

What this document is for: how the metadata-governance system is actually put together — its
components, what runs where, what talks to what — for someone trying to understand or extend it.
For *why* it looks this way, see the [README](../../README.md) and the ADRs linked throughout;
this document's job is the *how*.

## The one seam: `UCClient`

Every module that touches Unity Catalog — `harvest.py`, `apply.py`, `validate.py`,
`dq_registry.py` — depends on one thing: `uc_client.UCClient`, a `Protocol` describing a narrow
read/write surface (get a table's columns/comment/properties/tags; set a table or column comment,
properties, or tags). Nothing above that seam knows or cares which of two implementations it was
handed:

- `RealUCClient` — a thin `databricks-sdk` translation layer against the live Databricks Free
  Edition workspace. It translates, it does not decide: it turns `UCClient` calls into real SQL
  DDL (`COMMENT ON TABLE/COLUMN`, `ALTER TABLE ... SET TBLPROPERTIES/SET TAGS`) and returns the
  exact SQL string it ran (or, with `dry_run=True`, the string it *would* run, executing nothing).
- `FakeUCClient` — an in-memory stand-in with the same Protocol, the default backend for every
  `ucmeta` verb and every unit test. Fixture tables mirror the live workspace's schemas exactly.

Neither implementation imports the other; both import the Protocol only, so `harvest.py`/
`apply.py`/`validate.py` can take either as a constructor argument with no branching on which one
they got. A shared contract-test suite (`tests/unit/test_uc_client_contract.py`) runs the same
assertions against both, so the fake cannot silently drift from real Unity Catalog semantics
(idempotency of `COMMENT ON`, tags never appearing on a raw table-read response, `type_text` vs.
`type_name`, and so on — see ADR-004 for how those questions were settled by experiment). This
seam is why `--live` is a single flag on every verb rather than a second code path per verb.

## The one authoring surface: `Contract`

`models.py`'s `Contract` (backed by a JSON Schema under `contracts/_schema/`) is the only place a
dataset's metadata lives — one YAML file per dataset under `contracts/<area>/`. It draws one hard
line: harvested facts (column names, SQL types, nullability, partitioning) are never
hand-authored, and judgment fields (descriptions, business-term links, PII/sensitivity
classifications) are always either blank, marked `ai_proposed: true`, or cleared by a named human
— never silently guessed. Four dataset-level fields (`description`, `refresh`, `retention_days`,
`certification`) have no harvested source at all; `harvest.py` fills them with unmistakable
placeholders (`PLACEHOLDER_DESCRIPTION`, the `bronze` tier) rather than a caller-supplied value or
a guess, so a contract can always be constructed but a placeholder can never be mistaken for a
real declaration.

## The five-stage pipeline

```
harvest → propose → validate → apply → coverage
```

- **`harvest.py`** reads a table's facts through `UCClient.get_table` and writes a skeleton
  `Contract` — judgment fields left `None`, ready for a human or the drafter to fill.
- **`propose.py`** is the AI drafter: given a skeleton, it proposes a description, business-term
  link, and PII/sensitivity classification for every column, marking every value it touches
  `ai_proposed: true`. It never writes to Unity Catalog and never publishes anything (ADR-002) —
  its only output is a more-filled-in YAML file plus an audit record (`<name>.audit.json`: model,
  timestamp, both prompts, masked inputs) next to it. Column samples are masked before they reach
  the model; term links are dropped unless they resolve against `glossary/terms.yaml`.
- **`validate.py`** is pure checks, no writes: drift (does the contract's column list still match
  the catalogue), unreviewed markers (any `ai_proposed` flag still set), placeholder sentinels
  (any of harvest's four unmistakable placeholders still present), and certification-vs-evidence
  (a `silver`/`gold` claim with no passing DQ rule attached fails). All four run independently and
  every failure is collected, not just the first. This is also the machine-readable verdict a real
  provisioning/grant gate would call (ADR-007) — built here, not wired into an actual gate, since
  that gate belongs to the target organisation's platform.
- **`apply.py`** writes a contract to the live catalogue, and only after calling `validate()`
  itself and refusing the whole contract on any failure — it never trusts a caller to have
  validated first. `plan_apply` (dry-run) and `apply` (real) share one step-builder, so the SQL a
  reviewer sees printed before merge and the SQL that actually runs are provably the same code
  path, differing only in the `dry_run` flag passed to `UCClient`. Writes are attempted in order;
  a failure on one does not abort the rest (there is no cross-statement transaction in Unity
  Catalog DDL), so the outcome is reported as `success`, `partial_failure`, or `failed`, naming
  exactly which write labels landed and which didn't.
- **`coverage.py`** computes fill rate per dimension and per team from the contracts on disk (not
  from the catalogue), plus one clearly-labelled simulated outcome measure, and `dashboard/app.py`
  renders it as a static page. `coverage_history.py` (ADR-008) optionally appends one row per
  dataset per run to `workspace.platform.coverage_history`, feeding a native AI/BI dashboard.

## CI wiring

Two workflows read `change_classes.yaml`'s routing (`change_routing.py`, ADR-006 — a glob match
over changed file paths, "content" edits taking the fast path and "schema"/tooling changes the
slow one, never argued per change request):

- **`validate.yml`** runs on every pull request, always against `FakeUCClient` — credential-free
  by design, so any fork gets the identical real CI mechanism with nothing to configure.
- **`apply.yml`** runs on every push to `main`. It is wired to apply live as `ucmeta-ci-apply`
  whenever `DATABRICKS_CI_HOST`/`DATABRICKS_CI_CLIENT_ID`/`DATABRICKS_CI_CLIENT_SECRET` are
  configured as repository secrets; without them, it falls back to the identical apply-on-merge
  mechanism against `FakeUCClient`. Which branch ran is unmistakable in the job's own step list.

`ucmeta-ci-apply` (ADR-009) is a real, least-privileged service principal that owns three of the
four demo tables and is granted nothing else — no create or drop privilege anywhere, at any
level. Its grants are rebuildable from `scripts/provision_ci_apply_identity.sh`; the one manual
step that can't be scripted (minting the credential, storing it as GitHub secrets) is documented
in [`docs/ci-service-principal.md`](../ci-service-principal.md).

## The audit trail

Every `apply` attempt — success, partial failure, failure, or a refusal before any write —
publishes exactly one `ReleaseRecord` to `release_log.jsonl` (`release_log.py`): what changed, who
approved it, when, and the deployment outcome. Logging failures and refusals, not only successes,
is deliberate — an audit trail that only records wins is an advertisement. If the log write itself
fails, `apply()` never lets that escape as a raw exception; it returns the same result it would
have on success, with `release_log_error` naming the manual audit action required, so a caller
checking only `.status` still gets an accurate account of what happened to the catalogue.

## Related reading

- [README](../../README.md) — what this solution is for and how it fits alongside the catalog
  provider.
- ADR-001 (contracts not catalogue editing), ADR-002 (AI proposes, humans approve), ADR-003
  (files and change requests, not a UI), ADR-004 (the real workspace behind the `UCClient` seam),
  ADR-006 (two tracks for change), ADR-009 (the `ucmeta-ci-apply` identity) — all under
  [`docs/adrs/`](../adrs/).
- Specs F-PLATFORM-001 (the core loop), F-PLATFORM-002 (coverage history and dashboard),
  F-PLATFORM-003 (CI-only apply enforcement) for the *why* behind each design call above.

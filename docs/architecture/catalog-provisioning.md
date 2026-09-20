# Architecture: catalog provisioning (F-PLATFORM-004/005)

What this document is for: how the catalog-provisioning system is actually put together — its
components, what runs where, what talks to what — for someone trying to understand or extend it.
For *why* it looks this way, see the [README](../../README.md) and the ADRs linked throughout;
this document's job is the *how*.

## A second authoring surface

`catalog-requests/*.yaml` is a second authoring surface, sibling to `contracts/`, one nine-field
YAML request per catalog (`provision_catalog.py`'s `CatalogRequest` Pydantic model):
`catalog_name`, `business_application_id`, `business_area`, `description`, `default_schema`,
`requested_by`, `environment` (required), plus `region` and `sensitivity` (optional — `region` is
recorded only, nothing in this feature acts on it). Unknown fields are rejected outright
(`extra: "forbid"`), so a misspelled field name fails the request rather than silently doing
nothing. `catalog-requests/_template.yaml` is the platform-owned starting point for a real
request; it is never itself provisioned (the same template carve-out `contracts/_template.yaml`
already has in `apply.yml`/`validate.yml`).

## Three new `UCClient` capabilities

Provisioning needed operations `uc_client.py` didn't have — on something other than an
already-existing table — so three methods were added to the same seam every other write already
uses: `create_catalog(name, description)`, `create_schema(catalog, schema)`, and
`set_catalog_tags(catalog, tags)`. All three execute real DDL (`CREATE CATALOG`, `CREATE SCHEMA`,
`ALTER CATALOG ... SET TAGS`) through the identical statement-execution path `apply.py`'s table
writes use, and all three honor the same `dry_run` convention: with `dry_run=True`, each returns
the exact SQL it would run without touching catalogue state.

**Tags, not properties, for `business_area`/`environment`/`sensitivity`.** This mirrors the
distinction `apply.py` already draws at the table level: properties are structured facts nobody
searches by, tags are governance/classification labels a consumer filters or searches on. A
catalog's business area, its medallion tier, and its sensitivity classification are exactly the
kind of thing someone browsing the catalog list wants to filter by — so they're tags, the same
choice `apply.py` made for a table's `sensitivity`/`pii`/`business_term`.

## `provision_catalog.py`'s discipline: validate → plan → execute → log

`provision_catalog.py` deliberately shares no code with `apply.py` — a catalog request is a
different input, a catalog-plus-schema-plus-tags is a different shape of write — but it
reimplements the same discipline `apply.py` established, independently:

1. **Validate, never raising.** `load_catalog_request` is the one entry point that turns every way
   a request can be malformed (not valid YAML, fails Pydantic validation, an illegal single-part
   identifier, an unresolvable `business_application_id`) into a problem list rather than an
   exception. This is stricter than `apply.py`'s own precedent (a malformed contract there
   propagates straight out) because the spec asks for it explicitly: every refusal reason still
   produces a release-log record.
2. **Plan.** `_build_write_steps` builds a fixed, ordered, three-statement plan — create catalog,
   then create its default schema, then set its tags — always in that order, always all three.
   `plan_provision` returns the plan's SQL with zero writes, the same `dry_run=True` seam
   `apply.py`'s `plan_apply` uses, so the printed plan and the SQL that later actually runs can
   never diverge into two implementations.
3. **Execute.** `provision()` refuses the whole request, writing nothing, if validation found any
   problem (SC-004-03). Otherwise it attempts every planned write in order; a failure on one does
   not abort the rest, since there is no transaction across `CREATE CATALOG`/`CREATE SCHEMA`/
   `ALTER CATALOG ... SET TAGS`. The outcome is `success`, `partial_failure`, or `failed`,
   naming exactly which of the three writes landed.
4. **Log.** Exactly one `ReleaseRecord` is published per run — success, partial failure, failure,
   or refusal — to the same `release_log.jsonl` `apply.py` writes to, using the request file's own
   schema version as `contract_version`. A release-log write failure never escapes as a raw
   exception; it comes back as `release_log_error`, the same policy `apply.py` uses.

**Create-only, with one named exception.** Every write here is idempotent in effect on the
`UCClient` side (re-running `CREATE CATALOG`/`CREATE SCHEMA` against an already-existing object,
or `SET TAGS` with the same values, is a no-op), so re-provisioning the same request — because a
merge is reprocessed, or the catalog already existed for an unrelated reason — succeeds rather
than refusing. `set_catalog_tags` is the one write in the plan that is genuinely re-applied (and
converges on the current values) on every run, not just the first — tags can legitimately change
between requests for the same catalog; the catalog and its default schema, once created, do not.

## CI wiring

**`provision-catalog.yml`** runs on every push to `main`, filtered to changed paths under
`catalog-requests/` (the same changed-path-diff mechanism `apply.yml` uses, against
`catalog-requests/` instead of `contracts/`). It is wired to provision live as
`ucmeta-ci-provision` whenever `DATABRICKS_CI_PROVISION_HOST`/`_CLIENT_ID`/`_CLIENT_SECRET` are
configured — deliberately distinct secret names from `ucmeta-ci-apply`'s three, so one credential
can never be pasted into the other's slot unnoticed. Without them, it falls back to the identical
provisioning-on-merge mechanism against `FakeUCClient`. Which branch ran is visible directly in
the job's own step list, not only in its log text.

## `ucmeta-ci-provision`: a second identity, not a widened first one (ADR-011)

Creating a catalog needs a metastore-level `CREATE_CATALOG` privilege — standing `ucmeta-ci-apply`
(ADR-009) was explicitly built *not* to hold: "It is granted nothing else. No create or drop
anywhere, no administrative standing at account, workspace or metastore level." Rather than widen
that identity's grant, F-PLATFORM-005 introduced a second, separate service principal,
`ucmeta-ci-provision`, holding exactly `CREATE_CATALOG` on the metastore and `CAN_USE` on the
warehouse — and nothing on any table. This keeps the two identities' blast radii disjoint by
construction: `ucmeta-ci-apply` can vandalise three tables' metadata and create nothing anywhere;
`ucmeta-ci-provision` can create catalogs and touch no table. Its grants are rebuildable from
`scripts/provision_ci_provision_identity.sh`; the manual credential-minting step is documented in
[`docs/ci-service-principal-provision.md`](../ci-service-principal-provision.md).

## What exists today, as evidence

Two real catalogs have been provisioned live and are kept permanently as standing evidence (this
platform's provisioning has no delete path, by design): `data_platform_demo` (via a hand-run
command while the identity itself was being stood up) and `data_platform_demo_silver` (via an
actual merged pull request touching `catalog-requests/`, `create catalog`/`create schema`/
`set catalog tags` all reporting `OK`). Both already carry real tables documented through the
harvester's own harvest → document → apply loop (`pipeline_runs` and `data_quality_checks` inside
`data_platform_demo.demo`, contracts at `contracts/demo/*.yaml`) — concrete proof the two
solutions compose rather than living in separate demos.

## The named gap: provisioning grants no access

`provision-catalog` creates a catalog and its default schema and nothing else. No `USE_CATALOG`,
no `USE_SCHEMA` is granted to the requesting team, and there is no second schema, no table, and no
grant of any kind inside the catalog it creates. This was found live, not reasoned about in
advance — the catalog's own author went looking for a newly-provisioned catalog in the workspace
UI and could not see it, for exactly this reason. Closing it needs a grant step this feature
deliberately does not build; it is a genuine remaining gap, not a design decision (see the
README's "What I didn't do").

## Related reading

- [README](../../README.md) — what this solution is for and how it fits alongside the harvester.
- [ADR-011](../adrs/ADR-011-a-second-machine-identity-so-the-first-one-did-not-have-to-grow.md)
  (the second identity) and
  [ADR-009](../adrs/ADR-009-ci-only-apply-a-machine-identity-and-a-tested-boundary.md) (the first
  one, for contrast) under [`docs/adrs/`](../adrs/).
- Specs F-PLATFORM-004 (the mechanism, fake-backed) and F-PLATFORM-005 (the live path) for the
  *why* behind each design call above.

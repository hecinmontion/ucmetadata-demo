# 02 — `provision-catalog`, live, success

**What this proves:** the same `provision-catalog` verb, pointed at the real
Free Edition workspace through the `ucmeta-ci-provision` service principal,
creates (or re-confirms) a real catalog — and that re-running an already-
provisioned request is safe, because every write it plans is idempotent
(F-PLATFORM-004 SC-004-02, inherited live by F-PLATFORM-005 SC-005-04).

## Why this reuses an existing request file rather than authoring a new one

This demo deliberately reuses the real, already-provisioned request file
`catalog-requests/data-platform-demo.yaml` (`data_platform_demo`, first
provisioned live during F-PLATFORM-005's own build). Re-running it is
idempotent and safe — and it means this documentation pass doesn't create yet
another permanent real catalog in the workspace just to have something to
screenshot. Authoring a genuinely new live request follows demo 01's fixture
shape exactly, with `--live --profile ucmeta-ci-provision` added to the
command line.

```yaml
catalog_name: data_platform_demo
business_application_id: BA-40092
business_area: platform
region:
description: First catalog provisioned end-to-end by F-PLATFORM-005's live pipeline — kept permanently as standing evidence the live path works (rev 2).
default_schema: demo
sensitivity: internal
requested_by: hectormb.9@gmail.com
environment: bronze
```

## Command

```
uv run ucmeta provision-catalog catalog-requests/data-platform-demo.yaml --live --profile ucmeta-ci-provision --approved-by "Demo Author"
```

## Actual output

```
provision-catalog data_platform_demo: success
  OK   create catalog
  OK   create schema
  OK   set catalog sensitivity label
```

All three writes report success again on this re-run — `data_platform_demo`
already existed live from a prior run, and `CREATE CATALOG IF NOT EXISTS` /
`CREATE SCHEMA IF NOT EXISTS` / `ALTER CATALOG ... SET TAGS` all converge
cleanly on state that is already there, rather than erroring.

## Why this matters

This is the live counterpart to demo 01, and the safe way to demonstrate it:
re-running a request already merged and provisioned is exactly the shape
SC-004-02 ("the requested catalog already exists") and SC-005-04 ("the grant
script is re-run against an already-provisioned workspace") both name as a
property that must hold, not just be asserted. See F-PLATFORM-004 and
F-PLATFORM-005.

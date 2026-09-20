# 01 — `provision-catalog`, fake, success

**What this proves:** a well-formed catalog request file, run against the default
in-repo fake catalogue, provisions cleanly with zero Databricks credentials —
exactly the "clone the repo and run it on a laptop" path F-PLATFORM-004 designs
for.

## Fixture

`examples/fixtures/example-catalog-request.yaml` is a copy of
`catalog-requests/_template.yaml` with every required field filled in with
illustrative demo values (a real registered business application id,
`BA-20144`, resolved from `src/uc_metadata/owner_registry.py`):

```yaml
catalog_name: examples_demo_catalog
business_application_id: BA-20144
business_area: marketing
region:
description: Illustrative catalog request authored for examples/01-provision-catalog-fake-success.md — not a real business need.
default_schema: default
sensitivity:
requested_by: Demo Author
environment: silver
```

## Command

```
uv run ucmeta provision-catalog examples/fixtures/example-catalog-request.yaml --approved-by "Demo Author"
```

No `--live` flag, so this defaults to `FakeUCClient` — nothing here ever touches
the real workspace.

## Actual output

```
provision-catalog examples_demo_catalog: success
  OK   create catalog
  OK   create schema
```

Only two writes ran (not three) because `sensitivity` was left blank in the
fixture — `_build_write_steps` only plans the "set catalog sensitivity label"
write when a request declares one (`src/uc_metadata/provision_catalog.py`).

## Why "verifying" this means reading the output above, not a follow-up query

`FakeUCClient`'s catalogue state lives only in that process's memory
(`src/uc_metadata/fake_uc.py`) — it does not persist to disk, and a second
`uv run ucmeta ...` invocation starts from a fresh, empty fake catalogue. The
one thing this run leaves behind on disk is its `release_log.jsonl` entry
(an audit record, not catalogue state):

```json
{"full_name":"examples_demo_catalog","contract_version":1,"summary":"provisioned 2 write(s)","approved_by":"Demo Author","deployment_status":"success","writes_succeeded":["create catalog","create schema"],"writes_failed":[],"problems":[],"requested_by":"Demo Author"}
```

There is no `ucmeta describe-catalog examples_demo_catalog` command that could
show "yes, it's really there" the way demo 02's live re-run can — the command's
own printed output above *is* the complete record of what happened.

## Why this matters

F-PLATFORM-004's whole design goal is that the fake path needs no credentials
at all, so a reviewer (or this demo) can run the full request → provision loop
on a laptop with zero Databricks account. See spec F-PLATFORM-004, SC-004-01
("Happy path: a request file lands and a usable catalog is created").

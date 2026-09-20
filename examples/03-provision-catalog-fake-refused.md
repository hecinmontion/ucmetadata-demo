# 03 — `provision-catalog`, fake, refused at validation

**What this proves:** a request that fails validation is refused wholesale,
with zero writes attempted — before a single call reaches `FakeUCClient`
(spec F-PLATFORM-004, SC-004-03).

## Fixture

`examples/fixtures/example-catalog-request-invalid.yaml` is shaped exactly
like demo 01's fixture, with one deliberate problem: `business_application_id:
BA-99999`, an id that does not exist in `src/uc_metadata/owner_registry.py`'s
four registered entries (`BA-10231`, `BA-20144`, `BA-30587`, `BA-40092`).

```yaml
catalog_name: examples_invalid_catalog
business_application_id: BA-99999
business_area: marketing
region:
description: Deliberately invalid catalog request for examples/03 and examples/04 — the business_application_id does not resolve.
default_schema: default
sensitivity:
requested_by: Demo Author
environment: silver
```

This is chosen over a missing-required-field shape on purpose: an unresolvable
business application still parses cleanly as a valid-shaped `CatalogRequest`
(every Pydantic field is present and well-typed), so it exercises
`_validate_business_rules`'s owner-resolution check
(`src/uc_metadata/provision_catalog.py`) specifically, rather than failing
earlier at the Pydantic layer — a cleaner, more specific refusal to capture
than "some field was blank."

## Command

```
uv run ucmeta provision-catalog examples/fixtures/example-catalog-request-invalid.yaml --approved-by "Demo Author"
```

## Actual output

```
REFUSED: examples_invalid_catalog -- 1 problem(s):
  - "no owner registered for business_application_id='BA-99999'"
```

Exit code: `1`. Zero writes: no `OK`/`FAIL` write lines are printed at all,
because `provision_catalog.provision()` (which `_cmd_provision_catalog` in
`src/uc_metadata/cli.py` calls directly for any non-`--dry-run` invocation)
refuses the whole request the moment `load_catalog_request` reports a
problem, before `_build_write_steps` is ever called.

`tail -1 release_log.jsonl` after running this demo shows a new entry:

```json
{"full_name":"examples_invalid_catalog","contract_version":1,"summary":"refused: 1 validation problem(s), no writes attempted","approved_by":"Demo Author","timestamp":"...","deployment_status":"refused","writes_succeeded":[],"writes_failed":[],"problems":["\"no owner registered for business_application_id='BA-99999'\""],"requested_by":"Demo Author"}
```

This was previously not the case: an earlier version of `_cmd_provision_catalog`
called `load_catalog_request` itself and returned before ever calling
`provision()` — the one function that publishes the `ReleaseRecord` — so a
refusal reached through the real CLI never landed an audit-trail entry at
all. That bug is fixed: the CLI now always calls `provision()` directly for
a real run, so validation and release-log publication happen in exactly one
place, matching `apply.py`'s own discipline.

## Why this matters

SC-004-03 exists specifically so that a malformed or unresolvable request
never silently creates a partial catalogue — the whole request is refused,
named, and appended to the audit trail, so a refused request is visible in
the same release log a successful one would be, not a silent non-event.

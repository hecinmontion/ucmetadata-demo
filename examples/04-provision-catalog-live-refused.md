# 04 — `provision-catalog`, live, refused before any write

**What this proves:** validation refuses a malformed request identically
whether the underlying client is fake or the real, privileged
`ucmeta-ci-provision` identity — because validation runs, and the request is
refused, before `_build_write_steps` ever constructs a plan against the
client at all. This mirrors F-PLATFORM-005's SC-005-05 ("a merged request
fails validation, and the privileged identity refuses it identically").

## Fixture

The same deliberately-invalid fixture as demo 03,
`examples/fixtures/example-catalog-request-invalid.yaml`
(`business_application_id: BA-99999`, unresolvable against
`owner_registry.py`).

## Command

```
uv run ucmeta provision-catalog examples/fixtures/example-catalog-request-invalid.yaml --live --profile ucmeta-ci-provision --approved-by "Demo Author"
```

`--profile ucmeta-ci-provision` is used here (rather than `ucmeta-ci`) because
it is the identity actually privileged to create catalogs live
(F-PLATFORM-005) — the point being made is validation-is-identity-independent,
so either profile would prove it equally; `ucmeta-ci-provision` is chosen
because it is the identity this feature is actually about.

## Actual output

```
REFUSED: examples_invalid_catalog -- 1 problem(s):
  - "no owner registered for business_application_id='BA-99999'"
```

Byte-for-byte identical to demo 03's fake-run output, and identical exit code
(`1`). Zero live writes were attempted — no `CREATE CATALOG` call, or any
other `RealUCClient` method, was ever invoked, because `load_catalog_request`
refuses the request before `_build_write_steps(request, client)` is even
called (`src/uc_metadata/provision_catalog.py`). The identity behind `client`
never enters the picture: a refused request never gets far enough to ask what
that identity can or cannot do.

## Why this matters

This is the live proof, not just an assertion, that validation is identity-
independent: a live-privileged identity buys nothing against a request that
never passes the checks it would need to pass regardless of who is running
it. See F-PLATFORM-005's SC-005-05.

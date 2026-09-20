# Examples: a runnable cookbook

Eight demos, each showing an exact command and the real, actually-captured
output from running it — this repository's own "verified live, not asserted"
discipline (every ADR in `docs/adrs/` follows it) applied to its own
documentation. Fixtures each demo needs live under `docs/examples/fixtures/`, never
under `catalog-requests/` — that folder is scanned by the real
`.github/workflows/provision-catalog.yml` CI workflow's path filter on push,
and a deliberately-invalid fixture sitting there would be a landmine for
whoever pushes next.

**Fake demos (01, 03, 05, 07)** need zero credentials — the default backend
for every `ucmeta` verb is `FakeUCClient`, the in-repo fake catalogue. Anyone
who clones this repository can run these on a laptop with no Databricks
account.

**Live demos (02, 04, 06, 08)** need the `ucmeta` / `ucmeta-ci` /
`ucmeta-ci-provision` local Databricks CLI profiles this project's operator
work already set up, and touch the real Free Edition workspace:

- 02 and 04 are safe to re-run any number of times — 02 because every write
  `provision-catalog` plans is idempotent, 04 because it refuses before
  attempting any write at all.
- 06 deliberately stops at `--dry-run` and never performs a real write — see
  that demo's "why this matters" for the reason.
- 08 is read-only (`validate` never writes).

## Index

| # | Demo | What it shows |
|---|------|----------------|
| [01](01-provision-catalog-fake-success.md) | `provision-catalog`, fake, success | A well-formed catalog request provisions cleanly with zero credentials. |
| [02](02-provision-catalog-live-success.md) | `provision-catalog`, live, success | The same verb, live, re-provisioning an already-created real catalog idempotently. |
| [03](03-provision-catalog-fake-refused.md) | `provision-catalog`, fake, refused | An unresolvable business-application id refuses the whole request with zero writes. |
| [04](04-provision-catalog-live-refused.md) | `provision-catalog`, live, refused | The same invalid request refuses identically live, before any write is attempted. |
| [05](05-harvest-document-apply-fake.md) | `harvest` → document → `apply`, fake | The full happy-path loop: harvest a skeleton, fill in judgment fields by hand, apply it. |
| [06](06-harvest-document-apply-live-dry-run.md) | `harvest` → document → `apply --dry-run`, live | The same loop against the real workspace, stopping at a dry-run plan on purpose. |
| [07](07-validate-fake-fails.md) | `validate`, fake, fails | A shipped contract whose `silver` claim isn't backed by its own DQ evidence, caught. |
| [08](08-validate-live-passes.md) | `validate`, live, passes | The same four checks, run against the real workspace, passing on genuine evidence. |

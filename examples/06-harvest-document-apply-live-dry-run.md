# 06 — `harvest` → document → `apply --dry-run`, live

**What this proves:** `harvest` reading the real workspace, and `apply
--dry-run` planning the real writes it would perform against a real table —
without this documentation pass ever actually overwriting that table's
already-established live metadata.

## Step 1 — harvest, live (read-only)

```
uv run ucmeta harvest workspace.analytics.customers --ba-id BA-10231 -o examples/fixtures/customers-demo-live.yaml --live --profile ucmeta
```

`harvest` only reads the table's schema (`src/uc_metadata/harvest.py`) — no
write path exists for this verb at all — and the `ucmeta` profile has read
access to `workspace.analytics.customers`, so this is safe to run against the
real table.

### Actual output

```
Wrote a harvested skeleton contract for 'workspace.analytics.customers' to examples/fixtures/customers-demo-live.yaml
This is a skeleton: judgment fields are blank and/or carry a harvest placeholder. Run `ucmeta propose` and review before `ucmeta apply`.
```

The harvested skeleton is structurally identical to demo 05's fake harvest —
same seven columns, same placeholder sentinels — because `FakeUCClient`'s
seeded schema for this table was itself transcribed from a real harvest
against the live workspace (`src/uc_metadata/fake_uc.py`'s own docstring).

## Step 2 — document (the human edit)

Edited the same way as demo 05, but with text that names itself as
illustrative rather than a real declaration, since (see "why this matters"
below) it is never actually submitted live:

**After (dataset block and `email` column):**

```yaml
  refresh:
    cadence: daily
    sla_minutes: 120
  retention_days: 730
  certification: silver
  description: ILLUSTRATIVE description authored for examples/06-harvest-document-apply-live-dry-run.md
    -- not submitted as this table's real live description (see that demo's "why this matters").
columns:
- name: customer_id
  data_type: bigint
  nullable: true
  partition_key: false
  tags: []
- name: email
  data_type: string
  nullable: true
  partition_key: false
  description:
    value: ILLUSTRATIVE column description for the same demo -- see the demo file for why this
      is never actually applied live.
    ai_proposed: false
  business_term:
    value: email
    ai_proposed: false
  tags: []
```

## Step 3 — apply, live, `--dry-run` (deliberately never dropped)

```
uv run ucmeta apply examples/fixtures/customers-demo-live.yaml --approved-by "Demo Author" --live --profile ucmeta-ci --dry-run
```

### Actual output

```
Dry run: 4 statement(s) would be applied for workspace.analytics.customers (nothing written):
  COMMENT ON TABLE `workspace`.`analytics`.`customers` IS 'ILLUSTRATIVE description authored for examples/06-harvest-document-apply-live-dry-run.md -- not submitted as this table''s real live description (see that demo''s "why this matters").'
  COMMENT ON COLUMN `workspace`.`analytics`.`customers`.`email` IS 'ILLUSTRATIVE column description for the same demo -- see the demo file for why this is never actually applied live.'
  ALTER TABLE `workspace`.`analytics`.`customers` SET TBLPROPERTIES ('uc_metadata.certification' = 'silver', 'uc_metadata.retention_days' = '730', 'uc_metadata.refresh_cadence' = 'daily', 'uc_metadata.refresh_sla_minutes' = '120', 'uc_metadata.owner_business_application_id' = 'BA-10231')
  ALTER TABLE `workspace`.`analytics`.`customers` ALTER COLUMN `email` SET TAGS ('business_term' = 'email')
```

## Why this deliberately stops at `--dry-run`

`workspace.analytics.customers` already carries real, previously-established
live metadata from F-PLATFORM-003's own verification work — a real
description, real column comments, real tags (see `contracts/analytics/
customers.yaml`, the actual contract on file for this table, "verified
against the live workspace"). Dropping `--dry-run` here would silently
overwrite that with whatever illustrative text this demo happened to author,
with no real decision behind it about what the table's live description
*should* say. That is not this documentation pass's call to make, so it
doesn't make it. **Dropping `--dry-run` is the only difference between this
command and a real live apply** — everything else about the command above is
exactly what a real apply would run.

`--profile ucmeta-ci` is required here, not `ucmeta` (the profile used for the
read-only harvest step): F-PLATFORM-003 Layer 2 revoked the human identity's
write access to this table by moving ownership to the `ucmeta-ci-apply`
service principal — only that identity (reached here through the `ucmeta-ci`
profile) can write to it live now. `--dry-run` never touches the client for a
real write either way, so this holds regardless, but naming the correct
profile is part of accurately demonstrating the real command.

## Why this matters

This mirrors F-PLATFORM-003's identity separation directly: the human profile
(`ucmeta`) can read; only the CI service principal (`ucmeta-ci`, backed by
`ucmeta-ci-apply`) can write. See `docs/ci-service-principal.md` and ADR-009.

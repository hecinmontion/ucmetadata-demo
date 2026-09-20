# 05 — `harvest` → document → `apply`, fake

**What this proves:** the full happy-path loop a contributor actually runs —
harvest a table's real schema into a skeleton contract, fill in the judgment
fields a human (not harvest) must declare, then apply it — completes cleanly
against the default in-repo fake catalogue with zero credentials
(F-PLATFORM-001, SC-001-01).

## Step 1 — harvest

```
uv run ucmeta harvest workspace.analytics.customers --ba-id BA-10231 -o examples/fixtures/customers-demo-fake.yaml
```

Fake by default (no `--live`).

### Actual output

```
Wrote a harvested skeleton contract for 'workspace.analytics.customers' to examples/fixtures/customers-demo-fake.yaml
This is a skeleton: judgment fields are blank and/or carry a harvest placeholder. Run `ucmeta propose` and review before `ucmeta apply`.
```

The written skeleton carries harvest's four unmistakable placeholders
(`src/uc_metadata/harvest.py`): `description` is a `TODO(human)` string,
`refresh.cadence` is a `TODO(human)` string, `retention_days` is `1`, and
`certification` is `bronze`.

## Step 2 — document (the human edit)

`ucmeta validate`/`ucmeta apply` refuse a contract that still carries any of
harvest's placeholder sentinels (`src/uc_metadata/validate.py`,
`_placeholder_sentinel_problems`) — filling them in by hand is the "propose"
part of "AI proposes, humans approve" this demo does directly with an editor
rather than via `ucmeta propose` (which needs a live `ANTHROPIC_API_KEY`).
The actual before/after on the dataset block and the `email` column:

**Before:**

```yaml
  refresh:
    cadence: 'TODO(human): declare a cadence, e.g. daily'
    sla_minutes: 1
  retention_days: 1
  certification: bronze
  description: 'TODO(human): describe this dataset -- harvest cannot know this; it
    is never harvested.'
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
  tags: []
```

**After:**

```yaml
  refresh:
    cadence: daily
    sla_minutes: 120
  retention_days: 730
  certification: silver
  description: Customer master records for the direct-to-consumer storefront, documented
    for examples/05-harvest-document-apply-fake.md.
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
    value: Customer's primary electronic contact address.
    ai_proposed: false
  business_term:
    value: email
    ai_proposed: false
  tags: []
```

`certification: silver` is a real claim, not the bronze placeholder value left
untouched — which is why it also needs to be a claim the attached DQ evidence
actually supports (see `dq_registry.yaml`'s `customers-email-present` and
`customers-lifetime-value-non-negative` rules, both passing against
`FakeUCClient`'s seeded happy-path rows for this table).

## Step 3 — apply

```
uv run ucmeta apply examples/fixtures/customers-demo-fake.yaml --approved-by "Demo Author"
```

Fake by default.

### Actual output

```
apply workspace.analytics.customers: success
  OK   table comment
  OK   column comment: email
  OK   table properties
  OK   column tags: email
```

## Why this matters

This is F-PLATFORM-001's own core loop, SC-001-01 ("harvest → hand-author →
validate → apply"): `apply()` calls `validate()` internally and refuses the
whole contract if it does not pass (`src/uc_metadata/apply.py`), so a
successful `apply` here is also proof the edited contract passed every one of
`validate.py`'s four checks — drift, unreviewed markers, placeholder
sentinels, and certification-vs-evidence.

# 08 — `validate`, live, passes

**What this proves:** `validate` runs its full four-check pass — drift,
unreviewed markers, placeholder sentinels, certification-vs-evidence —
against the real workspace and passes cleanly, using only read access.

## Command

```
uv run ucmeta validate contracts/analytics/customers.yaml --live --profile ucmeta
```

`validate` never writes (`src/uc_metadata/validate.py`'s module docstring:
"it does not print the exact catalogue writes a merge would perform" is the
one thing it defers to `apply.py`'s planning function, which itself only
plans, never executes, on this path) — so this is safe to run against the
real table with the `ucmeta` profile's read-only access.

## Actual output

```
PASS: contracts/analytics/customers.yaml has no problems.

Planned catalogue writes for workspace.analytics.customers (17 statement(s)):
  COMMENT ON TABLE `workspace`.`analytics`.`customers` IS 'Customer master records for the direct-to-consumer storefront. One row per customer; no historical/slowly-changing versions are kept.'
  COMMENT ON COLUMN `workspace`.`analytics`.`customers`.`customer_id` IS 'Surrogate primary key identifying one customer.'
  COMMENT ON COLUMN `workspace`.`analytics`.`customers`.`email` IS 'Customer''s primary electronic contact address.'
  COMMENT ON COLUMN `workspace`.`analytics`.`customers`.`first_name` IS 'Customer''s given name, as provided at signup.'
  COMMENT ON COLUMN `workspace`.`analytics`.`customers`.`last_name` IS 'Customer''s family name, as provided at signup.'
  COMMENT ON COLUMN `workspace`.`analytics`.`customers`.`region` IS 'Coarse geographic market this customer is associated with.'
  COMMENT ON COLUMN `workspace`.`analytics`.`customers`.`signup_date` IS 'Calendar date this customer''s account was created.'
  COMMENT ON COLUMN `workspace`.`analytics`.`customers`.`lifetime_value` IS 'Total historical revenue attributed to this customer across all orders to date, in USD.'
  ALTER TABLE `workspace`.`analytics`.`customers` SET TBLPROPERTIES ('uc_metadata.certification' = 'silver', 'uc_metadata.retention_days' = '730', 'uc_metadata.refresh_cadence' = 'daily', 'uc_metadata.refresh_sla_minutes' = '120', 'uc_metadata.owner_business_application_id' = 'BA-10231')
  ALTER TABLE `workspace`.`analytics`.`customers` SET TAGS ('sensitivity' = 'confidential')
  ALTER TABLE `workspace`.`analytics`.`customers` ALTER COLUMN `customer_id` SET TAGS ('primary_key' = '', 'pii' = 'false', 'sensitivity' = 'internal')
  ALTER TABLE `workspace`.`analytics`.`customers` ALTER COLUMN `email` SET TAGS ('pii' = 'true', 'sensitivity' = 'confidential', 'business_term' = 'email')
  ALTER TABLE `workspace`.`analytics`.`customers` ALTER COLUMN `first_name` SET TAGS ('pii' = 'true', 'sensitivity' = 'confidential')
  ALTER TABLE `workspace`.`analytics`.`customers` ALTER COLUMN `last_name` SET TAGS ('pii' = 'true', 'sensitivity' = 'confidential')
  ALTER TABLE `workspace`.`analytics`.`customers` ALTER COLUMN `region` SET TAGS ('pii' = 'false', 'sensitivity' = 'internal', 'business_term' = 'region')
  ALTER TABLE `workspace`.`analytics`.`customers` ALTER COLUMN `signup_date` SET TAGS ('pii' = 'false', 'sensitivity' = 'internal', 'business_term' = 'signup_date')
  ALTER TABLE `workspace`.`analytics`.`customers` ALTER COLUMN `lifetime_value` SET TAGS ('pii' = 'false', 'sensitivity' = 'internal', 'business_term' = 'lifetime_value')
```

Exit code: `0`.

## Why this matters

This is the live counterpart to demo 07: the same four checks, run against
the real workspace instead of the fake, passing because
`contracts/analytics/customers.yaml`'s `silver` claim is genuinely backed by
two passing `dq_registry.yaml` rules against the real table's data
(`customers-email-present`, `customers-lifetime-value-non-negative`). See
F-PLATFORM-001, SC-001-01/SC-001-02.

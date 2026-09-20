# 07 — `validate`, fake, fails

**What this proves:** `validate` catches a certification claim the attached
data-quality evidence does not support — a real, already-documented failure
this repository ships deliberately, not a contrived one authored for this
demo.

## Command

```
uv run ucmeta validate contracts/marketing/campaigns.yaml
```

Fake by default — `validate` doesn't need `--live` to demonstrate this
failure. `contracts/marketing/campaigns.yaml` ships with `certification:
silver` and two attached `dq_registry.yaml` rules that are genuinely failing
against `FakeUCClient`'s seeded rows for this table — a negative budget and an
`end_date` before `start_date` — named as deliberate in that contract's own
header comment (per `src/uc_metadata/apply.py`'s module docstring, this is
exactly the case the certification-vs-evidence check exists to catch).

## Actual output

```
FAIL: contracts/marketing/campaigns.yaml -- 1 problem(s):
  - certification: 'silver' claimed for 'workspace.marketing.campaigns' but 2 attached DQ rule(s) are failing (campaigns-budget-non-negative, campaigns-end-date-not-before-start-date) -- the quality evidence does not support this tier

Planned catalogue writes for workspace.marketing.campaigns (17 statement(s)):
  COMMENT ON TABLE `workspace`.`marketing`.`campaigns` IS 'Marketing campaign records: one row per time-bounded campaign, its channel, budget and active window. Known data-quality issues on two rows (see dq_registry.yaml) are tracked, not yet remediated.'
  COMMENT ON COLUMN `workspace`.`marketing`.`campaigns`.`campaign_id` IS 'Surrogate primary key identifying one campaign.'
  COMMENT ON COLUMN `workspace`.`marketing`.`campaigns`.`name` IS 'Human-readable campaign name, as entered by the marketing team.'
  COMMENT ON COLUMN `workspace`.`marketing`.`campaigns`.`channel` IS 'The marketing route this campaign runs through (e.g. email, social, search).'
  COMMENT ON COLUMN `workspace`.`marketing`.`campaigns`.`budget` IS 'Spend approved for this campaign, in USD, fixed at creation.'
  COMMENT ON COLUMN `workspace`.`marketing`.`campaigns`.`start_date` IS 'Calendar date this campaign''s active window begins.'
  COMMENT ON COLUMN `workspace`.`marketing`.`campaigns`.`end_date` IS 'Calendar date this campaign''s active window ends. Expected on or after start_date.'
  COMMENT ON COLUMN `workspace`.`marketing`.`campaigns`.`active` IS 'Whether this campaign is currently running.'
  ALTER TABLE `workspace`.`marketing`.`campaigns` SET TBLPROPERTIES ('uc_metadata.certification' = 'silver', 'uc_metadata.retention_days' = '365', 'uc_metadata.refresh_cadence' = 'daily', 'uc_metadata.refresh_sla_minutes' = '60', 'uc_metadata.owner_business_application_id' = 'BA-20144')
  ALTER TABLE `workspace`.`marketing`.`campaigns` SET TAGS ('sensitivity' = 'internal')
  ALTER TABLE `workspace`.`marketing`.`campaigns` ALTER COLUMN `campaign_id` SET TAGS ('primary_key' = '', 'pii' = 'false', 'sensitivity' = 'internal')
  ALTER TABLE `workspace`.`marketing`.`campaigns` ALTER COLUMN `name` SET TAGS ('pii' = 'false', 'sensitivity' = 'internal')
  ALTER TABLE `workspace`.`marketing`.`campaigns` ALTER COLUMN `channel` SET TAGS ('pii' = 'false', 'sensitivity' = 'internal', 'business_term' = 'channel')
  ALTER TABLE `workspace`.`marketing`.`campaigns` ALTER COLUMN `budget` SET TAGS ('pii' = 'false', 'sensitivity' = 'internal', 'business_term' = 'budget')
  ALTER TABLE `workspace`.`marketing`.`campaigns` ALTER COLUMN `start_date` SET TAGS ('pii' = 'false', 'sensitivity' = 'internal')
  ALTER TABLE `workspace`.`marketing`.`campaigns` ALTER COLUMN `end_date` SET TAGS ('pii' = 'false', 'sensitivity' = 'internal')
  ALTER TABLE `workspace`.`marketing`.`campaigns` ALTER COLUMN `active` SET TAGS ('pii' = 'false', 'sensitivity' = 'internal', 'business_term' = 'campaign')
```

Exit code: `1`.

## Why the plan still prints even though validation failed

`ucmeta validate` composes two modules that deliberately don't call each
other (`src/uc_metadata/cli.py`'s module docstring): `validate.py` runs the
checks and stops, `apply.py`'s `plan_apply` builds the exact write list with
no opinion on whether the contract is fit to merge. The CLI glues them
together so a reviewer sees both what's wrong *and* exactly what would land
if the contract were merged as-is — regardless of whether the checks passed.

## Why this matters

This is the deliberate negative case F-PLATFORM-001's adversarial coverage
depends on: `campaigns` is fully filled in as metadata (every field present,
no placeholders, no unreviewed markers) but still fails validation on
correctness grounds — proving the certification-vs-evidence check catches
something fill-rate coverage alone cannot. See `src/uc_metadata/validate.py`'s
module docstring and `dq_registry.yaml`.

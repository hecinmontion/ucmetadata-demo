-- Bootstraps the coverage-history table (spec: F-PLATFORM-002; ADR-008 --
-- "coverage history is a Unity Catalog table ... in a platform-owned
-- schema, separate from the data-product schemas the contracts describe").
--
-- `workspace.platform` is a schema created and owned by the platform team,
-- distinct from `workspace.analytics`/`workspace.marketing` (the schemas
-- scripts/seed_demo_data.sql seeds for the data products this tool
-- describes): coverage measurement is platform infrastructure, not a data
-- product, and should not sit inside the estate it measures.
--
-- Run once against the Free Edition workspace, same convention as
-- scripts/seed_demo_data.sql:
--   databricks api post /api/2.0/sql/statements -p ucmeta --json '{
--     "warehouse_id": "66fca89a60cb0837",
--     "statement": "<one statement at a time from this file>"
--   }'
-- or paste into a SQL editor / notebook attached to the Serverless Starter
-- Warehouse. Idempotent (`CREATE ... IF NOT EXISTS`), so re-running this
-- script against an already-bootstrapped workspace is a no-op.
--
-- Granularity (ADR-008, resolved): one row per dataset per run, and nothing
-- else -- no pre-aggregated run-level or per-team summary rows. Every
-- aggregate a dashboard needs is a query over these rows, never a second
-- stored number that could disagree with `coverage.py`.
--
-- Append-only (Rules & Constraints): this table is only ever written to by
-- `uc_metadata.coverage_history.publish_coverage_history`, which only ever
-- issues `INSERT`. No code path in this repository issues `UPDATE` or
-- `DELETE` against it, and none should ever be added -- a dataset that was
-- uncovered in one run and covered in the next gets two rows that disagree,
-- and both stay true forever.

CREATE SCHEMA IF NOT EXISTS workspace.platform;

CREATE TABLE IF NOT EXISTS workspace.platform.coverage_history (
  -- Run identity: which run this row belongs to, and when that run happened.
  -- Every row from one run carries the same run_id/run_timestamp pair, so
  -- "give me one run's rows" and "order runs chronologically" both need only
  -- these two columns, never a join to a separate runs table (Rules &
  -- Constraints: no pre-aggregated run-level rows).
  run_id                                STRING    NOT NULL,
  run_timestamp                         TIMESTAMP NOT NULL,

  -- Dataset identity as seen at run time. `full_name` is the
  -- catalog.schema.table identity `models.Qualifier.full_name` produces;
  -- `team` is resolved via owner_registry the same way `coverage.py`
  -- resolves it for the report itself (see coverage.py's module docstring).
  -- A renamed or dropped dataset simply stops appearing in the newest
  -- run's rows -- its earlier rows are never rewritten or deleted (Rules &
  -- Constraints: "no pruning of orphaned entries").
  full_name                             STRING NOT NULL,
  team                                  STRING NOT NULL,

  -- Fill-rate dimensions: the same four booleans `coverage.py`'s
  -- `DatasetCoverage` computes (owner / description / sensitivity / DQ
  -- rules attached), kept as separate boolean columns rather than one
  -- packed structure so a dashboard or an ad-hoc query can filter/aggregate
  -- on any single dimension with a plain `WHERE`, with no need to unpack a
  -- nested value first. `dataset_fill_rate` is this dataset's own mean
  -- across those four booleans for this run -- the per-dataset "overall
  -- fill rate" figure, distinct from `has_owner AND has_description AND
  -- has_sensitivity AND has_dq_rules` (which is what "fully covered" means).
  has_owner                             BOOLEAN NOT NULL,
  has_description                       BOOLEAN NOT NULL,
  has_sensitivity                       BOOLEAN NOT NULL,
  has_dq_rules                          BOOLEAN NOT NULL,
  dataset_fill_rate                     DOUBLE  NOT NULL,

  -- Certification claim vs. evidence: the tier this dataset's contract
  -- claims, and whether coverage.py's tier_is_supported_by_evidence(...)
  -- verdict backed that claim for this run. NULL (not FALSE) means the
  -- verdict could not be computed for this run -- a silver/gold claim
  -- evaluated with no UCClient available -- distinct from a claim that was
  -- evaluated and found unsupported.
  certification_tier                    STRING  NOT NULL,
  certification_supported_by_evidence   BOOLEAN,

  -- The outcome measure this run published, carried into every dataset row
  -- of that run (Rules & Constraints: "the simulated label ... survives
  -- into the table and into the dashboard"). `outcome_measure_simulated` is
  -- never omitted or defaulted away -- every row this table has ever
  -- received came from a CoverageReport whose outcome_measures[0].simulated
  -- was already set by coverage.py, never guessed at here.
  outcome_measure_name                  STRING  NOT NULL,
  outcome_measure_value                 DOUBLE  NOT NULL,
  outcome_measure_unit                  STRING  NOT NULL,
  outcome_measure_simulated             BOOLEAN NOT NULL
) USING DELTA
COMMENT 'Append-only coverage history: one row per dataset per run. Written only by uc_metadata.coverage_history.publish_coverage_history via a single INSERT per run. Never UPDATEd, never DELETEd, never pruned -- see ADR-008 and spec F-PLATFORM-002 Rules & Constraints.';

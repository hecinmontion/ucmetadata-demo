-- Seeds demo tables into the `workspace` managed catalog on a Databricks
-- Free Edition workspace, standing in for datasets that already exist in a real
-- Unity Catalog estate before this tool ever touches them.
--
-- Four tables, four roles in the demo:
--   analytics.customers  -- clean, fully documented target for the happy-path walkthrough (SC-001-01)
--   marketing.campaigns  -- fully covered but fails its DQ rules (the well-covered-but-quality-red case)
--   analytics.orders     -- deliberately left messy/grandfathered/partially covered; `state` is an
--                           intentionally ambiguous column name (order status vs. US state) for the
--                           "AI confidently produces a wrong answer" Q&A moment
--   marketing.leads       -- brand new, never harvested at seed time. Once harvested and left
--                           unreviewed (deliberately, with no dq_registry.yaml rules registered
--                           for it either), it's the lowest-scoring dataset the coverage dashboard
--                           shows: has_owner=True (a human had to name a real BA id to harvest it
--                           at all -- see coverage.py's own comment on why this is never False),
--                           has_description/has_sensitivity/has_dq_rules all False -- 25% fill
--                           rate, the floor given how has_owner is defined, not a literal zero.
--
-- Run once against the Free Edition workspace:
--   databricks api post /api/2.0/sql/statements -p ucmeta --json @scripts/seed_demo_data_statement.json
-- or paste into a SQL editor / notebook attached to the Serverless Starter Warehouse.

CREATE SCHEMA IF NOT EXISTS workspace.analytics;
CREATE SCHEMA IF NOT EXISTS workspace.marketing;

-- ============================================================
-- analytics.customers -- happy path (SC-001-01)
-- ============================================================
CREATE TABLE IF NOT EXISTS workspace.analytics.customers (
  customer_id     BIGINT,
  email           STRING,
  first_name      STRING,
  last_name       STRING,
  region          STRING,
  signup_date     DATE,
  lifetime_value  DECIMAL(10,2)
) USING DELTA;

INSERT INTO workspace.analytics.customers VALUES
  (100001, 'amara.diallo@example.com',   'Amara',   'Diallo',   'EMEA', DATE'2023-02-14', 1240.50),
  (100002, 'jin.park@example.com',       'Jin',     'Park',     'APAC', DATE'2023-05-03', 340.00),
  (100003, 'lucas.oliveira@example.com', 'Lucas',   'Oliveira', 'LATAM',DATE'2022-11-21', 5620.75),
  (100004, 'freya.johansen@example.com', 'Freya',   'Johansen', 'EMEA', DATE'2024-01-09', 90.25),
  (100005, 'wei.chen@example.com',       'Wei',     'Chen',     'APAC', DATE'2023-08-30', 2100.00),
  (100006, 'noa.katz@example.com',       'Noa',     'Katz',     'EMEA', DATE'2024-03-17', 0.00),
  (100007, 'ravi.mehta@example.com',     'Ravi',    'Mehta',    'APAC', DATE'2022-07-04', 8890.10),
  (100008, 'elena.popescu@example.com',  'Elena',   'Popescu',  'EMEA', DATE'2023-12-25', 415.60);

-- ============================================================
-- marketing.campaigns -- well-covered but quality-red (adversarial demo)
-- Two rows violate an obvious DQ rule (end_date before start_date, negative
-- budget) even though every column will end up fully described.
-- ============================================================
CREATE TABLE IF NOT EXISTS workspace.marketing.campaigns (
  campaign_id  BIGINT,
  name         STRING,
  channel      STRING,
  budget       DECIMAL(10,2),
  start_date   DATE,
  end_date     DATE,
  active       BOOLEAN
) USING DELTA;

INSERT INTO workspace.marketing.campaigns VALUES
  (5001, 'Spring Launch',       'email',    12000.00, DATE'2026-03-01', DATE'2026-03-31', false),
  (5002, 'Summer Push',         'social',   8000.00,  DATE'2026-06-01', DATE'2026-06-30', false),
  (5003, 'Back to School',      'search',   -500.00,  DATE'2026-08-15', DATE'2026-09-01', false),  -- negative budget: DQ violation
  (5004, 'Holiday Blitz',       'email',    25000.00, DATE'2026-11-20', DATE'2026-11-10', false),  -- end before start: DQ violation
  (5005, 'New Year Retention',  'lifecycle',4000.00,  DATE'2027-01-02', DATE'2027-01-31', true),
  (5006, 'Referral Boost',      'referral', 3000.00,  DATE'2026-04-10', DATE'2026-05-10', true);

-- ============================================================
-- analytics.orders -- deliberately messy / grandfathered / partially covered.
-- `state` is intentionally ambiguous (order status vs. US state abbreviation)
-- to demonstrate the AI drafter's failure mode and the low-confidence flag.
-- Left uncontracted in contracts/ on purpose -- this is the two-speed-rollout
-- evidence dataset (decision 11), and the ALTER TABLE target for the live
-- drift demo (SC-001-02).
-- ============================================================
CREATE TABLE IF NOT EXISTS workspace.analytics.orders (
  order_id     BIGINT,
  customer_id  BIGINT,
  state        STRING,
  amount       DECIMAL(10,2),
  order_ts     TIMESTAMP,
  channel      STRING
) USING DELTA;

INSERT INTO workspace.analytics.orders VALUES
  (900001, 100001, 'shipped', 84.00,  TIMESTAMP'2026-04-02 10:15:00', 'web'),
  (900002, 100003, 'CA',      210.50, TIMESTAMP'2026-04-03 09:02:00', 'web'),      -- looks like US-state, not order status
  (900003, 100002, 'pending', 19.99,  TIMESTAMP'2026-04-04 14:22:00', 'mobile'),
  (900004, 100005, 'NY',      560.00, TIMESTAMP'2026-04-05 11:47:00', 'web'),      -- same ambiguity
  (900005, 100007, 'refunded',120.00, TIMESTAMP'2026-04-06 08:30:00', 'mobile'),
  (900006, 100004, 'shipped', 32.40,  TIMESTAMP'2026-04-07 16:05:00', 'web'),
  (900007, 100006, 'pending', 75.00,  TIMESTAMP'2026-04-08 12:12:00', 'mobile'),
  (900008, 100008, 'TX',      340.75, TIMESTAMP'2026-04-09 13:50:00', 'web'),
  (900009, 100001, 'shipped', 61.10,  TIMESTAMP'2026-04-10 15:40:00', 'mobile'),
  (900010, 100003, 'refunded',95.00,  TIMESTAMP'2026-04-11 17:00:00', 'web');

-- ============================================================
-- marketing.leads -- brand new, undiscovered dataset. No comment, no tags, no
-- properties applied here on purpose: this is the "just showed up, nobody has
-- touched it yet" state, contrasted against orders' "grandfathered, once
-- touched by harvest but still unreviewed" state. Deliberately no
-- dq_registry.yaml rule is registered for this table either.
-- ============================================================
CREATE TABLE IF NOT EXISTS workspace.marketing.leads (
  lead_id     BIGINT,
  email       STRING,
  source      STRING,
  created_at  TIMESTAMP,
  status      STRING
) USING DELTA;

INSERT INTO workspace.marketing.leads VALUES
  (700001, 'lena.moreau@example.com',    'webinar',     TIMESTAMP'2026-05-01 09:12:00', 'new'),
  (700002, 'ben.okafor@example.com',     'referral',    TIMESTAMP'2026-05-02 14:45:00', 'contacted'),
  (700003, 'priya.iyer@example.com',     'organic',     TIMESTAMP'2026-05-03 08:30:00', 'new'),
  (700004, 'tomas.vargas@example.com',   'paid_search', TIMESTAMP'2026-05-04 16:20:00', 'qualified'),
  (700005, 'hana.kobayashi@example.com', 'webinar',     TIMESTAMP'2026-05-05 11:05:00', 'contacted'),
  (700006, 'omar.said@example.com',      'referral',    TIMESTAMP'2026-05-06 13:40:00', 'disqualified');

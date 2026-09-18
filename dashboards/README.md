# dashboards/

`coverage.lvdash.json` is the version-controlled definition of the **UC Metadata Coverage**
Databricks AI/BI Dashboard (ADR-008). It is the source of truth: any change to the dashboard
goes through this file and a redeploy via `scripts/deploy_coverage_dashboard.sh`, not a live
edit in the workspace UI that nobody exports back.

## What it shows

Three datasets, all querying `workspace.platform.coverage_history` (the append-only table
`coverage_history.py` writes to — see ADR-008):

- **Overall fill rate (latest run)** — a counter, averaged across the most recent run's rows.
- **Time to first query (days) — SIMULATED** — the outcome measure from the latest run, labelled
  in its own title as simulated, per the project-wide rule that no caller may present a
  simulated figure as observed.
- **Coverage by dataset (latest run)** — a table: dataset, team, fill rate, certification tier,
  and whether the DQ evidence actually supports that tier claim.
- **Overall fill rate trend across runs** — a line chart over every run recorded in history, the
  actual payoff of making the metric a table instead of a file.

## How it was built

Per ADR-008's construction-method decision: route (a), iterating against the live `lakeview`
API rather than guessing at the undocumented widget/chart JSON schema. Every query was verified
standalone against the real table before being embedded in the dashboard; the definition was
created and published against the real workspace (both succeeded with no errors); the exported,
API-normalised definition (note: the API rewrites a single `query` string into a `queryLines`
array, among other things — that normalisation is only visible by doing this live, not from the
docs) is what's committed here.

**Honest limit of this verification**: CLI/API round-tripping proves the definition is
structurally valid and that Databricks accepted it as a real, queryable dashboard — it does not
prove the page *renders* correctly, since neither the CLI nor this session has a way to see
pixels. Open it in the workspace once before presenting it, to confirm visually.

## Redeploying

```bash
# Update the existing dashboard in place:
scripts/deploy_coverage_dashboard.sh <dashboard-id>

# Or create a fresh one:
scripts/deploy_coverage_dashboard.sh
```

Current live dashboard: id `01f1b3768f6c1f38a8f6609e4c630bc8`, workspace path
`/Users/hectormb.9@gmail.com/UC Metadata Coverage.lvdash.json`. Free Edition workspaces don't
expose a stable public URL for a dashboard the way a production workspace does — open it from
the workspace's own Dashboards list, or via `databricks lakeview get <id> -p ucmeta`.

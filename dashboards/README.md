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
- **Dataset fill rate by dataset** — a horizontal bar chart: one bar per dataset (`full_name`),
  length is that dataset's own fill rate, colour is its team. Replaced a table widget that never
  actually rendered (see below) — this is the current, confirmed-working visualisation.
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

**The table widget's honest failure, and how it was actually resolved.** Two API-accepted,
hand-guessed column-schema definitions for a `table` widget (the second copied field-for-field
from a real published Databricks dashboard example) both still failed to render in the browser —
"Invalid widget definition is imported" — confirmed genuine after a real hard refresh, not a
caching artefact. CLI/API round-tripping proved the definitions were structurally valid and that
Databricks accepted them as a real, queryable dashboard; it never proved they'd actually render,
which is exactly the limit route (a) has when nothing in the loop can see pixels. The resolution
was route (c): rebuilding the widget by hand through the workspace's own dashboard editor — as a
bar chart, not a table, since that's what the editor's own affordances made easy to build
correctly. That hand-built widget is what's live today, and this file was re-exported from the
live, working dashboard (`databricks lakeview get 01f1b3768f6c1f38a8f6609e4c630bc8 -p ucmeta`) to
bring `coverage.lvdash.json` back in sync with it — the one exception to "this file is the source
of truth, not a live edit nobody exports back" that this repository has had, caught and closed
rather than left standing.

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

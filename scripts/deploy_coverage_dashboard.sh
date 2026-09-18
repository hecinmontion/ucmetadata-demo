#!/usr/bin/env bash
# Deploys dashboards/coverage.lvdash.json to the live workspace as a real Databricks
# AI/BI Dashboard, and publishes it. This is the GitOps half of ADR-008's claim: the
# committed file is the source of truth, and any change to the dashboard goes through
# this file and a redeploy, not a live edit in the workspace UI that nobody exports
# back. If you do edit the dashboard in the UI, export it back over this file before
# committing (`databricks lakeview get <id> | jq -r '.serialized_dashboard' | jq '.'`).
#
# Usage:
#   scripts/deploy_coverage_dashboard.sh [dashboard_id]
#
# With no argument, creates a new dashboard. With a dashboard_id, updates that
# existing one in place instead of creating a duplicate.
#
# Requires: `databricks` CLI authenticated (OAuth profile `ucmeta` by default --
# see uc_client.DEFAULT_UC_PROFILE), `jq`, and a reachable SQL warehouse. No PAT.

set -euo pipefail

PROFILE="${DATABRICKS_PROFILE:-ucmeta}"
WAREHOUSE_ID="${DATABRICKS_WAREHOUSE_ID:-66fca89a60cb0837}"
DISPLAY_NAME="${DASHBOARD_DISPLAY_NAME:-UC Metadata Coverage}"
DEFINITION_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/dashboards/coverage.lvdash.json"

if [ ! -f "$DEFINITION_PATH" ]; then
  echo "Error: $DEFINITION_PATH not found" >&2
  exit 1
fi

SERIALIZED="$(jq -c . "$DEFINITION_PATH")"

# `databricks ... --json @-` does not read stdin despite the `@` convention working
# for a real file path -- confirmed empirically, not assumed from the --help text.
# A real temp file is what actually works; cleaned up on exit either way.
PAYLOAD_FILE="$(mktemp)"
trap 'rm -f "$PAYLOAD_FILE"' EXIT

if [ "${1:-}" != "" ]; then
  DASHBOARD_ID="$1"
  echo "Updating existing dashboard $DASHBOARD_ID ..."
  jq -n --arg sd "$SERIALIZED" --arg wh "$WAREHOUSE_ID" --arg name "$DISPLAY_NAME" \
    '{display_name: $name, warehouse_id: $wh, serialized_dashboard: $sd}' > "$PAYLOAD_FILE"
  databricks lakeview update "$DASHBOARD_ID" -p "$PROFILE" --json "@$PAYLOAD_FILE"
else
  echo "Creating a new dashboard ..."
  jq -n --arg sd "$SERIALIZED" --arg wh "$WAREHOUSE_ID" --arg name "$DISPLAY_NAME" \
    '{display_name: $name, warehouse_id: $wh, serialized_dashboard: $sd}' > "$PAYLOAD_FILE"
  RESULT="$(databricks lakeview create -p "$PROFILE" --json "@$PAYLOAD_FILE" -o json)"
  DASHBOARD_ID="$(echo "$RESULT" | jq -r '.dashboard_id')"
  echo "Created dashboard: $DASHBOARD_ID"
fi

echo "Publishing ..."
databricks lakeview publish "$DASHBOARD_ID" -p "$PROFILE" --warehouse-id "$WAREHOUSE_ID"
echo "Done. Dashboard id: $DASHBOARD_ID"
echo "Open it in the workspace: search for '$DISPLAY_NAME' under Dashboards, or use:"
echo "  databricks lakeview get $DASHBOARD_ID -p $PROFILE"

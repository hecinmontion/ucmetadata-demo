#!/usr/bin/env bash
# Provisions (or re-provisions, idempotently) the ucmeta-ci-apply service
# principal and every grant it needs -- Layer 1 and Layer 2 of ADR-009 /
# F-PLATFORM-003, expressed as a checked-in, re-runnable script rather than a
# paragraph asserting the workspace was set up correctly.
#
# This is what closes ADR-009's own "What is not yet true" gap: without this
# file, the arrangement it describes exists only as manual changes against
# the live workspace, and F-PLATFORM-001's disposable-workspace rule ("the
# workspace is reclaimable and rebuildable from the repository") has exactly
# one exception until this is checked in. After this script, that exception
# is closed: creating the service principal, granting it exactly what
# apply.py performs, transferring ownership of the three demo tables, and
# re-granting hectormb.9@gmail.com SELECT-only are all expressed here, not
# only in F-PLATFORM-003's Revision History.
#
# What this script does NOT do, deliberately (see docs/ci-service-principal.md
# and F-PLATFORM-003's Out of Scope, "Automating the creation of the
# automation environment's secret"): mint the service principal's OAuth
# client secret. That is a manual, once-only act performed by hand through
# the workspace's own admin console. Scripting it would need a credential
# capable of writing workspace secrets, which is a strictly worse thing to
# have lying around than the secret it would produce. This script never
# generates, reads or prints that secret value, and it takes no credential of
# its own as input -- it runs using whatever profile is already authenticated
# (the account-admin `ucmeta` profile by default), the same convention
# scripts/deploy_coverage_dashboard.sh uses.
#
# Idempotent: safe to re-run against an already-provisioned workspace.
# Service-principal creation is guarded by a lookup first; every grant below
# is expressed as a "changes: add" call, which Unity Catalog's own permission
# API treats as a set union rather than a replace, so re-running this script
# a second time changes nothing further -- the same idempotency guarantee
# scripts/bootstrap_coverage_history.sql states for its own `CREATE ... IF
# NOT EXISTS`.
#
# Usage:
#   scripts/provision_ci_apply_identity.sh
#
# Requires: `databricks` CLI authenticated as an account admin (in this
# solo prototype, the account owner's own `ucmeta` profile -- see
# uc_client.DEFAULT_UC_PROFILE) and `jq`. No PAT.

set -euo pipefail

PROFILE="${DATABRICKS_PROFILE:-ucmeta}"
WAREHOUSE_ID="${DATABRICKS_WAREHOUSE_ID:-66fca89a60cb0837}"
DISPLAY_NAME="${CI_APPLY_SP_DISPLAY_NAME:-ucmeta-ci-apply}"

CATALOG="workspace"
SCHEMAS=(analytics marketing)
TABLES=(
  workspace.analytics.customers
  workspace.analytics.orders
  workspace.marketing.campaigns
)

# The identity Layer 2 re-grants read-only access to -- F-PLATFORM-003 Rules
# & Constraints and ADR-009's Layer 2 section. Overridable so this script
# stays usable by someone rebuilding the workspace under a different owner.
HUMAN_READ_ONLY_IDENTITY="${CI_SCRIPT_HUMAN_IDENTITY:-hectormb.9@gmail.com}"

# ---- 1/5: service principal, idempotent creation ---------------------------
echo "== 1/5: service principal (${DISPLAY_NAME}) =="
EXISTING="$(databricks service-principals list -p "$PROFILE" \
  --filter "displayName eq \"${DISPLAY_NAME}\"" -o json)"
SP_ID="$(echo "$EXISTING" | jq -r '.[0].id // empty')"

if [ -n "$SP_ID" ]; then
  APP_ID="$(echo "$EXISTING" | jq -r '.[0].applicationId')"
  echo "Already exists: id=${SP_ID} applicationId=${APP_ID}. Skipping creation."
else
  CREATED="$(databricks service-principals create -p "$PROFILE" \
    --display-name "$DISPLAY_NAME" -o json)"
  SP_ID="$(echo "$CREATED" | jq -r '.id')"
  APP_ID="$(echo "$CREATED" | jq -r '.applicationId')"
  echo "Created: id=${SP_ID} applicationId=${APP_ID}."
  echo "Next, by hand (this script never touches the secret -- see"
  echo "docs/ci-service-principal.md): mint a client secret for this"
  echo "principal through the workspace admin console and store it as the"
  echo "DATABRICKS_CI_CLIENT_SECRET GitHub Actions secret."
fi

# ---- 2/5: entitlements ------------------------------------------------------
# Both are required before this identity can call any workspace API at all --
# without them, every call below would fail with "This API is disabled for
# users without the databricks-sql-access or workspace-access ...
# entitlements", even with every Unity Catalog grant already in place. A real
# finding from provisioning this principal for the first time, recorded here
# so a future rebuild does not have to rediscover it.
echo "== 2/5: entitlements (workspace-access, databricks-sql-access) =="
ENTITLEMENTS_PATCH="$(jq -n '{
  schemas: ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
  Operations: [
    {
      op: "add",
      path: "entitlements",
      value: [{value: "workspace-access"}, {value: "databricks-sql-access"}]
    }
  ]
}')"
databricks service-principals patch "$SP_ID" -p "$PROFILE" --json "$ENTITLEMENTS_PATCH" >/dev/null
echo "Entitlements present (re-adding an already-held entitlement is a no-op)."

# ---- 3/5: USE_CATALOG, USE_SCHEMA, warehouse CAN_USE ------------------------
# Schema/catalog-scoped because these privilege types have no finer grain
# (F-PLATFORM-003 Open Questions: grant granularity, resolved). Neither grants
# any content access by itself -- SELECT and ownership below do that work.
echo "== 3/5: USE_CATALOG, USE_SCHEMA, warehouse CAN_USE =="
databricks grants update catalog "$CATALOG" -p "$PROFILE" --json \
  "$(jq -n --arg p "$APP_ID" '{changes: [{principal: $p, add: ["USE_CATALOG"]}]}')" >/dev/null

for schema in "${SCHEMAS[@]}"; do
  databricks grants update schema "${CATALOG}.${schema}" -p "$PROFILE" --json \
    "$(jq -n --arg p "$APP_ID" '{changes: [{principal: $p, add: ["USE_SCHEMA"]}]}')" >/dev/null
done

# Not a catalog grant at all, and inert without it -- every grant above does
# nothing if the identity cannot use the warehouse the applier executes its
# statements through.
databricks warehouses update-permissions "$WAREHOUSE_ID" -p "$PROFILE" --json \
  "$(jq -n --arg app "$APP_ID" \
    '{access_control_list: [{service_principal_name: $app, permission_level: "CAN_USE"}]}')" >/dev/null
echo "USE_CATALOG, USE_SCHEMA (x${#SCHEMAS[@]}) and warehouse CAN_USE granted."

# ---- 4/5: table ownership, the mechanism that actually enforces Layer 2 ----
# Revoking a privilege from a table's owner is a no-op (ownership carries full
# control implicitly) -- see ADR-009's Context and F-PLATFORM-003's Rules &
# Constraints. Ownership is what has to move for the identity to gain real
# write access and for hector's own identity to lose it; a plain grant would
# not do either.
echo "== 4/5: table ownership -> ${DISPLAY_NAME} =="
for table in "${TABLES[@]}"; do
  current_owner="$(databricks tables get "$table" -p "$PROFILE" -o json | jq -r '.owner')"
  if [ "$current_owner" = "$APP_ID" ]; then
    echo "${table}: already owned by ${DISPLAY_NAME}."
  else
    databricks tables update "$table" -p "$PROFILE" --owner "$APP_ID" >/dev/null
    echo "${table}: ownership transferred to ${DISPLAY_NAME} (was ${current_owner})."
  fi
done

# ---- 5/5: the human keeps SELECT, and nothing else -------------------------
echo "== 5/5: ${HUMAN_READ_ONLY_IDENTITY} re-granted SELECT-only =="
for table in "${TABLES[@]}"; do
  databricks grants update table "$table" -p "$PROFILE" --json \
    "$(jq -n --arg p "$HUMAN_READ_ONLY_IDENTITY" '{changes: [{principal: $p, add: ["SELECT"]}]}')" >/dev/null
done
echo "SELECT granted on ${#TABLES[@]} table(s)."

echo
echo "Done. Layer 1 identity and Layer 2 revocation-by-ownership-transfer are"
echo "both in place, matching F-PLATFORM-003's Revision History rev 3."
echo
echo "Known, documented, NOT closed by this script (see"
echo "docs/ci-service-principal.md, ADR-009 'The part that did not work'):"
echo "${HUMAN_READ_ONLY_IDENTITY} remains a metastore administrator, so"
echo "SET/UNSET TAGS still bypasses this boundary for that identity with zero"
echo "explicit grant. No grant this script makes can switch that off --"
echo "closing it means removing the identity from the admins group entirely,"
echo "which is a materially larger, separately-decided change and is out of"
echo "scope here."

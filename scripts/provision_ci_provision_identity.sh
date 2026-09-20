#!/usr/bin/env bash
# Provisions (or re-provisions, idempotently) the ucmeta-ci-provision service
# principal and every grant it needs -- the identity decision F-PLATFORM-005
# revision 2 made, expressed as a checked-in, re-runnable script rather than a
# paragraph asserting the workspace was set up correctly.
#
# This is a NEW, SEPARATE identity from ucmeta-ci-apply, not a widening of it
# (spec: F-PLATFORM-005, Rules & Constraints, "ucmeta-ci-apply is not modified
# by this feature, in any respect"). This script is therefore a sibling to
# scripts/provision_ci_apply_identity.sh, not an edit to it -- see that
# script's own header for the identity it provisions, which this file never
# touches. Two identities, two scripts, each describing exactly one privilege
# set: the existing script's self-description as ADR-009's least-privilege
# arrangement stays accurate precisely because nothing here is added to it.
#
# What ucmeta-ci-provision is granted, and it is the narrowest set that lets
# `ucmeta provision-catalog --live` do its job (F-PLATFORM-005 Rules &
# Constraints, "the grant made is the narrowest one that lets the pipeline do
# its job, and nothing that is merely convenient"):
#   - the two entitlements every service principal needs before it can call
#     any workspace API at all (the same finding
#     provision_ci_apply_identity.sh already recorded -- not rediscovered
#     here, just re-applied to a second principal);
#   - the metastore-level CREATE_CATALOG privilege -- the one genuinely new
#     grant type in this project, since every privilege
#     provision_ci_apply_identity.sh grants is scoped to a catalog, schema or
#     table, and none of those helps create a catalog at all;
#   - CAN_USE on the same SQL warehouse the applier's statements execute
#     through, since this identity's CREATE CATALOG / CREATE SCHEMA / ALTER
#     CATALOG ... SET TAGS statements execute through it too.
# Nothing else. No USE_CATALOG, no USE_SCHEMA, no table ownership, no grant
# this identity does not need to create a catalog, a schema inside it and a
# label on it -- ucmeta-ci-apply keeps the grants that let it write table
# metadata, and this identity has no reason to overlap with it at all.
#
# What this script does NOT do, deliberately, for the same reason
# provision_ci_apply_identity.sh doesn't (see docs/ci-service-principal.md
# and docs/ci-service-principal-provision.md, "The one manual step"): mint
# the service principal's OAuth client secret. That stays a manual,
# once-only act performed by hand through the workspace's own admin console.
# This script never generates, reads or prints that secret value, and it
# takes no credential of its own as input -- it runs using whatever profile
# is already authenticated (the account-admin `ucmeta` profile by default),
# the same convention every other grant script in this repository uses.
#
# Idempotent: safe to re-run against an already-provisioned workspace
# (F-PLATFORM-005 SC-005-04). Service-principal creation is guarded by a
# lookup first; every grant below is expressed as a "changes: add" call,
# which Unity Catalog's own permission API treats as a set union rather than
# a replace, so re-running this script a second time changes nothing
# further.
#
# Usage:
#   scripts/provision_ci_provision_identity.sh
#
# Requires: `databricks` CLI authenticated as an account admin (in this solo
# prototype, the account owner's own `ucmeta` profile -- see
# uc_client.DEFAULT_UC_PROFILE) and `jq`. No PAT.

set -euo pipefail

PROFILE="${DATABRICKS_PROFILE:-ucmeta}"
WAREHOUSE_ID="${DATABRICKS_WAREHOUSE_ID:-66fca89a60cb0837}"
DISPLAY_NAME="${CI_PROVISION_SP_DISPLAY_NAME:-ucmeta-ci-provision}"

# ---- 1/4: service principal, idempotent creation ---------------------------
echo "== 1/4: service principal (${DISPLAY_NAME}) =="
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
  echo "docs/ci-service-principal-provision.md): mint a client secret for"
  echo "this principal through the workspace admin console and store it as"
  echo "the DATABRICKS_CI_PROVISION_CLIENT_SECRET GitHub Actions secret."
fi

# ---- 2/4: entitlements ------------------------------------------------------
# Same finding as provision_ci_apply_identity.sh's step 2/5, re-applied here
# rather than rediscovered: without both, every call below fails with "This
# API is disabled for users without the databricks-sql-access or
# workspace-access ... entitlements", even with every grant already in
# place.
echo "== 2/4: entitlements (workspace-access, databricks-sql-access) =="
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

# ---- 3/4: the metastore-level CREATE_CATALOG privilege ----------------------
# The one grant type nothing else in this repository has needed before now.
# Every privilege provision_ci_apply_identity.sh grants (USE_CATALOG,
# USE_SCHEMA, table ownership) is scoped to an object below the metastore;
# none of them can create one. CREATE CATALOG is issued against the
# metastore as a whole (SecurableType.METASTORE in the Databricks SDK,
# databricks/sdk/service/catalog.py), addressed by the metastore's own ID
# rather than by name -- resolved below via `databricks metastores summary`,
# the same call docs/ci-service-principal-provision.md's Identity section
# points at for a human doing this by hand.
echo "== 3/4: metastore-level CREATE_CATALOG =="
METASTORE_ID="$(databricks metastores summary -p "$PROFILE" -o json | jq -r '.metastore_id')"
databricks grants update metastore "$METASTORE_ID" -p "$PROFILE" --json \
  "$(jq -n --arg p "$APP_ID" '{changes: [{principal: $p, add: ["CREATE_CATALOG"]}]}')" >/dev/null
echo "CREATE_CATALOG granted on metastore ${METASTORE_ID}."

# ---- 4/4: warehouse CAN_USE -------------------------------------------------
# Not a catalog grant at all, and inert without it -- the CREATE_CATALOG
# grant above does nothing if the identity cannot use the warehouse its
# statements execute through. Same warehouse ucmeta-ci-apply uses, since
# provisioning and apply both go through RealUCClient's shared
# statement_execution seam.
echo "== 4/4: warehouse CAN_USE =="
databricks warehouses update-permissions "$WAREHOUSE_ID" -p "$PROFILE" --json \
  "$(jq -n --arg app "$APP_ID" \
    '{access_control_list: [{service_principal_name: $app, permission_level: "CAN_USE"}]}')" >/dev/null
echo "Warehouse CAN_USE granted."

echo
echo "Done. ${DISPLAY_NAME} holds the metastore-level privilege to create"
echo "catalogs and schemas and to label what it creates, plus warehouse"
echo "CAN_USE -- and nothing else. No USE_CATALOG, no USE_SCHEMA, no table"
echo "ownership, no administrative standing anywhere: it cannot write a"
echo "comment, a property or a tag onto a table, and it cannot reach"
echo "workspace.platform.coverage_history."
echo
echo "This script never reads or modifies ucmeta-ci-apply in any way -- it"
echo "provisions a second, disjoint identity, not a widened one. Running"
echo "both this script and scripts/provision_ci_apply_identity.sh, in either"
echo "order, against a workspace rebuilt from nothing reproduces the entire"
echo "two-identity arrangement (F-PLATFORM-005 SC-005-04)."

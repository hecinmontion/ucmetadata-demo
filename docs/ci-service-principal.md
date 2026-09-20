# The CI apply identity: `ucmeta-ci-apply`

What this document is for: the identity, its grants, its credential's expiry, and the
procedure for the one manual step nothing in this repository can script (minting the
secret and entering it into GitHub's own secret store). Spec: F-PLATFORM-003. Decision
record: [ADR-009](adrs/ADR-009-ci-only-apply-a-machine-identity-and-a-tested-boundary.md).
Re-runnable grant script: `scripts/provision_ci_apply_identity.sh`.

A second, separate machine identity, `ucmeta-ci-provision`, holds the metastore-level
privilege to create catalogs and is documented in its own sibling file,
[`ci-service-principal-provision.md`](ci-service-principal-provision.md) (F-PLATFORM-005 /
ADR-011) — this identity is untouched by that feature and gains nothing from it.

## Identity

| Field | Value |
|---|---|
| Display name | `ucmeta-ci-apply` |
| Application ID (client ID) | `d9971c7c-bdeb-4195-ac88-8964ab781a5c` |
| Workspace-internal ID | `70908332631556` |
| Type | Workspace-level service principal (non-human) |
| Created | 2026-09-19 |

## What it is granted, and why

Every grant below exists because something `apply.py` actually does — see F-PLATFORM-003's
Rules & Constraints, "the continuous-integration identity is granted the minimum the applier
actually performs, and the grant set is named rather than gestured at." Nothing here is
granted for convenience.

| Grant | On | Why |
|---|---|---|
| `workspace-access`, `databricks-sql-access` entitlements | The principal itself | Not a Unity Catalog grant at all — a separate, workspace-level permission layer. Without both, every API call below fails with `This API is disabled for users without the databricks-sql-access or workspace-access ... entitlements`, even with every UC grant already correct. Discovered empirically while provisioning this principal; recorded here and in `scripts/provision_ci_apply_identity.sh` so a rebuild does not have to rediscover it. |
| `USE_CATALOG` | `workspace` | Required to reach anything inside the catalogue at all; grants no content access by itself. |
| `USE_SCHEMA` | `workspace.analytics`, `workspace.marketing` | Required to reach the tables inside each schema; grants no content access by itself. |
| `CAN_USE` (warehouse permission, not a catalogue grant) | SQL warehouse `66fca89a60cb0837` | `apply.py`'s writes execute as SQL statements through this warehouse (`RealUCClient.statement_execution.execute_statement`). Every grant above is inert without it. |
| Ownership | `workspace.analytics.customers`, `workspace.analytics.orders`, `workspace.marketing.campaigns` | Ownership, not a `SELECT`/`MODIFY`/`APPLY_TAG` grant set, is the actual mechanism: revoking a privilege from an object's *owner* is a no-op (ownership carries full control implicitly), so for this identity to gain real read/comment/property/tag write access — and for hector's own identity to lose it — ownership had to move. See ADR-009's Context section for the mechanical finding this rests on. |

What it is explicitly **not** granted: anything to create or drop; any administrative
standing at account, workspace or metastore level; anything on any catalogue or schema
other than the two above; anything on `workspace.platform.coverage_history` (a different
feature's write path — see F-PLATFORM-002 / ADR-008 — and a different identity's job). A
service principal granted everything is a personal access token with extra steps; the
narrowness is the point.

## Credential

| Field | Value |
|---|---|
| Type | OAuth machine-to-machine (client ID + client secret) |
| Minted | 2026-09-19 |
| **Expires** | **2028-09-18** (~2 years out) |
| Stored | GitHub Actions repository secrets only, once this repository is pushed. Never in this repository, never in a workflow file, never in a job's printed output. |

### Rotation policy (resolved, F-PLATFORM-003 Open Questions, rev 4)

Minimal, by deliberate choice for a spare-time prototype: record the expiry date (above,
findable), write the procedure down (below), and do not build any scheduled rotation or
expiry-check workflow step. That machinery would be operational overhead for a workspace
Databricks may reclaim for inactivity well before two years is out — the same
over-engineering this project's own trade-offs argue against elsewhere. Rotation will most
likely never be exercised for real; the requirement is that the plan and the date exist and
are findable, not that a rotation is scheduled.

### Rotation procedure, for when it is exercised

1. Mint a **second** client secret for `ucmeta-ci-apply` through the workspace admin
   console (Settings → Identity and access → Service principals → `ucmeta-ci-apply` →
   Secrets → Generate secret) while the first secret is still valid, so both work at once
   and no merge fails for a credential reason mid-rotation.
2. Update the `DATABRICKS_CI_CLIENT_SECRET` GitHub Actions repository secret to the new
   value (Settings → Secrets and variables → Actions, on the repository once it is pushed).
3. Verify one real apply run succeeds using the new secret (a merge to `main` that changes
   a contract, or a manual local run with `--live --profile <a profile using the new
   secret>`).
4. Only then delete the old secret from the workspace admin console.
5. Update the expiry date recorded in this document.

The identity itself, and every grant above, survives rotation untouched — rotation replaces
a secret, never the principal (F-PLATFORM-003 SC-003-02).

If the credential is ever allowed to expire without replacement, the next live apply fails
at authentication with a clear error naming the expired credential, not a permissions error
that would send somebody looking in the wrong place.

## The one manual step (deliberately not scripted)

Per F-PLATFORM-003's Out of Scope, "Automating the creation of the automation environment's
secret": minting the client secret and entering it into GitHub's secret store is a
deliberate, once-only manual act performed by hand through each platform's own interface.
Scripting either half would require a credential capable of writing workspace secrets or
repository secrets — a strictly worse credential to have lying around than the one being
stored. `scripts/provision_ci_apply_identity.sh` creates the identity and every grant above;
it never touches the secret value.

**Procedure, once this repository has a GitHub remote:**

1. In the Databricks workspace admin console: Settings → Identity and access → Service
   principals → `ucmeta-ci-apply` → Secrets → Generate secret. Copy the client secret shown
   — it is shown exactly once.
2. In the GitHub repository: Settings → Secrets and variables → Actions → New repository
   secret. Create exactly three secrets, matching the names `.github/workflows/apply.yml`
   reads:
   - `DATABRICKS_CI_HOST` — the workspace URL (e.g. `https://<workspace-host>`).
   - `DATABRICKS_CI_CLIENT_ID` — `d9971c7c-bdeb-4195-ac88-8964ab781a5c` (this principal's
     application ID, from the table above; not secret by itself, but entered alongside the
     secret it pairs with for convenience).
   - `DATABRICKS_CI_CLIENT_SECRET` — the value copied in step 1.
3. Nothing else to do. `apply.yml`'s "Check whether a CI apply credential is configured"
   step reads these three by name at run time; the workflow file never contains a value.

A fork of this repository with none of these three secrets configured is expected and
supported: `apply.yml` detects their absence, states so in its own output, and runs the
apply-on-merge mechanism against the in-repository `FakeUCClient` instead — see
`.github/workflows/apply.yml`'s header comment and F-PLATFORM-003's SC-003-04.

## Blast radius if this credential leaks

An attacker holding it can, on three synthetic tables in a free, disposable,
non-commercial workspace containing no business data: read those tables, rewrite their
descriptions, and set their labels. They cannot create or delete anything, cannot reach any
other schema or catalogue, cannot read the platform's own coverage history, cannot touch the
account, and cannot impersonate a person. The response is one call to delete the credential.
Compare the owner's own personal credential, which is the account owner's full standing in a
string — see ADR-009's Consequences section for the full comparison.

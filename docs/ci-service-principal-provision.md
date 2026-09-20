# The CI provisioning identity: `ucmeta-ci-provision`

What this document is for: the identity, its grants, its credential's expiry, and the
procedure for the one manual step nothing in this repository can script (minting the
secret and entering it into GitHub's own secret store). Spec: F-PLATFORM-005. Decision
record: [ADR-011](adrs/ADR-011-a-second-machine-identity-so-the-first-one-did-not-have-to-grow.md).
Re-runnable grant script: `scripts/provision_ci_provision_identity.sh`.

This is a **second, separate** machine identity from
[`ucmeta-ci-apply`](ci-service-principal.md) — not a widened version of it. If you are
trying to keep two credentials straight, start there: that document covers the identity
that writes table metadata, this one covers the identity that creates catalogs, and
neither can do the other's job. Each links to the other so both are findable from either
starting point.

## Identity

| Field | Value |
|---|---|
| Display name | `ucmeta-ci-provision` |
| Application ID (client ID) | `b0047725-775f-455e-8b6a-7186fdb4b9b0` |
| Workspace-internal ID | `75972948747339` |
| Type | Workspace-level service principal (non-human) |
| Created | 2026-09-20 |

## What it is granted, and why

Every grant below exists because something `provision_catalog.py`'s live branch actually
does — see F-PLATFORM-005's Rules & Constraints, "the grant made is the narrowest one that
lets the pipeline do its job, and nothing that is merely convenient." Nothing here is
granted for convenience.

| Grant | On | Why |
|---|---|---|
| `workspace-access`, `databricks-sql-access` entitlements | The principal itself | Not a Unity Catalog grant at all — a separate, workspace-level permission layer. Without both, every API call below fails with `This API is disabled for users without the databricks-sql-access or workspace-access ... entitlements`, even with every other grant already correct. The same finding `docs/ci-service-principal.md` records for `ucmeta-ci-apply`, re-applied here to a second principal rather than rediscovered. |
| `CREATE_CATALOG` | The metastore as a whole (`SecurableType.METASTORE`, addressed by the metastore's own ID, not a name) | The one genuinely new grant type in this project. Creating a catalog is permitted by a privilege granted against the metastore, not against any catalog, schema or table inside it — every grant `ucmeta-ci-apply` holds is scoped below that level, which is why none of them helps here. Confirmed against the installed Databricks SDK (`databricks/sdk/service/catalog.py`): `Privilege.CREATE_CATALOG = "CREATE_CATALOG"`, `SecurableType.METASTORE = "METASTORE"`, and `CatalogsAPI.create`'s own docstring: "if the caller is a metastore admin or has the **CREATE_CATALOG** privilege." Applied with `databricks grants update metastore <metastore-id> --json '{"changes": [{"principal": "<app-id>", "add": ["CREATE_CATALOG"]}]}'`, where `<metastore-id>` comes from `databricks metastores summary`. |
| `CAN_USE` (warehouse permission, not a catalogue grant) | SQL warehouse `66fca89a60cb0837` (same warehouse `ucmeta-ci-apply` uses) | `provision_catalog.py`'s three statements — `CREATE CATALOG`, `CREATE SCHEMA`, `ALTER CATALOG ... SET TAGS` — execute as SQL through this warehouse (`RealUCClient.statement_execution.execute_statement`), the same seam `ucmeta-ci-apply`'s writes use. The `CREATE_CATALOG` grant above is inert without it. |

What it is explicitly **not** granted, and the contrast with `ucmeta-ci-apply` is the
point: no `USE_CATALOG`, no `USE_SCHEMA`, no table ownership, no table-scoped grant of any
kind — it cannot write a comment, a property or a tag onto a table, cannot read or write
`workspace.platform.coverage_history`, and has no administrative standing at account,
workspace or metastore level beyond the single `CREATE_CATALOG` privilege named above. A
provisioning identity granted metastore administration would be a personal access token
with extra steps; the narrowness is the point, exactly as it was for `ucmeta-ci-apply`.
Symmetrically, `ucmeta-ci-apply` is granted nothing this identity holds — the two
credentials' capabilities do not overlap at all, which is what "separation by function"
(F-PLATFORM-005 Glossary) means in practice.

## Credential

| Field | Value |
|---|---|
| Type | OAuth machine-to-machine (client ID + client secret) |
| Minted | 2026-09-20 |
| **Expires** | **2026-10-20** (30 days — see note below; materially shorter than `ucmeta-ci-apply`'s ~2-year credential) |
| Stored | GitHub Actions repository secrets only, under names distinct from `ucmeta-ci-apply`'s three (see below). Never in this repository, never in a workflow file, never in a job's printed output. |

### Rotation policy — a real departure from `ucmeta-ci-apply`'s, not a copy of it

`ucmeta-ci-apply`'s minimal-rotation position (`docs/ci-service-principal.md`, F-PLATFORM-003
Open Questions rev 4) rests on that credential's ~2-year lifetime plausibly outliving this
Free Edition workspace's own lifespan — "rotation will most likely never be exercised for
real." That reasoning does **not** carry over here: this secret was minted with a 30-day
lifetime, not a chosen ~2-year one, so the same minimal-position conclusion cannot be
copy-pasted as if it still applied. Recorded honestly rather than smoothed over: this
credential **will** need rotating within 30 days of 2026-09-20 if the live path is meant to
keep working past 2026-10-20, using the rotation procedure below. Whether that's addressed
by minting a longer-lived replacement (matching `ucmeta-ci-apply`'s convention) or by
accepting a real, near-term rotation cadence is an open call for whoever is maintaining this
past that date — not decided here.

### Rotation procedure, for when it is exercised

1. Mint a **second** client secret for `ucmeta-ci-provision` through the workspace admin
   console (Settings → Identity and access → Service principals → `ucmeta-ci-provision` →
   Secrets → Generate secret) while the first secret is still valid, so both work at once
   and no merge fails for a credential reason mid-rotation.
2. Update the `DATABRICKS_CI_PROVISION_CLIENT_SECRET` GitHub Actions repository secret to
   the new value (Settings → Secrets and variables → Actions, on the repository once it is
   pushed).
3. Verify one real provisioning run succeeds using the new secret (a merge to `main` that
   changes a catalog request, or a manual local run with
   `--live --profile <a profile using the new secret>`).
4. Only then delete the old secret from the workspace admin console.
5. Update the expiry date recorded in this document.

The identity itself, and every grant above, survives rotation untouched — rotation
replaces a secret, never the principal, the same guarantee `ucmeta-ci-apply`'s rotation
procedure states (F-PLATFORM-003 SC-003-02).

## The one manual step (deliberately not scripted)

Same reasoning as `ucmeta-ci-apply`'s (F-PLATFORM-003's Out of Scope, "Automating the
creation of the automation environment's secret," applied again to a second principal):
minting the client secret and entering it into GitHub's secret store is a deliberate,
once-only manual act performed by hand through each platform's own interface. Scripting
either half would require a credential capable of writing workspace secrets or repository
secrets — a strictly worse credential to have lying around than the one being stored.
`scripts/provision_ci_provision_identity.sh` creates the identity and every grant above;
it never touches the secret value.

**Procedure, once this repository has a GitHub remote:**

1. In the Databricks workspace admin console: Settings → Identity and access → Service
   principals → `ucmeta-ci-provision` → Secrets → Generate secret. Copy the client secret
   shown — it is shown exactly once.
2. In the GitHub repository: Settings → Secrets and variables → Actions → New repository
   secret. Create exactly three secrets, matching the names
   `.github/workflows/provision-catalog.yml` reads — deliberately distinct from
   `ucmeta-ci-apply`'s three (`DATABRICKS_CI_HOST` / `DATABRICKS_CI_CLIENT_ID` /
   `DATABRICKS_CI_CLIENT_SECRET`) so one credential can never be pasted into the other's
   slot unnoticed:
   - `DATABRICKS_CI_PROVISION_HOST` — the workspace URL (e.g. `https://<workspace-host>`;
     the same workspace `ucmeta-ci-apply` uses).
   - `DATABRICKS_CI_PROVISION_CLIENT_ID` — this principal's application ID, from the
     Identity table above once minted (not secret by itself, but entered alongside the
     secret it pairs with for convenience).
   - `DATABRICKS_CI_PROVISION_CLIENT_SECRET` — the value copied in step 1.
3. Nothing else to do. `provision-catalog.yml`'s "Check whether a CI provision credential
   is configured" step reads these three by name at run time; the workflow file never
   contains a value.

A fork of this repository with none of these three secrets configured is expected and
supported: `provision-catalog.yml` detects their absence, states so in its own output, and
runs the provisioning-on-merge mechanism against the in-repository `FakeUCClient` instead
— see `.github/workflows/provision-catalog.yml`'s header comment and F-PLATFORM-005's
SC-005-03.

## Blast radius if this credential leaks

An attacker holding it can, in a free, disposable, non-commercial workspace containing no
business data: create catalogs and schemas, and label what they created. They cannot read
or write a single table's data or metadata, cannot touch the platform's own coverage
history, cannot reach the account, and cannot impersonate a person. The response is one
call to delete the credential. This radius is disjoint from `ucmeta-ci-apply`'s (compare
`docs/ci-service-principal.md`'s own Blast radius section): one identity can create empty
namespaces and cannot touch a table; the other can vandalise three tables' metadata and
cannot create anything. Neither leak gives an attacker the other's capability.

## The real catalogs

F-PLATFORM-005 revision 2 resolved that the first catalog `ucmeta-ci-provision` creates in
the live workspace is kept permanently as standing evidence, rather than cleaned up after
verification. **They exist.** Two so far, kept deliberately — this section is the record so
nobody later finds either and wonders who made it.

| Field | Value | Value |
|---|---|---|
| Catalog | `data_platform_demo` | `data_platform_demo_silver` |
| Schema inside it | `demo` | `demo` |
| Catalog tags | `business_area: platform`, `environment: bronze`, `sensitivity: internal` | `business_area: platform`, `environment: silver`, `sensitivity: internal` |
| Created | 2026-09-20, by `ucmeta-ci-provision` | 2026-09-20, by `ucmeta-ci-provision` |
| Created from | `catalog-requests/data-platform-demo-bronze.yaml` | `catalog-requests/data-platform-demo-silver.yaml` |
| Business application | `BA-40092` | `BA-40092` |
| Requested by | `hectormb.9@gmail.com` | `hectormb.9@gmail.com` |

`data_platform_demo_silver` was provisioned via a real merge to `main` — the first time
`provision-catalog.yml`'s live branch fired from an actual push rather than a hand-run
command, and it succeeded on the first try (see F-PLATFORM-005's revision history). Both
catalogs' tags were widened after the fact (F-PLATFORM-004 rev 4) from `sensitivity` alone to
all three fields above: `business_area`/`environment` were previously recorded only in the
request file, never written into Unity Catalog, until the tag-write step in
`provision_catalog.py` was widened. Re-running the provisioning command against either
catalog is what backfilled the two new tags — no new grant was needed, since
`ucmeta-ci-provision` already owns both catalogs as their creator, and ownership already
carries full tag-write control.

All three planned writes land on every run (`create catalog`, `create schema`,
`set catalog tags`, `deployment_status: success`), and re-running the same command against
an already-provisioned catalog produces an identical clean success with no duplicate-object
errors — the live confirmation of the idempotent-creation claim F-PLATFORM-004 had only ever
proven against the in-memory fake.

**This catalog is not cleaned up, and that is deliberate rather than an oversight.** Keeping
it adds no delete capability to the platform, and removing it would not have used one either
— it would have meant inventing an out-of-band manual chore that nothing here performs and
that F-PLATFORM-005 does not otherwise need. The create-only rule constrains what the
software may do; it takes no position on whether a human tidies up afterwards. If you are
looking at this workspace and wondering whether `data_platform_demo` is safe to delete: it
is, nothing depends on it, but it is the only live proof that this pipeline has ever created
a real catalog, which is why it is still here.

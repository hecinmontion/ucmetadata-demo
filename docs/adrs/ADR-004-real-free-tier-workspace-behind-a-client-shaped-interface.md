# ADR-004: A real free-tier Unity Catalog workspace, behind a client-shaped interface

- **Status:** Accepted
- **Date:** 2026-09-17 (supersedes the original plan to target a hand-written mock)
- **Decider:** hector
- **Affects:** `src/uc_metadata/uc_client.py`, `fake_uc.py`, `tests/unit/test_uc_client_contract.py`,
  every `--live` flag in `cli.py`

## Context

The prototype was originally planned against a hand-written mock catalogue, on the premise that
nobody doing a spare-time submission has a Unity Catalog metastore to hit. That premise turned
out to be false: Databricks Free Edition is free, needs no credit card, has no trial clock, and
was verified reachable with a writable managed `workspace` catalogue and OAuth
user-to-machine authentication.

That changes the argument. The rule the build follows is *mock the systems you cannot touch;
build the primitives the design depends on; never mock the thing being evaluated* — and Unity
Catalog is very close to the thing being evaluated. A mock catalogue answers questions the way
its author guessed they would be answered; a real one settles them. At the same time, unit tests
must not need the network, and a reviewer must be able to clone the repository and run the whole
loop with no Databricks account at all.

## Decision

Target the real workspace, keep the seam.

- `UCClient` is a `Protocol` describing one narrow surface: read a table's columns, comment,
  properties and tags; write a comment, properties or tags back. Every write method takes a
  keyword-only `dry_run` and returns the exact SQL it ran (or would run).
- `RealUCClient` is a thin translation layer over `databricks-sdk` against the Free Edition
  workspace, reached through the Databricks CLI profile `ucmeta`.
- `FakeUCClient` is an in-memory implementation of the same protocol, used by the unit tests and
  as the **default** for every `ucmeta` verb. `--live` switches one invocation to the real client.
- Neither implementation imports the other; both import the protocol. A shared contract-test
  suite (`tests/unit/test_uc_client_contract.py`) runs against both, so the fake cannot quietly
  drift from real Unity Catalog semantics.
- Credentials come from OAuth user-to-machine (`databricks auth login`), never a personal access
  token. The repository holds a profile name and a workspace host; no secret.

## Consequences

- Several design questions were settled by experiment rather than by opinion: that the SDK's
  `type_name` is a driver-internal enum while `type_text` is the SQL-facing type string; that
  tags do not appear on `TablesAPI.get`'s response at all; and that `COMMENT ON ... IS` and
  `SET TBLPROPERTIES/SET TAGS` genuinely re-run cleanly with no observable change — which is what
  `apply.py`'s idempotency claim now rests on, verified at the seam rather than assumed above it.
- Idempotency, drift and revert-restores were demonstrated against real Unity Catalog, not a
  mutated fixture. Two of the three shipped contracts were applied for real.
- The inner loop stays fast and offline, and CI needs no credentials (see README "What's mocked"
  for why the workflows deliberately never pass `--live`).
- Two implementations are two things to maintain, and the fake can drift. That is the known cost;
  the shared contract test is the mitigation, and the fake's continued existence is also the
  fallback if the Free Edition account is ever reclaimed.
- Repointing at the target organisation's production metastore is a configuration change — a
  profile name and a catalogue path — not a rewrite. The seam is what carries that argument.

**What the free-tier workspace is explicitly not.** It is a personal Free Edition account:
serverless compute only, one workspace, a 2X-Small SQL warehouse, a ceiling of five concurrent
job tasks, no staging metastore, no region topology, no real identity groups, no production
governance policies, and three tables rather than thousands. So the prototype proves the API
surface and the semantics; it proves nothing about behaviour at organisational scale or under a
multi-region metastore configuration. The seam is evidence that the move to such an environment
is contained — not evidence that the move has been made.

## Alternatives considered

- **Hand-written mock only (the original plan).** Rejected once the real workspace turned out to
  be free: it would have meant mocking the system the submission is most directly about, and
  every semantic claim (idempotency, tag behaviour, type rendering) would have been a guess
  dressed as a test.
- **Call `databricks-sdk` directly from `harvest.py`/`apply.py`, no seam.** Rejected: unit tests
  would need the network and a credential, a reviewer would need a Databricks account to run
  anything, and the "repointing is contained" claim would have nowhere to live. The seam is cheap
  precisely because the surface is narrow — six operations, translation only, no decisions.
- **A paid trial workspace for higher fidelity.** Rejected: it adds a credit card and a trial
  clock, and buys nothing the argument needs. Free Edition already gives real API semantics; what
  it does not give (scale, staging, identity groups) a 14-day trial would not have given either.
- **A long-lived personal access token instead of OAuth.** Rejected. A PAT is a durable secret
  that has to live somewhere, and this is a public repository. OAuth user-to-machine stores a
  short-lived refreshable token outside the repository, so the "no personal access tokens" rule
  has teeth rather than being an untested claim: there is no token anywhere to leak. In
  automation, the equivalent would be a service-principal machine-to-machine identity — named in
  `apply.yml`, not built here.

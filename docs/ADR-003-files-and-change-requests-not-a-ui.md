# ADR-003: Files and change requests, not a user interface

- **Status:** Accepted
- **Date:** 2026-09-17
- **Decider:** hector
- **Affects:** `contracts/`, `cli/ucmeta`, `.github/workflows/`, CODEOWNERS-based approval

## Context

Something has to be the authoring surface for a contract. Two families were available: a web
form backed by a service and a database, or plain files in a repository reviewed through the
change-request flow the producers already use.

The design's load-bearing requirements are not about typing comfort. They are: every change is
reviewed by a named human before it reaches the catalogue; sensitivity changes need a second
approver; every change request prints the exact catalogue writes it would perform; apply happens
only on merge; and a bad apply can be reverted. Every one of those is a property of a review
workflow, not of a text input.

## Decision

Files plus change requests are the authoring surface. There is no UI to author metadata.

- One YAML contract per dataset under `contracts/<area>/<dataset>.yaml`, with a JSON Schema
  (`contracts/_schema/contract.schema.json`) and a template beside it.
- The review gate is the platform's change-request flow: `.github/workflows/validate.yml` runs
  the automated checks on every change request — routing the change to its class, validating each
  changed contract, and printing the full planned write set — and approval is expressed as code
  ownership per contract area. (The checks are built and run; the code-owners file itself is a
  named placeholder that is *not* shipped in this repository — see README "What I didn't do".)
- Apply is wired to merge on `main` (`apply.yml`), never to a manual button.
- The only interactive surface is a five-verb command-line tool (`ucmeta`) plus a generated
  static coverage page. No served application anywhere in the prototype.

## Consequences

- Nothing had to be built, hosted, authenticated or secured to get review, approval, diffing,
  history, revert and per-area ownership. That is the single largest budget saving in the
  project, and it bought the guardrails rather than the UI.
- The gate lands where producers already work. A metadata change looks exactly like a code
  change, which is the point: it rides on an existing habit rather than competing with one.
- The honest cost: this excludes non-engineer authors. A data steward or a business owner who
  should be correcting a business-term link is not going to open a pull request. For the
  prototype's users (data teams on a Databricks platform) that is acceptable; for a
  steward-driven glossary it would not be.
- The secondary cost is YAML itself — indentation mistakes and schema-shaped errors that a form
  would have prevented by construction. The mitigation is that `ucmeta validate` fails with
  named, specific problems, and `ucmeta harvest` generates a correct skeleton so nobody starts
  from an empty file.
- Reversibility is good: because the file is the substrate, a form can be added later that writes
  the same YAML and opens the same change request, with no change to the schema, the checks, or
  the applier. The reverse move — starting with a UI and later extracting a reviewable file
  format — is much more expensive, because the review gate would have to be retrofitted onto a
  database.

## Alternatives considered

- **A web authoring form with its own store.** Rejected for now, not forever; named in
  "What I didn't do" as the obvious follow-on. It buys accessibility for non-engineers, and it
  costs a service, a schema migration story, an auth model, and — most importantly — it would
  have made the review gate something to design rather than something to inherit.
- **Authoring in the catalogue UI.** Rejected in ADR-001, for review and audit reasons.
- **Spreadsheet intake, then an importer.** Rejected: it is a form with worse validation and no
  review, and the importer becomes the unreviewed writer to production.
- **A UI *and* files, kept in sync.** Rejected on the same grounds as bidirectional catalogue
  sync (ADR-001): two writers, invented conflict resolution, no single source of truth.

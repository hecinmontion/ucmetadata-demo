# ADR-002: AI proposes, humans approve

- **Status:** Accepted
- **Date:** 2026-09-17
- **Decider:** hector
- **Affects:** `src/uc_metadata/propose.py`, `models.py` (`Proposed`), `validate.py`, `apply.py`

## Context

The barrier to documenting a dataset is not that producers refuse to write descriptions; it is
the blank page. Forty columns with empty description fields is an hour of low-status work with
no immediate payoff, so it never reaches the top of anyone's list. An AI drafter removes almost
all of that cost: column names, types, a small sample of values and the shared glossary are
enough context to produce a plausible first draft of every description, term link and
sensitivity guess in one call.

The opposite force is accountability. Descriptions become the organisation's vocabulary, and
sensitivity classifications drive access decisions. A wrong-but-confident description is worse
than a blank one, because a blank field is visibly missing while a wrong one is quietly
believed. And there is no staging metastore to catch it in — every apply is a production change.

So the drafter has to be fast and useful without ever becoming the thing that decides.

## Decision

The AI proposes; it never publishes.

- Every value the drafter writes is wrapped as `Proposed(value=..., ai_proposed=True)`. The
  module that talks to the model has no code path that marks anything reviewed.
- `validate.py` fails a contract that still carries any unreviewed marker, and names every such
  field by its exact path.
- `apply.py` refuses such a contract **whole** — it does not apply the reviewed fields and skip
  the rest. Partial application would turn a review gate into a suggestion.
- Sensitivity and personal-data classifications need a second, distinct approver. (A design rule
  carried by code ownership on the change request, not by a check in this repository — see
  Consequences.)
- Every proposal reports its economics: model, token counts, dollar cost and wall-clock latency
  are printed and returned as `ProposalMetrics`.
- Sample values are masked before they leave the process (by column name, with an
  email-shaped-value backstop). Numeric surrogate keys are deliberately *not* masked — they
  identify a row, not a person, and the drafter needs them to describe join columns correctly.
- Two model outputs are treated as untrusted input rather than as answers: a proposed business
  term is dropped unless it resolves to a real glossary entry, and dataset sensitivity is
  floored to at least `confidential` if any column came back as personal data, whatever the
  model said.

## Consequences

- The AI is an accelerator, never a critical-path dependency. `harvest`, `validate`, `apply` and
  `coverage` all work with no API key at all; only `propose` needs one, and CI replays recorded
  fixtures so the automated checks are deterministic, offline and free.
- Cost and latency are visible per proposal instead of being an unexamined line item.
- Two parts of the audit story are built and two are not, and the difference matters. Built: the
  per-field `ai_proposed` marker, which blocks apply until cleared, and the append-only release
  record naming who approved each apply (`release_log.jsonl`). Not built: a per-field `reviewed_by`
  attribution, and a persisted proposal audit record holding the prompt and the inputs — the
  metrics are printed and returned, not stored beside the contract. Accountability today therefore
  runs through the change request (who committed, who approved) plus the release record, not
  through the contract file itself. The second-approver rule for sensitivity is likewise carried by
  review, not enforced by a check in this repository.
- The residual risk is reviewer fatigue, not model error: a human who clears forty markers
  without reading them has produced exactly the outcome this ADR is meant to prevent. The
  mitigation built is that the drafter flags where it had to guess between two plausible
  meanings, so attention lands where it matters; the mitigation *not* built is any measurement
  of review quality.
- No prompt-injection test was built (see README "What I didn't do"). The structural defence
  that does exist is this ADR's mechanism: a successful injection produces a bad *suggestion*,
  not a bad catalogue entry, because nothing reaches the catalogue until a human clears the
  marker. Claiming that makes injection harmless would be overstating it; naming the gap is the
  honest position.

## Alternatives considered

- **Auto-publish AI output, review after the fact.** Rejected. There is one global production
  metastore and no staging tier, so "review later" means the organisation's vocabulary and its
  sensitivity labels are whatever a model said until someone notices. The cost of being wrong is
  paid by consumers who cannot tell.
- **No AI at all — humans author from scratch.** Rejected: this is the blank page, i.e. the
  failure mode the whole feature exists to attack. It would also have removed the one part of
  the design the brief most directly probes.
- **Mock the drafter entirely for the prototype.** Rejected. The submission is partly an
  assessment of judgment about AI; a mocked drafter erases exactly that signal. Real calls with
  a small cheap model (`claude-haiku-4-5`), recorded fixtures for CI.
- **Invert it — humans draft, AI reviews.** Rejected: it keeps the blank-page cost (there is
  nothing to review until a human writes it) and moves accountability to the wrong side of the
  boundary.

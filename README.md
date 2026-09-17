# UC Metadata Platform

A prototype for improving metadata quality and coverage on a Databricks + Unity Catalog platform, where data teams own their datasets and a platform team provides shared guardrails.

> Status: early scaffold. Design decisions (what's mocked vs. built) are being finalized — see `docs/` for ADRs as they land.

## Problem

TODO — fill in once the diagnosis is finalized.

## Approach

TODO — one-paragraph framing + architecture diagram.

## Quickstart

TODO — once the CLI exists.

## What's mocked

TODO — filled in as each component's mock-vs-build call is made. See project ADRs in `docs/`.

One call already made and worth stating here rather than only in a workflow
comment: the three CI workflows under `.github/workflows/` (`validate.yml`,
`apply.yml`, `coverage.yml`) always run `ucmeta` against `FakeUCClient`, never
with `--live`. This is a public repo demonstrating a real interview
submission, so a personal Databricks Free Edition credential has no business
being a public-repo GitHub Actions secret — CI proves the gate *mechanism*
(routing, exit codes, apply-on-merge) is real and reproducible for anyone who
forks this repo; the live, `--live`-flagged loop against the real workspace
is a local, human-run demonstration.

**AI-proposed content has not been generated yet in this repo.** `propose.py` is
built, tested (see `tests/unit/test_propose.py`), and proven against
hand-authored fixture responses, but every contract shipped under `contracts/`
was written directly by a human, not drafted by the AI — this build session ran
with no `ANTHROPIC_API_KEY` available, and fabricating what a model "would have
said" into an `ai_proposed: true` field would be worse than leaving the field
human-authored. Before presenting this walkthrough, run `ucmeta propose
contracts/analytics/orders.yaml --in-place` (or against a chosen contract) with a
real `ANTHROPIC_API_KEY` to get a genuine AI-drafted proposal — `orders.state` is
deliberately ambiguous (order status vs. US state abbreviation) and is the best
candidate for demonstrating the drafter's low-confidence-flagging behaviour live.
This is a real, unclosed loop, not a completed part of the build.

## Trade-offs

TODO.

## What I didn't do

TODO.

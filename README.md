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

## Trade-offs

TODO.

## What I didn't do

TODO.

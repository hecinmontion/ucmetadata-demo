# LLM fixtures -- PLACEHOLDERS, not a completed integration

Every `*__PLACEHOLDER_NOT_RECORDED.json` file in this directory is **hand-authored**,
not a real recording of an Anthropic API response. They exist so the offline test
suite (`tests/unit/test_propose.py`) can exercise the full request-build /
structured-output-parse / contract-wiring path end to end without a network call or
an `ANTHROPIC_API_KEY` -- built while working in an environment with no Anthropic
credentials available (see `src/uc_metadata/propose.py`'s module docstring).

They are **structurally valid**: each one is a real `anthropic.types.Message` JSON
body (`id`, `type`, `role`, `model`, `content`, `stop_reason`, `stop_sequence`,
`usage`), and the `content[0].text` field is a real `model_dump_json()` dump of
`propose.py`'s private `_DatasetProposalPayload` structured-output schema, so
`tests/unit/llm_fixture_transport.py`'s replay transport and
`anthropic.Anthropic().messages.parse(...)`'s own JSON-schema parsing both accept
them without any special-casing. What they are **not**: an actual Claude Haiku 4.5
response, with real model judgment, real token counts, or a real dollar cost behind
them. The `usage.input_tokens`/`usage.output_tokens` values are plausible estimates
(cross-checked against the actual prompt text `propose.py` builds for each table),
not measured numbers.

**Shipping the interview submission with only these placeholders would fail the
guide's own "didn't spend $2 to prove they can use one" bar.** A real recording pass
is required before this integration is demonstrated as complete.

## Recording a real fixture

Once a real `ANTHROPIC_API_KEY` is available:

```
LLM_LIVE_TESTS=1 ANTHROPIC_API_KEY=sk-ant-... uv run pytest tests/unit/test_propose.py -m llm_live -v
```

This runs the `llm_live`-marked recording test(s) in `tests/unit/test_propose.py`
(skipped by default; this is the only thing that unskips them), which make one real,
billed call per dataset through `propose()` and overwrite the corresponding
`*__PLACEHOLDER_NOT_RECORDED.json` fixture with the genuine recorded response via
`llm_fixture_transport.build_llm_client`'s record-mode transport.

After recording, do both of the following so the placeholder status cannot be
missed by a later reader:

1. Rename each newly-recorded fixture to drop the `__PLACEHOLDER_NOT_RECORDED`
   suffix (e.g. `customers_propose__PLACEHOLDER_NOT_RECORDED.json` ->
   `customers_propose.json`), and update the fixture-name constants at the top of
   `tests/unit/test_propose.py` to match.
2. Delete this paragraph and the "PLACEHOLDERS, not a completed integration"
   framing above once every fixture referenced by `test_propose.py` is a real
   recording -- a stale placeholder warning next to genuine recordings is its own
   kind of misleading.

## Why record/replay instead of a fully mocked SDK

`tests/unit/llm_fixture_transport.py` intercepts at the HTTP transport layer
(`httpx2.MockTransport` / a wrapped `httpx2.HTTPTransport`), not by stubbing
`anthropic.Anthropic` itself. `propose.py` calls the real SDK's real
`.messages.parse(...)` method, which does its own request-building and
structured-output JSON parsing against whatever body the transport hands back --
so a fixture that does not match the real API's response shape fails the same way
a bad response from the real API would, rather than being silently accepted by a
hand-rolled fake `parse()`.

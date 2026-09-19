# LLM fixtures -- real recordings

`customers_propose.json`, `campaigns_propose.json`, and `orders_propose.json` are real
recorded Anthropic API responses (`claude-haiku-4-5-20251001`), captured on 2026-09-19
via the `llm_live`-marked recording tests in `tests/unit/test_propose.py`, run with a
real `ANTHROPIC_API_KEY`. Each is a genuine `anthropic.types.Message` JSON body with
real `usage.input_tokens`/`usage.output_tokens`, not an estimate.

`tests/unit/llm_fixture_transport.py`'s replay transport intercepts at the HTTP layer
(`httpx2.MockTransport`), not by stubbing `anthropic.Anthropic()` itself -- `propose.py`
still calls the real SDK's real `.messages.parse(...)`, which does its own
request-building and structured-output JSON parsing against whatever body the
transport hands back. A fixture that didn't match the real API's response shape would
fail the same way a bad live response would, not be silently accepted.

The `orders_propose.json` recording independently reproduced the same `state`-column
ambiguity-flagging behaviour (order status vs. US state abbreviation) seen in a live
`ucmeta propose --live` run against the real workspace on the same day -- two separate
real calls, same judgment call, same caveat in the model's own words. That's the
strongest evidence in this repo that the low-confidence-flagging story is genuine
model behaviour, not a scripted demo.

## Re-recording

If `propose.py`'s prompt changes, or the glossary/sample data changes meaningfully,
re-record with a real key:

```
LLM_LIVE_TESTS=1 ANTHROPIC_API_KEY=sk-ant-... uv run pytest tests/unit/test_propose.py -m llm_live -v
```

This overwrites all three fixture files in place with fresh recorded responses. No
rename step is needed this time -- the fixture-name constants in `test_propose.py`
already point at the real filenames.

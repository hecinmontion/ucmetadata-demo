"""A VCR-style record/replay transport for `propose.py`'s Anthropic client,
mirroring the `UC_LIVE_TESTS=1` convention `tests/unit/test_uc_client_contract.py`
already uses for the live Unity Catalog workspace -- here as `LLM_LIVE_TESTS=1`.

Two modes, selected by `build_llm_client`:

- *Replay* (default, no env var, no network, no API key): an `anthropic.Anthropic`
  client wired to an `httpx2.MockTransport` that reads a saved JSON fixture from
  `tests/fixtures/llm/<name>.json` and hands it back as the HTTP response body,
  without ever opening a socket. This is what the offline unit-test suite always
  uses.
- *Record* (`LLM_LIVE_TESTS=1` and a real `ANTHROPIC_API_KEY` set): an
  `anthropic.Anthropic` client wired to a transport that makes one real,
  billed HTTP call to the live Anthropic API and writes the raw JSON response
  body to that same fixture path, so the next replay run sees a genuine
  recording instead of a hand-authored placeholder.

See `tests/fixtures/llm/README.md` for the exact command to run a real
recording pass, and for why the fixtures checked in today are unmistakably
labelled placeholders rather than real recordings.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import anthropic
import httpx2

LLM_LIVE_TESTS_ENABLED = os.environ.get("LLM_LIVE_TESTS") == "1"

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "llm"

# A client built for replay never sends a real request, so this never needs to
# authenticate against anything -- it only has to be a non-empty string so the
# SDK's auth-header resolution has something to attach.
_REPLAY_PLACEHOLDER_API_KEY = "sk-ant-fixture-replay-not-a-real-key"


class _RecordingTransport(httpx2.HTTPTransport):
    """Makes a real HTTP call, then writes the raw JSON response body to
    `fixture_path` before handing the response back to the caller unchanged."""

    def __init__(self, fixture_path: Path) -> None:
        super().__init__()
        self._fixture_path = fixture_path

    def handle_request(self, request: httpx2.Request) -> httpx2.Response:
        response = super().handle_request(request)
        response.read()  # buffer the body so both we and the SDK can read it
        self._fixture_path.parent.mkdir(parents=True, exist_ok=True)
        self._fixture_path.write_text(json.dumps(response.json(), indent=2, sort_keys=True) + "\n")
        return response


def _replay_handler(fixture_path: Path, captured_requests: "list[httpx2.Request] | None"):
    if not fixture_path.exists():
        raise FileNotFoundError(
            f"no recorded or placeholder LLM fixture at {fixture_path}. Either point at an "
            "existing fixture, or run with LLM_LIVE_TESTS=1 and a real ANTHROPIC_API_KEY to "
            "record one -- see tests/fixtures/llm/README.md."
        )
    payload = json.loads(fixture_path.read_text())

    def handler(request: httpx2.Request) -> httpx2.Response:
        if captured_requests is not None:
            captured_requests.append(request)
        return httpx2.Response(200, json=payload, request=request)

    return handler


def build_llm_client(
    fixture_name: str,
    *,
    captured_requests: "list[httpx2.Request] | None" = None,
) -> anthropic.Anthropic:
    """Build an `anthropic.Anthropic` client for `fixture_name`
    (`tests/fixtures/llm/<fixture_name>.json`, no extension needed on the call
    site): record mode if `LLM_LIVE_TESTS=1` and `ANTHROPIC_API_KEY` are both
    set, replay mode otherwise. Either way, `propose.py` never knows the
    difference -- it just calls `.messages.parse(...)` on whatever client it
    was handed.

    In replay mode, pass a list as `captured_requests` to have every outgoing
    `httpx2.Request` appended to it before the canned response is returned --
    this is how a test asserts on what `propose.py` actually sent (e.g. that PII
    sample values reached the request already masked) without needing a real
    request to inspect.
    """
    fixture_path = FIXTURES_DIR / f"{fixture_name}.json"

    if LLM_LIVE_TESTS_ENABLED and os.environ.get("ANTHROPIC_API_KEY"):
        return anthropic.Anthropic(http_client=httpx2.Client(transport=_RecordingTransport(fixture_path)))

    return anthropic.Anthropic(
        api_key=_REPLAY_PLACEHOLDER_API_KEY,
        http_client=httpx2.Client(
            transport=httpx2.MockTransport(_replay_handler(fixture_path, captured_requests))
        ),
    )

# Safety Net and Residue Sweep Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the missing safety net (shared fakes in `tests/conftest.py`, direct wiring-seam tests) and sweep the refactor residue (single-sourced port topology, declarative launcher env injection, dead seams, docs and lint), with zero behavior change, in exactly two commits.

**Architecture:** Commit 1 is pure test infrastructure: fakes duplicated across two or more suites move to `tests/conftest.py` as pytest fixtures (factory fixtures returning the class where tests pass per-test arguments; underscore-named fixtures returning the helper functions so call sites and assertions stay byte-identical), and `tests/test_wiring.py` gains direct characterization tests for `bind_a2a_routes` and `ReplyArtifactStream`. Commit 2 is a mechanical residue sweep: port constants and derived default URLs single-source in `wiring.py`; host config fail-fast gets a named exception subclassing `RuntimeError`; the dead `system_prompt` seam is dropped from `llm.py`; `demo.py`'s env injection becomes declarative via `CHILDREN` triples; `ruff` is pinned as a dev-only dependency with `E`/`F`/`I` and its findings fixed.

**Tech Stack:** Python 3.13, uv, pytest + pytest-asyncio (asyncio auto mode, importlib import mode, no `__init__.py` under `tests/`), FastAPI + a2a-sdk, httpx, ruff (dev-only).

**Spec:** docs/superpowers/specs/2026-11-27-safety-net-and-residue-sweep-design.md

## Global Constraints

- No behavior change: env names (`A2A_POC_PORT`, `CHAT_AGENT_URL`, `SEARCH_AGENT_URL`, `OPENCODE_API_KEY`, `A2A_POC_DECISION_MODEL`, `LLM_*`, `TAVILY_API_KEY`), ports 9997/9998/9999, URLs, defaults, error messages, exit codes, and stdout shapes are all byte-identical before and after.
- The 62 existing tests stay green throughout, with assertions byte-identical wherever tests move; the suite grows to 70 by the end (4 wiring-seam tests, 1 URL-topology test, 1 host-config test, 2 launcher-env tests).
- Exactly two implementation commits (`test: consolidate shared fakes into conftest, pin wiring seams directly`, then `refactor: single-source port topology and sweep refactor residue`), both in pathspec form listing every changed file, so nothing else in the working tree can be swept in.
- `ruff` is a dev-only dependency (the `[dependency-groups] dev` group plus a `[tool.ruff]` section; never in `[project] dependencies`).
- Non-goals: no scaffold dedup, no `stream_reply` decomposition, no client-lifecycle changes, no narrowing of any `except` clause.

## Review Focus

- Ambient `A2A_POC_PORT` when running an agent standalone still overrides the bind port — pinned by the existing `test_resolve_bind_env_override` in `tests/test_wiring.py`, kept green by Task 3's full-suite run (Task 3 owns the code, must not touch `resolve_bind` semantics).
- Missing `OPENCODE_API_KEY` at host startup still fails fast with the byte-identical message — pinned by the new `test_main_missing_opencode_api_key_fails_fast` in `tests/host/test_app.py` (Task 4).
- Launcher ignores ambient agent-URL env vars because injection is explicit — pinned by the new `test_host_agent_url_injection_overrides_ambient` in `tests/test_demo.py` (Task 6).
- Import-sort drift in future edits gets caught — pinned by the `uv run ruff check .` gate (Task 7).
- A test file silently keeping a private copy of a moved fake — pinned by Task 1's grep single-definition check (Step 10).

---

### Task 1: Shared test fixtures in `tests/conftest.py`

**Files:**
- Create: `tests/conftest.py`
- Modify: `tests/chat/test_executor.py` (delete lines 22-45, fixture-inject bodies, trim imports)
- Modify: `tests/search/test_executor.py` (delete lines 23-34 and 41-50, keep `_artifact_events`, fixture-inject bodies, trim imports)
- Modify: `tests/host/test_executor.py` (delete lines 58-69, 84-90, and 97-98, keep `FakeDecider`/`FakeStream`/`_status_states`/`_completed`/`_failed`/`_working`/`_no_search`, fixture-inject bodies, trim imports)
- Modify: `tests/client/test_core.py` (delete lines 23-46, `_collect` becomes a local fixture, trim imports)
- Modify: `tests/client/test_cli.py` (delete lines 43-66, fixture-inject one test, trim imports)
- Modify: `tests/search/test_app.py` (delete lines 7-10, `_app` takes the fake class, fixture-inject both tests)
- Modify: `tests/search/test_tavily_client.py` (delete lines 4-17, fixture-inject constructions)
- Modify: `tests/host/test_decision.py:37-46,50` (rename `FakeClient` → `FakePostClient`)
- Modify: `tests/test_llm.py:50-52,56,62,71` (rename `FakeClient` → `FakeOpenAIClient`)

**Interfaces:**
- Consumes: the existing fake definitions (bodies copied verbatim into conftest): `FakeEventQueue`, `ScriptedClient`, `_card_transport`, `FakeTavilyClient` (the configurable variant from `tests/search/test_tavily_client.py`), and the `_context`/`_artifact_text`/`_final_state` helper bodies.
- Produces: `tests/conftest.py` fixtures usable by every test under `tests/`:
  - `queue() -> FakeEventQueue` (fresh instance; records `events`)
  - `_context() -> Callable[[str], SimpleNamespace]` (builds `message=new_text_message(text, role=Role.ROLE_USER), current_task=None`)
  - `_artifact_text() -> Callable[[list], str]` (joins all artifact part texts)
  - `_final_state() -> Callable[[list], int]` (last status state)
  - `scripted_client() -> type[ScriptedClient]` (factory: tests call `scripted_client(events)`)
  - `_card_transport() -> Callable[[], httpx.MockTransport]` (serves the chat agent card)
  - `fake_tavily_client() -> type[FakeTavilyClient]` (factory: tests call `fake_tavily_client(response=..., error=...)`)
  - Renamed single-file fakes (not in conftest — each appears in only one file): `FakePostClient` in `tests/host/test_decision.py`, `FakeOpenAIClient` in `tests/test_llm.py` (the two `FakeClient` classes fake different protocols — httpx `post` vs OpenAI `chat.completions` — so they are renamed in place, not consolidated; afterwards no fake name is defined twice under `tests/`).

Underscore-prefixed fixture names are deliberate: tests already call these helpers by those names, so request them as test parameters and the call sites — including lines inside assertions — stay byte-identical. (Verified against this repo's exact pytest config: importlib import mode, asyncio auto mode, `tests/`-level conftest.)

- [ ] **Step 1: Create `tests/conftest.py` with the fakes and fixtures**

```python
"""Shared test fakes: the stand-ins duplicated across two or more suites.

FakeEventQueue and the _context/_artifact_text/_final_state helpers come
from the chat/search/host executor suites; ScriptedClient and its card
transport from the two client suites; FakeTavilyClient from the two
search suites. Using tests keep their assertions byte-identical; only
construction becomes fixture injection.
"""

from types import SimpleNamespace

import httpx
import pytest
from a2a.helpers import new_text_message
from a2a.types import Role
from google.protobuf.json_format import MessageToJson

from a2apoc.chat.card import build_agent_card


class FakeEventQueue:
    def __init__(self):
        self.events = []

    async def enqueue_event(self, event):
        self.events.append(event)


class ScriptedClient:
    """Stand-in for ``a2a.client.Client`` that replays a scripted event stream."""

    def __init__(self, events):
        self._events = events

    async def send_message(self, request):
        for event in self._events:
            yield event

    async def close(self):
        pass


class FakeTavilyClient:
    """Duck-typed stand-in for ``tavily.AsyncTavilyClient``."""

    def __init__(self, response=None, error=None):
        self._response = response
        self._error = error
        self.calls = []

    async def search(self, query, **kwargs):
        self.calls.append((query, kwargs))
        if self._error:
            raise self._error
        return self._response


@pytest.fixture
def queue() -> FakeEventQueue:
    return FakeEventQueue()


@pytest.fixture
def _context():
    def make(text: str):
        return SimpleNamespace(
            message=new_text_message(text, role=Role.ROLE_USER), current_task=None
        )

    return make


@pytest.fixture
def _artifact_text():
    def make(events):
        parts = []
        for e in events:
            artifact = getattr(e, "artifact", None)
            if artifact is not None:
                parts.extend(p.text for p in artifact.parts)
        return "".join(parts)

    return make


@pytest.fixture
def _final_state():
    def make(events):
        states = [e.status.state for e in events if hasattr(e, "status")]
        return states[-1]

    return make


@pytest.fixture
def scripted_client() -> type[ScriptedClient]:
    return ScriptedClient


@pytest.fixture
def _card_transport():
    def make():
        """Transport whose only answer is a well-formed agent card."""
        card_json = MessageToJson(build_agent_card("http://127.0.0.1:9999"))

        def _serve_card(request):
            return httpx.Response(
                200, content=card_json, headers={"content-type": "application/json"}
            )

        return httpx.MockTransport(_serve_card)

    return make


@pytest.fixture
def fake_tavily_client() -> type[FakeTavilyClient]:
    return FakeTavilyClient
```

- [ ] **Step 2: Convert `tests/chat/test_executor.py`**

Delete the `FakeEventQueue` class and the `_context`/`_artifact_text`/`_final_state` function definitions. In every test: delete the `queue = FakeEventQueue()` line, add to the def's parameter list exactly the fixtures its body uses (`queue` where it constructed the queue; `_context`/`_final_state`/`_artifact_text` where the body calls them; `caplog` stays as-is), and when the grown def line exceeds 88 characters wrap it parenthesized. Remove the imports that only the deleted code used: `from types import SimpleNamespace`, `from a2a.helpers import new_text_message`, and `Role` from the `a2a.types` import (keep `import logging` and `from a2a.types import TaskState`). Worked example (the others follow the same rule):

```python
async def test_executor_streams_deltas_and_completes(
    queue, _context, _final_state, _artifact_text
):
    executor = ChatAgentExecutor(agent=FakeAgent(chunks=["Hel", "lo"]))
    await executor.execute(_context("hi"), queue)
    assert _final_state(queue.events) == TaskState.TASK_STATE_COMPLETED
    assert _artifact_text(queue.events) == "Hello"
```

Run: `uv run pytest tests/chat/test_executor.py -q`
Expected: `5 passed` (assertions byte-identical; only construction became injection).

- [ ] **Step 3: Convert `tests/search/test_executor.py`**

Same rule as Step 2, additionally: keep `_artifact_events` and `FakeSearcher` in place (single-file helpers), and delete the local `_artifact_text` (its body routed through `_artifact_events`, but the shared fixture computes the identical result on these events, so the assertions keep their meaning and bytes). Trim the same three imports.

Run: `uv run pytest tests/search/test_executor.py -q`
Expected: `3 passed`

- [ ] **Step 4: Convert `tests/host/test_executor.py`**

Delete `FakeEventQueue`, `_context`, `_artifact_text`, and `_final_state`. Keep `FakeDecider`, `FakeStream`, `_completed`/`_failed`/`_working`, `_status_states`, `_status_texts`, `_no_search` (all single-file). Each test's def gains the fixtures its body uses (all six use `queue`, `_context`, `_final_state`; scenarios 1-5 also `_artifact_text`); wrap over-long defs. Remove `from types import SimpleNamespace`, `from a2a.helpers import new_text_message`, and `Role` from the `a2a.types` import.

Run: `uv run pytest tests/host/test_executor.py -q`
Expected: `6 passed`

- [ ] **Step 5: Convert `tests/client/test_core.py`**

Delete the `ScriptedClient` class and `_card_transport` function. Replace the module-level `_collect(events)` helper with a local fixture (call sites `await _collect(events)` stay byte-identical):

```python
@pytest.fixture
def _collect(scripted_client, _card_transport):
    """Collect stream_reply events with a scripted client and card transport."""

    async def collect(events):
        async def factory(card):
            return scripted_client(events)

        received = []
        async for event in stream_reply(
            "http://127.0.0.1:9999",
            "hi",
            httpx_client=httpx.AsyncClient(transport=_card_transport()),
            client_factory=factory,
        ):
            received.append(event)
        return received

    return collect
```

The two direct scripted tests (`test_core_yields_deltas_and_status_in_order`, `test_core_failed_task_ends_without_systemexit_and_prints_nothing`) gain `(scripted_client, _card_transport)` and their `factory` closures change `ScriptedClient(events)` → `scripted_client(events)`. The three `_collect` tests gain `(_collect)`. The `A2A_POC_TIMEOUT` and connection-error tests are untouched. Add `import pytest` (already present) and remove `from google.protobuf.json_format import MessageToJson` and `from a2apoc.chat.card import build_agent_card` (only the moved transport used them).

Run: `uv run pytest tests/client/test_core.py -q`
Expected: `9 passed`

- [ ] **Step 6: Convert `tests/client/test_cli.py`**

Delete the `ScriptedClient` class and `_card_transport` function. `test_client_failed_task_prints_reason_and_exits_nonzero` gains `(scripted_client, _card_transport)` and its factory closure changes `ScriptedClient(events)` → `scripted_client(events)`. Remove `from google.protobuf.json_format import MessageToJson` and `from a2apoc.chat.card import build_agent_card`.

Run: `uv run pytest tests/client/test_cli.py -q`
Expected: `4 passed`

- [ ] **Step 7: Convert `tests/search/test_app.py` and `tests/search/test_tavily_client.py`**

`tests/search/test_app.py`: delete the local `FakeTavilyClient` (the trivial variant); the shared configurable fake replaces it — construct it with the empty response to preserve behavior: `fake_tavily_client(response={"results": []})`. `_app` takes the fake class as a parameter; both tests gain `(fake_tavily_client)`:

```python
def _app(fake_tavily_client):
    return create_search_app(
        searcher=TavilySearcher(fake_tavily_client(response={"results": []}))
    )


def test_agent_card_route_serves_card(fake_tavily_client):
    client = TestClient(_app(fake_tavily_client))
    ...
```

`test_create_search_app_port_flows_into_card` similarly gains `(fake_tavily_client)` and wraps its `TestClient(create_search_app(...))` construction across lines (the current one-line form is 98 characters). `tests/search/test_tavily_client.py`: delete the `FakeTavilyClient` class, each test gains `(fake_tavily_client)`, and the four constructions change `FakeTavilyClient(response=...)` → `fake_tavily_client(response=...)`. `_response` stays local.

Run: `uv run pytest tests/search/test_app.py tests/search/test_tavily_client.py -q`
Expected: `5 passed`

- [ ] **Step 8: Disambiguate the two unrelated `FakeClient` classes (rename in place)**

`tests/host/test_decision.py`: rename the class `FakeClient` → `FakePostClient` (it duck-types `httpx.AsyncClient.post`); the only reference is inside the `_decider` helper — update class def and that one line. `tests/test_llm.py`: rename the class `FakeClient` → `FakeOpenAIClient` (it duck-types `AsyncOpenAI` via `.chat.completions`); update the class def and its three construction sites. Neither moves to conftest (each lives in one file); the renames exist so no fake name is defined in two test files.

Run: `uv run pytest tests/host/test_decision.py tests/test_llm.py -q`
Expected: `14 passed` (9 + 5)

- [ ] **Step 9: Run the whole suite**

Run: `uv run pytest -q`
Expected: `62 passed` (same count; no new tests yet)

- [ ] **Step 10: Prove each moved fake is defined exactly once**

```bash
for name in "class FakeEventQueue" "class ScriptedClient" "class FakeTavilyClient" \
            "def _context" "def _artifact_text" "def _final_state" "def _card_transport"; do
  echo "== $name"; grep -rn "$name" tests/ --include="*.py"
done
grep -rn "class FakeClient" tests/ --include="*.py"
```

Expected: exactly one hit for each of the seven names, all in `tests/conftest.py`; the final grep prints nothing (both `FakeClient`s renamed).

### Task 2: Direct wiring-seam characterization tests (ends commit 1)

**Files:**
- Modify: `tests/test_wiring.py` (append after the existing `resolve_bind` tests)

**Interfaces:**
- Consumes: `bind_a2a_routes(app: FastAPI, agent_card: AgentCard, request_handler: DefaultRequestHandler) -> FastAPI`; `ReplyArtifactStream` with `async push(updater: TaskUpdater, delta: str)`, `async finish(updater)`, `async flush_partial(updater)`; `a2apoc.chat.card.build_agent_card(base_url: str) -> AgentCard`; `AGENT_CARD_WELL_KNOWN_PATH`, `DEFAULT_RPC_URL` from `a2a.utils`.
- Produces: commit 1 — `test: consolidate shared fakes into conftest, pin wiring seams directly` — containing Task 1 + Task 2 changes.

These tests pin **existing** behavior (verified against the current code): they should pass immediately once written. If one fails, the test misreads the behavior — investigate and fix the **test**, not `wiring.py`.

- [ ] **Step 1: Write the four characterization tests**

Add imports (merged into the file's import block, ruff-sorted):

```python
import pytest
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.utils import AGENT_CARD_WELL_KNOWN_PATH, DEFAULT_RPC_URL
from fastapi import FastAPI

from a2apoc.chat.card import build_agent_card
from a2apoc.wiring import HOST, ReplyArtifactStream, bind_a2a_routes, resolve_bind
```

Add two single-use fakes and the tests:

```python
class _StubExecutor:
    """Executor stand-in: routes are attached, never exercised."""

    async def execute(self, context, event_queue):
        raise NotImplementedError


class _RecordingUpdater:
    """TaskUpdater stand-in recording add_artifact calls as kwargs dicts."""

    def __init__(self):
        self.calls = []

    async def add_artifact(self, parts, **kwargs):
        self.calls.append({"parts": [p.text for p in parts], **kwargs})


def test_bind_a2a_routes_attaches_card_and_jsonrpc_routes():
    card = build_agent_card("http://127.0.0.1:9999")
    handler = DefaultRequestHandler(
        agent_executor=_StubExecutor(),
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )
    app = FastAPI()

    result = bind_a2a_routes(app, card, handler)

    assert result is app
    paths = {route.path for route in app.routes}
    assert AGENT_CARD_WELL_KNOWN_PATH in paths
    assert DEFAULT_RPC_URL in paths


async def test_reply_stream_push_finish_emits_two_chunks_sharing_one_artifact():
    stream = ReplyArtifactStream()
    updater = _RecordingUpdater()

    await stream.push(updater, "a")
    await stream.push(updater, "b")
    await stream.finish(updater)

    first, second = updater.calls
    assert first["parts"] == ["a"]
    assert first["append"] is False
    assert first["last_chunk"] is None
    assert second["parts"] == ["b"]
    assert second["append"] is True
    assert second["last_chunk"] is True
    assert first["artifact_id"] == second["artifact_id"]
    assert first["name"] == second["name"] == "reply"


async def test_reply_stream_flush_partial_never_flags_last_chunk():
    stream = ReplyArtifactStream()
    updater = _RecordingUpdater()

    await stream.push(updater, "a")
    await stream.flush_partial(updater)

    (call,) = updater.calls
    assert call["parts"] == ["a"]
    assert call["append"] is False
    assert call["last_chunk"] is None


async def test_reply_stream_finish_and_flush_on_empty_stream_are_noops():
    stream = ReplyArtifactStream()
    updater = _RecordingUpdater()

    await stream.finish(updater)
    await stream.flush_partial(updater)

    assert updater.calls == []
```

- [ ] **Step 2: Run the new tests (they pass immediately — characterization)**

Run: `uv run pytest tests/test_wiring.py -v`
Expected: `7 passed` — the 3 existing `resolve_bind` tests plus the 4 new ones, all green on the first run. If a new test fails, the test is wrong: re-read `wiring.py` and fix the test.

- [ ] **Step 3: Run the whole suite**

Run: `uv run pytest -q`
Expected: `66 passed`

- [ ] **Step 4: Commit commit 1 (pathspec form; stage the new conftest first)**

```bash
git add tests/conftest.py
git commit tests/conftest.py tests/chat/test_executor.py tests/client/test_cli.py \
  tests/client/test_core.py tests/host/test_decision.py tests/host/test_executor.py \
  tests/search/test_app.py tests/search/test_executor.py tests/search/test_tavily_client.py \
  tests/test_llm.py tests/test_wiring.py \
  -m "test: consolidate shared fakes into conftest, pin wiring seams directly"
```

Expected: one commit containing exactly those 11 test files; `git status` still shows any unrelated staged file (e.g. `README.md`) untouched.

### Task 3: Port topology in `wiring.py`

**Files:**
- Modify: `src/a2apoc/wiring.py:19-21` (constant block)
- Modify: `src/a2apoc/chat/app.py:11-13`
- Modify: `src/a2apoc/search/app.py:12-14`
- Modify: `src/a2apoc/host/app.py:16,18,25-26` (import, `PORT`, delete the two URL constants)
- Modify: `src/a2apoc/client/core.py:18` (import + `DEFAULT_BASE_URL`)
- Modify: `src/a2apoc/demo.py:27-32` (repoint the URL import — required to keep the suite green, since `tests/test_demo.py` imports `a2apoc.demo`)
- Test: `tests/test_wiring.py` (one new test)

**Interfaces:**
- Consumes: `HOST = "127.0.0.1"` (already in `wiring.py`).
- Produces (used by Tasks 6, 7, 8): in `wiring.py` — `CHAT_PORT = 9999`, `SEARCH_PORT = 9997`, `HOST_PORT = 9998`, `DEFAULT_CHAT_AGENT_URL = f"http://{HOST}:{CHAT_PORT}"`, `DEFAULT_SEARCH_AGENT_URL = f"http://{HOST}:{SEARCH_PORT}"`. Env-var *names* stay with their owners (`host/app.py` keeps `CHAT_AGENT_URL_ENV`, `SEARCH_AGENT_URL_ENV`, `OPENCODE_API_KEY_ENV`, `DECISION_MODEL_ENV`); topology moves, config interfaces don't.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_wiring.py` (and add `DEFAULT_CHAT_AGENT_URL`, `DEFAULT_SEARCH_AGENT_URL` to the `a2apoc.wiring` import — wrap that import parenthesized across lines once it exceeds 88 characters):

```python
def test_default_agent_urls_pin_topology():
    assert DEFAULT_CHAT_AGENT_URL == "http://127.0.0.1:9999"
    assert DEFAULT_SEARCH_AGENT_URL == "http://127.0.0.1:9997"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_wiring.py::test_default_agent_urls_pin_topology -q`
Expected: FAIL with `ImportError: cannot import name 'DEFAULT_CHAT_AGENT_URL' from 'a2apoc.wiring'`

- [ ] **Step 3: Implement the constants and update every importer**

In `src/a2apoc/wiring.py`, extend the constant block after `PORT_ENV_VAR`:

```python
CHAT_PORT = 9999
SEARCH_PORT = 9997
HOST_PORT = 9998

DEFAULT_CHAT_AGENT_URL = f"http://{HOST}:{CHAT_PORT}"
DEFAULT_SEARCH_AGENT_URL = f"http://{HOST}:{SEARCH_PORT}"
```

Then: `chat/app.py` — `PORT = CHAT_PORT` (import `CHAT_PORT`); `search/app.py` — `PORT = SEARCH_PORT`; `host/app.py` — `PORT = HOST_PORT`, delete the two `DEFAULT_*_AGENT_URL` literal definitions and import them from `wiring` instead (wrap the grown `from a2apoc.wiring import (...)` parenthesized); `client/core.py` — `from a2apoc.wiring import HOST, HOST_PORT` and `DEFAULT_BASE_URL = f"http://{HOST}:{HOST_PORT}"` (value unchanged: `http://127.0.0.1:9998`); `demo.py` — change its import to `from a2apoc.host.app import CHAT_AGENT_URL_ENV, SEARCH_AGENT_URL_ENV` plus `from a2apoc.wiring import DEFAULT_CHAT_AGENT_URL, DEFAULT_SEARCH_AGENT_URL` (the `if name == "host":` injection keeps working until Task 6 restructures it).

- [ ] **Step 4: Run the tests and the port-literal grep**

Run: `uv run pytest -q`
Expected: `67 passed`

Run: `grep -rn "999[789]" --include="*.py" src/`
Expected: exactly three hits, all in `src/a2apoc/wiring.py` (the `CHAT_PORT`/`SEARCH_PORT`/`HOST_PORT` lines).

### Task 4: Host config error and shared decision timeout

**Files:**
- Modify: `src/a2apoc/host/app.py` (new exception class; raise site at lines 56-60; httpx client at lines 64-67; import line 14)
- Modify: `src/a2apoc/host/decision.py:22,63` (rename `_DEFAULT_TIMEOUT` → `DEFAULT_TIMEOUT`)
- Test: `tests/host/test_app.py` (one new test; note: the current file pins nothing about the error — this test is what pins Review Focus #2)

**Interfaces:**
- Consumes: the existing error message text (byte-identical constraint).
- Produces: `class HostConfigError(RuntimeError)` in `a2apoc.host.app`; `DEFAULT_TIMEOUT = httpx.Timeout(30.0)` in `a2apoc.host.decision` (public; used by `OpenCodeDecider.__init__`'s `timeout` default and by `host/app.py`'s client construction).

- [ ] **Step 1: Write the failing test**

Append to `tests/host/test_app.py` (the repo root has a real `.env` containing `OPENCODE_API_KEY`, so the test must stub `load_dotenv` — `main()` calls it before the check):

```python
def test_main_missing_opencode_api_key_fails_fast(monkeypatch):
    monkeypatch.setattr("a2apoc.host.app.load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("OPENCODE_API_KEY", raising=False)
    with pytest.raises(HostConfigError) as excinfo:
        main()
    assert str(excinfo.value) == (
        "Missing required environment variable: OPENCODE_API_KEY. "
        "Copy .env.example to .env and fill in values."
    )
    assert isinstance(excinfo.value, RuntimeError)
```

Change the file's existing import to `from a2apoc.host.app import HostConfigError, create_host_app, main` and add `import pytest`.

Run: `uv run pytest tests/host/test_app.py::test_main_missing_opencode_api_key_fails_fast -q`
Expected: FAIL with `ImportError: cannot import name 'HostConfigError' from 'a2apoc.host.app'`

- [ ] **Step 2: Implement `HostConfigError` and the raise**

In `src/a2apoc/host/app.py`, define (after the env-var constant block, before `Decider`):

```python
class HostConfigError(RuntimeError):
    """Raised when the host's required environment variables are missing."""
```

In `main()`, change `raise RuntimeError(...)` to `raise HostConfigError(...)` with the message text byte-identical (same f-string, same line breaks).

- [ ] **Step 3: Rename the timeout constant and reuse it**

In `src/a2apoc/host/decision.py`: `_DEFAULT_TIMEOUT` → `DEFAULT_TIMEOUT` (both the definition and the `OpenCodeDecider.__init__` default). In `src/a2apoc/host/app.py`: extend the decision import (the single-line form exceeds 88 characters, so wrap it parenthesized):

```python
from a2apoc.host.decision import (
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT,
    Decision,
    OpenCodeDecider,
)
```

and build the client as `httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, headers={"Authorization": f"Bearer {api_key}"})`, deleting the duplicated `httpx.Timeout(30.0)` literal.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest -q`
Expected: `68 passed`

### Task 5: Drop the dead `system_prompt` seam in `llm.py`

**Files:**
- Modify: `src/a2apoc/llm.py:67-70,78,92-102` (both signatures, the attribute, the stale docstring)

**Interfaces:**
- Produces: `ChatAgent.__init__(self, client, model: str)` (prompt is always `SYSTEM_PROMPT`, referenced directly in `stream_reply`'s messages list) and `build_chat_agent(config: Config) -> ChatAgent`.

- [ ] **Step 1: Grep to confirm no caller passes `system_prompt`**

Run: `grep -rn "system_prompt" src/ tests/ --include="*.py"`
Expected: 7 hits — 6 in `src/a2apoc/llm.py` (the two signatures, the attribute assignment, the message construction, the docstring, the forwarding kwarg) plus `tests/test_llm.py:70`'s **test name** (`test_stream_reply_sends_system_prompt_user_text_and_model` — a name, not a call site). Zero call sites pass the kwarg, so removal is safe. If any real caller appears, stop and reconsider.

- [ ] **Step 2: Drop the parameter and fix the stale docstring**

`ChatAgent.__init__` becomes `def __init__(self, client, model: str):` (delete the `system_prompt` parameter and the `self._system_prompt` attribute; `stream_reply`'s system message becomes `{"role": "system", "content": SYSTEM_PROMPT}`). `build_chat_agent` becomes `def build_chat_agent(config: Config) -> ChatAgent:` with the docstring reduced to its accurate first line — `"""Build a ChatAgent with a real AsyncOpenAI client from Config."""` — deleting the stale paragraph (it documents an override that no longer exists and cites "the host's decider prompt", removed 2026-11-25); drop `system_prompt=system_prompt` from the `ChatAgent(...)` call.

- [ ] **Step 3: Run the tests and the residue grep**

Run: `uv run pytest -q`
Expected: `68 passed` (no caller passed the parameter, so no test changes)

Run: `grep -rn "system_prompt" src/ --include="*.py"`
Expected: no hits.

### Task 6: Declarative env injection in `demo.py`

**Files:**
- Modify: `src/a2apoc/demo.py:27-67` (imports, `CHILDREN`, `_spawn`), `:70-78` (`_stream` guard), `:1-20` (module docstring phrase)
- Test: `tests/test_demo.py` (two new tests, mirroring the file's existing monkeypatched `create_subprocess_exec` pattern)

**Interfaces:**
- Consumes: `a2apoc.wiring.DEFAULT_CHAT_AGENT_URL`, `DEFAULT_SEARCH_AGENT_URL`, `PORT_ENV_VAR`; `a2apoc.host.app.CHAT_AGENT_URL_ENV`, `SEARCH_AGENT_URL_ENV`.
- Produces: `CHILDREN: tuple[tuple[str, str, dict[str, str]], ...]` — `(name, module, extra_env)` triples, empty dict for the non-host children, the host's env mapping for the host; `_spawn(name: str, module: str, extra_env: dict[str, str]) -> asyncio.subprocess.Process`.

- [ ] **Step 1: Write the two failing tests**

Append to `tests/test_demo.py` (reusing its `_FakeProcess`; import the wiring constants):

```python
async def test_host_child_env_carries_default_agent_urls(monkeypatch):
    envs = []

    async def fake_exec(*args: Any, **kwargs: Any) -> _FakeProcess:
        envs.append(kwargs.get("env"))
        return _FakeProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.delenv("CHAT_AGENT_URL", raising=False)
    monkeypatch.delenv("SEARCH_AGENT_URL", raising=False)
    monkeypatch.setenv("A2A_POC_PORT", "7777")

    for name, module, extra_env in demo.CHILDREN:
        await demo._spawn(name, module, extra_env)

    assert envs[2]["CHAT_AGENT_URL"] == DEFAULT_CHAT_AGENT_URL
    assert envs[2]["SEARCH_AGENT_URL"] == DEFAULT_SEARCH_AGENT_URL
    for env in envs[:2]:
        assert "CHAT_AGENT_URL" not in env
        assert "SEARCH_AGENT_URL" not in env
    assert all("A2A_POC_PORT" not in env for env in envs)


async def test_host_agent_url_injection_overrides_ambient(monkeypatch):
    envs = []

    async def fake_exec(*args: Any, **kwargs: Any) -> _FakeProcess:
        envs.append(kwargs.get("env"))
        return _FakeProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setenv("CHAT_AGENT_URL", "http://ambient:1")
    monkeypatch.setenv("SEARCH_AGENT_URL", "http://ambient:2")

    for name, module, extra_env in demo.CHILDREN:
        await demo._spawn(name, module, extra_env)

    assert envs[2]["CHAT_AGENT_URL"] == DEFAULT_CHAT_AGENT_URL
    assert envs[2]["SEARCH_AGENT_URL"] == DEFAULT_SEARCH_AGENT_URL
```

Add `from a2apoc.wiring import DEFAULT_CHAT_AGENT_URL, DEFAULT_SEARCH_AGENT_URL` to the imports.

Run: `uv run pytest tests/test_demo.py -q`
Expected: `1 passed, 2 failed` — both new tests fail with `ValueError: not enough values to unpack (expected 3, got 2)` (today's `CHILDREN` entries are pairs).

- [ ] **Step 2: Implement the declarative injection**

Change `CHILDREN` to triples (env names from `a2apoc.host.app`, URLs and `PORT_ENV_VAR` from `a2apoc.wiring` — wrap the wiring import parenthesized):

```python
# (log prefix, module, extra env) for each child, in spawn order.
CHILDREN: tuple[tuple[str, str, dict[str, str]], ...] = (
    ("search", "a2apoc.search.app", {}),
    ("chat", "a2apoc.chat.app", {}),
    (
        "host",
        "a2apoc.host.app",
        {
            CHAT_AGENT_URL_ENV: DEFAULT_CHAT_AGENT_URL,
            SEARCH_AGENT_URL_ENV: DEFAULT_SEARCH_AGENT_URL,
        },
    ),
)
```

`_spawn` takes `extra_env: dict[str, str]`, replaces the `if name == "host":` block with an unconditional `env.update(extra_env)`, and pops the port via the wiring constant: `env.pop(PORT_ENV_VAR, None)` (update its docstring accordingly: each child's `extra_env` is applied explicitly on top). `_supervise`'s spawn loop unpacks three values: `for name, module, extra_env in CHILDREN:`. In `_stream`, replace `assert proc.stdout is not None` with:

```python
    if proc.stdout is None:
        # _spawn always pipes stdout; anything else is a launcher bug.
        raise RuntimeError(f"child {name} was spawned without piped stdout")
```

In the module docstring, change "(the spec defaults, imported from the host module)" to "(the spec defaults, imported from wiring)".

- [ ] **Step 3: Run the tests**

Run: `uv run pytest -q`
Expected: `70 passed`

### Task 7: Docs, ruff pin, dead-file sweep (ends commit 2)

**Files:**
- Modify: `.env.example:13`
- Delete: `tests/resources/test.http` (unreferenced anywhere; not collected)
- Modify: `pyproject.toml` (dev group + `[tool.ruff]` section), `uv.lock` (regenerated by uv)
- Modify: whatever the ruff findings name (see Step 4)

**Interfaces:**
- Consumes: all constants from Tasks 3-6.
- Produces: commit 2 — `refactor: single-source port topology and sweep refactor residue` — containing Tasks 3-7 changes; a clean `uv run ruff check .` gate for the future.

- [ ] **Step 1: Fix the stale model name in `.env.example`**

Line 13: `# A2A_POC_DECISION_MODEL=jev-1.14` → `# A2A_POC_DECISION_MODEL=gemini-decision-1`

- [ ] **Step 2: Delete the unreferenced scratch file**

Run: `git rm tests/resources/test.http`
Expected: `rm 'tests/resources/test.http'` (it is referenced by nothing — verified: no source, test, config, or README mention).

- [ ] **Step 3: Pin ruff as a dev dependency with a minimal rule set**

In `pyproject.toml`'s `[dependency-groups] dev` list add `"ruff>=0.17"`, and append a section:

```toml
[tool.ruff]
select = ["E", "F", "I"]
```

- [ ] **Step 4: Run ruff and fix everything it reports**

Run: `uv run ruff check .` (uv auto-syncs, which updates `uv.lock` — that file belongs in the commit).
Expected first run: **10 findings** — 6 `I001` (import sorting; auto-fixable) in `src/a2apoc/client/{cli,core,ui}.py`, `tests/client/test_cli.py`, `tests/client/test_core.py`, `tests/test_llm.py`, plus 4 `E501` (line too long, 88 default) in `src/a2apoc/search/card.py:22`, `tests/chat/test_executor.py:66`, `tests/test_llm.py:28` and `:56`. If a few more `E501` appear (e.g. a def line that grew past 88 in earlier tasks), wrap those the same way — the gate is a clean check, not the exact count.

Run: `uv run ruff check --fix .`
Expected: the 6 import-sort findings are fixed (pure reordering/blank-line merging, verified against the current tree; no code moves).

Then wrap the 4 long lines manually (string-wrap for the card description; parenthesized wraps for the constructor calls — all are construction/helper lines, none are assertion lines, so the byte-identical-assertion constraint holds):

```python
# src/a2apoc/search/card.py:22
        description=(
            "One Tavily-backed web search agent exposed over A2A (proof of concept)."
        ),
```

```python
# tests/chat/test_executor.py:66
    executor = ChatAgentExecutor(
        agent=FakeAgent(error=RuntimeError("boom: 401 Unauthorized"))
    )
```

```python
# tests/test_llm.py:28
def _chunk(text: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content=text))]
    )
```

```python
# tests/test_llm.py:56 (FakeOpenAIClient after Task 1's rename)
    agent = ChatAgent(
        client=FakeOpenAIClient([_chunk("Hel"), _chunk("lo")]), model="test-model"
    )
```

Run: `uv run ruff check .`
Expected: `All checks passed!` (no `BLE` findings exist under `select = ["E", "F", "I"]` — verified; should one ever appear after a future rule change, silence it with a targeted `# noqa: BLE001` plus a one-line comment explaining the deliberate degradation catch — never narrow an `except` clause).

- [ ] **Step 5: Run the whole suite after the lint fixes**

Run: `uv run pytest -q`
Expected: `70 passed` (import reordering and line wraps are behavior-neutral)

- [ ] **Step 6: Commit commit 2 (pathspec form)**

```bash
git commit .env.example pyproject.toml uv.lock \
  src/a2apoc/chat/app.py src/a2apoc/client/cli.py src/a2apoc/client/core.py \
  src/a2apoc/client/ui.py src/a2apoc/demo.py src/a2apoc/host/app.py \
  src/a2apoc/host/decision.py src/a2apoc/llm.py src/a2apoc/search/app.py \
  src/a2apoc/search/card.py src/a2apoc/wiring.py \
  tests/chat/test_executor.py tests/client/test_cli.py tests/client/test_core.py \
  tests/host/test_app.py tests/resources/test.http tests/test_demo.py \
  tests/test_llm.py tests/test_wiring.py \
  -m "refactor: single-source port topology and sweep refactor residue"
```

Expected: one commit containing exactly those 22 paths (the `test.http` pathspec records the staged deletion); `git status` shows only pre-existing unrelated changes.

### Task 8: Final verification battery (no commit)

**Files:** none (verification only).

**Interfaces:**
- Consumes: everything produced by Tasks 1-7.

- [ ] **Step 1: Full suite**

Run: `uv run pytest -q`
Expected: `70 passed`

- [ ] **Step 2: Lint gate**

Run: `uv run ruff check .`
Expected: `All checks passed!`

- [ ] **Step 3: Import smoke**

Run: `uv run python -c "import a2apoc.wiring, a2apoc.llm, a2apoc.chat.app, a2apoc.host.app, a2apoc.search.app, a2apoc.client.core, a2apoc.demo"`
Expected: no output, exit code 0.

- [ ] **Step 4: Port-literal grep**

Run: `grep -rn "999[789]" --include="*.py" src/`
Expected: exactly three hits, all in `src/a2apoc/wiring.py`.

- [ ] **Step 5: Launcher boot check with dummy env (commands verified against the current tree)**

```bash
LOG="$TMPDIR/a2a-poc-demo.log"   # or any session temp dir; not the repo
LLM_API_KEY=dummy LLM_BASE_URL=http://localhost:1 LLM_MODEL=dummy \
TAVILY_API_KEY=dummy OPENCODE_API_KEY=dummy \
  uv run a2a-poc-demo > "$LOG" 2>&1 &
DEMO_PID=$!
for port in 9997 9998 9999; do
  ok=0
  for i in $(seq 1 30); do
    if curl -sf "http://127.0.0.1:$port/.well-known/agent-card.json" > /dev/null; then ok=1; break; fi
    sleep 1
  done
  echo "port $port card curl: $ok"
done
kill -INT $DEMO_PID
wait $DEMO_PID
echo "demo exit code: $?"
lsof -nP -iTCP:9997 -iTCP:9998 -iTCP:9999 -sTCP:LISTEN || echo "no listeners left"
```

Expected: `port 9997 card curl: 1`, `port 9998 card curl: 1`, `port 9999 card curl: 1`, `demo exit code: 0`, `no listeners left` (and the log tail shows all three children's `Finished server process` lines). If any curl fails, inspect `$LOG` before killing anything; always `kill -INT $DEMO_PID` and re-run the `lsof` check so no listeners are left behind.

# Multi-Agent Host Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A host A2A agent that decides when web knowledge is needed, delegates to a new Tavily search agent, and relays a chat-agent-synthesized answer — plus a three-process demo launcher.

**Architecture:** Three A2A agents as separate processes: search agent (new, Tavily-backed, port 9997), chat agent (existing, parameterized, port 9999), host (new, orchestrator, port 9998). The host consumes `a2a_poc.client.core.stream_reply` to delegate and reuses the server package's artifact-streaming pattern to relay. The Streamlit UI gains one additive behavior: rendering mid-stream status messages.

**Tech Stack:** Python 3.13, uv, a2a-sdk 1.3.1, `tavily-python>=0.8` (new), uvicorn, FastAPI, pytest + pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-11-23-multi-agent-host-design.md`

## Global Constraints

- Anti-goals from the spec: the chat agent stays generic (no knowledge of the search agent or host); the CLI's observable behavior is unchanged; the ONLY sanctioned UI change is additive mid-stream status rendering — existing pinned tests must keep passing unchanged.
- Env contract: `A2A_POC_PORT` (per-process port override; invalid value → fail fast naming the var), `CHAT_AGENT_URL` (default `http://127.0.0.1:9999`), `SEARCH_AGENT_URL` (default `http://127.0.0.1:9997`), `TAVILY_API_KEY` (fail fast at search-agent startup). Bind host is loopback-only (`127.0.0.1`) for every process. The launcher uses fixed defaults and injects matching URLs into the host child.
- Console commands: existing `a2a-poc-server`, `a2a-poc-client`, `a2a-poc-ui` keep working; new `a2a-poc-search-agent`, `a2a-poc-host`, `a2a-poc-demo`.
- Card identities (exact): search — name "A2A PoC Search Agent", skill id `web_search`, skill name "Web search", description "Searches the web (Tavily) and returns the top results as text."; host — name "A2A PoC Host", skill id `orchestrate`, skill name "Orchestration", description "Decides when web knowledge is needed, delegates to a search agent, and synthesizes the final answer via a chat agent."
- a2a-sdk 1.3.1 protobuf facts carry over: helpers in `a2a.helpers` (`new_text_message`, `new_text_part`, `new_task_from_user_message`, `get_message_text`), `TaskUpdater.add_artifact(..., artifact_id, name, append, last_chunk)`, SCREAMING_SNAKE_CASE enums, `DefaultRequestHandler`/route-factory wiring.
- Tavily (verified): `from tavily import AsyncTavilyClient`; `await client.search(query, max_results=5)`; response dict with `results: [{title, url, content, score, ...}]`; errors in `tavily.errors`.
- `.gitignore` is owner-provided — NEVER modify it. No credentials in the repo; `.env` never committed. Every task ends with a conventional commit.

## Review Focus

1. Search unavailable (dead search agent, Tavily error, or FAILED search task) → the host task still COMPLETES with an answer plus a degradation status note → `tests/host/test_executor.py` (Task 3).
2. Decider exception or unparseable decider output → degrade to the no-search path with a note / fail-safe NO_SEARCH → `tests/host/test_executor.py` + `tests/host/test_decision.py` (Task 3).
3. Missing `TAVILY_API_KEY` → the search agent fails fast at startup naming the var → `tests/search/test_config.py` (Task 2).
4. Chat-agent delegation returns FAILED → the host task FAILED with the wire reason, never an empty success → `tests/host/test_executor.py` (Task 3).
5. Launcher Ctrl-C leaves no orphan children and ports don't collide → scripted boot/curl/interrupt verification in Task 5 (committed test impractical; the check is pinned as a step).

---

### Task 1: Server parameterization + shared wiring

**Files:**
- Create: `src/a2a_poc/server/wiring.py`, `tests/server/test_wiring.py`
- Modify: `src/a2a_poc/server/app.py`

**Interfaces:**
- Produces (for Tasks 2, 3, 5):
  - `a2a_poc.server.wiring.HOST = "127.0.0.1"`
  - `resolve_bind(default_port: int) -> tuple[str, int]` — reads `A2A_POC_PORT` (int); missing → default; invalid → `ValueError` naming the var; host is always `HOST`.
  - `bind_a2a_routes(app: FastAPI, agent_card, request_handler) -> FastAPI` — the DefaultRequestHandler + route attach logic extracted from `create_app`, using the SDK constants for the well-known path and RPC URL.
  - `a2a_poc.server.app.create_app(config: Config | None = None, port: int = 9999) -> FastAPI` — additive `port` param; the card's interface URL derives from `HOST`/`port`. `main()` uses `resolve_bind(9999)`.

- [ ] **Step 1: Write failing tests** in `tests/server/test_wiring.py`:
  - `test_resolve_bind_default` — no env → `("127.0.0.1", 9999)`-style (use a distinct default like 9997 to prove the default flows through).
  - `test_resolve_bind_env_override` — `A2A_POC_PORT=1234` → `("127.0.0.1", 1234)`.
  - `test_resolve_bind_invalid_env_fails_fast` — `A2A_POC_PORT=abc` → `ValueError` whose message contains `A2A_POC_PORT`.
  - In `tests/server/test_server.py` add `test_create_app_port_flows_into_card` — `create_app(dummy_config, port=1234)`; GET the well-known card path; `body["supported_interfaces"][0]["url"]` endswith `":1234"` (adapt the assertion mechanics to the served JSON's actual shape; never weaken existing tests).
- [ ] **Step 2: Run to verify they fail.** `uv run pytest tests/server/test_wiring.py tests/server/test_server.py -v` — import failures.
- [ ] **Step 3: Implement** `wiring.py` per Interfaces; refactor `app.py` to use `bind_a2a_routes` + the `port` param (existing behavior and tests unchanged).
- [ ] **Step 4: Run to verify pass.** Full suite green (21 existing + 4 new).
- [ ] **Step 5: Commit.** `git add src/a2a_poc/server tests/server && git commit -m "refactor: shared A2A app wiring and env-driven port"`

### Task 2: Search agent

**Files:**
- Create: `src/a2a_poc/search/__init__.py` (empty), `src/a2a_poc/search/tavily_client.py`, `src/a2a_poc/search/config.py`, `src/a2a_poc/search/executor.py`, `src/a2a_poc/search/card.py`, `src/a2a_poc/search/app.py`
- Create tests: `tests/search/test_tavily_client.py`, `tests/search/test_config.py`, `tests/search/test_executor.py`, `tests/search/test_app.py`
- Modify: `pyproject.toml` (dependency `tavily-python>=0.8`; script `a2a-poc-search-agent = "a2a_poc.search.app:main"`), `.env.example` (add `TAVILY_API_KEY=your-tavily-key`)

**Interfaces:**
- Consumes: Task 1's `resolve_bind`/`bind_a2a_routes`; server executor patterns (`TaskUpdater`, `_ReplyArtifactStream` style — emit one artifact, not a stream).
- Produces (Task 3's host delegates to this agent over the wire; nothing imports it):
  - `TavilyConfigError(RuntimeError)`
  - `load_tavily_config() -> str` (the API key; `.env`-aware; missing/empty → `TavilyConfigError` naming `TAVILY_API_KEY`)
  - `class TavilySearcher: __init__(self, client)` (duck-typed; production: `AsyncTavilyClient(api_key=...)`), `async def search(self, query: str) -> str` — `await client.search(query, max_results=5)`; formats each result as title + URL + snippet lines; returns `"No results found."` when `results` is empty.
  - `SearchAgentExecutor(AgentExecutor)` with `__init__(self, searcher: TavilySearcher)` — WORKING → single artifact (`name="search_results"`) with the formatted text → COMPLETED; searcher exceptions → FAILED + `logger.exception` (server-executor pattern); `cancel` no-op; touches only `context.message`/`context.current_task`.
  - `build_search_agent_card(base_url: str) -> AgentCard` (exact identity in Global Constraints; streaming capability False).
  - `create_search_app(searcher: TavilySearcher, port: int = 9997) -> FastAPI` and `main() -> None` (fail-fast key, real `AsyncTavilyClient`, `resolve_bind(9997)`, uvicorn).

- [ ] **Step 1: `uv add "tavily-python>=0.8"`** (expect a lock regeneration; commit it with this task).
- [ ] **Step 2: Write failing tests:**
  - `test_tavily_client.py` — fake client (duck-typed `async def search(self, query, **kwargs)` returning a scripted dict): formatted output contains each result's title, url, and content; `max_results == 5` is passed; empty `results` → `"No results found."`.
  - `test_config.py` — mirror the server config tests: set/unset `TAVILY_API_KEY` (env_file=None) → value / `TavilyConfigError` naming the var.
  - `test_executor.py` — fake searcher returning text → COMPLETED + artifact text equals it; fake searcher raising → FAILED + empty artifacts.
  - `test_app.py` — `create_search_app(fake_searcher)`; GET well-known card path → 200, `body["name"] == "A2A PoC Search Agent"`, skill id `web_search` present.
- [ ] **Step 3: Run to verify they fail** (import failures).
- [ ] **Step 4: Implement** the search package per Interfaces.
- [ ] **Step 5: Run to verify pass** — full suite green.
- [ ] **Step 6: Boot check without a real key:** `TAVILY_API_KEY=dummy uv run a2a-poc-search-agent & sleep 3; curl -sf http://127.0.0.1:9997/.well-known/agent-card.json >/dev/null && echo BOOT_OK; kill %1` — expect BOOT_OK (startup makes no Tavily call). Also verify missing key fail-fast: `env -u TAVILY_API_KEY uv run a2a-poc-search-agent` exits non-zero naming the var (short timeout; it must NOT bind the port).
- [ ] **Step 7: Commit.** `git add pyproject.toml uv.lock .env.example src/a2a_poc/search tests/search && git commit -m "feat: Tavily-backed search agent"`

### Task 3: Host — decision and orchestration

**Files:**
- Create: `src/a2a_poc/host/__init__.py` (empty), `src/a2a_poc/host/decision.py`, `src/a2a_poc/host/executor.py`, `src/a2a_poc/host/card.py`, `src/a2a_poc/host/app.py`
- Create tests: `tests/host/test_decision.py`, `tests/host/test_executor.py`, `tests/host/test_app.py`
- Modify: `src/a2a_poc/server/agent.py`, `pyproject.toml` (script `a2a-poc-host = "a2a_poc.host.app:main"`)

**Interfaces:**
- Consumes: Task 1's `resolve_bind`/`bind_a2a_routes`; `a2a_poc.client.core.stream_reply(base_url, user_text, httpx_client=None, client_factory=None) -> AsyncIterator[Delta | Status]` (Delta.text, Status.state, Status.message); `a2a_poc.server.config.load_config`/`Config`; `ChatAgent`.
- Produces:
  - `ChatAgent.__init__(self, client, model: str, system_prompt: str = SYSTEM_PROMPT)` (additive; existing tests untouched).
  - `@dataclass(frozen=True) class Decision: needs_search: bool; query: str`
  - `DECIDER_SYSTEM_PROMPT: str` — instructs a single-line reply `SEARCH: <refined query>` or `NO_SEARCH`.
  - `async def decide_with(agent: ChatAgent, user_text: str) -> Decision` — consumes the agent's reply; lenient parse (case-insensitive `search:` prefix → needs_search True + rest stripped; anything else → `Decision(False, "")`).
  - `HostAgentExecutor(AgentExecutor)`, `__init__(self, decider, chat_url: str, search_url: str, stream=core.stream_reply)` — the injectable `stream` callable (signature identical to `core.stream_reply`) is the test seam.
  - `build_host_agent_card(base_url: str) -> AgentCard` (identity in Global Constraints; streaming capability True).
  - `create_host_app(decider, chat_url: str, search_url: str, port: int = 9998) -> FastAPI`; `main() -> None` — `load_config()`, build `ChatAgent` via `build_chat_agent` + `DECIDER_SYSTEM_PROMPT`, `decider = functools.partial(decide_with, agent)`; URLs from `CHAT_AGENT_URL`/`SEARCH_AGENT_URL` env with spec defaults; `resolve_bind(9998)`; uvicorn.

- [ ] **Step 1: Write failing tests:**
  - `test_decision.py` — `decide_with` over a fake ChatAgent-style object (scripted deltas): `"SEARCH: latest A2A spec"` → `Decision(True, "latest A2A spec")`; `"NO_SEARCH"` and `"no_search"` → `Decision(False, "")`; garbage (`"I think maybe search?"`) → `Decision(False, "")`.
  - `test_executor.py` — injectable fake `decider` and fake `stream` returning scripted `Delta`/`Status` sequences per URL; scenarios:
    1. no-search path: chat stream receives the raw user text; host emits WORKING, relays chat deltas, COMPLETED; concatenated artifact text equals the chat reply.
    2. search path: decider → `Decision(True, "q")`; the search-URL stream returns deltas; the chat-URL stream's received prompt contains both the user question and the search results text; status messages include the searching narration.
    3. search degradation (stream raises for the search URL): chat still called with the raw user text; task COMPLETED; a degradation status message is emitted.
    4. search FAILED (stream returns a FAILED final Status for the search URL): same as 3.
    5. decider raises: no-search path with a couldn't-decide status note; task COMPLETED.
    6. chat FAILED: host task FAILED with the chat status's message as the reason; no empty COMPLETED.
  - `test_app.py` — `create_host_app(fake_decider, ...)`; GET well-known card path → 200, `body["name"] == "A2A PoC Host"`, skill id `orchestrate`.
- [ ] **Step 2: Run to verify they fail.**
- [ ] **Step 3: Implement** — host package per Interfaces. Executor flow pinned: task + WORKING → decider (exception → status note + `Decision(False, "")`) → if search: narration status, collect the search stream's deltas (exceptions or FAILED final status → degradation note, results dropped) → compose the chat prompt (raw question, or a synthesis prompt carrying question + results) → relay the chat stream's deltas as the host's streamed artifacts (same artifact-stream pattern as the server executor) → if the chat final status is FAILED → host FAILED with that message; else COMPLETED. Exceptions in the synthesis relay → FAILED + `logger.exception`.
- [ ] **Step 4: Run to verify pass** — full suite green.
- [ ] **Step 5: Commit.** `git add src/a2a_poc/server/agent.py src/a2a_poc/host pyproject.toml tests/host && git commit -m "feat: multi-agent host with search-then-synthesize orchestration"`

### Task 4: UI status rendering (the one sanctioned UI addition)

**Files:**
- Modify: `src/a2a_poc/client/ui.py`
- Modify tests: `tests/client/test_ui.py` (add one test)

**Interfaces:**
- Consumes: `a2a_poc.client.core.Status` (state, message).
- Produces: `status_info_text(status: Status) -> str | None` in `ui.py` — returns the message for mid-stream statuses that should render (message present AND state != `TaskState.TASK_STATE_FAILED`), else None. The `_reply_text_stream` adapter calls `st.info(status_info_text(s))` when non-None, before yielding the next delta.

- [ ] **Step 1: Write the failing test** in `tests/client/test_ui.py`: `test_status_info_text` — `Status(TASK_STATE_WORKING-int, "Searching the web…")` → the message; `Status(..., None)` → None; `Status(TASK_STATE_FAILED-int, "LLM call failed: boom")` → None (the existing post-stream `st.error` path owns FAILED).
- [ ] **Step 2: Run to verify it fails** (import error).
- [ ] **Step 3: Implement** `status_info_text` + the adapter call. Existing UI tests must keep passing unchanged.
- [ ] **Step 4: Run to verify pass** — full suite green.
- [ ] **Step 5: Commit.** `git add src/a2a_poc/client/ui.py tests/client/test_ui.py && git commit -m "feat: render host phase narration in the UI"`

### Task 5: Demo launcher

**Files:**
- Create: `src/a2a_poc/demo.py`
- Modify: `pyproject.toml` (script `a2a-poc-demo = "a2a_poc.demo:main"`), `src/a2a_poc/server/app.py`, `src/a2a_poc/search/app.py`, `src/a2a_poc/host/app.py` (each gains `if __name__ == "__main__": main()`)

**Interfaces:**
- Consumes: the three agent mains, spawnable via `sys.executable -m a2a_poc.server.app` / `-m a2a_poc.search.app` / `-m a2a_poc.host.app` (hence the `__main__` guards).
- Produces: `main() -> None` — spawns the three subprocesses (search, chat, host) with prefixed, line-buffered output; injects `CHAT_AGENT_URL`/`SEARCH_AGENT_URL` (spec defaults) into the host child's env; on SIGINT/SIGTERM terminates all children and waits; non-zero child exit terminates the others and exits non-zero.

- [ ] **Step 1: Implement `demo.py`** (asyncio subprocess supervision; ~60 lines; no committed test — the pinned verification below is the check; disclose the mechanics in the report).
- [ ] **Step 2: Verify:** with dummy env (`LLM_API_KEY=dummy LLM_BASE_URL=http://127.0.0.1:9999/v1 LLM_MODEL=dummy TAVILY_API_KEY=dummy uv run a2a-poc-demo &`), after ~5s: curl the host card (`http://127.0.0.1:9998/.well-known/agent-card.json`) → 200; `lsof -nP -iTCP:9997 -iTCP:9998 -iTCP:9999 -sTCP:LISTEN` shows three listeners on 127.0.0.1; send SIGINT to the launcher; all three listeners gone (`lsof` empty); no orphan processes. Capture the outputs.
- [ ] **Step 3: Full suite green.**
- [ ] **Step 4: Commit.** `git add src/a2a_poc/demo.py src/a2a_poc/server/app.py src/a2a_poc/search/app.py src/a2a_poc/host/app.py pyproject.toml && git commit -m "feat: a2a-poc-demo three-process launcher"`

### Task 6: README + final verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README** — new "Multi-agent demo" section: the flow diagram from the spec; `.env` now also needs `TAVILY_API_KEY`; run with `uv run a2a-poc-demo` (or the three commands individually); point the UI's sidebar at `http://127.0.0.1:9998`; what you'll see (phase info lines, then the streamed answer; degradation notes when search is unavailable); the kill-the-search-agent degradation demo; the custom-port caveat (standalone `A2A_POC_PORT` requires matching `*_AGENT_URL`). CLI section unchanged.
- [ ] **Step 2: Run the full suite** — all passing, pristine.
- [ ] **Step 3: Commit.** `git add README.md && git commit -m "docs: multi-agent demo README"`

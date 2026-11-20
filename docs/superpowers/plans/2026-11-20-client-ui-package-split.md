# Client UI (Streamlit) + Package Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split `a2a_poc` into `server`/`client` sub-packages, extract a reusable client core, and add a Streamlit chat UI as a second client frontend — with zero behavior change on the server and the CLI.

**Architecture:** The `server` package keeps today's modules (pure moves). The `client` package gains `core.py` — an async event-stream API with no printing and no `SystemExit` — consumed by `cli.py` (today's behavior, byte-for-byte) and a new `ui.py` (Streamlit chat over the wire). Tests mirror the split.

**Tech Stack:** Python 3.13, uv (`uv_build`), a2a-sdk 1.3.1, `streamlit>=1.58` (new), pytest + pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-11-20-client-ui-package-split-design.md`

## Global Constraints

- Pure moves and refactors: zero server/protocol behavior change; CLI observable behavior (stdout/stderr shape, exit codes, error wording) unchanged and pinned by existing tests.
- Existing test assertions must not be weakened — only import paths change (plus the `tests/test_client.py` → `tests/client/test_cli.py` move).
- Absolute imports matching existing style (e.g. `from a2a_poc.server.agent import ChatAgent`); no re-exports in package `__init__.py`.
- `.gitignore` is owner-provided — NEVER create or modify it. No credentials in the repo.
- a2a-sdk 1.3.1 protobuf facts carry over: helpers in `a2a.helpers`; `StreamResponse` payload oneof (`task`/`message`/`status_update`/`artifact_update`); SCREAMING_SNAKE_CASE enums.
- Use `git mv` for file moves (history preservation).
- Every task ends with a conventional commit.

## Review Focus

1. CLI behavior must not regress during the refactor → the four existing tests in `tests/client/test_cli.py` (dead-server, malformed-URL, failed-task exit, `--help`) pass unchanged in Tasks 1 and 2.
2. The core must be free of console side effects (a Streamlit app would die on `SystemExit`; printing would pollute) → `tests/client/test_core.py` asserts `capsys` output is empty and no `SystemExit` on a failed task (Task 2).
3. Transport/protocol failures must surface from the core as exceptions (frontends translate) → `test_core` asserts the `A2AClientError` family and `httpx.InvalidURL` propagate (Task 2).
4. The UI must render without a server and show pre-existing chat history → `tests/client/test_ui.py` AppTest render + pre-seeded `session_state["messages"]` history test (Task 3).
5. Console scripts must resolve after the move → Task 1 smoke (`uv run a2a-poc-client --help` exit 0; `from a2a_poc.server.app import create_app` importable) and Task 3 declares `a2a-poc-ui` (launch verified manually per README).

---

### Task 1: Package split

**Files:**
- Create: `src/a2a_poc/server/__init__.py` (empty), `src/a2a_poc/client/__init__.py` (empty)
- Move (git mv) + import updates: `src/a2a_poc/config.py` → `src/a2a_poc/server/config.py`; `agent.py` → `server/agent.py`; `card.py` → `server/card.py`; `executor.py` → `server/executor.py`; `server.py` → `server/app.py`; `client.py` → `client/cli.py`
- Move tests: `tests/test_{config,agent,card,executor,server}.py` → `tests/server/` (imports updated); `tests/test_client.py` → `tests/client/test_cli.py` (import updated)
- Modify: `pyproject.toml` `[project.scripts]`

**Interfaces:**
- Produces (for later tasks): `a2a_poc.server.config`, `a2a_poc.server.agent`, `a2a_poc.server.card`, `a2a_poc.server.executor`, `a2a_poc.server.app` (`create_app`, `main`, `HOST`, `PORT`), `a2a_poc.client.cli` (`run`, `main`, `DEFAULT_BASE_URL`).

- [ ] **Step 1: Move and rewire.** `git mv` the six modules and the six test files per Files; create the two empty `__init__.py` files; set `pyproject.toml` scripts to:

```toml
[project.scripts]
a2a-poc-server = "a2a_poc.server.app:main"
a2a-poc-client = "a2a_poc.client.cli:main"
```

- [ ] **Step 2: Update internal imports.** `server/executor.py`: `from a2a_poc.agent import ChatAgent` → `from a2a_poc.server.agent import ChatAgent`. `server/app.py`: config/agent/card/executor imports → `a2a_poc.server.*`. `client/cli.py` imports only a2a-sdk/httpx — no changes.

- [ ] **Step 3: Update test imports.** Server tests → `a2a_poc.server.{config,agent,card,executor,app}`; `tests/client/test_cli.py` → `from a2a_poc.client.cli import main, run`. Assertions otherwise byte-identical.

- [ ] **Step 4: Run the full suite.** `uv run pytest -v` — expect 16 passed (imports only changed).

- [ ] **Step 5: Smoke.** `uv run a2a-poc-client --help` (exit 0) and `uv run python -c "from a2a_poc.server.app import create_app; from a2a_poc.client.cli import main"`.

- [ ] **Step 6: Commit.** `git add -A && git commit -m "refactor: split a2a_poc into server and client packages"`

### Task 2: Client core extraction

**Files:**
- Create: `src/a2a_poc/client/core.py`, `tests/client/test_core.py`
- Modify: `src/a2a_poc/client/cli.py` (delegate to core)

**Interfaces:**
- Consumes: `cli.py`'s current event loop and error handling (post-Task-1 location).
- Produces (Task 3's `ui.py` consumes these exactly):
  - `DEFAULT_BASE_URL: str` (moved here from cli; cli re-imports it)
  - `ClientFactory = Callable[[AgentCard], Awaitable[Client]]`
  - `@dataclass(frozen=True) class Delta: text: str`
  - `@dataclass(frozen=True) class Status: state: int; message: str | None` (joined text of the status message's parts; None when absent)
  - `async def stream_reply(base_url: str, user_text: str, httpx_client: httpx.AsyncClient | None = None, client_factory: ClientFactory | None = None) -> AsyncIterator[Delta | Status]` — resolves the card, streams events, closes only self-owned clients; **no printing, no SystemExit; transport/protocol exceptions propagate**.
- cli.py: `run(...)` keeps its exact current signature and observable behavior, implemented by consuming `core.stream_reply`.

- [ ] **Step 1: Write the failing tests** in `tests/client/test_core.py`, reusing the MockTransport-served-card + `client_factory` scripting pattern already present in `tests/client/test_cli.py`:
  - `test_core_yields_deltas_and_status_in_order` — scripted stream (status WORKING → artifact `"Hel"` → artifact `"lo"` → status COMPLETED) → events are `[Status(WORKING, None), Delta("Hel"), Delta("lo"), Status(COMPLETED, None)]` in order.
  - `test_core_failed_task_ends_without_systemexit_and_prints_nothing` — scripted FAILED status with message `"LLM call failed: boom"` → last event is `Status(state == TaskState.TASK_STATE_FAILED, message == "LLM call failed: boom")`; the generator completes without `SystemExit`; `capsys.readouterr().out == ""`.
  - `test_core_propagates_connection_errors` — MockTransport raising `httpx.ConnectError` → the SDK's `A2AClientError` family propagates out of `stream_reply`.

- [ ] **Step 2: Run to verify it fails.** `uv run pytest tests/client/test_core.py -v` — expect import failure (no `a2a_poc.client.core`).

- [ ] **Step 3: Implement `src/a2a_poc/client/core.py`** per the Interfaces block: move card resolution, event dispatch (yielding typed events instead of printing), and client lifecycle out of `cli.py`. `Status.message` joins the part texts of `status.message` when the status carries one.

- [ ] **Step 4: Run to verify it passes.** `uv run pytest tests/client/test_core.py -v` — expect 3 passed.

- [ ] **Step 5: Refactor `cli.py` to consume `core.stream_reply`** (printing, exit codes, and error translation stay in cli); run the FULL suite — expect all passing (16 old + 3 new), with `test_cli.py` untouched.

- [ ] **Step 6: Commit.** `git add src/a2a_poc/client tests/client && git commit -m "refactor: extract reusable client core; cli becomes a frontend"`

### Task 3: Streamlit chat UI

**Files:**
- Create: `src/a2a_poc/client/ui.py`, `tests/client/test_ui.py`
- Modify: `pyproject.toml` (dependency `streamlit>=1.58`; script `a2a-poc-ui = "a2a_poc.client.ui:main"`)

**Interfaces:**
- Consumes: `a2a_poc.client.core` (`DEFAULT_BASE_URL`, `Delta`, `Status`, `stream_reply`).
- Produces: Streamlit script (module-level rendering) + `def main() -> None` console entry bootstrapping streamlit on this file.

- [ ] **Step 1: Add the dependency.** `uv add "streamlit>=1.58"`.

- [ ] **Step 2: Write the failing tests** in `tests/client/test_ui.py` (AppTest, offline — no chat submission, so no network):
  - `test_ui_renders_chat_page` — `AppTest.from_file("src/a2a_poc/client/ui.py", default_timeout=10)` then `at.run()` → `not at.exception`; a chat input exists.
  - `test_ui_renders_existing_history` — pre-seed `at.session_state["messages"] = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]`, run → `not at.exception` and both messages render as chat messages.
  These pin the session-state contract: history is a list of `{"role", "content"}` dicts under key `"messages"`.

- [ ] **Step 3: Run to verify it fails.** `uv run pytest tests/client/test_ui.py -v` — expect failure (ui.py missing).

- [ ] **Step 4: Implement `src/a2a_poc/client/ui.py`.** Title; sidebar text input for the base URL (default `DEFAULT_BASE_URL`); `st.session_state["messages"]` history rendered with `st.chat_message`; `st.chat_input` prompt. On prompt: append the user message, render it, then inside `st.chat_message("assistant")` stream the reply with `st.write_stream` over an adapter that yields `Delta.text` values while capturing the last `Status` into a holder; after the stream, if the final state is `TaskState.TASK_STATE_FAILED` → `st.error` with the status message. Wrap the exchange in try/except for `(httpx.HTTPError, httpx.InvalidURL, A2AClientError)` → `st.error` with a friendly cannot-reach message (the app must not die). Add `main()` using the streamlit bootstrap idiom: `from streamlit.web import cli as stcli` and `sys.argv = ["streamlit", "run", str(Path(__file__).resolve()), *sys.argv[1:]]; sys.exit(stcli.main())`.

- [ ] **Step 5: Wire the entry point and verify.** Add `a2a-poc-ui` to `pyproject.toml` scripts; `uv sync`; run `uv run pytest tests/client/test_ui.py -v` then the full suite — all passing.

- [ ] **Step 6: Commit.** `git add pyproject.toml uv.lock src/a2a_poc/client/ui.py tests/client/test_ui.py && git commit -m "feat: Streamlit chat UI for the A2A client"`

### Task 4: README + final verification

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Update README.** Add the package-structure tree (`server`/`client`); a "Run the UI" section — start the agent first (`uv run a2a-poc-server`), then `uv run a2a-poc-ui` and open the URL Streamlit prints (default `http://localhost:8501`); document the sidebar base-URL field and that failures render as red error boxes with the wire reason. Keep the CLI section unchanged.

- [ ] **Step 2: Run the full suite.** `uv run pytest -v` — all passing, pristine output.

- [ ] **Step 3: Commit.** `git add README.md && git commit -m "docs: README for split packages + Streamlit UI"`

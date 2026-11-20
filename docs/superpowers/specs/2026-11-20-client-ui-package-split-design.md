# A2A PoC — Client UI (Streamlit) + package split — Design

- **Date:** 2026-11-20
- **Status:** Approved (owner approved all calls in conversation, incl. test-folder reorganization)
- **Builds on:** `docs/superpowers/specs/2026-11-18-a2a-poc-design.md` (original PoC design)

## Intent & why

Before deeper A2A work (multi-agent), give the client side a visible UI (Streamlit chat) and reorganize the codebase into `server`/`client` sub-packages so each side can grow independently. The server and its wire behavior stay exactly as-is.

## Goals

1. Package split: `src/a2a_poc/server/` (config, agent, card, executor, app) and `src/a2a_poc/client/` (core, cli, ui) — pure moves, no behavior change.
2. Client core/frontend separation: `client/core.py` exposes a reusable async API (yields deltas + status events, ends with the final outcome) with **no printing and no SystemExit**; `client/cli.py` preserves current CLI behavior byte-for-byte (output shape, friendly errors, exit codes).
3. Streamlit UI (`client/ui.py`): chat with history in `st.session_state`; replies streamed token-by-token via `st.write_stream`; `st.error` on FAILED with the wire reason; sidebar field for the agent's base URL (default `http://127.0.0.1:9999`). The server runs separately — the UI is an A2A client over the wire, not an embed.
4. `streamlit` as a regular dependency; new `a2a-poc-ui` console command.
5. Tests reorganized to mirror the packages: `tests/server/` (config/agent/card/executor/app tests) and `tests/client/` (`test_cli.py` = today's `test_client.py` with unchanged assertions and updated imports; new `test_core.py` for the core API). All 16 existing tests keep passing.
6. README updated: UI section (run server, then `a2a-poc-ui`), package-structure overview.

## Non-goals

- Any server/protocol behavior change; multi-agent orchestration; auth; UI polish beyond token rendering; new client protocol features.

## Constraints

- Existing test assertions must not be weakened — only import paths (and the test_client.py → test_cli.py rename/move) change.
- The CLI's observable behavior (stdout/stderr shape, exit codes, error wording) is a compatibility surface pinned by existing tests.
- No credentials in the repo; `.gitignore` is owner-provided — never modify it.
- a2a-sdk 1.3.1 protobuf facts carry over (helpers in `a2a.helpers`, `StreamResponse` payload oneof, SCREAMING_SNAKE_CASE enums).

## Approaches considered

1. **Thin: call `run()` from Streamlit** — rejected: `run()` prints to stdout and raises `SystemExit`; both break a Streamlit app.
2. **Core + two frontends** (CLI + UI sharing `client/core.py`) — **picked**: proper separation, both frontends testable, and the `client_factory` test seam already exists.

## How — decided

- Naming: `server.py` → `server/app.py`; `client.py` → `client/cli.py`.
- Chat-with-history UI (not one-shot): messages in `st.session_state`, rendered with `st.chat_message` / `st.chat_input`; reply streamed with `st.write_stream` over the core's deltas; FAILED → `st.error` with the wire reason.
- `streamlit>=1.58` (matches the owner's `langchain-agentic-poc` floor).
- Core error semantics: transport/protocol exceptions propagate from the core; each frontend translates them (CLI: friendly stderr + exit 1, unchanged; UI: `st.error`).
- New `a2a-poc-ui` console script wrapping `streamlit run`.

## Left to the builder

- Exact core API signature and event representation (e.g. an async generator yielding typed delta/status events).
- `ui.py` details (layout, session-state keying, base-URL persistence, final-outcome capture after `st.write_stream`).
- Streamlit launch mechanics for `a2a-poc-ui` (programmatic bootstrap vs subprocess — implementer's choice, disclosed).
- Whether/how to smoke-test the UI (`streamlit.testing.v1.AppTest` is available; a minimal render test is desirable if cheap).
- Test split details within `tests/client/`.

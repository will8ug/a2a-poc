# Rename `server` package to `chat` — Design (short)

- **Date:** 2026-11-23
- **Status:** Approved in conversation (package name `chat`; command renamed to `a2a-poc-chat`)
- **Context:** after the multi-agent phase, `a2a_poc/server/`'s name is stale — all three agent packages are servers, and the other two are purpose-named (`search`, `host`).

## What changes (one mechanical commit, behavior unchanged)

1. `git mv src/a2a_poc/server src/a2a_poc/chat`.
2. Promote the shared, agent-agnostic `wiring.py` (`HOST`, `resolve_bind`, `bind_a2a_routes` — imported by all three agent apps) to top-level `src/a2a_poc/wiring.py`, mirroring top-level `demo.py`. `chat/` then holds only the chat agent (config, agent, card, executor, app).
3. Console command `a2a-poc-server = "a2a_poc.server.app:main"` → `a2a-poc-chat = "a2a_poc.chat.app:main"` (pyproject).
4. Launcher spawn target: `-m a2a_poc.server.app` → `-m a2a_poc.chat.app` (`demo.py`).
5. Update the ~20 import references: `chat/` internals (`a2a_poc.server.{config,agent,card,executor}` → `a2a_poc.chat.*`; wiring → `a2a_poc.wiring`), `search/app.py` (wiring → `a2a_poc.wiring`), `host/app.py` (wiring/config/agent → `a2a_poc.wiring` / `a2a_poc.chat.*`), `host/executor.py` (`_ReplyArtifactStream` import re-pointed to `a2a_poc.chat.executor`).
6. Tests: `git mv tests/server tests/chat` with imports updated; `tests/chat/test_server.py` → `tests/chat/test_app.py` (parallel with search/host); `tests/server/test_wiring.py` → `tests/test_wiring.py` (top-level, mirroring the module). All assertions unchanged.
7. README: `a2a-poc-server` → `a2a-poc-chat` in both places (the run command and the multi-agent three-commands block); the "Run the server" section becomes "Run the chat agent" with its "The server binds…" sentence reworded to "The chat agent binds…". Nothing else.

## Deliberately NOT done

- `_ReplyArtifactStream` stays private in `chat/executor.py` with the host's import re-pointed (promotion to a shared module remains deferred, as ledgered in the multi-agent review).
- No other README/wording changes beyond item 7.

## Verification

- Full suite (55 tests, assertions untouched).
- `uv run a2a-poc-chat --help` exit 0; `uv run python -c "import a2a_poc.chat.app, a2a_poc.wiring"`.
- Launcher dummy-env boot: three loopback listeners, three card curls 200, SIGINT → exit 0, lsof/pgrep empty (the `-m` spawn path is the behavioral risk).

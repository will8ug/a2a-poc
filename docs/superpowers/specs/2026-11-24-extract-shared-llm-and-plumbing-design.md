# Extract shared LLM client and A2A plumbing — Design (short)

- **Date:** 2026-11-24
- **Status:** Approved in conversation; execution pending owner's go-ahead
- **Problem:** agents import from other agents for shared infrastructure — `host` uses `chat/config.py`'s `Config`/`load_config` (really LLM-endpoint config, needed for the decider) and `chat/agent.py`'s `ChatAgent`/`build_chat_agent` (really a generic streaming OpenAI-compatible client), plus a private import of `_ReplyArtifactStream` from `chat/executor.py`.

## What changes (one mechanical commit, behavior unchanged, names unchanged)

1. Create `src/a2a_poc/llm.py` — move `chat/config.py` (`Config`, `ConfigError`, `load_config`) and `chat/agent.py` (`SYSTEM_PROMPT`, `ChatAgent`, `build_chat_agent`) into it. This is the shared LLM client + endpoint config; `git mv` where practical, else move-and-merge into one module.
2. Promote `_ReplyArtifactStream` from `chat/executor.py` into `src/a2a_poc/wiring.py` as public `ReplyArtifactStream` (underscore dropped); `chat/executor.py` and `host/executor.py` import it from `a2a_poc.wiring`.
3. Update importers: `chat/app.py` (config/agent → `a2a_poc.llm`), `host/app.py` (config/agent → `a2a_poc.llm`; wiring unchanged), `host/executor.py` (`_ReplyArtifactStream` → `a2a_poc.wiring.ReplyArtifactStream`), `chat/executor.py` (same).
4. Tests mirror the moves: `tests/chat/test_config.py` + `tests/chat/test_agent.py` → `tests/test_llm.py` (top-level, mirroring `tests/test_wiring.py`); `tests/chat/test_executor.py` and `tests/host/test_executor.py` import updates only. All assertions byte-identical.
5. Resulting layout:

```
src/a2a_poc/
├── llm.py        # Config, ConfigError, load_config, ChatAgent, build_chat_agent, SYSTEM_PROMPT
├── wiring.py     # HOST, resolve_bind, bind_a2a_routes, ReplyArtifactStream
├── demo.py
├── chat/         # card.py, executor.py, app.py — the chat agent's identity + serving only
├── search/       # unchanged
├── host/         # imports only a2a_poc.llm, a2a_poc.wiring, a2a_poc.client.core
└── client/       # unchanged
```

**Invariant:** no agent imports another agent — agents share only top-level, purpose-named infrastructure.

## Rejected alternative (recorded to prevent relitigating)

`a2a_poc/server/` parent package containing chat/search/host plus `server/common/`:
- "server" names the transport role, not the purpose — retired one level up in the 2026-11-23 rename; reintroducing it recreates the confusion (`a2a_poc.server.chat.app`).
- `common/` is a junk-drawer name; purpose-named modules (`llm.py`, `wiring.py`) stay self-documenting.
- The host is both server (to the UI) and client (of chat/search); a server/client taxonomy misleads.
- Churn across everything just moved, no behavioral gain.

## Deliberately deferred (trigger: a fourth agent appears)

- A shared card-building helper (the three `card.py` files are near-duplicates with pinned identities).
- Folding the triplicated `DefaultRequestHandler` + `InMemoryTaskStore` + `FastAPI` construction (~10 lines per app) into `wiring.py`.

## Verification

- Full suite (55 tests, assertions untouched).
- Import smoke: `uv run python -c "import a2a_poc.llm, a2a_poc.wiring, a2a_poc.chat.app, a2a_poc.host.app, a2a_poc.search.app"`.
- Launcher dummy-env boot: three loopback listeners, three card curls 200, SIGINT → exit 0, lsof/pgrep empty.
- Leftover grep: no `a2a_poc.chat.config` / `a2a_poc.chat.agent` / `_ReplyArtifactStream` references outside the moved modules.

---

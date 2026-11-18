# A2A PoC — Design

- **Date:** 2026-11-18
- **Status:** Approved (with amendments: `.gitignore` provided by owner; LLM endpoint inputs come from `.env`; fresh implementation, decoupled from `private-assistant`)
- **Scope choice:** "One agent + client" — over two-agents-plus-host (deferred to a later phase by owner) and hello-world-only (proves too little).

## Intent & why

A minimal, runnable proof-of-concept of the A2A protocol in Python: one LLM-backed agent served over A2A plus a streaming client. It validates the `a2a-sdk` stack before A2A is folded into the broader Agentic AI demo (A2A was explicitly deferred in `private-assistant`'s plans). Success = the client streams a real LLM reply from the A2A agent end-to-end.

## Goals

1. Greenfield uv project: Python 3.13, `src/` layout, git repo (`.gitignore` provided by owner — do not recreate).
2. One chat agent over A2A: user text in, streamed LLM reply out (task status updates + artifact chunks).
3. LLM via Bailian qwen, called with the `openai` package against an OpenAI-compatible endpoint. All endpoint inputs from `.env`: `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` (values supplied by owner; `.env.example` with placeholders; `.env` never committed).
4. Server: `a2a-sdk[fastapi] >= 1.3` (spec 1.0) on FastAPI + uvicorn (port 9999), JSON-RPC binding, SSE streaming, `InMemoryTaskStore`, AgentCard at `/.well-known/agent-card.json`.
5. Client console command: resolve agent card, send a message, print the live event stream.
6. Verification: end-to-end client run, `curl` of the agent card, minimal pytest smoke tests (card route; executor happy-path with stubbed LLM).

## Non-goals (v1)

- Agent-to-agent orchestration / multi-agent host (deliberately the next phase)
- Auth/OAuth, signed agent cards, multi-tenancy
- DB-backed task stores, push notifications
- gRPC or REST bindings (JSON-RPC + SSE only)
- Prompt engineering, tools, or memory in the agent (plain chat)
- pydantic-settings / typed config layer

## Constraints

- a2a-sdk 1.x (spec 1.0) API only. Stale 0.3-era examples are everywhere online: spec 1.0 uses the unified `Part` model, `SCREAMING_SNAKE_CASE` enums, `SendMessage` operation names, `/.well-known/agent-card.json` path, and `supported_interfaces` in AgentCard. Source of truth: a2a-protocol.org Python tutorial + a2aproject/a2a-samples — not blog posts.
- No credentials in the repo; only the three LLM env vars above.
- Python >= 3.10 required by the SDK; we use 3.13.

## Approaches considered

| Approach | Verdict |
|---|---|
| Two agents + host (agent-to-agent) | Best demo of A2A's purpose; owner deferred to a later phase |
| One agent + client | **Picked** — proves the reusable LLM-behind-A2A path end-to-end |
| Hello-world echo only | Fastest; proves too little (no LLM path) |

## How — decided (calls made on proper-practice grounds)

- uv + `pyproject.toml` + `src/a2a_poc/` layout; console scripts `a2a-poc-server`, `a2a-poc-client`.
- FastAPI (not bare Starlette): first-class SDK support, headroom for custom endpoints later; wire via the current tutorial's route-factory style.
- `python-dotenv` + `os.environ` with fail-fast startup validation (clear error listing missing vars).
- LLM streaming: `openai` client with `stream=True`; deltas forwarded as artifact updates; final artifact on completion.
- Minimal pytest smoke tests; the end-to-end client run remains the primary demo verification.
- Fresh implementation; no code copied from `private-assistant`.

## Left to the builder

- Exact a2a-sdk 1.3 API wiring (imports, route factories, types) — verify against the current official tutorial/samples, not memory.
- AgentCard metadata wording (name/description/skill).
- README (setup, `.env`, run commands, expected observations).
- Module split within `src/a2a_poc/` (suggested: `config.py`, `agent.py` (LLM), `executor.py`, `card.py`, `server.py`, `client.py`).

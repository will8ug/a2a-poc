# A2A PoC — Multi-Agent Host (search + synthesis) — Design

- **Date:** 2026-11-23
- **Status:** Approved by owner 2026-11-23 (builder-check questions resolved)
- **Builds on:** `docs/superpowers/specs/2026-11-18-a2a-poc-design.md` (original PoC; this was its deferred multi-agent phase) and `docs/superpowers/specs/2026-11-20-client-ui-package-split-design.md` (server/client split).

## Intent & why

Demonstrate what A2A is actually for — agent-to-agent delegation over the wire — kept minimal. One **host agent** orchestrates two remote agents in a research-then-synthesize pipeline: a new **web-search agent** (Tavily-backed) and the existing **chat agent**. The user's UI talks only to the host; the host↔agent hops are real A2A traffic.

## The demo flow

```
user ──"What's new with X?"──▶  HOST (A2A agent, port 9998)
                                1. decide: internet knowledge needed? (one LLM call → "SEARCH: <query>" | "NO_SEARCH")
                                2. ── query ──▶  SEARCH AGENT (port 9997) → Tavily → results as text
                                3. ── question + results ──▶  CHAT AGENT (port 9999)
                                4. ◀── streamed, synthesized answer (relayed live to the user)
```

No-search path: step 1 answers NO_SEARCH and the host delegates straight to the chat agent with the raw question. The chat agent always produces the final answer (owner: "keep it a simple chat agent"); the search agent is purely a knowledge feeder.

## Goals

1. **Search agent** — new A2A agent (default port 9997), skill `web_search`: takes a query message, runs Tavily, returns the top-5 results formatted as `title + URL + snippet` text as a single artifact. `TAVILY_API_KEY` from `.env`, fail-fast at startup.
2. **Chat agent** — the existing server, port-driven and card-parameterizable, otherwise unchanged; still the final answerer.
3. **Host agent** — new A2A agent (default port 9998): LLM decision call, delegation to both remote agents via `a2a_poc.client.core.stream_reply`, synthesis-prompt composition, relays the chat agent's streamed reply as its own artifacts; status messages narrate phases ("Searching the web…", "Synthesizing…" / degradation notes). The Streamlit UI renders mid-stream status messages as info lines, so phases and degradation notes are visible in the browser.
4. **Graceful degradation** — search-agent or Tavily failure → status note + answer without search (task does not fail). Synthesis failure → task FAILED (existing pattern, with server-side traceback logging).
5. **Launcher** — `a2a-poc-demo`: one command that starts and supervises all three agent processes (separate processes; Ctrl-C stops all; each process fail-fasts its own config with a clear message).
6. **UI/CLI — one sanctioned UI addition** — the CLI is unchanged; the Streamlit UI gains exactly one additive behavior: rendering mid-stream status messages (phase narration + degradation notes) as info lines in the chat. The sidebar / `--base-url` already point anywhere; README documents pointing at the host.
7. **Offline tests** for everything new, using the established duck-typed seams (injectable decider, injectable Tavily client, `core.stream_reply`'s `client_factory`/`httpx_client`).
8. `.env.example` gains `TAVILY_API_KEY`; README gains the multi-agent section.

## Non-goals

- Parallel or multi-query search; tool-calling inside the chat agent; MCP; auth/OAuth; multi-tenancy; showing raw search results to the end user; LLM routing beyond the single search/no-search decision; process supervision beyond Ctrl-C (no restart policies); production hardening.

## Anti-goals

- The chat agent must NOT learn about the search agent or receive a special prompt — it stays generic (owner-specified).
- Nothing may weaken existing pinned tests or change the CLI's observable behavior; the only sanctioned UI change is the additive status-message rendering described in Goals (existing pinned UI tests must keep passing unchanged).

## Constraints

- a2a-sdk 1.3.1 protobuf facts carry over (`a2a.helpers`, `StreamResponse` oneof, `TaskUpdater.add_artifact(append/last_chunk)`, SCREAMING_SNAKE_CASE enums).
- Tavily facts (verified 2026-11-23): `tavily-python==0.8.5` (floor `>=0.8`), `from tavily import AsyncTavilyClient`; `await client.search(query, max_results=5)`; `await client.close()`; async context manager supported. Response `dict` with `results: [{title, url, content, score, ...}]`. Errors in the `tavily.errors` module (`InvalidAPIKeyError` for 401, `UsageLimitExceededError` for 429, `ForbiddenError`; note `tavily.errors.TimeoutError` subclasses `Exception`, not the builtin). The client falls back to the `TAVILY_API_KEY` env var natively; we still read it ourselves for fail-fast startup. Python 3.13 supported.
- Env-driven ports (the deferred punch-list item): every process's bind host/port and its card's interface URL derive from the same source.
- `.gitignore` owner-provided — never modify. No credentials in the repo; `.env` never committed.
- Existing console commands keep working: `a2a-poc-server` (chat agent), `a2a-poc-client`, `a2a-poc-ui`.

## Approaches considered

1. **Routing inside the Streamlit UI** (client-side router) — rejected: produces zero agent-to-agent A2A traffic; demonstrates nothing about the protocol.
2. **Deterministic routing + translator/echo second agent** — rejected by the owner in favor of web search with an LLM decision.
3. **Host agent orchestrating search-then-synthesize** — **picked** (owner-specified): real A2A delegation, chat agent stays simple, search agent is a genuinely different kind of agent (non-LLM, tool-backed) which shows interop.

## How — decided

- **Topology & env:** host 9998 / chat 9999 / search 9997, each overridable via `A2A_POC_PORT` (per-process); the host reads `CHAT_AGENT_URL` (default `http://127.0.0.1:9999`) and `SEARCH_AGENT_URL` (default `http://127.0.0.1:9997`); the host's LLM decision uses the same `LLM_*` env as the chat agent. One `.env` holds everything. The launcher always uses the fixed defaults and injects matching `CHAT_AGENT_URL`/`SEARCH_AGENT_URL` into the host child; `A2A_POC_PORT` is a per-process override for running agents standalone (README documents that custom ports also require setting the corresponding URL vars). The bind host stays loopback-only (127.0.0.1) for every process.
- **Card identities:** search agent — name "A2A PoC Search Agent", skill id `web_search`, description "Searches the web (Tavily) and returns the top results as text." Host — name "A2A PoC Host", skill id `orchestrate`, description "Decides when web knowledge is needed, delegates to a search agent, and synthesizes the final answer via a chat agent." Chat agent's card unchanged.
- **Decision protocol:** one LLM call with a strict single-line system prompt: reply exactly `SEARCH: <refined query>` or `NO_SEARCH`. Lenient parse (case-insensitive prefix); anything unparseable → NO_SEARCH (fail safe: direct answer). The decider is an injectable async callable returning a small `Decision(needs_search: bool, query: str)`; production uses a ChatAgent-style wrapper. `ChatAgent` gains an optional `system_prompt` parameter (default = today's `SYSTEM_PROMPT`) so the decider reuses it without touching the chat agent's prompt — additive, existing tests unaffected. A decider *exception* (LLM transport/auth error) degrades gracefully: a status note ("couldn't decide, answering directly") and the no-search path — if the LLM endpoint is truly down, the synthesis call fails right after and the task fails then.
- **Search agent executor:** message text → query; `AsyncTavilyClient` injected (duck-typed for tests); `max_results=5`; results formatted `title + URL + snippet` text, emitted as a single artifact; FAILED with the error text if Tavily raises (the host treats search-task failure as degradation, not task failure).
- **Host executor flow:** task + WORKING → `decider(user_text)` → if search: status "Searching the web…" → collect the search agent's reply text via `core.stream_reply(SEARCH_AGENT_URL, query)` (deltas joined; transport errors or FAILED → status "Search unavailable (…): answering without it", results dropped) → compose the synthesis prompt (`Answer the user's question using the web search results below.` + question + results block; or the raw question when no search) → relay `core.stream_reply(CHAT_AGENT_URL, prompt)` deltas as the host's own streamed artifacts (reusing the artifact-stream pattern from `server/executor.py`) → COMPLETED. Exceptions in synthesis → FAILED + `logger.exception` (existing pattern).
- **Shared wiring:** the app-creation wiring (DefaultRequestHandler + routes) is shared between the three agents via a small helper; existing `create_app(config)` signature and its tests stay intact.
- **Launcher:** `a2a-poc-demo` spawns the three agent processes (separate processes — per-agent kill-ability demos the degradation path), prefixes each process's output, forwards Ctrl-C to all.
- **New console commands:** `a2a-poc-search-agent`, `a2a-poc-host`, `a2a-poc-demo` (existing three unchanged).

## Left to the builder

- Exact module layout inside `a2a_poc/host/` and `a2a_poc/search/` (mirror the server package's shape).
- The host's test seam for its two delegations (MockTransport card-serving per URL, or injectable stream callables) — either is fine; disclose the choice.
- Tavily client lifecycle (per-request context manager vs shared client) — disclose.
- Launcher process-spawn mechanics (console-script subprocesses vs `python -m`).
- Decider system-prompt wording (single-line protocol is pinned; wording is free).

## Builder check (2026-11-23)

A fresh reviewer read this design as the planning engineer. All factual claims about the current code verified. Three plan-shaping questions were raised and resolved by the owner: (1) the UI renders mid-stream status messages (additive-only, as recorded in Goals/Anti-goals); (2) the launcher uses fixed port defaults only, with `A2A_POC_PORT` as a per-process standalone override and the URL-sync caveat documented; (3) a decider exception degrades to the no-search path with a status note.

# Safety net + residue sweep — Design (short)

- **Date:** 2026-11-27
- **Status:** Approved in conversation (approach A of three; minimal config unification and the topology/env-name ownership split confirmed by owner)
- **Problem:** The last three refactors (shared-plumbing extraction `ff0ddec`, two renames) left residue, and the shared seams they created have no direct tests: five hardcoded port literals across four files; three config styles plus a dead `system_prompt` seam in `llm.py` left over from the 2026-11-25 decision-model switch; `.env.example` recommends `jev-1.14`, which that spec rejected; `demo.py` keys the host's env injection on a display label; there is no `tests/conftest.py` — the same fakes are copy-pasted across up to three test files, and `wiring.bind_a2a_routes`/`ReplyArtifactStream` are covered only indirectly.

## What changes (two commits, behavior unchanged)

**Commit 1 — safety net:**

1. `tests/conftest.py`: the fakes duplicated across two or more test files move there as pytest fixtures — `FakeEventQueue` (×3 executor suites), `ScriptedClient` + its card transport (×2 client suites, 54 identical lines), `FakeTavilyClient` (×2), `FakeClient` (×2), and the `_context`/`_artifact_text`/`_final_state` helpers. Assertions stay byte-identical; only construction becomes fixture injection.
2. First direct unit tests for `wiring.bind_a2a_routes` (card + JSON-RPC routes attached) and `wiring.ReplyArtifactStream` (one artifact id shared, look-ahead buffering, `last_chunk` only via `finish`, `flush_partial` never flags last).

**Commit 2 — residue sweep:**

3. Ports single-sourced in `wiring.py`: `CHAT_PORT = 9999`, `SEARCH_PORT = 9997`, `HOST_PORT = 9998`, `DEFAULT_CHAT_AGENT_URL`/`DEFAULT_SEARCH_AGENT_URL` derived from `HOST` + port. `chat/app.py`, `search/app.py`, `host/app.py`, `client/core.py` import them. Env-var *names* stay with their owners (`host/app.py` keeps `CHAT_AGENT_URL_ENV` etc.) — topology moves, config interfaces don't.
4. `host/app.py`'s inline env check adopts the shared fail-fast shape; error message byte-identical. Minimal version — no new config modules, no dataclass-ifying host/search config.
5. `build_chat_agent`/`ChatAgent` drop the unused `system_prompt` parameter (the host decider that used it was removed 2026-11-25); stale docstring fixed.
6. `demo.py`: env injection becomes declarative — `CHILDREN` carries each child's env overrides, so the host's agent URLs are keyed structurally, not by display label; `env.pop(PORT_ENV_VAR, None)` uses the wiring constant; the production-path `assert proc.stdout is not None` becomes an explicit raise; topology imports from `wiring` instead of `a2apoc.host.app`.
7. Small items: `.env.example` `jev-1.14` → `gemini-decision-1`; delete unreferenced `tests/resources/test.http`; `host/app.py` reuses the decider's timeout constant (drop the duplicated `httpx.Timeout(30.0)`); `ruff` pinned as a dev dependency with a minimal rule set and its findings fixed.

## Approaches considered

- **A. Safety net + residue sweep (picked).** Lowest risk, overrides no recorded decision, de-risks every later refactor. The repo is small and green (62 tests, ~1.5k lines), so the cheap safe pass is the highest ROI.
- **B. The deferred scaffold dedup now.** The 2026-11-24 spec deliberately deferred folding the triplicated `DefaultRequestHandler`/`InMemoryTaskStore`/`FastAPI` construction and TaskUpdater bootstrap into `wiring.py` until a fourth agent appears; with three agents the payoff is modest and doing it now relitigates a recorded timing call. Rejected for this pass.
- **C. Decompose `client/core.py`'s `stream_reply`.** The most complex function in the repo (ruff C901 12 > 10), but the 2026-11-20 spec pins the CLI output shape as a compatibility surface — highest risk, internal-only payoff. Rejected.

## Non-goals

- The deferred scaffold dedup (trigger stays: a fourth agent appears).
- `stream_reply` decomposition.
- Closing the long-lived `httpx.AsyncClient` (host) / Tavily client — real, but needs a lifespan design choice; disclosed here, deferred (the 2026-11-23 spec's "disclose" item).
- Loosening test logger-name/narration-string pins — no modules move in this pass.
- Any behavior change: env names, ports, URLs, defaults, error messages, exit codes, stdout shapes are all unchanged.

## Verification

- Full suite green (62 tests; assertions byte-identical where tests are moved).
- `uv run ruff check .` clean once pinned.
- Import smoke: all four app modules import.
- Launcher boot check with dummy env: three loopback listeners, three card curls 200, SIGINT → exit 0.
- Grep: no `9997`/`9998`/`9999` literals outside `wiring.py` (tests may pin ports).

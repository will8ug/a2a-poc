# Switch the host decider to an OpenCode decision model — Design (short)

- **Date:** 2026-11-25
- **Status:** Approved in conversation (env name and response envelope confirmed by owner); execution pending owner's go-ahead
- **Context:** the host's routing decision ("does this message need internet knowledge?") is currently an LLM prompt (`ChatAgent` + `DECIDER_SYSTEM_PROMPT`, single-line `SEARCH:`/`NO_SEARCH` protocol) on the shared chat LLM. Replace it with a purpose-built decision model over the System One protocol via OpenCode Console, model `gemini-decision-1` (Jev is unavailable in the owner's country).

## What changes (one commit, behavior change by design)

1. **`OpenCodeDecider`** in `src/a2apoc/host/decision.py` — `__init__(self, client, model: str = "gemini-decision-1", timeout: httpx.Timeout = httpx.Timeout(30.0))`, duck-typed httpx client (house pattern, injectable); `async def __call__(self, user_text: str) -> Decision`. Request: `POST https://opencode.ai/inference/systemone/v1/systemone`, `Authorization: Bearer <OPENCODE_API_KEY>`, body `{"model": self._model, "state": user_text, "questions": {"needs_search": {"type": "noul", "instructions": "Does answering this message need current information from the internet?"}}}`. Response parse (owner-observed envelope): `data["answers"]["needs_search"]`; a `"type": "refusal"` answer or non-2xx status raises (rides the existing decider-exception degradation); otherwise the `noul` float is the yes-probability, banded: **>= 0.7 → Decision(True); <= 0.3 → Decision(False); middle → Decision(True)**. Thresholds are code constants (decision-model probabilities drift; tune later if needed).
2. **`Decision` simplifies** to `@dataclass(frozen=True) class Decision: needs_search: bool` — the `query` field is dropped (decision models don't generate text; no query refinement).
3. **Executor:** the search delegation sends the **raw user message** (not a refined query); the decider-exception degradation path ("answering directly") is unchanged. `DECIDER_SYSTEM_PROMPT` and `decide_with` are removed (replaced outright).
4. **Host app:** `main()` reads `OPENCODE_API_KEY` (fail-fast naming the var, `.env`-aware) and `A2A_POC_DECISION_MODEL` (default `gemini-decision-1`), builds the httpx client + `OpenCodeDecider`. The host no longer imports `a2apoc.llm` — it becomes **LLM-free** (env: `OPENCODE_API_KEY` + `CHAT_AGENT_URL`/`SEARCH_AGENT_URL`).
5. **Tests (TDD, offline, duck-typed fake client):** decision tests pin the bands (high → True, low → False, middle → True), refusal → raises, non-2xx → raises, and the request body (model, state, the noul question); executor tests re-pin scenario 2 to the search call receiving the raw user text (and `Decision` literals to the new shape); app test unchanged.
6. **Docs:** `.env.example` gains `OPENCODE_API_KEY=your-opencode-key` (+ a commented optional `A2A_POC_DECISION_MODEL` line); README's "Configure" section gains the key (the host needs it in addition to `LLM_*` for the chat agent and `TAVILY_API_KEY` for the search agent).

## Owner-observed response envelope (grounds the parser)

```json
{
  "model": "gemini-decision-1",
  "answers": {
    "is_urgent": {"type": "noul", "noul": 0.9760494932146012, "confidence": 0.9760494932146012}
  },
  "usage": {"input_tokens": 106, "output_tokens": 0, "cost": 1.06e-05}
}
```

Note: OpenCode's `gemini-decision-1` returns `confidence` on noul answers (unlike TypeSafe's documented shape) — informational; the decision thresholds key on `noul`.

## Rejected alternatives

- Jev (`jev-1.14` / OpenRouter): unavailable in the owner's country.
- OpenRouter Decisions API: same availability problem, second vendor/key.
- `typesafe-sdk` dependency: a ~30-line envelope doesn't justify it.
- Keeping the LLM decider as a fallback: the existing decider-exception degradation already covers decision-model outages ("answering directly").

## Verification

- Full suite green (offline; decision/executor tests re-pinned as above).
- Import smoke; host boot check with a dummy `OPENCODE_API_KEY` (no decision call at startup).
- Live behavior is the owner's acceptance run: sub-second routing, status lines appear faster; wrong/missing key → host fails fast naming `OPENCODE_API_KEY`.

---

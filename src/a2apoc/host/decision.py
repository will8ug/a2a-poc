"""Route user messages via the OpenCode decision model over System One.

The decider asks one ``noul`` question — "does answering this message
need current information from the internet?" — and bands the returned
yes-probability: >= 0.7 searches, <= 0.3 answers directly, and the
uncertain middle band searches. The thresholds are code constants:
decision-model probabilities drift, so tuning happens here, not in
config.
"""

from dataclasses import dataclass

import httpx

DEFAULT_MODEL = "gemini-decision-1"

# System One inference endpoint (OpenCode Console).
_ENDPOINT = "https://opencode.ai/inference/systemone/v1/systemone"

# Shared default client timeout (httpx's own DEFAULT_TIMEOUT_CONFIG
# pattern: a module-level singleton value object).
_DEFAULT_TIMEOUT = httpx.Timeout(30.0)

# The single question asked about each message; its key also names the
# answer in the response envelope.
_QUESTION = "needs_search"
_QUESTION_INSTRUCTIONS = (
    "Does answering this message need current information from the internet?"
)

# Banding thresholds for the noul yes-probability.
_SEARCH_THRESHOLD = 0.7
_NO_SEARCH_THRESHOLD = 0.3


@dataclass(frozen=True)
class Decision:
    """The routing outcome for one user message."""

    needs_search: bool


class OpenCodeDecider:
    """Routes a message by asking the decision model one noul question.

    ``client`` is duck-typed: any object exposing async
    ``post(url, json=...)`` returning a response with ``status_code``
    and ``json()`` works (production uses ``httpx.AsyncClient``; the
    ``Authorization`` header rides the client's default headers, built
    by the host app, like the Tavily key rides the Tavily client). When
    ``client`` is None the decider creates its own
    ``httpx.AsyncClient`` with ``timeout``.

    Calling the instance routes ``user_text`` to a :class:`Decision`.
    Refusal answers and non-2xx responses raise, riding the executor's
    decider-failure degradation (answering directly).
    """

    def __init__(
        self,
        client=None,
        model: str = DEFAULT_MODEL,
        timeout: httpx.Timeout = _DEFAULT_TIMEOUT,
    ):
        if client is not None:
            self._client = client
        else:
            self._client = httpx.AsyncClient(timeout=timeout)
        self._model = model

    async def __call__(self, user_text: str) -> Decision:
        """Ask the decision model to route ``user_text``.

        The answer's ``noul`` float is the yes-probability, banded into
        a :class:`Decision` by the module thresholds.
        """
        response = await self._client.post(
            _ENDPOINT,
            json={
                "model": self._model,
                "state": user_text,
                "questions": {
                    _QUESTION: {"type": "noul", "instructions": _QUESTION_INSTRUCTIONS}
                },
            },
        )
        if not 200 <= response.status_code < 300:
            raise RuntimeError(
                f"Decision model returned HTTP {response.status_code}"
            )
        answer = response.json()["answers"][_QUESTION]
        if answer.get("type") == "refusal":
            raise RuntimeError("Decision model refused to answer")
        noul = answer["noul"]
        if noul >= _SEARCH_THRESHOLD:
            return Decision(needs_search=True)
        if noul <= _NO_SEARCH_THRESHOLD:
            return Decision(needs_search=False)
        return Decision(needs_search=True)

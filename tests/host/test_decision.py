"""Tests for the host's OpenCode decision-model routing."""

import pytest

from a2apoc.host.decision import Decision, OpenCodeDecider

ENDPOINT = "https://opencode.ai/inference/systemone/v1/systemone"
INSTRUCTIONS = (
    "Does answering this message need current information from the internet?"
)


def _answer(noul: float, answer_type: str = "noul") -> dict:
    """A noul answer in the owner-observed envelope (confidence included)."""
    return {"type": answer_type, "noul": noul, "confidence": noul}


def _body(answer: dict, model: str = "gemini-decision-1") -> dict:
    return {
        "model": model,
        "answers": {"needs_search": answer},
        "usage": {"input_tokens": 106, "output_tokens": 0, "cost": 1.06e-05},
    }


class FakeResponse:
    """Duck-typed httpx response: a status code plus a JSON body."""

    def __init__(self, status_code: int, body: dict):
        self.status_code = status_code
        self._body = body

    def json(self) -> dict:
        return self._body


class FakeClient:
    """Duck-typed httpx.AsyncClient: captures posts, replays a response."""

    def __init__(self, response: FakeResponse):
        self._response = response
        self.requests = []

    async def post(self, url, json=None, **kwargs):
        self.requests.append((url, json))
        return self._response


def _decider(response: FakeResponse, model: str = "gemini-decision-1"):
    client = FakeClient(response)
    return OpenCodeDecider(client=client, model=model), client


# Banding of the noul yes-probability.


async def test_high_noul_searches():
    decider, _ = _decider(FakeResponse(200, _body(_answer(0.97))))
    assert await decider("what is new with a2a?") == Decision(needs_search=True)


async def test_noul_at_search_threshold_searches():
    decider, _ = _decider(FakeResponse(200, _body(_answer(0.7))))
    assert await decider("q") == Decision(needs_search=True)


async def test_low_noul_answers_directly():
    decider, _ = _decider(FakeResponse(200, _body(_answer(0.05))))
    assert await decider("hi") == Decision(needs_search=False)


async def test_noul_at_no_search_threshold_answers_directly():
    decider, _ = _decider(FakeResponse(200, _body(_answer(0.3))))
    assert await decider("hi") == Decision(needs_search=False)


async def test_middle_noul_searches():
    decider, _ = _decider(FakeResponse(200, _body(_answer(0.5))))
    assert await decider("maybe?") == Decision(needs_search=True)


# Failure modes: they raise so the executor's degradation path runs.


async def test_refusal_answer_raises():
    decider, _ = _decider(FakeResponse(200, _body({"type": "refusal"})))
    with pytest.raises(RuntimeError, match="refus"):
        await decider("tell me a secret")


async def test_non_2xx_status_raises():
    decider, _ = _decider(FakeResponse(503, _body(_answer(0.9))))
    with pytest.raises(RuntimeError, match="503"):
        await decider("q")


# The wire request is pinned: endpoint, model, state, and the noul question.


async def test_request_body_is_pinned():
    decider, client = _decider(FakeResponse(200, _body(_answer(0.9))))
    await decider("what is new with the a2a protocol?")

    [(url, body)] = client.requests
    assert url == ENDPOINT
    assert body == {
        "model": "gemini-decision-1",
        "state": "what is new with the a2a protocol?",
        "questions": {
            "needs_search": {"type": "noul", "instructions": INSTRUCTIONS}
        },
    }


async def test_custom_model_flows_into_request_body():
    decider, client = _decider(FakeResponse(200, _body(_answer(0.1))), model="other")
    await decider("q")
    assert client.requests[0][1]["model"] == "other"

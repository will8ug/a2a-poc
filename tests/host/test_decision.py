"""Tests for the host's search-or-not decision parsing."""

from a2apoc.host.decision import Decision, decide_with


class FakeAgent:
    """ChatAgent-style stand-in that replays scripted deltas."""

    def __init__(self, chunks):
        self._chunks = chunks
        self.received = []

    async def stream_reply(self, user_text: str):
        self.received.append(user_text)
        for chunk in self._chunks:
            yield chunk


async def test_search_prefix_yields_refined_query():
    agent = FakeAgent(["SEARCH:", " latest A2A spec"])
    decision = await decide_with(agent, "what is the latest a2a spec?")
    assert decision == Decision(needs_search=True, query="latest A2A spec")
    assert agent.received == ["what is the latest a2a spec?"]


async def test_lowercase_search_prefix_yields_refined_query():
    decision = await decide_with(FakeAgent(["search: rust async runtime"]), "q")
    assert decision == Decision(needs_search=True, query="rust async runtime")


async def test_no_search_literal_answers_directly():
    decision = await decide_with(FakeAgent(["NO_SEARCH"]), "hello")
    assert decision == Decision(needs_search=False, query="")


async def test_lowercase_no_search_answers_directly():
    decision = await decide_with(FakeAgent(["no_search"]), "hello")
    assert decision == Decision(needs_search=False, query="")


async def test_garbage_reply_answers_directly():
    decision = await decide_with(FakeAgent(["I think maybe search?"]), "hello")
    assert decision == Decision(needs_search=False, query="")

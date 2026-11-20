from types import SimpleNamespace

from a2a_poc.server.agent import SYSTEM_PROMPT, ChatAgent


def _chunk(text: str):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text))])


def _empty_choices_chunk():
    return SimpleNamespace(choices=[])


class FakeCompletions:
    def __init__(self, chunks):
        self._chunks = chunks
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)

        async def gen():
            for c in self._chunks:
                yield c

        return gen()


class FakeClient:
    def __init__(self, chunks):
        self.chat = SimpleNamespace(completions=FakeCompletions(chunks))


async def test_stream_reply_yields_deltas_in_order():
    agent = ChatAgent(client=FakeClient([_chunk("Hel"), _chunk("lo")]), model="test-model")
    deltas = [d async for d in agent.stream_reply("hi")]
    assert deltas == ["Hel", "lo"]


async def test_stream_reply_skips_chunks_with_no_choices():
    agent = ChatAgent(
        client=FakeClient([_chunk("Hel"), _empty_choices_chunk(), _chunk("lo")]),
        model="test-model",
    )
    deltas = [d async for d in agent.stream_reply("hi")]
    assert deltas == ["Hel", "lo"]


async def test_stream_reply_sends_system_prompt_user_text_and_model():
    client = FakeClient([_chunk("ok")])
    agent = ChatAgent(client=client, model="test-model")
    async for _ in agent.stream_reply("what is a2a?"):
        pass
    (call,) = client.chat.completions.calls
    assert call["model"] == "test-model"
    assert call["stream"] is True
    contents = [m["content"] for m in call["messages"]]
    assert SYSTEM_PROMPT in contents
    assert "what is a2a?" in contents

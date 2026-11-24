from types import SimpleNamespace

import pytest

from a2a_poc.llm import ChatAgent, Config, ConfigError, SYSTEM_PROMPT, load_config


def test_load_config_reads_all_env_vars(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "http://test.local/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    cfg = load_config(env_file=None)
    assert cfg == Config(
        api_key="test-key", base_url="http://test.local/v1", model="test-model"
    )


def test_load_config_missing_vars_fail_fast(monkeypatch):
    for name in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ConfigError) as excinfo:
        load_config(env_file=None)
    for name in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"):
        assert name in str(excinfo.value)


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

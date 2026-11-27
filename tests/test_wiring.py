import pytest
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.utils import AGENT_CARD_WELL_KNOWN_PATH, DEFAULT_RPC_URL
from fastapi import FastAPI

from a2apoc.chat.card import build_agent_card
from a2apoc.wiring import (
    DEFAULT_CHAT_AGENT_URL,
    DEFAULT_SEARCH_AGENT_URL,
    HOST,
    ReplyArtifactStream,
    bind_a2a_routes,
    resolve_bind,
)


def test_resolve_bind_default(monkeypatch):
    monkeypatch.delenv("A2A_POC_PORT", raising=False)
    assert HOST == "127.0.0.1"
    assert resolve_bind(9997) == ("127.0.0.1", 9997)


def test_resolve_bind_env_override(monkeypatch):
    monkeypatch.setenv("A2A_POC_PORT", "1234")
    assert resolve_bind(9999) == (HOST, 1234)


def test_resolve_bind_invalid_env_fails_fast(monkeypatch):
    monkeypatch.setenv("A2A_POC_PORT", "abc")
    with pytest.raises(ValueError) as excinfo:
        resolve_bind(9999)
    assert "A2A_POC_PORT" in str(excinfo.value)


class _StubExecutor:
    """Executor stand-in: routes are attached, never exercised."""

    async def execute(self, context, event_queue):
        raise NotImplementedError


class _RecordingUpdater:
    """TaskUpdater stand-in recording add_artifact calls as kwargs dicts."""

    def __init__(self):
        self.calls = []

    async def add_artifact(self, parts, **kwargs):
        self.calls.append({"parts": [p.text for p in parts], **kwargs})


def test_bind_a2a_routes_attaches_card_and_jsonrpc_routes():
    card = build_agent_card("http://127.0.0.1:9999")
    handler = DefaultRequestHandler(
        agent_executor=_StubExecutor(),
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )
    app = FastAPI()

    result = bind_a2a_routes(app, card, handler)

    assert result is app
    paths = {route.path for route in app.routes}
    assert AGENT_CARD_WELL_KNOWN_PATH in paths
    assert DEFAULT_RPC_URL in paths


async def test_reply_stream_push_finish_emits_two_chunks_sharing_one_artifact():
    stream = ReplyArtifactStream()
    updater = _RecordingUpdater()

    await stream.push(updater, "a")
    await stream.push(updater, "b")
    await stream.finish(updater)

    first, second = updater.calls
    assert first["parts"] == ["a"]
    assert first["append"] is False
    assert first["last_chunk"] is None
    assert second["parts"] == ["b"]
    assert second["append"] is True
    assert second["last_chunk"] is True
    assert first["artifact_id"] == second["artifact_id"]
    assert first["name"] == second["name"] == "reply"


async def test_reply_stream_flush_partial_never_flags_last_chunk():
    stream = ReplyArtifactStream()
    updater = _RecordingUpdater()

    await stream.push(updater, "a")
    await stream.flush_partial(updater)

    (call,) = updater.calls
    assert call["parts"] == ["a"]
    assert call["append"] is False
    assert call["last_chunk"] is None


async def test_reply_stream_finish_and_flush_on_empty_stream_are_noops():
    stream = ReplyArtifactStream()
    updater = _RecordingUpdater()

    await stream.finish(updater)
    await stream.flush_partial(updater)

    assert updater.calls == []


def test_default_agent_urls_pin_topology():
    assert DEFAULT_CHAT_AGENT_URL == "http://127.0.0.1:9999"
    assert DEFAULT_SEARCH_AGENT_URL == "http://127.0.0.1:9997"

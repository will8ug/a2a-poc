"""Shared test fakes: the stand-ins duplicated across two or more suites.

FakeEventQueue and the _context/_artifact_text/_final_state helpers come
from the chat/search/host executor suites; ScriptedClient and its card
transport from the two client suites; FakeTavilyClient from the two
search suites. Using tests keep their assertions byte-identical; only
construction becomes fixture injection.
"""

from types import SimpleNamespace

import httpx
import pytest
from a2a.helpers import new_text_message
from a2a.types import Role
from google.protobuf.json_format import MessageToJson

from a2apoc.chat.card import build_agent_card


class FakeEventQueue:
    def __init__(self):
        self.events = []

    async def enqueue_event(self, event):
        self.events.append(event)


class ScriptedClient:
    """Stand-in for ``a2a.client.Client`` that replays a scripted event stream."""

    def __init__(self, events):
        self._events = events

    async def send_message(self, request):
        for event in self._events:
            yield event

    async def close(self):
        pass


class FakeTavilyClient:
    """Duck-typed stand-in for ``tavily.AsyncTavilyClient``."""

    def __init__(self, response=None, error=None):
        self._response = response
        self._error = error
        self.calls = []

    async def search(self, query, **kwargs):
        self.calls.append((query, kwargs))
        if self._error:
            raise self._error
        return self._response


@pytest.fixture
def queue() -> FakeEventQueue:
    return FakeEventQueue()


@pytest.fixture
def _context():
    def make(text: str):
        return SimpleNamespace(
            message=new_text_message(text, role=Role.ROLE_USER), current_task=None
        )

    return make


@pytest.fixture
def _artifact_text():
    def make(events):
        parts = []
        for e in events:
            artifact = getattr(e, "artifact", None)
            if artifact is not None:
                parts.extend(p.text for p in artifact.parts)
        return "".join(parts)

    return make


@pytest.fixture
def _final_state():
    def make(events):
        states = [e.status.state for e in events if hasattr(e, "status")]
        return states[-1]

    return make


@pytest.fixture
def scripted_client() -> type[ScriptedClient]:
    return ScriptedClient


@pytest.fixture
def _card_transport():
    def make():
        """Transport whose only answer is a well-formed agent card."""
        card_json = MessageToJson(build_agent_card("http://127.0.0.1:9999"))

        def _serve_card(request):
            return httpx.Response(
                200, content=card_json, headers={"content-type": "application/json"}
            )

        return httpx.MockTransport(_serve_card)

    return make


@pytest.fixture
def fake_tavily_client() -> type[FakeTavilyClient]:
    return FakeTavilyClient

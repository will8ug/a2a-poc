import httpx
import pytest

from google.protobuf.json_format import MessageToJson

from a2a.client import A2AClientError
from a2a.helpers import new_text_message
from a2a.types import (
    Artifact,
    Part,
    StreamResponse,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)

from a2a_poc.server.card import build_agent_card
from a2a_poc.client.core import Delta, Status, stream_reply


class ScriptedClient:
    """Stand-in for ``a2a.client.Client`` that replays a scripted event stream."""

    def __init__(self, events):
        self._events = events

    async def send_message(self, request):
        for event in self._events:
            yield event

    async def close(self):
        pass


def _card_transport():
    """Transport whose only answer is a well-formed agent card."""
    card_json = MessageToJson(build_agent_card("http://127.0.0.1:9999"))

    def _serve_card(request):
        return httpx.Response(
            200, content=card_json, headers={"content-type": "application/json"}
        )

    return httpx.MockTransport(_serve_card)


def _status_update(state, message=None):
    status = (
        TaskStatus(state=state, message=message)
        if message is not None
        else TaskStatus(state=state)
    )
    return StreamResponse(
        status_update=TaskStatusUpdateEvent(
            task_id="t1", context_id="c1", status=status
        )
    )


def _artifact_update(text):
    return StreamResponse(
        artifact_update=TaskArtifactUpdateEvent(
            task_id="t1",
            context_id="c1",
            artifact=Artifact(artifact_id="a1", parts=[Part(text=text)]),
        )
    )


async def test_core_yields_deltas_and_status_in_order():
    events = [
        _status_update(TaskState.TASK_STATE_WORKING),
        _artifact_update("Hel"),
        _artifact_update("lo"),
        _status_update(TaskState.TASK_STATE_COMPLETED),
    ]

    async def factory(card):
        return ScriptedClient(events)

    received = []
    async for event in stream_reply(
        "http://127.0.0.1:9999",
        "hi",
        httpx_client=httpx.AsyncClient(transport=_card_transport()),
        client_factory=factory,
    ):
        received.append(event)

    assert received == [
        Status(state=TaskState.TASK_STATE_WORKING, message=None),
        Delta(text="Hel"),
        Delta(text="lo"),
        Status(state=TaskState.TASK_STATE_COMPLETED, message=None),
    ]


async def test_core_failed_task_ends_without_systemexit_and_prints_nothing(capsys):
    events = [
        _status_update(TaskState.TASK_STATE_WORKING),
        _status_update(
            TaskState.TASK_STATE_FAILED,
            message=new_text_message("LLM call failed: boom"),
        ),
    ]

    async def factory(card):
        return ScriptedClient(events)

    received = []
    async for event in stream_reply(
        "http://127.0.0.1:9999",
        "hi",
        httpx_client=httpx.AsyncClient(transport=_card_transport()),
        client_factory=factory,
    ):
        received.append(event)

    assert received[-1] == Status(
        state=TaskState.TASK_STATE_FAILED, message="LLM call failed: boom"
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


async def test_core_propagates_connection_errors():
    def _refuse(request):
        raise httpx.ConnectError("connection refused")

    transport = httpx.MockTransport(_refuse)

    with pytest.raises(A2AClientError):
        async for _event in stream_reply(
            "http://127.0.0.1:1",
            "hi",
            httpx_client=httpx.AsyncClient(transport=transport),
        ):
            pass

import httpx
import pytest

from a2a.client import A2AClientError
from a2a.helpers import new_text_message
from a2a.types import (
    Artifact,
    Part,
    StreamResponse,
    Task,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)

from a2apoc.client.core import Delta, Status, default_timeout, stream_reply


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


async def test_core_yields_deltas_and_status_in_order(scripted_client, _card_transport):
    events = [
        _status_update(TaskState.TASK_STATE_WORKING),
        _artifact_update("Hel"),
        _artifact_update("lo"),
        _status_update(TaskState.TASK_STATE_COMPLETED),
    ]

    async def factory(card):
        return scripted_client(events)

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


async def test_core_failed_task_ends_without_systemexit_and_prints_nothing(
    scripted_client, _card_transport, capsys
):
    events = [
        _status_update(TaskState.TASK_STATE_WORKING),
        _status_update(
            TaskState.TASK_STATE_FAILED,
            message=new_text_message("LLM call failed: boom"),
        ),
    ]

    async def factory(card):
        return scripted_client(events)

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


def _task_response(state, artifact_texts=(), message=None):
    task = Task(
        id="t1",
        context_id="c1",
        status=(
            TaskStatus(state=state, message=message)
            if message is not None
            else TaskStatus(state=state)
        ),
    )
    for i, text in enumerate(artifact_texts):
        task.artifacts.append(
            Artifact(
                artifact_id=f"a{i}", name="search_results", parts=[Part(text=text)]
            )
        )
    return StreamResponse(task=task)


@pytest.fixture
def _collect(scripted_client, _card_transport):
    """Collect stream_reply events with a scripted client and card transport."""

    async def collect(events):
        async def factory(card):
            return scripted_client(events)

        received = []
        async for event in stream_reply(
            "http://127.0.0.1:9999",
            "hi",
            httpx_client=httpx.AsyncClient(transport=_card_transport()),
            client_factory=factory,
        ):
            received.append(event)
        return received

    return collect


async def test_core_translates_final_task_from_non_streaming_agent(_collect):
    events = [
        _task_response(
            TaskState.TASK_STATE_COMPLETED,
            artifact_texts=["A2A is an agent-to-agent protocol."],
        )
    ]

    assert await _collect(events) == [
        Delta(text="A2A is an agent-to-agent protocol."),
        Status(state=TaskState.TASK_STATE_COMPLETED, message=None),
    ]


async def test_core_translates_failed_task_with_reason(_collect):
    events = [
        _task_response(
            TaskState.TASK_STATE_FAILED,
            message=new_text_message("Search failed: boom"),
        )
    ]

    assert await _collect(events) == [
        Status(state=TaskState.TASK_STATE_FAILED, message="Search failed: boom"),
    ]


async def test_core_ignores_non_terminal_task_event_in_stream(_collect):
    # A streaming response's first event is the initial task (SUBMITTED);
    # it must not surface as an extra leading Status.
    events = [
        _task_response(TaskState.TASK_STATE_SUBMITTED),
        _status_update(TaskState.TASK_STATE_WORKING),
        _artifact_update("Hel"),
        _status_update(TaskState.TASK_STATE_COMPLETED),
    ]

    assert await _collect(events) == [
        Status(state=TaskState.TASK_STATE_WORKING, message=None),
        Delta(text="Hel"),
        Status(state=TaskState.TASK_STATE_COMPLETED, message=None),
    ]


def test_default_timeout_defaults(monkeypatch):
    monkeypatch.delenv("A2A_POC_TIMEOUT", raising=False)

    timeout = default_timeout()

    assert timeout.read == 60.0
    assert timeout.connect == 5.0
    assert timeout.write == 10.0
    assert timeout.pool == 5.0


def test_default_timeout_env_override(monkeypatch):
    monkeypatch.setenv("A2A_POC_TIMEOUT", "120")

    timeout = default_timeout()

    assert timeout.read == 120.0
    assert timeout.connect == 5.0
    assert timeout.write == 10.0
    assert timeout.pool == 5.0


def test_default_timeout_invalid_env(monkeypatch):
    monkeypatch.setenv("A2A_POC_TIMEOUT", "abc")

    with pytest.raises(ValueError, match="A2A_POC_TIMEOUT"):
        default_timeout()

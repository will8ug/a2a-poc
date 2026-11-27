import httpx
import pytest
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

from a2apoc.client.cli import main, run


async def test_client_dead_server_friendly_error(capsys):
    def _refuse(request):
        raise httpx.ConnectError("connection refused")

    transport = httpx.MockTransport(_refuse)
    with pytest.raises(SystemExit) as excinfo:
        await run(
            "http://127.0.0.1:1",
            "hi",
            httpx_client=httpx.AsyncClient(transport=transport),
        )
    assert excinfo.value.code == 1
    assert "cannot reach" in capsys.readouterr().err


async def test_client_malformed_base_url_friendly_error(capsys):
    with pytest.raises(SystemExit) as excinfo:
        await run("http://[::1", "hi")
    assert excinfo.value.code == 1
    assert "cannot reach" in capsys.readouterr().err


async def test_client_failed_task_prints_reason_and_exits_nonzero(
    scripted_client, _card_transport, capsys
):
    events = [
        StreamResponse(
            status_update=TaskStatusUpdateEvent(
                task_id="t1",
                context_id="c1",
                status=TaskStatus(state=TaskState.TASK_STATE_WORKING),
            )
        ),
        StreamResponse(
            artifact_update=TaskArtifactUpdateEvent(
                task_id="t1",
                context_id="c1",
                artifact=Artifact(artifact_id="a1", parts=[Part(text="Hel")]),
            )
        ),
        StreamResponse(
            status_update=TaskStatusUpdateEvent(
                task_id="t1",
                context_id="c1",
                status=TaskStatus(
                    state=TaskState.TASK_STATE_FAILED,
                    message=new_text_message("LLM call failed: 401 bad api key"),
                ),
            )
        ),
    ]

    async def factory(card):
        return scripted_client(events)

    with pytest.raises(SystemExit) as excinfo:
        await run(
            "http://127.0.0.1:9999",
            "hi",
            httpx_client=httpx.AsyncClient(transport=_card_transport()),
            client_factory=factory,
        )
    assert excinfo.value.code == 1
    out = capsys.readouterr()
    assert "LLM call failed: 401 bad api key" in out.out
    assert "final state: TASK_STATE_FAILED" in out.out
    assert out.err == ""


def test_main_help_exits_zero(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])
    assert excinfo.value.code == 0
    assert "base-url" in capsys.readouterr().out

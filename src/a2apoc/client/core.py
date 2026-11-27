"""Reusable A2A client core: stream agent replies as typed events.

Side-effect free (no printing, no exit codes, no exception translation):
frontends such as ``cli.py`` (and the upcoming Streamlit UI) consume
``stream_reply`` and own all presentation and error translation.
"""

import os
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

import httpx
from a2a.client import A2ACardResolver, Client, ClientConfig, create_client
from a2a.helpers import new_text_message
from a2a.types import AgentCard, Role, SendMessageRequest, TaskState

from a2apoc.wiring import HOST, HOST_PORT

DEFAULT_BASE_URL = f"http://{HOST}:{HOST_PORT}"

TIMEOUT_ENV_VAR = "A2A_POC_TIMEOUT"

# httpx's defaults: 5s connect/write/pool; only the read timeout is raised.
_CONNECT_TIMEOUT = 5.0
_WRITE_TIMEOUT = 10.0
_POOL_TIMEOUT = 5.0
_DEFAULT_READ_TIMEOUT = 60.0

ClientFactory = Callable[[AgentCard], Awaitable[Client]]


def default_timeout() -> httpx.Timeout:
    """Build the httpx timeout for clients this module creates.

    The read timeout (default 60.0 seconds, overridable at call time via
    the ``A2A_POC_TIMEOUT`` env var as float seconds) covers agent-side
    time-to-first-byte: the chat agent's LLM time-to-first-token on SSE
    streams and the search agent's non-streaming Tavily round trip both
    regularly exceed httpx's 5-second default. A value that does not
    parse as a float raises :class:`ValueError` naming the env var.
    """
    raw = os.environ.get(TIMEOUT_ENV_VAR)
    if raw is None:
        read = _DEFAULT_READ_TIMEOUT
    else:
        try:
            read = float(raw)
        except ValueError:
            raise ValueError(
                f"{TIMEOUT_ENV_VAR} must be a float, got {raw!r}"
            ) from None
    return httpx.Timeout(
        connect=_CONNECT_TIMEOUT, read=read, write=_WRITE_TIMEOUT, pool=_POOL_TIMEOUT
    )


# Task states that end a task's lifecycle. Non-streaming agents answer
# message/send with one final task in one of these states; streaming
# agents send the initial task (SUBMITTED) as the first stream event.
_TERMINAL_TASK_STATES = frozenset(
    {
        TaskState.TASK_STATE_COMPLETED,
        TaskState.TASK_STATE_FAILED,
        TaskState.TASK_STATE_CANCELED,
        TaskState.TASK_STATE_REJECTED,
    }
)


@dataclass(frozen=True)
class Delta:
    """A chunk of artifact text streamed from the agent."""

    text: str


@dataclass(frozen=True)
class Status:
    """A task-state transition observed in the reply stream.

    ``message`` is the joined text of the status message's parts when the
    status carries a message (e.g. the failure reason on FAILED), else None.
    """

    state: int
    message: str | None


async def stream_reply(
    base_url: str,
    user_text: str,
    httpx_client: httpx.AsyncClient | None = None,
    client_factory: ClientFactory | None = None,
) -> AsyncIterator[Delta | Status]:
    """Stream the agent's reply to ``user_text`` as typed events.

    Resolves the agent card at ``base_url``, sends the message, and yields
    ``Delta`` for each streamed artifact text chunk and ``Status`` for each
    task-state transition, in arrival order. Non-streaming agents reply
    with one final task (artifacts plus a terminal status); that task is
    translated into the same typed events, while the non-terminal task a
    streaming agent sends first is not surfaced. Transport and protocol
    errors propagate to the caller. Creates and closes an HTTP client
    only when ``httpx_client`` is not supplied; the A2A client is always
    closed (it never closes a shared ``httpx_client``).
    ``client_factory`` overrides how the A2A client is built from the
    resolved card (a seam for tests that script the event stream).
    """
    owns_client = httpx_client is None
    http_client = (
        httpx_client
        if httpx_client is not None
        else httpx.AsyncClient(timeout=default_timeout())
    )
    try:
        resolver = A2ACardResolver(httpx_client=http_client, base_url=base_url)
        agent_card = await resolver.get_agent_card()
        if client_factory is None:
            client = await create_client(
                agent=agent_card,
                client_config=ClientConfig(streaming=True, httpx_client=http_client),
            )
        else:
            client = await client_factory(agent_card)
        try:
            request = SendMessageRequest(
                message=new_text_message(user_text, role=Role.ROLE_USER)
            )
            async for event in client.send_message(request):
                if event.HasField("artifact_update"):
                    for part in event.artifact_update.artifact.parts:
                        if part.text:
                            yield Delta(text=part.text)
                elif event.HasField("status_update"):
                    status = event.status_update.status
                    yield Status(
                        state=status.state,
                        message=_status_message_text(status),
                    )
                elif _is_final_task(event):
                    # Non-streaming agents answer message/send with the
                    # final task — artifacts plus a terminal status —
                    # instead of streamed updates. Translate it into the
                    # same typed events so consumers see one uniform
                    # stream.
                    for artifact in event.task.artifacts:
                        for part in artifact.parts:
                            if part.text:
                                yield Delta(text=part.text)
                    task_status = event.task.status
                    yield Status(
                        state=task_status.state,
                        message=_status_message_text(task_status),
                    )
        finally:
            await client.close()
    finally:
        if owns_client:
            await http_client.aclose()


def _is_final_task(event) -> bool:
    """Whether ``event`` carries a terminal-state task (a final reply)."""
    return event.HasField("task") and event.task.status.state in _TERMINAL_TASK_STATES


def _status_message_text(status) -> str | None:
    """Return the status message's text, or None when it carries no message."""
    if not status.HasField("message"):
        return None
    return "\n".join(part.text for part in status.message.parts if part.text)

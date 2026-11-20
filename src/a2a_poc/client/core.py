"""Reusable A2A client core: stream agent replies as typed events.

Side-effect free (no printing, no exit codes, no exception translation):
frontends such as ``cli.py`` (and the upcoming Streamlit UI) consume
``stream_reply`` and own all presentation and error translation.
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

import httpx

from a2a.client import A2ACardResolver, Client, ClientConfig, create_client
from a2a.helpers import new_text_message
from a2a.types import AgentCard, Role, SendMessageRequest

DEFAULT_BASE_URL = "http://127.0.0.1:9999"

ClientFactory = Callable[[AgentCard], Awaitable[Client]]


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
    task-state transition, in arrival order. Transport and protocol errors
    propagate to the caller. Creates and closes an HTTP client only when
    ``httpx_client`` is not supplied; the A2A client is always closed (it
    never closes a shared ``httpx_client``). ``client_factory`` overrides
    how the A2A client is built from the resolved card (a seam for tests
    that script the event stream).
    """
    owns_client = httpx_client is None
    http_client = httpx_client if httpx_client is not None else httpx.AsyncClient()
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
        finally:
            await client.close()
    finally:
        if owns_client:
            await http_client.aclose()


def _status_message_text(status) -> str | None:
    """Return the status message's text, or None when it carries no message."""
    if not status.HasField("message"):
        return None
    return "\n".join(part.text for part in status.message.parts if part.text)

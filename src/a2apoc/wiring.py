"""Shared A2A server wiring: bind-address resolution, route attachment,
and the look-ahead reply artifact stream."""

import os
import uuid

from a2a.helpers import new_text_part
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import (
    add_a2a_routes_to_fastapi,
    create_agent_card_routes,
    create_jsonrpc_routes,
)
from a2a.server.tasks import TaskUpdater
from a2a.types import AgentCard
from a2a.utils import AGENT_CARD_WELL_KNOWN_PATH, DEFAULT_RPC_URL
from fastapi import FastAPI

HOST = "127.0.0.1"

PORT_ENV_VAR = "A2A_POC_PORT"

CHAT_PORT = 9999
SEARCH_PORT = 9997
HOST_PORT = 9998

DEFAULT_CHAT_AGENT_URL = f"http://{HOST}:{CHAT_PORT}"
DEFAULT_SEARCH_AGENT_URL = f"http://{HOST}:{SEARCH_PORT}"


def resolve_bind(default_port: int) -> tuple[str, int]:
    """Resolve the server bind address from the ``A2A_POC_PORT`` env var.

    Returns ``(host, port)``; the host is always :data:`HOST`. A missing
    env var falls back to ``default_port``; a value that does not parse
    as an int raises :class:`ValueError` naming the env var.
    """
    raw = os.environ.get(PORT_ENV_VAR)
    if raw is None:
        return HOST, default_port
    try:
        port = int(raw)
    except ValueError:
        raise ValueError(
            f"{PORT_ENV_VAR} must be an integer, got {raw!r}"
        ) from None
    return HOST, port


def bind_a2a_routes(
    app: FastAPI, agent_card: AgentCard, request_handler: DefaultRequestHandler
) -> FastAPI:
    """Attach the agent card and A2A JSON-RPC routes to ``app``."""
    add_a2a_routes_to_fastapi(
        app,
        agent_card_routes=create_agent_card_routes(
            agent_card, card_url=AGENT_CARD_WELL_KNOWN_PATH
        ),
        jsonrpc_routes=create_jsonrpc_routes(
            request_handler, rpc_url=DEFAULT_RPC_URL
        ),
    )
    return app


_REPLY_ARTIFACT_NAME = "reply"


class ReplyArtifactStream:
    """Streams one reply artifact through a one-delta look-ahead buffer.

    All chunks share one artifact id: the first chunk creates the
    artifact, later ones append to it, and the final one is flagged as
    the last chunk. Each delta is held until the next one arrives (or
    the stream ends) so the final update can be marked ``last_chunk``.
    """

    def __init__(self) -> None:
        self._artifact_id = str(uuid.uuid4())
        self._append = False
        self._pending: str | None = None

    async def push(self, updater: TaskUpdater, delta: str) -> None:
        """Hold ``delta`` back, emitting the previously held one, if any."""
        if self._pending is not None:
            await self._emit(updater, self._pending)
        self._pending = delta

    async def finish(self, updater: TaskUpdater) -> None:
        """Emit the held delta, if any, as the artifact's final chunk."""
        if self._pending is not None:
            await self._emit(updater, self._pending, last_chunk=True)
            self._pending = None

    async def flush_partial(self, updater: TaskUpdater) -> None:
        """Emit the held delta, if any, after a mid-stream failure.

        The emission is never marked ``last_chunk``: the reply was cut
        short, so consumers must not treat the artifact as complete.
        """
        if self._pending is not None:
            await self._emit(updater, self._pending)

    async def _emit(
        self, updater: TaskUpdater, text: str, last_chunk: bool | None = None
    ) -> None:
        await updater.add_artifact(
            [new_text_part(text)],
            artifact_id=self._artifact_id,
            name=_REPLY_ARTIFACT_NAME,
            append=self._append,
            last_chunk=last_chunk,
        )
        self._append = True

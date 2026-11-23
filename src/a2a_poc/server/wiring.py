"""Shared A2A server wiring: bind-address resolution and route attachment."""

import os

from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import (
    add_a2a_routes_to_fastapi,
    create_agent_card_routes,
    create_jsonrpc_routes,
)
from a2a.types import AgentCard
from a2a.utils import AGENT_CARD_WELL_KNOWN_PATH, DEFAULT_RPC_URL
from fastapi import FastAPI

HOST = "127.0.0.1"

PORT_ENV_VAR = "A2A_POC_PORT"


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

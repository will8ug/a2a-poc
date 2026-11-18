"""FastAPI server exposing the PoC chat agent over the A2A protocol."""

import uvicorn
from fastapi import FastAPI

from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import (
    add_a2a_routes_to_fastapi,
    create_agent_card_routes,
    create_jsonrpc_routes,
)
from a2a.server.tasks import InMemoryTaskStore
from a2a.utils import AGENT_CARD_WELL_KNOWN_PATH, DEFAULT_RPC_URL

from a2a_poc.agent import build_chat_agent
from a2a_poc.card import build_agent_card
from a2a_poc.config import Config, load_config
from a2a_poc.executor import ChatAgentExecutor

HOST = "127.0.0.1"
PORT = 9999


def create_app(config: Config | None = None) -> FastAPI:
    """Build a FastAPI app serving the agent card and A2A JSON-RPC routes.

    ``config`` defaults to :func:`load_config`; pass an explicit config in
    tests to avoid touching the environment.
    """
    config = config or load_config()
    agent = build_chat_agent(config)
    card = build_agent_card(f"http://{HOST}:{PORT}")
    handler = DefaultRequestHandler(
        agent_executor=ChatAgentExecutor(agent),
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )
    app = FastAPI()
    add_a2a_routes_to_fastapi(
        app,
        agent_card_routes=create_agent_card_routes(
            card, card_url=AGENT_CARD_WELL_KNOWN_PATH
        ),
        jsonrpc_routes=create_jsonrpc_routes(handler, rpc_url=DEFAULT_RPC_URL),
    )
    return app


def main() -> None:
    """Run the server (console entry point ``a2a-poc-server``)."""
    uvicorn.run(create_app(load_config()), host=HOST, port=PORT)

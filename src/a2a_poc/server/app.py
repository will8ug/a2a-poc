"""FastAPI server exposing the PoC chat agent over the A2A protocol."""

import uvicorn
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from fastapi import FastAPI

from a2a_poc.server.agent import build_chat_agent
from a2a_poc.server.card import build_agent_card
from a2a_poc.server.config import Config, load_config
from a2a_poc.server.executor import ChatAgentExecutor
from a2a_poc.server.wiring import HOST, bind_a2a_routes, resolve_bind

PORT = 9999


def create_app(config: Config | None = None, port: int = PORT) -> FastAPI:
    """Build a FastAPI app serving the agent card and A2A JSON-RPC routes.

    ``config`` defaults to :func:`load_config`; pass an explicit config in
    tests to avoid touching the environment. ``port`` defaults to
    :data:`PORT` and sets the URL the agent card advertises.
    """
    config = config or load_config()
    agent = build_chat_agent(config)
    card = build_agent_card(f"http://{HOST}:{port}")
    handler = DefaultRequestHandler(
        agent_executor=ChatAgentExecutor(agent),
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )
    app = FastAPI()
    return bind_a2a_routes(app, card, handler)


def main() -> None:
    """Run the server (console entry point ``a2a-poc-server``)."""
    host, port = resolve_bind(PORT)
    uvicorn.run(create_app(load_config(), port=port), host=host, port=port)


if __name__ == "__main__":
    main()

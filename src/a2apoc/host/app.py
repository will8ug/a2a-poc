"""FastAPI server exposing the PoC multi-agent host over the A2A protocol."""

import os
from collections.abc import Awaitable, Callable

import httpx
import uvicorn
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from dotenv import load_dotenv
from fastapi import FastAPI

from a2apoc.host.card import build_host_agent_card
from a2apoc.host.decision import (
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT,
    Decision,
    OpenCodeDecider,
)
from a2apoc.host.executor import HostAgentExecutor
from a2apoc.wiring import (
    DEFAULT_CHAT_AGENT_URL,
    DEFAULT_SEARCH_AGENT_URL,
    HOST,
    HOST_PORT,
    bind_a2a_routes,
    resolve_bind,
)

PORT = HOST_PORT

CHAT_AGENT_URL_ENV = "CHAT_AGENT_URL"
SEARCH_AGENT_URL_ENV = "SEARCH_AGENT_URL"
OPENCODE_API_KEY_ENV = "OPENCODE_API_KEY"
DECISION_MODEL_ENV = "A2A_POC_DECISION_MODEL"


class HostConfigError(RuntimeError):
    """Raised when the host's required environment variables are missing."""


Decider = Callable[[str], Awaitable[Decision]]


def create_host_app(
    decider: Decider, chat_url: str, search_url: str, port: int = PORT
) -> FastAPI:
    """Build a FastAPI app serving the host agent card and A2A routes.

    ``decider`` is the async callable ``(user_text) -> Decision`` routing
    each message (tests inject a fake; ``main`` builds an
    ``OpenCodeDecider``). ``chat_url``/``search_url`` are the downstream
    agents' base URLs. ``port`` defaults to :data:`PORT` and sets the URL
    the agent card advertises.
    """
    card = build_host_agent_card(f"http://{HOST}:{port}")
    handler = DefaultRequestHandler(
        agent_executor=HostAgentExecutor(decider, chat_url, search_url),
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )
    app = FastAPI()
    return bind_a2a_routes(app, card, handler)


def main() -> None:
    """Run the host (console entry point ``a2a-poc-host``)."""
    load_dotenv(".env")
    api_key = os.environ.get(OPENCODE_API_KEY_ENV)
    if not api_key:
        raise HostConfigError(
            f"Missing required environment variable: {OPENCODE_API_KEY_ENV}. "
            "Copy .env.example to .env and fill in values."
        )
    model = os.environ.get(DECISION_MODEL_ENV, DEFAULT_MODEL)
    # The decider never sees the key: it rides the client's default
    # headers, as the Tavily key rides the Tavily client.
    client = httpx.AsyncClient(
        timeout=DEFAULT_TIMEOUT,
        headers={"Authorization": f"Bearer {api_key}"},
    )
    decider = OpenCodeDecider(client=client, model=model)
    chat_url = os.environ.get(CHAT_AGENT_URL_ENV, DEFAULT_CHAT_AGENT_URL)
    search_url = os.environ.get(SEARCH_AGENT_URL_ENV, DEFAULT_SEARCH_AGENT_URL)
    host, port = resolve_bind(PORT)
    uvicorn.run(
        create_host_app(decider, chat_url, search_url, port=port),
        host=host,
        port=port,
    )


if __name__ == "__main__":
    main()

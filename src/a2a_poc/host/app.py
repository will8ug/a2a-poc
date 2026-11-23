"""FastAPI server exposing the PoC multi-agent host over the A2A protocol."""

import functools
import os
from collections.abc import Awaitable, Callable

import uvicorn
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from fastapi import FastAPI

from a2a_poc.host.card import build_host_agent_card
from a2a_poc.host.decision import DECIDER_SYSTEM_PROMPT, Decision, decide_with
from a2a_poc.host.executor import HostAgentExecutor
from a2a_poc.chat.agent import build_chat_agent
from a2a_poc.chat.config import load_config
from a2a_poc.wiring import HOST, bind_a2a_routes, resolve_bind

PORT = 9998

CHAT_AGENT_URL_ENV = "CHAT_AGENT_URL"
SEARCH_AGENT_URL_ENV = "SEARCH_AGENT_URL"

DEFAULT_CHAT_AGENT_URL = "http://127.0.0.1:9999"
DEFAULT_SEARCH_AGENT_URL = "http://127.0.0.1:9997"

Decider = Callable[[str], Awaitable[Decision]]


def create_host_app(
    decider: Decider, chat_url: str, search_url: str, port: int = PORT
) -> FastAPI:
    """Build a FastAPI app serving the host agent card and A2A routes.

    ``decider`` is the async callable ``(user_text) -> Decision`` routing
    each message (tests inject a fake; ``main`` builds one around a
    ChatAgent). ``chat_url``/``search_url`` are the downstream agents'
    base URLs. ``port`` defaults to :data:`PORT` and sets the URL the
    agent card advertises.
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
    config = load_config()
    agent = build_chat_agent(config, system_prompt=DECIDER_SYSTEM_PROMPT)
    decider = functools.partial(decide_with, agent)
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

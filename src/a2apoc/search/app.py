"""FastAPI server exposing the PoC search agent over the A2A protocol."""

import uvicorn
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from fastapi import FastAPI

from a2apoc.search.card import build_search_agent_card
from a2apoc.search.config import load_tavily_config
from a2apoc.search.executor import SearchAgentExecutor
from a2apoc.search.tavily_client import TavilySearcher, build_tavily_searcher
from a2apoc.wiring import HOST, SEARCH_PORT, bind_a2a_routes, resolve_bind

PORT = SEARCH_PORT


def create_search_app(
    searcher: TavilySearcher, port: int = PORT
) -> FastAPI:
    """Build a FastAPI app serving the search agent card and A2A routes.

    ``searcher`` must be passed explicitly (tests use a duck-typed fake;
    ``main`` builds the production Tavily client). ``port`` defaults to
    :data:`PORT` and sets the URL the agent card advertises.
    """
    card = build_search_agent_card(f"http://{HOST}:{port}")
    handler = DefaultRequestHandler(
        agent_executor=SearchAgentExecutor(searcher),
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )
    app = FastAPI()
    return bind_a2a_routes(app, card, handler)


def main() -> None:
    """Run the server (console entry point ``a2a-poc-search-agent``)."""
    searcher = build_tavily_searcher(load_tavily_config())
    host, port = resolve_bind(PORT)
    uvicorn.run(create_search_app(searcher, port=port), host=host, port=port)


if __name__ == "__main__":
    main()

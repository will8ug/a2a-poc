"""Searcher wrapping the Tavily async client.

``AsyncTavilyClient`` is duck-typed: any object exposing
``async search(query, **kwargs)`` returning a Tavily response dict
works.
"""

from tavily import AsyncTavilyClient

MAX_RESULTS = 5

_NO_RESULTS = "No results found."


class TavilySearcher:
    """Searches the web via Tavily and formats the top results as text."""

    def __init__(self, client):
        self._client = client

    async def search(self, query: str) -> str:
        """Run ``query`` and return formatted results, one block per hit."""
        response = await self._client.search(query, max_results=MAX_RESULTS)
        results = response.get("results", [])
        if not results:
            return _NO_RESULTS
        blocks = []
        for result in results:
            blocks.append(
                f"{result.get('title', '')}\n"
                f"{result.get('url', '')}\n"
                f"{result.get('content', '')}"
            )
        return "\n\n".join(blocks)


def build_tavily_searcher(api_key: str) -> TavilySearcher:
    """Build a TavilySearcher with a real AsyncTavilyClient."""
    return TavilySearcher(client=AsyncTavilyClient(api_key=api_key))

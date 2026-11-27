from a2apoc.search.tavily_client import TavilySearcher


def _response(results):
    return {
        "query": "q",
        "results": [
            {
                "title": r["title"],
                "url": r["url"],
                "content": r["content"],
                "score": 0.9,
            }
            for r in results
        ],
    }


async def test_search_formats_title_url_and_snippet(fake_tavily_client):
    client = fake_tavily_client(
        response=_response(
            [
                {
                    "title": "A2A Protocol",
                    "url": "https://a2a.example/protocol",
                    "content": "Agent-to-agent protocol overview.",
                },
                {
                    "title": "Tavily Docs",
                    "url": "https://tavily.example/docs",
                    "content": "Search API documentation.",
                },
            ]
        )
    )
    searcher = TavilySearcher(client)
    output = await searcher.search("what is a2a")
    assert "A2A Protocol" in output
    assert "https://a2a.example/protocol" in output
    assert "Agent-to-agent protocol overview." in output
    assert "Tavily Docs" in output
    assert "https://tavily.example/docs" in output
    assert "Search API documentation." in output


async def test_search_passes_max_results_five(fake_tavily_client):
    client = fake_tavily_client(response=_response([]))
    searcher = TavilySearcher(client)
    await searcher.search("anything")
    query, kwargs = client.calls[0]
    assert query == "anything"
    assert kwargs["max_results"] == 5


async def test_search_empty_results_returns_placeholder(fake_tavily_client):
    client = fake_tavily_client(response=_response([]))
    searcher = TavilySearcher(client)
    assert await searcher.search("obscure") == "No results found."

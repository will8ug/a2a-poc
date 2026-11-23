from fastapi.testclient import TestClient

from a2a_poc.search.app import create_search_app
from a2a_poc.search.tavily_client import TavilySearcher


class FakeTavilyClient:
    async def search(self, query, **kwargs):
        return {"results": []}


def _app():
    return create_search_app(searcher=TavilySearcher(FakeTavilyClient()))


def test_agent_card_route_serves_card():
    client = TestClient(_app())
    response = client.get("/.well-known/agent-card.json")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "A2A PoC Search Agent"
    assert body["capabilities"]["streaming"] is False
    skill = body["skills"][0]
    assert skill["id"] == "web_search"
    assert "search" in skill["tags"]


def test_create_search_app_port_flows_into_card():
    client = TestClient(create_search_app(searcher=TavilySearcher(FakeTavilyClient()), port=1234))
    body = client.get("/.well-known/agent-card.json").json()
    assert body["supportedInterfaces"][0]["url"].endswith(":1234")

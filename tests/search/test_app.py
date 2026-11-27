from fastapi.testclient import TestClient

from a2apoc.search.app import create_search_app
from a2apoc.search.tavily_client import TavilySearcher


def _app(fake_tavily_client):
    return create_search_app(
        searcher=TavilySearcher(fake_tavily_client(response={"results": []}))
    )


def test_agent_card_route_serves_card(fake_tavily_client):
    client = TestClient(_app(fake_tavily_client))
    response = client.get("/.well-known/agent-card.json")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "A2A PoC Search Agent"
    assert body["capabilities"]["streaming"] is False
    skill = body["skills"][0]
    assert skill["id"] == "web_search"
    assert "search" in skill["tags"]


def test_create_search_app_port_flows_into_card(fake_tavily_client):
    client = TestClient(
        create_search_app(
            searcher=TavilySearcher(fake_tavily_client(response={"results": []})),
            port=1234,
        )
    )
    body = client.get("/.well-known/agent-card.json").json()
    assert body["supportedInterfaces"][0]["url"].endswith(":1234")

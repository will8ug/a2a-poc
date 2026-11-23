"""Tests for the host FastAPI app's agent card route."""

from fastapi.testclient import TestClient

from a2a_poc.host.app import create_host_app
from a2a_poc.host.decision import Decision

CHAT_URL = "http://chat.test"
SEARCH_URL = "http://search.test"


async def _fake_decider(user_text: str):
    return Decision(needs_search=False, query="")


def _app():
    return create_host_app(_fake_decider, CHAT_URL, SEARCH_URL)


def test_agent_card_route_serves_card():
    client = TestClient(_app())
    response = client.get("/.well-known/agent-card.json")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "A2A PoC Host"
    skill = body["skills"][0]
    assert skill["id"] == "orchestrate"
    assert skill["name"] == "Orchestration"
    assert "orchestration" in skill["tags"]
    assert "delegates to a search agent" in skill["description"]


def test_host_card_advertises_streaming_and_jsonrpc():
    body = TestClient(_app()).get("/.well-known/agent-card.json").json()
    assert body["capabilities"]["streaming"] is True
    assert body["supportedInterfaces"][0]["protocolBinding"] == "JSONRPC"


def test_create_host_app_port_flows_into_card():
    app = create_host_app(_fake_decider, CHAT_URL, SEARCH_URL, port=1234)
    body = TestClient(app).get("/.well-known/agent-card.json").json()
    assert body["supportedInterfaces"][0]["url"].endswith(":1234")

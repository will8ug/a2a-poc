from fastapi.testclient import TestClient

from a2a_poc.server.config import Config
from a2a_poc.server.app import create_app


def _app():
    return create_app(
        config=Config(api_key="dummy", base_url="http://dummy/v1", model="dummy")
    )


def test_agent_card_route_serves_card():
    client = TestClient(_app())
    response = client.get("/.well-known/agent-card.json")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "A2A PoC Chat Agent"
    assert body["capabilities"]["streaming"] is True


def test_create_app_port_flows_into_card():
    client = TestClient(
        create_app(
            config=Config(
                api_key="dummy", base_url="http://dummy/v1", model="dummy"
            ),
            port=1234,
        )
    )
    body = client.get("/.well-known/agent-card.json").json()
    assert body["supportedInterfaces"][0]["url"].endswith(":1234")

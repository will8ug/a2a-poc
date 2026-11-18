from google.protobuf.json_format import MessageToDict

from a2a_poc.card import build_agent_card

BASE_URL = "http://127.0.0.1:9999"


def test_build_agent_card_shape():
    card = build_agent_card(BASE_URL)
    assert card.name == "A2A PoC Chat Agent"
    assert card.capabilities.streaming is True
    interfaces = card.supported_interfaces
    assert len(interfaces) == 1
    assert interfaces[0].url == BASE_URL
    assert "JSONRPC" in str(interfaces[0].protocol_binding).upper()
    assert card.skills and card.skills[0].id == "chat"
    # Protobuf equivalent of pydantic's ``model_dump(exclude_none=True)``:
    # a dict of only the set fields.
    data = MessageToDict(card, preserving_proto_field_name=True)
    assert data["name"] == "A2A PoC Chat Agent"

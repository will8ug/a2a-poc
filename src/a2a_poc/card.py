"""Build the A2A AgentCard advertised by the PoC agent."""

from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill


def build_agent_card(base_url: str) -> AgentCard:
    """Build the agent card pointing at ``base_url``."""
    skill = AgentSkill(
        id="chat",
        name="Chat",
        description="Conversational chat: send text, get a streamed reply.",
        tags=["chat"],
        input_modes=["text/plain"],
        output_modes=["text/plain"],
    )
    capabilities = AgentCapabilities(streaming=True)
    interface = AgentInterface(
        protocol_binding="JSONRPC", url=base_url, protocol_version="1.0"
    )
    return AgentCard(
        name="A2A PoC Chat Agent",
        description="One LLM-backed chat agent exposed over A2A (proof of concept).",
        version="0.1.0",
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        capabilities=capabilities,
        supported_interfaces=[interface],
        skills=[skill],
    )

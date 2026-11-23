"""Build the A2A AgentCard advertised by the PoC host agent."""

from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill


def build_host_agent_card(base_url: str) -> AgentCard:
    """Build the host agent card pointing at ``base_url``."""
    skill = AgentSkill(
        id="orchestrate",
        name="Orchestration",
        description=(
            "Decides when web knowledge is needed, delegates to a search agent, "
            "and synthesizes the final answer via a chat agent."
        ),
        tags=["orchestration"],
        input_modes=["text/plain"],
        output_modes=["text/plain"],
    )
    capabilities = AgentCapabilities(streaming=True)
    interface = AgentInterface(
        protocol_binding="JSONRPC", url=base_url, protocol_version="1.0"
    )
    return AgentCard(
        name="A2A PoC Host",
        description=(
            "Multi-agent host over A2A: routes each question through a search "
            "agent and a chat agent (proof of concept)."
        ),
        version="0.1.0",
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        capabilities=capabilities,
        supported_interfaces=[interface],
        skills=[skill],
    )

"""Build the A2A AgentCard advertised by the PoC search agent."""

from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill


def build_search_agent_card(base_url: str) -> AgentCard:
    """Build the search agent card pointing at ``base_url``."""
    skill = AgentSkill(
        id="web_search",
        name="Web search",
        description="Searches the web (Tavily) and returns the top results as text.",
        tags=["search"],
        input_modes=["text/plain"],
        output_modes=["text/plain"],
    )
    capabilities = AgentCapabilities(streaming=False)
    interface = AgentInterface(
        protocol_binding="JSONRPC", url=base_url, protocol_version="1.0"
    )
    return AgentCard(
        name="A2A PoC Search Agent",
        description="One Tavily-backed web search agent exposed over A2A (proof of concept).",
        version="0.1.0",
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        capabilities=capabilities,
        supported_interfaces=[interface],
        skills=[skill],
    )

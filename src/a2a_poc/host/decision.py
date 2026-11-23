"""Route user messages: decide whether a web search is needed, and with what query."""

from dataclasses import dataclass

from a2a_poc.server.agent import ChatAgent

DECIDER_SYSTEM_PROMPT = (
    "You are a routing assistant. Decide whether answering the user's message "
    "requires web knowledge you do not have. Reply with exactly one line and "
    "nothing else: 'SEARCH: <refined search query>' if a web search would help, "
    "or 'NO_SEARCH' if the message can be answered directly."
)


@dataclass(frozen=True)
class Decision:
    """The routing outcome for one user message."""

    needs_search: bool
    query: str


async def decide_with(agent: ChatAgent, user_text: str) -> Decision:
    """Ask ``agent`` to route ``user_text`` and parse its one-line reply.

    The parse is lenient: a case-insensitive ``search:`` prefix routes to
    search with the remainder (stripped) as the query; anything else —
    ``NO_SEARCH`` or malformed output — answers directly. Protocol or
    transport errors from the agent propagate to the caller.
    """
    reply = ""
    async for delta in agent.stream_reply(user_text):
        reply += delta
    line = reply.strip()
    if line.lower().startswith("search:"):
        return Decision(needs_search=True, query=line[len("search:"):].strip())
    return Decision(needs_search=False, query="")

"""Streamlit chat UI for the A2A PoC client: chat with the agent in a browser.

Streamlit executes this script top to bottom on ``streamlit run``, so the
rendering code below runs unconditionally; ``main`` exists only for the
``a2a-poc-ui`` console script and bootstraps Streamlit on this file. The UI
is a pure frontend: it consumes ``a2apoc.client.core.stream_reply`` and
translates its events (and errors) into Streamlit elements.
"""

import sys
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import streamlit as st

from a2a.client import A2AClientError
from a2a.types import TaskState

from a2apoc.client.core import (
    DEFAULT_BASE_URL,
    Delta,
    Status,
    stream_reply,
)


class _StatusHolder:
    """Mutable box capturing the last ``Status`` event yielded by a stream."""

    def __init__(self) -> None:
        self.status: Status | None = None


def status_info_text(status: Status) -> str | None:
    """Return the message to show with ``st.info`` for a mid-stream status.

    Non-failure statuses that carry a message (e.g. the host agent's
    phase narration while delegating to sub-agents) render as an in-stream
    info note. A FAILED status returns None: the failure reason goes
    through the post-stream ``st.error`` path instead.
    """
    if status.message is None or status.state == TaskState.TASK_STATE_FAILED:
        return None
    return status.message


async def _reply_text_stream(
    events: AsyncIterator[Delta | Status], holder: _StatusHolder
) -> AsyncIterator[str]:
    """Adapt ``stream_reply`` events for ``st.write_stream``.

    Yields only the ``Delta`` text chunks (so the reply streams as it
    arrives) while recording the last ``Status`` into ``holder`` and
    rendering each render-worthy status as an ``st.info`` note before the
    next chunk is yielded.
    """
    async for event in events:
        if isinstance(event, Delta):
            yield event.text
        elif isinstance(event, Status):
            holder.status = event
            info_text = status_info_text(event)
            if info_text is not None:
                st.info(info_text)


st.set_page_config(page_title="A2A PoC Chat", page_icon="🤖")
st.title("A2A PoC Chat")

base_url = st.sidebar.text_input("Agent base URL", value=DEFAULT_BASE_URL)

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])

if prompt := st.chat_input("Message the agent"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)
    holder = _StatusHolder()
    with st.chat_message("assistant"):
        try:
            reply = st.write_stream(
                _reply_text_stream(stream_reply(base_url, prompt), holder)
            )
        except (httpx.HTTPError, httpx.InvalidURL, A2AClientError) as exc:
            st.error(f"Cannot reach the A2A agent at {base_url} ({exc})")
        else:
            if reply:
                st.session_state.messages.append(
                    {"role": "assistant", "content": reply}
                )
            status = holder.status
            if status is not None and status.state == TaskState.TASK_STATE_FAILED:
                st.error(status.message or "The agent task failed.")


def main() -> None:
    """Run the Streamlit app on this script (console entry ``a2a-poc-ui``)."""
    from streamlit.web import cli as stcli

    sys.argv = [
        "streamlit",
        "run",
        str(Path(__file__).resolve()),
        "--server.address",
        "127.0.0.1",
        *sys.argv[1:],
    ]
    sys.exit(stcli.main())

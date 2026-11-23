"""Offline AppTest coverage for the Streamlit chat UI.

The tests only exercise rendering — no chat submission, so no network.
They pin the session-state contract: history is a list of
``{"role": str, "content": str}`` dicts under ``st.session_state["messages"]``.
"""

from pathlib import Path

from a2a.types import TaskState
from streamlit.testing.v1 import AppTest

from a2a_poc.client.core import Status
from a2a_poc.client.ui import status_info_text

UI_SCRIPT = (
    Path(__file__).resolve().parents[2] / "src" / "a2a_poc" / "client" / "ui.py"
)


def test_status_info_text():
    """Mid-stream statuses with a message render; FAILED stays st.error's job."""
    assert (
        status_info_text(
            Status(
                state=TaskState.TASK_STATE_WORKING,
                message="Searching the web…",
            )
        )
        == "Searching the web…"
    )
    assert (
        status_info_text(Status(state=TaskState.TASK_STATE_WORKING, message=None))
        is None
    )
    assert (
        status_info_text(
            Status(
                state=TaskState.TASK_STATE_FAILED,
                message="LLM call failed: boom",
            )
        )
        is None
    )


def test_ui_renders_chat_page():
    at = AppTest.from_file(UI_SCRIPT, default_timeout=10)
    at.run()
    assert not at.exception
    assert len(at.chat_input) == 1


def test_ui_renders_existing_history():
    at = AppTest.from_file(UI_SCRIPT, default_timeout=10)
    at.session_state["messages"] = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    at.run()
    assert not at.exception
    rendered = list(at.chat_message)
    assert [message.name for message in rendered] == ["user", "assistant"]
    assert [md.value for md in rendered[0].markdown] == ["hi"]
    assert [md.value for md in rendered[1].markdown] == ["hello"]

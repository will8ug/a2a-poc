import logging
from types import SimpleNamespace

from a2a.helpers import new_text_message
from a2a.types import Role, TaskState

from a2apoc.chat.executor import ChatAgentExecutor


class FakeAgent:
    def __init__(self, chunks=None, error=None):
        self._chunks = chunks or []
        self._error = error

    async def stream_reply(self, user_text: str):
        for c in self._chunks:
            yield c
        if self._error:
            raise self._error


class FakeEventQueue:
    def __init__(self):
        self.events = []

    async def enqueue_event(self, event):
        self.events.append(event)


def _context(text: str):
    return SimpleNamespace(message=new_text_message(text, role=Role.ROLE_USER), current_task=None)


def _artifact_text(events):
    parts = []
    for e in events:
        artifact = getattr(e, "artifact", None)
        if artifact is not None:
            parts.extend(p.text for p in artifact.parts)
    return "".join(parts)


def _final_state(events):
    states = [e.status.state for e in events if hasattr(e, "status")]
    return states[-1]


async def test_executor_streams_deltas_and_completes():
    queue = FakeEventQueue()
    executor = ChatAgentExecutor(agent=FakeAgent(chunks=["Hel", "lo"]))
    await executor.execute(_context("hi"), queue)
    assert _final_state(queue.events) == TaskState.TASK_STATE_COMPLETED
    assert _artifact_text(queue.events) == "Hello"


async def test_executor_streams_cjk_text():
    queue = FakeEventQueue()
    executor = ChatAgentExecutor(agent=FakeAgent(chunks=["你好", "，A2A"]))
    await executor.execute(_context("用中文打个招呼"), queue)
    assert _final_state(queue.events) == TaskState.TASK_STATE_COMPLETED
    assert _artifact_text(queue.events) == "你好，A2A"


async def test_llm_failure_marks_task_failed():
    queue = FakeEventQueue()
    executor = ChatAgentExecutor(agent=FakeAgent(error=RuntimeError("boom: 401 Unauthorized")))
    await executor.execute(_context("hi"), queue)
    assert _final_state(queue.events) == TaskState.TASK_STATE_FAILED
    assert _artifact_text(queue.events) == ""


async def test_llm_failure_flushes_held_delta_before_failed():
    queue = FakeEventQueue()
    executor = ChatAgentExecutor(
        agent=FakeAgent(chunks=["partial-"], error=RuntimeError("boom"))
    )
    await executor.execute(_context("hi"), queue)
    assert _final_state(queue.events) == TaskState.TASK_STATE_FAILED
    assert _artifact_text(queue.events) == "partial-"


async def test_llm_failure_logs_exception_server_side(caplog):
    queue = FakeEventQueue()
    executor = ChatAgentExecutor(agent=FakeAgent(error=RuntimeError("boom")))
    with caplog.at_level(logging.ERROR, logger="a2apoc.chat.executor"):
        await executor.execute(_context("hi"), queue)
    assert any(
        r.name == "a2apoc.chat.executor"
        and r.levelno == logging.ERROR
        and "LLM call failed" in r.getMessage()
        for r in caplog.records
    )

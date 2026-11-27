import logging

from a2a.types import TaskState

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


async def test_executor_streams_deltas_and_completes(
    queue, _context, _final_state, _artifact_text
):
    executor = ChatAgentExecutor(agent=FakeAgent(chunks=["Hel", "lo"]))
    await executor.execute(_context("hi"), queue)
    assert _final_state(queue.events) == TaskState.TASK_STATE_COMPLETED
    assert _artifact_text(queue.events) == "Hello"


async def test_executor_streams_cjk_text(queue, _context, _final_state, _artifact_text):
    executor = ChatAgentExecutor(agent=FakeAgent(chunks=["你好", "，A2A"]))
    await executor.execute(_context("用中文打个招呼"), queue)
    assert _final_state(queue.events) == TaskState.TASK_STATE_COMPLETED
    assert _artifact_text(queue.events) == "你好，A2A"


async def test_llm_failure_marks_task_failed(
    queue, _context, _final_state, _artifact_text
):
    executor = ChatAgentExecutor(agent=FakeAgent(error=RuntimeError("boom: 401 Unauthorized")))
    await executor.execute(_context("hi"), queue)
    assert _final_state(queue.events) == TaskState.TASK_STATE_FAILED
    assert _artifact_text(queue.events) == ""


async def test_llm_failure_flushes_held_delta_before_failed(
    queue, _context, _final_state, _artifact_text
):
    executor = ChatAgentExecutor(
        agent=FakeAgent(chunks=["partial-"], error=RuntimeError("boom"))
    )
    await executor.execute(_context("hi"), queue)
    assert _final_state(queue.events) == TaskState.TASK_STATE_FAILED
    assert _artifact_text(queue.events) == "partial-"


async def test_llm_failure_logs_exception_server_side(queue, _context, caplog):
    executor = ChatAgentExecutor(agent=FakeAgent(error=RuntimeError("boom")))
    with caplog.at_level(logging.ERROR, logger="a2apoc.chat.executor"):
        await executor.execute(_context("hi"), queue)
    assert any(
        r.name == "a2apoc.chat.executor"
        and r.levelno == logging.ERROR
        and "LLM call failed" in r.getMessage()
        for r in caplog.records
    )

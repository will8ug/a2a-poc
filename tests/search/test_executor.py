import logging

from a2a.types import TaskState

from a2apoc.search.executor import SearchAgentExecutor


class FakeSearcher:
    def __init__(self, text=None, error=None):
        self._text = text
        self._error = error
        self.queries = []

    async def search(self, query: str) -> str:
        self.queries.append(query)
        if self._error:
            raise self._error
        return self._text


def _artifact_events(events):
    return [e for e in events if getattr(e, "artifact", None) is not None]


async def test_executor_emits_single_artifact_and_completes(
    queue, _context, _final_state, _artifact_text
):
    searcher = FakeSearcher(text="A2A Protocol\nhttps://a2a.example\noverview")
    executor = SearchAgentExecutor(searcher=searcher)
    await executor.execute(_context("search: a2a"), queue)
    assert searcher.queries == ["search: a2a"]
    assert _final_state(queue.events) == TaskState.TASK_STATE_COMPLETED
    artifacts = _artifact_events(queue.events)
    assert len(artifacts) == 1
    assert artifacts[0].artifact.name == "search_results"
    assert artifacts[0].last_chunk is True
    assert _artifact_text(queue.events) == (
        "A2A Protocol\nhttps://a2a.example\noverview"
    )


async def test_searcher_failure_marks_task_failed(queue, _context, _final_state):
    searcher = FakeSearcher(error=RuntimeError("boom: 401 Unauthorized"))
    executor = SearchAgentExecutor(searcher=searcher)
    await executor.execute(_context("hi"), queue)
    assert _final_state(queue.events) == TaskState.TASK_STATE_FAILED
    assert _artifact_events(queue.events) == []


async def test_searcher_failure_logs_exception_server_side(queue, _context, caplog):
    searcher = FakeSearcher(error=RuntimeError("boom"))
    executor = SearchAgentExecutor(searcher=searcher)
    with caplog.at_level(logging.ERROR, logger="a2apoc.search.executor"):
        await executor.execute(_context("hi"), queue)
    assert any(
        r.name == "a2apoc.search.executor"
        and r.levelno == logging.ERROR
        and "Search failed" in r.getMessage()
        for r in caplog.records
    )

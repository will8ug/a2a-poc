import logging
from types import SimpleNamespace

from a2a.helpers import new_text_message
from a2a.types import Role, TaskState

from a2a_poc.search.executor import SearchAgentExecutor


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


class FakeEventQueue:
    def __init__(self):
        self.events = []

    async def enqueue_event(self, event):
        self.events.append(event)


def _context(text: str):
    return SimpleNamespace(
        message=new_text_message(text, role=Role.ROLE_USER), current_task=None
    )


def _artifact_events(events):
    return [e for e in events if getattr(e, "artifact", None) is not None]


def _artifact_text(events):
    parts = []
    for e in _artifact_events(events):
        parts.extend(p.text for p in e.artifact.parts)
    return "".join(parts)


def _final_state(events):
    states = [e.status.state for e in events if hasattr(e, "status")]
    return states[-1]


async def test_executor_emits_single_artifact_and_completes():
    queue = FakeEventQueue()
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


async def test_searcher_failure_marks_task_failed():
    queue = FakeEventQueue()
    searcher = FakeSearcher(error=RuntimeError("boom: 401 Unauthorized"))
    executor = SearchAgentExecutor(searcher=searcher)
    await executor.execute(_context("hi"), queue)
    assert _final_state(queue.events) == TaskState.TASK_STATE_FAILED
    assert _artifact_events(queue.events) == []


async def test_searcher_failure_logs_exception_server_side(caplog):
    queue = FakeEventQueue()
    searcher = FakeSearcher(error=RuntimeError("boom"))
    executor = SearchAgentExecutor(searcher=searcher)
    with caplog.at_level(logging.ERROR, logger="a2a_poc.search.executor"):
        await executor.execute(_context("hi"), queue)
    assert any(
        r.name == "a2a_poc.search.executor"
        and r.levelno == logging.ERROR
        and "Search failed" in r.getMessage()
        for r in caplog.records
    )

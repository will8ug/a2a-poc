"""Tests for the host's decide → search → synthesize orchestration."""

from types import SimpleNamespace

from a2a.helpers import new_text_message
from a2a.types import Role, TaskState

from a2a_poc.client.core import Delta, Status
from a2a_poc.host.decision import Decision
from a2a_poc.host.executor import HostAgentExecutor

CHAT_URL = "http://chat.test"
SEARCH_URL = "http://search.test"


class FakeDecider:
    """Callable decider stand-in: returns a scripted Decision or raises."""

    def __init__(self, decision=None, error=None):
        self._decision = decision
        self._error = error
        self.received = []

    async def __call__(self, user_text):
        self.received.append(user_text)
        if self._error is not None:
            raise self._error
        return self._decision


class FakeStream:
    """``stream_reply`` stand-in dispatching scripted events by URL.

    ``script`` maps a URL to a list of ``Delta``/``Status`` events; an
    ``Exception`` in the list is raised at that point in the stream. Each
    call is recorded as ``(url, text)``.
    """

    def __init__(self):
        self.calls = []
        self._scripts = {}

    def script(self, url, events):
        self._scripts[url] = list(events)
        return self

    def __call__(self, base_url, user_text, httpx_client=None, client_factory=None):
        self.calls.append((base_url, user_text))
        return self._replay(base_url)

    async def _replay(self, base_url):
        for event in self._scripts[base_url]:
            if isinstance(event, Exception):
                raise event
            yield event


class FakeEventQueue:
    def __init__(self):
        self.events = []

    async def enqueue_event(self, event):
        self.events.append(event)


def _context(text: str):
    return SimpleNamespace(
        message=new_text_message(text, role=Role.ROLE_USER), current_task=None
    )


def _completed():
    return Status(state=TaskState.TASK_STATE_COMPLETED, message=None)


def _failed(message: str):
    return Status(state=TaskState.TASK_STATE_FAILED, message=message)


def _working():
    return Status(state=TaskState.TASK_STATE_WORKING, message=None)


def _artifact_text(events):
    parts = []
    for e in events:
        artifact = getattr(e, "artifact", None)
        if artifact is not None:
            parts.extend(p.text for p in artifact.parts)
    return "".join(parts)


def _status_states(events):
    return [e.status.state for e in events if hasattr(e, "status")]


def _final_state(events):
    return _status_states(events)[-1]


def _status_texts(events):
    texts = []
    for e in events:
        status = getattr(e, "status", None)
        if status is None or not status.HasField("message"):
            continue
        texts.append("\n".join(p.text for p in status.message.parts if p.text))
    return texts


def _no_search():
    return Decision(needs_search=False, query="")


# Scenario 1: no search needed — relay the chat agent's streamed reply.


async def test_no_search_relays_chat_reply_as_artifacts():
    queue = FakeEventQueue()
    stream = FakeStream().script(
        CHAT_URL, [_working(), Delta("Hel"), Delta("lo"), _completed()]
    )
    executor = HostAgentExecutor(
        FakeDecider(_no_search()), CHAT_URL, SEARCH_URL, stream=stream
    )

    await executor.execute(_context("hi"), queue)

    # Only the chat agent is called, with the raw user text.
    assert stream.calls == [(CHAT_URL, "hi")]
    assert TaskState.TASK_STATE_WORKING in _status_states(queue.events)
    assert any(
        "Synthesizing the answer" in text for text in _status_texts(queue.events)
    )
    assert _final_state(queue.events) == TaskState.TASK_STATE_COMPLETED
    assert _artifact_text(queue.events) == "Hello"


# Scenario 2: search needed — synthesize from question + results.


async def test_search_path_composes_question_and_results():
    queue = FakeEventQueue()
    stream = FakeStream()
    stream.script(
        SEARCH_URL,
        [_working(), Delta("A2A is an agent-to-agent protocol."), _completed()],
    )
    stream.script(CHAT_URL, [_working(), Delta("syn"), Delta("thesized"), _completed()])
    executor = HostAgentExecutor(
        FakeDecider(Decision(needs_search=True, query="a2a protocol")),
        CHAT_URL,
        SEARCH_URL,
        stream=stream,
    )

    await executor.execute(_context("what is a2a?"), queue)

    assert stream.calls[0] == (SEARCH_URL, "a2a protocol")
    chat_url, chat_prompt = stream.calls[1]
    assert chat_url == CHAT_URL
    assert "what is a2a?" in chat_prompt
    assert "A2A is an agent-to-agent protocol." in chat_prompt
    assert any("Searching the web" in text for text in _status_texts(queue.events))
    assert any(
        "Synthesizing the answer" in text for text in _status_texts(queue.events)
    )
    assert _final_state(queue.events) == TaskState.TASK_STATE_COMPLETED
    # Only the synthesized chat reply becomes a host artifact.
    assert _artifact_text(queue.events) == "synthesized"


# Scenario 3: the search stream raises — degrade to a direct answer.


async def test_search_error_degrades_to_direct_answer():
    queue = FakeEventQueue()
    stream = FakeStream()
    stream.script(SEARCH_URL, [RuntimeError("connection refused")])
    stream.script(CHAT_URL, [_working(), Delta("direct answer"), _completed()])
    executor = HostAgentExecutor(
        FakeDecider(Decision(needs_search=True, query="q")),
        CHAT_URL,
        SEARCH_URL,
        stream=stream,
    )

    await executor.execute(_context("what time is it?"), queue)

    # Chat is still called, with the raw user text (no results to synthesize).
    assert stream.calls[-1] == (CHAT_URL, "what time is it?")
    assert _final_state(queue.events) == TaskState.TASK_STATE_COMPLETED
    assert _artifact_text(queue.events) == "direct answer"
    assert any("Search unavailable" in text for text in _status_texts(queue.events))
    assert any("answering without it" in text for text in _status_texts(queue.events))


# Scenario 4: the search task FAILED — degrade to a direct answer.


async def test_search_failed_status_degrades_to_direct_answer():
    queue = FakeEventQueue()
    stream = FakeStream()
    stream.script(SEARCH_URL, [Delta("partial results"), _failed("Tavily API error")])
    stream.script(CHAT_URL, [_working(), Delta("direct answer"), _completed()])
    executor = HostAgentExecutor(
        FakeDecider(Decision(needs_search=True, query="q")),
        CHAT_URL,
        SEARCH_URL,
        stream=stream,
    )

    await executor.execute(_context("what time is it?"), queue)

    chat_url, chat_prompt = stream.calls[-1]
    assert chat_url == CHAT_URL
    # The failed search's partial results are dropped: raw user text only.
    assert chat_prompt == "what time is it?"
    assert "partial results" not in chat_prompt
    assert _final_state(queue.events) == TaskState.TASK_STATE_COMPLETED
    assert _artifact_text(queue.events) == "direct answer"
    assert any("Search unavailable" in text for text in _status_texts(queue.events))
    assert any("answering without it" in text for text in _status_texts(queue.events))


# Scenario 5: the decider raises — fall back to the no-search path.


async def test_decider_error_falls_back_to_direct_answer():
    queue = FakeEventQueue()
    stream = FakeStream().script(
        CHAT_URL, [_working(), Delta("direct answer"), _completed()]
    )
    executor = HostAgentExecutor(
        FakeDecider(error=RuntimeError("LLM 500")),
        CHAT_URL,
        SEARCH_URL,
        stream=stream,
    )

    await executor.execute(_context("hi"), queue)

    assert stream.calls == [(CHAT_URL, "hi")]
    assert _final_state(queue.events) == TaskState.TASK_STATE_COMPLETED
    assert _artifact_text(queue.events) == "direct answer"
    assert any("Couldn't decide" in text for text in _status_texts(queue.events))
    assert any("answering directly" in text for text in _status_texts(queue.events))


# Scenario 6: the chat task FAILED — the host task fails with the wire reason.


async def test_chat_failed_fails_host_task_with_wire_reason():
    queue = FakeEventQueue()
    stream = FakeStream().script(
        CHAT_URL,
        [_working(), Delta("par"), Delta("tial"), _failed("LLM call failed: boom")],
    )
    executor = HostAgentExecutor(
        FakeDecider(_no_search()), CHAT_URL, SEARCH_URL, stream=stream
    )

    await executor.execute(_context("hi"), queue)

    assert _final_state(queue.events) == TaskState.TASK_STATE_FAILED
    assert TaskState.TASK_STATE_COMPLETED not in _status_states(queue.events)
    assert _status_texts(queue.events)[-1] == "LLM call failed: boom"

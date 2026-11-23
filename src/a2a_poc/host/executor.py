"""A2A host executor: decide → search → synthesize, with graceful degradation.

The host owns the task lifecycle and talks to the search and chat agents
over the wire via the client core's ``stream_reply`` (injectable as
``stream`` so tests can script the remote agents). Only the chat agent's
reply becomes the host's streamed artifact; search results feed the chat
prompt instead.
"""

import logging

from a2a.helpers import (
    get_message_text,
    new_task_from_user_message,
    new_text_message,
)
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import TaskState

from a2a_poc.client.core import Delta, Status, stream_reply
from a2a_poc.host.decision import Decision

# Private by naming convention only: reusing the server executor's
# look-ahead artifact stream keeps the artifact chunking protocol
# knowledge in exactly one place (disclosed in the task report).
from a2a_poc.server.executor import _ReplyArtifactStream

logger = logging.getLogger(__name__)

_SEARCH_NARRATION = "Searching the web…"
_SYNTHESIS_NARRATION = "Synthesizing the answer…"


class HostAgentExecutor(AgentExecutor):
    """Runs the decide → search → synthesize pipeline for one A2A request.

    Failures degrade rather than abort: a failed decider or search agent
    falls back to answering directly (with a status note saying so), and
    only a failed chat relay marks the host task FAILED. The chat reply
    is relayed as the host's streamed artifact using the same look-ahead
    artifact stream as the server executor.
    """

    def __init__(self, decider, chat_url: str, search_url: str, stream=stream_reply):
        self._decider = decider
        self._chat_url = chat_url
        self._search_url = search_url
        self._stream = stream

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task = context.current_task
        if task is None:
            task = new_task_from_user_message(context.message)
            await event_queue.enqueue_event(task)

        updater = TaskUpdater(
            event_queue=event_queue,
            task_id=task.id,
            context_id=task.context_id,
        )
        await updater.update_status(state=TaskState.TASK_STATE_WORKING)
        user_text = get_message_text(context.message)

        decision = await self._decide(updater, user_text)
        results_text = (
            await self._search(updater, decision) if decision.needs_search else None
        )
        prompt = _compose_prompt(user_text, results_text)
        await self._relay(updater, prompt)

    async def _decide(self, updater: TaskUpdater, user_text: str) -> Decision:
        """Route the message; on any failure, answer directly instead."""
        try:
            return await self._decider(user_text)
        except Exception as exc:
            logger.warning("Decider failed; answering directly", exc_info=True)
            await updater.update_status(
                state=TaskState.TASK_STATE_WORKING,
                message=new_text_message(
                    f"Couldn't decide ({exc}): answering directly"
                ),
            )
            return Decision(needs_search=False, query="")

    async def _search(self, updater: TaskUpdater, decision: Decision) -> str | None:
        """Query the search agent; return its joined text, or None on failure.

        Emits a searching narration first. If the stream raises or its
        final status is FAILED, the host degrades: a status note is
        emitted and the results are dropped.
        """
        await updater.update_status(
            state=TaskState.TASK_STATE_WORKING,
            message=new_text_message(_SEARCH_NARRATION),
        )
        chunks: list[str] = []
        final_status: Status | None = None
        try:
            async for event in self._stream(self._search_url, decision.query):
                if isinstance(event, Delta):
                    chunks.append(event.text)
                else:
                    final_status = event
        except Exception as exc:
            await self._degrade_to_direct(updater, reason=str(exc))
            return None
        if _failed_status(final_status):
            await self._degrade_to_direct(
                updater, reason=final_status.message or "search agent task failed"
            )
            return None
        return "".join(chunks)

    async def _degrade_to_direct(self, updater: TaskUpdater, reason: str) -> None:
        """Note that search failed and the answer will not use it."""
        await updater.update_status(
            state=TaskState.TASK_STATE_WORKING,
            message=new_text_message(
                f"Search unavailable ({reason}): answering without it"
            ),
        )

    async def _relay(self, updater: TaskUpdater, prompt: str) -> None:
        """Stream the chat agent's reply as the host task's artifact.

        Emits a synthesizing narration first (the chat agent synthesizes
        the final answer whether or not search results were used).
        """
        await updater.update_status(
            state=TaskState.TASK_STATE_WORKING,
            message=new_text_message(_SYNTHESIS_NARRATION),
        )
        reply = _ReplyArtifactStream()
        final_status: Status | None = None
        try:
            async for event in self._stream(self._chat_url, prompt):
                if isinstance(event, Delta):
                    await reply.push(updater, event.text)
                else:
                    final_status = event
        except Exception as exc:
            logger.exception("Chat relay failed")
            await reply.flush_partial(updater)
            await updater.update_status(
                state=TaskState.TASK_STATE_FAILED,
                message=new_text_message(f"Chat relay failed: {exc}"),
            )
            return
        if _failed_status(final_status):
            reason = final_status.message or "chat agent task failed"
            await reply.flush_partial(updater)
            await updater.update_status(
                state=TaskState.TASK_STATE_FAILED,
                message=new_text_message(reason),
            )
            return
        await reply.finish(updater)
        await updater.update_status(state=TaskState.TASK_STATE_COMPLETED)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """No-op: the pipeline is short-lived and cannot be cancelled."""


def _compose_prompt(user_text: str, results_text: str | None) -> str:
    """Build the chat prompt: raw question, or question plus search results."""
    if results_text is None:
        return user_text
    return (
        "Answer the user's question using the web search results below.\n\n"
        f"Question: {user_text}\n\n"
        f"Web search results:\n{results_text}"
    )


def _failed_status(status: Status | None) -> bool:
    """Whether ``status`` is a non-None FAILED terminal status."""
    return status is not None and status.state == TaskState.TASK_STATE_FAILED

"""A2A agent executor bridging ChatAgent streams to task lifecycle events."""

import logging
import uuid

from a2a.helpers import (
    get_message_text,
    new_task_from_user_message,
    new_text_message,
    new_text_part,
)
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import TaskState

from a2a_poc.agent import ChatAgent

logger = logging.getLogger(__name__)

_REPLY_ARTIFACT_NAME = "reply"


class _ReplyArtifactStream:
    """Streams one reply artifact through a one-delta look-ahead buffer.

    All chunks share one artifact id: the first chunk creates the
    artifact, later ones append to it, and the final one is flagged as
    the last chunk. Each delta is held until the next one arrives (or
    the stream ends) so the final update can be marked ``last_chunk``.
    """

    def __init__(self) -> None:
        self._artifact_id = str(uuid.uuid4())
        self._append = False
        self._pending: str | None = None

    async def push(self, updater: TaskUpdater, delta: str) -> None:
        """Hold ``delta`` back, emitting the previously held one, if any."""
        if self._pending is not None:
            await self._emit(updater, self._pending)
        self._pending = delta

    async def finish(self, updater: TaskUpdater) -> None:
        """Emit the held delta, if any, as the artifact's final chunk."""
        if self._pending is not None:
            await self._emit(updater, self._pending, last_chunk=True)
            self._pending = None

    async def flush_partial(self, updater: TaskUpdater) -> None:
        """Emit the held delta, if any, after a mid-stream failure.

        The emission is never marked ``last_chunk``: the reply was cut
        short, so consumers must not treat the artifact as complete.
        """
        if self._pending is not None:
            await self._emit(updater, self._pending)

    async def _emit(
        self, updater: TaskUpdater, text: str, last_chunk: bool | None = None
    ) -> None:
        await updater.add_artifact(
            [new_text_part(text)],
            artifact_id=self._artifact_id,
            name=_REPLY_ARTIFACT_NAME,
            append=self._append,
            last_chunk=last_chunk,
        )
        self._append = True


class ChatAgentExecutor(AgentExecutor):
    """Runs a ChatAgent to fulfil A2A requests.

    Streams the agent's reply as artifact-update events on the request's
    event queue, wrapped in the standard task lifecycle: WORKING on start,
    COMPLETED on success, FAILED if the agent's stream raises — flushing
    any partially streamed reply first and logging the failure with its
    traceback server-side.
    """

    def __init__(self, agent: ChatAgent):
        self._agent = agent

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
        reply = _ReplyArtifactStream()
        try:
            async for delta in self._agent.stream_reply(
                get_message_text(context.message)
            ):
                await reply.push(updater, delta)
            await reply.finish(updater)
        except Exception as exc:
            logger.exception("LLM call failed")
            await reply.flush_partial(updater)
            await updater.update_status(
                state=TaskState.TASK_STATE_FAILED,
                message=new_text_message(f"LLM call failed: {exc}"),
            )
            return
        await updater.update_status(state=TaskState.TASK_STATE_COMPLETED)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """No-op: streaming replies are short-lived and cannot be cancelled."""

"""A2A agent executor bridging ChatAgent streams to task lifecycle events."""

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

_REPLY_ARTIFACT_NAME = "reply"


class ChatAgentExecutor(AgentExecutor):
    """Runs a ChatAgent to fulfil A2A requests.

    Streams the agent's reply as artifact-update events on the request's
    event queue, wrapped in the standard task lifecycle: WORKING on start,
    COMPLETED on success, FAILED if the agent's stream raises.
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
        try:
            await self._stream_reply_as_artifacts(
                updater, get_message_text(context.message)
            )
        except Exception as exc:
            await updater.update_status(
                state=TaskState.TASK_STATE_FAILED,
                message=new_text_message(f"LLM call failed: {exc}"),
            )
            return
        await updater.update_status(state=TaskState.TASK_STATE_COMPLETED)

    async def _stream_reply_as_artifacts(
        self, updater: TaskUpdater, user_text: str
    ) -> None:
        """Emit one artifact update per delta of the agent's streamed reply.

        All chunks share one artifact id: the first chunk creates the
        artifact, later ones append to it, and the final one is flagged as
        the last chunk. Each delta is held until the next one arrives (or
        the stream ends) so the final update can be marked ``last_chunk``.
        """
        artifact_id = str(uuid.uuid4())
        append = False
        pending = None
        async for delta in self._agent.stream_reply(user_text):
            if pending is not None:
                await updater.add_artifact(
                    [new_text_part(pending)],
                    artifact_id=artifact_id,
                    name=_REPLY_ARTIFACT_NAME,
                    append=append,
                )
                append = True
            pending = delta
        if pending is not None:
            await updater.add_artifact(
                [new_text_part(pending)],
                artifact_id=artifact_id,
                name=_REPLY_ARTIFACT_NAME,
                append=append,
                last_chunk=True,
            )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """No-op: streaming replies are short-lived and cannot be cancelled."""

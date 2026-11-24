"""A2A agent executor bridging ChatAgent streams to task lifecycle events."""

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

from a2a_poc.llm import ChatAgent
from a2a_poc.wiring import ReplyArtifactStream

logger = logging.getLogger(__name__)


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
        reply = ReplyArtifactStream()
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

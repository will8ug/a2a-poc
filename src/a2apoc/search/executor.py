"""A2A agent executor bridging TavilySearcher to the task lifecycle."""

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

from a2apoc.search.tavily_client import TavilySearcher

logger = logging.getLogger(__name__)

_SEARCH_ARTIFACT_NAME = "search_results"


class SearchAgentExecutor(AgentExecutor):
    """Runs a TavilySearcher to fulfil A2A requests.

    Wraps the search in the standard task lifecycle: WORKING on start,
    one final artifact with the formatted results, COMPLETED on success,
    FAILED if the search raises — logging the failure with its traceback
    server-side.
    """

    def __init__(self, searcher: TavilySearcher):
        self._searcher = searcher

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
            results = await self._searcher.search(get_message_text(context.message))
        except Exception as exc:
            logger.exception("Search failed")
            await updater.update_status(
                state=TaskState.TASK_STATE_FAILED,
                message=new_text_message(f"Search failed: {exc}"),
            )
            return
        await updater.add_artifact(
            [new_text_part(results)],
            artifact_id=str(uuid.uuid4()),
            name=_SEARCH_ARTIFACT_NAME,
            last_chunk=True,
        )
        await updater.update_status(state=TaskState.TASK_STATE_COMPLETED)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """No-op: a single search call is short-lived and cannot be cancelled."""

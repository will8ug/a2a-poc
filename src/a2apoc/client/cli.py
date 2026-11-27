"""Streaming A2A client CLI: talk to the PoC agent server from the terminal."""

import argparse
import asyncio
import sys

import httpx
from a2a.client import A2AClientError
from a2a.types import TaskState

from a2apoc.client.core import (
    DEFAULT_BASE_URL,
    ClientFactory,
    Delta,
    Status,
    stream_reply,
)


async def run(
    base_url: str,
    user_text: str,
    httpx_client: httpx.AsyncClient | None = None,
    client_factory: ClientFactory | None = None,
) -> None:
    """Send ``user_text`` to the A2A agent at ``base_url`` and stream the reply.

    Resolves the agent card, then streams response events to stdout: artifact
    text is printed as it arrives, task-state transitions get their own line,
    status messages (e.g. the failure reason on a FAILED task) print after
    their state line, and a final state line closes the output. Exits with
    code 1 when the task ends in FAILED, and with code 1 and a stderr message
    when the agent cannot be reached. Creates and closes an HTTP client only
    when ``httpx_client`` is not supplied. ``client_factory`` overrides how
    the A2A client is built from the resolved card (a seam for tests that
    script the event stream).
    """
    last_state: int | None = None
    text_on_line = False
    try:
        async for event in stream_reply(
            base_url, user_text, httpx_client, client_factory
        ):
            if isinstance(event, Delta):
                print(event.text, end="", flush=True)
                text_on_line = True
            elif isinstance(event, Status):
                last_state = event.state
                if text_on_line:
                    print()
                    text_on_line = False
                print(TaskState.Name(event.state))
                if event.message:
                    print(event.message)
    except (httpx.HTTPError, httpx.InvalidURL, A2AClientError) as exc:
        print(
            f"error: cannot reach A2A agent at {base_url} ({exc})",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
    if text_on_line:
        print()
    if last_state is not None:
        print(f"final state: {TaskState.Name(last_state)}")
    if last_state == TaskState.TASK_STATE_FAILED:
        raise SystemExit(1)


def main(argv: list[str] | None = None) -> None:
    """Run the client (console entry point ``a2a-poc-client``)."""
    parser = argparse.ArgumentParser(
        prog="a2a-poc-client",
        description="Send a message to the A2A PoC agent and stream the reply.",
    )
    parser.add_argument("text", help="Message text to send to the agent.")
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Base URL of the A2A agent server (default: {DEFAULT_BASE_URL}).",
    )
    args = parser.parse_args(argv)
    asyncio.run(run(args.base_url, args.text))

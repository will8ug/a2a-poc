"""Streaming A2A client CLI: talk to the PoC agent server from the terminal."""

import argparse
import asyncio
import sys

import httpx

from a2a.client import A2ACardResolver, A2AClientError, Client, ClientConfig, create_client
from a2a.helpers import new_text_message
from a2a.types import Role, SendMessageRequest, TaskState

DEFAULT_BASE_URL = "http://127.0.0.1:9999"


async def run(
    base_url: str,
    user_text: str,
    httpx_client: httpx.AsyncClient | None = None,
) -> None:
    """Send ``user_text`` to the A2A agent at ``base_url`` and stream the reply.

    Resolves the agent card, then streams response events to stdout: artifact
    text is printed as it arrives, task-state transitions get their own line,
    and a final state line closes the output. Creates and closes an HTTP
    client only when ``httpx_client`` is not supplied.
    """
    owns_client = httpx_client is None
    http_client = httpx_client if httpx_client is not None else httpx.AsyncClient()
    try:
        resolver = A2ACardResolver(httpx_client=http_client, base_url=base_url)
        agent_card = await resolver.get_agent_card()
        client = await create_client(
            agent=agent_card,
            client_config=ClientConfig(streaming=True, httpx_client=http_client),
        )
        try:
            await _stream_reply(client, user_text)
        finally:
            await client.close()
    except (httpx.HTTPError, A2AClientError) as exc:
        print(
            f"error: cannot reach A2A agent at {base_url} ({exc})",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
    finally:
        if owns_client:
            await http_client.aclose()


async def _stream_reply(client: Client, user_text: str) -> None:
    """Consume the streamed response, printing artifact text and task states."""
    request = SendMessageRequest(
        message=new_text_message(user_text, role=Role.ROLE_USER)
    )
    last_state: int | None = None
    text_on_line = False
    async for event in client.send_message(request):
        if event.HasField("artifact_update"):
            for part in event.artifact_update.artifact.parts:
                if part.text:
                    print(part.text, end="", flush=True)
                    text_on_line = True
        elif event.HasField("status_update"):
            last_state = event.status_update.status.state
            if text_on_line:
                print()
                text_on_line = False
            print(TaskState.Name(last_state))
        elif event.HasField("task"):
            last_state = event.task.status.state
    if text_on_line:
        print()
    if last_state is not None:
        print(f"final state: {TaskState.Name(last_state)}")


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

"""Streaming LLM chat agent backed by an OpenAI-compatible API."""

from collections.abc import AsyncIterator

from openai import AsyncOpenAI

from a2a_poc.config import Config

SYSTEM_PROMPT = "You are a helpful AI assistant. Answer questions concisely."


class ChatAgent:
    """Streams chat completions from any OpenAI-compatible client.

    ``client`` is duck-typed: any object exposing async
    ``chat.completions.create(**kwargs)`` works (production uses
    ``openai.AsyncOpenAI``).
    """

    def __init__(self, client, model: str):
        self._client = client
        self._model = model

    async def stream_reply(self, user_text: str) -> AsyncIterator[str]:
        """Yield non-empty text deltas from a streaming chat completion."""
        stream = await self._client.chat.completions.create(
            model=self._model,
            stream=True,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ],
        )
        async for chunk in stream:
            if not chunk.choices:
                # Some OpenAI-compatible endpoints end the stream with
                # usage-only chunks that carry no choices; skip them.
                continue
            content = chunk.choices[0].delta.content
            if content:
                yield content


def build_chat_agent(config: Config) -> ChatAgent:
    """Build a ChatAgent with a real AsyncOpenAI client from Config."""
    return ChatAgent(
        client=AsyncOpenAI(base_url=config.base_url, api_key=config.api_key),
        model=config.model,
    )

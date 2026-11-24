"""Shared LLM plumbing: endpoint configuration and a streaming chat client.

``Config``/``load_config`` fail fast on the ``LLM_*`` environment
variables naming the OpenAI-compatible endpoint, and ``ChatAgent``
streams chat completions from it; ``build_chat_agent`` wires the two
together. Every agent shares this module instead of importing from
another agent.
"""

import os
from collections.abc import AsyncIterator
from dataclasses import dataclass

from dotenv import load_dotenv
from openai import AsyncOpenAI


class ConfigError(RuntimeError):
    """Raised when required configuration environment variables are missing."""


@dataclass(frozen=True)
class Config:
    api_key: str
    base_url: str
    model: str


_REQUIRED_VARS = ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL")


def load_config(env_file: str | None = ".env") -> Config:
    """Load configuration from the environment.

    If ``env_file`` is not None, variables are loaded from that file first
    without overriding variables already present in the environment.
    """
    if env_file is not None:
        load_dotenv(env_file)

    missing = [name for name in _REQUIRED_VARS if not os.environ.get(name)]
    if missing:
        raise ConfigError(
            "Missing required environment variables: "
            + ", ".join(missing)
            + ". Copy .env.example to .env and fill in values."
        )

    return Config(
        api_key=os.environ["LLM_API_KEY"],
        base_url=os.environ["LLM_BASE_URL"],
        model=os.environ["LLM_MODEL"],
    )


SYSTEM_PROMPT = "You are a helpful AI assistant. Answer questions concisely."


class ChatAgent:
    """Streams chat completions from any OpenAI-compatible client.

    ``client`` is duck-typed: any object exposing async
    ``chat.completions.create(**kwargs)`` works (production uses
    ``openai.AsyncOpenAI``).
    """

    def __init__(self, client, model: str, system_prompt: str = SYSTEM_PROMPT):
        self._client = client
        self._model = model
        self._system_prompt = system_prompt

    async def stream_reply(self, user_text: str) -> AsyncIterator[str]:
        """Yield non-empty text deltas from a streaming chat completion."""
        stream = await self._client.chat.completions.create(
            model=self._model,
            stream=True,
            messages=[
                {"role": "system", "content": self._system_prompt},
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


def build_chat_agent(config: Config, system_prompt: str = SYSTEM_PROMPT) -> ChatAgent:
    """Build a ChatAgent with a real AsyncOpenAI client from Config.

    ``system_prompt`` overrides the default persona (e.g. the host's
    decider prompt); it defaults to :data:`SYSTEM_PROMPT`.
    """
    return ChatAgent(
        client=AsyncOpenAI(base_url=config.base_url, api_key=config.api_key),
        model=config.model,
        system_prompt=system_prompt,
    )

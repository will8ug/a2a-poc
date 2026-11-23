"""Fail-fast configuration for the Tavily search agent."""

import os

from dotenv import load_dotenv

_TAVILY_API_KEY = "TAVILY_API_KEY"


class TavilyConfigError(RuntimeError):
    """Raised when the Tavily API key is missing from configuration."""


def load_tavily_config(env_file: str | None = ".env") -> str:
    """Load the Tavily API key from the environment.

    If ``env_file`` is not None, variables are loaded from that file first
    without overriding variables already present in the environment.

    Raises :class:`TavilyConfigError` when the key is missing or empty.
    """
    if env_file is not None:
        load_dotenv(env_file)

    api_key = os.environ.get(_TAVILY_API_KEY)
    if not api_key:
        raise TavilyConfigError(
            f"Missing required environment variable: {_TAVILY_API_KEY}. "
            "Copy .env.example to .env and fill in values."
        )
    return api_key

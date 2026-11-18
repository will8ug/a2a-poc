"""Fail-fast configuration loaded from environment variables."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv


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

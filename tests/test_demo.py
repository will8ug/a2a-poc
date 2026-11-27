"""Offline tests for the demo launcher's supervision invariants.

The plan pinned the end-to-end boot/SIGINT check as demo.py's test, but
review findings superseded that for two invariants: a spawn failure
mid-boot must not orphan the children already spawned, and ambient
``A2A_POC_PORT`` must not reach any child (the launcher always uses the
fixed default ports). Both are pinned here with a monkeypatched
``asyncio.create_subprocess_exec``; everything else about the launcher
stays covered by the end-to-end check.
"""

import asyncio
from typing import Any

import pytest

from a2apoc import demo
from a2apoc.wiring import DEFAULT_CHAT_AGENT_URL, DEFAULT_SEARCH_AGENT_URL


class _FakeStdout:
    """Pipe surface ``_stream`` consumes: immediate EOF."""

    async def readline(self) -> bytes:
        return b""


class _FakeProcess:
    """Minimum ``asyncio.subprocess.Process`` surface demo.py consumes."""

    def __init__(self) -> None:
        self.stdout = _FakeStdout()
        self.returncode: int | None = None  # None = still running.
        self.terminate_calls = 0
        self.wait_calls = 0

    def terminate(self) -> None:
        self.terminate_calls += 1

    async def wait(self) -> int:
        self.wait_calls += 1
        self.returncode = 0  # terminated children exit cleanly.
        return 0


def test_spawn_failure_terminates_already_spawned_children(monkeypatch):
    """A failed spawn must reap the children spawned before it.

    The first child (search) spawns fine; the second (chat) raises
    ``OSError`` (as under fd/process limits). The launcher must surface the
    failure and terminate the first child instead of orphaning it. ``main``
    lets the ``OSError`` propagate, which exits the process non-zero.
    """
    first = _FakeProcess()
    spawned_modules: list[Any] = []
    spawned_envs: list[Any] = []

    async def fake_exec(*args: Any, **kwargs: Any) -> _FakeProcess:
        spawned_modules.append(args[2])  # (python, "-m", module)
        spawned_envs.append(kwargs.get("env"))
        if len(spawned_modules) == 1:
            return first
        raise OSError("simulated spawn failure (fd/process limit)")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    # An exported port override in the launcher's own environment: it must
    # not reach any child (README: "The demo launcher always uses the
    # default ports"), or all three children would race for one port.
    monkeypatch.setenv("A2A_POC_PORT", "7777")

    with pytest.raises(OSError, match="simulated spawn failure"):
        demo.main()

    assert spawned_modules == [
        "a2apoc.search.app",
        "a2apoc.chat.app",
    ]
    # Orphan-prevention pin: the already-spawned child was terminated...
    assert first.terminate_calls == 1
    # ...and waited on (reaped), not just signalled.
    assert first.wait_calls == 1
    # Port pin: every child env is passed explicitly and carries no
    # ambient A2A_POC_PORT.
    assert spawned_envs[0] is not None
    assert "A2A_POC_PORT" not in spawned_envs[0]


async def test_host_child_env_carries_default_agent_urls(monkeypatch):
    envs = []

    async def fake_exec(*args: Any, **kwargs: Any) -> _FakeProcess:
        envs.append(kwargs.get("env"))
        return _FakeProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.delenv("CHAT_AGENT_URL", raising=False)
    monkeypatch.delenv("SEARCH_AGENT_URL", raising=False)
    monkeypatch.setenv("A2A_POC_PORT", "7777")

    for name, module, extra_env in demo.CHILDREN:
        await demo._spawn(name, module, extra_env)

    assert envs[2]["CHAT_AGENT_URL"] == DEFAULT_CHAT_AGENT_URL
    assert envs[2]["SEARCH_AGENT_URL"] == DEFAULT_SEARCH_AGENT_URL
    for env in envs[:2]:
        assert "CHAT_AGENT_URL" not in env
        assert "SEARCH_AGENT_URL" not in env
    assert all("A2A_POC_PORT" not in env for env in envs)


async def test_host_agent_url_injection_overrides_ambient(monkeypatch):
    envs = []

    async def fake_exec(*args: Any, **kwargs: Any) -> _FakeProcess:
        envs.append(kwargs.get("env"))
        return _FakeProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setenv("CHAT_AGENT_URL", "http://ambient:1")
    monkeypatch.setenv("SEARCH_AGENT_URL", "http://ambient:2")

    for name, module, extra_env in demo.CHILDREN:
        await demo._spawn(name, module, extra_env)

    assert envs[2]["CHAT_AGENT_URL"] == DEFAULT_CHAT_AGENT_URL
    assert envs[2]["SEARCH_AGENT_URL"] == DEFAULT_SEARCH_AGENT_URL

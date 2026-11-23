"""Offline tests for the demo launcher's supervision invariants.

The plan pinned the end-to-end boot/SIGINT check as demo.py's test, but a
review finding superseded that for one invariant: a spawn failure mid-boot
must not orphan the children already spawned. That invariant is pinned here
with a monkeypatched ``asyncio.create_subprocess_exec``; everything else
about the launcher stays covered by the end-to-end check.
"""

import asyncio
from typing import Any

import pytest

from a2a_poc import demo


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

    async def fake_exec(*args: Any, **kwargs: Any) -> _FakeProcess:
        spawned_modules.append(args[2])  # (python, "-m", module)
        if len(spawned_modules) == 1:
            return first
        raise OSError("simulated spawn failure (fd/process limit)")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    with pytest.raises(OSError, match="simulated spawn failure"):
        demo.main()

    assert spawned_modules == [
        "a2a_poc.search.app",
        "a2a_poc.server.app",
    ]
    # Orphan-prevention pin: the already-spawned child was terminated...
    assert first.terminate_calls == 1
    # ...and waited on (reaped), not just signalled.
    assert first.wait_calls == 1

"""Demo launcher: run the search agent, chat agent, and host together.

``main`` spawns each server as a ``sys.executable -m a2a_poc...``
subprocess and supervises them:

* every output line is printed with a ``[name]`` prefix;
* the host child gets ``CHAT_AGENT_URL``/``SEARCH_AGENT_URL`` (the spec
  defaults, imported from the host module) injected into its environment
  explicitly, while ambient ``A2A_POC_PORT`` is stripped from every child
  (the launcher always uses the default ports; an exported port override
  would otherwise make all three children bind one port);
* SIGINT/SIGTERM to the launcher terminates every child, waits for them,
  and exits cleanly;
* a child that exits on its own terminates its siblings, is reported by
  name, and makes the launcher exit non-zero.

There is deliberately no committed test for this module: the pinned
end-to-end check (start all three, curl the agent cards, SIGINT the
launcher, then confirm every listener and process is gone) is the test.
"""

import asyncio
import os
import signal
import sys

from a2a_poc.host.app import (
    CHAT_AGENT_URL_ENV,
    DEFAULT_CHAT_AGENT_URL,
    DEFAULT_SEARCH_AGENT_URL,
    SEARCH_AGENT_URL_ENV,
)

# (log prefix, module) for each child, in spawn order.
CHILDREN: tuple[tuple[str, str], ...] = (
    ("search", "a2a_poc.search.app"),
    ("chat", "a2a_poc.server.app"),
    ("host", "a2a_poc.host.app"),
)

# Seconds to wait after terminate() before escalating to kill().
TERMINATE_TIMEOUT = 10.0


async def _spawn(name: str, module: str) -> asyncio.subprocess.Process:
    """Start ``python -m module`` with merged, piped output.

    Ambient ``A2A_POC_PORT`` is stripped from the child env so the
    launcher's fixed default ports always win: the three children must
    never race for one port. The host child additionally gets the agent
    URLs injected explicitly, so the demo does not depend on ambient
    environment settings either.
    """
    env = os.environ.copy()
    env.pop("A2A_POC_PORT", None)
    if name == "host":
        env[CHAT_AGENT_URL_ENV] = DEFAULT_CHAT_AGENT_URL
        env[SEARCH_AGENT_URL_ENV] = DEFAULT_SEARCH_AGENT_URL
    print(f"[demo] starting {name}: {sys.executable} -m {module}", flush=True)
    return await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        module,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )


async def _stream(name: str, proc: asyncio.subprocess.Process) -> int:
    """Echo the child's merged output line by line; return its exit code."""
    assert proc.stdout is not None  # always set by _spawn
    while True:
        raw = await proc.stdout.readline()
        if not raw:
            break  # EOF: the child closed its streams and is exiting.
        print(f"[{name}] {raw.decode('utf-8', 'replace').rstrip()}", flush=True)
    return await proc.wait()


async def _stop(procs: dict[str, asyncio.subprocess.Process]) -> None:
    """Terminate every live child, wait for it, kill any straggler."""
    for proc in procs.values():
        if proc.returncode is None:
            proc.terminate()
    for name, proc in procs.items():
        try:
            await asyncio.wait_for(proc.wait(), TERMINATE_TIMEOUT)
        except TimeoutError:
            print(f"[demo] {name} ignored SIGTERM; killing it", flush=True)
            proc.kill()
            await proc.wait()


async def _supervise() -> int:
    """Run all children until a signal or an unsolicited child exit."""
    # Install signal handlers before spawning so a signal during boot
    # cannot orphan children: it just triggers the normal shutdown path.
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    stop_task = asyncio.create_task(stop.wait(), name="stop")
    # Allocate the state the reaping finally needs before the try and fill
    # it inside: a spawn failure mid-boot still lands in that finally,
    # which terminates and waits for the children spawned so far.
    procs: dict[str, asyncio.subprocess.Process] = {}
    streams: dict[str, asyncio.Task[int]] = {}
    try:
        for name, module in CHILDREN:
            procs[name] = await _spawn(name, module)
        print("[demo] all children started; Ctrl-C to stop", flush=True)
        for name, proc in procs.items():
            streams[name] = asyncio.create_task(
                _stream(name, proc), name=f"stream-{name}"
            )
        name_by_task = {task: name for name, task in streams.items()}
        done, _ = await asyncio.wait(
            [stop_task, *streams.values()],
            return_when=asyncio.FIRST_COMPLETED,
        )
        if stop_task in done:
            print("[demo] signal received; shutting down", flush=True)
            return 0
        exited_task = next(iter(done))  # stop_task is pending: a child exited.
        exited = name_by_task[exited_task]
        raw = exited_task.result()
        print(
            f"[demo] {exited} exited on its own (code {raw}); stopping the others",
            flush=True,
        )
        return raw if raw > 0 else 1
    finally:
        # Always reap every child (no zombies) and settle the streamers.
        await _stop(procs)
        await asyncio.gather(*streams.values(), return_exceptions=True)
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(sig)
        stop_task.cancel()
        await asyncio.gather(stop_task, return_exceptions=True)


def main() -> None:
    """Run the demo (console entry point ``a2a-poc-demo``)."""
    try:
        code = asyncio.run(_supervise())
    except KeyboardInterrupt:  # signal raced handler installation
        code = 130
    sys.exit(code)

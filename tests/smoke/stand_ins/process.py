"""Starting and stopping a stand-in: a server process of its own, on loopback and an ephemeral port.

A stand-in runs as a separate process, never as a thread in pytest's: pytest's process has its
sockets blocked (tests/smoke/conftest.py), and a server thread there could not accept a
connection. The process binds `127.0.0.1` on port 0, so the operating system picks a free port and
two checks never collide, and announces what it bound as the first line on its stdout: one JSON
object naming its ports. Everything it says after that goes to a log file beside the check's other
scratch files, so a pipe nobody reads can never fill and stall it.

:meth:`StandInProcess.stop` is the teardown: terminate, wait, kill if it will not go. A stand-in
outlives no check: every one started is remembered in :data:`STARTED`, and tests/smoke/conftest.py
fails the check after which one is still running.
"""

from __future__ import annotations

import json
import selectors
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import IO

__all__ = ["LOOPBACK", "STARTED", "StandInFailedToStart", "StandInProcess", "still_running"]

LOOPBACK = "127.0.0.1"
"""The only address a stand-in binds, and the only host a declared stand-in can be reached at."""

STARTUP_SECONDS = 20.0
"""How long a stand-in may take to announce its ports. Moto's server takes well under one."""


STARTED: list[StandInProcess] = []
"""Every stand-in this pytest process started, running or not."""


class StandInFailedToStart(RuntimeError):
    """The stand-in exited, or said nothing, before announcing the ports it bound."""


class StandInProcess:
    """One running stand-in, and the ports it announced."""

    def __init__(self, process: subprocess.Popen[str], ports: Mapping[str, int], log: Path) -> None:
        self.process = process
        self.ports = dict(ports)
        self.log = log

    @classmethod
    def start(cls, script: Path, *arguments: str, log: Path) -> StandInProcess:
        """Run `script` with this interpreter and wait for the line naming its ports."""
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("w", encoding="utf-8") as errors:
            process = subprocess.Popen(
                [sys.executable, str(script), *arguments],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=errors,
                text=True,
            )
        try:
            assert process.stdout is not None
            announced = _first_line(process.stdout, STARTUP_SECONDS)
            if not announced:
                raise StandInFailedToStart(f"{script.name} announced no ports:\n{_tail(log)}")
            ports = json.loads(announced)
            if not isinstance(ports, dict) or not all(isinstance(port, int) for port in ports.values()):
                raise StandInFailedToStart(f"{script.name} announced {announced!r}, not its ports")
        except BaseException:
            _stop(process)
            raise
        started = cls(process, {str(name): int(port) for name, port in ports.items()}, log)
        STARTED.append(started)
        return started

    def address(self, name: str) -> tuple[str, int]:
        """`(host, port)` of the server this stand-in announced as `name`."""
        return LOOPBACK, self.ports[name]

    @property
    def addresses(self) -> Sequence[tuple[str, int]]:
        return [self.address(name) for name in self.ports]

    @property
    def running(self) -> bool:
        return self.process.poll() is None

    def stop(self) -> None:
        _stop(self.process)


def still_running() -> list[StandInProcess]:
    """The stand-ins started in this process that have not exited."""
    return [stand_in for stand_in in STARTED if stand_in.running]


def _first_line(stream: IO[str], timeout: float) -> str:
    deadline = time.monotonic() + timeout
    with selectors.DefaultSelector() as selector:
        selector.register(stream, selectors.EVENT_READ)
        while time.monotonic() < deadline:
            if selector.select(timeout=max(0.0, deadline - time.monotonic())):
                return stream.readline().strip()
    return ""


def _stop(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    if process.stdout is not None:
        process.stdout.close()


def _tail(log: Path) -> str:
    return "\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-30:])

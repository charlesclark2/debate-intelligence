"""Run a command under a time limit that stops it and every process it started (v1-e41-t05).

    .venv/bin/python scripts/hard_stop.py [--grace SECONDS] SECONDS COMMAND [ARGUMENT ...]

Working agreement 10 bounds a session's test runs with this script, at 115 seconds:

    .venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest tests/scripts -k hard_stop

Why not `perl -e 'alarm 115; exec @ARGV'`, which sessions used before: the alarm stops the one
process it is set on, the pytest controller, and nothing it started. In a probe on 2026-10-31 its
two xdist workers outlived it by about 5 seconds and then exited on their own, but the
subprocesses their tests had started ran on as orphans until they were killed by hand. A test that
runs a command or a parse pool leaves exactly that behind. `v1-e40-t22`'s run went on for about
30 minutes at load averages near 50 after its alarm, until it was killed by pid.

This script starts the command in a new session, so the command leads a process group of its own
and everything it starts joins that group: pytest-xdist's workers do (`execnet` starts them as
plain children), so do the subprocesses their tests start, and so does the pytest that `uv run`
starts. When the limit passes, the script
sends SIGTERM to the whole group, waits a grace period (5 seconds unless `--grace` says otherwise)
for it to be gone, sends SIGKILL to whatever is left, says on stderr that it stopped the run and at
what limit, and exits 124, the code GNU `timeout` uses. A SIGINT, SIGTERM or SIGHUP sent to the
script stops the group the same way, and the script exits 128 plus that signal's number.

A command that finishes in time exits with its own code, or with 128 plus the signal's number if a
signal killed it, as a shell reports it. Anything it left running in its group is stopped the same
way, and the script says so. Output is not touched: the command writes to the script's own stdout
and stderr, so nothing is buffered or reordered.

What a group kill cannot reach: a process that calls setsid() or setpgid() leaves the group, and
so do its children. Daemons do that; pytest and pytest-xdist do not, which
tests/scripts/test_hard_stop.py checks with a real `pytest -n 2` run whose tests each start a
subprocess. SIGKILL sent to this script
itself also leaves the group running, since nothing is left to stop it.

Python's standard library only, so it runs under any interpreter: macOS has no `setsid` command, and
`subprocess`'s `start_new_session` calls setsid() on macOS and Linux alike.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import signal
import subprocess
import sys
import time
from types import FrameType

STOPPED_AT_LIMIT = 124
COMMAND_NOT_FOUND = 127
COMMAND_NOT_RUNNABLE = 126
DEFAULT_GRACE_SECONDS = 5.0
# SIGKILL cannot be caught, so a group lasts after it only while the kernel tears it down.
AFTER_KILL_SECONDS = 5.0
POLL_SECONDS = 0.05
FORWARDED_SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)


class _Interrupted(Exception):
    def __init__(self, signum: int) -> None:
        super().__init__(signum)
        self.signum = signum


def _raise_interrupted(signum: int, frame: FrameType | None) -> None:
    raise _Interrupted(signum)


def _say(message: str) -> None:
    print(f"hard_stop: {message}", file=sys.stderr, flush=True)


def _positive_seconds(text: str) -> float:
    try:
        seconds = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a number of seconds: {text!r}") from None
    if not seconds > 0:
        raise argparse.ArgumentTypeError(f"must be more than 0 seconds: {text!r}")
    return seconds


def _parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="hard_stop.py",
        description="Run COMMAND; after SECONDS, stop it and every process in its group.",
    )
    parser.add_argument(
        "--grace",
        type=_positive_seconds,
        default=DEFAULT_GRACE_SECONDS,
        help=f"seconds between SIGTERM and SIGKILL (default {DEFAULT_GRACE_SECONDS:g})",
    )
    parser.add_argument("seconds", type=_positive_seconds, help="the time limit")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="the command and its arguments")
    args = parser.parse_args(argv)
    if args.command[:1] == ["--"]:
        args.command = args.command[1:]
    if not args.command:
        parser.error("a command to run is required")
    return args


def _group_exists(group: int) -> bool:
    try:
        os.killpg(group, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _signal_group(group: int, signum: int) -> None:
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(group, signum)


def _gone_within(run: subprocess.Popen[bytes], seconds: float) -> bool:
    """Wait up to `seconds` for the run's group to be empty, reaping the run's own process."""
    deadline = time.monotonic() + seconds
    while True:
        run.poll()
        if not _group_exists(run.pid):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(POLL_SECONDS)


def _stop_group(run: subprocess.Popen[bytes], grace: float) -> str:
    """TERM the run's group, then KILL what is left after `grace`; say how it ended."""
    for signum in FORWARDED_SIGNALS:
        signal.signal(signum, signal.SIG_IGN)
    _signal_group(run.pid, signal.SIGTERM)
    if _gone_within(run, grace):
        return f"sent TERM to process group {run.pid}, which ended"
    _signal_group(run.pid, signal.SIGKILL)
    if _gone_within(run, AFTER_KILL_SECONDS):
        return f"sent TERM to process group {run.pid}, then sent KILL after {grace:g} s"
    return (
        f"sent TERM to process group {run.pid}, then sent KILL after {grace:g} s, "
        f"and part of the group was still there {AFTER_KILL_SECONDS:g} s later"
    )


def _exit_code(returncode: int) -> int:
    return 128 - returncode if returncode < 0 else returncode


def main(argv: list[str] | None = None) -> int:
    args = _parse(sys.argv[1:] if argv is None else argv)
    for signum in FORWARDED_SIGNALS:
        signal.signal(signum, _raise_interrupted)
    run: subprocess.Popen[bytes] | None = None
    try:
        run = subprocess.Popen(args.command, start_new_session=True)
        returncode = run.wait(timeout=args.seconds)
    except FileNotFoundError:
        _say(f"command not found: {args.command[0]}")
        return COMMAND_NOT_FOUND
    except PermissionError:
        _say(f"command cannot be run: {args.command[0]}")
        return COMMAND_NOT_RUNNABLE
    except subprocess.TimeoutExpired:
        assert run is not None
        how = _stop_group(run, args.grace)
        _say(f"stopped the run at its {args.seconds:g}-second limit: {how}.")
        return STOPPED_AT_LIMIT
    except _Interrupted as interrupted:
        name = signal.Signals(interrupted.signum).name
        if run is None:
            return 128 + interrupted.signum
        how = _stop_group(run, args.grace)
        _say(f"received {name} before the {args.seconds:g}-second limit; stopped the run: {how}.")
        return 128 + interrupted.signum
    if _group_exists(run.pid):
        how = _stop_group(run, args.grace)
        code = _exit_code(returncode)
        _say(f"the command exited with {code} but left processes running in its group: {how}.")
    return _exit_code(returncode)


if __name__ == "__main__":
    sys.exit(main())

"""`scripts/hard_stop.py`: a session's time limit stops the run and every process it started (v1-e41-t05).

The commands under test are real process trees on this machine: a small program that forks
children and grandchildren which ignore SIGTERM, as a stuck xdist worker can, and one real
`pytest -n 2` run. Each process writes its pid to a file as it starts, and the `pid_dir` fixture
SIGKILLs any of them still alive when the test ends, so a failing test (or a mutant of the script)
leaves nothing running. No test waits near a real limit: the limits here are a second or two.
"""

from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "hard_stop.py"
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import task_helper  # noqa: E402

STOPPED_AT_LIMIT = 124
# How long a test waits for the script before it gives up, kills what it can and fails.
OUTER_TIMEOUT = 30.0

# The program a test runs under the script. It ignores SIGTERM and forks CHILDREN children, each of
# which forks GRANDCHILDREN grandchildren; the ignored SIGTERM is inherited by every fork. Every
# process records "<role>-<pid>" in PID_DIR, holding its process group, session and parent. When
# the whole tree has recorded itself the leader prints "tree ready" and then holds, or exits with
# the code given as LEADER (a number) and leaves the tree behind. A child given ESCAPE calls
# setsid() first, so it and its grandchildren are in a session and process group of their own, and
# points its stdout and stderr at /dev/null, as a daemon does, so the test's pipes can close.
TREE_PROGRAM = r"""
import os, signal, sys, time
from pathlib import Path

pid_dir = Path(sys.argv[1])
children, grandchildren, leader = int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
escape = sys.argv[5:] == ["escape"]

def record(role):
    path = pid_dir / f"{role}-{os.getpid()}"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(f"{os.getpgid(0)} {os.getsid(0)} {os.getppid()}\n")
    temporary.rename(path)

def hold():
    while True:
        time.sleep(60)

signal.signal(signal.SIGTERM, signal.SIG_IGN)
record("leader")
for _ in range(children):
    if os.fork() == 0:
        if escape:
            os.setsid()
            nowhere = os.open(os.devnull, os.O_WRONLY)
            os.dup2(nowhere, 1)
            os.dup2(nowhere, 2)
        record("child")
        for _ in range(grandchildren):
            if os.fork() == 0:
                record("grandchild")
                hold()
        hold()
expected = 1 + children + children * grandchildren
while len([p for p in pid_dir.iterdir() if p.suffix != ".tmp"]) < expected:
    time.sleep(0.01)
print("tree ready", flush=True)
if leader == "hold":
    hold()
sys.exit(int(leader))
"""


# --------------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------------


def _alive(pid: int) -> bool:
    """Whether `pid` is a running process. A zombie is not running: it is waiting to be reaped."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    state = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True)
    return bool(state.stdout.strip()) and not state.stdout.strip().startswith("Z")


def _recorded(pid_dir: Path) -> dict[int, tuple[str, int, int, int]]:
    """pid -> (role, process group, session, parent) for every process that recorded itself."""
    recorded = {}
    for path in pid_dir.iterdir():
        if path.suffix == ".tmp":
            continue
        role, pid = path.name.rsplit("-", 1)
        group, session, parent = (int(field) for field in path.read_text().split())
        recorded[int(pid)] = (role, group, session, parent)
    return recorded


def _survivors(pids: list[int], within: float) -> list[int]:
    """The pids still running after up to `within` seconds; orphans take a moment to be reaped."""
    deadline = time.monotonic() + within
    while True:
        running = [pid for pid in pids if _alive(pid)]
        if not running or time.monotonic() > deadline:
            return running
        time.sleep(0.05)


@pytest.fixture
def pid_dir(tmp_path: Path) -> Iterator[Path]:
    directory = tmp_path / "pids"
    directory.mkdir()
    yield directory
    for pid in _recorded(directory):
        if _alive(pid):
            os.kill(pid, signal.SIGKILL)


def _start(
    *arguments: str, cwd: Path | None = None, env: dict[str, str] | None = None
) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [sys.executable, str(SCRIPT), *arguments],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=cwd,
        env=env,
    )


def _finish(run: subprocess.Popen[str]) -> tuple[int, str, str, float]:
    """Wait for the script; (exit code, stdout, stderr, seconds it took from now)."""
    started = time.monotonic()
    try:
        stdout, stderr = run.communicate(timeout=OUTER_TIMEOUT)
    except subprocess.TimeoutExpired:
        run.kill()
        run.wait()
        # Whatever the script failed to stop still holds its pipes open, so they never reach end of
        # file; the pid_dir fixture kills those processes.
        pytest.fail(f"hard_stop.py was still running after {OUTER_TIMEOUT} s")
    return run.returncode, stdout, stderr, time.monotonic() - started


def _tree(
    tmp_path: Path, pid_dir: Path, children: int, grandchildren: int, leader: str, *extra: str
) -> list[str]:
    program = tmp_path / "tree.py"
    program.write_text(TREE_PROGRAM)
    return [sys.executable, str(program), str(pid_dir), str(children), str(grandchildren), leader, *extra]


# --------------------------------------------------------------------------------------------
# a run past its limit
# --------------------------------------------------------------------------------------------


def test_hard_stop_kills_every_process_of_a_tree_that_ignores_term(tmp_path: Path, pid_dir: Path) -> None:
    command = _tree(tmp_path, pid_dir, children=2, grandchildren=2, leader="hold")
    run = _start("--grace", "1", "2", *command)
    code, stdout, stderr, took = _finish(run)

    recorded = _recorded(pid_dir)
    roles = sorted(role for role, *_ in recorded.values())
    assert roles == ["child"] * 2 + ["grandchild"] * 4 + ["leader"], "the tree did not finish starting in 2 s"
    assert _survivors(list(recorded), within=3.0) == []
    assert code == STOPPED_AT_LIMIT
    assert "tree ready" in stdout
    assert "hard_stop: stopped the run at its 2-second limit" in stderr
    assert "sent KILL" in stderr
    # The limit, the 1-second grace and at most a few seconds more.
    assert took < 2 + 1 + 4


def test_hard_stop_ends_a_tree_that_obeys_term_without_kill(tmp_path: Path, pid_dir: Path) -> None:
    program = tmp_path / "obeys_term.py"
    program.write_text(TREE_PROGRAM.replace("signal.signal(signal.SIGTERM, signal.SIG_IGN)", ""))
    run = _start("--grace", "5", "1", sys.executable, str(program), str(pid_dir), "1", "1", "hold")
    code, _, stderr, took = _finish(run)

    assert len(_recorded(pid_dir)) == 3
    assert _survivors(list(_recorded(pid_dir)), within=3.0) == []
    assert code == STOPPED_AT_LIMIT
    assert "sent KILL" not in stderr
    assert took < 1 + 4, "a group that obeys TERM is not kept for the whole grace period"


# --------------------------------------------------------------------------------------------
# a run that finishes in time
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("exit_code", [0, 3])
def test_hard_stop_passes_a_command_in_time_through(exit_code: int) -> None:
    program = f"import sys; print('to stdout'); print('to stderr', file=sys.stderr); sys.exit({exit_code})"
    code, stdout, stderr, took = _finish(_start("10", sys.executable, "-c", program))

    assert (code, stdout, stderr) == (exit_code, "to stdout\n", "to stderr\n")
    assert took < 5, "a command that finishes is not held to its limit"


def test_hard_stop_passes_output_through_while_the_command_runs() -> None:
    program = "import time; print('first', flush=True); time.sleep(1.5); print('second')"
    run = _start("10", sys.executable, "-c", program)
    assert run.stdout is not None
    first = run.stdout.readline()
    still_running = run.poll() is None
    code, rest, _, _ = _finish(run)

    assert (first, still_running) == ("first\n", True)
    assert (code, rest) == (0, "second\n")


def test_hard_stop_reports_a_command_killed_by_a_signal_as_a_shell_does() -> None:
    program = "import os, signal; os.kill(os.getpid(), signal.SIGKILL)"
    code, _, _, _ = _finish(_start("10", sys.executable, "-c", program))

    assert code == 128 + signal.SIGKILL


def test_hard_stop_stops_what_a_command_in_time_left_running_in_its_group(
    tmp_path: Path, pid_dir: Path
) -> None:
    command = _tree(tmp_path, pid_dir, children=1, grandchildren=1, leader="5")
    code, stdout, stderr, _ = _finish(_start("--grace", "1", "10", *command))

    recorded = _recorded(pid_dir)
    assert len(recorded) == 3
    assert _survivors(list(recorded), within=3.0) == []
    assert code == 5
    assert "tree ready" in stdout
    assert "left processes running in its group" in stderr


# --------------------------------------------------------------------------------------------
# what a group kill cannot reach, and why pytest-xdist is not that case
# --------------------------------------------------------------------------------------------


def test_hard_stop_cannot_reach_a_child_that_started_its_own_session(tmp_path: Path, pid_dir: Path) -> None:
    command = _tree(tmp_path, pid_dir, 1, 1, "hold", "escape")
    code, _, _, _ = _finish(_start("--grace", "1", "1", *command))

    recorded = _recorded(pid_dir)
    escaped = sorted(pid for pid, (role, *_) in recorded.items() if role != "leader")
    leader = [pid for pid, (role, *_) in recorded.items() if role == "leader"]
    assert code == STOPPED_AT_LIMIT
    assert _survivors(leader, within=3.0) == []
    # The documented limit: setsid() takes a process out of the group, so the kill misses it and
    # its own children. The pid_dir fixture kills them.
    assert _survivors(escaped, within=0.5) == escaped


XDIST_TESTS = """
import os, time
from pathlib import Path

import pytest

@pytest.mark.parametrize("n", [1, 2])
def test_hold(n):
    pid_dir = Path(os.environ["HARD_STOP_PID_DIR"])
    path = pid_dir / f"worker-{os.getpid()}"
    path.with_suffix(".tmp").write_text(f"{os.getpgid(0)} {os.getsid(0)} {os.getppid()}\\n")
    path.with_suffix(".tmp").rename(path)
    time.sleep(60)
"""


def test_hard_stop_reaches_pytest_xdist_workers_which_stay_in_the_run_s_group(
    tmp_path: Path, pid_dir: Path
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "pytest.ini").write_text("[pytest]\n")
    (project / "test_hold.py").write_text(XDIST_TESTS)
    env = {key: value for key, value in os.environ.items() if not key.startswith("PYTEST_")}
    env["HARD_STOP_PID_DIR"] = str(pid_dir)
    pytest_command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-n",
        "2",
        "-p",
        "no:randomly",
        "-p",
        "no:cacheprovider",
    ]
    run = _start("--grace", "1", "60", *pytest_command, cwd=project, env=env)

    deadline = time.monotonic() + OUTER_TIMEOUT
    while len(_recorded(pid_dir)) < 2 and time.monotonic() < deadline and run.poll() is None:
        time.sleep(0.05)
    workers = _recorded(pid_dir)
    # Stopping the script stops its run the same way the limit does, without waiting for it.
    run.send_signal(signal.SIGTERM)
    code, _, stderr, _ = _finish(run)

    assert len(workers) == 2, f"the xdist workers did not start: {stderr}"
    # Each worker's parent is the pytest controller, the leader of the group the script made.
    assert {(group, session) for _, group, session, parent in workers.values()} == {
        (parent, parent) for *_, parent in workers.values()
    }
    assert len({parent for *_, parent in workers.values()}) == 1
    assert _survivors(list(workers), within=3.0) == []
    assert code == 128 + signal.SIGTERM
    assert "hard_stop: received SIGTERM" in stderr


# --------------------------------------------------------------------------------------------
# usage
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("arguments", [["5"], ["0", "true"], ["-1", "true"], ["soon", "true"]])
def test_hard_stop_refuses_a_missing_command_or_a_limit_that_is_not_positive(arguments: list[str]) -> None:
    code, _, stderr, _ = _finish(_start(*arguments))

    assert code == 2
    assert "usage:" in stderr


def test_hard_stop_says_when_the_command_cannot_be_found(tmp_path: Path) -> None:
    code, _, stderr, _ = _finish(_start("5", str(tmp_path / "no-such-command")))

    assert code == 127
    assert "no-such-command" in stderr


# --------------------------------------------------------------------------------------------
# agreement 10 and the session prompt name it
# --------------------------------------------------------------------------------------------

HARD_STOP_RUN = ".venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest"


def _words(text: str) -> str:
    return " ".join(text.split())


def test_agreement_10_and_the_session_prompt_name_the_hard_stop_in_place_of_the_perl_alarm() -> None:
    agreements = (REPO_ROOT / "docs" / "process" / "working-agreements.md").read_text()
    agreement_10 = re.search(r"^## 10\..*?(?=^## 11\.)", agreements, re.MULTILINE | re.DOTALL)
    assert agreement_10 is not None

    for text in (agreement_10.group(0), task_helper.PROMPT):
        assert HARD_STOP_RUN in _words(text)
        assert "perl -e" not in text

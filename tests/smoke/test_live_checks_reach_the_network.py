"""A check marked `live` reaches the network from pytest's own process, and the next plain check does not.

`v1-e39-t10`'s cloud checks call dev with httpx inside pytest's process. The repository's options
include `--disable-socket`, and tests/smoke's conftest let a `live` check past its own block without
turning pytest-socket back on, so all three failed on `socket.getaddrinfo` wherever they ran for real.
Their own tests called them against the app in-process, with no socket, and could not see it
(`v1-e39-t26`).

This runs socket_probes/live_then_plain_checks.py in a real pytest, from the repository root so that
it reads pyproject.toml's options itself, with the stand-in for dev a loopback server in that pytest's
own process: a `live` check, then a plain one. The first must get the server's answer and the second
must be refused: as the runbook runs the cloud checks (`-n 0`), with `--force-enable-socket` added, and
in xdist workers, as validate-dev's driver runs them (it passes no `-n`, so pyproject's
`--numprocesses=auto` holds; two workers here).

`in_process`: it tests tests/smoke's own machinery, so it runs in `ci` and is not part of
validate-dev's recorded tier.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tomllib
import xml.etree.ElementTree as ElementTree
from pathlib import Path

import pytest

pytestmark = pytest.mark.in_process

REPOSITORY = Path(__file__).resolve().parents[2]
PROBES = Path(__file__).resolve().parent / "socket_probes" / "live_then_plain_checks.py"
LIVE_CHECK = "test_a_live_check_reaches_the_loopback_server"
PLAIN_CHECK = "test_a_plain_check_after_it_is_refused"


def repository_addopts() -> list[str]:
    pyproject = tomllib.loads((REPOSITORY / "pyproject.toml").read_text(encoding="utf-8"))
    return pyproject["tool"]["pytest"]["ini_options"]["addopts"]


def child_environment() -> dict[str, str]:
    """This environment without what would change the child's options or point it at a build."""
    return {
        name: value
        for name, value in os.environ.items()
        if name != "PYTEST_ADDOPTS" and not name.startswith(("PYTEST_XDIST", "DEBATE_SMOKE"))
    }


def test_the_child_run_starts_from_blocked_sockets() -> None:
    """The run below proves something only while the repository's own options block the network."""
    assert "--disable-socket" in repository_addopts()


@pytest.mark.parametrize(
    "extra",
    [["-n", "0"], ["-n", "0", "--force-enable-socket"], ["-n", "2"]],
    ids=["as-the-runbook-runs-it", "force-enable-socket", "in-xdist-workers"],
)
def test_a_live_check_reaches_loopback_and_the_next_plain_check_is_refused(
    tmp_path: Path, extra: list[str]
) -> None:
    junit = tmp_path / "junit.xml"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(PROBES),
            "-m",
            "not slow",
            "-p",
            "no:randomly",
            "-p",
            "no:cacheprovider",
            f"--junitxml={junit}",
            *extra,
        ],
        cwd=REPOSITORY,
        env=child_environment(),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    output = completed.stdout + completed.stderr
    assert junit.exists(), output
    outcomes = {case.get("name"): outcome(case) for case in ElementTree.parse(junit).iter("testcase")}
    assert outcomes == {LIVE_CHECK: "passed", PLAIN_CHECK: "passed"}, output
    assert completed.returncode == 0, output


def outcome(case: ElementTree.Element) -> str:
    for word in ("failure", "error", "skipped"):
        if case.find(word) is not None:
            return word
    return "passed"

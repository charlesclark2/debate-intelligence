"""Fixtures and guards for tests/smoke: an installed build, run as a process, offline (v1-e01-t10).

:func:`installed_cli` is the one way a smoke check reaches the CLI (installed_build.py says which
binary that is). With ``DEBATE_SMOKE_BIN`` set, as validate-dev sets it, every selected check under
tests/smoke must use it: a check that would exercise this checkout's source instead (``CliRunner``,
moto, respx) stops the run before anything is tested.

**The network is blocked unless a check is marked ``live``** (ac4). In this process, pytest-socket
is switched on here rather than trusted to the command line. In the CLI's process, which
pytest-socket never sees, ``network_guard/sitecustomize.py`` refuses every outbound call and logs
it, and :func:`installed_cli` fails the check afterwards if the log holds anything, even when the
command caught the refusal and carried on.

The markers registered here: ``in_process`` for checks that drive the CLI inside pytest's own
process (they run in ``ci`` and are not part of validate-dev's recorded tier), and ``canary`` for
validate-dev's opt-in live canary tier. README.md in this directory explains both.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
import pytest_socket
from tests.smoke.installed_build import (
    SMOKE_BIN,
    SMOKE_DIRECTORY,
    InstalledCli,
    SmokeBuild,
    SmokeConfigurationError,
    assert_no_network_attempts,
    resolve_build,
)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "in_process: drives the CLI inside pytest's own process (CliRunner, moto, respx); runs in ci, "
        "not in validate-dev's recorded tier",
    )
    config.addinivalue_line(
        "markers", "canary: validate-dev's opt-in live canary tier; polite, low-cost, dev budget only"
    )


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Against an installed build, refuse to run any smoke check that would test the source tree.

    `trylast`, so this sees the items `-m` left selected.
    """
    if not os.environ.get(SMOKE_BIN, "").strip():
        return
    offenders = [
        item.nodeid
        for item in items
        if Path(item.path).resolve().is_relative_to(SMOKE_DIRECTORY)
        and "installed_cli" not in getattr(item, "fixturenames", ())
    ]
    if offenders:
        raise pytest.UsageError(
            f"{SMOKE_BIN} is set, so every selected smoke check must run the installed binary through "
            "the installed_cli fixture. These would test this checkout's source instead (deselect "
            "them with -m 'not in_process'):\n  " + "\n  ".join(offenders)
        )


@pytest.fixture(scope="session")
def smoke_build() -> SmokeBuild:
    try:
        return resolve_build(os.environ)
    except SmokeConfigurationError as problem:
        pytest.exit(f"tests/smoke cannot run: {problem}", returncode=pytest.ExitCode.USAGE_ERROR)


@pytest.fixture
def installed_cli(
    smoke_build: SmokeBuild, tmp_path: Path, request: pytest.FixtureRequest
) -> Iterator[InstalledCli]:
    """The build under test. Offline, and checked for network attempts, unless marked `live`."""
    live = request.node.get_closest_marker("live") is not None
    cli = InstalledCli(smoke_build, tmp_path, network=live)
    yield cli
    if not live:
        assert_no_network_attempts(cli.network_log)


@pytest.fixture(autouse=True)
def _sockets_blocked_unless_live(request: pytest.FixtureRequest) -> Iterator[None]:
    """pytest's own process gets no network either, whatever the command line said (ac4)."""
    if request.node.get_closest_marker("live") is not None:
        yield
        return
    pytest_socket.disable_socket(allow_unix_socket=True)
    try:
        yield
    finally:
        pytest_socket.enable_socket()

"""The end-to-end suite's rules: no network, a data directory of the test's own, every boundary recorded.

Every module under `tests/integration/` is checked at collection for two things, and the run stops
with a usage error naming the module if one is missing (`v1-e09-t05`):

* **`slow`, at module level.** `pytestmark` carries `pytest.mark.slow`, so the PR `ci` check, which
  runs `-m "not slow and not live"`, leaves the module out, and validate-dev's slow tier
  (`slow and not live and not eval and not operator_data`) and the nightly run take it.
* **No socket opt-out.** No test asks for pytest-socket's `enable_socket` marker or `socket_enabled`
  fixture. The suite runs with sockets disabled, and nothing in it may turn them back on.

A missing recording is never a skip: the harness (`e2e_harness.py`) raises
:class:`MissingFixtureError` for a cassette a scenario names that is not committed, and
:func:`boundaries` raises it when the test ends for any request no recording answered.

Every test then runs with the socket check of :func:`network_disabled`: `disable_socket` is called
again here, whatever options the run was started with, and an Internet socket is shown to be refused
before the test body starts. The run's header says so.

The fixtures:

* :func:`cli_environment`: no `DEBATE_*` override from the shell, `DEBATE_ENV=test`, and the data
  directory, `HOME` and every output under `tmp_path`, so nothing is read from or written to the
  machine's own state. Committed configuration (`config/`, `prompts/`) is read from the checkout.
* :func:`boundaries`: :class:`~tests.integration.e2e_harness.Boundaries`, handed to every container the
  app builds, and checked when the test ends: a request no recording answered fails the test with
  :class:`MissingFixtureError`.
* :func:`cli`: the CLI, run in this process through `create_app()`.
"""

from __future__ import annotations

import os
import socket
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from pytest_socket import SocketBlockedError, disable_socket
from tests.integration.e2e_harness import Boundaries, Cli

from debate_cli.container import ServiceContainer

# Imported here, before any test arms the socket check: urllib3 (through trafilatura) probes for IPv6
# with a socket when it is first imported, which the first article fetch would otherwise do inside a test.
from debate_core.integrations import html_extractor as html_extractor
from debate_core.integrations.models.errors import MissingFixtureError

SUITE: Path = Path(__file__).resolve().parent


def pytest_report_header(config: pytest.Config) -> str:
    return (
        "tests/integration: sockets disabled for every test (pytest-socket disable_socket, AF_UNIX only); "
        "every boundary recorded"
    )


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Refuse a module of this suite that is not marked `slow` or that turns sockets back on."""
    refusals: set[str] = set()
    for item in items:
        path = Path(str(item.path)).resolve()
        if SUITE not in path.parents:
            continue
        module = item.getparent(pytest.Module)
        marks: Any = getattr(module.obj, "pytestmark", []) if module is not None else []
        marks = marks if isinstance(marks, list) else [marks]
        if not any(getattr(mark, "name", None) == "slow" for mark in marks):
            refusals.add(
                f"{path.relative_to(SUITE.parents[1])}: no module-level `pytestmark = pytest.mark.slow`"
            )
        if item.get_closest_marker("enable_socket") is not None or "socket_enabled" in getattr(
            item, "fixturenames", ()
        ):
            refusals.add(f"{item.nodeid}: turns sockets back on")
    if refusals:
        raise pytest.UsageError("tests/integration: " + "; ".join(sorted(refusals)))


@pytest.fixture(autouse=True)
def network_disabled() -> None:
    """Disable Internet sockets for this test, and show that one is refused before the test runs."""
    disable_socket(allow_unix_socket=True)
    # pytest-socket warns as it refuses; the probe expects its own warning, so any other one still shows.
    with pytest.warns(UserWarning, match="tried to use socket"), pytest.raises(SocketBlockedError):
        socket.socket(socket.AF_INET, socket.SOCK_STREAM)


@pytest.fixture
def cli_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The `test` environment over a data directory of this test's own; returns that directory."""
    for name in [name for name in os.environ if name.startswith("DEBATE_")]:
        monkeypatch.delenv(name)
    data_dir = tmp_path / "data"
    monkeypatch.setenv("DEBATE_ENV", "test")
    monkeypatch.setenv("DEBATE_STORAGE__DATA_DIR", str(data_dir))
    # robots.txt and the page are two requests to one host; the polite interval would sleep between them.
    monkeypatch.setenv("DEBATE_HTTP__PER_HOST_INTERVAL_SECONDS", "0")
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return data_dir


@pytest.fixture
def boundaries(cli_environment: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Boundaries]:
    """Every container the app builds gets the recorded boundaries; an unrecorded request fails the test."""
    recorded = Boundaries()
    build = ServiceContainer.__init__

    def with_recordings(self: ServiceContainer, **arguments: Any) -> None:
        build(self, **arguments)
        for name, instance in recorded.seams():
            self.override(name, instance)

    monkeypatch.setattr(ServiceContainer, "__init__", with_recordings)
    yield recorded
    missing = recorded.missing_fixtures()
    if missing:
        raise missing[0]


@pytest.fixture
def cli() -> Cli:
    return Cli()


__all__ = ["MissingFixtureError"]

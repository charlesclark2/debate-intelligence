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

**A check that declares a stand-in may reach it, and nothing else** (v1-e01-t21). The stand-in
fixtures (:data:`~tests.smoke.stand_ins.STAND_IN_FIXTURES`) start a server on 127.0.0.1 and an
ephemeral port, tell :func:`installed_cli` its address, and stop it afterwards. The build's guard
then lets it connect to exactly those addresses, and this process is opened to 127.0.0.1 alone for
the check. Loopback is refused, and logged, for every check that declares none.

The markers registered here: ``in_process`` for checks that drive the CLI inside pytest's own
process (they run in ``ci`` and are not part of validate-dev's recorded tier), and ``canary`` for
validate-dev's opt-in live canary tier. README.md in this directory explains both.
"""

from __future__ import annotations

import os
import socket
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

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
from tests.smoke.stand_ins import STAND_IN_FIXTURES
from tests.smoke.stand_ins.opencaselist import OpenCaselistStandIn, StandInCertificate, make_certificate
from tests.smoke.stand_ins.process import LOOPBACK, still_running
from tests.smoke.stand_ins.s3 import S3StandIn


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


@pytest.fixture
def s3_stand_in(installed_cli: InstalledCli, tmp_path: Path) -> Iterator[S3StandIn]:
    """moto in server mode, which the build reaches through `storage.s3.endpoint_url` (v1-e01-t21)."""
    stand_in = S3StandIn.start(log=tmp_path / "stand-ins" / "s3.log")
    try:
        for host, port in stand_in.addresses:
            installed_cli.allow_stand_in(host, port)
        installed_cli.configure(DEBATE_STORAGE__S3__ENDPOINT_URL=stand_in.endpoint)
        yield stand_in
    finally:
        stand_in.stop()


@pytest.fixture(scope="session")
def stand_in_certificate(tmp_path_factory: pytest.TempPathFactory) -> StandInCertificate:
    """The run's CA and the leaf the OpenCaselist stand-in serves with; made once per worker."""
    return make_certificate(tmp_path_factory.mktemp("stand-in-certificate"))


@pytest.fixture
def opencaselist_stand_in(
    installed_cli: InstalledCli, tmp_path: Path, stand_in_certificate: StandInCertificate
) -> Iterator[OpenCaselistStandIn]:
    """The OpenCaselist API and its file host, over https, reached through `caselist.api_base_url`."""
    stand_in = OpenCaselistStandIn.start(tmp_path / "stand-ins" / "opencaselist", stand_in_certificate)
    try:
        for host, port in stand_in.addresses:
            installed_cli.allow_stand_in(host, port)
        installed_cli.configure(
            DEBATE_CASELIST__API_BASE_URL=stand_in.api_base_url,
            SSL_CERT_FILE=str(stand_in_certificate.authority),
        )
        yield stand_in
    finally:
        stand_in.stop()


@pytest.fixture(autouse=True)
def _no_stand_in_outlives_its_check() -> Iterator[None]:
    """Torn down after every other fixture of the check, so it sees what they left running (ac4)."""
    yield
    left = still_running()
    for stand_in in left:
        stand_in.stop()
    assert not left, f"{len(left)} stand-in(s) outlived the check: {[s.ports for s in left]}"


@pytest.fixture(autouse=True)
def _sockets_blocked_unless_live(request: pytest.FixtureRequest) -> Iterator[None]:
    """pytest's own process gets no network either, whatever the command line said (ac4).

    A check that declares a stand-in gets 127.0.0.1 and nothing else (v1-e01-t21).
    """
    if request.node.get_closest_marker("live") is not None:
        yield
        return
    if STAND_IN_FIXTURES & set(request.fixturenames):
        with _loopback_only():
            yield
        return
    pytest_socket.disable_socket(allow_unix_socket=True)
    try:
        yield
    finally:
        pytest_socket.enable_socket()


@contextmanager
def _loopback_only() -> Iterator[None]:
    """Connections to 127.0.0.1 only, and no host lookup but of 127.0.0.1 and localhost."""
    pytest_socket.enable_socket()
    connect, getaddrinfo = socket.socket.connect, socket.getaddrinfo

    def loopback_lookups(host: Any, *arguments: Any, **keywords: Any) -> Any:
        name = host.decode("ascii", "replace") if isinstance(host, bytes) else host
        if name not in {LOOPBACK, "localhost"}:
            raise pytest_socket.SocketBlockedError(f"a stand-in check looked up {host!r}")
        return getaddrinfo(host, *arguments, **keywords)

    pytest_socket.socket_allow_hosts([LOOPBACK], allow_unix_socket=True)
    socket.getaddrinfo = loopback_lookups
    try:
        yield
    finally:
        socket.socket.connect = connect  # type: ignore[method-assign]
        socket.getaddrinfo = getaddrinfo

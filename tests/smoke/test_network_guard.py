"""The offline smoke tier cannot reach the network, shown on the build under test (ac4).

These run in validate-dev's recorded tier too, so every validation proves the guard against the
installed build's own interpreter on the machine doing the validating, not just on a laptop.

Each check points the guard's log at a file of its own, because the attempt it provokes is the
point; the fixture's own log, which fails a check that leaves anything in it, stays empty.

The address is 192.0.2.1, from TEST-NET-1 (RFC 5737), which is reserved for documentation and
routes nowhere: even with the guard gone, nothing would be reached.

The last three checks are v1-e01-t21's: loopback is refused to a check that declares no stand-in,
and a check that declares one reaches that stand-in and no other address, on this machine or off it.
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
import pytest_socket
from tests.smoke.installed_build import NETWORK_LOG, STAND_INS, InstalledCli
from tests.smoke.stand_ins.s3 import S3StandIn

UNROUTABLE = "192.0.2.1"

CONNECT = f"""
import socket
try:
    socket.create_connection(({UNROUTABLE!r}, 9), timeout=1)
except RuntimeError as refusal:
    print("refused:", type(refusal).__name__)
except OSError as failure:
    print("reached the network stack:", failure)
else:
    print("connected")
"""


def attempts(log: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []


def test_the_builds_interpreter_cannot_open_a_connection(installed_cli: InstalledCli, tmp_path: Path) -> None:
    log = tmp_path / "provoked.log"

    run = installed_cli.run_program(
        [str(installed_cli.build.interpreter), "-c", CONNECT], env={NETWORK_LOG: str(log)}
    )

    assert run.exit_code == 0, run.output
    assert run.stdout.strip() == "refused: OutboundNetworkBlocked"
    assert [attempt["call"] for attempt in attempts(log)] == ["getaddrinfo"]


def test_a_request_the_cli_itself_makes_is_refused_and_logged(
    installed_cli: InstalledCli, tmp_path: Path
) -> None:
    """`caselist auth login` aimed at an unroutable address: the CLI's own process loads the guard."""
    log = tmp_path / "provoked.log"
    pointed_nowhere = {
        NETWORK_LOG: str(log),
        "DEBATE_CASELIST__API_ENABLED": "true",
        "DEBATE_CASELIST__API_BASE_URL": f"https://{UNROUTABLE}/v1",
        "DEBATE_CASELIST__TOKEN_BACKEND": "file",
        "DEBATE_CASELIST__MAX_ATTEMPTS": "1",
        "DEBATE_HTTP__CONNECT_TIMEOUT_SECONDS": "1",
    }

    run = installed_cli.run(
        "--json", "caselist", "auth", "login", "--username", "nobody", env=pointed_nowhere, stdin="x\n"
    )

    assert run.exit_code != 0, run.output
    logged = attempts(log)
    assert logged, f"the CLI's request was not refused by the guard:\n{run.output}"
    assert all(UNROUTABLE in str(attempt["target"]) for attempt in logged), logged


# ------------------------------------------------------------------------------------------------
# Loopback, for a check that declares a stand-in and for no other (v1-e01-t21, ac2)
# ------------------------------------------------------------------------------------------------

#: A plain `connect`, with no host lookup before it: what the guard's connect rule decides alone. (A
#: lookup of anything but loopback is refused first, which the checks above already show.)
REACH = """
import socket, sys
for address in sys.argv[1:]:
    host, port = address.rsplit(":", 1)
    connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    connection.settimeout(2)
    try:
        connection.connect((host, int(port)))
    except RuntimeError as refusal:
        print(address, "refused:", type(refusal).__name__)
    except OSError as failure:
        print(address, "reached the network stack:", failure)
    else:
        print(address, "connected")
    finally:
        connection.close()
"""

LISTENER = """
import socket, sys
server = socket.socket()
server.bind(("127.0.0.1", 0))
server.listen()
print(server.getsockname()[1], flush=True)
while True:
    connection, _ = server.accept()
    with open(sys.argv[1], "a") as accepted:
        accepted.write("accepted\\n")
    connection.close()
"""


@pytest.fixture
def loopback_listener(tmp_path: Path) -> Iterator[tuple[str, Path]]:
    """Something listening on 127.0.0.1 that is not a stand-in: no check declares it.

    Yields its `host:port` and the file it writes a line to for every connection it accepts.
    """
    accepted = tmp_path / "listener-accepted.txt"
    listener = subprocess.Popen(
        [sys.executable, "-c", LISTENER, str(accepted)], stdout=subprocess.PIPE, text=True
    )
    try:
        assert listener.stdout is not None
        port = int(listener.stdout.readline())
        yield f"127.0.0.1:{port}", accepted
    finally:
        listener.terminate()
        listener.wait(timeout=5)


def reach(installed_cli: InstalledCli, log: Path, *addresses: str) -> dict[str, str]:
    """What the build's interpreter got, connecting to each address with the guard loaded."""
    run = installed_cli.run_program(
        [str(installed_cli.build.interpreter), "-c", REACH, *addresses], env={NETWORK_LOG: str(log)}
    )
    assert run.exit_code == 0, run.output
    return dict(line.split(" ", 1) for line in run.stdout.splitlines())


def test_a_check_without_a_stand_in_is_refused_loopback_and_the_refusal_is_logged(
    installed_cli: InstalledCli, tmp_path: Path, loopback_listener: tuple[str, Path]
) -> None:
    listening, accepted = loopback_listener
    log = tmp_path / "provoked.log"

    reached = reach(installed_cli, log, listening)

    assert reached == {listening: "refused: OutboundNetworkBlocked"}
    assert [(attempt["call"], attempt["target"]) for attempt in attempts(log)] == [
        ("connect", repr(("127.0.0.1", int(listening.rsplit(":", 1)[1]))))
    ]
    assert not accepted.exists(), "the connection reached the listener"
    with pytest.raises(pytest_socket.SocketBlockedError):
        socket.create_connection(("127.0.0.1", int(listening.rsplit(":", 1)[1])), timeout=1)


def test_a_check_with_a_stand_in_reaches_it_and_is_refused_an_address_off_this_machine(
    installed_cli: InstalledCli, tmp_path: Path, s3_stand_in: S3StandIn
) -> None:
    log = tmp_path / "provoked.log"
    (stand_in,) = (f"{host}:{port}" for host, port in s3_stand_in.addresses)
    elsewhere = f"{UNROUTABLE}:9"

    reached = reach(installed_cli, log, stand_in, elsewhere)

    assert reached == {stand_in: "connected", elsewhere: "refused: OutboundNetworkBlocked"}
    assert [(attempt["call"], attempt["target"]) for attempt in attempts(log)] == [
        ("connect", repr((UNROUTABLE, 9)))
    ]
    with (
        socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection,
        pytest.raises(pytest_socket.SocketConnectBlockedError),
    ):
        connection.connect((UNROUTABLE, 9))


def test_a_check_with_a_stand_in_is_refused_any_other_loopback_port_and_it_is_logged(
    installed_cli: InstalledCli, tmp_path: Path, s3_stand_in: S3StandIn, loopback_listener: tuple[str, Path]
) -> None:
    """A stand-in opens its own address, not loopback as a whole."""
    listening, accepted = loopback_listener
    log = tmp_path / "provoked.log"

    reached = reach(installed_cli, log, listening)

    assert reached == {listening: "refused: OutboundNetworkBlocked"}
    assert [attempt["call"] for attempt in attempts(log)] == ["connect"]
    assert not accepted.exists(), "the connection reached the listener"


def test_a_stand_in_declared_off_this_machine_opens_nothing(
    installed_cli: InstalledCli, tmp_path: Path, s3_stand_in: S3StandIn
) -> None:
    """A declaration cannot open an address off the machine: the guard keeps its loopback entries only."""
    log = tmp_path / "provoked.log"
    (stand_in,) = (f"{host}:{port}" for host, port in s3_stand_in.addresses)
    elsewhere = f"{UNROUTABLE}:9"

    run = installed_cli.run_program(
        [str(installed_cli.build.interpreter), "-c", REACH, stand_in, elsewhere],
        env={NETWORK_LOG: str(log), STAND_INS: f"{stand_in} {elsewhere}"},
    )

    assert run.exit_code == 0, run.output
    reached = dict(line.split(" ", 1) for line in run.stdout.splitlines())
    assert reached == {stand_in: "connected", elsewhere: "refused: OutboundNetworkBlocked"}
    assert [(attempt["call"], attempt["target"]) for attempt in attempts(log)] == [
        ("connect", repr((UNROUTABLE, 9)))
    ]

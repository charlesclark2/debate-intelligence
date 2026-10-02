"""The offline smoke tier cannot reach the network, shown on the build under test (ac4).

These run in validate-dev's recorded tier too, so every validation proves the guard against the
installed build's own interpreter on the machine doing the validating, not just on a laptop.

Each check points the guard's log at a file of its own, because the attempt it provokes is the
point; the fixture's own log, which fails a check that leaves anything in it, stays empty.

The address is 192.0.2.1, from TEST-NET-1 (RFC 5737), which is reserved for documentation and
routes nowhere: even with the guard gone, nothing would be reached.
"""

from __future__ import annotations

import json
from pathlib import Path

from tests.smoke.installed_build import NETWORK_LOG, InstalledCli

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

"""Plain `doctor` makes no network call and binds nothing but loopback (v1-e05-t09, the PM's ruling).

`scripts/install_channel.sh` and `validate-dev` run plain `doctor` on machines with no network to
speak of, so it may neither reach out nor listen. It does import every wired integration
(v1-e01-t22), and importing the AWS SDK imports urllib3, which binds one AF_INET6 socket to `::1`
to learn whether the machine has IPv6 (`urllib3/util/connection.py`). That bind is loopback, sends
nothing and is swallowed by urllib3 if it fails. pytest-socket's guard refuses any socket at all, so
it reports the probe, and only as a warning in whichever test first imports boto3 in a worker.

This guard is the precise one. It runs plain `doctor` in a fresh interpreter, where urllib3 has not
been imported yet, with every way of reaching the network refused and recorded: `connect`,
`connect_ex`, `sendto`, `getaddrinfo`, `gethostbyname` and `gethostbyname_ex`, and `bind` to any
address that is not loopback (127.0.0.0/8, `::1`). It records rather than only raises, because the
code it guards may swallow the refusal, as urllib3 does. The guard is tested on its own first: a
guard that misses a call would pass doctor for the wrong reason.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any

import pytest

from debate_cli.exit_codes import ExitCode

GUARD = """
import ipaddress, json, socket

attempts = []


def refuse(what):
    attempts.append(what)
    raise OSError(f"refused by the network guard: {what}")


def is_loopback(address):
    try:
        return ipaddress.ip_address(address[0]).is_loopback
    except (TypeError, ValueError, IndexError):
        return False


real_bind = socket.socket.bind


def bind(self, address):
    if not is_loopback(address):
        refuse(f"bind {address!r}")
    return real_bind(self, address)


socket.socket.bind = bind
socket.socket.connect = lambda self, address: refuse(f"connect {address!r}")
socket.socket.connect_ex = lambda self, address: refuse(f"connect_ex {address!r}")
socket.socket.sendto = lambda self, *arguments: refuse(f"sendto {arguments[-1]!r}")
socket.getaddrinfo = lambda host, *arguments, **options: refuse(f"getaddrinfo {host!r}")
socket.gethostbyname = lambda host: refuse(f"gethostbyname {host!r}")
socket.gethostbyname_ex = lambda host: refuse(f"gethostbyname_ex {host!r}")

exit_code = None
urllib3_imported = None
try:
{body}
finally:
    print(json.dumps({"attempts": attempts, "exit_code": exit_code, "urllib3_imported": urllib3_imported}))
"""

PLAIN_DOCTOR = """
import sys
from typer.testing import CliRunner
from debate_cli.app import create_app
assert "urllib3" not in sys.modules
exit_code = CliRunner().invoke(create_app(), ["doctor"]).exit_code
urllib3_imported = "urllib3.util.connection" in sys.modules
"""
"""Plain `doctor`, in an interpreter that has not imported urllib3 yet, so its loopback probe runs."""


def guarded(body: str) -> dict[str, Any]:
    """Run `body` in a fresh interpreter under the guard; what it tried, and `exit_code` if it set one."""
    indented = "\n".join(f"    {line}" for line in body.strip().splitlines())
    environ = {name: value for name, value in os.environ.items() if not name.startswith("DEBATE_")}
    completed = subprocess.run(
        [sys.executable, "-c", GUARD.replace("{body}", indented)],
        capture_output=True,
        text=True,
        env=environ,
        timeout=60,
        check=False,
    )
    lines = completed.stdout.strip().splitlines()
    assert lines, completed.stderr[-2000:]
    found: dict[str, Any] = json.loads(lines[-1])
    return found


def test_plain_doctor_makes_no_network_call_and_binds_nothing_but_loopback() -> None:
    found = guarded(PLAIN_DOCTOR)

    # urllib3 was imported, so its ::1 probe ran under the guard and was allowed, as it should be.
    assert found == {"attempts": [], "exit_code": ExitCode.OK, "urllib3_imported": True}


# ------------------------------------------------------------------------------------------------
# The guard itself: it reports every way of reaching the network, and allows the loopback probe
# ------------------------------------------------------------------------------------------------

SWALLOWED = "try:\n    {call}\nexcept OSError:\n    pass"
"""Each call is made the way urllib3 makes its probe: the refusal is caught and dropped."""


@pytest.mark.parametrize(
    ("call", "reported"),
    [
        ('socket.getaddrinfo("example.invalid", 443)', "getaddrinfo 'example.invalid'"),
        ('socket.gethostbyname("example.invalid")', "gethostbyname 'example.invalid'"),
        ('socket.gethostbyname_ex("example.invalid")', "gethostbyname_ex 'example.invalid'"),
        ('socket.socket().connect(("192.0.2.1", 443))', "connect ('192.0.2.1', 443)"),
        ('socket.socket().connect_ex(("192.0.2.1", 443))', "connect_ex ('192.0.2.1', 443)"),
        ('socket.socket(type=socket.SOCK_DGRAM).sendto(b"x", ("192.0.2.1", 53))', "sendto ('192.0.2.1', 53)"),
        ('socket.socket().bind(("0.0.0.0", 0))', "bind ('0.0.0.0', 0)"),
        ('socket.socket(socket.AF_INET6).bind(("::", 0))', "bind ('::', 0)"),
        ('socket.socket().bind(("localhost", 0))', "bind ('localhost', 0)"),
    ],
    ids=[
        "getaddrinfo",
        "gethostbyname",
        "gethostbyname_ex",
        "connect",
        "connect_ex",
        "sendto",
        "bind-any-ipv4",
        "bind-any-ipv6",
        "bind-a-name",
    ],
)
def test_the_doctor_network_guard_reports_a_swallowed_network_call(call: str, reported: str) -> None:
    found = guarded(SWALLOWED.format(call=call))

    assert found["attempts"] == [reported]


@pytest.mark.parametrize(
    "address",
    ['("127.0.0.1", 0)', '("127.8.9.10", 0)'],
    ids=["127.0.0.1", "elsewhere-in-127/8"],
)
def test_the_doctor_network_guard_allows_a_loopback_bind(address: str) -> None:
    found = guarded(f"with socket.socket() as probe:\n    probe.bind({address})")

    assert found["attempts"] == []


def test_the_doctor_network_guard_allows_urllib3s_ipv6_probe() -> None:
    """The exact call urllib3 makes when it is imported; `::1` may be unusable here, never refused."""
    found = guarded(SWALLOWED.format(call='socket.socket(socket.AF_INET6).bind(("::1", 0))'))

    assert found["attempts"] == []

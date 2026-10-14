"""The stand-ins themselves: each on 127.0.0.1 and a port the system chose, and gone when stopped.

`v1-e01-t21`, ac4. Every stand-in binds port 0, so the operating system hands it a free port from
its ephemeral range and two checks running side by side never collide. Stopping one ends its
process and frees its port; that every check's stand-ins are stopped is enforced in conftest.py,
not left to these checks.

Each check here takes a stand-in fixture as well as starting its own, which is what opens this
process to 127.0.0.1 (tests/smoke/stand_ins/__init__.py).
"""

from __future__ import annotations

import socket
import subprocess
import sys
from pathlib import Path

import pytest
from tests.smoke.installed_build import InstalledCli
from tests.smoke.stand_ins.opencaselist import OpenCaselistStandIn, StandInCertificate
from tests.smoke.stand_ins.process import LOOPBACK
from tests.smoke.stand_ins.s3 import S3StandIn


def ephemeral_ports() -> range:
    """The operating system's own range for a port-0 bind, read from the system."""
    if sys.platform == "darwin":
        first, last = (
            int(subprocess.run(["sysctl", "-n", name], capture_output=True, text=True, check=True).stdout)
            for name in ("net.inet.ip.portrange.first", "net.inet.ip.portrange.last")
        )
    else:
        first, last = map(int, Path("/proc/sys/net/ipv4/ip_local_port_range").read_text().split())
    return range(first, last + 1)


def refuses_connections(address: tuple[str, int]) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
        connection.settimeout(2)
        try:
            connection.connect(address)
        except ConnectionRefusedError:
            return True
    return False


def test_two_s3_stand_ins_at_once_get_two_ephemeral_ports_on_loopback(
    installed_cli: InstalledCli, s3_stand_in: S3StandIn, tmp_path: Path
) -> None:
    other = S3StandIn.start(log=tmp_path / "other-s3.log")
    try:
        addresses = [*s3_stand_in.addresses, *other.addresses]
    finally:
        other.stop()

    assert [host for host, _ in addresses] == [LOOPBACK, LOOPBACK]
    (first, _), (second, _) = ((port, host) for host, port in addresses)
    assert first != second
    assert first in ephemeral_ports() and second in ephemeral_ports(), (first, second, ephemeral_ports())


def test_the_opencaselist_stand_in_binds_two_ephemeral_ports_on_loopback(
    installed_cli: InstalledCli, opencaselist_stand_in: OpenCaselistStandIn
) -> None:
    """Two servers, because the site is two hosts: the API, and the file host it never sends a token."""
    (api_host, api_port), (files_host, files_port) = opencaselist_stand_in.addresses

    assert (api_host, files_host) == (LOOPBACK, LOOPBACK)
    assert api_port != files_port
    assert {api_port, files_port} <= set(ephemeral_ports())
    assert opencaselist_stand_in.api_base_url == f"https://{LOOPBACK}:{api_port}/v1"


@pytest.mark.parametrize("kind", ["s3", "opencaselist"])
def test_a_stopped_stand_in_has_exited_and_its_ports_refuse_connections(
    installed_cli: InstalledCli,
    s3_stand_in: S3StandIn,
    stand_in_certificate: StandInCertificate,
    tmp_path: Path,
    kind: str,
) -> None:
    started = (
        S3StandIn.start(log=tmp_path / "stopped.log")
        if kind == "s3"
        else OpenCaselistStandIn.start(tmp_path / "stopped", stand_in_certificate)
    )
    addresses = list(started.addresses)
    assert not any(refuses_connections(address) for address in addresses), "it was listening"

    started.stop()

    assert not started.process.running
    assert started.process.process.returncode is not None
    assert all(refuses_connections(address) for address in addresses)

"""Refuses every outbound network call in a process that tests/smoke starts (v1-e01-t10, ac4).

pytest-socket blocks sockets in pytest's own process and nowhere else. The smoke checks run the
installed `debate-research` as a separate process, which pytest-socket never sees, so they put this
directory on that process's PYTHONPATH and name a log file in ``DEBATE_SMOKE_NETWORK_LOG``. Python's
``site`` module imports ``sitecustomize`` at start-up, before the CLI's own code, so from then on:

* connecting or sending to an internet address (IPv4 or IPv6, loopback included) raises
  :class:`OutboundNetworkBlocked`;
* resolving a host name raises it too, since a DNS lookup is itself a request; ``localhost`` and
  numeric loopback addresses are the exceptions, because resolving them leaves the machine never;
* every refusal is appended to the log as one JSON line, *before* raising.

The log is what makes this enforcement rather than a hint. A command that caught the exception and
carried on (a retry loop, a "could not reach the server" message) would still leave its line in the
log, and the smoke fixture fails the check after it finishes whenever the log is not empty
(tests/smoke/conftest.py).

Unix-domain sockets are left alone: they cannot leave the machine, and asyncio builds its event
loop's self-pipe from one. Binding is left alone too: urllib3 binds ``::1`` once at import to learn
whether IPv6 works, which sends nothing.

The exception derives from ``RuntimeError``, not ``OSError``, on purpose: an HTTP client treats an
``OSError`` as a transient network failure and may retry it quietly, whereas this should end the
command loudly. Without ``DEBATE_SMOKE_NETWORK_LOG`` this module does nothing.
"""

from __future__ import annotations

import os

_LOG = os.environ.get("DEBATE_SMOKE_NETWORK_LOG")

if _LOG:
    import json
    import socket
    from typing import Any

    _RESOLVABLE = frozenset({"localhost", "127.0.0.1", "::1"})
    _INTERNET_FAMILIES = frozenset({socket.AF_INET, socket.AF_INET6})

    class OutboundNetworkBlocked(RuntimeError):
        """A process started by the smoke suite tried to reach the network."""

    def _refuse(call: str, target: object) -> None:
        with open(_LOG, "a", encoding="utf-8") as log:  # noqa: PTH123 - no pathlib before the CLI loads
            log.write(json.dumps({"pid": os.getpid(), "call": call, "target": repr(target)}) + "\n")
        raise OutboundNetworkBlocked(
            f"{call}({target!r}) refused: the smoke suite runs with the network blocked "
            "(tests/smoke/network_guard/sitecustomize.py)"
        )

    _connect = socket.socket.connect
    _connect_ex = socket.socket.connect_ex
    _sendto = socket.socket.sendto
    _getaddrinfo = socket.getaddrinfo
    _gethostbyname = socket.gethostbyname
    _gethostbyname_ex = socket.gethostbyname_ex

    def _connect_guarded(self: socket.socket, address: Any) -> None:
        if self.family in _INTERNET_FAMILIES:
            _refuse("connect", address)
        _connect(self, address)

    def _connect_ex_guarded(self: socket.socket, address: Any) -> int:
        if self.family in _INTERNET_FAMILIES:
            _refuse("connect_ex", address)
        return _connect_ex(self, address)

    def _sendto_guarded(self: socket.socket, *arguments: Any) -> int:
        if self.family in _INTERNET_FAMILIES:
            _refuse("sendto", arguments[-1])
        return _sendto(self, *arguments)

    def _getaddrinfo_guarded(host: Any, *arguments: Any, **keywords: Any) -> Any:
        if host is not None and _as_text(host) not in _RESOLVABLE:
            _refuse("getaddrinfo", host)
        return _getaddrinfo(host, *arguments, **keywords)

    def _gethostbyname_guarded(host: str) -> str:
        if host not in _RESOLVABLE:
            _refuse("gethostbyname", host)
        return _gethostbyname(host)

    def _gethostbyname_ex_guarded(host: str) -> Any:
        if host not in _RESOLVABLE:
            _refuse("gethostbyname_ex", host)
        return _gethostbyname_ex(host)

    def _as_text(host: Any) -> str:
        return host.decode("ascii", "replace") if isinstance(host, bytes) else str(host)

    socket.socket.connect = _connect_guarded  # type: ignore[method-assign]
    socket.socket.connect_ex = _connect_ex_guarded  # type: ignore[method-assign]
    socket.socket.sendto = _sendto_guarded  # type: ignore[method-assign,assignment]
    socket.getaddrinfo = _getaddrinfo_guarded
    socket.gethostbyname = _gethostbyname_guarded
    socket.gethostbyname_ex = _gethostbyname_ex_guarded

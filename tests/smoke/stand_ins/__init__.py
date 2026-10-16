"""Stand-ins: local servers the installed build reaches over loopback in place of AWS and OpenCaselist.

`v1-e01-t21`. The storage and OpenCaselist smoke checks used moto and respx, which patch the process
they run in. The installed build is a different process, so those checks could only run against
the source tree. A stand-in is a server instead, in a process of its own, bound to 127.0.0.1 on an
ephemeral port. The build is pointed at it through configuration a dev installation accepts and a
prod one refuses, and is a client of it exactly as it is of the real service:

* :mod:`~tests.smoke.stand_ins.s3`: moto in server mode, for the evidence bucket and STS, reached
  through `storage.s3.endpoint_url`;
* :mod:`~tests.smoke.stand_ins.opencaselist`: the OpenCaselist API and its file host over https,
  serving synthetic responses, reached through `caselist.api_base_url`.

**Only a check that declares a stand-in can reach loopback, and it reaches only that stand-in.** A
check declares one by taking its fixture, one of :data:`STAND_IN_FIXTURES`
(tests/smoke/conftest.py). The fixture starts the server and tells
:class:`~tests.smoke.installed_build.InstalledCli` its addresses, which the build's network guard
then lets the build connect to: those `host:port` pairs, and nothing else, loopback or not
(`network_guard/sitecustomize.py`). pytest's own process is opened to 127.0.0.1 for the check, so
that it can set the stand-in up and read what it was asked. Every other check runs as before, with
loopback refused like any other address and the refusal logged.
"""

from __future__ import annotations

__all__ = ["STAND_IN_FIXTURES"]

STAND_IN_FIXTURES = frozenset({"s3_stand_in", "opencaselist_stand_in"})
"""The fixtures that declare a stand-in. A check that takes one may reach loopback; no other may."""

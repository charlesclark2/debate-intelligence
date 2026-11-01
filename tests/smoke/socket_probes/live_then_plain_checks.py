"""A `live` check and a plain one, run in a pytest of their own by test_live_checks_reach_the_network.py.

No normal run collects this file: its name does not start with `test_`, so only a command line that
names it runs it. That child pytest reads the repository's own options from pyproject.toml,
`--disable-socket` among them, and this directory's conftest, tests/smoke/conftest.py, as every
smoke check does (`v1-e39-t26`).

The server is a thread in the child's own process on 127.0.0.1, started when pytest imports this
file, during collection and before pytest-socket blocks anything, so it is listening whatever either
check is allowed. Each check reaches for it the way a cloud check reaches for dev: httpx, in pytest's
own process. The `live` one must get its answer; the plain one, which runs after it, must be refused.
Nothing leaves the machine.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Final

import httpx
import pytest
import pytest_socket
from tests.smoke.stand_ins.process import LOOPBACK

ANSWER: Final = "the loopback server answered"


class _Answer(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = ANSWER.encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        pass


_SERVER: Final = ThreadingHTTPServer((LOOPBACK, 0), _Answer)
threading.Thread(target=_SERVER.serve_forever, daemon=True).start()
URL: Final = f"http://{LOOPBACK}:{_SERVER.server_port}/"


def get() -> httpx.Response:
    """No proxy from the environment, so the request can only go to the loopback server."""
    with httpx.Client(trust_env=False, timeout=5) as client:
        return client.get(URL)


@pytest.mark.live
def test_a_live_check_reaches_the_loopback_server() -> None:
    assert get().text == ANSWER


def test_a_plain_check_after_it_is_refused() -> None:
    with pytest.raises(pytest_socket.SocketBlockedError):
        get()

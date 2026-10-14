"""The OpenCaselist stand-in's process: the API and its file host, over TLS on loopback (`v1-e01-t21`).

Started by :class:`tests.smoke.stand_ins.opencaselist.OpenCaselistStandIn`, never by hand. Two
servers, each on 127.0.0.1 and an ephemeral port, because the real site is two hosts: the API,
which the client sends its token to, and the object store an archive listing points at, which it
never does (`debate_core.integrations.opencaselist.transport`). Both speak https, as the client
requires, with a certificate made for the run that the build is told to trust (`SSL_CERT_FILE`).

What they serve is the **site file** the check wrote: JSON naming, for each server, the responses
by route. It is read again on every request, so a check that lists a new camp file between two
pulls rewrites it. Every response is synthetic, built by the check from the invented fixtures under
`tests/fixtures/` (`docs/policies/caselist-data-use.md`); no real response, name or token is here.

The API answers 401 to a request without the `caselist_token` cookie, as the real one does. Each
request is appended to the **request log** as one JSON line: which server, the method, the path,
the query, and whether the cookie was sent. Never its value.

The first line on stdout is `{"api": <port>, "files": <port>}`.
"""

from __future__ import annotations

import argparse
import json
import ssl
import sys
import threading
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit

LOOPBACK = "127.0.0.1"
TOKEN_COOKIE = "caselist_token"


def route_key(path: str, query: str | dict[str, str] = "") -> str:
    """How a route is named in the site file: the path, then its query in a fixed order."""
    pairs = (
        sorted(query.items()) if isinstance(query, dict) else sorted(parse_qsl(query, keep_blank_values=True))
    )
    return f"{path}?{urlencode(pairs)}" if pairs else path


def handler_for(
    server_name: str, site: Path, log: Path, lock: threading.Lock
) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802 - the name http.server dispatches to
            parts = urlsplit(self.path)
            cookie = SimpleCookie(self.headers.get("Cookie", ""))
            authenticated = TOKEN_COOKIE in cookie and bool(cookie[TOKEN_COOKIE].value)
            with lock, log.open("a", encoding="utf-8") as record:
                record.write(
                    json.dumps(
                        {
                            "server": server_name,
                            "method": "GET",
                            "path": parts.path,
                            "query": dict(parse_qsl(parts.query, keep_blank_values=True)),
                            "authenticated": authenticated,
                        }
                    )
                    + "\n"
                )
            if server_name == "api" and not authenticated:
                self._answer(401, json.dumps({"message": "Not authenticated"}).encode(), "application/json")
                return
            routes: dict[str, Any] = json.loads(site.read_text(encoding="utf-8")).get(server_name, {})
            response = routes.get(route_key(parts.path, parts.query)) or routes.get(parts.path)
            if response is None:
                self._answer(404, json.dumps({"message": "Not found"}).encode(), "application/json")
                return
            if "file" in response:
                body = Path(response["file"]).read_bytes()
                content_type = response.get("content_type", "application/octet-stream")
            else:
                body = json.dumps(response["json"]).encode()
                content_type = "application/json"
            self._answer(int(response.get("status", 200)), body, content_type)

        def _answer(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - http.server's signature
            sys.stderr.write(f"{server_name}: {format % args}\n")

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--certificate", type=Path, required=True)
    parser.add_argument("--key", type=Path, required=True)
    parser.add_argument("--site", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    arguments = parser.parse_args()

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(arguments.certificate, arguments.key)
    lock = threading.Lock()
    servers: dict[str, ThreadingHTTPServer] = {}
    for name in ("api", "files"):
        server = ThreadingHTTPServer((LOOPBACK, 0), handler_for(name, arguments.site, arguments.log, lock))
        server.socket = context.wrap_socket(server.socket, server_side=True)
        servers[name] = server
    sys.stdout.write(json.dumps({name: server.server_address[1] for name, server in servers.items()}) + "\n")
    sys.stdout.flush()
    sys.stdout = sys.stderr
    threads = [threading.Thread(target=server.serve_forever, daemon=True) for server in servers.values()]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()


if __name__ == "__main__":
    main()

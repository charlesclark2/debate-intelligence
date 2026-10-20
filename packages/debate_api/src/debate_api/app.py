"""The student search pilot's ASGI app (ADR-0019 (b)), as small as v1-e39-t04 needs it.

This is the placeholder the pilot's infrastructure is proven with: a request through CloudFront
reaches the function and gets this page back, and the Lambda Web Adapter's readiness check gets
`/healthz`. Sign-in, the session and the search pages arrive with v1-e39-t05 and v1-e39-t06, which
grow this module rather than replace it.

It is a plain ASGI app with no Lambda code in it. In the image, uvicorn serves it on port 8080 with
its access log off, because an access log line holds the client's address and the query string
(gate item 4); the adapter forwards each function URL event to it.

Two rules from ADR-0019 hold already:

* every response says `Cache-Control: private, no-store` unless a route has said otherwise
  ((a) 5: nothing the app serves is cached by CloudFront or kept by the browser);
* there is no interactive API documentation, because FastAPI's pages load scripts from a
  third-party CDN and the pilot loads none ((b) 1).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse

PRIVATE_NO_STORE = "private, no-store"

PLACEHOLDER_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Team evidence search</title>
</head>
<body>
<main>
<h1>Team evidence search</h1>
<p>The team's evidence search is being set up. Signing in and searching are not open yet.</p>
</main>
</body>
</html>
"""


async def healthz() -> JSONResponse:
    """The Lambda Web Adapter's readiness check, and the deploy script's check through CloudFront."""
    return JSONResponse({"status": "ok"})


async def placeholder() -> HTMLResponse:
    """The page every path of the pilot will sit behind, for now without the sign-in in front."""
    return HTMLResponse(PLACEHOLDER_PAGE)


async def private_no_store(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    response = await call_next(request)
    response.headers.setdefault("Cache-Control", PRIVATE_NO_STORE)
    return response


def create_app() -> FastAPI:
    """Build the app. uvicorn calls this with `--factory`, so importing the module builds nothing."""
    app = FastAPI(
        title="Team evidence search",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.middleware("http")(private_no_store)
    app.add_api_route("/healthz", healthz, methods=["GET"], include_in_schema=False)
    app.add_api_route("/", placeholder, methods=["GET"], include_in_schema=False)
    return app

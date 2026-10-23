"""The student search pilot's ASGI app (ADR-0019 (b)): sign-in, the session, the account and search pages.

v1-e39-t04 proved the infrastructure with a placeholder page; v1-e39-t05 puts sign-in in front of
everything (ADR-0019 (d)); v1-e39-t06 adds the search pages behind it, over the index the function
fetches the first time a search needs it.

It is a plain ASGI app with no Lambda code in it. In the image, uvicorn serves it on port 8080
with its access log off, because an access log line holds the client's address and the query
string (gate item 4); the Lambda Web Adapter forwards each function URL event to it. uvicorn calls
:func:`create_app` with `--factory`, which builds the services from the function's environment
through `debate_api.container`. A test passes its own :class:`~debate_api.state.PilotServices`.

What holds for every response:

* `Cache-Control: private, no-store` unless a route said otherwise ((a) 5): only the content-hashed
  script and stylesheet under `/static/` are cacheable;
* no interactive API documentation, because FastAPI's pages load scripts from a third-party CDN and
  the pilot loads none ((b) 1);
* no CORS headers.

The order the layers are added in is the order that matters: the caching rule wraps everything,
then the gate (:mod:`debate_api.access`), then the routes and their error handlers.
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

from debate_api.access import RouteAccess, install_gate
from debate_api.cookies import CookieSealer
from debate_api.errors import install_error_handlers
from debate_api.pages import PageRenderer, load_app_script, load_app_stylesheet
from debate_api.routes import register_routes
from debate_api.state import PilotServices, PilotState

__all__ = ["PRIVATE_NO_STORE", "create_app"]

PRIVATE_NO_STORE = "private, no-store"


async def private_no_store(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    response = await call_next(request)
    response.headers.setdefault("Cache-Control", PRIVATE_NO_STORE)
    return response


def create_app(services: PilotServices | None = None) -> FastAPI:
    """Build the app. With no `services`, build them from this process's environment.

    Building them reads the client secret and the cookie keys from Parameter Store, and refuses to
    go on if the cookie keys are still Terraform's placeholder
    (:class:`~debate_api.configuration.CookieKeysNotSet`), so a misconfigured function never starts.
    """
    if services is None:
        # Imported here: the composition root builds AWS adapters, which a test never needs.
        from debate_api.container import build_pilot_services

        services = build_pilot_services(os.environ)
    app = FastAPI(title="Team evidence search", docs_url=None, redoc_url=None, openapi_url=None)
    script, stylesheet = load_app_script(), load_app_stylesheet()
    app.state.pilot = PilotState(
        services=services,
        sealer=CookieSealer(services.cookie_keys),
        renderer=PageRenderer(
            app_script=script, app_stylesheet=stylesheet, cart_cap=services.card_download.card_cap
        ),
        app_script=script,
        app_stylesheet=stylesheet,
    )
    routes = RouteAccess()
    register_routes(app, routes)
    install_error_handlers(app)
    install_gate(app, routes)
    app.middleware("http")(private_no_store)
    return app

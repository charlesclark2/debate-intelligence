"""The authorization matrix (v1-e39-t05 ac1 and ac6): every route, both roles, every session state.

The landscape pages (v1-e39-t17) are in it: a student and a coach alike may read them (data-use
policy 1.16), and every other session state is refused.

Each route is asked for as a student and as a coach, with a session that is valid, expired,
idle, tampered, sealed under keys the app does not hold, sealed as another cookie, or absent. Only
the four session-free routes answer without a valid session, and a coach route refuses a student.

The route list here is checked against the app's own routes, so a route added without a row in
:data:`ROUTE_REQUESTS` fails :func:`test_the_matrix_covers_every_route_the_app_serves`.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import timedelta
from typing import Any

import pytest
from fastapi.routing import APIRoute

from debate_api.access import SESSION_FREE_PATHS, Access, RouteAccess
from debate_api.configuration import CookieKeys
from debate_api.cookies import SESSION_COOKIE, SIGN_IN_COOKIE, CookieSealer
from debate_api.routes import ROUTE_ACCESS


@pytest.fixture
def world(every_surface_world: Any) -> Any:
    """This file's world: every surface at once (`v1-e39-t20`)."""
    return every_surface_world


@dataclass(frozen=True)
class RouteRequest:
    method: str
    path: str
    """The route's path as the app registers it."""
    url: str
    """What is asked for: the path with its parameters filled in."""
    data: dict[str, str] | None = None


def _script_url(world: Any) -> str:
    return world.app.state.pilot.app_script.path


ROUTE_REQUESTS: list[RouteRequest] = [
    RouteRequest("GET", "/healthz", "/healthz"),
    RouteRequest("GET", "/static/{digest}/{name}", "<script>"),
    RouteRequest("GET", "/auth/callback", "/auth/callback?code=synthetic-code&state=synthetic-state"),
    RouteRequest("GET", "/signed-out", "/signed-out"),
    RouteRequest("POST", "/auth/sign-out", "/auth/sign-out", {}),
    RouteRequest("GET", "/account/authenticator", "/account/authenticator"),
    RouteRequest("POST", "/account/authenticator", "/account/authenticator", {"code": "424242"}),
    RouteRequest("GET", "/", "/"),
    RouteRequest("GET", "/search", "/search?q=zephyr&event=LD"),
    RouteRequest("GET", "/cards/{caselist}/{cluster_id}", "<card featured>"),
    RouteRequest("GET", "/cards/{caselist}/{cluster_id}/copy", "<card featured>/copy"),
    RouteRequest("POST", "/download", "/download", {"cards": f"hsld26/{27:064x}"}),
    RouteRequest("GET", "/account", "/account"),
    RouteRequest("POST", "/account/email", "/account/email", {"email": "debater.one@example.test"}),
    RouteRequest("POST", "/account/email/verify", "/account/email/verify", {"code": "135790"}),
    RouteRequest("POST", "/account/email/remove", "/account/email/remove", {}),
    RouteRequest("GET", "/landscape", "/landscape"),
    RouteRequest("GET", "/landscape/{caselist}", "/landscape/synthpolicy26"),
    RouteRequest("GET", "/landscape/{caselist}/report/{part}", "/landscape/synthpolicy26/report/negative"),
    RouteRequest("GET", "/landscape/{caselist}/schools", "/landscape/synthpolicy26/schools"),
    RouteRequest(
        "GET", "/landscape/{caselist}/schools/{school}", "/landscape/synthpolicy26/schools/ashgrove"
    ),
    RouteRequest(
        "GET",
        "/landscape/{caselist}/positions/{position_id}",
        "/landscape/synthpolicy26/positions/invented-da",
    ),
    RouteRequest("GET", "/coach", "/coach"),
]

SESSION_FREE = {"/healthz", "/static/{digest}/{name}", "/auth/callback", "/signed-out"}
COACH_ONLY = {"/coach"}
PENDING_ENROLMENT_ONLY = {"/account/authenticator"}
"""A full session is sent to `/account` from these (PM ruling (d), 2026-10-20)."""


def send(world: Any, request: RouteRequest, csrf_token: str | None) -> Any:
    url = _script_url(world) if request.url == "<script>" else request.url
    url = url.replace("<card featured>", world.card_path("featured"))
    if request.method == "GET":
        return world.browser.get(url)
    return world.post(url, request.data, csrf_token=csrf_token or "no-session-token")


def sent_to_sign_in(response: Any) -> bool:
    return response.status_code == 302 and response.headers["location"].startswith(
        "https://auth.tub.example.test/oauth2/authorize?"
    )


def refused_by_the_gate(response: Any) -> bool:
    """A redirect to managed login, or a 401 or 403: what the gate answers instead of the route."""
    return sent_to_sign_in(response) or response.status_code in {401, 403}


# --------------------------------------------------------------------------------------------
# The sessions a browser can hold
# --------------------------------------------------------------------------------------------


def valid(world: Any, username: str) -> str | None:
    return world.sealed_session(world.session_for(username))


def expired(world: Any, username: str) -> str | None:
    """Twelve hours since sign-in, though seen a minute ago and just revalidated."""
    session = world.session_for(username)
    now = world.clock()
    return world.sealed_session(
        replace(
            session,
            started_at=now - timedelta(hours=12),
            last_seen_at=now - timedelta(minutes=1),
            revalidated_at=now - timedelta(minutes=1),
        )
    )


def idle(world: Any, username: str) -> str | None:
    """An hour without a request."""
    session = world.session_for(username)
    now = world.clock()
    return world.sealed_session(
        replace(session, started_at=now - timedelta(hours=2), last_seen_at=now - timedelta(minutes=60))
    )


def tampered(world: Any, username: str) -> str | None:
    """One character of the ciphertext changed."""
    sealed = world.sealed_session(world.session_for(username))
    position = len(sealed) // 2
    swapped = "A" if sealed[position] != "A" else "B"
    return sealed[:position] + swapped + sealed[position + 1 :]


def foreign_keys(world: Any, username: str) -> str | None:
    """A well-formed session sealed under keys this app does not hold."""
    other = CookieSealer(CookieKeys(current=os.urandom(32), previous=os.urandom(32)))
    return world.sealed_session(world.session_for(username), sealer=other)


def another_cookie(world: Any, username: str) -> str | None:
    """A session's fields sealed as the sign-in cookie: the cookie name is authenticated too."""
    return world.sealed_session(world.session_for(username), name=SIGN_IN_COOKIE)


def absent(world: Any, username: str) -> str | None:
    return None


NOT_A_SESSION: list[Callable[[Any, str], str | None]] = [
    expired,
    idle,
    tampered,
    foreign_keys,
    another_cookie,
    absent,
]


def with_cookie(world: Any, value: str | None) -> None:
    if value is not None:
        world.browser.cookies.set(SESSION_COOKIE, value, domain="tub.example.test")


@pytest.fixture(params=["student", "coach"])
def signed_up(request: pytest.FixtureRequest, world: Any) -> tuple[Any, str]:
    username = f"{request.param}.one"
    world.login.add_account(username, request.param)
    return world, username


# --------------------------------------------------------------------------------------------
# The matrix
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("route", ROUTE_REQUESTS, ids=lambda route: f"{route.method} {route.path}")
@pytest.mark.parametrize("session_state", NOT_A_SESSION, ids=lambda state: state.__name__)
def test_without_a_valid_session_only_the_four_session_free_routes_answer(
    signed_up: tuple[Any, str], route: RouteRequest, session_state: Callable[[Any, str], str | None]
) -> None:
    world, username = signed_up
    with_cookie(world, session_state(world, username))

    response = send(world, route, csrf_token=None)

    if route.path in SESSION_FREE:
        assert not refused_by_the_gate(response), (response.status_code, response.headers.get("location"))
    elif route.method == "GET":
        assert sent_to_sign_in(response), (response.status_code, response.headers.get("location"))
    else:
        assert response.status_code == 401
        assert response.json() == {"message": "You are signed out. Sign in again.", "location": "/"}


@pytest.mark.parametrize("route", ROUTE_REQUESTS, ids=lambda route: f"{route.method} {route.path}")
def test_with_a_valid_session_every_route_answers_but_coach_and_enrolment_routes_refuse(
    signed_up: tuple[Any, str], route: RouteRequest
) -> None:
    world, username = signed_up
    session = world.use_session(world.session_for(username))

    response = send(world, route, csrf_token=session.csrf_token)

    if route.path in COACH_ONLY and session.role.value == "student":
        assert response.status_code == 403
        assert "For the coach only" in response.text
    elif route.path in PENDING_ENROLMENT_ONLY and route.method == "GET":
        assert (response.status_code, response.headers.get("location")) == (303, "/account")
    elif route.path in PENDING_ENROLMENT_ONLY:
        assert response.status_code == 403
        assert response.json()["location"] == "/account"
    else:
        assert not refused_by_the_gate(response), (response.status_code, response.text[:200])


def test_a_session_that_ended_is_cleared_from_the_browser(world: Any) -> None:
    world.login.add_account("debater.one", "student")
    with_cookie(world, expired(world, "debater.one"))

    response = world.browser.get("/account")

    assert sent_to_sign_in(response)
    cleared = [
        header for header in response.headers.get_list("set-cookie") if header.startswith(SESSION_COOKIE)
    ]
    assert cleared and all("Max-Age=0" in header for header in cleared)


def test_a_path_no_route_claims_needs_a_session_too(world: Any) -> None:
    world.login.add_account("debater.one", "student")

    assert sent_to_sign_in(world.browser.get("/no-such-page"))
    assert sent_to_sign_in(world.browser.get("/static-but-not-static"))

    world.use_session(world.session_for("debater.one"))
    assert world.browser.get("/no-such-page").status_code == 404


# --------------------------------------------------------------------------------------------
# Exactly four session-free routes
# --------------------------------------------------------------------------------------------


def test_the_matrix_covers_every_route_the_app_serves(world: Any) -> None:
    served = {
        (method, route.path)
        for route in world.app.routes
        if isinstance(route, APIRoute)
        for method in route.methods or ()
    }

    assert served == {(request.method, request.path) for request in ROUTE_REQUESTS}


def test_exactly_four_routes_are_session_free() -> None:
    public = {path for path, access in ROUTE_ACCESS.items() if access is Access.PUBLIC}

    assert public == SESSION_FREE
    assert {"/healthz", "/auth/callback", "/signed-out"} == SESSION_FREE_PATHS


@pytest.mark.parametrize("path", ["/", "/account", "/auth/sign-in", "/status", "/healthz/details", "/coach"])
def test_no_other_route_can_be_registered_as_session_free(path: str) -> None:
    with pytest.raises(ValueError, match="cannot be session-free"):
        RouteAccess().register(path, Access.PUBLIC)


def test_every_route_says_what_access_it_needs(world: Any) -> None:
    paths = {route.path for route in world.app.routes if isinstance(route, APIRoute)}

    assert paths == set(ROUTE_ACCESS)

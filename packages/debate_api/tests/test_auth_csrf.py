"""CSRF on every state-changing request (ADR-0019 (d), CSRF), and sign-out.

A state-changing request is a POST carrying the session's CSRF token in `X-CSRF-Token`, an
`Origin` equal to the pilot's own and `Sec-Fetch-Site: same-origin`. Anything else is refused with
403 before the route runs. GET changes nothing, and the app sends no CORS headers.
"""

from __future__ import annotations

from typing import Any

import pytest

from debate_api.cookies import ALL_COOKIES

STATE_CHANGING = [
    ("/auth/sign-out", {}),
    ("/account/email", {"email": "debater.one@example.test"}),
    ("/account/email/verify", {"code": "135790"}),
    ("/account/email/remove", {}),
]
PATHS = [path for path, _ in STATE_CHANGING]


@pytest.fixture
def student(world: Any) -> tuple[Any, Any]:
    world.login.add_account("debater.one", "student")
    return world, world.use_session(world.session_for("debater.one"))


def changed_nothing(world: Any) -> bool:
    return world.self_service.calls == [] and world.login.revoked == [] and world.audit.records == []


@pytest.mark.parametrize(("path", "data"), STATE_CHANGING, ids=PATHS)
@pytest.mark.parametrize(
    "forgery",
    [
        {"csrf_token": None},
        {"csrf_token": "a-token-from-another-session"},
        {"csrf_token": ""},
        {"origin": None},
        {"origin": "https://evil.example"},
        {"origin": "https://tub.example.test.evil.example"},
        {"origin": "http://tub.example.test"},
        {"fetch_site": None},
        {"fetch_site": "cross-site"},
        {"fetch_site": "same-site"},
        {"fetch_site": "none"},
    ],
    ids=lambda forgery: "-".join(f"{key}={value}" for key, value in forgery.items()),
)
def test_a_forged_state_changing_request_is_refused_before_the_route_runs(
    student: tuple[Any, Any], path: str, data: dict[str, str], forgery: dict[str, Any]
) -> None:
    world, session = student
    arguments: dict[str, Any] = {"csrf_token": session.csrf_token, **forgery}

    response = world.post(path, data, **arguments)

    assert response.status_code == 403
    assert response.json() == {"message": "This request was refused. Reload the page and try again."}
    assert changed_nothing(world)


def test_another_sessions_token_is_refused(world: Any) -> None:
    world.login.add_account("debater.one", "student")
    world.login.add_account("debater.two", "student")
    theirs = world.session_for("debater.two")
    world.use_session(world.session_for("debater.one"))

    response = world.post(
        "/account/email", {"email": "debater.one@example.test"}, csrf_token=theirs.csrf_token
    )

    assert response.status_code == 403


@pytest.mark.parametrize("path", PATHS)
def test_get_never_reaches_a_state_changing_route(student: tuple[Any, Any], path: str) -> None:
    """A pending enrolment's confirm is CSRF-checked in `test_auth_enrolment.py`."""
    world, _ = student

    assert world.browser.get(path).status_code == 405
    assert changed_nothing(world)


def test_the_page_carries_the_token_app_js_sends(student: tuple[Any, Any]) -> None:
    world, session = student

    page = world.browser.get("/account")

    assert f'<meta name="tub-csrf" content="{session.csrf_token}">' in page.text


@pytest.mark.parametrize("method", ["OPTIONS", "GET"])
def test_the_app_sends_no_cors_headers(student: tuple[Any, Any], method: str) -> None:
    world, _ = student

    response = world.browser.request(
        method,
        "/account",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )

    assert not [name for name in response.headers if name.lower().startswith("access-control-")]


# --------------------------------------------------------------------------------------------
# Sign-out
# --------------------------------------------------------------------------------------------


def test_sign_out_revokes_the_refresh_token_clears_every_cookie_and_goes_through_logout(
    student: tuple[Any, Any],
) -> None:
    world, session = student

    response = world.post("/auth/sign-out", csrf_token=session.csrf_token)

    assert response.status_code == 200
    assert response.json() == {
        "location": "https://auth.tub.example.test/logout?client_id=synthetic-client-id"
        "&logout_uri=https%3A%2F%2Ftub.example.test%2Fsigned-out"
    }
    assert world.login.revoked == [session.refresh_token]
    cleared = {
        header.split("=", 1)[0] for header in response.headers.get_list("set-cookie") if "Max-Age=0" in header
    }
    assert cleared == set(ALL_COOKIES)
    assert world.browser.get("/").status_code == 302


def test_sign_out_still_clears_the_cookies_when_the_revocation_fails(student: tuple[Any, Any]) -> None:
    world, session = student
    world.login.post_form = lambda url, fields, *, headers: __import__(  # type: ignore[method-assign]
        "debate_core.integrations.cognito", fromlist=["HttpResponse"]
    ).HttpResponse(503, b"")

    response = world.post("/auth/sign-out", csrf_token=session.csrf_token)

    assert response.status_code == 200
    assert response.json()["location"].startswith("https://auth.tub.example.test/logout?")


def test_the_signed_out_page_needs_no_session_and_clears_the_cookies(world: Any) -> None:
    response = world.browser.get("/signed-out")

    assert response.status_code == 200
    assert "You are signed out" in response.text
    cleared = {
        header.split("=", 1)[0] for header in response.headers.get_list("set-cookie") if "Max-Age=0" in header
    }
    assert cleared == set(ALL_COOKIES)

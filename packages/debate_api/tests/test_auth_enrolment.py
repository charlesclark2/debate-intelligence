"""No session until an authenticator is registered (v1-e39-t05 ac6), and the email fallback.

A student who chose email at managed login's first setup has no authenticator. They get no
session: only a pending enrolment, which opens the app's own authenticator page and nothing else,
until a code from a new authenticator is confirmed. The one exception is an account the coach put
in `email-second-factor` whose email is verified (PM ruling, 2026-10-19).
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import pytest

from debate_api.cookies import ENROLMENT_COOKIE, SESSION_COOKIE

EMAIL = "debater.two@example.test"


def without_an_authenticator(world: Any, *groups: str, **settings: Any) -> Any:
    world.login.add_account("debater.two", *(groups or ("student",)), has_authenticator=False, **settings)
    return world


def confirm(world: Any, code: str) -> Any:
    enrolment = world.app.state.pilot.enrolment_in(_request_with_cookies(world))
    return world.post("/account/authenticator", {"code": code}, csrf_token=enrolment.csrf_token)


def _request_with_cookies(world: Any) -> Any:
    from starlette.requests import Request

    cookie = "; ".join(f"{name}={value}" for name, value in world.browser.cookies.items())
    return Request({"type": "http", "headers": [(b"cookie", cookie.encode())]})


# --------------------------------------------------------------------------------------------
# No authenticator: no session
# --------------------------------------------------------------------------------------------


def test_an_account_with_no_authenticator_gets_no_session(world: Any) -> None:
    without_an_authenticator(world)

    response = world.sign_in("debater.two", "/account")

    assert response.status_code == 303
    assert response.headers["location"] == "/account/authenticator"
    assert world.browser.cookies.get(SESSION_COOKIE) is None
    assert world.browser.cookies.get(ENROLMENT_COOKIE)


@pytest.mark.parametrize("path", ["/", "/account", "/coach"])
def test_a_pending_enrolment_opens_no_page_but_the_authenticator_page(world: Any, path: str) -> None:
    without_an_authenticator(world, "coach")
    world.sign_in("debater.two")

    response = world.browser.get(path)

    assert response.status_code == 303
    assert response.headers["location"] == "/account/authenticator"


@pytest.mark.parametrize("path", ["/account/email", "/account/email/verify", "/account/email/remove"])
def test_a_pending_enrolment_changes_nothing_but_the_authenticator(world: Any, path: str) -> None:
    without_an_authenticator(world)
    world.sign_in("debater.two")
    enrolment = world.app.state.pilot.enrolment_in(_request_with_cookies(world))

    response = world.post(path, {"email": EMAIL, "code": "135790"}, csrf_token=enrolment.csrf_token)

    assert response.status_code == 403
    assert response.json()["location"] == "/account/authenticator"
    assert "UpdateUserAttributes" not in world.self_service.operations()


def test_the_enrolment_page_shows_a_qr_code_and_the_setup_key(world: Any) -> None:
    without_an_authenticator(world)
    world.sign_in("debater.two")

    page = world.browser.get("/account/authenticator")

    assert page.status_code == 200
    assert "<svg" in page.text and 'class="segno"' in page.text
    assert "JBSW Y3DP EHPK 3PXP" in page.text
    assert page.headers["cache-control"] == "private, no-store"
    assert "AssociateSoftwareToken" in world.self_service.operations()


def test_a_wrong_code_starts_no_session(world: Any) -> None:
    without_an_authenticator(world)
    world.sign_in("debater.two")
    world.browser.get("/account/authenticator")

    response = confirm(world, "000000")

    assert response.status_code == 400
    assert response.json() == {
        "message": "That code was not accepted. Check the app and enter the newest code."
    }
    assert world.browser.cookies.get(SESSION_COOKIE) is None


def test_a_confirmed_authenticator_starts_the_session_and_returns_to_the_page_asked_for(world: Any) -> None:
    without_an_authenticator(world)
    world.sign_in("debater.two", "/account")
    world.browser.get("/account/authenticator")

    response = confirm(world, world.good_authenticator_code)

    assert response.status_code == 200
    assert response.json() == {"location": "/account"}
    session = world.session_cookie()
    assert session is not None and session.username == "debater.two"
    assert world.browser.cookies.get(ENROLMENT_COOKIE) is None
    assert world.login.accounts["debater.two"].has_authenticator
    assert world.browser.get("/account").status_code == 200
    assert [record.action.value for record in world.audit.records] == ["authenticator-registered"]


def test_a_confirmed_authenticator_with_a_verified_email_turns_on_both_factors(world: Any) -> None:
    without_an_authenticator(world, email=EMAIL, email_verified=True, email_factor=True)
    world.sign_in("debater.two")
    world.browser.get("/account/authenticator")

    confirm(world, world.good_authenticator_code)

    preference = [details for op, _, details in world.self_service.calls if op == "SetUserMFAPreference"]
    assert preference == [{"authenticator": True, "email": True}]


def test_the_secret_is_never_logged(world: Any, caplog: pytest.LogCaptureFixture) -> None:
    without_an_authenticator(world)
    caplog.set_level(logging.DEBUG)
    world.sign_in("debater.two")
    world.browser.get("/account/authenticator")
    confirm(world, world.good_authenticator_code)

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert world.authenticator_secret not in logged
    assert world.good_authenticator_code not in logged


def test_a_pending_enrolment_lasts_fifteen_minutes(world: Any) -> None:
    without_an_authenticator(world)
    world.sign_in("debater.two")
    world.clock.advance(timedelta(minutes=14, seconds=59))
    assert world.browser.get("/account/authenticator").status_code == 200

    world.clock.advance(timedelta(seconds=1))
    response = world.browser.get("/account/authenticator")

    assert response.status_code == 302 and response.headers["location"].startswith(world.authorize_url)


def test_a_pending_enrolment_can_sign_out(world: Any) -> None:
    without_an_authenticator(world)
    world.sign_in("debater.two")
    enrolment = world.app.state.pilot.enrolment_in(_request_with_cookies(world))

    response = world.post("/auth/sign-out", csrf_token=enrolment.csrf_token)

    assert response.status_code == 200
    assert response.json()["location"].startswith("https://auth.tub.example.test/logout?")
    assert world.browser.cookies.get(ENROLMENT_COOKIE) is None
    assert world.login.revoked == [enrolment.refresh_token]


# --------------------------------------------------------------------------------------------
# The email-second-factor fallback
# --------------------------------------------------------------------------------------------


def test_an_email_second_factor_account_with_a_verified_email_gets_a_session(world: Any) -> None:
    without_an_authenticator(
        world, "student", "email-second-factor", email=EMAIL, email_verified=True, email_factor=True
    )

    response = world.sign_in("debater.two", "/account")

    assert response.headers["location"] == "/account"
    session = world.session_cookie()
    assert session is not None and session.email_second_factor
    assert world.browser.get("/account").status_code == 200


def test_an_email_second_factor_account_without_a_verified_email_must_enrol(world: Any) -> None:
    without_an_authenticator(world, "student", "email-second-factor", email=EMAIL, email_verified=False)

    response = world.sign_in("debater.two")

    assert response.headers["location"] == "/account/authenticator"
    assert world.browser.cookies.get(SESSION_COOKIE) is None


def test_a_verified_email_alone_is_not_enough_outside_the_group(world: Any) -> None:
    without_an_authenticator(world, email=EMAIL, email_verified=True, email_factor=True)

    response = world.sign_in("debater.two")

    assert response.headers["location"] == "/account/authenticator"
    assert world.browser.cookies.get(SESSION_COOKIE) is None

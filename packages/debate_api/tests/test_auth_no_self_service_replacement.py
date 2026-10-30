"""No self-service authenticator replacement in the pilot (PM ruling (d), 2026-10-20, ac5 re-run).

On dev, `AssociateSoftwareToken` dropped an authenticator managed login had set up at once, which
is how most students enrol, and kept one the app had set up. A replacement left unfinished would
then leave enrolment open to anyone with the student's password. So a student with a new phone asks
the coach for a reset, whose temporary password comes from the coach.

`/account/authenticator` is for a pending enrolment only. A full session's GET goes to `/account`
and calls nothing in Cognito, its POST is refused, and no route a full session can reach calls
`AssociateSoftwareToken`.

Revalidation's second-factor check stays (deviation 4): a session whose account has lost its last
second factor ends, and the audit log records `session-ended-no-second-factor`.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import pytest
from fastapi.routing import APIRoute

from debate_core.application.errors import StoreError
from debate_core.application.tub.identity import Role

FORM = {"code": "424242", "email": "debater.one@example.test"}


@pytest.fixture
def world(auth_world: Any) -> Any:
    """This file's world: sign-in alone: no index, no sources and no landscape bundles (`v1-e39-t20`)."""
    return auth_world


@pytest.fixture
def student(world: Any) -> tuple[Any, Any]:
    world.login.add_account("debater.one", "student")
    return world, world.use_session(world.session_for("debater.one"))


def is_signed_out(response: Any, world: Any) -> bool:
    return response.status_code == 302 and response.headers["location"].startswith(world.authorize_url)


# --------------------------------------------------------------------------------------------
# The authenticator page is a pending enrolment's only
# --------------------------------------------------------------------------------------------


def test_a_full_sessions_get_goes_to_the_account_page_and_calls_nothing(student: tuple[Any, Any]) -> None:
    world, _ = student

    response = world.browser.get("/account/authenticator")

    assert response.status_code == 303
    assert response.headers["location"] == "/account"
    assert world.self_service.calls == []
    assert world.login.accounts["debater.one"].pending_secret is None
    assert "<svg" not in response.text


def test_a_full_sessions_confirm_is_refused_and_calls_nothing(student: tuple[Any, Any]) -> None:
    world, session = student

    response = world.post("/account/authenticator", {"code": "424242"}, csrf_token=session.csrf_token)

    assert response.status_code == 403
    assert response.json()["location"] == "/account"
    assert world.self_service.calls == []
    assert world.audit.records == []


def test_there_is_no_route_to_begin_a_replacement(student: tuple[Any, Any]) -> None:
    world, session = student

    response = world.post("/account/authenticator/begin", csrf_token=session.csrf_token)

    assert response.status_code == 404
    assert world.self_service.calls == []


def _every_request(world: Any) -> list[tuple[str, str]]:
    script = world.app.state.pilot.app_script.path
    return [
        (method, script if route.path == "/static/{digest}/app.js" else route.path)
        for route in world.app.routes
        if isinstance(route, APIRoute)
        for method in sorted(route.methods or ())
    ]


@pytest.mark.parametrize(
    "account",
    [
        {"groups": ("student",)},
        {"groups": ("coach",)},
        {
            "groups": ("student", "email-second-factor"),
            "has_authenticator": False,
            "email": "debater.one@example.test",
            "email_verified": True,
            "email_factor": True,
        },
    ],
    ids=["student", "coach", "email-second-factor"],
)
def test_no_route_a_full_session_can_reach_calls_associate_software_token(
    world: Any, account: dict[str, Any]
) -> None:
    """The test that holds ruling (d): every route the app serves, asked as a full session."""
    settings = {name: value for name, value in account.items() if name != "groups"}
    world.login.add_account("debater.one", *account["groups"], **settings)

    for method, path in _every_request(world):
        session = world.use_session(world.session_for("debater.one"))
        if method == "GET":
            response = world.browser.get(path)
        else:
            response = world.post(path, FORM, csrf_token=session.csrf_token)
        assert response.status_code != 401 and not is_signed_out(response, world), (method, path)

    assert "AssociateSoftwareToken" not in world.self_service.operations()


def test_a_pending_enrolment_still_begins_on_the_get(world: Any) -> None:
    world.login.add_account("debater.two", "student", has_authenticator=False)
    world.sign_in("debater.two")

    page = world.browser.get("/account/authenticator")

    assert "<svg" in page.text
    assert "AssociateSoftwareToken" in world.self_service.operations()


# --------------------------------------------------------------------------------------------
# A session whose account lost its last second factor
# --------------------------------------------------------------------------------------------


def lose_the_authenticator(world: Any) -> None:
    """What a coach's reset leaves behind, without the global sign-out that ends the session sooner."""
    world.login.accounts["debater.one"].has_authenticator = False


def test_a_session_ended_for_want_of_a_second_factor_is_recorded(student: tuple[Any, Any]) -> None:
    world, session = student
    lose_the_authenticator(world)
    world.clock.advance(timedelta(minutes=5))

    assert is_signed_out(world.browser.get("/account"), world)

    [ended] = world.audit.records
    assert ended.action.value == "session-ended-no-second-factor"
    assert ended.time == world.clock()
    assert ended.actor_role is Role.STUDENT
    assert ended.actor_subject == ended.account_subject == session.subject
    assert "debater.one" not in ended.to_json()


def test_a_session_ended_for_another_reason_records_nothing(student: tuple[Any, Any]) -> None:
    world, _ = student
    world.login.disable("debater.one")
    world.clock.advance(timedelta(minutes=5))

    assert is_signed_out(world.browser.get("/account"), world)
    assert world.audit.records == []


def test_a_session_end_that_cannot_be_recorded_still_ends_the_session(
    student: tuple[Any, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    world, _ = student
    lose_the_authenticator(world)
    world.clock.advance(timedelta(minutes=5))

    def unreachable(record: Any) -> None:
        raise StoreError("the audit log did not answer")

    monkeypatch.setattr(world.audit, "record", unreachable)

    assert is_signed_out(world.browser.get("/account"), world)


def test_a_lost_session_end_record_is_logged_once_without_a_name_or_subject(
    student: tuple[Any, Any], monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Second PM review, 2026-10-20: a dropped record leaves one WARNING naming its action."""
    world, session = student
    lose_the_authenticator(world)
    world.clock.advance(timedelta(minutes=5))

    def unreachable(record: Any) -> None:
        raise StoreError("the audit log did not answer")

    monkeypatch.setattr(world.audit, "record", unreachable)

    with caplog.at_level(logging.WARNING):
        world.browser.get("/account")

    [warning] = [record for record in caplog.records if record.levelno >= logging.WARNING]
    assert warning.levelno == logging.WARNING
    assert "session-ended-no-second-factor" in warning.getMessage()
    logged = warning.getMessage() + repr(warning.args)
    assert "debater.one" not in logged
    assert session.subject not in logged

"""Replacing an authenticator starts with a POST (PM review of v1-e39-t05, 2026-10-20).

The session cookie is `SameSite=Lax`, so a cross-site link to a page reaches it with the session.
For a full session, `GET /account/authenticator` therefore changes nothing and calls nothing in
Cognito: it shows a *Start* button, a POST to `/account/authenticator/begin` through the CSRF,
`Origin` and `Sec-Fetch-Site` checks, and only that POST begins a new secret. A pending enrolment
keeps the GET that begins one, because it has no authenticator to lose and the callback's 303 lands
there.

*Start* drops the old authenticator at once, so the account has no second factor until the new one
is confirmed. *Start* therefore counts as the session's revalidation: the student has five minutes
to confirm, and with no confirmation the session ends at the first revalidation after that. Both
ends are in the audit log (PM ruling, 2026-10-20).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from debate_core.application.errors import StoreError
from debate_core.application.tub.identity import Role

BEGIN = "/account/authenticator/begin"


@pytest.fixture
def student(world: Any) -> tuple[Any, Any]:
    world.login.add_account("debater.one", "student")
    return world, world.use_session(world.session_for("debater.one"))


def test_the_page_for_a_full_session_calls_nothing_in_cognito(student: tuple[Any, Any]) -> None:
    world, _ = student

    page = world.browser.get("/account/authenticator")

    assert page.status_code == 200
    assert world.self_service.calls == []
    assert world.login.accounts["debater.one"].pending_secret is None
    assert f'<form method="post" action="{BEGIN}">' in page.text
    assert "<svg" not in page.text
    assert world.authenticator_secret not in page.text


def test_start_begins_a_new_secret_and_shows_its_qr_code(student: tuple[Any, Any]) -> None:
    world, session = student

    response = world.post(BEGIN, csrf_token=session.csrf_token)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["cache-control"] == "private, no-store"
    assert "<svg" in response.text and "JBSW Y3DP EHPK 3PXP" in response.text
    assert 'action="/account/authenticator"' in response.text
    assert world.self_service.operations().count("AssociateSoftwareToken") == 1


def test_start_then_a_confirmed_code_replaces_the_authenticator(student: tuple[Any, Any]) -> None:
    world, session = student
    world.browser.get("/account/authenticator")
    world.post(BEGIN, csrf_token=session.csrf_token)

    response = world.post(
        "/account/authenticator", {"code": world.good_authenticator_code}, csrf_token=session.csrf_token
    )

    assert response.json() == {"location": "/account?done=authenticator-replaced"}
    assert [record.action.value for record in world.audit.records] == [
        "authenticator-replacement-started",
        "authenticator-registered",
    ]


@pytest.mark.parametrize(
    "forgery",
    [
        {"csrf_token": None},
        {"csrf_token": "a-token-from-another-session"},
        {"origin": "https://evil.example"},
        {"origin": None},
        {"fetch_site": "cross-site"},
        {"fetch_site": None},
    ],
    ids=lambda forgery: "-".join(f"{key}={value}" for key, value in forgery.items()),
)
def test_a_forged_start_is_refused_before_cognito_is_asked(
    student: tuple[Any, Any], forgery: dict[str, Any]
) -> None:
    world, session = student

    response = world.post(BEGIN, **{"csrf_token": session.csrf_token, **forgery})

    assert response.status_code == 403
    assert world.self_service.calls == []


def test_start_is_for_a_full_session_only(world: Any) -> None:
    """A pending enrolment's page already began its secret; it has no Start to press."""
    world.login.add_account("debater.two", "student", has_authenticator=False)
    world.sign_in("debater.two")
    world.self_service.calls.clear()
    from debate_api.cookies import ENROLMENT_COOKIE, enrolment_from_payload

    enrolment = enrolment_from_payload(
        world.sealer.open(ENROLMENT_COOKIE, world.browser.cookies.get(ENROLMENT_COOKIE))
    )

    assert enrolment is not None

    response = world.post(BEGIN, csrf_token=enrolment.csrf_token)

    assert response.status_code == 403
    assert response.json()["location"] == "/account/authenticator"
    assert "AssociateSoftwareToken" not in world.self_service.operations()


def test_a_pending_enrolment_still_begins_on_the_get(world: Any) -> None:
    world.login.add_account("debater.two", "student", has_authenticator=False)
    world.sign_in("debater.two")

    page = world.browser.get("/account/authenticator")

    assert "<svg" in page.text
    assert BEGIN not in page.text
    assert "AssociateSoftwareToken" in world.self_service.operations()


# --------------------------------------------------------------------------------------------
# Start counts as a revalidation
# --------------------------------------------------------------------------------------------


@pytest.fixture
def late_student(student: tuple[Any, Any]) -> tuple[Any, Any]:
    """A session last revalidated 4:55 ago, so its next revalidation is due five seconds from now."""
    world, session = student
    world.clock.advance(timedelta(minutes=4, seconds=55))
    return world, session


def refreshes(world: Any) -> int:
    return sum(1 for request in world.login.token_requests if request["grant_type"] == "refresh_token")


def is_signed_out(response: Any, world: Any) -> bool:
    return response.status_code == 302 and response.headers["location"].startswith(world.authorize_url)


def test_a_revalidation_due_seconds_after_start_does_not_end_the_session(
    late_student: tuple[Any, Any],
) -> None:
    world, session = late_student
    assert world.post(BEGIN, csrf_token=session.csrf_token).status_code == 200
    world.clock.advance(timedelta(seconds=10))

    page = world.browser.get("/account/authenticator")

    assert page.status_code == 200
    assert world.session_cookie().revalidated_at == world.clock() - timedelta(seconds=10)


def test_a_confirm_4_59_after_start_succeeds(late_student: tuple[Any, Any]) -> None:
    world, session = late_student
    world.post(BEGIN, csrf_token=session.csrf_token)
    world.clock.advance(timedelta(minutes=4, seconds=59))

    response = world.post(
        "/account/authenticator", {"code": world.good_authenticator_code}, csrf_token=session.csrf_token
    )

    assert response.json() == {"location": "/account?done=authenticator-replaced"}
    assert world.login.accounts["debater.one"].has_authenticator


def test_with_no_confirm_the_session_ends_at_the_first_revalidation_after_five_minutes(
    late_student: tuple[Any, Any],
) -> None:
    world, session = late_student
    world.post(BEGIN, csrf_token=session.csrf_token)
    world.clock.advance(timedelta(minutes=4, seconds=59))
    assert world.browser.get("/account/authenticator").status_code == 200
    before = refreshes(world)
    world.clock.advance(timedelta(seconds=1))

    response = world.browser.get("/account/authenticator")

    assert is_signed_out(response, world)
    assert refreshes(world) == before + 1
    assert world.session_cookie() is None


def test_a_forged_start_does_not_count_as_a_revalidation(late_student: tuple[Any, Any]) -> None:
    world, session = late_student
    assert world.post(BEGIN, csrf_token=None).status_code == 403
    before = refreshes(world)
    world.clock.advance(timedelta(seconds=10))

    world.browser.get("/")

    assert refreshes(world) == before + 1
    assert world.session_cookie().revalidated_at == world.clock()


def test_start_rechecks_the_role_as_a_revalidation_does(student: tuple[Any, Any]) -> None:
    world, session = student
    world.login.accounts["debater.one"].groups = set()

    response = world.post(BEGIN, csrf_token=session.csrf_token)

    assert response.status_code == 401
    assert "AssociateSoftwareToken" not in world.self_service.operations()
    assert world.login.accounts["debater.one"].has_authenticator


def test_start_on_an_account_signed_out_elsewhere_changes_nothing(student: tuple[Any, Any]) -> None:
    world, session = student
    world.login.sign_out_everywhere("debater.one")

    response = world.post(BEGIN, csrf_token=session.csrf_token)

    assert response.status_code == 401
    assert world.self_service.calls == []
    assert world.audit.records == []


# --------------------------------------------------------------------------------------------
# The audit records
# --------------------------------------------------------------------------------------------


def test_start_records_authenticator_replacement_started(student: tuple[Any, Any]) -> None:
    world, session = student

    world.post(BEGIN, csrf_token=session.csrf_token)

    [record] = world.audit.records
    assert record.action.value == "authenticator-replacement-started"
    assert record.actor_role is Role.STUDENT
    assert record.actor_subject == record.account_subject == session.subject
    assert "debater.one" not in record.to_json()


def test_a_session_ended_for_want_of_a_second_factor_is_recorded(student: tuple[Any, Any]) -> None:
    world, session = student
    world.post(BEGIN, csrf_token=session.csrf_token)
    world.clock.advance(timedelta(minutes=5))

    assert is_signed_out(world.browser.get("/account"), world)

    started, ended = world.audit.records
    assert started.action.value == "authenticator-replacement-started"
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


def test_a_start_that_cannot_be_recorded_keeps_the_old_authenticator(
    student: tuple[Any, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    world, session = student

    def unreachable(record: Any) -> None:
        raise StoreError("the audit log did not answer")

    monkeypatch.setattr(world.audit, "record", unreachable)

    response = world.post(BEGIN, csrf_token=session.csrf_token)

    assert response.status_code == 503
    assert "AssociateSoftwareToken" not in world.self_service.operations()
    assert world.login.accounts["debater.one"].has_authenticator


def test_a_session_end_that_cannot_be_recorded_still_ends_the_session(
    student: tuple[Any, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    world, session = student
    world.post(BEGIN, csrf_token=session.csrf_token)
    world.clock.advance(timedelta(minutes=5))

    def unreachable(record: Any) -> None:
        raise StoreError("the audit log did not answer")

    monkeypatch.setattr(world.audit, "record", unreachable)

    assert is_signed_out(world.browser.get("/account"), world)

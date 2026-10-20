"""Replacing an authenticator starts with a POST (PM review of v1-e39-t05, 2026-10-20).

The session cookie is `SameSite=Lax`, so a cross-site link to a page reaches it with the session.
For a full session, `GET /account/authenticator` therefore changes nothing and calls nothing in
Cognito: it shows a *Start* button, a POST to `/account/authenticator/begin` through the CSRF,
`Origin` and `Sec-Fetch-Site` checks, and only that POST begins a new secret. A pending enrolment
keeps the GET that begins one, because it has no authenticator to lose and the callback's 303 lands
there.
"""

from __future__ import annotations

from typing import Any

import pytest

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
    assert [record.action.value for record in world.audit.records] == ["authenticator-registered"]


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

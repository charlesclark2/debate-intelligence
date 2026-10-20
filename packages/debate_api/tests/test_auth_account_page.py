"""The account page (v1-e39-t05 ac6): add, verify and remove the backup email; replace the authenticator.

Each change goes through the student's own access token, redeemed for the change and dropped, and
each completed one writes one audit record with the student's subject and no address.
"""

from __future__ import annotations

from typing import Any

import pytest

EMAIL = "debater.one@example.test"


@pytest.fixture
def student(world: Any) -> tuple[Any, Any]:
    world.login.add_account("debater.one", "student")
    session = world.use_session(world.session_for("debater.one"))
    return world, session


def post(world: Any, session: Any, path: str, data: dict[str, str] | None = None) -> Any:
    return world.post(path, data, csrf_token=session.csrf_token)


def actions(world: Any) -> list[str]:
    return [record.action.value for record in world.audit.records]


# --------------------------------------------------------------------------------------------
# The backup email
# --------------------------------------------------------------------------------------------


def test_the_page_offers_to_add_a_backup_email(student: tuple[Any, Any]) -> None:
    world, _ = student

    page = world.browser.get("/account")

    assert page.status_code == 200
    assert 'action="/account/email"' in page.text
    assert "Your authenticator app is set up" in page.text


def test_adding_an_email_sets_it_unverified_and_records_nothing_yet(student: tuple[Any, Any]) -> None:
    world, session = student

    response = post(world, session, "/account/email", {"email": EMAIL})

    assert response.json() == {"location": "/account?done=email-sent"}
    account = world.login.accounts["debater.one"]
    assert (account.email, account.email_verified) == (EMAIL, False)
    assert world.audit.records == []
    page = world.browser.get("/account?done=email-sent")
    assert "We sent a code to that address" in page.text
    assert 'action="/account/email/verify"' in page.text


def test_verifying_the_email_turns_on_both_factors_with_neither_preferred(student: tuple[Any, Any]) -> None:
    world, session = student
    post(world, session, "/account/email", {"email": EMAIL})

    response = post(world, session, "/account/email/verify", {"code": world.good_email_code})

    assert response.json() == {"location": "/account?done=email-confirmed"}
    assert world.login.accounts["debater.one"].email_verified
    preference = [details for op, _, details in world.self_service.calls if op == "SetUserMFAPreference"]
    assert preference == [{"authenticator": True, "email": True}]
    assert actions(world) == ["backup-email-added"]


def test_a_wrong_email_code_verifies_nothing(student: tuple[Any, Any]) -> None:
    world, session = student
    post(world, session, "/account/email", {"email": EMAIL})

    response = post(world, session, "/account/email/verify", {"code": "000000"})

    assert response.status_code == 400
    assert response.json() == {
        "message": "That code was not accepted. Check the email and enter the newest code."
    }
    assert not world.login.accounts["debater.one"].email_verified
    assert world.audit.records == []


@pytest.mark.parametrize("code", ["12345", "1234567", "abcdef", ""])
def test_a_code_that_is_not_six_digits_is_refused_before_cognito_is_asked(
    student: tuple[Any, Any], code: str
) -> None:
    world, session = student
    post(world, session, "/account/email", {"email": EMAIL})

    response = post(world, session, "/account/email/verify", {"code": code})

    assert response.status_code == 400
    assert "VerifyUserAttribute" not in world.self_service.operations()


@pytest.mark.parametrize(
    "email", ["not an address", "debater@", "@example.test", "a@b", "x" * 250 + "@example.test"]
)
def test_something_that_is_not_an_email_is_refused_and_not_repeated(
    student: tuple[Any, Any], email: str
) -> None:
    world, session = student

    response = post(world, session, "/account/email", {"email": email})

    assert response.status_code == 400
    assert response.json() == {"message": "That is not an email address."}
    assert "UpdateUserAttributes" not in world.self_service.operations()


def test_removing_the_email_turns_the_email_factor_off_first(student: tuple[Any, Any]) -> None:
    world, session = student
    account = world.login.accounts["debater.one"]
    account.email, account.email_verified, account.email_factor = EMAIL, True, True

    response = post(world, session, "/account/email/remove")

    assert response.json() == {"location": "/account?done=email-removed"}
    operations = world.self_service.operations()
    assert operations.index("SetUserMFAPreference") < operations.index("DeleteUserAttributes")
    assert account.email is None and not account.email_factor
    assert actions(world) == ["backup-email-removed"]


def test_an_email_that_is_the_only_second_factor_cannot_be_removed(world: Any) -> None:
    world.login.add_account(
        "debater.two",
        "student",
        "email-second-factor",
        has_authenticator=False,
        email="debater.two@example.test",
        email_verified=True,
        email_factor=True,
    )
    session = world.use_session(world.session_for("debater.two"))

    page = world.browser.get("/account")
    response = post(world, session, "/account/email/remove")

    assert 'action="/account/email/remove"' not in page.text
    assert "Ask your coach" in page.text
    assert response.status_code == 400
    assert "ask the coach" in response.json()["message"]
    assert world.login.accounts["debater.two"].email == "debater.two@example.test"
    assert world.audit.records == []


def test_the_audit_record_names_no_address_and_no_username(student: tuple[Any, Any]) -> None:
    world, session = student
    post(world, session, "/account/email", {"email": EMAIL})
    post(world, session, "/account/email/verify", {"code": world.good_email_code})
    post(world, session, "/account/email/remove")

    for record in world.audit.records:
        line = record.to_json()
        assert EMAIL not in line and "debater.one" not in line
        assert record.actor_subject == record.account_subject == session.subject


# --------------------------------------------------------------------------------------------
# Replacing the authenticator
# --------------------------------------------------------------------------------------------


def test_the_start_page_warns_that_the_old_authenticator_stops_at_once(student: tuple[Any, Any]) -> None:
    """ac5 step 4 on dev, 2026-10-20: after Start, Cognito listed no authenticator on the account."""
    world, _ = student

    page = world.browser.get("/account/authenticator")

    assert "your current authenticator app stops working at once" in page.text
    assert "finish in one sitting" in page.text


def test_the_start_page_says_what_to_do_if_signed_out_or_asked_unexpectedly(
    student: tuple[Any, Any],
) -> None:
    """PM ruling, 2026-10-20: the same two lines as the guide's."""
    world, _ = student

    page = world.browser.get("/account/authenticator")

    assert (
        "If you are signed out partway through, sign in again straight away and finish setting up "
        "the authenticator app." in page.text
    )
    assert (
        "If the sign-in page ever asks you to set up an authenticator when you did not choose "
        "<strong>Start</strong>, tell the coach." in page.text
    )


def test_after_start_the_qr_page_says_the_old_authenticator_has_stopped(student: tuple[Any, Any]) -> None:
    world, session = student

    page = post(world, session, "/account/authenticator/begin")

    assert page.status_code == 200
    assert "Your old authenticator app has stopped working" in page.text
    assert "keeps working" not in page.text
    assert not world.login.accounts["debater.one"].has_authenticator


def test_the_account_page_says_the_old_app_stops_when_you_start(student: tuple[Any, Any]) -> None:
    world, _ = student

    page = world.browser.get("/account")

    assert "stops working as soon as you choose Start" in page.text


def test_a_confirmed_new_authenticator_replaces_the_old_one(student: tuple[Any, Any]) -> None:
    world, session = student
    post(world, session, "/account/authenticator/begin")

    response = post(world, session, "/account/authenticator", {"code": world.good_authenticator_code})

    assert response.json() == {"location": "/account?done=authenticator-replaced"}
    assert (
        "VerifySoftwareToken",
        "debater.one",
        {"code": world.good_authenticator_code},
    ) in world.self_service.calls
    assert actions(world) == ["authenticator-replacement-started", "authenticator-registered"]
    assert (
        "Your new authenticator app is set up"
        in world.browser.get("/account?done=authenticator-replaced").text
    )


def test_an_unknown_notice_is_not_shown(student: tuple[Any, Any]) -> None:
    world, _ = student

    page = world.browser.get("/account?done=%3Cscript%3Ealert(1)%3C/script%3E")

    assert "alert(1)" not in page.text
    assert 'role="status"' not in page.text.split("<main>")[1].split("<h2>")[0]


def test_a_change_after_the_account_was_signed_out_ends_the_session(student: tuple[Any, Any]) -> None:
    world, session = student
    world.login.sign_out_everywhere("debater.one")

    response = post(world, session, "/account/email", {"email": EMAIL})

    assert response.status_code == 401
    assert response.json()["location"] == "/"
    assert world.session_cookie() is None

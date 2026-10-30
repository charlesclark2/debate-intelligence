"""The session's lifetimes, revalidation and keys (ADR-0019 (d); v1-e39-t05 ac6, the disable bound).

| Lifetime | Value |
|---|---|
| Idle timeout | 60 minutes without a request |
| Absolute session lifetime | 12 hours from sign-in |
| Revalidation | at most every 5 minutes |

A coach's disable signs the account out everywhere, so its refresh token stops working, and the
session ends at the next revalidation: within five minutes.
"""

from __future__ import annotations

import base64
import json
import os
from datetime import timedelta
from typing import Any

import pytest

from debate_api.configuration import CookieKeys, CookieKeysNotSet, parse_cookie_keys
from debate_api.cookies import SESSION_COOKIE, CookieSealer, session_payload


@pytest.fixture
def world(auth_world: Any) -> Any:
    """This file's world: sign-in alone: no index, no sources and no landscape bundles (`v1-e39-t20`)."""
    return auth_world


def signed_in(world: Any, username: str = "debater.one", *groups: str) -> Any:
    world.login.add_account(username, *(groups or ("student",)))
    response = world.sign_in(username)
    assert response.status_code == 303
    return world


def is_signed_in(world: Any, path: str = "/") -> bool:
    response = world.browser.get(path)
    return response.status_code == 200


def refreshes(world: Any) -> int:
    return sum(1 for request in world.login.token_requests if request["grant_type"] == "refresh_token")


# --------------------------------------------------------------------------------------------
# Idle and absolute lifetimes
# --------------------------------------------------------------------------------------------


def test_a_request_within_the_hour_keeps_the_session_alive(world: Any) -> None:
    signed_in(world)
    for _ in range(4):
        world.clock.advance(timedelta(minutes=59))
        assert is_signed_in(world)


def test_an_hour_without_a_request_ends_the_session(world: Any) -> None:
    signed_in(world)
    world.clock.advance(timedelta(minutes=60))

    assert not is_signed_in(world)


def test_twelve_hours_after_sign_in_the_session_ends_however_active(world: Any) -> None:
    signed_in(world)
    for _ in range(23):
        world.clock.advance(timedelta(minutes=30))
        assert is_signed_in(world)
    world.clock.advance(timedelta(minutes=30))

    assert not is_signed_in(world)


def test_the_cookie_does_not_outlive_the_absolute_lifetime(world: Any) -> None:
    signed_in(world)
    for _ in range(21):
        world.clock.advance(timedelta(minutes=30))
        world.browser.get("/")
    world.clock.advance(timedelta(minutes=30))

    response = world.browser.get("/")

    header = next(h for h in response.headers.get_list("set-cookie") if h.startswith(SESSION_COOKIE))
    assert "Max-Age=3600" in header


# --------------------------------------------------------------------------------------------
# Revalidation
# --------------------------------------------------------------------------------------------


def test_within_five_minutes_no_revalidation_is_made(world: Any) -> None:
    signed_in(world)
    world.clock.advance(timedelta(minutes=4, seconds=59))

    assert is_signed_in(world)
    assert refreshes(world) == 0


def test_after_five_minutes_the_refresh_token_is_redeemed_again(world: Any) -> None:
    signed_in(world)
    world.clock.advance(timedelta(minutes=5))

    assert is_signed_in(world)
    assert refreshes(world) == 1
    world.clock.advance(timedelta(minutes=1))
    assert is_signed_in(world)
    assert refreshes(world) == 1


def test_a_disabled_accounts_session_ends_within_five_minutes(world: Any) -> None:
    signed_in(world)
    world.clock.advance(timedelta(minutes=1))
    world.login.disable("debater.one")

    world.clock.advance(timedelta(minutes=3, seconds=59))
    assert is_signed_in(world), "revalidation is at most every five minutes, not on every request"
    world.clock.advance(timedelta(seconds=1))
    response = world.browser.get("/")

    assert response.status_code == 302 and response.headers["location"].startswith(world.authorize_url)
    assert world.session_cookie() is None


@pytest.mark.parametrize("ending", ["removed", "reset", "signed out everywhere"])
def test_a_removed_or_reset_accounts_session_ends_at_the_next_revalidation(world: Any, ending: str) -> None:
    signed_in(world)
    if ending == "removed":
        del world.login.accounts["debater.one"]
    elif ending == "reset":
        world.login.accounts["debater.one"].has_authenticator = False
        world.login.sign_out_everywhere("debater.one")
    else:
        world.login.sign_out_everywhere("debater.one")
    world.clock.advance(timedelta(minutes=5))

    assert not is_signed_in(world)


def test_a_role_taken_away_takes_effect_at_the_next_revalidation(world: Any) -> None:
    signed_in(world, "coach.one", "coach")
    assert world.browser.get("/coach").status_code == 200
    world.login.accounts["coach.one"].groups = {"student"}

    world.clock.advance(timedelta(minutes=5))

    assert world.browser.get("/coach").status_code == 403
    assert world.session_cookie().role.value == "student"


def test_an_account_left_with_no_role_loses_its_session(world: Any) -> None:
    signed_in(world)
    world.login.accounts["debater.one"].groups = set()
    world.clock.advance(timedelta(minutes=5))

    assert not is_signed_in(world)


def test_an_account_whose_authenticator_went_and_has_no_email_factor_loses_its_session(world: Any) -> None:
    signed_in(world)
    world.login.accounts["debater.one"].has_authenticator = False
    world.clock.advance(timedelta(minutes=5))

    assert not is_signed_in(world)


def test_an_email_second_factor_withdrawn_takes_effect_at_the_next_revalidation(world: Any) -> None:
    world.login.add_account(
        "debater.two",
        "student",
        "email-second-factor",
        has_authenticator=False,
        email="debater.two@example.test",
        email_verified=True,
        email_factor=True,
    )
    world.sign_in("debater.two")
    assert is_signed_in(world)
    world.login.accounts["debater.two"].groups = {"student"}
    world.clock.advance(timedelta(minutes=5))

    assert not is_signed_in(world)


# --------------------------------------------------------------------------------------------
# Keys
# --------------------------------------------------------------------------------------------


def test_a_cookie_sealed_with_the_previous_key_still_opens(world: Any) -> None:
    world.login.add_account("debater.one", "student")
    session = world.session_for("debater.one")
    before_rotation = CookieSealer(CookieKeys(current=world.cookie_keys.previous, previous=os.urandom(32)))
    world.browser.cookies.set(
        SESSION_COOKIE,
        before_rotation.seal(SESSION_COOKIE, session_payload(session)),
        domain="tub.example.test",
    )

    assert is_signed_in(world)


def test_a_session_cookie_stays_well_under_four_kilobytes(world: Any) -> None:
    """Cognito's refresh tokens are about 1,800 characters; the session must still fit one cookie."""
    from dataclasses import replace

    world.login.add_account("a.thirty.two.character.username", "student")
    session = replace(world.session_for("a.thirty.two.character.username"), refresh_token="r" * 2000)

    assert len(SESSION_COOKIE) + 1 + len(world.sealed_session(session)) < 3800


def _keys(**values: object) -> str:
    return json.dumps(values)


def _key() -> str:
    return base64.b64encode(os.urandom(32)).decode()


@pytest.mark.parametrize(
    "raw",
    [
        _keys(placeholder="Not a key. Write the real keys with the runbook's put-parameter step."),
        _keys(current=_key()),
        _keys(current=_key(), previous=_key(), spare=_key()),
        _keys(current=_key(), previous=base64.b64encode(os.urandom(16)).decode()),
        _keys(current="not base64 !", previous=_key()),
        _keys(current=7, previous=_key()),
        "not json",
        "[]",
    ],
    ids=[
        "placeholder",
        "one-key",
        "extra-key",
        "short-key",
        "not-base64",
        "not-a-string",
        "not-json",
        "not-object",
    ],
)
def test_cookie_keys_that_are_not_two_32_byte_keys_are_refused(raw: str) -> None:
    with pytest.raises(CookieKeysNotSet):
        parse_cookie_keys(raw)


def test_two_32_byte_keys_are_accepted() -> None:
    current, previous = os.urandom(32), os.urandom(32)

    keys = parse_cookie_keys(
        _keys(current=base64.b64encode(current).decode(), previous=base64.b64encode(previous).decode())
    )

    assert (keys.current, keys.previous) == (current, previous)
    assert "current" not in repr(keys) or base64.b64encode(current).decode() not in repr(keys)


def test_the_app_refuses_to_start_on_the_placeholder_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """`create_app()` as uvicorn calls it, with Parameter Store holding Terraform's placeholder."""
    import debate_api.container as container
    from debate_api.app import create_app

    parameters = {
        "/debate-dev-tub/cookie-keys": _keys(placeholder="Not a key."),
        "/debate-dev-tub/client-secret": "synthetic-client-secret",
    }
    monkeypatch.setattr(container, "build_ssm_client", lambda *, region: object())
    monkeypatch.setattr(container, "read_secure_parameter", lambda client, name: parameters[name])
    for name, value in {
        "TUB_ENVIRONMENT": "dev",
        "TUB_PUBLIC_ORIGIN": "https://tub.example.test",
        "TUB_LOGIN_ORIGIN": "https://auth.tub.example.test",
        "TUB_USER_POOL_ID": "us-east-1_SyntheticPool",
        "TUB_CLIENT_ID": "synthetic-client-id",
        "TUB_CLIENT_SECRET_PARAMETER": "/debate-dev-tub/client-secret",
        "TUB_COOKIE_KEYS_PARAMETER": "/debate-dev-tub/cookie-keys",
        "TUB_AUDIT_LOG_GROUP": "debate-dev-tub-audit",
        "TUB_EVIDENCE_BUCKET": "debate-dev-evidence-synthetic",
    }.items():
        monkeypatch.setenv(name, value)

    with pytest.raises(CookieKeysNotSet, match="placeholder"):
        create_app()

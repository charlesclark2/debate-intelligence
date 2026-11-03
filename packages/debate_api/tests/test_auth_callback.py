"""The sign-in callback (v1-e39-t05 ac2): what it accepts, and everything it refuses.

The ID tokens are RS256 tokens signed with a key generated for the test and checked by the real
verifier against the key set the fake managed login publishes. Managed login's half of PKCE is
played by the fake as Cognito plays it: a code issued for a challenge is redeemed only with the
verifier that hashes to it.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

from debate_api.cookies import ENROLMENT_COOKIE, SESSION_COOKIE, SIGN_IN_COOKIE, transaction_payload


@pytest.fixture
def world(auth_world: Any) -> Any:
    """This file's world: sign-in alone: no index, no sources and no landscape bundles (`v1-e39-t20`)."""
    return auth_world


def query_of(url: str) -> dict[str, str]:
    return {name: values[0] for name, values in parse_qs(urlsplit(url).query).items()}


def set_cookie_names(response: Any) -> dict[str, str]:
    """The cookies a response sets, by name, with their attributes; a cleared one ends `Max-Age=0`."""
    return {header.split("=", 1)[0]: header for header in response.headers.get_list("set-cookie")}


def assert_not_signed_in(world: Any, response: Any) -> None:
    assert response.status_code == 400
    assert "Sign-in did not finish" in response.text
    assert world.session_cookie() is None
    assert (
        SESSION_COOKIE not in set_cookie_names(response)
        or "Max-Age=0" in set_cookie_names(response)[SESSION_COOKIE]
    )
    assert world.browser.cookies.get(ENROLMENT_COOKIE) is None


@pytest.fixture
def debater(world: Any) -> Any:
    world.login.add_account("debater.one", "student")
    return world


# --------------------------------------------------------------------------------------------
# What a good answer does
# --------------------------------------------------------------------------------------------


def test_the_redirect_carries_state_nonce_and_an_s256_challenge(debater: Any) -> None:
    query = query_of(debater.start_sign_in("/account"))

    assert query["response_type"] == "code"
    assert query["client_id"] == debater.client_id
    assert query["redirect_uri"] == "https://tub.example.test/auth/callback"
    assert query["scope"] == "openid aws.cognito.signin.user.admin"
    assert query["code_challenge_method"] == "S256"
    assert len(query["code_challenge"]) == 43
    assert len(query["state"]) >= 43 and len(query["nonce"]) >= 43
    sign_in_cookie = debater.browser.cookies.get(SIGN_IN_COOKIE)
    assert sign_in_cookie and query["state"] not in sign_in_cookie


def test_a_good_answer_starts_a_session_and_returns_to_the_page_asked_for(debater: Any) -> None:
    response = debater.sign_in("debater.one", "/account?done=email-sent")

    assert response.status_code == 303
    assert response.headers["location"] == "/account?done=email-sent"
    session = debater.session_cookie()
    assert session is not None and session.username == "debater.one" and session.role.value == "student"
    cookies = set_cookie_names(response)
    assert "Max-Age=0" in cookies[SIGN_IN_COOKIE]
    exchange = debater.login.token_requests[-1]
    assert exchange["grant_type"] == "authorization_code"
    assert exchange["redirect_uri"] == "https://tub.example.test/auth/callback"
    assert len(exchange["code_verifier"]) >= 43


def test_the_session_cookie_is_host_prefixed_secure_http_only_and_lax(debater: Any) -> None:
    header = set_cookie_names(debater.sign_in("debater.one"))[SESSION_COOKIE]

    attributes = {part.strip().split("=")[0].lower() for part in header.split(";")[1:]}
    assert SESSION_COOKIE.startswith("__Host-")
    assert {"secure", "httponly", "path", "samesite", "max-age"} <= attributes
    assert "domain" not in attributes
    assert "Path=/" in header and "SameSite=lax" in header
    assert "Max-Age=43200" in header


def test_no_token_is_readable_in_the_cookie(debater: Any) -> None:
    debater.sign_in("debater.one")

    cookie = debater.browser.cookies.get(SESSION_COOKIE)
    assert cookie.startswith("v1.")
    for token in [*debater.login.refresh_tokens, *debater.login.access_tokens]:
        assert token not in cookie
    assert "debater.one" not in cookie


def test_a_coach_is_signed_in_as_a_coach(world: Any) -> None:
    world.login.add_account("coach.one", "coach", "student")

    world.sign_in("coach.one")

    assert world.session_cookie().role.value == "coach"
    assert world.browser.get("/coach").status_code == 200


@pytest.mark.parametrize(
    "return_to", ["//evil.example/", "/\\evil.example", "https://evil.example/", "/\x00x"]
)
def test_a_return_path_off_the_site_becomes_the_home_page(debater: Any, return_to: str) -> None:
    """The gate records only the path it was asked for; this starts a transaction for a worse one."""
    transaction, url = debater.services.sign_in.begin(return_to)
    debater.browser.cookies.set(
        SIGN_IN_COOKIE,
        debater.sealer.seal(SIGN_IN_COOKIE, transaction_payload(transaction)),
        domain="tub.example.test",
    )

    response = debater.callback(debater.login.authorize(url, "debater.one"))

    assert response.headers["location"] == "/"


# --------------------------------------------------------------------------------------------
# The transaction: state, its age, and the browser that started it
# --------------------------------------------------------------------------------------------


def test_a_mismatched_state_is_refused(debater: Any) -> None:
    answer = debater.login.authorize(debater.start_sign_in(), "debater.one")

    response = debater.callback({**answer, "state": "not-the-state-this-browser-was-given"})

    assert_not_signed_in(debater, response)
    assert debater.login.token_requests == []


def test_an_answer_without_state_is_refused(debater: Any) -> None:
    answer = debater.login.authorize(debater.start_sign_in(), "debater.one")

    assert_not_signed_in(debater, debater.callback({"code": answer["code"]}))


def test_an_answer_in_a_browser_that_started_no_sign_in_is_refused(debater: Any) -> None:
    answer = debater.login.authorize(debater.start_sign_in(), "debater.one")
    other_browser = debater.new_browser()

    response = debater.callback(answer, browser=other_browser)

    assert response.status_code == 400
    assert other_browser.cookies.get(SESSION_COOKIE) is None


def test_an_answer_after_five_minutes_is_refused(debater: Any) -> None:
    answer = debater.login.authorize(debater.start_sign_in(), "debater.one")
    debater.clock.advance(timedelta(minutes=5))

    assert_not_signed_in(debater, debater.callback(answer))


def test_an_error_from_managed_login_is_refused(debater: Any) -> None:
    answer = debater.login.authorize(debater.start_sign_in(), "debater.one")

    assert_not_signed_in(debater, debater.callback({**answer, "error": "access_denied"}))


def test_a_code_cannot_be_used_twice(debater: Any) -> None:
    answer = debater.login.authorize(debater.start_sign_in(), "debater.one")
    debater.callback(answer)
    debater.browser.cookies.clear()
    debater.start_sign_in()

    replay = debater.callback(answer)

    assert replay.status_code == 400


# --------------------------------------------------------------------------------------------
# PKCE
# --------------------------------------------------------------------------------------------


def test_a_code_issued_for_another_browsers_challenge_is_refused(debater: Any) -> None:
    """Code injection: a code bound to browser B's verifier, delivered to browser A's callback."""
    browser_b = debater.new_browser()
    code_for_b = debater.login.authorize(debater.start_sign_in(browser=browser_b), "debater.one")["code"]
    state_for_a = debater.login.authorize(debater.start_sign_in(), "debater.one")["state"]

    response = debater.callback({"code": code_for_b, "state": state_for_a})

    assert_not_signed_in(debater, response)
    assert debater.login.token_requests[-1]["grant_type"] == "authorization_code"


def test_the_verifier_sent_is_the_one_whose_hash_was_the_challenge(debater: Any) -> None:
    import base64
    import hashlib

    url = debater.start_sign_in()
    challenge = query_of(url)["code_challenge"]

    debater.callback(debater.login.authorize(url, "debater.one"))

    verifier = debater.login.token_requests[-1]["code_verifier"]
    digest = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    assert digest == challenge
    assert debater.session_cookie() is not None


# --------------------------------------------------------------------------------------------
# The ID token
# --------------------------------------------------------------------------------------------

BAD_ID_TOKENS = {
    "from another pool": {"iss": "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_AnotherPool"},
    "for another app client": {"aud": "another-client-id"},
    "already expired": {"exp": 0},
    "an access token": {"token_use": "access"},
    "for another sign-in": {"nonce": "a-nonce-this-browser-never-sent"},
    "with no subject": {"sub": ""},
}


@pytest.mark.parametrize("changes", BAD_ID_TOKENS.values(), ids=BAD_ID_TOKENS.keys())
def test_an_id_token_that_fails_a_check_is_refused(debater: Any, changes: dict[str, object]) -> None:
    debater.login.claim_changes = changes

    assert_not_signed_in(debater, debater.sign_in("debater.one"))


def test_an_id_token_signed_by_a_key_the_pool_does_not_publish_is_refused(debater: Any) -> None:
    debater.login.sign_with_an_unpublished_key()

    assert_not_signed_in(debater, debater.sign_in("debater.one"))


def test_an_id_token_naming_the_pools_key_but_signed_by_another_is_refused(debater: Any) -> None:
    debater.login.sign_with_an_impostor_key()

    assert_not_signed_in(debater, debater.sign_in("debater.one"))


def test_an_id_token_with_its_claims_altered_after_signing_is_refused(debater: Any) -> None:
    original = debater.login.signing_key.sign

    def altered(claims: dict[str, object], **kwargs: Any) -> str:
        head, _, signature = original(claims, **kwargs).split(".")
        import base64
        import json

        forged = {**claims, "cognito:groups": ["coach"]}
        body = base64.urlsafe_b64encode(json.dumps(forged).encode()).rstrip(b"=").decode()
        return f"{head}.{body}.{signature}"

    debater.login.signing_key.sign = altered  # type: ignore[method-assign]

    assert_not_signed_in(debater, debater.sign_in("debater.one"))


@pytest.mark.parametrize("algorithm", ["none", "HS256"])
def test_an_id_token_not_signed_with_rs256_is_refused(debater: Any, algorithm: str) -> None:
    original = debater.login.signing_key.sign
    debater.login.signing_key.sign = lambda claims, **_: original(  # type: ignore[method-assign]
        claims, header={"alg": algorithm, "kid": "synthetic-key-1"}
    )

    assert_not_signed_in(debater, debater.sign_in("debater.one"))


def test_an_account_in_no_role_group_is_not_signed_in(world: Any) -> None:
    world.login.add_account("debater.two", "email-second-factor")

    response = world.sign_in("debater.two")

    assert response.status_code == 400
    assert "Ask your coach" in response.text
    assert world.session_cookie() is None

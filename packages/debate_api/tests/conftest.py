"""A test world for the pilot app: the real app, the real use cases and the real OAuth adapter.

Only two things are stand-ins, and both answer as Cognito would:

* :class:`FakeManagedLogin` is the HTTPS transport the real
  :class:`~debate_core.integrations.cognito.CognitoOAuthClient` and
  :class:`~debate_core.integrations.cognito.PublishedKeySet` talk to. It plays managed login's
  `/oauth2/authorize` (by hand, through :meth:`FakeManagedLogin.authorize`), `/oauth2/token` and
  `/oauth2/revoke`, and the pool's key set. Its ID tokens are RS256 tokens signed with an RSA key
  generated for the test, so the real :class:`~debate_core.integrations.cognito.CognitoIdTokenVerifier`
  checks every one of them, and a test can change any claim or sign with another key.
* :class:`FakeSelfService` is the token-authorized API over the same accounts.

Every name, address, code and secret here is synthetic. No test reaches a network: the app runs
in-process through Starlette's test client.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.padding import PKCS1v15
from cryptography.hazmat.primitives.hashes import SHA256
from starlette.testclient import TestClient

from debate_api.app import create_app
from debate_api.configuration import CookieKeys, PilotConfiguration
from debate_api.cookies import SESSION_COOKIE, CookieSealer, session_payload
from debate_api.state import PilotServices
from debate_core.application.ports.tub import AccountSelfService, AccountStanding, CodeRefused, TokenRefused
from debate_core.application.tub.account_page import AccountPageService
from debate_core.application.tub.audit import AuditRecord
from debate_core.application.tub.identity import AuthenticatorSecret, Role
from debate_core.application.tub.sessions import Session
from debate_core.application.tub.sign_in import SignInService
from debate_core.integrations.cognito import (
    CognitoIdTokenVerifier,
    CognitoOAuthClient,
    HttpResponse,
    HttpTransport,
    PublishedKeySet,
    issuer_for,
)

REGION = "us-east-1"
POOL_ID = "us-east-1_SyntheticPool"
CLIENT_ID = "synthetic-client-id"
CLIENT_SECRET = "synthetic-client-secret"
PUBLIC_ORIGIN = "https://tub.example.test"
LOGIN_ORIGIN = "https://auth.tub.example.test"
ISSUER = issuer_for(REGION, POOL_ID)
AUTHORIZE_URL = f"{LOGIN_ORIGIN}/oauth2/authorize"
START = datetime(2026, 11, 2, 15, 0, tzinfo=UTC)

AUTHENTICATOR_SECRET = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"
"""A synthetic base32 secret, the shape AssociateSoftwareToken returns."""
GOOD_AUTHENTICATOR_CODE = "424242"
GOOD_EMAIL_CODE = "135790"


class MutableClock:
    def __init__(self, start: datetime = START) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


@dataclass
class FakeAccount:
    username: str
    subject: str
    groups: set[str]
    has_authenticator: bool = True
    email: str | None = None
    email_verified: bool = False
    email_factor: bool = False
    enabled: bool = True
    generation: int = 0
    """Bumped by a global sign-out: every refresh and access token issued before it stops working."""
    pending_secret: str | None = None
    pending_email: str | None = None


_PRIVATE_KEYS: dict[str, rsa.RSAPrivateKey] = {}


def _private_key(key_id: str) -> rsa.RSAPrivateKey:
    """One RSA key per key id for the whole run: generating one takes longer than a test."""
    if key_id not in _PRIVATE_KEYS:
        _PRIVATE_KEYS[key_id] = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return _PRIVATE_KEYS[key_id]


@dataclass
class SigningKey:
    key_id: str
    """The `kid` its tokens name."""
    material: str | None = None
    """Which generated key actually signs; another than `key_id`'s makes an impostor."""

    @property
    def private_key(self) -> rsa.RSAPrivateKey:
        return _private_key(self.material or self.key_id)

    def jwk(self) -> dict[str, str]:
        numbers = self.private_key.public_key().public_numbers()
        return {
            "kid": self.key_id,
            "kty": "RSA",
            "alg": "RS256",
            "use": "sig",
            "n": _b64url(numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")),
            "e": _b64url(numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, "big")),
        }

    def sign(self, claims: Mapping[str, object], *, header: Mapping[str, object] | None = None) -> str:
        head = _b64url(json.dumps(header or {"alg": "RS256", "kid": self.key_id}).encode())
        body = _b64url(json.dumps(claims).encode())
        signature = self.private_key.sign(f"{head}.{body}".encode(), PKCS1v15(), SHA256())
        return f"{head}.{body}.{_b64url(signature)}"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


@dataclass
class IssuedCode:
    username: str
    code_challenge: str | None
    code_challenge_method: str | None
    nonce: str | None
    redirect_uri: str


class FakeManagedLogin(HttpTransport):
    """Managed login's OAuth endpoints and the pool's key set, answering as Cognito does."""

    def __init__(self, clock: MutableClock) -> None:
        self.clock = clock
        self.published_key = SigningKey("synthetic-key-1")
        self.signing_key = self.published_key
        self.accounts: dict[str, FakeAccount] = {}
        self.codes: dict[str, IssuedCode] = {}
        self.refresh_tokens: dict[str, tuple[str, int]] = {}
        self.access_tokens: dict[str, tuple[str, int]] = {}
        self.claim_changes: dict[str, object] = {}
        """Applied to every ID token issued from now on: another issuer, audience, expiry..."""
        self.token_requests: list[dict[str, str]] = []
        self.revoked: list[str] = []

    # Accounts --------------------------------------------------------------------------------

    def add_account(self, username: str, *groups: str, **settings: Any) -> FakeAccount:
        account = FakeAccount(
            username=username,
            subject=f"sub-{secrets.token_hex(8)}",
            groups=set(groups or ("student",)),
            **settings,
        )
        self.accounts[username] = account
        return account

    def sign_out_everywhere(self, username: str) -> None:
        self.accounts[username].generation += 1

    def disable(self, username: str) -> None:
        self.sign_out_everywhere(username)
        self.accounts[username].enabled = False

    def sign_with_an_unpublished_key(self) -> None:
        """Issue ID tokens signed by a key the pool's key set does not list."""
        self.signing_key = SigningKey("synthetic-key-unpublished")

    def sign_with_an_impostor_key(self) -> None:
        """Issue ID tokens that name the published key's id but are signed by another key."""
        self.signing_key = SigningKey("synthetic-key-1", material="synthetic-key-impostor")

    def account_for_access_token(self, access_token: str) -> FakeAccount:
        username, generation = self.access_tokens.get(access_token, ("", -1))
        account = self.accounts.get(username)
        if account is None or not account.enabled or account.generation != generation:
            raise TokenRefused("the access token is no longer accepted")
        return account

    # /oauth2/authorize, played by the test ---------------------------------------------------

    def authorize(self, authorization_url: str, username: str) -> dict[str, str]:
        """What managed login redirects back with once `username` has signed in: a code and the state."""
        parts = urlsplit(authorization_url)
        assert f"{parts.scheme}://{parts.netloc}{parts.path}" == AUTHORIZE_URL
        query = {name: values[0] for name, values in parse_qs(parts.query).items()}
        assert query["client_id"] == CLIENT_ID
        code = secrets.token_urlsafe(16)
        self.codes[code] = IssuedCode(
            username=username,
            code_challenge=query.get("code_challenge"),
            code_challenge_method=query.get("code_challenge_method"),
            nonce=query.get("nonce"),
            redirect_uri=query["redirect_uri"],
        )
        return {"code": code, "state": query["state"]}

    # The HTTPS transport ---------------------------------------------------------------------

    def get(self, url: str) -> HttpResponse:
        assert url == f"{ISSUER}/.well-known/jwks.json"
        return HttpResponse(200, json.dumps({"keys": [self.published_key.jwk()]}).encode())

    def post_form(self, url: str, fields: Mapping[str, str], *, headers: Mapping[str, str]) -> HttpResponse:
        expected = "Basic " + base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
        if headers.get("Authorization") != expected:
            return _oauth_error(401, "invalid_client")
        if url == f"{LOGIN_ORIGIN}/oauth2/revoke":
            self.revoked.append(fields["token"])
            self.refresh_tokens.pop(fields["token"], None)
            return HttpResponse(200, b"")
        assert url == f"{LOGIN_ORIGIN}/oauth2/token"
        self.token_requests.append(dict(fields))
        if fields.get("grant_type") == "authorization_code":
            return self._exchange(fields)
        if fields.get("grant_type") == "refresh_token":
            return self._refresh(fields)
        return _oauth_error(400, "unsupported_grant_type")

    def _exchange(self, fields: Mapping[str, str]) -> HttpResponse:
        issued = self.codes.pop(fields.get("code", ""), None)
        if issued is None or issued.redirect_uri != fields.get("redirect_uri"):
            return _oauth_error(400, "invalid_grant")
        if issued.code_challenge is not None:
            verifier = fields.get("code_verifier", "")
            digest = _b64url(hashlib.sha256(verifier.encode()).digest())
            if issued.code_challenge_method != "S256" or digest != issued.code_challenge:
                return _oauth_error(400, "invalid_grant")
        account = self.accounts[issued.username]
        refresh_token = f"refresh-{secrets.token_hex(12)}"
        self.refresh_tokens[refresh_token] = (account.username, account.generation)
        return self._tokens(account, nonce=issued.nonce, refresh_token=refresh_token)

    def _refresh(self, fields: Mapping[str, str]) -> HttpResponse:
        username, generation = self.refresh_tokens.get(fields.get("refresh_token", ""), ("", -1))
        account = self.accounts.get(username)
        if account is None or not account.enabled or account.generation != generation:
            return _oauth_error(400, "invalid_grant")
        return self._tokens(account, nonce=None, refresh_token=None)

    def _tokens(self, account: FakeAccount, *, nonce: str | None, refresh_token: str | None) -> HttpResponse:
        now = int(self.clock().timestamp())
        claims: dict[str, object] = {
            "iss": ISSUER,
            "aud": CLIENT_ID,
            "token_use": "id",
            "sub": account.subject,
            "cognito:username": account.username,
            "cognito:groups": sorted(account.groups),
            "iat": now,
            "exp": now + 300,
        }
        if nonce is not None:
            claims["nonce"] = nonce
        claims.update(self.claim_changes)
        access_token = f"access-{secrets.token_hex(12)}"
        self.access_tokens[access_token] = (account.username, account.generation)
        body: dict[str, object] = {
            "id_token": self.signing_key.sign(claims),
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": 300,
        }
        if refresh_token is not None:
            body["refresh_token"] = refresh_token
        return HttpResponse(200, json.dumps(body).encode())

    def issue_refresh_token(self, username: str) -> str:
        account = self.accounts[username]
        token = f"refresh-{secrets.token_hex(12)}"
        self.refresh_tokens[token] = (username, account.generation)
        return token


def _oauth_error(status: int, error: str) -> HttpResponse:
    return HttpResponse(status, json.dumps({"error": error, "error_description": "synthetic"}).encode())


class FakeSelfService(AccountSelfService):
    """The token-authorized API over :class:`FakeManagedLogin`'s accounts, recording each call."""

    def __init__(self, login: FakeManagedLogin) -> None:
        self.login = login
        self.calls: list[tuple[str, str, dict[str, object]]] = []

    def _account(self, operation: str, access_token: str, **details: object) -> FakeAccount:
        account = self.login.account_for_access_token(access_token)
        self.calls.append((operation, account.username, details))
        return account

    def standing(self, access_token: str) -> AccountStanding:
        account = self._account("GetUser", access_token)
        return AccountStanding(
            has_authenticator=account.has_authenticator,
            email=account.email,
            email_verified=account.email_verified,
            email_factor_enabled=account.email_factor,
        )

    def begin_authenticator(self, access_token: str) -> AuthenticatorSecret:
        """As Cognito does it (measured on dev, 2026-10-20): the current authenticator goes at once.

        After `AssociateSoftwareToken`, `AdminGetUser` listed no MFA setting at all, and the next
        sign-in asked for authenticator setup.
        """
        account = self._account("AssociateSoftwareToken", access_token)
        account.pending_secret = AUTHENTICATOR_SECRET
        account.has_authenticator = False
        return AuthenticatorSecret(AUTHENTICATOR_SECRET)

    def confirm_authenticator(self, access_token: str, code: str) -> None:
        account = self._account("VerifySoftwareToken", access_token, code=code)
        if account.pending_secret is None or code != GOOD_AUTHENTICATOR_CODE:
            raise CodeRefused("authenticator")
        account.pending_secret = None
        account.has_authenticator = True

    def set_second_factors(self, access_token: str, *, authenticator: bool, email: bool) -> None:
        account = self._account(
            "SetUserMFAPreference", access_token, authenticator=authenticator, email=email
        )
        account.email_factor = email

    def set_backup_email(self, access_token: str, email: str) -> None:
        account = self._account("UpdateUserAttributes", access_token, email=email)
        account.email, account.email_verified = email, False

    def confirm_backup_email(self, access_token: str, code: str) -> None:
        account = self._account("VerifyUserAttribute", access_token, code=code)
        if account.email is None or code != GOOD_EMAIL_CODE:
            raise CodeRefused("email")
        account.email_verified = True

    def remove_backup_email(self, access_token: str) -> None:
        account = self._account("DeleteUserAttributes", access_token)
        account.email, account.email_verified = None, False

    def operations(self) -> list[str]:
        return [operation for operation, _, _ in self.calls]


class FakeAuditSink:
    def __init__(self) -> None:
        self.records: list[AuditRecord] = []

    def record(self, record: AuditRecord) -> None:
        self.records.append(record)


def configuration() -> PilotConfiguration:
    return PilotConfiguration(
        environment="dev",
        public_origin=PUBLIC_ORIGIN,
        login_origin=LOGIN_ORIGIN,
        user_pool_id=POOL_ID,
        client_id=CLIENT_ID,
        client_secret_parameter="/debate-dev-tub/client-secret",
        cookie_keys_parameter="/debate-dev-tub/cookie-keys",
        audit_log_group="debate-dev-tub-audit",
    )


def new_cookie_keys() -> CookieKeys:
    return CookieKeys(current=os.urandom(32), previous=os.urandom(32))


class PilotWorld:
    """The app over the fakes, a browser for it, and helpers to sign in or plant a session."""

    public_origin = PUBLIC_ORIGIN
    login_origin = LOGIN_ORIGIN
    authorize_url = AUTHORIZE_URL
    issuer = ISSUER
    client_id = CLIENT_ID
    good_authenticator_code = GOOD_AUTHENTICATOR_CODE
    good_email_code = GOOD_EMAIL_CODE
    authenticator_secret = AUTHENTICATOR_SECRET

    def __init__(self) -> None:
        self.clock = MutableClock()
        self.login = FakeManagedLogin(self.clock)
        self.self_service = FakeSelfService(self.login)
        self.audit = FakeAuditSink()
        self.cookie_keys = new_cookie_keys()
        self.sealer = CookieSealer(self.cookie_keys)
        identity_provider = CognitoOAuthClient(
            login_origin=LOGIN_ORIGIN,
            public_origin=PUBLIC_ORIGIN,
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            id_tokens=CognitoIdTokenVerifier(
                issuer=ISSUER,
                client_id=CLIENT_ID,
                key_set=PublishedKeySet(issuer=ISSUER, transport=self.login),
                clock=self.clock,
            ),
            transport=self.login,
        )
        self.services = PilotServices(
            configuration=configuration(),
            cookie_keys=self.cookie_keys,
            sign_in=SignInService(
                identity_provider=identity_provider, self_service=self.self_service, clock=self.clock
            ),
            account_page=AccountPageService(
                identity_provider=identity_provider,
                self_service=self.self_service,
                audit=self.audit,
                clock=self.clock,
                authenticator_issuer="Team evidence search (dev)",
            ),
            clock=self.clock,
        )
        self.app = create_app(self.services)
        self.browser = self.new_browser()

    def new_browser(self) -> TestClient:
        return TestClient(self.app, base_url=PUBLIC_ORIGIN, follow_redirects=False)

    # Signing in through the real flow --------------------------------------------------------

    def start_sign_in(self, path: str = "/", *, browser: TestClient | None = None) -> str:
        """Ask for `path` without a session; return the managed login URL the app sent the browser to."""
        response = (browser or self.browser).get(path)
        assert response.status_code == 302, response.text
        location = response.headers["location"]
        assert location.startswith(AUTHORIZE_URL)
        return location

    def callback(self, answer: Mapping[str, str], *, browser: TestClient | None = None) -> Any:
        return (browser or self.browser).get("/auth/callback", params=dict(answer))

    def sign_in(self, username: str, path: str = "/", *, browser: TestClient | None = None) -> Any:
        """The whole flow: the redirect, managed login's answer for `username`, and the callback."""
        authorization_url = self.start_sign_in(path, browser=browser)
        return self.callback(self.login.authorize(authorization_url, username), browser=browser)

    # Planting a session directly -------------------------------------------------------------

    def session_for(self, username: str, **changes: Any) -> Session:
        account = self.login.accounts[username]
        session = Session(
            subject=account.subject,
            username=username,
            role=Role.COACH if "coach" in account.groups else Role.STUDENT,
            email_second_factor="email-second-factor" in account.groups,
            started_at=self.clock(),
            last_seen_at=self.clock(),
            revalidated_at=self.clock(),
            csrf_token=secrets.token_urlsafe(32),
            refresh_token=self.login.issue_refresh_token(username),
        )
        return replace(session, **changes)

    def sealed_session(
        self, session: Session, *, sealer: CookieSealer | None = None, name: str = SESSION_COOKIE
    ) -> str:
        return (sealer or self.sealer).seal(name, session_payload(session))

    def use_session(self, session: Session, *, browser: TestClient | None = None) -> Session:
        (browser or self.browser).cookies.set(
            SESSION_COOKIE, self.sealed_session(session), domain="tub.example.test"
        )
        return session

    def session_cookie(self, browser: TestClient | None = None) -> Session | None:
        from debate_api.cookies import session_from_payload

        value = (browser or self.browser).cookies.get(SESSION_COOKIE)
        return session_from_payload(self.sealer.open(SESSION_COOKIE, value))

    # Requests the way app.js sends them ------------------------------------------------------

    def post(
        self,
        path: str,
        data: Mapping[str, str] | None = None,
        *,
        csrf_token: str | None,
        origin: str | None = PUBLIC_ORIGIN,
        fetch_site: str | None = "same-origin",
        browser: TestClient | None = None,
    ) -> Any:
        body = "&".join(f"{name}={value}" for name, value in (data or {}).items()).encode()
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "x-amz-content-sha256": hashlib.sha256(body).hexdigest(),
        }
        if csrf_token is not None:
            headers["X-CSRF-Token"] = csrf_token
        if origin is not None:
            headers["Origin"] = origin
        if fetch_site is not None:
            headers["Sec-Fetch-Site"] = fetch_site
        return (browser or self.browser).post(path, content=body, headers=headers)


@pytest.fixture
def world() -> PilotWorld:
    return PilotWorld()


@pytest.fixture
def make_world() -> Callable[[], PilotWorld]:
    return PilotWorld

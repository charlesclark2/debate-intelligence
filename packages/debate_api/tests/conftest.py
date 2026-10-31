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

The world is split by surface (v1-e39-t20), so that a change selects only the tests it reaches
(`scripts/affected_tests.py` reads this file fixture by fixture). :class:`PilotWorld` is sign-in
alone: no index is published, no source is stored and no landscape bundle is listed. Each surface
adds its own pieces, and a test file names the one it needs in its own `world` fixture:

* `search_world` (:class:`SearchWorld`). The search pages (v1-e39-t06) run over a real index: the
  `search_corpus` fixture, built once by `v1-e39-t02`'s writer, published in memory by
  :mod:`debate_core.testing.search_index`, and fetched by the real
  :class:`~debate_core.application.search_index_holder.SearchIndexHolder` into the world's own
  directory, so a page test goes through the same download, digest checks and read-only open the
  function does.
* `download_world` (:class:`DownloadWorld`). The download (v1-e39-t08) runs over real sources: the
  `download_sources` fixture, synthetic Verbatim files built in memory, parsed by the real parser,
  and put in :class:`RecordingSourceStore` stand-ins for the bucket's `raw/caselist/hsld26` and
  `raw/openev/2026`. Their cards are documents of the `download_corpus` fixture like any other, so
  the real E33 writer builds a downloaded file from them, and that index is published under the
  running parser's version.
* `landscape_world` (:class:`LandscapeWorld`). The landscape pages (v1-e39-t17) read
  :class:`InMemoryLandscapeObjects`, which lists and reads the hand-written bundles under
  `fixtures/landscape/` as the bucket's `reports/landscape/` would; their own tests also put them in
  a moto bucket and read them through the real `S3EvidenceObjectStore`.
* `auth_world` is :class:`PilotWorld` itself, and `every_surface_world`
  (:class:`EverySurfaceWorld`) all of them at once, for the tests that walk every route.

Nothing is built at import: the corpora, the parser and the sources are session-scoped fixtures,
built the first time a test asks for them.

Every name, address, code, secret, tag, cite and card here is synthetic. No test reaches a network:
the app runs in-process through Starlette's test client.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import tempfile
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from functools import cache, partial
from pathlib import Path
from typing import Any, Final
from urllib.parse import parse_qs, quote_plus, urlsplit

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.padding import PKCS1v15
from cryptography.hazmat.primitives.hashes import SHA256
from jsonschema import Draft202012Validator
from starlette.testclient import TestClient

from debate_api.app import create_app
from debate_api.configuration import CookieKeys, PilotConfiguration
from debate_api.cookies import SESSION_COOKIE, CookieSealer, session_payload
from debate_api.landscape_markdown import RenderedBundle, render_bundle
from debate_api.state import PilotServices
from debate_core.application.card_download import (
    DEFAULT_DOWNLOAD_CARD_CAP,
    DEFAULT_DOWNLOAD_SOURCE_XML_BYTES,
    DOWNLOAD_FETCH_MAX_BYTES,
    CardDownloadService,
    WriterFactory,
)
from debate_core.application.errors import BlobIntegrityError, NotFound, StoreUnavailable
from debate_core.application.evidence_search import EvidenceSearchService
from debate_core.application.ports.evidence_file_writer import EvidenceFileWriter
from debate_core.application.ports.evidence_store import ObjectInfo, ObjectKey
from debate_core.application.ports.persistence import BlobKey, SnapshotStore
from debate_core.application.ports.search_index import IndexedOccurrence, SearchDocument
from debate_core.application.ports.search_index_source import PointerRead
from debate_core.application.ports.suppression import disclosure_digest
from debate_core.application.ports.tub import AccountSelfService, AccountStanding, CodeRefused, TokenRefused
from debate_core.application.search_index_build import cite_without_cutter_mark
from debate_core.application.search_index_holder import ClosableSearchIndexReader, SearchIndexHolder
from debate_core.application.tub.access_audit import AccessAuditService
from debate_core.application.tub.account_page import AccountPageService
from debate_core.application.tub.audit import AuditRecord
from debate_core.application.tub.identity import AuthenticatorSecret, Role
from debate_core.application.tub.landscape_pages import LandscapeObjects, LandscapeShelf
from debate_core.application.tub.sessions import Session
from debate_core.application.tub.sign_in import SignInService
from debate_core.domain.caselist import SourceDocument, SourceFormat, SourceOrigin
from debate_core.domain.debate_files import FontSizeSpan, FormattingSpan, ParsedCard, ParsedDocument
from debate_core.domain.search_index import SEARCH_INDEX_POINTER_KEY, read_aloud_text
from debate_core.domain.style_profile import RunEmphasis, StyleMatchSource
from debate_core.integrations.cognito import (
    CognitoIdTokenVerifier,
    CognitoOAuthClient,
    HttpResponse,
    HttpTransport,
    PublishedKeySet,
)
from debate_core.integrations.docx_file_writer.writer import DocxEvidenceFileWriter
from debate_core.integrations.docx_parser.package import declared_document_bytes
from debate_core.integrations.docx_parser.parser import DebateDocxParser
from debate_core.integrations.local.search_index import SqliteSearchIndexWriter
from debate_core.integrations.local.search_index_reader import SqliteSearchIndexReader
from debate_core.testing.docx_builder import build_docx, paragraph_xml, run_xml
from debate_core.testing.search_index import InMemorySearchIndexSource, PublishedIndex, published_index

REGION = "us-east-1"
POOL_ID = "us-east-1_SyntheticPool"
CLIENT_ID = "synthetic-client-id"
CLIENT_SECRET = "synthetic-client-secret"
PUBLIC_ORIGIN = "https://tub.example.test"
LOGIN_ORIGIN = "https://auth.tub.example.test"
ISSUER = f"https://cognito-idp.{REGION}.amazonaws.com/{POOL_ID}"
"""What `issuer_for` builds, written out: a constant that called it would make every test here need it."""
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


AUDIT_RECORD_SCHEMA: Final = (
    Path(__file__).resolve().parents[3] / "docs" / "data" / "tub-audit-record.schema.json"
)


@cache
def audit_record_validator() -> Draft202012Validator:
    """The committed schema every audit record must meet (`v1-e39-t07`)."""
    schema = json.loads(AUDIT_RECORD_SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


class FakeAuditSink:
    """The audit log in memory. With `failing` set, every write raises as an unreachable log group would.

    Every record is checked against the committed schema as it is written, so every test that makes
    the app write one, the account changes' included, checks the schema against a real record.
    """

    def __init__(self) -> None:
        self.records: list[AuditRecord] = []
        self.failing = False

    def record(self, record: AuditRecord) -> None:
        if self.failing:
            raise StoreUnavailable("PutLogEvents", "debate-dev-tub-audit", "synthetic outage")
        audit_record_validator().validate(json.loads(record.to_json()))
        self.records.append(record)


# --------------------------------------------------------------------------------------------
# The landscape pages' synthetic bundles (v1-e39-t17)
# --------------------------------------------------------------------------------------------

LANDSCAPE_FIXTURES: Final = Path(__file__).resolve().parent / "fixtures" / "landscape"
LANDSCAPE_PUBLISHED_AT: Final = datetime(2026, 10, 21, 6, 0, tzinfo=UTC)


def landscape_fixture_objects() -> dict[str, bytes]:
    """Every file under `fixtures/landscape/`, by the key it would have in the bucket."""
    return {
        f"reports/landscape/{path.relative_to(LANDSCAPE_FIXTURES).as_posix()}": path.read_bytes()
        for path in sorted(LANDSCAPE_FIXTURES.rglob("*.md"))
        if path.name != "README.md"
    }


class InMemoryLandscapeObjects(LandscapeObjects):
    """The bucket's `reports/landscape/` in memory: listed and read as `S3EvidenceObjectStore` does.

    `reads` counts each listing and each file read, and `failing` makes every call raise as an
    unreachable bucket would.
    """

    def __init__(self, objects: Mapping[str, bytes] | None = None) -> None:
        self.objects: dict[str, tuple[bytes, datetime]] = {
            key: (content, LANDSCAPE_PUBLISHED_AT)
            for key, content in (landscape_fixture_objects() if objects is None else objects).items()
        }
        self.listings = 0
        self.reads: list[str] = []
        self.failing = False

    def put(self, key: str, content: bytes, at: datetime) -> None:
        self.objects[key] = (content, at)

    def delete(self, key: str) -> None:
        del self.objects[key]

    async def list_objects(self, prefix: str) -> tuple[ObjectInfo, ...]:
        if self.failing:
            raise StoreUnavailable("ListObjectsV2", prefix, "synthetic outage")
        self.listings += 1
        return tuple(
            ObjectInfo(key=key, size=len(content), last_modified=at)
            for key, (content, at) in sorted(self.objects.items())
            if key.startswith(prefix)
        )

    async def get_file(self, key: ObjectKey, destination: Path) -> ObjectInfo:
        if self.failing:
            raise StoreUnavailable("GetObject", key, "synthetic outage")
        if key not in self.objects:
            raise NotFound("evidence object", key)
        self.reads.append(key)
        content, at = self.objects[key]
        destination.write_bytes(content)
        return ObjectInfo(key=key, size=len(content), last_modified=at)


# --------------------------------------------------------------------------------------------
# The search pages' synthetic index (v1-e39-t06)
# --------------------------------------------------------------------------------------------

SCHOOL, TEAM, OTHER_SCHOOL, OTHER_TEAM = "Maple Grove", "QX", "Riverbend", "ZT"
TOURNAMENT, ROUND = "Invented Invitational", "Round 4"
CAMP = "Cascade Institute"
LINKED_SCHOOL, LINKED_TEAM = "Cedarbrook", "LM"
"""The linked card's school and team code, in the form an openCaselist address spells them: one word
each (`v1-e39-t11`). `Maple Grove`, with its space, is a display name, so the featured card has no link."""

FEATURED_TEXT: Final = "Zephyr winds raise granite costs.\nThe second paragraph says basalt holds."
"""The featured card's text: every kind of span lands on it, one highlight across the line break."""

LONG_CARD_WORDS: Final = 3200
LONG_READ_ALOUD: Final = "Zephyr read aloud stretch"
FILLER_CARDS: Final = 20
"""Cards 6 to 25: with the five named cards, 25 match `zephyr`, so the results run to two pages."""


def _span(text: str, emphasis: RunEmphasis, words: str, colour: str | None = None) -> FormattingSpan:
    start = text.index(words)
    return FormattingSpan(
        emphasis=emphasis,
        start_offset=start,
        end_offset=start + len(words),
        highlight_color=colour,
        rule_id="synthetic",
        match_source=StyleMatchSource.VERBATIM,
    )


def _size(text: str, words: str, half_points: int) -> FontSizeSpan:
    start = text.index(words)
    return FontSizeSpan(start_offset=start, end_offset=start + len(words), half_points=half_points)


def cluster_of(doc_id: int) -> str:
    return f"{doc_id:064x}"


def _occurrence(
    ordinal: int,
    doc_id: int,
    *,
    caselist: str = "hsld26",
    school: str | None = SCHOOL,
    team: str | None = TEAM,
    side: str = "NEG",
    provenance: bool = True,
) -> IndexedOccurrence:
    camp = caselist == "openev"
    kept = provenance and not camp
    return IndexedOccurrence(
        ordinal=ordinal,
        caselist=caselist,
        source_sha256=f"{doc_id:032x}{ordinal:032x}",
        disclosure=None if camp else f"{ordinal:032x}{doc_id:032x}",
        first_element_index=0,
        last_element_index=2,
        snapshot="2026-policy" if camp else "2026-09-15",
        last_snapshot="2026-policy" if camp else "2026-10-13",
        completeness="FULL",
        attributed=True,
        provenance=provenance,
        side=side if kept else None,
        school=school if kept else None,
        team_code=team if kept else None,
        tournament=TOURNAMENT if kept else None,
        round=ROUND if kept else None,
        camp=CAMP if camp else None,
        camp_year=2026 if camp else None,
        camp_event="POLICY" if camp else None,
        camp_file_title="Invented Adv CP" if camp else None,
    )


def _document(
    doc_id: int,
    *,
    text: str,
    tag: str | None,
    cite: str = "Lindqvist 26, Invented Quarterly, 2026",
    caselist: str = "hsld26",
    event: str = "LD",
    sides: tuple[str, ...] = ("NEG",),
    spans: Sequence[FormattingSpan] = (),
    sizes: Sequence[FontSizeSpan] = (),
    occurrences: Sequence[IndexedOccurrence] | None = None,
    team_count: int = 1,
) -> SearchDocument:
    held = tuple(occurrences) if occurrences is not None else (_occurrence(0, doc_id, caselist=caselist),)
    camp = caselist == "openev"
    return SearchDocument(
        doc_id=doc_id,
        caselist=caselist,
        cluster_id=cluster_of(doc_id),
        event=event,
        camp=CAMP if camp else None,
        tag=tag,
        cite=cite,
        short_cite=cite.split(",")[0],
        read_aloud=read_aloud_text(text, spans),
        text=text,
        completeness="FULL",
        formatting_spans=tuple(spans),
        font_size_spans=tuple(sizes),
        sides=sides,
        first_seen=None if camp else "2026-09-15",
        last_seen=None if camp else "2026-10-13",
        file_count=len(held),
        team_count=0 if camp else team_count,
        occurrences=held,
    )


def _long_text() -> str:
    vocabulary = ("granite", "basalt", "quartz", "feldspar", "mica", "gneiss", "schist", "slate")
    rest = " ".join(vocabulary[index % len(vocabulary)] for index in range(LONG_CARD_WORDS - 5))
    return f"{LONG_READ_ALOUD}. Zephyr {rest}."


def _featured_formatting() -> tuple[tuple[FormattingSpan, ...], tuple[FontSizeSpan, ...]]:
    spans = (
        _span(FEATURED_TEXT, RunEmphasis.UNDERLINE, "Zephyr winds raise granite costs"),
        _span(FEATURED_TEXT, RunEmphasis.HIGHLIGHT, "winds raise", "cyan"),
        _span(FEATURED_TEXT, RunEmphasis.EMPHASIS, "granite"),
        _span(FEATURED_TEXT, RunEmphasis.HIGHLIGHT, "costs.\nThe", "yellow"),
        _span(FEATURED_TEXT, RunEmphasis.SHRUNK, "second paragraph says"),
        _span(FEATURED_TEXT, RunEmphasis.BOLD, "basalt holds"),
        _span(FEATURED_TEXT, RunEmphasis.UNDERTAG, "says basalt"),
        _span(FEATURED_TEXT, RunEmphasis.ANALYTIC, "holds"),
        _span(FEATURED_TEXT, RunEmphasis.CITE, "Zephyr"),
        _span(FEATURED_TEXT, RunEmphasis.HEADING, "The"),
    )
    sizes = (
        _size(FEATURED_TEXT, "Zephyr winds raise granite costs.", 22),
        _size(FEATURED_TEXT, "second paragraph says", 16),
        _size(FEATURED_TEXT, "basalt holds.", 21),
    )
    return spans, sizes


HOSTILE_TAG: Final = "<script>alert('tag')</script> zephyr hostile"
HOSTILE_CITE: Final = 'Hostile 26, "onerror=alert(1)" <b>Quarterly</b>'
HOSTILE_TEXT: Final = "<img src=x onerror=alert(1)> zephyr javascript:alert(1) </p><style>body{}</style>"


# --------------------------------------------------------------------------------------------
# The download's synthetic sources (v1-e39-t08)
# --------------------------------------------------------------------------------------------

CASELIST_STORE: Final = "raw/caselist/hsld26"
CAMP_STORE: Final = "raw/openev/2026"
CAMP_RELEASE: Final = "2026-policy"
DRAWING: Final = (
    '<w:drawing xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
    '<wp:inline><a:graphic><a:graphicData><pic:pic><pic:blipFill><a:blip r:embed="rId9"/>'
    "</pic:blipFill></pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing>"
)
"""A picture inside a card, which the E33 writer refuses as UNSUPPORTED_CONTENT."""


def _tag(text: str) -> str:
    return paragraph_xml(run_xml(text), style="Heading4")


def _cite(name_year: str, rest: str) -> str:
    return paragraph_xml(run_xml(name_year, character_style="Style13ptBold") + run_xml(rest))


def _body(lead: str, read: str, tail: str, *, inside: str = "") -> str:
    return paragraph_xml(
        run_xml(lead, half_points=16)
        + run_xml(read, character_style="StyleUnderline", highlight="cyan")
        + run_xml(" ", half_points=16)
        + run_xml("a stressed warrant", character_style="Emphasis", bold=True, highlight="green")
        + (f"<w:r>{inside}</w:r>" if inside else "")
        + run_xml(tail, half_points=16)
    )


@dataclass(frozen=True)
class DownloadSource:
    """One synthetic source: where the bucket keeps it, its bytes, and the cards the parser reads in it."""

    store: str
    caselist: str
    content: bytes
    parsed: ParsedDocument
    stored: bool = True
    """False for the source the store has lost: its card's download is refused SOURCE_UNAVAILABLE."""

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()


def understated(content: bytes, declared: int) -> bytes:
    """`content` with its zip directory claiming `declared` bytes for `word/document.xml`, its CRC unchanged.

    The claim is what a download's budget reads; the part still holds every byte it held.
    """
    data = bytearray(content)
    signature = b"PK\x01\x02"
    position = data.find(signature)
    while position != -1:
        length = int.from_bytes(data[position + 28 : position + 30], "little")
        if data[position + 46 : position + 46 + length] == b"word/document.xml":
            data[position + 24 : position + 28] = declared.to_bytes(4, "little")
            return bytes(data)
        position = data.find(signature, position + 4)
    raise AssertionError("the package has no word/document.xml")


def _source(
    parser: DebateDocxParser,
    content: bytes,
    *,
    caselist: str = "hsld26",
    stored: bool = True,
    declared: int | None = None,
) -> DownloadSource:
    camp = caselist == "openev"
    sha = hashlib.sha256(content).hexdigest()
    document = SourceDocument(
        sha256=sha,
        byte_size=len(content),
        source_format=SourceFormat.DOCX,
        origin=SourceOrigin.OPENEV if camp else SourceOrigin.CASELIST_ARCHIVE,
        caselist=None if camp else caselist,
        first_seen_snapshot=date(2026, 9, 15),
        last_seen_snapshot=date(2026, 10, 13),
    )
    parsed = parser.parse(content, document, source_path="synthetic-source.docx")
    assert isinstance(parsed, ParsedDocument), parsed
    return DownloadSource(
        store=CAMP_STORE if camp else CASELIST_STORE,
        caselist=caselist,
        content=content if declared is None else understated(content, declared),
        parsed=parsed,
        stored=stored,
    )


def build_download_sources(parser: DebateDocxParser) -> Mapping[str, DownloadSource]:
    """Six synthetic sources: two cards in one, one each in the rest. `understated`'s zip directory
    claims 1,000 bytes for a `word/document.xml` that holds far more."""
    return {
        "disclosed": _source(
            parser,
            build_docx(
                _tag("Gabbro ridges slow upland erosion")
                + _cite("Thorvaldsen 26", ", Fellow, Synthetic Geology Review, 2026")
                + _body("Upland soils ", "hold behind gabbro ridges", " for decades.")
                + _tag("Pumice terraces drain quickly")
                + _cite("Aaltonen 25", ", Hydrologist, Synthetic Water Quarterly, 2025")
                + _body("Rain ", "passes through pumice terraces", " within hours.")
            ),
        ),
        "other": _source(
            parser,
            build_docx(
                _tag("Scoria fields warm faster")
                + _cite("Vasquez 24", ", Climatologist, Synthetic Heat Review, 2024")
                + _body("Dark ground ", "absorbs more sunlight", " than pale ground.")
            ),
        ),
        "camp": _source(
            parser,
            build_docx(
                _tag("Tuff walls shelter seedlings")
                + _cite("Okafor 26", ", Ecologist, Synthetic Seedling Review, 2026")
                + _body("Seedlings ", "survive behind tuff walls", " in dry years.")
            ),
            caselist="openev",
        ),
        "picture": _source(
            parser,
            build_docx(
                _tag("Andesite slopes hold snow")
                + _cite("Haugen 26", ", Glaciologist, Synthetic Snow Review, 2026")
                + _body("Snow ", "stays on andesite slopes", " into spring.", inside=DRAWING)
            ),
        ),
        "understated": _source(
            parser,
            build_docx(
                _tag("Tephra plumes travel far downwind")
                + _cite("Sigurdsson 26", ", Volcanologist, Synthetic Ash Review, 2026")
                + "".join(
                    _body("Fine ash ", f"drifts for hundreds of kilometres {n}", " on the wind.")
                    for n in range(40)
                )
            ),
            declared=1000,
        ),
        "lost": _source(
            parser,
            build_docx(
                _tag("Rhyolite domes vent slowly")
                + _cite("Lindgren 23", ", Volcanologist, Synthetic Vent Review, 2023")
                + _body("Gas ", "escapes rhyolite domes", " over centuries.")
            ),
            stored=False,
        ),
    }


DOWNLOAD_CARDS: Final = {
    "download": (27, "disclosed", 0),
    "download second": (28, "disclosed", 1),
    "download other": (29, "other", 0),
    "camp download": (30, "camp", 0),
    "picture": (31, "picture", 0),
    "lost source": (32, "lost", 0),
    "understated": (33, "understated", 0),
}
"""The downloadable cards: each one's doc id, its source in the `download_sources` fixture, and which
card of it."""


def download_card(sources: Mapping[str, DownloadSource], name: str) -> ParsedCard:
    """The parsed card a download's card is copied from."""
    _, source, number = DOWNLOAD_CARDS[name]
    return sources[source].parsed.cards[number]


def _download_document(doc_id: int, source: DownloadSource, card: ParsedCard) -> SearchDocument:
    """The document `v1-e39-t02`'s build writes for one card of `source`, alone in its cluster."""
    camp = source.caselist == "openev"
    occurrence = IndexedOccurrence(
        ordinal=0,
        caselist=source.caselist,
        source_sha256=source.sha256,
        disclosure=None if camp else disclosure_digest(source.caselist, f"Synthetic/{doc_id}.docx"),
        first_element_index=card.provenance.first_element_index,
        last_element_index=card.provenance.last_element_index,
        snapshot=CAMP_RELEASE if camp else "2026-09-15",
        last_snapshot=CAMP_RELEASE if camp else "2026-10-13",
        completeness=card.completeness.value,
        attributed=True,
        provenance=True,
        side=None if camp else "AFF",
        school=None if camp else SCHOOL,
        team_code=None if camp else TEAM,
        tournament=None if camp else TOURNAMENT,
        round=None if camp else ROUND,
        camp=CAMP if camp else None,
        camp_year=2026 if camp else None,
        camp_event="POLICY" if camp else None,
        camp_file_title="Invented Camp File" if camp else None,
    )
    return SearchDocument(
        doc_id=doc_id,
        caselist=source.caselist,
        cluster_id=cluster_of(doc_id),
        event="POLICY" if camp else "LD",
        camp=CAMP if camp else None,
        tag=card.tag,
        cite=cite_without_cutter_mark(card.full_cite),
        short_cite=card.short_cite,
        read_aloud=read_aloud_text(card.evidence_text, card.formatting_spans),
        text=card.evidence_text,
        completeness=card.completeness.value,
        formatting_spans=card.formatting_spans,
        font_size_spans=card.font_size_spans,
        sides=() if camp else ("AFF",),
        first_seen=None if camp else "2026-09-15",
        last_seen=None if camp else "2026-10-13",
        file_count=1,
        team_count=0 if camp else 1,
        occurrences=(occurrence,),
    )


def download_documents(sources: Mapping[str, DownloadSource]) -> tuple[SearchDocument, ...]:
    return tuple(
        _download_document(doc_id, sources[source], download_card(sources, name))
        for name, (doc_id, source, _) in DOWNLOAD_CARDS.items()
    )


class RecordingSourceStore(SnapshotStore):
    """One `raw/` prefix of the bucket: sources by their SHA-256, every read recorded, writes refused."""

    def __init__(self, prefix: str) -> None:
        self.prefix = prefix
        self.blobs: dict[str, bytes] = {}
        self.reads: list[str] = []

    def add(self, content: bytes) -> None:
        self.blobs[hashlib.sha256(content).hexdigest()] = content

    async def put(self, data: bytes) -> BlobKey:
        raise AssertionError(f"a download wrote to {self.prefix}")

    async def get(self, key: BlobKey) -> bytes:
        self.reads.append(key)
        stored = self.blobs.get(key)
        if stored is None:
            raise NotFound("snapshot blob", key)
        actual = hashlib.sha256(stored).hexdigest()
        if actual != key:
            raise BlobIntegrityError(key, actual)
        return stored

    async def exists(self, key: BlobKey) -> bool:
        return key in self.blobs


# --------------------------------------------------------------------------------------------
# The corpora: the search pages' cards, and the same with the download's
# --------------------------------------------------------------------------------------------


def corpus_documents(downloadable: Sequence[SearchDocument] = ()) -> tuple[SearchDocument, ...]:
    """The search pages' cards, with `downloadable` (the download's) before the linked card, which is last."""
    long_text = _long_text()
    featured_spans, featured_sizes = _featured_formatting()
    return (
        _document(
            1,
            text=FEATURED_TEXT,
            tag="Zephyr winds raise granite costs",
            spans=featured_spans,
            sizes=featured_sizes,
            occurrences=(
                _occurrence(0, 1),
                _occurrence(1, 1, school=OTHER_SCHOOL, team=OTHER_TEAM, side="AFF"),
                _occurrence(2, 1, provenance=False),
            ),
            sides=("AFF", "NEG"),
            team_count=2,
        ),
        _document(
            2,
            text="Invented text about zephyr tariffs.",
            tag="Zephyr tariffs help farmers",
            caselist="hspf26",
            event="PF",
            sides=("PRO",),
            occurrences=(_occurrence(0, 2, caselist="hspf26", side="PRO"),),
        ),
        _document(
            3,
            text="A camp card about zephyr basalt.",
            tag="Camp zephyr card",
            caselist="openev",
            event="POLICY",
            sides=(),
        ),
        _document(
            4,
            text=long_text,
            tag="A very long zephyr card",
            spans=(
                _span(long_text, RunEmphasis.UNDERLINE, LONG_READ_ALOUD),
                _span(long_text, RunEmphasis.HIGHLIGHT, "read aloud", "green"),
            ),
        ),
        _document(
            5,
            text=HOSTILE_TEXT,
            tag=HOSTILE_TAG,
            cite=HOSTILE_CITE,
            spans=(_span(HOSTILE_TEXT, RunEmphasis.HIGHLIGHT, "zephyr", "chartreuse"),),
        ),
        *(
            _document(doc_id, text=f"Filler card {doc_id} about zephyr.", tag=f"Zephyr filler {doc_id}")
            for doc_id in range(6, 6 + FILLER_CARDS)
        ),
        *downloadable,
        _document(
            LINKED_CARD,
            text="Tundra lichens slow invented erosion.",
            tag="Tundra lichens slow erosion",
            occurrences=(_occurrence(0, LINKED_CARD, school=LINKED_SCHOOL, team=LINKED_TEAM),),
        ),
    )


LINKED_CARD: Final = 6 + FILLER_CARDS
"""Card 26, which holds no `zephyr`: the one card whose school and team code make an openCaselist link."""

SEARCH_CARDS: Final = {
    "featured": 1,
    "public forum": 2,
    "camp": 3,
    "long": 4,
    "hostile": 5,
    "linked": LINKED_CARD,
}
"""The named cards of the `search_corpus` fixture by doc id; the rest are fillers."""
CARDS: Final = {**SEARCH_CARDS, **{name: doc_id for name, (doc_id, _, _) in DOWNLOAD_CARDS.items()}}
"""The named cards of the `download_corpus` fixture: the search pages' and the download's, the only
ones whose sources exist."""


def published_corpus(
    corpus: Sequence[SearchDocument], *, parser_version: str | None = None
) -> PublishedIndex:
    """`corpus` built by `v1-e39-t02`'s writer and published in memory, under `parser_version` if given."""
    with tempfile.TemporaryDirectory() as scratch:
        path = Path(scratch) / "search-index.sqlite"
        sink = SqliteSearchIndexWriter().create(path)
        for document in corpus:
            sink.add(document)
        sink.finish()
        sqlite = path.read_bytes()
    stores: dict[str, int] = {}
    for document in corpus:
        stores[document.caselist] = stores.get(document.caselist, 0) + 1
    if parser_version is None:
        return published_index(sqlite, documents_by_store=stores)
    return published_index(sqlite, documents_by_store=stores, parser_version=parser_version)


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
        evidence_bucket="debate-dev-evidence-synthetic",
    )


def new_cookie_keys() -> CookieKeys:
    return CookieKeys(current=os.urandom(32), previous=os.urandom(32))


class _RecordingWriter:
    """The real E33 writer, keeping a copy of every file it builds for the test to read."""

    def __init__(self, writer: DocxEvidenceFileWriter, built: list[bytes]) -> None:
        self._writer = writer
        self._built = built

    async def build(self, request: Any) -> Any:
        result = await self._writer.build(request)
        docx = getattr(result, "docx", None)
        if isinstance(docx, bytes):
            self._built.append(docx)
        return result


# --------------------------------------------------------------------------------------------
# What a world without a surface has in its place
# --------------------------------------------------------------------------------------------

NO_SURFACE: Final = "this world has no such surface: the test file's `world` fixture names the one it needs"


class NothingPublished:
    """The search index's prefix of a bucket nothing was ever published to: a search finds no index."""

    def read_pointer(self, *, if_none_match: str | None) -> PointerRead:
        raise NotFound("search index object", SEARCH_INDEX_POINTER_KEY)

    def read_object(self, key: str, *, max_bytes: int) -> bytes:
        raise NotFound("search index object", key)

    def stream_object(self, key: str) -> Iterator[bytes]:
        raise NotFound("search index object", key)


def _no_index_to_open(path: Path, index_id: str) -> ClosableSearchIndexReader:
    raise AssertionError(NO_SURFACE)


def _no_download_writer(sources: SnapshotStore) -> EvidenceFileWriter:
    raise AssertionError(NO_SURFACE)


def _no_document_size(content: bytes) -> int | None:
    raise AssertionError(NO_SURFACE)


# --------------------------------------------------------------------------------------------
# The worlds, one per surface
# --------------------------------------------------------------------------------------------


class PilotWorld:
    """The app over the fakes, a browser for it, and helpers to sign in or plant a session.

    Sign-in alone: nothing is published to search, no source is stored to download and no landscape
    bundle is listed. Each surface's world overrides the method that builds its service.
    """

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
        self._index_directory = tempfile.TemporaryDirectory(prefix="tub-index-")
        self.index_directory = Path(self._index_directory.name)
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
        search_index = self._search_index()
        access_audit = AccessAuditService(audit=self.audit, clock=self.clock)
        self.services = PilotServices(
            configuration=configuration(),
            cookie_keys=self.cookie_keys,
            sign_in=SignInService(
                identity_provider=identity_provider,
                self_service=self.self_service,
                audit=self.audit,
                clock=self.clock,
            ),
            account_page=AccountPageService(
                identity_provider=identity_provider,
                self_service=self.self_service,
                audit=self.audit,
                clock=self.clock,
                authenticator_issuer="Team evidence search (dev)",
            ),
            search_index=search_index,
            access_audit=access_audit,
            card_download=self._card_download(search_index, access_audit),
            landscape=self._landscape(),
            clock=self.clock,
        )
        self.app = create_app(self.services)
        self.browser = self.new_browser()

    # Each surface's service, absent here ------------------------------------------------------

    def _search_index(self) -> SearchIndexHolder:
        return SearchIndexHolder(
            NothingPublished(),
            directory=self.index_directory,
            open_reader=_no_index_to_open,
            clock=self.clock,
        )

    def _card_download(
        self, search_index: SearchIndexHolder, access_audit: AccessAuditService
    ) -> CardDownloadService:
        return self._no_download(search_index, access_audit, parser_version=NO_SURFACE)

    def _no_download(
        self, search_index: SearchIndexHolder, access_audit: AccessAuditService, *, parser_version: str
    ) -> CardDownloadService:
        """No source stored and no writer wired: a download is a test's mistake.

        Download is on when `parser_version` is the one the index was built by, as on the search pages.
        """
        return CardDownloadService(
            search_index=search_index,
            writer=_no_download_writer,
            source_stores=RecordingSourceStore,
            access_audit=access_audit,
            parser_version=parser_version,
            profile_version=NO_SURFACE,
            clock=self.clock,
            document_size=_no_document_size,
        )

    def _landscape(self) -> LandscapeShelf[RenderedBundle]:
        return LandscapeShelf(InMemoryLandscapeObjects({}), prepare=render_bundle, clock=self.clock)

    # Browsers and accounts -------------------------------------------------------------------

    def signed_in_student(self, username: str = "debater.one") -> Session:
        """A student account and its session, planted in the browser."""
        self.login.add_account(username, "student")
        return self.use_session(self.session_for(username))

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


class SearchWorld(PilotWorld):
    """Sign-in and the search pages, over `corpus` published as `index` and fetched by the real holder."""

    def __init__(
        self,
        *,
        index: PublishedIndex,
        corpus: tuple[SearchDocument, ...],
        cards: Mapping[str, int],
        count_cap: int | None = None,
        **rest: Any,
    ) -> None:
        self.index = index
        self.corpus = corpus
        self.cards = cards
        """The named cards of :attr:`corpus` by doc id; the rest are fillers."""
        self.index_source = InMemorySearchIndexSource()
        self.index_source.publish(index)
        self._count_cap = count_cap
        super().__init__(**rest)

    def _search_index(self) -> SearchIndexHolder:
        count_cap = self._count_cap
        return SearchIndexHolder(
            self.index_source,
            directory=self.index_directory,
            open_reader=lambda path, index_id: SqliteSearchIndexReader(path, index_id=index_id),
            clock=self.clock,
            build_service=(
                EvidenceSearchService
                if count_cap is None
                else partial(EvidenceSearchService, count_cap=count_cap)
            ),
            suppression_list=self.index_source,
        )

    def _card_download(
        self, search_index: SearchIndexHolder, access_audit: AccessAuditService
    ) -> CardDownloadService:
        """Download is on, as for an index this function's parser built; nothing can be downloaded."""
        return self._no_download(
            search_index, access_audit, parser_version=self.index.manifest.parser_version
        )

    def card_reference(self, name: str) -> str:
        """`<caselist>/<cluster id>` of one of :attr:`cards`, as the cart names it."""
        return self.card_path(name).removeprefix("/cards/")

    def card_path(self, name: str) -> str:
        """The page of one of :attr:`cards`."""
        doc_id = self.cards[name]
        caselist = next(document.caselist for document in self.corpus if document.doc_id == doc_id)
        return f"/cards/{caselist}/{cluster_of(doc_id)}"


class DownloadWorld(SearchWorld):
    """The search world over the download's corpus, its sources stored and the real E33 writer wired."""

    caselist_store = CASELIST_STORE
    camp_store = CAMP_STORE

    def __init__(
        self,
        *,
        sources: Mapping[str, DownloadSource],
        parser: DebateDocxParser,
        download_card_cap: int = DEFAULT_DOWNLOAD_CARD_CAP,
        download_source_xml_bytes: int = DEFAULT_DOWNLOAD_SOURCE_XML_BYTES,
        download_fetch_bytes: int = DOWNLOAD_FETCH_MAX_BYTES,
        download_writer: WriterFactory | None = None,
        **rest: Any,
    ) -> None:
        self._sources = sources
        self._parser = parser
        self._download_card_cap = download_card_cap
        self._download_source_xml_bytes = download_source_xml_bytes
        self._download_fetch_bytes = download_fetch_bytes
        self._download_writer = download_writer
        self.source_stores = {prefix: RecordingSourceStore(prefix) for prefix in (CASELIST_STORE, CAMP_STORE)}
        for source in sources.values():
            if source.stored:
                self.source_stores[source.store].add(source.content)
        self.built: list[bytes] = []
        """The bytes of every file a download built, sent or not."""
        super().__init__(**rest)

    def sources(self) -> Mapping[str, DownloadSource]:
        """The download's synthetic sources, by name (`v1-e39-t08`)."""
        return self._sources

    def parser(self) -> DebateDocxParser:
        return self._parser

    def document_bytes(self, source: str) -> int:
        """What a source's zip directory declares for its `word/document.xml`, as a download reads it."""
        declared = declared_document_bytes(self._sources[source].content)
        assert declared is not None
        return declared

    def source_card(self, name: str) -> ParsedCard:
        """The parsed card one of the download's cards is copied from."""
        return download_card(self._sources, name)

    def _card_download(
        self, search_index: SearchIndexHolder, access_audit: AccessAuditService
    ) -> CardDownloadService:
        parser = self._parser
        return CardDownloadService(
            search_index=search_index,
            writer=self._download_writer
            or (
                lambda sources: _RecordingWriter(
                    DocxEvidenceFileWriter(snapshots=sources, parser=parser), self.built
                )
            ),
            source_stores=lambda prefix: self.source_stores.get(prefix) or RecordingSourceStore(prefix),
            access_audit=access_audit,
            parser_version=parser.parser_version,
            profile_version=parser.profile_version,
            clock=self.clock,
            card_cap=self._download_card_cap,
            document_size=declared_document_bytes,
            source_xml_bytes=self._download_source_xml_bytes,
            fetch_bytes=self._download_fetch_bytes,
        )

    def download(
        self,
        *names: str,
        cards: str | None = None,
        browser: TestClient | None = None,
        csrf_token: str | None = None,
        pocket: str | None = None,
    ) -> Any:
        """POST `/download` as `app.js` sends it, for the named cards (or a `cards` field as given), with
        the `pocket` field the student typed, urlencoded, when one is given (`v1-e39-t24`)."""
        field = cards if cards is not None else ",".join(self.card_reference(name) for name in names)
        token = csrf_token
        if token is None:
            session = self.session_cookie(browser)
            assert session is not None, "sign a student in first"
            token = session.csrf_token
        fields = {"cards": field} if pocket is None else {"cards": field, "pocket": quote_plus(pocket)}
        return self.post("/download", fields, csrf_token=token, browser=browser)


class LandscapeWorld(PilotWorld):
    """Sign-in and the landscape pages, over the bundles under `fixtures/landscape/` unless given others."""

    def __init__(self, *, landscape_objects: LandscapeObjects | None = None, **rest: Any) -> None:
        self.landscape_objects = landscape_objects or InMemoryLandscapeObjects()
        super().__init__(**rest)

    def _landscape(self) -> LandscapeShelf[RenderedBundle]:
        return LandscapeShelf(self.landscape_objects, prepare=render_bundle, clock=self.clock)


class EverySurfaceWorld(DownloadWorld, LandscapeWorld):
    """Every surface at once, for the tests that walk every route: the download's and the landscape's."""


# --------------------------------------------------------------------------------------------
# Reading Copy card's spans back (v1-e39-t06 ac2)
# --------------------------------------------------------------------------------------------


def _declarations(style: str) -> str:
    """A `style` attribute as one canonical string: Chrome's paste may space or terminate it."""
    parts = [part.strip() for part in style.split(";") if part.strip()]
    return ";".join(re.sub(r"\s*:\s*", ":", part) for part in parts)


def copied_spans(
    styles_by_character: Sequence[Sequence[str]],
) -> tuple[list[FormattingSpan], list[FontSizeSpan]]:
    """The spans a copy's span styles say, character by character, each as the runs it covers.

    The inverse of `debate_api.copy_card`'s table. A style the table does not write is an error,
    so a paste that rewrote a declaration fails the read-back rather than dropping a span.
    """
    from debate_api.copy_card import EMPHASIS_STYLES, HIGHLIGHT_STYLES

    by_style = {
        **{_declarations(style): ("emphasis", emphasis.value) for emphasis, style in EMPHASIS_STYLES.items()},
        **{_declarations(style): ("highlight", colour) for colour, style in HIGHLIGHT_STYLES.items()},
    }
    covered: dict[tuple[str, str], list[int]] = {}
    for offset, styles in enumerate(styles_by_character):
        for style in map(_declarations, styles):
            size = re.fullmatch(r"font-size:(\d+)(\.5)?pt", style)
            if size is not None:
                key = ("size", str(int(size.group(1)) * 2 + (1 if size.group(2) else 0)))
            else:
                key = by_style[style]
            covered.setdefault(key, []).append(offset)
    spans: list[FormattingSpan] = []
    sizes: list[FontSizeSpan] = []
    for (kind, value), offsets in covered.items():
        for start, end in _runs_of(offsets):
            if kind == "size":
                sizes.append(FontSizeSpan(start_offset=start, end_offset=end, half_points=int(value)))
                continue
            highlight = kind == "highlight"
            spans.append(
                FormattingSpan(
                    emphasis=RunEmphasis.HIGHLIGHT if highlight else RunEmphasis(value),
                    start_offset=start,
                    end_offset=end,
                    highlight_color=value if highlight else None,
                    rule_id="read-back",
                    match_source=StyleMatchSource.VERBATIM,
                )
            )
    return spans, sizes


def _runs_of(offsets: Sequence[int]) -> list[tuple[int, int]]:
    runs: list[list[int]] = []
    for offset in sorted(offsets):
        if runs and runs[-1][1] == offset:
            runs[-1][1] = offset + 1
        else:
            runs.append([offset, offset + 1])
    return [(start, end) for start, end in runs]


@pytest.fixture
def read_back() -> Callable[[Sequence[Sequence[str]]], tuple[list[FormattingSpan], list[FontSizeSpan]]]:
    """:func:`copied_spans`, for the Copy card tests in Python and in Chromium."""
    return copied_spans


# --------------------------------------------------------------------------------------------
# What more than one world shares, built once per session
# --------------------------------------------------------------------------------------------


@pytest.fixture(scope="session")
def search_corpus() -> tuple[SearchDocument, ...]:
    """The search pages' cards: the five named, twenty fillers and the linked card, last."""
    return corpus_documents()


@pytest.fixture(scope="session")
def search_corpus_index(search_corpus: tuple[SearchDocument, ...]) -> PublishedIndex:
    return published_corpus(search_corpus)


@pytest.fixture(scope="session")
def download_parser() -> DebateDocxParser:
    """The running parser, as the function's composition root builds it: one for the process."""
    return DebateDocxParser()


@pytest.fixture(scope="session")
def download_sources(download_parser: DebateDocxParser) -> Mapping[str, DownloadSource]:
    return build_download_sources(download_parser)


@pytest.fixture(scope="session")
def download_corpus(download_sources: Mapping[str, DownloadSource]) -> tuple[SearchDocument, ...]:
    """The search pages' cards with the download's seven, which are the only ones whose sources exist."""
    return corpus_documents(download_documents(download_sources))


@pytest.fixture(scope="session")
def download_corpus_index(
    download_corpus: tuple[SearchDocument, ...], download_parser: DebateDocxParser
) -> PublishedIndex:
    """The download's corpus, published under the running parser's version as a download requires."""
    return published_corpus(download_corpus, parser_version=download_parser.parser_version)


# --------------------------------------------------------------------------------------------
# The worlds: a test file's own `world` fixture names the one it needs
# --------------------------------------------------------------------------------------------


@pytest.fixture
def auth_world() -> Iterator[PilotWorld]:
    made = PilotWorld()
    yield made
    made.services.search_index.close()


@pytest.fixture
def make_search_world(
    search_corpus: tuple[SearchDocument, ...], search_corpus_index: PublishedIndex
) -> Callable[..., SearchWorld]:
    return partial(SearchWorld, index=search_corpus_index, corpus=search_corpus, cards=SEARCH_CARDS)


@pytest.fixture
def search_world(make_search_world: Callable[..., SearchWorld]) -> Iterator[SearchWorld]:
    made = make_search_world()
    yield made
    made.services.search_index.close()


@pytest.fixture
def make_download_world(
    download_corpus: tuple[SearchDocument, ...],
    download_corpus_index: PublishedIndex,
    download_sources: Mapping[str, DownloadSource],
    download_parser: DebateDocxParser,
) -> Callable[..., DownloadWorld]:
    return partial(
        DownloadWorld,
        index=download_corpus_index,
        corpus=download_corpus,
        cards=CARDS,
        sources=download_sources,
        parser=download_parser,
    )


@pytest.fixture
def download_world(make_download_world: Callable[..., DownloadWorld]) -> Iterator[DownloadWorld]:
    made = make_download_world()
    yield made
    made.services.search_index.close()


@pytest.fixture
def make_landscape_world() -> Callable[..., LandscapeWorld]:
    return LandscapeWorld


@pytest.fixture
def landscape_world(make_landscape_world: Callable[..., LandscapeWorld]) -> Iterator[LandscapeWorld]:
    made = make_landscape_world()
    yield made
    made.services.search_index.close()


@pytest.fixture
def every_surface_world(
    download_corpus: tuple[SearchDocument, ...],
    download_corpus_index: PublishedIndex,
    download_sources: Mapping[str, DownloadSource],
    download_parser: DebateDocxParser,
) -> Iterator[EverySurfaceWorld]:
    made = EverySurfaceWorld(
        index=download_corpus_index,
        corpus=download_corpus,
        cards=CARDS,
        sources=download_sources,
        parser=download_parser,
    )
    yield made
    made.services.search_index.close()


@pytest.fixture
def landscape_files() -> dict[str, bytes]:
    """The synthetic bundles under `fixtures/landscape/`, by bucket key (`v1-e39-t17`)."""
    return landscape_fixture_objects()


@pytest.fixture
def landscape_store() -> Callable[..., InMemoryLandscapeObjects]:
    """:class:`InMemoryLandscapeObjects`, to build with other files than the fixtures'."""
    return InMemoryLandscapeObjects

"""Checking a Cognito ID token before anything in it is believed (ADR-0019 (d), The flow, step 2).

A token is accepted only when every one of these holds, in this order:

1. it is three base64url parts, and its header names `RS256` and a key id;
2. that key is in the pool's published key set (fetched again once, for a key rotated in since);
3. its signature verifies with that key;
4. `iss` is this pool, `aud` is this app client, `token_use` is `id`;
5. `exp` is after now;
6. it names a subject and a username.

Each refusal is a :class:`~debate_core.application.ports.tub.TokenRefused` whose reason is a fixed
phrase; no claim's value and no part of the token is ever put in one.
"""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Final, Protocol, cast

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.padding import PKCS1v15
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey, RSAPublicNumbers
from cryptography.hazmat.primitives.hashes import SHA256

from debate_core.application.errors import StoreUnavailable
from debate_core.application.ports.tub import TokenRefused, VerifiedIdentity
from debate_core.integrations.cognito.transport import HttpTransport

__all__ = ["CognitoIdTokenVerifier", "JsonWebKeySet", "PublishedKeySet", "issuer_for", "rsa_key_from_jwk"]

_SIGNING_ALGORITHM: Final = "RS256"


def issuer_for(region: str, user_pool_id: str) -> str:
    """The `iss` of every token the pool issues, and the base of its key set's URL."""
    return f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}"


class JsonWebKeySet(Protocol):
    def keys(self, *, refresh: bool = False) -> Mapping[str, RSAPublicKey]:
        """The pool's signing keys by key id; `refresh` fetches them again."""
        ...


def rsa_key_from_jwk(jwk: Mapping[str, object]) -> RSAPublicKey | None:
    """The RSA public key a JSON Web Key describes, or `None` if it is not an RSA signing key."""
    if jwk.get("kty") != "RSA" or jwk.get("use", "sig") != "sig":
        return None
    modulus, exponent = jwk.get("n"), jwk.get("e")
    if not isinstance(modulus, str) or not isinstance(exponent, str):
        return None
    try:
        numbers = RSAPublicNumbers(
            e=int.from_bytes(_b64url_decode(exponent), "big"),
            n=int.from_bytes(_b64url_decode(modulus), "big"),
        )
        return numbers.public_key()
    except (ValueError, binascii.Error):
        return None


class PublishedKeySet(JsonWebKeySet):
    """The pool's key set from `<issuer>/.well-known/jwks.json`, fetched on first use and kept."""

    def __init__(self, *, issuer: str, transport: HttpTransport) -> None:
        self._url = f"{issuer}/.well-known/jwks.json"
        self._transport = transport
        self._keys: dict[str, RSAPublicKey] | None = None

    def keys(self, *, refresh: bool = False) -> Mapping[str, RSAPublicKey]:
        if self._keys is None or refresh:
            self._keys = self._fetch()
        return self._keys

    def _fetch(self) -> dict[str, RSAPublicKey]:
        response = self._transport.get(self._url)
        if response.status != 200:
            raise StoreUnavailable("GET", "the user pool's key set", str(response.status))
        try:
            document = json.loads(response.body)
        except ValueError as error:
            raise StoreUnavailable("GET", "the user pool's key set", "not JSON") from error
        listed: object = cast(dict[str, object], document).get("keys") if isinstance(document, dict) else None
        entries = cast(list[object], listed) if isinstance(listed, list) else []
        keys: dict[str, RSAPublicKey] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            jwk = cast(dict[str, object], entry)
            key_id = jwk.get("kid")
            key = rsa_key_from_jwk(jwk)
            if isinstance(key_id, str) and key is not None:
                keys[key_id] = key
        return keys


class CognitoIdTokenVerifier:
    """Checks an ID token from one pool, for one app client, at the clock's now."""

    def __init__(
        self, *, issuer: str, client_id: str, key_set: JsonWebKeySet, clock: Callable[[], datetime]
    ) -> None:
        self._issuer = issuer
        self._client_id = client_id
        self._key_set = key_set
        self._clock = clock

    def verify(self, token: str) -> VerifiedIdentity:
        """The token's identity, or :class:`TokenRefused` naming the first check it failed."""
        parts = token.split(".")
        if len(parts) != 3:
            raise TokenRefused("the ID token is not a signed token")
        header = _json_object(parts[0])
        if header.get("alg") != _SIGNING_ALGORITHM:
            raise TokenRefused("the ID token is not signed with RS256")
        key_id = header.get("kid")
        if not isinstance(key_id, str):
            raise TokenRefused("the ID token names no signing key")
        key = self._key_set.keys().get(key_id) or self._key_set.keys(refresh=True).get(key_id)
        if key is None:
            raise TokenRefused("the ID token was signed by a key this pool does not publish")
        try:
            key.verify(
                _b64url_decode(parts[2]), f"{parts[0]}.{parts[1]}".encode("ascii"), PKCS1v15(), SHA256()
            )
        except (InvalidSignature, ValueError, binascii.Error) as error:
            raise TokenRefused("the ID token's signature does not verify") from error
        return self._identity(_json_object(parts[1]))

    def _identity(self, claims: Mapping[str, object]) -> VerifiedIdentity:
        if claims.get("iss") != self._issuer:
            raise TokenRefused("the ID token was issued by another user pool")
        audience = claims.get("aud")
        if audience != self._client_id:
            raise TokenRefused("the ID token was issued for another app client")
        if claims.get("token_use") != "id":
            raise TokenRefused("the token is not an ID token")
        expiry = claims.get("exp")
        if not isinstance(expiry, int | float) or isinstance(expiry, bool):
            raise TokenRefused("the ID token has no expiry")
        if self._clock().timestamp() >= expiry:
            raise TokenRefused("the ID token has expired")
        subject, username = claims.get("sub"), claims.get("cognito:username")
        if not isinstance(subject, str) or not subject or not isinstance(username, str) or not username:
            raise TokenRefused("the ID token names no account")
        groups = claims.get("cognito:groups", [])
        nonce = claims.get("nonce")
        return VerifiedIdentity(
            subject=subject,
            username=username,
            groups=frozenset(group for group in cast(list[object], groups) if isinstance(group, str))
            if isinstance(groups, list)
            else frozenset(),
            nonce=nonce if isinstance(nonce, str) else None,
        )


def _b64url_decode(part: str) -> bytes:
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


def _json_object(part: str) -> dict[str, object]:
    try:
        value = json.loads(_b64url_decode(part))
    except (ValueError, binascii.Error) as error:
        raise TokenRefused("the ID token is malformed") from error
    if not isinstance(value, dict):
        raise TokenRefused("the ID token is malformed")
    return cast(dict[str, object], value)

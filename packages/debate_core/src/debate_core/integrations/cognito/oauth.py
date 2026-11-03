"""Managed login's OAuth endpoints, from the server (ADR-0019 (d), The flow).

* `/oauth2/authorize`: where an unsigned browser is sent, with `state`, `nonce` and an `S256`
  challenge, for the scopes `openid` and `aws.cognito.signin.user.admin`.
* `/oauth2/token`: the code exchange (with the verifier) and the refresh grant, both authenticated
  with the client secret by HTTP Basic, which only the function holds.
* `/oauth2/revoke`: the refresh token, at sign-out.
* `/logout`: managed login's own session cookie cleared, then back to `/signed-out`.

Every ID token that comes back is checked by
:class:`~debate_core.integrations.cognito.id_tokens.CognitoIdTokenVerifier` before it is returned.
A refusal from the token endpoint is :class:`~debate_core.application.ports.tub.TokenRefused`
carrying the OAuth error code only when it is one RFC 6749 defines; the endpoint's description is
never passed on.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from typing import Final, cast
from urllib.parse import urlencode

from debate_core.application.errors import StoreUnavailable
from debate_core.application.ports.tub import IdentityProvider, IssuedTokens, TokenRefused
from debate_core.application.tub.sessions import SignInTransaction
from debate_core.integrations.cognito.id_tokens import CognitoIdTokenVerifier
from debate_core.integrations.cognito.transport import HttpResponse, HttpTransport

__all__ = ["SCOPES", "CognitoOAuthClient"]

SCOPES: Final = "openid aws.cognito.signin.user.admin"
_OAUTH_ERRORS: Final = frozenset(
    {"invalid_request", "invalid_client", "invalid_grant", "unauthorized_client", "unsupported_grant_type"}
)


class CognitoOAuthClient(IdentityProvider):
    """:class:`~debate_core.application.ports.tub.IdentityProvider` over managed login's endpoints."""

    def __init__(
        self,
        *,
        login_origin: str,
        public_origin: str,
        client_id: str,
        client_secret: str,
        id_tokens: CognitoIdTokenVerifier,
        transport: HttpTransport,
    ) -> None:
        self._login_origin = login_origin.rstrip("/")
        self._public_origin = public_origin.rstrip("/")
        self._client_id = client_id
        credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode("ascii")
        self._authorization = f"Basic {credentials}"
        self._id_tokens = id_tokens
        self._transport = transport

    @property
    def redirect_uri(self) -> str:
        return f"{self._public_origin}/auth/callback"

    def authorization_url(self, transaction: SignInTransaction) -> str:
        query = urlencode(
            {
                "response_type": "code",
                "client_id": self._client_id,
                "redirect_uri": self.redirect_uri,
                "scope": SCOPES,
                "state": transaction.state,
                "nonce": transaction.nonce,
                "code_challenge": transaction.code_challenge,
                "code_challenge_method": "S256",
            }
        )
        return f"{self._login_origin}/oauth2/authorize?{query}"

    def exchange_code(self, code: str, code_verifier: str) -> IssuedTokens:
        response = self._token_request(
            {
                "grant_type": "authorization_code",
                "client_id": self._client_id,
                "code": code,
                "redirect_uri": self.redirect_uri,
                "code_verifier": code_verifier,
            }
        )
        return self._issued(response, refresh_expected=True)

    def refresh(self, refresh_token: str) -> IssuedTokens:
        response = self._token_request(
            {"grant_type": "refresh_token", "client_id": self._client_id, "refresh_token": refresh_token}
        )
        return self._issued(response, refresh_expected=False)

    def revoke(self, refresh_token: str) -> None:
        response = self._transport.post_form(
            f"{self._login_origin}/oauth2/revoke",
            {"token": refresh_token, "client_id": self._client_id},
            headers={"Authorization": self._authorization},
        )
        if response.status >= 500:
            raise StoreUnavailable("revoke", "managed login", str(response.status))
        if response.status != 200:
            raise TokenRefused(_refusal_reason(response))

    def sign_out_url(self) -> str:
        query = urlencode({"client_id": self._client_id, "logout_uri": f"{self._public_origin}/signed-out"})
        return f"{self._login_origin}/logout?{query}"

    def _token_request(self, fields: Mapping[str, str]) -> HttpResponse:
        response = self._transport.post_form(
            f"{self._login_origin}/oauth2/token", fields, headers={"Authorization": self._authorization}
        )
        if response.status >= 500:
            raise StoreUnavailable("token", "managed login", str(response.status))
        if response.status != 200:
            raise TokenRefused(_refusal_reason(response))
        return response

    def _issued(self, response: HttpResponse, *, refresh_expected: bool) -> IssuedTokens:
        body = _json_object(response.body)
        id_token, access_token = body.get("id_token"), body.get("access_token")
        if not isinstance(id_token, str) or not isinstance(access_token, str):
            raise TokenRefused("managed login returned no tokens")
        refresh_token = body.get("refresh_token")
        if refresh_expected and not isinstance(refresh_token, str):
            raise TokenRefused("managed login returned no refresh token")
        return IssuedTokens(
            identity=self._id_tokens.verify(id_token),
            access_token=access_token,
            refresh_token=refresh_token if isinstance(refresh_token, str) else None,
        )


def _json_object(body: bytes) -> dict[str, object]:
    try:
        value = json.loads(body)
    except ValueError as error:
        raise TokenRefused("managed login's answer is not JSON") from error
    if not isinstance(value, dict):
        raise TokenRefused("managed login's answer is not JSON")
    return cast(dict[str, object], value)


def _refusal_reason(response: HttpResponse) -> str:
    try:
        error = _json_object(response.body).get("error")
    except TokenRefused:
        error = None
    if isinstance(error, str) and error in _OAUTH_ERRORS:
        return f"managed login refused it ({error})"
    return f"managed login refused it (HTTP {response.status})"

"""`POST /login`: trading Tabroom credentials for a caselist_token, once.

The password is taken as a :class:`~pydantic.SecretStr`, revealed only while the request body is
built, and not kept: nothing here stores it, logs it, or puts it in an error. The username is not
logged either. What comes back is the token — itself a `SecretStr` from the moment it is parsed —
and the expiry the API states.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from pydantic import SecretStr, ValidationError

from debate_core.application.ports.caselist_source import (
    CaselistLoginRejected,
    UnexpectedCaselistResponse,
)
from debate_core.integrations.opencaselist.models import LoginResponse
from debate_core.integrations.opencaselist.redaction import logger, register_secret
from debate_core.integrations.opencaselist.transport import OpenCaselistTransport

__all__ = ["IssuedToken", "LoginResource"]


@dataclass(frozen=True, slots=True)
class IssuedToken:
    """What a successful login yields. `repr` shows the token as `**********`."""

    token: SecretStr
    expires_at: datetime | None


class LoginResource:
    """Logging in."""

    def __init__(self, transport: OpenCaselistTransport) -> None:
        self._transport = transport

    async def login(self, username: str, password: SecretStr) -> IssuedToken:
        operation = "log in"
        response = await self._transport.post_json(
            "/login",
            operation=operation,
            body={"username": username, "password": password.get_secret_value(), "remember": True},
            authenticated=False,
            on_auth_refusal=CaselistLoginRejected,
        )
        try:
            answer = LoginResponse.model_validate(response.body)
        except ValidationError:
            raise UnexpectedCaselistResponse(
                operation, "the login answer is not the documented shape"
            ) from None
        if answer.token is None or not answer.token.get_secret_value():
            raise UnexpectedCaselistResponse(operation, "the login answer carries no token")
        register_secret(answer.token.get_secret_value())
        logger.info("OpenCaselist: logged in; a caselist_token was issued")
        return IssuedToken(token=answer.token, expires_at=_parse_expiry(answer.expires))


def _parse_expiry(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None

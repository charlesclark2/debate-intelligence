"""Where botocore's Cognito exceptions stop and :mod:`debate_core.application.errors` begins.

Every call the Cognito adapters make runs inside :func:`mapped_cognito_errors`, which turns a
`ClientError`, a missing credential or an unreachable endpoint into a domain error.

* `UserNotFoundException`: `NotFound("account", <username>)`, or `TokenRefused` from a
  token-authorized call.
* `UsernameExistsException`: `AlreadyExists("account", <username>)`.
* `CodeMismatchException`, `ExpiredCodeException`, `EnableSoftwareTokenMFAException`:
  `CodeRefused`.
* `NotAuthorizedException` from a token-authorized call: `TokenRefused`, the access token was
  revoked.
* `AccessDeniedException`, or `NotAuthorizedException` from an administrative call:
  `StoreAccessDenied`, naming the profile.
* An expired or absent SSO session, `ExpiredTokenException`, `UnrecognizedClientException`:
  `StoreCredentialsExpired`, with the login command.
* A profile the AWS config does not define: `StoreProfileNotConfigured`.
* A throttle, a 5xx, a timeout, or any other code: `StoreUnavailable`, carrying the code.

**What never goes in a message:** Cognito's own message text. It is not this project's sentence
and could one day quote what was sent. A message here is built from the operation, the response
code, the profile and, for an administrative call, the username the coach typed. Never a password,
a code or a token: none of them is passed to this module.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import Final

from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    CredentialRetrievalError,
    NoCredentialsError,
    PartialCredentialsError,
    ProfileNotFound,
    SSOTokenLoadError,
    TokenRetrievalError,
    UnauthorizedSSOTokenError,
)

from debate_core.application.errors import (
    AlreadyExists,
    DomainError,
    NotFound,
    StoreAccessDenied,
    StoreCredentialsExpired,
    StoreProfileNotConfigured,
    StoreUnavailable,
)
from debate_core.application.ports.tub import CodeRefused, TokenRefused

__all__ = ["GRANTS_ARE_LISTED_IN", "THE_USER_POOL", "mapped_cognito_errors", "translate_cognito_error"]

THE_USER_POOL: Final = "the pilot's user pool"
GRANTS_ARE_LISTED_IN: Final = "docs/runbooks/evidence-search.md"

_CODE_REFUSED: Final = frozenset(
    {"CodeMismatchException", "ExpiredCodeException", "EnableSoftwareTokenMFAException"}
)
_EXPIRED_CREDENTIALS: Final = frozenset({"ExpiredTokenException", "UnrecognizedClientException"})


@contextmanager
def mapped_cognito_errors(
    operation: str,
    *,
    profile: str | None = None,
    username: str | None = None,
    token_authorized: bool = False,
    code_kind: str = "authenticator",
) -> Generator[None, None, None]:
    """Run a block of Cognito calls, translating anything botocore raises out of it."""
    try:
        yield
    except (BotoCoreError, ClientError) as error:
        raise translate_cognito_error(
            error,
            operation,
            profile=profile,
            username=username,
            token_authorized=token_authorized,
            code_kind=code_kind,
        ) from error


def translate_cognito_error(
    error: BaseException,
    operation: str,
    *,
    profile: str | None = None,
    username: str | None = None,
    token_authorized: bool = False,
    code_kind: str = "authenticator",
) -> DomainError:
    """The domain error `error` means for `operation`. Total: every input gives an error, none is raised."""
    if isinstance(error, ClientError):
        code = error.response.get("Error", {}).get("Code", "") or "an unknown response"
        return _translate_code(
            code,
            operation,
            profile=profile,
            username=username,
            token_authorized=token_authorized,
            code_kind=code_kind,
        )
    if isinstance(
        error,
        UnauthorizedSSOTokenError
        | SSOTokenLoadError
        | TokenRetrievalError
        | NoCredentialsError
        | PartialCredentialsError
        | CredentialRetrievalError,
    ):
        return StoreCredentialsExpired(
            f"the AWS session for {THE_USER_POOL} is not usable", hint=_login_hint(profile)
        )
    if isinstance(error, ProfileNotFound):
        return StoreProfileNotConfigured(profile, setting="--profile")
    return StoreUnavailable(operation, THE_USER_POOL, type(error).__name__)


def _translate_code(
    code: str,
    operation: str,
    *,
    profile: str | None,
    username: str | None,
    token_authorized: bool,
    code_kind: str,
) -> DomainError:
    if code in _CODE_REFUSED:
        return CodeRefused(code_kind)
    if token_authorized and code in {"NotAuthorizedException", "UserNotFoundException"}:
        return TokenRefused("the access token is no longer accepted")
    if code == "UserNotFoundException":
        return NotFound("account", username or "?")
    if code == "UsernameExistsException":
        return AlreadyExists("account", username or "?")
    if code in {"AccessDeniedException", "NotAuthorizedException"}:
        hint = (
            f"the profile {profile} is signed in but not allowed to call {operation}; "
            f"{GRANTS_ARE_LISTED_IN} lists what TubAccounts may do"
            if profile
            else f"not allowed to call {operation}"
        )
        return StoreAccessDenied(operation, THE_USER_POOL, hint=hint)
    if code in _EXPIRED_CREDENTIALS:
        return StoreCredentialsExpired(
            f"the AWS session for {THE_USER_POOL} is not usable", hint=_login_hint(profile)
        )
    return StoreUnavailable(operation, THE_USER_POOL, code)


def _login_hint(profile: str | None) -> str | None:
    return f"aws sso login --profile {profile}" if profile else None

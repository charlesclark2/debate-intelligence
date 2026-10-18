"""What a failed Bedrock call becomes: retried, or one of the port's errors. No botocore error leaves.

The ModelRouter port promises its callers the errors of :mod:`debate_core.application.errors` and
nothing else, so every `ClientError` and `BotoCoreError` the adapter meets is decided here, once:

Retried, attempts permitting, and raised as below when they run out:

* `ThrottlingException`: :class:`~debate_core.application.errors.ProviderRateLimited`.
* `ServiceUnavailableException`, `ModelNotReadyException`, `InternalServerException`:
  :class:`~debate_core.application.errors.ModelUnavailableError`.

Never retried:

* `AccessDeniedException`, an expired or unrecognised credential, no credentials at all:
  :class:`~debate_core.application.errors.ModelAccessDenied`.
* `ValidationException`, `ResourceNotFoundException`, any other 4xx:
  :class:`~debate_core.application.errors.ModelRequestRejected`.
* `ModelTimeoutException`, `ModelErrorException`, a connection or read timeout, anything else:
  :class:`~debate_core.application.errors.ModelUnavailableError`.

**Only what passes is retried.** A throttle, a model still loading, a service briefly down: the
same request can succeed a moment later. A refusal, a validation error or an unknown model is a
fact about the request, and retrying it would only repeat the refusal (the task spec forbids it).
`ModelTimeoutException` and a read timeout are deliberately not retried either: the model ran,
the call may well have been billed, and a second attempt would run, and bill, it again.
"""

from __future__ import annotations

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
    DomainError,
    ModelAccessDenied,
    ModelRequestRejected,
    ModelUnavailableError,
    ProviderRateLimited,
)

__all__ = [
    "ACCESS_DENIED_CODES",
    "EXPIRED_CREDENTIAL_CODES",
    "PROVIDER",
    "RATE_LIMITED_CODES",
    "RETRIED_CODES",
    "is_retried",
    "translate_bedrock_error",
]

PROVIDER: Final = "bedrock"
"""The provider name every error from this adapter carries, as `models.provider` spells it."""

RATE_LIMITED_CODES: Final = frozenset({"ThrottlingException"})
"""The caller is over its rate: retried, and reported as a rate limit when the attempts run out."""

RETRIED_CODES: Final = RATE_LIMITED_CODES | frozenset(
    {"ServiceUnavailableException", "ModelNotReadyException", "InternalServerException"}
)
"""Every response code a call is retried on. Nothing else is (module docstring)."""

ACCESS_DENIED_CODES: Final = frozenset({"AccessDeniedException"})
"""The credentials are valid and not allowed this call, or the model is not enabled in the account."""

EXPIRED_CREDENTIAL_CODES: Final = frozenset(
    {
        "ExpiredToken",
        "ExpiredTokenException",
        "RequestExpired",
        "InvalidClientTokenId",
        "UnrecognizedClientException",
        "TokenRefreshRequired",
    }
)
"""Response codes that mean the credentials were valid once and are not any more."""

_LOGIN_HINT: Final = "log in again, e.g. `aws sso login` for the profile AWS_PROFILE names"
_GRANT_HINT: Final = (
    "the role needs bedrock:InvokeModel on this model or inference profile, and the model must be "
    "enabled in the account"
)
_CREDENTIAL_ERRORS: Final = (
    UnauthorizedSSOTokenError,
    SSOTokenLoadError,
    TokenRetrievalError,
    NoCredentialsError,
    PartialCredentialsError,
    CredentialRetrievalError,
)
_MESSAGE_LIMIT: Final = 300
"""Longest piece of a provider's own message an error repeats; enough to name the parameter refused."""


def is_retried(error: BaseException) -> bool:
    """Whether a call that failed with `error` should be sent again, attempts permitting."""
    return isinstance(error, ClientError) and response_code_of(error) in RETRIED_CODES


def translate_bedrock_error(error: BaseException, target: str, *, attempts: int = 1) -> DomainError:
    """The port error for `error` on a call addressed to `target` (a model id or inference profile).

    `attempts` is how many times the call was sent, and is named in the message of a failure that
    was retried. Anything this module does not recognise becomes `ModelUnavailableError`, so that
    no botocore exception reaches a service.
    """
    if isinstance(error, ClientError):
        return _translate_response(error, target, attempts)
    if isinstance(error, _CREDENTIAL_ERRORS):
        return ModelAccessDenied(PROVIDER, target, "no usable AWS credentials", hint=_LOGIN_HINT)
    if isinstance(error, ProfileNotFound):
        return ModelAccessDenied(
            PROVIDER,
            target,
            "the AWS profile this run names is not defined in this machine's AWS config",
            hint="set AWS_PROFILE to a profile that is",
        )
    if isinstance(error, BotoCoreError):
        return ModelUnavailableError(PROVIDER, target, _short(str(error)))
    return ModelUnavailableError(PROVIDER, target, f"{type(error).__name__}: {_short(str(error))}")


def response_code_of(error: ClientError) -> str:
    """The `Error.Code` Bedrock returned, or the HTTP status as a string when there was none."""
    response = error.response
    code = response.get("Error", {}).get("Code", "")
    if code:
        return code
    return str(response.get("ResponseMetadata", {}).get("HTTPStatusCode", ""))


def _translate_response(error: ClientError, target: str, attempts: int) -> DomainError:
    code = response_code_of(error)
    message = _short(error.response.get("Error", {}).get("Message", "") or code)
    after = f" after {attempts} attempts" if attempts > 1 else ""
    if code in RATE_LIMITED_CODES:
        return ProviderRateLimited(PROVIDER, f"{target}: {code}{after}: {message}")
    if code in RETRIED_CODES:
        return ModelUnavailableError(PROVIDER, target, f"{code}{after}: {message}")
    if code in ACCESS_DENIED_CODES:
        return ModelAccessDenied(PROVIDER, target, f"{code}: {message}", hint=_GRANT_HINT)
    if code in EXPIRED_CREDENTIAL_CODES:
        return ModelAccessDenied(PROVIDER, target, f"{code}: {message}", hint=_LOGIN_HINT)
    if _is_client_fault(error):
        return ModelRequestRejected(PROVIDER, target, code or "ClientError", message)
    return ModelUnavailableError(PROVIDER, target, f"{code}: {message}")


def _is_client_fault(error: ClientError) -> bool:
    """A 4xx, other than the ones handled above: the request, not the service, is at fault.

    `ModelTimeoutException` (408) and `ModelErrorException` (424) are 4xx by status but say the
    model failed to answer, not that the request was wrong, so they are not rejections.
    """
    if response_code_of(error) in {"ModelTimeoutException", "ModelErrorException"}:
        return False
    status = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    return isinstance(status, int) and 400 <= status < 500


def _short(text: str) -> str:
    """`text` cut to a length an error message can repeat."""
    flat = " ".join(text.split())
    return flat if len(flat) <= _MESSAGE_LIMIT else flat[: _MESSAGE_LIMIT - 1] + "…"

"""One Secrets Manager secret, read and written by name, and never seen by a log (ADR-0020 (2)).

The weekly caselist run keeps two secrets: the coach's Tabroom password, which only the login
task's role reads, and the caselist_token, which only the run's role reads
(`debate-<env>-caselist-tabroom-password`, `debate-<env>-caselist-token`). This module is the one
small client both go through. :class:`ManagedSecret` reads a secret's current value, writes a new
version, and describes it; it holds no value of its own and returns what it reads to its caller.
`v2-e10-t04`'s settings secrets provider is to extend it, not to grow a second one beside it.

## Nothing here reaches a log

botocore writes every request's parameters and every response's body to its own loggers at DEBUG:
`botocore.endpoint` logs `PutSecretValue`'s `SecretString`, and `botocore.parsers` logs
`GetSecretValue`'s answer. Either is the secret in plain text, in a handler this project does not
own. So every call here runs under :func:`quiet_wire_log`, which drops every record those two
loggers make *on the calling thread* while the call is in flight. Records from other threads, and
every record outside a call, pass untouched. A scrubbing filter would not do: it can only replace
a string it already knows, and the value arrives inside JSON, escaped, in a form the caller never
held.

## Nothing here reaches an error

A botocore exception is translated to the application's store errors and raised `from None`, so
nothing botocore said rides along as a `__cause__`. Its messages do not quote a secret today, but a
parameter validation error quotes the value it rejected, and `from None` makes "never" hold
whatever botocore says next. The translated error names the operation, the secret's name and the
response code, and nothing else.

## Where requests go

Only to AWS. The client is built with `ignore_configured_endpoint_urls`, so neither
`AWS_ENDPOINT_URL` nor an `endpoint_url` in the AWS config can send a password somewhere else. Tests
answer through botocore's `before-send` hook or its `Stubber`, never a stand-in endpoint.
"""

from __future__ import annotations

import contextlib
import logging
import threading
from collections.abc import Generator, Mapping
from typing import Any, Final, Protocol, cast

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError, ProfileNotFound

from debate_core.application.errors import (
    DomainError,
    NotFound,
    StoreAccessDenied,
    StoreCredentialsExpired,
    StoreProfileNotConfigured,
    StoreUnavailable,
)

__all__ = [
    "WIRE_LOGGERS",
    "ManagedSecret",
    "SecretsManagerClient",
    "build_secrets_manager_client",
    "quiet_wire_log",
]

WIRE_LOGGERS: Final = ("botocore.endpoint", "botocore.parsers")
"""The botocore loggers that write request parameters and response bodies at DEBUG."""

_NOT_FOUND_CODES: Final = frozenset({"ResourceNotFoundException"})
_ACCESS_DENIED_CODES: Final = frozenset({"AccessDeniedException", "AccessDenied", "DecryptionFailure"})
_EXPIRED_CREDENTIAL_CODES: Final = frozenset(
    {
        "ExpiredToken",
        "ExpiredTokenException",
        "RequestExpired",
        "InvalidClientTokenId",
        "UnrecognizedClientException",
        "TokenRefreshRequired",
    }
)


class SecretsManagerClient(Protocol):
    """The three Secrets Manager calls this module makes, as boto3's client spells them."""

    def get_secret_value(self, *, SecretId: str) -> Mapping[str, Any]: ...  # noqa: N803 - boto3's name

    def put_secret_value(self, *, SecretId: str, SecretString: str) -> Mapping[str, Any]: ...  # noqa: N803

    def describe_secret(self, *, SecretId: str) -> Mapping[str, Any]: ...  # noqa: N803


def build_secrets_manager_client(*, region: str, profile: str | None = None) -> SecretsManagerClient:
    """A Secrets Manager client for `region`, signed by `profile` or the SDK's own chain.

    No profile is what the cloud tasks use: the chain finds the task role. On the coach's Mac the
    profile is the one signed in under `Debate<Env>CaselistCredentialWriter`.
    """
    try:
        session = boto3.session.Session(profile_name=profile, region_name=region)
    except ProfileNotFound:
        raise StoreProfileNotConfigured(profile, setting="--aws-profile") from None
    # botocore has taken this argument since 1.31; the botocore-stubs installed here do not list
    # it (as in debate_core.integrations.s3.client). Narrowed to this one line.
    config = Config(ignore_configured_endpoint_urls=True)  # pyright: ignore[reportCallIssue]
    # No boto3-stubs package is installed for Secrets Manager, so the overload is Unknown; the
    # Protocol above is the part of the client this module relies on.
    client = session.client("secretsmanager", config=config)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    return cast(SecretsManagerClient, client)


# ------------------------------------------------------------------------------------------------
# Keeping botocore's wire log quiet during a call
# ------------------------------------------------------------------------------------------------


class _QuietOnThisThread(logging.Filter):
    """Drops every record made on a thread that is inside :func:`quiet_wire_log`."""

    def __init__(self) -> None:
        super().__init__()
        self._local = threading.local()

    @property
    def depth(self) -> int:
        return cast(int, getattr(self._local, "depth", 0))

    @depth.setter
    def depth(self, value: int) -> None:
        self._local.depth = value

    def filter(self, record: logging.LogRecord) -> bool:
        return self.depth == 0


_QUIET: Final = _QuietOnThisThread()
_install_lock = threading.Lock()
_installed = False


def _install_quiet_filter() -> None:
    global _installed
    with _install_lock:
        if not _installed:
            for name in WIRE_LOGGERS:
                logging.getLogger(name).addFilter(_QUIET)
            _installed = True


@contextlib.contextmanager
def quiet_wire_log() -> Generator[None]:
    """Drop what botocore's wire loggers write on this thread until the block ends."""
    _install_quiet_filter()
    _QUIET.depth += 1
    try:
        yield
    finally:
        _QUIET.depth -= 1


# ------------------------------------------------------------------------------------------------
# One secret
# ------------------------------------------------------------------------------------------------


class ManagedSecret:
    """One secret by name: its current value, a new version of it, and whether it is there."""

    def __init__(
        self, client: SecretsManagerClient, secret_id: str, *, login_hint: str | None = None
    ) -> None:
        self._client = client
        self.secret_id = secret_id
        self._login_hint = login_hint

    def read(self) -> str | None:
        """The current value, or `None` when there is none.

        Terraform creates each secret as an empty shell, and Secrets Manager answers a read of one
        with the same `ResourceNotFoundException` as a secret that does not exist, so the two are
        one answer here. What the caller says about it names the secret, which tells them apart.
        """
        try:
            with self._translated("GetSecretValue"), quiet_wire_log():
                response = self._client.get_secret_value(SecretId=self.secret_id)
        except NotFound:
            return None
        value = response.get("SecretString")
        return value if isinstance(value, str) else None

    def write(self, value: str) -> str | None:
        """Store `value` as a new current version, and return that version's id."""
        with self._translated("PutSecretValue"), quiet_wire_log():
            response = self._client.put_secret_value(SecretId=self.secret_id, SecretString=value)
        version = response.get("VersionId")
        return version if isinstance(version, str) else None

    def describe(self) -> None:
        """Check the secret exists and this identity may see it. Reads no value."""
        with self._translated("DescribeSecret"), quiet_wire_log():
            self._client.describe_secret(SecretId=self.secret_id)

    @contextlib.contextmanager
    def _translated(self, operation: str) -> Generator[None]:
        """Translate what botocore raises into the application's store errors, `from None`."""
        try:
            yield
        except ClientError as error:
            code = str(error.response.get("Error", {}).get("Code", ""))
            raise self._error_for(operation, code) from None
        except NoCredentialsError:
            raise StoreCredentialsExpired(hint=self._login_hint) from None
        except BotoCoreError as error:
            raise StoreUnavailable(operation, self._resource, type(error).__name__) from None

    @property
    def _resource(self) -> str:
        return f"secret {self.secret_id}"

    def _error_for(self, operation: str, code: str) -> DomainError:
        if code in _NOT_FOUND_CODES:
            return NotFound("secret", self.secret_id)
        if code in _ACCESS_DENIED_CODES:
            return StoreAccessDenied(operation, self._resource, hint=self._login_hint)
        if code in _EXPIRED_CREDENTIAL_CODES:
            return StoreCredentialsExpired(
                f"the AWS session for {self._resource} has expired", hint=self._login_hint
            )
        return StoreUnavailable(operation, self._resource, code or "an unknown response")

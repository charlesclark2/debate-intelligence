"""The pilot's audit log: one CloudWatch Logs event per audit record (ADR-0019 (e)).

The group, `debate-<env>-tub-audit`, keeps events 400 days, and no API edits or deletes one. Two
writers use it, each in its own stream:

* the coach's `tub users`, in `tub-users`, which Terraform creates so that the `TubAccounts`
  permission set needs `PutLogEvents` on that one stream and no `CreateLogStream`
  (`create_stream=False`);
* the function, in a stream it creates for its execution environment the first time it writes
  (`create_stream=True`), which its role allows on its own audit group.

A write that fails raises a `StoreError`: the change it records was made, and the caller says so.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import boto3
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
    StoreAccessDenied,
    StoreCredentialsExpired,
    StoreProfileNotConfigured,
    StoreUnavailable,
)
from debate_core.application.ports.tub import AuditSink
from debate_core.application.tub.audit import AuditRecord

if TYPE_CHECKING:
    from mypy_boto3_logs import CloudWatchLogsClient

__all__ = ["ACCOUNT_CHANGES_STREAM", "CloudWatchAuditSink", "build_logs_client"]

ACCOUNT_CHANGES_STREAM: Final = "tub-users"
"""The stream the coach's commands write to (`infrastructure/modules/evidence_search/main.tf`)."""

_THE_AUDIT_LOG: Final = "the pilot's audit log"


def build_logs_client(*, profile: str | None, region: str) -> CloudWatchLogsClient:
    """A CloudWatch Logs client signed with `profile`, or with the function's role when `None`."""
    try:
        session = boto3.session.Session(profile_name=profile, region_name=region)
    except ProfileNotFound as error:
        raise StoreProfileNotConfigured(profile, setting="--profile") from error
    return session.client("logs")  # pyright: ignore[reportUnknownMemberType]


class CloudWatchAuditSink(AuditSink):
    """:class:`~debate_core.application.ports.tub.AuditSink` appending to one stream of one group."""

    def __init__(
        self,
        *,
        client: CloudWatchLogsClient,
        log_group: str,
        log_stream: str,
        create_stream: bool,
        profile: str | None = None,
    ) -> None:
        self._client = client
        self._group = log_group
        self._stream = log_stream
        self._stream_ready = not create_stream
        self._profile = profile

    def record(self, record: AuditRecord) -> None:
        try:
            if not self._stream_ready:
                self._create_stream()
            self._client.put_log_events(
                logGroupName=self._group,
                logStreamName=self._stream,
                logEvents=[{"timestamp": int(record.time.timestamp() * 1000), "message": record.to_json()}],
            )
        except (BotoCoreError, ClientError) as error:
            raise self._translated(error) from error

    def _create_stream(self) -> None:
        try:
            self._client.create_log_stream(logGroupName=self._group, logStreamName=self._stream)
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") != "ResourceAlreadyExistsException":
                raise
        self._stream_ready = True

    def _translated(self, error: BaseException) -> DomainError:
        if isinstance(error, ClientError):
            code = error.response.get("Error", {}).get("Code", "")
            if code == "AccessDeniedException":
                return StoreAccessDenied("PutLogEvents", _THE_AUDIT_LOG, hint=_grant_hint(self._profile))
            if code in {"ExpiredTokenException", "UnrecognizedClientException"}:
                return StoreCredentialsExpired(hint=_login_hint(self._profile))
            return StoreUnavailable("PutLogEvents", _THE_AUDIT_LOG, code or "an unknown response")
        if isinstance(
            error,
            UnauthorizedSSOTokenError
            | SSOTokenLoadError
            | TokenRetrievalError
            | NoCredentialsError
            | PartialCredentialsError
            | CredentialRetrievalError,
        ):
            return StoreCredentialsExpired(hint=_login_hint(self._profile))
        return StoreUnavailable("PutLogEvents", _THE_AUDIT_LOG, type(error).__name__)


def _login_hint(profile: str | None) -> str | None:
    return f"aws sso login --profile {profile}" if profile else None


def _grant_hint(profile: str | None) -> str | None:
    return f"the profile {profile} may not write to this audit stream" if profile else None

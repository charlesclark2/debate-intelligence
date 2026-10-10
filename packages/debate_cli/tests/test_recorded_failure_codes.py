"""One vocabulary of error codes, shared by the services that record a failure and the CLI (`v1-e34-t13`).

A stage of `caselist pull` records the code of each failure that failed it, and the command decides
its exit status from those codes. That only works if a recorded code is the word the CLI reports
the same exception under, so the code lives in `debate_core.application.errors` and
`debate_cli.exit_codes` reads it from there. These tests hold the two together.

Every expected code is written by hand from the class name. The exit rule over codes is in
`test_output.py`, beside the mapping `v1-e01-t20` wrote; the rule over a run's stages is in
`commands/test_caselist_pull.py`.
"""

from __future__ import annotations

import pytest

from debate_cli.exit_codes import ExitCode, error_code_for, exit_code_for, exit_code_for_failure_codes
from debate_cli.output import CommandFailure
from debate_core.application.caselist_sync import DailyDownloadLimitReached
from debate_core.application.errors import (
    UNMODELLED_ERROR_CODE,
    LocalStoreAccessDenied,
    ProviderRateLimited,
    ProviderUnavailable,
    StoreAccessDenied,
    StoreCredentialsExpired,
    StoreUnavailable,
    UnreadableArchive,
    reported_error_code,
)
from debate_core.application.ports.caselist_source import ArchiveUnavailable, CaselistAuthExpired

#: Failures a stage of `caselist pull` records instead of raising, and the code each is recorded
#: under, written by hand from the class name.
RECORDED_FAILURES = [
    (StoreUnavailable("PutObject", "s3://b/k", "503"), "STORE_UNAVAILABLE"),
    (StoreCredentialsExpired(hint="aws sso login"), "STORE_CREDENTIALS_EXPIRED"),
    (StoreAccessDenied("PutObject", "s3://b/k"), "STORE_ACCESS_DENIED"),
    (LocalStoreAccessDenied("read", "the blob directory"), "STORE_ACCESS_DENIED"),
    (ProviderUnavailable("opencaselist", "HTTP 503"), "PROVIDER_UNAVAILABLE"),
    (ProviderRateLimited("opencaselist", retry_after_seconds=30.0), "PROVIDER_RATE_LIMITED"),
    (
        DailyDownloadLimitReached(ProviderRateLimited("opencaselist", retry_after_seconds=86_400.0)),
        "DAILY_DOWNLOAD_LIMIT_REACHED",
    ),
    (ArchiveUnavailable("hsld26-weekly-2026-09-15.zip", 404), "ARCHIVE_UNAVAILABLE"),
    (CaselistAuthExpired(401, "download OpenEv file 512"), "CASELIST_AUTH_EXPIRED"),
    (UnreadableArchive("the download", "not a readable zip file"), "UNREADABLE_ARCHIVE"),
    (PermissionError(13, "Permission denied"), "INTERNAL_ERROR"),
    (OSError(28, "No space left on device"), "INTERNAL_ERROR"),
]


@pytest.mark.parametrize(("failure", "code"), RECORDED_FAILURES, ids=lambda value: str(value)[:28])
def test_a_recorded_failure_has_the_code_the_cli_reports_the_same_exception_under(
    failure: BaseException, code: str
) -> None:
    """One vocabulary (v1-e34-t13): what a stage records for a failure is what `error.code` would
    have been had that failure ended the command."""
    assert reported_error_code(failure) == code
    assert error_code_for(failure) == code


def test_the_unmodelled_code_is_the_name_of_the_internal_error_exit_status() -> None:
    """`debate_core` cannot import the CLI's exit codes, so it spells the word itself; this is what
    keeps the two spellings one."""
    assert ExitCode.INTERNAL_ERROR.name == UNMODELLED_ERROR_CODE


def test_the_daily_limit_is_a_verdict_and_never_a_retrieval_failure() -> None:
    """It arrives as a rate limit and is deliberately not a provider failure: were it to end a
    command, it would end it with `1`."""
    daily = DailyDownloadLimitReached(ProviderRateLimited("opencaselist", retry_after_seconds=86_400.0))

    assert exit_code_for(daily) is ExitCode.DOMAIN_FAILURE
    assert exit_code_for_failure_codes([error_code_for(daily)]) is ExitCode.DOMAIN_FAILURE


def test_a_refusal_by_this_machine_is_the_same_failure_to_a_program_as_one_by_the_bucket() -> None:
    """The filesystem stores' subclass keeps its parent's code and exit status, so nothing that
    branches on `STORE_ACCESS_DENIED` has to learn a second word."""
    refused = LocalStoreAccessDenied("list", "the manifest directory", hint="check storage.data_dir")
    failure = CommandFailure.from_exception(refused)

    assert exit_code_for(refused) is ExitCode.RETRIEVAL_FAILURE
    assert (failure.code, failure.exit_code) == ("STORE_ACCESS_DENIED", ExitCode.RETRIEVAL_FAILURE)
    assert failure.details["resource"] == "the manifest directory"
    assert failure.hint == "check storage.data_dir"

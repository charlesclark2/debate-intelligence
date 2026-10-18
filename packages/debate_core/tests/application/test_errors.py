"""The port error hierarchy: the shape callers catch on, and the facts each error carries.

A use case catches `NotFound`, or `Conflict`, or `DomainError` as a backstop, and an adapter has
to raise something that lands in the right one of those buckets. That is what is checked here —
the hierarchy is part of the contract, not an implementation detail of the messages.
"""

from __future__ import annotations

import pytest

from debate_core.application.errors import (
    AlreadyExists,
    BlobIntegrityError,
    Conflict,
    DomainError,
    InvalidCursor,
    InvalidModelOutput,
    ModelAccessDenied,
    ModelRequestRejected,
    ModelUnavailableError,
    NotFound,
    ProviderError,
    ProviderRateLimited,
    ProviderUnavailable,
    RevisionMismatch,
    SnapshotIntegrityCheck,
    SnapshotIntegrityError,
    StoreCredentialsExpired,
    StoreError,
    StoreProfileNotConfigured,
    error_code_of,
    reported_error_message,
)

EVERY_ERROR = (
    NotFound("Card", "01J"),
    InvalidCursor("nonsense"),
    Conflict("a conflict"),
    AlreadyExists("Card", "01J"),
    RevisionMismatch("Card", "01J", 3, 4),
    BlobIntegrityError("abc123"),
    SnapshotIntegrityError("01J", SnapshotIntegrityCheck.RAW_BYTES_HASH),
    InvalidModelOutput("select-passage", "1.0.0", "missing field"),
    ProviderError("openalex", "broke"),
    ProviderUnavailable("openalex"),
    ModelUnavailableError("bedrock", "a-model"),
    ProviderRateLimited("openalex"),
    ModelAccessDenied("bedrock", "a-model", "not allowed"),
    ModelRequestRejected("bedrock", "a-model", "ValidationException", "bad parameter"),
)


@pytest.mark.parametrize("error", EVERY_ERROR, ids=lambda error: type(error).__name__)
def test_every_port_error_is_a_domain_error(error: DomainError) -> None:
    assert isinstance(error, DomainError)
    assert str(error)


def test_write_conflicts_share_a_base_so_a_caller_can_retry_on_one_except_clause() -> None:
    assert issubclass(AlreadyExists, Conflict)
    assert issubclass(RevisionMismatch, Conflict)
    assert not issubclass(NotFound, Conflict)


def test_provider_failures_share_a_base_and_name_the_provider() -> None:
    assert issubclass(ProviderUnavailable, ProviderError)
    assert issubclass(ProviderRateLimited, ProviderError)
    assert ProviderUnavailable("openalex", "timed out").provider == "openalex"


def test_a_revision_mismatch_carries_both_revisions() -> None:
    error = RevisionMismatch("Card", "01J", 3, 4)
    assert (error.expected_revision, error.actual_revision) == (3, 4)
    assert "expected revision 3" in str(error)
    assert "stored 4" in str(error)


def test_a_revision_mismatch_can_report_that_the_record_is_gone() -> None:
    assert "no longer exists" in str(RevisionMismatch("Card", "01J", 3))


def test_rate_limiting_carries_the_wait_the_provider_asked_for() -> None:
    error = ProviderRateLimited("crossref", retry_after_seconds=30.0)
    assert error.retry_after_seconds == 30.0
    assert "retry after 30.0s" in str(error)


def test_an_unreachable_model_is_a_provider_outage_that_names_the_model() -> None:
    """It keeps PROVIDER_UNAVAILABLE, the code the CLI and `caselist pull` treat as retryable."""
    error = ModelUnavailableError("bedrock", "a-model", "model not ready")
    assert isinstance(error, ProviderUnavailable)
    assert error.model_id == "a-model"
    assert "a-model: model not ready" in str(error)
    assert error_code_of(error) == error_code_of(ProviderUnavailable("bedrock")) == "PROVIDER_UNAVAILABLE"


def test_invalid_model_output_identifies_the_prompt_version_that_produced_it() -> None:
    error = InvalidModelOutput("select-passage", "1.2.0", "end_offset missing", model_id="claude-x")
    assert (error.prompt_id, error.prompt_version, error.model_id) == (
        "select-passage",
        "1.2.0",
        "claude-x",
    )
    assert "select-passage@1.2.0" in str(error)


def test_a_blob_integrity_error_reports_the_digest_the_bytes_actually_have() -> None:
    error = BlobIntegrityError("abc", actual_sha256="def")
    assert error.actual_sha256 == "def"
    assert "def" in str(error)


def test_a_snapshot_integrity_error_names_the_check_and_both_values() -> None:
    """The verifier turns `check` into a reason code, so it is an attribute, not only a message."""
    error = SnapshotIntegrityError(
        "01J", SnapshotIntegrityCheck.NORMALIZED_TEXT_HASH, expected="a" * 64, actual="b" * 64
    )

    assert error.snapshot_id == "01J"
    assert error.check is SnapshotIntegrityCheck.NORMALIZED_TEXT_HASH
    assert (error.expected, error.actual) == ("a" * 64, "b" * 64)
    assert "normalized_text_hash" in str(error)
    assert not isinstance(error, BlobIntegrityError), "a damaged blob and snapshot are reported apart"


def test_a_profile_that_is_not_configured_names_its_setting_and_is_not_an_expired_session() -> None:
    """Its own class and its own code, so that nothing that waits for a login catches it (`v1-e29-t07`)."""
    error = StoreProfileNotConfigured(
        "debate-dev-evidence-typo", setting="storage.s3.aws_profile", hint="correct the setting"
    )

    assert isinstance(error, StoreError)
    assert not isinstance(error, StoreCredentialsExpired)
    assert error_code_of(error) == "STORE_PROFILE_NOT_CONFIGURED"
    assert str(error) == (
        "AWS profile 'debate-dev-evidence-typo', named by storage.s3.aws_profile, is not defined in "
        "this machine's AWS config: correct the setting"
    )
    assert (error.profile, error.setting, error.hint) == (
        "debate-dev-evidence-typo",
        "storage.s3.aws_profile",
        "correct the setting",
    )


def test_a_profile_that_is_not_configured_invents_no_name_and_no_setting() -> None:
    assert (
        str(StoreProfileNotConfigured(None)) == "the AWS profile is not defined in this machine's AWS config"
    )
    assert str(StoreProfileNotConfigured("debate-dev-evidence")) == (
        "AWS profile 'debate-dev-evidence' is not defined in this machine's AWS config"
    )


@pytest.mark.parametrize(
    ("error", "reported"),
    [
        pytest.param(NotFound("Card", "01J"), "Card not found: 01J", id="this project's own sentence"),
        pytest.param(
            PermissionError(13, "Permission denied", "/Users/someone/inbox/A Camp Release.docx"),
            "PermissionError (errno 13)",
            id="an OSError, by its class and errno",
        ),
        pytest.param(
            FileNotFoundError(2, "No such file or directory", "/Users/someone/data/x"),
            "FileNotFoundError (errno 2)",
            id="a subclass, by its own class",
        ),
        pytest.param(OSError("no errno, a path: /Users/someone"), "OSError", id="an OSError with no errno"),
        pytest.param(RuntimeError("a bug quoting /Users/someone"), "RuntimeError", id="anything else"),
    ],
)
def test_a_recorded_failure_quotes_only_what_this_project_wrote(error: BaseException, reported: str) -> None:
    """`v1-e29-t09` ac7: what a result or a message of its own says of a failure that did not end the
    command. An error this project did not write is named, never quoted."""
    assert reported_error_message(error) == reported


@pytest.mark.parametrize("kind", [ModelAccessDenied, ModelRequestRejected])
def test_a_refused_model_call_is_a_provider_failure_no_retry_cures(kind: type[ProviderError]) -> None:
    """Neither is unavailability or rate: retrying the same call gets the same refusal."""
    assert issubclass(kind, ProviderError)
    assert not issubclass(kind, (ProviderUnavailable, ProviderRateLimited))


def test_a_rejected_request_keeps_the_providers_code_and_names_the_model() -> None:
    error = ModelRequestRejected(
        "bedrock", "geo.a-model", "ValidationException", "temperature is not supported"
    )

    assert error.provider_code == "ValidationException"
    assert error.model_id == "geo.a-model"
    assert str(error) == "bedrock: geo.a-model: ValidationException: temperature is not supported"


def test_a_denied_model_call_gives_its_hint() -> None:
    error = ModelAccessDenied("bedrock", "geo.a-model", "no usable credentials", hint="log in again")

    assert error.hint == "log in again"
    assert str(error) == "bedrock: geo.a-model: no usable credentials (log in again)"

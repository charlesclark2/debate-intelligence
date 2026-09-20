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
    NotFound,
    ProviderError,
    ProviderRateLimited,
    ProviderUnavailable,
    RevisionMismatch,
)

EVERY_ERROR = (
    NotFound("Card", "01J"),
    InvalidCursor("nonsense"),
    Conflict("a conflict"),
    AlreadyExists("Card", "01J"),
    RevisionMismatch("Card", "01J", 3, 4),
    BlobIntegrityError("abc123"),
    InvalidModelOutput("select-passage", "1.0.0", "missing field"),
    ProviderError("openalex", "broke"),
    ProviderUnavailable("openalex"),
    ProviderRateLimited("openalex"),
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

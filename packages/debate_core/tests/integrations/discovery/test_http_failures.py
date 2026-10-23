"""The one mapping from an HTTP status and its Retry-After to the port's error types."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from debate_core.application.errors import ProviderRateLimited, ProviderUnavailable
from debate_core.integrations.discovery.http_failures import provider_error_for_status, retry_after_seconds

NOW = datetime(2026, 10, 21, 7, 28, 0, tzinfo=UTC)


@pytest.mark.parametrize("status", [100, 200, 204, 301, 304])
def test_a_status_below_400_is_for_the_adapter_to_read(status: int) -> None:
    assert provider_error_for_status("crossref", status, {}, now=NOW) is None


def test_429_is_rate_limited_with_the_wait_the_provider_stated() -> None:
    error = provider_error_for_status("crossref", 429, {"Retry-After": "120"}, now=NOW)
    assert isinstance(error, ProviderRateLimited)
    assert error.retry_after_seconds == 120.0
    assert str(error) == "crossref: HTTP 429 (retry after 120.0s)"


def test_the_retry_after_header_is_found_whatever_its_case() -> None:
    error = provider_error_for_status("crossref", 429, {"retry-after": "7"}, now=NOW)
    assert isinstance(error, ProviderRateLimited)
    assert error.retry_after_seconds == 7.0


def test_429_without_retry_after_is_still_rate_limited() -> None:
    error = provider_error_for_status("crossref", 429, {}, now=NOW)
    assert isinstance(error, ProviderRateLimited)
    assert error.retry_after_seconds is None


@pytest.mark.parametrize("status", [408, 500, 502, 503, 504])
def test_a_timeout_or_server_error_is_unavailable(status: int) -> None:
    error = provider_error_for_status("crossref", status, {"Retry-After": "30"}, now=NOW)
    assert type(error) is ProviderUnavailable
    assert str(error) == f"crossref: HTTP {status}"


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_any_other_client_error_is_unavailable_and_says_the_request_was_refused(status: int) -> None:
    error = provider_error_for_status("crossref", status, {}, now=NOW)
    assert type(error) is ProviderUnavailable
    assert str(error) == f"crossref: HTTP {status}: the provider refused the request"


@pytest.mark.parametrize(
    ("header", "seconds"),
    [
        ("120", 120.0),
        (" 0 ", 0.0),
        ("Wed, 21 Oct 2026 07:30:00 GMT", 120.0),
        ("Wed, 21 Oct 2026 07:00:00 GMT", 0.0),
        ("not a date", None),
        ("-5", None),
        ("", None),
        (None, None),
    ],
)
def test_retry_after_reads_seconds_or_an_http_date(header: str | None, seconds: float | None) -> None:
    assert retry_after_seconds(header, now=NOW) == seconds


@pytest.mark.parametrize("header", ["²", "١٢٠"], ids=["superscript-two", "arabic-indic-120"])
def test_429_with_digits_that_are_not_ascii_is_rate_limited_with_no_stated_wait(header: str) -> None:
    """`str.isdigit()` accepts both; `float("²")` raised a ValueError out of here (`v1-e07-t08`)."""
    error = provider_error_for_status("crossref", 429, {"Retry-After": header}, now=NOW)
    assert isinstance(error, ProviderRateLimited)
    assert error.retry_after_seconds is None

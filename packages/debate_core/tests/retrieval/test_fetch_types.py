"""FetchResult's invariants: a failed fetch never carries a partial body, and robots is consistent."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from debate_core.domain import AccessStatus
from debate_core.retrieval.fetch_types import (
    FetchResult,
    HttpStatusError,
    RobotsDisallowed,
    RobotsRefusalReason,
    Timeout,
    TimeoutPhase,
    TooLarge,
)
from debate_core.retrieval.fetch_types import FetchResult as PortFetchResult

URL = "https://news.example.org/a"
WHEN = datetime(2026, 10, 21, 9, 0, tzinfo=UTC)


def result(**fields: Any) -> FetchResult:
    return FetchResult(requested_url=URL, final_url=URL, elapsed_ms=1.0, fetched_at=WHEN, **fields)


def robots_refusal() -> RobotsDisallowed:
    return RobotsDisallowed(
        url=URL,
        message="robots.txt on news.example.org refuses this URL (disallowed)",
        robots_url="https://news.example.org/robots.txt",
        reason=RobotsRefusalReason.DISALLOWED,
    )


def test_the_port_names_the_same_class() -> None:
    assert PortFetchResult is FetchResult


def test_a_size_failure_cannot_carry_the_bytes_it_cut_off() -> None:
    too_large = TooLarge(url=URL, message="too big", limit_bytes=1024, received_bytes=2048)
    with pytest.raises(ValidationError, match="must have an empty body"):
        result(body=b"x" * 2048, error=too_large)


def test_a_timeout_cannot_carry_a_partial_body() -> None:
    timeout = Timeout(url=URL, message="slow", phase=TimeoutPhase.TOTAL, limit_seconds=30.0)
    with pytest.raises(ValidationError, match="must have an empty body"):
        result(body=b"<html>half", error=timeout)


def test_an_error_status_keeps_its_body() -> None:
    error = HttpStatusError(url=URL, message="403", status_code=403, attempts=1)
    assert result(status_code=403, body=b"challenge", error=error).body == b"challenge"


def test_an_error_status_must_match_the_results_status() -> None:
    error = HttpStatusError(url=URL, message="404", status_code=404, attempts=1)
    with pytest.raises(ValidationError, match="own status_code"):
        result(status_code=410, error=error)


def test_a_robots_refusal_is_recorded_as_robots_disallowed() -> None:
    assert (
        result(error=robots_refusal(), access_status=AccessStatus.ROBOTS_DISALLOWED).error == robots_refusal()
    )
    with pytest.raises(ValidationError, match="ROBOTS_DISALLOWED exactly when"):
        result(error=robots_refusal())


def test_robots_disallowed_without_a_robots_refusal_is_rejected() -> None:
    with pytest.raises(ValidationError, match="ROBOTS_DISALLOWED exactly when"):
        result(access_status=AccessStatus.ROBOTS_DISALLOWED)


def test_each_error_reads_back_from_json_as_its_own_type() -> None:
    original = result(error=robots_refusal(), access_status=AccessStatus.ROBOTS_DISALLOWED)
    restored = FetchResult.model_validate_json(original.model_dump_json())
    assert type(restored.error) is RobotsDisallowed
    assert restored == original

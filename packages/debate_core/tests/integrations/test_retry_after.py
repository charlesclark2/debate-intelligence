"""The one `Retry-After` reader every HTTP adapter shares, and the clock its date form reads (`v1-e07-t08`).

The date form is a distance from the caller's injected clock: these read it from a
:class:`~debate_core.testing.fakes.clock_and_ids.FixedClock`, so each wait is exact. The malformed
headers are read as they were before the reader was shared: digits only for the discovery mapping
and the article fetcher, anything `float()` reads for OpenCaselist's transport (`any_number`).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from debate_core.integrations.retry_after import retry_after_seconds
from debate_core.testing.fakes.clock_and_ids import FixedClock

NOW = datetime(2030, 10, 21, 7, 28, 0, tzinfo=UTC)
"""Years ahead of the real now, so a reader that looked at the wall clock would give other answers."""


@pytest.mark.parametrize("any_number", [False, True])
@pytest.mark.parametrize(
    ("header", "seconds"),
    [
        pytest.param("Mon, 21 Oct 2030 07:30:00 GMT", 120.0, id="two-minutes-ahead"),
        pytest.param("Mon, 21 Oct 2030 07:28:00 GMT", 0.0, id="now"),
        pytest.param("Mon, 21 Oct 2030 07:00:00 GMT", 0.0, id="already-past"),
        pytest.param("Mon, 21 Oct 2030 09:30:00 +0200", 120.0, id="ahead-in-another-zone"),
        pytest.param("21 Oct 2030 07:30:00", 120.0, id="no-zone-is-utc"),
    ],
)
def test_a_date_is_measured_from_the_clock_it_is_given(header: str, seconds: float, any_number: bool) -> None:
    assert retry_after_seconds(header, now=FixedClock(NOW).now(), any_number=any_number) == seconds


def test_the_same_date_asks_for_less_as_the_clock_moves_on() -> None:
    clock = FixedClock(NOW)
    header = "Mon, 21 Oct 2030 07:30:00 GMT"

    first = retry_after_seconds(header, now=clock.now())
    clock.advance(timedelta(seconds=90))
    second = retry_after_seconds(header, now=clock.now())
    clock.advance(timedelta(hours=1))
    third = retry_after_seconds(header, now=clock.now())

    assert (first, second, third) == (120.0, 30.0, 0.0)


@pytest.mark.parametrize("any_number", [False, True])
def test_a_number_of_seconds_does_not_read_the_clock(any_number: bool) -> None:
    moments = [NOW, NOW + timedelta(days=400), NOW - timedelta(days=400)]
    assert {retry_after_seconds(" 120 ", now=moment, any_number=any_number) for moment in moments} == {120.0}


@pytest.mark.parametrize(
    ("header", "seconds"),
    [
        pytest.param("soon", None, id="words"),
        pytest.param("Mon, 99 Foo 2030", None, id="a-broken-date"),
        pytest.param("1.5", None, id="a-fraction"),
        pytest.param("-5", None, id="a-negative-number"),
        pytest.param("+5", None, id="a-signed-number"),
        pytest.param("1e2", None, id="an-exponent"),
        pytest.param("", None, id="empty"),
        pytest.param("   ", None, id="blank"),
        pytest.param(None, None, id="absent"),
    ],
)
def test_a_malformed_header_is_no_wait_to_the_discovery_mapping_and_the_fetcher(
    header: str | None, seconds: float | None
) -> None:
    """RFC 9110's `delay-seconds` is digits only; anything else that is not a date is unreadable."""
    assert retry_after_seconds(header, now=NOW) == seconds


@pytest.mark.parametrize(
    ("header", "seconds"),
    [
        pytest.param("soon", None, id="words"),
        pytest.param("Mon, 99 Foo 2030", None, id="a-broken-date"),
        pytest.param("1.5", 1.5, id="a-fraction"),
        pytest.param("-5", 0.0, id="a-negative-number"),
        pytest.param("+5", 5.0, id="a-signed-number"),
        pytest.param("1e2", 100.0, id="an-exponent"),
        pytest.param("", None, id="empty"),
        pytest.param(None, None, id="absent"),
    ],
)
def test_any_number_reads_the_seconds_form_as_opencaselist_always_did(
    header: str | None, seconds: float | None
) -> None:
    assert retry_after_seconds(header, now=NOW, any_number=True) == seconds

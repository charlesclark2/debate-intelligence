"""The one `Retry-After` reader every HTTP adapter shares, and the clock its date form reads (`v1-e07-t08`).

The date form is a distance from the caller's injected clock: these read it from a
:class:`~debate_core.testing.fakes.clock_and_ids.FixedClock`, so each wait is exact. The seconds form
is ASCII digits only, for every adapter (the PM's rulings on `v1-e07-t08`): OpenCaselist's `float()`
reading, under which `nan` hung the transport, is gone, and a digit `float()` cannot read (`²`) is
unreadable rather than a `ValueError`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from debate_core.integrations.retry_after import retry_after_seconds
from debate_core.testing.fakes.clock_and_ids import FixedClock

NOW = datetime(2030, 10, 21, 7, 28, 0, tzinfo=UTC)
"""Years ahead of the real now, so a reader that looked at the wall clock would give other answers."""


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
def test_a_date_is_measured_from_the_clock_it_is_given(header: str, seconds: float) -> None:
    assert retry_after_seconds(header, now=FixedClock(NOW).now()) == seconds


def test_the_same_date_asks_for_less_as_the_clock_moves_on() -> None:
    clock = FixedClock(NOW)
    header = "Mon, 21 Oct 2030 07:30:00 GMT"

    first = retry_after_seconds(header, now=clock.now())
    clock.advance(timedelta(seconds=90))
    second = retry_after_seconds(header, now=clock.now())
    clock.advance(timedelta(hours=1))
    third = retry_after_seconds(header, now=clock.now())

    assert (first, second, third) == (120.0, 30.0, 0.0)


def test_a_number_of_seconds_does_not_read_the_clock() -> None:
    moments = [NOW, NOW + timedelta(days=400), NOW - timedelta(days=400)]
    assert {retry_after_seconds(" 120 ", now=moment) for moment in moments} == {120.0}


@pytest.mark.parametrize(
    ("header", "seconds"),
    [
        pytest.param("soon", None, id="words"),
        pytest.param("Mon, 99 Foo 2030", None, id="a-broken-date"),
        pytest.param("1.5", None, id="a-fraction"),
        pytest.param("-5", None, id="a-negative-number"),
        pytest.param("+5", None, id="a-signed-number"),
        pytest.param("1e2", None, id="an-exponent"),
        pytest.param("nan", None, id="nan"),
        pytest.param("inf", None, id="inf"),
        pytest.param("\u00b2", None, id="a-superscript-digit"),
        pytest.param("\u0661\u0662\u0660", None, id="arabic-indic-digits"),
        pytest.param("\uff11\uff12\uff10", None, id="fullwidth-digits"),
        pytest.param("", None, id="empty"),
        pytest.param("   ", None, id="blank"),
        pytest.param(None, None, id="absent"),
    ],
)
def test_anything_but_ascii_digits_or_a_date_is_unreadable(header: str | None, seconds: float | None) -> None:
    """RFC 9110's `delay-seconds` is `1*DIGIT`, ASCII digits. `str.isdigit()` also accepts `²`, which
    `float()` then refuses, and other scripts' digits; none of them is a wait."""
    assert retry_after_seconds(header, now=NOW) == seconds

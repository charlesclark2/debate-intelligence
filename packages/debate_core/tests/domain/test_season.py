"""The season a date falls in, 1 August to 31 July (`v1-e39-t28` moved it here from the backfile command)."""

from __future__ import annotations

from datetime import date

import pytest

from debate_core.domain.season import SEASON_STARTS_IN_MONTH, current_season_start


@pytest.mark.parametrize(
    ("today", "start"),
    [
        (date(2026, 7, 31), 2025),
        (date(2026, 8, 1), 2026),
        (date(2026, 10, 31), 2026),
        (date(2026, 12, 31), 2026),
        (date(2027, 1, 1), 2026),
        (date(2027, 7, 31), 2026),
        (date(2027, 8, 1), 2027),
    ],
)
def test_a_season_starts_on_1_august(today: date, start: int) -> None:
    assert SEASON_STARTS_IN_MONTH == 8
    assert current_season_start(today) == start

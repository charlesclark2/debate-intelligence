"""Weekly trends on the synthetic caselists (`v1-e32-t04` ac1, ac2, ac3).

Every expected value was worked out by hand: the three-window caselist's in
`tests/fixtures/landscape/synthetic_caselist/README.md` ("Trends") and its `expected_trends.csv`,
the topic-change caselist's in its README, and the boundary cases below from their own small tables
(working agreement 6).
"""

from __future__ import annotations

import csv
import dataclasses
from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest

from debate_core.application.landscape_counts import CountedReads, CountedRound
from debate_core.application.landscape_report import LandscapeReportInputs, LandscapeReportService
from debate_core.application.landscape_trends import TrendsCrossTopics, landscape_trends
from debate_core.domain.caselist import Disclosure, RoundLabel
from debate_core.domain.landscape import Taxonomy
from debate_core.domain.landscape_trends import LandscapeTrends, TrendLabel, TrendRow, WeeklyTeams
from debate_core.testing.landscape_report import (
    SYNTHETIC_THIRD_SNAPSHOT,
    TOPIC_CHANGE_CASELIST,
    TOPIC_CHANGE_SNAPSHOT,
    read_synthetic_caselist,
    read_topic_change_caselist,
    synthetic_staleness,
)

REPO = Path(__file__).resolve().parents[4]
FIXTURES = REPO / "tests" / "fixtures" / "landscape"
FIXTURE = FIXTURES / "synthetic_caselist"
TOPIC_CHANGE = FIXTURES / "topic_change_caselist"
FIRST, SECOND, THIRD = date(2026, 9, 8), date(2026, 9, 15), SYNTHETIC_THIRD_SNAPSHOT
KK_RENAMED = "Driftwood Fictional/Driftwood Fictional KK/DriftwoodFictional-KK-Aff-2-ImaginaryClassic-R1.docx"


def _trends(inputs: LandscapeReportInputs, **options: object) -> LandscapeTrends:
    report, counted = LandscapeReportService().count(
        inputs, synthetic_staleness(caselist=inputs.caselist, newest_snapshot=inputs.through)
    )
    return landscape_trends(
        caselist=inputs.caselist,
        taxonomy=inputs.taxonomy,
        counted=counted,
        snapshot=report.header.snapshot,
        snapshot_topics=inputs.snapshot_topics,
        topic_range=inputs.topic_range,
        **options,  # pyright: ignore[reportArgumentType]
    )


def _through(day: date) -> LandscapeReportInputs:
    return read_synthetic_caselist(FIXTURE, through=day)


def _row(trends: LandscapeTrends, position_id: str) -> TrendRow:
    return next(row for row in trends.rows if row.position_id == position_id)


# ------------------------------------------------------------------------------------------------
# The three-window caselist (ac1)
# ------------------------------------------------------------------------------------------------


def test_the_third_window_matches_the_hand_computed_expected_rows() -> None:
    trends = _trends(_through(THIRD))
    with (FIXTURE / "expected_trends.csv").open(encoding="utf-8", newline="") as stream:
        expected = list(csv.DictReader(stream))
    assert [row.position_id for row in trends.rows] == [one["position_id"] for one in expected]
    for row, one in zip(trends.rows, expected, strict=True):
        assert (row.label, row.kind.value, row.trend.value) == (one["label"], one["kind"], one["trend_label"])
        assert (str(row.weekly_teams), str(row.previous_teams)) == (
            one["weekly_teams"],
            one["previous_teams"],
        )
        assert row.held_back_by_team_floor is (one["held_back_by_team_floor"] == "true")


def test_the_third_windows_denominators_are_its_first_seen_rounds_teams() -> None:
    trends = _trends(_through(THIRD))
    # Aff: XX, ZZ, VV. Neg: YY, QQ, KK. The week before, 4 and 4, with VV's b7 on no side making 8.
    assert trends.weekly == WeeklyTeams(snapshot=THIRD, aff_teams=3, neg_teams=3, teams=6)
    assert trends.previous == WeeklyTeams(snapshot=SECOND, aff_teams=4, neg_teams=4, teams=8)
    assert (trends.previous_snapshot, trends.topic_change, trends.windows) == (
        SECOND,
        None,
        (FIRST, SECOND, THIRD),
    )


def test_shares_and_deltas_are_exact_fractions() -> None:
    trends = _trends(_through(THIRD))
    innovation, single_payer = _row(trends, "innovation-advantage"), _row(trends, "single-payer-aff")
    assert (innovation.weekly_share, innovation.previous_share, innovation.delta_points) == (
        Fraction(1),
        Fraction(1, 2),
        Fraction(50),
    )
    assert single_payer.delta_points == Fraction(-50, 3)


def test_the_t03_bundles_snapshot_compares_the_second_window_with_the_first() -> None:
    trends = _trends(_through(SECOND))
    labels = {row.position_id: row.trend for row in trends.rows}
    assert labels == {
        "single-payer-aff": TrendLabel.STEADY,
        "public-option-aff": TrendLabel.STEADY,
        "costs-advantage": TrendLabel.FALLING,
        "innovation-advantage": TrendLabel.STEADY,
        "condo-bad": TrendLabel.NEW,
        "election-da": TrendLabel.STEADY,
        "hospital-closures-da": TrendLabel.NEW,
        "provider-strikes-da": TrendLabel.NEW,
        "spending-da": TrendLabel.FALLING,
        "states-cp": TrendLabel.STEADY,
        "cap-k": TrendLabel.STEADY,
        "nhi-t": TrendLabel.STEADY,
    }
    held = {row.position_id for row in trends.rows if row.held_back_by_team_floor}
    assert held == {"single-payer-aff", "public-option-aff", "innovation-advantage", "states-cp"}
    assert (_row(trends, "costs-advantage").delta_points, _row(trends, "spending-da").delta_points) == (
        -25,
        -50,
    )


# ------------------------------------------------------------------------------------------------
# First seen: keyed on content and team, never on the path
# ------------------------------------------------------------------------------------------------


def test_a_file_carried_into_a_later_window_under_a_new_path_is_not_a_new_disclosure() -> None:
    inputs = _through(THIRD)
    renamed = [one for one in inputs.disclosures if one.source_path == KK_RENAMED]
    assert [(one.snapshot, one.team_code) for one in renamed] == [(THIRD, "KK")]
    trends = _trends(inputs)
    # KK's a4 is its round first seen on 2026-09-15: not one of the third window's aff teams or reads.
    assert trends.weekly.aff_teams == 3
    assert (
        _row(trends, "innovation-advantage").weekly_teams,
        _row(trends, "costs-advantage").weekly_teams,
    ) == (3, 0)


def test_the_same_file_read_in_a_new_round_is_a_new_disclosure() -> None:
    """The control for the rename case: the same bytes for another round are that round's."""
    inputs = _through(THIRD)
    as_a_new_round = tuple(
        one.evolve(tournament="Later Tournament", round_label=RoundLabel.from_raw("R5"))
        if one.source_path == KK_RENAMED
        else one
        for one in inputs.disclosures
    )
    trends = _trends(dataclasses.replace(inputs, disclosures=as_a_new_round))
    assert trends.weekly.aff_teams == 4
    assert (
        _row(trends, "innovation-advantage").weekly_teams,
        _row(trends, "costs-advantage").weekly_teams,
    ) == (4, 1)


def test_renaming_every_path_changes_no_trend() -> None:
    inputs = _through(THIRD)

    def renamed(one: Disclosure, index: int) -> Disclosure:
        return one.evolve(source_path=f"{one.school}/{one.school} {one.team_code}/renamed-{index}.docx")

    shuffled = tuple(renamed(one, index) for index, one in enumerate(inputs.disclosures))
    assert _trends(dataclasses.replace(inputs, disclosures=shuffled)) == _trends(inputs)


# ------------------------------------------------------------------------------------------------
# A caselist's first snapshot (ac2)
# ------------------------------------------------------------------------------------------------


def test_a_caselists_first_snapshot_is_all_new_with_no_deltas() -> None:
    trends = _trends(_through(FIRST))
    assert trends.rows
    assert {row.trend for row in trends.rows} == {TrendLabel.NEW}
    assert all(row.previous_share is None and row.delta_points is None for row in trends.rows)
    assert (trends.previous_snapshot, trends.previous, trends.held_back) == (None, None, 0)
    assert {row.position_id for row in trends.rows} == {
        "single-payer-aff",
        "public-option-aff",
        "costs-advantage",
        "innovation-advantage",
        "spending-da",
        "election-da",
        "states-cp",
        "cap-k",
        "nhi-t",
    }


# ------------------------------------------------------------------------------------------------
# The threshold and the team floor (ac2), on a small world of their own
# ------------------------------------------------------------------------------------------------

LAST_WEEK, THIS_WEEK = date(2026, 10, 13), date(2026, 10, 20)
TWENTY = 20
"""Twenty negative teams disclose in each week, so one team is exactly 5 points."""


def _world(last_week: int, this_week: int) -> CountedReads:
    """Twenty neg teams a week; `last_week` and `this_week` of them read the Spending DA.

    One more team read it the week before last, so it is not NEW.
    """
    rounds: dict[str, CountedRound] = {}
    reads: set[str] = set()
    for week, readers in ((LAST_WEEK, last_week), (THIS_WEEK, this_week)):
        for team in range(TWENTY):
            name = f"{week.isoformat()}-{team}"
            rounds[name] = CountedRound(side="neg", team=("school", f"t{week.day}{team}"), first_seen=week)
            if team < readers:
                reads.add(name)
    rounds["earliest"] = CountedRound(side="neg", team=("school", "early"), first_seen=date(2026, 10, 6))
    reads.add("earliest")
    return CountedReads(rounds=rounds, reads={"spending-da": frozenset(reads)})


def _world_trend(counted: CountedReads, **options: object) -> TrendRow:
    trends = landscape_trends(
        caselist="synthpolicy26",
        taxonomy=_taxonomy(),
        counted=counted,
        snapshot=THIS_WEEK,
        **options,  # pyright: ignore[reportArgumentType]
    )
    return _row(trends, "spending-da")


def _taxonomy() -> Taxonomy:
    return read_synthetic_caselist(FIXTURE).taxonomy


@pytest.mark.parametrize(
    ("last_week", "this_week", "expected", "held"),
    [
        (4, 5, TrendLabel.RISING, False),
        (5, 4, TrendLabel.FALLING, False),
        (2, 3, TrendLabel.RISING, False),
        (3, 2, TrendLabel.FALLING, False),
        (1, 2, TrendLabel.STEADY, True),
        (2, 1, TrendLabel.STEADY, True),
        (0, 2, TrendLabel.STEADY, True),
        (7, 7, TrendLabel.STEADY, False),
    ],
)
def test_a_change_of_exactly_the_threshold_moves_only_with_enough_teams(
    last_week: int, this_week: int, expected: TrendLabel, held: bool
) -> None:
    row = _world_trend(_world(last_week, this_week))
    assert abs(row.delta_points or 0) == 5 * abs(this_week - last_week)
    assert (row.trend, row.held_back_by_team_floor) == (expected, held)


def test_a_change_below_the_configured_threshold_is_steady_and_not_held_back() -> None:
    row = _world_trend(_world(4, 5), threshold_points=Decimal("5.1"))
    assert (row.trend, row.held_back_by_team_floor) == (TrendLabel.STEADY, False)


def test_the_team_floor_is_configurable() -> None:
    assert _world_trend(_world(1, 2), minimum_teams=2).trend is TrendLabel.RISING
    assert _world_trend(_world(2, 3), minimum_teams=4).held_back_by_team_floor


def test_the_threshold_and_floor_must_mean_something() -> None:
    with pytest.raises(ValueError, match="above 0 points"):
        _world_trend(_world(4, 5), threshold_points=Decimal(0))
    with pytest.raises(ValueError, match="at least one team"):
        _world_trend(_world(4, 5), minimum_teams=0)


def test_a_position_read_last_week_and_not_this_week_still_has_a_row() -> None:
    row = _world_trend(_world(6, 0))
    assert (row.weekly_teams, row.previous_teams, row.delta_points, row.trend) == (
        0,
        6,
        Fraction(-30),
        TrendLabel.FALLING,
    )


def test_a_week_with_no_team_on_the_side_gives_no_delta() -> None:
    counted = _world(4, 5)
    aff_only = {
        one: dataclasses.replace(stated, side="aff") if stated.first_seen == LAST_WEEK else stated
        for one, stated in counted.rounds.items()
    }
    row = _world_trend(CountedReads(rounds=aff_only, reads=counted.reads))
    assert (row.previous_share, row.delta_points, row.trend) == (None, None, TrendLabel.STEADY)


# ------------------------------------------------------------------------------------------------
# Topics (ac3)
# ------------------------------------------------------------------------------------------------


def test_no_trend_crosses_a_topic_change_and_the_trends_say_it_changed() -> None:
    inputs = read_topic_change_caselist(TOPIC_CHANGE)
    trends = _trends(inputs)
    assert (trends.caselist, trends.snapshot, trends.topic_id) == (
        TOPIC_CHANGE_CASELIST,
        TOPIC_CHANGE_SNAPSHOT,
        "synthetic-ld-sep-oct",
    )
    assert trends.topic_change is not None
    assert (trends.topic_change.previous_snapshot, trends.topic_change.previous_topic_id) == (
        date(2026, 8, 25),
        "synthetic-ld-jul-aug",
    )
    assert (trends.previous_snapshot, trends.previous, trends.windows) == (
        None,
        None,
        (TOPIC_CHANGE_SNAPSHOT,),
    )
    assert [(row.position_id, row.trend, row.weekly_teams) for row in trends.rows] == [
        ("restored-ecosystems-contention", TrendLabel.NEW, 1),
        ("biopower-k", TrendLabel.NEW, 1),
    ]
    assert all(row.previous_share is None and row.delta_points is None for row in trends.rows)


def test_a_round_from_the_other_topic_is_refused() -> None:
    inputs = read_topic_change_caselist(TOPIC_CHANGE, with_the_old_topic=True)
    with pytest.raises(TrendsCrossTopics, match="synthetic-ld-jul-aug"):
        _trends(inputs)


def test_without_a_topic_map_the_old_topics_disclosures_would_have_made_a_comparison() -> None:
    """The control for the refusal: the topic map is what stops it, not the disclosures alone."""
    inputs = read_topic_change_caselist(TOPIC_CHANGE, with_the_old_topic=True)
    trends = _trends(dataclasses.replace(inputs, snapshot_topics=None))
    assert trends.previous_snapshot == date(2026, 8, 25)


def test_the_topic_range_says_whether_the_windows_span_a_full_cycle() -> None:
    inputs = read_topic_change_caselist(TOPIC_CHANGE)
    assert (inputs.topic_range, _trends(inputs).covers_full_topic_cycle) == (
        (date(2026, 9, 1), date(2026, 10, 31)),
        False,
    )
    assert _trends(_through(THIRD)).covers_full_topic_cycle is None
    full = dataclasses.replace(_through(THIRD), topic_range=(date(2026, 9, 2), date(2026, 9, 28)))
    assert _trends(full).covers_full_topic_cycle is True
    late_start = dataclasses.replace(_through(THIRD), topic_range=(date(2026, 9, 1), date(2026, 9, 28)))
    assert _trends(late_start).covers_full_topic_cycle is False


def test_snapshot_topics_for_the_report_topic_add_empty_windows() -> None:
    inputs = _through(THIRD)
    topics: Mapping[date, str] = {
        day: inputs.taxonomy.topic_id for day in (date(2026, 9, 1), FIRST, SECOND, THIRD)
    }
    trends = _trends(dataclasses.replace(inputs, snapshot_topics=topics))
    assert trends.windows == (date(2026, 9, 1), FIRST, SECOND, THIRD)
    assert trends.previous_snapshot == SECOND

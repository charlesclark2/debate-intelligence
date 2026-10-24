"""The per-school view on the synthetic caselist (`v1-e32-t04` ac4).

The expected rows were worked out by hand from the fixture's table in
`scripts/make_landscape_fixture.py` (working agreement 6): each team's rounds through 2026-09-15 and
the positions the report counts them as reading, with no ANSWERS, nothing below the threshold and no
placement on the other side.
"""

from __future__ import annotations

import dataclasses
import random
from collections import Counter
from datetime import date
from pathlib import Path

from debate_core.application.landscape_counts import round_id
from debate_core.application.landscape_report import LandscapeReportInputs, LandscapeReportService
from debate_core.application.landscape_schools import school_view
from debate_core.domain.caselist import Disclosure, RoundLabel
from debate_core.domain.landscape_report import AffAssignment
from debate_core.domain.landscape_schools import SchoolView
from debate_core.testing.landscape_report import read_synthetic_caselist, synthetic_staleness

REPO = Path(__file__).resolve().parents[4]
FIXTURE = REPO / "tests" / "fixtures" / "landscape" / "synthetic_caselist"
ASH, BIRCH, CEDAR, DRIFT = (
    "Ashgrove Fictional",
    "Birchmoor Fictional",
    "Cedarvale Fictional",
    "Driftwood Fictional",
)
FI, IC = "Fictional Invitational", "Imaginary Classic"

EXPECTED = [
    (ASH, "XX", "aff", "costs-advantage", 2, IC),
    (ASH, "XX", "aff", "single-payer-aff", 2, IC),
    (ASH, "YY", "neg", "cap-k", 1, IC),
    (ASH, "YY", "neg", "election-da", 1, IC),
    (ASH, "YY", "neg", "hospital-closures-da", 1, IC),
    (ASH, "YY", "neg", "spending-da", 1, FI),
    (ASH, "YY", "neg", "states-cp", 1, FI),
    (BIRCH, "QQ", "aff", "condo-bad", 1, IC),
    (BIRCH, "QQ", "aff", "costs-advantage", 1, IC),
    (BIRCH, "QQ", "neg", "cap-k", 1, FI),
    (BIRCH, "QQ", "neg", "spending-da", 1, FI),
    (BIRCH, "ZZ", "aff", "costs-advantage", 1, FI),
    (BIRCH, "ZZ", "aff", "innovation-advantage", 1, FI),
    (BIRCH, "ZZ", "neg", "spending-da", 1, IC),
    (BIRCH, "ZZ", "neg", "states-cp", 1, IC),
    (CEDAR, "VV", "aff", "costs-advantage", 1, FI),
    (CEDAR, "VV", "aff", "public-option-aff", 1, FI),
    (CEDAR, "WW", "neg", "nhi-t", 2, IC),
    (CEDAR, "WW", "neg", "election-da", 1, FI),
    (CEDAR, "WW", "neg", "provider-strikes-da", 1, IC),
    (DRIFT, "JJ", "aff", "innovation-advantage", 1, IC),
    (DRIFT, "JJ", "aff", "single-payer-aff", 1, IC),
    (DRIFT, "JJ", "neg", "spending-da", 1, FI),
    (DRIFT, "JJ", "neg", "states-cp", 1, FI),
    (DRIFT, "KK", "aff", "costs-advantage", 1, IC),
    (DRIFT, "KK", "aff", "innovation-advantage", 1, IC),
]
"""Through 2026-09-15: school, team code, side, position, rounds, last tournament, in view order."""


def _view(inputs: LandscapeReportInputs | None = None) -> SchoolView:
    inputs = inputs or read_synthetic_caselist(FIXTURE)
    report, counted = LandscapeReportService().count(inputs, synthetic_staleness())
    return school_view(
        caselist=inputs.caselist,
        snapshot=report.header.snapshot,
        disclosures=inputs.disclosures,
        counted=counted,
    )


def _rows(view: SchoolView) -> list[tuple[str, str, str, str, int, str | None]]:
    return [
        (row.school, row.team_code, row.side.value, row.position_id, row.rounds, row.last_tournament)
        for row in view.rows
    ]


def test_the_view_matches_the_hand_computed_rows() -> None:
    view = _view()
    assert _rows(view) == EXPECTED
    assert (view.schools, view.teams, view.rounds_with_no_team, view.rounds_on_no_side) == (4, 8, 0, 1)


def test_each_positions_rows_and_the_left_out_rounds_make_the_reports_rounds() -> None:
    inputs = read_synthetic_caselist(FIXTURE)
    report = LandscapeReportService().build(inputs, synthetic_staleness())
    by_position = Counter[str]()
    for row in _view(inputs).rows:
        by_position[row.position_id] += row.rounds
    # VV's b7, on no readable side, is the Capitalism K's third round.
    assert {stats.position_id: stats.rounds for stats in report.positions} == {**by_position, "cap-k": 3}


def test_answers_below_threshold_and_other_side_placements_are_not_rows() -> None:
    rows = {(code, side, position) for _, code, side, position, _, _ in _rows(_view())}
    # b1's answer to the Costs advantage (YY, JJ), a2's Public option at 0.5 (ZZ), b3's Courts CP at
    # 0.5 (WW), a6's Spending DA block in an aff round (JJ), b8's answer to PICs bad (KK).
    for absent in (
        ("YY", "neg", "costs-advantage"),
        ("JJ", "neg", "costs-advantage"),
        ("ZZ", "aff", "public-option-aff"),
        ("WW", "neg", "courts-cp"),
        ("JJ", "aff", "spending-da"),
        ("KK", "neg", "pics-bad"),
    ):
        assert absent not in rows
    assert not any(code == "KK" and side == "neg" for code, side, _ in rows)


def test_an_assigned_aff_reaches_the_view_through_the_seam() -> None:
    inputs = read_synthetic_caselist(FIXTURE)
    first_round = next(
        one for one in inputs.disclosures if one.source_sha256 == "a1" * 32 and one.tournament == FI
    )
    assigned = AffAssignment(
        round_id=round_id(first_round), position_id="public-option-aff", method="PLAN_TEXT"
    )
    view = _view(dataclasses.replace(inputs, aff_assignments=(assigned,)))
    xx = [row for row in _rows(view) if row[1] == "XX"]
    # The assigned aff replaces the card's single payer for that round; the advantage stays.
    assert xx == [
        (ASH, "XX", "aff", "costs-advantage", 2, IC),
        (ASH, "XX", "aff", "public-option-aff", 1, FI),
        (ASH, "XX", "aff", "single-payer-aff", 1, IC),
    ]


def test_a_round_by_no_readable_team_is_left_out_and_counted() -> None:
    inputs = read_synthetic_caselist(FIXTURE)
    unfiled = tuple(
        one.evolve(school="UNKNOWN", team_code="UNKNOWN") if one.source_sha256 == "a4" * 32 else one
        for one in inputs.disclosures
    )
    view = _view(dataclasses.replace(inputs, disclosures=unfiled))
    assert not any(row.team_code == "KK" and row.side.value == "aff" for row in view.rows)
    assert (view.rounds_with_no_team, view.rounds_on_no_side) == (1, 1)


def test_a_team_is_one_team_whatever_its_case_and_shows_its_commonest_spelling() -> None:
    inputs = read_synthetic_caselist(FIXTURE)
    # XX discloses three times through 2026-09-15; one of them spells it in lower case.
    lowered = list(inputs.disclosures)
    index = next(
        i for i, one in enumerate(lowered) if one.team_code == "XX" and one.snapshot == date(2026, 9, 8)
    )
    lowered[index] = lowered[index].evolve(school="ashgrove fictional", team_code="xx")
    view = _view(dataclasses.replace(inputs, disclosures=tuple(lowered)))
    assert _rows(view) == EXPECTED


def test_the_last_tournament_is_the_latest_rounds_and_ties_go_to_the_commonest_then_text_order() -> None:
    inputs = read_synthetic_caselist(FIXTURE)
    extra = next(one for one in inputs.disclosures if one.source_sha256 == "b6" * 32)
    # WW reads T in a second round first seen on 2026-09-15, at a tournament before IC in text order.
    second = extra.evolve(
        tournament="Hypothetical Open",
        round_label=RoundLabel.from_raw("R5"),
        source_path=extra.source_path.replace("R3", "R5"),
    )
    view = _view(dataclasses.replace(inputs, disclosures=(*inputs.disclosures, second)))
    nhi = next(row for row in view.rows if row.team_code == "WW" and row.position_id == "nhi-t")
    assert (nhi.rounds, nhi.last_tournament) == (3, "Hypothetical Open")


def test_shuffled_inputs_give_the_same_view() -> None:
    inputs = read_synthetic_caselist(FIXTURE)
    shuffler = random.Random(20261024)
    for _ in range(3):
        shuffled = dataclasses.replace(
            inputs,
            classifications=tuple(shuffler.sample(list(inputs.classifications), len(inputs.classifications))),
            disclosures=tuple(shuffler.sample(list(inputs.disclosures), len(inputs.disclosures))),
        )
        assert _view(shuffled) == _view(inputs)


def test_no_tag_cite_heading_or_path_reaches_the_view() -> None:
    """Debater names can only arrive through a team's own text or filename; the view carries neither."""
    inputs = read_synthetic_caselist(FIXTURE)
    names = ("Jordan Ellis", "Priya Natarajan")
    cards = tuple(
        card.model_copy(
            update={"tag": f"{names[0]} 1AC: {card.tag}", "short_cite": names[1], "headings": names}
        )
        for card in inputs.cards
    )

    def with_a_name(one: Disclosure) -> Disclosure:
        return one.evolve(source_path=one.source_path.replace(".docx", f"-{names[0].replace(' ', '')}.docx"))

    planted = dataclasses.replace(
        inputs, cards=cards, disclosures=tuple(map(with_a_name, inputs.disclosures))
    )
    view = _view(planted)
    dumped = view.model_dump_json()
    assert _rows(view) == EXPECTED
    for name in (*names, names[0].replace(" ", "")):
        assert name not in dumped
    assert ".docx" not in dumped


def test_a_spelling_disclosed_after_the_snapshot_does_not_change_the_view() -> None:
    inputs = read_synthetic_caselist(FIXTURE)
    carried = next(one for one in inputs.disclosures if one.team_code == "XX" and one.tournament == IC)
    # XX's Imaginary Classic round listed four more times on 2026-09-22, spelled in lower case.
    later = tuple(
        carried.evolve(
            snapshot=date(2026, 9, 22),
            school="ashgrove fictional",
            team_code="xx",
            tournament=f"{IC}".lower(),
        )
        for _ in range(4)
    )
    assert _rows(_view(dataclasses.replace(inputs, disclosures=(*inputs.disclosures, *later)))) == EXPECTED

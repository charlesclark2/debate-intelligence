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

from debate_core.application.landscape_counts import (
    LANDSCAPE_SIDE,
    CountedReads,
    CountedRound,
    round_id,
    team_identity,
)
from debate_core.application.landscape_report import LandscapeReportInputs, LandscapeReportService
from debate_core.application.landscape_schools import school_view
from debate_core.domain.caselist import Disclosure, RoundLabel, Side
from debate_core.domain.landscape_report import AffAssignment
from debate_core.domain.landscape_schools import SchoolView
from debate_core.testing.landscape_report import read_synthetic_caselist, synthetic_staleness

REPO = Path(__file__).resolve().parents[4]
FIXTURE = REPO / "tests" / "fixtures" / "landscape" / "synthetic_caselist"
ASH, BIRCH, CEDAR, DRIFT = (
    "Ashgrove Fictional",
    "Birchmoor",
    "Cedarvale Fictional",
    "Driftwood Fictional",
)
FI, IC = "Fictional Invitational", "Imaginary Classic"

EXPECTED = [
    (ASH, "XX", "aff", "costs-advantage", 2),
    (ASH, "XX", "aff", "single-payer-aff", 2),
    (ASH, "YY", "neg", "cap-k", 1),
    (ASH, "YY", "neg", "election-da", 1),
    (ASH, "YY", "neg", "hospital-closures-da", 1),
    (ASH, "YY", "neg", "spending-da", 1),
    (ASH, "YY", "neg", "states-cp", 1),
    (BIRCH, "QQ", "aff", "condo-bad", 1),
    (BIRCH, "QQ", "aff", "costs-advantage", 1),
    (BIRCH, "QQ", "neg", "cap-k", 1),
    (BIRCH, "QQ", "neg", "spending-da", 1),
    (BIRCH, "ZZ", "aff", "costs-advantage", 1),
    (BIRCH, "ZZ", "aff", "innovation-advantage", 1),
    (BIRCH, "ZZ", "neg", "spending-da", 1),
    (BIRCH, "ZZ", "neg", "states-cp", 1),
    (CEDAR, "VV", "aff", "costs-advantage", 1),
    (CEDAR, "VV", "aff", "public-option-aff", 1),
    (CEDAR, "WW", "neg", "nhi-t", 2),
    (CEDAR, "WW", "neg", "election-da", 1),
    (CEDAR, "WW", "neg", "provider-strikes-da", 1),
    (DRIFT, "JJ", "aff", "innovation-advantage", 1),
    (DRIFT, "JJ", "aff", "single-payer-aff", 1),
    (DRIFT, "JJ", "neg", "spending-da", 1),
    (DRIFT, "JJ", "neg", "states-cp", 1),
    (DRIFT, "KK", "aff", "costs-advantage", 1),
    (DRIFT, "KK", "aff", "innovation-advantage", 1),
]
"""Through 2026-09-15: school, team code, side, position and rounds, in view order."""


def _view(inputs: LandscapeReportInputs | None = None) -> SchoolView:
    inputs = inputs or read_synthetic_caselist(FIXTURE)
    report, counted = LandscapeReportService().count(inputs, synthetic_staleness())
    return school_view(
        caselist=inputs.caselist,
        snapshot=report.header.snapshot,
        disclosures=inputs.disclosures,
        counted=counted,
    )


def _rows(view: SchoolView) -> list[tuple[str, str, str, str, int]]:
    return [(row.school, row.team_code, row.side.value, row.position_id, row.rounds) for row in view.rows]


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
    rows = {(code, side, position) for _, code, side, position, _ in _rows(_view())}
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
        (ASH, "XX", "aff", "costs-advantage", 2),
        (ASH, "XX", "aff", "public-option-aff", 1),
        (ASH, "XX", "aff", "single-payer-aff", 1),
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
        )
        for _ in range(4)
    )
    assert _rows(_view(dataclasses.replace(inputs, disclosures=(*inputs.disclosures, *later)))) == EXPECTED


def test_a_spelling_tie_shows_the_first_spelling_in_text_order() -> None:
    inputs = read_synthetic_caselist(FIXTURE)
    carried = next(one for one in inputs.disclosures if one.team_code == "XX" and one.tournament == IC)
    # XX's three disclosures through 2026-09-15 are spelled one way; three more of its round, another.
    shouted = tuple(carried.evolve(school="ASHGROVE FICTIONAL") for _ in range(3))
    view = _view(dataclasses.replace(inputs, disclosures=(*inputs.disclosures, *shouted)))
    expected = [("ASHGROVE FICTIONAL", *row[1:]) if row[1] == "XX" else row for row in EXPECTED]
    assert _rows(view) == expected


# ------------------------------------------------------------------------------------------------
# v1-e32-t54: the rounds under each position
# ------------------------------------------------------------------------------------------------

S08, S15 = date(2026, 9, 8), date(2026, 9, 15)
EXPECTED_ROUNDS = [
    # Ashgrove's XX read a1 at both tournaments: one file for its two rounds. a1 answers the Spending DA.
    (ASH, "XX", "costs-advantage", "reads", "aff", IC, "R1", S15, 2, False),
    (ASH, "XX", "costs-advantage", "reads", "aff", FI, "R1", S08, 2, False),
    (ASH, "XX", "single-payer-aff", "reads", "aff", IC, "R1", S15, 2, False),
    (ASH, "XX", "single-payer-aff", "reads", "aff", FI, "R1", S08, 2, False),
    (ASH, "XX", "spending-da", "AT", "aff", IC, "R1", S15, 2, True),
    (ASH, "XX", "spending-da", "AT", "aff", FI, "R1", S08, 2, True),
    # b1 is YY's and JJ's: one round each, so no mark. b1 answers the Costs advantage.
    (ASH, "YY", "cap-k", "reads", "neg", IC, "R1", S15, 1, False),
    (ASH, "YY", "election-da", "reads", "neg", IC, "R1", S15, 1, False),
    (ASH, "YY", "hospital-closures-da", "reads", "neg", IC, "R1", S15, 1, False),
    (ASH, "YY", "spending-da", "reads", "neg", FI, "R1", S08, 1, False),
    (ASH, "YY", "states-cp", "reads", "neg", FI, "R1", S08, 1, False),
    (ASH, "YY", "costs-advantage", "AT", "neg", FI, "R1", S08, 1, True),
    (BIRCH, "QQ", "condo-bad", "reads", "aff", IC, "R2", S15, 1, False),
    (BIRCH, "QQ", "costs-advantage", "reads", "aff", IC, "R2", S15, 1, False),
    (BIRCH, "QQ", "cap-k", "reads", "neg", FI, "R2", S08, 1, False),
    (BIRCH, "QQ", "spending-da", "reads", "neg", FI, "R2", S08, 1, False),
    (BIRCH, "ZZ", "costs-advantage", "reads", "aff", FI, "R2", S08, 1, False),
    (BIRCH, "ZZ", "innovation-advantage", "reads", "aff", FI, "R2", S08, 1, False),
    (BIRCH, "ZZ", "spending-da", "reads", "neg", IC, "R2", S15, 1, False),
    (BIRCH, "ZZ", "states-cp", "reads", "neg", IC, "R2", S15, 1, False),
    # a3 reads and answers the Costs advantage in one round: one line, a read. b7 is on no side.
    (CEDAR, "VV", "costs-advantage", "reads", "aff", FI, "R3", S08, 1, False),
    (CEDAR, "VV", "public-option-aff", "reads", "aff", FI, "R3", S08, 1, False),
    (CEDAR, "WW", "nhi-t", "reads", "neg", IC, "R3", S15, 1, False),
    (CEDAR, "WW", "nhi-t", "reads", "neg", FI, "R3", S08, 1, False),
    (CEDAR, "WW", "election-da", "reads", "neg", FI, "R3", S08, 1, False),
    (CEDAR, "WW", "provider-strikes-da", "reads", "neg", IC, "R3", S15, 1, False),
    # a6's DA blocks in an aff round answer them: the Spending DA beside JJ's neg read of it, the
    # Midterms DA as a position JJ only answers, after the Costs advantage, which b1 answers.
    (DRIFT, "JJ", "innovation-advantage", "reads", "aff", IC, "R3", S15, 1, False),
    (DRIFT, "JJ", "single-payer-aff", "reads", "aff", IC, "R3", S15, 1, False),
    (DRIFT, "JJ", "spending-da", "AT", "aff", IC, "R3", S15, 1, False),
    (DRIFT, "JJ", "spending-da", "reads", "neg", FI, "R4", S08, 1, False),
    (DRIFT, "JJ", "states-cp", "reads", "neg", FI, "R4", S08, 1, False),
    (DRIFT, "JJ", "costs-advantage", "AT", "neg", FI, "R4", S08, 1, True),
    (DRIFT, "JJ", "election-da", "AT", "aff", IC, "R3", S15, 1, True),
    # a4's listing on 2026-09-22 is after the report's date, so it is one round of KK's, no mark.
    (DRIFT, "KK", "costs-advantage", "reads", "aff", IC, "R1", S15, 1, False),
    (DRIFT, "KK", "innovation-advantage", "reads", "aff", IC, "R1", S15, 1, False),
    (DRIFT, "KK", "pics-bad", "AT", "neg", IC, "R4", S15, 1, True),
]
"""Through 2026-09-15, worked out by hand from the fixture's table: school, team code, position, stance,
side, tournament and round as disclosed, first seen, rounds in the file, answers only."""


def _round_lines(view: SchoolView) -> list[tuple[object, ...]]:
    return [
        (
            one.school,
            one.team_code,
            one.position_id,
            one.stance.value,
            one.side.value,
            one.tournament,
            one.round_label,
            one.snapshot,
            one.rounds_in_file,
            one.answers_only,
        )
        for one in view.round_lines
    ]


def test_the_school_view_lists_each_teams_rounds_under_its_positions_as_worked_out_by_hand() -> None:
    view = _view()
    assert _round_lines(view) == EXPECTED_ROUNDS
    assert _rows(view) == EXPECTED, "schools.csv's rows are unchanged"


def test_school_round_lines_hold_exactly_the_reads_the_rows_count() -> None:
    view = _view()
    reads = Counter((one.team_code, one.side.value, one.position_id) for one in view.round_lines if one.stance.value == "reads")
    assert reads == Counter({(code, side, position): rounds for _, code, side, position, rounds in EXPECTED})


def test_shuffled_inputs_give_the_same_school_round_lines() -> None:
    inputs = read_synthetic_caselist(FIXTURE)
    shuffler = random.Random(20261106)
    shuffled = dataclasses.replace(
        inputs,
        classifications=tuple(shuffler.sample(list(inputs.classifications), len(inputs.classifications))),
        disclosures=tuple(shuffler.sample(list(inputs.disclosures), len(inputs.disclosures))),
    )
    assert _round_lines(_view(shuffled)) == EXPECTED_ROUNDS


def test_a_school_round_assigned_its_aff_holds_it_by_every_file_of_the_round() -> None:
    """XX's first round is assigned the Public option aff: no card places it, a1 holds it for two rounds."""
    inputs = read_synthetic_caselist(FIXTURE)
    first_round = next(
        one for one in inputs.disclosures if one.source_sha256 == "a1" * 32 and one.tournament == FI
    )
    assigned = AffAssignment(
        round_id=round_id(first_round), position_id="public-option-aff", method="PLAN_TEXT"
    )
    view = _view(dataclasses.replace(inputs, aff_assignments=(assigned,)))
    xx = [line for line in _round_lines(view) if line[1] == "XX" and line[3] == "reads"]
    assert xx == [
        (ASH, "XX", "costs-advantage", "reads", "aff", IC, "R1", S15, 2, False),
        (ASH, "XX", "costs-advantage", "reads", "aff", FI, "R1", S08, 2, False),
        (ASH, "XX", "public-option-aff", "reads", "aff", FI, "R1", S08, 2, False),
        (ASH, "XX", "single-payer-aff", "reads", "aff", IC, "R1", S15, 2, False),
    ]


# Hand-built rounds, for the order and the mark. Every name is invented.

MAPLE, QX, QZ = "Maple Grove", "QX", "QZ"
QUILL, BIRCHWATER, ALDER = "Quillfeather Invitational", "Birchwater Classic", "alder open"
WEEK, NEWER = date(2026, 10, 27), date(2026, 11, 3)
POSITION = "spending-da"


def _disclosure(
    sha: str,
    tournament: str | None,
    label: str | None,
    *,
    team: str = QX,
    snapshot: date = WEEK,
    side: Side = Side.NEG,
) -> Disclosure:
    base = read_synthetic_caselist(FIXTURE).disclosures[0]
    return base.evolve(
        source_sha256=sha * 32,
        snapshot=snapshot,
        school=MAPLE,
        team_code=team,
        side=side,
        tournament=tournament,
        round_label=None if label is None else RoundLabel.from_raw(label),
        source_path=f"{MAPLE}/{team}/{sha}-{label}.docx",
    )


def _hand_view(
    disclosures: list[Disclosure],
    *,
    reads: dict[str, list[Disclosure]],
    answers: dict[str, list[Disclosure]] | None = None,
    holding: dict[tuple[str, int], set[str]] | None = None,
) -> SchoolView:
    """The view of `disclosures`, with the reads and answers given, each holding its own file unless
    `holding` (position and index in `disclosures`) says which files hold it."""
    rounds: dict[str, CountedRound] = {}
    for one in disclosures:
        known = rounds.get(round_id(one))
        first = one.snapshot if known is None else min(known.first_seen, one.snapshot)
        rounds[round_id(one)] = CountedRound(
            side=LANDSCAPE_SIDE.get(one.side, ""), team=team_identity(one), first_seen=first
        )
    held: dict[tuple[str, str], frozenset[str]] = {}
    for position_id, found in (*reads.items(), *(answers or {}).items()):
        for one in found:
            held[(position_id, round_id(one))] = held.get((position_id, round_id(one)), frozenset()) | {
                one.source_sha256
            }
    for (position_id, index), shas in (holding or {}).items():
        held[(position_id, round_id(disclosures[index]))] = frozenset(sha * 32 for sha in shas)
    counted = CountedReads(
        rounds=rounds,
        reads={key: frozenset(map(round_id, found)) for key, found in reads.items()},
        answers={key: frozenset(map(round_id, found)) for key, found in (answers or {}).items()},
        holding=held,
    )
    return school_view(caselist=disclosures[0].caselist, snapshot=NEWER, disclosures=disclosures, counted=counted)


def _shown(view: SchoolView) -> list[tuple[object, ...]]:
    return [
        (one.team_code, one.position_id, one.stance.value, one.tournament, one.round_label, one.rounds_in_file)
        for one in view.round_lines
    ]


def test_school_round_lines_are_newest_snapshot_first_then_tournament_then_latest_round_first() -> None:
    """The PM's order (2026-11-06): elims before prelims, a higher prelim first, unrecognised last."""
    disclosures = [
        _disclosure("c1", QUILL, "R3"),
        _disclosure("c2", BIRCHWATER, "Round 2"),
        _disclosure("c3", BIRCHWATER, "Rd Robin"),
        _disclosure("c4", BIRCHWATER, "Quarters"),
        _disclosure("c5", BIRCHWATER, "Bracket B"),
        _disclosure("c6", BIRCHWATER, "Round 6"),
        _disclosure("c7", ALDER, "Round 1"),
        _disclosure("c8", BIRCHWATER, "Doubles"),
        _disclosure("c9", BIRCHWATER, "Finals"),
        _disclosure("ca", BIRCHWATER, "R2", snapshot=NEWER),
    ]
    expected = [
        (BIRCHWATER, "R2"),
        (ALDER, "Round 1"),
        (BIRCHWATER, "Finals"),
        (BIRCHWATER, "Quarters"),
        (BIRCHWATER, "Doubles"),
        (BIRCHWATER, "Round 6"),
        (BIRCHWATER, "Round 2"),
        (BIRCHWATER, "Bracket B"),
        (BIRCHWATER, "Rd Robin"),
        (QUILL, "R3"),
    ]
    view = _hand_view(disclosures, reads={POSITION: disclosures})
    assert [(one[3], one[4]) for one in _shown(view)] == expected
    shuffler = random.Random(20261106)
    for _ in range(3):
        shuffled = shuffler.sample(disclosures, len(disclosures))
        again = _hand_view(shuffled, reads={POSITION: shuffled})
        assert [(one[3], one[4]) for one in _shown(again)] == expected


def test_a_school_round_with_no_tournament_or_no_round_goes_after_those_with_one() -> None:
    disclosures = [
        _disclosure("d1", None, None),
        _disclosure("d2", QUILL, None),
        _disclosure("d3", QUILL, "R1"),
    ]
    view = _hand_view(disclosures, reads={POSITION: disclosures})
    assert [(one[3], one[4]) for one in _shown(view)] == [(QUILL, "R1"), (QUILL, None), (None, None)]


def test_a_file_disclosed_for_several_school_rounds_marks_them_by_this_teams_rounds_alone() -> None:
    """e1 holds the DA in three of QX's rounds and one of QZ's; e2 and e3 share a round; e4 is in a round
    whose position e5 holds, and e4's two rounds do not mark it."""
    disclosures = [
        _disclosure("e1", BIRCHWATER, "Quarters"),
        _disclosure("e1", BIRCHWATER, "Round 6"),
        _disclosure("e1", QUILL, "R2"),
        _disclosure("e1", QUILL, "R4", team=QZ),
        _disclosure("e2", ALDER, "Round 2"),
        _disclosure("e3", ALDER, "Round 2"),
        _disclosure("e3", ALDER, "Round 5"),
        _disclosure("e4", ALDER, "Round 3"),
        _disclosure("e5", ALDER, "Round 3"),
        _disclosure("e4", ALDER, "Round 4"),
    ]
    reads = [disclosures[index] for index in (0, 1, 2, 3, 4, 6, 7)]
    view = _hand_view(disclosures, reads={POSITION: reads}, holding={(POSITION, 4): {"e2", "e3"}, (POSITION, 7): {"e5"}})
    assert _shown(view) == [
        (QX, POSITION, "reads", ALDER, "Round 5", 2),
        (QX, POSITION, "reads", ALDER, "Round 3", 1),
        (QX, POSITION, "reads", ALDER, "Round 2", 2),
        (QX, POSITION, "reads", BIRCHWATER, "Quarters", 3),
        (QX, POSITION, "reads", BIRCHWATER, "Round 6", 3),
        (QX, POSITION, "reads", QUILL, "R2", 3),
        (QZ, POSITION, "reads", QUILL, "R4", 1),
    ]


def test_a_teams_read_positions_come_first_in_row_order_then_those_it_only_answers() -> None:
    aff = [_disclosure(sha, QUILL, label, side=Side.AFF) for sha, label in (("f1", "R1"), ("f2", "R3"))]
    neg = [_disclosure(sha, BIRCHWATER, label) for sha, label in (("f3", "R2"), ("f4", "R4"), ("f5", "R6"))]
    view = _hand_view(
        [*aff, *neg],
        reads={"states-cp": neg[:1], "single-payer-aff": aff, "cap-k": neg},
        answers={"election-da": aff[:1], "courts-cp": aff, "cap-k": neg[:2], "nhi-t": neg[1:2]},
    )
    lines = [(one.position_id, one.stance.value, one.answers_only) for one in view.round_lines]
    assert lines == [
        ("single-payer-aff", "reads", False),
        ("single-payer-aff", "reads", False),
        ("cap-k", "reads", False),
        ("cap-k", "reads", False),
        ("cap-k", "reads", False),
        ("states-cp", "reads", False),
        ("courts-cp", "AT", True),
        ("courts-cp", "AT", True),
        ("election-da", "AT", True),
        ("nhi-t", "AT", True),
    ]


def test_a_school_round_by_no_team_or_on_no_side_is_no_line() -> None:
    disclosures = [
        _disclosure("71", QUILL, "R1", team="UNKNOWN"),
        _disclosure("72", QUILL, "R2", side=Side.UNKNOWN),
        _disclosure("73", QUILL, "R3"),
    ]
    view = _hand_view(disclosures, reads={POSITION: disclosures}, answers={"cap-k": disclosures})
    assert [(one[1], one[4]) for one in _shown(view)] == [(POSITION, "R3"), ("cap-k", "R3")]


def test_a_school_round_spelled_two_ways_shows_its_commonest_spelling() -> None:
    disclosures = [
        _disclosure("81", QUILL, "Round 4"),
        _disclosure("81", "QUILLFEATHER INVITATIONAL", "R4", snapshot=NEWER),
        _disclosure("81", QUILL, "Round 4", snapshot=NEWER),
    ]
    view = _hand_view(disclosures, reads={POSITION: disclosures[:1]})
    assert _shown(view) == [(QX, POSITION, "reads", QUILL, "Round 4", 1)]
    assert view.round_lines[0].snapshot == WEEK

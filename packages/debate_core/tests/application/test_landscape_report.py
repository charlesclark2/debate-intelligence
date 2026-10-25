"""LandscapeReportService over the synthetic caselists (`v1-e32-t03` ac1 to ac3, `v1-e32-t10`, `v1-e32-t15`).

Every expected number here was counted by hand from the fixture's table
(`tests/fixtures/landscape/synthetic_caselist/README.md`, `scripts/make_landscape_fixture.py`),
never read off the service. Tests named `aggregate` are the aggregation node's; `top_cards` the
top-card node's; `impact` `v1-e32-t10`'s impact cards; `advantages` `v1-e32-t15`'s advantages by aff;
`chain`, `lead_in`, `scenario` and `coverage` `v1-e32-t14`'s link chains, what each impact runs
through, and what no heading or label gives.
"""

from __future__ import annotations

import ast
import csv
import dataclasses
import re
from datetime import date
from pathlib import Path

import pytest
import yaml

from debate_core.application.landscape_report import (
    LandscapeReportInputs,
    LandscapeReportService,
    ReportCannotShip,
    landscape_cards,
    overrides_digest,
    round_id,
)
from debate_core.application.landscape_staleness import assess_staleness
from debate_core.application.ports.parsed_store import OccurrenceRecord
from debate_core.arguments.landscape.kritikal_aff import KritikalAffInputs
from debate_core.arguments.landscape.seeding import SeedCard, SeedSource, SeedTeam
from debate_core.domain.card_occurrence import ClusterMembership
from debate_core.domain.caselist import Disclosure, Event, RoundLabel, Side
from debate_core.domain.debate_files import CardCompleteness
from debate_core.domain.landscape import PositionKind, Taxonomy
from debate_core.domain.landscape_classification import (
    ClassificationMethod,
    ItemKind,
    OverrideRules,
    PositionClassification,
    PositionRole,
)
from debate_core.domain.landscape_report import (
    AdvantagesByAff,
    AffAssignment,
    KritikalAffs,
    LandscapeReport,
    PositionStats,
    UnassignedAdvantageReads,
)
from debate_core.domain.landscape_texts import AnalyticTextKind, LandscapeTexts, MoreTexts, TextCoverage
from debate_core.testing.landscape_report import (
    SYNTHETIC_CASELIST,
    read_synthetic_caselist,
    synthetic_staleness,
)

REPO = Path(__file__).resolve().parents[4]
FIXTURE = REPO / "tests" / "fixtures" / "landscape" / "synthetic_caselist"
EXPECTED_POSITIONS = REPO / "tests" / "fixtures" / "landscape" / "golden" / "positions.csv"
FIRST, SECOND = date(2026, 9, 8), date(2026, 9, 15)
FIRST_TOURNAMENT, SECOND_TOURNAMENT = "Fictional Invitational", "Imaginary Classic"


def _inputs(**changes: object) -> LandscapeReportInputs:
    return dataclasses.replace(read_synthetic_caselist(FIXTURE), **changes)  # pyright: ignore[reportArgumentType]


def _report(
    inputs: LandscapeReportInputs | None = None, *, top_cards: int = 5, impact_cards: int = 3
) -> LandscapeReport:
    return LandscapeReportService(top_cards=top_cards, impact_cards=impact_cards).build(
        inputs or _inputs(), synthetic_staleness()
    )


def _position(report: LandscapeReport, position_id: str) -> PositionStats:
    return next(stats for stats in report.positions if stats.position_id == position_id)


def _round(code: str, tournament: str | None, side: Side = Side.AFF) -> str:
    """The round id of the fixture's disclosure by `code` at `tournament` on `side`."""
    found = {
        round_id(one)
        for one in read_synthetic_caselist(FIXTURE).disclosures
        if one.team_code == code and one.tournament == tournament and one.side is side
    }
    assert len(found) == 1
    return found.pop()


# ------------------------------------------------------------------------------------------------
# Aggregation
# ------------------------------------------------------------------------------------------------


def test_aggregate_positions_match_the_hand_computed_file() -> None:
    lines = [
        line
        for line in EXPECTED_POSITIONS.read_text(encoding="utf-8").splitlines()
        if not line.startswith("#")
    ]
    expected = list(csv.DictReader(lines))
    report = _report()
    assert [
        {
            "position_id": stats.position_id,
            "label": stats.label,
            "kind": stats.kind.value,
            "rounds": str(stats.rounds),
            "teams": str(stats.teams),
            "aff_rounds": str(stats.aff_rounds),
            "neg_rounds": str(stats.neg_rounds),
            "first_seen_snapshot": stats.first_seen_snapshot.isoformat(),
            "is_new": "true" if stats.is_new else "false",
            "share_of_teams": f"{stats.share_of_teams[0]}/{stats.share_of_teams[1]}",
        }
        for stats in report.positions
    ] == [{**row, "share_of_teams": _share_fraction(row["share_of_teams"])} for row in expected]


def _share_fraction(rounded: str) -> str:
    """The expected file's three-place share, as the hand count's fraction (every side has 6 teams)."""
    return {"0.167": "1/6", "0.333": "2/6", "0.500": "3/6", "0.667": "4/6", "0.833": "5/6"}[rounded]


def test_aggregate_answers_never_count_as_reads() -> None:
    report = _report()
    # a1 answers spending-da in two aff rounds; b1 answers costs-advantage in two neg rounds.
    assert (_position(report, "spending-da").aff_rounds, _position(report, "spending-da").rounds) == (0, 4)
    assert (_position(report, "costs-advantage").neg_rounds, _position(report, "costs-advantage").rounds) == (
        0,
        6,
    )
    # pics-bad is only ever answered (b8), so it is not a position read.
    assert "pics-bad" not in {stats.position_id for stats in report.positions}
    # b7's answer to nhi-t is in a round on no readable side, where only the role keeps it out.
    nhi_t = _position(report, "nhi-t")
    assert (nhi_t.rounds, nhi_t.teams) == (2, 1)


def test_aggregate_a_placement_in_a_round_on_the_other_side_answers_the_position() -> None:
    report = _report()
    # a6, JJ's affirmative file, has a `Spending DA` block with no AT: marker: the 2AC answering it.
    spending = _position(report, "spending-da")
    assert (spending.rounds, spending.aff_rounds, spending.neg_rounds, spending.teams) == (4, 0, 4, 4)
    # a6's Midterms card under `internal link` (v1-e32-t14's) is a second such placement, by the same round.
    assert report.unclassified.other_side_position_rounds == 2
    assert "31" not in {fingerprint for fingerprint, _ in _top(report, "spending-da")}
    # A round on no readable side is not the other side: b7 still reads cap-k.
    assert _position(report, "cap-k").rounds == 3


def test_aggregate_below_threshold_and_queued_items_are_unclassified_not_counted() -> None:
    report = _report()
    assert "courts-cp" not in {stats.position_id for stats in report.positions}
    assert (_position(report, "public-option-aff").rounds, _position(report, "public-option-aff").teams) == (
        1,
        1,
    )
    summary = report.unclassified
    assert (summary.cards, summary.unplaced_cards, summary.below_threshold_cards) == (56, 8, 2)
    assert (summary.unclassified_cards, summary.decided_no_position_cards) == (10, 1)
    # b7's answer to the midterms DA (v1-e32-t10's fixture card) is placed, and counts nowhere.
    # v1-e32-t14's eleven cards (a3 three, a5, a6, b2, b3, b4, b5 three) are all placed by alias.
    assert (report.header.cards, report.header.cards_placed) == (56, 45)


@pytest.mark.parametrize(("threshold", "unplaced", "below", "placed"), [(0.95, 8, 10, 37), (0.4, 8, 0, 47)])
def test_aggregate_the_report_threshold_decides_what_is_unclassified(
    threshold: float, unplaced: int, below: int, placed: int
) -> None:
    # At 0.95 the eight INHERITED cards in range (0.9: a1 two, a3, a6, b1 two, b5, b6) fall below it
    # too; at 0.4 the two TAG_KEYWORD cards (0.5) are counted. v1-e32-t14's eleven are ALIAS (1.0).
    report = LandscapeReportService(review_threshold=threshold).build(_inputs(), synthetic_staleness())
    assert (report.unclassified.unplaced_cards, report.unclassified.below_threshold_cards) == (
        unplaced,
        below,
    )
    assert report.header.cards_placed == placed


def test_aggregate_unclassified_rounds_are_counted_by_side() -> None:
    summary = _report().unclassified
    # Aff: a2 (ZZ), a4 (KK) and a5 (QQ) have no card under an aff. Neg: b8 (KK) has no neg position.
    assert (summary.aff_rounds_unidentified, summary.aff_rounds) == (3, 7)
    assert (summary.neg_rounds_unplaced, summary.neg_rounds) == (1, 8)


def test_aggregate_disclosures_after_the_snapshot_are_out_of_range() -> None:
    report = _report()
    # b9 (2026-09-22) reads cap-k and spending-da, and its cards would make 58.
    assert (_position(report, "cap-k").rounds, _position(report, "spending-da").rounds) == (3, 4)
    assert (report.header.snapshot, report.header.rounds, report.unclassified.cards) == (SECOND, 16, 56)


def test_aggregate_a_round_carried_into_the_next_window_is_one_round_first_seen_in_the_first() -> None:
    report = _report()
    single_payer = _position(report, "single-payer-aff")
    # a1 at the first tournament (listed in both windows), a1 at the second, a6.
    assert (single_payer.rounds, single_payer.teams, single_payer.first_seen_snapshot) == (3, 2, FIRST)


def test_aggregate_one_file_two_teams_disclosed_counts_in_both_rounds() -> None:
    states = _position(_report(), "states-cp")
    # b1 (YY and JJ) and b5 (ZZ).
    assert (states.rounds, states.teams) == (3, 3)


def test_aggregate_a_disclosure_by_no_readable_team_reads_its_round_but_is_no_team() -> None:
    inputs = read_synthetic_caselist(FIXTURE)
    # a4, KK's affirmative round, filed where the path parser could read no school or team code.
    unfiled = tuple(
        one.evolve(school="UNKNOWN", team_code="UNKNOWN") if one.source_sha256 == "a4" * 32 else one
        for one in inputs.disclosures
    )
    report = _report(dataclasses.replace(inputs, disclosures=unfiled))
    innovation = _position(report, "innovation-advantage")
    assert (innovation.rounds, innovation.teams, innovation.share_of_teams) == (3, 2, (2, 5))
    # KK still disclosed b8 on the negative.
    assert (report.header.aff_rounds, report.header.aff_teams, report.header.teams) == (7, 5, 8)
    assert (
        next(card for card in report.top_cards if card.position_id == "innovation-advantage").teams_reading
        == 2
    )


def test_aggregate_rounds_and_teams_by_side_are_the_denominators() -> None:
    header = _report().header
    assert (header.rounds, header.aff_rounds, header.neg_rounds) == (16, 7, 8)
    assert (header.teams, header.aff_teams, header.neg_teams) == (8, 6, 6)
    assert header.rounds_with_a_read == 15


def test_aggregate_share_of_teams_is_over_the_teams_disclosing_on_the_positions_side() -> None:
    cap = _position(_report(), "cap-k")
    # Read by QQ and YY on the negative and by VV in a round on no readable side.
    assert (cap.teams, cap.neg_rounds, cap.aff_rounds, cap.rounds) == (3, 2, 0, 3)
    assert cap.share_of_teams == (2, 6)
    assert _position(_report(), "costs-advantage").share_of_teams == (5, 6)


def test_aggregate_new_means_first_seen_after_the_previous_snapshot() -> None:
    report = _report()
    assert report.header.previous_snapshot == FIRST
    assert [stats.position_id for stats in report.positions if stats.is_new] == [
        "condo-bad",
        "hospital-closures-da",
        "provider-strikes-da",
    ]


def test_aggregate_in_the_first_snapshot_nothing_is_new() -> None:
    report = _report(_inputs(through=FIRST))
    assert report.header.previous_snapshot is None
    assert report.header.snapshot == FIRST
    assert not any(stats.is_new for stats in report.positions)
    assert {stats.position_id for stats in report.positions} == {
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


def test_aggregate_positions_are_ordered_by_side_kind_teams_rounds_and_id() -> None:
    assert [stats.position_id for stats in _report().positions] == [
        "single-payer-aff",
        "public-option-aff",
        "costs-advantage",
        "innovation-advantage",
        "condo-bad",
        "spending-da",
        "election-da",
        "hospital-closures-da",
        "provider-strikes-da",
        "states-cp",
        "cap-k",
        "nhi-t",
    ]


def test_aggregate_positions_rank_by_teams_before_rounds() -> None:
    inputs = read_synthetic_caselist(FIXTURE)
    strikes_round = next(one for one in inputs.disclosures if one.source_sha256 == "b6" * 32)
    # WW reads b6 (provider strikes, and nhi-t) in two more rounds: 3 rounds by 1 team, against the
    # midterms DA's 2 rounds by 2 teams.
    more = tuple(
        strikes_round.evolve(round_label=RoundLabel.from_raw(played), source_path=f"{played}.docx")
        for played in ("R5", "R6")
    )
    report = _report(dataclasses.replace(inputs, disclosures=(*inputs.disclosures, *more)))
    assert (
        _position(report, "provider-strikes-da").rounds,
        _position(report, "provider-strikes-da").teams,
    ) == (3, 1)
    assert (_position(report, "election-da").rounds, _position(report, "election-da").teams) == (2, 2)
    assert [stats.position_id for stats in report.positions if stats.kind.value == "da"] == [
        "spending-da",
        "election-da",
        "provider-strikes-da",
        "hospital-closures-da",
    ]


def test_aggregate_input_order_changes_nothing() -> None:
    inputs = read_synthetic_caselist(FIXTURE)
    reversed_inputs = dataclasses.replace(
        inputs,
        classifications=tuple(reversed(inputs.classifications)),
        disclosures=tuple(reversed(inputs.disclosures)),
        cards=tuple(reversed(inputs.cards)),
    )
    assert _report(reversed_inputs) == _report(inputs)


def test_aggregate_the_header_names_versions_digest_and_coverage() -> None:
    header = _report().header
    assert (header.caselist, header.topic_id, header.taxonomy_version) == (
        SYNTHETIC_CASELIST,
        "synthetic-policy-topic",
        "1.2.0",
    )
    # sha256 of '[["extra", null]]', computed with shasum, not with the code.
    assert header.overrides_digest == "1789afec01f8e1417460965e050263e11df2d4128ca0ed9604d1643f430639a0"
    assert (header.prompt_version, header.parser_version, header.review_threshold) == (
        "none",
        "2026.10.20-docx-6",
        0.6,
    )
    assert (header.stale, header.newest_snapshot, header.snapshot_age_days) == (False, SECOND, 2)


def test_aggregate_with_no_overrides_the_header_says_none() -> None:
    no_overrides = OverrideRules(topic_id="synthetic-policy-topic")
    assert overrides_digest(no_overrides) == "none"
    assert _report(_inputs(overrides=no_overrides)).header.overrides_digest == "none"


def test_aggregate_a_report_that_cannot_say_how_old_its_data_is_does_not_ship() -> None:
    no_snapshot = assess_staleness(SYNTHETIC_CASELIST, report_date=SECOND, newest_snapshot=None)
    with pytest.raises(ReportCannotShip, match="cannot say how old"):
        LandscapeReportService().build(_inputs(), no_snapshot)
    other = assess_staleness("othercl26", report_date=SECOND, newest_snapshot=SECOND)
    with pytest.raises(ReportCannotShip, match="othercl26"):
        LandscapeReportService().build(_inputs(), other)


def test_aggregate_a_classification_under_another_taxonomy_version_is_refused() -> None:
    inputs = read_synthetic_caselist(FIXTURE)
    stale = inputs.classifications[0].evolve(taxonomy_version="1.1.0")
    with pytest.raises(ReportCannotShip, match=r"1\.1\.0"):
        _report(dataclasses.replace(inputs, classifications=(stale, *inputs.classifications[1:])))


# ------------------------------------------------------------------------------------------------
# The aff seam for v1-e32-t09
# ------------------------------------------------------------------------------------------------


def test_aggregate_without_assignments_affirmative_rounds_are_identified_by_placed_cards_only() -> None:
    report = _report()
    assert [(one.method, one.rounds) for one in report.aff_identification] == [("PLACED_CARD", 4)]
    assert report.unclassified.aff_rounds_unidentified == 3


def test_aggregate_an_aff_assignment_is_counted_with_its_method() -> None:
    assignments = (
        # a1's first-tournament round: its heading says single payer; the assignment wins.
        AffAssignment(
            round_id=_round("XX", FIRST_TOURNAMENT), position_id="public-option-aff", method="PLAN_TEXT"
        ),
        # a2 (ZZ) had no aff; a4 (KK) had none.
        AffAssignment(
            round_id=_round("ZZ", FIRST_TOURNAMENT), position_id="public-option-aff", method="PLAN_TEXT"
        ),
        AffAssignment(
            round_id=_round("KK", SECOND_TOURNAMENT), position_id="single-payer-aff", method="TEAM_ROUNDS"
        ),
    )
    report = _report(read_synthetic_caselist(FIXTURE, aff_assignments=assignments))
    single_payer = _position(report, "single-payer-aff")
    # Rounds: a1 at the second tournament (XX), a6 (JJ), a4 (KK); all first seen 2026-09-15.
    assert (single_payer.rounds, single_payer.teams, single_payer.aff_rounds) == (3, 3, 3)
    assert (single_payer.first_seen_snapshot, single_payer.is_new, single_payer.share_of_teams) == (
        SECOND,
        True,
        (3, 6),
    )
    public_option = _position(report, "public-option-aff")
    # a3 (VV) by its card, and the two assigned rounds (XX, ZZ).
    assert (public_option.rounds, public_option.teams, public_option.first_seen_snapshot) == (3, 3, FIRST)
    assert [(one.method, one.rounds) for one in report.aff_identification] == [
        ("PLACED_CARD", 3),
        ("PLAN_TEXT", 2),
        ("TEAM_ROUNDS", 1),
    ]
    assert report.unclassified.aff_rounds_unidentified == 1
    # Advantages and negative positions are counted as placed, whatever the assignment.
    assert _position(report, "costs-advantage").rounds == 6
    # The single payer card in the reassigned round no longer counts it, but XX still reads that
    # card in its other round.
    sp_card = next(card for card in report.top_cards if card.position_id == "single-payer-aff")
    assert sp_card.teams_reading == 2


def test_aggregate_an_assignment_for_a_round_out_of_range_is_ignored() -> None:
    assignment = AffAssignment(
        round_id="0123456789abcdef", position_id="single-payer-aff", method="PLAN_TEXT"
    )
    report = _report(read_synthetic_caselist(FIXTURE, aff_assignments=(assignment,)))
    assert report == _report()


@pytest.mark.parametrize(
    ("code", "tournament", "position_id", "refusal"),
    [
        ("ZZ", FIRST_TOURNAMENT, "costs-advantage", "not an aff"),
        ("ZZ", FIRST_TOURNAMENT, "medicaid-aff", "not a position"),
        ("YY", FIRST_TOURNAMENT, "single-payer-aff", "not an affirmative round"),
    ],
)
def test_aggregate_an_assignment_that_contradicts_the_inputs_is_refused(
    code: str, tournament: str, position_id: str, refusal: str
) -> None:
    side = Side.NEG if code == "YY" else Side.AFF
    assignment = AffAssignment(
        round_id=_round(code, tournament, side), position_id=position_id, method="PLAN_TEXT"
    )
    with pytest.raises(ReportCannotShip, match=refusal):
        _report(read_synthetic_caselist(FIXTURE, aff_assignments=(assignment,)))


def test_aggregate_a_round_assigned_twice_is_refused() -> None:
    one = _round("ZZ", FIRST_TOURNAMENT)
    twice = (
        AffAssignment(round_id=one, position_id="single-payer-aff", method="PLAN_TEXT"),
        AffAssignment(round_id=one, position_id="public-option-aff", method="TEAM_ROUNDS"),
    )
    with pytest.raises(ReportCannotShip, match="twice"):
        _report(read_synthetic_caselist(FIXTURE, aff_assignments=twice))


def test_round_id_names_a_round_by_digest_alone() -> None:
    disclosures = read_synthetic_caselist(FIXTURE).disclosures
    ids = {round_id(one) for one in disclosures if one.snapshot <= SECOND}
    assert len(ids) == 16
    carried = [
        round_id(one) for one in disclosures if one.team_code == "XX" and one.tournament == FIRST_TOURNAMENT
    ]
    assert len(carried) == 2 and carried[0] == carried[1]
    assert all(len(one) == 16 and set(one) <= set("0123456789abcdef") for one in ids)


def test_round_id_files_with_no_tournament_or_round_are_rounds_of_their_own() -> None:
    unlabelled = next(one for one in read_synthetic_caselist(FIXTURE).disclosures if one.tournament is None)
    other_file = unlabelled.evolve(source_sha256="c1" * 32)
    assert round_id(other_file) != round_id(unlabelled)
    labelled = next(one for one in read_synthetic_caselist(FIXTURE).disclosures if one.tournament is not None)
    assert round_id(labelled.evolve(source_sha256="c1" * 32)) == round_id(labelled)


def test_round_id_ignores_case_and_reads_the_normalized_round() -> None:
    labelled: Disclosure = next(one for one in read_synthetic_caselist(FIXTURE).disclosures if one.tournament)
    respelled = labelled.evolve(
        school=labelled.school.upper(),
        team_code=labelled.team_code.lower(),
        tournament=(labelled.tournament or "").upper(),
        round_label=labelled.round_label.model_copy(update={"raw": "Round 1"})
        if labelled.round_label
        else None,
    )
    assert round_id(respelled) == round_id(labelled)


# ------------------------------------------------------------------------------------------------
# Top cards
# ------------------------------------------------------------------------------------------------


def _top(report: LandscapeReport, position_id: str) -> list[tuple[str, int]]:
    return [
        (card.fingerprint[:2], card.teams_reading)
        for card in report.top_cards
        if card.position_id == position_id
    ]


def test_top_cards_rank_clusters_by_distinct_teams_and_count_near_duplicates_once() -> None:
    report = _report()
    # Cluster 2: XX (two copies, once), ZZ, VV and QQ. Cluster 3: KK; 35 and 37: VV; 38: QQ.
    # Cluster 36 (a3's) only answers the advantage.
    assert _top(report, "costs-advantage") == [("02", 4), ("03", 1), ("35", 1), ("37", 1), ("38", 1)]
    # Cluster 14: YY and JJ (one file), QQ, ZZ. Cluster 15: YY and JJ. 39: QQ; 40, 41 (and 42, cut): ZZ.
    assert _top(report, "spending-da") == [("14", 4), ("15", 2), ("39", 1), ("40", 1), ("41", 1)]


def test_top_cards_ties_are_broken_by_fingerprint() -> None:
    assert _top(_report(), "nhi-t") == [("21", 1), ("29", 1)]


def test_top_cards_are_capped_at_n_per_position() -> None:
    report = _report(top_cards=1)
    assert _top(report, "costs-advantage") == [("02", 4)]
    assert len(report.top_cards) == len(report.positions)


def test_top_cards_answers_and_out_of_range_cards_are_not_counted() -> None:
    report = _report()
    # b1's answer to costs-advantage is cluster 17; b9's cap-k card would add a team to cluster 18.
    assert "17" not in {fingerprint for fingerprint, _ in _top(report, "costs-advantage")}
    assert _top(report, "cap-k") == [("18", 3)]


def test_top_cards_show_the_commonest_tag_and_cite_from_the_first_such_card() -> None:
    report = _report()
    costs = next(card for card in report.top_cards if card.position_id == "costs-advantage")
    # Three of cluster 2's five cards say this with "Okafor 25"; the first of them is a1's second card.
    assert (costs.tag, costs.short_cite, costs.element_index) == (
        "Single payer cuts administrative costs",
        "Okafor 25",
        3,
    )
    assert costs.source_object_key == "raw/caselist/synthpolicy26/sha256/a1/a1/" + "a1" * 32
    assert costs.source_snapshot == FIRST
    # Cluster 20's two cards tie one to one: the first tag in text order.
    election = next(card for card in report.top_cards if card.position_id == "election-da")
    assert (election.tag, election.source_object_key[-4:]) == (
        "Health reform costs the incumbents the midterms",
        "b3b3",
    )


def test_top_cards_the_first_card_by_digest_shows_only_when_its_tag_and_cite_are_the_commonest() -> None:
    inputs = read_synthetic_caselist(FIXTURE)
    retagged = tuple(
        card.evolve(tag="An uncommon tag")
        if (card.source_sha256, card.element_index) == ("a1" * 32, 3)
        else card
        for card in inputs.cards
    )
    report = _report(dataclasses.replace(inputs, cards=retagged))
    costs = next(card for card in report.top_cards if card.position_id == "costs-advantage")
    # a2's first card and a5's first card still say the commonest pair; a2 sorts first.
    assert (costs.tag, costs.short_cite, costs.source_object_key[-4:], costs.element_index) == (
        "Single payer cuts administrative costs",
        "Okafor 25",
        "a2a2",
        0,
    )


def test_top_cards_every_row_is_file_import() -> None:
    assert {card.provenance_mode.value for card in _report().top_cards} == {"FILE_IMPORT"}


# ------------------------------------------------------------------------------------------------
# Impact cards (v1-e32-t10)
# ------------------------------------------------------------------------------------------------


def _impacts(report: LandscapeReport, position_id: str) -> list[tuple[str, int]]:
    return [
        (card.fingerprint[:2], card.teams_reading)
        for card in report.impact_cards
        if card.position_id == position_id
    ]


def _with_card(
    inputs: LandscapeReportInputs, source: str, element: int, **changes: object
) -> LandscapeReportInputs:
    """`inputs` with the classification of `source`'s card at `element` changed."""
    return dataclasses.replace(
        inputs,
        classifications=tuple(
            one.evolve(**changes)
            if (one.source_sha256, one.first_element_index) == (source * 32, element)
            else one
            for one in inputs.classifications
        ),
    )


def test_impact_cards_count_only_the_labelled_copies_of_a_cluster() -> None:
    report = _report()
    # Cluster 2 is read by XX, ZZ, VV and QQ, but only a1's copy d (XX) is labelled, by its tag.
    # Cluster 3: a4 (KK), under an impact heading. Cluster 37: a3 (VV), heading and tag.
    assert _impacts(report, "costs-advantage") == [("02", 1), ("03", 1), ("37", 1)]
    # Cluster 14 is read by four teams; only b2's copy (QQ) is labelled. Cluster 15 (turns case): YY, JJ.
    # Cluster 42: b5 (ZZ), under `recession impact`.
    assert _impacts(report, "spending-da") == [("15", 2), ("14", 1), ("42", 1)]
    assert _impacts(report, "hospital-closures-da") == [("23", 1)]


def test_impact_cards_rank_by_teams_then_by_cluster_id() -> None:
    report = _report()
    # Spending: 15 before 14, against their ids. Costs: 2 and 3 tie at one team, so the id orders them.
    assert [
        (card.rank, card.fingerprint[:2]) for card in report.impact_cards if card.position_id == "spending-da"
    ] == [(1, "15"), (2, "14"), (3, "42")]
    assert [
        card.fingerprint[:2] for card in report.impact_cards if card.position_id == "costs-advantage"
    ] == [
        "02",
        "03",
        "37",
    ]


def test_impact_cards_are_capped_at_n_per_position() -> None:
    report = _report(impact_cards=1)
    assert [(card.position_id, card.fingerprint[:2]) for card in report.impact_cards] == [
        ("costs-advantage", "02"),
        ("spending-da", "15"),
        ("hospital-closures-da", "23"),
    ]
    assert report.header.impact_cards_per_position == 1
    assert _report().header.impact_cards_per_position == 3


def test_impact_cards_show_a_labelled_copy_not_the_clusters_commonest() -> None:
    costs = next(card for card in _report().impact_cards if card.position_id == "costs-advantage")
    assert (costs.tag, costs.short_cite, costs.element_index, costs.source_snapshot) == (
        "2. Extinction from economic collapse",
        "Okafor 25",
        6,
        FIRST,
    )
    assert costs.source_object_key == "raw/caselist/synthpolicy26/sha256/a1/a1/" + "a1" * 32
    assert {card.provenance_mode.value for card in _report().impact_cards} == {"FILE_IMPORT"}


def test_impact_an_answer_is_never_an_impact_card() -> None:
    # b7's answer to the midterms DA is under `impact` and tagged `2. Extinction outweighs`, in a round
    # on no readable side: only its role keeps it out.
    assert _impacts(_report(), "election-da") == []
    as_read = _with_card(read_synthetic_caselist(FIXTURE), "b7", 9, role=PositionRole.READS)
    assert _impacts(_report(as_read), "election-da") == [("33", 1)]


def test_impact_a_card_in_a_round_on_the_other_side_is_never_an_impact_card() -> None:
    # a6, JJ's affirmative file, has a spending DA card under `impact`: the 2AC answering the DA.
    assert "31" not in {fingerprint for fingerprint, _ in _impacts(_report(), "spending-da")}
    inputs = read_synthetic_caselist(FIXTURE)
    sideless = tuple(
        one.evolve(side=Side.UNKNOWN) if one.source_sha256 == "a6" * 32 else one for one in inputs.disclosures
    )
    report = _report(dataclasses.replace(inputs, disclosures=sideless))
    assert _impacts(report, "spending-da") == [("15", 2), ("14", 1), ("31", 1)]


def test_impact_no_impact_defense_and_impact_turns_headings_label_nothing() -> None:
    report = _report()
    # b3 `no impact`, b4 `impact defense`, b6 `impact turns`.
    assert _impacts(report, "election-da") == []
    assert _impacts(report, "provider-strikes-da") == []
    inputs = read_synthetic_caselist(FIXTURE)
    relabelled = tuple(
        card.evolve(headings=("midterms da", "impact"))
        if (card.source_sha256, card.element_index) == ("b3" * 32, 0)
        else card
        for card in inputs.cards
    )
    assert _impacts(_report(dataclasses.replace(inputs, cards=relabelled)), "election-da") == [("20", 1)]


def test_impact_cards_are_listed_for_das_and_advantages_only() -> None:
    # b2's cap-k card is under `impact`, and a K is not listed.
    assert {card.position_id for card in _report().impact_cards} == {
        "costs-advantage",
        "spending-da",
        "hospital-closures-da",
    }


def test_impact_out_of_range_and_below_threshold_cards_are_not_impact_cards() -> None:
    # b9's spending DA card (cluster 28) is under `impact` and disclosed after the report's date.
    assert "28" not in {fingerprint for fingerprint, _ in _impacts(_report(), "spending-da")}
    below = _with_card(read_synthetic_caselist(FIXTURE), "b4", 6, confidence=0.5)
    assert _impacts(_report(below), "hospital-closures-da") == []


def test_impact_coverage_counts_documents_with_no_labelled_impact_per_kind() -> None:
    coverage = {one.kind.value: one for one in _report().impact_coverage}
    # Advantages: a1 to a6 (b1 only answers); a1, a3 and a4 carry an impact card.
    # DAs: b1, b2, b3, b4, b5, b6 (a6 is the other side, b9 out of range); b1, b2, b4 and b5 carry one.
    assert {
        kind: (one.documents, one.labelled_documents, one.unlabelled_documents)
        for kind, one in coverage.items()
    } == {
        "advantage": (6, 3, 3),
        "da": (6, 4, 2),
    }
    assert [one.kind.value for one in _report().impact_coverage] == ["advantage", "da"]


# ------------------------------------------------------------------------------------------------
# From the stores
# ------------------------------------------------------------------------------------------------


def _occurrence(sha: str, element: int, cluster: str, disclosure: str) -> OccurrenceRecord:
    return OccurrenceRecord(
        caselist=SYNTHETIC_CASELIST,
        snapshot="2026-09-08",
        last_snapshot="2026-09-15",
        source_sha256=sha,
        parser_version="2026.10.20-docx-6",
        profile_version="2026.09.20-verbatim-1",
        fingerprint_version="card-fingerprint-v4",
        disclosure=disclosure,
        first_element_index=element,
        last_element_index=element + 2,
        exact_fingerprint=cluster[:-2] + "0a",
        cluster_id=cluster,
        membership=ClusterMembership.NEAR_DUPLICATE,
        completeness=CardCompleteness.FULL,
    )


def test_landscape_cards_take_each_cards_cluster_from_the_occurrence_table() -> None:
    source = SeedSource(
        sha256="a1" * 32,
        teams=(),
        cards=(
            SeedCard(tag="One", section_path=(), first_element_index=0, short_cite="Cite 24"),
            SeedCard(tag=None, section_path=(), first_element_index=3),
            SeedCard(tag="No paragraph", section_path=(), first_element_index=None),
            SeedCard(tag="No row", section_path=(), first_element_index=9),
        ),
    )
    rows = [
        _occurrence("a1" * 32, 0, "01" * 32, "d1" * 32),
        _occurrence("a1" * 32, 0, "01" * 32, "d2" * 32),
        _occurrence("a1" * 32, 3, "02" * 32, "d1" * 32),
    ]
    cards = landscape_cards([source], rows)
    assert [(card.element_index, card.cluster_id[:2], card.tag, card.short_cite) for card in cards] == [
        (0, "01", "One", "Cite 24"),
        (3, "02", None, None),
    ]


def test_landscape_cards_carry_the_normalized_headings_without_an_open_tag_or_a_school() -> None:
    source = SeedSource(
        sha256="a1" * 32,
        teams=(SeedTeam(identity="one", side=Side.NEG, names=("Ashgrove Fictional", "XX")),),
        cards=(
            SeedCard(
                tag="Extinction outweighs",
                section_path=("1NC — Spending DA", "Ashgrove Fictional XX Impacts"),
                first_element_index=0,
            ),
            SeedCard(tag=None, section_path=("Spending DA", "Extinction outweighs"), first_element_index=3),
            SeedCard(
                tag="Elsewhere", section_path=("Birchmoor Fictional Turns Case",), first_element_index=6
            ),
        ),
    )
    rows = [_occurrence("a1" * 32, element, "01" * 32, "d1" * 32) for element in (0, 3, 6)]
    cards = landscape_cards([source], rows, {"Birchmoor Fictional": ("ZZ",)})
    # The open tag under the second card is no heading; Birchmoor is another school of the caselist.
    assert [card.headings for card in cards] == [
        ("spending da", "impacts"),
        ("spending da",),
        ("turns case",),
    ]


def test_landscape_cards_carry_whether_each_heading_answers() -> None:
    source = SeedSource(
        sha256="a1" * 32,
        teams=(SeedTeam(identity="one", side=Side.NEG, names=("Ashgrove Fictional", "XX")),),
        cards=(
            SeedCard(tag="Polls", section_path=("Midterms DA", "AT: Uniqueness"), first_element_index=0),
            SeedCard(tag="Polls", section_path=("Midterms DA", "Uniqueness"), first_element_index=3),
        ),
    )
    rows = [_occurrence("a1" * 32, element, "01" * 32, "d1" * 32) for element in (0, 3)]
    cards = landscape_cards([source], rows)
    assert [(card.headings, card.heading_answers) for card in cards] == [
        (("midterms da", "uniqueness"), (False, True)),
        (("midterms da", "uniqueness"), ()),
    ]


# ------------------------------------------------------------------------------------------------
# Scenarios and link chains (v1-e32-t14)
# ------------------------------------------------------------------------------------------------
#
# Counted by hand from the fixture's README, "Scenarios and link chains".


def _with_fixture_card(
    inputs: LandscapeReportInputs, source: str, element: int, **changes: object
) -> LandscapeReportInputs:
    """`inputs` with `source`'s card at `element` changed: its headings or its tag."""
    return dataclasses.replace(
        inputs,
        cards=tuple(
            one.model_copy(update=changes)
            if (one.source_sha256, one.element_index) == (source * 32, element)
            else one
            for one in inputs.cards
        ),
    )


def _row(report: LandscapeReport, position_id: str, cluster: str):  # noqa: ANN202 - the report's own row
    return next(
        card
        for card in report.impact_cards
        if card.position_id == position_id and card.fingerprint[:2] == cluster
    )


def _chain(report: LandscapeReport, position_id: str) -> dict[str, tuple[str, int]]:
    return {
        card.role.value: (card.fingerprint[:2], card.teams_reading)
        for card in report.chain_cards
        if card.position_id == position_id
    }


def test_chain_each_role_shows_its_most_read_labelled_cluster() -> None:
    report = _report()
    assert _chain(report, "spending-da") == {
        "uniqueness": ("40", 1),
        "link": ("14", 2),
        "internal_link": ("41", 1),
        "impact": ("15", 2),
    }
    assert _chain(report, "costs-advantage") == {"impact": ("02", 1), "solvency": ("35", 1)}
    assert _chain(report, "innovation-advantage") == {"internal_link": ("06", 1)}
    assert _chain(report, "election-da") == {"link": ("44", 1)}
    assert _chain(report, "hospital-closures-da") == {"impact": ("23", 1)}
    assert _chain(report, "provider-strikes-da") == {}
    assert {card.rank for card in report.chain_cards} == {1}


def test_chain_the_impact_role_is_the_impact_sections_first_row() -> None:
    report = _report()
    impacts = [card for card in report.chain_cards if card.role.value == "impact"]
    # The Costs advantage and the Spending and Hospital closures DAs have impact cards.
    assert [card.position_id for card in impacts] == [
        "costs-advantage",
        "spending-da",
        "hospital-closures-da",
    ]
    for card in impacts:
        if card.role.value == "impact":
            first = next(one for one in report.impact_cards if one.position_id == card.position_id)
            assert (card.fingerprint, card.teams_reading, card.tag) == (
                first.fingerprint,
                first.teams_reading,
                first.tag,
            )


def test_chain_an_answers_card_never_fills_a_role() -> None:
    # a1's `uq` card answers the Spending DA; b5's cluster 40 is its uniqueness. a3's cluster 36, under
    # `internal link` of the Costs advantage, answers it, so the advantage has no internal link.
    assert _chain(_report(), "costs-advantage").get("internal_link") is None
    as_read = _with_card(read_synthetic_caselist(FIXTURE), "a3", 12, role=PositionRole.READS)
    assert _chain(_report(as_read), "costs-advantage")["internal_link"] == ("36", 1)


def test_chain_a_card_in_a_round_on_the_other_side_never_fills_a_role() -> None:
    # a6, JJ's affirmative file, has a Midterms DA card under `internal link`.
    assert _chain(_report(), "election-da").get("internal_link") is None
    inputs = read_synthetic_caselist(FIXTURE)
    sideless = tuple(
        one.evolve(side=Side.UNKNOWN) if one.source_sha256 == "a6" * 32 else one for one in inputs.disclosures
    )
    assert _chain(_report(dataclasses.replace(inputs, disclosures=sideless)), "election-da")[
        "internal_link"
    ] == ("45", 1)


def test_chain_an_answer_sub_heading_fills_no_role() -> None:
    # b3's cluster 43 is under `AT: Uniqueness`; without the answer flag it is the DA's uniqueness.
    assert _chain(_report(), "election-da").get("uniqueness") is None
    plain = _with_fixture_card(read_synthetic_caselist(FIXTURE), "b3", 9, heading_answers=())
    assert _chain(_report(plain), "election-da")["uniqueness"] == ("43", 1)


def test_chain_no_link_and_a_u_in_a_tag_label_nothing() -> None:
    # a2's copy of cluster 2 is under `no link`; a5's cluster 38 is tagged `U: premiums are rising now`.
    chain = _chain(_report(), "costs-advantage")
    assert "link" not in chain and "uniqueness" not in chain
    inputs = _with_fixture_card(
        read_synthetic_caselist(FIXTURE), "a2", 0, headings=("costs advantage", "link")
    )
    inputs = _with_fixture_card(inputs, "a5", 9, tag="Uniqueness: premiums are rising now")
    chain = _chain(_report(inputs), "costs-advantage")
    assert (chain["link"], chain["uniqueness"]) == (("02", 1), ("38", 1))


def test_chain_a_heading_the_coach_ruled_names_no_position_still_labels_its_role() -> None:
    inputs = read_synthetic_caselist(FIXTURE)
    ruled = OverrideRules.model_validate(
        {
            "topic_id": inputs.overrides.topic_id,
            "overrides": [
                *(one.model_dump(mode="json") for one in inputs.overrides.overrides),
                {"heading": "link", "position_id": None},
                {"heading": "solvency", "position_id": None},
            ],
        }
    )
    report = _report(dataclasses.replace(inputs, overrides=ruled))
    assert _chain(report, "spending-da")["link"] == ("14", 2)
    assert _chain(report, "costs-advantage")["solvency"] == ("35", 1)


def test_lead_in_a_labelled_internal_link_above_the_impact_card() -> None:
    row = _row(_report(), "spending-da", "42")
    assert (row.internal_link_tag, row.card_above_tag) == ("Deficits spike interest rates", None)


def test_lead_in_an_answers_card_is_never_the_internal_link() -> None:
    # a3's cluster 36 sits above cluster 37 under the Costs advantage, labelled, but answers it.
    assert _row(_report(), "costs-advantage", "37").internal_link_tag is None
    as_read = _with_card(read_synthetic_caselist(FIXTURE), "a3", 12, role=PositionRole.READS)
    assert (
        _row(_report(as_read), "costs-advantage", "37").internal_link_tag == "Drug prices drive the deficit"
    )


def test_lead_in_the_card_above_is_shown_only_when_no_internal_link_is_labelled() -> None:
    row = _row(_report(), "costs-advantage", "02")
    assert (row.internal_link_tag, row.card_above_tag) == (None, "Single payer cuts administrative costs")
    labelled = _with_fixture_card(read_synthetic_caselist(FIXTURE), "a1", 3, tag="Internal link: costs fall")
    row = _row(_report(labelled), "costs-advantage", "02")
    assert (row.internal_link_tag, row.card_above_tag) == ("Internal link: costs fall", None)


def test_lead_in_the_card_above_is_never_an_impact_card_or_in_another_block() -> None:
    # a4's card above cluster 3 is under the Innovation advantage; b1's above cluster 15 is the `link` block.
    report = _report()
    assert _row(report, "costs-advantage", "03").card_above_tag is None
    assert _row(report, "spending-da", "15").card_above_tag is None
    impact_above = _with_fixture_card(read_synthetic_caselist(FIXTURE), "a1", 3, tag="Extinction from costs")
    assert _row(_report(impact_above), "costs-advantage", "02").card_above_tag is None


def test_scenario_a_name_shows_only_when_two_or_more_teams_use_it() -> None:
    report = _report()
    assert _row(report, "costs-advantage", "02").scenario == "economic collapse"
    assert _row(report, "costs-advantage", "03").scenario is None
    # a5 (QQ) filing cluster 2 under `drug prices` instead: each name now has the other's teams.
    moved = _with_fixture_card(
        read_synthetic_caselist(FIXTURE), "a5", 0, headings=("costs advantage", "drug prices")
    )
    report = _report(moved)
    assert (
        _row(report, "costs-advantage", "02").scenario,
        _row(report, "costs-advantage", "03").scenario,
    ) == (
        None,
        "drug prices",
    )


def test_scenario_a_name_holding_a_caselist_word_is_withheld_and_counted() -> None:
    report = _report()
    assert _row(report, "spending-da", "15").scenario is None
    assert {one.kind.value: one.withheld_names for one in report.chain_coverage} == {"advantage": 0, "da": 1}
    renamed = _with_fixture_card(
        read_synthetic_caselist(FIXTURE), "b1", 3, headings=("spending da", "harbor crash", "turns case")
    )
    report = _report(renamed)
    assert _row(report, "spending-da", "15").scenario == "harbor crash"
    assert {one.kind.value: one.withheld_names for one in report.chain_coverage} == {"advantage": 0, "da": 0}


def test_coverage_counts_what_no_heading_or_label_gives_per_kind() -> None:
    coverage = {one.kind.value: one for one in _report().chain_coverage}
    # Advantage: a6 alone has no scenario heading and no role label; DA: b3 and b6.
    assert {
        kind: (
            one.documents,
            one.unstructured_documents,
            one.positions,
            one.impact_rows,
            one.rows_with_scenario,
            one.rows_with_internal_link,
            one.rows_with_card_above,
        )
        for kind, one in coverage.items()
    } == {"advantage": (6, 1, 2, 3, 1, 0, 1), "da": (6, 2, 4, 4, 1, 1, 0)}
    assert [(gap.role.value, gap.positions) for gap in coverage["advantage"].roles_without_card] == [
        ("uniqueness", 2),
        ("link", 2),
        ("internal_link", 1),
        ("impact", 1),
        ("harms", 2),
        ("inherency", 2),
        ("solvency", 1),
    ]
    assert [(gap.role.value, gap.positions) for gap in coverage["da"].roles_without_card] == [
        ("uniqueness", 3),
        ("link", 2),
        ("internal_link", 3),
        ("impact", 2),
    ]


# ------------------------------------------------------------------------------------------------
# No model
# ------------------------------------------------------------------------------------------------


def test_no_module_that_builds_or_renders_the_report_imports_a_model_router() -> None:
    for module in (
        REPO / "packages/debate_core/src/debate_core/application/landscape_report.py",
        REPO / "packages/debate_core/src/debate_core/arguments/landscape/render.py",
        REPO / "packages/debate_core/src/debate_core/arguments/landscape/impacts.py",
        REPO / "packages/debate_core/src/debate_core/arguments/landscape/link_chains.py",
        REPO / "packages/debate_core/src/debate_core/domain/landscape_report.py",
    ):
        imported = {
            name
            for node in ast.walk(ast.parse(module.read_text(encoding="utf-8")))
            if isinstance(node, ast.ImportFrom)
            for name in [node.module or "", *(alias.name for alias in node.names)]
        }
        assert not {name for name in imported if "model_router" in name or "ModelRouter" in name}, module


# ------------------------------------------------------------------------------------------------
# Analytic texts (v1-e32-t11): CP texts, alternatives, roles of the ballot, overview counts
# ------------------------------------------------------------------------------------------------
#
# Counted by hand from tests/fixtures/landscape/synthetic_caselist/analytic_texts.json (its README's
# "Analytic texts"): b1 is read by YY and JJ, b2 by QQ, b3 and b6 by WW, b4 by YY, b5 by ZZ, b7 by VV on
# no readable side, b8 by KK; a1, a3 and a6 are XX's, VV's and JJ's affirmative files; b9 is out of range.


def _texts(report: LandscapeReport | None = None):  # noqa: ANN202 - the report's own type
    texts = (report or _report()).texts
    assert texts is not None
    return texts


def _shown(kind: AnalyticTextKind, position_id: str) -> list[tuple[int, int, str]]:
    found = next(one for one in _texts().positions if one.kind is kind and one.position_id == position_id)
    return [(row.rank, row.teams, row.text) for row in found.texts]


def test_texts_each_cp_shows_its_top_three_texts_by_teams_and_counts_the_rest() -> None:
    assert _shown(AnalyticTextKind.CP_TEXT, "states-cp") == [
        (1, 4, "The fifty states should establish a sample single payer system."),
        (2, 3, "Congress should give the fifty states sample block grants."),
        (3, 2, "The fifty states should adopt a sample payment cap."),
    ]
    states = next(one for one in _texts().positions if one.position_id == "states-cp")
    assert states.more == MoreTexts(position_id="states-cp", kind=AnalyticTextKind.CP_TEXT, texts=1, teams=1)
    # A CP no card counts for (courts-cp is below the threshold) still shows the texts placed under it.
    assert _shown(AnalyticTextKind.CP_TEXT, "courts-cp") == [
        (1, 1, "The federal courts should strike down a sample mandate.")
    ]


def test_texts_are_ordered_by_kind_then_by_their_teams() -> None:
    assert [(one.kind, one.position_id) for one in _texts().positions] == [
        (AnalyticTextKind.CP_TEXT, "states-cp"),
        (AnalyticTextKind.CP_TEXT, "courts-cp"),
        (AnalyticTextKind.K_ALTERNATIVE, "cap-k"),
        (AnalyticTextKind.ROLE_OF_THE_BALLOT, "cap-k"),
    ]


def test_texts_a_round_on_no_readable_side_counts_and_the_commonest_wording_shows() -> None:
    # b7's round has no side, so it is not the other side: VV reads the first alternative with QQ and KK.
    assert _shown(AnalyticTextKind.K_ALTERNATIVE, "cap-k") == [
        (1, 3, "The alternative is to reject sample markets in care."),
        (2, 2, "Our alternative is sample democratic planning."),
        (3, 1, "refuse the sample market."),
    ]


def test_texts_a_text_naming_a_school_is_withheld_and_counted() -> None:
    texts = _texts()
    shown = {row.text for one in texts.positions for row in one.texts}
    assert not any("Ashgrove" in text for text in shown)
    assert _coverage(texts, AnalyticTextKind.CP_TEXT).withheld_texts == 1


def _coverage(texts: LandscapeTexts, kind: AnalyticTextKind) -> TextCoverage:
    return next(one for one in texts.coverage if one.kind is kind)


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        # labels, documents, counted, elsewhere, place nothing, no heading, withheld, unread, guard
        # b6's labelled text with no actor, under no heading, is v1-e32-t16's (its list is refused).
        (AnalyticTextKind.CP_TEXT, (16, 8, 11, 2, 1, 2, 1, 1, 2)),
        (AnalyticTextKind.K_ALTERNATIVE, (9, 8, 5, 1, 1, 2, 0, 0, 0)),
        (AnalyticTextKind.ROLE_OF_THE_BALLOT, (2, 2, 1, 0, 1, 0, 0, 0, 0)),
        (AnalyticTextKind.OVERVIEW, (8, 8, 5, 1, 1, 1, 0, 0, 0)),
    ],
)
def test_texts_every_label_in_range_is_counted_by_where_it_was_placed(
    kind: AnalyticTextKind, expected: tuple[int, ...]
) -> None:
    one = _coverage(_texts(), kind)
    assert (
        one.labels,
        one.documents,
        one.counted,
        one.elsewhere,
        one.headings_place_nothing,
        one.no_heading,
        one.withheld_texts,
        one.unread,
        one.refused_by_guard,
    ) == expected


def test_texts_out_of_range_files_are_not_read() -> None:
    # b9 is disclosed after the report's date: its copy of the first CP text and its 5 refusals count nowhere.
    assert _coverage(_texts(), AnalyticTextKind.CP_TEXT).refused_by_guard == 2
    # Through the first snapshot only b1, b2 and b3 are in range: 1, 2 and 2 CP-text labels, and no refusal.
    texts = _texts(_report(_inputs(through=FIRST)))
    assert _coverage(texts, AnalyticTextKind.CP_TEXT).labels == 5
    assert _coverage(texts, AnalyticTextKind.CP_TEXT).refused_by_guard == 0


def test_texts_a_placed_text_not_read_again_counts_its_team_but_shows_another_copy() -> None:
    # b8's copy of the second text could not be read again; KK still reads it, and b4's copy shows.
    assert _shown(AnalyticTextKind.CP_TEXT, "states-cp")[1] == (
        2,
        3,
        "Congress should give the fifty states sample block grants.",
    )


def test_texts_overviews_are_counted_per_side_and_never_quoted() -> None:
    texts = _texts()
    assert [
        (one.position_id, one.label, one.position_kind.value, one.teams, one.aff_teams, one.neg_teams)
        for one in texts.overviews
    ] == [
        ("election-da", "Midterms DA", "da", 2, 1, 2),
        ("costs-advantage", "Costs advantage", "advantage", 1, 1, 0),
        ("states-cp", "States CP", "cp", 1, 0, 1),
    ]
    assert AnalyticTextKind.OVERVIEW not in {one.kind for one in texts.positions}


def test_texts_without_readings_the_report_has_no_text_sections() -> None:
    assert _report(_inputs(analytic_texts=None)).texts is None


def test_texts_a_text_is_never_beside_a_school_or_team_code() -> None:
    disclosures = read_synthetic_caselist(FIXTURE).disclosures
    names = {one.school for one in disclosures} | {one.team_code for one in disclosures}
    dumped = _texts().model_dump_json()
    assert not {
        name for name in names if re.search(rf"(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])", dumped)
    }


# ------------------------------------------------------------------------------------------------
# A CP's planks (v1-e32-t16), grouped by the advantage they solve
# ------------------------------------------------------------------------------------------------
#
# Counted by hand from the same fixture's planks (its README's "Planks"): the teams are t11's above.


def _planks(report: LandscapeReport | None = None):  # noqa: ANN202 - the report's own type
    found = {one.position_id: one for one in _texts(report).planks}
    return found


def test_planks_each_cp_groups_its_planks_by_the_advantage_they_solve_top_three_each() -> None:
    states = _planks()["states-cp"]
    assert [
        (group.solves, group.label, [(row.rank, row.teams, row.text) for row in group.planks])
        for group in states.groups
    ] == [
        (
            "costs-advantage",
            "Costs advantage",
            [
                (1, 4, "Expand sample clinics to cut costs."),
                (2, 3, "Cap sample drug prices to cut costs and spur innovation."),
                (3, 2, "The fifty states should also cap sample premiums."),
            ],
        ),
        (
            "innovation-advantage",
            "Innovation advantage",
            [
                (1, 3, "Cap sample drug prices to cut costs and spur innovation."),
                (2, 1, "Fund a sample research prize."),
            ],
        ),
        (None, None, [(1, 3, "Publish a sample price list."), (2, 1, "Hire sample navigators.")]),
    ]
    assert states.groups[0].more == MoreTexts(
        position_id="states-cp", kind=AnalyticTextKind.CP_PLANK, texts=1, teams=1
    )
    assert [group.more for group in states.groups[1:]] == [None, None]
    assert list(_planks()) == ["states-cp"]


def test_planks_a_plank_naming_two_advantages_counts_once_in_the_totals() -> None:
    states = _planks()["states-cp"]
    assert (states.planks, states.teams, states.withheld) == (8, 6, 1)


def test_planks_a_plank_naming_a_school_is_withheld_and_counted() -> None:
    texts = _texts()
    shown = {row.text for one in texts.planks for group in one.groups for row in group.planks}
    assert shown and not any("Ashgrove" in text for text in shown)
    assert _coverage(texts, AnalyticTextKind.CP_PLANK).withheld_texts == 1


def test_planks_every_plank_in_range_is_counted_by_where_it_went() -> None:
    one = _coverage(_texts(), AnalyticTextKind.CP_PLANK)
    assert (
        one.labels,
        one.documents,
        one.counted,
        one.elsewhere,
        one.headings_place_nothing,
        one.no_heading,
        one.withheld_texts,
        one.unread,
        one.refused_by_guard,
        one.plank_labels,
        one.solves_other_words,
    ) == (16, 8, 14, 1, 0, 1, 1, 1, 2, 1, 1)


def test_planks_out_of_range_files_are_not_read() -> None:
    # b9's plank, label and refusals are after the report's date; through the first snapshot, b1, b2 and
    # b3's five planks are in range, and b6's refusals and label are not.
    shown = {row.text for one in _texts().planks for group in one.groups for row in group.planks}
    assert "Ban sample surprise bills." not in shown
    first = _coverage(_texts(_report(_inputs(through=FIRST))), AnalyticTextKind.CP_PLANK)
    assert (first.labels, first.refused_by_guard, first.plank_labels) == (5, 0, 0)


# ------------------------------------------------------------------------------------------------
# Advantages by affirmative (`v1-e32-t15`)
# ------------------------------------------------------------------------------------------------
#
# Over `tests/fixtures/landscape/advantages_per_aff/`, whose README holds the table every expected
# number here was counted from by hand, and whose `report_section.md` was written by hand from it.

ADVANTAGES = REPO / "tests" / "fixtures" / "landscape" / "advantages_per_aff"


def _advantage_inputs() -> LandscapeReportInputs:
    """The fixture's rounds as disclosures, its files' cards as classifications, and t09's assignments."""
    table = yaml.safe_load((ADVANTAGES / "rounds.yaml").read_text(encoding="utf-8"))
    taxonomy = Taxonomy.model_validate(
        yaml.safe_load((ADVANTAGES / "taxonomy.yaml").read_text(encoding="utf-8"))
    )
    school_of = {code: school for school, codes in table["schools"].items() for code in codes}
    disclosures: list[Disclosure] = []
    assignments: list[AffAssignment] = []
    for row in table["rounds"]:
        school, code, side = school_of[row["team"]], row["team"], Side(row["side"])
        for name in row["files"]:
            disclosures.append(
                Disclosure(
                    caselist=SYNTHETIC_CASELIST,
                    event=Event.POLICY,
                    school=school,
                    team_code=code,
                    side=side,
                    tournament=row["tournament"],
                    round_label=RoundLabel(raw=row["round"], normalized=row["round"]),
                    snapshot=SECOND,
                    source_path=f"{school}/{school} {code}/{code}-{side.value}-{row['round']}-{name}.docx",
                    source_sha256=name * 32,
                )
            )
        if row.get("assigned"):
            assignments.append(
                AffAssignment(
                    round_id=round_id(disclosures[-1]), position_id=row["assigned"], method=row["method"]
                )
            )
    classifications: list[PositionClassification] = []
    for name, cards in table["files"].items():
        for index, card in enumerate(cards):
            placed = {"position": card} if isinstance(card, str) else card
            classifications.append(
                PositionClassification(
                    item_id=f"{name * 32}:card:{index}",
                    item_kind=ItemKind.CARD,
                    source_sha256=name * 32,
                    first_element_index=index,
                    position_id=placed["position"],
                    role=PositionRole(placed.get("role", "READS")),
                    method=ClassificationMethod(placed.get("method", "ALIAS")),
                    confidence=float(placed.get("confidence", 1.0)),
                    rationale="synthetic fixture: placed as the fixture table says",
                    taxonomy_version=taxonomy.taxonomy_version,
                    prompt_version="none",
                )
            )
    return LandscapeReportInputs(
        caselist=SYNTHETIC_CASELIST,
        through=SECOND,
        taxonomy=taxonomy,
        overrides=OverrideRules(topic_id=taxonomy.topic_id, overrides=()),
        parser_version="2026.10.20-docx-6",
        classifications=classifications,
        disclosures=disclosures,
        cards=(),
        aff_assignments=tuple(assignments),
    )


def _by_aff(advantages_per_aff: int = 5, inputs: LandscapeReportInputs | None = None) -> AdvantagesByAff:
    report = LandscapeReportService(advantages_per_aff=advantages_per_aff).build(
        inputs or _advantage_inputs(), synthetic_staleness()
    )
    assert report.advantages_by_aff is not None
    return report.advantages_by_aff


def _section(found: AdvantagesByAff, position_id: str) -> tuple[list[tuple[str, int]], int, int]:
    """An aff's shown advantages with their teams, and its `more` and `more_teams`."""
    one = next(aff for aff in found.affs if aff.position_id == position_id)
    return [(row.position_id, row.teams) for row in one.advantages], one.more, one.more_teams


def test_advantages_report_md_section_matches_the_hand_written_golden_file() -> None:
    bundle = LandscapeReportService().bundle(_advantage_inputs(), synthetic_staleness())
    report_md = bundle.files["report.md"]
    start = report_md.index("## Advantages by affirmative\n")
    # The section ends at the next section of its level or the next part's heading (`v1-e32-t20`).
    following = re.compile(r"\n#{1,2} ").search(report_md, start)
    assert following is not None
    end = following.start() + 1
    assert report_md[start:end] == (ADVANTAGES / "report_section.md").read_text(encoding="utf-8")


def test_advantages_a_read_in_a_round_assigned_to_another_aff_is_never_counted_under_this_one() -> None:
    found = _by_aff()
    # QQ's Public option round reads innovation and pandemics; under Single payer they stay YY's alone,
    # so they are the 2 more, read by 1 team, and QQ's Single payer reads stay out of Public option.
    assert _section(found, "single-payer-aff") == (
        [
            ("costs-advantage", 3),
            ("coverage-advantage", 3),
            ("budgets-advantage", 2),
            ("disease-advantage", 2),
            ("inequality-advantage", 1),
        ],
        2,
        1,
    )
    assert _section(found, "public-option-aff") == (
        [("innovation-advantage", 1), ("pandemics-advantage", 1)],
        0,
        0,
    )


def test_advantages_a_mechanism_round_counts_under_the_mechanism_and_once_under_its_aff() -> None:
    found = _by_aff()
    single_payer = next(aff for aff in found.affs if aff.position_id == "single-payer-aff")
    assert (single_payer.rounds, single_payer.teams, single_payer.advantage_teams) == (6, 5, 4)
    global_budgets = next(aff for aff in found.affs if aff.position_id == "global-budgets-aff")
    assert (global_budgets.mechanism_of, global_budgets.rounds, global_budgets.teams) == (
        "single-payer-aff",
        2,
        2,
    )
    assert _section(found, "global-budgets-aff") == ([("budgets-advantage", 2), ("costs-advantage", 2)], 0, 0)


def test_advantages_the_cut_off_shows_the_top_n_and_counts_the_rest_by_distinct_teams() -> None:
    assert _by_aff(3).advantages_per_aff == 3
    assert _section(_by_aff(3), "single-payer-aff") == (
        [("costs-advantage", 3), ("coverage-advantage", 3), ("budgets-advantage", 2)],
        4,
        3,
    )
    assert _section(_by_aff(7), "single-payer-aff")[1:] == (0, 0)
    assert len(_section(_by_aff(7), "single-payer-aff")[0]) == 7


def test_advantages_the_teams_behind_and_n_more_are_distinct_never_a_sum() -> None:
    # Innovation and pandemics are YY's alone: one team, where a sum would say two.
    assert _section(_by_aff(), "single-payer-aff")[1:] == (2, 1)


def test_advantages_the_affs_are_ordered_and_those_with_no_advantage_read_are_listed_apart() -> None:
    found = _by_aff()
    assert [aff.position_id for aff in found.affs] == [
        "single-payer-aff",
        "global-budgets-aff",
        "public-option-aff",
    ]
    assert [(one.position_id, one.mechanism_of, one.rounds) for one in found.without_advantages] == [
        ("nanomedicine-aff", "single-payer-aff", 1),
        ("voucher-aff", None, 1),
    ]


def test_advantages_nothing_is_taken_from_an_advantages_taxonomy_parent() -> None:
    # costs-advantage names Public option as its parent; Public option's round reads no costs card.
    assert "costs-advantage" not in {row for row, _ in _section(_by_aff(), "public-option-aff")[0]}


def test_advantages_reads_with_no_assigned_aff_count_placed_card_rounds_with_them() -> None:
    assert _by_aff().unassigned == UnassignedAdvantageReads(reads=4, rounds=3, teams=2, placed_card_rounds=1)


def test_advantages_without_assignments_every_affirmative_advantage_read_has_no_assigned_aff() -> None:
    # The t03 fixture through 2026-09-15: all 7 affirmative rounds read costs or innovation, 9 reads by
    # 6 teams (XX's two rounds are one team), and a placed aff card identifies 4 of the rounds.
    found = _report().advantages_by_aff
    assert found is not None
    assert (found.affs, found.without_advantages) == ((), ())
    assert found.unassigned == UnassignedAdvantageReads(reads=9, rounds=7, teams=6, placed_card_rounds=4)


def test_advantages_a_taxonomy_with_no_advantage_has_no_section() -> None:
    inputs = _advantage_inputs()
    without = dataclasses.replace(
        inputs,
        taxonomy=inputs.taxonomy.model_copy(
            update={
                "positions": tuple(
                    one for one in inputs.taxonomy.positions if one.kind is not PositionKind.ADVANTAGE
                )
            }
        ),
        classifications=[
            one for one in inputs.classifications if not (one.position_id or "").endswith("-advantage")
        ],
    )
    bundle = LandscapeReportService().bundle(without, synthetic_staleness())
    assert bundle.report.advantages_by_aff is None
    assert "## Advantages by affirmative" not in bundle.files["report.md"]


def test_advantages_a_cut_off_below_one_is_refused() -> None:
    with pytest.raises(ValueError, match="at least one advantage"):
        LandscapeReportService(advantages_per_aff=0)


# ------------------------------------------------------------------------------------------------
# Kritikal affirmatives (`v1-e32-t17`)
# ------------------------------------------------------------------------------------------------
#
# Over `tests/fixtures/landscape/kritikal_affs/`, whose README holds the table every expected number
# here was counted from by hand, and whose `report_section.md` and `method_table.md` were written by
# hand from it.

KRITIKAL = REPO / "tests" / "fixtures" / "landscape" / "kritikal_affs"


def _kritikal_inputs(*, with_kritikal: bool = True) -> LandscapeReportInputs:
    """The fixture's rounds as disclosures, its files' cards as classifications, the assignments, and the
    K-aff inputs: marker files, each file's heading families, and the rounds the advantage guard refused.

    Without them, as a run with no K-aff config, no round is assigned the K aff either."""
    table = yaml.safe_load((KRITIKAL / "rounds.yaml").read_text(encoding="utf-8"))
    taxonomy = Taxonomy.model_validate(
        yaml.safe_load((KRITIKAL / "taxonomy.yaml").read_text(encoding="utf-8"))
    )
    school_of = {code: school for school, codes in table["schools"].items() for code in codes}
    disclosures: list[Disclosure] = []
    assignments: list[AffAssignment] = []
    refused: set[str] = set()
    for row in table["rounds"]:
        school, code, side = school_of[row["team"]], row["team"], Side(row["side"])
        for name in row["files"]:
            disclosures.append(
                Disclosure(
                    caselist=SYNTHETIC_CASELIST,
                    event=Event.POLICY,
                    school=school,
                    team_code=code,
                    side=side,
                    tournament=row["tournament"],
                    round_label=RoundLabel(raw=row["round"], normalized=row["round"]),
                    snapshot=SECOND,
                    source_path=f"{school}/{school} {code}/{code}-{side.value}-{row['round']}-{name}.docx",
                    source_sha256=name * 32,
                )
            )
        if row.get("assigned") and (with_kritikal or row["assigned"] != table["kritikal"]["position_id"]):
            assignments.append(
                AffAssignment(
                    round_id=round_id(disclosures[-1]), position_id=row["assigned"], method=row["method"]
                )
            )
        if row.get("refused_by_advantage"):
            refused.add(round_id(disclosures[-1]))
    classifications = [
        PositionClassification(
            item_id=f"{name * 32}:card:{index}",
            item_kind=ItemKind.CARD,
            source_sha256=name * 32,
            first_element_index=index,
            position_id=position,
            role=PositionRole.READS,
            method=ClassificationMethod.ALIAS,
            confidence=1.0,
            rationale="synthetic fixture: placed as the fixture table says",
            taxonomy_version=taxonomy.taxonomy_version,
            prompt_version="none",
        )
        for name, cards in table["files"].items()
        for index, position in enumerate(cards)
    ]
    found = table["kritikal"]
    kritikal = KritikalAffInputs(
        position_id=found["position_id"],
        marker_sources=frozenset(name * 32 for name in found["marker_files"]),
        heading_families={name * 32: tuple(families) for name, families in found["heading_families"].items()},
        families=dict(found["families"]),
        refused_by_advantage=frozenset(refused),
    )
    return LandscapeReportInputs(
        caselist=SYNTHETIC_CASELIST,
        through=SECOND,
        taxonomy=taxonomy,
        overrides=OverrideRules(topic_id=taxonomy.topic_id, overrides=()),
        parser_version="2026.10.20-docx-6",
        classifications=classifications,
        disclosures=disclosures,
        cards=(),
        aff_assignments=tuple(assignments),
        kritikal_affs=kritikal if with_kritikal else None,
    )


def _kritikal(inputs: LandscapeReportInputs | None = None) -> KritikalAffs:
    report = LandscapeReportService().build(inputs or _kritikal_inputs(), synthetic_staleness())
    assert report.kritikal_affs is not None
    return report.kritikal_affs


def _kritikal_report_md(inputs: LandscapeReportInputs | None = None) -> str:
    return (
        LandscapeReportService()
        .bundle(inputs or _kritikal_inputs(), synthetic_staleness())
        .files["report.md"]
    )


def test_kritikal_report_md_section_matches_the_hand_written_golden_file() -> None:
    report_md = _kritikal_report_md()
    start = report_md.index("## Kritikal affirmatives\n")
    following = re.compile(r"\n#{1,2} ").search(report_md, start)
    assert following is not None
    assert report_md[start : following.start() + 1] == (KRITIKAL / "report_section.md").read_text(
        encoding="utf-8"
    )


def test_kritikal_method_table_matches_the_hand_written_golden_file() -> None:
    report_md = _kritikal_report_md()
    start = report_md.index("How affirmative rounds were identified:\n")
    end = report_md.index("not read this season.\n", start) + len("not read this season.\n")
    assert report_md[start:end] == (KRITIKAL / "method_table.md").read_text(encoding="utf-8")


def test_kritikal_the_group_sits_in_the_affirmative_part_after_the_advantages_by_aff() -> None:
    report_md = _kritikal_report_md()
    affirmative, negative = report_md.index("# Affirmative\n"), report_md.index("# Negative\n")
    advantages, kritikal = (
        report_md.index("## Advantages by affirmative\n"),
        report_md.index("## Kritikal affirmatives\n"),
    )
    assert affirmative < advantages < kritikal < negative


def test_kritikal_rounds_by_marker_and_by_carry_with_their_teams() -> None:
    found = _kritikal()
    assert (found.position_id, found.rounds, found.teams, found.by_marker, found.by_carry) == (
        "kritikal-aff",
        3,
        2,
        2,
        1,
    )


def test_kritikal_the_rounds_the_advantage_guard_refused_are_counted_and_stay_unidentified() -> None:
    report = LandscapeReportService().build(_kritikal_inputs(), synthetic_staleness())
    assert report.kritikal_affs is not None
    assert report.kritikal_affs.refused_by_advantage == 1
    assert report.unclassified.aff_rounds_unidentified == 2


def test_kritikal_families_count_only_the_k_aff_files_headings_ordered_by_files_teams_then_config() -> None:
    families = [(one.family_id, one.files, one.teams) for one in _kritikal().families]
    assert families == [("cap", 3, 2), ("settler-colonialism", 1, 1), ("afropessimism", 1, 1)]


def test_kritikal_the_control_counts_marker_files_in_rounds_identified_another_way() -> None:
    found = _kritikal()
    assert (found.control_files, found.control_rounds) == (2, 2)


def test_kritikal_the_k_aff_is_an_affirmative_position_with_its_rounds() -> None:
    report = LandscapeReportService().build(_kritikal_inputs(), synthetic_staleness())
    row = next(one for one in report.positions if one.position_id == "kritikal-aff")
    assert (row.kind, row.rounds, row.teams, row.aff_rounds) == (PositionKind.AFF, 3, 2, 3)


def test_kritikal_without_k_aff_inputs_there_is_no_group_and_no_extra_rows() -> None:
    inputs = _kritikal_inputs(with_kritikal=False)
    report = LandscapeReportService().build(inputs, synthetic_staleness())
    assert report.kritikal_affs is None
    report_md = _kritikal_report_md(inputs)
    assert "## Kritikal affirmatives" not in report_md
    assert "not carried in" not in report_md
    assert "(a control:" not in report_md
    assert "KRITIKAL_AFF" not in report_md

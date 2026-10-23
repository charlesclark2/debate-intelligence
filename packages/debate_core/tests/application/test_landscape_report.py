"""LandscapeReportService over the synthetic two-snapshot caselist (`v1-e32-t03` ac1 to ac3).

Every expected number here was counted by hand from the fixture's table
(`tests/fixtures/landscape/synthetic_caselist/README.md`, `scripts/make_landscape_fixture.py`),
never read off the service. Tests named `aggregate` are the aggregation node's; `top_cards` the
top-card node's.
"""

from __future__ import annotations

import ast
import csv
import dataclasses
from datetime import date
from pathlib import Path

import pytest

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
from debate_core.arguments.landscape.seeding import SeedCard, SeedSource
from debate_core.domain.card_occurrence import ClusterMembership
from debate_core.domain.caselist import Disclosure, Side
from debate_core.domain.debate_files import CardCompleteness
from debate_core.domain.landscape_classification import OverrideRules
from debate_core.domain.landscape_report import AffAssignment, LandscapeReport, PositionStats
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


def _report(inputs: LandscapeReportInputs | None = None, *, top_cards: int = 5) -> LandscapeReport:
    return LandscapeReportService(top_cards=top_cards).build(inputs or _inputs(), synthetic_staleness())


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


def test_aggregate_below_threshold_and_queued_items_are_unclassified_not_counted() -> None:
    report = _report()
    assert "courts-cp" not in {stats.position_id for stats in report.positions}
    assert (_position(report, "public-option-aff").rounds, _position(report, "public-option-aff").teams) == (
        1,
        1,
    )
    summary = report.unclassified
    assert (summary.cards, summary.unplaced_cards, summary.below_threshold_cards) == (42, 8, 2)
    assert (summary.unclassified_cards, summary.decided_no_position_cards) == (10, 1)
    assert (report.header.cards, report.header.cards_placed) == (42, 31)


@pytest.mark.parametrize(("threshold", "unplaced", "below", "placed"), [(0.95, 8, 10, 23), (0.4, 8, 0, 33)])
def test_aggregate_the_report_threshold_decides_what_is_unclassified(
    threshold: float, unplaced: int, below: int, placed: int
) -> None:
    # At 0.95 the eight INHERITED cards in range (0.9: a1 two, a3, a6, b1 two, b5, b6) fall below it
    # too; at 0.4 the two TAG_KEYWORD cards (0.5) are counted.
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
    # b9 (2026-09-22) reads cap-k and spending-da, and its cards would make 44.
    assert (_position(report, "cap-k").rounds, _position(report, "spending-da").rounds) == (3, 4)
    assert (report.header.snapshot, report.header.rounds, report.unclassified.cards) == (SECOND, 16, 42)


def test_aggregate_a_round_carried_into_the_next_window_is_one_round_first_seen_in_the_first() -> None:
    report = _report()
    single_payer = _position(report, "single-payer-aff")
    # a1 at the first tournament (listed in both windows), a1 at the second, a6.
    assert (single_payer.rounds, single_payer.teams, single_payer.first_seen_snapshot) == (3, 2, FIRST)


def test_aggregate_one_file_two_teams_disclosed_counts_in_both_rounds() -> None:
    states = _position(_report(), "states-cp")
    # b1 (YY and JJ) and b5 (ZZ).
    assert (states.rounds, states.teams) == (3, 3)


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
    # Cluster 2: XX (two copies, once), ZZ, VV and QQ. Cluster 3: KK.
    assert _top(report, "costs-advantage") == [("02", 4), ("03", 1)]
    # Cluster 14: YY and JJ (one file), QQ, ZZ. Cluster 15: YY and JJ.
    assert _top(report, "spending-da") == [("14", 4), ("15", 2)]


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


def test_top_cards_every_row_is_file_import() -> None:
    assert {card.provenance_mode.value for card in _report().top_cards} == {"FILE_IMPORT"}


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


# ------------------------------------------------------------------------------------------------
# No model
# ------------------------------------------------------------------------------------------------


def test_no_module_that_builds_or_renders_the_report_imports_a_model_router() -> None:
    for module in (
        REPO / "packages/debate_core/src/debate_core/application/landscape_report.py",
        REPO / "packages/debate_core/src/debate_core/arguments/landscape/render.py",
        REPO / "packages/debate_core/src/debate_core/domain/landscape_report.py",
    ):
        imported = {
            name
            for node in ast.walk(ast.parse(module.read_text(encoding="utf-8")))
            if isinstance(node, ast.ImportFrom)
            for name in [node.module or "", *(alias.name for alias in node.names)]
        }
        assert not {name for name in imported if "model_router" in name or "ModelRouter" in name}, module

"""The occurrence table and caselist card statistics (`v1-e31-t04` ac4, and ac3 in context).

Every school, team code, author and card here is invented (`Maple Grove`, `QX`, `Cedar Hollow`,
`ZaLu`), and the only cutter mark is the obviously synthetic `zzTEST`
(`docs/policies/caselist-data-use.md`). Expected counts are worked out by hand in each test's
comments from the cards the test builds, never read back from the service.
"""

from __future__ import annotations

import asyncio
import json
from datetime import date
from pathlib import Path

import pytest

from debate_core.application.caselist_card_stats import (
    CaselistCardReport,
    CaselistCardStatsService,
    UnreadableParsedCards,
    read_parsed_cards,
)
from debate_core.application.settings import CardFingerprintSettings
from debate_core.domain.card_occurrence import ClusterMembership
from debate_core.domain.caselist import Disclosure, Event, RoundLabel, Side, SourceOrigin
from debate_core.domain.debate_files import (
    CardCompleteness,
    FileImportProvenance,
    ParsedCard,
    ParsedDocument,
)
from debate_core.domain.style_profile import StyleMatchSource
from debate_core.evidence.fingerprints import FINGERPRINT_VERSION
from debate_core.evidence.near_duplicates import NearDuplicateThresholds
from debate_core.testing.fakes import InMemoryCaselistRepository

CASELIST = "testcl26"
WEEK_ONE, WEEK_TWO, WEEK_THREE = date(2026, 9, 1), date(2026, 9, 8), date(2026, 9, 15)

FILE_A = "a" * 64
FILE_B = "b" * 64
FILE_C = "c" * 64
FILE_D = "d" * 64

HEAT = (
    "Cities that pave over their green space do not merely lose shade; they lose the evening. The "
    "Varrow Commission's survey of forty mid-sized municipalities found that asphalt and roofing "
    "retain the afternoon's heat well past midnight, so that neighbourhoods with the least canopy "
    "cool the least overnight. The commission concluded that canopy loss is a public health problem "
    "before it is an aesthetic one."
)
HEAT_TRIMMED = HEAT.split(" The commission concluded")[0]
WAREHOUSE = (
    "Automation rarely eliminates a job outright; it removes the tasks within a job that were "
    "easiest to measure. Injury reports rose in the eighteen months after installation, and "
    "turnover among new hires nearly doubled."
)


def card(
    source: str,
    element: int,
    body: str = HEAT,
    *,
    snapshot: date = WEEK_ONE,
    short_cite: str | None = "Pellam 26",
    full_cite: str = "Pellam 26 (Oriel Pellam, Fictional Review of Urban Climate, 2026)",
    tag: str = "Canopy loss kills",
    completeness: CardCompleteness = CardCompleteness.FULL,
    caselist: str | None = CASELIST,
) -> ParsedCard:
    return ParsedCard(
        tag=tag,
        short_cite=short_cite,
        full_cite=full_cite,
        evidence_text=body,
        completeness=completeness,
        match_source=StyleMatchSource.VERBATIM,
        confidence=1.0,
        provenance=FileImportProvenance(
            source_sha256=source,
            source_path=f"synthetic/{source[:4]}.docx",
            origin=SourceOrigin.CASELIST_ARCHIVE if caselist else SourceOrigin.OPENEV,
            caselist=caselist,
            camp=None if caselist else "Invented Camp",
            snapshot=snapshot,
            first_element_index=element,
            last_element_index=element + 1,
            parser_version="test-parser",
            profile_version="test-profile",
        ),
    )


def disclosure(
    source: str,
    snapshot: date,
    *,
    school: str = "Maple Grove",
    team_code: str = "QX",
    side: Side = Side.AFF,
    tournament: str = "Invented Invitational",
    round_raw: str = "Round 1",
    path: str | None = None,
) -> Disclosure:
    return Disclosure(
        source_sha256=source,
        caselist=CASELIST,
        snapshot=snapshot,
        event=Event.LD,
        school=school,
        team_code=team_code,
        side=side,
        tournament=tournament,
        round_label=RoundLabel.from_raw(round_raw),
        source_path=path or f"{school}/{team_code}/{school}-{team_code}-{side}-{tournament}-{round_raw}.docx",
    )


def build_report(
    cards: list[ParsedCard],
    disclosures: list[Disclosure],
    **options: object,
) -> CaselistCardReport:
    repository = InMemoryCaselistRepository()

    async def run() -> CaselistCardReport:
        for item in disclosures:
            await repository.record_disclosure(item)
        service = CaselistCardStatsService(repository, ellipsis_markers=("…",))
        return await service.report(cards, caselist=CASELIST, **options)  # type: ignore[arg-type]

    return asyncio.run(run())


# ------------------------------------------------------------------------------------------------
# ac4: cumulative snapshots collapse; teams are counted, not files
# ------------------------------------------------------------------------------------------------


def test_three_cumulative_snapshots_yield_one_occurrence_with_first_and_last_seen() -> None:
    # One file, disclosed once, present in three weekly archives and parsed under each of them.
    cards = [card(FILE_A, 4, snapshot=week) for week in (WEEK_THREE, WEEK_ONE, WEEK_TWO)]
    disclosures = [disclosure(FILE_A, week) for week in (WEEK_ONE, WEEK_TWO, WEEK_THREE)]

    report = build_report(cards, disclosures)

    assert len(report.occurrences) == 1
    occurrence = report.occurrences[0]
    assert occurrence.first_seen_snapshot == WEEK_ONE
    assert occurrence.last_seen_snapshot == WEEK_THREE
    assert (occurrence.school, occurrence.team_code, occurrence.side) == ("Maple Grove", "QX", Side.AFF)
    assert occurrence.tournament == "Invented Invitational"
    assert occurrence.round_label == RoundLabel.from_raw("Round 1")
    assert occurrence.source_sha256 == FILE_A
    assert occurrence.element_index == 4
    assert occurrence.fingerprint_version == FINGERPRINT_VERSION
    # Three parsed records, one card position, one occurrence, one card, one team.
    totals = report.totals
    assert (totals.parsed_cards, totals.cards, totals.occurrences, totals.clusters, totals.teams) == (
        3,
        1,
        1,
        1,
        1,
    )


def test_a_reupload_under_a_second_path_is_the_same_occurrence() -> None:
    disclosures = [
        disclosure(FILE_A, WEEK_ONE),
        disclosure(
            FILE_A, WEEK_TWO, path="Maple Grove/QX/Maple Grove-QX-Aff-Invented Invitational-Round 1 (1).docx"
        ),
    ]
    report = build_report([card(FILE_A, 4)], disclosures)
    assert len(report.occurrences) == 1
    assert report.occurrences[0].last_seen_snapshot == WEEK_TWO


def test_cluster_counts_distinct_teams_not_files() -> None:
    # QX reads the heat card in three rounds, from three different files (one of them trimmed).
    # ZaLu reads it once, in the same bytes QX used in round one.
    cards = [
        card(FILE_A, 4),
        card(FILE_B, 9, HEAT_TRIMMED, tag="Asphalt keeps cities hot"),
        card(FILE_C, 2, HEAT.replace("'", "’"), tag="Heat islands"),
        card(FILE_D, 0, WAREHOUSE, short_cite="Thorne 26", tag="Automation intensifies work"),
    ]
    disclosures = [
        disclosure(FILE_A, WEEK_ONE),
        disclosure(
            FILE_A, WEEK_ONE, school="Cedar Hollow", team_code="ZaLu", side=Side.NEG, round_raw="Round 3"
        ),
        disclosure(FILE_B, WEEK_ONE, round_raw="Round 2"),
        disclosure(FILE_C, WEEK_TWO, round_raw="Octas"),
        disclosure(FILE_D, WEEK_TWO, school="Cedar Hollow", team_code="ZaLu"),
    ]

    report = build_report(cards, disclosures, include_teams=True)

    heat, warehouse = report.top_clusters
    # Heat: occurrences QX/A, ZaLu/A, QX/B, QX/C = 4; files A, B, C = 3; teams QX, ZaLu = 2.
    assert (heat.distinct_teams, heat.occurrences, heat.files) == (2, 4, 3)
    assert heat.short_cite == "Pellam 26"
    assert heat.teams == (("Cedar Hollow", "ZaLu"), ("Maple Grove", "QX"))
    assert (warehouse.distinct_teams, warehouse.occurrences, warehouse.files) == (1, 1, 1)
    assert warehouse.short_cite == "Thorne 26"
    # Card positions A4, B9, C2, D0 = 4. Exact bodies: HEAT (A and C normalize alike), HEAT_TRIMMED,
    # WAREHOUSE = 3. Clusters: heat, warehouse = 2. Duplicate rate 1 - 2/4.
    totals = report.totals
    assert (totals.cards, totals.occurrences, totals.exact_unique, totals.clusters, totals.teams) == (
        4,
        5,
        3,
        2,
        2,
    )
    assert totals.duplicate_rate == 0.5


def test_teams_are_left_out_unless_asked_for() -> None:
    report = build_report([card(FILE_A, 4)], [disclosure(FILE_A, WEEK_ONE)])
    assert report.top_clusters[0].teams is None


def test_a_card_with_no_disclosure_is_a_card_but_not_a_team() -> None:
    report = build_report([card(FILE_A, 4, snapshot=WEEK_TWO)], [])
    (occurrence,) = report.occurrences
    assert occurrence.school is None and occurrence.team_code is None and occurrence.team is None
    assert occurrence.first_seen_snapshot == occurrence.last_seen_snapshot == WEEK_TWO
    assert (report.totals.cards, report.totals.teams, report.top_clusters[0].distinct_teams) == (1, 0, 0)


def test_other_caselists_and_camp_files_are_left_out() -> None:
    cards = [card(FILE_A, 4), card(FILE_B, 1, caselist="othercl26"), card(FILE_C, 1, caselist=None)]
    report = build_report(cards, [])
    assert report.totals.parsed_cards == 1


def test_snapshot_reports_what_was_known_on_that_date() -> None:
    cards = [card(FILE_A, 4, snapshot=week) for week in (WEEK_ONE, WEEK_TWO, WEEK_THREE)] + [
        card(FILE_B, 0, WAREHOUSE, short_cite="Thorne 26", snapshot=WEEK_THREE)
    ]
    disclosures = [disclosure(FILE_A, week) for week in (WEEK_ONE, WEEK_TWO, WEEK_THREE)] + [
        disclosure(FILE_B, WEEK_THREE, team_code="QY")
    ]

    report = build_report(cards, disclosures, snapshot=WEEK_TWO)

    assert report.snapshot == WEEK_TWO
    (occurrence,) = report.occurrences
    assert occurrence.last_seen_snapshot == WEEK_TWO
    assert report.totals.clusters == 1


def test_top_limits_and_orders_clusters() -> None:
    cards = [
        card(FILE_A, 0, WAREHOUSE, short_cite="Thorne 26"),
        card(FILE_B, 0),
        card(FILE_C, 0),
    ]
    disclosures = [
        disclosure(FILE_A, WEEK_ONE),
        disclosure(FILE_B, WEEK_ONE),
        disclosure(FILE_C, WEEK_ONE, team_code="QY"),
    ]
    report = build_report(cards, disclosures, top=1)
    (only,) = report.top_clusters
    assert only.short_cite == "Pellam 26"
    assert only.distinct_teams == 2


# ------------------------------------------------------------------------------------------------
# ac3 in the table: abbreviated disclosures count toward the full card's cluster
# ------------------------------------------------------------------------------------------------


def test_linked_abbreviated_card_counts_toward_the_full_cards_cluster() -> None:
    abbreviated = card(
        FILE_B,
        3,
        "Cities that pave over … before it is an aesthetic one.",
        short_cite="Pellam '26",
        completeness=CardCompleteness.ABBREVIATED,
    )
    unmatched = card(
        FILE_C,
        3,
        "Cities that pave over … before it is a fiscal one.",
        completeness=CardCompleteness.ABBREVIATED,
    )
    disclosures = [
        disclosure(FILE_A, WEEK_ONE),
        disclosure(FILE_B, WEEK_ONE, school="Cedar Hollow", team_code="ZaLu"),
        disclosure(FILE_C, WEEK_ONE, school="Cedar Hollow", team_code="ZaLu", round_raw="Round 2"),
    ]

    report = build_report([card(FILE_A, 4), abbreviated, unmatched], disclosures)

    by_source = {occurrence.source_sha256: occurrence for occurrence in report.occurrences}
    assert by_source[FILE_B].membership is ClusterMembership.ABBREVIATED_LINK
    assert by_source[FILE_B].cluster_id == by_source[FILE_A].cluster_id
    assert by_source[FILE_C].membership is ClusterMembership.UNLINKED
    assert by_source[FILE_C].cluster_id == by_source[FILE_C].exact_fingerprint
    assert report.top_clusters[0].distinct_teams == 2
    assert report.top_clusters[0].tag == "Canopy loss kills"
    assert (report.totals.linked_abbreviated, report.totals.unlinked_abbreviated) == (1, 1)


# ------------------------------------------------------------------------------------------------
# Cutter marks: recorded verbatim, never repr'd, never in statistics
# ------------------------------------------------------------------------------------------------


def test_cutter_mark_is_recorded_on_the_occurrence_and_nowhere_else() -> None:
    signed = card(FILE_A, 4, full_cite="Pellam 26 (Oriel Pellam, Fictional Review, 2026) //zzTEST")
    report = build_report([signed], [disclosure(FILE_A, WEEK_ONE)], include_teams=True)

    (occurrence,) = report.occurrences
    assert occurrence.cutter_mark == "zzTEST"
    assert "zzTEST" not in repr(occurrence)
    assert "zzTEST" not in repr(report.top_clusters) + repr(report.totals)


# ------------------------------------------------------------------------------------------------
# Determinism
# ------------------------------------------------------------------------------------------------


def test_report_does_not_depend_on_input_order() -> None:
    cards = [
        card(FILE_A, 4),
        card(FILE_B, 9, HEAT_TRIMMED),
        card(FILE_D, 0, WAREHOUSE, short_cite="Thorne 26"),
    ]
    disclosures = [disclosure(FILE_A, WEEK_ONE), disclosure(FILE_B, WEEK_ONE, team_code="QY")]
    forward = build_report(cards, disclosures, include_teams=True)
    backward = build_report(list(reversed(cards)), list(reversed(disclosures)), include_teams=True)
    assert forward == backward


# ------------------------------------------------------------------------------------------------
# Reading parsed-card JSONL, and the thresholds from settings
# ------------------------------------------------------------------------------------------------


def test_read_parsed_cards_accepts_cards_and_documents(tmp_path: Path) -> None:
    first, second = card(FILE_A, 4), card(FILE_B, 1, WAREHOUSE)
    document = ParsedDocument(
        source_sha256=FILE_B,
        source_path="synthetic/bbbb.docx",
        parser_version="test-parser",
        profile_version="test-profile",
        cards=(second,),
    )
    (tmp_path / "nested").mkdir()
    (tmp_path / "a.jsonl").write_text(first.model_dump_json() + "\n\n", encoding="utf-8")
    (tmp_path / "nested" / "b.jsonl").write_text(document.model_dump_json() + "\n", encoding="utf-8")
    (tmp_path / "ignored.txt").write_text("not read", encoding="utf-8")

    assert read_parsed_cards(tmp_path) == [first, second]


def test_an_unreadable_line_names_the_file_and_line_but_not_its_content(tmp_path: Path) -> None:
    good = card(FILE_A, 4).model_dump_json()
    broken = json.loads(good)
    broken["completeness"] = "HALF"
    (tmp_path / "cards.jsonl").write_text(f"{good}\n{json.dumps(broken)}\n", encoding="utf-8")

    with pytest.raises(UnreadableParsedCards) as raised:
        read_parsed_cards(tmp_path)

    message = str(raised.value)
    assert "cards.jsonl line 2" in message
    assert "completeness" in message
    assert "Cities" not in message and "Pellam" not in message

    (tmp_path / "cards.jsonl").write_text("{not json\n", encoding="utf-8")
    with pytest.raises(UnreadableParsedCards, match="line 1 is not a parsed card: not JSON"):
        read_parsed_cards(tmp_path)


def test_thresholds_come_from_settings() -> None:
    assert CardFingerprintSettings().thresholds() == NearDuplicateThresholds(jaccard=0.8, containment=0.9)
    tuned = CardFingerprintSettings(near_duplicate_jaccard=0.7, near_duplicate_containment=0.95)
    assert tuned.thresholds() == NearDuplicateThresholds(jaccard=0.7, containment=0.95)

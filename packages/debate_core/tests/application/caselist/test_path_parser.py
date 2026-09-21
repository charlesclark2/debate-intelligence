"""Every shape of disclosed filename the importer has to survive, as a table.

The canonical pattern is one row of it. The rest are the ways real archives break it, and the
rule they are all checked against is the same one ac1 states: an unreadable name yields a
disclosure with side `UNKNOWN` and a warning, never a dropped file.

The odd cases come from two places. The synthetic fixture's members are all here, so the parser
and the archives it is tested with cannot drift apart. The rest are shapes the operator reported
from the real corpus — a numeric copy index after the side, em dashes, doubled and quadrupled
hyphens, bracketed numbers, files with no side at all — written here as invented equivalents,
because `docs/policies/caselist-data-use.md` forbids a real filename in a committed test.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from tests.fixtures.caselist.build_synthetic_archives import SNAPSHOTS, SYNTHETIC_EVENT

from debate_core.application.caselist.path_parser import (
    UNKNOWN_SCHOOL,
    UNKNOWN_TEAM_CODE,
    ParsedDisclosurePath,
    parse_disclosure_path,
    source_format_for,
)
from debate_core.domain.caselist import (
    Event,
    NormalizedRound,
    Side,
    SourceFormat,
)


@dataclass(frozen=True, slots=True)
class ParseCase:
    """One path and what reading it must produce."""

    name: str
    path: str
    side: Side
    tournament: str | None
    round_raw: str | None
    normalized_round: NormalizedRound | None = None
    school: str = "Maple Grove"
    team_code: str = "QX"
    event: Event = Event.LD
    source_format: SourceFormat = SourceFormat.DOCX
    copy_index: int | None = None
    warnings: int = 0


PARSE_CASES: tuple[ParseCase, ...] = (
    ParseCase(
        name="the canonical pattern",
        path="Maple Grove/QX/Maple Grove-QX-Aff-Grove City Invitational-Round 1.docx",
        side=Side.AFF,
        tournament="Grove City Invitational",
        round_raw="Round 1",
        normalized_round=NormalizedRound.R1,
    ),
    ParseCase(
        name="a side shouted, and no round at all",
        path="Cedar Hollow/ZaLu/Cedar Hollow-ZaLu-AFF-Harbor Classic.docx",
        side=Side.AFF,
        tournament="Harbor Classic",
        round_raw=None,
        school="Cedar Hollow",
        team_code="ZaLu",
        warnings=1,
    ),
    ParseCase(
        name="a side spelled out, and an elimination round",
        path="Cedar Hollow/ZaLu/Cedar Hollow-ZaLu-Negative-Harbor Classic-Octas.docx",
        side=Side.NEG,
        tournament="Harbor Classic",
        round_raw="Octas",
        normalized_round=NormalizedRound.OCTAS,
        school="Cedar Hollow",
        team_code="ZaLu",
    ),
    ParseCase(
        name="a doubled hyphen, and a tournament whose own name contains 'Round'",
        path=("Northgate Prep/BeCo/Northgate Prep-BeCo-Affirmative-Ridgeline Round Robin--Doubles.docx"),
        side=Side.AFF,
        tournament="Ridgeline Round Robin",
        round_raw="Doubles",
        normalized_round=NormalizedRound.DOUBLES,
        school="Northgate Prep",
        team_code="BeCo",
    ),
    ParseCase(
        name="a numeric copy index after the side, and four hyphens",
        path=("Northgate Prep/BeCo/Northgate Prep-BeCo-Neg-02----Ridgeline Round Robin-Round 6.docx"),
        side=Side.NEG,
        tournament="Ridgeline Round Robin",
        round_raw="Round 6",
        normalized_round=NormalizedRound.R6,
        school="Northgate Prep",
        team_code="BeCo",
        copy_index=2,
    ),
    ParseCase(
        name="a Public Forum side in a Lincoln-Douglas caselist",
        path="Riverbend Academy/MnPr/Riverbend Academy-MnPr-Pro-Seaside Cup-Finals.docx",
        side=Side.UNKNOWN,
        tournament="Seaside Cup",
        round_raw="Finals",
        normalized_round=NormalizedRound.FINALS,
        school="Riverbend Academy",
        team_code="MnPr",
        warnings=1,
    ),
    ParseCase(
        name="the same name in the Public Forum caselist it belongs to",
        path="Riverbend Academy/MnPr/Riverbend Academy-MnPr-Pro-Seaside Cup-Finals.docx",
        side=Side.PRO,
        tournament="Seaside Cup",
        round_raw="Finals",
        normalized_round=NormalizedRound.FINALS,
        school="Riverbend Academy",
        team_code="MnPr",
        event=Event.PF,
    ),
    ParseCase(
        name="a Public Forum con, in Public Forum",
        path="Riverbend Academy/MnPr/Riverbend Academy-MnPr-Con-Seaside Cup-Round 4.docx",
        side=Side.CON,
        tournament="Seaside Cup",
        round_raw="Round 4",
        normalized_round=NormalizedRound.R4,
        school="Riverbend Academy",
        team_code="MnPr",
        event=Event.PF,
    ),
    ParseCase(
        name="a PDF, stored unparsed",
        path="Riverbend Academy/MnPr/Riverbend Academy-MnPr-Aff-Seaside Cup-Quarters.pdf",
        side=Side.AFF,
        tournament="Seaside Cup",
        round_raw="Quarters",
        normalized_round=NormalizedRound.QUARTERS,
        school="Riverbend Academy",
        team_code="MnPr",
        source_format=SourceFormat.PDF,
    ),
    ParseCase(
        name="a legacy .doc, stored unparsed",
        path="Riverbend Academy/MnPr/Riverbend Academy-MnPr-Neg-Seaside Cup-Quarters.doc",
        side=Side.NEG,
        tournament="Seaside Cup",
        round_raw="Quarters",
        normalized_round=NormalizedRound.QUARTERS,
        school="Riverbend Academy",
        team_code="MnPr",
        source_format=SourceFormat.DOC,
    ),
    ParseCase(
        name="a browser's re-upload suffix",
        path="Maple Grove/QX/Maple Grove-QX-Aff-Grove City Invitational-Round 1 (1).docx",
        side=Side.AFF,
        tournament="Grove City Invitational",
        round_raw="Round 1",
        normalized_round=NormalizedRound.R1,
        copy_index=1,
    ),
    ParseCase(
        name="a bracketed copy number inside the tournament",
        path="Maple Grove/QX/Maple Grove-QX-Neg-Bayview Open [2]-Semis.docx",
        side=Side.NEG,
        tournament="Bayview Open",
        round_raw="Semis",
        normalized_round=NormalizedRound.SEMIS,
        copy_index=2,
    ),
    ParseCase(
        name="an em dash where a hyphen belongs",
        path="Riverbend Academy/MnPr/Riverbend Academy-MnPr-Aff-Seaside Cup—Round 5.docx",
        side=Side.AFF,
        tournament="Seaside Cup",
        round_raw="Round 5",
        normalized_round=NormalizedRound.R5,
        school="Riverbend Academy",
        team_code="MnPr",
    ),
    ParseCase(
        name="a filename prefix naming neither the school nor the team its directories name",
        path="Northgate Prep/BeCo/Westfield-XY-Neg-Ridgeline Round Robin-Round 3.docx",
        side=Side.NEG,
        tournament="Ridgeline Round Robin",
        round_raw="Round 3",
        normalized_round=NormalizedRound.R3,
        school="Northgate Prep",
        team_code="BeCo",
        warnings=1,
    ),
    ParseCase(
        name="no structure at all",
        path="Cedar Hollow/ZaLu/notes about the harbor round.docx",
        side=Side.UNKNOWN,
        tournament=None,
        round_raw=None,
        school="Cedar Hollow",
        team_code="ZaLu",
        warnings=1,
    ),
    ParseCase(
        name="an abbreviated school in the prefix is the ordinary case, not a warning",
        path="Northgate Prep/BeCo/Northgate-BeCo-Neg-Ridgeline Round Robin-Round 3.docx",
        side=Side.NEG,
        tournament="Ridgeline Round Robin",
        round_raw="Round 3",
        normalized_round=NormalizedRound.R3,
        school="Northgate Prep",
        team_code="BeCo",
    ),
    ParseCase(
        name="no prefix at all: the side is the first token",
        path="Maple Grove/QX/Aff-Grove City Invitational-Round 2.docx",
        side=Side.AFF,
        tournament="Grove City Invitational",
        round_raw="Round 2",
        normalized_round=NormalizedRound.R2,
    ),
    ParseCase(
        name="a round the platform does not recognise is kept and warned about",
        path="Maple Grove/QX/Maple Grove-QX-Aff-Grove City Invitational-Round Robin.docx",
        side=Side.AFF,
        tournament="Grove City Invitational",
        round_raw="Round Robin",
        normalized_round=None,
        warnings=1,
    ),
    ParseCase(
        name="a trailing copy number after a readable round",
        path="Maple Grove/QX/Maple Grove-QX-Neg-Grove City Invitational-Round 6-2.docx",
        side=Side.NEG,
        tournament="Grove City Invitational",
        round_raw="Round 6",
        normalized_round=NormalizedRound.R6,
        copy_index=2,
    ),
    ParseCase(
        name="a two-word elimination round is not half tournament",
        path="Maple Grove/QX/Maple Grove-QX-Aff-Bayview Open-Double-Octas.docx",
        side=Side.AFF,
        tournament="Bayview Open",
        round_raw="Double Octas",
        normalized_round=NormalizedRound.DOUBLES,
    ),
    ParseCase(
        name="a side and a round but no tournament",
        path="Maple Grove/QX/Maple Grove-QX-Aff-Finals.docx",
        side=Side.AFF,
        tournament=None,
        round_raw="Finals",
        normalized_round=NormalizedRound.FINALS,
        warnings=1,
    ),
    ParseCase(
        name="a side and nothing after it",
        path="Maple Grove/QX/Maple Grove-QX-Neg.docx",
        side=Side.NEG,
        tournament=None,
        round_raw=None,
        warnings=2,
    ),
    ParseCase(
        name="a file filed straight under its school, with no team-code directory",
        path="Maple Grove/Maple Grove-QX-Aff-Grove City Invitational-Round 1.docx",
        side=Side.AFF,
        tournament="Grove City Invitational",
        round_raw="Round 1",
        normalized_round=NormalizedRound.R1,
        team_code=UNKNOWN_TEAM_CODE,
        warnings=1,
    ),
    ParseCase(
        name="a file at the archive root, in no directory at all",
        path="Maple Grove-QX-Aff-Grove City Invitational-Round 1.docx",
        side=Side.AFF,
        tournament="Grove City Invitational",
        round_raw="Round 1",
        normalized_round=NormalizedRound.R1,
        school=UNKNOWN_SCHOOL,
        team_code=UNKNOWN_TEAM_CODE,
        warnings=1,
    ),
    ParseCase(
        name="an unknown extension is stored as OTHER",
        path="Maple Grove/QX/Maple Grove-QX-Aff-Grove City Invitational-Round 1.rtf",
        side=Side.AFF,
        tournament="Grove City Invitational",
        round_raw="Round 1",
        normalized_round=NormalizedRound.R1,
        source_format=SourceFormat.OTHER,
    ),
    ParseCase(
        name="a school whose name contains a side word is not read as a side",
        path="Concord Academy/RiOs/Concord Academy-RiOs-Neg-Seaside Cup-Round 2.docx",
        side=Side.NEG,
        tournament="Seaside Cup",
        round_raw="Round 2",
        normalized_round=NormalizedRound.R2,
        school="Concord Academy",
        team_code="RiOs",
    ),
)


@pytest.mark.parametrize("case", PARSE_CASES, ids=lambda case: case.name)
def test_a_disclosed_filename_is_read_into_its_fields(case: ParseCase) -> None:
    parsed = parse_disclosure_path(case.path, event=case.event)

    assert parsed.school == case.school
    assert parsed.team_code == case.team_code
    assert parsed.side == case.side
    assert parsed.tournament == case.tournament
    assert (parsed.round_label.raw if parsed.round_label else None) == case.round_raw
    assert (parsed.round_label.normalized if parsed.round_label else None) == case.normalized_round
    assert parsed.source_format == case.source_format
    assert parsed.copy_index == case.copy_index


@pytest.mark.parametrize("case", PARSE_CASES, ids=lambda case: case.name)
def test_the_parser_warns_exactly_as_often_as_it_could_not_read_something(case: ParseCase) -> None:
    """A warning per thing that could not be read — and none at all when everything could.

    Counted rather than matched on wording so the messages can be improved without rewriting the
    table, but counted exactly, because a parser that warns about everything is a parser nobody
    reads the warnings of.
    """
    parsed = parse_disclosure_path(case.path, event=case.event)

    assert len(parsed.warnings) == case.warnings, parsed.warnings
    assert parsed.is_fully_parsed == (case.warnings == 0)


@pytest.mark.parametrize("case", PARSE_CASES, ids=lambda case: case.name)
def test_the_side_recorded_is_always_one_the_event_debates(case: ParseCase) -> None:
    """ac1's floor: whatever the filename said, the record is one the domain will store."""
    from debate_core.domain.caselist import sides_for_event

    parsed = parse_disclosure_path(case.path, event=case.event)

    assert parsed.side in sides_for_event(case.event)


# ------------------------------------------------------------------------------------------------
# Nothing is ever dropped
# ------------------------------------------------------------------------------------------------

UNREADABLE_PATHS = (
    "",
    ".",
    "a.docx",
    "----.docx",
    "Maple Grove/QX/-----.docx",
    "Maple Grove/QX/.docx",
    "Maple Grove/QX/——.docx",
    "Maple Grove/QX/(1).docx",
    "Maple Grove/QX/[2] [3] [4].docx",
    "Maple Grove/QX/Aff.docx",
    "Maple Grove/QX/12345.docx",
    "Maple Grove/QX/Maple Grove-QX-Aff-" + "x" * 300 + ".docx",
)


@pytest.mark.parametrize("path", UNREADABLE_PATHS, ids=lambda path: repr(path))
def test_an_unreadable_path_still_yields_a_parsed_result(path: str) -> None:
    """The contract: every path parses. A name this bad is a warning, never an exception."""
    parsed = parse_disclosure_path(path, event=Event.LD)

    assert isinstance(parsed, ParsedDisclosurePath)
    assert parsed.school
    assert parsed.team_code
    assert parsed.side in {Side.AFF, Side.NEG, Side.UNKNOWN}


# ------------------------------------------------------------------------------------------------
# Team codes are never widened
# ------------------------------------------------------------------------------------------------


def test_a_team_directory_with_whitespace_is_refused_and_not_quoted_back() -> None:
    """The case most likely to be a real name, so neither the value nor a hint of it may travel.

    `docs/policies/caselist-data-use.md` treats every team code as personal data about a minor and
    forbids one in a log, a manifest row or a console line. A "team code" with a space in it is
    almost always a pair of names, and the domain refuses it outright (`TeamCodeText`).
    """
    parsed = parse_disclosure_path(
        "Maple Grove/Rivera and Osei/Maple Grove-Aff-Grove City Invitational-Round 1.docx",
        event=Event.LD,
    )

    assert parsed.team_code == UNKNOWN_TEAM_CODE
    assert len(parsed.warnings) >= 1
    assert not any("Rivera" in warning or "Osei" in warning for warning in parsed.warnings)


def test_a_team_directory_longer_than_the_domain_allows_is_refused_and_not_quoted_back() -> None:
    parsed = parse_disclosure_path(
        "Maple Grove/ThisIsFarTooLongToBeACode/Maple Grove-Aff-Seaside Cup-Round 1.docx",
        event=Event.LD,
    )

    assert parsed.team_code == UNKNOWN_TEAM_CODE
    assert not any("ThisIsFarTooLong" in warning for warning in parsed.warnings)


def test_a_team_code_the_domain_accepts_is_kept_exactly_as_disclosed() -> None:
    """Rule 1 of the policy: exactly as disclosed, and nothing more."""
    parsed = parse_disclosure_path(
        "Maple Grove/ZaLu/Maple Grove-ZaLu-Aff-Seaside Cup-Round 1.docx", event=Event.LD
    )

    assert parsed.team_code == "ZaLu"


# ------------------------------------------------------------------------------------------------
# The fixture and the parser agree
# ------------------------------------------------------------------------------------------------


def test_every_member_of_the_synthetic_fixture_parses() -> None:
    """The archives the import tests run against hold no path this parser chokes on."""
    event = Event(SYNTHETIC_EVENT)
    for snapshot in SNAPSHOTS:
        for member in snapshot.members:
            if member.body is None or member.zip_only:
                continue
            parsed = parse_disclosure_path(member.path, event=event)
            assert parsed.source_path == member.path


def test_the_fixture_carries_exactly_the_warnings_the_expected_summary_counts() -> None:
    """The fixture's expected warning counts are the parser's, member by member.

    Both halves of ac1 in one assertion: the odd names parse, and the ones that cannot be fully
    read are exactly the ones the committed summary says are warned about.
    """
    event = Event(SYNTHETIC_EVENT)
    warned = {
        member.path
        for member in SNAPSHOTS[-1].members
        if member.body is not None
        and not member.zip_only
        and parse_disclosure_path(member.path, event=event).warnings
    }

    assert warned == {
        "Cedar Hollow/ZaLu/Cedar Hollow-ZaLu-AFF-Harbor Classic.docx",
        "Cedar Hollow/ZaLu/notes about the harbor round.docx",
        "Northgate Prep/BeCo/Westfield-XY-Neg-Ridgeline Round Robin-Round 3.docx",
        "Riverbend Academy/MnPr/Riverbend Academy-MnPr-Pro-Seaside Cup-Finals.docx",
    }


# ------------------------------------------------------------------------------------------------
# Formats
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("a.docx", SourceFormat.DOCX),
        ("a.DOCX", SourceFormat.DOCX),
        ("a.doc", SourceFormat.DOC),
        ("a.pdf", SourceFormat.PDF),
        ("a.PDF", SourceFormat.PDF),
        ("a.rtf", SourceFormat.OTHER),
        ("a", SourceFormat.OTHER),
    ],
)
def test_the_extension_decides_the_stored_format(filename: str, expected: SourceFormat) -> None:
    assert source_format_for(filename) == expected

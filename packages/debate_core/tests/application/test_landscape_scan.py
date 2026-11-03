"""The scan before a landscape report is shared, and what makes two weeks' hits the same hit (`v1-e32-t05`).

Every school, team code, tournament and path here is invented.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from debate_core.application.landscape_scan import (
    ScanAcceptance,
    ScanAcceptanceLog,
    ScanHit,
    ScanKind,
    hits_by_section,
    hits_digest,
    pending_hits,
    scan_report,
)
from debate_core.domain.caselist import Disclosure, Event, Side

SHA = "a" * 64


def _disclosure(
    school: str = "Quillmere Academy", code: str = "QW", tournament: str | None = "Lantern Classic"
) -> Disclosure:
    return Disclosure(
        source_sha256=SHA,
        caselist="synthetic26",
        snapshot=date(2026, 9, 15),
        event=Event.POLICY,
        school=school,
        team_code=code,
        side=Side.AFF,
        tournament=tournament,
        source_path=f"{school}/{code}/{school}-{code}-Aff-Round 1.docx",
    )


def _terms(text: str, *disclosures: Disclosure) -> list[tuple[ScanKind, str]]:
    return [(hit.kind, hit.term) for hit in scan_report({"report.md": text}, disclosures or (_disclosure(),))]


def test_a_team_code_is_found_case_sensitively_as_a_whole_word() -> None:
    assert _terms("As QW said") == [(ScanKind.TEAM_CODE, "QW")]
    assert _terms("QW, then") == [(ScanKind.TEAM_CODE, "QW")]
    assert _terms("qw said") == []
    assert _terms("QWERTY and AQW") == []


def test_a_school_or_tournament_is_found_as_words_without_regard_to_case() -> None:
    assert _terms("per quillmere academy") == [(ScanKind.SCHOOL, "Quillmere Academy")]
    assert _terms("the LANTERN CLASSIC file") == [(ScanKind.TOURNAMENT, "Lantern Classic")]
    assert _terms("Quillmere Academyx") == []


def test_a_school_of_three_characters_or_fewer_is_not_looked_for() -> None:
    short = _disclosure(school="Ash", code="ZZ", tournament="Elm")
    assert _terms("ash and elm trees", short) == []
    assert _terms("Ashe Elmo", _disclosure(school="Ashe", code="ZZ", tournament="Elmo")) == [
        (ScanKind.SCHOOL, "Ashe"),
        (ScanKind.TOURNAMENT, "Elmo"),
    ]


def test_a_path_is_found_anywhere_in_a_line() -> None:
    path = _disclosure().source_path
    assert (ScanKind.PATH, path) in _terms(f"see x{path}y")


def test_unknown_school_and_code_are_not_terms() -> None:
    unknown = _disclosure(school="UNKNOWN", code="UNKNOWN", tournament=None)
    assert _terms("UNKNOWN said UNKNOWN", unknown) == []


def test_one_hit_per_term_per_line_with_its_line_number() -> None:
    hits = scan_report({"top_cards.csv": "header\nQW and QW again\nnothing\nQW"}, [_disclosure()])
    assert [(hit.file, hit.line_number) for hit in hits] == [("top_cards.csv", 2), ("top_cards.csv", 4)]


def test_a_hit_keeps_its_key_when_its_counts_and_its_place_change() -> None:
    this_week = ScanHit(
        "top_cards.csv", 3, ScanKind.TEAM_CODE, "QW", "spending-da,1,2,As QW argued,Okonkwo 26"
    )
    next_week = ScanHit(
        "top_cards.csv", 9, ScanKind.TEAM_CODE, "QW", "spending-da,3,14,As QW argued,Okonkwo 26"
    )
    assert this_week.key == next_week.key


def test_a_hit_in_a_changed_tag_is_a_new_hit() -> None:
    before = ScanHit("top_cards.csv", 3, ScanKind.TEAM_CODE, "QW", "spending-da,1,2,As QW argued,Okonkwo 26")
    after = ScanHit("top_cards.csv", 3, ScanKind.TEAM_CODE, "QW", "spending-da,1,2,As QW wrote,Okonkwo 26")
    elsewhere = ScanHit("report.md", 3, ScanKind.TEAM_CODE, "QW", "spending-da,1,2,As QW argued,Okonkwo 26")
    assert len({before.key, after.key, elsewhere.key}) == 3


def test_the_digest_is_of_the_hits_in_no_order() -> None:
    one = ScanHit("a.csv", 1, ScanKind.SCHOOL, "Quillmere Academy", "x Quillmere Academy")
    two = ScanHit("b.csv", 2, ScanKind.TEAM_CODE, "QW", "y QW")
    assert hits_digest([one, two]) == hits_digest([two, one])
    assert hits_digest([one, two]) != hits_digest([one])
    assert len(hits_digest([one])) == 12


def test_accepted_hits_are_remembered_and_only_new_ones_are_pending(tmp_path: Path) -> None:
    log = ScanAcceptanceLog(tmp_path / "acceptances")
    one = ScanHit("a.csv", 1, ScanKind.TEAM_CODE, "QW", "As QW argued")
    two = ScanHit("a.csv", 2, ScanKind.TEAM_CODE, "PX", "As PX argued")
    log.record(
        ScanAcceptance("synthetic26", date(2026, 9, 15), date(2026, 9, 17), hits_digest([one]), (one,))
    )

    assert log.accepted("synthetic26") == {one.key}
    assert log.accepted("othercl26") == frozenset()
    assert pending_hits((one, two), log.accepted("synthetic26")) == (two,)


def test_a_damaged_acceptance_line_accepts_nothing(tmp_path: Path) -> None:
    log = ScanAcceptanceLog(tmp_path)
    log.path("synthetic26").write_text(
        '{"hits": [{"key": "abc"}]}\nnot json\n{"hits": "nope"}\n', encoding="utf-8"
    )

    assert log.accepted("synthetic26") == {"abc"}


def test_the_school_view_is_scanned_for_paths_only() -> None:
    """`v1-e32-t04`: schools.csv and schools.md name schools, team codes and tournaments by design."""
    disclosure = _disclosure()
    line = "Quillmere Academy,QW,aff,single-payer-aff,1,Lantern Classic"
    files = {"schools.csv": line, "report.md": line}
    hits = scan_report(files, (disclosure,), school_view_files=("schools.csv",))
    assert {(hit.file, hit.kind) for hit in hits} == {
        ("report.md", ScanKind.TEAM_CODE),
        ("report.md", ScanKind.SCHOOL),
        ("report.md", ScanKind.TOURNAMENT),
    }
    with_a_path = {"schools.csv": f"{line} {disclosure.source_path}"}
    hits = scan_report(with_a_path, (disclosure,), school_view_files=("schools.csv",))
    assert [(hit.file, hit.kind) for hit in hits] == [("schools.csv", ScanKind.PATH)]


# -- the hits by section (v1-e32-t16) --------------------------------------------------------------

REPORT = """\
# Sample landscape

Intro line.

## Counterplan texts, alternatives and roles of the ballot

### Counterplan texts

| Rank | Teams | Text |
|---|---|---|
| 1 | 2 | As QW argued, sample text. |

Its planks: 2, read by 2 teams.

| Solves | Rank | Teams | Plank |
|---|---|---|---|
| Costs advantage | 1 | 2 | As QW argued, sample plank. |
| not named | 1 | 1 | Quillmere Academy sample plank. |

* Costs advantage: and 1 more plank, read by 1 team.

## Overviews

Sample QW line.
"""


def test_hits_are_counted_by_file_section_and_kind_with_the_plank_tables_apart() -> None:
    lines = REPORT.splitlines()

    def hit(number: int, kind: ScanKind, term: str, file: str = "report.md") -> ScanHit:
        line = lines[number - 1] if file == "report.md" else "x,As QW argued"
        return ScanHit(file, number, kind, term, line)

    text_hit = hit(11, ScanKind.TEAM_CODE, "QW")
    plank_hit = hit(17, ScanKind.TEAM_CODE, "QW")
    school_hit = hit(18, ScanKind.SCHOOL, "Quillmere Academy")
    more_hit = hit(20, ScanKind.TEAM_CODE, "QW")
    overview_hit = hit(24, ScanKind.TEAM_CODE, "QW")
    csv_hit = hit(2, ScanKind.TEAM_CODE, "QW", file="top_cards.csv")
    found = hits_by_section(
        [text_hit, plank_hit, school_hit, more_hit, overview_hit, csv_hit],
        [plank_hit, csv_hit],
        {"report.md": REPORT, "top_cards.csv": "a\nx,As QW argued\n"},
    )
    assert [(one.file, one.section, one.kind, one.hits, one.not_yet_accepted) for one in found] == [
        ("report.md", "Counterplan texts", ScanKind.TEAM_CODE, 2, 0),
        ("report.md", "Counterplan texts: plank table", ScanKind.TEAM_CODE, 1, 1),
        ("report.md", "Counterplan texts: plank table", ScanKind.SCHOOL, 1, 0),
        ("report.md", "Overviews", ScanKind.TEAM_CODE, 1, 0),
        ("top_cards.csv", "(whole file)", ScanKind.TEAM_CODE, 1, 1),
    ]


def test_a_hit_above_every_heading_is_at_the_top_and_no_hit_counts_nothing() -> None:
    hit = ScanHit("report.md", 1, ScanKind.TEAM_CODE, "QW", "QW at the top")
    found = hits_by_section([hit], [], {"report.md": "QW at the top\n## Later\n"})
    assert [(one.section, one.hits) for one in found] == [("(top)", 1)]
    assert hits_by_section([], [], {"report.md": REPORT}) == ()

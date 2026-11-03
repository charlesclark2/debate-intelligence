"""`scripts/sample_cite_shapes.py --plan bold-in-part`: the lines t24's rule leaves (`v1-e31-t32`).

One invented file in (7)'s formatting, whose defaults make every run bold at 13 pt and whose bodies
and cites switch bold off at 11 pt. Each line above a cite is written to be one case. The file is
read by the parser this branch carries, as the sample will read the store. Every expectation is
written by hand from what the file was built to hold (working agreement 6).

====  ==========================================================  ==================================
 at    paragraph                                                   stratum
====  ==========================================================  ==================================
  0    a tag in `Heading4`                                         -
  1    cite, bracketed                                             -
  2    body                                                        -
  3    bold in part: a trailing two words switched off             bold in part, nothing else fails
  4    cite, bracketed, opening a card with no tag                 -
  5    body                                                        -
  6    bold in part and over 300 characters                        bold in part, something else too
  7    cite, bracketed, opening a card with no tag                 -
  8    body                                                        -
  9    nothing set: bold throughout as Word shows it               - (t24's rule reads it as a tag)
 10    cite, bracketed                                             -
 11    body                                                        -
 12    bold switched off throughout                                not bold
 13    cite, bracketed, opening a card with no tag                 -
 14    body                                                        -
 15    bold in part, in a paragraph style that maps to no unit     read through a style (its alias)
 16    cite, bracketed, opening a card with no tag                 -
 17    body                                                        -
 18    bold in part, inside a body, above no cite                  -
 19    body                                                        -
 20    a tag in `Heading4`                                         -
 21    bold switched off, under the tag                            - (its cite's card has a tag)
 22    cite, bracketed                                             -
 23    body                                                        -
 24    an analytic in the `Analytic` style                         - (read as an analytic)
 25    cite, bracketed, opening a card with no tag                 -
 26    body                                                        -
====  ==========================================================  ==================================
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from tests.evals.parser.cite_shapes import READING_SIZE, SOURCE, prose, qualifications

from debate_core.domain.caselist import SourceDocument, SourceFormat, SourceOrigin
from debate_core.domain.debate_files import ParsedDocument
from debate_core.domain.style_profile import StructuralUnit
from debate_core.evidence.style_classifier import ParagraphDescription, RunDescription
from debate_core.integrations.docx_parser import DOCX_PARSER_VERSION
from debate_core.integrations.docx_parser.runs import ReadParagraph
from debate_core.testing.docx_builder import W_NAMESPACE, build_docx, paragraph_xml, run_xml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import sample_cite_shapes as script  # noqa: E402

CASELIST = "testcl26"
VERSION = "2026.10.27-docx-7"

STYLES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    f'<w:styles xmlns:w="{W_NAMESPACE}">'
    '<w:docDefaults><w:rPrDefault><w:rPr><w:b w:val="1"/><w:sz w:val="26"/></w:rPr></w:rPrDefault>'
    "</w:docDefaults>"
    '<w:style w:type="paragraph" w:styleId="Normal" w:default="1"><w:name w:val="normal"/></w:style>'
    '<w:style w:type="paragraph" w:styleId="Heading4"><w:name w:val="heading 4"/>'
    '<w:basedOn w:val="Normal"/></w:style>'
    '<w:style w:type="paragraph" w:styleId="NormalWeb"><w:name w:val="Normal (Web)"/>'
    '<w:basedOn w:val="Normal"/></w:style>'
    '<w:style w:type="paragraph" w:styleId="Analytic"><w:name w:val="Analytic"/>'
    '<w:basedOn w:val="Normal"/></w:style>'
    "</w:styles>"
)


def _off(text: str, **formatting: Any) -> str:
    return run_xml(text, bold=False, half_points=READING_SIZE, **formatting)


def _bracketed(name: str) -> str:
    return paragraph_xml(_off(f"{name} [{qualifications(450)}, {SOURCE}] KR"))


def _cut(stem: str) -> str:
    return paragraph_xml(_off(prose(400, f"{stem} "), underline="single"))


LONG_LINE = "Grid operators warn that " + "reserve margins thin every winter and " * 8 + "fall"

FILE = build_docx(
    paragraph_xml(run_xml("First tag"), style="Heading4")
    + _bracketed("Okonkwo 26")
    + _cut("Alpha")
    + paragraph_xml(run_xml("Reserve margins thin ") + _off("every winter"))
    + _bracketed("Ferreira 25")
    + _cut("Bravo")
    + paragraph_xml(run_xml(LONG_LINE) + _off(" again"))
    + _bracketed("Achebe 23")
    + _cut("Charlie")
    + paragraph_xml(run_xml("Imports cannot close the gap"))
    + _bracketed("Mensah 21")
    + _cut("Delta")
    + paragraph_xml(_off("A note left plain"))
    + _bracketed("Tanaka 22")
    + _cut("Echo")
    + paragraph_xml(run_xml("Storage fills ") + _off("the gap"), style="NormalWeb")
    + _bracketed("Lindqvist 24")
    + _cut("Foxtrot")
    + paragraph_xml(run_xml("A line ") + _off("in the middle"))
    + _cut("Golf")
    + paragraph_xml(run_xml("Last tag"), style="Heading4")
    + paragraph_xml(_off("A note under the tag"))
    + _bracketed("Ibsen 19")
    + _cut("Hotel")
    + paragraph_xml(run_xml("An analytic ") + _off("of our own"), style="Analytic")
    + _bracketed("Mensah 18")
    + _cut("India"),
    styles_xml=STYLES,
)
DIGEST = hashlib.sha256(FILE).hexdigest()

ALONE, AND_MORE = 17, 18
STRATUM_OF = {stratum.side: number for number, stratum in enumerate(script.STRATA)}
NOT_BOLD = STRATUM_OF["not bold, as Word shows it"]
THROUGH_A_STYLE = STRATUM_OF["read by an assembly rule or through a style"]


def _parsed() -> tuple[Any, ParsedDocument]:
    parser = script._ReadingParser()  # pyright: ignore[reportPrivateUsage]
    snapshot = date(2026, 11, 3)
    record = SourceDocument(
        sha256=DIGEST,
        byte_size=len(FILE),
        source_format=SourceFormat.DOCX,
        origin=SourceOrigin.CASELIST_ARCHIVE,
        caselist=CASELIST,
        first_seen_snapshot=snapshot,
        last_seen_snapshot=snapshot,
    )
    document = parser.parse(FILE, record, source_path="sample.docx")
    assert isinstance(document, ParsedDocument)
    return parser, document


def _strata() -> list[tuple[int, int]]:
    parser, document = _parsed()
    assert parser.package is not None
    shown = script._as_word_shows_them(parser.reads, parser.package)  # pyright: ignore[reportPrivateUsage]
    return script.bold_in_part_strata(parser.reads, shown, document, parser.profile)


def test_the_file_reads_as_the_table_says() -> None:
    _, document = _parsed()
    units = [section.unit for section in document.sections]
    assert units[9] is StructuralUnit.TAG, "t24's rule reads the line bold throughout as a tag"
    assert units[24] is StructuralUnit.ANALYTIC
    for at in (3, 6, 12, 15, 18, 21):
        assert units[at] in (StructuralUnit.EVIDENCE, StructuralUnit.OTHER), at
    for at in (1, 4, 7, 10, 13, 16, 22, 25):
        assert units[at] is StructuralUnit.CITE, at
    assert [card.tag for card in document.cards] == [
        "First tag",
        None,
        None,
        "Imports cannot close the gap",
        None,
        None,
        "Last tag",
        None,
    ]
    assert document.cards[7].provenance.first_element_index == document.sections[25].element_index


def test_each_left_line_is_in_the_stratum_of_its_first_failing_condition() -> None:
    """Line 15 is bold in part, but how it was read comes first: through its style's alias."""
    assert _strata() == [(ALONE, 3), (AND_MORE, 6), (NOT_BOLD, 12), (THROUGH_A_STYLE, 15)]


def test_the_plan_draws_24_and_6_and_counts_the_rest() -> None:
    planned = {
        stratum.side: stratum.planned for stratum in script.STRATA if stratum.plan == script.BOLD_IN_PART_PLAN
    }
    assert planned == {
        "bold in part, as Word shows it, nothing else the rule asks fails": 24,
        "bold in part, as Word shows it, something else fails too": 6,
        "read by an assembly rule or through a style": 0,
        "behind a style that maps to no unit": 0,
        "not bold, as Word shows it": 0,
        "over 300 characters": 0,
        "below reading size or no size stated, as Word shows it": 0,
        "names a source at its head": 0,
        "a highlighted run": 0,
        "a run in the underline or emphasis style": 0,
        "fails nothing: the cite is a guess a body may yet take": 0,
    }
    source = script._Source(
        CASELIST, DIGEST, Path("unused"), Path("unused"), VERSION, script.BOLD_IN_PART_PLAN
    )  # pyright: ignore[reportPrivateUsage]
    found = {number: [(source, position) for position in range(40)] for number in range(len(script.STRATA))}
    drawn = Counter(stratum for stratum, _, _ in script.draw(found, 5, script.BOLD_IN_PART_PLAN))
    assert drawn == {ALONE: 24, AND_MORE: 6}


def test_the_other_plans_are_unchanged() -> None:
    assert Counter(stratum.plan for stratum in script.STRATA)[script.BOLD_TAG_PLAN] == 4
    assert sum(s.planned for s in script.STRATA if s.plan == script.BOLD_TAG_PLAN) == 36
    assert sum(s.planned for s in script.STRATA if s.plan == script.FIRST_PLAN) == 70
    assert sum(s.planned for s in script.STRATA if s.plan == script.LEFT_QUOTE_PLAN) == 28


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    blob = tmp_path / "blobs" / "sha256" / DIGEST[:2] / DIGEST[2:4] / DIGEST
    blob.parent.mkdir(parents=True)
    blob.write_bytes(FILE)
    version = tmp_path / "parsed" / CASELIST / VERSION
    version.mkdir(parents=True)
    (version / "index.jsonl").write_text(json.dumps({"source_sha256": DIGEST, "outcome": "PARSED"}) + "\n")
    return tmp_path


def _run(data_dir: Path, sheet: Path, monkeypatch: pytest.MonkeyPatch) -> int:
    def no_keys(prompt: str) -> str:
        raise AssertionError("the bold-in-part plan reads no keys")

    monkeypatch.setattr(script, "read_key", no_keys)
    arguments = ["--data-dir", str(data_dir), "--caselist", CASELIST, "--plan", "bold-in-part", "--seed", "3"]
    return script.main([*arguments, "--save-tallies", str(sheet), "--workers", "1"])


def test_the_sample_is_printed_numbered_with_its_unbolded_part_marked_and_counted(
    data_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(data_dir, tmp_path / "sheet.txt", monkeypatch) == 0

    printed = capsys.readouterr().out
    assert "Item 1 of 2." in printed and "Item 2 of 2." in printed
    assert ">>> \x1b[1mReserve margins thin \x1b[0mevery winter" in printed, "bold as Word shows it"
    assert "Unbolded, between [[ ]]:  Reserve margins thin [[every winter]]" in printed
    assert "Unbolded, counted:  11 of 29 characters, 1 stretch, at the tail; letters" in printed
    assert "Unbolded, between [[ ]]:  Grid operators warn that" in printed
    assert "and fall [[again]]\n" in printed
    assert printed.rstrip().endswith("Paste nothing printed above.")


def test_a_long_line_is_marked_by_its_opening_and_its_end() -> None:
    long = "Grid " * 400
    read = ReadParagraph(
        element_index=0,
        text="AT: " + long,
        description=ParagraphDescription(
            runs=(RunDescription(text="AT: ", bold=False), RunDescription(text=long, bold=True))
        ),
        run_offsets=((0, 4), (4, 4 + len(long))),
    )
    marked = script._unbolded_marked(read)  # pyright: ignore[reportPrivateUsage]
    assert marked.startswith("[[AT:]] Grid Grid")
    assert "characters not shown" in marked
    assert len(marked) < 1_400


def test_the_tally_sheet_holds_counts_and_a_row_per_item_and_no_text(
    data_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sheet = tmp_path / "sheet.txt"
    assert _run(data_dir, sheet, monkeypatch) == 0
    printed = capsys.readouterr().out
    first = 1 if printed.index("Reserve margins thin") < printed.index("Grid operators warn") else 2

    lines = sheet.read_text().splitlines()
    assert lines[:2] == [
        "Bold-in-part sample (v1-e31-t32), seed 3: 2 items from 1 parsed sources,",
        f"parser {DOCX_PARSER_VERSION}, store {VERSION}.",
    ]
    counts = lines[lines.index("by the first condition of v1-e31-t24's rule each fails:") + 1 :][:12]
    assert counts == [
        "  read by an assembly rule or through a style: 1",
        "  behind a style that maps to no unit: 0",
        "  not bold, as Word shows it: 1",
        "  bold in part, as Word shows it, nothing else the rule asks fails: 1 (drew 1)",
        "  bold in part, as Word shows it, something else fails too: 1 (drew 1)",
        "  over 300 characters: 0",
        "  below reading size or no size stated, as Word shows it: 0",
        "  names a source at its head: 0",
        "  a highlighted run: 0",
        "  a run in the underline or emphasis style: 0",
        "  fails nothing: the cite is a guess a body may yet take: 0",
        "  All: 4",
    ]
    rows = lines[lines.index("Item | Unbolded, counted | Tag? | How it differs") + 1 :][:2]
    long_line = "5 of 286 characters, 1 stretch, at the tail; letters"  # 21 + 8 * 32 + 4 bold, "again" not
    expected = ["11 of 29 characters, 1 stretch, at the tail; letters", long_line]
    if first == 2:
        expected.reverse()
    assert rows == [f"   {n} | {counted} |  |" for n, counted in enumerate(expected, start=1)]
    assert lines[-2:] == [
        f"  bold in part, as Word shows it, nothing else the rule asks fails: {first}",
        f"  bold in part, as Word shows it, something else fails too: {3 - first}",
    ]

    written = sheet.read_text()
    for word in ("Reserve", "winter", "Grid", "Okonkwo", "First tag", "Alpha", CASELIST):
        assert word not in written, word
    assert not re.search(r"[0-9a-f]{12}", written)


def test_a_sheet_that_exists_is_never_overwritten(
    data_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sheet = tmp_path / "sheet.txt"
    sheet.write_text("the operator's answers\n")
    with pytest.raises(SystemExit, match="exists"):
        _run(data_dir, sheet, monkeypatch)
    assert sheet.read_text() == "the operator's answers\n"


def test_the_sheet_may_not_be_inside_the_repository(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(SystemExit, match="outside the repository"):
        _run(data_dir, script.REPO_ROOT / "sheet.txt", monkeypatch)

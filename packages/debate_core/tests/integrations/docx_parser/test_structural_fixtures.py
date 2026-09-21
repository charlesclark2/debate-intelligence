"""The committed structural fixtures: one file per template family, against hand-written answers.

Each `.docx` in `tests/fixtures/debate_files/structural/` stands for one of the families the
style survey measured — team Verbatim, a caselist upload that has been through CardMirror, a camp
file, an opencaselist wiki conversion, a Google Docs export, an older direct-formatted file — plus
the shapes that must not become cards. Beside each one is a `.expected.json` naming, for every
paragraph, the unit, the rule and the match source the parser should produce, and for every card
its tag, cite, completeness and element range.

**Those answers are written by hand** in `scripts/generate_structural_fixtures.py` and never
produced by running the parser, so a disagreement here is a real finding rather than a fixture
catching up with the code.

The fixtures are synthetic. Every string in them is invented, and the repository holds no real or
scrubbed debate file: see the directory's `MANIFEST.md` for why, and `v1-e31-t05-parser-eval` for
where accuracy against real files is measured instead.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from debate_core.domain.caselist import SourceDocument, SourceFormat, SourceOrigin
from debate_core.domain.debate_files import ParsedDocument
from debate_core.domain.style_profile import RunEmphasis, StyleProfile
from debate_core.integrations.docx_parser.parser import DOCX_PARSER_VERSION, DebateDocxParser
from debate_core.testing.docx_builder import build_docx, paragraph_xml, run_xml

REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
FIXTURE_DIRECTORY = REPOSITORY_ROOT / "tests" / "fixtures" / "debate_files" / "structural"

SOURCE_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
SNAPSHOT = date(2026, 9, 12)


@dataclass(frozen=True)
class Fixture:
    """One committed fixture and the answers written for it."""

    name: str
    content: bytes
    expected: dict[str, Any]

    def __str__(self) -> str:
        return self.name


def load_fixtures() -> list[Fixture]:
    paths = sorted(FIXTURE_DIRECTORY.glob("*.docx"))
    fixtures: list[Fixture] = []
    for path in paths:
        expected_path = path.with_suffix("").with_suffix(".expected.json")
        expected_path = path.parent / f"{path.stem}.expected.json"
        fixtures.append(
            Fixture(
                name=path.name,
                content=path.read_bytes(),
                expected=json.loads(expected_path.read_text(encoding="utf-8")),
            )
        )
    return fixtures


FIXTURES = load_fixtures()


def make_source(fixture: Fixture) -> SourceDocument:
    """A source document for a fixture, with the origin its corpus implies."""
    camp = fixture.expected["corpus"] == "camp"
    return SourceDocument(
        sha256=SOURCE_SHA256,
        byte_size=len(fixture.content),
        source_format=SourceFormat.DOCX,
        origin=SourceOrigin.OPENEV if camp else SourceOrigin.CASELIST_ARCHIVE,
        caselist=None if camp else "hsld26",
        first_seen_snapshot=SNAPSHOT,
        last_seen_snapshot=SNAPSHOT,
    )


@pytest.fixture(scope="session")
def parser(profile: StyleProfile) -> DebateDocxParser:
    return DebateDocxParser(profile)


def parse_fixture(parser: DebateDocxParser, fixture: Fixture) -> ParsedDocument:
    result = parser.parse(
        fixture.content,
        make_source(fixture),
        source_path=f"structural/{fixture.name}",
        camp="Northwestern" if fixture.expected["corpus"] == "camp" else None,
    )
    assert isinstance(result, ParsedDocument), result
    return result


def test_the_fixture_directory_covers_every_template_family() -> None:
    """Goal criterion ac6: eight to ten fixtures, across the families the survey measured."""
    assert 8 <= len(FIXTURES) <= 10
    families = {fixture.expected["family"] for fixture in FIXTURES}
    assert families == {"verbatim", "cardmirror", "wiki-converted", "other-heuristic", "not-a-debate-file"}
    corpora = {fixture.expected["corpus"] for fixture in FIXTURES}
    assert {"team", "caselist", "camp"} <= corpora


@pytest.mark.parametrize("fixture", FIXTURES, ids=str)
def test_the_committed_expectations_are_not_stale(fixture: Fixture) -> None:
    """A fixture whose answers name an older parser or profile has to be regenerated and re-read."""
    assert fixture.expected["parser_version"] == DOCX_PARSER_VERSION
    assert fixture.expected["profile_version"]


@pytest.mark.parametrize("fixture", FIXTURES, ids=str)
def test_every_paragraph_is_the_unit_the_fixture_says_it_is(
    parser: DebateDocxParser, fixture: Fixture
) -> None:
    document = parse_fixture(parser, fixture)
    expected = fixture.expected["paragraphs"]
    assert len(document.sections) == len(expected), (
        f"{fixture.name}: parsed {len(document.sections)} paragraphs, expected {len(expected)}"
    )
    for section, answer in zip(document.sections, expected, strict=True):
        where = f"{fixture.name} paragraph {answer['index']}"
        assert section.text == answer["text"], where
        assert section.unit.value == answer["unit"], where
        assert section.match.rule_id == answer["rule_id"], where
        assert section.match.match_source.value == answer["match_source"], where
        assert list(section.section_path) == answer["section_path"], where


@pytest.mark.parametrize("fixture", FIXTURES, ids=str)
def test_every_card_is_the_card_the_fixture_says_it_is(parser: DebateDocxParser, fixture: Fixture) -> None:
    document = parse_fixture(parser, fixture)
    expected = fixture.expected["cards"]
    assert len(document.cards) == len(expected), (
        f"{fixture.name}: parsed {len(document.cards)} cards, expected {len(expected)}"
    )
    for card, answer in zip(document.cards, expected, strict=True):
        where = f"{fixture.name} card {answer['tag'][:40]!r}"
        assert card.tag == answer["tag"], where
        assert card.short_cite == answer["short_cite"], where
        assert card.full_cite == answer["full_cite"], where
        assert card.undertag == answer["undertag"], where
        assert card.evidence_text == answer["evidence_text"], where
        assert card.completeness.value == answer["completeness"], where
        assert list(card.section_path) == answer["section_path"], where
        assert card.provenance.first_element_index == answer["first_element_index"], where
        assert card.provenance.last_element_index == answer["last_element_index"], where


@pytest.mark.parametrize("fixture", FIXTURES, ids=str)
def test_every_underline_span_selects_the_characters_the_fixture_names(
    parser: DebateDocxParser, fixture: Fixture
) -> None:
    """The offsets, checked against text written down before the parser ran."""
    document = parse_fixture(parser, fixture)
    for card, answer in zip(document.cards, fixture.expected["cards"], strict=True):
        underlined = [
            card.evidence_text[span.start_offset : span.end_offset]
            for span in card.formatting_spans
            if span.emphasis is RunEmphasis.UNDERLINE
        ]
        assert underlined == answer["underlined_text"], f"{fixture.name}: {card.tag[:40]!r}"


@pytest.mark.parametrize("fixture", FIXTURES, ids=str)
def test_the_warnings_a_fixture_expects_are_reported(parser: DebateDocxParser, fixture: Fixture) -> None:
    document = parse_fixture(parser, fixture)
    for fragment in fixture.expected["warnings_contain"]:
        assert any(fragment in warning for warning in document.warnings), fixture.name


@pytest.mark.parametrize("fixture", FIXTURES, ids=str)
def test_no_fixture_leaks_authorship_or_comment_text(parser: DebateDocxParser, fixture: Fixture) -> None:
    """`tracked-changes-and-comments.docx` carries `NEVER READ` in every part that is never opened."""
    document = parse_fixture(parser, fixture)
    dumped = document.model_dump_json()
    assert "NEVER READ" not in dumped, fixture.name


@pytest.mark.parametrize("fixture", FIXTURES, ids=str)
def test_every_card_is_unverified_and_carries_file_import_provenance(
    parser: DebateDocxParser, fixture: Fixture
) -> None:
    document = parse_fixture(parser, fixture)
    for card in document.cards:
        assert card.verification_status.value == "UNVERIFIED"
        assert card.provenance.provenance_mode.value == "FILE_IMPORT"
        assert card.provenance.source_sha256 == SOURCE_SHA256
        assert card.provenance.parser_version == DOCX_PARSER_VERSION
        assert card.provenance.profile_version == document.profile_version


@pytest.mark.parametrize("fixture", FIXTURES, ids=str)
def test_parsing_a_fixture_twice_gives_the_same_answer(parser: DebateDocxParser, fixture: Fixture) -> None:
    assert parse_fixture(parser, fixture) == parse_fixture(parser, fixture)


# --------------------------------------------------------------------------------------------
# The large file. Marked `slow`: it runs in the validate-dev slow tier, not the PR `ci` check.
# --------------------------------------------------------------------------------------------

#: Cards in the synthetic large file. At roughly 17 cards to a page this is about 300 pages, and
#: its `word/document.xml` is 5.2 MB uncompressed — the size goal criterion ac6 names.
LARGE_FILE_CARDS = 5250

#: The budget from goal criterion ac6. Generous against what the parser measures on a laptop,
#: because a CI runner is slower and a timing test that fails on a busy machine teaches nothing.
LARGE_FILE_SECONDS = 20.0


def build_large_file() -> bytes:
    """Build a 300-page debate file in memory. Not committed: a multi-megabyte binary is not a fixture.

    Every card's text carries its zone number, so the file compresses the way a real one does.
    That is not decoration: 5 MB of *identical* cards deflates to a ratio the loader refuses as a
    zip bomb, which would make this a test of the compression limit rather than of parse speed.
    """
    parts = [paragraph_xml(run_xml("AT: Reserve Margin Turn"), style="Heading3")]
    for zone in range(LARGE_FILE_CARDS):
        parts.append(
            paragraph_xml(
                run_xml(f"Data centre demand collapses the reserve margin in zone {zone}"),
                style="Heading4",
            )
            + paragraph_xml(
                run_xml(f"Okonkwo {20 + zone % 7}", character_style="Style13ptBold")
                + run_xml(f" (Journal of Grid Studies {zone}, 14 March 2026), example.invalid/grid/{zone}")
            )
            + paragraph_xml(
                run_xml(
                    f"Grid operators in zone {zone} reported that demand from new data centres rose ",
                    half_points=16,
                )
                + run_xml(
                    f"faster than any other load category in planning cycle {zone}",
                    character_style="StyleUnderline",
                    underline="single",
                    highlight="cyan",
                    half_points=22,
                )
                + run_xml(
                    ", and the increase outpaced every scenario the utility had planned against, "
                    f"leaving the reserve margin in zone {zone} thinner than at any point in the "
                    "past decade.",
                    half_points=16,
                )
            )
        )
    return build_docx("".join(parts))


@pytest.mark.slow
def test_a_three_hundred_page_file_parses_within_the_budget(parser: DebateDocxParser) -> None:
    """Goal criterion ac6's second half, measured on a file built for the occasion.

    Marked `slow`, so it runs in the validate-dev slow tier rather than in the PR `ci` check —
    building the file costs more than parsing it, and the PR budget is five minutes for
    everything.
    """
    content = build_large_file()
    source = SourceDocument(
        sha256=SOURCE_SHA256,
        byte_size=len(content),
        source_format=SourceFormat.DOCX,
        origin=SourceOrigin.CASELIST_ARCHIVE,
        caselist="hsld26",
        first_seen_snapshot=SNAPSHOT,
        last_seen_snapshot=SNAPSHOT,
    )
    started = time.monotonic()
    document = parser.parse(content, source, source_path="structural/large-synthetic-file.docx")
    elapsed = time.monotonic() - started

    assert isinstance(document, ParsedDocument)
    assert document.card_count == LARGE_FILE_CARDS
    assert elapsed < LARGE_FILE_SECONDS, f"parsed in {elapsed:.1f}s, budget {LARGE_FILE_SECONDS}s"

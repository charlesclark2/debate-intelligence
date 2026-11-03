"""Built files for the quality checks' unit tests (`v1-e33-t04`): synthetic sources, t02's real writer.

Every source is synthetic, built in memory with :mod:`debate_core.testing.docx_builder` (the
convention `v1-e31-t15` set). A test gets a file built by `v1-e33-t02`'s writer, the built file
re-parsed by the E31 parser, and each sidecar entry's source card read from its own source, which is
what the service hands the checks.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, date, datetime
from typing import Any

import pytest

from debate_core.application.ports.evidence_file_writer import BuiltEvidenceFile, FileBuildRequest
from debate_core.domain.caselist import SourceDocument, SourceFormat, SourceOrigin
from debate_core.domain.debate_files import ParsedDocument
from debate_core.domain.style_profile import StyleProfile
from debate_core.evidence.file_checks.identity import SourceCardReading
from debate_core.integrations.docx_file_writer.writer import DocxEvidenceFileWriter
from debate_core.integrations.docx_parser.parser import DebateDocxParser
from debate_core.testing.docx_builder import build_docx, paragraph_xml, run_xml
from debate_core.testing.file_builder import FileBuilderWorld, SourceCard

BUILT_AT = datetime(2026, 10, 19, 12, 30, tzinfo=UTC)

#: A built file, the built file re-parsed, and each sidecar position's source card.
Checked = tuple[BuiltEvidenceFile, ParsedDocument, dict[int, SourceCardReading]]

#: Given the sources' cards in order, the recipe's blocks: `(heading, items)`.
Layout = Callable[[Sequence[SourceCard]], Sequence[tuple[str, Sequence[Mapping[str, Any]]]]]


def tag(text: str) -> str:
    return paragraph_xml(run_xml(text), style="Heading4")


def cite(name_year: str, rest: str = ", Senior Fellow, Synthetic Energy Review, 2026") -> str:
    return paragraph_xml(run_xml(name_year, character_style="Style13ptBold") + run_xml(rest))


def body(lead: str, read: str, emphasised: str, tail: str, *, colour: str = "cyan") -> str:
    """A body: small print, an underlined highlighted stretch, an emphasised one, a direct underline."""
    return paragraph_xml(
        run_xml(lead, half_points=16)
        + run_xml(read, character_style="StyleUnderline", highlight=colour)
        + run_xml(", and ", half_points=16)
        + run_xml(emphasised, character_style="Emphasis", bold=True, highlight="green")
        + run_xml(" with ", half_points=16)
        + run_xml("a direct underline", underline="single", highlight="yellow")
        + run_xml(tail, half_points=16)
    )


SOURCE_ONE = build_docx(
    tag("Moratoria raise prices for every ratepayer")
    + cite("Lindqvist 26")
    + body("A moratorium ", "freezes new supply", "demand keeps rising", " in every market.")
    + tag("Reliability falls first in the summer peak")
    + cite("Okonkwo 25", ", Grid Analyst, Synthetic Utility Quarterly, 2025")
    + body(
        "Operators ", "shed load at the peak", "reserves run thin", " across the region.", colour="magenta"
    )
)

SOURCE_TWO = build_docx(
    tag("Data centres bring tax revenue to rural counties")
    + cite("Achterberg 26", ", Economist, Synthetic Fiscal Review, 2026")
    + body("Counties ", "collect new property tax", "schools are funded", " for a decade.")
    + tag("The cite alone, a card disclosed without its text")
    + cite("Marsh 24", ", Professor, Synthetic Law Review, 2024")
)


def standard_layout(cards: Sequence[SourceCard]) -> Sequence[tuple[str, Sequence[Mapping[str, Any]]]]:
    """Two blocks: two cards around an analytic, then a re-tagged card and a cite-only one."""
    one, two, three, four = cards
    return (
        (
            "Prices",
            (
                {"fingerprint": one.fingerprint},
                {"analytic": "The coach's own analytic between two cards."},
                {"fingerprint": two.fingerprint},
            ),
        ),
        (
            "Revenue",
            (
                {"fingerprint": three.fingerprint, "tag_override": "The coach's own tag for this card"},
                {"fingerprint": four.fingerprint},
            ),
        ),
    )


def reparse(parser: DebateDocxParser, docx: bytes, *, caselist: str = "hspolicy26") -> ParsedDocument:
    """A built (or hand-built) file re-parsed as the service re-parses it."""
    source = SourceDocument(
        sha256=hashlib.sha256(docx).hexdigest(),
        byte_size=len(docx),
        source_format=SourceFormat.DOCX,
        origin=SourceOrigin.CASELIST_ARCHIVE,
        caselist=caselist,
        first_seen_snapshot=date(2026, 10, 19),
        last_seen_snapshot=date(2026, 10, 19),
    )
    parsed = parser.parse(docx, source, source_path="built-file.docx")
    assert isinstance(parsed, ParsedDocument), parsed
    return parsed


def build_and_read(
    parser: DebateDocxParser, contents: Sequence[bytes], layout: Layout, *, disclosed: bool = True
) -> Checked:
    """Build a file from `contents` with t02's writer and read it as the checks are given it.

    With `disclosed=False` no source has a disclosure on record, the case t01's AUTO falls back to.
    """
    world = FileBuilderWorld(parser=parser)
    cards: list[SourceCard] = []
    for content in contents:
        if disclosed:
            cards.extend(asyncio.run(world.add_source(content)))
        else:
            cards.extend(asyncio.run(world.add_source(content, disclosure=None)))
    recipe = world.recipe(layout(cards))
    resolved = world.resolve(recipe, {card.fingerprint: card for card in cards})
    built = asyncio.run(
        DocxEvidenceFileWriter(snapshots=world.snapshots, parser=parser).build(
            FileBuildRequest(resolved, BUILT_AT)
        )
    )
    assert isinstance(built, BuiltEvidenceFile), built
    sources: dict[int, SourceCardReading] = {}
    for entry in built.manifest.cards:
        document = world.documents[entry.source_sha256]
        card = next(
            card
            for card in document.cards
            if card.provenance.first_element_index == entry.first_element_index
            and card.provenance.last_element_index == entry.last_element_index
        )
        sources[entry.position] = SourceCardReading(card=card)
    return built, reparse(parser, built.docx), sources


@pytest.fixture(scope="session")
def parser() -> DebateDocxParser:
    return DebateDocxParser()


@pytest.fixture(scope="session")
def profile(parser: DebateDocxParser) -> StyleProfile:
    return parser.profile


@pytest.fixture(scope="session")
def standard(parser: DebateDocxParser) -> Checked:
    """Four cards from two sources in two blocks, one re-tagged by the coach and one cite-only."""
    return build_and_read(parser, (SOURCE_ONE, SOURCE_TWO), standard_layout)


@pytest.fixture(scope="session")
def build(parser: DebateDocxParser) -> Callable[..., Checked]:
    """Build a file from synthetic source documents, laid out by a function of their cards.

    `build(contents, layout)`, or `build(contents, layout, disclosed=False)`.
    """

    def build_one(contents: Sequence[bytes], layout: Layout, *, disclosed: bool = True) -> Checked:
        return build_and_read(parser, contents, layout, disclosed=disclosed)

    return build_one


@pytest.fixture(scope="session")
def read(parser: DebateDocxParser) -> Callable[[bytes], ParsedDocument]:
    """Re-parse any `.docx` as the service re-parses a built file."""
    return lambda docx: reparse(parser, docx)


@pytest.fixture(scope="session")
def source_bytes() -> tuple[bytes, bytes]:
    """The standard file's two sources: two full cards; a full card and a cite-only one."""
    return SOURCE_ONE, SOURCE_TWO

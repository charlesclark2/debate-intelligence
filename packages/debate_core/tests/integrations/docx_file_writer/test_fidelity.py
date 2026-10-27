"""Fidelity: a built file re-parsed with the E31 parser gives every card as its source gave it (ac1).

For each card, the evidence text, the cite text and the formatting (underline, emphasis, bold,
highlight colour, font size) read from the built file are compared with the same card read from its
source. These tests re-parse the built file themselves: they do not rely on the writer's own
read-back, which they are also a check on.

The parser is the current one, `2026.10.20-docx-6`. Formatting is compared as the characters each
emphasis covers (:func:`~debate_core.domain.file_provenance.formatting_sha256`'s reading), because the
parser joins two touching spans only when the same rule found them, and the writer re-maps a source's
style aliases to the profile's ids. Font-size spans are compared exactly.

Sources are synthetic: built in memory with :mod:`debate_core.testing.docx_builder`, or the committed
E31 structural fixtures, which are synthetic too.
"""

from __future__ import annotations

import ast
import asyncio
import hashlib
import zipfile
from collections.abc import Sequence
from datetime import UTC, date, datetime
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from lxml import etree

from debate_core.application.ports.evidence_file_writer import (
    BuiltEvidenceFile,
    CardRefusalCode,
    FileBuildRefusal,
    FileBuildRequest,
)
from debate_core.domain.caselist import SourceDocument, SourceFormat, SourceOrigin
from debate_core.domain.debate_files import ParsedCard, ParsedDocument
from debate_core.domain.style_profile import RunEmphasis
from debate_core.integrations.docx_file_writer.writer import DocxEvidenceFileWriter
from debate_core.integrations.docx_parser.parser import DOCX_PARSER_VERSION, DebateDocxParser
from debate_core.testing.docx_builder import build_docx, paragraph_xml, run_xml
from debate_core.testing.file_builder import (
    DEFAULT_DISCLOSURE,
    FileBuilderWorld,
    SourceCard,
    SyntheticDisclosure,
)

REPOSITORY = Path(__file__).resolve().parents[5]
STRUCTURAL = REPOSITORY / "tests" / "fixtures" / "debate_files" / "structural"
WRITER_PACKAGE = REPOSITORY / "packages/debate_core/src/debate_core/integrations/docx_file_writer"
BUILT_AT = datetime(2026, 10, 19, 12, 30, tzinfo=UTC)

Runs = Sequence[tuple[str, dict[str, Any]]]


def paragraph(runs: Runs, style: str | None = None) -> str:
    return paragraph_xml("".join(run_xml(text, **formatting) for text, formatting in runs), style=style)


def tag(text: str) -> str:
    return paragraph([(text, {})], "Heading4")


def styled_cite(name: str, rest: str = ", Senior Fellow, Synthetic Energy Review, 3-4-2026") -> str:
    return paragraph([(name, {"character_style": "Style13ptBold"}), (rest, {})])


# ------------------------------------------------------------------------------------------------
# Reading cards
# ------------------------------------------------------------------------------------------------


def reparse(parser: DebateDocxParser, content: bytes) -> ParsedDocument:
    source = SourceDocument(
        sha256=hashlib.sha256(content).hexdigest(),
        byte_size=len(content),
        source_format=SourceFormat.DOCX,
        origin=SourceOrigin.CASELIST_ARCHIVE,
        caselist="hspolicy26",
        first_seen_snapshot=date(2026, 10, 19),
        last_seen_snapshot=date(2026, 10, 19),
    )
    parsed = parser.parse(content, source, source_path="built.docx")
    assert isinstance(parsed, ParsedDocument), parsed
    return parsed


def coverage(card: ParsedCard) -> dict[tuple[str, str | None], list[tuple[int, int]]]:
    """Which characters each emphasis (and highlight colour) covers, touching ranges joined."""
    by_emphasis: dict[tuple[str, str | None], list[tuple[int, int]]] = {}
    for span in sorted(card.formatting_spans, key=lambda span: span.start_offset):
        ranges = by_emphasis.setdefault((str(span.emphasis), span.highlight_color), [])
        if ranges and span.start_offset <= ranges[-1][1]:
            ranges[-1] = (ranges[-1][0], max(ranges[-1][1], span.end_offset))
        else:
            ranges.append((span.start_offset, span.end_offset))
    return by_emphasis


def what_ac1_compares(card: ParsedCard) -> tuple[object, ...]:
    return (
        card.evidence_text,
        card.full_cite,
        coverage(card),
        tuple((size.start_offset, size.end_offset, size.half_points) for size in card.font_size_spans),
    )


def build_all(
    parser: DebateDocxParser, *contents: bytes, disclosure: SyntheticDisclosure | None = DEFAULT_DISCLOSURE
) -> tuple[list[SourceCard], BuiltEvidenceFile | FileBuildRefusal]:
    """Every card of every source, in order, in one block of one built file."""
    world = FileBuilderWorld(parser=parser)
    cards: list[SourceCard] = []
    for content in contents:
        cards.extend(asyncio.run(world.add_source(content, disclosure=disclosure)))
    unique = list({card.fingerprint: card for card in cards}.values())
    recipe = world.recipe([("Every card", [{"fingerprint": card.fingerprint} for card in unique])])
    resolved = world.resolve(recipe, {card.fingerprint: card for card in unique})
    writer = DocxEvidenceFileWriter(snapshots=world.snapshots, parser=parser)
    return unique, asyncio.run(writer.build(FileBuildRequest(resolved, BUILT_AT)))


def assert_every_card_reads_as_its_source(
    parser: DebateDocxParser, cards: Sequence[SourceCard], result: BuiltEvidenceFile | FileBuildRefusal
) -> None:
    assert isinstance(result, BuiltEvidenceFile), result
    built = reparse(parser, result.docx).cards
    assert len(built) == len(cards)
    for source, copy in zip(cards, built, strict=True):
        assert what_ac1_compares(copy) == what_ac1_compares(source.card)


# ------------------------------------------------------------------------------------------------
# The run shapes ac1 names, in synthetic sources
# ------------------------------------------------------------------------------------------------

UNDERLINE = {"character_style": "StyleUnderline"}
SMALL = {"half_points": 16}

#: A card holding every run shape ac1 names, each in its own stretch of text.
EVERY_RUN_SHAPE = (
    tag("Moratoria raise prices for every ratepayer")
    + styled_cite("Lindqvist 26")
    + paragraph(
        [
            ("The moratorium ", SMALL),
            ("freezes supply", {**UNDERLINE, "highlight": "cyan"}),
            (" while ", SMALL),
            ("demand keeps rising", {"underline": "single", "highlight": "green"}),
            (" and ", {"half_points": 22}),
            ("prices climb", {"character_style": "Emphasis", "bold": True, "highlight": "yellow"}),
            (" in every ", {"half_points": 12}),
            ("service area", {**UNDERLINE, "underline": "single", "half_points": 26}),
            (", the board ", SMALL),
            ("concedes", {"bold": True, "highlight": "magenta"}),
            (" in its own ", SMALL),
            ("filing", {"highlight": "lightGray", "half_points": 22}),
            (".", SMALL),
        ]
    )
    + paragraph(
        [("A second paragraph of the card, ", SMALL), ("read aloud", {**UNDERLINE, "highlight": "cyan"})]
    )
)

AUTHOR = 'w:author="Coach Fictional" w:date="2026-09-01T10:00:00Z"'

#: A card with a tracked insertion, a tracked deletion and a comment in its body.
TRACKED_AND_COMMENTED = (
    tag("Reliability falls first in the summer peak")
    + styled_cite("Okonkwo 25")
    + (
        '<w:p><w:commentRangeStart w:id="3"/>'
        '<w:r><w:rPr><w:sz w:val="16"/></w:rPr><w:t xml:space="preserve">Operators </w:t></w:r>'
        f'<w:ins w:id="1" {AUTHOR}><w:r><w:rPr><w:rStyle w:val="StyleUnderline"/>'
        '<w:highlight w:val="cyan"/></w:rPr><w:t>shed load</w:t></w:r></w:ins>'
        f'<w:del w:id="2" {AUTHOR}><w:r>'
        '<w:delText xml:space="preserve"> hold steady</w:delText></w:r></w:del>'
        '<w:r><w:rPr><w:sz w:val="16"/></w:rPr><w:t xml:space="preserve"> when reserves run thin.</w:t></w:r>'
        '<w:commentRangeEnd w:id="3"/>'
        '<w:r><w:rPr><w:rStyle w:val="CommentReference"/></w:rPr><w:commentReference w:id="3"/></w:r>'
        "</w:p>"
    )
)

#: A card whose evidence holds U+0001 and U+FFFE raw, as CardMirror's exporter has written them.
FORBIDDEN_CHARACTERS = (
    tag("Data centres bring tax revenue")
    + styled_cite("Achterberg 26")
    + (
        '<w:p><w:r><w:rPr><w:rStyle w:val="StyleUnderline"/><w:highlight w:val="cyan"/></w:rPr>'
        '<w:t xml:space="preserve">Revenue\x01 grows￾ with every site.</w:t></w:r></w:p>'
    )
)


def test_the_synthetic_sources_hold_every_shape_ac1_names(parser: DebateDocxParser) -> None:
    """The fixture is what it claims: otherwise the fidelity test below proves less than it says."""
    world = FileBuilderWorld(parser=parser)
    (every,) = asyncio.run(world.add_source(build_docx(EVERY_RUN_SHAPE)))
    emphases = {span.emphasis for span in every.card.formatting_spans}
    assert {RunEmphasis.UNDERLINE, RunEmphasis.EMPHASIS, RunEmphasis.BOLD, RunEmphasis.HIGHLIGHT} <= emphases
    colours = {span.highlight_color for span in every.card.formatting_spans if span.highlight_color}
    assert colours == {"cyan", "green", "yellow", "magenta", "lightGray"}
    assert {size.half_points for size in every.card.font_size_spans} == {12, 16, 22, 26}

    tracked = build_docx(TRACKED_AND_COMMENTED)
    asyncio.run(world.add_source(tracked))
    warnings = world.documents[hashlib.sha256(tracked).hexdigest()].warnings
    assert any("tracked deletion" in warning for warning in warnings)
    with zipfile.ZipFile(BytesIO(tracked)) as archive:
        document = archive.read("word/document.xml")
    assert b"<w:ins " in document and b"<w:commentReference " in document


def test_every_run_shape_reads_back_as_its_source(parser: DebateDocxParser) -> None:
    cards, result = build_all(
        parser,
        build_docx(EVERY_RUN_SHAPE),
        build_docx(TRACKED_AND_COMMENTED),
        build_docx(FORBIDDEN_CHARACTERS),
    )
    assert len(cards) == 3
    assert_every_card_reads_as_its_source(parser, cards, result)


def test_a_forbidden_character_reads_back_as_the_replacement_character_the_parser_gave(
    parser: DebateDocxParser,
) -> None:
    _, result = build_all(parser, build_docx(FORBIDDEN_CHARACTERS))
    assert isinstance(result, BuiltEvidenceFile)
    assert reparse(parser, result.docx).cards[0].evidence_text == "Revenue� grows� with every site."
    assert result.manifest.cards[0].forbidden_characters_replaced == 2


def test_the_tracked_change_and_the_comment_are_resolved_the_parsers_way(parser: DebateDocxParser) -> None:
    _, result = build_all(parser, build_docx(TRACKED_AND_COMMENTED))
    assert isinstance(result, BuiltEvidenceFile)
    card = reparse(parser, result.docx).cards[0]
    assert card.evidence_text == "Operators shed load when reserves run thin."
    with zipfile.ZipFile(BytesIO(result.docx)) as archive:
        document = archive.read("word/document.xml")
    for absent in (b"Coach Fictional", b"w:ins", b"w:del", b"comment", b"hold steady"):
        assert absent not in document, absent


def test_the_parser_ac1_is_measured_with_is_the_current_one(parser: DebateDocxParser) -> None:
    assert parser.parser_version == DOCX_PARSER_VERSION == "2026.10.20-docx-6"


# ------------------------------------------------------------------------------------------------
# The committed E31 structural fixtures
# ------------------------------------------------------------------------------------------------

STRUCTURAL_WITH_CARDS = [
    "analytics-and-undertags.docx",
    "cardmirror-camp-file.docx",
    "cardmirror-caselist-upload.docx",
    "non-verbatim-caselist-upload.docx",
    "pre-2026-direct-formatting.docx",
    "team-verbatim-file.docx",
    "tracked-changes-and-comments.docx",
    "wiki-converted-cite-entries.docx",
]


def test_every_structural_fixture_with_cards_is_listed(parser: DebateDocxParser) -> None:
    with_cards = sorted(
        path.name
        for path in STRUCTURAL.glob("*.docx")
        if asyncio.run(FileBuilderWorld(parser=parser).add_source(path.read_bytes()))
    )
    assert with_cards == STRUCTURAL_WITH_CARDS


@pytest.mark.parametrize("name", STRUCTURAL_WITH_CARDS)
def test_a_file_built_from_a_structural_fixture_reads_back_as_the_fixture(
    parser: DebateDocxParser, name: str
) -> None:
    cards, result = build_all(parser, (STRUCTURAL / name).read_bytes())
    assert_every_card_reads_as_its_source(parser, cards, result)


def test_one_file_built_from_every_structural_fixture_reads_back_as_them(parser: DebateDocxParser) -> None:
    contents = [(STRUCTURAL / name).read_bytes() for name in STRUCTURAL_WITH_CARDS]
    cards, result = build_all(parser, *contents)
    assert len(cards) == 5, "ten cards, five distinct bodies: the fixtures share their cards' text"
    assert_every_card_reads_as_its_source(parser, cards, result)


# ------------------------------------------------------------------------------------------------
# Every cite shape, and no provenance line in any (PM amendment 2026-10-19; `v1-e33-t08`)
# ------------------------------------------------------------------------------------------------

PROSE = (
    "The reserve margin in every regional market fell below the planning target this year, and "
    "operators warned that new data centre load would push it lower still unless capacity is built. "
) * 2
BODY = paragraph(
    [
        (PROSE[:60], SMALL),
        (PROSE[60:140], {"underline": "single", "highlight": "cyan", "half_points": 16}),
        (PROSE[140:], SMALL),
    ]
)
TAIL = ", professor of energy policy, Invented Institute of Grid Studies, Invented Review of Grids, 3-4-2026"
TAG = tag("Data centre demand collapses the reserve margin")

#: Each shape, its source, and a rule id the parser must have used for the source's card, so that
#: the shape is the shape its name says.
CITE_SHAPES: dict[str, tuple[str, str]] = {
    "a Verbatim card": (TAG + styled_cite("Okonkwo 26", TAIL) + BODY, "verbatim-cite-run-style"),
    "a cite line with no cite style": (
        TAG
        + paragraph([("Okonkwo 26", {"bold": True, "half_points": 26}), (TAIL, {"half_points": 22})])
        + BODY,
        "heuristic-cite-line-author-year",
    ),
    "a cite behind a first name": (
        TAG + paragraph([("Adaeze ", {}), ("Okonkwo 26", {"bold": True}), (TAIL, {})]) + BODY,
        "assembly-cite-behind-a-name-before-the-body",
    ),
    "a cite wholly in brackets": (
        TAG + paragraph([("[Okonkwo 26" + TAIL + "] KR", {})]) + BODY,
        "assembly-bracketed-cite-before-the-body",
    ),
    "a two-line cite": (
        TAG + styled_cite("Okonkwo 26", TAIL) + styled_cite("Lindqvist 25", TAIL) + BODY,
        "verbatim-cite-run-style",
    ),
    "a card with no tag": (styled_cite("Okonkwo 26", TAIL) + BODY, "verbatim-cite-run-style"),
    "a card with no cite": (TAG + BODY, "heuristic-marked-up-body-text"),
    "a cite-only card": (TAG + styled_cite("Okonkwo 26", TAIL), "verbatim-cite-run-style"),
    "an undertag above the cite": (
        TAG
        + paragraph([("Read with the uniqueness card", {})], "Undertag")
        + styled_cite("Okonkwo 26", TAIL)
        + BODY,
        "verbatim-style-id:Undertag",
    ),
    "a cite guess the body took": (
        TAG
        + styled_cite("Okonkwo 26", TAIL)
        + paragraph([("Okonkwo 26 … the reserve margin fell below target … new capacity is needed", SMALL)])
        + BODY,
        "assembly-cite-guess-after-card-cite",
    ),
}


def _source_card(parser: DebateDocxParser, content: bytes) -> ParsedCard:
    world = FileBuilderWorld(parser=parser)
    (card, *_) = asyncio.run(world.add_source(content))
    return card.card


@pytest.mark.parametrize("shape", CITE_SHAPES, ids=list(CITE_SHAPES))
def test_every_cite_shape_reads_back_as_its_source_with_no_provenance_line(
    parser: DebateDocxParser, shape: str
) -> None:
    markup, rule = CITE_SHAPES[shape]
    content = build_docx(markup)
    source = _source_card(parser, content)
    assert any(rule_id.startswith(rule) for rule_id in source.rule_ids), source.rule_ids
    cards, result = build_all(parser, content)
    assert_every_card_reads_as_its_source(parser, cards, result)
    assert isinstance(result, BuiltEvidenceFile)
    read = reparse(parser, result.docx)
    assert read.cards[0].undertag == source.undertag, "the card's undertag is its own, with no line"
    line = result.manifest.cards[0].provenance_line
    assert not any(line in section.text or "[Disclosed: " in section.text for section in read.sections)


HIGHLIGHTED_CITE = paragraph(
    [
        ("Okonkwo 26", {"bold": True, "highlight": "yellow"}),
        (", " + ("professor of energy policy at the Invented Institute of Grid Studies, " * 8)[:580], {}),
    ]
)
UNDERTAG_LINE = paragraph([("[Disclosed: hspolicy26 2026-09-15]", {})], "Undertag")


def parser_steps_over_an_undertag(parser: DebateDocxParser) -> bool:
    """Whether the parser reads a highlighted cite as a cite with an Undertag line before its body.

    False at `2026.10.18-docx-5`; `v1-e31-t24` made it True (PM ruling, 2026-10-19).
    """
    card = _source_card(parser, build_docx(TAG + HIGHLIGHTED_CITE + UNDERTAG_LINE + BODY))
    return card.full_cite.startswith("Okonkwo 26")


def test_a_highlighted_cite_builds_and_reads_back_with_its_body_below_it(parser: DebateDocxParser) -> None:
    """The one shape the provenance line changed, until `v1-e31-t24`.

    The parser read a highlighted cite as a cite only when its body was directly below it, and the
    line stood between them, so the read-back refused the card. `v1-e31-t24` let the parser step over
    an Undertag line; since `v1-e33-t08` a built file writes no line, so the body is below the cite
    again, as in the source.
    """
    content = build_docx(TAG + HIGHLIGHTED_CITE + BODY)
    source = _source_card(parser, content)
    assert any(rule_id.startswith("assembly-highlighted-cite-before-the-body") for rule_id in source.rule_ids)
    cards, result = build_all(parser, content)
    assert_every_card_reads_as_its_source(parser, cards, result)
    assert isinstance(result, BuiltEvidenceFile)
    built = reparse(parser, result.docx).cards[0]
    assert built.full_cite == source.full_cite
    assert built.undertag == source.undertag == ""


def test_the_parser_steps_over_the_line(parser: DebateDocxParser) -> None:
    """The state the test above rests on, turned over by `v1-e31-t24`."""
    assert parser_steps_over_an_undertag(parser) is True


def test_a_tagless_card_after_a_cite_only_card_is_refused_on_read_back(parser: DebateDocxParser) -> None:
    """A tagless card after a cite-only card merges into it, so the file does not read back."""
    first = build_docx(TAG + styled_cite("Marsh 24", TAIL))
    second = build_docx(styled_cite("Okonkwo 26", TAIL) + BODY)
    _, result = build_all(parser, first, second)
    assert isinstance(result, FileBuildRefusal)
    for refusal in result.refusals:
        assert refusal.code is CardRefusalCode.READBACK_MISMATCH


# ------------------------------------------------------------------------------------------------
# Boundaries
# ------------------------------------------------------------------------------------------------


def test_the_writer_never_imports_the_e06_docx_renderer() -> None:
    """The task's forbidden list. Checked by reading the imports, since the renderer is not written yet."""
    imported: set[str] = set()
    for path in WRITER_PACKAGE.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
            elif isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
    assert imported, "the scan found the writer's modules"
    assert not {module for module in imported if "docx_renderer" in module}


def test_the_writer_calls_no_model() -> None:
    for path in WRITER_PACKAGE.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for word in ("ModelRouter", "model_router", "generate_structured", "bedrock"):
            assert word not in text, (path.name, word)


def test_a_stretch_underlined_by_an_alias_beside_the_profiles_own_style_reads_back(
    parser: DebateDocxParser,
) -> None:
    """The source reads two underline spans (two rules); the writer re-maps the alias and the built
    file reads one. The characters underlined are the same, which is what ac1 compares."""
    content = build_docx(
        tag("Moratoria raise prices")
        + styled_cite("Lindqvist 26")
        + paragraph(
            [
                ("Supply ", SMALL),
                ("freezes", {"character_style": "Underline", **SMALL}),
                (" in place", {**UNDERLINE, **SMALL}),
                (" this year.", SMALL),
            ]
        )
    )
    cards, result = build_all(parser, content)
    underlines = [span for span in cards[0].card.formatting_spans if span.emphasis is RunEmphasis.UNDERLINE]
    assert len(underlines) == 2, "the source reads the alias and the style as two spans"
    assert_every_card_reads_as_its_source(parser, cards, result)
    assert isinstance(result, BuiltEvidenceFile)
    rebuilt = [
        s
        for s in reparse(parser, result.docx).cards[0].formatting_spans
        if s.emphasis is RunEmphasis.UNDERLINE
    ]
    assert len(rebuilt) == 1


WORDML = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def runs_of_the_paragraph(docx: bytes, text: str) -> list[tuple[str, bytes]]:
    """Each run of the one body paragraph whose text is `text`: its text and its properties as XML."""
    body = etree.fromstring(zipfile.ZipFile(BytesIO(docx)).read("word/document.xml"))
    found = [
        element
        for element in body.iter(f"{WORDML}p")
        if "".join(t.text or "" for t in element.iter(f"{WORDML}t")) == text
    ]
    assert len(found) == 1, len(found)
    return [
        (
            "".join(t.text or "" for t in run.iter(f"{WORDML}t")),
            b""
            if run.find(f"{WORDML}rPr") is None
            else etree.tostring(run.find(f"{WORDML}rPr"), method="c14n"),
        )
        for run in found[0].iter(f"{WORDML}r")
    ]


def test_a_white_highlighted_paragraph_is_copied_as_its_source_wrote_it(parser: DebateDocxParser) -> None:
    """`v1-e31-t31`: the parser no longer reads white as highlight; the writer still copies it.

    The writer copies a card's paragraphs from its source (`v1-e33-t02`), so the white run reaches the
    built file with its `w:highlight` as the source wrote it, and the card reads back as its source.
    """
    runs = [
        ("Supply ", SMALL),
        ("freezes in place", {"underline": "single", "highlight": "cyan", **SMALL}),
        (" while the grid waits", {"highlight": "white", **SMALL}),
        (" this year.", SMALL),
    ]
    text = "".join(run_text for run_text, _ in runs)
    content = build_docx(tag("Moratoria raise prices") + styled_cite("Lindqvist 26") + paragraph(runs))
    source = _source_card(parser, content)
    assert [
        span.highlight_color for span in source.formatting_spans if span.emphasis is RunEmphasis.HIGHLIGHT
    ] == ["cyan"]

    cards, result = build_all(parser, content)

    assert_every_card_reads_as_its_source(parser, cards, result)
    assert isinstance(result, BuiltEvidenceFile)
    copied = runs_of_the_paragraph(result.docx, text)
    assert copied == runs_of_the_paragraph(content, text)
    assert any(b'w:val="white"' in properties for _, properties in copied)

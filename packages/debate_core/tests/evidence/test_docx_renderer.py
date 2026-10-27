"""Tests for `debate_core.evidence.docx_renderer`: cut cards into a Verbatim .docx (`v1-e06-t04`).

Every check reads the rendered bytes back with python-docx, independently of the renderer: the
paragraphs in order with their style ids, and each run's text, character style, highlight, size and
colour. What the renderer adds to a card's evidence (the omission marker, a bracketed interpolation)
is taken out by :func:`evidence_read_back`, which finds each addition where the *card* says it goes,
by its own arithmetic, so what is left must be `Card.evidence_text` character for character.

Two kinds of card are rendered:

* t02's news-article card, cut by `CardService` in `tests/fixtures/card/card_world.py` from t04's
  synthetic page with the committed fake-router answers: VERIFIED, quoting [212, 712) less the
  omission [320, 422), with five spans. Its expected runs below are written by hand from t04's
  paragraphs and t02's `NEWS_SPANS`; its cite is t01's hand-written expected cite for the page.
* Cards built here by hand, for what the world card lacks: interpolations, Unicode beyond curly
  quotes, a tab and line breaks, overlapping spans across a cut, and UNVERIFIED cards.

Names say which plan node a test belongs to (`-k structure`, `-k unverified`, `-k manifest`).
"""

from __future__ import annotations

import hashlib
import io
import re
import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Final
from xml.etree import ElementTree

import docx
import pytest
from docx.opc.packuri import PackURI
from docx.opc.part import Part
from docx.text.paragraph import Paragraph
from tests.fixtures.card.card_world import CardWorld, news_request
from tests.fixtures.verification.verification_world import run

from debate_core.application.export_service import ExportService
from debate_core.domain import (
    Card,
    CardOmission,
    CardSpan,
    CitationField,
    CitationFieldSource,
    Interpolation,
    SpanStyle,
    VerificationStatus,
)
from debate_core.domain.caselist import SourceDocument, SourceFormat, SourceOrigin
from debate_core.domain.debate_files import ParsedDocument
from debate_core.evidence.card_rendering import CardToRender, CiteText, DocumentHeadings, RenderRefused
from debate_core.evidence.docx_manifest_part import (
    EmbeddedManifestError,
    read_embedded_manifest,
    read_embedded_manifest_bytes,
)
from debate_core.evidence.docx_renderer import render_cards_docx
from debate_core.evidence.format_profile import (
    FORMAT_PROFILES_DIRECTORY,
    ResolvedFormatProfile,
    load_format_profile,
    load_format_profile_from_text,
    resolve_format_profile,
)
from debate_core.evidence.manifest import (
    MANIFEST_VERSION,
    CardManifest,
    SnapshotReference,
    serialize_manifest,
)
from debate_core.integrations.docx_file_writer.base_template import render_styles_xml
from debate_core.integrations.docx_parser.parser import DebateDocxParser
from debate_core.testing.builders import DEFAULT_CITATION, build_card, build_source_snapshot
from debate_core.testing.fakes.clock_and_ids import FixedClock

REPOSITORY: Final = Path(__file__).resolve().parents[4]
PROFILES: Final = REPOSITORY / FORMAT_PROFILES_DIRECTORY
TEAM_DEFAULT: Final = load_format_profile("team-default", PROFILES)
PLAIN: Final = load_format_profile("plain", PROFILES)
GENERATED_AT: Final = datetime(2026, 10, 27, 9, 30, tzinfo=UTC)
W: Final = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

MARKER: Final = " … "
"""The committed profiles' omission marker, written here by hand."""

NEWS_CITE: Final = CiteText(
    short_cite="Whitfield 26",
    full_cite=(
        'Whitfield 26 [Dana Whitfield; "Scientists Say Mammoth Revival Is Years Away"; The Daily Meridian; '
        "September 14, 2026; "
        "https://www.dailymeridian.example/science/2026/09/14/mammoth-revival-years-away; "
        "accessed October 26, 2026]"
    ),
)
"""t01's hand-written expected cite for the news-article page (`tests/fixtures/citation`)."""


# --------------------------------------------------------------------------------------------
# Reading a rendered file back, independently of the renderer
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ReadRun:
    text: str
    character_style: str | None
    highlight: str | None
    half_points: int | None
    color: str | None = None


@dataclass(frozen=True)
class ReadParagraph:
    style_id: str
    runs: tuple[ReadRun, ...]

    @property
    def text(self) -> str:
        return "".join(r.text for r in self.runs)


def read_run(paragraph: Paragraph) -> tuple[ReadRun, ...]:
    runs: list[ReadRun] = []
    for each in paragraph.runs:
        properties = each.element.rPr
        style = properties.rStyle.val if properties is not None and properties.rStyle is not None else None
        highlight = each.font.highlight_color
        size = each.font.size
        rgb = each.font.color.rgb if each.font.color.type is not None else None
        runs.append(
            ReadRun(
                text=each.text,
                character_style=style,
                highlight=highlight.xml_value if highlight is not None else None,
                half_points=round(size.pt * 2) if size is not None else None,
                color=str(rgb) if rgb is not None else None,
            )
        )
    return tuple(runs)


def read_paragraphs(data: bytes) -> list[ReadParagraph]:
    document = docx.Document(io.BytesIO(data))
    paragraphs: list[ReadParagraph] = []
    for paragraph in document.paragraphs:
        style = paragraph.style
        assert style is not None
        paragraphs.append(ReadParagraph(style_id=style.style_id, runs=read_run(paragraph)))
    return paragraphs


def evidence_read_back(
    paragraph: ReadParagraph, card: Card, marker: str = MARKER
) -> tuple[str, list[ReadRun]]:
    """The paragraph's evidence, with each renderer addition taken out where the card says it goes.

    An omission goes where the kept snapshot text before it ends; an interpolation before the
    character at its anchor, after any cut at the same place. Each must be a run of its own whose
    text is exactly the marker or the bracketed interpolation, or it is read as evidence.
    """
    additions: list[tuple[int, str]] = []
    kept, previous_end = 0, card.evidence_start_offset or 0
    for omission in card.omitted_ranges:
        kept += omission.start_offset - previous_end
        additions.append((kept, marker))
        previous_end = omission.end_offset
    additions.extend((i.anchor, f"[{i.text}]") for i in card.interpolations)
    additions.sort(key=lambda addition: (addition[0], addition[1] != marker))
    text, evidence_runs = "", list[ReadRun]()
    for each in paragraph.runs:
        if additions and additions[0] == (len(text), each.text):
            additions.pop(0)
            continue
        text += each.text
        evidence_runs.append(each)
    assert not additions, f"the renderer's additions were not found where they belong: {additions}"
    return text, evidence_runs


def marks_per_character(runs: list[ReadRun]) -> list[tuple[bool, bool]]:
    """(underlined, highlighted) for every evidence character, from the runs that carry it."""
    marks: list[tuple[bool, bool]] = []
    for each in runs:
        marks.extend(
            [(each.character_style == "StyleUnderline", each.highlight is not None)] * len(each.text)
        )
    return marks


def marks_from_spans(card: Card) -> list[tuple[bool, bool]]:
    """The oracle: a character is underlined (highlighted) when an underline (highlight) span covers it."""

    def covered(offset: int, style: SpanStyle) -> bool:
        return any(s.style is style and s.start_offset <= offset < s.end_offset for s in card.spans)

    return [
        (covered(i, SpanStyle.UNDERLINE), covered(i, SpanStyle.HIGHLIGHT))
        for i in range(len(card.evidence_text))
    ]


def styles_part(data: bytes) -> ElementTree.Element:
    with zipfile.ZipFile(io.BytesIO(data)) as package:
        return ElementTree.fromstring(package.read("word/styles.xml"))


# --------------------------------------------------------------------------------------------
# Cards, manifests and rendering
# --------------------------------------------------------------------------------------------


def manifest_of(*cards: Card) -> CardManifest:
    snapshots = {
        card.snapshot_id: SnapshotReference.of(build_source_snapshot(snapshot_id=card.snapshot_id))
        for card in cards
        if card.snapshot_id is not None
    }
    return CardManifest(
        manifest_version=MANIFEST_VERSION,
        generated_at=GENERATED_AT,
        cards=cards,
        snapshots=tuple(snapshots[key] for key in sorted(snapshots)),
    )


HAND_CITE: Final = CiteText(
    short_cite="Rivera et al. 23",
    full_cite='Rivera et al. 23 [Rivera, J. and Okonkwo, A.; "Arctic methane release is accelerating"]',
)


def render(
    *cards: CardToRender,
    profile: ResolvedFormatProfile = TEAM_DEFAULT,
    headings: DocumentHeadings | None = None,
) -> bytes:
    return render_cards_docx(
        manifest_of(*(c.card for c in cards)), cards, profile, headings=headings or DocumentHeadings()
    )


FULLY_VERIFIED_CITATION: Final = DEFAULT_CITATION.evolve(
    accessed_at=DEFAULT_CITATION.accessed_at.evolve(source=CitationFieldSource.RETRIEVAL, verified=True)
)
"""The builder's cite with its accessed date verified too, so a hand-built card's cite has no mark."""


def hand_card(**changes: Any) -> Card:
    changes.setdefault("citation", FULLY_VERIFIED_CITATION)
    return build_card(**changes)


def verified(card: Card) -> Card:
    return card.evolve(verification_status=VerificationStatus.VERIFIED)


@pytest.fixture(scope="module")
def news() -> tuple[Card, CardManifest]:
    """t02's VERIFIED news-article card and the manifest ExportService writes for it."""
    world = CardWorld()
    snapshot_id = run(world.add_page()).snapshot.snapshot_id
    card = run(world.card_service.cut_card(news_request(snapshot_id))).card
    assert card.verification_status is VerificationStatus.VERIFIED
    manifest = run(ExportService(articles=world.articles, clock=FixedClock(GENERATED_AT)).manifest([card]))
    return card, manifest


#: The news card's evidence paragraph, written by hand from t04's paragraphs and t02's NEWS_SPANS:
#: (text, underlined, highlighted, half-points). Read text is 22 half-points, the rest 16, and the
#: cut at evidence offset 108 (snapshot [320, 422)) is the profile's marker at the base size.
NEWS_EVIDENCE_RUNS: Final = [
    ("The delay follows two years of ", False, False, 16),
    ("failed attempts", True, True, 22),
    (" to grow edited elephant embryos to term", True, False, 22),
    (" in surrogate animals.", False, False, 16),
    (MARKER, False, False, 22),
    ("Conservation biologists who have criticized the project said ", False, False, 16),
    ("the timeline was never realistic", True, False, 22),
    (". “Every year this slips, ", False, False, 16),
    ("the money raised for it is ", True, False, 22),
    ("money that did not go to elephants that are alive now", True, True, 22),
    (
        ",” said Priya Ramaswamy, who studies elephant populations and was not involved in the work.",
        False,
        False,
        16,
    ),
]


def as_tuples(runs: tuple[ReadRun, ...] | list[ReadRun]) -> list[tuple[str, bool, bool, int | None]]:
    return [
        (r.text, r.character_style == "StyleUnderline", r.highlight is not None, r.half_points) for r in runs
    ]


# --------------------------------------------------------------------------------------------
# Node document-structure: headings, tag, cite and evidence
# --------------------------------------------------------------------------------------------


def test_structure_a_verified_card_is_its_tag_its_cite_and_its_evidence_in_that_order(
    news: tuple[Card, CardManifest],
) -> None:
    card, manifest = news

    paragraphs = read_paragraphs(render_cards_docx(manifest, [CardToRender(card, NEWS_CITE)], TEAM_DEFAULT))

    assert [(p.style_id, p.text) for p in paragraphs[:2]] == [
        ("Heading4", "Each delay in reviving the mammoth costs living elephants funding"),
        ("Normal", NEWS_CITE.full_cite),
    ]
    assert paragraphs[2].style_id == "Normal"
    assert len(paragraphs) == 3


def test_structure_the_evidence_runs_are_the_card_spans_condensed_where_nothing_is_read(
    news: tuple[Card, CardManifest],
) -> None:
    card, manifest = news

    evidence = read_paragraphs(render_cards_docx(manifest, [CardToRender(card, NEWS_CITE)], TEAM_DEFAULT))[2]

    assert as_tuples(evidence.runs) == NEWS_EVIDENCE_RUNS
    assert {r.highlight for r in evidence.runs} == {None, "cyan"}


def test_structure_the_evidence_reads_back_as_exactly_the_cards_evidence_text(
    news: tuple[Card, CardManifest],
) -> None:
    card, _ = news
    card = card.evolve(
        interpolations=(Interpolation(anchor=108, text="critics"), Interpolation(anchor=398, text="sic"))
    )

    evidence = read_paragraphs(render(CardToRender(card, NEWS_CITE)))[2]
    text, runs = evidence_read_back(evidence, card)

    assert text == card.evidence_text
    assert marks_per_character(runs) == marks_from_spans(card)
    assert evidence.text.count(MARKER) == 1
    assert [r.text for r in evidence.runs].index("[critics]") == [r.text for r in evidence.runs].index(
        MARKER
    ) + 1
    assert evidence.runs[-1].text == "[sic]"


#: A hand-built card for what the news card lacks. Evidence offsets, written out:
#:   0-5 "Ærø’s" · 5 " " · 6-12 "“café”" · 12-15 " — " · 15-20 "naïve" · 20 " " · 21 "🐘" · 22-24 "\n\n"
#:   24-28 "Herd" · 28 "\t" · 29-34 "counts" · 35 "." ; then, after a cut at 36, "Ice" at 36-39 and " melts"
#:   at 39-45. The underline is 6-40, so it ends after the space; the highlights are 15-22 and 33-39.
UNICODE_EVIDENCE: Final = "Ærø’s “café” — naïve 🐘\n\nHerd\tcounts.Ice melts"


def unicode_card() -> Card:
    assert len(UNICODE_EVIDENCE) == 45
    return hand_card(
        evidence_text=UNICODE_EVIDENCE,
        evidence_start_offset=500,
        evidence_end_offset=560,
        omitted_ranges=(CardOmission(start_offset=536, end_offset=551),),
        spans=(
            CardSpan(start_offset=6, end_offset=40, style=SpanStyle.UNDERLINE),
            CardSpan(start_offset=15, end_offset=22, style=SpanStyle.HIGHLIGHT),
            CardSpan(start_offset=33, end_offset=39, style=SpanStyle.HIGHLIGHT),
        ),
    ).evolve(
        interpolations=(
            Interpolation(anchor=0, text="the island"),
            Interpolation(anchor=36, text="and"),
            Interpolation(anchor=45, text="emphasis added"),
        )
    )


def test_structure_unicode_tabs_breaks_overlaps_cuts_and_interpolations_read_back_exactly() -> None:
    card = verified(unicode_card())

    evidence = read_paragraphs(render(CardToRender(card, HAND_CITE)))[-1]
    text, runs = evidence_read_back(evidence, card)

    assert text == UNICODE_EVIDENCE
    assert marks_per_character(runs) == marks_from_spans(card)
    assert [r.text for r in evidence.runs] == [
        "[the island]",
        "Ærø’s ",
        "“café” — ",
        "naïve 🐘",
        "\n\nHerd\tcoun",
        "ts.",
        MARKER,
        "[and]",
        "Ice",
        " ",
        "melts",
        "[emphasis added]",
    ]


def test_structure_headings_are_written_once_above_the_cards_in_pocket_hat_block_order() -> None:
    first = verified(hand_card(card_id="0CARD000000000000000000001"))
    second = verified(hand_card(card_id="0CARD000000000000000000002", tag="A second tag"))

    paragraphs = read_paragraphs(
        render(
            CardToRender(first, HAND_CITE),
            CardToRender(second, HAND_CITE),
            headings=DocumentHeadings(pocket="Aff", hat="Methane advantage", block="Feedbacks"),
        )
    )

    assert [(p.style_id, p.text) for p in paragraphs if p.style_id.startswith("Heading")] == [
        ("Heading1", "Aff"),
        ("Heading2", "Methane advantage"),
        ("Heading3", "Feedbacks"),
        ("Heading4", "Arctic methane feedback is already measurable"),
        ("Heading4", "A second tag"),
    ]
    assert len(paragraphs) == 3 + 2 * 3


def test_structure_headings_left_out_are_not_written() -> None:
    paragraphs = read_paragraphs(
        render(CardToRender(verified(hand_card()), HAND_CITE), headings=DocumentHeadings(hat="Only a hat"))
    )

    assert [p.style_id for p in paragraphs] == ["Heading2", "Heading4", "Normal", "Normal"]


@pytest.mark.parametrize(
    ("style_id", "name", "outline_level"),
    [
        ("Heading1", "heading 1", "0"),
        ("Heading2", "heading 2", "1"),
        ("Heading3", "heading 3", "2"),
        ("Heading4", "heading 4", "3"),
    ],
)
def test_structure_heading_styles_carry_the_style_profiles_names_and_outline_levels(
    style_id: str, name: str, outline_level: str
) -> None:
    data = render(
        CardToRender(verified(hand_card()), HAND_CITE),
        headings=DocumentHeadings(pocket="Pocket", hat="Hat", block="Block"),
    )

    [style] = [s for s in styles_part(data).iter(f"{W}style") if s.get(f"{W}styleId") == style_id]
    name_element = style.find(f"{W}name")
    level = style.find(f"{W}pPr/{W}outlineLvl")
    assert name_element is not None and name_element.get(f"{W}val") == name
    assert level is not None and level.get(f"{W}val") == outline_level


def test_structure_the_style_table_is_the_one_the_lossless_writer_generates_from_the_style_profile() -> None:
    data = render(CardToRender(verified(hand_card()), HAND_CITE))

    with zipfile.ZipFile(io.BytesIO(data)) as package:
        rendered = package.read("word/styles.xml")
    expected = render_styles_xml(TEAM_DEFAULT.style_profile)
    assert ElementTree.canonicalize(rendered) == ElementTree.canonicalize(expected)


def test_structure_the_short_cite_carries_the_cite_style_and_the_rest_the_full_cite_size(
    news: tuple[Card, CardManifest],
) -> None:
    card, manifest = news

    cite = read_paragraphs(render_cards_docx(manifest, [CardToRender(card, NEWS_CITE)], TEAM_DEFAULT))[1]

    assert [(r.text, r.character_style, r.half_points) for r in cite.runs] == [
        ("Whitfield 26", "Style13ptBold", None),
        (NEWS_CITE.full_cite.removeprefix("Whitfield 26"), None, 22),
    ]


def test_structure_a_profile_without_a_bold_short_cite_writes_it_at_the_full_cite_size() -> None:
    text = (
        (PROFILES / "team-default.yaml")
        .read_text(encoding="utf-8")
        .replace("short_cite_bold: true", "short_cite_bold: false")
        .replace("full_cite_half_points: 22", "full_cite_half_points: 18")
        .replace("name: team-default", "name: small")
    )
    profile = resolve_format_profile(load_format_profile_from_text(text))

    cite = read_paragraphs(render(CardToRender(verified(hand_card()), HAND_CITE), profile=profile))[1]

    assert [(r.text, r.character_style, r.half_points) for r in cite.runs] == [
        ("Rivera et al. 23", None, 18),
        (HAND_CITE.cite_line, None, 18),
    ]


def test_structure_plain_writes_no_highlight_and_keeps_every_underline(
    news: tuple[Card, CardManifest],
) -> None:
    card, manifest = news

    evidence = read_paragraphs(render_cards_docx(manifest, [CardToRender(card, NEWS_CITE)], PLAIN))[2]

    assert {r.highlight for r in evidence.runs} == {None}
    assert [(t, u, s) for t, u, _, s in as_tuples(evidence.runs)] == [
        (t, u, s) for t, u, _, s in NEWS_EVIDENCE_RUNS
    ]


def test_structure_a_card_with_no_evidence_has_no_evidence_paragraph() -> None:
    card = hand_card(evidence_text="", evidence_start_offset=None, evidence_end_offset=None, spans=())

    paragraphs = read_paragraphs(render(CardToRender(card, HAND_CITE, ("MODEL_OUTPUT_INVALID",))))

    assert (paragraphs[0].style_id, paragraphs[0].text) == ("Heading4", card.tag)
    assert paragraphs[-1].text == HAND_CITE.full_cite


def test_structure_the_cards_must_be_the_manifests_cards_in_its_order() -> None:
    first = verified(hand_card(card_id="0CARD000000000000000000001"))
    second = verified(hand_card(card_id="0CARD000000000000000000002"))
    manifest = manifest_of(first, second)

    with pytest.raises(RenderRefused, match="the manifest's cards"):
        render_cards_docx(
            manifest, [CardToRender(second, HAND_CITE), CardToRender(first, HAND_CITE)], TEAM_DEFAULT
        )
    with pytest.raises(RenderRefused, match="the manifest's cards"):
        render_cards_docx(manifest, [CardToRender(first, HAND_CITE)], TEAM_DEFAULT)
    with pytest.raises(RenderRefused, match="the manifest's cards"):
        render_cards_docx(
            manifest,
            [CardToRender(first, HAND_CITE), CardToRender(second.evolve(tag="Changed"), HAND_CITE)],
            TEAM_DEFAULT,
        )


@pytest.mark.parametrize(
    ("character", "name"), [("\r", "U+000D"), ("\x00", "U+0000"), ("\x0b", "U+000B"), ("￾", "U+FFFE")]
)
def test_structure_evidence_a_docx_cannot_carry_as_written_is_refused_never_altered(
    character: str, name: str
) -> None:
    text = f"Before{character}after"
    card = verified(
        hand_card(
            evidence_text=text,
            evidence_start_offset=0,
            evidence_end_offset=len(text),
            spans=(CardSpan(start_offset=0, end_offset=6, style=SpanStyle.UNDERLINE),),
        )
    )

    with pytest.raises(
        RenderRefused, match=re.escape(f"evidence of card {card.card_id} holds {name} at offset 6")
    ):
        render(CardToRender(card, HAND_CITE))


def test_structure_the_same_cards_and_profile_give_the_same_bytes(news: tuple[Card, CardManifest]) -> None:
    card, manifest = news
    cards = [CardToRender(card, NEWS_CITE)]

    first = render_cards_docx(manifest, cards, TEAM_DEFAULT)
    second = render_cards_docx(manifest, cards, TEAM_DEFAULT)

    assert hashlib.sha256(first).hexdigest() == hashlib.sha256(second).hexdigest()
    with zipfile.ZipFile(io.BytesIO(first)) as package:
        assert {info.date_time for info in package.infolist()} == {(2026, 10, 27, 9, 30, 0)}


def test_structure_the_document_properties_name_the_tool_and_no_student(
    news: tuple[Card, CardManifest],
) -> None:
    card, manifest = news

    data = render_cards_docx(manifest, [CardToRender(card, NEWS_CITE)], TEAM_DEFAULT)

    properties = docx.Document(io.BytesIO(data)).core_properties
    assert properties.author == "debate-research"
    assert properties.last_modified_by in ("", "debate-research")
    assert (properties.created, properties.modified) == (GENERATED_AT, GENERATED_AT)
    assert (properties.title, properties.subject, properties.comments, properties.keywords) == (
        "",
        "",
        "",
        "",
    )
    with zipfile.ZipFile(io.BytesIO(data)) as package:
        names = package.namelist()
        documents = {
            name: package.read(name).decode("utf-8") for name in names if name.startswith("docProps/")
        }
    assert sorted(documents) == ["docProps/core.xml"]
    assert "@" not in documents["docProps/core.xml"]
    assert card.owner_id not in documents["docProps/core.xml"]


def test_structure_the_verbatim_parser_reads_the_card_back_under_its_headings(
    news: tuple[Card, CardManifest],
) -> None:
    card, manifest = news
    data = render_cards_docx(
        manifest,
        [CardToRender(card, NEWS_CITE)],
        TEAM_DEFAULT,
        headings=DocumentHeadings(pocket="Neg", hat="De-extinction DA", block="Link"),
    )

    source = SourceDocument(
        sha256=hashlib.sha256(data).hexdigest(),
        byte_size=len(data),
        source_format=SourceFormat.DOCX,
        origin=SourceOrigin.CASELIST_ARCHIVE,
        caselist="rendered26",
        first_seen_snapshot=date(2026, 10, 27),
        last_seen_snapshot=date(2026, 10, 27),
    )
    parsed = DebateDocxParser().parse(data, source, source_path="rendered.docx")

    assert isinstance(parsed, ParsedDocument)
    [parsed_card] = parsed.cards
    assert parsed_card.tag == card.tag
    assert parsed_card.section_path == ("Neg", "De-extinction DA", "Link")
    assert parsed_card.short_cite == "Whitfield 26"
    assert parsed_card.evidence_text.replace(MARKER, "") == card.evidence_text


# --------------------------------------------------------------------------------------------
# Node banners-and-marks: the UNVERIFIED banner and unverified cite fields
# --------------------------------------------------------------------------------------------

RED: Final = "FF0000"


def test_an_unverified_card_gets_a_red_banner_under_its_tag_naming_its_reasons_by_code() -> None:
    card = hand_card()
    reasons = ("CITATION_UNVERIFIED", "EVIDENCE_UNVERIFIED", "CARD_INCOMPLETE")

    paragraphs = read_paragraphs(render(CardToRender(card, HAND_CITE, reasons)))

    tag, banner, cite, evidence = paragraphs
    assert (tag.style_id, tag.text) == ("Heading4", card.tag)
    assert (banner.style_id, banner.text) == (
        "Normal",
        "UNVERIFIED — not a finished card: CITATION_UNVERIFIED, EVIDENCE_UNVERIFIED, CARD_INCOMPLETE",
    )
    assert {r.color for r in banner.runs} == {RED}
    assert {(r.character_style, r.highlight) for r in banner.runs} == {(None, None)}
    assert cite.text == HAND_CITE.full_cite
    assert evidence_read_back(evidence, card)[0] == card.evidence_text


def test_a_failed_card_gets_the_unverified_banner_with_its_own_status() -> None:
    card = hand_card(verification_status=VerificationStatus.FAILED)

    banner = read_paragraphs(render(CardToRender(card, HAND_CITE, ("HASH_MISMATCH",))))[1]

    assert banner.text == "FAILED — not a finished card: HASH_MISMATCH"
    assert {r.color for r in banner.runs} == {RED}


def test_the_unverified_banner_takes_its_colour_from_the_format_profile() -> None:
    text = (PROFILES / "team-default.yaml").read_text(encoding="utf-8")
    profile = resolve_format_profile(
        load_format_profile_from_text(
            text.replace("unverified_banner_color: FF0000", "unverified_banner_color: C00000")
        )
    )

    banner = read_paragraphs(
        render(CardToRender(hand_card(), HAND_CITE, ("SPAN_MISMATCH",)), profile=profile)
    )[1]

    assert {r.color for r in banner.runs} == {"C00000"}


def test_every_unverified_or_failed_card_has_a_banner_and_no_verified_card_has_one() -> None:
    cards = [
        CardToRender(verified(hand_card(card_id="0CARD000000000000000000001")), HAND_CITE),
        CardToRender(hand_card(card_id="0CARD000000000000000000002"), HAND_CITE, ("SPAN_MISMATCH",)),
        CardToRender(verified(hand_card(card_id="0CARD000000000000000000003")), HAND_CITE),
        CardToRender(
            hand_card(card_id="0CARD000000000000000000004", verification_status=VerificationStatus.FAILED),
            HAND_CITE,
            ("TEXT_MISMATCH",),
        ),
    ]

    paragraphs = read_paragraphs(render(*cards))

    banners = [p.text for p in paragraphs if any(r.color == RED for r in p.runs)]
    assert banners == [
        "UNVERIFIED — not a finished card: SPAN_MISMATCH",
        "FAILED — not a finished card: TEXT_MISMATCH",
    ]
    verified_card, unverified_card = (
        ["Heading4", "Normal", "Normal"],
        ["Heading4", "Normal", "Normal", "Normal"],
    )
    assert [
        p.style_id for p in paragraphs
    ] == verified_card + unverified_card + verified_card + unverified_card


def test_a_verified_card_renders_no_unverified_banner(news: tuple[Card, CardManifest]) -> None:
    card, manifest = news

    paragraphs = read_paragraphs(render_cards_docx(manifest, [CardToRender(card, NEWS_CITE)], TEAM_DEFAULT))

    assert len(paragraphs) == 3
    assert all(r.color is None for p in paragraphs for r in p.runs)
    assert not any("not a finished card" in p.text for p in paragraphs)


@pytest.mark.parametrize(
    ("status", "reasons", "problem"),
    [
        (VerificationStatus.UNVERIFIED, (), "its banner must name why"),
        (VerificationStatus.FAILED, (), "its banner must name why"),
        (VerificationStatus.VERIFIED, ("SPAN_MISMATCH",), "is VERIFIED"),
        (VerificationStatus.UNVERIFIED, ("the evidence says elephants are alive now",), "is a code"),
        (VerificationStatus.UNVERIFIED, ("citation_unverified",), "is a code"),
        (VerificationStatus.UNVERIFIED, ("SPAN_MISMATCH", ""), "is a code"),
    ],
)
def test_unverified_reasons_are_codes_given_exactly_when_a_card_is_not_verified(
    status: VerificationStatus, reasons: tuple[str, ...], problem: str
) -> None:
    with pytest.raises(RenderRefused, match=problem):
        CardToRender(hand_card(verification_status=status), HAND_CITE, reasons)


def test_the_unverified_banner_holds_no_word_of_the_snapshot_only_its_status_and_codes() -> None:
    card = hand_card()

    banner = read_paragraphs(render(CardToRender(card, HAND_CITE, ("CITATION_UNVERIFIED",))))[1]

    status, _, rest = banner.text.partition(" — not a finished card: ")
    assert (status, rest) == ("UNVERIFIED", "CITATION_UNVERIFIED")
    evidence_words = {word.strip(".,").lower() for word in card.evidence_text.split()}
    assert not evidence_words & {word.strip(".,:—").lower() for word in banner.text.split()} - {"not", "a"}


def unverified_cite(**fields: CitationField[Any]) -> Card:
    return hand_card(citation=FULLY_VERIFIED_CITATION.evolve(**fields))


def cite_paragraph(card: Card, reasons: tuple[str, ...] = ("CITATION_UNVERIFIED",)) -> ReadParagraph:
    paragraphs = read_paragraphs(render(CardToRender(card, HAND_CITE, reasons)))
    [cite] = [p for p in paragraphs if p.text.startswith(HAND_CITE.short_cite)]
    return cite


def test_unverified_cite_fields_are_marked_after_the_cite_from_the_citations_own_flags() -> None:
    card = unverified_cite(
        authors=FULLY_VERIFIED_CITATION.authors.evolve(source=CitationFieldSource.HEURISTIC, verified=False),
        published_at=CitationField[datetime](),
        canonical_url=FULLY_VERIFIED_CITATION.canonical_url.evolve(verified=False),
    )

    cite = cite_paragraph(card)

    assert cite.text == HAND_CITE.full_cite + " [author unverified] [date unverified] [URL unverified]"
    assert [(r.text, r.character_style, r.half_points) for r in cite.runs][-1] == (
        " [author unverified] [date unverified] [URL unverified]",
        None,
        22,
    )


def test_an_optional_cite_field_is_marked_only_when_it_is_shown_unverified() -> None:
    missing = unverified_cite(author_credentials=CitationField[str]())
    unverified = unverified_cite(
        author_credentials=FULLY_VERIFIED_CITATION.author_credentials.evolve(verified=False),
        accessed_at=FULLY_VERIFIED_CITATION.accessed_at.evolve(verified=False),
    )

    assert cite_paragraph(verified(missing), ()).text == HAND_CITE.full_cite
    assert cite_paragraph(verified(unverified), ()).text == (
        HAND_CITE.full_cite + " [credentials unverified] [accessed date unverified]"
    )


def test_a_field_the_student_cleared_is_marked_cleared_not_unverified() -> None:
    card = unverified_cite(authors=CitationField[tuple[str, ...]]()).evolve(
        citation=FULLY_VERIFIED_CITATION.evolve(
            authors=CitationField[tuple[str, ...]](),
            accessed_at=CitationField[datetime](),
            cleared_by_student=("authors", "accessed_at"),
        )
    )

    cite = cite_paragraph(card)

    assert (
        cite.text == HAND_CITE.full_cite + " [author cleared by student] [accessed date cleared by student]"
    )
    assert "unverified]" not in cite.text


def test_a_fully_verified_cite_has_no_unverified_mark(news: tuple[Card, CardManifest]) -> None:
    card, manifest = news

    cite = read_paragraphs(render_cards_docx(manifest, [CardToRender(card, NEWS_CITE)], TEAM_DEFAULT))[1]

    assert cite.text == NEWS_CITE.full_cite


# --------------------------------------------------------------------------------------------
# Node manifest-part: the embedded custom XML manifest, and reading it back
# --------------------------------------------------------------------------------------------

MANIFEST_NAMESPACE: Final = "urn:debate-intelligence:manifest:v1"
CUSTOM_XML: Final = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/customXml"


def custom_xml_items(data: bytes) -> dict[str, bytes]:
    """Every custom XML data item in the package, by member name, without their properties parts."""
    with zipfile.ZipFile(io.BytesIO(data)) as package:
        return {
            name: package.read(name)
            for name in package.namelist()
            if name.startswith("customXml/item") and not name.startswith("customXml/itemProps")
        }


def test_the_manifest_part_holds_the_manifests_serialized_bytes_in_one_namespaced_element(
    news: tuple[Card, CardManifest],
) -> None:
    card, manifest = news

    data = render_cards_docx(manifest, [CardToRender(card, NEWS_CITE)], TEAM_DEFAULT)

    [(name, item)] = custom_xml_items(data).items()
    root = ElementTree.fromstring(item)
    assert name == "customXml/item1.xml"
    assert root.tag == f"{{{MANIFEST_NAMESPACE}}}manifest"
    assert len(root) == 0
    assert (root.text or "").encode("utf-8") == serialize_manifest(manifest)


def test_the_manifest_part_is_related_from_the_document_with_its_properties_part(
    news: tuple[Card, CardManifest],
) -> None:
    card, manifest = news

    data = render_cards_docx(manifest, [CardToRender(card, NEWS_CITE)], TEAM_DEFAULT)

    with zipfile.ZipFile(io.BytesIO(data)) as package:
        relationships = ElementTree.fromstring(package.read("word/_rels/document.xml.rels"))
        item_relationships = ElementTree.fromstring(package.read("customXml/_rels/item1.xml.rels"))
        properties = ElementTree.fromstring(package.read("customXml/itemProps1.xml"))
        content_types = package.read("[Content_Types].xml").decode("utf-8")
    assert [r.get("Target") for r in relationships if r.get("Type") == CUSTOM_XML] == [
        "../customXml/item1.xml"
    ]
    assert [r.get("Target") for r in item_relationships] == ["itemProps1.xml"]
    schema_refs = properties.iter(
        "{http://schemas.openxmlformats.org/officeDocument/2006/customXml}schemaRef"
    )
    assert [
        ref.get("{http://schemas.openxmlformats.org/officeDocument/2006/customXml}uri") for ref in schema_refs
    ] == [MANIFEST_NAMESPACE]
    assert 'PartName="/customXml/itemProps1.xml"' in content_types


def test_read_embedded_manifest_gives_back_the_same_manifest_and_bytes(
    news: tuple[Card, CardManifest], tmp_path: Path
) -> None:
    card, manifest = news
    path = tmp_path / "evidence.docx"
    path.write_bytes(render_cards_docx(manifest, [CardToRender(card, NEWS_CITE)], TEAM_DEFAULT))

    assert read_embedded_manifest(path) == manifest
    assert read_embedded_manifest_bytes(path) == serialize_manifest(manifest)


def test_the_embedded_manifest_survives_a_save_and_reopen_beside_another_custom_xml_part(
    news: tuple[Card, CardManifest], tmp_path: Path
) -> None:
    """Word keeps custom XML parts, and may add its own (a bibliography) and renumber them."""
    card, manifest = news
    rendered = tmp_path / "rendered.docx"
    rendered.write_bytes(render_cards_docx(manifest, [CardToRender(card, NEWS_CITE)], TEAM_DEFAULT))
    document = docx.Document(str(rendered))
    sources = Part(
        PackURI("/customXml/item2.xml"),
        "application/xml",
        b'<b:Sources xmlns:b="http://schemas.openxmlformats.org/officeDocument/2006/bibliography"/>',
        document.part.package,
    )
    document.part.relate_to(sources, CUSTOM_XML)
    saved = tmp_path / "saved.docx"
    document.save(str(saved))

    assert len(custom_xml_items(saved.read_bytes())) == 2
    assert read_embedded_manifest_bytes(saved) == serialize_manifest(manifest)
    assert read_embedded_manifest(saved) == manifest


def test_one_manifest_lists_every_card_of_the_document_in_document_order(tmp_path: Path) -> None:
    cards = [
        CardToRender(verified(hand_card(card_id=f"0CARD00000000000000000000{n}", tag=f"Tag {n}")), HAND_CITE)
        for n in (3, 1, 2)
    ]
    path = tmp_path / "three.docx"
    path.write_bytes(render(*cards))

    embedded = read_embedded_manifest(path)
    tags = [p.text for p in read_paragraphs(path.read_bytes()) if p.style_id == "Heading4"]
    assert [c.card_id for c in embedded.cards] == [c.card.card_id for c in cards]
    assert tags == [c.tag for c in embedded.cards] == ["Tag 3", "Tag 1", "Tag 2"]
    assert len(custom_xml_items(path.read_bytes())) == 1


def test_a_manifest_holding_xml_markup_characters_round_trips_exactly(tmp_path: Path) -> None:
    card = verified(hand_card(tag='Methane <b>"rises"</b> & ]]> the feedback runs'))
    path = tmp_path / "markup.docx"
    path.write_bytes(render(CardToRender(card, HAND_CITE)))

    assert read_embedded_manifest(path).cards == (card,)
    assert read_embedded_manifest_bytes(path) == serialize_manifest(manifest_of(card))


def rewritten(data: bytes, replace: dict[str, bytes | None]) -> bytes:
    """`data` with members replaced (or removed, for None), every other member as it was."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(buffer, "w") as target:
        for name in source.namelist():
            if name not in replace:
                target.writestr(name, source.read(name))
        for name, content in replace.items():
            if content is not None:
                target.writestr(name, content)
    return buffer.getvalue()


def test_a_document_with_no_manifest_or_two_is_refused_by_the_reader(tmp_path: Path) -> None:
    data = render(CardToRender(verified(hand_card()), HAND_CITE))
    item = custom_xml_items(data)["customXml/item1.xml"]
    none = tmp_path / "none.docx"
    none.write_bytes(rewritten(data, {"customXml/item1.xml": None}))
    two = tmp_path / "two.docx"
    two.write_bytes(rewritten(data, {"customXml/item7.xml": item}))

    with pytest.raises(EmbeddedManifestError, match="holds no embedded manifest"):
        read_embedded_manifest(none)
    with pytest.raises(EmbeddedManifestError, match="holds 2 embedded manifests"):
        read_embedded_manifest(two)


def test_the_manifest_reader_refuses_a_custom_xml_part_that_declares_a_document_type(tmp_path: Path) -> None:
    data = render(CardToRender(verified(hand_card()), HAND_CITE))
    hostile = (
        b'<?xml version="1.0"?><!DOCTYPE m [<!ENTITY a "aaaaaaaaaa">]>'
        b'<manifest xmlns="urn:debate-intelligence:manifest:v1">&a;</manifest>'
    )
    path = tmp_path / "hostile.docx"
    path.write_bytes(rewritten(data, {"customXml/item1.xml": hostile}))

    with pytest.raises(EmbeddedManifestError, match="declares a document type"):
        read_embedded_manifest_bytes(path)


def test_a_manifest_element_with_more_than_text_in_it_is_refused(tmp_path: Path) -> None:
    data = render(CardToRender(verified(hand_card()), HAND_CITE))
    nested = b'<manifest xmlns="urn:debate-intelligence:manifest:v1">{}<extra/></manifest>'
    path = tmp_path / "nested.docx"
    path.write_bytes(rewritten(data, {"customXml/item1.xml": nested}))

    with pytest.raises(EmbeddedManifestError, match="holds only the manifest's text"):
        read_embedded_manifest_bytes(path)


def test_a_manifest_an_xml_part_cannot_carry_is_refused_before_anything_is_written() -> None:
    title = FULLY_VERIFIED_CITATION.title.evolve(value="Methane￿ release")
    card = verified(hand_card(citation=FULLY_VERIFIED_CITATION.evolve(title=title)))

    with pytest.raises(RenderRefused, match=re.escape("the manifest holds U+FFFF")):
        render(CardToRender(card, HAND_CITE))


# --------------------------------------------------------------------------------------------
# Node renderer-suite: LibreOffice opens the file (slow; validate-dev's slow job installs soffice)
# --------------------------------------------------------------------------------------------


@pytest.mark.slow
def test_libreoffice_opens_a_rendered_document_headless_and_reads_every_paragraph(tmp_path: Path) -> None:
    """A file Word or LibreOffice would offer to repair does not load headless, so nothing is converted.

    It skips only where soffice is absent, which is a laptop: validate-dev's slow job installs it, and
    a skip there fails the tier (v1-e01-t10).
    """
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if soffice is None:
        pytest.skip("LibreOffice (soffice) is not installed here; validate-dev's slow job installs it")
    unverified = hand_card(card_id="0CARD000000000000000000002", tag="An unverified card")
    source = tmp_path / "cards.docx"
    source.write_bytes(
        render(
            CardToRender(verified(unicode_card()), HAND_CITE),
            CardToRender(unverified, HAND_CITE, ("CITATION_UNVERIFIED",)),
            headings=DocumentHeadings(pocket="Aff", hat="Methane", block="Feedbacks"),
        )
    )

    result = subprocess.run(
        [
            soffice,
            "--headless",
            "--norestore",
            f"-env:UserInstallation={(tmp_path / 'profile').as_uri()}",
            "--convert-to",
            "txt:Text (encoded):UTF8",
            "--outdir",
            str(tmp_path / "converted"),
            str(source),
        ],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )

    converted = tmp_path / "converted" / "cards.txt"
    assert result.returncode == 0, result.stderr
    assert converted.exists(), f"LibreOffice converted nothing: {result.stdout} {result.stderr}"
    text = converted.read_text(encoding="utf-8-sig")
    for expected in (
        "Aff",
        "Feedbacks",
        "Arctic methane feedback is already measurable",
        "UNVERIFIED — not a finished card: CITATION_UNVERIFIED",
        HAND_CITE.full_cite,
        "[the island]Ærø’s “café” — naïve 🐘",
        f"ts.{MARKER}[and]Ice melts[emphasis added]",
    ):
        assert expected in text, expected

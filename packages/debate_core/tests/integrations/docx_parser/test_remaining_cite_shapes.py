"""The cite shapes `v1-e31-t12` counted and left, each rebuilt as an invented file (`v1-e31-t19`).

Counted first over the operator's corpus, read in place by counts only
(`docs/data/caselist-parse-report.md`), then settled by the PM's rulings of 2026-10-18:

* **A cite behind a first name or a title** (`Adaeze Okonkwo 26`, `Dr. Okonkwo 26`): where a cite
  stands, a line whose name and year start within 40 characters behind one to three capitalised
  words or a title, and that sets the name and year (or its opening) in bold, or holds everything
  after the year in one bracket.
* **A paragraph style that maps to no unit** (`Normal (Web)`, `List Paragraph`) no longer hides the
  cite and body rules. It still hides the heading rules.
* **A highlighted cite** is a cite where a cite stands and a body follows.
* **`v1-e31-t09`'s cite-style hold** keeps a long guess as a cite only when the style marks a name
  and a year at its head. A style anywhere else is emphasis.
* **A short cite written with U+2018 before its year** (`Okonkwo ‘26`, as Word's autocorrect types
  it) is read as one written with ’, for matching only: the text is not changed.

Every file is built in memory from invented text, and every expectation is written by hand
(working agreement 6).
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from tests.evals.parser.cite_shapes import CITE_SIZE, READING_SIZE, SMALL_PRINT, SOURCE, prose, qualifications

from debate_core.application.ports.parsed_store import parse_version_directory
from debate_core.domain.caselist import SourceDocument, SourceFormat, SourceOrigin
from debate_core.domain.debate_files import CardCompleteness, ParsedCard, ParsedDocument
from debate_core.domain.style_profile import StructuralUnit, StyleMatchSource, StyleProfile
from debate_core.evidence.style_classifier import (
    ParagraphDescription,
    RunDescription,
    classify_paragraph,
    is_a_highlighted_cite,
)
from debate_core.integrations.docx_parser.parser import DOCX_PARSER_VERSION, DebateDocxParser
from debate_core.testing.docx_builder import build_docx, paragraph_xml, run_xml

SOURCE_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
SNAPSHOT = date(2026, 10, 18)
SOURCE_PATH = "hspf26/Invented High/AB/Invented High-AB-Aff-Imaginary Invitational-Round 2.docx"

TAG = "Data centre demand collapses the reserve margin"
CITE = StructuralUnit.CITE
EVIDENCE = StructuralUnit.EVIDENCE
OTHER = StructuralUnit.OTHER
FULL = CardCompleteness.FULL
CITE_ONLY = CardCompleteness.CITE_ONLY

BEHIND_A_NAME = "assembly-cite-behind-a-name-before-the-body"
HIGHLIGHTED_CITE = "assembly-highlighted-cite-before-the-body"


@pytest.fixture
def parser(profile: StyleProfile) -> DebateDocxParser:
    return DebateDocxParser(profile)


def parse(parser: DebateDocxParser, *paragraphs: str) -> ParsedDocument:
    source = SourceDocument(
        sha256=SOURCE_SHA256,
        byte_size=48_000,
        source_format=SourceFormat.DOCX,
        origin=SourceOrigin.CASELIST_ARCHIVE,
        caselist="hspf26",
        first_seen_snapshot=SNAPSHOT,
        last_seen_snapshot=SNAPSHOT,
    )
    result = parser.parse(build_docx("".join(paragraphs)), source, source_path=SOURCE_PATH)
    assert isinstance(result, ParsedDocument), result
    return result


def only_card(document: ParsedDocument) -> ParsedCard:
    """The document's one card. Any other number of cards fails here, by assertion."""
    ranges = [(c.provenance.first_element_index, c.provenance.last_element_index) for c in document.cards]
    assert len(ranges) == 1, ranges
    return document.cards[0]


def section_of(document: ParsedDocument, text: str) -> Any:
    (section,) = [section for section in document.sections if section.text == text]
    return section


Runs = list[tuple[str, dict[str, Any]]]


def paragraph(runs: Runs, style: str | None = None, outline_level: int | None = None) -> tuple[str, str]:
    """A paragraph's markup and its text."""
    markup = paragraph_xml(
        "".join(run_xml(text, **formatting) for text, formatting in runs),
        style=style,
        outline_level=outline_level,
    )
    return markup, "".join(text for text, _ in runs)


def tag_paragraph(text: str = TAG) -> str:
    return paragraph_xml(run_xml(text), style="Heading4")


def cite_paragraph(style: str | None = None) -> tuple[str, str]:
    """A cite as a file with no cite style writes one: a bold name at 13 pt, then the rest."""
    return paragraph(
        [
            ("Okonkwo 26", {"bold": True, "half_points": CITE_SIZE}),
            (f", Adaeze Okonkwo, invented for this test, {SOURCE}.", {"half_points": READING_SIZE}),
        ],
        style=style,
    )


BODY_TEXT = prose(240)


def body_paragraph(text: str = BODY_TEXT, style: str | None = None) -> tuple[str, str]:
    """8 pt text with an underlined, highlighted stretch a debater reads aloud."""
    return paragraph(
        [
            (text[:60], {"half_points": SMALL_PRINT}),
            (text[60:140], {"underline": "single", "highlight": "cyan", "half_points": SMALL_PRINT}),
            (text[140:], {"half_points": SMALL_PRINT}),
        ],
        style=style,
    )


BODY, _ = body_paragraph()
CITE_MARKUP, CITE_TEXT = cite_paragraph()


# --------------------------------------------------------------------------------------------
# (1) A cite behind a first name or a title
# --------------------------------------------------------------------------------------------

#: What follows the name and year in each cite below: credentials and the source.
TAIL = f", professor of energy policy, Invented Institute of Grid Studies, {SOURCE}"

#: The same, long enough that ending a sentence makes it prose to the classifier: 200 characters.
SENTENCE_TAIL = TAIL + ", a review of reserve margins in four regional markets."


def behind_a_name(
    before: str,
    name: str = "Okonkwo 26",
    after: str = TAIL,
    *,
    name_bold: bool = True,
    before_bold: bool = False,
    highlight: str | None = None,
    underline_after: bool = False,
    cite_style: bool = False,
) -> tuple[str, str]:
    """`before` + `name` + `after`, at reading size, formatted as asked."""
    name_formatting: dict[str, Any] = {"bold": True} if name_bold else {}
    if highlight:
        name_formatting["highlight"] = highlight
    if cite_style:
        name_formatting["character_style"] = "Style13ptBold"
    after_formatting: dict[str, Any] = {"underline": "single"} if underline_after else {}
    return paragraph(
        [
            (before, {"bold": True} if before_bold else {}),
            (name, name_formatting),
            (after, after_formatting),
        ]
    )


TAKEN_BEHIND_A_NAME = {
    "a first name, the name and year in bold": behind_a_name("Adaeze "),
    "a first name, ending a sentence, read as body before": behind_a_name("Adaeze ", after=SENTENCE_TAIL),
    "two first names": behind_a_name("Adaeze Ngozi "),
    "an initial": behind_a_name("A. "),
    "three words": behind_a_name("Adaeze N. Ngozi "),
    "a title": behind_a_name("Dr. "),
    "a title and two names": behind_a_name("Professor Adaeze Ngozi "),
    "the opening in bold, the name and year not": behind_a_name("Adaeze ", name_bold=False, before_bold=True),
    "an underlined link after it": behind_a_name("Adaeze ", underline_after=True),
    "a first name, then one bracket to the end": behind_a_name(
        "Adaeze ", after=f" [{TAIL[2:]}] KR", name_bold=False
    ),
    "et al.": behind_a_name("Adaeze ", name="Okonkwo et al. 26"),
    "a left quote before the year": behind_a_name("Adaeze ", name="Okonkwo \u201826"),
    "a title and three names": behind_a_name("Professor Adaeze N. Ngozi "),
}


class TestACiteBehindAFirstNameOrATitle:
    @pytest.mark.parametrize("built", TAKEN_BEHIND_A_NAME.values(), ids=TAKEN_BEHIND_A_NAME.keys())
    def test_under_a_tag_it_is_the_cards_cite(self, parser: DebateDocxParser, built: tuple[str, str]) -> None:
        markup, text = built
        document = parse(parser, tag_paragraph(), markup, BODY)

        card = only_card(document)
        assert (card.tag, card.full_cite, card.evidence_text, card.completeness) == (
            TAG,
            text,
            BODY_TEXT,
            FULL,
        )
        section = section_of(document, text)
        assert section.unit is CITE
        assert section.match.rule_id.startswith(BEHIND_A_NAME + ":heuristic-")
        assert section.match.match_source is StyleMatchSource.HEURISTIC
        assert section.match.confidence == 0.6

    def test_under_the_cards_cite_it_is_a_second_line_of_the_cite(self, parser: DebateDocxParser) -> None:
        markup, text = behind_a_name("Adaeze ")
        card = only_card(parse(parser, tag_paragraph(), CITE_MARKUP, markup, BODY))

        assert (card.full_cite, card.evidence_text) == (CITE_TEXT + "\n" + text, BODY_TEXT)

    def test_a_tag_whose_only_paragraph_it_is_is_a_cite_only_card(self, parser: DebateDocxParser) -> None:
        markup, text = behind_a_name("Adaeze ")
        document = parse(parser, tag_paragraph(), markup, tag_paragraph("Another tag"), BODY)

        assert [(c.tag, c.full_cite, c.completeness) for c in document.cards] == [
            (TAG, text, CITE_ONLY),
            ("Another tag", "", FULL),
        ]

    def test_inside_a_body_it_is_left_as_it_was(self, parser: DebateDocxParser) -> None:
        markup, text = behind_a_name("Adaeze ", after=SENTENCE_TAIL)
        assert len(text) >= 200
        second_body, second_text = body_paragraph(prose(300, "Planners responded."))
        document = parse(parser, tag_paragraph(), CITE_MARKUP, BODY, markup, second_body)

        card = only_card(document)
        assert card.full_cite == CITE_TEXT
        assert card.evidence_text == "\n".join([BODY_TEXT, text, second_text])
        assert section_of(document, text).match.rule_id == "heuristic-prose-paragraph"

    LEFT = {
        "highlighted": behind_a_name("Adaeze ", highlight="yellow"),
        "plain: no bold and no bracket": behind_a_name("Adaeze ", name_bold=False),
        "four words before the name": behind_a_name("Adaeze Ngozi Chidinma Ama "),
        "a sentence opener before it": behind_a_name("In "),
        "a lower-case word before it": behind_a_name("according to "),
        "a sentence before it": behind_a_name("The audit by "),
        "the name and year past 40 characters": behind_a_name("Adaeze N" + "g" * 32 + " "),
        "the name and year in the cite style": behind_a_name("Adaeze ", cite_style=True, after=TAIL + "."),
        "only the name bold, not its year": paragraph(
            [("Adaeze ", {}), ("Okonkwo", {"bold": True}), (" 26" + TAIL, {})]
        ),
        "the cite style on a phrase further in, past 1,000 characters": paragraph(
            [
                ("Adaeze ", {}),
                ("Okonkwo 26", {"bold": True}),
                (", " + qualifications(1_000), {}),
                ("Grid Studies", {"character_style": "Style13ptBold"}),
                (", " + qualifications(100) + ".", {}),
            ]
        ),
    }

    @pytest.mark.parametrize("built", LEFT.values(), ids=LEFT.keys())
    def test_what_the_rule_leaves(self, parser: DebateDocxParser, built: tuple[str, str]) -> None:
        markup, text = built
        document = parse(parser, tag_paragraph(), markup, BODY)

        assert not section_of(document, text).match.rule_id.startswith(BEHIND_A_NAME)

    def test_the_name_and_year_at_40_characters_is_taken(self, parser: DebateDocxParser) -> None:
        before = "Adaeze N" + "g" * 31 + " "
        assert len(before) == 40
        markup, text = behind_a_name(before)

        assert section_of(parse(parser, tag_paragraph(), markup, BODY), text).unit is CITE

    @pytest.mark.parametrize(("length", "taken"), [(2_000, True), (2_001, False)])
    def test_the_line_ends_by_2000_characters(
        self, parser: DebateDocxParser, length: int, taken: bool
    ) -> None:
        opening = "Adaeze Okonkwo 26, "
        markup, text = paragraph(
            [("Adaeze ", {}), ("Okonkwo 26", {"bold": True}), (", " + qualifications(length - 19), {})]
        )
        assert len(text) == length and text.startswith(opening)

        assert (section_of(parse(parser, tag_paragraph(), markup, BODY), text).unit is CITE) is taken


# --------------------------------------------------------------------------------------------
# (2) A paragraph style that maps to no unit
# --------------------------------------------------------------------------------------------

UNMAPPED_STYLES = ["NormalWeb", "ListParagraph", "BodyText", "Normal"]


class TestAParagraphStyleThatMapsToNoUnit:
    @pytest.mark.parametrize("style", UNMAPPED_STYLES)
    def test_its_cite_and_body_are_read(self, parser: DebateDocxParser, style: str) -> None:
        cite_markup, cite_text = cite_paragraph(style=style)
        body_markup, body_text = body_paragraph(style=style)
        document = parse(parser, tag_paragraph(), cite_markup, body_markup)

        card = only_card(document)
        assert (card.tag, card.full_cite, card.evidence_text, card.completeness) == (
            TAG,
            cite_text,
            body_text,
            FULL,
        )
        cite_section, body_section = section_of(document, cite_text), section_of(document, body_text)
        assert cite_section.match.rule_id.startswith("heuristic-cite-line-author-year:verbatim-")
        assert body_section.match.rule_id.startswith("heuristic-marked-up-body-text:verbatim-")
        assert cite_section.match.rule_id.endswith(style)

    def test_a_cite_style_run_in_it_is_a_cite(self, parser: DebateDocxParser) -> None:
        markup, text = paragraph(
            [("Okonkwo 26", {"character_style": "Style13ptBold"}), (", invented for this test.", {})],
            style="NormalWeb",
        )
        section = section_of(parse(parser, tag_paragraph(), markup, BODY), text)

        assert section.unit is CITE
        assert section.match.rule_id == "verbatim-cite-run-style:verbatim-alias-id:NormalWeb"
        assert section.match.match_source is StyleMatchSource.VERBATIM_ALIAS

    @pytest.mark.parametrize(
        "heading",
        [
            paragraph([("Grid Reliability", {"bold": True, "half_points": 26})], style="NormalWeb"),
            paragraph([("Grid Reliability", {"bold": True})], style="NormalWeb", outline_level=3),
            paragraph(
                [("Grid Reliability", {"bold": True, "half_points": 52})], style="NormalWeb", outline_level=0
            ),
        ],
        ids=["bold at tag size", "bold at outline level 3", "bold at pocket size and outline level 0"],
    )
    def test_the_heading_rules_never_see_through_it(
        self, parser: DebateDocxParser, heading: tuple[str, str]
    ) -> None:
        markup, text = heading
        section = section_of(parse(parser, markup, CITE_MARKUP, BODY), text)

        assert (section.unit, section.match.rule_id) == (OTHER, "verbatim-alias-id:NormalWeb")

    def test_a_short_plain_line_in_it_is_still_nothing(self, parser: DebateDocxParser) -> None:
        markup, text = paragraph([("Continued below", {})], style="NormalWeb")
        section = section_of(parse(parser, tag_paragraph(), CITE_MARKUP, BODY, markup), text)

        assert (section.unit, section.match.rule_id) == (OTHER, "verbatim-alias-id:NormalWeb")

    def test_a_mapped_style_is_untouched(self, parser: DebateDocxParser) -> None:
        """`Heading4` says "tag", whatever its runs look like."""
        markup, text = paragraph([("Okonkwo 26, invented for this test.", {"bold": True})], style="Heading4")
        section = section_of(parse(parser, markup, BODY), text)

        assert section.match.rule_id == "verbatim-style-id:Heading4"

    def test_the_classifier_sees_through_it(self, profile: StyleProfile) -> None:
        described = ParagraphDescription(
            runs=(RunDescription(text="Okonkwo 26, invented for this test.", bold=True, half_points=26),),
            style_id="NormalWeb",
        )

        assert classify_paragraph(described, profile).unit is CITE

    def test_the_classifier_leaves_a_table_cell_in_it_as_it_was(self, profile: StyleProfile) -> None:
        described = ParagraphDescription(
            runs=(RunDescription(text="Okonkwo 26, invented for this test.", bold=True, half_points=26),),
            style_id="NormalWeb",
            in_table=True,
        )

        assert classify_paragraph(described, profile).rule_id == "verbatim-alias-id:NormalWeb"

    def test_a_blank_paragraph_in_small_print_in_it_is_still_nothing(self, profile: StyleProfile) -> None:
        """Its mark is small print, which the body rule would take for shrunk text: a blank body line."""
        described = ParagraphDescription(runs=(), style_id="NormalWeb", paragraph_half_points=SMALL_PRINT)

        assert classify_paragraph(described, profile).unit is OTHER

    def test_a_table_cell_in_it_is_still_page_furniture(self, parser: DebateDocxParser) -> None:
        cite_markup, cite_text = cite_paragraph(style="NormalWeb")
        table = f"<w:tbl><w:tr><w:tc>{cite_markup}</w:tc></w:tr></w:tbl>"
        section = section_of(parse(parser, tag_paragraph(), table, BODY), cite_text)

        assert section.unit is OTHER


# --------------------------------------------------------------------------------------------
# (3) A highlighted cite
# --------------------------------------------------------------------------------------------


def highlighted_cite(kind: str, length: int = 600, highlight_all: bool = False) -> tuple[str, str]:
    """A cite of `length` characters with its name highlighted, in one of the three shapes."""
    rest = qualifications(length - len("Okonkwo 26, ") - (4 if kind == "one bracket" else 0))
    highlight = {"highlight": "yellow"}
    if kind == "bold opening":
        runs: Runs = [
            ("Okonkwo 26", {"bold": True, **highlight}),
            (", " + rest, highlight if highlight_all else {}),
        ]
    elif kind == "one bracket":
        runs = [("Okonkwo 26", highlight), (" [" + rest + "] KR", {})]
    else:
        runs = [("Okonkwo 26", {"character_style": "Style13ptBold", **highlight}), (", " + rest, {})]
    markup, text = paragraph(runs)
    assert len(text) == length, (kind, len(text))
    return markup, text


HIGHLIGHTED_KINDS = ["bold opening", "one bracket", "styled head"]
STYLED_PAST_THE_PROFILE = 1_200


def kind_length(kind: str) -> int:
    return STYLED_PAST_THE_PROFILE if kind == "styled head" else 600


class TestAHighlightedCite:
    @pytest.mark.parametrize("kind", HIGHLIGHTED_KINDS)
    def test_under_a_tag_with_a_body_below_it_is_the_cards_cite(
        self, parser: DebateDocxParser, kind: str
    ) -> None:
        markup, text = highlighted_cite(kind, kind_length(kind))
        document = parse(parser, tag_paragraph(), markup, BODY)

        card = only_card(document)
        assert (card.tag, card.full_cite, card.evidence_text, card.completeness) == (
            TAG,
            text,
            BODY_TEXT,
            FULL,
        )
        section = section_of(document, text)
        assert section.match.rule_id == f"{HIGHLIGHTED_CITE}:heuristic-marked-up-body-text"
        assert section.match.confidence == 0.6

    def test_a_left_quote_before_its_year_is_read_as_an_apostrophe(self, parser: DebateDocxParser) -> None:
        markup, text = paragraph(
            [("Okonkwo \u201826", {"bold": True, "highlight": "yellow"}), (", " + qualifications(588), {})]
        )

        assert only_card(parse(parser, tag_paragraph(), markup, BODY)).full_cite == text

    def test_highlighted_throughout_it_is_still_the_cite_when_a_body_follows(
        self, parser: DebateDocxParser
    ) -> None:
        markup, text = highlighted_cite("bold opening", highlight_all=True)

        assert only_card(parse(parser, tag_paragraph(), markup, BODY)).full_cite == text

    @pytest.mark.parametrize("kind", HIGHLIGHTED_KINDS)
    def test_with_no_body_below_it_is_a_card_written_as_one_paragraph(
        self, parser: DebateDocxParser, kind: str
    ) -> None:
        markup, text = highlighted_cite(kind, kind_length(kind))
        document = parse(parser, tag_paragraph(), markup, tag_paragraph("Another tag"), CITE_MARKUP, BODY)

        assert [(c.tag, c.full_cite, c.evidence_text) for c in document.cards] == [
            (TAG, "", text),
            ("Another tag", CITE_TEXT, BODY_TEXT),
        ]

    def test_a_blank_line_between_it_and_the_body_changes_nothing(self, parser: DebateDocxParser) -> None:
        markup, text = highlighted_cite("bold opening")
        blank = paragraph_xml(run_xml(""))

        assert only_card(parse(parser, tag_paragraph(), markup, blank, BODY)).full_cite == text

    def test_the_shape_is_a_highlighted_ones(self, profile: StyleProfile) -> None:
        """Not highlighted, a paragraph of the same shape is the long cite line's to read."""
        described = ParagraphDescription(
            runs=(
                RunDescription(text="Okonkwo 26", bold=True),
                RunDescription(text=", " + qualifications(600)),
            )
        )

        assert is_a_highlighted_cite(described, profile) is False
        highlighted = described.model_copy(
            update={"runs": (described.runs[0].model_copy(update={"highlight": "yellow"}), described.runs[1])}
        )
        assert is_a_highlighted_cite(highlighted, profile) is True

    def test_after_a_body_it_is_left_in_the_body(self, parser: DebateDocxParser) -> None:
        markup, text = highlighted_cite("bold opening")
        card = only_card(parse(parser, tag_paragraph(), CITE_MARKUP, BODY, markup, BODY))

        assert card.full_cite == CITE_TEXT
        assert card.evidence_text == "\n".join([BODY_TEXT, text, BODY_TEXT])

    @pytest.mark.parametrize(
        ("kind", "length", "taken"),
        [
            ("bold opening", 2_000, True),
            ("bold opening", 2_001, False),
            ("one bracket", 2_000, True),
            ("one bracket", 2_001, False),
            ("styled head", 4_000, True),
            ("styled head", 4_001, False),
        ],
    )
    def test_its_bounds(self, parser: DebateDocxParser, kind: str, length: int, taken: bool) -> None:
        markup, text = highlighted_cite(kind, length)

        assert (section_of(parse(parser, tag_paragraph(), markup, BODY), text).unit is CITE) is taken

    def test_a_sentence_opener_is_no_author(self, parser: DebateDocxParser) -> None:
        markup, text = paragraph(
            [("In 2019", {"bold": True, "highlight": "yellow"}), (", " + qualifications(600), {})]
        )

        assert section_of(parse(parser, tag_paragraph(), markup, BODY), text).unit is EVIDENCE


# --------------------------------------------------------------------------------------------
# (4) v1-e31-t09's cite-style hold
# --------------------------------------------------------------------------------------------

#: A guess past 2,000 characters: prose that holds an ellipsis and a name with a year 900 in.
LONG_GUESS = (
    prose(899)[:899]
    + " Lindqvist 2019 reached the same conclusion [...] and so did the audit. "
    + prose(1_400)
)[:2_300]


def long_guess(*, styled: str) -> tuple[str, str]:
    """Small print. `styled` says where the cite style sits: on the name inside, or on a name at the head."""
    if styled == "inside":
        before, name, after = LONG_GUESS.partition("Lindqvist 2019")
        return paragraph(
            [
                (before, {"half_points": 10}),
                (name, {"character_style": "Style13ptBold", "half_points": 10}),
                (after, {"half_points": 10}),
            ]
        )
    text = "Okonkwo 26, " + (LONG_GUESS + " " + prose(2_100))[:4_300]
    assert len(text) > 4_000, "past the styled cite's bound, so only the hold can keep it a cite"
    return paragraph(
        [
            ("Okonkwo 26", {"character_style": "Style13ptBold", "half_points": 10}),
            (text[10:], {"half_points": 10}),
        ]
    )


class TestTheCiteStyleHold:
    def test_a_style_inside_a_long_guess_after_the_cards_cite_is_emphasis(
        self, profile: StyleProfile
    ) -> None:
        markup, text = long_guess(styled="inside")
        document = parse(DebateDocxParser(profile), tag_paragraph(), CITE_MARKUP, markup)

        card = only_card(document)
        assert (card.full_cite, card.evidence_text, card.completeness) == (CITE_TEXT, text, FULL)
        assert (
            section_of(document, text).match.rule_id
            == "assembly-cite-guess-after-card-cite:heuristic-wiki-cite-entry"
        )

    def test_a_style_inside_a_long_guess_under_a_bare_tag_is_emphasis(self, profile: StyleProfile) -> None:
        markup, text = long_guess(styled="inside")
        document = parse(DebateDocxParser(profile), tag_paragraph(), markup)

        card = only_card(document)
        assert (card.full_cite, card.evidence_text, card.completeness) == ("", text, FULL)

    @pytest.mark.parametrize("position", ["after the card's cite", "under a bare tag"])
    def test_a_style_on_a_name_and_year_at_the_head_still_holds_it(
        self, profile: StyleProfile, position: str
    ) -> None:
        markup, text = long_guess(styled="head")
        before = [CITE_MARKUP] if position == "after the card's cite" else []
        card = only_card(parse(DebateDocxParser(profile), tag_paragraph(), *before, markup))

        assert card.full_cite.endswith(text)
        assert card.completeness is CITE_ONLY


# --------------------------------------------------------------------------------------------
# (6) A short cite written with U+2018 before its year
# --------------------------------------------------------------------------------------------

LEFT_QUOTE = "‘"
RIGHT_QUOTE = "’"


def short_cite_line(quote: str, *, bold_heading: bool = False) -> tuple[str, str]:
    """`Okonkwo ‘26` alone on its line, in the cite style or, with `bold_heading`, bold at 13 pt."""
    text = f"Okonkwo {quote}26"
    formatting: dict[str, Any] = (
        {"bold": True, "half_points": CITE_SIZE} if bold_heading else {"character_style": "Style13ptBold"}
    )
    return paragraph([(text, formatting)])


BRACKETED_CITE, BRACKETED_TEXT = paragraph(
    [(f"[Adaeze Okonkwo 2026, {qualifications(300)}, {SOURCE}] KR", {})]
)


class TestAShortCiteWithALeftQuote:
    @pytest.mark.parametrize("quote", [LEFT_QUOTE, RIGHT_QUOTE, "'"], ids=["U+2018", "U+2019", "straight"])
    def test_the_short_cite_is_read_from_the_line_above_a_bracketed_cite(
        self, profile: StyleProfile, quote: str
    ) -> None:
        markup, text = short_cite_line(quote)
        card = only_card(parse(DebateDocxParser(profile), tag_paragraph(), markup, BRACKETED_CITE, BODY))

        assert card.short_cite == text
        assert card.full_cite == text + "\n" + BRACKETED_TEXT
        assert (card.tag, card.evidence_text) == (TAG, BODY_TEXT)

    def test_bold_at_13_pt_it_is_a_cite_line_and_not_a_tag(self, profile: StyleProfile) -> None:
        markup, text = short_cite_line(LEFT_QUOTE, bold_heading=True)
        document = parse(DebateDocxParser(profile), tag_paragraph(), markup, BRACKETED_CITE, BODY)

        card = only_card(document)
        assert (card.tag, card.short_cite) == (TAG, text)
        assert section_of(document, text).match.rule_id == "heuristic-cite-line-author-year"

    def test_the_text_keeps_its_left_quote(self, profile: StyleProfile) -> None:
        markup, _ = short_cite_line(LEFT_QUOTE)
        card = only_card(parse(DebateDocxParser(profile), tag_paragraph(), markup, BRACKETED_CITE, BODY))

        assert card.short_cite is not None
        assert LEFT_QUOTE in card.short_cite and LEFT_QUOTE in card.full_cite
        assert RIGHT_QUOTE not in card.full_cite

    def test_a_name_and_year_inside_a_line_is_found_with_it(self, profile: StyleProfile) -> None:
        """The long cite line's bold opening asks for a name and a year at the front, as written."""
        markup, text = paragraph(
            [(f"Okonkwo {LEFT_QUOTE}26", {"bold": True}), (", " + qualifications(600), {})]
        )
        section = section_of(parse(DebateDocxParser(profile), tag_paragraph(), markup, BODY), text)

        assert (section.unit, section.match.rule_id) == (CITE, "heuristic-cite-line-bold-author-year")

    def test_a_left_quote_inside_a_name_is_left_as_it_is(self, profile: StyleProfile) -> None:
        """Only a left quote before a digit is read as an apostrophe: `O‘Brien` is not `O’Brien`."""
        markup, _ = paragraph([(f"O{LEFT_QUOTE}Brien 26", {"character_style": "Style13ptBold"})])
        card = only_card(parse(DebateDocxParser(profile), tag_paragraph(), markup, BRACKETED_CITE, BODY))

        assert card.short_cite is None

    def test_the_wiki_guess_finds_its_year_behind_one(self, profile: StyleProfile) -> None:
        described = ParagraphDescription(
            runs=(RunDescription(text=f"Reserve margins narrowed … as Okonkwo {LEFT_QUOTE}26 had warned."),)
        )

        assert classify_paragraph(described, profile).rule_id == "heuristic-wiki-cite-entry"

    def test_a_left_quote_not_before_a_year_changes_nothing(self, profile: StyleProfile) -> None:
        markup, _ = paragraph([(f"Okonkwo {LEFT_QUOTE}twenty-six", {"character_style": "Style13ptBold"})])
        card = only_card(parse(DebateDocxParser(profile), tag_paragraph(), markup, BRACKETED_CITE, BODY))

        assert card.short_cite is None


# --------------------------------------------------------------------------------------------
# The parser version
# --------------------------------------------------------------------------------------------

#: The version directory the 2026-10-16 re-parse wrote, under `v1-e31-t12`'s rules, and the version
#: `v1-e31-t15` bumped to before this task.
THIRD_CORPUS_PARSE_VERSION = "2026.10.12-docx-3"
ZIP_GUARD_VERSION = "2026.10.18-docx-4"


class TestTheParserVersion:
    def test_it_is_the_version_this_task_bumped_to_or_a_later_one(self) -> None:
        """The output changes, so the stored cards must say which reading made them.

        `2026.10.18-docx-5`, or one a later task bumped to (`v1-e31-t24`: `2026.10.20-docx-6`).
        """
        assert parse_version_directory(DOCX_PARSER_VERSION) >= parse_version_directory("2026.10.18-docx-5")

    def test_its_directory_sorts_after_the_last_corpus_parses(self) -> None:
        """The newest version directory is the one a reader takes."""
        names = sorted(
            [DOCX_PARSER_VERSION, ZIP_GUARD_VERSION, THIRD_CORPUS_PARSE_VERSION], key=parse_version_directory
        )
        assert names == [THIRD_CORPUS_PARSE_VERSION, ZIP_GUARD_VERSION, DOCX_PARSER_VERSION]

    def test_every_card_names_it(self, parser: DebateDocxParser) -> None:
        card = only_card(parse(parser, tag_paragraph(), CITE_MARKUP, BODY))

        assert card.provenance.parser_version == DOCX_PARSER_VERSION

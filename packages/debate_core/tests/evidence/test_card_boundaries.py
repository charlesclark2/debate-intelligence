"""Long bodies and bodies holding two cards, described in counts (`v1-e31-t22`).

Every file is built in memory from invented text, and every expectation is written by hand from
what each paragraph was written to be (working agreement 6). Bodies for the containment tests are
numbered words, so which body holds which can be read off the numbers.
"""

from __future__ import annotations

from datetime import date

import pytest
from tests.evals.parser.cite_shapes import CITE_SIZE, READING_SIZE, SMALL_PRINT, SOURCE, prose

from debate_core.domain.caselist import SourceDocument, SourceFormat, SourceOrigin
from debate_core.domain.debate_files import ParsedCard, ParsedDocument
from debate_core.domain.style_profile import StyleProfile
from debate_core.evidence.card_boundaries import (
    Ending,
    Holding,
    LongBody,
    LongBodyKind,
    bodies_holding_two_cards,
    is_cite_shaped,
    is_too_long_to_be_one_card,
    read_long_body,
    rule_family,
    tally_holdings,
    tally_long_bodies,
    word_count,
)
from debate_core.evidence.near_duplicates import CutIndex
from debate_core.evidence.style_profile_loader import load_style_profile
from debate_core.integrations.docx_parser.parser import DebateDocxParser
from debate_core.testing.docx_builder import build_docx, paragraph_xml, run_xml

PROFILE: StyleProfile = load_style_profile()
SNAPSHOT = date(2026, 10, 19)


def parse(*paragraphs: str) -> ParsedDocument:
    source = SourceDocument(
        sha256="a" * 64,
        byte_size=1_000,
        source_format=SourceFormat.DOCX,
        origin=SourceOrigin.CASELIST_ARCHIVE,
        caselist="testcl26",
        first_seen_snapshot=SNAPSHOT,
        last_seen_snapshot=SNAPSHOT,
    )
    document = DebateDocxParser(PROFILE).parse(
        build_docx("".join(paragraphs)), source, source_path="invented.docx"
    )
    assert isinstance(document, ParsedDocument), document
    return document


def para(text: str, *, style: str | None = None, **formatting: object) -> str:
    return paragraph_xml(run_xml(text, **formatting), style=style)  # type: ignore[arg-type]


def tag(text: str) -> str:
    return para(text, style="Heading4")


def cite(name: str = "Okonkwo 26") -> str:
    """A cite as a file with no cite style writes it: the name and year in bold, then the source."""
    return paragraph_xml(
        run_xml(name, bold=True, half_points=CITE_SIZE)
        + run_xml(f", Adaeze Okonkwo, invented for this test, {SOURCE}", half_points=READING_SIZE)
    )


def underlined_body(characters: int = 600) -> str:
    """A card's text, underlined in small print: read as body by its markup."""
    return para(prose(characters), underline="single", half_points=SMALL_PRINT)


def plain_prose(characters: int = 600) -> str:
    """Prose at reading size with nothing marked: read as body because it is prose."""
    return para(prose(characters), half_points=READING_SIZE)


def highlighted_cite_line(name: str = "Lindqvist 2019") -> str:
    """A line that names its source at its head, highlighted as a body is: the cite guess an open
    body keeps for itself."""
    return para(f"{name}, invented review of grid planning, {SOURCE}", highlight="yellow")


def short_plain_line(text: str = "Reserve margins fall in every region") -> str:
    """A tag typed in body style: short, plain, no sentence end. Read as nothing."""
    return para(text, half_points=READING_SIZE)


def only_card(document: ParsedDocument) -> ParsedCard:
    assert len(document.cards) == 1, [card.provenance for card in document.cards]
    return document.cards[0]


def first_card(document: ParsedDocument) -> ParsedCard:
    return min(document.cards, key=lambda card: card.provenance.first_element_index)


# ------------------------------------------------------------------------------------------------
# What a paragraph looks like
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "shaped"),
    [
        ("Okonkwo 26, Adaeze Okonkwo, professor of energy policy", True),
        ("Okonkwo and Ferreira 2025, a review of four markets", True),
        ("[Okonkwo 26, Adaeze Okonkwo, professor of energy policy] KR", True),
        ("Dr. Adaeze Okonkwo 26, professor of energy policy", True),
        # The name and year start 40 characters in: still the head.
        ("x" * 39 + " Okonkwo 26, a review", True),
        # 41 characters in: a sentence that mentions a source.
        ("x" * 40 + " Okonkwo 26, a review", False),
        ("In 2019 the grid operator raised its forecast", False),
        ("Reserve margins fall in every region", False),
        ("", False),
        # Longer than any cite line the classifier reads.
        ("Okonkwo 26, " + "q" * 1_989, False),
        ("Okonkwo 26, " + "q" * 1_988, True),
    ],
)
def test_a_cite_shaped_paragraph_names_its_source_at_its_head(text: str, shaped: bool) -> None:
    assert is_cite_shaped(text, PROFILE) is shaped


def test_a_rule_is_named_by_its_family_alone() -> None:
    assert (
        rule_family("heuristic-prose-paragraph:verbatim-alias-id:Invented Style")
        == "heuristic-prose-paragraph"
    )
    assert rule_family("assembly-cite-guess-inside-card-body:heuristic-cite-line-author-year") == (
        "assembly-cite-guess-inside-card-body"
    )
    assert rule_family("heuristic-marked-up-body-text") == "heuristic-marked-up-body-text"


def test_a_body_of_3000_words_is_one_card_and_of_3001_too_long_to_be_one() -> None:
    assert is_too_long_to_be_one_card(3_000) is False
    assert is_too_long_to_be_one_card(3_001) is True


def test_words_are_runs_between_whitespace() -> None:
    assert word_count("  one two\nthree\tfour  ") == 4
    assert word_count("") == 0


# ------------------------------------------------------------------------------------------------
# What ended a card
# ------------------------------------------------------------------------------------------------


def ending_of(*after: str) -> Ending:
    """The ending of a card of a tag, a cite and a body, with `after` behind it."""
    document = parse(tag("First tag"), cite(), underlined_body(), *after)
    return read_long_body(document, first_card(document), PROFILE).ending


def test_a_card_followed_by_another_cards_tag_was_ended_by_it() -> None:
    assert ending_of(tag("Second tag"), cite(), underlined_body()) is Ending.TAG_IN_A_DEBATE_STYLE


def test_a_tag_the_classifier_guessed_from_bold_at_a_tag_size_is_told_apart() -> None:
    bold_line = para("Second tag in bold at a tag size", bold=True, half_points=26)
    assert ending_of(bold_line, cite(), underlined_body()) is Ending.TAG_GUESSED


def test_a_pocket_hat_or_block_heading_ends_a_card() -> None:
    assert ending_of(para("A block", style="Heading3")) is Ending.SECTION_HEADING
    assert ending_of(para("A hat", style="Heading2")) is Ending.SECTION_HEADING


def test_an_analytic_and_a_tag_with_nothing_under_it_are_told_apart() -> None:
    assert ending_of(para("An analytic line of argument", style="Analytic")) is Ending.ANALYTIC
    assert (
        ending_of(tag("A tag with nothing under it"), para("A block", style="Heading3"))
        is Ending.TAG_WITH_NOTHING_UNDER_IT
    )


def test_a_cite_after_the_body_ends_the_card_and_starts_one_with_no_tag() -> None:
    assert ending_of(cite("Ferreira 25"), underlined_body()) is Ending.CITE


def test_a_card_at_the_end_of_its_file_was_ended_by_the_end() -> None:
    assert ending_of() is Ending.END_OF_FILE


def test_blank_lines_and_lines_read_as_nothing_are_stepped_over() -> None:
    blank_heading = para("", style="Heading4")
    assert ending_of(blank_heading, short_plain_line(), para("A block", style="Heading3")) is (
        Ending.SECTION_HEADING
    )
    assert ending_of(short_plain_line()) is Ending.END_OF_FILE


# ------------------------------------------------------------------------------------------------
# What a file writes
# ------------------------------------------------------------------------------------------------


def described(*paragraphs: str) -> LongBody:
    document = parse(*paragraphs)
    return read_long_body(document, first_card(document), PROFILE)


def test_a_file_with_a_tag_style_writes_tags_and_uses_debate_styles() -> None:
    body = described(tag("First tag"), cite(), underlined_body())
    assert body.file_writes_tags is True
    assert body.file_uses_debate_styles is True
    assert body.has_tag is True
    assert body.has_cite is True


def test_a_card_of_a_tag_and_a_body_has_no_cite() -> None:
    body = described(tag("First tag"), underlined_body())
    assert body.has_tag is True
    assert body.has_cite is False


def test_a_file_of_cites_and_bodies_writes_no_tags_and_uses_no_debate_style() -> None:
    body = described(cite(), plain_prose(), cite("Ferreira 25"), plain_prose())
    assert body.file_writes_tags is False
    assert body.file_uses_debate_styles is False
    assert body.has_tag is False
    assert body.has_cite is True
    assert body.cards_in_file == 2


def test_a_style_that_maps_to_no_unit_is_no_debate_style() -> None:
    body = described(
        para("Okonkwo 26, Adaeze Okonkwo, invented for this test", style="Normal", bold=True),
        para(prose(600), style="Normal", underline="single"),
        # A line no rule sees through the style takes: the style's own `OTHER`, matched by name.
        para("A line in Normal", style="Normal"),
    )
    assert body.file_uses_debate_styles is False


def test_a_tag_guessed_from_bold_writes_tags_without_a_debate_style() -> None:
    body = described(
        para("A tag in bold at a tag size", bold=True, half_points=26), cite(), underlined_body()
    )
    assert body.file_writes_tags is True
    assert body.file_uses_debate_styles is False


def test_a_tag_demoted_for_having_nothing_under_it_still_says_the_file_writes_tags() -> None:
    body = described(
        cite(), underlined_body(), para("A tag with nothing under it", bold=True, half_points=26)
    )
    assert body.file_writes_tags is True
    assert body.file_uses_debate_styles is False


def test_a_blank_heading_still_says_the_file_uses_the_style() -> None:
    body = described(para("", style="Heading4"), cite(), plain_prose())
    assert body.file_writes_tags is False
    assert body.file_uses_debate_styles is True


def test_a_cite_in_the_cite_character_style_is_a_debate_style() -> None:
    body = described(
        paragraph_xml(
            run_xml("Okonkwo 26", character_style="Style13ptBold") + run_xml(f", invented, {SOURCE}")
        ),
        plain_prose(),
    )
    assert body.file_uses_debate_styles is True


# ------------------------------------------------------------------------------------------------
# What is inside a long body
# ------------------------------------------------------------------------------------------------


def test_a_tag_typed_in_body_style_above_a_cite_the_body_kept_is_a_line_above_a_cite() -> None:
    body = described(
        tag("First tag"),
        cite(),
        underlined_body(),
        short_plain_line(),
        highlighted_cite_line(),
        underlined_body(),
    )
    assert body.cite_shaped_paragraphs == 1
    assert body.short_lines_above_a_cite == 1
    assert body.cite_shaped_rules == ("assembly-cite-guess-inside-card-body",)
    assert body.kind is LongBodyKind.LINE_ABOVE_A_CITE_INSIDE
    # The line read as nothing is no paragraph of the body; the cite line the body kept is.
    assert body.paragraphs == 3
    assert body.ending is Ending.END_OF_FILE


def test_a_cite_the_body_kept_straight_after_a_body_paragraph_is_a_cite_inside() -> None:
    body = described(tag("First tag"), cite(), underlined_body(), highlighted_cite_line(), underlined_body())
    assert body.cite_shaped_paragraphs == 1
    assert body.short_lines_above_a_cite == 0
    assert body.kind is LongBodyKind.CITE_INSIDE


def test_a_long_line_above_a_cite_is_no_tag() -> None:
    long_line = short_plain_line("x" * 301)
    body = described(
        tag("First tag"), cite(), underlined_body(), long_line, highlighted_cite_line(), underlined_body()
    )
    assert body.short_lines_above_a_cite == 0
    assert body.kind is LongBodyKind.CITE_INSIDE


def test_a_line_of_a_headings_length_above_a_cite_is_where_a_tag_would_be() -> None:
    body = described(
        tag("First tag"),
        cite(),
        underlined_body(),
        short_plain_line("x" * 300),
        highlighted_cite_line(),
        underlined_body(),
    )
    assert body.short_lines_above_a_cite == 1


def test_a_blank_line_above_a_cite_is_no_tag() -> None:
    body = described(
        tag("First tag"),
        cite(),
        underlined_body(),
        para("", half_points=READING_SIZE),
        highlighted_cite_line(),
        underlined_body(),
    )
    assert body.cite_shaped_paragraphs == 1
    assert body.short_lines_above_a_cite == 0


def test_a_table_cell_above_a_cite_is_page_furniture_and_no_tag() -> None:
    table = f"<w:tbl><w:tr><w:tc>{short_plain_line('Speech times')}</w:tc></w:tr></w:tbl>"
    body = described(
        tag("First tag"), cite(), underlined_body(), table, highlighted_cite_line(), underlined_body()
    )
    assert body.cite_shaped_paragraphs == 1
    assert body.short_lines_above_a_cite == 0


def test_a_cite_shaped_line_above_a_cite_is_no_tag() -> None:
    body = described(
        tag("First tag"),
        cite(),
        underlined_body(),
        highlighted_cite_line("Ferreira 2025"),
        highlighted_cite_line(),
        underlined_body(),
    )
    assert body.cite_shaped_paragraphs == 2
    assert body.short_lines_above_a_cite == 0


def test_a_cite_shaped_line_read_as_nothing_counts_and_names_its_rule() -> None:
    # 400 characters and more with no bold and no bracket: no cite line; no sentence end: no prose.
    unread = para("Okonkwo 26, " + "invented credentials " * 20 + "and more", half_points=READING_SIZE)
    body = described(
        tag("First tag"), cite(), underlined_body(), short_plain_line(), unread, underlined_body()
    )
    assert body.cite_shaped_rules == ("heuristic-unclassified-paragraph",)
    assert body.short_lines_above_a_cite == 1


def test_the_cards_own_cite_read_as_its_first_body_paragraph_is_not_inside() -> None:
    # Before the body has begun, a cite-shaped paragraph is the card's own unread cite, not a
    # boundary: v1-e31-t19's question, not this one.
    unread_cite = para("Okonkwo 26, " + "invented credentials " * 20 + "and more", half_points=READING_SIZE)
    body = described(tag("First tag"), unread_cite, underlined_body(), underlined_body())
    assert body.cite_shaped_paragraphs == 0
    assert body.kind is LongBodyKind.MARKED_UP_WITHOUT_A_CITE_INSIDE


def test_a_body_with_no_cite_inside_is_marked_up_or_plain_prose_by_its_underlining() -> None:
    marked = described(tag("First tag"), cite(), underlined_body())
    plain = described(cite(), plain_prose(), plain_prose(), plain_prose())
    # One paragraph: the line break between two belongs to no span, and is not underlined.
    assert marked.marked_up_share == 1.0
    assert marked.kind is LongBodyKind.MARKED_UP_WITHOUT_A_CITE_INSIDE
    assert plain.marked_up_share == 0.0
    assert plain.kind is LongBodyKind.PLAIN_PROSE
    assert plain.paragraphs == 3


def test_a_body_a_twentieth_underlined_is_marked_up_and_less_is_prose() -> None:
    def underlined_share(underlined: int) -> LongBody:
        text = prose(2_000)[:2_000]
        return described(
            cite(),
            paragraph_xml(
                run_xml(text[:underlined], underline="single", half_points=READING_SIZE)
                + run_xml(text[underlined:], half_points=READING_SIZE)
            ),
        )

    assert underlined_share(100).marked_up_share == 0.05
    assert underlined_share(100).kind is LongBodyKind.MARKED_UP_WITHOUT_A_CITE_INSIDE
    assert underlined_share(99).kind is LongBodyKind.PLAIN_PROSE


def test_highlighting_counts_as_marking_up_and_bold_does_not() -> None:
    text = prose(1_000)[:1_000]
    highlighted = described(cite(), para(text, highlight="yellow"))
    bold = described(cite(), para(text, bold=True, half_points=SMALL_PRINT))
    assert highlighted.marked_up_share == 1.0
    assert bold.marked_up_share == 0.0


def test_the_words_are_the_cards_body_words() -> None:
    document = parse(cite(), plain_prose(600))
    card = only_card(document)
    assert read_long_body(document, card, PROFILE).words == len(card.evidence_text.split())


# ------------------------------------------------------------------------------------------------
# Bodies holding two cards
# ------------------------------------------------------------------------------------------------


def words(stem: str, count: int, start: int = 0) -> list[str]:
    return [f"{stem}{number}" for number in range(start, start + count)]


def text(*parts: list[str]) -> str:
    return " ".join(word for part in parts for word in part)


FIRST = words("first", 80)
SECOND = words("second", 80)
THIRD = words("third", 70)
#: One run of 100 words, and two cuts of it sharing 20 words: under three-tenths of either.
RUN = words("run", 100)
#: Another run of 100, and two cuts sharing 40 words: more than three-tenths.
WIDE = words("wide", 100)


def index_of(**bodies: str) -> CutIndex:
    return CutIndex(bodies)


def test_a_body_holding_two_bodies_that_share_nothing_holds_two_cards() -> None:
    index = index_of(holder=text(FIRST, SECOND), first=text(FIRST), second=text(SECOND))
    assert bodies_holding_two_cards(index) == [
        Holding(
            holder="holder",
            held=("first", "second"),
            pair_sharing_nothing=("first", "second"),
            pair_not_overlapping=("first", "second"),
            sharing_nothing=2,
        )
    ]


def test_three_bodies_sharing_nothing_are_counted_as_three() -> None:
    index = index_of(
        holder=text(FIRST, SECOND, THIRD), first=text(FIRST), second=text(SECOND), third=text(THIRD)
    )
    [holding] = bodies_holding_two_cards(index)
    assert holding.sharing_nothing == 3
    # Of the pairs, the one whose smaller body is largest: 80 and 80 words, over 70.
    assert holding.pair_sharing_nothing == ("first", "second")


def test_two_cuts_that_share_a_little_do_not_overlap_but_do_not_share_nothing() -> None:
    index = index_of(holder=text(RUN), early=text(RUN[:60]), late=text(RUN[40:]))
    assert bodies_holding_two_cards(index) == [
        Holding(
            holder="holder",
            held=("early", "late"),
            pair_sharing_nothing=None,
            pair_not_overlapping=("early", "late"),
            sharing_nothing=0,
        )
    ]


def test_two_cuts_that_overlap_are_one_card_cut_twice_and_not_counted() -> None:
    index = index_of(holder=text(WIDE), early=text(WIDE[:70]), late=text(WIDE[30:]))
    assert bodies_holding_two_cards(index) == []


def test_a_body_holding_one_body_is_not_counted() -> None:
    index = index_of(holder=text(FIRST, SECOND), first=text(FIRST), elsewhere=text(THIRD))
    assert bodies_holding_two_cards(index) == []


def test_a_copy_is_not_held_and_holds_the_same_two_cards() -> None:
    changed = [*FIRST, *SECOND]
    changed[80] = "changed"
    index = index_of(
        holder=text(FIRST, SECOND), copy=" ".join(changed), first=text(FIRST), second=text(SECOND[1:])
    )
    holdings = bodies_holding_two_cards(index)
    assert [holding.holder for holding in holdings] == ["copy", "holder"]
    assert [holding.held for holding in holdings] == [("second", "first"), ("second", "first")]


def test_a_body_held_inside_a_held_body_still_makes_two_cards_with_its_neighbour() -> None:
    # The holder is nearly all `big`, which holds `first` and `second`: a pair sharing nothing in
    # the holder although `big`, picked first by size, overlaps both.
    big = text(FIRST, SECOND)
    index = index_of(holder=big + " one more", big=big, first=text(FIRST), second=text(SECOND))
    holdings = {holding.holder: holding for holding in bodies_holding_two_cards(index)}
    assert sorted(holdings) == ["big", "holder"]
    assert holdings["holder"].pair_sharing_nothing == ("first", "second")
    assert holdings["holder"].sharing_nothing == 2


# ------------------------------------------------------------------------------------------------
# Tallies
# ------------------------------------------------------------------------------------------------


def long_body(**changes: object) -> LongBody:
    values: dict[str, object] = {
        "words": 4_000,
        "ending": Ending.TAG_IN_A_DEBATE_STYLE,
        "file_writes_tags": True,
        "file_uses_debate_styles": True,
        "has_tag": True,
        "has_cite": True,
        "cards_in_file": 30,
        "paragraphs": 12,
        "cite_shaped_paragraphs": 0,
        "short_lines_above_a_cite": 0,
        "marked_up_share": 0.4,
        "cite_shaped_rules": (),
    }
    values.update(changes)
    return LongBody(**values)  # type: ignore[arg-type]


def test_long_bodies_are_tallied_by_ending_tags_kind_and_bands() -> None:
    tally = tally_long_bodies(
        [
            long_body(),
            long_body(
                words=12_000,
                ending=Ending.END_OF_FILE,
                file_writes_tags=False,
                file_uses_debate_styles=False,
                has_tag=False,
                cards_in_file=1,
                marked_up_share=0.0,
            ),
            long_body(
                words=5_001,
                cite_shaped_paragraphs=2,
                short_lines_above_a_cite=1,
                cite_shaped_rules=("assembly-cite-guess-inside-card-body", "heuristic-prose-paragraph"),
                marked_up_share=0.01,
                cards_in_file=2,
            ),
            long_body(marked_up_share=0.005, cards_in_file=21),
        ]
    )
    assert tally == {
        "cards": 4,
        "by_cards_in_file": {"1": 1, "2 to 5": 1, "21 or more": 2},
        "by_ending": {"a tag in a debate style": 3, "the end of the file": 1},
        "by_ending_and_file_writing_tags": {
            "a tag in a debate style | file writes tags: yes": 3,
            "the end of the file | file writes tags: no": 1,
        },
        "by_file_using_debate_styles": {"no": 1, "yes": 3},
        "by_file_writing_tags": {"file writes tags: no": 1, "file writes tags: yes": 3},
        "by_kind": {
            "a short line above a cite-shaped paragraph inside": 1,
            "no cite inside, marked up": 1,
            "no cite inside, plain prose": 2,
        },
        "by_kind_and_file_styles": {
            "a short line above a cite-shaped paragraph inside | debate styles: yes": 1,
            "no cite inside, marked up | debate styles: yes": 1,
            "no cite inside, plain prose | debate styles: no": 1,
            "no cite inside, plain prose | debate styles: yes": 1,
        },
        "by_marked_up_share": {"5% or more": 1, "none": 1, "under 5%": 2},
        "by_tag_and_cite": {"tag: no | cite: yes": 1, "tag: yes | cite: yes": 3},
        "by_words": {"10,001 or more": 1, "3,001 to 5,000": 2, "5,001 to 10,000": 1},
        "cite_shaped_paragraphs_by_rule": {
            "assembly-cite-guess-inside-card-body": 1,
            "heuristic-prose-paragraph": 1,
        },
    }


def test_no_long_bodies_tally_to_nothing() -> None:
    assert tally_long_bodies([]) == {"cards": 0}


@pytest.mark.parametrize(
    ("words_each", "band"), [(64, "long (64 words or more)"), (63, "short (under 64 words)")]
)
def test_the_smaller_of_two_cards_is_short_under_64_words(words_each: int, band: str) -> None:
    one, two = words("one", words_each), words("two", words_each)
    index = index_of(holder=text(one, two), one=text(one), two=text(two))
    tally = tally_holdings(bodies_holding_two_cards(index), index, cards_by_fingerprint={"holder": 1})
    assert tally["by_smaller_of_the_two"] == {band: 1}


def test_holdings_are_tallied_in_texts_and_in_the_cards_that_carry_them() -> None:
    short_one, short_two = words("shortone", 30), words("shorttwo", 30)
    index = index_of(
        holder=text(FIRST, SECOND),
        first=text(FIRST),
        second=text(SECOND),
        small=text(short_one, short_two),
        one=text(short_one),
        two=text(short_two),
        cut=text(RUN),
        early=text(RUN[:60]),
        late=text(RUN[40:]),
    )
    tally = tally_holdings(
        bodies_holding_two_cards(index),
        index,
        cards_by_fingerprint={"holder": 3, "small": 1, "cut": 5},
        long_bodies=frozenset({"small"}),
    )
    assert tally == {
        "full_texts": 9,
        "holding_two_sharing_nothing_texts": 2,
        "holding_two_sharing_nothing_cards": 4,
        "holding_two_not_overlapping_texts": 3,
        "by_bodies_sharing_nothing": {"2": 2},
        "by_holder_over_the_long_body_line": {"no": 1, "yes": 1},
        "by_holder_words": {"0 to 299": 2},
        "by_smaller_of_the_two": {"long (64 words or more)": 1, "short (under 64 words)": 1},
    }

"""PDF layout rules: running headers and footers, page numbers, de-hyphenation, paragraphs (v1-e04-t04 ac3).

The rules are the PM's rulings of 2026-10-25 on the session's proposal
(docs/session-reports/v1-e04-t04-content-extraction.md):

* **De-hyphenation.** A soft hyphen is dropped; a hyphen not between two letters is kept; between
  letters, the word's spellings elsewhere in the body decide, compared case-insensitively and counting
  only spellings that are not themselves split at a line end; when neither or both appear, the
  hyphen is kept and the join is UNDETERMINED. Lines are joined at a hyphen with no space, and every
  join is recorded.
* **Headers and footers.** Only the three lines nearest each end of a page are candidates. A line
  goes when its exact text repeats there on two or more pages, or when its whole text is a
  page-number form whose number advances with the page by a constant offset on two or more pages.
  Anything else stays, however short.

Each test builds pages by hand: body lines 14 pt apart from y = 730, 10 pt type at x = 72, a header
at y = 760 and footers at y = 52 and 40 in 8 pt.
"""

from __future__ import annotations

from collections import Counter
from typing import Final

from hypothesis import event, given, settings
from hypothesis import strategies as st
from tests.fixtures.extraction.build_pdf_fixtures import journal_article_pages
from tests.fixtures.extraction.expected_output import join_mismatches, load_expected, removed_line_rows

from debate_core.retrieval.extraction import JoinDecision, LineJoin, PageEdge, RemovalReason
from debate_core.retrieval.pdf_layout import PdfPageText, PdfTextLayout, PositionedLine, lay_out_pages

LEFT: Final = 72.0
INDENT: Final = 90.0


def line(text: str, y: float, *, x: float = LEFT, size: float = 10.0) -> PositionedLine:
    return PositionedLine(text=text, x=x, y=y, font_size=size)


def page(
    number: int, *body: str, header: str | None = None, footers: tuple[str, ...] = (), top: float = 730.0
) -> PdfPageText:
    """A page: an optional header, body lines 14 pt apart, then footers from y = 52 down."""
    lines: list[PositionedLine] = []
    if header is not None:
        lines.append(line(header, 760.0, size=8.0))
    lines += [line(text, top - 14.0 * index) for index, text in enumerate(body)]
    lines += [line(text, 52.0 - 12.0 * index, size=8.0) for index, text in enumerate(footers)]
    return PdfPageText(page_number=number, lines=tuple(lines))


def one_paragraph(*texts: str) -> PdfTextLayout:
    return lay_out_pages([page(1, *texts)])


def removed(layout: PdfTextLayout) -> list[tuple[int, PageEdge, RemovalReason, str]]:
    return [(item.page_number, item.edge, item.reason, item.text) for item in layout.removed_lines]


def only_join(layout: PdfTextLayout) -> LineJoin:
    assert len(layout.line_joins) == 1, layout.line_joins
    return layout.line_joins[0]


def body(number: int) -> tuple[str, ...]:
    """Four body lines unique to page `number`, so none of them repeats on another page."""
    return tuple(f"Body line {word} on page {number}." for word in ("one", "two", "three", "four"))


# --------------------------------------------------------------------------------------------
# Running headers and footers
# --------------------------------------------------------------------------------------------


def test_a_line_repeated_at_the_top_of_two_pages_is_a_running_header_and_is_recorded() -> None:
    layout = lay_out_pages(
        [
            page(1, *body(1)),
            page(2, *body(2), header="Journal of Tests"),
            page(3, *body(3), header="Journal of Tests"),
        ]
    )
    assert removed(layout) == [
        (2, PageEdge.TOP, RemovalReason.RUNNING_HEADER, "Journal of Tests"),
        (3, PageEdge.TOP, RemovalReason.RUNNING_HEADER, "Journal of Tests"),
    ]
    assert not any("Journal of Tests" in paragraph for paragraph in layout.paragraphs)
    assert layout.removed_characters == 2 * len("Journal of Tests")


def test_a_line_repeated_at_the_bottom_of_two_pages_is_a_running_footer() -> None:
    layout = lay_out_pages(
        [page(1, *body(1), footers=("CC BY 4.0",)), page(2, *body(2), footers=("CC BY 4.0",))]
    )
    assert removed(layout) == [
        (1, PageEdge.BOTTOM, RemovalReason.RUNNING_FOOTER, "CC BY 4.0"),
        (2, PageEdge.BOTTOM, RemovalReason.RUNNING_FOOTER, "CC BY 4.0"),
    ]


def test_running_lines_match_with_their_whitespace_collapsed() -> None:
    layout = lay_out_pages(
        [page(1, *body(1), header="Journal  of Tests"), page(2, *body(2), header="Journal of Tests ")]
    )
    assert [item.reason for item in layout.removed_lines] == [RemovalReason.RUNNING_HEADER] * 2


def test_a_short_line_that_appears_once_in_an_edge_zone_is_body_text() -> None:
    layout = lay_out_pages(
        [
            page(1, "Notes", *body(1), header="Journal of Tests", footers=("CC BY 4.0",)),
            page(2, *body(2), "2", header="Journal of Tests", footers=("CC BY 4.0",)),
        ]
    )
    assert [item.text for item in layout.removed_lines] == ["Journal of Tests", "CC BY 4.0"] * 2
    assert "Notes" in layout.paragraphs[0]
    assert layout.paragraphs[-1].endswith("Body line four on page 2. 2")


def test_a_line_repeated_outside_the_edge_zones_stays() -> None:
    def seven(number: int) -> tuple[str, ...]:
        first, last = body(number)[:3], tuple(text.replace("page", "sheet") for text in body(number)[:3])
        return (*first, "Repeated line.", *last)

    layout = lay_out_pages([page(1, *seven(1)), page(2, *seven(2))])
    assert layout.removed_lines == ()
    assert sum(paragraph.count("Repeated line.") for paragraph in layout.paragraphs) == 2


# --------------------------------------------------------------------------------------------
# Page numbers
# --------------------------------------------------------------------------------------------


def numbered_pages(form: str, first: int = 1) -> list[PdfPageText]:
    return [page(number, *body(number), footers=(form.format(n=number + first - 1),)) for number in (1, 2, 3)]


def test_page_numbers_in_each_form_are_removed() -> None:
    for form in (
        "{n}",
        "Page {n}",
        "page {n}",
        "PAGE {n}",
        "{n} of 9",
        "Page {n} of 9",
        "- {n} -",
        "– {n} –",
    ):
        layout = lay_out_pages(numbered_pages(form, first=11))
        assert [item.reason for item in layout.removed_lines] == [RemovalReason.PAGE_NUMBER] * 3, form
        assert [item.edge for item in layout.removed_lines] == [PageEdge.BOTTOM] * 3, form


def test_lowercase_roman_page_numbers_are_removed() -> None:
    pages = [
        page(number, *body(number), footers=(numeral,))
        for number, numeral in ((1, "iv"), (2, "v"), (3, "vi"))
    ]
    assert [item.text for item in lay_out_pages(pages).removed_lines] == ["iv", "v", "vi"]


def test_a_page_number_at_the_top_is_removed_from_the_top() -> None:
    pages = [page(number, *body(number), header=str(number + 100)) for number in (1, 2)]
    assert removed(lay_out_pages(pages)) == [
        (1, PageEdge.TOP, RemovalReason.PAGE_NUMBER, "101"),
        (2, PageEdge.TOP, RemovalReason.PAGE_NUMBER, "102"),
    ]


def test_numbers_that_do_not_advance_with_the_page_stay() -> None:
    pages = [
        page(1, *body(1), footers=("5",)),
        page(2, *body(2), footers=("9",)),
        page(3, *body(3), footers=("4",)),
    ]
    assert lay_out_pages(pages).removed_lines == ()


def test_only_the_pages_whose_numbers_share_an_offset_lose_them() -> None:
    pages = [
        page(1, *body(1), footers=("12",)),
        page(2, *body(2), footers=("13",)),
        page(3, *body(3), footers=("40",)),
    ]
    assert [item.text for item in lay_out_pages(pages).removed_lines] == ["12", "13"]


def test_a_one_page_document_keeps_its_lone_number() -> None:
    assert lay_out_pages([page(1, *body(1), footers=("1",))]).removed_lines == ()


def test_table_captions_on_consecutive_pages_are_not_page_numbers() -> None:
    # PM ruling 2026-10-25: only a whole-text page-number form can be a page number.
    pages = [
        page(1, *body(1)),
        page(2, "Table 2", *body(2)),
        page(3, "Table 3", *body(3)),
        page(4, *body(4), footers=("Figure 4",)),
    ]
    layout = lay_out_pages(pages)
    assert layout.removed_lines == ()
    assert any(paragraph.startswith("Table 2") for paragraph in layout.paragraphs)
    assert any(paragraph.startswith("Table 3") for paragraph in layout.paragraphs)


def test_text_around_a_number_or_an_uppercase_numeral_is_not_a_page_number_form() -> None:
    for first, second in (
        ("Chapter 2", "Chapter 3"),
        ("II", "III"),
        ("2.", "3."),
        ("p. 2", "p. 3"),
        ("2 of", "3 of"),
    ):
        pages = [page(1, *body(1)), page(2, *body(2), footers=(first,)), page(3, *body(3), footers=(second,))]
        assert lay_out_pages(pages).removed_lines == (), (first, second)


def test_a_number_that_is_not_the_outermost_line_stays_even_when_it_fits_the_sequence() -> None:
    pages = [
        page(1, *body(1), footers=("1",)),
        page(2, *body(2), "2", footers=("2",)),
        page(3, *body(3), footers=("3",)),
    ]
    layout = lay_out_pages(pages)
    assert [(item.page_number, item.text) for item in layout.removed_lines] == [(1, "1"), (2, "2"), (3, "3")]
    assert "Body line four on page 2. 2 Body line one on page 3." in layout.paragraphs[1]


def test_a_page_number_is_found_beneath_a_running_footer() -> None:
    pages = [page(number, *body(number), footers=("CC BY 4.0", f"Page {number} of 2")) for number in (1, 2)]
    assert [item.reason for item in lay_out_pages(pages).removed_lines] == [
        RemovalReason.RUNNING_FOOTER,
        RemovalReason.PAGE_NUMBER,
    ] * 2


# --------------------------------------------------------------------------------------------
# De-hyphenation
# --------------------------------------------------------------------------------------------


def test_a_broken_word_whose_joined_form_appears_elsewhere_loses_its_hyphen_and_no_space_is_added() -> None:
    layout = one_paragraph("the extinc-", "tion of species; extinction is final")
    assert layout.paragraphs == ("the extinction of species; extinction is final",)
    join = only_join(layout)
    assert (join.decision, join.hyphen_kept, join.offset, join.character) == (
        JoinDecision.JOINED_FORM_IN_DOCUMENT,
        False,
        len("the extinc"),
        "-",
    )
    assert (join.hyphenated_form_count, join.joined_form_count, join.page_number) == (0, 1, 1)


def test_a_compound_whose_hyphenated_form_appears_elsewhere_keeps_its_hyphen() -> None:
    layout = one_paragraph("a long-", "term plan and a long-term view")
    assert layout.paragraphs == ("a long-term plan and a long-term view",)
    join = only_join(layout)
    assert (join.decision, join.hyphen_kept, join.offset) == (
        JoinDecision.HYPHENATED_FORM_IN_DOCUMENT,
        True,
        6,
    )
    assert (join.hyphenated_form_count, join.joined_form_count) == (1, 0)


def test_when_neither_spelling_appears_the_hyphen_stays_and_the_join_is_undetermined() -> None:
    layout = one_paragraph("a well-", "intentioned distraction")
    assert layout.paragraphs == ("a well-intentioned distraction",)
    join = only_join(layout)
    assert (join.decision, join.hyphen_kept) == (JoinDecision.UNDETERMINED, True)
    assert (join.hyphenated_form_count, join.joined_form_count) == (0, 0)


def test_when_both_spellings_appear_the_hyphen_stays_and_the_join_is_undetermined() -> None:
    layout = one_paragraph("cooperation and co-operation; relied on co-", "operation")
    assert layout.paragraphs == ("cooperation and co-operation; relied on co-operation",)
    join = only_join(layout)
    assert (join.decision, join.hyphen_kept, join.hyphenated_form_count, join.joined_form_count) == (
        JoinDecision.UNDETERMINED,
        True,
        1,
        1,
    )


def test_spellings_elsewhere_are_compared_case_insensitively() -> None:
    hyphenated = one_paragraph("De-extinction is costly, and de-", "extinction is slow")
    assert only_join(hyphenated).decision is JoinDecision.HYPHENATED_FORM_IN_DOCUMENT
    assert hyphenated.paragraphs == ("De-extinction is costly, and de-extinction is slow",)
    joined = one_paragraph("EXTINCTION is final; extinc-", "tion is forever")
    assert only_join(joined).decision is JoinDecision.JOINED_FORM_IN_DOCUMENT
    assert joined.paragraphs == ("EXTINCTION is final; extinction is forever",)


def test_other_line_end_hyphenations_are_not_evidence_for_either_spelling() -> None:
    # PM ruling 2026-10-25: only spellings that appear mid-line count.
    compound = one_paragraph("the de-", "extinction plan, a de-", "extinction law")
    assert compound.paragraphs == ("the de-extinction plan, a de-extinction law",)
    assert [join.decision for join in compound.line_joins] == [JoinDecision.UNDETERMINED] * 2
    broken = one_paragraph("an exam-", "ple and another exam-", "ple")
    assert broken.paragraphs == ("an exam-ple and another exam-ple",)
    assert [(join.hyphenated_form_count, join.joined_form_count) for join in broken.line_joins] == [
        (0, 0)
    ] * 2


def test_a_word_that_starts_or_ends_a_line_unbroken_is_evidence() -> None:
    layout = one_paragraph("conservation is slow, but conser-", "vation works and needs", "conservation")
    assert only_join(layout).joined_form_count == 2


def test_a_left_fragment_keeps_its_own_hyphens() -> None:
    layout = one_paragraph("a state-of-the-", "art lab and a state-of-the-art plan")
    assert layout.paragraphs == ("a state-of-the-art lab and a state-of-the-art plan",)
    assert only_join(layout).decision is JoinDecision.HYPHENATED_FORM_IN_DOCUMENT


def test_a_soft_hyphen_is_dropped() -> None:
    layout = one_paragraph("the bio­", "diversity they protect")
    assert layout.paragraphs == ("the biodiversity they protect",)
    join = only_join(layout)
    assert (join.decision, join.character, join.hyphen_kept) == (JoinDecision.SOFT_HYPHEN, "­", False)


def test_a_hyphen_or_dash_not_between_two_letters_is_kept() -> None:
    for first, second, joined, character in (
        ("from 2019-", "2024 onward", "from 2019-2024 onward", "-"),
        ("rising COVID-", "19 cases", "rising COVID-19 cases", "-"),
        ("the Paris–", "London line", "the Paris–London line", "–"),
        ("a pause—", "and then more", "a pause—and then more", "—"),
        ("the word-", "“quoted”", "the word-“quoted”", "-"),
    ):
        layout = one_paragraph(first, second)
        assert layout.paragraphs == (joined,)
        join = only_join(layout)
        assert (join.decision, join.character, join.hyphen_kept) == (
            JoinDecision.NOT_A_WORD_BREAK,
            character,
            True,
        )


def test_a_dash_after_a_space_is_an_ordinary_line_break() -> None:
    layout = one_paragraph("prices rose -", "sharply")
    assert layout.paragraphs == ("prices rose - sharply",)
    assert layout.line_joins == ()


def test_a_hyphen_at_the_end_of_a_paragraph_is_not_a_join() -> None:
    lines = (
        line("A paragraph that", 730.0),
        line("ends in co-", 716.0),
        line("operation after a gap.", 686.0),
        line("It goes on.", 672.0),
    )
    layout = lay_out_pages([PdfPageText(page_number=1, lines=lines)])
    assert layout.paragraphs == ("A paragraph that ends in co-", "operation after a gap. It goes on.")
    assert layout.line_joins == ()


def test_a_word_broken_across_a_page_is_joined_and_recorded_on_the_first_page() -> None:
    pages = [
        page(
            1, "environmental law matters. Protecting habitat for the envi-", header="Running", footers=("1",)
        ),
        page(2, "ronmental future.", header="Running", footers=("2",)),
    ]
    layout = lay_out_pages(pages)
    assert layout.paragraphs == (
        "environmental law matters. Protecting habitat for the environmental future.",
    )
    join = only_join(layout)
    assert (join.decision, join.page_number, join.paragraph_index) == (
        JoinDecision.JOINED_FORM_IN_DOCUMENT,
        1,
        0,
    )


def test_join_offsets_count_from_the_start_of_their_own_paragraph() -> None:
    lines = (
        line("Heading", 730.0, size=12.0),
        line("a long-term goal and a long-", 712.0),
        line("term view", 698.0),
    )
    layout = lay_out_pages([PdfPageText(page_number=1, lines=lines)])
    assert layout.paragraphs == ("Heading", "a long-term goal and a long-term view")
    join = only_join(layout)
    assert (join.paragraph_index, join.offset) == (1, len("a long-term goal and a long"))


# --------------------------------------------------------------------------------------------
# Paragraphs
# --------------------------------------------------------------------------------------------


def test_an_indented_line_a_larger_gap_or_a_new_type_size_starts_a_paragraph() -> None:
    lines = (
        line("First paragraph opens", 730.0, x=INDENT),
        line("and continues.", 716.0),
        line("Second opens indented", 702.0, x=INDENT),
        line("and continues.", 688.0),
        line("Third after a gap.", 664.0),
        line("A heading", 650.0, size=12.0),
    )
    layout = lay_out_pages([PdfPageText(page_number=1, lines=lines)])
    assert layout.paragraphs == (
        "First paragraph opens and continues.",
        "Second opens indented and continues.",
        "Third after a gap.",
        "A heading",
    )


def test_a_paragraph_continues_onto_the_next_page_only_when_nothing_ends_it() -> None:
    def two_pages(last: str, first: PositionedLine) -> tuple[str, ...]:
        return lay_out_pages(
            [
                PdfPageText(page_number=1, lines=(line(last, 730.0),)),
                PdfPageText(page_number=2, lines=(first, line("and more.", 716.0))),
            ]
        ).paragraphs

    assert two_pages("runs on", line("to the next page", 730.0)) == ("runs on to the next page and more.",)
    assert two_pages("ends here.", line("New page", 730.0)) == ("ends here.", "New page and more.")
    assert two_pages("asks a question?”", line("New page", 730.0)) == (
        "asks a question?”",
        "New page and more.",
    )
    assert two_pages("runs on", line("Indented opening", 730.0, x=INDENT)) == (
        "runs on",
        "Indented opening and more.",
    )
    assert two_pages("runs on", line("A heading", 730.0, size=12.0)) == ("runs on", "A heading", "and more.")


def test_a_line_that_moves_up_the_page_is_a_new_column_and_continues_its_paragraph() -> None:
    lines = (line("left column runs", 200.0), line("on into the right column.", 730.0, x=320.0))
    assert lay_out_pages([PdfPageText(page_number=1, lines=lines)]).paragraphs == (
        "left column runs on into the right column.",
    )


def test_blank_lines_are_skipped_and_each_line_is_trimmed() -> None:
    lines = (line("  first line  ", 730.0), line("   ", 716.0), line("second line", 702.0))
    assert lay_out_pages([PdfPageText(page_number=1, lines=lines)]).paragraphs == ("first line second line",)


# --------------------------------------------------------------------------------------------
# The fixture, through the rules alone
# --------------------------------------------------------------------------------------------


def test_the_journal_article_lines_lay_out_as_the_hand_written_expectation() -> None:
    pages = [
        PdfPageText(
            page_number=number,
            lines=tuple(line(drawn.text, drawn.y, x=drawn.x, size=drawn.size) for drawn in drawn_lines),
        )
        for number, drawn_lines in enumerate(journal_article_pages(), start=1)
    ]
    expected = load_expected("journal-article")
    layout = lay_out_pages(pages)
    assert list(layout.paragraphs) == expected["paragraphs"]
    assert join_mismatches(layout.paragraphs, layout.line_joins, expected["line_joins"]) == []
    assert removed_line_rows(layout.removed_lines) == expected["removed_lines"]


def test_the_journal_article_counts_reported_to_the_pm() -> None:
    pages = [
        PdfPageText(
            page_number=number,
            lines=tuple(line(drawn.text, drawn.y, x=drawn.x, size=drawn.size) for drawn in drawn_lines),
        )
        for number, drawn_lines in enumerate(journal_article_pages(), start=1)
    ]
    layout = lay_out_pages(pages)
    assert Counter(join.decision for join in layout.line_joins) == {
        JoinDecision.JOINED_FORM_IN_DOCUMENT: 4,
        JoinDecision.SOFT_HYPHEN: 1,
        JoinDecision.HYPHENATED_FORM_IN_DOCUMENT: 4,
        JoinDecision.NOT_A_WORD_BREAK: 1,
        JoinDecision.UNDETERMINED: 3,
    }
    assert Counter(join.hyphen_kept for join in layout.line_joins) == {True: 8, False: 5}
    assert Counter(item.page_number for item in layout.removed_lines) == {1: 2, 2: 3, 3: 3}


# --------------------------------------------------------------------------------------------
# No character is invented or lost, except the recorded ones
# --------------------------------------------------------------------------------------------

_TEXT = st.text(alphabet="abcDE -­–0123.", min_size=1, max_size=24)


@st.composite
def documents(draw: st.DrawFn) -> list[PdfPageText]:
    pages: list[PdfPageText] = []
    for number in range(1, draw(st.integers(min_value=1, max_value=4)) + 1):
        texts = draw(st.lists(_TEXT, min_size=1, max_size=9))
        lines = [
            line(
                text,
                730.0 - 14.0 * index - draw(st.sampled_from([0.0, 0.0, 0.0, 12.0])),
                x=draw(st.sampled_from([LEFT, LEFT, INDENT])),
                size=draw(st.sampled_from([10.0, 10.0, 12.0])),
            )
            for index, text in enumerate(texts)
        ]
        pages.append(PdfPageText(page_number=number, lines=tuple(lines)))
    return pages


def visible(text: str) -> Counter[str]:
    return Counter(character for character in text if not character.isspace())


@settings(max_examples=300, deadline=None)
@given(documents())
def test_every_character_is_in_the_text_a_removed_line_or_a_dropped_join(pages: list[PdfPageText]) -> None:
    layout = lay_out_pages(pages)
    printed = sum((visible(item.text) for page_text in pages for item in page_text.lines), Counter[str]())
    accounted = sum((visible(paragraph) for paragraph in layout.paragraphs), Counter[str]())
    accounted += sum((visible(item.text) for item in layout.removed_lines), Counter[str]())
    accounted += Counter(join.character for join in layout.line_joins if not join.hyphen_kept)
    assert accounted == printed
    event(f"joins kept: {min(sum(join.hyphen_kept for join in layout.line_joins), 2)}+")
    event(f"joins dropped: {min(sum(not join.hyphen_kept for join in layout.line_joins), 2)}+")
    event(f"lines removed: {min(len(layout.removed_lines), 2)}+")
    event(f"paragraphs: {min(len(layout.paragraphs), 3)}+")

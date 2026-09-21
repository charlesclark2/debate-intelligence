"""Run text and formatting spans: is the text exactly what the file says, and do the offsets land?

The fidelity test at the bottom of this file is the one that matters most. It re-reads the XML
independently of the reader — pulling every `w:t` out of the paragraph with a second, dumber walk
— and proves that the text the reader produced is the same string, and that each span selects the
characters the run that produced it held. A parser that quietly normalized a quotation mark, or
that built its offsets from a second pass over the tree, would fail it.

The rest of the file is the behaviour the fidelity test assumes: tracked changes, the two
underline encodings, tabs and breaks, and what a text box does.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from debate_core.domain.debate_files import FontSizeSpan, FormattingSpan
from debate_core.domain.style_profile import (
    RunEmphasis,
    StructuralUnit,
    StyleMatchSource,
    StyleProfile,
)
from debate_core.integrations.docx_parser.package import (
    XmlElement,
    open_debate_docx,
    qualified_name,
)
from debate_core.integrations.docx_parser.runs import (
    ReadParagraph,
    SpannedText,
    concatenate_spanned_text,
    font_size_spans_for,
    formatting_spans_for,
    iter_text_box_paragraphs,
    merge_adjacent_formatting_spans,
    read_paragraph,
)
from debate_core.testing.docx_builder import build_docx, paragraph_xml, run_xml

# Invented for these tests. No real evidence, no real cite, no real team.
OPENING = "Grid operators in the region reported that demand from new data centres rose "
UNDERLINED = "faster than any other load category last year"
CLOSING = ", and the increase outpaced every scenario the utility had planned against."


def read_first_paragraph(body: str, *, index: int = 0) -> ReadParagraph:
    """Build a one-paragraph package and read the paragraph at `index` out of it."""
    package = open_debate_docx(build_docx(body))
    element = list(package.body)[index]
    return read_paragraph(element, package, element_index=index)


def read_all_paragraphs(body: str) -> list[ReadParagraph]:
    package = open_debate_docx(build_docx(body))
    return [
        read_paragraph(element, package, element_index=index) for index, element in enumerate(package.body)
    ]


def iter_w_t_text(element: XmlElement) -> Iterator[str]:
    """Every `w:t` under an element, by a walk that knows nothing about this parser."""
    for text_element in element.iter(qualified_name("t")):
        yield text_element.text or ""


# --------------------------------------------------------------------------------------------
# Text, exactly
# --------------------------------------------------------------------------------------------


class TestParagraphText:
    def test_runs_are_concatenated_in_document_order(self) -> None:
        read = read_first_paragraph(paragraph_xml(run_xml(OPENING) + run_xml(UNDERLINED) + run_xml(CLOSING)))
        assert read.text == OPENING + UNDERLINED + CLOSING

    def test_preserved_whitespace_is_kept_character_for_character(self) -> None:
        """A run of nothing but spaces is part of a card's text and is not trimmed away."""
        read = read_first_paragraph(paragraph_xml(run_xml("one") + run_xml("   ") + run_xml("two")))
        assert read.text == "one   two"

    def test_a_tab_contributes_a_tab_and_a_break_a_newline(self) -> None:
        body = "<w:p><w:r><w:t>before</w:t><w:tab/><w:t>after</w:t><w:br/><w:t>next</w:t></w:r></w:p>"
        assert read_first_paragraph(body).text == "before\tafter\nnext"

    def test_a_drawing_contributes_nothing(self) -> None:
        body = "<w:p><w:r><w:t>caption</w:t><w:drawing/></w:r></w:p>"
        assert read_first_paragraph(body).text == "caption"

    def test_text_inside_a_hyperlink_is_part_of_the_paragraph(self) -> None:
        """Cites carry URLs, and 437 files in the survey style them with `Hyperlink`."""
        body = (
            "<w:p>"
            '<w:r><w:t xml:space="preserve">Journal of Grid Studies, </w:t></w:r>'
            '<w:hyperlink r:id="rId7" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            "<w:r><w:t>example.invalid/grid</w:t></w:r></w:hyperlink>"
            "</w:p>"
        )
        assert read_first_paragraph(body).text == "Journal of Grid Studies, example.invalid/grid"

    def test_an_empty_paragraph_reads_as_empty(self) -> None:
        read = read_first_paragraph("<w:p/>")
        assert read.text == ""
        assert read.description.is_empty


class TestTrackedChanges:
    def test_an_insertion_is_kept(self) -> None:
        body = (
            "<w:p>"
            '<w:r><w:t xml:space="preserve">demand rose </w:t></w:r>'
            '<w:ins w:id="1" w:author="a" w:date="2026-03-14T00:00:00Z">'
            "<w:r><w:t>sharply </w:t></w:r></w:ins>"
            "<w:r><w:t>last year</w:t></w:r>"
            "</w:p>"
        )
        read = read_first_paragraph(body)
        assert read.text == "demand rose sharply last year"
        assert read.insertions_kept == 1

    def test_a_deletion_is_dropped_and_its_text_is_never_read(self) -> None:
        """`w:delText` is text the file would no longer read out loud, so it is not the card."""
        body = (
            "<w:p>"
            '<w:r><w:t xml:space="preserve">demand rose </w:t></w:r>'
            '<w:del w:id="2" w:author="a" w:date="2026-03-14T00:00:00Z">'
            "<w:r><w:delText>slightly </w:delText></w:r></w:del>"
            "<w:r><w:t>last year</w:t></w:r>"
            "</w:p>"
        )
        read = read_first_paragraph(body)
        assert read.text == "demand rose last year"
        assert "slightly" not in read.text
        assert read.deletions_dropped == 1

    def test_a_moved_run_is_kept_where_it_moved_to_and_dropped_where_it_came_from(self) -> None:
        body = (
            "<w:p>"
            '<w:moveTo w:id="3" w:author="a" w:date="2026-03-14T00:00:00Z">'
            '<w:r><w:t xml:space="preserve">kept </w:t></w:r></w:moveTo>'
            '<w:moveFrom w:id="4" w:author="a" w:date="2026-03-14T00:00:00Z">'
            "<w:r><w:delText>gone</w:delText></w:r></w:moveFrom>"
            "<w:r><w:t>text</w:t></w:r>"
            "</w:p>"
        )
        read = read_first_paragraph(body)
        assert read.text == "kept text"


class TestTextBoxes:
    def test_a_text_box_does_not_contribute_to_the_paragraph_that_holds_it(self) -> None:
        body = (
            "<w:p><w:r><w:t>body text</w:t>"
            "<w:pict><w:txbxContent><w:p><w:r><w:t>page banner</w:t></w:r></w:p></w:txbxContent>"
            "</w:pict></w:r></w:p>"
        )
        read = read_first_paragraph(body)
        assert read.text == "body text"

    def test_a_text_box_is_read_once_even_though_word_writes_it_twice(self) -> None:
        """Word writes an `mc:Choice` rendering and an `mc:Fallback` holding the same paragraphs."""
        box = "<w:txbxContent><w:p><w:r><w:t>page banner</w:t></w:r></w:p></w:txbxContent>"
        body = (
            "<w:p><w:r>"
            '<mc:AlternateContent><mc:Choice Requires="wps">'
            f"{box}</mc:Choice><mc:Fallback>{box}</mc:Fallback></mc:AlternateContent>"
            "</w:r></w:p>"
        )
        package = open_debate_docx(build_docx(body))
        paragraphs = list(iter_text_box_paragraphs(list(package.body)[0]))
        assert len(paragraphs) == 1
        assert "".join(iter_w_t_text(paragraphs[0])) == "page banner"

    def test_a_plain_text_box_with_no_alternate_content_is_found(self) -> None:
        body = (
            "<w:p><w:r><w:pict><w:txbxContent>"
            "<w:p><w:r><w:t>margin note</w:t></w:r></w:p>"
            "</w:txbxContent></w:pict></w:r></w:p>"
        )
        package = open_debate_docx(build_docx(body))
        paragraphs = list(iter_text_box_paragraphs(list(package.body)[0]))
        assert len(paragraphs) == 1


# --------------------------------------------------------------------------------------------
# Formatting
# --------------------------------------------------------------------------------------------


class TestRunProperties:
    def test_bold_off_on_a_heading_run_is_read_as_off_not_as_absent(self) -> None:
        """`<w:b w:val="0"/>` says "not bold"; reading it as "says nothing" loses the fact."""
        read = read_first_paragraph(paragraph_xml(run_xml("tag text", bold=False), style="Heading4"))
        assert read.description.runs[0].bold is False

    def test_a_run_that_says_nothing_about_bold_inherits(self) -> None:
        read = read_first_paragraph(paragraph_xml(run_xml("tag text"), style="Heading4"))
        assert read.description.runs[0].bold is None

    def test_a_w_u_with_no_val_is_a_single_underline(self) -> None:
        body = "<w:p><w:r><w:rPr><w:u/></w:rPr><w:t>read this</w:t></w:r></w:p>"
        assert read_first_paragraph(body).description.runs[0].underline == "single"

    def test_a_character_style_is_resolved_against_the_documents_own_style_table(self) -> None:
        read = read_first_paragraph(paragraph_xml(run_xml(UNDERLINED, character_style="StyleUnderline")))
        run = read.description.runs[0]
        assert run.character_style_id == "StyleUnderline"
        assert run.character_style_name == "Style Underline"
        assert run.character_style_based_on == ("DefaultParagraphFont",)


class TestFormattingSpans:
    def test_an_underlined_run_becomes_one_span_over_its_own_characters(self, profile: StyleProfile) -> None:
        read = read_first_paragraph(
            paragraph_xml(
                run_xml(OPENING) + run_xml(UNDERLINED, character_style="StyleUnderline") + run_xml(CLOSING)
            )
        )
        spans = formatting_spans_for(read, profile, slot=StructuralUnit.EVIDENCE)
        underlines = [span for span in spans if span.emphasis is RunEmphasis.UNDERLINE]
        assert len(underlines) == 1
        assert read.text[underlines[0].start_offset : underlines[0].end_offset] == UNDERLINED

    def test_cardmirrors_dual_underline_encoding_produces_one_span_not_two(
        self, profile: StyleProfile
    ) -> None:
        """63% of the corpus has been through CardMirror, which writes both encodings on body runs.

        `StyleUnderline` and a direct `<w:u>` on the same run are one underline. Two spans here
        would double the underlining of most of the corpus.
        """
        read = read_first_paragraph(
            paragraph_xml(
                run_xml(OPENING)
                + run_xml(UNDERLINED, character_style="StyleUnderline", underline="single")
                + run_xml(CLOSING)
            )
        )
        spans = formatting_spans_for(read, profile, slot=StructuralUnit.EVIDENCE)
        underlines = [span for span in spans if span.emphasis is RunEmphasis.UNDERLINE]
        assert len(underlines) == 1
        assert underlines[0].match_source is StyleMatchSource.VERBATIM

    def test_a_direct_underline_in_a_heading_slot_is_the_expected_encoding(
        self, profile: StyleProfile
    ) -> None:
        read = read_first_paragraph(
            paragraph_xml(run_xml("AT: Reserve Margin Turn", underline="single"), style="Heading3")
        )
        spans = formatting_spans_for(read, profile, slot=StructuralUnit.BLOCK)
        underline = next(span for span in spans if span.emphasis is RunEmphasis.UNDERLINE)
        assert underline.rule_id == "direct-underline"

    def test_a_highlight_span_carries_the_colour_it_was_written_with(self, profile: StyleProfile) -> None:
        read = read_first_paragraph(
            paragraph_xml(
                run_xml(OPENING) + run_xml(UNDERLINED, character_style="StyleUnderline", highlight="cyan")
            )
        )
        spans = formatting_spans_for(read, profile, slot=StructuralUnit.EVIDENCE)
        highlight = next(span for span in spans if span.emphasis is RunEmphasis.HIGHLIGHT)
        assert highlight.highlight_color == "cyan"
        assert read.text[highlight.start_offset : highlight.end_offset] == UNDERLINED

    def test_emphasis_and_underline_can_cover_the_same_characters(self, profile: StyleProfile) -> None:
        """Verbatim's `Emphasis` is itself underlined: emphasised text is marked-up underlining."""
        read = read_first_paragraph(paragraph_xml(run_xml(UNDERLINED, character_style="Emphasis")))
        spans = formatting_spans_for(read, profile, slot=StructuralUnit.EVIDENCE)
        assert {span.emphasis for span in spans} == {RunEmphasis.EMPHASIS}

    def test_a_blank_run_produces_no_span(self, profile: StyleProfile) -> None:
        read = read_first_paragraph(
            paragraph_xml(run_xml("", character_style="StyleUnderline") + run_xml(OPENING))
        )
        assert formatting_spans_for(read, profile, slot=StructuralUnit.EVIDENCE) == ()

    def test_four_runs_of_one_underlined_sentence_merge_into_one_span(self, profile: StyleProfile) -> None:
        """Word splits a run whenever somebody edits inside it; a card's spans must not show that."""
        pieces = ("faster ", "than any ", "other load ", "category")
        read = read_first_paragraph(
            paragraph_xml("".join(run_xml(piece, character_style="StyleUnderline") for piece in pieces))
        )
        spans = formatting_spans_for(read, profile, slot=StructuralUnit.EVIDENCE)
        assert len(spans) == 1
        assert read.text[spans[0].start_offset : spans[0].end_offset] == "".join(pieces)

    def test_spans_that_differ_in_the_rule_that_found_them_are_not_merged(
        self, profile: StyleProfile
    ) -> None:
        read = read_first_paragraph(
            paragraph_xml(
                run_xml("styled ", character_style="StyleUnderline") + run_xml("direct", underline="single")
            )
        )
        spans = formatting_spans_for(read, profile, slot=StructuralUnit.EVIDENCE)
        assert len({span.rule_id for span in spans}) == 2


class TestFontSizeSpans:
    def test_shrunk_and_read_text_produce_separate_size_spans(self, profile: StyleProfile) -> None:
        """The unread part of a card sits at `w:sz` 16 and the read part at 22 — measured, not set."""
        read = read_first_paragraph(
            paragraph_xml(
                run_xml(OPENING, half_points=16)
                + run_xml(UNDERLINED, character_style="StyleUnderline", half_points=22)
                + run_xml(CLOSING, half_points=16)
            )
        )
        spans = font_size_spans_for(read)
        assert [span.half_points for span in spans] == [16, 22, 16]
        assert read.text[spans[1].start_offset : spans[1].end_offset] == UNDERLINED

    def test_adjacent_runs_at_the_same_size_merge(self) -> None:
        read = read_first_paragraph(
            paragraph_xml(run_xml(OPENING, half_points=16) + run_xml(CLOSING, half_points=16))
        )
        assert len(font_size_spans_for(read)) == 1

    def test_a_run_that_declares_no_size_records_none(self) -> None:
        read = read_first_paragraph(paragraph_xml(run_xml(OPENING)))
        assert font_size_spans_for(read) == ()

    def test_a_shrunk_run_is_also_reported_as_shrunk_emphasis(self, profile: StyleProfile) -> None:
        read = read_first_paragraph(paragraph_xml(run_xml(OPENING, half_points=16)))
        spans = formatting_spans_for(read, profile, slot=StructuralUnit.EVIDENCE)
        assert any(span.emphasis is RunEmphasis.SHRUNK for span in spans)


# --------------------------------------------------------------------------------------------
# Joining paragraphs into a card body
# --------------------------------------------------------------------------------------------


class TestConcatenation:
    def test_spans_move_onto_the_joined_string(self) -> None:
        first = SpannedText(
            text="first line",
            formatting_spans=(
                FormattingSpan(
                    emphasis=RunEmphasis.UNDERLINE,
                    start_offset=0,
                    end_offset=5,
                    rule_id="verbatim-style-id:StyleUnderline",
                    match_source=StyleMatchSource.VERBATIM,
                ),
            ),
        )
        second = SpannedText(
            text="second line",
            font_size_spans=(FontSizeSpan(start_offset=0, end_offset=6, half_points=16),),
        )
        joined = concatenate_spanned_text([first, second])
        assert joined.text == "first line\nsecond line"
        assert joined.text[joined.font_size_spans[0].start_offset : joined.font_size_spans[0].end_offset] == (
            "second"
        )

    def test_nothing_joins_to_an_empty_text(self) -> None:
        assert concatenate_spanned_text([]).text == ""

    def test_a_span_never_runs_across_the_separator(self) -> None:
        part = SpannedText(
            text="line",
            formatting_spans=(
                FormattingSpan(
                    emphasis=RunEmphasis.UNDERLINE,
                    start_offset=0,
                    end_offset=4,
                    rule_id="verbatim-style-id:StyleUnderline",
                    match_source=StyleMatchSource.VERBATIM,
                ),
            ),
        )
        joined = concatenate_spanned_text([part, part])
        assert len(joined.formatting_spans) == 2
        assert all(
            joined.text[span.start_offset : span.end_offset] == "line" for span in joined.formatting_spans
        )

    def test_merging_is_stable_when_given_spans_out_of_order(self) -> None:
        late = FormattingSpan(
            emphasis=RunEmphasis.UNDERLINE,
            start_offset=5,
            end_offset=9,
            rule_id="direct-underline",
            match_source=StyleMatchSource.VERBATIM,
        )
        early = late.evolve(start_offset=0, end_offset=5)
        assert merge_adjacent_formatting_spans([late, early]) == (early.evolve(end_offset=9),)


# --------------------------------------------------------------------------------------------
# Fidelity: the text and the offsets against a second, independent reading of the XML
# --------------------------------------------------------------------------------------------

FIDELITY_BODY = (
    paragraph_xml(run_xml("Data centre demand collapses the reserve margin"), style="Heading4")
    + paragraph_xml(
        run_xml("Okonkwo 26", character_style="Style13ptBold")
        + run_xml(" (Journal of Grid Studies, 14 March 2026), ")
        + run_xml("example.invalid/grid")
    )
    + paragraph_xml(
        run_xml(OPENING, half_points=16)
        + run_xml(
            UNDERLINED,
            character_style="StyleUnderline",
            underline="single",
            highlight="cyan",
            half_points=22,
        )
        + run_xml(CLOSING, half_points=16)
    )
)


@pytest.mark.parametrize("index", [0, 1, 2])
def test_paragraph_text_equals_the_concatenated_w_t_text_of_its_runs(index: int) -> None:
    """Re-read the XML with a walk that knows nothing about the reader, and compare.

    This is goal criterion ac3's first half. Nothing normalizes, corrects or re-flows a card's
    text; what comes out is what the runs hold, character for character.
    """
    package = open_debate_docx(build_docx(FIDELITY_BODY))
    element = list(package.body)[index]
    read = read_paragraph(element, package, element_index=index)
    assert read.text == "".join(iter_w_t_text(element))


def test_every_span_selects_exactly_the_characters_of_the_run_that_produced_it(
    profile: StyleProfile,
) -> None:
    """ac3's second half: underline, emphasis, bold, highlight and size land on the right offsets."""
    package = open_debate_docx(build_docx(FIDELITY_BODY))
    element = list(package.body)[2]
    read = read_paragraph(element, package, element_index=2)

    formatting = formatting_spans_for(read, profile, slot=StructuralUnit.EVIDENCE)
    by_emphasis = {span.emphasis: span for span in formatting}
    for emphasis in (RunEmphasis.UNDERLINE, RunEmphasis.HIGHLIGHT):
        span = by_emphasis[emphasis]
        assert read.text[span.start_offset : span.end_offset] == UNDERLINED

    sizes = font_size_spans_for(read)
    assert read.text[sizes[0].start_offset : sizes[0].end_offset] == OPENING
    assert read.text[sizes[1].start_offset : sizes[1].end_offset] == UNDERLINED
    assert read.text[sizes[2].start_offset : sizes[2].end_offset] == CLOSING


def test_no_span_runs_past_the_end_of_the_text_it_indexes(profile: StyleProfile) -> None:
    """Belt and braces for every paragraph of the fidelity document, at every slot."""
    package = open_debate_docx(build_docx(FIDELITY_BODY))
    for index, element in enumerate(package.body):
        read = read_paragraph(element, package, element_index=index)
        for slot in StructuralUnit:
            for span in formatting_spans_for(read, profile, slot=slot):
                assert span.end_offset <= len(read.text)
        for size_span in font_size_spans_for(read):
            assert size_span.end_offset <= len(read.text)


def test_the_reader_does_not_depend_on_paragraph_order_to_get_offsets_right() -> None:
    """Each paragraph's offsets are its own; reading them in any order gives the same answer."""
    forwards = read_all_paragraphs(FIDELITY_BODY)
    package = open_debate_docx(build_docx(FIDELITY_BODY))
    elements = list(package.body)
    backwards = [
        read_paragraph(elements[index], package, element_index=index)
        for index in reversed(range(len(elements)))
    ]
    assert [read.text for read in forwards] == [read.text for read in reversed(backwards)]

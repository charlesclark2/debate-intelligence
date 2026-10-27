"""The missed-unit tallies, on an invented file whose labels and expected counts are written by hand.

Each paragraph below is written to be one thing, and its label says so (working agreement 6). The
expected counts follow from what each paragraph was written to be and from the classifier's rules,
read off the classifier, not off a run: a second cite line with a link and no name is read as
nothing; a cite under a tag that opens in lower case is read as nothing; a cite set in the tag style
is read as a second tag, and the tag above it, left with nothing under it, as an analytic.

Those are `2026.10.20-docx-6`'s readings. `v1-e31-t31` (`2026.10.27-docx-7`) reads all three by their
place, so a parser that misses them is the checkout's with that pass left out
(:class:`CiteLinesAsDocx6ReadThem`): the tally is a count of what some parser misses, and these tests
need one that misses. :class:`TestTheCheckoutsParser` shows the current one leaves none of them.

The names, journals, links and sentences are invented.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import pytest
from tests.evals.parser.digests import keyed_digest, text_digest
from tests.evals.parser.labels_schema import (
    CardLabel,
    Category,
    DebateFormat,
    FileLabelHeader,
    LabelFile,
    LabelStatus,
    ManifestEntry,
    ParagraphLabel,
    ReviewerRole,
    SpanLabel,
    TemplateFamily,
)
from tests.evals.parser.missed_units import (
    BODY_UNDER_A_TAG,
    LONGER_CITE,
    PROPOSED_VARIANT,
    SECOND_LINE,
    SECOND_TAG,
    UNDER_A_TAG,
    WHITE_HIGHLIGHT_VARIANT,
    CardOutcome,
    FileCounts,
    NameAndYear,
    ReadingParser,
    count_file,
    tally,
)
from tests.evals.parser.synthetic import TEST_DIGEST_KEY

from debate_core.domain.caselist import SourceDocument, SourceFormat, SourceOrigin
from debate_core.domain.debate_files import CardCompleteness, ParsedDocument
from debate_core.domain.style_profile import StructuralUnit
from debate_core.testing.docx_builder import build_docx, paragraph_xml, run_xml

POCKET = StructuralUnit.POCKET
TAG = StructuralUnit.TAG
CITE = StructuralUnit.CITE
EVIDENCE = StructuralUnit.EVIDENCE

BODY = "Reserve margins fall below safe levels within two summers"
GREY = " and nobody plans for it"
CYAN = "Older plants fail first"

#: (markup, text, gold unit, card), in body order.
PARAGRAPHS = (
    (paragraph_xml(run_xml("Invented Negative"), style="Heading1"), "Invented Negative", POCKET, None),
    # Card 0: its cite runs over two lines, and the second is read as nothing.
    (
        paragraph_xml(run_xml("Moratoria collapse the margin"), style="Heading4"),
        "Moratoria collapse the margin",
        TAG,
        0,
    ),
    (
        paragraph_xml(run_xml("Okonkwo 26", character_style="Style13ptBold") + run_xml(", Grid Analyst")),
        "Okonkwo 26, Grid Analyst",
        CITE,
        0,
    ),
    (
        paragraph_xml(run_xml("Fictional Energy Review, https://example.org/grid-review")),
        "Fictional Energy Review, https://example.org/grid-review",
        CITE,
        0,
    ),
    (paragraph_xml(run_xml(BODY, underline="single")), BODY, EVIDENCE, 0),
    # Card 1: its only cite line opens in lower case, so no cite rule reads it.
    (paragraph_xml(run_xml("Older fleets fail"), style="Heading4"), "Older fleets fail", TAG, 1),
    (
        paragraph_xml(run_xml("published by an invented grid desk in 2026, https://example.org/desk")),
        "published by an invented grid desk in 2026, https://example.org/desk",
        CITE,
        1,
    ),
    (
        paragraph_xml(run_xml(BODY, underline="single") + run_xml(GREY, highlight="lightGray")),
        BODY + GREY,
        EVIDENCE,
        1,
    ),
    # Card 2: its cite is set in the tag style.
    (paragraph_xml(run_xml("Reserve margins recover"), style="Heading4"), "Reserve margins recover", TAG, 2),
    (
        paragraph_xml(run_xml("Lindqvist 25, Professor, Invented University"), style="Heading4"),
        "Lindqvist 25, Professor, Invented University",
        CITE,
        2,
    ),
    (paragraph_xml(run_xml(CYAN, underline="single", highlight="cyan")), CYAN, EVIDENCE, 2),
    # Card 3: read right, but for a short first body line with neither link nor year.
    (paragraph_xml(run_xml("Fleets age out"), style="Heading4"), "Fleets age out", TAG, 3),
    (
        paragraph_xml(
            run_xml("Adebayo 24", character_style="Style13ptBold") + run_xml(", Invented Institute")
        ),
        "Adebayo 24, Invented Institute",
        CITE,
        3,
    ),
    (paragraph_xml(run_xml("As the review puts it")), "As the review puts it", EVIDENCE, 3),
    (paragraph_xml(run_xml(BODY, underline="single")), BODY, EVIDENCE, 3),
)

#: Span rows: a highlight on paragraph 4 that the file does not carry, the lightGray run on paragraph 7
#: labelled as no highlight, and the cyan run on paragraph 10 labelled exactly.
SPANS = (
    SpanLabel(index=4, underline=((0, len(BODY)),), highlight=((0, 7),)),
    SpanLabel(index=7, underline=((0, len(BODY)),)),
    SpanLabel(index=10, underline=((0, len(CYAN)),), highlight=((0, len(CYAN)),)),
)

ENTRY_FIELDS = {
    "category": Category.CAMP,
    "season": "2026-27",
    "debate_format": DebateFormat.POLICY,
    "template_family": TemplateFamily.VERBATIM,
}


class CiteLinesAsDocx6ReadThem(ReadingParser):
    """The checkout's parser, reading cite lines as `2026.10.20-docx-6` did: no cite line by its place."""

    def _cite_lines_by_their_place(self, assembled: Any) -> dict[int, str]:  # pyright: ignore[reportIncompatibleMethodOverride]
        return {}


def _counted(parser: ReadingParser) -> tuple[ManifestEntry, FileCounts]:
    content = build_docx("".join(markup for markup, _, _, _ in PARAGRAPHS))
    digest = keyed_digest(content, TEST_DIGEST_KEY)
    labels = LabelFile(
        header=FileLabelHeader(
            digest=digest,
            paragraph_count=len(PARAGRAPHS),
            blocks=((0, len(PARAGRAPHS) - 1),),
            plan_id="",
            status=LabelStatus.CORRECTED,
            prelabel_parser_version="hand-written",
            corrected_by=ReviewerRole.OPERATOR,
        ),
        paragraphs=tuple(
            ParagraphLabel(
                index=index,
                length=len(text),
                text_digest=text_digest(text, TEST_DIGEST_KEY),
                unit=unit,
                card=card,
            )
            for index, (_, text, unit, card) in enumerate(PARAGRAPHS)
        ),
        cards=tuple(CardLabel(card=card, completeness=CardCompleteness.FULL) for card in range(4)),
        spans=SPANS,
    )
    entry = ManifestEntry(digest=digest, **ENTRY_FIELDS)
    source = SourceDocument(
        sha256="0" * 64,
        byte_size=len(content),
        source_format=SourceFormat.DOCX,
        origin=SourceOrigin.OPENEV,
        first_seen_snapshot=date(2026, 10, 27),
        last_seen_snapshot=date(2026, 10, 27),
    )
    document = parser.parse(content, source, source_path="invented.docx", camp="camp")
    assert isinstance(document, ParsedDocument)
    return entry, count_file(entry, labels, document, parser)


@pytest.fixture(scope="module")
def counted() -> tuple[ManifestEntry, FileCounts]:
    return _counted(CiteLinesAsDocx6ReadThem())


@pytest.fixture(scope="module")
def tallied(counted: tuple[ManifestEntry, FileCounts]) -> dict[str, object]:
    return tally([counted])


class TestTheMissedRows:
    def test_each_miss_is_read_as_the_classifier_reads_it(
        self, counted: tuple[ManifestEntry, FileCounts]
    ) -> None:
        _, counts = counted
        read = {(row.labelled, row.read_as, row.rule) for row in counts.missed}
        assert read == {
            (CITE, StructuralUnit.OTHER, "heuristic-unclassified-paragraph"),
            (TAG, StructuralUnit.ANALYTIC, "assembly-tag-without-cite-or-evidence"),
            (CITE, TAG, "verbatim-style-id"),
        }
        assert len(counts.missed) == 4

    def test_the_second_cite_line_is_described_without_its_text(
        self, counted: tuple[ManifestEntry, FileCounts]
    ) -> None:
        _, counts = counted
        second_line = next(row for row in counts.missed if row.above_labelled is CITE)
        assert second_line.above_read_as is CITE
        assert (second_line.below_labelled, second_line.below_read_as) == (EVIDENCE, EVIDENCE)
        assert second_line.name_and_year is NameAndYear.NONE
        assert second_line.holds_a_link and not second_line.holds_a_year
        assert second_line.card_outcome is CardOutcome.CITE_READ_IN_PART
        assert set(second_line.taken_by) == {
            "second line of a cite, read as nothing",
            SECOND_LINE,
            LONGER_CITE,
        }

    def test_the_cite_under_a_tag_leaves_its_card_with_no_cite(
        self, counted: tuple[ManifestEntry, FileCounts]
    ) -> None:
        _, counts = counted
        under = next(
            row for row in counts.missed if row.above_labelled is TAG and row.read_as is StructuralUnit.OTHER
        )
        assert under.holds_a_link and under.holds_a_year
        assert under.card_outcome is CardOutcome.NO_CITE_READ
        assert under.taken_by == (UNDER_A_TAG,)

    def test_the_cite_in_the_tag_style_demotes_the_tag_above(
        self, counted: tuple[ManifestEntry, FileCounts]
    ) -> None:
        _, counts = counted
        second_tag = next(row for row in counts.missed if row.read_as is TAG)
        assert second_tag.name_and_year is NameAndYear.AT_THE_HEAD
        assert (second_tag.above_labelled, second_tag.above_read_as) == (TAG, StructuralUnit.ANALYTIC)
        assert second_tag.taken_by == (SECOND_TAG,)
        demoted = next(row for row in counts.missed if row.labelled is TAG)
        assert (demoted.below_labelled, demoted.below_read_as) == (CITE, TAG)


class TestTheTally:
    def test_rows_and_cards(self, tallied: dict[str, object]) -> None:
        cite = tallied["CITE"]
        assert isinstance(cite, dict)
        assert (cite["labelled"], cite["read_right"], cite["missed"]) == (5, 2, 3)
        tag = tallied["TAG"]
        assert isinstance(tag, dict)
        assert (tag["labelled"], tag["read_right"], tag["missed"]) == (4, 3, 1)
        cards = tallied["cards_with_a_labelled_cite"]
        assert isinstance(cards, dict)
        assert cards["as read"] == {"all": 1, "part": 1, "none": 2}
        assert cards[PROPOSED_VARIANT] == {"all": 4, "part": 0, "none": 0}

    def test_the_candidate_shapes_by_gold_unit(self, tallied: dict[str, object]) -> None:
        shapes = tallied["candidate_shapes"]
        assert isinstance(shapes, dict)
        labelled_as = {name: shape["labelled_as"] for name, shape in shapes.items()}
        assert labelled_as == {
            "second line of a cite, read as nothing": {"CITE": 1, "EVIDENCE": 1},
            SECOND_LINE: {"CITE": 1},
            LONGER_CITE: {"CITE": 1},
            UNDER_A_TAG: {"CITE": 1},
            BODY_UNDER_A_TAG: {},
            SECOND_TAG: {"CITE": 1},
        }

    def test_what_if_the_proposed_shapes_read_every_cite_and_give_the_tag_back(
        self, tallied: dict[str, object]
    ) -> None:
        what_if = tallied["what_if"]
        assert isinstance(what_if, dict)
        as_read = what_if["as read"]["overall"]
        assert (as_read["CITE"]["tp"], as_read["CITE"]["fp"], as_read["CITE"]["fn"]) == (2, 0, 3)
        # The cite read as a second tag is a false tag; the tag it pushed down is a missed one.
        assert (as_read["TAG"]["tp"], as_read["TAG"]["fp"], as_read["TAG"]["fn"]) == (3, 1, 1)
        proposed = what_if[PROPOSED_VARIANT]["overall"]
        assert (proposed["CITE"]["tp"], proposed["CITE"]["fp"], proposed["CITE"]["fn"]) == (5, 0, 0)
        assert (proposed["TAG"]["tp"], proposed["TAG"]["fp"], proposed["TAG"]["fn"]) == (4, 0, 0)

    def test_highlight_characters_by_colour(
        self, tallied: dict[str, object], counted: tuple[ManifestEntry, FileCounts]
    ) -> None:
        entry, _ = counted
        highlight = tallied["highlight"]
        assert isinstance(highlight, dict)
        prefix = f"camp | verbatim | Policy | {entry.digest[:16]}"
        assert highlight["missed_characters"] == {f"{prefix} | no highlight on the run": 7}
        assert highlight["added_characters"] == {f"{prefix} | lightGray (not a reading colour)": len(GREY)}
        what_if = tallied["what_if"]
        assert isinstance(what_if, dict)
        as_read = round(2 * len(CYAN) / (2 * len(CYAN) + len(GREY) + 7), 4)
        assert what_if["as read"]["overall"]["highlight_f1"] == as_read
        # lightGray is still read as highlight, so leaving out white changes nothing here.
        assert what_if[WHITE_HIGHLIGHT_VARIANT]["overall"]["highlight_f1"] == as_read

    def test_no_text_leaves_the_tally(self, tallied: dict[str, object]) -> None:
        printed = json.dumps(tallied)
        for _, text, _, _ in PARAGRAPHS:
            assert text not in printed
        for word in ("Okonkwo", "Lindqvist", "Adebayo", "example.org", "Invented"):
            assert word not in printed


class TestTheCheckoutsParser:
    def test_it_reads_every_cite_and_tag_the_invented_file_holds(self) -> None:
        _, counts = _counted(ReadingParser())

        assert counts.missed == ()
        assert {
            key: count
            for key, count in counts.outcomes.items()
            if key[:2] == ("cards with a labelled cite", "as read")
        } == {("cards with a labelled cite", "as read", "all"): 4}

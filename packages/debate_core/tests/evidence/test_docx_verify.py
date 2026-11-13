"""Tests for reading a rendered .docx's body and comparing it with its cards (`v1-e06-t07`).

Two plan nodes, by name: tests with ``reader`` in their name are the body reader's
(:mod:`debate_core.evidence.docx_reader`), tests with ``diff`` the comparison's
(:mod:`debate_core.evidence.docx_verify`). Documents are real exports of t02's news card
(`tests/fixtures/verify/docx_world.py`), changed through python-docx the way Word changes them. Every
expected text and offset is counted by hand from the fixture's evidence, whose pieces the world names:
the first sentence is evidence [0, 108), the cut sits at 108, the critics' sentence is [108, 202) and
the rest [202, 398). In an untouched body everything after the cut is three characters further on,
the marker's length.

Tests with ``negation`` in their name are `v1-e06-t10`'s node: a deletion in the body that removes a
negating word is a ``NEGATION_REMOVED`` warning on a card that stays VERIFIED. They verify a card cut
from an invented source of their own (its offsets are counted where it is defined), through
``VerifyManifest``, so each sees the verdict `verify` reports.
"""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final

import pytest
from docx.document import Document
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls, qn
from tests.fixtures.verification.verification_world import VerificationWorld, run
from tests.fixtures.verify.docx_world import (
    CRITICS_SENTENCE,
    EXPORTED_AT,
    FIRST_SENTENCE,
    LAST_PART,
    MARKER,
    NEWS_CITE,
    NEWS_TAG,
    PROFILES,
    RENDERED_EVIDENCE,
    TEAM_DEFAULT,
    NewsExport,
    edited,
    evidence_paragraph,
    news_export,
    replace_in_evidence,
)

from debate_core.application.export_service import ExportService
from debate_core.application.verify_manifest import VerifyManifest
from debate_core.domain import Card, Interpolation, VerificationStatus
from debate_core.evidence.card_rendering import CardToRender, DocumentHeadings
from debate_core.evidence.docx_reader import UnreadableDocument, read_document_body
from debate_core.evidence.docx_renderer import render_cards_docx
from debate_core.evidence.docx_verify import (
    BodyCard,
    BodyComparison,
    BodyInterpolation,
    BodyParagraph,
    CharacterRange,
    DocumentBody,
    ManualEdit,
    body_evidence,
    compare_body,
    match_body_cards,
)
from debate_core.evidence.format_profile import load_format_profiles
from debate_core.evidence.manifest import CardManifest
from debate_core.testing.fakes.clock_and_ids import FixedClock

STYLES: Final = TEAM_DEFAULT.style_profile
OBJECT: Final = "\ufffc"
"""What the reader reads in place of anything Word shows that is not text: a picture, a symbol."""
SHIFT: Final = len(MARKER)


@pytest.fixture(scope="module")
def export() -> NewsExport:
    return news_export()


@pytest.fixture(scope="module")
def card(export: NewsExport) -> Card:
    return export.card


def body_of(document: bytes) -> DocumentBody:
    return read_document_body(document, STYLES)


def with_paragraph_xml(xml: str) -> Callable[[Document], None]:
    """Append ``xml`` (one ``w:p`` or ``w:tbl``, ``w`` declared by the caller) after the evidence."""

    def change(document: Document) -> None:
        evidence_paragraph(document)._p.addnext(parse_xml(xml))  # pyright: ignore[reportPrivateUsage]

    return change


def with_runs_in_evidence(xml: str) -> Callable[[Document], None]:
    """Insert run-level ``xml`` into the evidence paragraph right after its first run."""

    def change(document: Document) -> None:
        first = evidence_paragraph(document).runs[0]._r  # pyright: ignore[reportPrivateUsage]
        first.addnext(parse_xml(xml))

    return change


# --------------------------------------------------------------------------------------------
# Node docx-reader: the body as Word shows it, cut into cards by the profile's styles
# --------------------------------------------------------------------------------------------


def test_reader_reads_an_untouched_export_as_its_tag_its_cite_and_its_evidence(export: NewsExport) -> None:
    assert body_of(export.document) == DocumentBody(
        cards=(
            BodyCard(
                position=0,
                tag=NEWS_TAG,
                paragraphs=(
                    BodyParagraph(NEWS_CITE.full_cite, is_cite=True),
                    BodyParagraph(RENDERED_EVIDENCE),
                ),
            ),
        )
    )


def test_reader_leaves_headings_out_and_starts_a_card_at_each_tag(export: NewsExport) -> None:
    second = export.card.evolve(card_id="0CVT0000000000000000000002", tag="A second tag")
    manifest = CardManifest(
        manifest_version=2,
        generated_at=export.manifest.generated_at,
        cards=(export.card, second),
        snapshots=export.manifest.snapshots,
    )
    document = render_cards_docx(
        manifest,
        [CardToRender(export.card, NEWS_CITE), CardToRender(second, NEWS_CITE)],
        TEAM_DEFAULT,
        headings=DocumentHeadings(pocket="1AC", hat="De-extinction", block="Funding"),
    )

    body = body_of(document)

    assert [(card.position, card.tag, len(card.paragraphs)) for card in body.cards] == [
        (0, NEWS_TAG, 2),
        (1, "A second tag", 2),
    ]


def test_reader_reads_the_banner_of_an_unverified_card_as_a_paragraph_before_the_cite(
    export: NewsExport,
) -> None:
    unverified = export.card.evolve(verification_status=VerificationStatus.UNVERIFIED)
    manifest = export.manifest.model_copy(update={"cards": (unverified,)})
    document = render_cards_docx(
        manifest, [CardToRender(unverified, NEWS_CITE, ("CITATION_UNVERIFIED",))], TEAM_DEFAULT
    )

    [card] = body_of(document).cards

    assert card.paragraphs == (
        BodyParagraph("UNVERIFIED — not a finished card: CITATION_UNVERIFIED"),
        BodyParagraph(NEWS_CITE.full_cite, is_cite=True),
        BodyParagraph(RENDERED_EVIDENCE),
    )


def test_reader_ends_a_card_at_a_heading_of_any_level(export: NewsExport) -> None:
    heading = (
        f'<w:p {nsdecls("w")}><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>'
        "<w:r><w:t>Next pocket</w:t></w:r></w:p>"
    )
    after = f"<w:p {nsdecls('w')}><w:r><w:t>Not under the card</w:t></w:r></w:p>"

    def change(document: Document) -> None:
        evidence = evidence_paragraph(document)._p  # pyright: ignore[reportPrivateUsage]
        evidence.addnext(parse_xml(after))
        evidence.addnext(parse_xml(heading))

    [card] = body_of(edited(export.document, change)).cards

    assert [paragraph.text for paragraph in card.paragraphs] == [NEWS_CITE.full_cite, RENDERED_EVIDENCE]


def test_reader_reads_a_tracked_insertion_and_leaves_out_a_tracked_deletion(export: NewsExport) -> None:
    """Word shows an insertion and, in the final view, not a deletion; the reader reads what it shows."""
    runs = (
        f'<w:ins {nsdecls("w")} w:id="1" w:author="s" w:date="2026-10-30T00:00:00Z">'
        '<w:r><w:t xml:space="preserve">not </w:t></w:r></w:ins>'
    )
    deletion = (
        f'<w:del {nsdecls("w")} w:id="2" w:author="s" w:date="2026-10-30T00:00:00Z"><w:r>'
        "<w:delText>gone</w:delText></w:r></w:del>"
    )

    document = edited(export.document, with_runs_in_evidence(runs))
    document = edited(document, with_runs_in_evidence(deletion))

    evidence = body_of(document).cards[0].paragraphs[-1].text
    assert evidence == "The delay follows two years of " + "not " + RENDERED_EVIDENCE[31:]


def test_reader_leaves_out_hidden_text(export: NewsExport) -> None:
    hidden = f"<w:r {nsdecls('w')}><w:rPr><w:vanish/></w:rPr><w:t>hidden</w:t></w:r>"

    evidence = body_of(edited(export.document, with_runs_in_evidence(hidden))).cards[0].paragraphs[-1].text

    assert evidence == RENDERED_EVIDENCE


@pytest.mark.parametrize(
    "run_xml",
    [
        f'<w:r {nsdecls("w")}><w:sym w:font="Symbol" w:char="F0AE"/></w:r>',
        f'<w:r {nsdecls("w")}><w:footnoteReference w:id="1"/></w:r>',
        f"<w:r {nsdecls('w', 'wp')}><w:drawing><wp:inline/></w:drawing></w:r>",
    ],
    ids=["a symbol", "a footnote mark", "a picture"],
)
def test_reader_reads_what_word_shows_that_is_not_text_as_an_object_character(
    export: NewsExport, run_xml: str
) -> None:
    evidence = body_of(edited(export.document, with_runs_in_evidence(run_xml))).cards[0].paragraphs[-1].text

    assert evidence == RENDERED_EVIDENCE[:31] + OBJECT + RENDERED_EVIDENCE[31:]


def test_reader_reads_tabs_breaks_and_text_inside_a_hyperlink(export: NewsExport) -> None:
    runs = (
        f'<w:hyperlink {nsdecls("w")} w:anchor="x"><w:r><w:tab/><w:t>linked</w:t><w:br/></w:r></w:hyperlink>'
    )

    evidence = body_of(edited(export.document, with_runs_in_evidence(runs))).cards[0].paragraphs[-1].text

    assert evidence == RENDERED_EVIDENCE[:31] + "\tlinked\n" + RENDERED_EVIDENCE[31:]


def test_reader_reads_a_table_under_a_card_as_a_paragraph_of_its_text(export: NewsExport) -> None:
    table = (
        f"<w:tbl {nsdecls('w')}><w:tr><w:tc><w:p><w:r><w:t>left</w:t></w:r></w:p></w:tc>"
        "<w:tc><w:p><w:r><w:t>right</w:t></w:r></w:p></w:tc></w:tr></w:tbl>"
    )

    [card] = body_of(edited(export.document, with_paragraph_xml(table))).cards

    assert card.paragraphs[-1] == BodyParagraph("left\nright")


def test_reader_knows_a_tag_by_its_style_name_when_word_has_renamed_its_id(export: NewsExport) -> None:
    """German Word writes heading 4's id as `berschrift4`; the name stays `heading 4`."""

    def localized(document: Document) -> None:
        document.styles["heading 4"].element.set(qn("w:styleId"), "berschrift4")
        document.paragraphs[0]._p.pPr.pStyle.set(qn("w:val"), "berschrift4")  # pyright: ignore[reportOptionalMemberAccess, reportPrivateUsage]

    [card] = body_of(edited(export.document, localized)).cards

    assert card.tag == NEWS_TAG


def test_reader_refuses_a_file_that_is_not_a_docx() -> None:
    with pytest.raises(UnreadableDocument, match="not a .docx"):
        body_of(b"Marrow basin wells, card list\n")


def test_reader_refuses_a_package_with_no_main_document(export: NewsExport) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(export.document)) as source, zipfile.ZipFile(buffer, "w") as target:
        for member in source.infolist():
            if member.filename != "word/document.xml":
                target.writestr(member, source.read(member))

    with pytest.raises(UnreadableDocument, match="main document"):
        body_of(buffer.getvalue())


def test_reader_refuses_a_main_document_that_declares_a_document_type(export: NewsExport) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(export.document)) as source, zipfile.ZipFile(buffer, "w") as target:
        for member in source.infolist():
            content = source.read(member)
            if member.filename == "word/document.xml":
                content = content.replace(b"?>", b'?><!DOCTYPE w:document [<!ENTITY e "x">]>', 1)
            target.writestr(member, content)

    with pytest.raises(UnreadableDocument, match="document type"):
        body_of(buffer.getvalue())


# --------------------------------------------------------------------------------------------
# Node body-diff: which body card is which, which paragraphs are evidence, what changed
# --------------------------------------------------------------------------------------------


def body_card(*paragraphs: BodyParagraph, position: int = 0, tag: str = NEWS_TAG) -> BodyCard:
    return BodyCard(position=position, tag=tag, paragraphs=paragraphs)


CITE: Final = BodyParagraph(NEWS_CITE.full_cite, is_cite=True)


def test_diff_matches_body_cards_by_position_when_the_counts_agree_whatever_their_tags() -> None:
    body = DocumentBody(
        cards=(body_card(tag="Rewritten by the student"), body_card(position=1, tag="Second"))
    )

    matched, unclaimed = match_body_cards(["First", "Second"], body)

    assert matched == body.cards
    assert unclaimed == ()


def test_diff_matches_by_tag_in_order_when_a_card_was_taken_out_of_the_body() -> None:
    kept = body_card(tag="Second")
    matched, unclaimed = match_body_cards(["First", "Second"], DocumentBody(cards=(kept,)))

    assert matched == (None, kept)
    assert unclaimed == ()


def test_diff_reports_a_body_card_no_manifest_card_claims() -> None:
    ours, theirs = body_card(tag="First"), body_card(position=1, tag="Pasted in by hand")
    body = DocumentBody(cards=(ours, body_card(position=2, tag="Also pasted"), theirs))

    matched, unclaimed = match_body_cards(["First", "Pasted in by hand"], body)

    assert matched == (ours, theirs)
    assert [card.tag for card in unclaimed] == ["Also pasted"]


def test_diff_takes_the_evidence_from_after_the_cite_and_leaves_blank_paragraphs_out(card: Card) -> None:
    shown = body_card(
        CITE, BodyParagraph("first"), BodyParagraph("  "), BodyParagraph(""), BodyParagraph("second")
    )

    assert body_evidence(card, shown) == "first\nsecond"


def test_diff_finds_the_cite_by_place_when_no_paragraph_carries_the_cite_style(card: Card) -> None:
    plain = BodyParagraph(NEWS_CITE.full_cite)

    assert body_evidence(card, body_card(plain, BodyParagraph("evidence"))) == "evidence"
    unverified = card.evolve(verification_status=VerificationStatus.UNVERIFIED)
    assert body_evidence(
        unverified, body_card(BodyParagraph("banner"), plain, BodyParagraph("evidence"))
    ) == ("evidence")


def test_diff_an_untouched_body_follows_the_policy_with_nothing_removed(card: Card) -> None:
    comparison = compare_body(card, RENDERED_EVIDENCE, MARKER)

    assert (comparison.manual_edits, comparison.interpolations, comparison.deletions) == ((), (), ())


def test_diff_a_changed_word_is_a_manual_edit_with_both_ranges(card: Card) -> None:
    """ "two" is evidence [18, 21); "three" is body [18, 23)."""
    body = RENDERED_EVIDENCE.replace("two years", "three years", 1)

    assert compare_body(card, body, MARKER).manual_edits == (
        ManualEdit(evidence_range=CharacterRange(18, 21), body_range=CharacterRange(18, 23)),
    )


def test_diff_a_word_whose_case_changed_is_a_manual_edit(card: Card) -> None:
    """ "Every" is evidence [204, 209) and body [207, 212): a capital is part of the quotation."""
    body = RENDERED_EVIDENCE.replace("“Every", "“every", 1)

    assert compare_body(card, body, MARKER).manual_edits == (
        ManualEdit(evidence_range=CharacterRange(204, 209), body_range=CharacterRange(207, 212)),
    )


def test_diff_letters_taken_out_of_a_word_are_a_manual_edit_not_a_deletion(card: Card) -> None:
    """ "failed" is evidence [31, 37); "fail" is body [31, 35)."""
    body = RENDERED_EVIDENCE.replace("failed", "fail", 1)

    assert compare_body(card, body, MARKER).manual_edits == (
        ManualEdit(evidence_range=CharacterRange(31, 37), body_range=CharacterRange(31, 35)),
    )


def test_diff_deleting_the_space_between_two_words_is_a_manual_edit(card: Card) -> None:
    """ "two years" [18, 27) becomes one word, "twoyears", body [18, 26)."""
    body = RENDERED_EVIDENCE.replace("two years", "twoyears", 1)

    assert compare_body(card, body, MARKER).manual_edits == (
        ManualEdit(evidence_range=CharacterRange(18, 27), body_range=CharacterRange(18, 26)),
    )


@pytest.mark.parametrize(
    "body",
    [
        FIRST_SENTENCE + MARKER + LAST_PART,
        FIRST_SENTENCE + MARKER.rstrip() + LAST_PART,
        FIRST_SENTENCE + LAST_PART,
    ],
    ids=["marker kept, its space doubled", "marker kept", "marker deleted too"],
)
def test_diff_deleting_a_whole_sentence_is_a_deletion_that_follows_the_policy(card: Card, body: str) -> None:
    comparison = compare_body(card, body, MARKER)

    assert comparison.manual_edits == ()
    assert comparison.deletions == (CharacterRange(108, 202),)


def test_diff_deleting_words_and_typing_the_marker_in_their_place_follows_the_policy(card: Card) -> None:
    """ "failed attempts to grow edited" is evidence [31, 61)."""
    body = RENDERED_EVIDENCE.replace("failed attempts to grow edited", "…", 1)

    comparison = compare_body(card, body, MARKER)

    assert comparison.manual_edits == ()
    assert comparison.deletions == (CharacterRange(31, 61),)


def test_diff_a_marker_where_nothing_was_cut_is_a_manual_edit(card: Card) -> None:
    """After "realistic." (evidence 202, body 205), where nothing was cut."""
    body = RENDERED_EVIDENCE.replace("realistic.", "realistic.…", 1)

    assert compare_body(card, body, MARKER).manual_edits == (
        ManualEdit(evidence_range=CharacterRange(202, 202), body_range=CharacterRange(205, 206)),
    )


def test_diff_the_marker_is_the_profiles_own(card: Card) -> None:
    """A profile whose marker is three full stops: one typed where words were cut follows the policy."""
    body = FIRST_SENTENCE + " ... " + CRITICS_SENTENCE + LAST_PART

    assert compare_body(card, body, " ... ").manual_edits == ()
    assert compare_body(card, body, MARKER).manual_edits != ()


def test_diff_an_added_interpolation_is_reported_where_it_is_read_and_follows_the_policy(card: Card) -> None:
    """ "project" is evidence 156; the interpolation is read before it."""
    body = RENDERED_EVIDENCE.replace("the project", "the [mammoth] project", 1)

    comparison = compare_body(card, body, MARKER)

    assert comparison.manual_edits == ()
    assert comparison.interpolations == (BodyInterpolation(anchor=156, length=7, recorded=False),)


def test_diff_an_interpolation_the_card_records_is_reported_as_recorded(card: Card) -> None:
    recorded = card.evolve(interpolations=(Interpolation(anchor=156, text="mammoth revival"),))
    body = (
        FIRST_SENTENCE
        + MARKER
        + CRITICS_SENTENCE.replace("project", "[mammoth revival]project", 1)
        + LAST_PART
    )

    comparison = compare_body(recorded, body, MARKER)

    assert comparison.manual_edits == ()
    assert comparison.interpolations == (BodyInterpolation(anchor=156, length=15, recorded=True),)


def test_diff_words_replaced_by_an_interpolation_follow_the_policy(card: Card) -> None:
    """Deleting "Conservation biologists" [108, 131) and bracketing words of one's own in their place."""
    body = RENDERED_EVIDENCE.replace("Conservation biologists", "[Scientists]", 1)

    comparison = compare_body(card, body, MARKER)

    assert comparison.manual_edits == ()
    assert comparison.deletions == (CharacterRange(108, 131),)
    assert [item.length for item in comparison.interpolations] == [10]


@pytest.mark.parametrize(
    ("inserted", "body_end"),
    [("[] ", 162), ("[  ] ", 164), ("[a] [b] ", 167)],
    ids=["empty brackets", "brackets around spaces", "two interpolations in one place"],
)
def test_diff_brackets_an_interpolation_cannot_be_are_a_manual_edit(
    card: Card, inserted: str, body_end: int
) -> None:
    body = RENDERED_EVIDENCE.replace("the project", "the " + inserted + "project", 1)

    [edit] = compare_body(card, body, MARKER).manual_edits

    assert (edit.evidence_range, edit.body_range) == (CharacterRange(156, 156), CharacterRange(159, body_end))


def test_diff_an_added_space_is_a_manual_edit(card: Card) -> None:
    """Between "“" (evidence 203) and "Every" (204)."""
    body = RENDERED_EVIDENCE.replace("“Every", "“ Every", 1)

    assert compare_body(card, body, MARKER).manual_edits == (
        ManualEdit(evidence_range=CharacterRange(204, 204), body_range=CharacterRange(207, 208)),
    )


@pytest.mark.parametrize("body", ["", "   ", MARKER, "[the card was here]"])
def test_diff_a_body_that_keeps_none_of_the_evidence_is_one_manual_edit_of_all_of_it(
    card: Card, body: str
) -> None:
    assert compare_body(card, body, MARKER).manual_edits == (
        ManualEdit(evidence_range=CharacterRange(0, 398), body_range=CharacterRange(0, len(body))),
    )


def test_diff_a_paragraph_added_under_the_evidence_is_a_manual_edit(card: Card) -> None:
    shown = body_card(CITE, BodyParagraph(RENDERED_EVIDENCE), BodyParagraph("And it will never work."))

    [edit] = compare_body(card, body_evidence(card, shown), MARKER).manual_edits

    assert (edit.evidence_range, edit.body_range) == (CharacterRange(398, 398), CharacterRange(401, 425))


def test_diff_a_body_too_different_to_compare_is_one_manual_edit_of_all_of_it(card: Card) -> None:
    body = "word " * 1100

    assert compare_body(card, body, MARKER).manual_edits == (
        ManualEdit(evidence_range=CharacterRange(0, 398), body_range=CharacterRange(0, len(body))),
    )


def test_diff_text_the_card_itself_brackets_is_quoted_text_not_an_interpolation(card: Card) -> None:
    """A source may bracket its own words; the same group in the body is the source's, not the student's.

    Only the comparison is under test, so the card's text is swapped without re-cutting it."""
    text = "Shares fell [sharply] on Monday."
    bracketed = card.model_copy(update={"evidence_text": text, "omitted_ranges": ()})

    comparison = compare_body(bracketed, text, MARKER)

    assert (comparison.manual_edits, comparison.interpolations) == ((), ())


# --------------------------------------------------------------------------------------------
# Node verify-docx-flags-a-removed-negation (`v1-e06-t10`): a deletion that removes a negation warns
# --------------------------------------------------------------------------------------------
#
# The card here is cut from an invented source, exported by ExportService and changed through
# python-docx, then verified by VerifyManifest, so every test sees the verdict `verify` prints. Its
# offsets are counted by hand from NEGATION_SOURCE:
#
#   snapshot   0-26    "Engineers met on Tuesday. "               left out of the envelope
#   snapshot  26-71    "The levee will not hold another spring flood."   -> evidence   0-45
#   snapshot  71-100   " Officials said nothing new. "            the card's own omission (29)
#   snapshot 100-186   "Inspectors have never checked the north wall, and residents don't trust the
#                      new pumps."                                                -> evidence 45-131
#
# so an evidence offset is 26 less than its snapshot offset before the cut and 55 less after it:
#   "will " 10-15 (36-41), "not " 15-19 (41-45), "hold " 19-24 (45-50), "another " 24-32 (50-58),
#   "never " 61-67 (116-122), "don't " 105-111 (160-166).
# The omission holds "nothing", a negating word no body deletion removes, so a check that read the
# snapshot between a deletion's ends, instead of the words the deletion took out, would warn for it.
# "have" keeps "never" off the word right after the cut. Until `v1-e06-t15` deleting the word after
# the word right after a cut read as a MANUAL_EDIT; that node's tests pin deletions beside a marker.

NEGATION_SOURCE: Final = (
    "Engineers met on Tuesday. The levee will not hold another spring flood. Officials said nothing new. "
    "Inspectors have never checked the north wall, and residents don't trust the new pumps."
)
NEGATION_RANGES: Final = ((26, 71), (100, 186))
NEGATION_EVIDENCE: Final = (
    "The levee will not hold another spring flood."
    "Inspectors have never checked the north wall, and residents don't trust the new pumps."
)
SOURCE_WORDS: Final = ("levee", "never", "don't", "Inspectors", "residents", "pumps", "Officials")
"""Words of the source that no warning or reason may carry: the output holds offsets, never evidence."""


@dataclass(frozen=True)
class VerifiedExport:
    world: VerificationWorld
    card: Card
    document: bytes


def verified_export(
    source_text: str,
    ranges: tuple[tuple[int, int], ...],
    evidence: str,
    card_of: Callable[[Card], Card] = lambda card: card,
) -> VerifiedExport:
    """A card cut from ``ranges`` of an invented source, VERIFIED, changed by ``card_of`` and exported to
    a .docx in the team profile. ``evidence`` is its hand-written ``evidence_text``."""
    world = VerificationWorld()
    source = world.add_source(source_text)
    card, result = run(world.verifier.verify_and_record(world.cut_card_from_ranges(source, ranges)))
    assert (result.status, card.evidence_text) == (VerificationStatus.VERIFIED, evidence)
    card = card_of(card)
    exporter = ExportService(
        articles=world.articles, clock=FixedClock(EXPORTED_AT), render_docx=render_cards_docx
    )
    return VerifiedExport(world, card, run(exporter.export_docx([card], profile=TEAM_DEFAULT)))


def negation_export(card_of: Callable[[Card], Card] = lambda card: card) -> VerifiedExport:
    """The invented negation card, VERIFIED, changed by ``card_of`` and exported."""
    return verified_export(NEGATION_SOURCE, NEGATION_RANGES, NEGATION_EVIDENCE, card_of)


@pytest.fixture(scope="module")
def negation_card() -> VerifiedExport:
    return negation_export()


def docx_verdict(
    export: VerifiedExport,
    *changes: Callable[[Document], None],
    world: VerificationWorld | None = None,
    source_words: tuple[str, ...] = SOURCE_WORDS,
) -> dict[str, Any]:
    """The one card's verdict on ``export`` changed by each of ``changes``, as `verify --json` gives it.

    ``source_words`` are words of the card's source that the report may not quote."""
    document = export.document
    for change in changes:
        document = edited(document, change)
    world = world or export.world
    use_case = VerifyManifest(
        verifier=world.verifier,
        articles=world.articles,
        format_profiles=lambda: load_format_profiles(PROFILES),
    )
    report = run(use_case.verify(document)).model_dump(mode="json")
    [verdict] = report["cards"]
    text = json.dumps(report)
    assert not [word for word in source_words if word in text], "the report quotes the evidence"
    return verdict


def negation_warnings(verdict: dict[str, Any]) -> list[tuple[str, tuple[int, int], tuple[int, int]]]:
    """Each warning's code, evidence_text range and snapshot range, in body order."""
    return [
        (
            warning["code"],
            (warning["evidence_range"]["start"], warning["evidence_range"]["end"]),
            (warning["snapshot_range"]["start"], warning["snapshot_range"]["end"]),
        )
        for warning in verdict.get("warnings", [])
    ]


def is_verified_without_reasons(verdict: dict[str, Any]) -> bool:
    return (verdict["status"], verdict["reasons"]) == ("VERIFIED", [])


@pytest.mark.parametrize(
    ("replacement", "evidence_range", "snapshot_range"),
    [
        pytest.param("", (15, 19), (41, 45), id="deleted"),
        pytest.param("… ", (15, 18), (41, 44), id="replaced-by-the-marker"),
    ],
)
def test_negation_a_deletion_that_removes_not_is_a_warning_with_its_ranges_on_a_verified_card(
    negation_card: VerifiedExport,
    replacement: str,
    evidence_range: tuple[int, int],
    snapshot_range: tuple[int, int],
) -> None:
    """Typing the marker over "not " keeps the space after it, so the deletion is "not" alone."""
    verdict = docx_verdict(negation_card, replace_in_evidence("not ", replacement))

    assert is_verified_without_reasons(verdict)
    assert negation_warnings(verdict) == [("NEGATION_REMOVED", evidence_range, snapshot_range)]


def test_negation_a_deletion_that_removes_no_negating_word_gives_no_warning(
    negation_card: VerifiedExport,
) -> None:
    verdict = docx_verdict(negation_card, replace_in_evidence("another ", ""))

    assert is_verified_without_reasons(verdict)
    assert "warnings" not in verdict


def test_negation_kept_while_the_words_either_side_of_it_are_cut_gives_no_warning(
    negation_card: VerifiedExport,
) -> None:
    """ "will " and "hold " go, "not" stays: two deletions, each beside the negation, neither through it."""
    verdict = docx_verdict(negation_card, replace_in_evidence("will ", ""), replace_in_evidence("hold ", ""))

    assert is_verified_without_reasons(verdict)
    assert "warnings" not in verdict


def test_negation_two_deletions_that_each_remove_one_give_two_warnings_in_body_order(
    negation_card: VerifiedExport,
) -> None:
    verdict = docx_verdict(negation_card, replace_in_evidence("never ", ""), replace_in_evidence("not ", ""))

    assert is_verified_without_reasons(verdict)
    assert negation_warnings(verdict) == [
        ("NEGATION_REMOVED", (15, 19), (41, 45)),
        ("NEGATION_REMOVED", (61, 67), (116, 122)),
    ]


def test_negation_a_contracted_negation_removed_is_a_warning(negation_card: VerifiedExport) -> None:
    """The edit policy counts any word ending in "n't" as a negation (`negation.NEGATION_SUFFIX`)."""
    verdict = docx_verdict(negation_card, replace_in_evidence("don't ", ""))

    assert is_verified_without_reasons(verdict)
    assert negation_warnings(verdict) == [("NEGATION_REMOVED", (105, 111), (160, 166))]


def test_negation_one_deletion_that_removes_two_is_one_warning(negation_card: VerifiedExport) -> None:
    """ "never checked the north wall, and residents don't " is one deletion: one warning, its whole range."""
    verdict = docx_verdict(
        negation_card, replace_in_evidence("never checked the north wall, and residents don't ", "")
    )

    assert is_verified_without_reasons(verdict)
    assert negation_warnings(verdict) == [("NEGATION_REMOVED", (61, 111), (116, 166))]


def across_the_cards_own_cut(document: Document) -> None:
    """ "spring flood.", the marker and "Inspectors " taken out: one deletion, either side of the cut."""
    before, marker, after = evidence_paragraph(document).runs
    assert before.text.endswith("spring flood.") and marker.text == MARKER
    assert after.text.startswith("Inspectors ")
    before.text = before.text.removesuffix("spring flood.")
    marker.text = ""
    after.text = after.text.removeprefix("Inspectors ")


def test_negation_a_deletion_across_the_cards_own_cut_reads_only_the_words_it_removed(
    negation_card: VerifiedExport,
) -> None:
    """Evidence [32, 56) is snapshot [58, 71) and [100, 111); "nothing", in the omission between, was
    not in the body to remove."""
    verdict = docx_verdict(negation_card, across_the_cards_own_cut)

    assert is_verified_without_reasons(verdict)
    assert "warnings" not in verdict


def from_not_to_never_across_the_cut(document: Document) -> None:
    """ "not hold another spring flood.", the marker and "Inspectors have never " taken out: one deletion."""
    before, marker, after = evidence_paragraph(document).runs
    assert before.text.endswith("not hold another spring flood.") and marker.text == MARKER
    assert after.text.startswith("Inspectors have never ")
    before.text = before.text.removesuffix("not hold another spring flood.")
    marker.text = ""
    after.text = after.text.removeprefix("Inspectors have never ")


def test_negation_one_deletion_across_the_cut_with_a_negation_either_side_is_one_warning(
    negation_card: VerifiedExport,
) -> None:
    """Evidence [15, 67) is snapshot [41, 71) and [100, 122): "not" in one, "never" in the other, one
    deletion, so one warning, which spans the omission between."""
    verdict = docx_verdict(negation_card, from_not_to_never_across_the_cut)

    assert is_verified_without_reasons(verdict)
    assert negation_warnings(verdict) == [("NEGATION_REMOVED", (15, 67), (41, 122))]


def test_negation_is_not_read_where_the_card_does_not_reproduce_its_snapshot() -> None:
    """The card says "now" where the source says "not"; deleting it removes no negation the body showed.

    The swap keeps the card's length, so only the verifier's exact comparison sees it. The words a
    deletion removed are read from the snapshot only when the verifier rebuilt the card's evidence from
    it exactly."""
    tampered = negation_export(
        lambda card: card.model_copy(
            update={"evidence_text": card.evidence_text.replace("will not", "will now")}
        )
    )

    verdict = docx_verdict(tampered, replace_in_evidence("now ", ""))

    assert (verdict["status"], verdict["reason_codes"]) == ("UNVERIFIED", ["TEXT_MISMATCH"])
    assert "warnings" not in verdict


def test_negation_is_not_read_where_the_card_was_cut_from_other_text() -> None:
    """A card whose text hash is not its snapshot's has offsets into some other text: the verifier does
    not rebuild its evidence at all, so nothing is read at them, even where the words still match."""
    other_text = negation_export(lambda card: card.model_copy(update={"normalized_text_hash": "a" * 64}))

    verdict = docx_verdict(other_text, replace_in_evidence("not ", ""))

    assert (verdict["status"], verdict["reason_codes"]) == ("UNVERIFIED", ["HASH_MISMATCH"])
    assert "warnings" not in verdict


def test_negation_warnings_and_interpolations_come_in_body_order(negation_card: VerifiedExport) -> None:
    """ "not " goes at evidence 15 and "[drainage]" is read before "pumps", evidence 125."""
    verdict = docx_verdict(
        negation_card,
        replace_in_evidence("new pumps", "new [drainage] pumps"),
        replace_in_evidence("not ", ""),
    )

    assert is_verified_without_reasons(verdict)
    assert [
        (warning["code"], warning.get("evidence_range"), warning["evidence_offset"])
        for warning in verdict["warnings"]
    ] == [
        ("NEGATION_REMOVED", {"start": 15, "end": 19}, None),
        ("INTERPOLATION_PRESENT", None, 125),
    ]
    # The ranges are a negation's alone: an interpolation's warning keeps the keys it had before them.
    assert [sorted(warning) for warning in verdict["warnings"]] == [
        ["code", "detail", "evidence_offset", "evidence_range", "snapshot_range"],
        ["code", "detail", "evidence_offset"],
    ]


def test_negation_is_not_read_without_the_cards_snapshot(negation_card: VerifiedExport) -> None:
    verdict = docx_verdict(negation_card, replace_in_evidence("not ", ""), world=VerificationWorld())

    assert (verdict["status"], verdict["reason_codes"]) == ("UNVERIFIED", ["SNAPSHOT_MISSING"])
    assert "warnings" not in verdict


# --------------------------------------------------------------------------------------------
# Node marker-side deletions (`v1-e06-t15`): a whole-word deletion beside a cut's marker is a deletion
# --------------------------------------------------------------------------------------------
#
# The card here has three cuts, all at sentence ends, so its body shows three markers. It is cut from
# an invented source, exported by ExportService and changed through python-docx; each test reads the
# body as `verify` does and checks both the comparison's ranges and the verdict. Offsets, counted by
# hand from MARKER_SOURCE:
#
#   snapshot   0-12    "Levees fail."                                      -> evidence   0-12
#   snapshot  12-39    " Engineers met on Tuesday. "            cut 1, drawn at evidence 12
#   snapshot  39-84    "The levee will not hold another spring flood."     -> evidence  12-57
#   snapshot  84-113   " Officials said nothing new. "          cut 2, drawn at evidence 57
#   snapshot 113-132   "Repairs never came."                               -> evidence  57-76
#   snapshot 132-153   " The budget is gone. "                  cut 3, drawn at evidence 76
#   snapshot 153-186   "Nobody has checked the north wall"                 -> evidence  76-109
#   snapshot 186-197   " since May."                            after the card
#
# so a snapshot offset is the evidence offset plus 0, 27, 56 and 77 in the four pieces, and a body
# offset is the evidence offset plus 0, 3, 6 and 9 (each marker, " … ", is three characters). Words:
#   piece 1: "Levees" 0-6, "fail" 7-11, "." 11
#   piece 2: "The" 12-15, "levee" 16-21, "spring" 44-50, "flood" 51-56, "." 56
#   piece 3: "Repairs" 57-64, "never" 65-70, "came" 71-75, "." 75   (between two cuts)
#   piece 4: "Nobody" 76-82, "has" 83-86, "north" 99-104, "wall" 105-109   (the body's last word)
#
# Where a space beside a marker can be the card's own space, it is read as the card's: deleting "The "
# right after cut 1 leaves ". … levee", whose one space after the marker is the card's space after
# "The", so the deletion is "The" [12, 15). That is how t07 already reads a marker typed over words
# ("… " over "not " is the deletion "not"), and it keeps every deletion as small as the body allows.

MARKER_SOURCE: Final = (
    "Levees fail. Engineers met on Tuesday. The levee will not hold another spring flood. "
    "Officials said nothing new. Repairs never came. The budget is gone. "
    "Nobody has checked the north wall since May."
)
MARKER_RANGES: Final = ((0, 12), (39, 84), (113, 132), (153, 186))
MARKER_EVIDENCE: Final = (
    "Levees fail."
    "The levee will not hold another spring flood."
    "Repairs never came."
    "Nobody has checked the north wall"
)
MARKER_RENDERED: Final = (
    "Levees fail. … The levee will not hold another spring flood. … Repairs never came. … "
    "Nobody has checked the north wall"
)
MARKER_SOURCE_WORDS: Final = ("Levees", "levee", "flood", "Repairs", "Nobody", "north", "Officials", "budget")


@pytest.fixture(scope="module")
def marker_card() -> VerifiedExport:
    export = verified_export(MARKER_SOURCE, MARKER_RANGES, MARKER_EVIDENCE)
    assert body_of(export.document).cards[0].paragraphs[-1].text == MARKER_RENDERED
    return export


def marker_comparison(export: VerifiedExport, *changes: Callable[[Document], None]) -> BodyComparison:
    """The body diff of ``export`` changed by each of ``changes``, read as `verify` reads it."""
    document = export.document
    for change in changes:
        document = edited(document, change)
    [shown] = body_of(document).cards
    return compare_body(export.card, body_evidence(export.card, shown), MARKER)


def marker_verdict(export: VerifiedExport, *changes: Callable[[Document], None]) -> dict[str, Any]:
    return docx_verdict(export, *changes, source_words=MARKER_SOURCE_WORDS)


@pytest.mark.parametrize(
    ("old", "new", "deletion"),
    [
        pytest.param("Levees ", "", (0, 7), id="the-first-word-of-the-body-one-word-before-cut-1"),
        pytest.param(" fail", "", (6, 11), id="right-before-cut-1"),
        pytest.param("The levee", "levee", (12, 15), id="right-after-cut-1"),
        pytest.param("levee ", "", (16, 22), id="one-word-after-cut-1"),
        pytest.param("spring ", "", (44, 51), id="one-word-before-cut-2"),
        pytest.param(" flood", "", (50, 56), id="right-before-cut-2"),
        pytest.param("Repairs ", "", (57, 64), id="right-after-cut-2-between-two-cuts"),
        pytest.param("never ", "", (65, 71), id="one-word-after-cut-2-and-before-cut-3"),
        pytest.param(" came", "", (70, 75), id="right-before-cut-3-between-two-cuts"),
        pytest.param(
            "Repairs never came.", "", (57, 76), id="all-between-two-cuts-leaving-the-markers-together"
        ),
        pytest.param("Nobody ", "", (76, 82), id="right-after-cut-3"),
        pytest.param("has ", "", (83, 87), id="one-word-after-cut-3"),
        pytest.param(" wall", "", (104, 109), id="the-last-word-of-the-body"),
    ],
)
def test_marker_a_whole_word_deleted_beside_a_cut_is_a_deletion_with_its_range(
    marker_card: VerifiedExport, old: str, new: str, deletion: tuple[int, int]
) -> None:
    comparison = marker_comparison(marker_card, replace_in_evidence(old, new))

    assert (comparison.manual_edits, comparison.deletions) == ((), (CharacterRange(*deletion),))
    assert is_verified_without_reasons(marker_verdict(marker_card, replace_in_evidence(old, new)))


def test_marker_deletions_beside_two_different_cuts_are_two_deletions(marker_card: VerifiedExport) -> None:
    """ "levee " one word after cut 1 and "has " one word after cut 3, in one body."""
    changes = (replace_in_evidence("levee ", ""), replace_in_evidence("has ", ""))

    comparison = marker_comparison(marker_card, *changes)

    assert (comparison.manual_edits, comparison.deletions) == (
        (),
        (CharacterRange(16, 22), CharacterRange(83, 87)),
    )
    assert is_verified_without_reasons(marker_verdict(marker_card, *changes))


def test_marker_the_second_word_after_the_news_cards_cut_deleted_is_a_deletion(card: Card) -> None:
    """t07's own reproduction: "biologists " is evidence [121, 132), the second word after the cut at 108.
    "Conservation " right after the cut is "Conservation" [108, 120), its space read as the marker's."""
    assert compare_body(card, RENDERED_EVIDENCE.replace("biologists ", "", 1), MARKER).deletions == (
        CharacterRange(121, 132),
    )
    assert compare_body(card, RENDERED_EVIDENCE.replace("Conservation ", "", 1), MARKER).deletions == (
        CharacterRange(108, 120),
    )


@pytest.mark.parametrize(
    ("old", "new", "evidence_range", "body_range"),
    [
        pytest.param("The levee", "A levee", (12, 15), (15, 16), id="letters-altered-right-after-cut-1"),
        pytest.param(
            "levee will", "levees will", (16, 21), (19, 25), id="letters-altered-one-word-after-cut-1"
        ),
        pytest.param(" flood.", " floods.", (51, 56), (54, 60), id="letters-altered-right-before-cut-2"),
        pytest.param("came.", "come.", (71, 75), (77, 81), id="letters-altered-between-two-cuts"),
        pytest.param("fail.", "fail again.", (11, 11), (11, 17), id="a-word-added-right-before-cut-1"),
        pytest.param(
            "Nobody has", "Truly Nobody has", (76, 76), (85, 91), id="a-word-added-right-after-cut-3"
        ),
        pytest.param("flood.", "flood. Sadly", (57, 57), (60, 66), id="a-word-added-right-before-cut-2"),
        pytest.param(
            "levee will", "levee levee will", (22, 22), (25, 31), id="a-word-repeated-one-word-after-cut-1"
        ),
        pytest.param(
            "another spring",
            "another … late spring",
            (43, 43),
            (46, 53),
            id="a-marker-then-a-word-where-nothing-was-cut",
        ),
        pytest.param(
            "another spring",
            "another late … spring",
            (44, 44),
            (47, 54),
            id="a-word-then-a-marker-where-nothing-was-cut",
        ),
    ],
)
def test_marker_a_changed_or_added_word_beside_a_cut_is_a_manual_edit(
    marker_card: VerifiedExport,
    old: str,
    new: str,
    evidence_range: tuple[int, int],
    body_range: tuple[int, int],
) -> None:
    """Body ranges: "A" 15-16, "levees" 19-25, "floods" 54-60, "come" 77-81; " again" 11-17; "Truly "
    85-91, after cut 3's marker (82-85) and before "Nobody" (76); " Sadly" 60-66, after "flood." and
    before cut 2's marker, at evidence 57; the second "levee " 25-31, before "will" (22). The card's own
    marker beside a changed word is never part of the manual edit's body range; a marker typed where
    nothing was cut is: " … late" 46-53 before the space after "another" (43), "late … " 47-54 before
    "spring" (44)."""
    comparison = marker_comparison(marker_card, replace_in_evidence(old, new))

    assert comparison.manual_edits == (
        ManualEdit(CharacterRange(*evidence_range), CharacterRange(*body_range)),
    )
    assert comparison.deletions == ()
    verdict = marker_verdict(marker_card, replace_in_evidence(old, new))
    assert (verdict["status"], verdict["reason_codes"]) == ("UNVERIFIED", ["MANUAL_EDIT"])


def test_marker_a_word_moved_across_a_cut_is_a_manual_edit_never_a_deletion(
    marker_card: VerifiedExport,
) -> None:
    """ "The" taken from after cut 1 and typed before its marker: "Levees fail. The … levee will"."""
    changes = (replace_in_evidence("fail.", "fail. The"), replace_in_evidence("The levee", "levee"))

    comparison = marker_comparison(marker_card, *changes)

    assert comparison.manual_edits != ()
    assert comparison.deletions == ()
    verdict = marker_verdict(marker_card, *changes)
    assert (verdict["status"], verdict["reason_codes"]) == ("UNVERIFIED", ["MANUAL_EDIT"])


@pytest.mark.parametrize(
    ("old", "evidence_range", "snapshot_range"),
    [
        pytest.param("never ", (65, 71), (121, 127), id="one-word-after-cut-2"),
        pytest.param("Nobody ", (76, 82), (153, 159), id="right-after-cut-3"),
    ],
)
def test_marker_a_negation_deleted_beside_a_cut_is_a_warning_on_a_verified_card(
    marker_card: VerifiedExport,
    old: str,
    evidence_range: tuple[int, int],
    snapshot_range: tuple[int, int],
) -> None:
    """ "never" is snapshot [121, 126) and "Nobody" [153, 159); the omission before each holds "nothing",
    which no deletion here removes."""
    verdict = marker_verdict(marker_card, replace_in_evidence(old, ""))

    assert is_verified_without_reasons(verdict)
    assert negation_warnings(verdict) == [("NEGATION_REMOVED", evidence_range, snapshot_range)]


def test_marker_an_ellipsis_the_source_itself_prints_is_quoted_text(card: Card) -> None:
    """A source may print " … " itself; the body's copy is the source's, and a word deleted after it is a
    deletion. "then " is evidence [14, 19). Only the comparison is under test, so the card's text is
    swapped without re-cutting it."""
    text = "Prices rose … then fell sharply."
    quoted = card.model_copy(update={"evidence_text": text, "omitted_ranges": ()})

    untouched = compare_body(quoted, text, MARKER)
    deleted = compare_body(quoted, text.replace("then ", "", 1), MARKER)

    assert (untouched.manual_edits, untouched.deletions) == ((), ())
    assert (deleted.manual_edits, deleted.deletions) == ((), (CharacterRange(14, 19),))

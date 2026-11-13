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
    HiddenCut,
    ManualEdit,
    body_evidence,
    compare_body,
    match_body_cards,
)
from debate_core.evidence.edit_policy import apply_quotation_edit
from debate_core.evidence.edits import AddInterpolation, QuotationEdit
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
    ],
    ids=["marker kept, its space doubled", "marker kept"],
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
    """A profile whose marker is three full stops: one typed where words were cut follows the policy.
    Until `v1-e06-t17` the default profile refused the same body; since the coach's decision of
    2026-11-13 it reads " ... " as its own " … " (test_typed_marker_is_read_for_the_ellipsis_profile_only)."""
    body = FIRST_SENTENCE + " ... " + CRITICS_SENTENCE + LAST_PART

    assert compare_body(card, body, " ... ").manual_edits == ()


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
    edits: tuple[QuotationEdit, ...] = (),
) -> VerifiedExport:
    """A card cut from ``ranges`` of an invented source, VERIFIED, changed by ``card_of`` and exported to
    a .docx in the team profile. ``evidence`` is its hand-written ``evidence_text``. Each of ``edits`` is
    applied first through E03's edit API, and the edited card is verified again (`v1-e06-t17`)."""
    world = VerificationWorld()
    source = world.add_source(source_text)
    card, result = run(world.verifier.verify_and_record(world.cut_card_from_ranges(source, ranges)))
    for edit in edits:
        card, result = run(
            world.verifier.verify_and_record(
                apply_quotation_edit(card, edit, source.snapshot, source.normalized).card
            )
        )
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


# --------------------------------------------------------------------------------------------
# Node joined words (`v1-e06-t16`): an untouched export whose cut joins two words verifies
# --------------------------------------------------------------------------------------------
#
# ``evidence_text`` joins a card's kept pieces with nothing between them, so a piece that ends in a
# word followed by one that starts with a word reads as one word in the card ("holdnever"), while the
# body shows the two words either side of the profile's marker. The card here is cut from an invented
# source at three such joins, exported by ExportService and changed through python-docx. Offsets,
# counted by hand from JOIN_SOURCE:
#
#   snapshot   0-9     "Engineers"                                         -> evidence   0-9
#   snapshot   9-30    " met on Tuesday. The "                  cut 1, drawn at evidence  9
#   snapshot  30-49    "levee will not hold"                               -> evidence   9-28
#   snapshot  49-93    " another spring flood, they warned. Repairs "      cut 2, at evidence 28
#   snapshot  93-116   "never came to the north"                           -> evidence  28-51
#   snapshot 116-139   " wall before the storm "                cut 3, drawn at evidence 51
#   snapshot 139-145   "season"                                            -> evidence  51-57
#   snapshot 145-146   "."                                      after the card
#
# so a snapshot offset is the evidence offset plus 0, 21, 65 and 88 in the four pieces, and a body
# offset is the evidence offset plus 0, 3, 6 and 9. Words, evidence (body):
#   piece 1: "Engineers" 0-9 (0-9), the body's first word, right before join 1
#   piece 2: "levee" 9-14 (12-17), "will" 15-19, "not" 20-23 (23-26), "hold" 24-28 (27-31)
#   piece 3: "never" 28-33 (34-39), "came" 34-38 (40-44), "north" 46-51 (52-57)
#   piece 4: "season" 51-57 (60-66), the body's last word, right after join 3
#
# The joins are at the body's start (join 1), its middle (join 2, with "not" one word before it and
# "never" right after it) and its end (join 3). As in the t15 section, a space beside a marker that can
# be the card's own space is read as the card's, so deleting " hold" before join 2 is the deletion
# "hold", and the space before the marker stands for the card's space after "not".

JOIN_SOURCE: Final = (
    "Engineers met on Tuesday. The levee will not hold another spring flood, they warned. "
    "Repairs never came to the north wall before the storm season."
)
JOIN_RANGES: Final = ((0, 9), (30, 49), (93, 116), (139, 145))
JOIN_EVIDENCE: Final = "Engineerslevee will not holdnever came to the northseason"
JOIN_RENDERED: Final = "Engineers … levee will not hold … never came to the north … season"
JOIN_SOURCE_WORDS: Final = ("Engineers", "levee", "north", "season", "Tuesday", "warned", "Repairs", "storm")

PM_JOIN_SOURCE: Final = "The levee will not hold another spring flood, engineers said."
"""The PM's reproduction (v1-e06-t15's follow-up 1): "hold" [19, 23) is joined to "flood" [23, 28)."""


@pytest.fixture(scope="module")
def join_card() -> VerifiedExport:
    export = verified_export(JOIN_SOURCE, JOIN_RANGES, JOIN_EVIDENCE)
    assert body_of(export.document).cards[0].paragraphs[-1].text == JOIN_RENDERED
    return export


def join_verdict(export: VerifiedExport, *changes: Callable[[Document], None]) -> dict[str, Any]:
    return docx_verdict(export, *changes, source_words=JOIN_SOURCE_WORDS)


def retyped_marker(index: int, text: str) -> Callable[[Document], None]:
    """The ``index``-th marker run of the evidence (from 0) rewritten as ``text``."""

    def change(document: Document) -> None:
        markers = [each for each in evidence_paragraph(document).runs if each.text == MARKER]
        markers[index].text = text

    return change


@pytest.mark.parametrize(
    ("source", "ranges", "evidence", "rendered"),
    [
        pytest.param(
            JOIN_SOURCE,
            ((0, 9), (30, 49)),
            "Engineerslevee will not hold",
            "Engineers … levee will not hold",
            id="at-the-start-of-the-body",
        ),
        pytest.param(
            JOIN_SOURCE,
            ((30, 49), (93, 116)),
            "levee will not holdnever came to the north",
            "levee will not hold … never came to the north",
            id="in-the-middle-of-the-body",
        ),
        pytest.param(
            JOIN_SOURCE,
            ((93, 116), (139, 145)),
            "never came to the northseason",
            "never came to the north … season",
            id="at-the-end-of-the-body",
        ),
        pytest.param(JOIN_SOURCE, JOIN_RANGES, JOIN_EVIDENCE, JOIN_RENDERED, id="three-joins-in-one-card"),
        pytest.param(
            PM_JOIN_SOURCE,
            ((0, 23), (39, 45)),
            "The levee will not holdflood,",
            "The levee will not hold … flood,",
            id="the-pms-reproduction",
        ),
    ],
)
def test_join_an_untouched_export_whose_cut_joins_two_words_verifies(
    source: str, ranges: tuple[tuple[int, int], ...], evidence: str, rendered: str
) -> None:
    export = verified_export(source, ranges, evidence)
    assert body_of(export.document).cards[0].paragraphs[-1].text == rendered

    comparison = marker_comparison(export)

    assert comparison == BodyComparison(manual_edits=(), interpolations=(), deletions=())
    assert is_verified_without_reasons(docx_verdict(export, source_words=("levee", "flood", "north")))


@pytest.mark.parametrize(
    ("change", "evidence_range", "body_range"),
    [
        pytest.param(
            replace_in_evidence("Engineers", "Engineer"),
            (0, 9),
            (0, 8),
            id="letters-altered-right-before-join-1",
        ),
        pytest.param(
            replace_in_evidence("levee ", "levees "),
            (9, 14),
            (12, 18),
            id="letters-altered-right-after-join-1",
        ),
        pytest.param(
            replace_in_evidence("hold", "holds"), (24, 28), (27, 32), id="letters-altered-right-before-join-2"
        ),
        pytest.param(
            replace_in_evidence("never", "ever"), (28, 33), (34, 38), id="letters-altered-right-after-join-2"
        ),
        pytest.param(
            replace_in_evidence("season", "seasons"),
            (51, 57),
            (60, 67),
            id="letters-altered-right-after-join-3",
        ),
        pytest.param(
            replace_in_evidence("never", "now never"),
            (28, 28),
            (34, 38),
            id="a-word-added-right-after-join-2",
        ),
        pytest.param(
            replace_in_evidence("hold", "hold now"), (28, 28), (31, 35), id="a-word-added-right-before-join-2"
        ),
    ],
)
def test_join_a_changed_or_added_word_beside_a_join_is_a_manual_edit(
    join_card: VerifiedExport,
    change: Callable[[Document], None],
    evidence_range: tuple[int, int],
    body_range: tuple[int, int],
) -> None:
    """Body ranges: "Engineer" 0-8, before join 1's marker; "levees" 12-18 and "holds" 27-32; "ever" 34-38
    after join 2's marker (31-34); "seasons" 60-67; "now " 34-38 after join 2's marker and " now" 31-35
    before it, both at evidence 28. Taking join 2's marker out ("holdnever") was a case here until
    `v1-e06-t17`, which reads it as a hidden cut (test_hidden_cut_a_marker_taken_out_at_a_word_join)."""
    comparison = marker_comparison(join_card, change)

    assert comparison.manual_edits == (
        ManualEdit(CharacterRange(*evidence_range), CharacterRange(*body_range)),
    )
    assert comparison.deletions == ()
    verdict = join_verdict(join_card, change)
    assert (verdict["status"], verdict["reason_codes"]) == ("UNVERIFIED", ["MANUAL_EDIT"])


@pytest.mark.parametrize(
    ("old", "deletion"),
    [
        pytest.param("Engineers", (0, 9), id="the-first-word-of-the-body-right-before-join-1"),
        pytest.param("levee ", (9, 14), id="right-after-join-1"),
        pytest.param("will ", (15, 20), id="one-word-after-join-1"),
        pytest.param(" hold", (24, 28), id="right-before-join-2"),
        pytest.param("came ", (34, 39), id="one-word-after-join-2"),
        pytest.param(" north", (46, 51), id="right-before-join-3"),
        pytest.param("season", (51, 57), id="the-last-word-of-the-body-right-after-join-3"),
    ],
)
def test_join_a_whole_word_deleted_beside_a_join_is_a_deletion_with_its_range(
    join_card: VerifiedExport, old: str, deletion: tuple[int, int]
) -> None:
    """ "levee " right after join 1 is "levee" [9, 14): the marker's space after it stands for the card's
    space after "levee". " hold" and " north" before a marker leave the card's space before them in front
    of the marker, so each is the word alone. A deletion one word further on keeps its own space. The
    first and last words leave their marker at the body's edge, which stands for the deletion's cut."""
    comparison = marker_comparison(join_card, replace_in_evidence(old, ""))

    assert (comparison.manual_edits, comparison.deletions) == ((), (CharacterRange(*deletion),))
    verdict = join_verdict(join_card, replace_in_evidence(old, ""))
    assert is_verified_without_reasons(verdict)
    assert negation_warnings(verdict) == []


@pytest.mark.parametrize(
    ("old", "evidence_range", "snapshot_range"),
    [
        pytest.param("never ", (28, 33), (93, 98), id="right-after-join-2"),
        pytest.param("not ", (20, 24), (41, 45), id="one-word-before-join-2"),
    ],
)
def test_join_a_negation_deleted_beside_a_join_is_a_warning_on_a_verified_card(
    join_card: VerifiedExport,
    old: str,
    evidence_range: tuple[int, int],
    snapshot_range: tuple[int, int],
) -> None:
    """ "never" is snapshot [93, 98), right after join 2, its space read as the marker's; "not " is
    snapshot [41, 45), a word clear of the marker, so its own space goes with it."""
    verdict = join_verdict(join_card, replace_in_evidence(old, ""))

    assert is_verified_without_reasons(verdict)
    assert negation_warnings(verdict) == [("NEGATION_REMOVED", evidence_range, snapshot_range)]


# A marker typed with other spacing (v1-e06-t15's follow-up 2). The student retypes a marker's run; the
# card's own space beside it is read as the card's only where the body still has an ordinary space
# there, so with no ordinary space after the marker, "never " deleted right after join 2 is evidence
# [28, 34), its space included, and with one there it is "never" [28, 33). A word one further on keeps
# its own space whatever the marker's spacing: "will " [15, 20) after join 1, "came " [34, 39) after
# join 2. Two spaces each side of the marker could be paired with the card's spaces either side of
# "never" and read "came " deleted as a word moved, until the marker's whole spacing was one unit.

OTHER_SPACINGS: Final = (
    pytest.param(" …", id="one-space-before"),
    pytest.param("… ", id="one-space-after"),
    pytest.param("…", id="no-spaces"),
    pytest.param(" … ", id="non-breaking-spaces"),
    pytest.param("  …  ", id="two-spaces-each-side"),
)


@pytest.mark.parametrize("spacing", OTHER_SPACINGS)
def test_join_markers_retyped_with_other_spacing_verify_untouched(
    join_card: VerifiedExport, spacing: str
) -> None:
    """All three markers retyped: each change retypes the first marker still drawn as the profile's."""
    changes = tuple(retyped_marker(0, spacing) for _ in range(3))

    comparison = marker_comparison(join_card, *changes)

    assert comparison == BodyComparison(manual_edits=(), interpolations=(), deletions=())
    assert is_verified_without_reasons(join_verdict(join_card, *changes))


@pytest.mark.parametrize("spacing", OTHER_SPACINGS)
@pytest.mark.parametrize(
    ("marker", "old", "deletion"),
    [
        pytest.param(0, "will ", (15, 20), id="one-word-after-join-1"),
        pytest.param(1, "came ", (34, 39), id="one-word-after-join-2"),
    ],
)
def test_join_a_word_deleted_one_word_after_a_retyped_marker_is_a_deletion(
    join_card: VerifiedExport, spacing: str, marker: int, old: str, deletion: tuple[int, int]
) -> None:
    changes = (retyped_marker(marker, spacing), replace_in_evidence(old, ""))

    comparison = marker_comparison(join_card, *changes)

    assert (comparison.manual_edits, comparison.deletions) == ((), (CharacterRange(*deletion),))
    assert is_verified_without_reasons(join_verdict(join_card, *changes))


@pytest.mark.parametrize(
    ("spacing", "deletion"),
    [
        pytest.param(" …", (28, 34), id="one-space-before"),
        pytest.param("… ", (28, 33), id="one-space-after"),
        pytest.param("…", (28, 34), id="no-spaces"),
        pytest.param(" … ", (28, 34), id="non-breaking-spaces"),
        pytest.param("  …  ", (28, 33), id="two-spaces-each-side"),
    ],
)
def test_join_a_negation_deleted_right_after_a_retyped_marker_is_a_warning(
    join_card: VerifiedExport, spacing: str, deletion: tuple[int, int]
) -> None:
    """ "never" is snapshot [93, 98) and its space 98; the snapshot range is the deletion's, plus 65."""
    changes = (retyped_marker(1, spacing), replace_in_evidence("never ", ""))

    comparison = marker_comparison(join_card, *changes)

    assert (comparison.manual_edits, comparison.deletions) == ((), (CharacterRange(*deletion),))
    verdict = join_verdict(join_card, *changes)
    assert is_verified_without_reasons(verdict)
    snapshot = (deletion[0] + 65, deletion[1] + 65)
    assert negation_warnings(verdict) == [("NEGATION_REMOVED", deletion, snapshot)]


# --------------------------------------------------------------------------------------------
# Node cuts always shown (`v1-e06-t17`): a hidden cut is named, a mid-word anchor verifies, and a
# marker typed as " ... " is the marker
# --------------------------------------------------------------------------------------------
#
# Three sections, each on a card above: t15's marker card (MARKER_SOURCE, whose cuts join a full stop
# to a capital), t16's join card (JOIN_SOURCE, whose cuts join a word to a word) and t07's news card.
#
# Hidden cuts. A body that takes a cut's marker out shows the card's characters with nothing where
# the cut is. A hidden cut is named by its evidence offset (the cut's omission offset) and the body
# offset where its marker should be. On the marker card, cut 1 is evidence 12, cut 2 is 57 and cut 3
# is 76; with one marker taken out, the body offset is the evidence offset plus 3 for each marker still
# drawn before it, so 12, 60 and 82. On the join card, join 1 is 9 (body 9 with its marker out), join 2
# is 28 (body 31) and join 3 is 51 (body 57).
#
# Interpolation anchors inside a word. Each card here is the join card with an interpolation "s"
# added through E03's edit API, so the body shows "[s]" (three characters) inside the word:
#   anchor 11 inside "levee" [9, 14), right after join 1: "le[s]vee" is body 12-20
#   anchor 30 inside "never" [28, 33), right after join 2: "ne[s]ver" is body 34-42
#   anchor 54 inside "season" [51, 57), the body's last word: "sea[s]son" is body 60-69
#
# Typed markers (the coach's decision of 2026-11-13). Three full stops with whitespace either side read
# as the profile's marker; without it they are three full stops. On the marker card the dots typed at
# cut 1 sit at body 12: "..." is 12-15, " ..." and "... " are 12-16, " .... " 12-18. On the join card
# "..." at join 2 is body 31-34. "another" is marker-card evidence 36-43 and body 39-46; " ... " typed
# for the space after it puts its dots and the space after them at body 47-51, before "spring" (44).


def blanked_run(text: str) -> Callable[[Document], None]:
    """The one evidence run whose whole text is ``text`` emptied, as deleting it in Word does."""

    def change(document: Document) -> None:
        [run_] = [each for each in evidence_paragraph(document).runs if each.text == text]
        run_.text = ""

    return change


def anchored_export(anchor: int) -> VerifiedExport:
    """The join card with the interpolation "s" added at ``anchor`` through E03's edit API, re-verified."""
    return verified_export(
        JOIN_SOURCE, JOIN_RANGES, JOIN_EVIDENCE, edits=(AddInterpolation(anchor=anchor, text="s"),)
    )


ANCHORS_INSIDE_WORDS: Final = (
    pytest.param(
        11, "Engineers … le[s]vee will not hold … never came to the north … season", id="inside-levee"
    ),
    pytest.param(
        30, "Engineers … levee will not hold … ne[s]ver came to the north … season", id="inside-never"
    ),
    pytest.param(
        54, "Engineers … levee will not hold … never came to the north … sea[s]son", id="inside-season"
    ),
)


@pytest.mark.parametrize(("anchor", "rendered"), ANCHORS_INSIDE_WORDS)
def test_anchor_inside_a_word_verifies_on_an_untouched_export(anchor: int, rendered: str) -> None:
    """The PM's case is "inside-levee": ManualEdit(evidence [9, 14), body [12, 20)) before this node."""
    export = anchored_export(anchor)
    assert body_of(export.document).cards[0].paragraphs[-1].text == rendered

    comparison = marker_comparison(export)

    assert comparison == BodyComparison(
        manual_edits=(),
        interpolations=(BodyInterpolation(anchor=anchor, length=1, recorded=True),),
        deletions=(),
    )
    verdict = docx_verdict(export, source_words=JOIN_SOURCE_WORDS)
    assert is_verified_without_reasons(verdict)
    assert [(item["code"], item["evidence_offset"]) for item in verdict["warnings"]] == [
        ("INTERPOLATION_PRESENT", anchor)
    ]


@pytest.mark.parametrize(("anchor", "rendered"), ANCHORS_INSIDE_WORDS)
def test_anchor_inside_a_word_whose_interpolation_the_body_leaves_out_verifies(
    anchor: int, rendered: str
) -> None:
    """The word is the source's again, as an interpolation left out at a word's edge is."""
    export = anchored_export(anchor)

    comparison = marker_comparison(export, blanked_run("[s]"))

    assert comparison == BodyComparison(manual_edits=(), interpolations=(), deletions=())
    verdict = docx_verdict(export, blanked_run("[s]"), source_words=JOIN_SOURCE_WORDS)
    assert is_verified_without_reasons(verdict)
    assert verdict.get("warnings", []) == []


@pytest.mark.parametrize(
    ("change", "body_range"),
    [
        pytest.param(replace_in_evidence("le", ""), (12, 18), id="the-letters-before-the-anchor"),
        pytest.param(replace_in_evidence("vee will", " will"), (12, 17), id="the-letters-after-the-anchor"),
    ],
)
def test_anchor_inside_a_word_letters_deleted_on_one_side_of_it_are_a_manual_edit(
    change: Callable[[Document], None], body_range: tuple[int, int]
) -> None:
    """ "[s]vee" is body 12-18 and "le[s]" 12-17, both after join 1's marker (9-12): "levee" [9, 14)
    changed, never a deletion of letters beside an interpolation."""
    export = anchored_export(11)

    comparison = marker_comparison(export, change)

    assert comparison.manual_edits == (ManualEdit(CharacterRange(9, 14), CharacterRange(*body_range)),)
    assert comparison.deletions == ()
    verdict = docx_verdict(export, change, source_words=JOIN_SOURCE_WORDS)
    assert (verdict["status"], verdict["reason_codes"]) == ("UNVERIFIED", ["MANUAL_EDIT"])


def test_anchor_inside_a_word_deleted_with_its_interpolation_is_a_deletion() -> None:
    """ "levee " right after join 1, as t16's "right-after-join-1" deletes it: "levee" [9, 14)."""
    export = anchored_export(11)
    changes = (replace_in_evidence("le", ""), blanked_run("[s]"), replace_in_evidence("vee will", "will"))

    comparison = marker_comparison(export, *changes)

    assert comparison == BodyComparison(
        manual_edits=(), interpolations=(), deletions=(CharacterRange(9, 14),)
    )
    assert is_verified_without_reasons(docx_verdict(export, *changes, source_words=JOIN_SOURCE_WORDS))


def test_anchor_a_bracket_inside_a_word_the_card_does_not_record_is_a_manual_edit(
    join_card: VerifiedExport,
) -> None:
    """ "le[s]vee" typed into the join card, which records no interpolation: t16's measured ranges."""
    change = replace_in_evidence("levee", "le[s]vee")

    comparison = marker_comparison(join_card, change)

    assert comparison.manual_edits == (ManualEdit(CharacterRange(9, 14), CharacterRange(12, 20)),)
    verdict = join_verdict(join_card, change)
    assert (verdict["status"], verdict["reason_codes"]) == ("UNVERIFIED", ["MANUAL_EDIT"])


NBSP: Final = chr(0xA0)
SPACED_DOTS: Final = (
    pytest.param(" ... ", id="one-space-each-side"),
    pytest.param("  ...  ", id="two-spaces-each-side"),
    pytest.param(f"{NBSP}...{NBSP}", id="non-breaking-spaces"),
)


@pytest.mark.parametrize("typed", SPACED_DOTS)
@pytest.mark.parametrize(
    ("source", "ranges", "evidence", "source_words"),
    [
        pytest.param(MARKER_SOURCE, MARKER_RANGES, MARKER_EVIDENCE, MARKER_SOURCE_WORDS, id="marker-card"),
        pytest.param(JOIN_SOURCE, JOIN_RANGES, JOIN_EVIDENCE, JOIN_SOURCE_WORDS, id="join-card"),
    ],
)
def test_typed_marker_of_spaced_full_stops_at_every_cut_verifies(
    source: str,
    ranges: tuple[tuple[int, int], ...],
    evidence: str,
    source_words: tuple[str, ...],
    typed: str,
) -> None:
    """All three markers retyped: each change retypes the first marker still drawn as the profile's."""
    export = verified_export(source, ranges, evidence)
    changes = tuple(retyped_marker(0, typed) for _ in range(3))

    comparison = marker_comparison(export, *changes)

    assert comparison == BodyComparison(manual_edits=(), interpolations=(), deletions=())
    assert is_verified_without_reasons(docx_verdict(export, *changes, source_words=source_words))


@pytest.mark.parametrize(
    ("index", "old", "new", "deletion"),
    [
        pytest.param(0, "The levee", "levee", (12, 15), id="marker-card-right-after-cut-1"),
        pytest.param(1, "Repairs ", "", (57, 64), id="marker-card-right-after-cut-2"),
    ],
)
def test_typed_marker_beside_a_word_deleted_on_the_marker_card_is_a_deletion(
    marker_card: VerifiedExport, index: int, old: str, new: str, deletion: tuple[int, int]
) -> None:
    """t15's ranges for the profile's marker: the space after the dots stands for the card's own."""
    changes = (retyped_marker(index, " ... "), replace_in_evidence(old, new))

    comparison = marker_comparison(marker_card, *changes)

    assert (comparison.manual_edits, comparison.deletions) == ((), (CharacterRange(*deletion),))
    assert is_verified_without_reasons(marker_verdict(marker_card, *changes))


@pytest.mark.parametrize(
    ("old", "deletion", "negations"),
    [
        pytest.param("came ", (34, 39), [], id="one-word-after-join-2"),
        pytest.param(
            "never ", (28, 33), [("NEGATION_REMOVED", (28, 33), (93, 98))], id="a-negation-right-after-join-2"
        ),
    ],
)
def test_typed_marker_beside_a_word_deleted_on_the_join_card_is_a_deletion(
    join_card: VerifiedExport,
    old: str,
    deletion: tuple[int, int],
    negations: list[tuple[str, tuple[int, int], tuple[int, int]]],
) -> None:
    """t16's ranges for the profile's marker; "never" is snapshot [93, 98)."""
    changes = (retyped_marker(1, " ... "), replace_in_evidence(old, ""))

    comparison = marker_comparison(join_card, *changes)

    assert (comparison.manual_edits, comparison.deletions) == ((), (CharacterRange(*deletion),))
    verdict = join_verdict(join_card, *changes)
    assert is_verified_without_reasons(verdict)
    assert negation_warnings(verdict) == negations


@pytest.mark.parametrize(
    ("card_name", "index", "typed", "evidence_range", "body_range"),
    [
        pytest.param("marker", 0, "...", (12, 12), (12, 15), id="no-spaces-at-cut-1"),
        pytest.param("marker", 0, " ...", (12, 12), (12, 16), id="a-space-before-only-at-cut-1"),
        pytest.param("marker", 0, "... ", (12, 12), (12, 16), id="a-space-after-only-at-cut-1"),
        pytest.param("marker", 0, " .... ", (12, 12), (12, 18), id="four-full-stops-at-cut-1"),
        pytest.param("join", 1, "...", (28, 28), (31, 34), id="no-spaces-at-join-2"),
    ],
)
def test_typed_marker_of_full_stops_without_a_space_each_side_is_a_manual_edit(
    marker_card: VerifiedExport,
    join_card: VerifiedExport,
    card_name: str,
    index: int,
    typed: str,
    evidence_range: tuple[int, int],
    body_range: tuple[int, int],
) -> None:
    export = marker_card if card_name == "marker" else join_card
    change = retyped_marker(index, typed)

    comparison = marker_comparison(export, change)

    assert comparison.manual_edits == (
        ManualEdit(CharacterRange(*evidence_range), CharacterRange(*body_range)),
    )
    words = MARKER_SOURCE_WORDS if card_name == "marker" else JOIN_SOURCE_WORDS
    verdict = docx_verdict(export, change, source_words=words)
    assert (verdict["status"], verdict["reason_codes"]) == ("UNVERIFIED", ["MANUAL_EDIT"])


def test_typed_marker_of_spaced_full_stops_where_nothing_was_cut_is_a_manual_edit(
    marker_card: VerifiedExport,
) -> None:
    """ "another ... spring": the dots and the space after them, body 47-51, before "spring" (44)."""
    change = replace_in_evidence("another spring", "another ... spring")

    comparison = marker_comparison(marker_card, change)

    assert comparison.manual_edits == (ManualEdit(CharacterRange(44, 44), CharacterRange(47, 51)),)
    verdict = marker_verdict(marker_card, change)
    assert (verdict["status"], verdict["reason_codes"]) == ("UNVERIFIED", ["MANUAL_EDIT"])


def test_typed_marker_is_read_for_the_ellipsis_profile_only(card: Card) -> None:
    """A profile whose marker is three full stops does not read the ellipsis character as its marker:
    the coach's decision reads typed full stops as "…", not the other way round."""
    body = FIRST_SENTENCE + MARKER + CRITICS_SENTENCE + LAST_PART

    assert compare_body(card, body, " ... ").manual_edits != ()
    assert compare_body(card, body, MARKER).manual_edits == ()


@pytest.mark.parametrize(
    ("index", "hidden"),
    [
        pytest.param(0, (12, 12), id="cut-1-fail-then-The"),
        pytest.param(1, (57, 60), id="cut-2-flood-then-Repairs"),
        pytest.param(2, (76, 82), id="cut-3-came-then-Nobody"),
    ],
)
def test_hidden_cut_a_marker_taken_out_at_a_punctuation_join(
    marker_card: VerifiedExport, index: int, hidden: tuple[int, int]
) -> None:
    """The body equals the card's characters there ("fail.The"), so nothing else differs."""
    comparison = marker_comparison(marker_card, retyped_marker(index, ""))

    assert comparison == BodyComparison(
        manual_edits=(), interpolations=(), deletions=(), hidden_cuts=(HiddenCut(*hidden),)
    )


def test_hidden_cut_every_marker_taken_out_is_one_hidden_cut_each(marker_card: VerifiedExport) -> None:
    """With no marker left, the body is the card's evidence_text and every body offset its own."""
    changes = tuple(retyped_marker(0, "") for _ in range(3))

    comparison = marker_comparison(marker_card, *changes)

    assert comparison.manual_edits == ()
    assert comparison.hidden_cuts == (HiddenCut(12, 12), HiddenCut(57, 57), HiddenCut(76, 76))


@pytest.mark.parametrize(
    ("index", "hidden"),
    [
        pytest.param(0, (9, 9), id="join-1-Engineerslevee"),
        pytest.param(1, (28, 31), id="join-2-holdnever"),
        pytest.param(2, (51, 57), id="join-3-northseason"),
    ],
)
def test_hidden_cut_a_marker_taken_out_at_a_word_join(
    join_card: VerifiedExport, index: int, hidden: tuple[int, int]
) -> None:
    """Until this node "holdnever" was ManualEdit(evidence [24, 33), body [27, 36)), t16's Decision 2: its
    characters are the card's, and what the body changed is the cut it no longer shows."""
    comparison = marker_comparison(join_card, retyped_marker(index, ""))

    assert comparison == BodyComparison(
        manual_edits=(), interpolations=(), deletions=(), hidden_cuts=(HiddenCut(*hidden),)
    )


@pytest.mark.parametrize(
    ("card_name", "index", "typed", "hidden", "interpolations"),
    [
        pytest.param("marker", 0, " ", (12, 12), (), id="a-space-at-cut-1"),
        pytest.param("join", 1, " ", (28, 31), (), id="a-space-at-join-2"),
        pytest.param(
            "marker",
            0,
            " [and] ",
            (12, 12),
            (BodyInterpolation(anchor=12, length=3, recorded=False),),
            id="an-interpolation-at-cut-1",
        ),
    ],
)
def test_hidden_cut_a_marker_replaced_by_something_else(
    marker_card: VerifiedExport,
    join_card: VerifiedExport,
    card_name: str,
    index: int,
    typed: str,
    hidden: tuple[int, int],
    interpolations: tuple[BodyInterpolation, ...],
) -> None:
    """A space where the marker was is not a MANUAL_EDIT for an added space: it is the cut, hidden."""
    export = marker_card if card_name == "marker" else join_card

    comparison = marker_comparison(export, retyped_marker(index, typed))

    assert comparison == BodyComparison(
        manual_edits=(), interpolations=interpolations, deletions=(), hidden_cuts=(HiddenCut(*hidden),)
    )


@pytest.mark.parametrize(
    ("old", "new", "deletion", "hidden"),
    [
        pytest.param("The levee", "levee", (12, 16), (12, 12), id="the-word-after-cut-1"),
        pytest.param(" fail", "", (6, 11), (12, 7), id="the-word-before-cut-1"),
    ],
)
def test_hidden_cut_a_word_deleted_beside_a_cut_with_its_marker(
    marker_card: VerifiedExport, old: str, new: str, deletion: tuple[int, int], hidden: tuple[int, int]
) -> None:
    """ "Levees fail.levee will" deletes "The " [12, 16): no marker is left to stand for its space.
    "Levees.The levee" deletes " fail" [6, 11), and the full stop that is left sits between the deletion
    and the cut, so the cut is hidden at "The", body 7."""
    changes = (retyped_marker(0, ""), replace_in_evidence(old, new))

    comparison = marker_comparison(marker_card, *changes)

    assert comparison == BodyComparison(
        manual_edits=(),
        interpolations=(),
        deletions=(CharacterRange(*deletion),),
        hidden_cuts=(HiddenCut(*hidden),),
    )


def test_hidden_cut_a_sentence_deleted_with_the_news_cards_marker(card: Card) -> None:
    """t07's "marker deleted too": the critics' sentence [108, 202) and the cut before it, at 108."""
    comparison = compare_body(card, FIRST_SENTENCE + LAST_PART, MARKER)

    assert comparison == BodyComparison(
        manual_edits=(),
        interpolations=(),
        deletions=(CharacterRange(108, 202),),
        hidden_cuts=(HiddenCut(108, 108),),
    )


def test_hidden_cut_none_where_one_marker_is_left_for_the_two_cuts_a_deletion_joins(
    marker_card: VerifiedExport,
) -> None:
    """ "Repairs never came." [57, 76) deleted with cut 3's marker: cut 2's marker still shows the cut."""
    changes = (retyped_marker(2, ""), replace_in_evidence("Repairs never came.", ""))

    comparison = marker_comparison(marker_card, *changes)

    assert comparison == BodyComparison(
        manual_edits=(), interpolations=(), deletions=(CharacterRange(57, 76),)
    )
    assert is_verified_without_reasons(marker_verdict(marker_card, *changes))

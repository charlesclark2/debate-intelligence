"""Classifying a file's paragraphs and grouping them into cards.

The two modules below this one have made the file safe to read and turned its paragraphs into
text and formatting. This one decides what the paragraphs *are* and which of them belong to the
same card, and it is where a `ParsedCard`'s provenance is attached.

## The classifier is not re-implemented here

Every unit — pocket, hat, block, tag, cite, evidence, analytic, undertag — is resolved by
:func:`~debate_core.evidence.style_classifier.classify_paragraph`, which tries the Verbatim style
first, its aliases second and a measured heuristic last. This module adds eight decisions the
classifier does not make, because each needs something the classifier cannot see:

* **A tag with no cite and no evidence under it is an analytic.** `Heading4` is what a debater
  types for a line of analysis as well as for a card's tag, and only the following paragraphs
  tell the two apart.
* **A card that is only its first and last words is abbreviated, not truncated.** An opencaselist
  disclosure may record a tag, a cite and an ellipsis between the opening and closing words —
  all the open-source rules require. Padding it or dropping it would both misrepresent the file,
  so it is kept and flagged. It is told by its *shape*: one ellipsis marker with a few words
  either side (:data:`MAXIMUM_DISCLOSED_FRAGMENT_WORDS`). An ellipsis on its own proves nothing:
  the first parse of the corpus called 22,443 cards abbreviated for holding one, and 21,278 of
  them have a body over 1,000 characters (`v1-e31-t09`).
* **Page furniture is `OTHER`, whatever style it carries.** A paragraph in a table cell or in a
  text box is a speech-time chart or a page banner, not a card. The classifier resolves a style
  before it looks at where a paragraph sits, so a `Heading4` in a table cell comes back from it
  as a tag; here it is `OTHER`, and the rule that said otherwise is kept in the rule id.
* **A blank line is `OTHER`, whatever style it carries.** A debater presses Enter in `Heading4`
  and leaves an empty heading behind: 5,043 of them in the first parse of the corpus, in nearly a
  quarter of its files. Read as a tag it opened a card with an empty tag and demoted the real tag
  above it; read as a pocket, hat or block it put an empty string in every path below it. It
  opens, closes and names nothing (`v1-e31-t09`). A blank line in a *body* style is left alone:
  it changes no structure, and evidence text is copied as the file lays it out.
* **A cite guessed inside a card's body is body when it is formatted as body.** A paragraph of a
  source's own prose that holds an ellipsis and a name with a year, or that opens *In 2019*,
  comes back from the classifier's two cite heuristics as a cite. The classifier cannot see that
  a card is already open with its body under way. Taking the guess at its word cut the card short
  there and stored the rest as a card with no tag: about 11,000 of the 15,528 empty tags in the
  first parse of the corpus. So when the paragraph is small print or highlighted, which is what a
  debater does to evidence, and does not open with a bold name, which is how a cite is written,
  it is the card's next body paragraph (`v1-e31-t09`). A cite *style* is never second-guessed.
* **A cite guessed before the body has opened is the body's first paragraph in two cases.** The
  rule above needs a body to be open, so the *first* body paragraph a guess misread was still
  added to the card's cite: 2,480 cards were left with a cite thousands of characters long and no
  evidence text at all. Formatted as body in the same sense, and carrying no cite character
  style, such a paragraph opens the body when the card already has a cite, unless it is short
  enough to be a cite entry and another cite follows it. When the card has no cite, only length
  says where one would end, so it opens the body past
  :data:`LONGEST_GUESSED_CITE_ENTRY_CHARACTERS` and not when it opens with a name and a year
  (`v1-e31-t09`). A guess that arrives with no card open stays the cite of a card with no tag:
  re-read as body it would belong to nothing and be dropped.
* **A guess longer than any cite entry is body wherever a card is open.** Both rules above ask
  that the paragraph be formatted as body, and a body's first words are often bold: 220 cards
  were still stored with their body in the cite and no evidence text. Past
  :data:`LONGEST_GUESSED_CITE_ENTRY_CHARACTERS` a wiki cite-entry guess is body whatever its
  formatting, unless a cite character style marks a name and a year at its head or it names a
  source within its first :data:`A_CITE_ENTRY_NAMES_ITS_SOURCE_WITHIN_CHARACTERS`, which is where
  a cite run together with its card has its cite (`v1-e31-t12`). A cite style anywhere else in
  the paragraph is emphasis and holds nothing (`v1-e31-t19`).
* **A cite written wholly inside a bracket is a cite where a cite stands.** `[Okonkwo 26, ...] KR`
  opens with its bracket, so nothing that reads the front of a line sees a name and a year, and
  it was read as body text or as nothing: a card that is only such a cite was stored `FULL`. A
  reference in brackets inside a source's own text has the same shape, so the classifier cannot
  call it; under a tag or under the card's cite, before any body, it is the card's cite
  (`v1-e31-t12`).

## Where a section path comes from

Pockets, hats, blocks and tags nest in that order, and each one closes the levels below it. A
paragraph's `section_path` is the text of the headings still open above it, outermost first, and
a heading is never in its own path. A card's path is its tag's path, so a card is placed by the
pocket, hat and block it sits under and named by its own tag.

## Provenance, and what it promises

Every card records the SHA-256 of the file, the path it sat at inside its archive, the caselist
or camp it came from, the snapshot it was read under, the range of paragraphs it was built from,
and the versions of this parser and of the style profile. Re-run the same versions over the same
bytes and the same cards come out, which is what makes a card's provenance checkable years later
rather than merely recorded. Nothing here is verified evidence: an imported card is `UNVERIFIED`
and the model refuses to say otherwise.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Final

from debate_core.domain.caselist import SnapshotDate, SourceDocument, SourceFormat
from debate_core.domain.debate_files import (
    CardCompleteness,
    FileImportProvenance,
    FileSection,
    ParsedCard,
    ParsedDocument,
    ParseFailure,
    ParseFailureReason,
)
from debate_core.domain.style_profile import (
    ParagraphStyleMatch,
    RunEmphasis,
    StructuralUnit,
    StyleMatchSource,
    StyleProfile,
)
from debate_core.evidence.style_classifier import (
    MAXIMUM_HEADING_CHARACTERS,
    NAME_AND_YEAR_AT_THE_HEAD_CHARACTERS,
    RunDescription,
    classify_paragraph,
    first_name_and_year,
    for_matching,
    is_a_cite_behind_a_first_name_or_title,
    is_a_cite_wholly_in_brackets,
    is_a_highlighted_cite,
    the_cite_style_marks_a_name_and_year_at_the_head,
)
from debate_core.evidence.style_profile_loader import load_style_profile
from debate_core.integrations.docx_parser.package import (
    DEFAULT_PACKAGE_LIMITS,
    DocxPackage,
    DocxPackageError,
    PackageLimits,
    XmlElement,
    open_debate_docx,
    qualified_name,
)
from debate_core.integrations.docx_parser.runs import (
    ReadParagraph,
    SpannedText,
    as_word_shows_it,
    concatenate_spanned_text,
    font_size_spans_for,
    formatting_spans_for,
    iter_text_box_paragraphs,
    read_paragraph,
)

__all__ = ["DOCX_PARSER_VERSION", "BodyParagraph", "DebateDocxParser", "body_paragraphs"]

#: Version recorded on every card this parser produces. Bumped whenever the output changes, so a
#: stored card always names the reading that produced it. Bumped too when the only change is that
#: a file once refused is now read: the parsed store skips a source it has already recorded under
#: the running version, refusals included, so without a new version the file would never be tried
#: again.
#:
#: `2026.09.20-docx-1` read the first full corpus. `2026.10.10-docx-2` (`v1-e31-t09`) reads the 23
#: files it refused for the words `system "` and `public '`, keeps a body paragraph guessed to be
#: a cite in its card, no longer takes a blank line in a heading style for a heading, calls a card
#: abbreviated for the shape of a first-and-last-words disclosure rather than for an ellipsis, and
#: no longer files the first paragraph of a body as the card's cite. `2026.10.12-docx-3`
#: (`v1-e31-t12`) reads cites the two before it missed or misread: a cite in the cite character
#: style past the profile's 1,000 characters, a cite line longer than 400 characters that opens
#: in bold or holds everything after its name and year in one bracket, and a cite written wholly
#: inside a bracket; it no longer takes a line that opens *In 2019* for a cite, and a guessed cite
#: entry longer than any cite entry is body whatever its formatting. `2026.10.18-docx-4`
#: (`v1-e31-t15`) reads three kinds of file the three before it refused: one whose compression
#: ratio was over the limit only in a part the reader never opens, and one whose text held a raw
#: character XML 1.0 forbids, each now replaced by U+FFFD; and it names a CardMirror `.cmir` filed
#: under another extension as an unsupported format rather than a broken zip. `2026.10.18-docx-5`
#: (`v1-e31-t19`) reads a cite behind a first name or a title, and a highlighted cite with a body
#: below it, where a cite stands; reads the cite and body rules through a paragraph style that maps
#: to no unit; holds a long guess by its cite style only when the style marks a name and year at its
#: head; and reads `Okonkwo ‘26`, with a left quote before the year, as a short cite.
#: `2026.10.20-docx-6` (`v1-e31-t24`) reads a bold line directly above a cite that opens a card with no
#: tag as that card's tag, its bold and size read as Word shows them, and steps over an Undertag line
#: when it looks for the body below a highlighted cite.
DOCX_PARSER_VERSION: Final = "2026.10.20-docx-6"

W_PARAGRAPH: Final = qualified_name("p")
W_TABLE: Final = qualified_name("tbl")
W_TABLE_ROW: Final = qualified_name("tr")
W_TABLE_CELL: Final = qualified_name("tc")
W_STRUCTURED_DOCUMENT_TAG: Final = qualified_name("sdt")
W_STRUCTURED_DOCUMENT_CONTENT: Final = qualified_name("sdtContent")

#: The units that open a section level, outermost first. A heading closes every level below it.
HEADING_UNITS: Final = (
    StructuralUnit.POCKET,
    StructuralUnit.HAT,
    StructuralUnit.BLOCK,
    StructuralUnit.TAG,
)

#: The units a paragraph with no visible text may still be. Everything else structures the file,
#: and a blank line structures nothing.
_UNITS_A_BLANK_PARAGRAPH_KEEPS: Final = (StructuralUnit.OTHER, StructuralUnit.EVIDENCE)

#: The most words a disclosure of a card's first and last words gives on either side of its
#: ellipsis marker.
#:
#: Set from what such a disclosure is, because the corpus has no population of them to measure. The
#: disclosure rules ask for a card's first and last few words; the profile's own examples give
#: eight and nine. Of the 22,053 card bodies this parser reads from the corpus that hold a marker,
#: 12,988 hold exactly one, and in none of those are both sides 15 words or fewer: the shortest longer
#: side is 17 words, in a whole card with an omission. Twelve sits
#: in the middle of that gap, above every disclosure we have a model of and below every whole card
#: the corpus holds. A whole card is never called abbreviated; a disclosure that quoted thirteen
#: words would be called whole, which is the safe way to be wrong.
MAXIMUM_DISCLOSED_FRAGMENT_WORDS: Final = 12

#: The longest paragraph a guess may make the first cite of a card, in characters.
#:
#: Measured over the 772 paragraphs in the corpus that the wiki heuristic makes the first cite
#: under a tag. A paragraph is marked as a cite by its author when it carries the cite character
#: style or opens with a name and a year. Up to 1,000 characters 194 of 258 are; from 1,001 to
#: 1,517 characters 74 of 81 are; and from 1,518 to 2,678 not one of 35 is. The longest cite
#: paragraph *style* at the head of a card is 1,427 characters. So a real cite entry ends by
#: 1,517, and 2,000 sits in the gap above it: any bound from 1,518 to 2,678 moves no paragraph
#: the corpus marks as a cite, and this one leaves 11 unmarked paragraphs alone that 1,518 would
#: have moved. The classifier's own bound for a cite *style* is the profile's 1,000.
LONGEST_GUESSED_CITE_ENTRY_CHARACTERS: Final = 2_000

#: How far into a paragraph a cite entry run together with its card may name its source.
#:
#: A guess past :data:`LONGEST_GUESSED_CITE_ENTRY_CHARACTERS` is body by its length alone only
#: when no name and year sits in its first 300 characters. Of the 403 such guesses in the corpus
#: that are still cites and neither carry a cite style nor open with a name and a year, 336 have
#: their first name and year further in than that: prose that mentions a source somewhere. 18
#: have it within 80 characters and 49 between 81 and 300, and those 67 are left as they are:
#: a card written as one paragraph behind a full name looks the same, and splitting one into its
#: cite and its words is a model question.
A_CITE_ENTRY_NAMES_ITS_SOURCE_WITHIN_CHARACTERS: Final = 300

#: A body paragraph re-read from a cite guess is no surer than the classifier's own shrunk-text rule.
_REREAD_BODY_CONFIDENCE: Final = 0.6

#: A cite read from its bracket and its place is a guess of the same weight as a cite line.
_BRACKETED_CITE_CONFIDENCE: Final = 0.6

#: A tag read from its bold and its place above a cite is a guess of the same weight as the
#: classifier's own bold line at reading size (`heuristic-direct-formatted-heading-tag`).
_BOLD_TAG_CONFIDENCE: Final = 0.5

#: The units after which a cite may stand: a tag, a line under it, or a line of the cite itself.
_UNITS_A_CITE_STANDS_AFTER: Final = (StructuralUnit.TAG, StructuralUnit.UNDERTAG, StructuralUnit.CITE)

#: How much a match source is worth when a card reports the weakest one it was built from.
_MATCH_SOURCE_STRENGTH: Final = {
    StyleMatchSource.VERBATIM: 2,
    StyleMatchSource.VERBATIM_ALIAS: 1,
    StyleMatchSource.HEURISTIC: 0,
}


# --------------------------------------------------------------------------------------------
# Walking the body
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _BodyParagraph:
    """One paragraph of the body, and the two facts about where it sits."""

    element: XmlElement
    in_table: bool = False
    in_text_box: bool = False


def _iter_table_paragraphs(table: XmlElement) -> Iterator[_BodyParagraph]:
    """Yield a table's paragraphs cell by cell, descending into nested tables.

    Walked structurally rather than with `iter()` so that a text box inside a cell is not
    swept up here and then found again by the text-box walk.
    """
    for row in table.iterfind(W_TABLE_ROW):
        for cell in row.iterfind(W_TABLE_CELL):
            for child in cell:
                if child.tag == W_PARAGRAPH:
                    yield _BodyParagraph(child, in_table=True)
                    yield from _iter_text_box_paragraphs_of(child, in_table=True)
                elif child.tag == W_TABLE:
                    yield from _iter_table_paragraphs(child)


def _iter_text_box_paragraphs_of(element: XmlElement, *, in_table: bool = False) -> Iterator[_BodyParagraph]:
    """Yield the paragraphs of any text box inside one paragraph."""
    for paragraph in iter_text_box_paragraphs(element):
        yield _BodyParagraph(paragraph, in_table=in_table, in_text_box=True)


#: One paragraph of the body and where it sits, as the walk that numbers element indices sees it.
BodyParagraph = _BodyParagraph


def body_paragraphs(body: XmlElement) -> tuple[BodyParagraph, ...]:
    """Every paragraph of the body, indexed exactly as a card's provenance element indices are.

    The lossless writer (`v1-e33-t02`) finds a card's paragraphs by those indices, so it walks the
    body with the parser's own walk rather than a second one that could disagree with it.
    """
    return tuple(_iter_body_paragraphs(body))


def _iter_body_paragraphs(element: XmlElement) -> Iterator[_BodyParagraph]:
    """Yield every paragraph of the body in document order, tables and text boxes included.

    The order is the order the bytes are in, which is the order a reader sees the file in Word.
    A paragraph's position in this walk is its element index, and it is what a card's provenance
    records: it is reproducible from the same bytes under the same parser version.
    """
    for child in element:
        tag = child.tag
        if tag == W_PARAGRAPH:
            yield _BodyParagraph(child)
            yield from _iter_text_box_paragraphs_of(child)
        elif tag == W_TABLE:
            yield from _iter_table_paragraphs(child)
        elif tag == W_STRUCTURED_DOCUMENT_TAG:
            for content in child.iterfind(W_STRUCTURED_DOCUMENT_CONTENT):
                yield from _iter_body_paragraphs(content)


# --------------------------------------------------------------------------------------------
# Assembling cards
# --------------------------------------------------------------------------------------------


@dataclass(slots=True)
class _CardUnderConstruction:
    """A card being built as the walk moves down the file."""

    tag: str = ""
    undertag_lines: list[str] = field(default_factory=list[str])
    cite_lines: list[str] = field(default_factory=list[str])
    evidence_parts: list[SpannedText] = field(default_factory=list[SpannedText])
    section_path: tuple[str, ...] = ()
    first_element_index: int = 0
    last_element_index: int = 0
    matches: list[ParagraphStyleMatch] = field(default_factory=list[ParagraphStyleMatch])

    @property
    def has_body(self) -> bool:
        return any(part.text.strip() for part in self.evidence_parts)

    @property
    def has_cite(self) -> bool:
        return any(line.strip() for line in self.cite_lines)


@dataclass(frozen=True, slots=True)
class _ReadSection:
    """One paragraph, read and classified, before the assembly has had its say."""

    read: ReadParagraph
    match: ParagraphStyleMatch
    in_text_box: bool
    occupies_tag_level: bool = False
    """True for a paragraph written as a tag that the assembly demoted to an analytic.

    It is no longer a tag, but it still sits where one sat: the next paragraph is its sibling,
    not its child, and no tag is open beneath it.
    """


@dataclass(frozen=True, slots=True)
class _Provenance:
    """What every card of one file records about where it came from."""

    source: SourceDocument
    source_path: str
    snapshot: date
    camp: str | None


@dataclass(frozen=True, slots=True)
class _Assembled:
    """One walk over a file's classified paragraphs: its sections and cards."""

    sections: list[FileSection]
    decided: list[_ReadSection]
    """Each paragraph as the walk finally read it, aligned with `sections`."""
    cards: list[ParsedCard]
    deletions_dropped: int


class DebateDocxParser:
    """The V1 :class:`~debate_core.application.ports.debate_files.DebateFileParser`.

    Deterministic and offline: no clock, no random source, no model call, no network. The same
    bytes, profile and parser version always produce the same document.
    """

    def __init__(
        self,
        profile: StyleProfile | None = None,
        *,
        limits: PackageLimits = DEFAULT_PACKAGE_LIMITS,
    ) -> None:
        self._profile = profile if profile is not None else load_style_profile()
        self._limits = limits
        # One pattern for every spelling. `[...]` is one marker, not a bracket, a marker and a
        # bracket: a match is taken where it starts first, and the bracketed spelling starts earlier.
        self._ellipsis_marker = re.compile(
            "|".join(re.escape(marker) for marker in self._profile.cite.wiki_ellipsis_markers)
        )

    @property
    def parser_version(self) -> str:
        return DOCX_PARSER_VERSION

    @property
    def profile_version(self) -> str:
        return self._profile.profile_version

    @property
    def profile(self) -> StyleProfile:
        """The style profile every unit and emphasis in the output was resolved through."""
        return self._profile

    # -- the port -----------------------------------------------------------------------------

    def parse(
        self,
        content: bytes,
        source: SourceDocument,
        *,
        source_path: str,
        snapshot: SnapshotDate | None = None,
        camp: str | None = None,
    ) -> ParsedDocument | ParseFailure:
        """Read one imported file into sections and cards, or say why it could not be read."""
        if not source.is_parsable:
            return self._failure(
                source,
                source_path,
                ParseFailureReason.UNSUPPORTED_FORMAT,
                f"{source.source_format} is stored unparsed in V1",
            )
        try:
            package = open_debate_docx(content, limits=self._limits)
        except DocxPackageError as error:
            return self._failure(
                source, source_path, error.reason, error.detail, source_format=error.source_format
            )
        return self._build_document(
            package,
            source=source,
            source_path=source_path,
            snapshot=snapshot if snapshot is not None else source.last_seen_snapshot,
            camp=camp,
        )

    def _failure(
        self,
        source: SourceDocument,
        source_path: str,
        reason: ParseFailureReason,
        detail: str,
        *,
        source_format: SourceFormat | None = None,
    ) -> ParseFailure:
        return ParseFailure(
            source_sha256=source.sha256,
            source_path=source_path,
            reason=reason,
            detail=detail,
            parser_version=DOCX_PARSER_VERSION,
            source_format=source_format,
        )

    # -- reading and classifying --------------------------------------------------------------

    def _read_sections(self, package: DocxPackage) -> list[_ReadSection]:
        """Read and classify every paragraph, in document order."""
        sections: list[_ReadSection] = []
        for index, body_paragraph in enumerate(_iter_body_paragraphs(package.body)):
            read = read_paragraph(
                body_paragraph.element,
                package,
                element_index=index,
                in_table=body_paragraph.in_table,
            )
            if body_paragraph.in_text_box:
                match = ParagraphStyleMatch(
                    unit=StructuralUnit.OTHER,
                    rule_id="assembly-text-box",
                    match_source=StyleMatchSource.HEURISTIC,
                    confidence=1.0,
                )
            elif body_paragraph.in_table:
                match = ParagraphStyleMatch(
                    unit=StructuralUnit.OTHER,
                    rule_id="assembly-table-cell",
                    match_source=StyleMatchSource.HEURISTIC,
                    confidence=1.0,
                )
            else:
                match = classify_paragraph(read.description, self._profile)
                if match.unit not in _UNITS_A_BLANK_PARAGRAPH_KEEPS and not read.text.strip():
                    match = ParagraphStyleMatch(
                        unit=StructuralUnit.OTHER,
                        rule_id=f"assembly-empty-paragraph:{match.rule_id}",
                        match_source=StyleMatchSource.HEURISTIC,
                        confidence=1.0,
                    )
            sections.append(_ReadSection(read=read, match=match, in_text_box=body_paragraph.in_text_box))
        return sections

    def _read_cites_where_a_cite_stands(self, sections: list[_ReadSection]) -> list[_ReadSection]:
        """Re-read as a cite a paragraph whose shape is a cite's only where a cite stands.

        Three shapes are cites there and something else elsewhere, so the classifier cannot call
        them:

        * **wholly inside a bracket.** `[Okonkwo 26, ...] KR` is a cite and `(Lindqvist 2019)` on
          a line of an article is the article's own reference
          (:func:`~debate_core.evidence.style_classifier.is_a_cite_wholly_in_brackets`,
          `v1-e31-t12`);
        * **behind a first name or a title.** `Adaeze Okonkwo 26, ...` with the name and year in
          bold is a cite, and a sentence in a body can open with a bold name
          (:func:`~debate_core.evidence.style_classifier.is_a_cite_behind_a_first_name_or_title`,
          `v1-e31-t19`);
        * **a highlighted cite, with a body below it.** A cite whose name a debater highlighted to
          read, and a card written as one paragraph behind its cite, have one shape
          (:func:`~debate_core.evidence.style_classifier.is_a_highlighted_cite`). Only the first
          has a body after it (`v1-e31-t19`).

        A cite stands after a tag, an undertag or another line of the cite, before any body.
        Blank lines, page furniture and lines read as nothing are stepped over.
        A guessed cite that a body may yet take for itself (:meth:`_is_a_guess_a_body_may_take`)
        is not such a line: what follows it may be the middle of a body, where a reference in
        brackets would end the card.

        Only what the classifier guessed to be body or nothing is re-read; a paragraph style is
        the file's author saying what the paragraph is. It runs before tags with no card are
        demoted, because a tag whose only paragraph is such a cite is a card, cite-only, and read
        as nothing the cite left its tag an analytic.
        """
        reread: list[_ReadSection] = []
        a_cite_stands_here = False
        a_body_follows = _followed_by_a_body(sections)
        for position, section in enumerate(sections):
            match = section.match
            reason = (
                self._why_it_is_a_cite_where_a_cite_stands(
                    section.read, a_body_follows=a_body_follows[position]
                )
                if a_cite_stands_here
                and match.unit in (StructuralUnit.EVIDENCE, StructuralUnit.OTHER)
                and match.match_source is StyleMatchSource.HEURISTIC
                and not match.rule_id.startswith("assembly-")
                else None
            )
            if reason is not None:
                section = _ReadSection(
                    read=section.read,
                    match=ParagraphStyleMatch(
                        unit=StructuralUnit.CITE,
                        rule_id=f"{reason}:{match.rule_id}",
                        match_source=StyleMatchSource.HEURISTIC,
                        confidence=_BRACKETED_CITE_CONFIDENCE,
                    ),
                    in_text_box=section.in_text_box,
                )
            unit = section.match.unit
            if unit in _UNITS_A_CITE_STANDS_AFTER:
                a_cite_stands_here = not self._is_a_guess_a_body_may_take(section)
            elif unit is not StructuralUnit.OTHER:
                a_cite_stands_here = False
            reread.append(section)
        return reread

    def _why_it_is_a_cite_where_a_cite_stands(
        self, read: ReadParagraph, *, a_body_follows: bool
    ) -> str | None:
        """The assembly rule that reads a paragraph standing where a cite stands as a cite, or None."""
        description = read.description
        if is_a_cite_wholly_in_brackets(description, self._profile):
            return "assembly-bracketed-cite-before-the-body"
        if is_a_cite_behind_a_first_name_or_title(description, self._profile):
            return "assembly-cite-behind-a-name-before-the-body"
        if a_body_follows and is_a_highlighted_cite(description, self._profile):
            return "assembly-highlighted-cite-before-the-body"
        return None

    def _is_a_guess_a_body_may_take(self, section: _ReadSection) -> bool:
        """Whether a paragraph is a guessed cite that the assembly may yet re-read as body.

        A guess formatted as body, or longer than any cite entry: the two kinds an open body takes
        for itself (:meth:`_keep_a_guessed_cite_in_its_body`). A cite read from a style is never one.
        """
        match = section.match
        return (
            match.unit is StructuralUnit.CITE
            and match.match_source is StyleMatchSource.HEURISTIC
            and (self._is_formatted_as_body(section.read) or self._is_longer_than_a_cite_entry(section))
        )

    def _demote_tags_with_no_card(self, sections: list[_ReadSection]) -> list[_ReadSection]:
        """Turn a tag with no cite and no evidence under it into an analytic.

        `Heading4` is what a debater types for a line of analysis as well as for a card's tag, so
        the only thing that tells them apart is whether a cite or a body follows before the next
        heading. Goal criterion ac2.
        """
        demoted: list[_ReadSection] = []
        for position, section in enumerate(sections):
            if section.match.unit is not StructuralUnit.TAG or not section.read.text.strip():
                demoted.append(section)
                continue
            if _card_follows(sections, position):
                demoted.append(section)
                continue
            demoted.append(
                _ReadSection(
                    read=section.read,
                    match=ParagraphStyleMatch(
                        unit=StructuralUnit.ANALYTIC,
                        rule_id=f"assembly-tag-without-cite-or-evidence:{section.match.rule_id}",
                        match_source=StyleMatchSource.HEURISTIC,
                        confidence=min(section.match.confidence, 0.7),
                    ),
                    in_text_box=section.in_text_box,
                    occupies_tag_level=True,
                )
            )
        return demoted

    def _keep_a_guessed_cite_in_its_body(
        self, section: _ReadSection, building: _CardUnderConstruction | None
    ) -> _ReadSection:
        """Re-read a cite guessed inside an open body as body, when it is formatted as body.

        Three things have to hold, and each is something only the assembly can see or weigh:

        * a card is open and already has a body, so there is a body for the paragraph to belong to;
        * the classifier *guessed*: the match is one of its cite heuristics, not a Verbatim cite
          style, which is the file's author saying "cite" and is taken at its word;
        * the paragraph is formatted the way a body is and not the way a cite is
          (:meth:`_is_formatted_as_body`), or is longer than any cite entry
          (:meth:`_is_longer_than_a_cite_entry`).

        Otherwise the paragraph stays the cite the classifier called it, and starts a card with no
        tag, which is what two cards under one tag look like.
        """
        if building is None or not building.has_body:
            return section
        if not self._is_a_guess_a_body_may_take(section):
            return section
        return _reread_as_body(section, "assembly-cite-guess-inside-card-body")

    def _open_the_body_with_a_guessed_cite(
        self,
        section: _ReadSection,
        building: _CardUnderConstruction | None,
        *,
        a_cite_follows: bool,
    ) -> _ReadSection:
        """Re-read a cite guessed before the card's body has opened as the body's first paragraph.

        :meth:`_keep_a_guessed_cite_in_its_body` needs a body to be open. This is the paragraph
        before that: a card is open and has no body yet. The guess has to be a guess, and the
        paragraph formatted as body, exactly as there. Two things more are asked, because here the
        paragraph sits where a cite belongs:

        * **no cite character style marks a name and a year at its head.** The classifier lets go
          of its style rule past 1,000 characters and its guess takes over, but where the style
          marks the paragraph's source the author's mark is still on it, and it never moves. On a
          phrase further in, the style is emphasis (`v1-e31-t19`);
        * **the card already has a cite**, so the paragraph is not the only cite the card has.
          Failing that, it must be longer than any cite entry
          (:data:`LONGEST_GUESSED_CITE_ENTRY_CHARACTERS`) and must not open with a name and a year,
          which is where a cite run together with its card would have its cite;
        * **it is not a line in the middle of a cite.** A paragraph short enough to be a cite
          entry, with the card's cite above it and another cite right below, is left where it is.
          Re-read as body it would end the card at the cite below, and the real body under that
          would go to a card with no tag.

        A guess longer than any cite entry (:meth:`_is_longer_than_a_cite_entry`) opens the body
        whatever its formatting: a body's first words are often bold, and length alone says such
        a paragraph is no cite entry.

        With no card open the paragraph is left the cite of a card with no tag. Re-read as body it
        would belong to no card, and :meth:`_close` drops a body with neither tag nor cite.
        """
        match = section.match
        if building is None:
            return section
        if match.unit is not StructuralUnit.CITE or match.match_source is not StyleMatchSource.HEURISTIC:
            return section
        by_its_length_alone = self._is_longer_than_a_cite_entry(section)
        if not by_its_length_alone and (
            not self._is_formatted_as_body(section.read)
            or self._the_cite_style_marks_its_source(section.read)
        ):
            return section
        # A guess that is still a cite here was not taken by an open body, so the card has none yet.
        text = section.read.text
        longer_than_a_cite_entry = len(text) > LONGEST_GUESSED_CITE_ENTRY_CHARACTERS
        if building.has_cite:
            if a_cite_follows and not longer_than_a_cite_entry:
                return section
            return _reread_as_body(section, "assembly-cite-guess-after-card-cite")
        if by_its_length_alone or (longer_than_a_cite_entry and self._short_cite(text) is None):
            return _reread_as_body(section, "assembly-cite-guess-longer-than-a-cite")
        return section

    def _is_longer_than_a_cite_entry(self, section: _ReadSection) -> bool:
        """Whether a paragraph the classifier guessed to be a cite is body by its length alone.

        The wiki guess takes any paragraph that holds an ellipsis and a name with a year, at any
        length, and it is the only guess with no bound of its own. Past
        :data:`LONGEST_GUESSED_CITE_ENTRY_CHARACTERS` a paragraph is no cite entry, unless the
        file's author marked a name and a year at its head with a cite character style, or it
        names a source within its first
        :data:`A_CITE_ENTRY_NAMES_ITS_SOURCE_WITHIN_CHARACTERS`: a card written as one paragraph
        behind its cite, which is left as the classifier called it.
        """
        text = section.read.text
        if len(text) <= LONGEST_GUESSED_CITE_ENTRY_CHARACTERS or self._the_cite_style_marks_its_source(
            section.read
        ):
            return False
        source = first_name_and_year(text.strip(), self._profile)
        return source is None or source.start() > A_CITE_ENTRY_NAMES_ITS_SOURCE_WITHIN_CHARACTERS

    def _followed_by_a_cite(self, sections: Sequence[_ReadSection]) -> list[bool]:
        """For each paragraph, whether the next one that says anything is a cite that stays a cite.

        Blank lines and page furniture are stepped over. A cite stays a cite unless it is a guess
        formatted as body or longer than any cite entry, which an open body takes for itself
        (:meth:`_keep_a_guessed_cite_in_its_body`).
        """
        followed = [False] * len(sections)
        a_cite_is_next = False
        for position in range(len(sections) - 1, -1, -1):
            followed[position] = a_cite_is_next
            section = sections[position]
            match = section.match
            if match.unit is StructuralUnit.OTHER:
                continue
            a_cite_is_next = match.unit is StructuralUnit.CITE and not self._is_a_guess_a_body_may_take(
                section
            )
        return followed

    def _the_cite_style_marks_its_source(self, read: ReadParagraph) -> bool:
        """Whether a cite character style marks a name and a year at the paragraph's head.

        That is what the style is for in a cite. Until `v1-e31-t19` a cite-style run anywhere held
        a guess as a cite at any length, and 26 paragraphs of over 2,000 characters, formatted as
        body, stood as cite text with the style on a phrase in their middle: emphasis, by the
        measure `v1-e31-t12` took for the style past the profile's bound (the PM's ruling in its
        review). 23 cards were `CITE_ONLY` with their body in the cite.
        """
        return the_cite_style_marks_a_name_and_year_at_the_head(read.description, self._profile)

    def _is_formatted_as_body(self, read: ReadParagraph) -> bool:
        """Whether a paragraph carries a body's formatting and not a cite's.

        Small print throughout, or highlighting, is what a debater does to evidence: the profile's
        shrink rule measured the first, and nobody highlights a citation. A bold name at the front
        is how a cite is written, so a paragraph that has both is left as the classifier called it.
        Underline on its own decides nothing: a cite's link is underlined as often as a card's text.
        """
        description = read.description
        visible = description.visible_runs
        if not visible:
            return False
        opens_bold = visible[0].bold if visible[0].bold is not None else bool(description.paragraph_bold)
        if opens_bold:
            return False
        return description.has_highlighted_run or self._profile.is_shrunk(
            description.effective_half_points, underlined=False
        )

    # -- building the output ------------------------------------------------------------------

    def _build_document(
        self,
        package: DocxPackage,
        *,
        source: SourceDocument,
        source_path: str,
        snapshot: date,
        camp: str | None,
    ) -> ParsedDocument:
        classified = self._read_cites_where_a_cite_stands(self._read_sections(package))
        provenance = _Provenance(source=source, source_path=source_path, snapshot=snapshot, camp=camp)
        assembled = self._assemble(self._demote_tags_with_no_card(classified), provenance)
        tags = self._bold_tags_above_cites(assembled, package)
        if tags:
            classified = [
                _read_as_a_bold_tag(section) if position in tags else section
                for position, section in enumerate(classified)
            ]
            assembled = self._assemble(self._demote_tags_with_no_card(classified), provenance)

        warnings = list(package.warnings)
        if package.forbidden_characters_replaced:
            warnings.append(
                f"{package.forbidden_characters_replaced} character(s) XML 1.0 forbids were each "
                "replaced by U+FFFD; no other character moved"
            )
        if assembled.deletions_dropped:
            warnings.append(
                f"{assembled.deletions_dropped} tracked deletion(s) were dropped; the card is what the file "
                "would read as, not what it used to read as"
            )
        return ParsedDocument(
            source_sha256=source.sha256,
            source_path=source_path,
            parser_version=DOCX_PARSER_VERSION,
            profile_version=self._profile.profile_version,
            sections=tuple(assembled.sections),
            cards=tuple(assembled.cards),
            warnings=tuple(warnings),
        )

    def _assemble(self, read_sections: list[_ReadSection], provenance: _Provenance) -> _Assembled:
        """Walk the classified paragraphs once, building sections and cards."""
        source, source_path, snapshot, camp = (
            provenance.source,
            provenance.source_path,
            provenance.snapshot,
            provenance.camp,
        )
        open_headings: list[str | None] = [None, None, None, None]
        sections: list[FileSection] = []
        decided: list[_ReadSection] = []
        cards: list[ParsedCard] = []
        building: _CardUnderConstruction | None = None
        deletions_dropped = 0

        followed_by_a_cite = self._followed_by_a_cite(read_sections)
        for read_section, a_cite_follows in zip(read_sections, followed_by_a_cite, strict=True):
            section = self._keep_a_guessed_cite_in_its_body(read_section, building)
            section = self._open_the_body_with_a_guessed_cite(
                section, building, a_cite_follows=a_cite_follows
            )
            unit = section.match.unit
            deletions_dropped += section.read.deletions_dropped

            if unit in HEADING_UNITS:
                # A heading's path is the headings *above* it, so the one it replaces at its own
                # level is already out of it: a second tag under a block is a sibling of the first,
                # not a child of it.
                level = HEADING_UNITS.index(unit)
                path = tuple(text for text in open_headings[:level] if text is not None)
                open_headings[level] = section.read.text
                for lower in range(level + 1, len(open_headings)):
                    open_headings[lower] = None
            elif section.occupies_tag_level:
                level = HEADING_UNITS.index(StructuralUnit.TAG)
                path = tuple(text for text in open_headings[:level] if text is not None)
                for lower in range(level, len(open_headings)):
                    open_headings[lower] = None
            else:
                path = tuple(text for text in open_headings if text is not None)

            sections.append(
                FileSection(
                    unit=unit,
                    text=section.read.text,
                    section_path=path,
                    match=section.match,
                    element_index=section.read.element_index,
                    formatting_spans=formatting_spans_for(section.read, self._profile, slot=unit),
                    font_size_spans=font_size_spans_for(section.read),
                    in_table=section.read.in_table,
                )
            )
            decided.append(section)

            building = self._advance(building, section, path, cards, source, source_path, snapshot, camp)

        if building is not None:
            self._close(building, cards, source, source_path, snapshot, camp)
        return _Assembled(
            sections=sections, decided=decided, cards=cards, deletions_dropped=deletions_dropped
        )

    def _bold_tags_above_cites(self, assembled: _Assembled, package: DocxPackage) -> frozenset[int]:
        """The positions of the lines that are the tags of the cards their cites open (`v1-e31-t24`).

        A cite that opens a card with no tag, and the paragraph directly above it, blank lines and
        page furniture stepped over and never a second paragraph that says something. The line is
        the card's tag when :meth:`_is_a_bold_tag` says so, and the cite is no guess a body may yet
        take for itself: re-read with a tag above it, such a guess could become the body. A card
        that already has a tag is never touched.
        """
        tagless = {
            card.provenance.first_element_index for card in assembled.cards if not (card.tag or "").strip()
        }
        tags: set[int] = set()
        for position, section in enumerate(assembled.sections):
            if section.unit is not StructuralUnit.CITE or section.element_index not in tagless:
                continue
            if self._is_a_guess_a_body_may_take(assembled.decided[position]):
                continue
            above = position - 1
            while above >= 0 and _says_nothing(assembled.sections[above]):
                above -= 1
            if above >= 0 and self._is_a_bold_tag(assembled.decided[above], package):
                tags.add(above)
        return frozenset(tags)

    def _is_a_bold_tag(self, section: _ReadSection, package: DocxPackage) -> bool:
        """Whether a line read as body or nothing is a tag in bold that the reader could not see.

        `v1-e31-t19`'s item (7): a tag typed with nothing set, in a file whose document defaults make
        every run bold at 13 pt, gave the reader an unbolded line of no size, and a bold tag with no
        size of its own gave it no size; the classifier's bold-heading rule needs both. Here, and
        only here, the line's bold and size are read as Word shows them
        (:func:`~debate_core.integrations.docx_parser.runs.as_word_shows_it`): bold throughout, at
        reading size or larger. The classifier and every other rule read what a run says.

        It must also be no longer than a heading and name no source at its head; read by a
        heuristic, as body or nothing, not through a paragraph style; and hold no highlighted run
        and no run in the underline or emphasis style, which is read evidence, not a heading (the
        PM's ruling of 2026-10-20).
        """
        match = section.match
        if (
            match.unit not in (StructuralUnit.EVIDENCE, StructuralUnit.OTHER)
            or match.match_source is not StyleMatchSource.HEURISTIC
            or match.rule_id.startswith("assembly-")
        ):
            return False
        description = section.read.description
        if self._profile.resolve_paragraph_style(
            description.style_id, description.style_name, description.style_based_on
        ):
            return False
        text = section.read.text.strip()
        if not text or len(text) > MAXIMUM_HEADING_CHARACTERS or description.has_highlighted_run:
            return False
        if any(self._marks_read_evidence(run) for run in description.visible_runs):
            return False
        source = first_name_and_year(text, self._profile)
        if source is not None and source.start() <= NAME_AND_YEAR_AT_THE_HEAD_CHARACTERS:
            return False
        shown = as_word_shows_it(description, package)
        size = shown.effective_half_points
        return shown.effective_bold and size is not None and size >= self._profile.shrink.body_half_points

    def _marks_read_evidence(self, run: RunDescription) -> bool:
        """Whether a run carries the underline or emphasis character style: evidence a debater cut."""
        match = self._profile.resolve_character_style(
            run.character_style_id, run.character_style_name, run.character_style_based_on
        )
        return match is not None and match.emphasis in (RunEmphasis.UNDERLINE, RunEmphasis.EMPHASIS)

    def _advance(
        self,
        building: _CardUnderConstruction | None,
        section: _ReadSection,
        path: tuple[str, ...],
        cards: list[ParsedCard],
        source: SourceDocument,
        source_path: str,
        snapshot: date,
        camp: str | None,
    ) -> _CardUnderConstruction | None:
        """Fold one classified paragraph into the card being built, or start or finish one."""
        unit = section.match.unit
        text = section.read.text

        if unit in (StructuralUnit.POCKET, StructuralUnit.HAT, StructuralUnit.BLOCK):
            if building is not None:
                self._close(building, cards, source, source_path, snapshot, camp)
            return None

        if unit is StructuralUnit.TAG:
            if building is not None:
                self._close(building, cards, source, source_path, snapshot, camp)
            return _CardUnderConstruction(
                tag=text,
                section_path=path,
                first_element_index=section.read.element_index,
                last_element_index=section.read.element_index,
                matches=[section.match],
            )

        if unit is StructuralUnit.ANALYTIC:
            if building is not None:
                self._close(building, cards, source, source_path, snapshot, camp)
            return None

        if unit is StructuralUnit.CITE:
            if building is not None and building.has_body:
                self._close(building, cards, source, source_path, snapshot, camp)
                building = None
            if building is None:
                # A cite with no tag above it: ordinary in a wiki-converted disclosure.
                building = _CardUnderConstruction(
                    section_path=path,
                    first_element_index=section.read.element_index,
                    last_element_index=section.read.element_index,
                )
            building.cite_lines.append(text)
            building.last_element_index = section.read.element_index
            building.matches.append(section.match)
            return building

        if unit is StructuralUnit.UNDERTAG:
            if building is not None:
                building.undertag_lines.append(text)
                building.last_element_index = section.read.element_index
                building.matches.append(section.match)
            return building

        if unit is StructuralUnit.EVIDENCE and building is not None:
            building.evidence_parts.append(
                SpannedText(
                    text=text,
                    formatting_spans=formatting_spans_for(
                        section.read, self._profile, slot=StructuralUnit.EVIDENCE
                    ),
                    font_size_spans=font_size_spans_for(section.read),
                )
            )
            building.last_element_index = section.read.element_index
            building.matches.append(section.match)
            return building

        return building

    def _close(
        self,
        building: _CardUnderConstruction,
        cards: list[ParsedCard],
        source: SourceDocument,
        source_path: str,
        snapshot: date,
        camp: str | None,
    ) -> None:
        """Finish a card and append it, unless there is nothing there to keep.

        A tag on its own is not a card — it has already been demoted to an analytic by then — and
        neither is an evidence paragraph with no cite and no tag, which is a stray body somebody
        pasted. Both are still `FileSection`s; they simply do not become cards.
        """
        if not building.has_cite and not building.has_body:
            return
        if not building.tag.strip() and not building.has_cite:
            return

        body = concatenate_spanned_text(building.evidence_parts)
        full_cite = "\n".join(building.cite_lines).strip()
        completeness = self._completeness(body.text)
        cards.append(
            ParsedCard(
                tag=building.tag,
                short_cite=self._short_cite(full_cite),
                full_cite=full_cite,
                undertag="\n".join(building.undertag_lines),
                evidence_text=body.text if completeness is not CardCompleteness.CITE_ONLY else "",
                completeness=completeness,
                section_path=building.section_path,
                formatting_spans=body.formatting_spans
                if completeness is not CardCompleteness.CITE_ONLY
                else (),
                font_size_spans=body.font_size_spans
                if completeness is not CardCompleteness.CITE_ONLY
                else (),
                match_source=_weakest_match_source(building.matches),
                confidence=min((match.confidence for match in building.matches), default=0.5),
                rule_ids=tuple(match.rule_id for match in building.matches),
                provenance=FileImportProvenance(
                    source_sha256=source.sha256,
                    source_path=source_path,
                    origin=source.origin,
                    caselist=source.caselist,
                    camp=camp,
                    snapshot=snapshot,
                    first_element_index=building.first_element_index,
                    last_element_index=building.last_element_index,
                    parser_version=DOCX_PARSER_VERSION,
                    profile_version=self._profile.profile_version,
                ),
            )
        )

    # -- the two judgements about a card ------------------------------------------------------

    def _completeness(self, evidence_text: str) -> CardCompleteness:
        """Decide whether a card is whole, abbreviated or a cite on its own.

        From the body alone. A cite carries an ellipsis for its own reasons, a shortened title or
        a list of authors, and says nothing about how much of the card the file holds.
        """
        if not evidence_text.strip():
            return CardCompleteness.CITE_ONLY
        if self._is_first_and_last_words(evidence_text):
            return CardCompleteness.ABBREVIATED
        return CardCompleteness.FULL

    def _is_first_and_last_words(self, evidence_text: str) -> bool:
        """Whether a body has the shape of a disclosure: a few words, one marker, a few words more.

        Exactly one marker, because one joins a beginning to an end and two leave things out of a
        quotation. Words on both sides of it, because a marker that opens or closes a body joins
        nothing. And no more than :data:`MAXIMUM_DISCLOSED_FRAGMENT_WORDS` on either side, counted
        over the whole body, so a line break between the two halves changes nothing.
        """
        fragments = self._ellipsis_marker.split(evidence_text)
        if len(fragments) != 2:
            return False
        return all(0 < len(fragment.split()) <= MAXIMUM_DISCLOSED_FRAGMENT_WORDS for fragment in fragments)

    def _short_cite(self, full_cite: str) -> str | None:
        """Split the part a debater says out loud off the front of a cite line.

        The pattern is the profile's, measured in `v1-e31-t02` and refined against the labelled
        set in `v1-e31-t05`. A cite this does not recognise gets no short cite rather than a
        guessed one: an invented short cite would be repeated back to a debater as fact.
        """
        if not full_cite.strip():
            return None
        match = re.match(self._profile.cite.short_cite_pattern, for_matching(full_cite))
        if match is None:
            return None
        # Taken from the cite as written: `Okonkwo ‘26` keeps its left quote (`v1-e31-t19`).
        short = full_cite[: match.end()].strip().rstrip(",")
        return short or None


def _reread_as_body(section: _ReadSection, reason: str) -> _ReadSection:
    """The same paragraph as evidence, with the assembly rule and the guess it overrode on record."""
    match = section.match
    return _ReadSection(
        read=section.read,
        match=ParagraphStyleMatch(
            unit=StructuralUnit.EVIDENCE,
            rule_id=f"{reason}:{match.rule_id}",
            match_source=StyleMatchSource.HEURISTIC,
            confidence=min(match.confidence, _REREAD_BODY_CONFIDENCE),
        ),
        in_text_box=section.in_text_box,
    )


#: What the look-ahead for a body steps over: page furniture, blank lines and lines read as nothing,
#: and an Undertag line, which belongs to the card above it. A built file writes its provenance line
#: as an Undertag below every cite (`v1-e33-t02`), and a highlighted cite with that line between it
#: and its body was read as body until `v1-e31-t24`.
_UNITS_A_BODY_IS_LOOKED_FOR_PAST: Final = (StructuralUnit.OTHER, StructuralUnit.UNDERTAG)


def _read_as_a_bold_tag(section: _ReadSection) -> _ReadSection:
    """The same paragraph as the tag of the card below it, with the rule it overrode on record."""
    match = section.match
    return _ReadSection(
        read=section.read,
        match=ParagraphStyleMatch(
            unit=StructuralUnit.TAG,
            rule_id=f"assembly-bold-tag-above-a-cite:{match.rule_id}",
            match_source=StyleMatchSource.HEURISTIC,
            confidence=_BOLD_TAG_CONFIDENCE,
        ),
        in_text_box=section.in_text_box,
    )


def _says_nothing(section: FileSection) -> bool:
    """A blank line, a table cell or a text box: stepped over, as the cite rules step over them."""
    return (
        not section.text.strip()
        or section.in_table
        or section.match.rule_id.startswith(("assembly-text-box", "assembly-table-cell"))
    )


def _followed_by_a_body(sections: Sequence[_ReadSection]) -> list[bool]:
    """For each paragraph, whether the next one that is not `OTHER` or an undertag is body."""
    followed = [False] * len(sections)
    a_body_is_next = False
    for position in range(len(sections) - 1, -1, -1):
        followed[position] = a_body_is_next
        unit = sections[position].match.unit
        if unit not in _UNITS_A_BODY_IS_LOOKED_FOR_PAST:
            a_body_is_next = unit is StructuralUnit.EVIDENCE
    return followed


def _card_follows(sections: Sequence[_ReadSection], position: int) -> bool:
    """Whether a cite or an evidence paragraph follows a tag before the next heading."""
    for section in sections[position + 1 :]:
        unit = section.match.unit
        if unit in (StructuralUnit.CITE, StructuralUnit.EVIDENCE):
            return True
        if unit in HEADING_UNITS or unit is StructuralUnit.ANALYTIC:
            return False
    return False


def _weakest_match_source(matches: Sequence[ParagraphStyleMatch]) -> StyleMatchSource:
    """The least certain of the match sources a card was built from.

    A card is only as trustworthy as the weakest step that built it, and reporting the strongest
    would make a heuristic guess look like a Verbatim style match in the accuracy evaluation.
    """
    if not matches:
        return StyleMatchSource.HEURISTIC
    return min(matches, key=lambda match: _MATCH_SOURCE_STRENGTH[match.match_source]).match_source

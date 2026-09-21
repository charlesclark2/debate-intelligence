"""Classifying a file's paragraphs and grouping them into cards.

The two modules below this one have made the file safe to read and turned its paragraphs into
text and formatting. This one decides what the paragraphs *are* and which of them belong to the
same card, and it is where a `ParsedCard`'s provenance is attached.

## The classifier is not re-implemented here

Every unit — pocket, hat, block, tag, cite, evidence, analytic, undertag — is resolved by
:func:`~debate_core.evidence.style_classifier.classify_paragraph`, which tries the Verbatim style
first, its aliases second and a measured heuristic last. This module adds three decisions the
classifier does not make, because each needs something the classifier cannot see:

* **A tag with no cite and no evidence under it is an analytic.** `Heading4` is what a debater
  types for a line of analysis as well as for a card's tag, and only the following paragraphs
  tell the two apart.
* **A card that is only its first and last words is abbreviated, not truncated.** An opencaselist
  disclosure often records a tag, a cite and an ellipsis between the opening and closing words —
  all the open-source rules require. Padding it or dropping it would both misrepresent the file,
  so it is kept and flagged.
* **Page furniture is `OTHER`, whatever style it carries.** A paragraph in a table cell or in a
  text box is a speech-time chart or a page banner, not a card. The classifier resolves a style
  before it looks at where a paragraph sits, so a `Heading4` in a table cell comes back from it
  as a tag; here it is `OTHER`, and the rule that said otherwise is kept in the rule id.

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

from debate_core.domain.caselist import SnapshotDate, SourceDocument
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
    StructuralUnit,
    StyleMatchSource,
    StyleProfile,
)
from debate_core.evidence.style_classifier import classify_paragraph
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
    concatenate_spanned_text,
    font_size_spans_for,
    formatting_spans_for,
    iter_text_box_paragraphs,
    read_paragraph,
)

__all__ = ["DOCX_PARSER_VERSION", "DebateDocxParser"]

#: Version recorded on every card this parser produces. Bumped whenever the output changes, so a
#: stored card always names the reading that produced it.
DOCX_PARSER_VERSION: Final = "2026.09.20-docx-1"

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

    @property
    def parser_version(self) -> str:
        return DOCX_PARSER_VERSION

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
            return self._failure(source, source_path, error.reason, error.detail)
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
    ) -> ParseFailure:
        return ParseFailure(
            source_sha256=source.sha256,
            source_path=source_path,
            reason=reason,
            detail=detail,
            parser_version=DOCX_PARSER_VERSION,
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
            sections.append(_ReadSection(read=read, match=match, in_text_box=body_paragraph.in_text_box))
        return sections

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
                )
            )
        return demoted

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
        read_sections = self._demote_tags_with_no_card(self._read_sections(package))

        open_headings: list[str | None] = [None, None, None, None]
        sections: list[FileSection] = []
        cards: list[ParsedCard] = []
        building: _CardUnderConstruction | None = None
        deletions_dropped = 0

        for section in read_sections:
            unit = section.match.unit
            path = tuple(text for text in open_headings if text is not None)
            deletions_dropped += section.read.deletions_dropped

            if unit in HEADING_UNITS:
                level = HEADING_UNITS.index(unit)
                open_headings[level] = section.read.text
                for lower in range(level + 1, len(open_headings)):
                    open_headings[lower] = None

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

            building = self._advance(building, section, path, cards, source, source_path, snapshot, camp)

        if building is not None:
            self._close(building, cards, source, source_path, snapshot, camp)

        warnings = list(package.warnings)
        if deletions_dropped:
            warnings.append(
                f"{deletions_dropped} tracked deletion(s) were dropped; the card is what the file "
                "would read as, not what it used to read as"
            )
        return ParsedDocument(
            source_sha256=source.sha256,
            source_path=source_path,
            parser_version=DOCX_PARSER_VERSION,
            profile_version=self._profile.profile_version,
            sections=tuple(sections),
            cards=tuple(cards),
            warnings=tuple(warnings),
        )

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
        completeness = self._completeness(body.text, full_cite)
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

    def _completeness(self, evidence_text: str, full_cite: str) -> CardCompleteness:
        """Decide whether a card is whole, abbreviated or a cite on its own. Goal criterion ac2."""
        if not evidence_text.strip():
            return CardCompleteness.CITE_ONLY
        markers = self._profile.cite.wiki_ellipsis_markers
        if any(marker in evidence_text for marker in markers) or any(
            marker in full_cite for marker in markers
        ):
            return CardCompleteness.ABBREVIATED
        return CardCompleteness.FULL

    def _short_cite(self, full_cite: str) -> str | None:
        """Split the part a debater says out loud off the front of a cite line.

        The pattern is the profile's, measured in `v1-e31-t02` and refined against the labelled
        set in `v1-e31-t05`. A cite this does not recognise gets no short cite rather than a
        guessed one: an invented short cite would be repeated back to a debater as fact.
        """
        if not full_cite.strip():
            return None
        match = re.match(self._profile.cite.short_cite_pattern, full_cite)
        if match is None:
            return None
        short = match.group(0).strip().rstrip(",")
        return short or None


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

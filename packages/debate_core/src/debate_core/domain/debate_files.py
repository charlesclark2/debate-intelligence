"""What reading a debate `.docx` produces: sections, cards, formatting spans and provenance.

A debate file is a document with a structure of its own. Under a pocket sit hats, under a hat
blocks, under a block tags, and under a tag the cite and the body of one card. The reader that
takes a file apart is an adapter (`debate_core.integrations.docx_parser`); what it hands back is
defined here, as values, because four other pieces of the platform consume it and none of them
should have to know that OOXML exists:

* card fingerprints and occurrence counts (`v1-e31-t04`),
* the incremental parse pipeline and its parsed-card store (`v1-e31-t06`),
* the accuracy evaluation (`v1-e31-t05`), which compares these objects against labels,
* V3's uploaded-file persistence (`v3-e20-t01`), which gives them revisions and stores them.

## The rules these models exist to enforce

**Evidence text is copied, never produced.** :attr:`ParsedCard.evidence_text` is the concatenated
text of the runs it came from, character for character: no normalization, no re-flowing, no
correction of a converter's mangled quotation marks. Every offset in a
:class:`FormattingSpan` indexes *that* string. This is the same rule the platform applies to
retrieved snapshots (architecture proposal §8), and it is what lets a card be checked against
the file it came from years later.

**An imported card is never verified.** A card that came out of somebody else's file has not been
through the platform's verification pipeline, and :class:`ParsedCard` cannot express that it has:
its :attr:`~ParsedCard.verification_status` is `UNVERIFIED` and a validator rejects anything else.

**A failure is a value, not a silent shrug.** A file that is malformed, oversized, macro-enabled
or simply not a `.docx` yields a :class:`ParseFailure` naming a :class:`ParseFailureReason` —
never a half-filled :class:`ParsedDocument`. A bulk import of twelve thousand files needs to be
able to list what it could not read.

**Nothing here identifies a person.** A card records the caselist, the snapshot, the SHA-256 and
the path it came from. There is no field for a debater, and the parser never reads `docProps`
authorship or comment authors out of the package (architecture proposal §14).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from debate_core.domain.base import DomainModel, NonEmptyText, Sha256Hex
from debate_core.domain.caselist.values import CaselistSlug, SnapshotDate, SourceOrigin
from debate_core.domain.enums import ProvenanceMode, VerificationStatus
from debate_core.domain.style_profile import (
    ParagraphStyleMatch,
    RunEmphasis,
    StructuralUnit,
    StyleMatchSource,
)

__all__ = [
    "IMPORTED_CARD_PROVENANCE_MODE",
    "IMPORTED_CARD_VERIFICATION_STATUS",
    "CardCompleteness",
    "FileImportProvenance",
    "FileSection",
    "FontSizeSpan",
    "FormattingSpan",
    "ParseFailure",
    "ParseFailureReason",
    "ParsedCard",
    "ParsedDocument",
]

#: Everything in this module came out of a file somebody imported. Never a fetch, never a model.
IMPORTED_CARD_PROVENANCE_MODE = ProvenanceMode.FILE_IMPORT

#: An imported card has not been through the platform's verification pipeline and never claims to.
IMPORTED_CARD_VERIFICATION_STATUS = VerificationStatus.UNVERIFIED


# --------------------------------------------------------------------------------------------
# Vocabularies
# --------------------------------------------------------------------------------------------


class CardCompleteness(StrEnum):
    """How much of a card the file actually contained.

    Caselist uploads are not team files. A disclosure often records only that a card exists —
    its tag, its cite, and the first and last few words of its body, which is all the open-source
    rules require. Such a card is *abbreviated*, not broken, and it is worth keeping: it is
    evidence that a team read something, and `v1-e31-t04` fingerprints it alongside full cards.
    Padding it out or dropping it would both be lies of a different kind.
    """

    FULL = "FULL"
    """Tag, cite and a body that runs from start to finish."""

    ABBREVIATED = "ABBREVIATED"
    """A body that carries a wiki-conversion ellipsis marker between its first and last words."""

    CITE_ONLY = "CITE_ONLY"
    """A tag and a cite with no body at all."""


class ParseFailureReason(StrEnum):
    """Why a file produced no :class:`ParsedDocument`.

    The reasons split into three groups: *we do not read this format* (V1 parses `.docx` only),
    *this file is a hazard* (the package is built to exhaust the reader, or carries macros), and
    *this file is broken*. The pipeline in `v1-e31-t06` reports them separately, because a corpus
    with a hundred PDFs in it is normal and a corpus with a hundred zip bombs in it is not.
    """

    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    """A `.doc`, a PDF or anything else V1 stores without parsing."""

    MACRO_ENABLED = "MACRO_ENABLED"
    """A `.docm`: a Word package carrying a VBA project. Not opened, whatever its extension says."""

    ENCRYPTED = "ENCRYPTED"
    """An OLE-wrapped, password-protected package. There is nothing to read without the password."""

    NOT_A_ZIP = "NOT_A_ZIP"
    """The bytes are not a zip container at all, so there is no `.docx` in them."""

    MALFORMED_PACKAGE = "MALFORMED_PACKAGE"
    """A zip that opens but is not a Word package, or whose members cannot be read."""

    MISSING_DOCUMENT_PART = "MISSING_DOCUMENT_PART"
    """No `word/document.xml`. Whatever else the package holds, it is not a document we can read."""

    TOO_LARGE = "TOO_LARGE"
    """The package's uncompressed size exceeds the reader's limit."""

    TOO_MANY_ENTRIES = "TOO_MANY_ENTRIES"
    """The package holds more members than the reader's limit allows."""

    COMPRESSION_RATIO_EXCEEDED = "COMPRESSION_RATIO_EXCEEDED"
    """One member expands by more than the reader's limit: the shape of a zip bomb."""

    FORBIDDEN_XML_CONSTRUCT = "FORBIDDEN_XML_CONSTRUCT"
    """A DTD, an entity declaration or an external reference. Never resolved, never expanded."""

    MALFORMED_XML = "MALFORMED_XML"
    """`word/document.xml` is not well-formed XML."""


# --------------------------------------------------------------------------------------------
# Formatting, as offsets into text that was copied exactly
# --------------------------------------------------------------------------------------------


class FormattingSpan(DomainModel):
    """One stretch of text carrying one kind of emphasis.

    Offsets are half-open character positions into the text of the section or card that holds the
    span — `start_offset` inclusive, `end_offset` exclusive — so a span can be applied by slicing
    and nothing has to re-derive where a run ended.

    **Underline appears once.** Verbatim encodes underline as a character style in body slots and
    as a direct `<w:u>` in structural slots, and CardMirror, which 63% of the surveyed corpus has
    been through, writes *both* on body runs when it exports. They are one underline. Two spans
    would double every underlined stretch in most of the corpus; the parser collapses them, and
    :attr:`rule_id` records which encoding was found.
    """

    emphasis: RunEmphasis = Field(description="What this stretch of text carries.")
    start_offset: int = Field(ge=0, description="Inclusive start character offset.")
    end_offset: int = Field(gt=0, description="Exclusive end character offset.")
    highlight_color: str | None = Field(
        default=None,
        description="The `w:highlight` token, e.g. `cyan`. Set only when emphasis is HIGHLIGHT.",
    )
    rule_id: NonEmptyText = Field(description="The profile or classifier rule that produced this span.")
    match_source: StyleMatchSource = Field(description="Style match, alias match, or heuristic.")

    @model_validator(mode="after")
    def _check_span(self) -> Self:
        if self.start_offset >= self.end_offset:
            raise ValueError(
                f"span start_offset ({self.start_offset}) must be before end_offset ({self.end_offset})"
            )
        if self.emphasis is RunEmphasis.HIGHLIGHT and self.highlight_color is None:
            raise ValueError("a HIGHLIGHT span must name the highlight colour it was written with")
        if self.emphasis is not RunEmphasis.HIGHLIGHT and self.highlight_color is not None:
            raise ValueError(
                f"only a HIGHLIGHT span carries a colour; {self.emphasis} span named {self.highlight_color!r}"
            )
        return self

    @property
    def length(self) -> int:
        """How many characters this span covers."""
        return self.end_offset - self.start_offset


class FontSizeSpan(DomainModel):
    """One stretch of text at one font size, in half-points.

    Separate from :class:`FormattingSpan` because a size is a measurement rather than an emphasis.
    The profile's shrink rule turns a size into the `SHRUNK` emphasis where it means "not read
    aloud", but the measured value is kept too: a writer that has to reproduce the file needs the
    number, and the accuracy evaluation compares numbers rather than a threshold's verdict.
    """

    start_offset: int = Field(ge=0, description="Inclusive start character offset.")
    end_offset: int = Field(gt=0, description="Exclusive end character offset.")
    half_points: int = Field(gt=0, description="`w:sz` in half-points; 22 is ordinary body text.")

    @model_validator(mode="after")
    def _check_span(self) -> Self:
        if self.start_offset >= self.end_offset:
            raise ValueError(
                f"span start_offset ({self.start_offset}) must be before end_offset ({self.end_offset})"
            )
        return self

    @property
    def length(self) -> int:
        """How many characters this span covers."""
        return self.end_offset - self.start_offset


# --------------------------------------------------------------------------------------------
# Provenance
# --------------------------------------------------------------------------------------------


class FileImportProvenance(DomainModel):
    """Where one card came from, precisely enough to find it again in the original file.

    The SHA-256 identifies the bytes, the path says where in the archive they sat, and the element
    index range says which paragraphs of `word/document.xml` the card was built from. Together
    with `parser_version` and `profile_version` that is a reproducible claim: re-run the same
    parser and profile over the same bytes and the same cards come out.

    A caselist import names its caselist; an OpenEv camp release names its camp instead, and
    carries no caselist, exactly as
    :class:`~debate_core.domain.caselist.entities.SourceDocument` requires.
    """

    provenance_mode: ProvenanceMode = Field(
        default=IMPORTED_CARD_PROVENANCE_MODE,
        description="Always FILE_IMPORT: this card was read out of an imported file.",
    )
    source_sha256: Sha256Hex = Field(description="SHA-256 of the file's bytes. Identity of the source.")
    source_path: NonEmptyText = Field(description="Path of the file inside the archive it arrived in.")
    origin: SourceOrigin = Field(description="Which import brought the bytes in.")
    caselist: CaselistSlug | None = Field(
        default=None, description="Caselist the file was disclosed in; None for an OpenEv camp file."
    )
    camp: NonEmptyText | None = Field(
        default=None, description="Camp that released the file; None for a caselist disclosure."
    )
    snapshot: SnapshotDate = Field(description="The snapshot the file was read under.")
    first_element_index: int = Field(
        ge=0, description="Index in the document body of the first paragraph this card was built from."
    )
    last_element_index: int = Field(
        ge=0, description="Index in the document body of the last paragraph this card was built from."
    )
    parser_version: NonEmptyText = Field(description="Version of the parser that produced the card.")
    profile_version: NonEmptyText = Field(description="Version of the style profile it resolved through.")

    @model_validator(mode="after")
    def _check_provenance(self) -> Self:
        if self.provenance_mode is not IMPORTED_CARD_PROVENANCE_MODE:
            raise ValueError(
                f"a parsed card is always {IMPORTED_CARD_PROVENANCE_MODE}, not {self.provenance_mode}"
            )
        if self.origin is SourceOrigin.CASELIST_ARCHIVE and self.caselist is None:
            raise ValueError("a card parsed out of a caselist archive must name its caselist")
        if self.origin is SourceOrigin.OPENEV and self.caselist is not None:
            raise ValueError(
                f"an OpenEv camp file belongs to a camp, not to a caselist; got caselist={self.caselist!r}"
            )
        if self.last_element_index < self.first_element_index:
            raise ValueError(
                f"last_element_index ({self.last_element_index}) precedes first_element_index "
                f"({self.first_element_index})"
            )
        return self


# --------------------------------------------------------------------------------------------
# What a parse produced
# --------------------------------------------------------------------------------------------


class FileSection(DomainModel):
    """One paragraph of the file, classified, with its place in the heading hierarchy.

    Every paragraph becomes a section, including the ones that turn out to be `OTHER`. Keeping
    them is what makes the element index range on a card meaningful and what lets the accuracy
    evaluation count false positives as well as misses.

    `section_path` is the text of the heading ancestors above this paragraph, outermost first:
    `("Data Centre Moratorium Negative", "Grid Reliability", "AT: Reserve Margin Turn")`. A
    heading's own text is not in its own path.
    """

    unit: StructuralUnit = Field(description="What this paragraph is.")
    text: str = Field(description="The paragraph's text, exactly as its runs spell it.")
    section_path: tuple[str, ...] = Field(
        default=(), description="Text of the heading ancestors above this paragraph, outermost first."
    )
    match: ParagraphStyleMatch = Field(description="The unit, the rule that decided it, and how sure.")
    element_index: int = Field(ge=0, description="Position of this paragraph in the document body.")
    formatting_spans: tuple[FormattingSpan, ...] = Field(
        default=(), description="Emphasis spans, as offsets into `text`."
    )
    font_size_spans: tuple[FontSizeSpan, ...] = Field(
        default=(), description="Font sizes, as offsets into `text`."
    )
    in_table: bool = Field(default=False, description="Whether the paragraph sits inside a table cell.")

    @model_validator(mode="after")
    def _check_spans_fit(self) -> Self:
        _require_spans_within(self.text, self.formatting_spans, self.font_size_spans, label="section")
        if self.match.unit is not self.unit:
            raise ValueError(
                f"section says it is {self.unit} but its match says {self.match.unit}; one of them is wrong"
            )
        return self


class ParsedCard(DomainModel):
    """A tag, its cite and its evidence, as one file spelled them.

    This is the unit `v1-e31-t04` fingerprints and `v1-e31-t06` stores. It is deliberately not a
    :class:`~debate_core.domain.card.Card`: a `Card` is a student's own work with a verified
    quotation behind it, and conflating the two is exactly the mistake the evidence-integrity rule
    exists to prevent. A `ParsedCard` says what somebody else's file contained, and says so as
    `UNVERIFIED`.

    `match_source` and `confidence` are the *weakest* of the matches that built the card, and
    `rule_ids` names every rule that fired, in order. Weakest rather than strongest because a card
    is only as trustworthy as the least certain step that built it, and reporting the strongest
    would make a guess look like a style match in the accuracy evaluation.

    This has a consequence worth knowing before reading a number: an ordinary Verbatim card
    reports `HEURISTIC`. Verbatim gives a card's body no paragraph style of its own, so the body
    is recognised by its underlining and highlighting rather than by a style, and that step is a
    heuristic however perfectly styled the tag and cite above it are. `rule_ids` is where the
    detail lives — `verbatim-style-id:Heading4`, `verbatim-cite-run-style`,
    `heuristic-marked-up-body-text` — and it is what `v1-e31-t05` sorts misses by.
    """

    tag: str = Field(default="", description="The claim the card is read for; empty if the file had none.")
    short_cite: str | None = Field(
        default=None, description="The part a debater says out loud, e.g. `Okonkwo 26`; None if unreadable."
    )
    full_cite: str = Field(default="", description="The whole cite line, exactly as written.")
    undertag: str = Field(
        default="",
        description="Undertag lines under the tag, joined by newlines; empty when the card has none.",
    )
    evidence_text: str = Field(
        default="", description="The card's body, the runs' text concatenated, copied exactly."
    )
    completeness: CardCompleteness = Field(description="FULL, ABBREVIATED or CITE_ONLY.")
    section_path: tuple[str, ...] = Field(
        default=(), description="Text of the heading ancestors above the tag, outermost first."
    )
    formatting_spans: tuple[FormattingSpan, ...] = Field(
        default=(), description="Emphasis spans, as offsets into `evidence_text`."
    )
    font_size_spans: tuple[FontSizeSpan, ...] = Field(
        default=(), description="Font sizes, as offsets into `evidence_text`."
    )
    match_source: StyleMatchSource = Field(description="The weakest match source used to build the card.")
    confidence: float = Field(
        ge=0.0, le=1.0, description="The lowest confidence of the matches that built the card."
    )
    rule_ids: tuple[NonEmptyText, ...] = Field(
        default=(), description="Every rule that fired while building this card, in order."
    )
    verification_status: VerificationStatus = Field(
        default=IMPORTED_CARD_VERIFICATION_STATUS,
        description="Always UNVERIFIED: an imported card has not been through verification.",
    )
    provenance: FileImportProvenance = Field(description="Where in which file this card came from.")

    @model_validator(mode="after")
    def _check_card(self) -> Self:
        if self.verification_status is not IMPORTED_CARD_VERIFICATION_STATUS:
            raise ValueError(
                f"a parsed card is always {IMPORTED_CARD_VERIFICATION_STATUS}; it has not been "
                f"verified against a publisher's text, so it cannot claim {self.verification_status}"
            )
        _require_spans_within(self.evidence_text, self.formatting_spans, self.font_size_spans, label="card")
        if self.completeness is CardCompleteness.CITE_ONLY and self.evidence_text.strip():
            raise ValueError("a CITE_ONLY card has no body, but this one carries evidence text")
        if self.completeness is not CardCompleteness.CITE_ONLY and not self.evidence_text.strip():
            raise ValueError(
                f"a {self.completeness} card carries a body, but this one has none; it is CITE_ONLY"
            )
        return self

    @property
    def is_abbreviated(self) -> bool:
        """True when the file recorded only part of the card's body, or none of it."""
        return self.completeness is not CardCompleteness.FULL


class ParsedDocument(DomainModel):
    """Everything one `.docx` turned into: its paragraphs, its cards and what the reader noticed.

    `sections` is every paragraph in document order; `cards` are the groupings built from them.
    A card's paragraphs are still in `sections` — the two are views of one file, not a split.
    """

    source_sha256: Sha256Hex = Field(description="SHA-256 of the parsed file's bytes.")
    source_path: NonEmptyText = Field(description="Path of the file inside the archive it arrived in.")
    parser_version: NonEmptyText = Field(description="Version of the parser that read the file.")
    profile_version: NonEmptyText = Field(description="Version of the style profile it resolved through.")
    sections: tuple[FileSection, ...] = Field(
        default=(), description="Every paragraph of the body, in document order."
    )
    cards: tuple[ParsedCard, ...] = Field(
        default=(), description="The cards assembled from those paragraphs, in document order."
    )
    warnings: tuple[NonEmptyText, ...] = Field(
        default=(), description="What the reader could not do, in the order it found it."
    )

    @model_validator(mode="after")
    def _check_document_order(self) -> Self:
        indices = [section.element_index for section in self.sections]
        if indices != sorted(indices):
            raise ValueError("sections must be in document order by element_index")
        for card in self.cards:
            if card.provenance.source_sha256 != self.source_sha256:
                raise ValueError(
                    f"card provenance names source {card.provenance.source_sha256[:12]}… but the "
                    f"document is {self.source_sha256[:12]}…"
                )
        return self

    @property
    def card_count(self) -> int:
        """How many cards were assembled."""
        return len(self.cards)

    def sections_of(self, unit: StructuralUnit) -> tuple[FileSection, ...]:
        """Every section of one unit, in document order."""
        return tuple(section for section in self.sections if section.unit is unit)


class ParseFailure(DomainModel):
    """A file the reader refused or could not read, and why.

    Returned rather than raised: a pipeline reading twelve thousand caselist files needs a row per
    failure it can count and publish, not an exception that stops the run. `detail` is safe to log
    — it names limits and formats, never document text, a team code or a filesystem path outside
    the archive.
    """

    source_sha256: Sha256Hex = Field(description="SHA-256 of the file's bytes.")
    source_path: NonEmptyText = Field(description="Path of the file inside the archive it arrived in.")
    reason: ParseFailureReason = Field(description="Which refusal this was.")
    detail: str = Field(default="", description="What was seen, in terms of limits and formats only.")
    parser_version: NonEmptyText = Field(description="Version of the parser that refused the file.")


# --------------------------------------------------------------------------------------------
# Shared invariants
# --------------------------------------------------------------------------------------------


def _require_spans_within(
    text: str,
    formatting_spans: tuple[FormattingSpan, ...],
    font_size_spans: tuple[FontSizeSpan, ...],
    *,
    label: str,
) -> None:
    """Reject spans that run past the end of the text they index into.

    An offset past the end means the text and the formatting were derived from different readings
    of the file, which is the one failure mode that would silently corrupt every downstream use of
    a card.
    """
    length = len(text)
    for span in formatting_spans:
        if span.end_offset > length:
            raise ValueError(
                f"{label} {span.emphasis} span {span.start_offset}-{span.end_offset} runs past the "
                f"end of its {length}-character text"
            )
    for size_span in font_size_spans:
        if size_span.end_offset > length:
            raise ValueError(
                f"{label} font-size span {size_span.start_offset}-{size_span.end_offset} runs past "
                f"the end of its {length}-character text"
            )

"""What extraction produces from fetched bytes, and how it refuses (v1-e04-t04).

:class:`ExtractedContent` is what every
:class:`~debate_core.application.ports.providers.ContentExtractor` returns: the paragraphs in reading
order, which extractor produced them at which version, unverified metadata hints, and quality
signals the access classifier (v1-e04-t03) and ArticleService (v1-e04-t05) read. The adapters live
in :mod:`debate_core.integrations` (`html_extractor`, `pdf_extractor`); this module holds the values
they exchange and the one decision they share, which kind of document the bytes are.

**Extraction never changes a word.** It decides which text is the article and where paragraphs
break; it does not correct, summarize or rewrite. The one place it touches characters is a PDF line
that ends in a hyphen (:mod:`debate_core.retrieval.pdf_layout`), and every such join is recorded
here as a :class:`LineJoin`, with what was decided and on what evidence, so that verification
(E03) and a reviewer can see exactly where the text differs from the printed lines. Every line
removed as a running header, footer or page number is recorded too, as a :class:`RemovedLine`.

**A refusal is an exception, never a partial result.** An encrypted PDF, a page that declares
itself paywalled, a type no extractor reads, a document past the size or page limit: each raises
its own :class:`ExtractionError` and nothing is extracted. The caller (ArticleService) maps the
refusal to an access status; it never receives half a document.

**Metadata hints are unverified,** and :class:`UnverifiedMetadataHints` says so in its name. They
are strings as the page states them, inputs to CitationService (E06), never citation fields.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal, Protocol, Self

from pydantic import Field, model_validator

from debate_core.domain import DomainModel, NonEmptyText
from debate_core.retrieval.content_sniffing import sniff_content_type
from debate_core.retrieval.fetch_types import FetchResult

__all__ = [
    "ContentTypeDispatcher",
    "DocumentKind",
    "DocumentTooLarge",
    "EncryptedDocument",
    "ExtractedContent",
    "ExtractionError",
    "ExtractionQuality",
    "JoinDecision",
    "LineEndCharacter",
    "LineJoin",
    "PageEdge",
    "PaywallMarkerFound",
    "RemovalReason",
    "RemovedLine",
    "TooManyPages",
    "UnreadableDocument",
    "UnsupportedContentType",
    "UnverifiedMetadataHints",
    "document_kind",
]


# --------------------------------------------------------------------------------------------
# Refusals
# --------------------------------------------------------------------------------------------


class ExtractionError(Exception):
    """An extractor refused a document. Nothing was extracted from it."""


class UnsupportedContentType(ExtractionError, ValueError):
    """The bytes are neither HTML nor PDF, by their own signature or by the declared type.

    Also a `ValueError`, which is what the port has always said an extractor raises for a type it
    does not handle.
    """

    def __init__(self, declared: str | None, sniffed: str | None) -> None:
        self.declared = declared
        self.sniffed = sniffed
        super().__init__(
            f"no extractor reads this document (declared {declared!r}, bytes look like {sniffed!r})"
        )


class EncryptedDocument(ExtractionError):
    """The PDF is encrypted. Its text is not read, even when an empty password would open it.

    An owner password with no user password is how a PDF restricts copying, which is the platform's
    "DRM-protected" case: the publisher has said not to take the text out, so it is not taken.
    """

    def __init__(self) -> None:
        super().__init__("the PDF is encrypted; its text is not extracted")


class PaywallMarkerFound(ExtractionError):
    """The page declares its content is not free to read (schema.org `isAccessibleForFree`)."""

    def __init__(self, marker: str) -> None:
        self.marker = marker
        super().__init__(f"the page declares itself paywalled ({marker}); its text is not extracted")


class DocumentTooLarge(ExtractionError):
    """The document has more bytes than the extractor's limit, so it is not parsed at all."""

    def __init__(self, size_bytes: int, limit_bytes: int) -> None:
        self.size_bytes = size_bytes
        self.limit_bytes = limit_bytes
        super().__init__(f"the document is {size_bytes} bytes, over the {limit_bytes}-byte limit")


class TooManyPages(ExtractionError):
    """The PDF has more pages than the extractor's limit, so no page is read."""

    def __init__(self, page_count: int, limit: int) -> None:
        self.page_count = page_count
        self.limit = limit
        super().__init__(f"the PDF has {page_count} pages, over the {limit}-page limit")


class UnreadableDocument(ExtractionError):
    """The document could not be parsed or decoded without guessing at its characters."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


# --------------------------------------------------------------------------------------------
# Which extractor reads the bytes
# --------------------------------------------------------------------------------------------


class DocumentKind(StrEnum):
    """The two kinds of document the platform extracts text from."""

    HTML = "html"
    PDF = "pdf"


_DECLARED_KINDS: Final = {
    "text/html": DocumentKind.HTML,
    "application/xhtml+xml": DocumentKind.HTML,
    "application/pdf": DocumentKind.PDF,
    "application/x-pdf": DocumentKind.PDF,
}
_SNIFFED_KINDS: Final = {"text/html": DocumentKind.HTML, "application/pdf": DocumentKind.PDF}
_SNIFFED_WITHOUT_OPINION: Final = frozenset({"application/xml"})
"""An XHTML page starts `<?xml`, so an XML signature defers to the declared type."""


def document_kind(fetched: FetchResult) -> DocumentKind:
    """Which extractor reads `fetched`, or :class:`UnsupportedContentType` when neither does.

    The bytes decide first: a PDF served as `text/html` or as `application/octet-stream` is a PDF,
    and a body that starts like HTML is HTML whatever the server called it. When the bytes match no
    signature (or only XML's), the declared `Content-Type` decides. Bytes with any other signature
    (an image, an archive) are refused whatever was declared.
    """
    declared = (fetched.content_type or "").split(";", 1)[0].strip().lower() or None
    sniffed = sniff_content_type(fetched.body)
    if sniffed in _SNIFFED_KINDS:
        return _SNIFFED_KINDS[sniffed]
    if (sniffed is None or sniffed in _SNIFFED_WITHOUT_OPINION) and declared in _DECLARED_KINDS:
        return _DECLARED_KINDS[declared]
    raise UnsupportedContentType(declared, sniffed)


class _Extractor(Protocol):
    """The part of the ContentExtractor port the dispatcher calls (the port lives above this layer)."""

    @property
    def name(self) -> str: ...

    def extract(self, fetched: FetchResult) -> ExtractedContent: ...


class ContentTypeDispatcher:
    """A ContentExtractor that hands each document to the HTML or the PDF extractor.

    The choice is :func:`document_kind`'s, so a mislabelled PDF reaches the PDF extractor and a type
    neither reads raises :class:`UnsupportedContentType` before either is called.
    """

    def __init__(self, *, html: _Extractor, pdf: _Extractor) -> None:
        self._extractors = {DocumentKind.HTML: html, DocumentKind.PDF: pdf}

    @property
    def name(self) -> str:
        return "content-type-dispatcher"

    def extract(self, fetched: FetchResult) -> ExtractedContent:
        return self._extractors[document_kind(fetched)].extract(fetched)


# --------------------------------------------------------------------------------------------
# What extraction produces
# --------------------------------------------------------------------------------------------


class UnverifiedMetadataHints(DomainModel):
    """Unverified metadata an extractor noticed on the page.

    Deliberately separate from :class:`~debate_core.domain.Citation`, and deliberately all
    strings: these are raw, unparsed hints, as the page states them. CitationService (E06) is what
    turns a hint into a citation field with a recorded source, and a hint that cannot be confirmed
    leaves the cite field missing rather than filled in (architecture proposal §8).
    """

    title: str | None = Field(default=None, description="Title as the document states it.")
    authors: tuple[str, ...] = Field(default=(), description="Byline text, unparsed, in page order.")
    published_at: str | None = Field(default=None, description="Date string exactly as found.")
    site_name: str | None = Field(default=None, description="Site or publication name as stated.")
    canonical_url: str | None = Field(default=None, description="`rel=canonical` target, if declared.")


class ExtractionQuality(DomainModel):
    """Signals about how well extraction went, used to decide whether to trust the text."""

    character_count: int = Field(ge=0, description="Characters of readable text extracted.")
    paragraph_count: int = Field(ge=0, description="Paragraphs extracted.")
    fallback_used: bool = Field(
        default=False, description="True when the primary extractor fell short and a fallback ran."
    )
    boilerplate_ratio: float | None = Field(
        default=None, ge=0, le=1, description="Share of the document discarded as navigation or ads."
    )


type LineEndCharacter = Literal["-", "‐", "­", "–", "—"]
"""The characters a PDF line can end in where the next line joins it with no space: hyphen-minus,
hyphen, soft hyphen, en dash, em dash."""


class JoinDecision(StrEnum):
    """Why a line-end character was kept or dropped when two PDF lines were joined."""

    SOFT_HYPHEN = "soft_hyphen"
    """U+00AD, a discretionary hyphen, printed only at a break: dropped."""

    NOT_A_WORD_BREAK = "not_a_word_break"
    """A dash, or something other than a letter on either side (`2019-|2024`): kept."""

    HYPHENATED_FORM_IN_DOCUMENT = "hyphenated_form_in_document"
    """Elsewhere mid-line the document spells the word with the hyphen, never without: kept."""

    JOINED_FORM_IN_DOCUMENT = "joined_form_in_document"
    """Elsewhere mid-line the document spells the word without the hyphen, never with: dropped."""

    UNDETERMINED = "undetermined"
    """Neither spelling, or both, appear elsewhere: kept, so no printed character is lost."""


_DROPPING_DECISIONS: Final = frozenset({JoinDecision.SOFT_HYPHEN, JoinDecision.JOINED_FORM_IN_DOCUMENT})


class LineJoin(DomainModel):
    """Two PDF lines of one paragraph joined with no space, because the first ended in a hyphen.

    `offset` is where the line-end character is in the paragraph when it was kept, and where it
    would have been when it was dropped: the paragraph's text up to `offset` is the first line's.
    """

    paragraph_index: int = Field(ge=0, description="Which paragraph of the ExtractedContent.")
    offset: int = Field(ge=1, description="Character offset of the join in that paragraph.")
    page_number: int = Field(ge=1, description="Page of the line that ended in the hyphen.")
    character: LineEndCharacter = Field(description="The line-end character as printed.")
    hyphen_kept: bool = Field(description="Whether the character is in the paragraph's text.")
    decision: JoinDecision = Field(description="Which branch of the rule decided.")
    hyphenated_form_count: int = Field(
        default=0, ge=0, description="Mid-line occurrences elsewhere of the word with the hyphen."
    )
    joined_form_count: int = Field(
        default=0, ge=0, description="Mid-line occurrences elsewhere of the word without it."
    )

    @model_validator(mode="after")
    def _check_decision_matches_outcome(self) -> Self:
        if self.hyphen_kept == (self.decision in _DROPPING_DECISIONS):
            raise ValueError(f"a {self.decision.value} join cannot have hyphen_kept={self.hyphen_kept}")
        if (self.decision is JoinDecision.SOFT_HYPHEN) != (self.character == "­"):
            raise ValueError("a join is soft_hyphen exactly when its character is U+00AD")
        return self


class PageEdge(StrEnum):
    """Which end of the page a removed line was at."""

    TOP = "top"
    BOTTOM = "bottom"


class RemovalReason(StrEnum):
    """Why a PDF line was left out of the text."""

    RUNNING_HEADER = "running_header"
    """Its exact text is near the top of two or more pages."""

    RUNNING_FOOTER = "running_footer"
    """Its exact text is near the bottom of two or more pages."""

    PAGE_NUMBER = "page_number"
    """Its whole text is a page-number form whose number advances with the page."""


class RemovedLine(DomainModel):
    """One line of a PDF left out of the text, and why."""

    page_number: int = Field(ge=1, description="Page the line was on.")
    edge: PageEdge = Field(description="Whether it was near the top or the bottom of the page.")
    reason: RemovalReason = Field(description="Which rule removed it.")
    text: str = Field(description="The line as extracted.")


class ExtractedContent(DomainModel):
    """Readable text pulled out of a fetched document.

    Paragraphs are kept as a sequence in reading order rather than as one string, because the
    paragraph is the unit a card's offsets are anchored to and the unit a model is allowed to
    refer to when it selects a passage.

    Extraction never changes words. No spelling fixes, no summarizing, no model cleanup: the text
    that reaches a card has to be the publisher's. The quality counts are checked against the
    paragraphs, and each join against the paragraph it is in, so neither can describe text that is
    not there.
    """

    paragraphs: tuple[str, ...] = Field(default=(), description="Body paragraphs in reading order.")
    extractor_name: NonEmptyText = Field(description="Extractor that produced this text.")
    extractor_version: NonEmptyText = Field(
        description="Its version and its libraries'; on the snapshot, so extraction stays reproducible."
    )
    metadata_hints: UnverifiedMetadataHints = Field(
        default_factory=UnverifiedMetadataHints, description="Unverified metadata seen on the page."
    )
    quality: ExtractionQuality = Field(description="Signals about the extraction itself.")
    line_joins: tuple[LineJoin, ...] = Field(
        default=(), description="Every PDF line joined at a hyphen, in reading order; empty for HTML."
    )
    removed_lines: tuple[RemovedLine, ...] = Field(
        default=(), description="Every PDF line left out as a header, footer or page number; empty for HTML."
    )

    @property
    def text(self) -> str:
        """The paragraphs joined by blank lines, the form the normalizer (E03-t01) takes."""
        return "\n\n".join(self.paragraphs)

    @model_validator(mode="after")
    def _check_signals_describe_the_text(self) -> Self:
        for paragraph in self.paragraphs:
            # Checked, never stripped: a model that trimmed text would move every offset after it.
            if not paragraph.strip() or paragraph != paragraph.strip():
                raise ValueError("a paragraph must be non-blank, with no whitespace at either end")
        if self.quality.paragraph_count != len(self.paragraphs):
            raise ValueError("quality.paragraph_count must equal the number of paragraphs")
        if self.quality.character_count != sum(len(paragraph) for paragraph in self.paragraphs):
            raise ValueError("quality.character_count must equal the paragraphs' total length")
        for join in self.line_joins:
            if join.paragraph_index >= len(self.paragraphs):
                raise ValueError(f"a line join names paragraph {join.paragraph_index}, which does not exist")
            paragraph = self.paragraphs[join.paragraph_index]
            if join.offset > len(paragraph):
                raise ValueError(f"a line join's offset {join.offset} is past its paragraph's end")
            if join.hyphen_kept and paragraph[join.offset : join.offset + 1] != join.character:
                raise ValueError(f"a kept join's character is not at offset {join.offset} of its paragraph")
        return self

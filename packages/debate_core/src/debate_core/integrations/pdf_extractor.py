"""The open-access PDF extractor: pypdf reads the lines, the layout rules decide the text (v1-e04-t04).

:class:`PdfExtractor` implements the
:class:`~debate_core.application.ports.providers.ContentExtractor` port for PDFs. pypdf reads each
page's lines with where they start and their type size; :mod:`debate_core.retrieval.pdf_layout`
removes running headers, footers and page numbers, joins lines at hyphens and builds paragraphs, and
records every removal and join on the result.

## What it refuses, before reading a word

Each is a :mod:`debate_core.retrieval.extraction` error:

| Refusal | When |
|---|---|
| `UnsupportedContentType` | the bytes are not a PDF |
| `DocumentTooLarge` | more bytes than `max_bytes`; nothing is parsed |
| `EncryptedDocument` | the file is encrypted, even when an empty password would open it |
| `TooManyPages` | more pages than `max_pages`; no page is read |
| `UnreadableDocument` | pypdf cannot parse it, a stream is cut short or expands past `max_stream_bytes` |

A refusal is an exception, never part of the text. The two size limits and pypdf's own decompression
limits (lowered here to `max_stream_bytes` per stream, for every filter) are what keep a PDF bomb
from costing more than reading a large open-access paper does. There is no OCR: a scanned PDF has
no text layer and produces no paragraphs.

## Metadata hints

The document information dictionary's `/Title` and `/Author`, as written there, unverified. A PDF
states no publication date or canonical URL that the platform could rely on, so those stay empty.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from io import BytesIO
from typing import Any, Final

import pypdf
from pypdf import PdfReader, apply_configuration
from pypdf.errors import FileNotDecryptedError, LimitReachedError

from debate_core.retrieval.content_sniffing import sniff_content_type
from debate_core.retrieval.extraction import (
    DocumentKind,
    DocumentTooLarge,
    EncryptedDocument,
    ExtractedContent,
    ExtractionQuality,
    TooManyPages,
    UnreadableDocument,
    UnsupportedContentType,
    UnverifiedMetadataHints,
    document_kind,
)
from debate_core.retrieval.fetch_types import FetchResult
from debate_core.retrieval.pdf_layout import PdfPageText, PositionedLine, lay_out_pages

__all__ = [
    "DEFAULT_MAX_BYTES",
    "DEFAULT_MAX_PAGES",
    "DEFAULT_MAX_STREAM_BYTES",
    "LAYOUT_RULES_VERSION",
    "PdfExtractor",
]

EXTRACTOR_NAME: Final = "pypdf"
LAYOUT_RULES_VERSION: Final = "pdf-layout-1"
"""Bumped whenever a rule in `debate_core.retrieval.pdf_layout` changes what text a PDF produces."""

DEFAULT_MAX_BYTES: Final = 50 * 1024 * 1024
"""A long open-access report with figures is a few tens of megabytes; past this, nothing is parsed."""
DEFAULT_MAX_PAGES: Final = 500
DEFAULT_MAX_STREAM_BYTES: Final = 20_000_000
"""How far one stream may expand when decoded; pypdf's own default is 75 MB."""

_DECODE_LIMITS: Final = (
    "zlib_maximum_output_length",
    "lzw_maximum_output_length",
    "run_length_maximum_output_length",
    "brotli_maximum_output_length",
    "jbig2_maximum_output_length",
    "array_based_stream_maximum_output_length",
)


class PdfExtractor:
    """Readable text from an open-access PDF, with every removal and hyphen join recorded."""

    def __init__(
        self,
        *,
        max_bytes: int = DEFAULT_MAX_BYTES,
        max_pages: int = DEFAULT_MAX_PAGES,
        max_stream_bytes: int = DEFAULT_MAX_STREAM_BYTES,
    ) -> None:
        self._max_bytes = max_bytes
        self._max_pages = max_pages
        self._max_stream_bytes = max_stream_bytes

    @property
    def name(self) -> str:
        return EXTRACTOR_NAME

    @property
    def version(self) -> str:
        """The layout rules' version and pypdf's, which together decide the text."""
        return f"{LAYOUT_RULES_VERSION}+pypdf-{pypdf.__version__}"

    def extract(self, fetched: FetchResult) -> ExtractedContent:
        if document_kind(fetched) is not DocumentKind.PDF:
            raise UnsupportedContentType(fetched.content_type, sniff_content_type(fetched.body))
        if len(fetched.body) > self._max_bytes:
            raise DocumentTooLarge(len(fetched.body), self._max_bytes)
        limits = dict.fromkeys(_DECODE_LIMITS, self._max_stream_bytes)
        with apply_configuration(**limits):
            pages, hints = self._read(fetched.body)
        layout = lay_out_pages(pages)
        total = layout.kept_characters + layout.removed_characters
        return ExtractedContent(
            paragraphs=layout.paragraphs,
            extractor_name=EXTRACTOR_NAME,
            extractor_version=self.version,
            metadata_hints=hints,
            quality=ExtractionQuality(
                character_count=sum(len(paragraph) for paragraph in layout.paragraphs),
                paragraph_count=len(layout.paragraphs),
                fallback_used=False,
                boilerplate_ratio=layout.removed_characters / total if total else None,
            ),
            line_joins=layout.line_joins,
            removed_lines=layout.removed_lines,
        )

    def _read(self, body: bytes) -> tuple[list[PdfPageText], UnverifiedMetadataHints]:
        try:
            reader = PdfReader(BytesIO(body), strict=False)
            if reader.is_encrypted:
                raise EncryptedDocument()
            page_count = len(reader.pages)
            if page_count > self._max_pages:
                raise TooManyPages(page_count, self._max_pages)
            pages = [
                PdfPageText(page_number=number, lines=_page_lines(page))
                for number, page in enumerate(reader.pages, start=1)
            ]
        except (EncryptedDocument, TooManyPages):
            raise
        except FileNotDecryptedError as error:
            raise EncryptedDocument() from error
        except LimitReachedError as error:
            raise UnreadableDocument(
                f"a stream expands past the {self._max_stream_bytes}-byte limit"
            ) from error
        except Exception as error:
            # pypdf raises its own errors and plain ones (KeyError, ValueError) on a malformed file.
            # None of them leaves usable text, and none may reach a caller as anything but a refusal.
            raise UnreadableDocument(f"pypdf could not read the PDF ({type(error).__name__})") from error
        return pages, _metadata_hints(reader)


def _page_lines(page: pypdf.PageObject) -> tuple[PositionedLine, ...]:
    """The page's lines in drawing order, each placed where its first visible text starts."""
    lines: list[PositionedLine] = []
    parts: list[str] = []
    start: list[tuple[float, float, float]] = []

    def finish_line() -> None:
        text = "".join(parts)
        if text.strip() and start:
            x, y, size = start[0]
            lines.append(PositionedLine(text=text, x=x, y=y, font_size=size))
        parts.clear()
        start.clear()

    def visit(text: str, cm: Sequence[float], tm: Sequence[float], _font: Any, font_size: float) -> None:
        for number, piece in enumerate(text.split("\n")):
            if number:
                finish_line()
            if piece.strip() and not start:
                start.append(_placement(cm, tm, font_size))
            parts.append(piece)

    page.extract_text(visitor_text=visit)
    finish_line()
    return tuple(lines)


def _placement(cm: Sequence[float], tm: Sequence[float], font_size: float) -> tuple[float, float, float]:
    """Where a run of text starts on the page, and its type size, from the text and graphics matrices."""
    x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
    y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
    scale = math.hypot(tm[2], tm[3]) * math.hypot(cm[2], cm[3])
    return x, y, font_size * scale


def _metadata_hints(reader: PdfReader) -> UnverifiedMetadataHints:
    try:
        info = reader.metadata
        title = info.title if info is not None else None
        author = info.author if info is not None else None
    except Exception:
        # A hint is optional; a damaged information dictionary costs the hint, not the text.
        return UnverifiedMetadataHints()
    return UnverifiedMetadataHints(
        title=(title.strip() or None) if title else None,
        authors=(author.strip(),) if author and author.strip() else (),
    )

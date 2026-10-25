"""The extraction model, the content-type decision and the dispatcher (v1-e04-t04 extracted-model, ac4)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Final

import pytest
from pydantic import ValidationError

from debate_core.retrieval.extraction import (
    ContentTypeDispatcher,
    DocumentKind,
    ExtractedContent,
    ExtractionError,
    ExtractionQuality,
    JoinDecision,
    LineJoin,
    UnsupportedContentType,
    document_kind,
)
from debate_core.retrieval.fetch_types import FetchResult

URL: Final = "https://example.org/article"
WHEN: Final = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
PDF_BYTES: Final = b"%PDF-1.7\n1 0 obj"
HTML_BYTES: Final = b"<!DOCTYPE html><html><body><p>Words.</p></body></html>"


def fetched(body: bytes, content_type: str | None) -> FetchResult:
    return FetchResult(
        requested_url=URL,
        final_url=URL,
        elapsed_ms=1.0,
        fetched_at=WHEN,
        body=body,
        content_type=content_type,
    )


# --------------------------------------------------------------------------------------------
# document_kind
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("body", "content_type", "expected"),
    [
        (HTML_BYTES, "text/html; charset=utf-8", DocumentKind.HTML),
        (HTML_BYTES, "TEXT/HTML", DocumentKind.HTML),
        (
            b"<?xml version='1.0'?><html xmlns='http://www.w3.org/1999/xhtml'>",
            "application/xhtml+xml",
            DocumentKind.HTML,
        ),
        (b"Words with no tag at the start.", "text/html", DocumentKind.HTML),
        (PDF_BYTES, "application/pdf", DocumentKind.PDF),
        (b"no signature", "application/x-pdf", DocumentKind.PDF),
        # The bytes decide over the label: a mislabelled PDF is a PDF, mislabelled HTML is HTML.
        (PDF_BYTES, "text/html", DocumentKind.PDF),
        (PDF_BYTES, "application/octet-stream", DocumentKind.PDF),
        (PDF_BYTES, None, DocumentKind.PDF),
        (HTML_BYTES, "text/plain", DocumentKind.HTML),
        (HTML_BYTES, None, DocumentKind.HTML),
    ],
)
def test_the_bytes_then_the_declared_type_choose_the_extractor(
    body: bytes, content_type: str | None, expected: DocumentKind
) -> None:
    assert document_kind(fetched(body, content_type)) is expected


@pytest.mark.parametrize(
    ("body", "content_type", "declared", "sniffed"),
    [
        (b"\x89PNG\r\n\x1a\n....", "image/png", "image/png", "image/png"),
        # An image served as HTML is still an image.
        (b"\x89PNG\r\n\x1a\n....", "text/html", "text/html", "image/png"),
        (b"PK\x03\x04docx", "application/pdf", "application/pdf", "application/zip"),
        (b"plain words", "text/plain", "text/plain", None),
        (b"plain words", "application/octet-stream", "application/octet-stream", None),
        (b"plain words", None, None, None),
        (b"", None, None, None),
        (b"<?xml version='1.0'?><rss>", "application/rss+xml", "application/rss+xml", "application/xml"),
    ],
)
def test_a_type_no_extractor_reads_is_refused_naming_both_types(
    body: bytes, content_type: str | None, declared: str | None, sniffed: str | None
) -> None:
    with pytest.raises(UnsupportedContentType) as refused:
        document_kind(fetched(body, content_type))
    assert (refused.value.declared, refused.value.sniffed) == (declared, sniffed)


def test_unsupported_content_type_is_an_extraction_error_and_the_ports_value_error() -> None:
    assert issubclass(UnsupportedContentType, ExtractionError)
    assert issubclass(UnsupportedContentType, ValueError)


# --------------------------------------------------------------------------------------------
# ContentTypeDispatcher
# --------------------------------------------------------------------------------------------


class RecordingExtractor:
    def __init__(self, name: str) -> None:
        self.name = name
        self.calls: list[FetchResult] = []

    def extract(self, fetched: FetchResult) -> ExtractedContent:
        self.calls.append(fetched)
        return content(paragraphs=(f"read by {self.name}",), extractor_name=self.name)


def test_the_dispatcher_hands_each_document_to_the_extractor_for_its_kind() -> None:
    html, pdf = RecordingExtractor("html"), RecordingExtractor("pdf")
    dispatcher = ContentTypeDispatcher(html=html, pdf=pdf)

    assert dispatcher.extract(fetched(PDF_BYTES, "text/html")).paragraphs == ("read by pdf",)
    assert dispatcher.extract(fetched(HTML_BYTES, "text/html")).paragraphs == ("read by html",)
    assert (len(html.calls), len(pdf.calls)) == (1, 1)


def test_the_dispatcher_refuses_an_unsupported_type_before_calling_either() -> None:
    html, pdf = RecordingExtractor("html"), RecordingExtractor("pdf")
    with pytest.raises(UnsupportedContentType):
        ContentTypeDispatcher(html=html, pdf=pdf).extract(fetched(b"\x89PNG\r\n\x1a\n", "image/png"))
    assert html.calls == pdf.calls == []


# --------------------------------------------------------------------------------------------
# ExtractedContent and LineJoin invariants
# --------------------------------------------------------------------------------------------


def content(**changes: Any) -> ExtractedContent:
    paragraphs = changes.pop("paragraphs", ("First paragraph.", "a well-intentioned plan"))
    fields: dict[str, Any] = {
        "paragraphs": paragraphs,
        "extractor_name": "test",
        "extractor_version": "test-1",
        "quality": ExtractionQuality(
            character_count=sum(len(paragraph) for paragraph in paragraphs), paragraph_count=len(paragraphs)
        ),
    }
    return ExtractedContent(**(fields | changes))


def join(**changes: Any) -> LineJoin:
    fields: dict[str, Any] = {
        "paragraph_index": 1,
        "offset": 6,
        "page_number": 1,
        "character": "-",
        "hyphen_kept": True,
        "decision": JoinDecision.UNDETERMINED,
    }
    return LineJoin(**(fields | changes))


def test_text_joins_paragraphs_with_a_blank_line() -> None:
    assert content().text == "First paragraph.\n\na well-intentioned plan"


def test_a_kept_join_must_point_at_its_character_in_its_paragraph() -> None:
    assert content(line_joins=(join(),)).line_joins[0].offset == 6
    with pytest.raises(ValidationError, match="not at offset 5"):
        content(line_joins=(join(offset=5),))
    with pytest.raises(ValidationError, match="not at offset 23"):
        content(line_joins=(join(offset=23),))


def test_a_join_must_name_a_paragraph_and_an_offset_inside_it() -> None:
    with pytest.raises(ValidationError, match="paragraph 2, which does not exist"):
        content(line_joins=(join(paragraph_index=2),))
    with pytest.raises(ValidationError, match="past its paragraph's end"):
        content(
            line_joins=(join(offset=24, hyphen_kept=False, decision=JoinDecision.JOINED_FORM_IN_DOCUMENT),)
        )


@pytest.mark.parametrize(
    ("decision", "character", "hyphen_kept"),
    [
        (JoinDecision.SOFT_HYPHEN, "­", False),
        (JoinDecision.JOINED_FORM_IN_DOCUMENT, "-", False),
        (JoinDecision.HYPHENATED_FORM_IN_DOCUMENT, "-", True),
        (JoinDecision.NOT_A_WORD_BREAK, "–", True),
        (JoinDecision.UNDETERMINED, "-", True),
    ],
)
def test_each_decision_keeps_or_drops_and_cannot_say_otherwise(
    decision: JoinDecision, character: str, hyphen_kept: bool
) -> None:
    assert join(decision=decision, character=character, hyphen_kept=hyphen_kept).hyphen_kept is hyphen_kept
    with pytest.raises(ValidationError, match=f"a {decision.value} join cannot have hyphen_kept"):
        join(decision=decision, character=character, hyphen_kept=not hyphen_kept)


def test_a_join_is_soft_hyphen_exactly_when_its_character_is_one() -> None:
    with pytest.raises(ValidationError, match="exactly when its character is U\\+00AD"):
        join(decision=JoinDecision.SOFT_HYPHEN, character="-", hyphen_kept=False)
    with pytest.raises(ValidationError, match="exactly when its character is U\\+00AD"):
        join(decision=JoinDecision.UNDETERMINED, character="­", hyphen_kept=True)


def test_quality_counts_must_describe_the_paragraphs() -> None:
    with pytest.raises(ValidationError, match="paragraph_count"):
        content(quality=ExtractionQuality(character_count=39, paragraph_count=1))
    with pytest.raises(ValidationError, match="character_count"):
        content(quality=ExtractionQuality(character_count=40, paragraph_count=2))


@pytest.mark.parametrize("paragraph", ["", "   ", " leading", "trailing\n"])
def test_a_paragraph_is_never_blank_or_padded_and_is_never_trimmed_for_you(paragraph: str) -> None:
    with pytest.raises(ValidationError, match="non-blank, with no whitespace at either end"):
        content(paragraphs=(paragraph,))

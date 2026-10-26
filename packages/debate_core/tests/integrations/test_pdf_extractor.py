"""The PDF extractor on the synthetic journal article, and every refusal (v1-e04-t04 ac3, ac4).

The sample is `tests/fixtures/extraction/journal-article.pdf`, written by the fixture builder with no
PDF library, and the expected paragraphs, joins and removed lines are the hand-written
`journal-article.expected.json`. The rules themselves are tested line by line in
`packages/debate_core/tests/retrieval/test_pdf_layout.py`; here the bytes go through pypdf.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final

import pypdf
import pytest
from tests.fixtures.extraction.build_pdf_fixtures import (
    JOURNAL_ARTICLE_FILE,
    journal_article_pdf,
    long_compressed_page_pdf,
    plain_pages_pdf,
)
from tests.fixtures.extraction.expected_output import join_mismatches, load_expected, removed_line_rows

from debate_core.integrations.pdf_extractor import LAYOUT_RULES_VERSION, PdfExtractor
from debate_core.retrieval.extraction import (
    DocumentTooLarge,
    EncryptedDocument,
    ExtractionError,
    TooManyPages,
    UnreadableDocument,
    UnsupportedContentType,
)
from debate_core.retrieval.fetch_types import FetchResult

URL: Final = "https://journal.example/articles/moral-hazard.pdf"
WHEN: Final = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)


def fetched(body: bytes, content_type: str | None = "application/pdf") -> FetchResult:
    return FetchResult(
        requested_url=URL,
        final_url=URL,
        elapsed_ms=1.0,
        fetched_at=WHEN,
        body=body,
        content_type=content_type,
    )


def test_the_committed_pdf_is_what_the_builder_writes() -> None:
    assert JOURNAL_ARTICLE_FILE.read_bytes() == journal_article_pdf()


def test_pdf_extractor_produces_the_hand_written_paragraphs_joins_and_removals() -> None:
    expected = load_expected("journal-article")
    extracted = PdfExtractor().extract(fetched(JOURNAL_ARTICLE_FILE.read_bytes()))

    assert list(extracted.paragraphs) == expected["paragraphs"]
    assert join_mismatches(extracted.paragraphs, extracted.line_joins, expected["line_joins"]) == []
    assert removed_line_rows(extracted.removed_lines) == expected["removed_lines"]


def test_pdf_extractor_names_itself_its_rules_and_pypdfs_version() -> None:
    extracted = PdfExtractor().extract(fetched(journal_article_pdf()))
    assert extracted.extractor_name == PdfExtractor().name == "pypdf"
    assert extracted.extractor_version == f"{LAYOUT_RULES_VERSION}+pypdf-{pypdf.__version__}"


def test_pdf_extractor_reports_its_quality_signals() -> None:
    extracted = PdfExtractor().extract(fetched(journal_article_pdf()))
    removed = sum(len(line.text) for line in extracted.removed_lines)
    assert extracted.quality.paragraph_count == 16
    assert extracted.quality.fallback_used is False
    assert extracted.quality.boilerplate_ratio is not None
    assert 0 < extracted.quality.boilerplate_ratio < 0.2
    # Two running headers (72 characters), three running footers (69) and three page numbers (11).
    assert removed == 2 * 72 + 3 * 69 + 3 * 11


def test_a_mislabelled_pdf_is_still_read_as_a_pdf() -> None:
    extracted = PdfExtractor().extract(
        fetched(journal_article_pdf(), content_type="application/octet-stream")
    )
    assert extracted.quality.paragraph_count == 16


def test_extracting_the_same_bytes_twice_gives_the_same_content() -> None:
    body = journal_article_pdf()
    assert PdfExtractor().extract(fetched(body)) == PdfExtractor().extract(fetched(body))


# --------------------------------------------------------------------------------------------
# Refusals: a typed error, never part of the text
# --------------------------------------------------------------------------------------------


def test_an_encrypted_pdf_is_refused_before_any_text_is_read() -> None:
    with pytest.raises(EncryptedDocument):
        PdfExtractor().extract(fetched(journal_article_pdf(encrypted=True)))


def test_a_pdf_over_the_byte_limit_is_refused_before_it_is_parsed() -> None:
    body = journal_article_pdf()
    assert PdfExtractor(max_bytes=len(body)).extract(fetched(body)).paragraphs
    with pytest.raises(DocumentTooLarge) as refused:
        PdfExtractor(max_bytes=len(body) - 1).extract(fetched(body))
    assert (refused.value.size_bytes, refused.value.limit_bytes) == (len(body), len(body) - 1)


def test_a_pdf_over_the_page_limit_is_refused() -> None:
    assert PdfExtractor(max_pages=5).extract(fetched(plain_pages_pdf(5))).text.count("Sentence") == 5
    with pytest.raises(TooManyPages) as refused:
        PdfExtractor(max_pages=5).extract(fetched(plain_pages_pdf(6)))
    assert (refused.value.page_count, refused.value.limit) == (6, 5)


def test_a_stream_that_expands_past_the_limit_is_refused() -> None:
    body = long_compressed_page_pdf()
    assert PdfExtractor().extract(fetched(body)).text.count("of a long page") == 50
    with pytest.raises(UnreadableDocument, match="expands past the 1000-byte limit"):
        PdfExtractor(max_stream_bytes=1000).extract(fetched(body))


def test_a_truncated_stream_is_refused_not_read_in_part() -> None:
    with pytest.raises(UnreadableDocument, match="PdfStreamError"):
        PdfExtractor().extract(fetched(long_compressed_page_pdf(keep_compressed_bytes=300)))


@pytest.mark.parametrize("body", [b"%PDF-1.4\nnot a pdf at all", b"%PDF-", journal_article_pdf()[:2000]])
def test_a_malformed_pdf_is_refused(body: bytes) -> None:
    with pytest.raises(UnreadableDocument):
        PdfExtractor().extract(fetched(body))


@pytest.mark.parametrize(
    ("body", "content_type"),
    [
        (b"<!DOCTYPE html><html><body><p>An article.</p></body></html>", "text/html"),
        (b"\x89PNG\r\n\x1a\n....", "image/png"),
        (b"plain words", "text/plain"),
    ],
)
def test_what_is_not_a_pdf_raises_unsupported_content_type(body: bytes, content_type: str) -> None:
    with pytest.raises(UnsupportedContentType):
        PdfExtractor().extract(fetched(body, content_type))


def test_every_refusal_is_an_extraction_error() -> None:
    for refusal in (
        EncryptedDocument,
        DocumentTooLarge,
        TooManyPages,
        UnreadableDocument,
        UnsupportedContentType,
    ):
        assert issubclass(refusal, ExtractionError)

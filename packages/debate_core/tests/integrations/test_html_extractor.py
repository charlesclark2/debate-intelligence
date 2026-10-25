"""The HTML extractor on synthetic news, think-tank and federal pages, its fallback and refusals (v1-e04-t04).

ac1: TrafilaturaExtractor returns the body paragraphs of each sample in
`tests/fixtures/extraction/`, matching the hand-written `<sample>.expected.json`, with navigation,
ads and comment sections excluded. ac2: below the configured minimum the fallback runs and
`fallback_used` is true. ac4: name, version and quality signals on every result, and
UnsupportedContentType for what is not HTML. Every sample is synthetic; nothing is fetched.
"""

from __future__ import annotations

from datetime import UTC, datetime
from importlib.metadata import version
from typing import Final

import pytest
from lxml import etree
from tests.fixtures.extraction.expected_output import load_expected, sample_bytes

from debate_core.integrations.html_extractor import HTML_RULES_VERSION, TrafilaturaExtractor
from debate_core.retrieval.extraction import (
    DocumentTooLarge,
    PaywallMarkerFound,
    UnreadableDocument,
    UnsupportedContentType,
    UnverifiedMetadataHints,
)
from debate_core.retrieval.fetch_types import FetchResult

WHEN: Final = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
SAMPLES: Final = ("news-article", "think-tank-report", "gov-press-release")


def fetched(
    body: bytes, content_type: str | None = "text/html; charset=utf-8", url: str = "https://site.example/a"
) -> FetchResult:
    return FetchResult(
        requested_url=url,
        final_url=url,
        elapsed_ms=1.0,
        fetched_at=WHEN,
        body=body,
        content_type=content_type,
    )


def sample(name: str) -> FetchResult:
    return fetched(sample_bytes(f"{name}.html"), url=load_expected(name)["final_url"])


def page(body: str, head: str = "") -> bytes:
    return f"<!DOCTYPE html><html><head>{head}</head><body>{body}</body></html>".encode()


ARTICLE: Final = "".join(
    f"<p>Paragraph {number} of an article about funding for habitat protection and species revival, "
    "long enough that an extractor treats it as body text rather than a caption.</p>"
    for number in range(1, 5)
)


# --------------------------------------------------------------------------------------------
# ac1: the golden samples
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", SAMPLES)
def test_trafilatura_extractor_returns_the_hand_written_paragraphs(name: str) -> None:
    extracted = TrafilaturaExtractor().extract(sample(name))
    assert list(extracted.paragraphs) == load_expected(name)["paragraphs"]
    assert extracted.extractor_name == "trafilatura"
    assert extracted.quality.fallback_used is False


@pytest.mark.parametrize("name", SAMPLES)
def test_trafilatura_extractor_leaves_out_navigation_ads_and_comments(name: str) -> None:
    text = TrafilaturaExtractor().extract(sample(name)).text
    assert [excluded for excluded in load_expected(name)["excluded"] if excluded in text] == []


@pytest.mark.parametrize("name", SAMPLES)
def test_trafilatura_extractor_reports_unverified_metadata_hints_as_the_page_states_them(name: str) -> None:
    hints = TrafilaturaExtractor().extract(sample(name)).metadata_hints
    assert isinstance(hints, UnverifiedMetadataHints)
    assert hints.model_dump(mode="json") == load_expected(name)["metadata_hints"]


@pytest.mark.parametrize("name", SAMPLES)
def test_every_extracted_paragraph_is_text_the_page_shows(name: str) -> None:
    # Not one word changes: each paragraph is, character for character, a stretch of the page's
    # visible text with its whitespace collapsed as a browser collapses it.
    source = etree.fromstring(sample_bytes(f"{name}.html"), etree.HTMLParser())
    for element in source.iter("script", "style"):
        element.text = ""
    shown = " ".join("".join(str(piece) for piece in source.itertext()).split())
    assert [
        paragraph
        for paragraph in TrafilaturaExtractor().extract(sample(name)).paragraphs
        if paragraph not in shown
    ] == []


def test_trafilatura_extractor_names_every_library_version_that_decides_the_text() -> None:
    assert TrafilaturaExtractor().extract(sample("news-article")).extractor_version == (
        f"{HTML_RULES_VERSION}+trafilatura-{version('trafilatura')}"
        f"+readability-lxml-{version('readability-lxml')}+lxml-{version('lxml')}"
    )
    assert TrafilaturaExtractor().name == "trafilatura"


def test_trafilatura_extractor_reports_quality_signals() -> None:
    extracted = TrafilaturaExtractor().extract(sample("news-article"))
    expected = load_expected("news-article")["paragraphs"]
    assert extracted.quality.paragraph_count == len(expected)
    assert extracted.quality.character_count == sum(len(paragraph) for paragraph in expected)
    assert extracted.quality.boilerplate_ratio is not None
    assert 0.2 < extracted.quality.boilerplate_ratio < 1


def test_extracting_the_same_page_twice_gives_the_same_content() -> None:
    assert TrafilaturaExtractor().extract(sample("think-tank-report")) == TrafilaturaExtractor().extract(
        sample("think-tank-report")
    )


# --------------------------------------------------------------------------------------------
# ac2: the fallback below the configured minimum
# --------------------------------------------------------------------------------------------


def primary_characters(name: str) -> int:
    return sum(len(paragraph) for paragraph in load_expected(name)["paragraphs"])


@pytest.mark.parametrize("name", SAMPLES)
def test_the_fallback_does_not_run_when_the_primary_reaches_the_minimum_exactly(name: str) -> None:
    extracted = TrafilaturaExtractor(minimum_characters=primary_characters(name)).extract(sample(name))
    assert (extracted.quality.fallback_used, extracted.extractor_name) == (False, "trafilatura")


@pytest.mark.parametrize("name", SAMPLES)
def test_the_fallback_runs_when_the_primary_is_one_character_short(name: str) -> None:
    extracted = TrafilaturaExtractor(minimum_characters=primary_characters(name) + 1).extract(sample(name))
    assert extracted.quality.fallback_used is True


def test_an_old_table_layout_that_trafilatura_cannot_read_is_recovered_by_the_fallback() -> None:
    sentences = [
        f"Habitat grants were announced for wetlands and forests, part {number}." for number in range(6)
    ]
    body = (
        "<table><tr><td><a href='/'>Home</a></td></tr><tr><td>"
        + "<br><br>".join(sentences)
        + "</td></tr></table>"
    )
    extracted = TrafilaturaExtractor().extract(fetched(page(body)))
    assert (extracted.quality.fallback_used, extracted.extractor_name) == (True, "readability-lxml")
    assert extracted.paragraphs == (" ".join(sentences),)


def test_the_fallbacks_text_is_kept_when_it_found_more() -> None:
    # readability keeps the news story's in-body ad, so it finds more; its text is used and named.
    extracted = TrafilaturaExtractor(minimum_characters=10_000).extract(sample("news-article"))
    assert (extracted.quality.fallback_used, extracted.extractor_name) == (True, "readability-lxml")
    assert extracted.paragraphs[:2] == tuple(load_expected("news-article")["paragraphs"][:2])


def test_the_primarys_text_is_kept_when_the_fallback_found_no_more() -> None:
    extracted = TrafilaturaExtractor(minimum_characters=10_000).extract(sample("gov-press-release"))
    assert (extracted.quality.fallback_used, extracted.extractor_name) == (True, "trafilatura")
    assert list(extracted.paragraphs) == load_expected("gov-press-release")["paragraphs"]


def test_a_page_with_no_text_is_an_empty_extraction_with_the_fallback_tried() -> None:
    extracted = TrafilaturaExtractor().extract(fetched(page("")))
    assert extracted.paragraphs == ()
    assert (extracted.quality.fallback_used, extracted.quality.character_count) == (True, 0)


# --------------------------------------------------------------------------------------------
# Words are never joined or changed
# --------------------------------------------------------------------------------------------


def test_a_line_break_inside_a_paragraph_never_joins_two_words() -> None:
    body = ARTICLE + "<p>Signed by the director<br>and the deputy director<br/>of the program.</p>"
    paragraphs = TrafilaturaExtractor().extract(fetched(page(body))).paragraphs
    assert "Signed by the director and the deputy director of the program." in paragraphs


def test_a_latin_1_label_is_read_as_windows_1252_so_curly_quotes_survive() -> None:
    body = page(ARTICLE + "<p>\u201cProtect it now,\u201d the report said, \u2014 before it is gone.</p>")
    encoded = body.decode().encode("cp1252")
    extracted = TrafilaturaExtractor().extract(fetched(encoded, "text/html; charset=ISO-8859-1"))
    assert "\u201cProtect it now,\u201d the report said, \u2014 before it is gone." in extracted.paragraphs


def test_the_pages_own_meta_charset_is_used_when_the_header_names_none() -> None:
    body = page(
        ARTICLE + "<p>Caf\u00e9 owners and na\u00efve plans.</p>", head='<meta charset="windows-1252">'
    )
    extracted = TrafilaturaExtractor().extract(fetched(body.decode().encode("cp1252"), "text/html"))
    assert "Caf\u00e9 owners and na\u00efve plans." in extracted.paragraphs


def test_a_utf_8_byte_order_mark_decides_the_encoding() -> None:
    body = b"\xef\xbb\xbf" + page(ARTICLE + "<p>Na\u00efve plans.</p>")
    assert (
        "Na\u00efve plans."
        in TrafilaturaExtractor().extract(fetched(body, "text/html; charset=iso-8859-1")).paragraphs
    )


def test_bytes_that_are_not_their_declared_encoding_are_refused_not_replaced() -> None:
    with pytest.raises(UnreadableDocument, match="not valid utf-8"):
        TrafilaturaExtractor().extract(fetched(page(ARTICLE).replace(b"Paragraph 2", b"Paragraph \xff")))


def test_an_unknown_encoding_is_refused() -> None:
    with pytest.raises(UnreadableDocument, match="unknown character encoding"):
        TrafilaturaExtractor().extract(fetched(page(ARTICLE), "text/html; charset=x-made-up"))


def test_an_xhtml_page_with_an_xml_declaration_is_read() -> None:
    body = b'<?xml version="1.0" encoding="utf-8"?>' + page(ARTICLE)
    assert len(TrafilaturaExtractor().extract(fetched(body, "application/xhtml+xml")).paragraphs) == 4


# --------------------------------------------------------------------------------------------
# Refusals
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "json_ld",
    [
        '{"@type": "NewsArticle", "isAccessibleForFree": false}',
        '{"@type": "NewsArticle", "isAccessibleForFree": "False"}',
        '{"@type": "NewsArticle", "hasPart": {"@type": "WebPageElement", "isAccessibleForFree": "false"}}',
        '{"@graph": [{"@type": "WebPage"}, {"@type": "Article", "isAccessibleForFree": false}]}',
        '[{"@type": "BreadcrumbList"}, {"@type": "Article", "isAccessibleForFree": false}]',
    ],
)
def test_a_page_declaring_itself_not_free_in_json_ld_is_refused(json_ld: str) -> None:
    head = f'<script type="application/ld+json">{json_ld}</script>'
    with pytest.raises(PaywallMarkerFound, match="in JSON-LD"):
        TrafilaturaExtractor().extract(fetched(page(ARTICLE, head)))


def test_a_page_declaring_itself_not_free_in_microdata_is_refused() -> None:
    body = f'<article itemscope><meta itemprop="isAccessibleForFree" content="False">{ARTICLE}</article>'
    with pytest.raises(PaywallMarkerFound, match="in microdata"):
        TrafilaturaExtractor().extract(fetched(page(body)))


@pytest.mark.parametrize(
    "head",
    [
        '<script type="application/ld+json">{"@type": "Article", "isAccessibleForFree": true}</script>',
        '<script type="application/ld+json">{"@type": "Article", "isAccessibleForFree": "True"}</script>',
        '<script type="application/ld+json">{not json, "isAccessibleForFree": false</script>',
        "",
    ],
)
def test_a_page_that_declares_nothing_or_free_access_is_extracted(head: str) -> None:
    assert len(TrafilaturaExtractor().extract(fetched(page(ARTICLE, head))).paragraphs) == 4


@pytest.mark.parametrize(
    ("body", "content_type"),
    [
        (b"%PDF-1.7\n1 0 obj", "application/pdf"),
        (b"%PDF-1.7\n1 0 obj", "text/html"),
        (b"\x89PNG\r\n\x1a\n....", "image/png"),
        (b"plain words", "text/plain"),
    ],
)
def test_what_is_not_html_raises_unsupported_content_type(body: bytes, content_type: str) -> None:
    with pytest.raises(UnsupportedContentType):
        TrafilaturaExtractor().extract(fetched(body, content_type))


def test_a_page_over_the_byte_limit_is_refused_before_it_is_parsed() -> None:
    body = page(ARTICLE)
    assert TrafilaturaExtractor(max_bytes=len(body)).extract(fetched(body)).paragraphs
    with pytest.raises(DocumentTooLarge):
        TrafilaturaExtractor(max_bytes=len(body) - 1).extract(fetched(body))

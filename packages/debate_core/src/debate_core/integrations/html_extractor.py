"""The HTML article extractor: trafilatura first, readability-lxml when it finds too little (v1-e04-t04).

:class:`TrafilaturaExtractor` implements the
:class:`~debate_core.application.ports.providers.ContentExtractor` port for web pages.

## How a page becomes paragraphs

1. **Refusals first.** A document that is not HTML raises
   :class:`~debate_core.retrieval.extraction.UnsupportedContentType`; more bytes than `max_bytes`
   raises :class:`~debate_core.retrieval.extraction.DocumentTooLarge`; a page whose schema.org markup
   says `isAccessibleForFree: false` raises
   :class:`~debate_core.retrieval.extraction.PaywallMarkerFound`. That is the one paywall marker read
   here, because it sits in the JSON-LD this extractor parses for hints anyway; the full list of
   markers, versioned, is the access classifier's (v1-e04-t03).
2. **Decoding without guessing.** The bytes are decoded strictly, by their byte-order mark, else the
   `Content-Type` charset, else the page's own `<meta charset>`, else UTF-8, with the WHATWG reading
   of `iso-8859-1` and `ascii` as windows-1252. A page that does not decode raises
   :class:`~debate_core.retrieval.extraction.UnreadableDocument`; no character is ever replaced.
3. **trafilatura** finds the main text, favouring precision, with its own fallbacks off (`fast`),
   comments, tables, images and links left out.
4. **readability-lxml** runs when trafilatura's text is shorter than `minimum_characters`. Its text
   is used when it is longer; either way `fallback_used` is true, and `extractor_name` says which
   library's text was kept.

Paragraphs are the leaf blocks of the chosen tree in document order (paragraphs, headings, list
items, quotations), with the page's `h1`, the title, left out: it is reported as the title hint.
Inside a paragraph, a line break and every run of whitespace become one space, as a browser renders
them; no other character is touched.

## Metadata hints

Raw strings as the page states them, unverified: the title from the article's JSON-LD `headline`
(or `name`), else `og:title`, else `<title>`; authors from its JSON-LD `author`, else
`<meta name="author">`; the date from `datePublished`, else `article:published_time`; the site from
`og:site_name`, else the JSON-LD publisher; and `rel=canonical` resolved against the final URL.
"""

from __future__ import annotations

import codecs
import json
import re
from collections.abc import Iterator
from importlib.metadata import version
from typing import Any, Final, cast
from urllib.parse import urljoin

import trafilatura
from lxml import etree
from readability import Document as ReadabilityDocument  # pyright: ignore[reportMissingTypeStubs]

from debate_core.retrieval.content_sniffing import sniff_content_type
from debate_core.retrieval.extraction import (
    DocumentKind,
    DocumentTooLarge,
    ExtractedContent,
    ExtractionQuality,
    PaywallMarkerFound,
    UnreadableDocument,
    UnsupportedContentType,
    UnverifiedMetadataHints,
    document_kind,
)
from debate_core.retrieval.fetch_types import FetchResult

__all__ = ["DEFAULT_MAX_BYTES", "DEFAULT_MINIMUM_CHARACTERS", "HTML_RULES_VERSION", "TrafilaturaExtractor"]

PRIMARY_NAME: Final = "trafilatura"
FALLBACK_NAME: Final = "readability-lxml"
HTML_RULES_VERSION: Final = "html-1"
"""Bumped whenever this module changes what text a page produces with the same libraries."""

DEFAULT_MINIMUM_CHARACTERS: Final = 250
"""trafilatura's own minimum extracted size; below it the fallback runs."""
DEFAULT_MAX_BYTES: Final = 10 * 1024 * 1024

_TRAFILATURA_BLOCKS: Final = frozenset(
    {"p", "head", "item", "quote", "code", "list", "table", "row", "cell", "div"}
)
_TRAFILATURA_TITLE: Final = "h1"
_HTML_BLOCKS: Final = frozenset(
    {
        "p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "ul", "ol", "dl", "dt", "dd", "blockquote", "pre",
        "figcaption", "div", "section", "article", "main", "header", "footer", "aside",
        "table", "tr", "td", "th",
    }
)  # fmt: skip
_LINE_BREAKS: Final = frozenset({"lb", "br"})
_NOT_TEXT: Final = frozenset({"script", "style", "noscript", "template"})

_ARTICLE_TYPES: Final = frozenset(
    {
        "Article", "NewsArticle", "AnalysisNewsArticle", "OpinionNewsArticle", "ReportageNewsArticle",
        "BlogPosting", "Report", "ScholarlyArticle", "TechArticle", "WebPage",
    }
)  # fmt: skip
_XML_DECLARATION: Final = re.compile(r"\A\s*<\?xml[^>]*\?>")
_META_CHARSET: Final = re.compile(rb"""<meta[^>]+charset\s*=\s*["']?\s*([A-Za-z0-9_.:-]+)""", re.IGNORECASE)
_HEADER_CHARSET: Final = re.compile(r"""charset\s*=\s*["']?([A-Za-z0-9_.:-]+)""", re.IGNORECASE)
_WINDOWS_1252_LABELS: Final = frozenset(
    {"iso-8859-1", "iso8859-1", "latin1", "latin-1", "l1", "us-ascii", "ascii", "windows-1252", "cp1252"}
)
_BOMS: Final = (
    (codecs.BOM_UTF8, "utf-8"),
    (codecs.BOM_UTF16_LE, "utf-16-le"),
    (codecs.BOM_UTF16_BE, "utf-16-be"),
)

#: One element of a parsed page. lxml publishes no non-underscored name for it (as in docx_parser).
type HtmlElement = etree._Element  # pyright: ignore[reportPrivateUsage]


class TrafilaturaExtractor:
    """Readable article text from a web page, with a readability-lxml fallback."""

    def __init__(
        self, *, minimum_characters: int = DEFAULT_MINIMUM_CHARACTERS, max_bytes: int = DEFAULT_MAX_BYTES
    ) -> None:
        self._minimum_characters = minimum_characters
        self._max_bytes = max_bytes

    @property
    def name(self) -> str:
        return PRIMARY_NAME

    @property
    def version(self) -> str:
        """This module's rules and every library that decides the text, each at its version."""
        return (
            f"{HTML_RULES_VERSION}+trafilatura-{version('trafilatura')}"
            f"+readability-lxml-{version('readability-lxml')}+lxml-{version('lxml')}"
        )

    def extract(self, fetched: FetchResult) -> ExtractedContent:
        if document_kind(fetched) is not DocumentKind.HTML:
            raise UnsupportedContentType(fetched.content_type, sniff_content_type(fetched.body))
        if len(fetched.body) > self._max_bytes:
            raise DocumentTooLarge(len(fetched.body), self._max_bytes)
        markup = _XML_DECLARATION.sub("", _decode(fetched))
        tree = _parse(markup)
        json_ld = list(_json_ld_nodes(tree))
        marker = _paywall_marker(tree, json_ld)
        if marker is not None:
            raise PaywallMarkerFound(marker)

        paragraphs, extractor_name = _primary_paragraphs(markup, fetched.final_url), PRIMARY_NAME
        fallback_used = _length(paragraphs) < self._minimum_characters
        if fallback_used:
            fallback = _fallback_paragraphs(markup, fetched.final_url)
            if _length(fallback) > _length(paragraphs):
                paragraphs, extractor_name = fallback, FALLBACK_NAME
        visible = _visible_characters(tree)
        return ExtractedContent(
            paragraphs=paragraphs,
            extractor_name=extractor_name,
            extractor_version=self.version,
            metadata_hints=_metadata_hints(tree, json_ld, fetched.final_url),
            quality=ExtractionQuality(
                character_count=_length(paragraphs),
                paragraph_count=len(paragraphs),
                fallback_used=fallback_used,
                boilerplate_ratio=max(0.0, 1 - _length(paragraphs) / visible) if visible else None,
            ),
        )


def _length(paragraphs: tuple[str, ...]) -> int:
    return sum(len(paragraph) for paragraph in paragraphs)


# --------------------------------------------------------------------------------------------
# Decoding and parsing
# --------------------------------------------------------------------------------------------


def _decode(fetched: FetchResult) -> str:
    body = fetched.body
    for bom, encoding in _BOMS:
        if body.startswith(bom):
            return _strict_decode(body[len(bom) :], encoding)
    declared = _HEADER_CHARSET.search(fetched.content_type or "")
    meta = _META_CHARSET.search(body[:2048])
    label = (declared[1] if declared else meta[1].decode("ascii") if meta else "utf-8").lower()
    return _strict_decode(body, "cp1252" if label in _WINDOWS_1252_LABELS else label)


def _strict_decode(body: bytes, encoding: str) -> str:
    try:
        return body.decode(encoding, errors="strict")
    except LookupError as error:
        raise UnreadableDocument(f"the page names an unknown character encoding ({encoding})") from error
    except UnicodeDecodeError as error:
        raise UnreadableDocument(f"the page is not valid {encoding}; no character is guessed") from error


def _parse(markup: str) -> HtmlElement:
    try:
        tree = etree.fromstring(markup, etree.HTMLParser()) if markup.strip() else None
    except (etree.LxmlError, ValueError) as error:
        raise UnreadableDocument(f"the page could not be parsed ({type(error).__name__})") from error
    # lxml answers None, not an error, for markup with no element in it at all.
    return tree if tree is not None else etree.fromstring("<html><body></body></html>", etree.HTMLParser())


# --------------------------------------------------------------------------------------------
# Paragraphs
# --------------------------------------------------------------------------------------------


def _primary_paragraphs(markup: str, url: str) -> tuple[str, ...]:
    document = trafilatura.bare_extraction(
        markup,
        url=url,
        fast=True,
        favor_precision=True,
        include_comments=False,
        include_tables=False,
        include_images=False,
        include_links=False,
        include_formatting=False,
        with_metadata=False,
    )
    body: object = getattr(document, "body", None)
    if not isinstance(body, etree._Element):  # pyright: ignore[reportPrivateUsage]
        return ()
    return tuple(
        text
        for block in _leaf_blocks(body, _TRAFILATURA_BLOCKS)
        if not (block.tag == "head" and block.get("rend") == _TRAFILATURA_TITLE)
        if (text := _rendered_text(block))
    )


def _fallback_paragraphs(markup: str, url: str) -> tuple[str, ...]:
    try:
        summary = cast(str, ReadabilityDocument(markup, url=url).summary(html_partial=True))  # pyright: ignore[reportUnknownMemberType]
    except Exception:
        # readability raises its own Unparseable, and lxml's errors, on a page with nothing to read.
        # Finding nothing is the answer then: the primary extractor's text stands.
        return ()
    fragment = _parse(f"<div>{summary}</div>")
    return tuple(
        text
        for block in _leaf_blocks(fragment, _HTML_BLOCKS)
        if _tag(block) != "h1"
        if (text := _rendered_text(block))
    )


def _tag(element: HtmlElement) -> str | None:
    """The element's tag name; None for a comment or processing instruction, whose `tag` is a function."""
    tag = cast(object, element.tag)  # the stubs say str; lxml gives a comment the Comment function
    return tag if isinstance(tag, str) else None


def _leaf_blocks(root: HtmlElement, blocks: frozenset[str]) -> Iterator[HtmlElement]:
    """The block elements under `root` that contain no other block, in document order."""
    for element in root.iter():
        if element is root or _tag(element) not in blocks:
            continue
        if not any(_tag(child) in blocks for child in element.iterdescendants()):
            yield element


def _rendered_text(element: HtmlElement) -> str:
    """The element's text as a browser shows it: a line break and any whitespace run are one space."""
    return " ".join("".join(_text_pieces(element)).split())


def _text_pieces(element: HtmlElement) -> Iterator[str]:
    if _tag(element) is None or _tag(element) in _NOT_TEXT:
        return
    if element.text:
        yield element.text
    for child in element:
        if _tag(child) in _LINE_BREAKS:
            yield " "
        else:
            yield from _text_pieces(child)
        if child.tail:
            yield child.tail


def _visible_characters(tree: HtmlElement) -> int:
    body = tree.find("body")
    return len(_rendered_text(body)) if body is not None else 0


# --------------------------------------------------------------------------------------------
# JSON-LD, the paywall marker and the metadata hints
# --------------------------------------------------------------------------------------------


def _json_ld_nodes(tree: HtmlElement) -> Iterator[dict[str, Any]]:
    """Every top-level JSON-LD node on the page, `@graph` members included; malformed blocks skipped."""
    for script in tree.iter("script"):
        if (script.get("type") or "").strip().lower() != "application/ld+json" or not script.text:
            continue
        try:
            parsed: object = json.loads(script.text)
        except ValueError:
            continue
        for node in cast(list[object], parsed) if isinstance(parsed, list) else [parsed]:
            if isinstance(node, dict):
                typed = cast(dict[str, Any], node)
                yield typed
                graph = typed.get("@graph")
                if isinstance(graph, list):
                    members = cast(list[object], graph)
                    yield from (
                        cast(dict[str, Any], member) for member in members if isinstance(member, dict)
                    )


def _paywall_marker(tree: HtmlElement, json_ld: list[dict[str, Any]]) -> str | None:
    if any(_says_not_free(node) for node in json_ld):
        return "isAccessibleForFree=false in JSON-LD"
    for meta in tree.iter("meta"):
        if (
            meta.get("itemprop") == "isAccessibleForFree"
            and (meta.get("content") or "").strip().lower() == "false"
        ):
            return "isAccessibleForFree=false in microdata"
    return None


def _says_not_free(value: object) -> bool:
    """Whether a JSON-LD value, at any depth (`hasPart` included), declares isAccessibleForFree false."""
    if isinstance(value, dict):
        node = cast(dict[str, Any], value)
        flag = node.get("isAccessibleForFree")
        if flag is False or (isinstance(flag, str) and flag.strip().lower() == "false"):
            return True
        return any(_says_not_free(child) for child in node.values())
    if isinstance(value, list):
        return any(_says_not_free(child) for child in cast(list[object], value))
    return False


def _metadata_hints(
    tree: HtmlElement, json_ld: list[dict[str, Any]], final_url: str
) -> UnverifiedMetadataHints:
    none: dict[str, Any] = {}
    article = next((node for node in json_ld if _ARTICLE_TYPES & _types(node)), none)
    title_element = tree.find(".//title")
    return UnverifiedMetadataHints(
        title=_first(
            _string(article.get("headline")),
            _string(article.get("name")),
            _meta(tree, "property", "og:title"),
            _rendered_text(title_element) if title_element is not None else None,
        ),
        authors=_names(article.get("author")) or tuple(filter(None, [_meta(tree, "name", "author")])),
        published_at=_first(
            _string(article.get("datePublished")), _meta(tree, "property", "article:published_time")
        ),
        site_name=_first(_meta(tree, "property", "og:site_name"), *_names(article.get("publisher"))),
        canonical_url=_canonical(tree, final_url),
    )


def _types(node: dict[str, Any]) -> set[str]:
    declared = node.get("@type")
    if isinstance(declared, str):
        return {declared}
    if isinstance(declared, list):
        return {item for item in cast(list[object], declared) if isinstance(item, str)}
    return set()


def _string(value: object) -> str | None:
    return (value.strip() or None) if isinstance(value, str) else None


def _first(*values: str | None) -> str | None:
    return next((value.strip() for value in values if value and value.strip()), None)


def _names(value: object) -> tuple[str, ...]:
    """Names from a JSON-LD person or organization, a list of them, or plain strings, in order."""
    items = cast(list[object], value) if isinstance(value, list) else [value]
    names: list[str] = []
    for item in items:
        name = _string(cast(dict[str, Any], item).get("name")) if isinstance(item, dict) else _string(item)
        if name is not None:
            names.append(name)
    return tuple(names)


def _meta(tree: HtmlElement, attribute: str, key: str) -> str | None:
    for meta in tree.iter("meta"):
        if (meta.get(attribute) or "").strip().lower() == key:
            return _string(meta.get("content"))
    return None


def _canonical(tree: HtmlElement, final_url: str) -> str | None:
    for link in tree.iter("link"):
        if "canonical" in (link.get("rel") or "").lower().split() and (link.get("href") or "").strip():
            return urljoin(final_url, (link.get("href") or "").strip())
    return None

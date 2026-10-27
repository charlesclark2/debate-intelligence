"""Cite fields as a stored page states them, each with where it was read (v1-e06-t01).

:func:`harvest_page` reads a snapshot's raw bytes, exactly as the publisher sent them, and returns
:class:`CitationCandidates`: for each cite field, every value the page states, tagged with its
:class:`~debate_core.domain.enums.CitationFieldSource` and the text it was read out of. It chooses
nothing. Which candidate becomes the cite, and whether it counts as verified, is
:class:`~debate_core.application.citation_service.CitationService`'s decision, by a fixed precedence.
Nothing here is guessed by a model, and nothing is fetched.

Candidates come in source order, JSON-LD, meta tags, OpenGraph, byline, retrieval, heuristic, and within one
source in the order of the lists below. The same value from the same source is listed once.

## The sources

* **JSON-LD** (`json_ld`): the page's article node, the first node typed as an article, report or
  blog post, else the first `WebPage` node. Title from `headline`, then `name`; authors from `author`
  (people or organizations, by `name`, or plain strings); publication from `isPartOf`, then
  `publisher`; date from `datePublished`; URL from `url`, then `mainEntityOfPage`; DOIs from
  `identifier` and `sameAs`. The nodes come from :func:`~debate_core.retrieval.json_ld.json_ld_nodes`,
  the walk the access classifier and the HTML extractor share.
* **Meta tags** (`meta_tag`), by `name` or `property`, in any case: title from `citation_title`,
  `dc.title`, `dcterms.title`; authors from `citation_author` (one author per tag), `dc.creator`,
  `dcterms.creator`, `author`, `article:author`; publication from `citation_journal_title`,
  `citation_conference_title`, `citation_publisher`, `dc.publisher`, `dcterms.publisher`; date from
  `citation_publication_date`, `citation_date`, `citation_online_date`, `article:published_time`,
  `dc.date`, `dcterms.date`, `dc.date.issued`, `dcterms.issued`, `date`; URL from the
  `<link rel="canonical">`, `citation_public_url`, `citation_abstract_html_url`; DOIs from
  `citation_doi`, `dc.identifier`, `dcterms.identifier`, `prism.doi`, `bepress_citation_doi`. The
  canonical link is not strictly a meta tag, but it is the same kind of statement: the page's own
  head declaring something about itself.
* **OpenGraph** (`opengraph`): `og:title`, `og:site_name` as the publication, `og:url`.
* **Byline** (`byline`): the first element classed `byline`, `byline-author`, `author`, `authors`,
  `author-name`, `article-author` or `contributor` that names anyone, else the `rel="author"` links,
  else the `itemprop="author"` elements. Names are its `itemprop="name"` parts, else its links, else
  its text with a leading "By" dropped, cut at the first comma, bar, middle dot or dash, and split on
  "and", "&" and ";". So "By Dana Whitfield, Science Correspondent" names Dana Whitfield and nothing
  else. The date is a `<time datetime>` inside that byline, or an `itemprop="datePublished"`. **Author
  credentials** come from an explicit author bio: an element classed `author-bio`, `author-bios`,
  `bio`, `about-author`, `about-the-author`, `contributor-bio` or `author-description`, whose
  paragraphs are kept verbatim when they name one of the page's authors in full.
* **Heuristic** (`heuristic`), never verified: the `<title>` element, which usually carries the
  site's name too, and a date in the URL's path (`/2026/03/14/` or `2026-03-14`, a whole date only).
* **Retrieval** (`retrieval`): the retrieved URL itself, canonicalized, as the URL of last resort. It
  is the platform's own record of where it retrieved the text, not a guess, so it is not a heuristic
  (`v1-e06-t02`); the citation service verifies it when the platform retrieved the text.

Credentials are read from the bio and from JSON-LD's `jobTitle` and `affiliation` of each author
(as "Name, job title, affiliation"; authors joined with "; "), and from nothing else: not a job
title after a byline, not a `description`, not `citation_author_institution` (ac3). Crossref's
affiliations are the third source; they reach the service through its DOI lookup, not this module.

## What is not read

A document that is not HTML (a PDF, a user's plain text) has no markup to read, so only
:func:`harvest_url` applies to it. Nor does a page whose bytes do not decode: by its byte-order mark,
else the `Content-Type` charset, else its `<meta charset>`, else UTF-8, strictly, with no character
guessed. DOIs are read from the metadata and the URLs, never from the body text, where a reference
list would name other works'.

The page is parsed with the standard library's `html.parser`, because lxml stays inside the
adapters (the import contracts in the workspace root).
"""

from __future__ import annotations

import codecs
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from html.parser import HTMLParser
from typing import Any, Final, cast
from urllib.parse import urljoin, urlsplit

from debate_core.domain.enums import CitationFieldSource
from debate_core.retrieval.canonical_url import InvalidUrlError, canonicalize_url
from debate_core.retrieval.content_sniffing import sniff_content_type
from debate_core.retrieval.identifiers import detect_identifiers
from debate_core.retrieval.json_ld import json_ld_nodes, json_ld_types

__all__ = [
    "CitationCandidates",
    "Harvested",
    "StatedDate",
    "harvest_page",
    "harvest_url",
    "parse_stated_date",
]

_JSON_LD: Final = CitationFieldSource.JSON_LD
_META_TAG: Final = CitationFieldSource.META_TAG
_OPENGRAPH: Final = CitationFieldSource.OPENGRAPH
_BYLINE: Final = CitationFieldSource.BYLINE
_HEURISTIC: Final = CitationFieldSource.HEURISTIC
_RETRIEVAL: Final = CitationFieldSource.RETRIEVAL


@dataclass(frozen=True, slots=True)
class Harvested[ValueT]:
    """One value for one cite field, the source it was read from, and the text it was read out of."""

    value: ValueT
    source: CitationFieldSource
    raw: str


@dataclass(frozen=True, slots=True)
class CitationCandidates:
    """Every value a page and its URL state for each cite field, in source order."""

    authors: tuple[Harvested[tuple[str, ...]], ...] = ()
    author_credentials: tuple[Harvested[str], ...] = ()
    title: tuple[Harvested[str], ...] = ()
    publication: tuple[Harvested[str], ...] = ()
    published_at: tuple[Harvested[datetime], ...] = ()
    canonical_url: tuple[Harvested[str], ...] = ()
    dois: tuple[str, ...] = ()
    """Bare lowercase DOIs the metadata and the URLs state, in order, once each."""


@dataclass(frozen=True, slots=True)
class StatedDate:
    """A publication date as a page states it: the instant in UTC, and the calendar day it names.

    The two differ for a time late in the day west of UTC: "2026-09-14T22:30:00-04:00" is 02:30 UTC
    on the 15th, but the page names the 14th, and the 14th is what a cite should print.
    """

    moment: datetime
    calendar_date: date


# --------------------------------------------------------------------------------------------
# Dates
# --------------------------------------------------------------------------------------------

_MONTHS: Final = {
    name: number
    for number, names in enumerate(
        (
            ("january", "jan"), ("february", "feb"), ("march", "mar"), ("april", "apr"), ("may",),
            ("june", "jun"), ("july", "jul"), ("august", "aug"), ("september", "sep", "sept"),
            ("october", "oct"), ("november", "nov"), ("december", "dec"),
        ),
        start=1,
    )
    for name in names
}  # fmt: skip
_ISO_DATE: Final = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_ISO_DATETIME: Final = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}.*")
_SLASHED_DATE: Final = re.compile(r"(\d{4})/(\d{1,2})/(\d{1,2})")
_MONTH_DAY_YEAR: Final = re.compile(r"([A-Za-z]+)\.?\s+(\d{1,2}),?\s+(\d{4})")
_DAY_MONTH_YEAR: Final = re.compile(r"(\d{1,2})\s+([A-Za-z]+)\.?,?\s+(\d{4})")
_URL_PATH_DATE: Final = re.compile(r"(?:^|/)(\d{4})[/-](\d{2})[/-](\d{2})(?=$|[/-])")


def parse_stated_date(text: str) -> StatedDate | None:
    """The date `text` states, or `None` when it states no whole date.

    Accepts an ISO 8601 date or date-time (with an offset, `Z`, or none, when only its day is kept),
    `YYYY/MM/DD`, and a month written out or abbreviated ("March 3, 2026", "Sept. 14, 2026",
    "3 March 2026"). A year or a month alone is no date: it would need a day the page never stated.
    Nor is an all-number date with the day first or the month first, which cannot be told apart.
    """
    stripped = text.strip()
    if _ISO_DATETIME.fullmatch(stripped):
        try:
            stated = datetime.fromisoformat(stripped)
        except ValueError:
            return None
        if stated.tzinfo is None:
            return _whole_day(stated.date())
        return StatedDate(stated.astimezone(UTC), stated.date())
    if match := _ISO_DATE.fullmatch(stripped) or _SLASHED_DATE.fullmatch(stripped):
        return _day(int(match[1]), int(match[2]), int(match[3]))
    if match := _MONTH_DAY_YEAR.fullmatch(stripped):
        month = _MONTHS.get(match[1].lower())
        return None if month is None else _day(int(match[3]), month, int(match[2]))
    if match := _DAY_MONTH_YEAR.fullmatch(stripped):
        month = _MONTHS.get(match[2].lower())
        return None if month is None else _day(int(match[3]), month, int(match[1]))
    return None


def _day(year: int, month: int, day: int) -> StatedDate | None:
    try:
        return _whole_day(date(year, month, day))
    except ValueError:
        return None


def _whole_day(day: date) -> StatedDate:
    return StatedDate(datetime(day.year, day.month, day.day, tzinfo=UTC), day)


# --------------------------------------------------------------------------------------------
# The URL alone
# --------------------------------------------------------------------------------------------


def harvest_url(retrieved_url: str) -> CitationCandidates:
    """What the retrieved URL alone suggests: itself as the URL, a date in its path, its DOIs."""
    return _with_url_heuristics(CitationCandidates(), retrieved_url, ())


def _with_url_heuristics(
    found: CitationCandidates, retrieved_url: str, title_element: tuple[Harvested[str], ...]
) -> CitationCandidates:
    stated_urls = [retrieved_url, *(candidate.value for candidate in found.canonical_url)]
    path_dates = (_path_date(url) for url in stated_urls)
    return replace(
        found,
        title=_once((*found.title, *title_element)),
        published_at=_once((*found.published_at, *(stated for stated in path_dates if stated is not None))),
        canonical_url=_once(
            (*found.canonical_url, Harvested(_canonical(retrieved_url), _RETRIEVAL, retrieved_url))
        ),
        dois=tuple(dict.fromkeys((*found.dois, *detect_identifiers(retrieved_url).dois))),
    )


def _path_date(url: str) -> Harvested[datetime] | None:
    match = _URL_PATH_DATE.search(urlsplit(url).path)
    stated = _day(int(match[1]), int(match[2]), int(match[3])) if match else None
    return (
        None
        if stated is None or match is None
        else Harvested(stated.moment, _HEURISTIC, match[0].lstrip("/"))
    )


def _canonical(url: str) -> str:
    try:
        return canonicalize_url(url)
    except InvalidUrlError:
        return url


# --------------------------------------------------------------------------------------------
# The page
# --------------------------------------------------------------------------------------------


def harvest_page(raw: bytes, *, content_type: str | None, retrieved_url: str) -> CitationCandidates:
    """Every cite value the page in `raw`, retrieved from `retrieved_url`, states; see the module docstring.

    A document that is not HTML, or that does not decode, yields what :func:`harvest_url` does.
    """
    markup = _decode(raw, content_type) if _is_html(raw, content_type) else None
    if markup is None:
        return harvest_url(retrieved_url)
    page = _Page(markup, retrieved_url)
    json_ld = page.json_ld()
    meta = page.meta_tags()
    opengraph = page.opengraph()
    byline = page.byline()
    found = CitationCandidates(
        authors=_once((*json_ld.authors, *meta.authors, *byline.authors)),
        title=_once((*json_ld.title, *meta.title, *opengraph.title)),
        publication=_once((*json_ld.publication, *meta.publication, *opengraph.publication)),
        published_at=_once((*json_ld.published_at, *meta.published_at, *byline.published_at)),
        canonical_url=_once((*json_ld.canonical_url, *meta.canonical_url, *opengraph.canonical_url)),
        dois=tuple(dict.fromkeys((*meta.dois, *json_ld.dois))),
    )
    names = {name for candidate in found.authors for name in candidate.value}
    found = replace(found, author_credentials=_once((*json_ld.author_credentials, *page.bios(names))))
    return _with_url_heuristics(found, retrieved_url, page.title_element())


def _once[ValueT](candidates: Iterable[Harvested[ValueT]]) -> tuple[Harvested[ValueT], ...]:
    """`candidates` in order, each value listed once per source."""
    seen: set[tuple[object, CitationFieldSource]] = set()
    kept: list[Harvested[ValueT]] = []
    for candidate in candidates:
        key = (candidate.value, candidate.source)
        if key not in seen:
            seen.add(key)
            kept.append(candidate)
    return tuple(kept)


# Decoding --------------------------------------------------------------------------------------

_HTML_TYPES: Final = frozenset({"text/html", "application/xhtml+xml"})
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


def _is_html(raw: bytes, content_type: str | None) -> bool:
    """HTML by the bytes' own signature, or by the declared type when the bytes have no opinion."""
    sniffed = sniff_content_type(raw)
    declared = (content_type or "").split(";", 1)[0].strip().lower()
    return sniffed == "text/html" or (sniffed in (None, "application/xml") and declared in _HTML_TYPES)


def _decode(raw: bytes, content_type: str | None) -> str | None:
    for bom, encoding in _BOMS:
        if raw.startswith(bom):
            return _strict(raw[len(bom) :], encoding)
    declared = _HEADER_CHARSET.search(content_type or "")
    meta = _META_CHARSET.search(raw[:2048])
    label = (declared[1] if declared else meta[1].decode("ascii") if meta else "utf-8").lower()
    return _strict(raw, "cp1252" if label in _WINDOWS_1252_LABELS else label)


def _strict(raw: bytes, encoding: str) -> str | None:
    try:
        return raw.decode(encoding, errors="strict")
    except (LookupError, UnicodeDecodeError):
        return None


# The parsed page -----------------------------------------------------------------------------

_VOID: Final = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)
_NOT_TEXT: Final = frozenset({"script", "style", "noscript", "template"})


@dataclass(eq=False)
class _Element:
    tag: str
    attributes: dict[str, str]
    children: list[_Element | str] = field(default_factory=list["_Element | str"])

    def get(self, name: str) -> str:
        return self.attributes.get(name, "").strip()

    @property
    def tokens(self) -> frozenset[str]:
        """Its class tokens and its id, lower-cased."""
        return frozenset([*self.get("class").lower().split(), *self.get("id").lower().split()])

    def iter(self) -> Iterator[_Element]:
        """This element and every element under it, in document order."""
        yield self
        for child in self.children:
            if isinstance(child, _Element):
                yield from child.iter()

    def text(self, *, leaving_out: frozenset[str] = frozenset()) -> str:
        """Its text as a browser shows it, every whitespace run one space."""
        return " ".join("".join(self._pieces(leaving_out)).split())

    def raw_text(self) -> str:
        """Its own text, unrendered: a script's source."""
        return "".join(child for child in self.children if isinstance(child, str))

    def _pieces(self, leaving_out: frozenset[str]) -> Iterator[str]:
        for child in self.children:
            if isinstance(child, str):
                yield child
            elif child.tag not in _NOT_TEXT and child.tag not in leaving_out:
                yield " " if child.tag == "br" else ""
                yield from child._pieces(leaving_out)


class _TreeBuilder(HTMLParser):
    """A forgiving element tree: an end tag closes up to its own start, a stray one is ignored."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Element("#document", {})
        self._open: list[_Element] = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        element = _Element(tag, {name: value or "" for name, value in attrs})
        self._open[-1].children.append(element)
        if tag not in _VOID:
            self._open.append(element)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._open[-1].children.append(_Element(tag, {name: value or "" for name, value in attrs}))

    def handle_endtag(self, tag: str) -> None:
        for depth in range(len(self._open) - 1, 0, -1):
            if self._open[depth].tag == tag:
                del self._open[depth:]
                return

    def handle_data(self, data: str) -> None:
        self._open[-1].children.append(data)


@dataclass(frozen=True, slots=True)
class _FromOneSource:
    authors: tuple[Harvested[tuple[str, ...]], ...] = ()
    author_credentials: tuple[Harvested[str], ...] = ()
    title: tuple[Harvested[str], ...] = ()
    publication: tuple[Harvested[str], ...] = ()
    published_at: tuple[Harvested[datetime], ...] = ()
    canonical_url: tuple[Harvested[str], ...] = ()
    dois: tuple[str, ...] = ()


_ARTICLE_TYPES: Final = frozenset(
    {
        "Article", "NewsArticle", "AnalysisNewsArticle", "OpinionNewsArticle", "ReportageNewsArticle",
        "BlogPosting", "Report", "ScholarlyArticle", "TechArticle",
    }
)  # fmt: skip
_WEB_PAGE: Final = "WebPage"

_META_TITLE: Final = ("citation_title", "dc.title", "dcterms.title")
_META_AUTHORS_ONE_PER_TAG: Final = (
    "citation_author",
    "dc.creator",
    "dcterms.creator",
    "author",
    "article:author",
)
_META_PUBLICATION: Final = (
    "citation_journal_title", "citation_conference_title", "citation_publisher",
    "dc.publisher", "dcterms.publisher",
)  # fmt: skip
_META_DATE: Final = (
    "citation_publication_date", "citation_date", "citation_online_date", "article:published_time",
    "dc.date", "dcterms.date", "dc.date.issued", "dcterms.issued", "date",
)  # fmt: skip
_META_URL: Final = ("citation_public_url", "citation_abstract_html_url")
_META_DOI: Final = (
    "citation_doi",
    "dc.identifier",
    "dcterms.identifier",
    "prism.doi",
    "bepress_citation_doi",
)

_BYLINE_TOKENS: Final = frozenset(
    {"byline", "byline-author", "author", "authors", "author-name", "article-author", "contributor"}
)
_BIO_TOKENS: Final = frozenset(
    {
        "author-bio",
        "author-bios",
        "bio",
        "about-author",
        "about-the-author",
        "contributor-bio",
        "author-description",
    }
)
_HEADINGS: Final = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
_BY: Final = re.compile(r"^(?:(?:written|story|report|reporting)\s+)?by\b[\s:]*", re.IGNORECASE)
_BYLINE_END: Final = re.compile(r"\s*(?:,|\||·|•|—|–|\s-\s)")
_NAME_SEPARATOR: Final = re.compile(r"\s+(?:and|&)\s+|\s*;\s*", re.IGNORECASE)


class _Page:
    """One parsed page and the readings of it each source makes."""

    def __init__(self, markup: str, retrieved_url: str) -> None:
        builder = _TreeBuilder()
        builder.feed(markup)
        builder.close()
        self._elements = list(builder.root.iter())
        self._url = retrieved_url
        self._meta = self._read_meta()

    def _read_meta(self) -> dict[str, list[str]]:
        meta: dict[str, list[str]] = {}
        for element in self._elements:
            if element.tag != "meta" or not element.get("content"):
                continue
            for attribute in ("name", "property"):
                if key := element.get(attribute).lower():
                    meta.setdefault(key, []).append(element.get("content"))
        return meta

    def _first_meta(self, key: str) -> str | None:
        values = self._meta.get(key)
        return values[0] if values else None

    # JSON-LD ------------------------------------------------------------------------------------

    def json_ld(self) -> _FromOneSource:
        blocks = (
            element.raw_text()
            for element in self._elements
            if element.tag == "script" and element.get("type").lower() == "application/ld+json"
        )
        nodes = list(json_ld_nodes(blocks))
        node = next((node for node in nodes if _ARTICLE_TYPES & json_ld_types(node)), None) or next(
            (node for node in nodes if _WEB_PAGE in json_ld_types(node)), None
        )
        if node is None:
            return _FromOneSource()
        authors = _json_ld_names(node.get("author"))
        return _FromOneSource(
            title=_texts(_JSON_LD, node.get("headline"), node.get("name")),
            authors=(Harvested(authors, _JSON_LD, ", ".join(authors)),) if authors else (),
            author_credentials=_json_ld_credentials(node.get("author")),
            publication=_texts(_JSON_LD, *_json_ld_first_names(node.get("isPartOf"), node.get("publisher"))),
            published_at=_dates(_JSON_LD, node.get("datePublished")),
            canonical_url=self._urls(_JSON_LD, node.get("url"), _id_of(node.get("mainEntityOfPage"))),
            dois=_dois(_json_ld_strings(node.get("identifier")), _json_ld_strings(node.get("sameAs"))),
        )

    # Meta tags and OpenGraph ----------------------------------------------------------------------

    def meta_tags(self) -> _FromOneSource:
        authors = (
            names
            for key in _META_AUTHORS_ONE_PER_TAG
            if (names := tuple(name for value in self._meta.get(key, []) if (name := _as_name(value))))
        )
        return _FromOneSource(
            title=_texts(_META_TAG, *map(self._first_meta, _META_TITLE)),
            authors=tuple(Harvested(names, _META_TAG, ", ".join(names)) for names in authors),
            publication=_texts(_META_TAG, *map(self._first_meta, _META_PUBLICATION)),
            published_at=_dates(_META_TAG, *map(self._first_meta, _META_DATE)),
            canonical_url=self._urls(_META_TAG, self._canonical_link(), *map(self._first_meta, _META_URL)),
            dois=_dois(*(self._meta.get(key, []) for key in _META_DOI)),
        )

    def opengraph(self) -> _FromOneSource:
        return _FromOneSource(
            title=_texts(_OPENGRAPH, self._first_meta("og:title")),
            publication=_texts(_OPENGRAPH, self._first_meta("og:site_name")),
            canonical_url=self._urls(_OPENGRAPH, self._first_meta("og:url")),
        )

    def _canonical_link(self) -> str | None:
        for element in self._elements:
            if (
                element.tag == "link"
                and "canonical" in element.get("rel").lower().split()
                and element.get("href")
            ):
                return element.get("href")
        return None

    def _urls(self, source: CitationFieldSource, *stated: object) -> tuple[Harvested[str], ...]:
        found: list[Harvested[str]] = []
        for value in stated:
            if isinstance(value, str) and value.strip():
                resolved = urljoin(self._url, value.strip())
                parts = urlsplit(resolved)
                if (
                    parts.scheme in ("http", "https")
                    and parts.netloc
                    and not any(c.isspace() for c in resolved)
                ):
                    found.append(Harvested(resolved, source, value.strip()))
        return tuple(found)

    def title_element(self) -> tuple[Harvested[str], ...]:
        title = next((element for element in self._elements if element.tag == "title"), None)
        text = title.text() if title is not None else ""
        return (Harvested(text, _HEURISTIC, text),) if text else ()

    # Byline and bios ----------------------------------------------------------------------------------

    def byline(self) -> _FromOneSource:
        bylines = [element for element in self._elements if element.tokens & _BYLINE_TOKENS]
        names = next((names for element in bylines if (names := _byline_names(element))), ())
        if not names:
            names = _distinct_names(
                e.text() for e in self._elements if e.tag == "a" and "author" in e.get("rel").lower().split()
            )
        if not names:
            names = _distinct_names(
                _itemprop_name(e) for e in self._elements if e.get("itemprop") == "author"
            )
        times = [
            e.get("datetime") or e.get("content")
            for e in self._elements
            if (e.tag == "time" and any(e in byline.iter() for byline in bylines))
            or e.get("itemprop") == "datePublished"
        ]
        return _FromOneSource(
            authors=(Harvested(names, _BYLINE, ", ".join(names)),) if names else (),
            published_at=_dates(_BYLINE, *times)[:1],
        )

    def bios(self, author_names: set[str]) -> tuple[Harvested[str], ...]:
        """The first author bio's paragraphs that name one of `author_names`, verbatim."""
        for element in self._elements:
            if not element.tokens & _BIO_TOKENS:
                continue
            paragraphs = [e.text() for e in element.iter() if e.tag == "p"] or [
                element.text(leaving_out=_HEADINGS)
            ]
            naming = [text for text in paragraphs if any(_names_in(name, text) for name in author_names)]
            if naming:
                bio = " ".join(naming)
                return (Harvested(bio, _BYLINE, bio),)
        return ()


def _names_in(name: str, text: str) -> bool:
    """Whether `text` names `name` in full, as whole words."""
    return re.search(rf"(?<!\w){re.escape(name)}(?!\w)", text) is not None


# Reading values ------------------------------------------------------------------------------------


def _texts(source: CitationFieldSource, *values: object) -> tuple[Harvested[str], ...]:
    stripped = (" ".join(value.split()) for value in values if isinstance(value, str))
    return tuple(Harvested(text, source, text) for text in stripped if text)


def _dates(source: CitationFieldSource, *values: object) -> tuple[Harvested[datetime], ...]:
    found: list[Harvested[datetime]] = []
    for value in values:
        if isinstance(value, str) and (stated := parse_stated_date(value)) is not None:
            found.append(Harvested(stated.moment, source, value.strip()))
    return tuple(found)


def _dois(*groups: Iterable[str]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(doi for group in groups for value in group for doi in detect_identifiers(value).dois)
    )


def _as_name(value: str) -> str | None:
    """`value` as an author's name, or `None` when it is not one: a URL, an address, a number."""
    name = " ".join(_BY.sub("", value).split())
    if not name or len(name) > 100 or "@" in name or "://" in name or name.startswith("www."):
        return None
    if not any(character.isalpha() for character in name) or any(character.isdigit() for character in name):
        return None
    return name


def _distinct_names(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(name for value in values if (name := _as_name(value))))


def _byline_names(byline: _Element) -> tuple[str, ...]:
    parts = [e for e in byline.iter() if e.get("itemprop") == "name"] or [
        e for e in byline.iter() if e.tag == "a"
    ]
    if parts:
        return _distinct_names(part.text() for part in parts)
    text = _BY.sub("", byline.text(leaving_out=frozenset({"time"})))
    return _distinct_names(_NAME_SEPARATOR.split(_BYLINE_END.split(text, maxsplit=1)[0]))


def _itemprop_name(element: _Element) -> str:
    named = next((e for e in element.iter() if e is not element and e.get("itemprop") == "name"), None)
    return (named or element).get("content") or (named or element).text()


def _mapping(value: object) -> dict[str, Any] | None:
    return cast(dict[str, Any], value) if isinstance(value, dict) else None


def _listed(value: object) -> list[object]:
    return cast(list[object], value) if isinstance(value, list) else [value]


def _json_ld_names(value: object) -> tuple[str, ...]:
    """Names from a JSON-LD person or organization, a list of them, or plain strings, in order."""
    names = (
        mapping.get("name") if (mapping := _mapping(item)) is not None else item for item in _listed(value)
    )
    return _distinct_names(name for name in names if isinstance(name, str))


def _json_ld_first_names(*values: object) -> Iterator[str]:
    """The name of each of `values` (an organization or periodical, or a list of them), in order."""
    for value in values:
        names = _json_ld_names(value)
        if names:
            yield names[0]


def _json_ld_credentials(authors: object) -> tuple[Harvested[str], ...]:
    """'Name, job title, affiliation' for each JSON-LD author that states either, joined by '; '."""
    stated: list[str] = []
    for item in _listed(authors):
        author = _mapping(item)
        name = (
            _as_name(author.get("name", ""))
            if author is not None and isinstance(author.get("name"), str)
            else None
        )
        if author is None or name is None:
            continue
        job_title = _texts(_JSON_LD, author.get("jobTitle"))
        affiliations = [
            mapping.get("name") if (mapping := _mapping(entry)) is not None else entry
            for entry in _listed(author.get("affiliation"))
        ]
        parts = [
            *(candidate.value for candidate in job_title),
            *(c.value for c in _texts(_JSON_LD, *affiliations)),
        ]
        if parts:
            stated.append(", ".join((name, *parts)))
    credentials = "; ".join(stated)
    return (Harvested(credentials, _JSON_LD, credentials),) if credentials else ()


def _json_ld_strings(value: object) -> list[str]:
    """Strings in a JSON-LD `identifier` or `sameAs`: plain, a PropertyValue's `value`, or a list."""
    found: list[str] = []
    for item in _listed(value):
        mapping = _mapping(item)
        inner = mapping.get("value") if mapping is not None else item
        if isinstance(inner, str):
            found.append(inner)
    return found


def _id_of(value: object) -> object:
    mapping = _mapping(value)
    return value if mapping is None else mapping.get("@id") or mapping.get("url")

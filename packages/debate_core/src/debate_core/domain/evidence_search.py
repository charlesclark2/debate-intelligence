"""The student search pilot's queries, filters, pages and results, pure over the index (`v1-e39-t03`).

`v1-e39-t02` builds the index: one SQLite FTS5 document per card cluster, its tag, cite, read-aloud
text and evidence text searchable, everything else stored (`docs/data/search-index.md`). This module
says what a student may ask of it and what comes back. The SQLite statements that ask are
:class:`~debate_core.integrations.local.search_index_reader.SqliteSearchIndexReader`'s, and
:class:`~debate_core.application.evidence_search.EvidenceSearchService` puts the two together.

## A query is parsed, never handed to MATCH

FTS5's query language has operators (`AND`, `OR`, `NOT`, `NEAR`), prefixes (`*`), column filters
(`text:`, `{tag cite}:`), initial-token anchors (`^`), parentheses and quoting, and a string that
misuses any of them is a syntax error. A student's words never reach it as written. :func:`parse_query`
reads four things and nothing else:

* a word, any run of characters up to a space;
* a `"quoted phrase"`, up to the next double quote or the end of the query;
* a leading minus, which excludes the word or phrase after it;
* an `author:` or `tag:` prefix (in any case), which limits the word or phrase after it to the cite
  or to the tag. `author:` means the card's author, which is written in its cite, never a debater.

Everything else is literal text: `NEAR(a b)`, `grow*`, `school:Riverbend`, `(` and `AND` are words
like any other. :meth:`ParsedQuery.fts5_expression` writes each term as an FTS5 string, with its
double quotes doubled, so the tokenizer reads it as a phrase of its words; the only operators and
column names in the expression are the ones this module writes. A term with no letter or digit in
it (`-`, `***`) is dropped, because FTS5 reads an empty phrase as matching nothing and would empty
the whole query. Control characters and lone surrogates are dropped before any of this: SQLite stops
reading an FTS5 string at a NUL.

## Nobody is searchable

The index keeps school, team code, tournament and round in its `occurrences` table, which no FTS5
table covers, and this module has no way to ask for them: there is no `school:` or `team:` prefix,
and a word that looks like one is literal text matched against the four searchable columns only
(the data-use policy's E39 gate item 8; the task's forbidden "search by school, team code or
debater").

## Filters, pages and cursors

:class:`SearchFilters` narrows by event, caselist or camp, side and first seen on or after a date. A
camp (`openev`) document has no first or last seen, so a first-seen filter leaves every camp card out,
and the page carries :attr:`SearchNotice.FIRST_SEEN_CASELIST_CARDS_ONLY` so the search page can say so
(PM amendment 2026-10-20, `v1-e39-t02` follow-up 2).

Results come :data:`SEARCH_PAGE_SIZE` to a page. A page's cursor is an offset into that query's
ranking and the first 128 bits of :func:`search_binding`, a digest of the index id, the parsed query
and the filters, so a cursor from another query, other filters or another index is refused. It needs
no secret: anyone can compute a binding, but a cursor so made only pages through the results of the
query it is bound to, which its holder could ask for directly.

## Ranking

BM25 over the four searchable columns, weighted by :data:`RANKING_WEIGHTS`: the one place the weights
live. The session report of `v1-e39-t03` justifies them on a small synthetic relevance set, which
`test_evidence_search_ranking.py` holds.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import unicodedata
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Final, Self

from pydantic import Field, model_validator

from debate_core.domain.base import DomainModel
from debate_core.domain.caselist import Event, Side
from debate_core.domain.file_recipe import CAMP_STORE, StoreName
from debate_core.domain.search_index import IndexedFontSizeSpan, IndexedFormattingSpan
from debate_core.domain.style_profile import RunEmphasis

__all__ = [
    "MAX_CURSOR_OFFSET",
    "MAX_QUERY_CHARACTERS",
    "MAX_QUERY_TERMS",
    "RANKING_WEIGHTS",
    "SEARCH_PAGE_SIZE",
    "SNIPPET_CLOSE",
    "SNIPPET_ELLIPSIS",
    "SNIPPET_OPEN",
    "SNIPPET_TOKENS",
    "Card",
    "CardRun",
    "InvalidSearchCursor",
    "OccurrenceProvenance",
    "ParsedQuery",
    "QueryTerm",
    "RankingWeights",
    "SearchField",
    "SearchFilters",
    "SearchHit",
    "SearchNotice",
    "SearchPage",
    "SnippetSegment",
    "card_runs",
    "decode_search_cursor",
    "encode_search_cursor",
    "occurrence_provenance_line",
    "parse_query",
    "search_binding",
    "snippet_segments",
]

SEARCH_PAGE_SIZE: Final = 20
"""Results on one page."""

MAX_QUERY_CHARACTERS: Final = 512
"""A query is read up to this many characters; the rest is ignored, and the page says so."""

MAX_QUERY_TERMS: Final = 32
"""A query keeps this many words and phrases; the rest are ignored, and the page says so."""

MAX_CURSOR_OFFSET: Final = 100_000
"""The furthest a cursor may point into a ranking: five thousand pages."""

SNIPPET_OPEN: Final = "\x02"
SNIPPET_CLOSE: Final = "\x03"
"""What FTS5's `snippet()` is told to put around a matched word. XML 1.0 has no such characters, so
no `.docx` the parser read can hold one; and :func:`snippet_segments` reads them back into segments
that the renderer escapes, so a stray one could misplace a mark and never inject anything."""

SNIPPET_ELLIPSIS: Final = "…"
"""What `snippet()` puts where it cut the text."""

SNIPPET_TOKENS: Final = 24
"""Words in a snippet. FTS5 allows up to 64; a snippet never carries a whole long card."""


class SearchField(StrEnum):
    """A searchable column a prefix limits a term to, by its FTS5 column name."""

    TAG = "tag"
    CITE = "cite"


_PREFIXES: Final = (("author:", SearchField.CITE), ("tag:", SearchField.TAG))
"""The only prefixes: `author:` searches the cite, where a card names its author; `tag:` the tag."""


@dataclass(frozen=True, slots=True)
class QueryTerm:
    """One word or quoted phrase of a query: its text as typed, and how it was asked for."""

    text: str
    phrase: bool = False
    excluded: bool = False
    field: SearchField | None = None

    def fts5(self) -> str:
        """This term as an FTS5 phrase, its double quotes doubled, behind its column filter if any."""
        quoted = '"' + self.text.replace('"', '""') + '"'
        return f"{self.field.value} : {quoted}" if self.field is not None else quoted


@dataclass(frozen=True, slots=True)
class ParsedQuery:
    """What :func:`parse_query` read: the terms in order, and whether any of the query was ignored."""

    terms: tuple[QueryTerm, ...]
    shortened: bool = False

    @property
    def included(self) -> tuple[QueryTerm, ...]:
        return tuple(term for term in self.terms if not term.excluded)

    @property
    def excluded(self) -> tuple[QueryTerm, ...]:
        return tuple(term for term in self.terms if term.excluded)

    def fts5_expression(self) -> str | None:
        """The FTS5 expression: every included term, AND, then NOT each excluded one.

        `None` when nothing is included: FTS5's `NOT` takes two sides, and a query of exclusions
        alone asks for every card but some, which is not a search.
        """
        included = [term.fts5() for term in self.included]
        if not included:
            return None
        expression = " AND ".join(included)
        excluded = [term.fts5() for term in self.excluded]
        if excluded:
            expression = f"({expression})" + "".join(f" NOT {term}" for term in excluded)
        return expression

    def canonical(self) -> list[list[object]]:
        """The terms as plain values, for :func:`search_binding`: two spellings of one query match."""
        return [
            [term.text, term.phrase, term.excluded, term.field.value if term.field else None]
            for term in self.terms
        ]


def _cleaned(raw: str) -> str:
    """`raw` with control characters and lone surrogates turned into spaces."""
    return "".join(" " if unicodedata.category(char) in ("Cc", "Cs") else char for char in raw)


def _has_word(text: str) -> bool:
    """Whether `text` has a character the `unicode61` tokenizer can make a token of."""
    return any(unicodedata.category(char)[0] in "LN" or unicodedata.category(char) == "Co" for char in text)


def parse_query(raw: str) -> ParsedQuery:
    """Read a student's query into terms. Never raises: every string is some query, maybe an empty one."""
    cleaned = _cleaned(raw)
    shortened = len(cleaned) > MAX_QUERY_CHARACTERS
    text = cleaned[:MAX_QUERY_CHARACTERS]
    terms: list[QueryTerm] = []
    position, end = 0, len(text)
    while position < end:
        if text[position].isspace():
            position += 1
            continue
        excluded = text[position] == "-" and position + 1 < end and not text[position + 1].isspace()
        if excluded:
            position += 1
        field_named: SearchField | None = None
        for prefix, field_of_prefix in _PREFIXES:
            after = position + len(prefix)
            if text[position:after].lower() == prefix and after < end and not text[after].isspace():
                field_named, position = field_of_prefix, after
                break
        if text[position] == '"':
            closing = text.find('"', position + 1)
            closing = end if closing == -1 else closing
            words, phrase, position = text[position + 1 : closing], True, closing + 1
        else:
            stop = position
            while stop < end and not text[stop].isspace():
                stop += 1
            words, phrase, position = text[position:stop], False, stop
        if _has_word(words):
            terms.append(QueryTerm(words, phrase=phrase, excluded=excluded, field=field_named))
    if len(terms) > MAX_QUERY_TERMS:
        terms, shortened = terms[:MAX_QUERY_TERMS], True
    return ParsedQuery(tuple(terms), shortened=shortened)


class SearchFilters(DomainModel):
    """What a search is narrowed to. Every filter is optional, and they combine with AND."""

    event: Event | None = Field(default=None, description="LD, POLICY or PF.")
    caselist: StoreName | None = Field(
        default=None, description="A caselist slug, or `openev` for camp cards."
    )
    camp: str | None = Field(default=None, min_length=1, max_length=100, description="One camp's cards.")
    side: Side | None = Field(default=None, description="A side the card was disclosed on; never UNKNOWN.")
    first_seen_on_or_after: date | None = Field(
        default=None,
        description="Cards a caselist first listed on or after this day. Camp cards have no such day.",
    )

    @model_validator(mode="after")
    def _check_filters(self) -> Self:
        if self.side is Side.UNKNOWN:
            raise ValueError("the index records no UNKNOWN side to filter by")
        if self.camp is not None and self.caselist not in (None, CAMP_STORE):
            raise ValueError(f"a camp's cards are in `{CAMP_STORE}`, never in a caselist")
        return self


@dataclass(frozen=True, slots=True)
class RankingWeights:
    """BM25 weights for the FTS5 columns, in their order: tag, cite, read-aloud text, text."""

    tag: float
    cite: float
    read_aloud: float
    text: float

    def bm25(self) -> str:
        """FTS5's per-query rank function: `bm25(10.0, 6.0, 3.0, 1.0)`, as `rank MATCH` takes it."""
        weights = (self.tag, self.cite, self.read_aloud, self.text)
        if any(not weight > 0 for weight in weights):
            raise ValueError("every BM25 weight is a positive number")
        return "bm25(" + ", ".join(repr(float(weight)) for weight in weights) + ")"


RANKING_WEIGHTS: Final = RankingWeights(tag=10.0, cite=6.0, read_aloud=3.0, text=1.0)
"""The one place the ranking's weights live. The interior of the plateau a grid of 168 weightings found on
the synthetic relevance set in `test_evidence_search_ranking.py`; the `v1-e39-t03` session report has
the numbers."""


class InvalidSearchCursor(ValueError):
    """A cursor that is not one this module wrote for the same query, filters and index."""


_CURSOR_BINDING_LENGTH: Final = 32
_CURSOR_TEXT: Final = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_CURSOR_PAYLOAD: Final = re.compile(rf"^(0|[1-9][0-9]{{0,5}}):([0-9a-f]{{{_CURSOR_BINDING_LENGTH}}})$")


def search_binding(index_id: str, query: ParsedQuery, filters: SearchFilters) -> str:
    """SHA-256 of what a ranking depends on: the index, the parsed query and the filters."""
    canonical = {
        "index_id": index_id,
        "terms": query.canonical(),
        "filters": filters.model_dump(mode="json"),
    }
    text = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def encode_search_cursor(binding: str, offset: int) -> str:
    """The cursor for the ranking `binding` names, from position `offset`."""
    if not 0 <= offset <= MAX_CURSOR_OFFSET:
        raise ValueError(f"a cursor's offset is 0 to {MAX_CURSOR_OFFSET}")
    payload = f"{offset}:{binding[:_CURSOR_BINDING_LENGTH]}".encode("ascii")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def decode_search_cursor(cursor: str, binding: str) -> int:
    """The offset a cursor holds, if it is bound to `binding`. :class:`InvalidSearchCursor` otherwise."""
    if _CURSOR_TEXT.match(cursor) is None:
        raise InvalidSearchCursor("not a search cursor")
    try:
        payload = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode("ascii")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        raise InvalidSearchCursor("not a search cursor") from None
    matched = _CURSOR_PAYLOAD.match(payload)
    if matched is None:
        raise InvalidSearchCursor("not a search cursor")
    offset = int(matched.group(1))
    if offset > MAX_CURSOR_OFFSET:
        raise InvalidSearchCursor("a search cursor points no further than the cursor limit")
    if matched.group(2) != binding[:_CURSOR_BINDING_LENGTH]:
        raise InvalidSearchCursor("this cursor belongs to another query, other filters or another index")
    return offset


class SearchNotice(StrEnum):
    """Something the search page should tell the student about their results."""

    NO_SEARCH_TERMS = "NO_SEARCH_TERMS"
    """The query had no word to search for (only exclusions, or only punctuation): no results."""

    QUERY_SHORTENED = "QUERY_SHORTENED"
    """The query ran past :data:`MAX_QUERY_CHARACTERS` or :data:`MAX_QUERY_TERMS`; the rest was ignored."""

    FIRST_SEEN_CASELIST_CARDS_ONLY = "FIRST_SEEN_CASELIST_CARDS_ONLY"
    """First seen applies to caselist cards only: camp cards have no first-seen day and are left out."""


@dataclass(frozen=True, slots=True)
class SnippetSegment:
    """A stretch of a snippet, and whether it is a matched word."""

    text: str
    marked: bool


def snippet_segments(raw: str) -> tuple[SnippetSegment, ...]:
    """Split a snippet `snippet()` marked with :data:`SNIPPET_OPEN` and :data:`SNIPPET_CLOSE` into segments.

    A marker out of turn is ignored, and the markers themselves never appear in a segment.
    """
    segments: list[SnippetSegment] = []
    marked = False
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            text = "".join(buffer)
            if segments and segments[-1].marked == marked:
                segments[-1] = SnippetSegment(segments[-1].text + text, marked)
            else:
                segments.append(SnippetSegment(text, marked))
            buffer.clear()

    for char in raw:
        if char in (SNIPPET_OPEN, SNIPPET_CLOSE):
            flush()
            marked = char == SNIPPET_OPEN
        else:
            buffer.append(char)
    flush()
    return tuple(segments)


@dataclass(frozen=True, slots=True)
class CardRun:
    """A stretch of a card's text with one formatting throughout: what the card page renders.

    `emphases` in :class:`RunEmphasis` order. A highlight's colours are in `highlight_colors` and the
    sizes in `font_sizes`, each sorted; two of either mean two stored spans of different colour or size
    overlap there, and both are kept, so a render covers exactly what the spans cover.

    Every field is a plain value: the text, each emphasis's name (a :class:`RunEmphasis`, which is a
    `str`: `"UNDERLINE"`), each `w:highlight` colour token as stored (`"cyan"`) and each size in
    half-points (`22`). A page that renders runs its own way, such as Copy card's inline styles
    (`v1-e39-t06`), needs nothing else and never needs card HTML.
    """

    text: str
    emphases: tuple[RunEmphasis, ...] = ()
    highlight_colors: tuple[str, ...] = ()
    font_sizes: tuple[int, ...] = ()

    @property
    def formatting(self) -> tuple[tuple[RunEmphasis, ...], tuple[str, ...], tuple[int, ...]]:
        return self.emphases, self.highlight_colors, self.font_sizes


_EMPHASIS_ORDER: Final = {emphasis: rank for rank, emphasis in enumerate(RunEmphasis)}


def card_runs(
    text: str,
    formatting_spans: Sequence[IndexedFormattingSpan],
    font_size_spans: Sequence[IndexedFontSizeSpan],
) -> tuple[CardRun, ...]:
    """Cut `text` into runs at every span edge, each carrying the formatting that covers all of it.

    Neighbouring runs with the same formatting are one run, so two touching underline spans render as
    one. A span reaching past the text is cut at its end. Every character of `text` is in exactly one
    run, in order.
    """
    length = len(text)
    starts: dict[int, list[tuple[str, object]]] = {}
    ends: dict[int, list[tuple[str, object]]] = {}

    def add(start: int, end: int, key: tuple[str, object]) -> None:
        start, end = max(0, start), min(length, end)
        if start < end:
            starts.setdefault(start, []).append(key)
            ends.setdefault(end, []).append(key)

    for span in formatting_spans:
        add(span.start_offset, span.end_offset, ("emphasis", span.emphasis))
        if span.highlight_color is not None:
            add(span.start_offset, span.end_offset, ("colour", span.highlight_color))
    for size in font_size_spans:
        add(size.start_offset, size.end_offset, ("size", size.half_points))

    edges = sorted({0, length, *starts, *ends})
    active: Counter[tuple[str, object]] = Counter()
    runs: list[CardRun] = []
    for here, after in zip(edges, edges[1:], strict=False):
        for key in ends.get(here, ()):
            active[key] -= 1
        for key in starts.get(here, ()):
            active[key] += 1
        keys = [key for key, count in active.items() if count > 0]
        run = CardRun(
            text[here:after],
            emphases=tuple(
                sorted(
                    (value for kind, value in keys if kind == "emphasis" and isinstance(value, RunEmphasis)),
                    key=_EMPHASIS_ORDER.__getitem__,
                )
            ),
            highlight_colors=tuple(sorted(str(value) for kind, value in keys if kind == "colour")),
            font_sizes=tuple(
                sorted(value for kind, value in keys if kind == "size" and isinstance(value, int))
            ),
        )
        if runs and runs[-1].formatting == run.formatting:
            runs[-1] = CardRun(runs[-1].text + run.text, *run.formatting)
        else:
            runs.append(run)
    return tuple(runs)


_SIDE_LABELS: Final = {
    Side.AFF.value: "Aff",
    Side.NEG.value: "Neg",
    Side.PRO.value: "Pro",
    Side.CON.value: "Con",
}
_EVENT_LABELS: Final = {Event.POLICY.value: "Policy", Event.LD.value: "LD", Event.PF.value: "PF"}


def occurrence_provenance_line(
    *,
    caselist: str,
    snapshot: str,
    provenance: bool,
    side: str | None = None,
    school: str | None = None,
    team_code: str | None = None,
    tournament: str | None = None,
    round_label: str | None = None,
    camp: str | None = None,
    camp_year: int | None = None,
    camp_event: str | None = None,
    camp_file_title: str | None = None,
) -> str | None:
    """The line below a card's cite, from what the index stores of an occurrence; `None` when it kept none.

    The same line the E33 writer's `provenance_line` composes from the parsed store's records (data-use
    policy, Attribution rule 2): `[Disclosed: hsld26 2026-09-15 — Maple Grove QX, Aff vs. Riverbend
    Invitational Round 4]`, or `[Disclosed: hsld26 2026-09-15]` with no disclosure on record; a camp
    card's `[OpenEv: Cascade Institute 2026 — Policy, Climate Adv CP]`. A test holds the two together.
    """
    if not provenance:
        return None
    if caselist == CAMP_STORE:
        year = camp_year if camp_year is not None else int(snapshot[:4])
        event_label = _EVENT_LABELS.get(camp_event, snapshot[5:]) if camp_event else snapshot[5:]
        named = " ".join(part for part in (camp, str(year)) if part)
        title = f", {camp_file_title}" if camp_file_title else ""
        return f"[OpenEv: {named} — {event_label}{title}]"
    head = f"Disclosed: {caselist} {snapshot}"
    if school is None and team_code is None:
        return f"[{head}]"
    side_label = _SIDE_LABELS.get(side or "")
    where = " ".join(part for part in (tournament, round_label) if part)
    if side_label and where:
        detail = f", {side_label} vs. {where}"
    elif side_label or where:
        detail = f", {side_label or where}"
    else:
        detail = ""
    return f"[{head} — {school} {team_code}{detail}]"


@dataclass(frozen=True, slots=True)
class SearchHit:
    """One result: enough for a results page, and the card's key to open it by.

    `team_count` is `None` when a suppression left the card with survivors the index kept no
    provenance for (:func:`~debate_core.application.evidence_search.surviving_counts`).
    """

    caselist: str
    cluster_id: str
    event: str
    camp: str | None
    tag: str | None
    short_cite: str | None
    snippet: tuple[SnippetSegment, ...] = field(repr=False)
    file_count: int
    team_count: int | None
    provenance_line: str | None = field(repr=False)


@dataclass(frozen=True, slots=True)
class SearchPage:
    """A page of results, the cursor to the next (`None` on the last), and what the page should say."""

    hits: tuple[SearchHit, ...]
    next_cursor: str | None
    partial: bool = False
    notices: tuple[SearchNotice, ...] = ()


@dataclass(frozen=True, slots=True)
class OccurrenceProvenance:
    """One surviving occurrence of a card: where it was disclosed, if the index kept that.

    `provenance` False means the index kept only the occurrence's digests (it is past the build's
    provenance limit), so every disclosure field is `None` and so is the line. School, team code,
    tournament and round are kept off the `repr`.
    """

    ordinal: int
    caselist: str
    snapshot: str
    last_snapshot: str
    completeness: str
    attributed: bool
    provenance: bool
    side: str | None = None
    school: str | None = field(default=None, repr=False)
    team_code: str | None = field(default=None, repr=False)
    tournament: str | None = field(default=None, repr=False)
    round_label: str | None = field(default=None, repr=False)
    camp: str | None = None
    camp_year: int | None = None
    camp_event: str | None = None
    camp_file_title: str | None = None
    provenance_line: str | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class Card:
    """A card as its page shows it: its representative's text as formatted runs, every survivor's line.

    `team_count` is `None` in the case :class:`SearchHit` describes.
    """

    caselist: str
    cluster_id: str
    event: str
    camp: str | None
    tag: str | None
    cite: str
    short_cite: str | None
    completeness: str
    text: str = field(repr=False)
    read_aloud: str = field(repr=False)
    runs: tuple[CardRun, ...] = field(repr=False)
    sides: tuple[str, ...]
    first_seen: str | None
    last_seen: str | None
    file_count: int
    team_count: int | None
    occurrences: tuple[OccurrenceProvenance, ...] = field(repr=False)

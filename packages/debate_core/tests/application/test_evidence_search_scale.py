"""How fast search answers, on a synthetic 250,000-document index and the operator's own (`v1-e39-t03`).

Both tests are marked slow and stay off the PR's path (working agreement 1).

* ac5 (`test_search_p95_on_a_synthetic_index_of_250000_documents`): an index of 250,000 invented
  documents is generated in the run, from a vocabulary of invented words drawn with a Zipf-like
  skew, so a common word matches a large share of the index the way `the` or `nuclear` would. Each
  of :data:`SYNTHETIC_QUERIES` runs once to warm the cache and then :data:`TIMED_PASSES` times; the
  test prints the 50th and 95th percentile and the slowest time, which the session report records.
* The operator's check (`test_search_timings_on_the_operators_index`): :data:`OPERATOR_QUERIES`, twenty
  generic queries, run read-only against the index named by `DEBATE_TUB_SEARCH_INDEX`. It prints
  timings and result counts and nothing else: no tag, cite, text or provenance. It skips when the
  variable is not set, and is marked `operator_data`, so validate-dev's slow tier leaves it out
  rather than counting that skip as a failure (`v1-e01-t34`).
* The operator's passage and prefix check (`test_passage_and_prefix_timings_on_the_operators_index`,
  `v1-e39-t13`): :data:`OPERATOR_PASSAGES`, eleven invented sentences of generic debate words up to
  the forty-word limit, searched as passages, and :data:`OPERATOR_PREFIXES`, twelve prefixes down to
  three letters, on the same index and under the same rules: timings and counts only.

Times are the service's whole call: parsing, the ranked statement, the snippets, the result
objects and, since `v1-e39-t11`, the result count up to its default cap of 1,000, with no
suppression predicate. The synthetic test also times every query with a cap of 1, which reads two
rows, as the nearest thing to a search with no count, and prints each query's count.
"""

from __future__ import annotations

import os
import random
import sqlite3
import statistics
import time
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Final

import pytest

from debate_core.application.evidence_search import EvidenceSearchService
from debate_core.application.ports.search_index import IndexedOccurrence, SearchDocument
from debate_core.domain.caselist import Event, Side
from debate_core.domain.evidence_search import SearchFilters, parse_passage, parse_query
from debate_core.integrations.local.search_index import SqliteSearchIndexWriter
from debate_core.integrations.local.search_index_reader import SqliteSearchIndexReader

SYNTHETIC_DOCUMENTS: Final = 250_000
VOCABULARY: Final = 20_000
TEXT_WORDS: Final = 120
TIMED_PASSES: Final = 3

_ONSETS: Final = (
    "b",
    "d",
    "f",
    "g",
    "k",
    "l",
    "m",
    "n",
    "p",
    "r",
    "s",
    "t",
    "v",
    "z",
    "br",
    "tr",
    "pl",
    "st",
)
_VOWELS: Final = ("a", "e", "i", "o", "u", "ai", "ou")
_CODAS: Final = ("", "n", "r", "s", "l", "x", "m")


def vocabulary(size: int) -> list[str]:
    """Invented words, `kelomar`-like: distinct, pronounceable, and no word of any language on purpose."""
    words: list[str] = []
    for one in range(size * 4):
        syllables: list[str] = []
        value = one
        for _ in range(3):
            value, onset = divmod(value, len(_ONSETS))
            value, vowel = divmod(value, len(_VOWELS))
            syllables.append(_ONSETS[onset] + _VOWELS[vowel])
        value, coda = divmod(value, len(_CODAS))
        words.append("".join(syllables) + _CODAS[coda] + (str(value) if value else ""))
    return sorted(set(words), key=lambda word: (len(word), word))[:size]


WORDS: Final = vocabulary(VOCABULARY)
SURNAMES: Final = [word.title() for word in WORDS[-500:]]


def synthetic_documents(count: int, seed: int = 39) -> Iterator[SearchDocument]:
    generator = random.Random(seed)
    weights = [1.0 / (rank + 1) for rank in range(VOCABULARY)]
    cumulative: list[float] = []
    total = 0.0
    for weight in weights:
        total += weight
        cumulative.append(total)
    events = ("LD", "POLICY", "PF")
    caselists = {"LD": "hsld26", "POLICY": "hspolicy26", "PF": "hspf26"}
    sides = {"LD": ("AFF", "NEG"), "POLICY": ("AFF", "NEG"), "PF": ("PRO", "CON")}
    for doc_id in range(1, count + 1):
        words = generator.choices(WORDS, cum_weights=cumulative, k=TEXT_WORDS + 8)
        event = events[doc_id % 3]
        camp = doc_id % 8 == 0
        caselist = "openev" if camp else caselists[event]
        text = " ".join(words[8:])
        read_aloud = " ".join(words[8 : 8 + TEXT_WORDS // 4])
        author = SURNAMES[generator.randrange(len(SURNAMES))]
        day = f"2026-{8 + doc_id % 3:02d}-{1 + doc_id % 28:02d}"
        yield SearchDocument(
            doc_id=doc_id,
            caselist=caselist,
            cluster_id=f"{doc_id:064x}",
            event=event,
            camp="Cascade Institute" if camp else None,
            tag=" ".join(words[:8]),
            cite=(
                f"{author} 26, Dr. {author}, professor at Invented University, "
                f"{' '.join(words[2:6])}, Invented Review"
            ),
            short_cite=f"{author} 26",
            read_aloud=read_aloud,
            text=text,
            completeness="FULL",
            formatting_spans=(),
            font_size_spans=(),
            sides=() if camp else (sides[event][doc_id % 2],),
            first_seen=None if camp else day,
            last_seen=None if camp else day,
            file_count=1,
            team_count=1,
            occurrences=(
                IndexedOccurrence(
                    ordinal=0,
                    caselist=caselist,
                    source_sha256=f"{doc_id:064x}",
                    disclosure=None if camp else f"{doc_id:064x}"[::-1],
                    first_element_index=0,
                    last_element_index=2,
                    snapshot="2026-policy" if camp else day,
                    last_snapshot="2026-policy" if camp else day,
                    completeness="FULL",
                    attributed=True,
                    provenance=True,
                    side=None if camp else sides[event][doc_id % 2],
                    school=None if camp else "Maple Grove",
                    team_code=None if camp else "QX",
                ),
            ),
        )


SYNTHETIC_QUERIES: Final = (
    (WORDS[0], SearchFilters()),
    (WORDS[1], SearchFilters()),
    (WORDS[9], SearchFilters()),
    (WORDS[99], SearchFilters()),
    (WORDS[999], SearchFilters()),
    (WORDS[9999], SearchFilters()),
    (f"{WORDS[0]} {WORDS[1]}", SearchFilters()),
    (f"{WORDS[4]} {WORDS[49]}", SearchFilters()),
    (f'"{WORDS[0]} {WORDS[1]}"', SearchFilters()),
    (f"tag:{WORDS[2]}", SearchFilters()),
    (f"author:{SURNAMES[7].lower()}", SearchFilters()),
    (f"{WORDS[2]} -{WORDS[3]}", SearchFilters()),
    (WORDS[0], SearchFilters(event=Event.PF)),
    (WORDS[0], SearchFilters(side=Side.CON)),
    (WORDS[0], SearchFilters(caselist="openev")),
    (WORDS[5], SearchFilters(first_seen_on_or_after=date(2026, 10, 20))),
    (f"{WORDS[9]} {WORDS[99]}", SearchFilters(event=Event.LD, side=Side.AFF)),
    (f"{WORDS[499]} {WORDS[999]}", SearchFilters()),
    (f'"{WORDS[3]} {WORDS[7]}" -{WORDS[11]}', SearchFilters()),
    (f"{WORDS[19]} {WORDS[29]} {WORDS[39]}", SearchFilters()),
)
"""Twenty queries over the vocabulary's ranks: the commonest word, rare ones, AND, phrases, the two
prefixes, an exclusion, every filter, and narrow filters over a common word."""

OPERATOR_QUERIES: Final = (
    ("economy", SearchFilters()),
    ("nuclear war", SearchFilters()),
    ("climate change", SearchFilters()),
    ('"economic growth"', SearchFilters()),
    ("china", SearchFilters()),
    ("deterrence", SearchFilters()),
    ("extinction", SearchFilters()),
    ("democracy", SearchFilters()),
    ("artificial intelligence", SearchFilters()),
    ("tag:extinction", SearchFilters()),
    ("author:professor", SearchFilters()),
    ("warming -china", SearchFilters()),
    ('"nuclear war" -russia', SearchFilters()),
    ("the", SearchFilters()),
    ("economy", SearchFilters(event=Event.POLICY)),
    ("nuclear war", SearchFilters(side=Side.AFF)),
    ("china", SearchFilters(first_seen_on_or_after=date(2026, 9, 15))),
    ("hegemony", SearchFilters(caselist="openev")),
    ("pandemic", SearchFilters(event=Event.PF, side=Side.CON)),
    ("space", SearchFilters(event=Event.LD)),
)
"""Twenty generic queries: common words, phrases, both prefixes, exclusions and every filter."""

OPERATOR_PASSAGES: Final = (
    ("Nuclear war between great powers would cause human extinction", SearchFilters()),
    ("Economic growth increases carbon emissions and accelerates climate change", SearchFilters()),
    ("Artificial intelligence threatens jobs and democracy around the world", SearchFilters()),
    ("Deterrence prevents conflict because leaders fear escalation", SearchFilters()),
    ("A rising China challenges American hegemony in Asia", SearchFilters()),
    ("Pandemics spread faster when global health systems collapse", SearchFilters(event=Event.PF)),
    ("Space militarization risks an arms race with Russia", SearchFilters(side=Side.AFF)),
    ("Warming oceans destroy coral reefs and the fisheries that feed millions", SearchFilters()),
    ("Sanctions fail to change authoritarian regime behavior", SearchFilters(caselist="openev")),
    ("Renewable energy transitions reduce dependence on oil imports", SearchFilters()),
    (
        "Nuclear war between great powers would cause human extinction, and economic growth increases "
        "carbon emissions that accelerate climate change, while artificial intelligence threatens jobs and "
        "democracy; deterrence prevents conflict because leaders fear escalation, a rising China challenges "
        "American hegemony, pandemics spread when health systems collapse, and sanctions fail regimes "
        "everywhere today",
        SearchFilters(),
    ),
)
"""Eleven invented passages of generic words, the last at the forty-content-word limit."""

OPERATOR_PREFIXES: Final = (
    ("econom*", SearchFilters()),
    ("nucl* war", SearchFilters()),
    ("climat*", SearchFilters()),
    ("deter*", SearchFilters()),
    ("extinct*", SearchFilters()),
    ("democra*", SearchFilters()),
    ("hegemon*", SearchFilters(caselist="openev")),
    ("pandem*", SearchFilters(event=Event.PF)),
    ("milit* -china", SearchFilters()),
    ("tag:sanction*", SearchFilters()),
    ("pro*", SearchFilters()),
    ("con*", SearchFilters()),
)
"""Twelve prefixes: common stems, a prefix with a word, a filter, an exclusion, a column, and the two
widest three-letter prefixes, `pro*` and `con*`."""


def time_queries(
    searched: EvidenceSearchService,
    queries: tuple[tuple[str, SearchFilters], ...],
    counted: list[str] | None = None,
    *,
    passage: bool = False,
) -> tuple[list[float], list[float], list[int]]:
    """Cold times (the first pass), warm times (the timed passes), and each query's first-page size.

    Each query's result count, as the page writes it, is appended to `counted` when it is given."""
    cold: list[float] = []
    sizes: list[int] = []
    for query, filters in queries:
        started = time.perf_counter()
        page = searched.search(query, filters, passage=passage)
        cold.append(time.perf_counter() - started)
        sizes.append(len(page.hits))
        assert not page.partial
        assert page.count is not None
        if counted is not None:
            counted.append(f"{page.count.matches}{'+' if page.count.capped else ''}")
    warm: list[float] = []
    for _ in range(TIMED_PASSES):
        for query, filters in queries:
            started = time.perf_counter()
            searched.search(query, filters, passage=passage)
            warm.append(time.perf_counter() - started)
    return cold, warm, sizes


def percentiles(times: list[float]) -> str:
    cuts = statistics.quantiles(times, n=100, method="inclusive")
    return f"p50 {cuts[49] * 1000:.1f} ms, p95 {cuts[94] * 1000:.1f} ms, max {max(times) * 1000:.1f} ms"


def match_counts(
    path: Path, queries: tuple[tuple[str, SearchFilters], ...], *, passage: bool = False
) -> list[int]:
    """How many documents each query's words match, before filters: counts only. For a passage, any
    of its words: the OR the passage's minimum then narrows."""
    parse = parse_passage if passage else parse_query
    with sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro&immutable=1", uri=True) as connection:
        return [
            connection.execute(
                "SELECT count(*) FROM search WHERE search MATCH ?", (parse(query).fts5_expression(),)
            ).fetchone()[0]
            for query, _ in queries
        ]


@pytest.mark.slow
def test_search_p95_on_a_synthetic_index_of_250000_documents(tmp_path: Path) -> None:
    """ac5: the 95th-percentile query time, reported in the session report."""
    count = int(os.environ.get("DEBATE_SEARCH_SCALE_DOCUMENTS", SYNTHETIC_DOCUMENTS))
    path = tmp_path / "search-index.sqlite"
    started = time.perf_counter()
    sink = SqliteSearchIndexWriter().create(path)
    for document in synthetic_documents(count):
        sink.add(document)
    sink.finish()
    built = time.perf_counter() - started
    searched = EvidenceSearchService(
        SqliteSearchIndexReader(path, index_id="0" * 16), time_budget_seconds=600.0
    )
    shown: list[str] = []
    cold, warm, sizes = time_queries(searched, SYNTHETIC_QUERIES, shown)
    barely = EvidenceSearchService(
        SqliteSearchIndexReader(path, index_id="0" * 16), time_budget_seconds=600.0, count_cap=1
    )
    _, warm_barely, _ = time_queries(barely, SYNTHETIC_QUERIES)
    counts = match_counts(path, SYNTHETIC_QUERIES)
    print(
        f"\nsynthetic index: {count} documents, {path.stat().st_size} bytes, built in {built:.1f} s, "
        f"SQLite {sqlite3.sqlite_version}"
        f"\nwarm, {len(warm)} timed searches, counting to 1,000: {percentiles(warm)}"
        f"\ncold, first pass, counting to 1,000: {percentiles(cold)}"
        f"\nwarm, {len(warm_barely)} timed searches, counting to 1: {percentiles(warm_barely)}"
        f"\nmatches per query: {counts}"
        f"\ncount shown per query: {shown}"
        f"\nfirst-page results per query: {sizes}"
    )
    assert count == SYNTHETIC_DOCUMENTS or "DEBATE_SEARCH_SCALE_DOCUMENTS" in os.environ
    assert max(counts) > count // 4, "the commonest word matches a large share of the index"
    assert all(size == min(20, matched) for size, matched in zip(sizes[:12], counts[:12], strict=True))


@pytest.mark.slow
@pytest.mark.operator_data
def test_search_timings_on_the_operators_index() -> None:
    """The operator's read-only check: timings and counts only."""
    named = os.environ.get("DEBATE_TUB_SEARCH_INDEX")
    if not named:
        pytest.skip("DEBATE_TUB_SEARCH_INDEX names no index")
    path = Path(named).expanduser()
    searched = EvidenceSearchService(
        SqliteSearchIndexReader(path, index_id=path.parent.name), time_budget_seconds=600.0
    )
    cold, warm, sizes = time_queries(searched, OPERATOR_QUERIES)
    counts = match_counts(path, OPERATOR_QUERIES)
    print(
        f"\noperator's index: {path.stat().st_size} bytes, SQLite {sqlite3.sqlite_version}"
        f"\nwarm, {len(warm)} timed searches: {percentiles(warm)}"
        f"\ncold, first pass: {percentiles(cold)}"
        f"\nslowest warm query: number {1 + warm.index(max(warm)) % len(OPERATOR_QUERIES)}"
        f"\nmatches per query: {counts}"
        f"\nfirst-page results per query: {sizes}"
    )


@pytest.mark.slow
@pytest.mark.operator_data
def test_passage_and_prefix_timings_on_the_operators_index() -> None:
    """The operator's read-only check of `v1-e39-t13`'s queries: timings and counts only."""
    named = os.environ.get("DEBATE_TUB_SEARCH_INDEX")
    if not named:
        pytest.skip("DEBATE_TUB_SEARCH_INDEX names no index")
    path = Path(named).expanduser()
    searched = EvidenceSearchService(
        SqliteSearchIndexReader(path, index_id=path.parent.name), time_budget_seconds=600.0
    )
    words = [len(parse_passage(query).terms) for query, _ in OPERATOR_PASSAGES]
    passage_counts: list[str] = []
    cold, warm, sizes = time_queries(searched, OPERATOR_PASSAGES, passage_counts, passage=True)
    prefix_counts: list[str] = []
    prefix_cold, prefix_warm, prefix_sizes = time_queries(searched, OPERATOR_PREFIXES, prefix_counts)
    print(
        f"\noperator's index: {path.stat().st_size} bytes, format {searched_format(path)}, "
        f"SQLite {sqlite3.sqlite_version}"
        f"\npassages, warm, {len(warm)} timed searches: {percentiles(warm)}"
        f"\npassages, cold, first pass: {percentiles(cold)}"
        f"\npassage content words: {words}"
        f"\npassage OR matches: {match_counts(path, OPERATOR_PASSAGES, passage=True)}"
        f"\npassage results counted: {passage_counts}"
        f"\nslowest warm passage: number {1 + warm.index(max(warm)) % len(OPERATOR_PASSAGES)}"
        f"\nprefixes, warm, {len(prefix_warm)} timed searches: {percentiles(prefix_warm)}"
        f"\nprefixes, cold, first pass: {percentiles(prefix_cold)}"
        f"\nprefix results counted: {prefix_counts}"
        f"\nslowest warm prefix: number {1 + prefix_warm.index(max(prefix_warm)) % len(OPERATOR_PREFIXES)}"
        f"\nfirst-page results: passages {sizes}, prefixes {prefix_sizes}"
    )
    assert words[-1] == 40, "the last passage is at the forty-word limit"


def searched_format(path: Path) -> int:
    with sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro&immutable=1", uri=True) as connection:
        return connection.execute("PRAGMA user_version").fetchone()[0]

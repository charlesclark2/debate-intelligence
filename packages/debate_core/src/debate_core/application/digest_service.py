"""`debate-research daily <preset>`: one day's new research, grouped by argument and need (v1-e08-t07).

:class:`DigestService` runs a preset's searches for a date window, leaves out what an earlier digest
of the same preset already listed, and groups the rest by the preset's argument/need pairs. The CLI
renders the digest and writes its file; this module decides what is in it and when it counts as listed.

## The searches

For each of the preset's pairs, in the preset's order, and each of its queries, in order, one
federated search (:class:`~debate_core.application.federated_search.FederatedSearchService`, the one
`search` runs) asks the preset's providers the query expanded for that argument and need, on the
preset's topic, inside the window: from the start of the first day to the end of `--date`, in UTC.
The window is the search's own `since` and `until`, so it overrules every template's recency window.
The service is built for the preset's feed topics alone (the container's job), so a politics digest
never reads the health-insurance feeds. The searches run one after another; each is stored as
`search` stores it.

## What is new

A result is new unless any of its canonical URLs or DOIs was listed by a digest of the same preset on
another date (:mod:`~debate_core.application.digest_seen_set`). A source two of the day's searches
find is listed once, in the first group, in preset order, that found it. In a group, results keep
the order they were found in: query by query, each search's in rank order.

## When results count as listed

Only after the digest file is written. :meth:`DigestService.run` builds the digest, hands it to the
writer it is given, and saves the seen-set only when the writer returns, so a writer that fails, or a
crash before it finishes, marks nothing seen. A digest whose searches got no answer from any provider
(FAILED) is not written and marks nothing.

## The status and the footer

The digest's status is :func:`~debate_core.application.federated_search.search_status` over every
call of every search: COMPLETE, PARTIAL when any provider failed on any search or answered in part,
FAILED when none answered. The provider footer is the searches' own record, all of it.

The preset's providers are configuration, not a request by name (the PM's ruling 3 on v1-e07-t15): a
search asks them with `providers_named=False`, so one that settings enable but cannot configure (its
key missing, as GovInfo's often is) is named with its cure and left out of the status, as it is for a
plain search. So, since v1-e07-t23, is one the environment does not enable at all: it is named with
`enable it in providers.enabled`, and the digest is COMPLETE if the others answered. A digest none of
whose providers was asked is still FAILED.

## Feed topics awaiting review

A feed topic with a feed whose `review:` is still `awaiting_coach_review` is read like any other, and
the digest names the topic and those feeds' publishers (the PM's amendment of 2026-10-22).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Final, Protocol

from debate_core.application.batch_cut_service import BatchCandidate, BatchNeed, batch_need
from debate_core.application.digest_seen_set import DigestSeenSet, DigestSeenStore, SourceKeys, source_keys
from debate_core.application.federated_ranking import RankedCandidate
from debate_core.application.federated_search import search_status
from debate_core.application.federated_search_types import ExpansionRequest, SearchOutcome, SearchRequest
from debate_core.domain import AccessStatus, Article, SearchFilters, SearchStatus
from debate_core.domain.argument_taxonomy import ArgumentTaxonomy
from debate_core.domain.daily_preset import DailyPair, DailyPreset
from debate_core.domain.discovery import ProviderStatus

__all__ = [
    "MAX_WINDOW_DAYS",
    "Digest",
    "DigestGroup",
    "DigestItem",
    "DigestRequest",
    "DigestSearching",
    "DigestService",
    "DigestWindow",
    "DigestWriter",
    "FeedTopicReview",
    "digest_batch_candidates",
    "digest_bundle_need",
]

MAX_WINDOW_DAYS: Final = 31
"""The longest `--window`: a month of a preset's feeds is already more than a digest a person reads."""

_WINDOW: Final = re.compile(r"^([1-9][0-9]?)d$")


@dataclass(frozen=True, slots=True)
class DigestWindow:
    """How many days, ending with the digest's date, its searches cover: `1d` is the date alone."""

    days: int = 1

    def __post_init__(self) -> None:
        if not 1 <= self.days <= MAX_WINDOW_DAYS:
            raise ValueError(f"a window is 1 to {MAX_WINDOW_DAYS} days, not {self.days}")

    @classmethod
    def parse(cls, text: str) -> DigestWindow:
        """`1d` to `31d`; `ValueError` saying what a window is for anything else."""
        found = _WINDOW.fullmatch(text.strip())
        if found is None:
            raise ValueError(f"{text!r} is not a window: give days, 1d to {MAX_WINDOW_DAYS}d")
        return cls(int(found.group(1)))

    def bounds(self, day: date) -> tuple[datetime, datetime]:
        """The first instant of the window's first day and the last of `day`, in UTC."""
        first = day - timedelta(days=self.days - 1)
        return datetime.combine(first, time.min, tzinfo=UTC), datetime.combine(day, time.max, tzinfo=UTC)

    def __str__(self) -> str:
        return f"{self.days}d"


@dataclass(frozen=True, slots=True)
class DigestRequest:
    """One digest: a preset, the date it is for, and how many days back it looks."""

    preset: DailyPreset
    day: date
    window: DigestWindow = DigestWindow()


@dataclass(frozen=True, slots=True)
class FeedTopicReview:
    """A feed topic a preset reads, and the publishers of its feeds the coach has not yet reviewed."""

    topic: str
    awaiting_coach_review: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DigestItem:
    """One new result: the ranked source, its Article, and the search that found it."""

    ranked: RankedCandidate
    article: Article | None
    query: str
    """The preset query the search was for."""
    search_id: str
    need: BatchNeed
    """What a card cut from it is for: the search's argument and need, in the taxonomy's words."""
    keys: SourceKeys

    @property
    def known_access(self) -> AccessStatus:
        return AccessStatus.UNKNOWN if self.article is None else self.article.access_status


@dataclass(frozen=True, slots=True)
class DigestGroup:
    """One argument/need pair of the preset, and the new results its searches found."""

    pair: DailyPair
    heading: str
    """`Politics DA — Uniqueness`: the argument's and the need's labels."""
    items: tuple[DigestItem, ...]


@dataclass(frozen=True, slots=True)
class Digest:
    """One preset's digest for one date: its groups, the searches behind them, and what was left out."""

    preset: DailyPreset
    day: date
    window: DigestWindow
    since: datetime
    until: datetime
    groups: tuple[DigestGroup, ...]
    outcomes: tuple[SearchOutcome, ...]
    listed_before: int
    """Distinct sources the searches found that a digest of another date already listed."""
    feed_topics: tuple[FeedTopicReview, ...]
    file: Path | None = None
    """Where the digest was written; None until it is, and for a FAILED digest, which is not."""

    @property
    def heading(self) -> str:
        """The digest's own heading, and its bundle's block: `Politics daily digest: 2026-09-17`."""
        return f"{self.preset.label} daily digest: {self.day.isoformat()}"

    @property
    def provider_statuses(self) -> tuple[ProviderStatus, ...]:
        """Every call of every search, in the order the searches ran."""
        return tuple(status for outcome in self.outcomes for status in outcome.provider_statuses)

    @property
    def uncounted(self) -> tuple[str, ...]:
        """The preset's providers left out of the status, as each search left them out (v1-e07-t15)."""
        return tuple(dict.fromkeys(name for outcome in self.outcomes for name in outcome.uncounted))

    @property
    def status(self) -> SearchStatus:
        """COMPLETE, PARTIAL or FAILED over every call of every search."""
        return search_status(self.provider_statuses, uncounted=self.uncounted)

    @property
    def items(self) -> tuple[DigestItem, ...]:
        """Every new result, group by group."""
        return tuple(item for group in self.groups for item in group.items)

    @property
    def awaiting_review(self) -> tuple[FeedTopicReview, ...]:
        """The feed topics read with a feed still awaiting the coach's review."""
        return tuple(topic for topic in self.feed_topics if topic.awaiting_coach_review)


class DigestSearching(Protocol):
    """The search a digest runs each of its queries through: `search`'s federated search."""

    async def search(self, request: SearchRequest) -> SearchOutcome: ...


type DigestWriter = Callable[[Digest], Path]
"""Renders the digest and writes its file, returning where; raising means nothing was written."""


class DigestService:
    """Builds a preset's digest for a date, has it written, and only then records what it listed."""

    def __init__(
        self,
        *,
        searching: DigestSearching,
        seen: DigestSeenStore,
        taxonomy: ArgumentTaxonomy,
        feed_reviews: Mapping[str, Sequence[str]] | None = None,
    ) -> None:
        """`feed_reviews`: for each feed topic, the publishers of its feeds still awaiting review."""
        self._searching = searching
        self._seen = seen
        self._taxonomy = taxonomy
        self._feed_reviews = dict(feed_reviews or {})

    async def build(self, request: DigestRequest) -> Digest:
        """The digest, without writing it or recording anything: see the module docstring."""
        preset = request.preset
        seen = self._seen.load(preset.name)
        since, until = request.window.bounds(request.day)
        listed: list[SourceKeys] = []
        left_out: list[SourceKeys] = []
        outcomes: list[SearchOutcome] = []
        groups: list[DigestGroup] = []
        for pair in preset.pairs:
            items: list[DigestItem] = []
            for query in preset.queries:
                outcome = await self._searching.search(self._request(preset, pair, query, since, until))
                outcomes.append(outcome)
                for item in self._items(outcome, query):
                    if any(item.keys.overlaps(keys) for keys in (*listed, *left_out)):
                        continue
                    if seen.listed_before(item.keys, request.day):
                        left_out.append(item.keys)
                        continue
                    listed.append(item.keys)
                    items.append(item)
            groups.append(DigestGroup(pair=pair, heading=self._heading(pair), items=tuple(items)))
        return Digest(
            preset=preset,
            day=request.day,
            window=request.window,
            since=since,
            until=until,
            groups=tuple(groups),
            outcomes=tuple(outcomes),
            listed_before=len(left_out),
            feed_topics=tuple(
                FeedTopicReview(topic, tuple(self._feed_reviews.get(topic, ())))
                for topic in preset.feed_topics
            ),
        )

    async def run(self, request: DigestRequest, write: DigestWriter) -> Digest:
        """Build the digest, have `write` write it, and then record its results as listed.

        A FAILED digest is returned unwritten and records nothing. If `write` raises, nothing is
        recorded and the exception propagates.
        """
        digest = await self.build(request)
        if digest.status is SearchStatus.FAILED:
            return digest
        path = write(digest)
        seen: DigestSeenSet = self._seen.load(request.preset.name)
        self._seen.save(seen.with_listed((item.keys for item in digest.items), request.day))
        return replace(digest, file=path)

    def _request(
        self, preset: DailyPreset, pair: DailyPair, query: str, since: datetime, until: datetime
    ) -> SearchRequest:
        return SearchRequest(
            query=query,
            filters=SearchFilters(since=since, until=until, max_results=preset.max_results),
            providers=preset.providers,
            providers_named=False,
            expansion=ExpansionRequest(argument=pair.argument, need=pair.need, topic_id=preset.topic),
            topic_id=preset.topic,
        )

    def _items(self, outcome: SearchOutcome, query: str) -> list[DigestItem]:
        expansion = outcome.search.expansion
        if expansion is None:
            raise ValueError("a digest's search is always expanded for its pair; this one was not")
        need = batch_need(self._taxonomy, expansion, query)
        articles = {
            result.rank: article for result, article in zip(outcome.results, outcome.articles, strict=True)
        }
        return [
            DigestItem(
                ranked=ranked,
                article=articles.get(ranked.rank),
                query=query,
                search_id=outcome.search.search_id,
                need=need,
                keys=source_keys(ranked),
            )
            for ranked in sorted(outcome.ranked_candidates, key=lambda ranked: ranked.rank)
        ]

    def _heading(self, pair: DailyPair) -> str:
        argument = self._taxonomy.find_argument(pair.argument)
        if argument is None:
            raise ValueError(f"the taxonomy has no argument {pair.argument!r}; the presets were not checked")
        need = self._taxonomy.family_of(argument).need(pair.need)
        return f"{argument.label} — {need.label}"


def digest_batch_candidates(digest: Digest) -> tuple[BatchCandidate, ...]:
    """The digest's new results as `--auto-cut` candidates: each group's first, then each one's second...

    So the top results of every argument and need are tried before any group's second, and N cards are
    cut from across the digest, not all from its first group. Each candidate carries its own need, the
    one its search was expanded for, and is numbered in this order from 1.
    """
    order: list[DigestItem] = []
    depth = max((len(group.items) for group in digest.groups), default=0)
    for position in range(depth):
        order.extend(group.items[position] for group in digest.groups if position < len(group.items))
    return tuple(
        BatchCandidate(
            rank=number,
            url=item.ranked.candidate.url,
            title=item.ranked.candidate.title,
            known_access=item.known_access,
            need=item.need,
        )
        for number, item in enumerate(order, start=1)
    )


def digest_bundle_need(digest: Digest) -> BatchNeed:
    """The batch request's need for a digest's `--auto-cut`: its heading is the bundle's block heading,
    the digest's own. Every candidate carries the need its search was for
    (:func:`digest_batch_candidates`), so this one's argument and need are never what a card is cut for."""
    return BatchNeed(argument=digest.preset.label, need=digest.heading, heading=digest.heading)

"""PositionClassificationService: one caselist's sections and cards placed under its topic's positions.

`v1-e32-t02-position-classification`, deterministic stage only (the PM's amendment of 2026-10-22): no
model is called, and an item the matcher cannot place goes to the review queue and is reported as
Unclassified by `v1-e32-t03`. The model stage is `v1-e32-t07`'s, and adds MODEL results to the same
cache under its own prompt version.

One run, over a :class:`~debate_core.application.landscape_seeding.SeedReading` (the caselist's
parsed sources on the topic, with their disclosing teams):

1. reads the topic's merged taxonomy and the coach's overrides from the
   :class:`~debate_core.application.ports.taxonomy_repository.TaxonomyRepository`;
2. reads every section and card (:func:`~debate_core.arguments.landscape.matcher.read_items`);
3. looks each one's :class:`~debate_core.application.ports.classification_store.ClassificationKey`
   up in the caselist's cache, and places only what is not there
   (:meth:`~debate_core.arguments.landscape.matcher.PositionMatcher.place`). A cached result is
   checked against the taxonomy's active ids before it is used, and placed again if it fails, so an
   edit made without a version bump cannot bring back an id that is gone;
4. writes the cache back when anything changed, keeping every other topic's results and dropping this
   topic's results under any other taxonomy version;
5. builds the review queue from the items nothing placed or placed below the threshold, and writes its
   CSV to the data directory.

It returns every item's :class:`~debate_core.domain.landscape_classification.PositionClassification`
for the report, with counts for the run's summary.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Final

from pydantic import ValidationError

from debate_core.application.landscape_seeding import SeedReading
from debate_core.application.ports.classification_store import (
    CachedClassification,
    ClassificationKey,
    ClassificationStore,
)
from debate_core.application.ports.taxonomy_repository import TaxonomyRepository
from debate_core.arguments.landscape.matcher import MatchItem, PositionMatcher, read_items
from debate_core.arguments.landscape.review_queue import (
    DEFAULT_MINIMUM_REVIEW_TEAMS,
    DEFAULT_REVIEW_THRESHOLD,
    QueuedItem,
    ReviewQueue,
    build_review_queue,
    needs_review,
)
from debate_core.arguments.landscape.source_headings import CaselistNames
from debate_core.domain.landscape import Taxonomy
from debate_core.domain.landscape_classification import (
    DETERMINISTIC_PROMPT_VERSION,
    ClassificationResult,
    ItemKind,
    PositionClassification,
    checked_against,
)

__all__ = [
    "DECIDED_NO_POSITION",
    "UNPLACED",
    "ClassificationCounts",
    "ClassificationRun",
    "PositionClassificationService",
]

UNPLACED: Final = "UNPLACED"
"""The count key of an item nothing placed."""

DECIDED_NO_POSITION: Final = "OVERRIDE_NO_POSITION"
"""The count key of an item every heading over which the coach ruled names no position."""


def _count_key(result: ClassificationResult) -> str:
    if result.method is None:
        return UNPLACED
    if result.position_id is None:
        return DECIDED_NO_POSITION
    return result.method.value


@dataclass(frozen=True, slots=True)
class ClassificationCounts:
    """What one run read, placed, looked up and queued."""

    sources: int
    sections: int
    cards: int
    cards_by_method: dict[str, int]
    """Cards by method, plus :data:`UNPLACED` and :data:`DECIDED_NO_POSITION`."""
    sections_by_method: dict[str, int]
    cards_counted: int
    """Cards under a position at or above the review threshold: what a report counts."""
    cards_below_threshold: int
    lookups: int
    """Distinct cache keys looked up: items read alike are looked up once."""
    hits: int
    misses: int
    """Keys placed by the matcher in this run: not cached, or cached under an id that is gone."""
    refused_cached: int
    """Of the misses, cached results that named an id the taxonomy no longer counts under."""
    cache_written: bool

    @property
    def hit_rate(self) -> float:
        return self.hits / self.lookups if self.lookups else 1.0


@dataclass(frozen=True, slots=True)
class ClassificationRun:
    caselist: str
    topic_id: str
    taxonomy_version: str
    prompt_version: str
    classifications: tuple[PositionClassification, ...] = field(repr=False)
    review_queue: ReviewQueue = field(repr=False)
    review_queue_location: str = field(repr=False)
    counts: ClassificationCounts


class PositionClassificationService:
    """Places a caselist's items under its topic's positions, deterministically and cached."""

    def __init__(
        self,
        *,
        taxonomies: TaxonomyRepository,
        store: ClassificationStore,
        review_threshold: float = DEFAULT_REVIEW_THRESHOLD,
        minimum_review_teams: int = DEFAULT_MINIMUM_REVIEW_TEAMS,
    ) -> None:
        if not 0.0 <= review_threshold <= 1.0:
            raise ValueError(f"the review threshold is between 0 and 1; got {review_threshold}")
        self._taxonomies = taxonomies
        self._store = store
        self._threshold = review_threshold
        self._minimum_review_teams = minimum_review_teams

    async def classify(self, reading: SeedReading) -> ClassificationRun:
        taxonomy = self._taxonomies.taxonomy(reading.topic_id)
        matcher = PositionMatcher(taxonomy, self._taxonomies.overrides(reading.topic_id))
        names = CaselistNames(reading.caselist_names)
        cached = {entry.key: entry for entry in await self._store.read(reading.caselist)}
        placed: dict[ClassificationKey, ClassificationResult] = {}
        written: dict[ClassificationKey, CachedClassification] = {}
        refused: set[ClassificationKey] = set()
        hits = 0
        classifications: list[PositionClassification] = []
        queued: list[QueuedItem] = []
        by_kind: dict[ItemKind, Counter[str]] = {ItemKind.SECTION: Counter(), ItemKind.CARD: Counter()}
        below = counted = 0
        for source in reading.sources:
            for item in read_items(source, names):
                key = ClassificationKey(
                    reading.topic_id,
                    taxonomy.taxonomy_version,
                    matcher.override_digest(item),
                    DETERMINISTIC_PROMPT_VERSION,
                    item.fingerprint,
                )
                result = placed.get(key)
                if result is None:
                    result = _usable(cached.get(key), taxonomy)
                    if result is not None:
                        hits += 1
                    else:
                        if key in cached:
                            refused.add(key)
                        result = matcher.place(item)
                        written[key] = _entry(key, result)
                    placed[key] = result
                classifications.append(_classification(item, result))
                by_kind[item.kind][_count_key(result)] += 1
                review = needs_review(result, self._threshold)
                if item.kind is ItemKind.CARD:
                    below += review and result.position_id is not None
                    counted += not review and result.position_id is not None
                if review:
                    queued.append(
                        QueuedItem(
                            source_sha256=source.sha256,
                            kind=item.kind,
                            teams=source.teams,
                            headings=matcher.undecided_headings(item),
                            candidates=matcher.candidates(item),
                        )
                    )
        kept = {
            key: entry
            for key, entry in cached.items()
            if key not in refused
            and not (
                entry.topic_id == reading.topic_id and entry.taxonomy_version != taxonomy.taxonomy_version
            )
        }
        changed = bool(written) or len(kept) != len(cached)
        if changed:
            await self._store.replace(reading.caselist, [*kept.values(), *written.values()])
        queue = build_review_queue(queued, minimum_teams=self._minimum_review_teams)
        location = await self._store.write_review_queue(reading.caselist, reading.topic_id, queue.rows)
        return ClassificationRun(
            caselist=reading.caselist,
            topic_id=reading.topic_id,
            taxonomy_version=taxonomy.taxonomy_version,
            prompt_version=DETERMINISTIC_PROMPT_VERSION,
            classifications=tuple(classifications),
            review_queue=queue,
            review_queue_location=location,
            counts=ClassificationCounts(
                sources=len(reading.sources),
                sections=sum(by_kind[ItemKind.SECTION].values()),
                cards=sum(by_kind[ItemKind.CARD].values()),
                cards_by_method=dict(sorted(by_kind[ItemKind.CARD].items())),
                sections_by_method=dict(sorted(by_kind[ItemKind.SECTION].items())),
                cards_counted=counted,
                cards_below_threshold=below,
                lookups=len(placed),
                hits=hits,
                misses=len(written),
                refused_cached=len(refused),
                cache_written=changed,
            ),
        )


def _usable(entry: CachedClassification | None, taxonomy: Taxonomy) -> ClassificationResult | None:
    if entry is None:
        return None
    try:
        return checked_against(taxonomy, entry.result)
    except ValidationError:
        return None


def _entry(key: ClassificationKey, result: ClassificationResult) -> CachedClassification:
    return CachedClassification(
        topic_id=key.topic_id,
        taxonomy_version=key.taxonomy_version,
        override_digest=key.override_digest,
        prompt_version=key.prompt_version,
        item_fingerprint=key.item_fingerprint,
        result=result,
    )


def _classification(item: MatchItem, result: ClassificationResult) -> PositionClassification:
    return PositionClassification(
        item_id=item.item_id,
        item_kind=item.kind,
        source_sha256=item.source_sha256,
        first_element_index=item.first_element_index,
        **result.model_dump(),
    )

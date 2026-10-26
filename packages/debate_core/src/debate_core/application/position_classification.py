"""PositionClassificationService: one caselist's sections and cards placed under its topic's positions.

Stage one is `v1-e32-t02-position-classification`'s deterministic matcher. Stage two, when the service
is built with a :class:`~debate_core.application.landscape_model_stage.ModelClassificationStage`
(`v1-e32-t07`), asks a model about the cards stage one left unplaced or placed below the review
threshold, and only those: never a section, a card placed at or above the threshold, or one the coach
ruled names no position. Without a stage no model is called, and an item the matcher cannot place goes
to the review queue and is reported as Unclassified by `v1-e32-t03`.

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
4. with a model stage, looks each card that needs review up under its stage-one key with the stage's
   prompt version instead of `none`, and sends the stage only the keys not cached there, once per key.
   A MODEL result that places a card replaces stage one's for it; one that places nothing (a refused
   answer) is cached so the card is not asked about again under that prompt version, and stage one's
   result stands;
5. writes the cache back when anything changed, keeping every other topic's results and dropping this
   topic's results under any other taxonomy version and, with a model stage, under any other prompt
   version: a prompt version bump misses only MODEL results;
6. builds the review queue from the items nothing placed or placed below the threshold, and writes its
   CSV to the data directory.

It returns every item's :class:`~debate_core.domain.landscape_classification.PositionClassification`
for the report, with counts for the run's summary.
"""

from __future__ import annotations

import dataclasses
from collections import Counter
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final

from pydantic import ValidationError

from debate_core.application.landscape_model_stage import (
    ModelClassificationStage,
    ModelStageOutcome,
    scrubbed_cite,
)
from debate_core.application.landscape_seeding import SeedReading
from debate_core.application.ports.classification_store import (
    CachedClassification,
    ClassificationKey,
    ClassificationStore,
)
from debate_core.application.ports.taxonomy_repository import TaxonomyRepository
from debate_core.arguments.landscape.matcher import MatchItem, PositionMatcher, read_items
from debate_core.arguments.landscape.model_stage import ModelCandidate, places_nothing, sent_headings
from debate_core.arguments.landscape.review_queue import (
    DEFAULT_MINIMUM_REVIEW_TEAMS,
    DEFAULT_REVIEW_THRESHOLD,
    QueuedItem,
    ReviewQueue,
    build_review_queue,
    needs_review,
)
from debate_core.arguments.landscape.seeding import SeedCard, SeedSource
from debate_core.arguments.landscape.source_headings import CaselistNames
from debate_core.arguments.landscape.tag_scrub import card_tag, code_words
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
    "model_candidate",
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
    model_items: int = 0
    """Cards (one per fingerprint) the model was asked about in this run; in a dry run, would be."""
    model_calls: int = 0
    """Model calls this run made, repairs included."""
    model_candidates: int = 0
    """Cards (one per fingerprint) needing review with no MODEL result cached under this prompt version."""
    model_hits: int = 0
    """Cards (one per fingerprint) needing review whose MODEL result was cached under this prompt version."""
    model_held_back: int = 0
    """Candidates over the run's `max_model_items`, left for a later run."""
    model_refused: dict[str, int] = field(default_factory=dict[str, int])
    """Answers this run that placed nothing, by reason."""
    model_input_tokens: int = 0
    model_output_tokens: int = 0
    """Tokens of the calls whose answers were used, as the router reported them."""
    model_interrupted: str | None = None
    """The router error that stopped the model stage; None when it ran to the end or never ran."""

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
    """Places a caselist's items under its topic's positions: deterministically, then by model, cached."""

    def __init__(
        self,
        *,
        taxonomies: TaxonomyRepository,
        store: ClassificationStore,
        review_threshold: float = DEFAULT_REVIEW_THRESHOLD,
        minimum_review_teams: int = DEFAULT_MINIMUM_REVIEW_TEAMS,
        model_stage: ModelClassificationStage | None = None,
    ) -> None:
        if not 0.0 <= review_threshold <= 1.0:
            raise ValueError(f"the review threshold is between 0 and 1; got {review_threshold}")
        self._taxonomies = taxonomies
        self._store = store
        self._threshold = review_threshold
        self._minimum_review_teams = minimum_review_teams
        self._model_stage = model_stage

    async def classify(self, reading: SeedReading) -> ClassificationRun:
        taxonomy = self._taxonomies.taxonomy(reading.topic_id)
        matcher = PositionMatcher(taxonomy, self._taxonomies.overrides(reading.topic_id))
        names = CaselistNames(reading.caselist_names)
        cached = {entry.key: entry for entry in await self._store.read(reading.caselist)}
        placed: dict[ClassificationKey, ClassificationResult] = {}
        written: dict[ClassificationKey, CachedClassification] = {}
        refused: set[ClassificationKey] = set()
        hits = 0
        read: list[_Read] = []
        for source in reading.sources:
            cards = iter(source.cards)
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
                card = next(cards) if item.kind is ItemKind.CARD else None
                read.append(_Read(source, item, key, result, card))
        model = await self._model_stage_run(reading, taxonomy, names, read, cached, refused, written)
        classifications: list[PositionClassification] = []
        queued: list[QueuedItem] = []
        by_kind: dict[ItemKind, Counter[str]] = {ItemKind.SECTION: Counter(), ItemKind.CARD: Counter()}
        below = counted = 0
        for one in read:
            result = model.placement(one) or one.result
            item = one.item
            classifications.append(_classification(item, result))
            by_kind[item.kind][_count_key(result)] += 1
            review = needs_review(result, self._threshold)
            if item.kind is ItemKind.CARD:
                below += review and result.position_id is not None
                counted += not review and result.position_id is not None
            if review:
                queued.append(
                    QueuedItem(
                        source_sha256=one.source.sha256,
                        kind=item.kind,
                        teams=one.source.teams,
                        headings=matcher.undecided_headings(item),
                        tag_candidates=matcher.tag_candidates(item),
                    )
                )
        stage = self._model_stage
        kept = {
            key: entry
            for key, entry in cached.items()
            if key not in refused
            and not (
                entry.topic_id == reading.topic_id
                and (
                    entry.taxonomy_version != taxonomy.taxonomy_version
                    or (
                        stage is not None
                        and entry.prompt_version not in (DETERMINISTIC_PROMPT_VERSION, stage.prompt_version)
                    )
                )
            )
        }
        changed = bool(written) or len(kept) != len(cached)
        if changed:
            await self._store.replace(reading.caselist, [*kept.values(), *written.values()])
        queue = build_review_queue(
            queued, heading_candidates=matcher.heading_candidates, minimum_teams=self._minimum_review_teams
        )
        location = await self._store.write_review_queue(reading.caselist, reading.topic_id, queue.rows)
        outcome = model.outcome
        return ClassificationRun(
            caselist=reading.caselist,
            topic_id=reading.topic_id,
            taxonomy_version=taxonomy.taxonomy_version,
            prompt_version=stage.prompt_version if stage is not None else DETERMINISTIC_PROMPT_VERSION,
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
                misses=sum(1 for key in written if key.prompt_version == DETERMINISTIC_PROMPT_VERSION),
                refused_cached=sum(
                    1 for key in refused if key.prompt_version == DETERMINISTIC_PROMPT_VERSION
                ),
                cache_written=changed,
                model_items=outcome.sent,
                model_calls=outcome.calls,
                model_candidates=model.candidates,
                model_hits=model.hits,
                model_held_back=outcome.held_back,
                model_refused=dict(outcome.refused),
                model_input_tokens=outcome.input_tokens,
                model_output_tokens=outcome.output_tokens,
                model_interrupted=outcome.interrupted,
            ),
        )

    async def _model_stage_run(
        self,
        reading: SeedReading,
        taxonomy: Taxonomy,
        names: CaselistNames,
        read: Sequence[_Read],
        cached: Mapping[ClassificationKey, CachedClassification],
        refused: set[ClassificationKey],
        written: dict[ClassificationKey, CachedClassification],
    ) -> _ModelPlacements:
        """Stage two over the cards stage one left unplaced or below the threshold; nothing without a stage.

        A card's MODEL result is cached under its stage-one key with the stage's prompt version. One
        cached there is used as it is; the rest are asked about, once per key, and what comes back is
        added to `written`.
        """
        stage = self._model_stage
        if stage is None:
            return _ModelPlacements(None, {})
        found: dict[ClassificationKey, ClassificationResult] = {}
        candidates: dict[ClassificationKey, ModelCandidate] = {}
        shared: Counter[ClassificationKey] = Counter()
        hits = 0
        codes = code_words(reading.caselist_names)
        for one in read:
            if one.card is None or not needs_review(one.result, self._threshold):
                continue
            key = one.key._replace(prompt_version=stage.prompt_version)
            shared[key] += 1
            if key in found or key in candidates:
                continue
            result = _usable(cached.get(key), taxonomy)
            if result is not None:
                found[key] = result
                hits += 1
                continue
            if key in cached:
                refused.add(key)
            candidates[key] = model_candidate(one.source, one.item, one.card, names, codes)
        outcome = await stage.run(
            [dataclasses.replace(candidate, cards=shared[key]) for key, candidate in candidates.items()],
            taxonomy=taxonomy,
            caselist=reading.caselist,
            version=reading.version,
            names=names,
            codes=codes,
        )
        for key, candidate in candidates.items():
            result = outcome.results.get(candidate.fingerprint)
            if result is not None:
                found[key] = result
                written[key] = _entry(key, result)
        return _ModelPlacements(
            stage.prompt_version, found, outcome=outcome, candidates=len(candidates), hits=hits
        )


def model_candidate(
    source: SeedSource, item: MatchItem, card: SeedCard, names: CaselistNames, codes: Collection[str]
) -> ModelCandidate:
    """`card` of `source`, read by stage one as `item`, as the model stage is asked about it.

    Its headings lose team-code words, and its tag and short cite are read as words without the
    disclosing teams' names, the caselist's schools or any team code. The excerpt is cut later, from the
    evidence the stage reads for the cards it keeps.
    """
    own = tuple(name for team in source.teams for name in team.names if name.strip())
    return ModelCandidate(
        fingerprint=item.fingerprint,
        source_sha256=source.sha256,
        first_element_index=card.first_element_index or 0,
        headings=sent_headings(item.headings, codes),
        tag=card_tag(card.tag, own, names, codes),
        short_cite=scrubbed_cite(card.short_cite, own, names, codes),
        own_names=own,
    )


@dataclass(frozen=True, slots=True)
class _Read:
    """One item as stage one read and placed it, with its stored card when it is one."""

    source: SeedSource
    item: MatchItem
    key: ClassificationKey
    result: ClassificationResult
    card: SeedCard | None


_NOTHING_ASKED: Final = ModelStageOutcome(results={}, sent=0, held_back=0)


@dataclass(frozen=True, slots=True)
class _ModelPlacements:
    """What stage two found for this run's cards, by their MODEL keys."""

    prompt_version: str | None
    results: Mapping[ClassificationKey, ClassificationResult]
    outcome: ModelStageOutcome = _NOTHING_ASKED
    candidates: int = 0
    hits: int = 0

    def placement(self, one: _Read) -> ClassificationResult | None:
        """The MODEL result that places `one`'s card, or None: stage one's result stands."""
        if self.prompt_version is None or one.card is None:
            return None
        result = self.results.get(one.key._replace(prompt_version=self.prompt_version))
        if result is None or places_nothing(result):
            return None
        return result


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

"""The model stage measured against cards a coach labelled (`v1-e32-t07` ac4).

`debate-research landscape evaluate` is a thin adapter over :class:`LandscapeModelEvaluationService`.
One evaluation, for one caselist (one format) at its newest weekly snapshot unless one is named:

1. **reads the coach's labels**: `v1-e32-t21`'s coach sample, the CSV the coach filled (`sample_row`,
   `position`) and the rows file written beside it (`sample_row` to item id), so a card the coach labelled
   for t21 is labelled once for both (:func:`read_coach_sample`). A label is a position id of the topic's
   taxonomy, `none` for a card that argues no position, or `unsure` or blank, which is not scored;
2. **reads each labelled card** from the parsed store exactly as a landscape run reads it
   (:func:`~debate_core.application.position_classification.model_candidate`), and asks the model stage
   about all of them, whatever stage one made of them, under the run's model mode: `replay` serves the
   cassettes recorded on this machine, `record` (the operator's, once, after the policy's open question 4
   is answered) makes the calls and writes them;
3. **scores** the answers (:class:`FormatEvaluation`): of the cards a run would count (a MODEL result at
   or above the review threshold), how many name the coach's position. A card the coach labelled `none`
   counts against the model when it is placed;
4. **scans** what was sent, and every cassette of the prompt, for the caselist's schools, team codes and
   the disclosing teams' tournaments (:func:`~debate_core.arguments.landscape.model_stage.name_scan`).

Nothing is cached and no report is written: the evaluation measures the stage and changes no placement.
Every count is a number; no tag, heading or label text is returned or logged.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Final, TextIO, cast

from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.errors import DomainError, ProviderError
from debate_core.application.landscape_model_stage import (
    CLASSIFY_POSITION_PROMPT_ID,
    BatchRecord,
    ModelClassificationStage,
    ModelStageInterrupted,
    ModelStageOutcome,
)
from debate_core.application.landscape_seeding import SeedReading, read_seed_sources
from debate_core.application.landscape_staleness import LandscapeStalenessCheck
from debate_core.application.ports.evidence_store import EvidenceObjectStore
from debate_core.application.ports.parsed_store import ParsedStore
from debate_core.application.ports.suppression import SuppressionList
from debate_core.application.ports.taxonomy_repository import TaxonomyRepository
from debate_core.application.position_classification import model_candidate
from debate_core.arguments.landscape.evaluation_breakdown import (
    CardBreakdown,
    CardOutcome,
    Score,
    StratumScore,
    card_outcome,
    deterministic_placement,
    label_kind,
    model_set_score,
    outcome_counts,
    related,
    stratum_scores,
)
from debate_core.arguments.landscape.matcher import MatchItem, PositionMatcher, read_items
from debate_core.arguments.landscape.model_stage import (
    ModelCandidate,
    NameScan,
    name_scan,
    places_nothing,
    prompt_variables,
    refusal_reason,
)
from debate_core.arguments.landscape.review_queue import DEFAULT_REVIEW_THRESHOLD
from debate_core.arguments.landscape.scan_hits import (
    ScanHit,
    ScanNames,
    cassette_hits,
    input_batch_hits,
    repair_cassette_hits,
)
from debate_core.arguments.landscape.source_headings import CaselistNames
from debate_core.arguments.landscape.tag_scrub import code_words
from debate_core.domain.landscape import Taxonomy
from debate_core.domain.landscape_classification import ItemKind, OverrideRules

__all__ = [
    "BATCH_ANSWERED",
    "BATCH_REFUSED",
    "BATCH_REPAIRED",
    "NO_POSITION_LABEL",
    "TARGET_ACCURACY",
    "UNSURE_LABEL",
    "BatchBreakdown",
    "EvaluationBreakdown",
    "EvaluationRefused",
    "FormatEvaluation",
    "LabelledAnswers",
    "LabelledCard",
    "LandscapeModelEvaluationService",
    "ask_labelled_cards",
    "break_down_labelled_cards",
    "evaluate_labelled_cards",
    "read_coach_sample",
    "read_sample_populations",
    "score_labelled_answers",
]

TARGET_ACCURACY: Final = 0.85
"""ac4's bar: the share of counted MODEL placements naming the coach's position, per format."""

NO_POSITION_LABEL: Final = "none"
"""The coach's label for a card that argues no position."""

UNSURE_LABEL: Final = "unsure"
"""The coach's label for a card they could not place: not scored, as a blank is not."""


class EvaluationRefused(DomainError):
    """The labels, the caselist or the snapshot cannot be evaluated: named by row or value, never by text."""


@dataclass(frozen=True, slots=True)
class LabelledCard:
    """One card the coach labelled: its item id and their position id or `none`."""

    item_id: str
    label: str
    sample_row: int | None = None
    """Its row in the coach's file, which names it to the coach and the PM without its text."""
    stratum: str | None = None
    """The stratum `v1-e32-t21` drew it from, when the rows file says."""


@dataclass(frozen=True, slots=True)
class FormatEvaluation:
    """One format's score: what was labelled, found, asked, placed and right, and what the scans found."""

    caselist: str
    event: str
    topic_id: str
    taxonomy_version: str
    prompt_version: str
    snapshot: date | None
    labelled: int
    """Labelled cards scored: a position id or `none`."""
    found: int
    """Of those, the cards the store still holds; a card a removal has reached since is not found."""
    asked: int
    """Distinct fingerprints the model was asked about."""
    calls: int
    counted: int
    """Found cards the model placed at or above the review threshold: what a report would count."""
    correct: int
    """Of the counted, those naming the coach's position."""
    placed_below_threshold: int
    placed_labelled_none: int
    """Counted cards the coach labelled `none`: each is wrong."""
    refused: dict[str, int] = field(default_factory=dict[str, int])
    input_tokens: int = 0
    output_tokens: int = 0
    sent: NameScan = field(default_factory=lambda: NameScan(texts=0))
    """The scan of every batch's prompt input as sent."""
    cassettes: NameScan = field(default_factory=lambda: NameScan(texts=0))
    """The scan of every cassette of the prompt on this machine."""
    interrupted_by: ProviderError | None = None
    """The router error that stopped the stage partway; None when it ran to the end."""
    unanswered: int = 0
    """Cards (fingerprints) a stop left unasked; 0 when the stage ran to the end."""

    @property
    def interrupted(self) -> str | None:
        """The class of :attr:`interrupted_by`; None when the stage ran to the end."""
        return type(self.interrupted_by).__name__ if self.interrupted_by is not None else None

    @property
    def stopped(self) -> ModelStageInterrupted | None:
        """The stop as a landscape run raises it, so the CLI judges both commands alike (`v1-e32-t33`)."""
        if self.interrupted_by is None:
            return None
        return ModelStageInterrupted(self.interrupted_by, sent=self.asked, unanswered=self.unanswered)

    @property
    def accuracy(self) -> float | None:
        return self.correct / self.counted if self.counted else None

    @property
    def meets_target(self) -> bool:
        accuracy = self.accuracy
        return accuracy is not None and accuracy >= TARGET_ACCURACY


def read_coach_sample(sample: TextIO, rows: Iterable[str], taxonomy: Taxonomy) -> tuple[LabelledCard, ...]:
    """The coach's labels, joined to their cards: `sample` is the filled CSV, `rows` the file beside it.

    `rows` is JSON lines: a header line, then one object per card with its `sample_row` and `item_id`, as
    `v1-e32-t21` writes them. A label naming no active position of `taxonomy`, or a row the rows file does
    not have, is refused by its row number.
    """
    by_row: dict[int, str] = {}
    strata: dict[int, str] = {}
    for line in rows:
        if not line.strip():
            continue
        loaded: object = json.loads(line)
        if isinstance(loaded, dict):
            data = cast(dict[str, object], loaded)
            row, item_id, stratum = data.get("sample_row"), data.get("item_id"), data.get("stratum")
            if isinstance(row, int) and isinstance(item_id, str):
                by_row[row] = item_id
                if isinstance(stratum, str):
                    strata[row] = stratum
    reader = csv.DictReader(sample)
    if reader.fieldnames is None or not {"sample_row", "position"} <= set(reader.fieldnames):
        raise EvaluationRefused("the coach's sample needs its sample_row and position columns")
    active = {position.id for position in taxonomy.active_positions}
    labelled: list[LabelledCard] = []
    for line in reader:
        label = (line.get("position") or "").strip()
        if not label or label.casefold() == UNSURE_LABEL:
            continue
        row = int(line["sample_row"])
        if row not in by_row:
            raise EvaluationRefused(f"row {row} of the coach's sample is not in its rows file")
        if label.casefold() == NO_POSITION_LABEL:
            label = NO_POSITION_LABEL
        elif label not in active:
            raise EvaluationRefused(
                f"row {row} names a position that is not an active id of {taxonomy.topic_id} "
                f"{taxonomy.taxonomy_version}"
            )
        labelled.append(
            LabelledCard(item_id=by_row[row], label=label, sample_row=row, stratum=strata.get(row))
        )
    return tuple(labelled)


def read_sample_populations(rows: Iterable[str]) -> dict[str, int]:
    """The unplaced cards each stratum of the sample was drawn from, from the rows file's header line.

    Empty for a rows file whose header has no `populations` (a sample not drawn by strata).
    """
    header = next((line for line in rows if line.strip()), None)
    loaded: object = json.loads(header) if header is not None else None
    populations = cast(dict[str, object], loaded).get("populations") if isinstance(loaded, dict) else None
    if not isinstance(populations, dict):
        return {}
    return {
        str(name): count
        for name, count in cast(dict[object, object], populations).items()
        if isinstance(count, int)
    }


@dataclass(frozen=True, slots=True)
class LabelledAnswers:
    """What the stage was asked about the labelled cards, and answered (:func:`ask_labelled_cards`)."""

    labels: Mapping[str, str]
    """Each labelled card's label, by item id."""
    items: Mapping[str, MatchItem] = field(repr=False)
    """Each labelled card the reading holds, as stage one reads it, by item id: the found cards."""
    candidates: Mapping[str, ModelCandidate] = field(repr=False)
    """One candidate per fingerprint of the found cards: what the stage was asked about."""
    outcome: ModelStageOutcome
    names: CaselistNames = field(repr=False)
    tournaments: frozenset[str] = field(repr=False)
    """The disclosing teams' names, every source's: the scan's other names."""


async def ask_labelled_cards(
    reading: SeedReading,
    labelled: Iterable[LabelledCard],
    stage: ModelClassificationStage,
    taxonomy: Taxonomy,
) -> LabelledAnswers:
    """Ask `stage` about every labelled card `reading` holds, once per fingerprint, as a run would ask."""
    labels = {one.item_id: one.label for one in labelled}
    names = CaselistNames(reading.caselist_names)
    codes = code_words(reading.caselist_names)
    candidates: dict[str, ModelCandidate] = {}
    items: dict[str, MatchItem] = {}
    tournaments: set[str] = set()
    for source in reading.sources:
        tournaments |= {name for team in source.teams for name in team.names}
        if not any(item_id.startswith(f"{source.sha256}:") for item_id in labels):
            continue
        cards = iter(source.cards)
        for item in read_items(source, names):
            if item.kind is not ItemKind.CARD:
                continue
            card = next(cards)
            if item.item_id in labels:
                items[item.item_id] = item
                candidates.setdefault(item.fingerprint, model_candidate(source, item, card, names, codes))
    outcome = await stage.run(
        list(candidates.values()),
        taxonomy=taxonomy,
        caselist=reading.caselist,
        version=reading.version,
        names=names,
        codes=codes,
    )
    return LabelledAnswers(
        labels=labels,
        items=items,
        candidates=candidates,
        outcome=outcome,
        names=names,
        tournaments=frozenset(tournaments),
    )


def score_labelled_answers(
    reading: SeedReading,
    taxonomy: Taxonomy,
    asked: LabelledAnswers,
    *,
    prompt_version: str,
    review_threshold: float = DEFAULT_REVIEW_THRESHOLD,
    cassettes: Iterable[str] = (),
    snapshot: date | None = None,
) -> FormatEvaluation:
    """The evaluation's score of `asked`, and the scans of what was sent and of `cassettes`."""
    labels, outcome = asked.labels, asked.outcome
    counted = correct = below = labelled_none = 0
    for item_id, item in asked.items.items():
        result = outcome.results.get(item.fingerprint)
        if result is None or places_nothing(result):
            continue
        if result.confidence < review_threshold:
            below += 1
            continue
        counted += 1
        correct += result.position_id == labels[item_id]
        labelled_none += labels[item_id] == NO_POSITION_LABEL
    refused = Counter(outcome.refused)
    return FormatEvaluation(
        caselist=reading.caselist,
        event=taxonomy.event.value if taxonomy.event is not None else "",
        topic_id=taxonomy.topic_id,
        taxonomy_version=taxonomy.taxonomy_version,
        prompt_version=prompt_version,
        snapshot=snapshot,
        labelled=len(labels),
        found=len(asked.items),
        asked=outcome.sent,
        calls=outcome.calls,
        counted=counted,
        correct=correct,
        placed_below_threshold=below,
        placed_labelled_none=labelled_none,
        refused=dict(sorted(refused.items())),
        input_tokens=outcome.input_tokens,
        output_tokens=outcome.output_tokens,
        sent=name_scan(outcome.sent_inputs, reading.caselist_names, asked.tournaments),
        cassettes=name_scan(cassettes, reading.caselist_names, asked.tournaments),
        interrupted_by=outcome.interrupted_by,
        unanswered=len(asked.candidates) - outcome.sent,
    )


async def evaluate_labelled_cards(
    reading: SeedReading,
    taxonomy: Taxonomy,
    labelled: Iterable[LabelledCard],
    stage: ModelClassificationStage,
    *,
    review_threshold: float = DEFAULT_REVIEW_THRESHOLD,
    cassette_texts: Callable[[], Iterable[str]] = lambda: (),
    snapshot: date | None = None,
) -> FormatEvaluation:
    """Ask `stage` about every labelled card `reading` holds, and score the answers against the labels.

    `cassette_texts` is read after the stage has run, so a recording run scans what it recorded.
    """
    asked = await ask_labelled_cards(reading, labelled, stage, taxonomy)
    return score_labelled_answers(
        reading,
        taxonomy,
        asked,
        prompt_version=stage.prompt_version,
        review_threshold=review_threshold,
        cassettes=cassette_texts(),
        snapshot=snapshot,
    )


BATCH_ANSWERED: Final = "answered"
BATCH_REPAIRED: Final = "repaired"
BATCH_REFUSED: Final = "refused"


@dataclass(frozen=True, slots=True)
class BatchBreakdown:
    """One batch of the evaluation: its cards, its calls, and what the structured-output guard did."""

    number: int
    """From 1, in the order asked."""
    cards: int
    calls: int
    outcome: str
    """:data:`BATCH_ANSWERED` first time, :data:`BATCH_REPAIRED` (the repair's answer was used), or
    :data:`BATCH_REFUSED` (the answer and its repair both failed: every card placed nothing)."""
    problems: Mapping[str, int] = field(default_factory=dict[str, int])
    """The failed attempts' reported problems by type (`string_too_long`, `missing_item`): no values."""
    error_count: int = 0
    """How many problems the failed attempts had in all, reported or not."""


@dataclass(frozen=True, slots=True)
class EvaluationBreakdown:
    """The evaluation, and every labelled card's outcome beside stage one's placement (`v1-e32-t39`).

    The scan hits are for the operator's terminal only, and are withheld from the `repr`.
    """

    evaluation: FormatEvaluation
    cards: tuple[CardBreakdown, ...]
    batches: tuple[BatchBreakdown, ...]
    populations: Mapping[str, int] = field(default_factory=dict[str, int])
    """The unplaced cards each stratum of the sample was drawn from; empty when the rows file has none."""
    sent_hits: tuple[ScanHit, ...] = field(default=(), repr=False)
    """The scan's hits in each batch's prompt input as sent."""
    cassette_hits: tuple[ScanHit, ...] = field(default=(), repr=False)
    """Its hits in each cassette of the prompt the evaluation's scan read."""
    repair_hits: tuple[ScanHit, ...] = field(default=(), repr=False)
    """Its hits in this prompt's repair cassettes filed under the caselist, which that scan does not read."""
    repair_cassettes: int = 0
    """How many repair cassettes those are."""

    @property
    def outcomes(self) -> dict[str, int]:
        return outcome_counts(self.cards)

    @property
    def model_set(self) -> Score:
        return model_set_score(self.cards)

    @property
    def strata(self) -> tuple[StratumScore, ...]:
        return stratum_scores(self.cards, self.populations)


async def break_down_labelled_cards(
    reading: SeedReading,
    taxonomy: Taxonomy,
    overrides: OverrideRules,
    labelled: Sequence[LabelledCard],
    stage: ModelClassificationStage,
    *,
    review_threshold: float = DEFAULT_REVIEW_THRESHOLD,
    cassette_texts: Callable[[], Iterable[str]] = lambda: (),
    repair_cassette_texts: Callable[[], Iterable[str]] = lambda: (),
    populations: Mapping[str, int] | None = None,
    snapshot: date | None = None,
) -> EvaluationBreakdown:
    """:func:`evaluate_labelled_cards`, and each card's outcome, batch and stage-one placement.

    The stage is asked exactly as the evaluation asks it, so a replay finds the same cassettes. Stage one
    places each found card with `taxonomy` and the coach's `overrides`, as a landscape run does.
    """
    asked = await ask_labelled_cards(reading, labelled, stage, taxonomy)
    cassettes = list(cassette_texts())
    evaluation = score_labelled_answers(
        reading,
        taxonomy,
        asked,
        prompt_version=stage.prompt_version,
        review_threshold=review_threshold,
        cassettes=cassettes,
        snapshot=snapshot,
    )
    outcome = asked.outcome
    matcher = PositionMatcher(taxonomy, overrides)
    batch_of = {
        fingerprint: number
        for number, record in enumerate(outcome.batches, start=1)
        for fingerprint in record.fingerprints
    }
    cards: list[CardBreakdown] = []
    for item_id, one in {card.item_id: card for card in labelled}.items():
        cards.append(
            _card_breakdown(
                one,
                asked.items.get(item_id),
                outcome,
                taxonomy,
                matcher,
                batch_of,
                threshold=review_threshold,
            )
        )
    names = ScanNames.of(
        reading.caselist_names,
        asked.tournaments,
        taxonomy_text=str(prompt_variables(taxonomy, ())["positions"]),
    )
    repairs = [
        text for text in repair_cassette_texts() if _repairs(text, reading.caselist, stage.prompt_version)
    ]
    return EvaluationBreakdown(
        evaluation=evaluation,
        cards=tuple(cards),
        batches=tuple(_batch_breakdown(number, one) for number, one in enumerate(outcome.batches, start=1)),
        populations=dict(populations or {}),
        sent_hits=tuple(
            hit
            for number, text in enumerate(outcome.sent_inputs, start=1)
            for hit in input_batch_hits(f"input batch {number}", text, names)
        ),
        cassette_hits=tuple(
            hit
            for number, text in enumerate(cassettes, start=1)
            for hit in cassette_hits(f"cassette {number}", text, names)
        ),
        repair_hits=tuple(
            hit
            for number, text in enumerate(repairs, start=1)
            for hit in repair_cassette_hits(f"repair cassette {number}", text, names)
        ),
        repair_cassettes=len(repairs),
    )


def _card_breakdown(
    labelled: LabelledCard,
    item: MatchItem | None,
    outcome: ModelStageOutcome,
    taxonomy: Taxonomy,
    matcher: PositionMatcher,
    batch_of: Mapping[str, int],
    *,
    threshold: float,
) -> CardBreakdown:
    kind = label_kind(taxonomy, labelled.label)
    if item is None:
        return CardBreakdown(
            label=labelled.label,
            label_kind=kind,
            outcome=CardOutcome.NOT_FOUND,
            sample_row=labelled.sample_row,
            stratum=labelled.stratum,
        )
    result = outcome.results.get(item.fingerprint)
    found = card_outcome(taxonomy, labelled.label, result, threshold=threshold)
    answered = result is not None and not places_nothing(result)
    answer = result.position_id if result is not None and answered else None
    reason = refusal_reason(result) if result is not None and found is CardOutcome.REFUSED else None
    return CardBreakdown(
        label=labelled.label,
        label_kind=kind,
        outcome=found,
        refusal=reason.value if reason is not None else None,
        answer=answer,
        confidence=result.confidence if result is not None and answered else None,
        deterministic=deterministic_placement(matcher.place(item), threshold=threshold),
        sample_row=labelled.sample_row,
        stratum=labelled.stratum,
        batch=batch_of.get(item.fingerprint),
        related=found in (CardOutcome.WRONG_POSITION_SAME_KIND, CardOutcome.WRONG_KIND)
        and answer is not None
        and related(taxonomy, answer, labelled.label),
    )


def _batch_breakdown(number: int, record: BatchRecord) -> BatchBreakdown:
    failed = [attempt for attempt in record.attempts if not attempt.valid]
    if record.refused:
        verdict = BATCH_REFUSED
    elif record.repaired:
        verdict = BATCH_REPAIRED
    else:
        verdict = BATCH_ANSWERED
    return BatchBreakdown(
        number=number,
        cards=len(record.fingerprints),
        calls=len(record.attempts),
        outcome=verdict,
        problems=dict(sorted(Counter(problem.type for one in failed for problem in one.problems).items())),
        error_count=sum(one.error_count for one in failed),
    )


def _repairs(cassette: str, caselist: str, prompt_version: str) -> bool:
    """Whether `cassette` is a `model.repair` call for this prompt and version, filed under `caselist`."""
    try:
        loaded: object = json.loads(cassette)
    except json.JSONDecodeError:
        return False
    if not isinstance(loaded, dict):
        return False
    document = cast(dict[str, Any], loaded)
    caselists = document.get("caselists")
    try:
        failed = document["request"]["prompt"]["variables"]["failed_prompt"]
    except (KeyError, TypeError):
        return False
    return (
        isinstance(caselists, list)
        and caselist in caselists
        and failed == f"{CLASSIFY_POSITION_PROMPT_ID}@{prompt_version}"
    )


type EvaluationStageFactory = Callable[[int], ModelClassificationStage]
"""Builds the model stage for an evaluation, asking about at most the given number of cards."""


class LandscapeModelEvaluationService:
    """Resolves a caselist's snapshot and topic, reads its sources, and evaluates the stage on the labels."""

    def __init__(
        self,
        *,
        taxonomies: TaxonomyRepository,
        parsed_store: ParsedStore,
        local: LocalEvidence,
        suppression: SuppressionList,
        objects: EvidenceObjectStore,
        stage: EvaluationStageFactory,
        cassette_texts: Callable[[], Iterable[str]],
        repair_cassette_texts: Callable[[], Iterable[str]] = lambda: (),
        review_threshold: float = DEFAULT_REVIEW_THRESHOLD,
    ) -> None:
        self._taxonomies = taxonomies
        self._parsed = parsed_store
        self._local = local
        self._suppression = suppression
        self._objects = objects
        self._stage = stage
        self._cassette_texts = cassette_texts
        self._repair_cassette_texts = repair_cassette_texts
        self._threshold = review_threshold

    async def evaluate(
        self, caselist: str, sample: TextIO, rows: Iterable[str], *, snapshot: date | None = None
    ) -> FormatEvaluation:
        prepared = await self._prepared(caselist, sample, rows, snapshot)
        return await evaluate_labelled_cards(
            prepared.reading,
            prepared.taxonomy,
            prepared.labelled,
            self._stage(len(prepared.labelled)),
            review_threshold=self._threshold,
            cassette_texts=self._cassette_texts,
            snapshot=prepared.through,
        )

    async def break_down(
        self, caselist: str, sample: TextIO, rows: Iterable[str], *, snapshot: date | None = None
    ) -> EvaluationBreakdown:
        """:meth:`evaluate`, broken down card by card, with the scan's hits for the operator's terminal."""
        lines = list(rows)
        prepared = await self._prepared(caselist, sample, lines, snapshot)
        return await break_down_labelled_cards(
            prepared.reading,
            prepared.taxonomy,
            self._taxonomies.overrides(prepared.reading.topic_id),
            prepared.labelled,
            self._stage(len(prepared.labelled)),
            review_threshold=self._threshold,
            cassette_texts=self._cassette_texts,
            repair_cassette_texts=self._repair_cassette_texts,
            populations=read_sample_populations(lines),
            snapshot=prepared.through,
        )

    async def _prepared(
        self, caselist: str, sample: TextIO, rows: Iterable[str], snapshot: date | None
    ) -> _Prepared:
        through = snapshot or await LandscapeStalenessCheck(
            objects=self._objects, run_log=None
        ).newest_snapshot(caselist)
        if through is None:
            raise EvaluationRefused(f"{caselist} has no weekly snapshot on this machine")
        resolved = self._taxonomies.resolve(caselist, through)
        if resolved is None or resolved.taxonomy is None:
            raise EvaluationRefused(
                f"topics.yaml puts {caselist} on {through.isoformat()} on no topic with a taxonomy"
            )
        taxonomy = resolved.taxonomy
        labelled = read_coach_sample(sample, rows, taxonomy)
        if not labelled:
            raise EvaluationRefused("the coach's sample has no labelled row to score")
        reading = await read_seed_sources(
            store=self._parsed,
            local=self._local,
            suppression=self._suppression,
            topic=resolved.topic,
            caselist=caselist,
            through=through,
        )
        return _Prepared(reading=reading, taxonomy=taxonomy, labelled=labelled, through=through)


@dataclass(frozen=True, slots=True)
class _Prepared:
    """A caselist's snapshot resolved, its sources read, and the coach's labels joined to them."""

    reading: SeedReading = field(repr=False)
    taxonomy: Taxonomy
    labelled: tuple[LabelledCard, ...]
    through: date

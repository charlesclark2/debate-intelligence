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
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date
from typing import Final, TextIO, cast

from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.errors import DomainError, ProviderError
from debate_core.application.landscape_model_stage import ModelClassificationStage, ModelStageInterrupted
from debate_core.application.landscape_seeding import SeedReading, read_seed_sources
from debate_core.application.landscape_staleness import LandscapeStalenessCheck
from debate_core.application.ports.evidence_store import EvidenceObjectStore
from debate_core.application.ports.parsed_store import ParsedStore
from debate_core.application.ports.suppression import SuppressionList
from debate_core.application.ports.taxonomy_repository import TaxonomyRepository
from debate_core.application.position_classification import model_candidate
from debate_core.arguments.landscape.matcher import read_items
from debate_core.arguments.landscape.model_stage import ModelCandidate, NameScan, name_scan, places_nothing
from debate_core.arguments.landscape.review_queue import DEFAULT_REVIEW_THRESHOLD
from debate_core.arguments.landscape.source_headings import CaselistNames
from debate_core.arguments.landscape.tag_scrub import code_words
from debate_core.domain.landscape import Taxonomy
from debate_core.domain.landscape_classification import ItemKind

__all__ = [
    "NO_POSITION_LABEL",
    "TARGET_ACCURACY",
    "UNSURE_LABEL",
    "EvaluationRefused",
    "FormatEvaluation",
    "LabelledCard",
    "LandscapeModelEvaluationService",
    "evaluate_labelled_cards",
    "read_coach_sample",
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
        """The stop as a landscape run raises it, so the CLI judges both commands by one rule (`v1-e32-t33`)."""
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
    for line in rows:
        if not line.strip():
            continue
        loaded: object = json.loads(line)
        if isinstance(loaded, dict):
            data = cast(dict[str, object], loaded)
            row, item_id = data.get("sample_row"), data.get("item_id")
            if isinstance(row, int) and isinstance(item_id, str):
                by_row[row] = item_id
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
        labelled.append(LabelledCard(item_id=by_row[row], label=label))
    return tuple(labelled)


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
    labels = {one.item_id: one.label for one in labelled}
    names = CaselistNames(reading.caselist_names)
    codes = code_words(reading.caselist_names)
    candidates: dict[str, ModelCandidate] = {}
    fingerprint_of: dict[str, str] = {}
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
                fingerprint_of[item.item_id] = item.fingerprint
                candidates.setdefault(item.fingerprint, model_candidate(source, item, card, names, codes))
    outcome = await stage.run(
        list(candidates.values()),
        taxonomy=taxonomy,
        caselist=reading.caselist,
        version=reading.version,
        names=names,
        codes=codes,
    )
    counted = correct = below = labelled_none = 0
    for item_id, fingerprint in fingerprint_of.items():
        result = outcome.results.get(fingerprint)
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
        prompt_version=stage.prompt_version,
        snapshot=snapshot,
        labelled=len(labels),
        found=len(fingerprint_of),
        asked=outcome.sent,
        calls=outcome.calls,
        counted=counted,
        correct=correct,
        placed_below_threshold=below,
        placed_labelled_none=labelled_none,
        refused=dict(sorted(refused.items())),
        input_tokens=outcome.input_tokens,
        output_tokens=outcome.output_tokens,
        sent=name_scan(outcome.sent_inputs, reading.caselist_names, tournaments),
        cassettes=name_scan(cassette_texts(), reading.caselist_names, tournaments),
        interrupted_by=outcome.interrupted_by,
        unanswered=len(candidates) - outcome.sent,
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
        review_threshold: float = DEFAULT_REVIEW_THRESHOLD,
    ) -> None:
        self._taxonomies = taxonomies
        self._parsed = parsed_store
        self._local = local
        self._suppression = suppression
        self._objects = objects
        self._stage = stage
        self._cassette_texts = cassette_texts
        self._threshold = review_threshold

    async def evaluate(
        self, caselist: str, sample: TextIO, rows: Iterable[str], *, snapshot: date | None = None
    ) -> FormatEvaluation:
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
        return await evaluate_labelled_cards(
            reading,
            taxonomy,
            labelled,
            self._stage(len(labelled)),
            review_threshold=self._threshold,
            cassette_texts=self._cassette_texts,
            snapshot=through,
        )

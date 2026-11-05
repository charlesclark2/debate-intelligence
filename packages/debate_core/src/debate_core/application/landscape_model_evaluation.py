"""The model stage measured against cards a coach labelled (`v1-e32-t07` ac4).

`debate-research landscape evaluate` is a thin adapter over :class:`LandscapeModelEvaluationService`.
One evaluation, for one caselist (one format) at its newest weekly snapshot unless one is named:

1. **reads the coach's labels**: `v1-e32-t21`'s coach sample, the CSV the coach filled (`sample_row`,
   `position`) and the rows file written beside it (`sample_row` to item id), so a card the coach labelled
   for t21 is labelled once for both (:func:`read_coach_sample`). A label is a position id of the topic's
   taxonomy, `none` for a card that argues no position, or `unsure` or blank, which is not scored. An
   optional `also` column names a second position the coach accepts (`v1-e32-t41`);
2. **reads each labelled card** from the parsed store exactly as a landscape run reads it
   (:func:`~debate_core.application.position_classification.model_candidate`), and asks the model stage
   about all of them, whatever stage one made of them, under the run's model mode: `replay` serves the
   cassettes recorded on this machine, `record` (the operator's, once, after the policy's open question 4
   is answered) makes the calls and writes them;
3. **scores** the answers (:class:`FormatEvaluation`): of the cards a run would count (a MODEL result at
   or above the review threshold), how many name the coach's position. A card the coach labelled `none`
   counts against the model when it is placed. Scored again as students meet it (`v1-e32-t43`), each
   card stage one places surely, with the taxonomy and the coach's overrides, on that placement and every
   other on the model's answer: the pipeline's accuracy is what the bar reads;
4. **scans** what was sent, every cassette of the prompt version it ran, and every repair cassette of that
   version filed under the caselist, for the caselist's schools, team codes and the disclosing teams'
   tournaments (:func:`~debate_core.arguments.landscape.model_stage.name_scan`): their values, not their
   JSON keys, and without the committed positions text a cassette holds (`v1-e32-t40`). A text whose
   every hit is marked a JSON key's name or a taxonomy word leaves its scan clean, and is counted as set
   aside (:func:`~debate_core.arguments.landscape.scan_hits.marked_scan`, `v1-e32-t44`).

Nothing is cached and no report is written: the evaluation measures the stage and changes no placement.
Every count is a number; no tag, heading or label text is returned or logged.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
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
    ANSWERS_PREFIX,
    CardBreakdown,
    CardOutcome,
    GenericAnswers,
    LabelledScore,
    Score,
    StratumScore,
    card_outcome,
    deterministic_placement,
    generic_answer_counts,
    generic_positions,
    label_kind,
    labelled_as,
    model_alone_score,
    model_set_score,
    outcome_counts,
    pipeline_score,
    related,
    scored_stance,
    stratum_scores,
)
from debate_core.arguments.landscape.matcher import MatchItem, PositionMatcher, read_items
from debate_core.arguments.landscape.model_stage import (
    ModelCandidate,
    NameScan,
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
    marked_scan,
    repair_cassette_hits,
)
from debate_core.arguments.landscape.source_headings import CaselistNames
from debate_core.arguments.landscape.tag_scrub import DisclosedNames, code_words
from debate_core.domain.landscape import Taxonomy, Topic
from debate_core.domain.landscape_classification import ItemKind, OverrideRules, Stance

__all__ = [
    "BATCH_ANSWERED",
    "BATCH_REFUSED",
    "BATCH_REPAIRED",
    "BAR_READS",
    "NO_POSITION_LABEL",
    "SECOND_LABEL_COLUMN",
    "TARGET_ACCURACY",
    "UNSURE_LABEL",
    "BatchBreakdown",
    "CoachLabel",
    "CoachSampleCheck",
    "EvaluationBreakdown",
    "EvaluationRefused",
    "FormatEvaluation",
    "LabelledAnswers",
    "LabelledCard",
    "LandscapeModelEvaluationService",
    "SampleSides",
    "ask_labelled_cards",
    "break_down_labelled_cards",
    "coach_label",
    "coach_sample_counts",
    "committed_positions",
    "evaluate_labelled_cards",
    "labelled_card_breakdowns",
    "read_coach_sample",
    "read_sample_populations",
    "row_labels",
    "scanned_cassettes",
    "scanned_repairs",
    "score_labelled_answers",
    "stance_counts",
]

TARGET_ACCURACY: Final = 0.85
"""ac4's bar: the share of the counted placements naming the coach's position, per format, as students meet
them: stage one's sure placements and the model's for the rest (the PM's ruling for `v1-e32-t43`; until then
the model's alone)."""

BAR_READS: Final = "pipeline"
"""Which score :data:`TARGET_ACCURACY` is read against: :attr:`FormatEvaluation.pipeline`'s."""

NO_POSITION_LABEL: Final = "none"
"""The coach's label for a card that argues no position."""

UNSURE_LABEL: Final = "unsure"
"""The coach's label for a card they could not place: not scored, as a blank is not."""

SECOND_LABEL_COLUMN: Final = "also"
"""The coach sample's optional column naming a second position the coach accepts for a card (`v1-e32-t41`)."""


_NOTHING_SCORED: Final = LabelledScore(labelled=0, counted=0, correct=0, refused=0, below_threshold=0)


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
    also: str | None = None
    """A second position id the coach accepts, from the sample's :data:`SECOND_LABEL_COLUMN`; never `none`."""
    stance: Stance = Stance.READS
    """ANSWERS for a label written `at:<id>` (`v1-e32-t46`)."""
    also_stance: Stance = Stance.READS
    """The second label's stance."""


@dataclass(frozen=True, slots=True)
class CoachLabel:
    """One cell of the coach's sample read: a position id or `none`, and its stance."""

    label: str
    stance: Stance = Stance.READS

    @property
    def written(self) -> str:
        """The label as the sample writes it: the id, `at:<id>` for one that answers, or `none`."""
        return labelled_as(self.label, self.stance)


def coach_label(cell: str, active: Collection[str]) -> CoachLabel | None:
    """The label a cell of the coach's sample holds; None for a blank or `unsure` cell, which is not scored.

    `at:<id>` (:data:`~debate_core.arguments.landscape.evaluation_breakdown.ANSWERS_PREFIX`, read without
    case, space after the colon ignored) labels a card that answers the position (`v1-e32-t46`); a plain id
    one that reads it. Raises `ValueError`, naming the rule and never the cell, for a label that names no
    active position: `at:none` and an `at:` with no id among them.
    """
    text = cell.strip()
    if text[: len(ANSWERS_PREFIX)].casefold() == ANSWERS_PREFIX:
        answered = text[len(ANSWERS_PREFIX) :].strip()
        if not answered:
            raise ValueError("is labelled at: with no position to answer")
        if answered.casefold() == NO_POSITION_LABEL:
            raise ValueError("is labelled at:none, and none is no position to answer")
        if answered not in active:
            raise ValueError("answers a position that is not an active id")
        return CoachLabel(answered, Stance.ANSWERS)
    if not text or text.casefold() == UNSURE_LABEL:
        return None
    if text.casefold() == NO_POSITION_LABEL:
        return CoachLabel(NO_POSITION_LABEL)
    if text not in active:
        raise ValueError("names a position that is not an active id")
    return CoachLabel(text)


def row_labels(
    row: int, position: str, also: str, taxonomy: Taxonomy
) -> tuple[CoachLabel, CoachLabel | None] | None:
    """Row `row`'s label and second label, from its `position` and `also` cells; None for a row not scored.

    Raises :class:`EvaluationRefused`, naming the row and the rule and never a cell, as
    :func:`read_coach_sample` refuses it.
    """
    active = {one.id for one in taxonomy.active_positions}
    try:
        label = coach_label(position, active)
    except ValueError as refused:
        of = (
            f" of {taxonomy.topic_id} {taxonomy.taxonomy_version}"
            if str(refused).endswith("active id")
            else ""
        )
        raise EvaluationRefused(f"row {row} {refused}{of}") from None
    if label is None:
        return None
    return label, _second_label(row, label, also.strip(), active, taxonomy)


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
    """The scan of every cassette of the prompt on this machine, but one naming another prompt version."""
    repair_cassettes: NameScan = field(default_factory=lambda: NameScan(texts=0))
    """The scan of every repair cassette of the prompt version, filed under the caselist (`v1-e32-t40`)."""
    interrupted_by: ProviderError | None = None
    """The router error that stopped the stage partway; None when it ran to the end."""
    unanswered: int = 0
    """Cards (fingerprints) a stop left unasked; 0 when the stage ran to the end."""
    model_alone: LabelledScore = field(default_factory=lambda: _NOTHING_SCORED)
    """The model's answers for every labelled card (`v1-e32-t43`): the counts above, with its refusals and
    coverage."""
    pipeline: LabelledScore = field(default_factory=lambda: _NOTHING_SCORED)
    """The labelled cards as students meet them, stage one's sure placements first (`v1-e32-t43`): the bar
    reads its accuracy."""

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
        """The model's alone, over its counted cards: not what the bar reads since `v1-e32-t43`."""
        return self.correct / self.counted if self.counted else None

    @property
    def scans_clean(self) -> bool:
        """Whether no scan, of the prompt inputs, the cassettes or the repair cassettes, found a name."""
        return self.sent.clean and self.cassettes.clean and self.repair_cassettes.clean

    @property
    def meets_target(self) -> bool:
        """Whether the pipeline's accuracy, over its counted cards, reaches the bar (:data:`BAR_READS`)."""
        accuracy = self.pipeline.accuracy
        return accuracy is not None and accuracy >= TARGET_ACCURACY


def read_coach_sample(sample: TextIO, rows: Iterable[str], taxonomy: Taxonomy) -> tuple[LabelledCard, ...]:
    """The coach's labels, joined to their cards: `sample` is the filled CSV, `rows` the file beside it.

    `rows` is JSON lines: a header line, then one object per card with its `sample_row` and `item_id`, as
    `v1-e32-t21` writes them. A label naming no active position of `taxonomy`, or a row the rows file does
    not have, is refused by its row number. So is a second label (:data:`SECOND_LABEL_COLUMN`) that is
    `none`, the row's own label or no active position, or that a row labelled `none` gives; a row that is
    not scored is not read for one.
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
    labelled: list[LabelledCard] = []
    for line in reader:
        row = int(line["sample_row"])
        read = row_labels(row, line.get("position") or "", line.get(SECOND_LABEL_COLUMN) or "", taxonomy)
        if read is None:
            continue
        if row not in by_row:
            raise EvaluationRefused(f"row {row} of the coach's sample is not in its rows file")
        label, also = read
        labelled.append(
            LabelledCard(
                item_id=by_row[row],
                label=label.label,
                sample_row=row,
                stratum=strata.get(row),
                also=also.label if also is not None else None,
                stance=label.stance,
                also_stance=also.stance if also is not None else Stance.READS,
            )
        )
    return tuple(labelled)


def _second_label(
    row: int, label: CoachLabel, also: str, active: set[str], taxonomy: Taxonomy
) -> CoachLabel | None:
    """Row `row`'s second label, None when blank: an active position other than its first in id or stance,
    never `none`. The same id with the other stance accepts either stance (`v1-e32-t46`)."""
    if not also:
        return None
    if label.label == NO_POSITION_LABEL:
        raise EvaluationRefused(f"row {row} is labelled none and names a second label")
    bare = also[len(ANSWERS_PREFIX) :] if also[: len(ANSWERS_PREFIX)].casefold() == ANSWERS_PREFIX else also
    if bare.strip().casefold() == NO_POSITION_LABEL:
        raise EvaluationRefused(f"row {row}'s second label is none: a second label names a position")
    try:
        second = coach_label(also, active)
    except ValueError:
        second = None
    if second is None:
        raise EvaluationRefused(
            f"row {row}'s second label is not an active id of {taxonomy.topic_id} {taxonomy.taxonomy_version}"
        )
    if second == label:
        raise EvaluationRefused(f"row {row}'s second label is its first")
    return second


@dataclass(frozen=True, slots=True)
class CoachSampleCheck:
    """The coach's sample read against a caselist's taxonomy, without asking the model: counts only."""

    caselist: str
    topic_id: str
    taxonomy_version: str
    snapshot: date
    labelled: int
    """Rows scored: a position id or `none`."""
    by_label_kind: dict[str, int]
    """Those rows by their label's kind (`da`, `cp`...), `none` for a card labelled none."""
    second_labels: dict[str, int]
    """The rows with a second label, by that label's kind."""
    by_stance: dict[str, int] = field(default_factory=dict[str, int])
    """The rows labelled a position, by their label's stance (`v1-e32-t46`)."""


def coach_sample_counts(
    labelled: Iterable[LabelledCard], taxonomy: Taxonomy
) -> tuple[dict[str, int], dict[str, int]]:
    """The labelled rows by their label's kind, and the rows with a second label by its kind."""
    chosen = list(labelled)
    kinds = Counter(label_kind(taxonomy, one.label) for one in chosen)
    second = Counter(label_kind(taxonomy, one.also) for one in chosen if one.also is not None)
    return dict(sorted(kinds.items())), dict(sorted(second.items()))


def stance_counts(labelled: Iterable[LabelledCard]) -> dict[str, int]:
    """The rows labelled a position by their label's stance, both stances named (`v1-e32-t46`)."""
    found = Counter(one.stance.value for one in labelled if one.label != NO_POSITION_LABEL)
    return {stance.value: found[stance.value] for stance in sorted(Stance, key=lambda one: one.value)}


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
    """Every disclosing team's tournament, every source's: the scan's third list (`v1-e32-t40`; until then
    each team's school and code were on it too, and the first two lists hold those)."""
    second_labels: Mapping[str, str] = field(default_factory=dict[str, str])
    """The second label of each labelled card that has one, by item id (`v1-e32-t41`)."""
    labelled: tuple[LabelledCard, ...] = ()
    """The labelled cards, one per item id, in the sample's order: what each card's breakdown is of."""
    file_sides: Mapping[str, frozenset[str]] = field(default_factory=dict[str, frozenset[str]])
    """The sides each source holding a labelled card was disclosed on, by its digest (`v1-e32-t46`)."""


async def ask_labelled_cards(
    reading: SeedReading,
    labelled: Iterable[LabelledCard],
    stage: ModelClassificationStage,
    taxonomy: Taxonomy,
) -> LabelledAnswers:
    """Ask `stage` about every labelled card `reading` holds, once per fingerprint, as a run would ask."""
    chosen = list(labelled)
    labels = {one.item_id: one.label for one in chosen}
    second_labels = {one.item_id: one.also for one in chosen if one.also is not None}
    names = CaselistNames(reading.caselist_names)
    codes = code_words(reading.caselist_names)
    disclosed = DisclosedNames.of_sources(reading.sources)
    candidates: dict[str, ModelCandidate] = {}
    items: dict[str, MatchItem] = {}
    tournaments: set[str] = set()
    file_sides: dict[str, frozenset[str]] = {}
    for source in reading.sources:
        tournaments |= {team.tournament for team in source.teams if team.tournament}
        if not any(item_id.startswith(f"{source.sha256}:") for item_id in labels):
            continue
        file_sides[source.sha256] = frozenset(team.side.value for team in source.teams)
        cards = iter(source.cards)
        for item in read_items(source, names):
            if item.kind is not ItemKind.CARD:
                continue
            card = next(cards)
            if item.item_id in labels:
                items[item.item_id] = item
                candidates.setdefault(
                    item.fingerprint, model_candidate(source, item, card, names, codes, disclosed)
                )
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
        second_labels=second_labels,
        labelled=tuple({one.item_id: one for one in chosen}.values()),
        file_sides=file_sides,
    )


def score_labelled_answers(
    reading: SeedReading,
    taxonomy: Taxonomy,
    asked: LabelledAnswers,
    *,
    prompt_version: str,
    overrides: OverrideRules | None = None,
    review_threshold: float = DEFAULT_REVIEW_THRESHOLD,
    cassettes: Iterable[str] = (),
    repair_cassettes: Iterable[str] = (),
    snapshot: date | None = None,
) -> FormatEvaluation:
    """The evaluation's score of `asked`, and the scans of what was sent, of `cassettes` and of
    `repair_cassettes`, each read as :func:`scanned_cassettes` and :func:`scanned_repairs` choose.

    A counted answer is right when it names the card's label or its second label (`v1-e32-t41`), each with
    its stance (`v1-e32-t46`): the counts are the cards' breakdowns' (:func:`labelled_card_breakdowns`). The
    pipeline's score places each card with `taxonomy` and `overrides`, the coach's decisions on its headings
    (none when None), as a landscape run does (`v1-e32-t43`)."""
    labels, outcome = asked.labels, asked.outcome
    cards = labelled_card_breakdowns(asked, taxonomy, overrides, threshold=review_threshold)
    committed = committed_positions(taxonomy)
    names = ScanNames.of(reading.caselist_names, asked.tournaments, taxonomy_text=committed)
    alone = model_alone_score(cards)
    labelled_none = sum(card.outcome is CardOutcome.PLACED_LABELLED_NONE for card in cards)
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
        counted=alone.counted,
        correct=alone.correct,
        placed_below_threshold=alone.below_threshold,
        placed_labelled_none=labelled_none,
        refused=dict(sorted(refused.items())),
        input_tokens=outcome.input_tokens,
        output_tokens=outcome.output_tokens,
        sent=marked_scan(
            outcome.sent_inputs,
            lambda text: input_batch_hits("input batch", text, names),
            reading.caselist_names,
            asked.tournaments,
        ),
        cassettes=marked_scan(
            scanned_cassettes(cassettes, prompt_version),
            lambda text: cassette_hits("cassette", text, names),
            reading.caselist_names,
            asked.tournaments,
            leave_out=(committed,),
        ),
        repair_cassettes=marked_scan(
            scanned_repairs(repair_cassettes, reading.caselist, prompt_version),
            lambda text: repair_cassette_hits("repair cassette", text, names),
            reading.caselist_names,
            asked.tournaments,
            leave_out=(committed,),
        ),
        interrupted_by=outcome.interrupted_by,
        unanswered=len(asked.candidates) - outcome.sent,
        model_alone=alone,
        pipeline=pipeline_score(cards),
    )


async def evaluate_labelled_cards(
    reading: SeedReading,
    taxonomy: Taxonomy,
    labelled: Iterable[LabelledCard],
    stage: ModelClassificationStage,
    *,
    overrides: OverrideRules | None = None,
    review_threshold: float = DEFAULT_REVIEW_THRESHOLD,
    cassette_texts: Callable[[], Iterable[str]] = lambda: (),
    repair_cassette_texts: Callable[[], Iterable[str]] = lambda: (),
    snapshot: date | None = None,
) -> FormatEvaluation:
    """Ask `stage` about every labelled card `reading` holds, and score the answers against the labels.

    `cassette_texts` and `repair_cassette_texts` are read after the stage has run, so a recording run
    scans what it recorded. `overrides` are the coach's decisions the pipeline's score places cards with.
    """
    asked = await ask_labelled_cards(reading, labelled, stage, taxonomy)
    return score_labelled_answers(
        reading,
        taxonomy,
        asked,
        prompt_version=stage.prompt_version,
        overrides=overrides,
        review_threshold=review_threshold,
        cassettes=cassette_texts(),
        repair_cassettes=repair_cassette_texts(),
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
    generic: Mapping[str, str] = field(default_factory=dict[str, str])
    """The taxonomy's generic positions, id to kind (:func:`generic_positions`, `v1-e32-t49`)."""

    @property
    def outcomes(self) -> dict[str, int]:
        return outcome_counts(self.cards)

    @property
    def generic_answers(self) -> GenericAnswers:
        """The model's answers naming a generic position, on their own (`v1-e32-t49`)."""
        return generic_answer_counts(self.cards, self.generic)

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
    cassettes = scanned_cassettes(cassette_texts(), stage.prompt_version)
    repairs = scanned_repairs(repair_cassette_texts(), reading.caselist, stage.prompt_version)
    evaluation = score_labelled_answers(
        reading,
        taxonomy,
        asked,
        prompt_version=stage.prompt_version,
        overrides=overrides,
        review_threshold=review_threshold,
        cassettes=cassettes,
        repair_cassettes=repairs,
        snapshot=snapshot,
    )
    outcome = asked.outcome
    cards = labelled_card_breakdowns(asked, taxonomy, overrides, threshold=review_threshold)
    names = ScanNames.of(
        reading.caselist_names, asked.tournaments, taxonomy_text=committed_positions(taxonomy)
    )
    return EvaluationBreakdown(
        evaluation=evaluation,
        cards=cards,
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
        generic=generic_positions(taxonomy),
    )


def labelled_card_breakdowns(
    asked: LabelledAnswers, taxonomy: Taxonomy, overrides: OverrideRules | None, *, threshold: float
) -> tuple[CardBreakdown, ...]:
    """Each labelled card's outcome, batch and stage-one placement, by `taxonomy` and the coach's
    `overrides` (none when None), in the sample's order: what the evaluation's scores and the breakdown are
    counted from."""
    rules = overrides if overrides is not None else OverrideRules(topic_id=taxonomy.topic_id)
    matcher = PositionMatcher(taxonomy, rules)
    batch_of = {
        fingerprint: number
        for number, record in enumerate(asked.outcome.batches, start=1)
        for fingerprint in record.fingerprints
    }
    return tuple(
        _card_breakdown(
            one,
            asked.items.get(one.item_id),
            asked.outcome,
            taxonomy,
            matcher,
            batch_of,
            threshold=threshold,
            file_sides=asked.file_sides.get(one.item_id.split(":", 1)[0], frozenset()),
        )
        for one in asked.labelled
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
    file_sides: Collection[str] = (),
) -> CardBreakdown:
    kind = label_kind(taxonomy, labelled.label)
    if item is None:
        return CardBreakdown(
            label=labelled.label,
            label_kind=kind,
            outcome=CardOutcome.NOT_FOUND,
            sample_row=labelled.sample_row,
            stratum=labelled.stratum,
            also=labelled.also,
            stance=labelled.stance,
            also_stance=labelled.also_stance,
        )
    result = outcome.results.get(item.fingerprint)
    found = card_outcome(
        taxonomy,
        labelled.label,
        result,
        threshold=threshold,
        also=labelled.also,
        stance=labelled.stance,
        also_stance=labelled.also_stance,
        file_sides=file_sides,
    )
    answered = result is not None and not places_nothing(result)
    answer = result.position_id if result is not None and answered else None
    placed = matcher.place(item)
    reason = refusal_reason(result) if result is not None and found is CardOutcome.REFUSED else None
    return CardBreakdown(
        label=labelled.label,
        label_kind=kind,
        outcome=found,
        refusal=reason.value if reason is not None else None,
        answer=answer,
        confidence=result.confidence if result is not None and answered else None,
        deterministic=deterministic_placement(
            placed, threshold=threshold, taxonomy=taxonomy, file_sides=file_sides
        ),
        sample_row=labelled.sample_row,
        stratum=labelled.stratum,
        batch=batch_of.get(item.fingerprint),
        related=found in (CardOutcome.WRONG_POSITION_SAME_KIND, CardOutcome.WRONG_KIND)
        and answer is not None
        and related(taxonomy, answer, labelled.label),
        also=labelled.also,
        stance=labelled.stance,
        also_stance=labelled.also_stance,
        answer_stance=scored_stance(taxonomy, answer, result.role, file_sides)
        if result is not None and answer is not None
        else None,
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


def committed_positions(taxonomy: Taxonomy) -> str:
    """`taxonomy`'s positions as the prompt sends them: committed text, which the scans leave out."""
    return str(prompt_variables(taxonomy, ())["positions"])


def scanned_cassettes(texts: Iterable[str], prompt_version: str) -> list[str]:
    """The cassettes of the prompt an evaluation scans: every one but those naming another prompt version.

    A cassette recorded under an earlier version is no part of this evaluation (1.0.0's held names in
    heading paths, `v1-e32-t39`). A text whose version cannot be read is scanned: the filter fails toward
    reading more.
    """
    return [text for text in texts if _prompt_version_of(text) in (None, prompt_version)]


def _prompt_version_of(cassette: str) -> str | None:
    document = _document_of(cassette)
    try:
        version = document["request"]["prompt"]["prompt_version"] if document is not None else None
    except (KeyError, TypeError):
        return None
    return version if isinstance(version, str) else None


def _document_of(cassette: str) -> dict[str, Any] | None:
    try:
        loaded: object = json.loads(cassette)
    except json.JSONDecodeError:
        return None
    return cast(dict[str, Any], loaded) if isinstance(loaded, dict) else None


def scanned_repairs(texts: Iterable[str], caselist: str, prompt_version: str) -> list[str]:
    """The repair cassettes an evaluation scans: of the classify prompt at `prompt_version`, filed under
    `caselist` (`v1-e32-t39` listed their hits; `v1-e32-t40` counts them in the evaluation's scan)."""
    return [text for text in texts if _repairs(text, caselist, prompt_version)]


def _repairs(cassette: str, caselist: str, prompt_version: str) -> bool:
    """Whether `cassette` is a `model.repair` call for this prompt and version, filed under `caselist`."""
    document = _document_of(cassette)
    if document is None:
        return False
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
            overrides=self._taxonomies.overrides(prepared.reading.topic_id),
            review_threshold=self._threshold,
            cassette_texts=self._cassette_texts,
            repair_cassette_texts=self._repair_cassette_texts,
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

    async def check_sample(
        self, caselist: str, sample: TextIO, rows: Iterable[str], *, snapshot: date | None = None
    ) -> CoachSampleCheck:
        """Read the coach's sample against the caselist's taxonomy as :meth:`evaluate` reads it, and count it,
        reading no source and asking no model (`v1-e32-t41`). Refused exactly as the evaluation refuses it."""
        _, taxonomy, through = await self._resolved(caselist, snapshot)
        labelled = _labelled(sample, rows, taxonomy)
        by_label_kind, second_labels = coach_sample_counts(labelled, taxonomy)
        return CoachSampleCheck(
            by_stance=stance_counts(labelled),
            caselist=caselist,
            topic_id=taxonomy.topic_id,
            taxonomy_version=taxonomy.taxonomy_version,
            snapshot=through,
            labelled=len(labelled),
            by_label_kind=by_label_kind,
            second_labels=second_labels,
        )

    async def sample_sides(
        self, caselist: str, sample: TextIO, rows: Iterable[str], *, snapshot: date | None = None
    ) -> SampleSides:
        """The coach's labelled rows, read as :meth:`evaluate` reads them, and the sides each one's file was
        disclosed on, from the snapshot's reading: what the relabelling sitting shows beside a card
        (`v1-e32-t46`). Asks no model; a row whose card the store no longer holds has no side."""
        prepared = await self._prepared(caselist, sample, rows, snapshot)
        by_source = {
            source.sha256: frozenset(team.side.value for team in source.teams)
            for source in prepared.reading.sources
        }
        sides = {
            one.sample_row: by_source.get(one.item_id.split(":", 1)[0], frozenset())
            for one in prepared.labelled
            if one.sample_row is not None
        }
        return SampleSides(taxonomy=prepared.taxonomy, labelled=prepared.labelled, sides=sides)

    async def _resolved(self, caselist: str, snapshot: date | None) -> tuple[Topic, Taxonomy, date]:
        """The topic the caselist's snapshot is on and its taxonomy, and the snapshot: the given one or the
        newest."""
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
        return resolved.topic, resolved.taxonomy, through

    async def _prepared(
        self, caselist: str, sample: TextIO, rows: Iterable[str], snapshot: date | None
    ) -> _Prepared:
        topic, taxonomy, through = await self._resolved(caselist, snapshot)
        labelled = _labelled(sample, rows, taxonomy)
        reading = await read_seed_sources(
            store=self._parsed,
            local=self._local,
            suppression=self._suppression,
            topic=topic,
            caselist=caselist,
            through=through,
            topic_map=self._taxonomies.topic_map(),
        )
        return _Prepared(reading=reading, taxonomy=taxonomy, labelled=labelled, through=through)


@dataclass(frozen=True, slots=True)
class SampleSides:
    """The coach's labelled rows, read against the taxonomy, and the sides each one's file was disclosed on
    (:class:`~debate_core.domain.caselist.Side` values), by sample row (`v1-e32-t46`)."""

    taxonomy: Taxonomy
    labelled: tuple[LabelledCard, ...]
    sides: Mapping[int, frozenset[str]]


def _labelled(sample: TextIO, rows: Iterable[str], taxonomy: Taxonomy) -> tuple[LabelledCard, ...]:
    labelled = read_coach_sample(sample, rows, taxonomy)
    if not labelled:
        raise EvaluationRefused("the coach's sample has no labelled row to score")
    return labelled


@dataclass(frozen=True, slots=True)
class _Prepared:
    """A caselist's snapshot resolved, its sources read, and the coach's labels joined to them."""

    reading: SeedReading = field(repr=False)
    taxonomy: Taxonomy
    labelled: tuple[LabelledCard, ...]
    through: date

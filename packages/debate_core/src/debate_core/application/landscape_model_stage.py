"""The landscape's model stage: asking a model about the cards headings cannot place (`v1-e32-t07`).

:class:`~debate_core.application.position_classification.PositionClassificationService` runs stage one,
`v1-e32-t02`'s deterministic matcher, and hands this stage the cards it left unplaced or placed below the
review threshold, one :class:`~debate_core.arguments.landscape.model_stage.ModelCandidate` per fingerprint
not already cached under this prompt version. :meth:`ModelClassificationStage.run`:

1. **orders** them, most cards first (:func:`~debate_core.arguments.landscape.model_stage.model_order`),
   and keeps the first `max_items`; the rest are **held back** for a later run, and counted;
2. **reads** each kept card's evidence text from the parsed store (:class:`ParsedStoreCardTexts`), and
   cuts its excerpt: its first words, without the names of the caselist's schools and teams;
3. **asks** in batches of `batch_size`, each one call to `landscape.classify_position` through the
   :class:`~debate_core.application.structured_output.StructuredOutputGuard` on the `high_volume` route.
   A batch whose answer leaves a card unanswered, answers one twice or names one it was not asked about
   is repaired once, as an answer that does not fit the schema is, and then refused;
4. **judges** each answer (:func:`~debate_core.arguments.landscape.model_stage.judge`): an unknown
   position id, a rationale echoing twelve or more consecutive words of the card, or no position at all
   places nothing, and the card stays in the review queue.

It returns one MODEL result per candidate it asked about, placed or placing nothing, for the cache.

**Planning only** (a dry run): the stage orders, caps and counts, and asks nothing.

**A model that cannot be reached**, or refuses the call for rate or access, stops the stage: the results
of the batches already answered are kept, and :attr:`ModelStageOutcome.interrupted` names the error's
class. The service writes what it has and the run stops with :class:`ModelStageInterrupted`.

## The policy gate (:func:`model_use_gate`)

The data-use policy lets a model read the real corpus only once its open question 4, the provider's
no-training and no-retention terms and the account's logging check, is recorded as answered. A live run
is refused until the policy's own table says so: the gate reads the policy's open-questions row 4, and a
row still marked `Open`, or no policy to read, refuses.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final, Protocol

from debate_core.application.errors import DomainError, OutputProblem, ProviderError
from debate_core.application.model_errors import ModelOutputError, ValidationPolicy
from debate_core.application.ports.parsed_store import ParsedStore
from debate_core.application.structured_output import StructuredOutputGuard
from debate_core.arguments.landscape.model_stage import (
    CITE_WORDS,
    DEFAULT_BATCH_SIZE,
    EXCERPT_WORDS,
    ModelCandidate,
    ModelItem,
    Refusal,
    answer_problems,
    batches,
    bounded_words,
    item_label,
    judge,
    model_order,
    prompt_variables,
    refusal,
    refusal_reason,
)
from debate_core.arguments.landscape.source_headings import CaselistNames
from debate_core.arguments.landscape.tag_scrub import card_tag
from debate_core.domain.landscape import Taxonomy
from debate_core.domain.landscape_classification import ClassificationResult, ModelPositionAnswers
from debate_core.domain.model_contracts import ModelPrompt, TaskClass

__all__ = [
    "CLASSIFY_POSITION_PROMPT_ID",
    "CLASSIFY_POSITION_VERSION",
    "CLASSIFICATION_POLICY",
    "CLASSIFICATION_TASK_CLASS",
    "DEFAULT_MAX_MODEL_ITEMS",
    "POLICY_QUESTION",
    "CardTexts",
    "ModelClassificationStage",
    "ModelStageInterrupted",
    "ModelStageOutcome",
    "ParsedStoreCardTexts",
    "model_use_gate",
    "scrubbed_cite",
]

logger = logging.getLogger(__name__)

CLASSIFY_POSITION_PROMPT_ID: Final = "landscape.classify_position"
"""The registered prompt the stage runs (`prompts/landscape/classify_position.md`)."""

CLASSIFY_POSITION_VERSION: Final = "1.0.0"
"""The version of :data:`CLASSIFY_POSITION_PROMPT_ID` a stage runs unless it is built with another."""

CLASSIFICATION_TASK_CLASS: Final = TaskClass.HIGH_VOLUME
"""The task class the prompt declares and is routed as: cheap, frequent classification."""

CLASSIFICATION_POLICY: Final = ValidationPolicy(fail_closed=False)
"""Placing a card under a position writes no evidence, so it is not an evidence-integrity action."""

DEFAULT_MAX_MODEL_ITEMS: Final = 2000
"""Cards (one per fingerprint) one run may ask a model about, proposed to the PM from hspolicy26's count.

On 2026-10-20's store the first 2,000, in :func:`~debate_core.arguments.landscape.model_stage.model_order`,
stand for 14,413 of the 58,299 cards stage one left unplaced or below the threshold, in 100 calls.
"""

POLICY_QUESTION: Final = 4
"""The data-use policy's open question a live run waits on: the provider's no-retention terms."""


class ModelStageInterrupted(DomainError):
    """The model could not be reached, or refused the call for rate or access, partway through a run."""

    def __init__(self, error: str, *, sent: int, unanswered: int) -> None:
        super().__init__(
            f"the model stage stopped on {error} after {sent} card(s); the {unanswered} card(s) not yet "
            "answered were not cached, the cache and the review queue hold what was answered, and no "
            "report was written or published"
        )
        self.error = error
        self.sent = sent
        self.unanswered = unanswered


class CardTexts(Protocol):
    """Where the stage reads a card's evidence text: only for the cards it asks about."""

    async def evidence_texts(
        self, caselist: str, version: str, wanted: Mapping[str, Collection[int]]
    ) -> Mapping[tuple[str, int], str]:
        """Each wanted card's evidence text by (source digest, first paragraph); none for a card without."""
        ...


class ParsedStoreCardTexts:
    """Evidence texts from the parsed store: each stored card keeps its `evidence_text`."""

    def __init__(self, store: ParsedStore) -> None:
        self._store = store

    async def evidence_texts(
        self, caselist: str, version: str, wanted: Mapping[str, Collection[int]]
    ) -> Mapping[tuple[str, int], str]:
        found: dict[tuple[str, int], str] = {}
        for sha256, indexes in sorted(wanted.items()):
            record = await self._store.read_document(caselist, version, sha256)
            stored = record.document.get("cards") if record is not None else None
            for card in stored if isinstance(stored, list) else []:
                if not isinstance(card, dict):
                    continue
                provenance = card.get("provenance")
                first = provenance.get("first_element_index") if isinstance(provenance, dict) else None
                text = card.get("evidence_text")
                if isinstance(first, int) and first in indexes and isinstance(text, str) and text.strip():
                    found[(sha256, first)] = text
        return found


@dataclass(frozen=True, slots=True)
class ModelStageOutcome:
    """What one stage run asked, what came back, and what it held back."""

    results: Mapping[str, ClassificationResult] = field(repr=False)
    """A MODEL result per fingerprint asked about: placed, or placing nothing."""
    sent: int
    """Cards (fingerprints) asked about; in a plan, the ones a run would ask about."""
    held_back: int
    """Candidates over `max_items`, left for a later run."""
    calls: int = 0
    """Model calls made, repairs included."""
    refused: Mapping[str, int] = field(default_factory=dict[str, int])
    """Answers that placed nothing, by :class:`~debate_core.arguments.landscape.model_stage.Refusal`."""
    input_tokens: int = 0
    output_tokens: int = 0
    """Tokens of the calls whose answers were used, as the router reported them."""
    interrupted: str | None = None
    """The class of the router error that stopped the stage; None when it ran to the end."""
    sent_inputs: tuple[str, ...] = field(default=(), repr=False)
    """Each batch's `items` variable as sent: what a scan of the prompt inputs reads. Never logged."""


class ModelClassificationStage:
    """Asks the model about stage one's leftovers in capped, checked batches."""

    def __init__(
        self,
        guard: StructuredOutputGuard,
        texts: CardTexts,
        *,
        prompt_version: str = CLASSIFY_POSITION_VERSION,
        max_items: int = DEFAULT_MAX_MODEL_ITEMS,
        batch_size: int = DEFAULT_BATCH_SIZE,
        plan_only: bool = False,
    ) -> None:
        if max_items < 0:
            raise ValueError(f"max_model_items is 0 or more; got {max_items}")
        if batch_size < 1:
            raise ValueError(f"a batch holds at least one card; got {batch_size}")
        self._guard = guard
        self._texts = texts
        self.prompt_version = prompt_version
        self.max_items = max_items
        self._batch_size = batch_size
        self.plan_only = plan_only

    @property
    def prompt_id(self) -> str:
        return CLASSIFY_POSITION_PROMPT_ID

    def planning(self) -> ModelClassificationStage:
        """This stage, counting what it would ask and asking nothing: a dry run's."""
        return ModelClassificationStage(
            self._guard,
            self._texts,
            prompt_version=self.prompt_version,
            max_items=self.max_items,
            batch_size=self._batch_size,
            plan_only=True,
        )

    async def run(
        self,
        candidates: Sequence[ModelCandidate],
        *,
        taxonomy: Taxonomy,
        caselist: str,
        version: str,
        names: CaselistNames,
        codes: Collection[str],
    ) -> ModelStageOutcome:
        """Ask about the first `max_items` of `candidates` in :func:`model_order`; hold back the rest."""
        ordered = model_order(candidates)
        kept = ordered[: self.max_items]
        held_back = len(ordered) - len(kept)
        if self.plan_only or not kept:
            return ModelStageOutcome(results={}, sent=len(kept), held_back=held_back)
        wanted: dict[str, set[int]] = {}
        for one in kept:
            wanted.setdefault(one.source_sha256, set()).add(one.first_element_index)
        evidence = await self._texts.evidence_texts(caselist, version, wanted)
        items = [
            _item(one, evidence.get((one.source_sha256, one.first_element_index)), names, codes)
            for one in kept
        ]
        results: dict[str, ClassificationResult] = {}
        refused: Counter[str] = Counter()
        calls = input_tokens = output_tokens = 0
        interrupted: str | None = None
        sent_inputs: list[str] = []
        for batch in batches(items, self._batch_size):
            variables = prompt_variables(taxonomy, batch)
            sent_inputs.append(str(variables["items"]))
            prompt = ModelPrompt(
                prompt_id=CLASSIFY_POSITION_PROMPT_ID, prompt_version=self.prompt_version, variables=variables
            )
            size = len(batch)
            try:
                answered = await self._guard.generate(
                    CLASSIFICATION_TASK_CLASS,
                    prompt,
                    ModelPositionAnswers,
                    policy=CLASSIFICATION_POLICY,
                    check=lambda answers, size=size: _as_output_problems(answers, size),
                )
            except ModelOutputError as invalid:
                calls += invalid.attempts
                for item in batch:
                    results[item.candidate.fingerprint] = refusal(
                        Refusal.BATCH_REFUSED,
                        taxonomy_version=taxonomy.taxonomy_version,
                        prompt_id=CLASSIFY_POSITION_PROMPT_ID,
                        prompt_version=self.prompt_version,
                        model_id=invalid.model_id or "unknown",
                    )
                refused[Refusal.BATCH_REFUSED.value] += size
                continue
            except ProviderError as error:
                interrupted = type(error).__name__
                logger.warning(
                    "landscape model stage interrupted",
                    extra={"error": interrupted, "answered": len(results), "cards": len(items)},
                )
                break
            calls += len(answered.attempts)
            usage = answered.response.usage
            input_tokens += usage.input_tokens or 0
            output_tokens += usage.output_tokens or 0
            model_id = answered.response.route.model_id
            by_label = {answer.item: answer for answer in answered.output.answers}
            for index, item in enumerate(batch):
                result = judge(
                    by_label[item_label(index)],
                    item,
                    taxonomy=taxonomy,
                    prompt_id=CLASSIFY_POSITION_PROMPT_ID,
                    prompt_version=self.prompt_version,
                    model_id=model_id,
                )
                results[item.candidate.fingerprint] = result
                reason = refusal_reason(result)
                if reason is not None:
                    refused[reason.value] += 1
        return ModelStageOutcome(
            results=results,
            sent=len(results) if interrupted is not None else len(kept),
            held_back=held_back,
            calls=calls,
            refused=dict(sorted(refused.items())),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            interrupted=interrupted,
            sent_inputs=tuple(sent_inputs),
        )


def _item(
    candidate: ModelCandidate, evidence: str | None, names: CaselistNames, codes: Collection[str]
) -> ModelItem:
    excerpt = bounded_words(card_tag(evidence, candidate.own_names, names, codes), EXCERPT_WORDS)
    return ModelItem(candidate=candidate, excerpt=excerpt, evidence=evidence or "")


def scrubbed_cite(
    short_cite: str | None, own_names: Collection[str], names: CaselistNames, codes: Collection[str]
) -> str | None:
    """A short cite as a model is shown it: words, no names of the caselist's teams, at most a dozen."""
    return bounded_words(card_tag(short_cite, tuple(own_names), names, codes), CITE_WORDS)


def _as_output_problems(answers: ModelPositionAnswers, size: int) -> tuple[OutputProblem, ...]:
    return tuple(
        OutputProblem(loc=("answers",), type=problem.type, msg=problem.msg)
        for problem in answer_problems(answers, size)
    )


def model_use_gate(policy_text: str | None) -> str | None:
    """Why a live model run over the real corpus may not start, or None when the policy allows it.

    `policy_text` is `docs/policies/caselist-data-use.md`, or None when there is none to read. The
    gate reads the row of the policy's open-questions table for question :data:`POLICY_QUESTION`; a row
    whose status still says `Open`, or no such row, refuses.
    """
    if policy_text is None:
        return (
            "the data-use policy (docs/policies/caselist-data-use.md) is not in this checkout, so whether "
            f"its open question {POLICY_QUESTION} is answered cannot be read; run live from a source checkout"
        )
    row = next(
        (line for line in policy_text.splitlines() if line.startswith(f"| {POLICY_QUESTION} |")),
        None,
    )
    if row is None:
        return f"the data-use policy has no open question {POLICY_QUESTION} to read; a live run waits on it"
    cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
    status = cells[2] if len(cells) > 2 else ""
    if "open" in status.casefold() or not status:
        return (
            f"the data-use policy records open question {POLICY_QUESTION} (the model provider's no-training "
            "and no-retention terms, and the account's logging check) as still open; a live run over the "
            "real corpus waits until it is answered (E32 gate)"
        )
    return None

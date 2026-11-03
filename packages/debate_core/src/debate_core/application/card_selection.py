"""Asking a model where a card's evidence is and what to mark in it: `card.select` and `card.markup`.

:class:`CardSelector` is the one place either prompt is called from. Every call goes through the
:class:`~debate_core.application.structured_output.StructuredOutputGuard` with
:data:`SELECTION_POLICY`, which is fail-closed: an evidence-integrity action never gets a default,
partial or coerced answer (v1-e05-t06-card-selection-contract). Each call also passes the guard a
check from :mod:`debate_core.evidence.selection_guard`, so an answer whose offsets fall outside the
snapshot or the selection, or whose free text repeats the snapshot, is repaired once and then
refused with :class:`~debate_core.application.model_errors.ModelOutputError`, exactly like an answer
that does not fit its schema.

A repair resends the call's rendered prompt, numbered snapshot included, with the problems; the
problems name fields, counts and offsets, never the answer's text (v1-e05-t05).

What comes back is a :class:`~debate_core.evidence.selection_contract.GeneratedCardSelection` or
:class:`~debate_core.evidence.selection_contract.GeneratedCardMarkup`, holding the answer with
`result.metadata.with_inputs(snapshot_ids=..., retrieval_ids=...)`. Turning it into evidence is span
extraction's (`v1-e03-t03`); the pipeline that does that and saves a card is `v1-e06-t02`.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Final

from debate_core.application.errors import OutputProblem
from debate_core.application.model_errors import ValidationPolicy
from debate_core.application.snapshot_service import LoadedSnapshot
from debate_core.application.structured_output import StructuredOutputGuard
from debate_core.domain.model_contracts import ModelPrompt, TaskClass
from debate_core.evidence.numbered_snapshot import NumberedSnapshot
from debate_core.evidence.selection_contract import (
    CARD_MARKUP_PROMPT_ID,
    CARD_SELECT_PROMPT_ID,
    CardSelection,
    GeneratedCardMarkup,
    GeneratedCardSelection,
    MarkupSuggestion,
)
from debate_core.evidence.selection_guard import (
    GuardProblem,
    SnapshotWords,
    markup_problems,
    selection_problems,
)

__all__ = [
    "CARD_MARKUP_VERSION",
    "CARD_SELECT_VERSION",
    "SELECTION_POLICY",
    "SELECTION_TASK_CLASS",
    "CardSelector",
]

CARD_SELECT_VERSION: Final = "1.0.0"
"""The version of `card.select` a selector runs unless it is built with another."""

CARD_MARKUP_VERSION: Final = "1.0.0"
"""The version of `card.markup` a selector runs unless it is built with another."""

SELECTION_POLICY: Final = ValidationPolicy(fail_closed=True)
"""Selection and markup are evidence-integrity actions: they fail closed, always."""

SELECTION_TASK_CLASS: Final = TaskClass.COMPLEX_REASONING
"""The task class both prompts declare and are routed as."""


class CardSelector:
    """Runs `card.select` and `card.markup` over a loaded snapshot, fail-closed and checked."""

    def __init__(
        self,
        guard: StructuredOutputGuard,
        *,
        select_version: str = CARD_SELECT_VERSION,
        markup_version: str = CARD_MARKUP_VERSION,
    ) -> None:
        self._guard = guard
        self._select_version = select_version
        self._markup_version = markup_version

    async def select(self, loaded: LoadedSnapshot, research_need: str) -> GeneratedCardSelection:
        """Where in `loaded` the evidence for `research_need` is, with a suggested tag.

        `loaded` comes from :meth:`~debate_core.application.snapshot_service.SnapshotService.load`,
        so the text the model is shown is the snapshot's, checked. Raises `ModelOutputError` when
        the answer and its one repair are both unusable.
        """
        numbered = NumberedSnapshot(loaded.normalized)
        words = SnapshotWords(loaded.normalized.text)
        prompt = ModelPrompt(
            prompt_id=CARD_SELECT_PROMPT_ID,
            prompt_version=self._select_version,
            variables={"research_need": _need(research_need), "numbered_snapshot": numbered.render()},
        )
        result = await self._guard.generate(
            SELECTION_TASK_CLASS,
            prompt,
            CardSelection,
            policy=SELECTION_POLICY,
            check=lambda selection: _as_output_problems(selection_problems(selection, numbered, words)),
        )
        return GeneratedCardSelection(
            snapshot_id=loaded.snapshot.snapshot_id,
            selection=result.output,
            metadata=result.metadata.with_inputs(
                snapshot_ids=[loaded.snapshot.snapshot_id], retrieval_ids=()
            ),
        )

    async def mark_up(
        self, loaded: LoadedSnapshot, selected: GeneratedCardSelection, research_need: str
    ) -> GeneratedCardMarkup:
        """What to underline and highlight in `selected`, which was made from `loaded`.

        The model is shown only the paragraphs the selection touches, numbered as in the whole
        snapshot, and the selection's passages as numbers. Raises `ValueError` when `selected` is
        from another snapshot, and `ModelOutputError` when the answer and its repair are unusable.
        """
        snapshot_id = loaded.snapshot.snapshot_id
        if selected.snapshot_id != snapshot_id:
            raise ValueError(f"the selection is from snapshot {selected.snapshot_id}, not {snapshot_id}")
        selection = selected.selection
        numbered = NumberedSnapshot(loaded.normalized)
        words = SnapshotWords(loaded.normalized.text)
        passages = [
            {
                "first_paragraph": passage.first_paragraph,
                "last_paragraph": passage.last_paragraph,
                "start_offset": passage.start_offset,
                "end_offset": (
                    passage.end_offset
                    if passage.end_offset is not None
                    else numbered.paragraph_length(passage.last_paragraph)
                ),
            }
            for passage in selection.passages
        ]
        touched = {
            number
            for passage in selection.passages
            for number in range(passage.first_paragraph, passage.last_paragraph + 1)
        }
        prompt = ModelPrompt(
            prompt_id=CARD_MARKUP_PROMPT_ID,
            prompt_version=self._markup_version,
            variables={
                "research_need": _need(research_need),
                "tag": selection.tag.text,
                "passages": json.dumps(passages, indent=2),
                "numbered_passages": numbered.render(touched),
            },
        )
        result = await self._guard.generate(
            SELECTION_TASK_CLASS,
            prompt,
            MarkupSuggestion,
            policy=SELECTION_POLICY,
            check=lambda markup: _as_output_problems(markup_problems(markup, selection, numbered, words)),
        )
        return GeneratedCardMarkup(
            snapshot_id=snapshot_id,
            markup=result.output,
            metadata=result.metadata.with_inputs(snapshot_ids=[snapshot_id], retrieval_ids=()),
        )


def _need(research_need: str) -> str:
    if not research_need.strip():
        raise ValueError("a research need must say what the card is for")
    return research_need


def _as_output_problems(problems: Sequence[GuardProblem]) -> tuple[OutputProblem, ...]:
    return tuple(
        OutputProblem(loc=problem.loc, type=problem.type.value, msg=problem.msg) for problem in problems
    )

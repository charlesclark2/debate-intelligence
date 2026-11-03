"""A model router that cuts the same card shape from any page, in whatever order calls come (v1-e08-t06).

`--auto-cut` runs cuts side by side, so `ScriptedModelRouter`'s one queue, answered in call order,
cannot say which page an answer is for. :class:`EveryPageRouter` gives every `card.select` the same
answer, paragraph 2 whole, and every `card.markup` the same answer, its first 20 characters
underlined. Every page the HTTP cassettes serve as ACCESSIBLE has a second paragraph longer than
that, so each answer fits each page, and the cut is as real as any: the evidence is cut from the
snapshot by CardService, never taken from the answer, and only the verifier passes it.

The answers are offsets only, written by hand, and hold no word of any page.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Final

from pydantic import BaseModel

from debate_core.domain.model_contracts import (
    EmbeddingResponse,
    ModelParams,
    ModelPrompt,
    ModelResponse,
    RerankResponse,
    TaskClass,
)
from debate_core.evidence.selection_contract import CARD_MARKUP_PROMPT_ID, CARD_SELECT_PROMPT_ID
from debate_core.testing.fakes.model_router import ScriptedModelRouter

__all__ = ["EVERY_PAGE_MARKUP", "EVERY_PAGE_SELECTION", "EVERY_PAGE_TAG", "EveryPageRouter"]

EVERY_PAGE_TAG: Final = "The second paragraph says what the need asks"
EVERY_PAGE_SELECTION: Final[dict[str, Any]] = {
    "passages": [{"first_paragraph": 2, "last_paragraph": 2, "start_offset": 0, "end_offset": None}],
    "tag": {
        "text": EVERY_PAGE_TAG,
        "argument_role": "link",
        "need_alignment": "direct",
        "confidence": 0.7,
    },
    "rationale": "Paragraph 2 answers the need.",
    "confidence": 0.7,
}
EVERY_PAGE_MARKUP: Final[dict[str, Any]] = {
    "spans": [
        {"paragraph": 2, "start_offset": 0, "end_offset": 20, "style": "underline", "purpose": "claim"}
    ],
    "rationale": "The opening words carry the claim.",
}


class EveryPageRouter:
    """Answers each `card.select` and `card.markup` call with the one answer for that prompt.

    `refuse` maps a 1-based `card.select` call number to the exception that call raises instead, so a
    test can have the third cut's first call refused by the budget guard. `prompts` keeps every
    structured call's prompt id, in the order the calls were made.
    """

    def __init__(self, *, refuse: dict[int, Exception] | None = None) -> None:
        self._inner = ScriptedModelRouter()
        self._refuse = dict(refuse or {})
        self._selections = 0
        self.prompts: list[str] = []

    async def generate_structured[OutputT: BaseModel](
        self,
        task_class: TaskClass,
        prompt: ModelPrompt,
        schema: type[OutputT],
        params: ModelParams | None = None,
    ) -> ModelResponse[OutputT]:
        self.prompts.append(prompt.prompt_id)
        if prompt.prompt_id == CARD_SELECT_PROMPT_ID:
            self._selections += 1
            refused = self._refuse.get(self._selections)
            if refused is not None:
                raise refused
            self._inner.enqueue(EVERY_PAGE_SELECTION)
        elif prompt.prompt_id == CARD_MARKUP_PROMPT_ID:
            self._inner.enqueue(EVERY_PAGE_MARKUP)
        # Enqueued and taken in one step, with nothing awaited between: no other cut's call can take it.
        return await self._inner.generate_structured(task_class, prompt, schema, params)

    async def embed(self, texts: Sequence[str]) -> EmbeddingResponse:
        raise AssertionError("cutting a card embeds nothing")

    async def rerank(self, query: str, documents: Sequence[str]) -> RerankResponse:
        raise AssertionError("cutting a card reranks nothing")

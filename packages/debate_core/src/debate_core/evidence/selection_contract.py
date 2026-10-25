"""What a model may answer when it selects a card or marks one up: places, labels and reasons, no quotes.

ADR-0006 says the model selects and never authors evidence. These schemas are the part of that rule a
model sees. A card selection (`card.select`, `prompts/card/select.md`) names where the evidence is,
as paragraph numbers and offsets into the paragraph-numbered snapshot
(:mod:`debate_core.evidence.numbered_snapshot`), with a suggested tag, a rationale and a confidence.
A markup answer (`card.markup`, `prompts/card/markup.md`) names what to underline and highlight in
that selection, the same way. No field anywhere takes evidence or quoted text, and the model's
free text (the tag and the rationales) is checked by :mod:`debate_core.evidence.selection_guard`
for runs of the snapshot's own words before anything uses it.

## Offsets

A passage or a span names a paragraph by the number shown as `[PN]` in the prompt, counted from 1,
and offsets into **that paragraph's normalized text**: half-open, in Python `str` indices (code
points), 0 being the paragraph's first character.
:class:`~debate_core.evidence.numbered_snapshot.NumberedSnapshot` turns them into offsets into
the snapshot's normalized text, the unit span extraction
(`v1-e03-t03`) takes. Offsets that the schema alone can refuse (negative ones, paragraph 0) are
refused here; the rest depend on the snapshot and are the guard's.

## Strict, closed and frozen

Every model refuses keys it does not declare, at every depth (`extra="forbid"`), and is frozen. The
structured-output guard validates answers in pydantic's strict JSON mode (v1-e05-t05), so `"3"` is
not an offset either.

## Provenance

What is kept of an answer is a :class:`GeneratedCardSelection` or :class:`GeneratedCardMarkup`:
the answer, the snapshot it is about, and a
:class:`~debate_core.domain.provenance.SourcedArtifactMetadata`, the metadata
`response.metadata.with_inputs(snapshot_ids=..., retrieval_ids=...)` returns. That metadata is a
required field of a type the bare `response.metadata` is not, so neither artifact can be built or
loaded without the call's provenance and the inputs it was given (the PM's amendment of
2026-10-19, ac5).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Final, Self

from pydantic import Field, StringConstraints, model_validator

from debate_core.domain import SpanPurpose, SpanStyle
from debate_core.domain.base import DomainModel, Ulid
from debate_core.domain.provenance import SourcedArtifactMetadata

__all__ = [
    "CARD_MARKUP_PROMPT_ID",
    "CARD_SELECT_PROMPT_ID",
    "MAX_MARKUP_SPANS",
    "MAX_PASSAGES",
    "MAX_RATIONALE_CHARACTERS",
    "MAX_TAG_CHARACTERS",
    "ArgumentRole",
    "CardSelection",
    "GeneratedCardMarkup",
    "GeneratedCardSelection",
    "MarkupSpan",
    "MarkupSuggestion",
    "NeedAlignment",
    "SelectedPassage",
    "TagSuggestion",
]

CARD_SELECT_PROMPT_ID: Final = "card.select"
"""The registered prompt that answers with a :class:`CardSelection`."""

CARD_MARKUP_PROMPT_ID: Final = "card.markup"
"""The registered prompt that answers with a :class:`MarkupSuggestion`."""

MAX_TAG_CHARACTERS: Final = 300
"""Longest tag a model may suggest. A tag is one claim sentence; this only stops an essay."""

MAX_RATIONALE_CHARACTERS: Final = 1000
"""Longest rationale a model may give for a selection or a markup."""

MAX_PASSAGES: Final = 12
"""Most passages one selection may name. A card is one passage, or a few with cuts between them."""

MAX_MARKUP_SPANS: Final = 100
"""Most underline and highlight spans one markup answer may name."""

ParagraphNumber = Annotated[int, Field(ge=1, description="The paragraph's number, N in its [PN] label.")]
"""The number a paragraph is shown with in the numbered snapshot, counted from 1."""

ParagraphOffset = Annotated[int, Field(ge=0)]
"""A character offset into one paragraph's normalized text, in code points."""

ModelText = Annotated[str, StringConstraints(min_length=1, pattern=r"\S")]
"""Free text a model writes: not empty and not only whitespace. Never stripped or otherwise changed."""


class ArgumentRole(StrEnum):
    """What a card does for the argument the research need belongs to."""

    UNIQUENESS = "uniqueness"
    """The status quo: the link or impact has not happened yet, or is about to."""

    LINK = "link"
    """The plan or the opponent's action causes the effect the argument needs."""

    INTERNAL_LINK = "internal_link"
    """One step of the chain between the link and the impact."""

    IMPACT = "impact"
    """Why the outcome at the end of the chain matters."""


class NeedAlignment(StrEnum):
    """How closely the selected evidence answers the research need it was asked for."""

    DIRECT = "direct"
    """The evidence makes the claim the need asks for."""

    PARTIAL = "partial"
    """The evidence supports part of the claim, or a narrower one."""

    TANGENTIAL = "tangential"
    """The evidence is related but does not make the claim; a weak card."""


class SelectedPassage(DomainModel):
    """One contiguous passage, from `start_offset` in `first_paragraph` to `end_offset` in `last_paragraph`.

    A passage over whole paragraphs leaves both offsets at their defaults. A passage inside one
    paragraph has `first_paragraph == last_paragraph`. Several passages make a card with cuts:
    whatever lies between them is omitted, and shown as omitted, never filled in.
    """

    first_paragraph: ParagraphNumber
    last_paragraph: ParagraphNumber
    start_offset: ParagraphOffset = Field(
        default=0,
        description="Where the passage starts, in first_paragraph's text; 0 is its first character.",
    )
    end_offset: Annotated[int, Field(ge=1)] | None = Field(
        default=None,
        description="Where the passage ends (exclusive), in last_paragraph's text; null for its end.",
    )


class TagSuggestion(DomainModel):
    """The tag a model suggests for a card: one claim sentence, what it does, and how well it fits."""

    text: ModelText = Field(
        max_length=MAX_TAG_CHARACTERS,
        description="The tag: one concise claim sentence in the model's own words, never quoted text.",
    )
    argument_role: ArgumentRole = Field(description="What the card does for the argument.")
    need_alignment: NeedAlignment = Field(description="How closely the card answers the research need.")
    confidence: float = Field(ge=0.0, le=1.0, description="The model's confidence in the tag, 0 to 1.")


class CardSelection(DomainModel):
    """The answer to `card.select`: where a card's evidence is, and a suggested tag. Never the evidence."""

    passages: tuple[SelectedPassage, ...] = Field(
        min_length=1, max_length=MAX_PASSAGES, description="The passages the card's evidence is cut from."
    )
    tag: TagSuggestion = Field(description="The suggested tag.")
    rationale: ModelText = Field(
        max_length=MAX_RATIONALE_CHARACTERS,
        description="Why this evidence answers the need, in the model's own words, never quoted text.",
    )
    confidence: float = Field(ge=0.0, le=1.0, description="The model's confidence in the selection, 0 to 1.")


class MarkupSpan(DomainModel):
    """Characters `[start_offset, end_offset)` of paragraph `paragraph`, underlined or highlighted.

    `style` and `purpose` are the enums a card's :class:`~debate_core.domain.CardSpan` uses, so a span
    maps onto a card without translation (`v1-e03-t07`).
    """

    paragraph: ParagraphNumber
    start_offset: ParagraphOffset = Field(description="Where the span starts, in the paragraph's text.")
    end_offset: Annotated[int, Field(ge=1)] = Field(
        description="Where the span ends (exclusive), in the paragraph's text."
    )
    style: SpanStyle = Field(description="Underline (read aloud) or highlight (emphasised).")
    purpose: SpanPurpose | None = Field(
        default=None, description="What argumentative work the marked words do, when the model can say."
    )


class MarkupSuggestion(DomainModel):
    """The answer to `card.markup`: what to underline and highlight in a selection. Never the words."""

    spans: tuple[MarkupSpan, ...] = Field(
        min_length=1, max_length=MAX_MARKUP_SPANS, description="The underlines and highlights."
    )
    rationale: ModelText = Field(
        max_length=MAX_RATIONALE_CHARACTERS,
        description="Why these words carry the argument, in the model's own words, never quoted text.",
    )


class GeneratedCardSelection(DomainModel):
    """A card selection as kept: the answer, the snapshot it selects from, and where it came from.

    `metadata` is the call's provenance with its inputs recorded, and must name exactly this
    snapshot, so a selection cannot be kept apart from the text its offsets refer to.
    """

    snapshot_id: Ulid = Field(description="The snapshot whose numbered text the selection was made in.")
    selection: CardSelection = Field(description="The model's answer, as the guard accepted it.")
    metadata: SourcedArtifactMetadata = Field(
        description="The call's provenance and the inputs it was given."
    )

    @model_validator(mode="after")
    def _metadata_names_this_selection(self) -> Self:
        _require_provenance(self.metadata, CARD_SELECT_PROMPT_ID, self.snapshot_id)
        return self


class GeneratedCardMarkup(DomainModel):
    """A markup answer as kept: the spans, the snapshot they mark, and where they came from."""

    snapshot_id: Ulid = Field(description="The snapshot whose numbered text the spans point into.")
    markup: MarkupSuggestion = Field(description="The model's answer, as the guard accepted it.")
    metadata: SourcedArtifactMetadata = Field(
        description="The call's provenance and the inputs it was given."
    )

    @model_validator(mode="after")
    def _metadata_names_this_markup(self) -> Self:
        _require_provenance(self.metadata, CARD_MARKUP_PROMPT_ID, self.snapshot_id)
        return self


def _require_provenance(metadata: SourcedArtifactMetadata, prompt_id: str, snapshot_id: str) -> None:
    if metadata.prompt_id != prompt_id:
        raise ValueError(f"the metadata is for prompt {metadata.prompt_id}, not {prompt_id}")
    if metadata.snapshot_ids != (snapshot_id,):
        raise ValueError(
            f"the metadata records {len(metadata.snapshot_ids)} snapshot inputs; it must record exactly "
            f"the snapshot {snapshot_id}"
        )

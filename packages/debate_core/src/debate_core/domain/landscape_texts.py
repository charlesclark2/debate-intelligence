"""A team's own analytic texts in the landscape report: what is kept, quoted and counted (`v1-e32-t11`).

`v1-e32-t11` reads, from each source's own paragraphs, the four kinds of analytic text the coach asked
for on 2026-10-24, and places each under the position its section is placed under, by `v1-e32-t02`'s
matcher. This module is what is kept of one such text (:class:`AnalyticTextReading`, never its words)
and what the report shows of them (:class:`LandscapeTexts`).

## What is quoted, and what is only counted (the PM's rulings of 2026-10-24)

* **CP texts, K alternatives and roles of the ballot** are quoted word for word, as data-use policy 1.13
  allows: in report.md only, never beside a school or team code, and a text naming a school of the
  caselist withheld and counted. Each CP and K shows its top distinct texts, grouped by their normalized
  words, with the teams reading each, then how many more texts and teams there are.
* **Overviews** are counted only: per position, on each side, the teams with one. The coach's decision of
  2026-10-24: policy 1.13 does not list overviews, so no overview text is kept, cached or shown.

## What is never here

No school, team code or debater's name, and no text in a reading: a reading holds the place, unit and
digest of its text. The report's quoted texts are read again from the source, checked against that
digest, when the report is built.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Self

from pydantic import Field, model_validator

from debate_core.domain.base import DomainModel, NonEmptyText, Sha256Hex
from debate_core.domain.landscape import PositionId, PositionKind
from debate_core.domain.landscape_classification import PositionRole
from debate_core.domain.style_profile import StructuralUnit

__all__ = [
    "DEFAULT_TEXTS_PER_POSITION",
    "POSITION_KIND_OF",
    "QUOTED_KINDS",
    "AnalyticTextKind",
    "AnalyticTextReading",
    "LandscapeTexts",
    "MoreTexts",
    "OverviewCount",
    "PositionTexts",
    "QuotedText",
    "TextCoverage",
    "TextForm",
    "TextPlacement",
]

DEFAULT_TEXTS_PER_POSITION: Final = 3
"""How many distinct texts a CP or K shows (the PM's ruling of 2026-10-24)."""


class AnalyticTextKind(StrEnum):
    CP_TEXT = "CP_TEXT"
    K_ALTERNATIVE = "K_ALTERNATIVE"
    ROLE_OF_THE_BALLOT = "ROLE_OF_THE_BALLOT"
    OVERVIEW = "OVERVIEW"
    """Counted only: no digest, no text."""


QUOTED_KINDS: Final = (
    AnalyticTextKind.CP_TEXT,
    AnalyticTextKind.K_ALTERNATIVE,
    AnalyticTextKind.ROLE_OF_THE_BALLOT,
)
"""The kinds the report quotes, in report order."""

POSITION_KIND_OF: Final = {
    AnalyticTextKind.CP_TEXT: PositionKind.CP,
    AnalyticTextKind.K_ALTERNATIVE: PositionKind.K,
    AnalyticTextKind.ROLE_OF_THE_BALLOT: PositionKind.K,
}
"""The kind of position a quoted text must be placed under to be shown."""


class TextForm(StrEnum):
    LABEL = "LABEL"
    """A label paragraph of its own (`Alt`, `Role of the ballot`, `Overview`); the text is the next one."""
    INLINE = "INLINE"
    """A label opening the paragraph that holds the text (`Text: The fifty states should ...`)."""
    SENTENCE = "SENTENCE"
    """The paragraph is the text, opening with the label's words (`The alternative is ...`)."""
    BY_PLACE = "BY_PLACE"
    """No label: the first `should` analytic of a block placed under a CP, past the actor guard."""


class TextPlacement(StrEnum):
    PLACED = "PLACED"
    """The nearest placed heading over the label places it under a position."""
    HEADINGS_PLACE_NOTHING = "HEADINGS_PLACE_NOTHING"
    """Headings are over it, and none is an alias or an override (`1NC`, `OFF`)."""
    NO_HEADING = "NO_HEADING"
    """No heading over it says anything once normalized."""


class AnalyticTextReading(DomainModel):
    """What is kept of one analytic text of one source: where it is and what places it. Never its words."""

    kind: AnalyticTextKind
    form: TextForm
    label_element_index: int = Field(
        ge=0, description="The label's paragraph; the text's own for a sentence."
    )
    element_index: int = Field(ge=0, description="The paragraph holding the text.")
    unit: StructuralUnit = Field(description="The unit of the paragraph holding the text.")
    kept: bool = Field(description="Whether that paragraph is inside a card the parsed store holds.")
    digest: Sha256Hex | None = Field(
        default=None, description="SHA-256 of the text's lowercase words; None for an overview."
    )
    placement: TextPlacement
    position_id: PositionId | None = None
    role: PositionRole | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        if (self.kind is AnalyticTextKind.OVERVIEW) != (self.digest is None):
            raise ValueError("an overview keeps no digest, and every quoted kind keeps one")
        if (self.placement is TextPlacement.PLACED) != (self.position_id is not None):
            raise ValueError("a placed text names its position, and only a placed one does")
        if (self.position_id is None) != (self.role is None):
            raise ValueError("a position and its role go together")
        if self.form is TextForm.BY_PLACE and self.kind is not AnalyticTextKind.CP_TEXT:
            raise ValueError("only a CP text is read by its place")
        return self


class QuotedText(DomainModel):
    """One of a position's top texts: a row of its table in report.md."""

    position_id: PositionId
    kind: AnalyticTextKind
    rank: int = Field(ge=1)
    teams: int = Field(ge=0, description="Distinct teams whose files hold it under the position.")
    text: str = Field(repr=False, description="Word for word, as one of its files holds it.")


class MoreTexts(DomainModel):
    """The texts of a position past the cut-off: `and N more texts, read by M teams`."""

    position_id: PositionId
    kind: AnalyticTextKind
    texts: int = Field(ge=1)
    teams: int = Field(ge=0)


class PositionTexts(DomainModel):
    """One CP's or K's texts of one kind: its top texts, and the rest as a count."""

    position_id: PositionId
    label: NonEmptyText
    kind: AnalyticTextKind
    texts: tuple[QuotedText, ...] = Field(min_length=1, description="By rank.")
    more: MoreTexts | None = None


class TextCoverage(DomainModel):
    """What one kind's labels came to: how many were shown, and why the rest were not."""

    kind: AnalyticTextKind
    labels: int = Field(ge=0, description="Texts found in the range's files, labelled or by their place.")
    documents: int = Field(ge=0, description="Files holding one.")
    counted: int = Field(ge=0, description="Placed under a position of the kind, read on its side.")
    elsewhere: int = Field(
        ge=0,
        description="Placed under another kind of position, as an answer, or in a round on the other side.",
    )
    headings_place_nothing: int = Field(ge=0)
    no_heading: int = Field(ge=0)
    withheld_texts: int = Field(
        ge=0, description="Distinct texts naming a school of the caselist: not shown."
    )
    unread: int = Field(ge=0, description="Counted texts that could not be read again as they were read.")
    refused_by_guard: int = Field(
        default=0, ge=0, description="CP only: first `should` analytics under a CP the actor guard left out."
    )

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.counted + self.elsewhere + self.headings_place_nothing + self.no_heading != self.labels:
            raise ValueError("every text found is counted, placed elsewhere, or not placed")
        return self

    @property
    def unplaced(self) -> int:
        return self.headings_place_nothing + self.no_heading


class OverviewCount(DomainModel):
    """One position's overviews: the teams with one, on each side. No text."""

    position_id: PositionId
    label: NonEmptyText
    position_kind: PositionKind
    aff_teams: int = Field(ge=0)
    neg_teams: int = Field(ge=0)
    teams: int = Field(ge=0, description="Distinct teams with an overview under it, on either side.")


class LandscapeTexts(DomainModel):
    """The report's analytic texts: quoted rows per CP and K, and overview counts per position."""

    texts_per_position: int = Field(ge=1)
    positions: tuple[PositionTexts, ...] = Field(
        description="By kind, then by the teams with a text under the position, then position id."
    )
    coverage: tuple[TextCoverage, ...] = Field(
        description="One per kind, in :class:`AnalyticTextKind` order."
    )
    overviews: tuple[OverviewCount, ...] = Field(description="By teams with an overview, then position id.")

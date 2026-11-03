"""Where what was read from each affirmative file's plan text is cached (`v1-e32-t09`).

Reading a plan text means parsing the source again (the parsed card store keeps no analytics), about
0.3 s a file, so a weekly run reads only the sources it has not read before. Each reading is kept
per caselist under a :class:`PlanTextKey`:

* **the source's digest** and **the parser version** that read it: a parser bump reads every source
  again;
* **the vocabulary digest**
  (:attr:`~debate_core.arguments.landscape.plan_text.PlanTextVocabulary.digest`): the words that name
  each aff, and the reading rules. An alias or tag keyword the coach adds reads every source again.

What is kept is derived, never text (the PM's ruling of 2026-10-24): each plan text's place, unit,
whether the store keeps it, whether it reads like a plan text, a digest of its words, and the aff ids
it names. A source the parser refused is kept as unreadable, so it is not parsed again each week;
one whose bytes could not be read at all is not kept, and is tried again.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import NamedTuple, Protocol, runtime_checkable

from pydantic import Field

from debate_core.arguments.landscape.kritikal_aff import KritikalMarkerKind
from debate_core.domain.base import DomainModel, NonEmptyText, Sha256Hex
from debate_core.domain.landscape import PositionId
from debate_core.domain.landscape_texts import TextForm
from debate_core.domain.style_profile import StructuralUnit

__all__ = [
    "CachedKritikalMarker",
    "CachedPlanText",
    "CachedPlanTextParagraph",
    "PlanTextKey",
    "PlanTextStore",
]


class PlanTextKey(NamedTuple):
    source_sha256: str
    parser_version: str
    vocabulary_digest: str


class CachedPlanTextParagraph(DomainModel):
    """One plan text of a source, as :class:`~debate_core.arguments.landscape.plan_text.PlanTextParagraph`."""

    label_element_index: int = Field(ge=0)
    element_index: int = Field(ge=0)
    unit: StructuralUnit
    kept: bool
    shaped: bool
    digest: Sha256Hex
    named: tuple[PositionId, ...]


class CachedKritikalMarker(DomainModel):
    """One K-aff marker of a source, as :class:`~debate_core.arguments.landscape.kritikal_aff.KritikalMarker`:
    its kind, how it was written, where it is and its unit. Never its words (`v1-e32-t17`)."""

    kind: KritikalMarkerKind
    form: TextForm
    element_index: int = Field(ge=0)
    unit: StructuralUnit


class CachedPlanText(DomainModel):
    """One source's reading under one key: a line of the caselist's plan-text cache."""

    source_sha256: Sha256Hex
    parser_version: NonEmptyText
    vocabulary_digest: Sha256Hex
    readable: bool = Field(description="False when the parser refused the source.")
    paragraphs: tuple[CachedPlanTextParagraph, ...] = ()
    kritikal_markers: tuple[CachedKritikalMarker, ...] = ()
    heading_families: tuple[PositionId, ...] = Field(
        default=(), description="The K families the source's headings name, by id (`v1-e32-t17`)."
    )
    transition_paragraphs: tuple[CachedPlanTextParagraph, ...] = Field(
        default=(),
        description="Its plan texts under a transition label (`Thus the plan`, `Thus`), kept apart from "
        "t09's so no verdict of t09's changes (`v1-e32-t24`).",
    )

    @property
    def key(self) -> PlanTextKey:
        return PlanTextKey(self.source_sha256, self.parser_version, self.vocabulary_digest)


@runtime_checkable
class PlanTextStore(Protocol):
    """One machine's plan-text cache, per caselist."""

    async def read(self, caselist: str) -> tuple[CachedPlanText, ...]:
        """Every cached reading of `caselist`; empty when none was ever written."""
        ...

    async def replace(self, caselist: str, entries: Sequence[CachedPlanText]) -> None:
        """Make `entries` the caselist's whole cache, atomically."""
        ...

"""Where what was read of each source's analytic texts is cached (`v1-e32-t11`).

Reading a CP text, an alternative, a role of the ballot or an overview means parsing the source again
(the parsed card store keeps no analytics), about 0.25 s a file, so a weekly run reads only the sources
it has not read before. Each reading is kept per caselist under an :class:`AnalyticTextKey`, the PM's
ruling of 2026-10-24:

* **the source's digest** and **the parser version** that read it: a parser bump reads every source
  again;
* **the rules digest** (:attr:`~debate_core.arguments.landscape.analytic_texts.AnalyticTextRules.digest`):
  the labels, the reading rules, the CP texts' actor list, the taxonomy's positions and the coach's
  overrides. A text's position is cached with it, so a taxonomy or overrides edit reads every source
  again, once.

What is kept is derived, never text: each text's kind, form, place, unit, whether the store keeps it, a
digest of its words (none for an overview), and the position it is placed under. A source the parser
refused is kept as unreadable, so it is not parsed again each week; one whose bytes could not be read
at all is not kept, and is tried again.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import NamedTuple, Protocol, runtime_checkable

from pydantic import Field

from debate_core.domain.base import DomainModel, NonEmptyText, Sha256Hex
from debate_core.domain.landscape_texts import AnalyticTextReading

__all__ = ["AnalyticTextKey", "AnalyticTextStore", "CachedAnalyticTexts"]


class AnalyticTextKey(NamedTuple):
    source_sha256: str
    parser_version: str
    rules_digest: str


class CachedAnalyticTexts(DomainModel):
    """One source's reading under one key: a line of the caselist's analytic-text cache."""

    source_sha256: Sha256Hex
    parser_version: NonEmptyText
    rules_digest: Sha256Hex
    readable: bool = Field(description="False when the parser refused the source.")
    readings: tuple[AnalyticTextReading, ...] = ()
    refused_by_guard: int = Field(default=0, ge=0)
    planks_refused_by_guard: int = Field(
        default=0, ge=0, description="List planks left out because their CP text fails the actor guard."
    )
    plank_labels: int = Field(
        default=0, ge=0, description="List paragraphs that are only an advantage's alias (`v1-e32-t16`)."
    )

    @property
    def key(self) -> AnalyticTextKey:
        return AnalyticTextKey(self.source_sha256, self.parser_version, self.rules_digest)


@runtime_checkable
class AnalyticTextStore(Protocol):
    """One machine's analytic-text cache, per caselist."""

    async def read(self, caselist: str) -> tuple[CachedAnalyticTexts, ...]:
        """Every cached reading of `caselist`; empty when none was ever written."""
        ...

    async def replace(self, caselist: str, entries: Sequence[CachedAnalyticTexts]) -> None:
        """Make `entries` the caselist's whole cache, atomically."""
        ...

"""Where position classifications are cached, and where the review queue is written (`v1-e32-t02`).

A weekly run classifies only what it has not classified before, whether a weekly window or a complete
archive brings the item (weekly archives are windows, not cumulative: `v1-e30-t17`). So results are
kept per caselist, each under a :class:`ClassificationKey`:

* **the topic and its taxonomy version**: a version bump makes every result of that topic a miss,
  and touches no other topic's, so an LD caselist's two topics keep their own;
* **the override digest**: a digest of the coach's decisions on the headings over the item
  (:meth:`~debate_core.domain.landscape_classification.OverrideRules.digest_for`), so a decision
  makes only the items under its heading a miss;
* **the prompt version**: `none` for every deterministic result; from `v1-e32-t07`, a prompt bump
  makes only MODEL results a miss;
* **the item fingerprint**: a digest of what placement reads (the normalized headings and the tag's
  words), so two items read alike share one result.

What is kept is a result: ids, a confidence, a method and a rationale that names the rule and the
taxonomy or override text it matched. No heading, tag or path is in it. The review queue's CSV
holds normalized headings with counts and candidate ids, and is written to this machine's data
directory beside the cache, never to the repository.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import NamedTuple, Protocol, Self, runtime_checkable

from pydantic import Field, model_validator

from debate_core.arguments.landscape.review_queue import ReviewRow
from debate_core.domain.base import DomainModel, NonEmptyText, Sha256Hex
from debate_core.domain.landscape import PositionId, TaxonomyVersion
from debate_core.domain.landscape_classification import ClassificationResult

__all__ = ["CachedClassification", "ClassificationKey", "ClassificationStore"]


class ClassificationKey(NamedTuple):
    """What a cached result is valid for."""

    topic_id: str
    taxonomy_version: str
    override_digest: str
    prompt_version: str
    item_fingerprint: str


class CachedClassification(DomainModel):
    """One cached result and the key it was placed under: a line of the caselist's cache file."""

    topic_id: PositionId
    taxonomy_version: TaxonomyVersion
    override_digest: NonEmptyText = Field(
        description="`none`, or the digest of the decisions on its headings."
    )
    prompt_version: NonEmptyText = Field(description="`none` for a deterministic result.")
    item_fingerprint: Sha256Hex
    result: ClassificationResult

    @model_validator(mode="after")
    def _check_key(self) -> Self:
        if self.result.taxonomy_version != self.taxonomy_version:
            raise ValueError("a cached result is kept under the taxonomy version it was placed under")
        if self.result.prompt_version != self.prompt_version:
            raise ValueError("a cached result is kept under the prompt version that wrote it")
        return self

    @property
    def key(self) -> ClassificationKey:
        return ClassificationKey(
            self.topic_id,
            self.taxonomy_version,
            self.override_digest,
            self.prompt_version,
            self.item_fingerprint,
        )


@runtime_checkable
class ClassificationStore(Protocol):
    """One machine's classification cache and review queue files, per caselist."""

    async def read(self, caselist: str) -> tuple[CachedClassification, ...]:
        """Every cached result of `caselist`; empty when none was ever written."""
        ...

    async def replace(self, caselist: str, entries: Sequence[CachedClassification]) -> None:
        """Make `entries` the caselist's whole cache, atomically."""
        ...

    async def write_review_queue(
        self, caselist: str, topic_id: str, rows: Sequence[ReviewRow], *, suggestions: bool = False
    ) -> str:
        """Write `caselist`'s queue CSV on `topic_id`, replacing the last one; return where it went.

        `suggestions` writes the local proxy model's suggestion column, for a queue it ordered (`v1-e32-t26`).
        """
        ...

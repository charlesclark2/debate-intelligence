"""The review queue's order model: its file, and when it may order a run's queue (`v1-e32-t26`).

`scripts/compare_local_classifier.py train-queue-order` trains `v1-e32-t21`'s proxy on a caselist's
feature table, as t21's comparison does (the same seed, the same nine tenths), and writes its weights
with the threshold t21's rule gives it and what it was trained from (:class:`QueueOrderModelFile`).
A classification run reads it through :class:`ReviewQueueOrdering` and orders its review queue by it
(:mod:`~debate_core.arguments.landscape.queue_order`). Nothing is placed by it.

The model orders nothing, and the queue is exactly today's, when :meth:`ReviewQueueOrdering.load`
finds:

* no model trained for the caselist and topic;
* a file it cannot read as one;
* a model trained under another taxonomy version than the topic's now, whose positions may be gone;
* a removal that has reached any source it was trained from: t21's check
  (:func:`sources_a_removal_reached`), the one that refuses a feature table. The model is derived from
  that table, so it stands or falls with it.

Each case gives the one line the run prints instead (:attr:`QueueOrderLoad.note`). This module never
imports scikit-learn: scoring needs only the weights, so an installed build orders its queue too.
"""

from __future__ import annotations

import json
from collections.abc import Collection, Iterable
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Final, cast

from debate_core.application.caselist.suppression import load_suppression_state
from debate_core.application.ports.parsed_store import ParsedStore, SourceOutcome
from debate_core.application.ports.queue_order_model_store import QueueOrderModelStore
from debate_core.application.ports.suppression import SuppressionList
from debate_core.arguments.landscape.queue_order import QueueOrderModel
from debate_core.domain.landscape import Taxonomy

__all__ = [
    "QUEUE_ORDER_MODEL_SCHEMA",
    "QueueOrderLoad",
    "QueueOrderModelFile",
    "ReviewQueueOrdering",
    "TRAIN_COMMAND",
    "model_file_text",
    "read_model_file",
    "sources_a_removal_reached",
]

QUEUE_ORDER_MODEL_SCHEMA: Final = "review-queue-order-model-1"

TRAIN_COMMAND: Final = "scripts/compare_local_classifier.py train-queue-order"

_OFF: Final = "Review queue order: off, today's order kept"


async def sources_a_removal_reached(
    caselist: str,
    version: str,
    sources: Collection[str],
    suppressed_at_build: Iterable[tuple[str, str]],
    *,
    store: ParsedStore,
    suppression: SuppressionList,
) -> frozenset[str]:
    """Of `sources`, read from `caselist`'s parsed `version`, the ones a removal has reached since.

    One is reached when the store's version no longer holds it parsed, when it is suppressed whole, or
    when one of its disclosures is suppressed that was not (`suppressed_at_build`) when it was read.
    `v1-e32-t21`'s rule for a feature table, and so for the model trained from one.
    """
    wanted = frozenset(sources)
    entries = await store.read_entries(caselist, version)
    parsed = {entry.source_sha256 for entry in entries if entry.outcome is SourceOutcome.PARSED}
    state = await load_suppression_state(suppression)
    built = set(suppressed_at_build)
    newly = {sha for sha, disclosure in state.disclosures if sha in wanted and (sha, disclosure) not in built}
    return frozenset(sha for sha in wanted if sha not in parsed or sha in state.sources or sha in newly)


@dataclass(frozen=True, slots=True)
class QueueOrderModelFile:
    """A trained review-order model, and the feature table it was trained from."""

    caselist: str
    version: str
    """The parsed store's version directory the table was read from."""
    topic_id: str
    taxonomy_version: str
    through: date | None
    seed: int
    trained_cards: int
    sources: tuple[str, ...] = field(repr=False)
    """Every source of the table, sorted: what a removal is checked against."""
    suppressed_at_build: tuple[tuple[str, str], ...] = field(repr=False)
    """The table's disclosure suppressions when it was built, as t21 keeps them."""
    model: QueueOrderModel = field(repr=False)


def model_file_text(file: QueueOrderModelFile) -> str:
    """The file as JSON: what it was trained from, then the weights."""
    document = {
        "schema": QUEUE_ORDER_MODEL_SCHEMA,
        "caselist": file.caselist,
        "version": file.version,
        "topic_id": file.topic_id,
        "taxonomy_version": file.taxonomy_version,
        "through": None if file.through is None else file.through.isoformat(),
        "seed": file.seed,
        "trained_cards": file.trained_cards,
        "sources": sorted(file.sources),
        "suppressed_at_build": [list(pair) for pair in file.suppressed_at_build],
        "model": file.model.to_json(),
    }
    return json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n"


def read_model_file(text: str) -> QueueOrderModelFile:
    """A file :func:`model_file_text` wrote. Raises `ValueError` on another schema or a malformed one."""
    try:
        loaded: object = json.loads(text)
    except json.JSONDecodeError:
        raise ValueError("not JSON") from None
    data = cast(dict[str, Any], loaded) if isinstance(loaded, dict) else {}
    if data.get("schema") != QUEUE_ORDER_MODEL_SCHEMA:
        raise ValueError(f"not a {QUEUE_ORDER_MODEL_SCHEMA} file")
    try:
        through = data["through"]
        return QueueOrderModelFile(
            caselist=str(data["caselist"]),
            version=str(data["version"]),
            topic_id=str(data["topic_id"]),
            taxonomy_version=str(data["taxonomy_version"]),
            through=None if through is None else date.fromisoformat(str(through)),
            seed=int(data["seed"]),
            trained_cards=int(data["trained_cards"]),
            sources=tuple(str(one) for one in data["sources"]),
            suppressed_at_build=tuple((str(sha), str(digest)) for sha, digest in data["suppressed_at_build"]),
            model=QueueOrderModel.from_json(cast(dict[str, object], data["model"])),
        )
    except (KeyError, TypeError) as error:
        raise ValueError(f"a malformed {QUEUE_ORDER_MODEL_SCHEMA} file: {type(error).__name__}") from None


@dataclass(frozen=True, slots=True)
class QueueOrderLoad:
    """The model a run may order its queue by, or None, and the one line the run prints about it."""

    model: QueueOrderModel | None = field(repr=False)
    note: str


class ReviewQueueOrdering:
    """Reads a caselist's review-order model, and refuses it when it no longer stands."""

    def __init__(
        self, *, models: QueueOrderModelStore, parsed_store: ParsedStore, suppression: SuppressionList
    ) -> None:
        self._models = models
        self._parsed = parsed_store
        self._suppression = suppression

    async def load(self, caselist: str, topic_id: str, taxonomy: Taxonomy) -> QueueOrderLoad:
        """The model of `caselist` on `topic_id` under `taxonomy`, or why there is none."""
        text = await self._models.read(caselist, topic_id)
        if text is None:
            return _off(f"no review-order model is trained for {caselist} on {topic_id} (`{TRAIN_COMMAND}`)")
        location = self._models.location(caselist, topic_id)
        try:
            file = read_model_file(text)
        except ValueError as error:
            return _off(f"the review-order model at {location} cannot be read ({error}); train it again")
        if (file.caselist, file.topic_id) != (caselist, topic_id):
            return _off(
                f"the review-order model at {location} was trained for {file.caselist} on {file.topic_id}; "
                "train it again"
            )
        if file.taxonomy_version != taxonomy.taxonomy_version:
            return _off(
                f"the review-order model was trained under taxonomy {file.taxonomy_version} and {topic_id} "
                f"is now {taxonomy.taxonomy_version}; train it again"
            )
        reached = await sources_a_removal_reached(
            file.caselist,
            file.version,
            file.sources,
            file.suppressed_at_build,
            store=self._parsed,
            suppression=self._suppression,
        )
        if reached:
            return _off(
                f"a removal has reached {len(reached)} of the {len(file.sources)} sources the review-order "
                f"model was trained from, or this store no longer holds them parsed; train it again "
                f"(`{TRAIN_COMMAND}`)"
            )
        model = file.model
        through = "" if file.through is None else f" through {file.through.isoformat()}"
        suggests = (
            f"a suggestion is shown at {model.suggest_from:.2f} or above"
            if model.suggest_from is not None
            else "no suggestion is shown, since no confidence reached 90% held-out precision"
        )
        return QueueOrderLoad(
            model,
            f"Review queue order: by the local proxy model's confidence, highest first (trained on "
            f"{file.trained_cards} cards{through}); {suggests}; nothing is placed by it.",
        )


def _off(reason: str) -> QueueOrderLoad:
    return QueueOrderLoad(None, f"{_OFF}: {reason}.")

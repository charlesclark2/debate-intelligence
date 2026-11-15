"""The held-out sample's own scan hits, for the operator's terminal only (`v1-e32-t50`, the PM's ruling of
2026-11-14).

An evaluation's cassette scan reads every cassette of the route's classify prompt at its version, and every
repair of it filed under the caselist, not one sample's. So a hit no trusted mark sets aside may sit in the
holdout's cassettes or in the first sample's, and `--breakdown`, which lists hits, refuses a holdout. This
module keeps the texts that are the holdout's own and lists their hits:

* a `landscape.classify_position` cassette whose request's `items` are a card list the holdout's replay
  sent;
* a `model.repair` cassette whose failed prompt holds such a list.

A hit is the scan's (:mod:`~debate_core.arguments.landscape.scan_hits`): which text, the field, its kind,
the words and the words around them, and its marks. Nothing here names a sample row, a card's outcome or an
answer's position.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from typing import cast

from debate_core.arguments.landscape.scan_hits import (
    ScanHit,
    ScanNames,
    cassette_hits,
    input_batch_hits,
    repair_cassette_hits,
    sets_aside,
)

__all__ = ["HoldoutScanHits", "holdout_scan_hits", "own_cassettes", "own_repairs"]


@dataclass(frozen=True, slots=True)
class HoldoutScanHits:
    """The holdout's own texts' hits, numbered in this order: its input batches', its cassettes', then its
    repair cassettes'. For the operator's terminal only; :attr:`left` is a count that may be written down."""

    hits: tuple[ScanHit, ...]
    input_batches: int
    cassettes: int
    repair_cassettes: int

    @property
    def left(self) -> int:
        """How many hits carry no mark that sets a hit aside: the ones that keep a scan unclean."""
        return sum(not sets_aside(hit) for hit in self.hits)


def _loaded(value: object) -> object:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return value


def _variables(cassette: str) -> dict[str, object]:
    document = _loaded(cassette)
    for key in ("request", "prompt", "variables"):
        if not isinstance(document, dict):
            return {}
        document = cast(dict[str, object], document).get(key)
    return cast(dict[str, object], document) if isinstance(document, dict) else {}


def _sent_lists(sent_inputs: Iterable[str]) -> list[object]:
    return [one for one in map(_loaded, sent_inputs) if isinstance(one, list)]


def own_cassettes(cassettes: Iterable[str], sent_inputs: Sequence[str]) -> list[str]:
    """The classify cassettes whose request's `items` are a card list the holdout's replay sent."""
    sent = _sent_lists(sent_inputs)
    return [
        text
        for text in cassettes
        if (items := _loaded(_variables(text).get("items"))) is not None and items in sent
    ]


def _card_lists(turn: str) -> Iterator[object]:
    """Every JSON list in a rendered turn: the classify prompt renders its `items` into its user turn."""
    decoder = json.JSONDecoder()
    start = turn.find("[")
    while start != -1:
        try:
            value, end = decoder.raw_decode(turn, start)
        except json.JSONDecodeError:
            start = turn.find("[", start + 1)
            continue
        if isinstance(value, list):
            yield value
        start = turn.find("[", end)


def own_repairs(repairs: Iterable[str], sent_inputs: Sequence[str]) -> list[str]:
    """The repair cassettes whose failed prompt holds a card list the holdout's replay sent."""
    sent = _sent_lists(sent_inputs)
    found: list[str] = []
    for text in repairs:
        variables = _variables(text)
        turns = [
            value for key in ("failed_system", "failed_user") if isinstance(value := variables.get(key), str)
        ]
        if any(listed in sent for turn in turns for listed in _card_lists(turn)):
            found.append(text)
    return found


def holdout_scan_hits(
    sent_inputs: Sequence[str], cassettes: Sequence[str], repairs: Sequence[str], names: ScanNames
) -> HoldoutScanHits:
    """The hits of the holdout's input batches and of its own cassettes and repairs, read as the scan reads
    them. `cassettes` and `repairs` are the texts the evaluation scans; only the holdout's are kept."""
    kept, mended = own_cassettes(cassettes, sent_inputs), own_repairs(repairs, sent_inputs)
    hits = (
        *(
            hit
            for number, text in enumerate(sent_inputs, start=1)
            for hit in input_batch_hits(f"input batch {number}", text, names)
        ),
        *(
            hit
            for number, text in enumerate(kept, start=1)
            for hit in cassette_hits(f"cassette {number}", text, names)
        ),
        *(
            hit
            for number, text in enumerate(mended, start=1)
            for hit in repair_cassette_hits(f"repair cassette {number}", text, names)
        ),
    )
    return HoldoutScanHits(
        hits=hits, input_batches=len(sent_inputs), cassettes=len(kept), repair_cassettes=len(mended)
    )

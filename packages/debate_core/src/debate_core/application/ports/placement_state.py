"""The placement state: what the aggregate rebuild reads of each parsed source, kept between runs.

`v1-e31-t10`, by the PM's rulings of 2026-11-06. The rebuild places a caselist's cards from every
parsed source in its version directory, and until this task it read every source's document and
signed every distinct full body with MinHash on every run: about 30% and 50 to 80% of a rebuild. The
placement state keeps, beside the aggregates, exactly what placing a card reads of it, so that a run
reads the documents only of the sources it added and signs only their new bodies, and places every
card as a full rebuild does.

## What it holds

* **For each source it was built from**, by SHA-256: each of its cards, in the order the rebuild
  takes them (first paragraph), as a :class:`PlacedCard`: its paragraph range, completeness and exact
  fingerprint; for a full card its short-cite key, which the linker counts copies by; for an
  abbreviated or cite-only card its link key, or none. The words of both are numbers in the
  vocabulary.
* **For each distinct full body**, by exact fingerprint: its words as numbers in the vocabulary (the
  clusterer's words, :func:`~debate_core.evidence.near_duplicates.matching_words`), and its MinHash
  signature.
* **The vocabulary**: each word once.
* **Stamps**: the parser and profile versions of the directory, the fingerprint version, and a digest
  of the rules that decide what it holds (:attr:`PlacementState.rules`).

Card words as numbers plus a vocabulary, short-cite keys and digests: no path, no school, no team, no
tag, no cite beyond its short-cite key, nothing `parsed/` does not already hold (the PM's ruling,
item 1). A source the suppression list stops is not in it, because it is not placed.

## When it is used

Only when it is readable and every stamp matches, and its sources are exactly the ones the rebuild
places less the ones this run added (the ruling's item 2). Anything else is a full rebuild, which
writes a new state. Deleting it is always safe: the next run rebuilds in full.
"""

from __future__ import annotations

from array import array
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from debate_core.application.errors import DomainError
from debate_core.domain.debate_files import CardCompleteness

__all__ = [
    "PLACEMENT_STATE_NAME",
    "PLACEMENT_STATE_SCHEMA_VERSION",
    "PlacedAnchor",
    "PlacedBody",
    "PlacedCard",
    "PlacementState",
    "UnreadablePlacementState",
]

PLACEMENT_STATE_NAME: Final = "placement-state.sqlite"
"""The state's file in a version directory, beside the aggregates, here and in the bucket."""

PLACEMENT_STATE_SCHEMA_VERSION: Final = 1
"""The file's layout. A file of another layout is not read: the run rebuilds in full."""

type WordNumbers = tuple[int, ...]


@dataclass(frozen=True, slots=True)
class PlacedAnchor:
    """An abbreviated card's link key (:class:`~debate_core.evidence.abbreviated_links.AbbreviationAnchor`),
    its words as numbers in the vocabulary."""

    short_cite_key: WordNumbers
    opening_words: WordNumbers
    closing_words: WordNumbers
    from_cite_line: bool


@dataclass(frozen=True, slots=True)
class PlacedCard:
    """What placing one card reads of it, and where its rows point."""

    first_element: int
    last_element: int
    completeness: CardCompleteness
    fingerprint: str
    short_cite_key: WordNumbers | None
    """A full card's short-cite key, which the linker counts its copies under; `None` for a card with
    none, and for every abbreviated or cite-only card, whose key is in its anchor."""
    anchor: PlacedAnchor | None
    """An abbreviated or cite-only card's link key; `None` for a full card and for one with no key."""


@dataclass(frozen=True, slots=True)
class PlacedBody:
    """One distinct full body: its words as numbers, and its MinHash signature (`None` for a body with
    no words, which is never signed)."""

    words: array[int]
    signature: array[int] | None


@dataclass(frozen=True, slots=True)
class PlacementState:
    """A version directory's placement state (this module's docstring)."""

    parser_version: str
    profile_version: str
    fingerprint_version: str
    rules: str
    """Digest of what decides the state's contents beside the fingerprint version: the clusterer's
    shingle size, MinHash permutations and seed, the linker's fewest anchor words, and the ellipsis
    markers (:func:`~debate_core.application.caselist_card_stats.placement_rules`)."""
    vocabulary: tuple[str, ...]
    sources: Mapping[str, tuple[PlacedCard, ...]]
    """Each source it was built from, by SHA-256, to its cards in the order the rebuild takes them."""
    bodies: Mapping[str, PlacedBody]
    """Each distinct full body its sources' full cards have, by exact fingerprint."""


class UnreadablePlacementState(DomainError):
    """The state's file is there and cannot be read: not this layout, damaged, or inconsistent.

    Never names a word of it. The rebuild that meets one rebuilds in full and writes a new one.
    """

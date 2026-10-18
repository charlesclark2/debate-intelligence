"""How two card bodies overlap, read from their five-word runs, and which overlaps a rule decides
(`v1-e31-t21`).

:mod:`debate_core.evidence.near_duplicates` decides which bodies share a cluster. This module
describes a pair of bodies that already share one, or that a sample is about to show a person, and
says nothing about where either belongs. It reads shingle sets and returns shapes and counts, never
a word of a body.

## A pair's shape

Both bodies are cut into :data:`~debate_core.evidence.near_duplicates.SHINGLE_SIZE`-word shingles
(:func:`~debate_core.evidence.near_duplicates.shingles`). The pair is measured by two
**directional shares**: the share of the first body's shingles that the second holds, and the
share of the second's that the first holds. A symmetric measure (Jaccard, or containment over the
smaller set without saying which is smaller) hides the difference between a short cut inside a
long card and two long cards that happen to share a paragraph, which is the difference a person
is asked about.

:class:`PairShape`, from the shares, in this order:

* **identical**: each body holds at least :data:`IDENTICAL_SHARE` of the other's shingles.
* **contained**: the larger holds at least :data:`CONTAINED_SHARE` of the smaller's. Split by
  size, because a cut a fifth the length of the card it is cut from is a different question from
  two cuts a word apart: the smaller is under :data:`SMALL_PART_OF_THE_LARGER` of the larger, or it
  is that or more. "Smaller" and "larger" are by shingle count.
* **overlapping**: from :data:`OVERLAPPING_SHARE` to :data:`CONTAINED_SHARE` of the smaller's
  shingles are shared.
* **sharing a little**: some shingle is shared, under :data:`OVERLAPPING_SHARE` of the smaller's.
* **sharing nothing**: no shingle in common. This shape has no threshold, so a count of it does
  not depend on the constants above: it is the measure the PM recorded for the largest clusters on
  2026-10-16, which :func:`debate_core.evidence.cluster_diagnosis.cluster_shape` also counts.

A body with no words has no shingles and no shape (:func:`pair_shares` refuses it).

## What a rule decides

The PM's ruling of 2026-10-16: a card is a passage. Two bodies are one card when one holds the
other or they overlap; two passages of one article are two cards. A rule can therefore answer for
the two ends of the scale, and :func:`rule_verdict` does:

* identical and contained pairs are the **same card**;
* pairs sharing nothing are **different cards**;
* every other shape is left for a person.

`scripts/compare_card_clusters.py` counts the pairs a rule decides and shows a person only the rest.
Narrowing the band a person sees (deciding some overlapping pairs by rule, say) is a change to
:data:`RULE_VERDICTS`, made from the tallies of the shapes people were asked about.

## Pairs sharing only a few runs

The clusterer refuses a join that would put two texts sharing no shingle in one cluster
(`card-fingerprint-v4`, `v1-e31-t20`), so one shingle in common is enough to get past that guard. A
stock phrase five words long is one shingle. :func:`pairs_sharing_few_runs` counts a cluster's pairs
that share at least one shingle and no more than :data:`FEW_RUNS`, by how many they share: the PM's
measure (2026-10-18) of whether stock phrases bridge different cards. It is a count beside the
shapes, not a shape: such a pair is usually sharing a little, but two bodies of a few words can be
identical on one shingle.
"""

from __future__ import annotations

import statistics
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from debate_core.evidence.near_duplicates import SHINGLE_SIZE, matching_words, word_shingles

__all__ = [
    "CONTAINED_SHARE",
    "FEW_RUNS",
    "IDENTICAL_SHARE",
    "OVERLAPPING_SHARE",
    "RULE_VERDICTS",
    "SMALL_PART_OF_THE_LARGER",
    "ClusterPairShapes",
    "PairShape",
    "PairShares",
    "RuleVerdict",
    "cluster_pair_shapes",
    "pair_shape",
    "pair_shares",
    "pairs_sharing_few_runs",
    "rule_verdict",
    "shared_words",
]

IDENTICAL_SHARE: Final = 0.98
"""Each body holds at least this share of the other's shingles: the two are one text, give or take
a word, and neither is a cut of the other."""

CONTAINED_SHARE: Final = 0.9
"""The larger body holds at least this share of the smaller's shingles: the smaller is inside it.
The containment threshold the clusterer confirms a cut on (`NearDuplicateThresholds.containment`)."""

OVERLAPPING_SHARE: Final = 0.3
"""From this share of the smaller body's shingles up to :data:`CONTAINED_SHARE`, the pair overlaps;
under it, they share a little."""

SMALL_PART_OF_THE_LARGER: Final = 1 / 3
"""A contained body under this share of the larger body's size is a small part of it."""

FEW_RUNS: Final = 2
"""A pair sharing at least one shingle and no more than this many shares only a few runs."""


class PairShape(StrEnum):
    """How two bodies overlap, from the directional shares of their shingles."""

    IDENTICAL = "identical"
    CONTAINED_SMALL = "contained, under a third of the larger"
    CONTAINED_LARGE = "contained, a third or more of the larger"
    OVERLAPPING = "overlapping"
    SHARING_A_LITTLE = "sharing a little"
    SHARING_NOTHING = "sharing nothing"


class RuleVerdict(StrEnum):
    """What a rule says of a pair, in the words a person's verdict is tallied in."""

    SAME = "same card"
    DIFFERENT = "different card"


RULE_VERDICTS: Final[Mapping[PairShape, RuleVerdict]] = {
    PairShape.IDENTICAL: RuleVerdict.SAME,
    PairShape.CONTAINED_SMALL: RuleVerdict.SAME,
    PairShape.CONTAINED_LARGE: RuleVerdict.SAME,
    PairShape.SHARING_NOTHING: RuleVerdict.DIFFERENT,
}
"""The shapes a rule decides. A shape missing here is a person's to decide."""


@dataclass(frozen=True, slots=True)
class PairShares:
    """The shingle counts of a pair of bodies. Counts only."""

    left: int
    right: int
    shared: int

    @property
    def share_of_left(self) -> float:
        """The share of the left body's shingles that the right body holds."""
        return self.shared / self.left

    @property
    def share_of_right(self) -> float:
        """The share of the right body's shingles that the left body holds."""
        return self.shared / self.right

    @property
    def shape(self) -> PairShape:
        return pair_shape(self)


def pair_shares(left: frozenset[str], right: frozenset[str]) -> PairShares:
    """The counts of two shingle sets. Neither may be empty: a body with no words has no shape."""
    if not left or not right:
        raise ValueError("a body with no words has no shape")
    return PairShares(left=len(left), right=len(right), shared=len(left & right))


def pair_shape(shares: PairShares) -> PairShape:
    """The shape of a pair, as this module's docstring defines it."""
    if shares.shared == 0:
        return PairShape.SHARING_NOTHING
    if shares.share_of_left >= IDENTICAL_SHARE and shares.share_of_right >= IDENTICAL_SHARE:
        return PairShape.IDENTICAL
    smaller, larger = sorted((shares.left, shares.right))
    of_the_smaller = shares.shared / smaller
    if of_the_smaller >= CONTAINED_SHARE:
        if smaller < SMALL_PART_OF_THE_LARGER * larger:
            return PairShape.CONTAINED_SMALL
        return PairShape.CONTAINED_LARGE
    if of_the_smaller >= OVERLAPPING_SHARE:
        return PairShape.OVERLAPPING
    return PairShape.SHARING_A_LITTLE


def rule_verdict(shape: PairShape) -> RuleVerdict | None:
    """What a rule says of a pair of this shape, or `None` when a person has to say."""
    return RULE_VERDICTS.get(shape)


def shared_words(words: Sequence[str], other: frozenset[str]) -> tuple[bool, ...]:
    """For each of `words`, whether it is in a shingle that `other` holds.

    `words` are a body's matching words (:func:`~debate_core.evidence.near_duplicates.matching_words`)
    and `other` the other body's shingle set. A body shorter than a shingle is one shingle of all its
    words, so its words are shared together or not at all. What a display marks as text both bodies
    hold.
    """
    flags = [False] * len(words)
    ordered = word_shingles(words)
    width = min(SHINGLE_SIZE, len(words))
    for start, shingle in enumerate(ordered):
        if shingle in other:
            flags[start : start + width] = [True] * width
    return tuple(flags)


@dataclass(frozen=True, slots=True)
class ClusterPairShapes:
    """The pairs of one cluster's distinct texts, by shape, and what its texts are. Counts only."""

    distinct_texts: int
    texts_with_no_words: int
    """Distinct texts with no shingle, which are in no pair."""
    pairs: int
    """Pairs of distinct texts that both have words."""
    by_shape: Mapping[PairShape, int]
    """Every shape, a zero included."""
    pairs_sharing_few_runs: Mapping[int, int]
    """Pairs by the shingles they share, for each count from 1 to :data:`FEW_RUNS`, a zero included."""
    distinct_short_cites: int
    """Short cites of the texts' cards, compared with case and spacing ignored."""
    texts_with_no_short_cite: int
    """Distinct texts none of whose cards has a short cite."""
    words_smallest: int
    words_median: int
    words_largest: int

    def as_json(self) -> dict[str, object]:
        return {
            "distinct_texts": self.distinct_texts,
            "texts_with_no_words": self.texts_with_no_words,
            "pairs": self.pairs,
            "pairs_by_shape": {shape.value: self.by_shape[shape] for shape in PairShape},
            "share_of_pairs_by_shape": {
                shape.value: round(self.by_shape[shape] / self.pairs, 4) if self.pairs else 0.0
                for shape in PairShape
            },
            "pairs_sharing_only_few_runs": {
                str(runs): count for runs, count in sorted(self.pairs_sharing_few_runs.items())
            },
            "distinct_short_cites": self.distinct_short_cites,
            "texts_with_no_short_cite": self.texts_with_no_short_cite,
            "words_smallest": self.words_smallest,
            "words_median": self.words_median,
            "words_largest": self.words_largest,
        }


def cluster_pair_shapes(
    bodies: Mapping[str, str], short_cites: Mapping[str, Collection[str | None]]
) -> ClusterPairShapes:
    """Describe one cluster's distinct texts and every pair of them.

    `bodies` maps each distinct text's exact fingerprint to its body, and `short_cites` maps the same
    fingerprint to the short cites of the cards that hold it (`None` or blank for a card with none).
    Word counts are of matching words, over the texts that have any; the median is rounded down.
    """
    words = {fingerprint: matching_words(body) for fingerprint, body in bodies.items()}
    sets = {fingerprint: frozenset(word_shingles(text)) for fingerprint, text in words.items()}
    texts = sorted(fingerprint for fingerprint in bodies if sets[fingerprint])
    by_shape = dict.fromkeys(PairShape, 0)
    few_runs = dict.fromkeys(range(1, FEW_RUNS + 1), 0)
    for position, left in enumerate(texts):
        for right in texts[position + 1 :]:
            shares = pair_shares(sets[left], sets[right])
            by_shape[pair_shape(shares)] += 1
            if shares.shared in few_runs:
                few_runs[shares.shared] += 1

    def cite_key(cite: str | None) -> str:
        return " ".join((cite or "").split()).casefold()

    cites = {
        fingerprint: {cite_key(cite) for cite in short_cites.get(fingerprint, ())} - {""}
        for fingerprint in bodies
    }
    counts = sorted(len(words[text]) for text in texts)
    return ClusterPairShapes(
        distinct_texts=len(bodies),
        texts_with_no_words=len(bodies) - len(texts),
        pairs=sum(by_shape.values()),
        by_shape=by_shape,
        pairs_sharing_few_runs=few_runs,
        distinct_short_cites=len(set[str]().union(*cites.values())),
        texts_with_no_short_cite=sum(not held for held in cites.values()),
        words_smallest=counts[0] if counts else 0,
        words_median=int(statistics.median(counts)) if counts else 0,
        words_largest=counts[-1] if counts else 0,
    )


def pairs_sharing_few_runs(bodies: Mapping[str, str]) -> dict[int, int]:
    """One cluster's pairs of distinct texts by the shingles they share, for each count from 1 to
    :data:`FEW_RUNS`, a zero included. `bodies` maps each text's exact fingerprint to its body.

    The count :class:`ClusterPairShapes` holds, without the rest of the description: what a count
    over every cluster of a caselist needs.
    """
    sets = [frozenset(word_shingles(matching_words(body))) for body in bodies.values()]
    counts = dict.fromkeys(range(1, FEW_RUNS + 1), 0)
    for position, left in enumerate(sets):
        for right in sets[position + 1 :]:
            shared = len(left & right)
            if shared in counts:
                counts[shared] += 1
    return counts

"""Near-duplicate card clusters: word shingles, seeded MinHash, LSH buckets, confirmed overlap.

An exact fingerprint (:mod:`debate_core.evidence.fingerprints`) recognises two copies of a card
whose words are identical. Most copies are not: one team cut the card a paragraph shorter, another
kept an extra paragraph, a third pasted it out of a PDF that split `installation` into `install
ation`. This module groups those copies into one cluster without comparing every card with every
other card, which at caselist scale would be tens of billions of comparisons.

## How a cluster is found

1. **Words.** The body is put through the fingerprint normalization, a line-break hyphenation
   (`commis- sion`, a hyphen followed by whitespace) is rejoined, and the text is split into runs
   of letters and digits. Punctuation is dropped, so `shade ;` and `shade;` are the same words.
2. **Shingles.** Every run of :data:`SHINGLE_SIZE` consecutive words. A body shorter than that is
   one shingle of all its words.
3. **MinHash.** :data:`MINHASH_PERMUTATIONS` seeded hash functions stand in for random
   permutations of the shingle universe. Each is SHAKE-128 keyed by :data:`MINHASH_SEED` and the
   function's position, so a signature is the same on every machine, in every process and under any
   `PYTHONHASHSEED`. Python's `hash()` and the unseeded `random` module are never used.
4. **LSH buckets.** The signature is cut into :data:`LSH_BANDS` bands of :data:`LSH_ROWS_PER_BAND`
   values. Two bodies that agree on every value of any one band are *candidates*.
5. **Confirmation.** A candidate pair is a match when its real shingle sets have Jaccard
   similarity at least the configured threshold (0.8 by default). When both bodies are long, it is
   also a match on containment — the overlap divided by the smaller set — at least its threshold
   (0.9), which is what lets a card cut a paragraph shorter still join its cluster.
6. **Short bodies** are matched as cuts by their own step, below, not by the banding.
7. **Union-find.** Confirmed pairs are merged. The cluster id is the smallest exact fingerprint in
   the cluster.

## Short bodies (`v1-e31-t08`)

Steps 4 and 5 were built for long cards and fail short ones in two ways `v1-e31-t06` measured.
One changed word costs a body the :data:`SHINGLE_SIZE` shingles that contain it, a tenth of a long
card and a third of a 19-word one, so a typo or an OCR split drops a short card under the 0.9
containment threshold. And a short cut of a card shares so few shingles with it that the banding
rarely makes the pair a candidate at all: a third of the original is found about one time in four.
A third way was found while fixing those: the banding pairs a short body with only *some* of the
bodies that contain it, so a fragment two different cards share joined whichever it happened to be
paired with, and would have merged the two had it been paired with both.

A body is **short** when it has fewer than :data:`SHORT_BODY_SHINGLES` shingles (64 words). The
line is where the long-card rule stops needing help: the costliest change the short rule tolerates,
a word split in two inside a cut of a longer body, takes `SHINGLE_SIZE + 1` shingles from the cut,
which is a tenth of 60. At and above the line the 0.9 containment threshold already admits it.

A short body is never merged on containment through the banding. Instead:

* **Its containers are enumerated, not sampled.** Every body holding both the short body's first
  and its last shingle, and at least as large, is compared with it. Both ends inside the other body
  is what a cut of a card looks like, and looking them up is exact, so which bodies are compared no
  longer depends on the hash seed.
* **A container is confirmed** on the same containment threshold as before, or when the short body
  is in it as one run *but for one word*: changed, split in two, run together from two, dropped or
  added, with at least :data:`SHINGLE_SIZE` unchanged words on each side
  (:func:`contained_but_for_one_word`). One word, because a tenth of a short body's shingles is less
  than one word's worth. Unchanged words on both sides, because two cards from one article that
  open alike and then diverge differ from the point of divergence to the end, and a changed word
  does not.
* **It joins only when that is not a guess.** A short body joins a container's cluster when every
  confirmed container is in that one cluster, and the container is at most
  `1 / MIN_CUT_SHARE` times its size. A body inside two clusters is a cut of either, so it stays
  out of both; this is the rule abbreviated disclosures are linked by. A body whose two end
  shingles are both held by more than :data:`MAX_CONTAINER_CLUSTERS` other clusters opens and
  closes with stock phrases and is left alone without comparing them all, which is also what bounds
  the step's cost. The size limit keeps a body that is really a whole section of a file, parsed as
  one card, from gathering the short cards it contains into one cluster.

Two long bodies are matched exactly as before this step existed.

## Why the cluster id cannot depend on input order

Every step above is a function of the *set* of bodies: candidate pairs come from bucket membership
and from which bodies hold a shingle, confirmation is symmetric, and the union always makes the
smaller root the parent, so the root of a component is its smallest member however the merges
happened to be ordered. Joining a short body's cluster to its one container cluster can only make
another short body's containers fewer clusters, never more, so repeating it until nothing changes
ends in the same place whatever order it ran in. The same bodies, read from files in any order, in
any process, produce the same ids.

## What a cluster is not

Clustering never touches the text a card displays. It reads normalized words and returns ids.
Nothing here calls a model or an embedding service; the task forbids both for deduplication.

## Changing the rules

Which bodies share a cluster id is part of what
:data:`~debate_core.evidence.fingerprints.FINGERPRINT_VERSION` names. A change here that can move a
body to another cluster bumps it, as the short-body step did (`card-fingerprint-v2`), although the
exact fingerprint itself is unchanged.
"""

from __future__ import annotations

import hashlib
import re
import struct
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from typing import Final

from pydantic import Field

from debate_core.domain.base import DomainModel
from debate_core.evidence.fingerprints import normalize_for_matching

__all__ = [
    "LSH_BANDS",
    "LSH_ROWS_PER_BAND",
    "MAX_CONTAINER_CLUSTERS",
    "MINHASH_PERMUTATIONS",
    "MINHASH_SEED",
    "MIN_CUT_SHARE",
    "SHINGLE_SIZE",
    "SHORT_BODY_SHINGLES",
    "NearDuplicateThresholds",
    "cluster_near_duplicates",
    "contained_but_for_one_word",
    "containment",
    "jaccard",
    "matching_words",
    "minhash_signature",
    "shingles",
    "word_shingles",
]

SHINGLE_SIZE: Final = 5
"""Words per shingle."""

MINHASH_PERMUTATIONS: Final = 128
"""Seeded hash functions in a MinHash signature."""

LSH_BANDS: Final = 32
"""Bands the signature is cut into; two bodies sharing any one band are candidates."""

LSH_ROWS_PER_BAND: Final = 4
"""Signature values per band. `LSH_BANDS * LSH_ROWS_PER_BAND == MINHASH_PERMUTATIONS`."""

MINHASH_SEED: Final = "debate-card-minhash-v1"
"""Key for the MinHash hash functions. Changing it changes which pairs become candidates."""

SHORT_BODY_SHINGLES: Final = 60
"""A body with fewer shingles than this (under 64 words) is short, and matched as a cut by its own
step. `(SHINGLE_SIZE + 1) / (1 - 0.9)`: from here up, the default containment threshold already
admits the one changed word the short step tolerates, at its costliest."""

MIN_CUT_SHARE: Final = 0.25
"""The smallest share of a container's shingles a short body may be and still join its cluster."""

MAX_CONTAINER_CLUSTERS: Final = 8
"""A short body whose end shingles are both held by more other clusters than this is left alone."""

_SIGNATURE_BYTES: Final = 4 * MINHASH_PERMUTATIONS
_SIGNATURE_LAYOUT: Final = struct.Struct(f"<{MINHASH_PERMUTATIONS}I")
_EMPTY_SLOT: Final = 0xFFFFFFFF

#: A hyphen at a line break, once whitespace has been collapsed: `commis- sion`.
_LINE_BREAK_HYPHENATION: Final = re.compile(r"(?<=\w)- (?=\w)")
_WORD: Final = re.compile(r"\w+")

assert LSH_BANDS * LSH_ROWS_PER_BAND == MINHASH_PERMUTATIONS  # noqa: S101 - a module invariant


class NearDuplicateThresholds(DomainModel):
    """When a candidate pair counts as the same card. Read from settings; defaults are the spec's."""

    jaccard: float = Field(default=0.8, gt=0.0, le=1.0, description="Minimum shingle Jaccard similarity.")
    containment: float = Field(
        default=0.9, gt=0.0, le=1.0, description="Minimum overlap divided by the smaller shingle set."
    )


def matching_words(text: str) -> list[str]:
    """The words of `text` as the clusterer sees them: normalized, de-hyphenated, no punctuation."""
    normalized = _LINE_BREAK_HYPHENATION.sub("", normalize_for_matching(text))
    return _WORD.findall(normalized)


def word_shingles(words: Sequence[str], size: int = SHINGLE_SIZE) -> list[str]:
    """Every run of `size` consecutive words, in order; one shingle of all of them when shorter."""
    if not words:
        return []
    if len(words) < size:
        return [" ".join(words)]
    return [" ".join(words[start : start + size]) for start in range(len(words) - size + 1)]


def shingles(text: str, size: int = SHINGLE_SIZE) -> frozenset[str]:
    """Every run of `size` consecutive words in `text`; one shingle of all of them when shorter."""
    return frozenset(word_shingles(matching_words(text), size))


def minhash_signature(shingle_set: Iterable[str], seed: str = MINHASH_SEED) -> tuple[int, ...]:
    """The MinHash signature of a shingle set: per hash function, the smallest value any shingle takes.

    One SHAKE-128 digest per shingle, keyed by the seed, supplies all
    :data:`MINHASH_PERMUTATIONS` 32-bit values at once, read little-endian so the result does not
    depend on the machine's byte order.
    """
    key = seed.encode("utf-8") + b"\x00"
    minimums = [_EMPTY_SLOT] * MINHASH_PERMUTATIONS
    for shingle in shingle_set:
        digest = hashlib.shake_128(key + shingle.encode("utf-8")).digest(_SIGNATURE_BYTES)
        minimums = list(map(min, minimums, _SIGNATURE_LAYOUT.unpack(digest)))
    return tuple(minimums)


def jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    """Shared shingles over all shingles. 0.0 when both are empty."""
    union = len(left | right)
    return len(left & right) / union if union else 0.0


def containment(left: frozenset[str], right: frozenset[str]) -> float:
    """Shared shingles over the smaller set: how much of the shorter body the longer one contains."""
    smaller = min(len(left), len(right))
    return len(left & right) / smaller if smaller else 0.0


def contained_but_for_one_word(short: Sequence[str], long: Sequence[str]) -> bool:
    """Whether `short` is in `long` as one run of words, except at one word.

    The one word may be changed (`forty`, `fourty`), split in two (`students`, `stud ents`), run
    together from two, dropped or added. At least :data:`SHINGLE_SIZE` words of `short` before it
    and as many after it must be in `long` unchanged and in place: a typo is flanked by the same
    text on both sides, and two cards that open alike and then diverge are not.
    """
    opening = tuple(short[:SHINGLE_SIZE])
    if len(opening) < SHINGLE_SIZE:
        return False
    for start in range(len(long) - SHINGLE_SIZE + 1):
        if tuple(long[start : start + SHINGLE_SIZE]) != opening:
            continue
        same = SHINGLE_SIZE
        while same < len(short) and start + same < len(long) and short[same] == long[start + same]:
            same += 1
        if same == len(short):
            return True
        for from_short, from_long in _ONE_WORD_CHANGES:
            rest = short[same + from_short :]
            resume = start + same + from_long
            if len(rest) >= SHINGLE_SIZE and tuple(long[resume : resume + len(rest)]) == tuple(rest):
                return True
    return False


#: How one word differs, as (words of the short body, words of the long body) at the difference:
#: changed, split in two, run together from two, added, dropped.
_ONE_WORD_CHANGES: Final = ((1, 1), (1, 2), (2, 1), (0, 1), (1, 0))


def cluster_near_duplicates(
    bodies: Mapping[str, str],
    thresholds: NearDuplicateThresholds | None = None,
    *,
    seed: str = MINHASH_SEED,
) -> dict[str, str]:
    """Group card bodies into near-duplicate clusters.

    `bodies` maps each exact fingerprint to one body with that fingerprint (which body does not
    matter: they normalize identically). The result maps every fingerprint to its cluster id, the
    smallest fingerprint in its cluster; a body that matched nothing is its own cluster.
    """
    limits = thresholds or NearDuplicateThresholds()
    fingerprints = sorted(bodies)
    shingle_sets = {fingerprint: shingles(bodies[fingerprint]) for fingerprint in fingerprints}

    buckets: defaultdict[tuple[int, tuple[int, ...]], list[str]] = defaultdict(list)
    for fingerprint in fingerprints:
        if not shingle_sets[fingerprint]:
            continue
        signature = minhash_signature(shingle_sets[fingerprint], seed)
        for band in range(LSH_BANDS):
            rows = signature[band * LSH_ROWS_PER_BAND : (band + 1) * LSH_ROWS_PER_BAND]
            buckets[(band, rows)].append(fingerprint)

    candidates: set[tuple[str, str]] = set()
    for members in buckets.values():
        for position, left in enumerate(members):
            for right in members[position + 1 :]:
                candidates.add((left, right) if left < right else (right, left))

    parent = {fingerprint: fingerprint for fingerprint in fingerprints}
    for left, right in sorted(candidates):
        left_set, right_set = shingle_sets[left], shingle_sets[right]
        # Containment through the banding is for two long bodies; a short one is matched as a cut
        # by the step below, which finds every body that contains it instead of the ones sampled.
        both_long = min(len(left_set), len(right_set)) >= SHORT_BODY_SHINGLES
        if jaccard(left_set, right_set) >= limits.jaccard or (
            both_long and containment(left_set, right_set) >= limits.containment
        ):
            _union(parent, left, right)
    _join_short_bodies_to_their_one_container(parent, bodies, shingle_sets, limits)
    return {fingerprint: _find(parent, fingerprint) for fingerprint in fingerprints}


def _join_short_bodies_to_their_one_container(
    parent: dict[str, str],
    bodies: Mapping[str, str],
    shingle_sets: Mapping[str, frozenset[str]],
    limits: NearDuplicateThresholds,
) -> None:
    """The short-body step of this module's docstring, applied to `parent` in place."""
    fingerprints = sorted(bodies)
    words: dict[str, list[str]] = {}

    def words_of(fingerprint: str) -> list[str]:
        if fingerprint not in words:
            words[fingerprint] = matching_words(bodies[fingerprint])
        return words[fingerprint]

    ends: dict[str, tuple[str, str]] = {}
    for fingerprint in fingerprints:
        if 0 < len(shingle_sets[fingerprint]) < SHORT_BODY_SHINGLES:
            ordered = word_shingles(words_of(fingerprint))
            ends[fingerprint] = (ordered[0], ordered[-1])
    if not ends:
        return

    end_shingles = {shingle for pair in ends.values() for shingle in pair}
    holders: defaultdict[str, set[str]] = defaultdict(set)
    for fingerprint in fingerprints:
        for shingle in shingle_sets[fingerprint] & end_shingles:
            holders[shingle].add(fingerprint)

    # Per cluster as the banding left it: every container of its short bodies, and whether any of
    # them is small enough to join. `None` marks a cluster with a body too common to compare.
    containers: defaultdict[str, set[str] | None] = defaultdict(set)
    joinable: set[str] = set()
    for short, (first, last) in ends.items():
        cluster = _find(parent, short)
        short_set = shingle_sets[short]
        found = containers[cluster]
        if found is None:
            continue
        others: defaultdict[str, list[str]] = defaultdict(list)
        for holder in sorted(holders[first] & holders[last]):
            if len(shingle_sets[holder]) >= len(short_set) and _find(parent, holder) != cluster:
                others[_find(parent, holder)].append(holder)
        if len(others) > MAX_CONTAINER_CLUSTERS:
            containers[cluster] = None
            continue
        for members in others.values():
            for holder in members:
                holder_set = shingle_sets[holder]
                if len(short_set & holder_set) >= limits.containment * len(
                    short_set
                ) or contained_but_for_one_word(words_of(short), words_of(holder)):
                    found.add(holder)
                    if len(short_set) >= MIN_CUT_SHARE * len(holder_set):
                        joinable.add(cluster)
                    break  # one confirmed container says this cluster holds the short body

    pending = {cluster: found for cluster, found in containers.items() if found and cluster in joinable}
    joined = True
    while joined:
        joined = False
        for cluster in sorted(pending):
            own = _find(parent, cluster)
            targets = {_find(parent, holder) for holder in pending[cluster]} - {own}
            if len(targets) == 1:
                _union(parent, own, targets.pop())
                joined = True


def _find(parent: dict[str, str], fingerprint: str) -> str:
    root = fingerprint
    while parent[root] != root:
        root = parent[root]
    while parent[fingerprint] != root:  # path compression
        parent[fingerprint], fingerprint = root, parent[fingerprint]
    return root


def _union(parent: dict[str, str], left: str, right: str) -> None:
    """Merge two components, always under the smaller root, so a root is its component's minimum."""
    left_root, right_root = _find(parent, left), _find(parent, right)
    if left_root == right_root:
        return
    smaller, larger = sorted((left_root, right_root))
    parent[larger] = smaller

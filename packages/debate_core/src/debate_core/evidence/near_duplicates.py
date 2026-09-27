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
5. **Confirmation.** A candidate pair is a match only when its real shingle sets have Jaccard
   similarity at least the configured threshold (0.8 by default), or containment — the overlap
   divided by the smaller set — at least its threshold (0.9). Containment is what lets a card cut a
   paragraph shorter still join its cluster: the short copy is almost entirely inside the long one.
6. **Union-find.** Confirmed pairs are merged. The cluster id is the smallest exact fingerprint in
   the cluster.

## Why the cluster id cannot depend on input order

Every step above is a function of the *set* of bodies: candidate pairs come from bucket membership,
confirmation is symmetric, and the union always makes the smaller root the parent, so the root of a
component is its smallest member however the merges happened to be ordered. The same bodies, read
from files in any order, in any process, produce the same ids.

## What a cluster is not

Clustering never touches the text a card displays. It reads normalized words and returns ids.
Nothing here calls a model or an embedding service; the task forbids both for deduplication.
"""

from __future__ import annotations

import hashlib
import re
import struct
from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Final

from pydantic import Field

from debate_core.domain.base import DomainModel
from debate_core.evidence.fingerprints import normalize_for_matching

__all__ = [
    "LSH_BANDS",
    "LSH_ROWS_PER_BAND",
    "MINHASH_PERMUTATIONS",
    "MINHASH_SEED",
    "SHINGLE_SIZE",
    "NearDuplicateThresholds",
    "cluster_near_duplicates",
    "containment",
    "jaccard",
    "matching_words",
    "minhash_signature",
    "shingles",
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


def shingles(text: str, size: int = SHINGLE_SIZE) -> frozenset[str]:
    """Every run of `size` consecutive words in `text`; one shingle of all of them when shorter."""
    words = matching_words(text)
    if not words:
        return frozenset()
    if len(words) < size:
        return frozenset({" ".join(words)})
    return frozenset(" ".join(words[start : start + size]) for start in range(len(words) - size + 1))


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
        if (
            jaccard(left_set, right_set) >= limits.jaccard
            or containment(left_set, right_set) >= limits.containment
        ):
            _union(parent, left, right)
    return {fingerprint: _find(parent, fingerprint) for fingerprint in fingerprints}


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

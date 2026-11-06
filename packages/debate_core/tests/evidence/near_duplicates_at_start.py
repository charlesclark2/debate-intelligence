"""The near-duplicate clusterer as `v1-e31-t10` found it, kept as the oracle of the rebuild's tests.

Copied from `debate_core/evidence/near_duplicates.py` at the commit `v1-e31-t10` started from
(`81ed12e`), with only this docstring changed. Its MinHash is the one before that task, which takes
the minimum per hash function shingle by shingle. It is the old code, not the code under test, so it
can disagree with it (working agreement 6). Do not change it to follow the clusterer: a change to the
rules belongs in a test of its own.
"""

from __future__ import annotations

import hashlib
import re
import struct
from array import array
from collections import OrderedDict, defaultdict
from collections.abc import Callable, Hashable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Final, overload

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
    "MIN_OVERLAP_SHARE",
    "SHINGLE_SIZE",
    "SHINGLE_SETS_KEPT",
    "SHORT_BODY_SHINGLES",
    "BodyWords",
    "CutIndex",
    "NearDuplicateThresholds",
    "SpelledWords",
    "Witnesses",
    "cluster_near_duplicates",
    "confirms_a_cut",
    "contained_but_for_one_word",
    "containment",
    "jaccard",
    "joining_target",
    "matching_words",
    "minhash_signature",
    "ordered_shingles",
    "shingles",
    "too_common",
    "witnesses",
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

MIN_CUT_SHARE: Final = 0.1
"""The smallest share of its smallest witness's shingles a cut may be and still join that cluster;
also the smallest share of a body a passage it holds is (:meth:`CutIndex.holds_a_passage_apart_from`).
A quarter until the operator's sample of cuts it kept out (`v1-e31-t20`): 20 of 20 the same card,
8 of them under a tenth. The PM set it on 2026-10-18."""

MIN_OVERLAP_SHARE: Final = 0.3
"""Two bodies overlap when they share at least this share of the smaller one's shingles (the PM,
2026-10-18): `v1-e31-t21`'s line between overlapping and sharing a little."""

MAX_CONTAINER_CLUSTERS: Final = 8
"""A short body whose end shingles are both held by more other clusters than this, as the clusters
stand when it is considered, is left alone."""

SHINGLE_SETS_KEPT: Final = 1 << 18
"""Shingles, over all the sets kept, that :class:`CutIndex` keeps made between comparisons: the
sets of the bodies compared most recently. A set larger than this is made each time it is asked for."""

_SIGNATURE_BYTES: Final = 4 * MINHASH_PERMUTATIONS
_SIGNATURE_LAYOUT: Final = struct.Struct(f"<{MINHASH_PERMUTATIONS}I")
_EMPTY_SLOT: Final = 0xFFFFFFFF

#: A word's number in :class:`BodyWords`: an unsigned 32-bit integer.
_WORD_NUMBER: Final = "I"
_WORD_NUMBER_BYTES: Final = 4
#: The bytes of one shingle of :data:`SHINGLE_SIZE` words.
_SHINGLE_BYTES: Final = SHINGLE_SIZE * _WORD_NUMBER_BYTES

#: A hyphen at a line break, once whitespace has been collapsed: `commis- sion`.
_LINE_BREAK_HYPHENATION: Final = re.compile(r"(?<=\w)- (?=\w)")
_WORD: Final = re.compile(r"\w+")

assert LSH_BANDS * LSH_ROWS_PER_BAND == MINHASH_PERMUTATIONS  # noqa: S101 - a module invariant
assert array(_WORD_NUMBER).itemsize == _WORD_NUMBER_BYTES  # noqa: S101 - a module invariant


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


def jaccard(left: frozenset[Hashable], right: frozenset[Hashable]) -> float:
    """Shared shingles over all shingles. 0.0 when both are empty."""
    union = len(left | right)
    return len(left & right) / union if union else 0.0


def containment(left: frozenset[Hashable], right: frozenset[Hashable]) -> float:
    """Shared shingles over the smaller set: how much of the shorter body the longer one contains."""
    smaller = min(len(left), len(right))
    return len(left & right) / smaller if smaller else 0.0


def contained_but_for_one_word(short: Sequence[Hashable], long: Sequence[Hashable]) -> bool:
    """Whether `short` is in `long` as one run of words, except at one word.

    The words may be strings or their numbers in :class:`BodyWords`; they are only compared.

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


def confirms_a_cut(
    cut_set: frozenset[Hashable],
    holder_set: frozenset[Hashable],
    cut_words: Sequence[Hashable],
    holder_words: Sequence[Hashable],
    limits: NearDuplicateThresholds,
) -> bool:
    """Whether a body that holds an end of `cut` is confirmed to contain it.

    At least the containment threshold of the cut's shingles are in the holder, or the cut is short
    and in it but for one word. The one test the short-body step and
    :mod:`debate_core.evidence.cluster_diagnosis` both apply, so the diagnosis cannot drift from
    the rule it explains.
    """
    if len(cut_set & holder_set) >= limits.containment * len(cut_set):
        return True
    return len(cut_set) < SHORT_BODY_SHINGLES and contained_but_for_one_word(cut_words, holder_words)


def ordered_shingles(numbers: bytes) -> list[bytes]:
    """A body's shingles in order, as keys: each the bytes of its words' numbers in :class:`BodyWords`.

    :func:`word_shingles`, read through the numbers: every run of :data:`SHINGLE_SIZE` words, or one
    of all of them when there are fewer. Two keys are equal exactly when their words are, because
    each number stands for one word and a shorter body's key is shorter.
    """
    if len(numbers) <= _SHINGLE_BYTES:
        return [numbers] if numbers else []
    return [
        numbers[start : start + _SHINGLE_BYTES]
        for start in range(0, len(numbers) - _SHINGLE_BYTES + 1, _WORD_NUMBER_BYTES)
    ]


class SpelledWords(Sequence[str]):
    """One body's words, read from their numbers as they are asked for: what the linker compares an
    abbreviated card's words with (:class:`~debate_core.evidence.abbreviated_links.FullCardWords`).
    A slice is a tuple of the words, so it compares equal to the tuple of the same words."""

    __slots__ = ("_numbers", "_vocabulary")

    def __init__(self, numbers: array[int], vocabulary: Sequence[str]) -> None:
        self._numbers = numbers
        self._vocabulary = vocabulary

    def __len__(self) -> int:
        return len(self._numbers)

    @overload
    def __getitem__(self, position: int) -> str: ...
    @overload
    def __getitem__(self, position: slice) -> tuple[str, ...]: ...
    def __getitem__(self, position: int | slice) -> str | tuple[str, ...]:
        if isinstance(position, slice):
            return tuple(map(self._vocabulary.__getitem__, self._numbers[position]))
        return self._vocabulary[self._numbers[position]]


class BodyWords(Mapping[str, "array[int]"]):
    """Every body's words as the clusterer reads them (:func:`matching_words`), each held as its
    number in one vocabulary: four bytes a word, and each distinct word's text once.

    Maps a fingerprint to its body's word numbers. Two words have one number exactly when they are
    the same string, so comparing numbers is comparing the words.
    """

    def __init__(self, bodies: Mapping[str, str]) -> None:
        numbered: dict[str, int] = {}
        self._numbers = {
            fingerprint: array(
                _WORD_NUMBER, [numbered.setdefault(word, len(numbered)) for word in matching_words(text)]
            )
            for fingerprint, text in sorted(bodies.items())
        }
        self.vocabulary: tuple[str, ...] = tuple(numbered)
        """Each word once, at its number."""

    def __getitem__(self, fingerprint: str) -> array[int]:
        return self._numbers[fingerprint]

    def __iter__(self) -> Iterator[str]:
        return iter(self._numbers)

    def __len__(self) -> int:
        return len(self._numbers)

    def spelled(self, fingerprint: str) -> SpelledWords:
        """The body's words as strings, read from the vocabulary as they are asked for."""
        return SpelledWords(self._numbers[fingerprint], self.vocabulary)

    def shingles_of(self, fingerprint: str) -> list[bytes]:
        """The body's shingle keys in order (:func:`ordered_shingles`)."""
        return ordered_shingles(self._numbers[fingerprint].tobytes())


class _ShingleSets(Mapping[str, frozenset[bytes]]):
    """Each body's set of shingle keys, made from its word numbers when it is asked for. The sets of
    the bodies asked for most recently are kept, up to :data:`SHINGLE_SETS_KEPT` shingles in all."""

    def __init__(self, words: BodyWords) -> None:
        self._words = words
        self._kept: OrderedDict[str, frozenset[bytes]] = OrderedDict()
        self._shingles_kept = 0

    def __getitem__(self, fingerprint: str) -> frozenset[bytes]:
        found = self._kept.get(fingerprint)
        if found is not None:
            self._kept.move_to_end(fingerprint)
            return found
        made = frozenset(self._words.shingles_of(fingerprint))
        if len(made) <= SHINGLE_SETS_KEPT:
            self._kept[fingerprint] = made
            self._shingles_kept += len(made)
            while self._shingles_kept > SHINGLE_SETS_KEPT:
                _, dropped = self._kept.popitem(last=False)
                self._shingles_kept -= len(dropped)
        return made

    def __iter__(self) -> Iterator[str]:
        return iter(self._words)

    def __len__(self) -> int:
        return len(self._words)


class CutIndex:
    """Which bodies hold which, worked out from the bodies alone, before any cluster exists.

    The clusterer and :mod:`debate_core.evidence.cluster_diagnosis` both read containment from
    here, so a diagnosis cannot drift from the rule it explains. Every answer is cached: a body is
    asked about many times, in every round of the cut step. The bodies are held as this module's
    docstring says ("How the bodies are held"): `words` maps each to its word numbers, and `sets`
    makes its shingle set when it is asked for.

    `words`, when given, are the :class:`BodyWords` of these same bodies, made by the caller to
    read them again after the index is gone, as the linker does.
    """

    def __init__(
        self,
        bodies: Mapping[str, str],
        thresholds: NearDuplicateThresholds | None = None,
        *,
        words: BodyWords | None = None,
    ) -> None:
        self.limits = thresholds or NearDuplicateThresholds()
        self.fingerprints: list[str] = sorted(bodies)
        if words is not None and list(words) != self.fingerprints:
            raise ValueError("the words given are not of the bodies given")
        self.words: BodyWords = words if words is not None else BodyWords(bodies)
        self.sets: Mapping[str, frozenset[bytes]] = _ShingleSets(self.words)
        self._sizes: dict[str, int] = {}
        self.ends: dict[str, tuple[bytes, bytes]] = {}
        for fingerprint in self.fingerprints:
            runs = self.words.shingles_of(fingerprint)
            self._sizes[fingerprint] = len(set(runs))
            if runs:
                self.ends[fingerprint] = (runs[0], runs[-1])

        end_shingles = {shingle for pair in self.ends.values() for shingle in pair}
        holders: defaultdict[bytes, set[str]] = defaultdict(set)
        for fingerprint in self.fingerprints:
            for shingle in end_shingles.intersection(self.words.shingles_of(fingerprint)):
                holders[shingle].add(fingerprint)
        self._candidates: dict[str, list[str]] = {}
        self._both_ends: dict[str, list[str]] = {}
        for cut, (first, last) in self.ends.items():
            size = self.size(cut)
            found = [
                holder
                for holder in holders[first] | holders[last]
                if holder != cut and self.size(holder) >= size
            ]
            if found:
                self._candidates[cut] = self.by_size(found)
            if size < SHORT_BODY_SHINGLES:
                self._both_ends[cut] = [
                    holder for holder in found if holder in holders[first] & holders[last]
                ]

        self._held: dict[tuple[str, str], bool] = {}
        self._overlapping: dict[tuple[str, str], bool] = {}
        self._containers: dict[str, list[str]] = {}
        self._apart: dict[tuple[str, str], bool] = {}
        # A body's passages, worked out now: the bodies it holds that are at least the share of it.
        # Only these can join it, and they are few, since they are at least a tenth of its size.
        self._passages: defaultdict[str, list[str]] = defaultdict(list)
        for cut, holding in self._candidates.items():
            for holder in holding:
                if self.size(cut) / self.size(holder) < MIN_CUT_SHARE:
                    break
                if self.holds(holder, cut):
                    self._passages[holder].append(cut)

    def size(self, fingerprint: str) -> int:
        """Shingles in the body."""
        return self._sizes[fingerprint]

    def shingle_texts(self, fingerprint: str) -> frozenset[str]:
        """The body's shingles as text, as :func:`shingles` gives them: what MinHash signs."""
        return frozenset(word_shingles(self.words.spelled(fingerprint)[:]))

    def by_size(self, fingerprints: Iterable[str]) -> list[str]:
        """Smallest first, then by fingerprint: the order a body's containers are tried in."""
        return sorted(fingerprints, key=lambda fingerprint: (self.size(fingerprint), fingerprint))

    def candidates(self, cut: str) -> Sequence[str]:
        """Every other body at least as large that holds the cut's first or last shingle, smallest
        first and unconfirmed."""
        return self._candidates.get(cut, ())

    def holding_both_ends(self, cut: str) -> Sequence[str]:
        """For a short cut, the candidates holding its first and its last shingle: what
        :func:`too_common` counts."""
        return self._both_ends.get(cut, ())

    def holds(self, holder: str, cut: str) -> bool:
        """Whether `holder` contains `cut`: at least as large, holding its first or last shingle,
        and confirmed."""
        key = (holder, cut)
        known = self._held.get(key)
        if known is None:
            ends = self.ends.get(cut)
            held = self.sets[holder]
            known = (
                ends is not None
                and holder != cut
                and self.size(holder) >= self.size(cut)
                and (ends[0] in held or ends[1] in held)
                and confirms_a_cut(self.sets[cut], held, self.words[cut], self.words[holder], self.limits)
            )
            self._held[key] = known
        return known

    def containers(self, cut: str) -> list[str]:
        """The bodies that hold `cut` and that it does not hold back, smallest first."""
        found = self._containers.get(cut)
        if found is None:
            found = [
                holder
                for holder in self.candidates(cut)
                if self.holds(holder, cut) and not self.holds(cut, holder)
            ]
            self._containers[cut] = found
        return found

    def copies(self) -> list[tuple[str, str]]:
        """Pairs of bodies of one size that each hold the other: one text, give or take a word."""
        found = {
            (min(holder, cut), max(holder, cut))
            for holder, held in self._passages.items()
            for cut in held
            if self.size(cut) == self.size(holder) and self.holds(cut, holder)
        }
        return sorted(found)

    def passages(self, holder: str) -> Sequence[str]:
        """The bodies `holder` holds that are at least :data:`MIN_CUT_SHARE` of it."""
        return self._passages.get(holder, ())

    def overlap(self, left: str, right: str) -> bool:
        """Whether two bodies share at least :data:`MIN_OVERLAP_SHARE` of the smaller's shingles.
        A body with none overlaps nothing."""
        key = (left, right) if left < right else (right, left)
        known = self._overlapping.get(key)
        if known is None:
            left_set, right_set = self.sets[left], self.sets[right]
            smaller = min(len(left_set), len(right_set))
            known = smaller > 0 and len(left_set & right_set) / smaller >= MIN_OVERLAP_SHARE
            self._overlapping[key] = known
        return known

    def holds_a_passage_apart_from(self, holder: str, cut: str) -> bool:
        """Whether `holder` holds a passage that `cut` does not overlap: then the two are two cards,
        both in `holder`, and `holder` is no witness for either."""
        key = (holder, cut)
        known = self._apart.get(key)
        if known is None:
            known = any(
                passage != cut and not self.overlap(passage, cut) for passage in self.passages(holder)
            )
            self._apart[key] = known
        return known

    def overlap_throughout(self, left: Iterable[str], right: Sequence[str]) -> bool:
        """Whether every body of `left` overlaps every body of `right`."""
        return all(self.overlap(one, other) for one in left for other in right)


@dataclass(frozen=True, slots=True)
class Witnesses:
    """The clusters that hold a cut, as the cut step counts them."""

    clusters: frozenset[str]
    smallest: str
    """The smallest witness: the body the cut's share is of."""
    nested: bool = False
    """Witnesses in several clusters that hold one another, counted as one."""


def witnesses(cut: str, cluster_of: Callable[[str], str], index: CutIndex) -> Witnesses | None:
    """The clusters that witness `cut`, or `None` when no body that may witness it holds it.

    A container that also holds a passage `cut` does not overlap is no witness for it.
    `cluster_of` gives a body's cluster as the placement stands. The cut's own cluster is counted
    like any other. One cluster is returned when the witnesses are in one, or when every witness
    outside the cluster of the smallest holds a witness inside it.
    """
    held = [holder for holder in index.containers(cut) if not index.holds_a_passage_apart_from(holder, cut)]
    if not held:
        return None
    smallest = held[0]
    home = cluster_of(smallest)
    inside = [holder for holder in held if cluster_of(holder) == home]
    outside = [holder for holder in held if cluster_of(holder) != home]
    if all(any(index.holds(holder, within) for within in inside) for holder in outside):
        return Witnesses(frozenset((home,)), smallest, nested=bool(outside))
    return Witnesses(frozenset(cluster_of(holder) for holder in held), smallest)


def too_common(cut: str, cluster_of: Callable[[str], str], index: CutIndex) -> bool:
    """Whether a short body's ends are both held by more than :data:`MAX_CONTAINER_CLUSTERS` other
    clusters, as the placement stands."""
    if index.size(cut) >= SHORT_BODY_SHINGLES:
        return False
    own = cluster_of(cut)
    seen: set[str] = set()
    for holder in index.holding_both_ends(cut):
        cluster = cluster_of(holder)
        if cluster != own:
            seen.add(cluster)
            if len(seen) > MAX_CONTAINER_CLUSTERS:
                return True
    return False


def joining_target(
    cuts: Iterable[str], own: str, cluster_of: Callable[[str], str], index: CutIndex
) -> str | None:
    """The cluster that the cluster `own` joins by the cut step, given those of its bodies that
    have candidate containers (:meth:`CutIndex.candidates`); `None` when it joins none."""
    target: str | None = None
    within_the_share = False
    for cut in cuts:
        if too_common(cut, cluster_of, index):
            return None
        seen = witnesses(cut, cluster_of, index)
        if seen is None:
            continue
        if len(seen.clusters) > 1:
            return None
        (cluster,) = seen.clusters
        if cluster == own:
            continue
        if target is not None and cluster != target:
            return None
        target = cluster
        within_the_share = within_the_share or index.size(cut) / index.size(seen.smallest) >= MIN_CUT_SHARE
    return target if within_the_share else None


class _Clusters:
    """Union-find over fingerprints that also keeps each cluster's bodies, for the refusal."""

    def __init__(self, fingerprints: Sequence[str]) -> None:
        self.parent = {fingerprint: fingerprint for fingerprint in fingerprints}
        self.members = {fingerprint: [fingerprint] for fingerprint in fingerprints}

    def find(self, fingerprint: str) -> str:
        return _find(self.parent, fingerprint)

    def join(self, left: str, right: str) -> None:
        """Merge two clusters, always under the smaller root, so a root is its cluster's minimum."""
        smaller, larger = sorted((self.find(left), self.find(right)))
        if smaller == larger:
            return
        self.parent[larger] = smaller
        self.members[smaller].extend(self.members.pop(larger))


def cluster_near_duplicates(
    bodies: Mapping[str, str],
    thresholds: NearDuplicateThresholds | None = None,
    *,
    seed: str = MINHASH_SEED,
    words: BodyWords | None = None,
) -> dict[str, str]:
    """Group card bodies into near-duplicate clusters.

    `bodies` maps each exact fingerprint to one body with that fingerprint (which body does not
    matter: they normalize identically). The result maps every fingerprint to its cluster id, the
    smallest fingerprint in its cluster; a body that matched nothing is its own cluster. `words`,
    when given, are the bodies' :class:`BodyWords`, for a caller that reads them afterwards.
    """
    index = CutIndex(bodies, thresholds, words=words)
    shingle_sets = index.sets

    buckets: defaultdict[tuple[int, tuple[int, ...]], list[str]] = defaultdict(list)
    for fingerprint in index.fingerprints:
        if not index.size(fingerprint):
            continue
        signature = minhash_signature(index.shingle_texts(fingerprint), seed)
        for band in range(LSH_BANDS):
            rows = signature[band * LSH_ROWS_PER_BAND : (band + 1) * LSH_ROWS_PER_BAND]
            buckets[(band, rows)].append(fingerprint)

    candidates: set[tuple[str, str]] = set()
    for members in buckets.values():
        for position, left in enumerate(members):
            for right in members[position + 1 :]:
                candidates.add((left, right) if left < right else (right, left))

    # Copies: the pairs that are one text, strongest first. Containment is the cut step's, which
    # finds every body that contains a cut instead of the ones the banding sampled.
    clusters = _Clusters(index.fingerprints)
    _join_copies(
        clusters,
        index,
        {
            pair: similarity
            for pair in candidates
            if (similarity := jaccard(shingle_sets[pair[0]], shingle_sets[pair[1]])) >= index.limits.jaccard
        },
    )
    # Then bodies of one size that each hold the other: a word changed, which in a short body costs
    # more shingles than Jaccard forgives. A short one too common to compare is left alone, counted
    # against the copies above and before any of these joins, so the order of these does not count.
    _join_copies(
        clusters,
        index,
        {
            pair: jaccard(shingle_sets[pair[0]], shingle_sets[pair[1]])
            for pair in index.copies()
            if not any(too_common(fingerprint, clusters.find, index) for fingerprint in pair)
        },
    )
    _join_cuts_to_their_one_container(clusters, index)
    return {fingerprint: clusters.find(fingerprint) for fingerprint in index.fingerprints}


def _join_copies(clusters: _Clusters, index: CutIndex, pairs: Mapping[tuple[str, str], float]) -> None:
    """Join each pair's clusters, most similar first, then by fingerprint, unless the join would put
    two bodies that do not overlap in one cluster."""
    for left, right in sorted(pairs, key=lambda pair: (-pairs[pair], pair)):
        left_root, right_root = clusters.find(left), clusters.find(right)
        if left_root != right_root and index.overlap_throughout(
            clusters.members[left_root], clusters.members[right_root]
        ):
            clusters.join(left_root, right_root)


def _join_cuts_to_their_one_container(clusters: _Clusters, index: CutIndex) -> None:
    """The cut step of this module's docstring, in rounds, applied to `clusters` in place."""
    cuts = [fingerprint for fingerprint in index.fingerprints if index.candidates(fingerprint)]
    while True:
        by_cluster: defaultdict[str, list[str]] = defaultdict(list)
        for cut in cuts:
            by_cluster[clusters.find(cut)].append(cut)
        proposed: dict[str, str] = {}
        for own, members in by_cluster.items():
            target = joining_target(members, own, clusters.find, index)
            if target is not None and index.overlap_throughout(
                clusters.members[own], clusters.members[target]
            ):
                proposed[own] = target
        accepted = _accepted_joins(proposed, clusters, index)
        if not accepted:
            return
        for joiner, target in accepted:
            clusters.join(joiner, target)


def _accepted_joins(
    proposed: Mapping[str, str], clusters: _Clusters, index: CutIndex
) -> list[tuple[str, str]]:
    """Which of a round's joins happen: see "The order joins happen in" in this module's docstring.

    `proposed` maps a cluster to the one it would join, each already overlapping its target
    throughout. A cluster takes in the clusters that would join it once it is joining nothing
    itself, or once its own join has been refused: every one of them, except two that do not
    overlap, which it takes in neither of.
    """
    accepted: list[tuple[str, str]] = []
    joining: defaultdict[str, list[str]] = defaultdict(list)
    for own, target in proposed.items():
        joining[target].append(own)
    settled = [target for target in joining if target not in proposed]
    while settled:
        refused: list[str] = []
        for target in settled:
            owns = joining[target]
            for own in owns:
                if all(
                    index.overlap_throughout(clusters.members[own], clusters.members[other])
                    for other in owns
                    if other != own
                ):
                    accepted.append((own, target))
                else:
                    refused.append(own)
        settled = [own for own in refused if own in joining]
    return sorted(accepted)


def _find(parent: dict[str, str], fingerprint: str) -> str:
    root = fingerprint
    while parent[root] != root:
        root = parent[root]
    while parent[fingerprint] != root:  # path compression
        parent[fingerprint], fingerprint = root, parent[fingerprint]
    return root

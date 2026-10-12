"""Why near-duplicate clustering left a body where it did, in counts (`v1-e31-t11`).

:mod:`debate_core.evidence.near_duplicates` answers *which* bodies share a cluster. This module
answers the question a person asks of a finished placement: this body is plainly inside that one,
so why are they apart, and which limit did it. It reads bodies and the cluster ids they were given
and returns outcomes, digests and numbers. It never returns a word of a body, changes no cluster and
takes no part in placing a card.

## A cut and its containers

A body is a **cut** of another when the other is at least as large, holds the cut's first and last
shingle, and is *confirmed*: nine-tenths of the cut's shingles are in it, or the cut is short and
in it but for one word (:func:`~debate_core.evidence.near_duplicates.confirms_a_cut`, the test the
clusterer itself applies). :func:`diagnose_cuts` reports every body with a container **outside its
own cluster** that no container inside its cluster accounts for, and says what kept it out
(:class:`CutOutcome`):

* **Short cuts** are governed by the short-body step, so the outcome names the limit of that step
  that applied: its witnesses are in more than one cluster, it is under
  :data:`~debate_core.evidence.near_duplicates.MIN_CUT_SHARE` of the smallest body that holds it,
  or its ends are held by more than
  :data:`~debate_core.evidence.near_duplicates.MAX_CONTAINER_CLUSTERS` clusters. A short cut the
  step's own conditions would join, and that is still apart, is reported as exactly that: on a
  placement made by the current rules it is one whose cluster holds another short body pointing
  elsewhere, and on a placement made by earlier rules it is what those rules got wrong.
* **Long cuts** have no step of their own. A long cut and its container are compared only if the
  LSH banding happens to pair them, and a pair that was compared would have merged. So a long cut
  with a container outside its cluster is one the banding never paired.
* A short body nine-tenths inside a body that **lacks one of its ends** is reported too: before the
  short-body step such a pair merged when the banding paired it, and since it they are never
  compared.

**Witnesses.** As in the clusterer since `card-fingerprint-v3`, containers that hold one another
count once. When every confirmed container outside the cluster of the smallest one holds a
container inside that cluster, the cut has one witness (:attr:`CutFinding.containers_nested`). And a container
outside the cut's cluster that holds a container *inside* it is accounted for: a cut that has
joined its smallest container is not reported for the larger bodies that container is a cut of.

## Containers in more than one cluster: one card, or two?

A cut inside two clusters stays out of both, because joining either would be a guess. That is right
when the clusters are two different cards that share a passage, and it costs recall when they are
one card whose longer copies never merged. The two are told apart the way
:mod:`debate_core.evidence.abbreviated_links` tells them apart for an abbreviation: by the
containers' own text. Two container clusters *read as one card* when some container of one shares at
least :data:`~debate_core.evidence.abbreviated_links.SPLIT_COPY_OVERLAP` of the smaller body's
shingles with some container of the other; a cut's container clusters read as one card when that
relation connects them all (:class:`CopiesRead`). For each connected pair :class:`KeptApartBy` says
which limit left the two copies in different clusters.

This is a reading of counts, not a judgement of the cards. Whether two bodies that share half
their text are one card is what the operator's by-eye sample decides.

## A cluster's shape

:func:`cluster_shape` describes one cluster from the inside (:class:`ClusterShape`): how many pairs
of its distinct texts share nothing at all, how many texts hold two smaller texts that share
nothing, how many are inside two larger texts that share under half, and whether the cluster hangs
together through single texts. One much-read card and its overlapping cuts is a cluster whose texts
share text with one another. A chain of containment merges is a cluster with pairs of texts that
have no shingle in common: joined through a body that holds both, or through a passage both hold.
Whether such a cluster is one card cut at many extents or several cards is, again, for a person.
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence, Set
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Final

from debate_core.evidence.abbreviated_links import SPLIT_COPY_OVERLAP
from debate_core.evidence.near_duplicates import (
    LSH_BANDS,
    LSH_ROWS_PER_BAND,
    MAX_CONTAINER_CLUSTERS,
    MIN_CUT_SHARE,
    MINHASH_SEED,
    SHORT_BODY_SHINGLES,
    NearDuplicateThresholds,
    confirms_a_cut,
    containment,
    jaccard,
    matching_words,
    minhash_signature,
    word_shingles,
)

__all__ = [
    "MAX_CONTAINERS_COMPARED",
    "SHARE_BANDS",
    "ClusterShape",
    "CopiesRead",
    "CutCensus",
    "CutFinding",
    "CutOutcome",
    "DividedPart",
    "KeptApartBy",
    "cluster_shape",
    "diagnose_cuts",
    "explain_divided_part",
    "tally_cuts",
]

MAX_CONTAINERS_COMPARED: Final = 12
"""Containers of one cut, per cluster, that are compared across clusters and checked against the
banding. A much-read card has hundreds of copies; a spread of them by size says as much."""


class CutOutcome(StrEnum):
    """What kept a cut out of the cluster of a body that contains it."""

    SEVERAL_CLUSTERS = "short: its witnesses are in more than one cluster"
    UNDER_MIN_CUT_SHARE = "short: under the minimum share of the smallest body that holds it"
    TOO_MANY_HOLDERS = "short: its ends are held by too many clusters"
    WITHIN_THE_RULE = "short: one cluster is its witness, within the share, and it is still apart"
    ENDS_NOT_BOTH_INSIDE = "short: nine-tenths inside a body that lacks one of its ends"
    LONG_NEVER_PAIRED = "long: its containers are one cluster the banding never paired it with"
    LONG_SEVERAL_CLUSTERS = "long: its containers are in more than one cluster"


class CopiesRead(StrEnum):
    """How the container clusters of a cut inside several of them read, from their own text."""

    ONE_CARD_SPLIT = "as one card, split"
    DIFFERENT_CARDS = "as different cards"


class KeptApartBy(StrEnum):
    """Which limit left two copies that read as one card in different clusters."""

    BANDING = "pass the thresholds, never paired by the banding"
    THRESHOLDS = "share at least half, under the Jaccard and containment thresholds"
    SHORT_BODY_STEP = "the smaller copy is a short body the short-body step left out"


@dataclass(frozen=True, slots=True)
class CutFinding:
    """One body with a container outside its cluster. Digests and numbers only."""

    fingerprint: str
    cluster_id: str
    shingles: int
    outcome: CutOutcome
    container_clusters: tuple[str, ...]
    """Other clusters holding a confirmed container that nothing in its own cluster accounts for."""
    containers: frozenset[str]
    """Every such body outside its cluster that was found to contain it, by either test."""
    containers_nested: bool = False
    """Its containers are in several clusters, and every one outside the cluster of the smallest
    holds a container inside that cluster: one witness."""
    copies_read: CopiesRead | None = None
    """For a cut with containers in several clusters: how those clusters read."""
    kept_apart_by: tuple[KeptApartBy, ...] = ()
    """For container clusters that read as one card: the limit between each connected pair."""
    share_of_smallest_container: float = 0.0
    """Its shingles over those of the smallest confirmed container: 0.0 when none was confirmed."""
    banded_with_a_container: bool = False
    """Whether the banding pairs it with one of the containers compared: for a short cut, the pair
    the rules before the short-body step would have merged."""
    first_container_over_the_share: bool = False
    """For :attr:`CutOutcome.WITHIN_THE_RULE` with one container cluster: the container that sorts
    first by fingerprint there is over the share, although a smaller one is within it. What
    `card-fingerprint-v2` measured the share against."""
    smallest_container: str | None = None
    """The smallest confirmed container: the body a rule that joined this cut would join it to."""
    witness_cluster_texts: int = 0
    """Distinct bodies in the smallest container's cluster."""
    witness_cluster_texts_sharing_nothing: int = 0
    """Of those, the bodies with no shingle in common with this cut: what joining it there would
    put in one cluster with a text it shares nothing with."""

    @property
    def has_one_witness(self) -> bool:
        """One cluster holds it, or several whose containers are nested: not a guess to join."""
        return len(self.container_clusters) == 1 or self.containers_nested

    @property
    def is_short(self) -> bool:
        return self.shingles < SHORT_BODY_SHINGLES


@dataclass(frozen=True, slots=True)
class CutCensus:
    """What :func:`diagnose_cuts` found over one placement."""

    texts: int
    """Distinct bodies read."""
    short_texts: int
    """Of those, the bodies under :data:`SHORT_BODY_SHINGLES` shingles."""
    findings: tuple[CutFinding, ...]
    """Every body with a container outside its cluster, sorted by fingerprint."""


@dataclass(frozen=True, slots=True)
class DividedPart:
    """Why one part of an earlier cluster is no longer with the rest of it."""

    kind: str
    outcome: CutOutcome | None = None
    containers_nested: bool = False
    first_container_over_the_share: bool = False
    copies_read: CopiesRead | None = None
    kept_apart_by: tuple[KeptApartBy, ...] = ()

    LEFT_OUT = "a short cut in this part was left out"
    THROUGH_A_CUT = "this part was joined only through a short cut elsewhere"
    UNEXPLAINED = "no short cut links this part to the rest"


@dataclass(frozen=True, slots=True)
class ClusterShape:
    """One cluster from the inside. Counts only."""

    cluster_id: str
    cards: int
    distinct_texts: int
    short_texts: int
    words_smallest: int
    words_median: int
    words_largest: int
    pairs: int
    """Pairs of distinct texts."""
    pairs_sharing_nothing: int
    pairs_sharing_under_half: int
    """Pairs sharing some shingle, and under :data:`SPLIT_COPY_OVERLAP` of the smaller text."""
    pairs_sharing_half_or_more: int
    pairs_matching: int
    """Pairs the rules would confirm if compared: Jaccard, long containment, or a short cut."""
    groups_sharing_half: int
    """Connected groups when only texts sharing at least half of the smaller are joined."""
    largest_group_texts: int
    largest_group_cards: int
    texts_sharing_nothing_with_most_read: int
    cards_sharing_nothing_with_most_read: int
    bridging_texts: int
    """Texts whose removal leaves matching texts in more than one piece."""
    bridges_between_parts_sharing_under_half: int
    """Bridging texts whose pieces, once it is removed, have a pair of texts sharing under half of
    the smaller: nothing joins those two but the bridge."""
    texts_holding_parts_that_share_nothing: int
    """Texts with two smaller texts nine-tenths inside them that have no shingle in common."""
    texts_inside_texts_that_share_under_half: int
    """Texts nine-tenths inside two larger texts that share under half of the smaller of the two."""
    such_bridges_that_are_fragments: int
    """Of those, the ones smaller than every text they match: a passage several texts contain."""
    such_bridges_that_hold_the_parts: int
    """Of those, the ones larger than every text they match: one body holding several texts."""

    def as_json(self) -> dict[str, object]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


# ------------------------------------------------------------------------------------------------
# Cuts and their containers
# ------------------------------------------------------------------------------------------------


class _Bodies:
    """The words and shingles of every body, worked out once."""

    def __init__(self, bodies: Mapping[str, str]) -> None:
        self.fingerprints = sorted(bodies)
        self.words = {fingerprint: matching_words(bodies[fingerprint]) for fingerprint in self.fingerprints}
        self.ordered = {
            fingerprint: word_shingles(self.words[fingerprint]) for fingerprint in self.fingerprints
        }
        self.sets = {fingerprint: frozenset(self.ordered[fingerprint]) for fingerprint in self.fingerprints}

    def size(self, fingerprint: str) -> int:
        return len(self.sets[fingerprint])

    def by_size(self, fingerprints: Set[str] | Sequence[str]) -> list[str]:
        """Smallest first, then by fingerprint: an order that depends on nothing else."""
        return sorted(fingerprints, key=lambda fingerprint: (self.size(fingerprint), fingerprint))


def diagnose_cuts(
    bodies: Mapping[str, str],
    clusters: Mapping[str, str],
    thresholds: NearDuplicateThresholds | None = None,
    *,
    seed: str = MINHASH_SEED,
) -> CutCensus:
    """Every body that another body outside its cluster contains, and what kept it out.

    `bodies` maps each exact fingerprint to its text and `clusters` maps it to the cluster id it
    was given, by any version of the rules. A body whose containers are all in its own cluster, or
    that nothing contains, is not among the findings.
    """
    limits = thresholds or NearDuplicateThresholds()
    held = _Bodies(bodies)
    ends = {
        fingerprint: (ordered[0], ordered[-1]) for fingerprint, ordered in held.ordered.items() if ordered
    }
    short = {fingerprint for fingerprint in ends if held.size(fingerprint) < SHORT_BODY_SHINGLES}

    end_shingles = {shingle for pair in ends.values() for shingle in pair}
    short_shingles = {shingle for fingerprint in short for shingle in held.sets[fingerprint]}
    indexed = end_shingles | short_shingles
    holders: defaultdict[str, set[str]] = defaultdict(set)
    for fingerprint in held.fingerprints:
        for shingle in held.sets[fingerprint] & indexed:
            holders[shingle].add(fingerprint)

    signatures: dict[str, tuple[int, ...]] = {}

    def banded(left: str, right: str) -> bool:
        for fingerprint in (left, right):
            if fingerprint not in signatures:
                signatures[fingerprint] = minhash_signature(held.sets[fingerprint], seed)
        return _share_a_band(signatures[left], signatures[right])

    def holds(holder: str, cut: str) -> bool:
        return held.size(holder) >= held.size(cut) and confirms_a_cut(
            held.sets[cut], held.sets[holder], held.words[cut], held.words[holder], limits
        )

    members: defaultdict[str, list[str]] = defaultdict(list)
    for fingerprint in held.fingerprints:
        members[clusters[fingerprint]].append(fingerprint)

    findings: list[CutFinding] = []
    for cut in sorted(ends):
        first, last = ends[cut]
        cut_set, cluster = held.sets[cut], clusters[cut]
        holding_both_ends = {
            holder
            for holder in holders[first] & holders[last]
            if holder != cut and held.size(holder) >= len(cut_set)
        }
        outside_holders = {holder for holder in holding_both_ends if clusters[holder] != cluster}
        # The smallest containers it is already with: a body outside that holds one of them is
        # accounted for, as a larger copy of something the cut has joined.
        with_it = [
            holder for holder in held.by_size(holding_both_ends - outside_holders) if holds(holder, cut)
        ][:MAX_CONTAINERS_COMPARED]

        def accounted_for(holder: str, with_it: Sequence[str] = with_it) -> bool:
            return any(holds(holder, inside) for inside in with_it)

        confirmed: defaultdict[str, list[str]] = defaultdict(list)
        for holder in held.by_size(outside_holders):
            if holds(holder, cut) and not accounted_for(holder):
                confirmed[clusters[holder]].append(holder)

        lacking_an_end: set[str] = set()
        if cut in short:
            sharing: Counter[str] = Counter()
            for shingle in cut_set:
                sharing.update(holders[shingle])
            lacking_an_end = {
                other
                for other, shared in sharing.items()
                if other != cut
                and other not in holding_both_ends
                and clusters[other] != cluster
                and held.size(other) >= len(cut_set)
                and shared >= limits.containment * len(cut_set)
                and not accounted_for(other)
            }
        if not confirmed and not lacking_an_end:
            continue

        finding = _finding(held, cut, cluster, outside_holders, confirmed, lacking_an_end, clusters, limits)
        if finding.smallest_container is not None:
            beside = members[clusters[finding.smallest_container]]
            finding = replace(
                finding,
                witness_cluster_texts=len(beside),
                witness_cluster_texts_sharing_nothing=sum(cut_set.isdisjoint(held.sets[b]) for b in beside),
            )
        if cut in short:
            # Only a short cut's pairing matters: a long pair the banding made would have merged.
            compared = [holder for members in confirmed.values() for holder in _spread(members)]
            compared += held.by_size(lacking_an_end)[:MAX_CONTAINERS_COMPARED]
            finding = replace(
                finding,
                banded_with_a_container=any(
                    banded(cut, holder)
                    for holder in compared
                    if len(cut_set & held.sets[holder]) >= limits.containment * len(cut_set)
                ),
            )
        findings.append(finding)
    return CutCensus(texts=len(held.fingerprints), short_texts=len(short), findings=tuple(findings))


def _finding(
    held: _Bodies,
    cut: str,
    cluster: str,
    outside_holders: Set[str],
    confirmed: Mapping[str, list[str]],
    lacking_an_end: Set[str],
    clusters: Mapping[str, str],
    limits: NearDuplicateThresholds,
) -> CutFinding:
    """The finding for one cut, before the banding check. `confirmed` is by cluster, smallest first."""
    size = held.size(cut)
    is_short = size < SHORT_BODY_SHINGLES
    everything = held.by_size([holder for members in confirmed.values() for holder in members])
    smallest = everything[0] if everything else None
    home = [
        holder for holder in everything if smallest is not None and clusters[holder] == clusters[smallest]
    ]
    nested = len(confirmed) > 1 and all(
        any(
            held.size(inside) <= held.size(holder)
            and confirms_a_cut(
                held.sets[inside], held.sets[holder], held.words[inside], held.words[holder], limits
            )
            for inside in home
        )
        for holder in everything
        if holder not in home
    )
    copies_read, kept_apart_by = (
        _read_container_clusters(held, confirmed, limits) if len(confirmed) > 1 else (None, ())
    )

    def finding(outcome: CutOutcome, *, first_container_over_the_share: bool = False) -> CutFinding:
        return CutFinding(
            fingerprint=cut,
            cluster_id=cluster,
            shingles=size,
            outcome=outcome,
            container_clusters=tuple(sorted(confirmed)),
            containers=frozenset(everything) | frozenset(lacking_an_end),
            containers_nested=nested,
            share_of_smallest_container=size / held.size(smallest) if smallest is not None else 0.0,
            smallest_container=smallest,
            copies_read=copies_read,
            kept_apart_by=kept_apart_by,
            first_container_over_the_share=first_container_over_the_share,
        )

    if smallest is None:
        return finding(CutOutcome.ENDS_NOT_BOTH_INSIDE)
    if not is_short:
        return finding(
            CutOutcome.LONG_SEVERAL_CLUSTERS if len(confirmed) > 1 else CutOutcome.LONG_NEVER_PAIRED
        )
    # The short-body step counts the clusters holding both ends before it compares any of them.
    if len({clusters[holder] for holder in outside_holders}) > MAX_CONTAINER_CLUSTERS:
        return finding(CutOutcome.TOO_MANY_HOLDERS)
    if len(confirmed) > 1 and not nested:
        return finding(CutOutcome.SEVERAL_CLUSTERS)
    if size < MIN_CUT_SHARE * held.size(smallest):
        return finding(CutOutcome.UNDER_MIN_CUT_SHARE)
    first_by_fingerprint = min(everything)
    return finding(
        CutOutcome.WITHIN_THE_RULE,
        first_container_over_the_share=len(confirmed) == 1
        and size < MIN_CUT_SHARE * held.size(first_by_fingerprint),
    )


def _spread(members: Sequence[str]) -> list[str]:
    """Up to :data:`MAX_CONTAINERS_COMPARED` of `members`, evenly across the order given."""
    if len(members) <= MAX_CONTAINERS_COMPARED:
        return list(members)
    step = (len(members) - 1) / (MAX_CONTAINERS_COMPARED - 1)
    return [members[round(position * step)] for position in range(MAX_CONTAINERS_COMPARED)]


def _read_container_clusters(
    held: _Bodies, confirmed: Mapping[str, list[str]], limits: NearDuplicateThresholds
) -> tuple[CopiesRead, tuple[KeptApartBy, ...]]:
    """Whether a cut's container clusters read as one card, and what split each connected pair."""
    names = sorted(confirmed)
    linked: dict[str, set[str]] = {name: set() for name in names}
    gaps: list[KeptApartBy] = []
    for position, left in enumerate(names):
        for right in names[position + 1 :]:
            best = max(
                (
                    (containment(held.sets[a], held.sets[b]), a, b)
                    for a in _spread(confirmed[left])
                    for b in _spread(confirmed[right])
                ),
                key=lambda scored: (scored[0], scored[1], scored[2]),
            )
            if best[0] < SPLIT_COPY_OVERLAP:
                continue
            linked[left].add(right)
            linked[right].add(left)
            gaps.append(_kept_apart_by(held, best[1], best[2], limits))
    reached, frontier = {names[0]}, [names[0]]
    while frontier:
        for neighbour in linked[frontier.pop()] - reached:
            reached.add(neighbour)
            frontier.append(neighbour)
    if len(reached) < len(names):
        return CopiesRead.DIFFERENT_CARDS, tuple(sorted(gaps))
    return CopiesRead.ONE_CARD_SPLIT, tuple(sorted(gaps))


def _kept_apart_by(held: _Bodies, left: str, right: str, limits: NearDuplicateThresholds) -> KeptApartBy:
    left_set, right_set = held.sets[left], held.sets[right]
    overlap = containment(left_set, right_set)
    if min(len(left_set), len(right_set)) < SHORT_BODY_SHINGLES:
        if jaccard(left_set, right_set) >= limits.jaccard:
            return KeptApartBy.BANDING
        return KeptApartBy.SHORT_BODY_STEP if overlap >= limits.containment else KeptApartBy.THRESHOLDS
    if jaccard(left_set, right_set) >= limits.jaccard or overlap >= limits.containment:
        return KeptApartBy.BANDING
    return KeptApartBy.THRESHOLDS


def _share_a_band(left: Sequence[int], right: Sequence[int]) -> bool:
    return any(
        left[band * LSH_ROWS_PER_BAND : (band + 1) * LSH_ROWS_PER_BAND]
        == right[band * LSH_ROWS_PER_BAND : (band + 1) * LSH_ROWS_PER_BAND]
        for band in range(LSH_BANDS)
    )


def tally_cuts(findings: Sequence[CutFinding]) -> dict[str, object]:
    """The findings as counts, in the shape the diagnosis prints."""
    by_outcome: Counter[str] = Counter(finding.outcome.value for finding in findings)

    def several(chosen: Sequence[CutFinding]) -> dict[str, object]:
        """Cuts whose containers are in more than one cluster: how those clusters read."""
        inside_several = [finding for finding in chosen if finding.copies_read is not None]
        split = [f for f in inside_several if f.copies_read is CopiesRead.ONE_CARD_SPLIT]
        return {
            "cuts": len(inside_several),
            "of which the containers are nested": sum(f.containers_nested for f in inside_several),
            CopiesRead.ONE_CARD_SPLIT.value: len(split),
            CopiesRead.DIFFERENT_CARDS.value: len(inside_several) - len(split),
            "one card split, by what kept the copies apart": dict(
                sorted(Counter(gap.value for finding in split for gap in set(finding.kept_apart_by)).items())
            ),
        }

    def shares(outcome: CutOutcome) -> dict[str, int]:
        counted = Counter(
            _share_band(finding.share_of_smallest_container)
            for finding in findings
            if finding.outcome is outcome
        )
        return {band: counted.get(band, 0) for _, band in SHARE_BANDS}

    def within_the_rule(chosen: Sequence[CutFinding]) -> dict[str, int]:
        within = [finding for finding in chosen if finding.outcome is CutOutcome.WITHIN_THE_RULE]
        nested = sum(finding.containers_nested for finding in within)
        first = sum(finding.first_container_over_the_share for finding in within)
        return {
            "cuts": len(within),
            "its containers are nested copies in several clusters": nested,
            "the container first by fingerprint is over the share": first,
            "neither: another short body of its cluster points elsewhere": len(within) - nested - first,
        }

    def one_witness_within_the_share(chosen: Sequence[CutFinding]) -> dict[str, int]:
        """Cuts with one witness and within the share: what a step like the short one would join."""
        joining = [
            finding
            for finding in chosen
            if finding.has_one_witness and finding.share_of_smallest_container >= MIN_CUT_SHARE
        ]
        beside_all = [f for f in joining if f.witness_cluster_texts_sharing_nothing == 0]
        return {
            "cuts": len(joining),
            "sharing text with every text of the witness's cluster": len(beside_all),
            "of which that cluster is one text": sum(f.witness_cluster_texts == 1 for f in beside_all),
            "sharing nothing with at least one text of it": len(joining) - len(beside_all),
        }

    short = [finding for finding in findings if finding.is_short]
    banded = [finding for finding in short if finding.banded_with_a_container]
    return {
        "bodies_with_a_container_outside_their_cluster": len(findings),
        "by_outcome": {outcome.value: by_outcome.get(outcome.value, 0) for outcome in CutOutcome},
        "short_with_containers_in_several_clusters": several(short),
        "long_with_containers_in_several_clusters": several(
            [finding for finding in findings if not finding.is_short]
        ),
        "short_within_the_rule_and_apart": within_the_rule(short),
        "short_under_the_minimum_share_by_share": shares(CutOutcome.UNDER_MIN_CUT_SHARE),
        "long_never_paired_by_share": shares(CutOutcome.LONG_NEVER_PAIRED),
        "long_with_one_witness_within_the_share": one_witness_within_the_share(
            [finding for finding in findings if not finding.is_short]
        ),
        "short_the_banding_pairs_with_a_container": {
            "cuts": len(banded),
            "by_outcome": dict(sorted(Counter(finding.outcome.value for finding in banded).items())),
            "with_containers_in_several_clusters": several(banded),
            "within_the_rule_and_apart": within_the_rule(banded),
        },
    }


SHARE_BANDS: Final = (
    (0.1, "under a tenth"),
    (MIN_CUT_SHARE, "a tenth to a quarter"),
    (0.5, "a quarter to a half"),
    (float("inf"), "half or more"),
)
"""A cut's share of its smallest container, in bands; the second ends at :data:`MIN_CUT_SHARE`."""


def _share_band(share: float) -> str:
    return next(name for limit, name in SHARE_BANDS if share < limit)


def explain_divided_part(part: Set[str], rest: Set[str], findings: Mapping[str, CutFinding]) -> DividedPart:
    """Why `part` and `rest`, once one cluster, are apart: the short cut that used to join them.

    `part` and `rest` are the exact fingerprints of two sides of an earlier cluster, and `findings`
    is :func:`diagnose_cuts` over the later placement, by fingerprint. Under the rules before the
    short-body step the only join that step removed was a short body merged with a body the banding
    paired it with, on containment. So the part either holds such a cut, whose containers are in
    the rest, or was joined to the rest only through such a cut on the other side.
    """
    for kind, cuts, others in (
        (DividedPart.LEFT_OUT, part, rest),
        (DividedPart.THROUGH_A_CUT, rest, part),
    ):
        for cut in sorted(cuts):
            finding = findings.get(cut)
            if finding is not None and finding.is_short and finding.containers & others:
                return DividedPart(
                    kind,
                    finding.outcome,
                    finding.containers_nested,
                    finding.first_container_over_the_share,
                    finding.copies_read,
                    finding.kept_apart_by,
                )
    return DividedPart(DividedPart.UNEXPLAINED)


# ------------------------------------------------------------------------------------------------
# One cluster from the inside
# ------------------------------------------------------------------------------------------------


def cluster_shape(
    cluster_id: str,
    bodies: Mapping[str, str],
    copies: Mapping[str, int],
    thresholds: NearDuplicateThresholds | None = None,
) -> ClusterShape:
    """Describe one cluster: `bodies` are its distinct texts and `copies` how many cards hold each."""
    limits = thresholds or NearDuplicateThresholds()
    held = _Bodies(bodies)
    texts = [fingerprint for fingerprint in held.fingerprints if held.sets[fingerprint]]
    nothing = under_half = half_or_more = matching = 0
    alike: dict[str, set[str]] = {text: set() for text in texts}
    matches: dict[str, set[str]] = {text: set() for text in texts}
    disjoint: dict[str, set[str]] = {text: set() for text in texts}
    for position, left in enumerate(texts):
        for right in texts[position + 1 :]:
            overlap = containment(held.sets[left], held.sets[right])
            if overlap == 0:
                nothing += 1
                disjoint[left].add(right)
                disjoint[right].add(left)
            elif overlap < SPLIT_COPY_OVERLAP:
                under_half += 1
            else:
                half_or_more += 1
                alike[left].add(right)
                alike[right].add(left)
            if _would_match(held, left, right, limits):
                matching += 1
                matches[left].add(right)
                matches[right].add(left)

    groups = _components(texts, alike)
    nobody: set[str] = set()
    largest = max(groups, key=lambda group: (sum(copies[text] for text in group), len(group)), default=nobody)
    most_read = min(texts, key=lambda text: (-copies[text], text), default=None)
    apart = disjoint[most_read] if most_read is not None else nobody
    bridging = unrelated = fragments = holding = 0
    whole = len(_components(texts, matches))
    for text in texts:
        remaining = [other for other in texts if other != text]
        pieces = _components(remaining, matches)
        if len(pieces) <= whole:
            continue
        bridging += 1
        if any(
            other - alike[member]
            for position, piece in enumerate(pieces)
            for other in pieces[position + 1 :]
            for member in piece
        ):
            unrelated += 1
            fragments += all(held.size(other) > held.size(text) for other in matches[text])
            holding += all(held.size(other) < held.size(text) for other in matches[text])
    inside: dict[str, list[str]] = {text: [] for text in texts}
    holds: dict[str, list[str]] = {text: [] for text in texts}
    for small in texts:
        for large in texts:
            if held.size(small) < held.size(large) and len(
                held.sets[small] & held.sets[large]
            ) >= limits.containment * held.size(small):
                inside[small].append(large)
                holds[large].append(small)
    holding_unrelated = sum(
        any(right in disjoint[left] for position, left in enumerate(parts) for right in parts[position + 1 :])
        for parts in holds.values()
    )
    inside_unrelated = sum(
        any(
            right not in alike[left]
            for position, left in enumerate(wholes)
            for right in wholes[position + 1 :]
        )
        for wholes in inside.values()
    )
    words = sorted(len(held.words[text]) for text in texts)
    return ClusterShape(
        cluster_id=cluster_id,
        cards=sum(copies.values()),
        distinct_texts=len(held.fingerprints),
        short_texts=sum(held.size(text) < SHORT_BODY_SHINGLES for text in texts),
        words_smallest=words[0] if words else 0,
        words_median=int(statistics.median(words)) if words else 0,
        words_largest=words[-1] if words else 0,
        pairs=nothing + under_half + half_or_more,
        pairs_sharing_nothing=nothing,
        pairs_sharing_under_half=under_half,
        pairs_sharing_half_or_more=half_or_more,
        pairs_matching=matching,
        groups_sharing_half=len(groups),
        largest_group_texts=len(largest),
        largest_group_cards=sum(copies[text] for text in largest),
        texts_sharing_nothing_with_most_read=len(apart),
        cards_sharing_nothing_with_most_read=sum(copies[text] for text in apart),
        bridging_texts=bridging,
        bridges_between_parts_sharing_under_half=unrelated,
        texts_holding_parts_that_share_nothing=holding_unrelated,
        texts_inside_texts_that_share_under_half=inside_unrelated,
        such_bridges_that_are_fragments=fragments,
        such_bridges_that_hold_the_parts=holding,
    )


def _would_match(held: _Bodies, left: str, right: str, limits: NearDuplicateThresholds) -> bool:
    """Whether the rules confirm this pair when they compare it, in either direction."""
    left_set, right_set = held.sets[left], held.sets[right]
    if jaccard(left_set, right_set) >= limits.jaccard:
        return True
    smaller, larger = sorted((left, right), key=lambda text: (held.size(text), text))
    ordered = held.ordered[smaller]
    if not (ordered[0] in held.sets[larger] and ordered[-1] in held.sets[larger]):
        return held.size(smaller) >= SHORT_BODY_SHINGLES and (
            containment(left_set, right_set) >= limits.containment
        )
    return confirms_a_cut(
        held.sets[smaller], held.sets[larger], held.words[smaller], held.words[larger], limits
    )


def _components(nodes: Sequence[str], edges: Mapping[str, Set[str]]) -> list[set[str]]:
    kept = set(nodes)
    seen: set[str] = set()
    components: list[set[str]] = []
    for node in nodes:
        if node in seen:
            continue
        group, frontier = {node}, [node]
        while frontier:
            for neighbour in (edges[frontier.pop()] & kept) - group:
                group.add(neighbour)
                frontier.append(neighbour)
        seen |= group
        components.append(group)
    return components

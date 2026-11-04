"""The pairs `card-fingerprint-v4` keeps apart that `v1-e31-t29` may recover, in counts.

`v1-e31-t20` built the PM's card ruling into matching: a card is a passage, and every two bodies in a
cluster overlap. Three shapes it keeps apart were filed to be counted and sampled before any rule
changes (`v1-e31-t29`, and the PM's amendment of 2026-10-20). This module finds each in a finished
placement and returns digests and counts. It never returns a word of a body, a tag or a cite, and
it changes no cluster.

1. **A body nine-tenths inside another that holds neither of its ends**
   (:attr:`~debate_core.evidence.cluster_diagnosis.CutOutcome.ENDS_NOT_INSIDE`). The clusterer
   finds a body's containers from its first and last five-word runs, so a copy with a word
   changed at both ends is never compared with the body it is inside. The diagnosis finds such
   pairs from three interior runs; :func:`neither_end_pairs` reads them off its findings.
2. **Two trims of one body that share no text** (:func:`trims_sharing_nothing`): two passages of
   one holder, sharing no five-word run, as `v1-e31-t08`'s Brannock and Kessler cards are. By the
   ruling they are two cards, and the holder witnesses neither (:meth:`CutIndex.holds_a_passage_apart_from`).
   The bodies alone cannot say they are one card; what the cards carry beside them might, so each
   pair says whether a card of each carries the same tag and the same cite (:class:`Beside`), and
   how many of the holder's words are in neither trim: none when the holder is the two trims end to
   end, which is Brannock's shape and `v1-e31-t11`'s false join's.
3. **Holders the witness refusal sets aside** (:func:`refusing_holders`): every body holding two
   passages that do not overlap, the test `v1-e31-t20` refuses a witness by, by its length in words.
   `v1-e31-t22` counted the bodies holding two bodies whole that share no text; the PM's amendment
   asks for the ones under 300 words.

"Holds", "passage" and "overlap" are :class:`~debate_core.evidence.near_duplicates.CutIndex`'s, so
these counts cannot drift from the rules they describe.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from itertools import combinations
from typing import Final

from debate_core.evidence.cluster_diagnosis import SHARE_BANDS, CutCensus, CutFinding, CutOutcome
from debate_core.evidence.fingerprints import normalize_for_matching
from debate_core.evidence.near_duplicates import SHINGLE_SIZE, SHORT_BODY_SHINGLES, CutIndex

__all__ = [
    "HOLDER_UNDER_WORDS",
    "HOLDER_WORD_BANDS",
    "WORDS_IN_NEITHER_BANDS",
    "Beside",
    "NeitherEndPair",
    "RefusingHolder",
    "TrimPair",
    "band",
    "beside",
    "label",
    "neither_end_pairs",
    "refusing_holders",
    "tally_neither_end",
    "tally_refusals",
    "tally_trims",
    "trims_sharing_nothing",
    "words_in_neither",
]

HOLDER_UNDER_WORDS: Final = 300
"""The PM's amendment of 2026-10-20 samples the holders under this many words."""

HOLDER_WORD_BANDS: Final = ((0, 299), (300, 999), (1_000, 2_999), (3_000, None))
"""A holder's length in words, in `v1-e31-t22`'s bands, the first ending under :data:`HOLDER_UNDER_WORDS`."""

WORDS_IN_NEITHER_BANDS: Final = ((0, 0), (1, 9), (10, 49), (50, None))
"""Words of a holder in neither of two trims: none is the two trims end to end."""


def band(value: int, bands: Sequence[tuple[int, int | None]]) -> str:
    """The band `value` falls in, named by its ends: `0`, `1 to 9`, `3,000 or more`."""
    for lowest, highest in bands:
        if value >= lowest and (highest is None or value <= highest):
            if highest is None:
                return f"{lowest:,} or more"
            return f"{lowest:,}" if lowest == highest else f"{lowest:,} to {highest:,}"
    raise ValueError(f"{value} is in no band")


# ------------------------------------------------------------------------------------------------
# (1) Nine-tenths inside a body holding neither end
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class NeitherEndPair:
    """A body with no container outside its cluster but bodies there holding nine-tenths of it."""

    cut: str
    container: str
    """The smallest of those bodies, then by fingerprint: the one a person is shown it beside."""
    shingles: int
    share: float
    """Its shingles over the container's."""
    container_clusters: int
    """Clusters holding such a body."""
    container_holds_another_passage: bool
    """The container also holds a passage the cut does not overlap: were it found from the ends, it
    would be no witness (:meth:`CutIndex.holds_a_passage_apart_from`)."""


def neither_end_pairs(
    census: CutCensus, index: CutIndex, cluster_of: Callable[[str], str]
) -> list[NeitherEndPair]:
    """Each finding of `census` whose only containers outside its cluster hold neither of its ends.

    `index` holds the same bodies the census was taken over; `cluster_of` gives each its cluster.
    """
    found: list[NeitherEndPair] = []
    for finding in census.findings:
        if finding.outcome is not CutOutcome.ENDS_NOT_INSIDE:
            continue
        container = index.by_size(finding.containers)[0]
        found.append(
            NeitherEndPair(
                cut=finding.fingerprint,
                container=container,
                shingles=finding.shingles,
                share=finding.shingles / index.size(container),
                container_clusters=len({cluster_of(holder) for holder in finding.containers}),
                container_holds_another_passage=_holds_a_passage_apart(index, container, finding.fingerprint),
            )
        )
    return found


def _holds_a_passage_apart(index: CutIndex, holder: str, cut: str) -> bool:
    """:meth:`CutIndex.holds_a_passage_apart_from`, for a holder the index does not count as one."""
    return any(passage != cut and not index.overlap(passage, cut) for passage in index.passages(holder))


def tally_neither_end(pairs: Sequence[NeitherEndPair]) -> dict[str, object]:
    """Counts of :func:`neither_end_pairs`. No text."""
    return {
        "bodies": len(pairs),
        "long": sum(pair.shingles >= SHORT_BODY_SHINGLES for pair in pairs),
        "short": sum(pair.shingles < SHORT_BODY_SHINGLES for pair in pairs),
        "by_container_clusters": _in_order(
            Counter("one" if pair.container_clusters == 1 else "two or more" for pair in pairs),
            ["one", "two or more"],
        ),
        "by_share_of_the_container": _in_order(
            Counter(_share_band(pair.share) for pair in pairs), [name for _, name in SHARE_BANDS]
        ),
        "container_holds_another_passage": sum(pair.container_holds_another_passage for pair in pairs),
    }


def _share_band(share: float) -> str:
    return next(name for limit, name in SHARE_BANDS if share < limit)


# ------------------------------------------------------------------------------------------------
# (2) Two trims of one body that share no text
# ------------------------------------------------------------------------------------------------

type Label = tuple[str | None, str | None]
"""What one card carries beside its body: its tag and its full cite, normalized; None when absent."""


def label(tag: str | None, cite: str | None) -> Label:
    """A card's tag and cite as :func:`beside` compares them: the fingerprint normalization, so case,
    quotes, dashes and runs of whitespace do not count. An empty one is absent."""

    def normalized(text: str | None) -> str | None:
        return normalize_for_matching(text) or None if text else None

    return normalized(tag), normalized(cite)


class Beside(StrEnum):
    """What the cards carrying two bodies say beside them, best first."""

    SAME_TAG_AND_CITE = "a card of each carries the same tag and the same cite"
    SAME_CITE = "the same cite, never with the same tag"
    SAME_TAG = "the same tag, never with the same cite"
    NEITHER = "neither the same tag nor the same cite"


def beside(left: Collection[Label], right: Collection[Label]) -> Beside:
    """The best :class:`Beside` any card of `left` and any card of `right` give. An absent tag or
    cite matches nothing."""
    pairs = [(one, other) for one in left for other in right]
    if any(one[0] and one == other and one[1] for one, other in pairs):
        return Beside.SAME_TAG_AND_CITE
    if any(one[1] and one[1] == other[1] for one, other in pairs):
        return Beside.SAME_CITE
    if any(one[0] and one[0] == other[0] for one, other in pairs):
        return Beside.SAME_TAG
    return Beside.NEITHER


@dataclass(frozen=True, slots=True)
class TrimPair:
    """Two passages of one holder that share no five-word run. By fingerprint, `first < second`."""

    holder: str
    first: str
    second: str
    holder_words: int
    words_in_neither: int
    """Words of the holder in no run of either trim: 0 when the holder is the two end to end."""
    beside: Beside
    with_the_holder: int
    """How many of the two are in the holder's cluster."""


def words_in_neither(index: CutIndex, holder: str, trims: Iterable[str]) -> int:
    """Words of `holder` covered by no five-word run that one of `trims` has."""
    runs = index.words.shingles_of(holder)
    held = frozenset[bytes]().union(*(index.sets[trim] for trim in trims))
    covered = [False] * len(index.words[holder])
    for start, run in enumerate(runs):
        if run in held:
            covered[start : start + SHINGLE_SIZE] = [True] * len(covered[start : start + SHINGLE_SIZE])
    return covered.count(False)


def trims_sharing_nothing(
    index: CutIndex, cluster_of: Callable[[str], str], labels: Mapping[str, Collection[Label]]
) -> list[TrimPair]:
    """Every two passages of one holder that share no five-word run, once each.

    A pair two holders hold, such as a card and its one-word copy, is counted once, with its
    smallest holder, then by fingerprint. `labels` gives what each body's cards carry beside it.
    """
    found: dict[tuple[str, str], TrimPair] = {}
    for holder in index.by_size(index.fingerprints):
        for first, second in combinations(sorted(index.passages(holder)), 2):
            if (first, second) in found or not index.sets[first].isdisjoint(index.sets[second]):
                continue
            found[(first, second)] = TrimPair(
                holder=holder,
                first=first,
                second=second,
                holder_words=len(index.words[holder]),
                words_in_neither=words_in_neither(index, holder, (first, second)),
                beside=beside(labels.get(first, ()), labels.get(second, ())),
                with_the_holder=sum(cluster_of(trim) == cluster_of(holder) for trim in (first, second)),
            )
    return [found[pair] for pair in sorted(found)]


def tally_trims(pairs: Sequence[TrimPair]) -> dict[str, object]:
    """Counts of :func:`trims_sharing_nothing`. No text."""
    gaps = [band(low, WORDS_IN_NEITHER_BANDS) for low, _ in WORDS_IN_NEITHER_BANDS]
    same = [pair for pair in pairs if pair.beside is Beside.SAME_TAG_AND_CITE]
    return {
        "pairs": len(pairs),
        "holders": len({pair.holder for pair in pairs}),
        "by_beside": _in_order(Counter(pair.beside.value for pair in pairs), [kind.value for kind in Beside]),
        "by_holder_words_in_neither": _in_order(
            Counter(band(pair.words_in_neither, WORDS_IN_NEITHER_BANDS) for pair in pairs), gaps
        ),
        "same_tag_and_cite_by_holder_words_in_neither": _in_order(
            Counter(band(pair.words_in_neither, WORDS_IN_NEITHER_BANDS) for pair in same), gaps
        ),
        "same_tag_and_cite_by_holder_words": _in_order(
            Counter(band(pair.holder_words, HOLDER_WORD_BANDS) for pair in same),
            [band(low, HOLDER_WORD_BANDS) for low, _ in HOLDER_WORD_BANDS],
        ),
        "by_trims_with_the_holder": _in_order(
            Counter(str(pair.with_the_holder) for pair in pairs), ["0", "1", "2"]
        ),
    }


# ------------------------------------------------------------------------------------------------
# (3) Holders the witness refusal sets aside
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RefusingHolder:
    """A body holding two passages that do not overlap: no witness for either."""

    holder: str
    words: int
    sharing_nothing: bool
    """Two of its passages share no five-word run, not only fail to overlap."""
    refused_for: int
    """Bodies it holds that it is no witness for (:meth:`CutIndex.holds_a_passage_apart_from`)."""


def refusing_holders(index: CutIndex) -> list[RefusingHolder]:
    """Every body that holds two passages that do not overlap, by fingerprint."""
    held_by: dict[str, list[str]] = {}
    for cut in index.fingerprints:
        for holder in index.containers(cut):
            held_by.setdefault(holder, []).append(cut)
    found: list[RefusingHolder] = []
    for holder in index.fingerprints:
        apart = [
            (first, second)
            for first, second in combinations(sorted(index.passages(holder)), 2)
            if not index.overlap(first, second)
        ]
        if not apart:
            continue
        found.append(
            RefusingHolder(
                holder=holder,
                words=len(index.words[holder]),
                sharing_nothing=any(
                    index.sets[first].isdisjoint(index.sets[second]) for first, second in apart
                ),
                refused_for=sum(
                    index.holds_a_passage_apart_from(holder, cut) for cut in held_by.get(holder, ())
                ),
            )
        )
    return found


def tally_refusals(
    holders: Sequence[RefusingHolder], kept_out: Sequence[CutFinding], index: CutIndex
) -> dict[str, object]:
    """Counts of :func:`refusing_holders`, and of the bodies the refusal keeps out of every cluster
    holding them (`kept_out`, the findings :attr:`CutOutcome.HELD_WITH_ANOTHER_PASSAGE` describes),
    each by the length of its smallest container. No text."""
    names = [band(low, HOLDER_WORD_BANDS) for low, _ in HOLDER_WORD_BANDS]
    under = [holder for holder in holders if holder.words < HOLDER_UNDER_WORDS]
    return {
        "holders": len(holders),
        "by_holder_words": _in_order(
            Counter(band(holder.words, HOLDER_WORD_BANDS) for holder in holders), names
        ),
        "sharing_nothing_by_holder_words": _in_order(
            Counter(band(holder.words, HOLDER_WORD_BANDS) for holder in holders if holder.sharing_nothing),
            names,
        ),
        "under_300_words_refused_for": sum(holder.refused_for for holder in under),
        "bodies_kept_out_by_smallest_container_words": _in_order(
            Counter(
                band(len(index.words[finding.smallest_container]), HOLDER_WORD_BANDS)
                for finding in kept_out
                if finding.smallest_container is not None
            ),
            names,
        ),
    }


def _in_order(counts: Counter[str], names: Sequence[str]) -> dict[str, int]:
    """Every name in `names`, in that order, with its count, 0 when absent."""
    return {name: counts[name] for name in names}

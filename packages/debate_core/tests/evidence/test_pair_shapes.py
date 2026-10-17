"""Pair shapes from directional shingle shares, and the shapes a rule decides (`v1-e31-t21`).

Every body here is numbered invented words, so a body of n words has n - 4 five-word shingles and
every share is arithmetic. Each threshold is met exactly on one side of a boundary and missed by one
shingle on the other.
"""

from __future__ import annotations

import pytest

from debate_core.evidence.cluster_diagnosis import cluster_shape
from debate_core.evidence.near_duplicates import shingles, word_shingles
from debate_core.evidence.pair_shapes import (
    CONTAINED_SHARE,
    IDENTICAL_SHARE,
    OVERLAPPING_SHARE,
    RULE_VERDICTS,
    SMALL_PART_OF_THE_LARGER,
    PairShape,
    PairShares,
    RuleVerdict,
    cluster_pair_shapes,
    pair_shape,
    pair_shares,
    rule_verdict,
    shared_words,
)


def numbered(stem: str, count: int, start: int = 0) -> list[str]:
    return [f"{stem}{index}" for index in range(start, start + count)]


def shape_of(left: list[str], right: list[str]) -> PairShape:
    shapes = {
        pair_shape(pair_shares(frozenset(word_shingles(a)), frozenset(word_shingles(b))))
        for a, b in ((left, right), (right, left))
    }
    (shape,) = shapes  # the shape does not depend on which body is first
    return shape


#: 104 words, 100 shingles: the smaller body of every pair below.
SMALL = numbered("w", 104)


def test_the_thresholds_are_the_ones_the_pm_measured_with() -> None:
    assert (IDENTICAL_SHARE, CONTAINED_SHARE, OVERLAPPING_SHARE) == (0.98, 0.9, 0.3)
    assert SMALL_PART_OF_THE_LARGER == 1 / 3


def test_shares_are_directional() -> None:
    """A 100-shingle body inside a 400-shingle one: all of the first, a quarter of the second."""
    larger = [*SMALL, *numbered("x", 300)]
    shares = pair_shares(frozenset(word_shingles(SMALL)), frozenset(word_shingles(larger)))
    assert shares == PairShares(left=100, right=400, shared=100)
    assert (shares.share_of_left, shares.share_of_right) == (1.0, 0.25)
    assert shares.shape is PairShape.CONTAINED_SMALL


def test_identical_needs_each_body_to_hold_ninety_eight_hundredths_of_the_other() -> None:
    """Shifted by two words, 98 of each body's 100 shingles are shared: identical. Shifted by three,
    97: the smaller is still inside the other, so contained."""
    assert shape_of(SMALL, [*SMALL[2:], "y0", "y1"]) is PairShape.IDENTICAL
    assert shape_of(SMALL, [*SMALL[3:], "y0", "y1", "y2"]) is PairShape.CONTAINED_LARGE
    assert shape_of(SMALL, list(SMALL)) is PairShape.IDENTICAL


def test_identical_is_each_way_not_either_way() -> None:
    """All of the smaller is in the larger, but the larger has three shingles of its own: 100 of
    103 is under 0.98, so the pair is a body inside a slightly longer one, not one text."""
    assert shape_of(SMALL, [*SMALL, "y0", "y1"]) is PairShape.IDENTICAL  # 100 of 102
    assert shape_of(SMALL, [*SMALL, "y0", "y1", "y2"]) is PairShape.CONTAINED_LARGE  # 100 of 103


def test_contained_needs_nine_tenths_of_the_smaller() -> None:
    """The larger holds the smaller from its eleventh word on (90 of 100 shingles), or its twelfth
    (89). Its 390 shingles make the smaller under a third of it either way."""
    other = numbered("x", 300)
    assert shape_of(SMALL, [*SMALL[10:], *other]) is PairShape.CONTAINED_SMALL
    assert shape_of(SMALL, [*SMALL[11:], *other]) is PairShape.OVERLAPPING


def test_contained_is_split_at_a_third_of_the_larger() -> None:
    """The whole smaller body inside a larger of 300 shingles is a third of it; inside 301, under."""
    assert shape_of(SMALL, [*SMALL, *numbered("x", 200)]) is PairShape.CONTAINED_LARGE
    assert shape_of(SMALL, [*SMALL, *numbered("x", 201)]) is PairShape.CONTAINED_SMALL


def test_overlapping_starts_at_three_tenths_of_the_smaller() -> None:
    """The larger holds the smaller's last 34 words (30 shingles), or its last 33 (29)."""
    other = numbered("x", 200)
    assert shape_of(SMALL, [*other, *SMALL[70:]]) is PairShape.OVERLAPPING
    assert shape_of(SMALL, [*other, *SMALL[71:]]) is PairShape.SHARING_A_LITTLE


def test_one_shared_shingle_is_sharing_a_little_and_none_is_sharing_nothing() -> None:
    other = numbered("x", 200)
    assert shape_of(SMALL, [*other, *SMALL[99:]]) is PairShape.SHARING_A_LITTLE  # five words, one shingle
    assert shape_of(SMALL, [*other, *SMALL[100:]]) is PairShape.SHARING_NOTHING  # four words, none
    assert shape_of(SMALL, other) is PairShape.SHARING_NOTHING


def test_a_body_with_no_words_has_no_shape() -> None:
    with pytest.raises(ValueError, match="no words"):
        pair_shares(frozenset(), shingles("one two three four five"))
    with pytest.raises(ValueError, match="no words"):
        pair_shares(shingles("one two three four five"), shingles(" ... "))


def test_a_rule_decides_identical_and_contained_as_same_and_sharing_nothing_as_different() -> None:
    assert {shape: rule_verdict(shape) for shape in PairShape} == {
        PairShape.IDENTICAL: RuleVerdict.SAME,
        PairShape.CONTAINED_SMALL: RuleVerdict.SAME,
        PairShape.CONTAINED_LARGE: RuleVerdict.SAME,
        PairShape.OVERLAPPING: None,
        PairShape.SHARING_A_LITTLE: None,
        PairShape.SHARING_NOTHING: RuleVerdict.DIFFERENT,
    }
    assert set(RULE_VERDICTS) == {shape for shape in PairShape if rule_verdict(shape) is not None}
    # Tallied in the words a person's verdict is tallied in.
    assert {verdict.value for verdict in RuleVerdict} == {"same card", "different card"}


def test_shared_words_are_the_words_of_shingles_the_other_body_holds() -> None:
    """The other body holds words 40 to 59 of this one: exactly those twenty are marked."""
    other = frozenset(word_shingles([*numbered("x", 30), *SMALL[40:60], *numbered("z", 30)]))
    flags = shared_words(SMALL, other)
    assert len(flags) == len(SMALL)
    assert [index for index, shared in enumerate(flags) if shared] == list(range(40, 60))


def test_shared_words_of_a_body_shorter_than_a_shingle_are_all_or_nothing() -> None:
    short = ["alpha", "beta", "gamma"]
    assert shared_words(short, frozenset(word_shingles(short))) == (True, True, True)
    assert shared_words(short, frozenset(word_shingles(["alpha", "beta"]))) == (False, False, False)
    assert shared_words([], frozenset()) == ()


#: One cluster holding a pair of every shape. By hand, with SMALL as the hub:
#: SMALL and SHIFTED are identical; SMALL is a third or more of AROUND and under a third of
#: INSIDE_LONG; OVERLAP shares its last 40 words; A_LITTLE its last 10; ELSEWHERE nothing.
SHIFTED = [*SMALL[2:], "y0", "y1"]
AROUND = [*SMALL, *numbered("x", 100)]
INSIDE_LONG = [*numbered("v", 300), *SMALL]
OVERLAP = [*numbered("o", 100), *SMALL[64:]]
A_LITTLE = [*numbered("l", 100), *SMALL[94:]]
ELSEWHERE = numbered("e", 120)
CLUSTER = {
    "a-small": SMALL,
    "b-shifted": SHIFTED,
    "c-around": AROUND,
    "d-inside-long": INSIDE_LONG,
    "e-overlap": OVERLAP,
    "f-a-little": A_LITTLE,
    "g-elsewhere": ELSEWHERE,
}


def test_a_cluster_is_counted_by_the_shape_of_every_pair_of_its_texts() -> None:
    bodies = {name: " ".join(words) for name, words in CLUSTER.items()}
    shapes = cluster_pair_shapes(bodies, {})
    expected = {
        (left, right): shape_of(CLUSTER[left], CLUSTER[right])
        for position, left in enumerate(sorted(CLUSTER))
        for right in sorted(CLUSTER)[position + 1 :]
    }
    # The hub's own pairs, by hand.
    assert {right: expected[("a-small", right)] for right in sorted(CLUSTER)[1:]} == {
        "b-shifted": PairShape.IDENTICAL,
        "c-around": PairShape.CONTAINED_LARGE,
        "d-inside-long": PairShape.CONTAINED_SMALL,
        "e-overlap": PairShape.OVERLAPPING,
        "f-a-little": PairShape.SHARING_A_LITTLE,
        "g-elsewhere": PairShape.SHARING_NOTHING,
    }
    # All 21 pairs, by hand. Besides the hub's: SHIFTED is 98 of its 100 shingles inside AROUND
    # and INSIDE_LONG, and shares OVERLAP's 36 and A_LITTLE's 6; AROUND and INSIDE_LONG share the
    # hub's 100, half of AROUND; OVERLAP's 36 are a little of AROUND's and INSIDE_LONG's larger
    # sets, and A_LITTLE's 6 a little of everything holding them; ELSEWHERE shares nothing.
    by_hand = {
        PairShape.IDENTICAL: 1,
        PairShape.CONTAINED_SMALL: 2,
        PairShape.CONTAINED_LARGE: 2,
        PairShape.OVERLAPPING: 3,
        PairShape.SHARING_A_LITTLE: 7,
        PairShape.SHARING_NOTHING: 6,
    }
    assert dict(shapes.by_shape) == by_hand
    assert {shape: list(expected.values()).count(shape) for shape in PairShape} == by_hand
    assert shapes.pairs == 21
    assert (shapes.distinct_texts, shapes.texts_with_no_words) == (7, 0)
    # 104, 104, 110, 120, 140, 204 and 404 words.
    assert (shapes.words_smallest, shapes.words_median, shapes.words_largest) == (104, 120, 404)


def test_the_count_sharing_nothing_is_the_one_the_largest_clusters_were_measured_by() -> None:
    """`diagnose` counted the PM's 2026-10-16 figures with `cluster_shape`; shapes must agree."""
    bodies = {name: " ".join(words) for name, words in CLUSTER.items()}
    shapes = cluster_pair_shapes(bodies, {})
    measured = cluster_shape("a-small", bodies, dict.fromkeys(bodies, 1))
    assert shapes.by_shape[PairShape.SHARING_NOTHING] == measured.pairs_sharing_nothing
    assert shapes.pairs == measured.pairs


def test_texts_with_no_words_are_counted_and_in_no_pair() -> None:
    bodies = {"a": " ".join(SMALL), "b": " ".join(SHIFTED), "c": " -- "}
    shapes = cluster_pair_shapes(bodies, {})
    assert (shapes.distinct_texts, shapes.texts_with_no_words, shapes.pairs) == (3, 1, 1)
    assert shapes.by_shape[PairShape.IDENTICAL] == 1


def test_short_cites_are_counted_with_case_and_spacing_ignored() -> None:
    bodies = {"a": " ".join(SMALL), "b": " ".join(SHIFTED), "c": " ".join(ELSEWHERE)}
    cites = {"a": ["Invented 26", "invented  26"], "b": ["Made Up 25", None], "c": [None, "  "]}
    shapes = cluster_pair_shapes(bodies, cites)
    assert (shapes.distinct_short_cites, shapes.texts_with_no_short_cite) == (2, 1)
    assert cluster_pair_shapes(bodies, {}).texts_with_no_short_cite == 3


def test_the_json_names_shapes_and_counts_alone() -> None:
    bodies = {name: " ".join(words) for name, words in CLUSTER.items()}
    shown = cluster_pair_shapes(bodies, {"a-small": ["Invented 26"]}).as_json()
    assert shown["pairs_by_shape"] == {
        "identical": 1,
        "contained, under a third of the larger": 2,
        "contained, a third or more of the larger": 2,
        "overlapping": 3,
        "sharing a little": 7,
        "sharing nothing": 6,
    }
    # Of 21 pairs, to four places.
    assert shown["share_of_pairs_by_shape"] == {
        "identical": 0.0476,
        "contained, under a third of the larger": 0.0952,
        "contained, a third or more of the larger": 0.0952,
        "overlapping": 0.1429,
        "sharing a little": 0.3333,
        "sharing nothing": 0.2857,
    }
    text = repr(shown)
    assert not [word for word in ("w1", "Invented", "a-small", "elsewhere") if word in text]

"""`debate_core.evidence.recall_shapes`, on invented bodies of numbered words (`v1-e31-t29`).

Every expected figure is worked out by hand from the bodies below, not from a run.

* A Kessler-shaped card (`v1-e31-t08`'s `kessler-night-buses`): a 46-word card, a one-word copy
  of it (a word changed in its middle), a trim of its first 14 words and one of its last 18. The
  trims share nothing; 14 of the card's words are in neither.
* A Brannock-shaped card (`brannock-ferry-fares`, the shape of `v1-e31-t11`'s false join): a
  29-word card that is a 13-word trim and a 16-word trim end to end.
* A long card of 200 words, a 100-word copy of its words 1 to 98 with its first and last word
  changed (nine-tenths inside, holding neither end), and a 50-word passage of the card's end that
  the copy does not overlap.

Every body is its own cluster: how the clusterer would place them is not what is counted.
"""

from __future__ import annotations

import pytest

from debate_core.evidence.cluster_diagnosis import diagnose_cuts
from debate_core.evidence.near_duplicates import CutIndex, NearDuplicateThresholds
from debate_core.evidence.recall_shapes import (
    Beside,
    NeitherEndPair,
    RefusingHolder,
    TrimPair,
    band,
    beside,
    label,
    neither_end_pairs,
    refusing_holders,
    tally_neither_end,
    tally_refusals,
    tally_trims,
    trims_sharing_nothing,
    words_in_neither,
)


def _words(stem: str, start: int, stop: int) -> list[str]:
    return [f"{stem}{number}" for number in range(start, stop)]


KESSLER = _words("k", 0, 46)
KESSLER_COPY = [*KESSLER[:20], "kchanged", *KESSLER[21:]]
LONG = _words("w", 0, 200)

BODIES = {
    "kessler": " ".join(KESSLER),
    "kessler-copy": " ".join(KESSLER_COPY),
    "kessler-start": " ".join(KESSLER[:14]),
    "kessler-end": " ".join(KESSLER[28:]),
    "brannock": " ".join(_words("b", 0, 29)),
    "brannock-end": " ".join(_words("b", 0, 13)),
    "brannock-start": " ".join(_words("b", 13, 29)),
    "long": " ".join(LONG),
    "long-copy": " ".join(["wfirst", *LONG[1:99], "wlast"]),
    "long-passage": " ".join(LONG[150:]),
}
CLUSTERS = {fingerprint: fingerprint for fingerprint in BODIES}

#: What each body's cards carry: Kessler's trims the same tag and cite, Brannock's the same tag and
#: another cite.
LABELS = {
    "kessler-start": {label("Night buses cut absenteeism", "Kessler 25, Invented Review")},
    "kessler-end": {label("Night buses  cut absenteeism", "KESSLER 25, Invented Review")},
    "brannock-end": {label("Fares are inelastic", "Brannock 25")},
    "brannock-start": {label("Fares are inelastic", "Brannock 26")},
}


@pytest.fixture(scope="module")
def index() -> CutIndex:
    return CutIndex(BODIES)


def test_a_label_is_the_tag_and_cite_normalized_and_an_empty_one_is_absent() -> None:
    assert label("Fares  are INELASTIC", "Brannock ‘25") == ("fares are inelastic", "brannock '25")
    assert label(None, "") == (None, None)
    assert label("", " Kessler 25 ") == (None, "kessler 25")


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ({("t", "c")}, {("t", "c")}, Beside.SAME_TAG_AND_CITE),
        ({("t", "c"), ("u", "d")}, {("u", "d")}, Beside.SAME_TAG_AND_CITE),
        ({("t", "c")}, {("u", "c")}, Beside.SAME_CITE),
        ({("t", "c")}, {("t", "d")}, Beside.SAME_TAG),
        ({("t", "c")}, {("t", "d"), ("u", "c")}, Beside.SAME_CITE),
        ({(None, "c")}, {(None, "c")}, Beside.SAME_CITE),
        ({("t", None)}, {("t", None)}, Beside.SAME_TAG),
        ({(None, None)}, {(None, None)}, Beside.NEITHER),
        (set[tuple[str | None, str | None]](), {("t", "c")}, Beside.NEITHER),
    ],
)
def test_beside_is_the_best_any_card_of_each_gives(
    left: set[tuple[str | None, str | None]], right: set[tuple[str | None, str | None]], expected: Beside
) -> None:
    assert beside(left, right) is expected


def test_words_in_neither_trim_are_none_when_the_holder_is_the_two_end_to_end(index: CutIndex) -> None:
    assert words_in_neither(index, "brannock", ("brannock-end", "brannock-start")) == 0
    assert words_in_neither(index, "kessler", ("kessler-start", "kessler-end")) == 14
    assert words_in_neither(index, "kessler-copy", ("kessler-start", "kessler-end")) == 14
    assert words_in_neither(index, "kessler", ("kessler-start",)) == 32


def test_two_trims_sharing_nothing_are_found_once_beside_their_smallest_holder(index: CutIndex) -> None:
    # The card and its one-word copy both hold Kessler's trims, at one size: "kessler" sorts first.
    assert trims_sharing_nothing(index, CLUSTERS.__getitem__, LABELS) == [
        TrimPair(
            holder="brannock",
            first="brannock-end",
            second="brannock-start",
            holder_words=29,
            words_in_neither=0,
            beside=Beside.SAME_TAG,
            with_the_holder=0,
        ),
        TrimPair(
            holder="kessler",
            first="kessler-end",
            second="kessler-start",
            holder_words=46,
            words_in_neither=14,
            beside=Beside.SAME_TAG_AND_CITE,
            with_the_holder=0,
        ),
    ]


def test_a_trim_in_the_holders_cluster_is_counted_as_with_it(index: CutIndex) -> None:
    clusters = {**CLUSTERS, "kessler-start": "kessler"}
    (_, kessler) = trims_sharing_nothing(index, clusters.__getitem__, LABELS)
    assert kessler.with_the_holder == 1


def test_trims_are_tallied_by_what_their_cards_carry_and_the_words_in_neither(index: CutIndex) -> None:
    pairs = trims_sharing_nothing(index, CLUSTERS.__getitem__, LABELS)
    assert tally_trims(pairs) == {
        "pairs": 2,
        "holders": 2,
        "by_beside": {
            "a card of each carries the same tag and the same cite": 1,
            "the same cite, never with the same tag": 0,
            "the same tag, never with the same cite": 1,
            "neither the same tag nor the same cite": 0,
        },
        "by_holder_words_in_neither": {"0": 1, "1 to 9": 0, "10 to 49": 1, "50 or more": 0},
        "same_tag_and_cite_by_holder_words_in_neither": {"0": 0, "1 to 9": 0, "10 to 49": 1, "50 or more": 0},
        "same_tag_and_cite_by_holder_words": {
            "0 to 299": 1,
            "300 to 999": 0,
            "1,000 to 2,999": 0,
            "3,000 or more": 0,
        },
        "by_trims_with_the_holder": {"0": 2, "1": 0, "2": 0},
    }


def test_a_body_holding_neither_end_is_paired_with_the_smallest_such_body(index: CutIndex) -> None:
    census = diagnose_cuts(BODIES, CLUSTERS, index=index)
    # 96 shingles of the copy over 196 of the card. The card holds a passage, its last 50 words,
    # that the copy does not overlap: found from its ends, the card would be no witness.
    assert neither_end_pairs(census, index, CLUSTERS.__getitem__) == [
        NeitherEndPair(
            cut="long-copy",
            container="long",
            shingles=96,
            share=96 / 196,
            container_clusters=1,
            container_holds_another_passage=True,
        )
    ]


def test_neither_end_pairs_are_tallied_by_length_clusters_and_share(index: CutIndex) -> None:
    pairs = [
        NeitherEndPair("a", "b", 96, 96 / 196, 1, True),
        NeitherEndPair("c", "d", 20, 0.12, 2, False),
        NeitherEndPair("e", "f", 59, 0.05, 1, False),
    ]
    assert tally_neither_end(pairs) == {
        "bodies": 3,
        "long": 1,
        "short": 2,
        "by_container_clusters": {"one": 2, "two or more": 1},
        "by_share_of_the_container": {
            "under a tenth": 1,
            "a tenth to a quarter": 1,
            "a quarter to a half": 1,
            "half or more": 0,
        },
        "container_holds_another_passage": 1,
    }


def test_holders_of_two_passages_that_do_not_overlap_are_the_ones_refused(index: CutIndex) -> None:
    # The long card holds one passage only; neither copy of Kessler's card is a passage apart from
    # the trims, because each holds both.
    assert refusing_holders(index) == [
        RefusingHolder(holder="brannock", words=29, sharing_nothing=True, refused_for=2),
        RefusingHolder(holder="kessler", words=46, sharing_nothing=True, refused_for=2),
        RefusingHolder(holder="kessler-copy", words=46, sharing_nothing=True, refused_for=2),
    ]


def test_the_refusal_is_tallied_by_holder_length_and_the_bodies_it_keeps_out(index: CutIndex) -> None:
    census = diagnose_cuts(BODIES, CLUSTERS, index=index)
    kept_out = [finding for finding in census.findings if finding.outcome.name == "HELD_WITH_ANOTHER_PASSAGE"]
    assert sorted(finding.fingerprint for finding in kept_out) == [
        "brannock-end",
        "brannock-start",
        "kessler-end",
        "kessler-start",
    ]
    bands = {"0 to 299": 0, "300 to 999": 0, "1,000 to 2,999": 0, "3,000 or more": 0}
    assert tally_refusals(refusing_holders(index), kept_out, index) == {
        "holders": 3,
        "by_holder_words": {**bands, "0 to 299": 3},
        "sharing_nothing_by_holder_words": {**bands, "0 to 299": 3},
        "under_300_words_refused_for": 6,
        "bodies_kept_out_by_smallest_container_words": {**bands, "0 to 299": 4},
    }


def test_a_holder_of_300_words_is_not_under_300() -> None:
    holders = [RefusingHolder("a", 299, True, 1), RefusingHolder("b", 300, False, 5)]
    tallied = tally_refusals(holders, [], CutIndex({}))
    assert tallied["under_300_words_refused_for"] == 1
    assert tallied["by_holder_words"] == {
        "0 to 299": 1,
        "300 to 999": 1,
        "1,000 to 2,999": 0,
        "3,000 or more": 0,
    }
    assert tallied["sharing_nothing_by_holder_words"] == {
        "0 to 299": 1,
        "300 to 999": 0,
        "1,000 to 2,999": 0,
        "3,000 or more": 0,
    }


def test_bands_are_named_by_their_ends() -> None:
    bands = ((0, 0), (1, 9), (50, None))
    assert [band(value, bands) for value in (0, 1, 9, 50, 3_000)] == [
        "0",
        "1 to 9",
        "1 to 9",
        "50 or more",
        "50 or more",
    ]
    with pytest.raises(ValueError, match="in no band"):
        band(10, bands)


def test_the_diagnosis_refuses_an_index_of_other_bodies_or_thresholds(index: CutIndex) -> None:
    with pytest.raises(ValueError, match="not of the bodies"):
        diagnose_cuts({"kessler": BODIES["kessler"]}, {"kessler": "kessler"}, index=index)
    with pytest.raises(ValueError, match="not of the bodies"):
        diagnose_cuts(BODIES, CLUSTERS, NearDuplicateThresholds(containment=0.8), index=index)

"""The counts-only diagnosis of a finished placement (`v1-e31-t11`), on invented bodies.

Every body here is a run of numbered made-up words (`word0 word1 ...`), so two bodies share a
shingle exactly where a test makes them share words, and every expected figure below is worked out
by hand from the word counts: a body of `n` words has `n - 4` shingles, and is short under 60.

The clusters a test hands to the diagnosis are written out, not computed, wherever the test is
about a placement the current rules would not make: the diagnosis exists to explain placements made
by earlier rules too.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from debate_core.evidence.cluster_diagnosis import (
    SHARE_BANDS,
    ClusterShape,
    CopiesRead,
    CutFinding,
    CutOutcome,
    DividedPart,
    KeptApartBy,
    cluster_shape,
    diagnose_cuts,
    explain_divided_part,
    tally_cuts,
)
from debate_core.evidence.near_duplicates import MIN_CUT_SHARE, cluster_near_duplicates

from .test_near_duplicates import (
    CUT_OF_THE_COPY,
    LONG_COPY,
    WHOLE,
    numbered,
    replaced,
    templated,
)


def joined(bodies: dict[str, list[str]]) -> dict[str, str]:
    return {key: " ".join(words) for key, words in bodies.items()}


def each_alone(bodies: dict[str, list[str]]) -> dict[str, str]:
    """Every body a cluster of its own: the placement before anything was joined."""
    return {key: key for key in bodies}


def diagnosed(bodies: dict[str, list[str]], clusters: dict[str, str] | None = None) -> dict[str, CutFinding]:
    census = diagnose_cuts(joined(bodies), clusters or each_alone(bodies))
    return {finding.fingerprint: finding for finding in census.findings}


NESTED = {"whole": WHOLE, "copy": LONG_COPY, "cut": CUT_OF_THE_COPY}
"""326, 86 and 26 shingles: a short cut of a long copy of a long card."""


# ------------------------------------------------------------------------------------------------
# What is and is not a finding
# ------------------------------------------------------------------------------------------------


def test_a_cut_in_its_containers_cluster_is_not_a_finding() -> None:
    card = [*numbered("shared", 13), *numbered("first", 25)]
    bodies = {"card": card, "cut": card[:13]}
    census = diagnose_cuts(joined(bodies), {"card": "card", "cut": "card"})
    assert (census.texts, census.short_texts, census.findings) == (2, 2, ())


def test_bodies_that_nothing_contains_are_not_findings() -> None:
    bodies = {"one": numbered("one", 40), "two": numbered("two", 90)}
    census = diagnose_cuts(joined(bodies), each_alone(bodies))
    assert (census.texts, census.short_texts, census.findings) == (2, 1, ())


def test_a_cut_the_rule_would_join_and_that_is_apart_is_reported_as_that() -> None:
    """Nine shingles of a 34-shingle card: over a quarter, one container, one cluster. Apart only
    because this placement was written that way."""
    card = [*numbered("shared", 13), *numbered("first", 25)]
    finding = diagnosed({"card": card, "cut": card[:13]})["cut"]
    assert finding.outcome is CutOutcome.WITHIN_THE_RULE
    assert (finding.shingles, finding.is_short, finding.container_clusters) == (9, True, ("card",))
    assert finding.share_of_smallest_container == pytest.approx(9 / 34)
    assert (finding.smallest_container, finding.containers) == ("card", frozenset({"card"}))
    assert (finding.containers_nested, finding.first_container_over_the_share) == (False, False)
    assert (finding.copies_read, finding.kept_apart_by, finding.has_one_witness) == (None, (), True)


# ------------------------------------------------------------------------------------------------
# The short-body step's limits, one each
# ------------------------------------------------------------------------------------------------


def test_a_cut_inside_two_different_cards_has_witnesses_in_two_clusters() -> None:
    """`v1-e31-t08`'s false positive: thirteen words two cards open with. The cards share 9 of
    the smaller one's 33 shingles, so they read as different cards, which they are."""
    opening = numbered("shared", 13)
    bodies = {
        "first": [*opening, *numbered("first", 25)],
        "second": [*opening, *numbered("second", 24)],
        "opening": opening,
    }
    findings = diagnosed(bodies)
    assert set(findings) == {"opening"}
    finding = findings["opening"]
    assert finding.outcome is CutOutcome.SEVERAL_CLUSTERS
    assert finding.container_clusters == ("first", "second")
    assert (finding.containers_nested, finding.has_one_witness) == (False, False)
    assert (finding.copies_read, finding.kept_apart_by) == (CopiesRead.DIFFERENT_CARDS, ())
    assert finding.smallest_container == "second"


def test_a_cut_under_a_quarter_of_its_only_container_is_under_the_minimum_share() -> None:
    body = numbered("word", 64)  # 60 shingles
    finding = diagnosed({"body": body, "cut": body[:18]})["cut"]  # 14 shingles
    assert finding.outcome is CutOutcome.UNDER_MIN_CUT_SHARE
    assert finding.share_of_smallest_container == pytest.approx(14 / 60)
    assert MIN_CUT_SHARE > 14 / 60


def test_a_cut_whose_ends_nine_other_clusters_hold_is_left_alone() -> None:
    """Nine bodies that open and close alike, and a copy of the first with one word changed. The
    copy's ends are in nine other clusters, and so are the first body's, counting the copy."""
    many = templated(9)
    bodies = {f"t{index}": body for index, body in enumerate(many)}
    bodies["copy"] = replaced(many[0], 15, "changed")
    findings = diagnosed(bodies)
    assert {key: finding.outcome for key, finding in findings.items()} == {
        "copy": CutOutcome.TOO_MANY_HOLDERS,
        "t0": CutOutcome.TOO_MANY_HOLDERS,
    }

    fewer = {f"t{index}": body for index, body in enumerate(templated(8))}
    fewer["copy"] = bodies["copy"]
    assert diagnosed(fewer)["copy"].outcome is CutOutcome.WITHIN_THE_RULE


def test_a_short_body_nine_tenths_inside_a_body_that_lacks_one_of_its_ends() -> None:
    """Forty words, and a longer body that starts at the third of them: it has 34 of the 36
    shingles and not the first, so it is never looked up as a container."""
    short = numbered("word", 40)
    bodies = {"short": short, "longer": [*short[2:], *numbered("more", 60)]}
    findings = diagnosed(bodies)
    assert set(findings) == {"short"}
    finding = findings["short"]
    assert finding.outcome is CutOutcome.ENDS_NOT_BOTH_INSIDE
    assert (finding.container_clusters, finding.containers) == ((), frozenset({"longer"}))
    assert (finding.smallest_container, finding.share_of_smallest_container) == (None, 0.0)


# ------------------------------------------------------------------------------------------------
# Nested copies: one witness
# ------------------------------------------------------------------------------------------------


def test_a_cut_of_nested_copies_left_alone_is_within_the_rule_and_apart() -> None:
    """The placement `card-fingerprint-v2` made of these three: each alone. The cut's containers
    are two clusters, the larger holds the smaller, and the cut is 26 of the smaller's 86 shingles.
    The two long copies pass the containment threshold and were never paired."""
    findings = diagnosed(NESTED)
    assert set(findings) == {"cut", "copy"}
    cut = findings["cut"]
    assert cut.outcome is CutOutcome.WITHIN_THE_RULE
    assert cut.container_clusters == ("copy", "whole")
    assert (cut.containers_nested, cut.has_one_witness, cut.first_container_over_the_share) == (
        True,
        True,
        False,
    )
    assert (cut.copies_read, cut.kept_apart_by) == (CopiesRead.ONE_CARD_SPLIT, (KeptApartBy.BANDING,))
    assert cut.smallest_container == "copy"
    assert cut.share_of_smallest_container == pytest.approx(26 / 86)
    assert (cut.witness_cluster_texts, cut.witness_cluster_texts_sharing_nothing) == (1, 0)


def test_a_long_cut_the_banding_never_paired_with_its_card() -> None:
    copy = diagnosed(NESTED)["copy"]
    assert copy.outcome is CutOutcome.LONG_NEVER_PAIRED
    assert (copy.is_short, copy.container_clusters, copy.smallest_container) == (False, ("whole",), "whole")
    assert copy.share_of_smallest_container == pytest.approx(86 / 326)
    assert copy.banded_with_a_container is False  # only a short cut's pairing is looked up


def test_once_the_cut_has_joined_the_smallest_copy_only_the_long_split_is_left() -> None:
    """The placement the current rules make. The cut is with the copy, and the whole card holds
    the copy, so the whole card is accounted for: the one finding left is the long copy's own."""
    clusters = cluster_near_duplicates(joined(NESTED))
    assert clusters["cut"] == clusters["copy"] != clusters["whole"]
    assert set(diagnosed(NESTED, clusters)) == {"copy"}


def test_a_cut_with_a_copy_that_the_outside_body_holds_is_set_aside_not_lost() -> None:
    """The same placement. The cut is kept, apart from the findings, described as it would be were
    the copy not there: its one container outside is the whole card, of which it is 26 of 326
    shingles. The earlier rules may have joined the card to this cluster through it."""
    clusters = cluster_near_duplicates(joined(NESTED))
    census = diagnose_cuts(joined(NESTED), clusters)
    assert [finding.fingerprint for finding in census.findings] == ["copy"]
    (cut,) = census.with_a_copy
    assert (cut.fingerprint, cut.outcome) == ("cut", CutOutcome.UNDER_MIN_CUT_SHARE)
    assert (cut.containers, cut.smallest_container) == (frozenset({"whole"}), "whole")

    counted = tally_cuts(census.findings, [replace(cut, banded_with_a_container=True)])
    assert counted["bodies_with_a_container_outside_their_cluster"] == 1
    assert counted["with_a_copy_in_their_cluster_that_every_outside_container_holds"] == {
        "bodies": 1,
        "short": 1,
        "short_the_banding_pairs_with_an_outside_container": {
            "cuts": 1,
            "by_outcome_were_the_copy_not_there": {CutOutcome.UNDER_MIN_CUT_SHARE.value: 1},
        },
    }

    # An earlier cluster of all three, now the card on one side and the copy and cut on the other.
    findings = {finding.fingerprint: finding for finding in census.findings}
    assert explain_divided_part({"copy", "cut"}, {"whole"}, findings) == DividedPart(DividedPart.UNEXPLAINED)
    explained = explain_divided_part({"copy", "cut"}, {"whole"}, findings, {"cut": cut})
    assert (explained.kind, explained.outcome, explained.with_a_copy) == (
        DividedPart.LEFT_OUT,
        CutOutcome.UNDER_MIN_CUT_SHARE,
        True,
    )
    through = explain_divided_part({"whole"}, {"copy", "cut"}, findings, {"cut": cut})
    assert (through.kind, through.with_a_copy) == (DividedPart.THROUGH_A_CUT, True)


def test_a_short_copy_under_a_quarter_of_its_card_and_the_cut_inside_it() -> None:
    """The longer copies are split by the short-body step itself here: the 41-shingle copy is
    under a quarter of the 196-shingle card."""
    whole = numbered("word", 200)
    copy = whole[60:105]
    findings = diagnosed({"whole": whole, "copy": copy, "cut": copy[10:30]})
    assert findings["copy"].outcome is CutOutcome.UNDER_MIN_CUT_SHARE
    assert findings["copy"].share_of_smallest_container == pytest.approx(41 / 196)
    cut = findings["cut"]
    assert (cut.outcome, cut.containers_nested) == (CutOutcome.WITHIN_THE_RULE, True)
    assert cut.kept_apart_by == (KeptApartBy.SHORT_BODY_STEP,)


def test_a_cut_inside_two_overlapping_copies_has_two_witnesses_that_read_as_one_card() -> None:
    """Two 86-shingle copies sharing 56 shingles, neither holding the other, and the card that
    holds both. Not nested, so the cut is inside several clusters; and they read as one card, split
    by the thresholds between the two copies and by the banding between each and the card."""
    bodies = {
        "whole": WHOLE,
        "first": WHOLE[100:190],
        "second": WHOLE[130:220],
        "cut": WHOLE[140:170],
    }
    findings = diagnosed(bodies)
    cut = findings["cut"]
    assert cut.outcome is CutOutcome.SEVERAL_CLUSTERS
    assert cut.container_clusters == ("first", "second", "whole")
    assert (cut.containers_nested, cut.has_one_witness) == (False, False)
    assert cut.copies_read is CopiesRead.ONE_CARD_SPLIT
    assert cut.kept_apart_by == (KeptApartBy.BANDING, KeptApartBy.BANDING, KeptApartBy.THRESHOLDS)
    assert findings["first"].outcome is findings["second"].outcome is CutOutcome.LONG_NEVER_PAIRED


def test_the_container_first_by_fingerprint_being_over_the_share_is_flagged() -> None:
    """What `card-fingerprint-v2` measured the share against. Two copies in one cluster, 60 and 80
    shingles, and a 15-shingle cut: a quarter of the smaller, under a quarter of the larger."""
    smaller = numbered("word", 64)
    larger = [*smaller, *numbered("more", 20)]
    cut = smaller[:19]
    larger_first = diagnosed({"a": larger, "b": smaller, "c": cut}, {"a": "a", "b": "a", "c": "c"})["c"]
    assert larger_first.outcome is CutOutcome.WITHIN_THE_RULE
    assert (larger_first.smallest_container, larger_first.first_container_over_the_share) == ("b", True)
    smaller_first = diagnosed({"a": smaller, "b": larger, "c": cut}, {"a": "a", "b": "a", "c": "c"})["c"]
    assert (smaller_first.smallest_container, smaller_first.first_container_over_the_share) == ("a", False)


def test_a_long_cut_inside_two_cards_that_share_only_it() -> None:
    """Seventy words two long cards both open with, as a body of its own: the long fragment that
    can still merge two cards through the banding. 66 of each card's 166 shingles are shared."""
    fragment = numbered("shared", 70)
    bodies = {
        "fragment": fragment,
        "first": [*fragment, *numbered("first", 100)],
        "second": [*fragment, *numbered("second", 100)],
    }
    finding = diagnosed(bodies)["fragment"]
    assert finding.outcome is CutOutcome.LONG_SEVERAL_CLUSTERS
    assert (finding.copies_read, finding.containers_nested) == (CopiesRead.DIFFERENT_CARDS, False)


# ------------------------------------------------------------------------------------------------
# The banding check, and the witness's cluster
# ------------------------------------------------------------------------------------------------


def test_whether_the_banding_pairs_a_short_cut_with_its_container() -> None:
    """46 of 48 shingles is a pair the banding all but always makes; 16 of 396 one it all but never
    does. The first is what the rules before the short-body step would have merged."""
    nearly_all = numbered("word", 52)
    assert diagnosed({"body": nearly_all, "cut": nearly_all[:50]})["cut"].banded_with_a_container is True
    long_body = numbered("word", 400)
    sliver = diagnosed({"body": long_body, "cut": long_body[100:120]})["cut"]
    assert (sliver.outcome, sliver.banded_with_a_container) == (CutOutcome.UNDER_MIN_CUT_SHARE, False)


def test_the_texts_of_the_witness_cluster_a_cut_shares_nothing_with_are_counted() -> None:
    """The copy's one container is the whole card, and that card's cluster also holds a body the
    copy shares no word with: joining the copy there would put those two in one cluster."""
    bodies = {**NESTED, "elsewhere": numbered("elsewhere", 90)}
    clusters = {"whole": "whole", "elsewhere": "whole", "copy": "copy", "cut": "copy"}
    copy = diagnosed(bodies, clusters)["copy"]
    assert (copy.witness_cluster_texts, copy.witness_cluster_texts_sharing_nothing) == (2, 1)


# ------------------------------------------------------------------------------------------------
# The tally
# ------------------------------------------------------------------------------------------------


def test_the_tally_of_the_nested_copies_left_alone() -> None:
    """Two findings: the cut (within the rule, nested, split by the banding) and the long copy
    (never paired, 86 of 326 shingles: a quarter to a half, one witness cluster of one text). The
    banding flag is set by hand so the figures do not rest on which pairs the seed makes."""
    findings = diagnosed(NESTED)
    cut = replace(findings["cut"], banded_with_a_container=True)
    several = {
        "cuts": 1,
        "of which the containers are nested": 1,
        "as one card, split": 1,
        "as different cards": 0,
        "one card split, by what kept the copies apart": {KeptApartBy.BANDING.value: 1},
    }
    within = {
        "cuts": 1,
        "its containers are nested copies in several clusters": 1,
        "the container first by fingerprint is over the share": 0,
        "neither: another short body of its cluster points elsewhere": 0,
    }
    no_shares = {name: 0 for _, name in SHARE_BANDS}
    assert tally_cuts([findings["copy"], cut]) == {
        "bodies_with_a_container_outside_their_cluster": 2,
        "by_outcome": {
            outcome.value: int(outcome in (CutOutcome.WITHIN_THE_RULE, CutOutcome.LONG_NEVER_PAIRED))
            for outcome in CutOutcome
        },
        "short_with_containers_in_several_clusters": several,
        "long_with_containers_in_several_clusters": {
            **dict.fromkeys(several, 0),
            "one card split, by what kept the copies apart": {},
        },
        "short_within_the_rule_and_apart": within,
        "short_under_the_minimum_share_by_share": no_shares,
        "long_never_paired_by_share": {**no_shares, "a quarter to a half": 1},
        "long_with_one_witness_within_the_share": {
            "cuts": 1,
            "sharing text with every text of the witness's cluster": 1,
            "of which that cluster is one text": 1,
            "sharing nothing with at least one text of it": 0,
        },
        "short_the_banding_pairs_with_a_container": {
            "cuts": 1,
            "by_outcome": {CutOutcome.WITHIN_THE_RULE.value: 1},
            "with_containers_in_several_clusters": several,
            "within_the_rule_and_apart": within,
        },
        "with_a_copy_in_their_cluster_that_every_outside_container_holds": {
            "bodies": 0,
            "short": 0,
            "short_the_banding_pairs_with_an_outside_container": {
                "cuts": 0,
                "by_outcome_were_the_copy_not_there": {},
            },
        },
    }


def test_the_share_bands_end_at_the_minimum_cut_share() -> None:
    assert [limit for limit, _ in SHARE_BANDS][1] == MIN_CUT_SHARE


# ------------------------------------------------------------------------------------------------
# Divided parts
# ------------------------------------------------------------------------------------------------


def test_a_divided_part_is_explained_by_the_short_cut_that_used_to_join_it() -> None:
    """An earlier cluster of all three nested bodies, now three clusters. The cut's part left
    because the cut was left out; the whole card's part was joined to the rest only through it."""
    findings = diagnosed(NESTED)
    left_out = explain_divided_part({"cut"}, {"whole", "copy"}, findings)
    assert left_out.kind == DividedPart.LEFT_OUT
    assert (left_out.outcome, left_out.containers_nested) == (CutOutcome.WITHIN_THE_RULE, True)
    assert (left_out.copies_read, left_out.kept_apart_by) == (
        CopiesRead.ONE_CARD_SPLIT,
        (KeptApartBy.BANDING,),
    )

    through = explain_divided_part({"whole"}, {"copy", "cut"}, findings)
    assert (through.kind, through.outcome) == (DividedPart.THROUGH_A_CUT, CutOutcome.WITHIN_THE_RULE)

    assert explain_divided_part({"whole"}, {"copy"}, findings) == DividedPart(DividedPart.UNEXPLAINED)


# ------------------------------------------------------------------------------------------------
# A cluster from the inside
# ------------------------------------------------------------------------------------------------


def shape(bodies: dict[str, list[str]], copies: dict[str, int]) -> ClusterShape:
    return cluster_shape("cluster", joined(bodies), copies)


def test_the_shape_of_one_card_and_two_overlapping_cuts() -> None:
    """A 100-word card and its first and last 80 words. Every pair shares at least half: the two
    cuts share 56 of 76 shingles. The card bridges the cuts, which are not unrelated."""
    base = numbered("word", 100)
    found = shape({"base": base, "left": base[:80], "right": base[20:]}, {"base": 4, "left": 1, "right": 1})
    assert found == ClusterShape(
        cluster_id="cluster",
        cards=6,
        distinct_texts=3,
        short_texts=0,
        words_smallest=80,
        words_median=80,
        words_largest=100,
        pairs=3,
        pairs_sharing_nothing=0,
        pairs_sharing_under_half=0,
        pairs_sharing_half_or_more=3,
        pairs_matching=2,
        groups_sharing_half=1,
        largest_group_texts=3,
        largest_group_cards=6,
        texts_sharing_nothing_with_most_read=0,
        cards_sharing_nothing_with_most_read=0,
        bridging_texts=1,
        bridges_between_parts_sharing_under_half=0,
        texts_holding_parts_that_share_nothing=0,
        texts_inside_texts_that_share_under_half=0,
        such_bridges_that_are_fragments=0,
        such_bridges_that_hold_the_parts=0,
    )


def test_the_shape_of_two_cards_joined_through_a_body_that_holds_both() -> None:
    """Two 80-word cards with no word in common, and one body that is both end to end. The two
    cards share nothing; the body holding them is the only thing joining them. The most-read text
    is the first card, with five copies, and the second card's two copies share nothing with it."""
    first, second = numbered("first", 80), numbered("second", 80)
    found = shape({"both": [*first, *second], "c1": first, "c2": second}, {"both": 1, "c1": 5, "c2": 2})
    assert (found.cards, found.distinct_texts) == (8, 3)
    assert (found.words_smallest, found.words_median, found.words_largest) == (80, 80, 160)
    assert (found.pairs_sharing_nothing, found.pairs_sharing_under_half) == (1, 0)
    assert (found.pairs_sharing_half_or_more, found.pairs_matching) == (2, 2)
    assert (found.groups_sharing_half, found.largest_group_texts, found.largest_group_cards) == (1, 3, 8)
    assert (found.texts_sharing_nothing_with_most_read, found.cards_sharing_nothing_with_most_read) == (1, 2)
    assert (found.bridging_texts, found.bridges_between_parts_sharing_under_half) == (1, 1)
    assert (found.such_bridges_that_hold_the_parts, found.such_bridges_that_are_fragments) == (1, 0)
    assert found.texts_holding_parts_that_share_nothing == 1
    assert found.texts_inside_texts_that_share_under_half == 0


def test_the_shape_of_two_cards_joined_through_a_passage_both_hold() -> None:
    """Seventy words two 170-word cards both open with, and the passage as a body of its own. The
    cards share 66 of 166 shingles, under half; the passage is inside both and bridges them."""
    passage = numbered("shared", 70)
    bodies = {
        "a": [*passage, *numbered("first", 100)],
        "b": [*passage, *numbered("second", 100)],
        "f": passage,
    }
    found = shape(bodies, {"a": 3, "b": 2, "f": 1})
    assert (found.pairs_sharing_nothing, found.pairs_sharing_under_half) == (0, 1)
    assert (found.pairs_sharing_half_or_more, found.pairs_matching) == (2, 2)
    assert (found.bridging_texts, found.bridges_between_parts_sharing_under_half) == (1, 1)
    assert (found.such_bridges_that_are_fragments, found.such_bridges_that_hold_the_parts) == (1, 0)
    assert found.texts_inside_texts_that_share_under_half == 1
    assert found.texts_holding_parts_that_share_nothing == 0
    assert found.texts_sharing_nothing_with_most_read == 0
    assert (found.words_smallest, found.words_median, found.words_largest) == (70, 170, 170)


def test_the_shape_of_an_empty_cluster_is_all_zeroes() -> None:
    found = cluster_shape("cluster", {}, {})
    assert (found.cards, found.distinct_texts, found.pairs, found.words_median) == (0, 0, 0, 0)
    assert found.as_json()["cluster_id"] == "cluster"


# ------------------------------------------------------------------------------------------------
# Edges of the reading
# ------------------------------------------------------------------------------------------------


def test_two_short_copies_a_word_apart_in_length_were_split_by_the_banding_alone() -> None:
    """A 50-word copy and the same with two words more share 46 of 48 shingles: over the Jaccard
    threshold, so only never being paired could have left them in two clusters."""
    copy = numbered("word", 50)
    bodies = {"copy": copy, "longer": [*copy, *numbered("more", 2)], "cut": copy[10:40]}
    cut = diagnosed(bodies)["cut"]
    assert (cut.containers_nested, cut.kept_apart_by) == (True, (KeptApartBy.BANDING,))


def test_a_cut_with_more_containers_in_a_cluster_than_are_compared() -> None:
    """Fourteen copies of growing length in one cluster, and a different body in another that holds
    the cut and not the smallest copy. The smallest copy is among the dozen compared: it shares the
    cut's 16 shingles with the other body, 16 of its own 27."""
    base = numbered("word", 30)
    cut = base[5:25]
    bodies = {f"c{index:02}": [*base, *numbered(f"x{index}x", index + 1)] for index in range(14)}
    bodies["other"] = [*numbered("before", 10), *cut, *numbered("after", 10)]
    bodies["cut"] = cut
    clusters = {key: "other" if key == "other" else "cut" if key == "cut" else "c00" for key in bodies}
    finding = diagnosed(bodies, clusters)["cut"]
    assert finding.outcome is CutOutcome.SEVERAL_CLUSTERS
    assert len(finding.containers) == 15
    assert (finding.copies_read, finding.kept_apart_by) == (
        CopiesRead.ONE_CARD_SPLIT,
        (KeptApartBy.THRESHOLDS,),
    )


def test_two_near_identical_texts_match_in_a_clusters_shape() -> None:
    base = numbered("word", 100)
    found = shape({"base": base, "twin": replaced(base, 50, "changed")}, {"base": 1, "twin": 1})
    assert (found.pairs, found.pairs_matching, found.bridging_texts) == (1, 1, 0)

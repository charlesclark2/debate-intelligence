"""Near-duplicate clustering against the hand-labelled variant set (`v1-e31-t04` ac2).

`tests/fixtures/fingerprints/variants.jsonl` is 35 copies of 9 invented cards. Each row's `card`
field says which card it is a copy of, and those labels were written and committed before the
clusterer existed (commit "Add the hand-labelled near-duplicate variant set"), so nothing the
clusterer does can have shaped them (`docs/process/working-agreements.md` §6).

Two copies are the *same card* exactly when their labels are equal. Precision and recall are
counted over every pair of rows: 595 pairs, 75 of them same-card by label.

The set is built to make precision hard as well as recall:

* **A second card from the same article** (`pellam-canopy-fund`) opens with the first card's last
  sentence, and one copy of the first card (`a1-extra-paragraph`) was cut long enough to take in
  the second card's next two sentences as well.
* **The same author on adjacent pages** (`quenby-page-14`, `quenby-page-15`) share a whole sentence.
* **Two authors quoting the same statute** (`marchetti-…`, `oyelaran-…`) open with the same
  thirty-six words.
* **Two short cards from one article** (`ilves-…`) open with the same eleven words.

Nothing here is real: invented authors, invented journals, invented arguments, and no cutter mark
except the obviously synthetic `zzTEST`.
"""

from __future__ import annotations

import itertools
import json
import random
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Final

import pytest

from debate_core.domain.caselist import SourceOrigin
from debate_core.domain.debate_files import (
    CardCompleteness,
    FileImportProvenance,
    FormattingSpan,
    ParsedCard,
)
from debate_core.domain.style_profile import RunEmphasis, StyleMatchSource
from debate_core.evidence.fingerprints import card_fingerprint
from debate_core.evidence.near_duplicates import (
    LSH_BANDS,
    LSH_ROWS_PER_BAND,
    MAX_CONTAINER_CLUSTERS,
    MIN_CUT_SHARE,
    MINHASH_PERMUTATIONS,
    SHINGLE_SIZE,
    SHORT_BODY_SHINGLES,
    NearDuplicateThresholds,
    cluster_near_duplicates,
    contained_but_for_one_word,
    containment,
    jaccard,
    matching_words,
    minhash_signature,
    shingles,
    word_shingles,
)

VARIANTS_PATH = Path(__file__).resolve().parents[4] / "tests" / "fixtures" / "fingerprints" / "variants.jsonl"

REQUIRED_PRECISION = 0.98
REQUIRED_RECALL = 0.90


@dataclass(frozen=True)
class Variant:
    """One labelled row of the variant set, read into the ParsedCard the clusterer would see."""

    variant_id: str
    label: str
    card: ParsedCard


def load_variants() -> list[Variant]:
    variants: list[Variant] = []
    for position, line in enumerate(VARIANTS_PATH.read_text(encoding="utf-8").splitlines()):
        row = json.loads(line)
        card = ParsedCard(
            tag=row["tag"],
            short_cite=row["short_cite"],
            full_cite=row["full_cite"],
            evidence_text=row["evidence_text"],
            completeness=CardCompleteness.FULL,
            formatting_spans=tuple(
                FormattingSpan(
                    emphasis=RunEmphasis.HIGHLIGHT,
                    start_offset=start,
                    end_offset=end,
                    highlight_color="cyan",
                    rule_id="variant-set-highlight",
                    match_source=StyleMatchSource.VERBATIM,
                )
                for start, end in row["highlights"]
            ),
            match_source=StyleMatchSource.VERBATIM,
            confidence=1.0,
            provenance=FileImportProvenance(
                source_sha256=f"{position:064x}",
                source_path=f"variant-set/{row['id']}.docx",
                origin=SourceOrigin.CASELIST_ARCHIVE,
                caselist="testcl26",
                snapshot=date(2026, 9, 1),
                first_element_index=0,
                last_element_index=0,
                parser_version="variant-set",
                profile_version="variant-set",
            ),
        )
        variants.append(Variant(variant_id=row["id"], label=row["card"], card=card))
    return variants


def cluster_ids(variants: list[Variant], thresholds: NearDuplicateThresholds | None = None) -> dict[str, str]:
    """Variant id to cluster id, feeding the clusterer bodies in the order the variants are given."""
    fingerprints = {
        variant.variant_id: card_fingerprint(variant.card).exact_fingerprint for variant in variants
    }
    bodies: dict[str, str] = {}
    for variant in variants:
        bodies.setdefault(fingerprints[variant.variant_id], variant.card.evidence_text)
    clusters = cluster_near_duplicates(bodies, thresholds)
    return {variant_id: clusters[fingerprint] for variant_id, fingerprint in fingerprints.items()}


@dataclass(frozen=True)
class PairCounts:
    true_positives: int
    false_positives: int
    false_negatives: int

    @property
    def precision(self) -> float:
        predicted = self.true_positives + self.false_positives
        return self.true_positives / predicted if predicted else 1.0

    @property
    def recall(self) -> float:
        labelled = self.true_positives + self.false_negatives
        return self.true_positives / labelled if labelled else 1.0


def pair_counts(variants: list[Variant], clusters: dict[str, str]) -> PairCounts:
    true_positives = false_positives = false_negatives = 0
    for left, right in itertools.combinations(variants, 2):
        same_card = left.label == right.label
        same_cluster = clusters[left.variant_id] == clusters[right.variant_id]
        if same_card and same_cluster:
            true_positives += 1
        elif same_cluster:
            false_positives += 1
        elif same_card:
            false_negatives += 1
    return PairCounts(true_positives, false_positives, false_negatives)


@pytest.fixture(scope="module")
def variants() -> list[Variant]:
    return load_variants()


# ------------------------------------------------------------------------------------------------
# The variant set is what it says it is
# ------------------------------------------------------------------------------------------------


def test_variant_set_covers_every_variation_the_spec_names(variants: list[Variant]) -> None:
    ids = {variant.variant_id for variant in variants}
    for required in (
        "a1-trimmed-start",
        "a1-trimmed-end",
        "a1-extra-paragraph",
        "a1-ocr-spacing",
        "a1-rehighlighted",
        "a2-original",  # a different card from the same article
        "b15-original",  # the same author, the adjacent page
    ):
        assert required in ids
    assert len(variants) == 35
    labelled_pairs = sum(
        1 for left, right in itertools.combinations(variants, 2) if left.label == right.label
    )
    assert labelled_pairs == 75


def test_retagged_and_rehighlighted_copies_share_the_exact_fingerprint(variants: list[Variant]) -> None:
    by_id = {variant.variant_id: card_fingerprint(variant.card) for variant in variants}
    assert by_id["a1-retagged-smart-quotes"] == by_id["a1-original"] == by_id["a1-rehighlighted"]
    assert by_id["b15-retagged"] == by_id["b15-original"]
    assert by_id["c-recited-reflowed"] == by_id["c-original"] == by_id["c-rehighlighted"]
    assert by_id["f-retagged"] == by_id["f-original"]
    assert by_id["a1-one-word-typo"] != by_id["a1-original"]


# ------------------------------------------------------------------------------------------------
# ac2: precision and recall against the hand labels
# ------------------------------------------------------------------------------------------------


def test_near_duplicate_precision_and_recall_meet_the_bar(variants: list[Variant]) -> None:
    counts = pair_counts(variants, cluster_ids(variants))
    print(
        f"\nvariant set: {counts.true_positives} true positive, {counts.false_positives} false positive, "
        f"{counts.false_negatives} false negative pairs; precision {counts.precision:.3f}, "
        f"recall {counts.recall:.3f}"
    )
    assert counts.precision >= REQUIRED_PRECISION
    assert counts.recall >= REQUIRED_RECALL


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("a1-original", "a2-original"),
        ("a1-extra-paragraph", "a2-original"),
        ("a1-extra-paragraph", "a2-trimmed-end"),
        ("b14-original", "b15-original"),
        ("b14-ocr-spacing", "b15-trimmed-end"),
        ("d-original", "e-original"),
        ("d-trimmed-end", "e-ocr-spacing"),
        ("f-original", "g-original"),
        ("f-trimmed-end", "g-original"),
    ],
)
def test_hard_negatives_stay_in_separate_clusters(variants: list[Variant], left: str, right: str) -> None:
    clusters = cluster_ids(variants)
    assert clusters[left] != clusters[right]


@pytest.mark.parametrize(
    "variant_id",
    [
        "a1-trimmed-start",
        "a1-trimmed-end",
        "a1-extra-paragraph",
        "a1-ocr-spacing",
        "a1-one-word-typo",
        "c-trimmed-start",
        "c-trimmed-end",
        "c-extra-paragraph",
        "c-ocr-spacing",
        "c-trimmed-both-ends-ocr",
    ],
)
def test_long_card_variants_join_the_original(variants: list[Variant], variant_id: str) -> None:
    clusters = cluster_ids(variants)
    original = f"{variant_id.split('-')[0]}-original"
    assert clusters[variant_id] == clusters[original]


def test_cluster_id_is_the_smallest_exact_fingerprint_in_the_cluster(variants: list[Variant]) -> None:
    clusters = cluster_ids(variants)
    members: dict[str, set[str]] = {}
    for variant in variants:
        members.setdefault(clusters[variant.variant_id], set()).add(
            card_fingerprint(variant.card).exact_fingerprint
        )
    for cluster_id, fingerprints in members.items():
        assert cluster_id == min(fingerprints)


# ------------------------------------------------------------------------------------------------
# ac2: stable across runs and input order
# ------------------------------------------------------------------------------------------------


def test_cluster_ids_are_identical_across_runs(variants: list[Variant]) -> None:
    assert cluster_ids(variants) == cluster_ids(variants)


@pytest.mark.parametrize("shuffle_seed", [1, 2, 3, 4, 5])
def test_cluster_ids_do_not_depend_on_input_order(variants: list[Variant], shuffle_seed: int) -> None:
    reordered = list(variants)
    random.Random(shuffle_seed).shuffle(reordered)
    assert reordered != variants
    assert cluster_ids(reordered) == cluster_ids(variants)
    assert cluster_ids(list(reversed(variants))) == cluster_ids(variants)


def test_cluster_ids_do_not_depend_on_the_process_hash_seed(variants: list[Variant]) -> None:
    """A fresh interpreter under two different `PYTHONHASHSEED`s agrees with this one."""
    script = (
        "import json, sys\n"
        "from debate_core.evidence.fingerprints import fingerprint_text\n"
        "from debate_core.evidence.near_duplicates import cluster_near_duplicates\n"
        "rows = [json.loads(line) for line in open(sys.argv[1], encoding='utf-8')]\n"
        "bodies = {fingerprint_text(row['evidence_text']): row['evidence_text'] for row in rows}\n"
        "print(json.dumps(cluster_near_duplicates(bodies), sort_keys=True))\n"
    )
    expected = {
        card_fingerprint(variant.card).exact_fingerprint: cluster_id
        for variant, cluster_id in zip(variants, cluster_ids(variants).values(), strict=True)
    }
    for hash_seed in ("0", "12345"):
        completed = subprocess.run(
            [sys.executable, "-c", script, str(VARIANTS_PATH)],
            check=True,
            capture_output=True,
            text=True,
            env={"PYTHONHASHSEED": hash_seed, "PYTHONIOENCODING": "utf-8"},
        )
        assert json.loads(completed.stdout) == expected


def test_union_makes_the_smallest_fingerprint_the_root_whatever_the_merge_order() -> None:
    """A chain a-b, b-c, c-d merged in every order ends at the same representative."""
    body = (
        "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
        "sixteen seventeen eighteen nineteen twenty"
    )
    words = body.split()
    # Each copy drops one different word from the end, so each contains the next.
    chain = {f"{'f' * 63}{index}": " ".join(words[: len(words) - index]) for index in range(4)}
    expected = min(chain)
    for ordering in itertools.permutations(sorted(chain)):
        clusters = cluster_near_duplicates({key: chain[key] for key in ordering})
        assert set(clusters.values()) == {expected}


# ------------------------------------------------------------------------------------------------
# The pieces
# ------------------------------------------------------------------------------------------------


def test_matching_words_rejoin_line_break_hyphenation_and_drop_punctuation() -> None:
    assert matching_words("The Varrow Commis-\nsion ; it said,so") == [
        "the",
        "varrow",
        "commission",
        "it",
        "said",
        "so",
    ]
    assert matching_words("night-time") == ["night", "time"]


def test_shingles_are_word_runs_of_the_configured_size() -> None:
    assert SHINGLE_SIZE == 5
    assert shingles("a b c d e f") == frozenset({"a b c d e", "b c d e f"})
    assert shingles("too short") == frozenset({"too short"})
    assert shingles("  ") == frozenset()


def test_signature_has_the_configured_shape_and_is_order_free() -> None:
    assert (MINHASH_PERMUTATIONS, LSH_BANDS, LSH_ROWS_PER_BAND) == (128, 32, 4)
    shingle_list = sorted(shingles("the dam operators lowered the reservoir twice in one season"))
    signature = minhash_signature(shingle_list)
    assert len(signature) == MINHASH_PERMUTATIONS
    assert minhash_signature(reversed(shingle_list)) == signature
    assert minhash_signature(shingle_list, seed="another-seed") != signature


def test_similarity_measures() -> None:
    left = frozenset({"a", "b", "c", "d"})
    right = frozenset({"c", "d"})
    assert jaccard(left, right) == 0.5
    assert containment(left, right) == 1.0
    assert jaccard(frozenset(), frozenset()) == 0.0
    assert containment(frozenset(), right) == 0.0


def test_thresholds_are_configurable(variants: list[Variant]) -> None:
    """A stricter bar splits the trimmed copies off; the default keeps them."""
    strict = NearDuplicateThresholds(jaccard=1.0, containment=1.0)
    relaxed = cluster_ids(variants)
    strict_clusters = cluster_ids(variants, strict)
    assert relaxed["a1-ocr-spacing"] == relaxed["a1-original"]
    assert strict_clusters["a1-ocr-spacing"] != strict_clusters["a1-original"]


# ------------------------------------------------------------------------------------------------
# Short bodies (`v1-e31-t08`): matched as cuts, by enumeration, and never by a guess
# ------------------------------------------------------------------------------------------------

LIBRARY: list[str] = [
    *("extending", "library", "hours", "past", "nine", "in", "the", "evening", "tripled", "the"),
    *("number", "of", "students", "using", "the", "study", "rooms", "on", "weeknights"),
]
"""Nineteen words. `students` is the thirteenth: twelve words before it and six after."""


def numbered(stem: str, count: int) -> list[str]:
    """`count` distinct invented words, so no shingle is shared except where a test shares it."""
    return [f"{stem}{index}" for index in range(count)]


def clustered(*bodies: list[str]) -> list[str]:
    """Cluster ids of `bodies`, in the order given. Each body is keyed by a made-up fingerprint."""
    keys = [f"{index:064x}" for index in range(len(bodies))]
    clusters = cluster_near_duplicates({key: " ".join(body) for key, body in zip(keys, bodies, strict=True)})
    return [clusters[key] for key in keys]


def replaced(words: list[str], position: int, *replacement: str, count: int = 1) -> list[str]:
    return [*words[:position], *replacement, *words[position + count :]]


@pytest.mark.parametrize(
    ("short", "long"),
    [
        # One word changed.
        (replaced(LIBRARY, 12, "studnts"), LIBRARY),
        (LIBRARY, replaced(LIBRARY, 12, "studnts")),
        # One word split in two by a stray space, read from either side.
        (LIBRARY, replaced(LIBRARY, 12, "stud", "ents")),
        (replaced(LIBRARY, 12, "stud", "ents"), [*numbered("before", 3), *LIBRARY, *numbered("after", 3)]),
        # Two words run together.
        (replaced(LIBRARY, 5, "inthe", count=2), LIBRARY),
        # One word dropped from the copy, and one added to it.
        (replaced(LIBRARY, 9, count=1), LIBRARY),
        (LIBRARY, replaced(LIBRARY, 9, count=1)),
        # A cut of the body, with a changed word inside the cut.
        (replaced(LIBRARY, 12, "studnts")[3:], LIBRARY),
        # No change at all: wholly inside.
        (LIBRARY[2:17], LIBRARY),
    ],
)
def test_a_short_body_is_inside_another_but_for_one_word(short: list[str], long: list[str]) -> None:
    assert contained_but_for_one_word(short, long)


@pytest.mark.parametrize(
    ("short", "long"),
    [
        # The changed word has fewer than five unchanged words before it, or after it.
        (replaced(LIBRARY, 3, "passed"), LIBRARY),
        (replaced(LIBRARY, 15, "studdy"), LIBRARY),
        # Two words changed, however far apart.
        (replaced(replaced(LIBRARY, 6, "teh"), 12, "studnts"), LIBRARY),
        # Two adjacent words changed.
        (replaced(LIBRARY, 11, "off", "studnts", count=2), LIBRARY),
        # Two cards that open with the same twelve words and then say different things.
        ([*LIBRARY[:12], "pupils", "enrolled"], LIBRARY),
        ([*LIBRARY[:12], *numbered("otherwise", 7)], LIBRARY),
        # Too short to have five unchanged words on both sides of anything.
        (replaced(LIBRARY[:10], 5, "inn"), LIBRARY),
        # Its opening is nowhere in the other body.
        (numbered("unrelated", 19), LIBRARY),
        # Fewer than five words: no opening to look for.
        (LIBRARY[:4], LIBRARY),
    ],
)
def test_a_short_body_is_not_inside_another_but_for_one_word(short: list[str], long: list[str]) -> None:
    assert not contained_but_for_one_word(short, long)


def test_the_short_line_is_where_the_containment_threshold_admits_one_changed_word() -> None:
    """`SHORT_BODY_SHINGLES` is derived, not chosen: at the line, t04's rule needs no help.

    The costliest change the short step tolerates is a word split in two inside a cut of a longer
    body, which costs the cut the `SHINGLE_SIZE + 1` shingles that hold either half. That is a tenth
    of 60: one shingle fewer and the threshold refuses it, which is the case the step is for.
    """
    assert SHORT_BODY_SHINGLES == (SHINGLE_SIZE + 1) * 10
    limit = NearDuplicateThresholds().containment
    body = numbered("word", 200)

    def cut_with_a_split_word(shingle_count: int) -> list[str]:
        cut = replaced(body[50 : 50 + shingle_count + SHINGLE_SIZE - 2], 30, "split", "apart")
        assert len(word_shingles(cut)) == shingle_count
        return cut

    def overlap(cut: list[str]) -> float:
        return containment(frozenset(word_shingles(cut)), frozenset(word_shingles(body)))

    at_the_line = cut_with_a_split_word(SHORT_BODY_SHINGLES)
    under_the_line = cut_with_a_split_word(SHORT_BODY_SHINGLES - 1)
    assert contained_but_for_one_word(at_the_line, body)
    assert contained_but_for_one_word(under_the_line, body)
    assert overlap(at_the_line) >= limit
    assert overlap(under_the_line) < limit


def test_a_short_copy_with_one_changed_word_joins_its_card() -> None:
    original, typo, unrelated = clustered(LIBRARY, replaced(LIBRARY, 12, "studnts"), numbered("other", 19))
    assert original == typo
    assert unrelated != original


def test_a_short_cut_joins_the_one_card_it_is_inside() -> None:
    """Thirteen words of a 38-word card: a quarter of its shingles, which the banding rarely pairs."""
    card = [*numbered("shared", 13), *numbered("first", 25)]
    assert len(set(clustered(card, card[:13]))) == 1


def test_a_short_body_inside_two_different_cards_joins_neither_and_does_not_merge_them() -> None:
    """The fragment two cards share is a cut of either. Joining one would be a guess, and joining
    both would make one card of two."""
    opening = numbered("shared", 13)
    first = [*opening, *numbered("first", 25)]
    second = [*opening, *numbered("second", 24)]
    assert len(set(clustered(first, second, opening))) == 3
    assert len(set(clustered(first, opening))) == 1
    assert len(set(clustered(second, opening))) == 1


def test_a_short_cut_joins_once_the_copies_that_hold_it_are_one_cluster() -> None:
    """Two copies of one card a word apart both hold the cut, and are one cluster by the same step."""
    card = [*numbered("shared", 13), *numbered("first", 25)]
    assert len(set(clustered(card, replaced(card, 20, "changed"), card[:13]))) == 1


def test_a_short_cut_joins_a_body_no_more_than_four_times_its_size() -> None:
    assert MIN_CUT_SHARE == 0.25
    body = numbered("word", 64)  # 60 shingles
    a_quarter = body[:19]  # 15 shingles
    under_a_quarter = body[:18]  # 14 shingles
    assert len(set(clustered(body, a_quarter))) == 1
    assert len(set(clustered(body, under_a_quarter))) == 2


def test_a_body_too_large_to_join_still_makes_a_short_body_ambiguous() -> None:
    """A whole section parsed as one card holds many cards' text. It cannot gather them, and a
    short body inside it and inside one real card is still inside two."""
    fragment = numbered("shared", 14)
    card = [*fragment, *numbered("card", 20)]
    section = [*numbered("before", 100), *fragment, *numbered("after", 100)]
    assert len(set(clustered(card, fragment))) == 1
    assert len(set(clustered(card, section, fragment))) == 3


def templated(count: int, middle: int = 20) -> list[list[str]]:
    """`count` different bodies that all open with the same five words and close with the same five."""
    return [
        [*numbered("opens", 5), *numbered(f"body{index}x", middle), *numbered("closes", 5)]
        for index in range(count)
    ]


def test_a_short_body_that_opens_and_closes_like_many_others_is_left_alone() -> None:
    """Past `MAX_CONTAINER_CLUSTERS` other clusters holding both its ends, nothing is compared."""
    assert MAX_CONTAINER_CLUSTERS == 8
    few = templated(MAX_CONTAINER_CLUSTERS)
    many = templated(MAX_CONTAINER_CLUSTERS + 1)
    copy = replaced(few[0], 15, "changed")
    assert copy == replaced(many[0], 15, "changed")

    joined = clustered(*few, copy)
    assert joined[-1] == joined[0]
    assert len(set(joined)) == MAX_CONTAINER_CLUSTERS

    left_alone = clustered(*many, copy)
    assert len(set(left_alone)) == MAX_CONTAINER_CLUSTERS + 2


def test_a_cluster_with_one_body_too_common_to_compare_joins_nothing() -> None:
    """Two near-identical short copies are one cluster by Jaccard, and both open and close like
    nine other cards. The first is left alone, and so is the cluster when the second comes up."""
    many = templated(MAX_CONTAINER_CLUSTERS + 2, middle=49)
    copy = replaced(many[0], 30, "changed")
    assert jaccard(frozenset(word_shingles(many[0])), frozenset(word_shingles(copy))) >= 0.8

    clusters = clustered(*many, copy)
    assert clusters[-1] == clusters[0]
    assert len(set(clusters)) == MAX_CONTAINER_CLUSTERS + 2


def test_a_long_bodys_cut_is_still_left_to_the_banding() -> None:
    """The short step is for short bodies. Two long bodies are matched exactly as before it existed:
    a 64-word cut of a 400-word card shares a seventh of its shingles, the banding does not pair
    them, and nothing else looks. One word shorter, the cut is short and is not a quarter of the
    card, so it does not join either; cut from a card four times its size, it does."""
    card = numbered("word", 400)
    long_cut = card[100:164]
    assert len(word_shingles(long_cut)) == SHORT_BODY_SHINGLES
    assert len(set(clustered(card, long_cut))) == 2

    smaller_card = card[80:320]  # 236 shingles: four times 59
    short_cut = card[100:163]
    assert len(word_shingles(short_cut)) == SHORT_BODY_SHINGLES - 1
    assert len(set(clustered(smaller_card, short_cut))) == 1
    assert len(set(clustered(smaller_card, long_cut))) == 2


# ------------------------------------------------------------------------------------------------
# Short cuts whose containers are several copies of one card (`v1-e31-t11`)
# ------------------------------------------------------------------------------------------------
#
# On the re-parsed corpus the short-body step left 81 short cuts out of a cluster the earlier
# rules had put them in. Counted by `scripts/compare_card_clusters.py diagnose`, 27 of them are
# the two cases below; the limits that held the rest are kept, and have a case here too.


def partition(*bodies: list[str]) -> list[list[int]]:
    """Which of `bodies` share a cluster, as sorted groups of their positions."""
    groups: dict[str, list[int]] = {}
    for position, cluster in enumerate(clustered(*bodies)):
        groups.setdefault(cluster, []).append(position)
    return sorted(groups.values())


def keyed_partition(bodies: dict[str, list[str]]) -> list[list[str]]:
    """The same for bodies under fingerprints the test chooses, so their sort order is the test's."""
    clusters = cluster_near_duplicates({key: " ".join(body) for key, body in bodies.items()})
    groups: dict[str, list[str]] = {}
    for key in bodies:
        groups.setdefault(clusters[key], []).append(key)
    return sorted(sorted(group) for group in groups.values())


def test_a_short_cut_is_measured_against_the_smallest_body_that_holds_it() -> None:
    """One cluster holds the cut in two copies: one four times its size, and that copy with twenty
    words more. The cut is a quarter of the smaller, so it joins. Before `v1-e31-t11` the share was
    tested against whichever copy's fingerprint sorted first, and a digest decided the outcome."""
    smaller = numbered("word", 64)  # 60 shingles
    larger = [*smaller, *numbered("more", 20)]  # 80 shingles
    cut = smaller[:19]  # 15 shingles: a quarter of 60, under a quarter of 80
    assert len(word_shingles(cut)) == MIN_CUT_SHARE * len(word_shingles(smaller))
    assert len(word_shingles(cut)) < MIN_CUT_SHARE * len(word_shingles(larger))
    assert partition(smaller, larger) == [[0, 1]]  # the two copies are one cluster before the cut

    assert keyed_partition({"a": smaller, "b": larger, "c": cut}) == [["a", "b", "c"]]
    assert keyed_partition({"a": larger, "b": smaller, "c": cut}) == [["a", "b", "c"]]


def test_a_short_cut_under_a_quarter_of_every_body_that_holds_it_still_stays_out() -> None:
    """The share is a limit, not a formality: under a quarter of the smallest copy, no join."""
    smaller = numbered("word", 64)
    larger = [*smaller, *numbered("more", 20)]
    assert keyed_partition({"a": smaller, "b": larger, "c": smaller[:18]}) == [["a", "b"], ["c"]]


WHOLE: Final = numbered("word", 330)
"""A long card. No copy below shares enough of it for the banding to pair them: checked in the
tests that rely on it, since which pairs the banding makes is the seed's doing, not arithmetic."""

LONG_COPY: Final = WHOLE[100:190]
"""Ninety words of it (86 shingles): a long body, and just over a quarter of the whole."""

CUT_OF_THE_COPY: Final = LONG_COPY[10:40]
"""Thirty words (26 shingles) of the copy: a short body, three-tenths of the copy."""


def test_a_short_cut_inside_nested_copies_joins_the_smallest_of_them() -> None:
    """The cut is inside the copy, and the copy is inside the whole card. The banding never paired
    the two long bodies, so they are two clusters, and the cut was "inside more than one cluster"
    and left out of both. But the larger holds everything the smaller does: being inside it says
    nothing the smaller did not. One witness, not two, so the cut joins the smaller copy."""
    assert partition(WHOLE, LONG_COPY) == [[0], [1]]  # the split among the longer copies
    assert partition(WHOLE, LONG_COPY, CUT_OF_THE_COPY) == [[0], [1, 2]]


def test_a_short_cut_joins_a_short_copy_that_a_longer_card_holds() -> None:
    """The same when the smaller copy is itself short and under a quarter of the whole card, which
    is what keeps it out of the card's cluster. The cut is two-fifths of the copy."""
    whole = numbered("word", 200)
    copy = whole[60:105]  # 41 shingles of 196
    cut = copy[10:30]  # 16 shingles
    assert partition(whole, copy) == [[0], [1]]
    assert partition(whole, copy, cut) == [[0], [1, 2]]


def test_a_larger_copy_with_one_changed_word_still_holds_the_smaller() -> None:
    """Whether the larger body holds the smaller is the test a cut is confirmed by: a short copy is
    held but for one word. Here the whole card has a typo inside the copy and outside the cut."""
    whole = numbered("word", 200)
    copy = whole[60:105]
    cut = copy[10:30]
    typo = replaced(whole, 60 + 37, "changed")
    assert containment(frozenset(word_shingles(copy)), frozenset(word_shingles(typo))) < 0.9
    assert contained_but_for_one_word(copy, typo)
    assert partition(typo, copy, cut) == [[0], [1, 2]]


def test_a_short_cut_inside_nested_copies_and_a_third_card_joins_nothing() -> None:
    """A third body holds the cut and not the smaller copy. That is a second witness: the cut is
    inside two bodies neither of which accounts for the other, and joins neither."""
    other = [*numbered("other", 40), *CUT_OF_THE_COPY, *numbered("ending", 40)]
    assert partition(WHOLE, LONG_COPY, other, CUT_OF_THE_COPY) == [[0], [1], [2], [3]]


def test_a_short_cut_inside_two_overlapping_copies_joins_neither() -> None:
    """Two copies that overlap by two-thirds and each have text the other lacks. Neither holds the
    other, so the cut both contain is still inside two clusters. This is the largest group of cuts
    the corpus diagnosis found left out, and the rule that leaves them out is kept: which of two
    different extents of a text a cut belongs to is a guess."""
    first, second = WHOLE[100:190], WHOLE[130:220]
    cut = WHOLE[140:170]
    shared = containment(frozenset(word_shingles(first)), frozenset(word_shingles(second)))
    assert 0.5 <= shared < 0.9
    assert partition(WHOLE, first, second, cut) == [[0], [1], [2], [3]]


def test_a_body_in_the_larger_copys_cluster_that_does_not_hold_the_smaller_is_a_second_witness() -> None:
    """An 800-word card and a near-copy of it, one cluster by Jaccard, in which the passage the
    90-word copy was cut from is reworded around the cut. The card holds the copy; its near-copy
    holds the cut and not the copy. Every container outside the smaller copy's cluster has to
    account for itself, not just the smallest of them, so the cut is inside two and joins neither."""
    card = numbered("word", 800)
    copy = card[100:190]
    cut = copy[10:40]
    reworded = [
        *card[:100],
        *numbered("re", 10),
        *cut,
        *numbered("worded", 50),
        *card[190:],
        *numbered("z", 5),
    ]
    assert len(reworded) > len(card)
    assert jaccard(frozenset(word_shingles(card)), frozenset(word_shingles(reworded))) >= 0.8
    assert partition(card, reworded, copy) == [[0, 1], [2]]
    assert partition(card, reworded, copy, cut) == [[0, 1], [2], [3]]
    assert partition(card, copy, cut) == [[0], [1, 2]]  # and without the near-copy, it joins


@pytest.mark.parametrize("twin_sorts_first", [False, True])
def test_two_copies_of_one_size_in_one_cluster_do_not_leave_the_outcome_to_a_digest(
    twin_sorts_first: bool,
) -> None:
    """The 90-word copy and a twin of it with a different ending: 77 of 86 shingles shared, one
    cluster by Jaccard, and neither holds the other. The whole card holds the copy and not the
    twin. Whichever of the two sorts first, the card holds a container of the cut inside their
    cluster, so it is no second witness and the cut joins them."""
    twin = [*LONG_COPY[:81], *numbered("ending", 9)]
    shared = len(frozenset(word_shingles(twin)) & frozenset(word_shingles(LONG_COPY)))
    assert (shared, len(word_shingles(twin))) == (77, 86)  # Jaccard 77/95, containment under 0.9
    keys = {"copy": "2", "twin": "1" if twin_sorts_first else "3", "whole": "4", "cut": "5"}
    bodies = {keys["copy"]: LONG_COPY, keys["twin"]: twin, keys["whole"]: WHOLE, keys["cut"]: CUT_OF_THE_COPY}
    assert keyed_partition(bodies) == sorted(
        [sorted([keys["copy"], keys["twin"], keys["cut"]]), [keys["whole"]]]
    )


def test_a_short_cut_under_a_quarter_of_the_smallest_nested_copy_stays_out() -> None:
    cut = LONG_COPY[10:30]  # 16 shingles of 86
    assert len(word_shingles(cut)) < MIN_CUT_SHARE * len(word_shingles(LONG_COPY))
    assert partition(WHOLE, LONG_COPY, cut) == [[0], [1], [2]]


def test_joining_the_smallest_nested_copy_never_merges_the_longer_copies() -> None:
    """The cut joins one cluster and merges none: the long bodies are where they were without it."""
    with_the_cut = clustered(WHOLE, LONG_COPY, CUT_OF_THE_COPY)
    without = clustered(WHOLE, LONG_COPY)
    assert with_the_cut[:2] == without


@pytest.mark.parametrize("ordering", list(itertools.permutations(range(3))))
def test_nested_copies_cluster_the_same_under_any_fingerprints(ordering: tuple[int, ...]) -> None:
    """Which body is "the smallest" is decided by size, then fingerprint: never by input order."""
    bodies = (WHOLE, LONG_COPY, CUT_OF_THE_COPY)
    keys = [f"{position:064x}" for position in ordering]
    clusters = cluster_near_duplicates({key: " ".join(body) for key, body in zip(keys, bodies, strict=True)})
    whole, copy, cut = (clusters[key] for key in keys)
    assert whole != copy
    assert cut == copy


def test_a_cut_with_two_witnesses_is_measured_against_the_smallest_once_they_are_one_cluster() -> None:
    """A 150-word card, a near-copy of it that rewords ten words, a 50-word copy of the passage
    holding those ten words, and a 16-word cut from the part both versions keep.

    The cut has two witnesses at first: the short copy, and the card's cluster, because the
    near-copy holds the cut and not the short copy. Then the short copy joins the card (46 of its
    146 shingles), and every witness is one cluster. The cut is 12 shingles: over a quarter of the
    short copy's 46 and a twelfth of the card's 146. It is the smallest body holding it that the
    share is of, so it joins.
    """
    card = numbered("word", 150)
    near_copy = replaced(card, 20, *numbered("reworded", 10), count=10)
    short_copy = card[20:70]
    cut = card[30:46]
    assert jaccard(frozenset(word_shingles(card)), frozenset(word_shingles(near_copy))) >= 0.8
    assert not contained_but_for_one_word(short_copy, near_copy)
    assert len(word_shingles(cut)) >= MIN_CUT_SHARE * len(word_shingles(short_copy))
    assert len(word_shingles(cut)) < MIN_CUT_SHARE * len(word_shingles(card))
    assert partition(card, near_copy, short_copy) == [[0, 1, 2]]
    assert partition(card, near_copy, short_copy, cut) == [[0, 1, 2, 3]]


# ------------------------------------------------------------------------------------------------
# Long cuts, and joins only on text two bodies share (`v1-e31-t20`)
# ------------------------------------------------------------------------------------------------
#
# The PM's ruling of 2026-10-16: a card is a passage. Two bodies are one card when one holds the
# other or they overlap; two passages of one article are two cards. Bodies join only on text they
# share directly, never through a third body that holds both, and a body that holds the passages
# of two or more clusters is not a witness for joining any of them.


def shares_text_throughout(*bodies: list[str]) -> bool:
    """Whether every two of `bodies` that `clustered` puts in one cluster share a shingle."""
    clusters = clustered(*bodies)
    sets = [frozenset(word_shingles(body)) for body in bodies]
    return all(
        not sets[left].isdisjoint(sets[right])
        for left, right in itertools.combinations(range(len(bodies)), 2)
        if clusters[left] == clusters[right]
    )


FIRST_PASSAGE: Final = numbered("first", 59)
"""Fifty-nine words (55 shingles): a short body."""

SECOND_PASSAGE: Final = numbered("second", 87)
"""Eighty-seven words (83 shingles), none of them the first passage's."""

BOTH_PASSAGES: Final = [*FIRST_PASSAGE, *SECOND_PASSAGE, *numbered("then", 4)]
"""A 150-word body holding all of both: two cards stored as one, or a card and its neighbour."""


@pytest.mark.parametrize("ordering", list(itertools.permutations(range(3))))
def test_two_bodies_sharing_no_text_are_not_joined_through_a_third_that_holds_both(
    ordering: tuple[int, ...],
) -> None:
    """`v1-e31-t11`'s false join, the shape the operator's join sample found on 2026-10-16: two
    bodies of 59 and 87 words that share no text, joined because a 150-word body holds all of both.
    The body holding both passages is a witness for neither, so under any fingerprints all three
    stay apart."""
    shares = [
        len(word_shingles(passage)) / len(word_shingles(BOTH_PASSAGES))
        for passage in (FIRST_PASSAGE, SECOND_PASSAGE)
    ]
    assert min(shares) >= MIN_CUT_SHARE
    keys = [f"{position:064x}" for position in ordering]
    bodies = dict(zip(keys, (FIRST_PASSAGE, SECOND_PASSAGE, BOTH_PASSAGES), strict=True))
    assert keyed_partition(bodies) == sorted([key] for key in keys)


def test_a_body_holding_one_passage_is_that_passages_card() -> None:
    """The same bodies two at a time. Among them the long body holds one passage, and each passage
    joins it, the long one by the same step as the short one."""
    assert partition(FIRST_PASSAGE, BOTH_PASSAGES) == [[0, 1]]
    assert partition(SECOND_PASSAGE, BOTH_PASSAGES) == [[0, 1]]


def test_a_body_holding_two_passages_is_no_witness_even_for_a_passage_nothing_else_claims() -> None:
    """The second passage is also inside a card of its own. The body holding both passages is still
    no witness: the first passage, which nothing else holds, stays out of it, and the second joins
    the card that holds it alone."""
    own_card = [*numbered("before", 30), *SECOND_PASSAGE, *numbered("after", 30)]
    assert partition(FIRST_PASSAGE, SECOND_PASSAGE, BOTH_PASSAGES, own_card) == [[0], [1, 3], [2]]


def test_a_long_cut_joins_the_one_card_it_is_inside() -> None:
    """A hundred words of a 300-word card, a third of its shingles. Before `v1-e31-t20` a long cut
    joined a card only when the banding happened to pair the two; its containers are now found the
    way a short cut's are."""
    card = numbered("word", 300)
    cut = card[100:200]
    assert len(word_shingles(cut)) >= SHORT_BODY_SHINGLES
    assert partition(card, cut) == [[0, 1]]


def test_a_long_cut_joins_a_card_no_more_than_four_times_its_size() -> None:
    """`MIN_CUT_SHARE` holds for a long cut as for a short one: 60 shingles of 240 join, of 241 not."""
    cut = numbered("word", 300)[100:164]
    assert len(word_shingles(cut)) == SHORT_BODY_SHINGLES
    assert partition(numbered("word", 244), cut) == [[0, 1]]
    assert partition(numbered("word", 245), cut) == [[0], [1]]


def test_a_short_cut_and_the_long_copies_it_sits_between_are_one_cluster() -> None:
    """The shape behind the pairs divided since `v1-e31-t08`: a 30-word cut of a 90-word copy of a
    330-word card, which the banding never paired with the copy. `card-fingerprint-v3` put the cut
    with the copy and left the card apart. The copy is over a quarter of the card, so it now joins
    the card, and the cut is with both."""
    whole = numbered("word", 330)
    copy = whole[100:190]
    cut = copy[10:40]
    assert len(word_shingles(copy)) >= MIN_CUT_SHARE * len(word_shingles(whole))
    assert partition(whole, copy) == [[0, 1]]
    assert partition(whole, copy, cut) == [[0, 1, 2]]


def test_two_passages_held_by_two_copies_of_one_card_join_neither() -> None:
    """A 200-word card and a copy of it cut twenty words later, one cluster by Jaccard. The card
    holds a 55-word opening, the copy a 55-word close, and the two share nothing. Each has one
    witness, that cluster, and either alone joins it; both would put two texts sharing nothing in
    one cluster, so neither does. The cluster holds two passages through two of its bodies."""
    article = numbered("word", 220)
    card, later = article[:200], article[20:220]
    opening, closing = article[:55], article[165:220]
    assert jaccard(frozenset(word_shingles(card)), frozenset(word_shingles(later))) >= 0.8
    assert frozenset(word_shingles(opening)).isdisjoint(word_shingles(closing))
    assert partition(card, later, opening) == [[0, 1, 2]]
    assert partition(card, later, closing) == [[0, 1, 2]]
    assert partition(card, later, opening, closing) == [[0, 1], [2], [3]]


def test_copies_a_few_words_apart_never_chain_into_a_cluster_of_texts_that_share_nothing() -> None:
    """Eleven 100-word extents of one article, each ten words on from the last: each pair of
    neighbours is one card by Jaccard (86 of 106 shingles), and the first and last share nothing.
    Copies are joined strongest first, then by fingerprint, and a join that would put two texts
    sharing nothing in one cluster is refused: here the last extent stays apart."""
    article = numbered("word", 200)
    extents = [article[10 * step : 10 * step + 100] for step in range(11)]
    neighbours = jaccard(frozenset(word_shingles(extents[0])), frozenset(word_shingles(extents[1])))
    assert neighbours >= 0.8
    assert frozenset(word_shingles(extents[0])).isdisjoint(word_shingles(extents[10]))
    assert shares_text_throughout(*extents)
    assert partition(*extents) == [list(range(10)), [10]]


def test_a_cut_already_with_a_body_that_holds_it_does_not_take_that_cluster_into_another() -> None:
    """`v1-e31-t11`'s Follow-up 6. A 40-word passage and a copy of it five words longer, one cluster
    by Jaccard: the copy holds the passage. An 80-word card elsewhere holds the passage and not the
    copy. The passage's own cluster is one witness and the card another, neither holds the other,
    and the passage joins neither. Without the copy, it joins the card."""
    passage = numbered("passage", 40)
    longer = [*passage, *numbered("more", 5)]
    card = [*numbered("before", 20), *passage, *numbered("after", 20)]
    assert partition(passage, longer) == [[0, 1]]
    assert partition(passage, card) == [[0, 1]]
    assert partition(passage, longer, card) == [[0, 1], [2]]


def test_a_long_cut_already_with_a_body_that_holds_it_does_not_pull_in_a_second() -> None:
    """The same for a long cut, the case `v1-e31-t11`'s Decision 1 held long cuts back for: joined
    naively, a cut already in a cluster with one body that holds it would pull in the cluster of a
    second."""
    passage = numbered("passage", 100)
    longer = [*passage, *numbered("more", 5)]
    card = [*numbered("before", 40), *passage, *numbered("after", 40)]
    assert partition(passage, longer) == [[0, 1]]
    assert partition(passage, card) == [[0, 1]]
    assert partition(passage, longer, card) == [[0, 1], [2]]


def test_a_cut_whose_copy_does_not_hold_it_still_joins_the_card_that_does() -> None:
    """The boundary of the rule above: a copy that ends in two other words is one card with the
    passage by Jaccard but does not hold it, so the passage's cluster is no witness of its own. It
    joins the card that holds the passage, and the copy, which shares the passage's text with the
    card, comes with it."""
    passage = numbered("passage", 40)
    variant = [*passage[:38], *numbered("ending", 2)]
    card = [*numbered("before", 20), *passage, *numbered("after", 20)]
    assert partition(passage, variant) == [[0, 1]]
    assert partition(passage, variant, card) == [[0, 1, 2]]


def test_a_short_cut_of_a_card_whose_copies_join_one_another_is_compared_once_they_have() -> None:
    """`MAX_CONTAINER_CLUSTERS` is counted against the clusters as they stand, after long cuts have
    joined. Nine copies of a 513-word card, each the opening of the next and about four-fifths of
    it, are ten clusters to start with: none is one card with another by Jaccard. A 20-word cut of
    the opening is inside all ten, more than the limit, so at first it is left alone. Each copy
    joins the next and the last joins the card, and then the cut is inside one cluster."""
    lengths = [64, 81, 102, 128, 161, 203, 256, 323, 407]
    card = numbered("word", 513)
    copies = [card[:length] for length in lengths]
    cut = card[10:30]
    sets = [frozenset(word_shingles(body)) for body in (*copies, card)]
    assert max(jaccard(sets[position], sets[position + 1]) for position in range(9)) < 0.8
    assert len(sets) > MAX_CONTAINER_CLUSTERS
    assert partition(*copies, card) == [list(range(10))]
    assert partition(*copies, card, cut) == [list(range(11))]


def test_a_short_body_nine_tenths_inside_a_body_lacking_one_of_its_ends_stays_out() -> None:
    """`v1-e31-t08`'s rule, kept until the operator's `lacking-an-end` sample says otherwise: a
    40-word passage with one stray word after it is 36 of its 37 shingles inside the card, but its
    last shingle is not, so it is not compared."""
    card = numbered("word", 100)
    stray = [*card[20:60], "stray"]
    stray_set = frozenset(word_shingles(stray))
    assert containment(stray_set, frozenset(word_shingles(card))) >= 0.9
    assert word_shingles(stray)[-1] not in frozenset(word_shingles(card))
    assert partition(card, stray) == [[0], [1]]

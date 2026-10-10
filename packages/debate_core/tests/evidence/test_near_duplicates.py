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

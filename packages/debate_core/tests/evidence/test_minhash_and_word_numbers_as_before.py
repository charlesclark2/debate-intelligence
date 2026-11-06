"""MinHash by column minima, and clusters from the state's word numbers, are what they were (`v1-e31-t10`).

The task takes MinHash's minimum per hash function over one array of digests instead of shingle by
shingle, and gives the clusterer the placement state's word numbers instead of numbering text. Neither
may change a value: the signatures equal the clusterer's as the task found it
(:mod:`.near_duplicates_at_start`, the whole module copied), and so do the clusters, whatever order
the state numbered words in.
Every word here is drawn from invented syllables.
"""

from __future__ import annotations

import random
from array import array

from hypothesis import event, given, settings
from hypothesis import strategies as st

from debate_core.evidence.near_duplicates import (
    BodyWords,
    cluster_near_duplicates,
    matching_words,
    minhash_signature,
)

from .near_duplicates_at_start import cluster_near_duplicates as cluster_near_duplicates_at_start
from .near_duplicates_at_start import minhash_signature as minhash_signature_at_start

SYLLABLES = st.sampled_from(["ka", "lo", "mi", "ner", "pa", "sto", "vu", "zé", "ø", "3"])
WORDS = st.lists(SYLLABLES, min_size=1, max_size=3).map("".join)
SHINGLE_SETS = st.frozensets(st.lists(WORDS, min_size=1, max_size=5).map(" ".join), max_size=60)


@settings(max_examples=300, deadline=None)
@given(shingle_set=SHINGLE_SETS, seed=st.sampled_from(["debate-card-minhash-v1", "another seed"]))
def test_minhash_by_columns_is_the_minimum_shingle_by_shingle(shingle_set: frozenset[str], seed: str) -> None:
    assert minhash_signature(shingle_set, seed) == minhash_signature_at_start(shingle_set, seed)


def test_an_empty_set_has_the_empty_signature_as_before() -> None:
    assert minhash_signature(frozenset()) == minhash_signature_at_start(frozenset()) == (0xFFFFFFFF,) * 128


PASSAGES = tuple(
    tuple(
        random.Random(seed).choice(["ka", "lo", "mi", "ner", "pa", "sto", "vu", "zé"]) + str(n % 7)
        for n in range(90)
    )
    for seed in range(3)
)


def _variant(words: tuple[str, ...], start: int, length: int, changes: int) -> str:
    """A cut of a passage, with up to three words changed: copies, cuts and near copies to cluster."""
    chosen = list(words[start : start + length])
    for number in range(changes):
        chosen[(number + 1) * len(chosen) // 4] = f"changed{number}"
    return " ".join(chosen)


@settings(max_examples=150, deadline=None)
@given(
    bodies=st.dictionaries(
        st.text("0123456789abcdef", min_size=64, max_size=64),
        st.sampled_from(PASSAGES).flatmap(
            lambda words: st.tuples(st.integers(0, 40), st.integers(8, 60), st.integers(0, 3)).map(
                lambda cut: _variant(words, *cut)
            )
        ),
        max_size=10,
    ),
    order=st.randoms(use_true_random=False),
)
def test_clusters_from_numbers_in_any_vocabulary_order_are_those_from_text(
    bodies: dict[str, str], order: object
) -> None:
    """The placement state numbers words in the order its sources were read, which is not the order
    :class:`BodyWords` numbers them in from text: the clusters are the clusterer's as the task found it."""
    fingerprints = list(bodies)
    order.shuffle(fingerprints)  # type: ignore[attr-defined]
    numbered: dict[str, int] = {}
    numbers = {
        fingerprint: array(
            "I", [numbered.setdefault(word, len(numbered)) for word in matching_words(bodies[fingerprint])]
        )
        for fingerprint in fingerprints
    }

    from_numbers = cluster_near_duplicates(None, words=BodyWords.from_numbers(numbers, list(numbered)))

    assert from_numbers == cluster_near_duplicates_at_start(bodies)
    event("some bodies joined" if len(set(from_numbers.values())) < len(from_numbers) else "every body alone")

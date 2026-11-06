"""MinHash by column minima, and word numbers made from numbers, are what they were (`v1-e31-t10`).

The task takes MinHash's minimum per hash function over one array of digests instead of shingle by
shingle, and builds the clusterer's word numbers from the placement state's numbers instead of from
text. Neither may change a value: the signatures equal the clusterer's as the task found it
(:mod:`.near_duplicates_at_start`, the whole module copied), and the word numbers equal those
:class:`BodyWords` makes from the same bodies' text, whatever order the state numbered words in.
Every word here is drawn from invented syllables.
"""

from __future__ import annotations

from array import array

from hypothesis import given, settings
from hypothesis import strategies as st

from debate_core.evidence.near_duplicates import BodyWords, matching_words, minhash_signature

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


@settings(max_examples=200, deadline=None)
@given(
    bodies=st.dictionaries(
        st.text("0123456789abcdef", min_size=64, max_size=64),
        st.lists(WORDS, max_size=30).map(" ".join),
        max_size=12,
    ),
    order=st.randoms(use_true_random=False),
)
def test_word_numbers_from_numbers_are_those_from_text(bodies: dict[str, str], order: object) -> None:
    """The state numbers words in the order its sources were read, which is not the clusterer's."""
    fingerprints = list(bodies)
    order.shuffle(fingerprints)  # type: ignore[attr-defined]
    numbered: dict[str, int] = {}
    numbers = {
        fingerprint: array(
            "I", [numbered.setdefault(word, len(numbered)) for word in matching_words(bodies[fingerprint])]
        )
        for fingerprint in fingerprints
    }

    from_numbers = BodyWords.numbered(numbers, list(numbered))
    from_text = BodyWords(bodies)

    assert from_numbers.vocabulary == from_text.vocabulary
    assert list(from_numbers) == list(from_text)
    assert all(from_numbers[fingerprint] == from_text[fingerprint] for fingerprint in bodies)

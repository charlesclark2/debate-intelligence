"""The near-duplicate index is held compactly, and clusters exactly as it did (`v1-e40-t39`).

Until this task :class:`~debate_core.evidence.near_duplicates.CutIndex` held, for every distinct full
body, its words as a list of strings and its shingles as a set of strings: about 180 bytes a word,
5.43 GB of the whole `hspolicy26` rebuild's 6.25 GB peak (`docs/data/caselist-rebuild-memory.md`).
What each test below holds it to:

* **It grows by a few bytes a word.** A built index, traced with `tracemalloc`, for four times the
  bodies grows by under 16 bytes a word added. The index before this task grew by about 180, and one
  that kept its word lists or its shingle sets after the build would grow by 60 or more.
* **It answers as it did.** Every question the cut step asks of the index, and every cluster id, is
  what the clusterer before this task gives on the same bodies. That clusterer is kept as the oracle
  in `near_duplicates_as_before.py`, copied from the start commit (`b480d79`).
* **A hash collision changes no cluster.** The shingle keys are planted so that every one of them has
  the same hash: every lookup in every set and dict then meets a collision, and only comparing the
  keys themselves tells two shingles apart. The clusters are the same as without the plant.

Every body here is synthetic: invented words, no real card's text.
"""

from __future__ import annotations

import gc
import random
import tracemalloc
from collections.abc import Callable, Mapping
from typing import Final

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import debate_core.evidence.near_duplicates as near_duplicates
from debate_core.evidence.near_duplicates import CutIndex, cluster_near_duplicates, matching_words

from . import near_duplicates_as_before as before

#: Invented words: `w` and a number, so no body here is anyone's evidence.
WORDS: Final = tuple(f"w{number}" for number in range(3000))


def corpus(cards: int, seed: int = 39, words: int = 400) -> dict[str, str]:
    """`cards` invented passages, each with an exact-length copy that has one word changed, a cut of
    its middle third, and a body that runs from its second half into the next passage's first."""
    chosen = random.Random(seed)
    passages = [[chosen.choice(WORDS) for _ in range(words)] for _ in range(cards)]
    texts: list[list[str]] = []
    for number, passage in enumerate(passages):
        changed = list(passage)
        changed[words // 2] = "changed"
        following = passages[(number + 1) % cards]
        texts += [
            passage,
            changed,
            passage[words // 3 : 2 * words // 3],
            passage[words // 2 :] + following[: words // 2],
        ]
    return {f"{number:064x}": " ".join(text) for number, text in enumerate(texts)}


def word_count(bodies: Mapping[str, str]) -> int:
    return sum(len(matching_words(text)) for text in bodies.values())


def retained_by_index(bodies: Mapping[str, str], build: Callable[[Mapping[str, str]], object]) -> int:
    """Bytes the built index holds, as `tracemalloc` traces them, the bodies themselves left out."""
    gc.collect()
    tracemalloc.start()
    try:
        index = build(bodies)
        gc.collect()
        held = tracemalloc.get_traced_memory()[0]
    finally:
        tracemalloc.stop()
    del index
    return held


def test_the_index_grows_by_a_few_bytes_a_word_of_body_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """Eight passages' bodies, then thirty-two: about 32,000 words more. The index keeps the sets it
    made last, up to a bound, so the bound is set well under either corpus's shingles: what is left
    grows with the words. Measured when it was written: the index before this task grew by about
    200 bytes a word, this one by about 8."""
    monkeypatch.setattr(near_duplicates, "SHINGLE_SETS_KEPT", 2_000)
    fewer, more = corpus(8), corpus(32)
    added_words = word_count(more) - word_count(fewer)

    growth = retained_by_index(more, CutIndex) - retained_by_index(fewer, CutIndex)

    assert growth / added_words < 16, (growth, added_words)


def test_the_index_before_this_task_fails_the_same_measure() -> None:
    """The measure above tells the two apart: the oracle's index, which kept word and shingle strings,
    grows by far more than 16 bytes a word."""
    fewer, more = corpus(8), corpus(32)
    added_words = word_count(more) - word_count(fewer)

    growth = retained_by_index(more, before.CutIndex) - retained_by_index(fewer, before.CutIndex)

    assert growth / added_words > 100, (growth, added_words)


# ------------------------------------------------------------------------------------------------
# The same answers as before
# ------------------------------------------------------------------------------------------------


def assert_answers_as_before(bodies: Mapping[str, str]) -> None:
    """Every question the cut step and the diagnosis ask of the index, for every body or pair."""
    index, oracle = CutIndex(bodies), before.CutIndex(bodies)
    assert index.fingerprints == oracle.fingerprints
    for fingerprint in oracle.fingerprints:
        assert index.size(fingerprint) == oracle.size(fingerprint)
        assert list(index.candidates(fingerprint)) == list(oracle.candidates(fingerprint))
        assert list(index.holding_both_ends(fingerprint)) == list(oracle.holding_both_ends(fingerprint))
        assert index.containers(fingerprint) == oracle.containers(fingerprint)
        assert list(index.passages(fingerprint)) == list(oracle.passages(fingerprint))
        assert index.shingle_texts(fingerprint) == oracle.sets[fingerprint]
        assert len(index.words[fingerprint]) == len(oracle.words[fingerprint])
        for other in oracle.fingerprints:
            assert index.holds(fingerprint, other) == oracle.holds(fingerprint, other)
            assert index.overlap(fingerprint, other) == oracle.overlap(fingerprint, other)
    assert index.copies() == oracle.copies()
    assert cluster_near_duplicates(bodies) == before.cluster_near_duplicates(bodies)


def test_the_index_answers_as_before_on_passages_their_copies_cuts_and_joins() -> None:
    assert_answers_as_before(corpus(6, words=120))


SHORT_WORDS: Final = WORDS[:40]


@st.composite
def bodies(draw: st.DrawFn) -> dict[str, str]:
    """A few invented passages, and bodies cut from them, copied with a word changed, dropped or
    added, and run from one into another: what makes copies, cuts and passages for the cut step."""
    passages = draw(
        st.lists(st.lists(st.sampled_from(SHORT_WORDS), min_size=1, max_size=90), min_size=1, max_size=3)
    )
    texts: list[list[str]] = [list(passage) for passage in passages]
    for _ in range(draw(st.integers(0, 8))):
        source = draw(st.sampled_from(passages))
        start = draw(st.integers(0, len(source) - 1))
        end = draw(st.integers(start + 1, len(source)))
        piece = list(source[start:end])
        change = draw(st.sampled_from(("none", "changed", "dropped", "added", "joined")))
        at = draw(st.integers(0, len(piece) - 1))
        if change == "changed":
            piece[at] = draw(st.sampled_from(SHORT_WORDS))
        elif change == "dropped" and len(piece) > 1:
            del piece[at]
        elif change == "added":
            piece.insert(at, draw(st.sampled_from(SHORT_WORDS)))
        elif change == "joined":
            piece += draw(st.sampled_from(passages))
        texts.append(piece)
    # A body with no words at all, now and then: it has no shingles and overlaps nothing.
    if draw(st.booleans()):
        texts.append([])
    return {f"{number:064x}": " ".join(text) + ("." if not text else "") for number, text in enumerate(texts)}


@settings(max_examples=300, deadline=None)
@given(bodies())
def test_the_index_answers_as_before_on_generated_bodies(generated: dict[str, str]) -> None:
    assert_answers_as_before(generated)


# ------------------------------------------------------------------------------------------------
# A planted collision
# ------------------------------------------------------------------------------------------------


class CollidingKey(bytes):
    """A shingle key whose hash is every other key's: only comparing the bytes tells two apart."""

    def __hash__(self) -> int:
        return 39


def colliding(ordered: Callable[[bytes], list[bytes]]) -> Callable[[bytes], list[bytes]]:
    def planted(numbers: bytes) -> list[bytes]:
        return [CollidingKey(key) for key in ordered(numbers)]

    return planted


def test_the_planted_keys_collide(monkeypatch: pytest.MonkeyPatch) -> None:
    """The plant takes: every shingle the index holds is a key with the one hash."""
    monkeypatch.setattr(near_duplicates, "ordered_shingles", colliding(near_duplicates.ordered_shingles))
    index = CutIndex(corpus(2, words=60))

    keys = {key for fingerprint in index.fingerprints for key in index.sets[fingerprint]}

    assert len(keys) > 100
    assert all(isinstance(key, CollidingKey) for key in keys)
    assert {hash(key) for key in keys} == {39}


def test_shingles_whose_hashes_all_collide_cluster_as_before(monkeypatch: pytest.MonkeyPatch) -> None:
    generated = corpus(4, words=80)
    expected = before.cluster_near_duplicates(generated)
    assert len(set(expected.values())) > 1  # several clusters, so a merged one would show

    monkeypatch.setattr(near_duplicates, "ordered_shingles", colliding(near_duplicates.ordered_shingles))

    assert cluster_near_duplicates(generated) == expected


@settings(max_examples=60, deadline=None)
@given(bodies())
def test_generated_bodies_whose_shingle_hashes_all_collide_cluster_as_before(
    generated: dict[str, str],
) -> None:
    expected = before.cluster_near_duplicates(generated)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(near_duplicates, "ordered_shingles", colliding(near_duplicates.ordered_shingles))
        assert cluster_near_duplicates(generated) == expected

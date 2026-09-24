"""The sampling plan: contiguous, deterministic, weighted toward the rare units, and fixed in size.

Everything here is arithmetic over invented unit sequences, so it runs in the PR `ci` check where
the corpus never is.
"""

from __future__ import annotations

from datetime import date

import pytest
from tests.evals.parser.labels_schema import (
    MINIMUM_BLOCK_PARAGRAPHS,
    Category,
    DebateFormat,
    Manifest,
    ManifestEntry,
    TemplateFamily,
)
from tests.evals.parser.sampling import build_sampling_plan, choose_blocks, plan_identifier

from debate_core.domain.style_profile import StructuralUnit

U = StructuralUnit
DIGEST = "3f" * 32
OTHER_DIGEST = "c4" * 32


def _units(count: int, rare_at: range | None = None) -> list[StructuralUnit]:
    units = [U.EVIDENCE] * count
    for index in rare_at or ():
        units[index] = U.UNDERTAG
    return units


def _rows(blocks: tuple[tuple[int, int], ...]) -> int:
    return sum(last - first + 1 for first, last in blocks)


# --------------------------------------------------------------------------------------------
# Shape
# --------------------------------------------------------------------------------------------


def test_a_full_file_is_one_block_over_everything() -> None:
    assert choose_blocks(DIGEST, _units(400), full=True) == ((0, 399),)


def test_a_file_no_longer_than_one_block_is_labeled_whole() -> None:
    """A quarter of 18 paragraphs is 5 rows, which is less than a block; take the file instead."""
    assert choose_blocks(DIGEST, _units(18)) == ((0, 17),)


def test_about_a_quarter_of_a_longer_file() -> None:
    blocks = choose_blocks(DIGEST, _units(400))
    assert _rows(blocks) == 100  # 400 * 0.25, in blocks of 20
    assert 0.2 <= _rows(blocks) / 400 <= 0.3


def test_every_block_is_at_least_the_minimum_and_they_are_disjoint_and_ordered() -> None:
    blocks = choose_blocks(DIGEST, _units(1000))
    assert all(last - first + 1 >= MINIMUM_BLOCK_PARAGRAPHS for first, last in blocks)
    previous = -1
    for first, last in blocks:
        assert first > previous
        previous = last
    assert blocks[-1][1] < 1000


def test_blocks_are_contiguous_runs_not_scattered_rows() -> None:
    """Card-boundary exact match needs unbroken runs; scattered rows would make it unmeasurable."""
    for first, last in choose_blocks(DIGEST, _units(500)):
        assert last > first


def test_the_same_digest_and_units_always_give_the_same_blocks() -> None:
    units = _units(300, range(0, 40))
    assert choose_blocks(DIGEST, units) == choose_blocks(DIGEST, units)


def test_a_different_file_gets_different_blocks() -> None:
    units = _units(300)
    assert choose_blocks(DIGEST, units) != choose_blocks(OTHER_DIGEST, units)


# --------------------------------------------------------------------------------------------
# Weighting: which blocks, never how many
# --------------------------------------------------------------------------------------------


def test_weighting_does_not_change_how_many_rows_are_labeled() -> None:
    plain = choose_blocks(DIGEST, _units(400))
    weighted = choose_blocks(DIGEST, _units(400, range(0, 400, 3)))
    assert _rows(plain) == _rows(weighted)
    assert len(plain) == len(weighted)


def test_a_block_full_of_rare_units_is_picked_far_more_often() -> None:
    """One file proves nothing — a block can be drawn on its own luck. Over a hundred files, the
    block holding every rare unit should be picked much more often than an even draw would."""
    digests = [f"{index:064x}" for index in range(100)]
    plain = sum(1 for digest in digests if (380, 399) in choose_blocks(digest, _units(400)))
    weighted = sum(
        1 for digest in digests if (380, 399) in choose_blocks(digest, _units(400, range(380, 400)))
    )
    # An even draw takes five of twenty windows, so about 25 of 100. Weighted, that block's key is
    # u**(1/21) against u for the rest, which loses only when several ordinary windows draw very
    # high: well over half, not all. (Measured: 20 plain, 75 weighted.)
    assert plain < 40
    assert weighted > 60
    assert weighted > plain * 2


def test_weighting_does_not_take_only_the_rare_blocks() -> None:
    """Always taking the densest blocks would measure the corpus's tail rather than the corpus, so
    a weighted draw still reaches ordinary text."""
    units = _units(2000, range(0, 100))
    blocks = choose_blocks(DIGEST, units)
    assert any(first >= 100 for first, _ in blocks)


def test_touching_blocks_are_joined_into_one_run() -> None:
    """Two windows picked side by side are one unbroken run; every edge is a place a card is lost."""
    for digest in (DIGEST, OTHER_DIGEST, "ab" * 32, "77" * 32):
        blocks = choose_blocks(digest, _units(600))
        assert all(blocks[i][1] + 1 < blocks[i + 1][0] for i in range(len(blocks) - 1))


# --------------------------------------------------------------------------------------------
# The whole plan
# --------------------------------------------------------------------------------------------


def _entry(digest: str, *, pr_subset: bool = False) -> ManifestEntry:
    return ManifestEntry(
        digest=digest,
        category=Category.CASELIST,
        season="2026-27",
        debate_format=DebateFormat.LD,
        template_family=TemplateFamily.VERBATIM,
        pr_subset=pr_subset,
    )


def _plan(**kwargs):  # type: ignore[no-untyped-def]
    manifest = Manifest(entries=(_entry(DIGEST, pr_subset=True), _entry(OTHER_DIGEST)))
    units = {DIGEST: _units(50), OTHER_DIGEST: _units(400)}
    return build_sampling_plan(manifest, units, parser_version="p1", generated_on=date(2026, 9, 23), **kwargs)


def test_the_pr_subset_is_labeled_in_full_and_the_rest_sampled() -> None:
    plan = _plan()
    assert plan.of(DIGEST).full and plan.of(DIGEST).labeled_rows == 50
    assert not plan.of(OTHER_DIGEST).full
    assert plan.of(OTHER_DIGEST).labeled_rows == 100
    assert plan.labeled_rows == 150
    assert plan.total_rows == 450


def test_the_plan_id_changes_with_the_blocks_and_not_with_the_date() -> None:
    first = _plan()
    assert first.plan_id == _plan().plan_id
    assert first.plan_id != _plan(target_rate=0.5).plan_id
    assert plan_identifier(first.files, target_rate=0.25, minimum_block=20) == first.plan_id


def test_a_file_with_no_prelabels_is_an_error_not_a_silently_skipped_row() -> None:
    manifest = Manifest(entries=(_entry(DIGEST), _entry(OTHER_DIGEST)))
    with pytest.raises(KeyError, match="no pre-labeled units"):
        build_sampling_plan(
            manifest, {DIGEST: _units(50)}, parser_version="p1", generated_on=date(2026, 9, 23)
        )

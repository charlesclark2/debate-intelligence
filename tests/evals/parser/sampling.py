"""Choosing which paragraphs get labeled, once, before anybody labels anything.

Labeling all thirty files in full is about 5,800 rows of judgment work. The spec samples instead:
the six-file PR subset in full, because it gates every pull request and cannot be partial, and
about a quarter of every other file.

**Contiguous blocks, not scattered rows.** Per-unit precision and recall are sound on any sample,
but card-boundary exact match needs unbroken runs: a card that straddles a sampling gap cannot be
scored at all. Blocks are therefore at least
:data:`~tests.evals.parser.labels_schema.MINIMUM_BLOCK_PARAGRAPHS` paragraphs long.

**Deterministic.** A file's blocks come from its keyed digest, so re-running the planner picks the
same blocks, and the choice has nothing to do with who wrote a file or what is in it beyond the
weighting below. The digest is keyed, so the plan leaks nothing about which file is which.

**Weighted toward the rare units.** `POCKET`, `UNDERTAG` and `ANALYTIC` are both the sparsest units
and the ones the parser is weakest on; an even sample leaves their F1 too noisy to gate on. A
window holding more of them is likelier to be picked — but the number of blocks a file gets is
fixed before any weight is looked at, so **weighting changes which blocks are picked, not how
many**, and the sampling rate does not move.

The method is Efraimidis–Spirakis weighted sampling without replacement: each window gets a
uniform `u` derived from the file digest, its key is `u ** (1 / weight)`, and the top `k` keys win.
A window with twice the weight is twice as likely to be in the sample, and every window keeps a
chance of being picked, which an outright "take the windows with the most rare units" rule would
not — that would sample the same unusual shapes every time and measure the corpus's tail rather
than the corpus.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from datetime import date

from tests.evals.parser.labels_schema import (
    MINIMUM_BLOCK_PARAGRAPHS,
    RARE_UNITS,
    TARGET_SAMPLING_RATE,
    Block,
    FileSamplingPlan,
    Manifest,
    SamplingPlan,
)

from debate_core.domain.style_profile import StructuralUnit

__all__ = ["MAXIMUM_BLOCKS_PER_FILE", "build_sampling_plan", "choose_blocks", "plan_identifier"]

#: More blocks than this in one file would fragment it into many short runs, and every extra block
#: adds two edges where a card can fall outside the sample.
MAXIMUM_BLOCKS_PER_FILE = 5


def _uniform(digest: str, window: int) -> float:
    """A stable uniform in (0, 1] for one window of one file."""
    raw = hashlib.sha256(f"{digest}:window:{window}".encode()).digest()
    return (int.from_bytes(raw[:8], "big") + 1) / (2**64 + 1)


def _windows(paragraphs: int, block: int) -> list[Block]:
    """Consecutive windows of `block` paragraphs; the last one absorbs the remainder."""
    count = max(1, paragraphs // block)
    windows: list[Block] = []
    for index in range(count):
        first = index * block
        last = (paragraphs - 1) if index == count - 1 else (first + block - 1)
        windows.append((first, last))
    return windows


def choose_blocks(
    digest: str,
    units: Sequence[StructuralUnit],
    *,
    full: bool = False,
    target_rate: float = TARGET_SAMPLING_RATE,
    minimum_block: int = MINIMUM_BLOCK_PARAGRAPHS,
    maximum_blocks: int = MAXIMUM_BLOCKS_PER_FILE,
) -> tuple[Block, ...]:
    """The labeled blocks for one file, from its keyed digest and its pre-labeled units.

    `units` is the parser's unit for every paragraph, in body order — used only to weight windows.
    A file at or under the minimum block length is labeled whole: there is no way to take a
    shorter block, and a partial block would be a card cut in half.
    """
    paragraphs = len(units)
    if paragraphs == 0:
        return ()
    if full or paragraphs <= minimum_block:
        return ((0, paragraphs - 1),)

    target_rows = max(minimum_block, round(paragraphs * target_rate))
    block = max(minimum_block, -(-target_rows // maximum_blocks))
    windows = _windows(paragraphs, block)
    wanted = min(len(windows), max(1, round(target_rows / block)))

    ranked = []
    for index, (first, last) in enumerate(windows):
        rare = sum(1 for unit in units[first : last + 1] if unit in RARE_UNITS)
        key = _uniform(digest, index) ** (1.0 / (1 + rare))
        ranked.append((key, index))
    chosen = sorted(index for _, index in sorted(ranked, reverse=True)[:wanted])
    return _merge_adjacent(windows[index] for index in chosen)


def _merge_adjacent(blocks: Iterable[Block]) -> tuple[Block, ...]:
    """Join blocks that touch. Two windows picked side by side are one unbroken run, and every
    block edge is a place a card can fall outside the sample."""
    merged: list[Block] = []
    for first, last in blocks:
        if merged and first == merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], last)
        else:
            merged.append((first, last))
    return tuple(merged)


def plan_identifier(files: Sequence[FileSamplingPlan], *, target_rate: float, minimum_block: int) -> str:
    """A short digest of the plan's own content. Not of any file: every input here is already keyed."""
    canonical = json.dumps(
        {
            "target_rate": target_rate,
            "minimum_block": minimum_block,
            "files": [
                [plan.digest, [list(block) for block in plan.blocks]]
                for plan in sorted(files, key=lambda p: p.digest)
            ],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def build_sampling_plan(
    manifest: Manifest,
    units_by_file: Mapping[str, Sequence[StructuralUnit]],
    *,
    parser_version: str,
    generated_on: date,
    target_rate: float = TARGET_SAMPLING_RATE,
    minimum_block: int = MINIMUM_BLOCK_PARAGRAPHS,
) -> SamplingPlan:
    """The plan for every file in the manifest. Missing pre-labels are an error, not a skipped file."""
    missing = [entry.digest for entry in manifest.entries if entry.digest not in units_by_file]
    if missing:
        raise KeyError(f"no pre-labeled units for {len(missing)} file(s), starting {missing[0][:12]}…")
    files = []
    for entry in manifest.entries:
        units = units_by_file[entry.digest]
        blocks = choose_blocks(
            entry.digest,
            units,
            full=entry.pr_subset,
            target_rate=target_rate,
            minimum_block=minimum_block,
        )
        files.append(
            FileSamplingPlan(
                digest=entry.digest,
                paragraphs=len(units),
                blocks=blocks,
                full=bool(units) and blocks == ((0, len(units) - 1),),
            )
        )
    ordered = tuple(sorted(files, key=lambda plan: plan.digest))
    return SamplingPlan(
        plan_id=plan_identifier(ordered, target_rate=target_rate, minimum_block=minimum_block),
        generated_on=generated_on.isoformat(),
        parser_version=parser_version,
        target_rate=target_rate,
        minimum_block=minimum_block,
        files=ordered,
    )

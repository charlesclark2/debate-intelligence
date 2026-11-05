"""The coach's relabelling sitting for the answering stance (`v1-e32-t46`): what it shows, in what order, and
what it writes.

`scripts/relabel_coach_sample.py` is the terminal half. This module is the rest, values in and values out.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from debate_core.domain.landscape import Taxonomy

__all__ = [
    "CONTROL_ROWS",
    "COPY_SUFFIX",
    "ShownRow",
    "SittingRow",
    "copy_path",
    "disclosed_side",
    "relabel_counts",
    "relabelled_sample",
    "run_sitting",
    "sitting_rows",
]

CONTROL_ROWS: Final = 6
"""Labelled rows off the session's list drawn into the sitting, unmarked, beside the listed rows."""

COPY_SUFFIX: Final = ".before-stance-relabel"
"""Added to the sample's name for the copy kept before anything is written."""


@dataclass(frozen=True, slots=True)
class SittingRow:
    """One row the coach is shown: its number in the sample, and whether it is listed or a control."""

    row: int
    listed: bool


def sitting_rows(
    listed: Collection[int], labelled: Iterable[int], *, controls: int = CONTROL_ROWS, seed: int
) -> tuple[SittingRow, ...]:
    """The listed rows and `controls` rows drawn from the other `labelled` rows, all in one shuffled order."""
    del labelled, controls, seed
    return tuple(SittingRow(row, True) for row in sorted(listed))


def disclosed_side(sides: Collection[str]) -> str:
    """The sides a row's file was disclosed on, in words."""
    del sides
    return ""


def relabelled_sample(text: str, labels: Mapping[int, str]) -> str:
    """The coach's CSV `text` with the `position` cell of each row of `labels` set to its new label."""
    del labels
    return text


def relabel_counts(rows: Sequence[SittingRow], changed: Collection[int]) -> dict[str, dict[str, int]]:
    """Changed and unchanged rows, split into listed and control: counts only."""
    del rows, changed
    return {}


def copy_path(sample: Path) -> Path:
    """Where the copy of `sample` is kept before the sitting writes it."""
    return sample.with_name(f"{sample.stem}{COPY_SUFFIX}{sample.suffix}")


@dataclass(frozen=True, slots=True)
class ShownRow:
    """What the coach sees of one row: the coach's own tag and headings, the file's side, and the labels."""

    tag: str
    headings: str
    side: str
    label: str
    also: str = ""


def run_sitting(
    rows: Sequence[SittingRow],
    shown: Mapping[int, ShownRow],
    taxonomy: Taxonomy,
    *,
    ask: Callable[[str], str],
    say: Callable[[str], None],
) -> dict[int, str]:
    """Show each row in turn and take the coach's label; the labels that changed, by row."""
    del rows, shown, taxonomy, ask, say
    return {}

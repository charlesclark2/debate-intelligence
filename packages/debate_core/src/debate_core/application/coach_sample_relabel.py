"""The coach's relabelling sitting for the answering stance (`v1-e32-t46`): what it shows, in what order, and
what it writes.

The PM's ruling (2026-11-05): the session's listed rows, the cards that may answer a position, are mixed with
:data:`CONTROL_ROWS` rows drawn at random from the other labelled rows by a stated seed, all shown in one
random order and unmarked (:func:`sitting_rows`). Each card shows the coach's own tag and headings from the
coach's CSV, the side its file was disclosed on, and the coach's label, and nothing about the model's
answers, the recordings or the score (:func:`run_sitting`). The coach answers with a label, `at:<id>` for a
card that answers the position, and Enter keeps it; a label the evaluation would refuse is asked again,
never echoed. Only changed labels are written (:func:`relabelled_sample`), after the file they replace is kept as a
dated copy (:mod:`debate_core.application.coach_sample_labels_file`, `v1-e32-t58`), and the end counts changed and unchanged rows, listed and control
(:func:`relabel_counts`).

`scripts/relabel_coach_sample.py` is the terminal half. This module is the rest, values in and values out;
nothing here logs, and no row's text leaves the terminal it is shown in.
"""

from __future__ import annotations

import csv
import io
import random
from collections.abc import Callable, Collection, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from debate_core.application.landscape_model_evaluation import (
    UNSURE_LABEL,
    EvaluationRefused,
    coach_label,
    row_labels,
)
from debate_core.domain.landscape import Taxonomy

__all__ = [
    "CONTROL_ROWS",
    "ShownRow",
    "SittingRow",
    "disclosed_side",
    "relabel_counts",
    "relabelled_sample",
    "run_sitting",
    "shown_rows",
    "sitting_rows",
]

CONTROL_ROWS: Final = 6
"""Labelled rows off the session's list drawn into the sitting, unmarked, beside the listed rows."""

@dataclass(frozen=True, slots=True)
class SittingRow:
    """One row the coach is shown: its number in the sample, and whether it is listed or a control."""

    row: int
    listed: bool


def sitting_rows(
    listed: Collection[int], labelled: Iterable[int], *, controls: int = CONTROL_ROWS, seed: int
) -> tuple[SittingRow, ...]:
    """The listed rows and `controls` rows drawn from the other `labelled` rows, all in one shuffled order.

    `random.Random(seed)` draws the controls from the labelled rows off the list, in row order, then shuffles
    the whole sitting, so one seed gives one sitting. Raises `ValueError` for a listed row the coach did not
    label, or too few rows off the list to draw the controls from.
    """
    chosen = set(listed)
    scored = set(labelled)
    unlabelled = sorted(chosen - scored)
    if unlabelled:
        raise ValueError(f"row {unlabelled[0]} is listed but the coach did not label it")
    pool = sorted(scored - chosen)
    if len(pool) < controls:
        raise ValueError(f"{len(pool)} labelled row(s) off the list cannot give {controls} control rows")
    draw = random.Random(seed)
    rows = [SittingRow(row, True) for row in sorted(chosen)]
    rows += [SittingRow(row, False) for row in sorted(draw.sample(pool, controls))]
    draw.shuffle(rows)
    return tuple(rows)


_READABLE: Final = {"AFF": "aff", "PRO": "aff", "NEG": "neg", "CON": "neg"}


def disclosed_side(sides: Collection[str]) -> str:
    """The sides a row's file was disclosed on (:class:`~debate_core.domain.caselist.Side` values), in words:
    PF's pro and con as aff and neg, and `UNKNOWN` as no readable side."""
    readable = {_READABLE[side] for side in sides if side in _READABLE}
    if readable == {"aff"}:
        return "affirmative"
    if readable == {"neg"}:
        return "negative"
    return "both sides" if readable else "no readable side"


def relabelled_sample(text: str, labels: Mapping[int, str]) -> str:
    """The coach's CSV `text` with the `position` cell of each row of `labels` set to its new label.

    Every other row keeps its bytes, quoting and line ending included, and a changed row keeps its other
    cells' values and its line ending. With no change, `text` comes back as it was. Raises `ValueError` for
    a row the sample does not have.
    """
    if not labels:
        return text
    consumed: list[str] = []

    def lines() -> Iterator[str]:
        for line in text.splitlines(keepends=True):
            consumed.append(line)
            yield line

    written: list[str] = []
    found: set[int] = set()
    row_column = position_column = -1
    for number, record in enumerate(csv.reader(lines())):
        raw = "".join(consumed)
        consumed.clear()
        if number == 0:
            row_column, position_column = record.index("sample_row"), record.index("position")
        elif record and int(record[row_column]) in labels:
            row = int(record[row_column])
            record[position_column] = labels[row]
            found.add(row)
            ending = raw[len(raw.rstrip("\r\n")) :]
            out = io.StringIO(newline="")
            csv.writer(out, lineterminator=ending or "\n").writerow(record)
            raw = out.getvalue()
        written.append(raw)
    missing = sorted(set(labels) - found)
    if missing:
        raise ValueError(f"row {missing[0]} is not in the coach's sample")
    return "".join(written)


def relabel_counts(rows: Sequence[SittingRow], changed: Collection[int]) -> dict[str, dict[str, int]]:
    """Changed and unchanged rows, split into listed and control: counts only."""
    counts = {"listed": {"changed": 0, "unchanged": 0}, "control": {"changed": 0, "unchanged": 0}}
    for one in rows:
        counts["listed" if one.listed else "control"]["changed" if one.row in changed else "unchanged"] += 1
    return counts


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
    """Show each row in turn and take the coach's label; the labels that changed, by row, as the sample
    writes them (`at:<id>`, an id, `none` or `unsure`).

    `ask` takes the prompt and returns what the coach typed; `say` shows a line. Enter keeps the label. A
    label :func:`~debate_core.application.landscape_model_evaluation.row_labels` refuses, with the row's
    second label, is asked again, the rule said and the typed text never repeated. The typed text is read in
    lower case, as every position id is written.
    """
    changes: dict[int, str] = {}
    for number, one in enumerate(rows, start=1):
        row = shown[one.row]
        say("")
        say(f"Card {number} of {len(rows)}")
        say(f"Tag: {row.tag}")
        say(f"Headings: {row.headings}")
        say(f"Disclosed on: {row.side}")
        say(f"Your label: {row.label}")
        if row.also.strip():
            say(f"Your second label: {row.also}")
        while True:
            typed = ask("New label (Enter keeps yours): ").strip().casefold()
            if not typed:
                break
            try:
                read = row_labels(one.row, typed, row.also, taxonomy)
            except EvaluationRefused as refused:
                said = (
                    str(refused)
                    .replace(f"row {one.row}'s ", "this card's ")
                    .replace(f"row {one.row} ", "this card ")
                )
                say(f"Not taken: {said}. Type another label, or press Enter to keep yours.")
                continue
            written = read[0].written if read is not None else UNSURE_LABEL
            if written != _as_written(row.label, taxonomy):
                changes[one.row] = written
            break
    return changes


def _as_written(label: str, taxonomy: Taxonomy) -> str:
    """`label` as :func:`run_sitting` writes a label, or as it stands when it does not read."""
    try:
        read = coach_label(label, {one.id for one in taxonomy.active_positions})
    except ValueError:
        return label.strip()
    return read.written if read is not None else UNSURE_LABEL


def shown_rows(text: str, sides: Mapping[int, Collection[str]]) -> dict[int, ShownRow]:
    """What the sitting shows of each row of the coach's CSV `text`, with its file's `sides`: the coach's own
    `tag`, `headings`, `position` and `also` cells as written, and the sides in words
    (:func:`disclosed_side`). A row with no sides given shows no readable side."""
    found: dict[int, ShownRow] = {}
    for line in csv.DictReader(io.StringIO(text, newline="")):
        row = int(line["sample_row"])
        found[row] = ShownRow(
            tag=(line.get("tag") or "").strip(),
            headings=(line.get("headings") or "").strip(),
            side=disclosed_side(sides.get(row, ())),
            label=(line.get("position") or "").strip(),
            also=(line.get("also") or "").strip(),
        )
    return found

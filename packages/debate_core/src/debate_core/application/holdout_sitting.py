"""The coach's sitting for the held-out sample (`v1-e32-t50`): what it shows, what it takes, what it writes.

The PM's ruling of 2026-11-14: 120 cards in two sittings of 60 (:func:`sitting_range`), each card shown as
the first sample's sitting shows one (`v1-e32-t46`): the coach's own tag and headings from the CSV and the
side its file was disclosed on, and nothing of a model, a score, a stratum or a mark. The coach types a label
with its stance, `at:<id>` for a card that answers the position, and may add a second label after a comma
(:func:`run_holdout_sitting`). A label the evaluation would refuse is asked again, never echoed.

At the end of the second sitting, as a part of its own after the holdout's cards, the coach sees rows 16, 33
and 57 of the first sample (:data:`SIDE_RULE_ROWS`, `v1-e32-t49`'s ruling 3). Each was labelled as reading its
position in a file disclosed only on the side opposite it. Per row the coach chooses
(:func:`run_side_rows`): `at:<id>`, which replaces the label; `also <label>`, which adds a second label; or
`side`, "the side rule is wrong here", which writes nothing and is named on the sitting's last line
(:func:`side_rule_line`), for the PM to file a follow-up on t46's other-side rule.

Values in and values out; `scripts/label_holdout_sample.py` is the terminal half and writes through the guard
(:mod:`debate_core.application.coach_sample_labels_file`). Nothing here logs, and no row's text leaves the
terminal it is shown in.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from debate_core.application.coach_sample_relabel import ShownRow
from debate_core.application.landscape_model_evaluation import (
    NO_POSITION_LABEL,
    SECOND_LABEL_COLUMN,
    UNSURE_LABEL,
    EvaluationRefused,
    coach_label,
    row_labels,
)
from debate_core.arguments.landscape.evaluation_breakdown import ANSWERS_PREFIX
from debate_core.domain.landscape import Taxonomy

__all__ = [
    "ALSO_CHOICE",
    "SIDE_CHOICE",
    "SIDE_RULE_ROWS",
    "SideRowAnswers",
    "holdout_counts",
    "run_holdout_sitting",
    "run_side_rows",
    "side_rule_line",
    "sitting_range",
]

SIDE_RULE_ROWS: Final = (16, 33, 57)
"""The first sample's rows labelled as read in a file disclosed only on the side opposite their position."""

SIDE_CHOICE: Final = "side"
"""The coach's answer "the side rule is wrong here": nothing is written."""

ALSO_CHOICE: Final = "also"
"""The word before a second label the coach accepts."""

_POSITION: Final = "position"


def sitting_range(text: str) -> tuple[int, ...]:
    """The sample rows a sitting covers, from `1-60`, `61-120` or `3,5-7`: ascending, each once.

    Raises `ValueError` for an empty range, a range that runs backwards, or a row below 1.
    """
    rows: set[int] = set()
    for part in (one.strip() for one in text.split(",")):
        if not part:
            continue
        low, _, high = part.partition("-")
        first, last = int(low), int(high or low)
        if first < 1 or last < first:
            raise ValueError(f"{part} is not a range of sample rows")
        rows.update(range(first, last + 1))
    if not rows:
        raise ValueError("the sitting covers no row")
    return tuple(sorted(rows))


def _say_card(say: Callable[[str], None], number: int, total: int, row: ShownRow) -> None:
    say("")
    say(f"Card {number} of {total}")
    say(f"Tag: {row.tag}")
    say(f"Headings: {row.headings}")
    say(f"Disclosed on: {row.side}")
    if row.label:
        say(f"Your label: {row.label}")
    if row.also:
        say(f"Your second label: {row.also}")


def _refusal(refused: EvaluationRefused, row: int) -> str:
    return str(refused).replace(f"row {row}'s ", "this card's ").replace(f"row {row} ", "this card ")


def _written(label: str, active: Collection[str]) -> str:
    """`label` as a sitting writes it, or as it stands when it does not read."""
    try:
        read = coach_label(label, active)
    except ValueError:
        return label.strip()
    if read is None:
        return UNSURE_LABEL if label.strip() else ""
    return read.written


def run_holdout_sitting(
    rows: Sequence[int],
    shown: Mapping[int, ShownRow],
    taxonomy: Taxonomy,
    *,
    ask: Callable[[str], str],
    say: Callable[[str], None],
) -> dict[int, dict[str, str]]:
    """Show each row in turn and take the coach's label and second label; the cells that changed, by row.

    The coach types a position id, `at:<id>`, `none` or `unsure`, and may follow it with a comma and a
    second label; Enter leaves the row as it is. Each changed row gives its `position` and `also` cells as
    the sample writes them. A label :func:`~debate_core.application.landscape_model_evaluation.row_labels`
    refuses, or a second label on a row labelled `unsure`, is asked again, the rule said and the typed text
    never repeated. The typed text is read in lower case, as every position id is written.
    """
    active = {one.id for one in taxonomy.active_positions}
    changes: dict[int, dict[str, str]] = {}
    for number, row in enumerate(rows, start=1):
        one = shown[row]
        _say_card(say, number, len(rows), one)
        while True:
            typed = ask("Label (an id, at:<id>, none or unsure; a second after a comma; Enter skips): ")
            typed = typed.strip().casefold()
            if not typed:
                break
            first, _, second = (part.strip() for part in typed.partition(","))
            try:
                read = row_labels(row, first, second, taxonomy)
            except EvaluationRefused as refused:
                say(f"Not taken: {_refusal(refused, row)}. Type another label, or press Enter to skip it.")
                continue
            if read is None and (second or not first):
                say("Not taken: an unsure card takes no second label. Type another label, or press Enter.")
                continue
            if read is None:
                cells = {_POSITION: UNSURE_LABEL, SECOND_LABEL_COLUMN: ""}
            else:
                label, also = read
                cells = {
                    _POSITION: label.written,
                    SECOND_LABEL_COLUMN: also.written if also is not None else "",
                }
            if (cells[_POSITION], cells[SECOND_LABEL_COLUMN]) != (
                _written(one.label, active),
                _written(one.also, active),
            ):
                changes[row] = cells
            break
    return changes


@dataclass(frozen=True, slots=True)
class SideRowAnswers:
    """The coach's choices on the first sample's side-rule rows: the cells to write, and the rows answered
    `side`, which write nothing."""

    cells: dict[int, dict[str, str]]
    side_rule: tuple[int, ...]


def run_side_rows(
    rows: Sequence[int],
    shown: Mapping[int, ShownRow],
    taxonomy: Taxonomy,
    *,
    ask: Callable[[str], str],
    say: Callable[[str], None],
) -> SideRowAnswers:
    """Show each of the first sample's `rows` and take one of three choices for it.

    `at:<id>` replaces the row's label (its second label is kept, and must still read beside it);
    `also <label>` sets its second label, which must read beside its label; `side` writes nothing. Anything
    else is asked again, and so is a choice the evaluation would refuse, the rule said and the typed text
    never repeated.
    """
    say("")
    say(
        f"Now {len(rows)} cards of the first sample. Each was labelled as reading its position in a file "
        "disclosed only on the side opposite it."
    )
    say(
        f"For each, type at:<id> if it answers the position, {ALSO_CHOICE} <label> for a second label you "
        f"accept, or {SIDE_CHOICE} if your label stands and the side rule is wrong here."
    )
    cells: dict[int, dict[str, str]] = {}
    side_rule: list[int] = []
    for number, row in enumerate(rows, start=1):
        one = shown[row]
        _say_card(say, number, len(rows), one)
        while True:
            typed = ask(f"at:<id>, {ALSO_CHOICE} <label>, or {SIDE_CHOICE}: ").strip().casefold()
            if typed == SIDE_CHOICE:
                side_rule.append(row)
                break
            if typed.startswith(ANSWERS_PREFIX):
                found = _answers(row, typed, one, taxonomy, say)
                if found is not None:
                    cells[row] = {_POSITION: found}
                    break
                continue
            word, _, second = typed.partition(" ")
            if word == ALSO_CHOICE and second.strip():
                found = _second(row, second.strip(), one, taxonomy, say)
                if found is not None:
                    cells[row] = {SECOND_LABEL_COLUMN: found}
                    break
                continue
            say(f"Not taken: type at:<id>, {ALSO_CHOICE} <label>, or {SIDE_CHOICE}.")
    return SideRowAnswers(cells=cells, side_rule=tuple(side_rule))


def _answers(
    row: int, typed: str, one: ShownRow, taxonomy: Taxonomy, say: Callable[[str], None]
) -> str | None:
    try:
        read = row_labels(row, typed, one.also, taxonomy)
    except EvaluationRefused as refused:
        say(f"Not taken: {_refusal(refused, row)}. Type another choice.")
        return None
    return read[0].written if read is not None else None


def _second(
    row: int, typed: str, one: ShownRow, taxonomy: Taxonomy, say: Callable[[str], None]
) -> str | None:
    if typed.casefold() == NO_POSITION_LABEL:
        say("Not taken: a second label names a position. Type another choice.")
        return None
    try:
        read = row_labels(row, one.label, typed, taxonomy)
    except EvaluationRefused as refused:
        say(f"Not taken: {_refusal(refused, row)}. Type another choice.")
        return None
    if read is None or read[1] is None:
        say(f"Not taken: this card has no label to add a second to. Type at:<id> or {SIDE_CHOICE}.")
        return None
    return read[1].written


def holdout_counts(
    rows: Sequence[int], shown: Mapping[int, ShownRow], changes: Mapping[int, Mapping[str, str]]
) -> dict[str, int]:
    """The sitting's rows after it, counted: labelled a position or `none`, `unsure`, and left blank."""
    counts = {"labelled": 0, "unsure": 0, "blank": 0, "second_labels": 0}
    for row in rows:
        cells = changes.get(row)
        label = cells[_POSITION] if cells is not None else shown[row].label.strip().casefold()
        also = cells[SECOND_LABEL_COLUMN] if cells is not None else shown[row].also.strip()
        if not label:
            counts["blank"] += 1
        elif label == UNSURE_LABEL:
            counts["unsure"] += 1
        else:
            counts["labelled"] += 1
            counts["second_labels"] += bool(also)
    return counts


def side_rule_line(side_rule: Sequence[int]) -> str:
    """The sitting's last line: the first-sample rows answered `side`, by number, for the PM's follow-up."""
    if not side_rule:
        return "The side rule: no row was answered side."
    return "The side rule is wrong here, the coach says, on row(s) " + ", ".join(map(str, side_rule)) + "."

"""Labeling worksheets as a spreadsheet leaves them, and the repair that puts their text back.

`scripts/prelabel_docx.py` writes each file's worksheet as a CSV for a person to correct in a
spreadsheet, and reads it back. The spreadsheet is Numbers, and on 2026-10-02 the round trip cost
an evening on the first two files without a single labeling mistake:

* Cmd+S saved `<digest>.numbers` beside the CSV and left the CSV as it was written, so the import
  read the untouched original, twice. :func:`read_worksheet` reads a `.numbers` file directly, and
  :func:`older_worksheet` stops a command that is given the older of the two.
* Numbers changed whitespace, a non-breaking space and line breaks in six rows nobody had edited.
  :func:`text_difference` names the characters, and :func:`repair_worksheet` restores the
  document's text and carries the person's marks onto it.
* Underline and highlight cells emptied to mean "nothing marked" were refused as edited text. The
  repair fills them with the row's text and no marks, which is what "nothing marked" is written as.

Nothing here decides a label. The repair writes only the `text`, `underline` and `highlight`
columns, and only toward the document. A row whose letters or digits differ from the document is
left for a person to look at, and then nothing is written at all.

Messages name a row as the spreadsheet numbers it (the header is row 1) and a column by its
header, and quote a few characters around a difference, never a whole cell: a worksheet holds
other programs' cards.
"""

from __future__ import annotations

import csv
import difflib
import os
import re
from collections.abc import Mapping, Sequence, Set
from dataclasses import dataclass
from datetime import datetime
from itertools import pairwise
from pathlib import Path

__all__ = [
    "LABEL_COLUMNS",
    "MARK_CLOSE",
    "MARK_OPEN",
    "SPAN_COLUMNS",
    "WORKSHEET_COLUMNS",
    "MarkupError",
    "Problem",
    "Repair",
    "Worksheet",
    "WorksheetError",
    "carry_marks",
    "changes_words",
    "describe_difference",
    "merge_ranges",
    "older_worksheet",
    "parse_index",
    "position_map",
    "read_worksheet",
    "render_markup",
    "repair_worksheet",
    "row_number",
    "split_markup",
    "text_difference",
    "write_worksheet_csv",
]

MARK_OPEN = "⟦"
MARK_CLOSE = "⟧"
WORKSHEET_COLUMNS = ("index", "checked", "unit", "card", "completeness", "text", "underline", "highlight")
#: The columns a person fills in. Nothing in this module writes one.
LABEL_COLUMNS = ("index", "checked", "unit", "card", "completeness")
SPAN_COLUMNS = ("underline", "highlight")

#: Characters of the document's text shown on each side of a difference.
CONTEXT = 12
#: The most characters of a changed stretch quoted in a message.
LONGEST_QUOTE = 20
#: How many differences one message describes before it says how many more there are.
DIFFERENCES_PER_MESSAGE = 3


class WorksheetError(ValueError):
    """A worksheet that cannot become labels as it stands."""


class MarkupError(ValueError):
    """`⟦` and `⟧` marks that do not pair up."""


@dataclass(frozen=True)
class Problem:
    """One thing wrong with a worksheet, or one change the repair made, where a person will find it."""

    message: str
    row: int | None = None
    column: str | None = None

    def __str__(self) -> str:
        place = ", ".join(
            part for part in (f"row {self.row}" if self.row is not None else "", self.column or "") if part
        )
        return f"{place}: {self.message}" if place else self.message


def row_number(position: int) -> int:
    """The row number the spreadsheet shows for the worksheet row at `position`: the header is row 1."""
    return position + 2


def parse_index(cell: str) -> int | None:
    """A paragraph index as a spreadsheet may show it: `12`, or `1,234` with a thousands separator."""
    digits = cell.strip().replace(",", "")
    return int(digits) if re.fullmatch(r"[0-9]+", digits) else None


# --------------------------------------------------------------------------------------------
# Reading and writing
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Worksheet:
    """A worksheet's rows as text, whichever file they were read from."""

    columns: tuple[str, ...]
    rows: tuple[dict[str, str], ...]
    #: Lines above the header: Numbers' CSV export option "Include table names" adds one.
    lines_above_header: int = 0

    @classmethod
    def of(cls, rows: Sequence[Mapping[str, str | None]]) -> Worksheet:
        """Rows already read, as `csv.DictReader` gives them."""
        columns = tuple(rows[0]) if rows else WORKSHEET_COLUMNS
        return cls(
            columns=columns,
            rows=tuple({column: row.get(column) or "" for column in columns} for row in rows),
        )


def read_worksheet(path: Path) -> Worksheet:
    """Read a worksheet from a `.csv`, or from the `.numbers` file Numbers saves with Cmd+S."""
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as handle:
            records = [list(record) for record in csv.reader(handle)]
    elif suffix == ".numbers":
        records = _numbers_records(path)
    else:
        raise WorksheetError(f"{path.name}: a worksheet is a .csv file or a .numbers file")
    return _worksheet_from_records(records, path.name)


def _header_position(records: Sequence[Sequence[str]]) -> int | None:
    for position, record in enumerate(records[:3]):
        if {"index", "text"} <= {cell.strip() for cell in record}:
            return position
    return None


def _worksheet_from_records(records: list[list[str]], name: str) -> Worksheet:
    while records and not any(cell.strip() for cell in records[-1]):
        records.pop()
    position = _header_position(records)
    if position is None:
        raise WorksheetError(
            f"{name}: no header line. The first line should read {','.join(WORKSHEET_COLUMNS)}"
        )
    header = [cell.strip() for cell in records[position]]
    columns = tuple(column for column in header if column)
    rows = tuple(
        {column: (record[i] if i < len(record) else "") for i, column in enumerate(header) if column}
        for record in records[position + 1 :]
    )
    return Worksheet(columns=columns, rows=rows, lines_above_header=position)


def _numbers_records(path: Path) -> list[list[str]]:
    """The cells of the one table in a `.numbers` file that carries the worksheet's header, as text."""
    try:
        from numbers_parser import Document
    except ImportError as error:  # pragma: no cover - the dev dependency group installs it
        raise WorksheetError(
            "reading a .numbers file needs numbers-parser, from the dev dependency group: "
            "run `uv sync --all-packages`"
        ) from error
    try:
        document = Document(str(path))
    except Exception as error:  # numbers-parser raises its own errors and plain ones alike
        raise WorksheetError(
            f"{path.name}: numbers-parser could not read it ({type(error).__name__}). Export it from "
            "Numbers instead (File, Export To, CSV, with Include table names unticked) and give that file"
        ) from error
    tables = [
        [[_cell_text(cell.value, cell.formatted_value) for cell in row] for row in table.rows()]
        for sheet in document.sheets
        for table in sheet.tables
    ]
    worksheets = [table for table in tables if _header_position(table) is not None]
    if len(worksheets) != 1:
        raise WorksheetError(
            f"{path.name}: {len(worksheets)} tables have the worksheet's header; it should have exactly one"
        )
    return worksheets[0]


def _cell_text(value: object, formatted: str) -> str:
    """What a cell holds, as the CSV would carry it. Numbers stores `12` as the number 12.0."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, int | float) and not isinstance(value, bool) and float(value).is_integer():
        return str(int(value))
    return formatted


def write_worksheet_csv(path: Path, worksheet: Worksheet) -> None:
    """Write a worksheet as CSV, replacing whatever is at `path` only once the whole file is written."""
    partial = path.with_name(f".{path.name}.partial")
    with partial.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(worksheet.columns)
        for row in worksheet.rows:
            writer.writerow([row.get(column, "") for column in worksheet.columns])
    os.replace(partial, path)


def _modified(path: Path) -> int:
    """When a file was last saved. A `.numbers` package is a folder; its newest file counts."""
    if path.is_dir():
        return max([path.stat().st_mtime_ns, *(p.stat().st_mtime_ns for p in path.rglob("*"))])
    return path.stat().st_mtime_ns


def _when(nanoseconds: int) -> str:
    return datetime.fromtimestamp(nanoseconds / 1e9).strftime("%Y-%m-%d %H:%M:%S")


def older_worksheet(path: Path) -> str | None:
    """Why `path` is not the latest save of its worksheet, or None when it is.

    Numbers' Cmd+S writes `<digest>.numbers` beside `<digest>.csv` and leaves the CSV alone; a
    repair writes the CSV from the `.numbers` file. Whichever of the two was saved last holds the
    latest work.
    """
    suffix = path.suffix.lower()
    if suffix not in (".csv", ".numbers"):
        return None
    other = path.with_suffix(".numbers" if suffix == ".csv" else ".csv")
    if not (path.exists() and other.exists()):
        return None
    mine, theirs = _modified(path), _modified(other)
    if mine >= theirs:
        return None
    return (
        f"{path.name} is older than {other.name} beside it ({_when(mine)}, against {_when(theirs)}), "
        f"so it is not your latest save. Run this again with --worksheet naming {other.name}"
    )


# --------------------------------------------------------------------------------------------
# Span markup
# --------------------------------------------------------------------------------------------


def merge_ranges(ranges: Sequence[tuple[int, int]]) -> tuple[tuple[int, int], ...]:
    """Sort and join touching or overlapping ranges: underline and emphasis spans often abut."""
    merged: list[tuple[int, int]] = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return tuple(merged)


def render_markup(text: str, ranges: Sequence[tuple[int, int]]) -> str:
    pieces: list[str] = []
    cursor = 0
    for start, end in ranges:
        pieces += [text[cursor:start], MARK_OPEN, text[start:end], MARK_CLOSE]
        cursor = end
    pieces.append(text[cursor:])
    return "".join(pieces)


def split_markup(markup: str) -> tuple[str, tuple[tuple[int, int], ...]]:
    """The text under `⟦…⟧` markup, and the marked ranges of it."""
    ranges: list[tuple[int, int]] = []
    plain: list[str] = []
    start: int | None = None
    for position, character in enumerate(markup):
        if character == MARK_OPEN:
            if start is not None:
                raise MarkupError(f"{MARK_OPEN} opened twice{_near(markup, position, position + 1)}")
            start = len(plain)
        elif character == MARK_CLOSE:
            if start is None:
                raise MarkupError(
                    f"{MARK_CLOSE} with no {MARK_OPEN} before it{_near(markup, position, position + 1)}"
                )
            if len(plain) > start:
                ranges.append((start, len(plain)))
            start = None
        else:
            plain.append(character)
    if start is not None:
        raise MarkupError(f"{MARK_OPEN} never closed{_near(markup, markup.rindex(MARK_OPEN), len(markup))}")
    return "".join(plain), merge_ranges(ranges)


# --------------------------------------------------------------------------------------------
# What changed, in words
# --------------------------------------------------------------------------------------------

#: Characters a spreadsheet changes, by name: (article, name).
_NAMES: dict[str, tuple[str, str]] = {
    " ": ("a", "space"),
    " ": ("a", "non-breaking space"),
    " ": ("a", "narrow non-breaking space"),
    " ": ("a", "thin space"),
    "​": ("a", "zero-width space"),
    "﻿": ("a", "byte-order mark"),
    "\t": ("a", "tab"),
    "\n": ("a", "line break"),
    "\r": ("a", "carriage return"),
    "\r\n": ("a", "Windows line break"),
    "\v": ("a", "vertical tab"),
    " ": ("a", "line separator"),
    " ": ("a", "paragraph separator"),
    "'": ("a", "straight quote"),
    '"': ("a", "straight double quote"),
    "‘": ("an", "opening curly quote"),
    "’": ("a", "closing curly quote"),
    "“": ("an", "opening curly double quote"),
    "”": ("a", "closing curly double quote"),
    "-": ("a", "hyphen"),
    "‐": ("a", "Unicode hyphen"),
    "‑": ("a", "non-breaking hyphen"),
    "−": ("a", "minus sign"),
    "–": ("an", "en dash"),
    "—": ("an", "em dash"),
    "…": ("an", "ellipsis character"),
    "...": ("", "three dots"),
}

_VISIBLE = str.maketrans({"\n": "↵", "\r": "↵", "\t": "→", " ": "↵", " ": "↵", "\v": "↵"})


def _visible(text: str) -> str:
    return text.translate(_VISIBLE)


def _quote(piece: str) -> str:
    shown = piece if len(piece) <= LONGEST_QUOTE else piece[:LONGEST_QUOTE] + "…"
    return f'"{_visible(shown)}"'


def _name(piece: str) -> str:
    if piece in _NAMES:
        article, name = _NAMES[piece]
        return f"{article} {name}".strip()
    if len(set(piece)) == 1 and piece[0] in _NAMES:
        return f"{len(piece)} {_NAMES[piece[0]][1]}s"
    if 1 < len(piece) <= 3 and all(character in _NAMES for character in piece):
        return " and ".join(_name(character) for character in piece)
    return _quote(piece)


def _near(text: str, start: int, end: int) -> str:
    """`, near "…a few characters…"`, never the whole of `text`; empty when nothing short enough fits."""
    end = min(end, start + LONGEST_QUOTE)
    width = CONTEXT
    while width and start - width <= 0 and end + width >= len(text):
        width //= 2
    left, right = max(0, start - width), min(len(text), end + width)
    if left == 0 and right == len(text):
        return ""
    return f', near "{"…" if left else ""}{_visible(text[left:right])}{"…" if right < len(text) else ""}"'


def _letters_and_digits(text: str) -> list[str]:
    return [character for character in text if character.isalnum()]


def changes_words(found: str, expected: str) -> bool:
    """Whether the difference touches a letter or a digit. Spacing, quotes, dashes and ellipses do not.

    Compared as the sequence of letters and digits in each text, so it does not depend on how a
    diff happens to line the two up.
    """
    return _letters_and_digits(found) != _letters_and_digits(expected)


@dataclass(frozen=True)
class _Change:
    found: str
    expected: str
    #: Where, in the document's text.
    start: int
    end: int

    @property
    def touches_words(self) -> bool:
        return any(character.isalnum() for character in self.found + self.expected)

    def describe(self, expected_text: str) -> str:
        if not self.found:
            what = f"{_name(self.expected)} missing"
        elif not self.expected:
            what = f"{_name(self.found)} added"
        else:
            what = f"{_name(self.found)} where the document has {_name(self.expected)}"
        return what + _near(expected_text, self.start, self.end)


def _changes(found: str, expected: str) -> list[_Change]:
    matcher = difflib.SequenceMatcher(None, found, expected, autojunk=False)
    return [
        _Change(found[i1:i2], expected[j1:j2], j1, j2)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes()
        if tag != "equal"
    ]


def describe_difference(found: str, expected: str) -> str:
    """The first few differences between `found` and the document's `expected` text, in words.

    Where letters or digits differ, those come first: they are what a person has to fix.
    """
    changes = _changes(found, expected)
    if changes_words(found, expected):
        changes.sort(key=lambda change: not change.touches_words)
    described = "; ".join(change.describe(expected) for change in changes[:DIFFERENCES_PER_MESSAGE])
    if len(changes) > DIFFERENCES_PER_MESSAGE:
        described += f"; and {len(changes) - DIFFERENCES_PER_MESSAGE} more"
    return described


def text_difference(found: str, expected: str, *, under_marks: bool = False) -> str:
    """Say how `found` differs from the document's `expected` text, and what fixes it."""
    words = changes_words(found, expected)
    described = describe_difference(found, expected)
    if words and under_marks:
        return (
            f"the text under the marks was edited: letters or digits differ from the document ({described}). "
            "Only the marks move: put the words back as the document has them"
        )
    if words:
        return (
            f"letters or digits differ from the document ({described}). Put them back as the document "
            "has them (Edit, Undo in Numbers, or retype them); check --repair leaves this row to you"
        )
    if under_marks:
        return (
            f"the text under the marks differs from the document only in spacing or punctuation "
            f"({described}). check --repair carries the marks onto the document's text"
        )
    return (
        f"differs from the document only in spacing or punctuation ({described}). check --repair "
        "restores the document's text"
    )


# --------------------------------------------------------------------------------------------
# Carrying marks onto the document's text
# --------------------------------------------------------------------------------------------


def position_map(old: str, new: str) -> tuple[list[int], list[int]]:
    """Where each position in `old` (0 to `len(old)`) falls in `new`, for texts with the same words.

    Letters and digits anchor the alignment: the k-th in `old` is the k-th in `new`. Between two
    anchors the texts differ only in spacing and punctuation, and that stretch is aligned
    character by character, so a mark at the edge of a word stays at the edge of that word.

    Where `new` has characters inserted at a position, the position could go before them or after
    them, so two maps come back: the earliest place each position can go, and the latest. A mark
    ends at the earliest and starts at the latest, so inserted characters at its edges stay
    unmarked: `word⟧\n` against a document's `word\r\n` gives `word⟧\r\n`, not `word\r⟧\n`.
    """
    old_anchors = [i for i, character in enumerate(old) if character.isalnum()]
    new_anchors = [j for j, character in enumerate(new) if character.isalnum()]
    if [old[i] for i in old_anchors] != [new[j] for j in new_anchors]:
        raise ValueError("the two texts differ in their letters or digits")
    earliest: list[int | None] = [None] * (len(old) + 1)
    latest: list[int | None] = [None] * (len(old) + 1)
    for (old_before, old_next), (new_before, new_next) in zip(
        pairwise([-1, *old_anchors, len(old)]), pairwise([-1, *new_anchors, len(new)]), strict=True
    ):
        old_start, new_start = old_before + 1, new_before + 1
        gap = difflib.SequenceMatcher(None, old[old_start:old_next], new[new_start:new_next], autojunk=False)
        for tag, i1, i2, j1, j2 in gap.get_opcodes():
            for offset in range(i1, i2 + 1):
                if tag == "equal":
                    places = (j1 + offset - i1,)
                elif offset == i1 == i2 or i1 < offset < i2:
                    places = (j1, j2)
                else:
                    places = (j1 if offset == i1 else j2,)
                for place in places:
                    if earliest[old_start + offset] is None:
                        earliest[old_start + offset] = new_start + place
                    latest[old_start + offset] = new_start + place
        if earliest[old_start] is None:  # two empty stretches, between adjacent anchors
            earliest[old_start] = latest[old_start] = new_start
    return [p if p is not None else 0 for p in earliest], [p if p is not None else 0 for p in latest]


def carry_marks(markup: str, text: str) -> str | None:
    """`markup` with its marks moved onto `text`, or None when the words under the marks differ.

    Returns `markup` itself when its text is already `text`. Raises :class:`MarkupError` for marks
    that do not pair up, which only a person can place.
    """
    plain, ranges = split_markup(markup)
    if plain == text:
        return markup
    if changes_words(plain, text):
        return None
    earliest, latest = position_map(plain, text)
    carried = [(latest[start], earliest[end]) for start, end in ranges]
    return render_markup(text, merge_ranges([(start, end) for start, end in carried if end > start]))


# --------------------------------------------------------------------------------------------
# The repair
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Repair:
    """A repaired worksheet, each change made to it, and the rows it would not touch."""

    worksheet: Worksheet
    changes: tuple[Problem, ...]
    #: Rows whose words differ from the document. When there are any, nothing is written.
    refused: tuple[Problem, ...]


def repair_worksheet(worksheet: Worksheet, *, texts: Mapping[int, str], sampled: Set[int]) -> Repair:
    """Undo what a spreadsheet did to a worksheet, from the document, without touching a label.

    `texts` maps each labeled paragraph's index to its text in the document, and `sampled` holds
    the indices whose spans are labeled. For each row it restores `text`, carries the marks in
    `underline` and `highlight` onto the restored text, fills an empty span cell of a sampled row
    with the text and no marks, and empties the span cells of a row that is not sampled. A row it
    cannot place (its index is not one of `texts`) is left exactly as it is, for the check to name.
    """
    changes: list[Problem] = []
    refused: list[Problem] = []
    rows: list[dict[str, str]] = []
    if worksheet.lines_above_header:
        changes.append(
            Problem(
                'removed the line above the header that Numbers\' export option "Include table names" adds'
            )
        )
    for position, row in enumerate(worksheet.rows):
        number = row_number(position)
        repaired = dict(row)
        rows.append(repaired)
        index = parse_index(row.get("index", ""))
        if index is None or index not in texts:
            continue
        text = texts[index]
        found = row.get("text", "")
        if found != text:
            if changes_words(found, text):
                refused.append(Problem(text_difference(found, text), number, "text"))
            else:
                repaired["text"] = text
                changes.append(
                    Problem(
                        f"restored the document's text ({describe_difference(found, text)})",
                        number,
                        "text",
                    )
                )
        for column in SPAN_COLUMNS:
            if column not in worksheet.columns:
                continue
            cell = row.get(column, "")
            if index not in sampled:
                if cell:
                    repaired[column] = ""
                    changes.append(
                        Problem(
                            "emptied; this row is not sampled for spans, so nothing here is a label",
                            number,
                            column,
                        )
                    )
                continue
            if not cell.strip():
                repaired[column] = text
                changes.append(
                    Problem(
                        "was empty; filled with the row's text and no marks, which says nothing on this "
                        "row is marked. If Word shows marks there, add them in the spreadsheet, save, and "
                        "repair again",
                        number,
                        column,
                    )
                )
                continue
            try:
                carried = carry_marks(cell, text)
            except MarkupError:
                continue
            if carried is None:
                plain, _ = split_markup(cell)
                refused.append(Problem(text_difference(plain, text, under_marks=True), number, column))
            elif carried != cell:
                repaired[column] = carried
                changes.append(Problem("carried the marks onto the document's text", number, column))
    return Repair(
        worksheet=Worksheet(columns=worksheet.columns, rows=tuple(rows)),
        changes=tuple(changes),
        refused=tuple(refused),
    )

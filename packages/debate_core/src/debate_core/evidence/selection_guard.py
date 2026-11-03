"""The checks a schema-valid card selection or markup answer must pass before anything uses it.

A :class:`~debate_core.evidence.selection_contract.CardSelection` can be a perfectly valid instance
of its schema and still be unusable: it names paragraph 9 of a 4-paragraph snapshot, an offset past
the end of its paragraph, two passages that overlap, or it carries a tag that is a run of the
snapshot's own words. Validation cannot see any of that, because it depends on the snapshot. This
module can, and :class:`~debate_core.application.card_selection.CardSelector` runs it through the
structured-output guard's check, so a failing answer gets the guard's one repair and then a
:class:`~debate_core.application.model_errors.ModelOutputError`, exactly like one that does not fit
its schema (v1-e05-t06-card-selection-contract, ac3).

The rules are written down in this task's session report, under *Decisions and assumptions*, and
each has a test in ``tests/evidence/test_selection_contract.py``:

* **Offsets.** Every paragraph number is one of the snapshot's, every offset lies inside the
  paragraph it names, and every passage and span selects at least one character
  (:class:`~debate_core.evidence.numbered_snapshot.NumberedSnapshot` resolves them). Two passages
  may touch but not overlap. A markup span lies wholly inside one selected passage (touching
  passages joined), spans of one style do not overlap, and every highlighted character is
  underlined.
* **Quoted text.** No string in the answer contains :data:`QUOTED_RUN_WORDS` consecutive words of
  the snapshot's normalized text. Words are maximal runs of ``\\w`` characters, compared
  case-folded after the field is put in NFC; punctuation and whitespace separate words and are
  otherwise ignored.

## A problem never quotes

A :class:`GuardProblem` names a location, a type and a sentence of counts and offsets. It never
holds the words that matched, the field's text or the snapshot's: the error that carries it, the
repair prompt that lists it and the log line that counts it would otherwise carry the evidence a
model was refused for quoting.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from enum import Enum, StrEnum
from typing import Final, cast

from pydantic import BaseModel

from debate_core.domain import SpanStyle
from debate_core.evidence.numbered_snapshot import NumberedOffsetError, NumberedSnapshot
from debate_core.evidence.selection_contract import CardSelection, MarkupSpan, MarkupSuggestion

__all__ = [
    "QUOTED_RUN_WORDS",
    "GuardProblem",
    "GuardProblemType",
    "QuotedRun",
    "SnapshotWords",
    "markup_problems",
    "quoted_text_problems",
    "selection_problems",
]

QUOTED_RUN_WORDS: Final = 12
"""How many consecutive snapshot words in a free-text field make it quoted evidence (spec ac3)."""

_WORD: Final = re.compile(r"\w+")


class GuardProblemType(StrEnum):
    """Why the guard refused an answer.

    The offset types are :class:`~debate_core.evidence.numbered_snapshot.OffsetProblem`'s values.
    """

    PARAGRAPH_OUT_OF_BOUNDS = "paragraph_out_of_bounds"
    """A paragraph number the snapshot does not have."""

    OFFSET_OUT_OF_BOUNDS = "offset_out_of_bounds"
    """An offset outside the paragraph it names."""

    REVERSED_RANGE = "reversed_range"
    """A passage or span that ends before it starts."""

    EMPTY_RANGE = "empty_range"
    """A passage or span that selects no characters."""

    OVERLAPPING_PASSAGES = "overlapping_passages"
    """Two passages that share a character."""

    OUTSIDE_SELECTION = "outside_selection"
    """A markup span that is not wholly inside one selected passage."""

    OVERLAPPING_SAME_STYLE = "overlapping_same_style"
    """Two markup spans of the same style that share a character."""

    HIGHLIGHT_NOT_UNDERLINED = "highlight_not_underlined"
    """A highlighted character that no underline covers."""

    QUOTED_SNAPSHOT_TEXT = "quoted_snapshot_text"
    """A free-text field holding a run of :data:`QUOTED_RUN_WORDS` or more of the snapshot's words."""


@dataclass(frozen=True, slots=True)
class GuardProblem:
    """One reason the guard refused an answer: where, what kind, and a sentence of numbers. Never text."""

    loc: tuple[str | int, ...]
    """Path to the offending field in the answer, as pydantic writes one."""
    type: GuardProblemType
    """What is wrong."""
    msg: str
    """What is wrong, in counts, paragraph numbers and offsets only."""


@dataclass(frozen=True, slots=True)
class QuotedRun:
    """Where a field repeats the snapshot: how many words, and the snapshot offsets they span."""

    words: int
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class SnapshotWords:
    """A snapshot's normalized text as words, indexed by every run of :data:`QUOTED_RUN_WORDS` of them."""

    text: str = field(repr=False)
    _folded: tuple[str, ...] = field(init=False, repr=False, compare=False)
    _spans: tuple[tuple[int, int], ...] = field(init=False, repr=False, compare=False)
    _first_run_at: dict[tuple[str, ...], int] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        matches = list(_WORD.finditer(self.text))
        folded = tuple(match.group().casefold() for match in matches)
        first_run_at: dict[tuple[str, ...], int] = {}
        for position in range(len(folded) - QUOTED_RUN_WORDS + 1):
            first_run_at.setdefault(folded[position : position + QUOTED_RUN_WORDS], position)
        object.__setattr__(self, "_folded", folded)
        object.__setattr__(self, "_spans", tuple(match.span() for match in matches))
        object.__setattr__(self, "_first_run_at", first_run_at)

    def quoted_run(self, field_text: str) -> QuotedRun | None:
        """The first run of :data:`QUOTED_RUN_WORDS` or more snapshot words in ``field_text``, in full."""
        words = _folded_words(unicodedata.normalize("NFC", field_text))
        for position in range(len(words) - QUOTED_RUN_WORDS + 1):
            at = self._first_run_at.get(words[position : position + QUOTED_RUN_WORDS])
            if at is None:
                continue
            length = QUOTED_RUN_WORDS
            while (
                position + length < len(words)
                and at + length < len(self._folded)
                and words[position + length] == self._folded[at + length]
            ):
                length += 1
            return QuotedRun(words=length, start=self._spans[at][0], end=self._spans[at + length - 1][1])
        return None


def selection_problems(
    selection: CardSelection, numbered: NumberedSnapshot, words: SnapshotWords | None = None
) -> tuple[GuardProblem, ...]:
    """Everything wrong with ``selection`` as a selection from ``numbered``; empty when it can be used."""
    problems: list[GuardProblem] = []
    resolved: list[tuple[int, int, int]] = []
    for index, passage in enumerate(selection.passages):
        try:
            start, end = numbered.passage_range(passage)
        except NumberedOffsetError as refused:
            problems.append(_offset_problem(("passages", index), refused))
        else:
            resolved.append((start, end, index))
    problems.extend(
        GuardProblem(
            ("passages", later),
            GuardProblemType.OVERLAPPING_PASSAGES,
            f"passage {later} shares characters with passage {earlier}; passages may touch but not overlap",
        )
        for earlier, later in _overlaps(resolved)
    )
    problems.extend(quoted_text_problems(selection, words or SnapshotWords(numbered.source.text)))
    return tuple(problems)


def markup_problems(
    markup: MarkupSuggestion,
    selection: CardSelection,
    numbered: NumberedSnapshot,
    words: SnapshotWords | None = None,
) -> tuple[GuardProblem, ...]:
    """Everything wrong with ``markup`` as markup of ``selection``; empty when it can be used.

    ``selection`` must be one :func:`selection_problems` accepted for ``numbered``; any other is a
    caller's mistake and raises :class:`~debate_core.evidence.numbered_snapshot.NumberedOffsetError`.
    """
    selected = _joined(sorted(numbered.passage_range(passage) for passage in selection.passages))
    problems: list[GuardProblem] = []
    by_style: dict[SpanStyle, list[tuple[int, int, int]]] = {style: [] for style in SpanStyle}
    for index, span in enumerate(markup.spans):
        try:
            start, end = numbered.span_range(span)
        except NumberedOffsetError as refused:
            problems.append(_offset_problem(("spans", index), refused))
            continue
        if not any(low <= start and end <= high for low, high in selected):
            problems.append(
                GuardProblem(
                    ("spans", index),
                    GuardProblemType.OUTSIDE_SELECTION,
                    f"span {index} ({_where(span)}) is not wholly inside one selected passage",
                )
            )
            continue
        by_style[span.style].append((start, end, index))
    for style, spans in by_style.items():
        problems.extend(
            GuardProblem(
                ("spans", later),
                GuardProblemType.OVERLAPPING_SAME_STYLE,
                f"{style.value} span {later} shares characters with {style.value} span {earlier}; merge them",
            )
            for earlier, later in _overlaps(spans)
        )
    underlined = _joined(sorted((start, end) for start, end, _ in by_style[SpanStyle.UNDERLINE]))
    problems.extend(
        GuardProblem(
            ("spans", index),
            GuardProblemType.HIGHLIGHT_NOT_UNDERLINED,
            f"highlight span {index} ({_where(markup.spans[index])}) is not wholly underlined",
        )
        for start, end, index in by_style[SpanStyle.HIGHLIGHT]
        if not any(low <= start and end <= high for low, high in underlined)
    )
    problems.extend(quoted_text_problems(markup, words or SnapshotWords(numbered.source.text)))
    return tuple(problems)


def quoted_text_problems(answer: BaseModel, words: SnapshotWords) -> tuple[GuardProblem, ...]:
    """One problem for each string in ``answer`` that holds a run of the snapshot's words.

    Every string field is checked, at any depth, whatever it is called. Enum members are labels
    the schema defines, not text the model wrote, and are skipped.
    """
    problems: list[GuardProblem] = []
    for loc, value in _strings(answer, ()):
        run = words.quoted_run(value)
        if run is not None:
            problems.append(
                GuardProblem(
                    loc,
                    GuardProblemType.QUOTED_SNAPSHOT_TEXT,
                    f"{run.words} consecutive words of this field are the snapshot's own words (snapshot "
                    f"offsets {run.start} to {run.end}); write it in your own words and name evidence by "
                    "paragraph number and offsets only",
                )
            )
    return tuple(problems)


def _folded_words(text: str) -> tuple[str, ...]:
    return tuple(match.group().casefold() for match in _WORD.finditer(text))


def _strings(value: object, loc: tuple[str | int, ...]) -> Iterator[tuple[tuple[str | int, ...], str]]:
    if isinstance(value, Enum):
        return
    if isinstance(value, str):
        yield loc, value
    elif isinstance(value, BaseModel):
        for name in type(value).model_fields:
            yield from _strings(getattr(value, name), (*loc, name))
    elif isinstance(value, tuple | list):
        for index, item in enumerate(cast("Sequence[object]", value)):
            yield from _strings(item, (*loc, index))


def _offset_problem(loc: tuple[str | int, ...], refused: NumberedOffsetError) -> GuardProblem:
    return GuardProblem(loc, GuardProblemType(refused.problem.value), refused.detail)


def _overlaps(ranges: Sequence[tuple[int, int, int]]) -> Iterator[tuple[int, int]]:
    """``(earlier, later)`` indices of ranges that share a character with one that starts before them."""
    furthest: tuple[int, int] | None = None
    for start, end, index in sorted(ranges):
        if furthest is not None and start < furthest[0]:
            yield furthest[1], index
        if furthest is None or end > furthest[0]:
            furthest = (end, index)


def _joined(ranges: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    """Sorted ``ranges`` with touching and overlapping ones made one."""
    joined: list[tuple[int, int]] = []
    for start, end in ranges:
        if joined and start <= joined[-1][1]:
            joined[-1] = (joined[-1][0], max(end, joined[-1][1]))
        else:
            joined.append((start, end))
    return joined


def _where(span: MarkupSpan) -> str:
    return f"paragraph {span.paragraph}, offsets {span.start_offset} to {span.end_offset}"

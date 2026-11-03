"""What an in-round marker looks like: a line's form, by pattern (`v1-e31-t23`).

A debater who stops reading a card in a round marks the place, `Marked 10:42`, and later copies
carry the mark. :func:`line_form` names a line's form by a pattern id (:class:`LineForm`), never by
its text, so a count can say what kind of line it found without saying what the line said.

The PM ruled on 2026-11-03 which forms are markers: the three in :data:`IN_ROUND_MARKER_FORMS`.
`marker-word-opens-a-short-line` and a marker word and a time inside a longer line are not. A line of
one of the three is never a cite (:func:`is_an_in_round_marker`, ruling M3), and is otherwise read as
it always was (ruling M1). The patterns are kept apart from :mod:`debate_core.evidence.in_round_markers`,
which counts them, so the classifier can ask without importing the counts.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Final

__all__ = [
    "IN_ROUND_MARKER_FORMS",
    "MARKER_FORMS",
    "MARKER_LINE_MAXIMUM_CHARACTERS",
    "LineForm",
    "is_an_in_round_marker",
    "line_form",
]

#: The longest line a marker form is read from. `Marked 10:42` is twelve characters; a marker
#: with a speech or a note after it (`marked 10:42 in the 1AR`) is still short. A longer line that
#: holds a marker word and a time is counted apart (:attr:`LineForm.MARKER_INSIDE_A_LINE`).
MARKER_LINE_MAXIMUM_CHARACTERS: Final = 60

_MARKER_WORD: Final = r"(?:mark(?:ed|ing)?|stop(?:ped)?)"
_CLOCK_TIME: Final = r"(?<!\d)(?:[01]?\d|2[0-3]):[0-5]\d(?::[0-5]\d)?(?:\s*[ap]\.?\s?m\b\.?)?(?![\d:])"
#: Anything that is neither a letter nor a digit: brackets, asterisks, dashes, slashes, spaces.
_NO_WORD: Final = r"[\W_]*"

_OPENS_WITH_A_MARKER_WORD: Final = re.compile(rf"^{_NO_WORD}(?:card\s+)?{_MARKER_WORD}\b", re.IGNORECASE)
_OPENS_WITH_A_CLOCK_TIME: Final = re.compile(rf"^{_NO_WORD}{_CLOCK_TIME}", re.IGNORECASE)
_HOLDS_A_MARKER_WORD: Final = re.compile(rf"\b{_MARKER_WORD}\b", re.IGNORECASE)
_HOLDS_A_CLOCK_TIME: Final = re.compile(_CLOCK_TIME, re.IGNORECASE)
_A_MARKER_WORD_AND_A_TIME: Final = re.compile(
    rf"\b{_MARKER_WORD}\b{_NO_WORD}(?:at\b{_NO_WORD})?{_CLOCK_TIME}", re.IGNORECASE
)
_CLOCK_TIME_ALONE: Final = re.compile(rf"^{_NO_WORD}{_CLOCK_TIME}{_NO_WORD}$", re.IGNORECASE)
_MARKER_WORD_ALONE: Final = re.compile(
    rf"^{_NO_WORD}(?:card\s+)?{_MARKER_WORD}(?:\s+(?:here|card|reading)){{0,2}}{_NO_WORD}$", re.IGNORECASE
)
_NUMBER_ALONE: Final = re.compile(rf"^{_NO_WORD}(?:(?:page|pg|p)\.?\s*)?\d+{_NO_WORD}$", re.IGNORECASE)
_OMISSION_NOTE: Final = re.compile(
    rf"^{_NO_WORD}(?:(?:text|table|figure|chart|graph|graphic|image|footnotes?)\s+)?omitted{_NO_WORD}$",
    re.IGNORECASE,
)
_LETTER_OR_DIGIT: Final = re.compile(r"[^\W_]")


class LineForm(StrEnum):
    """A line's form, by pattern. The id is what leaves a count; the line's text never does."""

    MARKER_WORD_AND_CLOCK_TIME = "marker-word-and-clock-time"
    """A short line opening with a marker word or a time that holds both: `Marked 10:42`,
    `[marked at 3:05 pm]`, `10:42 marked`."""
    CLOCK_TIME_ALONE = "clock-time-alone"
    """A time and nothing else but punctuation: `10:42`, `(3:05 PM)`."""
    MARKER_WORD_ALONE = "marker-word-alone"
    """A marker word and nothing else but punctuation, `here`, `card` or `reading`: `MARKED`,
    `*mark here*`, `card marked`, `stopped reading here`."""
    MARKER_WORD_OPENS_A_SHORT_LINE = "marker-word-opens-a-short-line"
    """A short line that opens with a marker word and is none of the above: a marker with a note, or a
    line of a source that opens `Marked increases`."""
    MARKER_INSIDE_A_LINE = "marker-word-and-clock-time-inside-a-line"
    """A marker word followed by a time inside a line no marker form takes: a marker typed after
    words of the evidence on the same line. Not a whole line, so never one a ruling could record
    whole."""
    NUMBER_ALONE = "number-alone"
    """A number, or a page number, alone: `12`, `p. 12`, `[4]`."""
    NO_LETTER_OR_DIGIT = "no-letter-or-digit"
    """Punctuation alone: an ellipsis, `***`, `[…]`, a rule of dashes."""
    OMISSION_NOTE = "omission-note"
    """A note that something was left out: `[Table omitted]`, `Text omitted`."""
    NO_MARKER_FORM = "no-marker-form"
    """Anything else."""


#: The forms a marker is read from: the lines a ruling could record as markers, whole.
MARKER_FORMS: Final = (
    LineForm.MARKER_WORD_AND_CLOCK_TIME,
    LineForm.CLOCK_TIME_ALONE,
    LineForm.MARKER_WORD_ALONE,
    LineForm.MARKER_WORD_OPENS_A_SHORT_LINE,
)


def line_form(line: str) -> LineForm:
    """The form of one line, from the first pattern that fits it, in :class:`LineForm`'s order."""
    text = " ".join(line.split())
    if not text:
        return LineForm.NO_LETTER_OR_DIGIT
    short = len(text) <= MARKER_LINE_MAXIMUM_CHARACTERS
    if short:
        opens = _OPENS_WITH_A_MARKER_WORD.search(text) or _OPENS_WITH_A_CLOCK_TIME.search(text)
        if opens and _HOLDS_A_MARKER_WORD.search(text) and _HOLDS_A_CLOCK_TIME.search(text):
            return LineForm.MARKER_WORD_AND_CLOCK_TIME
        if _CLOCK_TIME_ALONE.match(text):
            return LineForm.CLOCK_TIME_ALONE
        if _MARKER_WORD_ALONE.match(text):
            return LineForm.MARKER_WORD_ALONE
        if _OPENS_WITH_A_MARKER_WORD.search(text):
            return LineForm.MARKER_WORD_OPENS_A_SHORT_LINE
    if _A_MARKER_WORD_AND_A_TIME.search(text):
        return LineForm.MARKER_INSIDE_A_LINE
    if _NUMBER_ALONE.match(text):
        return LineForm.NUMBER_ALONE
    if not _LETTER_OR_DIGIT.search(text):
        return LineForm.NO_LETTER_OR_DIGIT
    if _OMISSION_NOTE.match(text):
        return LineForm.OMISSION_NOTE
    return LineForm.NO_MARKER_FORM


#: The forms the PM ruled markers (2026-11-03): a marker word with a time, a time alone, a marker
#: word alone. `marker-word-opens-a-short-line` is counted as a marker form but is not one: it takes
#: `Marked increases in reserve margins` as readily as a marker with a note.
IN_ROUND_MARKER_FORMS: Final = MARKER_FORMS[:3]


def is_an_in_round_marker(line: str) -> bool:
    """Whether a line is an in-round marker: one of :data:`IN_ROUND_MARKER_FORMS`."""
    if len(line.strip()) > MARKER_LINE_MAXIMUM_CHARACTERS:
        return False
    return line_form(line) in IN_ROUND_MARKER_FORMS

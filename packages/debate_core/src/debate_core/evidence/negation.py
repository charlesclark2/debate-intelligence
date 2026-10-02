"""Does a cut remove a negation? A heuristic that draws a reader's attention, nothing more.

Cutting "not" out of "the treaty will not be ratified" leaves verbatim text that says the opposite of
its source, and it verifies, because VERIFIED means the quotation is the envelope minus the omissions,
not that the cuts are fair (ADR-0018, `docs/evidence/snapshot-text-format.md`). The envelope keeps
what was removed as offsets, so the removed text can be read back from the snapshot and looked at.
This module looks.

## The rule

A cut removes a negation when any word it touches is one of :data:`NEGATION_WORDS`, or ends in
:data:`NEGATION_SUFFIX` ("don't", "won't", "isn't"), compared case-insensitively, with a curly
apostrophe (U+2019, which the normalizer keeps) read as a straight one.

"Touches" means a word that has at least one character removed. When a cut starts or ends in the
middle of a word, the whole word counts, so cutting "not" out of "cannot" is flagged as "cannot".
When it starts or ends at a word's edge, the neighbouring word does not count, so cutting " really"
out of "not really" is not flagged for the "not" it kept.

## What it is not

It is a word list, not a reading. It misses negation it has no word for ("fails to", "un-", "lack
of"), leaves out hedges such as "hardly" on purpose, and flags cuts that change nothing ("no" in
"No. 5"). It never refuses an edit and never
affects verification: :class:`~debate_core.application.card_edit_service.CardEditService` accepts
the edit, and the result and the edit log say which omission carries the flag, so the CLI and the
exporter can show it. Whether the cut is fair is the reader's call.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence

from debate_core.evidence.snapshot_text import SnapshotText

__all__ = ["NEGATION_SUFFIX", "NEGATION_WORDS", "removes_negation"]

NEGATION_WORDS: frozenset[str] = frozenset(
    {"not", "no", "never", "without", "neither", "nor", "cannot", "none", "nothing", "nobody", "nowhere"}
)
"""Words that negate on their own. Lowercase, straight apostrophes.

Hedges ("hardly", "scarcely", "barely") are left out on purpose: they weaken a claim but do not reverse
it, and flagging them would bury the cuts that do.
"""

NEGATION_SUFFIX = "n't"
"""The contracted negation: any word ending in it is a negation."""

_WORD = re.compile(r"[^\W_]+(?:['’][^\W_]+)*")


def removes_negation(snapshot_text: SnapshotText, removed: Sequence[tuple[int, int]]) -> bool:
    """True when the snapshot ranges ``removed`` take out a word that negates (see the module docstring)."""
    return any(
        _negates(word) for start, end in removed for word in _touched_words(snapshot_text.text, start, end)
    )


def _negates(word: str) -> bool:
    folded = word.lower().replace("’", "'")
    return folded in NEGATION_WORDS or folded.endswith(NEGATION_SUFFIX)


def _is_word_character(character: str) -> bool:
    return character.isalnum() or character in "'’"


def _touched_words(text: str, start: int, end: int) -> Iterator[str]:
    """The words in ``text[start:end]``, each widened to the whole word where the range cuts through it."""
    if start >= end:
        return
    if _is_word_character(text[start]):
        while start > 0 and _is_word_character(text[start - 1]):
            start -= 1
    if _is_word_character(text[end - 1]):
        while end < len(text) and _is_word_character(text[end]):
            end += 1
    yield from (match.group() for match in _WORD.finditer(text, start, end))

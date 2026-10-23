"""A pocket, hat or block heading reduced to the form a taxonomy alias is written in.

Teams name one position many ways: `1NC — Spending DA Shell`, `2. spending DA`, `Spending DA vs
Sample Squad`. :func:`normalize_heading` reduces each to `spending da`, and says whether the heading
*answers* a position (`AT: Spending DA`) rather than reading it. It is deterministic and pure: no
model, no I/O, the same text every time (`v1-e32-t01-position-taxonomy` ac4).

## What it strips, in order

1. **Characters.** Unicode compatibility forms (NFKC), an em or en dash to a spaced `-` (a
   separator), every other dash to `-`, apostrophes dropped, `&` read as `and`.
2. **Prefixes of the whole heading**, repeatedly: punctuation, numbering (`1.`, `2)`, `IV.`, `b)`,
   `#3`), round names (`1NC`, `2AR`), a preliminary round (`Round 5`, `R2`; never an elimination
   word, so `Final Rule CP` stays), and answer markers (`AT:`, `A2`, `A/T`, `Answers to`). `AT`
   without a colon counts only in capitals, so `At the Margin DA` stays a heading.
3. **Segments.** The rest is split at spaced dashes, runs of hyphens (`OFF---1NC`), pipes, colons
   and brackets. A segment that is
   only a number, a round name or an answer marker goes. A segment after the first that names a
   round (`Harbor Classic R3`, `Octas v. Sample Squad`) or ends in a tournament word
   (`Invitational`, `Classic`) goes whole, since what is left of it is a tournament or an opponent.
   An answer marker after a position has been read ends the heading: `Midterms DA AT Dome` and
   `Spending DA - AT: Golden Dome` are blocks of the DA, not answers to it. After a word that only
   names a kind of argument it does not: `Theory---AT: 50 State Fiat Bad` answers that shell.
4. **Suffixes of each segment**, repeatedly: punctuation, an opponent (`vs Sample Squad`,
   `v. Sample Squad`; a bare `v` is left alone for `Brown v Board`), a round (`R2`, `Round 4`,
   `Octas`, read by :func:`~debate_core.domain.caselist.normalize_round_token`), a round name
   (`1AC`), a version (`v1.0`, `2.0`), and `Shell`, `Block`, `Frontlines`, `Extensions`, `Off`,
   `T/L` and `Top Level`.
5. **Words.** Case-folded; every character that is not a letter or a digit is a space. A segment
   that is then only a side, `case` or `on case` goes, and so does a heading that is a count of
   off-case positions.

The result is a fixed point (normalizing it again changes nothing) and matches
:data:`~debate_core.domain.landscape.ALIAS_PATTERN`, so an alias copied from it is one the domain
model accepts and the matcher (`v1-e32-t02`) can find.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Final

from debate_core.domain.caselist import normalize_round_token

__all__ = ["NormalizedHeading", "normalize_heading"]


@dataclass(frozen=True, slots=True)
class NormalizedHeading:
    """A heading as an alias would spell it, and whether it answers the position it names."""

    text: str
    """Lowercase words of letters and digits, one space apart; empty when nothing was left."""

    answer: bool
    """True for `AT:`, `A2`, `A/T` or `Answers to`: an answer to the position, not a reading of it."""

    @property
    def is_empty(self) -> bool:
        return not self.text


_DASHES: Final = str.maketrans({"—": " - ", "–": " - ", "―": " - ", "‒": "-", "−": "-", "‐": "-", "‑": "-"})
_APOSTROPHES: Final = re.compile(r"['’‘`´]")

_ROUND_NAME: Final = r"[12](?:ac|nc|ar|nr)"
_NUMBERING: Final = re.compile(
    r"^\s*(?:#\s*\d{1,3}\b|(?:\d{1,3}|[ivx]{1,5}|[a-h])[.)\]](?=\s|$))\s*", re.IGNORECASE
)
_ROUND_PREFIX: Final = re.compile(rf"^\s*{_ROUND_NAME}\b[\s/:-]*", re.IGNORECASE)
_LEADING_ROUND: Final = re.compile(r"^\s*(?:round|rd|r)\s*[1-9]\b[\s/:.-]*", re.IGNORECASE)
_ANSWER_PREFIX: Final = re.compile(r"^\s*(?:a2|a/t|answers?\s+to)\b\s*[:-]?\s*", re.IGNORECASE)
_CAPITAL_AT_PREFIX: Final = re.compile(r"^\s*AT\b\s*[:-]?\s*")
_ANY_AT_WITH_COLON: Final = re.compile(r"^\s*at\s*:\s*", re.IGNORECASE)
_ANSWER_WORDS: Final = frozenset({"at", "a2", "a/t", "answers to", "answer to"})
_INNER_ANSWER: Final = re.compile(r"\s(?:AT|[Aa]2|[Aa]/[Tt])\b\s*:?\s+\S|\s[Aa][Tt]\s*:\s*\S")
_EDGE_PUNCTUATION: Final = " \t.,;!?*_~\"'-"

_SEPARATORS: Final = re.compile(r"\s+[-|]\s+|\s*-{2,}\s*|\s*[|:()\[\]]\s*")
_OPPONENT: Final = re.compile(r"\s+(?:vs\.?|v\.)\s+.*$", re.IGNORECASE)
_ROUND_SUFFIX: Final = re.compile(rf"\s*\b{_ROUND_NAME}\s*$", re.IGNORECASE)
_STRUCTURE_SUFFIX: Final = re.compile(
    r"\s*\b(?:shells?|blocks?|frontlines?|ext(?:ension)?s?|off|t/l|top\s+level)\s*$", re.IGNORECASE
)
_VERSION_SUFFIX: Final = re.compile(r"\s*\b(?:v\s?\d+(?:\.\d+)*|\d+\.\d+(?:\.\d+)*)\s*$", re.IGNORECASE)
_LONGEST_ROUND_PHRASE: Final = 3
_TOURNAMENT_WORDS: Final = frozenset(
    {"invitational", "invite", "classic", "tournament", "swing", "championship", "championships", "rr"}
)

_NOT_A_WORD: Final = re.compile(r"[^0-9a-z]+")
_STRUCTURAL: Final = frozenset(
    {"aff", "neg", "affirmative", "negative", "case", "on", "on case", "off case", "offcase"}
)
_OFF_COUNT: Final = re.compile(r"^\d{1,2} off$")
_CATEGORY_WORDS: Final = frozenset(
    {"theory", "t", "topicality", "k", "kritik", "da", "disad", "cp", "counterplan", "framework"}
)
"""Words that name a kind of argument and no position, so an answer marker after one does not end it."""


def normalize_heading(raw: str) -> NormalizedHeading:
    """`raw` as an alias would spell it, and whether it answers a position. Never raises."""
    text = _APOSTROPHES.sub("", unicodedata.normalize("NFKC", raw).translate(_DASHES)).replace("&", " and ")
    text, answer = _strip_prefixes(text)
    kept: list[str] = []
    for index, part in enumerate(part for part in _SEPARATORS.split(text) if part.strip(_EDGE_PUNCTUATION)):
        segment = part.strip(_EDGE_PUNCTUATION)
        marked = segment.casefold() in _ANSWER_WORDS or _strip_prefixes(segment)[1]
        if marked and kept and " ".join(kept) not in _CATEGORY_WORDS:
            break
        if segment.casefold() in _ANSWER_WORDS:
            answer = True
            continue
        segment, segment_answer = _strip_prefixes(segment)
        answer = answer or segment_answer
        inner = _INNER_ANSWER.search(segment)
        if inner is not None:
            segment = segment[: inner.start()]
        segment, labelled = _strip_suffixes(segment)
        words = _words(segment)
        if _names_a_position(words, labelled=labelled, first=index == 0):
            kept.append(words)
        if inner is not None:
            break
    joined = " ".join(kept)
    if joined in _STRUCTURAL or _OFF_COUNT.match(joined):
        joined = ""
    return NormalizedHeading(text=joined, answer=answer)


def _names_a_position(words: str, *, labelled: bool, first: bool) -> bool:
    """False for a segment that is empty, a number, a side, or a round or tournament after the first."""
    if not words or words.isdigit() or words in _STRUCTURAL:
        return False
    return not (labelled and not first) and words.rsplit(" ", 1)[-1] not in _TOURNAMENT_WORDS


def _strip_prefixes(text: str) -> tuple[str, bool]:
    """Numbering, round names and answer markers off the front, as often as they repeat."""
    answer = False
    while True:
        before = text
        text = _NUMBERING.sub("", text.lstrip(_EDGE_PUNCTUATION), count=1)
        text = _ROUND_PREFIX.sub("", text, count=1)
        text = _LEADING_ROUND.sub("", text, count=1)
        for marker in (_ANSWER_PREFIX, _CAPITAL_AT_PREFIX, _ANY_AT_WITH_COLON):
            text, found = marker.subn("", text, count=1)
            answer = answer or bool(found)
        if text == before:
            return text, answer


def _strip_suffixes(text: str) -> tuple[str, bool]:
    """Opponents, rounds and Shell/Block/Off off the end; True when a round or an opponent went."""
    labelled = False
    while True:
        before = text
        text = text.rstrip(_EDGE_PUNCTUATION)
        text, opponents = _OPPONENT.subn("", text, count=1)
        text, round_found = _without_trailing_round(text)
        labelled = labelled or bool(opponents) or round_found
        text = _ROUND_SUFFIX.sub("", text, count=1)
        text = _STRUCTURE_SUFFIX.sub("", text, count=1)
        text = _VERSION_SUFFIX.sub("", text, count=1)
        if text == before:
            return text, labelled


def _without_trailing_round(text: str) -> tuple[str, bool]:
    """`text` without a round its last one to three words name (`R3`, `Round 4`, `Double Octas`)."""
    words = text.split()
    for length in range(min(_LONGEST_ROUND_PHRASE, len(words)), 0, -1):
        if normalize_round_token(" ".join(words[-length:])) is not None:
            return " ".join(words[:-length]), True
    return text, False


def _words(text: str) -> str:
    return " ".join(_NOT_A_WORD.sub(" ", text.casefold()).split())

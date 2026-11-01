"""Does a rendered card's body still say what its card says? The DOCX half of `verify` (`v1-e06-t07`).

A .docx the platform exported carries its manifest (`v1-e06-t04`), and `verify` checks each manifest
card against its stored snapshot exactly as it checks a JSON manifest. That proves the manifest. This
module checks the other half: that the evidence a reader sees in the document body is still the
card's ``evidence_text``, give or take the edits a student may make (architecture proposal §8 step 7,
:mod:`debate_core.evidence.edit_policy`). It is pure: :mod:`debate_core.evidence.docx_reader` turns the
document into a :class:`DocumentBody`, and nothing here opens a file or reads a snapshot.

## Which body card is which manifest card

:func:`match_body_cards` pairs them by position and tag. When the body holds as many cards as the
manifest, the n-th tag is the n-th card, whatever its words: a tag is the student's own to rewrite.
When the counts differ, a card was added or taken out, so each manifest card is matched, in order, to
the next body card with exactly its tag. A manifest card with no body card is reported, and so is a
body card no manifest card claims.

## Which paragraphs are the evidence

Inside one body card (its tag up to the next heading), the cite is the first paragraph that carries
the cite character style; if none does, it is the first paragraph, or the second when the card was
rendered with an UNVERIFIED banner above its cite. Everything after the cite is the evidence: its
paragraphs that hold anything but whitespace, joined with a line feed. A paragraph a student added
after the evidence therefore reads as evidence and is reported, never skipped, because a reader of
the document would take it for part of the card.

## The edit policy, in the body

The body evidence is compared with ``evidence_text`` as a sequence of tokens: words, single
characters of whitespace and punctuation, and bracketed groups. A token-level diff (Myers, so the
fewest tokens are added and removed) leaves each difference as a *hunk*, a run of removed card tokens
and added body tokens between two runs that match. A hunk is allowed when:

* it only removes card tokens: a deletion. Because tokens are whole words, a deletion inside a word
  ("un" out of "unlikely") is not one of these; it is a changed word. The edit API accepts any range,
  so this is the one place the body is held to more than E03's rules: a document has no record of
  which characters were removed, only of what is left, and a word that lost letters is a different
  word (the session report records the choice);
* what it adds is whitespace, at most one bracketed interpolation, and the format profile's omission
  marker, and at least one of the last two. An interpolation is :class:`~debate_core.domain.Interpolation`'s
  rendering, square brackets around text an ``Interpolation`` accepts; two in one place are refused,
  as E03 refuses a second interpolation at one anchor. An omission marker is allowed where text was
  removed, in that hunk or by the card's own omissions; a marker that claims a cut nobody made is not.

Formatting is never read: underlining, highlighting and sizes are the student's to change, so a markup
change is not a difference at all. Every other hunk is a :class:`ManualEdit`, with the card range it
replaced and the body range it holds. A body that keeps none of the card's words is one too: E03
refuses the deletion that would leave nothing quoted.

## What it never holds

Text. A :class:`ManualEdit` is two ranges, a :class:`BodyInterpolation` an offset and a length, so a
report built from them cannot carry a word of the evidence or of the student's insertion.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from pydantic import TypeAdapter, ValidationError

from debate_core.domain import Card, InterpolatedText, VerificationStatus
from debate_core.evidence.run_segmentation import omission_offsets

__all__ = [
    "MAXIMUM_BODY_EDIT_TOKENS",
    "BodyCard",
    "BodyComparison",
    "BodyInterpolation",
    "BodyParagraph",
    "CharacterRange",
    "DocumentBody",
    "ManualEdit",
    "body_evidence",
    "compare_body",
    "match_body_cards",
]

MAXIMUM_BODY_EDIT_TOKENS: Final = 2000
"""The most tokens a body may add and remove before it is reported as one edit of the whole card.

The diff's time grows with this number times the card's length. A body that differs from its card in
more tokens than this is not a lightly cut card; reporting it whole is a :class:`ManualEdit` either way.
"""

_TOKEN: Final = re.compile(r"\[[^\[\]]*\]|[^\W_]+(?:['’][^\W_]+)*|.", re.DOTALL)
"""A bracketed group, a word (apostrophes inside it included, as the negation check reads words), or
any other single character, whitespace and line feeds among them."""

_INTERPOLATED_TEXT: Final[TypeAdapter[str]] = TypeAdapter(InterpolatedText)


# --------------------------------------------------------------------------------------------
# What the reader gives
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BodyParagraph:
    """One paragraph of a body card as Word shows it, and whether it carries the cite style."""

    text: str
    is_cite: bool = False


@dataclass(frozen=True, slots=True)
class BodyCard:
    """A tag in the body and the paragraphs under it, up to the next heading of any level."""

    position: int
    """Its index among the body's tags, from 0."""
    tag: str
    paragraphs: tuple[BodyParagraph, ...]


@dataclass(frozen=True, slots=True)
class DocumentBody:
    """Every card in a document's body, in document order."""

    cards: tuple[BodyCard, ...]


# --------------------------------------------------------------------------------------------
# What the comparison gives
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CharacterRange:
    """``[start, end)``; empty where something was only added."""

    start: int
    end: int


@dataclass(frozen=True, slots=True)
class ManualEdit:
    """A difference the edit policy does not allow: the card's characters it replaced, and the body's."""

    evidence_range: CharacterRange
    """Into the card's ``evidence_text``, as ``first_differing_offset`` is."""
    body_range: CharacterRange
    """Into the body's evidence: its paragraphs joined with a line feed (:func:`body_evidence`)."""


@dataclass(frozen=True, slots=True)
class BodyInterpolation:
    """A bracketed interpolation in the body: where it is read, its length, and whether the card has it."""

    anchor: int
    """The ``evidence_text`` offset it is read before, as an ``Interpolation``'s anchor is."""
    length: int
    """How many characters are inside its brackets."""
    recorded: bool
    """True when the card records an interpolation of exactly this text here."""


@dataclass(frozen=True, slots=True)
class BodyComparison:
    """What the body did to the card's evidence, by the edit policy's kinds."""

    manual_edits: tuple[ManualEdit, ...]
    interpolations: tuple[BodyInterpolation, ...]
    deletions: tuple[CharacterRange, ...]
    """The card ranges the body leaves out, whether a hunk only removed them or also added a marker."""

    @property
    def follows_the_policy(self) -> bool:
        """True when every difference is one the edit policy allows."""
        return not self.manual_edits


# --------------------------------------------------------------------------------------------
# Matching and segmenting
# --------------------------------------------------------------------------------------------


def match_body_cards(
    tags: Sequence[str], body: DocumentBody
) -> tuple[tuple[BodyCard | None, ...], tuple[BodyCard, ...]]:
    """Each manifest card's body card (or None), and the body cards no manifest card claims.

    ``tags`` are the manifest cards' tags in manifest order. See the module docstring for the rule.
    """
    if len(tags) == len(body.cards):
        return tuple(body.cards), ()
    matched: list[BodyCard | None] = []
    cursor = 0
    for tag in tags:
        found = next(
            (index for index in range(cursor, len(body.cards)) if body.cards[index].tag == tag), None
        )
        if found is None:
            matched.append(None)
            continue
        matched.append(body.cards[found])
        cursor = found + 1
    claimed = {card.position for card in matched if card is not None}
    return tuple(matched), tuple(card for card in body.cards if card.position not in claimed)


def body_evidence(card: Card, body_card: BodyCard) -> str:
    """The evidence ``body_card`` shows for ``card``: what follows its cite, blank paragraphs left out."""
    paragraphs = body_card.paragraphs
    cite = next((index for index, paragraph in enumerate(paragraphs) if paragraph.is_cite), None)
    if cite is None:
        cite = 0 if card.verification_status is VerificationStatus.VERIFIED else 1
    return "\n".join(paragraph.text for paragraph in paragraphs[cite + 1 :] if paragraph.text.strip())


def compare_body(card: Card, body_text: str, omission_marker: str) -> BodyComparison:
    """Classify every difference between ``card.evidence_text`` and ``body_text`` by the edit policy."""
    evidence = _tokens(card.evidence_text)
    body = _tokens(body_text)
    whole = ManualEdit(CharacterRange(0, len(card.evidence_text)), CharacterRange(0, len(body_text)))
    hunks = _diff(
        [token.text for token in evidence], [token.text for token in body], MAXIMUM_BODY_EDIT_TOKENS
    )
    if hunks is None:
        return BodyComparison(manual_edits=(whole,), interpolations=(), deletions=())
    hunks = _trimmed(_merged(_slid(hunks, evidence, body), evidence, body), evidence, body)
    removed_words = sum(
        1 for hunk in hunks for token in evidence[hunk.removed_start : hunk.removed_end] if not token.is_space
    )
    kept_words = sum(1 for token in evidence if not token.is_space) - removed_words
    if kept_words == 0 and (card.evidence_text.strip() or body_text.strip()):
        # E03 refuses the deletion that leaves nothing quoted ("delete the card instead").
        return BodyComparison(manual_edits=(whole,), interpolations=(), deletions=())
    return _Classifier(card, evidence, body, _tokens(omission_marker.strip())).classify(hunks)


# --------------------------------------------------------------------------------------------
# Tokens and the diff
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Token:
    text: str
    start: int

    @property
    def end(self) -> int:
        return self.start + len(self.text)

    @property
    def is_space(self) -> bool:
        return self.text.isspace()

    @property
    def is_bracketed(self) -> bool:
        return len(self.text) >= 2 and self.text[0] == "[" and self.text[-1] == "]"


def _tokens(text: str) -> list[_Token]:
    return [_Token(match.group(), match.start()) for match in _TOKEN.finditer(text)]


@dataclass(frozen=True, slots=True)
class _Hunk:
    """Card tokens ``[removed_start, removed_end)`` replaced by body tokens ``[added_start, added_end)``."""

    removed_start: int
    removed_end: int
    added_start: int
    added_end: int


def _diff(removed: Sequence[str], added: Sequence[str], limit: int) -> list[_Hunk] | None:
    """The hunks of a shortest edit script from ``removed`` to ``added`` (Myers), or None past ``limit``."""
    n, m = len(removed), len(added)
    if abs(n - m) > limit:
        return None
    offset = limit + 1
    frontier = [0] * (2 * limit + 3)
    trace: list[list[int]] = []
    for d in range(min(n + m, limit) + 1):
        trace.append(frontier[offset - d - 1 : offset + d + 2])
        for k in range(-d, d + 1, 2):
            if k == -d or (k != d and frontier[offset + k - 1] < frontier[offset + k + 1]):
                x = frontier[offset + k + 1]
            else:
                x = frontier[offset + k - 1] + 1
            y = x - k
            while x < n and y < m and removed[x] == added[y]:
                x, y = x + 1, y + 1
            frontier[offset + k] = x
            if x >= n and y >= m:
                return _hunks_of(_moves(trace, n, m), n, m)
    return None


def _moves(trace: list[list[int]], n: int, m: int) -> list[tuple[int, int]]:
    """Every point the shortest path passes through, from ``(n, m)`` back to ``(0, 0)``."""
    x, y = n, m
    points = [(x, y)]
    for d in range(len(trace) - 1, -1, -1):
        saved = trace[d]  # the frontier before step d, diagonals -d-1 .. d+1, so diagonal k is at k+d+1
        k = x - y
        down = k == -d or (k != d and saved[k - 1 + d + 1] < saved[k + 1 + d + 1])
        previous_k = k + 1 if down else k - 1
        previous_x = saved[previous_k + d + 1]
        previous_y = previous_x - previous_k
        while x > previous_x and y > previous_y:
            x, y = x - 1, y - 1
            points.append((x, y))
        if d > 0:
            x, y = previous_x, previous_y
            points.append((x, y))
    return points[::-1]


def _hunks_of(points: list[tuple[int, int]], n: int, m: int) -> list[_Hunk]:
    hunks: list[_Hunk] = []
    open_at: tuple[int, int] | None = None
    for (x0, y0), (x1, y1) in zip(points, points[1:], strict=False):
        diagonal = x1 - x0 == 1 and y1 - y0 == 1
        if diagonal and open_at is not None:
            hunks.append(_Hunk(open_at[0], x0, open_at[1], y0))
            open_at = None
        elif not diagonal and open_at is None:
            open_at = (x0, y0)
    if open_at is not None:
        hunks.append(_Hunk(open_at[0], n, open_at[1], m))
    return hunks


def _slid(hunks: list[_Hunk], removed: Sequence[_Token], added: Sequence[_Token]) -> list[_Hunk]:
    """Each hunk that only removes or only adds moved as far right as its matching neighbours allow.

    Where a run of tokens repeats, a shortest edit script may take either copy; the rightmost is the
    one that reads as "this was taken out" or "this was put in before that word", so an interpolation
    is read before the word after it and a deletion of a sentence takes the sentence, not the full stop
    before it.
    """
    slid: list[_Hunk] = []
    for index, hunk in enumerate(hunks):
        limit_removed = hunks[index + 1].removed_start if index + 1 < len(hunks) else len(removed)
        a0, a1, b0, b1 = hunk.removed_start, hunk.removed_end, hunk.added_start, hunk.added_end
        if a0 == a1:
            while a0 < limit_removed and b1 < len(added) and added[b0].text == added[b1].text:
                a0, a1, b0, b1 = a0 + 1, a1 + 1, b0 + 1, b1 + 1
        elif b0 == b1:
            while a1 < limit_removed and removed[a0].text == removed[a1].text:
                a0, a1, b0, b1 = a0 + 1, a1 + 1, b0 + 1, b1 + 1
        slid.append(_Hunk(a0, a1, b0, b1))
    return slid


def _merged(hunks: list[_Hunk], removed: Sequence[_Token], added: Sequence[_Token]) -> list[_Hunk]:
    """Hunks that only whitespace keeps apart, joined: one place in the text, one difference."""
    merged: list[_Hunk] = []
    for hunk in hunks:
        if merged and all(token.is_space for token in removed[merged[-1].removed_end : hunk.removed_start]):
            last = merged.pop()
            hunk = _Hunk(last.removed_start, hunk.removed_end, last.added_start, hunk.added_end)
        merged.append(hunk)
    return merged


def _trimmed(hunks: list[_Hunk], removed: Sequence[_Token], added: Sequence[_Token]) -> list[_Hunk]:
    """Each hunk without the tokens it removes and adds back unchanged at either end."""
    trimmed: list[_Hunk] = []
    for hunk in hunks:
        a0, a1, b0, b1 = hunk.removed_start, hunk.removed_end, hunk.added_start, hunk.added_end
        while a0 < a1 and b0 < b1 and removed[a0].text == added[b0].text:
            a0, b0 = a0 + 1, b0 + 1
        while a0 < a1 and b0 < b1 and removed[a1 - 1].text == added[b1 - 1].text:
            a1, b1 = a1 - 1, b1 - 1
        if a0 < a1 or b0 < b1:
            trimmed.append(_Hunk(a0, a1, b0, b1))
    return trimmed


# --------------------------------------------------------------------------------------------
# Classifying each hunk
# --------------------------------------------------------------------------------------------


class _Classifier:
    def __init__(self, card: Card, evidence: list[_Token], body: list[_Token], marker: list[_Token]) -> None:
        self._card = card
        self._evidence = evidence
        self._body = body
        self._marker = [token.text for token in marker]
        self._omissions = frozenset(omission_offsets(card))

    def classify(self, hunks: list[_Hunk]) -> BodyComparison:
        edits: list[ManualEdit] = []
        interpolations: list[BodyInterpolation] = []
        deletions: list[CharacterRange] = []
        for hunk in hunks:
            removed = self._range(
                self._evidence, hunk.removed_start, hunk.removed_end, len(self._card.evidence_text)
            )
            added = self._range(self._body, hunk.added_start, hunk.added_end, self._body_length)
            inserted = self._insertion(hunk, removed)
            if inserted is None:
                edits.append(ManualEdit(removed, added))
                continue
            if removed.start < removed.end:
                deletions.append(removed)
            if inserted != "":
                interpolations.append(self._interpolation(inserted, removed))
        return BodyComparison(tuple(edits), tuple(interpolations), tuple(deletions))

    @property
    def _body_length(self) -> int:
        return self._body[-1].end if self._body else 0

    @staticmethod
    def _range(tokens: list[_Token], start: int, end: int, length: int) -> CharacterRange:
        if start < end:
            return CharacterRange(tokens[start].start, tokens[end - 1].end)
        offset = tokens[start].start if start < len(tokens) else length
        return CharacterRange(offset, offset)

    def _insertion(self, hunk: _Hunk, removed: CharacterRange) -> str | None:
        """What the hunk adds, if the policy allows it: ``""`` for nothing or a marker, the
        interpolation's text for one; None when it adds anything else."""
        added = self._body[hunk.added_start : hunk.added_end]
        if not added:
            return ""
        interpolations: list[str] = []
        markers = 0
        index = 0
        while index < len(added):
            token = added[index]
            if self._marker and [t.text for t in added[index : index + len(self._marker)]] == self._marker:
                markers += 1
                index += len(self._marker)
                continue
            if token.is_bracketed:
                try:
                    interpolations.append(_INTERPOLATED_TEXT.validate_python(token.text[1:-1]))
                except ValidationError:
                    return None
            elif not token.is_space:
                return None
            index += 1
        if len(interpolations) > 1 or not (interpolations or markers):
            return None
        if markers and removed.start == removed.end and removed.start not in self._omissions:
            return None
        return interpolations[0] if interpolations else ""

    def _interpolation(self, text: str, removed: CharacterRange) -> BodyInterpolation:
        recorded = next(
            (
                item.anchor
                for item in self._card.interpolations
                if item.text == text and removed.start <= item.anchor <= removed.end
            ),
            None,
        )
        anchor = recorded if recorded is not None else removed.end
        return BodyInterpolation(anchor=anchor, length=len(text), recorded=recorded is not None)

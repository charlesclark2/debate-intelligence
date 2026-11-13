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

The format profile's whole omission marker (``" … "``, its spaces included) is one unit in the diff, in
the body and in the card alike, and its tokens are put back after it (`v1-e06-t15`). So is a marker
typed with other spacing: the marker's sign ("…") with all the whitespace either side of it, as one
space, none, non-breaking spaces or two spaces each side (`v1-e06-t16`). Compared token
by token, the marker's spaces could be paired with the card's spaces either side of the word after a
cut, and Myers then had two equally short edit scripts: one deletes the word, the other reads the
word before it as moved across the marker, a manual edit. As a unit the marker matches nothing but a
marker, so a whole-word deletion beside a cut is a deletion wherever it sits. Then each hunk drops the
tokens it removes and adds back unchanged at its ends, so a space beside the marker that can be the
card's own space is read as the card's: deleting "The " right after a cut leaves one space after the
marker, which is the card's space after "The", and the deletion is "The". A marker typed over words
is read the same way. A hunk that is a manual edit does not report a whole marker at either end where
the card has a cut: that marker is the card's own, and the edit's body range is what the student
changed.

The card's evidence is tokenized with its omission offsets as token boundaries (`v1-e06-t16`).
``evidence_text`` joins the kept pieces with nothing between them, so where a piece ends in a word and
the next starts with one, the card holds one run of letters ("holdflood") where the body shows two
words either side of the marker ("hold … flood"). Split at the cut, they are the two words the source
wrote, and the untouched body only adds a marker at a cut. The body is tokenized as Word shows it.

An interpolation anchored inside one of the card's words is a token boundary too, where the body shows
that word split by a bracketed group (`v1-e06-t17`): the body's "le[s]vee" is the card's "le" and
"vee" with an interpolation read between them, so an untouched export verifies. A body that leaves the
interpolation out shows the source's word whole, and the card's word stays whole to match it. Letters
deleted on one side of such an anchor ("[s]vee") change the word, a manual edit.

Three full stops typed with whitespace either side (" ... ") read as the profile's "…" (the coach's
decision of 2026-11-13), with the same spacing rule as the sign itself. Without whitespace on both
sides they are three full stops, and a hunk that adds them is a manual edit. This is verify's reading
only: the renderer draws "…".

## A cut is always shown (`v1-e06-t17`)

Each of the card's cuts must be drawn: some hunk that takes in its omission offset must add a marker.
A body that takes the marker out shows the card's characters with nothing where text was cut, and a
reader cannot tell. That is a :class:`HiddenCut` wherever the join falls:

* the marker taken out where the cut joins a full stop to a word ("fail.The"), which leaves no hunk at
  all, or a word to a word ("holdnever"), which leaves a hunk whose characters are the card's own and
  only its tokens break differently. Until this task the second was a manual edit and the first verified;
* the marker replaced by whitespace or by an interpolation: not a manual edit for an added space, the cut
  hidden;
* a word deleted beside the cut with the marker: the deletion is still a deletion, and the cut is hidden
  where the body runs the two sides together.

A deletion that takes in two cuts shows both with one marker: the reader sees that text was cut there.
A hunk that is a manual edit for what it adds is only a manual edit, whatever cut it takes in.

Formatting is never read: underlining, highlighting and sizes are the student's to change, so a markup
change is not a difference at all. Every other hunk is a :class:`ManualEdit`, with the card range it
replaced and the body range it holds. A body that keeps none of the card's words is one too: E03
refuses the deletion that would leave nothing quoted.

## A deletion that removes a negation (`v1-e06-t10`)

E03's DeleteRange flags a cut that takes out a word that negates, and :func:`removed_negations` asks
the body's deletions the same question with the same code: each deletion's ``evidence_text`` range is
mapped to the snapshot ranges it was cut from
(:func:`~debate_core.evidence.card_mapping.snapshot_ranges_of`) and handed to
:func:`~debate_core.evidence.negation.removes_negation`, so the words read are the ones the body took
out, never a card omission between them, and the word list is the policy's. A hit is a
:class:`RemovedNegation`, one per deletion however many negating words it took. It is a warning, never a
difference the policy refuses: the words that are left are still the source's.

## What it never holds

Text. A :class:`ManualEdit` is two ranges, a :class:`BodyInterpolation` an offset and a length, a
:class:`RemovedNegation` two ranges and a :class:`HiddenCut` two offsets, so a report built from them
cannot carry a word of the evidence or of the student's insertion.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from pydantic import TypeAdapter, ValidationError

from debate_core.domain import Card, InterpolatedText, VerificationStatus
from debate_core.evidence.card_mapping import snapshot_ranges_of
from debate_core.evidence.negation import removes_negation
from debate_core.evidence.run_segmentation import omission_offsets
from debate_core.evidence.snapshot_text import SnapshotText

__all__ = [
    "MAXIMUM_BODY_EDIT_TOKENS",
    "BodyCard",
    "BodyComparison",
    "BodyInterpolation",
    "BodyParagraph",
    "CharacterRange",
    "DocumentBody",
    "HiddenCut",
    "ManualEdit",
    "RemovedNegation",
    "body_evidence",
    "compare_body",
    "match_body_cards",
    "removed_negations",
]

MAXIMUM_BODY_EDIT_TOKENS: Final = 2000
"""The most tokens a body may add and remove before it is reported as one edit of the whole card.

The diff's time grows with this number times the card's length. A body that differs from its card in
more tokens than this is not a lightly cut card; reporting it whole is a :class:`ManualEdit` either way.
"""

_TOKEN: Final = re.compile(r"(?<=\s)\.\.\.(?=\s)|\[[^\[\]]*\]|[^\W_]+(?:['’][^\W_]+)*|.", re.DOTALL)
"""Three full stops with whitespace either side (`v1-e06-t17`), a bracketed group, a word (apostrophes
inside it included, as the negation check reads words), or any other single character, whitespace and
line feeds among them."""

_ELLIPSIS: Final = "…"
_TYPED_ELLIPSIS: Final = "..."
"""Three full stops typed for the ellipsis: a marker sign beside "…" when whitespace stands either side
of them (the coach's decision of 2026-11-13). Without it they are three full stops."""

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
class HiddenCut:
    """One of the card's own cuts that the body does not show: no omission marker where it falls."""

    evidence_offset: int
    """The cut's omission offset in ``evidence_text``."""
    body_offset: int
    """Where in the body's evidence the cut's marker should be."""


@dataclass(frozen=True, slots=True)
class BodyComparison:
    """What the body did to the card's evidence, by the edit policy's kinds."""

    manual_edits: tuple[ManualEdit, ...]
    interpolations: tuple[BodyInterpolation, ...]
    deletions: tuple[CharacterRange, ...]
    """The card ranges the body leaves out, whether a hunk only removed them or also added a marker."""
    hidden_cuts: tuple[HiddenCut, ...] = ()
    """The card's cuts the body shows no marker for, in evidence order (`v1-e06-t17`)."""

    @property
    def follows_the_policy(self) -> bool:
        """True when every difference is one the edit policy allows."""
        return not self.manual_edits and not self.hidden_cuts


@dataclass(frozen=True, slots=True)
class RemovedNegation:
    """A deletion in the body that took out a word that negates, by the edit policy's test."""

    evidence_range: CharacterRange
    """The deletion, into the card's ``evidence_text``, as :attr:`BodyComparison.deletions` gives it."""
    snapshot_range: CharacterRange
    """The same deletion in the snapshot: from its first removed character to its last. A deletion
    across one of the card's own cuts spans that omission too, as E03's flag names the omission that
    holds it; only the quoted words either side were read."""


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
    cuts = omission_offsets(card)
    shown_anchors = _anchors_shown_inside_words(card, cuts, body_text)
    evidence = _tokens(card.evidence_text, sorted({*cuts, *shown_anchors}))
    body = _tokens(body_text)
    marker = [token.text for token in _tokens(omission_marker)]
    signs = _marker_signs(marker)
    evidence_units, evidence_bounds = _units(evidence, signs)
    body_units, body_bounds = _units(body, signs)
    whole = ManualEdit(CharacterRange(0, len(card.evidence_text)), CharacterRange(0, len(body_text)))
    unit_hunks = _diff(
        [unit.text for unit in evidence_units], [unit.text for unit in body_units], MAXIMUM_BODY_EDIT_TOKENS
    )
    if unit_hunks is None:
        return BodyComparison(manual_edits=(whole,), interpolations=(), deletions=())
    unit_hunks = _merged(_slid(unit_hunks, evidence_units, body_units), evidence_units, body_units)
    hunks = _trimmed(_expanded(unit_hunks, evidence_bounds, body_bounds), evidence, body)
    removed_words = sum(
        1
        for hunk in hunks
        if not _same_text(hunk, evidence, body)
        for token in evidence[hunk.removed_start : hunk.removed_end]
        if not token.is_space
    )
    kept_words = sum(1 for token in evidence if not token.is_space) - removed_words
    if kept_words == 0 and (card.evidence_text.strip() or body_text.strip()):
        # E03 refuses the deletion that leaves nothing quoted ("delete the card instead").
        return BodyComparison(manual_edits=(whole,), interpolations=(), deletions=())
    return _Classifier(card, evidence, body, marker, signs).classify(hunks)


def removed_negations(
    card: Card, comparison: BodyComparison, snapshot_text: SnapshotText
) -> tuple[RemovedNegation, ...]:
    """Each of ``comparison``'s deletions that removes a word that negates, in body order.

    ``snapshot_text`` must be the text ``card``'s evidence was rebuilt from exactly
    (:meth:`~debate_core.application.evidence_verifier.EvidenceVerifier.verify_with_snapshot_text`
    gives it only then), so the snapshot words at a deletion's offsets are the words the body removed.
    """
    found: list[RemovedNegation] = []
    for deletion in comparison.deletions:
        removed = snapshot_ranges_of(card, deletion.start, deletion.end)
        if removes_negation(snapshot_text, removed):
            found.append(RemovedNegation(deletion, CharacterRange(removed[0][0], removed[-1][1])))
    return tuple(found)


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


def _tokens(text: str, boundaries: Sequence[int] = ()) -> list[_Token]:
    """``text`` as tokens, none of which crosses one of ``boundaries`` (increasing offsets into ``text``).

    The card's evidence is tokenized with its omission offsets as boundaries, so the pieces either side
    of a cut are never one token (`v1-e06-t16`).
    """
    edges = [0, *boundaries, len(text)]
    return [
        _Token(match.group(), match.start())
        for start, end in zip(edges, edges[1:], strict=False)
        for match in _TOKEN.finditer(text, start, end)
    ]


def _anchors_shown_inside_words(card: Card, cuts: Sequence[int], body_text: str) -> list[int]:
    """Each interpolation anchor inside one of the card's words that the body shows split there.

    Such an anchor is a token boundary beside the omission offsets (`v1-e06-t17`), so the body's
    "le[s]vee" is the card's "le" and "vee" with an interpolation between them. It is one only where the
    body shows the word's two pieces either side of a bracketed group: a body that leaves the
    interpolation out shows the source's word whole, and the card's word stays whole to match it.
    """
    words = _tokens(card.evidence_text, cuts)
    shown: list[int] = []
    for item in card.interpolations:
        word = next((token for token in words if token.start < item.anchor < token.end), None)
        if word is None:
            continue
        before = re.escape(card.evidence_text[word.start : item.anchor])
        after = re.escape(card.evidence_text[item.anchor : word.end])
        if re.search(rf"{before}\[[^\[\]]*\]{after}", body_text):
            shown.append(item.anchor)
    return shown


def _marker_signs(marker: Sequence[str]) -> tuple[tuple[str, ...], ...]:
    """The profile's marker without the whitespace either side (" … " is "…"), the signs a body's marker
    is read by; and the typed "..." beside "…" (the coach's decision of 2026-11-13)."""
    start, end = 0, len(marker)
    while start < end and marker[start].isspace():
        start += 1
    while end > start and marker[end - 1].isspace():
        end -= 1
    sign = tuple(marker[start:end])
    return (sign, (_TYPED_ELLIPSIS,)) if sign == (_ELLIPSIS,) else (sign,)


def _sign_width(tokens: Sequence[_Token], index: int, signs: Sequence[Sequence[str]]) -> int:
    """How many tokens from ``index`` spell one of ``signs``; 0 if none does."""
    for sign in signs:
        if sign and [token.text for token in tokens[index : index + len(sign)]] == list(sign):
            return len(sign)
    return 0


@dataclass(frozen=True, slots=True)
class _Hunk:
    """Card tokens ``[removed_start, removed_end)`` replaced by body tokens ``[added_start, added_end)``."""

    removed_start: int
    removed_end: int
    added_start: int
    added_end: int


def _units(tokens: list[_Token], signs: Sequence[Sequence[str]]) -> tuple[list[_Token], list[int]]:
    """``tokens`` with each omission marker made one unit, and where each unit starts in ``tokens`` (one
    more entry, ``len(tokens)``, closes the last).

    A marker is one of ``signs`` (:func:`_marker_signs`: "…", and "..." typed for it) and all the
    whitespace either side of it (:func:`_marker_width`). The diff compares units, so a marker's own
    spaces cannot be paired with the card's spaces: where they could, two edit scripts are equally
    short, and the one that pairs them reads a word deleted beside a cut as that word moved across it
    (`v1-e06-t15`). The profile's " … " is one such unit, and so is the marker a student typed with
    other spacing, such as two spaces either side (`v1-e06-t16`).
    """
    units: list[_Token] = []
    bounds: list[int] = []
    index = 0
    while index < len(tokens):
        bounds.append(index)
        width = _marker_width(tokens, index, signs)
        if width:
            text = "".join(token.text for token in tokens[index : index + width])
            units.append(_Token(text, tokens[index].start))
            index += width
        else:
            units.append(tokens[index])
            index += 1
    bounds.append(len(tokens))
    return units, bounds


def _marker_width(tokens: Sequence[_Token], index: int, signs: Sequence[Sequence[str]]) -> int:
    """How many tokens from ``index`` are spaces, then one of ``signs``, then spaces; 0 if they are not."""
    end = _past_spaces(tokens, index)
    width = _sign_width(tokens, end, signs)
    if not width:
        return 0
    return _past_spaces(tokens, end + width) - index


def _past_spaces(tokens: Sequence[_Token], index: int) -> int:
    while index < len(tokens) and tokens[index].is_space:
        index += 1
    return index


def _expanded(hunks: list[_Hunk], removed_bounds: Sequence[int], added_bounds: Sequence[int]) -> list[_Hunk]:
    """Hunks over units, as hunks over the tokens the units are made of."""
    return [
        _Hunk(
            removed_bounds[hunk.removed_start],
            removed_bounds[hunk.removed_end],
            added_bounds[hunk.added_start],
            added_bounds[hunk.added_end],
        )
        for hunk in hunks
    ]


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


def _same_text(hunk: _Hunk, removed: Sequence[_Token], added: Sequence[_Token]) -> bool:
    """True when the hunk's card and body characters are the same, and only where tokens break differs:
    the body runs two of the card's tokens into one where the card has a cut and the body no marker."""
    return (
        hunk.removed_start < hunk.removed_end
        and hunk.added_start < hunk.added_end
        and "".join(token.text for token in removed[hunk.removed_start : hunk.removed_end])
        == "".join(token.text for token in added[hunk.added_start : hunk.added_end])
    )


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


@dataclass(frozen=True, slots=True)
class _Added:
    """What a hunk adds that the policy can allow: at most one interpolation's text, and its markers."""

    interpolation: str | None
    markers: int
    nothing: bool
    """True when the hunk adds no token at all: it only removes."""


class _Classifier:
    def __init__(
        self,
        card: Card,
        evidence: list[_Token],
        body: list[_Token],
        whole_marker: list[str],
        signs: tuple[tuple[str, ...], ...],
    ) -> None:
        self._card = card
        self._evidence = evidence
        self._body = body
        self._whole_marker = whole_marker
        self._signs = signs
        self._cuts = omission_offsets(card)
        self._omissions = frozenset(self._cuts)

    def classify(self, hunks: list[_Hunk]) -> BodyComparison:
        edits: list[ManualEdit] = []
        interpolations: list[BodyInterpolation] = []
        deletions: list[CharacterRange] = []
        hidden: list[HiddenCut] = []
        # The card's cuts some hunk takes in: shown by its marker, hidden there, or inside a manual edit.
        reached: set[int] = set()
        for hunk in hunks:
            removed = self._removed(hunk)
            cuts = [cut for cut in self._cuts if removed.start <= cut <= removed.end]
            reached.update(cuts)
            body_at = self._range(self._body, hunk.added_start, hunk.added_end, self._body_length).start
            if _same_text(hunk, self._evidence, self._body):
                # The body repeats the card's characters here, so a cut sits as far into the body's run
                # as the card's tokens before it are long.
                hidden.extend(HiddenCut(cut, body_at + self._length_before(hunk, cut)) for cut in cuts)
                continue
            added = self._added(hunk)
            if added is None or not (cuts and not added.markers or self._allows(added, removed)):
                rest = self._without_the_cards_marker(hunk)
                edits.append(
                    ManualEdit(
                        self._removed(rest),
                        self._range(self._body, rest.added_start, rest.added_end, self._body_length),
                    )
                )
                continue
            if cuts and not added.markers:
                # A cut is always shown: whatever else this hunk does where the card has a cut, and
                # whitespace alone included, it draws no marker there.
                hidden.extend(HiddenCut(cut, body_at) for cut in cuts)
            if removed.start < removed.end:
                deletions.append(removed)
            if added.interpolation is not None:
                interpolations.append(self._interpolation(added.interpolation, removed))
        hidden.extend(
            HiddenCut(cut, self._body_offset(hunks, cut)) for cut in self._cuts if cut not in reached
        )
        return BodyComparison(
            tuple(edits),
            tuple(interpolations),
            tuple(deletions),
            tuple(sorted(hidden, key=lambda cut: cut.evidence_offset)),
        )

    def _length_before(self, hunk: _Hunk, cut: int) -> int:
        """How many characters the hunk's card tokens hold before ``cut``, a token boundary inside it."""
        removed = self._evidence[hunk.removed_start : hunk.removed_end]
        return sum(len(token.text) for token in removed if token.end <= cut)

    def _body_offset(self, hunks: list[_Hunk], cut: int) -> int:
        """Where the body shows the card's text at ``cut``, a cut no hunk takes in."""
        index = next(index for index, token in enumerate(self._evidence) if token.start == cut)
        shift = sum(
            (hunk.added_end - hunk.added_start) - (hunk.removed_end - hunk.removed_start)
            for hunk in hunks
            if hunk.removed_end <= index
        )
        position = index + shift
        return self._body[position].start if position < len(self._body) else self._body_length

    def _removed(self, hunk: _Hunk) -> CharacterRange:
        return self._range(
            self._evidence, hunk.removed_start, hunk.removed_end, len(self._card.evidence_text)
        )

    def _without_the_cards_marker(self, hunk: _Hunk) -> _Hunk:
        """A manual edit's hunk without the whole marker it adds at either end where the card has a cut.

        That marker is the card's own, drawn where the renderer drew it; the edit is what is left. Only
        a hunk the policy already refuses is narrowed, and the rest still holds what made it refused,
        so this changes the ranges a manual edit reports, never whether one is reported.
        """
        a0, a1, b0, b1 = hunk.removed_start, hunk.removed_end, hunk.added_start, hunk.added_end
        width = len(self._whole_marker)
        if not width:
            return hunk
        if self._spells_the_marker(b0) and self._removed(_Hunk(a0, a0, b0, b0)).start in self._omissions:
            b0 += width
        if (
            b1 - b0 >= width
            and self._spells_the_marker(b1 - width)
            and self._removed(_Hunk(a1, a1, b1, b1)).start in self._omissions
        ):
            b1 -= width
        return _Hunk(a0, a1, b0, b1)

    def _spells_the_marker(self, start: int) -> bool:
        width = len(self._whole_marker)
        return [token.text for token in self._body[start : start + width]] == self._whole_marker

    @property
    def _body_length(self) -> int:
        return self._body[-1].end if self._body else 0

    @staticmethod
    def _range(tokens: list[_Token], start: int, end: int, length: int) -> CharacterRange:
        if start < end:
            return CharacterRange(tokens[start].start, tokens[end - 1].end)
        offset = tokens[start].start if start < len(tokens) else length
        return CharacterRange(offset, offset)

    def _added(self, hunk: _Hunk) -> _Added | None:
        """What the hunk adds, or None when it adds anything but whitespace, markers and one
        interpolation."""
        added = self._body[hunk.added_start : hunk.added_end]
        interpolations: list[str] = []
        markers = 0
        index = 0
        while index < len(added):
            width = _sign_width(added, index, self._signs)
            if width:
                markers += 1
                index += width
                continue
            token = added[index]
            if token.is_bracketed:
                try:
                    interpolations.append(_INTERPOLATED_TEXT.validate_python(token.text[1:-1]))
                except ValidationError:
                    return None
            elif not token.is_space:
                return None
            index += 1
        if len(interpolations) > 1:
            return None
        return _Added(interpolations[0] if interpolations else None, markers, not added)

    def _allows(self, added: _Added, removed: CharacterRange) -> bool:
        """True when the policy allows the hunk: it only removes, or what it adds is a marker or an
        interpolation (whitespace alone is not), and a marker it adds stands where text was removed."""
        if not (added.nothing or added.interpolation is not None or added.markers):
            return False
        return not (added.markers and removed.start == removed.end and removed.start not in self._omissions)

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

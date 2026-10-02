"""What an edit does to a card: §8 step 7 as a pure function.

:func:`apply_edit` takes a card, an operation from :mod:`debate_core.evidence.edits` and the card's
snapshot, and returns the edited card, or raises. It saves nothing and verifies nothing:
:class:`~debate_core.application.card_edit_service.CardEditService` re-verifies the result and saves
it only if it is VERIFIED.

## Every accepted edit re-cuts the card from its snapshot

No edit touches ``evidence_text``. Each one works out which snapshot ranges the card should quote and
which snapshot characters each span should mark, and then the card is cut again, exactly as a new card
is: :class:`~debate_core.evidence.extractor.EvidenceExtractor` slices the snapshot,
:class:`~debate_core.evidence.markup.CardMarkup` checks the markup against the slices, and
:func:`~debate_core.evidence.card_mapping.place_evidence_on_card` sets the envelope, the omissions, the
text and the spans. An edit therefore cannot produce text the snapshot does not hold at those offsets,
and the omissions come out canonical without anything here making them so: a deletion at an edge of
the quotation is a smaller envelope, one inside it is an omission, and one touching an omission joins
it.

## Deletions, step by step

1. The deleted evidence-text range is mapped to the snapshot ranges it was cut from
   (:func:`~debate_core.evidence.card_mapping.snapshot_ranges_of`, the one place that arithmetic
   lives), and those ranges are taken out of the card's quoted ranges.
2. **Markup is carried across in snapshot offsets.** Each span is mapped to the snapshot characters it
   marks, and the deleted ones are taken out. A span that lost all its text is dropped, and its
   purpose with it. A span that lost part keeps the rest and its purpose. A span the deletion cut
   through the middle becomes two spans, one per side, each with the span's style and purpose,
   because a card span never marks across a cut.
3. **Interpolations move with the quotation.** An anchor before the deletion stays. One after it moves
   back by the length deleted. One at either edge of the deletion lands on the seam. One strictly
   inside the deletion would have nowhere to go, and two at opposite edges would land on one place, so
   either refuses the deletion with :class:`~debate_core.evidence.edits.InterpolationBlocksDeletion`:
   remove the interpolation first.
4. **The text the deletion removed is checked for a negation**
   (:func:`~debate_core.evidence.negation.removes_negation`). A hit is a :class:`NegationFlag` on the
   outcome naming the omission that now holds it, or none when the deletion shrank the envelope. It
   never refuses the edit.

## Every edit does what it says and nothing else

After the re-cut, the new ``evidence_text`` must be the old one with exactly the deleted characters
gone, or unchanged for any other kind of edit. Re-cutting is what makes the text verbatim; this check
is what makes it the text the student was looking at when they made the edit. They differ when the
stored quotation does not match its snapshot. A same-length alteration passes the card's own
invariants, so it can be stored, and re-cutting would silently replace it with the snapshot's text
while the edit "succeeded". The verifier cannot see that: whatever is cut from a snapshot verifies.
Such an edit is refused with ``QUOTATION_DOES_NOT_MATCH_SNAPSHOT``, and the card stays as it is for
the verifier to report.

## Refused, never repaired

An edit that does not fit the card is refused with a typed
:class:`~debate_core.evidence.edits.EvidenceEditRefused`: never clamped to the text, never merged with
a neighbour, never partly applied. Insertions, substitutions and moves are refused by kind
(:class:`~debate_core.evidence.edits.ForbiddenEvidenceEdit`) before anything else is looked at.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

from pydantic import ValidationError

from debate_core.domain import (
    Card,
    CardOmission,
    CardSpan,
    Interpolation,
    SourceSnapshot,
    SpanPurpose,
    SpanStyle,
)
from debate_core.evidence.card_mapping import place_evidence_on_card, snapshot_ranges_of
from debate_core.evidence.edits import (
    FORBIDDEN_EDIT_KINDS,
    AddInterpolation,
    DeleteRange,
    EditCite,
    EditKind,
    EditProblem,
    EditTag,
    EvidenceEdit,
    ForbiddenEvidenceEdit,
    InsertText,
    InterpolationBlocksDeletion,
    InvalidEvidenceEdit,
    MoveText,
    RemoveInterpolation,
    ReplaceText,
    SetMarkup,
    kind_of,
)
from debate_core.evidence.extractor import EvidenceExtractor
from debate_core.evidence.markup import CardMarkup, EvidenceMarkupSpan, InvalidMarkup
from debate_core.evidence.negation import removes_negation
from debate_core.evidence.selection import EvidenceSelection
from debate_core.evidence.snapshot_text import SnapshotText

__all__ = ["EditedCard", "NegationFlag", "apply_edit"]

type _Ranges = tuple[tuple[int, int], ...]

_EXTRACTOR = EvidenceExtractor()


@dataclass(frozen=True, slots=True)
class NegationFlag:
    """A deletion took out a word that negates (:mod:`debate_core.evidence.negation`).

    ``omission`` is the card's omission that now holds the removed text, in snapshot offsets. It is
    ``None`` when the deletion was at an edge of the quotation, which shrinks the envelope and leaves no
    omission to point at. Holds no text: whoever shows the flag reads the omission from the snapshot.
    """

    omission: CardOmission | None


@dataclass(frozen=True, slots=True)
class EditedCard:
    """The card an accepted edit produces: cut again from its snapshot, ``UNVERIFIED``, not saved."""

    card: Card
    kind: EditKind
    negation_flag: NegationFlag | None = None


@dataclass(frozen=True, slots=True)
class _Mark:
    """A span carried in snapshot offsets: the pieces it marks, each inside one kept piece of text."""

    pieces: _Ranges
    style: SpanStyle
    purpose: SpanPurpose | None


def apply_edit(
    card: Card, edit: EvidenceEdit, snapshot: SourceSnapshot, snapshot_text: SnapshotText
) -> EditedCard:
    """Return what ``edit`` makes of ``card``, cut again from ``snapshot``, or raise.

    ``snapshot_text`` must come from a verified load of ``snapshot`` (the extractor checks it belongs
    to the record). Raises :class:`~debate_core.evidence.edits.ForbiddenEvidenceEdit` for an insertion,
    substitution or move, :class:`~debate_core.evidence.edits.InterpolationBlocksDeletion` for a
    deletion an interpolation is in the way of, and
    :class:`~debate_core.evidence.edits.InvalidEvidenceEdit` for an edit that does not fit the card.
    Raises :class:`ValueError` if ``snapshot`` is not the card's.
    """
    kind = kind_of(edit)
    if kind in FORBIDDEN_EDIT_KINDS:
        raise ForbiddenEvidenceEdit(kind)
    if card.snapshot_id != snapshot.snapshot_id:
        raise ValueError(
            f"card {card.card_id} quotes snapshot {card.snapshot_id}, not {snapshot.snapshot_id}"
        )
    kept = card.quoted_ranges
    marks = _marks_of(card, card.spans)
    match edit:
        case DeleteRange():
            return _delete(card, edit, snapshot, snapshot_text)
        case SetMarkup():
            for span in edit.spans:
                _check_within_text(
                    kind, card, span.end_offset, f"span [{span.start_offset}, {span.end_offset})"
                )
            marks = _marks_of(card, edit.spans)
            edited = _recut(kind, card, snapshot, snapshot_text, kept, marks, card.interpolations)
        case AddInterpolation():
            interpolations = _with_interpolation(card, edit)
            edited = _recut(kind, card, snapshot, snapshot_text, kept, marks, interpolations)
        case RemoveInterpolation():
            interpolations = _without_interpolation(card, edit)
            edited = _recut(kind, card, snapshot, snapshot_text, kept, marks, interpolations)
        case EditTag():
            retagged = _evolved(kind, EditProblem.INVALID_TAG, card, tag=edit.tag)
            edited = _recut(kind, retagged, snapshot, snapshot_text, kept, marks, card.interpolations)
        case EditCite():
            _check_cite_claims_nothing(card, edit)
            recited = card.evolve(citation=edit.citation)
            edited = _recut(kind, recited, snapshot, snapshot_text, kept, marks, card.interpolations)
        case InsertText() | ReplaceText() | MoveText():  # pragma: no cover - refused above, by kind
            raise ForbiddenEvidenceEdit(kind)
    _check_quotation(kind, edited, card.evidence_text)
    return EditedCard(edited, kind)


def _delete(
    card: Card, edit: DeleteRange, snapshot: SourceSnapshot, snapshot_text: SnapshotText
) -> EditedCard:
    kind = edit.kind
    _check_within_text(kind, card, edit.end, f"deletion [{edit.start}, {edit.end})")
    removed = snapshot_ranges_of(card, edit.start, edit.end)
    kept = _without(card.quoted_ranges, removed)
    if not kept:
        raise InvalidEvidenceEdit(
            kind,
            EditProblem.DELETES_ALL_EVIDENCE,
            "the deletion would leave nothing quoted; delete the card instead",
        )
    interpolations = _interpolations_after_deletion(card, edit)
    marks = tuple(
        _Mark(_without(mark.pieces, removed), mark.style, mark.purpose)
        for mark in _marks_of(card, card.spans)
    )
    edited = _recut(kind, card, snapshot, snapshot_text, kept, marks, interpolations)
    _check_quotation(kind, edited, card.evidence_text[: edit.start] + card.evidence_text[edit.end :])
    flag = _negation_flag(edited, removed, snapshot_text)
    return EditedCard(edited, kind, flag)


def _marks_of(card: Card, spans: tuple[CardSpan, ...]) -> tuple[_Mark, ...]:
    """Spans in evidence-text offsets, as the snapshot characters they mark."""
    return tuple(
        _Mark(snapshot_ranges_of(card, span.start_offset, span.end_offset), span.style, span.purpose)
        for span in spans
    )


def _without(ranges: _Ranges, removed: _Ranges) -> _Ranges:
    """``ranges`` with every character in ``removed`` taken out; both sorted and non-overlapping."""
    remaining: list[tuple[int, int]] = []
    for start, end in ranges:
        cursor = start
        for cut_start, cut_end in removed:
            if cut_end <= cursor or cut_start >= end:
                continue
            if cut_start > cursor:
                remaining.append((cursor, cut_start))
            cursor = max(cursor, cut_end)
        if cursor < end:
            remaining.append((cursor, end))
    return tuple(remaining)


def _recut(
    kind: EditKind,
    card: Card,
    snapshot: SourceSnapshot,
    snapshot_text: SnapshotText,
    kept: _Ranges,
    marks: tuple[_Mark, ...],
    interpolations: tuple[Interpolation, ...],
) -> Card:
    """The card quoting ``kept`` of the snapshot, marked up by ``marks``, cut exactly as a new card is."""
    evidence = _EXTRACTOR.extract(snapshot, snapshot_text, EvidenceSelection.of_offsets(*kept))
    try:
        markup = CardMarkup(
            evidence,
            tuple(
                EvidenceMarkupSpan(start, end, mark.style, mark.purpose)
                for mark in marks
                for start, end in mark.pieces
            ),
        )
    except InvalidMarkup as refused:
        raise InvalidEvidenceEdit(kind, EditProblem.INVALID_MARKUP, str(refused)) from None
    return place_evidence_on_card(card, markup).evolve(interpolations=interpolations)


def _check_within_text(kind: EditKind, card: Card, end: int, what: str) -> None:
    if end > len(card.evidence_text):
        raise InvalidEvidenceEdit(
            kind,
            EditProblem.OUTSIDE_EVIDENCE,
            f"{what} runs past the end of the {len(card.evidence_text)}-character evidence_text",
        )


def _check_quotation(kind: EditKind, edited: Card, expected: str) -> None:
    """The re-cut quotation is exactly what the student saw, less what they deleted."""
    if edited.evidence_text != expected:
        raise InvalidEvidenceEdit(
            kind,
            EditProblem.QUOTATION_DOES_NOT_MATCH_SNAPSHOT,
            "cut again from its snapshot, the card does not quote what its stored evidence_text says; "
            "it needs verifying, not editing",
        )


def _interpolations_after_deletion(card: Card, edit: DeleteRange) -> tuple[Interpolation, ...]:
    """Every interpolation moved to where its anchor lands once ``edit`` is applied, or a refusal."""
    inside = [item.anchor for item in card.interpolations if edit.start < item.anchor < edit.end]
    if inside:
        raise InterpolationBlocksDeletion(
            edit.kind, inside, f"interpolations anchored at {inside} are inside the deletion"
        )
    deleted_length = edit.end - edit.start
    moved = tuple(
        item if item.anchor <= edit.start else item.evolve(anchor=item.anchor - deleted_length)
        for item in card.interpolations
    )
    for previous, item in itertools.pairwise(moved):
        if previous.anchor == item.anchor:
            raise InterpolationBlocksDeletion(
                edit.kind,
                (edit.start, edit.end),
                f"the interpolations anchored at {edit.start} and {edit.end} would meet at one place",
            )
    return moved


def _with_interpolation(card: Card, edit: AddInterpolation) -> tuple[Interpolation, ...]:
    kind = edit.kind
    _check_within_text(kind, card, edit.anchor, f"anchor {edit.anchor}")
    if any(item.anchor == edit.anchor for item in card.interpolations):
        raise InvalidEvidenceEdit(
            kind,
            EditProblem.INTERPOLATION_ALREADY_THERE,
            f"an interpolation is already anchored at {edit.anchor}",
        )
    try:
        added = Interpolation(anchor=edit.anchor, text=edit.text)
    except ValidationError as refused:
        problems = "; ".join(error["msg"] for error in refused.errors())
        raise InvalidEvidenceEdit(kind, EditProblem.INVALID_INTERPOLATION, problems) from None
    return tuple(sorted((*card.interpolations, added), key=lambda item: item.anchor))


def _without_interpolation(card: Card, edit: RemoveInterpolation) -> tuple[Interpolation, ...]:
    remaining = tuple(item for item in card.interpolations if item.anchor != edit.anchor)
    if len(remaining) == len(card.interpolations):
        raise InvalidEvidenceEdit(
            edit.kind, EditProblem.NO_INTERPOLATION_THERE, f"no interpolation is anchored at {edit.anchor}"
        )
    return remaining


def _evolved(kind: EditKind, problem: EditProblem, card: Card, **changes: object) -> Card:
    try:
        return card.evolve(**changes)
    except ValidationError as refused:
        problems = "; ".join(error["msg"] for error in refused.errors())
        raise InvalidEvidenceEdit(kind, problem, problems) from None


def _check_cite_claims_nothing(card: Card, edit: EditCite) -> None:
    """A cite field the student changed may not arrive marked verified."""
    before = card.citation.model_dump()
    after = edit.citation.model_dump()
    claimed = [name for name, field in after.items() if field != before[name] and field["verified"]]
    if claimed:
        raise InvalidEvidenceEdit(
            edit.kind,
            EditProblem.CITATION_CLAIMS_VERIFICATION,
            f"changed cite fields {claimed} are marked verified; only the citation service verifies one",
        )


def _negation_flag(edited: Card, removed: _Ranges, snapshot_text: SnapshotText) -> NegationFlag | None:
    if not removes_negation(snapshot_text, removed):
        return None
    first, last = removed[0][0], removed[-1][1]
    holding = [
        omission
        for omission in edited.omitted_ranges
        if omission.start_offset <= first and last <= omission.end_offset
    ]
    return NegationFlag(holding[0] if holding else None)

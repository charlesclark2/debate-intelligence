"""What a student may ask to do to a card, in the coordinates an editor shows them.

Architecture proposal §8 step 7: a student may cut quoted evidence, mark it up, and add bracketed
words of their own beside it, and may rewrite the tag and the cite. They may not put words in the
source's mouth. This module is the vocabulary an editor sends; :mod:`debate_core.evidence.edit_policy`
decides what each one does to a card, and
:class:`~debate_core.application.card_edit_service.CardEditService` re-verifies and saves the result.

## Coordinates

Every offset here is into the card's ``evidence_text``, the quotation exactly as the student sees
it: no ellipsis, no brackets, the kept pieces joined with nothing. A student never sees snapshot
offsets, so never sends one. The policy maps evidence-text offsets back to the snapshot through
:func:`~debate_core.evidence.card_mapping.snapshot_ranges_of`, the one place that arithmetic lives.

## The vocabulary includes what is refused

:class:`InsertText`, :class:`ReplaceText` and :class:`MoveText` are what an editor would send for
typing into a quotation, overtyping it, or dragging a passage elsewhere. They are in the vocabulary
so that the refusal is explicit and tested, not an accident of a missing case:
:func:`~debate_core.evidence.edit_policy.allowed_edit` raises :class:`ForbiddenEvidenceEdit` for each,
by kind, without reading its payload. Nothing stores a forbidden operation's text: not the card, not
the edit log (refused edits are not logged), not the error, whose message names only the kind. The
text fields are left out of ``repr`` so a stray log line does not print them either.

Reordering is refused here, not by a validator on the card. A card is one envelope read left to
right (ADR-0018), so a reordered card cannot be written down at all; ``MoveText`` exists only so an
editor that offers dragging gets a typed answer.

| Kind | Operation | Allowed |
|---|---|---|
| ``delete_range`` | :class:`DeleteRange` | yes: a smaller envelope at an edge, an omission inside |
| ``set_markup`` | :class:`SetMarkup` | yes: replaces the underlines and highlights |
| ``add_interpolation`` | :class:`AddInterpolation` | yes: bracketed words beside the quotation |
| ``remove_interpolation`` | :class:`RemoveInterpolation` | yes |
| ``edit_tag`` | :class:`EditTag` | yes, with no snapshot and no re-cut |
| ``edit_cite`` | :class:`EditCite` | yes, likewise; a changed field may not claim verification |
| ``insert_text`` | :class:`InsertText` | no: :class:`ForbiddenEvidenceEdit` |
| ``replace_text`` | :class:`ReplaceText` | no: :class:`ForbiddenEvidenceEdit` |
| ``move_text`` | :class:`MoveText` | no: :class:`ForbiddenEvidenceEdit` |
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import ClassVar

from debate_core.domain import CardSpan, Citation
from debate_core.evidence._runtime_checks import is_instance, is_tuple_of

__all__ = [
    "AddInterpolation",
    "DeleteRange",
    "EditCite",
    "EditKind",
    "EditProblem",
    "EditTag",
    "EvidenceEdit",
    "EvidenceEditRefused",
    "ForbiddenEvidenceEdit",
    "InsertText",
    "InterpolationBlocksDeletion",
    "InvalidEvidenceEdit",
    "MoveText",
    "QuotationEdit",
    "RemoveInterpolation",
    "ReplaceText",
    "SetMarkup",
    "TagOrCiteEdit",
    "kind_of",
]


class EditKind(StrEnum):
    """Every kind of edit an editor can send, allowed or not. Recorded in the edit log."""

    DELETE_RANGE = "delete_range"
    SET_MARKUP = "set_markup"
    ADD_INTERPOLATION = "add_interpolation"
    REMOVE_INTERPOLATION = "remove_interpolation"
    EDIT_TAG = "edit_tag"
    EDIT_CITE = "edit_cite"
    INSERT_TEXT = "insert_text"
    REPLACE_TEXT = "replace_text"
    MOVE_TEXT = "move_text"


class EditProblem(StrEnum):
    """Why an allowed kind of edit could not be applied to this card."""

    NOT_AN_EDIT = "not_an_edit"
    """The request is not one of the operations in this module, or a field has the wrong type."""

    NOT_AN_OFFSET = "not_an_offset"
    """An offset is not a non-negative ``int``."""

    EMPTY_DELETION = "empty_deletion"
    """A deletion that removes nothing, or ends before it starts."""

    OUTSIDE_EVIDENCE = "outside_evidence"
    """A range, span or anchor reaches past the end of ``evidence_text``."""

    DELETES_ALL_EVIDENCE = "deletes_all_evidence"
    """A deletion would leave nothing quoted. Deleting the card is a different operation."""

    CARD_HAS_NO_EVIDENCE = "card_has_no_evidence"
    """A quotation edit on a card that quotes nothing yet. Tag and cite edits are not refused."""

    INVALID_MARKUP = "invalid_markup"
    """The new markup overlaps itself within a style, or a highlight is not underlined."""

    INVALID_INTERPOLATION = "invalid_interpolation"
    """The interpolated text is empty or holds a square bracket."""

    INTERPOLATION_ALREADY_THERE = "interpolation_already_there"
    """An interpolation is already anchored at that offset; edit that one instead."""

    NO_INTERPOLATION_THERE = "no_interpolation_there"
    """No interpolation is anchored at the offset given for removal."""

    INVALID_TAG = "invalid_tag"
    """The tag is empty."""

    CITATION_CLAIMS_VERIFICATION = "citation_claims_verification"
    """A cite field the student changed is marked verified. Only the citation service verifies."""

    QUOTATION_DOES_NOT_MATCH_SNAPSHOT = "quotation_does_not_match_snapshot"
    """Cut again from the snapshot, the card does not quote what it says it does, so an edit made
    against its stored text would not do what the student saw."""


class EvidenceEditRefused(ValueError):
    """An edit that was not applied. Nothing was saved and nothing was logged.

    ``kind`` is the kind of edit refused, or ``None`` when the request was not an edit at all. The
    message never quotes evidence, a tag, a cite or an operation's payload.
    """

    def __init__(self, kind: EditKind | None, detail: str) -> None:
        self.kind = kind
        """The kind of edit refused, or ``None`` when the request was not an edit."""
        super().__init__(f"{kind.value if kind is not None else 'edit'} refused: {detail}")


class ForbiddenEvidenceEdit(EvidenceEditRefused):
    """An edit that would insert, substitute or reorder quoted characters.

    Raised for the kind, never for its content: an insertion of nothing is still an insertion.
    """

    def __init__(self, kind: EditKind) -> None:
        super().__init__(
            kind,
            "quoted evidence can only be cut (delete_range), marked up (set_markup) or given a bracketed "
            "interpolation beside it (add_interpolation); its characters are never inserted, replaced or "
            "moved",
        )


class InterpolationBlocksDeletion(EvidenceEditRefused):
    """A deletion that would remove the place an interpolation is anchored.

    An anchor strictly inside the deleted range would have nowhere to go, and two anchors either side
    of it would land on the same place. Remove the interpolation first, then delete.
    """

    def __init__(self, kind: EditKind, anchors: Sequence[int], detail: str) -> None:
        self.anchors = tuple(anchors)
        """The evidence-text anchors of the interpolations in the way."""
        super().__init__(kind, f"{detail}; remove the interpolation first, then delete")


class InvalidEvidenceEdit(EvidenceEditRefused):
    """An allowed kind of edit that does not fit this card."""

    def __init__(self, kind: EditKind | None, problem: EditProblem, detail: str) -> None:
        self.problem = problem
        """What was wrong, for a caller that maps refusals to messages without parsing them."""
        super().__init__(kind, f"{problem.value}: {detail}")


def _check_offset(kind: EditKind, name: str, value: object) -> None:
    # bool is an int subclass; True is not an offset.
    if type(value) is not int or value < 0:
        raise InvalidEvidenceEdit(kind, EditProblem.NOT_AN_OFFSET, f"{name} must be a non-negative int")


@dataclass(frozen=True, slots=True)
class DeleteRange:
    """Cut ``evidence_text[start:end]`` out of the quotation.

    At either edge of the quotation it shrinks the envelope; inside, it becomes an omitted range,
    joining any omission it touches (ADR-0018). The snapshot is not changed and the cut text is not
    stored: the card records where it was, and the exporter decides how to show the cut.
    """

    kind: ClassVar[EditKind] = EditKind.DELETE_RANGE
    start: int
    end: int

    def __post_init__(self) -> None:
        _check_offset(self.kind, "start", self.start)
        _check_offset(self.kind, "end", self.end)
        if self.end <= self.start:
            raise InvalidEvidenceEdit(
                self.kind, EditProblem.EMPTY_DELETION, f"[{self.start}, {self.end}) removes nothing"
            )


@dataclass(frozen=True, slots=True)
class SetMarkup:
    """Replace the card's underlines and highlights with ``spans``, in evidence-text offsets.

    A span that runs across a cut is kept as one span per kept piece, each with the same style and
    purpose, because a card span never marks across a cut (`v1-e03-t07`).
    """

    kind: ClassVar[EditKind] = EditKind.SET_MARKUP
    spans: tuple[CardSpan, ...]

    def __post_init__(self) -> None:
        if not is_tuple_of(self.spans, CardSpan):
            raise InvalidEvidenceEdit(self.kind, EditProblem.NOT_AN_EDIT, "spans must be a tuple of CardSpan")


@dataclass(frozen=True, slots=True)
class AddInterpolation:
    """Add bracketed words of the student's own before ``evidence_text[anchor]``.

    ``text`` is given without brackets; the renderer adds them. It is stored beside the quotation,
    never in it, and is not verified.
    """

    kind: ClassVar[EditKind] = EditKind.ADD_INTERPOLATION
    anchor: int
    text: str

    def __post_init__(self) -> None:
        _check_offset(self.kind, "anchor", self.anchor)
        if not is_instance(self.text, str):
            raise InvalidEvidenceEdit(self.kind, EditProblem.NOT_AN_EDIT, "text must be a str")


@dataclass(frozen=True, slots=True)
class RemoveInterpolation:
    """Remove the interpolation anchored at ``anchor``."""

    kind: ClassVar[EditKind] = EditKind.REMOVE_INTERPOLATION
    anchor: int

    def __post_init__(self) -> None:
        _check_offset(self.kind, "anchor", self.anchor)


@dataclass(frozen=True, slots=True)
class EditTag:
    """Replace the card's tag. The tag is the student's own claim, not quoted evidence."""

    kind: ClassVar[EditKind] = EditKind.EDIT_TAG
    tag: str = field(repr=False)

    def __post_init__(self) -> None:
        if not is_instance(self.tag, str):
            raise InvalidEvidenceEdit(self.kind, EditProblem.NOT_AN_EDIT, "tag must be a str")


@dataclass(frozen=True, slots=True)
class EditCite:
    """Replace the card's cite.

    A field the student changes may not arrive marked verified: only the citation service verifies a
    cite field (E06). A changed required field is therefore unverified, and the card is saved
    ``UNVERIFIED`` (``CITATION_UNVERIFIED``) until the citation service re-resolves it
    (`v1-e06-t01` ac5).
    """

    kind: ClassVar[EditKind] = EditKind.EDIT_CITE
    citation: Citation = field(repr=False)

    def __post_init__(self) -> None:
        if not is_instance(self.citation, Citation):
            raise InvalidEvidenceEdit(self.kind, EditProblem.NOT_AN_EDIT, "citation must be a Citation")


@dataclass(frozen=True, slots=True)
class InsertText:
    """Type ``text`` into the quotation before ``evidence_text[at]``. Always refused."""

    kind: ClassVar[EditKind] = EditKind.INSERT_TEXT
    at: int
    text: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class ReplaceText:
    """Overtype ``evidence_text[start:end]`` with ``text``. Always refused, even when ``text`` is
    empty (send a :class:`DeleteRange`) or equal to what it replaces."""

    kind: ClassVar[EditKind] = EditKind.REPLACE_TEXT
    start: int
    end: int
    text: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class MoveText:
    """Move ``evidence_text[start:end]`` to before ``evidence_text[to]``. Always refused."""

    kind: ClassVar[EditKind] = EditKind.MOVE_TEXT
    start: int
    end: int
    to: int


type EvidenceEdit = (
    DeleteRange
    | SetMarkup
    | AddInterpolation
    | RemoveInterpolation
    | EditTag
    | EditCite
    | InsertText
    | ReplaceText
    | MoveText
)
"""Any operation an editor can send."""

type QuotationEdit = DeleteRange | SetMarkup | AddInterpolation | RemoveInterpolation
"""The allowed edits to what a card quotes or how it is marked: each re-cuts from the snapshot."""

type TagOrCiteEdit = EditTag | EditCite
"""The allowed edits to the student's own words: they need no snapshot and never re-cut."""

_EDIT_TYPES = (
    DeleteRange,
    SetMarkup,
    AddInterpolation,
    RemoveInterpolation,
    EditTag,
    EditCite,
    InsertText,
    ReplaceText,
    MoveText,
)


def kind_of(edit: object) -> EditKind:
    """The kind of ``edit``, or :class:`InvalidEvidenceEdit` when it is not an operation from this module.

    Fails closed: a request of any other type is refused rather than ignored.
    """
    for edit_type in _EDIT_TYPES:
        if is_instance(edit, edit_type):
            return edit_type.kind
    raise InvalidEvidenceEdit(
        None, EditProblem.NOT_AN_EDIT, f"a {type(edit).__name__} is not an evidence edit"
    )

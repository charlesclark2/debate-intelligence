"""What cutting a card takes and gives back (v1-e06-t02): the request, the result, why a card is UNVERIFIED.

:meth:`~debate_core.application.card_service.CardService.cut_card` takes a :class:`CutRequest` and
returns a :class:`CutResult`: the card as saved, the evidence verifier's verdict on it, the provenance
of every model call that shaped it, and a :class:`CardFailure` for each reason it is not VERIFIED.

## Failure reasons

Every failure after the snapshot exists is a reason on a saved UNVERIFIED card, never an exception
and never a card that looks finished (architecture proposal §8, the hard failure rule). Each is one
:class:`CardFailureReason`, a stable code a program reads:

* ``MODEL_OUTPUT_INVALID``: the model's selection or markup answer, and its one repair, were refused
  by the structured-output guard.
* ``SPAN_MISMATCH``: the places the model named could not be cut from the snapshot, or the verifier
  did not reproduce the evidence at the card's offsets (``TEXT_MISMATCH``, ``SPAN_OUT_OF_RANGE``).
* ``CITATION_UNVERIFIED``: a required cite field is missing or unverified; ``fields`` names them.
* ``EVIDENCE_UNVERIFIED``: the verifier refused the card for any other reason, named in
  ``verifier_code``. After a model failure this is usually ``CARD_INCOMPLETE``: the consequence, kept
  beside its cause so the list says everything the verifier found.

A detail never quotes evidence, a tag or a model's answer: it holds prompt ids, codes, field names,
offsets and the verifier's own details, which hold none either.

## The rejection

A snapshot whose access status is not ACCESSIBLE is refused with :class:`SourceNotAccessibleError`
before any model call, and no card is made. It is reported under `debate-research fetch`'s code,
``SOURCE_NOT_ACCESSIBLE`` (`v1-e04-t06`), so a program sees one code for one failure.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar, Protocol

from debate_core.application.article_fetch import SOURCE_NOT_ACCESSIBLE_CODE
from debate_core.application.errors import DomainError
from debate_core.application.snapshot_service import LoadedSnapshot
from debate_core.domain import AccessStatus, Card, Ulid, VerificationStatus
from debate_core.domain.card import DEFAULT_FORMAT_PROFILE
from debate_core.domain.citation import CITATION_FIELD_NAMES
from debate_core.domain.provenance import SourcedArtifactMetadata
from debate_core.evidence.selection_contract import GeneratedCardMarkup, GeneratedCardSelection
from debate_core.evidence.verification_types import ReasonCode, VerificationResult

__all__ = [
    "CardFailure",
    "CardFailureReason",
    "CardSelecting",
    "CutRequest",
    "CutResult",
    "SourceNotAccessibleError",
]


class CardFailureReason(StrEnum):
    """Why a cut card is UNVERIFIED. Values are stable: they are written into results and JSON output."""

    MODEL_OUTPUT_INVALID = "MODEL_OUTPUT_INVALID"
    """The model's `card.select` or `card.markup` answer was refused after its one repair."""

    SPAN_MISMATCH = "SPAN_MISMATCH"
    """The selection or markup could not be cut from the snapshot, or the verifier did not reproduce it."""

    CITATION_UNVERIFIED = "CITATION_UNVERIFIED"
    """A required cite field is missing or unverified; the failure names which."""

    EVIDENCE_UNVERIFIED = "EVIDENCE_UNVERIFIED"
    """The verifier refused the card for another reason, which ``verifier_code`` names."""


@dataclass(frozen=True, slots=True)
class CardFailure:
    """One reason a cut card is UNVERIFIED: its code, a sentence for people, and what it is about."""

    reason: CardFailureReason
    detail: str
    """For people. Prompt ids, codes, field names and offsets; never evidence, a tag or a model's words."""
    fields: tuple[str, ...] = ()
    """For ``CITATION_UNVERIFIED``, and only for it: the required cite fields not verified, in cite order."""
    verifier_code: ReasonCode | None = None
    """The verifier's code, when the failure is the verifier's finding."""

    def __post_init__(self) -> None:
        if (self.reason is CardFailureReason.CITATION_UNVERIFIED) != bool(self.fields):
            raise ValueError(
                "a CITATION_UNVERIFIED failure names the cite fields it is about, and no other does"
            )
        unknown = [name for name in self.fields if name not in CITATION_FIELD_NAMES]
        if unknown:
            raise ValueError(f"not cite fields: {', '.join(unknown)}")


@dataclass(frozen=True, slots=True)
class CutRequest:
    """Cut a card for `need` from the stored snapshot `snapshot_id`, for the student `owner_id`.

    `argument` is the argument the need belongs to ("Politics DA"), when the student names one: the
    model is asked for the need within it (:attr:`research_need`). `format_profile` names the team
    profile an exporter renders the card in; the profiles themselves are `v1-e06-t03`'s.
    """

    snapshot_id: Ulid
    need: str
    owner_id: Ulid
    argument: str | None = None
    format_profile: str = DEFAULT_FORMAT_PROFILE
    organization_id: Ulid | None = None

    def __post_init__(self) -> None:
        if not self.need.strip():
            raise ValueError("a research need must say what the card is for")
        if not self.format_profile.strip():
            raise ValueError("a format profile name cannot be blank")

    @property
    def research_need(self) -> str:
        """What the model is asked for: "argument: need", or the need alone when no argument is named."""
        argument = (self.argument or "").strip()
        return f"{argument}: {self.need}" if argument else self.need


@dataclass(frozen=True, slots=True)
class CutResult:
    """A cut card as saved, the verifier's verdict on it, its model provenance, and why it is not VERIFIED.

    Constructed only consistent: the verdict is about this card and states its status, a VERIFIED
    result carries no reason, and an UNVERIFIED one carries at least one.
    """

    card: Card
    verification: VerificationResult
    metadata: tuple[SourcedArtifactMetadata, ...]
    """Each model call that shaped the card, in order: `card.select`, then `card.markup`."""
    reasons: tuple[CardFailure, ...]

    def __post_init__(self) -> None:
        if self.verification.card_id != self.card.card_id:
            raise ValueError(
                f"the verdict is about card {self.verification.card_id}, not {self.card.card_id}"
            )
        if self.verification.status is not self.card.verification_status:
            raise ValueError(
                f"the card's status is {self.card.verification_status}, "
                f"but its verdict says {self.verification.status}"
            )
        if self.verification.status is VerificationStatus.VERIFIED and self.reasons:
            raise ValueError("a VERIFIED card cannot carry a failure reason")
        if self.verification.status is not VerificationStatus.VERIFIED and not self.reasons:
            raise ValueError("an UNVERIFIED card must carry at least one failure reason")

    @property
    def is_verified(self) -> bool:
        """True when the card was saved VERIFIED."""
        return self.verification.is_verified

    @property
    def reason_codes(self) -> tuple[CardFailureReason, ...]:
        """The codes of :attr:`reasons`, in order, without repeats."""
        return tuple(dict.fromkeys(failure.reason for failure in self.reasons))


class SourceNotAccessibleError(DomainError):
    """A card was asked for from a snapshot whose access status is not ACCESSIBLE.

    Raised before any model call; no card is made. Reported under `debate-research fetch`'s
    ``SOURCE_NOT_ACCESSIBLE``, the one code for a source the platform may not cut from.
    """

    ERROR_CODE: ClassVar[str] = SOURCE_NOT_ACCESSIBLE_CODE

    def __init__(self, snapshot_id: Ulid, access_status: AccessStatus) -> None:
        self.snapshot_id = snapshot_id
        """The snapshot asked for."""
        self.access_status = access_status
        """Its recorded access status."""
        super().__init__(
            f"snapshot {snapshot_id} is {access_status.value}, not ACCESSIBLE: no card is cut from it"
        )


class CardSelecting(Protocol):
    """Where a card's evidence is and what to mark in it, as a model answers; checked, never trusted.

    :class:`~debate_core.application.card_selection.CardSelector` is the production one: every answer
    goes through the fail-closed structured-output guard. CardService still cuts what it is given
    from the snapshot and refuses what does not fit, so a selector is never the last check.
    """

    async def select(self, loaded: LoadedSnapshot, research_need: str) -> GeneratedCardSelection:
        """Where in `loaded` the evidence for `research_need` is, with a suggested tag."""
        ...

    async def mark_up(
        self, loaded: LoadedSnapshot, selected: GeneratedCardSelection, research_need: str
    ) -> GeneratedCardMarkup:
        """What to underline and highlight in `selected`."""
        ...

"""The evidence card and its markup.

A :class:`Card` is the platform's output: a tag, a cite, a verbatim quotation, and the underlining
and highlighting a debater reads from. Its invariants exist to make one failure mode impossible —
quoted evidence that is not traceable to a stored snapshot.

Three rules are enforced here, at construction:

1. A card that holds evidence text must say where the text came from: a `snapshot_id` and the
   offsets of the quotation inside that snapshot's normalized text.
2. A card can only be `VERIFIED` if it has everything re-verification needs: the snapshot, the
   `normalizer_version` the offsets were taken under, and at least one marked span.
3. Spans must fall inside the evidence text, and two spans of the same style may not overlap.

The domain deliberately does *not* check that `evidence_text` equals the snapshot slice. That
comparison is the evidence verifier's job (E03): a tampered or edited card has to be constructible
so the verifier can report `TEXT_MISMATCH` on it, rather than blowing up before it can be checked.
"""

from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from debate_core.domain.base import (
    ORGANIZATION_ID_FIELD,
    OWNER_ID_FIELD,
    DomainEntity,
    DomainModel,
    NonEmptyText,
    Sha256Hex,
    Ulid,
    new_id,
)
from debate_core.domain.citation import Citation
from debate_core.domain.enums import ProvenanceMode, SpanPurpose, SpanStyle, VerificationStatus

__all__ = ["Card", "CardSpan"]

#: Format profile applied when a card does not name one. The profiles themselves are declarative
#: config loaded by the renderer (E06), not code.
DEFAULT_FORMAT_PROFILE = "team-default"


class CardSpan(DomainModel):
    """A marked region of a card's evidence.

    Offsets are character positions **into the card's `evidence_text`**, half-open (`start`
    inclusive, `end` exclusive) — not into the snapshot. The renderer marks up the quotation it is
    given, so spans stay correct no matter where in the source the quotation was taken from.
    """

    span_id: Ulid = Field(default_factory=new_id, description="ULID identifying this span.")
    start_offset: int = Field(ge=0, description="Inclusive start character offset into evidence_text.")
    end_offset: int = Field(gt=0, description="Exclusive end character offset into evidence_text.")
    style: SpanStyle = Field(description="How the region is rendered: underlined or highlighted.")
    purpose: SpanPurpose | None = Field(
        default=None, description="What argumentative work the region does, when known."
    )

    @model_validator(mode="after")
    def _check_bounds(self) -> Self:
        if self.start_offset >= self.end_offset:
            raise ValueError(
                f"span start_offset ({self.start_offset}) must be before end_offset ({self.end_offset})"
            )
        return self

    @property
    def length(self) -> int:
        """Number of characters the span covers."""
        return self.end_offset - self.start_offset

    def overlaps(self, other: CardSpan) -> bool:
        """True when this span shares at least one character with `other`."""
        return self.start_offset < other.end_offset and other.start_offset < self.end_offset


class Card(DomainEntity):
    """A piece of evidence cut from a source snapshot.

    `evidence_text` is verbatim: it is extracted from the stored snapshot at
    `[evidence_start_offset:evidence_end_offset]`, never written or paraphrased by a model. A model
    may choose *which* span to cut and may write the `tag`, but the quotation itself only ever
    comes out of the snapshot (architecture proposal §8).

    `provenance_mode` has no default on purpose. Defaulting it would make
    `PUBLISHER_RETRIEVED` — the strongest claim the platform can make about a piece of text — the
    thing that happens when a caller says nothing, which is exactly backwards.

    `verification_status` defaults to `UNVERIFIED`, and only the evidence verifier (E03) promotes
    a card to `VERIFIED`.
    """

    card_id: Ulid = Field(default_factory=new_id, description="ULID primary key.")
    owner_id: Ulid = Field(description=f"{OWNER_ID_FIELD} Required: a card always belongs to a student.")
    organization_id: Ulid | None = Field(default=None, description=ORGANIZATION_ID_FIELD)
    article_id: Ulid = Field(description="The article the evidence was cut from.")
    snapshot_id: Ulid | None = Field(
        default=None, description="The snapshot the evidence was cut from; required once there is evidence."
    )
    tag: NonEmptyText = Field(description="The claim the card is read for, written above the cite.")
    citation: Citation = Field(default_factory=Citation, description="The cite, with per-field provenance.")
    evidence_text: str = Field(
        default="", description="Verbatim quotation taken from the snapshot; empty until extraction runs."
    )
    evidence_start_offset: int | None = Field(
        default=None, ge=0, description="Inclusive start offset of the quotation in the normalized snapshot."
    )
    evidence_end_offset: int | None = Field(
        default=None, gt=0, description="Exclusive end offset of the quotation in the normalized snapshot."
    )
    normalized_text_hash: Sha256Hex | None = Field(
        default=None, description="SHA-256 of the snapshot's normalized text the offsets refer to."
    )
    normalizer_version: NonEmptyText | None = Field(
        default=None, description="Normalizer version the offsets were taken under; needed to re-verify."
    )
    spans: tuple[CardSpan, ...] = Field(
        default=(), description="Underline and highlight regions within evidence_text."
    )
    verification_status: VerificationStatus = Field(
        default=VerificationStatus.UNVERIFIED,
        description="Set to VERIFIED only by the evidence verifier, after reproducing the quotation.",
    )
    provenance_mode: ProvenanceMode = Field(description="Where the evidence text came from.")
    format_profile: NonEmptyText = Field(
        default=DEFAULT_FORMAT_PROFILE, description="Name of the team's formatting profile for export."
    )

    @model_validator(mode="after")
    def _check_evidence_location(self) -> Self:
        """Evidence text and its location in the snapshot must arrive together."""
        has_start = self.evidence_start_offset is not None
        has_end = self.evidence_end_offset is not None
        if has_start != has_end:
            raise ValueError("evidence_start_offset and evidence_end_offset must both be set or both be None")
        if (
            self.evidence_start_offset is not None
            and self.evidence_end_offset is not None
            and self.evidence_start_offset >= self.evidence_end_offset
        ):
            raise ValueError(
                f"evidence_start_offset ({self.evidence_start_offset}) must be before "
                f"evidence_end_offset ({self.evidence_end_offset})"
            )
        if self.evidence_text:
            if self.snapshot_id is None:
                raise ValueError(
                    "a card holding evidence_text must reference the snapshot it was cut from; "
                    "evidence that cannot be traced to a snapshot is not evidence"
                )
            if not has_start:
                raise ValueError(
                    "a card holding evidence_text must record evidence_start_offset and "
                    "evidence_end_offset so the quotation can be reproduced from the snapshot"
                )
        elif has_start:
            raise ValueError("evidence offsets were given without any evidence_text")
        return self

    @model_validator(mode="after")
    def _check_spans(self) -> Self:
        """Spans mark up the evidence, so they must fall inside it and not collide."""
        if not self.spans:
            return self
        if not self.evidence_text:
            raise ValueError("a card with no evidence_text cannot carry spans")
        length = len(self.evidence_text)
        for span in self.spans:
            if span.end_offset > length:
                raise ValueError(
                    f"span {span.start_offset}-{span.end_offset} runs past the end of evidence_text "
                    f"({length} characters)"
                )
        for index, span in enumerate(self.spans):
            for other in self.spans[index + 1 :]:
                if span.style is other.style and span.overlaps(other):
                    raise ValueError(
                        f"two {span.style} spans overlap ({span.start_offset}-{span.end_offset} and "
                        f"{other.start_offset}-{other.end_offset}); merge them instead"
                    )
        return self

    @model_validator(mode="after")
    def _check_verified_preconditions(self) -> Self:
        """A card can only claim VERIFIED if everything re-verification needs is on it."""
        if self.verification_status is not VerificationStatus.VERIFIED:
            return self
        missing: list[str] = []
        if self.snapshot_id is None:
            missing.append("snapshot_id")
        if self.normalizer_version is None:
            missing.append("normalizer_version")
        if not self.evidence_text:
            missing.append("evidence_text")
        if not self.spans:
            missing.append("at least one span")
        if missing:
            raise ValueError(
                f"a VERIFIED card must have {', '.join(missing)}; "
                "a card that cannot be re-verified stays UNVERIFIED"
            )
        return self

    @property
    def is_finished_evidence(self) -> bool:
        """True when this card may be presented and exported as a finished evidence card."""
        return self.verification_status is VerificationStatus.VERIFIED

    def spans_of_style(self, style: SpanStyle) -> tuple[CardSpan, ...]:
        """Return this card's spans of one style, ordered by position in the evidence."""
        return tuple(sorted((s for s in self.spans if s.style is style), key=lambda s: s.start_offset))

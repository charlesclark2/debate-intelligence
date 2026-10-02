"""The evidence card and its markup.

A :class:`Card` is the platform's output: a tag, a cite, a verbatim quotation, and the underlining
and highlighting a debater reads from. Its invariants exist to make one failure mode impossible —
quoted evidence that is not traceable to a stored snapshot.

## Envelope and omissions (ADR-0018)

A card quotes one passage of its snapshot and records what it left out of it. Cutting a card means
removing words from the middle of a passage, so this is the ordinary case, not an exception.

* `evidence_start_offset` and `evidence_end_offset` are the **envelope**: the first character of the
  passage the card quotes from, and the position just past its last, in the snapshot's normalized
  text.
* `omitted_ranges` lists what was removed from inside the envelope, as snapshot offsets, in
  **canonical form**: sorted, non-overlapping, non-adjacent (two touching omissions are one
  omission), non-empty, and strictly inside the envelope, touching neither boundary (an omission at
  an edge is a smaller envelope). One card therefore has exactly one representation.
* `evidence_text` is the envelope with the omissions removed, the pieces concatenated with **no
  joiner**: no ellipsis, bracket or space is ever stored, because any of them is text no snapshot
  contains. Whether and how a cut is shown (an ellipsis, a paragraph break) is decided by the
  exporter from `omitted_ranges` when it renders the card.
* `CardSpan` offsets index `evidence_text`, never the snapshot, so a span cannot mark omitted text.

`debate_core.evidence.card_mapping.place_evidence_on_card` is the one function that turns an
extracted selection and its markup into these fields; nothing else does that offset arithmetic.

## Construction rules

Four rules are enforced here, at construction:

1. A card that holds evidence text must say where the text came from: a `snapshot_id` and the
   envelope of the quotation inside that snapshot's normalized text.
2. Omissions are in canonical form, and the envelope's length minus the total length of the
   omissions equals `len(evidence_text)`. That length invariant needs no snapshot to check.
3. A card can only be `VERIFIED` if it has everything re-verification needs: the snapshot, the
   `normalizer_version` the offsets were taken under, and at least one marked span.
4. Spans must fall inside the evidence text, and two spans of the same style may not overlap.

The domain deliberately does *not* check that `evidence_text` equals the snapshot's text at those
offsets. That comparison is the evidence verifier's job (E03): a tampered or edited card has to be
constructible so the verifier can report `TEXT_MISMATCH` on it, rather than blowing up before it can
be checked. The length invariant is consistent with that: it compares the card with itself, and a
card whose text was altered without changing its length is still constructible and still reported.
"""

from __future__ import annotations

import itertools
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

__all__ = ["Card", "CardOmission", "CardSpan"]

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


class CardOmission(DomainModel):
    """Characters of the snapshot a card left out of the passage it quotes.

    Offsets are character positions **into the snapshot's normalized text**, like the card's
    `evidence_start_offset` and `evidence_end_offset`, half-open (`start_offset` inclusive,
    `end_offset` exclusive). This is the opposite of :class:`CardSpan`, whose offsets index
    `evidence_text`: an omission names text that is, by definition, not in `evidence_text`.

    It holds no text. Whoever audits the card reads what was removed from the snapshot at these
    offsets, and the exporter decides how to show the cut.
    """

    start_offset: int = Field(ge=0, description="Inclusive start offset of the omitted text in the snapshot.")
    end_offset: int = Field(gt=0, description="Exclusive end offset of the omitted text in the snapshot.")

    @model_validator(mode="after")
    def _check_bounds(self) -> Self:
        if self.start_offset >= self.end_offset:
            raise ValueError(
                f"an omission must remove at least one character; start_offset ({self.start_offset}) "
                f"must be before end_offset ({self.end_offset})"
            )
        return self

    @property
    def length(self) -> int:
        """Number of snapshot characters omitted."""
        return self.end_offset - self.start_offset


class Card(DomainEntity):
    """A piece of evidence cut from a source snapshot.

    `evidence_text` is verbatim: it is the stored snapshot's text from `evidence_start_offset` to
    `evidence_end_offset` with `omitted_ranges` taken out (see the module docstring), never written
    or paraphrased by a model. A model may choose *which* span to cut and may write the `tag`, but
    the quotation itself only ever comes out of the snapshot (architecture proposal §8).

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
        default=None,
        ge=0,
        description="Inclusive start offset of the quotation's envelope in the normalized snapshot.",
    )
    evidence_end_offset: int | None = Field(
        default=None,
        gt=0,
        description="Exclusive end offset of the quotation's envelope in the normalized snapshot.",
    )
    omitted_ranges: tuple[CardOmission, ...] = Field(
        default=(),
        description=(
            "Snapshot ranges left out from inside the envelope, in canonical form: sorted, separated by "
            "at least one kept character, and touching neither end of the envelope."
        ),
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
    def _check_omissions(self) -> Self:
        """Omissions are canonical, and the envelope minus them is exactly as long as the text."""
        start, end = self.evidence_start_offset, self.evidence_end_offset
        if start is None or end is None:
            if self.omitted_ranges:
                raise ValueError("a card with no evidence envelope cannot omit anything from it")
            return self
        for omission in self.omitted_ranges:
            if not start < omission.start_offset or not omission.end_offset < end:
                raise ValueError(
                    f"omission {omission.start_offset}-{omission.end_offset} is not strictly inside the "
                    f"envelope {start}-{end}; an omission at an edge is a smaller envelope"
                )
        for previous, omission in itertools.pairwise(self.omitted_ranges):
            # One rule: each omission starts after the previous one ends, with a kept character
            # between them. The label only says which way a refused pair breaks it.
            if omission.start_offset <= previous.end_offset:
                if omission.start_offset < previous.start_offset:
                    problem = "are out of order"
                elif omission.start_offset < previous.end_offset:
                    problem = "overlap"
                else:
                    problem = "touch; two touching omissions are one omission"
                raise ValueError(
                    f"omissions {previous.start_offset}-{previous.end_offset} and "
                    f"{omission.start_offset}-{omission.end_offset} {problem}"
                )
        quoted = (end - start) - sum(omission.length for omission in self.omitted_ranges)
        if quoted != len(self.evidence_text):
            raise ValueError(
                f"the envelope {start}-{end} minus {len(self.omitted_ranges)} omission(s) quotes {quoted} "
                f"characters, but evidence_text has {len(self.evidence_text)}"
            )
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
    def quoted_ranges(self) -> tuple[tuple[int, int], ...]:
        """The snapshot ranges `evidence_text` is made of, in order: the envelope minus the omissions.

        Empty for a card with no evidence. Half-open `(start, end)` pairs into the snapshot's
        normalized text; each is non-empty, and consecutive ones never touch.
        """
        if self.evidence_start_offset is None or self.evidence_end_offset is None:
            return ()
        ranges: list[tuple[int, int]] = []
        kept_from = self.evidence_start_offset
        for omission in self.omitted_ranges:
            ranges.append((kept_from, omission.start_offset))
            kept_from = omission.end_offset
        ranges.append((kept_from, self.evidence_end_offset))
        return tuple(ranges)

    @property
    def is_finished_evidence(self) -> bool:
        """True when this card may be presented and exported as a finished evidence card."""
        return self.verification_status is VerificationStatus.VERIFIED

    def spans_of_style(self, style: SpanStyle) -> tuple[CardSpan, ...]:
        """Return this card's spans of one style, ordered by position in the evidence."""
        return tuple(sorted((s for s in self.spans if s.style is style), key=lambda s: s.start_offset))

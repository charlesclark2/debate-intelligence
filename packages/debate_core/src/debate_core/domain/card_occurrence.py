"""Recognising one card across many files: its fingerprint, its cluster and every place it appears.

The same piece of evidence is disclosed by dozens of teams. Each copy is re-tagged, re-highlighted,
cut a sentence shorter or pasted through a PDF that broke its spacing, and a landscape report
(E32) that counted copies would count the same card thirty times. The models here are what lets
the platform say "this is one card, and these are the thirty places it was read".

* :class:`CardFingerprint` — the exact identity of one card body, under a documented, versioned
  normalization (:mod:`debate_core.evidence.fingerprints`).
* :class:`CardOccurrence` — one place a card appears: which cluster it belongs to, which file and
  paragraph it sits in, who disclosed it and in which snapshots it was seen.

## Rules these models carry

**A fingerprint is for matching, never for display.** The normalization lowercases, unifies quotes
and collapses whitespace so that two copies of one card hash the same. Nothing it produces is ever
stored as, or shown in place of, evidence text; :class:`CardFingerprint` holds a digest and has no
field for normalized text at all.

**An occurrence is a place, not a file.** Weekly caselist archives are cumulative, so one
disclosure arrives again every week until it is taken down. An occurrence is therefore keyed by
the source's SHA-256 and the card's element index together with the disclosure it was read under
(caselist, school, team code, side, tournament and round) — never by snapshot or archive path — and
the snapshots only move its first and last seen dates (:attr:`CardOccurrence.occurrence_key`).

**A cutter mark is opaque.** Cite tails often end with the initials or handle of whoever cut the
card. That is cross-team provenance and it is kept, verbatim, as :attr:`CardOccurrence.cutter_mark`
— under the same minimization as a team code (`docs/policies/caselist-data-use.md`, prohibition 6
and personal-data rules 4 and 5). It is never expanded to a name, never joined to a roster or a
Tabroom entry, never printed by a report, and it is excluded from the model's `repr` so that an
occurrence that reaches a log line by accident does not carry it there.

**Nothing here identifies a person beyond what a disclosure already says.** School and team code
are copied from the E30 :class:`~debate_core.domain.caselist.entities.Disclosure`; there is no
field for a debater's name.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Annotated, Final, Self

from pydantic import AfterValidator, Field, StringConstraints, model_validator

from debate_core.domain.base import DomainModel, NonEmptyText, Sha256Hex
from debate_core.domain.caselist.values import CaselistSlug, RoundLabel, Side, TeamCodeText
from debate_core.domain.debate_files import CardCompleteness

__all__ = [
    "CUTTER_MARK_MAX_LENGTH",
    "CardFingerprint",
    "CardOccurrence",
    "ClusterMembership",
    "CutterMarkText",
    "FingerprintBasis",
    "OccurrenceKey",
]

#: Longest cutter mark kept. Real ones are initials or a short handle (`JD`, `ab/cd`).
CUTTER_MARK_MAX_LENGTH: Final = 16


def _reject_name_shaped_cutter_mark(value: str) -> str:
    """Refuse a "cutter mark" with whitespace in it: that is a name, not a mark."""
    if any(character.isspace() for character in value):
        raise ValueError(
            "a cutter mark is a single opaque token, never whitespace-separated words "
            "(the platform stores no names)"
        )
    return value


CutterMarkText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=CUTTER_MARK_MAX_LENGTH),
    AfterValidator(_reject_name_shaped_cutter_mark),
]
"""A cutter mark exactly as the cite tail spelled it, constrained so a full name cannot fit."""


class FingerprintBasis(StrEnum):
    """What the exact fingerprint was computed over.

    A card's identity is its evidence body: tags and cites are excluded because teams re-tag and
    re-cite the same card. A `CITE_ONLY` card has no body, so its fingerprint is taken over its
    cite line instead, and says so here; hashing its empty body would make every cite-only card
    in the corpus one card.
    """

    EVIDENCE_BODY = "EVIDENCE_BODY"
    """The normalized evidence text. Every FULL and ABBREVIATED card."""

    CITE_LINE = "CITE_LINE"
    """The normalized full cite. A CITE_ONLY card, which has no body."""


class ClusterMembership(StrEnum):
    """How a card came to be in the cluster its occurrence names."""

    NEAR_DUPLICATE = "NEAR_DUPLICATE"
    """A full card, placed by MinHash candidates confirmed by Jaccard or containment."""

    ABBREVIATED_LINK = "ABBREVIATED_LINK"
    """An ABBREVIATED or CITE_ONLY card linked to exactly one full card's cluster by short cite plus
    first and last words."""

    UNLINKED = "UNLINKED"
    """An ABBREVIATED or CITE_ONLY card that matched no full card, or more than one. Its cluster is
    its own exact fingerprint: a link is never guessed."""


class CardFingerprint(DomainModel):
    """The exact identity of one card body under one version of the fingerprint normalization."""

    exact_fingerprint: Sha256Hex = Field(
        description="SHA-256 of the normalized body (or cite line, for a CITE_ONLY card)."
    )
    fingerprint_version: NonEmptyText = Field(
        description="Version of the normalization rules the digest was computed under."
    )
    basis: FingerprintBasis = Field(description="Whether the digest covers the body or the cite line.")


#: The natural key of an occurrence; see :attr:`CardOccurrence.occurrence_key`.
type OccurrenceKey = tuple[str, int, str, str, str, str, str, str]


class CardOccurrence(DomainModel):
    """One place a card appears: a paragraph range in one file, under one disclosure.

    Disclosure fields are `None` for a card whose file has no disclosure on record — an OpenEv
    camp file, or a caselist source this machine has parsed but not imported — so an occurrence
    is never dropped for missing metadata. Such an occurrence counts as a file but not as a team.
    """

    cluster_id: Sha256Hex = Field(
        description="The smallest exact fingerprint among the cluster's full cards; stable across runs."
    )
    exact_fingerprint: Sha256Hex = Field(description="This card's own exact fingerprint.")
    fingerprint_version: NonEmptyText = Field(description="Version of the fingerprint normalization.")
    completeness: CardCompleteness = Field(description="FULL, ABBREVIATED or CITE_ONLY, as parsed.")
    membership: ClusterMembership = Field(description="How the card joined its cluster.")
    caselist: CaselistSlug | None = Field(default=None, description="Caselist; None for a camp file.")
    camp: NonEmptyText | None = Field(default=None, description="Camp; None for a caselist disclosure.")
    school: NonEmptyText | None = Field(default=None, description="School, as the disclosure spells it.")
    team_code: TeamCodeText | None = Field(default=None, description="Team code, exactly as disclosed.")
    side: Side | None = Field(default=None, description="Side the disclosing file was read on.")
    tournament: NonEmptyText | None = Field(default=None, description="Tournament, as disclosed.")
    round_label: RoundLabel | None = Field(default=None, description="Round, as disclosed and normalized.")
    first_seen_snapshot: date = Field(description="Earliest snapshot this occurrence was seen in.")
    last_seen_snapshot: date = Field(description="Latest snapshot this occurrence was seen in.")
    source_sha256: Sha256Hex = Field(description="SHA-256 of the file the card was read from.")
    element_index: int = Field(
        ge=0, description="Index in the document body of the first paragraph the card was built from."
    )
    cutter_mark: CutterMarkText | None = Field(
        default=None,
        repr=False,
        description=(
            "Initials or handle from the cite tail, verbatim and opaque. Never expanded, joined, "
            "logged or shown in a report."
        ),
    )
    tag: str = Field(default="", description="The card's tag in this file, copied exactly.")
    short_cite: str | None = Field(default=None, description="The card's short cite in this file, copied.")

    @model_validator(mode="after")
    def _check_occurrence(self) -> Self:
        if self.last_seen_snapshot < self.first_seen_snapshot:
            raise ValueError(
                f"last_seen_snapshot {self.last_seen_snapshot.isoformat()} precedes first_seen_snapshot "
                f"{self.first_seen_snapshot.isoformat()}"
            )
        if self.team_code is not None and self.school is None:
            raise ValueError("a team code is only meaningful inside a school; this occurrence names none")
        if self.caselist is not None and self.camp is not None:
            raise ValueError("an occurrence belongs to a caselist disclosure or to a camp file, not both")
        return self

    @property
    def occurrence_key(self) -> OccurrenceKey:
        """What makes two sightings the same occurrence.

        The source SHA-256 and element index say which paragraph of which bytes; the disclosure
        fields say who read it where. Snapshot and archive path are deliberately absent, so the
        same disclosure in three cumulative archives, or re-uploaded under a browser's `(1)` name,
        is one occurrence. The same bytes disclosed by two teams are two.
        """
        return (
            self.source_sha256,
            self.element_index,
            self.caselist or self.camp or "",
            self.school or "",
            self.team_code or "",
            str(self.side) if self.side is not None else "",
            self.tournament or "",
            self.round_label.raw if self.round_label is not None else "",
        )

    @property
    def team(self) -> tuple[str, str, str] | None:
        """(caselist, school, team code), or `None` when no disclosure names a team."""
        if self.caselist is None or self.school is None or self.team_code is None:
            return None
        return (self.caselist, self.school, self.team_code)

"""A cite that carries its own provenance, field by field.

Every part of a citation is a :class:`CitationField`: the value, where it was harvested from, and
whether that source counts as verification. Nothing here is ever filled in by a model. If a
publication date cannot be found, the field stays missing and the export shows the gap, because a
plausible-looking invented date is exactly the failure this platform exists to prevent
(architecture proposal §8).
"""

from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from debate_core.domain.base import DomainModel, NonEmptyText, UtcDatetime
from debate_core.domain.enums import CitationFieldSource

__all__ = ["REQUIRED_CITATION_FIELDS", "Citation", "CitationField"]

#: The fields a cite must have verified before a card can be presented as finished evidence.
#: Author credentials and the accessed date are recorded when available but never required: many
#: legitimate sources state no author qualification.
REQUIRED_CITATION_FIELDS = ("authors", "title", "publication", "published_at", "canonical_url")


class CitationField[CitationValueT](DomainModel):
    """One citation value together with where it came from.

    Two invariants keep the provenance honest:

    * a field whose source is `missing` holds no value and cannot be verified;
    * a field can only be `verified` if it has a value from a source that actually verifies it —
      a `heuristic` guess (a date read out of a URL slug, say) never counts.
    """

    value: CitationValueT | None = Field(default=None, description="The harvested value, if any.")
    source: CitationFieldSource = Field(
        default=CitationFieldSource.MISSING, description="Where the value was harvested from."
    )
    verified: bool = Field(
        default=False, description="True only when the source independently confirms the value."
    )
    raw: str | None = Field(
        default=None, description="The unparsed text the value was read from, kept for auditing."
    )

    @model_validator(mode="after")
    def _check_provenance(self) -> Self:
        if self.source is CitationFieldSource.MISSING:
            if self.value is not None:
                raise ValueError("a citation field with source 'missing' cannot hold a value")
            if self.verified:
                raise ValueError("a citation field with source 'missing' cannot be verified")
        if self.verified:
            if self.value is None:
                raise ValueError("a verified citation field must have a value")
            if self.source is CitationFieldSource.HEURISTIC:
                raise ValueError(
                    "a heuristic value is a guess and cannot be marked verified; "
                    "use an explicit metadata source or leave the field unverified"
                )
        return self

    @property
    def is_present(self) -> bool:
        """True when a value was found, whether or not it is verified."""
        return self.value is not None


class Citation(DomainModel):
    """The cite for one card, with per-field provenance.

    `authors` is a single field holding the ordered author list rather than one field per author,
    because a page's byline is harvested (and verified) as a unit.

    Resolution — harvesting these values from a snapshot's HTML and from Crossref — is the
    citation service's job (E06); this model only records the outcome and its provenance.
    """

    authors: CitationField[tuple[NonEmptyText, ...]] = Field(
        default_factory=CitationField[tuple[NonEmptyText, ...]], description="Author names, in order."
    )
    author_credentials: CitationField[str] = Field(
        default_factory=CitationField[str],
        description="Author qualification as stated on the source or in Crossref/ORCID; never inferred.",
    )
    title: CitationField[str] = Field(default_factory=CitationField[str], description="Article title.")
    publication: CitationField[str] = Field(
        default_factory=CitationField[str], description="Publication, journal or issuing body."
    )
    published_at: CitationField[UtcDatetime] = Field(
        default_factory=CitationField[UtcDatetime], description="Publication date, in UTC."
    )
    canonical_url: CitationField[str] = Field(
        default_factory=CitationField[str], description="Canonical URL of the source."
    )
    accessed_at: CitationField[UtcDatetime] = Field(
        default_factory=CitationField[UtcDatetime], description="When the platform retrieved the source."
    )

    @property
    def unverified_fields(self) -> tuple[str, ...]:
        """Names of the required cite fields that are not verified, in cite order.

        Exports use this to mark a cite as incomplete rather than presenting it as checked.
        """
        verified_by_name: dict[str, bool] = {
            "authors": self.authors.verified,
            "title": self.title.verified,
            "publication": self.publication.verified,
            "published_at": self.published_at.verified,
            "canonical_url": self.canonical_url.verified,
        }
        return tuple(name for name in REQUIRED_CITATION_FIELDS if not verified_by_name[name])

    @property
    def is_fully_verified(self) -> bool:
        """True when every required cite field has a verified value."""
        return not self.unverified_fields

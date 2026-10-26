"""The DOI lookup a cite prefers for a scholarly source (v1-e06-t01).

:class:`DoiMetadataSource` answers one question: what does the registry that holds this DOI say the
work is? :class:`~debate_core.application.citation_service.CitationService` asks it for a page that
states a DOI, and prefers its title, container title, date and authors to the page's own metadata,
because a registration deposit is the publisher's statement about the work rather than about one
web page that shows it.

The adapter is `debate_core.integrations.crossref_doi` (Crossref's `/works/{doi}`), and it keeps a
cache by DOI on this machine, so a DOI is asked for once. Searching Crossref for works is discovery
(`v1-e07-t03`) and is not this port.

The values are what a deposit states, mapped and nothing more: no name is reformatted, no date
completed. A deposit that gives only a year leaves the month and day `None`, and the service then
does not use that date (a cite date is never given a day the source did not state).
"""

from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from pydantic import Field

from debate_core.domain import DomainModel, NonEmptyText

__all__ = ["DoiAuthor", "DoiDate", "DoiMetadataSource", "DoiWork"]


class DoiAuthor(DomainModel):
    """One contributor as a deposit names them: split into given and family names, or as one name."""

    given: NonEmptyText | None = Field(default=None, description="Given name(s), as deposited.")
    family: NonEmptyText | None = Field(default=None, description="Family name, as deposited.")
    name: NonEmptyText | None = Field(
        default=None, description="A name deposited whole, as for an organization or a consortium."
    )
    affiliations: tuple[NonEmptyText, ...] = Field(
        default=(), description="Affiliation names, as deposited, in order."
    )
    orcid: NonEmptyText | None = Field(default=None, description="The ORCID iD URL, when deposited.")

    @property
    def display_name(self) -> str | None:
        """"Given Family", the family name alone, or the whole name; `None` when none is deposited."""
        if self.family is not None:
            return f"{self.given} {self.family}" if self.given is not None else self.family
        return self.name


class DoiDate(DomainModel):
    """One of a deposit's dates (`published`, `published-online`, `issued`, ...), to the precision given."""

    kind: NonEmptyText = Field(description="Which of the deposit's dates this is.")
    year: int = Field(ge=1, le=9999, description="The year.")
    month: int | None = Field(default=None, ge=1, le=12, description="The month, when deposited.")
    day: int | None = Field(default=None, ge=1, le=31, description="The day, when deposited.")

    @property
    def whole_date(self) -> date | None:
        """The date, when the deposit gives its year, month and day and they make a real date."""
        if self.month is None or self.day is None:
            return None
        try:
            return date(self.year, self.month, self.day)
        except ValueError:
            return None


class DoiWork(DomainModel):
    """What the registry holding a DOI says about the work."""

    doi: NonEmptyText = Field(description="The DOI the registry answered for, bare and lower-case.")
    title: NonEmptyText | None = Field(default=None, description="The work's title.")
    container_title: NonEmptyText | None = Field(
        default=None, description="The journal, book or proceedings it appeared in."
    )
    authors: tuple[DoiAuthor, ...] = Field(default=(), description="Its authors, in deposited order.")
    dates: tuple[DoiDate, ...] = Field(
        default=(), description="Its dates, earliest publication first: published, online, print, issued."
    )


@runtime_checkable
class DoiMetadataSource(Protocol):
    """Looks a DOI up in the registry that holds it."""

    async def lookup(self, doi: str) -> DoiWork | None:
        """The registry's record for `doi` (bare, lower-case), or `None` when it holds none.

        Raises :class:`~debate_core.application.errors.ProviderUnavailable` when the registry could
        not answer: a timeout, a transport failure, a rate limit, a server error or a response that
        does not read as a work. A caller that can do without the answer catches that and goes on.
        """
        ...

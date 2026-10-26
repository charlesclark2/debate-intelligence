"""Cite fields as a stored page states them, each with where it was read (v1-e06-t01). Skeleton."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from debate_core.domain.enums import CitationFieldSource

__all__ = [
    "CitationCandidates",
    "Harvested",
    "StatedDate",
    "harvest_page",
    "harvest_url",
    "parse_stated_date",
]


@dataclass(frozen=True, slots=True)
class Harvested[ValueT]:
    """One value for one cite field, the source it was read from, and the text it was read out of."""

    value: ValueT
    source: CitationFieldSource
    raw: str


@dataclass(frozen=True, slots=True)
class CitationCandidates:
    """Every value a page and its URL state for each cite field, in the order they were found."""

    authors: tuple[Harvested[tuple[str, ...]], ...] = ()
    author_credentials: tuple[Harvested[str], ...] = ()
    title: tuple[Harvested[str], ...] = ()
    publication: tuple[Harvested[str], ...] = ()
    published_at: tuple[Harvested[datetime], ...] = ()
    canonical_url: tuple[Harvested[str], ...] = ()
    dois: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class StatedDate:
    """A publication date as a page states it: the instant in UTC, and the calendar day it names."""

    moment: datetime
    calendar_date: date


def parse_stated_date(text: str) -> StatedDate | None:
    return None


def harvest_url(retrieved_url: str) -> CitationCandidates:
    return CitationCandidates()


def harvest_page(raw: bytes, *, content_type: str | None, retrieved_url: str) -> CitationCandidates:
    return CitationCandidates()

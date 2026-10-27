"""CitationService: a card's cite, each field with its source and whether that verifies it (v1-e06-t01).

:meth:`CitationService.resolve` turns an article and one of its snapshots into a
:class:`~debate_core.domain.Citation`. Nothing in it is written or guessed by a model (architecture
proposal §8, §19): each field is a value some source states, or it is missing.

## Where values come from

1. **The page.** For a snapshot the platform retrieved, the stored raw bytes are read by
   :func:`~debate_core.retrieval.citation_harvest.harvest_page`: JSON-LD, meta tags, OpenGraph,
   bylines and author bios, and the URL's own heuristics. A snapshot of any other provenance (a
   user's pasted text) holds no markup, so only its URL is read
   (:func:`~debate_core.retrieval.citation_harvest.harvest_url`), and the title the user gave the
   article, which is a heuristic.
2. **Crossref, by DOI.** The first DOI the page's metadata or URL states, else the article's own, is
   looked up through the :class:`~debate_core.application.ports.doi_metadata.DoiMetadataSource` port,
   once per DOI (the adapter caches). Crossref gives the title, the container title as the
   publication, the first whole date (a year or a month alone is never completed), the authors, and
   each author's deposited affiliations as credentials. A lookup that fails is logged and the cite
   is resolved from the page: a Crossref outage never fails a cite. The outcome is on the
   :class:`CitationResolution` (:class:`CrossrefOutcome`).

## Which value wins, and what verifies it

Per field, the candidate from the highest source in :data:`SOURCE_PRECEDENCE` wins: Crossref, then
JSON-LD, meta tags, OpenGraph, byline, the platform's retrieval record, heuristic; within one source,
the first found. A field with no candidate is `missing`.

A value is **verified** when its source is an explicit statement (anything but `heuristic`) and the
platform retrieved the source itself (`PUBLISHER_RETRIEVED`). A heuristic is never verified, and
nothing about a user's pasted text is: not even Crossref's answer for a DOI in its URL, because
nothing shows the text is that work. The provenance mode travels on the resolution and into the
formatted cite, so it stays visible.

**Credentials** are only ever an explicit author bio on the page, JSON-LD's `jobTitle` and
`affiliation`, or Crossref's affiliations (ac3), each of a person author. Otherwise the field is
missing and the cite carries no qualification.

**An organization as the author** (`v1-e06-t02`). When no source names a person, an organization a
typed source names as the author stands in: a JSON-LD `author` typed `Organization` or a subtype, or
a Crossref contributor deposited with a whole name and no family name. The cite marks it
(`authors_are_organizations`), and its short cite keeps the name whole. Beside a named person an
organization is not an author, and nothing else ever makes one: not a site name, `og:site_name`, a
publisher or the publication. With no typed organization, `authors` stays missing.

**The platform's retrieval record** (`retrieval`, `v1-e06-t02`) is the accessed date, the snapshot's
`retrieved_at` with the timestamp as `raw`, and the URL of last resort: the retrieved URL,
canonicalized, when the page declares no canonical URL of its own. Like any explicit source it is
verified exactly when the platform retrieved the text, so an open-access PDF, or a page with no
canonical link, can verify; under any other provenance it is a record of what the user said.

## A student's edits (ac5)

A student may change a cite field through
:class:`~debate_core.application.card_edit_service.CardEditService`, which stores it unverified.
:meth:`CitationService.re_resolve` resolves the card's snapshot again and, when the card's edit log
holds a cite edit, keeps what the student wrote (:func:`keep_student_edits`): a field whose value
equals the derived one takes the derived field, verified exactly when the derivation is; a field
that differs keeps the student's value, unverified, and is named in
:attr:`CitationResolution.student_fields`. A field the student cleared is recorded on the cite
(`cleared_by_student`, by the edit policy) and stays empty, named there too, and is never filled
again by re-resolution (`v1-e06-t02`): a required one leaves the card UNVERIFIED, with the
verifier's ``CITATION_UNVERIFIED`` naming it. A card no student has cite-edited takes the derived
cite whole. Saving the card, and re-verifying it, is the caller's step.

## Formatting (ac4)

:func:`format_cite` writes the short cite, "Lastname YY" (first author's last name, "et al." for
more, an organization's name whole; with no author the publication, then the title; "ND" with no
date), and the full cite line:
authors with their credentials in parentheses, the title in quotes, the publication, the date as
the source states its day, the URL, the accessed date, and where the text came from when the
platform did not retrieve it. Team conventions are format profiles' business (`v1-e06-t03`). The
returned :class:`FormattedCite` names every field that is shown unverified, and every field that is
missing, so an export can mark them.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any, Final

from debate_core.application.errors import ProviderUnavailable
from debate_core.application.ports.card_edit_log import CardEditLog
from debate_core.application.ports.doi_metadata import DoiMetadataSource, DoiWork
from debate_core.application.ports.persistence import ArticleRepository
from debate_core.application.snapshot_service import LoadedSnapshot, SnapshotService
from debate_core.domain import Article, Card, Citation, CitationField, ProvenanceMode
from debate_core.domain.citation import CITATION_FIELD_NAMES
from debate_core.domain.enums import CitationFieldSource
from debate_core.evidence.edits import EditKind
from debate_core.retrieval.citation_harvest import (
    CitationCandidates,
    Harvested,
    harvest_page,
    harvest_url,
    parse_stated_date,
)

__all__ = [
    "CITATION_FIELD_NAMES",
    "SOURCE_PRECEDENCE",
    "CitationResolution",
    "CitationService",
    "CrossrefOutcome",
    "FormattedCite",
    "format_cite",
    "keep_student_edits",
    "resolve_citation",
]

logger = logging.getLogger(__name__)

SOURCE_PRECEDENCE: Final = (
    CitationFieldSource.CROSSREF,
    CitationFieldSource.JSON_LD,
    CitationFieldSource.META_TAG,
    CitationFieldSource.OPENGRAPH,
    CitationFieldSource.BYLINE,
    CitationFieldSource.RETRIEVAL,
    CitationFieldSource.HEURISTIC,
)
"""Which source's value a field takes when several state one, highest first."""

_RANK: Final = {source: rank for rank, source in enumerate(SOURCE_PRECEDENCE)}
_CROSSREF: Final = CitationFieldSource.CROSSREF
_HEURISTIC: Final = CitationFieldSource.HEURISTIC
_RETRIEVAL: Final = CitationFieldSource.RETRIEVAL


class CrossrefOutcome(StrEnum):
    """What came of looking the source's DOI up."""

    NO_DOI = "no_doi"
    """The source states no DOI, so nothing was looked up."""

    NOT_CONFIGURED = "not_configured"
    """A DOI was found, but no DOI lookup is wired."""

    FOUND = "found"
    """Crossref holds the DOI, and its answer was used."""

    NOT_REGISTERED = "not_registered"
    """Crossref holds no record for the DOI; the page's metadata stands."""

    FAILED = "failed"
    """The lookup failed (timeout, transport, error answer); the page's metadata stands."""


@dataclass(frozen=True, slots=True)
class CitationResolution:
    """A resolved cite, the provenance of the text it is for, and how the DOI lookup went."""

    citation: Citation
    provenance_mode: ProvenanceMode
    """The snapshot's provenance mode, kept beside the cite so a reader can tell whose text it is."""

    doi: str | None
    """The DOI looked up, or that would have been."""

    crossref: CrossrefOutcome
    student_fields: tuple[str, ...] = ()
    """Fields that keep a student's value, unverified, because it differs from the source's (ac5)."""


@dataclass(frozen=True, slots=True)
class FormattedCite:
    """A cite as text, and the fields an export must mark."""

    short_cite: str
    """"Lastname YY", as "Smith 26"."""

    full_cite: str
    """The short cite and the bracketed cite line, accessed date included."""

    unverified_fields: tuple[str, ...]
    """Fields shown in the cite whose value is not verified, in cite order."""

    missing_fields: tuple[str, ...]
    """Fields with no value, in cite order; the cite shows nothing for them."""

    provenance_mode: ProvenanceMode


# --------------------------------------------------------------------------------------------
# Choosing each field
# --------------------------------------------------------------------------------------------


def resolve_citation(
    candidates: CitationCandidates,
    work: DoiWork | None,
    *,
    provenance_mode: ProvenanceMode,
    accessed_at: datetime,
) -> Citation:
    """The cite `candidates` and the Crossref `work` make, by :data:`SOURCE_PRECEDENCE`.

    A value is verified only when its source is not `heuristic` and `provenance_mode` is
    PUBLISHER_RETRIEVED; see the module docstring.
    """
    deposit = _deposit_candidates(work)
    verifies = provenance_mode is ProvenanceMode.PUBLISHER_RETRIEVED
    people = (*deposit.authors, *candidates.authors)
    organizations = (*deposit.organization_authors, *candidates.organization_authors)
    return Citation.model_validate(
        {
            "authors": _chosen(people or organizations, verifies),
            "authors_are_organizations": not people and bool(organizations),
            "author_credentials": _chosen(
                (*deposit.author_credentials, *candidates.author_credentials), verifies
            ),
            "title": _chosen((*deposit.title, *candidates.title), verifies),
            "publication": _chosen((*deposit.publication, *candidates.publication), verifies),
            "published_at": _chosen((*deposit.published_at, *candidates.published_at), verifies),
            "canonical_url": _chosen(candidates.canonical_url, verifies),
            "accessed_at": {
                "value": accessed_at,
                "source": _RETRIEVAL,
                "verified": verifies,
                "raw": accessed_at.isoformat(),
            },
        }
    )


def _chosen(candidates: Sequence[Harvested[Any]], verifies: bool) -> dict[str, Any]:
    """The highest-ranked candidate as a citation field's data; the first of equals; missing when none."""
    if not candidates:
        return {}
    best = min(candidates, key=lambda candidate: _RANK[candidate.source])
    return {
        "value": best.value,
        "source": best.source,
        "verified": verifies and best.source is not _HEURISTIC,
        "raw": best.raw,
    }


def _deposit_candidates(work: DoiWork | None) -> CitationCandidates:
    """What a Crossref work states, as candidates from `crossref`."""
    if work is None:
        return CitationCandidates()
    people = tuple(author for author in work.authors if author.family is not None)
    names = tuple(name for author in people if (name := author.display_name) is not None)
    organizations = tuple(
        author.name for author in work.authors if author.family is None and author.name is not None
    )
    credentials = "; ".join(
        ", ".join((name, *author.affiliations))
        for author in people
        if (name := author.display_name) is not None and author.affiliations
    )
    day = next((stated.whole_date for stated in work.dates if stated.whole_date is not None), None)
    return CitationCandidates(
        authors=(Harvested(names, _CROSSREF, ", ".join(names)),) if names else (),
        organization_authors=(
            (Harvested(organizations, _CROSSREF, ", ".join(organizations)),) if organizations else ()
        ),
        author_credentials=(Harvested(credentials, _CROSSREF, credentials),) if credentials else (),
        title=(Harvested(work.title, _CROSSREF, work.title),) if work.title else (),
        publication=(Harvested(work.container_title, _CROSSREF, work.container_title),)
        if work.container_title
        else (),
        published_at=(
            (Harvested(datetime(day.year, day.month, day.day, tzinfo=UTC), _CROSSREF, day.isoformat()),)
            if day is not None
            else ()
        ),
    )


def keep_student_edits(stored: Citation, derived: Citation) -> tuple[Citation, tuple[str, ...]]:
    """`derived`, keeping each of `stored`'s fields a student changed away from the source (ac5).

    For each field: a field the student cleared (`stored.cleared_by_student`, `v1-e06-t02`) stays
    empty, whatever the source says. Otherwise, when `stored` has no value, or the same value as
    `derived`, the derived field is taken, verified exactly when the derivation is. A stored value
    marked verified is the service's own from an earlier resolution (a student's changed field never
    arrives verified), so the derivation replaces it. Any other stored value is the student's: it is
    kept as stored, with `verified` false. The names of the cleared and kept fields are returned with
    the cite, in cite order.
    """
    kept: dict[str, CitationField[Any]] = {}
    for name in CITATION_FIELD_NAMES:
        mine: CitationField[Any] = getattr(stored, name)
        theirs: CitationField[Any] = getattr(derived, name)
        if name in stored.cleared_by_student or (
            mine.is_present and not mine.verified and mine.value != theirs.value
        ):
            kept[name] = mine
    marked = {"authors_are_organizations": stored.authors_are_organizations} if "authors" in kept else {}
    return derived.evolve(**kept, **marked, cleared_by_student=stored.cleared_by_student), tuple(kept)


# --------------------------------------------------------------------------------------------
# The service
# --------------------------------------------------------------------------------------------


class CitationService:
    """Resolves cites from stored snapshots and Crossref. Holds no state between calls."""

    def __init__(
        self,
        *,
        articles: ArticleRepository,
        snapshots: SnapshotService,
        edit_log: CardEditLog,
        doi_metadata: DoiMetadataSource | None = None,
    ) -> None:
        self._articles = articles
        self._snapshots = snapshots
        self._edit_log = edit_log
        self._doi_metadata = doi_metadata

    async def resolve(self, article: Article, source: LoadedSnapshot) -> CitationResolution:
        """The cite for a card cut from `source`, a checked load of one of `article`'s snapshots.

        Raises :class:`ValueError` when `source` is a snapshot of another article. A failed DOI
        lookup does not raise: it is logged, and the resolution says so.
        """
        snapshot = source.snapshot
        if snapshot.article_id != article.article_id:
            raise ValueError(
                f"snapshot {snapshot.snapshot_id} was taken of article {snapshot.article_id}, "
                f"not {article.article_id}"
            )
        mode = snapshot.provenance_mode
        if mode is ProvenanceMode.PUBLISHER_RETRIEVED:
            candidates = harvest_page(
                source.raw_bytes, content_type=snapshot.content_type, retrieved_url=snapshot.canonical_url
            )
        else:
            candidates = harvest_url(snapshot.canonical_url)
            if article.title != article.canonical_url:
                named = Harvested(article.title, _HEURISTIC, article.title)
                candidates = replace(candidates, title=(*candidates.title, named))
        dois = tuple(dict.fromkeys((*candidates.dois, *filter(None, [article.identifiers.doi]))))
        doi = dois[0] if dois else None
        work, outcome = await self._look_up(doi)
        citation = resolve_citation(candidates, work, provenance_mode=mode, accessed_at=snapshot.retrieved_at)
        return CitationResolution(citation=citation, provenance_mode=mode, doi=doi, crossref=outcome)

    async def re_resolve(self, card: Card) -> CitationResolution:
        """`card`'s cite resolved again from its snapshot, keeping a student's changed fields (ac5).

        Raises :class:`ValueError` for a card that quotes no snapshot. ``NotFound`` and
        ``SnapshotIntegrityError`` from reading its article or snapshot propagate.
        """
        if card.snapshot_id is None:
            raise ValueError(f"card {card.card_id} quotes no snapshot, so no source states its cite")
        article = await self._articles.get(card.article_id)
        loaded = await self._snapshots.load(await self._articles.get_snapshot(card.snapshot_id))
        derived = await self.resolve(article, loaded)
        entries = await self._edit_log.entries_for(card.card_id)
        if not any(entry.edit_kind is EditKind.EDIT_CITE for entry in entries):
            return derived
        citation, student_fields = keep_student_edits(card.citation, derived.citation)
        return replace(derived, citation=citation, student_fields=student_fields)

    async def _look_up(self, doi: str | None) -> tuple[DoiWork | None, CrossrefOutcome]:
        if doi is None:
            return None, CrossrefOutcome.NO_DOI
        if self._doi_metadata is None:
            return None, CrossrefOutcome.NOT_CONFIGURED
        try:
            work = await self._doi_metadata.lookup(doi)
        except ProviderUnavailable as failure:
            logger.warning(
                "DOI lookup failed; the cite is resolved from the page's own metadata",
                extra={"doi": doi, "provider": failure.provider, "reason": str(failure)},
            )
            return None, CrossrefOutcome.FAILED
        if work is None:
            return None, CrossrefOutcome.NOT_REGISTERED
        return work, CrossrefOutcome.FOUND


# --------------------------------------------------------------------------------------------
# Formatting
# --------------------------------------------------------------------------------------------

_MONTH_NAMES: Final = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)  # fmt: skip
_NAME_SUFFIXES: Final = frozenset({"jr", "sr", "ii", "iii", "iv", "phd", "md"})
_PROVENANCE_NOTES: Final = {
    ProvenanceMode.USER_SUPPLIED: "user-supplied text",
    ProvenanceMode.PASTED: "pasted text",
    ProvenanceMode.FILE_IMPORT: "imported from a debate file",
}
NO_AUTHOR: Final = "[no author]"
NO_DATE: Final = "ND"


def format_cite(citation: Citation, *, provenance_mode: ProvenanceMode) -> FormattedCite:
    """The short cite and the full cite line for `citation`; see the module docstring."""
    day = _stated_day(citation.published_at)
    short = f"{_short_name(citation)} {f'{day.year % 100:02d}' if day is not None else NO_DATE}"
    parts: list[str] = []
    names, credentials = citation.authors.value, citation.author_credentials.value
    if names:
        parts.append(_listed(names) + (f" ({credentials})" if credentials else ""))
    elif credentials:
        parts.append(f"({credentials})")
    if citation.title.value:
        parts.append(f'"{citation.title.value}"')
    if citation.publication.value:
        parts.append(citation.publication.value)
    if day is not None:
        parts.append(_long_date(day))
    if citation.canonical_url.value:
        parts.append(citation.canonical_url.value)
    if citation.accessed_at.value is not None:
        parts.append(f"accessed {_long_date(citation.accessed_at.value.astimezone(UTC).date())}")
    if (note := _PROVENANCE_NOTES.get(provenance_mode)) is not None:
        parts.append(note)
    fields: list[tuple[str, CitationField[Any]]] = [
        (name, getattr(citation, name)) for name in CITATION_FIELD_NAMES
    ]
    return FormattedCite(
        short_cite=short,
        full_cite=f"{short} [{'; '.join(parts)}]" if parts else short,
        unverified_fields=tuple(name for name, field in fields if field.is_present and not field.verified),
        missing_fields=tuple(name for name, field in fields if not field.is_present),
        provenance_mode=provenance_mode,
    )


def _short_name(citation: Citation) -> str:
    names = citation.authors.value
    if names:
        first = names[0] if citation.authors_are_organizations else _last_name(names[0])
        return first + (" et al." if len(names) > 1 else "")
    return citation.publication.value or citation.title.value or NO_AUTHOR


def _last_name(name: str) -> str:
    """'Smith' from 'Jane Smith', 'Smith, Jane' and 'Jane Smith Jr.'."""
    before, comma, after = name.partition(",")
    if comma and after.strip().rstrip(".").lower() not in _NAME_SUFFIXES:
        return before.strip() or name
    words = [word for word in before.split() if word.rstrip(".,").lower() not in _NAME_SUFFIXES]
    return words[-1] if words else name


def _listed(names: Sequence[str]) -> str:
    if len(names) <= 2:
        return " and ".join(names)
    return f"{', '.join(names[:-1])}, and {names[-1]}"


def _stated_day(published: CitationField[datetime]) -> date | None:
    """The day the source named: the stated date's own day when the raw text is a date that gives
    this instant (a late-evening time west of UTC is the next day in UTC), else the UTC day."""
    if published.value is None:
        return None
    stated = parse_stated_date(published.raw) if published.raw is not None else None
    if stated is not None and stated.moment == published.value:
        return stated.calendar_date
    return published.value.astimezone(UTC).date()


def _long_date(day: date) -> str:
    return f"{_MONTH_NAMES[day.month - 1]} {day.day}, {day.year}"

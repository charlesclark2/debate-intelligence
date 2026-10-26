"""CitationService (v1-e06-t01). Skeleton."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final

from debate_core.application.ports.card_edit_log import CardEditLog
from debate_core.application.ports.doi_metadata import DoiMetadataSource, DoiWork
from debate_core.application.ports.persistence import ArticleRepository
from debate_core.application.snapshot_service import LoadedSnapshot, SnapshotService
from debate_core.domain import Article, Card, Citation, ProvenanceMode
from debate_core.domain.enums import CitationFieldSource
from debate_core.retrieval.citation_harvest import CitationCandidates

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

SOURCE_PRECEDENCE: Final = (
    CitationFieldSource.CROSSREF,
    CitationFieldSource.JSON_LD,
    CitationFieldSource.META_TAG,
    CitationFieldSource.OPENGRAPH,
    CitationFieldSource.BYLINE,
    CitationFieldSource.HEURISTIC,
)

CITATION_FIELD_NAMES: Final = (
    "authors",
    "author_credentials",
    "title",
    "publication",
    "published_at",
    "canonical_url",
    "accessed_at",
)


class CrossrefOutcome(StrEnum):
    NO_DOI = "no_doi"
    NOT_CONFIGURED = "not_configured"
    FOUND = "found"
    NOT_REGISTERED = "not_registered"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class CitationResolution:
    citation: Citation
    provenance_mode: ProvenanceMode
    doi: str | None
    crossref: CrossrefOutcome
    student_fields: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FormattedCite:
    short_cite: str
    full_cite: str
    unverified_fields: tuple[str, ...]
    missing_fields: tuple[str, ...]
    provenance_mode: ProvenanceMode


def resolve_citation(
    candidates: CitationCandidates,
    work: DoiWork | None,
    *,
    provenance_mode: ProvenanceMode,
    accessed_at: datetime,
) -> Citation:
    return Citation()


def keep_student_edits(stored: Citation, derived: Citation) -> tuple[Citation, tuple[str, ...]]:
    return derived, ()


def format_cite(citation: Citation, *, provenance_mode: ProvenanceMode) -> FormattedCite:
    return FormattedCite("", "", (), (), provenance_mode)


class CitationService:
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
        return CitationResolution(Citation(), source.snapshot.provenance_mode, None, CrossrefOutcome.NO_DOI)

    async def re_resolve(self, card: Card) -> CitationResolution:
        return CitationResolution(Citation(), card.provenance_mode, None, CrossrefOutcome.NO_DOI)

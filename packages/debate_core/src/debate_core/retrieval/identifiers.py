"""DOI, arXiv and PMID detection (skeleton for the red run)."""

from __future__ import annotations

from dataclasses import dataclass

from debate_core.domain.article import ArticleIdentifiers

__all__ = ["ScholarlyIdentifiers", "detect_identifiers"]


@dataclass(frozen=True, slots=True)
class ScholarlyIdentifiers:
    dois: tuple[str, ...] = ()
    arxiv_ids: tuple[str, ...] = ()
    pmids: tuple[str, ...] = ()

    @property
    def is_empty(self) -> bool:
        return True

    def as_article_identifiers(self) -> ArticleIdentifiers:
        return ArticleIdentifiers()


def detect_identifiers(text: str) -> ScholarlyIdentifiers:
    return ScholarlyIdentifiers()

"""OpenAlex, the primary scholarly discovery provider (v1-e07-t02).

:class:`OpenAlexProvider` asks OpenAlex's `/works` endpoint for a query and maps each work to a
:class:`~debate_core.domain.discovery.CandidateResult`. It is a plain adapter: the registry wraps it
in :class:`~debate_core.integrations.discovery.resilience.ResilientProvider`, which times it,
benches it after repeated failures and holds it through a rate limit. It never ranks, deduplicates
(E08) or downloads full text (ArticleService fetches an open-access URL when it wants one).

**What is kept from a work** is what `CandidateResult` defines and no more: the DOI and the OpenAlex
id, the title, the authors' display names (never their affiliations or ORCIDs), the venue, the
publication date, the work's type as a :class:`~debate_core.domain.enums.SourceType`, the abstract
and the best open-access URL. A work with no title or no OpenAlex id is not a candidate and is
skipped; any other field OpenAlex leaves out, or sends in a shape this module does not read, is left
empty rather than failing the search.

**The abstract** arrives as an inverted index, word to positions, because OpenAlex does not ship
plain-text abstracts. :func:`rebuild_abstract` puts each word back at its positions. It is a
snippet for discovery only: card evidence comes from a stored snapshot, never from here.

**The venue** is `primary_location.source.display_name`. OpenAlex removed `host_venue`.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, date, datetime
from types import MappingProxyType
from typing import Any, Final, cast
from urllib.parse import urlsplit

from pydantic import ValidationError

from debate_core.domain.article import ArticleIdentifiers
from debate_core.domain.discovery import CandidateResult
from debate_core.domain.enums import SourceType

__all__ = [
    "PROVIDER_NAME",
    "SOURCE_TYPE_BY_WORK_TYPE",
    "candidate_from_work",
    "rebuild_abstract",
    "source_type_for",
]

PROVIDER_NAME: Final = "openalex"
"""The name settings enable this provider by, and every result carries."""

SOURCE_TYPE_BY_WORK_TYPE: Final[Mapping[str, SourceType]] = MappingProxyType(
    {
        "article": SourceType.SCHOLARLY,
        "book": SourceType.SCHOLARLY,
        "book-chapter": SourceType.SCHOLARLY,
        "book-review": SourceType.SCHOLARLY,
        "conference-abstract": SourceType.SCHOLARLY,
        "conference-paper": SourceType.SCHOLARLY,
        "data-paper": SourceType.SCHOLARLY,
        "dissertation": SourceType.SCHOLARLY,
        "editorial": SourceType.SCHOLARLY,
        "erratum": SourceType.SCHOLARLY,
        "letter": SourceType.SCHOLARLY,
        "peer-review": SourceType.SCHOLARLY,
        "preprint": SourceType.SCHOLARLY,
        "reference-entry": SourceType.SCHOLARLY,
        "retraction": SourceType.SCHOLARLY,
        "review": SourceType.SCHOLARLY,
        "software-paper": SourceType.SCHOLARLY,
        "report": SourceType.OTHER,
        "standard": SourceType.OTHER,
        "dataset": SourceType.OTHER,
        "libguides": SourceType.OTHER,
        "other": SourceType.OTHER,
        "paratext": SourceType.OTHER,
        "software": SourceType.OTHER,
        "supplementary-materials": SourceType.OTHER,
    }
)
"""OpenAlex's work types (help.openalex.org/data/work-types, read 2026-10-21) as source types.

Journal, book, conference and thesis content is scholarly. A `report` or a `standard` is `other`,
because its issuer may be a government, a think tank or a company and the work type does not say
which; data, code, front matter and library guides are not publications at all. A type OpenAlex adds
later is `other` until it is added here (:func:`source_type_for`).
"""


def source_type_for(work_type: object) -> SourceType:
    """The source type for an OpenAlex work type; `other` for any type not in the table."""
    if not isinstance(work_type, str):
        return SourceType.OTHER
    return SOURCE_TYPE_BY_WORK_TYPE.get(work_type, SourceType.OTHER)


def rebuild_abstract(inverted_index: object) -> str | None:
    """The abstract an OpenAlex `abstract_inverted_index` encodes, words in order; `None` when empty.

    The index maps each word to the positions it occupies (`{"in": [3, 57]}`). Every word goes back
    at each of its positions and the words are joined by single spaces in position order, which is
    how OpenAlex itself documents reading it. Entries that are not a word with a list of
    non-negative integer positions are ignored.
    """
    if not isinstance(inverted_index, Mapping):
        return None
    placed: dict[int, str] = {}
    for word, positions in cast(Mapping[object, object], inverted_index).items():
        if not isinstance(word, str) or not isinstance(positions, list):
            continue
        for position in cast(list[object], positions):
            if isinstance(position, int) and not isinstance(position, bool) and position >= 0:
                placed[position] = word
    text = " ".join(placed[position] for position in sorted(placed)).strip()
    return text or None


def candidate_from_work(work: Mapping[str, Any]) -> CandidateResult | None:
    """One OpenAlex work as a candidate; `None` for a work with no title or no OpenAlex id."""
    openalex_id = _openalex_id(work.get("id"))
    title = _text(work.get("display_name"))
    if openalex_id is None or title is None:
        return None
    doi = _doi(work.get("doi"))
    primary = _mapping(work.get("primary_location"))
    url = _http_url(primary.get("landing_page_url")) or (f"https://doi.org/{doi}" if doi else None)
    return CandidateResult(
        provider=PROVIDER_NAME,
        provider_record_id=openalex_id,
        title=title,
        url=url or f"https://openalex.org/{openalex_id}",
        identifiers=ArticleIdentifiers(doi=doi, openalex_id=openalex_id),
        source_type=source_type_for(work.get("type")),
        authors=_author_names(work.get("authorships")),
        publication=_text(_mapping(primary.get("source")).get("display_name")),
        published_at=_publication_date(work.get("publication_date")),
        snippet=rebuild_abstract(work.get("abstract_inverted_index")),
        open_access_url=_open_access_url(work),
    )


def _open_access_url(work: Mapping[str, Any]) -> str | None:
    """The best open copy: OpenAlex's best OA location, its PDF before its landing page.

    Falls back to `open_access.oa_url`, OpenAlex's own pick, when the work is open but carries no
    best location. A location that is not itself open is never used.
    """
    best = _mapping(work.get("best_oa_location"))
    if best.get("is_oa") is True:
        found = _http_url(best.get("pdf_url")) or _http_url(best.get("landing_page_url"))
        if found is not None:
            return found
    status = _mapping(work.get("open_access"))
    if status.get("is_oa") is True:
        return _http_url(status.get("oa_url"))
    return None


def _author_names(authorships: object) -> tuple[str, ...]:
    """The display names of the disambiguated authors, in byline order; nothing else of theirs."""
    if not isinstance(authorships, list):
        return ()
    names: list[str] = []
    for authorship in cast(list[object], authorships):
        name = _text(_mapping(_mapping(authorship).get("author")).get("display_name"))
        if name is not None:
            names.append(name)
    return tuple(names)


def _openalex_id(value: object) -> str | None:
    """`W2741809807` from `https://openalex.org/W2741809807` (or from the bare id)."""
    text = _text(value)
    if text is None:
        return None
    short = text.rstrip("/").rsplit("/", 1)[-1]
    if len(short) < 2 or short[0] != "W" or not short[1:].isdigit():
        return None
    return short


def _doi(value: object) -> str | None:
    """The bare lowercase DOI, or `None` when OpenAlex sent none or one that is not a DOI."""
    text = _text(value)
    if text is None:
        return None
    try:
        return ArticleIdentifiers(doi=text).doi
    except ValidationError:
        return None


def _publication_date(value: object) -> datetime | None:
    """Midnight UTC on OpenAlex's `YYYY-MM-DD` publication date."""
    text = _text(value)
    if text is None:
        return None
    try:
        day = date.fromisoformat(text)
    except ValueError:
        return None
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


def _http_url(value: object) -> str | None:
    """`value` when it is a URL `CandidateResult` accepts: absolute http(s), with a host, no spaces."""
    text = _text(value)
    if text is None or any(character.isspace() for character in text):
        return None
    parts = urlsplit(text)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None
    return text


def _text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _mapping(value: object) -> Mapping[str, Any]:
    return cast(Mapping[str, Any], value) if isinstance(value, Mapping) else {}

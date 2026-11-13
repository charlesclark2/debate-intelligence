"""Source-side entities: the article the platform found, and the snapshot it saved.

An :class:`Article` is *what* a source is — its canonical URL, title, authors and identifiers.
A :class:`SourceSnapshot` is *what was actually retrieved at one moment*: immutable bytes, their
hashes, and the versions of the extractor and normalizer that produced them.

Keeping them apart is what makes evidence verifiable. An article's metadata can be refreshed and
corrected; a snapshot never changes, so a card cut against a snapshot can always be re-checked
against exactly the text it was cut from (architecture proposal §8).
"""

from __future__ import annotations

import re
from typing import Self

from pydantic import Field, field_validator, model_validator

from debate_core.domain.base import (
    ORGANIZATION_ID_FIELD,
    OWNER_ID_FIELD,
    DomainEntity,
    DomainModel,
    HttpUrlStr,
    NonEmptyText,
    Sha256Hex,
    Ulid,
    UtcDatetime,
    new_id,
)
from debate_core.domain.citation import (
    CITATION_FIELD_NAMES,
    STATED_CITATION_FIELDS,
    Citation,
    CitationField,
)
from debate_core.domain.enums import AccessStatus, DatePrecision, ProvenanceMode, SourceType

__all__ = ["Article", "ArticleIdentifiers", "SourceSnapshot"]


_DOI_URL_PREFIXES = (
    "https://doi.org/",
    "http://doi.org/",
    "https://dx.doi.org/",
    "http://dx.doi.org/",
    "doi:",
)
_DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")
_PMID_RE = re.compile(r"^\d{1,9}$")


def _normalize_doi(value: str | None) -> str | None:
    """Reduce any accepted spelling of a DOI to its bare lowercase form.

    Providers hand back DOIs as bare strings, as `doi:` prefixed strings and as resolver URLs.
    They are normalized here, in the model, so that deduplication by DOI works no matter which
    adapter produced the value.
    """
    if value is None:
        return None
    candidate = value.strip()
    lowered = candidate.lower()
    for prefix in _DOI_URL_PREFIXES:
        if lowered.startswith(prefix):
            candidate = candidate[len(prefix) :]
            break
    candidate = candidate.strip().lower()
    if not _DOI_RE.match(candidate):
        raise ValueError(f"not a DOI (expected 10.NNNN/suffix, optionally as a doi.org URL): {value!r}")
    return candidate


class ArticleIdentifiers(DomainModel):
    """External identifiers for one source, used to deduplicate results across providers.

    Every field is optional: a news article usually has none of them, a journal article usually has
    several. Provider-specific payloads do not belong here — adapters keep those in their own
    result types (E07).
    """

    doi: NonEmptyText | None = Field(
        default=None, description="Bare lowercase DOI, for example 10.1038/nature12373."
    )
    arxiv_id: NonEmptyText | None = Field(default=None, description="arXiv identifier, e.g. 2301.00234.")
    pmid: NonEmptyText | None = Field(default=None, description="PubMed identifier, digits only.")
    openalex_id: NonEmptyText | None = Field(default=None, description="OpenAlex work id, e.g. W2741809807.")
    semantic_scholar_id: NonEmptyText | None = Field(default=None, description="Semantic Scholar paper id.")

    @field_validator("doi")
    @classmethod
    def _check_doi(cls, value: str | None) -> str | None:
        return _normalize_doi(value)

    @field_validator("pmid")
    @classmethod
    def _check_pmid(cls, value: str | None) -> str | None:
        if value is not None and not _PMID_RE.match(value):
            raise ValueError(f"PMID must be digits only: {value!r}")
        return value

    @property
    def is_empty(self) -> bool:
        """True when no external identifier is known for this source."""
        return all(
            value is None
            for value in (self.doi, self.arxiv_id, self.pmid, self.openalex_id, self.semantic_scholar_id)
        )


class Article(DomainEntity):
    """A source the platform knows about, identified by its canonical URL.

    An article is metadata only. Its text lives in :class:`SourceSnapshot` records, because text
    is what has to be hashed, versioned and held immutable.

    `access_status` is the latest known answer to "can we legitimately read this?"; it starts as
    `UNKNOWN` for an article that has only been discovered through search.
    """

    article_id: Ulid = Field(default_factory=new_id, description="ULID primary key.")
    owner_id: Ulid | None = Field(default=None, description=OWNER_ID_FIELD)
    organization_id: Ulid | None = Field(default=None, description=ORGANIZATION_ID_FIELD)
    canonical_url: HttpUrlStr = Field(description="The deduplicated, canonical http(s) URL of the source.")
    title: NonEmptyText = Field(description="Title as published.")
    authors: tuple[NonEmptyText, ...] = Field(
        default=(), description="Author names as published, in published order."
    )
    publication: NonEmptyText | None = Field(
        default=None, description="Publication, journal, outlet or issuing body."
    )
    published_at: UtcDatetime | None = Field(
        default=None, description="Publication timestamp in UTC; None when the source states no date."
    )
    date_precision: DatePrecision = Field(
        default=DatePrecision.DAY,
        exclude_if=lambda precision: precision is DatePrecision.DAY,
        description=(
            "How much of `published_at` is known (`v1-e06-t13`): `year` and `month` mean it is the first "
            "instant of that year or month, as a discovery provider stated it, and no day is known. `day`, "
            "the default, is what every Article stored before this field held, and is left out of the "
            "stored record."
        ),
    )
    source_type: SourceType = Field(
        default=SourceType.OTHER,
        description="Descriptive category of the publication, never a quality score.",
    )
    access_status: AccessStatus = Field(
        default=AccessStatus.UNKNOWN, description="Most recent retrieval outcome for this source."
    )
    identifiers: ArticleIdentifiers = Field(
        default_factory=ArticleIdentifiers, description="External identifiers used for deduplication."
    )


class SourceSnapshot(DomainEntity):
    """An immutable record of one retrieval of one source.

    A snapshot is the anchor of evidence integrity. It records the SHA-256 of the exact bytes that
    came back, the SHA-256 of the deterministically normalized text derived from them, and the
    versions of the code that produced each, so a card's evidence can be reconstructed and
    re-checked later (architecture proposal §8, steps 1-2 and 5).

    Blob keys are storage-neutral strings resolved by the `SnapshotStore` port, not S3 keys: V1
    stores blobs on the local filesystem and V2 stores them in S3 without the entity changing.

    Snapshots are never rewritten. `revision` therefore stays at 1; re-retrieving a source produces
    a new snapshot rather than mutating this one.
    """

    snapshot_id: Ulid = Field(default_factory=new_id, description="ULID primary key.")
    owner_id: Ulid | None = Field(default=None, description=OWNER_ID_FIELD)
    organization_id: Ulid | None = Field(default=None, description=ORGANIZATION_ID_FIELD)
    article_id: Ulid = Field(description="The article this snapshot was taken of.")
    canonical_url: HttpUrlStr = Field(description="The URL actually retrieved, after redirects.")
    retrieved_at: UtcDatetime = Field(description="When the retrieval happened, in UTC.")
    access_status: AccessStatus = Field(description="How the retrieval was classified.")
    provenance_mode: ProvenanceMode = Field(description="Whether the platform or a user supplied this text.")
    raw_blob_key: NonEmptyText = Field(description="SnapshotStore key of the exact bytes received.")
    normalized_blob_key: NonEmptyText = Field(
        description="SnapshotStore key of the normalized text and its paragraph map."
    )
    sha256: Sha256Hex = Field(description="SHA-256 of the raw bytes, as stored.")
    normalized_text_hash: Sha256Hex = Field(description="SHA-256 of the normalized text, UTF-8, no BOM.")
    extractor_version: NonEmptyText = Field(description="Version of the extractor that produced the text.")
    normalizer_version: NonEmptyText = Field(
        description="Version of the normalizer; re-verification must use this same version."
    )
    content_type: NonEmptyText | None = Field(
        default=None, description="Content type reported by the source, if any."
    )
    byte_size: int | None = Field(default=None, ge=0, description="Size of the raw blob in bytes.")
    stated_citation: Citation | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
        description=(
            "Cite fields the user stated when they supplied this text (`v1-e06-t12`): the title, authors, "
            "publication and date, never verified. Only a USER_SUPPLIED snapshot has them. Left out of the "
            "stored record when there are none, so a snapshot stated nothing for is stored as before."
        ),
    )

    @model_validator(mode="after")
    def _check_stated_citation(self) -> Self:
        stated = self.stated_citation
        if stated is None:
            return self
        if self.provenance_mode is not ProvenanceMode.USER_SUPPLIED:
            raise ValueError("only a USER_SUPPLIED snapshot carries cite fields its user stated")
        fields: dict[str, CitationField[object]] = {
            name: getattr(stated, name) for name in CITATION_FIELD_NAMES
        }
        if claimed := [name for name, field in fields.items() if field.verified]:
            raise ValueError(f"a stated cite field is never verified: {', '.join(claimed)}")
        if others := [n for n, f in fields.items() if f.is_present and n not in STATED_CITATION_FIELDS]:
            stateable = ", ".join(STATED_CITATION_FIELDS)
            raise ValueError(f"a user states only {stateable}, not {', '.join(others)}")
        if not any(field.is_present for field in fields.values()):
            raise ValueError("a stated cite that states nothing is no stated cite; leave it out")
        return self

"""Article, ArticleIdentifiers and SourceSnapshot: the source side of the domain."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from debate_core.domain import (
    AccessStatus,
    Article,
    ArticleIdentifiers,
    ProvenanceMode,
    SourceSnapshot,
    SourceType,
    new_id,
)

RAW_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
NORMALIZED_SHA256 = "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"


def make_article(**overrides: object) -> Article:
    """An Article with every required field filled in, for tests that vary one thing."""
    fields: dict[str, object] = {
        "canonical_url": "https://example.org/climate-2026",
        "title": "Rising seas and coastal infrastructure",
    }
    fields.update(overrides)
    return Article.model_validate(fields)


def make_snapshot(**overrides: object) -> SourceSnapshot:
    """A SourceSnapshot with every required field filled in."""
    fields: dict[str, object] = {
        "article_id": new_id(),
        "canonical_url": "https://example.org/climate-2026",
        "retrieved_at": datetime(2026, 9, 17, 14, 30, tzinfo=UTC),
        "access_status": AccessStatus.ACCESSIBLE,
        "provenance_mode": ProvenanceMode.PUBLISHER_RETRIEVED,
        "raw_blob_key": "snapshots/01ARZ3NDEKTSV4RRFFQ69G5FAV/raw.html",
        "normalized_blob_key": "snapshots/01ARZ3NDEKTSV4RRFFQ69G5FAV/normalized.json",
        "sha256": RAW_SHA256,
        "normalized_text_hash": NORMALIZED_SHA256,
        "extractor_version": "trafilatura-1.12.0",
        "normalizer_version": "1",
    }
    fields.update(overrides)
    return SourceSnapshot.model_validate(fields)


# --------------------------------------------------------------------------------------------
# Article
# --------------------------------------------------------------------------------------------


def test_article_has_the_section_7_key_fields() -> None:
    article = make_article(
        authors=("Jane Rivera", "Samir Osei"),
        publication="Journal of Coastal Policy",
        published_at=datetime(2026, 3, 1, tzinfo=UTC),
        source_type=SourceType.SCHOLARLY,
        access_status=AccessStatus.ACCESSIBLE,
        owner_id=new_id(),
        organization_id=new_id(),
    )
    assert article.article_id
    assert article.canonical_url == "https://example.org/climate-2026"
    assert article.title == "Rising seas and coastal infrastructure"
    assert article.authors == ("Jane Rivera", "Samir Osei")
    assert article.publication == "Journal of Coastal Policy"
    assert article.source_type is SourceType.SCHOLARLY
    assert article.access_status is AccessStatus.ACCESSIBLE
    assert article.revision == 1


def test_a_discovered_article_starts_with_unknown_access() -> None:
    article = make_article()
    assert article.access_status is AccessStatus.UNKNOWN
    assert article.source_type is SourceType.OTHER
    assert article.identifiers.is_empty


def test_article_round_trips_through_json() -> None:
    article = make_article(
        authors=("Jane Rivera",),
        published_at=datetime(2026, 3, 1, 9, 30, 15, 123456, tzinfo=UTC),
        source_type=SourceType.NEWS,
        identifiers=ArticleIdentifiers(doi="10.1038/nature12373", pmid="12345678"),
        owner_id=new_id(),
    )
    assert Article.model_validate_json(article.model_dump_json()) == article


def test_article_title_is_required() -> None:
    with pytest.raises(ValidationError):
        Article.model_validate({"canonical_url": "https://example.org/a"})


# --------------------------------------------------------------------------------------------
# Identifiers
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "supplied",
    [
        "10.1038/NATURE12373",
        "https://doi.org/10.1038/nature12373",
        "http://dx.doi.org/10.1038/Nature12373",
        "doi:10.1038/nature12373",
        "  10.1038/nature12373  ",
    ],
)
def test_dois_are_normalized_to_their_bare_lowercase_form(supplied: str) -> None:
    assert ArticleIdentifiers(doi=supplied).doi == "10.1038/nature12373"


@pytest.mark.parametrize("supplied", ["nature12373", "10.x/abc", "https://example.org/paper", "10.1038/"])
def test_malformed_dois_are_rejected(supplied: str) -> None:
    with pytest.raises(ValidationError):
        ArticleIdentifiers(doi=supplied)


def test_pmid_must_be_digits() -> None:
    assert ArticleIdentifiers(pmid="12345678").pmid == "12345678"
    with pytest.raises(ValidationError):
        ArticleIdentifiers(pmid="PMID12345678")


def test_identifiers_are_all_optional() -> None:
    identifiers = ArticleIdentifiers()
    assert identifiers.is_empty
    assert not ArticleIdentifiers(arxiv_id="2301.00234").is_empty


# --------------------------------------------------------------------------------------------
# SourceSnapshot
# --------------------------------------------------------------------------------------------


def test_snapshot_records_both_hashes_and_both_versions() -> None:
    snapshot = make_snapshot(byte_size=48123, content_type="text/html; charset=utf-8")
    assert snapshot.sha256 == RAW_SHA256
    assert snapshot.normalized_text_hash == NORMALIZED_SHA256
    assert snapshot.extractor_version == "trafilatura-1.12.0"
    assert snapshot.normalizer_version == "1"
    assert snapshot.retrieved_at.tzinfo is UTC
    assert snapshot.provenance_mode is ProvenanceMode.PUBLISHER_RETRIEVED


def test_snapshot_round_trips_through_json() -> None:
    snapshot = make_snapshot(byte_size=1024)
    assert SourceSnapshot.model_validate_json(snapshot.model_dump_json()) == snapshot


@pytest.mark.parametrize(
    "field",
    [
        "article_id",
        "canonical_url",
        "retrieved_at",
        "access_status",
        "provenance_mode",
        "raw_blob_key",
        "normalized_blob_key",
        "sha256",
        "normalized_text_hash",
        "extractor_version",
        "normalizer_version",
    ],
)
def test_snapshot_provenance_fields_are_all_required(field: str) -> None:
    fields = make_snapshot().model_dump()
    del fields[field]
    with pytest.raises(ValidationError):
        SourceSnapshot.model_validate(fields)


@pytest.mark.parametrize(
    "digest",
    [
        "",
        "not-a-hash",
        "E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855",  # uppercase
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b85",  # 63 characters
    ],
)
def test_snapshot_hashes_must_be_lowercase_sha256_hex(digest: str) -> None:
    with pytest.raises(ValidationError):
        make_snapshot(sha256=digest)


def test_snapshot_provenance_mode_has_no_default() -> None:
    fields = make_snapshot().model_dump()
    del fields["provenance_mode"]
    with pytest.raises(ValidationError) as caught:
        SourceSnapshot.model_validate(fields)
    assert "provenance_mode" in str(caught.value)


def test_snapshot_rejects_a_naive_retrieved_at() -> None:
    with pytest.raises(ValidationError):
        make_snapshot(retrieved_at=datetime(2026, 9, 17, 14, 30))  # deliberately naive

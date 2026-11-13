"""Article, ArticleIdentifiers and SourceSnapshot: the source side of the domain."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from debate_core.domain import (
    AccessStatus,
    Article,
    ArticleIdentifiers,
    Citation,
    CitationField,
    CitationFieldSource,
    ProvenanceMode,
    SourceSnapshot,
    SourceType,
    new_id,
)
from debate_core.domain.enums import DatePrecision

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


# --------------------------------------------------------------------------------------------
# SourceSnapshot.stated_citation: cite fields a user stated for their copy (v1-e06-t12)
# --------------------------------------------------------------------------------------------

STATED_AT = datetime(2026, 8, 30, tzinfo=UTC)


def stated(**fields: CitationField[Any]) -> Citation:
    """A stated cite: the fields given, else a title, each unverified and heuristic."""
    given: dict[str, Any] = fields or {"title": heuristic("Basin Councils After the Dry Summer")}
    return Citation.model_validate(given)


def heuristic(
    value: Any, *, verified: bool = False, source: CitationFieldSource = CitationFieldSource.HEURISTIC
) -> CitationField[Any]:
    return CitationField[Any](value=value, source=source, verified=verified, raw=str(value))


def test_a_user_supplied_snapshot_carries_its_stated_citation_through_json() -> None:
    citation = stated(
        authors=heuristic(("Mara Okonkwo-Lindqvist", "Teodor Brannigan")),
        title=heuristic("Basin Councils After the Dry Summer"),
        publication=heuristic("The Quarterly Watershed"),
        published_at=heuristic(STATED_AT),
    )
    snapshot = make_snapshot(provenance_mode=ProvenanceMode.USER_SUPPLIED, stated_citation=citation)

    assert SourceSnapshot.model_validate_json(snapshot.model_dump_json()) == snapshot
    assert snapshot.stated_citation == citation


@pytest.mark.parametrize(
    "mode", [mode for mode in ProvenanceMode if mode is not ProvenanceMode.USER_SUPPLIED]
)
def test_only_a_user_supplied_snapshot_may_carry_a_stated_citation(mode: ProvenanceMode) -> None:
    with pytest.raises(ValidationError, match="USER_SUPPLIED"):
        make_snapshot(provenance_mode=mode, stated_citation=stated())


@pytest.mark.parametrize("name", ["authors", "title", "publication", "published_at"])
def test_a_stated_citation_with_a_field_marked_verified_is_refused(name: str) -> None:
    values: dict[str, Any] = {
        "authors": ("Mara Okonkwo-Lindqvist",),
        "title": "Basin Councils After the Dry Summer",
        "publication": "The Quarterly Watershed",
        "published_at": STATED_AT,
    }
    claimed = stated(**{name: heuristic(values[name], verified=True, source=CitationFieldSource.BYLINE)})

    with pytest.raises(ValidationError, match="verified"):
        make_snapshot(provenance_mode=ProvenanceMode.USER_SUPPLIED, stated_citation=claimed)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("author_credentials", "Hydrologist"),
        ("canonical_url", "https://example.org/climate-2026"),
        ("accessed_at", STATED_AT),
    ],
)
def test_a_stated_citation_holds_only_the_fields_a_user_states(name: str, value: Any) -> None:
    with pytest.raises(ValidationError, match="states"):
        make_snapshot(
            provenance_mode=ProvenanceMode.USER_SUPPLIED,
            stated_citation=stated(title=heuristic("A title"), **{name: heuristic(value)}),
        )


def test_a_stated_citation_that_states_nothing_is_refused() -> None:
    with pytest.raises(ValidationError, match="nothing"):
        make_snapshot(provenance_mode=ProvenanceMode.USER_SUPPLIED, stated_citation=Citation())


SNAPSHOT_DOCUMENT_BEFORE_T12 = (
    '{"created_at":"2026-09-17T14:30:00Z","updated_at":"2026-09-17T14:30:00Z","revision":1,'
    '"snapshot_id":"01ARZ3NDEKTSV4RRFFQ69G5FB0","owner_id":null,"organization_id":null,'
    '"article_id":"01ARZ3NDEKTSV4RRFFQ69G5FAA","canonical_url":"https://example.org/a",'
    '"retrieved_at":"2026-09-17T14:30:00Z","access_status":"UNKNOWN","provenance_mode":"{mode}",'
    '"raw_blob_key":"raw","normalized_blob_key":"norm","sha256":"' + "0" * 64 + '",'
    '"normalized_text_hash":"' + "1" * 64 + '","extractor_version":"x","normalizer_version":"1",'
    '"content_type":"text/plain; charset=utf-8","byte_size":5}'
)
"""A snapshot's stored document as every build before `v1-e06-t12` wrote it, written by hand."""


@pytest.mark.parametrize("mode", list(ProvenanceMode))
def test_a_snapshot_with_no_stated_citation_is_stored_byte_for_byte_as_before(mode: ProvenanceMode) -> None:
    """The SQLite row's document is `model_dump_json()`; with nothing stated it gains no key, so every
    existing row, and every snapshot of any provenance stored without stated fields, is unchanged."""
    moment = datetime(2026, 9, 17, 14, 30, tzinfo=UTC)
    snapshot = SourceSnapshot(
        snapshot_id="01ARZ3NDEKTSV4RRFFQ69G5FB0",
        article_id="01ARZ3NDEKTSV4RRFFQ69G5FAA",
        canonical_url="https://example.org/a",
        retrieved_at=moment,
        created_at=moment,
        updated_at=moment,
        access_status=AccessStatus.UNKNOWN,
        provenance_mode=mode,
        raw_blob_key="raw",
        normalized_blob_key="norm",
        sha256="0" * 64,
        normalized_text_hash="1" * 64,
        extractor_version="x",
        normalizer_version="1",
        content_type="text/plain; charset=utf-8",
        byte_size=5,
    )

    assert snapshot.model_dump_json() == SNAPSHOT_DOCUMENT_BEFORE_T12.replace("{mode}", mode.value)
    assert (
        SourceSnapshot.model_validate_json(SNAPSHOT_DOCUMENT_BEFORE_T12.replace("{mode}", mode.value))
        == snapshot
    )


# --------------------------------------------------------------------------------------------
# An Article's date precision (v1-e06-t13)
# --------------------------------------------------------------------------------------------


def test_an_article_dates_to_the_day_unless_it_says_otherwise() -> None:
    article = make_article(published_at=datetime(2021, 3, 4, tzinfo=UTC))

    assert article.date_precision is DatePrecision.DAY
    assert "date_precision" not in article.model_dump()


@pytest.mark.parametrize(
    ("moment", "precision"),
    [
        (datetime(2021, 1, 1, tzinfo=UTC), DatePrecision.YEAR),
        (datetime(2021, 3, 1, tzinfo=UTC), DatePrecision.MONTH),
    ],
    ids=["year", "month"],
)
def test_an_articles_year_or_month_is_kept_beside_its_date_through_json(
    moment: datetime, precision: DatePrecision
) -> None:
    article = make_article(published_at=moment, date_precision=precision)

    assert article.model_dump()["date_precision"] == precision.value
    assert Article.model_validate_json(article.model_dump_json()) == article


@pytest.mark.parametrize(
    ("moment", "precision", "message"),
    [
        (datetime(2021, 3, 4, tzinfo=UTC), DatePrecision.YEAR, "first instant of its year"),
        (datetime(2021, 3, 4, tzinfo=UTC), DatePrecision.MONTH, "first instant of its month"),
        (None, DatePrecision.YEAR, "no date"),
    ],
    ids=["a day as a year", "a day as a month", "no date"],
)
def test_an_article_never_gives_a_date_a_precision_it_does_not_have(
    moment: datetime | None, precision: DatePrecision, message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        make_article(published_at=moment, date_precision=precision)

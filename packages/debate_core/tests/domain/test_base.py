"""The shared primitives: model behaviour, constrained scalars and the injectable id factory."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from itertools import count

import pytest
from pydantic import ValidationError

from debate_core.domain import (
    CROCKFORD_BASE32_ALPHABET,
    EXPORTED_MODELS,
    Article,
    Card,
    DomainEntity,
    DomainModel,
    ProvenanceMode,
    new_id,
    use_id_factory,
    utc_now,
)


class _Example(DomainModel):
    name: str
    count: int = 0


def test_domain_models_are_frozen() -> None:
    model = _Example(name="a")
    attribute = "name"  # via a variable: assigning directly is also a static type error
    with pytest.raises(ValidationError):
        setattr(model, attribute, "b")


def test_domain_models_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError) as caught:
        _Example.model_validate({"name": "a", "nmae": "typo"})
    assert "nmae" in str(caught.value)


def test_evolve_returns_a_changed_copy() -> None:
    model = _Example(name="a", count=1)
    evolved = model.evolve(count=2)
    assert evolved.count == 2
    assert evolved.name == "a"
    assert model.count == 1


def test_evolve_revalidates_so_invariants_cannot_be_bypassed() -> None:
    card = Card(
        owner_id=new_id(),
        article_id=new_id(),
        tag="Warming is anthropogenic",
        provenance_mode=ProvenanceMode.PUBLISHER_RETRIEVED,
    )
    with pytest.raises(ValidationError):
        card.evolve(evidence_text="text with no snapshot behind it")


def test_utc_now_is_timezone_aware() -> None:
    assert utc_now().tzinfo is UTC


# --------------------------------------------------------------------------------------------
# ULIDs
# --------------------------------------------------------------------------------------------


def test_generated_ids_are_canonical_ulids() -> None:
    identifier = new_id()
    assert len(identifier) == 26
    assert set(identifier) <= set(CROCKFORD_BASE32_ALPHABET)


def test_generated_ids_sort_by_creation_time() -> None:
    identifiers = [new_id() for _ in range(50)]
    assert identifiers == sorted(identifiers)


@pytest.mark.parametrize(
    "identifier",
    [
        "",
        "01ARZ3NDEKTSV4RRFFQ69G5FA",  # 25 characters
        "01ARZ3NDEKTSV4RRFFQ69G5FAVX",  # 27 characters
        "81ARZ3NDEKTSV4RRFFQ69G5FAV",  # first character above 7: timestamp overflow
        "01ARZ3NDEKTSV4RRFFQ69G5FAI",  # I is not in the Crockford alphabet
        "01arz3ndektsv4rrffq69g5fav",  # lowercase
        "01ARZ3NDEK-TSV4RRFFQ69G5F",
    ],
)
def test_ulid_fields_reject_malformed_ids(identifier: str) -> None:
    with pytest.raises(ValidationError):
        Article(article_id=identifier, canonical_url="https://example.org/a", title="Title")


def test_id_factory_is_injectable() -> None:
    counter = count(1)

    def deterministic_id() -> str:
        return f"01ARZ3NDEKTSV4RRFFQ69G5{next(counter):03d}"

    with use_id_factory(deterministic_id):
        first = Article(canonical_url="https://example.org/a", title="One")
        second = Article(canonical_url="https://example.org/b", title="Two")

    assert first.article_id == "01ARZ3NDEKTSV4RRFFQ69G5001"
    assert second.article_id == "01ARZ3NDEKTSV4RRFFQ69G5002"
    assert Article(canonical_url="https://example.org/c", title="Three").article_id != first.article_id


def test_id_factory_override_is_undone_on_error() -> None:
    def deterministic_id() -> str:
        return "01ARZ3NDEKTSV4RRFFQ69G5FAV"

    with pytest.raises(RuntimeError), use_id_factory(deterministic_id):
        raise RuntimeError("boom")

    assert new_id() != "01ARZ3NDEKTSV4RRFFQ69G5FAV"


# --------------------------------------------------------------------------------------------
# Timestamps
# --------------------------------------------------------------------------------------------


def test_naive_datetimes_are_rejected() -> None:
    with pytest.raises(ValidationError) as caught:
        Article(
            canonical_url="https://example.org/a",
            title="Title",
            published_at=datetime(2026, 9, 17, 12, 0, 0),  # deliberately naive
        )
    assert "timezone-aware" in str(caught.value)


def test_naive_datetime_strings_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Article.model_validate(
            {
                "canonical_url": "https://example.org/a",
                "title": "Title",
                "published_at": "2026-09-17T12:00:00",
            }
        )


def test_aware_datetimes_are_normalized_to_utc() -> None:
    eastern = timezone(timedelta(hours=-4))
    article = Article(
        canonical_url="https://example.org/a",
        title="Title",
        published_at=datetime(2026, 9, 17, 8, 0, 0, tzinfo=eastern),
    )
    assert article.published_at == datetime(2026, 9, 17, 12, 0, 0, tzinfo=UTC)
    assert article.published_at is not None
    assert article.published_at.tzinfo is UTC


# --------------------------------------------------------------------------------------------
# Entity base fields
# --------------------------------------------------------------------------------------------


def test_entities_carry_tenancy_timestamps_and_a_revision() -> None:
    article = Article(canonical_url="https://example.org/a", title="Title")
    assert isinstance(article, DomainEntity)
    assert article.owner_id is None
    assert article.organization_id is None
    assert article.revision == 1
    assert article.created_at.tzinfo is UTC
    assert article.updated_at.tzinfo is UTC


@pytest.mark.parametrize("model", EXPORTED_MODELS, ids=lambda model: model.__name__)
def test_every_entity_carries_tenancy_and_audit_fields(model: type[DomainModel]) -> None:
    """Entities are tenant-scoped and versioned; value objects belong to their parent entity."""
    fields = set(model.model_fields)
    if not issubclass(model, DomainEntity):
        assert fields.isdisjoint({"owner_id", "organization_id", "revision"})
        return
    assert {"owner_id", "organization_id", "created_at", "updated_at", "revision"} <= fields


def test_revision_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        Article(canonical_url="https://example.org/a", title="Title", revision=0)


@pytest.mark.parametrize(
    "url",
    ["", "example.org/a", "ftp://example.org/a", "file:///etc/passwd", "https:///a", "https://ex ample.org"],
)
def test_urls_must_be_absolute_http(url: str) -> None:
    with pytest.raises(ValidationError):
        Article(canonical_url=url, title="Title")


def test_urls_are_not_rewritten() -> None:
    url = "https://example.org/Some/Path?b=2&a=1"
    assert Article(canonical_url=url, title="Title").canonical_url == url


def test_non_empty_text_is_stripped_and_must_not_be_blank() -> None:
    assert Article(canonical_url="https://example.org/a", title="  Title  ").title == "Title"
    with pytest.raises(ValidationError):
        Article(canonical_url="https://example.org/a", title="   ")

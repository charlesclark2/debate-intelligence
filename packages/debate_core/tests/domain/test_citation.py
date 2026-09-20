"""Citation and CitationField: a cite that knows where each of its parts came from."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from debate_core.domain import (
    REQUIRED_CITATION_FIELDS,
    Citation,
    CitationField,
    CitationFieldSource,
)


def verified_citation() -> Citation:
    """A cite whose every required field is verified against page metadata."""
    return Citation(
        authors=CitationField[tuple[str, ...]](
            value=("Jane Rivera",), source=CitationFieldSource.META_TAG, verified=True
        ),
        title=CitationField[str](value="Rising seas", source=CitationFieldSource.META_TAG, verified=True),
        publication=CitationField[str](
            value="Journal of Coastal Policy", source=CitationFieldSource.CROSSREF, verified=True
        ),
        published_at=CitationField[datetime](
            value=datetime(2026, 3, 1, tzinfo=UTC), source=CitationFieldSource.JSON_LD, verified=True
        ),
        canonical_url=CitationField[str](
            value="https://example.org/climate-2026", source=CitationFieldSource.OPENGRAPH, verified=True
        ),
    )


# --------------------------------------------------------------------------------------------
# CitationField
# --------------------------------------------------------------------------------------------


def test_a_field_defaults_to_missing_and_unverified() -> None:
    field = CitationField[str]()
    assert field.value is None
    assert field.source is CitationFieldSource.MISSING
    assert field.verified is False
    assert field.is_present is False


def test_a_missing_field_cannot_hold_a_value() -> None:
    with pytest.raises(ValidationError) as caught:
        CitationField[str](value="Jane Rivera")
    assert "cannot hold a value" in str(caught.value)


def test_a_missing_field_cannot_be_verified() -> None:
    with pytest.raises(ValidationError):
        CitationField[str](source=CitationFieldSource.MISSING, verified=True)


def test_a_verified_field_must_have_a_value() -> None:
    with pytest.raises(ValidationError) as caught:
        CitationField[str](source=CitationFieldSource.META_TAG, verified=True)
    assert "must have a value" in str(caught.value)


def test_a_heuristic_guess_can_never_be_verified() -> None:
    guessed = CitationField[str](value="2026-03-01", source=CitationFieldSource.HEURISTIC, raw="/2026/03/")
    assert guessed.is_present
    assert guessed.verified is False

    with pytest.raises(ValidationError) as caught:
        CitationField[str](value="2026-03-01", source=CitationFieldSource.HEURISTIC, verified=True)
    assert "cannot be marked verified" in str(caught.value)


def test_a_field_keeps_the_raw_text_it_was_read_from() -> None:
    field = CitationField[str](
        value="Jane Rivera",
        source=CitationFieldSource.BYLINE,
        verified=True,
        raw="By Jane Rivera, staff writer",
    )
    assert field.raw == "By Jane Rivera, staff writer"


def test_field_values_are_typed_by_their_parameter() -> None:
    # Validated from JSON-ish input, as a harvester would: the wrong type is a runtime failure.
    with pytest.raises(ValidationError):
        CitationField[datetime].model_validate({"value": "not a date", "source": "meta_tag"})


def test_a_published_at_field_rejects_a_naive_datetime() -> None:
    with pytest.raises(ValidationError):
        Citation(
            published_at=CitationField[datetime](
                value=datetime(2026, 3, 1),  # deliberately naive
                source=CitationFieldSource.META_TAG,
            )
        )


# --------------------------------------------------------------------------------------------
# Citation
# --------------------------------------------------------------------------------------------


def test_an_empty_citation_is_all_missing_and_not_verified() -> None:
    citation = Citation()
    assert citation.is_fully_verified is False
    assert citation.unverified_fields == REQUIRED_CITATION_FIELDS
    assert citation.authors.source is CitationFieldSource.MISSING


def test_a_fully_harvested_citation_is_verified() -> None:
    citation = verified_citation()
    assert citation.unverified_fields == ()
    assert citation.is_fully_verified is True


def test_author_credentials_and_accessed_date_are_not_required() -> None:
    citation = verified_citation()
    assert citation.author_credentials.source is CitationFieldSource.MISSING
    assert citation.accessed_at.source is CitationFieldSource.MISSING
    assert citation.is_fully_verified is True


def test_one_unverified_field_is_reported_by_name() -> None:
    citation = verified_citation().evolve(publication=CitationField[str]())
    assert citation.unverified_fields == ("publication",)
    assert citation.is_fully_verified is False


def test_required_fields_are_the_cite_line_essentials() -> None:
    assert REQUIRED_CITATION_FIELDS == ("authors", "title", "publication", "published_at", "canonical_url")


def test_citation_round_trips_through_json() -> None:
    citation = verified_citation().evolve(
        author_credentials=CitationField[str](
            value="professor of coastal engineering, Rice University",
            source=CitationFieldSource.JSON_LD,
            verified=True,
            raw="Jane Rivera is professor of coastal engineering at Rice University.",
        ),
        accessed_at=CitationField[datetime](
            value=datetime(2026, 9, 17, 14, 30, tzinfo=UTC),
            source=CitationFieldSource.CROSSREF,
            verified=True,
        ),
    )
    assert Citation.model_validate_json(citation.model_dump_json()) == citation

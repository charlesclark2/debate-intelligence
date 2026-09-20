"""Card and CardSpan: the invariants that keep quoted evidence traceable to a snapshot."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from debate_core.domain import (
    DEFAULT_FORMAT_PROFILE,
    Card,
    CardSpan,
    Citation,
    CitationField,
    CitationFieldSource,
    ProvenanceMode,
    SpanPurpose,
    SpanStyle,
    VerificationStatus,
    new_id,
)

EVIDENCE = "Sea level rise of one metre would displace roughly 230 million people worldwide."
NORMALIZED_SHA256 = "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"


def make_span(**overrides: object) -> CardSpan:
    """An underline span covering the first clause of EVIDENCE."""
    fields: dict[str, object] = {"start_offset": 0, "end_offset": 26, "style": SpanStyle.UNDERLINE}
    fields.update(overrides)
    return CardSpan.model_validate(fields)


def make_card(**overrides: object) -> Card:
    """A card with no evidence yet: the state right after a cut is requested."""
    fields: dict[str, object] = {
        "owner_id": new_id(),
        "article_id": new_id(),
        "tag": "Sea level rise displaces hundreds of millions",
        "provenance_mode": ProvenanceMode.PUBLISHER_RETRIEVED,
    }
    fields.update(overrides)
    return Card.model_validate(fields)


def make_cut_card(**overrides: object) -> Card:
    """A card whose evidence has been extracted from a snapshot but not yet verified."""
    fields: dict[str, object] = {
        "snapshot_id": new_id(),
        "evidence_text": EVIDENCE,
        "evidence_start_offset": 1840,
        "evidence_end_offset": 1840 + len(EVIDENCE),
        "normalized_text_hash": NORMALIZED_SHA256,
        "normalizer_version": "1",
        "spans": (make_span(),),
    }
    fields.update(overrides)
    return make_card(**fields)


# --------------------------------------------------------------------------------------------
# CardSpan
# --------------------------------------------------------------------------------------------


def test_span_carries_offsets_style_and_purpose() -> None:
    span = make_span(end_offset=40, purpose=SpanPurpose.IMPACT)
    assert span.span_id
    assert span.start_offset == 0
    assert span.end_offset == 40
    assert span.length == 40
    assert span.style is SpanStyle.UNDERLINE
    assert span.purpose is SpanPurpose.IMPACT


def test_span_purpose_is_optional() -> None:
    assert make_span().purpose is None


@pytest.mark.parametrize(("start", "end"), [(10, 10), (10, 5), (0, 0)])
def test_span_start_must_precede_end(start: int, end: int) -> None:
    with pytest.raises(ValidationError):
        CardSpan(start_offset=start, end_offset=end, style=SpanStyle.UNDERLINE)


@pytest.mark.parametrize(("start", "end"), [(-1, 5), (-5, -1)])
def test_span_offsets_must_be_non_negative(start: int, end: int) -> None:
    with pytest.raises(ValidationError):
        CardSpan(start_offset=start, end_offset=end, style=SpanStyle.UNDERLINE)


def test_span_overlap_detection() -> None:
    first = make_span(start_offset=0, end_offset=10)
    assert first.overlaps(make_span(start_offset=9, end_offset=20))
    assert not first.overlaps(make_span(start_offset=10, end_offset=20))


def test_span_round_trips_through_json() -> None:
    span = make_span(purpose=SpanPurpose.WARRANT, style=SpanStyle.HIGHLIGHT)
    assert CardSpan.model_validate_json(span.model_dump_json()) == span


# --------------------------------------------------------------------------------------------
# Card: shape and defaults
# --------------------------------------------------------------------------------------------


def test_a_new_card_is_unverified() -> None:
    card = make_card()
    assert card.verification_status is VerificationStatus.UNVERIFIED
    assert card.is_finished_evidence is False
    assert card.evidence_text == ""
    assert card.spans == ()
    assert card.format_profile == DEFAULT_FORMAT_PROFILE
    assert card.revision == 1
    assert isinstance(card.citation, Citation)


def test_card_owner_is_required() -> None:
    with pytest.raises(ValidationError) as caught:
        Card.model_validate(
            {
                "article_id": new_id(),
                "tag": "A tag",
                "provenance_mode": ProvenanceMode.PUBLISHER_RETRIEVED,
            }
        )
    assert "owner_id" in str(caught.value)


def test_card_provenance_mode_has_no_default() -> None:
    with pytest.raises(ValidationError) as caught:
        Card.model_validate({"owner_id": new_id(), "article_id": new_id(), "tag": "A tag"})
    assert "provenance_mode" in str(caught.value)


def test_card_tag_must_not_be_blank() -> None:
    with pytest.raises(ValidationError):
        make_card(tag="   ")


def test_card_round_trips_through_json() -> None:
    card = make_cut_card(
        verification_status=VerificationStatus.VERIFIED,
        organization_id=new_id(),
        citation=Citation(
            title=CitationField[str](value="Rising seas", source=CitationFieldSource.META_TAG, verified=True),
            published_at=CitationField[datetime](
                value=datetime(2026, 3, 1, tzinfo=UTC), source=CitationFieldSource.JSON_LD, verified=True
            ),
        ),
        spans=(
            make_span(start_offset=0, end_offset=26, style=SpanStyle.UNDERLINE, purpose=SpanPurpose.CLAIM),
            make_span(start_offset=10, end_offset=20, style=SpanStyle.HIGHLIGHT),
        ),
    )
    assert Card.model_validate_json(card.model_dump_json()) == card


# --------------------------------------------------------------------------------------------
# Card: evidence must be traceable to a snapshot
# --------------------------------------------------------------------------------------------


def test_evidence_text_requires_a_snapshot() -> None:
    with pytest.raises(ValidationError) as caught:
        make_card(evidence_text=EVIDENCE, evidence_start_offset=0, evidence_end_offset=len(EVIDENCE))
    assert "must reference the snapshot" in str(caught.value)


def test_evidence_text_requires_offsets() -> None:
    with pytest.raises(ValidationError) as caught:
        make_card(snapshot_id=new_id(), evidence_text=EVIDENCE)
    assert "evidence_start_offset" in str(caught.value)


def test_offsets_without_evidence_text_are_rejected() -> None:
    with pytest.raises(ValidationError) as caught:
        make_card(snapshot_id=new_id(), evidence_start_offset=0, evidence_end_offset=10)
    assert "without any evidence_text" in str(caught.value)


def test_evidence_offsets_must_be_supplied_as_a_pair() -> None:
    with pytest.raises(ValidationError) as caught:
        make_card(snapshot_id=new_id(), evidence_text=EVIDENCE, evidence_start_offset=0)
    assert "both be set or both be None" in str(caught.value)


def test_evidence_offsets_must_be_ordered_and_non_negative() -> None:
    with pytest.raises(ValidationError):
        make_cut_card(evidence_start_offset=200, evidence_end_offset=100)
    with pytest.raises(ValidationError):
        make_cut_card(evidence_start_offset=-1)


def test_a_tampered_card_is_still_constructible_so_the_verifier_can_report_it() -> None:
    """Text/offset mismatch is the verifier's finding (TEXT_MISMATCH), not a construction error."""
    card = make_cut_card(evidence_text=EVIDENCE.replace("230", "930"))
    assert card.verification_status is VerificationStatus.UNVERIFIED
    assert "930 million" in card.evidence_text


# --------------------------------------------------------------------------------------------
# Card: spans mark up the evidence
# --------------------------------------------------------------------------------------------


def test_spans_must_fall_inside_the_evidence_text() -> None:
    with pytest.raises(ValidationError) as caught:
        make_cut_card(spans=(make_span(start_offset=0, end_offset=len(EVIDENCE) + 1),))
    assert "runs past the end of evidence_text" in str(caught.value)


def test_spans_without_evidence_text_are_rejected() -> None:
    with pytest.raises(ValidationError) as caught:
        make_card(spans=(make_span(),))
    assert "no evidence_text cannot carry spans" in str(caught.value)


def test_two_spans_of_the_same_style_may_not_overlap() -> None:
    with pytest.raises(ValidationError) as caught:
        make_cut_card(
            spans=(
                make_span(start_offset=0, end_offset=30, style=SpanStyle.UNDERLINE),
                make_span(start_offset=20, end_offset=40, style=SpanStyle.UNDERLINE),
            )
        )
    assert "overlap" in str(caught.value)


def test_a_highlight_may_sit_inside_an_underline() -> None:
    card = make_cut_card(
        spans=(
            make_span(start_offset=0, end_offset=40, style=SpanStyle.UNDERLINE),
            make_span(start_offset=10, end_offset=20, style=SpanStyle.HIGHLIGHT),
        )
    )
    assert len(card.spans) == 2
    assert len(card.spans_of_style(SpanStyle.HIGHLIGHT)) == 1


def test_spans_of_style_returns_them_in_reading_order() -> None:
    card = make_cut_card(
        spans=(
            make_span(start_offset=30, end_offset=40, style=SpanStyle.UNDERLINE),
            make_span(start_offset=0, end_offset=10, style=SpanStyle.UNDERLINE),
            make_span(start_offset=5, end_offset=12, style=SpanStyle.HIGHLIGHT),
        )
    )
    underlines = card.spans_of_style(SpanStyle.UNDERLINE)
    assert [span.start_offset for span in underlines] == [0, 30]


# --------------------------------------------------------------------------------------------
# Card: the VERIFIED preconditions
# --------------------------------------------------------------------------------------------


def test_a_card_with_everything_can_be_verified() -> None:
    card = make_cut_card(verification_status=VerificationStatus.VERIFIED)
    assert card.verification_status is VerificationStatus.VERIFIED
    assert card.is_finished_evidence is True


def test_verified_requires_a_snapshot_normalizer_version_evidence_and_a_span() -> None:
    """An empty card asked to be VERIFIED is told everything re-verification would need."""
    with pytest.raises(ValidationError) as caught:
        make_card(verification_status=VerificationStatus.VERIFIED)
    message = str(caught.value)
    for requirement in ("snapshot_id", "normalizer_version", "evidence_text", "at least one span"):
        assert requirement in message


def test_verified_requires_the_normalizer_version_the_offsets_were_taken_under() -> None:
    with pytest.raises(ValidationError) as caught:
        make_cut_card(normalizer_version=None, verification_status=VerificationStatus.VERIFIED)
    assert "normalizer_version" in str(caught.value)


def test_verified_requires_at_least_one_span() -> None:
    with pytest.raises(ValidationError) as caught:
        make_cut_card(spans=(), verification_status=VerificationStatus.VERIFIED)
    assert "at least one span" in str(caught.value)


def test_evolve_cannot_smuggle_a_card_into_the_verified_state() -> None:
    card = make_card()
    with pytest.raises(ValidationError):
        card.evolve(verification_status=VerificationStatus.VERIFIED)


def test_pasted_provenance_survives_onto_the_card() -> None:
    card = make_cut_card(provenance_mode=ProvenanceMode.USER_SUPPLIED)
    assert card.provenance_mode is ProvenanceMode.USER_SUPPLIED
    assert card.verification_status is VerificationStatus.UNVERIFIED

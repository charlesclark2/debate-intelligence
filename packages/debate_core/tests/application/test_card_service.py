"""CardService.cut_card: a stored snapshot and a research need in, a persisted card and its verdict out.

Sections, as the spec's plan selects them: the request and result types; ``-k verified``, the
pipeline that cuts a VERIFIED card (ac1, ac4); ``-k "unverified or rejected"``, every failure saved
UNVERIFIED with its reason, one test per reason, and an inaccessible snapshot refused before any
model call (ac2, ac3).

Task v1-e06-t02. Everything is offline and synthetic: t04's pages, stored as ArticleService stores
them, and the fake router's hand-written answers under ``tests/fixtures/model_outputs/``
(``card_world.py``). Expected evidence and offsets are worked out by hand from t04's hand-written
paragraphs and written down (working agreement 6).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final

import pytest

from debate_core.application.article_fetch import SOURCE_NOT_ACCESSIBLE_CODE
from debate_core.application.card_types import (
    CardFailure,
    CardFailureReason,
    CutRequest,
    CutResult,
    SourceNotAccessibleError,
)
from debate_core.application.errors import DomainError, error_code_of
from debate_core.domain import (
    AccessStatus,
    Card,
    CardSpan,
    ProvenanceMode,
    SpanStyle,
    VerificationStatus,
)
from debate_core.domain.card import DEFAULT_FORMAT_PROFILE
from debate_core.evidence.verification_types import (
    REQUIRED_CHECKS,
    ReasonCode,
    VerificationCheck,
    VerificationReason,
    VerificationResult,
)

STUDENT: Final = "0ST0DENT000000000000000001"
ARTICLE: Final = "0ART0000000000000000000001"
SNAPSHOT: Final = "0SNAP000000000000000000001"
WHEN: Final = datetime(2026, 10, 26, 15, 0, tzinfo=UTC)


# =============================================================================================
# The request and result types
# =============================================================================================


def test_a_request_refuses_a_need_that_says_nothing() -> None:
    with pytest.raises(ValueError, match="need"):
        CutRequest(snapshot_id=SNAPSHOT, need=" \n ", owner_id=STUDENT)


def test_a_request_refuses_a_blank_format_profile_name() -> None:
    with pytest.raises(ValueError, match="format profile"):
        CutRequest(snapshot_id=SNAPSHOT, need="A need", owner_id=STUDENT, format_profile=" ")


def test_a_request_names_the_default_format_profile_unless_told_another() -> None:
    assert CutRequest(snapshot_id=SNAPSHOT, need="A need", owner_id=STUDENT).format_profile == "team-default"
    assert DEFAULT_FORMAT_PROFILE == "team-default"


def test_a_request_with_an_argument_asks_the_model_for_the_need_within_that_argument() -> None:
    request = CutRequest(
        snapshot_id=SNAPSHOT,
        need="revival money is lost to living species",
        owner_id=STUDENT,
        argument="De-extinction DA",
    )

    assert request.research_need == "De-extinction DA: revival money is lost to living species"


def test_a_request_without_an_argument_asks_for_the_need_alone() -> None:
    request = CutRequest(snapshot_id=SNAPSHOT, need="revival money is lost", owner_id=STUDENT, argument="  ")

    assert request.research_need == "revival money is lost"


def blank_card(status: VerificationStatus = VerificationStatus.UNVERIFIED) -> Card:
    if status is VerificationStatus.UNVERIFIED:
        return Card(
            owner_id=STUDENT,
            article_id=ARTICLE,
            tag="A tag",
            provenance_mode=ProvenanceMode.PUBLISHER_RETRIEVED,
        )
    return Card(
        owner_id=STUDENT,
        article_id=ARTICLE,
        snapshot_id=SNAPSHOT,
        tag="A tag",
        evidence_text="abc",
        evidence_start_offset=0,
        evidence_end_offset=3,
        normalizer_version="evidence-normalizer-v1",
        spans=(CardSpan(start_offset=0, end_offset=3, style=SpanStyle.UNDERLINE),),
        verification_status=status,
        provenance_mode=ProvenanceMode.PUBLISHER_RETRIEVED,
    )


def verdict(card: Card, status: VerificationStatus) -> VerificationResult:
    verified = status is VerificationStatus.VERIFIED
    return VerificationResult(
        card_id=card.card_id,
        status=status,
        reasons=() if verified else (VerificationReason(ReasonCode.CARD_INCOMPLETE, "no evidence"),),
        checks_run=REQUIRED_CHECKS if verified else frozenset({VerificationCheck.CARD_COMPLETE}),
        verified_at=WHEN,
        verifier_version="evidence-verifier-v2",
        normalizer_version=card.normalizer_version,
        snapshot_id=card.snapshot_id,
    )


INCOMPLETE: Final = CardFailure(
    CardFailureReason.EVIDENCE_UNVERIFIED,
    "the card holds no evidence",
    verifier_code=ReasonCode.CARD_INCOMPLETE,
)


def test_a_result_whose_card_and_verdict_disagree_on_the_status_is_refused() -> None:
    card = blank_card()

    with pytest.raises(ValueError, match="status"):
        CutResult(
            card=card,
            verification=verdict(blank_card(VerificationStatus.VERIFIED), VerificationStatus.VERIFIED),
            metadata=(),
            reasons=(),
        )


def test_a_result_whose_verdict_is_about_another_card_is_refused() -> None:
    with pytest.raises(ValueError, match="card"):
        CutResult(
            card=blank_card(),
            verification=verdict(blank_card(), VerificationStatus.UNVERIFIED),
            metadata=(),
            reasons=(INCOMPLETE,),
        )


def test_an_unverified_result_has_to_say_why() -> None:
    card = blank_card()

    with pytest.raises(ValueError, match="reason"):
        CutResult(
            card=card, verification=verdict(card, VerificationStatus.UNVERIFIED), metadata=(), reasons=()
        )


def test_a_verified_result_cannot_carry_a_failure_reason() -> None:
    card = blank_card(VerificationStatus.VERIFIED)

    with pytest.raises(ValueError, match="reason"):
        CutResult(
            card=card,
            verification=verdict(card, VerificationStatus.VERIFIED),
            metadata=(),
            reasons=(INCOMPLETE,),
        )


def test_a_result_lists_its_reason_codes_once_each_in_order() -> None:
    card = blank_card()
    model = CardFailure(CardFailureReason.MODEL_OUTPUT_INVALID, "card.select@1.0.0 refused")
    result = CutResult(
        card=card,
        verification=verdict(card, VerificationStatus.UNVERIFIED),
        metadata=(),
        reasons=(model, INCOMPLETE, model),
    )

    assert result.reason_codes == ("MODEL_OUTPUT_INVALID", "EVIDENCE_UNVERIFIED")
    assert not result.is_verified


def test_a_citation_failure_names_the_fields_it_is_about_and_only_it_does() -> None:
    with pytest.raises(ValueError, match="field"):
        CardFailure(CardFailureReason.CITATION_UNVERIFIED, "required citation fields not verified")
    with pytest.raises(ValueError, match="field"):
        CardFailure(CardFailureReason.SPAN_MISMATCH, "the span is outside", fields=("authors",))
    with pytest.raises(ValueError, match="field"):
        CardFailure(CardFailureReason.CITATION_UNVERIFIED, "not verified", fields=("weather",))

    named = CardFailure(
        CardFailureReason.CITATION_UNVERIFIED, "not verified", fields=("authors", "published_at")
    )
    assert named.fields == ("authors", "published_at")


def test_the_typed_rejection_is_reported_under_the_fetch_commands_code() -> None:
    refused = SourceNotAccessibleError(SNAPSHOT, AccessStatus.PAYWALLED)

    assert isinstance(refused, DomainError)
    assert error_code_of(refused) == SOURCE_NOT_ACCESSIBLE_CODE == "SOURCE_NOT_ACCESSIBLE"
    assert (refused.snapshot_id, refused.access_status) == (SNAPSHOT, AccessStatus.PAYWALLED)
    assert str(refused) == f"snapshot {SNAPSHOT} is PAYWALLED, not ACCESSIBLE: no card is cut from it"

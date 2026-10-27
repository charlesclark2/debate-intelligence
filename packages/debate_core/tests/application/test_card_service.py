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
from tests.fixtures.card.card_world import NEWS_ARGUMENT, NEWS_NEED, CardWorld, news_request

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
    SpanPurpose,
    SpanStyle,
    VerificationStatus,
)
from debate_core.domain.card import DEFAULT_FORMAT_PROFILE
from debate_core.domain.model_contracts import ModelProvider, TaskClass
from debate_core.evidence.verification_types import (
    REQUIRED_CHECKS,
    ReasonCode,
    VerificationCheck,
    VerificationReason,
    VerificationResult,
)

pytestmark = pytest.mark.anyio

STUDENT: Final = "0ST0DENT000000000000000001"
ARTICLE: Final = "0ART0000000000000000000001"
SNAPSHOT: Final = "0SNAP000000000000000000001"
WHEN: Final = datetime(2026, 10, 26, 15, 0, tzinfo=UTC)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def world() -> CardWorld:
    return CardWorld()


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
    verified = blank_card(VerificationStatus.VERIFIED)

    with pytest.raises(ValueError, match="status"):
        CutResult(
            card=verified.evolve(verification_status=VerificationStatus.UNVERIFIED),
            verification=verdict(verified, VerificationStatus.VERIFIED),
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


async def test_a_result_whose_metadata_is_not_its_cards_is_refused(world: CardWorld) -> None:
    source = await world.add_page("news-article")
    cut = await world.card_service.cut_card(news_request(source.snapshot.snapshot_id))

    with pytest.raises(ValueError, match="metadata"):
        CutResult(card=cut.card, verification=cut.verification, metadata=cut.metadata[:1], reasons=())


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


# =============================================================================================
# The pipeline: an accessible article is cut into a VERIFIED card (ac1, ac4)
# =============================================================================================

#: The news article (t04's hand-written paragraphs): P1 0-210, P2 212-420, P3 422-712, P4 714-889,
#: P5 891-1106. The committed answers select P2 0-108 and all of P3, which is snapshot 212-320 and
#: 422-712 with 320-422 left out. Worked by hand from the paragraphs.
SEGMENT_ONE: Final = (
    "The delay follows two years of failed attempts to grow edited elephant embryos to term in surrogate "
    "animals."
)
SEGMENT_TWO: Final = (
    "Conservation biologists who have criticized the project said the timeline was never realistic. "
    "\u201cEvery year this slips, the money raised for it is money that did not go to elephants that are "
    "alive now,\u201d said Priya Ramaswamy, who studies elephant populations and was not involved in the "
    "work."
)
NEWS_TAG: Final = "Each delay in reviving the mammoth costs living elephants funding"

#: The marks, by hand, in evidence_text: P2 31-86 and 31-46 stay put (P2's passage starts at 0);
#: P3's 61-93, 119-199 and 146-199 move on by P2's 108 characters.
NEWS_SPANS: Final = [
    (
        31,
        86,
        SpanStyle.UNDERLINE,
        SpanPurpose.WARRANT,
        "failed attempts to grow edited elephant embryos to term",
    ),
    (31, 46, SpanStyle.HIGHLIGHT, SpanPurpose.WARRANT, "failed attempts"),
    (169, 201, SpanStyle.UNDERLINE, SpanPurpose.CLAIM, "the timeline was never realistic"),
    (
        227,
        307,
        SpanStyle.UNDERLINE,
        SpanPurpose.IMPACT,
        "the money raised for it is money that did not go to elephants that are alive now",
    ),
    (
        254,
        307,
        SpanStyle.HIGHLIGHT,
        SpanPurpose.IMPACT,
        "money that did not go to elephants that are alive now",
    ),
]


async def test_an_accessible_article_is_cut_into_a_verified_card_whose_evidence_is_the_snapshot_slice(
    world: CardWorld,
) -> None:
    source = await world.add_page("news-article")

    result = await world.card_service.cut_card(news_request(source.snapshot.snapshot_id))

    card = result.card
    assert (result.is_verified, card.verification_status, result.reasons) == (
        True,
        VerificationStatus.VERIFIED,
        (),
    )
    assert card.evidence_text == SEGMENT_ONE + SEGMENT_TWO
    text = source.normalized.text
    assert card.evidence_text == text[212:320] + text[422:712]
    assert (card.evidence_start_offset, card.evidence_end_offset) == (212, 712)
    assert [(omitted.start_offset, omitted.end_offset) for omitted in card.omitted_ranges] == [(320, 422)]
    assert card.tag == NEWS_TAG


async def test_the_verified_card_carries_its_snapshot_spans_and_cite(world: CardWorld) -> None:
    source = await world.add_page("news-article")
    article = await world.articles.get(source.snapshot.article_id)

    card = (await world.card_service.cut_card(news_request(source.snapshot.snapshot_id))).card

    snapshot = source.snapshot
    assert (card.snapshot_id, card.normalized_text_hash, card.normalizer_version) == (
        snapshot.snapshot_id,
        snapshot.normalized_text_hash,
        snapshot.normalizer_version,
    )
    assert (card.article_id, card.owner_id, card.provenance_mode) == (
        article.article_id,
        STUDENT,
        ProvenanceMode.PUBLISHER_RETRIEVED,
    )
    assert [
        (
            span.start_offset,
            span.end_offset,
            span.style,
            span.purpose,
            card.evidence_text[span.start_offset : span.end_offset],
        )
        for span in sorted(
            card.spans, key=lambda span: (span.start_offset, span.style != SpanStyle.UNDERLINE)
        )
    ] == NEWS_SPANS
    assert card.citation == (await world.service.resolve(article, source)).citation
    assert card.citation.is_fully_verified
    assert card.citation.authors.value == ("Dana Whitfield",)


async def test_the_verified_card_is_saved_once_at_revision_one(world: CardWorld) -> None:
    source = await world.add_page("news-article")

    result = await world.card_service.cut_card(news_request(source.snapshot.snapshot_id))

    stored = await world.cards.get(result.card.card_id)
    assert stored == result.card
    assert stored.revision == 1
    assert [card.card_id for card in (await world.cards.list_by_article(stored.article_id)).items] == [
        stored.card_id
    ]


async def test_the_verified_card_records_the_model_prompt_and_parameters_of_both_calls(
    world: CardWorld,
) -> None:
    source = await world.add_page("news-article")

    result = await world.card_service.cut_card(news_request(source.snapshot.snapshot_id))

    stored = await world.cards.get(result.card.card_id)
    assert stored.generated_by == result.metadata
    assert [(m.prompt_id, m.prompt_version) for m in stored.generated_by] == [
        ("card.select", "1.0.0"),
        ("card.markup", "1.0.0"),
    ]
    for metadata in stored.generated_by:
        assert metadata.model_id == "fake-fixture-model"
        assert metadata.route.provider is ModelProvider.FAKE
        assert metadata.route.task_class is TaskClass.COMPLEX_REASONING
        assert metadata.temperature is None  # nothing was sent, so the route's default applied
        assert metadata.snapshot_ids == (source.snapshot.snapshot_id,)
        assert metadata.retrieval_ids == ()
        assert metadata.repair_attempted is False
    assert stored.format_profile == "team-default"


async def test_re_verifying_a_saved_verified_card_reproduces_its_status(world: CardWorld) -> None:
    source = await world.add_page("news-article")
    result = await world.card_service.cut_card(news_request(source.snapshot.snapshot_id))

    again = await world.verifier.verify(await world.cards.get(result.card.card_id))

    assert again.status is result.verification.status is VerificationStatus.VERIFIED
    assert again.reasons == result.verification.reasons == ()


async def test_the_verified_card_keeps_the_format_profile_it_was_cut_for(world: CardWorld) -> None:
    source = await world.add_page("news-article")
    request = news_request(source.snapshot.snapshot_id)

    result = await world.card_service.cut_card(
        CutRequest(
            snapshot_id=request.snapshot_id,
            need=request.need,
            owner_id=STUDENT,
            argument=request.argument,
            format_profile="camp-condensed",
        )
    )

    assert result.is_verified
    assert (await world.cards.get(result.card.card_id)).format_profile == "camp-condensed"


async def test_the_model_is_asked_for_the_need_within_its_argument_before_a_verified_card_is_cut(
    world: CardWorld,
) -> None:
    source = await world.add_page("news-article")

    await world.card_service.cut_card(news_request(source.snapshot.snapshot_id))

    assert [prompt.prompt_id for prompt in world.router.calls] == ["card.select", "card.markup"]
    assert world.router.calls[0].variables["research_need"] == f"{NEWS_ARGUMENT}: {NEWS_NEED}"
    assert str(world.router.calls[0].variables["numbered_snapshot"]).startswith("[P1] A private laboratory")

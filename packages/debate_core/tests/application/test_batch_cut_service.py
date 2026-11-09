"""BatchCutService: ranked results in, up to N VERIFIED cards out, an entry per result tried (v1-e08-t06).

The cuts are real: CardService over the card world's in-memory stores, the production selector and
guard, CitationService and the evidence verifier, so only the verifier makes a card VERIFIED. The
model is :class:`~tests.fixtures.card.every_page_router.EveryPageRouter`, whose one answer per prompt
fits every page. The fetch is an instrumented fake: each URL is either a card-world page, stored as a
retrieval stores it, or an access status with no snapshot, as ArticleFetch reports a page it may not
read. The fake and the cutter count the attempts running at once, which is what the concurrency
tests read.

Expected entries are written by hand from the pages: the news article, the think-tank report and
the open-access PDF (with Crossref's answer for its DOI) cite in full and verify; the government press
release names no author, so its card is UNVERIFIED for its cite
(`tests/fixtures/citation/government-press-release.expected.json`).
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final

import pytest
from pydantic import BaseModel
from tests.fixtures.card.card_world import REPOSITORY_ROOT, STUDENT, CardWorld
from tests.fixtures.card.every_page_router import EveryPageRouter

from debate_core.application.article_fetch import FetchReport, SnapshotSummary
from debate_core.application.batch_cut_service import (
    BatchCandidate,
    BatchCutRequest,
    BatchCutService,
    BatchNeed,
    BatchReport,
    BatchStopReason,
    SpendTally,
    batch_need,
)
from debate_core.application.budget import BudgetExceededError, UnpricedModelError
from debate_core.application.card_types import CutRequest, CutResult
from debate_core.application.errors import ProviderUnavailable
from debate_core.application.query_expansion import ARGUMENT_TAXONOMY_PATH, load_argument_taxonomy
from debate_core.domain import AccessStatus, ArticleIdentifiers, ProvenanceMode, VerificationStatus
from debate_core.domain.model_contracts import ModelParams, ModelPrompt, ModelResponse, TaskClass
from debate_core.domain.search import ExpandedQuery, QueryOrigin, SearchExpansion, WindowSource

pytestmark = pytest.mark.anyio

NEED: Final = BatchNeed(
    argument="Politics DA",
    need="Link for health insurance: How the plan or action sets the argument off.",
    heading="Politics DA — Link: health insurance",
)

VERIFYING: Final = ("news-article", "think-tank-report", "open-access-pdf")
"""The card-world pages whose cards verify with the router's answers."""
UNVERIFYING: Final = "government-press-release"
"""The page whose card is UNVERIFIED: it names no author, so its cite is not verified."""


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def url(name: str) -> str:
    return f"https://{name}.example/article"


@dataclass
class Meter:
    """How many attempts are running now, and the most that ever ran at once."""

    running: int = 0
    peak: int = 0

    def enter(self) -> None:
        self.running += 1
        self.peak = max(self.peak, self.running)

    def leave(self) -> None:
        self.running -= 1


@dataclass
class RecordedFetching:
    """ArticleFetch's `retrieve`, answered from `pages`: a card-world page, or a status with no snapshot."""

    world: CardWorld
    pages: Mapping[str, str | AccessStatus]
    meter: Meter
    asked: list[str] = field(default_factory=list[str])

    async def retrieve(self, url: str) -> FetchReport:
        self.asked.append(url)
        self.meter.enter()
        page = self.pages[url]
        await asyncio.sleep(0.002)
        if isinstance(page, AccessStatus):
            self.meter.leave()
            return _report(url, page, reason=f"the fake classified this page {page.value}")
        loaded = await self.world.add_page(page)
        snapshot = loaded.snapshot
        return _report(
            url,
            AccessStatus.ACCESSIBLE,
            reason="The text was extracted",
            snapshot=SnapshotSummary(
                snapshot_id=snapshot.snapshot_id,
                provenance_mode=snapshot.provenance_mode,
                access_status=snapshot.access_status,
                sha256=snapshot.sha256,
                normalized_text_hash=snapshot.normalized_text_hash,
                paragraph_count=len(loaded.normalized.paragraphs),
                extractor_version=snapshot.extractor_version,
                normalizer_version=snapshot.normalizer_version,
                content_type=snapshot.content_type,
                byte_size=snapshot.byte_size,
                retrieved_at=snapshot.retrieved_at,
                reused=False,
            ),
        )


def _report(
    url: str, status: AccessStatus, *, reason: str, snapshot: SnapshotSummary | None = None
) -> FetchReport:
    return FetchReport(
        correlation_id="corr",
        requested_url=url,
        canonical_url=url,
        final_url=url,
        article_id="01ARTICLE0000000000000000A",
        title=url,
        identifiers=ArticleIdentifiers(),
        access_status=status,
        reason=reason,
        rules_version=None,
        evidence=None,
        fetched=True,
        provenance_mode=ProvenanceMode.PUBLISHER_RETRIEVED if snapshot is not None else None,
        snapshot=snapshot,
    )


@dataclass
class MeteredCutting:
    """CardService's `cut_card`, after a short wait, ending the attempt the fetch began."""

    world: CardWorld
    meter: Meter
    requests: list[CutRequest] = field(default_factory=list[CutRequest])

    async def cut_card(self, request: CutRequest) -> CutResult:
        self.requests.append(request)
        try:
            await asyncio.sleep(0.005)
            return await self.world.card_service.cut_card(request)
        finally:
            self.meter.leave()


@dataclass
class Batch:
    world: CardWorld
    fetching: RecordedFetching
    cutting: MeteredCutting
    meter: Meter
    service: BatchCutService

    async def cut(
        self, names: Sequence[str | tuple[str, AccessStatus]], *, wanted: int, concurrency: int = 1
    ) -> BatchReport:
        candidates = [
            BatchCandidate(
                rank=rank,
                url=url(n if isinstance(n, str) else n[0]),
                title=f"Result {rank}",
                known_access=AccessStatus.UNKNOWN if isinstance(n, str) else n[1],
            )
            for rank, n in enumerate(names, start=1)
        ]
        return await self.service.cut(
            BatchCutRequest(
                candidates=candidates, wanted=wanted, need=NEED, owner_id=STUDENT, concurrency=concurrency
            )
        )


def batch(
    pages: Mapping[str, str | AccessStatus],
    router: EveryPageRouter | None = None,
    spend: SpendTally | None = None,
) -> Batch:
    world = CardWorld(router or EveryPageRouter())
    meter = Meter()
    fetching = RecordedFetching(world, {url(name): page for name, page in pages.items()}, meter)
    cutting = MeteredCutting(world, meter)
    return Batch(
        world, fetching, cutting, meter, BatchCutService(fetching=fetching, cutting=cutting, spend=spend)
    )


PAGES: Final[dict[str, str | AccessStatus]] = {
    "news": "news-article",
    "think-tank": "think-tank-report",
    "journal": "open-access-pdf",
    "press-release": UNVERIFYING,
    "news-again": "news-article",
    "think-tank-again": "think-tank-report",
    "journal-again": "open-access-pdf",
    "paywalled": AccessStatus.PAYWALLED,
    "robots": AccessStatus.ROBOTS_DISALLOWED,
    "not-found": AccessStatus.NOT_FOUND,
}


def statuses(report: BatchReport) -> list[tuple[int, str]]:
    return [(entry.rank, entry.verdict) for entry in report.entries]


# ------------------------------------------------------------------------------------------------
# Walking the ranking
# ------------------------------------------------------------------------------------------------


async def test_it_cuts_in_rank_order_and_stops_once_n_cards_are_verified() -> None:
    run = batch(PAGES)

    report = await run.cut(["news", "think-tank", "journal", "news-again"], wanted=3)

    assert statuses(report) == [
        (1, "VERIFIED"),
        (2, "VERIFIED"),
        (3, "VERIFIED"),
    ]
    assert report.stop_reason is BatchStopReason.COMPLETE
    assert report.complete
    assert run.fetching.asked == [url("news"), url("think-tank"), url("journal")]
    assert [result.card.card_id for result in report.verified] == [e.card_id for e in report.entries]
    assert all(result.card.verification_status is VerificationStatus.VERIFIED for result in report.verified)
    assert report.unverified == ()


async def test_each_cut_is_asked_for_the_searchs_argument_and_need_by_the_owner() -> None:
    run = batch(PAGES)

    await run.cut(["news"], wanted=1)

    (request,) = run.cutting.requests
    assert request.research_need == (
        "Politics DA: Link for health insurance: How the plan or action sets the argument off."
    )
    assert request.owner_id == STUDENT
    assert request.format_profile == "team-default"


async def test_a_candidate_with_its_own_need_is_cut_for_it_and_the_others_for_the_requests() -> None:
    """A daily digest's results come from searches for different needs (v1-e08-t07)."""
    run = batch(PAGES)
    own = BatchNeed(
        argument="Midterms DA",
        need="Uniqueness for Senate: Where things stand now, before the plan or action.",
        heading="Midterms DA — Uniqueness: Senate",
    )
    candidates = [
        BatchCandidate(rank=1, url=url("news"), title="Result 1", need=own),
        BatchCandidate(rank=2, url=url("think-tank"), title="Result 2"),
    ]

    await run.service.cut(BatchCutRequest(candidates=candidates, wanted=2, need=NEED, owner_id=STUDENT))

    assert [request.research_need for request in run.cutting.requests] == [
        "Midterms DA: Uniqueness for Senate: Where things stand now, before the plan or action.",
        "Politics DA: Link for health insurance: How the plan or action sets the argument off.",
    ]


async def test_an_unverified_card_is_kept_apart_and_never_counts_toward_n() -> None:
    run = batch(PAGES)

    report = await run.cut(["press-release", "news", "think-tank", "journal"], wanted=3)

    assert statuses(report) == [
        (1, "UNVERIFIED"),
        (2, "VERIFIED"),
        (3, "VERIFIED"),
        (4, "VERIFIED"),
    ]
    assert report.stop_reason is BatchStopReason.COMPLETE
    assert len(report.verified) == 3
    (unverified,) = report.unverified
    assert unverified.card.verification_status is VerificationStatus.UNVERIFIED
    assert report.entries[0].reasons == ("CITATION_UNVERIFIED",)
    assert report.entries[0].card_id == unverified.card.card_id
    assert unverified.card.card_id not in {result.card.card_id for result in report.verified}


# ------------------------------------------------------------------------------------------------
# Skipping (ac2)
# ------------------------------------------------------------------------------------------------


async def test_paywalled_and_robots_disallowed_results_are_skipped_and_the_batch_goes_on() -> None:
    run = batch(PAGES)

    report = await run.cut(
        ["paywalled", "news", "robots", ("journal-again", AccessStatus.PAYWALLED), "think-tank", "journal"],
        wanted=3,
    )

    assert [(e.rank, e.verdict, e.access_status, e.fetched, e.reasons) for e in report.entries] == [
        (1, "SKIPPED", AccessStatus.PAYWALLED, True, ("SOURCE_NOT_ACCESSIBLE",)),
        (2, "VERIFIED", AccessStatus.ACCESSIBLE, True, ()),
        (3, "SKIPPED", AccessStatus.ROBOTS_DISALLOWED, True, ("SOURCE_NOT_ACCESSIBLE",)),
        (4, "SKIPPED", AccessStatus.PAYWALLED, False, ("SOURCE_NOT_ACCESSIBLE",)),
        (5, "VERIFIED", AccessStatus.ACCESSIBLE, True, ()),
        (6, "VERIFIED", AccessStatus.ACCESSIBLE, True, ()),
    ]
    assert report.entries[0].details == ("the fake classified this page PAYWALLED",)
    assert report.entries[3].details == (
        "an earlier retrieval recorded this source as PAYWALLED, so it was not fetched again",
    )
    assert url("journal-again") not in run.fetching.asked
    assert report.stop_reason is BatchStopReason.COMPLETE
    assert [e.card_id for e in report.entries if e.verdict == "SKIPPED"] == [None, None, None]


async def test_a_result_recorded_with_a_transient_error_is_fetched_again() -> None:
    run = batch(PAGES)

    report = await run.cut([("news", AccessStatus.ERROR)], wanted=1)

    assert statuses(report) == [(1, "VERIFIED")]
    assert run.fetching.asked == [url("news")]


async def test_fewer_than_n_because_every_other_result_was_inaccessible() -> None:
    run = batch(PAGES)

    report = await run.cut(["news", "paywalled", "robots"], wanted=3)

    assert statuses(report) == [
        (1, "VERIFIED"),
        (2, "SKIPPED"),
        (3, "SKIPPED"),
    ]
    assert report.stop_reason is BatchStopReason.ALL_REMAINING_INACCESSIBLE
    assert not report.complete


async def test_fewer_than_n_because_the_candidates_ran_out() -> None:
    run = batch(PAGES)

    report = await run.cut(["news", "press-release", "paywalled"], wanted=3)

    assert report.stop_reason is BatchStopReason.CANDIDATES_EXHAUSTED
    assert len(report.verified) == 1
    assert len(report.unverified) == 1


async def test_no_candidates_is_exhausted_with_no_entries() -> None:
    run = batch(PAGES)

    report = await run.cut([], wanted=2)

    assert report.entries == ()
    assert report.stop_reason is BatchStopReason.CANDIDATES_EXHAUSTED


async def test_a_cut_that_could_not_run_is_failed_and_the_batch_goes_on() -> None:
    run = batch(PAGES, EveryPageRouter(refuse={1: ProviderUnavailable("bedrock", "no answer")}))

    report = await run.cut(["news", "think-tank"], wanted=1)

    assert statuses(report) == [(1, "FAILED"), (2, "VERIFIED")]
    assert report.entries[0].reasons == ("PROVIDER_UNAVAILABLE",)
    assert report.entries[0].card_id is None
    assert report.entries[0].access_status is AccessStatus.ACCESSIBLE
    assert report.stop_reason is BatchStopReason.COMPLETE


# ------------------------------------------------------------------------------------------------
# Concurrency and budget (ac3)
# ------------------------------------------------------------------------------------------------


EIGHT_ACCESSIBLE: Final = [
    "news",
    "think-tank",
    "journal",
    "news-again",
    "think-tank-again",
    "journal-again",
    "news",
    "journal",
]


@pytest.mark.parametrize("concurrency", [1, 2, 3])
async def test_no_more_than_concurrency_cuts_run_at_once(concurrency: int) -> None:
    run = batch(PAGES)

    report = await run.cut(EIGHT_ACCESSIBLE[:6], wanted=6, concurrency=concurrency)

    assert run.meter.peak == concurrency
    assert run.meter.running == 0
    assert len(report.verified) == 6
    assert [entry.rank for entry in report.entries] == [1, 2, 3, 4, 5, 6]


async def test_no_more_cuts_run_than_the_cards_still_wanted() -> None:
    run = batch(PAGES)

    report = await run.cut(EIGHT_ACCESSIBLE, wanted=2, concurrency=5)

    assert run.meter.peak == 2
    assert run.fetching.asked == [url("news"), url("think-tank")]
    assert len(report.verified) == 2


async def test_a_refused_cut_is_replaced_by_the_next_candidate_under_concurrency() -> None:
    run = batch(PAGES)

    report = await run.cut(
        ["news", "paywalled", "press-release", "think-tank", "journal"], wanted=3, concurrency=3
    )

    assert statuses(report) == [
        (1, "VERIFIED"),
        (2, "SKIPPED"),
        (3, "UNVERIFIED"),
        (4, "VERIFIED"),
        (5, "VERIFIED"),
    ]
    assert run.meter.peak <= 3


def budget_refusal() -> BudgetExceededError:
    return BudgetExceededError(
        limit_name="per-run", limit_usd=0.05, spent_usd=0.04, ceiling_usd=0.02, model_id="model-under-test"
    )


async def test_the_budget_guard_stops_the_run_and_the_verified_cards_are_kept() -> None:
    run = batch(PAGES, EveryPageRouter(refuse={2: budget_refusal()}))

    report = await run.cut(["news", "think-tank", "journal", "news-again"], wanted=3)

    assert statuses(report) == [(1, "VERIFIED"), (2, "BUDGET_EXCEEDED")]
    assert report.stop_reason is BatchStopReason.BUDGET_EXCEEDED
    assert report.entries[1].reasons == ("BUDGET_EXCEEDED",)
    assert (
        report.entries[1].details[0].startswith("model call to model-under-test refused: the per-run budget")
    )
    assert report.entries[1].card_id is None
    assert len(report.verified) == 1
    assert run.fetching.asked == [url("news"), url("think-tank")]


async def test_after_the_budget_stops_a_run_no_waiting_candidate_starts_and_running_cuts_finish() -> None:
    run = batch(PAGES, EveryPageRouter(refuse={2: budget_refusal()}))

    report = await run.cut(
        ["news", "think-tank", "journal", "news-again", "journal-again"], wanted=4, concurrency=2
    )

    assert report.stop_reason is BatchStopReason.BUDGET_EXCEEDED
    assert "BUDGET_EXCEEDED" in [entry.verdict for entry in report.entries]
    assert url("journal-again") not in run.fetching.asked
    assert run.meter.running == 0
    assert all(entry.verdict != "FAILED" for entry in report.entries)


async def test_a_run_the_budget_stops_short_of_n_is_not_complete() -> None:
    run = batch(PAGES, EveryPageRouter(refuse={2: budget_refusal()}))

    report = await run.cut(["news", "think-tank", "journal"], wanted=2)

    assert statuses(report) == [
        (1, "VERIFIED"),
        (2, "BUDGET_EXCEEDED"),
    ]
    assert report.stop_reason is BatchStopReason.BUDGET_EXCEEDED
    assert not report.complete


async def test_a_call_the_guard_cannot_price_under_a_limit_ends_the_run_before_any_card() -> None:
    unpriced = UnpricedModelError("model-without-a-price", "input and output price per 1K tokens")
    run = batch(PAGES, EveryPageRouter(refuse={1: unpriced}))

    report = await run.cut(["news", "think-tank", "journal"], wanted=2)

    assert statuses(report) == [(1, "BUDGET_EXCEEDED")]
    assert report.entries[0].reasons == ("UNPRICED_MODEL_ERROR",)
    assert report.stop_reason is BatchStopReason.BUDGET_EXCEEDED
    assert run.fetching.asked == [url("news")]
    assert report.verified == ()


# ------------------------------------------------------------------------------------------------
# Cost
# ------------------------------------------------------------------------------------------------


class CostingRouter(EveryPageRouter):
    """Records each call's cost in the tally, as the usage log does for every real call."""

    def __init__(self, tally: SpendTally, costs: Mapping[str, float | None]) -> None:
        super().__init__()
        self._tally = tally
        self._costs = costs

    async def generate_structured[OutputT: BaseModel](
        self,
        task_class: TaskClass,
        prompt: ModelPrompt,
        schema: type[OutputT],
        params: ModelParams | None = None,
    ) -> ModelResponse[OutputT]:
        response = await super().generate_structured(task_class, prompt, schema, params)
        await asyncio.sleep(0.001)
        self._tally.record(self._costs[prompt.prompt_id])
        return response


async def test_each_entry_carries_its_own_calls_cost_even_beside_other_cuts() -> None:
    tally = SpendTally()
    run = batch(PAGES, CostingRouter(tally, {"card.select": 0.004, "card.markup": 0.001}), spend=tally)

    report = await run.cut(["news", "paywalled", "think-tank", "journal"], wanted=3, concurrency=3)

    assert [(entry.verdict, entry.cost_usd) for entry in report.entries] == [
        ("VERIFIED", pytest.approx(0.005)),
        ("SKIPPED", 0.0),
        ("VERIFIED", pytest.approx(0.005)),
        ("VERIFIED", pytest.approx(0.005)),
    ]
    assert report.cost_usd == pytest.approx(0.015)


async def test_an_unpriced_call_makes_its_entry_and_the_total_cost_unknown() -> None:
    tally = SpendTally()
    run = batch(PAGES, CostingRouter(tally, {"card.select": 0.004, "card.markup": None}), spend=tally)

    report = await run.cut(["news"], wanted=1)

    assert report.entries[0].cost_usd is None
    assert report.cost_usd is None


async def test_a_replayed_cut_costs_nothing() -> None:
    run = batch(PAGES)

    report = await run.cut(["news"], wanted=1)

    assert report.entries[0].cost_usd == 0.0
    assert report.cost_usd == 0.0


def test_a_call_outside_any_measured_block_is_counted_nowhere() -> None:
    tally = SpendTally()
    tally.record(1.0)
    with tally.measuring() as reading:
        tally.record(0.25)
    tally.record(2.0)

    assert reading.cost_usd == 0.25


# ------------------------------------------------------------------------------------------------
# The request and the need
# ------------------------------------------------------------------------------------------------


def test_the_need_is_the_taxonomys_argument_and_need_for_the_query() -> None:
    taxonomy = load_argument_taxonomy(REPOSITORY_ROOT / ARGUMENT_TAXONOMY_PATH)
    expansion = SearchExpansion(
        taxonomy_version=taxonomy.taxonomy_version,
        argument="politics-da",
        need="link",
        variables={"query": "health insurance", "topic": "health insurance"},
        queries=(
            ExpandedQuery(
                query="health insurance political capital",
                origin=QueryOrigin.TEMPLATE,
                template_id="politics-da/link/1",
                template="{query} political capital",
                window=WindowSource.NEED,
            ),
        ),
    )

    assert batch_need(taxonomy, expansion, "health insurance") == NEED


@pytest.mark.parametrize(("wanted", "concurrency"), [(0, 1), (1, 0)])
def test_a_request_wants_at_least_one_card_and_one_cut_at_a_time(wanted: int, concurrency: int) -> None:
    with pytest.raises(ValueError, match="at least one"):
        BatchCutRequest(candidates=(), wanted=wanted, need=NEED, owner_id=STUDENT, concurrency=concurrency)

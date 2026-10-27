"""CardService wired to in-memory stores, the citation world and the fake model router (v1-e06-t02).

A page is stored the way ArticleService stores a retrieval: its article saved, its raw bytes
snapshotted by `SnapshotService.create` with t04's hand-written paragraphs as the extracted text,
and read back by `SnapshotService.load`. The cite is resolved from the raw bytes by t01's
CitationService, through `CitationWorld` (Crossref answered by respx).

The selector is the production `CardSelector` behind the production structured-output guard. Its
router is `FakeModelRouter` over `tests/fixtures/model_outputs/`, whose `card.select` and
`card.markup` answers for the news article were written by hand, offsets only; a test may hand in
`ScriptedModelRouter` answers instead. Either is wrapped in :class:`CountingRouter`, so a test can
say how many model calls were made, and that none were.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from pydantic import BaseModel
from tests.fixtures.citation.citation_world import RETRIEVED_AT, CitationWorld, load_case

from debate_core.application.card_selection import CardSelector
from debate_core.application.card_service import CardService
from debate_core.application.card_types import CardSelecting, CutRequest
from debate_core.application.ports.model_router import ModelRouter
from debate_core.application.snapshot_service import LoadedSnapshot
from debate_core.application.structured_output import StructuredOutputGuard
from debate_core.domain import AccessStatus, Article, ArticleIdentifiers, ProvenanceMode
from debate_core.domain.model_contracts import (
    EmbeddingResponse,
    ModelParams,
    ModelPrompt,
    ModelResponse,
    RerankResponse,
    TaskClass,
)
from debate_core.integrations.models.fake_router import FakeModelRouter
from debate_core.integrations.models.prompt_registry import PromptRegistry
from debate_core.testing.fakes.clock_and_ids import SequentialIdGenerator

REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[3]
FIXTURES: Final = REPOSITORY_ROOT / "tests" / "fixtures"
MODEL_OUTPUTS: Final = FIXTURES / "model_outputs"
STUDENT: Final = "0ST0DENT000000000000000001"

NEWS_NEED: Final = "money spent reviving the mammoth is money lost to living elephants"
NEWS_ARGUMENT: Final = "De-extinction DA"
"""The need and argument the committed news-article answers were written for."""

PAGES: Final = {
    "news-article": "news-article",
    "think-tank-report": "think-tank-report",
    "government-press-release": "gov-press-release",
    "open-access-pdf": "journal-article",
    "organization-report": "gov-press-release",
}
"""Citation case → t04's extraction case, whose hand-written paragraphs are the snapshot's text."""


def paragraphs_of(case: str) -> list[str]:
    """t04's hand-written paragraphs for the page of citation case `case`."""
    expected = FIXTURES / "extraction" / f"{PAGES[case]}.expected.json"
    paragraphs: list[str] = json.loads(expected.read_text(encoding="utf-8"))["paragraphs"]
    return paragraphs


def page_bytes(case: str) -> bytes:
    """The page of citation case `case`, as t04 wrote it."""
    page: str = load_case(case)["page"]
    return (FIXTURES / page).read_bytes()


def without_lines(raw: bytes, *needles: bytes) -> bytes:
    """`raw` without the line holding each needle; each must be on exactly one line, so a page edit shows."""
    lines = raw.splitlines(keepends=True)
    for needle in needles:
        holding = [line for line in lines if needle in line]
        if len(holding) != 1:
            raise AssertionError(f"{needle!r} is on {len(holding)} lines of the page, not one")
        lines.remove(holding[0])
    return b"".join(lines)


class CountingRouter:
    """A model router that passes every call to `inner` and keeps the prompt of each structured call."""

    def __init__(self, inner: ModelRouter) -> None:
        self.inner = inner
        self.calls: list[ModelPrompt] = []

    async def generate_structured[OutputT: BaseModel](
        self,
        task_class: TaskClass,
        prompt: ModelPrompt,
        schema: type[OutputT],
        params: ModelParams | None = None,
    ) -> ModelResponse[OutputT]:
        self.calls.append(prompt)
        return await self.inner.generate_structured(task_class, prompt, schema, params)

    async def embed(self, texts: Sequence[str]) -> EmbeddingResponse:
        return await self.inner.embed(texts)

    async def rerank(self, query: str, documents: Sequence[str]) -> RerankResponse:
        return await self.inner.rerank(query, documents)


class CardWorld(CitationWorld):
    """The citation world, plus the selector, the counting router and the card service."""

    def __init__(self, router: ModelRouter | None = None, *, selector: CardSelecting | None = None) -> None:
        super().__init__()
        self.router = CountingRouter(router if router is not None else FakeModelRouter(MODEL_OUTPUTS))
        self.registry = PromptRegistry.load(REPOSITORY_ROOT / "prompts")
        self.selector: CardSelecting = (
            selector
            if selector is not None
            else CardSelector(StructuredOutputGuard(self.router, self.registry))
        )
        self.card_service = CardService(
            articles=self.articles,
            snapshots=self.snapshots,
            selector=self.selector,
            citations=self.service,
            verifier=self.verifier,
            cards=self.cards,
            clock=self.clock,
            id_generator=SequentialIdGenerator("CVT"),
        )
        self._page_article_ids = SequentialIdGenerator("PAGE")

    async def add_page(
        self,
        case: str = "news-article",
        *,
        access_status: AccessStatus = AccessStatus.ACCESSIBLE,
        raw_bytes: bytes | None = None,
    ) -> LoadedSnapshot:
        """Store citation case `case`'s page with t04's paragraphs as its text; return it loaded.

        `raw_bytes` replaces the page's own bytes (a variant a test made of them); the text, and so the
        numbered snapshot the model is shown, is t04's either way.
        """
        stated = load_case(case)
        article = await self.articles.save(
            Article(
                article_id=self._page_article_ids.new_id(),
                canonical_url=stated["article"]["canonical_url"],
                title=stated["article"]["title"],
                access_status=access_status,
                identifiers=ArticleIdentifiers(doi=stated["article"]["doi"]),
            )
        )
        snapshot = await self.snapshots.create(
            article_id=article.article_id,
            raw_bytes=raw_bytes if raw_bytes is not None else page_bytes(case),
            extracted_text="\n\n".join(paragraphs_of(case)),
            canonical_url=stated["retrieved_url"],
            retrieved_at=RETRIEVED_AT,
            extractor_version="fixture-extractor/1",
            provenance_mode=ProvenanceMode(stated["provenance_mode"]),
            access_status=access_status,
            content_type=stated["content_type"],
        )
        await self.articles.save_snapshot(snapshot)
        return await self.snapshots.load(snapshot)


def news_request(snapshot_id: str, **changes: str | None) -> CutRequest:
    """The request the committed news-article answers were written for, with `changes` applied."""
    fields: dict[str, str | None] = {"need": NEWS_NEED, "argument": NEWS_ARGUMENT, **changes}
    return CutRequest(
        snapshot_id=snapshot_id,
        need=str(fields["need"]),
        owner_id=STUDENT,
        argument=fields["argument"],
    )

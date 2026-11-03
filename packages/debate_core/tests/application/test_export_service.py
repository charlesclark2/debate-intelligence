"""ExportService.export_json: cards in, the version-2 manifest's bytes out (`v1-e06-t05`).

The cards are cut by t02's CardService in `tests/fixtures/card/card_world.py`, from the news article
whose `card.select` and `card.markup` answers are committed. The router in front of the fake one
reports a Bedrock route, so the metadata a real call would leave on a card is what the manifest has to
carry. Every expected value is written by hand from the fixtures:

* the snapshot is t04's five news-article paragraphs, joined by blank lines; its raw bytes are the
  page file, and the world stores it at `RETRIEVED_AT` with extractor `fixture-extractor/1`;
* the committed answers quote [212, 712) less the omission [320, 422): part of the second paragraph
  and all of the third. The first, fourth and fifth paragraphs are not on the card.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import BaseModel
from tests.fixtures.card.card_world import (
    MODEL_OUTPUTS,
    STUDENT,
    CardWorld,
    news_request,
    page_bytes,
    paragraphs_of,
)
from tests.fixtures.verification.verification_world import run

from debate_core.application.citation_service import format_cite
from debate_core.application.errors import NotFound
from debate_core.application.export_service import ExportRefused, ExportService
from debate_core.application.ports.model_router import ModelRouter
from debate_core.domain import Card, VerificationStatus
from debate_core.domain.model_contracts import (
    EmbeddingResponse,
    ModelParams,
    ModelPrompt,
    ModelProvider,
    ModelResponse,
    RerankResponse,
    ResolvedRoute,
    TaskClass,
)
from debate_core.evidence.card_rendering import CardToRender, CiteText, DocumentHeadings
from debate_core.evidence.docx_renderer import render_cards_docx
from debate_core.evidence.format_profile import FORMAT_PROFILES_DIRECTORY, load_format_profile
from debate_core.evidence.manifest import CardManifest
from debate_core.integrations.models.fake_router import FakeModelRouter
from debate_core.testing.fakes.clock_and_ids import FixedClock

REPOSITORY = Path(__file__).resolve().parents[4]
GENERATED_AT = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
NEWS_TEXT = "\n\n".join(paragraphs_of("news-article"))
FIRST_SNAPSHOT = "0SNAP000000000000000000001"
SECOND_SNAPSHOT = "0SNAP000000000000000000002"

NEWS_REFERENCE = {
    "snapshot_id": FIRST_SNAPSHOT,
    "sha256": hashlib.sha256(page_bytes("news-article")).hexdigest(),
    "normalized_text_hash": hashlib.sha256(NEWS_TEXT.encode("utf-8")).hexdigest(),
    "normalizer_version": "evidence-normalizer-v1",
    "extractor_version": "fixture-extractor/1",
    "retrieved_at": "2026-10-26T15:00:00Z",
    "canonical_url": (
        "https://www.dailymeridian.example/science/2026/09/14/mammoth-revival-years-away?utm_source=newsletter"
    ),
}
"""The news article's snapshot as a manifest names it: the citation world's retrieval of the page."""


class BedrockRouteRouter:
    """Passes every call to `inner`, and reports the route a Bedrock call would have taken."""

    def __init__(self, inner: ModelRouter) -> None:
        self.inner = inner

    async def generate_structured[OutputT: BaseModel](
        self,
        task_class: TaskClass,
        prompt: ModelPrompt,
        schema: type[OutputT],
        params: ModelParams | None = None,
    ) -> ModelResponse[OutputT]:
        response = await self.inner.generate_structured(task_class, prompt, schema, params)
        route = ResolvedRoute(
            task_class=task_class,
            provider=ModelProvider.BEDROCK,
            model_id="fixture.export-model-v1",
            inference_profile="us.fixture.export-model-v1",
            region="us-west-2",
            temperature=0.2,
            max_tokens=2048,
            timeout_seconds=60.0,
        )
        return response.evolve(route=route)

    async def embed(self, texts: Sequence[str]) -> EmbeddingResponse:
        return await self.inner.embed(texts)

    async def rerank(self, query: str, documents: Sequence[str]) -> RerankResponse:
        return await self.inner.rerank(query, documents)


def call(prompt_id: str) -> dict[str, Any]:
    """One model call as the card records it: the Bedrock route, and the snapshot it was shown."""
    return {
        "prompt_id": prompt_id,
        "prompt_version": "1.0.0",
        "route": {
            "task_class": "complex_reasoning",
            "provider": "bedrock",
            "model_id": "fixture.export-model-v1",
            "inference_profile": "us.fixture.export-model-v1",
            "region": "us-west-2",
            "temperature": 0.2,
            "max_tokens": 2048,
            "timeout_seconds": 60.0,
            "effort": None,
        },
        "provider_request_id": None,
        "snapshot_ids": [FIRST_SNAPSHOT],
        "retrieval_ids": [],
        "created_at": "2026-01-01T00:00:00Z",
        "repair_attempted": False,
        "repair_prompt_version": None,
    }


class ExportWorld:
    """t02's card world with the Bedrock-route router, and the export service over its stores."""

    def __init__(self) -> None:
        self.cards = CardWorld(BedrockRouteRouter(FakeModelRouter(MODEL_OUTPUTS)))
        self.export = ExportService(articles=self.cards.articles, clock=FixedClock(GENERATED_AT))

    def cut(self, snapshot_id: str) -> Card:
        card = run(self.cards.card_service.cut_card(news_request(snapshot_id))).card
        assert card.verification_status is VerificationStatus.VERIFIED
        return card

    def add_news_page(self) -> str:
        return run(self.cards.add_page()).snapshot.snapshot_id

    def export_json(self, cards: Sequence[Card]) -> bytes:
        return run(self.export.export_json(cards))


@pytest.fixture
def world() -> ExportWorld:
    return ExportWorld()


@pytest.fixture
def card(world: ExportWorld) -> Card:
    return world.cut(world.add_news_page())


def keys_and_strings(value: object, path: str = "$") -> Iterator[tuple[str, str | None, str | None]]:
    """Every (path, key, string value) in a JSON document, walked depth first."""
    if isinstance(value, dict):
        for key, item in cast("dict[str, object]", value).items():
            yield f"{path}.{key}", key, None
            yield from keys_and_strings(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(cast("list[object]", value)):
            yield from keys_and_strings(item, f"{path}[{index}]")
    elif isinstance(value, str):
        yield path, None, value


# --------------------------------------------------------------------------------------------
# What is written
# --------------------------------------------------------------------------------------------


def test_export_json_writes_version_2_with_the_card_and_its_snapshot_reference(
    world: ExportWorld, card: Card
) -> None:
    document = json.loads(world.export_json([card]))

    assert document == {
        "manifest_version": 2,
        "generated_at": "2026-10-01T12:00:00Z",
        "cards": [card.model_dump(mode="json")],
        "snapshots": [NEWS_REFERENCE],
    }


def test_export_json_carries_every_model_calls_model_route_prompt_and_temperature(
    world: ExportWorld, card: Card
) -> None:
    document = json.loads(world.export_json([card]))

    assert document["cards"][0]["generated_by"] == [call("card.select"), call("card.markup")]


def test_export_json_writes_every_field_a_default_leaves_empty(world: ExportWorld, card: Card) -> None:
    """An older build is not promised these manifests, so nothing is left out to suit one."""
    (written,) = json.loads(world.export_json([card]))["cards"]

    assert written["interpolations"] == []
    assert written["citation"]["cleared_by_student"] == []
    assert written["citation"]["authors_are_organizations"] is False
    assert written["organization_id"] is None


# --------------------------------------------------------------------------------------------
# The same cards, the same bytes
# --------------------------------------------------------------------------------------------


def test_export_json_is_byte_for_byte_the_same_every_time(world: ExportWorld, card: Card) -> None:
    """Twice from one world, and once from another holding the same snapshot record.

    The other world exports the same card rather than cutting its own: the card mapping mints span
    ids, so two cuts are two different cards.
    """
    again = ExportWorld()
    assert again.add_news_page() == card.snapshot_id

    first = world.export_json([card])

    assert world.export_json([card]) == first
    assert again.export_json([card]) == first


def test_export_json_sorts_every_key_and_indents_for_a_readable_diff(world: ExportWorld, card: Card) -> None:
    written = world.export_json([card])
    document = json.loads(written)

    assert list(document) == ["cards", "generated_at", "manifest_version", "snapshots"]
    assert list(document["snapshots"][0]) == sorted(NEWS_REFERENCE)
    assert written == (json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()
    assert written.startswith(b'{\n  "cards": [\n    {\n      "article_id": ')


def test_export_json_keeps_the_callers_card_order(world: ExportWorld) -> None:
    snapshot_id = world.add_news_page()
    first, second = world.cut(snapshot_id), world.cut(snapshot_id)

    document = json.loads(world.export_json([second, first]))

    assert [entry["card_id"] for entry in document["cards"]] == [
        "0CVT0000000000000000000002",
        "0CVT0000000000000000000001",
    ]
    assert [reference["snapshot_id"] for reference in document["snapshots"]] == [FIRST_SNAPSHOT]


def test_export_json_references_each_snapshot_once_in_id_order(world: ExportWorld) -> None:
    from_first = world.cut(world.add_news_page())
    from_second = world.cut(world.add_news_page())

    document = json.loads(
        world.export_json([from_second, from_first, from_second.evolve(card_id="0CVT0000000000000000000099")])
    )

    assert [reference["snapshot_id"] for reference in document["snapshots"]] == [
        FIRST_SNAPSHOT,
        SECOND_SNAPSHOT,
    ]
    assert document["snapshots"][1] == {**NEWS_REFERENCE, "snapshot_id": SECOND_SNAPSHOT}


# --------------------------------------------------------------------------------------------
# What is never written
# --------------------------------------------------------------------------------------------


def test_export_json_never_inlines_a_snapshots_text_or_bytes(world: ExportWorld, card: Card) -> None:
    written = world.export_json([card])
    strings = [value for _, _, value in keys_and_strings(json.loads(written)) if value is not None]
    first, _, _, fourth, fifth = paragraphs_of("news-article")

    for paragraph in (first, fourth, fifth):
        assert not any(paragraph in value for value in strings), "a paragraph the card does not quote"
    assert not any(NEWS_TEXT in value for value in strings)
    assert b"<html" not in written.lower()
    assert hashlib.sha256(page_bytes("news-article")).hexdigest() in written.decode()


def test_export_json_names_the_student_by_opaque_owner_id_only(world: ExportWorld, card: Card) -> None:
    """No name or email of the student: every key of the document is walked."""
    walked = list(keys_and_strings(json.loads(world.export_json([card]))))
    keys = {key for _, key, _ in walked if key is not None}

    assert not [key for key in keys if "mail" in key.lower()]
    assert not [key for key in keys if key.lower() == "name" or key.lower().endswith("_name")]
    assert {key for key in keys if any(word in key for word in ("owner", "student", "user", "person"))} == {
        "owner_id",
        "cleared_by_student",  # a list of cite field names (v1-e06-t02), not data about the student
    }
    assert [value for path, key, value in walked if key is None and path.endswith(".owner_id")] == [STUDENT]
    assert not [value for _, _, value in walked if value is not None and "@" in value]


# --------------------------------------------------------------------------------------------
# What is refused
# --------------------------------------------------------------------------------------------


def test_export_json_refuses_an_empty_list_of_cards(world: ExportWorld) -> None:
    with pytest.raises(ExportRefused) as refused:
        world.export_json([])

    assert str(refused.value) == "a manifest lists at least one card; there are no cards to export"


def test_export_json_refuses_a_card_listed_twice(world: ExportWorld, card: Card) -> None:
    with pytest.raises(ExportRefused) as refused:
        world.export_json([card, card])

    assert str(refused.value) == f"card {card.card_id} is listed twice; a manifest lists each card once"


def test_export_json_refuses_a_card_that_names_no_snapshot(world: ExportWorld, card: Card) -> None:
    blank = Card(
        owner_id=STUDENT,
        article_id=card.article_id,
        tag="No evidence yet",
        provenance_mode=card.provenance_mode,
    )

    with pytest.raises(ExportRefused) as refused:
        world.export_json([card, blank])

    assert str(refused.value) == (
        f"card {blank.card_id} names no snapshot, so a manifest has nothing to verify it against"
    )


def test_export_json_lets_a_missing_snapshot_record_propagate(world: ExportWorld, card: Card) -> None:
    elsewhere = card.evolve(snapshot_id="0AWAYSNAP00000000000000001", generated_by=())

    with pytest.raises(NotFound) as missing:
        world.export_json([elsewhere])

    assert (missing.value.entity, missing.value.key) == ("SourceSnapshot", "0AWAYSNAP00000000000000001")


# --------------------------------------------------------------------------------------------
# The auto-cut bundle (v1-e08-t06)
# --------------------------------------------------------------------------------------------

BUNDLE_BLOCK = "Politics DA — Link: health insurance"
TODAYS_RENDER_SHA256 = {
    "team-default": "52027feb308eb14c34af3a3e39d179cc8223deb426013be80762e281f2741d49",
    "flow": "b258942ed96a675286aa6340c47a2d57c5368abb6e4d788022d7da7f31dab190",
    "plain": "5ed859c69dc3de59346fa2a6b443726918b061e6dde9b70a33265aaba291b5df",
}
"""SHA-256 of `render_cards_docx`'s bytes for :func:`todays_render_inputs`, measured on the renderer as it
was before v1-e08-t06 added the UNVERIFIED section (commit 07039c0), and committed before it changed."""


def fixed_span_ids(card: Card, first: int) -> Card:
    """`card` with span ids that are the same every run: a span's id is otherwise a fresh ULID."""
    spans = tuple(
        span.model_copy(update={"span_id": f"0SPAN{first + index:021d}"})
        for index, span in enumerate(card.spans)
    )
    return card.evolve(spans=spans)


def todays_render_inputs(world: ExportWorld) -> tuple[CardManifest, list[CardToRender]]:
    """The committed news-article card, VERIFIED, then a second cut of it filed UNVERIFIED with its codes."""
    verified = fixed_span_ids(world.cut(world.add_news_page()), 1)
    unverified = fixed_span_ids(world.cut(world.add_news_page()), 10).evolve(
        verification_status=VerificationStatus.UNVERIFIED
    )
    manifest = run(world.export.manifest([verified, unverified]))
    return manifest, [
        CardToRender(verified, CiteText(*_short_and_full(verified))),
        CardToRender(
            unverified, CiteText(*_short_and_full(unverified)), ("CITATION_UNVERIFIED", "TEXT_MISMATCH")
        ),
    ]


def _short_and_full(card: Card) -> tuple[str, str]:
    formatted = format_cite(card.citation, provenance_mode=card.provenance_mode)
    return formatted.short_cite, formatted.full_cite


@pytest.mark.parametrize("profile_name", sorted(TODAYS_RENDER_SHA256))
def test_bundle_renderer_called_as_before_writes_todays_bytes(world: ExportWorld, profile_name: str) -> None:
    manifest, items = todays_render_inputs(world)
    profile = load_format_profile(profile_name, REPOSITORY / FORMAT_PROFILES_DIRECTORY)

    data = render_cards_docx(
        manifest,
        items,
        profile,
        headings=DocumentHeadings(pocket="Politics", hat="Health", block=BUNDLE_BLOCK),
    )

    assert hashlib.sha256(data).hexdigest() == TODAYS_RENDER_SHA256[profile_name]

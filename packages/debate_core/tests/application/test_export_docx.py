"""ExportService.export_docx: cards and their failures in, the rendered .docx out (`v1-e06-t04`).

The card is t02's VERIFIED news-article card from `tests/fixtures/card/card_world.py`. The renderer is
the real one, handed to the service as its port the way a composition root would. The expected cite is
t01's hand-written expected cite for the page (`tests/fixtures/citation/news-article.expected.json`),
and the expected banner codes are written here from the failures each test hands in.
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import docx
import pytest
from tests.fixtures.card.card_world import CardWorld, news_request
from tests.fixtures.verification.verification_world import run

from debate_core.application.card_types import CardFailure, CardFailureReason
from debate_core.application.export_service import ExportRefused, ExportService
from debate_core.domain import Card, VerificationStatus
from debate_core.evidence.card_rendering import CardToRender, DocumentHeadings
from debate_core.evidence.docx_manifest_part import read_embedded_manifest
from debate_core.evidence.docx_renderer import render_cards_docx
from debate_core.evidence.format_profile import (
    FORMAT_PROFILES_DIRECTORY,
    ResolvedFormatProfile,
    load_format_profile,
)
from debate_core.evidence.manifest import CardManifest
from debate_core.evidence.verification_types import ReasonCode
from debate_core.testing.fakes.clock_and_ids import FixedClock

REPOSITORY: Final = Path(__file__).resolve().parents[4]
TEAM_DEFAULT: Final = load_format_profile("team-default", REPOSITORY / FORMAT_PROFILES_DIRECTORY)
GENERATED_AT: Final = datetime(2026, 10, 27, 9, 30, tzinfo=UTC)
NEWS_FULL_CITE: Final = (
    'Whitfield 26 [Dana Whitfield; "Scientists Say Mammoth Revival Is Years Away"; The Daily Meridian; '
    "September 14, 2026; https://www.dailymeridian.example/science/2026/09/14/mammoth-revival-years-away; "
    "accessed October 26, 2026]"
)


class RecordingRenderer:
    """The real renderer, keeping what the service handed it."""

    def __init__(self) -> None:
        self.calls: list[tuple[CardManifest, tuple[CardToRender, ...], DocumentHeadings | None]] = []

    def __call__(
        self,
        manifest: CardManifest,
        cards: Sequence[CardToRender],
        profile: ResolvedFormatProfile,
        *,
        headings: DocumentHeadings | None = None,
    ) -> bytes:
        self.calls.append((manifest, tuple(cards), headings))
        return render_cards_docx(manifest, cards, profile, headings=headings)


class DocxWorld:
    def __init__(self) -> None:
        self.cards = CardWorld()
        self.renderer = RecordingRenderer()
        self.export = ExportService(
            articles=self.cards.articles, clock=FixedClock(GENERATED_AT), render_docx=self.renderer
        )

    def cut(self) -> Card:
        snapshot_id = run(self.cards.add_page()).snapshot.snapshot_id
        return run(self.cards.card_service.cut_card(news_request(snapshot_id))).card


@pytest.fixture
def world() -> DocxWorld:
    return DocxWorld()


def paragraph_texts(data: bytes) -> list[str]:
    return [paragraph.text for paragraph in docx.Document(io.BytesIO(data)).paragraphs]


def test_export_docx_renders_the_cards_with_their_formatted_cite_and_embeds_their_manifest(
    world: DocxWorld, tmp_path: Path
) -> None:
    card = world.cut()

    data = run(world.export.export_docx([card], profile=TEAM_DEFAULT))

    path = tmp_path / "evidence.docx"
    path.write_bytes(data)
    assert read_embedded_manifest(path) == run(world.export.manifest([card]))
    assert paragraph_texts(data)[:2] == [card.tag, NEWS_FULL_CITE]
    [(_, [item], _)] = world.renderer.calls
    assert (item.cite.short_cite, item.cite.full_cite, item.unverified_reasons) == (
        "Whitfield 26",
        NEWS_FULL_CITE,
        (),
    )


def test_export_docx_names_each_failure_and_verifier_code_in_the_banner(world: DocxWorld) -> None:
    card = world.cut().evolve(verification_status=VerificationStatus.UNVERIFIED)
    failures = {
        card.card_id: [
            CardFailure(
                CardFailureReason.CITATION_UNVERIFIED,
                "published_at is not verified",
                fields=("published_at",),
            ),
            CardFailure(
                CardFailureReason.EVIDENCE_UNVERIFIED,
                "the verifier found a mismatch",
                verifier_code=ReasonCode.TEXT_MISMATCH,
            ),
            CardFailure(
                CardFailureReason.SPAN_MISMATCH,
                "the verifier found a mismatch",
                verifier_code=ReasonCode.TEXT_MISMATCH,
            ),
        ]
    }

    data = run(world.export.export_docx([card], profile=TEAM_DEFAULT, failures=failures))

    assert paragraph_texts(data)[1] == (
        "UNVERIFIED — not a finished card: "
        "CITATION_UNVERIFIED, EVIDENCE_UNVERIFIED, TEXT_MISMATCH, SPAN_MISMATCH"
    )


def test_export_docx_passes_the_headings_through(world: DocxWorld) -> None:
    card = world.cut()
    headings = DocumentHeadings(block="De-extinction DA")

    data = run(world.export.export_docx([card], profile=TEAM_DEFAULT, headings=headings))

    assert paragraph_texts(data)[0] == "De-extinction DA"
    assert world.renderer.calls[0][2] == headings


def test_export_docx_refuses_an_unverified_card_given_no_failure_to_name(world: DocxWorld) -> None:
    card = world.cut().evolve(verification_status=VerificationStatus.UNVERIFIED)

    with pytest.raises(ExportRefused, match="its banner must name why"):
        run(world.export.export_docx([card], profile=TEAM_DEFAULT))
    assert world.renderer.calls == []


def test_export_docx_refuses_failures_for_a_card_it_is_not_exporting(world: DocxWorld) -> None:
    card = world.cut()
    stray = CardFailure(CardFailureReason.SPAN_MISMATCH, "elsewhere")

    with pytest.raises(ExportRefused, match="0CARD000000000000000000009"):
        run(
            world.export.export_docx(
                [card], profile=TEAM_DEFAULT, failures={"0CARD000000000000000000009": [stray]}
            )
        )


def test_export_docx_needs_a_renderer(world: DocxWorld) -> None:
    export = ExportService(articles=world.cards.articles, clock=FixedClock(GENERATED_AT))

    with pytest.raises(ExportRefused, match="no DOCX renderer"):
        run(export.export_docx([world.cut()], profile=TEAM_DEFAULT))

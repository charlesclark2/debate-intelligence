"""Exported .docx files for `verify`'s DOCX tests, and the edits a student makes to them (`v1-e06-t07`).

Every document starts as a real export: t02's VERIFIED news-article card, cut by CardService in
:class:`~tests.fixtures.card.card_world.CardWorld` and written by ExportService with the production
DOCX renderer, exactly as `debate-research cut` writes it (`v1-e06-t06`). A scenario then changes the
document the way Word would, through python-docx: a run's text rewritten, its underline taken off, a
sentence taken out, a bracketed interpolation typed in. Nothing is written by hand into a package's
bytes.

The texts below are written by hand from the fixture page (t04's paragraphs) and t02's committed
answers, never read back from the code under test: :data:`EVIDENCE` is the first sentence of the
page's second paragraph and the whole third paragraph, joined with nothing; the renderer draws the
cut between them at evidence offset 108 as the profile's marker.
"""

from __future__ import annotations

import io
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import docx
from docx.document import Document
from docx.text.paragraph import Paragraph
from tests.fixtures.card.card_world import CardWorld, news_request
from tests.fixtures.verification.verification_world import run

from debate_core.application.export_service import ExportService
from debate_core.application.snapshot_service import LoadedSnapshot
from debate_core.domain import Card, VerificationStatus
from debate_core.evidence.card_rendering import CardToRender, CiteText
from debate_core.evidence.docx_renderer import render_cards_docx
from debate_core.evidence.format_profile import (
    FORMAT_PROFILES_DIRECTORY,
    ResolvedFormatProfile,
    load_format_profile,
)
from debate_core.evidence.manifest import CardManifest
from debate_core.testing.fakes.clock_and_ids import FixedClock

REPOSITORY: Final = Path(__file__).resolve().parents[3]
PROFILES: Final = REPOSITORY / FORMAT_PROFILES_DIRECTORY
TEAM_DEFAULT: Final = load_format_profile("team-default", PROFILES)
EXPORTED_AT: Final = datetime(2026, 10, 27, 9, 30, tzinfo=UTC)

NEWS_CARD_ID: Final = "0CVT0000000000000000000001"
NEWS_TAG: Final = "Each delay in reviving the mammoth costs living elephants funding"
"""The committed `card.select` answer's tag."""
NEWS_CITE: Final = CiteText(
    short_cite="Whitfield 26",
    full_cite=(
        'Whitfield 26 [Dana Whitfield; "Scientists Say Mammoth Revival Is Years Away"; The Daily Meridian; '
        "September 14, 2026; "
        "https://www.dailymeridian.example/science/2026/09/14/mammoth-revival-years-away; "
        "accessed October 26, 2026]"
    ),
)
"""t01's hand-written cite for the page, used where a test renders a manifest itself."""

FIRST_SENTENCE: Final = (
    "The delay follows two years of failed attempts to grow edited elephant embryos to term in surrogate "
    "animals."
)
"""Evidence [0, 108)."""
CRITICS_SENTENCE: Final = (
    "Conservation biologists who have criticized the project said the timeline was never realistic."
)
"""Evidence [108, 202): the second sentence, right after the cut."""
LAST_PART: Final = (
    " “Every year this slips, the money raised for it is money that did not go to elephants that are alive "
    "now,” said Priya Ramaswamy, who studies elephant populations and was not involved in the work."
)
"""Evidence [202, 398)."""
EVIDENCE: Final = FIRST_SENTENCE + CRITICS_SENTENCE + LAST_PART
MARKER: Final = " … "
"""The committed profiles' omission marker."""
RENDERED_EVIDENCE: Final = FIRST_SENTENCE + MARKER + CRITICS_SENTENCE + LAST_PART
"""The evidence paragraph of an untouched export, as Word shows it."""


@dataclass(frozen=True)
class NewsExport:
    """The world the card was cut in, the card, its manifest and the exported document."""

    world: CardWorld
    snapshot: LoadedSnapshot
    card: Card
    manifest: CardManifest
    document: bytes


def news_export(
    *, profile: ResolvedFormatProfile = TEAM_DEFAULT, change_card: Callable[[Card], Card] | None = None
) -> NewsExport:
    """The news card cut, verified and exported to a .docx in ``profile`` by ExportService.

    ``change_card`` is applied to the cut card before export, for a variant whose markup differs; it
    must leave the quotation alone, or the card no longer verifies.
    """
    world = CardWorld()
    snapshot = run(world.add_page())
    card = run(world.card_service.cut_card(news_request(snapshot.snapshot.snapshot_id))).card
    assert (card.card_id, card.verification_status) == (NEWS_CARD_ID, VerificationStatus.VERIFIED)
    assert card.evidence_text == EVIDENCE, "the hand-written evidence is the cut card's"
    if change_card is not None:
        card = change_card(card)
    export = ExportService(
        articles=world.articles, clock=FixedClock(EXPORTED_AT), render_docx=render_cards_docx
    )
    document = run(export.export_docx([card], profile=profile))
    return NewsExport(world, snapshot, card, run(export.manifest([card])), document)


def render_with(
    manifest: CardManifest, export: NewsExport, profile: ResolvedFormatProfile = TEAM_DEFAULT
) -> bytes:
    """``manifest`` rendered as the export's document was, for a test that changed the manifest itself."""
    return render_cards_docx(manifest, [CardToRender(card, NEWS_CITE) for card in manifest.cards], profile)


# --------------------------------------------------------------------------------------------
# What a student does to it in Word
# --------------------------------------------------------------------------------------------


def edited(document: bytes, change: Callable[[Document], None]) -> bytes:
    """``document`` opened with python-docx, changed by ``change``, and saved again."""
    opened = docx.Document(io.BytesIO(document))
    change(opened)
    buffer = io.BytesIO()
    opened.save(buffer)
    return buffer.getvalue()


def evidence_paragraph(document: Document) -> Paragraph:
    """The news card's evidence: the document's last paragraph, after its tag and its cite."""
    return document.paragraphs[-1]


def replace_in_evidence(old: str, new: str) -> Callable[[Document], None]:
    """Rewrite ``old`` as ``new`` inside the one evidence run that holds it, its formatting kept."""

    def change(document: Document) -> None:
        runs = [each for each in evidence_paragraph(document).runs if old in each.text]
        assert len(runs) == 1, f"{old!r} is not inside exactly one run"
        runs[0].text = runs[0].text.replace(old, new, 1)

    return change


def without_markup(document: Document) -> None:
    """Every evidence run's underline style and highlight taken off, as "Clear formatting" does."""
    for each in evidence_paragraph(document).runs:
        each.style = None
        each.font.highlight_color = None


def news_card_with_the_critics_sentence_unmarked(card: Card) -> Card:
    """The news card with no span inside :data:`CRITICS_SENTENCE`, so the sentence is unmarked."""
    return card.evolve(spans=tuple(span for span in card.spans if not 108 <= span.start_offset < 202))

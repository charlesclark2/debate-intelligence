"""The DOCX renderer, as ExportService sees it (`v1-e06-t04`).

:func:`debate_core.evidence.docx_renderer.render_cards_docx` is the implementation. It writes with
python-docx, which `debate_core.application` may not reach even through another module (the import
contract "Document libraries stay inside debate_core.integrations.docx_parser"), so a composition
root hands it to :class:`~debate_core.application.export_service.ExportService` as this port. The
values it takes are the renderer's own, from modules that import no document library.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from debate_core.evidence.card_rendering import CardToRender, DocumentHeadings
from debate_core.evidence.format_profile import ResolvedFormatProfile
from debate_core.evidence.manifest import CardManifest

__all__ = ["CardDocumentRenderer"]


class CardDocumentRenderer(Protocol):
    """Renders the cards of one manifest as a .docx, with the manifest embedded in it."""

    def __call__(
        self,
        manifest: CardManifest,
        cards: Sequence[CardToRender],
        profile: ResolvedFormatProfile,
        *,
        headings: DocumentHeadings | None = None,
    ) -> bytes: ...

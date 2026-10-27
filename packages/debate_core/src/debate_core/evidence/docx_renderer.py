"""Skeleton for the red run of `v1-e06-t04`: an empty document, and no checks."""

from __future__ import annotations

import io
from collections.abc import Sequence

import docx

from debate_core.evidence.card_rendering import CardToRender, DocumentHeadings
from debate_core.evidence.format_profile import ResolvedFormatProfile
from debate_core.evidence.manifest import CardManifest

__all__ = ["render_cards_docx"]


def render_cards_docx(
    manifest: CardManifest,
    cards: Sequence[CardToRender],
    profile: ResolvedFormatProfile,
    *,
    headings: DocumentHeadings | None = None,
) -> bytes:
    del manifest, cards, profile, headings
    buffer = io.BytesIO()
    docx.Document().save(buffer)
    return buffer.getvalue()

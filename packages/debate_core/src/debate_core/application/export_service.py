"""ExportService: cards in, the card manifest out (`v1-e06-t05-json-manifest-export`).

:meth:`ExportService.export_json` writes the version-2 :class:`~debate_core.evidence.manifest.CardManifest`
of a list of cards: each card exactly as the domain serializes it, with its model calls in
``generated_by`` (`v1-e06-t02`), and one :class:`~debate_core.evidence.manifest.SnapshotReference` per
snapshot the cards were cut from, read through the article repository. The bytes are what
`debate-research verify` reads (`v1-e03-t06`) and what the DOCX renderer embeds (`v1-e06-t04`).

## The same cards give the same bytes

Keys are sorted and the document is indented (:func:`~debate_core.evidence.manifest.serialize_manifest`),
the cards keep the order they were given in, and the snapshot references are in snapshot id order.
``generated_at`` comes from the injected clock. Two exports of the same cards therefore diff to
nothing, and a renderer's document order is the manifest's card order, which is the order `verify`
reports positions in.

## What it refuses

* **No cards.** A manifest lists at least one: a gate on `verify`'s exit code must not pass having
  checked nothing.
* **A card listed twice.** Its verdict would be reported twice under one id.
* **A card that names no snapshot.** It has no evidence and nothing a reader could verify it
  against, and a manifest references every card's snapshot.

Each is an :class:`ExportRefused`, raised before any repository is read. A snapshot record that is
not stored is ``NotFound`` from the repository, and propagates: the export cannot run, which says
nothing about the card.

## What it never writes

A snapshot's text or bytes: a reference holds ids, hashes, versions, a time and a URL. Nothing about
the student beyond the card's opaque ``owner_id``: the card holds no name or email, and the manifest
adds nothing to it.
"""

from __future__ import annotations

from collections.abc import Sequence

from debate_core.application.errors import DomainError
from debate_core.application.ports.card_document import CardDocumentRenderer
from debate_core.application.ports.persistence import ArticleRepository
from debate_core.application.ports.providers import Clock
from debate_core.domain import Card
from debate_core.evidence.manifest import (
    MANIFEST_VERSION,
    CardManifest,
    SnapshotReference,
    serialize_manifest,
)

__all__ = ["ExportRefused", "ExportService"]


class ExportRefused(DomainError):
    """The cards cannot be written as a manifest. Nothing was read and nothing was written."""


class ExportService:
    """Writes cards as a card manifest, referencing the snapshots they were cut from."""

    def __init__(
        self, *, articles: ArticleRepository, clock: Clock, render_docx: CardDocumentRenderer | None = None
    ) -> None:
        self._articles = articles
        self._clock = clock
        self._render_docx = render_docx

    async def manifest(self, cards: Sequence[Card]) -> CardManifest:
        """The current-version manifest of ``cards``, in their order, with their snapshots' references."""
        if not cards:
            raise ExportRefused("a manifest lists at least one card; there are no cards to export")
        seen: set[str] = set()
        for card in cards:
            if card.card_id in seen:
                raise ExportRefused(f"card {card.card_id} is listed twice; a manifest lists each card once")
            seen.add(card.card_id)
            if card.snapshot_id is None:
                raise ExportRefused(
                    f"card {card.card_id} names no snapshot, so a manifest has nothing to verify it against"
                )
        snapshot_ids = sorted({card.snapshot_id for card in cards if card.snapshot_id is not None})
        references = [
            SnapshotReference.of(await self._articles.get_snapshot(snapshot_id))
            for snapshot_id in snapshot_ids
        ]
        return CardManifest(
            manifest_version=MANIFEST_VERSION,
            generated_at=self._clock.now(),
            cards=tuple(cards),
            snapshots=tuple(references),
        )

    async def export_json(self, cards: Sequence[Card]) -> bytes:
        """``cards`` as the manifest's JSON: keys sorted, indented, UTF-8, the same bytes every time."""
        return serialize_manifest(await self.manifest(cards))

    async def export_docx(self, cards: Sequence[Card], **_: object) -> bytes:
        raise ExportRefused("skeleton")

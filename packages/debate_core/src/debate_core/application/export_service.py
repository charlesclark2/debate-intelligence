"""ExportService: cards in, the card manifest out (`v1-e06-t05-json-manifest-export`).

:meth:`ExportService.export_json` writes the version-2 :class:`~debate_core.evidence.manifest.CardManifest`
of a list of cards: each card exactly as the domain serializes it, with its model calls in
``generated_by`` (`v1-e06-t02`), and one :class:`~debate_core.evidence.manifest.SnapshotReference` per
snapshot the cards were cut from, read through the article repository. The bytes are what
`debate-research verify` reads (`v1-e03-t06`) and what the DOCX renderer embeds (`v1-e06-t04`).

:meth:`ExportService.export_docx` is the DOCX side (`v1-e06-t04`): the same manifest, with each card's
cite formatted by `format_cite` and each failure `CardService` reported as a code, handed to the
renderer, which reaches this service as the
:class:`~debate_core.application.ports.card_document.CardDocumentRenderer` port because it writes with
python-docx and this layer may not import a document library.

## The same cards give the same bytes

Keys are sorted and the document is indented (:func:`~debate_core.evidence.manifest.serialize_manifest`),
the cards keep the order they were given in, and the snapshot references are in snapshot id order.
``generated_at`` comes from the injected clock. Two exports of the same cards therefore diff to
nothing, and a renderer's document order is the manifest's card order, which is the order `verify`
reports positions in.

## The auto-cut bundle (`v1-e08-t06`)

:meth:`ExportService.export_docx_bundle` and :meth:`ExportService.export_json_bundle` write
`search --auto-cut`'s bundle: the VERIFIED cards under one block heading, then, only when there are
any, the UNVERIFIED cards in a section of their own under "UNVERIFIED — not finished cards", each with
its banner. A card filed in the wrong section is refused, here and again by the renderer.

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

from collections.abc import Mapping, Sequence

from debate_core.application.card_types import CardFailure, CutResult
from debate_core.application.citation_service import format_cite
from debate_core.application.errors import DomainError
from debate_core.application.ports.card_document import CardDocumentRenderer
from debate_core.application.ports.persistence import ArticleRepository
from debate_core.application.ports.providers import Clock
from debate_core.domain import Card
from debate_core.evidence.card_rendering import CardToRender, CiteText, DocumentHeadings, RenderRefused
from debate_core.evidence.format_profile import ResolvedFormatProfile
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

    async def export_docx(
        self,
        cards: Sequence[Card],
        *,
        profile: ResolvedFormatProfile,
        failures: Mapping[str, Sequence[CardFailure]] | None = None,
        headings: DocumentHeadings | None = None,
    ) -> bytes:
        """``cards`` as a .docx in ``profile``, with their manifest embedded (`v1-e06-t04`).

        Each cite is :func:`~debate_core.application.citation_service.format_cite`'s. ``failures`` are
        `CardService`'s reasons by card id; each card that is not VERIFIED needs at least one, and its
        banner names each failure's code and the verifier's code beside it, once each.
        """
        return await self._docx(cards, profile=profile, failures=failures or {}, headings=headings)

    async def export_docx_bundle(
        self,
        verified: Sequence[CutResult],
        unverified: Sequence[CutResult],
        *,
        profile: ResolvedFormatProfile,
        block: str,
    ) -> bytes:
        """An auto-cut bundle (`v1-e08-t06`): `verified` under the block heading `block`, then
        `unverified` alone in the section headed "UNVERIFIED — not finished cards", each with its banner.

        The section is written only when `unverified` holds a card. Raises :class:`ExportRefused` for a
        card that is not VERIFIED among `verified`, or a VERIFIED card among `unverified`, before
        anything is read.
        """
        cards = _bundle_cards(verified, unverified)
        return await self._docx(
            cards,
            profile=profile,
            failures={result.card.card_id: result.reasons for result in unverified},
            headings=DocumentHeadings(block=block),
            unverified_from=len(verified) if unverified else None,
        )

    async def export_json_bundle(
        self, verified: Sequence[CutResult], unverified: Sequence[CutResult]
    ) -> bytes:
        """The manifest of the same bundle: the cards of `verified`, then those of `unverified`.

        A card's section is its status: the manifest's format has no other place for it, and every card
        listed before the first one that is not VERIFIED is VERIFIED. Refuses as
        :meth:`export_docx_bundle` does.
        """
        return await self.export_json(_bundle_cards(verified, unverified))

    async def _docx(
        self,
        cards: Sequence[Card],
        *,
        profile: ResolvedFormatProfile,
        failures: Mapping[str, Sequence[CardFailure]],
        headings: DocumentHeadings | None,
        unverified_from: int | None = None,
    ) -> bytes:
        if self._render_docx is None:
            raise ExportRefused("this export service was built with no DOCX renderer")
        strays = sorted(set(failures) - {card.card_id for card in cards})
        if strays:
            raise ExportRefused(f"failures were given for cards that are not exported: {', '.join(strays)}")
        manifest = await self.manifest(cards)
        try:
            items = [
                CardToRender(card, _cite_text(card), _reason_codes(failures.get(card.card_id, ())))
                for card in cards
            ]
            if unverified_from is None:
                return self._render_docx(manifest, items, profile, headings=headings)
            return self._render_docx(
                manifest, items, profile, headings=headings, unverified_from=unverified_from
            )
        except RenderRefused as refused:
            raise ExportRefused(str(refused)) from refused


def _bundle_cards(verified: Sequence[CutResult], unverified: Sequence[CutResult]) -> list[Card]:
    """The bundle's cards in document order, VERIFIED first; refused when one is in the wrong section."""
    for result in verified:
        if not result.is_verified:
            raise ExportRefused(
                f"card {result.card.card_id} is {result.card.verification_status.value}: it cannot be filed "
                "among the VERIFIED cards"
            )
    for result in unverified:
        if result.is_verified:
            raise ExportRefused(
                f"card {result.card.card_id} is VERIFIED: it cannot be filed in the UNVERIFIED section"
            )
    return [result.card for result in (*verified, *unverified)]


def _cite_text(card: Card) -> CiteText:
    formatted = format_cite(card.citation, provenance_mode=card.provenance_mode)
    return CiteText(short_cite=formatted.short_cite, full_cite=formatted.full_cite)


def _reason_codes(failures: Sequence[CardFailure]) -> tuple[str, ...]:
    """Each failure's code, then the verifier's code it carries, in order and once each."""
    codes: list[str] = []
    for failure in failures:
        codes.append(failure.reason.value)
        if failure.verifier_code is not None:
            codes.append(failure.verifier_code.value)
    return tuple(dict.fromkeys(codes))

"""Download: a card, or a cart of cards, as one Verbatim `.docx` built by the E33 writer (`v1-e39-t08`).

The card page's *Download .docx* and the cart's *Download cart* both send a list of card references,
`<caselist>/<cluster id>`, and :meth:`CardDownloadService.download` answers with a
:class:`DownloadedFile` or a :class:`DownloadRefused`. The file is built by the E33
:class:`~debate_core.application.ports.evidence_file_writer.EvidenceFileWriter` exactly as `files
build` calls it: each card copied from its source's own runs and read back, with no provenance line
(data-use policy version 1.11, `v1-e33-t08`). Its sidecar is built and never sent; the download's
`cards-downloaded` audit record names the cards instead.

## The cart is the browser's, and nothing in it is trusted (the PM's ruling of 2026-10-22)

The session is a signed cookie and holds no cart. The browser keeps the cart and sends it with the
download, under the CSRF and body-hash rules of every POST. Here each reference is parsed
(:func:`parse_cart`), duplicates are dropped, the count is capped, and every card is looked up again
through the index holder's lease, under the suppression list that lease read, before any source is
read. A card on a page rendered before a removal is refused at the download and named.

## In order, and what stops each step

1. **Download is on.** The lease's index names the parser version every occurrence's element indices
   were found by. When it is not this function's parser, download is switched off
   (:attr:`DownloadRefusal.SWITCHED_OFF`): never failed card by card.
2. **The cart.** Unreadable (:attr:`DownloadRefusal.UNREADABLE_CART`), empty, or over the card cap
   (:attr:`DownloadRefusal.TOO_MANY_CARDS`): refused before anything is looked up.
3. **Each card.** Not in the search, or its representative suppressed now; a cite with no evidence
   text; the same card twice. Each is a :class:`RefusedCard` with its place in the cart, and the
   student can drop them and build the rest.
4. **The file's size, estimated** from the text the index holds (:func:`estimated_file_bytes`):
   over :data:`DOWNLOAD_FILE_MAX_BYTES`, refused before anything is read.
5. **The sources**, read once each through `source_stores` (`raw/caselist/<slug>`, or a camp
   file's `raw/openev/<year>`). A card whose own source is over the source budget is refused and
   named (:attr:`RefusedCardReason.SOURCE_TOO_LARGE`), so it can be dropped like any other; sources
   that only add up past the budget refuse the cart before the build
   (:attr:`DownloadRefusal.SOURCES_TOO_LARGE`). A source that is missing or no longer hashes to its
   name refuses its cards.
6. **The build.** The writer's own refusals (UNSUPPORTED_CONTENT, READBACK_MISMATCH and the rest)
   name their cards. A built file over the size limit is refused, never failed at the response.
7. **The audit record**, written before the file is returned. One that cannot be written raises
   :class:`~debate_core.application.tub.access_audit.AccessNotRecorded`, and nothing is sent.

## Why there are two caps (measured 2026-10-22, `docs/session-reports/v1-e39-t08-card-download.md`)

The writer parses every source it copies from, whole, and holds them all until the file is read
back. So a build costs time and memory per distinct source, in proportion to its size, and next to
nothing per card. On synthetic sources of the mean disclosed size (236 KB), 30 cards from 30
sources took 29 s on the operator's Mac and 30 cards from one source 2.5 s; one camp-sized source
(1 MB) took 4.5 s alone, and each mean-size source held about 80 MB. CloudFront and the function
both stop a request at 30 s, and the function has 2,048 MB. :data:`DEFAULT_DOWNLOAD_CARD_CAP` keeps
the worst case of mean-size sources, and :data:`DEFAULT_DOWNLOAD_SOURCE_BYTES` a cart of large ones,
under about two thirds of that; the function's environment can set either lower or higher.

## Nothing is written

Sources are read into memory and the file is built in memory: nothing is written to the bucket or
to any disk. No step logs a reference, a tag or a word of a card.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Final

from debate_core.application.caselist.publish_plan import source_prefix
from debate_core.application.errors import BlobIntegrityError, NotFound
from debate_core.application.evidence_search import CardSource
from debate_core.application.file_recipes import Resolution, ResolvedCard, ResolvedRecipe, recipe_hash
from debate_core.application.ports.evidence_file_writer import (
    BuiltEvidenceFile,
    CardRefusalCode,
    EvidenceFileWriter,
    FileBuildRequest,
    UnsupportedContentKind,
)
from debate_core.application.ports.parsed_store import OccurrenceRecord
from debate_core.application.ports.persistence import BlobKey, SnapshotStore
from debate_core.application.search_index_holder import ScreenedSearch, SearchIndexHolder
from debate_core.application.tub.access_audit import AccessAuditService
from debate_core.application.tub.audit import CARD_REFERENCE_PATTERN, MAX_DOWNLOAD_CARDS
from debate_core.application.tub.sessions import Session
from debate_core.domain.card_occurrence import ClusterMembership
from debate_core.domain.caselist import Event, Side
from debate_core.domain.debate_files import CardCompleteness
from debate_core.domain.file_recipe import FileRecipe, render_location
from debate_core.evidence.fingerprints import FINGERPRINT_VERSION, fingerprint_text

__all__ = [
    "DEFAULT_DOWNLOAD_CARD_CAP",
    "DEFAULT_DOWNLOAD_SOURCE_BYTES",
    "DOWNLOAD_FILE_MAX_BYTES",
    "CardDownloadService",
    "CardKey",
    "DownloadRefusal",
    "DownloadRefused",
    "DownloadedFile",
    "RefusedCard",
    "RefusedCardReason",
    "WriterFactory",
    "estimated_file_bytes",
    "parse_cart",
]

DEFAULT_DOWNLOAD_CARD_CAP: Final = 8
"""The most cards one download holds unless the function's environment says otherwise.

Eight cards from eight mean-size sources is about 8 s on the operator's Mac, and under 20 s at twice
that, the allowance this record makes for the function's slower core until it is timed on dev."""

DEFAULT_DOWNLOAD_SOURCE_BYTES: Final = 2_000_000
"""The most bytes of sources one build reads unless the function's environment says otherwise.

The slowest measured rate was 4.5 s per MB of source (one camp-sized file); 2 MB is 9 s on the Mac
and under 20 s at twice that, and holds well under 1 GB of parsed sources."""

DOWNLOAD_FILE_MAX_BYTES: Final = 3_000_000
"""The largest file a download returns.

A function URL buffers at most 6 MB of response (ADR-0019, Lambda quotas), and the Lambda Web Adapter
sends a binary body base64-encoded, a third larger, so a file of 4.5 MB would already fill it. 3 MB
leaves a third of that as headroom. The largest measured cart, 30 long cards, built to 245 KB."""

ESTIMATE_FIXED_BYTES: Final = 16_384
"""The estimate's allowance for the parts every file has. A one-card file of five words is 3,230 bytes."""

ESTIMATE_BYTES_PER_CARD: Final = 2_048
"""The estimate's allowance for each card's tag and cite paragraphs."""

ESTIMATE_BYTES_PER_CHARACTER: Final = 2
"""The estimate's allowance per character of a card's tag, cite and text. Measured: 0.46 bytes for
ordinary formatting, 0.95 with every word its own fully formatted run."""

_MAX_CART_CHARACTERS: Final = MAX_DOWNLOAD_CARDS * 96
"""A cart's longest readable form: thirty references and their separators, with room to spare."""

_REFERENCE: Final = re.compile(CARD_REFERENCE_PATTERN)

_FILE_TITLE: Final = "Cards from the team evidence search"
_POCKET: Final = "Team evidence search"
_BLOCK: Final = "Downloaded cards"


@dataclass(frozen=True, slots=True, order=True)
class CardKey:
    """One card as the cart names it: its store and its cluster id."""

    caselist: str
    cluster_id: str

    @property
    def reference(self) -> str:
        return f"{self.caselist}/{self.cluster_id}"


class UnreadableCart(ValueError):
    """A cart that is not a list of card references."""


def parse_cart(raw: str) -> tuple[CardKey, ...]:
    """The cards a download's `cards` field names, in order, each once; :class:`UnreadableCart` if any
    part is not a card reference. References are separated by commas."""
    if len(raw) > _MAX_CART_CHARACTERS:
        raise UnreadableCart("the cart is longer than any cart of thirty cards")
    keys: list[CardKey] = []
    for part in raw.split(","):
        reference = part.strip()
        if not reference:
            continue
        if _REFERENCE.match(reference) is None:
            raise UnreadableCart("a part of the cart is not a card reference")
        caselist, cluster_id = reference.split("/")
        key = CardKey(caselist, cluster_id)
        if key not in keys:
            keys.append(key)
    return tuple(keys)


class DownloadRefusal(StrEnum):
    """Why a download was not built."""

    SWITCHED_OFF = "SWITCHED_OFF"
    """The index was built by another parser version than this function's: download is off."""

    UNREADABLE_CART = "UNREADABLE_CART"
    """The cart is not a list of card references."""

    EMPTY_CART = "EMPTY_CART"
    """The cart names no card."""

    TOO_MANY_CARDS = "TOO_MANY_CARDS"
    """More cards than the cap."""

    CARDS_REFUSED = "CARDS_REFUSED"
    """Some cards cannot go in the file; :attr:`DownloadRefused.cards` names each."""

    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    """The file would be, or was, larger than :data:`DOWNLOAD_FILE_MAX_BYTES`."""

    SOURCES_TOO_LARGE = "SOURCES_TOO_LARGE"
    """The cards' sources together are more than one build may read in time."""


class RefusedCardReason(StrEnum):
    """Why one card cannot go in the file."""

    NOT_IN_SEARCH = "NOT_IN_SEARCH"
    """Not in the index, or removed since: its representative is on the suppression list now."""

    NO_EVIDENCE_TEXT = "NO_EVIDENCE_TEXT"
    """A cite and no evidence text (CITE_ONLY): there is no card to copy."""

    ALREADY_IN_FILE = "ALREADY_IN_FILE"
    """The same evidence as an earlier card of the cart: a file holds a card once."""

    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    """Its source's bytes are not in the store, or no longer hash to their name."""

    SOURCE_CHANGED = "SOURCE_CHANGED"
    """Its source no longer reads as the card the index holds (the writer's OCCURRENCE_MISMATCH or
    SOURCE_UNREADABLE)."""

    UNSUPPORTED_CONTENT = "UNSUPPORTED_CONTENT"
    """It holds content the writer cannot copy losslessly: an image, a text box, a table and the like."""

    READBACK_MISMATCH = "READBACK_MISMATCH"
    """The built file did not read back as its source card."""

    SOURCE_TOO_LARGE = "SOURCE_TOO_LARGE"
    """Its own source is over the source budget, so no download can hold it (the PM's review of
    2026-10-22). A cart whose sources only add up past the budget is :attr:`DownloadRefusal.
    SOURCES_TOO_LARGE` instead."""


_WRITER_REASONS: Final[Mapping[CardRefusalCode, RefusedCardReason]] = {
    CardRefusalCode.UNSUPPORTED_CONTENT: RefusedCardReason.UNSUPPORTED_CONTENT,
    CardRefusalCode.SOURCE_UNAVAILABLE: RefusedCardReason.SOURCE_UNAVAILABLE,
    CardRefusalCode.SOURCE_UNREADABLE: RefusedCardReason.SOURCE_CHANGED,
    CardRefusalCode.OCCURRENCE_MISMATCH: RefusedCardReason.SOURCE_CHANGED,
    CardRefusalCode.READBACK_MISMATCH: RefusedCardReason.READBACK_MISMATCH,
}


@dataclass(frozen=True, slots=True)
class RefusedCard:
    """One card of the cart that stopped the file, by its place in the cart (from 1).

    `tag` and `short_cite` are what the card page shows, to name it; a card no longer in the search
    has neither, so a removed card's words are never repeated.
    """

    position: int
    key: CardKey
    reason: RefusedCardReason
    tag: str | None = field(default=None, repr=False)
    short_cite: str | None = field(default=None, repr=False)
    content_kinds: tuple[UnsupportedContentKind, ...] = ()


@dataclass(frozen=True, slots=True)
class DownloadRefused:
    """A download that was not built, and why. `cards` names each card that stopped it."""

    refusal: DownloadRefusal
    cards: tuple[RefusedCard, ...] = ()
    card_cap: int | None = None


@dataclass(frozen=True, slots=True)
class DownloadedFile:
    """A built file and the cards in it, in order; its audit record is already written."""

    docx: bytes = field(repr=False)
    cards: tuple[CardKey, ...]


WriterFactory = Callable[[SnapshotStore], EvidenceFileWriter]
"""The E33 writer over one store: the sources this build fetched through `source_stores`, each from
the store of its prefix in the evidence layout, held in memory for the build."""


def estimated_file_bytes(cards: Sequence[CardSource]) -> int:
    """An upper bound on the built file's size, from the text the index holds of each card."""
    return ESTIMATE_FIXED_BYTES + sum(
        ESTIMATE_BYTES_PER_CARD
        + ESTIMATE_BYTES_PER_CHARACTER * (len(card.tag or "") + len(card.cite) + len(card.text))
        for card in cards
    )


class _FetchedSources:
    """The sources one build reads, fetched before it: a :class:`SnapshotStore` that only reads.

    A source that could not be fetched raises, to the writer, what the store raised for it.
    """

    def __init__(self, fetched: Mapping[str, bytes | NotFound | BlobIntegrityError]) -> None:
        self._fetched = fetched

    async def put(self, data: bytes) -> BlobKey:
        raise NotImplementedError("a download writes no source")

    async def get(self, key: BlobKey) -> bytes:
        found = self._fetched.get(key)
        if found is None:
            raise NotFound("snapshot blob", key)
        if isinstance(found, bytes):
            return found
        raise found

    async def exists(self, key: BlobKey) -> bool:
        return isinstance(self._fetched.get(key), bytes)


@dataclass(frozen=True, slots=True)
class _Screened:
    """What the lease said: download off, or each card's source (`None`: not in the search now)."""

    switched_off: bool
    sources: tuple[CardSource | None, ...] = ()


class CardDownloadService:
    """Builds downloads for one function: the index holder, the writer, the stores and the audit."""

    def __init__(
        self,
        *,
        search_index: SearchIndexHolder,
        writer: WriterFactory,
        source_stores: Callable[[str], SnapshotStore],
        access_audit: AccessAuditService,
        parser_version: str,
        profile_version: str,
        clock: Callable[[], datetime],
        card_cap: int = DEFAULT_DOWNLOAD_CARD_CAP,
        source_bytes: int = DEFAULT_DOWNLOAD_SOURCE_BYTES,
        file_bytes: int = DOWNLOAD_FILE_MAX_BYTES,
    ) -> None:
        if not 1 <= card_cap <= MAX_DOWNLOAD_CARDS:
            raise ValueError(f"a download holds between 1 and {MAX_DOWNLOAD_CARDS} cards")
        if source_bytes < 1 or file_bytes < 1:
            raise ValueError("a download's byte limits are positive")
        self._search_index = search_index
        self._writer = writer
        self._source_stores = source_stores
        self._audit = access_audit
        self._parser_version = parser_version
        self._profile_version = profile_version
        self._clock = clock
        self._card_cap = card_cap
        self._source_bytes = source_bytes
        self._file_bytes = file_bytes

    @property
    def card_cap(self) -> int:
        return self._card_cap

    def is_on(self, search: ScreenedSearch) -> bool:
        """Whether this lease's index was built by this function's parser, so its cards can be built."""
        return search.parser_version == self._parser_version

    async def download(self, session: Session, cart: str) -> DownloadedFile | DownloadRefused:
        """The file for the cards `cart` names, or why not. The audit record is written before it returns.

        Raises :class:`~debate_core.application.search_index_holder.SearchIndexUnavailable` when the
        index or the suppression list cannot be read, and :class:`~debate_core.application.tub.
        access_audit.AccessNotRecorded` when the record cannot be written: no file either way.
        """
        try:
            keys = parse_cart(cart)
        except UnreadableCart:
            return DownloadRefused(DownloadRefusal.UNREADABLE_CART)
        if not keys:
            return DownloadRefused(DownloadRefusal.EMPTY_CART)
        if len(keys) > self._card_cap:
            return DownloadRefused(DownloadRefusal.TOO_MANY_CARDS, card_cap=self._card_cap)
        screened = await asyncio.to_thread(self._screen, keys)
        if screened.switched_off:
            return DownloadRefused(DownloadRefusal.SWITCHED_OFF)
        refused = _refused_by_lookup(keys, screened.sources)
        if refused:
            return DownloadRefused(DownloadRefusal.CARDS_REFUSED, refused)
        sources = tuple(source for source in screened.sources if source is not None)
        if estimated_file_bytes(sources) > self._file_bytes:
            return DownloadRefused(DownloadRefusal.FILE_TOO_LARGE)
        fetched, too_large = await self._fetch(sources)
        alone = _refused_too_large(keys, sources, too_large)
        if alone:
            return DownloadRefused(DownloadRefusal.CARDS_REFUSED, alone)
        if (
            sum(len(content) for content in fetched.values() if isinstance(content, bytes))
            > self._source_bytes
        ):
            return DownloadRefused(DownloadRefusal.SOURCES_TOO_LARGE)
        built = await self._build(keys, sources, fetched)
        if isinstance(built, DownloadRefused):
            return built
        if len(built.docx) > self._file_bytes:
            return DownloadRefused(DownloadRefusal.FILE_TOO_LARGE)
        await asyncio.to_thread(
            self._audit.cards_downloaded, session, [(key.caselist, key.cluster_id) for key in keys]
        )
        return DownloadedFile(docx=built.docx, cards=keys)

    # The lease ------------------------------------------------------------------------------

    def _screen(self, keys: Sequence[CardKey]) -> _Screened:
        """Each card's source under the list this lease read, unless download is off."""
        with self._search_index.lease() as search:
            if not self.is_on(search):
                return _Screened(switched_off=True)
            return _Screened(
                switched_off=False,
                sources=tuple(search.card_source(key.caselist, key.cluster_id) for key in keys),
            )

    # The sources ----------------------------------------------------------------------------

    async def _fetch(
        self, sources: Sequence[CardSource]
    ) -> tuple[dict[str, bytes | NotFound | BlobIntegrityError], frozenset[str]]:
        """Each distinct source's bytes, or the error its store gave, and the sources over the budget alone.

        Every distinct source is read, at most one per card in the cart, so that each card whose own
        source is too large is named. A source over the budget is not kept.
        """
        fetched: dict[str, bytes | NotFound | BlobIntegrityError] = {}
        too_large: set[str] = set()
        for source in sources:
            if source.source_sha256 in fetched or source.source_sha256 in too_large:
                continue
            store = self._source_stores(source_prefix(source.caselist, source.snapshot))
            try:
                content = await store.get(source.source_sha256)
            except (NotFound, BlobIntegrityError) as problem:
                fetched[source.source_sha256] = problem
                continue
            if len(content) > self._source_bytes:
                too_large.add(source.source_sha256)
                continue
            fetched[source.source_sha256] = content
        return fetched, frozenset(too_large)

    # The build ------------------------------------------------------------------------------

    async def _build(
        self,
        keys: Sequence[CardKey],
        sources: Sequence[CardSource],
        fetched: Mapping[str, bytes | NotFound | BlobIntegrityError],
    ) -> BuiltEvidenceFile | DownloadRefused:
        resolved = self._resolved(sources)
        store = _FetchedSources(fetched)
        result = await self._writer(store).build(FileBuildRequest(resolved, self._clock()))
        if isinstance(result, BuiltEvidenceFile):
            return result
        by_path = {card.path: position for position, card in enumerate(resolved.cards)}
        return DownloadRefused(
            DownloadRefusal.CARDS_REFUSED,
            tuple(
                RefusedCard(
                    position=by_path[one.path] + 1,
                    key=keys[by_path[one.path]],
                    reason=_WRITER_REASONS[one.code],
                    tag=sources[by_path[one.path]].tag,
                    short_cite=sources[by_path[one.path]].short_cite,
                    content_kinds=one.content_kinds,
                )
                for one in result.refusals
            ),
        )

    def _resolved(self, sources: Sequence[CardSource]) -> ResolvedRecipe:
        """The cart as a recipe of one pocket and one block, each card pinned to its representative.

        A recipe names one format, caselist and side, which a cart of cards from several stores does
        not have. They go into the sidecar alone, which a download never sends, so the first card's
        event and store stand in, with the format's first side.
        """
        fingerprints = [_fingerprint(source) for source in sources]
        first = sources[0]
        event = Event(first.event)
        recipe = FileRecipe.model_validate(
            {
                "schema_version": 1,
                "title": _FILE_TITLE,
                "topic": "team-evidence-search",
                "format": event.value,
                "caselist": first.caselist,
                "position": "downloaded-cards",
                "side": (Side.PRO if event is Event.PF else Side.AFF).value,
                "fingerprint_version": FINGERPRINT_VERSION,
                "structure": [
                    {
                        "pocket": _POCKET,
                        "blocks": [
                            {"block": _BLOCK, "items": [{"fingerprint": one} for one in fingerprints]}
                        ],
                    }
                ],
            }
        )
        cards = tuple(
            ResolvedCard(
                path=render_location(location),
                fingerprint=ref.fingerprint,
                tag_override=None,
                resolution=Resolution.PINNED,
                occurrence=self._occurrence(source, ref.fingerprint),
            )
            for (location, ref), source in zip(recipe.card_refs(), sources, strict=True)
        )
        return ResolvedRecipe(
            recipe=recipe,
            recipe_hash=recipe_hash(recipe),
            versions={source.caselist: self._parser_version for source in sources},
            cards=cards,
            errors=(),
        )

    def _occurrence(self, source: CardSource, fingerprint: str) -> OccurrenceRecord:
        """The representative's row as the writer reads one. The index keeps no cluster membership,
        which the writer never reads; `UNLINKED` claims the least."""
        return OccurrenceRecord(
            caselist=source.caselist,
            snapshot=source.snapshot,
            last_snapshot=source.last_snapshot,
            source_sha256=source.source_sha256,
            parser_version=self._parser_version,
            profile_version=self._profile_version,
            fingerprint_version=FINGERPRINT_VERSION,
            disclosure=source.disclosure,
            camp=source.camp,
            first_element_index=source.first_element_index,
            last_element_index=source.last_element_index,
            exact_fingerprint=fingerprint,
            cluster_id=source.cluster_id,
            membership=ClusterMembership.UNLINKED,
            completeness=CardCompleteness(source.completeness),
        )


def _fingerprint(source: CardSource) -> str:
    """The exact fingerprint of the card the page shows: its evidence text's (E31's rule for a FULL or
    ABBREVIATED card). The writer refuses a source whose card at those paragraphs has another."""
    return fingerprint_text(source.text)


def _refused_too_large(
    keys: Sequence[CardKey], sources: Sequence[CardSource], too_large: frozenset[str]
) -> tuple[RefusedCard, ...]:
    """The cards whose own source is over the source budget: no cart that holds them can be built."""
    return tuple(
        RefusedCard(position, key, RefusedCardReason.SOURCE_TOO_LARGE, source.tag, source.short_cite)
        for position, (key, source) in enumerate(zip(keys, sources, strict=True), start=1)
        if source.source_sha256 in too_large
    )


def _refused_by_lookup(
    keys: Sequence[CardKey], sources: Sequence[CardSource | None]
) -> tuple[RefusedCard, ...]:
    """The cards the lease refuses: not in the search now, no evidence text, or a card twice."""
    refused: list[RefusedCard] = []
    seen: set[str] = set()
    for position, (key, source) in enumerate(zip(keys, sources, strict=True), start=1):
        if source is None:
            refused.append(RefusedCard(position, key, RefusedCardReason.NOT_IN_SEARCH))
            continue
        if source.completeness == CardCompleteness.CITE_ONLY.value:
            refused.append(
                RefusedCard(position, key, RefusedCardReason.NO_EVIDENCE_TEXT, source.tag, source.short_cite)
            )
            continue
        fingerprint = _fingerprint(source)
        if fingerprint in seen:
            refused.append(
                RefusedCard(position, key, RefusedCardReason.ALREADY_IN_FILE, source.tag, source.short_cite)
            )
            continue
        seen.add(fingerprint)
    return tuple(refused)

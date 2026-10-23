"""The download's limits, at the edge (`v1-e39-t08` ac5 and the cart's rules).

* **The buffered-response limit.** A cart whose estimated file is over
  :data:`~debate_core.application.card_download.DOWNLOAD_FILE_MAX_BYTES` is refused before a source is
  read or the writer is called, and one exactly at it goes on to the build: a synthetic cart of eight
  cards whose text the index holds, sized to the byte.
* **The estimate is an upper bound.** Every file the E33 writer built from the measured worst case,
  every word its own fully formatted run, is smaller than its estimate.
* **The cart as sent.** :func:`~debate_core.application.card_download.parse_cart` takes card references
  and nothing else, in order, each once.

The service runs over a real index holder and index, with a writer that records what it was asked;
no test reaches a network.
"""

from __future__ import annotations

import asyncio
import random
import tempfile
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Final, cast

import pytest

from debate_core.application.card_download import (
    DOWNLOAD_FILE_MAX_BYTES,
    ESTIMATE_BYTES_PER_CARD,
    ESTIMATE_BYTES_PER_CHARACTER,
    ESTIMATE_FIXED_BYTES,
    CardDownloadService,
    CardKey,
    DownloadRefusal,
    DownloadRefused,
    UnreadableCart,
    estimated_file_bytes,
    parse_cart,
)
from debate_core.application.errors import NotFound
from debate_core.application.evidence_search import CardSource
from debate_core.application.ports.evidence_file_writer import (
    BuiltEvidenceFile,
    FileBuildRefusal,
    FileBuildRequest,
)
from debate_core.application.ports.persistence import BlobKey
from debate_core.application.ports.search_index import IndexedOccurrence, SearchDocument
from debate_core.application.search_index_holder import SearchIndexHolder
from debate_core.application.tub.access_audit import AccessAuditService
from debate_core.application.tub.audit import AuditRecord
from debate_core.application.tub.identity import Role
from debate_core.application.tub.sessions import Session
from debate_core.integrations.docx_file_writer.writer import DocxEvidenceFileWriter
from debate_core.integrations.docx_parser.parser import DebateDocxParser
from debate_core.integrations.local.search_index import SqliteSearchIndexWriter
from debate_core.integrations.local.search_index_reader import SqliteSearchIndexReader
from debate_core.testing.docx_builder import build_docx, paragraph_xml, run_xml
from debate_core.testing.file_builder import FileBuilderWorld
from debate_core.testing.search_index import InMemorySearchIndexSource, published_index

NOW: Final = datetime(2026, 11, 2, 15, 0, tzinfo=UTC)
PARSER_VERSION: Final = "2026.10.20-docx-6"
TAG: Final = "T"
CITE: Final = "C 26"
CARDS: Final = 8
AT_THE_LIMIT: Final = (
    ((DOWNLOAD_FILE_MAX_BYTES - ESTIMATE_FIXED_BYTES) // CARDS - ESTIMATE_BYTES_PER_CARD)
    // ESTIMATE_BYTES_PER_CHARACTER
    - len(TAG)
    - len(CITE)
)
"""The text, in characters, that puts eight cards' estimate exactly at the limit: 185,447."""


def cluster(doc_id: int) -> str:
    return f"{doc_id:064x}"


def document(doc_id: int, characters: int) -> SearchDocument:
    """A card of `characters` characters of text whose source no store holds."""
    return SearchDocument(
        doc_id=doc_id,
        caselist="hsld26",
        cluster_id=cluster(doc_id),
        event="LD",
        camp=None,
        tag=TAG,
        cite=CITE,
        short_cite="C 26",
        read_aloud="",
        text=f"{doc_id:02d}" + "w" * (characters - 2),
        completeness="FULL",
        formatting_spans=(),
        font_size_spans=(),
        sides=("AFF",),
        first_seen="2026-09-15",
        last_seen="2026-10-13",
        file_count=1,
        team_count=1,
        occurrences=(
            IndexedOccurrence(
                ordinal=0,
                caselist="hsld26",
                source_sha256=f"{doc_id:064x}",
                disclosure=f"{doc_id + 100:064x}",
                first_element_index=0,
                last_element_index=2,
                snapshot="2026-09-15",
                last_snapshot="2026-10-13",
                completeness="FULL",
                attributed=True,
                provenance=False,
            ),
        ),
    )


class RecordingWriter:
    def __init__(self) -> None:
        self.requests: list[FileBuildRequest] = []

    async def build(self, request: FileBuildRequest) -> BuiltEvidenceFile | FileBuildRefusal:
        self.requests.append(request)
        return FileBuildRefusal(())


class EmptyStore:
    def __init__(self) -> None:
        self.reads: list[str] = []

    async def put(self, data: bytes) -> BlobKey:
        raise AssertionError("a download writes no source")

    async def get(self, key: BlobKey) -> bytes:
        self.reads.append(key)
        raise NotFound("snapshot blob", key)

    async def exists(self, key: BlobKey) -> bool:
        return False


class Sink:
    def __init__(self) -> None:
        self.records: list[AuditRecord] = []

    def record(self, record: AuditRecord) -> None:
        self.records.append(record)


class Near:
    """A service over an index of nine cards: eight at the limit between them, and one a character longer."""

    def __init__(self, directory: Path) -> None:
        path = directory / "near.sqlite"
        sink = SqliteSearchIndexWriter().create(path)
        for doc_id in range(1, CARDS + 1):
            sink.add(document(doc_id, AT_THE_LIMIT))
        sink.add(document(CARDS + 1, AT_THE_LIMIT + 1))
        sink.finish()
        source = InMemorySearchIndexSource()
        source.publish(
            published_index(
                path.read_bytes(), documents_by_store={"hsld26": CARDS + 1}, parser_version=PARSER_VERSION
            )
        )
        self.holder = SearchIndexHolder(
            source,
            directory=directory / "index",
            open_reader=lambda file, index_id: SqliteSearchIndexReader(file, index_id=index_id),
            clock=lambda: NOW,
        )
        self.writer = RecordingWriter()
        self.store = EmptyStore()
        self.audit = Sink()
        self.service = CardDownloadService(
            search_index=self.holder,
            writer=lambda sources: self.writer,
            source_stores=lambda prefix: self.store,
            access_audit=AccessAuditService(audit=self.audit, clock=lambda: NOW),
            parser_version=PARSER_VERSION,
            profile_version="synthetic-profile",
            clock=lambda: NOW,
            card_cap=CARDS,
        )

    def download(self, *doc_ids: int) -> Any:
        cart = ",".join(f"hsld26/{cluster(doc_id)}" for doc_id in doc_ids)
        return asyncio.run(self.service.download(SESSION, cart))


SESSION: Final = Session(
    subject="synthetic-subject",
    username="debater.one",
    role=Role.STUDENT,
    email_second_factor=False,
    started_at=NOW,
    last_seen_at=NOW,
    revalidated_at=NOW,
    csrf_token="synthetic-token",
    refresh_token="synthetic-refresh",
)


@pytest.fixture
def near() -> Iterator[Near]:
    with tempfile.TemporaryDirectory(prefix="tub-download-") as directory:
        made = Near(Path(directory))
        yield made
        made.holder.close()


def test_download_cart_estimated_exactly_at_the_buffered_limit_goes_on_to_the_build(near: Near) -> None:
    result = near.download(*range(1, CARDS + 1))

    assert AT_THE_LIMIT == 185_447
    assert len(near.writer.requests) == 1, result
    assert len(near.store.reads) == CARDS


def test_download_cart_two_bytes_past_the_buffered_limit_is_refused_before_building(near: Near) -> None:
    result = near.download(*range(2, CARDS + 2))

    assert result == DownloadRefused(DownloadRefusal.FILE_TOO_LARGE)
    assert near.writer.requests == [] and near.store.reads == [] and near.audit.records == []


def test_download_estimate_is_the_documented_sum(near: Near) -> None:
    with near.holder.lease() as search:
        sources = [search.card_source("hsld26", cluster(doc_id)) for doc_id in range(1, CARDS + 1)]
    assert all(source is not None for source in sources)

    assert (
        estimated_file_bytes([source for source in sources if source is not None]) == DOWNLOAD_FILE_MAX_BYTES
    )


# ------------------------------------------------------------------------------------------------
# The estimate bounds what the writer builds
# ------------------------------------------------------------------------------------------------

_WORDS: Final = (
    "the",
    "policy",
    "of",
    "tariff",
    "growth",
    "climate",
    "alliance",
    "ruling",
    "capital",
    "court",
)


def _worst_card(rng: random.Random, number: int, words: int) -> str:
    """A card whose every word is its own run, underlined, emphasised, highlighted and resized."""
    colours = ("cyan", "yellow", "green", "magenta")
    runs = "".join(
        run_xml(
            rng.choice(_WORDS) + " ",
            character_style="Emphasis",
            bold=True,
            underline="single",
            highlight=colours[index % 4],
            half_points=16 + 2 * (index % 5),
        )
        for index in range(words)
    )
    return (
        paragraph_xml(run_xml(f"Synthetic worst-case claim {number}"), style="Heading4")
        + paragraph_xml(
            run_xml(f"Brandvold {20 + number % 7}", character_style="Style13ptBold")
            + run_xml(", Fellow, Synthetic Review")
        )
        + paragraph_xml(runs)
    )


@pytest.mark.parametrize(("cards", "words"), [(1, 5), (1, 400), (30, 400)], ids=["tiny", "one", "thirty"])
def test_download_estimate_is_above_every_file_the_writer_builds_from_the_worst_formatting(
    cards: int, words: int
) -> None:
    parser = DebateDocxParser()
    world = FileBuilderWorld(
        parser=parser, caselist="hsld26", snapshot=date(2026, 9, 15), last_snapshot=date(2026, 9, 22)
    )
    rng = random.Random(20261022)
    parsed = asyncio.run(
        world.add_source(build_docx("".join(_worst_card(rng, n, words) for n in range(cards))))
    )
    recipe = world.recipe([("Downloaded cards", [{"fingerprint": card.fingerprint} for card in parsed])])
    built = asyncio.run(
        DocxEvidenceFileWriter(snapshots=world.snapshots, parser=parser).build(
            FileBuildRequest(world.resolve(recipe, {card.fingerprint: card for card in parsed}), NOW)
        )
    )
    assert isinstance(built, BuiltEvidenceFile)
    sources = [
        CardSource(
            caselist="hsld26",
            cluster_id=card.fingerprint,
            event="LD",
            camp=None,
            tag=card.card.tag,
            short_cite=card.card.short_cite,
            completeness="FULL",
            source_sha256=card.occurrence.source_sha256,
            disclosure=None,
            snapshot="2026-09-15",
            last_snapshot="2026-09-22",
            first_element_index=0,
            last_element_index=0,
            cite=card.card.full_cite,
            text=card.card.evidence_text,
        )
        for card in parsed
    ]

    assert len(built.docx) < estimated_file_bytes(sources)


# ------------------------------------------------------------------------------------------------
# The cart as sent
# ------------------------------------------------------------------------------------------------

ONE: Final = f"hsld26/{1:064x}"
CAMP: Final = f"openev/{2:064x}"


def test_cart_is_parsed_in_order_each_card_once_with_blanks_and_spaces_ignored() -> None:
    assert parse_cart(f" {CAMP} ,{ONE},,{CAMP},{ONE} ") == (
        CardKey("openev", f"{2:064x}"),
        CardKey("hsld26", f"{1:064x}"),
    )
    assert parse_cart("") == () and parse_cart(" , ") == ()


@pytest.mark.parametrize(
    "cart",
    [
        "hsld26",
        f"hsld26/{1:063x}",
        f"hsld26/{1:064x}0",
        f"hsld26/{1:064x}/",
        f"/hsld26/{1:064x}",
        f"hsld2/{1:064x}",
        f"camp/{1:064x}",
        f"hsld26\\{1:064x}",
        f"hsld26/{1:064x};{CAMP}",
        f"{ONE}\n{CAMP}",
        f"hsld26/{'g' * 64}",
        ",".join([ONE] * 41),
    ],
)
def test_cart_with_any_part_that_is_not_a_card_reference_is_unreadable(cart: str) -> None:
    with pytest.raises(UnreadableCart):
        parse_cart(cart)


def test_cart_of_thirty_distinct_references_is_readable() -> None:
    cart = ",".join(f"hsld26/{number:064x}" for number in range(30))

    assert len(parse_cart(cart)) == 30


def test_download_cart_cap_is_between_one_and_the_audit_records_thirty() -> None:
    for cap in (0, 31):
        with pytest.raises(ValueError, match="between 1 and 30"):
            CardDownloadService(
                search_index=cast(SearchIndexHolder, None),
                writer=lambda sources: RecordingWriter(),
                source_stores=lambda prefix: EmptyStore(),
                access_audit=AccessAuditService(audit=Sink(), clock=lambda: NOW),
                parser_version=PARSER_VERSION,
                profile_version="synthetic-profile",
                clock=lambda: NOW,
                card_cap=cap,
            )

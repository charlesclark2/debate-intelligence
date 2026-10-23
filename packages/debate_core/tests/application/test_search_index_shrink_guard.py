"""The shrink guard: an index that would drop a store's cards is never published (`v1-e39-t14`).

Three layers, one rule. :func:`~debate_core.application.search_index_publish.check_index_size` is
the rule over two manifests written here by hand; :class:`~debate_core.application.search_index_publish.
SearchIndexPublishService` applies it to real built indexes before its first upload; and the weekly
run's search index stage (:class:`~debate_core.application.search_index_refresh.SearchIndexRefresh`)
meets it through that same service, and never with the override.

The PM's rulings of 2026-10-22: per store, not just the total; a store the current index holds at 0
documents is refused; a store whose aggregates hold no rows is refused even at a first publish; each
refusal names the store, both counts and the index left current, and the pointer is untouched.

The bucket is a directory on disk (`FsEvidenceObjectStore`): no network, no AWS. Every store is
synthetic: invented sentences, sources named by the digest of an invented phrase, and parser versions
that are no release's. Every expected count is written by hand from the store a test builds.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Final

import pytest

from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.caselist_sync import SearchIndexStageReport, StageOutcome
from debate_core.application.ports.parsed_store import (
    DocumentRecord,
    OccurrenceRecord,
    SourceEntry,
    SourceOutcome,
)
from debate_core.application.ports.suppression import ReasonCode, SuppressionAction, SuppressionEntry
from debate_core.application.search_index_build import (
    BuiltSearchIndex,
    SearchIndexBuildService,
    SearchIndexStoreNotReady,
)
from debate_core.application.search_index_publish import (
    CurrentSearchIndex,
    CurrentSearchIndexUnreadable,
    PublishedSearchIndex,
    SearchIndexPublishService,
    SearchIndexStoreEmpty,
    SearchIndexWouldShrink,
    StoreShrink,
    check_index_size,
)
from debate_core.application.search_index_refresh import SEARCH_INDEX_DIRECTORY, SearchIndexRefresh
from debate_core.domain.card_occurrence import ClusterMembership
from debate_core.domain.caselist import Event, SourceFormat, SourceOrigin
from debate_core.domain.debate_files import CardCompleteness, FileImportProvenance, ParsedCard, ParsedDocument
from debate_core.domain.search_index import (
    SEARCH_INDEX_FORMAT_VERSION,
    SEARCH_INDEX_GZIP_NAME,
    SEARCH_INDEX_MANIFEST_NAME,
    SEARCH_INDEX_POINTER_KEY,
    SQLITE_FEATURE_CEILING,
    IndexCounts,
    IndexFile,
    SearchIndexManifest,
    SearchIndexPointer,
    StoreState,
    SuppressionListState,
    index_object_key,
)
from debate_core.domain.style_profile import StyleMatchSource
from debate_core.evidence.fingerprints import FINGERPRINT_VERSION, card_fingerprint
from debate_core.integrations.local import FsEvidenceObjectStore
from debate_core.integrations.local.search_index import SqliteSearchIndexWriter
from debate_core.integrations.local.suppression_list import local_suppression_list_file
from debate_core.testing.fakes.caselist import InMemoryCaselistRepository
from debate_core.testing.fakes.parsed_store import InMemoryParsedStore

LD: Final = "hsld26"
PF: Final = "hspf26"
STORES: Final = (LD, PF)
EVENTS: Final = {LD: Event.LD, PF: Event.PF}
PARSER: Final = "2026.01.05-synthetic-a"
PROFILE: Final = "2026.01.01-synthetic-profile"
REASON: Final = "RM-2026-99, a synthetic whole-file removal"


def sha(name: str) -> str:
    return hashlib.sha256(name.encode()).hexdigest()


# ------------------------------------------------------------------------------------------------
# Manifests by hand, for the rule itself
# ------------------------------------------------------------------------------------------------


def manifest(
    documents: Mapping[str, int], *, rows: Mapping[str, int] | None = None, tag: str = "new"
) -> SearchIndexManifest:
    """A manifest holding `documents` of each store, and `rows` rows (else its documents, 1 or more)."""
    sqlite_sha = sha(f"sqlite {tag} {sorted(documents.items())} {sorted((rows or {}).items())}")
    read = {store: (rows or {}).get(store, max(count, 1)) for store, count in documents.items()}
    return SearchIndexManifest(
        format_version=SEARCH_INDEX_FORMAT_VERSION,
        index_id=sqlite_sha[:16],
        parser_version=PARSER,
        fingerprint_version=FINGERPRINT_VERSION,
        sqlite_version="3.50.4",
        sqlite_feature_ceiling=SQLITE_FEATURE_CEILING,
        provenance_limit=5,
        stores=tuple(
            StoreState(
                caselist=store,
                version_directory=PARSER,
                latest_snapshot="2026-09-01",
                occurrence_rows=read[store],
                occurrences_sha256=sha(f"rows {store} {read[store]}"),
            )
            for store in sorted(documents)
        ),
        snapshot="2026-09-01",
        suppression=SuppressionListState(entries=0, path_holds=0, sha256=sha("no entries")),
        counts=IndexCounts(
            documents=sum(documents.values()),
            documents_by_store=dict(documents),
            occurrences=sum(documents.values()),
            provenance_rows=sum(documents.values()),
            occurrence_rows_read=sum(read.values()),
            suppressed_occurrences=0,
            clusters_left_out=0,
            unattributed_representatives=0,
        ),
        sqlite_file=IndexFile(name="search-index.sqlite", bytes=40_000, sha256=sqlite_sha),
        gzip_object=IndexFile(name="search-index.sqlite.gz", bytes=12_000, sha256=sha(f"gzip {sqlite_sha}")),
    )


def current_of(documents: Mapping[str, int]) -> CurrentSearchIndex:
    """The index `current.json` names, holding `documents` of each store."""
    held = manifest(documents, tag="current")
    pointer = SearchIndexPointer(
        format_version=held.format_version,
        index_id=held.index_id,
        manifest_key=index_object_key(held.index_id, SEARCH_INDEX_MANIFEST_NAME),
        manifest_sha256=sha("manifest bytes"),
        object_key=index_object_key(held.index_id, SEARCH_INDEX_GZIP_NAME),
        object_sha256=held.gzip_object.sha256,
        sqlite_sha256=held.sqlite_file.sha256,
    )
    return CurrentSearchIndex(pointer=pointer, manifest=held)


def refused_for(
    new: SearchIndexManifest, current: CurrentSearchIndex | None, *, share: int = 90
) -> SearchIndexWouldShrink:
    with pytest.raises(SearchIndexWouldShrink) as refused:
        check_index_size(new, current, minimum_share_percent=share)
    return refused.value


# ------------------------------------------------------------------------------------------------
# The rule: per store, not just the total
# ------------------------------------------------------------------------------------------------


def test_search_index_shrink_guard_refuses_one_store_under_the_share_though_the_total_grew() -> None:
    current = current_of({LD: 10, PF: 10})
    new = manifest({LD: 8, PF: 14})

    refused = refused_for(new, current)

    assert refused.shrinks == (StoreShrink(LD, 8, 10),)
    assert (refused.store, refused.documents, refused.current_documents) == (LD, 8, 10)
    assert refused.current_index_id == current.index_id
    message = str(refused)
    assert "hsld26 has 8 documents against 10" in message
    assert f"current.json still names {current.index_id}" in message
    assert '--allow-shrink "<reason>"' in message


def test_search_index_shrink_guard_passes_a_store_at_exactly_the_share() -> None:
    assert (
        check_index_size(manifest({LD: 9, PF: 10}), current_of({LD: 10, PF: 10}), minimum_share_percent=90)
        is None
    )


def test_search_index_shrink_guard_refuses_a_store_the_current_index_holds_at_0_with_the_total_fine() -> None:
    current = current_of({LD: 10, PF: 2})

    left_out = refused_for(manifest({LD: 12}), current)
    emptied = refused_for(manifest({LD: 12, PF: 0}, rows={PF: 3}), current)

    assert left_out.shrinks == (StoreShrink(PF, 0, 2),), "a store the build did not read has 0 documents"
    assert emptied.shrinks == (StoreShrink(PF, 0, 2),), "a store whose every row was suppressed"
    assert "hspf26 has 0 documents against 2" in str(emptied)


def test_search_index_shrink_guard_refuses_a_store_at_0_whatever_the_share_is_set_to() -> None:
    refused = refused_for(manifest({LD: 1, PF: 0}, rows={PF: 3}), current_of({LD: 10, PF: 2}), share=0)

    assert refused.shrinks == (StoreShrink(PF, 0, 2),), "at a share of 0 the store of 1 in 10 passes"


def test_search_index_shrink_guard_names_every_store_it_refuses_for() -> None:
    refused = refused_for(manifest({LD: 1, PF: 1}), current_of({LD: 10, PF: 10}))

    assert refused.shrinks == (StoreShrink(LD, 1, 10), StoreShrink(PF, 1, 10))
    assert refused.stores_shrunk == 2
    assert "hsld26 has 1 documents against 10; hspf26 has 1 documents against 10" in str(refused)


def test_search_index_shrink_guard_does_not_compare_a_store_the_current_index_does_not_hold() -> None:
    assert check_index_size(manifest({LD: 10, PF: 1}), current_of({LD: 10}), minimum_share_percent=90) is None
    assert check_index_size(manifest({LD: 10}), current_of({LD: 10, PF: 0}), minimum_share_percent=90) is None


def test_search_index_shrink_guard_refuses_a_store_with_empty_aggregates_at_a_first_publish() -> None:
    new = manifest({LD: 0, PF: 0}, rows={LD: 0, PF: 0})

    with pytest.raises(SearchIndexStoreEmpty) as refused:
        check_index_size(new, None, minimum_share_percent=90)

    assert (refused.value.store, refused.value.documents, refused.value.current_documents) == (LD, 0, None)
    assert "hsld26, whose aggregates hold no occurrence rows" in str(refused.value)
    assert "no index is published yet" in str(refused.value)


def test_search_index_shrink_guard_refuses_empty_aggregates_against_a_current_index_and_with_a_reason() -> (
    None
):
    """The 2026-10-22 case: every store's aggregates empty, over an index two debaters were using."""
    current = current_of({LD: 13_225, PF: 11_393})
    new = manifest({LD: 0, PF: 0}, rows={LD: 0, PF: 0})

    with pytest.raises(SearchIndexStoreEmpty) as refused:
        check_index_size(new, current, minimum_share_percent=90, allow_shrink=REASON)

    assert (refused.value.store, refused.value.current_documents) == (LD, 13_225)
    assert f"0 documents against 13,225 in index {current.index_id}" in str(refused.value)
    assert f"current.json still names {current.index_id}" in str(refused.value)


def test_search_index_shrink_guard_with_a_reason_returns_what_it_let_through() -> None:
    allowed = check_index_size(
        manifest({LD: 8, PF: 10}), current_of({LD: 10, PF: 10}), minimum_share_percent=90, allow_shrink=REASON
    )

    assert allowed is not None
    assert (allowed.reason, allowed.shrinks) == (REASON, (StoreShrink(LD, 8, 10),))


def test_search_index_shrink_guard_with_a_reason_it_does_not_need_lets_nothing_through() -> None:
    assert (
        check_index_size(
            manifest({LD: 10}), current_of({LD: 10}), minimum_share_percent=90, allow_shrink=REASON
        )
        is None
    )


# ------------------------------------------------------------------------------------------------
# Real indexes: the store, the build and the bucket
# ------------------------------------------------------------------------------------------------


def _card(source: str, text: str, store: str) -> ParsedCard:
    return ParsedCard(
        tag="Invented growth claim",
        full_cite="Okonkwo 26, Invented Journal of Growth",
        evidence_text=text,
        completeness=CardCompleteness.FULL,
        match_source=StyleMatchSource.HEURISTIC,
        confidence=0.9,
        provenance=FileImportProvenance(
            source_sha256=source,
            source_path="placeholder.docx",
            origin=SourceOrigin.CASELIST_ARCHIVE,
            caselist=store,
            snapshot=date(2026, 9, 1),
            first_element_index=0,
            last_element_index=2,
            parser_version=PARSER,
            profile_version=PROFILE,
        ),
    )


def texts(store: str, count: int) -> list[str]:
    return [f"Invented {store} evidence number {number}" for number in range(count)]


def write_store(parsed: InMemoryParsedStore, store: str, cards: Sequence[str]) -> None:
    """A source of one card and one occurrence row for each of `cards`; again, the rows are replaced."""
    rows: list[OccurrenceRecord] = []
    for text in cards:
        source = sha(f"{store} {text}")
        card = _card(source, text, store)
        if asyncio.run(parsed.read_document(store, PARSER, source)) is None:
            document = ParsedDocument(
                source_sha256=source,
                source_path="placeholder.docx",
                parser_version=PARSER,
                profile_version=PROFILE,
                cards=(card,),
            )
            entry = SourceEntry(
                caselist=store,
                snapshot="2026-09-01",
                source_sha256=source,
                parser_version=PARSER,
                profile_version=PROFILE,
                fingerprint_version=FINGERPRINT_VERSION,
                source_format=SourceFormat.DOCX,
                byte_size=100,
                outcome=SourceOutcome.PARSED,
                cards=1,
            )
            record = DocumentRecord.from_parsed_document(
                document,
                caselist=store,
                snapshot="2026-09-01",
                fingerprint_version=FINGERPRINT_VERSION,
                camp=None,
            )
            asyncio.run(parsed.write_source(store, PARSER, entry, record))
        rows.append(
            OccurrenceRecord(
                caselist=store,
                snapshot="2026-09-01",
                last_snapshot="2026-09-01",
                source_sha256=source,
                parser_version=PARSER,
                profile_version=PROFILE,
                fingerprint_version=FINGERPRINT_VERSION,
                disclosure=sha(f"disclosure {text}"),
                camp=None,
                first_element_index=0,
                last_element_index=2,
                exact_fingerprint=card_fingerprint(card).exact_fingerprint,
                cluster_id=sha(f"cluster {text}"),
                membership=ClusterMembership.NEAR_DUPLICATE,
                completeness=CardCompleteness.FULL,
            )
        )
    asyncio.run(parsed.write_aggregates(store, PARSER, index=(), failures=(), occurrences=rows))


def suppression_of(store: str, text: str) -> SuppressionEntry:
    return SuppressionEntry(
        action=SuppressionAction.SUPPRESS,
        sha256=sha(f"{store} {text}"),
        recorded_at=datetime(2026, 10, 22, tzinfo=UTC),
        reason=ReasonCode.REQUESTED_BY_TEAM,
        request_id="RM-2026-99",
    )


class RecordingPublisher(SearchIndexPublishService):
    """The real publish service, recording the override every call to it passed."""

    def __init__(self, *, bucket: FsEvidenceObjectStore, parser_version: str) -> None:
        super().__init__(bucket=bucket, parser_version=parser_version)
        self.overrides: list[str | None] = []

    async def publish(self, directory: Path, *, allow_shrink: str | None = None) -> PublishedSearchIndex:
        self.overrides.append(allow_shrink)
        return await super().publish(directory, allow_shrink=allow_shrink)


@dataclass
class World:
    """One machine's data directory and parsed store, a bucket on disk, and the services over them."""

    root: Path

    def __post_init__(self) -> None:
        self.data_dir = self.root / "data"
        self.out = self.data_dir / SEARCH_INDEX_DIRECTORY
        self.parsed = InMemoryParsedStore()
        self.bucket = FsEvidenceObjectStore(self.root / "bucket")
        self.suppression = RecordedSuppressionList(local_suppression_list_file(self.data_dir))
        self.builder = SearchIndexBuildService(
            parsed_store=self.parsed,
            caselists=InMemoryCaselistRepository(),
            suppression=self.suppression,
            writer=SqliteSearchIndexWriter(),
            parser_version=PARSER,
            event_for_caselist=EVENTS.get,
        )
        self.publisher = RecordingPublisher(bucket=self.bucket, parser_version=PARSER)
        write_store(self.parsed, LD, texts(LD, 10))
        write_store(self.parsed, PF, texts(PF, 5))

    def build(self, stores: Sequence[str] = STORES) -> BuiltSearchIndex:
        return asyncio.run(self.builder.build(stores, self.root / "built"))

    def publish(self, built: BuiltSearchIndex, *, allow_shrink: str | None = None) -> PublishedSearchIndex:
        return asyncio.run(self.publisher.publish(built.directory, allow_shrink=allow_shrink))

    def suppress(self, store: str, cards: Sequence[str]) -> None:
        asyncio.run(self.suppression.append([suppression_of(store, text) for text in cards]))

    def pointer(self) -> SearchIndexPointer | None:
        landed = self.root / "fetched-current.json"
        try:
            asyncio.run(self.bucket.get_file(SEARCH_INDEX_POINTER_KEY, landed))
        except Exception:
            return None
        return SearchIndexPointer.model_validate_json(landed.read_bytes())

    def keys(self) -> set[str]:
        return {one.key for one in asyncio.run(self.bucket.list_objects("reports/"))}

    async def _reconcile(self) -> None:
        return None

    def stage(self) -> SearchIndexRefresh:
        return SearchIndexRefresh(
            builder=self.builder,
            out=self.out,
            parser_version=PARSER,
            publisher=self.publisher,
            bucket=self.bucket,
            reconcile=self._reconcile,
            environment="dev",
        )

    def refresh(self) -> SearchIndexStageReport:
        return asyncio.run(self.stage().refresh(STORES, no_session=None))


@pytest.fixture
def world(tmp_path: Path) -> World:
    return World(tmp_path)


def emptied(built: BuiltSearchIndex, stores: Sequence[str]) -> BuiltSearchIndex:
    """`built`, its manifest rewritten to record `stores` with no rows and no documents.

    The build refuses a store whose occurrence table holds no rows (`v1-e39-t02`), so a directory
    like this one stands for an index another build, or a hand, wrote: the guard reads the manifest.
    """
    counts = built.manifest.counts
    documents = {
        store: (0 if store in stores else count) for store, count in counts.documents_by_store.items()
    }
    rewritten = built.manifest.model_copy(
        update={
            "stores": tuple(
                one.model_copy(update={"occurrence_rows": 0}) if one.caselist in stores else one
                for one in built.manifest.stores
            ),
            "counts": counts.model_copy(
                update={"documents": sum(documents.values()), "documents_by_store": documents}
            ),
        }
    )
    (built.directory / SEARCH_INDEX_MANIFEST_NAME).write_bytes(rewritten.to_json_bytes())
    return BuiltSearchIndex(directory=built.directory, manifest=rewritten)


# ------------------------------------------------------------------------------------------------
# `tub index publish`'s service: refused before the first upload, the pointer untouched
# ------------------------------------------------------------------------------------------------


def test_search_index_publish_refuses_one_store_under_the_share_and_leaves_the_pointer(world: World) -> None:
    first = world.publish(world.build())
    world.suppress(LD, texts(LD, 2))
    shrunk = world.build()
    assert shrunk.manifest.counts.documents_by_store == {LD: 8, PF: 5}
    before = world.keys()

    with pytest.raises(SearchIndexWouldShrink) as refused:
        world.publish(shrunk)

    assert refused.value.shrinks == (StoreShrink(LD, 8, 10),)
    assert refused.value.current_index_id == first.index_id
    pointer = world.pointer()
    assert pointer is not None and pointer.index_id == first.index_id
    assert world.keys() == before, "nothing of the refused index was uploaded"


def test_search_index_publish_refuses_a_store_at_0_with_the_total_fine_and_leaves_the_pointer(
    world: World,
) -> None:
    first = world.publish(world.build())
    write_store(world.parsed, LD, texts(LD, 16))
    only_ld = world.build((LD,))
    assert only_ld.manifest.counts.documents_by_store == {LD: 16}, "16 documents against the 15 published"

    with pytest.raises(SearchIndexWouldShrink) as refused:
        world.publish(only_ld)

    assert refused.value.shrinks == (StoreShrink(PF, 0, 5),)
    assert f"hspf26 has 0 documents against 5 in index {first.index_id}" in str(refused.value)
    pointer = world.pointer()
    assert pointer is not None and pointer.index_id == first.index_id


def test_search_index_publish_refuses_a_first_index_of_empty_aggregates_and_writes_no_pointer(
    world: World,
) -> None:
    built = emptied(world.build(), [PF])

    with pytest.raises(SearchIndexStoreEmpty) as refused:
        world.publish(built)

    assert (refused.value.store, refused.value.current_index_id) == (PF, None)
    assert world.pointer() is None
    assert world.keys() == set()


def test_search_index_publish_refuses_every_store_emptied_over_the_current_index(world: World) -> None:
    """The 2026-10-22 case, at the publish: an index of all-empty aggregates over the one in use."""
    first = world.publish(world.build())
    write_store(world.parsed, LD, texts(LD, 11))
    built = emptied(world.build(), STORES)

    with pytest.raises(SearchIndexStoreEmpty) as refused:
        world.publish(built, allow_shrink=REASON)

    assert (refused.value.store, refused.value.current_documents) == (LD, 10)
    pointer = world.pointer()
    assert pointer is not None and pointer.index_id == first.index_id


def test_search_index_publish_with_allow_shrink_publishes_and_records_the_reason_outside_the_manifest(
    world: World, caplog: pytest.LogCaptureFixture
) -> None:
    first = world.publish(world.build())
    world.suppress(LD, texts(LD, 2))
    shrunk = world.build()

    with caplog.at_level(logging.WARNING, logger="debate_core.application.search_index_publish"):
        published = world.publish(shrunk, allow_shrink=f"  {REASON}  ")

    assert published.index_id == shrunk.manifest.index_id
    assert published.replaced == first.index_id
    assert published.allowed_shrink is not None
    assert published.allowed_shrink.reason == REASON
    assert published.allowed_shrink.shrinks == (StoreShrink(LD, 8, 10),)
    pointer = world.pointer()
    assert pointer is not None and pointer.index_id == shrunk.manifest.index_id
    landed = world.root / "fetched-manifest.json"
    asyncio.run(world.bucket.get_file(pointer.manifest_key, landed))
    assert landed.read_bytes() == (shrunk.directory / SEARCH_INDEX_MANIFEST_NAME).read_bytes()
    assert REASON.encode() not in landed.read_bytes() + pointer.to_json_bytes()
    [line] = [one for one in caplog.records if one.name == "debate_core.application.search_index_publish"]
    extra = vars(line)
    assert (extra["reason"], extra["replaced"], extra["stores_shrunk"]) == (REASON, first.index_id, [LD])


@pytest.mark.parametrize("reason", ["", "   ", "two\nlines", "x" * 201])
def test_search_index_publish_refuses_an_allow_shrink_reason_that_is_not_a_short_line(
    world: World, reason: str
) -> None:
    with pytest.raises(ValueError, match="one line of 1 to 200 characters"):
        world.publish(world.build(), allow_shrink=reason)
    assert world.keys() == set()


@pytest.mark.parametrize(
    ("damage", "said"),
    [
        ("pointer", "current.json is not a pointer this build reads"),
        ("manifest", "the manifest in the bucket is not the one current.json names"),
    ],
)
def test_search_index_publish_refuses_when_the_current_index_cannot_be_read(
    world: World, damage: str, said: str
) -> None:
    first = world.publish(world.build())
    world.suppress(LD, texts(LD, 1))
    second = world.build()
    damaged = world.root / "damaged"
    damaged.write_bytes(b'{"not": "a pointer"}\n')
    key = SEARCH_INDEX_POINTER_KEY if damage == "pointer" else first.pointer.manifest_key
    asyncio.run(world.bucket.put_file(key, damaged))
    before = world.keys()

    with pytest.raises(CurrentSearchIndexUnreadable, match=said):
        world.publish(second)
    assert world.keys() == before

    published = world.publish(second, allow_shrink=REASON)
    assert published.allowed_shrink is not None
    assert published.allowed_shrink.current_unreadable is not None
    assert said in published.allowed_shrink.current_unreadable


# ------------------------------------------------------------------------------------------------
# The weekly stage: the same guard, refused as a failed stage, never overridden
# ------------------------------------------------------------------------------------------------


def test_index_stage_refuses_a_shrunken_index_and_leaves_the_pointer_and_the_local_index(
    world: World,
) -> None:
    first = world.refresh()
    assert first.counts is not None and first.counts.published
    world.suppress(LD, texts(LD, 3))

    report = world.refresh()

    assert report.outcome is StageOutcome.FAILED
    assert isinstance(report.failure, SearchIndexWouldShrink)
    assert report.failure.shrinks == (StoreShrink(LD, 7, 10),)
    assert report.counts is not None and report.counts.built and not report.counts.published
    assert f"current.json still names {first.counts.index_id}" in report.reason
    pointer = world.pointer()
    assert pointer is not None and pointer.index_id == first.counts.index_id
    assert (world.out / first.counts.index_id).is_dir(), "the published index stays on this machine"
    assert (world.out / report.counts.index_id).is_dir(), "and so does the refused one, for a publish by hand"
    assert report.hint is not None and '--allow-shrink "<reason>"' in report.hint
    assert world.publisher.overrides == [None, None]


def test_index_stage_refuses_a_store_at_0_with_the_total_fine(world: World) -> None:
    first = world.refresh()
    assert first.counts is not None
    write_store(world.parsed, LD, texts(LD, 16))
    world.suppress(PF, texts(PF, 5))

    report = world.refresh()

    assert report.outcome is StageOutcome.FAILED
    assert isinstance(report.failure, SearchIndexWouldShrink)
    assert report.failure.shrinks == (StoreShrink(PF, 0, 5),)
    assert report.counts is not None and report.counts.documents == 16
    pointer = world.pointer()
    assert pointer is not None and pointer.index_id == first.counts.index_id
    assert world.publisher.overrides == [None, None]


def test_index_stage_refuses_every_stores_aggregates_emptied_and_leaves_the_pointer(world: World) -> None:
    """The 2026-10-22 case in the weekly run: the build refuses an empty occurrence table first."""
    first = world.refresh()
    assert first.counts is not None
    for store in STORES:
        asyncio.run(world.parsed.write_aggregates(store, PARSER, index=(), failures=(), occurrences=()))

    report = world.refresh()

    assert report.outcome is StageOutcome.FAILED
    assert isinstance(report.failure, SearchIndexStoreNotReady)
    pointer = world.pointer()
    assert pointer is not None and pointer.index_id == first.counts.index_id
    assert world.publisher.overrides == [None]


def test_index_stage_publishes_a_store_at_the_share_without_any_override(world: World) -> None:
    first = world.refresh()
    assert first.counts is not None
    world.suppress(LD, texts(LD, 1))

    report = world.refresh()

    assert report.outcome is StageOutcome.COMPLETED
    assert report.counts is not None and report.counts.published
    pointer = world.pointer()
    assert pointer is not None and pointer.index_id == report.counts.index_id
    assert world.publisher.overrides == [None, None]


def test_index_stage_records_each_runs_growth_against_the_index_it_replaced(world: World) -> None:
    first = world.refresh()
    assert first.counts is not None
    assert (first.counts.previous_index_id, first.counts.documents_growth) == (None, None)
    write_store(world.parsed, LD, texts(LD, 13))

    second = world.refresh()

    assert second.counts is not None and second.counts.published
    assert second.counts.previous_index_id == first.counts.index_id
    assert second.counts.documents_growth == 3
    assert second.counts.sqlite_bytes_growth == second.counts.sqlite_bytes - first.counts.sqlite_bytes
    assert second.counts.gzip_bytes_growth == second.counts.gzip_bytes - first.counts.gzip_bytes
    assert f"against {first.counts.index_id}: +3 documents" in second.reason
    assert second.counts.as_json()["documents_growth"] == 3
    assert second.counts.as_json()["previous_index_id"] == first.counts.index_id


def test_index_stage_records_a_refused_runs_shrink_as_negative_growth(world: World) -> None:
    first = world.refresh()
    assert first.counts is not None
    world.suppress(LD, texts(LD, 3))

    report = world.refresh()

    assert report.counts is not None
    assert report.counts.previous_index_id == first.counts.index_id
    assert report.counts.documents_growth == -3
    assert f"against {first.counts.index_id}: -3 documents" in report.reason


def test_index_stage_that_changed_nothing_records_no_growth(world: World) -> None:
    world.refresh()

    again = world.refresh()

    assert again.outcome is StageOutcome.SKIPPED
    assert again.counts is not None
    assert (again.counts.previous_index_id, again.counts.documents_growth) == (None, None)

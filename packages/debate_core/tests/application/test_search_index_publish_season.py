"""`tub index publish --season`: a backfile season's own index, to its own pointer (`v1-e39-t18`).

The PM's shape 4: each season's pointer has its own shrink guard, and the weekly stage's
`current.json` and its guard are untouched. A season's index holds that season's store alone.

The bucket is a directory on disk (`FsEvidenceObjectStore`): no network, no AWS. Every store is
synthetic: invented slugs, sentences and parser versions, sources named by the digest of an invented
phrase. Every expected count is written by hand from the store a test builds.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Final

import pytest

from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.ports.parsed_store import (
    DocumentRecord,
    OccurrenceRecord,
    SourceEntry,
    SourceOutcome,
)
from debate_core.application.ports.suppression import disclosure_digest
from debate_core.application.search_index_build import BuiltSearchIndex, SearchIndexBuildService
from debate_core.application.search_index_publish import (
    SearchIndexPublishService,
    SearchIndexWouldShrink,
    SeasonIndexHoldsOtherStores,
)
from debate_core.application.season_indexes import season_pointer_key
from debate_core.domain.card_occurrence import ClusterMembership
from debate_core.domain.caselist import Event, SourceFormat, SourceOrigin
from debate_core.domain.debate_files import CardCompleteness, FileImportProvenance, ParsedCard, ParsedDocument
from debate_core.domain.search_index import SEARCH_INDEX_POINTER_KEY, SearchIndexPointer
from debate_core.domain.style_profile import StyleMatchSource
from debate_core.evidence.fingerprints import FINGERPRINT_VERSION, card_fingerprint
from debate_core.integrations.local import FsEvidenceObjectStore
from debate_core.integrations.local.search_index import SqliteSearchIndexWriter
from debate_core.integrations.local.suppression_list import local_suppression_list_file
from debate_core.testing.fakes.caselist import InMemoryCaselistRepository
from debate_core.testing.fakes.parsed_store import InMemoryParsedStore

CURRENT_STORE: Final = "hsqq26"
SEASON: Final = "hsxx25"
PARSER: Final = "2026.01.05-synthetic-s"
PROFILE: Final = "2026.01.01-synthetic-profile"
WORDS: Final = ("granite", "basalt", "obsidian", "pumice", "quartz", "feldspar")


def build(tmp_path: Path, caselist: str, cards: int, *, tag: str = "a") -> BuiltSearchIndex:
    """An index of `cards` distinct invented cards of `caselist`, built as `tub index build` builds one."""
    source = hashlib.sha256(f"invented source {caselist} {tag}".encode()).hexdigest()
    parsed = tuple(
        ParsedCard(
            tag=f"Invented {WORDS[number % len(WORDS)]} claim {number} {tag}",
            full_cite=f"Okonkwo 2{number}",
            evidence_text=f"The invented {WORDS[number % len(WORDS)]} study {number} {tag} finds costs rise.",
            completeness=CardCompleteness.FULL,
            match_source=StyleMatchSource.HEURISTIC,
            confidence=0.9,
            provenance=FileImportProvenance(
                source_sha256=source,
                source_path="placeholder.docx",
                origin=SourceOrigin.CASELIST_ARCHIVE,
                caselist=caselist,
                snapshot=date(2026, 9, 1),
                first_element_index=3 * number,
                last_element_index=3 * number + 2,
                parser_version=PARSER,
                profile_version=PROFILE,
            ),
        )
        for number in range(cards)
    )
    store = InMemoryParsedStore()
    fields = {
        "caselist": caselist,
        "snapshot": "2026-09-01",
        "source_sha256": source,
        "parser_version": PARSER,
        "profile_version": PROFILE,
        "fingerprint_version": FINGERPRINT_VERSION,
    }
    document = ParsedDocument(
        source_sha256=source,
        source_path="placeholder.docx",
        parser_version=PARSER,
        profile_version=PROFILE,
        cards=parsed,
    )
    asyncio.run(
        store.write_source(
            caselist,
            PARSER,
            SourceEntry.model_validate(
                {
                    **fields,
                    "source_format": SourceFormat.DOCX,
                    "byte_size": 1,
                    "outcome": SourceOutcome.PARSED,
                    "cards": cards,
                }
            ),
            DocumentRecord.from_parsed_document(
                document,
                caselist=caselist,
                snapshot="2026-09-01",
                fingerprint_version=FINGERPRINT_VERSION,
                camp=None,
            ),
        )
    )
    rows = tuple(
        OccurrenceRecord.model_validate(
            {
                **fields,
                "last_snapshot": "2026-09-08",
                "disclosure": disclosure_digest(caselist, f"Invented School/QX/{tag}.docx"),
                "first_element_index": 3 * number,
                "last_element_index": 3 * number + 2,
                "exact_fingerprint": card_fingerprint(card).exact_fingerprint,
                "cluster_id": card_fingerprint(card).exact_fingerprint,
                "membership": ClusterMembership.NEAR_DUPLICATE,
                "completeness": CardCompleteness.FULL,
            }
        )
        for number, card in enumerate(parsed)
    )
    asyncio.run(store.write_aggregates(caselist, PARSER, index=(), failures=(), occurrences=rows))
    service = SearchIndexBuildService(
        parsed_store=store,
        caselists=InMemoryCaselistRepository(),
        suppression=RecordedSuppressionList(local_suppression_list_file(tmp_path / f"data-{caselist}-{tag}")),
        writer=SqliteSearchIndexWriter(),
        parser_version=PARSER,
        event_for_caselist={caselist: Event.LD}.get,
        release_manifest_lines=lambda _key: (),
    )
    return asyncio.run(service.build((caselist,), tmp_path / f"out-{caselist}-{tag}"))


def publisher(bucket: FsEvidenceObjectStore, season: str | None = None) -> SearchIndexPublishService:
    return SearchIndexPublishService(bucket=bucket, parser_version=PARSER, season=season)


def pointer_at(bucket: FsEvidenceObjectStore, key: str, tmp_path: Path) -> SearchIndexPointer:
    landed = tmp_path / "fetched-pointer.json"
    asyncio.run(bucket.get_file(key, landed))
    return SearchIndexPointer.model_validate_json(landed.read_bytes())


def keys_in(bucket_root: Path) -> Sequence[str]:
    return sorted(str(one.relative_to(bucket_root)) for one in bucket_root.rglob("*") if one.is_file())


@pytest.fixture
def bucket(tmp_path: Path) -> FsEvidenceObjectStore:
    return FsEvidenceObjectStore(tmp_path / "bucket")


def test_a_season_index_is_published_to_its_own_pointer_and_current_json_is_untouched(
    tmp_path: Path, bucket: FsEvidenceObjectStore
) -> None:
    current = build(tmp_path, CURRENT_STORE, 4)
    asyncio.run(publisher(bucket).publish(current.directory))
    before = pointer_at(bucket, SEARCH_INDEX_POINTER_KEY, tmp_path)
    season = build(tmp_path, SEASON, 2)

    published = asyncio.run(publisher(bucket, SEASON).publish(season.directory))

    assert published.pointer_key == season_pointer_key(SEASON)
    assert pointer_at(bucket, season_pointer_key(SEASON), tmp_path).index_id == season.manifest.index_id
    assert pointer_at(bucket, SEARCH_INDEX_POINTER_KEY, tmp_path) == before
    assert before.index_id == current.manifest.index_id


def test_a_season_index_holding_another_store_is_refused_and_nothing_is_uploaded(
    tmp_path: Path, bucket: FsEvidenceObjectStore
) -> None:
    wrong = build(tmp_path, CURRENT_STORE, 2)

    with pytest.raises(SeasonIndexHoldsOtherStores) as refused:
        asyncio.run(publisher(bucket, SEASON).publish(wrong.directory))

    assert refused.value.season == SEASON
    assert refused.value.stores == (CURRENT_STORE,)
    assert keys_in(tmp_path / "bucket") == []


def test_a_season_pointer_has_its_own_shrink_guard(tmp_path: Path, bucket: FsEvidenceObjectStore) -> None:
    asyncio.run(publisher(bucket, SEASON).publish(build(tmp_path, SEASON, 5, tag="full").directory))
    smaller = build(tmp_path, SEASON, 2, tag="small")

    with pytest.raises(SearchIndexWouldShrink) as refused:
        asyncio.run(publisher(bucket, SEASON).publish(smaller.directory))

    assert [(one.store, one.documents, one.current_documents) for one in refused.value.shrinks] == [
        (SEASON, 2, 5)
    ]


def test_the_current_index_does_not_guard_a_season_and_a_season_does_not_guard_the_current_index(
    tmp_path: Path, bucket: FsEvidenceObjectStore
) -> None:
    asyncio.run(publisher(bucket).publish(build(tmp_path, CURRENT_STORE, 6).directory))

    season = asyncio.run(publisher(bucket, SEASON).publish(build(tmp_path, SEASON, 1).directory))
    current = asyncio.run(publisher(bucket).publish(build(tmp_path, CURRENT_STORE, 6, tag="next").directory))

    assert season.replaced is None
    assert current.pointer_key == SEARCH_INDEX_POINTER_KEY
    assert pointer_at(bucket, season_pointer_key(SEASON), tmp_path).index_id == season.index_id

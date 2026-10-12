"""The parsed card store says "refused", not `PermissionError`, and never "nothing here" (`v1-e31-t09`).

`v1-e34-t13` translated the three filesystem stores that sit behind the evidence ports and left
this one, because :class:`LocalParsedStore` walks and reads `<data_dir>/parsed` itself. Until now
a directory the operating system refuses did one of two things there:

* raised a raw `PermissionError`, which reaches the CLI as exit 70, "a bug", with the directory's
  absolute path in its message; or
* **listed fewer sources than the store holds**, because `Path.rglob` skips a directory it may not
  read. `caselist parse` then counted those sources as never parsed.

Each now raises `LocalStoreAccessDenied` naming the directory's role, "the parsed card store",
with the `PermissionError` kept as its cause. The refusals are real: `chmod 000` on a directory
under `tmp_path` (`tests/fixtures/permissions.py`), skipped under root, where modes are ignored.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.fixtures.permissions import needs_permissions, refused

from debate_core.application import errors
from debate_core.application.errors import StoreAccessDenied
from debate_core.application.ports.parsed_store import (
    DocumentRecord,
    OccurrenceRecord,
    SourceEntry,
    SourceOutcome,
    source_object_key,
)
from debate_core.domain.card_occurrence import ClusterMembership
from debate_core.domain.caselist import SourceFormat
from debate_core.domain.debate_files import CardCompleteness
from debate_core.integrations.local.parsed_store import LocalParsedStore
from debate_core.integrations.local.refusals import ACCESS_DENIED_HINT

pytestmark = [pytest.mark.anyio, needs_permissions]

CASELIST = "testcl26"
OTHER_CASELIST = "othercl26"
VERSION = "2026.10.10-docx-2"
PROFILE = "2026.09.20-verbatim-1"
FINGERPRINTS = "card-fingerprint-v1"
ROLE = "the parsed card store"

#: Three sources in three fan-out directories, so that one can be refused and two left readable.
FIRST, SECOND, THIRD = "aa" + "1" * 62, "bb" + "2" * 62, "cc" + "3" * 62


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "evidence"


def entry_for(sha256: str, *, caselist: str = CASELIST, parsed: bool = False) -> SourceEntry:
    fields: dict[str, object] = {
        "caselist": caselist,
        "snapshot": "2026-09-01",
        "source_sha256": sha256,
        "parser_version": VERSION,
        "profile_version": PROFILE,
        "fingerprint_version": FINGERPRINTS,
        "source_format": SourceFormat.DOCX,
        "byte_size": 100,
    }
    if parsed:
        return SourceEntry.model_validate({**fields, "outcome": SourceOutcome.PARSED, "cards": 0})
    return SourceEntry.for_failure(reason="MALFORMED_XML", detail="", **fields)


def document_for(sha256: str) -> DocumentRecord:
    """An invented stored document with no cards: the adapter only has to carry it."""
    return DocumentRecord(
        caselist=CASELIST,
        snapshot="2026-09-01",
        source_sha256=sha256,
        parser_version=VERSION,
        profile_version=PROFILE,
        fingerprint_version=FINGERPRINTS,
        document={
            "source_sha256": sha256,
            "parser_version": VERSION,
            "profile_version": PROFILE,
            "cards": [],
            "warnings": [],
        },
    )


def occurrence_for(sha256: str) -> OccurrenceRecord:
    return OccurrenceRecord(
        caselist=CASELIST,
        snapshot="2026-09-01",
        last_snapshot="2026-09-01",
        source_sha256=sha256,
        parser_version=VERSION,
        profile_version=PROFILE,
        fingerprint_version=FINGERPRINTS,
        disclosure="d" * 64,
        first_element_index=0,
        last_element_index=2,
        exact_fingerprint="e" * 64,
        cluster_id="c" * 64,
        membership=ClusterMembership.NEAR_DUPLICATE,
        completeness=CardCompleteness.FULL,
    )


@pytest.fixture
async def store(data_dir: Path) -> LocalParsedStore:
    """A store holding three sources of one caselist, its aggregates, and one source of another."""
    held = LocalParsedStore(data_dir)
    await held.write_source(CASELIST, VERSION, entry_for(FIRST, parsed=True), document_for(FIRST))
    for sha256 in (SECOND, THIRD):
        await held.write_source(CASELIST, VERSION, entry_for(sha256), None)
    entries = [entry_for(FIRST, parsed=True), entry_for(SECOND), entry_for(THIRD)]
    await held.write_aggregates(
        CASELIST, VERSION, index=entries, failures=entries[1:], occurrences=[occurrence_for(FIRST)]
    )
    await held.write_source(OTHER_CASELIST, VERSION, entry_for(FIRST, caselist=OTHER_CASELIST), None)
    return held


def fan_out_directory(store: LocalParsedStore, sha256: str) -> Path:
    return (store.root / source_object_key(CASELIST, VERSION, sha256)).parent


def assert_refused(
    caught: pytest.ExceptionInfo[StoreAccessDenied], *, operation: str, data_dir: Path
) -> None:
    """A local refusal: the operation, the role, the data-directory hint, the cause, and no path."""
    error = caught.value
    assert type(error) is errors.LocalStoreAccessDenied
    assert (error.operation, error.resource, error.hint) == (operation, ROLE, ACCESS_DENIED_HINT)
    assert errors.error_code_of(error) == "STORE_ACCESS_DENIED"
    assert isinstance(error.__cause__, PermissionError)
    assert str(data_dir) not in str(error)
    assert str(data_dir.parent) not in str(error)


# ------------------------------------------------------------------------------------------------
# Listings: a refused tree is not an empty one
# ------------------------------------------------------------------------------------------------


class TestListingTheStore:
    async def test_the_store_lists_what_it_holds_when_nothing_is_refused(
        self, store: LocalParsedStore
    ) -> None:
        """The baseline every refusal below is measured against."""
        assert await store.version_directories(CASELIST) == (VERSION,)
        assert [entry.source_sha256 for entry in await store.read_entries(CASELIST, VERSION)] == [
            FIRST,
            SECOND,
            THIRD,
        ]

    async def test_version_directories_of_a_refused_root_is_a_refusal(
        self, store: LocalParsedStore, data_dir: Path
    ) -> None:
        with refused(store.root), pytest.raises(StoreAccessDenied) as caught:
            await store.version_directories(CASELIST)

        assert_refused(caught, operation="list", data_dir=data_dir)

    async def test_version_directories_of_a_refused_caselist_is_a_refusal(
        self, store: LocalParsedStore, data_dir: Path
    ) -> None:
        with refused(store.root / CASELIST), pytest.raises(StoreAccessDenied) as caught:
            await store.version_directories(CASELIST)

        assert_refused(caught, operation="list", data_dir=data_dir)

    @pytest.mark.parametrize("depth", ["the root", "the caselist", "the version", "the sources"])
    async def test_entries_under_a_refused_directory_are_a_refusal_at_any_depth(
        self, store: LocalParsedStore, data_dir: Path, depth: str
    ) -> None:
        directory = {
            "the root": store.root,
            "the caselist": store.root / CASELIST,
            "the version": store.root / CASELIST / VERSION,
            "the sources": store.root / CASELIST / VERSION / "sha256",
        }[depth]

        with refused(directory), pytest.raises(StoreAccessDenied) as caught:
            await store.read_entries(CASELIST, VERSION)

        assert_refused(caught, operation="list", data_dir=data_dir)

    async def test_one_refused_fan_out_directory_is_a_refusal_and_not_two_entries_out_of_three(
        self, store: LocalParsedStore, data_dir: Path
    ) -> None:
        """The defect: the walk skipped the directory, and a parsed source read as never parsed."""
        with refused(fan_out_directory(store, SECOND).parent), pytest.raises(StoreAccessDenied) as caught:
            await store.read_entries(CASELIST, VERSION)

        assert_refused(caught, operation="list", data_dir=data_dir)

    async def test_the_deepest_fan_out_directory_refused_is_a_refusal_too(
        self, store: LocalParsedStore, data_dir: Path
    ) -> None:
        with refused(fan_out_directory(store, THIRD)), pytest.raises(StoreAccessDenied) as caught:
            await store.read_entries(CASELIST, VERSION, snapshot="2026-09-01")

        assert_refused(caught, operation="list", data_dir=data_dir)

    async def test_another_caselists_refused_directory_does_not_stop_this_ones_listing(
        self, store: LocalParsedStore
    ) -> None:
        """A listing opens only the directories that could hold what it was asked for."""
        with refused(store.root / OTHER_CASELIST):
            assert await store.version_directories(CASELIST) == (VERSION,)
            assert len(await store.read_entries(CASELIST, VERSION)) == 3

    async def test_a_store_that_does_not_exist_still_lists_nothing(self, data_dir: Path) -> None:
        """Absent is an answer; only refused is not."""
        empty = LocalParsedStore(data_dir)

        assert await empty.version_directories(CASELIST) == ()
        assert await empty.read_entries(CASELIST, VERSION) == ()
        assert await empty.read_document(CASELIST, VERSION, FIRST) is None
        assert await empty.read_index(CASELIST, VERSION) is None


# ------------------------------------------------------------------------------------------------
# Reads and writes
# ------------------------------------------------------------------------------------------------


class TestReadingAndWriting:
    async def test_a_document_under_a_refused_directory_is_a_refusal_not_an_absent_document(
        self, store: LocalParsedStore, data_dir: Path
    ) -> None:
        with refused(fan_out_directory(store, FIRST)), pytest.raises(StoreAccessDenied) as caught:
            await store.read_document(CASELIST, VERSION, FIRST)

        assert_refused(caught, operation="read", data_dir=data_dir)

    async def test_a_source_file_that_may_not_be_opened_is_a_refusal(
        self, store: LocalParsedStore, data_dir: Path
    ) -> None:
        path = store.root / source_object_key(CASELIST, VERSION, FIRST)
        path.chmod(0)
        try:
            with pytest.raises(StoreAccessDenied) as caught:
                await store.read_document(CASELIST, VERSION, FIRST)
            assert_refused(caught, operation="read", data_dir=data_dir)
            with pytest.raises(StoreAccessDenied) as caught:
                await store.read_entries(CASELIST, VERSION)
            assert_refused(caught, operation="read", data_dir=data_dir)
        finally:
            path.chmod(0o644)

    @pytest.mark.parametrize("aggregate", ["read_index", "read_failures", "read_occurrences"])
    async def test_an_aggregate_under_a_refused_directory_is_a_refusal_not_an_absent_file(
        self, store: LocalParsedStore, data_dir: Path, aggregate: str
    ) -> None:
        """`None` means a removal deleted it and the next run rebuilds it. Refused is not that."""
        with refused(store.root / CASELIST / VERSION), pytest.raises(StoreAccessDenied) as caught:
            await getattr(store, aggregate)(CASELIST, VERSION)

        assert_refused(caught, operation="read", data_dir=data_dir)

    async def test_writing_a_source_into_a_refused_directory_is_a_refusal(
        self, store: LocalParsedStore, data_dir: Path
    ) -> None:
        fourth = "dd" + "4" * 62
        sources = store.root / CASELIST / VERSION / "sha256"
        sources.chmod(0o555)
        try:
            with pytest.raises(StoreAccessDenied) as caught:
                await store.write_source(CASELIST, VERSION, entry_for(fourth), None)
        finally:
            sources.chmod(0o755)

        assert_refused(caught, operation="write", data_dir=data_dir)
        assert not fan_out_directory(store, fourth).exists()

    async def test_writing_the_aggregates_into_a_refused_directory_is_a_refusal(
        self, store: LocalParsedStore, data_dir: Path
    ) -> None:
        version = store.root / CASELIST / VERSION
        before = (version / "index.jsonl").read_bytes()
        version.chmod(0o555)
        try:
            with pytest.raises(StoreAccessDenied) as caught:
                await store.write_aggregates(CASELIST, VERSION, index=[], failures=[], occurrences=[])
        finally:
            version.chmod(0o755)

        assert_refused(caught, operation="write", data_dir=data_dir)
        assert (version / "index.jsonl").read_bytes() == before

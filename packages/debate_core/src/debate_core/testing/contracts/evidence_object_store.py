"""What every `EvidenceObjectStore` must do, whatever it stores objects in.

The named half of the evidence store: manifests, reports, built files — the objects a caller finds by
the name it gave them rather than by a digest. One suite, two implementations
(:class:`~debate_core.integrations.s3.S3EvidenceObjectStore` over a bucket and
:class:`~debate_core.integrations.local.FsEvidenceObjectStore` over a directory), because
`v1-e29-t05-evidence-sync-cli` diffs one against the other and moves what differs. A diff is only
meaningful if both sides answer the same questions the same way, and this is where that is settled
rather than assumed (architecture proposal §16, §17).

Four things it pins down, each of which the two implementations could reasonably have disagreed about:

* **A listing is sorted by key and states no digests.** Both rules are in the port's docstring, and
  both are here because a sync plan built from an unsorted listing is unreproducible and a listing
  that hashed 60,000 objects would be one no caller could afford.
* **`head` states the digest the store recorded**, and a `put_file` is what records it.
* **A round trip is byte-identical**, and a download that cannot be verified lands nothing.
* **A missing object is `NotFound` from `head` and `get_file`**, while a prefix that matches nothing
  is an empty listing and not an error.

What it deliberately leaves alone is where an object physically goes: a bucket key, a path under an
evidence directory, whether a directory is created eagerly. Those are in each adapter's own tests.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path

import pytest

from debate_core.application.errors import NotFound
from debate_core.application.ports import EvidenceObjectStore
from debate_core.testing.contracts.harness import AdapterContract

__all__ = ["EvidenceObjectStoreContract", "EvidenceObjectStoreFactory"]

type EvidenceObjectStoreFactory = Callable[[], EvidenceObjectStore]
"""Returns another handle onto the same object store."""

#: A manifest row and a report, real-looking rather than `b"a"` so a failure names which came back.
CASELIST_MANIFEST = (
    b'{"sha256":"5e88489","bytes":48213,"content_type":"application/pdf","caselist":"hsld26"}\n'
)
SYNC_REPORT = b'{"run":"2026-09-15T06-00Z","new":41,"changed":0,"skipped":1174}\n'

#: Keys from `docs/architecture/evidence-store-layout.md`, so the contract exercises real names.
MANIFEST_KEY = "manifests/hsld26/2026-09-15.jsonl"
OTHER_MANIFEST_KEY = "manifests/hsld26/2026-09-22.jsonl"
REPORT_KEY = "reports/sync/2026-09-15T06-00Z.json"
UNWRITTEN_KEY = "manifests/hsld26/nothing-was-ever-written-here.jsonl"


class EvidenceObjectStoreContract(AdapterContract):
    """Subclass this in a `Test…` class and override `make_adapter` to hold a store to the contract."""

    @pytest.fixture
    def make_adapter(self) -> EvidenceObjectStoreFactory:
        """Return a factory handing out handles onto one empty object store.

        A binding must override this. See `README.md` in this directory.
        """
        raise NotImplementedError(
            "an EvidenceObjectStoreContract binding must override the `make_adapter` fixture with "
            "a factory returning handles onto one empty object store"
        )

    @pytest.fixture
    def store(self, make_adapter: EvidenceObjectStoreFactory) -> EvidenceObjectStore:
        """The store under test; the contract's tests use this rather than the factory."""
        return make_adapter()

    @pytest.fixture
    def manifest_file(self, tmp_path: Path) -> Path:
        """A local file to upload, since this port moves files rather than bytes."""
        source = tmp_path / "source" / "2026-09-15.jsonl"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(CASELIST_MANIFEST)
        return source

    # ----------------------------------------------------------------------------------------
    # Putting and getting
    # ----------------------------------------------------------------------------------------

    async def test_put_file_reports_the_size_and_digest_of_what_it_stored(
        self, store: EvidenceObjectStore, manifest_file: Path
    ) -> None:
        """The digest comes back from the write, so a caller never has to re-read to learn it."""
        stored = await store.put_file(MANIFEST_KEY, manifest_file)

        assert stored.key == MANIFEST_KEY
        assert stored.size == len(CASELIST_MANIFEST)
        assert stored.sha256 == hashlib.sha256(CASELIST_MANIFEST).hexdigest()

    async def test_an_object_round_trips_byte_for_byte(
        self, store: EvidenceObjectStore, manifest_file: Path, tmp_path: Path
    ) -> None:
        await store.put_file(MANIFEST_KEY, manifest_file)

        destination = tmp_path / "downloaded" / "2026-09-15.jsonl"
        got = await store.get_file(MANIFEST_KEY, destination)

        assert destination.read_bytes() == CASELIST_MANIFEST
        assert got.sha256 == hashlib.sha256(CASELIST_MANIFEST).hexdigest()

    async def test_get_file_creates_the_directories_it_needs(
        self, store: EvidenceObjectStore, manifest_file: Path, tmp_path: Path
    ) -> None:
        """A caller mirroring a bucket's layout locally should not have to pre-build the tree."""
        await store.put_file(MANIFEST_KEY, manifest_file)

        destination = tmp_path / "a" / "b" / "c" / "2026-09-15.jsonl"
        await store.get_file(MANIFEST_KEY, destination)

        assert destination.read_bytes() == CASELIST_MANIFEST

    async def test_an_empty_object_round_trips(
        self, store: EvidenceObjectStore, tmp_path: Path
    ) -> None:
        """An empty manifest is an empty manifest, not a failed write."""
        empty = tmp_path / "empty.jsonl"
        empty.write_bytes(b"")

        stored = await store.put_file(MANIFEST_KEY, empty)

        assert stored.size == 0
        assert (await store.head(MANIFEST_KEY)).size == 0
        assert (await store.get_file(MANIFEST_KEY, tmp_path / "out.jsonl")).size == 0
        assert (tmp_path / "out.jsonl").read_bytes() == b""

    async def test_a_named_object_may_be_replaced(
        self, store: EvidenceObjectStore, manifest_file: Path, tmp_path: Path
    ) -> None:
        """The difference from the snapshot store: a re-published manifest is still that manifest.

        A content-addressed blob must never come through this port, which is why the rule can be this
        permissive here and absolute there.
        """
        await store.put_file(MANIFEST_KEY, manifest_file)
        appended = tmp_path / "appended.jsonl"
        appended.write_bytes(CASELIST_MANIFEST + SYNC_REPORT)

        replaced = await store.put_file(MANIFEST_KEY, appended)

        assert replaced.size == len(CASELIST_MANIFEST + SYNC_REPORT)
        assert (await store.head(MANIFEST_KEY)).sha256 == hashlib.sha256(
            CASELIST_MANIFEST + SYNC_REPORT
        ).hexdigest()

    async def test_a_second_handle_reads_what_the_first_stored(
        self,
        store: EvidenceObjectStore,
        make_adapter: EvidenceObjectStoreFactory,
        manifest_file: Path,
        tmp_path: Path,
    ) -> None:
        """Two handles are two views of one store, not two stores."""
        await store.put_file(MANIFEST_KEY, manifest_file)

        other = make_adapter()

        assert (await other.head(MANIFEST_KEY)).size == len(CASELIST_MANIFEST)
        await other.get_file(MANIFEST_KEY, tmp_path / "from-the-other-handle.jsonl")
        assert (tmp_path / "from-the-other-handle.jsonl").read_bytes() == CASELIST_MANIFEST

    # ----------------------------------------------------------------------------------------
    # Heading
    # ----------------------------------------------------------------------------------------

    async def test_head_states_the_size_and_the_digest_the_store_recorded(
        self, store: EvidenceObjectStore, manifest_file: Path
    ) -> None:
        """What a sync diffs on, without reading the object."""
        await store.put_file(MANIFEST_KEY, manifest_file)

        found = await store.head(MANIFEST_KEY)

        assert found.key == MANIFEST_KEY
        assert found.size == len(CASELIST_MANIFEST)
        assert found.sha256 == hashlib.sha256(CASELIST_MANIFEST).hexdigest()

    async def test_heading_an_object_that_was_never_written_raises_not_found(
        self, store: EvidenceObjectStore
    ) -> None:
        with pytest.raises(NotFound) as refused:
            await store.head(UNWRITTEN_KEY)

        assert refused.value.key == UNWRITTEN_KEY

    async def test_getting_an_object_that_was_never_written_raises_not_found(
        self, store: EvidenceObjectStore, tmp_path: Path
    ) -> None:
        with pytest.raises(NotFound) as refused:
            await store.get_file(UNWRITTEN_KEY, tmp_path / "nothing")

        assert refused.value.key == UNWRITTEN_KEY
        assert not (tmp_path / "nothing").exists()

    # ----------------------------------------------------------------------------------------
    # Listing
    # ----------------------------------------------------------------------------------------

    async def test_a_listing_returns_the_objects_under_the_prefix_sorted_by_key(
        self, store: EvidenceObjectStore, manifest_file: Path
    ) -> None:
        """Sorted, so that a sync plan and its printed summary are reproducible."""
        await store.put_file(OTHER_MANIFEST_KEY, manifest_file)
        await store.put_file(MANIFEST_KEY, manifest_file)
        await store.put_file(REPORT_KEY, manifest_file)

        manifests = await store.list_objects("manifests/")

        assert [found.key for found in manifests] == [MANIFEST_KEY, OTHER_MANIFEST_KEY]

    async def test_a_listing_states_sizes_but_no_digests(
        self, store: EvidenceObjectStore, manifest_file: Path
    ) -> None:
        """The rule that keeps a listing's cost the same in a directory and in a bucket."""
        await store.put_file(MANIFEST_KEY, manifest_file)

        listed = await store.list_objects("")

        assert [(found.size, found.sha256) for found in listed] == [(len(CASELIST_MANIFEST), None)]

    async def test_an_empty_prefix_lists_the_whole_store(
        self, store: EvidenceObjectStore, manifest_file: Path
    ) -> None:
        await store.put_file(MANIFEST_KEY, manifest_file)
        await store.put_file(REPORT_KEY, manifest_file)

        assert [found.key for found in await store.list_objects("")] == [MANIFEST_KEY, REPORT_KEY]

    async def test_a_prefix_is_matched_as_a_string_and_not_as_a_path(
        self, store: EvidenceObjectStore, manifest_file: Path
    ) -> None:
        """`manifests/hs` matches `manifests/hsld26/…`, as it does in S3."""
        await store.put_file(MANIFEST_KEY, manifest_file)
        await store.put_file(REPORT_KEY, manifest_file)

        assert [found.key for found in await store.list_objects("manifests/hs")] == [MANIFEST_KEY]

    async def test_a_prefix_that_matches_nothing_is_an_empty_listing_and_not_an_error(
        self, store: EvidenceObjectStore, manifest_file: Path
    ) -> None:
        """Absence is an ordinary answer to a listing."""
        await store.put_file(MANIFEST_KEY, manifest_file)

        assert await store.list_objects("exports/") == ()

    async def test_listing_an_empty_store_is_an_empty_listing(
        self, store: EvidenceObjectStore
    ) -> None:
        assert await store.list_objects("") == ()

    # ----------------------------------------------------------------------------------------
    # Keys that must never reach storage
    # ----------------------------------------------------------------------------------------

    @pytest.mark.parametrize(
        "unusable_key",
        ["", "/manifests/x.jsonl", "manifests/../../etc/passwd", "manifests//x.jsonl", "manifests/"],
        ids=["empty", "absolute", "escaping", "empty-segment", "trailing-slash"],
    )
    async def test_an_unusable_key_is_refused_by_every_method(
        self, store: EvidenceObjectStore, manifest_file: Path, tmp_path: Path, unusable_key: str
    ) -> None:
        """`ValueError`, not a `DomainError`: no listing of any store can produce such a key.

        This is the traversal guard, so it is checked on the way *in* — before anything is written or
        read — and on every method rather than only the one a reviewer happened to think about.
        """
        with pytest.raises(ValueError):
            await store.put_file(unusable_key, manifest_file)
        with pytest.raises(ValueError):
            await store.head(unusable_key)
        with pytest.raises(ValueError):
            await store.get_file(unusable_key, tmp_path / "nothing")

    async def test_putting_a_local_file_that_does_not_exist_is_the_callers_error(
        self, store: EvidenceObjectStore, tmp_path: Path
    ) -> None:
        """A named source that is not there is a bug in the caller, not a condition of the store."""
        with pytest.raises(FileNotFoundError):
            await store.put_file(MANIFEST_KEY, tmp_path / "was-never-created.jsonl")

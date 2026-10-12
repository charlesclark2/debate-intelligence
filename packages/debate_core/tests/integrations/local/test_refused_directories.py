"""The three filesystem stores `v1-e01-t20` left alone say "refused", not `PermissionError` (`v1-e34-t13`).

`FsEvidenceObjectStore`, `FsEvidenceVersionStore` and `LocalAppendOnlyFile` each met a directory the
operating system refuses with a raw `PermissionError`, which reaches the CLI as exit 70, "a bug",
with the directory's absolute path in its message. `FsEvidenceObjectStore.list_objects` was worse:
it listed nothing, and every caller then acted on an empty store.

Each now raises `LocalStoreAccessDenied`, the `StoreAccessDenied` the filesystem adapters raise,
naming the directory's role and never its path, with the `PermissionError` kept as its cause. The
refusals are real: `chmod 000` on a directory under `tmp_path` (`tests/fixtures/permissions.py`),
skipped under root, where modes are ignored.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.fixtures.permissions import needs_permissions, refused

from debate_core.application import errors
from debate_core.application.errors import StoreAccessDenied
from debate_core.application.ports.evidence_versions import ObjectVersion
from debate_core.integrations.local import FsEvidenceObjectStore
from debate_core.integrations.local.fs_version_store import FsEvidenceVersionStore
from debate_core.integrations.local.refusals import ACCESS_DENIED_HINT
from debate_core.integrations.local.suppression_list import local_suppression_list_file

pytestmark = [pytest.mark.anyio, needs_permissions]

MANIFEST_KEY = "manifests/hsld26/2026-09-15.jsonl"
REPORT_KEY = "reports/sync-runs/2026/20260916T060000Z.json"
BLOB_KEY = "sha256/5e/88/5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8"
LIST_LINE = '{"schema_version":1,"action":"suppress"}'


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "evidence"


@pytest.fixture
def a_file(tmp_path: Path) -> Path:
    source = tmp_path / "a-file"
    source.write_bytes(b"one synthetic line\n")
    return source


def assert_refused(
    caught: pytest.ExceptionInfo[StoreAccessDenied], *, operation: str, role: str, data_dir: Path
) -> None:
    """A local refusal: the operation, the directory's role, the data-directory hint, and no path.

    The subclass and the code function are looked up here rather than imported by name, so that
    against a build without them each test fails on what the store did, not at import.
    """
    error = caught.value
    assert type(error) is errors.LocalStoreAccessDenied
    assert (error.operation, error.resource, error.hint) == (operation, role, ACCESS_DENIED_HINT)
    assert errors.error_code_of(error) == "STORE_ACCESS_DENIED"
    assert isinstance(error.__cause__, PermissionError)
    assert str(data_dir) not in str(error)
    assert str(data_dir.parent) not in str(error)


# ------------------------------------------------------------------------------------------------
# FsEvidenceObjectStore
# ------------------------------------------------------------------------------------------------


class TestTheObjectStore:
    async def test_listing_a_refused_root_raises_instead_of_listing_nothing(
        self, data_dir: Path, a_file: Path
    ) -> None:
        """The defect `v1-e01-t20` measured: one object is stored, and a listing of the refused
        tree used to answer `()`."""
        store = FsEvidenceObjectStore(data_dir)
        await store.put_file(MANIFEST_KEY, a_file)

        with refused(store.root), pytest.raises(StoreAccessDenied) as caught:
            await store.list_objects("")

        assert_refused(caught, operation="list", role="the evidence object directory", data_dir=data_dir)

    async def test_listing_a_prefix_whose_directory_is_refused_names_that_directory(
        self, data_dir: Path, a_file: Path
    ) -> None:
        store = FsEvidenceObjectStore(data_dir)
        await store.put_file(MANIFEST_KEY, a_file)

        with refused(store.root / "manifests"), pytest.raises(StoreAccessDenied) as caught:
            await store.list_objects("manifests/hsld26/")

        assert_refused(caught, operation="list", role="the manifest directory", data_dir=data_dir)

    async def test_a_refused_directory_deeper_in_the_prefix_is_a_refusal_too(
        self, data_dir: Path, a_file: Path
    ) -> None:
        """`manifests/` can be read and the caselist's own directory under it cannot."""
        store = FsEvidenceObjectStore(data_dir)
        await store.put_file(MANIFEST_KEY, a_file)

        with refused(store.root / "manifests" / "hsld26"), pytest.raises(StoreAccessDenied) as caught:
            await store.list_objects("manifests/")

        assert_refused(caught, operation="list", role="the manifest directory", data_dir=data_dir)

    async def test_a_refused_directory_that_could_hold_no_match_does_not_stop_the_listing(
        self, data_dir: Path, a_file: Path
    ) -> None:
        """`reports/` holds no key starting `manifests/`, so it is never opened."""
        store = FsEvidenceObjectStore(data_dir)
        await store.put_file(MANIFEST_KEY, a_file)
        await store.put_file(REPORT_KEY, a_file)

        with refused(store.root / "reports"):
            listed = await store.list_objects("manifests/")

        assert [info.key for info in listed] == [MANIFEST_KEY]

    async def test_a_store_whose_root_does_not_exist_still_lists_nothing(self, data_dir: Path) -> None:
        """Absent is an answer; only refused is not."""
        assert await FsEvidenceObjectStore(data_dir).list_objects("") == ()

    async def test_the_blob_tree_is_named_as_the_blob_directory(self, data_dir: Path, a_file: Path) -> None:
        """The same class rooted at `blobs/`, as publish, status and `store sync` list it."""
        blobs = FsEvidenceObjectStore(data_dir, subdirectory=Path("blobs"))
        await blobs.put_file(BLOB_KEY, a_file)

        with refused(blobs.root), pytest.raises(StoreAccessDenied) as caught:
            await blobs.list_objects("")

        assert_refused(caught, operation="list", role="the blob directory", data_dir=data_dir)

    async def test_head_get_and_put_under_a_refused_directory_are_refusals(
        self, data_dir: Path, a_file: Path, tmp_path: Path
    ) -> None:
        store = FsEvidenceObjectStore(data_dir)
        await store.put_file(MANIFEST_KEY, a_file)
        manifests = store.root / "manifests"

        with refused(manifests), pytest.raises(StoreAccessDenied) as caught:
            await store.head(MANIFEST_KEY)
        assert_refused(caught, operation="read", role="the manifest directory", data_dir=data_dir)

        with refused(manifests), pytest.raises(StoreAccessDenied) as caught:
            await store.get_file(MANIFEST_KEY, tmp_path / "copy.jsonl")
        assert_refused(caught, operation="read", role="the manifest directory", data_dir=data_dir)
        assert not (tmp_path / "copy.jsonl").exists()

        with refused(manifests), pytest.raises(StoreAccessDenied) as caught:
            await store.put_file("manifests/hsld26/2026-09-22.jsonl", a_file)
        assert_refused(caught, operation="write", role="the manifest directory", data_dir=data_dir)


# ------------------------------------------------------------------------------------------------
# FsEvidenceVersionStore
# ------------------------------------------------------------------------------------------------


class TestTheVersionStore:
    @pytest.fixture
    def blobs(self, data_dir: Path) -> FsEvidenceVersionStore:
        store = FsEvidenceVersionStore(data_dir / "blobs")
        path = store.root / BLOB_KEY
        path.parent.mkdir(parents=True)
        path.write_bytes(b"a synthetic disclosed file\n")
        return store

    async def test_listing_under_a_refused_root_raises_instead_of_listing_nothing(
        self, blobs: FsEvidenceVersionStore, data_dir: Path
    ) -> None:
        """A removal asks whether this machine holds a blob. "Refused" must not read as "no"."""
        assert [version.key for version in await blobs.list_versions(BLOB_KEY)] == [BLOB_KEY]

        with refused(blobs.root), pytest.raises(StoreAccessDenied) as caught:
            await blobs.list_versions(BLOB_KEY)

        assert_refused(caught, operation="list", role="the blob directory", data_dir=data_dir)

    async def test_listing_under_a_refused_fan_out_directory_is_a_refusal(
        self, blobs: FsEvidenceVersionStore, data_dir: Path
    ) -> None:
        with refused(blobs.root / "sha256" / "5e"), pytest.raises(StoreAccessDenied) as caught:
            await blobs.list_versions(BLOB_KEY)

        assert_refused(caught, operation="list", role="the blob directory", data_dir=data_dir)

    async def test_reading_and_deleting_under_a_refused_directory_are_refusals(
        self, blobs: FsEvidenceVersionStore, data_dir: Path, tmp_path: Path
    ) -> None:
        version = ObjectVersion(key=BLOB_KEY, version_id=None, size=27)
        fan_out = (blobs.root / BLOB_KEY).parent

        with refused(fan_out), pytest.raises(StoreAccessDenied) as caught:
            await blobs.get_version_file(version, tmp_path / "copy")
        assert_refused(caught, operation="read", role="the blob directory", data_dir=data_dir)

        with refused(fan_out), pytest.raises(StoreAccessDenied) as caught:
            await blobs.delete_versions([version])
        assert_refused(caught, operation="delete", role="the blob directory", data_dir=data_dir)
        assert (blobs.root / BLOB_KEY).is_file(), "nothing was deleted"

    async def test_a_version_that_is_not_refused_is_still_copied_to_where_the_caller_asks(
        self, blobs: FsEvidenceVersionStore, tmp_path: Path
    ) -> None:
        """The read was rewritten to tell the store's refusal from the destination's; it still copies."""
        version = ObjectVersion(key=BLOB_KEY, version_id=None, size=27)

        await blobs.get_version_file(version, tmp_path / "taken-out" / "copy")

        assert (tmp_path / "taken-out" / "copy").read_bytes() == b"a synthetic disclosed file\n"

    async def test_the_parsed_tree_is_named_as_the_parsed_card_store(self, data_dir: Path) -> None:
        parsed = FsEvidenceVersionStore(data_dir / "parsed")
        (parsed.root / "hsld26").mkdir(parents=True)
        (parsed.root / "hsld26" / "a-parsed-file.json").write_bytes(b"{}\n")

        with refused(parsed.root), pytest.raises(StoreAccessDenied) as caught:
            await parsed.list_versions("hsld26/")

        assert_refused(caught, operation="list", role="the parsed card store", data_dir=data_dir)

    async def test_a_root_that_does_not_exist_still_lists_nothing(self, data_dir: Path) -> None:
        assert await FsEvidenceVersionStore(data_dir / "parsed").list_versions("hsld26/") == ()


# ------------------------------------------------------------------------------------------------
# LocalAppendOnlyFile
# ------------------------------------------------------------------------------------------------


class TestTheAppendOnlyFile:
    async def test_reading_a_refused_suppression_directory_is_a_refusal_not_an_empty_list(
        self, data_dir: Path
    ) -> None:
        """An empty list suppresses nothing, so a list that cannot be read must never read as one."""
        record = local_suppression_list_file(data_dir)
        await record.append_lines([LIST_LINE])
        assert await record.read_lines() == (LIST_LINE,)

        with refused(record.path.parent), pytest.raises(StoreAccessDenied) as caught:
            await record.read_lines()

        assert_refused(caught, operation="read", role="the suppression directory", data_dir=data_dir)

    async def test_appending_under_a_refused_suppression_directory_is_a_refusal(self, data_dir: Path) -> None:
        record = local_suppression_list_file(data_dir)
        await record.append_lines([LIST_LINE])
        directory = record.path.parent
        directory.chmod(0o500)  # readable and searchable, so the read succeeds, and not writable
        record.path.chmod(0o400)
        try:
            with pytest.raises(StoreAccessDenied) as caught:
                await record.append_lines(['{"schema_version":1,"action":"unsuppress"}'])
        finally:
            directory.chmod(0o700)
            record.path.chmod(0o600)

        assert_refused(caught, operation="write", role="the suppression directory", data_dir=data_dir)
        assert await record.read_lines() == (LIST_LINE,), "nothing was appended"

    async def test_a_list_that_does_not_exist_is_still_an_empty_one(self, data_dir: Path) -> None:
        assert await local_suppression_list_file(data_dir).read_lines() == ()

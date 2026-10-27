"""The raw sources a restored copy's manifests name, fetched into the copy (`v1-e40-t10`).

Each rule of :mod:`debate_core.application.caselist.run_state_sources` on its own, against moto's S3
and a temporary directory standing for the copy. The whole command, restore and all, is tested through
the CLI in `debate_cli/tests/bucket_mode/test_restore_run_state_with_sources.py`. What is here:

* exactly the sources the copy's manifests name are fetched, each from its own key, never another
  object under `raw/`; `--caselist` and `--snapshot` narrow the manifests read;
* bytes that do not hash to the digest named are deleted and refused, and no file in the copy keeps
  them, whether the bucket's recorded digest agrees with them or not;
* a named source the bucket does not hold stops the fetch with the count, unless the suppression list
  holds it, when it is skipped and counted; a `403` for a missing key is a missing source, and a
  `403` for a key that is there stays a refusal;
* a disk without room for the sources and the margin is refused before any fetch;
* nothing is written outside the copy's directory.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast

import pytest

from debate_core.application.caselist import run_state_sources
from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.publish_plan import local_blob_key, source_key
from debate_core.application.caselist.run_state_sources import (
    FREE_SPACE_MARGIN_BYTES,
    RestoredSources,
    RestoredSourcesIncomplete,
    SnapshotsNotRestored,
    SourceSelection,
    SourcesFetched,
    SourcesPlan,
    TooLittleRoomForSources,
)
from debate_core.application.errors import NotFound, StoreAccessDenied
from debate_core.application.ports.evidence_store import EvidenceObjectStore, ObjectInfo, ObjectKey
from debate_core.application.ports.suppression import (
    PathHoldEntry,
    ReasonCode,
    SuppressionAction,
    SuppressionEntry,
    SuppressionState,
    disclosure_digest,
)
from debate_core.integrations.local import BLOB_DIRECTORY, FsEvidenceObjectStore
from debate_core.integrations.s3 import S3EvidenceObjectStore

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

CASELIST: Final = "testcl26"
WEEK_1: Final = "2026-09-15"
WEEK_2: Final = "2026-09-22"
CAMP: Final = "2026-ndi"
NO_SUPPRESSION: Final = SuppressionState.from_entries(())
ROOMY: Final = 10 * FREE_SPACE_MARGIN_BYTES


def body(name: str) -> bytes:
    return f"fictional source {name}\n".encode()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


ONLY_WEEK_1, BOTH_WEEKS, ONLY_WEEK_2, CAMP_FILE, NEVER_NAMED = (
    body(name) for name in ("week one", "both weeks", "week two", "camp", "never named")
)


def row(data: bytes, path: str) -> dict[str, object]:
    return {
        "kind": "member",
        "path": path,
        "sha256": digest(data),
        "byte_size": len(data),
        "classification": "NEW",
        "source_format": "docx",
    }


MANIFESTS: Final[dict[tuple[str, str], list[dict[str, object]]]] = {
    (CASELIST, WEEK_1): [
        row(ONLY_WEEK_1, "Fictional High/AB/r1.docx"),
        row(BOTH_WEEKS, "Fictional High/AB/r2.docx"),
    ],
    (CASELIST, WEEK_2): [
        row(BOTH_WEEKS, "Fictional High/AB/r2.docx"),
        row(ONLY_WEEK_2, "Fictional High/CD/r1.docx"),
    ],
    ("openev", CAMP): [row(CAMP_FILE, "Fictional Camp/aff.docx")],
}
"""Three manifests naming four distinct sources, one of them twice."""

KEYS: Final[dict[bytes, str]] = {
    ONLY_WEEK_1: source_key(CASELIST, WEEK_1, digest(ONLY_WEEK_1)),
    BOTH_WEEKS: source_key(CASELIST, WEEK_1, digest(BOTH_WEEKS)),
    ONLY_WEEK_2: source_key(CASELIST, WEEK_2, digest(ONLY_WEEK_2)),
    CAMP_FILE: source_key("openev", CAMP, digest(CAMP_FILE)),
}


def evidence_at(directory: Path) -> LocalEvidence:
    objects = FsEvidenceObjectStore(directory)
    blobs = FsEvidenceObjectStore(directory, subdirectory=BLOB_DIRECTORY.parent)
    return LocalEvidence(
        objects=objects, blobs=blobs, object_path_for=objects.path_for, blob_path_for=blobs.path_for
    )


def a_restored_copy(root: Path) -> Path:
    """The copy as the restore leaves it: manifests, and an empty blob tree."""
    copy = root / "copy"
    for (caselist, snapshot), rows in MANIFESTS.items():
        manifest = copy / "objects" / "manifests" / caselist / f"{snapshot}.jsonl"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text("".join(json.dumps(each) + "\n" for each in rows), encoding="utf-8")
    return copy


def put_raw(client: S3Client, bucket: str, key: str, data: bytes, *, recorded: str | None = None) -> None:
    """A raw object as the publisher leaves it: its digest recorded in the metadata, unless overridden."""
    client.put_object(Bucket=bucket, Key=key, Body=data, Metadata={"sha256": recorded or digest(data)})


def a_published_bucket(client: S3Client, bucket: str) -> None:
    """Every named source at its key, and decoys under the same prefixes that no manifest names."""
    for data, key in KEYS.items():
        put_raw(client, bucket, key, data)
    put_raw(client, bucket, source_key(CASELIST, WEEK_1, digest(NEVER_NAMED)), NEVER_NAMED)
    put_raw(client, bucket, source_key("openev", "2026-gdi", digest(b"another camp")), b"another camp")


def sources(
    copy: Path, store: EvidenceObjectStore, *, free: int = ROOMY, local: LocalEvidence | None = None
) -> RestoredSources:
    return RestoredSources(
        bucket=store, local=local or evidence_at(copy), directory=copy, free_bytes=lambda _: free
    )


def blob(copy: Path, data: bytes) -> Path:
    return copy / BLOB_DIRECTORY.parent / local_blob_key(digest(data))


def every_file(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


EVERY_MANIFEST: Final = SourceSelection()


def fetch(
    restored: RestoredSources,
    selection: SourceSelection = EVERY_MANIFEST,
    state: SuppressionState = NO_SUPPRESSION,
) -> tuple[SourcesPlan, SourcesFetched]:
    """Plan, check the room and fetch, as the restore does."""

    async def both() -> tuple[SourcesPlan, SourcesFetched]:
        plan = await restored.plan(selection, state)
        restored.refuse_too_little_room(plan)
        return plan, await restored.fetch(plan)

    return asyncio.run(both())


# ------------------------------------------------------------------------------------------------
# Exactly the sources the manifests name
# ------------------------------------------------------------------------------------------------


def test_every_source_the_manifests_name_is_fetched_from_its_own_key_and_nothing_else(
    tmp_path: Path, s3_client: S3Client, evidence_bucket: str
) -> None:
    copy = a_restored_copy(tmp_path)
    a_published_bucket(s3_client, evidence_bucket)
    manifests_before = every_file(copy / "objects")

    plan, fetched = fetch(sources(copy, S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client)))

    assert {source.key for source in plan.to_fetch} == set(KEYS.values())
    assert plan.bytes_to_fetch == sum(len(data) for data in KEYS)
    assert fetched == SourcesFetched(
        manifests=3, named=4, fetched=4, fetched_bytes=sum(len(data) for data in KEYS), suppressed=0
    )
    for data in KEYS:
        assert blob(copy, data).read_bytes() == data
    assert not blob(copy, NEVER_NAMED).exists(), "a raw object no manifest names is never fetched"
    assert sorted(every_file(copy / BLOB_DIRECTORY.parent)) == sorted(
        local_blob_key(digest(data)) for data in KEYS
    ), "the blob tree holds the named sources and nothing else: no landing file is left"
    assert every_file(copy / "objects") == manifests_before


class Recording:
    """The bucket's adapter, recording every call; a listing is recorded with its prefix."""

    def __init__(self, inner: EvidenceObjectStore) -> None:
        self.inner = inner
        self.calls: list[tuple[str, str]] = []

    async def list_objects(self, prefix: str) -> tuple[ObjectInfo, ...]:
        self.calls.append(("list", prefix))
        return await self.inner.list_objects(prefix)

    def store(self) -> EvidenceObjectStore:
        return cast("EvidenceObjectStore", self)

    async def get_file(self, key: ObjectKey, destination: Path) -> ObjectInfo:
        self.calls.append(("get", key))
        return await self.inner.get_file(key, destination)

    def __getattr__(self, name: str) -> object:
        return getattr(self.inner, name)


def test_no_listing_of_raw_is_asked_and_each_key_is_read_once(
    tmp_path: Path, s3_client: S3Client, evidence_bucket: str
) -> None:
    copy = a_restored_copy(tmp_path)
    a_published_bucket(s3_client, evidence_bucket)
    store = Recording(S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client))

    fetch(sources(copy, store.store()))

    assert [call for call in store.calls if call[0] == "list"] == []
    assert sorted(key for _, key in store.calls) == sorted(KEYS.values())


@pytest.mark.parametrize(
    ("selection", "expected"),
    [
        (SourceSelection(caselists=(CASELIST,)), [ONLY_WEEK_1, BOTH_WEEKS, ONLY_WEEK_2]),
        (SourceSelection(caselists=("openev",)), [CAMP_FILE]),
        (SourceSelection(caselists=(CASELIST,), snapshots=(WEEK_2,)), [BOTH_WEEKS, ONLY_WEEK_2]),
        (SourceSelection(snapshots=(WEEK_1, CAMP)), [ONLY_WEEK_1, BOTH_WEEKS, CAMP_FILE]),
    ],
    ids=["one caselist", "camp releases", "one caselist's week", "a week and a camp release"],
)
def test_caselists_and_snapshots_narrow_the_manifests_read(
    tmp_path: Path,
    s3_client: S3Client,
    evidence_bucket: str,
    selection: SourceSelection,
    expected: list[bytes],
) -> None:
    copy = a_restored_copy(tmp_path)
    a_published_bucket(s3_client, evidence_bucket)

    _, fetched = fetch(
        sources(copy, S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client)), selection
    )

    held = {data for data in KEYS if blob(copy, data).exists()}
    assert held == set(expected)
    assert fetched.fetched == len(expected)


def test_a_snapshot_named_that_no_selected_manifest_is_fetches_nothing(
    tmp_path: Path, s3_client: S3Client, evidence_bucket: str
) -> None:
    copy = a_restored_copy(tmp_path)
    a_published_bucket(s3_client, evidence_bucket)
    restored = sources(copy, S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client))

    with pytest.raises(SnapshotsNotRestored) as refused:
        fetch(restored, SourceSelection(caselists=("openev",), snapshots=(CAMP, WEEK_2)))

    assert refused.value.snapshots_not_restored == 1
    assert not (copy / BLOB_DIRECTORY.parent).exists()


# ------------------------------------------------------------------------------------------------
# Each source checked against its digest
# ------------------------------------------------------------------------------------------------

OTHER_BYTES: Final = b"bytes that are not the source the manifest names\n"


@pytest.mark.parametrize(
    "recorded",
    ["the other bytes' digest", "the named digest"],
    ids=["the bucket records the other bytes", "the bucket records the named digest"],
)
def test_bytes_that_are_not_the_digest_named_are_deleted_and_refused(
    tmp_path: Path, s3_client: S3Client, evidence_bucket: str, recorded: str
) -> None:
    """Whether the bucket's own metadata agrees with the wrong bytes or not, none of them is kept."""
    copy = a_restored_copy(tmp_path)
    a_published_bucket(s3_client, evidence_bucket)
    put_raw(
        s3_client,
        evidence_bucket,
        KEYS[ONLY_WEEK_2],
        OTHER_BYTES,
        recorded=digest(OTHER_BYTES) if recorded == "the other bytes' digest" else digest(ONLY_WEEK_2),
    )
    restored = sources(copy, S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client))

    with pytest.raises(RestoredSourcesIncomplete) as refused:
        fetch(restored, SourceSelection(snapshots=(WEEK_2,)))

    assert refused.value.mismatched == 1
    assert refused.value.missing == 0
    assert not blob(copy, ONLY_WEEK_2).exists()
    assert OTHER_BYTES not in every_file(copy).values(), "no file in the copy keeps a mismatched byte"


def test_after_a_mismatch_no_further_fetch_starts(
    tmp_path: Path, s3_client: S3Client, evidence_bucket: str
) -> None:
    copy = a_restored_copy(tmp_path)
    a_published_bucket(s3_client, evidence_bucket)
    for data in KEYS:
        put_raw(s3_client, evidence_bucket, KEYS[data], OTHER_BYTES + data)
    store = Recording(S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client))
    restored = RestoredSources(
        bucket=store.store(),
        local=evidence_at(copy),
        directory=copy,
        free_bytes=lambda _: ROOMY,
    )

    async def one_at_a_time() -> None:
        plan = await restored.plan(SourceSelection(), NO_SUPPRESSION)
        await restored.fetch(plan)

    with pytest.MonkeyPatch.context() as patched:
        patched.setattr(run_state_sources, "_PARALLEL_DOWNLOADS", 1)
        with pytest.raises(RestoredSourcesIncomplete) as refused:
            asyncio.run(one_at_a_time())

    assert refused.value.mismatched == 1
    assert len(store.calls) == 1, store.calls


def test_a_checked_source_is_put_on_the_disk_then_renamed_then_its_directory_put_on_the_disk(
    tmp_path: Path, s3_client: S3Client, evidence_bucket: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    copy = a_restored_copy(tmp_path)
    a_published_bucket(s3_client, evidence_bucket)
    final = blob(copy, CAMP_FILE)
    flushes: list[tuple[str, bool]] = []

    def flushed(path: Path) -> None:
        flushes.append(("the directory" if path == final.parent else "the landing file", final.exists()))

    monkeypatch.setattr(run_state_sources, "_flush", flushed)

    fetch(
        sources(copy, S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client)),
        SourceSelection(caselists=("openev",)),
    )

    assert flushes == [("the landing file", False), ("the directory", True)], "flushed, renamed, flushed"
    assert final.read_bytes() == CAMP_FILE


# ------------------------------------------------------------------------------------------------
# A source missing from the bucket
# ------------------------------------------------------------------------------------------------


def test_a_named_source_missing_from_the_bucket_and_not_suppressed_stops_the_fetch_with_the_count(
    tmp_path: Path, s3_client: S3Client, evidence_bucket: str
) -> None:
    """The planted store: one named source deleted from the bucket, nothing on the suppression list."""
    copy = a_restored_copy(tmp_path)
    a_published_bucket(s3_client, evidence_bucket)
    s3_client.delete_object(Bucket=evidence_bucket, Key=KEYS[ONLY_WEEK_1])
    restored = sources(copy, S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client))

    with pytest.raises(RestoredSourcesIncomplete) as stopped:
        fetch(restored)

    assert (stopped.value.missing, stopped.value.mismatched, stopped.value.fetched) == (1, 0, 3)
    assert "1 named source(s) are not in the bucket and not on the suppression list" in str(stopped.value)
    assert "holds the restored copy and 3 of the 4 sources" in str(stopped.value)
    assert "not a copy to publish from" in str(stopped.value)


def suppressing(data: bytes) -> SuppressionState:
    return SuppressionState.from_entries(
        [
            SuppressionEntry(
                action=SuppressionAction.SUPPRESS,
                sha256=digest(data),
                recorded_at=datetime(2026, 10, 20, tzinfo=UTC),
                reason=ReasonCode.REQUESTED_BY_TEAM,
                request_id="RM-2026-07",
            )
        ]
    )


@pytest.mark.parametrize(
    "in_the_bucket", [False, True], ids=["removed from the bucket", "still in the bucket"]
)
def test_a_source_the_suppression_list_holds_is_skipped_and_counted(
    tmp_path: Path, s3_client: S3Client, evidence_bucket: str, in_the_bucket: bool
) -> None:
    copy = a_restored_copy(tmp_path)
    a_published_bucket(s3_client, evidence_bucket)
    if not in_the_bucket:
        s3_client.delete_object(Bucket=evidence_bucket, Key=KEYS[ONLY_WEEK_1])

    plan, fetched = fetch(
        sources(copy, S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client)),
        state=suppressing(ONLY_WEEK_1),
    )

    assert plan.suppressed == 1
    assert (fetched.fetched, fetched.suppressed) == (3, 1)
    assert not blob(copy, ONLY_WEEK_1).exists(), (
        "the publisher never uploads it, and the copy never fetches it"
    )


def test_a_digest_only_rows_at_a_held_path_name_is_skipped_and_counted(
    tmp_path: Path, s3_client: S3Client, evidence_bucket: str
) -> None:
    copy = a_restored_copy(tmp_path)
    a_published_bucket(s3_client, evidence_bucket)
    s3_client.delete_object(Bucket=evidence_bucket, Key=KEYS[ONLY_WEEK_2])
    hold = PathHoldEntry(
        caselist=CASELIST,
        disclosure=disclosure_digest(CASELIST, "Fictional High/CD/r1.docx"),
        sha256="e" * 64,
        after_snapshot=date(2026, 9, 1),
        recorded_at=datetime(2026, 10, 20, tzinfo=UTC),
        reason=ReasonCode.REQUESTED_BY_TEAM,
        request_id="RM-2026-08",
    )

    _, fetched = fetch(
        sources(copy, S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client)),
        state=SuppressionState.from_entries((), [hold]),
    )

    assert (fetched.fetched, fetched.suppressed) == (3, 1)


class RefusingWhatItCannotList:
    """S3 as the everyday operator meets it: a read of a missing key is refused with `403`, not `404`."""

    def __init__(self, inner: EvidenceObjectStore, *, refused_too: frozenset[str] = frozenset()) -> None:
        self.inner = inner
        self.refused_too = refused_too

    async def get_file(self, key: ObjectKey, destination: Path) -> ObjectInfo:
        if key in self.refused_too:
            raise StoreAccessDenied("GetObject", key)
        try:
            return await self.inner.get_file(key, destination)
        except NotFound:
            raise StoreAccessDenied("GetObject", key) from None

    async def list_objects(self, prefix: str) -> tuple[ObjectInfo, ...]:
        return await self.inner.list_objects(prefix)

    def store(self) -> EvidenceObjectStore:
        return cast("EvidenceObjectStore", self)

    def __getattr__(self, name: str) -> object:
        return getattr(self.inner, name)


def test_a_refused_read_of_a_key_the_bucket_does_not_list_is_a_missing_source(
    tmp_path: Path, s3_client: S3Client, evidence_bucket: str
) -> None:
    copy = a_restored_copy(tmp_path)
    a_published_bucket(s3_client, evidence_bucket)
    s3_client.delete_object(Bucket=evidence_bucket, Key=KEYS[CAMP_FILE])
    store = RefusingWhatItCannotList(S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client))

    with pytest.raises(RestoredSourcesIncomplete) as stopped:
        fetch(sources(copy, store.store()))

    assert stopped.value.missing == 1


def test_a_refused_read_of_a_key_the_bucket_holds_stays_a_refusal(
    tmp_path: Path, s3_client: S3Client, evidence_bucket: str
) -> None:
    copy = a_restored_copy(tmp_path)
    a_published_bucket(s3_client, evidence_bucket)
    store = RefusingWhatItCannotList(
        S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client),
        refused_too=frozenset({KEYS[CAMP_FILE]}),
    )

    with pytest.raises(StoreAccessDenied):
        fetch(sources(copy, store.store()))

    assert not blob(copy, CAMP_FILE).exists()


# ------------------------------------------------------------------------------------------------
# Room, and the directory
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("short_by", [1, 0], ids=["one byte short", "exactly enough"])
def test_a_disk_without_room_for_the_sources_and_the_margin_is_refused_before_any_fetch(
    tmp_path: Path, s3_client: S3Client, evidence_bucket: str, short_by: int
) -> None:
    copy = a_restored_copy(tmp_path)
    a_published_bucket(s3_client, evidence_bucket)
    needed = sum(len(data) for data in KEYS)
    restored = sources(
        copy,
        S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client),
        free=needed + FREE_SPACE_MARGIN_BYTES - short_by,
    )

    if short_by:
        with pytest.raises(TooLittleRoomForSources) as refused:
            fetch(restored)
        assert (refused.value.needed_bytes, refused.value.margin_bytes) == (needed, FREE_SPACE_MARGIN_BYTES)
        assert not (copy / BLOB_DIRECTORY.parent).exists()
    else:
        _, fetched = fetch(restored)
        assert fetched.fetched == 4


def test_the_free_space_asked_is_the_copys_own_filesystems(
    tmp_path: Path, s3_client: S3Client, evidence_bucket: str
) -> None:
    copy = a_restored_copy(tmp_path)
    asked: list[Path] = []
    restored = RestoredSources(
        bucket=S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client),
        local=evidence_at(copy),
        directory=copy,
        free_bytes=lambda directory: asked.append(directory) or ROOMY,
    )

    restored.refuse_too_little_room(SourcesPlan(manifests=0, named=0, to_fetch=(), suppressed=0))

    assert asked == [copy.resolve()]


def test_a_blob_tree_outside_the_copy_is_never_written(
    tmp_path: Path, s3_client: S3Client, evidence_bucket: str
) -> None:
    """The copy's manifests, read through a store whose blobs are another directory's: refused, unwritten."""
    copy = a_restored_copy(tmp_path)
    a_published_bucket(s3_client, evidence_bucket)
    elsewhere = tmp_path / "data"
    elsewhere.mkdir()
    wrong = LocalEvidence(
        objects=evidence_at(copy).objects,
        blobs=evidence_at(elsewhere).blobs,
        object_path_for=evidence_at(copy).object_path_for,
        blob_path_for=evidence_at(elsewhere).blob_path_for,
    )

    with pytest.raises(ValueError, match="outside the copy's directory"):
        fetch(sources(copy, S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client), local=wrong))

    assert every_file(elsewhere) == {}


_EXTRAS: Final = frozenset(
    {"manifests", "named", "fetched", "fetched_bytes", "suppressed", "missing", "mismatched"}
)


def test_what_it_says_is_counts_never_a_key_a_digest_or_a_path(
    tmp_path: Path, s3_client: S3Client, evidence_bucket: str, caplog: pytest.LogCaptureFixture
) -> None:
    copy = a_restored_copy(tmp_path)
    a_published_bucket(s3_client, evidence_bucket)
    s3_client.delete_object(Bucket=evidence_bucket, Key=KEYS[ONLY_WEEK_1])
    caplog.set_level("INFO", logger=run_state_sources.__name__)

    with pytest.raises(RestoredSourcesIncomplete) as stopped:
        fetch(sources(copy, S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client)))

    said: list[str] = [str(stopped.value)]
    for record in caplog.records:
        said.append(record.getMessage())
        said.extend(str(value) for name, value in vars(record).items() if name in _EXTRAS)
    for word in [*(digest(data) for data in KEYS), "raw/", "Fictional", str(tmp_path), CASELIST]:
        assert not any(word in each for each in said), word

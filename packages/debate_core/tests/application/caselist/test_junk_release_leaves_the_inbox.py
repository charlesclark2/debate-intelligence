"""A camp release of junk alone leaves the inbox once it is handled (`v1-e34-t15`).

Since `v1-e34-t08` a camp release holding only junk is imported once and not again: the import
writes its delivery entry, and the entry names no member, because the importer classified none.
Inbox retention (`v1-e34-t11`) still kept it as `not_imported` on every run, since no manifest row
came from its bytes, so it stayed in the inbox for good. A Word `~$` lock file in it stores the name
of whoever had the document open.

Retention now removes a camp download whose delivery entry exists, names no member, and names these
bytes as what the id delivered, with the reason `junk_only`, and names it by its OpenEv id and the
start of its SHA-256 alone. Nothing else loosens: a camp download with no entry, one whose entry
names members, and every weekly and complete archive are judged as before.

Everything is real except the OpenCaselist source, as in `test_inbox_retention.py`, whose
installation this borrows: the importers, the manifests, the store, the publisher and the status
comparison against moto, and the run monitor with its run log, details file and bucket copies, as
`test_summary_names_no_camp_file.py` drives them. Every expected value is written by hand from the
fixtures below (working agreement 6): ids, decisions, byte counts read off the bytes served, and the
retention sentence.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from tests.fixtures.caselist.build_synthetic_archives import build_snapshot_zips

from debate_core.application.caselist_sync import (
    OPENEV_DELIVERIES_FILENAME,
    SelectionDecision,
    StageOutcome,
    SyncStage,
)
from debate_core.application.ports.caselist_source import OpenEvFile, openev_inbox_name
from debate_core.application.sync_runs import SYNC_RUN_DETAILS_FILENAME, SYNC_RUN_DETAILS_KEY_PREFIX
from debate_core.integrations.s3 import S3EvidenceObjectStore

from . import test_inbox_retention as inbox_retention
from .run_record_scenarios import SECOND_RUN
from .test_inbox_retention import (
    CASELIST,
    RELEASE,
    RELEASE_BODY,
    WEEK_1,
    FakeSource,
    Installation,
    kept,
    label,
    outcome,
    removed,
    retention_of,
    sha256_label,
    stage_reason,
    weekly_name,
)
from .test_summary_names_no_camp_file import PROBE, Watched, pasteable, pull

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

LOCK_HOLDER = "Ottoline Probeworth-Vasquez"
"""The invented person a Word lock file in the release names: who had the document open."""

JUNK_ONLY = OpenEvFile(
    openev_id=960,
    path=f"openev/2026/{PROBE} Institute/{PROBE} Empty Release.zip",
    filename=f"{PROBE} Empty Release.zip",
    year=2026,
    tags=("policy",),
)
"""A camp release whose title, folder and so inbox name carry :data:`PROBE`."""


def _word_lock_file(holder: str) -> bytes:
    """What Word leaves as `~$<name>`: the holder's name, once in one byte per letter and once in
    UTF-16, padded, as Word's owner file keeps it. Invented; only its shape is Word's."""
    narrow = bytes([len(holder)]) + holder.encode("ascii").ljust(53, b"\x20")
    wide = len(holder).to_bytes(2, "little") + holder.encode("utf-16-le")
    return (narrow + wide).ljust(162, b"\x00")


def junk_only_zip(*, holder: str = LOCK_HOLDER) -> bytes:
    """A camp release of junk alone, byte-identically every time: a Word lock file naming
    :data:`LOCK_HOLDER`, a `.DS_Store`, and an AppleDouble sidecar."""
    members = (
        (f"{PROBE} Empty Release/.DS_Store", b"\x00\x05\x16\x07 invented macOS metadata"),
        (f"{PROBE} Empty Release/~${PROBE} Harbor Tariffs Aff.docx", _word_lock_file(holder)),
        (f"__MACOSX/{PROBE} Empty Release/._{PROBE} Harbor Tariffs Aff.docx", b"\x00\x05\x16\x07 invented"),
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, body in members:
            info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, body)
    return buffer.getvalue()


JUNK_ONLY_BODY = junk_only_zip()

JUNK_ONLY_SHA256 = hashlib.sha256(JUNK_ONLY_BODY).hexdigest()

JUNK_ONLY_REMOVED = {
    "name": sha256_label(JUNK_ONLY_BODY),
    "kind": "camp_download",
    "bytes": len(JUNK_ONLY_BODY),
    "openev_id": 960,
    "reason": "junk_only",
}
"""How the summary lists the release once retention has removed it, written out by hand."""

JUNK_ONLY_SENTENCE = (
    f"1 file(s) removed, {len(JUNK_ONLY_BODY)} bytes freed: "
    f"1 camp download(s), openev-960 sha256 {JUNK_ONLY_SHA256[:12]} (imported, and it held junk alone)"
)
"""The retention stage's reason on the run that imports the release, written out by hand."""


def test_the_fixture_is_junk_alone_and_its_lock_file_names_the_holder() -> None:
    """Without this the tests below could pass by searching for strings that were never there."""
    with zipfile.ZipFile(io.BytesIO(JUNK_ONLY_BODY)) as archive:
        names = archive.namelist()
        lock = next(name for name in names if "/~$" in name)
        assert LOCK_HOLDER.encode("ascii") in archive.read(lock)
        assert LOCK_HOLDER.encode("utf-16-le") in archive.read(lock)
    assert all(PROBE in name for name in names)
    assert PROBE in openev_inbox_name(JUNK_ONLY)


@pytest.fixture
def installation(tmp_path: Path, s3_client: S3Client, evidence_bucket: str) -> Installation:
    """A data directory and the moto bucket it publishes to, with the fixture weeklies to list."""
    return Installation(
        data_dir=tmp_path / "evidence",
        bucket=S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client),
        archives=build_snapshot_zips(tmp_path / "published"),
    )


@pytest.fixture
def empty_bucket(s3_client: S3Client) -> S3EvidenceObjectStore:
    """A second bucket in the same moto account, holding nothing: a comparison against it confirms nothing."""
    s3_client.create_bucket(Bucket="debate-test-evidence-moto-empty")
    return S3EvidenceObjectStore(bucket="debate-test-evidence-moto-empty", client=s3_client)


@pytest.fixture
def logged(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    caplog.set_level(logging.INFO, logger="debate_core")
    return caplog


async def everything_a_person_reads(
    installation: Installation, watched: Watched, logged: pytest.LogCaptureFixture
) -> dict[str, str]:
    """What `test_summary_names_no_camp_file.pasteable` gathers, and the run's details, here and in
    the bucket."""
    texts = await pasteable(installation, watched, logged)
    record = watched.pulled.record
    if record is not None:
        texts["the run details"] = (installation.data_dir / SYNC_RUN_DETAILS_FILENAME).read_text(
            encoding="utf-8"
        )
        copy = installation.data_dir.parent / "bucket-details-copy.json"
        details_key = SYNC_RUN_DETAILS_KEY_PREFIX + record.object_key.removeprefix("reports/sync-runs/")
        await installation.bucket.get_file(details_key, copy)
        texts["the bucket's copy of the run details"] = copy.read_text(encoding="utf-8")
    return texts


def assert_names_nothing_from_the_release(texts: dict[str, str]) -> None:
    """No camp title, no inbox file name, and nothing read from inside the archive."""
    for secret in (PROBE, LOCK_HOLDER, "Probeworth", openev_inbox_name(JUNK_ONLY), "~$", ".DS_Store"):
        named = sorted(where for where, text in texts.items() if secret.casefold() in text.casefold())
        assert not named, f"{secret!r} reached {named}"


# ------------------------------------------------------------------------------------------------
# ac1: removed after the run that imports it, by id and digest, for its own reason; never again
# ------------------------------------------------------------------------------------------------


async def test_a_junk_only_release_leaves_on_the_run_that_imports_it_and_is_never_fetched_or_imported_again(
    installation: Installation, logged: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The run fetches the release and imports it, which keeps nothing and writes its delivery
    entry with no member. Retention then removes it, as `openev-960 sha256 <prefix>`, with the
    reason `junk_only`, in the summary and in the run record. The next run's own stages show it
    handled: the select stage calls it already imported, the download stage fetches nothing, the
    import stage imports nothing, and the inbox stays empty. It runs a week later, as the next
    scheduled run would, so that the two runs have their own run ids."""
    source = FakeSource(installation.archives, openev=[(JUNK_ONLY, JUNK_ONLY_BODY)])

    first = await pull(installation, source)

    summary = first.pulled.summary
    assert summary.succeeded, summary.stages
    assert source.openev_fetches == [960]
    assert [(one.openev_id, one.decision) for one in summary.openev] == [(960, SelectionDecision.DOWNLOAD)]
    assert summary.files_imported == 0 and summary.files_skipped == 3, "the release is not junk alone"
    assert summary.snapshots_imported == ("openev 2026-policy",), "its release manifest is written"
    assert retention_of(summary)["removed"] == [JUNK_ONLY_REMOVED], (
        "the junk-only release was not removed as junk_only, named by its id and digest"
    )
    assert retention_of(summary)["kept"] == []
    assert retention_of(summary)["bytes_freed"] == len(JUNK_ONLY_BODY)
    assert stage_reason(summary, SyncStage.RETENTION) == JUNK_ONLY_SENTENCE
    assert installation.inbox_names() == set()
    texts = await everything_a_person_reads(installation, first, logged)
    assert first.pulled.record is not None and first.pulled.details is not None
    retention_entries = [one for one in first.pulled.record.stages if one.stage == "retention"]
    assert [(one.outcome, one.reason) for one in retention_entries] == [("completed", JUNK_ONLY_SENTENCE)]
    assert JUNK_ONLY_SENTENCE in texts["the run log"]
    assert JUNK_ONLY_SENTENCE in texts["the bucket's copy of the run record"]
    for where, text in texts.items():
        assert "not_imported" not in text and "not imported" not in text, f"{where} calls it not imported"
    assert first.pulled.details.stage("retention") is None, "a completed retention stage has no details"
    assert_names_nothing_from_the_release(texts)

    monkeypatch.setattr(inbox_retention, "RUN_CLOCK", SECOND_RUN)
    again = await pull(installation, source)

    summary = again.pulled.summary
    assert summary.succeeded, summary.stages
    assert source.openev_fetches == [960], "the junk-only release was downloaded again"
    assert [(one.openev_id, one.decision) for one in summary.openev] == [
        (960, SelectionDecision.ALREADY_IMPORTED)
    ]
    assert summary.openev_downloaded == 0
    assert summary.files_imported == 0 and summary.files_skipped == 0, "the junk-only release was read again"
    assert summary.snapshots_imported == (), "the junk-only release was imported again"
    assert summary.nothing_new
    assert outcome(summary, SyncStage.RETENTION) is StageOutcome.SKIPPED
    assert stage_reason(summary, SyncStage.RETENTION) == "the inbox holds nothing"
    assert installation.inbox_names() == set()
    assert_names_nothing_from_the_release(await everything_a_person_reads(installation, again, logged))


# ------------------------------------------------------------------------------------------------
# ac2: a camp download with no entry, one whose entry names members, and a weekly, as before
# ------------------------------------------------------------------------------------------------


async def test_a_junk_only_release_whose_import_failed_has_no_entry_and_stays_until_an_import_writes_one(
    installation: Installation,
) -> None:
    """An import that fails writes no delivery entry, so the release stays as `not_imported`, as
    any camp download with no entry does. The next run imports it from the inbox without fetching
    it, which writes the entry, and only then does it leave."""
    source = FakeSource(installation.archives, openev=[(JUNK_ONLY, JUNK_ONLY_BODY)])

    failed = await installation.sync(source, openev_fails=True).run([CASELIST])

    assert outcome(failed, SyncStage.IMPORT) is StageOutcome.FAILED
    assert not (installation.data_dir / OPENEV_DELIVERIES_FILENAME).exists()
    assert kept(failed) == {sha256_label(JUNK_ONLY_BODY): "not_imported"}
    assert removed(failed) == []
    assert installation.inbox_names() == {openev_inbox_name(JUNK_ONLY)}

    retried = await installation.sync(source).run([CASELIST])

    assert source.openev_fetches == [960], "the waiting copy was fetched again"
    assert retried.files_skipped == 3
    assert retention_of(retried)["removed"] == [JUNK_ONLY_REMOVED]
    assert installation.inbox_names() == set()


async def test_a_junk_only_release_whose_entry_is_gone_stays_when_no_run_imports_it_again(
    installation: Installation,
) -> None:
    """Imported by a run that had no bucket to confirm against, so its copy is still here; then the
    delivery record is lost, and upstream stops listing the release, so no run imports it again.
    With no entry it stays as `not_imported`, exactly as before this task."""
    source = FakeSource(installation.archives, openev=[(JUNK_ONLY, JUNK_ONLY_BODY)])
    await installation.sync(source, bucket=False).run([CASELIST])
    (installation.data_dir / OPENEV_DELIVERIES_FILENAME).unlink()
    source.openev = []

    summary = await installation.sync(source).run([CASELIST])

    assert kept(summary) == {sha256_label(JUNK_ONLY_BODY): "not_imported"}
    assert removed(summary) == []
    assert installation.inbox_names() == {openev_inbox_name(JUNK_ONLY)}


async def test_with_nothing_confirmed_in_the_bucket_only_the_junk_only_release_leaves(
    installation: Installation, empty_bucket: S3EvidenceObjectStore
) -> None:
    """One run fetches a weekly, a camp release whose entry names its two camp files, and the
    junk-only release, and imports all three; the bucket it compares with holds nothing. The weekly
    and the camp release stay as `not_confirmed`, as before. The junk-only release has no snapshot
    to confirm, and goes."""
    source = FakeSource(
        installation.archives, weeks=[WEEK_1], openev=[(RELEASE, RELEASE_BODY), (JUNK_ONLY, JUNK_ONLY_BODY)]
    )

    summary = await installation.sync(source, compare_with=empty_bucket).run([CASELIST])

    assert summary.snapshots_imported == (label(WEEK_1), "openev 2026-policy")
    assert kept(summary) == {label(WEEK_1): "not_confirmed", sha256_label(RELEASE_BODY): "not_confirmed"}
    assert retention_of(summary)["removed"] == [JUNK_ONLY_REMOVED]
    assert installation.inbox_names() == {weekly_name(WEEK_1), openev_inbox_name(RELEASE)}


async def test_a_copy_whose_bytes_are_not_the_ones_the_entry_names_stays(installation: Installation) -> None:
    """The release is imported and leaves. Then a file under its inbox name turns up holding other
    bytes (put there by hand, say). Its id's entry names no member, but it names the bytes the id
    delivered, and these are not they: they were never imported, so they stay as `not_imported`."""
    source = FakeSource(installation.archives, openev=[(JUNK_ONLY, JUNK_ONLY_BODY)])
    first = await installation.sync(source).run([CASELIST])
    assert retention_of(first)["removed"] == [JUNK_ONLY_REMOVED]
    other = junk_only_zip(holder="Another Invented Holder")
    (installation.inbox / openev_inbox_name(JUNK_ONLY)).write_bytes(other)

    summary = await installation.sync(source).run([CASELIST])

    assert source.openev_fetches == [960]
    assert summary.snapshots_imported == ()
    assert kept(summary) == {sha256_label(other): "not_imported"}
    assert removed(summary) == []
    assert installation.inbox_names() == {openev_inbox_name(JUNK_ONLY)}


async def test_a_dry_run_lists_a_junk_only_release_an_earlier_run_left_and_removes_nothing(
    installation: Installation,
) -> None:
    """The backlog: a run with no bucket imported the release and left its copy, as every build
    before this task did. A dry run lists it under `would_remove`, with its reason, and changes
    nothing; the real run after it removes it, and fetches and imports nothing."""
    source = FakeSource(installation.archives, openev=[(JUNK_ONLY, JUNK_ONLY_BODY)])
    await installation.sync(source, bucket=False).run([CASELIST])
    before = installation.inbox_state()

    dry = await installation.sync(source).run([CASELIST], dry_run=True)

    assert installation.inbox_state() == before, "the dry run changed the inbox"
    assert retention_of(dry)["would_remove"] == [JUNK_ONLY_REMOVED]
    assert retention_of(dry)["bytes_would_free"] == len(JUNK_ONLY_BODY)
    assert retention_of(dry)["kept"] == []

    summary = await installation.sync(source).run([CASELIST])

    assert source.openev_fetches == [960]
    assert summary.snapshots_imported == () and summary.files_skipped == 0
    assert retention_of(summary)["removed"] == [JUNK_ONLY_REMOVED]
    assert json.dumps(retention_of(summary)).count("openev_id") == 1
    assert installation.inbox_names() == set()

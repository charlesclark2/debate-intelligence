"""Retiring superseded parsed-store version directories, on this machine and in a bucket (`v1-e31-t16`).

The rule is written for readers in `docs/data/parsed-card-store.md` ("Retention"); every standing
asserted below is written by hand from it, not read back from the code. The stores are made-up:
a temporary data directory, and moto's bucket. Version names are parser-version labels only, and
the caselist is the fictional `testcl26`.

What each part holds the command to:

* ac1: the dry run lists every directory with its standing and counts, and changes nothing.
* ac2: with the dry run's confirmation, a superseded directory is deleted on this machine and its
  objects tagged, never deleted, in the bucket; the current directory, a directory newer than this
  build, and a directory with no successor in that place are refused.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import pytest

from debate_core.application.caselist.version_retention import (
    RetentionRefused,
    Standing,
    VersionDirectoryRetention,
    standings,
)
from debate_core.application.ports.version_directories import (
    RESTORED_TAG_VALUE,
    RETIREMENT_TAG_KEY,
    RETIREMENT_TAG_VALUE,
)
from debate_core.integrations.local.version_directories import LocalVersionDirectories
from debate_core.integrations.s3.version_directories import S3VersionDirectories

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

CASELIST: Final = "testcl26"
OTHER_CASELIST: Final = "testpf26"
FIRST: Final = "2026.09.20-docx-1"
SECOND: Final = "2026.10.10-docx-2"
SECOND_REPARSED: Final = "2026.10.10-docx-2_reparse-2"
BUILD: Final = "2026.10.12-docx-3"
"""The parser version of the build under test: its newest directory is the current one."""
NEWER: Final = "2099.01.01-docx-99"

#: Each directory's files, relative to it, and their bytes. Written by hand.
FILES: Final = {
    "sha256/ab/cd/abcd01.jsonl": b'{"record":"source"}\n',
    "sha256/ef/01/ef0102.jsonl": b'{"record":"source"}\n{"record":"document"}\n',
    "index.jsonl": b"{}\n",
}
FILE_BYTES: Final = sum(len(content) for content in FILES.values())


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


# ------------------------------------------------------------------------------------------------
# The rule
# ------------------------------------------------------------------------------------------------


def test_each_directory_is_judged_against_this_builds_parser_version() -> None:
    judged = standings([FIRST, SECOND, SECOND_REPARSED, BUILD, NEWER], BUILD)

    assert judged == {
        FIRST: Standing.SUPERSEDED,
        SECOND: Standing.SUPERSEDED,
        SECOND_REPARSED: Standing.SUPERSEDED,
        BUILD: Standing.CURRENT,
        NEWER: Standing.NEWER_THAN_THIS_BUILD,
    }


def test_the_newest_generation_of_this_builds_parser_version_is_current_and_the_one_before_superseded() -> (
    None
):
    judged = standings([f"{BUILD}_reparse-2", BUILD, f"{BUILD}_reparse-10"], BUILD)

    assert judged == {
        BUILD: Standing.SUPERSEDED,
        f"{BUILD}_reparse-2": Standing.SUPERSEDED,
        f"{BUILD}_reparse-10": Standing.CURRENT,
    }


def test_nothing_is_superseded_in_a_place_with_no_directory_of_this_builds_parser_version() -> None:
    judged = standings([FIRST, SECOND, NEWER], BUILD)

    assert judged == {
        FIRST: Standing.NOT_YET_SUPERSEDED,
        SECOND: Standing.NOT_YET_SUPERSEDED,
        NEWER: Standing.NEWER_THAN_THIS_BUILD,
    }


# ------------------------------------------------------------------------------------------------
# This machine: retiring deletes
# ------------------------------------------------------------------------------------------------


def write_directories(data_dir: Path, caselist: str, *versions: str) -> None:
    for version in versions:
        for name, content in FILES.items():
            path = data_dir / "parsed" / caselist / version / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)


def tree(data_dir: Path) -> dict[str, bytes]:
    root = data_dir / "parsed"
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    built = tmp_path / "data"
    write_directories(built, CASELIST, FIRST, SECOND, BUILD)
    write_directories(built, OTHER_CASELIST, SECOND, BUILD)
    return built


def local_retention(data_dir: Path, parser_version: str = BUILD) -> VersionDirectoryRetention:
    return VersionDirectoryRetention(LocalVersionDirectories(data_dir), parser_version=parser_version)


@pytest.mark.anyio
async def test_the_dry_run_lists_every_directory_with_its_standing_and_counts_and_changes_nothing(
    data_dir: Path,
) -> None:
    before = tree(data_dir)

    plan = await local_retention(data_dir).plan()

    assert [(row.caselist, row.version, row.standing) for row in plan.rows] == [
        (CASELIST, FIRST, Standing.SUPERSEDED),
        (CASELIST, SECOND, Standing.SUPERSEDED),
        (CASELIST, BUILD, Standing.CURRENT),
        (OTHER_CASELIST, SECOND, Standing.SUPERSEDED),
        (OTHER_CASELIST, BUILD, Standing.CURRENT),
    ]
    assert {(row.contents.objects, row.contents.bytes, row.contents.tagged) for row in plan.rows} == {
        (len(FILES), FILE_BYTES, None)
    }
    assert [(row.caselist, row.version) for row in plan.selected] == [
        (CASELIST, FIRST),
        (CASELIST, SECOND),
        (OTHER_CASELIST, SECOND),
    ]
    assert len(plan.confirmation) == 12
    assert tree(data_dir) == before


@pytest.mark.anyio
async def test_a_named_superseded_directory_is_deleted_in_every_caselist_and_nothing_else_changes(
    data_dir: Path,
) -> None:
    before = tree(data_dir)
    retention = local_retention(data_dir)
    plan = await retention.plan(versions=[SECOND])

    result = await retention.execute(plan, confirmation=plan.confirmation)

    assert [(row.caselist, row.version, count) for row, count in result.acted_on] == [
        (CASELIST, SECOND, len(FILES)),
        (OTHER_CASELIST, SECOND, len(FILES)),
    ]
    assert tree(data_dir) == {key: value for key, value in before.items() if f"/{SECOND}/" not in key}
    assert not (data_dir / "parsed" / CASELIST / SECOND).exists()
    assert (data_dir / "parsed" / CASELIST).is_dir()


@pytest.mark.anyio
async def test_the_current_directory_is_refused_and_nothing_is_deleted(data_dir: Path) -> None:
    before = tree(data_dir)
    retention = local_retention(data_dir)
    plan = await retention.plan(versions=[BUILD])

    refusal = plan.refusal(plan.confirmation)
    with pytest.raises(RetentionRefused):
        await retention.execute(plan, confirmation=plan.confirmation)

    assert refusal is not None
    assert (refusal.code, refusal.caselist, refusal.version) == ("CURRENT_VERSION_DIRECTORY", CASELIST, BUILD)
    assert tree(data_dir) == before


@pytest.mark.anyio
async def test_a_directory_newer_than_this_build_is_refused_and_nothing_is_deleted(data_dir: Path) -> None:
    """An older build run after a newer one has written its directory: the older build's own is not
    current any more, and the newer one is not its to judge."""
    write_directories(data_dir, CASELIST, NEWER)
    before = tree(data_dir)
    retention = local_retention(data_dir)
    plan = await retention.plan(caselists=[CASELIST], versions=[NEWER])

    refusal = plan.refusal(plan.confirmation)
    with pytest.raises(RetentionRefused):
        await retention.execute(plan, confirmation=plan.confirmation)

    assert refusal is not None
    assert (refusal.code, refusal.version) == ("NEWER_THAN_THIS_BUILD", NEWER)
    assert tree(data_dir) == before


@pytest.mark.anyio
async def test_one_refused_directory_refuses_the_whole_run(data_dir: Path) -> None:
    before = tree(data_dir)
    retention = local_retention(data_dir)
    plan = await retention.plan(versions=[SECOND, BUILD])

    with pytest.raises(RetentionRefused):
        await retention.execute(plan, confirmation=plan.confirmation)

    assert tree(data_dir) == before


@pytest.mark.anyio
async def test_a_place_with_no_directory_of_this_build_has_nothing_superseded_to_retire(
    data_dir: Path,
) -> None:
    before = tree(data_dir)
    retention = local_retention(data_dir, parser_version="2026.10.20-docx-4")
    plan = await retention.plan(versions=[SECOND])

    refusal = plan.refusal(plan.confirmation)

    assert plan.selected == ()
    assert refusal is not None
    assert refusal.code == "NOT_YET_SUPERSEDED"
    assert tree(data_dir) == before


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("versions", "confirmation", "code"),
    [
        ((), "plan", "VERSION_NOT_NAMED"),
        ((SECOND,), None, "CONFIRMATION_MISMATCH"),
        ((SECOND,), "0123456789ab", "CONFIRMATION_MISMATCH"),
        (("2026.01.01-docx-0",), "plan", "NO_SUCH_VERSION_DIRECTORY"),
    ],
)
async def test_without_a_named_directory_and_the_dry_runs_confirmation_nothing_is_deleted(
    data_dir: Path, versions: tuple[str, ...], confirmation: str | None, code: str
) -> None:
    before = tree(data_dir)
    retention = local_retention(data_dir)
    plan = await retention.plan(versions=versions)
    given = plan.confirmation if confirmation == "plan" else confirmation

    with pytest.raises(RetentionRefused) as refused:
        await retention.execute(plan, confirmation=given)

    assert refused.value.refusal.code == code
    assert tree(data_dir) == before


@pytest.mark.anyio
async def test_a_directory_that_changed_since_the_dry_run_is_refused(data_dir: Path) -> None:
    retention = local_retention(data_dir)
    shown = (await retention.plan(versions=[FIRST])).confirmation
    (data_dir / "parsed" / CASELIST / FIRST / "late.jsonl").write_bytes(b"{}\n")
    before = tree(data_dir)

    plan = await retention.plan(versions=[FIRST])
    with pytest.raises(RetentionRefused) as refused:
        await retention.execute(plan, confirmation=shown)

    assert refused.value.refusal.code == "CONFIRMATION_MISMATCH"
    assert tree(data_dir) == before


@pytest.mark.anyio
async def test_nothing_on_this_machine_can_be_restored(data_dir: Path) -> None:
    plan = await local_retention(data_dir).plan(versions=[FIRST], restore=True)

    refusal = plan.refusal(plan.confirmation)

    assert refusal is not None
    assert refusal.code == "NOTHING_TO_RESTORE_HERE"


@pytest.mark.anyio
async def test_the_adapter_never_deletes_the_newest_directory_a_caselist_has(data_dir: Path) -> None:
    """A second guard, under the service's: whatever it is asked, this machine keeps the newest."""
    before = tree(data_dir)

    with pytest.raises(ValueError, match="newest"):
        await LocalVersionDirectories(data_dir).retire(CASELIST, BUILD)
    with pytest.raises(ValueError, match="not a caselist or version directory name"):
        await LocalVersionDirectories(data_dir).retire(CASELIST, "..")

    assert tree(data_dir) == before


# ------------------------------------------------------------------------------------------------
# The bucket: retiring tags, and deletes nothing
# ------------------------------------------------------------------------------------------------


@pytest.fixture
def bucket(s3_client: S3Client, evidence_bucket: str) -> Iterator[str]:
    """`parsed/` as a publish leaves it, plus one object outside `parsed/` that nothing may touch."""
    for caselist, versions in ((CASELIST, (FIRST, SECOND, BUILD)), (OTHER_CASELIST, (SECOND, BUILD))):
        for version in versions:
            for name, content in FILES.items():
                s3_client.put_object(
                    Bucket=evidence_bucket, Key=f"parsed/{caselist}/{version}/{name}", Body=content
                )
    s3_client.put_object(Bucket=evidence_bucket, Key=f"manifests/{CASELIST}/2026-09-15.jsonl", Body=b"{}\n")
    yield evidence_bucket


def bucket_retention(
    s3_client: S3Client, bucket: str, parser_version: str = BUILD
) -> VersionDirectoryRetention:
    return VersionDirectoryRetention(
        S3VersionDirectories(bucket=bucket, client=s3_client, threads=4), parser_version=parser_version
    )


def tags_by_key(s3_client: S3Client, bucket: str) -> dict[str, dict[str, str]]:
    keys = [item.get("Key", "") for item in s3_client.list_objects_v2(Bucket=bucket).get("Contents", [])]
    return {
        key: {
            tag["Key"]: tag["Value"] for tag in s3_client.get_object_tagging(Bucket=bucket, Key=key)["TagSet"]
        }
        for key in keys
    }


def every_version(s3_client: S3Client, bucket: str) -> list[tuple[str, str, bool]]:
    listed = s3_client.list_object_versions(Bucket=bucket)
    return sorted(
        [(item.get("Key", ""), item.get("VersionId", ""), False) for item in listed.get("Versions", [])]
        + [(item.get("Key", ""), item.get("VersionId", ""), True) for item in listed.get("DeleteMarkers", [])]
    )


@pytest.fixture
def operations(s3_client: S3Client) -> list[str]:
    """Every S3 operation the client sends, by name, in order."""
    sent: list[str] = []

    def record(model: Any, **_: Any) -> None:
        sent.append(model.name)

    s3_client.meta.events.register("before-call.s3", record)
    return sent


@pytest.mark.anyio
async def test_the_bucket_dry_run_counts_tags_only_where_it_might_retire(
    s3_client: S3Client, bucket: str
) -> None:
    plan = await bucket_retention(s3_client, bucket).plan(caselists=[CASELIST])

    assert [(row.version, row.standing, row.contents.objects, row.contents.tagged) for row in plan.rows] == [
        (FIRST, Standing.SUPERSEDED, len(FILES), 0),
        (SECOND, Standing.SUPERSEDED, len(FILES), 0),
        (BUILD, Standing.CURRENT, len(FILES), None),
    ]
    assert plan.location == f"s3://{bucket}"


@pytest.mark.anyio
async def test_retiring_in_the_bucket_tags_every_object_of_the_directory_and_deletes_nothing(
    s3_client: S3Client, bucket: str, operations: list[str]
) -> None:
    key = f"parsed/{CASELIST}/{SECOND}/index.jsonl"
    s3_client.put_object_tagging(
        Bucket=bucket, Key=key, Tagging={"TagSet": [{"Key": "kept", "Value": "yes"}]}
    )
    versions_before = every_version(s3_client, bucket)
    retention = bucket_retention(s3_client, bucket)
    plan = await retention.plan(versions=[SECOND])
    operations.clear()

    result = await retention.execute(plan, confirmation=plan.confirmation)
    sent = set(operations)

    retired = {RETIREMENT_TAG_KEY: RETIREMENT_TAG_VALUE}
    expected = {
        stored: ({**retired, "kept": "yes"} if stored == key else retired) if f"/{SECOND}/" in stored else {}
        for stored in tags_by_key(s3_client, bucket)
    }
    assert tags_by_key(s3_client, bucket) == expected
    assert [count for _, count in result.acted_on] == [len(FILES), len(FILES)]
    assert every_version(s3_client, bucket) == versions_before
    assert sent == {"ListObjectsV2", "GetObjectTagging", "PutObjectTagging"}


@pytest.mark.anyio
async def test_retiring_twice_tags_nothing_the_second_time(s3_client: S3Client, bucket: str) -> None:
    retention = bucket_retention(s3_client, bucket)
    first = await retention.plan(caselists=[CASELIST], versions=[FIRST])
    await retention.execute(first, confirmation=first.confirmation)

    again = await retention.plan(caselists=[CASELIST], versions=[FIRST])
    result = await retention.execute(again, confirmation=again.confirmation)

    assert [row.contents.tagged for row in again.selected] == [len(FILES)]
    assert [count for _, count in result.acted_on] == [0]


@pytest.mark.anyio
async def test_the_bucket_refuses_its_current_directory_and_one_newer_than_this_build(
    s3_client: S3Client, bucket: str
) -> None:
    for name, content in FILES.items():
        s3_client.put_object(Bucket=bucket, Key=f"parsed/{CASELIST}/{NEWER}/{name}", Body=content)
    before = tags_by_key(s3_client, bucket)
    retention = bucket_retention(s3_client, bucket)

    for version, code in ((BUILD, "CURRENT_VERSION_DIRECTORY"), (NEWER, "NEWER_THAN_THIS_BUILD")):
        plan = await retention.plan(caselists=[CASELIST], versions=[version])
        with pytest.raises(RetentionRefused) as refused:
            await retention.execute(plan, confirmation=plan.confirmation)
        assert refused.value.refusal.code == code

    assert tags_by_key(s3_client, bucket) == before


@pytest.mark.anyio
async def test_a_bucket_the_current_directory_was_not_published_to_keeps_what_it_has(
    s3_client: S3Client, bucket: str
) -> None:
    """The new directory is on this machine but not in the bucket yet: nothing there is superseded."""
    plan = await bucket_retention(s3_client, bucket, parser_version="2026.10.20-docx-4").plan(
        versions=[SECOND]
    )

    refusal = plan.refusal(plan.confirmation)

    assert refusal is not None
    assert refusal.code == "NOT_YET_SUPERSEDED"


@pytest.mark.anyio
async def test_restoring_sets_the_retirement_tag_to_restored_and_keeps_every_other_tag(
    s3_client: S3Client, bucket: str
) -> None:
    key = f"parsed/{CASELIST}/{FIRST}/index.jsonl"
    s3_client.put_object_tagging(
        Bucket=bucket, Key=key, Tagging={"TagSet": [{"Key": "kept", "Value": "yes"}]}
    )
    before = tags_by_key(s3_client, bucket)
    retention = bucket_retention(s3_client, bucket)
    retire = await retention.plan(caselists=[CASELIST], versions=[FIRST])
    await retention.execute(retire, confirmation=retire.confirmation)

    restore = await retention.plan(caselists=[CASELIST], versions=[FIRST], restore=True)
    result = await retention.execute(restore, confirmation=restore.confirmation)

    restored = {RETIREMENT_TAG_KEY: RESTORED_TAG_VALUE}
    assert [count for _, count in result.acted_on] == [len(FILES)]
    assert tags_by_key(s3_client, bucket) == {
        stored: ({**tags, **restored} if f"/{FIRST}/" in stored else tags) for stored, tags in before.items()
    }

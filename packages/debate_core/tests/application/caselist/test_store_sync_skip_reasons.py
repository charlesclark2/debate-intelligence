"""`store sync`'s skip breakdown, with the real publisher (`v1-e29-t11-store-sync-skip-reasons`).

A push skips a manifest `caselist publish` withholds and a blob only a held row names (`v1-e30-t25`,
`v1-e30-t22`), and reported only a count. :attr:`SyncPlan.skipped_reasons` groups the skips by kind,
and for a withheld manifest carries the publisher's own message and the requests it names: the
removal the operator runs again. Here the publisher is the real one,
:func:`~debate_core.application.caselist.publish_service.withheld_manifest_reason`, over `v1-e30-t21`'s
store and removal, and its message is compared with what a real publish of the same snapshot says.

Every test runs offline: moto for the bucket, a temporary data directory, and a temporary `HOME`.
"""

from __future__ import annotations

import functools
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from tests.fixtures.caselist.build_revised_path_archives import CASELIST, REVISED_PATH

from debate_core.application.caselist.evidence_listing import held_back_digests
from debate_core.application.caselist.publish_service import withheld_manifest_reason
from debate_core.application.caselist.suppression import load_suppression_state
from debate_core.application.evidence_sync import (
    EvidenceSyncService,
    ManifestWithholding,
    SkipKind,
    SkippedReason,
    SyncDirection,
    SyncKeyspace,
)
from debate_core.application.ports.suppression import SuppressionList
from debate_core.integrations.local import FsEvidenceObjectStore

from .conftest import REQUEST, RemovalWorld
from .test_held_path_loose_ends import HELD_WEEK_MANIFEST
from .test_removal_covers_later_uploads import NAMES, revised_path_world
from .test_store_sync_withholds_manifests import (
    ROW_KINDS,
    Withheld,
    a_held_row,
    off_the_bucket,
    the_publishers_message,
)

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

#: The requests each row kind's message names, written from `_withheld_for_rows`: a row the list
#: stops is named by its digest alone, and a row at a held path by its digest and the request.
REQUESTS_NAMED: dict[str, tuple[str, ...]] = {
    "a suppressed file": (),
    "a withdrawn disclosure": (),
    "a withdrawn camp path": (),
    "a held row": (REQUEST,),
    "a held row in a complete archive": (REQUEST,),
    "a held link": (REQUEST,),
    "junk at the held path": (REQUEST,),
}


@pytest.fixture(autouse=True)
def temporary_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """A `HOME` of this test's own, so nothing here can read or write the operator's."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


@pytest.fixture
async def world(tmp_path: Path, s3_client: S3Client, evidence_bucket: str) -> RemovalWorld:
    return await revised_path_world(tmp_path, s3_client, evidence_bucket)


def store_sync(world: RemovalWorld, suppression: SuppressionList) -> EvidenceSyncService:
    """`store sync --blob-prefix raw/caselist/testcl26`, built as the composition root builds it."""
    return EvidenceSyncService(
        suppression=suppression,
        keyspaces=(
            SyncKeyspace(name="objects", local=world.local.objects, remote=world.bucket),
            SyncKeyspace(
                name="blobs",
                local=world.local.blobs,
                remote=world.bucket,
                remote_prefix=f"raw/caselist/{CASELIST}",
                content_addressed=True,
            ),
        ),
        held_back=functools.partial(held_back_digests, world.local),
        withheld_manifests=functools.partial(withheld_manifest_reason, world.local),
    )


async def the_answer(
    world: RemovalWorld, key: str, suppression: SuppressionList
) -> ManifestWithholding | None:
    """What the publisher answers a push about the local manifest at `key`."""
    (info,) = [one for one in await world.local.objects.list_objects(key) if one.key == key]
    return await withheld_manifest_reason(world.local, info, await load_suppression_state(suppression))


# ------------------------------------------------------------------------------------------------
# The push
# ------------------------------------------------------------------------------------------------


async def test_a_push_reports_the_withheld_manifest_and_the_held_only_blob_by_kind(
    world: RemovalWorld, tmp_path: Path
) -> None:
    """After the removal an older build imports 2026-10-08, with an upload at the held path that no
    other row names. A push leaves out the week's manifest and the upload's bytes, and says why."""
    made = await a_held_row(world, tmp_path)

    plan = await store_sync(world, made.suppression).plan(direction=SyncDirection.PUSH)
    breakdown = {reason.kind: reason for reason in plan.skipped_reasons}
    message = await the_publishers_message(world, made)

    assert message is not None
    assert breakdown[SkipKind.WITHHELD_MANIFEST] == SkippedReason(
        SkipKind.WITHHELD_MANIFEST,
        1,
        ("manifests/te",),
        messages=(message,),
        request_ids=(REQUEST,),
    )
    assert breakdown[SkipKind.HELD_ONLY_BLOB] == SkippedReason(SkipKind.HELD_ONLY_BLOB, 1, ("raw/caselist",))
    assert sum(reason.count for reason in plan.skipped_reasons) == plan.counts["skipped"]
    reported = json.dumps([reason.as_json() for reason in plan.skipped_reasons])
    assert not [word for word in (*NAMES, REVISED_PATH, ".docx", "__MACOSX") if word in reported]


async def test_a_push_reports_a_manifest_the_publisher_cannot_read_as_its_own_kind(
    world: RemovalWorld,
) -> None:
    unreadable = f"manifests/{CASELIST}/2026-10-13.jsonl"
    FsEvidenceObjectStore(world.data_dir).path_for(unreadable).write_bytes(b"not a manifest row\n")

    plan = await store_sync(world, world.suppression()).plan(
        prefix="manifests/", direction=SyncDirection.PUSH
    )

    assert {reason.kind: reason for reason in plan.skipped_reasons}[
        SkipKind.UNREADABLE_MANIFEST
    ] == SkippedReason(
        SkipKind.UNREADABLE_MANIFEST,
        1,
        ("manifests/te",),
        messages=(f"{unreadable} line 1 is not a usable manifest row: not JSON",),
    )


# ------------------------------------------------------------------------------------------------
# The publisher's answer
# ------------------------------------------------------------------------------------------------


@pytest.fixture(params=list(ROW_KINDS))
async def withheld(
    request: pytest.FixtureRequest, world: RemovalWorld, tmp_path: Path
) -> tuple[str, Withheld]:
    """One manifest of the row kind on this machine and not in the bucket, and the kind's name."""
    made = await ROW_KINDS[request.param](world, tmp_path)
    off_the_bucket(world, made.key)
    return request.param, made


async def test_the_publishers_answer_names_exactly_the_requests_its_message_names(
    world: RemovalWorld, withheld: tuple[str, Withheld]
) -> None:
    kind, made = withheld

    answer = await the_answer(world, made.key, made.suppression)

    assert answer is not None
    assert (answer.message, answer.unreadable, answer.request_ids) == (
        await the_publishers_message(world, made),
        False,
        REQUESTS_NAMED[kind],
    )
    assert set(re.findall(r"RM-\d{4}-\d{2,4}", answer.message)) == set(answer.request_ids)


async def test_the_publishers_answer_for_a_manifest_it_cannot_read_is_its_refusal(
    world: RemovalWorld,
) -> None:
    unreadable = f"manifests/{CASELIST}/2026-10-13.jsonl"
    FsEvidenceObjectStore(world.data_dir).path_for(unreadable).write_bytes(b"not a manifest row\n")

    assert await the_answer(world, unreadable, world.suppression()) == ManifestWithholding(
        f"{unreadable} line 1 is not a usable manifest row: not JSON", unreadable=True
    )


async def test_the_publisher_has_no_answer_for_a_manifest_it_publishes(
    world: RemovalWorld, tmp_path: Path
) -> None:
    await a_held_row(world, tmp_path)

    assert await the_answer(world, f"manifests/{CASELIST}/2026-09-22.jsonl", world.suppression()) is None
    assert await the_answer(world, HELD_WEEK_MANIFEST, world.suppression()) is not None

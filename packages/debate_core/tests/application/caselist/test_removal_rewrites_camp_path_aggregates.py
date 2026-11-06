"""A camp path's withdrawal rewrites OpenEv's aggregates by release and camp path (`v1-e30-t33`, ruling Q2).

The world is `v1-e30-t14`'s (`test_removal_withdraws_one_camp_path.py`): removing 512's bytes
(`estuary`) takes 640 (`revised`) down as a later upload at its camp path in `2026-policy`, and 800
holds the same bytes in `2027-policy`, so `revised` is withdrawn from `2026-policy` only. Its camp-file
record there goes, and no other row of that release holds it: the release is left with no live camp path
of it. The parsed store is planted for OpenEv, here and in the bucket, from the store's own models:

| Source | Release | Camp path | Cards |
|---|---|---|---|
| `estuary` | 2026-policy | its 512 row | 2 |
| `revised` | 2026-policy | its 640 row | 2 |
| `revised` | 2027-policy | its 800 row | 2 |

So the occurrence table has 6 rows and `camp_paths.jsonl` 3 lines; the removal leaves 2 rows, both
`revised`'s in `2027-policy`, and 1 line, re-stamped with the rewritten table's digest, and the index
keeps `revised`'s entry, whose copy OpenEv keeps.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Final

import pytest

from debate_core.application.caselist.removal_plan import AggregateAction, Disposition, Side
from debate_core.application.ports.parsed_store import (
    OccurrenceRecord,
    SourceEntry,
    SourceOutcome,
    source_object_key,
)
from debate_core.application.ports.suppression import camp_path_disclosure
from debate_core.domain.card_occurrence import ClusterMembership
from debate_core.domain.caselist import SourceFormat
from debate_core.domain.debate_files import CardCompleteness
from debate_core.integrations.local.parsed_store import LocalParsedStore

from .conftest import RemovalWorld
from .test_removal_covers_later_camp_uploads import NEW_ROW, RELEASE, RELEASE_KEY, REVISED_SHA256
from .test_removal_withdraws_one_camp_path import (
    NEXT_RELEASE_KEY,
    NEXT_YEAR_ROW,
    another_release_holds_the_later_upload,
    plan_removal,
    rows_of,
)
from .test_sync_skips_suppressed_downloads import ESTUARY_SHA256

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

VERSION: Final = "2026.10.27-docx-7"
NEXT_RELEASE: Final = "2027-policy"
TABLE: Final = f"openev/{VERSION}/occurrences.jsonl"
BESIDE: Final = f"openev/{VERSION}/camp_paths.jsonl"


@pytest.fixture
def world(tmp_path: Path, s3_client: S3Client, evidence_bucket: str) -> RemovalWorld:
    return RemovalWorld(data_dir=tmp_path / "evidence", bucket_name=evidence_bucket, client=s3_client)


def estuary_row(world: RemovalWorld) -> str:
    (local, _) = rows_of(world, RELEASE_KEY)
    (path,) = [path for path, sha256 in local.items() if sha256 == ESTUARY_SHA256]
    return path


def rows(release: str, sha256: str, camp_path: str) -> list[OccurrenceRecord]:
    return [
        OccurrenceRecord(
            caselist="openev",
            snapshot=release,
            last_snapshot=release,
            source_sha256=sha256,
            parser_version=VERSION,
            profile_version="2026.09.20-verbatim-1",
            fingerprint_version="card-fingerprint-v4",
            disclosure=None,
            camp="Tamarack",
            first_element_index=card * 3,
            last_element_index=card * 3 + 2,
            exact_fingerprint=hashlib.sha256(f"{release}{sha256}{card}".encode()).hexdigest(),
            cluster_id=hashlib.sha256(f"{release}{sha256}{card}".encode()).hexdigest(),
            membership=ClusterMembership.NEAR_DUPLICATE,
            completeness=CardCompleteness.FULL,
            camp_path_disclosures=(camp_path,),
        )
        for card in range(2)
    ]


async def plant_openev(world: RemovalWorld) -> None:
    scratch = world.data_dir.parent / "plant-openev"
    entries = [
        SourceEntry(
            caselist="openev",
            snapshot=RELEASE,
            source_sha256=sha256,
            parser_version=VERSION,
            profile_version="2026.09.20-verbatim-1",
            fingerprint_version="card-fingerprint-v4",
            source_format=SourceFormat.DOCX,
            byte_size=10,
            outcome=SourceOutcome.PARSED,
            cards=2,
        )
        for sha256 in sorted((ESTUARY_SHA256, REVISED_SHA256))
    ]
    for entry in entries:
        path = scratch / "parsed" / source_object_key("openev", VERSION, entry.source_sha256)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(entry.model_dump_json() + "\n", encoding="utf-8")
    occurrences = sorted(
        [
            *rows(RELEASE, ESTUARY_SHA256, camp_path_disclosure(RELEASE, estuary_row(world))),
            *rows(RELEASE, REVISED_SHA256, camp_path_disclosure(RELEASE, NEW_ROW)),
            *rows(NEXT_RELEASE, REVISED_SHA256, camp_path_disclosure(NEXT_RELEASE, NEXT_YEAR_ROW)),
        ],
        key=lambda row: (row.cluster_id, row.source_sha256),
    )
    await LocalParsedStore(scratch).write_aggregates(
        "openev", VERSION, index=entries, failures=[], occurrences=occurrences
    )
    for path in sorted((scratch / "parsed").rglob("*.jsonl")):
        relative = path.relative_to(scratch / "parsed").as_posix()
        target = world.data_dir / "parsed" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
        await world.bucket.put_file(f"parsed/{relative}", path)


def lines(world: RemovalWorld, key: str) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in (world.data_dir / "parsed" / key).read_text().splitlines()
        if line.strip()
    ]


def bucket_lines(world: RemovalWorld, key: str) -> list[dict[str, object]]:
    body = world.client.get_object(Bucket=world.bucket_name, Key=f"parsed/{key}")["Body"].read().decode()
    return [json.loads(line) for line in body.splitlines() if line.strip()]


async def test_a_camp_path_withdrawal_drops_its_releases_rows_and_keeps_the_other_releases(
    world: RemovalWorld,
) -> None:
    await another_release_holds_the_later_upload(world)
    await plant_openev(world)
    assert rows_of(world, NEXT_RELEASE_KEY)[0] == {NEXT_YEAR_ROW: REVISED_SHA256}
    next_year = camp_path_disclosure(NEXT_RELEASE, NEXT_YEAR_ROW)

    plan = await plan_removal(world)
    revised = plan.source(REVISED_SHA256)
    assert revised is not None and revised.disposition is Disposition.WITHDRAW
    changes = {(change.side, change.key): change for change in plan.aggregates}
    assert changes[(Side.LOCAL, TABLE)].rows_dropped == 4
    assert changes[(Side.LOCAL, BESIDE)].action is AggregateAction.REWRITE
    assert changes[(Side.LOCAL, BESIDE)].rows_dropped == 2

    assert (await world.service().execute(plan)).completed

    for read in (lines, bucket_lines):
        table = read(world, TABLE)
        assert [(row["source_sha256"], row["snapshot"]) for row in table] == [
            (REVISED_SHA256, NEXT_RELEASE)
        ] * 2
        assert [row["source_sha256"] for row in read(world, f"openev/{VERSION}/index.jsonl")] == [
            REVISED_SHA256
        ]
        (kept,) = read(world, BESIDE)
        assert (kept["source_sha256"], kept["snapshot"], kept["camp_path_disclosure"]) == (
            REVISED_SHA256,
            NEXT_RELEASE,
            next_year,
        )
    table_bytes = (world.data_dir / "parsed" / TABLE).read_bytes()
    assert lines(world, BESIDE)[0]["occurrence_table_sha256"] == hashlib.sha256(table_bytes).hexdigest()
    read_back = await LocalParsedStore(world.data_dir).read_occurrences("openev", VERSION)
    assert read_back is not None
    assert {row.camp_path_disclosures for row in read_back} == {(next_year,)}, "the rows keep their camp path"

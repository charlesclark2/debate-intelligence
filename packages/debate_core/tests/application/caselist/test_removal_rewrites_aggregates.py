"""A removal rewrites only the aggregates of the version directories holding what it removes (`v1-e30-t33`).

The PM's ruling of 2026-11-05. A whole-file removal reaches, on each side, the version directories
where that side holds the file's per-source parsed file, and nothing else; it rewrites each of their
aggregates without the rows that name the file and purges the older versions, so nothing is rebuilt
afterwards; a retired directory's aggregates are deleted instead; and a withdrawal does the same with
the rows of the disclosures it withdraws.

The world is synthetic throughout. Three caselists hold invented files, imported and published by the
real importer and publisher, and the parsed store is planted from the store's own record models
(:func:`plant`): one row per source in `index.jsonl`, two cards per disclosure in `occurrences.jsonl`.

* `testcl26`, `2026.10.27-docx-7`, both sides: `only` at Alpha R1, `kept` at Bravo R1, `two` at
  Alpha R2, `team` at Alpha R3 and Bravo R3;
* `testcl26`, `2026.10.20-docx-6`, both sides: `kept`, unsupported;
* `testcm26`, `2026.10.27-docx-7`, both sides: `two` at Alpha R2;
* `testcl25` (the backfile), `2026.10.27-docx-7`, the bucket only: `backfile` at Bravo R4.

So `testcl26`'s current `index.jsonl` has 4 rows, `failures.jsonl` none, and `occurrences.jsonl` 10:
two cards for each of `only`, `kept` and `two`, and two for each of `team`'s two disclosures. Every
count below is worked out from this table. The bucket holds an older version of each current
occurrence table too, with the same rows: what a purge has to take. The schools and team codes are
invented.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Final

import pytest

from debate_core.application.caselist.import_service import CaselistImportService
from debate_core.application.caselist.manifest import manifest_key, write_manifest
from debate_core.application.caselist.publish_service import CaselistPublishService
from debate_core.application.caselist.removal_plan import (
    AggregateAction,
    AggregateChange,
    RemovalPlan,
    Side,
    SourceSelector,
    parse_team_selector,
)
from debate_core.application.caselist.removal_residue import CLOCK_SKEW_MARGIN
from debate_core.application.caselist.removal_service import RemovalIncomplete, TakedownAccess
from debate_core.application.caselist.status_service import CaselistStatusService
from debate_core.application.errors import error_code_of
from debate_core.application.ports.evidence_versions import EvidenceVersionStore, ObjectVersion
from debate_core.application.ports.parsed_store import (
    OccurrenceRecord,
    SourceEntry,
    SourceOutcome,
    parse_version_directory,
    source_object_key,
)
from debate_core.application.ports.suppression import (
    ReasonCode,
    RemovalLogEntry,
    RemovalLogKind,
    RemovalOutcome,
    RemovalScopeEntry,
    RemovalSelectorKind,
    SuppressionAction,
    SuppressionEntry,
    disclosure_digest,
)
from debate_core.domain.card_occurrence import ClusterMembership
from debate_core.domain.caselist import Event, SourceFormat
from debate_core.domain.debate_files import CardCompleteness
from debate_core.integrations.local import FsEvidenceObjectStore, FsSnapshotStore, SqliteDatabase
from debate_core.integrations.local.archive_reader import archive_digest, read_archive
from debate_core.integrations.local.parsed_store import LocalParsedStore
from debate_core.integrations.local.sqlite_caselist_repository import SqliteCaselistRepository
from debate_core.integrations.s3 import S3EvidenceVersionStore
from debate_core.testing.fakes.suppression import empty_suppression_list

from .conftest import REMOVAL_TIME, REQUEST, TAKEDOWN_ROLE, RemovalWorld, SignedInAs
from .test_manifest_and_aggregate_residue import backdate

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

CASELIST: Final = "testcl26"
SECOND: Final = "testcm26"
BACKFILE: Final = "testcl25"
CURRENT: Final = "2026.10.27-docx-7"
OLDER: Final = "2026.10.20-docx-6"
SNAPSHOT: Final = date(2026, 10, 27)
PROFILE: Final = "2026.09.20-verbatim-1"
FINGERPRINT: Final = "card-fingerprint-v4"
AGGREGATES: Final = ("index.jsonl", "failures.jsonl", "occurrences.jsonl")

ALPHA: Final = ("Alpha School", "AlOn")
BRAVO: Final = ("Bravo School", "BrTw")


def member_path(team: tuple[str, str], round_label: str) -> str:
    school, code = team
    return f"{school}/{code}/{school}-{code}-Aff-Synthetic Open-{round_label}.pdf"


def body(name: str) -> bytes:
    return b"%PDF-1.4\n% a synthetic file for the aggregate tests: " + name.encode() + b"\n%%EOF\n"


def digest(name: str) -> str:
    return hashlib.sha256(body(name)).hexdigest()


MEMBERS: Final[dict[str, tuple[tuple[str, str], ...]]] = {
    CASELIST: (
        (member_path(ALPHA, "Round 1"), "only"),
        (member_path(BRAVO, "Round 1"), "kept"),
        (member_path(ALPHA, "Round 2"), "two"),
        (member_path(ALPHA, "Round 3"), "team"),
        (member_path(BRAVO, "Round 3"), "team"),
    ),
    SECOND: ((member_path(ALPHA, "Round 2"), "two"),),
    BACKFILE: ((member_path(BRAVO, "Round 4"), "backfile"),),
}


@dataclass(frozen=True, slots=True)
class Planted:
    """One source as the plant writes it: its body's name, outcome and disclosure paths."""

    name: str
    paths: tuple[str, ...] = ()
    outcome: SourceOutcome = SourceOutcome.PARSED


def fingerprint(name: str, path: str, card: int) -> str:
    return hashlib.sha256(f"{name}|{card}".encode()).hexdigest()


#: The cluster `only`'s first card shares with `kept`'s: its id is `only`'s fingerprint, the smaller.
SHARED_CLUSTER: Final = min(fingerprint("only", "", 0), fingerprint("kept", "", 0))


def plant_rows(
    caselist: str, version: str, sources: tuple[Planted, ...]
) -> tuple[list[SourceEntry], list[OccurrenceRecord]]:
    entries: list[SourceEntry] = []
    occurrences: list[OccurrenceRecord] = []
    common: dict[str, object] = {
        "caselist": caselist,
        "snapshot": SNAPSHOT.isoformat(),
        "parser_version": parse_version_directory(version)[0],
        "profile_version": PROFILE,
        "fingerprint_version": FINGERPRINT,
    }
    for one in sources:
        if one.outcome is SourceOutcome.PARSED:
            entry = SourceEntry.model_validate(
                {
                    **common,
                    "source_sha256": digest(one.name),
                    "source_format": SourceFormat.PDF,
                    "byte_size": len(body(one.name)),
                    "outcome": SourceOutcome.PARSED,
                    "cards": 2,
                }
            )
        else:
            entry = SourceEntry.for_failure(
                reason="UNSUPPORTED_FORMAT",
                detail="a PDF",
                **common,
                source_sha256=digest(one.name),
                source_format=SourceFormat.PDF,
                byte_size=len(body(one.name)),
            )
        entries.append(entry)
        if one.outcome is not SourceOutcome.PARSED:
            continue
        for path in one.paths:
            for card in range(2):
                exact = fingerprint(one.name, path, card)
                cluster = SHARED_CLUSTER if card == 0 and one.name in ("only", "kept") else exact
                occurrences.append(
                    OccurrenceRecord.model_validate(
                        {
                            **common,
                            "last_snapshot": SNAPSHOT.isoformat(),
                            "source_sha256": digest(one.name),
                            "disclosure": disclosure_digest(caselist, path),
                            "first_element_index": card * 3,
                            "last_element_index": card * 3 + 2,
                            "exact_fingerprint": exact,
                            "cluster_id": cluster,
                            "membership": ClusterMembership.NEAR_DUPLICATE,
                            "completeness": CardCompleteness.FULL,
                        }
                    )
                )
    occurrences.sort(key=lambda row: (row.cluster_id, row.source_sha256, row.first_element_index))
    return entries, occurrences


async def plant(
    world: RemovalWorld,
    caselist: str,
    version: str,
    sources: tuple[Planted, ...],
    *,
    here: bool = True,
    bucket: bool = True,
) -> None:
    """Write one version directory's per-source files and aggregates, here and in the bucket.

    The aggregates are written by the store itself, so their bytes are the store's. In the bucket the
    occurrence table is put twice, so it has an older version holding the same rows.
    """
    scratch = world.data_dir.parent / f"plant-{caselist}-{version}"
    store = LocalParsedStore(scratch)
    entries, occurrences = plant_rows(caselist, version, sources)
    for entry in entries:
        path = scratch / "parsed" / source_object_key(caselist, version, entry.source_sha256)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(entry.model_dump_json() + "\n", encoding="utf-8")
    await store.write_aggregates(
        caselist,
        version,
        index=entries,
        failures=[entry for entry in entries if entry.outcome is not SourceOutcome.PARSED],
        occurrences=occurrences,
    )
    for path in sorted((scratch / "parsed").rglob("*.jsonl")):
        relative = path.relative_to(scratch / "parsed").as_posix()
        if here:
            target = world.data_dir / "parsed" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(path.read_bytes())
        if bucket:
            times = 2 if relative.endswith("/occurrences.jsonl") else 1
            for _ in range(times):
                await world.bucket.put_file(f"parsed/{relative}", path)


def archive(directory: Path, caselist: str) -> Path:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as written:
        for path, name in MEMBERS[caselist]:
            written.writestr(
                zipfile.ZipInfo(f"{caselist}-1027/{path}", date_time=(1980, 1, 1, 0, 0, 0)), body(name)
            )
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{caselist}-1027.zip"
    target.write_bytes(buffer.getvalue())
    return target


@pytest.fixture
async def world(tmp_path: Path, s3_client: S3Client, evidence_bucket: str) -> RemovalWorld:
    """The table in the module docstring, imported, published and planted."""
    data_dir = tmp_path / "evidence"
    importer = CaselistImportService(
        caselists=SqliteCaselistRepository(SqliteDatabase.open(data_dir)),
        blobs=FsSnapshotStore(data_dir),
        suppression=empty_suppression_list(),
    )
    built = RemovalWorld(data_dir=data_dir, bucket_name=evidence_bucket, client=s3_client)
    limit = 64 * 1024 * 1024
    for caselist in (CASELIST, SECOND, BACKFILE):
        zipped = archive(tmp_path / "zips", caselist)
        report = await importer.import_archive(
            read_archive(zipped, max_archive_bytes=limit, max_unpacked_bytes=limit),
            caselist=caselist,
            snapshot=SNAPSHOT,
            event=Event("LD"),
            archive_sha256=archive_digest(zipped),
        )
        write_manifest(report, FsEvidenceObjectStore(data_dir).path_for(manifest_key(caselist, SNAPSHOT)))
        publisher = CaselistPublishService(
            local=built.local, remote=built.bucket, suppression=empty_suppression_list()
        )
        assert (await publisher.execute(await publisher.plan(caselist))).succeeded
    await plant(
        built,
        CASELIST,
        CURRENT,
        (
            Planted("only", (member_path(ALPHA, "Round 1"),)),
            Planted("kept", (member_path(BRAVO, "Round 1"),)),
            Planted("two", (member_path(ALPHA, "Round 2"),)),
            Planted("team", (member_path(ALPHA, "Round 3"), member_path(BRAVO, "Round 3"))),
        ),
    )
    await plant(built, CASELIST, OLDER, (Planted("kept", outcome=SourceOutcome.UNSUPPORTED),))
    await plant(built, SECOND, CURRENT, (Planted("two", (member_path(ALPHA, "Round 2"),)),))
    await plant(
        built, BACKFILE, CURRENT, (Planted("backfile", (member_path(BRAVO, "Round 4"),)),), here=False
    )
    return built


# ------------------------------------------------------------------------------------------------
# Reading the world
# ------------------------------------------------------------------------------------------------


def local_key(caselist: str, version: str, name: str) -> str:
    return f"{caselist}/{version}/{name}"


def bucket_key(caselist: str, version: str, name: str) -> str:
    return f"parsed/{caselist}/{version}/{name}"


def reached(plan: RemovalPlan) -> dict[tuple[Side, str], AggregateChange]:
    return {(change.side, change.key): change for change in plan.aggregates}


def directories(plan: RemovalPlan) -> set[tuple[Side, str, str]]:
    return {(change.side, change.caselist, change.version) for change in plan.aggregates}


def local_lines(world: RemovalWorld, caselist: str, version: str, name: str) -> list[bytes]:
    return (
        (world.data_dir / "parsed" / local_key(caselist, version, name))
        .read_bytes()
        .splitlines(keepends=True)
    )


def bucket_versions(world: RemovalWorld, key: str) -> list[tuple[str, bytes]]:
    """Every version of exactly `key`, newest first, with its bytes."""
    listed = world.client.list_object_versions(Bucket=world.bucket_name, Prefix=key)
    found: list[tuple[str, bytes]] = []
    for version in listed.get("Versions", []):
        if version.get("Key") != key:
            continue
        version_id = str(version.get("VersionId"))
        found.append(
            (
                version_id,
                world.client.get_object(Bucket=world.bucket_name, Key=key, VersionId=version_id)[
                    "Body"
                ].read(),
            )
        )
    return found


def everything_under(world: RemovalWorld, prefix: str) -> list[tuple[str, str]]:
    listed = world.client.list_object_versions(Bucket=world.bucket_name, Prefix=prefix)
    return sorted(
        [(str(v.get("Key")), str(v.get("VersionId"))) for v in listed.get("Versions", [])]
        + [(str(m.get("Key")), str(m.get("VersionId"))) for m in listed.get("DeleteMarkers", [])]
    )


def rows_of(lines: list[bytes]) -> list[dict[str, object]]:
    return [json.loads(line) for line in lines if line.strip()]


def without(lines: list[bytes], *names: str) -> list[bytes]:
    """`lines` less those naming one of `names`' sources: what the rewrite must leave, byte for byte."""
    digests = {digest(name) for name in names}
    return [line for line in lines if json.loads(line)["source_sha256"] not in digests]


async def plan_removal(world: RemovalWorld, name: str, *, include_shared: bool = False) -> RemovalPlan:
    return await world.service().plan(
        SourceSelector(digest(name)),
        request_id=REQUEST,
        reason=ReasonCode.REQUESTED_BY_TEAM,
        include_shared=include_shared,
    )


async def remove(world: RemovalWorld, name: str, *, include_shared: bool = False) -> RemovalPlan:
    plan = await plan_removal(world, name, include_shared=include_shared)
    assert (await world.service().execute(plan)).completed
    return plan


# ------------------------------------------------------------------------------------------------
# Which aggregates a whole-file removal plans: the ruling's (a)
# ------------------------------------------------------------------------------------------------


async def test_a_file_one_caselist_holds_reaches_only_the_directories_holding_its_parsed_file(
    world: RemovalWorld,
) -> None:
    """`only` is parsed in `testcl26`'s current directory alone: its older directory, `testcm26`, the
    backfile and OpenEv hold no parsed file of it, so none of their aggregates is planned."""
    plan = await plan_removal(world, "only")

    assert directories(plan) == {(Side.LOCAL, CASELIST, CURRENT), (Side.BUCKET, CASELIST, CURRENT)}
    changes = reached(plan)
    for side, key_of in ((Side.LOCAL, local_key), (Side.BUCKET, bucket_key)):
        index = changes[(side, key_of(CASELIST, CURRENT, "index.jsonl"))]
        failures = changes[(side, key_of(CASELIST, CURRENT, "failures.jsonl"))]
        occurrences = changes[(side, key_of(CASELIST, CURRENT, "occurrences.jsonl"))]
        assert (index.action, index.rows, index.rows_dropped) == (AggregateAction.REWRITE, 4, 1)
        assert (failures.action, failures.rows, failures.rows_dropped) == (AggregateAction.LEFT, 0, 0)
        assert (occurrences.action, occurrences.rows, occurrences.rows_dropped) == (
            AggregateAction.REWRITE,
            10,
            2,
        )
    bucket_occurrences = changes[(Side.BUCKET, bucket_key(CASELIST, CURRENT, "occurrences.jsonl"))]
    assert bucket_occurrences.versions is not None and len(bucket_occurrences.versions) == 1, "the older one"
    assert bucket_occurrences.bytes == len(
        b"".join(local_lines(world, CASELIST, CURRENT, "occurrences.jsonl"))
    )
    assert all(planned.kind.value != "parsed_aggregate" for planned in plan.objects)


async def test_its_removal_rewrites_those_tables_without_its_rows_and_purges_their_older_versions(
    world: RemovalWorld,
) -> None:
    before = {name: local_lines(world, CASELIST, CURRENT, name) for name in AGGREGATES}
    untouched = {
        prefix: everything_under(world, prefix)
        for prefix in (f"parsed/{CASELIST}/{OLDER}/", f"parsed/{SECOND}/", f"parsed/{BACKFILE}/")
    }

    await remove(world, "only")

    for name in AGGREGATES:
        expected = without(before[name], "only")
        assert local_lines(world, CASELIST, CURRENT, name) == expected, name
        (current,) = bucket_versions(world, bucket_key(CASELIST, CURRENT, name))
        assert current[1].splitlines(keepends=True) == expected, f"{name}: one version, the rewrite"
    assert len(rows_of(local_lines(world, CASELIST, CURRENT, "index.jsonl"))) == 3
    assert len(rows_of(local_lines(world, CASELIST, CURRENT, "occurrences.jsonl"))) == 8
    for prefix, versions in untouched.items():
        assert everything_under(world, prefix) == versions, prefix


async def test_a_surviving_cluster_keeps_the_id_a_removed_card_gave_it(world: RemovalWorld) -> None:
    """The ruling's Q3: `kept`'s first card keeps the cluster id that was `only`'s fingerprint."""
    await remove(world, "only")

    kept = [
        row
        for row in rows_of(local_lines(world, CASELIST, CURRENT, "occurrences.jsonl"))
        if row["source_sha256"] == digest("kept") and row["first_element_index"] == 0
    ]
    assert [row["cluster_id"] for row in kept] == [SHARED_CLUSTER]


async def test_a_file_two_caselists_hold_reaches_both(world: RemovalWorld) -> None:
    plan = await plan_removal(world, "two", include_shared=True)

    assert directories(plan) == {
        (side, caselist, CURRENT) for side in (Side.LOCAL, Side.BUCKET) for caselist in (CASELIST, SECOND)
    }
    changes = reached(plan)
    assert changes[(Side.BUCKET, bucket_key(SECOND, CURRENT, "occurrences.jsonl"))].rows_dropped == 2
    assert changes[(Side.BUCKET, bucket_key(SECOND, CURRENT, "index.jsonl"))].rows_dropped == 1

    assert (await world.service().execute(plan)).completed
    assert rows_of(local_lines(world, SECOND, CURRENT, "occurrences.jsonl")) == []
    assert rows_of(local_lines(world, SECOND, CURRENT, "index.jsonl")) == []


async def test_a_backfile_held_only_in_the_bucket_is_rewritten_there_and_nothing_is_rebuilt(
    world: RemovalWorld,
) -> None:
    before = bucket_versions(world, bucket_key(BACKFILE, CURRENT, "occurrences.jsonl"))[0][1]
    plan = await plan_removal(world, "backfile")

    assert directories(plan) == {(Side.BUCKET, BACKFILE, CURRENT)}

    assert (await world.service().execute(plan)).completed
    (after,) = bucket_versions(world, bucket_key(BACKFILE, CURRENT, "occurrences.jsonl"))
    assert after[1] == b"".join(without(before.splitlines(keepends=True), "backfile")) == b""
    assert not (world.data_dir / "parsed" / BACKFILE).exists()


# ------------------------------------------------------------------------------------------------
# A retired directory is deleted, not rewritten: the ruling's addition to (a)
# ------------------------------------------------------------------------------------------------


def retire(world: RemovalWorld, caselist: str, version: str) -> None:
    """Tag every current object of a directory as `caselist retire --bucket --execute` does."""
    listed = world.client.list_objects_v2(Bucket=world.bucket_name, Prefix=f"parsed/{caselist}/{version}/")
    for one in listed.get("Contents", []):
        world.client.put_object_tagging(
            Bucket=world.bucket_name,
            Key=str(one.get("Key")),
            Tagging={"TagSet": [{"Key": "debate-retention", "Value": "superseded"}]},
        )


async def test_a_retired_directory_holding_the_file_has_its_aggregates_deleted_not_rewritten(
    world: RemovalWorld,
) -> None:
    await plant(
        world,
        CASELIST,
        OLDER,
        (
            Planted("kept", outcome=SourceOutcome.UNSUPPORTED),
            Planted("only", outcome=SourceOutcome.UNSUPPORTED),
        ),
    )
    retire(world, CASELIST, OLDER)

    plan = await plan_removal(world, "only")

    changes = reached(plan)
    for name in AGGREGATES:
        retired = changes[(Side.BUCKET, bucket_key(CASELIST, OLDER, name))]
        assert retired.action is AggregateAction.DELETE, name
        assert (
            changes[(Side.BUCKET, bucket_key(CASELIST, CURRENT, name))].action is not AggregateAction.DELETE
        )
    assert (
        changes[(Side.LOCAL, local_key(CASELIST, OLDER, "failures.jsonl"))].action is AggregateAction.REWRITE
    )

    assert (await world.service().execute(plan)).completed
    for name in AGGREGATES:
        assert bucket_versions(world, bucket_key(CASELIST, OLDER, name)) == [], name
    assert rows_of(local_lines(world, CASELIST, OLDER, "failures.jsonl")) == [
        json.loads(line) for line in local_lines(world, CASELIST, OLDER, "index.jsonl")
    ]


# ------------------------------------------------------------------------------------------------
# Re-runs: the per-source file outlives the rows, and an earlier build's run is found by its scope
# ------------------------------------------------------------------------------------------------


@dataclass
class RefusesRawDeletes:
    """The takedown's version store, refusing to delete any `raw/` version: a run stopped part-way."""

    inner: EvidenceVersionStore

    @property
    def location(self) -> str:
        return self.inner.location

    async def list_versions(self, prefix: str) -> tuple[ObjectVersion, ...]:
        return await self.inner.list_versions(prefix)

    async def get_version_file(self, version: ObjectVersion, destination: Path) -> None:
        await self.inner.get_version_file(version, destination)

    async def delete_versions(self, versions: Sequence[ObjectVersion]) -> int:
        chosen = tuple(versions)
        if any(one.key.startswith("raw/") for one in chosen):
            raise OSError("refused for the test")
        return await self.inner.delete_versions(chosen)


async def test_a_run_stopped_after_the_aggregates_is_found_again_by_the_per_source_file(
    world: RemovalWorld,
) -> None:
    def stopping() -> TakedownAccess:
        return TakedownAccess(
            versions=RefusesRawDeletes(S3EvidenceVersionStore(bucket=world.bucket_name, client=world.client)),
            objects=world.bucket,
            caller=SignedInAs(TAKEDOWN_ROLE),
            profile="debate-dev-evidence-removal",
            bucket=world.bucket_name,
        )

    plan = await plan_removal(world, "only")
    with pytest.raises(RemovalIncomplete):
        await world.service(takedown=stopping).execute(plan)
    per_source = f"parsed/{source_object_key(CASELIST, CURRENT, digest('only'))}"
    assert bucket_versions(world, per_source), "the run stopped before the per-source file"
    for name in AGGREGATES:
        (rewritten,) = bucket_versions(world, bucket_key(CASELIST, CURRENT, name))
        rows = rows_of(rewritten[1].splitlines(keepends=True))
        assert digest("only") not in {row["source_sha256"] for row in rows}, f"{name}: after the aggregates"

    again = await plan_removal(world, "only")

    assert (Side.BUCKET, CASELIST, CURRENT) in directories(again)
    assert (await world.service().execute(again)).completed
    assert bucket_versions(world, per_source) == []


async def test_a_per_source_file_left_only_as_an_older_version_still_reaches_its_directory(
    world: RemovalWorld,
) -> None:
    """A delete with no version id hid the bucket's per-source file under a marker: its version is still
    restorable, so its directory's tables may still hold its rows, and are reached."""
    per_source = f"parsed/{source_object_key(CASELIST, CURRENT, digest('only'))}"
    world.client.delete_object(Bucket=world.bucket_name, Key=per_source)
    assert world.client.list_objects_v2(Bucket=world.bucket_name, Prefix=per_source).get("KeyCount") == 0

    plan = await plan_removal(world, "only")

    assert (Side.BUCKET, CASELIST, CURRENT) in directories(plan)
    assert reached(plan)[(Side.BUCKET, bucket_key(CASELIST, CURRENT, "occurrences.jsonl"))].rows_dropped == 2


async def test_a_rerun_finds_rows_an_earlier_build_left_by_the_caselists_its_scope_recorded(
    world: RemovalWorld,
) -> None:
    """An earlier build deleted the per-source files first. Its run stopped with the rows still in
    the tables: only the scope it wrote says where to look."""
    earlier = REMOVAL_TIME - timedelta(days=1)
    await world.suppression().append(
        [
            SuppressionEntry(
                action=SuppressionAction.SUPPRESS,
                sha256=digest("only"),
                recorded_at=earlier,
                reason=ReasonCode.REQUESTED_BY_TEAM,
                request_id=REQUEST,
            )
        ]
    )
    entry = RemovalLogEntry(
        kind=RemovalLogKind.REMOVAL,
        recorded_at=earlier,
        request_id=REQUEST,
        reason=ReasonCode.REQUESTED_BY_TEAM,
        environment="dev",
        selector=RemovalSelectorKind.SOURCE,
        outcome=RemovalOutcome.INCOMPLETE,
        error_code="OS_ERROR",
    )
    scope = RemovalScopeEntry(
        recorded_at=earlier,
        request_id=REQUEST,
        environment="dev",
        caselists=(CASELIST,),
        manifest_rewrites=(),
    )
    await world.removal_log().append([entry], scopes=[scope])
    per_source = source_object_key(CASELIST, CURRENT, digest("only"))
    (world.data_dir / "parsed" / per_source).unlink()
    for version_id, _ in bucket_versions(world, f"parsed/{per_source}"):
        world.client.delete_object(Bucket=world.bucket_name, Key=f"parsed/{per_source}", VersionId=version_id)

    plan = await plan_removal(world, "only")

    changes = reached(plan)
    for side, key_of in ((Side.LOCAL, local_key), (Side.BUCKET, bucket_key)):
        assert changes[(side, key_of(CASELIST, CURRENT, "occurrences.jsonl"))].rows_dropped == 2
    assert {caselist for _, caselist, _ in directories(plan)} == {CASELIST}


# ------------------------------------------------------------------------------------------------
# Withdrawals: the same rewrite, by disclosure
# ------------------------------------------------------------------------------------------------


async def test_a_team_withdrawal_drops_its_disclosures_rows_and_keeps_the_entry_another_team_holds(
    world: RemovalWorld,
) -> None:
    """`team` is Alpha's and Bravo's: Alpha's withdrawal takes its two rows, and the entry stays. `only`
    is Alpha's alone, and goes whole; `two` is held in `testcm26` by the same code, so its copy here
    goes, and `testcm26`'s tables are left as they are."""
    occurrences = local_lines(world, CASELIST, CURRENT, "occurrences.jsonl")
    second = {name: local_lines(world, SECOND, CURRENT, name) for name in AGGREGATES}
    remover = world.service()
    plan = await remover.plan(
        parse_team_selector(f"{CASELIST}/{ALPHA[0]}/{ALPHA[1]}"),
        request_id=REQUEST,
        reason=ReasonCode.REQUESTED_BY_TEAM,
    )
    withdrawn = disclosure_digest(CASELIST, member_path(ALPHA, "Round 3"))

    assert (await remover.execute(plan)).completed

    index = rows_of(local_lines(world, CASELIST, CURRENT, "index.jsonl"))
    assert sorted(str(row["source_sha256"]) for row in index) == sorted([digest("kept"), digest("team")])
    expected = [
        line for line in without(occurrences, "only", "two") if json.loads(line)["disclosure"] != withdrawn
    ]
    assert local_lines(world, CASELIST, CURRENT, "occurrences.jsonl") == expected
    assert len(rows_of(expected)) == 4, "kept's two cards and Bravo's two of team"
    for name in AGGREGATES:
        assert local_lines(world, SECOND, CURRENT, name) == second[name], name


async def test_a_rerun_of_a_completed_withdrawal_leaves_the_version_it_left_clean(
    world: RemovalWorld,
) -> None:
    """`team`'s per-source file stays, since Bravo holds it, so the same request run again reaches the
    directory again. Its rewrite, written well inside the first run and since replaced by a rebuild, is
    the version that run left clean: status never counts it, and the re-run does not purge it."""
    remover = world.service()
    selector = parse_team_selector(f"{CASELIST}/{ALPHA[0]}/{ALPHA[1]}")
    assert (
        await remover.execute(
            await remover.plan(selector, request_id=REQUEST, reason=ReasonCode.REQUESTED_BY_TEAM)
        )
    ).completed
    key = bucket_key(CASELIST, CURRENT, "occurrences.jsonl")
    ((rewrite, body),) = bucket_versions(world, key)
    backdate(world, key, rewrite, REMOVAL_TIME - timedelta(minutes=20))
    rebuilt = world.data_dir.parent / "rebuilt-occurrences.jsonl"
    rebuilt.write_bytes(body)
    await world.bucket.put_file(key, rebuilt)

    again = await world.service().plan(selector, request_id=REQUEST, reason=ReasonCode.REQUESTED_BY_TEAM)

    assert reached(again)[(Side.BUCKET, key)].action is AggregateAction.LEFT
    assert again.nothing_to_do


# ------------------------------------------------------------------------------------------------
# A line the removal cannot read stops it with nothing written
# ------------------------------------------------------------------------------------------------


async def test_an_unreadable_line_stops_the_run_incomplete_with_nothing_written(world: RemovalWorld) -> None:
    table = world.data_dir / "parsed" / local_key(CASELIST, CURRENT, "occurrences.jsonl")
    table.write_bytes(table.read_bytes() + b"not a row\n")
    await world.bucket.put_file(bucket_key(CASELIST, CURRENT, "occurrences.jsonl"), table)
    plan = await plan_removal(world, "only")
    assert {
        change.unreadable_line for change in plan.aggregates if change.action is AggregateAction.UNREADABLE
    } == {11}
    tree, bucket = world.tree(), everything_under(world, "")

    with pytest.raises(RemovalIncomplete) as stopped:
        await world.service().execute(plan)

    assert error_code_of(stopped.value.__cause__ or stopped.value) == "UNREADABLE_AGGREGATE_LINE"
    log_file = world.data_dir / "suppression" / "removal-log.jsonl"
    log = [RemovalLogEntry.from_line(line) for line in log_file.read_text().splitlines() if line.strip()]
    assert [one.outcome for one in log] == [RemovalOutcome.INCOMPLETE]
    assert await world.suppression().entries() == ()
    changed = {path for path in set(tree) | set(world.tree()) if tree.get(path) != world.tree().get(path)}
    assert changed <= {
        "suppression/removal-log.jsonl",
        "suppression/removal-scopes.jsonl",
        "suppression/removal-aggregates.jsonl",
    }
    assert {key for key, _ in set(everything_under(world, "")) - set(bucket)} <= {
        "manifests/_suppression/removal-log.jsonl",
        "manifests/_suppression/removal-scopes.jsonl",
        "manifests/_suppression/removal-aggregates.jsonl",
    } | {key for key, _ in everything_under(world, "manifests/_suppression/preflight/")}


async def test_rows_put_back_after_a_completed_removal_are_taken_again_with_the_version_that_held_them(
    world: RemovalWorld,
) -> None:
    """A publish from a store that still held the file, after the removal completed: the same request run
    again rewrites the table and deletes every version but its rewrite, the one it replaced included."""
    key = bucket_key(CASELIST, CURRENT, "occurrences.jsonl")
    held = world.data_dir.parent / "held-occurrences.jsonl"
    held.write_bytes(b"".join(local_lines(world, CASELIST, CURRENT, "occurrences.jsonl")))
    await remove(world, "only")
    await world.bucket.put_file(key, held)
    assert len(bucket_versions(world, key)) == 2

    plan = await plan_removal(world, "only")
    assert reached(plan)[(Side.BUCKET, key)].action is AggregateAction.REWRITE
    assert (await world.service().execute(plan)).completed

    left = bucket_versions(world, key)
    assert len(left) == 1, "every version but the rewrite is deleted"
    assert digest("only").encode() not in left[0][1]


async def test_a_table_changed_since_the_plan_stops_the_run_with_nothing_written(world: RemovalWorld) -> None:
    """A publish between the dry run and the execution: the rewrite is of the bytes the plan counted only."""
    plan = await plan_removal(world, "only")
    table = world.data_dir / "parsed" / local_key(CASELIST, CURRENT, "index.jsonl")
    changed = world.data_dir.parent / "changed-index.jsonl"
    changed.write_bytes(table.read_bytes() + table.read_bytes().splitlines(keepends=True)[0])
    await world.bucket.put_file(bucket_key(CASELIST, CURRENT, "index.jsonl"), changed)

    with pytest.raises(RemovalIncomplete) as stopped:
        await world.service().execute(plan)

    assert error_code_of(stopped.value.__cause__ or stopped.value) == "AGGREGATE_REWRITE_REFUSED"
    assert await world.suppression().entries() == ()
    still_there = [
        line
        for line in local_lines(world, CASELIST, CURRENT, "occurrences.jsonl")
        if digest("only").encode() in line
    ]
    assert len(still_there) == 2, "this machine's table is as it was"


# ------------------------------------------------------------------------------------------------
# The residue check after a rewrite: the ruling's Q4
# ------------------------------------------------------------------------------------------------


def status(world: RemovalWorld) -> CaselistStatusService:
    return CaselistStatusService(
        local=world.local,
        remote=world.bucket,
        suppression=world.suppression(),
        removal_log=world.removal_log(),
        environment="dev",
        versions=S3EvidenceVersionStore(bucket=world.bucket_name, client=world.client),
    )


async def aggregate_residue(world: RemovalWorld) -> dict[str, int]:
    report = await status(world).status(CASELIST, residue=True)
    (left,) = [one for one in report.residue if one.caselist == CASELIST]
    return {one.role: one.versions for one in left.older_versions}


async def test_status_counts_no_rewrite_and_no_directory_the_removal_did_not_reach(
    world: RemovalWorld,
) -> None:
    """Every version backdated before the removal's completion, as a real run's are: the rewrites it
    left, and `testcl26`'s older directory, which it never reached, are no residue."""
    await remove(world, "only")
    before = REMOVAL_TIME - CLOCK_SKEW_MARGIN - timedelta(minutes=5)
    for prefix in (f"parsed/{CASELIST}/{CURRENT}/", f"parsed/{CASELIST}/{OLDER}/"):
        for key, version_id in everything_under(world, prefix):
            backdate(world, key, version_id, before)

    assert await aggregate_residue(world) == {}


async def test_status_counts_an_older_version_of_a_table_it_reached(world: RemovalWorld) -> None:
    await remove(world, "only")
    key = bucket_key(CASELIST, CURRENT, "occurrences.jsonl")
    (rewrite,) = bucket_versions(world, key)
    stale = str(world.client.put_object(Bucket=world.bucket_name, Key=key, Body=b"")["VersionId"])
    backdate(world, key, stale, REMOVAL_TIME - timedelta(days=1))
    backdate(world, key, rewrite[0], REMOVAL_TIME - CLOCK_SKEW_MARGIN - timedelta(minutes=5))

    assert await aggregate_residue(world) == {"occurrences.jsonl": 1}


# ------------------------------------------------------------------------------------------------
# The placement state (`v1-e31-t10`)
# ------------------------------------------------------------------------------------------------

STATE: Final = "placement-state.sqlite"


async def plant_state(
    world: RemovalWorld, caselist: str, version: str, *, versions_in_the_bucket: int
) -> bytes:
    """A placement state's file in a directory, here and in the bucket. A removal never reads one, so
    its bytes are anything; the bucket gets it `versions_in_the_bucket` times."""
    content = f"a placement state of {caselist} {version}".encode()
    path = world.data_dir / "parsed" / local_key(caselist, version, STATE)
    path.write_bytes(content)
    for _ in range(versions_in_the_bucket):
        await world.bucket.put_file(bucket_key(caselist, version, STATE), path)
    return content


async def test_a_removal_deletes_the_placement_state_of_each_directory_it_reaches_on_each_side(
    world: RemovalWorld,
) -> None:
    """`only` is parsed in `testcl26`'s current directory alone, so that directory's state goes, here and
    in the bucket with both its versions, and is recorded; the older directory's and `testcm26`'s stay,
    as their tables do. The state is deleted, never edited: no other file of the directory changes for it."""
    await plant_state(world, CASELIST, CURRENT, versions_in_the_bucket=2)
    older = await plant_state(world, CASELIST, OLDER, versions_in_the_bucket=1)
    second = await plant_state(world, SECOND, CURRENT, versions_in_the_bucket=1)

    plan = await plan_removal(world, "only")

    states = {key: change for (_, key), change in reached(plan).items() if key.endswith(STATE)}
    assert sorted(states) == [bucket_key(CASELIST, CURRENT, STATE), local_key(CASELIST, CURRENT, STATE)]
    assert {change.action for change in states.values()} == {AggregateAction.DISCARD}
    bucket_change = states[bucket_key(CASELIST, CURRENT, STATE)]
    assert bucket_change.versions is not None and len(bucket_change.versions) == 2
    assert bucket_change.rows is None and bucket_change.sha256 is None, "a state is never counted or read"

    report = await world.service().execute(plan)

    assert report.completed
    assert report.placement_states_deleted == 2
    assert not (world.data_dir / "parsed" / local_key(CASELIST, CURRENT, STATE)).exists()
    assert bucket_versions(world, bucket_key(CASELIST, CURRENT, STATE)) == []
    assert (world.data_dir / "parsed" / local_key(CASELIST, OLDER, STATE)).read_bytes() == older
    assert [body for _, body in bucket_versions(world, bucket_key(SECOND, CURRENT, STATE))] == [second]
    (record,) = await world.removal_log().aggregate_records()
    assert bucket_key(CASELIST, CURRENT, STATE) in record.deleted
    assert all(not one.key.endswith(STATE) for one in record.kept)


async def test_status_counts_an_older_version_of_a_placement_state_it_deleted(world: RemovalWorld) -> None:
    """A version of a deleted state older than the removal is one it should have taken: residue. A new
    state the next run writes is newer than the removal, and is not."""
    await plant_state(world, CASELIST, CURRENT, versions_in_the_bucket=1)
    await remove(world, "only")
    key = bucket_key(CASELIST, CURRENT, STATE)
    stale = str(world.client.put_object(Bucket=world.bucket_name, Key=key, Body=b"stale")["VersionId"])
    backdate(world, key, stale, REMOVAL_TIME - timedelta(days=1))
    for other, version_id in everything_under(world, f"parsed/{CASELIST}/{CURRENT}/"):
        if other != key:
            backdate(world, other, version_id, REMOVAL_TIME - CLOCK_SKEW_MARGIN - timedelta(minutes=5))

    assert await aggregate_residue(world) == {STATE: 1}

    world.client.put_object(Bucket=world.bucket_name, Key=key, Body=b"the next run's state")
    assert await aggregate_residue(world) == {STATE: 1}, (
        "the new state is not residue; the stale one still is"
    )


async def test_a_state_written_between_the_plan_and_the_execution_is_deleted_too(world: RemovalWorld) -> None:
    """Every version of a reached state goes, whenever it was written: one written after the dry run
    holds the removed source's words as much as one written before."""
    await plant_state(world, CASELIST, CURRENT, versions_in_the_bucket=1)
    plan = await plan_removal(world, "only")
    path = world.data_dir / "parsed" / local_key(CASELIST, CURRENT, STATE)
    await world.bucket.put_file(bucket_key(CASELIST, CURRENT, STATE), path)

    assert (await world.service().execute(plan)).completed

    assert bucket_versions(world, bucket_key(CASELIST, CURRENT, STATE)) == []

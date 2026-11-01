"""An older build's own code, reading a camp release manifest as this build writes it (`v1-e30-t14` ac3).

Not collected: its name is not a test module's, and it is only ever run by its path, with an older
build's source first on `PYTHONPATH`. `stored_camp_manifests/README.md` gives the commands and what
each printed. It writes nothing outside pytest's temporary directory.

It carries out the stored history with the source it is run against, which writes that source's own
manifest, then puts `stored_camp_manifests/written_by_this_build/2026-policy.jsonl` in its place:
the same rows, each with the keys of :data:`ADDED` that source's own rows lack: `openev_id` and
`upstream_path_sha256` for a source from before `v1-e30-t14`, and `openev_camp_word` for one from
before `v1-e30-t31`. Then it does with that manifest everything that source does with one, and says
whether each reader refused those keys, ignored them or kept them:

* publishes it and asks for the status (the publisher and status read sources from the rows);
* pulls the next week, which asks the rows what is already imported and merges a new camp file in;
* re-derives the release's metadata (`caselist reimport-openev-metadata`);
* removes 512 by `--source`, which plans from the rows, takes 640 down as its later upload, and
  rewrites the manifest without them;
* and asks for the status once more.
"""

from __future__ import annotations

import inspect
import json
import os
from pathlib import Path

import pytest
from tests.fixtures.openev.build_synthetic_openev import CAMP_ALIASES_PATH

from debate_core.application.caselist.camp_metadata import load_camp_aliases
from debate_core.application.caselist.manifest import write_manifest_lines
from debate_core.application.caselist.openev_import_service import OpenEvImportService
from debate_core.application.caselist.openev_metadata_reimport import rederive_release
from debate_core.application.caselist.publish_service import CaselistPublishService
from debate_core.application.caselist.removal_plan import SourceSelector
from debate_core.application.caselist.status_service import CaselistStatusService
from debate_core.application.caselist.suppression import load_suppression_state
from debate_core.application.ports.suppression import ReasonCode, UnreadableAppendOnlyRecord
from debate_core.domain.caselist import Event
from debate_core.integrations.local import FsSnapshotStore
from debate_core.integrations.s3 import S3EvidenceVersionStore

from .camp_manifest_scenario import (
    MANIFEST_NAME,
    NEXT_WEEK,
    NEXT_WEEK_BODY,
    NEXT_WEEK_ROW,
    OTHER_CAMP,
    OTHER_CAMP_BODY,
    REVISED_BODY,
    REVISION,
    ROWS,
    STORED,
    WITHDRAWAL_RECORDS,
    release_lines,
    release_manifest,
    two_pulls,
)
from .conftest import REQUEST, RemovalWorld
from .test_sync_skips_suppressed_downloads import ESTUARY_SHA256, decisions, pull

pytestmark = pytest.mark.anyio

THIS_BUILDS = STORED / "written_by_this_build" / MANIFEST_NAME
ADDED = ("openev_id", "upstream_path_sha256", "openev_camp_word")
"""The keys this build's rows carry that an older build's may not (`v1-e30-t14`, `v1-e30-t31`)."""


def _source() -> str:
    import debate_core

    return Path(debate_core.__file__).parents[4].name


def _by_path(lines: list[str]) -> dict[str, str]:
    return {json.loads(line)["path"]: line for line in lines if json.loads(line)["kind"] == "member"}


def _without_the_keys(line: str, keys: tuple[str, ...]) -> str:
    """A manifest line as a build whose rows lack `keys` renders the same row."""
    row = {key: value for key, value in json.loads(line).items() if key not in keys}
    return json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _keys_as_written(before: dict[str, str], after: dict[str, str], keys: tuple[str, ...]) -> bool:
    return all(
        json.loads(after[path]).get(key) == json.loads(line).get(key) and key in json.loads(after[path])
        for path, line in before.items()
        for key in keys
    )


def _kept(before: dict[str, str], after: dict[str, str], keys: tuple[str, ...]) -> str:
    """How the rows this build wrote came through: kept byte for byte, kept with the keys, or not."""
    common = [path for path in before if path in after]
    if all(after[path] == before[path] for path in common):
        return f"kept byte for byte ({len(common)} row(s))"
    with_keys = [
        path
        for path in common
        if all(json.loads(after[path]).get(key) == json.loads(before[path]).get(key) for key in keys)
    ]
    changed = sorted(
        {
            key
            for path in common
            for key, value in json.loads(after[path]).items()
            if json.loads(before[path]).get(key) != value
        }
    )
    return (
        f"kept the keys as written on {len(with_keys)} of {len(common)} row(s); "
        f"field(s) it changed: {', '.join(changed) or 'none'}"
    )


async def test_this_source_reads_a_camp_manifest_as_this_build_writes_it(
    removal_world: RemovalWorld, capsys: pytest.CaptureFixture[str]
) -> None:
    assert os.environ.get("CHECK_AN_OLDER_BUILD_READS") == "this-builds-camp-manifests", (
        "run by its path against an older build's source; see stored_camp_manifests/README.md"
    )
    world = removal_world
    source = await two_pulls(world)
    own = release_lines(world)
    written = {key for line in own for key in json.loads(line)}
    lacks = tuple(key for key in ADDED if key not in written)
    release_manifest(world).write_bytes(THIS_BUILDS.read_bytes())
    placed = _by_path(release_lines(world))
    unchanged_but_the_keys = all(
        {key: value for key, value in json.loads(line).items() if key not in lacks} == json.loads(theirs)
        for line, theirs in zip(release_lines(world), own, strict=True)
    )
    lines: list[str] = [
        f"reader: the debate_core source at {_source()}",
        f"placed: this build's manifest; the keys this source's rows lack: {', '.join(lacks) or 'none'}; "
        f"its rows are this source's own but for them: {unchanged_but_the_keys}",
    ]

    def status_in_sync() -> CaselistStatusService:
        return CaselistStatusService(local=world.local, remote=world.bucket, suppression=world.suppression())

    publisher = CaselistPublishService(
        local=world.local, remote=world.bucket, suppression=world.suppression()
    )
    published = await publisher.execute(await publisher.plan("openev", "2026-policy"))
    status = await status_in_sync().status("openev")
    lines.append(f"publish: succeeded {published.succeeded}; status in sync: {status.in_sync}")

    source.files = [(REVISION, REVISED_BODY), (OTHER_CAMP, OTHER_CAMP_BODY), (NEXT_WEEK, NEXT_WEEK_BODY)]
    summary = await pull(world, source)
    merged = _by_path(release_lines(world))
    lines.append(
        "next pull: "
        + ", ".join(f"openev-{one} {decision.value}" for one, decision in sorted(decisions(summary).items()))
    )
    lines.append(
        f"its merge: this build's rows {_kept(placed, merged, lacks)}; "
        f"the new row {NEXT_WEEK_ROW in merged}, "
        f"with the keys {all(key in json.loads(merged.get(NEXT_WEEK_ROW, '{}')) for key in lacks)}"
    )

    importer = OpenEvImportService(
        caselists=world.repository, blobs=FsSnapshotStore(world.data_dir), suppression=world.suppression()
    )
    # The control: this source's re-derive of the same manifest without the keys, which is what it
    # would have written itself. The two may differ by the keys and nothing else.
    mine = release_lines(world)
    state = await load_suppression_state(world.suppression())
    aliases = load_camp_aliases(CAMP_ALIASES_PATH)
    with_keys, without = (
        rederive_release(
            year=2026, event=Event.POLICY, recorded_manifest=lines_, aliases=aliases, suppression=state
        )
        for lines_ in (mine, [_without_the_keys(line, lacks) for line in mine])
    )
    same_but_the_keys = [_without_the_keys(line, lacks) for line in with_keys.manifest_lines] == list(
        without.manifest_lines
    )
    rederived = await importer.reimport_metadata(
        year=2026, event=Event.POLICY, recorded_manifest=mine, aliases=aliases
    )
    write_manifest_lines(rederived.manifest_lines, release_manifest(world))
    lines.append(
        f"metadata re-import: this build's rows kept the keys as written: "
        f"{_keys_as_written(placed, _by_path(release_lines(world)), lacks)}; the same as its re-derive of "
        f"its own manifest but for the keys: {same_but_the_keys}"
    )

    before_removal = _by_path(release_lines(world))
    service = world.service()
    plan = await service.plan(
        SourceSelector(ESTUARY_SHA256), request_id=REQUEST, reason=ReasonCode.REQUESTED_BY_CAMP
    )
    report = await service.execute(plan)
    after_removal = _by_path(release_lines(world))
    later = sorted(one for version in plan.later_uploads for one in version.openev_ids)
    left = {path: line for path, line in before_removal.items() if path not in ROWS[:2]}
    lines.append(
        f"removal of 512: completed {report.log_entry.outcome.value == 'COMPLETED'}; later upload(s) "
        f"{', '.join(f'openev-{one}' for one in later)}; rows it kept {_kept(left, after_removal, lacks)}; "
        f"512 and 640 gone {not set(ROWS[:2]) & set(after_removal)}"
    )
    publisher = CaselistPublishService(
        local=world.local, remote=world.bucket, suppression=world.suppression()
    )
    published = await publisher.execute(await publisher.plan("openev", "2026-policy"))
    status = await status_in_sync().status("openev")
    lines.append(f"publish again: succeeded {published.succeeded}; status in sync: {status.in_sync}")

    with capsys.disabled():
        print()
        for line in lines:
            print(line)


async def test_this_source_reads_the_records_a_camp_path_withdrawal_leaves(
    removal_world: RemovalWorld, capsys: pytest.CaptureFixture[str]
) -> None:
    """A camp path's entry in the list, and an `openev` line in the withdrawal record (`v1-e30-t14`).

    This source's history, then this build's records of 640's camp path withdrawn put where the
    records are kept, on this machine and in the bucket. Then what the agent and the operator run
    with them: the list read, the next pull, the same removal run with this source (which finishes
    512 and takes 640 down whole, since this source has no other release holding it), a publish and
    the status, with the residue check where this source has one. Last, the withdrawal record read
    by this source's own model, which no command of it does.
    """
    assert os.environ.get("CHECK_AN_OLDER_BUILD_READS") == "this-builds-camp-manifests", (
        "run by its path against an older build's source; see stored_camp_manifests/README.md"
    )
    world = removal_world
    source = await two_pulls(world)
    placed: list[str] = []
    for name in WITHDRAWAL_RECORDS:
        body = (STORED / "written_by_this_build" / "suppression" / name).read_bytes()
        (world.data_dir / "suppression").mkdir(parents=True, exist_ok=True)
        (world.data_dir / "suppression" / name).write_bytes(body)
        world.client.put_object(Bucket=world.bucket_name, Key=f"manifests/_suppression/{name}", Body=body)
        placed.append(name)
    lines = [f"reader: the debate_core source at {_source()}", f"placed, in both places: {', '.join(placed)}"]

    state = await load_suppression_state(world.suppression())
    lines.append(f"list read: {len(state.sources)} whole file(s) and {len(state.disclosures)} disclosure(s)")

    summary = await pull(world, source)
    lines.append(
        "next pull: "
        + ", ".join(f"openev-{one} {decision.value}" for one, decision in sorted(decisions(summary).items()))
    )

    service = world.service()
    plan = await service.plan(
        SourceSelector(ESTUARY_SHA256), request_id=REQUEST, reason=ReasonCode.REQUESTED_BY_CAMP
    )
    report = await service.execute(plan)
    lines.append(
        f"the same removal: {report.log_entry.outcome.value}; removed "
        f"{len(report.log_entry.removed_sha256)} file(s), withdrew {len(report.log_entry.withdrawn_sha256)}"
    )
    publisher = CaselistPublishService(
        local=world.local, remote=world.bucket, suppression=world.suppression()
    )
    published = await publisher.execute(await publisher.plan("openev", "2026-policy"))
    status = CaselistStatusService(local=world.local, remote=world.bucket, suppression=world.suppression())
    lines.append(
        f"publish: succeeded {published.succeeded}; status in sync: {(await status.status('openev')).in_sync}"
    )
    if "removal_log" in inspect.signature(CaselistStatusService.__init__).parameters:
        residue = CaselistStatusService(
            local=world.local,
            remote=world.bucket,
            suppression=world.suppression(),
            removal_log=world.removal_log(),  # type: ignore[call-arg]
            environment="dev",  # type: ignore[call-arg]
            versions=S3EvidenceVersionStore(bucket=world.bucket_name, client=world.client),  # type: ignore[call-arg]
        )
        checked = await residue.status("openev", residue=True)
        lines.append(f"status with the residue check: completed; in sync {checked.in_sync}")
    else:
        lines.append("status with the residue check: this source reads no removal log")
    if hasattr(world.suppression(), "withdrawals"):
        try:
            withdrawals = await world.suppression().withdrawals()  # type: ignore[attr-defined]
        except UnreadableAppendOnlyRecord as refused:
            lines.append(
                f"the withdrawal record read by this source's own model: {type(refused).__name__} at line "
                f"{refused.line_number}; no command of this source reads it"
            )
        else:
            lines.append(f"the withdrawal record read by this source's own model: {len(withdrawals)} line(s)")
    else:
        lines.append("the withdrawal record: this source has no reader of it")
    left = (world.data_dir / "suppression" / "withdrawals.jsonl").read_bytes()
    lines.append(
        "the withdrawal record afterwards: this build's line kept "
        f"{(STORED / 'written_by_this_build' / 'suppression' / 'withdrawals.jsonl').read_bytes() in left}"
    )

    with capsys.disabled():
        print()
        for line in lines:
            print(line)

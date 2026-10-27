"""`caselist backfile-import` end to end in bucket mode, over moto and a stand-in site (`v1-e34-t34` ac2).

The PM's rulings of 2026-10-25, each by test, through the real application and composition root:

* a backfile caselist's complete archive imports as its dated snapshot, parses and publishes, and
  its manifest reaches the run-state bundle;
* the bucket's run lock is the weekly run's, held per step and free during the download;
* the window, the budget, the free-space precheck, the marker and the seed each refuse before anything
  is downloaded, and the dry run names them;
* the backfile ledger is the bucket's, and the weekly run's ledger is never touched;
* `caselist pull` and `landscape report` refuse a backfile; the search index is not touched;
* a removal, the suppression list and a path hold reach a backfile exactly as the current season's.

The backfile is `testcl25`, a fictional 2025-26 caselist whose complete archive is built here from the
parse world's synthetic bodies (`tests/fixtures/parse_pipeline/build_parse_world.py`). Its four members,
and what the pipeline must make of them, written by hand:

| Path | Body | Parse |
|---|---|---|
| `Maple Grove/QX/…-Round 1.docx` | `verbatim` (also in the current season) | 1 card |
| `Cedar Hollow/ZaLu/…-Round 2.docx` | `wiki` (also in the current season) | 2 cards |
| `Westfield/XY/…-Round 6.docx` | `direct` (only the backfile holds it here) | 1 card |
| `Westfield/XY/…-Quarters.pdf` | `pdf` | unsupported |

Nothing here is real caselist content, and no test opens a socket.
"""

from __future__ import annotations

import gzip
import importlib.util
import io
import json
import shutil
import sys
import tarfile
import zipfile
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any, Final

import httpx
import pytest
from tests.fixtures.parse_pipeline.build_parse_world import BODIES, WEEKS, digest_of

from debate_cli.exit_codes import ExitCode
from debate_core.application.caselist.backfile_import import BACKFILE_LEDGER_KEY
from debate_core.application.caselist.run_state import RUN_STATE_BUNDLE_KEY

World = Any
"""`conftest.py`'s world, which a test module cannot import by name."""

API: Final = "https://api.opencaselist.example.invalid/v1"
FILE_HOST: Final = "https://files.opencaselist.example.invalid"
BACKFILE: Final = "testcl25"
OTHER_BACKFILE: Final = "testcl24"
ARCHIVE_DATE: Final = date(2026, 6, 30)
LATER_ARCHIVE_DATE: Final = date(2026, 7, 28)
MANIFEST_KEY: Final = f"manifests/{BACKFILE}/{ARCHIVE_DATE.isoformat()}.jsonl"
"""The backfile's one dated snapshot: its complete archive, filed in the series every reader reads."""
WEEKLY_LEDGER_KEY: Final = "reports/sync/state/caselist-sync-download-starts.json"
WEEK_1, WEEK_2, _ = (week.snapshot for week in WEEKS)

ON_A_THURSDAY: Final = datetime(2026, 10, 15, 14, 0, tzinfo=UTC)
"""09:00 in Chicago, the morning after a weekly run: outside the no-import window."""
ON_A_WEDNESDAY: Final = datetime(2026, 10, 21, 15, 0, tzinfo=UTC)
"""10:00 in Chicago, during the weekly run's day: inside the window."""

R1: Final = "Maple Grove/QX/Maple Grove-QX-Aff-Lakeside Open-Round 1.docx"
R2: Final = "Cedar Hollow/ZaLu/Cedar Hollow-ZaLu-Neg-Lakeside Open-Round 2.docx"
R6: Final = "Westfield/XY/Westfield-XY-Neg-Lakeside Open-Round 6.docx"
QUARTERS: Final = "Westfield/XY/Westfield-XY-Aff-Lakeside Open-Quarters.pdf"
MEMBERS: Final = {R1: BODIES["verbatim"], R2: BODIES["wiki"], R6: BODIES["direct"], QUARTERS: BODIES["pdf"]}


def archive_name(caselist: str, day: date) -> str:
    return f"{caselist}-all-{day.isoformat()}.zip"


def zipped(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(members):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o644 << 16
            archive.writestr(info, members[name])
    return buffer.getvalue()


class Site:
    """The stand-in OpenCaselist's answers for the backfiles: their listings, sizes and bytes."""

    def __init__(self, world: World) -> None:
        self.world = world
        self.fetched: list[str] = []
        self.sized: list[str] = []
        self.lock_states_while_fetching: list[str] = []
        self.while_fetching: list[Any] = []

    def offer(self, caselist: str, *archives: tuple[date, bytes]) -> None:
        listing = [
            {"name": archive_name(caselist, day), "url": f"{FILE_HOST}/{archive_name(caselist, day)}"}
            for day, _ in archives
        ]
        self.world.site.get(f"{API}/caselists/{caselist}/downloads").respond(200, json=listing)
        for day, body in archives:
            url = f"{FILE_HOST}/{archive_name(caselist, day)}"
            self.world.site.head(url).mock(side_effect=self._sized(url, len(body)))
            self.world.site.get(url).mock(side_effect=self._fetched(url, body))

    def _sized(self, url: str, size: int) -> Any:
        def answer(request: httpx.Request) -> httpx.Response:
            self.sized.append(url)
            return httpx.Response(200, headers={"Content-Length": str(size)})

        return answer

    def _fetched(self, url: str, body: bytes) -> Any:
        def answer(request: httpx.Request) -> httpx.Response:
            self.fetched.append(url)
            self.lock_states_while_fetching.append(self.world.lock()["state"])
            for act in self.while_fetching:
                act()
            return httpx.Response(200, content=body)

        return answer


@pytest.fixture
def backfiles(world: World, tmp_path: Path) -> Iterator[tuple[World, Site]]:
    """Two weeks of the current season pulled and seeded from the Mac; then a cloud task's empty copy."""
    world.listing(WEEK_1, WEEK_2)
    assert world.pull()["exit_code"] == ExitCode.OK
    world.seed()
    world.monkeypatch.setenv("DEBATE_CASELIST__BACKFILE_CASELISTS", json.dumps([BACKFILE, OTHER_BACKFILE]))
    world.monkeypatch.setenv("DEBATE_REMOVAL_PROFILE", "debate-dev-evidence-removal")
    world.clock.now = ON_A_THURSDAY
    site = Site(world)
    site.offer(BACKFILE, (ARCHIVE_DATE, zipped(MEMBERS)))
    site.offer(OTHER_BACKFILE, (date(2025, 7, 1), zipped({R1: BODIES["verbatim"]})))
    world.use(tmp_path / "cloud-task")
    yield world, site


def dry_run(world: World, caselist: str = BACKFILE) -> dict[str, Any]:
    return world.run("caselist", "backfile-import", "--caselist", caselist)


def execute(world: World, caselist: str = BACKFILE) -> dict[str, Any]:
    return world.run("caselist", "backfile-import", "--caselist", caselist, "--execute")


def refusals(envelope: dict[str, Any]) -> list[str]:
    assert envelope["exit_code"] == ExitCode.DOMAIN_FAILURE, envelope
    assert envelope["error"]["code"] == "BACKFILE_IMPORT_REFUSED", envelope
    return list(envelope["error"]["details"]["refusals"])


def member_rows(world: World, key: str = MANIFEST_KEY) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in world.body(key).decode("utf-8").splitlines()]
    return [row for row in rows if row.get("kind") == "member"]


def bundle_names(world: World) -> set[str]:
    raw = gzip.decompress(world.body(RUN_STATE_BUNDLE_KEY))
    with tarfile.open(fileobj=io.BytesIO(raw)) as bundle:
        return set(bundle.getnames())


def frees(world: World) -> int:
    """How many times the run lock has been written free: one per release."""
    count = 0
    for version in world.versions("reports/sync/run-lock.json"):
        if "VersionId" not in version:
            continue
        body = world.client.get_object(
            Bucket=world.bucket, Key="reports/sync/run-lock.json", VersionId=version["VersionId"]
        )["Body"].read()
        count += json.loads(body)["state"] == "free"
    return count


# ------------------------------------------------------------------------------------------------
# The dry run
# ------------------------------------------------------------------------------------------------


def test_the_dry_run_lists_and_sizes_and_downloads_writes_and_locks_nothing(
    backfiles: tuple[World, Site],
) -> None:
    world, site = backfiles
    before = world.everything()

    planned = dry_run(world)

    assert planned["exit_code"] == ExitCode.OK, planned
    data = planned["data"]
    assert (data["caselist"], data["season"], data["archive_date"]) == (BACKFILE, "2025-26", "2026-06-30")
    assert data["archive_bytes"] == len(zipped(MEMBERS))
    assert data["refusals"] == []
    assert data["backfile_downloads_left"] == 1
    assert data["inside_no_import_window"] is False
    assert data["space"]["enough"] is True
    assert data["space"]["required_bytes"] == (len(zipped(MEMBERS)) * 6 * 5 + 3) // 4
    assert site.sized == [f"{FILE_HOST}/{archive_name(BACKFILE, ARCHIVE_DATE)}"]
    assert site.fetched == []
    assert world.everything() == before, "a dry run writes nothing to the bucket, the lock included"


# ------------------------------------------------------------------------------------------------
# The import
# ------------------------------------------------------------------------------------------------


def test_a_backfile_imports_parses_and_publishes_as_its_dated_snapshot(
    backfiles: tuple[World, Site],
) -> None:
    world, site = backfiles
    weekly_ledger = world.everything()[WEEKLY_LEDGER_KEY]
    index_before = {key: tag for key, tag in world.everything().items() if key.startswith("reports/tub/")}

    imported = execute(world)

    assert imported["exit_code"] == ExitCode.OK, imported
    counts = imported["data"]["import"]
    assert (counts["members"], counts["suppressed"]) == (4, 0)
    assert (counts["parsed"], counts["unsupported"], counts["failed"], counts["cards"]) == (3, 1, 0, 4)
    assert {row["sha256"] for row in member_rows(world)} == {
        digest_of("verbatim"),
        digest_of("wiki"),
        digest_of("direct"),
        digest_of("pdf"),
    }
    raw = world.object_keys(f"raw/caselist/{BACKFILE}/")
    assert {key.rsplit("/", 1)[-1] for key in raw} == {row["sha256"] for row in member_rows(world)}
    assert any(key.endswith("/occurrences.jsonl") for key in world.object_keys(f"parsed/{BACKFILE}/"))
    assert any(name.endswith(MANIFEST_KEY) for name in bundle_names(world)), (
        "the bundle holds the backfile's manifest"
    )
    assert world.object_keys(f"manifests/{BACKFILE}/") == {MANIFEST_KEY}, (
        "one snapshot, the complete archive's"
    )
    assert counts["archive_left_inbox"] is True
    assert site.fetched == [f"{FILE_HOST}/{archive_name(BACKFILE, ARCHIVE_DATE)}"]
    assert world.everything()[WEEKLY_LEDGER_KEY] == weekly_ledger, "the weekly run's ledger is never touched"
    ledger = json.loads(world.body(BACKFILE_LEDGER_KEY))
    assert ledger["bulk_download_starts"] == [ON_A_THURSDAY.isoformat()]
    assert {
        key: tag for key, tag in world.everything().items() if key.startswith("reports/tub/")
    } == index_before
    assert world.lock()["state"] == "free"


def test_the_lock_is_the_weekly_runs_taken_for_each_step_and_free_during_the_download(
    backfiles: tuple[World, Site],
) -> None:
    world, site = backfiles
    released_before = frees(world)

    assert execute(world)["exit_code"] == ExitCode.OK

    assert site.lock_states_while_fetching == ["free"]
    assert frees(world) - released_before == 3, "the restore, the source publish and the parsed publish"


def test_a_backfile_import_is_not_a_weekly_run_and_leaves_the_run_log_alone(
    backfiles: tuple[World, Site],
) -> None:
    world, _ = backfiles
    runs_before = world.object_keys("reports/sync-runs/")

    assert execute(world)["exit_code"] == ExitCode.OK

    assert world.object_keys("reports/sync-runs/") == runs_before


def test_running_it_again_rebuilds_the_aggregates_after_a_removal_with_no_second_download(
    backfiles: tuple[World, Site], tmp_path: Path
) -> None:
    """The removal runbook's rebuild for a backfile: run the import again. It restores the backfile's
    parsed store, rebuilds its aggregates without what the removal took out, and publishes them."""
    world, site = backfiles
    assert execute(world)["exit_code"] == ExitCode.OK
    world.use(tmp_path / "the-macs-copy")
    removed = world.run(
        "caselist", "remove", "--source", digest_of("direct"), "--reason", "REQUESTED_BY_TEAM",
        "--request", "RM-2026-07", "--execute",
    )  # fmt: skip
    assert removed["exit_code"] == ExitCode.OK, removed
    assert not [
        key for key in world.object_keys(f"parsed/{BACKFILE}/") if key.endswith("/occurrences.jsonl")
    ], "a whole-file removal deletes the aggregates of every caselist it touches"
    world.use(tmp_path / "a-later-task")

    planned = dry_run(world)
    rebuilt = execute(world)

    assert planned["data"]["already_imported"] is True
    assert planned["data"]["refusals"] == [], "imported already: no download, so no budget is spent"
    assert planned["data"]["space"]["estimate_bytes"] == 5 * len(zipped(MEMBERS))
    assert rebuilt["exit_code"] == ExitCode.OK, rebuilt
    assert len(site.fetched) == 1
    [occurrences] = [
        key for key in world.object_keys(f"parsed/{BACKFILE}/") if key.endswith("/occurrences.jsonl")
    ]
    table = world.body(occurrences).decode("utf-8")
    assert digest_of("direct") not in table
    assert digest_of("verbatim") in table and digest_of("wiki") in table


# ------------------------------------------------------------------------------------------------
# What it refuses, before anything is fetched
# ------------------------------------------------------------------------------------------------


def test_inside_the_no_import_window_it_refuses_to_start_and_the_dry_run_says_so(
    backfiles: tuple[World, Site],
) -> None:
    world, site = backfiles
    world.clock.now = ON_A_WEDNESDAY

    planned = dry_run(world)
    assert refusals(planned) == ["INSIDE_NO_IMPORT_WINDOW"]
    assert planned["error"]["details"]["plan"]["no_import_window_ends"] == "2026-10-22T05:00:00+00:00"
    assert refusals(execute(world)) == ["INSIDE_NO_IMPORT_WINDOW"]
    assert site.fetched == []
    assert world.object_keys(f"manifests/{BACKFILE}/") == set()


def test_a_window_that_opens_during_the_import_stops_the_next_locked_step_and_the_run_resumes_after_it(
    backfiles: tuple[World, Site],
) -> None:
    world, site = backfiles
    site.while_fetching.append(lambda: setattr(world.clock, "now", ON_A_WEDNESDAY))

    stopped = execute(world)

    assert refusals(stopped) == ["INSIDE_NO_IMPORT_WINDOW"]
    assert world.object_keys(f"manifests/{BACKFILE}/") == set(), "the publish step never took the lock"
    assert world.lock()["state"] == "free"

    world.clock.now = ON_A_WEDNESDAY + timedelta(days=1)
    resumed = execute(world)

    assert resumed["exit_code"] == ExitCode.OK, resumed
    assert resumed["data"]["in_inbox"] is True
    assert len(site.fetched) == 1, "the archive left in the inbox is imported; no second download"
    assert world.object_keys(f"manifests/{BACKFILE}/") == {MANIFEST_KEY}


def test_one_complete_archive_a_day_from_the_buckets_ledger_whatever_machine_asks(
    backfiles: tuple[World, Site], tmp_path: Path
) -> None:
    world, site = backfiles
    assert execute(world)["exit_code"] == ExitCode.OK
    world.use(tmp_path / "another-machine")
    world.clock.advance(timedelta(hours=23, minutes=59))

    assert refusals(dry_run(world, OTHER_BACKFILE)) == ["BACKFILE_BUDGET_SPENT"]
    assert refusals(execute(world, OTHER_BACKFILE)) == ["BACKFILE_BUDGET_SPENT"]
    assert len(site.fetched) == 1

    world.clock.advance(timedelta(minutes=2))
    assert dry_run(world, OTHER_BACKFILE)["data"]["refusals"] == []


def test_too_little_free_space_is_refused_with_both_numbers(
    backfiles: tuple[World, Site], monkeypatch: pytest.MonkeyPatch
) -> None:
    from debate_core.application.caselist_sync import VolumeReading

    world, site = backfiles
    size = len(zipped(MEMBERS))
    required = (size * 6 * 5 + 3) // 4
    monkeypatch.setattr(
        "debate_core.application.caselist.backfile_import.read_volume",
        lambda _: VolumeReading(total_bytes=10 * required, used_bytes=10 * required - (required - 1)),
    )

    planned = dry_run(world)

    assert refusals(planned) == ["NOT_ENOUGH_FREE_SPACE"]
    message = planned["error"]["message"]
    assert f"{required - 1:,}" in message and f"{required:,}" in message
    assert refusals(execute(world)) == ["NOT_ENOUGH_FREE_SPACE"]
    assert site.fetched == []


def test_a_caselist_not_on_the_list_is_refused(backfiles: tuple[World, Site]) -> None:
    world, site = backfiles

    assert refusals(dry_run(world, "testcl26")) == ["NOT_A_BACKFILE"]
    assert refusals(execute(world, "testcl23")) == ["NOT_A_BACKFILE"]
    assert site.fetched == []


def test_a_caselist_with_no_complete_archive_is_refused(backfiles: tuple[World, Site]) -> None:
    world, site = backfiles
    world.site.get(f"{API}/caselists/{OTHER_BACKFILE}/downloads").respond(
        200,
        json=[
            {"name": "testcl24-weekly-2025-06-24.zip", "url": f"{FILE_HOST}/testcl24-weekly-2025-06-24.zip"}
        ],
    )

    assert refusals(dry_run(world, OTHER_BACKFILE)) == ["NO_COMPLETE_ARCHIVE"]
    assert site.fetched == []


def test_a_bucket_not_yet_seeded_is_refused(world: World, tmp_path: Path) -> None:
    world.mode("bucket")
    world.monkeypatch.setenv("DEBATE_CASELIST__BACKFILE_CASELISTS", json.dumps([BACKFILE]))
    world.clock.now = ON_A_THURSDAY
    Site(world).offer(BACKFILE, (ARCHIVE_DATE, zipped(MEMBERS)))

    assert refusals(dry_run(world)) == ["RUN_STATE_NOT_SEEDED"]


def test_local_mode_is_refused_because_the_ledger_and_the_lock_are_the_buckets(world: World) -> None:
    world.monkeypatch.setenv("DEBATE_CASELIST__BACKFILE_CASELISTS", json.dumps([BACKFILE]))
    world.clock.now = ON_A_THURSDAY
    Site(world).offer(BACKFILE, (ARCHIVE_DATE, zipped(MEMBERS)))

    assert "NOT_IN_BUCKET_MODE" in refusals(dry_run(world))


def test_a_bundle_a_removal_rewrote_during_the_import_is_never_overwritten(
    backfiles: tuple[World, Site],
) -> None:
    world, site = backfiles

    def rewrite_the_bundle() -> None:
        world.client.copy_object(
            Bucket=world.bucket,
            Key=RUN_STATE_BUNDLE_KEY,
            CopySource={"Bucket": world.bucket, "Key": RUN_STATE_BUNDLE_KEY},
            Metadata={"rewritten": "by a removal"},
            MetadataDirective="REPLACE",
        )

    site.while_fetching.append(rewrite_the_bundle)

    imported = execute(world)

    assert imported["exit_code"] == ExitCode.DOMAIN_FAILURE, imported
    assert imported["error"]["code"] == "BUNDLE_CHANGED_SINCE_RESTORE"
    assert world.object_keys(f"manifests/{BACKFILE}/") == set(), "nothing published"
    head = world.client.head_object(Bucket=world.bucket, Key=RUN_STATE_BUNDLE_KEY)
    assert head["Metadata"] == {"rewritten": "by a removal"}, "the removal's bundle is still the bucket's"
    assert world.lock()["state"] == "free"


# ------------------------------------------------------------------------------------------------
# The marker, everywhere else
# ------------------------------------------------------------------------------------------------


def test_pull_refuses_a_backfile_by_name_or_as_its_complete_archive(backfiles: tuple[World, Site]) -> None:
    world, site = backfiles

    for arguments in (("--caselist", BACKFILE), ("--caselist", "testcl26", "--full-archive", BACKFILE)):
        pulled = world.run("caselist", "pull", *arguments, "--dry-run")
        assert pulled["exit_code"] != ExitCode.OK, pulled
        assert pulled["error"]["code"] == "BACKFILE_IS_NOT_PULLED", pulled
    assert not [call for call in world.site.calls if f"/caselists/{BACKFILE}/" in str(call.request.url)]
    assert site.fetched == []


def test_a_profile_naming_a_backfile_among_the_weekly_caselists_is_refused(
    backfiles: tuple[World, Site],
) -> None:
    world, _ = backfiles
    world.monkeypatch.setenv("DEBATE_CASELIST__SYNC_CASELISTS", json.dumps(["testcl26", BACKFILE]))

    refused = world.run("caselist", "pull", "--dry-run")

    assert refused["exit_code"] != ExitCode.OK
    assert f"both name {BACKFILE}" in refused["error"]["message"]


def test_the_landscape_refuses_a_backfile(backfiles: tuple[World, Site]) -> None:
    world, _ = backfiles
    assert execute(world)["exit_code"] == ExitCode.OK

    refused = world.run("landscape", "report", "--caselist", BACKFILE)

    assert refused["exit_code"] != ExitCode.OK
    assert refused["error"]["code"] == "BACKFILE_HAS_NO_LANDSCAPE", refused


# ------------------------------------------------------------------------------------------------
# Removal, the suppression list and holds reach a backfile as they reach the current season
# ------------------------------------------------------------------------------------------------


def test_a_removal_reaches_a_backfiles_manifest_and_its_bytes(
    backfiles: tuple[World, Site], tmp_path: Path
) -> None:
    world, _ = backfiles
    assert execute(world)["exit_code"] == ExitCode.OK
    world.use(tmp_path / "the-macs-copy")
    removed_digest = digest_of("direct")

    removed = world.run(
        "caselist", "remove", "--source", removed_digest, "--reason", "REQUESTED_BY_TEAM",
        "--request", "RM-2026-04", "--execute",
    )  # fmt: skip

    assert removed["exit_code"] == ExitCode.OK, removed
    assert removed_digest not in {row["sha256"] for row in member_rows(world)}
    assert not [key for key in world.object_keys(f"raw/caselist/{BACKFILE}/") if key.endswith(removed_digest)]
    assert not [
        key for key in world.object_keys(f"parsed/{BACKFILE}/") if key.endswith(f"{removed_digest}.jsonl")
    ]
    assert removed_digest.encode() not in gzip.decompress(world.body(RUN_STATE_BUNDLE_KEY))


def test_a_source_on_the_suppression_list_is_not_brought_back_by_a_backfile(
    backfiles: tuple[World, Site], tmp_path: Path
) -> None:
    world, _ = backfiles
    world.use(tmp_path / "the-macs-copy")
    suppressed_digest = digest_of("wiki")
    removed = world.run(
        "caselist", "remove", "--source", suppressed_digest, "--reason", "REQUESTED_BY_TEAM",
        "--request", "RM-2026-05", "--execute",
    )  # fmt: skip
    assert removed["exit_code"] == ExitCode.OK, removed
    world.use(tmp_path / "cloud-task-after")

    imported = execute(world)

    assert imported["exit_code"] == ExitCode.OK, imported
    assert imported["data"]["import"]["suppressed"] == 1
    assert suppressed_digest not in {row.get("sha256") for row in member_rows(world)}
    assert not [
        key for key in world.object_keys(f"raw/caselist/{BACKFILE}/") if key.endswith(suppressed_digest)
    ]


def test_a_path_a_removal_holds_holds_a_later_complete_archive_of_the_backfile(
    backfiles: tuple[World, Site], tmp_path: Path
) -> None:
    """A whole-file removal by `--source` holds the path it took the file from (`v1-e30-t13`): new bytes
    there, in a later complete archive of the backfile, are refused and counted under the request."""
    world, site = backfiles
    assert execute(world)["exit_code"] == ExitCode.OK
    world.use(tmp_path / "the-macs-copy")
    removed = world.run(
        "caselist", "remove", "--source", digest_of("direct"), "--reason", "REQUESTED_BY_TEAM",
        "--request", "RM-2026-06", "--execute",
    )  # fmt: skip
    assert removed["exit_code"] == ExitCode.OK, removed
    later = {R1: BODIES["verbatim"], R2: BODIES["wiki"], R6: BODIES["cardmirror"]}
    site.offer(BACKFILE, (ARCHIVE_DATE, zipped(MEMBERS)), (LATER_ARCHIVE_DATE, zipped(later)))
    world.clock.advance(timedelta(days=2))
    world.use(tmp_path / "cloud-task-later")

    imported = execute(world)

    assert imported["exit_code"] == ExitCode.OK, json.dumps(imported.get("error"))[:1500]
    assert imported["data"]["archive_date"] == LATER_ARCHIVE_DATE.isoformat()
    assert imported["data"]["import"]["held_by_request"] == {"RM-2026-06": 1}
    later_key = f"manifests/{BACKFILE}/{LATER_ARCHIVE_DATE.isoformat()}.jsonl"
    assert digest_of("cardmirror") not in {row.get("sha256") for row in member_rows(world, later_key)}


def test_an_upload_a_backfile_import_refused_at_a_held_path_is_found_from_another_data_directory(
    backfiles: tuple[World, Site], tmp_path: Path
) -> None:
    """The task's working copy goes with it; the held-digest record reaches the bucket (`v1-e40-t12`).

    The import is the unlocked step, so the record is given to the bucket at the locked step's save
    of the bundle. A backfile import never runs the search index stage, whose reconcile was the only
    other way the record reached the bucket, so before `v1-e40-t12` it stayed in the task's copy."""
    world, site = backfiles
    assert execute(world)["exit_code"] == ExitCode.OK
    macs_copy = tmp_path / "the-macs-copy"
    world.use(macs_copy)
    remove = ("caselist", "remove", "--source", digest_of("direct"), "--reason", "REQUESTED_BY_TEAM")
    remove = (*remove, "--request", "RM-2026-06")
    assert world.run(*remove, "--execute")["exit_code"] == ExitCode.OK
    later = {R1: BODIES["verbatim"], R2: BODIES["wiki"], R6: BODIES["cardmirror"]}
    site.offer(BACKFILE, (ARCHIVE_DATE, zipped(MEMBERS)), (LATER_ARCHIVE_DATE, zipped(later)))
    world.clock.advance(timedelta(days=2))
    cloud = world.use(tmp_path / "cloud-task-later")
    imported = execute(world)
    assert imported["exit_code"] == ExitCode.OK, json.dumps(imported.get("error"))[:800]
    held = (cloud / "suppression" / "held-digests.jsonl").read_text(encoding="utf-8")
    assert digest_of("cardmirror") in held, "the premise: the task's import refused it, and recorded it"
    shutil.rmtree(cloud)
    world.use(macs_copy)

    status = world.run("caselist", "status", "--caselist", BACKFILE)
    planned = world.run(*remove)

    report = status["data"] if status["data"] is not None else status["error"]["details"]
    refused = {one["caselist"]: one for one in report["refused_at_import"]}[BACKFILE]
    assert refused["uploads"] == 1, refused
    assert refused["requests"] == ["RM-2026-06"]
    assert planned["exit_code"] == ExitCode.OK, planned
    sources = {one["sha256"]: one for one in planned["data"]["sources"]}
    assert sources[digest_of("cardmirror")]["inclusion"] == "held_at_import", sorted(sources)


# ------------------------------------------------------------------------------------------------
# The command a cloud task is started with (v1-e40-t09)
# ------------------------------------------------------------------------------------------------
#
# ops/caselist_run/start_backfile_import.py starts the run's task definition with its command
# overridden. These run that very command, as the script builds it, through the CLI over the stand-in
# bucket and site: the budget and the window are the command's own refusals in the task, and its
# result is never a weekly run's (the PM's rulings of 2026-10-27).

START_SCRIPT: Final = (
    Path(__file__).resolve().parents[4] / "ops" / "caselist_run" / "start_backfile_import.py"
)


def start_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("start_backfile_import", START_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def cloud_command(caselist: str, *, execute: bool = True) -> list[str]:
    """The container's command as the script starts it, less the `--json` the world adds itself."""
    started = start_script().import_command(caselist, execute=execute, environment="dev")
    assert started[0] == "--json"
    return list(started[1:])


def test_the_command_a_cloud_task_is_started_with_refuses_inside_the_window_before_any_download(
    backfiles: tuple[World, Site],
) -> None:
    world, site = backfiles
    world.clock.now = ON_A_WEDNESDAY

    assert refusals(world.run(*cloud_command(BACKFILE))) == ["INSIDE_NO_IMPORT_WINDOW"]
    assert refusals(world.run(*cloud_command(BACKFILE, execute=False))) == ["INSIDE_NO_IMPORT_WINDOW"]
    assert site.fetched == []
    assert BACKFILE_LEDGER_KEY not in world.object_keys("reports/sync/state/"), "no budget was spent"
    assert world.object_keys(f"manifests/{BACKFILE}/") == set()


def test_the_command_a_cloud_task_is_started_with_refuses_without_budget_before_any_download(
    backfiles: tuple[World, Site], tmp_path: Path
) -> None:
    world, site = backfiles
    assert world.run(*cloud_command(BACKFILE))["exit_code"] == ExitCode.OK
    world.use(tmp_path / "the-next-task")
    world.clock.advance(timedelta(hours=23, minutes=59))

    assert refusals(world.run(*cloud_command(OTHER_BACKFILE))) == ["BACKFILE_BUDGET_SPENT"]
    assert len(site.fetched) == 1, "only the first import downloaded"
    assert world.object_keys(f"manifests/{OTHER_BACKFILE}/") == set()


def test_what_a_cloud_import_prints_is_never_counted_as_a_weekly_run(backfiles: tuple[World, Site]) -> None:
    """The late-run alarm counts `caselist pull` envelopes that carry a run record
    (infrastructure/modules/caselist_run/alerts.tf, `runs_recorded`): an import's is neither."""
    world, _ = backfiles
    runs_before = world.object_keys("reports/sync-runs/")

    planned = world.run(*cloud_command(BACKFILE, execute=False))
    imported = world.run(*cloud_command(BACKFILE))

    for envelope in (planned, imported):
        assert envelope["exit_code"] == ExitCode.OK, envelope
        assert envelope["command"] == "caselist backfile-import"
        assert "run_record" not in json.dumps(envelope)
    assert world.object_keys("reports/sync-runs/") == runs_before, "no run record published"

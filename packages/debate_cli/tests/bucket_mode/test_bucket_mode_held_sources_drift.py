"""A cloud run that touches a camp release whose older files only the bucket holds (`v1-e40-t13`).

The first dev cloud run (`20261026T040426Z`) ended `incomplete`, with `CASELIST_DRIFT` on its
OpenEv camp release, and retention kept that night's camp download, though the bucket held every
source of the release and its manifest. The run's working copy was restored without raw sources,
and it held only the camp file it downloaded that night. Here the same week, in miniature: the Mac
pulls one camp file and seeds the bucket, and a run in bucket mode on an empty data directory then
finds a second file joining the same release.

The world is `conftest.py`'s: moto's S3, the fictional site, the real pipeline and composition root.
"""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from pathlib import Path
from typing import Any, Final

import httpx
from tests.fixtures.parse_pipeline.build_parse_world import BODIES, WEEKS

from debate_cli.exit_codes import ExitCode

World = Any
"""`conftest.py`'s world, which a test module cannot import by name."""

API: Final = "https://api.opencaselist.example.invalid/v1"
WEEK_1, WEEK_2, _ = (week.snapshot for week in WEEKS)
RELEASE: Final = "2026-policy"
"""The camp release both camp files are filed under: `<year>-<event>`."""
RELEASE_MANIFEST: Final = f"manifests/openev/{RELEASE}.jsonl"

FIRST_CAMP_FILE: Final = {
    "openev_id": 512,
    "path": "/openev/2026/Tamarack/TSF-Estuary Solvency Advocate.docx",
    "filename": "TSF-Estuary Solvency Advocate.docx",
    "year": 2026,
    "camp": "Tamarack",
    "tags": {"policy": True},
}
"""`conftest.py`'s one camp file, which the Mac pulls."""
JOINING_CAMP_FILE: Final = {
    **FIRST_CAMP_FILE,
    "openev_id": 513,
    "path": "/openev/2026/Tamarack/TSF-Kelp Inherency.docx",
    "filename": "TSF-Kelp Inherency.docx",
}
"""An invented second file of the same camp and event, with other bytes: it joins the release."""
JOINING_BODY: Final = BODIES["verbatim"]
FIRST_DIGEST: Final = hashlib.sha256(BODIES["cardmirror"]).hexdigest()


def stage(envelope: dict[str, Any], name: str) -> dict[str, Any]:
    summary = envelope["data"] or envelope["error"]["details"]
    [found] = [one for one in summary["stages"] if one["stage"] == name]
    return found


def a_camp_file_joins_on_an_empty_directory(world: World, tmp_path: Path) -> Path:
    """The Mac's pull of one camp file, the bucket seeded from it, then a second file listed."""
    world.listing(WEEK_1, WEEK_2)
    assert world.pull()["exit_code"] == ExitCode.OK
    world.seed()
    world.clock.advance(timedelta(days=7))
    world.site.get(f"{API}/openev").respond(200, json=[FIRST_CAMP_FILE, JOINING_CAMP_FILE])

    def download(request: httpx.Request) -> httpx.Response:
        # The client sends the listed path without its leading `/`, as the API asks.
        joining = request.url.params["path"] == str(JOINING_CAMP_FILE["path"]).lstrip("/")
        return httpx.Response(200, content=JOINING_BODY if joining else BODIES["cardmirror"])

    world.site.get(f"{API}/download").mock(side_effect=download)
    return world.use(tmp_path / "empty")


def test_a_release_whose_older_sources_only_the_bucket_holds_is_no_drift_and_the_run_completes(
    world: World, tmp_path: Path
) -> None:
    empty = a_camp_file_joins_on_an_empty_directory(world, tmp_path)

    pulled = world.pull()

    assert pulled["exit_code"] == ExitCode.OK, pulled
    report = stage(pulled, "report")
    assert report["outcome"] == "completed", report
    assert report["reason"] == "1 snapshot(s) confirmed in the bucket"
    assert report["drift"] == []
    retention = pulled["data"]["inbox_retention"]
    assert [one["kind"] for one in retention["removed"]] == ["camp_download"], retention
    assert retention["kept"] == []
    record, details = world.last_record(empty)
    assert record["outcome"] == "completed", record
    assert details["failure_codes"] == []
    assert not (empty / "blobs" / "sha256" / FIRST_DIGEST[0:2] / FIRST_DIGEST[2:4] / FIRST_DIGEST).exists(), (
        "the premise: the older camp file is held only in the bucket"
    )


def test_a_new_file_joining_sources_only_the_bucket_holds_publishes(world: World, tmp_path: Path) -> None:
    """The publish plan verifies a source the bucket lists before it asks this machine for it."""
    a_camp_file_joins_on_an_empty_directory(world, tmp_path)
    joining = hashlib.sha256(JOINING_BODY).hexdigest()

    pulled = world.pull()

    publish = stage(pulled, "publish")
    assert publish["outcome"] == "completed", publish
    assert publish["reason"] == "2 object(s) uploaded across 1 snapshot(s): 1 source(s) and 1 manifest(s)"
    named = {json.loads(line).get("sha256") for line in world.body(RELEASE_MANIFEST).splitlines()}
    assert {FIRST_DIGEST, joining} <= named
    assert f"raw/openev/2026/sha256/{joining[0:2]}/{joining[2:4]}/{joining}" in world.object_keys("raw/")


def test_caselist_status_counts_the_held_sources_present_in_bucket_mode_and_shows_them(
    world: World, tmp_path: Path
) -> None:
    a_camp_file_joins_on_an_empty_directory(world, tmp_path)
    assert world.pull()["exit_code"] == ExitCode.OK

    in_bucket_mode = world.run("caselist", "status", "--caselist", "openev")
    shown = world.invoke("caselist", "status", "--caselist", "openev")

    assert in_bucket_mode["exit_code"] == ExitCode.OK, in_bucket_mode
    [entry] = [one for one in in_bucket_mode["data"]["snapshots"] if one["snapshot"] == RELEASE]
    assert entry["in_sync"] is True
    assert entry["local_files"] == 1, "the joining file, which this run downloaded"
    assert entry["sources"] == 2
    assert entry["missing_local"] == []
    assert entry["held_only_in_bucket"] == 1
    caption = " ".join(shown.stdout.split())
    assert f"Raw sources held only in the bucket: 1 in openev {RELEASE}" in caption, caption


def test_the_same_working_copy_in_local_mode_is_drift_as_it_always_was(world: World, tmp_path: Path) -> None:
    a_camp_file_joins_on_an_empty_directory(world, tmp_path)
    assert world.pull()["exit_code"] == ExitCode.OK
    world.mode("local")

    in_local_mode = world.run("caselist", "status", "--caselist", "openev")

    assert in_local_mode["exit_code"] != ExitCode.OK
    assert in_local_mode["error"]["code"] == "CASELIST_DRIFT"
    [entry] = [one for one in in_local_mode["error"]["details"]["snapshots"] if one["snapshot"] == RELEASE]
    assert entry["missing_local"] == [FIRST_DIGEST]
    assert "held_only_in_bucket" not in entry, "local mode's output is unchanged"

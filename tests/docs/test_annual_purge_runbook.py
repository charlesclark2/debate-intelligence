"""The annual purge runbook's listings, run on synthetic stores, and its shape (`v1-e30-t28`).

`docs/runbooks/annual-purge.md` is run by the operator against both buckets and this Mac. Its dry runs
and checks are Python scripts in quoted heredocs: the inventory that judges each caselist by the
build's `caselist.backfile_caselists` and its dates, the school-view listing moved from the removal
runbook, the expired-version check, and the read of built files' sidecars. Each test takes a script out
of the runbook as written and runs it as the operator does (`python3 -I -`, or the file the window
writes), so a change to the runbook is what is tested.

Every slug, key, version id and date here is invented: no school, team code or real path.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Final

import pytest

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
RUNBOOK: Final = REPO_ROOT / "docs" / "runbooks" / "annual-purge.md"
REMOVAL_RUNBOOK: Final = REPO_ROOT / "docs" / "runbooks" / "caselist-removal.md"
POLICY: Final = REPO_ROOT / "docs" / "policies" / "caselist-data-use.md"
WINDOW_START: Final = "2026-08-01"
BACKFILE: Final = "samplecl25"
CURRENT: Final = "samplecl26"


def heredoc(marker: str) -> str:
    """The Python between `<<'MARKER'` and its closing `MARKER` line in the runbook."""
    [found] = re.findall(rf"<<'{marker}'\n(.*?)\n{marker}\n", RUNBOOK.read_text(encoding="utf-8"), re.DOTALL)
    return found


def shell_blocks(path: Path) -> list[str]:
    return re.findall(r"^```bash\n(.*?)^```$", path.read_text(encoding="utf-8"), re.DOTALL | re.MULTILINE)


def run_script(marker: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-I", "-", *args], input=heredoc(marker), capture_output=True, text=True, check=False
    )


# --- The inventory ---------------------------------------------------------------------------


@pytest.fixture
def settings(tmp_path: Path) -> Path:
    """`config show --json` as the window saves it: the build's backfile list, nothing else needed."""
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "data": {
                    "environment": "dev",
                    "settings": {
                        "caselist.backfile_caselists": [BACKFILE],
                        "caselist.sync_caselists": [CURRENT],
                        "storage.data_dir": str(tmp_path / "data"),
                        "caselist.inbox_dir": None,
                    },
                }
            }
        )
    )
    return path


def inventory(tmp_path: Path, settings: Path, label: str, listed: list[str], *dating: list[str]) -> list[str]:
    script = tmp_path / "inventory.py"
    script.write_text(heredoc("INVENTORY"))
    files = []
    for number, lines in enumerate([listed, *dating]):
        listing = tmp_path / f"listing-{number}.txt"
        listing.write_text("".join(f"{line}\n" for line in lines))
        files.append(str(listing))
    ran = subprocess.run(
        [sys.executable, "-I", str(script), str(settings), WINDOW_START, label, *files],
        capture_output=True,
        text=True,
        check=False,
    )
    assert ran.returncode == 0, ran.stderr
    return ran.stdout.splitlines()


def test_inventory_keeps_the_window_and_the_backfiles_and_ends_ok(tmp_path: Path, settings: Path) -> None:
    lines = inventory(
        tmp_path,
        settings,
        "bucket",
        [
            f"manifests/{CURRENT}/2026-08-04.jsonl",
            f"manifests/{CURRENT}/2027-07-27.jsonl",
            f"manifests/{BACKFILE}/2026-06-30.jsonl",
            f"manifests/{BACKFILE}/full/2026-06-30.jsonl",
            "manifests/openev/2026-policy.jsonl",
            "manifests/_suppression/suppression-list.jsonl",
            "manifests/_run-state/run-state.tar.gz",
        ],
    )
    assert lines == [
        f"bucket: {BACKFILE} KEEP backfile (2 item(s) here; dated 2026-06-30 to 2026-06-30)",
        f"bucket: {CURRENT} KEEP in the window (2 item(s) here; dated 2026-08-04 to 2027-07-27)",
        "bucket: openev 2026 KEEP in the window (1 release(s))",
        "bucket: 3 kept, 0 to purge, 0 stop(s)",
        "bucket: INVENTORY OK",
    ]


def test_inventory_reads_backfiles_from_the_setting_never_from_the_slug(tmp_path: Path, settings: Path) -> None:
    """Two caselists of one aged-out season: the setting names one, so only that one is a backfile."""
    lines = inventory(
        tmp_path,
        settings,
        "bucket",
        [f"manifests/{BACKFILE}/2026-06-30.jsonl", "manifests/othercl25/2026-06-30.jsonl"],
    )
    assert f"bucket: {BACKFILE} KEEP backfile (1 item(s) here; dated 2026-06-30 to 2026-06-30)" in lines
    assert (
        "bucket: othercl25 STOP aged out of the window from 2021-22 on, and not in caselist.backfile_caselists "
        "(1 item(s) here; dated 2026-06-30 to 2026-06-30)"
    ) in lines
    assert lines[-1] == "bucket: INVENTORY STOPS"


def test_inventory_purges_only_before_2021_22_and_judges_camp_years_by_topic_year(
    tmp_path: Path, settings: Path
) -> None:
    lines = inventory(
        tmp_path,
        settings,
        "bucket",
        [
            "manifests/oldcl21/2021-07-31.jsonl",
            "manifests/firstcl22/2021-08-01.jsonl",
            "manifests/openev/2020-policy.jsonl",
            "manifests/openev/2021-ld.jsonl",
            "manifests/openev/2025-policy.jsonl",
            "manifests/openev/2026-ld.jsonl",
        ],
    )
    assert "bucket: oldcl21 PURGE before 2021-22 (1 item(s) here; dated 2021-07-31 to 2021-07-31)" in lines
    assert any(line.startswith("bucket: firstcl22 STOP aged out of the window from 2021-22 on") for line in lines)
    assert "bucket: openev 2020 PURGE before 2021-22 (1 release(s))" in lines
    assert "bucket: openev 2021 KEEP aged out, kept as a backfile (1 release(s))" in lines
    assert "bucket: openev 2025 KEEP aged out, kept as a backfile (1 release(s))" in lines
    assert "bucket: openev 2026 KEEP in the window (1 release(s))" in lines
    assert "bucket: 3 kept, 2 to purge, 1 stop(s)" in lines


def test_inventory_window_starts_on_its_own_date(tmp_path: Path, settings: Path) -> None:
    on = inventory(tmp_path, settings, "bucket", [f"manifests/{CURRENT}/{WINDOW_START}.jsonl"])
    before = inventory(tmp_path, settings, "bucket", [f"manifests/{CURRENT}/2026-07-31.jsonl"])
    assert on[0].startswith(f"bucket: {CURRENT} KEEP in the window")
    assert before[0].startswith(f"bucket: {CURRENT} STOP aged out of the window")


def test_inventory_stops_on_a_backfile_dated_before_2021_22(tmp_path: Path, settings: Path) -> None:
    lines = inventory(tmp_path, settings, "bucket", [f"manifests/{BACKFILE}/2020-06-30.jsonl"])
    assert lines[0].startswith(f"bucket: {BACKFILE} STOP a backfile dated before 2021-22")


def test_inventory_dates_this_macs_stores_and_inbox_by_the_manifests(tmp_path: Path, settings: Path) -> None:
    """Prod's own data directory holds no manifests: its parsed store is dated by the bucket's."""
    lines = inventory(
        tmp_path,
        settings,
        "local",
        [
            f"parsed/{CURRENT}",
            f"landscape/classifications/{CURRENT}.jsonl",
            f"landscape/local-classifier/{CURRENT}",
            f"landscape/review/{CURRENT}",
            "landscape/model-cassettes/a-prompt",
            f"reports/landscape/{CURRENT}/2026-10-20",
            f"reports/landscape/{CURRENT}/.DS_Store",
            f"inbox/{CURRENT}-weekly-2026-10-21.zip",
            "inbox/openev-123-a-camp-file.docx",
            "inbox/.partial",
            "parsed/openev",
        ],
        [f"manifests/{CURRENT}/2026-08-04.jsonl", "manifests/openev/2026-policy.jsonl"],
    )
    assert lines == [
        f"local: {CURRENT} KEEP in the window (6 item(s) here; dated 2026-08-04 to 2026-10-21)",
        "local: openev KEEP 2 item(s) here, dated by the releases above or in the bucket",
        "local: 2 kept, 0 to purge, 0 stop(s)",
        "local: INVENTORY OK",
    ]


def test_inventory_stops_on_what_nothing_dates_and_on_keys_it_does_not_know(
    tmp_path: Path, settings: Path
) -> None:
    lines = inventory(
        tmp_path,
        settings,
        "local",
        ["parsed/testcl26", "parsed/openev", "manifests/samplecl26/latest.jsonl"],
    )
    assert lines[0].startswith("local: testcl26 STOP not a backfile, and no manifest, bundle or inbox archive dates it")
    assert "local: openev STOP 1 item(s) here, and no camp release dates them" in lines
    assert "local: STOP manifests/samplecl26/latest.jsonl is not a key this runbook knows" in lines
    assert lines[-1] == "local: INVENTORY STOPS"


def test_inventory_reads_the_bundles_member_names(tmp_path: Path, settings: Path) -> None:
    lines = inventory(
        tmp_path,
        settings,
        "bundle",
        [f"objects/manifests/{CURRENT}/2026-09-01.jsonl", "debate.sqlite3"],
    )
    assert lines[-1] == "bundle: INVENTORY OK"


def test_inventory_of_nothing_is_empty_not_ok(tmp_path: Path, settings: Path) -> None:
    assert inventory(tmp_path, settings, "bucket", [])[-1] == "bucket: INVENTORY EMPTY"


# --- The school views, moved from the removal runbook -----------------------------------------


def version(key: str, version_id: str, *, latest: bool = True) -> dict[str, Any]:
    return {"Key": key, "VersionId": version_id, "IsLatest": latest}


def school_views(tmp_path: Path, versions: list[dict[str, Any]], markers: list[dict[str, Any]]) -> Any:
    purge = tmp_path / "views"
    purge.mkdir(exist_ok=True)
    (purge / "versions.json").write_text(json.dumps({"Versions": versions, "DeleteMarkers": markers}))
    return run_script("SCHOOLVIEWS", str(purge), str(tmp_path / "data"), WINDOW_START)


def requested(tmp_path: Path) -> list[tuple[str, str]]:
    return sorted(
        (one["Key"], one["VersionId"])
        for request in sorted((tmp_path / "views").glob("delete-*.json"))
        for one in json.loads(request.read_text())["Objects"]
    )


def test_school_views_before_the_window_go_every_version_and_circuit_wide_files_stay(tmp_path: Path) -> None:
    old, new = f"reports/landscape/{CURRENT}/2026-07-28", f"reports/landscape/{CURRENT}/2026-08-04"
    local = tmp_path / "data" / old
    local.mkdir(parents=True)
    for name in ("schools.csv", "report.md"):
        (local / name).write_text("synthetic")
    (tmp_path / "data" / new).mkdir(parents=True)
    (tmp_path / "data" / new / "schools.md").write_text("synthetic")
    ran = school_views(
        tmp_path,
        [
            version(f"{old}/schools.csv", "a2"),
            version(f"{old}/schools.csv", "a1", latest=False),
            version(f"{old}/report.md", "b1"),
            version(f"{old}/trends.csv", "c1"),
            version(f"{new}/schools.csv", "d1"),
            version(f"{new}/schools.md", "e1"),
        ],
        [version(f"{old}/schools.md", "m1")],
    )
    assert ran.returncode == 0, ran.stderr
    assert requested(tmp_path) == [
        (f"{old}/schools.csv", "a1"),
        (f"{old}/schools.csv", "a2"),
        (f"{old}/schools.md", "m1"),
    ]
    assert (tmp_path / "views" / "local.txt").read_text().splitlines() == [str(local / "schools.csv")]
    assert ran.stdout.splitlines()[-1] == "3 bucket version(s) and 1 local file(s) to delete, of 2 bundle(s) listed in the bucket"


def test_school_views_stop_on_a_file_neither_list_names_and_write_nothing(tmp_path: Path) -> None:
    ran = school_views(
        tmp_path,
        [
            version(f"reports/landscape/{CURRENT}/2026-07-28/schools.csv", "a1"),
            version(f"reports/landscape/{CURRENT}/2026-07-28/report.html", "b1"),
        ],
        [],
    )
    assert ran.returncode == 1
    assert "neither a school view nor a circuit-wide file" in ran.stderr
    assert not list((tmp_path / "views").glob("delete-*.json"))
    assert not (tmp_path / "views" / "local.txt").exists()


def test_school_views_split_requests_at_a_thousand(tmp_path: Path) -> None:
    key = f"reports/landscape/{CURRENT}/2026-07-28/schools.csv"
    ran = school_views(tmp_path, [version(key, f"v{n}", latest=n == 0) for n in range(1001)], [])
    assert ran.returncode == 0, ran.stderr
    sizes = [len(json.loads(one.read_text())["Objects"]) for one in sorted((tmp_path / "views").glob("delete-*.json"))]
    assert sizes == [1000, 1]


# --- Expired noncurrent versions --------------------------------------------------------------


def stamped(key: str, version_id: str, modified: str, *, latest: bool = False) -> dict[str, Any]:
    return {"Key": key, "VersionId": version_id, "IsLatest": latest, "LastModified": modified}


def expired(tmp_path: Path, listings: dict[str, dict[str, Any]], retention: int = 30) -> list[str]:
    for name, body in listings.items():
        (tmp_path / f"versions-{name}.json").write_text(json.dumps(body))
    ran = run_script("EXPIRED", str(tmp_path), str(retention), "2027-09-10T12:00:00+00:00")
    assert ran.returncode == 0, ran.stderr
    return ran.stdout.splitlines()


def test_expired_counts_from_when_a_version_became_noncurrent(tmp_path: Path) -> None:
    """Noncurrent since the newer version's write: 40 days is past 30 and two, 31 days is not yet."""
    lines = expired(
        tmp_path,
        {
            "raw": {
                "Versions": [
                    stamped("raw/a", "a3", "2027-08-30T00:00:00Z", latest=True),
                    stamped("raw/a", "a2", "2027-08-01T00:00:00Z"),
                    stamped("raw/a", "a1", "2026-01-01T00:00:00Z"),
                    stamped("raw/b", "b1", "2025-01-01T00:00:00Z", latest=True),
                ]
            },
            "manifests": {
                "Versions": [stamped("manifests/c", "c1", "2027-01-01T00:00:00Z")],
                "DeleteMarkers": [stamped("manifests/c", "m1", "2027-08-10T00:00:00Z", latest=True)],
            },
        },
    )
    assert lines == [
        "manifests: 1 key(s), 0 noncurrent past 30 days",
        "raw: 2 key(s), 1 noncurrent past 30 days, the oldest noncurrent since 2027-08-01",
        "3 key(s), 3 noncurrent version(s) and delete marker(s), 1 past the lifecycle's 30 days and two more",
        "EXPIRED STOPS",
    ]


def test_expired_is_ok_within_the_age_and_empty_when_nothing_was_listed(tmp_path: Path) -> None:
    current_only = {"Versions": [stamped("parsed/a", "a1", "2020-01-01T00:00:00Z", latest=True)]}
    assert expired(tmp_path, {"parsed": current_only}, retention=365)[-1] == "EXPIRED OK"
    empty = tmp_path / "empty"
    empty.mkdir()
    (empty / "versions-raw.json").write_text("")
    ran = run_script("EXPIRED", str(empty), "30")
    assert ran.stdout.splitlines()[-1] == "EXPIRED EMPTY"


# --- Built files' sidecars --------------------------------------------------------------------


def test_sidecars_name_every_caselist_their_cards_cite(tmp_path: Path) -> None:
    sidecar = tmp_path / "file.provenance.json"
    sidecar.write_text(
        json.dumps({"cards": [{"caselist": CURRENT, "camp": None}, {"source": {"caselist": "openev"}}], "event": "LD"})
    )
    listing = tmp_path / "sidecars.txt"
    listing.write_text(f"{sidecar}\n")
    ran = run_script("SIDECARS", str(listing))
    assert ran.returncode == 0, ran.stderr
    assert ran.stdout.splitlines() == ["parsed/openev", f"parsed/{CURRENT}"]


# --- The runbook's shape ----------------------------------------------------------------------


def test_every_block_that_reaches_a_bucket_checks_the_day_the_lock_and_the_shell_first() -> None:
    blocks = shell_blocks(RUNBOOK)
    reaching = [block for block in blocks if re.search(r"\baws s3|debate-research --json store", block)]
    unguarded = [block.splitlines()[0] for block in reaching if "purge_guard() {" not in block and "if purge_guard; then" not in block]
    assert len(reaching) >= 8
    assert unguarded == []


def test_the_guard_refuses_a_wednesday_a_held_lock_and_an_override() -> None:
    [window] = [block for block in shell_blocks(RUNBOOK) if "purge_guard() {" in block]
    guard = window.split("purge_guard() {", 1)[1].split("\n  }\n", 1)[0]
    assert '"$(date +%A)" = "Wednesday"' in guard
    assert "reports/sync/run-lock.json" in guard and '"$LOCK_STATE" = "free"' in guard
    assert "^DEBATE_" in guard and "caselist (pull|backfile-import)" in guard


def test_no_block_holds_an_exclamation_mark() -> None:
    """Pasted into interactive zsh, a `!` can start a history expansion (the PM, 2026-10-28)."""
    assert [block.splitlines()[0] for block in shell_blocks(RUNBOOK) if "!" in block] == []


def test_the_removal_runbook_points_here_and_keeps_no_purge_code() -> None:
    text = REMOVAL_RUNBOOK.read_text(encoding="utf-8")
    section = text.split("## The annual purge: landscape school views\n", 1)[1].split("\n## ", 1)[0]
    assert "annual-purge.md#step-2--landscape-school-views" in section
    assert "```" not in section
    assert "SEASON_START" not in text and "landscape-school-view-purge" not in text


RETENTION_ROWS: Final = {
    "Weekly caselist snapshots": "Weekly caselist snapshots",
    "Backfiles": "Backfiles",
    "Parsed cards, fingerprints and classifications": "Parsed cards, fingerprints and classifications",
    "OpenEv camp files": "OpenEv camp files",
    "Per-school landscape views": "Per-school landscape views",
    "Circuit-wide landscape reports": "Circuit-wide landscape reports",
    "Team files built from disclosed cards": "Team files built from disclosed cards",
    "The student search pilot's index": "The student search pilot's index",
    "The student search pilot's access audit": "The pilot's access audit",
    "The weekly cloud run's working copy": "The weekly cloud run's and a backfile import's working copies",
    "A one-off backfile import's working copy": "The weekly cloud run's and a backfile import's working copies",
    "A working copy restored on the operator's machine": "A working copy restored on this Mac",
    "The weekly cloud run's run-state bundle": "The run-state bundle",
    "Removal log and suppression list": "Removal log and suppression list",
    "S3 noncurrent object versions": "S3 noncurrent versions",
}
"""Each row of the policy's retention table, by how it starts, and the runbook row that covers it."""


def first_cells(text: str, heading: str) -> list[str]:
    section = text.split(heading, 1)[1]
    table = re.search(r"\n(\|.*?\n)(?!\|)", section, re.DOTALL)
    assert table is not None
    rows = [line for line in table.group(1).splitlines() if line.startswith("|")][2:]
    return [row.split("|")[1].strip() for row in rows]


def test_the_runbook_covers_every_row_of_the_policys_retention_table() -> None:
    policy_rows = first_cells(POLICY.read_text(encoding="utf-8"), "## Retention\n")
    runbook_rows = first_cells(RUNBOOK.read_text(encoding="utf-8"), "## What the purge deletes, and what it keeps\n")
    unmapped = [row for row in policy_rows if not any(row.startswith(start) for start in RETENTION_ROWS)]
    assert unmapped == [], "a retention row the runbook does not cover yet"
    for start, covered_by in RETENTION_ROWS.items():
        assert any(row.startswith(start) for row in policy_rows), f"the policy has no row starting {start!r}"
        assert any(row.startswith(covered_by) for row in runbook_rows), f"the runbook has no row for {start!r}"

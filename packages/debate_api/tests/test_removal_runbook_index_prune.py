"""The removal runbook's index prune keeps the current index and the current pointer (`v1-e39-t07`).

`docs/runbooks/caselist-removal.md`, "P4 — Delete the superseded index versions", is run by the
operator against the bucket. Its dry run is a Python script in a heredoc, and the PM's ruling of
2026-10-22 asks for a guard in it: the current index's directory and the current version of
`current.json` are never in the delete set. This test takes the script out of the runbook as written
and runs it over invented `list-object-versions` answers, so the guard is tested where it lives.

Every key, id and version here is invented.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Final

import pytest

REPOSITORY: Final = Path(__file__).resolve().parents[3]
RUNBOOK: Final = REPOSITORY / "docs" / "runbooks" / "caselist-removal.md"
CURRENT: Final = "aaaaaaaaaaaaaaaa"
OLD: Final = "bbbbbbbbbbbbbbbb"
OLDER: Final = "cccccccccccccccc"
POINTER: Final = "reports/tub/search/current.json"


def prune_script() -> str:
    section = RUNBOOK.read_text(encoding="utf-8").split("### P4 — Delete the superseded index versions", 1)[1]
    found = re.search(r"python3 - \"\$PRUNE\" <<'PY'\n(.*?)\nPY\n", section, re.DOTALL)
    assert found is not None, "the runbook's prune dry run is no longer a python3 heredoc"
    return found.group(1)


def version(key: str, version_id: str, *, latest: bool) -> dict[str, Any]:
    return {"Key": key, "VersionId": version_id, "IsLatest": latest}


def index_objects(index_id: str, *, latest: bool, suffix: str = "1") -> list[dict[str, Any]]:
    return [
        version(f"reports/tub/search/{index_id}/manifest.json", f"m{suffix}", latest=latest),
        version(f"reports/tub/search/{index_id}/search-index.sqlite.gz", f"g{suffix}", latest=latest),
    ]


def run(
    tmp_path: Path, versions: list[dict[str, Any]], markers: list[dict[str, Any]], current: str = CURRENT
) -> Any:
    (tmp_path / "current.json").write_text(json.dumps({"index_id": current}))
    (tmp_path / "versions.json").write_text(json.dumps({"Versions": versions, "DeleteMarkers": markers}))
    return subprocess.run(
        [sys.executable, "-I", "-", str(tmp_path)],
        input=prune_script(),
        capture_output=True,
        text=True,
        check=False,
    )


def requested(tmp_path: Path) -> list[tuple[str, str]]:
    return sorted(
        (one["Key"], one["VersionId"])
        for request in sorted(tmp_path.glob("delete-*.json"))
        for one in json.loads(request.read_text())["Objects"]
    )


@pytest.fixture
def bucket() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The current index, two superseded ones, a noncurrent version of the current index's own
    manifest, and three versions of the pointer: the current one and two older ones."""
    versions = [
        *index_objects(CURRENT, latest=True),
        version(f"reports/tub/search/{CURRENT}/manifest.json", "m0", latest=False),
        *index_objects(OLD, latest=True),
        *index_objects(OLDER, latest=False, suffix="2"),
        version(POINTER, "p3", latest=True),
        version(POINTER, "p2", latest=False),
        version(POINTER, "p1", latest=False),
    ]
    markers = [version(f"reports/tub/search/{OLDER}/manifest.json", "d1", latest=True)]
    return versions, markers


def test_suppression_prune_deletes_every_superseded_version_and_keeps_the_current_index_and_pointer(
    tmp_path: Path, bucket: tuple[list[dict[str, Any]], list[dict[str, Any]]]
) -> None:
    answer = run(tmp_path, *bucket)

    assert answer.returncode == 0, answer.stderr
    assert requested(tmp_path) == sorted(
        [
            (f"reports/tub/search/{OLD}/manifest.json", "m1"),
            (f"reports/tub/search/{OLD}/search-index.sqlite.gz", "g1"),
            (f"reports/tub/search/{OLDER}/manifest.json", "m2"),
            (f"reports/tub/search/{OLDER}/search-index.sqlite.gz", "g2"),
            (f"reports/tub/search/{OLDER}/manifest.json", "d1"),
            (POINTER, "p2"),
            (POINTER, "p1"),
        ]
    )
    assert answer.stdout.splitlines()[-1] == (
        f"7 version(s) of 5 key(s) to delete; keeps reports/tub/search/{CURRENT}/ (2 objects) "
        f"and the current {POINTER}"
    )
    assert (tmp_path / "index_id").read_text() == CURRENT


def test_suppression_prune_stops_when_the_pointer_names_an_index_the_listing_does_not_hold(
    tmp_path: Path, bucket: tuple[list[dict[str, Any]], list[dict[str, Any]]]
) -> None:
    answer = run(tmp_path, *bucket, current="dddddddddddddddd")

    assert answer.returncode != 0
    assert "STOP" in answer.stderr
    assert list(tmp_path.glob("delete-*.json")) == []


def test_suppression_prune_with_only_the_current_index_deletes_nothing(tmp_path: Path) -> None:
    answer = run(tmp_path, [*index_objects(CURRENT, latest=True), version(POINTER, "p1", latest=True)], [])

    assert answer.returncode == 0, answer.stderr
    assert requested(tmp_path) == []
    assert answer.stdout.splitlines()[-1].startswith("0 version(s) of 0 key(s) to delete; keeps")


def test_suppression_prune_splits_its_requests_at_a_thousand_objects(tmp_path: Path) -> None:
    versions = [
        *index_objects(CURRENT, latest=True),
        version(POINTER, "p0", latest=True),
        *(version(POINTER, f"old{number}", latest=False) for number in range(1500)),
    ]

    answer = run(tmp_path, versions, [])

    assert answer.returncode == 0, answer.stderr
    sizes = [len(json.loads(path.read_text())["Objects"]) for path in sorted(tmp_path.glob("delete-*.json"))]
    assert sizes == [1000, 500]

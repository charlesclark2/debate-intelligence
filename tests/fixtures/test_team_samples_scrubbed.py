"""`tests/fixtures/team_samples/` holds a manifest of team files, and never a team file.

The spec's curate-samples node named this check for scrubbed copies of team files. The PM's
amendment of 2026-10-26 settled that no team file enters the repository in any form, scrubbed or
not, because a team file routinely carries cards another program cut. So the check that nothing
identifying is committed here is now the stronger one: there is nothing here but the manifest,
and the manifest holds season, event and a 16-hex-digit keyed digest per file, nothing else.
"""

from __future__ import annotations

import re
from pathlib import Path

TEAM_SAMPLES = Path(__file__).resolve().parent / "team_samples"
MANIFEST = TEAM_SAMPLES / "MANIFEST.md"

_ROW = re.compile(r"^\| 20\d\d-\d\d \| (LD|PF|Policy) \| `[0-9a-f]{16}` \|$")


def test_the_directory_holds_the_manifest_and_nothing_else() -> None:
    assert sorted(path.name for path in TEAM_SAMPLES.rglob("*")) == ["MANIFEST.md"]


def test_every_manifest_row_is_season_event_and_digest_only() -> None:
    table = [line for line in MANIFEST.read_text(encoding="utf-8").splitlines() if line.startswith("|")]

    assert table[:2] == ["| Season | Event | Digest |", "|---|---|---|"]
    rows = table[2:]
    assert rows, "the manifest lists no files"
    assert [row for row in rows if not _ROW.match(row)] == []
    digests = [row.split("`")[1] for row in rows]
    assert len(set(digests)) == len(digests)


def test_the_file_count_the_manifest_states_is_the_rows_it_lists() -> None:
    text = MANIFEST.read_text(encoding="utf-8")
    stated = re.search(r"^Run on \d{4}-\d{2}-\d{2}: (\d+) files\.$", text, re.MULTILINE)

    assert stated is not None
    assert int(stated.group(1)) == len([line for line in text.splitlines() if _ROW.match(line)])

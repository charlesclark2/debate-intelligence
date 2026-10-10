"""Weekly windows and complete archives in which one path is revised again and again (`v1-e30-t11`).

A removal request covers later uploads at the removed file's path (the PM's `v1-e30-t07` ruling), and
`caselist remove` has to find them among snapshots that are **windows**, not cumulative copies: each
weekly archive holds about one week's changes, so a revision of a file shows up as a row at the same
path in a later window, or only in a complete archive. This fixture is that case, small enough to
work every expected answer out by hand.

Nothing here came from a real caselist. The schools (`Alder Point`, `Birch Hill`), the team codes
(`KR`, `MT`), the tournament and every document are invented, as
`docs/policies/caselist-data-use.md` requires of anything committed.

## The paths

| Name | Path | Whose |
|---|---|---|
| `REVISED_PATH` | `Alder Point/KR/Alder Point-KR-Aff-Lakeshore Open-Round 2.docx` | the requester's |
| `OTHER_TEAM_PATH` | `Birch Hill/MT/Birch Hill-MT-Neg-Lakeshore Open-Round 4.docx` | another team |
| `KEPT_PATH` | `Birch Hill/MT/Birch Hill-MT-Aff-Lakeshore Open-Round 1.docx` | another team |
| `ONE_WEEK_PATH` | `Birch Hill/MT/Birch Hill-MT-Neg-Lakeshore Open-Round 3.docx` | another team |

## What each snapshot holds

`testcl26`, the caselist the request is about. A dash is a path the snapshot does not hold: the
window did not touch it that week.

| Snapshot | `REVISED_PATH` | `OTHER_TEAM_PATH` | `KEPT_PATH` | `ONE_WEEK_PATH` |
|---|---|---|---|---|
| weekly `2026-09-01` | `earlier-version` | — | `kept` | — |
| complete `full/2026-09-05` | `earlier-version` | — | `kept` | — |
| weekly `2026-09-08` | **`named-version`** | — | `kept` | `one-week-only` |
| weekly `2026-09-15` | `later-revision` | — | `kept` | — |
| weekly `2026-09-22` | — | — | `kept` | — |
| weekly `2026-09-29` | **`named-version`** | — | `kept` | — |
| complete `full/2026-10-03` | `later-in-complete-archive-only` | — | `kept` | — |
| weekly `2026-10-06` | `later-also-at-another-path` | `later-also-at-another-path` | `kept` | — |

`testclb26`, another caselist, holds one weekly, `2026-09-15`, with `other-caselist-same-path` at
a path spelled exactly as `REVISED_PATH` is. It is a different path: a path is a caselist and a path.

## The request, and its answer worked out by hand

`caselist remove --source <named-version>`. The earliest snapshot holding `named-version` at
`REVISED_PATH` is the weekly of `2026-09-08` (it is there again on `2026-09-29`, a revert, which
changes nothing: the earliest is what counts). So, at `(testcl26, REVISED_PATH)`:

| Body | Held there in | So it is | And the removal |
|---|---|---|---|
| `earlier-version` | `2026-09-01`, `full/2026-09-05`: before | an earlier version | lists it only |
| `later-revision` | `2026-09-15`: after | a later upload, held nowhere else | removes it |
| `later-in-complete-archive-only` | `full/2026-10-03`: after | a later upload, as above | removes it |
| `later-also-at-another-path` | `2026-10-06`: after | a later upload, shared | withdraws it from this path |

"Removes it" is everywhere: it is held nowhere else. "Shared" is `later-also-at-another-path`, which
`OTHER_TEAM_PATH` holds too, so only its row at `REVISED_PATH` goes and its bytes stay.

`full/2026-09-05` is the row that tells a date from a name: as a string, `full/2026-09-05` sorts
after `2026-09-08`, and as a date it is three days before. `later-revision` sits between the two
weeks that hold `named-version`, so a rule that looked after its *latest* snapshot would miss it.
`other-caselist-same-path` is in a snapshot dated after `09-08`, at the same spelling of the path,
in another caselist: not a later upload.

:data:`EXPECTED` states that answer as literals. Nothing here runs the removal planner, and no test
may derive these from it (`docs/process/working-agreements.md` §6).

The manifest rows the removal drops, one manifest at a time, each on this machine and in the bucket:

| Manifest | Row dropped | Why |
|---|---|---|
| `2026-09-01`, `full/2026-09-05` | none | the earlier version stays |
| `2026-09-08` | `named-version` | named |
| `2026-09-15` | `later-revision` | a later upload |
| `2026-09-22` | the `REMOVED` row at `REVISED_PATH` | it says the file at a removed file's path went |
| `2026-09-29` | `named-version` | named |
| `full/2026-10-03` | `later-in-complete-archive-only` | a later upload |
| `2026-10-06` | `later-also-at-another-path` at `REVISED_PATH` | withdrawn; its other row stays |
| `testclb26`'s `2026-09-15` | none | another caselist |

Run it by hand to look at what it makes::

    uv run python -m tests.fixtures.caselist.build_revised_path_archives /tmp/revised-path-archives
"""

from __future__ import annotations

import argparse
import hashlib
import zipfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Final

from tests.fixtures.caselist.build_synthetic_archives import (
    SYNTHETIC_CASELIST,
    _docx,  # pyright: ignore[reportPrivateUsage]
)

__all__ = [
    "BODIES",
    "CASELIST",
    "COMPLETE_ARCHIVES",
    "EXPECTED",
    "ExpectedRemoval",
    "KEPT_PATH",
    "ONE_WEEK_PATH",
    "OTHER_CASELIST",
    "OTHER_TEAM_PATH",
    "REVISED_PATH",
    "WEEKLY_WINDOWS",
    "build_complete_archive_zips",
    "build_weekly_zips",
    "digest_of",
    "write_archive",
]

CASELIST: Final = SYNTHETIC_CASELIST
"""`testcl26`, the caselist the request is about."""

OTHER_CASELIST: Final = "testclb26"
"""A second invented caselist, which holds a file at the same spelling of the revised path."""

REVISED_PATH: Final = "Alder Point/KR/Alder Point-KR-Aff-Lakeshore Open-Round 2.docx"
OTHER_TEAM_PATH: Final = "Birch Hill/MT/Birch Hill-MT-Neg-Lakeshore Open-Round 4.docx"
KEPT_PATH: Final = "Birch Hill/MT/Birch Hill-MT-Aff-Lakeshore Open-Round 1.docx"
ONE_WEEK_PATH: Final = "Birch Hill/MT/Birch Hill-MT-Neg-Lakeshore Open-Round 3.docx"

BODIES: Final[dict[str, bytes]] = {
    "earlier-version": _docx(("Lakeshore Open, round two, affirmative.", "As first disclosed.")),
    "named-version": _docx(("Lakeshore Open, round two, affirmative.", "The version a request names.")),
    "later-revision": _docx(("Lakeshore Open, round two, affirmative.", "Revised the week after.")),
    "later-in-complete-archive-only": _docx(
        ("Lakeshore Open, round two, affirmative.", "A revision only a complete archive caught.")
    ),
    "later-also-at-another-path": _docx(
        ("Lakeshore Open, round two, affirmative.", "A revision another team disclosed too.")
    ),
    "other-caselist-same-path": _docx(
        ("Lakeshore Open, round two, affirmative.", "Another caselist's file at the same spelling.")
    ),
    "kept": _docx(("Lakeshore Open, round one, affirmative.", "Another team's, in every snapshot.")),
    "one-week-only": _docx(("Lakeshore Open, round three, negative.", "In one weekly window only.")),
}
"""Every distinct document in the fixture, by the name the tables above use."""

WEEKLY_WINDOWS: Final[dict[tuple[str, date], dict[str, str]]] = {
    (CASELIST, date(2026, 9, 1)): {REVISED_PATH: "earlier-version", KEPT_PATH: "kept"},
    (CASELIST, date(2026, 9, 8)): {
        REVISED_PATH: "named-version",
        KEPT_PATH: "kept",
        ONE_WEEK_PATH: "one-week-only",
    },
    (CASELIST, date(2026, 9, 15)): {REVISED_PATH: "later-revision", KEPT_PATH: "kept"},
    (CASELIST, date(2026, 9, 22)): {KEPT_PATH: "kept"},
    (CASELIST, date(2026, 9, 29)): {REVISED_PATH: "named-version", KEPT_PATH: "kept"},
    (CASELIST, date(2026, 10, 6)): {
        REVISED_PATH: "later-also-at-another-path",
        OTHER_TEAM_PATH: "later-also-at-another-path",
        KEPT_PATH: "kept",
    },
    (OTHER_CASELIST, date(2026, 9, 15)): {REVISED_PATH: "other-caselist-same-path"},
}
"""Each weekly archive's members, `{path: body name}`, by caselist and date."""

COMPLETE_ARCHIVES: Final[dict[tuple[str, date], dict[str, str]]] = {
    (CASELIST, date(2026, 9, 5)): {REVISED_PATH: "earlier-version", KEPT_PATH: "kept"},
    (CASELIST, date(2026, 10, 3)): {REVISED_PATH: "later-in-complete-archive-only", KEPT_PATH: "kept"},
}
"""Each complete archive's members, likewise."""


@dataclass(frozen=True, slots=True)
class ExpectedRemoval:
    """What removing one version must do, as literals a person wrote from the tables above."""

    named: str
    later_uploads: dict[str, list[str]]
    """Body name -> the snapshots that hold it at `(testcl26, REVISED_PATH)`, in date order."""
    earlier_versions: dict[str, list[str]]
    removed_everywhere: list[str]
    withdrawn_from_the_revised_path: list[str]
    untouched: list[str]
    rows_dropped: dict[str, int]
    """Rows dropped from each of `testcl26`'s manifests, on each side. `testclb26`'s are not rewritten."""
    local_records: int
    whole_file_suppressions: int
    one_path_suppressions: int


EXPECTED: Final = ExpectedRemoval(
    named="named-version",
    later_uploads={
        "later-revision": ["2026-09-15"],
        "later-in-complete-archive-only": ["full/2026-10-03"],
        "later-also-at-another-path": ["2026-10-06"],
    },
    earlier_versions={"earlier-version": ["2026-09-01", "full/2026-09-05"]},
    removed_everywhere=["named-version", "later-revision", "later-in-complete-archive-only"],
    withdrawn_from_the_revised_path=["later-also-at-another-path"],
    untouched=["earlier-version", "other-caselist-same-path", "kept", "one-week-only"],
    rows_dropped={
        "2026-09-08": 1,
        "2026-09-15": 1,
        "2026-09-22": 1,
        "2026-09-29": 1,
        "full/2026-10-03": 1,
        "2026-10-06": 1,
    },
    # Two disclosure records and the source document of the named file; one disclosure and the
    # source document of the later revision; the source document of the revision only the complete
    # archive holds (a complete archive records no disclosure); and the one disclosure record of the
    # shared revision at the revised path.
    local_records=3 + 2 + 1 + 1,
    whole_file_suppressions=3,
    one_path_suppressions=1,
)
"""The answer to `caselist remove --source <named-version>`, written by hand from the tables above."""


def digest_of(body: str) -> str:
    """The sha256 of one of :data:`BODIES`."""
    return hashlib.sha256(BODIES[body]).hexdigest()


def write_archive(path: Path, members: dict[str, str]) -> Path:
    """Write `members` (`{path: body name}`) as a zip at `path`, byte for byte the same every time."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(members):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, BODIES[members[name]])
    return path


def build_weekly_zips(destination: Path) -> dict[tuple[str, date], Path]:
    """Every weekly archive, named as `caselist pull` names one: `<slug>-weekly-<date>.zip`."""
    return {
        (caselist, week): write_archive(
            Path(destination) / f"{caselist}-weekly-{week.isoformat()}.zip", members
        )
        for (caselist, week), members in WEEKLY_WINDOWS.items()
    }


def build_complete_archive_zips(destination: Path) -> dict[tuple[str, date], Path]:
    """Every complete archive, named as `caselist pull` names one: `<slug>-all-<date>.zip`."""
    return {
        (caselist, day): write_archive(Path(destination) / f"{caselist}-all-{day.isoformat()}.zip", members)
        for (caselist, day), members in COMPLETE_ARCHIVES.items()
    }


def main() -> None:
    """Build the archives into a directory, for looking at what the tests run against."""
    parser = argparse.ArgumentParser(description=__doc__ and __doc__.splitlines()[0])
    parser.add_argument("destination", type=Path, help="Directory to build the archives into.")
    arguments = parser.parse_args()
    for built in (
        build_weekly_zips(arguments.destination),
        build_complete_archive_zips(arguments.destination),
    ):
        for (caselist, day), path in sorted(built.items()):
            print(f"{caselist} {day.isoformat()}: {path}")


if __name__ == "__main__":
    main()

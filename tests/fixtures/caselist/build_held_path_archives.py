"""Archives that reach a store after a file at one of their paths was removed (`v1-e30-t13`).

`build_revised_path_archives.py` is the store a removal is made on: six weekly windows and two
complete archives of `testcl26`, in which one path is revised again and again, and one weekly of
another caselist. This fixture is what arrives afterwards. A removal by `--source` holds the removed
file's path, so the importer refuses a new upload there and the removal plan finds one that is
waiting in the download inbox.

Nothing here came from a real caselist. The schools, team codes, tournament and documents are the
invented ones of `build_revised_path_archives.py`, as `docs/policies/caselist-data-use.md` requires
of anything committed.

## The removal

`caselist remove --source <named-version>`. `named-version` is held at one path,
`(testcl26, REVISED_PATH)`, first in the weekly of `2026-09-08`. So the removal holds one path, and
the hold covers uploads in snapshots dated after `2026-09-08`.

## What arrives

Four archives. A path an archive is not listed with is one it does not hold.

`testcl26` weekly `2026-10-08`:

| Path | Document |
|---|---|
| `REVISED_PATH` | `uploaded-after-the-removal` |
| `ONE_WEEK_PATH` | `uploaded-after-at-another-path` |
| `KEPT_PATH` | `kept` |

`testcl26` complete archive `2026-10-09`:

| Path | Document |
|---|---|
| `REVISED_PATH` | `uploaded-after-in-a-complete-archive` |
| `KEPT_PATH` | `kept` |

`testcl26` weekly `2026-10-10`:

| Path | Document |
|---|---|
| `REVISED_PATH` | `uploaded-after-at-two-paths` |
| `OTHER_TEAM_PATH` | `uploaded-after-at-two-paths`, the same bytes |
| `KEPT_PATH` | `kept` |

`testclb26` weekly `2026-10-08` holds `uploaded-after-in-another-caselist` at a path spelled as
`REVISED_PATH` is.

## What an import of each must do, worked out by hand

The store the weeklies are classified against is the revised-path store after the removal. Its
newest weekly of `testcl26` is `2026-10-06`, which then holds `later-also-at-another-path` at
`OTHER_TEAM_PATH` and `kept` at `KEPT_PATH`; its newest complete archive is `full/2026-10-03`, which
then holds `kept` alone. `testclb26`'s only weekly, `2026-09-15`, holds `other-caselist-same-path`
at the same spelling of the revised path.

`testcl26` weekly `2026-10-08`, against `2026-10-06`:

| Path | What the import does | Counted as |
|---|---|---|
| `REVISED_PATH` | refuses it: a new sha256 at the held path | `SUPPRESSED` |
| `ONE_WEEK_PATH` | stores it: another path | `NEW` |
| `KEPT_PATH` | carries it forward | `UNCHANGED` |
| `OTHER_TEAM_PATH` | the window does not hold it | `REMOVED` |

`testcl26` complete archive `2026-10-09`, against `full/2026-10-03`:

| Path | What the import does | Counted as |
|---|---|---|
| `REVISED_PATH` | refuses it | `SUPPRESSED` |
| `KEPT_PATH` | carries it forward | `UNCHANGED` |

`testcl26` weekly `2026-10-10`, imported after `2026-10-08` and so against it:

| Path | What the import does | Counted as |
|---|---|---|
| `REVISED_PATH` | refuses it | `SUPPRESSED` |
| `OTHER_TEAM_PATH` | stores the same bytes: the hold is on the path, not on the bytes | `NEW` |
| `KEPT_PATH` | carries it forward | `UNCHANGED` |
| `ONE_WEEK_PATH` | the window does not hold it | `REMOVED` |

`testclb26` weekly `2026-10-08`, against `2026-09-15`: the file at the same spelling of the path is
stored, because it is another caselist's path. It replaces other bytes there, so it is `CHANGED`.

The weekly of `2026-09-01`, imported again, still stores `earlier-version` at `REVISED_PATH`: it is
dated before the removed file first appeared there, so it is an earlier version, which a removal
request does not cover (`v1-e30-t11`).

:data:`EXPECTED_COUNTS` states the counts as literals. Nothing here runs the importer or the removal
planner, and no test may derive these from either (`docs/process/working-agreements.md` §6).

## In the download inbox

The same three `testcl26` archives, put in the inbox before the removal runs, are archives waiting
to be imported. The removal plan must list the three uploads at the held path as later uploads, and
the executed removal must leave each archive in the inbox without its member at `REVISED_PATH`:

| Inbox archive | Left in it after the removal |
|---|---|
| `testcl26-weekly-2026-10-08.zip` | `ONE_WEEK_PATH`, `KEPT_PATH` |
| `testcl26-all-2026-10-09.zip` | `KEPT_PATH` |
| `testcl26-weekly-2026-10-10.zip` | `OTHER_TEAM_PATH` (the other team's copy), `KEPT_PATH` |

`uploaded-after-the-removal` and `uploaded-after-in-a-complete-archive` are held nowhere else, so
each is suppressed as a whole file. `uploaded-after-at-two-paths` is another team's too, so only
its disclosure at the held path is suppressed.

Run it by hand to look at what it makes::

    uv run python -m tests.fixtures.caselist.build_held_path_archives /tmp/held-path-archives
"""

from __future__ import annotations

import argparse
import hashlib
import zipfile
from datetime import date
from pathlib import Path
from typing import Final

from tests.fixtures.caselist.build_revised_path_archives import (
    BODIES,
    CASELIST,
    KEPT_PATH,
    ONE_WEEK_PATH,
    OTHER_CASELIST,
    OTHER_TEAM_PATH,
    REVISED_PATH,
)
from tests.fixtures.caselist.build_synthetic_archives import _docx  # pyright: ignore[reportPrivateUsage]

__all__ = [
    "ARRIVING_BODIES",
    "ARRIVING_COMPLETE_ARCHIVES",
    "ARRIVING_WEEKLIES",
    "EXPECTED_COUNTS",
    "HELD_FROM",
    "LEFT_IN_THE_INBOX",
    "arriving_digest_of",
    "build_arriving_complete_archive_zips",
    "build_arriving_weekly_zips",
]

HELD_FROM: Final = date(2026, 9, 8)
"""The earliest snapshot holding `named-version` at the revised path: the hold covers later ones."""

ARRIVING_BODIES: Final[dict[str, bytes]] = {
    "uploaded-after-the-removal": _docx(
        ("Lakeshore Open, round two, affirmative.", "Uploaded again after the removal.")
    ),
    "uploaded-after-in-a-complete-archive": _docx(
        ("Lakeshore Open, round two, affirmative.", "Uploaded after the removal; a complete archive has it.")
    ),
    "uploaded-after-at-two-paths": _docx(
        ("Lakeshore Open, round two, affirmative.", "Uploaded after the removal by two teams.")
    ),
    "uploaded-after-at-another-path": _docx(
        ("Lakeshore Open, round three, negative.", "Another team's upload the same week.")
    ),
    "uploaded-after-in-another-caselist": _docx(
        ("Lakeshore Open, round two, affirmative.", "Another caselist's upload at the same spelling.")
    ),
}
"""The documents that arrive after the removal, by the name the tables above use."""

ARRIVING_WEEKLIES: Final[dict[tuple[str, date], dict[str, str]]] = {
    (CASELIST, date(2026, 10, 8)): {
        REVISED_PATH: "uploaded-after-the-removal",
        ONE_WEEK_PATH: "uploaded-after-at-another-path",
        KEPT_PATH: "kept",
    },
    (CASELIST, date(2026, 10, 10)): {
        REVISED_PATH: "uploaded-after-at-two-paths",
        OTHER_TEAM_PATH: "uploaded-after-at-two-paths",
        KEPT_PATH: "kept",
    },
    (OTHER_CASELIST, date(2026, 10, 8)): {REVISED_PATH: "uploaded-after-in-another-caselist"},
}
"""Each arriving weekly archive's members, `{path: body name}`, by caselist and date."""

ARRIVING_COMPLETE_ARCHIVES: Final[dict[tuple[str, date], dict[str, str]]] = {
    (CASELIST, date(2026, 10, 9)): {
        REVISED_PATH: "uploaded-after-in-a-complete-archive",
        KEPT_PATH: "kept",
    },
}
"""The arriving complete archive's members, likewise."""

EXPECTED_COUNTS: Final[dict[str, dict[str, int]]] = {
    "testcl26 weekly 2026-10-08": {"SUPPRESSED": 1, "NEW": 1, "UNCHANGED": 1, "REMOVED": 1},
    "testcl26 complete 2026-10-09": {"SUPPRESSED": 1, "UNCHANGED": 1},
    "testcl26 weekly 2026-10-10": {"SUPPRESSED": 1, "NEW": 1, "UNCHANGED": 1, "REMOVED": 1},
    "testclb26 weekly 2026-10-08": {"CHANGED": 1},
}
"""What each import counts, written by hand from the tables above. A count of zero is left out."""

LEFT_IN_THE_INBOX: Final[dict[str, list[str]]] = {
    f"{CASELIST}-weekly-2026-10-08.zip": sorted([ONE_WEEK_PATH, KEPT_PATH]),
    f"{CASELIST}-all-2026-10-09.zip": [KEPT_PATH],
    f"{CASELIST}-weekly-2026-10-10.zip": sorted([OTHER_TEAM_PATH, KEPT_PATH]),
}
"""The members each waiting archive keeps once the removal has run, written by hand likewise."""

_ALL_BODIES: Final = {**BODIES, **ARRIVING_BODIES}


def arriving_digest_of(body: str) -> str:
    """The sha256 of one of :data:`ARRIVING_BODIES`."""
    return hashlib.sha256(ARRIVING_BODIES[body]).hexdigest()


def _write_archive(path: Path, members: dict[str, str]) -> Path:
    """Write `members` (`{path: body name}`) as a zip at `path`, byte for byte the same every time."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(members):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, _ALL_BODIES[members[name]])
    return path


def build_arriving_weekly_zips(destination: Path) -> dict[tuple[str, date], Path]:
    """Every arriving weekly archive, named as `caselist pull` names one: `<slug>-weekly-<date>.zip`."""
    return {
        (caselist, week): _write_archive(
            Path(destination) / f"{caselist}-weekly-{week.isoformat()}.zip", members
        )
        for (caselist, week), members in ARRIVING_WEEKLIES.items()
    }


def build_arriving_complete_archive_zips(destination: Path) -> dict[tuple[str, date], Path]:
    """The arriving complete archive, named as `caselist pull` names one: `<slug>-all-<date>.zip`."""
    return {
        (caselist, day): _write_archive(Path(destination) / f"{caselist}-all-{day.isoformat()}.zip", members)
        for (caselist, day), members in ARRIVING_COMPLETE_ARCHIVES.items()
    }


def main() -> None:
    """Build the archives into a directory, for looking at what the tests run against."""
    parser = argparse.ArgumentParser(description=__doc__ and __doc__.splitlines()[0])
    parser.add_argument("destination", type=Path, help="Directory to build the archives into.")
    arguments = parser.parse_args()
    for built in (
        build_arriving_weekly_zips(arguments.destination),
        build_arriving_complete_archive_zips(arguments.destination),
    ):
        for (caselist, day), path in sorted(built.items()):
            print(f"{caselist} {day.isoformat()}: {path}")


if __name__ == "__main__":
    main()

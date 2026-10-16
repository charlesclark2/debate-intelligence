"""Weekly windows and complete archives imported out of date order (`v1-e30-t17`).

A weekly archive holds about a week's editing, and the complete archive (`<slug>-all-<date>.zip`,
`v1-e34-t04`) is the cumulative copy (`docs/data/caselist-backfill-2026-09.md`, "Weekly archives are
adjacent windows, not cumulative copies"). The importer refused an archive older than one already
imported on the reasoning of cumulative weeklies. This fixture asks what an import actually does when
the archives arrive out of date order, under the window model, with every answer worked out by hand
below before any test runs it.

Nothing here came from a real caselist. The paths are the invented ones of
`build_revised_path_archives.py`, and every document is invented, as
`docs/policies/caselist-data-use.md` requires of anything committed.

## What each snapshot holds

`testcl26`. A dash is a path the snapshot does not hold.

| Snapshot | `REVISED_PATH` | `KEPT_PATH` | `ONE_WEEK_PATH` | `OTHER_TEAM_PATH` |
|---|---|---|---|---|
| complete `full/2026-08-29` | `first-version` | `carried` | — | — |
| weekly `2026-09-01` | `first-version` | `carried` | — | — |
| weekly `2026-09-08` | `second-version` | `carried` | `second-week-only` | `from-the-second-week-on` |
| complete `full/2026-09-12` | `second-version` | `carried` | — | `from-the-second-week-on` |
| weekly `2026-09-15` | `third-version` | `carried` | — | `from-the-second-week-on` |

One path is revised every week. `carried` is in every window, and `from-the-second-week-on` is first
in the second window and carried into the third: the file a second window brings and a third still
holds is the one an out-of-order import counts as first seen twice. `second-week-only` is in one
window and gone by the complete archive of `2026-09-12`: a withdrawal. Six distinct documents.

## How the counts are worked out

A weekly is classified against the latest weekly **dated** before it, whatever order they arrived
in, and its first-seen count is the distinct digests it stores that no weekly manifest dated before
it holds; complete archives are not read for either (`v1-e34-t04`). A complete archive is classified
against the latest complete archive dated before it, and its withdrawals are counted against every
manifest, weekly or complete, dated before it **that is on this machine when it is imported**. A
weekly is refused when a later weekly is already imported and it is not imported itself, unless the
import is allowed out of order; a week already imported is imported again without the flag
(`v1-e30-t18`). A complete archive writes no snapshot record, so no weekly is ever refused or
classified because of one.

## The scenarios, and their answers worked out by hand

Each is a fresh store and a list of imports in the order given.

**Weeklies in date order** (the reference): `2026-09-01`, `2026-09-08`, `2026-09-15`.

| Import | Against | Counts | First seen |
|---|---|---|---|
| `2026-09-01` | none | NEW 2 | 2 |
| `2026-09-08` | `2026-09-01` | CHANGED 1, UNCHANGED 1, NEW 2 | 3: `second-version` and the two new files |
| `2026-09-15` | `2026-09-08` | CHANGED 1, UNCHANGED 2, REMOVED 1 | 1: `third-version` |

The first-seen counts sum to 6, the distinct documents.

**A weekly after a later one**: `2026-09-01`, `2026-09-15`, then `2026-09-08`.

| Import | Against | Counts | First seen |
|---|---|---|---|
| `2026-09-01` | none | NEW 2 | 2 |
| `2026-09-15` | `2026-09-01` | CHANGED 1, UNCHANGED 1, NEW 1 | 2: `third-version`, `from-the-…-on` |
| `2026-09-08`, not allowed | refused: `2026-09-15` is already imported | | |
| `2026-09-08`, allowed out of order | `2026-09-01` | CHANGED 1, UNCHANGED 1, NEW 2 | 3, as in date order |

The late week is classified exactly as it is in date order, and nothing about it runs backwards. What
`v1-e30-t17` found off is the week after it, whose manifest was written before the late week was
there: it still named `2026-09-01` as its previous week, counted `from-the-second-week-on` as NEW
rather than UNCHANGED, had no REMOVED row for `ONE_WEEK_PATH`, and counted
`from-the-second-week-on` as first seen, so the first-seen counts summed to 7. Since `v1-e30-t18` it
is measured again (below). Importing `2026-09-15` again afterwards (it is the newest, so it needs no
flag) classifies it against `2026-09-08` and writes the manifest the date-order run wrote, byte for
byte.

**An older week imported again**: the three weeks in date order, then `2026-09-08` again, with no
flag (`v1-e30-t18`). It is classified against `2026-09-01` as before and writes the manifest it wrote
the first time, byte for byte; the `2026-09-15` manifest is not touched.

**A complete archive between two weeklies, in date order**: `2026-09-01`, `2026-09-08`,
`full/2026-09-12`, `2026-09-15`.

The complete archive has no complete archive before it, so all three of its files are NEW. Its
earlier snapshots are the two weeklies. Of their digests it lacks `first-version`, whose path now
holds `second-version` (superseded), and `second-week-only`, whose path is gone (withdrawn): withdrawn
1, superseded 1, 2 snapshots compared. `2026-09-15` is then classified as in date order.

**A complete archive imported before an earlier-dated weekly**: `2026-09-01`, `full/2026-09-12`,
`2026-09-08`, `2026-09-15`.

The complete archive is counted against `2026-09-01` alone, the one earlier manifest on this machine:
`first-version` superseded, nothing withdrawn, 1 snapshot compared. `2026-09-08` arrives later and is
dated before it, so the `second-week-only` withdrawal is never counted: the true answer, the one the
date-order run gives, is withdrawn 1, superseded 1, 2 compared. The weeklies are not refused (the
weekly series' newest is `2026-09-01` when `2026-09-08` arrives) and are classified as in date order.

**A complete archive before any weekly, dated before them all**: `full/2026-08-29`, the three weeklies,
then `full/2026-09-12`.

| Import | Against | Counts | First seen | Withdrawn, superseded, compared |
|---|---|---|---|---|
| `full/2026-08-29` | none | NEW 2 | — | 0, 0, 0 |
| the three weeklies | as in date order | as in date order | 2, 3, 1: the complete archive is not read | |
| `full/2026-09-12` | `full/2026-08-29` | CHANGED 1, UNCHANGED 1, NEW 1 | — | 1, 1, 3 |

**A complete archive before any weekly, dated after two of them**: `full/2026-09-12`, then the three
weeklies. The complete archive compares nothing: NEW 3, withdrawn 0, superseded 0, 0 compared, where
the date-order answer is 1, 1, 2. The weeklies are classified as in date order.

## The held path

A removal by `--source` holds the removed file's path from the earliest snapshot that held it there
(`v1-e30-t13`, Decision 1). Two stores, each `2026-09-01` and `2026-09-15` imported, then a removal,
then `2026-09-08` allowed out of order:

* **Dated after the hold's date.** `caselist remove --source <first-version>`. `first-version` is first
  at `REVISED_PATH` on `2026-09-01`, so the hold covers snapshots after `2026-09-01`, and
  `third-version` (`2026-09-15`) is a later upload, removed. The removal deletes `first-version`'s
  disclosure, so `2026-09-08` is classified against a `2026-09-01` that holds `carried` alone:
  `second-version` is at the held path in a snapshot dated after the hold, so SUPPRESSED and counted
  under the request; `carried` UNCHANGED; `second-week-only` and `from-the-second-week-on` NEW. First
  seen 2. Right under the window model: `second-version` was uploaded at the path after the removed
  file, which is what the request covers.
* **Dated before the hold's date.** `caselist remove --source <third-version>`. `third-version` is first
  at `REVISED_PATH` on `2026-09-15`, so the hold covers snapshots after `2026-09-15`; `first-version`
  is an earlier version, listed and kept. `2026-09-08` is dated before the hold, so `second-version`
  is an earlier version too and is imported: CHANGED 1 (against `first-version`), UNCHANGED 1, NEW 2,
  nothing held, first seen 3. Right: an earlier version is not covered by the request.

And the removal's later uploads (`v1-e30-t11`) after an out-of-order import: `2026-09-01`,
`2026-09-15`, then `2026-09-08` allowed out of order, then `caselist remove --source <first-version>`.
Later uploads are read from the manifests by date, so the answer is the date-order one: hold after
`2026-09-01`; `second-version` (`2026-09-08`) and `third-version` (`2026-09-15`) later uploads, both
removed; no earlier version.

## Measured again after a late weekly (`v1-e30-t18`)

After every weekly import, the weeklies dated after it are measured again from what the store
holds, never from their archives: each is classified against the latest weekly dated before it, as
a date-order import would be, and its first-seen count is taken against the weekly manifests dated
before it. A manifest whose bytes that changes is rewritten; one it does not is left alone. Then
the newest complete archive, if it is dated after the weekly, has its withdrawals counted again
against every manifest dated before it. Worked out by hand, scenario by scenario:

* **A weekly after a later one.** When `2026-09-08` is allowed in, `2026-09-15` is measured against
  it: CHANGED 1 (`third-version` over `second-version`), UNCHANGED 2 (`carried`,
  `from-the-second-week-on`), REMOVED 1 (`ONE_WEEK_PATH`), first seen 1 (`third-version`). That is
  the date-order manifest, so `2026-09-15` is rewritten, and the first-seen counts sum to 6. The
  refused attempt rewrites nothing, because nothing was imported.
* **The first weekly imported last**: `2026-09-08`, `2026-09-15`, then `2026-09-01` refused, then
  allowed. `2026-09-08` arrives first with nothing before it: NEW 4, first seen 4. `2026-09-15` is
  then the date-order answer, first seen 1. `2026-09-01` is NEW 2, first seen 2, and `2026-09-08`
  is measured against it: CHANGED 1, UNCHANGED 1, NEW 2, first seen 3, the date-order manifest, so
  it is rewritten. `2026-09-15` keeps `2026-09-08` as its previous week, and `third-version` is in
  no earlier week, so its manifest is the same bytes and is not rewritten.
* **An older week imported again**: the three weeks in date order, then `2026-09-08` again, with no
  flag. Nothing after it changes, so nothing is rewritten.
* **A complete archive imported before an earlier-dated weekly.** `2026-09-08` arrives after
  `full/2026-09-12`, the newest complete archive, and is dated before it, so its withdrawals are
  counted again, against `2026-09-01` and `2026-09-08`: withdrawn 1 (`second-week-only`),
  superseded 1 (`first-version`), 2 compared, where the import counted 0, 1, 1. `2026-09-15` is
  dated after it: no recount. The complete archive's manifest is then the date-order one byte for
  byte, since its summary differs only in those three counts.
* **A complete archive before any weekly, dated after two of them.** `2026-09-01` recounts it from
  0, 0, 0 to 0, 1, 1 (`first-version` superseded); `2026-09-08` from 0, 1, 1 to 1, 1, 2;
  `2026-09-15` is dated after it.
* **A complete archive between two weeklies, in date order**, and **before any weekly, dated before
  them all**: no weekly is dated before the newest complete archive when it is imported, and no
  weekly arrives after a later one, so nothing is rewritten.

:data:`EXPECTED_IMPORTS`, :data:`EXPECTED_HOLDS`, :data:`EXPECTED_LATER_UPLOADS` and
:data:`EXPECTED_REMEASURED` state those answers as literals. Nothing here runs the importer, and no
test may derive them from it (`docs/process/working-agreements.md` §6).

Run it by hand to look at what it makes::

    uv run python -m tests.fixtures.caselist.build_window_order_archives /tmp/window-order-archives
"""

from __future__ import annotations

import argparse
import hashlib
import zipfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Final, Literal

from tests.fixtures.caselist.build_revised_path_archives import (
    CASELIST,
    KEPT_PATH,
    ONE_WEEK_PATH,
    OTHER_TEAM_PATH,
    REVISED_PATH,
)
from tests.fixtures.caselist.build_synthetic_archives import (
    _docx,  # pyright: ignore[reportPrivateUsage]
)

__all__ = [
    "BODIES",
    "CASELIST",
    "COMPLETE_ARCHIVES",
    "EXPECTED_HOLDS",
    "EXPECTED_IMPORTS",
    "EXPECTED_LATER_UPLOADS",
    "EXPECTED_REMEASURED",
    "FIRST_WEEK",
    "FULL_AFTER_TWO_WEEKS",
    "FULL_BEFORE_THE_WEEKS",
    "SCENARIOS",
    "SECOND_WEEK",
    "THIRD_WEEK",
    "WEEKLY_WINDOWS",
    "ExpectedHold",
    "ExpectedImport",
    "ExpectedRemeasure",
    "Step",
    "build_complete_archive_zips",
    "build_weekly_zips",
    "digest_of",
]

FIRST_WEEK: Final = date(2026, 9, 1)
SECOND_WEEK: Final = date(2026, 9, 8)
THIRD_WEEK: Final = date(2026, 9, 15)
FULL_BEFORE_THE_WEEKS: Final = date(2026, 8, 29)
FULL_AFTER_TWO_WEEKS: Final = date(2026, 9, 12)

BODIES: Final[dict[str, bytes]] = {
    "first-version": _docx(("Lakeshore Open, round two, affirmative.", "The first version of the week.")),
    "second-version": _docx(("Lakeshore Open, round two, affirmative.", "Revised in the second week.")),
    "third-version": _docx(("Lakeshore Open, round two, affirmative.", "Revised again in the third week.")),
    "carried": _docx(("Lakeshore Open, round one, affirmative.", "Carried in every window.")),
    "second-week-only": _docx(("Lakeshore Open, round three, negative.", "In the second window only.")),
    "from-the-second-week-on": _docx(
        ("Lakeshore Open, round four, negative.", "First in the second window, carried into the third.")
    ),
}
"""Every distinct document in the fixture, by the name the tables above use."""

WEEKLY_WINDOWS: Final[dict[date, dict[str, str]]] = {
    FIRST_WEEK: {REVISED_PATH: "first-version", KEPT_PATH: "carried"},
    SECOND_WEEK: {
        REVISED_PATH: "second-version",
        KEPT_PATH: "carried",
        ONE_WEEK_PATH: "second-week-only",
        OTHER_TEAM_PATH: "from-the-second-week-on",
    },
    THIRD_WEEK: {
        REVISED_PATH: "third-version",
        KEPT_PATH: "carried",
        OTHER_TEAM_PATH: "from-the-second-week-on",
    },
}
"""Each weekly archive of `testcl26`, `{path: body name}`, by date."""

COMPLETE_ARCHIVES: Final[dict[date, dict[str, str]]] = {
    FULL_BEFORE_THE_WEEKS: {REVISED_PATH: "first-version", KEPT_PATH: "carried"},
    FULL_AFTER_TWO_WEEKS: {
        REVISED_PATH: "second-version",
        KEPT_PATH: "carried",
        OTHER_TEAM_PATH: "from-the-second-week-on",
    },
}
"""Each complete archive of `testcl26`, likewise."""


@dataclass(frozen=True, slots=True)
class Step:
    """One import in a scenario: a weekly or a complete archive, and whether it may be out of order."""

    kind: Literal["weekly", "complete"]
    day: date
    allow_out_of_order: bool = False

    @property
    def snapshot(self) -> str:
        """The snapshot's name as a manifest key names it: `2026-09-08` or `full/2026-09-12`."""
        return self.day.isoformat() if self.kind == "weekly" else f"full/{self.day.isoformat()}"


@dataclass(frozen=True, slots=True)
class ExpectedImport:
    """What one import must report, as literals a person wrote from the tables above."""

    snapshot: str
    previous: str | None
    counts: dict[str, int]
    first_seen: int | None = None
    """`None` for a complete archive, which reports no first-seen count."""
    withdrawals: tuple[int, int, int] | None = None
    """`(withdrawn, superseded, earlier snapshots compared)` for a complete archive; `None` for a weekly."""
    refused_by: str | None = None
    """The newer weekly an import not allowed out of order is refused for; then nothing else applies."""
    held: int = 0
    """Uploads refused because a removal holds their path."""


def _weekly(day: date, *, allowed: bool = False) -> Step:
    return Step("weekly", day, allow_out_of_order=allowed)


def _complete(day: date) -> Step:
    return Step("complete", day)


SCENARIOS: Final[dict[str, tuple[Step, ...]]] = {
    "weeklies in date order": (_weekly(FIRST_WEEK), _weekly(SECOND_WEEK), _weekly(THIRD_WEEK)),
    "a weekly after a later one": (
        _weekly(FIRST_WEEK),
        _weekly(THIRD_WEEK),
        _weekly(SECOND_WEEK),
        _weekly(SECOND_WEEK, allowed=True),
    ),
    "the first weekly imported last": (
        _weekly(SECOND_WEEK),
        _weekly(THIRD_WEEK),
        _weekly(FIRST_WEEK),
        _weekly(FIRST_WEEK, allowed=True),
    ),
    "an older week imported again": (
        _weekly(FIRST_WEEK),
        _weekly(SECOND_WEEK),
        _weekly(THIRD_WEEK),
        _weekly(SECOND_WEEK),
    ),
    "a complete archive between two weeklies, in date order": (
        _weekly(FIRST_WEEK),
        _weekly(SECOND_WEEK),
        _complete(FULL_AFTER_TWO_WEEKS),
        _weekly(THIRD_WEEK),
    ),
    "a complete archive imported before an earlier-dated weekly": (
        _weekly(FIRST_WEEK),
        _complete(FULL_AFTER_TWO_WEEKS),
        _weekly(SECOND_WEEK),
        _weekly(THIRD_WEEK),
    ),
    "a complete archive before any weekly, dated before them all": (
        _complete(FULL_BEFORE_THE_WEEKS),
        _weekly(FIRST_WEEK),
        _weekly(SECOND_WEEK),
        _weekly(THIRD_WEEK),
        _complete(FULL_AFTER_TWO_WEEKS),
    ),
    "a complete archive before any weekly, dated after two of them": (
        _complete(FULL_AFTER_TWO_WEEKS),
        _weekly(FIRST_WEEK),
        _weekly(SECOND_WEEK),
        _weekly(THIRD_WEEK),
    ),
}
"""Each scenario's imports, in the order they are made."""

_FIRST_IN_ORDER: Final = ExpectedImport("2026-09-01", None, {"NEW": 2}, first_seen=2)
_SECOND_IN_ORDER: Final = ExpectedImport(
    "2026-09-08", "2026-09-01", {"CHANGED": 1, "UNCHANGED": 1, "NEW": 2}, first_seen=3
)
_THIRD_IN_ORDER: Final = ExpectedImport(
    "2026-09-15", "2026-09-08", {"CHANGED": 1, "UNCHANGED": 2, "REMOVED": 1}, first_seen=1
)

EXPECTED_IMPORTS: Final[dict[str, tuple[ExpectedImport, ...]]] = {
    "weeklies in date order": (_FIRST_IN_ORDER, _SECOND_IN_ORDER, _THIRD_IN_ORDER),
    "a weekly after a later one": (
        _FIRST_IN_ORDER,
        ExpectedImport("2026-09-15", "2026-09-01", {"CHANGED": 1, "UNCHANGED": 1, "NEW": 1}, first_seen=2),
        ExpectedImport("2026-09-08", None, {}, refused_by="2026-09-15"),
        _SECOND_IN_ORDER,
    ),
    "the first weekly imported last": (
        ExpectedImport("2026-09-08", None, {"NEW": 4}, first_seen=4),
        _THIRD_IN_ORDER,
        ExpectedImport("2026-09-01", None, {}, refused_by="2026-09-15"),
        _FIRST_IN_ORDER,
    ),
    "an older week imported again": (_FIRST_IN_ORDER, _SECOND_IN_ORDER, _THIRD_IN_ORDER, _SECOND_IN_ORDER),
    "a complete archive between two weeklies, in date order": (
        _FIRST_IN_ORDER,
        _SECOND_IN_ORDER,
        ExpectedImport("full/2026-09-12", None, {"NEW": 3}, withdrawals=(1, 1, 2)),
        _THIRD_IN_ORDER,
    ),
    "a complete archive imported before an earlier-dated weekly": (
        _FIRST_IN_ORDER,
        ExpectedImport("full/2026-09-12", None, {"NEW": 3}, withdrawals=(0, 1, 1)),
        _SECOND_IN_ORDER,
        _THIRD_IN_ORDER,
    ),
    "a complete archive before any weekly, dated before them all": (
        ExpectedImport("full/2026-08-29", None, {"NEW": 2}, withdrawals=(0, 0, 0)),
        _FIRST_IN_ORDER,
        _SECOND_IN_ORDER,
        _THIRD_IN_ORDER,
        ExpectedImport(
            "full/2026-09-12",
            "full/2026-08-29",
            {"CHANGED": 1, "UNCHANGED": 1, "NEW": 1},
            withdrawals=(1, 1, 3),
        ),
    ),
    "a complete archive before any weekly, dated after two of them": (
        ExpectedImport("full/2026-09-12", None, {"NEW": 3}, withdrawals=(0, 0, 0)),
        _FIRST_IN_ORDER,
        _SECOND_IN_ORDER,
        _THIRD_IN_ORDER,
    ),
}
"""What each import of each scenario must report, in the order of :data:`SCENARIOS`."""


@dataclass(frozen=True, slots=True)
class ExpectedRemeasure:
    """What measuring the later manifests again must rewrite after one weekly import (`v1-e30-t18`)."""

    weeklies: tuple[str, ...] = ()
    """The weekly manifests rewritten, in date order."""
    complete_archive: tuple[str, tuple[int, int, int], tuple[int, int, int]] | None = None
    """`(full/<date>, withdrawals before, withdrawals after)`, each `(withdrawn, superseded, compared)`."""


_NOTHING_REWRITTEN: Final = ExpectedRemeasure()

EXPECTED_REMEASURED: Final[dict[str, tuple[ExpectedRemeasure | None, ...]]] = {
    "weeklies in date order": (_NOTHING_REWRITTEN, _NOTHING_REWRITTEN, _NOTHING_REWRITTEN),
    "a weekly after a later one": (
        _NOTHING_REWRITTEN,
        _NOTHING_REWRITTEN,
        None,
        ExpectedRemeasure(weeklies=("2026-09-15",)),
    ),
    "the first weekly imported last": (
        _NOTHING_REWRITTEN,
        _NOTHING_REWRITTEN,
        None,
        ExpectedRemeasure(weeklies=("2026-09-08",)),
    ),
    "an older week imported again": (
        _NOTHING_REWRITTEN,
        _NOTHING_REWRITTEN,
        _NOTHING_REWRITTEN,
        _NOTHING_REWRITTEN,
    ),
    "a complete archive between two weeklies, in date order": (
        _NOTHING_REWRITTEN,
        _NOTHING_REWRITTEN,
        None,
        _NOTHING_REWRITTEN,
    ),
    "a complete archive imported before an earlier-dated weekly": (
        _NOTHING_REWRITTEN,
        None,
        ExpectedRemeasure(complete_archive=("full/2026-09-12", (0, 1, 1), (1, 1, 2))),
        _NOTHING_REWRITTEN,
    ),
    "a complete archive before any weekly, dated before them all": (
        None,
        _NOTHING_REWRITTEN,
        _NOTHING_REWRITTEN,
        _NOTHING_REWRITTEN,
        None,
    ),
    "a complete archive before any weekly, dated after two of them": (
        None,
        ExpectedRemeasure(complete_archive=("full/2026-09-12", (0, 0, 0), (0, 1, 1))),
        ExpectedRemeasure(complete_archive=("full/2026-09-12", (0, 1, 1), (1, 1, 2))),
        _NOTHING_REWRITTEN,
    ),
}
"""After each import of each scenario, what the later manifests' measuring rewrote.

`None` where nothing is measured: a complete archive's own import, or a refused weekly.
"""


@dataclass(frozen=True, slots=True)
class ExpectedHold:
    """A removal made after two weeklies, and the out-of-order weekly imported after it."""

    named: str
    hold_after: str
    later_uploads: dict[str, list[str]]
    """Body name -> the snapshots that hold it at `REVISED_PATH`, in date order."""
    earlier_versions: list[str]
    late_week: ExpectedImport


EXPECTED_HOLDS: Final[dict[str, ExpectedHold]] = {
    "dated after the hold's date": ExpectedHold(
        named="first-version",
        hold_after="2026-09-01",
        later_uploads={"third-version": ["2026-09-15"]},
        earlier_versions=[],
        late_week=ExpectedImport(
            "2026-09-08", "2026-09-01", {"SUPPRESSED": 1, "UNCHANGED": 1, "NEW": 2}, first_seen=2, held=1
        ),
    ),
    "dated before the hold's date": ExpectedHold(
        named="third-version",
        hold_after="2026-09-15",
        later_uploads={},
        earlier_versions=["first-version"],
        late_week=ExpectedImport(
            "2026-09-08", "2026-09-01", {"CHANGED": 1, "UNCHANGED": 1, "NEW": 2}, first_seen=3
        ),
    ),
}
"""The two held-path scenarios: `2026-09-01` and `2026-09-15` imported, a removal, then `2026-09-08`."""

EXPECTED_LATER_UPLOADS: Final = ExpectedHold(
    named="first-version",
    hold_after="2026-09-01",
    later_uploads={"second-version": ["2026-09-08"], "third-version": ["2026-09-15"]},
    earlier_versions=[],
    late_week=_SECOND_IN_ORDER,
)
"""`2026-09-01`, `2026-09-15`, `2026-09-08` allowed out of order, then the removal of `first-version`."""


def digest_of(body: str) -> str:
    """The sha256 of one of :data:`BODIES`."""
    return hashlib.sha256(BODIES[body]).hexdigest()


def _write_archive(path: Path, members: dict[str, str]) -> Path:
    """Write `members` (`{path: body name}`) as a zip at `path`, byte for byte the same every time."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(members):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, BODIES[members[name]])
    return path


def build_weekly_zips(destination: Path) -> dict[date, Path]:
    """Every weekly archive, named as `caselist pull` names one: `<slug>-weekly-<date>.zip`."""
    return {
        week: _write_archive(Path(destination) / f"{CASELIST}-weekly-{week.isoformat()}.zip", members)
        for week, members in WEEKLY_WINDOWS.items()
    }


def build_complete_archive_zips(destination: Path) -> dict[date, Path]:
    """Every complete archive, named as `caselist pull` names one: `<slug>-all-<date>.zip`."""
    return {
        day: _write_archive(Path(destination) / f"{CASELIST}-all-{day.isoformat()}.zip", members)
        for day, members in COMPLETE_ARCHIVES.items()
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
        for day, path in sorted(built.items()):
            print(f"{CASELIST} {day.isoformat()}: {path}")


if __name__ == "__main__":
    main()

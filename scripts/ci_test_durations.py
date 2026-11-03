"""Deal whole test files to ci.yml's `test` parts by how long each took on dev's last push run, and
add that run's parts up into the record the next runs deal by (v1-e41-t17).

Until v1-e41-t17 run_in_parts.py dealt every file's tests round all the parts. That keeps the parts
level by worker time, but each part builds again the module- and class-scoped fixtures of every file
it holds a test of, and three task pull requests after v1-e41-t16 had their slowest part's pytest
step at 189-289 s, against working agreement 1's 2-minute line (docs/process/ci-test-part-costs.md).
Dealt whole, a file's fixtures are built in one part.

**The record.** Every part of dev's push run times its tests, setup, call and teardown summed per
test file (run_in_parts.py's `--record-durations`). ci.yml's `test-durations` job adds the parts'
files up with `combine` below and saves the sum in GitHub's Actions cache, which pull requests into
dev restore:

    {"format": 1, "recorded_at": "2026-11-02T20:51:00+00:00", "commit": "<sha>",
     "files": {"tests/scripts/test_hard_stop.py": 12.5, ...}}

The seconds are worker seconds on a push part, which measures coverage and so takes about half
again a pull request's time; the deal reads only their proportions.

**The deal.** `test-selection` restores the record once and `scripts/ci_test_selection.py` hands
every part the same deal, `{"parts": N, "part_of_file": {"<test file>": K, ...}}`, so a record saved
while a run goes on cannot give two parts different deals.

* A chosen file the record does not name counts as the median of the record's files: new files are
  usually small, and most of the suite's files are.
* A file heavier than an even share of the parts (the chosen files' total over N) is left out of the
  deal, and run_in_parts.py deals its tests round every part as before: no deal of whole files can
  make a part lighter than the heaviest file in it. On invented durations shaped like the costs
  page's, an affected set holding the heaviest file had its slowest part at 2.2 times the mean
  dealt whole, and at the mean with that file spread (the costs page has the figures).
* The rest go heaviest first onto the part that holds least so far, ties to the earlier path and the
  lower part: greedy longest-first, which the PM's ruling of 2026-11-02 set as the floor.

**When it deals test by test**, as before, and says why in the job summary: the record is missing
(nothing restored) or unreadable (not JSON, another format, a negative time, no time or commit); it
is stale, recorded more than OLDEST_RECORD ago or naming no duration for more than
MOST_UNRECORDED_SHARE of the chosen files; every chosen file is heavier than a part's share; or a part
would hold no file with a recorded time, which could leave it collecting no test, pytest's exit 5.
None of these fails the run: each is a reason, never an error. ci.yml's `test-selection` job also
deals test by test when the selection script itself fails.

Nothing here reads a secret or uses the network; the cache is restored and saved by ci.yml's steps.

Usage, as ci.yml's `test-durations` job runs it:
  python scripts/ci_test_durations.py combine --commit SHA --out DIR/test-durations.json PART_FILE...
"""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

RECORD_FORMAT = 1
# What the record is called where test-selection restores it and test-durations saves it.
RECORD_NAME = "test-durations.json"
# Stale (the PM's ruling of 2026-11-02 asked for an age or a share): dev's push runs refresh the record
# several times a day, so two weeks without one means its recording is broken; and a selection a
# quarter new to the record is dealt more by the default than by durations.
OLDEST_RECORD = timedelta(days=14)
MOST_UNRECORDED_SHARE = 0.25
# Each push part's file, named as ci.yml's push step names it.
PART_FILE = re.compile(r"^test-durations-part-(\d+)-of-(\d+)\.json$")


class Unusable(Exception):
    """Why the parts cannot be dealt by a record; they are then dealt test by test."""


@dataclass(frozen=True)
class Record:
    recorded_at: datetime
    commit: str
    files: dict[str, float]

    @property
    def default(self) -> float:
        """What a file with no record counts as: the median of every file the record names."""
        return statistics.median(self.files.values())


@dataclass(frozen=True)
class Deal:
    """Which part, from 1, each whole test file goes to; empty when every file is dealt test by test.
    `why` finishes the summary's sentence. `loads` are the parts' expected seconds, `spread` the files
    left to be dealt test by test for being heavier than a part's share."""

    parts: int
    part_of_file: dict[str, int]
    why: str
    loads: tuple[float, ...] = ()
    spread: tuple[str, ...] = ()
    unrecorded: int = 0
    default: float = 0.0

    @property
    def by_durations(self) -> bool:
        return bool(self.part_of_file)


def is_seconds(value: object) -> bool:
    return (
        isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value) and value >= 0
    )


def read_record(path: Path | None) -> Record:
    if path is None or not path.is_file():
        raise Unusable("no durations record was restored")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise Unusable(f"the durations record could not be read ({error})") from None
    return record_of(data)


def record_of(data: object) -> Record:
    if not isinstance(data, dict) or data.get("format") != RECORD_FORMAT:
        raise Unusable(f"the durations record is not a format {RECORD_FORMAT} record")
    files = data.get("files")
    if not isinstance(files, dict) or not files:
        raise Unusable("the durations record names no test file")
    for test_file, seconds in files.items():
        if not is_seconds(seconds):
            raise Unusable(f"the durations record gives {test_file!r} {seconds!r} seconds")
    try:
        recorded_at = datetime.fromisoformat(data["recorded_at"])
    except (KeyError, TypeError, ValueError):
        raise Unusable("the durations record says no time it was recorded") from None
    if recorded_at.tzinfo is None:
        raise Unusable("the durations record says no time it was recorded, only a local time")
    commit = data.get("commit")
    if not isinstance(commit, str):
        raise Unusable("the durations record names no commit")
    return Record(recorded_at, commit, {test_file: float(seconds) for test_file, seconds in files.items()})


def test_by_test(parts: int, why: str) -> Deal:
    return Deal(parts, {}, why)


def by_durations(
    durations: Mapping[str, float], parts: int
) -> tuple[dict[str, int], tuple[str, ...], list[float]]:
    """The deal of `durations`' files into `parts`: whole files heaviest first onto the lightest part,
    after the files heavier than a part's share, which are spread evenly over every part."""
    share = sum(durations.values()) / parts
    spread = tuple(sorted(test_file for test_file, seconds in durations.items() if seconds > share))
    loads = [sum(durations[test_file] for test_file in spread) / parts] * parts
    part_of_file: dict[str, int] = {}
    whole = sorted(
        (test_file for test_file in durations if test_file not in spread), key=lambda f: (-durations[f], f)
    )
    for test_file in whole:
        lightest = min(range(parts), key=lambda part: (loads[part], part))
        part_of_file[test_file] = lightest + 1
        loads[lightest] += durations[test_file]
    return part_of_file, spread, loads


def deal(test_files: Iterable[str], parts: int, record_path: Path | None, now: datetime) -> Deal:
    """The deal of the chosen `test_files` into `parts` by the record at `record_path`, or test by test
    and why."""
    files = sorted(set(test_files))
    try:
        return dealt(files, parts, read_record(record_path), now)
    except Unusable as reason:
        return test_by_test(parts, str(reason))


def dealt(files: list[str], parts: int, record: Record, now: datetime) -> Deal:
    age = now - record.recorded_at
    if age > OLDEST_RECORD:
        raise Unusable(
            f"the durations record is {age.days} days old, older than the {OLDEST_RECORD.days} days "
            "a record is dealt by"
        )
    unrecorded = [test_file for test_file in files if test_file not in record.files]
    if len(unrecorded) > MOST_UNRECORDED_SHARE * len(files):
        raise Unusable(
            f"{len(unrecorded)} of the {len(files)} test files chosen have no recorded duration, "
            "more than a quarter"
        )
    default = record.default
    durations = {test_file: record.files.get(test_file, default) for test_file in files}
    part_of_file, spread, loads = by_durations(durations, parts)
    if not part_of_file:
        raise Unusable("every test file chosen is heavier than a part's share")
    timed = {test_file for test_file in files if record.files.get(test_file, 0.0) > 0}
    held = {part for test_file, part in part_of_file.items() if test_file in timed}
    if timed & set(spread):
        held = set(range(1, parts + 1))
    if len(held) < parts:
        raise Unusable("a part would hold no test file with a recorded duration")
    return Deal(
        parts,
        part_of_file,
        f"by the durations dev's push run recorded at "
        f"{record.recorded_at.astimezone(UTC):%Y-%m-%d %H:%M} UTC "
        f"(commit `{record.commit[:12]}`)",
        tuple(loads),
        spread,
        len(unrecorded),
        default,
    )


def as_output(deal: Deal) -> str:
    """The deal as every part reads it: JSON on one line, or nothing for test by test."""
    if not deal.by_durations:
        return ""
    return json.dumps(
        {"parts": deal.parts, "part_of_file": deal.part_of_file}, sort_keys=True, separators=(",", ":")
    )


def summary(deal: Deal) -> str:
    if not deal.by_durations:
        return (
            "The parts are dealt test by test, each file's tests round every part as before "
            f"v1-e41-t17, because {deal.why}.\n"
        )
    has = "has" if deal.unrecorded == 1 else "have"
    lines = [
        f"The parts are dealt whole test files, heaviest first onto the lightest part, {deal.why}. "
        f"Expected seconds a part, as recorded: {min(deal.loads):.0f} to {max(deal.loads):.0f}.",
        f"{deal.unrecorded} of the {len(deal.part_of_file) + len(deal.spread)} test files chosen {has} "
        f"no record and count as the record's median, {deal.default:.1f} s.",
    ]
    if deal.spread:
        named = ", ".join(f"`{test_file}`" for test_file in deal.spread)
        lines.append(f"Dealt test by test round every part, as heavier than a part's share: {named}.")
    return "\n\n".join(lines) + "\n"


def combined(part_files: list[Path]) -> dict[str, float]:
    """Every push part's seconds added up per file. A file whose tests were in several parts (dealt
    test by test) is the sum of them. Refuses anything but exactly parts 1 to N of one N."""
    numbered: dict[tuple[int, int], Path] = {}
    for path in part_files:
        match = PART_FILE.match(path.name)
        if not match:
            raise SystemExit(f"combine: {path.name} does not say which part of how many it is")
        numbered[(int(match.group(1)), int(match.group(2)))] = path
    totals = {parts for _, parts in numbered}
    if len(totals) != 1:
        raise SystemExit(f"combine: the parts are of different matrices: {sorted(numbered)}")
    [parts] = totals
    missing = [part for part in range(1, parts + 1) if (part, parts) not in numbered]
    if missing:
        raise SystemExit(f"combine: expected parts 1 to {parts}; missing: {', '.join(map(str, missing))}")
    seconds: dict[str, float] = {}
    for path in numbered.values():
        try:
            timed = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError) as error:
            raise SystemExit(f"combine: {path.name} could not be read ({error})") from None
        if not isinstance(timed, dict) or not all(is_seconds(value) for value in timed.values()):
            raise SystemExit(f"combine: {path.name} is not seconds for each test file")
        for test_file, value in timed.items():
            seconds[test_file] = seconds.get(test_file, 0.0) + value
    if not seconds:
        raise SystemExit("combine: no part timed a test")
    return {test_file: round(seconds[test_file], 3) for test_file in sorted(seconds)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    combine = commands.add_parser("combine", help="add the push parts' files up into one record")
    combine.add_argument("--commit", required=True, help="the commit the push run tested")
    combine.add_argument("--out", type=Path, required=True, help=f"where to write the record, {RECORD_NAME}")
    combine.add_argument(
        "part_files", type=Path, nargs="*", help="test-durations-part-K-of-N.json, one a part"
    )
    arguments = parser.parse_args(argv)

    if not arguments.part_files:
        raise SystemExit("combine: no part's durations were downloaded")
    files = combined(arguments.part_files)
    record = {
        "format": RECORD_FORMAT,
        "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "commit": arguments.commit,
        "files": files,
    }
    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    arguments.out.write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
    print(
        f"Recorded {len(files)} test files' durations, {sum(files.values()):.0f} s in all, "
        f"at {arguments.out}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

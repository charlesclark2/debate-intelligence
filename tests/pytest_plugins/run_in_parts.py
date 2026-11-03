"""`--part K/N`: run one of N parts of whatever pytest selected (v1-e01-t27).

CI's `test` job is a matrix of parts, each on its own runner, so that the wait for `ci` on a pull
request stops growing with the suite (working agreement 1). `uv run pytest --part 2/4` runs the same
tests locally that part 2 of 4 runs there. Without the option this plugin does nothing.

How a test gets its part. Since v1-e41-t17 CI hands every part the same deal of whole test files to
parts (`--files-to-parts FILE`), which scripts/ci_test_selection.py makes from the durations dev's
push run recorded (scripts/ci_test_durations.py), so a file's module-scoped fixtures are built in
one part instead of in all of them. A file the deal names runs whole in its part. Every other file,
and every file when the deal is empty or not given, is dealt as before: its tests round the parts in
collection order, like cards, starting from a part chosen by a checksum of the file's path. So

* the parts are a partition by construction: every selected test is dealt to exactly one of them,
  whichever way its file is dealt. tests/scripts/test_ci_workflow_test_job.py proves it against the
  real suite, by collecting every part the way CI does, under a deal and under none, and comparing
  the node ids with an unsplit collection;
* a file dealt test by test spreads its cost evenly, including the few files that hold most of the
  suite's time. Measured on 5,812 tests, the heaviest of four parts held 1.04 times the mean test
  time. That is why the deal leaves out a file heavier than a part's share, and why a record that
  is missing or stale falls back to it;
* the deal has no state here. Every part and every xdist worker reads the same file and collects the
  same tests, so they deal alike; the record is read once, by ci.yml's `test-selection` job.

How many parts CI asks for follows the selection (v1-e41-t16): one per 30 test files, at most
MOST_PARTS. The dealing is the same at every N, and the partition proof deals the real suite at
every N the rule can give with `parts_dealt`, the function this hook deals with.

It deals what is left after `-m` and `-k` (the hook runs last), so a part of a narrower selection is
still a part of that selection. Every xdist worker collects for itself and deals the same way.

`--record-durations FILE` writes the seconds each test file took in this run, setup, call and
teardown summed, as JSON: `{"<test file>": seconds}`. Every part of dev's push run writes one, and
ci.yml's `test-durations` job adds them up into the record the next runs deal by. Under xdist the
controller writes it, from the reports its workers send.
"""

from __future__ import annotations

import argparse
import json
import sys
import zlib
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from pathlib import Path

import pytest


def part_of_parts(text: str) -> tuple[int, int]:
    """`2/4` as (2, 4); anything that is not a part of a whole number of parts is refused."""
    try:
        part, _, parts = text.partition("/")
        chosen = (int(part), int(parts))
    except ValueError:
        chosen = (0, 0)
    if not 1 <= chosen[0] <= chosen[1]:
        raise argparse.ArgumentTypeError(f"expected K/N with 1 <= K <= N, for example 2/4; got {text!r}")
    return chosen


def files_to_parts(text: str, parts: int) -> dict[str, int]:
    """The deal test-selection hands every part: the part, from 1, each whole test file goes to, as
    `{"parts": N, "part_of_file": {...}}`. Empty text is no deal: every file is dealt test by test.
    A deal into another number of parts, or naming a part that is not one of them, is refused: it
    is a fault in what wrote it, and following it could put a test in no part or in two."""
    if not text.strip():
        return {}
    try:
        deal = json.loads(text)
    except ValueError as error:
        raise pytest.UsageError(f"--files-to-parts: the deal is not JSON ({error})") from None
    part_of_file = deal.get("part_of_file") if isinstance(deal, dict) else None
    if not (
        isinstance(deal, dict)
        and deal.get("parts") == parts
        and isinstance(part_of_file, dict)
        and all(type(part) is int and 1 <= part <= parts for part in part_of_file.values())
    ):
        raise pytest.UsageError(
            f"--files-to-parts: not a deal of whole test files into {parts} parts: {text[:200]}"
        )
    return part_of_file


def first_part_dealt_to(test_file: str, parts: int) -> int:
    """Where dealing starts for one file, from 0. A checksum, so it is the same on every machine."""
    return zlib.crc32(test_file.encode("utf-8")) % parts


def parts_dealt(
    node_ids: Iterable[str], parts: int, part_of_file: Mapping[str, int] | None = None
) -> list[int]:
    """The part, from 0, each test is dealt to out of `parts`, for node ids in collection order: a
    file in the deal `part_of_file` (parts from 1) whole to its part, any other test by test."""
    part_of_file = part_of_file or {}
    dealt_so_far: Counter[str] = Counter()
    dealt: list[int] = []
    for node_id in node_ids:
        test_file = node_id.partition("::")[0]
        if test_file in part_of_file:
            dealt.append(part_of_file[test_file] - 1)
            continue
        dealt.append((first_part_dealt_to(test_file, parts) + dealt_so_far[test_file]) % parts)
        dealt_so_far[test_file] += 1
    return dealt


class DurationsRecorder:
    """Adds up each test file's seconds as the reports of its tests arrive, and writes them at the end."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.seconds: defaultdict[str, float] = defaultdict(float)

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        self.seconds[report.nodeid.partition("::")[0]] += report.duration

    def pytest_sessionfinish(self) -> None:
        timed = {test_file: round(self.seconds[test_file], 3) for test_file in sorted(self.seconds)}
        try:
            self.path.write_text(json.dumps(timed, indent=1) + "\n", encoding="utf-8")
        except OSError as error:
            # A part never fails for its durations: the record before this one stays in use.
            print(
                f"run_in_parts.py: could not record the test durations in {self.path}: {error}",
                file=sys.stderr,
            )


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--part",
        metavar="K/N",
        type=part_of_parts,
        default=None,
        help="Run part K of N of the selected tests. The N parts together are the whole selection.",
    )
    parser.addoption(
        "--files-to-parts",
        metavar="FILE",
        type=Path,
        default=None,
        help="With --part: deal whole test files to the parts as FILE says (written by "
        "scripts/ci_test_selection.py); the files it does not name, or all of them when it is empty, "
        "are dealt test by test.",
    )
    parser.addoption(
        "--record-durations",
        metavar="FILE",
        type=Path,
        default=None,
        help="Write each test file's seconds in this run (setup, call and teardown) to FILE, as JSON.",
    )


# The deal this run follows, read once at configuration, by the controller and every worker alike.
DEAL = pytest.StashKey[dict[str, int]]()


def pytest_configure(config: pytest.Config) -> None:
    chosen: tuple[int, int] | None = config.getoption("part")
    deal: Path | None = config.getoption("files_to_parts")
    if chosen is not None and deal is not None:
        try:
            text = deal.read_text(encoding="utf-8")
        except OSError as error:
            raise pytest.UsageError(f"--files-to-parts: could not read {deal}: {error}") from None
        config.stash[DEAL] = files_to_parts(text, chosen[1])
    path: Path | None = config.getoption("record_durations")
    # An xdist worker's reports reach the controller, which writes the one file.
    if path is not None and not hasattr(config, "workerinput"):
        config.pluginmanager.register(DurationsRecorder(path), "run_in_parts_durations")


def pytest_report_header(config: pytest.Config) -> str | None:
    chosen: tuple[int, int] | None = config.getoption("part")
    if chosen is None:
        return None
    deal = config.stash.get(DEAL, {})
    dealt = f" {len(deal)} whole files as the deal given says, the rest" if deal else ""
    return f"part: {chosen[0]} of {chosen[1]},{dealt} test by test (tests/pytest_plugins/run_in_parts.py)"


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    chosen: tuple[int, int] | None = config.getoption("part")
    if chosen is None:
        return
    part, parts = chosen
    in_this_part: list[pytest.Item] = []
    in_another_part: list[pytest.Item] = []
    dealt = parts_dealt((item.nodeid for item in items), parts, config.stash.get(DEAL, {}))
    for item, dealt_to in zip(items, dealt, strict=True):
        (in_this_part if dealt_to == part - 1 else in_another_part).append(item)
    items[:] = in_this_part
    config.hook.pytest_deselected(items=in_another_part)

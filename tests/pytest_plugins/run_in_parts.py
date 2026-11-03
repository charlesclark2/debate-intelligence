"""`--part K/N`: run one of N parts of whatever pytest selected (v1-e01-t27).

CI's `test` job is a matrix of parts, each on its own runner, so that the wait for `ci` on a pull
request stops growing with the suite (working agreement 1). `uv run pytest --part 2/4` runs the same
tests locally that part 2 of 4 runs there. Without the option this plugin does nothing.

How a test gets its part: each test file's tests are dealt round the parts in collection order, like
cards, starting from a part chosen by a checksum of the file's path. So

* the parts are a partition by construction: every selected test is dealt to exactly one of them.
  tests/scripts/test_ci_workflow_test_job.py proves it against the real suite, by collecting every
  part the way CI does and comparing the node ids with an unsplit collection;
* every file's cost is spread evenly, including the few files that hold most of the suite's time,
  so the parts stay level without a recorded-durations file that would go stale. Measured on
  5,812 tests, the heaviest of four parts held 1.04 times the mean test time;
* there is no state. The split cannot drift towards one part; what grows is every part together,
  and the answer to that is more parts: scripts/ci_test_selection.py's MOST_PARTS.

How many parts CI asks for follows the selection (v1-e41-t16): one per 30 test files, at most
MOST_PARTS. The dealing is the same at every N, and the partition proof deals the real suite at
every N the rule can give with `parts_dealt`, the function this hook deals with.

It deals what is left after `-m` and `-k` (the hook runs last), so a part of a narrower selection is
still a part of that selection. Every xdist worker collects for itself and deals the same way.
"""

from __future__ import annotations

import argparse
import zlib
from collections import Counter
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


def first_part_dealt_to(test_file: str, parts: int) -> int:
    """Where dealing starts for one file, from 0. A checksum, so it is the same on every machine."""
    return zlib.crc32(test_file.encode("utf-8")) % parts


def files_to_parts(text: str, parts: int) -> dict[str, int]:
    return {}


def parts_dealt(
    node_ids: Iterable[str], parts: int, part_of_file: Mapping[str, int] | None = None
) -> list[int]:
    """The part, from 0, each test is dealt to out of `parts`, for node ids in collection order."""
    dealt_so_far: Counter[str] = Counter()
    dealt: list[int] = []
    for node_id in node_ids:
        test_file = node_id.partition("::")[0]
        dealt.append((first_part_dealt_to(test_file, parts) + dealt_so_far[test_file]) % parts)
        dealt_so_far[test_file] += 1
    return dealt


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--part",
        metavar="K/N",
        type=part_of_parts,
        default=None,
        help="Run part K of N of the selected tests. The N parts together are the whole selection.",
    )
    parser.addoption("--files-to-parts", type=Path, default=None)
    parser.addoption("--record-durations", type=Path, default=None)


def pytest_report_header(config: pytest.Config) -> str | None:
    chosen: tuple[int, int] | None = config.getoption("part")
    if chosen is None:
        return None
    return f"part: {chosen[0]} of {chosen[1]} (tests/pytest_plugins/run_in_parts.py)"


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    chosen: tuple[int, int] | None = config.getoption("part")
    if chosen is None:
        return
    part, parts = chosen
    in_this_part: list[pytest.Item] = []
    in_another_part: list[pytest.Item] = []
    for item, dealt_to in zip(items, parts_dealt((item.nodeid for item in items), parts), strict=True):
        (in_this_part if dealt_to == part - 1 else in_another_part).append(item)
    items[:] = in_this_part
    config.hook.pytest_deselected(items=in_another_part)

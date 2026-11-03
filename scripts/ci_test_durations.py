"""Skeleton for the red run (v1-e41-t17): the interfaces, dealing nothing by durations."""

from __future__ import annotations

import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

RECORD_FORMAT = 1
RECORD_NAME = "test-durations.json"
OLDEST_RECORD = timedelta(days=14)
MOST_UNRECORDED_SHARE = 0.25


class Unusable(Exception):
    pass


@dataclass(frozen=True)
class Record:
    recorded_at: datetime
    commit: str
    files: dict[str, float]


@dataclass(frozen=True)
class Deal:
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


def read_record(path: Path | None) -> Record:
    raise Unusable("skeleton")


def test_by_test(parts: int, why: str) -> Deal:
    return Deal(parts, {}, why)


def by_durations(durations: Mapping[str, float], parts: int) -> tuple[dict[str, int], tuple[str, ...], list[float]]:
    return {}, (), [0.0] * parts


def deal(test_files: Iterable[str], parts: int, record_path: Path | None, now: datetime) -> Deal:
    return test_by_test(parts, "skeleton")


def as_output(deal: Deal) -> str:
    return ""


def summary(deal: Deal) -> str:
    return ""


def main(argv: list[str] | None = None) -> int:
    return 0


if __name__ == "__main__":
    sys.exit(main())

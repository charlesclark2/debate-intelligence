"""An older build never rewrites or publishes an occurrence table a newer one stamped (`v1-e34-t29`).

Every row of `occurrences.jsonl` carries the fingerprint version its fingerprint and cluster id were
computed under, and every run rebuilds the whole table under its own build's
:data:`~debate_core.evidence.fingerprints.FINGERPRINT_VERSION`. So a build older than a table's
stamp, run over the same parser version's directory, would put its own clusters back
(`v1-e31-t20`, Follow-up 4), and the search pilot's weekly index (`v1-e39-t09`) would publish them.

## The one rule

:func:`refuse_newer_table` is the rule every path that writes an occurrence table asks, as
:func:`~debate_core.application.caselist.publish_plan.stored_row_hold` is the one rule for a held
row. It takes the stamps a table holds and raises :class:`NewerFingerprintTable`, naming both
versions and the store, when one is newer than this build's. An equal or older stamp passes, and the
path goes on as it always did. The paths, each asking before it writes anything:

* **The parse pipeline's rebuild** (:meth:`~debate_core.application.caselist_parse.
  CaselistParseService.run`), which `caselist parse`, with or without `--publish`, and the weekly
  run's parse stage both run. It asks of the table it would replace as the caselist's current one:
  its own directory's, or, for a new directory, the one that directory supersedes.
* **The parsed store's publish** (:class:`~debate_core.application.caselist.parsed_publish.
  ParsedStorePublisher`), behind `caselist parse --publish` and the parse stage's publish. It asks
  of the table it would send and of the bucket's, when the bucket holds other bytes.

`store sync` asked too, from `v1-e34-t29`, while it moved `parsed/` as named objects. Since
`v1-e29-t12` it moves nothing under `parsed/` either way
(:class:`~debate_core.application.evidence_sync.EvidenceSyncService`), so it has no table to ask
about.

A refusal is raised before the path writes anything, so the table is left as it was: never a
partial rewrite.

## The order

:data:`~debate_core.evidence.fingerprints.EXACT_FINGERPRINT_VERSIONS` is a set, and loses its older
members when the normalization changes, so it does not say which of two versions is newer. Its
members are ordered by their version number: `card-fingerprint-v3` before `card-fingerprint-v4`.
That is the order used here. A stamp of another family, or one with no number, cannot be ordered
against this build's, and is treated as newer: this build cannot say its rules are not older.

## What is logged

Nothing. A refusal's message names a caselist, a version directory, a store and two versions.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Final, cast

from debate_core.application.errors import DomainError
from debate_core.application.ports.parsed_store import OCCURRENCES_NAME, PARSED_PREFIX
from debate_core.evidence.fingerprints import FINGERPRINT_VERSION

__all__ = [
    "THE_BUCKET",
    "THIS_MACHINES_PARSED_STORE",
    "NewerFingerprintTable",
    "fingerprint_stamps",
    "fingerprint_stamps_of_file",
    "is_newer_fingerprint_version",
    "newer_stamp",
    "occurrence_table_of",
    "profile_stamps",
    "profile_stamps_of_file",
    "refuse_newer_table",
]

THIS_MACHINES_PARSED_STORE: Final = "this machine's parsed store"
THE_BUCKET: Final = "the bucket"

_NUMBERED: Final = re.compile(r"(?P<family>.+)-v(?P<number>[1-9][0-9]*)")


def is_newer_fingerprint_version(stamped: str, build: str) -> bool:
    """Whether a table stamped `stamped` is newer than a build at `build`. See "The order"."""
    if stamped == build:
        return False
    theirs, ours = _NUMBERED.fullmatch(stamped), _NUMBERED.fullmatch(build)
    if theirs is None or ours is None or theirs["family"] != ours["family"]:
        return True
    return int(theirs["number"]) > int(ours["number"])


def newer_stamp(stamps: Iterable[str]) -> str | None:
    """The newest of `stamps` that is newer than this build's fingerprint version, or `None`."""
    newer = [stamp for stamp in set(stamps) if is_newer_fingerprint_version(stamp, FINGERPRINT_VERSION)]
    return max(newer, key=_newest_first_key) if newer else None


def _newest_first_key(stamp: str) -> tuple[bool, int, str]:
    numbered = _NUMBERED.fullmatch(stamp)
    return (numbered is None, int(numbered["number"]) if numbered else 0, stamp)


class NewerFingerprintTable(DomainError):
    """An occurrence table stamped with a newer fingerprint version than this build's (`v1-e34-t29`).

    Raised before anything is written, so the table is as it was. :attr:`fix` is the hint a weekly
    run's failed stage carries to its summary and its notification.
    """

    def __init__(self, *, caselist: str, version: str, store: str, stamped: str, build: str) -> None:
        self.caselist = caselist
        self.version = version
        self.store = store
        self.stamped = stamped
        self.build = build
        super().__init__(
            f"the occurrence table of {caselist} {version} in {store} is stamped {stamped}, newer than "
            f"this build's {build}; it was left as it was"
        )

    @property
    def fix(self) -> str:
        return (
            f"The occurrence table of {self.caselist} {self.version} in {self.store} is stamped "
            f"{self.stamped}, and this build's fingerprint version is {self.build}. Rebuild and publish "
            f"it with a build at {self.stamped} or later, and install that build for the weekly agent."
        )


def refuse_newer_table(stamps: Iterable[str], *, caselist: str, version: str, store: str) -> None:
    """Raise :class:`NewerFingerprintTable` when a stamp in `stamps` is newer than this build's.

    The one rule every path that writes an occurrence table asks before it writes anything. An
    equal or older stamp, and a table with no rows, pass.
    """
    stamped = newer_stamp(stamps)
    if stamped is not None:
        raise NewerFingerprintTable(
            caselist=caselist, version=version, store=store, stamped=stamped, build=FINGERPRINT_VERSION
        )


def fingerprint_stamps(lines: Iterable[str]) -> frozenset[str]:
    """The `fingerprint_version` of every row of an occurrence table's lines.

    Read from each line's JSON, not through the record's model: a newer build may write rows this
    build's model does not accept, and its table must still name its version. A line with no
    readable stamp says nothing about one and is passed over.
    """
    return _stamps(lines, "fingerprint_version")


def fingerprint_stamps_of_file(path: Path) -> frozenset[str]:
    """:func:`fingerprint_stamps` of the occurrence table at `path`, read a line at a time."""
    with path.open(encoding="utf-8") as stream:
        return fingerprint_stamps(stream)


def profile_stamps(lines: Iterable[str]) -> frozenset[str]:
    """The `profile_version` of every row of an occurrence table's lines (`v1-e33-t09`).

    The style profile the row's element indices were read under, read as :func:`fingerprint_stamps`
    reads its own stamp: from each line's JSON, passing over a line with none.
    """
    return _stamps(lines, "profile_version")


def profile_stamps_of_file(path: Path) -> frozenset[str]:
    """:func:`profile_stamps` of the occurrence table at `path`, read a line at a time."""
    with path.open(encoding="utf-8") as stream:
        return profile_stamps(stream)


def _stamps(lines: Iterable[str], name: str) -> frozenset[str]:
    stamps: set[str] = set()
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        stamp = cast("dict[str, object]", row).get(name) if isinstance(row, dict) else None
        if isinstance(stamp, str) and stamp:
            stamps.add(stamp)
    return frozenset(stamps)


def occurrence_table_of(key: str) -> tuple[str, str] | None:
    """`(caselist, version)` for a `parsed/<caselist>/<version>/occurrences.jsonl` key, else `None`."""
    parts = key.split("/")
    if len(parts) == 4 and parts[0] == PARSED_PREFIX and parts[3] == OCCURRENCES_NAME:
        return parts[1], parts[2]
    return None

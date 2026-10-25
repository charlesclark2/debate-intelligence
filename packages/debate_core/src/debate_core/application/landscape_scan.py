"""The scan before a landscape report is shared, and the operator's acceptance of what it found.

The data-use policy's E32 gate, item 4: the circuit-wide report is verified to contain no team code
before it is shared. `v1-e32-t03`'s preview showed that a scan cannot decide that alone. Its hits on
hspolicy26 were an evidence author who shares a school's name, an ordinary word that is also a
disclosed team code, and a filename token; none named a team, and a refusal on every hit would
block every week. So the scan lists, and the operator decides (the PM's rulings of 2026-10-24):

1. :func:`scan_report` lists every hit in the report's circuit-wide files, with its line;
2. a publish with a hit the operator has not accepted is refused, naming :func:`hits_digest` of the
   hits not yet accepted;
3. the operator reads them and runs again with that digest, which is accepted only while it is the
   digest of the hits the run found: one more hit, or one fewer, and it is stale;
4. what was accepted is kept in :class:`ScanAcceptanceLog`, in the local data directory, so a later
   week's run stops only on hits nobody has read.

## What it looks for

Every school, team code and tournament the report's own disclosures name, and the paths they were
filed under, as `v1-e32-t03`'s preview scanned:

* a **team code** case-sensitively, as a whole word, whatever its length: `XX` but not `XXL`;
* a **school** or **tournament** without regard to case, as whole words, when it is over three
  characters, since a shorter name is a word in every line;
* a **path** anywhere, without regard to case.

## The per-school view

`v1-e32-t04`'s `schools.csv` and `schools.md` name schools, team codes and tournaments by design: the
data-use policy allows school plus team code, as disclosed, in that view and nowhere else. A scan
that listed them would stop every week on every team until accepting meant nothing, so in the files
named as `school_view_files` it looks for paths only, which no file of the bundle may hold. Every
other file is scanned for everything.

## Which hits are the same hit next week

A hit is accepted by its :attr:`ScanHit.key`: its file, its kind, the term, and its line with every
run of digits written as `#`. A report's lines carry counts that change every week, and its rows
move up and down, so a hit keyed by its line number or its counts would be new every week and the
operator would accept the same words over and over until accepting meant nothing. A tag or a cite
that changes is a new line and a new hit.

The words a hit names stay on this machine: in the operator's terminal, and in the acceptance log
under the data directory. Nothing in a committed file names one.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Final, cast

from debate_core.application.caselist.path_parser import UNKNOWN_SCHOOL, UNKNOWN_TEAM_CODE
from debate_core.arguments.landscape.render import PLANK_TABLE_HEADER
from debate_core.domain.caselist import Disclosure

__all__ = [
    "DIGEST_LENGTH",
    "MINIMUM_NAME_LENGTH",
    "ScanAcceptance",
    "ScanAcceptanceLog",
    "ScanHit",
    "ScanKind",
    "SectionHits",
    "hits_by_section",
    "hits_digest",
    "pending_hits",
    "scan_report",
]

MINIMUM_NAME_LENGTH: Final = 4
"""A school or tournament is looked for when it is over three characters."""

DIGEST_LENGTH: Final = 12
"""Hex digits of :func:`hits_digest`: short enough to type, long enough never to repeat by chance."""

_KEY_LENGTH: Final = 16
_DIGITS: Final = re.compile(r"[0-9]+")


class ScanKind(StrEnum):
    """What a hit's term is in the disclosures."""

    TEAM_CODE = "team_code"
    SCHOOL = "school"
    TOURNAMENT = "tournament"
    PATH = "path"


@dataclass(frozen=True, slots=True, order=True)
class ScanHit:
    """One term from the disclosures, found in one line of one of the report's files."""

    file: str
    line_number: int
    """Counted from 1."""
    kind: ScanKind
    term: str
    line: str = field(repr=False)

    @property
    def key(self) -> str:
        """The hit as an acceptance remembers it: its line with every number as `#`, never its place."""
        shape = _DIGITS.sub("#", self.line)
        identity = json.dumps([self.file, self.kind.value, self.term, shape], ensure_ascii=False)
        return hashlib.sha256(identity.encode()).hexdigest()[:_KEY_LENGTH]


@dataclass(frozen=True, slots=True)
class _Term:
    kind: ScanKind
    term: str
    pattern: re.Pattern[str] | None
    """None for a path, which is looked for as a plain substring."""
    folded: str


def _terms(disclosures: Iterable[Disclosure]) -> list[_Term]:
    codes: set[str] = set()
    names: dict[tuple[ScanKind, str], None] = {}
    paths: set[str] = set()
    for one in disclosures:
        if one.team_code != UNKNOWN_TEAM_CODE and one.team_code.strip():
            codes.add(one.team_code)
        if one.school != UNKNOWN_SCHOOL and len(one.school) >= MINIMUM_NAME_LENGTH:
            names[(ScanKind.SCHOOL, one.school)] = None
        if one.tournament and len(one.tournament) >= MINIMUM_NAME_LENGTH:
            names[(ScanKind.TOURNAMENT, one.tournament)] = None
        if one.source_path:
            paths.add(one.source_path)
    terms = [
        _Term(
            ScanKind.TEAM_CODE,
            code,
            re.compile(rf"(?<![A-Za-z0-9]){re.escape(code)}(?![A-Za-z0-9])"),
            code.casefold(),
        )
        for code in sorted(codes)
    ]
    terms += [
        _Term(kind, name, re.compile(rf"(?<!\w){re.escape(name)}(?!\w)", re.IGNORECASE), name.casefold())
        for kind, name in sorted(names)
    ]
    terms += [_Term(ScanKind.PATH, path, None, path.casefold()) for path in sorted(paths)]
    return terms


_SECTIONED_FILE: Final = "report.md"
"""The one file counted by section: the others are counted whole; the school view's headings are schools."""


@dataclass(frozen=True, slots=True)
class SectionHits:
    """How many of the scan's hits of one kind are in one section of one file: a count, never a term."""

    file: str
    section: str
    """report.md's nearest heading over the hits, `: plank table` added inside a CP's plank table
    (`(top)` above every heading); `(whole file)` in every other file."""
    kind: ScanKind
    hits: int
    not_yet_accepted: int


def hits_by_section(
    hits: Sequence[ScanHit], pending: Collection[ScanHit], files: Mapping[str, str]
) -> tuple[SectionHits, ...]:
    """The hits counted by file, report.md's section and kind, in that order (`v1-e32-t16`).

    What the dry run reports of its scan: where the hits are, never what they name.
    """
    counted: dict[tuple[str, tuple[int, int], str, ScanKind], list[int]] = {}
    lines = {name: text.splitlines() for name, text in files.items() if name == _SECTIONED_FILE}
    for hit in hits:
        place, section = (
            _section(lines[hit.file], hit.line_number) if hit.file in lines else ((0, 0), "(whole file)")
        )
        found = counted.setdefault((hit.file, place, section, hit.kind), [0, 0])
        found[0] += 1
        found[1] += hit in pending
    kinds = list(ScanKind)
    return tuple(
        SectionHits(file=file, section=section, kind=kind, hits=total, not_yet_accepted=waiting)
        for (file, _, section, kind), (total, waiting) in sorted(
            counted.items(), key=lambda item: (item[0][0], item[0][1], kinds.index(item[0][3]))
        )
    )


def _section(lines: Sequence[str], number: int) -> tuple[tuple[int, int], str]:
    """The place and name of the section holding line `number` (counted from 1) of report.md."""
    heading, name = 0, "(top)"
    for index in range(min(number, len(lines)) - 1, -1, -1):
        if lines[index].startswith("#"):
            heading, name = index + 1, lines[index].lstrip("#").strip()
            break
    index = number - 1
    while 0 <= index < len(lines) and lines[index].startswith("|"):
        if lines[index] == PLANK_TABLE_HEADER:
            return (heading, index + 1), f"{name}: plank table"
        index -= 1
    return (heading, 0), name


def scan_report(
    files: Mapping[str, str], disclosures: Iterable[Disclosure], *, school_view_files: Collection[str] = ()
) -> tuple[ScanHit, ...]:
    """Every term of `disclosures` found in `files`, one hit per term per line, in file and line order.

    In `school_view_files`, which may name schools, team codes and tournaments, only paths are hits.
    """
    terms = _terms(disclosures)
    paths = [term for term in terms if term.kind is ScanKind.PATH]
    hits: list[ScanHit] = []
    for name in sorted(files):
        looked_for = paths if name in school_view_files else terms
        for number, line in enumerate(files[name].splitlines(), start=1):
            folded = line.casefold()
            for term in looked_for:
                if term.folded not in folded:
                    continue
                if term.pattern is not None and term.pattern.search(line) is None:
                    continue
                hits.append(ScanHit(name, number, term.kind, term.term, line))
    return tuple(sorted(hits))


def hits_digest(hits: Iterable[ScanHit]) -> str:
    """The digest the operator types to accept exactly these hits: of their keys, in no order."""
    keys = "\n".join(sorted({hit.key for hit in hits}))
    return hashlib.sha256(keys.encode()).hexdigest()[:DIGEST_LENGTH]


@dataclass(frozen=True, slots=True)
class ScanAcceptance:
    """One acceptance by the operator: the hits they read, by the digest they typed."""

    caselist: str
    snapshot: date
    accepted_on: date
    digest: str
    hits: tuple[ScanHit, ...] = field(repr=False)

    def as_json(self) -> dict[str, object]:
        return {
            "caselist": self.caselist,
            "snapshot": self.snapshot.isoformat(),
            "accepted_on": self.accepted_on.isoformat(),
            "digest": self.digest,
            "hits": [
                {"key": hit.key, "file": hit.file, "kind": hit.kind.value, "term": hit.term}
                for hit in self.hits
            ],
        }


class ScanAcceptanceLog:
    """The hits an operator accepted for one caselist, a line per acceptance, on this machine only.

    `<data dir>/landscape/scan-acceptances/<caselist>.jsonl`. A line this build cannot read accepts
    nothing, so a damaged log makes the operator read its hits again rather than wave them through.
    """

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def path(self, caselist: str) -> Path:
        return self._directory / f"{caselist}.jsonl"

    def accepted(self, caselist: str) -> frozenset[str]:
        """The keys of every hit accepted for `caselist`, in any run."""
        path = self.path(caselist)
        if not path.is_file():
            return frozenset()
        keys: set[str] = set()
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row: object = json.loads(line)
            except ValueError:
                continue
            hits = cast("dict[str, object]", row).get("hits") if isinstance(row, dict) else None
            for hit in cast("list[object]", hits) if isinstance(hits, list) else []:
                key = cast("dict[str, object]", hit).get("key") if isinstance(hit, dict) else None
                if isinstance(key, str):
                    keys.add(key)
        return frozenset(keys)

    def record(self, acceptance: ScanAcceptance) -> Path:
        """Append `acceptance` as one line, on the disk before this returns."""
        path = self.path(acceptance.caselist)
        path.parent.mkdir(parents=True, exist_ok=True)
        line = (json.dumps(acceptance.as_json(), ensure_ascii=False, sort_keys=True) + "\n").encode()
        descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(descriptor, line)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return path


def pending_hits(hits: Sequence[ScanHit], accepted: frozenset[str]) -> tuple[ScanHit, ...]:
    """The hits no earlier acceptance covers."""
    return tuple(hit for hit in hits if hit.key not in accepted)

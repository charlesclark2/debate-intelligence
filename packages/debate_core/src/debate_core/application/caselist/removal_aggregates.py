"""A removal's rewrite of the parsed store's aggregates without the rows it takes out (`v1-e30-t33`).

Until `v1-e30-t33` a removal deleted every aggregate of every caselist, in every version directory,
and left the next `caselist parse --publish` to rebuild them. Since the cloud cutover that rebuild
cannot run from the operator's machine (its store no longer holds the weeks the cloud ran), and a
backfile's is a cloud task of its own. So, by the PM's ruling of 2026-11-05, a removal now rewrites
each aggregate it reaches without the rows that name what it removes, in place, here and in the bucket,
and purges the older versions as it does a manifest's. Nothing is rebuilt afterwards.

## What a version directory holds (the ruling's (c), third condition)

Every file `caselist parse` writes under `parsed/<caselist>/<version>/`, here and in the bucket
(:mod:`debate_core.application.ports.parsed_store`); nothing else writes there:

* `sha256/ab/cd/<digest>.jsonl`: one source's entry, then its document. All of it is that source's.
* `index.jsonl`: one line per source, its entry with its card count. Every field is that source's.
* `failures.jsonl`: the entry of each source with no document. Every field is that source's.
* `occurrences.jsonl`: one line per card per disclosure. Its source, disclosure, span, snapshots,
  fingerprint and completeness are that card's; `cluster_id` and `membership` are worked out across
  the directory's cards.
* `camp_paths.jsonl` (`openev` only): one line per camp path of a camp file in a release. Its source,
  release and camp path are that file's; `occurrence_table_sha256` is the digest of the table's bytes.

No file holds a count or a statistic across sources: totals and cluster counts are a run's output, and
the search index recomputes its own. The two fields worked out across a directory are kept as they are
on the rows that survive (the ruling's Q3): a cluster whose smallest fingerprint was a removed card's
keeps that id, and a link or a join a removed card made stays, until the caselist's next rebuild. That
is what every reader already sees right after a removal, since each drops the rows the list stops and
keeps the rest (:func:`~debate_core.application.caselist.parse_sources.occurrence_is_stopped`).
`camp_paths.jsonl` names the bytes of the table it was written beside, so a rewrite of the table
re-stamps each of its lines with the new table's digest, or every camp row would lose its camp paths.

## Which rows go (:class:`RowsRemoved`)

The rows a rebuild after the removal would not write, asked of each row alone, and only of a source
the removal names:

* a source it removes whole, or whose copy it takes from this caselist (no other holder there keeps
  it), loses every row: its index and failures entries, every occurrence row, every camp path line;
* a source it withdraws one disclosure of, while another holder in the caselist keeps it, loses the
  occurrence rows the list will stop once the removal's entries are appended, by the row's own rule;
  and for a camp file, the camp path lines the list will stop, and a release's rows when the removal
  leaves no live camp path of it in that release. Its entry stays, as its per-source file does.

## The checks before a rewrite is written

:func:`rewrite_table` streams one table from one file into another, and is the whole of the rewrite:
every line it keeps is the source's line, byte for byte, in order; a line that is not a JSON object
naming a source's SHA-256 raises :class:`UnreadableAggregateLine`, and nothing is written. Then
:func:`check_rewrite` reads both files again, independently of the rule, and refuses a rewrite whose
lines are not the source's less the dropped ones, each dropped one naming a source the removal names,
with as many rows as the source less those dropped. Only a checked rewrite is ever uploaded.

Nothing here logs. A row holds digests, versions and indexes, never a path or a name, but nothing is
said about one anyway.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from debate_core.application.errors import DomainError
from debate_core.application.ports.parsed_store import (
    CAMP_PATHS_NAME,
    FAILURES_NAME,
    INDEX_NAME,
    OCCURRENCES_NAME,
)
from debate_core.application.ports.suppression import SuppressionState

__all__ = [
    "AggregateRewriteRefused",
    "RowsRemoved",
    "TableRewrite",
    "UnreadableAggregateLine",
    "camp_paths_beside",
    "check_rewrite",
    "file_sha256",
    "rewrite_directory",
    "rewrite_table",
]

_DIGEST: Final = re.compile(r"^[0-9a-f]{64}$")
_TABLE_DIGEST_FIELD: Final = "occurrence_table_sha256"
type CampPaths = Mapping[tuple[str, str], tuple[str, ...]]
"""`(release, source) -> camp path digests`, as the camp rows of one table carry them."""


class UnreadableAggregateLine(DomainError):
    """A line of an aggregate the removal reached is not one it can decide about. Nothing was written.

    Says which file and which line, never the line: a row holds no path or name, but a line that is not
    a row could hold anything.
    """

    def __init__(self, table: str, line: int) -> None:
        self.table = table
        self.line = line
        super().__init__(
            f"line {line} of {table} is not a parsed-store row naming its source; nothing was written. "
            "Move the file aside or rebuild it, then run the same removal again"
        )


class AggregateRewriteRefused(DomainError):
    """A rewrite failed its own check, or the table changed since the plan read it. Nothing was written."""

    def __init__(self, table: str, reason: str) -> None:
        self.table = table
        self.reason = reason
        super().__init__(f"{table} was not rewritten: {reason}; run the same removal again")


@dataclass(frozen=True, slots=True)
class RowsRemoved:
    """Which rows of one caselist's aggregates a removal takes out (this module's docstring)."""

    whole: frozenset[str] = frozenset()
    """Sources that lose every row: removed whole, or their copy taken from this caselist."""
    asked: frozenset[str] = frozenset()
    """Sources withdrawn from a disclosure while their copy stays: each row is asked of the list."""
    emptied_releases: frozenset[tuple[str, str]] = frozenset()
    """`(source, release)` of a camp file the removal leaves at no live camp path in that release."""
    state: SuppressionState = SuppressionState()
    """The list as it reads once the removal's entries are appended."""

    @property
    def names_anything(self) -> bool:
        return bool(self.whole or self.asked)

    def names(self, sha256: str) -> bool:
        """Whether a row of this source is one the removal may take out."""
        return sha256 in self.whole or sha256 in self.asked

    def entry_goes(self, row: Mapping[str, object]) -> bool:
        """An `index.jsonl` or `failures.jsonl` line: only a source that loses its copy loses it."""
        return row["source_sha256"] in self.whole

    def occurrence_goes(self, row: Mapping[str, object], camp_paths: CampPaths) -> bool:
        """An `occurrences.jsonl` line, asked as :func:`occurrence_is_stopped` asks a row."""
        sha256, snapshot = str(row["source_sha256"]), str(row.get("snapshot"))
        if sha256 in self.whole:
            return True
        if sha256 not in self.asked:
            return False
        if (sha256, snapshot) in self.emptied_releases:
            return True
        paths = camp_paths.get((snapshot, sha256), ())
        if paths:
            return all(self.state.suppresses(sha256, disclosure=path) for path in paths)
        disclosure = row.get("disclosure")
        return self.state.suppresses(sha256, disclosure=disclosure if isinstance(disclosure, str) else None)

    def camp_path_goes(self, row: Mapping[str, object]) -> bool:
        """A `camp_paths.jsonl` line: its source's rows gone from its release, or its own path stopped."""
        sha256, snapshot = str(row["source_sha256"]), str(row.get("snapshot"))
        if sha256 in self.whole or (sha256, snapshot) in self.emptied_releases:
            return True
        path = row.get("camp_path_disclosure")
        return (
            sha256 in self.asked and isinstance(path, str) and self.state.suppresses(sha256, disclosure=path)
        )


@dataclass(frozen=True, slots=True)
class TableRewrite:
    """What :func:`rewrite_table` found in one table, and wrote when it was given somewhere to write."""

    rows: int
    """Rows in the table as read: every line that is not blank."""
    rows_dropped: int
    bytes: int
    sha256: str
    """Of the table as read."""
    rewritten_sha256: str
    """Of the table as rewritten: the same as :attr:`sha256` when nothing was dropped."""


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def camp_paths_beside(path: Path | None, table_sha256: str, *, table: str) -> CampPaths:
    """`(release, source) -> camp path digests` of the lines of `path` written beside `table_sha256`.

    The rows' own camp paths, as the store gives them on read. A line this cannot read raises
    :class:`UnreadableAggregateLine`: a removal decides about every line, and a camp path it could not
    read could be one the list stops.
    """
    if path is None:
        return {}
    found: dict[tuple[str, str], set[str]] = {}
    for number, row in _rows(path, table):
        if row is None:
            continue
        stamp, camp_path = row.get(_TABLE_DIGEST_FIELD), row.get("camp_path_disclosure")
        if not isinstance(camp_path, str) or not isinstance(stamp, str):
            raise UnreadableAggregateLine(table, number)
        if stamp == table_sha256:
            found.setdefault((str(row.get("snapshot")), str(row["source_sha256"])), set()).add(camp_path)
    return {key: tuple(sorted(paths)) for key, paths in found.items()}


def rewrite_table(
    name: str,
    source: Path,
    target: Path | None,
    rows_removed: RowsRemoved,
    *,
    table: str,
    camp_paths: CampPaths | None = None,
    restamp: tuple[str, str] | None = None,
) -> TableRewrite:
    """Stream `source` into `target` without the rows `rows_removed` takes out; count only, with no target.

    `name` is the aggregate's file name, which says which rule a line is asked. An occurrence table is
    asked with its rows' `camp_paths`; `camp_paths.jsonl` with `restamp`, `(old, new)` table digests:
    each kept line stamped with the old table's digest is stamped with the new one's, and is otherwise
    the source's line. `table` names the file in an error. Raises :class:`UnreadableAggregateLine`,
    having written nothing, for a line it cannot read.
    """
    rows = dropped = 0
    read_digest, kept_digest = hashlib.sha256(), hashlib.sha256()
    size = 0
    incoming = None if target is None else target.with_name(f".{target.name}.incoming")
    stream = None
    if incoming is not None:
        incoming.parent.mkdir(parents=True, exist_ok=True)
        stream = incoming.open("wb")
    try:
        for number, raw, row in _lines(source, table):
            size += len(raw)
            read_digest.update(raw)
            if row is None:
                line = raw
            else:
                rows += 1
                if _goes(name, row, rows_removed, camp_paths or {}):
                    dropped += 1
                    continue
                line = _restamped(raw, row, restamp, table, number) if name == CAMP_PATHS_NAME else raw
            kept_digest.update(line)
            if stream is not None:
                stream.write(line)
    except BaseException:
        if stream is not None:
            stream.close()
        if incoming is not None:
            incoming.unlink(missing_ok=True)
        raise
    if stream is not None and incoming is not None and target is not None:
        stream.close()
        incoming.replace(target)
    return TableRewrite(
        rows=rows,
        rows_dropped=dropped,
        bytes=size,
        sha256=read_digest.hexdigest(),
        rewritten_sha256=kept_digest.hexdigest(),
    )


def rewrite_directory(
    tables: Mapping[str, Path],
    rows_removed: RowsRemoved,
    *,
    label: str,
    into: Path | None = None,
) -> dict[str, TableRewrite | UnreadableAggregateLine]:
    """Each of one version directory's current tables, by file name, counted, and rewritten into `into`
    when it is given (each checked by :func:`check_rewrite` before this returns it).

    The occurrence table goes first: its rows are asked with the camp paths `camp_paths.jsonl` gives
    them, which are the lines stamped with the table's digest, and those lines are then re-stamped with
    the rewritten table's. A table it cannot read is its :class:`UnreadableAggregateLine`; so is a camp
    path file the table's rows could not be asked without. `label` names the directory in an error.
    """
    done: dict[str, TableRewrite | UnreadableAggregateLine] = {}
    camp_paths: CampPaths = {}
    restamp: tuple[str, str] | None = None
    occurrences = tables.get(OCCURRENCES_NAME)
    beside = tables.get(CAMP_PATHS_NAME)
    if occurrences is not None:
        try:
            camp_paths = camp_paths_beside(
                beside, file_sha256(occurrences), table=f"{label}/{CAMP_PATHS_NAME}"
            )
        except UnreadableAggregateLine as unreadable:
            done[CAMP_PATHS_NAME] = unreadable
    order = [
        name for name in (OCCURRENCES_NAME, INDEX_NAME, FAILURES_NAME, CAMP_PATHS_NAME) if name in tables
    ]
    for name in order:
        if name in done:
            continue
        table = f"{label}/{name}"
        target = None if into is None else into / name
        try:
            result = rewrite_table(
                name,
                tables[name],
                target,
                rows_removed,
                table=table,
                camp_paths=camp_paths,
                restamp=restamp if name == CAMP_PATHS_NAME else None,
            )
        except UnreadableAggregateLine as unreadable:
            done[name] = unreadable
            continue
        if target is not None:
            check_rewrite(
                tables[name],
                target,
                rows_removed,
                result,
                table=table,
                restamp=restamp if name == CAMP_PATHS_NAME else None,
            )
        done[name] = result
        if name == OCCURRENCES_NAME:
            restamp = (result.sha256, result.rewritten_sha256)
    return done


def check_rewrite(
    source: Path,
    target: Path,
    rows_removed: RowsRemoved,
    expected: TableRewrite,
    *,
    table: str,
    restamp: tuple[str, str] | None = None,
) -> None:
    """Refuse a rewrite that is not the source less the dropped rows: the ruling's check, independent of
    the rule that chose them.

    Reads both files again: every line of `target` is the next line of `source` that is kept, byte for
    byte (with the table digest re-stamped, for `camp_paths.jsonl`); every line skipped names a source
    the removal names; and `target` holds as many rows as `source` less those dropped, which is the
    number the rewrite reported. Raises :class:`AggregateRewriteRefused` otherwise.
    """
    written = _lines(target, table)
    pending = next(written, None)
    rows = skipped = 0
    for number, raw, row in _lines(source, table):
        if row is not None:
            rows += 1
        line = raw if row is None or restamp is None else _restamped(raw, row, restamp, table, number)
        if pending is not None and pending[1] == line:
            pending = next(written, None)
            continue
        if row is None or not rows_removed.names(str(row["source_sha256"])):
            raise AggregateRewriteRefused(table, f"line {number} was left out and names nothing removed")
        skipped += 1
    if pending is not None:
        raise AggregateRewriteRefused(table, "the rewrite holds a line the table did not")
    if (rows, skipped, file_sha256(target)) != (
        expected.rows,
        expected.rows_dropped,
        expected.rewritten_sha256,
    ):
        raise AggregateRewriteRefused(table, "the rewrite does not hold the table's rows less those dropped")


def _goes(name: str, row: Mapping[str, object], rows_removed: RowsRemoved, camp_paths: CampPaths) -> bool:
    if name in (INDEX_NAME, FAILURES_NAME):
        return rows_removed.entry_goes(row)
    if name == OCCURRENCES_NAME:
        return rows_removed.occurrence_goes(row, camp_paths)
    if name == CAMP_PATHS_NAME:
        return rows_removed.camp_path_goes(row)
    raise ValueError(f"not an aggregate a removal rewrites: {name}")


def _restamped(
    raw: bytes, row: Mapping[str, object], restamp: tuple[str, str] | None, table: str, number: int
) -> bytes:
    """A camp path line stamped with the new table's digest, when it was stamped with the old one's."""
    if restamp is None or row.get(_TABLE_DIGEST_FIELD) != restamp[0]:
        return raw
    old, new = (f'"{_TABLE_DIGEST_FIELD}":"{digest}"'.encode() for digest in restamp)
    if raw.count(old) != 1:
        raise UnreadableAggregateLine(table, number)
    return raw.replace(old, new)


def _lines(path: Path, table: str):  # noqa: ANN202 - a generator of (number, raw line, row or None)
    """Each line of `path` as bytes, with its row, or `None` for a blank line, which no reader reads."""
    with path.open("rb") as stream:
        for number, raw in enumerate(stream, start=1):
            if not raw.strip():
                yield number, raw, None
                continue
            yield number, raw, _row(raw, table, number)


def _rows(path: Path, table: str):  # noqa: ANN202 - a generator of (number, row or None)
    for number, _, row in _lines(path, table):
        yield number, row


def _row(raw: bytes, table: str, number: int) -> dict[str, object]:
    try:
        row: object = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise UnreadableAggregateLine(table, number) from None
    if not isinstance(row, dict):
        raise UnreadableAggregateLine(table, number)
    fields: dict[str, object] = row  # pyright: ignore[reportUnknownVariableType]
    digest = fields.get("source_sha256")
    if not isinstance(digest, str) or _DIGEST.match(digest) is None:
        raise UnreadableAggregateLine(table, number)
    return fields

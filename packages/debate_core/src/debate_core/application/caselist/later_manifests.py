"""After a weekly is imported late, measure the manifests dated after it again (`v1-e30-t18`).

A weekly is classified against the latest weekly dated before it, so one imported late is
classified as it would have been in date order. What it changes is in the snapshots after it, whose
manifests were written without it (`v1-e30-t17`):

* **The next weekly** named the week before the late one as its previous week, and its
  classifications, its `REMOVED` rows and their counts were measured against that week.
* **Every later weekly's first-seen count** counted what the late week brought as first seen there.
* **The newest complete archive**, if it is dated after the late week, counted its withdrawals
  without it.

The archives are usually gone by then (the inbox keeps them only until they are published), so
:class:`LaterManifests` measures again from what the store already holds, and never reads an
archive (PM ruling, `v1-e30-t18`). After every weekly import, `caselist import` and `caselist pull`
hand the import's report to :meth:`LaterManifests.after_weekly_import`, which rewrites each manifest
whose bytes the measuring changes, to the manifest a date-order run writes. A manifest that does not
change is not written, so a weekly imported in date order rewrites nothing.

**Only a weekly's first import is measured in.** A week already imported was there when the weeks
after it were measured (:attr:`~debate_core.application.caselist.import_service.ImportReport.
imported_before`), so importing it again measures nothing again and writes its own manifest alone
(PM ruling 2). That is what leaves a removal's rewrite of a later week as the removal left it when
an older week is imported again, which the removal runbook's Step 6 does.

## A later weekly

Its member rows do not change: they are what its archive held, path by path, with the school, team,
round and digest the import read. What is measured again is what each was relative to the week
before:

* **The previous week** is the latest weekly dated before it among the snapshot records, as the
  importer finds it.
* **Each member row's classification** is decided by the importer's own rule
  (:func:`~debate_core.application.caselist.pipeline.classify_stored`), against that week's
  disclosures and the digests the rows before it in this manifest name.
* **`REMOVED` rows** are the previous week's paths the archive did not hold, as the importer adds
  them. What the archive held is its member rows' paths, and also each path of its old previous
  week that its old `REMOVED` rows leave out: a member the suppression list stopped has no row, but
  the import saw its path, and did not report that path `REMOVED`.
* **The summary's `classifications`** are counted from those rows, with the `SUPPRESSED` count kept
  as it was. Every other summary key but two is a fact about the archive and is kept.
* **`previous_snapshot`** is the new previous week, and **`first_seen`** moves by what the late
  weekly brings: less each digest of this week's rows that it holds and no other weekly manifest
  dated before this week does. Not counted afresh from the rows, because a removal keeps a
  manifest's first-seen count as the import recorded it when it drops a row
  (:mod:`~debate_core.application.caselist.removal_plan`), and a count from the rows would undo
  that. A manifest written before first-seen existed, or without a way to count it, keeps what it had.

## The newest complete archive

Its withdrawals are counted again when the weekly is dated before it: against every manifest dated
before it, weekly and complete, as its import counts them
(:func:`~debate_core.application.caselist.evidence_listing.snapshots_before_full_archive`), and
against the stored rows of its own manifest. Only its summary's `withdrawn`, `superseded` and
`earlier_snapshots` change, and its member rows are kept byte for byte. Only the newest one is
counted again (PM ruling 3); an older complete archive keeps the count it was imported with. Nothing
waits for a gap in the weekly series to close: the complete archive is imported when it arrives, and
counted again when the weekly does.

## What this cannot see

A member the suppression list stopped has no manifest row. Measuring again infers the paths of a
later week's stopped members from its old previous week, as above, which misses one the old
previous week did not hold: if the late week holds that path, it is reported `REMOVED`. And a
complete archive's import counts a stopped member as still present, which its recount cannot. Neither
changes what is stored, and neither arises without a removal and a late import together.

## What it never touches

The blobs, the source records and their seen ranges, the disclosures, the snapshot records and the
suppression list are read and never written. Nothing is logged but counts and snapshot names
(`docs/policies/caselist-data-use.md` rule 4).

## If it stops partway

Every rewrite is worked out before the first is written, so an unreadable manifest stops it before
anything is written. Each manifest is then written atomically and on its own: a failure to write one
leaves those before it rewritten, and those after it as they were.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from debate_core.application.caselist.evidence_listing import (
    LocalEvidence,
    digests_in_each_earlier_manifest,
    snapshots_before_full_archive,
)
from debate_core.application.caselist.import_service import (
    STORED_CLASSIFICATIONS,
    Classification,
    ImportedEntry,
    ImportReport,
)
from debate_core.application.caselist.manifest import (
    DISCLOSURE_FIELDS,
    common_member_fields,
    full_archive_manifest_key,
    manifest_key,
    read_manifest_lines,
    render_rows,
    write_manifest_lines,
)
from debate_core.application.caselist.pipeline import classify_stored
from debate_core.application.caselist.publish_plan import (
    UnreadableManifest,
    full_archive_date,
    full_archive_snapshot,
    manifest_prefix,
    snapshot_of_manifest_key,
    stored_rows_in_manifest,
)
from debate_core.application.caselist.suppression import load_suppression_state
from debate_core.application.caselist.withdrawals import WithdrawalCount, count_withdrawals
from debate_core.application.errors import DomainError
from debate_core.application.ports.caselist import CaselistRepository
from debate_core.application.ports.evidence_store import ObjectKey
from debate_core.application.ports.suppression import SuppressionList, SuppressionState

__all__ = [
    "CompleteArchiveRecount",
    "LaterManifests",
    "LaterManifestsNotWritable",
    "LaterManifestsRemeasured",
]

logger = logging.getLogger(__name__)

_STORED_NAMES = frozenset(str(classification) for classification in STORED_CLASSIFICATIONS)
_REMOVED = str(Classification.REMOVED)
_SUPPRESSED = str(Classification.SUPPRESSED)


class LaterManifestsNotWritable(DomainError):
    """The local evidence store names no file for a manifest, so none can be rewritten in place."""

    def __init__(self) -> None:
        super().__init__(
            "the later manifests cannot be measured again: this evidence store names no file for a manifest"
        )


@dataclass(frozen=True, slots=True)
class CompleteArchiveRecount:
    """The newest complete archive's withdrawals, counted again after an earlier-dated weekly."""

    caselist: str
    snapshot: str
    """`full/<date>`."""

    before: WithdrawalCount
    """What its manifest said."""

    after: WithdrawalCount
    """What it says now."""

    def sentence(self) -> str:
        """One clause for a run's import stage, beside the complete archives it imported. Counts only."""
        return (
            f"complete archive {self.caselist} {self.snapshot} recounted after an earlier-dated weekly: "
            f"{self.after.withdrawn} withdrawn, {self.after.superseded} superseded against "
            f"{self.after.earlier_snapshots} earlier snapshot(s)"
        )

    def as_json(self) -> dict[str, object]:
        return {
            "caselist": self.caselist,
            "snapshot": self.snapshot,
            "withdrawn": self.after.withdrawn,
            "superseded": self.after.superseded,
            "earlier_snapshots": self.after.earlier_snapshots,
        }


@dataclass(frozen=True, slots=True)
class LaterManifestsRemeasured:
    """What measuring the later manifests again rewrote."""

    caselist: str
    weeklies: tuple[str, ...] = ()
    """The weekly manifests rewritten, in date order."""

    complete_archive: CompleteArchiveRecount | None = None
    """The newest complete archive, when its withdrawals were counted again and changed."""

    @property
    def rewritten(self) -> tuple[str, ...]:
        """Every snapshot whose manifest was rewritten: the weeklies in date order, then `full/<date>`."""
        full = (self.complete_archive.snapshot,) if self.complete_archive is not None else ()
        return (*self.weeklies, *full)


class LaterManifests:
    """Measures again the manifests a weekly imported out of date order leaves stale.

    Takes the ports the importer reads, and the local evidence store the manifests are in::

        later = LaterManifests(
            caselists=SqliteCaselistRepository(database),
            local=local_evidence,
            suppression=RecordedSuppressionList(local_suppression_list_file(data_dir)),
        )
        remeasured = await later.after_weekly_import(report)  # the weekly import's own report

    The suppression list is the one the import read: every row is checked against it again as it is
    rendered, before any manifest is written.
    """

    def __init__(
        self, *, caselists: CaselistRepository, local: LocalEvidence, suppression: SuppressionList
    ) -> None:
        self._caselists = caselists
        self._local = local
        self._suppression = suppression

    async def after_weekly_import(self, report: ImportReport) -> LaterManifestsRemeasured:
        """Measure again every weekly manifest dated after `report`'s, and the newest complete archive.

        Call it with a weekly's report once its manifest is written, since the later weeks'
        first-seen counts read that manifest. Measures nothing for a dry run, a complete archive, or
        a week imported before; otherwise rewrites only the manifests that change.
        """
        caselist, snapshot = report.caselist, report.snapshot
        if not report.applied or report.full_archive or report.imported_before:
            return LaterManifestsRemeasured(caselist=caselist)
        weeklies, complete_archives = await self._manifest_dates(caselist)
        later = sorted(day for day in weeklies if day > snapshot)
        newest_complete = max(complete_archives, default=None)
        recount_due = newest_complete is not None and newest_complete > snapshot
        if not later and not recount_due:
            return LaterManifestsRemeasured(caselist=caselist)

        suppression = await load_suppression_state(self._suppression)
        held = sorted(stored.snapshot for stored in await self._caselists.list_snapshots(caselist))
        writes: list[tuple[Path, list[str]]] = []
        rewritten: list[str] = []
        for day in later:
            previous = max((one for one in held if one < day), default=None)
            measured = await self._measured_again(caselist, day, previous, suppression, late=snapshot)
            if measured is not None:
                writes.append(measured)
                rewritten.append(day.isoformat())
        recount = None
        if recount_due and newest_complete is not None:
            recounted = await self._recounted(caselist, newest_complete, suppression)
            if recounted is not None:
                recount, written = recounted
                writes.append(written)
        for path, lines in writes:
            write_manifest_lines(lines, path)
        result = LaterManifestsRemeasured(
            caselist=caselist, weeklies=tuple(rewritten), complete_archive=recount
        )
        logger.info(
            "measured later caselist manifests again",
            extra={
                "caselist": caselist,
                "snapshot": snapshot.isoformat(),
                "later_weeklies": len(later),
                "rewritten": list(result.rewritten),
            },
        )
        return result

    # --------------------------------------------------------------------------------------
    # A later weekly
    # --------------------------------------------------------------------------------------

    async def _measured_again(
        self, caselist: str, day: date, previous: date | None, suppression: SuppressionState, *, late: date
    ) -> tuple[Path, list[str]] | None:
        """One weekly's manifest measured again, as `(path, lines)`, or `None` when it does not change."""
        key = manifest_key(caselist, day)
        path = self._path_for(key)
        lines = read_manifest_lines(path)
        if not lines:
            return None
        members, summary = _rows_and_summary(key, lines)
        baseline = await self._disclosures_in(caselist, previous)
        rows, counts, stored = _classified_again(key, members, baseline=baseline)
        held_paths = _member_paths(members) | await self._stopped_paths(
            key, len(lines), caselist, members, summary
        )
        for gone in sorted(baseline.keys() - held_paths):
            counts[_REMOVED] = counts.get(_REMOVED, 0) + 1
            rows.append(_removed_row(gone))
        suppressed = _suppressed_count(summary)
        if suppressed > 0:
            counts[_SUPPRESSED] = suppressed
        measured: dict[str, object] = {
            **summary,
            "previous_snapshot": previous.isoformat() if previous is not None else None,
            "classifications": {name: counts[name] for name in sorted(counts) if counts[name] > 0},
        }
        first_seen = summary.get("first_seen")
        if isinstance(first_seen, int):
            measured["first_seen"] = first_seen - await self._first_seen_only_through(
                caselist, day, stored, late=late
            )
        rows.sort(key=lambda row: str(row["path"]))
        rendered = render_rows([*rows, measured], suppression=suppression, disclosure_scope=caselist)
        return None if rendered == list(lines) else (path, rendered)

    async def _stopped_paths(
        self,
        key: ObjectKey,
        line: int,
        caselist: str,
        members: Sequence[Mapping[str, object]],
        summary: Mapping[str, object],
    ) -> set[str]:
        """Paths the archive held whose members have no row: its old previous week's, not reported gone.

        The import reported `REMOVED` each path of its previous week that the archive did not hold.
        So a path of that week with no `REMOVED` row and no member row is one the archive held, for
        a member the suppression list stopped.
        """
        named = summary.get("previous_snapshot")
        if named is None:
            return set()
        if not isinstance(named, str):
            raise UnreadableManifest(key, line, "the summary's previous snapshot is not a date")
        try:
            old_previous = date.fromisoformat(named)
        except ValueError as unreadable:
            raise UnreadableManifest(
                key, line, "the summary's previous snapshot is not a date"
            ) from unreadable
        reported_gone = {str(row["path"]) for row in members if row.get("classification") == _REMOVED}
        return set((await self._disclosures_in(caselist, old_previous)).keys()) - reported_gone

    async def _first_seen_only_through(
        self, caselist: str, day: date, stored: set[str], *, late: date
    ) -> int:
        """How many of `stored` the late weekly's manifest holds and no other weekly before `day` does."""
        earlier = await digests_in_each_earlier_manifest(self._local, caselist, day)
        brought = earlier.get(late.isoformat(), frozenset())
        elsewhere = frozenset[str]().union(
            *(digests for name, digests in earlier.items() if name != late.isoformat())
        )
        return len((stored & brought) - elsewhere)

    async def _disclosures_in(self, caselist: str, snapshot: date | None) -> dict[str, str]:
        """What a weekly said, as `{source path: sha256}`: the importer's baseline, read the same way."""
        if snapshot is None:
            return {}
        baseline: dict[str, str] = {}
        cursor: str | None = None
        while True:
            page = await self._caselists.list_disclosures(
                caselist=caselist, snapshot=snapshot, limit=500, cursor=cursor
            )
            baseline.update({disclosure.source_path: disclosure.source_sha256 for disclosure in page.items})
            if not page.has_more:
                return baseline
            cursor = page.next_cursor

    # --------------------------------------------------------------------------------------
    # The newest complete archive
    # --------------------------------------------------------------------------------------

    async def _recounted(
        self, caselist: str, archive_date: date, suppression: SuppressionState
    ) -> tuple[CompleteArchiveRecount, tuple[Path, list[str]]] | None:
        """The complete archive's withdrawals counted again, and its manifest; `None` if unchanged."""
        key = full_archive_manifest_key(caselist, archive_date)
        path = self._path_for(key)
        lines = read_manifest_lines(path)
        if not lines:
            return None
        members, summary = _rows_and_summary(key, lines)
        before = _withdrawals_in(key, len(lines), summary)
        _, earlier = await snapshots_before_full_archive(self._local, caselist, archive_date)
        after = count_withdrawals(earlier, stored_rows_in_manifest(lines))
        if after == before:
            return None
        recounted = {
            **summary,
            "withdrawn": after.withdrawn,
            "superseded": after.superseded,
            "earlier_snapshots": after.earlier_snapshots,
        }
        recount = CompleteArchiveRecount(
            caselist=caselist, snapshot=full_archive_snapshot(archive_date), before=before, after=after
        )
        rendered = render_rows([*members, recounted], suppression=suppression, disclosure_scope=caselist)
        return recount, (path, rendered)

    # --------------------------------------------------------------------------------------
    # The store
    # --------------------------------------------------------------------------------------

    async def _manifest_dates(self, caselist: str) -> tuple[list[date], list[date]]:
        """The dates of this caselist's weekly and complete-archive manifests, from the key names alone."""
        weeklies: list[date] = []
        complete: list[date] = []
        for info in await self._local.objects.list_objects(manifest_prefix(caselist)):
            named = snapshot_of_manifest_key(caselist, info.key, full_archives=True)
            if named is None:
                continue
            full = full_archive_date(named)
            if full is not None:
                complete.append(full)
            else:
                weeklies.append(date.fromisoformat(named))
        return weeklies, complete

    def _path_for(self, key: ObjectKey) -> Path:
        path_for = self._local.object_path_for
        if path_for is None:
            raise LaterManifestsNotWritable
        return path_for(key)


def _rows_and_summary(
    key: ObjectKey, lines: Sequence[str]
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """A manifest's member rows, in order, and its one summary row, which is last."""
    rows: list[dict[str, object]] = []
    for number, line in enumerate(lines, start=1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as unreadable:
            raise UnreadableManifest(key, number, "not JSON") from unreadable
        if not isinstance(row, dict):
            raise UnreadableManifest(key, number, "not a JSON object")
        fields: dict[str, object] = row  # pyright: ignore[reportUnknownVariableType]
        rows.append(fields)
    if not rows or rows[-1].get("kind") != "summary":
        raise UnreadableManifest(key, len(lines), "the last row is not the summary")
    *members, summary = rows
    for number, row in enumerate(members, start=1):
        if row.get("kind") != "member" or not isinstance(row.get("path"), str):
            raise UnreadableManifest(key, number, "a row before the summary is not a member row")
    return members, summary


def _suppressed_count(summary: Mapping[str, object]) -> int:
    """The `SUPPRESSED` count a summary records: members the list stopped, which have no rows."""
    counts = summary.get("classifications")
    if not isinstance(counts, dict):
        return 0
    recorded: dict[str, object] = counts  # pyright: ignore[reportUnknownVariableType]
    suppressed = recorded.get(_SUPPRESSED, 0)
    return suppressed if isinstance(suppressed, int) else 0


def _member_paths(members: Sequence[Mapping[str, object]]) -> set[str]:
    """The paths of the members the archive held and the import classified: no skipped or REMOVED row."""
    return {
        str(row["path"])
        for row in members
        if row.get("classification") is not None and row.get("classification") != _REMOVED
    }


def _classified_again(
    key: ObjectKey, members: Sequence[Mapping[str, object]], *, baseline: Mapping[str, str]
) -> tuple[list[dict[str, object]], dict[str, int], set[str]]:
    """Every member row classified again against `baseline`, in the importer's order.

    Returns the rows without the old `REMOVED` ones, the counts, and the digests the rows store.
    `known` grows row by row in path order, as the importer's set of digests stored so far does, so
    the second copy of a file in one archive is a `DUPLICATE` here exactly when it was there.
    """
    baseline_digests = frozenset(baseline.values())
    known: set[str] = set()
    rows: list[dict[str, object]] = []
    counts: dict[str, int] = {}
    for number, row in enumerate(members, start=1):
        classification = row.get("classification")
        if classification == _REMOVED:
            continue
        if classification is None:
            rows.append(dict(row))
            continue
        digest = row.get("sha256")
        if classification not in _STORED_NAMES or not isinstance(digest, str):
            raise UnreadableManifest(key, number, "a member row is neither stored, skipped nor REMOVED")
        measured = str(
            classify_stored(
                str(row["path"]), digest, baseline=baseline, baseline_digests=baseline_digests, known=known
            )
        )
        known.add(digest)
        counts[measured] = counts.get(measured, 0) + 1
        rows.append({**row, "classification": measured})
    return rows, counts, known


def _removed_row(path: str) -> dict[str, object]:
    """A `REMOVED` row exactly as the importer's manifest writer renders one."""
    return {
        **common_member_fields(ImportedEntry[object](path=path, classification=Classification.REMOVED), ()),
        **dict.fromkeys(DISCLOSURE_FIELDS),
    }


def _withdrawals_in(key: ObjectKey, line: int, summary: Mapping[str, object]) -> WithdrawalCount:
    """The withdrawal counts a complete archive's summary records."""
    counts = [summary.get(name) for name in ("withdrawn", "superseded", "earlier_snapshots")]
    withdrawn, superseded, earlier = counts
    if not (isinstance(withdrawn, int) and isinstance(superseded, int) and isinstance(earlier, int)):
        raise UnreadableManifest(key, line, "a complete archive's summary carries no withdrawal counts")
    return WithdrawalCount(withdrawn=withdrawn, superseded=superseded, earlier_snapshots=earlier)

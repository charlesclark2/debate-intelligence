"""After a weekly is imported, measure the manifests dated after it again (`v1-e30-t18`).

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
call :meth:`LaterManifests.after_weekly_import`, and it rewrites each manifest whose bytes the
measuring changes, to the manifest a date-order run writes. A manifest that does not change is not
written, so a weekly imported in date order, or a week imported again, rewrites nothing.

## A later weekly

Its member rows do not change: they are what its archive held, path by path, with the school, team,
round and digest the import read. What is measured again is what each was relative to the week
before:

* **The previous week** is the latest weekly dated before it among the snapshot records, as the
  importer finds it.
* **Each member row's classification** is decided by the importer's own rule
  (:func:`~debate_core.application.caselist.pipeline.classify_stored`), against that week's
  disclosures and the digests the rows before it in this manifest name.
* **`REMOVED` rows** are the previous week's paths no member row names, as the importer adds them,
  except a path a removal holds for this week's date (`v1-e30-t13`). See "What this cannot see".
* **The summary's `classifications`** are counted from those rows, with the `SUPPRESSED` count kept
  as it was, and **`first_seen`** is taken again against the weekly manifests dated before it
  (:func:`~debate_core.application.caselist.evidence_listing.digests_in_earlier_manifests`). Every
  other summary key is a fact about the archive and is kept. A manifest written before first-seen
  existed, or without a way to count it, keeps what it had.

## The newest complete archive

Its withdrawals are counted again when the weekly is dated before it: against every manifest dated
before it, weekly and complete, as its import counts them
(:func:`~debate_core.application.caselist.evidence_listing.snapshots_before_full_archive`), and
against the stored rows of its own manifest. Only its summary's `withdrawn`, `superseded` and
`earlier_snapshots` change, and its member rows are kept byte for byte. Only the newest one is
counted again (PM ruling, `v1-e30-t18`); an older complete archive keeps the count it was imported
with. Nothing waits for a gap in the weekly series to close: the complete archive is imported when
it arrives, and counted again when the weekly does.

## What this cannot see

A member the suppression list stopped has no manifest row, so measuring again cannot know its path
or its digest. Two numbers can then differ from what the import counted:

* A path the previous week held, where a later week's member was stopped by its bytes or by its
  team's withdrawn copy, is reported `REMOVED`. One a removal holds for that week's date is not,
  as `caselist remove` drops a `REMOVED` row at a path that held the removed file.
* A complete archive's import counts a stopped member as still present, and its recount cannot.

Neither changes what is stored, and neither arises without a removal and a late import together.

## What it never touches

The blobs, the source records and their seen ranges, the disclosures, the snapshot records and the
suppression list are read and never written. Nothing is logged but counts and snapshot names
(`docs/policies/caselist-data-use.md` rule 4).

## If it stops partway

Each manifest is written atomically and on its own, so a failure leaves some rewritten and some
not. Importing the late week again, now with no flag, measures them all again, and the ones already
rewritten are left alone.
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
    digests_in_earlier_manifests,
    snapshots_before_full_archive,
)
from debate_core.application.caselist.import_service import (
    STORED_CLASSIFICATIONS,
    Classification,
    ImportedEntry,
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
        remeasured = await later.after_weekly_import("hsld26", date(2026, 9, 8))

    The suppression list is the one the import read: every row is checked against it again as it is
    rendered, and a removal's hold decides which `REMOVED` rows are left out.
    """

    def __init__(
        self, *, caselists: CaselistRepository, local: LocalEvidence, suppression: SuppressionList
    ) -> None:
        self._caselists = caselists
        self._local = local
        self._suppression = suppression

    async def after_weekly_import(self, caselist: str, snapshot: date) -> LaterManifestsRemeasured:
        """Measure again every weekly manifest dated after `snapshot`, and the newest complete archive.

        Call it after the weekly of `snapshot` is imported and its manifest written, since the
        later weeks' first-seen counts read it. Rewrites only the manifests that change.
        """
        weeklies, complete_archives = await self._manifest_dates(caselist)
        later = sorted(day for day in weeklies if day > snapshot)
        newest_complete = max(complete_archives, default=None)
        recount_due = newest_complete is not None and newest_complete > snapshot
        if not later and not recount_due:
            return LaterManifestsRemeasured(caselist=caselist)

        suppression = await load_suppression_state(self._suppression)
        held = sorted(stored.snapshot for stored in await self._caselists.list_snapshots(caselist))
        rewritten: list[str] = []
        for day in later:
            previous = max((one for one in held if one < day), default=None)
            if await self._measure_weekly_again(caselist, day, previous, suppression):
                rewritten.append(day.isoformat())
        recount = (
            await self._recount_complete_archive(caselist, newest_complete, suppression)
            if recount_due and newest_complete is not None
            else None
        )
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

    async def _measure_weekly_again(
        self, caselist: str, day: date, previous: date | None, suppression: SuppressionState
    ) -> bool:
        """Rewrite one weekly's manifest if measuring it again changes it; whether it did."""
        key = manifest_key(caselist, day)
        path = self._path_for(key)
        lines = read_manifest_lines(path)
        if not lines:
            return False
        members, summary = _rows_and_summary(key, lines)
        baseline = await self._disclosures_in(caselist, previous)
        rows, counts, stored = _classified_again(key, members, baseline=baseline)
        for gone in sorted(baseline.keys() - _member_paths(members)):
            if suppression.path_hold(caselist=caselist, path=gone, snapshot=day) is not None:
                continue
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
        if summary.get("first_seen") is not None:
            measured["first_seen"] = len(
                stored - await digests_in_earlier_manifests(self._local, caselist, day)
            )
        rows.sort(key=lambda row: str(row["path"]))
        return self._write_if_changed(path, lines, [*rows, measured], suppression, caselist)

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

    async def _recount_complete_archive(
        self, caselist: str, archive_date: date, suppression: SuppressionState
    ) -> CompleteArchiveRecount | None:
        """Count the complete archive's withdrawals again; rewrite its summary if they changed."""
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
        self._write_if_changed(path, lines, [*members, recounted], suppression, caselist)
        return CompleteArchiveRecount(
            caselist=caselist, snapshot=full_archive_snapshot(archive_date), before=before, after=after
        )

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

    @staticmethod
    def _write_if_changed(
        path: Path,
        lines: Sequence[str],
        rows: Sequence[Mapping[str, object]],
        suppression: SuppressionState,
        caselist: str,
    ) -> bool:
        """Render `rows` as the importer renders them, and write them only if they differ from `lines`."""
        rendered = render_rows(rows, suppression=suppression, disclosure_scope=caselist)
        if rendered == list(lines):
            return False
        write_manifest_lines(rendered, path)
        return True


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

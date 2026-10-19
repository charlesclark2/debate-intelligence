"""Which noncurrent manifest versions a removal's sweep deletes (`v1-e30-t07`, `v1-e30-t19`).

A removal rewrites each manifest that names what it removes and purges every other version of that
key. The sweep is what comes after: noncurrent versions of manifests the run did not rewrite just
now, which can still hold a removed row. A restorable version of a removed row is the row not
removed. The dry run asks it with the everyday profile, to count what the execution will delete,
and the execution asks it again with the takedown profile and deletes what it says.

## Two rules, and nothing else

1. **A version that names something removed.** Every noncurrent version of every manifest of the
   caselists the removal affects, except a key the run rewrites now, is read row by row, and goes
   if a row names what the removal took out (:class:`~debate_core.application.caselist.
   removal_plan.RemovalPlan`'s `names_removed`). The sweep since `v1-e30-t07`.
2. **A version an earlier run of the same request should have purged** (`v1-e30-t19`,
   `v1-e30-t24`). Each manifest an earlier run of the request rewrote in the bucket is recorded,
   with the version its rewrite is, in the scope beside that run's log entry (`v1-e30-t15`), and
   the run purged every other version of the key then. Which of the key's versions the sweep takes
   depends on how that run ended (:class:`EarlierRewrite`):

   * **A run that completed**: every version
     :func:`~debate_core.application.caselist.removal_residue.purge_should_have_taken`, the rule
     `caselist status` counts them by, so the same removal run again clears what status reports:
     a noncurrent version other than the rewrite, older than the run's completion less the
     clock-skew margin. Before `v1-e30-t24` this rule, too, was the stopped run's below, and a
     version stamped between the rewrite and the completion less the margin was counted and never
     cleared: one in the same second as the rewrite, or a publish from another machine while the
     run carried on more than fifteen minutes after its rewrite. The bucket need not still hold the
     rewrite: a version is compared with the run's completion, which the log records.
   * **A run that stopped**, or whose log entry the log does not hold: a noncurrent version strictly
     older than the rewrite, by the store's own time. Status compares nothing with such a run, so
     nothing it reports waits on this; the rewrite's purge was done when the scope recorded it, and
     a version older than the rewrite is one it should have taken. Where the bucket no longer holds
     the rewrite, nothing of that key is taken by this rule: older than it cannot be told.

## What it never takes

* The current version of any key, by either rule.
* The latest rewrite of a key by this request: no run's rule takes its own rewrite, and every
  earlier run had ended before it was written.
* A version written after the last completed run that rewrote its key, less the margin, and no
  older than a stopped run's rewrite of it: a re-import published since is an ordinary later write.
* A version of a key no run of this request rewrote that names nothing removed: another request's
  rewrite, or another environment's, is not this request's (`completed_removals` keeps them apart in
  the same way).
* A delete marker. It holds nothing.

So it deletes nothing outside a key the removal rewrote or a version that names what it removed:
the spec's forbidden list.
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from debate_core.application.caselist.publish_plan import manifest_prefix
from debate_core.application.caselist.removal_residue import purge_should_have_taken
from debate_core.application.ports.evidence_store import ObjectKey
from debate_core.application.ports.evidence_versions import EvidenceVersionStore, ObjectVersion
from debate_core.application.ports.suppression import (
    ManifestRewriteRecord,
    RemovalLogEntry,
    RemovalLogKind,
    RemovalOutcome,
    RemovalScopeEntry,
)

__all__ = [
    "EarlierRewrite",
    "NamesRemoved",
    "earlier_rewrites",
    "left_by_earlier_runs",
    "swept_manifest_versions",
]

type NamesRemoved = Callable[[str, str, ObjectKey], bool]
"""Whether one line of a manifest of `caselist`, at `key`, names something the removal took out."""


@dataclass(frozen=True, slots=True)
class EarlierRewrite:
    """One manifest an earlier run of the request rewrote, and how that run ended."""

    record: ManifestRewriteRecord
    """The key and the version its rewrite is, as the run's scope records them."""
    completed_at: datetime | None
    """The run's completion, from its `COMPLETED` log entry; `None` for a run that stopped, or whose
    entry the log does not hold, which the sweep holds to the rewrite itself."""


def earlier_rewrites(
    entries: Sequence[RemovalLogEntry],
    scopes: Sequence[RemovalScopeEntry],
    *,
    request_id: str,
    environment: str,
) -> tuple[EarlierRewrite, ...]:
    """The manifests this request's earlier runs in `environment` rewrote, from their scopes.

    Every run's, completed or stopped: a scope records a rewrite only once its purge is done. A run
    completed when a `COMPLETED` log entry is the one its scope joins
    (:meth:`~debate_core.application.ports.suppression.RemovalScopeEntry.joins`), as
    :func:`~debate_core.application.caselist.removal_residue.completed_removals` reads it. Another
    request's, or another environment's, are not this request's to sweep.
    """
    completed = [
        entry
        for entry in entries
        if entry.kind is RemovalLogKind.REMOVAL and entry.outcome is RemovalOutcome.COMPLETED
    ]
    found = {
        EarlierRewrite(
            record=rewrite,
            completed_at=scope.recorded_at if any(scope.joins(entry) for entry in completed) else None,
        ): None
        for scope in scopes
        if scope.request_id == request_id and scope.environment == environment
        for rewrite in scope.manifest_rewrites
    }
    return tuple(found)


async def swept_manifest_versions(
    versions: EvidenceVersionStore,
    *,
    caselists: Sequence[str],
    rewritten_now: Collection[ObjectKey],
    earlier_rewrites: Sequence[EarlierRewrite],
    names_removed: NamesRemoved,
) -> tuple[ObjectVersion, ...]:
    """Every version the sweep deletes, once each, in key and version order. Lists and reads only.

    `caselists` are those whose manifests the removal affects, `rewritten_now` the bucket keys the
    run rewrites (their purge takes every other version), and `earlier_rewrites` the rewrites
    earlier runs of the same request recorded. Raises what the store raises: a refused listing or
    read is the caller's to report.
    """
    swept: dict[tuple[ObjectKey, str | None], ObjectVersion] = {}
    for caselist in caselists:
        for version in await versions.list_versions(manifest_prefix(caselist)):
            if version.is_latest or version.is_delete_marker or version.key in rewritten_now:
                continue
            if await _names_removed(versions, caselist, version, names_removed):
                swept[(version.key, version.version_id)] = version
    for version in await left_by_earlier_runs(versions, earlier_rewrites, rewritten_now=rewritten_now):
        swept.setdefault((version.key, version.version_id), version)
    return tuple(sorted(swept.values()))


async def left_by_earlier_runs(
    versions: EvidenceVersionStore,
    rewrites: Sequence[EarlierRewrite],
    *,
    rewritten_now: Collection[ObjectKey] = (),
) -> tuple[ObjectVersion, ...]:
    """The versions of each key an earlier run rewrote that the run's purge should have taken.

    By :func:`~debate_core.application.caselist.removal_residue.purge_should_have_taken` for a run
    that completed, and strictly older than the rewrite for one that stopped: see the module
    docstring's second rule, and "What it never takes" for every version this leaves.
    """
    found: dict[tuple[ObjectKey, str | None], ObjectVersion] = {}
    listed: dict[ObjectKey, list[ObjectVersion]] = {}
    for rewrite in rewrites:
        record = rewrite.record
        if record.key in rewritten_now or record.version_id is None:
            continue
        if record.key not in listed:
            listed[record.key] = [
                one for one in await versions.list_versions(record.key) if one.key == record.key
            ]
        of_the_key = listed[record.key]
        if rewrite.completed_at is not None:
            completed_at = rewrite.completed_at
            taken = [one for one in of_the_key if purge_should_have_taken(one, record, completed_at)]
        else:
            taken = _older_than_the_rewrite(of_the_key, record)
        found.update({(one.key, one.version_id): one for one in taken})
    return tuple(found.values())


def _older_than_the_rewrite(
    of_the_key: Sequence[ObjectVersion], record: ManifestRewriteRecord
) -> list[ObjectVersion]:
    """A stopped run's rule: the noncurrent data versions strictly older than its rewrite, which the
    bucket must still hold for anything to be older than it. Strictly older keeps the rewrite itself,
    and a version stamped in the same second as it."""
    rewrite = next(
        (one for one in of_the_key if one.version_id == record.version_id and not one.is_delete_marker),
        None,
    )
    if rewrite is None or rewrite.last_modified is None:
        return []
    return [
        one
        for one in of_the_key
        if not one.is_latest
        and not one.is_delete_marker
        and one.last_modified is not None
        and one.last_modified < rewrite.last_modified
    ]


async def _names_removed(
    versions: EvidenceVersionStore, caselist: str, version: ObjectVersion, names_removed: NamesRemoved
) -> bool:
    with tempfile.TemporaryDirectory(prefix="debate-removal-") as directory:
        staged = Path(directory) / "version.jsonl"
        await versions.get_version_file(version, staged)
        lines = staged.read_text(encoding="utf-8").splitlines()
    return any(names_removed(caselist, line, version.key) for line in lines if line.strip())

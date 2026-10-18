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
2. **A version older than the request's own rewrite of its key** (`v1-e30-t19`). Each manifest an
   earlier run of the same request rewrote in the bucket is recorded, with the version its rewrite
   is, in the scope beside that run's log entry (`v1-e30-t15`). The run purged every other version
   of the key then, so a noncurrent version older than the rewrite is one that purge should have
   taken, whatever it names: `caselist status` counts it, and before this rule nothing cleared it.

## What it never takes

* The current version of any key, by either rule.
* The rewrite itself, and any version written after it: a re-import published since is an
  ordinary later write. Older is the store's own time, strictly earlier than the rewrite's; a
  version whose store states no time is not older than anything.
* A version of a key no run of this request rewrote that names nothing removed: another request's
  rewrite, or another environment's, is not this request's (`completed_removals` keeps them apart in
  the same way).
* Any version of a key whose rewrite the bucket no longer holds. "Older than the rewrite" cannot
  be told without it. That happens only when something deleted the rewrite, by hand or by a later
  request's own purge, which then took the older versions too.
* A delete marker. It holds nothing.

So it deletes nothing outside a key the removal rewrote or a version that names what it removed:
the spec's forbidden list.
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable, Collection, Sequence
from pathlib import Path

from debate_core.application.caselist.publish_plan import manifest_prefix
from debate_core.application.ports.evidence_store import ObjectKey
from debate_core.application.ports.evidence_versions import EvidenceVersionStore, ObjectVersion
from debate_core.application.ports.suppression import ManifestRewriteRecord

__all__ = ["NamesRemoved", "older_than_their_rewrite", "swept_manifest_versions"]

type NamesRemoved = Callable[[str, str, ObjectKey], bool]
"""Whether one line of a manifest of `caselist`, at `key`, names something the removal took out."""


async def swept_manifest_versions(
    versions: EvidenceVersionStore,
    *,
    caselists: Sequence[str],
    rewritten_now: Collection[ObjectKey],
    earlier_rewrites: Sequence[ManifestRewriteRecord],
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
    for version in await older_than_their_rewrite(versions, earlier_rewrites, rewritten_now=rewritten_now):
        swept.setdefault((version.key, version.version_id), version)
    return tuple(sorted(swept.values()))


async def older_than_their_rewrite(
    versions: EvidenceVersionStore,
    rewrites: Sequence[ManifestRewriteRecord],
    *,
    rewritten_now: Collection[ObjectKey] = (),
) -> tuple[ObjectVersion, ...]:
    """The noncurrent data versions of each rewritten key that are older than its rewrite.

    See "What it never takes" in the module docstring for every version this leaves. Strictly
    older is what keeps the rewrite itself, and a version stamped in the same second as it.
    """
    found: list[ObjectVersion] = []
    listed: dict[ObjectKey, list[ObjectVersion]] = {}
    for record in rewrites:
        if record.key in rewritten_now or record.version_id is None:
            continue
        if record.key not in listed:
            listed[record.key] = [
                one for one in await versions.list_versions(record.key) if one.key == record.key
            ]
        of_the_key = listed[record.key]
        rewrite = next(
            (one for one in of_the_key if one.version_id == record.version_id and not one.is_delete_marker),
            None,
        )
        if rewrite is None or rewrite.last_modified is None:
            continue
        found += [
            one
            for one in of_the_key
            if not one.is_latest
            and not one.is_delete_marker
            and one.last_modified is not None
            and one.last_modified < rewrite.last_modified
        ]
    return tuple(found)


async def _names_removed(
    versions: EvidenceVersionStore, caselist: str, version: ObjectVersion, names_removed: NamesRemoved
) -> bool:
    with tempfile.TemporaryDirectory(prefix="debate-removal-") as directory:
        staged = Path(directory) / "version.jsonl"
        await versions.get_version_file(version, staged)
        lines = staged.read_text(encoding="utf-8").splitlines()
    return any(names_removed(caselist, line, version.key) for line in lines if line.strip())

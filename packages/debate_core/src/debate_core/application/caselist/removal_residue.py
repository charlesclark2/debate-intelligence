"""What a removal left in the bucket, counted from a version listing (`v1-e30-t10`, `v1-e30-t15`).

A takedown deletes every version of every object of a removed file. One that stopped part-way, or
a delete made some other way, can leave versions behind, and a version that can be restored is a
file not removed. `debate-research caselist status` reports them through
:meth:`~debate_core.application.caselist.status_service.CaselistStatusService.status`, so the check
an operator already runs after a removal says whether anything is left, without the takedown
profile.

## It reads, with the everyday profile

One call, `ListObjectVersions`, under two prefixes per caselist: its sources (`raw/caselist/<slug>/`,
or `raw/openev/` for camp files) and its parsed cards (`parsed/<caselist>/`); and a third, its
manifests (`manifests/<caselist>/`), when a completed removal touched it. The everyday
`EvidenceOperator` profile may list versions under `raw/` and `parsed/` (`v1-e29-t06`). Nothing is
downloaded and nothing is deleted: this module calls no other method of the version store, and the
credential it is given cannot delete.

## What is residue

The suppression list says what was removed. A file whose **whole source** is suppressed is gone for
every holder, so any version of an object named for its digest is something a removal should have
taken. That covers the files a request named and the later uploads a removal took down with them
(`v1-e30-t11`), because each is suppressed whole. Per file, three counts:

`current_objects`
    Objects that are the current version of their key. A takedown deletes each version by its id,
    and S3 then makes the next version current, so what a takedown that stopped among an object's
    versions leaves is a current object with the older versions beneath it.
`noncurrent_versions`
    Data versions that are not current: under a newer version, or under a delete marker.
`delete_markers`
    A delete made without a version id hides an object under a marker and keeps every version. No
    plain listing shows that key again. The takedown leaves no marker, so one is counted.

An object is matched by its key alone: its last segment is the file's digest (`raw/`), or the
digest and an extension (`parsed/…/<sha256>.jsonl`).

## Manifests and aggregates (`v1-e30-t15`)

A removal also cleans two things no key names a file in, and this check reaches them by time alone,
from the listing and the removal log, with nothing downloaded. Under each completed removal:

* **The parsed store's aggregates.** It deletes every version of `index.jsonl`, `failures.jsonl` and
  `occurrences.jsonl`, in every version directory, of every caselist for a file it removes whole and
  of each caselist it withdraws a copy from (`removal_plan`, "The parsed card store's aggregates").
  `caselist_card_stats` writes card tags into them, so any version of one older than the removal can
  hold a removed card's row.
* **The manifests it rewrote.** It writes each one without the removed rows and purges every other
  version of it. Any version of that key older than the removal but the rewrite itself is one the
  purge should have taken.

So per caselist, against the latest completed removal that touched it (:func:`completed_removals`):
each aggregate version, current or not, older than its completion; and each version of a manifest
it rewrote, other than the rewrite, older than its completion. "Older" allows for the two clocks
(:data:`CLOCK_SKEW_MARGIN`). A version written after it is an ordinary later write: the aggregates
rebuilt by the next parse, a manifest published again.

**Not every manifest of the caselist.** The removal's sweep of the caselist's *other* manifests
reads each noncurrent version and deletes only those that name what was removed. A version that
never named it stays, older than the removal, and holds nothing removed: a camp release's manifest
re-published by `caselist reimport-openev-metadata` keeps one by design. Its age says nothing, so it
is not counted, and the sweep run again is what covers those.

**Only a caselist the removal touched**, one that held a file it removed or withdrew. A removal of a
whole file deletes every caselist's aggregates, but only one that held the file can hold a row of it.

Both facts come from the scope a removal records beside its log entry
(:class:`~debate_core.application.ports.suppression.RemovalScopeEntry`). A completed removal with no
scope was made by a build from before it, which did not say which caselists it touched; nothing is
compared with it, and the report names it as not checked.

## What it does not see

* **A manifest version older than a removal, of a manifest it did not rewrite**, which names a
  removed row: the sweep should have taken it. Telling it from one that names nothing would mean
  downloading it. Every executed removal sweeps those, a re-run included.
* **A file withdrawn from one team and kept for another.** It is suppressed for one disclosure, not
  whole, and the other holders' copy is the same object. Nothing in a key says which holder a
  version was for.
* **`manifests/_suppression/`**: the list, the log, the path holds and the scopes are appended to,
  and their old versions are the record of what was asked, which no removal deletes.

So "nothing found" means no version of a wholly removed file is left under `raw/` and `parsed/`, and
no aggregate or rewritten manifest version is older than a removal that touched its caselist, and
the command says exactly that.

## A refused listing is not an empty one

In an environment where the grant has not been applied the listing is refused
(:class:`~debate_core.application.errors.StoreAccessDenied`). The caselist is then reported as not
checked, with no counts at all: a zero would say nothing is left. Any other failure of the bucket
is raised, as it is for the rest of the comparison.

## What it reports

Counts and digests. The command prints the first twelve characters of each digest
(:attr:`ResidueFile.sha256_prefix`), which is enough to find the entry, and its request id, in the
suppression list.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Final

from debate_core.application.caselist.publish_plan import manifest_prefix, remote_source_prefix
from debate_core.application.errors import StoreAccessDenied, error_code_of
from debate_core.application.ports.evidence_store import ObjectKey
from debate_core.application.ports.evidence_versions import EvidenceVersionStore, ObjectVersion
from debate_core.application.ports.parsed_store import AGGREGATE_NAMES, PARSED_PREFIX
from debate_core.application.ports.suppression import (
    ManifestRewriteRecord,
    RemovalLogEntry,
    RemovalLogKind,
    RemovalOutcome,
    RemovalScopeEntry,
    SuppressionState,
)
from debate_core.domain import SHA256_HEX_PATTERN, Sha256Hex

__all__ = [
    "CLOCK_SKEW_MARGIN",
    "MANIFEST_ROLE",
    "RESIDUE_DIGEST_PREFIX_LENGTH",
    "CaselistResidue",
    "CompletedRemovals",
    "OlderVersions",
    "RemovalCompletion",
    "ResidueFile",
    "completed_removals",
    "removal_residue",
    "residue_prefixes",
]

RESIDUE_DIGEST_PREFIX_LENGTH: Final = 12
"""How much of a digest the report prints: what the removal plan prints for a later upload too."""

_DIGEST: Final = re.compile(SHA256_HEX_PATTERN)

CLOCK_SKEW_MARGIN: Final = timedelta(minutes=15)
"""How much older than a removal's completion a version must be to be counted (`v1-e30-t15`).

The completion is this machine's clock and a version's time is S3's. S3 refuses a signed request
whose time is more than 15 minutes from its own (`RequestTimeTooSkewed`), and a removal ends by
writing its log entry to the bucket, so this machine's clock was within 15 minutes of S3's at that
moment. A version S3 stamped after the completion therefore reads as no earlier than 15 minutes
before it, and is never counted. What the margin costs is a version written in the 15 minutes before
the completion and missed by the removal, which is not counted either."""

MANIFEST_ROLE: Final = "manifest"
"""The role of a manifest's versions in the report; an aggregate's role is its file name."""


@dataclass(frozen=True, slots=True)
class ResidueFile:
    """One removed file, and what the bucket still holds under keys named for it."""

    sha256: Sha256Hex
    current_objects: int = 0
    noncurrent_versions: int = 0
    delete_markers: int = 0

    @property
    def sha256_prefix(self) -> str:
        return self.sha256[:RESIDUE_DIGEST_PREFIX_LENGTH]


@dataclass(frozen=True, slots=True)
class OlderVersions:
    """How many versions of one key role in a caselist are older than a removal that touched it."""

    role: str
    """`manifest`, or the aggregate's file name: `index.jsonl`, `failures.jsonl`, `occurrences.jsonl`."""
    versions: int


@dataclass(frozen=True, slots=True)
class RemovalCompletion:
    """When a removal request was last completed in this environment, from the removal log."""

    request_id: str | None
    completed_at: datetime


@dataclass(frozen=True, slots=True)
class CompletedRemovals:
    """This environment's completed removals, as the residue check compares versions with them."""

    by_caselist: dict[str, RemovalCompletion] = field(default_factory=lambda: {})
    """The latest completed removal that touched each caselist."""
    rewrites: tuple[tuple[ManifestRewriteRecord, datetime], ...] = ()
    """Each manifest a completed removal rewrote, with that removal's completion."""
    not_checked: tuple[str, ...] = ()
    """Request ids of completed removals no scope says the reach of: made by an older build."""


@dataclass(frozen=True, slots=True)
class CaselistResidue:
    """What a version listing shows of one caselist's removed files, or that it could not be made."""

    caselist: str
    checked: bool
    """False when the listing was refused. The counts are then `None`, never zero."""
    files: tuple[ResidueFile, ...] = ()
    """Every removed file with anything left, in digest order. Empty when :attr:`checked` is false."""
    not_checked_reason: str | None = None
    """The error code of the refusal, e.g. `STORE_ACCESS_DENIED`."""
    older_versions: tuple[OlderVersions, ...] = ()
    """Manifest and aggregate versions older than a removal that touched this caselist, by role."""
    older_than: RemovalCompletion | None = None
    """The latest completed removal that touched this caselist, or `None` when none did."""

    @property
    def found(self) -> bool:
        return bool(self.files) or bool(self.older_versions)

    @property
    def current_objects(self) -> int | None:
        return sum(one.current_objects for one in self.files) if self.checked else None

    @property
    def noncurrent_versions(self) -> int | None:
        return sum(one.noncurrent_versions for one in self.files) if self.checked else None

    @property
    def delete_markers(self) -> int | None:
        return sum(one.delete_markers for one in self.files) if self.checked else None


def residue_prefixes(caselist: str) -> tuple[str, str]:
    """The two prefixes one caselist's check lists versions under: its sources, and its parsed cards."""
    return remote_source_prefix(caselist), f"{PARSED_PREFIX}/{caselist}/"


async def removal_residue(
    versions: EvidenceVersionStore,
    caselist: str,
    suppression: SuppressionState,
    removals: CompletedRemovals | None = None,
) -> CaselistResidue:
    """Count what the bucket still holds of `caselist`'s removed files and older versions. Lists only.

    With `removals`, also the manifest and aggregate versions older than the latest completed
    removal that touched `caselist`: see "Manifests and aggregates" in the module docstring.
    """
    completion = removals.by_caselist.get(caselist) if removals is not None else None
    counts: dict[Sha256Hex, list[int]] = {}
    listed: list[ObjectVersion] = []
    try:
        for prefix in residue_prefixes(caselist):
            for version in await versions.list_versions(prefix):
                listed.append(version)
                digest = _digest_named_by(version.key)
                if digest is None or not suppression.suppresses_source(digest):
                    continue
                current, noncurrent, markers = counts.setdefault(digest, [0, 0, 0])
                if version.is_delete_marker:
                    markers += 1
                elif version.is_latest:
                    current += 1
                else:
                    noncurrent += 1
                counts[digest] = [current, noncurrent, markers]
        if completion is not None:
            listed.extend(await versions.list_versions(manifest_prefix(caselist)))
    except StoreAccessDenied as refused:
        return CaselistResidue(caselist=caselist, checked=False, not_checked_reason=error_code_of(refused))
    return CaselistResidue(
        caselist=caselist,
        checked=True,
        files=tuple(
            ResidueFile(
                sha256=digest, current_objects=current, noncurrent_versions=noncurrent, delete_markers=markers
            )
            for digest, (current, noncurrent, markers) in sorted(counts.items())
        ),
        older_versions=_older_versions(caselist, listed, removals, completion),
        older_than=completion,
    )


def _older_versions(
    caselist: str,
    listed: Sequence[ObjectVersion],
    removals: CompletedRemovals | None,
    completion: RemovalCompletion | None,
) -> tuple[OlderVersions, ...]:
    """Per role, the data versions in `listed` that a completed removal touching `caselist` should
    have taken: an aggregate's older than the latest one, and a rewritten manifest's older than the
    removal that rewrote it, its own rewrite apart."""
    if removals is None or completion is None:
        return ()
    older: dict[str, set[tuple[ObjectKey, str | None]]] = {}
    aggregates = f"{PARSED_PREFIX}/{caselist}/"
    for version in listed:
        if version.is_delete_marker:
            continue
        role = _aggregate_role(version.key, aggregates)
        if role is not None and _before(version, completion.completed_at):
            older.setdefault(role, set()).add((version.key, version.version_id))
        for rewrite, completed_at in removals.rewrites:
            if (
                version.key == rewrite.key
                and version.version_id != rewrite.version_id
                and _before(version, completed_at)
            ):
                older.setdefault(MANIFEST_ROLE, set()).add((version.key, version.version_id))
    return tuple(
        OlderVersions(role=role, versions=len(older[role]))
        for role in (MANIFEST_ROLE, *AGGREGATE_NAMES)
        if role in older
    )


def _before(version: ObjectVersion, completed_at: datetime) -> bool:
    """Whether `version` was written before `completed_at`, by more than the clock-skew margin.

    A version whose store states no time is not counted: nothing shows it older.
    """
    return version.last_modified is not None and version.last_modified < completed_at - CLOCK_SKEW_MARGIN


def _aggregate_role(key: ObjectKey, aggregates: str) -> str | None:
    """The aggregate's file name for `<aggregates><version>/<name>`, or `None` for any other key."""
    if not key.startswith(aggregates):
        return None
    rest = key[len(aggregates) :].split("/")
    return rest[1] if len(rest) == 2 and rest[1] in AGGREGATE_NAMES else None


def completed_removals(
    entries: Sequence[RemovalLogEntry], scopes: Sequence[RemovalScopeEntry], environment: str
) -> CompletedRemovals:
    """What the removal log says of `environment`'s completed removals, request by request.

    A request is completed at the latest of its `COMPLETED` entries; one with none is not compared
    with anything. It touched the caselists of every scope joined to one of its entries, and the
    manifests rewritten by its completed runs are each held to the run that rewrote them. A request
    with any entry no scope joins was run by a build that recorded none, so which caselists it
    touched is unknown: it is named in :attr:`CompletedRemovals.not_checked` and compared with
    nothing. Another environment's entries are left out: its completion says nothing of this bucket.
    """
    by_request: dict[str | None, list[RemovalLogEntry]] = {}
    for entry in entries:
        if entry.kind is RemovalLogKind.REMOVAL and entry.environment == environment:
            by_request.setdefault(entry.request_id, []).append(entry)
    by_caselist: dict[str, RemovalCompletion] = {}
    rewrites: list[tuple[ManifestRewriteRecord, datetime]] = []
    not_checked: list[str] = []
    for request_id, runs in by_request.items():
        completed = [run for run in runs if run.outcome is RemovalOutcome.COMPLETED]
        if not completed:
            continue
        joined = [[scope for scope in scopes if scope.joins(run)] for run in runs]
        if not all(joined):
            not_checked.append(request_id or "a removal with no request id")
            continue
        completion = RemovalCompletion(
            request_id=request_id, completed_at=max(run.recorded_at for run in completed)
        )
        for caselist in {name for found in joined for scope in found for name in scope.caselists}:
            held = by_caselist.get(caselist)
            if held is None or held.completed_at < completion.completed_at:
                by_caselist[caselist] = completion
        rewrites.extend(
            (rewrite, run.recorded_at)
            for run, found in zip(runs, joined, strict=True)
            if run.outcome is RemovalOutcome.COMPLETED
            for scope in found
            for rewrite in scope.manifest_rewrites
        )
    return CompletedRemovals(
        by_caselist=by_caselist, rewrites=tuple(rewrites), not_checked=tuple(sorted(not_checked))
    )


def _digest_named_by(key: ObjectKey) -> Sha256Hex | None:
    """The digest an object's last key segment is, with or without an extension, or `None`."""
    stem = key.rsplit("/", 1)[-1].split(".", 1)[0]
    return stem if _DIGEST.match(stem) is not None else None

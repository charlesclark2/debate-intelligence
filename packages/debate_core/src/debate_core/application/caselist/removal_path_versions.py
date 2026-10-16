"""The other versions of a file the store holds at the paths a removal takes it from (`v1-e30-t11`).

A removal request covers later uploads at the same path (the PM's ruling under `v1-e30-t07`). The
sync enforces that for a file not yet imported: it holds a new upload at a removed path back
(`v1-e34-t07`, `v1-e34-t14`). This module is the other half, for uploads that were imported before
the removal: given every stored manifest row the planner read, it says which other files sit at a
removed file's paths, and whether each came later.

## Snapshots are windows

A weekly archive holds about one week's changes, not the whole caselist, so nothing here assumes a
snapshot lists a path it did not touch. A revision of a file shows up as a row at the same path in
a later window, or only in a complete archive (`full/<date>`). Every snapshot the planner reads is
asked, weekly and complete alike, on this machine and in the bucket.

## What "later" means

For a named file `A` and a path where it is held, take the **earliest** snapshot holding `A` there.
Another file held at that path is:

`LATER`
    in any snapshot dated after that one. The removal covers it. A revert (`A`, then `B`, then `A`
    again) still makes `B` later, because only `A`'s earliest snapshot is compared.
`EARLIER`
    only in snapshots dated before it. Not covered by the ruling: listed for the operator, and
    nothing is done to it.
`SAME_DATE`
    in no later snapshot, and in one of the same date: a weekly and the complete archive of one day
    that disagree, or this machine's copy of a manifest and the bucket's. Which came first cannot be
    read from the dates, so it is listed with the earlier versions and nothing is done to it.

Snapshots are ordered by date. A complete archive is ordered by its own date, not by its name:
`full/2026-09-05` is before the weekly of `2026-09-08`.

## What "the same path" means

Within one caselist, the caselist and the row's `path`, exactly as written. The same spelling in
another caselist is another path.

For an OpenEv camp file, the revision identity `v1-e34-t08` uses
(:func:`~debate_core.application.caselist_sync.camp_path_of_manifest_row`): two rows of one
release manifest, each named for its own OpenEv id (`openev-<id>-…`), whose paths agree as names
once the id is off. A release manifest is one accumulating file, so its rows are ordered by OpenEv
id, which upstream assigns in upload order: the higher id is the later upload. A row that names no
id, a camp file imported by hand, cannot say which upload it was, so it is neither a later upload
nor has one.

A release's rows do not keep the camp's folder, so two camps' files with one file name read as one
camp path. Where this machine's delivery record (`caselist-sync-openev-deliveries.json`) knows the
upstream path of both ids, it decides: different path digests are different paths, and the match is
reported as :attr:`SamePathEvidence.UPSTREAM_PATH_DIGEST`. Where it does not know both, as on a
machine that never pulled, the rows' names are all there is (:attr:`SamePathEvidence.ROW_NAME`), and
the plan says so.

## An archive in the download inbox is a snapshot too

A revision in an archive `caselist pull` downloaded is at the removed path whether or not it has
been imported (`v1-e30-t13`). The planner hands each inbox archive's members in as holdings marked
:attr:`PathHolding.inbox`, dated as the archive's name dates it, and the same rules above say which
are later. :attr:`PathVersion.snapshots` stays what the store's manifests show, and
:attr:`PathVersion.inbox_snapshots` is where only the inbox shows it.

Reads nothing and logs nothing: a function of the rows it is given.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from debate_core.application.caselist.publish_plan import OPENEV, full_archive_date
from debate_core.application.caselist_sync import camp_path_of_manifest_row
from debate_core.domain import Sha256Hex

__all__ = [
    "PathHolding",
    "PathIdentity",
    "PathVersion",
    "SamePathEvidence",
    "VersionRelation",
    "other_versions",
    "path_identity",
    "snapshot_date",
]

type PathIdentity = tuple[str, ...]
"""One path, comparably: `(caselist, path)`, or `("openev", release, *names)` for a camp path."""

type _Order = tuple[int, ...]


class VersionRelation(StrEnum):
    """When another file was held at a removed file's path. See the module docstring."""

    LATER = "later"
    EARLIER = "earlier"
    SAME_DATE = "same_date"


class SamePathEvidence(StrEnum):
    """What says two files were at one path."""

    CASELIST_PATH = "caselist_path"
    """Rows of one caselist with the same `path`."""
    UPSTREAM_PATH_DIGEST = "upstream_path_digest"
    """Camp rows whose names agree, and whose ids the delivery record puts at one upstream path."""
    ROW_NAME = "row_name"
    """Camp rows whose names agree. The delivery record here does not know both ids."""


@dataclass(frozen=True, slots=True)
class PathHolding:
    """One stored manifest row: these bytes, at this path, in this snapshot."""

    caselist: str
    """A caselist's slug, or `openev`."""
    snapshot: str
    """As the manifest's key names it: `2026-09-15`, `full/2026-09-15`, or a release, `2026-policy`."""
    path: str
    sha256: Sha256Hex
    inbox: bool = False
    """True for a member of an archive in the download inbox, rather than a stored manifest row."""


@dataclass(frozen=True, slots=True)
class PathVersion:
    """Another file the store holds at a path the removal takes a named file from.

    :attr:`path` identifies a team or a camp file. It is for the operator's terminal, and never for
    the plan's JSON or a log.
    """

    sha256: Sha256Hex
    relation: VersionRelation
    of_sha256: Sha256Hex
    """The named file whose path this is."""
    caselist: str
    path: str
    snapshots: tuple[str, ...]
    """Every snapshot whose manifest holds it at this path, in order. Empty for a file only the
    download inbox holds there."""
    openev_ids: tuple[int, ...]
    """For a camp file, the OpenEv ids its rows at this path name."""
    evidence: SamePathEvidence
    identity: PathIdentity
    inbox_snapshots: tuple[str, ...] = ()
    """The snapshots of the inbox archives that hold it at this path and that no manifest shows:
    downloaded and not imported, or imported by a build that refused it there (`v1-e30-t13`)."""

    @property
    def only_in_the_inbox(self) -> bool:
        """Whether no manifest holds it at this path: the store never took it in there."""
        return not self.snapshots


def path_identity(holding: PathHolding) -> PathIdentity | None:
    """The path a row is at, comparably, or `None` for a camp row that names no OpenEv id."""
    placed = _placed(holding)
    return placed[0] if placed is not None else None


def other_versions(
    holdings: Iterable[PathHolding],
    removed_from: Mapping[Sha256Hex, Collection[PathIdentity] | None],
    *,
    named: Collection[Sha256Hex],
    upstream_path_digests: Mapping[int, str],
) -> tuple[PathVersion, ...]:
    """Every other file held at a path the removal takes a named file from, and when.

    Args:
        holdings: Every stored row of every manifest the planner read, on either side.
        removed_from: For each file the removal removes or withdraws, the paths it takes it from:
            `None` for every path it is held at, or the paths of a withdrawal.
        named: The files the selector itself names. None of them is reported as a version of another.
        upstream_path_digests: The SHA-256 of each OpenEv id's upstream path, where the delivery
            record on this machine knows it.

    A file at two removed paths is reported once per path. One that is later than one named file and
    earlier than another at the same path is `LATER`.
    """
    by_identity: dict[PathIdentity, list[tuple[_Order, PathHolding]]] = {}
    for holding in set(holdings):
        placed = _placed(holding)
        if placed is not None:
            by_identity.setdefault(placed[0], []).append((placed[1], holding))

    found: dict[tuple[Sha256Hex, PathIdentity], PathVersion] = {}
    for identity, held in by_identity.items():
        for named_digest, limited_to in removed_from.items():
            if limited_to is not None and identity not in limited_to:
                continue
            of_named = [order for order, holding in held if holding.sha256 == named_digest]
            if not of_named:
                continue
            earliest = min(of_named)
            for digest in {holding.sha256 for _, holding in held} - set(named):
                version = _version_at(identity, held, digest, named_digest, earliest, upstream_path_digests)
                known = found.get((digest, identity))
                if version is not None and (known is None or _RANK[version.relation] > _RANK[known.relation]):
                    found[(digest, identity)] = version
    return tuple(
        sorted(
            found.values(),
            key=lambda one: (one.caselist, one.path, (*one.snapshots, *one.inbox_snapshots), one.sha256),
        )
    )


_RANK = {VersionRelation.EARLIER: 0, VersionRelation.SAME_DATE: 1, VersionRelation.LATER: 2}


def _version_at(
    identity: PathIdentity,
    held: list[tuple[_Order, PathHolding]],
    digest: Sha256Hex,
    named_digest: Sha256Hex,
    earliest: _Order,
    upstream_path_digests: Mapping[int, str],
) -> PathVersion | None:
    theirs = sorted(
        ((order, holding) for order, holding in held if holding.sha256 == digest),
        key=lambda one: (one[0], one[1].snapshot),
    )
    evidence = SamePathEvidence.CASELIST_PATH
    if identity[0] == OPENEV:
        named_ids = [order[0] for order, holding in held if holding.sha256 == named_digest]
        named_paths = {upstream_path_digests[one] for one in named_ids if one in upstream_path_digests}
        every_named_path_known = all(one in upstream_path_digests for one in named_ids)
        confirmed = [
            (order, holding)
            for order, holding in theirs
            if order[0] in upstream_path_digests and upstream_path_digests[order[0]] in named_paths
        ]
        if every_named_path_known:
            # The record knows where the named file was: an id it puts elsewhere is another camp's.
            theirs = [
                (order, holding)
                for order, holding in theirs
                if (order, holding) in confirmed or order[0] not in upstream_path_digests
            ]
        evidence = (
            SamePathEvidence.UPSTREAM_PATH_DIGEST
            if theirs and len(confirmed) == len(theirs)
            else SamePathEvidence.ROW_NAME
        )
    if not theirs:
        return None
    orders = [order for order, _ in theirs]
    if any(order > earliest for order in orders):
        relation = VersionRelation.LATER
    elif all(order < earliest for order in orders):
        relation = VersionRelation.EARLIER
    else:
        relation = VersionRelation.SAME_DATE
    first = theirs[0][1]
    stored = tuple(dict.fromkeys(holding.snapshot for _, holding in theirs if not holding.inbox))
    return PathVersion(
        sha256=digest,
        relation=relation,
        of_sha256=named_digest,
        caselist=first.caselist,
        path=first.path,
        snapshots=stored,
        openev_ids=tuple(order[0] for order, _ in theirs) if identity[0] == OPENEV else (),
        evidence=evidence,
        identity=identity,
        inbox_snapshots=tuple(
            dict.fromkeys(
                holding.snapshot for _, holding in theirs if holding.inbox and holding.snapshot not in stored
            )
        ),
    )


def _placed(holding: PathHolding) -> tuple[PathIdentity, _Order] | None:
    """Where a row is, and where it comes in the order of its path's versions."""
    if holding.caselist == OPENEV:
        openev_id, names = camp_path_of_manifest_row(holding.path)
        if openev_id is None or not names:
            return None
        return (OPENEV, holding.snapshot, *names), (openev_id,)
    held_on = snapshot_date(holding.snapshot)
    if held_on is None:
        return None
    return (holding.caselist, holding.path), (held_on.toordinal(),)


def snapshot_date(snapshot: str) -> date | None:
    """The date a caselist snapshot is ordered by: a weekly's, or a complete archive's own."""
    complete = full_archive_date(snapshot)
    if complete is not None:
        return complete
    try:
        return date.fromisoformat(snapshot)
    except ValueError:
        return None

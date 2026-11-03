"""The landscape bundles' school views, as a removal and `caselist status` reach them (`v1-e32-t13`).

Since `v1-e32-t04` each landscape bundle, `reports/landscape/<caselist>/<snapshot>/`, in the bucket
and under the data directory alike, holds a per-school view beside the circuit-wide report: the
files :data:`~debate_core.application.landscape_bundle_files.SCHOOL_VIEW_FILES` names, with schools and
team codes as disclosed. The data-use policy keeps a per-school view on its sources' clock and
removes it with them. The circuit-wide files
(:data:`~debate_core.application.landscape_bundle_files.CIRCUIT_WIDE_FILES`) name no school or team, and
a removal never touches them: the next report leaves the removed rounds out.

## One selection, for the plan, the execution and the residue check

:func:`is_school_view` decides, for one key, whether it is a school view of one of a set of
caselists. The removal plan lists with it, `--execute` deletes with it, and `caselist status` counts
what is left with it, so the three cannot drift apart. Two lists say what a bundle holds, both
`v1-e32-t04`'s and imported, never copied: a key of a caselist the set names whose file is in
neither, or that is not `<caselist>/<snapshot>/<file>`, is :class:`UnknownLandscapeFile`, never a
guess. The caselist is the key's own segment, matched whole, so no caselist's set reaches a bundle
of another whose name merely begins the same way.

## Which caselists, and which of their views

A removal reaches every caselist it touches (:attr:`~debate_core.application.caselist.removal_plan.
RemovalPlan.touched_caselists`, OpenEv apart, which has no bundle), and every school view of each:
it is removing something from that caselist now, and any of its views may hold the removed rounds.

Running the same removal again also reaches each caselist an earlier completed run of the request
touched, by the scope recorded beside the log, but only the views written before that run completed
(:class:`SchoolViewReach`). A view written afterwards was built from a store the removal had already
cleaned, such as the newest snapshot's bundle republished, and is never taken. That is the rule
`caselist status` counts by too (:func:`school_view_cutoffs`), so what status reports as left the
re-run clears, and what the re-run leaves status does not report.

"Before" is by the store's own clock, less
:data:`~debate_core.application.caselist.removal_residue.CLOCK_SKEW_MARGIN`, as the residue check
compares every other version with a removal: S3's `LastModified` in the bucket, the file's
modification time on this machine.

## What it never holds

A key is a caselist, a snapshot's date and a file's name: no school, team code or path on this
machine. The removal log and the scopes beside it carry counts only; the plan printed to the operator
lists keys.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Final

from debate_core.application.caselist.removal_residue import (
    CLOCK_SKEW_MARGIN,
    OlderVersions,
    RemovalCompletion,
)
from debate_core.application.errors import DomainError
from debate_core.application.landscape_bundle_files import (
    CIRCUIT_WIDE_FILES,
    REPORTS_PREFIX,
    SCHOOL_VIEW_FILES,
)
from debate_core.application.ports.evidence_store import EvidenceObjectStore
from debate_core.application.ports.evidence_versions import EvidenceVersionStore
from debate_core.application.ports.suppression import (
    RemovalLogEntry,
    RemovalLogKind,
    RemovalOutcome,
    RemovalScopeEntry,
)

__all__ = [
    "LANDSCAPE_PREFIX",
    "LOCAL_SCHOOL_VIEW_ROLE",
    "SCHOOL_VIEW_ROLE",
    "SchoolViewReach",
    "UnknownLandscapeFile",
    "bundle_of",
    "is_school_view",
    "reached",
    "school_view_cutoffs",
    "school_views_left",
    "written_before",
]

LANDSCAPE_PREFIX: Final = f"{REPORTS_PREFIX}/"
"""Every landscape bundle's prefix, in the bucket and under the data directory alike."""

SCHOOL_VIEW_ROLE: Final = "school view"
"""The role `caselist status` reports a school-view file left in the bucket under."""

LOCAL_SCHOOL_VIEW_ROLE: Final = "local school view"
"""The role it reports one left under the data directory under."""


class UnknownLandscapeFile(DomainError):
    """A bundle of a caselist being reached holds a file that is neither a school view nor circuit-wide.

    Raised before anything is deleted. The key is a caselist, a snapshot and a file's name, so the
    message may name it.
    """

    def __init__(self, key: str) -> None:
        self.key = key
        self.hint = (
            "a landscape bundle holds only the files v1-e32-t04 names; look at this one, remove it by "
            "hand if it is stray, and run the same command again"
        )
        super().__init__(
            f"{key} is in a landscape bundle of a caselist this removal reaches and is neither a school "
            f"view ({', '.join(SCHOOL_VIEW_FILES)}) nor a circuit-wide file "
            f"({', '.join(CIRCUIT_WIDE_FILES)}), so it cannot be told whether to delete it; nothing was "
            "deleted"
        )


def is_school_view(key: str, caselists: Collection[str]) -> bool:
    """Whether `key` is a school-view file of a bundle of one of `caselists`.

    False for a key outside :data:`LANDSCAPE_PREFIX` and for one whose caselist segment is not in
    `caselists`, whatever it holds. For one whose segment is, true for a school view, false for a
    circuit-wide file, and :class:`UnknownLandscapeFile` for anything else.
    """
    if not key.startswith(LANDSCAPE_PREFIX):
        return False
    parts = key[len(LANDSCAPE_PREFIX) :].split("/")
    if parts[0] not in caselists:
        return False
    if len(parts) == 3 and _is_snapshot(parts[1]):
        if parts[2] in SCHOOL_VIEW_FILES:
            return True
        if parts[2] in CIRCUIT_WIDE_FILES:
            return False
    raise UnknownLandscapeFile(key)


def bundle_of(key: str) -> tuple[str, date]:
    """The caselist and snapshot of a key :func:`is_school_view` accepted."""
    caselist, snapshot, _ = key[len(LANDSCAPE_PREFIX) :].split("/")
    return caselist, date.fromisoformat(snapshot)


def _is_snapshot(text: str) -> bool:
    try:
        return date.fromisoformat(text).isoformat() == text
    except ValueError:
        return False


@dataclass(frozen=True, slots=True)
class SchoolViewReach:
    """One caselist whose school views a removal deletes, and which of them."""

    caselist: str
    older_than: RemovalCompletion | None = None
    """`None`: every one, since the removal touches the caselist now. Otherwise only those written
    before this earlier run of the request completed (see the module docstring)."""


def written_before(last_modified: datetime | None, completed_at: datetime) -> bool:
    """Whether a version written at `last_modified` is older than a removal completed at `completed_at`.

    By more than :data:`~debate_core.application.caselist.removal_residue.CLOCK_SKEW_MARGIN`; a
    version whose store states no time is not older than anything, as the residue check reads it.
    """
    return last_modified is not None and last_modified < completed_at - CLOCK_SKEW_MARGIN


def reached(key: str, last_modified: datetime | None, reach: Sequence[SchoolViewReach]) -> bool:
    """Whether a removal reaching `reach` deletes this version of `key`."""
    by_caselist = {one.caselist: one.older_than for one in reach}
    if not is_school_view(key, by_caselist):
        return False
    older_than = by_caselist[bundle_of(key)[0]]
    return older_than is None or written_before(last_modified, older_than.completed_at)


def school_view_cutoffs(
    entries: Sequence[RemovalLogEntry],
    scopes: Sequence[RemovalScopeEntry],
    environment: str,
    *,
    request_id: str | None = None,
) -> Mapping[str, RemovalCompletion]:
    """For each caselist, the latest completed removal run whose own scope names it.

    Every request's, or with `request_id` that request's alone: what a re-run of it reaches. Per run,
    not per request: a re-run that did not touch a caselist leaves that caselist's cutoff where the
    run that did touch it put it, so a view republished between the two is never older than it. A run
    with no scope joined to its log entry, made by a build that recorded none, names no caselist.
    """
    found: dict[str, RemovalCompletion] = {}
    for entry in entries:
        if (
            entry.kind is not RemovalLogKind.REMOVAL
            or entry.outcome is not RemovalOutcome.COMPLETED
            or entry.environment != environment
            or (request_id is not None and entry.request_id != request_id)
        ):
            continue
        completion = RemovalCompletion(request_id=entry.request_id, completed_at=entry.recorded_at)
        for scope in scopes:
            if not scope.joins(entry):
                continue
            for caselist in scope.caselists:
                held = found.get(caselist)
                if held is None or held.completed_at < completion.completed_at:
                    found[caselist] = completion
    return found


async def school_views_left(
    caselist: str,
    cutoff: RemovalCompletion,
    *,
    bucket: EvidenceObjectStore,
    local: EvidenceVersionStore | None,
) -> tuple[OlderVersions, ...]:
    """The school-view files of `caselist` written before `cutoff`: what a removal should have deleted.

    The bucket's by a plain listing, the current objects only: the everyday profile may list
    `reports/` but not its versions, so a noncurrent version left there is not seen here (the
    re-run's `--execute`, under the removal profile, lists and deletes those). This machine's by its
    files. Each is counted when :func:`is_school_view` takes it for `caselist` and it is older than
    the cutoff, by :func:`written_before`, which is the rule a re-run reaches it by.
    """
    found: list[OlderVersions] = []
    listed = [(info.key, info.last_modified) for info in await bucket.list_objects(LANDSCAPE_PREFIX)]
    on_this_machine = (
        [(version.key, version.last_modified) for version in await local.list_versions(LANDSCAPE_PREFIX)]
        if local is not None
        else []
    )
    for role, files in ((SCHOOL_VIEW_ROLE, listed), (LOCAL_SCHOOL_VIEW_ROLE, on_this_machine)):
        left = sum(
            1
            for key, last_modified in files
            if is_school_view(key, (caselist,)) and written_before(last_modified, cutoff.completed_at)
        )
        if left:
            found.append(OlderVersions(role=role, versions=left))
    return tuple(found)

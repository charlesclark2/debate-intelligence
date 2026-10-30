"""Superseded search index versions in a bucket, listed and then deleted (`v1-e39-t15`).

`tub index publish` writes each index under `reports/tub/search/<index id>/` and then moves
`reports/tub/search/current.json` to it, and the bucket keeps every version of everything. The
data-use policy's E39 gate (items 1 and 5) wants the superseded ones gone, noncurrent versions
included: they are copies of disclosed cards, with the school and team code of each disclosure,
that a removal has to reach (`v1-e39-t07`). Until this task the removal runbook's P4 did it with a
pasted script; this is that script's rule, as a service `debate-research tub index prune` runs.

## What a plan keeps and what it deletes

The takedown credential asks which role it is signed in as first, and goes no further unless it is
this environment's takedown role (:func:`~debate_core.application.caselist.removal_service.preflight`'s
first step). Then it lists every version and delete marker under `reports/tub/search/`, and the
everyday credential reads `current.json`, in that order: a publish that lands between the two
leaves a pointer naming an index the listing does not hold, which is refused.

* **Kept:** every version under the current index's directory, `reports/tub/search/<index id>/`, and
  the listing's current version of `current.json`.
* **Deleted:** every other version and delete marker under `reports/tub/search/`, the older versions
  of `current.json` among them. They name superseded indexes and hold no card.
* **Refused** (:class:`PruneRefusal`): a bucket with no `current.json`, a pointer this build cannot
  read, and a pointer naming an index the listing does not hold, as current versions of both its
  manifest and its gzip object inside its directory, with a current `current.json` beside them.
  Nothing is kept by a guess, so nothing is deleted.

## A dry run, then a confirmation

As `caselist retire` does (`v1-e31-t16`): a plan's :attr:`PrunePlan.confirmation` is a digest of the
place, the index kept and every version it would delete. `--execute` plans again and acts only when
that plan's code is the one given, so it deletes exactly what the dry run listed, or nothing.

## The last checks, inside the run lock

:meth:`SearchIndexPrune.execute` is called holding the bucket's run lock, which every publish holds
too (`v1-e40-t04`), and refuses on a Wednesday in Chicago, the cloud run's day, when its search
index stage publishes and moves the pointer (:func:`is_cloud_run_day`). Then it reads `current.json`
again and refuses if it no longer is the pointer the plan read (:class:`SearchIndexPointerMoved`),
and refuses a plan that names a version it keeps (:class:`WouldDeleteTheCurrentSearchIndex`), before
it sends a single delete.

**Counts and index ids only** leave this module in messages. No card, path, school or team code is
under `reports/tub/search/` but inside the index files, and nothing here reads one.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from debate_core.application.caselist.removal_service import (
    NotTheTakedownRole,
    TakedownAccess,
    permission_set_of,
    takedown_permission_set,
)
from debate_core.application.caselist.version_retention import CONFIRMATION_LENGTH
from debate_core.application.errors import DomainError, NotFound
from debate_core.application.ports.evidence_store import EvidenceObjectStore
from debate_core.application.ports.evidence_versions import ObjectVersion
from debate_core.domain.search_index import SEARCH_INDEX_POINTER_KEY, SEARCH_INDEX_PREFIX, SearchIndexPointer

__all__ = [
    "CLOUD_RUN_ZONE",
    "PRUNE_COMMAND",
    "PruneGroup",
    "PruneOnCloudRunDay",
    "PrunePlan",
    "PruneRefusal",
    "PruneResult",
    "SearchIndexPointerMoved",
    "SearchIndexPrune",
    "SearchIndexPruneRefused",
    "WouldDeleteTheCurrentSearchIndex",
    "is_cloud_run_day",
]

PRUNE_COMMAND: Final = "tub index prune"
"""What the prune holds the bucket's run lock as."""

CLOUD_RUN_ZONE: Final = ZoneInfo("America/Chicago")
"""The cloud run's schedule is Wednesdays at 06:00 here (`docs/runbooks/caselist-scheduled-sync.md`)."""

_WEDNESDAY: Final = 2


def is_cloud_run_day(now: datetime) -> bool:
    """Whether `now` is a Wednesday in Chicago, all of it: the day the annual purge and P4 never run on."""
    return now.astimezone(CLOUD_RUN_ZONE).weekday() == _WEDNESDAY


@dataclass(frozen=True, slots=True)
class PruneRefusal:
    """Why a plan cannot be executed. `code` is what `--json` reports."""

    code: str
    message: str


@dataclass(frozen=True, slots=True)
class PruneGroup:
    """What a plan does under one name below `reports/tub/search/`: an index directory, or `current.json`."""

    name: str
    delete: int
    """Versions it would delete, delete markers not included."""
    delete_markers: int
    keep: int


@dataclass(frozen=True, slots=True)
class PrunePlan:
    """Every version under `reports/tub/search/`, split into what is kept and what would be deleted."""

    location: str
    pointer: SearchIndexPointer | None
    """`current.json` as the plan read it; `None` when the bucket has none or it could not be read."""
    kept: tuple[ObjectVersion, ...]
    doomed: tuple[ObjectVersion, ...]
    """What `--execute` deletes. Empty when the plan refuses."""
    refusals: tuple[PruneRefusal, ...]

    @property
    def index_id(self) -> str | None:
        return self.pointer.index_id if self.pointer is not None else None

    @property
    def keep_prefix(self) -> str | None:
        """The current index's directory, `reports/tub/search/<index id>/`."""
        return _directory_of(self.pointer.index_id) if self.pointer is not None else None

    @property
    def groups(self) -> tuple[PruneGroup, ...]:
        """Counts by index directory, then `current.json`, in key order."""
        names = sorted({_group_of(one.key) for one in (*self.kept, *self.doomed)}, key=_group_order)
        return tuple(
            PruneGroup(
                name=name,
                delete=sum(
                    1 for one in self.doomed if _group_of(one.key) == name and not one.is_delete_marker
                ),
                delete_markers=sum(
                    1 for one in self.doomed if _group_of(one.key) == name and one.is_delete_marker
                ),
                keep=sum(1 for one in self.kept if _group_of(one.key) == name),
            )
            for name in names
        )

    @property
    def confirmation(self) -> str:
        """The code `--confirm` takes: a digest of the place, the index kept and every version deleted."""
        shown = {
            "location": self.location,
            "index_id": self.index_id,
            "delete": sorted([one.key, one.version_id or ""] for one in self.doomed),
        }
        return hashlib.sha256(json.dumps(shown, sort_keys=True).encode()).hexdigest()[:CONFIRMATION_LENGTH]

    def refusal(self, confirmation: str | None) -> PruneRefusal | None:
        """Why this plan may not be executed with `confirmation`, or `None` when it may."""
        if self.refusals:
            return self.refusals[0]
        if confirmation != self.confirmation:
            return PruneRefusal(
                code="CONFIRMATION_MISMATCH",
                message=(
                    "the confirmation code is not this plan's: run the dry run again, read it, and pass "
                    "the code it prints"
                    if confirmation
                    else "pass the confirmation code the dry run prints"
                ),
            )
        return None


@dataclass(frozen=True, slots=True)
class PruneResult:
    plan: PrunePlan
    deleted: int


class SearchIndexPruneRefused(DomainError):
    """`execute` was asked to act on a plan that refuses. The command checks first, so this is a backstop."""

    def __init__(self, refusal: PruneRefusal) -> None:
        self.refusal = refusal
        super().__init__(f"{refusal.code}: {refusal.message}")


class SearchIndexPointerMoved(DomainError):
    """`current.json` changed between the plan and the delete. Nothing was deleted."""

    def __init__(self, *, planned: str | None, now: str | None) -> None:
        self.planned = planned
        self.now = now
        super().__init__(
            f"current.json now names {now or 'nothing readable'}, not the index {planned} the plan kept; "
            "nothing was deleted. Run the dry run again"
        )


class PruneOnCloudRunDay(DomainError):
    """`--execute` on a Wednesday in Chicago, when the cloud run publishes. Nothing was deleted."""

    def __init__(self) -> None:
        super().__init__(
            "it is Wednesday in Chicago, the cloud run's day, when its search index stage moves "
            "current.json; nothing was deleted. Run it on another day"
        )


class WouldDeleteTheCurrentSearchIndex(DomainError):
    """A plan named a version of the current index or the current `current.json`. Nothing was deleted."""

    def __init__(self, index_id: str | None) -> None:
        super().__init__(
            f"refusing to delete a version of the current index {index_id} or of the current current.json; "
            "nothing was deleted"
        )


class SearchIndexPrune:
    """Plans and carries out the deletion of superseded search index versions in one bucket.

    Args:
        pointer: The bucket under the everyday credential, which reads `current.json`.
        takedown: The takedown credential's reach, built when the plan first lists.
        environment: Whose takedown role the credential must be.
        clock: Now, for the cloud run's day.
    """

    def __init__(
        self,
        *,
        pointer: EvidenceObjectStore,
        takedown: Callable[[], TakedownAccess],
        environment: str,
        clock: Callable[[], datetime],
    ) -> None:
        self._pointer = pointer
        self._takedown = takedown
        self._environment = environment
        self._clock = clock

    async def plan(self) -> PrunePlan:
        """List, read the pointer, and split the listing. Deletes nothing."""
        access = await self._signed_in_takedown()
        listed = tuple(
            one
            for one in await access.versions.list_versions(SEARCH_INDEX_PREFIX)
            if one.key.startswith(SEARCH_INDEX_PREFIX)
        )
        location = f"s3://{access.bucket}"
        try:
            pointer = await self._read_pointer()
        except _UnreadablePointer:
            return _refused(
                location,
                None,
                "SEARCH_INDEX_POINTER_UNREADABLE",
                "current.json is not a pointer this build reads",
            )
        if pointer is None:
            return _refused(
                location,
                None,
                "NO_CURRENT_SEARCH_INDEX",
                "the bucket has no current.json, so no index is kept",
            )
        if not _holds(listed, pointer):
            return _refused(
                location,
                pointer,
                "POINTER_NOT_IN_LISTING",
                f"current.json names index {pointer.index_id}, which the listing does not hold: a publish "
                "may be under way. Nothing is deleted; run the dry run again later",
            )
        keep = _directory_of(pointer.index_id)
        kept = tuple(one for one in listed if one.key.startswith(keep) or _is_current_pointer(one))
        doomed = tuple(one for one in listed if not one.key.startswith(keep) and not _is_current_pointer(one))
        return PrunePlan(location=location, pointer=pointer, kept=kept, doomed=doomed, refusals=())

    async def execute(self, plan: PrunePlan, *, confirmation: str | None) -> PruneResult:
        """Delete the plan's versions, after the last checks. Call it holding the bucket's run lock."""
        refusal = plan.refusal(confirmation)
        if refusal is not None:
            raise SearchIndexPruneRefused(refusal)
        self.refuse_on_cloud_run_day()
        try:
            now = await self._read_pointer()
        except _UnreadablePointer:
            now = None
        if now != plan.pointer:
            raise SearchIndexPointerMoved(
                planned=plan.index_id, now=now.index_id if now is not None else None
            )
        _refuse_the_current(plan)
        if not plan.doomed:
            return PruneResult(plan=plan, deleted=0)
        deleted = await self._takedown().versions.delete_versions(plan.doomed)
        return PruneResult(plan=plan, deleted=deleted)

    def refuse_on_cloud_run_day(self) -> None:
        """Raise :class:`PruneOnCloudRunDay` on a Wednesday in Chicago: before the lock, and again inside."""
        if is_cloud_run_day(self._clock()):
            raise PruneOnCloudRunDay

    async def _signed_in_takedown(self) -> TakedownAccess:
        access = self._takedown()
        required = takedown_permission_set(self._environment)
        role_name = await access.caller.assumed_role_name()
        if permission_set_of(role_name) != required:
            raise NotTheTakedownRole(
                access.profile, role_name=role_name, required=required, environment=self._environment
            )
        return access

    async def _read_pointer(self) -> SearchIndexPointer | None:
        """`current.json`, or `None` when there is none. Raises :class:`_UnreadablePointer`."""
        with tempfile.TemporaryDirectory(prefix="tub-index-prune-") as scratch:
            landed = Path(scratch) / "current.json"
            try:
                await self._pointer.get_file(SEARCH_INDEX_POINTER_KEY, landed)
            except NotFound:
                return None
            try:
                return SearchIndexPointer.model_validate_json(landed.read_bytes())
            except ValidationError:
                raise _UnreadablePointer from None


class _UnreadablePointer(Exception):
    pass


def _refused(location: str, pointer: SearchIndexPointer | None, code: str, message: str) -> PrunePlan:
    return PrunePlan(
        location=location,
        pointer=pointer,
        kept=(),
        doomed=(),
        refusals=(PruneRefusal(code=code, message=message),),
    )


def _directory_of(index_id: str) -> str:
    return f"{SEARCH_INDEX_PREFIX}{index_id}/"


def _is_current_pointer(version: ObjectVersion) -> bool:
    return version.key == SEARCH_INDEX_POINTER_KEY and version.is_latest and not version.is_delete_marker


def _is_current(version: ObjectVersion, key: str) -> bool:
    return version.key == key and version.is_latest and not version.is_delete_marker


def _holds(listed: Sequence[ObjectVersion], pointer: SearchIndexPointer) -> bool:
    """Whether the listing holds the pointer's index, current, inside its directory, and a current pointer."""
    keep = _directory_of(pointer.index_id)
    named = (pointer.manifest_key, pointer.object_key)
    return (
        all(key.startswith(keep) for key in named)
        and all(any(_is_current(one, key) for one in listed) for key in named)
        and any(_is_current_pointer(one) for one in listed)
    )


def _refuse_the_current(plan: PrunePlan) -> None:
    """The last check before the delete: nothing kept, and nothing outside `reports/tub/search/`."""
    keep = plan.keep_prefix
    for one in plan.doomed:
        if keep is None or one.key.startswith(keep) or _is_current_pointer(one) or one in plan.kept:
            raise WouldDeleteTheCurrentSearchIndex(plan.index_id)
        if not one.key.startswith(SEARCH_INDEX_PREFIX) or one.key == SEARCH_INDEX_PREFIX:
            raise WouldDeleteTheCurrentSearchIndex(plan.index_id)


def _group_of(key: str) -> str:
    """`<index id>/` for a key in an index's directory, the name itself for one directly under the prefix."""
    rest = key.removeprefix(SEARCH_INDEX_PREFIX)
    head, slash, _ = rest.partition("/")
    return f"{head}/" if slash else head


def _group_order(name: str) -> tuple[bool, str]:
    """Index directories first, then `current.json` and anything else beside it."""
    return (not name.endswith("/"), name)

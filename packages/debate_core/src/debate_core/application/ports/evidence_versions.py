"""The takedown's view of an evidence store: every version of an object, and deleting them.

:class:`~debate_core.application.ports.evidence_store.EvidenceObjectStore` and
:class:`~debate_core.application.ports.persistence.SnapshotStore` deliberately have no delete.
Evidence is removed in exactly one situation — a removal request under
`docs/policies/caselist-data-use.md` — and when it is, *everything* goes: the object and every
noncurrent version the bucket kept of it, because "removed" with a restorable version still in the
bucket is not removed (`v1-e30-t07`, spec forbidden list). This port is that operation and nothing
else, and the only service built with one is
:class:`~debate_core.application.caselist.removal_service.CaselistRemovalService`.

In the bucket it is reached through the `EvidenceRemoval` permission set (`DEBATE_REMOVAL_PROFILE`),
the only credential in the account that can delete evidence or list versions. The everyday
`EvidenceOperator` credential can do neither: its implementation of :meth:`list_versions` raises
:class:`~debate_core.application.errors.StoreAccessDenied`, which a dry run reports as "versions not
counted" rather than failing.

On this machine a file has exactly one version, so the filesystem implementation lists each file as
one current version with no id, and deleting it unlinks the file.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from debate_core.application.ports.evidence_store import ObjectKey

__all__ = ["EvidenceVersionStore", "ObjectVersion"]


@dataclass(frozen=True, slots=True, order=True)
class ObjectVersion:
    """One version of one object: the current one, a noncurrent one, or a delete marker."""

    key: ObjectKey
    version_id: str | None
    """The store's id for the version. `None` in a store that keeps no versions."""
    size: int = 0
    is_latest: bool = True
    is_delete_marker: bool = False


@runtime_checkable
class EvidenceVersionStore(Protocol):
    """Lists and deletes every version of evidence objects. Takedowns only."""

    @property
    def location(self) -> str:
        """What this store is, for messages: a directory, or `s3://bucket`. Never a credential."""
        ...

    async def list_versions(self, prefix: str) -> tuple[ObjectVersion, ...]:
        """Every version of every object whose key starts with `prefix`, delete markers included.

        Sorted by key, then current version first. A prefix nothing matches lists nothing.
        """
        ...

    async def get_version_file(self, version: ObjectVersion, destination: Path) -> None:
        """Download one version's bytes to `destination`, so a takedown can read a superseded manifest."""
        ...

    async def delete_versions(self, versions: Sequence[ObjectVersion]) -> int:
        """Permanently delete each of `versions` and return how many were deleted.

        A version that is already gone counts as deleted: a takedown that failed part-way is
        finished by running it again.
        """
        ...

"""The takedown's view of an evidence store: every version of an object, and deleting them.

:class:`~debate_core.application.ports.evidence_store.EvidenceObjectStore` and
:class:`~debate_core.application.ports.persistence.SnapshotStore` deliberately have no delete.
Evidence is removed in exactly one situation — a removal request under
`docs/policies/caselist-data-use.md` — and when it is, *everything* goes: the object and every
noncurrent version the bucket kept of it, because "removed" with a restorable version still in the
bucket is not removed (`v1-e30-t07`, spec forbidden list). This port is that operation and nothing
else, and the only service that deletes through one is
:class:`~debate_core.application.caselist.removal_service.CaselistRemovalService`.

In the bucket, deleting is reached through the `EvidenceRemoval` permission set
(`DEBATE_REMOVAL_PROFILE`), the only credential in the account that can delete evidence. The
everyday `EvidenceOperator` credential cannot delete. It may list versions, read-only, under the
prefixes a takedown removes from (`v1-e29-t06`, applied in dev and prod on 2026-10-08), which is
what lets a removal's dry run count them and `caselist status` report what a removal left
(:mod:`~debate_core.application.caselist.removal_residue`, `v1-e30-t10`); both call
:meth:`list_versions` and nothing else. In an environment where that grant is not applied,
:meth:`list_versions` raises :class:`~debate_core.application.errors.StoreAccessDenied`, which the
dry run reports as "versions not counted" and the status as "not checked", rather than failing or
reading it as nothing there.

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
    """Lists and deletes every version of evidence objects. Deleting is for takedowns only."""

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

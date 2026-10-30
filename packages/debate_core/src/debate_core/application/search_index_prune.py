"""Superseded search index versions in a bucket, listed and then deleted (`v1-e39-t15`).

SKELETON for the red run: refuses nothing.
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final
from zoneinfo import ZoneInfo

from debate_core.application.caselist.removal_service import TakedownAccess
from debate_core.application.errors import DomainError, NotFound
from debate_core.application.ports.evidence_store import EvidenceObjectStore
from debate_core.application.ports.evidence_versions import ObjectVersion
from debate_core.domain.search_index import SEARCH_INDEX_POINTER_KEY, SEARCH_INDEX_PREFIX, SearchIndexPointer

__all__ = [
    "CLOUD_RUN_ZONE",
    "PRUNE_COMMAND",
    "PruneGroup",
    "PruneOnCloudRunDay",
    "PruneRefusal",
    "PruneResult",
    "PrunePlan",
    "SearchIndexPointerMoved",
    "SearchIndexPrune",
    "SearchIndexPruneRefused",
    "WouldDeleteTheCurrentSearchIndex",
    "is_cloud_run_day",
]

PRUNE_COMMAND: Final = "tub index prune"
CLOUD_RUN_ZONE: Final = ZoneInfo("America/Chicago")


def is_cloud_run_day(now: datetime) -> bool:
    del now
    return False


@dataclass(frozen=True, slots=True)
class PruneRefusal:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class PruneGroup:
    name: str
    delete: int
    delete_markers: int
    keep: int


@dataclass(frozen=True, slots=True)
class PrunePlan:
    location: str
    pointer: SearchIndexPointer | None
    kept: tuple[ObjectVersion, ...]
    doomed: tuple[ObjectVersion, ...]
    refusals: tuple[PruneRefusal, ...]

    @property
    def index_id(self) -> str | None:
        return self.pointer.index_id if self.pointer is not None else None

    @property
    def groups(self) -> tuple[PruneGroup, ...]:
        return ()

    @property
    def confirmation(self) -> str:
        return "000000000000"

    def refusal(self, confirmation: str | None) -> PruneRefusal | None:
        del confirmation
        return None


@dataclass(frozen=True, slots=True)
class PruneResult:
    plan: PrunePlan
    deleted: int


class SearchIndexPruneRefused(DomainError):
    def __init__(self, refusal: PruneRefusal) -> None:
        self.refusal = refusal
        super().__init__(f"{refusal.code}: {refusal.message}")


class SearchIndexPointerMoved(DomainError):
    pass


class PruneOnCloudRunDay(DomainError):
    pass


class WouldDeleteTheCurrentSearchIndex(DomainError):
    pass


class SearchIndexPrune:
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
        access = self._takedown()
        listed = await access.versions.list_versions(SEARCH_INDEX_PREFIX)
        return PrunePlan(
            location=f"s3://{access.bucket}",
            pointer=await self._read_pointer(),
            kept=(),
            doomed=tuple(listed),
            refusals=(),
        )

    async def execute(self, plan: PrunePlan, *, confirmation: str | None) -> PruneResult:
        del confirmation
        deleted = await self._takedown().versions.delete_versions(plan.doomed)
        return PruneResult(plan=plan, deleted=deleted)

    async def _read_pointer(self) -> SearchIndexPointer | None:
        with tempfile.TemporaryDirectory(prefix="tub-index-prune-") as scratch:
            landed = Path(scratch) / "current.json"
            try:
                await self._pointer.get_file(SEARCH_INDEX_POINTER_KEY, landed)
            except NotFound:
                return None
            return SearchIndexPointer.model_validate_json(landed.read_bytes())


def _unused(versions: Sequence[ObjectVersion]) -> None:
    del versions

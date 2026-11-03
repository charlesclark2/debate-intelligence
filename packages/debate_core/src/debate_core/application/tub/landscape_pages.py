"""The newest landscape bundles, as the pilot's landscape pages read them (`v1-e39-t17`, gate item 11).

:class:`LandscapeShelf` holds, for each caselist with a published bundle, the newest snapshot's
`report.md` and, unless a removal deleted it, its `schools.md`, each turned into whatever the pages
need by the `prepare` function the app gives it (rendered pages, in `debate_api`), so a page view
renders nothing it rendered a moment ago.

## Held no longer than five minutes

Before answering, a shelf older than :data:`~debate_core.domain.landscape_pages.LANDSCAPE_HOLD` lists
`reports/landscape/` again. A caselist whose newest bundle's files are the ones held (by key, size and
modification time) keeps what was prepared; any other is read again and prepared again. So a deleted
school view, a republished report or a newer snapshot reaches the pages within five minutes, and a
caselist whose bundles are all gone drops off.

If the listing or a read fails (a file deleted between the two included), the shelf is dropped and
:class:`LandscapeUnavailable` raised: an old shelf is never served past its five minutes because the
bucket did not answer.

## What it reads, and how

Through :class:`LandscapeObjects`, which :class:`~debate_core.integrations.s3.S3EvidenceObjectStore`
already is: one listing of the prefix (the function's role may list `reports/landscape/` and nothing
else), and each file it reads downloaded to a scratch directory that is gone when the read is. Nothing
here logs a key, a school or a team code.
"""

from __future__ import annotations

import asyncio
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Protocol

from debate_core.application.errors import BlobIntegrityError, DomainError, NotFound, StoreError
from debate_core.application.ports.evidence_store import ObjectInfo, ObjectKey
from debate_core.domain.landscape_pages import (
    LANDSCAPE_HOLD,
    LANDSCAPE_PREFIX,
    REPORT_FILE,
    SCHOOL_VIEW_FILE,
    bundle_file,
)

__all__ = [
    "HeldBundle",
    "LandscapeBundle",
    "LandscapeObjects",
    "LandscapeShelf",
    "LandscapeUnavailable",
    "newest_bundles",
]


class LandscapeObjects(Protocol):
    """The two reads of the evidence bucket the landscape pages make."""

    async def list_objects(self, prefix: str) -> tuple[ObjectInfo, ...]: ...

    async def get_file(self, key: ObjectKey, destination: Path) -> ObjectInfo: ...


class LandscapeUnavailable(DomainError):
    """The bundles could not be read, so no landscape page is shown."""

    def __init__(self) -> None:
        super().__init__("the landscape bundles could not be read")


@dataclass(frozen=True, slots=True)
class PublishedBundle:
    """The files of one caselist's newest complete bundle, as the listing gave them."""

    caselist: str
    snapshot: date
    report: ObjectInfo
    school_view: ObjectInfo | None

    @property
    def files(self) -> tuple[tuple[str, int, datetime | None], ...]:
        """What says whether these are the files already held: each one's key, size and time."""
        return tuple(
            (one.key, one.size, one.last_modified)
            for one in (self.report, self.school_view)
            if one is not None
        )


@dataclass(frozen=True, slots=True)
class LandscapeBundle:
    """One newest bundle's two Markdown files, as `prepare` is given them."""

    caselist: str
    snapshot: date
    report_markdown: str
    school_view_markdown: str | None
    """`None` when the snapshot holds no `schools.md`: a removal deleted it."""


@dataclass(frozen=True, slots=True)
class HeldBundle[PreparedT]:
    caselist: str
    snapshot: date
    prepared: PreparedT
    files: tuple[tuple[str, int, datetime | None], ...]


def newest_bundles(listing: tuple[ObjectInfo, ...]) -> dict[str, PublishedBundle]:
    """For each caselist, its newest snapshot holding `report.md`, and that snapshot's `schools.md` if any."""
    by_snapshot: dict[tuple[str, date], dict[str, ObjectInfo]] = {}
    for info in listing:
        found = bundle_file(info.key)
        if found is not None and found.name in (REPORT_FILE, SCHOOL_VIEW_FILE):
            by_snapshot.setdefault((found.caselist, found.snapshot), {})[found.name] = info
    newest: dict[str, PublishedBundle] = {}
    for (caselist, snapshot), files in sorted(by_snapshot.items()):
        if REPORT_FILE in files:
            newest[caselist] = PublishedBundle(
                caselist=caselist,
                snapshot=snapshot,
                report=files[REPORT_FILE],
                school_view=files.get(SCHOOL_VIEW_FILE),
            )
    return newest


class LandscapeShelf[PreparedT]:
    """The newest bundles, held at most five minutes, each prepared once while it is unchanged."""

    def __init__(
        self,
        objects: LandscapeObjects,
        *,
        prepare: Callable[[LandscapeBundle], PreparedT],
        clock: Callable[[], datetime],
    ) -> None:
        self._objects = objects
        self._prepare = prepare
        self._clock = clock
        self._held: dict[str, HeldBundle[PreparedT]] = {}
        self._read_at: datetime | None = None
        self._lock = asyncio.Lock()

    async def bundles(self) -> Mapping[str, HeldBundle[PreparedT]]:
        """Every caselist's newest bundle, by caselist, read again first if the shelf is five minutes old.

        :class:`LandscapeUnavailable` when the bucket cannot be listed or a file read.
        """
        async with self._lock:
            now = self._clock()
            if self._read_at is None or now - self._read_at >= LANDSCAPE_HOLD:
                try:
                    self._held = await self._read(self._held)
                except (StoreError, NotFound, BlobIntegrityError):
                    self._held, self._read_at = {}, None
                    raise LandscapeUnavailable() from None
                self._read_at = now
            return dict(self._held)

    async def _read(self, held: Mapping[str, HeldBundle[PreparedT]]) -> dict[str, HeldBundle[PreparedT]]:
        fresh: dict[str, HeldBundle[PreparedT]] = {}
        for caselist, published in newest_bundles(await self._objects.list_objects(LANDSCAPE_PREFIX)).items():
            kept = held.get(caselist)
            if kept is not None and (kept.snapshot, kept.files) == (published.snapshot, published.files):
                fresh[caselist] = kept
                continue
            bundle = LandscapeBundle(
                caselist=caselist,
                snapshot=published.snapshot,
                report_markdown=await self._text(published.report),
                school_view_markdown=(
                    None if published.school_view is None else await self._text(published.school_view)
                ),
            )
            prepared = await asyncio.to_thread(self._prepare, bundle)
            fresh[caselist] = HeldBundle(
                caselist=caselist, snapshot=published.snapshot, prepared=prepared, files=published.files
            )
        return fresh

    async def _text(self, info: ObjectInfo) -> str:
        with tempfile.TemporaryDirectory(prefix="tub-landscape-") as scratch:
            destination = Path(scratch) / "bundle-file"
            await self._objects.get_file(info.key, destination)
            return destination.read_text(encoding="utf-8", errors="replace")

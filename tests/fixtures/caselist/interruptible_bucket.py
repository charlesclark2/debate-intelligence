"""A bucket that can be made to fail, or to be killed, part-way through a publish.

Shared by the publisher's and the status comparison's tests, which both need the state an
interrupted publish leaves behind. It wraps the real S3 adapter and passes every call through;
all it adds is a hook that runs before each `put_file` and may raise.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path

from debate_core.application.ports.evidence_store import ObjectInfo, ObjectKey
from debate_core.integrations.s3 import S3EvidenceObjectStore

__all__ = ["ScriptedBucket", "SimulatedKill"]


class SimulatedKill(BaseException):
    """What a Ctrl-C or a killed process looks like to the code it interrupts."""


class ScriptedBucket:
    """The real S3 store, with a hook that may raise before a `put_file` reaches it.

    Uploads already started when a :class:`SimulatedKill` lands keep running in the adapter's
    worker threads — in a real killed process they would die with it — so a test awaits
    :meth:`settle` before it reads the bucket, and what it reads is then stable.
    """

    def __init__(
        self, inner: S3EvidenceObjectStore, before_put: Callable[[ObjectKey, int], None] | None = None
    ) -> None:
        self.inner = inner
        self.before_put = before_put
        self.puts = 0
        self._uploads: list[asyncio.Future[ObjectInfo]] = []

    async def settle(self) -> None:
        """Wait for every upload that was started, however its caller ended."""
        await asyncio.gather(*self._uploads, return_exceptions=True)

    async def list_objects(self, prefix: str) -> tuple[ObjectInfo, ...]:
        return await self.inner.list_objects(prefix)

    async def head(self, key: ObjectKey) -> ObjectInfo:
        return await self.inner.head(key)

    async def put_file(self, key: ObjectKey, source: Path) -> ObjectInfo:
        self.puts += 1
        if self.before_put is not None:
            self.before_put(key, self.puts)
        upload = asyncio.ensure_future(self.inner.put_file(key, source))
        self._uploads.append(upload)
        return await asyncio.shield(upload)

    async def get_file(self, key: ObjectKey, destination: Path) -> ObjectInfo:
        return await self.inner.get_file(key, destination)

"""The seed: a bucket's run lock created, and the machine's run state uploaded (`v1-e40-t04`, ADR-0020 (4)).

`debate-research caselist seed-run-state`, run once per home environment by the operator, at the
cutover (`v1-e40-t06`'s step, after the Mac's agent is unloaded: the PM's ruling 3(b) of
2026-10-24). Until a bucket is seeded no bucket-mode command starts against it
(:class:`~debate_core.application.caselist.run_lock.RunStateNotSeeded`); once it is, a local-mode
command refuses it (:class:`~debate_core.application.caselist.run_lock.BucketKeepsRunState`).

**The plan** (the dry run) reads and writes nothing in the bucket but a listing of the lock's key
and a `HeadObject` of each local manifest. It refuses when:

* the bucket already holds a lock object: it is seeded;
* a local manifest is one the publisher withholds (the publisher's own rule and message, as the
  save's);
* a local manifest is not in the bucket with the same SHA-256: this machine imported something it
  has not published, which the bundle would record as held while the bucket does not hold it.

**The seed** (`--execute`) plans again, then:

1. creates the lock object with `If-None-Match: *`, held by this machine, so that of two seeds only
   the first gets past this step;
2. uploads the run-state bundle and the five state files, the bundle by the save's own rule;
3. checks each back: the bucket's recorded SHA-256 of each is the one uploaded;
4. releases the lock, whatever happened after step 1.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from debate_core.application.caselist.run_lock import BucketRunLock
from debate_core.application.caselist.run_state import (
    RUN_STATE_BUNDLE_KEY,
    STATE_FILES,
    BundleSave,
    RunState,
    RunStateWithheld,
    state_key,
)
from debate_core.application.errors import DomainError, NotFound
from debate_core.application.ports.evidence_store import EvidenceObjectStore

__all__ = ["SEED_COMMAND", "RunStateSeed", "SeedPlan", "SeedRefused", "SeedReport"]

SEED_COMMAND: Final = "caselist seed-run-state"

_EMPTY_SHA256: Final = hashlib.sha256(b"").hexdigest()


class SeedRefused(DomainError):
    """The seed would not be safe, so nothing was written. Says why, and what fixes it."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"the bucket was not seeded, and nothing was written to it: {reason}")


@dataclass(frozen=True, slots=True)
class SeedPlan:
    """What a seed would upload, and whether it may."""

    seeded_already: bool
    manifests: int
    state_files: tuple[str, ...]
    """The state files this machine holds, by name; the others are uploaded as absent."""
    unconfirmed: tuple[str, ...] = ()
    withheld: str | None = None

    @property
    def refusal(self) -> str | None:
        if self.seeded_already:
            return (
                "the bucket already holds a run lock, so it is seeded; a bucket is seeded once, and its "
                "state is the bucket's from then on"
            )
        if self.withheld is not None:
            return self.withheld
        if self.unconfirmed:
            return (
                f"{len(self.unconfirmed)} manifest(s) on this machine are not in the bucket with the same "
                "SHA-256; publish them first (`caselist pull --publish-pending`, or `caselist publish "
                "--caselist <slug>`), so that the bundle records nothing the bucket does not hold"
            )
        return None


@dataclass(frozen=True, slots=True)
class SeedReport:
    """What the seed uploaded and checked back."""

    plan: SeedPlan
    bundle: BundleSave
    checked: tuple[str, ...]
    """Every key the seed uploaded and found in the bucket with the digest it uploaded."""


class RunStateSeed:
    """The seed. See the module docstring.

    Args:
        lock: This command's lease on the bucket's run lock, which it creates.
        state: The run's state in the bucket, through the fenced client.
        bucket: The same bucket, read to check each upload back.
        data_dir: The data directory the state files are in.
    """

    def __init__(
        self,
        *,
        lock: Callable[[], BucketRunLock],
        state: Callable[[], RunState],
        bucket: EvidenceObjectStore,
        data_dir: Path,
    ) -> None:
        self._lock = lock
        self._state = state
        self._bucket = bucket
        self._data_dir = Path(data_dir)

    async def plan(self) -> SeedPlan:
        seeded = await asyncio.to_thread(self._lock().bucket_is_seeded)
        state = self._state()
        manifests = len(await state.local_manifests())
        present = tuple(name for name in STATE_FILES if (self._data_dir / name).is_file())
        try:
            await state.refuse_withheld()
        except RunStateWithheld as withheld:
            return SeedPlan(
                seeded_already=seeded, manifests=manifests, state_files=present, withheld=str(withheld)
            )
        return SeedPlan(
            seeded_already=seeded,
            manifests=manifests,
            state_files=present,
            unconfirmed=await state.unconfirmed_manifests(),
        )

    async def execute(self) -> SeedReport:
        plan = await self.plan()
        if plan.refusal is not None:
            raise SeedRefused(plan.refusal)
        lock = self._lock()
        await asyncio.to_thread(lock.create, command=SEED_COMMAND)
        try:
            state = self._state()
            bundle = await state.save_bundle()
            if not bundle.saved:
                raise SeedRefused(bundle.reason)
            await state.save_state_files()
            checked = await self._check_back(bundle)
        finally:
            await asyncio.to_thread(lock.release)
        return SeedReport(plan=plan, bundle=bundle, checked=checked)

    async def _check_back(self, bundle: BundleSave) -> tuple[str, ...]:
        expected = {RUN_STATE_BUNDLE_KEY: bundle.sha256}
        for name in STATE_FILES:
            local = self._data_dir / name
            expected[state_key(name)] = _sha256_of(local) if local.is_file() else _EMPTY_SHA256
        for key, digest in expected.items():
            try:
                stored = await self._bucket.head(key)
            except NotFound:
                raise SeedRefused(f"{key} is not in the bucket after its upload") from None
            if stored.sha256 != digest:
                raise SeedRefused(f"{key} is in the bucket with another SHA-256 than was uploaded")
        return tuple(expected)


def _sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

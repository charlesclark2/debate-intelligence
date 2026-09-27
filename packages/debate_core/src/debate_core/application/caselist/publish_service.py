"""Publishing a caselist's imported snapshots to the evidence bucket, sources first, manifest last.

`debate-research caselist publish` is a thin command over :class:`CaselistPublishService`. What it
does is small; the order it does it in is the whole design.

## Why the order is the point

An OpenCaselist weekly download is a window of roughly a week's edits. The site keeps a
back-catalogue of them and a regenerated complete archive (ADR-0017), so a window missed today can
be fetched later — but only for as long as the site keeps it, and retention is undocumented. The
local evidence store is the archive of record, and publishing is what stops it being a single
laptop.

The bucket's `manifests/<caselist>/<snapshot>.jsonl` is what everything downstream trusts:
`caselist status` reads a manifest's presence as "this snapshot is published", and the scheduled
sync (`v1-e34-t02`) resumes from it. So **a manifest is written only after every source it names
is in the bucket and its checksum has been confirmed there**, and a half-published snapshot is one
with sources and no manifest — visibly incomplete, never a snapshot that looks whole and is not.

The rule is enforced as one check, not as the absence of a bug. After a snapshot's sources have
all finished, its manifest goes up only if *every* source key it names (apart from suppressed ones)
is in the set of keys this run has confirmed: uploaded and verified, or found present and verified.
A failed upload, a checksum that disagrees, a source missing from this machine or a run killed
part-way all leave a key outside that set, and the manifest is withheld.

## Idempotent and resumable

Nothing is uploaded that the bucket already holds with the right checksum. A listing says which
keys exist but states no digest (`debate_core.application.ports.evidence_store`), so a listed source
is headed and skipped only if the digest the bucket recorded for it equals the digest in its key —
which also catches an object that some other tool put there without one. A run that was interrupted
is resumed by running it again: what landed is found, verified and skipped; what did not is
uploaded; the manifest follows.

A content-addressed key is never overwritten. If the bucket holds different bytes, or no recorded
digest, under a source's key, that source fails, its snapshot's manifest is withheld, and a person
decides what happened (`docs/guides/evidence-store-cli.md`).

## Verified twice

Before an upload, the local blob is re-hashed, because a blob that no longer matches its own key
must not be published under it. After the upload, the bucket is asked separately for the digest it
recorded; `put_file` returns what was sent, and this is what arrived.

## What is logged

Counts, the caselist, the snapshot, and sha256 values. Never a school, a team code, a filename or a
disclosure path, in a log line, an error message or anything a traceback would carry — those exist
in the manifest body and nowhere this module writes (`docs/policies/caselist-data-use.md`,
personal-data rule 4). Every key this module names is a digest or a caselist and a date.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Collection, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from debate_core.application.caselist.evidence_listing import (
    LocalEvidence,
    list_remote_evidence,
    local_blob_sizes,
    local_file,
    read_local_snapshots,
)
from debate_core.application.caselist.publish_plan import (
    PlannedSource,
    PublishPlan,
    SnapshotPlan,
    SourceAction,
    build_publish_plan,
    local_blob_key,
    manifest_prefix,
    snapshot_manifest_key,
)
from debate_core.application.errors import (
    BlobIntegrityError,
    DomainError,
    NotFound,
    StoreAccessDenied,
    StoreCredentialsExpired,
)
from debate_core.application.ports.evidence_store import EvidenceObjectStore, ObjectInfo, ObjectKey
from debate_core.domain import Sha256Hex

__all__ = [
    "DEFAULT_CONCURRENCY",
    "CaselistPublishService",
    "ManifestOutcome",
    "NothingToPublish",
    "PublishReport",
    "SnapshotOutcome",
    "SourceOutcome",
    "SourceResult",
    "error_code_of",
]

logger = logging.getLogger(__name__)

DEFAULT_CONCURRENCY: Final = 8
"""How many sources are in flight at once.

Enough to hide S3's per-request latency — a first publish of the September windows is about 2,300
uploads, each a PutObject and two HeadObjects — and few enough that one laptop's upload link and
the adapter's thread pool are not the bottleneck being tuned.
"""


class NothingToPublish(DomainError):
    """This machine holds no manifest for what was asked to be published.

    Names the caselist and snapshot only. Import the archive first (`caselist import`).
    """

    def __init__(self, caselist: str, snapshot: str | None) -> None:
        self.caselist = caselist
        self.snapshot = snapshot
        what = snapshot_manifest_key(caselist, snapshot) if snapshot else f"{manifest_prefix(caselist)}*"
        super().__init__(f"no local manifest at {what}; import the archive before publishing it")


class SourceResult(StrEnum):
    """What happened to one source of one snapshot."""

    UPLOADED = "uploaded"
    """Uploaded in this run, and the bucket's recorded digest confirmed."""

    SKIPPED = "skipped"
    """Already in the bucket with the right digest, confirmed in this run."""

    SUPPRESSED = "suppressed"
    """On the removal suppression list; never uploaded."""

    FAILED = "failed"
    """Not confirmed in the bucket. The snapshot's manifest is withheld."""


class ManifestOutcome(StrEnum):
    """What happened to a snapshot's manifest."""

    UPLOADED = "uploaded"
    SKIPPED = "skipped"
    """The bucket already held these bytes."""

    WITHHELD = "withheld"
    """Not written, because at least one source was not confirmed. The snapshot is incomplete."""

    FAILED = "failed"
    """Every source was confirmed, and the manifest itself did not upload and verify."""


@dataclass(frozen=True, slots=True)
class SourceOutcome:
    """One source's result. `error_*` are set only for :attr:`SourceResult.FAILED`."""

    sha256: Sha256Hex
    key: ObjectKey
    result: SourceResult
    error_code: str | None = None
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class SnapshotOutcome:
    """What publishing one snapshot did."""

    caselist: str
    snapshot: str
    manifest_key: ObjectKey
    sources: tuple[SourceOutcome, ...]
    manifest: ManifestOutcome
    manifest_error: str | None = None

    def of(self, result: SourceResult) -> tuple[SourceOutcome, ...]:
        return tuple(outcome for outcome in self.sources if outcome.result is result)

    @property
    def failed(self) -> tuple[SourceOutcome, ...]:
        return self.of(SourceResult.FAILED)

    @property
    def complete(self) -> bool:
        """True when the bucket now holds this snapshot's manifest, and so all of its sources."""
        return self.manifest in (ManifestOutcome.UPLOADED, ManifestOutcome.SKIPPED)


@dataclass(frozen=True, slots=True)
class PublishReport:
    """What a publish did, or for a dry run, the plan alone."""

    plan: PublishPlan
    applied: bool
    snapshots: tuple[SnapshotOutcome, ...] = ()

    @property
    def succeeded(self) -> bool:
        """True for a dry run whose plan blocks nothing, and for a run that completed every snapshot."""
        if not self.applied:
            return all(not snapshot.blocked for snapshot in self.plan.snapshots)
        return all(snapshot.complete for snapshot in self.snapshots)

    @property
    def failed_sha256(self) -> tuple[Sha256Hex, ...]:
        """Every source digest that failed, once each, sorted: what the error message names."""
        if not self.applied:
            return tuple(sorted({source.sha256 for plan in self.plan.snapshots for source in plan.blocked}))
        return tuple(sorted({outcome.sha256 for snapshot in self.snapshots for outcome in snapshot.failed}))

    def count(self, result: SourceResult) -> int:
        """How many *distinct* source objects ended with `result` across the run."""
        return len({outcome.key for snapshot in self.snapshots for outcome in snapshot.of(result)})


class CaselistPublishService:
    """Publishes a caselist's local snapshots to the bucket of the environment it was built for.

    Built by the composition root with this machine's evidence store and the environment's bucket;
    it reads no settings and knows no bucket name (architecture proposal §6).

    ::

        service = CaselistPublishService(local=local_evidence, remote=bucket_store)
        plan = await service.plan("hsld26")            # a --dry-run stops here
        report = await service.execute(plan)

    Args:
        local: This machine's manifests and blobs.
        remote: The environment's evidence bucket.
        suppressed: Digests on the removal suppression list, never uploaded. The list and the check
            that fills it are `v1-e30-t07`'s; until it ships the composition root passes nothing.
        concurrency: Sources in flight at once; see :data:`DEFAULT_CONCURRENCY`.
    """

    def __init__(
        self,
        *,
        local: LocalEvidence,
        remote: EvidenceObjectStore,
        suppressed: Collection[Sha256Hex] = frozenset(),
        concurrency: int = DEFAULT_CONCURRENCY,
    ) -> None:
        if concurrency < 1:
            raise ValueError("concurrency must be at least 1")
        self._local = local
        self._remote = remote
        self._suppressed = frozenset(suppressed)
        self._concurrency = concurrency

    async def plan(self, caselist: str, snapshot: str | None = None) -> PublishPlan:
        """Work out what publishing would do, reading both sides and writing nothing.

        Raises :class:`NothingToPublish` when this machine holds no manifest for the request.
        """
        snapshots = await read_local_snapshots(self._local, caselist, snapshot)
        if not snapshots:
            raise NothingToPublish(caselist, snapshot)
        local_blobs = await local_blob_sizes(self._local)
        remote = await list_remote_evidence(self._remote, caselist)
        return build_publish_plan(
            caselist,
            snapshots,
            local_blobs=local_blobs.keys(),
            remote=remote,
            suppressed=self._suppressed,
        )

    async def execute(self, plan: PublishPlan) -> PublishReport:
        """Publish exactly what `plan` names, snapshot by snapshot, each manifest last.

        Failures of one source are collected, not raised: the report names every one and the
        command's exit code comes from :attr:`PublishReport.succeeded`. The exceptions are an
        expired or refused credential, which would be true of every remaining object and end the
        run at once — with no manifest written for the snapshot in progress.
        """
        confirmed: set[ObjectKey] = set()
        failed: dict[ObjectKey, SourceOutcome] = {}
        outcomes: list[SnapshotOutcome] = []
        for snapshot in plan.snapshots:
            outcome = await self._publish_snapshot(snapshot, confirmed, failed)
            _log_snapshot(outcome)
            outcomes.append(outcome)
        return PublishReport(plan=plan, applied=True, snapshots=tuple(outcomes))

    # --------------------------------------------------------------------------------------
    # One snapshot
    # --------------------------------------------------------------------------------------

    async def _publish_snapshot(
        self, plan: SnapshotPlan, confirmed: set[ObjectKey], failed: dict[ObjectKey, SourceOutcome]
    ) -> SnapshotOutcome:
        sources = await _bounded(
            [
                lambda planned=planned: self._publish_source(planned, confirmed, failed)
                for planned in plan.sources
            ],
            limit=self._concurrency,
        )

        # The invariant, checked directly: every source this manifest names is confirmed in the
        # bucket by this run, or the manifest is not written.
        unconfirmed = [
            planned.sha256
            for planned in plan.sources
            if planned.action is not SourceAction.SUPPRESSED and planned.key not in confirmed
        ]
        if unconfirmed:
            return SnapshotOutcome(
                caselist=plan.caselist,
                snapshot=plan.snapshot,
                manifest_key=plan.manifest_key,
                sources=tuple(sources),
                manifest=ManifestOutcome.WITHHELD,
                manifest_error=(
                    f"{len(unconfirmed)} source(s) not confirmed in the bucket: "
                    + ", ".join(sorted(unconfirmed))
                ),
            )

        try:
            manifest = await self._publish_manifest(plan)
            manifest_error = None
        except (StoreCredentialsExpired, StoreAccessDenied):
            raise
        except (DomainError, OSError) as failure:
            manifest = ManifestOutcome.FAILED
            manifest_error = f"{error_code_of(failure)}: {failure}"
        return SnapshotOutcome(
            caselist=plan.caselist,
            snapshot=plan.snapshot,
            manifest_key=plan.manifest_key,
            sources=tuple(sources),
            manifest=manifest,
            manifest_error=manifest_error,
        )

    async def _publish_source(
        self, planned: PlannedSource, confirmed: set[ObjectKey], failed: dict[ObjectKey, SourceOutcome]
    ) -> SourceOutcome:
        if planned.action is SourceAction.SUPPRESSED:
            return _outcome(planned, SourceResult.SUPPRESSED)
        if planned.action is SourceAction.MISSING_LOCALLY:
            return self._failed(planned, failed, "MISSING_LOCALLY", "not in this machine's blob store")
        if planned.action is SourceAction.MISMATCHED:
            return self._failed(
                planned,
                failed,
                "CHECKSUM_MISMATCH",
                f"{planned.key} is listed at {planned.remote_size} bytes, not {planned.size}; "
                "the key names other bytes and was left untouched",
            )
        if planned.action is SourceAction.UPLOADED_EARLIER:
            if planned.key in confirmed:
                return _outcome(planned, SourceResult.SKIPPED)
            earlier = failed.get(planned.key)
            if earlier is not None:
                return _outcome(
                    planned,
                    SourceResult.FAILED,
                    earlier.error_code,
                    f"failed earlier in this run: {earlier.error_message}",
                )

        if planned.action is SourceAction.VERIFY and planned.key in confirmed:
            # Listed in the bucket and already confirmed for an earlier snapshot of this run.
            return _outcome(planned, SourceResult.SKIPPED)
        try:
            if planned.action is SourceAction.VERIFY:
                try:
                    present = await self._remote.head(planned.key)
                except NotFound:
                    # Listed a moment ago and gone now: absent, so uploaded like any other.
                    present = None
                if present is not None:
                    problem = _presence_problem(planned, present)
                    if problem is not None:
                        return self._failed(planned, failed, "CHECKSUM_MISMATCH", problem)
                    confirmed.add(planned.key)
                    return _outcome(planned, SourceResult.SKIPPED)
            await self._upload(planned)
        except (StoreCredentialsExpired, StoreAccessDenied):
            raise
        except (DomainError, OSError) as failure:
            return self._failed(planned, failed, error_code_of(failure), str(failure))
        confirmed.add(planned.key)
        return _outcome(planned, SourceResult.UPLOADED)

    async def _upload(self, planned: PlannedSource) -> None:
        """Upload one blob and confirm, from the bucket's own head, that it holds those bytes."""
        blob_key = local_blob_key(planned.sha256)
        local = await self._local.blobs.head(blob_key)
        if local.sha256 is not None and local.sha256 != planned.sha256:
            # The local copy no longer matches its own key. Publishing it would file other bytes
            # under this digest in the system of record.
            raise BlobIntegrityError(blob_key, local.sha256)
        async with local_file(self._local.blobs, self._local.blob_path_for, blob_key) as path:
            sent = await self._remote.put_file(planned.key, path)
        if sent.sha256 != planned.sha256:
            raise BlobIntegrityError(planned.key, sent.sha256)
        recorded = (await self._remote.head(planned.key)).sha256
        if recorded != planned.sha256:
            raise BlobIntegrityError(planned.key, recorded)

    async def _publish_manifest(self, plan: SnapshotPlan) -> ManifestOutcome:
        """Upload the manifest unless the bucket already holds these bytes, then confirm it."""
        local = await self._local.objects.head(plan.manifest_key)
        if local.sha256 is None:  # pragma: no cover - a local store always states its digest
            raise BlobIntegrityError(plan.manifest_key)
        try:
            remote = await self._remote.head(plan.manifest_key)
        except NotFound:
            remote = None
        if remote is not None and remote.sha256 == local.sha256:
            return ManifestOutcome.SKIPPED
        async with local_file(self._local.objects, self._local.object_path_for, plan.manifest_key) as path:
            sent = await self._remote.put_file(plan.manifest_key, path)
        recorded = (await self._remote.head(plan.manifest_key)).sha256
        if sent.sha256 != local.sha256 or recorded != local.sha256:
            raise BlobIntegrityError(plan.manifest_key, recorded)
        return ManifestOutcome.UPLOADED

    @staticmethod
    def _failed(
        planned: PlannedSource, failed: dict[ObjectKey, SourceOutcome], code: str, message: str
    ) -> SourceOutcome:
        outcome = _outcome(planned, SourceResult.FAILED, code, message)
        failed[planned.key] = outcome
        return outcome


# ------------------------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------------------------


def _presence_problem(planned: PlannedSource, present: ObjectInfo) -> str | None:
    """Why a source already in the bucket cannot be confirmed, or `None` when it is confirmed.

    Confirmed means the bucket recorded this key's own digest at this size. An object with no
    recorded digest is not confirmed: something other than these adapters put it there, and it
    cannot be vouched for without reading it back, so a person looks at it.
    """
    if present.sha256 is None:
        return f"{planned.key} holds no recorded SHA-256; it cannot be confirmed without reading it"
    if present.sha256 != planned.sha256 or present.size != planned.size:
        return f"{planned.key} holds bytes recorded as {present.sha256} ({present.size} bytes)"
    return None


def _outcome(
    planned: PlannedSource,
    result: SourceResult,
    error_code: str | None = None,
    error_message: str | None = None,
) -> SourceOutcome:
    return SourceOutcome(
        sha256=planned.sha256,
        key=planned.key,
        result=result,
        error_code=error_code,
        error_message=error_message,
    )


async def _bounded[ResultT](
    factories: Sequence[Callable[[], Awaitable[ResultT]]], *, limit: int
) -> list[ResultT]:
    """Run every factory's awaitable with at most `limit` in flight, results in input order.

    Factories rather than coroutines, so that an awaitable never started is never created: when
    one task raises — a refused credential, a process being stopped — the rest are cancelled and
    awaited before the exception continues, and nothing is left running behind the caller's back.
    """
    semaphore = asyncio.Semaphore(limit)

    async def guarded(factory: Callable[[], Awaitable[ResultT]]) -> ResultT:
        async with semaphore:
            return await factory()

    tasks = [asyncio.ensure_future(guarded(factory)) for factory in factories]
    try:
        return list(await asyncio.gather(*tasks))
    except BaseException:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise


def error_code_of(failure: BaseException) -> str:
    """`BlobIntegrityError` -> `BLOB_INTEGRITY_ERROR`, matching the CLI's `--json` error codes."""
    name = type(failure).__name__
    return "".join(
        f"_{letter}" if letter.isupper() and index else letter for index, letter in enumerate(name)
    ).upper()


def _log_snapshot(outcome: SnapshotOutcome) -> None:
    """One line per snapshot: counts, the caselist and the date, and failed digests. Nothing else."""
    logger.info(
        "caselist publish %s %s: %d uploaded, %d skipped, %d suppressed, %d failed; manifest %s",
        outcome.caselist,
        outcome.snapshot,
        len(outcome.of(SourceResult.UPLOADED)),
        len(outcome.of(SourceResult.SKIPPED)),
        len(outcome.of(SourceResult.SUPPRESSED)),
        len(outcome.failed),
        outcome.manifest.value,
    )
    if outcome.failed:
        logger.warning(
            "caselist publish %s %s: manifest withheld; failed sha256 %s",
            outcome.caselist,
            outcome.snapshot,
            ", ".join(sorted(failure.sha256 for failure in outcome.failed)),
        )

"""Publishing the parsed card store to the evidence bucket, per-source files first, aggregates last.

`caselist parse --publish` (`v1-e31-t06`) copies one caselist's current version directory from
`<data_dir>/parsed/<caselist>/<version>/` to `parsed/<caselist>/<version>/` in the bucket for
`DEBATE_ENV`, through the :class:`~debate_core.application.ports.evidence_store.EvidenceObjectStore`
port, so S3 holds what the V2 debate tub indexes. It follows `caselist publish`
(:mod:`debate_core.application.caselist.publish_service`) in what it checks and what it reports,
and reuses its result vocabulary, so the two summaries read alike.

## Idempotent

A listing states no digests, so an object the bucket already lists is headed, and skipped only when
the SHA-256 the bucket recorded for it equals the local file's. A re-run over an unchanged store
therefore uploads nothing. An upload is confirmed by heading the object again and comparing the
recorded digest with the file's.

## Aggregates last

The per-source files go first. `index.jsonl`, `failures.jsonl` and `occurrences.jsonl`, and the camp
store's `camp_paths.jsonl` (`v1-e33-t07`), follow only when every per-source file is confirmed in
the bucket, so the bucket never holds an index naming a file it does not hold. An aggregate the
bucket holds with other bytes is replaced: it is rebuilt by every run. A per-source file the bucket
holds with other bytes is a failure and is left alone, as
`caselist publish` leaves a mismatched source: within one parser and profile version the same
bytes always parse to the same file, so a difference means something a person should look at.

## What is never sent

A per-source file whose source the removal suppression list stops (`v1-e30-t07`). The list is a
required argument. Only the version directory asked for is published, and the command only ever
asks for the current one, so an older version in the bucket is never overwritten.

Nor the per-source file of a held upload (`v1-e31-t26`): bytes that only a path a removal holds
discloses, in a snapshot the hold covers, which a build from before `v1-e30-t13` imported and parsed.
Which sources those are is asked of this machine's manifests through the parse pipeline's own rule
(:func:`~debate_core.application.caselist.parse_sources.held_only_sources`), which asks the
publisher's rule for a held row of each disclosure, so `caselist publish` and this command hold back
the same bytes. Such a file is reported `suppressed`, like a suppressed source's: the hold is on the
list. Bytes another live path discloses are published as before. The manifests are read only when
the list holds a path.

Nor anything at all over an occurrence table stamped with a newer fingerprint version than this
build's (`v1-e34-t29`): the one it would send, or the bucket's it would replace. Before the first
upload the publish reads the stamps of both, downloading the bucket's only when its bytes differ,
and is refused with both versions named, leaving the bucket as it was
(:mod:`debate_core.application.caselist.occurrence_table_guard`).

## The plan (`v1-e31-t40`)

:meth:`ParsedStorePublisher.plan` is the publish with every write taken out, for `caselist parse
--publish-only --dry-run`. It reads the same suppression list and held uploads, asks the same
occurrence table guard before anything else, and compares each object with the bucket by the same
code the publish decides by (:func:`_action`). So it lists each object as the publish would treat
it: to upload, present with the same digest, suppressed, or blocked, a per-source file the bucket
holds with other bytes or one that could not be read. A blocked file withholds the aggregates in the
publish, so the plan then lists none of them. Each object carries its kind (a per-source file, an
aggregate, the placement state) and its bytes on this machine. It uploads nothing and writes
nothing on this machine: a newer occurrence table in the bucket is read into a temporary
directory, as the publish reads it.

## What is logged

Counts, the caselist, the version and keys. A key here is a caselist, a parser version and a
digest; the store holds no path or name to leak (`docs/data/parsed-card-store.md`).
"""

from __future__ import annotations

import logging
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final

from debate_core.application.caselist.evidence_listing import LocalEvidence, local_file
from debate_core.application.caselist.occurrence_table_guard import (
    THE_BUCKET,
    THIS_MACHINES_PARSED_STORE,
    fingerprint_stamps_of_file,
    refuse_newer_table,
)
from debate_core.application.caselist.parse_sources import enumerate_sources, held_only_sources
from debate_core.application.caselist.publish_service import (
    DEFAULT_CONCURRENCY,
    SourceResult,
    _bounded,  # pyright: ignore[reportPrivateUsage]
    error_code_of,
)
from debate_core.application.caselist.suppression import load_suppression_state
from debate_core.application.errors import (
    STORE_ERRORS_TRUE_OF_EVERY_OBJECT,
    UNMODELLED_ERROR_CODE,
    BlobIntegrityError,
    DomainError,
    NotFound,
    reported_error_message,
)
from debate_core.application.ports.evidence_store import EvidenceObjectStore, ObjectInfo, ObjectKey
from debate_core.application.ports.parsed_store import OCCURRENCES_NAME, PARSED_PREFIX, REBUILT_NAMES
from debate_core.application.ports.placement_state import PLACEMENT_STATE_NAME
from debate_core.application.ports.suppression import SuppressionList, SuppressionState

__all__ = [
    "ParsedObjectKind",
    "ParsedObjectOutcome",
    "ParsedPublishPlan",
    "ParsedPublishReport",
    "ParsedStorePublisher",
    "PlannedAction",
    "PlannedObject",
]

logger = logging.getLogger(__name__)

_SOURCE_SEGMENT: Final = "sha256"


@dataclass(frozen=True, slots=True)
class ParsedObjectOutcome:
    """What happened to one object. `error_*` are set only for :attr:`SourceResult.FAILED`."""

    key: ObjectKey
    """The bucket key: `parsed/<caselist>/<version>/…`."""
    result: SourceResult
    aggregate: bool
    error_code: str | None = None
    error_message: str | None = None
    """Why it failed, for a person. An error this project did not write is named by its class and an
    `OSError` by its errno too, never by its text, which can quote a path on this machine
    (:func:`~debate_core.application.errors.reported_error_message`, `v1-e29-t09`)."""


@dataclass(frozen=True, slots=True)
class ParsedPublishReport:
    """What publishing one version directory did, in the vocabulary of `caselist publish`."""

    caselist: str
    version: str
    prefix: str
    objects: tuple[ParsedObjectOutcome, ...]
    aggregates_withheld: bool

    def count(self, result: SourceResult) -> int:
        return sum(outcome.result is result for outcome in self.objects)

    @property
    def failed_keys(self) -> tuple[ObjectKey, ...]:
        return tuple(sorted(outcome.key for outcome in self.objects if outcome.result is SourceResult.FAILED))

    @property
    def succeeded(self) -> bool:
        """True when every object is confirmed in the bucket or suppressed, aggregates included."""
        return not self.aggregates_withheld and not self.failed_keys

    @property
    def failure_codes(self) -> tuple[str, ...]:
        """The error code of every object the bucket did not confirm, in key order; none when complete.

        The codes `caselist publish` reports its failures under, so `caselist parse --publish` and
        the parse stage of `caselist pull` decide from them as it does (`v1-e34-t17`): the publish
        is one a retry may cure only when every code here is. A failure with no code contributes
        :data:`~debate_core.application.errors.UNMODELLED_ERROR_CODE`, which is on no such list.
        Withheld aggregates add nothing of their own: they are withheld because a source failed.
        """
        failed = sorted(
            (outcome for outcome in self.objects if outcome.result is SourceResult.FAILED),
            key=lambda outcome: outcome.key,
        )
        return tuple(outcome.error_code or UNMODELLED_ERROR_CODE for outcome in failed)


class ParsedObjectKind(StrEnum):
    """What one object of a version directory is (`docs/data/parsed-card-store.md`)."""

    PER_SOURCE_FILES = "per_source_files"
    """`sha256/ab/cd/<digest>.jsonl`: one source's entry and its cards."""

    AGGREGATES = "aggregates"
    """`index.jsonl`, `failures.jsonl`, `occurrences.jsonl`, and `camp_paths.jsonl` in `openev`."""

    PLACEMENT_STATE = "placement_state"
    """`placement-state.sqlite` (`v1-e31-t10`), sent with the aggregates."""


class PlannedAction(StrEnum):
    """What the publish would do with one object: :class:`SourceResult`'s, before anything is sent."""

    UPLOAD = "upload"
    """Absent from the bucket, or an aggregate the bucket holds with other bytes: it would be sent."""

    PRESENT = "present"
    """In the bucket with the digest of the file here: it would be skipped."""

    SUPPRESSED = "suppressed"
    """A per-source file the target's suppression list stops or holds: it would never be sent."""

    BLOCKED = "blocked"
    """A per-source file the bucket holds with other bytes, or one that could not be read: the
    publish would fail it, and withhold the aggregates."""


@dataclass(frozen=True, slots=True)
class PlannedObject:
    """One object of the plan. `size` is its bytes on this machine; `error_code` is set only when
    :attr:`PlannedAction.BLOCKED`."""

    key: ObjectKey
    """The bucket key: `parsed/<caselist>/<version>/…`."""
    kind: ParsedObjectKind
    action: PlannedAction
    size: int
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class ParsedPublishPlan:
    """What publishing one version directory would do, with nothing sent (`v1-e31-t40`)."""

    caselist: str
    version: str
    prefix: str
    objects: tuple[PlannedObject, ...]
    aggregates_withheld: bool
    """A per-source file is blocked, so the publish would send no aggregate and no placement state;
    the plan then lists none."""

    def _of(self, action: PlannedAction, kind: ParsedObjectKind | None) -> list[PlannedObject]:
        return [one for one in self.objects if one.action is action and (kind is None or one.kind is kind)]

    def count(self, action: PlannedAction, kind: ParsedObjectKind | None = None) -> int:
        """How many objects, of `kind` or of every kind, the publish would treat as `action`."""
        return len(self._of(action, kind))

    def size(self, action: PlannedAction, kind: ParsedObjectKind | None = None) -> int:
        """Their bytes on this machine."""
        return sum(one.size for one in self._of(action, kind))

    @property
    def blocked_keys(self) -> tuple[ObjectKey, ...]:
        return tuple(sorted(one.key for one in self.objects if one.action is PlannedAction.BLOCKED))

    @property
    def blocked_codes(self) -> tuple[str, ...]:
        """The code of every blocked object, in key order, as :attr:`ParsedPublishReport.failure_codes`."""
        blocked = sorted(self._of(PlannedAction.BLOCKED, None), key=lambda one: one.key)
        return tuple(one.error_code or UNMODELLED_ERROR_CODE for one in blocked)


@dataclass(frozen=True, slots=True)
class _Directory:
    """What a publish and a plan both read before the first object: one version directory and the bucket."""

    prefix: str
    state: SuppressionState
    held: Mapping[str, str]
    listed: frozenset[ObjectKey]
    sources: tuple[ObjectKey, ...]
    aggregates: tuple[ObjectKey, ...]


def _kind(key: ObjectKey) -> ParsedObjectKind:
    """The kind of a local key `<caselist>/<version>/…`."""
    if key.split("/")[2:3] == [_SOURCE_SEGMENT]:
        return ParsedObjectKind.PER_SOURCE_FILES
    if key.rsplit("/", 1)[-1] == PLACEMENT_STATE_NAME:
        return ParsedObjectKind.PLACEMENT_STATE
    return ParsedObjectKind.AGGREGATES


def _action(local: ObjectInfo, present: ObjectInfo | None, *, aggregate: bool) -> PlannedAction:
    """The one decision the publish and the plan both make about an object the list does not stop.

    In the bucket with the same digest: present. A per-source file the bucket holds with other bytes:
    blocked, left alone. Anything else, an aggregate the bucket holds differently among it: upload.
    """
    if present is not None and present.sha256 == local.sha256:
        return PlannedAction.PRESENT
    if present is not None and not aggregate:
        return PlannedAction.BLOCKED
    return PlannedAction.UPLOAD


class ParsedStorePublisher:
    """Copies one version directory of the parsed card store to the environment's bucket.

    Args:
        local: The parsed store's tree as an object store, keyed `<caselist>/<version>/…`, i.e. an
            :class:`~debate_core.integrations.local.FsEvidenceObjectStore` rooted at
            `<data_dir>/parsed`.
        local_path_for: The file a local key is stored at, so it is uploaded in place.
        remote: The environment's evidence bucket.
        suppression: The removal suppression list. Required: nothing is published without it.
        evidence: This machine's manifests and blobs, whose rows say which sources only a held path
            discloses (`v1-e31-t26`). Required, like the list.
    """

    def __init__(
        self,
        *,
        local: EvidenceObjectStore,
        local_path_for: Callable[[ObjectKey], Path] | None,
        remote: EvidenceObjectStore,
        suppression: SuppressionList,
        evidence: LocalEvidence,
        concurrency: int = DEFAULT_CONCURRENCY,
    ) -> None:
        if concurrency < 1:
            raise ValueError("concurrency must be at least 1")
        self._local = local
        self._local_path_for = local_path_for
        self._remote = remote
        self._suppression = suppression
        self._evidence = evidence
        self._concurrency = concurrency

    async def publish(self, caselist: str, version: str) -> ParsedPublishReport:
        """Upload what the bucket lacks or holds differently, per-source files before aggregates."""
        found = await self._directory(caselist, version)
        outcomes = list(
            await _bounded(
                [lambda key=key: self._source(key, found) for key in found.sources],
                limit=self._concurrency,
            )
        )
        withheld = any(outcome.result is SourceResult.FAILED for outcome in outcomes)
        if not withheld:
            for key in found.aggregates:
                outcomes.append(
                    await self._object(key, f"{PARSED_PREFIX}/{key}", found.listed, aggregate=True)
                )
        report = ParsedPublishReport(
            caselist=caselist,
            version=version,
            prefix=found.prefix,
            objects=tuple(outcomes),
            aggregates_withheld=withheld,
        )
        _log(report)
        return report

    async def plan(self, caselist: str, version: str) -> ParsedPublishPlan:
        """What :meth:`publish` would do, object by object, with nothing uploaded or written.

        Raises what the publish raises before its first upload: the occurrence table guard's
        refusal, and a store error true of every object.
        """
        found = await self._directory(caselist, version)
        planned = list(
            await _bounded(
                [lambda key=key: self._planned_source(key, found) for key in found.sources],
                limit=self._concurrency,
            )
        )
        withheld = any(one.action is PlannedAction.BLOCKED for one in planned)
        if not withheld:
            for key in found.aggregates:
                planned.append(await self._planned(key, found.listed, aggregate=True))
        plan = ParsedPublishPlan(
            caselist=caselist,
            version=version,
            prefix=found.prefix,
            objects=tuple(planned),
            aggregates_withheld=withheld,
        )
        _log_plan(plan)
        return plan

    async def _directory(self, caselist: str, version: str) -> _Directory:
        """The list, the held uploads, both listings and the guard: everything before the first object."""
        directory = f"{caselist}/{version}/"
        prefix = f"{PARSED_PREFIX}/{directory}"
        state = await load_suppression_state(self._suppression)
        held = (
            held_only_sources(await enumerate_sources(self._evidence, caselist), state)
            if state.held_paths
            else {}
        )
        local_keys = [info.key for info in await self._local.list_objects(directory)]
        listed = frozenset(info.key for info in await self._remote.list_objects(prefix))
        await self._refuse_a_newer_table(caselist, version, local_keys, listed)
        return _Directory(
            prefix=prefix,
            state=state,
            held=held,
            listed=listed,
            sources=tuple(key for key in local_keys if _kind(key) is ParsedObjectKind.PER_SOURCE_FILES),
            aggregates=tuple(
                key for key in local_keys if key.rsplit("/", 1)[-1] in REBUILT_NAMES and key.count("/") == 2
            ),
        )

    async def _refuse_a_newer_table(
        self, caselist: str, version: str, local_keys: Sequence[ObjectKey], listed: frozenset[ObjectKey]
    ) -> None:
        """Ask :func:`~debate_core.application.caselist.occurrence_table_guard.refuse_newer_table`
        of the occurrence table this publish would send, and of the bucket's it would replace when
        the bucket holds other bytes, before anything is uploaded."""
        key = f"{caselist}/{version}/{OCCURRENCES_NAME}"
        if key not in local_keys:
            return
        async with local_file(self._local, self._local_path_for, key) as path:
            stamps = fingerprint_stamps_of_file(path)
        refuse_newer_table(stamps, caselist=caselist, version=version, store=THIS_MACHINES_PARSED_STORE)
        remote_key = f"{PARSED_PREFIX}/{key}"
        if remote_key not in listed:
            return
        try:
            present = await self._remote.head(remote_key)
        except NotFound:
            return
        if present.sha256 == (await self._local.head(key)).sha256:
            return
        with tempfile.TemporaryDirectory(prefix="debate-publish-") as directory:
            downloaded = Path(directory) / OCCURRENCES_NAME
            await self._remote.get_file(remote_key, downloaded)
            stamps = fingerprint_stamps_of_file(downloaded)
        refuse_newer_table(stamps, caselist=caselist, version=version, store=THE_BUCKET)

    @staticmethod
    def _stopped(key: ObjectKey, found: _Directory) -> bool:
        """Whether the list stops, or a hold holds, the source of the per-source file at `key`."""
        digest = key.rsplit("/", 1)[-1].split(".", 1)[0]
        return found.state.suppresses_source(digest) or digest in found.held

    async def _compared(
        self, key: ObjectKey, remote_key: ObjectKey, listed: frozenset[ObjectKey]
    ) -> tuple[ObjectInfo, ObjectInfo | None]:
        """The local object, and the bucket's under `remote_key` when the listing named one."""
        local = await self._local.head(key)
        if remote_key not in listed:
            return local, None
        try:
            return local, await self._remote.head(remote_key)
        except NotFound:
            return local, None

    async def _source(self, key: ObjectKey, found: _Directory) -> ParsedObjectOutcome:
        remote_key = f"{PARSED_PREFIX}/{key}"
        if self._stopped(key, found):
            return ParsedObjectOutcome(key=remote_key, result=SourceResult.SUPPRESSED, aggregate=False)
        return await self._object(key, remote_key, found.listed, aggregate=False)

    async def _planned_source(self, key: ObjectKey, found: _Directory) -> PlannedObject:
        if self._stopped(key, found):
            return PlannedObject(
                key=f"{PARSED_PREFIX}/{key}",
                kind=ParsedObjectKind.PER_SOURCE_FILES,
                action=PlannedAction.SUPPRESSED,
                size=(await self._local.head(key)).size,
            )
        return await self._planned(key, found.listed, aggregate=False)

    async def _planned(
        self, key: ObjectKey, listed: frozenset[ObjectKey], *, aggregate: bool
    ) -> PlannedObject:
        """:meth:`_object`'s decision about `key`, made and not carried out."""
        remote_key = f"{PARSED_PREFIX}/{key}"
        try:
            local, present = await self._compared(key, remote_key, listed)
        except STORE_ERRORS_TRUE_OF_EVERY_OBJECT:
            raise
        except (DomainError, OSError) as failure:
            return PlannedObject(
                key=remote_key,
                kind=_kind(key),
                action=PlannedAction.BLOCKED,
                size=0,
                error_code=error_code_of(failure),
            )
        action = _action(local, present, aggregate=aggregate)
        return PlannedObject(
            key=remote_key,
            kind=_kind(key),
            action=action,
            size=local.size,
            error_code="CHECKSUM_MISMATCH" if action is PlannedAction.BLOCKED else None,
        )

    async def _object(
        self, key: ObjectKey, remote_key: ObjectKey, listed: frozenset[ObjectKey], *, aggregate: bool
    ) -> ParsedObjectOutcome:
        try:
            local, present = await self._compared(key, remote_key, listed)
            action = _action(local, present, aggregate=aggregate)
            if action is PlannedAction.PRESENT:
                return ParsedObjectOutcome(key=remote_key, result=SourceResult.SKIPPED, aggregate=aggregate)
            if action is PlannedAction.BLOCKED and present is not None:
                return ParsedObjectOutcome(
                    key=remote_key,
                    result=SourceResult.FAILED,
                    aggregate=aggregate,
                    error_code="CHECKSUM_MISMATCH",
                    error_message=(
                        f"{remote_key} holds bytes recorded as {present.sha256}, not {local.sha256}; "
                        "left untouched"
                    ),
                )
            async with local_file(self._local, self._local_path_for, key) as path:
                sent = await self._remote.put_file(remote_key, path)
            recorded = (await self._remote.head(remote_key)).sha256
            if sent.sha256 != local.sha256 or recorded != local.sha256:
                raise BlobIntegrityError(remote_key, recorded)
        except STORE_ERRORS_TRUE_OF_EVERY_OBJECT:
            raise
        except (DomainError, OSError) as failure:
            return ParsedObjectOutcome(
                key=remote_key,
                result=SourceResult.FAILED,
                aggregate=aggregate,
                error_code=error_code_of(failure),
                error_message=reported_error_message(failure),
            )
        return ParsedObjectOutcome(key=remote_key, result=SourceResult.UPLOADED, aggregate=aggregate)


def _log_plan(plan: ParsedPublishPlan) -> None:
    logger.info(
        "caselist parse publish plan %s %s: %d to upload (%d bytes), %d present, %d suppressed, %d blocked; "
        "aggregates %s",
        plan.caselist,
        plan.version,
        plan.count(PlannedAction.UPLOAD),
        plan.size(PlannedAction.UPLOAD),
        plan.count(PlannedAction.PRESENT),
        plan.count(PlannedAction.SUPPRESSED),
        plan.count(PlannedAction.BLOCKED),
        "withheld" if plan.aggregates_withheld else "planned",
    )


def _log(report: ParsedPublishReport) -> None:
    logger.info(
        "caselist parse publish %s %s: %d uploaded, %d skipped, %d suppressed, %d failed; aggregates %s",
        report.caselist,
        report.version,
        report.count(SourceResult.UPLOADED),
        report.count(SourceResult.SKIPPED),
        report.count(SourceResult.SUPPRESSED),
        len(report.failed_keys),
        "withheld" if report.aggregates_withheld else "published",
    )
    if report.failed_keys:
        logger.warning(
            "caselist parse publish %s %s: failed %s",
            report.caselist,
            report.version,
            ", ".join(report.failed_keys),
        )

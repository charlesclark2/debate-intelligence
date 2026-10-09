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

The per-source files go first. `index.jsonl`, `failures.jsonl` and `occurrences.jsonl` follow only
when every per-source file is confirmed in the bucket, so the bucket never holds an index naming a
file it does not hold. An aggregate the bucket holds with other bytes is replaced: it is rebuilt by
every run. A per-source file the bucket holds with other bytes is a failure and is left alone, as
`caselist publish` leaves a mismatched source: within one parser and profile version the same
bytes always parse to the same file, so a difference means something a person should look at.

## What is never sent

A per-source file whose source the removal suppression list stops (`v1-e30-t07`). The list is a
required argument. Only the version directory asked for is published, and the command only ever
asks for the current one, so an older version in the bucket is never overwritten.

## What is logged

Counts, the caselist, the version and keys. A key here is a caselist, a parser version and a
digest; the store holds no path or name to leak (`docs/data/parsed-card-store.md`).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from debate_core.application.caselist.evidence_listing import local_file
from debate_core.application.caselist.publish_service import (
    DEFAULT_CONCURRENCY,
    SourceResult,
    _bounded,  # pyright: ignore[reportPrivateUsage]
    error_code_of,
)
from debate_core.application.caselist.suppression import load_suppression_state
from debate_core.application.errors import (
    BlobIntegrityError,
    DomainError,
    NotFound,
    StoreAccessDenied,
    StoreCredentialsExpired,
)
from debate_core.application.ports.evidence_store import EvidenceObjectStore, ObjectKey
from debate_core.application.ports.parsed_store import AGGREGATE_NAMES, PARSED_PREFIX
from debate_core.application.ports.suppression import SuppressionList, SuppressionState

__all__ = ["ParsedObjectOutcome", "ParsedPublishReport", "ParsedStorePublisher"]

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


class ParsedStorePublisher:
    """Copies one version directory of the parsed card store to the environment's bucket.

    Args:
        local: The parsed store's tree as an object store, keyed `<caselist>/<version>/…`, i.e. an
            :class:`~debate_core.integrations.local.FsEvidenceObjectStore` rooted at
            `<data_dir>/parsed`.
        local_path_for: The file a local key is stored at, so it is uploaded in place.
        remote: The environment's evidence bucket.
        suppression: The removal suppression list. Required: nothing is published without it.
    """

    def __init__(
        self,
        *,
        local: EvidenceObjectStore,
        local_path_for: Callable[[ObjectKey], Path] | None,
        remote: EvidenceObjectStore,
        suppression: SuppressionList,
        concurrency: int = DEFAULT_CONCURRENCY,
    ) -> None:
        if concurrency < 1:
            raise ValueError("concurrency must be at least 1")
        self._local = local
        self._local_path_for = local_path_for
        self._remote = remote
        self._suppression = suppression
        self._concurrency = concurrency

    async def publish(self, caselist: str, version: str) -> ParsedPublishReport:
        """Upload what the bucket lacks or holds differently, per-source files before aggregates."""
        directory = f"{caselist}/{version}/"
        prefix = f"{PARSED_PREFIX}/{directory}"
        state = await load_suppression_state(self._suppression)
        local_keys = [info.key for info in await self._local.list_objects(directory)]
        listed = {info.key for info in await self._remote.list_objects(prefix)}
        sources = [key for key in local_keys if key.split("/")[2:3] == [_SOURCE_SEGMENT]]
        aggregates = [
            key for key in local_keys if key.rsplit("/", 1)[-1] in AGGREGATE_NAMES and key.count("/") == 2
        ]

        outcomes = list(
            await _bounded(
                [lambda key=key: self._source(key, prefix, listed, state) for key in sources],
                limit=self._concurrency,
            )
        )
        withheld = any(outcome.result is SourceResult.FAILED for outcome in outcomes)
        if not withheld:
            for key in aggregates:
                outcomes.append(await self._object(key, f"{PARSED_PREFIX}/{key}", listed, aggregate=True))
        report = ParsedPublishReport(
            caselist=caselist,
            version=version,
            prefix=prefix,
            objects=tuple(outcomes),
            aggregates_withheld=withheld,
        )
        _log(report)
        return report

    async def _source(
        self, key: ObjectKey, prefix: str, listed: set[ObjectKey], state: SuppressionState
    ) -> ParsedObjectOutcome:
        remote_key = f"{PARSED_PREFIX}/{key}"
        digest = key.rsplit("/", 1)[-1].split(".", 1)[0]
        if state.suppresses_source(digest):
            return ParsedObjectOutcome(key=remote_key, result=SourceResult.SUPPRESSED, aggregate=False)
        return await self._object(key, remote_key, listed, aggregate=False)

    async def _object(
        self, key: ObjectKey, remote_key: ObjectKey, listed: set[ObjectKey], *, aggregate: bool
    ) -> ParsedObjectOutcome:
        try:
            local = await self._local.head(key)
            if remote_key in listed:
                try:
                    present = await self._remote.head(remote_key)
                except NotFound:
                    present = None
                if present is not None and present.sha256 == local.sha256:
                    return ParsedObjectOutcome(
                        key=remote_key, result=SourceResult.SKIPPED, aggregate=aggregate
                    )
                if present is not None and not aggregate:
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
        except (StoreCredentialsExpired, StoreAccessDenied):
            raise
        except (DomainError, OSError) as failure:
            return ParsedObjectOutcome(
                key=remote_key,
                result=SourceResult.FAILED,
                aggregate=aggregate,
                error_code=error_code_of(failure),
                error_message=str(failure),
            )
        return ParsedObjectOutcome(key=remote_key, result=SourceResult.UPLOADED, aggregate=aggregate)


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

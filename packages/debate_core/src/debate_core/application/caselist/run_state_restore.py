"""A run's working copy, restored from the bucket into a directory of its own (`v1-e40-t06`, ADR-0020).

`debate-research caselist restore-run-state --into <directory>`, run by the operator on the Mac:

* for the cutover's comparison (`v1-e40-t06`'s ac1): the Mac restores the cloud run's working copy,
  then re-parses and rebuilds the index from it, offline, and compares (`ops/caselist_run/`);
* for a hand publish to prod until the pilot's promotion, from a copy restored under the dev lock
  (ADR-0020 (7)).

**What is restored** is what a `caselist pull` restores at its start
(:meth:`~debate_core.application.caselist.run_state.RunState.restore`): the run-state bundle, the
state files, the published index's manifest and the parsed store's current version directory of each
caselist named and `openev`, each checked against the SHA-256 its publisher recorded. Then the copy's
suppression list is reconciled with the bucket's, so that a parse or an index build in the copy
leaves out what the bucket's list stops. Raw sources are not restored unless asked for: a parse in
the copy fetches from `raw/` the ones it needs, as a cloud run's does.

**With sources** (`--with-sources`, `v1-e40-t10`), the restore then fetches, still under the lock and
into the same directory, the raw sources the restored manifests name, optionally only those of some
caselists and snapshots: what a hand publish to prod from the copy needs. Each is checked against its
digest, and a source missing from the bucket stops the command unless the copy's suppression list,
just reconciled, holds it. :mod:`debate_core.application.caselist.run_state_sources` is that rule.

**Under the lock.** A run saves its state at several moments: the download ledger before each
download, the bundle after its publish stage and again at its end, the run log at its end. A copy
taken between two of them would mix two states. So the restore holds the bucket's run lock, taken
the way every command that writes a bucket takes it, and no runner is part-way through its week
while it reads. The lock object is the only thing it writes to
the bucket. Every other write goes to the named directory: :class:`RunStateRestore` is given a
:class:`RunState` and a suppression list over that directory, never over this environment's own.

**The directory** must be new or empty, and must be neither this environment's data directory nor
inside it nor holding it. A copy restored over another store would mix the two, and its newest
parsed generation, which a later parse or publish reads, could be the other store's.

**The marker** (`v1-e40-t21`). The restore's first write to the directory is
:data:`RESTORED_COPY_MARKER` at its root: the environment, the bucket, the time of the restore and the
build's tag, never a caselist, a school or a path. The annual purge and the landscape runbook find a
leftover copy by it at any depth. It is written whole or not at all, before anything is restored, so a
restore that stops part-way, a source missing or no room for the sources among the reasons, leaves it
beside what it restored. A refusal before the lock is taken, or by the lock, writes no directory at
all. The data directory is refused, so it never holds one.

**What is logged** is counts. The directory is the operator's own path, and never logged.
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from debate_core.application.caselist.run_state import RestoreReport, RunState
from debate_core.application.caselist.run_state_sources import (
    RestoredSources,
    SourceSelection,
    SourcesFetched,
    SourcesPlan,
)
from debate_core.application.caselist.suppression import RecordedSuppressionList, load_suppression_state
from debate_core.application.errors import DomainError

__all__ = [
    "RESTORED_COPY_MARKER",
    "RESTORE_COMMAND",
    "RestoreTargetRefused",
    "RestoredCopy",
    "RestoredCopyMarker",
    "RunStateRestore",
    "restore_target_refusal",
]

RESTORE_COMMAND: Final = "caselist restore-run-state"
"""The command the lock's holder names while the restore holds it."""

RESTORED_COPY_MARKER: Final = "debate-research-restored-copy.json"
"""The file at the root of every copy a restore makes, saying the directory is a restored copy (`v1-e40-t21`).

No file of a data directory is named after the tool, so the name cannot collide with one. The annual
purge's step 1 and the landscape runbook's last step find leftover copies by it, at any depth.
"""


class RestoreTargetRefused(DomainError):
    """The directory named is one a restore must not write into. Nothing was taken or written."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"nothing was restored: {reason}")


def restore_target_refusal(target: Path, *, live_data_dir: Path) -> str | None:
    """Why a copy may not be restored into `target`, or `None` when it may. Reads, never writes.

    Both paths are compared resolved, so a symbolic link to the data directory is the data
    directory.
    """
    resolved = target.expanduser().resolve()
    live = live_data_dir.expanduser().resolve()
    if resolved == live:
        return "the directory named is this environment's own data directory; name a new, empty one"
    if live in resolved.parents:
        return "the directory named is inside this environment's own data directory; name one outside it"
    if resolved in live.parents:
        return "the directory named holds this environment's own data directory; name a new, empty one"
    if resolved.exists() and not resolved.is_dir():
        return "the path named is not a directory"
    if resolved.is_dir() and any(resolved.iterdir()):
        return (
            "the directory named is not empty, and a copy restored over another store would mix the two; "
            "name a new, empty one"
        )
    return None


@dataclass(frozen=True, slots=True)
class RestoredCopy:
    """What a restore put into its directory. Counts and ids only."""

    report: RestoreReport
    manifests: int
    suppression_entries: int
    sources: SourcesFetched | None = None
    """The raw sources fetched with `--with-sources`; `None` without it."""


@dataclass(frozen=True, slots=True)
class RestoredCopyMarker:
    """What the marker says: where the copy came from, when, and by which build. Never a name or a path."""

    environment: str
    bucket: str
    restored_at: datetime
    build_tag: str | None
    """The release tag of the build that restored the copy; `None` from a source checkout."""

    def as_json(self) -> str:
        return json.dumps(
            {
                "environment": self.environment,
                "bucket": self.bucket,
                "restored_at": self.restored_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "build_tag": self.build_tag,
            },
            indent=2,
        )


class RunStateRestore:
    """The restore into a named directory. See the module docstring.

    Args:
        state_in: The run's state in the bucket, over a given data directory.
        suppression_in: The suppression list over a given data directory's copy and the bucket's.
        sources_in: The raw sources of a copy restored into a given directory (`--with-sources`).
        live_data_dir: This environment's own data directory, which is refused.
        parsed_version: The parsed store's version directory this build reads.
        environment: This environment's name, for the marker.
        bucket: The bucket restored from, for the marker.
        build_tag: This build's release tag, for the marker; `None` from a source checkout.
        clock: Now, in UTC: the marker's time of the restore.
    """

    def __init__(
        self,
        *,
        state_in: Callable[[Path], RunState],
        suppression_in: Callable[[Path], RecordedSuppressionList],
        sources_in: Callable[[Path], RestoredSources],
        live_data_dir: Path,
        parsed_version: str,
        environment: str,
        bucket: str,
        build_tag: str | None,
        clock: Callable[[], datetime],
    ) -> None:
        self._state_in = state_in
        self._suppression_in = suppression_in
        self._sources_in = sources_in
        self._live_data_dir = Path(live_data_dir)
        self._parsed_version = parsed_version
        self._environment = environment
        self._bucket = bucket
        self._build_tag = build_tag
        self._clock = clock

    def refusal(self, target: Path) -> str | None:
        """Why `target` is refused, or `None`: see :func:`restore_target_refusal`."""
        return restore_target_refusal(target, live_data_dir=self._live_data_dir)

    async def restore(
        self,
        target: Path,
        caselists: Sequence[str],
        *,
        sources: SourceSelection | None = None,
        on_sources_planned: Callable[[SourcesPlan], None] | None = None,
    ) -> RestoredCopy:
        """Restore the working copy into `target`. Call it holding the bucket's run lock.

        With `sources`, then fetch the raw sources the selected manifests name, calling
        `on_sources_planned` with the counts and bytes before the first fetch.

        Raises :class:`RestoreTargetRefused` before anything is written, and otherwise what
        :meth:`RunState.restore` and, with `sources`,
        :class:`~debate_core.application.caselist.run_state_sources.RestoredSources` raise.
        """
        refusal = self.refusal(target)
        if refusal is not None:
            raise RestoreTargetRefused(refusal)
        directory = target.expanduser().resolve()
        directory.mkdir(parents=True, exist_ok=True)
        self._mark(directory)
        state = self._state_in(directory)
        report = await state.restore(caselists, parsed_version=self._parsed_version)
        # The copy's own list starts empty, so reconciling writes only the copy: the bucket's holds
        # everything the copy's does.
        suppression = self._suppression_in(directory)
        await suppression.reconcile()
        fetched = None
        if sources is not None:
            restored_sources = self._sources_in(directory)
            plan = await restored_sources.plan(sources, await load_suppression_state(suppression))
            if on_sources_planned is not None:
                on_sources_planned(plan)
            restored_sources.refuse_too_little_room(plan)
            fetched = await restored_sources.fetch(plan)
        return RestoredCopy(
            report=report,
            manifests=len(await state.local_manifests()),
            suppression_entries=len(await suppression.entries()),
            sources=fetched,
        )

    def _mark(self, directory: Path) -> None:
        """Write :data:`RESTORED_COPY_MARKER` before anything is restored, so a stop leaves it too.

        It lands as the restore's other files do, written in a scratch directory inside the copy and
        moved into place: the copy holds the whole marker or none.
        """
        marker = RestoredCopyMarker(
            environment=self._environment,
            bucket=self._bucket,
            restored_at=self._clock(),
            build_tag=self._build_tag,
        )
        with tempfile.TemporaryDirectory(dir=directory, prefix=".restored-copy-marker-") as scratch:
            landed = Path(scratch) / RESTORED_COPY_MARKER
            landed.write_text(marker.as_json() + "\n", encoding="utf-8")
            landed.replace(directory / RESTORED_COPY_MARKER)

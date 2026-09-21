"""Moving evidence between the local store and the environment's bucket, and knowing what moved.

`debate-research store sync` is a thin command over this module (`v1-e29-t05-evidence-sync-cli`).
Everything that decides anything lives here: which objects differ, which of them may be written,
what is verified after a transfer, and what a re-run after an interruption is allowed to skip.

## Two keyspaces, because the local store is two directories

The bucket is one namespace. The local evidence directory is two, and they hold different kinds of
thing (`debate_core.integrations.local`):

::

    <data_dir>/objects/manifests/hsld26/2026-09-15.jsonl  <->  manifests/hsld26/2026-09-15.jsonl
    <data_dir>/blobs/sha256/ab/cd/abcd…def0               <->  raw/caselist/hsld26/sha256/ab/cd/abcd…def0

So a sync is not one key-for-key diff but one per :class:`SyncKeyspace`: a local store, a remote
store, and the prefix that the remote side adds to every key. Named objects add nothing and are
key-identical; content-addressed blobs are key-identical *after* the prefix that says which corpus
they belong to, which is why that prefix is an input to the run rather than a constant in here
(`docs/architecture/evidence-store-layout.md`).

## What the two kinds of object are allowed to do

| | named object | content-addressed blob |
|---|---|---|
| | `manifests/`, `reports/`, `files/` | `…/sha256/…` |
| Absent at the destination | `new`, transferred | `new`, transferred |
| Present, same content | `skipped` | `skipped` |
| Present, different content | `changed`, overwritten | **never**: `mismatched`, run fails |
| Only at the destination | `would_delete`, left alone | `would_delete`, left alone |

The second column is the evidence chain, not a safety margin. A key that is the SHA-256 of its own
bytes cannot legitimately hold different bytes, so a destination object of a different size under
that key means something already went wrong, and writing over it would destroy the evidence that it
did (:class:`~debate_core.application.ports.persistence.SnapshotStore`, architecture proposal §8).
A `changed` blob is therefore not a thing this module can produce.

`would_delete` is reported and never acted on. V1's sync does not delete, the everyday SSO profiles
cannot delete, and removing evidence is an operator procedure with its own credential
(`docs/runbooks/caselist-removal.md`, `v1-e30-t07`). Counting what a deleting sync *would* remove is
still worth doing: it is how an operator notices that the bucket holds a corpus their laptop does
not.

## How few HeadObject calls this makes

`list_objects` states no digest, by design, in either implementation — S3's `ListObjectsV2` does not
return one, and a listing that promised digests would cost one `HeadObject` per key
(:mod:`debate_core.application.ports.evidence_store`). So the planner heads only what it must, and
the order of the cheap checks is the whole cost model:

1. **A blob present on both sides is skipped with no head at all.** Its key is its digest.
2. **A named object whose sizes differ is `changed` with no head.** Different sizes, different bytes.
3. **A named object the journal already recorded at this digest is skipped with no remote head.**
4. Only what is left — a named object present on both sides, at the same size, not journaled — costs
   one `HeadObject`.

For the corpus this was built for that means a first sync heads nothing (everything is new), and a
repeat sync of an unchanged store heads nothing either (everything is journaled). The heads are paid
for exactly by manifests and reports that were rewritten since the last run, which is a handful.

## Resuming

:class:`SyncJournal` is an append-only JSONL file per environment recording every transfer that
completed *and verified*. A run appends a line and flushes it before moving to the next object, so a
sync killed halfway leaves a journal that is accurate about everything it claims.

The journal never on its own decides that an object does not need transferring. An object is skipped
only when it is *both* present at the destination in this run's listing and journaled at the digest
this run would send. That ordering matters: a journal is a record of what this machine did, and a
bucket someone has since emptied must still re-fill, so the listing is the authority on presence and
the journal is only allowed to make the digest check free.

## Failures

A transfer that fails marks that object `failed` and the run continues, because 2,300 objects should
not be abandoned over one of them; the report carries every failure and the command exits non-zero.
The two exceptions are :class:`~debate_core.application.errors.StoreCredentialsExpired` and
:class:`~debate_core.application.errors.StoreAccessDenied`, which end the run immediately: they will
be true of every remaining object, and 2,300 copies of "your SSO session expired" is not a report.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from debate_core.application.errors import (
    BlobIntegrityError,
    DomainError,
    NotFound,
    StoreAccessDenied,
    StoreCredentialsExpired,
)
from debate_core.application.ports.evidence_store import (
    EvidenceObjectStore,
    ObjectInfo,
    ObjectKey,
    validate_object_key,
)
from debate_core.application.ports.providers import Clock
from debate_core.domain import Sha256Hex

__all__ = [
    "BLOB_KEY_SEGMENT",
    "EVIDENCE_PREFIXES",
    "JOURNAL_DIRECTORY",
    "EvidenceSyncService",
    "JournalEntry",
    "PlannedObject",
    "SyncAction",
    "SyncDirection",
    "SyncJournal",
    "SyncKeyspace",
    "SyncPlan",
    "SyncReport",
    "TransferOutcome",
    "UnsyncableKeyspace",
]

EVIDENCE_PREFIXES: tuple[str, ...] = (
    "raw/",
    "parsed/",
    "files/",
    "manifests/",
    "reports/",
    "uploads/",
    "exports/",
    "quarantine/",
)
"""The bucket's documented top-level prefixes, in the order `evidence-store-layout.md` lists them.

The same list as `local.evidence_prefixes` in `infrastructure/modules/evidence_bucket/main.tf`, and
it is here for a reason that is not tidiness: that list is what the `EvidenceOperator` permission
set may call `ListBucket` on, **one prefix at a time**, so listing the bucket *root* is denied. A
planner that asked for every key under `""` would get `AccessDenied` against the real bucket while
passing every test against moto, which grants everything. So an unfiltered run lists these eight in
turn, and an object whose key is under none of them is reported and not transferred.
"""

BLOB_KEY_SEGMENT = "sha256/"
"""The segment that marks the content-addressed part of a key, as both stores build it.

`<prefix>/sha256/<ab>/<cd>/<digest>` in the bucket, `blobs/sha256/<ab>/<cd>/<digest>` on disk. A
:class:`SyncKeyspace` is told whether it is content-addressed rather than sniffing for this, but the
constant is what :meth:`SyncKeyspace.digest_of_key` reads a digest back out of a key with.
"""

JOURNAL_DIRECTORY = Path("sync-journal")
"""Where the journals live inside the data directory: `<data_dir>/sync-journal/<env>.jsonl`.

A sibling of `objects/` and `blobs/` rather than a file inside either, so that the record of a sync
can never be mistaken for something the sync is supposed to move.
"""


class SyncDirection(StrEnum):
    """Which way evidence is moving."""

    PUSH = "push"
    """Local store to bucket. What publishing evidence is."""

    PULL = "pull"
    """Bucket to local store. What a second machine joining the team does."""

    @property
    def opposite(self) -> SyncDirection:
        return SyncDirection.PULL if self is SyncDirection.PUSH else SyncDirection.PUSH


class SyncAction(StrEnum):
    """What a sync decided about one object. The table in this module's docstring is the rule."""

    NEW = "new"
    """Absent at the destination; will be transferred."""

    CHANGED = "changed"
    """Present at the destination with different bytes; will be overwritten. Named objects only."""

    SKIPPED = "skipped"
    """Present at the destination and identical, or outside the documented prefixes."""

    WOULD_DELETE = "would_delete"
    """At the destination and not at the source. Reported; V1 never deletes."""

    MISMATCHED = "mismatched"
    """A content-addressed key whose two sides differ. Never written over; fails the run."""


class UnsyncableKeyspace(DomainError):
    """A keyspace was asked to sync something it has no mapping for.

    Raised when the local blob tree holds objects and no remote prefix was given for them: a blob's
    prefix says which corpus it belongs to (`raw/caselist/hsld26`, `raw/openev/2026`), and only the
    caller knows that. Guessing would file a season's disclosures under the wrong archive.
    """


# ------------------------------------------------------------------------------------------------
# What a sync is between
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SyncKeyspace:
    """One local store and one remote store holding the same objects under related keys.

    A run has one of these per local tree. The mapping is a prefix and nothing else: the local key
    `sha256/ab/cd/abcd…` is the remote key `raw/caselist/hsld26/sha256/ab/cd/abcd…`, and a named
    object's local key `manifests/hsld26/2026-09-15.jsonl` is that key in the bucket too
    (:attr:`remote_prefix` empty).

    Args:
        name: What this keyspace is, for the summary and the journal: `objects`, `blobs`.
        local: The store on this machine.
        remote: The store in the bucket.
        remote_prefix: What the remote side adds in front of every local key. Normalised to end in
            `/` unless it is empty.
        content_addressed: True when a key states the digest of its own bytes, which is what makes
            a diff a key-set comparison and makes an overwrite a refusal.
        local_path_for: Optional. Given a local key, the file that key is stored at, so a transfer
            can stream the real file instead of staging a copy of it. The filesystem store's
            `path_for` is what this is; a store that cannot answer leaves it `None` and transfers
            are staged through a temporary file instead.
    """

    name: str
    local: EvidenceObjectStore
    remote: EvidenceObjectStore
    remote_prefix: str = ""
    content_addressed: bool = False
    local_path_for: Callable[[ObjectKey], Path] | None = None

    def __post_init__(self) -> None:
        if self.remote_prefix and not self.remote_prefix.endswith("/"):
            object.__setattr__(self, "remote_prefix", self.remote_prefix + "/")
        if self.remote_prefix:
            validate_object_key(self.remote_prefix.rstrip("/"))

    def remote_key(self, local_key: ObjectKey) -> ObjectKey:
        """The key `local_key` has in the bucket."""
        return f"{self.remote_prefix}{local_key}"

    def local_key(self, remote_key: ObjectKey) -> ObjectKey:
        """The key `remote_key` has on disk. Raises :class:`ValueError` for a key not in this space."""
        if not remote_key.startswith(self.remote_prefix):
            raise ValueError(f"{remote_key!r} is not in the {self.name} keyspace")
        return remote_key[len(self.remote_prefix) :]

    def holds(self, remote_key: ObjectKey) -> bool:
        """Whether `remote_key` belongs to this keyspace."""
        return remote_key.startswith(self.remote_prefix)

    def digest_of_key(self, local_key: ObjectKey) -> Sha256Hex | None:
        """The digest a content-addressed key states, or `None` when the key states none.

        `sha256/ab/cd/abcd…def0` is the digest `abcd…def0`. Read from the last segment rather than
        reassembled from the fan-out, because the fan-out repeats bytes the digest already has.
        """
        if not self.content_addressed:
            return None
        _, _, tail = local_key.partition(BLOB_KEY_SEGMENT)
        candidate = tail.rsplit("/", 1)[-1]
        return candidate if len(candidate) == 64 else None


# ------------------------------------------------------------------------------------------------
# The plan and the report
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PlannedObject:
    """One object and what the planner decided about it."""

    keyspace: str
    local_key: ObjectKey
    remote_key: ObjectKey
    action: SyncAction
    size: int
    """Bytes at the source, or at the destination for :attr:`SyncAction.WOULD_DELETE`."""
    reason: str
    """Short, stable English for why: `absent at the destination`, `journaled at this digest`."""
    sha256: Sha256Hex | None = None
    """The source digest, when the planner had to work it out. `None` when it did not need to."""

    @property
    def transfers(self) -> bool:
        """Whether executing the plan moves this object's bytes."""
        return self.action in (SyncAction.NEW, SyncAction.CHANGED)


@dataclass(frozen=True, slots=True)
class SyncPlan:
    """Everything a sync would do, before it does any of it.

    A `--dry-run` prints this and stops. An apply hands it to
    :meth:`EvidenceSyncService.execute`, which transfers exactly the objects in it and nothing the
    planner did not name.
    """

    direction: SyncDirection
    prefix: str
    """The remote prefix this run was filtered to; empty for the whole store."""
    objects: tuple[PlannedObject, ...]
    remote_head_requests: int = 0
    """`HeadObject` calls the planning itself made. The number this module works to keep small."""

    def of(self, *actions: SyncAction) -> tuple[PlannedObject, ...]:
        """Every planned object with one of these actions, in key order."""
        wanted = set(actions)
        return tuple(planned for planned in self.objects if planned.action in wanted)

    def count(self, action: SyncAction) -> int:
        return sum(1 for planned in self.objects if planned.action is action)

    def bytes_for(self, action: SyncAction) -> int:
        return sum(planned.size for planned in self.objects if planned.action is action)

    @property
    def transfers(self) -> tuple[PlannedObject, ...]:
        """What executing this plan would move, in key order."""
        return tuple(planned for planned in self.objects if planned.transfers)

    @property
    def bytes_to_transfer(self) -> int:
        return sum(planned.size for planned in self.transfers)

    @property
    def counts(self) -> dict[str, int]:
        """One count per action, always all five keys, for the summary and the `--json` payload."""
        return {action.value: self.count(action) for action in SyncAction}

    @property
    def byte_counts(self) -> dict[str, int]:
        return {action.value: self.bytes_for(action) for action in SyncAction}


@dataclass(frozen=True, slots=True)
class TransferOutcome:
    """What actually happened to one object the plan asked for."""

    planned: PlannedObject
    transferred: bool
    sha256: Sha256Hex | None = None
    """The digest that was verified at the destination, when the transfer succeeded."""
    error_code: str | None = None
    """The failure's class name in upper snake case, or `None`. Never a credential, never content."""
    error_message: str | None = None

    @property
    def key(self) -> ObjectKey:
        return self.planned.remote_key


@dataclass(frozen=True, slots=True)
class SyncReport:
    """What a sync did, as both the operator and a scheduled consumer need it."""

    plan: SyncPlan
    applied: bool
    """False for a dry run, where nothing was transferred and the plan is the whole report."""
    outcomes: tuple[TransferOutcome, ...] = ()
    journal_path: Path | None = None

    @property
    def transferred(self) -> tuple[TransferOutcome, ...]:
        return tuple(outcome for outcome in self.outcomes if outcome.transferred)

    @property
    def failed(self) -> tuple[TransferOutcome, ...]:
        return tuple(outcome for outcome in self.outcomes if not outcome.transferred)

    @property
    def bytes_transferred(self) -> int:
        return sum(outcome.planned.size for outcome in self.transferred)

    @property
    def succeeded(self) -> bool:
        """True when nothing failed and no content-addressed key was found mismatched.

        A mismatch is a failure of the run even in a dry run: the two stores disagree about bytes
        that are named by their own digest, and no amount of transferring fixes that.
        """
        return not self.failed and self.plan.count(SyncAction.MISMATCHED) == 0


# ------------------------------------------------------------------------------------------------
# The journal
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class JournalEntry:
    """One verified transfer, as one line of JSON.

    Deliberately small and deliberately not a key-value store: an append-only log of facts is the
    one shape that is still correct after the process is killed between two of them.
    """

    finished_at: str
    direction: SyncDirection
    keyspace: str
    key: ObjectKey
    """The *local* key, so a journal stays readable if the remote prefix of a run ever changes."""
    sha256: Sha256Hex
    size: int
    remote: str
    """What the other side was: the bucket name. Never a credential and never a profile."""

    def as_json(self) -> dict[str, str | int]:
        return {
            "finished_at": self.finished_at,
            "direction": self.direction.value,
            "keyspace": self.keyspace,
            "key": self.key,
            "sha256": self.sha256,
            "size": self.size,
            "remote": self.remote,
        }

    @classmethod
    def from_json(cls, row: Mapping[str, object]) -> JournalEntry | None:
        """Read one line back, or `None` if it is not a usable entry.

        A journal is a file on an operator's disk that a killed process was writing to. A truncated
        last line, or a line from a future version with a field this one does not know, is ordinary
        and is skipped: the cost of ignoring an entry is one object transferred again, and the cost
        of trusting a malformed one is an object that never is.
        """
        try:
            direction = SyncDirection(str(row["direction"]))
            return cls(
                finished_at=str(row["finished_at"]),
                direction=direction,
                keyspace=str(row["keyspace"]),
                key=str(row["key"]),
                sha256=str(row["sha256"]),
                size=int(row["size"]),  # pyright: ignore[reportArgumentType]
                remote=str(row["remote"]),
            )
        except (KeyError, TypeError, ValueError):
            return None


class SyncJournal:
    """The append-only record of what has already been transferred and verified, per environment.

    One file, `<data_dir>/sync-journal/<environment>.jsonl`, opened at the start of a run and
    appended to as objects land. Reading it is what makes an interrupted sync resume cheaply; see
    this module's docstring for why reading it is never on its own a reason to skip anything.

    Entries recorded against a different bucket are ignored on load rather than deleted, so that
    pointing dev's data directory at a second bucket does not silently inherit the first one's
    record — and so that switching back does not lose it.
    """

    def __init__(self, path: Path | None, *, remote: str) -> None:
        self._path = path
        self._remote = remote
        self._verified: dict[tuple[str, SyncDirection, ObjectKey], Sha256Hex] = {}
        self._entries = 0
        if path is not None and path.is_file():
            self._load(path)

    @classmethod
    def open(cls, data_dir: Path, *, environment: str, remote: str) -> SyncJournal:
        """The journal for one environment's data directory, loaded if it exists."""
        return cls(Path(data_dir) / JOURNAL_DIRECTORY / f"{environment}.jsonl", remote=remote)

    @classmethod
    def unwritten(cls, *, remote: str = "") -> SyncJournal:
        """A journal that remembers nothing and writes nothing: what a dry run uses."""
        return cls(None, remote=remote)

    @property
    def path(self) -> Path | None:
        """Where entries are appended, or `None` for an unwritten journal."""
        return self._path

    @property
    def entry_count(self) -> int:
        """How many usable entries for this bucket the journal held when it was opened."""
        return self._entries

    def verified_digest(self, *, keyspace: str, direction: SyncDirection, key: ObjectKey) -> Sha256Hex | None:
        """The digest this journal says was last transferred for `key`, or `None`."""
        return self._verified.get((keyspace, direction, key))

    def record(self, entry: JournalEntry) -> None:
        """Append one verified transfer and make sure it has reached the disk.

        Flushed and `fsync`ed per entry rather than per run. A journal is only worth having if it
        is accurate after the thing that made it stop was not a clean exit, and the cost — one
        small synchronous write per object — is nothing beside the transfer it follows.
        """
        self._verified[(entry.keyspace, entry.direction, entry.key)] = entry.sha256
        self._entries += 1
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry.as_json(), ensure_ascii=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    def _load(self, path: Path) -> None:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            entry = JournalEntry.from_json(row)  # pyright: ignore[reportUnknownArgumentType]
            if entry is None or entry.remote != self._remote:
                continue
            self._verified[(entry.keyspace, entry.direction, entry.key)] = entry.sha256
            self._entries += 1


# ------------------------------------------------------------------------------------------------
# The service
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Side:
    """One direction's source and destination, so the planner is written once rather than twice."""

    source: EvidenceObjectStore
    destination: EvidenceObjectStore
    source_key: Callable[[ObjectKey], ObjectKey]
    destination_key: Callable[[ObjectKey], ObjectKey]


class EvidenceSyncService:
    """Plans and executes a sync between the local evidence store and the environment's bucket.

    Built by the composition root with the keyspaces for this run and the journal for this
    environment; it reads no settings, resolves no environment and knows no bucket name
    (architecture proposal §6). `debate-research store` is the only caller in V1, and it does
    nothing this class does not do for it.

    ::

        service = EvidenceSyncService(
            keyspaces=(named_objects, blobs),
            journal=SyncJournal.open(data_dir, environment="dev", remote=bucket),
        )
        plan = await service.plan(prefix="manifests/", direction=SyncDirection.PUSH)
        report = await service.execute(plan)

    Args:
        keyspaces: The local/remote pairs this run covers, in the order a summary lists them.
        journal: Where verified transfers are recorded and read back from. A dry run is given
            :meth:`SyncJournal.unwritten`, which remembers nothing.
        remote_name: The bucket, for the journal's entries. Never a credential.
        clock: Supplies the journal's timestamps. Optional, and the only clock in this package that
            has a default: a journal timestamp is operational bookkeeping an operator reads, not
            provenance a card depends on. A test that asserts on journal contents injects
            :class:`~debate_core.testing.fakes.FixedClock`.
    """

    def __init__(
        self,
        *,
        keyspaces: Sequence[SyncKeyspace],
        journal: SyncJournal | None = None,
        remote_name: str = "",
        clock: Clock | None = None,
    ) -> None:
        if not keyspaces:
            raise ValueError("a sync needs at least one keyspace")
        self._keyspaces = tuple(keyspaces)
        self._journal = journal if journal is not None else SyncJournal.unwritten(remote=remote_name)
        self._remote_name = remote_name
        self._clock = clock

    @property
    def keyspaces(self) -> tuple[SyncKeyspace, ...]:
        return self._keyspaces

    @property
    def journal(self) -> SyncJournal:
        return self._journal

    # --------------------------------------------------------------------------------------
    # Planning
    # --------------------------------------------------------------------------------------

    async def plan(self, *, prefix: str = "", direction: SyncDirection = SyncDirection.PUSH) -> SyncPlan:
        """Work out what this sync would do, without transferring anything.

        `prefix` filters by *remote* key, which is the key an operator reads in a runbook and in
        the console: `manifests/hsld26/` means those manifests whichever local directory they are
        in. An empty prefix means the whole store, which is listed as the eight documented prefixes
        in turn rather than as the bucket root — see :data:`EVIDENCE_PREFIXES`.

        Raises :class:`UnsyncableKeyspace` when a keyspace has local objects and no remote prefix
        to put them under.
        """
        planned: list[PlannedObject] = []
        heads = 0
        for keyspace in self._keyspaces:
            objects, keyspace_heads = await self._plan_keyspace(keyspace, prefix, direction)
            planned.extend(objects)
            heads += keyspace_heads
        planned.sort(key=lambda entry: (entry.keyspace, entry.remote_key))
        return SyncPlan(
            direction=direction,
            prefix=prefix,
            objects=tuple(planned),
            remote_head_requests=heads,
        )

    async def _plan_keyspace(
        self, keyspace: SyncKeyspace, prefix: str, direction: SyncDirection
    ) -> tuple[list[PlannedObject], int]:
        local_filter = _local_filter_for(keyspace, prefix)
        if local_filter is None:
            return [], 0

        local = {info.key: info for info in await keyspace.local.list_objects(local_filter)}
        remote = {
            keyspace.local_key(info.key): info
            for info in await self._list_remote(keyspace, local_filter)
            if self._owner_of(info.key) is keyspace
        }
        self._refuse_unmapped_blobs(keyspace, local)

        side = _side_for(keyspace, direction)
        source = local if direction is SyncDirection.PUSH else remote
        destination = remote if direction is SyncDirection.PUSH else local

        planned: list[PlannedObject] = []
        heads = 0
        for key in sorted(source):
            entry, cost = await self._classify(keyspace, side, key, source[key], destination.get(key))
            planned.append(entry)
            heads += cost
        planned.extend(
            _planned(keyspace, key, SyncAction.WOULD_DELETE, destination[key].size, "absent at the source")
            for key in sorted(set(destination) - set(source))
        )
        return planned, heads

    async def _classify(
        self,
        keyspace: SyncKeyspace,
        side: _Side,
        key: ObjectKey,
        source: ObjectInfo,
        destination: ObjectInfo | None,
    ) -> tuple[PlannedObject, int]:
        """Decide one object's action, spending as few `HeadObject` calls as the answer allows."""
        remote_key = keyspace.remote_key(key)
        owner = self._owner_of(remote_key)
        if owner is not None and owner is not keyspace:
            # Two keyspaces can spell one bucket key — a blob filed under `objects/raw/…` on disk
            # would. The more specific prefix owns it, so this one reports it and moves nothing,
            # rather than both of them planning the same upload.
            return (
                _planned(
                    keyspace,
                    key,
                    SyncAction.SKIPPED,
                    source.size,
                    f"in the {owner.name} keyspace, not this one",
                ),
                0,
            )
        if not _is_documented_prefix(remote_key):
            return (
                _planned(
                    keyspace,
                    key,
                    SyncAction.SKIPPED,
                    source.size,
                    "not under a documented evidence prefix",
                ),
                0,
            )

        if destination is None:
            digest = keyspace.digest_of_key(key)
            return _planned(
                keyspace, key, SyncAction.NEW, source.size, "absent at the destination", digest
            ), 0

        if keyspace.content_addressed:
            # The key is the digest, so identical keys are identical bytes and no store is asked
            # anything. Different sizes under one digest means one side is damaged: it is reported
            # and never written over, whichever side is the source.
            if destination.size != source.size:
                return (
                    _planned(
                        keyspace,
                        key,
                        SyncAction.MISMATCHED,
                        source.size,
                        f"content-addressed key holds {destination.size} bytes at the destination, "
                        f"{source.size} at the source",
                        keyspace.digest_of_key(key),
                    ),
                    0,
                )
            return (
                _planned(
                    keyspace,
                    key,
                    SyncAction.SKIPPED,
                    source.size,
                    "already stored under this digest",
                    keyspace.digest_of_key(key),
                ),
                0,
            )

        if destination.size != source.size:
            return _planned(keyspace, key, SyncAction.CHANGED, source.size, "different size"), 0

        source_digest = (await side.source.head(side.source_key(key))).sha256
        journaled = self._journal.verified_digest(
            keyspace=keyspace.name, direction=_direction_of(side, keyspace), key=key
        )
        if source_digest is not None and journaled == source_digest:
            return (
                _planned(
                    keyspace, key, SyncAction.SKIPPED, source.size, "journaled at this digest", source_digest
                ),
                0,
            )

        destination_digest = (await side.destination.head(side.destination_key(key))).sha256
        heads = 1 if side.destination is keyspace.remote else 0
        if source_digest is not None and source_digest == destination_digest:
            return (
                _planned(keyspace, key, SyncAction.SKIPPED, source.size, "identical", source_digest),
                heads,
            )
        reason = "no digest recorded at the destination" if destination_digest is None else "different digest"
        return _planned(keyspace, key, SyncAction.CHANGED, source.size, reason, source_digest), heads

    async def _list_remote(self, keyspace: SyncKeyspace, local_filter: str) -> tuple[ObjectInfo, ...]:
        """List the remote side, never asking for the bucket root.

        A remote prefix that would be empty is expanded into the eight documented prefixes, because
        that is what the operator's `ListBucket` grant is scoped to (:data:`EVIDENCE_PREFIXES`).
        """
        remote_filter = keyspace.remote_key(local_filter)
        if remote_filter:
            return await keyspace.remote.list_objects(remote_filter)
        found: list[ObjectInfo] = []
        for documented in EVIDENCE_PREFIXES:
            found.extend(await keyspace.remote.list_objects(documented))
        return tuple(sorted(found, key=lambda info: info.key))

    def _refuse_unmapped_blobs(self, keyspace: SyncKeyspace, local: Mapping[ObjectKey, ObjectInfo]) -> None:
        if keyspace.content_addressed and not keyspace.remote_prefix and local:
            raise UnsyncableKeyspace(
                f"the {keyspace.name} keyspace holds {len(local)} object(s) and no remote prefix was "
                "given for them; a content-addressed key needs the prefix that says which corpus it "
                "belongs to, such as raw/caselist/hsld26 or raw/openev/2026 "
                "(docs/architecture/evidence-store-layout.md)"
            )

    # --------------------------------------------------------------------------------------
    # Execution
    # --------------------------------------------------------------------------------------

    async def execute(self, plan: SyncPlan) -> SyncReport:
        """Transfer exactly what `plan` named, verifying each object, and record what landed.

        Objects are transferred in the plan's order, which is by keyspace and then by key, so an
        interrupted run and its resume walk the store the same way and a half-finished sync is a
        prefix of a finished one.

        Every failure but an unusable credential is collected rather than raised: the report names
        each one and :attr:`SyncReport.succeeded` is what the command's exit code comes from.
        """
        by_name = {keyspace.name: keyspace for keyspace in self._keyspaces}
        outcomes: list[TransferOutcome] = []
        for planned in plan.transfers:
            keyspace = by_name[planned.keyspace]
            outcomes.append(await self._transfer(keyspace, planned, plan.direction))
        return SyncReport(
            plan=plan,
            applied=True,
            outcomes=tuple(outcomes),
            journal_path=self._journal.path,
        )

    async def _transfer(
        self, keyspace: SyncKeyspace, planned: PlannedObject, direction: SyncDirection
    ) -> TransferOutcome:
        try:
            digest = await self._move(keyspace, planned, direction)
        except (StoreCredentialsExpired, StoreAccessDenied):
            # True of every remaining object. Ending here is the difference between one line an
            # operator can act on and 2,300 copies of it.
            raise
        except (DomainError, OSError) as failure:
            return TransferOutcome(
                planned=planned,
                transferred=False,
                error_code=_error_code(failure),
                error_message=str(failure),
            )
        self._journal.record(
            JournalEntry(
                finished_at=self._now(),
                direction=direction,
                keyspace=keyspace.name,
                key=planned.local_key,
                sha256=digest,
                size=planned.size,
                remote=self._remote_name,
            )
        )
        return TransferOutcome(planned=planned, transferred=True, sha256=digest)

    async def _move(
        self, keyspace: SyncKeyspace, planned: PlannedObject, direction: SyncDirection
    ) -> Sha256Hex:
        """Move one object and return the digest that was verified at the destination."""
        if direction is SyncDirection.PUSH:
            return await self._push(keyspace, planned)
        return await self._pull(keyspace, planned)

    async def _push(self, keyspace: SyncKeyspace, planned: PlannedObject) -> Sha256Hex:
        """Upload one object, then confirm from the bucket's own head that it holds those bytes."""
        async with _readable_source(keyspace, planned.local_key) as source:
            stored = await keyspace.remote.put_file(planned.remote_key, source)
        uploaded = stored.sha256
        if uploaded is None:  # pragma: no cover - both adapters state the digest they just wrote
            raise BlobIntegrityError(planned.remote_key)
        self._refuse_unexpected_digest(keyspace, planned, uploaded)

        # Acceptance criterion 2: the upload is not believed until the store, asked separately,
        # says it holds those bytes. `put_file` returns what it sent; this is what arrived.
        recorded = (await keyspace.remote.head(planned.remote_key)).sha256
        if recorded is None or recorded != uploaded:
            raise BlobIntegrityError(planned.remote_key, recorded)
        return uploaded

    async def _pull(self, keyspace: SyncKeyspace, planned: PlannedObject) -> Sha256Hex:
        """Download one object, and let nothing into the local store that has not been checked.

        `get_file` already re-hashes what it downloaded and refuses to rename it into place when
        it disagrees with the digest the *store recorded* — which is the whole check for a named
        object, and only half of it for a content-addressed one. A blob's authority is the digest
        in its own key, and the remote store does not know that key means anything. So a blob is
        downloaded to a staging file, checked against its key, and only then put into the local
        tree; downloading it straight to its final path would put an object that is not what it
        claims to be into the evidence store and report the failure afterwards.
        """
        direct = keyspace.local_path_for
        if direct is not None and not keyspace.content_addressed:
            landed = await keyspace.remote.get_file(planned.remote_key, direct(planned.local_key))
            digest = _stated_digest(landed, planned.remote_key)
            self._refuse_unexpected_digest(keyspace, planned, digest)
            return digest
        with _staging_file(planned.local_key) as staged:
            landed = await keyspace.remote.get_file(planned.remote_key, staged)
            digest = _stated_digest(landed, planned.remote_key)
            self._refuse_unexpected_digest(keyspace, planned, digest)
            stored = await keyspace.local.put_file(planned.local_key, staged)
        if stored.sha256 is not None and stored.sha256 != digest:  # pragma: no cover - a disk fault
            raise BlobIntegrityError(planned.local_key, stored.sha256)
        return digest

    def _refuse_unexpected_digest(
        self, keyspace: SyncKeyspace, planned: PlannedObject, actual: Sha256Hex
    ) -> None:
        """A content-addressed object must hash to the digest its own key states."""
        expected = keyspace.digest_of_key(planned.local_key)
        if expected is not None and expected != actual:
            raise BlobIntegrityError(planned.remote_key, actual)

    def _now(self) -> str:
        moment = self._clock.now() if self._clock is not None else datetime.now(UTC)
        return moment.isoformat()

    # --------------------------------------------------------------------------------------
    # The two read-only commands
    # --------------------------------------------------------------------------------------

    async def list_remote(self, prefix: str = "") -> tuple[ObjectInfo, ...]:
        """Every object in the bucket under `prefix`, sorted by key, with no digests.

        An empty prefix lists the documented prefixes in turn rather than the bucket root, which
        the operator credential may not list. Duplicates are collapsed, because two keyspaces over
        one bucket can both see the same object.
        """
        seen: dict[ObjectKey, ObjectInfo] = {}
        walked: set[tuple[int, str]] = set()
        for keyspace in self._keyspaces:
            local_filter = _local_filter_for(keyspace, prefix)
            if local_filter is None:
                continue
            # Two keyspaces over one bucket with the same effective prefix would page the same
            # listing twice. Keyed by the store's identity as well as the prefix, because two
            # keyspaces are only asking the same question if they are asking the same store.
            walk = (id(keyspace.remote), keyspace.remote_key(local_filter))
            if walk in walked:
                continue
            walked.add(walk)
            for info in await self._list_remote(keyspace, local_filter):
                seen.setdefault(info.key, info)
        return tuple(sorted(seen.values(), key=lambda info: info.key))

    async def fetch(self, remote_key: ObjectKey, destination: Path | None = None) -> ObjectInfo:
        """Download one object by its bucket key, verifying it, and return what landed.

        With no `destination` the object goes into the local store at its mapped key, which is
        where a later `sync` would expect to find it. Raises
        :class:`~debate_core.application.errors.NotFound` when no keyspace can place the key, so
        that a mistyped prefix is a named failure rather than a download into the wrong tree.
        """
        validate_object_key(remote_key)
        keyspace = self._keyspace_for(remote_key)
        planned = _planned(
            keyspace,
            keyspace.local_key(remote_key),
            SyncAction.NEW,
            0,
            "requested by key",
            keyspace.digest_of_key(keyspace.local_key(remote_key)),
        )
        if destination is None:
            digest = await self._pull(keyspace, planned)
            return ObjectInfo(key=remote_key, size=0, sha256=digest)
        landed = await keyspace.remote.get_file(remote_key, destination)
        self._refuse_unexpected_digest(keyspace, planned, _stated_digest(landed, remote_key))
        return landed

    def _keyspace_for(self, remote_key: ObjectKey) -> SyncKeyspace:
        """The keyspace that owns `remote_key`, or :class:`NotFound` when none does."""
        owner = self._owner_of(remote_key)
        if owner is None:
            raise NotFound("evidence keyspace", remote_key)
        return owner

    def _owner_of(self, remote_key: ObjectKey) -> SyncKeyspace | None:
        """Which keyspace a bucket key belongs to: the one with the longest matching prefix.

        Prefixes can nest — the named-object keyspace adds nothing to a key and so matches
        everything, while the blob keyspace matches `raw/caselist/hsld26/…` — and exactly one of
        them has to own each key or the planner would count it twice.
        """
        candidates = [keyspace for keyspace in self._keyspaces if keyspace.holds(remote_key)]
        if not candidates:
            return None
        return max(candidates, key=lambda keyspace: len(keyspace.remote_prefix))


# ------------------------------------------------------------------------------------------------
# Module-private helpers
# ------------------------------------------------------------------------------------------------


def _planned(
    keyspace: SyncKeyspace,
    local_key: ObjectKey,
    action: SyncAction,
    size: int,
    reason: str,
    sha256: Sha256Hex | None = None,
) -> PlannedObject:
    return PlannedObject(
        keyspace=keyspace.name,
        local_key=local_key,
        remote_key=keyspace.remote_key(local_key),
        action=action,
        size=size,
        reason=reason,
        sha256=sha256,
    )


def _side_for(keyspace: SyncKeyspace, direction: SyncDirection) -> _Side:
    """Which store is read and which is written, and how a local key is spelled at each."""
    if direction is SyncDirection.PUSH:
        return _Side(
            source=keyspace.local,
            destination=keyspace.remote,
            source_key=lambda key: key,
            destination_key=keyspace.remote_key,
        )
    return _Side(
        source=keyspace.remote,
        destination=keyspace.local,
        source_key=keyspace.remote_key,
        destination_key=lambda key: key,
    )


def _direction_of(side: _Side, keyspace: SyncKeyspace) -> SyncDirection:
    return SyncDirection.PUSH if side.source is keyspace.local else SyncDirection.PULL


def _local_filter_for(keyspace: SyncKeyspace, prefix: str) -> str | None:
    """The local-key prefix that `prefix` selects in this keyspace, or `None` for no overlap.

    Two ways a keyspace can intersect a remote filter: the filter is inside the keyspace
    (`raw/caselist/hsld26/sha256/ab` inside `raw/caselist/hsld26/`), or the keyspace is inside the
    filter (`raw/caselist/hsld26/` inside `raw/`). Anything else selects nothing from it.
    """
    if not prefix:
        return ""
    if prefix.startswith(keyspace.remote_prefix):
        return prefix[len(keyspace.remote_prefix) :]
    if keyspace.remote_prefix.startswith(prefix):
        return ""
    return None


def _is_documented_prefix(remote_key: ObjectKey) -> bool:
    return any(remote_key.startswith(documented) for documented in EVIDENCE_PREFIXES)


def _stated_digest(landed: ObjectInfo, key: ObjectKey) -> Sha256Hex:
    if landed.sha256 is None:  # pragma: no cover - both adapters hash what they wrote
        raise BlobIntegrityError(key)
    return landed.sha256


def _error_code(failure: BaseException) -> str:
    """`BlobIntegrityError` -> `BLOB_INTEGRITY_ERROR`, matching the CLI's `--json` error codes."""
    name = type(failure).__name__
    return "".join(
        f"_{letter}" if letter.isupper() and index else letter for index, letter in enumerate(name)
    ).upper()


class _readable_source:
    """The file to upload for one local key: the store's own file, or a staged copy of it.

    An async context manager rather than a function because the staged case has to clean up. The
    filesystem store answers `path_for`, so the common case stages nothing and a 40-megabyte camp
    file is read once; a store that cannot name a file for a key is copied out through
    :meth:`~debate_core.application.ports.evidence_store.EvidenceObjectStore.get_file` first, which
    keeps this module working against any implementation of the port rather than only that one.
    """

    def __init__(self, keyspace: SyncKeyspace, local_key: ObjectKey) -> None:
        self._keyspace = keyspace
        self._local_key = local_key
        self._staged: Path | None = None

    async def __aenter__(self) -> Path:
        direct = self._keyspace.local_path_for
        if direct is not None:
            return direct(self._local_key)
        directory = Path(tempfile.mkdtemp(prefix="debate-sync-"))
        self._staged = directory / "object"
        await self._keyspace.local.get_file(self._local_key, self._staged)
        return self._staged

    async def __aexit__(self, *_: object) -> None:
        if self._staged is not None:
            self._staged.unlink(missing_ok=True)
            self._staged.parent.rmdir()


class _staging_file:
    """A temporary path for a download that is verified before it is put into the local store."""

    def __init__(self, local_key: ObjectKey) -> None:
        self._local_key = local_key
        self._directory: Path | None = None

    def __enter__(self) -> Path:
        self._directory = Path(tempfile.mkdtemp(prefix="debate-sync-"))
        return self._directory / "object"

    def __exit__(self, *_: object) -> None:
        if self._directory is None:  # pragma: no cover - __enter__ always sets it
            return
        for leftover in self._directory.iterdir():
            leftover.unlink()
        self._directory.rmdir()

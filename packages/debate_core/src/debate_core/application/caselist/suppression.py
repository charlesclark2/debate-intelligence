"""The suppression list and the removal log over their copies: merged, append-only, typed.

The port (:mod:`debate_core.application.ports.suppression`) says what an entry is and what a copy
may do. This module is the part that is the same whichever copies a command holds:

* :class:`RecordedSuppressionList` and :class:`RecordedRemovalLog` read every copy they are given as
  one set of lines and, on every append, write each copy the lines it lacks — the new entries, and
  any entry another copy already had. That is the set-union merge spec ac4 asks for, done on every
  write, and it is why a removal made from one machine reaches the bucket and a removal recorded in
  the bucket reaches this machine's copy the next time either is written.
* :class:`ObjectStoreAppendOnlyRecord` is one copy kept as a named object —
  `manifests/_suppression/suppression-list.jsonl` in the bucket — through the
  :class:`~debate_core.application.ports.evidence_store.EvidenceObjectStore` port. An object cannot
  be appended to in place, so an append reads the object, adds lines to the end of what it read,
  writes it back, and checks that what is now there still begins with every byte that was there
  before. The bucket is versioned, so the previous version is kept as well.

The local copy is :class:`~debate_core.integrations.local.suppression_list.LocalAppendOnlyFile`.

## The path-hold record travels with the list

The paths removals hold (`v1-e30-t13`) are a second append-only record, `path-holds.jsonl`, kept
beside the list in every place the list is kept
(:class:`~debate_core.application.ports.suppression.PathHoldEntry` says why it is not a line of the
list). :class:`RecordedSuppressionList` finds it from its own copies, by asking each for the record
beside it, and reads and appends it by the same set-union rule. So a command that holds the list
holds the holds: nothing has to be passed in for them, and nothing can be left out.
:func:`load_suppression_state` reads both, and that is the one function every reader of the list
calls.

## So does the withdrawal record

Which caselist each suppressed disclosure was withdrawn from (`v1-e30-t16`) is a third record,
`withdrawals.jsonl`, in the same place (:class:`~debate_core.application.ports.suppression.
WithdrawalEntry` says why). The list finds it beside its copies as it finds the path holds, and the
removal log beside its own, which is the same file: :func:`caselist_withdrawn_from` attributes a
suppression entry by it, and :func:`caselists_withdrawn_by` a removal log entry.

## And the held-digest record

What an import refused at a held path (`v1-e30-t23`) is a fourth record beside the list,
`held-digests.jsonl` (:class:`~debate_core.application.ports.suppression.HeldDigestEntry` says
why), found as the path holds are. Its writer is the one exception to the rule below: the import
appends it, to this machine's copy alone (:func:`record_held_digests`), and the removal, which holds
every copy, gives the bucket's copy what it lacks. `held-digests.jsonl` is also appended by a
bucket-mode run under its lock (`v1-e40-t12`): each save of the run-state bundle gives the bucket's
copy what the working copy holds first
(:meth:`~debate_core.application.caselist.run_state.RunState.save_held_digests`).

## Which copies a command holds

The composition root decides, by one rule: a command reads every copy it can reach without being
given anything new to reach. `caselist import` never talks to a bucket — it runs offline — so it
reads this environment's local copy. `caselist publish`, `status`, `pull`, `remove` and
`unsuppress` already hold the bucket, so they read the union. Every command that writes the list
writes the union to both, so the local copy is never behind the bucket on the machine that made a
removal.
"""

from __future__ import annotations

import logging
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from pydantic import ValidationError

from debate_core.application.errors import NotFound, StoreCredentialsExpired
from debate_core.application.ports.evidence_store import EvidenceObjectStore, ObjectKey, validate_object_key
from debate_core.application.ports.suppression import (
    HELD_DIGESTS_FILENAME,
    PATH_HOLDS_FILENAME,
    REMOVAL_SCOPES_FILENAME,
    WITHDRAWALS_FILENAME,
    AppendOnlyRecord,
    AppendOnlyViolation,
    HeldDigestEntry,
    HeldDigestList,
    KeepsRecordsBesideIt,
    PathHoldEntry,
    PathHoldList,
    RemovalLogEntry,
    RemovalScopeEntry,
    SuppressionEntry,
    SuppressionList,
    SuppressionState,
    UnreadableAppendOnlyRecord,
    WithdrawalEntry,
    WithdrawalList,
)

__all__ = [
    "HELD_DIGESTS_KEY",
    "PATH_HOLDS_KEY",
    "REMOVAL_LOG_KEY",
    "SUPPRESSION_LIST_KEY",
    "SUPPRESSION_PREFIX",
    "LocalFallbackSuppressionList",
    "ObjectStoreAppendOnlyRecord",
    "RecordedRemovalLog",
    "RecordedSuppressionList",
    "caselist_withdrawn_from",
    "caselists_withdrawn_by",
    "is_suppression_key",
    "load_suppression_state",
    "read_held_digests",
    "read_path_holds",
    "read_withdrawals",
    "record_held_digests",
]

logger = logging.getLogger(__name__)

SUPPRESSION_PREFIX: Final = "manifests/_suppression/"
"""Where both records live in the bucket. The one prefix the takedown credential may write."""

SUPPRESSION_LIST_KEY: Final = validate_object_key(f"{SUPPRESSION_PREFIX}suppression-list.jsonl")
REMOVAL_LOG_KEY: Final = validate_object_key(f"{SUPPRESSION_PREFIX}removal-log.jsonl")
PATH_HOLDS_KEY: Final = validate_object_key(f"{SUPPRESSION_PREFIX}{PATH_HOLDS_FILENAME}")
"""The bucket's copy of the path-hold record: beside the list, under the takedown's one prefix."""
HELD_DIGESTS_KEY: Final = validate_object_key(f"{SUPPRESSION_PREFIX}{HELD_DIGESTS_FILENAME}")
"""The bucket's copy of the held-digest record (`v1-e30-t23`): a removal writes it, and a bucket-mode
run appends to it under its lock at each save of the run-state bundle (`v1-e40-t12`)."""

_PATH_HOLDS_CALLED: Final = "path-hold list"
_HELD_DIGESTS_CALLED: Final = "held-digest record"
_REMOVAL_SCOPES_CALLED: Final = "removal-scope record"
_WITHDRAWALS_CALLED: Final = "withdrawal record"


def is_suppression_key(key: str) -> bool:
    """Whether `key` is under `manifests/_suppression/`, which only remove and unsuppress may write.

    One exception: `held-digests.jsonl` is also appended by a bucket-mode run under its lock
    (`v1-e40-t12`). `store sync` skips the whole prefix either way.
    """
    return key.startswith(SUPPRESSION_PREFIX)


async def load_suppression_state(suppression: SuppressionList) -> SuppressionState:
    """What `suppression` currently suppresses, and the paths it holds."""
    return SuppressionState.from_entries(await suppression.entries(), await read_path_holds(suppression))


async def read_path_holds(suppression: SuppressionList) -> tuple[PathHoldEntry, ...]:
    """Every path-hold entry `suppression` keeps, lifted or not. None for a list that keeps none."""
    return await suppression.path_holds() if isinstance(suppression, PathHoldList) else ()


async def read_held_digests(suppression: SuppressionList) -> tuple[HeldDigestEntry, ...]:
    """Every held-digest entry beside `suppression`'s copies (`v1-e30-t23`); none for a list keeping none."""
    return await suppression.held_digests() if isinstance(suppression, HeldDigestList) else ()


async def record_held_digests(suppression: SuppressionList, entries: Sequence[HeldDigestEntry]) -> None:
    """Append what an import held at a held path to the record beside `suppression` (`v1-e30-t23`).

    Nothing to append writes nothing. A list that holds paths keeps this record beside the same
    copies, so one that cannot take it is refused rather than passed over: an import that lost the
    only record of the bytes would let them back in at another path.
    """
    if not entries:
        return
    if not isinstance(suppression, HeldDigestList):
        raise AppendOnlyViolation("the suppression list", "it keeps no held-digest record")
    await suppression.append_held_digests(entries)


async def read_withdrawals(suppression: SuppressionList) -> tuple[WithdrawalEntry, ...]:
    """Every withdrawal entry beside `suppression`'s copies (`v1-e30-t16`); none for a list keeping none."""
    return await suppression.withdrawals() if isinstance(suppression, WithdrawalList) else ()


def caselist_withdrawn_from(entry: SuppressionEntry, withdrawals: Sequence[WithdrawalEntry]) -> str | None:
    """The slug of the caselist `entry` withdrew its copy from, or `None` where nothing records it.

    `None` for a suppression of a whole file, which is taken from every caselist, and for one an
    earlier build appended, which wrote no withdrawal record (`v1-e30-t16`).
    """
    return next((one.caselist for one in withdrawals if one.attributes(entry)), None)


def caselists_withdrawn_by(
    entry: RemovalLogEntry, withdrawals: Sequence[WithdrawalEntry]
) -> dict[str, tuple[str, ...]]:
    """For each file `entry` lists as withdrawn, the slugs of the caselists its request took it from.

    By request and sha256, from the withdrawals recorded no later than the log entry: a run appends
    its withdrawals first and its log entry last. Where one request withdrew a file in several runs,
    each run's entry names every caselist the request had withdrawn it from by then. A file with no
    withdrawal recorded, as an earlier build's removal has none, is not in the result.
    """
    found: dict[str, set[str]] = {}
    for one in withdrawals:
        if (
            one.sha256 in entry.withdrawn_sha256
            and one.request_id == entry.request_id
            and one.recorded_at <= entry.recorded_at
        ):
            found.setdefault(one.sha256, set()).add(one.caselist)
    return {digest: tuple(sorted(caselists)) for digest, caselists in sorted(found.items())}


class _MergedLines:
    """Several copies of one append-only record, read as one and written as a set union of lines."""

    def __init__(self, records: Sequence[AppendOnlyRecord]) -> None:
        if not records:
            raise ValueError("an append-only record needs at least one copy")
        self._records = tuple(records)

    @property
    def records(self) -> tuple[AppendOnlyRecord, ...]:
        return self._records

    async def read(self) -> list[tuple[str, str, int]]:
        """Every distinct line across the copies, first-seen order, with where it was first read."""
        seen: set[str] = set()
        merged: list[tuple[str, str, int]] = []
        for record in self._records:
            for number, line in enumerate(await record.read_lines(), start=1):
                if line not in seen:
                    seen.add(line)
                    merged.append((line, record.location, number))
        return merged

    async def append(self, lines: Sequence[str]) -> None:
        """Give every copy each line of the union, plus `lines`, that it does not already hold."""
        wanted = [line for line, _, _ in await self.read()]
        known = set(wanted)
        wanted.extend(line for line in dict.fromkeys(lines) if line not in known)
        for record in self._records:
            present = set(await record.read_lines())
            missing = [line for line in wanted if line not in present]
            if missing:
                await record.append_lines(missing)


class RecordedSuppressionList:
    """A :class:`~debate_core.application.ports.suppression.SuppressionList` over one or more copies.

    ::

        suppression = RecordedSuppressionList(local_copy, bucket_copy)
        state = await load_suppression_state(suppression)

    The first copy is the one a message names when a line cannot be read. Entries are returned
    deduplicated; their order does not matter (see
    :class:`~debate_core.application.ports.suppression.SuppressionState`).
    """

    def __init__(self, *records: AppendOnlyRecord) -> None:
        self._lines = _MergedLines(records)
        # The path-hold record of each copy that can name a record beside it: the local file and
        # the bucket's object can, and a copy that cannot (a test's in-memory one) keeps no holds.
        beside = [
            record.beside(PATH_HOLDS_FILENAME, called=_PATH_HOLDS_CALLED)
            for record in records
            if isinstance(record, KeepsRecordsBesideIt)
        ]
        self._path_hold_lines = _MergedLines(beside) if beside else None
        self._withdrawal_lines = _beside(records, WITHDRAWALS_FILENAME, _WITHDRAWALS_CALLED)
        self._held_digest_lines = _beside(records, HELD_DIGESTS_FILENAME, _HELD_DIGESTS_CALLED)

    @property
    def records(self) -> tuple[AppendOnlyRecord, ...]:
        return self._lines.records

    @property
    def path_hold_records(self) -> tuple[AppendOnlyRecord, ...]:
        """The path-hold record beside each copy of the list that keeps one."""
        return self._path_hold_lines.records if self._path_hold_lines is not None else ()

    async def entries(self) -> tuple[SuppressionEntry, ...]:
        return tuple(_parse(SuppressionEntry, *read) for read in await self._lines.read())

    async def append(self, entries: Sequence[SuppressionEntry]) -> None:
        await self._lines.append([entry.to_line() for entry in entries])

    async def path_holds(self) -> tuple[PathHoldEntry, ...]:
        """Every path-hold entry on every copy, deduplicated. A record that does not exist has none."""
        if self._path_hold_lines is None:
            return ()
        return tuple(_parse(PathHoldEntry, *read) for read in await self._path_hold_lines.read())

    async def append_path_holds(self, entries: Sequence[PathHoldEntry]) -> None:
        """Append to every copy's path-hold record, by the rule :meth:`append` follows.

        Each copy is also given what another copy holds and it lacks, with or without anything new:
        a run that stopped between the two copies is finished by the next one. Where no copy holds
        anything and there is nothing to append, no record is created: an environment that has
        never held a path has no `path-holds.jsonl`.
        """
        if self._path_hold_lines is None:
            if entries:
                raise AppendOnlyViolation(
                    self._lines.records[0].location, "no copy of this list keeps a path-hold record beside it"
                )
            return
        await self._path_hold_lines.append([entry.to_line() for entry in entries])

    async def withdrawals(self) -> tuple[WithdrawalEntry, ...]:
        """Every withdrawal entry on every copy, deduplicated. A record that does not exist has none."""
        return await _read_withdrawals(self._withdrawal_lines)

    async def held_digests(self) -> tuple[HeldDigestEntry, ...]:
        """Every held-digest entry on every copy, deduplicated (`v1-e30-t23`). None where none exists."""
        if self._held_digest_lines is None:
            return ()
        return tuple(_parse(HeldDigestEntry, *read) for read in await self._held_digest_lines.read())

    async def append_held_digests(self, entries: Sequence[HeldDigestEntry]) -> None:
        """Append to every copy's held-digest record, by the rule :meth:`append_path_holds` follows.

        With nothing new, each copy is still given what another holds and it lacks: that is how a
        removal, and a bucket-mode save of the run-state bundle (`v1-e40-t12`), write the bucket's
        copy of what an import recorded on this machine.
        """
        if self._held_digest_lines is None:
            if entries:
                raise AppendOnlyViolation(
                    self._lines.records[0].location,
                    "no copy of this list keeps a held-digest record beside it",
                )
            return
        await self._held_digest_lines.append([entry.to_line() for entry in entries])

    async def append_withdrawals(self, entries: Sequence[WithdrawalEntry]) -> None:
        """Append to every copy's withdrawal record, by the rule :meth:`append_path_holds` follows.

        Where no copy holds any and there is nothing to append, no record is created. A removal
        appends them just before the suppression entries they attribute, so no copy holds a
        suppressed disclosure without its caselist beside it.
        """
        if self._withdrawal_lines is None:
            if entries:
                raise AppendOnlyViolation(
                    self._lines.records[0].location,
                    "no copy of this list keeps a withdrawal record beside it",
                )
            return
        await self._withdrawal_lines.append([entry.to_line() for entry in entries])

    async def reconcile(self) -> None:
        """Write every copy the entries another copy has and it lacks. Appends nothing new."""
        await self._lines.append([])
        if self._path_hold_lines is not None:
            await self._path_hold_lines.append([])
        if self._withdrawal_lines is not None:
            await self._withdrawal_lines.append([])
        if self._held_digest_lines is not None:
            await self._held_digest_lines.append([])


class LocalFallbackSuppressionList:
    """The weekly pull's list: every copy, or this machine's alone when the bucket's needs a login.

    ::

        suppression = LocalFallbackSuppressionList(union, local=local_copy)

    `caselist pull` runs unattended, and a weekly launchd run usually finds the operator's SSO
    session expired. `v1-e34-t02` built the run so that the local stages need no session and only
    publish waits for one; reading the bucket's copy of this list from the importers undid that
    (`v1-e34-t07`, after PM review). So when — and only when — reading every copy fails with
    :class:`~debate_core.application.errors.StoreCredentialsExpired` (no credentials at all, or
    expired ones), the entries are this machine's copy alone, and :attr:`local_only_reason` says
    why. The pull's skip and its importers hold this one object, so they fall back together.

    It is as safe as `caselist import`, which reads only the local copy by design
    (`v1-e30-t07` Deviation 7): on the one operator machine every command that writes the list
    writes both copies, so this machine's copy is never behind the bucket's; and `caselist publish`,
    which needs a session anyway, still refuses suppressed sources from the union. **Revisit it the
    day a second machine imports**, the same condition as Deviation 7: a removal made there would
    then be in the bucket's copy only, and an import here with an expired session would not see it.

    Every other failure to read a copy still fails closed: an access denial is a missing grant, not a
    login that timed out, and a torn or unreadable line is a list nobody can honour. Appending never
    falls back; an entry written to one copy only would be the disagreement the list exists to
    prevent.
    """

    def __init__(self, union: SuppressionList, *, local: SuppressionList) -> None:
        self._union = union
        self._local = local
        self.fallbacks = 0
        """How many reads fell back so far. A caller compares it before and after a stage."""
        self.local_only_reason: str | None = None
        """Why the latest read that fell back did, or `None` if none has."""

    async def entries(self) -> tuple[SuppressionEntry, ...]:
        try:
            return await self._union.entries()
        except StoreCredentialsExpired as expired:
            entries = await self._local.entries()
            self.fallbacks += 1
            self.local_only_reason = f"the bucket's copy could not be read without a login ({expired})"
            logger.warning(
                "suppression list: the bucket's copy needs a login, so this machine's copy alone was read"
            )
            return entries

    async def append(self, entries: Sequence[SuppressionEntry]) -> None:
        await self._union.append(entries)

    async def path_holds(self) -> tuple[PathHoldEntry, ...]:
        """The path holds, by the rule :meth:`entries` follows: this machine's alone without a login.

        An import that read the list from this machine and then failed on the path-hold record
        beside it would be the failure the fallback exists to prevent.
        """
        try:
            return await read_path_holds(self._union)
        except StoreCredentialsExpired as expired:
            holds = await read_path_holds(self._local)
            self.fallbacks += 1
            self.local_only_reason = f"the bucket's copy could not be read without a login ({expired})"
            logger.warning(
                "suppression list: the bucket's path-hold record needs a login, so this machine's "
                "copy alone was read"
            )
            return holds

    async def append_path_holds(self, entries: Sequence[PathHoldEntry]) -> None:
        if not isinstance(self._union, PathHoldList):
            raise AppendOnlyViolation("the suppression list", "it keeps no path-hold record")
        await self._union.append_path_holds(entries)

    async def held_digests(self) -> tuple[HeldDigestEntry, ...]:
        """The held digests, by the rule :meth:`path_holds` follows: this machine's alone without a login."""
        try:
            return await read_held_digests(self._union)
        except StoreCredentialsExpired as expired:
            held = await read_held_digests(self._local)
            self.fallbacks += 1
            self.local_only_reason = f"the bucket's copy could not be read without a login ({expired})"
            logger.warning(
                "suppression list: the bucket's held-digest record needs a login, so this machine's "
                "copy alone was read"
            )
            return held

    async def append_held_digests(self, entries: Sequence[HeldDigestEntry]) -> None:
        """Append to this machine's copy alone, whatever the session (`v1-e30-t23`).

        The pull's importers append here, and a backfile import's runs unlocked, where no bucket
        write may happen. Unlike every other append, this is never the union's.
        `held-digests.jsonl` is also appended by a bucket-mode run under its lock (`v1-e40-t12`):
        each save of the run-state bundle gives the bucket's copy what this one holds. The pull's
        search index stage and the removal run again do the same.
        """
        await record_held_digests(self._local, entries)


class RecordedRemovalLog:
    """A :class:`~debate_core.application.ports.suppression.RemovalLog` over one or more copies.

    It keeps the removal-scope record (`removal-scopes.jsonl`, `v1-e30-t15`) beside each copy that
    can name a record beside it, found and merged as :class:`RecordedSuppressionList` finds the path
    holds: a command that holds the log holds the scopes. It reads the withdrawal record
    (`withdrawals.jsonl`, `v1-e30-t16`) beside it the same way, which is the file the list appends
    to, and never appends to it.
    """

    def __init__(self, *records: AppendOnlyRecord) -> None:
        self._lines = _MergedLines(records)
        beside = [
            record.beside(REMOVAL_SCOPES_FILENAME, called=_REMOVAL_SCOPES_CALLED)
            for record in records
            if isinstance(record, KeepsRecordsBesideIt)
        ]
        self._scope_lines = _MergedLines(beside) if beside else None
        self._withdrawal_lines = _beside(records, WITHDRAWALS_FILENAME, _WITHDRAWALS_CALLED)

    @property
    def records(self) -> tuple[AppendOnlyRecord, ...]:
        return self._lines.records

    async def withdrawals(self) -> tuple[WithdrawalEntry, ...]:
        """Every withdrawal entry beside every copy of the log, deduplicated (`v1-e30-t16`)."""
        return await _read_withdrawals(self._withdrawal_lines)

    async def entries(self) -> tuple[RemovalLogEntry, ...]:
        return tuple(_parse(RemovalLogEntry, *read) for read in await self._lines.read())

    async def scopes(self) -> tuple[RemovalScopeEntry, ...]:
        """Every scope entry on every copy, deduplicated. None for a log that keeps no scope record."""
        if self._scope_lines is None:
            return ()
        return tuple(_parse(RemovalScopeEntry, *read) for read in await self._scope_lines.read())

    async def append(
        self, entries: Sequence[RemovalLogEntry], *, scopes: Sequence[RemovalScopeEntry] = ()
    ) -> None:
        """Append `scopes` to every copy's scope record, then `entries` to every copy of the log.

        The scopes go first, so a log entry is never on a copy without its scope beside it: a scope
        alone is joined to nothing and read by nothing. Where no copy keeps a scope record, scopes
        are refused rather than dropped.
        """
        if scopes:
            if self._scope_lines is None:
                raise AppendOnlyViolation(
                    self._lines.records[0].location,
                    "no copy of this log keeps a removal-scope record beside it",
                )
            await self._scope_lines.append([scope.to_line() for scope in scopes])
        await self._lines.append([entry.to_line() for entry in entries])


def _beside(records: Sequence[AppendOnlyRecord], filename: str, called: str) -> _MergedLines | None:
    """The record named `filename` beside each copy that can name one, merged; `None` if none can."""
    beside = [
        record.beside(filename, called=called)
        for record in records
        if isinstance(record, KeepsRecordsBesideIt)
    ]
    return _MergedLines(beside) if beside else None


async def _read_withdrawals(lines: _MergedLines | None) -> tuple[WithdrawalEntry, ...]:
    if lines is None:
        return ()
    return tuple(_parse(WithdrawalEntry, *read) for read in await lines.read())


def _parse[
    EntryT: (
        SuppressionEntry,
        RemovalLogEntry,
        PathHoldEntry,
        RemovalScopeEntry,
        WithdrawalEntry,
        HeldDigestEntry,
    )
](kind: type[EntryT], line: str, location: str, number: int) -> EntryT:
    try:
        return kind.model_validate_json(line)
    except ValidationError as refused:
        # Pydantic's description of the field that failed, never the line itself.
        raise UnreadableAppendOnlyRecord(location, number, refused.errors()[0]["msg"]) from None


class ObjectStoreAppendOnlyRecord:
    """One copy of an append-only record kept as a named object: the bucket's copy.

    Works over any :class:`~debate_core.application.ports.evidence_store.EvidenceObjectStore`, so
    the same class keeps the bucket's copy through the S3 adapter and, in tests, a directory's copy
    through the filesystem one.

    An append is read, extend, write, verify:

    1. The object is downloaded (absent means empty).
    2. The new bytes are the old bytes followed by the new lines — built that way, so they cannot
       be anything else.
    3. They are uploaded over the object; the bucket keeps the previous version.
    4. The object is read back and must begin with every old byte and end with the new lines. If
       something else wrote it in between, that is an
       :class:`~debate_core.application.ports.suppression.AppendOnlyViolation` naming the key, and
       the caller re-runs; nothing is retried behind its back.

    `reader`, when given, does the reading and `store` only the writing. A removal writes with the
    takedown credential, which has no `s3:ListBucket`; without it S3 answers a read of a key that does
    not exist yet with 403, not 404, so an environment's first removal could not tell "no list yet"
    from "not allowed". The everyday credential can list, so it reads.
    """

    def __init__(
        self,
        store: EvidenceObjectStore,
        key: ObjectKey,
        *,
        location: str | None = None,
        reader: EvidenceObjectStore | None = None,
    ) -> None:
        self._store = store
        self._reader = reader or store
        self._key = validate_object_key(key)
        self._location = location or key

    @property
    def location(self) -> str:
        return self._location

    @property
    def key(self) -> ObjectKey:
        return self._key

    def beside(self, filename: str, *, called: str) -> ObjectStoreAppendOnlyRecord:
        """The object named `filename` under this one's prefix, written and read as this one is.

        Its location is this one's with the key's last segment changed, so a copy named by its
        `s3://` address names its neighbour by one too. `called` is for copies named by a role.
        """
        del called
        key = validate_object_key(f"{self._key.rpartition('/')[0]}/{filename}")
        location = (
            f"{self._location.removesuffix(self._key)}{key}" if self._location.endswith(self._key) else key
        )
        reader = self._reader if self._reader is not self._store else None
        return ObjectStoreAppendOnlyRecord(self._store, key, location=location, reader=reader)

    async def read_lines(self) -> tuple[str, ...]:
        return _lines_of(await self._read_bytes(), self._location)

    async def append_lines(self, lines: Sequence[str]) -> None:
        if not lines:
            return
        for line in lines:
            if "\n" in line or "\r" in line:
                raise AppendOnlyViolation(self._location, "a line to append contains a line break")
        before = await self._read_bytes()
        _lines_of(before, self._location)  # refuses a torn last line before anything is written
        after = before + "".join(f"{line}\n" for line in lines).encode("utf-8")
        with tempfile.TemporaryDirectory(prefix="debate-append-") as directory:
            staged = Path(directory) / "record.jsonl"
            staged.write_bytes(after)
            await self._store.put_file(self._key, staged)
        landed = await self._read_bytes()
        if not landed.startswith(before) or landed != after:
            raise AppendOnlyViolation(
                self._location, "the object changed while it was being appended to; re-run the command"
            )

    async def _read_bytes(self) -> bytes:
        with tempfile.TemporaryDirectory(prefix="debate-append-") as directory:
            staged = Path(directory) / "record.jsonl"
            try:
                await self._reader.get_file(self._key, staged)
            except NotFound:
                return b""
            return staged.read_bytes()


def _lines_of(data: bytes, location: str) -> tuple[str, ...]:
    """The lines of a record's bytes, refusing one whose last line was never finished."""
    if not data:
        return ()
    if not data.endswith(b"\n"):
        lines = data.count(b"\n") + 1
        raise UnreadableAppendOnlyRecord(
            location, lines, "the last line has no newline (a write was interrupted)"
        )
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise UnreadableAppendOnlyRecord(location, 0, "not UTF-8") from None
    return tuple(line for line in text.split("\n")[:-1])

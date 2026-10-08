"""Taking removed bytes out of the sync's inbox: the step of a removal `v1-e30-t09` adds.

`caselist pull` downloads into an inbox (`caselist.inbox_dir`, or `<data_dir>/inbox`; one per
environment that pulls) and never clears it. After a removal the store and the bucket no longer
hold the removed files, but the inbox still did: the camp file as downloaded (`openev-<id>-…`) and
every weekly archive (`<slug>-weekly-<date>.zip`) whose members include it. The data-use policy
promises removal from everywhere the material is stored, so a removal now plans and purges those
too. After a `COMPLETED` removal no file in the inbox holds a removed sha256, as a file or as an
archive member.

## What counts as removed here: the suppression list, and nothing else

A file or an archive entry is taken out when the suppression list, as it will read once this
removal's entries are appended, stops it:

* its bytes are suppressed as a whole source; or
* it is a member of a weekly archive and that disclosure of it — its caselist and path — is
  suppressed, which is how a team's copy of a file another team also holds is withdrawn; or
* it is junk (`__MACOSX/` AppleDouble, a `~$` Word lock file, a `.DS_Store`) that names or sits
  only beside suppressed files, by the rule the importer uses to withhold the same junk's manifest
  rows (:func:`~debate_core.application.caselist.pipeline.withheld_skipped_paths`). A Word lock
  file holds the name of whoever had the document open, so leaving it would leave the very name.

Every other entry is kept byte for byte — another team's disclosure in the same archive, another
holder's copy of a withdrawn file, a camp file the list does not stop. An earlier removal's
leftovers are taken out too, because the list stops them; that is how running a removal again
clears what a removal made before this step existed left behind.

## Imported or waiting: what happens to each file

A file holding nothing the list stops is not touched. One that does is deleted or rewritten
without the removed entries, and which depends on whether anything in it is still to be imported:

`DELETE`, the file itself is removed
    A single document whose bytes are suppressed. Nothing else is in it.
`DELETE`, every member is removed
    A camp download (or any other zip) whose every real member the list stops. This is the sync's
    own test for a removed camp file (:attr:`~debate_core.application.caselist_sync.
    SelectionDecision.SKIPPED_AS_REMOVED`), so nothing it delivered is wanted.
`DELETE`, imported
    A weekly archive whose week this machine already holds a manifest for, or a camp download a
    manifest row came from. Its other members are already in the store.
`REWRITE`, waiting to be imported
    A weekly archive dated after the newest week imported, or a camp download no manifest records.
    The next pull imports it from the inbox (`ALREADY_IN_INBOX`), so it is rewritten without the
    removed entries, never deleted.
`REWRITE`, not a sync download
    Any other zip: nothing says it was imported, so nothing in it is thrown away.

**Why a waiting archive is never deleted.** `_decide_archive` calls a weekly dated after the newest
imported snapshot `ALREADY_IN_INBOX` when it is in the inbox and `DOWNLOAD` when it is not. Deleting
one would make the next pull fetch it again — a bulk download from the maintainer's five a day —
and put the removed files back in the inbox, the waste `v1-e34-t07` exists to stop, and the other
teams' disclosures in it would be imported a week late or, if the site had stopped listing it, never.

**Why an imported archive is deleted rather than rewritten.** It is dated on or before the newest
imported snapshot, so the sync calls it `ALREADY_IMPORTED` whether or not it is in the inbox and
never fetches it again; everything else it held is already stored with its manifest, whose
`archive_sha256` names the upstream archive. A rewritten copy would be bytes nothing reads, whose
digest matches neither that manifest nor the archive upstream still serves. ADR-0017: the site
keeps its back-catalogue, so the original can be fetched again if it is ever needed — recovering
from a mistaken removal needs exactly that, and a rewritten copy would not have helped, because the
removed file is the one thing it would not hold — and a re-fetched archive is filtered by the
importer.

**A camp download that is deleted is remembered first.** The sync decides that an OpenEv id was
removed by asking the list about the digests the id delivered, read from the delivery record
(`caselist-sync-openev-deliveries.json`) or, failing that, from the inbox copy. A camp file
imported before that record existed, or never imported, is known only from its inbox copy, so the
digests are written to the record before the copy is deleted
(:meth:`~debate_core.application.caselist_sync.OpenEvDeliveries.remember_if_unknown`). Without
that, the next pull would download the removed file again.

## What a rewritten archive's manifest records

The next pull imports the rewritten file and records its digest as the snapshot's
`archive_sha256`, because that field is the digest of the file imported — "we already imported
this exact file" (`ArchiveSnapshot`), and for a camp download what the sync matches the inbox copy
against. It is not the upstream archive's digest, and nothing pretends it is: the rewritten zip's
own comment names the request and the digest it was rewritten from, and the removal log entry
records each rewrite as a pair of digests (`inbox_rewrites`), so the chain from the manifest back
to what OpenCaselist served is in the append-only record, in both copies.

## How it is carried out

Under the sync's run lock (`<data_dir>/caselist-sync.lock`), so a `caselist pull` cannot import or
download into the inbox while it changes. Each file's digest is checked against the plan before
anything is done to it; a file that changed is not touched and the run stops `INCOMPLETE`. A
rewrite is written beside the original under a dot name the sync skips, read back and compared
entry by entry with the original less the dropped entries, and then renamed over it, so a run cut
short leaves each file either as it was or rewritten, never half written. Re-running the same
command plans again from the list and finishes the rest.

## Not checked

`<inbox>/.partial/` (downloads in progress, which the pull sweeps) and dot files, as the sync skips
them; symbolic links, which are not followed. A zip that cannot be read cannot be checked: it is
reported, and the removal does not call itself complete while it is there.

Nothing here logs. Its errors name a file by :attr:`InboxFilePlan.label` — a weekly archive's name
(a caselist and a date) or an OpenEv id — never a member's path or a camp file's title; the plan,
which the operator reads in their own terminal, shows the inbox names in full.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import uuid
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Final

from debate_core.application.caselist.pipeline import withheld_skipped_paths
from debate_core.application.caselist_sync import (
    LOCK_FILENAME,
    OPENEV_DELIVERIES_FILENAME,
    OpenEvDeliveries,
    OpenEvDelivery,
    RunLock,
    SyncRunInProgress,
    inbox_files,
    openev_id_of_inbox_name,
    weekly_archive_of_inbox_name,
)
from debate_core.application.errors import ArchiveTooLarge, DomainError, UnreadableArchive
from debate_core.application.ports.archive import ArchiveRewriter, InventoriedEntry
from debate_core.application.ports.suppression import SuppressionState, disclosure_digest

__all__ = [
    "CaselistInbox",
    "InboxAction",
    "InboxFileChanged",
    "InboxFileKind",
    "InboxFilePlan",
    "InboxFileUnreadable",
    "InboxInUse",
    "InboxPurge",
    "InboxReason",
    "InboxRewrite",
    "InboxRewriteFailed",
    "InboxTeamFilesLeft",
    "plan_inbox",
    "purge_inbox",
]

_REWRITE_SUFFIX: Final = ".removal-rewrite"
_CHUNK: Final = 1024 * 1024


# ------------------------------------------------------------------------------------------------
# What the inbox is
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CaselistInbox:
    """One environment's download inbox, as a removal sees it.

    Args:
        directory: `caselist.inbox_dir`, or `<data_dir>/inbox` when that is unset — the directory
            `caselist pull` downloads into. It need not exist.
        state_dir: The environment's data directory, where the sync keeps its run lock and the
            OpenEv delivery record.
        archives: Lists a zip's entries and rewrites one without some of them.
    """

    directory: Path
    state_dir: Path
    archives: ArchiveRewriter

    @property
    def deliveries(self) -> OpenEvDeliveries:
        return OpenEvDeliveries(self.state_dir / OPENEV_DELIVERIES_FILENAME)


class InboxFileKind(StrEnum):
    """What an inbox file is, by the name `caselist pull` gave it."""

    WEEKLY_ARCHIVE = "weekly_archive"
    """`<slug>-weekly-<date>.zip`."""
    OPENEV = "openev"
    """`openev-<id>-<file name>`: a single camp document, or a camp release as a zip."""
    OTHER = "other"
    """Anything else: a file the pull did not name, put there by hand."""


class InboxAction(StrEnum):
    DELETE = "delete"
    REWRITE = "rewrite"
    UNREADABLE = "unreadable"
    """A zip that cannot be opened, so cannot be checked. Nothing is done to it."""


class InboxReason(StrEnum):
    """Why a file is deleted or rewritten. See the module docstring for each."""

    THE_FILE_IS_REMOVED = "the file itself is removed"
    EVERY_MEMBER_IS_REMOVED = "every member is removed"
    IMPORTED = "imported: everything else in it is already in the store"
    WAITING_TO_BE_IMPORTED = "waiting to be imported: the next pull imports what is kept"
    NOT_A_SYNC_DOWNLOAD = "not a download the pull named, so nothing else in it is thrown away"
    CANNOT_BE_READ = "cannot be read as a zip, so it could not be checked"


@dataclass(frozen=True, slots=True)
class InboxFilePlan:
    """One inbox file a removal deletes or rewrites, and why. Its entry names are the operator's only."""

    name: str
    """Its path relative to the inbox: the download's own name, for everything the pull wrote."""
    kind: InboxFileKind
    sha256: str
    """The file's digest when planned. The executor acts only on these exact bytes."""
    action: InboxAction
    reason: InboxReason
    removed_sha256: tuple[str, ...] = ()
    """The suppressed digests it holds, as itself or as entries."""
    dropped: tuple[str, ...] = ()
    """For a rewrite: the names of the entries left out, as the zip carries them."""
    entries_dropped: int = 0
    """Files (not directory entries) taken out, junk included."""
    entries_kept: int = 0
    caselist: str | None = None
    snapshot: date | None = None
    openev_id: int | None = None
    delivered: frozenset[str] = frozenset()
    """For a camp download: the digests of every real member, which the delivery record keeps."""
    detail: str | None = None
    """For `UNREADABLE`: why, without a member's path."""

    @property
    def label(self) -> str:
        """How an error names this file: a weekly archive's own name (a caselist and a date), an
        OpenEv download's id, never a camp file's title or a name somebody gave a file by hand."""
        if self.kind is InboxFileKind.WEEKLY_ARCHIVE:
            return self.name
        if self.openev_id is not None:
            return f"openev-{self.openev_id}"
        return f"the inbox file with sha256 {self.sha256[:12]}…"


@dataclass(frozen=True, slots=True)
class InboxTeamFilesLeft:
    """A weekly archive waiting to be imported that holds files under the team's directory the list
    does not stop: files the store has never seen, so the removal could not resolve them. The next
    pull imports them; running the same removal after it removes them."""

    name: str
    files: int


@dataclass(frozen=True, slots=True)
class InboxRewrite:
    """One rewrite, for the removal log: the file's digest before and after. Digests only."""

    from_sha256: str
    to_sha256: str


@dataclass(slots=True)
class InboxPurge:
    """What :func:`purge_inbox` did, counted as it goes so a run cut short still reports its share."""

    deleted: int = 0
    rewritten: int = 0
    deliveries_recorded: int = 0
    rewrites: list[InboxRewrite] = field(default_factory=lambda: [])


# ------------------------------------------------------------------------------------------------
# Errors: each stops the run INCOMPLETE, and re-running finishes it
# ------------------------------------------------------------------------------------------------


class InboxInUse(DomainError):
    """A `caselist pull` holds the sync's run lock, so the inbox cannot be changed under it."""

    def __init__(self, lock_path: Path) -> None:
        self.lock_path = lock_path
        super().__init__(
            f"a caselist pull is running (it holds {lock_path}), so the inbox was left as it was; "
            "run the same command again when the pull has finished"
        )


class InboxFileChanged(DomainError):
    """An inbox file is not the bytes the plan was made from. It was not touched."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(
            f"inbox file {name} changed after the removal was planned, so it was not touched; "
            "run the same command again to plan it afresh"
        )


class InboxFileUnreadable(DomainError):
    """A zip in the inbox cannot be read, so whether it holds removed bytes cannot be known."""

    def __init__(self, name: str, detail: str | None) -> None:
        self.name = name
        super().__init__(
            f"inbox file {name} cannot be read as a zip ({detail or 'unreadable'}), so it was not checked "
            "for removed files. It cannot be imported either: move it out of the inbox or delete it, "
            "then run the same command again"
        )


class InboxRewriteFailed(DomainError):
    """A rewrite could not be written, or did not read back as the original less the dropped entries."""

    def __init__(self, name: str, reason: str) -> None:
        self.name = name
        super().__init__(f"inbox file {name} could not be rewritten ({reason}); it was left as it was")


# ------------------------------------------------------------------------------------------------
# Planning
# ------------------------------------------------------------------------------------------------


def plan_inbox(
    inbox: CaselistInbox,
    *,
    suppression: SuppressionState,
    imported_weeks: Collection[tuple[str, date]],
    imported_openev_downloads: Collection[str],
    team: tuple[str, str, str] | None = None,
) -> tuple[tuple[InboxFilePlan, ...], tuple[InboxTeamFilesLeft, ...]]:
    """Every inbox file holding something `suppression` stops, and what to do with it. Reads only.

    Args:
        inbox: The inbox and where the sync keeps its state.
        suppression: The list as it will read once this removal's entries are appended.
        imported_weeks: `(caselist, snapshot)` for every weekly manifest this machine holds.
        imported_openev_downloads: The download digests this machine's OpenEv manifest rows name.
        team: `(caselist, school, team code)` for a `--team` removal, to report the team's files
            in a waiting archive that the list does not stop; `None` otherwise.
    """
    remembered = inbox.deliveries.read()
    planned: list[InboxFilePlan] = []
    left: list[InboxTeamFilesLeft] = []
    for path in inbox_files(inbox.directory):
        name = path.relative_to(inbox.directory).as_posix()
        one, team_files = _plan_file(
            inbox,
            path,
            name,
            suppression=suppression,
            imported_weeks=imported_weeks,
            imported_openev_downloads=imported_openev_downloads,
            remembered={key: value.download_sha256 for key, value in remembered.items()},
            team=team,
        )
        if one is not None:
            planned.append(one)
        if team_files:
            left.append(InboxTeamFilesLeft(name=name, files=team_files))
    return tuple(planned), tuple(left)


def _plan_file(
    inbox: CaselistInbox,
    path: Path,
    name: str,
    *,
    suppression: SuppressionState,
    imported_weeks: Collection[tuple[str, date]],
    imported_openev_downloads: Collection[str],
    remembered: dict[int, str],
    team: tuple[str, str, str] | None,
) -> tuple[InboxFilePlan | None, int]:
    digest = _digest_of(path)
    kind, caselist, snapshot, openev_id = _kind_of(name)
    whole = suppression.suppresses_source(digest)
    if path.suffix.lower() != ".zip":
        if not whole:
            return None, 0
        return (
            InboxFilePlan(
                name=name,
                kind=kind,
                sha256=digest,
                action=InboxAction.DELETE,
                reason=InboxReason.THE_FILE_IS_REMOVED,
                removed_sha256=(digest,),
                openev_id=openev_id,
                delivered=frozenset({digest}),
            ),
            0,
        )

    try:
        entries = inbox.archives.inventory(path)
    except (UnreadableArchive, ArchiveTooLarge) as unreadable:
        reason = unreadable.reason if isinstance(unreadable, UnreadableArchive) else "over the size ceilings"
        return (
            InboxFilePlan(
                name=name,
                kind=kind,
                sha256=digest,
                action=InboxAction.DELETE if whole else InboxAction.UNREADABLE,
                reason=InboxReason.THE_FILE_IS_REMOVED if whole else InboxReason.CANNOT_BE_READ,
                removed_sha256=(digest,) if whole else (),
                openev_id=openev_id,
                delivered=frozenset({digest}) if whole else frozenset(),
                detail=None if whole else reason,
            ),
            0,
        )

    scope = caselist if kind is InboxFileKind.WEEKLY_ARCHIVE else None
    dropped, removed = entries_to_drop(entries, suppression=suppression, disclosure_scope=scope)
    real = [entry for entry in entries if entry.skip_reason is None and entry.sha256 is not None]
    waiting = kind is InboxFileKind.WEEKLY_ARCHIVE and (caselist, snapshot) not in imported_weeks
    team_files = (
        _team_files_left(entries, dropped, team)
        if team is not None and waiting and caselist == team[0]
        else 0
    )
    if not dropped and not whole:
        return None, team_files

    files = [entry for entry in entries if not entry.is_directory]
    kept_real = [entry for entry in real if entry.name not in dropped]
    if whole:
        action, reason = InboxAction.DELETE, InboxReason.THE_FILE_IS_REMOVED
    elif kind is InboxFileKind.WEEKLY_ARCHIVE:
        action, reason = (
            (InboxAction.REWRITE, InboxReason.WAITING_TO_BE_IMPORTED)
            if waiting
            else (InboxAction.DELETE, InboxReason.IMPORTED)
        )
    elif not kept_real:
        action, reason = InboxAction.DELETE, InboxReason.EVERY_MEMBER_IS_REMOVED
    elif kind is InboxFileKind.OPENEV and (
        digest in imported_openev_downloads or (openev_id is not None and remembered.get(openev_id) == digest)
    ):
        action, reason = InboxAction.DELETE, InboxReason.IMPORTED
    elif kind is InboxFileKind.OPENEV:
        action, reason = InboxAction.REWRITE, InboxReason.WAITING_TO_BE_IMPORTED
    else:
        action, reason = InboxAction.REWRITE, InboxReason.NOT_A_SYNC_DOWNLOAD

    dropped_files = sum(1 for entry in files if entry.name in dropped)
    return (
        InboxFilePlan(
            name=name,
            kind=kind,
            sha256=digest,
            action=action,
            reason=reason,
            removed_sha256=tuple(sorted({*removed, *([digest] if whole else [])})),
            dropped=tuple(entry.name for entry in entries if entry.name in dropped),
            entries_dropped=dropped_files,
            entries_kept=len(files) - dropped_files,
            caselist=caselist,
            snapshot=snapshot,
            openev_id=openev_id,
            delivered=frozenset(entry.sha256 for entry in real if entry.sha256 is not None),
        ),
        team_files,
    )


def entries_to_drop(
    entries: Sequence[InventoriedEntry], *, suppression: SuppressionState, disclosure_scope: str | None
) -> tuple[frozenset[str], frozenset[str]]:
    """The names of the entries the list stops, and the suppressed digests among them.

    `disclosure_scope` is the caselist of a weekly archive, whose members are disclosures, or `None`
    for anything else, which only a whole-source entry stops (as the OpenEv importer reads the list).
    See the module docstring for the junk rule and for directory entries.
    """
    stopped: set[str] = set()
    removed: set[str] = set()
    real: dict[str, bool] = {}
    for entry in entries:
        if entry.sha256 is None:
            continue
        disclosure = (
            disclosure_digest(disclosure_scope, entry.path)
            if disclosure_scope is not None and entry.skip_reason is None
            else None
        )
        hit = suppression.suppresses(entry.sha256, disclosure=disclosure)
        if hit:
            stopped.add(entry.name)
            removed.add(entry.sha256)
        if entry.skip_reason is None:
            real[entry.path] = hit or real.get(entry.path, False)
    shadowing = withheld_skipped_paths(
        real, [entry.path for entry in entries if entry.skip_reason is not None]
    )
    stopped |= {entry.name for entry in entries if entry.skip_reason is not None and entry.path in shadowing}
    # A directory entry goes with the last file under it, and only then: it names the directory.
    files = [entry for entry in entries if not entry.is_directory]
    for entry in entries:
        if not entry.is_directory:
            continue
        under = [one for one in files if one.name.startswith(entry.name.rstrip("/") + "/")]
        if under and all(one.name in stopped for one in under):
            stopped.add(entry.name)
    return frozenset(stopped), frozenset(removed)


def _team_files_left(
    entries: Iterable[InventoriedEntry], dropped: frozenset[str], team: tuple[str, str, str]
) -> int:
    _, school, team_code = team
    count = 0
    for entry in entries:
        if entry.skip_reason is not None or entry.sha256 is None or entry.name in dropped:
            continue
        directories = entry.path.split("/")[:-1]
        if len(directories) >= 2 and (directories[-2].strip(), directories[-1].strip()) == (
            school,
            team_code,
        ):
            count += 1
    return count


def _kind_of(name: str) -> tuple[InboxFileKind, str | None, date | None, int | None]:
    if "/" not in name:
        weekly = weekly_archive_of_inbox_name(name)
        if weekly is not None:
            return InboxFileKind.WEEKLY_ARCHIVE, weekly[0], weekly[1], None
        openev_id = openev_id_of_inbox_name(name)
        if openev_id is not None:
            return InboxFileKind.OPENEV, None, None, openev_id
    return InboxFileKind.OTHER, None, None, None


# ------------------------------------------------------------------------------------------------
# Carrying it out
# ------------------------------------------------------------------------------------------------


def purge_inbox(
    inbox: CaselistInbox,
    planned: Sequence[InboxFilePlan],
    *,
    request_id: str,
    done: InboxPurge,
) -> None:
    """Delete and rewrite the planned files, under the sync's run lock. Counts into `done` as it goes.

    Raises a :class:`~debate_core.application.errors.DomainError` — :class:`InboxInUse`,
    :class:`InboxFileChanged`, :class:`InboxFileUnreadable`, :class:`InboxRewriteFailed` — or an
    `OSError` at the first file it cannot finish, having left that file as it was.
    """
    if not planned:
        return
    try:
        with RunLock(inbox.state_dir / LOCK_FILENAME):
            for one in planned:
                _carry_out(inbox, one, request_id=request_id, done=done)
    except SyncRunInProgress as busy:
        raise InboxInUse(busy.lock_path) from None


def _carry_out(inbox: CaselistInbox, one: InboxFilePlan, *, request_id: str, done: InboxPurge) -> None:
    path = inbox.directory / one.name
    if one.action is InboxAction.UNREADABLE:
        raise InboxFileUnreadable(one.label, one.detail)
    if _digest_of(path) != one.sha256:
        raise InboxFileChanged(one.label)
    if one.action is InboxAction.REWRITE:
        done.rewrites.append(_rewrite(inbox, path, one, request_id=request_id))
        done.rewritten += 1
        return
    if one.openev_id is not None and one.delivered:
        # Before the copy goes: the only other place the sync could learn these digests from.
        done.deliveries_recorded += int(
            inbox.deliveries.remember_if_unknown(
                one.openev_id,
                OpenEvDelivery(download_sha256=one.sha256, path_sha256=None, member_sha256=one.delivered),
            )
        )
    path.unlink()
    done.deleted += 1


def _rewrite(inbox: CaselistInbox, path: Path, one: InboxFilePlan, *, request_id: str) -> InboxRewrite:
    """Write the file without its dropped entries beside it, check it, and rename it over the original.

    It is staged under the same name in a dot directory beside the original — which the sync skips —
    because the reader's wrapper rule reads the archive's own name: a staged copy named otherwise
    could read back with different paths.
    """
    staging = path.parent / f".{uuid.uuid4().hex}{_REWRITE_SUFFIX}"
    staged = staging / path.name
    comment = json.dumps(
        {
            "rewritten_by": "debate-research caselist remove",
            "request_id": request_id,
            "rewritten_from_sha256": one.sha256,
            "entries_removed": one.entries_dropped,
        },
        sort_keys=True,
    ).encode("utf-8")
    try:
        staging.mkdir()
        original = inbox.archives.inventory(path)
        inbox.archives.rewrite_without(path, staged, drop=one.dropped, comment=comment)
        expected = [_identity(entry) for entry in original if entry.name not in set(one.dropped)]
        rewritten = inbox.archives.inventory(staged)
        if [_identity(entry) for entry in rewritten] != expected:
            raise InboxRewriteFailed(
                one.label, "it did not read back as the original without the removed entries"
            )
        with staged.open("rb") as written:
            os.fsync(written.fileno())
        os.replace(staged, path)
    except (UnreadableArchive, ArchiveTooLarge) as broken:
        raise InboxRewriteFailed(one.label, type(broken).__name__) from broken
    finally:
        staged.unlink(missing_ok=True)
        with contextlib.suppress(OSError):
            staging.rmdir()
    return InboxRewrite(from_sha256=one.sha256, to_sha256=_digest_of(path))


def _identity(entry: InventoriedEntry) -> tuple[str, str, str | None, str | None]:
    return entry.name, entry.path, None if entry.skip_reason is None else str(entry.skip_reason), entry.sha256


def _digest_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()

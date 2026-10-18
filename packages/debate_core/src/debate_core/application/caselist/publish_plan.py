"""Where a caselist's sources and manifests go in the bucket, and what publishing them would do.

Everything here is a pure function of its arguments: key layout, reading a manifest's rows, and a
:class:`PublishPlan` built from the snapshots on this machine and a listing of the bucket. No store
is called. :mod:`debate_core.application.caselist.publish_service` executes a plan and
:mod:`debate_core.application.caselist.status_service` compares the two sides; both lean on the
layout and the manifest reading defined once here.

## The keys

::

    raw/caselist/hsld26/sha256/ab/cd/abcd…ef01     one disclosed source, by the digest of its bytes
    raw/openev/2026/sha256/1f/9e/1f9e…c4a1          one OpenEv camp file, filed under its topic year
    manifests/hsld26/2026-09-15.jsonl               one weekly snapshot of one caselist
    manifests/hsld26/full/2026-10-06.jsonl          one complete archive of one caselist
    manifests/openev/2026-ndi.jsonl                 one camp's files for one year

A complete archive (`v1-e34-t04`) is a snapshot named `full/<date>` wherever a snapshot is named —
`caselist publish --snapshot full/2026-10-06`, a pending publish, a status row — and its sources are
filed under the caselist's own `raw/` prefix like any weekly's, by digest. Its manifest is nested
so that it never shares a key with the weekly of the same date. Every reader of manifest keys gets
the weekly series alone unless it asks for the complete archives as well
(:func:`snapshot_of_manifest_key`'s `full_archives`), so a reader that was written for the weekly
series cannot see one by accident.

A source key is the digest and nothing else: no extension, no school, no team code, no original
filename (`docs/policies/caselist-data-use.md`, personal-data rule 3; the task spec). An extension
would make identical bytes two objects, and anything identifying would put a minor's initials into
every log line, error message and CloudTrail record that quotes the key. The fan-out is the local
blob store's, two levels of two hex characters, so that `store sync` and this module agree on the
tail of every key (`docs/architecture/evidence-store-layout.md`).

Camp files go under `raw/openev/<year>/` rather than `raw/caselist/openev/` because that is what
the layout document says; the session report for `v1-e30-t05-caselist-publish` records the
difference from the spec's shorter wording.

## A snapshot's sources

A manifest has one row per archive member, and not every row is a source this snapshot holds. The
rows that are — `NEW`, `UNCHANGED`, `CHANGED`, `DUPLICATE` — are the importer's
:data:`~debate_core.application.caselist.import_service.STORED_CLASSIFICATIONS`. A `REMOVED` row
describes a path the *previous* archive had; a `SUPPRESSED` row is a file that was deliberately not
stored; a skipped member has no digest. None of those is uploaded and none of them holds a
snapshot's manifest back.

Several rows can name one digest (a re-upload, another team's copy), so a snapshot's sources are
its *distinct* digests. Publishing the three synthetic weeks writes 14 objects for 31 member rows.

## What the plan decides, per source

| In the bucket's listing | Action | What the publisher then does |
|---|---|---|
| absent | `upload` | uploads, then confirms the bucket's recorded digest |
| present, same size | `verify` | heads it; skipped only if the recorded digest matches |
| present, different size | `mismatched` | nothing: the key names other bytes; the snapshot fails |
| (an earlier snapshot in this plan uploads it) | `uploaded_earlier` | waits on that upload's outcome |
| (not in the local blob store) | `missing_locally` | nothing; the snapshot fails |
| (on the suppression list) | `suppressed` | nothing |

The manifest is always last, and its action is `upload` or `verify` on the same rule. Whether it is
written is not the plan's decision but the publisher's, made after every source has an outcome.

## A manifest that still names a suppressed file is withheld

The suppression list (`v1-e30-t07`) is a required argument of :func:`build_publish_plan`, not an
option. A suppressed source is never uploaded. And a manifest with a *stored* row that the list
stops — the whole file, or that one team's disclosure of it — is withheld from the bucket
(:attr:`SnapshotPlan.suppressed_rows`), because uploading it would publish the removed path, school
and team code all over again. A manifest written after the removal has no such row (the importers
give a suppressed member none, and `caselist remove` rewrites the manifests it touches), so this
only fires for a manifest the removal never reached, and the fix is to run the removal on this
machine.

A stored row at a path a removal holds (`v1-e30-t13`), in a snapshot the hold covers, withholds the
manifest the same way (:attr:`SnapshotPlan.held_rows`, `v1-e30-t21`), with the same outcome and the
same code. Its bytes are not on the list, so the row is the requester's later upload at the removed
path, and uploading the manifest would publish that path. This build's importer never writes such a
row; a build from before `v1-e30-t13` imported one, because it reads no hold. Running the same
removal again takes the row out.

So does a skipped member's row at a held path, such as a symbolic link, in a snapshot the hold
covers (:attr:`SnapshotPlan.held_skipped_rows`; the PM's amendment of 2026-10-18 to `v1-e30-t23`).
Its path names the school and the team, and the link's body is often the removed file's name. A
build from before `v1-e30-t22` writes one, and before this task the publisher published it. It has
no bytes, so nothing else of it changes: the same outcome, the same code, and the fix the message
names is the same removal run again.

## Bytes only held rows name are not uploaded

A held row's bytes are the requester's later upload at the removed path, and a removal is a privacy
request: they do not go to the bucket on a held row's account (`v1-e30-t22`, the PM's ruling of
2026-10-16). So a digest that held rows name and no other row of the same manifest does is left out
of that snapshot's plan (:func:`held_only_digests`, :attr:`SnapshotPlan.held_back`), whatever the
bucket holds: it is neither uploaded nor verified, and no count includes it. A digest an unheld row
also names, another team's copy at its own path or a copy whose disclosure alone was withdrawn, is
planned by the table above as before, so another team's copy is never held back; and a later
snapshot whose own row names it uploads it as its own. The manifest is withheld for the held row as
before, with the same outcome, code and held count.

Such bytes are still in this machine's blob store, put there by the build that imported the row,
so every comparison of this machine with the bucket leaves them out too: `caselist status` does not
expect them in the bucket, and `store sync` does not push them.
"""

from __future__ import annotations

import json
import re
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Final

from debate_core.application.caselist.import_service import STORED_CLASSIFICATIONS
from debate_core.application.caselist.manifest import FULL_ARCHIVE_DIRECTORY, MANIFEST_DIRECTORY
from debate_core.application.caselist.pipeline import hold_on_skipped_member
from debate_core.application.errors import DomainError
from debate_core.application.ports.evidence_store import ObjectKey, validate_object_key
from debate_core.application.ports.suppression import (
    PathHoldEntry,
    SuppressionState,
    camp_path_scope,
    disclosure_digest,
)
from debate_core.domain import SHA256_HEX_PATTERN, Sha256Hex
from debate_core.domain.caselist import CASELIST_SLUG_PATTERN

__all__ = [
    "CASELIST_SOURCE_PREFIX",
    "MANIFEST_SUFFIX",
    "OPENEV",
    "OPENEV_SOURCE_PREFIX",
    "InvalidPublishTarget",
    "LocalSnapshot",
    "ManifestAction",
    "ManifestSource",
    "PlannedSource",
    "PublishPlan",
    "SnapshotPlan",
    "SourceAction",
    "UnreadableManifest",
    "build_publish_plan",
    "digest_of_local_blob_key",
    "full_archive_date",
    "full_archive_snapshot",
    "HeldRow",
    "held_only_digests",
    "held_rows",
    "held_skipped_rows",
    "local_blob_key",
    "manifest_prefix",
    "remote_source_prefix",
    "skipped_paths_in_manifest",
    "snapshot_date",
    "snapshot_manifest_key",
    "snapshot_of_manifest_key",
    "source_key",
    "source_prefix",
    "sources_in_manifest",
    "stored_rows_in_manifest",
    "suppressed_rows",
    "validate_publish_target",
]

CASELIST_SOURCE_PREFIX: Final = "raw/caselist"
"""Where disclosed caselist sources live: `raw/caselist/<slug>/sha256/…`."""

OPENEV_SOURCE_PREFIX: Final = "raw/openev"
"""Where OpenEv camp files live: `raw/openev/<year>/sha256/…`."""

OPENEV: Final = "openev"
"""The name `--caselist` takes for camp files, and the manifest directory they are filed under."""

MANIFEST_SUFFIX: Final = ".jsonl"

FULL_ARCHIVE_SNAPSHOT_PREFIX: Final = f"{FULL_ARCHIVE_DIRECTORY}/"
"""What a complete archive's snapshot name starts with: `full/2026-10-06`."""

_BLOB_SEGMENT: Final = "sha256"
_DIGEST = re.compile(SHA256_HEX_PATTERN)
_CASELIST_SLUG = re.compile(CASELIST_SLUG_PATTERN)
#: `2026-ndi`: a four-digit topic year, then the camp or event, as `manifests/openev/` files them.
_OPENEV_SNAPSHOT = re.compile(r"^(?P<year>[0-9]{4})-[a-z0-9][a-z0-9-]*$")
#: The classifications whose rows name a source this snapshot holds, as manifest strings.
_STORED: Final = frozenset(str(classification) for classification in STORED_CLASSIFICATIONS)


class InvalidPublishTarget(DomainError):
    """`--caselist` or `--snapshot` does not name something that can be published.

    A deterministic refusal the operator fixes by retyping, never a guess: a slug that is not
    `hsld26`-shaped would be a key prefix nobody else can find.
    """


class UnreadableManifest(DomainError):
    """A local manifest could not be read as the importer writes one.

    Names the manifest's key and the line number, never the line: a manifest row carries a school,
    a team code and a filename, and this message may reach a log (`caselist-data-use.md` rule 4).
    """

    def __init__(self, key: ObjectKey, line_number: int, reason: str) -> None:
        self.key = key
        self.line_number = line_number
        super().__init__(f"{key} line {line_number} is not a usable manifest row: {reason}")


# ------------------------------------------------------------------------------------------------
# Key layout
# ------------------------------------------------------------------------------------------------


def full_archive_snapshot(archive_date: date) -> str:
    """The snapshot name of a caselist's complete archive of `archive_date`: `full/2026-10-06`."""
    return f"{FULL_ARCHIVE_SNAPSHOT_PREFIX}{archive_date.isoformat()}"


def full_archive_date(snapshot: str) -> date | None:
    """The date a complete archive's snapshot name states, or `None` for any other name."""
    if not snapshot.startswith(FULL_ARCHIVE_SNAPSHOT_PREFIX):
        return None
    stated = snapshot[len(FULL_ARCHIVE_SNAPSHOT_PREFIX) :]
    try:
        parsed = date.fromisoformat(stated)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == stated else None


def validate_publish_target(caselist: str, snapshot: str | None = None) -> None:
    """Refuse a caselist or snapshot name that has no place in the layout.

    A caselist is a slug (`hsld26`) or `openev`. A caselist's snapshot is the archive's date as
    `YYYY-MM-DD`, or `full/YYYY-MM-DD` for its complete archive of that date; a camp snapshot is
    `<year>-<event>`, as `manifests/openev/` names it.
    """
    if caselist != OPENEV and _CASELIST_SLUG.match(caselist) is None:
        raise InvalidPublishTarget(
            f"--caselist must be a caselist slug such as hsld26, or {OPENEV!r}; got {caselist!r}"
        )
    if snapshot is None:
        return
    if caselist == OPENEV:
        if _OPENEV_SNAPSHOT.match(snapshot) is None:
            raise InvalidPublishTarget(
                f"an OpenEv snapshot is <year>-<event>, such as 2026-ndi; got {snapshot!r}"
            )
        return
    if full_archive_date(snapshot) is not None:
        return
    try:
        parsed = date.fromisoformat(snapshot)
    except ValueError:
        parsed = None
    if parsed is None or parsed.isoformat() != snapshot:
        raise InvalidPublishTarget(
            "a caselist snapshot is a date as YYYY-MM-DD, or full/YYYY-MM-DD for its complete "
            f"archive; got {snapshot!r}"
        )


def source_prefix(caselist: str, snapshot: str) -> str:
    """The prefix one snapshot's sources are filed under, without a trailing `/`.

    `raw/caselist/hsld26` for a caselist; `raw/openev/2026` for a camp snapshot, whose year is the
    first part of its name. Only OpenEv needs the snapshot to answer.
    """
    validate_publish_target(caselist, snapshot)
    if caselist == OPENEV:
        return f"{OPENEV_SOURCE_PREFIX}/{snapshot[:4]}"
    return f"{CASELIST_SOURCE_PREFIX}/{caselist}"


def remote_source_prefix(caselist: str) -> str:
    """The one prefix that lists every source of `caselist` in the bucket, with a trailing `/`.

    `raw/caselist/hsld26/` for a caselist and `raw/openev/` for camp files, whose years are below
    it. Every such prefix is under `raw/`, which is one of the documented prefixes the operator's
    `ListBucket` grant is scoped to.
    """
    validate_publish_target(caselist)
    if caselist == OPENEV:
        return f"{OPENEV_SOURCE_PREFIX}/"
    return f"{CASELIST_SOURCE_PREFIX}/{caselist}/"


def source_key(caselist: str, snapshot: str, digest: Sha256Hex) -> ObjectKey:
    """The bucket key of one source: `<source prefix>/sha256/ab/cd/<digest>`."""
    return validate_object_key(f"{source_prefix(caselist, snapshot)}/{local_blob_key(digest)}")


def local_blob_key(digest: Sha256Hex) -> ObjectKey:
    """The key of one blob in the local blob tree: `sha256/ab/cd/<digest>`.

    The same tail the bucket key ends in, which is what makes a local key and a remote key two
    spellings of one object.
    """
    if _DIGEST.match(digest) is None:
        raise ValueError(f"not a lowercase SHA-256 hex digest: {digest!r}")
    return f"{_BLOB_SEGMENT}/{digest[0:2]}/{digest[2:4]}/{digest}"


def digest_of_local_blob_key(key: ObjectKey) -> Sha256Hex | None:
    """The digest a local blob key states, or `None` for a key that is not one."""
    parts = key.split("/")
    if len(parts) != 4 or parts[0] != _BLOB_SEGMENT:
        return None
    digest = parts[3]
    if _DIGEST.match(digest) is None or parts[1] != digest[0:2] or parts[2] != digest[2:4]:
        return None
    return digest


def manifest_prefix(caselist: str) -> str:
    """`manifests/<caselist>/`: where every manifest of one caselist is filed."""
    validate_publish_target(caselist)
    return f"{MANIFEST_DIRECTORY}/{caselist}/"


def snapshot_manifest_key(caselist: str, snapshot: str) -> ObjectKey:
    """`manifests/hsld26/2026-09-15.jsonl`, or `manifests/openev/2026-ndi.jsonl` for camp files."""
    validate_publish_target(caselist, snapshot)
    return validate_object_key(f"{manifest_prefix(caselist)}{snapshot}{MANIFEST_SUFFIX}")


def snapshot_of_manifest_key(caselist: str, key: ObjectKey, *, full_archives: bool = False) -> str | None:
    """The snapshot a manifest key names, or `None` when `key` is not one of `caselist`'s manifests.

    Keys that are not a manifest of this caselist — a nested path, another suffix, a name that is
    not a snapshot — are `None` rather than errors, because a listing is allowed to hold things
    this module does not own (`manifests/_suppression/` is t07's).

    A complete archive's manifest (`manifests/<caselist>/full/<date>.jsonl`) is one of those nested
    paths, and is `None` too unless `full_archives` is set, when it is `full/<date>`. The default is
    the weekly series alone, so that the readers written for it — the sync's latest snapshot, the
    staleness check, the first-seen count — never see a complete archive (`v1-e34-t04`).
    """
    prefix = manifest_prefix(caselist)
    if not key.startswith(prefix) or not key.endswith(MANIFEST_SUFFIX):
        return None
    snapshot = key[len(prefix) : -len(MANIFEST_SUFFIX)]
    if caselist != OPENEV and full_archive_date(snapshot) is not None:
        return snapshot if full_archives else None
    if "/" in snapshot:
        return None
    try:
        validate_publish_target(caselist, snapshot)
    except InvalidPublishTarget:
        return None
    return snapshot


# ------------------------------------------------------------------------------------------------
# Reading a manifest
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True, order=True)
class ManifestSource:
    """One distinct source a snapshot holds: its digest and its size in bytes."""

    sha256: Sha256Hex
    size: int


def sources_in_manifest(key: ObjectKey, lines: Iterable[str]) -> tuple[ManifestSource, ...]:
    """The distinct sources one manifest's rows name, sorted by digest.

    Only member rows with a stored classification count; see this module's docstring. Raises
    :class:`UnreadableManifest` for a line that is not JSON, a member row with a stored
    classification and no usable digest or size, or one digest given two different sizes — any of
    which means the file is not what the importer wrote, and publishing it would publish a
    provenance record that disagrees with the bytes it describes.
    """
    sizes: dict[Sha256Hex, int] = {}
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            raise UnreadableManifest(key, number, "not JSON") from None
        if not isinstance(row, dict):
            raise UnreadableManifest(key, number, "not a JSON object")
        fields: dict[str, object] = row  # pyright: ignore[reportUnknownVariableType]
        if fields.get("kind") != "member" or fields.get("classification") not in _STORED:
            continue
        digest = fields.get("sha256")
        size = fields.get("byte_size")
        if not isinstance(digest, str) or _DIGEST.match(digest) is None:
            raise UnreadableManifest(key, number, "a stored member with no SHA-256 digest")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise UnreadableManifest(key, number, "a stored member with no byte size")
        if sizes.setdefault(digest, size) != size:
            raise UnreadableManifest(key, number, f"digest {digest} is given two different sizes")
    return tuple(sorted(ManifestSource(sha256=digest, size=size) for digest, size in sizes.items()))


def stored_rows_in_manifest(lines: Iterable[str]) -> tuple[tuple[Sha256Hex, str], ...]:
    """`(sha256, path)` of every member row with a stored classification, in file order.

    What the suppression check reads: a disclosure-scoped entry stops one path's row, not the
    digest. Assumes `lines` already passed :func:`sources_in_manifest`, which refuses a malformed
    manifest; a row this cannot read is simply not a stored row.
    """
    rows: list[tuple[Sha256Hex, str]] = []
    for line in lines:
        try:
            row = json.loads(line) if line.strip() else None
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        fields: dict[str, object] = row  # pyright: ignore[reportUnknownVariableType]
        digest, path = fields.get("sha256"), fields.get("path")
        if (
            fields.get("kind") == "member"
            and fields.get("classification") in _STORED
            and isinstance(digest, str)
            and isinstance(path, str)
        ):
            rows.append((digest, path))
    return tuple(rows)


def skipped_paths_in_manifest(lines: Iterable[str]) -> tuple[str, ...]:
    """The path of every skipped member row, in file order (`v1-e30-t22`).

    What the held-path check of a member that was never read looks at: a symbolic link at a removed
    file's path still names it. Like :func:`stored_rows_in_manifest`, a row this cannot read is not
    one.
    """
    paths: list[str] = []
    for line in lines:
        try:
            row = json.loads(line) if line.strip() else None
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        fields: dict[str, object] = row  # pyright: ignore[reportUnknownVariableType]
        path = fields.get("path")
        if fields.get("kind") == "member" and fields.get("skip_reason") is not None and isinstance(path, str):
            paths.append(path)
    return tuple(paths)


@dataclass(frozen=True, slots=True)
class LocalSnapshot:
    """One snapshot as this machine holds it: its manifest and the sources that manifest names."""

    caselist: str
    snapshot: str
    sources: tuple[ManifestSource, ...]
    manifest_size: int
    stored_rows: tuple[tuple[Sha256Hex, str], ...] = ()
    """`(sha256, path)` of every stored member row, for the suppression check. Never logged."""
    skipped_paths: tuple[str, ...] = ()
    """The path of every skipped member row, for the held-path check (`v1-e30-t22`). Never logged."""

    @property
    def manifest_key(self) -> ObjectKey:
        return snapshot_manifest_key(self.caselist, self.snapshot)


def suppressed_rows(local: LocalSnapshot, suppression: SuppressionState) -> tuple[Sha256Hex, ...]:
    """The digests of the local manifest's stored rows that `suppression` stops, sorted, once each.

    Checked by digest and by each row's own disclosure: for a caselist manifest the row's caselist
    path, so one team's withdrawn copy of a shared file is caught and the other team's row is not;
    for a camp release the row's camp path (`v1-e30-t14`), so a camp path withdrawn from this
    release is caught and another release's row of the same bytes is not.
    """
    scope = camp_path_scope(local.snapshot) if local.caselist == OPENEV else local.caselist
    stopped = {
        digest
        for digest, path in local.stored_rows
        if suppression.suppresses(digest, disclosure=disclosure_digest(scope, path))
    }
    return tuple(sorted(stopped))


@dataclass(frozen=True, slots=True, order=True)
class HeldRow:
    """A stored manifest row at a path a removal holds: its digest, and the request holding the path."""

    sha256: Sha256Hex
    request_id: str


def held_rows(local: LocalSnapshot, suppression: SuppressionState) -> tuple[HeldRow, ...]:
    """The local manifest's stored rows at a path a removal holds, sorted by digest, once each.

    A row is held when a removal holds its caselist path and the snapshot is dated after the removed
    file first appeared there: the rule the importer refuses an upload by
    (:meth:`~debate_core.application.ports.suppression.SuppressionState.path_hold`, `v1-e30-t13`).
    A row the list already stops is :func:`suppressed_rows`', not this. A camp release's rows are at
    no caselist path, so none is held. Where one digest is held at two paths, the first hold found
    names it.
    """
    held: dict[Sha256Hex, str] = {}
    for digest, hold in _holds_of_stored_rows(local, suppression):
        if hold is not None:
            held.setdefault(digest, hold.request_id)
    return tuple(HeldRow(sha256=digest, request_id=held[digest]) for digest in sorted(held))


def held_only_digests(local: LocalSnapshot, suppression: SuppressionState) -> frozenset[Sha256Hex]:
    """The digests held rows of the local manifest name and none of its other rows does (`v1-e30-t22`).

    Not uploaded: see "Bytes only held rows name are not uploaded" in the module docstring. A row the
    list stops by its disclosure is another row here, as it is not held: the bytes of a withdrawn
    copy are uploaded as they always were.
    """
    held: set[Sha256Hex] = set()
    unheld: set[Sha256Hex] = set()
    for digest, hold in _holds_of_stored_rows(local, suppression):
        (held if hold is not None else unheld).add(digest)
    return frozenset(held - unheld)


def held_skipped_rows(local: LocalSnapshot, suppression: SuppressionState) -> tuple[str, ...]:
    """The request holding the path of each skipped member row at a held path, sorted (`v1-e30-t22`).

    One per row: the rows this build's importer withholds
    (:func:`~debate_core.application.caselist.pipeline.hold_on_skipped_member`), which an earlier
    build wrote. A camp release's rows are at no caselist path, so none is held.
    """
    snapshot = snapshot_date(local.snapshot)
    caselist = None if local.caselist == OPENEV else local.caselist
    holds = (
        hold_on_skipped_member(suppression, caselist=caselist, path=path, snapshot=snapshot)
        for path in local.skipped_paths
    )
    return tuple(sorted(hold.request_id for hold in holds if hold is not None))


def _holds_of_stored_rows(
    local: LocalSnapshot, suppression: SuppressionState
) -> list[tuple[Sha256Hex, PathHoldEntry | None]]:
    """Each stored row's digest and the hold on its path, `None` where none covers it.

    The list's own rows come first: a row the list stops is :func:`suppressed_rows`', never held. A
    camp release's rows are at no caselist path, and a snapshot of no date is covered by no hold.
    """
    snapshot = snapshot_date(local.snapshot)
    if local.caselist == OPENEV or snapshot is None:
        return [(digest, None) for digest, _ in local.stored_rows]
    return [
        (
            digest,
            None
            if suppression.suppresses(digest, disclosure=disclosure_digest(local.caselist, path))
            else suppression.path_hold(caselist=local.caselist, path=path, snapshot=snapshot),
        )
        for digest, path in local.stored_rows
    ]


def snapshot_date(snapshot: str) -> date | None:
    """The date a caselist snapshot's name states: a weekly's `2026-09-15`, a complete archive's
    `full/2026-10-06`. `None` for any other name, such as a camp release's."""
    full = full_archive_date(snapshot)
    if full is not None:
        return full
    try:
        parsed = date.fromisoformat(snapshot)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == snapshot else None


# ------------------------------------------------------------------------------------------------
# The plan
# ------------------------------------------------------------------------------------------------


class SourceAction(StrEnum):
    """What the plan decided about one source of one snapshot. The table above is the rule."""

    UPLOAD = "upload"
    VERIFY = "verify"
    UPLOADED_EARLIER = "uploaded_earlier"
    MISMATCHED = "mismatched"
    MISSING_LOCALLY = "missing_locally"
    SUPPRESSED = "suppressed"


class ManifestAction(StrEnum):
    """What the plan decided about a snapshot's manifest."""

    UPLOAD = "upload"
    """Absent from the bucket."""

    VERIFY = "verify"
    """Present; the publisher compares digests and re-uploads only if they differ."""


#: Source actions that stop a snapshot's manifest from being written, whatever else happens.
BLOCKING_SOURCE_ACTIONS: Final = frozenset({SourceAction.MISMATCHED, SourceAction.MISSING_LOCALLY})


@dataclass(frozen=True, slots=True)
class PlannedSource:
    """One source of one snapshot and what the plan decided about it."""

    sha256: Sha256Hex
    size: int
    key: ObjectKey
    """The bucket key: `raw/caselist/<slug>/sha256/ab/cd/<digest>`."""
    action: SourceAction
    remote_size: int | None = None
    """What the bucket's listing gave as this key's size, when the key was listed."""


@dataclass(frozen=True, slots=True)
class SnapshotPlan:
    """Everything publishing one snapshot involves: its sources, then its manifest."""

    caselist: str
    snapshot: str
    sources: tuple[PlannedSource, ...]
    manifest_key: ObjectKey
    manifest_size: int
    manifest_action: ManifestAction
    suppressed_rows: tuple[Sha256Hex, ...] = ()
    """Digests of stored rows in the local manifest the suppression list stops; any withholds it."""
    held_rows: tuple[HeldRow, ...] = ()
    """Stored rows at a path a removal holds (`v1-e30-t21`); any withholds it, as a suppressed row does."""
    held_back: tuple[Sha256Hex, ...] = ()
    """Digests only held rows name, sorted: left out of :attr:`sources`, so never uploaded (`v1-e30-t22`)."""
    held_skipped_rows: tuple[str, ...] = ()
    """The request holding the path of each skipped member row at a held path, sorted (`v1-e30-t23`);
    any withholds the manifest, as a held stored row does."""

    @property
    def withholding_rows(self) -> tuple[str, ...]:
        """Every row that withholds the manifest, sorted, once each.

        A stored row by its digest, suppressed or held; a skipped member's row at a held path, which
        has no digest, by the request holding the path (`v1-e30-t23`). The publisher's rule: any
        withholds the manifest. `caselist status` asks this same property for the hint it gives a
        manifest mismatch (`v1-e30-t19`), so a change to what withholds a manifest is made here, and
        the hint follows it.
        """
        return tuple(
            sorted({*self.suppressed_rows, *(row.sha256 for row in self.held_rows), *self.held_skipped_rows})
        )

    def of(self, *actions: SourceAction) -> tuple[PlannedSource, ...]:
        wanted = set(actions)
        return tuple(source for source in self.sources if source.action in wanted)

    @property
    def uploads(self) -> tuple[PlannedSource, ...]:
        return self.of(SourceAction.UPLOAD)

    @property
    def blocked(self) -> tuple[PlannedSource, ...]:
        """Sources whose plan already says the manifest cannot be written."""
        return self.of(*BLOCKING_SOURCE_ACTIONS)

    @property
    def counts(self) -> dict[str, int]:
        """One count per source action, always every key, for the `--json` payload."""
        return {action.value: len(self.of(action)) for action in SourceAction}


@dataclass(frozen=True, slots=True)
class PublishPlan:
    """What publishing some snapshots of one caselist would do, in the order it would do it."""

    caselist: str
    snapshots: tuple[SnapshotPlan, ...]

    @property
    def uploads(self) -> tuple[PlannedSource, ...]:
        """Every source upload the plan would make, each distinct key once."""
        return tuple(source for snapshot in self.snapshots for source in snapshot.uploads)

    @property
    def bytes_to_upload(self) -> int:
        return sum(source.size for source in self.uploads)


def build_publish_plan(
    caselist: str,
    snapshots: Sequence[LocalSnapshot],
    *,
    local_blobs: Collection[Sha256Hex],
    remote: Mapping[ObjectKey, int],
    suppression: SuppressionState,
) -> PublishPlan:
    """Work out what publishing `snapshots` would do, from a listing of each side.

    Args:
        caselist: The caselist every snapshot belongs to.
        snapshots: The snapshots to publish. Planned in snapshot order whatever order they arrive
            in, so an earlier week's upload is the one a later week waits on.
        local_blobs: Every digest the local blob store holds.
        remote: The bucket's listing under this caselist's source and manifest prefixes, key to
            size. A listing states no digests (`debate_core.application.ports.evidence_store`), so
            a present object is `verify`, never skipped outright.
        suppression: The removal suppression list as the publisher read it. Required: a publish
            cannot be planned without it.
    """
    validate_publish_target(caselist)
    planned_uploads: set[ObjectKey] = set()
    plans: list[SnapshotPlan] = []
    for local in sorted(snapshots, key=lambda snapshot: snapshot.snapshot):
        if local.caselist != caselist:
            raise ValueError(f"snapshot {local.snapshot} belongs to {local.caselist}, not {caselist}")
        sources: list[PlannedSource] = []
        held_back = held_only_digests(local, suppression)
        for source in local.sources:
            if source.sha256 in held_back:
                continue
            key = source_key(caselist, local.snapshot, source.sha256)
            action = _source_action(source, key, local_blobs, remote, suppression, planned_uploads)
            if action is SourceAction.UPLOAD:
                planned_uploads.add(key)
            sources.append(
                PlannedSource(
                    sha256=source.sha256,
                    size=source.size,
                    key=key,
                    action=action,
                    remote_size=remote.get(key),
                )
            )
        manifest_key = local.manifest_key
        plans.append(
            SnapshotPlan(
                caselist=caselist,
                snapshot=local.snapshot,
                sources=tuple(sources),
                manifest_key=manifest_key,
                manifest_size=local.manifest_size,
                manifest_action=ManifestAction.VERIFY if manifest_key in remote else ManifestAction.UPLOAD,
                suppressed_rows=suppressed_rows(local, suppression),
                held_rows=held_rows(local, suppression),
                held_back=tuple(sorted(held_back)),
                held_skipped_rows=held_skipped_rows(local, suppression),
            )
        )
    return PublishPlan(caselist=caselist, snapshots=tuple(plans))


def _source_action(
    source: ManifestSource,
    key: ObjectKey,
    local_blobs: Collection[Sha256Hex],
    remote: Mapping[ObjectKey, int],
    suppression: SuppressionState,
    planned_uploads: Collection[ObjectKey],
) -> SourceAction:
    if suppression.suppresses_source(source.sha256):
        return SourceAction.SUPPRESSED
    if key in remote:
        # The key is the digest, so a listed object of another size under it holds other bytes.
        return SourceAction.VERIFY if remote[key] == source.size else SourceAction.MISMATCHED
    if key in planned_uploads:
        return SourceAction.UPLOADED_EARLIER
    if source.sha256 not in local_blobs:
        return SourceAction.MISSING_LOCALLY
    return SourceAction.UPLOAD

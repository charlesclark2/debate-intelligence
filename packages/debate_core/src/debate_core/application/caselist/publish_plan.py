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
    manifests/openev/2026-ndi.jsonl                 one camp's files for one year

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
| (on the suppression list) | `suppressed` | nothing, and it does not hold the manifest back |

The manifest is always last, and its action is `upload` or `verify` on the same rule. Whether it is
written is not the plan's decision but the publisher's, made after every source has an outcome.
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
from debate_core.application.caselist.manifest import MANIFEST_DIRECTORY
from debate_core.application.errors import DomainError
from debate_core.application.ports.evidence_store import ObjectKey, validate_object_key
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
    "local_blob_key",
    "manifest_prefix",
    "remote_source_prefix",
    "snapshot_manifest_key",
    "snapshot_of_manifest_key",
    "source_key",
    "source_prefix",
    "sources_in_manifest",
    "validate_publish_target",
]

CASELIST_SOURCE_PREFIX: Final = "raw/caselist"
"""Where disclosed caselist sources live: `raw/caselist/<slug>/sha256/…`."""

OPENEV_SOURCE_PREFIX: Final = "raw/openev"
"""Where OpenEv camp files live: `raw/openev/<year>/sha256/…`."""

OPENEV: Final = "openev"
"""The name `--caselist` takes for camp files, and the manifest directory they are filed under."""

MANIFEST_SUFFIX: Final = ".jsonl"

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


def validate_publish_target(caselist: str, snapshot: str | None = None) -> None:
    """Refuse a caselist or snapshot name that has no place in the layout.

    A caselist is a slug (`hsld26`) or `openev`. A caselist's snapshot is the archive's date as
    `YYYY-MM-DD`; a camp snapshot is `<year>-<event>`, as `manifests/openev/` names it.
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
    try:
        parsed = date.fromisoformat(snapshot)
    except ValueError:
        parsed = None
    if parsed is None or parsed.isoformat() != snapshot:
        raise InvalidPublishTarget(f"a caselist snapshot is a date as YYYY-MM-DD; got {snapshot!r}")


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


def snapshot_of_manifest_key(caselist: str, key: ObjectKey) -> str | None:
    """The snapshot a manifest key names, or `None` when `key` is not one of `caselist`'s manifests.

    Keys that are not a manifest of this caselist — a nested path, another suffix, a name that is
    not a snapshot — are `None` rather than errors, because a listing is allowed to hold things
    this module does not own (`manifests/_suppression/` is t07's).
    """
    prefix = manifest_prefix(caselist)
    if not key.startswith(prefix) or not key.endswith(MANIFEST_SUFFIX):
        return None
    snapshot = key[len(prefix) : -len(MANIFEST_SUFFIX)]
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


@dataclass(frozen=True, slots=True)
class LocalSnapshot:
    """One snapshot as this machine holds it: its manifest and the sources that manifest names."""

    caselist: str
    snapshot: str
    sources: tuple[ManifestSource, ...]
    manifest_size: int

    @property
    def manifest_key(self) -> ObjectKey:
        return snapshot_manifest_key(self.caselist, self.snapshot)


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
    suppressed: Collection[Sha256Hex] = frozenset(),
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
        suppressed: Digests on the removal suppression list. The list and the check that fills it
            are `v1-e30-t07`'s; this only honours what it is given.
    """
    validate_publish_target(caselist)
    planned_uploads: set[ObjectKey] = set()
    plans: list[SnapshotPlan] = []
    for local in sorted(snapshots, key=lambda snapshot: snapshot.snapshot):
        if local.caselist != caselist:
            raise ValueError(f"snapshot {local.snapshot} belongs to {local.caselist}, not {caselist}")
        sources: list[PlannedSource] = []
        for source in local.sources:
            key = source_key(caselist, local.snapshot, source.sha256)
            action = _source_action(source, key, local_blobs, remote, suppressed, planned_uploads)
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
            )
        )
    return PublishPlan(caselist=caselist, snapshots=tuple(plans))


def _source_action(
    source: ManifestSource,
    key: ObjectKey,
    local_blobs: Collection[Sha256Hex],
    remote: Mapping[ObjectKey, int],
    suppressed: Collection[Sha256Hex],
    planned_uploads: Collection[ObjectKey],
) -> SourceAction:
    if source.sha256 in suppressed:
        return SourceAction.SUPPRESSED
    if key in remote:
        # The key is the digest, so a listed object of another size under it holds other bytes.
        return SourceAction.VERIFY if remote[key] == source.size else SourceAction.MISMATCHED
    if key in planned_uploads:
        return SourceAction.UPLOADED_EARLIER
    if source.sha256 not in local_blobs:
        return SourceAction.MISSING_LOCALLY
    return SourceAction.UPLOAD

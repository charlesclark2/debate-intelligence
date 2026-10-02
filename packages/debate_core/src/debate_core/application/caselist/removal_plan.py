"""What a removal would do, worked out in full before anything is deleted.

`debate-research caselist remove` is a dry run unless told otherwise, and the dry run is this
module: given a selector — one file by its sha256, or one team's every disclosure across every
snapshot — it reads this machine's records and manifests and the environment's bucket, and
produces a :class:`RemovalPlan` that names every record, manifest row, file, object and version the
removal would delete, every source it would keep because someone else holds it too, and every
suppression entry it would append. :class:`~debate_core.application.caselist.removal_service.
CaselistRemovalService` executes exactly that plan — the manifests it writes are the ones planned
here, line for line — so what the operator reads before `--execute` is what happens.

It reads only. The dry run needs nothing but the everyday evidence profile: bucket listings, heads
and manifest downloads. Counting *noncurrent versions* needs `s3:ListBucketVersions`, which the
everyday profile does not have today; the plan then says the versions were not counted
(:attr:`RemovalPlan.versions_counted`), and `--execute` — which lists and deletes them with the
takedown profile — reports how many it deleted.

## Three things can happen to a source

`REMOVE`
    The file goes everywhere: its blob, its source document, every disclosure and camp-file record
    of it, every manifest row naming it, every `raw/` and `parsed/` object for it and every version
    of each. Its sha256 is suppressed as a whole source. What happens to a file only the requester
    holds, and to a shared file with `--include-shared`.
`WITHDRAW`
    A `--team` removal of a file another team or a camp file also holds, without
    `--include-shared`. Only the requester's disclosures go: their records, their manifest rows,
    and — when no other team in the same caselist holds it — that caselist's `raw/` and `parsed/`
    copies. The blob and the other holders' records stay. Each of the requester's paths is
    suppressed as one disclosure (:func:`~debate_core.application.ports.suppression.
    disclosure_digest`), so the next cumulative archive cannot record it as theirs again.
`SKIP_SHARED`
    A `--source` removal of a shared file without `--include-shared`. Nothing is deleted: there is
    no requesting team to withdraw it from, and deleting it would take it from the other holders
    (`docs/policies/caselist-data-use.md`, "Shared content").

## What "the team's" means

The archive's own structure: a path whose two directories above the file are the selector's
school and team code (with `__MACOSX/` mirror paths folded onto the real ones), exactly as the path
parser reads a disclosure (:mod:`debate_core.application.caselist.path_parser`). A `--team` removal
drops every row of that team's in every manifest of the caselist — files, junk entries, `REMOVED`
rows — because each one names the team.

## The sync's inbox

The plan also lists every file in the download inbox (`caselist pull`'s, `v1-e30-t09`) that holds
something the list will stop once this plan's entries are appended, and whether it is deleted or
rewritten without the removed entries: see :mod:`debate_core.application.caselist.inbox_purge`. An
archive still waiting to be imported is never deleted.

## Re-running

A removal that failed part-way is finished by running the same command again. The local records
are deleted last, so a re-run resolves the same sources; and a source whose suppression this
request already appended is planned again whatever else has gone, so nothing it left in the bucket
is forgotten.

## What it never puts in a log or an error

The selector's school and team code. They appear in the plan (the operator's own terminal, which
the policy allows) and nowhere this module logs or raises.
"""

from __future__ import annotations

import json
import re
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Final

from debate_core.application.caselist.evidence_listing import LocalEvidence, local_file
from debate_core.application.caselist.inbox_purge import (
    CaselistInbox,
    InboxFilePlan,
    InboxTeamFilesLeft,
    plan_inbox,
)
from debate_core.application.caselist.manifest import MANIFEST_DIRECTORY, render_rows
from debate_core.application.caselist.openev_manifest import openev_release_name, summary_row
from debate_core.application.caselist.pipeline import (
    STORED_CLASSIFICATIONS,
    Classification,
    withheld_skipped_paths,
)
from debate_core.application.caselist.publish_plan import (
    CASELIST_SOURCE_PREFIX,
    OPENEV,
    OPENEV_SOURCE_PREFIX,
    local_blob_key,
    manifest_prefix,
    snapshot_of_manifest_key,
)
from debate_core.application.errors import DomainError, StoreAccessDenied
from debate_core.application.ports.caselist import CaselistRepository
from debate_core.application.ports.evidence_store import EvidenceObjectStore, ObjectKey
from debate_core.application.ports.evidence_versions import EvidenceVersionStore, ObjectVersion
from debate_core.application.ports.providers import Clock
from debate_core.application.ports.suppression import (
    REMOVAL_REASONS,
    REQUEST_ID_PATTERN,
    ReasonCode,
    RemovalSelectorKind,
    SuppressionAction,
    SuppressionEntry,
    SuppressionList,
    SuppressionState,
    disclosure_digest,
)
from debate_core.domain import SHA256_HEX_PATTERN, Sha256Hex
from debate_core.domain.caselist import CASELIST_SLUG_PATTERN, CampFile, Disclosure, Event

__all__ = [
    "Disposition",
    "InvalidRemovalRequest",
    "ManifestRewrite",
    "ObjectKind",
    "ObjectRemoval",
    "PlannedSource",
    "RemovalPlan",
    "RemovalPlanner",
    "RemovalSelector",
    "Side",
    "SourceSelector",
    "TeamSelector",
    "parse_team_selector",
]

_DIGEST = re.compile(SHA256_HEX_PATTERN)
_CASELIST_SLUG = re.compile(CASELIST_SLUG_PATTERN)
_MACOS_METADATA_DIRECTORY: Final = "__MACOSX"
_PAGE: Final = 500


class InvalidRemovalRequest(DomainError):
    """The selector or the reason cannot be acted on. Says what is wrong, never what was typed."""


# ------------------------------------------------------------------------------------------------
# Selectors
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SourceSelector:
    """`--source <sha256>`: one file, wherever and however many times it was disclosed."""

    sha256: Sha256Hex

    def __post_init__(self) -> None:
        if _DIGEST.match(self.sha256) is None:
            raise InvalidRemovalRequest("--source must be a file's sha256: 64 lowercase hex characters")

    @property
    def kind(self) -> RemovalSelectorKind:
        return RemovalSelectorKind.SOURCE


@dataclass(frozen=True, slots=True)
class TeamSelector:
    """`--team <caselist>/<school>/<team>`: everything one team disclosed to one caselist."""

    caselist: str
    school: str
    team_code: str

    @property
    def kind(self) -> RemovalSelectorKind:
        return RemovalSelectorKind.TEAM

    def holds(self, caselist: str, path: str) -> bool:
        """Whether `path` in `caselist` is one of this team's: its two directories are the team's."""
        return caselist == self.caselist and team_of_path(path) == (self.school, self.team_code)

    def __str__(self) -> str:
        return f"{self.caselist}/{self.school}/{self.team_code}"


type RemovalSelector = SourceSelector | TeamSelector


def parse_team_selector(text: str) -> TeamSelector:
    """`hsld26/Maple Grove/QX` → a :class:`TeamSelector`. The message on refusal never quotes `text`."""
    parts = text.split("/")
    if len(parts) != 3 or not all(part.strip() for part in parts):
        raise InvalidRemovalRequest(
            "--team must be <caselist>/<school>/<team code>, as the archive's directories spell them"
        )
    caselist, school, team_code = parts[0].strip(), parts[1].strip(), parts[2].strip()
    if _CASELIST_SLUG.match(caselist) is None:
        raise InvalidRemovalRequest("--team must start with a caselist slug such as hsld26")
    return TeamSelector(caselist=caselist, school=school, team_code=team_code)


def team_of_path(path: str) -> tuple[str, str] | None:
    """The (school, team code) directories a member path is filed under, as the path parser reads them."""
    parts = path.split("/")
    if parts[0] == _MACOS_METADATA_DIRECTORY:
        parts = parts[1:]
    directories = parts[:-1]
    if len(directories) < 2:
        return None
    return directories[-2].strip(), directories[-1].strip()


# ------------------------------------------------------------------------------------------------
# The plan
# ------------------------------------------------------------------------------------------------


class Disposition(StrEnum):
    """What a removal does to one source. See the module docstring."""

    REMOVE = "remove"
    WITHDRAW = "withdraw"
    SKIP_SHARED = "skip_shared"


class Side(StrEnum):
    """Which copy of the evidence store a planned deletion or rewrite is on."""

    LOCAL = "local"
    BUCKET = "bucket"


class ObjectKind(StrEnum):
    BLOB = "blob"
    """This machine's copy of the bytes: `blobs/sha256/ab/cd/<digest>`."""
    RAW = "raw"
    """The bucket's copy: `raw/caselist/<slug>/…` or `raw/openev/<year>/…`."""
    PARSED = "parsed"
    """Cards derived from it, under `parsed/` locally and in the bucket (E31)."""


@dataclass(frozen=True, slots=True)
class DisclosureRef:
    """One disclosure record a removal deletes. Identifying; shown to the operator, never logged."""

    caselist: str
    snapshot: date
    source_path: str
    school: str
    team_code: str
    tournament: str | None = None
    round_label: str | None = None
    """The round as disclosed (`Round 1`, `Semis`): what the confirmation to the requester names."""


@dataclass(frozen=True, slots=True)
class CampFileRef:
    """One camp-file record a removal deletes."""

    year: int
    event: Event
    camp: str
    file_title: str


@dataclass(frozen=True, slots=True)
class PlannedSource:
    """One source and what the removal does to it."""

    sha256: Sha256Hex
    disposition: Disposition
    byte_size: int | None
    source_format: str | None
    disclosures: tuple[DisclosureRef, ...]
    """The disclosure records on this machine the removal deletes."""
    camp_files: tuple[CampFileRef, ...]
    """The camp-file records on this machine the removal deletes."""
    requester_paths: tuple[tuple[str, str], ...]
    """`(caselist, path)` of the requesting team's copies, from records and manifests alike."""
    other_teams: int
    """Other teams that disclosed these bytes, before the removal."""
    camp_file_holders: int
    """OpenEv camp files holding these bytes, before the removal."""
    kept_in: tuple[str, ...]
    """Caselists where another team still holds a withdrawn file, so its copy there stays."""
    delete_source_record: bool
    local_blob: bool
    """Whether this machine holds the blob and the removal deletes it."""
    suppression: tuple[SuppressionEntry, ...]
    """The entries this removal appends for it (none when they are already on the list)."""
    already_suppressed: bool = False
    """The list already carries this removal's suppression of it: a re-run finishing the job."""

    @property
    def shared(self) -> bool:
        return self.other_teams > 0 or self.camp_file_holders > 0


@dataclass(frozen=True, slots=True)
class ManifestRewrite:
    """One manifest the removal rewrites without the dropped rows."""

    key: ObjectKey
    side: Side
    rows_dropped: int
    member_rows_kept: int
    lines: tuple[str, ...]
    """The whole rewritten manifest, summary last: what the executor writes, byte for byte."""
    versions: int | None = None
    """For the bucket's copy: how many versions it has now, all of which the removal replaces."""


@dataclass(frozen=True, slots=True)
class ObjectRemoval:
    """One object a removal deletes, with every version of it the plan could see."""

    key: ObjectKey
    side: Side
    kind: ObjectKind
    sha256: Sha256Hex
    versions: tuple[ObjectVersion, ...] | None
    """Every version the store listed, or `None` when this credential cannot list versions."""


@dataclass(frozen=True, slots=True)
class RemovalPlan:
    """Everything a removal would do, in the order the executor does it."""

    selector: RemovalSelector
    request_id: str
    reason: ReasonCode
    include_shared: bool
    environment: str
    bucket: str
    recorded_at: datetime
    sources: tuple[PlannedSource, ...]
    manifests: tuple[ManifestRewrite, ...]
    objects: tuple[ObjectRemoval, ...]
    versions_counted: bool
    affected_caselists: tuple[str, ...] = ()
    """Caselists whose manifests the removal touched, for the noncurrent-version sweep."""
    suppression_after: SuppressionState = field(default_factory=SuppressionState)
    """The list as it will read once this plan's entries are appended."""
    inbox: tuple[InboxFilePlan, ...] = ()
    """Every file in the sync's inbox holding something that list stops, and what happens to it."""
    inbox_team_files_left: tuple[InboxTeamFilesLeft, ...] = ()
    """Archives waiting to be imported that hold files of the team the store has never seen."""
    inbox_directory: str = ""
    inbox_exists: bool = False
    """Whether that directory exists. Prod, which does not pull, has none; nothing is then created."""

    def of(self, disposition: Disposition) -> tuple[PlannedSource, ...]:
        return tuple(source for source in self.sources if source.disposition is disposition)

    @property
    def suppression_entries(self) -> tuple[SuppressionEntry, ...]:
        return tuple(entry for source in self.sources for entry in source.suppression)

    @property
    def local_records(self) -> int:
        return sum(
            len(source.disclosures) + len(source.camp_files) + int(source.delete_source_record)
            for source in self.sources
        )

    def objects_on(self, side: Side) -> tuple[ObjectRemoval, ...]:
        return tuple(planned for planned in self.objects if planned.side is side)

    def manifests_on(self, side: Side) -> tuple[ManifestRewrite, ...]:
        return tuple(rewrite for rewrite in self.manifests if rewrite.side is side)

    @property
    def nothing_to_do(self) -> bool:
        return (
            not self.local_records
            and not self.manifests
            and not self.objects
            and not self.suppression_entries
            and not any(source.local_blob for source in self.sources)
            and not self.inbox
        )


# ------------------------------------------------------------------------------------------------
# The planner
# ------------------------------------------------------------------------------------------------


@dataclass(slots=True)
class _ManifestCopy:
    """One copy of one manifest — this machine's or the bucket's — read into rows."""

    key: ObjectKey
    caselist: str
    side: Side
    rows: list[tuple[str, dict[str, object]]]
    """Every member row with the exact line it was read from, in file order."""
    summary: dict[str, object] | None

    @property
    def release(self) -> str:
        """The snapshot or OpenEv release the key names: `2026-09-15`, `2026-policy`."""
        return self.key.rsplit("/", 1)[-1].removesuffix(".jsonl")


@dataclass(slots=True)
class _Holdings:
    """Who holds one digest before the removal: teams, and OpenEv releases (one camp file each)."""

    teams: dict[tuple[str, str, str], set[str]] = field(default_factory=lambda: {})
    """Each holding team as (caselist, school, team code), and the paths it holds the bytes at."""
    releases: set[str] = field(default_factory=lambda: set())
    """OpenEv releases holding the bytes: `2026-policy`. A camp file is keyed by digest and release."""


class _BucketIndex:
    """One listing per prefix, kept for the whole plan, so sixty sources cost one walk each, not sixty."""

    def __init__(self, remote: EvidenceObjectStore, versions: EvidenceVersionStore) -> None:
        self._remote = remote
        self._versions = versions
        self._current: dict[str, set[str]] = {}
        self._listed: dict[str, dict[str, list[ObjectVersion]] | None] = {}

    async def current(self, prefix: str) -> set[str]:
        if prefix not in self._current:
            self._current[prefix] = {info.key for info in await self._remote.list_objects(prefix)}
        return self._current[prefix]

    async def versions(self, prefix: str) -> dict[str, list[ObjectVersion]] | None:
        """Versions by key under `prefix`, or `None` when this credential may not list versions."""
        if prefix not in self._listed:
            try:
                listed = await self._versions.list_versions(prefix)
            except StoreAccessDenied:
                self._listed[prefix] = None
            else:
                by_key: dict[str, list[ObjectVersion]] = {}
                for version in listed:
                    by_key.setdefault(version.key, []).append(version)
                self._listed[prefix] = by_key
        return self._listed[prefix]


class RemovalPlanner:
    """Builds a :class:`RemovalPlan`. Reads only; holds only the everyday credential's stores.

    Args:
        caselists: This machine's caselist records.
        local: This machine's manifests (and blobs, as named objects).
        local_blobs: This machine's blob tree, as the takedown sees it (one version per file).
        local_parsed: This machine's parsed-card tree (E31), likewise. Empty until E31 writes one.
        remote: The environment's bucket through the everyday profile: listings, heads, manifests.
        remote_versions: The bucket's versions through whichever credential the composition root
            gives it; a denial means "not counted", not failure.
        inbox: The sync's download inbox in this environment. Required, with no default, so that no
            removal can be built that forgets it.
        suppression: The suppression list (local and bucket copies).
        clock: The time entries are recorded at.
        environment: `dev` or `prod`, for the plan and the log.
        bucket: The bucket's name, for the plan.
    """

    def __init__(
        self,
        *,
        caselists: CaselistRepository,
        local: LocalEvidence,
        local_blobs: EvidenceVersionStore,
        local_parsed: EvidenceVersionStore,
        remote: EvidenceObjectStore,
        remote_versions: EvidenceVersionStore,
        inbox: CaselistInbox,
        suppression: SuppressionList,
        clock: Clock,
        environment: str,
        bucket: str,
    ) -> None:
        self._caselists = caselists
        self._local = local
        self._local_blobs = local_blobs
        self._local_parsed = local_parsed
        self._remote = remote
        self._remote_versions = remote_versions
        self._inbox = inbox
        self._suppression = suppression
        self._clock = clock
        self._environment = environment
        self._bucket = bucket

    async def plan(
        self,
        selector: RemovalSelector,
        *,
        request_id: str,
        reason: ReasonCode,
        include_shared: bool = False,
    ) -> RemovalPlan:
        """Work out everything removing `selector` would do. Writes nothing anywhere."""
        if reason not in REMOVAL_REASONS:
            raise InvalidRemovalRequest(f"--reason must be one of {', '.join(sorted(REMOVAL_REASONS))}")
        if re.match(REQUEST_ID_PATTERN, request_id) is None:
            raise InvalidRemovalRequest(
                "--request must be the register id, RM-<year>-<number>, e.g. RM-2026-01"
            )
        recorded_at = self._clock.now()
        existing = await self._suppression.entries()
        state = SuppressionState.from_entries(existing)
        caselists = await self._known_caselists()
        copies = [copy for caselist in caselists for copy in await self._manifest_copies(caselist)]

        sources: list[PlannedSource] = []
        for digest in sorted(await self._candidates(selector, copies, state, request_id)):
            sources.append(
                await self._plan_source(
                    digest,
                    await self._holdings(digest, copies),
                    selector,
                    include_shared=include_shared,
                    state=state,
                    request_id=request_id,
                    reason=reason,
                    recorded_at=recorded_at,
                )
            )

        after = SuppressionState.from_entries(
            [*existing, *(entry for source in sources for entry in source.suppression)]
        )
        removed = {source.sha256 for source in sources if source.disposition is Disposition.REMOVE}
        withdrawn_paths = {
            path
            for source in sources
            if source.disposition is Disposition.WITHDRAW
            for path in source.requester_paths
        }
        index = _BucketIndex(self._remote, self._remote_versions)
        rewrites = await self._manifest_rewrites(copies, selector, removed, withdrawn_paths, after, index)
        objects, counted = await self._objects(sources, caselists, copies, index)
        inbox, team_files_left = plan_inbox(
            self._inbox,
            suppression=after,
            imported_weeks=_imported_weeks(copies),
            imported_openev_downloads=_imported_openev_downloads(copies),
            team=(selector.caselist, selector.school, selector.team_code)
            if isinstance(selector, TeamSelector)
            else None,
        )
        return RemovalPlan(
            selector=selector,
            request_id=request_id,
            reason=reason,
            include_shared=include_shared,
            environment=self._environment,
            bucket=self._bucket,
            recorded_at=recorded_at,
            sources=tuple(sources),
            manifests=tuple(rewrites),
            objects=tuple(objects),
            versions_counted=counted
            and all(rewrite.versions is not None for rewrite in rewrites if rewrite.side is Side.BUCKET),
            affected_caselists=_affected_caselists(sources, caselists),
            suppression_after=after,
            inbox=inbox,
            inbox_team_files_left=team_files_left,
            inbox_directory=str(self._inbox.directory),
            inbox_exists=self._inbox.directory.is_dir(),
        )

    # --------------------------------------------------------------------------------------
    # Reading
    # --------------------------------------------------------------------------------------

    async def _known_caselists(self) -> list[str]:
        """Every caselist either copy of the store holds a manifest for, and OpenEv.

        All of them, whatever the selector: whether a team's file is shared depends on who else
        disclosed it, in any caselist, and a file is in the bucket under every caselist that did.
        """
        found: set[str] = {OPENEV}
        for store in (self._local.objects, self._remote):
            for info in await store.list_objects(f"{MANIFEST_DIRECTORY}/"):
                parts = info.key.split("/")
                if len(parts) == 3 and (parts[1] == OPENEV or _CASELIST_SLUG.match(parts[1])):
                    found.add(parts[1])
        return sorted(found)

    async def _manifest_copies(self, caselist: str) -> list[_ManifestCopy]:
        prefix = manifest_prefix(caselist)
        local_keys = {
            info.key
            for info in await self._local.objects.list_objects(prefix)
            if snapshot_of_manifest_key(caselist, info.key)
        }
        remote_keys = {
            info.key
            for info in await self._remote.list_objects(prefix)
            if snapshot_of_manifest_key(caselist, info.key)
        }
        copies: list[_ManifestCopy] = []
        for key in sorted(local_keys | remote_keys):
            local_lines: tuple[str, ...] | None = None
            local_digest: str | None = None
            if key in local_keys:
                async with local_file(self._local.objects, self._local.object_path_for, key) as path:
                    local_lines = tuple(path.read_text(encoding="utf-8").splitlines())
                local_digest = (await self._local.objects.head(key)).sha256
                copies.append(_copy(key, caselist, Side.LOCAL, local_lines))
            if key in remote_keys:
                remote_digest = (await self._remote.head(key)).sha256
                if local_lines is not None and remote_digest is not None and remote_digest == local_digest:
                    remote_lines = local_lines
                else:
                    remote_lines = await self._download_lines(key)
                copies.append(_copy(key, caselist, Side.BUCKET, remote_lines))
        return copies

    async def _download_lines(self, key: ObjectKey) -> tuple[str, ...]:
        with tempfile.TemporaryDirectory(prefix="debate-removal-") as directory:
            staged = Path(directory) / "manifest.jsonl"
            await self._remote.get_file(key, staged)
            return tuple(staged.read_text(encoding="utf-8").splitlines())

    async def _candidates(
        self,
        selector: RemovalSelector,
        copies: Sequence[_ManifestCopy],
        state: SuppressionState,
        request_id: str,
    ) -> set[str]:
        if isinstance(selector, SourceSelector):
            return {selector.sha256}
        found = {disclosure.source_sha256 for disclosure in await self._team_disclosures(selector)}
        for copy in copies:
            for _, row in copy.rows:
                digest, path = row.get("sha256"), row.get("path")
                if isinstance(digest, str) and isinstance(path, str) and selector.holds(copy.caselist, path):
                    found.add(digest)
        # A re-run after a partial failure: whatever this request already suppressed is still its.
        for digest, latest in state.latest.items():
            if latest.action is SuppressionAction.SUPPRESS and latest.request_id == request_id:
                found.add(digest)
        return found

    async def _team_disclosures(self, selector: TeamSelector) -> list[Disclosure]:
        """By school, then by the team's directory as well as its recorded code.

        A team-code directory the domain refused is recorded as `UNKNOWN` but still sits under the
        team's own directory, which is what the operator types.
        """
        return [
            disclosure
            async for disclosure in _all_disclosures(
                self._caselists, caselist=selector.caselist, school=selector.school
            )
            if disclosure.team_code == selector.team_code
            or selector.holds(disclosure.caselist, disclosure.source_path)
        ]

    async def _holdings(self, digest: str, copies: Sequence[_ManifestCopy]) -> _Holdings:
        holdings = _Holdings()
        async for disclosure in _all_disclosures(self._caselists, source_sha256=digest):
            team = team_of_path(disclosure.source_path) or (disclosure.school, disclosure.team_code)
            holdings.teams.setdefault((disclosure.caselist, *team), set()).add(disclosure.source_path)
        for camp_file in await _all_camp_files(self._caselists, digest):
            holdings.releases.add(openev_release_name(camp_file.year, camp_file.event))
        for copy in copies:
            for _, row in copy.rows:
                path = row.get("path")
                if (
                    row.get("sha256") != digest
                    or row.get("classification") not in _STORED
                    or not isinstance(path, str)
                ):
                    continue
                if copy.caselist == OPENEV:
                    holdings.releases.add(copy.release)
                elif (team := team_of_path(path)) is not None:
                    holdings.teams.setdefault((copy.caselist, *team), set()).add(path)
        return holdings

    # --------------------------------------------------------------------------------------
    # One source
    # --------------------------------------------------------------------------------------

    async def _plan_source(
        self,
        digest: str,
        holdings: _Holdings,
        selector: RemovalSelector,
        *,
        include_shared: bool,
        state: SuppressionState,
        request_id: str,
        reason: ReasonCode,
        recorded_at: datetime,
    ) -> PlannedSource:
        source = await self._caselists.find_source(digest)
        disclosures = [
            disclosure async for disclosure in _all_disclosures(self._caselists, source_sha256=digest)
        ]
        camp_files = await _all_camp_files(self._caselists, digest)
        latest = state.latest.get(digest)
        finishing = (
            latest is not None
            and latest.action is SuppressionAction.SUPPRESS
            and latest.request_id == request_id
        )

        if isinstance(selector, TeamSelector):
            requester = (selector.caselist, selector.school, selector.team_code)
            others = len(set(holdings.teams) - {requester})
            shared = others > 0 or bool(holdings.releases)
        else:
            others = len(holdings.teams)
            shared = len(holdings.teams) + len(holdings.releases) > 1

        if (state.suppresses_source(digest) and finishing) or not shared or include_shared:
            disposition = Disposition.REMOVE
        elif isinstance(selector, TeamSelector):
            disposition = Disposition.WITHDRAW
        else:
            disposition = Disposition.SKIP_SHARED

        requester_paths: tuple[tuple[str, str], ...] = ()
        entries: list[SuppressionEntry] = []
        dropped: list[DisclosureRef] = []
        dropped_camp: list[CampFileRef] = []
        local_blob = False
        if disposition is Disposition.REMOVE:
            dropped = [_disclosure_ref(disclosure) for disclosure in disclosures]
            dropped_camp = [_camp_ref(camp_file) for camp_file in camp_files]
            if not state.suppresses_source(digest):
                entries.append(_suppression(digest, None, recorded_at, reason, request_id))
            local_blob = bool(await self._local_blobs.list_versions(local_blob_key(digest)))
        elif disposition is Disposition.WITHDRAW:
            assert isinstance(selector, TeamSelector)
            dropped = [
                _disclosure_ref(disclosure)
                for disclosure in disclosures
                if selector.holds(disclosure.caselist, disclosure.source_path)
            ]
            paths = holdings.teams.get((selector.caselist, selector.school, selector.team_code), set())
            withdrawn = sorted(paths | {ref.source_path for ref in dropped})
            requester_paths = tuple((selector.caselist, path) for path in withdrawn)
            for path in withdrawn:
                digest_of_path = disclosure_digest(selector.caselist, path)
                if not state.suppresses(digest, disclosure=digest_of_path):
                    entries.append(_suppression(digest, digest_of_path, recorded_at, reason, request_id))

        return PlannedSource(
            sha256=digest,
            disposition=disposition,
            byte_size=source.byte_size if source is not None else None,
            source_format=str(source.source_format) if source is not None else None,
            disclosures=tuple(sorted(dropped, key=lambda ref: (ref.caselist, ref.snapshot, ref.source_path))),
            camp_files=tuple(sorted(dropped_camp, key=lambda ref: (ref.year, ref.event, ref.file_title))),
            requester_paths=requester_paths,
            other_teams=others,
            camp_file_holders=len(holdings.releases),
            kept_in=tuple(
                sorted(
                    {
                        caselist
                        for caselist, school, team_code in holdings.teams
                        if not (
                            isinstance(selector, TeamSelector)
                            and (school, team_code) == (selector.school, selector.team_code)
                        )
                    }
                )
            )
            if disposition is Disposition.WITHDRAW
            else (),
            delete_source_record=disposition is Disposition.REMOVE and source is not None,
            local_blob=local_blob,
            suppression=tuple(entries),
            already_suppressed=finishing,
        )

    # --------------------------------------------------------------------------------------
    # Manifests
    # --------------------------------------------------------------------------------------

    async def _manifest_rewrites(
        self,
        copies: Sequence[_ManifestCopy],
        selector: RemovalSelector,
        removed: set[str],
        withdrawn_paths: set[tuple[str, str]],
        after: SuppressionState,
        index: _BucketIndex,
    ) -> list[ManifestRewrite]:
        # Paths that ever held a removed file, per caselist: a REMOVED row at one of them names it too.
        held_removed: dict[str, set[str]] = {}
        for copy in copies:
            for _, row in copy.rows:
                path = row.get("path")
                if isinstance(path, str) and row.get("sha256") in removed:
                    held_removed.setdefault(copy.caselist, set()).add(path)

        rewrites: list[ManifestRewrite] = []
        for copy in copies:
            if copy.summary is None:
                continue
            dropped = _rows_to_drop(
                copy, selector, removed, withdrawn_paths, held_removed.get(copy.caselist, set()), after
            )
            if not dropped:
                continue
            versions: int | None = None
            if copy.side is Side.BUCKET:
                listed = await index.versions(copy.key)
                versions = None if listed is None else len(listed.get(copy.key, []))
            rewrites.append(
                ManifestRewrite(
                    key=copy.key,
                    side=copy.side,
                    rows_dropped=len(dropped),
                    member_rows_kept=len(copy.rows) - len(dropped),
                    lines=_rewritten(copy, dropped, after),
                    versions=versions,
                )
            )
        return rewrites

    # --------------------------------------------------------------------------------------
    # Objects
    # --------------------------------------------------------------------------------------

    async def _objects(
        self,
        sources: Sequence[PlannedSource],
        caselists: Sequence[str],
        copies: Sequence[_ManifestCopy],
        index: _BucketIndex,
    ) -> tuple[list[ObjectRemoval], bool]:
        counted = True
        objects: list[ObjectRemoval] = []
        disclosing = [name for name in caselists if name != OPENEV]
        openev_years = sorted({copy.release[:4] for copy in copies if copy.caselist == OPENEV})
        for source in sources:
            digest = source.sha256
            if source.disposition is Disposition.SKIP_SHARED:
                continue
            if source.disposition is Disposition.REMOVE:
                raw_prefixes = [f"{CASELIST_SOURCE_PREFIX}/{name}/" for name in disclosing]
                raw_prefixes += [f"{OPENEV_SOURCE_PREFIX}/{year}/" for year in openev_years]
                parsed_caselists = [*disclosing, OPENEV]
                if source.local_blob:
                    blob = await self._local_blobs.list_versions(local_blob_key(digest))
                    objects.append(
                        ObjectRemoval(
                            key=local_blob_key(digest),
                            side=Side.LOCAL,
                            kind=ObjectKind.BLOB,
                            sha256=digest,
                            versions=blob,
                        )
                    )
            else:
                # Withdrawn: a caselist's own copy goes only when no other team there still holds it,
                # by this machine's records or by any manifest on either side.
                parsed_caselists = sorted({name for name, _ in source.requester_paths} - set(source.kept_in))
                raw_prefixes = [f"{CASELIST_SOURCE_PREFIX}/{name}/" for name in parsed_caselists]

            for prefix in raw_prefixes:
                key = f"{prefix}{local_blob_key(digest)}"
                listed = await index.versions(prefix)
                versions = None if listed is None else tuple(listed.get(key, []))
                counted = counted and listed is not None
                if key in await index.current(prefix) or versions:
                    objects.append(
                        ObjectRemoval(
                            key=key, side=Side.BUCKET, kind=ObjectKind.RAW, sha256=digest, versions=versions
                        )
                    )
            for caselist in parsed_caselists:
                prefix = f"parsed/{caselist}/"
                listed = await index.versions(prefix)
                counted = counted and listed is not None
                keys = {key for key in await index.current(prefix) if _names_digest(key, digest)}
                keys |= {key for key in (listed or {}) if _names_digest(key, digest)}
                objects.extend(
                    ObjectRemoval(
                        key=key,
                        side=Side.BUCKET,
                        kind=ObjectKind.PARSED,
                        sha256=digest,
                        versions=None if listed is None else tuple(listed.get(key, [])),
                    )
                    for key in sorted(keys)
                )
                objects.extend(
                    ObjectRemoval(
                        key=version.key,
                        side=Side.LOCAL,
                        kind=ObjectKind.PARSED,
                        sha256=digest,
                        versions=(version,),
                    )
                    for version in await self._local_parsed.list_versions(f"{caselist}/")
                    if _names_digest(version.key, digest)
                )
        return objects, counted


# ------------------------------------------------------------------------------------------------
# Manifest rows
# ------------------------------------------------------------------------------------------------

_STORED: Final = frozenset(str(classification) for classification in STORED_CLASSIFICATIONS)


def _copy(key: ObjectKey, caselist: str, side: Side, lines: tuple[str, ...]) -> _ManifestCopy:
    rows: list[tuple[str, dict[str, object]]] = []
    summary: dict[str, object] | None = None
    for line in lines:
        if not line.strip():
            continue
        parsed: object = json.loads(line)
        if not isinstance(parsed, dict):
            continue
        row: dict[str, object] = parsed  # pyright: ignore[reportUnknownVariableType]
        if row.get("kind") == "summary":
            summary = row
        elif row.get("kind") == "member":
            rows.append((line, row))
    return _ManifestCopy(key=key, caselist=caselist, side=side, rows=rows, summary=summary)


def _rows_to_drop(
    copy: _ManifestCopy,
    selector: RemovalSelector,
    removed: set[str],
    withdrawn_paths: set[tuple[str, str]],
    held_removed: set[str],
    after: SuppressionState,
) -> set[int]:
    """Indexes of the member rows a rewrite leaves out. See the module docstring for each rule."""
    scope = None if copy.caselist == OPENEV else copy.caselist
    dropped = {
        index
        for index, (_, row) in enumerate(copy.rows)
        if _dropped(row, copy.caselist, scope, selector, removed, withdrawn_paths, held_removed, after)
    }
    real = {
        str(row["path"]): index in dropped
        for index, (_, row) in enumerate(copy.rows)
        if isinstance(row.get("path"), str)
        and row.get("skip_reason") is None
        and row.get("sha256") is not None
    }
    skipped = [
        str(row["path"])
        for _, row in copy.rows
        if row.get("skip_reason") is not None and isinstance(row.get("path"), str)
    ]
    shadowing = withheld_skipped_paths(real, skipped)
    dropped |= {index for index, (_, row) in enumerate(copy.rows) if row.get("path") in shadowing}
    return dropped


def _dropped(
    row: Mapping[str, object],
    caselist: str,
    scope: str | None,
    selector: RemovalSelector,
    removed: set[str],
    withdrawn_paths: set[tuple[str, str]],
    held_removed: set[str],
    after: SuppressionState,
) -> bool:
    """Whether one member row goes, before the junk that shadows dropped files is added."""
    path, digest = row.get("path"), row.get("sha256")
    if not isinstance(path, str):
        return False
    if isinstance(selector, TeamSelector) and selector.holds(caselist, path):
        return True  # every row of the requesting team's, junk and REMOVED rows included
    if digest in removed or (caselist, path) in withdrawn_paths:
        return True
    if row.get("classification") == str(Classification.REMOVED) and path in held_removed:
        return True  # "this path's file was taken down", where the file was the removed one
    # Anything else the list already stops: a row an earlier removal never reached.
    disclosure = disclosure_digest(scope, path) if scope is not None else None
    return isinstance(digest, str) and after.suppresses(digest, disclosure=disclosure)


def _rewritten(copy: _ManifestCopy, dropped: set[int], after: SuppressionState) -> tuple[str, ...]:
    """The manifest without the dropped rows: every kept row byte for byte, then a recounted summary.

    The kept rows go through :func:`~debate_core.application.caselist.manifest.render_rows` too,
    for its suppression check only: a rewrite that kept a row the list stops is refused before it
    is written.
    """
    assert copy.summary is not None
    kept = [row for index, (_, row) in enumerate(copy.rows) if index not in dropped]
    gone = [row for index, (_, row) in enumerate(copy.rows) if index in dropped]
    scope = None if copy.caselist == OPENEV else copy.caselist
    render_rows(kept, suppression=after, disclosure_scope=scope)
    if copy.caselist == OPENEV:
        summary = _recounted_openev_summary(copy.summary, kept, gone)
    else:
        summary = _recounted_caselist_summary(copy.summary, kept, gone)
    (summary_line,) = render_rows([summary], suppression=after, disclosure_scope=scope)
    return (*(line for index, (line, _) in enumerate(copy.rows) if index not in dropped), summary_line)


def _recounted_caselist_summary(
    old: Mapping[str, object], kept: Sequence[Mapping[str, object]], gone: Sequence[Mapping[str, object]]
) -> dict[str, object]:
    """The summary of a caselist manifest after rows are dropped.

    `members` and `skipped` describe the archive and do not change: a dropped member is still one
    the archive held. Each dropped member's classification moves to `SUPPRESSED`, as the next import
    would count it; a dropped `REMOVED` row is not a member and simply goes. `distinct_sha256` is
    recounted from the stored rows that remain.
    """
    counts = _counts(old.get("classifications"))
    for row in gone:
        classification = row.get("classification")
        if not isinstance(classification, str):
            continue
        counts[classification] = counts.get(classification, 0) - 1
        if classification != str(Classification.REMOVED):
            counts[str(Classification.SUPPRESSED)] = counts.get(str(Classification.SUPPRESSED), 0) + 1
    return {
        **old,
        "classifications": {name: counts[name] for name in sorted(counts) if counts[name] > 0},
        "distinct_sha256": len(
            {
                row.get("sha256")
                for row in kept
                if row.get("classification") in _STORED and isinstance(row.get("sha256"), str)
            }
        ),
    }


def _recounted_openev_summary(
    old: Mapping[str, object], kept: Sequence[Mapping[str, object]], gone: Sequence[Mapping[str, object]]
) -> dict[str, object]:
    """An OpenEv release summary, counted from the kept rows as the importer counts it."""
    previously = _counts(old.get("classifications")).get(str(Classification.SUPPRESSED), 0)
    year, event = old.get("year"), old.get("event")
    if not isinstance(year, int) or not isinstance(event, str):
        raise DomainError("an OpenEv manifest's summary row names no year or event; it cannot be rewritten")
    return summary_row(
        list(kept),
        year=year,
        event=Event(event),
        suppressed=previously + sum(1 for row in gone if isinstance(row.get("sha256"), str)),
    )


def _counts(raw: object) -> dict[str, int]:
    counts: dict[str, int] = {}
    if isinstance(raw, dict):
        for name, count in raw.items():  # pyright: ignore[reportUnknownVariableType]
            if isinstance(name, str) and isinstance(count, int):
                counts[name] = count
    return counts


# ------------------------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------------------------


def _affected_caselists(sources: Sequence[PlannedSource], caselists: Sequence[str]) -> tuple[str, ...]:
    """Caselists whose superseded manifest versions the executor sweeps: every one, if anything goes.

    Not only those this plan rewrites, nor only those this machine's records name: a re-run after a
    run that stopped during the sweep rewrites nothing — the current versions are already clean —
    and a machine with no local copy has no records to name the caselist by. The sweep only reads
    noncurrent versions, which a caselist accumulates one per re-published week at most.
    """
    if not any(source.disposition is not Disposition.SKIP_SHARED for source in sources):
        return ()
    return tuple(sorted(caselists))


def _imported_weeks(copies: Sequence[_ManifestCopy]) -> frozenset[tuple[str, date]]:
    """The weeks this machine holds a manifest for: what the sync calls imported (`_decide_archive`).

    This machine's copies only. The inbox is this machine's, and so is the sync's notion of what it
    has imported; a manifest that is only in the bucket has not been imported here.
    """
    weeks: set[tuple[str, date]] = set()
    for copy in copies:
        if copy.side is Side.LOCAL and copy.caselist != OPENEV:
            try:
                weeks.add((copy.caselist, date.fromisoformat(copy.release)))
            except ValueError:
                continue
    return frozenset(weeks)


def _imported_openev_downloads(copies: Sequence[_ManifestCopy]) -> frozenset[str]:
    """The download digests this machine's OpenEv manifest rows came from (each row's `archive_sha256`)."""
    return frozenset(
        str(row["archive_sha256"])
        for copy in copies
        if copy.side is Side.LOCAL and copy.caselist == OPENEV
        for _, row in copy.rows
        if isinstance(row.get("archive_sha256"), str)
    )


def _names_digest(key: str, digest: str) -> bool:
    """Whether an object key's last segment is this digest, with or without an extension."""
    name = key.rsplit("/", 1)[-1]
    return name == digest or name.startswith(f"{digest}.")


def _disclosure_ref(disclosure: Disclosure) -> DisclosureRef:
    return DisclosureRef(
        caselist=disclosure.caselist,
        snapshot=disclosure.snapshot,
        source_path=disclosure.source_path,
        school=disclosure.school,
        team_code=disclosure.team_code,
        tournament=disclosure.tournament,
        round_label=disclosure.round_label.raw if disclosure.round_label is not None else None,
    )


def _camp_ref(camp_file: CampFile) -> CampFileRef:
    return CampFileRef(
        year=camp_file.year, event=camp_file.event, camp=camp_file.camp, file_title=camp_file.file_title
    )


def _suppression(
    digest: str, disclosure: str | None, recorded_at: datetime, reason: ReasonCode, request_id: str
) -> SuppressionEntry:
    return SuppressionEntry(
        action=SuppressionAction.SUPPRESS,
        sha256=digest,
        disclosure=disclosure,
        recorded_at=recorded_at,
        reason=reason,
        request_id=request_id,
    )


async def _all_disclosures(caselists: CaselistRepository, **filters: object):  # noqa: ANN202 - an async generator
    cursor: str | None = None
    while True:
        page = await caselists.list_disclosures(limit=_PAGE, cursor=cursor, **filters)  # pyright: ignore[reportArgumentType]
        for disclosure in page.items:
            yield disclosure
        if not page.has_more:
            return
        cursor = page.next_cursor


async def _all_camp_files(caselists: CaselistRepository, digest: str) -> list[CampFile]:
    found: list[CampFile] = []
    cursor: str | None = None
    while True:
        page = await caselists.list_camp_files(source_sha256=digest, limit=_PAGE, cursor=cursor)
        found.extend(page.items)
        if not page.has_more:
            return found
        cursor = page.next_cursor

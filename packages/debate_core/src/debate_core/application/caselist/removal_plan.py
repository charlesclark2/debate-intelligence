"""What a removal would do, worked out in full before anything is deleted.

`debate-research caselist remove` is a dry run unless told otherwise, and the dry run is this
module: given a selector — one file by its sha256, or one team's every disclosure across every
snapshot — it reads this machine's records and manifests and the environment's bucket, and
produces a :class:`RemovalPlan` that names every record, manifest row, file, object and version the
removal would delete, every source it would keep because someone else holds it too, and every
suppression entry it would append. :class:`~debate_core.application.caselist.removal_service.
CaselistRemovalService` executes exactly that plan — the manifests it writes are the ones planned
here, line for line — so what the operator reads before `--execute` is what happens.

It reads only. The dry run needs nothing but the everyday evidence profile: bucket listings, heads,
manifest downloads and a listing of object versions. Counting *noncurrent versions* needs
`s3:ListBucketVersions`, which the everyday profile has, read-only, under the prefixes a takedown
removes from (`v1-e29-t06`, applied in dev and prod on 2026-10-08), so the plan gives each object's
version count. In an environment where that grant is not applied the listing is refused, and the
plan then says the versions were not counted (:attr:`RemovalPlan.versions_counted`); everything
else in it is the same. Either way `--execute` lists every version again with the takedown profile,
deletes them, and reports how many it deleted.

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
    disclosure_digest`), so no later archive, weekly or complete, can record it as theirs again.
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

## Later uploads at a removed path

A removal request covers later uploads at the same path (the PM's ruling under `v1-e30-t07`). For a
camp file the sync holds back one that has not been imported yet (`v1-e34-t14`); for a caselist
file the path hold below does. One the store already holds is this module's (`v1-e30-t11`). For
every file the selector names and removes or withdraws, the planner asks every snapshot it reads,
weekly and complete, which other files sit at the paths it takes that file from
(:mod:`~debate_core.application.caselist.removal_path_versions`, which says what "later" and "the
same path" mean, for a caselist and for an OpenEv camp file). A later upload joins the plan
(:attr:`Inclusion.LATER_UPLOAD`) and goes through everything a named file goes through:

* held at no other path, it is `REMOVE`d: blob, records, rows, `raw/` and `parsed/` objects with
  every version, the inbox, and a whole-file suppression;
* held at another live path too, it is `WITHDRAW`n from the removed paths only: those rows and
  disclosure records go and each of those paths is suppressed as one disclosure, while the blob and
  the other path's rows stay. `--include-shared` does not widen this: it is a decision about the
  files the request names;
* a camp file's later upload that another release or a team holds too is `WITHDRAW`n from its camp
  path (`v1-e30-t14`), as a caselist path is: its row in that release goes, and that release's
  camp-file record and its year's `raw/openev/<year>/` copy when nothing else there holds it, and
  one entry stops the file at that row of that release
  (:func:`~debate_core.application.ports.suppression.camp_path_disclosure`). The withdrawal record
  names `openev`. The other release's row, record and objects, and the blob, stay.

Two uploads are at one camp path when their rows say so: each row of a release manifest carries the
OpenEv id it was downloaded as and the SHA-256 of that id's upstream path (`v1-e30-t14`), and this
machine's delivery record says the same for the ids it pulled. The rows are what prod has, since it
never pulls and its manifests are published from dev's data directory; a row from before that task
has neither, and is matched by its name alone until it is re-derived.

An earlier version at the path is listed (:attr:`RemovalPlan.earlier_versions`) and left alone.
`only_named` (`--only-named`) plans the named files alone, for a request that is explicitly about
one version; the later uploads are still listed, as left in place.

A `--team` removal names every file at the team's paths already, earlier and later versions alike
(:meth:`RemovalPlanner._selected`), so it has later uploads only at the *other* holders' paths of a
shared file it removes with `--include-shared`.

## A removed path is held, and the inbox is read as snapshots (`v1-e30-t13`)

The store's manifests show a later upload only once it has been imported. Two more things cover
one that has not:

**The path hold.** A `--source` removal that removes a file whole plans one
:class:`~debate_core.application.ports.suppression.PathHoldEntry` for each caselist path it takes
the file from (:attr:`RemovalPlan.path_holds`), dated by the earliest snapshot that held the file
there. The executor appends them with the suppression entries, before anything is deleted, and
from then on the importer refuses a new sha256 at the path in any later snapshot. None is planned
with `--only-named`, which is a request about one version; for a file the plan withdraws or skips,
which stays with another holder; for a later upload, whose own paths are the removed ones; or by
`--team`, which holds no path and finds a team's later files by running again.

**The download inbox.** Every weekly and complete archive in the inbox is read as a snapshot too
(:func:`~debate_core.application.caselist.inbox_purge.read_inbox`), dated as its name dates it. A
revision waiting there at a removed path is a later upload by the same rule as one in a manifest:
it joins the plan, gets its suppression entry under the request, and the inbox step rewrites or
deletes the archive that holds it. Another path of it in the same archive is a live path, so a
revision two teams uploaded is withdrawn from the removed path only.

**Running the same removal again** finds what arrived since. The removed file's rows are gone by
then, so nothing in a manifest says where it was; its path holds do. For each hold of a file the
selector names, a row or an inbox member at the held path stands in for the removed file there
(:func:`_recorded_paths`), and everything at that path dated later is a later upload as before:
one this build refused at import, which is still in its archive in the inbox, and one an older
build imported, which is in the store.

**An upload refused at import whose archive has gone** (`v1-e30-t23`). Once retention or the
take-out removes the archive, neither the inbox nor the store holds anything at the held path, and
the hold keeps the path only as a digest. The import wrote the upload's sha256 to the held-digest
record beside the path holds (:class:`~debate_core.application.ports.suppression.HeldDigestEntry`),
with the hold's path digest and request. A re-run of that request reads it for the holds of the
files the selector names (:func:`_refused_at_import`), and plans each such digest
(:attr:`Inclusion.HELD_AT_IMPORT`) by the rule a later upload follows: held at no other path, it is
`REMOVE`d and suppressed whole; held at another live path too, it is `WITHDRAW`n from the held path
only, by the path's digest (:attr:`PlannedSource.held_at_import`). A digest the list already stops
at that path is not planned again, and one the inbox or a manifest still shows there is planned as
the later upload it is, with the record's path among those it is taken from.

**A skipped member's row at a held path** goes in every rewrite, the first run's included, for a
snapshot the hold covers (`v1-e30-t22`): a symbolic link named as the removed file, to which every
build before `v1-e30-t22` gave a row. This build's importer withholds it by the same rule
(:func:`~debate_core.application.caselist.pipeline.hold_on_skipped_member`), so a manifest the removal
rewrote and the same archive imported again afterwards leave out the same rows.

## The complete archive

A caselist's complete archive (`v1-e34-t04`) is its own snapshot, with its manifest at
`manifests/<slug>/full/<date>.jsonl` on this machine and in the bucket. Every manifest reader here
asks for it as well as for the weeklies (:meth:`RemovalPlanner._manifest_copies`), so a removal
finds a file only the complete archive holds, counts the complete archive's holders when it asks
whether a file is shared, and rewrites that manifest like a weekly's. Its sources are under the
caselist's own `raw/` prefix, and the executor's sweep of superseded versions lists
`manifests/<slug>/`, which holds `full/` too. The repository holds no disclosure record for it, so
what it says about a team is read from its manifest alone.

## The parsed card store's aggregates

A source parsed by `caselist parse` (`v1-e31-t06`) is in more than its own per-source file: the
caselist's `index.jsonl`, `failures.jsonl` and `occurrences.jsonl` hold rows derived from it, and
from each of its disclosures. Every one of those files, in every version directory of every
caselist the removal removes or withdraws anything from, is planned for deletion with its versions,
here and in the bucket (:attr:`ObjectKind.PARSED_AGGREGATE`). They hold nothing that cannot be
rebuilt, and the next `caselist parse` rebuilds the current directory's without what was removed.

## The sync's inbox

The plan also lists every file in the download inbox (`caselist pull`'s, `v1-e30-t09`) that holds
something the list will stop once this plan's entries are appended, and whether it is deleted or
rewritten without the removed entries: see :mod:`debate_core.application.caselist.inbox_purge`. An
archive still waiting to be imported is never deleted.

## Re-running

A removal that failed part-way is finished by running the same command again. The local records
are deleted last, so a re-run resolves the same sources; and a source whose suppression this
request already appended is planned again whatever else has gone, so nothing it left in the bucket
is forgotten. For `--source` that is a later upload this request suppressed, once the manifest rows
that showed it at the removed path have been rewritten: it is planned again while this machine
still holds a record or the blob of it (:attr:`Inclusion.UNFINISHED`), with or without `--only-named`.

A re-run also reads two records its first run left beside the list and the log (`v1-e30-t19`):

* **The withdrawal record** (`withdrawals.jsonl`, `v1-e30-t16`). A first run that withdrew a shared
  file deleted the records and rows that named the team's paths, and no record anywhere holds a
  path, so the re-run cannot find them. What it needs from them is where each copy was taken from,
  and the record says that by caselist (:attr:`PlannedSource.withdrawn_earlier_from`): that
  caselist's aggregates are planned again, and its copy when no other holder there keeps it, as the
  first run planned them. A `--source` re-run plans a withdrawn later upload again only for a copy
  still in such a caselist, and never removes it whole on the record's account. A withdrawal an
  earlier build made has no record, and nothing of it is planned again.
* **The scopes beside the log** (`v1-e30-t15`): the manifests each earlier run of the request
  rewrote, with the version of the rewrite (:attr:`RemovalPlan.earlier_rewrites`). The sweep takes
  the noncurrent versions of each that are older than its rewrite
  (:mod:`~debate_core.application.caselist.manifest_sweep`), and the dry run counts what the sweep
  will delete (:attr:`RemovalPlan.superseded_versions`), so a plan with a version to sweep is never
  "nothing to do".

## What it never puts in a log or an error

The selector's school and team code. They appear in the plan (the operator's own terminal, which
the policy allows) and nowhere this module logs or raises.
"""

from __future__ import annotations

import json
import re
import tempfile
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Final

from debate_core.application.caselist.evidence_listing import LocalEvidence, local_file
from debate_core.application.caselist.inbox_purge import (
    CaselistInbox,
    InboxFile,
    InboxFileKind,
    InboxFilePlan,
    InboxTeamFilesLeft,
    plan_inbox,
    read_inbox,
)
from debate_core.application.caselist.manifest import MANIFEST_DIRECTORY, read_manifest_file, render_rows
from debate_core.application.caselist.manifest_sweep import swept_manifest_versions
from debate_core.application.caselist.openev_manifest import (
    openev_release_name,
    row_upstream_identity,
    summary_row,
)
from debate_core.application.caselist.pipeline import (
    STORED_CLASSIFICATIONS,
    Classification,
    hold_on_skipped_member,
    withheld_skipped_paths,
)
from debate_core.application.caselist.publish_plan import (
    CASELIST_SOURCE_PREFIX,
    OPENEV,
    OPENEV_SOURCE_PREFIX,
    full_archive_snapshot,
    local_blob_key,
    manifest_prefix,
    snapshot_of_manifest_key,
)
from debate_core.application.caselist.removal_path_versions import (
    PathHolding,
    PathVersion,
    VersionRelation,
    other_versions,
    path_identity,
    snapshot_date,
)
from debate_core.application.caselist.suppression import read_held_digests, read_path_holds, read_withdrawals
from debate_core.application.errors import DomainError, StoreAccessDenied
from debate_core.application.ports.caselist import CaselistRepository
from debate_core.application.ports.caselist_source import openev_id_of_inbox_name
from debate_core.application.ports.evidence_store import EvidenceObjectStore, ObjectKey
from debate_core.application.ports.evidence_versions import EvidenceVersionStore, ObjectVersion
from debate_core.application.ports.parsed_store import AGGREGATE_NAMES
from debate_core.application.ports.providers import Clock
from debate_core.application.ports.suppression import (
    REMOVAL_REASONS,
    REQUEST_ID_PATTERN,
    HeldDigestEntry,
    ManifestRewriteRecord,
    PathHoldEntry,
    ReasonCode,
    RemovalScopeLog,
    RemovalSelectorKind,
    SuppressionAction,
    SuppressionEntry,
    SuppressionList,
    SuppressionState,
    WithdrawalEntry,
    camp_path_disclosure,
    camp_path_scope,
    disclosure_digest,
)
from debate_core.domain import SHA256_HEX_PATTERN, Sha256Hex
from debate_core.domain.caselist import CASELIST_SLUG_PATTERN, CampFile, Disclosure, Event

__all__ = [
    "Disposition",
    "Inclusion",
    "InvalidRemovalRequest",
    "LaterUploadOutcome",
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
    "taken_path",
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


class Inclusion(StrEnum):
    """Why a source is in the plan."""

    NAMED = "named"
    """The selector names it: the `--source` digest, or a file at one of the `--team`'s paths."""
    LATER_UPLOAD = "later_upload"
    """Held at a path the removal takes a named file from, in a later snapshot (`v1-e30-t11`)."""
    UNFINISHED = "unfinished"
    """Suppressed by an earlier run of this request, with something of it still on this machine."""
    HELD_AT_IMPORT = "held_at_import"
    """Refused at import at a path this request holds, and known only from the held-digest record:
    its archive has left the inbox, and the store never took it in (`v1-e30-t23`)."""


class LaterUploadOutcome(StrEnum):
    """What a plan does about one later upload at one removed path."""

    REMOVED = "removed"
    """Held at no other path: it goes everywhere."""
    WITHDRAWN_FROM_THE_PATH = "withdrawn_from_the_path"
    """Another path holds it too: only its rows and records at the removed path go."""
    KEPT_SHARED = "kept_shared"
    """Another holder has it, and this plan takes it from none of its paths: left whole.

    Before `v1-e30-t14` this was every camp file's later upload another holder had too, because a
    camp path could not be withdrawn. A camp path is withdrawn now, so a later upload is never this
    unless the planner finds no path to take it from."""
    LEFT_IN_PLACE = "left_in_place"
    """Not in the plan: `--only-named`."""


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
    PARSED_AGGREGATE = "parsed_aggregate"
    """An index, failures or occurrence file of a caselist the removal touches (`v1-e31-t06`)."""


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
    """The camp-file records on this machine the removal deletes: every one for a file removed
    whole, and for a camp path withdrawn the release's own, when no other row of it holds the file."""
    requester_paths: tuple[tuple[str, str], ...]
    """`(caselist, path)` of the copies a withdrawal takes: the requesting team's, from records and
    manifests alike, or for a later upload the removed paths it is held at. A camp path is
    `("openev", "<release>/<row path>")` (:func:`taken_path`, `v1-e30-t14`), whose
    :func:`~debate_core.application.ports.suppression.disclosure_digest` is the camp path's."""
    other_teams: int
    """Other teams that disclosed these bytes, before the removal: other than the requesting team,
    or for a `--source` removal other than the one team whose file it is. For a later upload, the
    teams holding it at a path the removal does not take it from, less the teams at the paths it
    does: a second path of the same team keeps the bytes, and is no other team (`v1-e30-t16`)."""
    camp_file_holders: int
    """OpenEv camp files holding these bytes before the removal, other than the one removed, as
    teams are counted (a camp file is one release's). For `--team`, every one, since a team is the
    holder removed; for `--source`, every one when a team holds the file, and one fewer when none
    does, so a file only one camp file holds has none (`v1-e30-t16`). For a later upload, the
    releases holding it at a camp path the removal does not take it from."""
    kept_in: tuple[str, ...]
    """Caselists where another holder still has a withdrawn file, so its copy there stays: another
    team for a `--team` withdrawal, and for a later upload any path the removal does not take it
    from, the same team's included; `openev` when another release keeps it (`v1-e30-t14`)."""
    delete_source_record: bool
    local_blob: bool
    """Whether this machine holds the blob and the removal deletes it."""
    suppression: tuple[SuppressionEntry, ...]
    """The entries this removal appends for it (none when they are already on the list)."""
    already_suppressed: bool = False
    """The list already carries this removal's suppression of it: a re-run finishing the job."""
    inclusion: Inclusion = Inclusion.NAMED
    withdrawn_earlier_from: tuple[str, ...] = ()
    """For a file withdrawn, the caselists an earlier run of this request withdrew it from, as the
    withdrawal record says (`v1-e30-t19`). Its first run deleted the records and rows that named the
    paths, so a re-run finds none of them; this is what still says where the copies were taken
    from, and the re-run plans those caselists' copies and aggregates again as the first run did."""

    held_at_import: tuple[tuple[str, Sha256Hex], ...] = ()
    """`(caselist, disclosure digest)` of each held path an import refused these bytes at, as the
    held-digest record says (`v1-e30-t23`), where no row or inbox member gives the path's text. A
    withdrawal takes the file from each of them, by the digest alone."""

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
    only_named: bool = False
    """`--only-named`: the later uploads in :attr:`later_uploads` are listed and left in place."""
    later_uploads: tuple[PathVersion, ...] = ()
    """Every later upload the store holds at a path the removal takes a named file from, one entry
    per path. Each is in :attr:`sources` as well, unless :attr:`only_named`."""
    earlier_versions: tuple[PathVersion, ...] = ()
    """Earlier versions at those paths, and files whose order the snapshot dates cannot give: listed
    for the operator, never included."""
    path_holds: tuple[PathHoldEntry, ...] = ()
    """The path entries this removal appends: one for each caselist path a `--source` removal takes
    a file from whole (`v1-e30-t13`). None with `--only-named`, none for a file withdrawn or
    skipped, and none that is already in force."""
    earlier_rewrites: tuple[ManifestRewriteRecord, ...] = ()
    """Each manifest an earlier run of this request rewrote in the bucket, with the version its
    rewrite is, from the scopes beside the removal log (`v1-e30-t15`). The sweep takes the versions
    of each key older than its rewrite (`v1-e30-t19`; :mod:`~debate_core.application.caselist.
    manifest_sweep`)."""
    superseded_versions: tuple[ObjectVersion, ...] | None = ()
    """The noncurrent manifest versions the execution's sweep would delete, as the dry run's
    credential lists and reads them (`v1-e30-t19`); `None` where it may not, so they were not
    counted. The execution works them out again with the takedown credential."""

    def of(self, disposition: Disposition) -> tuple[PlannedSource, ...]:
        return tuple(source for source in self.sources if source.disposition is disposition)

    def included_as(self, inclusion: Inclusion) -> tuple[PlannedSource, ...]:
        return tuple(source for source in self.sources if source.inclusion is inclusion)

    def source(self, sha256: str) -> PlannedSource | None:
        """What the plan does to one file, or `None` when it is not in the plan."""
        return next((source for source in self.sources if source.sha256 == sha256), None)

    def later_upload_outcome(self, version: PathVersion) -> LaterUploadOutcome:
        """What this plan does about one entry of :attr:`later_uploads`."""
        source = self.source(version.sha256)
        if source is None:
            return LaterUploadOutcome.LEFT_IN_PLACE
        if source.disposition is Disposition.REMOVE:
            return LaterUploadOutcome.REMOVED
        if any(
            taken_path(version.caselist, snapshot, version.path) in source.requester_paths
            for snapshot in version.snapshots or ("",)
        ):
            return LaterUploadOutcome.WITHDRAWN_FROM_THE_PATH
        return LaterUploadOutcome.KEPT_SHARED

    @property
    def later_uploads_added(self) -> int:
        """How many files the plan removes or withdraws only because they are later uploads."""
        return sum(
            1
            for source in self.included_as(Inclusion.LATER_UPLOAD)
            if source.disposition is not Disposition.SKIP_SHARED
        )

    @property
    def later_uploads_found(self) -> int:
        """How many distinct files :attr:`later_uploads` lists, added or not."""
        return len({version.sha256 for version in self.later_uploads})

    @property
    def suppression_entries(self) -> tuple[SuppressionEntry, ...]:
        return tuple(entry for source in self.sources for entry in source.suppression)

    @property
    def withdrawals(self) -> tuple[WithdrawalEntry, ...]:
        """The withdrawal record's entries this removal appends (`v1-e30-t16`).

        One for each suppression entry of one disclosure, naming the caselist it withdraws the copy
        from by its slug: the path it was taken from is `(caselist, path)` in
        :attr:`PlannedSource.requester_paths`, and the entry holds only its digest.
        """
        entries: list[WithdrawalEntry] = []
        for source in self.sources:
            # Every entry of one disclosure is planned for a path it is withdrawn from: by its text,
            # or by its digest alone where an import refused it there (v1-e30-t23).
            caselist_of = {
                disclosure_digest(caselist, path): caselist for caselist, path in source.requester_paths
            } | {disclosure: caselist for caselist, disclosure in source.held_at_import}
            entries += [
                WithdrawalEntry(
                    sha256=entry.sha256,
                    disclosure=entry.disclosure,
                    caselist=caselist_of[entry.disclosure],
                    recorded_at=entry.recorded_at,
                    reason=entry.reason,
                    request_id=self.request_id,
                )
                for entry in source.suppression
                if entry.disclosure is not None
            ]
        return tuple(entries)

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
    def touched_caselists(self) -> tuple[str, ...]:
        """The caselists that hold a file this plan removes or withdraws (`v1-e30-t15`).

        Where a manifest it rewrites is filed, where an object it deletes under `raw/` or `parsed/`
        is named for the file, where a record it deletes was disclosed, and where it withdraws a
        copy from; OpenEv for a camp file. Not every caselist whose aggregates it deletes: a removal
        deletes those of every caselist, and only one that held the file can hold a row of it.
        """
        touched: set[str] = {rewrite.key.split("/")[1] for rewrite in self.manifests}
        for planned in self.objects:
            if planned.side is Side.BUCKET and planned.kind is not ObjectKind.PARSED_AGGREGATE:
                touched.add(_caselist_of_bucket_key(planned.key))
        for source in self.sources:
            if source.disposition is Disposition.SKIP_SHARED:
                continue
            touched.update(ref.caselist for ref in source.disclosures)
            touched.update(caselist for caselist, _ in source.requester_paths)
            touched.update(source.withdrawn_earlier_from)
            if source.camp_files:
                touched.add(OPENEV)
        return tuple(sorted(touched))

    @property
    def nothing_to_do(self) -> bool:
        return (
            not self.local_records
            and not self.manifests
            and not self.objects
            and not self.suppression_entries
            and not self.path_holds
            and not any(source.local_blob for source in self.sources)
            and not self.inbox
            and self.superseded_versions == ()
        )

    async def swept_from(self, versions: EvidenceVersionStore) -> tuple[ObjectVersion, ...]:
        """The noncurrent manifest versions this plan's sweep deletes, as `versions` lists them.

        The dry run asks with the everyday credential, the execution with the takedown's: see
        :mod:`~debate_core.application.caselist.manifest_sweep`. Lists and reads only.
        """
        return await swept_manifest_versions(
            versions,
            caselists=self.affected_caselists,
            rewritten_now={rewrite.key for rewrite in self.manifests_on(Side.BUCKET)},
            earlier_rewrites=self.earlier_rewrites,
            names_removed=self.names_removed,
        )

    def names_removed(self, caselist: str, line: str, key: ObjectKey) -> bool:
        """Whether one manifest line names something this removal took out: what the sweep looks for.

        `key` is the manifest's: a camp release's rows are asked about at their camp path in the
        release the key names (`v1-e30-t14`), as a caselist's are at their caselist path.
        """
        try:
            row: object = json.loads(line)
        except json.JSONDecodeError:
            return False
        if not isinstance(row, dict) or row.get("kind") != "member":  # pyright: ignore[reportUnknownMemberType]
            return False
        fields: dict[str, object] = row  # pyright: ignore[reportUnknownVariableType]
        path, digest = fields.get("path"), fields.get("sha256")
        if (
            isinstance(self.selector, TeamSelector)
            and isinstance(path, str)
            and self.selector.holds(caselist, path)
        ):
            return True
        if isinstance(digest, str):
            release = key.rsplit("/", 1)[-1].removesuffix(".jsonl")
            scope = camp_path_scope(release) if caselist == OPENEV else caselist
            return self.suppression_after.suppresses(
                digest, disclosure=disclosure_digest(scope, path) if isinstance(path, str) else None
            )
        return False


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
        """The snapshot or OpenEv release the key names: `2026-09-15`, `2026-policy`.

        For a complete archive, its date alone; :attr:`full_archive` says which it is.
        """
        return self.key.rsplit("/", 1)[-1].removesuffix(".jsonl")

    @property
    def full_archive(self) -> bool:
        """Whether this is a complete archive's manifest, `manifests/<slug>/full/<date>.jsonl`."""
        return self.caselist != OPENEV and self.key.count("/") == 3

    @property
    def snapshot(self) -> str:
        """The snapshot's own name: `2026-09-15`, `full/2026-09-15`, or a release, `2026-policy`."""
        return full_archive_snapshot(date.fromisoformat(self.release)) if self.full_archive else self.release


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
        suppression: The suppression list (local and bucket copies), with the withdrawal record
            beside it, which a re-run reads for the caselists a copy was withdrawn from (`v1-e30-t19`),
            and the held-digest record, which it reads for the uploads an import refused at a held
            path (`v1-e30-t23`).
        removal_log: The removal log, both copies, for the scopes beside it: the manifests earlier
            runs of the same request rewrote, which the sweep holds their older versions to
            (`v1-e30-t19`). Required, with no default, like the inbox.
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
        removal_log: RemovalScopeLog,
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
        self._removal_log = removal_log
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
        only_named: bool = False,
    ) -> RemovalPlan:
        """Work out everything removing `selector` would do. Writes nothing anywhere.

        With `only_named` the later uploads at the removed paths are listed and left in place:
        see "Later uploads at a removed path" in the module docstring.
        """
        if reason not in REMOVAL_REASONS:
            raise InvalidRemovalRequest(f"--reason must be one of {', '.join(sorted(REMOVAL_REASONS))}")
        if re.match(REQUEST_ID_PATTERN, request_id) is None:
            raise InvalidRemovalRequest(
                "--request must be the register id, RM-<year>-<number>, e.g. RM-2026-01"
            )
        recorded_at = self._clock.now()
        existing = await self._suppression.entries()
        existing_holds = await read_path_holds(self._suppression)
        state = SuppressionState.from_entries(existing, existing_holds)
        # Where this request's earlier runs withdrew a copy from, and what they rewrote (v1-e30-t19).
        recorded = _withdrawn_by_the_request(await read_withdrawals(self._suppression), request_id)
        earlier_rewrites = await self._earlier_rewrites(request_id)
        caselists = await self._known_caselists()
        copies = [copy for caselist in caselists for copy in await self._manifest_copies(caselist)]

        selected = await self._selected(selector, copies)
        named = [
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
            for digest in sorted(selected)
        ]

        # Every other file at the paths the named files are taken from, and when it was held there:
        # in a manifest, or in an archive in the download inbox, imported or not (v1-e30-t13).
        inbox_files = read_inbox(self._inbox)
        held = (*_path_holdings(copies), *_inbox_holdings(inbox_files))
        path_holds = (
            _path_holds(named, held, state, recorded_at=recorded_at, reason=reason, request_id=request_id)
            if isinstance(selector, SourceSelector) and not only_named
            else ()
        )
        # A file this request removed earlier has no row left to say where it was: its holds do.
        holdings = (*held, *_recorded_paths(state, selected, held))
        versions = other_versions(
            holdings,
            _paths_taken(named),
            named=selected,
            # What the rows say (v1-e30-t14), which prod has too, and what this machine pulled.
            upstream_path_digests={**self._inbox.deliveries.upstream_paths(), **_row_upstream_paths(copies)},
        )
        later = tuple(one for one in versions if one.relation is VersionRelation.LATER)
        # What an import refused at a held path, which nothing else may name any more (v1-e30-t23).
        refused = _refused_at_import(
            await read_held_digests(self._suppression), state, named=selected, request_id=request_id
        )
        added: list[PlannedSource] = []
        if not only_named:
            for digest in sorted({one.sha256 for one in later}):
                added.append(
                    await self._plan_other_source(
                        digest,
                        [one for one in later if one.sha256 == digest],
                        holdings,
                        Inclusion.LATER_UPLOAD,
                        state=state,
                        request_id=request_id,
                        reason=reason,
                        recorded_at=recorded_at,
                        refused_at=refused.get(digest, ()),
                    )
                )
            for digest in sorted(set(refused) - selected - {one.sha256 for one in later}):
                if all(state.suppresses(digest, disclosure=disclosure) for _, disclosure in refused[digest]):
                    continue  # listed already: whatever is left of it is an unfinished run's
                added.append(
                    await self._plan_other_source(
                        digest,
                        [],
                        holdings,
                        Inclusion.HELD_AT_IMPORT,
                        state=state,
                        request_id=request_id,
                        reason=reason,
                        recorded_at=recorded_at,
                        refused_at=refused[digest],
                    )
                )

        # A re-run after a partial failure: whatever this request already suppressed is still its.
        index = _BucketIndex(self._remote, self._remote_versions)
        unfinished: list[PlannedSource] = []
        planned = selected | {source.sha256 for source in added}
        for digest in sorted(_suppressed_by(state, request_id) - planned):
            if isinstance(selector, TeamSelector):
                unfinished.append(
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
            elif await self._left_on_this_machine(digest, state, held):
                unfinished.append(
                    await self._plan_other_source(
                        digest,
                        [],
                        holdings,
                        Inclusion.UNFINISHED,
                        state=state,
                        request_id=request_id,
                        reason=reason,
                        recorded_at=recorded_at,
                        withdrawn_earlier_from=recorded.get(digest, ()),
                    )
                )
            elif digest in recorded:
                # Withdrawn by an earlier run, with nothing of it left on this machine: planned again
                # only to take a copy still in a caselist that keeps no holder of it (v1-e30-t19),
                # and never removed whole on the record's account.
                again = await self._plan_other_source(
                    digest,
                    [],
                    holdings,
                    Inclusion.UNFINISHED,
                    state=state,
                    request_id=request_id,
                    reason=reason,
                    recorded_at=recorded_at,
                    withdrawn_earlier_from=recorded[digest],
                )
                unkept = sorted(set(recorded[digest]) - set(again.kept_in))
                if again.disposition is Disposition.WITHDRAW and await _left_in_the_bucket(
                    digest, unkept, index
                ):
                    unfinished.append(again)
        sources = [
            _with_its_recorded_withdrawals(source, recorded)
            for source in [*sorted([*named, *unfinished], key=lambda source: source.sha256), *added]
        ]

        after = SuppressionState.from_entries(
            [*existing, *(entry for source in sources for entry in source.suppression)],
            [*existing_holds, *path_holds],
        )
        removed = {source.sha256 for source in sources if source.disposition is Disposition.REMOVE}
        withdrawn = {
            (caselist, path, source.sha256)
            for source in sources
            if source.disposition is Disposition.WITHDRAW
            for caselist, path in source.requester_paths
        }
        rewrites = await self._manifest_rewrites(copies, selector, removed, withdrawn, after, index)
        objects, counted = await self._objects(sources, caselists, copies, index)
        inbox, team_files_left = plan_inbox(
            self._inbox,
            suppression=after,
            imported_weeks=_imported_weeks(copies),
            imported_full_archives=_imported_weeks(copies, full_archives=True),
            imported_openev_downloads=_imported_openev_downloads(copies),
            team=(selector.caselist, selector.school, selector.team_code)
            if isinstance(selector, TeamSelector)
            else None,
            files=inbox_files,
            withdrawn_camp_documents=_withdrawn_camp_documents(sources),
        )
        plan = RemovalPlan(
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
            only_named=only_named,
            later_uploads=later,
            earlier_versions=tuple(one for one in versions if one.relation is not VersionRelation.LATER),
            path_holds=path_holds,
            earlier_rewrites=earlier_rewrites,
        )
        return replace(plan, superseded_versions=await self._swept(plan))

    async def _earlier_rewrites(self, request_id: str) -> tuple[ManifestRewriteRecord, ...]:
        """The manifests this request's earlier runs in this environment rewrote, from their scopes.

        Every run's, completed or stopped: a scope records a rewrite only once its purge is done.
        Another request's, or another environment's, are not this request's to sweep.
        """
        found = {
            rewrite: None
            for scope in await self._removal_log.scopes()
            if scope.request_id == request_id and scope.environment == self._environment
            for rewrite in scope.manifest_rewrites
        }
        return tuple(found)

    async def _swept(self, plan: RemovalPlan) -> tuple[ObjectVersion, ...] | None:
        """What the execution's sweep would delete, as the everyday credential sees it; `None` where
        it may not list or read noncurrent manifest versions, so they are not counted."""
        try:
            return await plan.swept_from(self._remote_versions)
        except StoreAccessDenied:
            return None

    # --------------------------------------------------------------------------------------
    # Reading
    # --------------------------------------------------------------------------------------

    async def _known_caselists(self) -> list[str]:
        """Every caselist either copy of the store holds a manifest for, and OpenEv.

        All of them, whatever the selector: whether a team's file is shared depends on who else
        disclosed it, in any caselist, and a file is in the bucket under every caselist that did. A
        caselist known only from a complete archive (`manifests/<slug>/full/<date>.jsonl`) counts.
        """
        found: set[str] = {OPENEV}
        for store in (self._local.objects, self._remote):
            for info in await store.list_objects(f"{MANIFEST_DIRECTORY}/"):
                parts = info.key.split("/")
                weekly_or_release = len(parts) == 3 and (parts[1] == OPENEV or _CASELIST_SLUG.match(parts[1]))
                complete = (
                    len(parts) == 4
                    and _CASELIST_SLUG.match(parts[1]) is not None
                    and snapshot_of_manifest_key(parts[1], info.key, full_archives=True) is not None
                )
                if weekly_or_release or complete:
                    found.add(parts[1])
        return sorted(found)

    async def _manifest_copies(self, caselist: str) -> list[_ManifestCopy]:
        """Every manifest of `caselist` on either side: its weeklies **and its complete archives**.

        A complete archive's manifest (`v1-e34-t04`) names schools, team codes and paths as a
        weekly's does, and a takedown that missed it would leave the removed row in the corpus's
        own copy. So it is read here, rewritten like any other, and swept like any other.
        """
        prefix = manifest_prefix(caselist)
        local_keys = {
            info.key
            for info in await self._local.objects.list_objects(prefix)
            if snapshot_of_manifest_key(caselist, info.key, full_archives=True)
        }
        remote_keys = {
            info.key
            for info in await self._remote.list_objects(prefix)
            if snapshot_of_manifest_key(caselist, info.key, full_archives=True)
        }
        copies: list[_ManifestCopy] = []
        for key in sorted(local_keys | remote_keys):
            local_lines: tuple[str, ...] | None = None
            local_digest: str | None = None
            if key in local_keys:
                async with local_file(self._local.objects, self._local.object_path_for, key) as path:
                    local_lines = tuple(read_manifest_file(path))
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

    async def _selected(self, selector: RemovalSelector, copies: Sequence[_ManifestCopy]) -> set[str]:
        """The files the selector itself names: the one digest, or every file at the team's paths.

        For a team that is every digest any record or any row of any snapshot, weekly or complete,
        on either side, holds under the team's directories: every version of every file of the
        team's, earlier and later alike. So a `--team` removal needs no search for later uploads
        at the team's own paths (`v1-e30-t11`).
        """
        if isinstance(selector, SourceSelector):
            return {selector.sha256}
        found = {disclosure.source_sha256 for disclosure in await self._team_disclosures(selector)}
        for copy in copies:
            for _, row in copy.rows:
                digest, path = row.get("sha256"), row.get("path")
                if isinstance(digest, str) and isinstance(path, str) and selector.holds(copy.caselist, path):
                    found.add(digest)
        return found

    async def _left_on_this_machine(
        self, digest: str, state: SuppressionState, held: Sequence[PathHolding]
    ) -> bool:
        """Whether a file this request already suppressed still has a record or its blob here.

        What a `--source` removal stopped part-way can leave of a later upload once the manifest
        rows that showed it at the removed path are rewritten: nothing else would find it again.
        A file with nothing left is not planned again, so a second `--source` under one request id
        does not list the first.

        For a camp path withdrawn (`v1-e30-t14`), what is left is a release's camp-file record with
        no row of the file left in that release, or a row at the withdrawn camp path itself: a build
        from before that task asks the list about a camp file's whole source only, so its pull may
        record the withdrawn id there again, and running the same removal again takes it.
        """
        disclosures = [one async for one in _all_disclosures(self._caselists, source_sha256=digest)]
        if not state.suppresses_source(digest):
            return (
                any(
                    state.suppresses(digest, disclosure=disclosure_digest(one.caselist, one.source_path))
                    for one in disclosures
                )
                or any(
                    state.suppresses(digest, disclosure=camp_path_disclosure(row.snapshot, row.path))
                    for row in held
                    if row.caselist == OPENEV and row.sha256 == digest and not row.inbox
                )
                or bool(_orphaned_releases(await _all_camp_files(self._caselists, digest), held, digest))
            )
        return bool(
            disclosures
            or await self._caselists.find_source(digest) is not None
            or await _all_camp_files(self._caselists, digest)
            or await self._local_blobs.list_versions(local_blob_key(digest))
        )

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
            other_releases = len(holdings.releases)
        else:
            # No requesting team: one holder is the one whose file is removed, and the rest are the
            # others. A team's file is that team's, and a file no team holds is one camp release's.
            # Counting every holder called a file one holder has "also held by 1 other team"
            # (`v1-e30-t10`), or "by 1 camp file" (`v1-e30-t16`).
            others = max(len(holdings.teams) - 1, 0)
            other_releases = len(holdings.releases) if holdings.teams else max(len(holdings.releases) - 1, 0)
        shared = others + other_releases > 0

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
            camp_file_holders=other_releases,
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

    async def _plan_other_source(
        self,
        digest: str,
        later: Sequence[PathVersion],
        holdings: Sequence[PathHolding],
        inclusion: Inclusion,
        *,
        state: SuppressionState,
        request_id: str,
        reason: ReasonCode,
        recorded_at: datetime,
        withdrawn_earlier_from: tuple[str, ...] = (),
        refused_at: Sequence[tuple[str, Sha256Hex]] = (),
    ) -> PlannedSource:
        """Plan a file the selector does not name: a later upload, or one a stopped run left.

        The removal takes it from the paths it is a later upload at (`later`) and from any path of
        it the list already stops. A path it is held at that is neither is a live path: with one,
        the bytes stay for that path and only the taken paths' rows and records go; with none, the
        file goes everywhere, exactly as a named file does. `--include-shared` plays no part: it
        is the operator's decision about the files the request names.

        `withdrawn_earlier_from` is where the withdrawal record says an earlier run of this request
        withdrew the file from (`v1-e30-t19`): a copy there that is still in the bucket is withdrawn
        again, though no row or record shows its path any more.

        `refused_at` is where the held-digest record says an import refused the file
        (`v1-e30-t23`): `(caselist, disclosure digest)` of each held path. Each is a taken path
        known by its digest alone, never a live one.
        """
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

        rows = [holding for holding in holdings if holding.sha256 == digest]
        held_at = {(row.caselist, row.path) for row in rows if row.caselist != OPENEV} | {
            (disclosure.caselist, disclosure.source_path) for disclosure in disclosures
        }
        taken = {(one.caselist, one.path) for one in later if one.caselist != OPENEV} | {
            (caselist, path)
            for caselist, path in held_at
            if state.suppresses(digest, disclosure=disclosure_digest(caselist, path))
        }
        live_paths = held_at - taken
        # A camp path is taken as a caselist path is (v1-e30-t14): where it is a later upload, and
        # where the list already stops the file at that release's row.
        later_camp_paths = {one.identity for one in later if one.caselist == OPENEV}
        camp_rows = [row for row in rows if row.caselist == OPENEV and not row.inbox]
        taken |= {
            taken_path(OPENEV, row.snapshot, row.path)
            for row in camp_rows
            if path_identity(row) in later_camp_paths
            or state.suppresses(digest, disclosure=camp_path_disclosure(row.snapshot, row.path))
        }
        # A release's record with no row of the file left: what a run stopped among the records leaves.
        orphaned: set[str] = (
            _orphaned_releases(camp_files, rows, digest) if inclusion is Inclusion.UNFINISHED else set()
        )
        live_releases = {
            row.snapshot for row in camp_rows if taken_path(OPENEV, row.snapshot, row.path) not in taken
        } | {
            release
            for release in {openev_release_name(one.year, one.event) for one in camp_files} - orphaned
            if not camp_rows
        }
        taken_releases = {path.split("/", 1)[0] for caselist, path in taken if caselist == OPENEV} | orphaned
        shared = bool(live_paths or live_releases)

        # A held path the record names and no row or inbox member shows (v1-e30-t23).
        taken_by_digest = {
            disclosure_digest(caselist, path) for caselist, path in taken if caselist != OPENEV
        }
        refused_only = tuple(sorted({one for one in refused_at if one[1] not in taken_by_digest}))

        if (state.suppresses_source(digest) and finishing) or not shared:
            disposition = Disposition.REMOVE
        elif taken or orphaned or withdrawn_earlier_from or refused_only:
            disposition = Disposition.WITHDRAW
        else:
            # Another holder has it, and nothing here says which path of it to take.
            disposition = Disposition.SKIP_SHARED

        entries: list[SuppressionEntry] = []
        dropped: list[DisclosureRef] = []
        dropped_camp: list[CampFileRef] = []
        requester_paths: tuple[tuple[str, str], ...] = ()
        local_blob = False
        if disposition is Disposition.REMOVE:
            dropped = [_disclosure_ref(disclosure) for disclosure in disclosures]
            dropped_camp = [_camp_ref(camp_file) for camp_file in camp_files]
            if not state.suppresses_source(digest):
                entries.append(_suppression(digest, None, recorded_at, reason, request_id))
            local_blob = bool(await self._local_blobs.list_versions(local_blob_key(digest)))
        elif disposition is Disposition.WITHDRAW:
            dropped = [
                _disclosure_ref(disclosure)
                for disclosure in disclosures
                if (disclosure.caselist, disclosure.source_path) in taken
            ]
            dropped_camp = [
                _camp_ref(camp_file)
                for camp_file in camp_files
                if (release := openev_release_name(camp_file.year, camp_file.event)) in taken_releases
                and release not in live_releases
            ]
            requester_paths = tuple(sorted(taken))
            for caselist, path in requester_paths:
                digest_of_path = disclosure_digest(caselist, path)
                if not state.suppresses(digest, disclosure=digest_of_path):
                    entries.append(_suppression(digest, digest_of_path, recorded_at, reason, request_id))
            for _, digest_of_path in refused_only:
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
            other_teams=len(_teams_at(live_paths) - _teams_at(taken)),
            camp_file_holders=len(live_releases),
            kept_in=tuple(
                sorted({caselist for caselist, _ in live_paths} | ({OPENEV} if live_releases else set()))
            )
            if disposition is Disposition.WITHDRAW
            else (),
            delete_source_record=disposition is Disposition.REMOVE and source is not None,
            local_blob=local_blob,
            suppression=tuple(entries),
            already_suppressed=finishing,
            inclusion=inclusion,
            held_at_import=refused_only,
        )

    # --------------------------------------------------------------------------------------
    # Manifests
    # --------------------------------------------------------------------------------------

    async def _manifest_rewrites(
        self,
        copies: Sequence[_ManifestCopy],
        selector: RemovalSelector,
        removed: set[str],
        withdrawn: set[tuple[str, str, str]],
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
                copy, selector, removed, withdrawn, held_removed.get(copy.caselist, set()), after
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
        aggregates_planned: set[tuple[Side, str]] = set()
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
                # by this machine's records or by any manifest on either side. A camp path's release
                # year's copy goes only when no other release of that year holds it (v1-e30-t14).
                # A re-run also takes the caselists the withdrawal record names, whose paths the
                # first run's deletions left nothing to show (v1-e30-t19).
                withdrawn_from = {name for name, _ in source.requester_paths} | set(
                    source.withdrawn_earlier_from
                )
                parsed_caselists = sorted(withdrawn_from - set(source.kept_in))
                raw_prefixes = [
                    f"{CASELIST_SOURCE_PREFIX}/{name}/" for name in parsed_caselists if name != OPENEV
                ]
                years = set(_camp_years_withdrawn(source, copies))
                if OPENEV in source.withdrawn_earlier_from and OPENEV not in source.kept_in:
                    # No release holds it any more, so no year's copy is any release's.
                    years |= set(openev_years)
                raw_prefixes += [f"{OPENEV_SOURCE_PREFIX}/{year}/" for year in sorted(years)]

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
            # Every caselist with a row derived from this source or one of the withdrawn disclosures,
            # including one where another team keeps the file: its occurrence rows still go.
            touched = {
                *parsed_caselists,
                *(name for name, _ in source.requester_paths),
                *source.withdrawn_earlier_from,
            }
            for caselist in sorted(touched):
                prefix = f"parsed/{caselist}/"
                listed = await index.versions(prefix)
                keys = {key for key in await index.current(prefix) if _is_parsed_aggregate(key, prefix)}
                keys |= {key for key in (listed or {}) if _is_parsed_aggregate(key, prefix)}
                for key in sorted(keys - {key for side, key in aggregates_planned if side is Side.BUCKET}):
                    aggregates_planned.add((Side.BUCKET, key))
                    objects.append(
                        ObjectRemoval(
                            key=key,
                            side=Side.BUCKET,
                            kind=ObjectKind.PARSED_AGGREGATE,
                            sha256=digest,
                            versions=None if listed is None else tuple(listed.get(key, [])),
                        )
                    )
                for version in await self._local_parsed.list_versions(f"{caselist}/"):
                    if (
                        _is_parsed_aggregate(version.key, f"{caselist}/")
                        and (Side.LOCAL, version.key) not in aggregates_planned
                    ):
                        aggregates_planned.add((Side.LOCAL, version.key))
                        objects.append(
                            ObjectRemoval(
                                key=version.key,
                                side=Side.LOCAL,
                                kind=ObjectKind.PARSED_AGGREGATE,
                                sha256=digest,
                                versions=(version,),
                            )
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
    withdrawn: set[tuple[str, str, str]],
    held_removed: set[str],
    after: SuppressionState,
) -> set[int]:
    """Indexes of the member rows a rewrite leaves out. See the module docstring for each rule."""
    dropped = {
        index
        for index, (_, row) in enumerate(copy.rows)
        if _dropped(row, copy, selector, removed, withdrawn, held_removed, after)
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
    caselist = None if copy.caselist == OPENEV else copy.caselist
    snapshot = snapshot_date(copy.snapshot)
    dropped |= {
        index
        for index, (_, row) in enumerate(copy.rows)
        if row.get("skip_reason") is not None
        and isinstance(path := row.get("path"), str)
        and hold_on_skipped_member(after, caselist=caselist, path=path, snapshot=snapshot) is not None
    }
    return dropped


def _dropped(
    row: Mapping[str, object],
    copy: _ManifestCopy,
    selector: RemovalSelector,
    removed: set[str],
    withdrawn: set[tuple[str, str, str]],
    held_removed: set[str],
    after: SuppressionState,
) -> bool:
    """Whether one member row goes, before the junk that shadows dropped files is added.

    `withdrawn` is `(caselist, path, sha256)` with the path as :func:`taken_path` gives it: a
    withdrawal takes one file from one path, and an earlier version of another file at that path
    keeps its row (`v1-e30-t11`). A camp path is one row of one release (`v1-e30-t14`).
    """
    path, digest = row.get("path"), row.get("sha256")
    if not isinstance(path, str):
        return False
    caselist = copy.caselist
    if isinstance(selector, TeamSelector) and selector.holds(caselist, path):
        return True  # every row of the requesting team's, junk and REMOVED rows included
    if digest in removed or (*taken_path(caselist, copy.release, path), digest) in withdrawn:
        return True
    if row.get("classification") == str(Classification.REMOVED) and path in held_removed:
        return True  # "this path's file was taken down", where the file was the removed one
    # Anything else the list already stops: a row an earlier removal never reached.
    return isinstance(digest, str) and after.suppresses(
        digest, disclosure=disclosure_digest(_scope(copy), path)
    )


def _scope(copy: _ManifestCopy) -> str:
    """What a row's disclosure digest is taken under: its caselist, or its camp release (`v1-e30-t14`)."""
    return camp_path_scope(copy.release) if copy.caselist == OPENEV else copy.caselist


def _rewritten(copy: _ManifestCopy, dropped: set[int], after: SuppressionState) -> tuple[str, ...]:
    """The manifest without the dropped rows: every kept row byte for byte, then a recounted summary.

    The kept rows go through :func:`~debate_core.application.caselist.manifest.render_rows` too,
    for its suppression check only: a rewrite that kept a row the list stops is refused before it
    is written.
    """
    assert copy.summary is not None
    kept = [row for index, (_, row) in enumerate(copy.rows) if index not in dropped]
    gone = [row for index, (_, row) in enumerate(copy.rows) if index in dropped]
    scope = _scope(copy)
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


def _path_holdings(copies: Sequence[_ManifestCopy]) -> tuple[PathHolding, ...]:
    """Every stored row of every manifest read, on either side: who holds which bytes at which path."""
    held: set[PathHolding] = set()
    for copy in copies:
        for _, row in copy.rows:
            digest, path = row.get("sha256"), row.get("path")
            if row.get("classification") in _STORED and isinstance(digest, str) and isinstance(path, str):
                held.add(
                    PathHolding(caselist=copy.caselist, snapshot=copy.snapshot, path=path, sha256=digest)
                )
    return tuple(sorted(held, key=lambda one: (one.caselist, one.snapshot, one.path, one.sha256)))


def _inbox_holdings(files: Sequence[InboxFile]) -> tuple[PathHolding, ...]:
    """Every real member of every weekly and complete archive in the inbox, as a snapshot holds it.

    Dated as the archive's name dates it, which is how the sync dates the snapshot it imports it
    as. An archive that cannot be read holds nothing here; the inbox step reports it. A camp
    download is not a caselist snapshot: `v1-e34-t14` holds a camp path.
    """
    held: set[PathHolding] = set()
    for file in files:
        if file.entries is None or file.caselist is None or file.snapshot is None:
            continue  # unreadable, or not a caselist's archive: only those are named for a caselist
        complete = file.kind is InboxFileKind.FULL_ARCHIVE
        snapshot = full_archive_snapshot(file.snapshot) if complete else file.snapshot.isoformat()
        for entry in file.entries:
            if entry.skip_reason is None and entry.sha256 is not None:
                held.add(
                    PathHolding(
                        caselist=file.caselist,
                        snapshot=snapshot,
                        path=entry.path,
                        sha256=entry.sha256,
                        inbox=True,
                    )
                )
    return tuple(sorted(held, key=lambda one: (one.caselist, one.snapshot, one.path, one.sha256)))


def _path_holds(
    named: Sequence[PlannedSource],
    held: Sequence[PathHolding],
    state: SuppressionState,
    *,
    recorded_at: datetime,
    reason: ReasonCode,
    request_id: str,
) -> tuple[PathHoldEntry, ...]:
    """One path entry for each caselist path the removal takes a named file from whole.

    The path is every place the file is held: a stored row, a disclosure record, or a member of an
    archive in the inbox. The hold is dated by the earliest snapshot that holds it there, which is
    the date `v1-e30-t11` measures "later" from. A file the plan withdraws or skips stays with
    another holder and gets none, and neither does a path this file already holds.
    """
    entries: list[PathHoldEntry] = []
    for source in named:
        if source.disposition is not Disposition.REMOVE:
            continue
        first_held: dict[tuple[str, str], date] = {}
        seen = [
            (row.caselist, row.path, snapshot_date(row.snapshot))
            for row in held
            if row.sha256 == source.sha256 and row.caselist != OPENEV
        ]
        seen += [(ref.caselist, ref.source_path, ref.snapshot) for ref in source.disclosures]
        for caselist, path, held_on in seen:
            if held_on is not None:
                first_held[(caselist, path)] = min(held_on, first_held.get((caselist, path), held_on))
        for (caselist, path), held_on in sorted(first_held.items()):
            disclosure = disclosure_digest(caselist, path)
            if any(hold.sha256 == source.sha256 for hold in state.held_paths.get(disclosure, ())):
                continue
            entries.append(
                PathHoldEntry(
                    caselist=caselist,
                    disclosure=disclosure,
                    sha256=source.sha256,
                    after_snapshot=held_on,
                    recorded_at=recorded_at,
                    reason=reason,
                    request_id=request_id,
                )
            )
    return tuple(entries)


def _recorded_paths(
    state: SuppressionState, named: Collection[str], held: Sequence[PathHolding]
) -> tuple[PathHolding, ...]:
    """Where the path holds in force say a named file was, for each such path something is held at.

    A hold keeps the path as a digest, so the path's text comes from whatever is at it now: a row
    or an inbox member whose caselist and path give the hold's digest. That is every case with
    something to find. The stand-in is dated by the hold, the earliest snapshot that held the
    removed file there, so "later" means what it meant when the file was removed.
    """
    of_named = {
        disclosure: [hold for hold in holds if hold.sha256 in named]
        for disclosure, holds in state.held_paths.items()
    }
    if not any(of_named.values()):
        return ()
    stand_ins: set[PathHolding] = set()
    for caselist, path in {(row.caselist, row.path) for row in held if row.caselist != OPENEV}:
        for hold in of_named.get(disclosure_digest(caselist, path), ()):
            stand_ins.add(
                PathHolding(
                    caselist=caselist,
                    snapshot=hold.after_snapshot.isoformat(),
                    path=path,
                    sha256=hold.sha256,
                )
            )
    return tuple(sorted(stand_ins, key=lambda one: (one.caselist, one.snapshot, one.path, one.sha256)))


def _refused_at_import(
    held: Sequence[HeldDigestEntry], state: SuppressionState, *, named: Collection[str], request_id: str
) -> dict[Sha256Hex, tuple[tuple[str, Sha256Hex], ...]]:
    """For each upload an import refused under this request, the held paths it was refused at (`v1-e30-t23`).

    `(caselist, disclosure digest)`, from a hold in force at the entry's path on a file the selector
    names, as :func:`_recorded_paths` asks of a row. A hold an un-suppress lifted refuses nothing
    any more, and its uploads are not planned. A named file is planned as named.
    """
    found: dict[Sha256Hex, set[tuple[str, Sha256Hex]]] = {}
    for entry in held:
        if entry.request_id != request_id or entry.sha256 in named:
            continue
        for hold in state.held_paths.get(entry.disclosure, ()):
            if hold.sha256 in named:
                found.setdefault(entry.sha256, set()).add((hold.caselist, hold.disclosure))
    return {digest: tuple(sorted(paths)) for digest, paths in sorted(found.items())}


def taken_path(caselist: str, snapshot: str, path: str) -> tuple[str, str]:
    """`(caselist, path)` as a withdrawal names a copy it takes (:attr:`PlannedSource.requester_paths`).

    A caselist path is its caselist and path, in every snapshot. A camp path is `openev` and
    `<release>/<row path>` (`v1-e30-t14`): one row of one release manifest, whose
    :func:`~debate_core.application.ports.suppression.disclosure_digest` is
    :func:`~debate_core.application.ports.suppression.camp_path_disclosure`.
    """
    return (OPENEV, f"{snapshot}/{path}") if caselist == OPENEV else (caselist, path)


def _withdrawn_camp_documents(sources: Sequence[PlannedSource]) -> dict[str, str]:
    """`{inbox name: sha256}` of the camp documents whose camp path this plan withdraws (`v1-e30-t14`).

    A single document the pull fetched is imported as one row at its inbox name, `openev-<id>-…`,
    so a withdrawn row at a name of that form is the copy in the inbox. A camp release that is a zip
    records its members at their own paths, which are not inbox names.
    """
    return {
        path.split("/", 1)[1]: source.sha256
        for source in sources
        if source.disposition is Disposition.WITHDRAW
        for caselist, path in source.requester_paths
        if caselist == OPENEV
        and openev_id_of_inbox_name(path.split("/", 1)[1]) is not None
        and "/" not in path.split("/", 1)[1]
    }


def _row_upstream_paths(copies: Sequence[_ManifestCopy]) -> dict[int, str]:
    """`{openev id: SHA-256 of its upstream path}` as the release manifests' rows carry it (`v1-e30-t14`)."""
    found: dict[int, str] = {}
    for copy in copies:
        if copy.caselist != OPENEV:
            continue
        for _, row in copy.rows:
            identity = row_upstream_identity(row)
            if identity is not None:
                found[identity[0]] = identity[1]
    return found


def _orphaned_releases(camp_files: Sequence[CampFile], held: Sequence[PathHolding], digest: str) -> set[str]:
    """The releases with a camp-file record of `digest` and no stored row of it: a withdrawal's leftover."""
    with_rows = {
        row.snapshot for row in held if row.caselist == OPENEV and row.sha256 == digest and not row.inbox
    }
    return {openev_release_name(one.year, one.event) for one in camp_files} - with_rows


def _camp_years_withdrawn(source: PlannedSource, copies: Sequence[_ManifestCopy]) -> list[str]:
    """The years whose `raw/openev/<year>/` copy a camp path's withdrawal deletes (`v1-e30-t14`).

    A year a withdrawn camp path or record is in, and no other release of that year still holds the
    file at a row the withdrawal does not take.
    """
    withdrawn = {path for caselist, path in source.requester_paths if caselist == OPENEV}
    years = {path.split("/", 1)[0][:4] for path in withdrawn} | {
        f"{ref.year:04d}" for ref in source.camp_files
    }
    live = {
        copy.release[:4]
        for copy in copies
        if copy.caselist == OPENEV
        for _, row in copy.rows
        if row.get("sha256") == source.sha256
        and row.get("classification") in _STORED
        and taken_path(OPENEV, copy.release, str(row.get("path"))) not in source.requester_paths
    }
    return sorted(years - live)


def _teams_at(paths: Collection[tuple[str, str]]) -> set[tuple[str, tuple[str, str]]]:
    """The teams holding `(caselist, path)` copies, each as its caselist and its two directories.

    A path filed under no team's directories is no team's, as :meth:`RemovalPlanner._holdings`
    counts them: the archive's structure is all that says whose a copy is.
    """
    return {(caselist, team) for caselist, path in paths if (team := team_of_path(path)) is not None}


def _paths_taken(named: Sequence[PlannedSource]) -> dict[str, frozenset[tuple[str, ...]] | None]:
    """For each named file the removal acts on, the paths it takes it from: `None` for all of them.

    A file left alone (`SKIP_SHARED`) is taken from nowhere, so nothing is a later upload of it.
    """
    taken: dict[str, frozenset[tuple[str, ...]] | None] = {}
    for source in named:
        if source.disposition is Disposition.REMOVE:
            taken[source.sha256] = None
        elif source.disposition is Disposition.WITHDRAW:
            taken[source.sha256] = frozenset(source.requester_paths)
    return taken


def _suppressed_by(state: SuppressionState, request_id: str) -> set[str]:
    """The files whose latest entry on the list is this request's suppression."""
    return {
        digest
        for digest, latest in state.latest.items()
        if latest.action is SuppressionAction.SUPPRESS and latest.request_id == request_id
    }


def _withdrawn_by_the_request(
    withdrawals: Sequence[WithdrawalEntry], request_id: str
) -> dict[str, tuple[str, ...]]:
    """For each file this request withdrew a copy of, the caselists it withdrew them from (`v1-e30-t19`).

    From the withdrawal record (`v1-e30-t16`), which a removal appends just before the suppression
    entries it attributes, so every copy a build since then withdrew is in it. This request's
    alone: another request's withdrawal of the same file reached another caselist, not this one's.
    An earlier build's withdrawal is not in it, and that file has no caselist here. Whether the list
    still suppresses one is not asked: a caselist here only joins a file this plan withdraws again
    under the same request, which reached it either way.
    """
    found: dict[str, set[str]] = {}
    for one in withdrawals:
        if one.request_id == request_id:
            found.setdefault(one.sha256, set()).add(one.caselist)
    return {digest: tuple(sorted(caselists)) for digest, caselists in found.items()}


def _with_its_recorded_withdrawals(
    source: PlannedSource, recorded: Mapping[str, tuple[str, ...]]
) -> PlannedSource:
    """A withdrawn file, with the caselists the request's earlier runs withdrew it from (`v1-e30-t19`)."""
    if source.disposition is not Disposition.WITHDRAW or source.sha256 not in recorded:
        return source
    return replace(source, withdrawn_earlier_from=recorded[source.sha256])


async def _left_in_the_bucket(digest: str, caselists: Sequence[str], index: _BucketIndex) -> bool:
    """Whether any version of `digest`'s copy, or of a parsed file of it, is in a caselist it was
    withdrawn from (`v1-e30-t19`): what a `--source` re-run plans a withdrawn later upload again for.

    A listing this credential may not make is read as maybe: the plan then includes the file, and
    says its versions were not counted.
    """
    for caselist in caselists:
        source_prefix = (
            f"{OPENEV_SOURCE_PREFIX}/" if caselist == OPENEV else f"{CASELIST_SOURCE_PREFIX}/{caselist}/"
        )
        for prefix in (source_prefix, f"parsed/{caselist}/"):
            listed = await index.versions(prefix)
            if listed is None or any(_names_digest(key, digest) for key in listed):
                return True
    return False


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


def _imported_weeks(
    copies: Sequence[_ManifestCopy], *, full_archives: bool = False
) -> frozenset[tuple[str, date]]:
    """The weeks this machine holds a manifest for: what the sync calls imported (`_decide_archive`).

    This machine's copies only. The inbox is this machine's, and so is the sync's notion of what it
    has imported; a manifest that is only in the bucket has not been imported here. The weekly
    series, or with `full_archives` the complete archives' dates instead: a complete archive shares
    its date with that week's weekly, and the one being imported says nothing about the other.
    """
    weeks: set[tuple[str, date]] = set()
    for copy in copies:
        if copy.side is Side.LOCAL and copy.caselist != OPENEV and copy.full_archive is full_archives:
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


def _caselist_of_bucket_key(key: str) -> str:
    """The caselist a `raw/` or `parsed/` key is filed under: `raw/caselist/<slug>/…`, `raw/openev/…`
    or `parsed/<caselist>/…`."""
    parts = key.split("/")
    if key.startswith(f"{CASELIST_SOURCE_PREFIX}/"):
        return parts[2]
    if key.startswith(f"{OPENEV_SOURCE_PREFIX}/"):
        return OPENEV
    return parts[1]


def _is_parsed_aggregate(key: str, caselist_prefix: str) -> bool:
    """Whether `key` is `<caselist_prefix><version>/<aggregate>`: a parsed store aggregate file."""
    if not key.startswith(caselist_prefix):
        return False
    rest = key[len(caselist_prefix) :].split("/")
    return len(rest) == 2 and rest[1] in AGGREGATE_NAMES


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

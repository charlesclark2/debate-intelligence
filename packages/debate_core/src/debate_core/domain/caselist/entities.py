"""The records an import of disclosed or camp evidence produces.

Seven models, in the order a file moves through them:

* :class:`Caselist` — one published caselist for one season (`hsld26`, event, level, season).
* :class:`School` — a school as it appears in that caselist's directory listing.
* :class:`TeamCode` — the code a team disclosed under, inside a school, inside a caselist.
* :class:`ArchiveSnapshot` — one weekly archive: its date, its own SHA-256, how it was acquired.
* :class:`SourceDocument` — one file, identified by the SHA-256 of its bytes, seen in a range of
  snapshots.
* :class:`Disclosure` — what a caselist archive says about that file: school, team code, side,
  tournament and round, and the path it was filed under.
* :class:`CampFile` — what an OpenEv release says about it: camp, year, event and file title.

**Identity is natural, not minted.** A caselist is its slug, a source document is its SHA-256, a
snapshot is its (caselist, date). These models therefore extend
:class:`~debate_core.domain.base.DomainModel` rather than
:class:`~debate_core.domain.base.DomainEntity`: there is no ULID to mint, no owner to record and
no revision to race for, because an import is a re-statement of what a public archive says, not an
edit a person makes.

**Provenance travels on the record.** Every imported record carries where it came from — origin,
the caselist or camp, the snapshot it was seen in, and the source SHA-256 — as fields of its own
rather than in a side table, so a manifest row, an S3 key and a landscape report can each be
traced back without a join. All of it is
:attr:`~debate_core.domain.enums.ProvenanceMode.FILE_IMPORT`: the platform parsed a file somebody
downloaded, and no field here may claim more than that.

**No personal data.** There is no field for a debater's name, an email address or a Tabroom person
id anywhere in this module, and `tests/domain/caselist/test_minimization.py` pins every model's
field set so that adding one fails CI (architecture proposal §14).
"""

from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from debate_core.domain.base import DomainModel, NonEmptyText, Sha256Hex
from debate_core.domain.caselist.values import (
    Acquisition,
    CaselistSlug,
    CompetitionLevel,
    Event,
    RoundLabel,
    Season,
    Side,
    SnapshotDate,
    SourceFormat,
    SourceOrigin,
    TeamCodeText,
    sides_for_event,
)
from debate_core.domain.enums import ProvenanceMode

__all__ = [
    "IMPORTED_EVIDENCE_PROVENANCE_MODE",
    "ArchiveSnapshot",
    "CampFile",
    "Caselist",
    "Disclosure",
    "School",
    "SourceDocument",
    "TeamCode",
]

IMPORTED_EVIDENCE_PROVENANCE_MODE = ProvenanceMode.FILE_IMPORT
"""The only provenance mode imported caselist and camp evidence may carry.

Named rather than written inline on each model so the claim is made in one place: everything in
this module came out of a file the operator downloaded, never from a publisher fetch and never
from a model.
"""


def _require_file_import(mode: ProvenanceMode) -> ProvenanceMode:
    """Reject any provenance mode other than `FILE_IMPORT` on an imported record."""
    if mode is not IMPORTED_EVIDENCE_PROVENANCE_MODE:
        raise ValueError(
            f"imported caselist evidence is always {IMPORTED_EVIDENCE_PROVENANCE_MODE}, not {mode}"
        )
    return mode


#: The shared declaration of the `provenance_mode` field on every imported record.
_PROVENANCE_MODE_FIELD = Field(
    default=IMPORTED_EVIDENCE_PROVENANCE_MODE,
    description="Always FILE_IMPORT: this record describes a file the operator downloaded.",
)


# --------------------------------------------------------------------------------------------
# The caselist and the teams in it
# --------------------------------------------------------------------------------------------


class Caselist(DomainModel):
    """One published caselist: an event, at a level, for a season.

    The slug is the identity and it is taken as data — a new season's caselists are rows an
    operator imports, not members of an enum this package would have to release.
    """

    slug: CaselistSlug = Field(description="Published slug, e.g. hsld26. Also the primary key.")
    event: Event = Field(description="Which event this caselist covers.")
    level: CompetitionLevel = Field(description="High school, college or middle school circuit.")
    season: Season = Field(description="The season this caselist covers, e.g. 2026-27.")
    display_name: NonEmptyText | None = Field(
        default=None, description="Human-readable name, e.g. 'HS LD 2026-27'; None when not stated."
    )


class School(DomainModel):
    """A school as one caselist lists it.

    Identity is (caselist, name). The name is the program's name as disclosed — a school, not a
    person — and it is kept verbatim because it is also the directory name inside the archive.
    """

    caselist: CaselistSlug = Field(description="The caselist this school appears in.")
    name: NonEmptyText = Field(description="School or program name exactly as the caselist lists it.")


class TeamCode(DomainModel):
    """A team as it disclosed itself: a short code, inside a school, inside a caselist.

    The code is usually the debaters' initials. That is as far as the platform goes: it stores the
    code as written and has no field for whose initials they are. :data:`TeamCodeText` enforces
    the shape (architecture proposal §14).
    """

    caselist: CaselistSlug = Field(description="The caselist this team appears in.")
    school: NonEmptyText = Field(description="Name of the school this team debates for.")
    code: TeamCodeText = Field(description="The team code exactly as disclosed, e.g. RiOs.")


# --------------------------------------------------------------------------------------------
# What an import saw
# --------------------------------------------------------------------------------------------


class ArchiveSnapshot(DomainModel):
    """One weekly open-source archive, as downloaded.

    Weekly archives are cumulative, so the snapshot date is the axis everything else is ordered
    along: a source document's first and last seen snapshots, a re-import's no-op check, and the
    refusal to import an archive older than the latest one already in the store all read it.

    `archive_sha256` is the hash of the downloaded archive itself, which is what makes "we already
    imported this exact file" answerable without re-reading its members.
    """

    caselist: CaselistSlug = Field(description="The caselist this archive was published for.")
    snapshot: SnapshotDate = Field(description="The date the archive was published.")
    archive_sha256: Sha256Hex = Field(description="SHA-256 of the downloaded archive file itself.")
    acquisition: Acquisition = Field(description="Whether the archive was downloaded by hand or via an API.")
    file_count: int = Field(ge=0, description="How many member files the archive contained.")


class SourceDocument(DomainModel):
    """One evidence file, identified by the SHA-256 of its bytes.

    The hash is the identity, which is what makes deduplication across cumulative weekly archives
    a lookup rather than a decision: the same file appearing in ten snapshots is one source
    document whose `last_seen_snapshot` moves forward.

    `origin` records which import first brought the bytes in. A file that later shows up in the
    other kind of import does not get a second source document — the
    :class:`Disclosure` or :class:`CampFile` recorded for it points back at this same SHA-256,
    which is how E31 and E32 can see that a disclosed card came from a camp file.
    """

    sha256: Sha256Hex = Field(description="SHA-256 of the file's bytes. The primary key.")
    byte_size: int = Field(ge=0, description="Size of the file in bytes, as downloaded.")
    source_format: SourceFormat = Field(description="DOCX, DOC, PDF or OTHER; only DOCX is parsed in V1.")
    origin: SourceOrigin = Field(description="Which import first stored these bytes.")
    caselist: CaselistSlug | None = Field(
        default=None,
        description="Caselist the bytes were first seen in; None for a source that arrived from OpenEv.",
    )
    first_seen_snapshot: SnapshotDate = Field(description="Earliest snapshot this file appeared in.")
    last_seen_snapshot: SnapshotDate = Field(description="Most recent snapshot this file appeared in.")
    provenance_mode: ProvenanceMode = _PROVENANCE_MODE_FIELD

    @model_validator(mode="after")
    def _check_provenance(self) -> Self:
        _require_file_import(self.provenance_mode)
        if self.origin is SourceOrigin.CASELIST_ARCHIVE and self.caselist is None:
            raise ValueError("a source imported from a caselist archive must name its caselist")
        if self.origin is SourceOrigin.OPENEV and self.caselist is not None:
            raise ValueError(
                f"an OpenEv source belongs to a camp, not to a caselist; got caselist={self.caselist!r}. "
                "A camp file that also appears in a caselist is linked through its Disclosure."
            )
        if self.last_seen_snapshot < self.first_seen_snapshot:
            raise ValueError(
                f"last_seen_snapshot {self.last_seen_snapshot.isoformat()} precedes first_seen_snapshot "
                f"{self.first_seen_snapshot.isoformat()}"
            )
        return self

    @property
    def is_parsable(self) -> bool:
        """True for the formats E31 can read. `DOC` and `PDF` are stored unparsed in V1."""
        return self.source_format is SourceFormat.DOCX


class Disclosure(DomainModel):
    """What one caselist archive says about one file: who read it, on which side, in which round.

    Identity is (caselist, snapshot, source_path): the same file disclosed under two paths is two
    disclosures of one :class:`SourceDocument`, which is exactly the shape a re-upload takes.

    Every parsed field is allowed to be missing. A filename the parser cannot read yields a
    disclosure with :attr:`~debate_core.domain.caselist.values.Side.UNKNOWN`, no tournament, no
    round and a warning — never a dropped file (v1-e30-t03 ac1). `parse_warnings` is what carries
    that admission forward into the manifest and the landscape reports.

    `event` is carried here as well as on the :class:`Caselist` so that the legal sides can be
    checked on the record itself: a Public Forum disclosure marked `AFF` is a parsing bug, and it
    is caught where the record is built rather than wherever someone later joins the two.
    """

    source_sha256: Sha256Hex = Field(description="SHA-256 of the disclosed file's bytes.")
    caselist: CaselistSlug = Field(description="The caselist this disclosure was published in.")
    snapshot: SnapshotDate = Field(description="The snapshot this disclosure was read from.")
    event: Event = Field(description="The caselist's event, which decides the legal sides.")
    school: NonEmptyText = Field(description="School name as the archive path spells it.")
    team_code: TeamCodeText = Field(description="Team code as disclosed, e.g. RiOs.")
    side: Side = Field(
        default=Side.UNKNOWN,
        description="Side the file was read on; UNKNOWN when the filename could not be parsed.",
    )
    tournament: NonEmptyText | None = Field(
        default=None, description="Tournament exactly as written in the filename; None when absent."
    )
    round_label: RoundLabel | None = Field(
        default=None, description="Round as written plus its normalized form; None when absent."
    )
    source_path: NonEmptyText = Field(
        description="Path of the file inside the archive, relative to the archive root."
    )
    parse_warnings: tuple[NonEmptyText, ...] = Field(
        default=(), description="What the path parser could not read, in the order it found them."
    )
    provenance_mode: ProvenanceMode = _PROVENANCE_MODE_FIELD

    @model_validator(mode="after")
    def _check_provenance(self) -> Self:
        _require_file_import(self.provenance_mode)
        allowed = sides_for_event(self.event)
        if self.side not in allowed:
            legal = ", ".join(sorted(side.value for side in allowed))
            raise ValueError(f"{self.event} debates {legal}, so side {self.side} is not one of its sides")
        return self


class CampFile(DomainModel):
    """What an OpenEv release says about one file: which camp produced it, for which year and event.

    Identity is (source_sha256, year, event): one file, released once. `camp` is normalized
    through the importer's alias table (v1-e30-t04) and is the literal string `UNKNOWN` — with a
    warning — when the filename does not name a camp it recognises, because a file with an
    unreadable camp is still evidence worth keeping.
    """

    source_sha256: Sha256Hex = Field(description="SHA-256 of the camp file's bytes.")
    camp: NonEmptyText = Field(description="Camp that released the file, normalized; UNKNOWN when unresolved.")
    year: int = Field(ge=2000, description="Calendar year of the camp release, e.g. 2026.")
    event: Event = Field(description="Event the file was cut for.")
    file_title: NonEmptyText = Field(description="File title: the filename without camp prefix or extension.")
    snapshot: SnapshotDate = Field(description="The date this release was imported under.")
    parse_warnings: tuple[NonEmptyText, ...] = Field(
        default=(), description="What the filename parser could not read, e.g. an unresolved camp."
    )
    provenance_mode: ProvenanceMode = _PROVENANCE_MODE_FIELD

    @model_validator(mode="after")
    def _check_provenance(self) -> Self:
        _require_file_import(self.provenance_mode)
        return self

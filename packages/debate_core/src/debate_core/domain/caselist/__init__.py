"""The vocabulary of disclosed and camp evidence.

One import of an OpenCaselist weekly archive or an OpenEv camp release turns files on the
operator's Mac into the records defined here, and everything downstream — the archive importer
(v1-e30-t03), the OpenEv importer (t04), the S3 publisher (t05), the DOCX parser (E31), the
argument-landscape reports (E32) and V2's debate tub — reads the same seven entities rather than
re-deriving school, team, side and round from paths of its own.

Two rules are worth knowing before adding anything here:

* **Caselist slugs are data.** `hsld26`, `hspolicy26` and `hspf26` are validated strings, not enum
  members, because each season mints new ones.
* **Nothing identifies a person.** A team code is stored exactly as disclosed — usually initials —
  and no model has a field for a name, an email address or a Tabroom person id
  (architecture proposal §14).

The models are deliberately not re-exported from :mod:`debate_core.domain`: caselist evidence is
a bounded area with names like `Event` and `Side` that would be ambiguous in the platform-wide
namespace, so callers import from `debate_core.domain.caselist` explicitly.
"""

from debate_core.domain.caselist.entities import (
    IMPORTED_EVIDENCE_PROVENANCE_MODE,
    ArchiveSnapshot,
    CampFile,
    Caselist,
    Disclosure,
    School,
    SourceDocument,
    TeamCode,
)
from debate_core.domain.caselist.values import (
    CASELIST_SLUG_PATTERN,
    ELIMINATION_ROUND_SPELLINGS,
    SEASON_PATTERN,
    TEAM_CODE_MAX_LENGTH,
    Acquisition,
    CaselistSlug,
    CompetitionLevel,
    Event,
    NormalizedRound,
    RoundLabel,
    Season,
    Sha256Hex,
    Side,
    SnapshotDate,
    SourceFormat,
    SourceOrigin,
    TeamCodeText,
    normalize_round_token,
    sides_for_event,
)

#: Every caselist entity, in the order an import produces them. The data-minimization guard in
#: `tests/domain/caselist/test_minimization.py` iterates this tuple, so a new entity is covered by
#: it the moment it is added here.
CASELIST_MODELS = (
    Caselist,
    School,
    TeamCode,
    ArchiveSnapshot,
    SourceDocument,
    Disclosure,
    CampFile,
)

__all__ = [
    "CASELIST_MODELS",
    "CASELIST_SLUG_PATTERN",
    "ELIMINATION_ROUND_SPELLINGS",
    "IMPORTED_EVIDENCE_PROVENANCE_MODE",
    "SEASON_PATTERN",
    "TEAM_CODE_MAX_LENGTH",
    "Acquisition",
    "ArchiveSnapshot",
    "CampFile",
    "Caselist",
    "CaselistSlug",
    "CompetitionLevel",
    "Disclosure",
    "Event",
    "NormalizedRound",
    "RoundLabel",
    "School",
    "Season",
    "Sha256Hex",
    "Side",
    "SnapshotDate",
    "SourceDocument",
    "SourceFormat",
    "SourceOrigin",
    "TeamCode",
    "TeamCodeText",
    "normalize_round_token",
    "sides_for_event",
]

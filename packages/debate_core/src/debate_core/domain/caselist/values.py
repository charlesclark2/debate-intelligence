"""The scalars, enums and small value objects the caselist entities are built from.

Disclosed evidence arrives as files in a weekly archive, so almost every value here is something
read off a path, a filename or a download page. Two rules shape the module.

**Slugs and codes are data, never code.** A caselist is identified by its slug — `hsld26`,
`hspolicy26`, `hspf26`, and whatever next season's are — so :data:`CaselistSlug` is a *validated
string*, not an enum. A new caselist is a row someone imports, not a release of this package.

**Names are not collected.** A team code is the code the team disclosed under, usually the
debaters' initials. :data:`TeamCodeText` caps it at
:data:`TEAM_CODE_MAX_LENGTH` characters and rejects anything containing whitespace, because
"Rivera & Osei" is a pair of names and `RiOs` is a team code (architecture proposal §14). No
caselist model has a field for a person's name, an email address or a Tabroom person id, and
`tests/domain/caselist/test_minimization.py` fails if one is added.

Round labels are kept twice: :class:`RoundLabel` holds the raw token exactly as the disclosing
team wrote it, and the normalized :class:`NormalizedRound` when the token is one we recognise.
Nothing is discarded, because "Round 3" and "R3" have to aggregate together in the E32 landscape
reports while a tournament's own spelling stays quotable.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Annotated, Self

from pydantic import AfterValidator, Field, StringConstraints

from debate_core.domain.base import DomainModel, NonEmptyText, Sha256Hex

__all__ = [
    "CASELIST_SLUG_PATTERN",
    "SEASON_PATTERN",
    "TEAM_CODE_MAX_LENGTH",
    "Acquisition",
    "CaselistSlug",
    "CompetitionLevel",
    "ELIMINATION_ROUND_SPELLINGS",
    "Event",
    "NormalizedRound",
    "RoundLabel",
    "Season",
    "Sha256Hex",
    "Side",
    "SnapshotDate",
    "SourceFormat",
    "SourceOrigin",
    "TeamCodeText",
    "normalize_round_token",
    "sides_for_event",
]


# --------------------------------------------------------------------------------------------
# Identifying scalars
# --------------------------------------------------------------------------------------------

#: A caselist slug is letters then a two-digit season year: `hsld26`, `hspolicy26`, `ndtceda26`.
CASELIST_SLUG_PATTERN = r"^[a-z]+[0-9]{2}$"

CaselistSlug = Annotated[
    str,
    StringConstraints(pattern=CASELIST_SLUG_PATTERN),
]
"""The slug a caselist is published under, validated but never enumerated.

Kept as data on purpose: each season mints new slugs, and a season rollover must not require a
release of `debate_core`. The pattern is the shape OpenCaselist uses — an event name followed by
the two-digit year the season ends in.
"""

#: A season is the school year written as `2026-27`: four digits, a hyphen, the next year's last two.
SEASON_PATTERN = r"^[0-9]{4}-[0-9]{2}$"


def _require_consecutive_season_years(value: str) -> str:
    """Reject `2026-28` and friends: the second half must be the year after the first."""
    start_year = int(value[:4])
    stated_end = int(value[5:])
    expected_end = (start_year + 1) % 100
    if stated_end != expected_end:
        raise ValueError(
            f"a season spans two consecutive years, so {value!r} should end in "
            f"{expected_end:02d}, not {stated_end:02d}"
        )
    return value


Season = Annotated[
    str,
    StringConstraints(pattern=SEASON_PATTERN),
    AfterValidator(_require_consecutive_season_years),
]
"""A competitive season written the way debaters write it: `2026-27`."""

#: Longest team code accepted. Real codes are initials or short abbreviations ("RiOs", "AB").
TEAM_CODE_MAX_LENGTH = 12


def _reject_name_shaped_team_code(value: str) -> str:
    """Reject a "team code" that is really a person's name.

    Whitespace inside the value is the tell: disclosed codes are single tokens, and a value with a
    space in it ("Jane Rivera", "Rivera & Osei") is a name that must not enter the store.
    """
    if any(character.isspace() for character in value):
        raise ValueError(
            f"a team code is a single token as disclosed, never whitespace-separated words "
            f"(the platform stores no debater names): {value!r}"
        )
    return value


TeamCodeText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=TEAM_CODE_MAX_LENGTH),
    AfterValidator(_reject_name_shaped_team_code),
]
"""A team code exactly as disclosed, constrained so a full name cannot be stored in its place.

Named `TeamCodeText` rather than `TeamCode` because
:class:`~debate_core.domain.caselist.entities.TeamCode` is the entity that carries one; this is
the scalar its `code` field is typed with.
"""


def _reject_future_snapshot_date(value: date) -> date:
    """Reject a snapshot dated after today (UTC).

    A snapshot date is the day an archive was published. One in the future is a typo or a machine
    with a wrong clock, and letting it in would make `latest_snapshot` point at a phantom archive
    that every later import then refuses to precede.
    """
    today = datetime.now(UTC).date()
    if value > today:
        raise ValueError(f"snapshot date is in the future: {value.isoformat()} (today is {today.isoformat()})")
    return value


SnapshotDate = Annotated[date, AfterValidator(_reject_future_snapshot_date)]
"""The date a weekly archive was published, as a plain calendar date.

A date, not a timestamp: the archive is "the 15 September 2026 one", and giving it a time of day
would invent precision the source does not have.
"""


# --------------------------------------------------------------------------------------------
# Closed vocabularies
# --------------------------------------------------------------------------------------------


class Event(StrEnum):
    """The debate event a caselist covers.

    Unlike the caselist slug, this really is closed: the three high-school events the platform
    supports decide which sides are legal and which file conventions apply.
    """

    LD = "LD"
    """Lincoln-Douglas."""

    POLICY = "POLICY"
    """Policy (team) debate."""

    PF = "PF"
    """Public Forum."""


class CompetitionLevel(StrEnum):
    """Which circuit a caselist belongs to. `hsld26` is high school; `ndtceda26` is college."""

    HIGH_SCHOOL = "HIGH_SCHOOL"
    COLLEGE = "COLLEGE"
    MIDDLE_SCHOOL = "MIDDLE_SCHOOL"


class Side(StrEnum):
    """The side a disclosed file was read on.

    LD and Policy debate affirmative and negative; Public Forum debates pro and con. `UNKNOWN` is
    legal for every event and is what the importer records when a filename cannot be parsed —
    a file is never dropped for having an unreadable name (v1-e30-t03 ac1).
    """

    AFF = "AFF"
    NEG = "NEG"
    PRO = "PRO"
    CON = "CON"
    UNKNOWN = "UNKNOWN"


_SIDES_BY_EVENT: dict[Event, frozenset[Side]] = {
    Event.LD: frozenset({Side.AFF, Side.NEG, Side.UNKNOWN}),
    Event.POLICY: frozenset({Side.AFF, Side.NEG, Side.UNKNOWN}),
    Event.PF: frozenset({Side.PRO, Side.CON, Side.UNKNOWN}),
}


def sides_for_event(event: Event) -> frozenset[Side]:
    """Return the sides that may be recorded for `event`, `UNKNOWN` always among them."""
    return _SIDES_BY_EVENT[event]


class SourceFormat(StrEnum):
    """The file format a source document arrived in.

    `DOC` and `PDF` are stored but not parsed in V1 — E31 parses `DOCX` — so the format is what
    tells a later pipeline which sources it can and cannot read.
    """

    DOCX = "DOCX"
    DOC = "DOC"
    PDF = "PDF"
    OTHER = "OTHER"


class SourceOrigin(StrEnum):
    """Which import brought a source in."""

    CASELIST_ARCHIVE = "CASELIST_ARCHIVE"
    """A weekly OpenCaselist open-source archive."""

    OPENEV = "OPENEV"
    """An OpenEv camp-file release."""


class Acquisition(StrEnum):
    """How the operator got hold of an archive.

    Recorded because the two are answerable in different ways: a manual download is a file on
    Charlie's Mac, while an API pull (E34) is reproducible from the source.
    """

    MANUAL_DOWNLOAD = "MANUAL_DOWNLOAD"
    API = "API"


# --------------------------------------------------------------------------------------------
# Round labels
# --------------------------------------------------------------------------------------------


class NormalizedRound(StrEnum):
    """The rounds the platform aggregates by.

    Preliminary rounds are `R1`-`R9`; elimination rounds are named. A token that maps to none of
    these normalizes to `None` rather than to a catch-all member, so an unrecognised round is
    visibly unrecognised instead of silently bucketed.
    """

    R1 = "R1"
    R2 = "R2"
    R3 = "R3"
    R4 = "R4"
    R5 = "R5"
    R6 = "R6"
    R7 = "R7"
    R8 = "R8"
    R9 = "R9"
    DOUBLES = "DOUBLES"
    OCTAS = "OCTAS"
    QUARTERS = "QUARTERS"
    SEMIS = "SEMIS"
    FINALS = "FINALS"


#: Elimination-round spellings seen in disclosed filenames, reduced to the round they mean.
ELIMINATION_ROUND_SPELLINGS: dict[str, NormalizedRound] = {
    "doubles": NormalizedRound.DOUBLES,
    "dubs": NormalizedRound.DOUBLES,
    "double octas": NormalizedRound.DOUBLES,
    "double octos": NormalizedRound.DOUBLES,
    "doubleoctas": NormalizedRound.DOUBLES,
    "doubleoctos": NormalizedRound.DOUBLES,
    "doubleoctafinals": NormalizedRound.DOUBLES,
    "double octafinals": NormalizedRound.DOUBLES,
    "octas": NormalizedRound.OCTAS,
    "octos": NormalizedRound.OCTAS,
    "octafinals": NormalizedRound.OCTAS,
    "octofinals": NormalizedRound.OCTAS,
    "quarters": NormalizedRound.QUARTERS,
    "quarterfinals": NormalizedRound.QUARTERS,
    "quads": NormalizedRound.QUARTERS,
    "semis": NormalizedRound.SEMIS,
    "semi": NormalizedRound.SEMIS,
    "semifinals": NormalizedRound.SEMIS,
    "semifinal": NormalizedRound.SEMIS,
    "finals": NormalizedRound.FINALS,
    "final": NormalizedRound.FINALS,
    "grand finals": NormalizedRound.FINALS,
    "gf": NormalizedRound.FINALS,
}

#: `R3`, `Round 3`, `rd3` or a bare `3` — the preliminary-round spellings, as one pattern.
_PRELIMINARY_ROUND_RE = re.compile(r"^(?:r|rd|round)?\s*([1-9])$")

#: Separators that appear between words in a filename token, all flattened to one space.
_TOKEN_SEPARATORS_RE = re.compile(r"[\s_]+")


def normalize_round_token(raw: str) -> NormalizedRound | None:
    """Map one raw round token onto a :class:`NormalizedRound`, or `None` when unrecognised.

    Case, underscores and repeated spaces are insignificant, so `Round_3`, `ROUND 3` and `r3` all
    normalize to `R3`. Everything else — `"Prelims"`, `"Elims"`, `"Round Robin"`, a tournament
    name that ended up in the round position — returns `None` and is kept only as
    :attr:`RoundLabel.raw`, because guessing here would fabricate data about a real round.
    """
    flattened = _TOKEN_SEPARATORS_RE.sub(" ", raw.strip().lower()).strip()
    if not flattened:
        return None
    preliminary = _PRELIMINARY_ROUND_RE.match(flattened)
    if preliminary is not None:
        return NormalizedRound(f"R{preliminary.group(1)}")
    hyphenless = flattened.replace("-", " ")
    return ELIMINATION_ROUND_SPELLINGS.get(flattened) or ELIMINATION_ROUND_SPELLINGS.get(hyphenless)


class RoundLabel(DomainModel):
    """A round as the disclosing team wrote it, plus the round the platform reads it as.

    Both halves matter. `raw` is quotable back to a coach — it is what the file said — while
    `normalized` is what a landscape report groups by. When the token is unrecognised, `normalized`
    is `None` and the label still carries the evidence of what was written.
    """

    raw: NonEmptyText = Field(description="The round token exactly as it appeared in the filename.")
    normalized: NormalizedRound | None = Field(
        default=None,
        description="The round this token was read as, or None when it is not one we recognise.",
    )

    @classmethod
    def from_raw(cls, raw: str) -> Self:
        """Build a label from a raw token, normalizing it with :func:`normalize_round_token`."""
        return cls(raw=raw, normalized=normalize_round_token(raw))

    @property
    def is_recognised(self) -> bool:
        """True when the raw token mapped onto a :class:`NormalizedRound`."""
        return self.normalized is not None

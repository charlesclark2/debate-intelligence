"""Reading a disclosure out of the path a weekly archive filed it under.

OpenCaselist names a disclosed file after the round it was read in::

    <School>/<TeamCode>/<School>-<TeamCode>-<Side>-<Tournament>-<Round>.docx

and then real teams name their files however they like. Across one weekly high-school LD archive
you will find a missing round, a side shouted (`AFF`) or spelled out (`Affirmative`), a Public
Forum side in a Lincoln-Douglas caselist, em dashes, doubled and quadrupled hyphens, a bracketed
copy number, a numeric copy index sitting between the side and the tournament, a browser's
`(1)` re-upload suffix, a filename whose prefix names a school the directories do not, and names
with no structure at all.

**Nothing is ever dropped.** This module's contract is that every path yields a
:class:`ParsedDisclosurePath`: what it could read, and a warning for each thing it could not. A
file whose name is unreadable still becomes a disclosure — with
:attr:`~debate_core.domain.caselist.Side.UNKNOWN`, no tournament and no round — because the file
is still evidence somebody read in a round, and a parser that dropped it would quietly shrink the
corpus by whatever fraction of teams name files badly (v1-e30-t03 ac1).

## How a name is read

1. **The directories are believed over the filename.** School and team code come from the two
   directories above the file, because those are the archive's own structure; the filename's
   prefix is a copy that teams get wrong. A prefix that matches neither is a warning, not an
   override.
2. **The side is the anchor.** Rather than counting hyphens — which breaks the moment a
   tournament has one in its name — the parser finds the first token that is a side and splits
   there: everything before it is the prefix, everything after it is the tournament and the round.
3. **The round is the last token.** With two or more tokens left, the last is the round *by
   position*, whether or not it is a spelling
   :func:`~debate_core.domain.caselist.normalize_round_token` recognises; an unrecognised one is
   still kept as :attr:`~debate_core.domain.caselist.RoundLabel.raw` and warned about. Two- and
   three-word elimination rounds (`Double Octas`) are tried first, so they are not mistaken for
   part of the tournament.
4. **Copy markers are recorded, not discarded.** `(1)`, `[2]` and a trailing `-2` after a round
   are a re-upload or a second file for the same round. They come off the name and are reported
   as :attr:`ParsedDisclosurePath.copy_index`, so the tournament they were stuck to still
   aggregates with every other file from that tournament.

## What it never does

It never widens a team code. `TeamCodeText` caps the code at
:data:`~debate_core.domain.caselist.TEAM_CODE_MAX_LENGTH` characters and rejects whitespace
(v1-e30-t02), and a directory that breaks those rules is almost always a person's name rather
than a code — `docs/policies/caselist-data-use.md` treats every team code as personal data about
a minor. Such a directory yields :data:`UNKNOWN_TEAM_CODE` and a warning that says what was wrong
with it **without quoting it**, so the rejected value does not travel on into a manifest row or a
console.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from debate_core.domain.caselist import (
    TEAM_CODE_MAX_LENGTH,
    Event,
    RoundLabel,
    Side,
    SourceFormat,
    normalize_round_token,
    sides_for_event,
)

__all__ = [
    "SIDE_SPELLINGS",
    "UNKNOWN_SCHOOL",
    "UNKNOWN_TEAM_CODE",
    "ParsedDisclosurePath",
    "parse_disclosure_path",
    "source_format_for",
]

UNKNOWN_SCHOOL = "UNKNOWN"
"""School recorded when the path has no school directory. The literal the caselist models use."""

UNKNOWN_TEAM_CODE = "UNKNOWN"
"""Team code recorded when the directory holding the file is not a usable code.

The same literal :class:`~debate_core.domain.caselist.CampFile` uses for a camp it cannot resolve,
for the same reason: a record with an unreadable field is still a record worth keeping, and the
field says so rather than being absent.
"""

#: Every spelling of a side seen in disclosed filenames, reduced to the side it means. Matched
#: against a whole token and case-insensitively, so a school called `Concord` is never read as CON.
SIDE_SPELLINGS: dict[str, Side] = {
    "aff": Side.AFF,
    "affs": Side.AFF,
    "affirmative": Side.AFF,
    "affirmatives": Side.AFF,
    "neg": Side.NEG,
    "negs": Side.NEG,
    "negative": Side.NEG,
    "negatives": Side.NEG,
    "pro": Side.PRO,
    "pros": Side.PRO,
    "con": Side.CON,
    "cons": Side.CON,
}

#: Extension to stored format. Everything else is OTHER and is stored unparsed like `.doc`.
_FORMATS_BY_EXTENSION: dict[str, SourceFormat] = {
    ".docx": SourceFormat.DOCX,
    ".doc": SourceFormat.DOC,
    ".pdf": SourceFormat.PDF,
}

#: Dashes teams type instead of a hyphen. Flattened before the name is split into tokens.
_DASH_VARIANTS = str.maketrans({"—": "-", "–": "-", "‒": "-", "−": "-"})

#: A trailing copy marker a browser or a re-upload leaves: `… (1)`, `…[2]`, `… - 3`.
_TRAILING_COPY_MARKER = re.compile(r"[\s._-]*[(\[](\d{1,3})[)\]]\s*$")

#: A bracketed copy number anywhere in a tournament: `Bayview Open [2]`.
_BRACKETED_COPY_NUMBER = re.compile(r"\s*[(\[](\d{1,3})[)\]]\s*")

#: Runs of whitespace, to be collapsed to one space.
_WHITESPACE_RUN = re.compile(r"\s+")

#: Punctuation and separators left stranded at either end of a tournament once parts come off.
_STRANDED_EDGES = " \t-_.,;:"

#: How many trailing tokens are tried as one elimination-round name (`Double Octas`).
_LONGEST_ROUND_PHRASE = 3


@dataclass(frozen=True, slots=True)
class ParsedDisclosurePath:
    """Everything one archive path says about one disclosed file.

    Built only by :func:`parse_disclosure_path`. Every field is populated on every path —
    `side` falls back to `UNKNOWN`, `school` and `team_code` to their `UNKNOWN` literals — so a
    caller never has to decide what to do with a half-parsed result. `warnings` is where the
    admissions go, and it is what the manifest row and the landscape reports carry forward.
    """

    source_path: str
    """The member's path relative to the archive root, with `/` separators."""

    school: str
    """The school directory, verbatim, or :data:`UNKNOWN_SCHOOL`."""

    team_code: str
    """The team-code directory, verbatim, or :data:`UNKNOWN_TEAM_CODE`."""

    side: Side
    """The side read from the filename, or `UNKNOWN`. Always legal for the caselist's event."""

    tournament: str | None
    """The tournament as written, cleaned of copy markers; `None` when none could be read."""

    round_label: RoundLabel | None
    """The round as written plus its normalized form; `None` when the name states no round."""

    source_format: SourceFormat
    """DOCX, DOC, PDF or OTHER, from the extension."""

    copy_index: int | None = None
    """The copy number a re-upload marker carried (`(1)`, `[2]`, a trailing `-2`), if any."""

    warnings: tuple[str, ...] = ()
    """What could not be read, in the order it was found. Never quotes a rejected team code."""

    @property
    def is_fully_parsed(self) -> bool:
        """True when the name gave up a side, a tournament and a round with nothing to warn about."""
        return not self.warnings


def source_format_for(filename: str) -> SourceFormat:
    """Return the stored format for a filename's extension.

    Public because the archive reader reports a format for members the parser never sees, and
    because the two must agree on what `.doc` is: a stored, unparsed source, not an `OTHER`.
    """
    return _FORMATS_BY_EXTENSION.get(PurePosixPath(filename).suffix.lower(), SourceFormat.OTHER)


def parse_disclosure_path(relative_path: str, *, event: Event) -> ParsedDisclosurePath:
    """Read one archive path into the fields a :class:`~debate_core.domain.caselist.Disclosure` needs.

    `relative_path` is the member's path relative to the archive root, `/`-separated:
    `Maple Grove/QX/Maple Grove-QX-Aff-Grove City Invitational-Round 1.docx`. `event` decides which
    sides are legal, so a `Pro` in a Lincoln-Douglas caselist is recorded as `UNKNOWN` with a
    warning rather than as a side the domain would refuse.

    Never raises. A path this function cannot make sense of comes back as a fully populated
    result whose `warnings` say so.
    """
    warnings: list[str] = []
    path = PurePosixPath(relative_path)
    school, team_code = _school_and_team_from_directories(path, warnings)
    stem, copy_index = _strip_trailing_copy_markers(path.stem)
    tokens = _tokens_of(stem)

    anchor = _index_of_side_token(tokens)
    if anchor is None:
        warnings.append("filename states no side, so the tournament and round could not be located in it")
        return ParsedDisclosurePath(
            source_path=path.as_posix(),
            school=school,
            team_code=team_code,
            side=Side.UNKNOWN,
            tournament=None,
            round_label=None,
            source_format=source_format_for(path.name),
            copy_index=copy_index,
            warnings=tuple(warnings),
        )

    side = _side_for_event(tokens[anchor], event, warnings)
    if anchor > 0 and not _prefix_names_this_team(tokens[:anchor], school, team_code):
        warnings.append(
            "filename prefix names neither the school nor the team code of the directories it is in"
        )

    remainder = tokens[anchor + 1 :]
    remainder, index_from_remainder = _take_copy_index(remainder)
    tournament, round_label = _split_tournament_and_round(remainder, warnings)
    tournament, index_from_tournament = _take_bracketed_copy_number(tournament)

    return ParsedDisclosurePath(
        source_path=path.as_posix(),
        school=school,
        team_code=team_code,
        side=side,
        tournament=tournament,
        round_label=round_label,
        source_format=source_format_for(path.name),
        copy_index=copy_index or index_from_remainder or index_from_tournament,
        warnings=tuple(warnings),
    )


# ------------------------------------------------------------------------------------------------
# The directories
# ------------------------------------------------------------------------------------------------


def _school_and_team_from_directories(path: PurePosixPath, warnings: list[str]) -> tuple[str, str]:
    """Take the school and team code from the two directories above the file.

    The archive's own structure, and therefore more trustworthy than the filename's copy of it.
    A file filed shallower than `<School>/<TeamCode>/` keeps whatever it does name and warns about
    the rest.
    """
    directories = path.parts[:-1]
    if len(directories) >= 2:
        school = _school_or_unknown(directories[-2], warnings)
        return school, _team_code_or_unknown(directories[-1], warnings)
    if len(directories) == 1:
        warnings.append("file is not inside a team-code directory")
        return _school_or_unknown(directories[0], warnings), UNKNOWN_TEAM_CODE
    warnings.append("file is not inside a school or team-code directory")
    return UNKNOWN_SCHOOL, UNKNOWN_TEAM_CODE


def _school_or_unknown(directory: str, warnings: list[str]) -> str:
    """The school directory verbatim, or the `UNKNOWN` literal with a warning."""
    name = directory.strip()
    if not name:
        warnings.append("school directory is empty")
        return UNKNOWN_SCHOOL
    return name


def _team_code_or_unknown(directory: str, warnings: list[str]) -> str:
    """The team-code directory verbatim, if it is a code the domain accepts.

    A directory with whitespace in it is a pair of names, not a code, and one longer than
    :data:`~debate_core.domain.caselist.TEAM_CODE_MAX_LENGTH` is not a code either. Both are
    refused, and **the warning does not repeat the value**: a whitespace-separated "team code" is
    the case most likely to be somebody's actual name, and a manifest row or a console line
    carrying it would be exactly what `docs/policies/caselist-data-use.md` forbids.
    """
    code = directory.strip()
    if not code:
        warnings.append("team-code directory is empty")
        return UNKNOWN_TEAM_CODE
    if any(character.isspace() for character in code):
        warnings.append(
            "team-code directory contains whitespace, so it is a name rather than a disclosed "
            "code and was not stored"
        )
        return UNKNOWN_TEAM_CODE
    if len(code) > TEAM_CODE_MAX_LENGTH:
        warnings.append(
            f"team-code directory is longer than the {TEAM_CODE_MAX_LENGTH} characters a "
            "disclosed code may have and was not stored"
        )
        return UNKNOWN_TEAM_CODE
    return code


# ------------------------------------------------------------------------------------------------
# The filename
# ------------------------------------------------------------------------------------------------


def _tokens_of(stem: str) -> list[str]:
    """Split a filename stem into hyphen-separated tokens, tolerating how teams type hyphens.

    Em, en and figure dashes are flattened to hyphens first, and the empty tokens that `--` and
    `----` produce are dropped — teams double a hyphen far more often than they mean an empty
    field.
    """
    flattened = stem.translate(_DASH_VARIANTS)
    return [token.strip() for token in flattened.split("-") if token.strip()]


def _index_of_side_token(tokens: list[str]) -> int | None:
    """The position of the first token that is a side, or `None` when no token is one.

    The anchor the rest of the parse hangs off. Matched against the whole token, so `Concord` and
    `Proctor` are not sides.
    """
    for position, token in enumerate(tokens):
        if token.strip().lower() in SIDE_SPELLINGS:
            return position
    return None


def _side_for_event(token: str, event: Event, warnings: list[str]) -> Side:
    """The side this token means, if that side is one this event debates.

    A Public Forum side in a Lincoln-Douglas caselist is a real thing that happens — a team files
    under the wrong caselist, or copies a teammate's filename — and the domain will not store it
    (`sides_for_event`). It becomes `UNKNOWN` with a warning, and the anchor is still used to
    split the tournament and round, because the rest of the name is still structured.
    """
    side = SIDE_SPELLINGS[token.strip().lower()]
    if side in sides_for_event(event):
        return side
    warnings.append(f"filename states side {side.value}, which {event.value} does not debate")
    return Side.UNKNOWN


def _prefix_names_this_team(prefix_tokens: list[str], school: str, team_code: str) -> bool:
    """Whether the tokens before the side name the school or team the directories name.

    Deliberately lenient: teams abbreviate their school in the filename (`Northgate` for
    `Northgate Prep`) far more often than they file under the wrong team. A prefix that carries
    the team code, or that begins with the school, is the ordinary case; anything else is worth a
    warning but never an override.

    A file with no school or team-code directory has already been warned about for exactly that,
    and there is nothing left for its prefix to disagree with — so it is not warned about twice.
    """
    if school == UNKNOWN_SCHOOL and team_code == UNKNOWN_TEAM_CODE:
        return True
    prefix = _comparison_key("".join(prefix_tokens))
    if not prefix:
        return True
    code = _comparison_key(team_code)
    if code and code != _comparison_key(UNKNOWN_TEAM_CODE) and code in prefix:
        return True
    name = _comparison_key(school)
    return bool(name) and (prefix.startswith(name) or name.startswith(prefix))


def _comparison_key(value: str) -> str:
    """Lowercase letters and digits only, for comparing a filename's spelling with a directory's."""
    return "".join(character for character in value.lower() if character.isalnum())


def _strip_trailing_copy_markers(stem: str) -> tuple[str, int | None]:
    """Take `(1)` or `[2]` off the end of a stem and report the number it carried.

    Repeated because a file downloaded twice picks up two: `… (1) (2)`. The last marker wins,
    which is the one the copy actually is.
    """
    copy_index: int | None = None
    remaining = stem.strip()
    while (matched := _TRAILING_COPY_MARKER.search(remaining)) is not None:
        if copy_index is None:
            copy_index = int(matched.group(1))
        remaining = remaining[: matched.start()].strip()
    return remaining, copy_index


def _take_copy_index(tokens: list[str]) -> tuple[list[str], int | None]:
    """Remove a purely numeric copy index from either end of the tokens after the side.

    Two real shapes, and neither is a tournament or a round:

    * `…-Neg-02----Ridgeline Round Robin-Round 6` — a number right after the side, distinguishing
      one of several files a team filed for that side.
    * `…-Seaside Cup-Round 6-2` — a number after a round that is already readable, which is a
      second copy of that round rather than a second round.
    """
    remaining = list(tokens)
    copy_index: int | None = None
    if len(remaining) >= 2 and remaining[0].isdigit():
        copy_index = int(remaining[0])
        remaining = remaining[1:]
    if (
        copy_index is None
        and len(remaining) >= 2
        and remaining[-1].isdigit()
        and normalize_round_token(remaining[-2]) is not None
    ):
        copy_index = int(remaining[-1])
        remaining = remaining[:-1]
    return remaining, copy_index


def _split_tournament_and_round(
    tokens: list[str], warnings: list[str]
) -> tuple[str | None, RoundLabel | None]:
    """Split the tokens after the side into a tournament and a round.

    The round is the *last* token by position, because that is what the naming convention says,
    and it is kept whether or not it is a spelling the platform recognises — an unrecognised
    round is visibly unrecognised (`RoundLabel.normalized is None`) rather than silently dropped.
    Two- and three-token elimination names are tried first so `Double Octas` is not half
    tournament and half round.
    """
    if not tokens:
        warnings.append("filename states no tournament")
        warnings.append("filename states no round")
        return None, None

    for length in range(min(_LONGEST_ROUND_PHRASE, len(tokens)), 1, -1):
        phrase = " ".join(tokens[-length:])
        if normalize_round_token(phrase) is not None:
            return _cleaned_tournament(tokens[:-length], warnings), RoundLabel.from_raw(phrase)

    if len(tokens) == 1:
        only = tokens[0]
        if normalize_round_token(only) is not None:
            warnings.append("filename states no tournament")
            return None, RoundLabel.from_raw(only)
        warnings.append("filename states no round")
        return _cleaned_tournament(tokens, warnings), None

    label = RoundLabel.from_raw(tokens[-1])
    if not label.is_recognised:
        warnings.append("round token in the filename is not one the platform recognises")
    return _cleaned_tournament(tokens[:-1], warnings), label


def _cleaned_tournament(tokens: list[str], warnings: list[str]) -> str | None:
    """Join the tournament tokens back up and tidy what the split left behind."""
    joined = _WHITESPACE_RUN.sub(" ", " ".join(tokens)).strip(_STRANDED_EDGES)
    if not joined:
        warnings.append("filename states no tournament")
        return None
    return joined


def _take_bracketed_copy_number(tournament: str | None) -> tuple[str | None, int | None]:
    """Lift `[2]` out of a tournament name, so `Bayview Open [2]` aggregates with `Bayview Open`."""
    if tournament is None:
        return None, None
    matched = _BRACKETED_COPY_NUMBER.search(tournament)
    if matched is None:
        return tournament, None
    stripped = _BRACKETED_COPY_NUMBER.sub(" ", tournament)
    cleaned = _WHITESPACE_RUN.sub(" ", stripped).strip(_STRANDED_EDGES)
    return (cleaned or None), int(matched.group(1))

"""Which camp an OpenEv file came from, and what the file is called once the camp is taken off.

One path in — relative to the root of whatever the operator downloaded — and a camp, an optional
lab, a file title and a source format out, with warnings for everything that could not be read.
It is the OpenEv importer's metadata extractor, the counterpart of
:mod:`debate_core.application.caselist.path_parser` for caselist disclosures.

## Where the camp comes from

Camp files reach the operator in three shapes. The OpenEv site files them as
`<year>/<camp>/<lab>/<file>`, so a download of several can keep that folder structure. A file
fetched on its own may carry its camp as a filename prefix, `DDI - Politics DA.docx`. And the
real release the v1-e30-t06 backfill imported names the camp *after* the title, before the year,
with the lab's initials last — `<title> - <camp> <year> <initials>` — in folders named for the kind
of argument rather than for the camp. All three are read:

1. **A folder.** A directory in the path whose whole name is a spelling in the alias table. The
   directory directly below it, if there is one, is the lab.
2. **A word of the filename.** Every run of whole words in the filename's stem that is a spelling
   in the same table, wherever it sits: start, middle or end. Matching is by whole word, never by
   substring — `SDI` is not found in `SDIX`, nor `Michigan` in `Michiganders` — and at each word
   the longest spelling is tried first, so `Spartan Debate Institute` is one match, not three.

The folder wins: it is where OpenEv itself filed the file. When the filename names a different
camp, the folder's is recorded and the disagreement is a warning.

Without a camp folder, the filename has to name **exactly one** camp. Two different camps in one
filename (`Dartmouth Rebuttals - Michigan 2026`) is :data:`UNKNOWN_CAMP` with a warning naming
both, never a guess at which is the camp and which is part of the title. The same camp named
twice is that camp. Two folders naming different camps are treated the same way.

When nothing names a camp the table knows, the camp is :data:`UNKNOWN_CAMP` with a warning, and
the file is imported regardless (ac1): a file with an unreadable camp is still evidence. Nothing
outside the table is ever a camp, however camp-like it looks: an operator who meets a new camp
adds it to the table (`v1-e30-t08`).

## The file title

The filename's stem, without the extension and without its *camp block*: the camp's words, the
year directly after them, and lab initials directly after that year if they end the name. So
`Politics DA - DDI 2026 ABC.docx` is `Politics DA`, `GDI_Topicality.docx` is `Topicality`, and
`Politics DA.docx` in a `DDI/` folder is `Politics DA`.

* **The year** is a four-digit `19xx` or `20xx` word immediately after the camp's words. A year
  anywhere else stays in the title.
* **Lab initials** are one to four capital letters immediately after that year, followed by
  nothing but separators or a browser's copy marker such as `(1)`. `Aff` is not initials, and
  nor is anything that does not end the name.
* What was before the camp block and what was after it are joined by a single space, with the
  separators at the join (` - `, `_`, `.`) dropped: `Saltmarsh T - UTNIF 2026 (1)` is
  `Saltmarsh T (1)`.
* When a camp is named twice, the occurrence followed by a year is the block; failing that, the
  first.

A file whose camp is :data:`UNKNOWN_CAMP` keeps its whole stem, because without a camp there is
no block to find, and guessing which words were the camp would lose information the path still
has. A filename that is nothing *but* its camp block keeps its whole stem rather than having no
title. With a camp folder and a filename naming a different single camp, that camp's block is
still taken off.

The scheduled sync (`v1-e34-t02`) saves each downloaded file as `openev-<id>-<file name>`
(:func:`debate_core.integrations.opencaselist.openev.openev_inbox_name`). That inbox prefix is
taken off before anything else, so a file fetched by the sync parses exactly as the same file
downloaded by hand.

## The alias table

`camp_aliases.yaml`, beside this module, and editable: an operator who meets a new camp adds it
there, or passes another table with `--camp-aliases`. Matching compares words, ignoring case and
treating spaces, hyphens, underscores and dots alike, so one spelling covers every way a filename
separates it. Two camps claiming one spelling is refused when the table is loaded
(:class:`InvalidCampAliases`), since which of them a file would get would otherwise depend on the
order the file happened to list them in.

## What is never here

A camp is an institution and a file title is a document's name. Neither is personal data, but a
lab is sometimes named after the instructors who ran it, so the lab is kept only where the path it
came from already is — the manifest — and is not a field of
:class:`~debate_core.domain.caselist.CampFile`.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from importlib import resources
from pathlib import Path, PurePosixPath
from typing import Final, cast

import yaml

from debate_core.application.caselist.path_parser import source_format_for
from debate_core.application.settings import ConfigurationError
from debate_core.domain.caselist import SourceFormat

__all__ = [
    "CAMP_ALIASES_RESOURCE",
    "UNKNOWN_CAMP",
    "CampAliases",
    "InvalidCampAliases",
    "ParsedCampPath",
    "load_camp_aliases",
    "parse_camp_path",
]

UNKNOWN_CAMP: Final = "UNKNOWN"
"""The camp recorded when neither the folders nor the filename name one the table knows."""

CAMP_ALIASES_RESOURCE: Final = "camp_aliases.yaml"
"""The packaged alias table, beside this module."""

#: A word, for matching: a run of letters and digits. Everything else separates words.
_WORD: Final = re.compile(r"[^\W_]+")

#: The prefix `openev_inbox_name` gives a file the scheduled sync downloads.
_INBOX_PREFIX: Final = re.compile(r"^openev-[0-9]+-")

#: The separators dropped where a camp block is cut out of a title: whitespace, `-`, `_`, `.` and
#: the dashes a word processor substitutes for a hyphen. Brackets are not, so a `(1)` survives.
_SEPARATORS: Final = r"[\s\-_.–—]"
_LEADING_SEPARATORS: Final = re.compile(rf"^{_SEPARATORS}+")
_TRAILING_SEPARATORS: Final = re.compile(rf"{_SEPARATORS}+$")

#: A topic year, as a whole word directly after a camp's words.
_YEAR: Final = re.compile(r"(?:19|20)[0-9]{2}")

#: Lab initials directly after that year, ending the name but for separators and a copy marker.
_TRAILING_INITIALS: Final = re.compile(
    rf"{_SEPARATORS}*[A-Z]{{1,4}}(?=(?:{_SEPARATORS}*\([0-9]+\))?{_SEPARATORS}*$)"
)

#: Warnings, as written into the camp-file record and the manifest. They name no path or file.
_UNRESOLVED_WARNING: Final = (
    "no folder and no word of the filename names a camp in the alias table; camp recorded as UNKNOWN"
)


class InvalidCampAliases(ConfigurationError):
    """The alias table is not a mapping of camps to spellings, or two camps share a spelling."""

    def __init__(self, message: str, *, source: str) -> None:
        super().__init__(message, field="camps", source=source)


def _words(text: str) -> tuple[str, ...]:
    """`text` as the case-folded words matching compares."""
    return tuple(word.casefold() for word in _WORD.findall(text))


def _mapping(value: object) -> dict[object, object] | None:
    """`value` as a mapping from parsed YAML, or `None` when it is not one."""
    return cast("dict[object, object]", value) if isinstance(value, dict) else None


def _texts(value: object) -> list[str] | None:
    """`value` as a list of strings from parsed YAML, or `None` when it is not one."""
    if not isinstance(value, list):
        return None
    texts = [item for item in cast("list[object]", value) if isinstance(item, str)]
    return texts if len(texts) == len(cast("list[object]", value)) else None


@dataclass(frozen=True, slots=True)
class CampAliases:
    """The alias table, indexed for matching: every spelling's words, to the camp they name."""

    by_words: Mapping[tuple[str, ...], str]
    """Each spelling as its case-folded words, mapped to the canonical camp name."""

    @property
    def camps(self) -> tuple[str, ...]:
        """Every canonical camp name, sorted."""
        return tuple(sorted(set(self.by_words.values())))

    @property
    def longest_spelling(self) -> int:
        """How many words the longest spelling has; how far a prefix match need look."""
        return max((len(words) for words in self.by_words), default=0)

    @classmethod
    def from_document(cls, document: object, *, source: str) -> CampAliases:
        """Build the index from a parsed `camp_aliases.yaml`, refusing anything malformed."""
        table = _mapping(document)
        camps = _mapping(table.get("camps")) if table is not None else None
        if not camps:
            raise InvalidCampAliases(
                f"{source} must be a mapping whose `camps` key maps each camp to its spellings",
                source=source,
            )
        by_words: dict[tuple[str, ...], str] = {}
        for camp, spellings in camps.items():
            if not isinstance(camp, str) or not _words(camp) or camp.strip() != camp:
                raise InvalidCampAliases(f"{source}: {camp!r} is not a usable camp name", source=source)
            listed = _texts([] if spellings is None else spellings)
            if listed is None:
                raise InvalidCampAliases(
                    f"{source}: the spellings of {camp} must be a list of text", source=source
                )
            for spelling in (camp, *listed):
                words = _words(spelling)
                if not words:
                    raise InvalidCampAliases(f"{source}: {camp} has a spelling with no words", source=source)
                claimed = by_words.setdefault(words, camp)
                if claimed != camp:
                    raise InvalidCampAliases(
                        f"{source}: {spelling!r} is listed for both {claimed} and {camp}", source=source
                    )
        return cls(by_words=by_words)

    def camp_for(self, text: str) -> str | None:
        """The camp `text` names as a whole — a folder name — or `None`."""
        return self.by_words.get(_words(text))


def load_camp_aliases(path: Path | None = None) -> CampAliases:
    """Load the alias table from `path`, or the packaged `camp_aliases.yaml` when `path` is `None`.

    Raises :class:`InvalidCampAliases` for a file that is not valid YAML or not a usable table.
    """
    if path is None:
        source = CAMP_ALIASES_RESOURCE
        text = (
            resources.files(__package__ or __name__)
            .joinpath(CAMP_ALIASES_RESOURCE)
            .read_text(encoding="utf-8")
        )
    else:
        source = str(path)
        try:
            text = Path(path).read_text(encoding="utf-8")
        except OSError as unreadable:
            raise InvalidCampAliases(
                f"{source} could not be read: {unreadable.strerror}", source=source
            ) from None
    try:
        document: object = yaml.safe_load(text)
    except yaml.YAMLError:
        raise InvalidCampAliases(f"{source} is not valid YAML", source=source) from None
    return CampAliases.from_document(document, source=source)


@dataclass(frozen=True, slots=True)
class ParsedCampPath:
    """Everything the OpenEv importer records about one file, read from its path alone."""

    source_path: str
    """The path this was read from, relative to the download's root."""

    camp: str
    """The canonical camp, or :data:`UNKNOWN_CAMP`."""

    lab: str | None
    """The folder directly below the camp's folder, or `None` when there is none."""

    file_title: str
    """The filename without its extension and without a camp prefix."""

    source_format: SourceFormat
    warnings: tuple[str, ...] = ()
    """What could not be read, in the order it was found. Names no path or file."""

    @property
    def camp_resolved(self) -> bool:
        return self.camp != UNKNOWN_CAMP


def parse_camp_path(relative_path: str, *, aliases: CampAliases) -> ParsedCampPath:
    """Read the camp, lab and file title out of one path. Never raises for a name it cannot read."""
    path = PurePosixPath(relative_path)
    warnings: list[str] = []

    folder_camps, lab = _camps_and_lab_from_folders(path.parts[:-1], aliases)
    filename = _INBOX_PREFIX.sub("", path.name)
    stem = PurePosixPath(filename).stem or filename
    matches = _camp_matches(stem, aliases)
    filename_camps = sorted({match.camp for match in matches})

    camp: str | None = None
    if len(folder_camps) > 1:
        warnings.append(_more_than_one_camp("the folders name", folder_camps))
        lab = None
    elif folder_camps:
        (camp,) = folder_camps
        others = [named for named in filename_camps if named != camp]
        if others:
            warnings.append(
                f"the filename names camp {', '.join(others)} but the folder names {camp}; "
                "the folder's camp is recorded"
            )
    elif len(filename_camps) > 1:
        warnings.append(_more_than_one_camp("the filename names", filename_camps))
    elif filename_camps:
        (camp,) = filename_camps
    else:
        warnings.append(_UNRESOLVED_WARNING)

    return ParsedCampPath(
        source_path=relative_path,
        camp=camp or UNKNOWN_CAMP,
        lab=lab,
        file_title=_title(stem, _camp_block(stem, matches, camp, filename_camps)),
        source_format=source_format_for(path.name),
        warnings=tuple(warnings),
    )


@dataclass(frozen=True, slots=True)
class _CampMatch:
    """One run of whole words in a filename's stem that is a spelling in the alias table."""

    camp: str
    start: int
    """Where the spelling's first word starts in the stem."""
    end: int
    """Where its last word ends."""


def _camp_matches(stem: str, aliases: CampAliases) -> tuple[_CampMatch, ...]:
    """Every spelling in `stem`, left to right, by whole words, longest spelling first at each word.

    Never a substring: a spelling's words must be whole words of the stem, so `SDI` is not found
    in `SDIX`. Matches do not overlap, so `Spartan Debate Institute` is one match, not three.
    """
    words = list(_WORD.finditer(stem))
    found: list[_CampMatch] = []
    index = 0
    while index < len(words):
        for length in range(min(aliases.longest_spelling, len(words) - index), 0, -1):
            spelling = tuple(word.group().casefold() for word in words[index : index + length])
            camp = aliases.by_words.get(spelling)
            if camp is not None:
                found.append(_CampMatch(camp, words[index].start(), words[index + length - 1].end()))
                index += length
                break
        else:
            index += 1
    return tuple(found)


def _more_than_one_camp(where: str, camps: list[str]) -> str:
    return f"{where} more than one camp in the alias table ({', '.join(camps)}); camp recorded as UNKNOWN"


def _camps_and_lab_from_folders(
    folders: tuple[str, ...], aliases: CampAliases
) -> tuple[list[str], str | None]:
    """Every camp a whole folder name names, sorted, and the folder below the outermost one as the lab."""
    camps: set[str] = set()
    lab: str | None = None
    for index, folder in enumerate(folders):
        camp = aliases.camp_for(folder)
        if camp is None:
            continue
        if not camps:
            lab = folders[index + 1] if index + 1 < len(folders) else None
        camps.add(camp)
    return sorted(camps), lab


def _camp_block(
    stem: str, matches: tuple[_CampMatch, ...], camp: str | None, named: list[str]
) -> _CampMatch | None:
    """The match whose words, year and initials come off the title, or `None` to keep the stem.

    The recorded camp's match; with a camp folder and a filename naming one other camp, that
    camp's. Of several, the last one followed by a year, else the first.
    """
    if camp is None:
        return None
    wanted = camp if camp in named else named[0] if len(named) == 1 else None
    candidates = [match for match in matches if match.camp == wanted]
    followed_by_year = [match for match in candidates if _year_after(stem, match.end) is not None]
    if followed_by_year:
        return followed_by_year[-1]
    return candidates[0] if candidates else None


def _title(stem: str, block: _CampMatch | None) -> str:
    """`stem` without `block`: its words, the year directly after them, and lab initials after that."""
    if block is None:
        return stem
    end = block.end
    year = _year_after(stem, end)
    if year is not None:
        end = year.end()
        initials = _TRAILING_INITIALS.match(stem, end)
        end = initials.end() if initials is not None else end
    before = _TRAILING_SEPARATORS.sub("", stem[: block.start])
    after = _LEADING_SEPARATORS.sub("", stem[end:])
    return (f"{before} {after}" if before and after else before or after) or stem


def _year_after(stem: str, position: int) -> re.Match[str] | None:
    """The year that is the next word after `position`, with only separators between, if there is one."""
    word = _WORD.search(stem, position)
    if word is None or _LEADING_SEPARATORS.sub("", stem[position : word.start()]):
        return None
    return word if _YEAR.fullmatch(word.group()) else None

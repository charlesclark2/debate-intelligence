"""Which camp an OpenEv file came from, and what the file is called once the camp is taken off.

One path in — relative to the root of whatever the operator downloaded — and a camp, an optional
lab, a file title and a source format out, with warnings for everything that could not be read.
It is the OpenEv importer's metadata extractor, the counterpart of
:mod:`debate_core.application.caselist.path_parser` for caselist disclosures.

## Where the camp comes from

Camp files reach the operator in two shapes. The OpenEv site files them as
`<year>/<camp>/<lab>/<file>`, so a download of several keeps that folder structure; and a file
fetched on its own usually carries its camp as a filename prefix, `DDI - Politics DA.docx` or
`GDI_Topicality.docx`. Both are read:

1. **A folder.** The outermost directory in the path that names a camp in the alias table. The
   directory directly below it, if there is one, is the lab.
2. **A filename prefix.** The leading words of the filename, matched against the same table,
   longest spelling first.

A folder is the stronger evidence — it is where OpenEv itself filed the file — so when both name a
camp and they disagree, the folder's is recorded and the disagreement is a warning. When neither
names one, the camp is :data:`UNKNOWN_CAMP` with a warning, and the file is imported regardless
(ac1): a file with an unreadable camp is still evidence.

## The file title

The filename without its extension and without the camp prefix, if the filename had one:
`GDI_Topicality.docx` is `Topicality`, and `Politics DA.docx` in a `DDI/` folder is `Politics DA`.
Nothing else is taken off — a year, a lab name or a side in the filename stays in the title,
because what counts as noise in a title differs camp by camp and a wrong guess loses information
that the path still has. A filename that is nothing *but* a camp keeps its whole stem as the
title rather than having none.

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

#: What may sit between a camp prefix and the title: separators and whitespace.
_LEADING_SEPARATORS: Final = re.compile(r"^[\W_]+")

#: Warnings, as written into the camp-file record and the manifest. They name no path or file.
_UNRESOLVED_WARNING: Final = (
    "no folder and no filename prefix names a camp in the alias table; camp recorded as UNKNOWN"
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

    folder_camp, lab = _camp_and_lab_from_folders(path.parts[:-1], aliases)
    filename = _INBOX_PREFIX.sub("", path.name)
    stem = PurePosixPath(filename).stem or filename
    prefix_camp, title = _camp_prefix_and_title(stem, aliases)

    if folder_camp is not None and prefix_camp is not None and folder_camp != prefix_camp:
        warnings.append(
            f"the filename prefix names camp {prefix_camp} but the folder names {folder_camp}; "
            "the folder's camp is recorded"
        )
    camp = folder_camp or prefix_camp
    if camp is None:
        warnings.append(_UNRESOLVED_WARNING)

    return ParsedCampPath(
        source_path=relative_path,
        camp=camp or UNKNOWN_CAMP,
        lab=lab,
        file_title=title,
        source_format=source_format_for(path.name),
        warnings=tuple(warnings),
    )


def _camp_and_lab_from_folders(
    folders: tuple[str, ...], aliases: CampAliases
) -> tuple[str | None, str | None]:
    """The outermost folder naming a camp, and the folder directly below it as the lab."""
    for index, folder in enumerate(folders):
        camp = aliases.camp_for(folder)
        if camp is not None:
            lab = folders[index + 1] if index + 1 < len(folders) else None
            return camp, lab
    return None, None


def _camp_prefix_and_title(stem: str, aliases: CampAliases) -> tuple[str | None, str]:
    """The camp the stem's leading words name, and the stem with those words taken off.

    Tries the longest spelling first, so `Spartan Debate Institute - K` is SDI with title `K`
    rather than a match on `Spartan` leaving `Debate Institute - K`.
    """
    matches = list(_WORD.finditer(stem))
    for length in range(min(aliases.longest_spelling, len(matches)), 0, -1):
        words = tuple(match.group().casefold() for match in matches[:length])
        camp = aliases.by_words.get(words)
        if camp is None:
            continue
        title = _LEADING_SEPARATORS.sub("", stem[matches[length - 1].end() :]).strip()
        return camp, title or stem
    return None, stem

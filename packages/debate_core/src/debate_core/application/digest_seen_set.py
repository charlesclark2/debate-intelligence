"""What a preset's daily digests have already listed, so the next one does not list it again (v1-e08-t07).

A :class:`DigestSeenSet` keeps, for one preset, every source its digests listed, by **canonical URL**
and by **DOI**, each with the date of the digest that first listed it. A source is listed before when
any one of its keys is: a paper listed under its DOI and found the next day at a publisher's URL is
the same paper (:func:`source_keys`).

**The same date is not an earlier digest.** A key recorded under the date being built was listed by
this date's own digest, which a second run of that date replaces; the second run lists it again, so
running a date twice gives the same digest rather than an empty one. A key recorded under any other
date was in another digest, and is left out.

## Where it is kept

:class:`FileDigestSeenStore` keeps one JSON file per preset, `<directory>/<preset>.json`, in the
CLI's local data directory (`<data dir>/daily/seen/`): never in the repository, never in a bucket
(the PM's ruling of 2026-11-09). A save writes a temporary file beside it, fsyncs it, renames it
over the name and fsyncs the directory, so a crash leaves the old file or the new one, never half of
one. A file that cannot be read is an error, not an empty set: an empty set would list again
everything every earlier digest listed.

The digest service saves only after the digest file is written
(:class:`~debate_core.application.digest_service.DigestService`), so a run that fails marks nothing seen.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Final, Literal, Protocol

from pydantic import Field, ValidationError

from debate_core.application.durable_files import fsync_directory
from debate_core.application.federated_dedupe import candidate_canonical_url
from debate_core.application.federated_ranking import RankedCandidate
from debate_core.domain.base import DomainModel, NonEmptyText

__all__ = [
    "SEEN_SET_SCHEMA_VERSION",
    "DigestSeenSet",
    "DigestSeenSetError",
    "DigestSeenStore",
    "FileDigestSeenStore",
    "SourceKeys",
    "source_keys",
]

SEEN_SET_SCHEMA_VERSION: Final = 1


class DigestSeenSetError(ValueError):
    """A preset's seen-set file could not be read or written; the message names the file."""


@dataclass(frozen=True, slots=True)
class SourceKeys:
    """Every key a source is known by: its canonical URLs and its DOIs."""

    urls: frozenset[str]
    dois: frozenset[str]

    def overlaps(self, other: SourceKeys) -> bool:
        """Whether the two share any URL or DOI: the same source."""
        return bool(self.urls & other.urls or self.dois & other.dois)


def source_keys(ranked: RankedCandidate) -> SourceKeys:
    """The canonical URL and DOI of the merged source and of every provider record merged into it.

    Each record's URL is canonicalized as deduplication does it
    (:func:`~debate_core.application.federated_dedupe.candidate_canonical_url`); one with no canonical
    form counts by the URL it was given. DOIs are compared lower case, as
    :class:`~debate_core.domain.ArticleIdentifiers` normalizes them.
    """
    candidate = ranked.candidate
    urls = {candidate.canonical_url or candidate.url}
    urls.update(candidate_canonical_url(member) or member.url for member in candidate.members)
    dois = {candidate.identifiers.doi} | {member.identifiers.doi for member in candidate.members}
    return SourceKeys(urls=frozenset(urls), dois=frozenset(doi.lower() for doi in dois if doi is not None))


class DigestSeenSet(DomainModel):
    """One preset's listed sources: each canonical URL and DOI, with the date that first listed it."""

    schema_version: Literal[1] = Field(default=SEEN_SET_SCHEMA_VERSION, description="This file's shape.")
    preset: NonEmptyText = Field(description="The preset whose digests listed these.")
    urls: dict[str, date] = Field(
        default_factory=dict[str, date], description="Canonical URL -> the digest date that first listed it."
    )
    dois: dict[str, date] = Field(
        default_factory=dict[str, date],
        description="DOI, lower case -> the digest date that first listed it.",
    )

    def listed_before(self, keys: SourceKeys, day: date) -> bool:
        """Whether a digest of another date listed the source under any of its keys."""
        listed = [self.urls[url] for url in keys.urls if url in self.urls]
        listed += [self.dois[doi] for doi in keys.dois if doi in self.dois]
        return any(when != day for when in listed)

    def with_listed(self, sources: Iterable[SourceKeys], day: date) -> DigestSeenSet:
        """This set with every key of `sources` recorded under `day`, unless it already has a date."""
        urls, dois = dict(self.urls), dict(self.dois)
        for keys in sources:
            for url in keys.urls:
                urls.setdefault(url, day)
            for doi in keys.dois:
                dois.setdefault(doi, day)
        return self.evolve(urls=urls, dois=dois)


class DigestSeenStore(Protocol):
    """Where each preset's seen-set is kept between runs."""

    def load(self, preset: str) -> DigestSeenSet:
        """The preset's set, or an empty one if no digest of it was ever written."""
        ...

    def save(self, seen: DigestSeenSet) -> None:
        """Replace the preset's set with `seen`, in one step."""
        ...


class FileDigestSeenStore:
    """Each preset's seen-set as `<directory>/<preset>.json`, replaced in one step on every save."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def path_for(self, preset: str) -> Path:
        """The preset's file."""
        return self._directory / f"{preset}.json"

    def load(self, preset: str) -> DigestSeenSet:
        path = self.path_for(preset)
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return DigestSeenSet(preset=preset)
        except (OSError, UnicodeDecodeError) as error:
            raise DigestSeenSetError(f"{path}: cannot be read: {error}") from error
        try:
            seen = DigestSeenSet.model_validate_json(text)
        except ValidationError as error:
            raise DigestSeenSetError(f"{path}: is not a seen-set: {error}") from error
        if seen.preset != preset:
            raise DigestSeenSetError(f"{path}: holds preset {seen.preset!r}, not {preset!r}")
        return seen

    def save(self, seen: DigestSeenSet) -> None:
        path = self.path_for(seen.preset)
        path.parent.mkdir(parents=True, exist_ok=True)
        document = {
            "schema_version": seen.schema_version,
            "preset": seen.preset,
            "urls": {url: when.isoformat() for url, when in sorted(seen.urls.items())},
            "dois": {doi: when.isoformat() for doi, when in sorted(seen.dois.items())},
        }
        handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(document, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            Path(temporary).replace(path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise
        fsync_directory(path.parent)

"""Which caselists a model cassette answered, and deleting one caselist's cassettes alone (`v1-e32-t31`).

A cassette is filed under its prompt and its call's key
(:mod:`~debate_core.integrations.models.record_replay`), and the key covers the call's prompt, version,
variables and schema, never the caselist. An identical card in two caselists is one call, recorded
once: putting the caselist in the key would ask the model twice for the same answer. So the caselist
is not part of the match. A cassette instead names, beside the request and response it recorded, the
**caselists** it was recorded or replayed for: a set, since one cassette can answer several.

1. :func:`filed_under` names the caselist a block's model calls are made for. The landscape's model
   stage opens it around each call, for the caselist it runs on.
2. The record-and-replay router reads it with :func:`filing_caselist`. Record mode writes the caselist
   into the new cassette, beside those the file at that key already named; replay adds it to a
   cassette that does not name it yet. Neither changes what was recorded, and live mode writes nothing.
3. :func:`caselist_cassettes` lists one caselist's cassettes, and :func:`delete_caselist_cassettes`
   deletes them: a cassette the caselist alone named is deleted, one another caselist also names
   loses only this name and is kept, and one that names no caselist (recorded before this task) is
   reported as unattributed and never deleted by a caselist.

No school, team code or path goes into a cassette: only the caselist's slug, which
:func:`filed_under` refuses unless it is one.
"""

from __future__ import annotations

import re
from collections.abc import Generator, Iterable
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Final, Protocol

from debate_core.domain.caselist import CASELIST_SLUG_PATTERN

__all__ = [
    "CaselistCassettes",
    "CassetteFiles",
    "CassetteFiling",
    "caselist_cassettes",
    "delete_caselist_cassettes",
    "filed_under",
    "filing_caselist",
    "is_caselist_slug",
]

_SLUG: Final = re.compile(CASELIST_SLUG_PATTERN)
_FILING: Final[ContextVar[str | None]] = ContextVar("cassette_filing", default=None)


def is_caselist_slug(value: object) -> bool:
    """Whether `value` is a caselist's slug (`hsld26`): the one thing a cassette may say about a caselist."""
    return isinstance(value, str) and _SLUG.fullmatch(value) is not None


def _refuse_a_non_slug(caselist: str) -> None:
    if not is_caselist_slug(caselist):
        raise ValueError(f"a cassette is filed under a caselist's slug, such as hsld26; got {caselist!r}")


@contextmanager
def filed_under(caselist: str) -> Generator[None, None, None]:
    """File every cassette recorded or replayed inside this block under `caselist`.

    Raises `ValueError` for a value that is not a caselist slug, before any call is made.
    """
    _refuse_a_non_slug(caselist)
    token = _FILING.set(caselist)
    try:
        yield
    finally:
        _FILING.reset(token)


def filing_caselist() -> str | None:
    """The caselist the current block's model calls are filed under; None outside :func:`filed_under`."""
    return _FILING.get()


@dataclass(frozen=True, slots=True)
class CassetteFiling:
    """One cassette on disk, by name, and the caselists it names."""

    cassette: str
    """`<prompt>/<key>.json`, relative to the cassette directory: a prompt id and a digest, nothing else."""
    caselists: frozenset[str]
    """The caselists it was recorded or replayed for; empty for one recorded before `v1-e32-t31`."""


class CassetteFiles(Protocol):
    """A cassette directory, as the per-caselist listing and delete see it."""

    def filings(self) -> Iterable[CassetteFiling]:
        """Every cassette there, with the caselists it names. An unreadable cassette raises."""
        ...

    def delete(self, cassette: str) -> None:
        """Delete `cassette`."""
        ...

    def withdraw(self, cassette: str, caselist: str) -> None:
        """Take `caselist` off `cassette`'s caselists, keeping the cassette and all it recorded."""
        ...


@dataclass(frozen=True, slots=True)
class CaselistCassettes:
    """One caselist's cassettes, by what a delete of that caselist does to each."""

    caselist: str
    sole: tuple[str, ...]
    """Cassettes this caselist alone names: deleted with it."""
    shared: tuple[str, ...]
    """Cassettes another caselist names too: kept, losing only this caselist's name."""
    unattributed: tuple[str, ...]
    """Cassettes that name no caselist: never deleted by a caselist's delete."""
    others: int
    """Cassettes only other caselists name: untouched."""


def caselist_cassettes(files: CassetteFiles, caselist: str) -> CaselistCassettes:
    """What `files` holds of `caselist`, read and changed nothing. Raises `ValueError` for a non-slug."""
    _refuse_a_non_slug(caselist)
    sole: list[str] = []
    shared: list[str] = []
    unattributed: list[str] = []
    others = 0
    for filing in sorted(files.filings(), key=lambda one: one.cassette):
        if not filing.caselists:
            unattributed.append(filing.cassette)
        elif caselist not in filing.caselists:
            others += 1
        elif len(filing.caselists) == 1:
            sole.append(filing.cassette)
        else:
            shared.append(filing.cassette)
    return CaselistCassettes(
        caselist=caselist,
        sole=tuple(sole),
        shared=tuple(shared),
        unattributed=tuple(unattributed),
        others=others,
    )


def delete_caselist_cassettes(files: CassetteFiles, caselist: str) -> CaselistCassettes:
    """Delete `caselist`'s sole cassettes and take its name off the shared ones; what it did, by cassette.

    Everything is listed first, so an unreadable cassette stops the delete before anything changes.
    """
    listed = caselist_cassettes(files, caselist)
    for cassette in listed.shared:
        files.withdraw(cassette, caselist)
    for cassette in listed.sole:
        files.delete(cassette)
    return listed

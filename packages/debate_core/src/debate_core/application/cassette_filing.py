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
4. A delete takes the listing's :attr:`~CaselistCassettes.confirmation` (`v1-e32-t34`), the code
   `debate-research landscape cassettes` prints on its dry run, as `caselist retire` and `tub index
   prune` print theirs. It is a digest of every cassette the delete would change, its sole and its shared
   ones, so a code read before the model stage recorded another of them, or read for another caselist,
   is refused with :class:`CassetteDeleteRefused` before anything changes. The caselist's slug is not
   in it: two caselists' codes agree only when neither names a cassette alone and both share the same
   ones, and then either code takes this caselist's name off those cassettes, which is what its own does.
   Since `v1-e32-t36` the digest also names the delete's form, below.
5. A removal (`v1-e32-t36`) is not a purge: a takedown has to reach every copy of the removed text, and a
   shared cassette holds it for the other caselist too (PM ruling, 2026-10-31).
   :func:`delete_caselist_cassettes_for_removal` deletes every cassette naming the caselist, sole and
   shared, and every unattributed one, since one recorded before `v1-e32-t31` may hold the text. It
   keeps only the cassettes naming other caselists alone; the cost to them is a re-recording, never a
   wrong answer. It takes the listing's :attr:`~CaselistCassettes.removal_confirmation`, a code of its
   own. Both codes digest one shape, the form with the cassettes it deletes and those it takes the name
   off, so where the two deletes would reach the same cassettes (no shared and no unattributed one,
   which is how the first recordings will be) the form is all that tells them apart, and it does: the
   two codes never stand in for each other, since each is read off a dry run that described its own
   form's delete.

No school, team code or path goes into a cassette: only the caselist's slug, which
:func:`filed_under` refuses unless it is one.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Generator, Iterable
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Final, Protocol

from debate_core.application.caselist.version_retention import CONFIRMATION_LENGTH
from debate_core.application.errors import DomainError
from debate_core.domain.caselist import CASELIST_SLUG_PATTERN

__all__ = [
    "CaselistCassettes",
    "CassetteDeleteRefused",
    "CassetteFiles",
    "CassetteFiling",
    "caselist_cassettes",
    "delete_caselist_cassettes",
    "delete_caselist_cassettes_for_removal",
    "filed_under",
    "filing_caselist",
    "is_caselist_slug",
]

_SLUG: Final = re.compile(CASELIST_SLUG_PATTERN)
_FILING: Final[ContextVar[str | None]] = ContextVar("cassette_filing", default=None)
PURGE_FORM: Final = "purge"
REMOVAL_FORM: Final = "removal"
"""Each code names its delete's form, so that neither form's code is ever the other's (`v1-e32-t36`)."""


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

    @property
    def confirmation(self) -> str:
        """The code :func:`delete_caselist_cassettes` takes: the purge, and the cassettes it changes."""
        return _confirmation(PURGE_FORM, deleted=self.sole, withdrawn=self.shared)

    @property
    def removal_confirmation(self) -> str:
        """The code :func:`delete_caselist_cassettes_for_removal` takes: the removal, and what it deletes."""
        return _confirmation(
            REMOVAL_FORM, deleted=(*self.sole, *self.shared, *self.unattributed), withdrawn=()
        )


def _confirmation(form: str, *, deleted: tuple[str, ...], withdrawn: tuple[str, ...]) -> str:
    shown = {"form": form, "deleted": list(deleted), "withdrawn": list(withdrawn)}
    return hashlib.sha256(json.dumps(shown, sort_keys=True).encode()).hexdigest()[:CONFIRMATION_LENGTH]


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


class CassetteDeleteRefused(DomainError):
    """A delete given no code, or not the code of the listing it would act on. Nothing was changed."""

    def __init__(self, listed: CaselistCassettes, confirmation: str | None) -> None:
        self.listed = listed
        """What the delete found, and would have acted on."""
        super().__init__(
            "the confirmation code is not this listing's: list the caselist's cassettes again, read the "
            "listing, and pass the code it prints; nothing was changed"
            if confirmation
            else "pass the confirmation code the listing prints; nothing was changed"
        )


def delete_caselist_cassettes(
    files: CassetteFiles, caselist: str, *, confirmation: str | None
) -> CaselistCassettes:
    """Delete `caselist`'s sole cassettes and take its name off the shared ones; what it did, by cassette.

    Everything is listed first, so an unreadable cassette, or a `confirmation` that is not that
    listing's code (:class:`CassetteDeleteRefused`), stops the delete before anything changes.
    """
    listed = caselist_cassettes(files, caselist)
    if confirmation != listed.confirmation:
        raise CassetteDeleteRefused(listed, confirmation)
    for cassette in listed.shared:
        files.withdraw(cassette, caselist)
    for cassette in listed.sole:
        files.delete(cassette)
    return listed


def delete_caselist_cassettes_for_removal(
    files: CassetteFiles, caselist: str, *, confirmation: str | None
) -> CaselistCassettes:
    """Delete every cassette naming `caselist`, sole and shared, and every unattributed one; what it did.

    Everything is listed first, so an unreadable cassette, or a `confirmation` that is not that listing's
    :attr:`~CaselistCassettes.removal_confirmation` (:class:`CassetteDeleteRefused`), a purge's code
    among them, stops the removal before anything changes.
    """
    listed = caselist_cassettes(files, caselist)
    if confirmation != listed.removal_confirmation:
        raise CassetteDeleteRefused(listed, confirmation)
    for cassette in (*listed.sole, *listed.shared, *listed.unattributed):
        files.delete(cassette)
    return listed

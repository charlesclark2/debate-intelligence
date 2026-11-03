"""What `caselist parse --publish-only` checks before it publishes a version directory (`v1-e31-t30`).

`caselist parse --publish` rebuilds before it publishes, so a publish that failed after its rebuild,
or the same store sent to a second environment's bucket, cost a whole rebuild. `--publish-only`
publishes the directory as the last rebuild left it. It publishes through the one publisher,
:meth:`~debate_core.application.caselist.parsed_publish.ParsedStorePublisher.publish`, called as the
rebuild's publish calls it, so the suppression list, held uploads, the occurrence table guard, the
aggregates going last and the idempotent skip all come with it and are not asked again here.

What is asked here is only what a rebuild would have made true and a publish alone cannot: that
there is a directory, that it is whole, that it is what this build's rebuild would publish, and
that its aggregates name nothing the suppression list of the environment it goes to now stops.

## Which directory

The running parser's current one, the newest generation of its parser version
(:meth:`~debate_core.application.caselist_parse.CaselistParseService.publishable_version`): the one
`--publish` publishes once it has rebuilt. An older version directory is never named or published.

## The refusals

Each is a :class:`PublishOnlyRefused` with its own code and reason, raised before anything is
uploaded, so a refusal leaves the bucket as it was. In the order they are asked:

* :class:`ParsedVersionDirectoryMissing`: the running parser version has no directory here.
* :class:`ParsedAggregatesMissing`: the index, the failures file or the occurrence table is absent.
  A removal deletes all three until the next rebuild, and a run stopped part-way leaves none in a
  new directory.
* :class:`ParsedSourceFilesMissing`: the index names a source with no per-source file.
* :class:`ParsedByAnotherParserVersion`: a per-source record names another parser or style profile
  version than the running parser's. A rebuild would start a new generation and publish that.
* :class:`ParsedFingerprintVersionMismatch`: the occurrence table holds a row stamped with any
  fingerprint version but this build's, or a per-source record is stamped with a newer one.
* :class:`ParsedAggregatesNameWhatTheListStops`: the index names a source, or the occurrence table
  a disclosure, that the target environment's suppression list stops or holds
  (:func:`refuse_what_the_list_stops`).

## Aggregates rebuilt before a removal (`v1-e31-t30` ac4)

A rebuild writes the index, the failures file and the occurrence table without what its suppression
list stops or holds. The publisher withholds a per-source file the target environment's list stops,
but sends the aggregates as they are. So aggregates rebuilt under dev's list and published to prod,
whose list holds a removal dev's lacks, would name what prod removed. `--publish` would have rebuilt
them first. Here they are refused instead, before any upload.

The question is the rebuild's own, asked of the target environment's list: the same
:func:`~debate_core.application.caselist.suppression.load_suppression_state` over the list the
publisher is given, and the predicates the rebuild filters its rows by,
:func:`~debate_core.application.caselist.parse_sources.is_aggregated` for the index and
:func:`~debate_core.application.caselist.parse_sources.live_disclosure_keys` for the occurrence
table, over :func:`~debate_core.application.caselist.parse_sources.enumerate_sources`. Those
answer for a suppressed source, a withdrawn disclosure and a held path alike, through
:func:`~debate_core.application.caselist.parse_sources.live_disclosures`;
:func:`~debate_core.application.caselist.parse_sources.held_only_sources` says how many of the
refused sources are held. No rule of its own is written here.

## The per-source records' fingerprint stamps

A per-source record keeps the fingerprint version in force on the day it was parsed, and nothing in
it depends on that version (`docs/data/parsed-card-store.md`): a fingerprint bump re-parses nothing,
and the next rebuild rewrites only the occurrence table. So a directory this build has just rebuilt
can hold per-source records stamped with an older version, and its rebuild's publish sends them. An
older stamp is therefore not refused; a newer one is, since only a newer build wrote it. The
occurrence table is the file a rebuild stamps whole, and every row of it must carry this build's
version.

The stamps are read through the store: the occurrence table's with
:func:`~debate_core.application.caselist.occurrence_table_guard.fingerprint_stamps_of_file`, under
:meth:`~debate_core.application.ports.parsed_store.ParsedStore.read_occurrence_stamps`, and each
per-source record's from its entry, the first line of its file.

## What is logged

Nothing. A refusal's message names a caselist, a version directory, versions, counts and at most a
few SHA-256 prefixes: never a path, a school, a team code or a file name.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Final

from debate_core.application.caselist.occurrence_table_guard import newer_stamp
from debate_core.application.caselist.parse_sources import (
    DisclosureKey,
    EnumeratedSource,
    held_only_sources,
    is_aggregated,
    live_disclosure_keys,
    occurrence_row_key,
)
from debate_core.application.errors import DomainError
from debate_core.application.ports.parsed_store import ParsedStore, skip_key
from debate_core.application.ports.suppression import SuppressionState
from debate_core.evidence.fingerprints import FINGERPRINT_VERSION

__all__ = [
    "ParsedAggregatesMissing",
    "ParsedAggregatesNameWhatTheListStops",
    "ParsedByAnotherParserVersion",
    "ParsedFingerprintVersionMismatch",
    "ParsedSourceFilesMissing",
    "ParsedVersionDirectoryMissing",
    "PublishOnlyRefused",
    "refuse_unpublishable",
    "refuse_what_the_list_stops",
]

#: How many SHA-256 prefixes a refusal names, and how long each is.
_NAMED_DIGESTS: Final = 3
_DIGEST_PREFIX: Final = 12


class PublishOnlyRefused(DomainError):
    """A version directory `--publish-only` will not publish. Raised before any upload.

    The subclass is the code; :attr:`hint` is what to run instead, which the CLI prints once.
    """

    def __init__(self, message: str, *, caselist: str, version: str | None, hint: str | None = None) -> None:
        self.caselist = caselist
        self.version = version
        self.hint = hint or _rebuild_and_publish(caselist)
        super().__init__(message)


class ParsedVersionDirectoryMissing(PublishOnlyRefused):
    """The running parser version has no directory for the caselist on this machine."""


class ParsedAggregatesMissing(PublishOnlyRefused):
    """The directory has no index, failures file or occurrence table, or lacks one of them."""


class ParsedSourceFilesMissing(PublishOnlyRefused):
    """The index names a source the directory holds no per-source file for."""


class ParsedByAnotherParserVersion(PublishOnlyRefused):
    """A per-source record was parsed under another parser or style profile version."""


class ParsedFingerprintVersionMismatch(PublishOnlyRefused):
    """The occurrence table is not stamped with this build's fingerprint version throughout, or a
    per-source record is stamped with a newer one."""


class ParsedAggregatesNameWhatTheListStops(PublishOnlyRefused):
    """The aggregates name a source or a disclosure the target environment's suppression list now
    stops or holds: they were rebuilt before it did."""


async def refuse_unpublishable(
    store: ParsedStore,
    caselist: str,
    version: str | None,
    *,
    parser_version: str,
    profile_version: str,
) -> str:
    """Return `version` when `--publish-only` may publish it; raise the :class:`PublishOnlyRefused`
    that says why not, in the order the module docstring gives.

    `version` is the running parser's current directory, or `None` when it has none.
    """
    if version is None:
        raise ParsedVersionDirectoryMissing(
            f"{caselist} has no version directory of parser version {parser_version} on this machine",
            caselist=caselist,
            version=None,
        )
    index = await store.read_index(caselist, version)
    failures = await store.read_failures(caselist, version)
    occurrence_stamps = await store.read_occurrence_stamps(caselist, version)
    missing = [
        name
        for name, held in (
            ("index", index),
            ("failures file", failures),
            ("occurrence table", occurrence_stamps),
        )
        if held is None
    ]
    if missing:
        raise ParsedAggregatesMissing(
            f"{caselist} {version} has no {_listed(missing)}: a removal deleted it, or no rebuild "
            "has finished since",
            caselist=caselist,
            version=version,
        )
    assert index is not None and occurrence_stamps is not None
    entries = await store.read_entries(caselist, version)
    recorded = {entry.source_sha256 for entry in entries}
    unfiled = sorted({entry.source_sha256 for entry in index} - recorded)
    if unfiled:
        raise ParsedSourceFilesMissing(
            f"the index of {caselist} {version} names {len(unfiled)} source(s) with no per-source "
            f"file on this machine ({_digests(unfiled)})",
            caselist=caselist,
            version=version,
        )
    other = sorted(
        {
            (entry.parser_version, entry.profile_version)
            for entry in entries
            if entry.skip_key != skip_key(entry.source_sha256, parser_version, profile_version)
        }
    )
    if other:
        raise ParsedByAnotherParserVersion(
            f"{caselist} {version} holds sources parsed under "
            f"{_listed(f'parser {parser} with profile {profile}' for parser, profile in other)}, "
            f"not this build's parser {parser_version} with profile {profile_version}; a rebuild "
            "would start a new generation and publish that",
            caselist=caselist,
            version=version,
        )
    stale = sorted(stamp for stamp in occurrence_stamps if stamp != FINGERPRINT_VERSION)
    if stale:
        raise ParsedFingerprintVersionMismatch(
            f"the occurrence table of {caselist} {version} holds rows stamped {_listed(stale)}, not "
            f"this build's {FINGERPRINT_VERSION}",
            caselist=caselist,
            version=version,
            hint=_hint_for_stamps(caselist, stale),
        )
    # The guard's own comparison, as every newer-than question about a stamp is (`v1-e34-t29`).
    newer = newer_stamp(entry.fingerprint_version for entry in entries)
    if newer is not None:
        raise ParsedFingerprintVersionMismatch(
            f"per-source records of {caselist} {version} are stamped {newer}, newer than this "
            f"build's {FINGERPRINT_VERSION}",
            caselist=caselist,
            version=version,
            hint=_hint_for_stamps(caselist, [newer]),
        )
    return version


def _rebuild_and_publish(caselist: str) -> str:
    return (
        f"`debate-research caselist parse --caselist {caselist} --publish` rebuilds the directory, "
        "then publishes it."
    )


def _hint_for_stamps(caselist: str, stamps: list[str]) -> str:
    """A newer stamp needs a newer build; an older one, this build's rebuild."""
    newest = newer_stamp(stamps)
    if newest is not None:
        return f"Publish it with a build at {newest} or later."
    return _rebuild_and_publish(caselist)


def _listed(names: Iterable[str]) -> str:
    return ", ".join(names)


def _digests(digests: list[str]) -> str:
    named = ", ".join(digest[:_DIGEST_PREFIX] for digest in digests[:_NAMED_DIGESTS])
    more = len(digests) - _NAMED_DIGESTS
    return f"sha256 {named}" + (f" and {more} more" if more > 0 else "")


async def refuse_what_the_list_stops(
    store: ParsedStore,
    caselist: str,
    version: str,
    *,
    sources: Sequence[EnumeratedSource],
    state: SuppressionState,
) -> None:
    """Raise :class:`ParsedAggregatesNameWhatTheListStops` when the index of `version` names a
    source, or its occurrence table a disclosure, that `state` no longer leaves live.

    `sources` is what this machine's manifests name, and `state` the target environment's list.
    Asked after :func:`refuse_unpublishable`, so the aggregates are there and this build's.
    """
    by_digest = {source.sha256: source for source in sources}
    index = await store.read_index(caselist, version) or ()
    occurrences = await store.read_occurrences(caselist, version) or ()
    stopped = sorted(
        {
            entry.source_sha256
            for entry in index
            if not is_aggregated(by_digest.get(entry.source_sha256), state)
        }
    )
    live: dict[str, frozenset[DisclosureKey]] = {}
    withdrawn: set[tuple[str, DisclosureKey]] = set()
    for row in occurrences:
        if row.source_sha256 not in live:
            live[row.source_sha256] = live_disclosure_keys(by_digest.get(row.source_sha256), state)
        key = occurrence_row_key(row.disclosure, row.snapshot)
        if key not in live[row.source_sha256]:
            withdrawn.add((row.source_sha256, key))
    if not stopped and not withdrawn:
        return
    held = held_only_sources(sources, state)
    named = sorted(set(stopped) | {sha256 for sha256, _ in withdrawn})
    raise ParsedAggregatesNameWhatTheListStops(
        f"the aggregates of {caselist} {version} name {len(stopped)} source(s) and {len(withdrawn)} "
        f"disclosure(s) this environment's suppression list now stops or holds "
        f"({sum(sha256 in held for sha256 in stopped)} of the sources only at a path a removal holds); "
        f"they were rebuilt before it did ({_digests(named)})",
        caselist=caselist,
        version=version,
        hint=(
            f"`debate-research caselist parse --caselist {caselist} --publish` rebuilds the aggregates "
            "from this environment's suppression list, then publishes them."
        ),
    )

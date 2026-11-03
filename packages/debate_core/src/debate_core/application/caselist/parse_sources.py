"""Which sources a caselist holds, read from its local manifests, for the parse pipeline.

`caselist parse` (`v1-e31-t06`) parses what the manifests say this machine stored, and nothing
else: the stored rows (`NEW`, `UNCHANGED`, `CHANGED`, `DUPLICATE`) of each snapshot's manifest under
`manifests/<caselist>/`. One source is one SHA-256, however many weeks and paths disclose it, and
every one of those disclosures is kept, because the occurrence table records each of them.

## Which manifests count: the weekly series and the OpenEv releases, and nothing else

The rule is :func:`~debate_core.application.caselist.publish_plan.snapshot_of_manifest_key` with its
default, the one rule every manifest reader shares for what counts as a snapshot. A caselist's
manifest counts when its key is exactly `manifests/<slug>/<YYYY-MM-DD>.jsonl`, and a camp release's
when it is exactly `manifests/openev/<year>-<event>.jsonl`. Everything else under the prefix is left
out, by name and not by accident:

* **The complete archives.** `v1-e34-t04` imports a caselist's complete archive as a snapshot of its
  own, `full/<date>`, with its manifest at `manifests/<slug>/full/<date>.jsonl`. Every source in it
  is a copy of a digest the weeklies already hold, and its "disclosures" are the whole corpus
  re-listed under one date. Counting them would make every card in the corpus look disclosed again
  on the day of each refresh. `caselist parse` never passes `full_archives=True`; the tests plant
  t04's own key and four other shapes (`all/`, `archive/`, a dated name with a suffix) and check
  each is left out of the parse and of the occurrence table.
* **The suppression records** under `manifests/_suppression/`, which are not a caselist.

Until `v1-e34-t04` this module had a rule of its own, `series_snapshot`. It was replaced when t04
merged; on 229 keys of every shape above, in three caselists, the two agreed on every one.

## What this does not decide

Whether a source is already parsed or in the requested snapshot is the service's to decide.
:func:`enumerate_sources` reports what the manifests say, rows the suppression list stops or holds
included, because every aggregate the service builds consults the list itself, through
:func:`live_disclosures`.

## Which disclosures are live (`v1-e31-t26`)

A disclosure is live when the suppression list neither stops it nor holds its path. Held is the
publisher's own rule for a stored row, asked and not restated
(:func:`~debate_core.application.caselist.publish_plan.stored_row_hold`): a row at a path a removal
holds, in a snapshot dated after the removed file first appeared there, is the requester's later
upload, which a build from before `v1-e30-t13` imported. Its bytes go to no bucket on its account
(`v1-e30-t22`), and the same holds for what the parse makes of them: a source with no live
disclosure is neither parsed nor in any aggregate, and its parsed file is not published
(:func:`held_only_sources`). A source another live path discloses is parsed and published as before;
only the held disclosure's occurrence rows go.

## A camp file's paths (`v1-e33-t07`)

A camp file has no disclosure, but each row of a release manifest is at a path, and a removal can
withdraw one camp path from one release (`v1-e30-t14`). The list records that withdrawal under
:func:`~debate_core.application.ports.suppression.camp_path_disclosure`, which the publisher already
asks of a camp manifest's rows, and so does :func:`live_disclosures`: a release's rows go at the next
parse whether or not this machine's manifest has been rewritten, and a release whose file another
of its paths still holds keeps them. Each camp row carries the digests of its release's live paths
(:func:`camp_path_digests`), so a reader of the table asks about a withdrawal made after it was built
(:func:`occurrence_is_stopped`).
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Final

from debate_core.application.caselist.evidence_listing import LocalEvidence, local_file
from debate_core.application.caselist.import_service import STORED_CLASSIFICATIONS
from debate_core.application.caselist.manifest import read_manifest_file
from debate_core.application.caselist.publish_plan import (
    OPENEV,
    UnreadableManifest,
    manifest_prefix,
    snapshot_of_manifest_key,
    stored_row_hold,
    validate_publish_target,
)
from debate_core.application.ports.evidence_store import ObjectKey
from debate_core.application.ports.parsed_store import OccurrenceRecord
from debate_core.application.ports.suppression import (
    PathHoldEntry,
    SuppressionState,
    camp_path_disclosure,
    disclosure_digest,
)
from debate_core.domain import Sha256Hex
from debate_core.domain.caselist import SourceDocument, SourceFormat, SourceOrigin

__all__ = [
    "Disclosed",
    "DisclosureKey",
    "EnumeratedSource",
    "disclosure_key",
    "enumerate_sources",
    "held_only_sources",
    "is_aggregated",
    "live_disclosure_keys",
    "camp_path_digests",
    "live_disclosures",
    "occurrence_is_stopped",
    "occurrence_row_key",
]

_STORED: Final = frozenset(str(classification) for classification in STORED_CLASSIFICATIONS)
_FORMATS: Final = {str(source_format): source_format for source_format in SourceFormat}


@dataclass(frozen=True, slots=True, order=True)
class Disclosed:
    """One stored row naming a source: the snapshot and the path it was disclosed at.

    The path names a school and a team code. It is used to give a parsed card its provenance path
    in memory and to compute a disclosure digest, and is never logged or written to the store.
    """

    snapshot: str
    path: str
    provenance_date: date
    """The date a card's provenance records: the snapshot itself, or for a camp file the import date."""

    def __repr__(self) -> str:
        return f"Disclosed(snapshot={self.snapshot!r}, path=<withheld>)"


@dataclass(frozen=True, slots=True)
class EnumeratedSource:
    """One source a caselist's manifests name, with every stored row that names it."""

    caselist: str
    sha256: Sha256Hex
    byte_size: int
    source_format: SourceFormat
    camp: str | None
    disclosures: tuple[Disclosed, ...]
    """Every stored row naming this digest, sorted by snapshot and path. Never empty."""

    @property
    def is_camp_file(self) -> bool:
        return self.caselist == OPENEV

    def source_document(self, disclosures: Iterable[Disclosed] | None = None) -> SourceDocument:
        """The SourceDocument the parser reads this source as, seen through `disclosures`."""
        seen = sorted(disclosures if disclosures is not None else self.disclosures)
        return SourceDocument(
            sha256=self.sha256,
            byte_size=self.byte_size,
            source_format=self.source_format,
            origin=SourceOrigin.OPENEV if self.is_camp_file else SourceOrigin.CASELIST_ARCHIVE,
            caselist=None if self.is_camp_file else self.caselist,
            first_seen_snapshot=min(disclosed.provenance_date for disclosed in seen),
            last_seen_snapshot=max(disclosed.provenance_date for disclosed in seen),
        )


async def enumerate_sources(local: LocalEvidence, caselist: str) -> tuple[EnumeratedSource, ...]:
    """Every source the weekly series (or the camp releases) of `caselist` stores, by SHA-256.

    Raises :class:`~debate_core.application.caselist.publish_plan.UnreadableManifest` for a manifest
    row it cannot read, naming the key and line number and never the row.
    """
    validate_publish_target(caselist)
    rows: dict[str, list[tuple[Disclosed, int, SourceFormat, str | None]]] = {}
    for info in await local.objects.list_objects(manifest_prefix(caselist)):
        snapshot = snapshot_of_manifest_key(caselist, info.key)
        if snapshot is None:
            continue
        async with local_file(local.objects, local.object_path_for, info.key) as path:
            lines = read_manifest_file(path)
        for digest, row in _stored_rows(info.key, caselist, snapshot, lines):
            rows.setdefault(digest, []).append(row)
    sources: list[EnumeratedSource] = []
    for digest in sorted(rows):
        found = sorted(rows[digest], key=lambda row: row[0])
        sizes = {size for _, size, _, _ in found}
        if len(sizes) != 1:
            raise UnreadableManifest(
                f"{manifest_prefix(caselist)}*", 0, f"digest {digest} is given two sizes"
            )
        _, size, source_format, camp = found[0]
        sources.append(
            EnumeratedSource(
                caselist=caselist,
                sha256=digest,
                byte_size=size,
                source_format=source_format,
                camp=camp,
                disclosures=tuple(row[0] for row in found),
            )
        )
    return tuple(sources)


def live_disclosures(source: EnumeratedSource, state: SuppressionState) -> tuple[Disclosed, ...]:
    """The disclosures of `source` the suppression list neither stops nor holds the path of.

    Stopped by the source or by its path: a caselist path by its disclosure digest, and a camp path
    by its camp path digest, which has the release in it, as the publisher checks a camp manifest's
    rows (`v1-e33-t07`). Held by the publisher's rule for a stored row
    (:func:`~debate_core.application.caselist.publish_plan.stored_row_hold`), which holds no camp
    file's row.
    """
    return tuple(
        disclosed
        for disclosed in source.disclosures
        if not state.suppresses(source.sha256, disclosure=_path_digest(source, disclosed))
        and _hold_on(source, disclosed, state) is None
    )


def camp_path_digests(source: EnumeratedSource, state: SuppressionState, release: str) -> tuple[str, ...]:
    """The camp path digest of each live path of the camp file `source` in `release`, sorted.

    What a camp occurrence row of that release carries (`v1-e33-t07`); empty for a caselist source.
    """
    if not source.is_camp_file:
        return ()
    return tuple(
        sorted(
            {
                camp_path_disclosure(release, disclosed.path)
                for disclosed in live_disclosures(source, state)
                if disclosed.snapshot == release
            }
        )
    )


def occurrence_is_stopped(row: OccurrenceRecord, state: SuppressionState) -> bool:
    """Whether the suppression list stops a stored occurrence row, asked of the row alone.

    A row is stopped by its source suppressed as a whole, or by its disclosure withdrawn. A camp row
    has no disclosure: it is stopped when every camp path it carries is withdrawn, so a release whose
    file another path still holds keeps it, and another release of the same file is never asked
    about (`v1-e33-t07`). A camp row written before rows carried camp paths has none, and only its
    whole source stops it, as before. :meth:`SuppressionState.suppresses` answers for the whole
    source too, so a camp row's whole source needs no question of its own.
    """
    if row.camp_path_disclosures:
        return all(state.suppresses(row.source_sha256, disclosure=path) for path in row.camp_path_disclosures)
    return state.suppresses(row.source_sha256, disclosure=row.disclosure)


type DisclosureKey = tuple[Sha256Hex | None, str | None]
"""What one occurrence row stands for: `(disclosure digest, None)` for a caselist disclosure, which
is one path however many weeks list it, and `(None, release)` for a camp file, which has no
disclosure, so each release is its own."""


def is_aggregated(source: EnumeratedSource | None, state: SuppressionState) -> bool:
    """Whether the parsed store's aggregates hold `source`: the manifests still name it, and one of
    its disclosures is live.

    The rebuild's rule for the index and the failures file, and the rule `caselist parse
    --publish-only` asks of an index it did not write (`v1-e31-t30`). `None` is a source the
    manifests no longer name.
    """
    return source is not None and bool(live_disclosures(source, state))


def disclosure_key(source: EnumeratedSource, disclosed: Disclosed) -> DisclosureKey:
    """The :data:`DisclosureKey` of one disclosure of `source`, as the rebuild writes its rows."""
    if source.is_camp_file:
        return (None, disclosed.snapshot)
    return (disclosure_digest(source.caselist, disclosed.path), None)


def live_disclosure_keys(
    source: EnumeratedSource | None, state: SuppressionState
) -> frozenset[DisclosureKey]:
    """The key of every live disclosure of `source`: the occurrence rows a rebuild would write for it."""
    if source is None:
        return frozenset()
    return frozenset(disclosure_key(source, disclosed) for disclosed in live_disclosures(source, state))


def occurrence_row_key(disclosure: Sha256Hex | None, snapshot: str) -> DisclosureKey:
    """The :data:`DisclosureKey` an occurrence row was written under, from its `disclosure` and
    `snapshot`: a camp file's row is its release's."""
    return (None, snapshot) if disclosure is None else (disclosure, None)


def held_only_sources(sources: Iterable[EnumeratedSource], state: SuppressionState) -> dict[Sha256Hex, str]:
    """Each source a held path discloses and no live one does, with the request holding the path.

    What the parsed store neither parses, aggregates nor publishes, and what `caselist status` names
    when an earlier build published its parsed file (`v1-e31-t26`). A source the list stops in every
    disclosure, and holds in none, is not here: the list's own rules answer for it. Where two
    requests hold its paths, the first disclosure's hold names it.
    """
    held: dict[Sha256Hex, str] = {}
    for source in sources:
        if live_disclosures(source, state):
            continue
        for disclosed in source.disclosures:
            hold = _hold_on(source, disclosed, state)
            if hold is not None:
                held[source.sha256] = hold.request_id
                break
    return held


def _path_digest(source: EnumeratedSource, disclosed: Disclosed) -> Sha256Hex:
    """The digest the suppression list withdraws one path of `source` under."""
    if source.is_camp_file:
        return camp_path_disclosure(disclosed.snapshot, disclosed.path)
    return disclosure_digest(source.caselist, disclosed.path)


def _hold_on(source: EnumeratedSource, disclosed: Disclosed, state: SuppressionState) -> PathHoldEntry | None:
    """The hold on one disclosure's path, asked of the publisher's rule for its stored row."""
    return stored_row_hold(source.caselist, disclosed.snapshot, source.sha256, disclosed.path, state)


def _stored_rows(
    key: ObjectKey, caselist: str, snapshot: str, lines: Iterable[str]
) -> Iterable[tuple[str, tuple[Disclosed, int, SourceFormat, str | None]]]:
    """`(sha256, (disclosure, size, format, camp))` for every stored member row of one manifest."""
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            row: object = json.loads(line)
        except json.JSONDecodeError:
            raise UnreadableManifest(key, number, "not JSON") from None
        if not isinstance(row, dict):
            raise UnreadableManifest(key, number, "not a JSON object")
        fields: dict[str, object] = row  # pyright: ignore[reportUnknownVariableType]
        if fields.get("kind") != "member" or fields.get("classification") not in _STORED:
            continue
        digest, path, size = fields.get("sha256"), fields.get("path"), fields.get("byte_size")
        source_format = _FORMATS.get(str(fields.get("format")))
        if not isinstance(digest, str) or not isinstance(path, str) or not path:
            raise UnreadableManifest(key, number, "a stored member with no digest or path")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0 or source_format is None:
            raise UnreadableManifest(key, number, "a stored member with no size or format")
        camp = fields.get("camp") if caselist == OPENEV else None
        yield (
            digest,
            (
                Disclosed(
                    snapshot=snapshot,
                    path=path,
                    provenance_date=_provenance_date(key, number, caselist, snapshot, fields),
                ),
                size,
                source_format,
                camp if isinstance(camp, str) and camp else None,
            ),
        )


def _provenance_date(
    key: ObjectKey, number: int, caselist: str, snapshot: str, fields: dict[str, object]
) -> date:
    if caselist != OPENEV:
        return date.fromisoformat(snapshot)
    imported_on = fields.get("imported_on")
    try:
        return date.fromisoformat(str(imported_on))
    except ValueError:
        raise UnreadableManifest(key, number, "a camp-file row with no import date") from None

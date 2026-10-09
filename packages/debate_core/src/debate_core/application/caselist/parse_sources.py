"""Which sources a caselist holds, read from its local manifests, for the parse pipeline.

`caselist parse` (`v1-e31-t06`) parses what the manifests say this machine stored, and nothing
else: the stored rows (`NEW`, `UNCHANGED`, `CHANGED`, `DUPLICATE`) of each snapshot's manifest under
`manifests/<caselist>/`. One source is one SHA-256, however many weeks and paths disclose it, and
every one of those disclosures is kept, because the occurrence table records each of them.

## Which manifests count: the weekly series and the OpenEv releases, and nothing else

:func:`series_snapshot` is the rule, and it is deliberately narrow. A caselist's manifest counts
when its key is exactly `manifests/<slug>/<YYYY-MM-DD>.jsonl`, and a camp release's when it is
exactly `manifests/openev/<year>-<event>.jsonl`. Everything else under the prefix is left out, by
name and not by accident:

* **The full-archive namespace.** `v1-e34-t04` imports a caselist's complete archive as a snapshot
  namespace of its own beside the weekly series (its ac0), under the caselist's manifest directory.
  Every source in it is a copy of a digest the weeklies already hold, and its "disclosures" are the
  whole corpus re-listed under one date. Counting them would make every card in the corpus look
  disclosed again on the day of each monthly refresh. Whatever the namespace ends up called, a key
  that is not a dated weekly manifest is not enumerated; the tests plant the forms already
  discussed (`full/`, `all/`, a dated name with a suffix) and check each is left out of the parse
  and of the occurrence table.
* **The suppression records** under `manifests/_suppression/`, which are not a caselist.

## What this does not decide

Whether a source is suppressed, already parsed or in the requested snapshot is the service's to
decide. This module reports what the manifests say, rows the suppression list stops included,
because every aggregate the service builds consults the list itself.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Final

from debate_core.application.caselist.evidence_listing import LocalEvidence, local_file
from debate_core.application.caselist.import_service import STORED_CLASSIFICATIONS
from debate_core.application.caselist.publish_plan import (
    OPENEV,
    UnreadableManifest,
    manifest_prefix,
    validate_publish_target,
)
from debate_core.application.ports.evidence_store import ObjectKey
from debate_core.domain import Sha256Hex
from debate_core.domain.caselist import SourceDocument, SourceFormat, SourceOrigin

__all__ = [
    "Disclosed",
    "EnumeratedSource",
    "enumerate_sources",
    "series_snapshot",
]

_SUFFIX: Final = ".jsonl"
_WEEKLY = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_RELEASE = re.compile(r"^[0-9]{4}-[a-z0-9][a-z0-9-]*$")
_STORED: Final = frozenset(str(classification) for classification in STORED_CLASSIFICATIONS)
_FORMATS: Final = {str(source_format): source_format for source_format in SourceFormat}


def series_snapshot(caselist: str, key: ObjectKey) -> str | None:
    """The snapshot a manifest key names when it is part of the weekly series or a camp release.

    `None` for every other key: the full-archive namespace, a nested path of any name, a name that
    is not a date (or for `openev`, not `<year>-<event>`), another suffix. The explicit rule for
    what `caselist parse` reads; see this module's docstring.
    """
    prefix = manifest_prefix(caselist)
    if not key.startswith(prefix) or not key.endswith(_SUFFIX):
        return None
    name = key[len(prefix) : -len(_SUFFIX)]
    if "/" in name:
        return None
    if caselist == OPENEV:
        return name if _RELEASE.match(name) else None
    if _WEEKLY.match(name) is None:
        return None
    try:
        return name if date.fromisoformat(name).isoformat() == name else None
    except ValueError:
        return None


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
        snapshot = series_snapshot(caselist, info.key)
        if snapshot is None:
            continue
        async with local_file(local.objects, local.object_path_for, info.key) as path:
            lines = path.read_text(encoding="utf-8").splitlines()
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

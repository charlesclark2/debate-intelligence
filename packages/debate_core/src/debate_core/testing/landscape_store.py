"""A synthetic caselist store for taxonomy seeding tests: parsed sources, their manifests, nothing real.

`v1-e32-t01-position-taxonomy` reads a caselist's parsed card store and its manifests together, so
the reader's tests and the seeding script's tests both need the two planted side by side under one
data directory. :class:`PlantedCaselist` writes them in the shapes `caselist parse` and the importer
write: one source file per parsed source (its entry, then a document record whose cards carry only
a tag, a section path and the paragraphs their provenance names, which is all seeding and the
position matcher read) and one manifest per snapshot, its member rows naming each disclosure's path.

Every school, team code, tournament and heading a test plants is its own invention.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from debate_core.application.ports.parsed_store import (
    PARSED_PREFIX,
    DocumentRecord,
    SourceEntry,
    SourceOutcome,
    StoreRecord,
    source_object_key,
)

__all__ = ["PARSER_VERSION", "PROFILE_VERSION", "PlantedCaselist", "PlantedCard"]

PARSER_VERSION = "2026.10.20-docx-6"
PROFILE_VERSION = "2026.09.20-verbatim-1"
_FINGERPRINT_VERSION = "card-fingerprint-v4"
_PARAGRAPHS_PER_CARD = 3
"""A planted card's tag, cite and body: card `n` starts at paragraph `3n`."""


@dataclass(frozen=True, slots=True)
class PlantedCard:
    """A card as seeding reads it: the headings over it, and its tag or none."""

    section_path: tuple[str, ...]
    tag: str | None = "An invented claim"


@dataclass(slots=True)
class PlantedCaselist:
    """One caselist's parsed sources and manifests under `data_dir`, written as they are added."""

    data_dir: Path
    caselist: str
    _manifest_rows: dict[str, list[dict[str, object]]] = field(default_factory=lambda: defaultdict(list))

    def source(
        self,
        name: str,
        cards: Sequence[PlantedCard],
        *,
        disclosures: Sequence[tuple[str, str]] = (),
        outcome: SourceOutcome = SourceOutcome.PARSED,
        version: str = PARSER_VERSION,
    ) -> str:
        """Plant one source named `name`, disclosed at each `(snapshot, path)`; return its digest."""
        digest = hashlib.sha256(name.encode()).hexdigest()
        first = min((snapshot for snapshot, _ in disclosures), default="2026-09-01")
        common = {
            "caselist": self.caselist,
            "snapshot": first,
            "source_sha256": digest,
            "parser_version": PARSER_VERSION,
            "profile_version": PROFILE_VERSION,
            "fingerprint_version": _FINGERPRINT_VERSION,
        }
        parsed = outcome is SourceOutcome.PARSED
        entry = SourceEntry.model_validate(
            {
                **common,
                "source_format": "DOCX",
                "byte_size": 100,
                "outcome": outcome,
                "reason": None if parsed else "NOT_A_ZIP",
                "cards": len(cards) if parsed else 0,
            }
        )
        record = (
            DocumentRecord.model_validate(
                {
                    **common,
                    "document": {
                        "source_sha256": digest,
                        "parser_version": PARSER_VERSION,
                        "profile_version": PROFILE_VERSION,
                        "cards": [
                            {
                                "tag": card.tag,
                                "section_path": list(card.section_path),
                                "provenance": {
                                    "first_element_index": index * _PARAGRAPHS_PER_CARD,
                                    "last_element_index": index * _PARAGRAPHS_PER_CARD + 2,
                                },
                            }
                            for index, card in enumerate(cards)
                        ],
                        "warnings": [],
                    },
                }
            )
            if parsed
            else None
        )
        target = self.data_dir / PARSED_PREFIX / source_object_key(self.caselist, version, digest)
        target.parent.mkdir(parents=True, exist_ok=True)
        records: list[StoreRecord] = [entry] if record is None else [entry, record]
        target.write_text("".join(_line(one) for one in records), encoding="utf-8")
        for snapshot, path in disclosures:
            self._manifest_rows[snapshot].append(
                {
                    "kind": "member",
                    "classification": "NEW",
                    "path": path,
                    "sha256": digest,
                    "byte_size": 100,
                    "format": "DOCX",
                }
            )
            self._write_manifest(snapshot)
        return digest

    def _write_manifest(self, snapshot: str) -> None:
        manifest = self.data_dir / "objects" / "manifests" / self.caselist / f"{snapshot}.jsonl"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        rows = sorted(self._manifest_rows[snapshot], key=lambda row: str(row["path"]))
        manifest.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _line(record: StoreRecord) -> str:
    """One record as `LocalParsedStore` writes it: sorted keys, compact, UTF-8."""
    return (
        json.dumps(record.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    )

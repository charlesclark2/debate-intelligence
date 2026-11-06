"""A synthetic caselist for `v1-e31-t10`'s tests of the placement state, with today's rebuild beside it.

Every word is invented, and so is every path, school and team: no real file's text or name. A
:class:`PlacementWorld` holds a data directory whose manifests name synthetic sources, parses and
rebuilds it with the real service over the local store, and gives what the rebuild as `v1-e31-t10`
found it would write for the same store (:mod:`.rebuild_at_start`), byte for byte.
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import shutil
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.parse_sources import enumerate_sources
from debate_core.application.caselist.parse_workers import InProcessParseRunner
from debate_core.application.caselist.suppression import RecordedSuppressionList, load_suppression_state
from debate_core.application.caselist_card_stats import CaselistCardStatsService
from debate_core.application.caselist_parse import CaselistParseService, ParseRunReport
from debate_core.application.ports.parsed_store import (
    FAILURES_NAME,
    INDEX_NAME,
    OCCURRENCES_NAME,
    PLACEMENT_STATE_NAME,
    DocumentRecord,
    source_object_key,
)
from debate_core.application.ports.suppression import ReasonCode, SuppressionAction, SuppressionEntry
from debate_core.domain.caselist import SnapshotDate, SourceDocument, SourceOrigin
from debate_core.domain.debate_files import (
    CardCompleteness,
    FileImportProvenance,
    FormattingSpan,
    ParsedCard,
    ParsedDocument,
)
from debate_core.domain.style_profile import RunEmphasis, StyleMatchSource
from debate_core.integrations.local import FsEvidenceObjectStore
from debate_core.integrations.local.parsed_store import LocalParsedStore
from debate_core.integrations.local.suppression_list import local_suppression_list_file
from debate_core.testing.fakes.caselist import build_fake_caselist_repository

from .rebuild_at_start import aggregates_at_start

__all__ = [
    "CASELIST",
    "LOGGER",
    "MARKERS",
    "PARSER_VERSION",
    "PROFILE_VERSION",
    "VOCABULARY",
    "WEEKS",
    "Card",
    "CountingStore",
    "PlacementWorld",
    "passage",
    "rebuild_lines",
]

CASELIST: Final = "synthcl26"
PARSER_VERSION: Final = "2031.01.01-synthetic-1"
PROFILE_VERSION: Final = "synthetic-profile-1"
MARKERS: Final = ("…",)
WEEKS: Final = ("2026-09-01", "2026-09-08", "2026-09-15", "2026-09-22", "2026-09-29", "2026-10-06")
TAG: Final = "An invented claim"
SCHOOL: Final = "Invented Academy"
LOGGER: Final = "debate_core.application.caselist_parse"

#: Invented words, so no body here is anyone's evidence.
VOCABULARY: Final = (
    "lantern",
    "quiver",
    "marrow",
    "tessel",
    "orvane",
    "plinth",
    "caddow",
    "ferrule",
    "wimble",
    "sorrel",
    "brindle",
    "quorl",
    "hessian",
    "tamber",
    "vellum",
    "pellow",
    "carrack",
    "drumlin",
    "fescue",
    "gannet",
    "harl",
    "isthmus",
    "jorum",
    "kestrel",
    "lodestar",
    "mizzen",
    "nacre",
    "oriel",
    "parapet",
    "quillon",
    "rasp",
    "scutter",
    "tallow",
    "umber",
    "vane",
    "wether",
    "yarrow",
    "zephyr",
    "argent",
    "bastion",
    "corbel",
    "dirk",
    "eyot",
    "fathom",
    "gimbal",
    "halyard",
    "ingle",
    "jib",
    "keel",
)


def passage(seed: int, words: int) -> list[str]:
    """`words` invented words, the same for the same seed."""
    chosen = random.Random(seed)
    return [chosen.choice(VOCABULARY) for _ in range(words)]


@dataclass(frozen=True, slots=True)
class Card:
    """What a synthetic document holds at one paragraph."""

    element: int
    text: str
    completeness: CardCompleteness = CardCompleteness.FULL
    short_cite: str | None = "Quillon 26"


class SyntheticParser:
    """Answers for each source with the cards it was given, under the world's parser version."""

    def __init__(self, documents: dict[str, tuple[Card, ...]], parser_version: str) -> None:
        self._documents = documents
        self.parser_version = parser_version
        self.profile_version = PROFILE_VERSION

    def parse(
        self,
        content: bytes,
        source: SourceDocument,
        *,
        source_path: str,
        snapshot: SnapshotDate | None = None,
        camp: str | None = None,
    ) -> ParsedDocument:
        assert snapshot is not None
        return ParsedDocument(
            source_sha256=source.sha256,
            source_path=source_path,
            parser_version=self.parser_version,
            profile_version=PROFILE_VERSION,
            cards=tuple(
                ParsedCard(
                    tag=TAG,
                    short_cite=card.short_cite,
                    full_cite=f"{card.short_cite or 'Unnamed'} (Invented Author, Fictional Quarterly, 2026)",
                    evidence_text=card.text,
                    completeness=card.completeness,
                    formatting_spans=(
                        FormattingSpan(
                            emphasis=RunEmphasis.UNDERLINE,
                            start_offset=0,
                            end_offset=len(card.text),
                            rule_id="synthetic-underline",
                            match_source=StyleMatchSource.VERBATIM,
                        ),
                    )
                    if card.text
                    else (),
                    match_source=StyleMatchSource.VERBATIM,
                    confidence=1.0,
                    provenance=FileImportProvenance(
                        source_sha256=source.sha256,
                        source_path=source_path,
                        origin=SourceOrigin.CASELIST_ARCHIVE,
                        caselist=CASELIST,
                        snapshot=snapshot,
                        first_element_index=card.element,
                        last_element_index=card.element + 2,
                        parser_version=self.parser_version,
                        profile_version=PROFILE_VERSION,
                    ),
                )
                for card in self._documents[source.sha256]
            ),
        )


class CountingStore(LocalParsedStore):
    """The local store, counting the documents a rebuild reads."""

    def __init__(self, data_dir: Path) -> None:
        super().__init__(data_dir)
        self.documents_read: list[str] = []

    async def read_document(self, caselist: str, version: str, sha256: str) -> DocumentRecord | None:
        self.documents_read.append(sha256)
        return await super().read_document(caselist, version, sha256)


def rebuild_lines(caplog_records: list[logging.LogRecord]) -> list[str]:
    """The rebuild's own log lines: which way it placed the cards, and why."""
    return [
        record.getMessage()
        for record in caplog_records
        if record.name == LOGGER
        and ("placement state" in record.getMessage() or "in full" in record.getMessage())
    ]


@dataclass
class PlacementWorld:
    """A data directory whose manifests name synthetic sources, and the parse service over it."""

    data_dir: Path
    parser_version: str = PARSER_VERSION
    incremental: bool = True
    documents: dict[str, tuple[Card, ...]] = field(default_factory=dict[str, tuple[Card, ...]])
    manifests: defaultdict[str, list[dict[str, object]]] = field(default_factory=lambda: defaultdict(list))
    names: dict[str, str] = field(default_factory=dict[str, str])
    """Each source's name to its SHA-256."""
    store: CountingStore = field(init=False)

    def __post_init__(self) -> None:
        self.store = CountingStore(self.data_dir)

    def add(self, name: str, cards: tuple[Card, ...], *, week: int, again: int | None = None) -> str:
        """Store one source and disclose it in `week` (and again in `again`); its SHA-256."""
        content = f"synthetic source {name}".encode()
        sha = hashlib.sha256(content).hexdigest()
        blob = self.data_dir / "blobs" / "sha256" / sha[0:2] / sha[2:4] / sha
        blob.parent.mkdir(parents=True, exist_ok=True)
        blob.write_bytes(content)
        self.documents[sha] = cards
        self.names[name] = sha
        path = f"{SCHOOL}/Team {name}/round-{name}.docx"
        for snapshot in (WEEKS[week], *(() if again is None else (WEEKS[again],))):
            self.manifests[snapshot].append(
                {
                    "kind": "member",
                    "classification": "NEW",
                    "path": path,
                    "sha256": sha,
                    "byte_size": len(content),
                    "format": "DOCX",
                }
            )
        self._write_manifests()
        return sha

    def relist(self, name: str, week: int) -> None:
        """List an earlier source again in `week`, at the same path: its disclosure's span widens."""
        sha = self.names[name]
        row = next(row for rows in self.manifests.values() for row in rows if row["sha256"] == sha)
        if row not in self.manifests[WEEKS[week]]:
            self.manifests[WEEKS[week]].append(dict(row))
        self._write_manifests()

    def _write_manifests(self) -> None:
        for snapshot, rows in self.manifests.items():
            manifest = self.data_dir / "objects" / "manifests" / CASELIST / f"{snapshot}.jsonl"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    @property
    def local(self) -> LocalEvidence:
        objects = FsEvidenceObjectStore(self.data_dir)
        blobs = FsEvidenceObjectStore(self.data_dir, subdirectory=Path("blobs"))
        return LocalEvidence(
            objects=objects, blobs=blobs, object_path_for=objects.path_for, blob_path_for=blobs.path_for
        )

    @property
    def suppression(self) -> RecordedSuppressionList:
        return RecordedSuppressionList(local_suppression_list_file(self.data_dir))

    @property
    def directory(self) -> Path:
        return self.data_dir / "parsed" / CASELIST / self.parser_version

    def service(self) -> CaselistParseService:
        return CaselistParseService(
            local=self.local,
            store=self.store,
            parser=SyntheticParser(self.documents, self.parser_version),
            runner=InProcessParseRunner(),
            suppression=self.suppression,
            card_placer=CaselistCardStatsService(
                build_fake_caselist_repository(), ellipsis_markers=MARKERS
            ).placer,
            failure_rate_threshold=1.0,
            failure_rate_minimum_sources=1,
            incremental_rebuild=self.incremental,
        )

    async def run(self) -> ParseRunReport:
        """Plan and run once, counting the documents its rebuild reads afresh."""
        self.store.documents_read.clear()
        service = self.service()
        return await service.run(await service.plan(CASELIST))

    def written(self) -> dict[str, bytes]:
        """The index, failures file and occurrence table the store holds."""
        return {
            name: (self.directory / name).read_bytes()
            for name in (INDEX_NAME, FAILURES_NAME, OCCURRENCES_NAME)
        }

    async def at_start(self) -> dict[str, bytes]:
        """What the rebuild as `v1-e31-t10` found it writes for the same store."""
        return await aggregates_at_start(
            LocalParsedStore(self.data_dir),
            caselist=CASELIST,
            version=self.parser_version,
            parser_version=self.parser_version,
            profile_version=PROFILE_VERSION,
            sources=await enumerate_sources(self.local, CASELIST),
            state=await load_suppression_state(self.suppression),
            markers=MARKERS,
        )

    async def stop(self, sha: str) -> None:
        """What a removal made on another machine leaves on this one's list."""
        await self.suppression.append(
            [
                SuppressionEntry(
                    action=SuppressionAction.SUPPRESS,
                    sha256=sha,
                    recorded_at=datetime(2026, 11, 6, 18, 0, tzinfo=UTC),
                    reason=ReasonCode.POLICY,
                    request_id="RM-2026-37",
                )
            ]
        )

    async def remove(self, sha: str) -> None:
        """What a removal leaves in the directory (`v1-e30-t33`, and this task's ruling): the source
        stopped, its per-source file gone, the placement state deleted. Its rewrite of the aggregates
        is not made here: the next run replaces them whole, and nothing reads them back."""
        await self.stop(sha)
        (self.data_dir / "parsed" / source_object_key(CASELIST, self.parser_version, sha)).unlink(
            missing_ok=True
        )
        self.state_path.unlink(missing_ok=True)

    @property
    def state_path(self) -> Path:
        return self.directory / PLACEMENT_STATE_NAME

    def forget(self) -> None:
        """Delete the data directory."""
        shutil.rmtree(self.data_dir, ignore_errors=True)

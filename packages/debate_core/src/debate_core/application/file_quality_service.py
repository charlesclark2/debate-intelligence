"""Checking a built evidence file before anyone reads from it (`v1-e33-t04`).

:class:`FileQualityService` takes a built `.docx` and the provenance sidecar beside it
(`<file>.provenance.json`, `v1-e33-t02`), and does not trust either:

1. It reads the sidecar against its own schema, and checks it describes these bytes.
2. It re-parses the built file with the E31 parser, through the
   :class:`~debate_core.application.ports.debate_files.DebateFileParser` port.
3. For each card, it fetches the source the sidecar names from the blob store by its SHA-256,
   hashes the bytes itself, re-parses them, and finds the card at the recorded paragraphs.
4. It runs every check in :mod:`debate_core.evidence.file_checks` and reads the suppression list.
5. :meth:`FileQualityService.check` writes `<file>.quality.json` and `<file>.quality.md` beside the
   built file.

No model is called, nothing is fixed, and the built file is never written to. `files build` and
`files check` (`v1-e33-t03`) call this service, and `files publish` (`v1-e33-t05`) gates on its
status; it has no command of its own.

## When a check cannot run

Without a valid sidecar nothing about a card can be established: which source it came from, whether
it is that source's card, whether a removal covers it. Those checks then FAIL, saying why, rather than
reporting a PASS they never earned. A built file the parser refuses fails every check that reads it.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Final

from pydantic import ValidationError

from debate_core.application.caselist.publish_plan import source_prefix
from debate_core.application.errors import BlobIntegrityError, NotFound
from debate_core.application.ports.debate_files import DebateFileParser
from debate_core.application.ports.parsed_store import OPENEV_STORE
from debate_core.application.ports.persistence import SnapshotStore
from debate_core.application.ports.suppression import SuppressionAction, SuppressionEntry, SuppressionList
from debate_core.domain.caselist import SourceDocument, SourceFormat, SourceOrigin
from debate_core.domain.debate_files import ParsedDocument, ParseFailure
from debate_core.domain.file_provenance import (
    FileProvenanceEntry,
    FileProvenanceManifest,
    provenance_sidecar_name,
)
from debate_core.domain.style_profile import StyleProfile
from debate_core.evidence.file_checks.identity import SourceCardReading, check_identity
from debate_core.evidence.file_checks.report import (
    CHECKER_VERSION,
    CheckResult,
    CheckStatus,
    FileQualityReport,
    QualityCheck,
    quality_report_names,
    render_markdown,
)
from debate_core.evidence.file_checks.structure import (
    SuppressionsInForce,
    check_alignment,
    check_cites,
    check_duplicates,
    check_headings,
    check_provenance,
    check_sidecar,
    check_suppression,
)
from debate_core.evidence.fingerprints import FINGERPRINT_VERSION
from debate_core.evidence.style_profile_loader import load_style_profile

__all__ = ["CheckedFile", "FileQualityService", "suppressions_in_force"]

#: The paths the parser is told the files sat at. Recorded nowhere: a real path names a team.
_BUILT_PATH_FOR_THE_PARSER: Final = "built-file.docx"
_SOURCE_PATH_FOR_THE_PARSER: Final = "checked-source.docx"

#: The day the parser is told an undated file was seen. Nothing a check reads depends on it.
_UNDATED: Final = date(2000, 1, 1)

#: What needs the sidecar, and what needs the built file to parse.
_NEED_THE_SIDECAR: Final = (
    QualityCheck.EVIDENCE_IDENTITY,
    QualityCheck.MANIFEST_ALIGNMENT,
    QualityCheck.PROVENANCE_COMPLETE,
    QualityCheck.SUPPRESSION,
)
_NEED_THE_DOCUMENT: Final = (
    QualityCheck.EVIDENCE_IDENTITY,
    QualityCheck.CITE_PRESENT,
    QualityCheck.DUPLICATE_CARDS,
    QualityCheck.HEADING_STRUCTURE,
    QualityCheck.MANIFEST_ALIGNMENT,
    QualityCheck.PROVENANCE_COMPLETE,
)


def suppressions_in_force(entries: Iterable[SuppressionEntry]) -> SuppressionsInForce:
    """The suppressions in force after every entry, each with the request id that made it.

    Entries are applied as :class:`~debate_core.application.ports.suppression.SuppressionState`
    applies them: by `recorded_at`, ties broken by their text, an un-suppress lifting every
    suppression of its SHA-256 recorded before it. A source or disclosure suppressed twice keeps the
    first request that suppressed it.
    """
    sources: dict[str, str] = {}
    disclosures: dict[tuple[str, str], str] = {}
    for entry in sorted(entries, key=lambda one: (one.recorded_at, one.to_line())):
        if entry.action is SuppressionAction.UNSUPPRESS:
            sources.pop(entry.sha256, None)
            disclosures = {pair: request for pair, request in disclosures.items() if pair[0] != entry.sha256}
            continue
        assert entry.request_id is not None, "a suppression carries its request id"
        if entry.disclosure is None:
            sources.setdefault(entry.sha256, entry.request_id)
        else:
            disclosures.setdefault((entry.sha256, entry.disclosure), entry.request_id)
    return SuppressionsInForce(sources=sources, disclosures=disclosures)


def _sidecar_problems(error: ValidationError) -> list[str]:
    """Where the sidecar breaks its schema and how: locations and pydantic's messages, never values."""
    problems: list[str] = []
    for detail in error.errors(include_input=False, include_url=False):
        location = ".".join(str(part) for part in detail["loc"])
        problems.append(f"{location}: {detail['msg']}" if location else str(detail["msg"]))
    return problems


@dataclass(frozen=True, slots=True)
class CheckedFile:
    """A checked file's report, and where its two renderings were written."""

    report: FileQualityReport
    json_path: Path
    markdown_path: Path


class FileQualityService:
    """Re-reads a built file, its sidecar and its sources, and reports PASS or FAIL per check and card.

    `snapshots` is the blob store the sources are read from by SHA-256; `source_stores`, when given,
    is the store under each source prefix of the evidence layout, as the writer takes it. `suppression`
    is required, with no default, as for every service that handles a source (`v1-e30-t07`). `profile`
    is the style profile the headings are held to, by default the one the parser reads with.
    """

    def __init__(
        self,
        *,
        parser: DebateFileParser,
        snapshots: SnapshotStore,
        suppression: SuppressionList,
        profile: StyleProfile | None = None,
        source_stores: Callable[[str], SnapshotStore] | None = None,
    ) -> None:
        self._parser = parser
        self._snapshots = snapshots
        self._suppression = suppression
        self._profile = profile if profile is not None else load_style_profile()
        self._source_stores = source_stores
        if self._profile.profile_version != parser.profile_version:
            raise ValueError(
                f"the style profile is {self._profile.profile_version} and the parser reads with "
                f"{parser.profile_version}: headings would be held to another profile than they were read by"
            )

    async def check(self, built_path: Path) -> CheckedFile:
        """Check the file at `built_path` and write its two reports beside it."""
        sidecar_path = built_path.with_name(provenance_sidecar_name(built_path.name))
        sidecar = sidecar_path.read_bytes() if sidecar_path.is_file() else None
        report = await self.check_file(built_path.read_bytes(), sidecar)
        json_name, markdown_name = quality_report_names(built_path.name)
        json_path, markdown_path = built_path.with_name(json_name), built_path.with_name(markdown_name)
        json_path.write_bytes(report.to_json_bytes())
        markdown_path.write_text(render_markdown(report), encoding="utf-8")
        return CheckedFile(report=report, json_path=json_path, markdown_path=markdown_path)

    async def check_file(self, docx: bytes, sidecar: bytes | None) -> FileQualityReport:
        """The report for a built file's bytes and its sidecar's (None when there is none). Writes nothing."""
        docx_sha256 = hashlib.sha256(docx).hexdigest()
        manifest, problems = self._read_sidecar(sidecar)
        results = check_sidecar(
            problems=problems,
            recorded_docx_sha256=manifest.docx_sha256 if manifest is not None else None,
            docx_sha256=docx_sha256,
            sidecar_parser_version=manifest.parser_version if manifest is not None else None,
            parser_version=self._parser.parser_version,
        )
        document = self._parse_built(docx, docx_sha256, manifest)
        if isinstance(document, ParseFailure):
            unread = f"the built file does not parse: {document.reason}"
            results.extend(_not_checked(check, unread) for check in _NEED_THE_DOCUMENT)
        else:
            known = frozenset(
                heading for entry in (manifest.cards if manifest else ()) for heading in entry.section_path
            )
            results += check_cites(document.cards)
            results += check_duplicates(document.cards)
            results += check_headings(document, self._profile, known)
        if manifest is None:
            results.extend(
                _not_checked(check, "not checked without a valid sidecar")
                for check in _NEED_THE_SIDECAR
                if not (isinstance(document, ParseFailure) and check in _NEED_THE_DOCUMENT)
            )
        else:
            if isinstance(document, ParsedDocument):
                sources = await self._read_sources(manifest.cards)
                results += check_identity(manifest.cards, document.cards, sources)
                results += check_alignment(manifest.cards, document.cards)
                results += check_provenance(manifest.cards, document)
            results += check_suppression(
                manifest.cards, suppressions_in_force(await self._suppression.entries())
            )
        return FileQualityReport.from_results(
            results,
            checker_version=CHECKER_VERSION,
            parser_version=self._parser.parser_version,
            style_profile_version=self._parser.profile_version,
            fingerprint_version=FINGERPRINT_VERSION,
            builder_version=manifest.builder_version if manifest is not None else None,
            sidecar_parser_version=manifest.parser_version if manifest is not None else None,
            docx_sha256=docx_sha256,
            recipe_hash=manifest.recipe_hash if manifest is not None else None,
            card_count=len(document.cards) if isinstance(document, ParsedDocument) else 0,
            manifest_card_count=len(manifest.cards) if manifest is not None else None,
        )

    # -- reading ------------------------------------------------------------------------------

    @staticmethod
    def _read_sidecar(sidecar: bytes | None) -> tuple[FileProvenanceManifest | None, list[str]]:
        if sidecar is None:
            return None, ["there is no sidecar beside the built file"]
        try:
            return FileProvenanceManifest.model_validate_json(sidecar), []
        except ValidationError as error:
            return None, _sidecar_problems(error)

    def _parse_built(
        self, docx: bytes, docx_sha256: str, manifest: FileProvenanceManifest | None
    ) -> ParsedDocument | ParseFailure:
        caselist = manifest.caselist if manifest is not None and manifest.caselist != OPENEV_STORE else None
        built = SourceDocument(
            sha256=docx_sha256,
            byte_size=len(docx),
            source_format=SourceFormat.DOCX,
            origin=SourceOrigin.CASELIST_ARCHIVE if caselist is not None else SourceOrigin.OPENEV,
            caselist=caselist,
            first_seen_snapshot=_UNDATED,
            last_seen_snapshot=_UNDATED,
        )
        return self._parser.parse(docx, built, source_path=_BUILT_PATH_FOR_THE_PARSER)

    async def _read_sources(self, entries: Sequence[FileProvenanceEntry]) -> dict[int, SourceCardReading]:
        """Each entry's source card, read from the source's own bytes, or why it cannot be."""
        parsed: dict[str, ParsedDocument | str] = {}
        readings: dict[int, SourceCardReading] = {}
        for entry in entries:
            sha = entry.source_sha256
            if sha not in parsed:
                parsed[sha] = await self._read_source(entry)
            document = parsed[sha]
            if isinstance(document, str):
                readings[entry.position] = SourceCardReading(card=None, problem=document)
                continue
            card = next(
                (
                    card
                    for card in document.cards
                    if card.provenance.first_element_index == entry.first_element_index
                    and card.provenance.last_element_index == entry.last_element_index
                ),
                None,
            )
            readings[entry.position] = (
                SourceCardReading(card=card)
                if card is not None
                else SourceCardReading(
                    card=None,
                    problem=(
                        f"no card of parser {self._parser.parser_version} runs from paragraph "
                        f"{entry.first_element_index} to {entry.last_element_index} of the source"
                    ),
                )
            )
        return readings

    async def _read_source(self, entry: FileProvenanceEntry) -> ParsedDocument | str:
        store = (
            self._snapshots
            if self._source_stores is None
            else self._source_stores(source_prefix(entry.caselist, entry.snapshot))
        )
        try:
            content = await store.get(entry.source_sha256)
        except NotFound:
            return "the source's bytes are not in the blob store"
        except BlobIntegrityError:
            return "the stored bytes no longer hash to the source's SHA-256"
        if hashlib.sha256(content).hexdigest() != entry.source_sha256:
            return "the stored bytes no longer hash to the source's SHA-256"
        camp = entry.caselist == OPENEV_STORE
        source = SourceDocument(
            sha256=entry.source_sha256,
            byte_size=len(content),
            source_format=SourceFormat.DOCX,
            origin=SourceOrigin.OPENEV if camp else SourceOrigin.CASELIST_ARCHIVE,
            caselist=None if camp else entry.caselist,
            first_seen_snapshot=_UNDATED if camp else date.fromisoformat(entry.snapshot),
            last_seen_snapshot=_UNDATED if camp else date.fromisoformat(entry.last_snapshot),
        )
        document = self._parser.parse(content, source, source_path=_SOURCE_PATH_FOR_THE_PARSER)
        if isinstance(document, ParseFailure):
            return f"the parser refuses the source: {document.reason}"
        return document


def _not_checked(check: QualityCheck, reason: str) -> CheckResult:
    return CheckResult(check=check, status=CheckStatus.FAIL, message=reason)

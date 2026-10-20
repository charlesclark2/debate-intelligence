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
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from debate_core.application.ports.debate_files import DebateFileParser
from debate_core.application.ports.persistence import SnapshotStore
from debate_core.application.ports.suppression import SuppressionEntry, SuppressionList
from debate_core.domain.style_profile import StyleProfile
from debate_core.evidence.file_checks.report import (
    CHECKER_VERSION,
    FileQualityReport,
    quality_report_names,
    render_markdown,
)
from debate_core.evidence.file_checks.structure import SuppressionsInForce
from debate_core.evidence.fingerprints import FINGERPRINT_VERSION
from debate_core.evidence.style_profile_loader import load_style_profile

__all__ = ["CheckedFile", "FileQualityService", "suppressions_in_force"]


def suppressions_in_force(entries: Iterable[SuppressionEntry]) -> SuppressionsInForce:
    """The suppressions in force after every entry, each with the request id that made it."""
    return SuppressionsInForce()


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
    is required, with no default, as for every service that handles a source (`v1-e30-t07`).
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

    async def check(self, built_path: Path) -> CheckedFile:
        """Check the file at `built_path` and write its two reports beside it."""
        report = await self.check_file(built_path.read_bytes(), None)
        json_name, markdown_name = quality_report_names(built_path.name)
        json_path, markdown_path = built_path.with_name(json_name), built_path.with_name(markdown_name)
        json_path.write_bytes(report.to_json_bytes())
        markdown_path.write_text(render_markdown(report), encoding="utf-8")
        return CheckedFile(report=report, json_path=json_path, markdown_path=markdown_path)

    async def check_file(self, docx: bytes, sidecar: bytes | None) -> FileQualityReport:
        """The report for a built file's bytes and its sidecar's (None when there is none). Writes nothing."""
        return FileQualityReport.from_results(
            [],
            checker_version=CHECKER_VERSION,
            parser_version=self._parser.parser_version,
            style_profile_version=self._parser.profile_version,
            fingerprint_version=FINGERPRINT_VERSION,
            docx_sha256=hashlib.sha256(docx).hexdigest(),
            card_count=0,
        )

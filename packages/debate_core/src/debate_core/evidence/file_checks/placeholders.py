"""SKELETON for the red run."""

from __future__ import annotations

from typing import Final

from debate_core.domain.debate_files import ParsedDocument
from debate_core.evidence.file_checks.report import CheckResult

__all__ = ["CP_TEXT_SLOT", "check_placeholders"]

CP_TEXT_SLOT: Final = "[the counterplan text: write it here]"


def check_placeholders(document: ParsedDocument, known_headings: frozenset[str]) -> list[CheckResult]:
    return []

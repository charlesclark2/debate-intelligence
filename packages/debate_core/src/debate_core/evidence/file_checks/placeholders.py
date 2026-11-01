"""The placeholders check: a built file still holding the slot `files suggest` drafts (`v1-e33-t15`).

A counterplan's draft opens its first block with :data:`CP_TEXT_SLOT` (`v1-e33-t11`), an analytic for
the coach to replace with the text the team reads. `files build` writes it as it stands, like any
analytic, so a recipe marked `ready` with the slot still in it builds a file that cannot be read in a
round as it is.

## A WARN, never a FAIL (PM ruling B on t11's question 1, 2026-10-31)

Each analytic whose text is exactly the slot is a WARN naming the block it sits in, so the coach sees
it in `files build`, `files check` and `files publish`'s "Warned, not blocked", and publish still goes
ahead. An analytic holding the slot's words among others is the coach's own and is not flagged. A file
without the slot has one PASS for the whole file.

The block is named as the heading check names a heading (:mod:`.structure`): by its text when the
sidecar records it as one of the coach's, otherwise by its level and paragraph. The message never
repeats the slot's words.

## Where the slot is defined

Here, below the application layer, so that the quality service can read it without importing
`files suggest`'s service, which imports the build service, which imports the quality service.
`files suggest` imports it from here and exports it as its own.
"""

from __future__ import annotations

from typing import Final

from debate_core.domain.debate_files import FileSection, ParsedDocument
from debate_core.domain.style_profile import StructuralUnit
from debate_core.evidence.file_checks.report import CheckResult, CheckStatus, QualityCheck

__all__ = ["CP_TEXT_SLOT", "check_placeholders"]

CP_TEXT_SLOT: Final = "[the counterplan text: write it here]"
"""The analytic a counterplan's draft opens with, for the coach to replace: never a team's text."""

_LEVELS: Final = (StructuralUnit.POCKET, StructuralUnit.HAT, StructuralUnit.BLOCK)


def check_placeholders(document: ParsedDocument, known_headings: frozenset[str]) -> list[CheckResult]:
    """A WARN for each analytic that is exactly :data:`CP_TEXT_SLOT`, naming its block; else one PASS.

    `known_headings` are the coach's headings the sidecar records, named by their text; any other
    heading above the slot is named by its level and paragraph.
    """
    check = QualityCheck.PLACEHOLDERS_REPLACED
    opened: dict[StructuralUnit, FileSection] = {}
    results: list[CheckResult] = []
    for section in document.sections:
        if section.unit in _LEVELS:
            for level in _LEVELS[_LEVELS.index(section.unit) :]:
                opened.pop(level, None)
            opened[section.unit] = section
        elif section.unit is StructuralUnit.ANALYTIC and section.text == CP_TEXT_SLOT:
            results.append(
                CheckResult(
                    check=check,
                    status=CheckStatus.WARN,
                    section_path=tuple(
                        opened[level].text
                        if opened[level].text in known_headings
                        else f"{level.lower()} at paragraph {opened[level].element_index}"
                        for level in _LEVELS
                        if level in opened
                    ),
                    paragraph_index=section.element_index,
                    message=(
                        "the analytic is still the placeholder for the counterplan's text that "
                        "`files suggest` drafts: write the text the team reads in its place, then build again"
                    ),
                )
            )
    return results or [
        CheckResult(
            check=check, status=CheckStatus.PASS, message="no analytic is a placeholder left to replace"
        )
    ]

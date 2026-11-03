"""Reading the hand-written `<sample>.expected.json` files and comparing extraction output with them.

Shared by the layout rules' tests (over the builder's lines) and the PDF and HTML extractors' tests
(over the bytes), so every suite checks a sample against the same expectation in the same way.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

from debate_core.retrieval.extraction import LineJoin, RemovedLine

FIXTURES: Final = Path(__file__).parent


def load_expected(sample: str) -> dict[str, Any]:
    """`<sample>.expected.json`, parsed."""
    expected: dict[str, Any] = json.loads((FIXTURES / f"{sample}.expected.json").read_text(encoding="utf-8"))
    return expected


def sample_bytes(file_name: str) -> bytes:
    """A sample's bytes, exactly as committed."""
    return (FIXTURES / file_name).read_bytes()


def join_mismatches(
    paragraphs: Sequence[str], joins: Sequence[LineJoin], expected: Sequence[dict[str, Any]]
) -> list[str]:
    """How `joins` differ from the expected joins, one line each; empty when they match.

    The expectation pins each join by the hand-written text on either side of it (`before` ends at
    the join, `after` starts there), so the offset is checked against the words, not against a
    number copied from a run.
    """
    if len(joins) != len(expected):
        return [f"{len(joins)} joins, expected {len(expected)}"]
    problems: list[str] = []
    for number, (join, wanted) in enumerate(zip(joins, expected, strict=True)):
        found = {
            "paragraph_index": join.paragraph_index,
            "page_number": join.page_number,
            "character": join.character,
            "hyphen_kept": join.hyphen_kept,
            "decision": join.decision.value,
            "hyphenated_form_count": join.hyphenated_form_count,
            "joined_form_count": join.joined_form_count,
        }
        for key, value in found.items():
            if value != wanted[key]:
                problems.append(f"join {number}: {key} is {value!r}, expected {wanted[key]!r}")
        paragraph = paragraphs[join.paragraph_index] if join.paragraph_index < len(paragraphs) else ""
        if not paragraph[: join.offset].endswith(wanted["before"]):
            problems.append(f"join {number}: text before offset is {paragraph[: join.offset][-30:]!r}")
        if not paragraph[join.offset :].startswith(wanted["after"]):
            problems.append(f"join {number}: text after offset is {paragraph[join.offset :][:30]!r}")
    return problems


def removed_line_rows(removed: Sequence[RemovedLine]) -> list[dict[str, Any]]:
    """Removed lines in the expectation's shape."""
    return [
        {
            "page_number": line.page_number,
            "edge": line.edge.value,
            "reason": line.reason.value,
            "text": line.text,
        }
        for line in removed
    ]

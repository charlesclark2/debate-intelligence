"""The baseline report `run_parser_eval.py --write-baseline` writes starts with the docs index line.

Every Markdown file under docs/ must open with `<!-- docs-index: ... -->`; the first baseline report
(2026-10-20) did not, and failed `spec-validate` until it was added by hand.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT))

import docs_index  # noqa: E402
import run_parser_eval  # noqa: E402


def test_the_baseline_report_opens_with_a_docs_index_description() -> None:
    text = run_parser_eval.baseline_report_text(
        "# Parser evaluation — full tier\n\nbody\n",
        "# Parser evaluation — PR subset\n\n## Units\n\nrows\n",
        "2026.10.20-docx-6",
    )
    first = text.splitlines()[0]
    match = docs_index.DESCRIPTION.fullmatch(first)
    assert match is not None
    assert match.group("text") == (
        "Parser evaluation baseline on 2026.10.20-docx-6: per-unit scores for the labelled tiers"
    )
    assert text.splitlines()[1] == "# Parser evaluation — full tier"
    assert "\n## PR subset\n" in text
    assert "\n### Units\n" in text

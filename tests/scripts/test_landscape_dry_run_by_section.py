"""`scripts/landscape_dry_run_by_section.py`: a dry run's counts and its hits by section (`v1-e32-t16`).

Over the synthetic caselist's report (`tests/fixtures/landscape/synthetic_caselist`, its README's
"Planks"), rendered as the run renders it, with two hits placed by hand: one in the States CP's texts
table, one in its plank table. Every expected line was written by hand from that README and the golden
report.md. Every school, team code and text here is invented.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from debate_core.application.landscape_report import LandscapeReportService
from debate_core.application.landscape_run import ScanResult
from debate_core.application.landscape_scan import ScanHit, ScanKind
from debate_core.testing.landscape_report import read_synthetic_caselist, synthetic_staleness

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import landscape_dry_run_by_section as script  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "tests" / "fixtures" / "landscape" / "synthetic_caselist"
TEXT_ROW = "| 1 | 4 | The fifty states should establish a sample single payer system. |"
PLANK_ROW = "| Costs advantage | 1 | 4 | Expand sample clinics to cut costs. |"


def _result() -> Any:
    bundle = LandscapeReportService().bundle(read_synthetic_caselist(FIXTURE), synthetic_staleness())
    lines = bundle.files["report.md"].splitlines()
    text_hit = ScanHit("report.md", lines.index(TEXT_ROW) + 1, ScanKind.TEAM_CODE, "XX", TEXT_ROW)
    plank_hit = ScanHit("report.md", lines.index(PLANK_ROW) + 1, ScanKind.SCHOOL, "Sample", PLANK_ROW)
    return SimpleNamespace(
        caselist="synthpolicy26",
        snapshot=bundle.report.header.snapshot,
        taxonomy_version="1.2.0",
        written=False,
        publish=SimpleNamespace(planned=tuple(range(7))),
        report=bundle.report,
        scan=ScanResult(hits=(text_hit, plank_hit), pending=(plank_hit,), digest="0123456789ab"),
        bundle_files=bundle.files,
    )


def test_the_dry_run_prints_the_planks_and_the_scans_hits_by_section_and_counts_only() -> None:
    result = _result()
    lines = script.report_lines(result)
    assert lines == [
        f"Dry run of synthpolicy26 through {result.snapshot.isoformat()}, taxonomy 1.2.0: nothing written; "
        "7 files planned.",
        "Planks: 8 under 1 CPs, in 3 groups by what they solve, 7 rows shown, 1 withheld for naming a "
        "school.",
        "  states-cp: 8 planks, 6 teams, 3 groups, 1 withheld",
        "Planks found: 16 in 8 files; 14 counted, 1 elsewhere, 0 under headings that place nothing, 1 under "
        "no heading; 2 refused with their CP text, 1 alias-only labels, 1 cards saying solves with other "
        "words, 1 not read again.",
        "Scan: 2 hits, 1 not yet accepted (digest 0123456789ab).",
        "  report.md | Counterplan texts | team_code: 1 (0 not yet accepted)",
        "  report.md | Counterplan planks: plank table | school: 1 (1 not yet accepted)",
        "Hits in report.md's plank tables: 1.",
    ]
    # Counts only: no hit's term or line, and no text or plank.
    for words in ("XX", "Sample", "sample", "Expand", "fifty states"):
        assert not any(words in line for line in lines)


def test_with_no_hit_the_plank_tables_say_so() -> None:
    result = _result()
    result.scan = ScanResult(hits=(), pending=(), digest="")
    assert script.report_lines(result)[-2:] == [
        "Scan: 0 hits, 0 not yet accepted.",
        "Hits in report.md's plank tables: 0.",
    ]

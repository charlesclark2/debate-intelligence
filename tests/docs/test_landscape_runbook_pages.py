"""The landscape runbook's pages counts (`v1-e32-t57`, the PM's ruling of 2026-11-07, Q2).

Step 3's dry-run block and step 4's publish blocks print how many school-view pages are over the budget
and the largest page's and position page's bytes, counts only, for the PM; a block of its own, for the
terminal only, prints the pages' names. Each block's own Python is run here, as the runbook gives it,
over a dry run's `--json` written by hand with invented names.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Final

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
RUNBOOK: Final = REPO_ROOT / "docs" / "runbooks" / "landscape-report-from-the-cloud-run.md"
_ONE_LINER: Final = re.compile(r"python3 -I -c '([^']*)' (/tmp/landscape-[a-z-]+\.json)")

OVER: Final = {
    "data": {
        "pages": {
            "budget": 153_600,
            "frame_allowance": 28_672,
            "checked": 9,
            "over_budget": [
                {"kind": "school", "page": "Larkspur Fictional", "school": None, "bytes": 160_001},
                {"kind": "team", "page": "QZ", "school": "Larkspur Fictional", "bytes": 153_600},
            ],
            "largest": {"kind": "school", "bytes": 160_001},
            "largest_position": {"page": "invented-da", "bytes": 40_000},
        },
        "publish": {"planned": [], "uploaded": [], "unchanged": []},
    }
}


def _blocks(path: str) -> list[str]:
    """Each one-liner of the runbook that reads `path`, in the runbook's order."""
    return [code for code, read in _ONE_LINER.findall(RUNBOOK.read_text(encoding="utf-8")) if read == path]


def _run(code: str, payload: object, tmp_path: Path) -> str:
    written = tmp_path / "run.json"
    written.write_text(json.dumps(payload), encoding="utf-8")
    ran = subprocess.run(
        [sys.executable, "-I", "-c", code, str(written)], capture_output=True, text=True, check=False
    )
    assert ran.returncode == 0, ran.stderr
    return ran.stdout


def test_the_dry_runs_counts_say_how_many_pages_are_over_and_name_none(tmp_path: Path) -> None:
    counts = _blocks("/tmp/landscape-dry-run.json")[0]

    out = _run(counts, OVER, tmp_path)

    assert (
        "pages_checked 9 pages_over_budget 2 largest_page school 160001 largest_position_page 40000 "
        "budget 153600\n"
    ) in out
    assert "Larkspur" not in out and "QZ" not in out


def test_the_terminal_only_block_names_each_page_over_the_budget(tmp_path: Path) -> None:
    (names,) = [
        code
        for code in _blocks("/tmp/landscape-dry-run.json")
        if "over_budget" in code and "print(p[" in code
    ]

    out = _run(names, OVER, tmp_path)

    assert out.splitlines() == ["school  Larkspur Fictional 160001", "team Larkspur Fictional QZ 153600"]


def test_every_publish_block_prints_the_counts_for_the_pm_to_record_and_no_name(tmp_path: Path) -> None:
    blocks = _blocks("/tmp/landscape-publish.json")
    pages = [code for code in blocks if "pages_over_budget" in code]

    assert len(pages) == len(blocks) == 2, "the publish and the publish with a digest"
    for code in pages:
        out = _run(code, OVER, tmp_path)
        assert "pages_over_budget 2 largest_page school 160001 largest_position_page 40000\n" in out
        assert "Larkspur" not in out and "QZ" not in out


def test_step_3_stops_on_a_page_over_the_budget_and_sends_the_pm_the_count() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    step_3 = text.split("## 3. The dry run, and its counts", 1)[1].split("\n## 4. ", 1)[0]

    assert "`pages_checked` above zero and `pages_over_budget 0`" in step_3
    assert "* `pages_over_budget` above zero:" in step_3
    assert "Send the PM the\n  `pages_over_budget` line" in step_3
    assert "do not publish until the PM says" in step_3

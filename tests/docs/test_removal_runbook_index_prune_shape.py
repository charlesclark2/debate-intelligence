"""The removal runbook's P4 keeps its dry run and its deletion in two blocks, the dry run first.

`docs/runbooks/caselist-removal.md`, "P4 — Delete the superseded index versions", runs
`debate-research tub index prune` (`v1-e39-t15`), which replaced the pasted script that
`packages/debate_api/tests/test_removal_runbook_index_prune.py` used to run. What that test also held
in place, by running the dry run alone, is working agreement 11: a command that deletes is two
operator blocks, its dry run and then its real run with the confirmation code, and a block never holds
both, so the plan is read before anything is deleted. This test holds that shape. The command's own
behaviour is `tests/smoke/test_tub_index_smoke.py`'s.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
RUNBOOK: Final = REPO_ROOT / "docs" / "runbooks" / "caselist-removal.md"
P4_HEADING: Final = "### P4 — Delete the superseded index versions"

PRUNE_RUN: Final = re.compile(r"debate-research tub index prune --env (?:dev|prod)\b(?P<rest>[^\n]*)")
"""A line that runs the prune, as opposed to asking for its `--help`."""


def p4_section() -> str:
    text = RUNBOOK.read_text(encoding="utf-8")
    assert text.count(P4_HEADING) == 1, f"the runbook has no single {P4_HEADING!r}"
    return text.split(P4_HEADING, 1)[1].split("\n### ", 1)[0]


def shell_blocks(section: str) -> list[tuple[int, int, str]]:
    """Each `bash` block in the section: where it starts and ends, and what it holds."""
    return [
        (found.start(), found.end(), found.group(1))
        for found in re.finditer(r"^```bash\n(.*?)^```$", section, re.DOTALL | re.MULTILINE)
    ]


def prune_runs(block: str) -> list[str]:
    """What follows `--env <environment>` on each line of `block` that runs the prune."""
    return [found.group("rest") for found in PRUNE_RUN.finditer(block)]


def test_p4_runs_the_dry_run_and_the_deletion_in_two_blocks_the_dry_run_first() -> None:
    section = p4_section()
    running = [(start, end, block) for start, end, block in shell_blocks(section) if prune_runs(block)]

    assert len(running) == 2, (
        f"P4 runs the prune in {len(running)} block(s), not a dry run block and a delete block"
    )
    (_, dry_run_end, dry_run), (delete_start, _, delete) = running
    assert prune_runs(dry_run) == [""], f"the first block is not the dry run alone: {prune_runs(dry_run)}"
    assert "--execute" not in dry_run, "the dry run's block holds an --execute"
    assert prune_runs(delete) == [' --execute --confirm "$CODE"'], (
        f'the second block does not delete with --execute --confirm "$CODE": {prune_runs(delete)}'
    )
    assert re.search(r"^CODE=", delete, re.MULTILINE), "the delete block does not set CODE itself"
    between = section[dry_run_end:delete_start]
    assert "Stop, and do not run the next block, if" in between, (
        "the prose between the blocks no longer says what in the dry run stops the operator"
    )

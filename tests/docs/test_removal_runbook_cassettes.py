"""The removal runbook deletes a caselist's model cassettes with the removal's form of the command.

`docs/runbooks/caselist-removal.md`, "The model stage's cassettes", runs `debate-research landscape
cassettes --for-removal` (`v1-e32-t36`) after a removal's `DONE`: every cassette naming the caselist,
shared ones included, and every unattributed one, since a takedown has to reach every copy of the
removed text (PM ruling, 2026-10-31). Until then the paragraph said to delete the recordings by hand.
These tests hold the section's shape: the command with the flag and its code, a dry run block and then
a delete block (working agreement 11), `--confirm-prod` in prod, the PM told, and no whole-directory
delete. The command's own behaviour is `packages/debate_cli/tests/test_landscape_cassettes.py`'s and
`tests/smoke/test_landscape_smoke.py`'s; the annual purge's form is `test_annual_purge_runbook.py`'s.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
RUNBOOK: Final = REPO_ROOT / "docs" / "runbooks" / "caselist-removal.md"
HEADING: Final = "### The model stage's cassettes (E32)"
COMMAND: Final = "debate-research landscape cassettes"


def section() -> str:
    text = RUNBOOK.read_text(encoding="utf-8")
    assert text.count(HEADING) == 1, f"the runbook has no single {HEADING!r}"
    return text.split(HEADING, 1)[1].split("\n## ", 1)[0].split("\n### ", 1)[0]


def shell_blocks(text: str) -> list[tuple[int, int, str]]:
    return [
        (found.start(), found.end(), found.group(1))
        for found in re.finditer(r"^```bash\n(.*?)^```$", text, re.DOTALL | re.MULTILINE)
    ]


def command_lines(block: str) -> list[str]:
    return [line.strip() for line in block.splitlines() if COMMAND in line]


def test_the_section_runs_the_removal_form_dry_run_first_then_the_delete_with_its_code() -> None:
    running = [(start, end, block) for start, end, block in shell_blocks(section()) if command_lines(block)]

    assert len(running) == 2, (
        f"the section runs the command in {len(running)} block(s), not a dry run and a delete"
    )
    (_, dry_run_end, dry_run), (delete_start, _, delete) = running
    assert command_lines(dry_run) == [
        f'DEBATE_ENV="$REMOVAL_ENV" uv run {COMMAND} --caselist "$CASELIST" --for-removal'
    ]
    assert command_lines(delete) == [
        f'DEBATE_ENV=prod uv run {COMMAND} --caselist "$CASELIST" --for-removal --delete '
        '--confirm "$CASSETTES_CODE" --confirm-prod',
        f'DEBATE_ENV="$REMOVAL_ENV" uv run {COMMAND} --caselist "$CASELIST" --for-removal --delete '
        '--confirm "$CASSETTES_CODE"',
    ]
    lines = [line.strip() for line in delete.splitlines()]
    assert "CASSETTES_CODE=" in lines
    assert lines.index('if [ -z "$CASSETTES_CODE" ]; then') < lines.index(command_lines(delete)[0])
    assert lines.index('elif [ "$REMOVAL_ENV" = "prod" ]; then') < lines.index(command_lines(delete)[0])
    assert "Stop, and do not run the next block, if" in section()[dry_run_end:delete_start]


def test_each_block_refuses_a_shell_with_a_leftover_debate_variable() -> None:
    for _, _, block in shell_blocks(section()):
        if command_lines(block):
            assert "env | grep -q '^DEBATE_'" in block, block.splitlines()[0]


def test_the_section_still_tells_the_pm_that_the_evaluation_is_recorded_again() -> None:
    assert "tell the PM, since the evaluation is then recorded again" in " ".join(section().split())


def test_no_block_in_the_runbook_deletes_the_cassettes_by_hand_or_by_the_purges_form() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")

    for _, _, block in shell_blocks(text):
        assert not re.search(r"\brm\b[^\n]*model-cassettes", block), "a block deletes the cassette directory"
        for line in command_lines(block):
            assert "--for-removal" in line, f"a block runs the purge's form after a removal: {line}"

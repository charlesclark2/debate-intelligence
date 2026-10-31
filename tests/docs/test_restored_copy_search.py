"""The runbooks' search for leftover restored copies, run on a synthetic home folder (`v1-e40-t21`).

`docs/runbooks/annual-purge.md`'s step 1 and `docs/runbooks/landscape-report-from-the-cloud-run.md`'s
last step each end with the same two searches: every directory holding the marker
`caselist restore-run-state` writes (:data:`RESTORED_COPY_MARKER`), at any depth, and, labelled
"restored before the marker", a directory holding `debate.sqlite3` three levels down with no marker.
Each test takes the commands out of the runbook as written and runs them in a shell over a tree under
`tmp_path`, with `HOME` pointed at it and `/tmp` replaced by a directory of its own, so a change to
the runbook is what is tested. What must hold:

* a copy holding the marker is listed at any depth, in the home folder and in `/tmp`;
* a directory holding `debate.sqlite3` and no marker is never a restored copy; three levels down or
  less it is listed under "restored before the marker", and deeper not at all;
* a marked copy is listed once, not again as restored before the marker;
* the dev and prod data directories are never listed, even holding a marker; nor is anything under
  `~/Library` or the Trash.

Every name here is invented: no school, team code or real path.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Final

import pytest

from debate_core.application.caselist.run_state_restore import RESTORED_COPY_MARKER

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
PURGE_RUNBOOK: Final = REPO_ROOT / "docs" / "runbooks" / "annual-purge.md"
LANDSCAPE_RUNBOOK: Final = REPO_ROOT / "docs" / "runbooks" / "landscape-report-from-the-cloud-run.md"
PURGE_SECTION: Final = "## Step 1 — No working copy left on this Mac\n"
LANDSCAPE_SECTION: Final = "## 5. Delete the copy\n"
SEARCH_START: Final = 'find -H "$HOME" /tmp '
SHELLS: Final = [shell for shell in ("bash", "zsh") if shutil.which(shell)]
"""The operator pastes into zsh; CI's runner may have only bash. Each that is here runs the search."""


def section_block(runbook: Path, heading: str) -> str:
    """The one `bash` block in the runbook's section under `heading`."""
    section = runbook.read_text(encoding="utf-8").split(heading, 1)[1].split("\n## ", 1)[0]
    [block] = re.findall(r"^```bash\n(.*?)^```$", section, re.DOTALL | re.MULTILINE)
    return block


def search_lines(block: str) -> list[str]:
    return [line for line in block.splitlines() if line.startswith(SEARCH_START)]


def the_purge_search() -> list[str]:
    return search_lines(section_block(PURGE_RUNBOOK, PURGE_SECTION))


def the_landscape_search() -> list[str]:
    return search_lines(section_block(LANDSCAPE_RUNBOOK, LANDSCAPE_SECTION))


RUNBOOK_SEARCHES: Final = {
    "the annual purge's step 1": the_purge_search,
    "the landscape runbook's last step": the_landscape_search,
}


def plant(directory: Path, *names: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    for name in names:
        (directory / name).write_text(
            "{}\n" if name == RESTORED_COPY_MARKER else "a database\n", encoding="utf-8"
        )
    return directory


class Tree:
    """A home folder and a `/tmp` with one of each kind of directory the search must tell apart."""

    def __init__(self, root: Path, *, planted: bool = True) -> None:
        self.home = plant(root / "home")
        self.tmp = plant(root / "tmp")
        if planted:
            self.plant()

    def plant(self) -> None:
        both = (RESTORED_COPY_MARKER, "debate.sqlite3")
        self.dev = plant(self.home / ".debate-research" / "dev", *both)
        self.prod = plant(self.home / ".debate-research" / "prod", *both)
        self.landscape_copy = plant(self.home / ".debate-research" / "landscape-copy-samplecl26", *both)
        self.deep_copy = plant(self.home / "one" / "two" / "three" / "four" / "copy-five-down", *both)
        self.stopped_copy = plant(self.home / "work" / "a" / "b" / "c" / "stopped-copy", RESTORED_COPY_MARKER)
        self.tmp_copy = plant(self.tmp / "one" / "two" / "three" / "four" / "copy-in-tmp", *both)
        self.before_the_marker = plant(
            self.home / ".debate-research" / "copy-before-the-marker", "debate.sqlite3"
        )
        self.plain_shallow = plant(self.tmp / "plain-shallow", "debate.sqlite3")
        self.plain_deep = plant(
            self.home / "one" / "two" / "three" / "four" / "plain-five-down", "debate.sqlite3"
        )
        self.in_library = plant(self.home / "Library" / "Caches" / "copy-in-library", *both)
        self.in_trash = plant(self.home / ".Trash" / "copy-in-the-trash", *both)
        # A directory named as the marker is not one.
        plant(self.home / "named-like-the-marker" / RESTORED_COPY_MARKER)

    def run(self, shell: str, lines: list[str]) -> tuple[list[str], list[str]]:
        """The two lists the search prints, each checked against the count after it."""
        script = "\n".join(lines) + "\n"
        assert script.count('"$HOME" /tmp ') == len(lines) == 2, "each search names the home folder and /tmp"
        script = script.replace('"$HOME" /tmp ', '"$HOME" "$SEARCHED_TMP" ')
        ran = subprocess.run(
            [shell, "-c", script],
            env={"PATH": os.environ["PATH"], "HOME": str(self.home), "SEARCHED_TMP": str(self.tmp)},
            capture_output=True,
            text=True,
            check=False,
        )
        assert ran.returncode == 0, ran.stderr
        printed = ran.stdout.splitlines()
        copies_end = next(i for i, line in enumerate(printed) if line.startswith("restored copies: "))
        before_end = next(
            i for i, line in enumerate(printed) if line.startswith("restored before the marker: ")
        )
        copies, before = printed[:copies_end], printed[copies_end + 1 : before_end]
        assert printed[copies_end] == f"restored copies: {len(copies)}"
        assert printed[before_end] == f"restored before the marker: {len(before)}"
        return copies, before


@pytest.fixture(params=SHELLS)
def shell(request: pytest.FixtureRequest) -> str:
    return request.param


@pytest.mark.parametrize("runbook", list(RUNBOOK_SEARCHES))
def test_a_marked_copy_is_found_at_any_depth_and_a_plain_database_directory_is_not(
    tmp_path: Path, shell: str, runbook: str
) -> None:
    tree = Tree(tmp_path)

    copies, _ = tree.run(shell, RUNBOOK_SEARCHES[runbook]())

    assert sorted(copies) == sorted(
        str(path) for path in (tree.landscape_copy, tree.deep_copy, tree.stopped_copy, tree.tmp_copy)
    )
    assert str(tree.plain_deep) not in copies and str(tree.plain_shallow) not in copies


@pytest.mark.parametrize("runbook", list(RUNBOOK_SEARCHES))
def test_a_database_three_levels_down_without_a_marker_is_listed_apart_as_restored_before_it(
    tmp_path: Path, shell: str, runbook: str
) -> None:
    tree = Tree(tmp_path)

    _, before = tree.run(shell, RUNBOOK_SEARCHES[runbook]())

    assert sorted(before) == sorted([str(tree.before_the_marker), str(tree.plain_shallow)])
    assert str(tree.landscape_copy) not in before, "a marked copy is listed once"


@pytest.mark.parametrize("runbook", list(RUNBOOK_SEARCHES))
def test_the_data_directories_library_and_trash_are_never_listed(
    tmp_path: Path, shell: str, runbook: str
) -> None:
    tree = Tree(tmp_path)

    copies, before = tree.run(shell, RUNBOOK_SEARCHES[runbook]())

    never = {str(path) for path in (tree.dev, tree.prod, tree.in_library, tree.in_trash)}
    assert never.isdisjoint(copies + before)


@pytest.mark.parametrize("runbook", list(RUNBOOK_SEARCHES))
def test_an_empty_home_folder_lists_nothing(tmp_path: Path, shell: str, runbook: str) -> None:
    """The success line the runbooks ask for: two zero counts."""
    assert Tree(tmp_path, planted=False).run(shell, RUNBOOK_SEARCHES[runbook]()) == ([], [])


def test_both_runbooks_search_with_the_same_commands_and_the_purge_block_is_only_the_search() -> None:
    assert the_landscape_search() == the_purge_search()
    assert (
        search_lines(section_block(PURGE_RUNBOOK, PURGE_SECTION))
        == section_block(PURGE_RUNBOOK, PURGE_SECTION).splitlines()
    ), "the purge's step 1 block is the search and nothing else, so all of it is tested"


def test_the_runbooks_name_the_marker_the_restore_writes() -> None:
    for line in the_purge_search():
        assert RESTORED_COPY_MARKER in line

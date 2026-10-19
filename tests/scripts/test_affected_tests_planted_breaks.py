"""Planted breaks: a deliberate break in a real module fails a test `affected_tests.py` selects (v1-e01-t28).

For each break in `PLANTED_BREAKS`, across the four workspace packages, the module is broken in a
clone of this repository's HEAD in a temporary directory and committed there. The script then
describes that commit (`--diff HEAD`, read from git), and pytest runs the selected test files
nearest the break, the ones with the shortest chain back to it, against the clone: its packages
first on `PYTHONPATH`, so the broken copy is the one imported. At least one of them must fail. The
clone is reset after each break and its bytes compared with the original, and this worktree is
never written to.

Each break prints its selection's size; run with `-s` to see them. The run takes about a minute,
so it is marked `slow` and is not on the pull-request path: it is the evidence for the task's
planted-break criterion, run on request (`uv run pytest -m slow -s -k planted tests/scripts`).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
NEAREST_TESTS_RUN = 10


@dataclass(frozen=True)
class PlantedBreak:
    name: str
    path: str
    old: str
    new: str


CORE = "packages/debate_core/src/debate_core"

PLANTED_BREAKS = [
    PlantedBreak(
        "debate_core: a DOI keeps a trailing dot",
        f"{CORE}/retrieval/identifiers.py",
        "            return candidate\n",
        '            return candidate + "."\n',
    ),
    PlantedBreak(
        "debate_core: a canonical URL keeps its default port",
        f"{CORE}/retrieval/canonical_url.py",
        "return None if port == _DEFAULT_PORTS[scheme] else port",
        "return port",
    ),
    PlantedBreak(
        "debate_core: the bundled public suffix list gains a line",
        f"{CORE}/retrieval/data/public_suffix_list.dat",
        "// ===BEGIN ICANN DOMAINS===\n",
        "// ===BEGIN ICANN DOMAINS===\nplanted.example\n",
    ),
    PlantedBreak(
        "debate_core.testing: the file builder's fingerprint is reversed",
        f"{CORE}/testing/file_builder.py",
        "return self.occurrence.exact_fingerprint\n",
        "return self.occurrence.exact_fingerprint[::-1]\n",
    ),
    PlantedBreak(
        "debate_cli: a retrieval failure exits 4",
        "packages/debate_cli/src/debate_cli/exit_codes.py",
        "    RETRIEVAL_FAILURE = 3\n",
        "    RETRIEVAL_FAILURE = 4\n",
    ),
    PlantedBreak(
        "debate_api: the package fails to import",
        "packages/debate_api/src/debate_api/__init__.py",
        '"""HTTP API service: a thin surface over debate_core."""\n',
        '"""HTTP API service: a thin surface over debate_core."""\n\nraise ImportError("planted break")\n',
    ),
    PlantedBreak(
        "debate_workers: the package fails to import",
        "packages/debate_workers/src/debate_workers/__init__.py",
        '"""Asynchronous job handlers: a thin surface over debate_core."""\n',
        '"""Asynchronous job handlers: a thin surface over debate_core."""\n'
        'raise ImportError("planted break")\n',
    ),
]


def git(root: Path, *args: str) -> str:
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=root,
        env=environment,
        capture_output=True,
        check=True,
        text=True,
    ).stdout


@pytest.fixture(scope="module")
def clone(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    head = git(REPO_ROOT, "rev-parse", "HEAD").strip()
    root = tmp_path_factory.mktemp("planted") / "clone"
    git(REPO_ROOT.parent, "clone", "--quiet", "--shared", "--no-checkout", str(REPO_ROOT), str(root))
    git(root, "checkout", "--quiet", "--detach", head)
    yield root
    assert git(root, "status", "--porcelain") == ""


@pytest.mark.slow
@pytest.mark.parametrize("planted", PLANTED_BREAKS, ids=[planted.name for planted in PLANTED_BREAKS])
def test_a_planted_break_fails_a_test_the_script_selects(clone: Path, planted: PlantedBreak) -> None:
    target = clone / planted.path
    original = target.read_bytes()
    text = original.decode()
    assert text.count(planted.old) == 1, f"the break no longer matches {planted.path}"
    target.write_text(text.replace(planted.old, planted.new), encoding="utf-8")
    git(clone, "commit", "--quiet", "--all", "--message", f"planted break: {planted.name}")
    try:
        chosen = subprocess.run(
            [sys.executable, str(clone / "scripts" / "affected_tests.py"), "--diff", "HEAD", "--explain"],
            cwd=clone,
            capture_output=True,
            text=True,
            check=True,
        )
        assert not chosen.stdout.startswith("The whole selection"), chosen.stdout
        reasons = dict(line.split("  <- ", 1) for line in chosen.stdout.splitlines())
        reached = {test: reason for test, reason in reasons.items() if planted.path in reason}
        assert reached, f"no selected test is traced to {planted.path}:\n{chosen.stdout}"
        nearest = sorted(reached, key=lambda test: (reached[test].count(", which "), test))[
            :NEAREST_TESTS_RUN
        ]
        sources = os.pathsep.join(str(path) for path in sorted(clone.glob("packages/*/src")))
        ran = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-n", "0", "-x", *nearest],
            cwd=clone,
            env={**os.environ, "PYTHONPATH": sources},
            capture_output=True,
            text=True,
            check=False,
        )
        summary = ran.stdout.strip().splitlines()[-1] if ran.stdout.strip() else ran.stderr
        total = re.search(r"of (\d+) test files", chosen.stderr)
        print(
            f"\n{planted.name}: {len(reasons)} of {total.group(1) if total else '?'} test files selected, "
            f"{len(reached)} traced to {planted.path}; the nearest {len(nearest)} ran: {summary}"
        )
        assert ran.returncode == 1 and " failed" in summary, ran.stdout[-3000:] + ran.stderr[-2000:]
    finally:
        git(clone, "reset", "--quiet", "--hard", "HEAD~1")
        assert target.read_bytes() == original

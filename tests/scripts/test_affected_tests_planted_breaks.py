"""Planted breaks: a break in a real module is caught by a test `affected_tests.py` selects (v1-e01-t28).

For each break in `PLANTED_BREAKS`, across the four workspace packages, the module is broken in a
clone of this repository's HEAD in a temporary directory and committed there. The script then
describes that commit (`--diff HEAD`, read from git), and pytest runs the selected test files
nearest the break against the clone: first those that mention a name from the changed line (the
tests that read what broke), then the ones with the shortest chain back to it, its packages first on
`PYTHONPATH`, so the broken copy is the one imported. At least one of them must catch it. (The
mention comes first since the PM batch of 2026-10-27 (x): by chain and path alone, `exit_codes.py`'s
break ran ten slow bucket-mode files that never read `RETRIEVAL_FAILURE` and was not caught, so
validate-dev's slow tier failed on `v1.1.0-dev.160`. Ordering by recorded durations is
`v1-e01-t40`.)
The clone is reset after each break and its bytes compared with the original, and this worktree is
never written to.

**What counts as caught** (v1-e01-t34) is read from pytest's exit code and its own words, by
:func:`how_caught`: a selected test failed, a selected test errored (a fixture broke), a selected
test file failed to collect, or a conftest the selected tests load failed to import (pytest exits
4 and says `ImportError while loading conftest`, whatever the exception was). Until v1-e01-t34 only
a failed test counted, so validate-dev went red from 2026-10-20 when `debate_api`'s break began to
surface as a collection error, and then as a conftest import error, and the file builder's as a
fixture error. Nothing else counts: no test ran, every test passed, a usage error, an internal
error. `test_a_break_no_selected_test_reaches_is_not_counted_as_caught` holds that with a real
break nothing reaches, so the check still fails when nothing catches a break.

v1-e01-t32 narrowed five edges (command registration, the contract suites' re-exports, a conftest
read fixture by fixture, a path that names only what it denotes, an import-linter-only root
`pyproject.toml`) and added a break for each: a narrowed edge is done only when a break in the code
a test uses still selects that test, and it fails.

Each break prints its selection's size; run with `-s` to see them. The run takes about two minutes,
so it is marked `slow` and is not on the pull-request path: validate-dev's slow tier runs it on
every dev pre-release, and it runs on request with `uv run pytest -m slow -s -k planted tests/scripts`.
The tests of :func:`how_caught` itself are fast and run on every pull request.
"""

from __future__ import annotations

import builtins
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
_BUILTINS = frozenset(dir(builtins))


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
    # v1-e01-t32: one for each edge that round narrowed. A test that uses the broken code must still
    # be selected, and fail.
    PlantedBreak(
        "debate_cli: a caselist slug implies the wrong event, outside the commands package",
        "packages/debate_cli/src/debate_cli/caselist_events.py",
        '    "hsld": Event.LD,\n',
        '    "hsld": Event.POLICY,\n',
    ),
    PlantedBreak(
        "debate_core.testing: the contract harness counts every page twice, with no package re-export",
        f"{CORE}/testing/contracts/harness.py",
        "        pages += 1\n",
        "        pages += 2\n",
    ),
    PlantedBreak(
        "debate_core: a local version listing drops its last version, used by a caselist conftest fixture",
        f"{CORE}/integrations/local/fs_version_store.py",
        "        return tuple(sorted(found))\n",
        "        return tuple(sorted(found))[:-1]\n",
    ),
    PlantedBreak(
        # The harvest test reads it as "extraction/news-article.html", a path from no folder of its own.
        "tests/fixtures: a fixture page's title changes, read by the end of its path",
        "tests/fixtures/extraction/news-article.html",
        '<meta property="og:title" content="Scientists say mammoth revival is years away">',
        '<meta property="og:title" content="Scientists say a planted revival is years away">',
    ),
    PlantedBreak(
        "pyproject.toml: an import-linter contract is renamed, and nothing else changes",
        "pyproject.toml",
        'name = "The keychain library stays inside debate_core.integrations.opencaselist"\n',
        'name = "The keychain library stays inside debate_core.integrations.opencaselist, planted"\n',
    ),
]

#: A real break that no selected test can reach: a function nothing calls answers wrongly. The
#: module is imported by hundreds of tests, so the script selects them and they run, and pass.
UNREACHED_BREAK = PlantedBreak(
    "debate_core: a function nothing calls answers wrongly",
    f"{CORE}/retrieval/identifiers.py",
    "from __future__ import annotations\n",
    "from __future__ import annotations\n\n\ndef _planted_and_never_called() -> int:\n    return 2 + 2 + 1\n",
)


# --------------------------------------------------------------------------------------------
# What counts as caught
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class SelectedRun:
    """pytest's run over the selected tests: its exit code and everything it printed."""

    returncode: int
    stdout: str
    stderr: str

    @property
    def summary(self) -> str:
        """pytest's last line, `1 failed, 7 deselected in 0.93s`, or its first complaint."""
        if self.stdout.strip():
            return self.stdout.strip().splitlines()[-1]
        return self.stderr.strip().splitlines()[0] if self.stderr.strip() else ""


def how_caught(run: SelectedRun) -> str | None:
    """How the selected tests caught a break, or None when nothing did.

    pytest exits 1 when a test failed or errored, 2 when it stopped at a collection error, and 4
    when a conftest failed to import, which it reports as `ImportError while loading conftest`
    whatever the exception was. Exit 4 is also a usage error or a missing file, so the code alone
    decides nothing: the summary line or the conftest message has to say what happened.
    """
    if run.returncode == 4:
        loaded = "ImportError while loading conftest" in run.stderr + run.stdout
        return "a conftest the selected tests load failed to import" if loaded else None
    if run.returncode not in (1, 2):
        return None
    if re.search(r"\b\d+ errors?\b", run.summary) and "ERROR collecting " in run.stdout:
        return "a selected test file failed to collect"
    if run.returncode == 1 and re.search(r"\b\d+ failed\b", run.summary):
        return "a selected test failed"
    if run.returncode == 1 and re.search(r"\b\d+ errors?\b", run.summary):
        return "a selected test errored"
    return None


# --------------------------------------------------------------------------------------------
# The planted breaks, in a clone
# --------------------------------------------------------------------------------------------


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


def changed_names(planted: PlantedBreak) -> frozenset[str]:
    """The names in the line a break changes that a test reading the broken code would mention.

    Only names shaped like a module's own (a constant, a class, an attribute in snake case: a capital
    or an underscore in it), never a builtin: `tuple`, `sorted` or a local such as `found` would
    prefer any test at all.
    """
    words = re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", planted.old)
    return frozenset(
        word
        for word in words
        if (any(c.isupper() for c in word) or "_" in word.strip("_")) and word not in _BUILTINS
    )


def names_any(test: Path, names: frozenset[str]) -> bool:
    """Whether a selected test file mentions any of `names` as a whole word."""
    if not names or not test.is_file():
        return False
    text = test.read_text(encoding="utf-8", errors="replace")
    return any(re.search(rf"\b{re.escape(name)}\b", text) for name in names)


def plant_and_run(clone: Path, planted: PlantedBreak) -> SelectedRun:
    """Commit `planted` in the clone, run the selected tests nearest it, and put the clone back."""
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
        names = changed_names(planted)
        nearest = sorted(
            reached,
            key=lambda test: (not names_any(clone / test, names), reached[test].count(", which "), test),
        )[:NEAREST_TESTS_RUN]
        sources = os.pathsep.join(str(path) for path in sorted(clone.glob("packages/*/src")))
        ran = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-n", "0", "-x", *nearest],
            cwd=clone,
            env={**os.environ, "PYTHONPATH": sources},
            capture_output=True,
            text=True,
            check=False,
        )
        run = SelectedRun(ran.returncode, ran.stdout, ran.stderr)
        total = re.search(r"of (\d+) test files", chosen.stderr)
        print(
            f"\n{planted.name}: {len(reasons)} of {total.group(1) if total else '?'} test files selected, "
            f"{len(reached)} traced to {planted.path}; the nearest {len(nearest)} ran "
            f"(exit {run.returncode}): {run.summary}; caught: {how_caught(run) or 'no'}"
        )
        return run
    finally:
        git(clone, "reset", "--quiet", "--hard", "HEAD~1")
        assert target.read_bytes() == original


@pytest.mark.slow
@pytest.mark.parametrize("planted", PLANTED_BREAKS, ids=[planted.name for planted in PLANTED_BREAKS])
def test_a_planted_break_is_caught_by_a_test_the_script_selects(clone: Path, planted: PlantedBreak) -> None:
    run = plant_and_run(clone, planted)

    assert how_caught(run), f"exit {run.returncode}\n{run.stdout[-3000:]}{run.stderr[-2000:]}"


@pytest.mark.slow
def test_a_break_no_selected_test_reaches_is_not_counted_as_caught(clone: Path) -> None:
    run = plant_and_run(clone, UNREACHED_BREAK)

    assert run.returncode == 0 and re.search(r"\b\d+ passed\b", run.summary), run.stdout[-3000:]
    assert how_caught(run) is None


# --------------------------------------------------------------------------------------------
# how_caught, on pytest's own words (recorded from pytest 8 runs, abridged by hand)
# --------------------------------------------------------------------------------------------

COLLECTION_ERROR_OUTPUT = """\
==================================== ERRORS ====================================
_______ ERROR collecting packages/debate_api/tests/test_pilot_placeholder_app.py _______
ImportError while importing test module '/tmp/clone/packages/debate_api/tests/test_pilot_placeholder_app.py'.
packages/debate_api/src/debate_api/__init__.py:3: in <module>
    raise ImportError("planted break")
E   ImportError: planted break
=========================== short test summary info ============================
ERROR packages/debate_api/tests/test_pilot_placeholder_app.py
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
1 warning, 1 error in 0.54s
"""

CONFTEST_IMPORT_ERROR = """\
ImportError while loading conftest '/tmp/clone/packages/debate_api/tests/conftest.py'.
packages/debate_api/tests/conftest.py:31: in <module>
    from debate_api.app import create_app
packages/debate_api/src/debate_api/__init__.py:3: in <module>
    raise ImportError("planted break")
E   ImportError: planted break
"""


@pytest.mark.parametrize(
    ("run", "caught"),
    [
        pytest.param(
            SelectedRun(1, "F\n=== FAILURES ===\n1 failed, 7 deselected in 0.93s\n", ""),
            "a selected test failed",
            id="a test failed",
        ),
        pytest.param(
            SelectedRun(
                1, "E\n=== ERRORS ===\nERROR at setup of test_a_file\n7 deselected, 1 error in 0.35s\n", ""
            ),
            "a selected test errored",
            id="a fixture errored",
        ),
        pytest.param(
            SelectedRun(1, COLLECTION_ERROR_OUTPUT, ""),
            "a selected test file failed to collect",
            id="a test file failed to collect, stopped by -x",
        ),
        pytest.param(
            SelectedRun(2, "!!! Interrupted: 1 error during collection !!!\n" + COLLECTION_ERROR_OUTPUT, ""),
            "a selected test file failed to collect",
            id="a test file failed to collect, interrupted",
        ),
        pytest.param(
            SelectedRun(4, "", CONFTEST_IMPORT_ERROR),
            "a conftest the selected tests load failed to import",
            id="a conftest failed to import",
        ),
    ],
)
def test_a_failure_an_error_or_a_collection_error_is_caught(run: SelectedRun, caught: str) -> None:
    assert how_caught(run) == caught


@pytest.mark.parametrize(
    "run",
    [
        pytest.param(SelectedRun(0, "....\n110 passed, 7 deselected in 0.37s\n", ""), id="every test passed"),
        pytest.param(SelectedRun(5, "\n7 deselected in 0.10s\n", ""), id="no test ran"),
        pytest.param(
            SelectedRun(
                4,
                "",
                "ERROR: usage: python -m pytest [options] [file_or_dir] [file_or_dir] [...]\n"
                "python -m pytest: error: unrecognized arguments: --bogus\n",
            ),
            id="a usage error",
        ),
        pytest.param(
            SelectedRun(
                4, "\n\nno tests ran in 0.06s\n", "ERROR: file or directory not found: test_gone.py\n"
            ),
            id="a selected file is missing",
        ),
        pytest.param(
            SelectedRun(
                3, "INTERNALERROR> Traceback (most recent call last):\nINTERNALERROR> KeyError\n", ""
            ),
            id="an internal error",
        ),
        pytest.param(
            SelectedRun(2, "!!! KeyboardInterrupt !!!\nno tests ran in 3.00s\n", ""),
            id="an interrupt",
        ),
    ],
)
def test_anything_else_is_not_caught(run: SelectedRun) -> None:
    assert how_caught(run) is None

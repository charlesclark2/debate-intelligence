"""Run the slow tests a pull request's affected set reaches, as ci.yml's `slow-tests` job does (v1-e41-t29).

`v1-e08-t24` changed the ranking and broke `tests/integration/test_e2e_research.py`. The pull
request's affected set chose that file, but its `test` parts run `-m "not slow and not live"`, so
nothing ran it until validate-dev's slow tier on dev, which went red for a day. Since then a pull
request into dev runs the same affected set a second time, here, with validate-dev's slow-tier
markers (`validate_dev.SLOW`, imported, so the two cannot drift): only the slow tests, of only the
files the parts were handed. For the whole selection it is every slow test.

**Four tests stay on validate-dev only** (the PM's ruling, 2026-11-13). `LEFT_TO_VALIDATE_DEV`
names them by node id, each with its reason; pytest deselects them here and the job summary prints
them. A new entry is a reviewed change: tests/scripts/test_ci_slow_tests_the_affected_set_reaches.py
pins the four.

**A skip fails the job**, as it fails validate-dev's tier: a check skipped for a missing browser,
program or image did not run. A slow test that needs what this job does not install goes on the
list above with its reason, rather than passing unseen. No slow test left to run (pytest's exit 5)
passes: the files chosen held none but the four.

`ci_test_selection.py` decides whether the job runs at all (`run_slow`) by `may_hold_slow_tests`, a
text check that can only say yes more often than pytest would, and whether it needs Chromium
(`needs_chromium`). `scripts/affected_tests.py --run --slow` runs the same command over a session's
affected set (working agreement 10).

Usage, as ci.yml's `slow-tests` job runs it (the file holds one test file per line; empty is the
whole selection):
  python scripts/ci_slow_tests.py --test-files "$RUNNER_TEMP/test-selection.txt" \\
      --junit "$RUNNER_TEMP/slow-tests.xml" --summary "$GITHUB_STEP_SUMMARY"
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import validate_dev

#: validate-dev's slow tier, which the PR's slow run must equal.
MARKERS = validate_dev.SLOW.marker_expression

#: The slow tests a pull request leaves to validate-dev, by node id, and why (the PM's ruling,
#: 2026-11-13). A file's id deselects every test in it, which here is its slow tests alone: the
#: parts run its others.
LEFT_TO_VALIDATE_DEV: dict[str, str] = {
    "tests/scripts/test_affected_tests_planted_breaks.py": (
        "the planted-break cases: every task pull request reaches them through its own spec, and on a "
        "runner they are most of validate-dev's 379-453-s slow tier; they prove the selection against "
        "the whole repository on every dev pre-release"
    ),
    "packages/debate_core/tests/evidence/test_docx_renderer.py::"
    "test_libreoffice_opens_a_rendered_document_headless_and_reads_every_paragraph": (
        "needs LibreOffice, which validate-dev's slow job installs"
    ),
    "packages/debate_core/tests/integrations/local/test_search_index_sqlite_features.py::"
    "test_search_index_opens_in_the_lambda_image_sqlite": (
        "needs the arm64 Lambda base image under QEMU, which validate-dev's slow job pulls"
    ),
    "packages/debate_core/tests/integrations/local/test_search_index_reader_sqlite_features.py::"
    "test_search_index_reader_statements_run_in_the_lambda_image_sqlite": (
        "needs the arm64 Lambda base image under QEMU, which validate-dev's slow job pulls"
    ),
}

#: The text a file that holds a slow test carries, or a conftest above it: `@pytest.mark.slow`,
#: `pytestmark = pytest.mark.slow`, `marks=pytest.mark.slow`. No plugin and no root conftest adds the
#: marker, which the tests of this file hold.
SLOW_MARK = "mark.slow"
#: Where the tests that drive Chromium live; the job installs Playwright's only when one is chosen.
CHROMIUM_TESTS = "packages/debate_api/tests/browser/"
EXIT_NO_TESTS_COLLECTED = 5


def left_out_files() -> frozenset[str]:
    return frozenset(node for node in LEFT_TO_VALIDATE_DEV if "::" not in node)


def may_hold_slow_tests(root: Path, test_file: str) -> bool:
    """Whether a slow test of this file may run here: the file or a conftest above it names the
    marker, and the file is not left to validate-dev whole. Yes whenever pytest could find one."""
    if test_file in left_out_files():
        return False
    folders = PurePosixPath(test_file).parents  # its own folder, each above it, and "." the root
    candidates = [root / test_file, *(root / folder / "conftest.py" for folder in folders)]
    return any(_names_the_marker(candidate) for candidate in candidates)


def _names_the_marker(path: Path) -> bool:
    try:
        return SLOW_MARK in path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False


def needs_chromium(test_files: Iterable[str] | None) -> bool:
    """Whether the job installs Playwright's Chromium: a chosen file drives it, or the whole selection."""
    return test_files is None or any(test.startswith(CHROMIUM_TESTS) for test in test_files)


def pytest_arguments(test_files: Sequence[str], junit: Path, *, workers: str = "auto") -> list[str]:
    """pytest's arguments: validate-dev's slow markers, the four left out, every chosen file (none is
    every testpath), its 25 slowest tests, and a JUnit report to count skips from."""
    return [
        "-n",
        workers,
        "--dist",
        "worksteal",
        "-m",
        MARKERS,
        *(f"--deselect={node}" for node in LEFT_TO_VALIDATE_DEV),
        "--durations=25",
        "-rfEs",
        f"--junitxml={junit}",
        "-o",
        "junit_family=xunit2",
        *test_files,
    ]


@dataclass(frozen=True)
class Outcome:
    exit_code: int
    counts: validate_dev.JUnitCounts | None

    @property
    def problems(self) -> list[str]:
        """Why the run did not pass; empty when it did. No slow test to run passes; a skip does not."""
        if self.exit_code == EXIT_NO_TESTS_COLLECTED:
            return []
        if self.counts is None:
            return [f"pytest wrote no JUnit report (exit {self.exit_code})"]
        problems = []
        if self.exit_code != 0:
            problems.append(f"pytest exited {self.exit_code}")
        if self.counts.failures or self.counts.errors:
            problems.append(f"{self.counts.failures} failed, {self.counts.errors} errors")
        if self.counts.skipped:
            problems.append(
                f"{self.counts.skipped} skipped: a skipped check did not run, so this job fails, as "
                "validate-dev's slow tier does. A slow test that needs what the job does not install "
                "goes on LEFT_TO_VALIDATE_DEV in scripts/ci_slow_tests.py, with its reason:\n    "
                + "\n    ".join(self.counts.skipped_names)
            )
        return problems


def run(
    test_files: Sequence[str], junit: Path, *, root: Path, python: str = sys.executable, workers: str = "auto"
) -> Outcome:
    junit.unlink(missing_ok=True)
    command = [python, "-m", "pytest", *pytest_arguments(test_files, junit, workers=workers)]
    print(f"== slow tests: {' '.join(command)}", flush=True)
    completed = subprocess.run(command, cwd=root, check=False)
    return Outcome(completed.returncode, validate_dev.read_junit(junit))


def summary(test_files: Sequence[str], outcome: Outcome) -> str:
    chosen = f"the slow tests of {len(test_files)} chosen test files" if test_files else "every slow test"
    if outcome.exit_code == EXIT_NO_TESTS_COLLECTED:
        verdict = "No slow test was left to run among them."
    elif outcome.problems:
        verdict = "Failed: " + "; ".join(problem.splitlines()[0] for problem in outcome.problems) + "."
    else:
        counts = outcome.counts
        verdict = f"{counts.tests if counts else 0} passed."
    left = "\n".join(f"- `{node}`: {reason}" for node, reason in LEFT_TO_VALIDATE_DEV.items())
    return (
        "### Slow tests\n\n"
        f"Ran {chosen}, with validate-dev's markers `{MARKERS}`. {verdict}\n\n"
        f"Left to validate-dev's slow tier, which runs them on every dev pre-release:\n\n{left}\n"
    )


def read_test_files(path: Path) -> list[str]:
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument(
        "--test-files",
        type=Path,
        required=True,
        help="one test file per line; an empty file is every testpath",
    )
    parser.add_argument("--junit", type=Path, required=True, help="where pytest writes its JUnit report")
    parser.add_argument("--summary", type=Path, help="a Markdown file to append the summary to")
    arguments = parser.parse_args(argv)

    root = Path(__file__).resolve().parents[1]
    test_files = read_test_files(arguments.test_files)
    outcome = run(test_files, arguments.junit, root=root)
    text = summary(test_files, outcome)
    print(text)
    for problem in outcome.problems:
        print(f"   {problem}", flush=True)
    if arguments.summary is not None:
        with arguments.summary.open("a", encoding="utf-8") as file:
            file.write(text)
    return 1 if outcome.problems else 0


if __name__ == "__main__":
    sys.exit(main())

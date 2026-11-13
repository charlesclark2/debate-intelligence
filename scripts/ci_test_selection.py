"""Choose the test files ci.yml's `test` parts run, and say why in the job summary (v1-e01-t38).

A pull request into dev runs the tests its changes reach: `scripts/affected_tests.py`'s selection
(v1-e01-t28), read against the pull request's base commit, with its always-run list and its
whole-selection rule for shared test ground. Every other run is the whole default selection:

* a pull request into main, which is a promotion;
* a push to dev or main, which is the record that the merged result is green, and which the dev
  pre-release waits for;
* a dispatched run, and any other event;
* and, on a pull request into dev, a selection that names the whole selection, a base commit that
  is not in the checkout, a selection that fails, or one that comes back empty.

One change runs no test at all (v1-e41-t15): ROADMAP.md and docs/README.md alone, which
refresh-generated-files.yml regenerates from the tree. The tests that read such files read
fixtures, and ci.yml's spec-validate checks the real files' links and descriptions on every run.
The bot's pull request is opened with the workflow token, which starts no pull_request run, so the
bot dispatches ci on its branch; that run is compared with origin/dev, and it too runs no test when
the branch changes only those files. Until then each refresh pull request ran all eight parts.

It also says how many parts run (v1-e41-t16): one per 30 test files chosen, at least one and at
most MOST_PARTS, and MOST_PARTS for the whole selection. Every part pays its setup and its own
collection, and until then every selection ran in all eight, including an affected set of a few
dozen files. Thirty test files are about 1,000 tests on today's suite, which a runner's part runs in
about 100 s, under working agreement 1's 2-minute line (docs/process/ci-test-part-costs.md has the
figures). The count is the selection's own, so it costs nothing on the parts' path.

It also deals the chosen files to the parts (v1-e41-t17): whole files, by the durations dev's last
push run recorded, which the `test-selection` job restores from GitHub's Actions cache and hands this
script as `--durations`. scripts/ci_test_durations.py makes the deal and says when it cannot be made:
a record missing, unreadable or stale deals the parts test by test, as before, with the reason in the
job summary, and never fails the run. For the whole selection the files dealt are every test file
under pyproject.toml's `testpaths`, as scripts/affected_tests.py lists them. Every part is handed the
same deal, and since v1-e41-t18 each collects only the files it gives that part and any it does not
name (run_in_parts.py), so the deal is also each part's list of files: one output for every part,
which a missing or empty deal leaves collecting everything as before.

It also chooses for ci.yml's `slow-tests` job (v1-e41-t29): on a pull request into dev, the
chosen files, or for the whole selection every test file, that may hold a slow test
(`ci_slow_tests.may_hold_slow_tests`, a text check that says yes whenever pytest could find one).
The job runs their slow tests with validate-dev's markers, less the four tests left to validate-dev.
Until then the parts' `not slow` dropped them, and v1-e08-t24's ranking change broke a slow e2e test
its affected set had chosen, which only validate-dev on dev then ran. Every other run leaves the slow
tier to validate-dev.

It fails toward more tests, never fewer. The choice is written in `$GITHUB_OUTPUT`'s format:
`run_parts`, whether the parts run at all, `parts`, the matrix's list of part numbers as JSON,
`files_to_parts`, the deal as JSON on one line (empty: test by test), and
`test_files`, one test file per line, for pytest to read as `@FILE`. For the whole selection the
list is empty: pytest given no paths runs every path in `testpaths`. If this script itself cannot
run, the workflow step hands the parts the whole selection in the most parts, so a crash here is
also the whole selection.

ci.yml's `test-selection` job runs this once and hands the choice and the deal to every part, which
deals the same list by the same deal (run_in_parts.py), so the parts together are exactly the selection;
tests/scripts/test_ci_workflow_test_job.py proves it. Until v1-e41-t15 every part ran this for
itself, 17 to 33 seconds eight times over. Nothing here reads a secret or uses the network: the
base commit and origin/dev come with the checkout.

Usage, as ci.yml's `test-selection` job runs it:
  python scripts/ci_test_selection.py --event pull_request --base-branch dev --base-sha SHA \\
      --ref-name 123/merge --durations "$RUNNER_TEMP/test-durations/test-durations.json" \\
      --outputs outputs.txt --summary "$GITHUB_STEP_SUMMARY"
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import affected_tests
import ci_slow_tests
import ci_test_durations

# The one target branch whose pull requests run only the tests their changes reach.
AFFECTED_SET_BRANCH = "dev"
# What refresh-generated-files.yml regenerates, and the branch it pushes them to (v1-e01-t16).
GENERATED_FILES = frozenset({"ROADMAP.md", "docs/README.md"})
GENERATED_FILES_BRANCH = "bot/refresh-generated-files"
# How many parts run (v1-e41-t16, the PM's ruling of 2026-11-02): one per TEST_FILES_PER_PART test
# files chosen, never more than MOST_PARTS, which the whole selection always gets. A part's pytest step
# passing 2 minutes on a whole-selection run means a larger MOST_PARTS (working agreement 1).
TEST_FILES_PER_PART = 30
MOST_PARTS = 8
SIZES_THE_RULE_GIVES = list(range(1, MOST_PARTS + 1))
# The parts read `test_files` from an environment variable, and Linux refuses one over 128 KiB.
# 650 test files name about 42 KB.
LONGEST_LIST_FOR_THE_PARTS = 100_000


@dataclass(frozen=True)
class Choice:
    """The test files to run, None for the whole default selection or none at all, and why."""

    tests: tuple[str, ...] | None
    reason: str
    total: int = 0

    @property
    def runs_parts(self) -> bool:
        return self.tests != ()


def whole(reason: str) -> Choice:
    return Choice(None, reason)


def nothing(reason: str) -> Choice:
    return Choice((), reason)


def only_generated_files(changes: list[affected_tests.Change]) -> bool:
    """Whether the changes are regenerated generated files and nothing else; deleting one is not."""
    return bool(changes) and all(change.path in GENERATED_FILES and not change.deleted for change in changes)


def choose(root: Path, event: str, base_branch: str, base_sha: str, ref_name: str) -> Choice:
    return handed_to_the_parts(chosen(root, event, base_branch, base_sha, ref_name))


def chosen(root: Path, event: str, base_branch: str, base_sha: str, ref_name: str) -> Choice:
    if event == "push":
        return whole(f"a push to {ref_name or 'a branch'} runs the whole selection")
    if event == "workflow_dispatch" and ref_name == GENERATED_FILES_BRANCH:
        return dispatched_on_the_generated_files_branch(root)
    if event != "pull_request":
        return whole(f"a {event or 'run with no event name'} runs the whole selection")
    if base_branch != AFFECTED_SET_BRANCH:
        return whole(
            f"a pull request into {base_branch or 'an unnamed branch'} is a promotion, "
            "which runs the whole selection"
        )
    if not base_sha or not commit_exists(root, base_sha):
        return whole(
            f"the pull request's base commit {base_sha[:12] or '(none given)'} is not in the checkout"
        )
    try:
        changes = affected_tests.changed_files(root, base_sha, "HEAD", None)
        if only_generated_files(changes):
            return nothing("the pull request changes only the generated files")
        selection = affected_tests.select(affected_tests.Tree.working(root), changes)
    except (Exception, SystemExit) as error:  # affected_tests stops with SystemExit when git fails
        return whole(f"the selection failed ({error})")
    if selection.whole is not None:
        return whole(selection.whole)
    if not selection.tests:
        python_changed = sum(change.path.endswith(".py") for change in changes)
        return whole(f"the selection is empty, and {python_changed} Python files changed")
    return Choice(
        tuple(sorted(selection.tests)),
        f"the tests that {len(changes)} changed files reach, against the base commit {base_sha[:12]}",
        selection.total,
    )


def dispatched_on_the_generated_files_branch(root: Path) -> Choice:
    """The run refresh-generated-files.yml dispatches for its pull request, which no pull_request run
    checks: what the branch changes since it left dev, whatever its last commit did."""
    base = f"origin/{AFFECTED_SET_BRANCH}"
    try:
        changes = affected_tests.changed_files(root, base, "HEAD", None)
    except (Exception, SystemExit) as error:
        return whole(f"{GENERATED_FILES_BRANCH} could not be compared with {base} ({error})")
    if only_generated_files(changes):
        return nothing(f"{GENERATED_FILES_BRANCH} changes only the generated files")
    return whole(
        f"{GENERATED_FILES_BRANCH} changes more than the generated files, "
        "and a dispatch runs the whole selection"
    )


def handed_to_the_parts(choice: Choice) -> Choice:
    """The choice, or the whole selection when its list is too long for the parts to be handed."""
    if (
        choice.tests
        and len("".join(f"{test}\n" for test in choice.tests).encode()) > LONGEST_LIST_FOR_THE_PARTS
    ):
        return whole(f"the {len(choice.tests)} test files chosen are too long to hand to the parts")
    return choice


def parts_of(choice: Choice) -> list[int]:
    """The `test` job's matrix for this choice: part numbers 1 to N. When no part runs it is one part
    that never runs, since GitHub refuses an empty matrix whether or not the job's `if:` holds."""
    if choice.tests is None:
        parts = MOST_PARTS
    else:
        parts = min(MOST_PARTS, max(1, -(-len(choice.tests) // TEST_FILES_PER_PART)))
    return list(range(1, parts + 1))


def test_files_to_deal(root: Path, choice: Choice) -> list[str]:
    """The files the parts share: the chosen ones, or for the whole selection every test file under
    `testpaths`. A file pytest collects that is not among them is dealt test by test."""
    if choice.tests is not None:
        return list(choice.tests)
    return sorted(affected_tests.Layout.of(affected_tests.Tree.working(root)).test_files)


def dealing(
    root: Path, choice: Choice, durations: Path | None, now: datetime
) -> ci_test_durations.Deal | None:
    """The deal of the chosen files to the parts by the record at `durations`, or test by test and why;
    None when no part runs."""
    if not choice.runs_parts:
        return None
    parts = len(parts_of(choice))
    try:
        test_files = test_files_to_deal(root, choice)
    except (Exception, SystemExit) as error:
        return ci_test_durations.test_by_test(parts, f"the test files could not be listed ({error})")
    deal = ci_test_durations.deal(test_files, parts, durations, now)
    if len(ci_test_durations.as_output(deal).encode()) > LONGEST_LIST_FOR_THE_PARTS:
        return ci_test_durations.test_by_test(parts, "the deal is too long to hand to the parts")
    return deal


@dataclass(frozen=True)
class SlowChoice:
    """Whether ci.yml's `slow-tests` job runs, which test files it is handed, and why (v1-e41-t29)."""

    runs: bool
    test_files: tuple[str, ...]
    reason: str

    @property
    def chromium(self) -> bool:
        return self.runs and ci_slow_tests.needs_chromium(self.test_files or None)


def slow_choice(root: Path, choice: Choice, event: str, base_branch: str) -> SlowChoice:
    """The slow tests a pull request into dev runs: those of the chosen files, or of every test file
    for the whole selection, that may hold one (`ci_slow_tests.may_hold_slow_tests`). Every other run
    leaves the slow tier to validate-dev, which runs it whole on every dev pre-release. A test file
    list that cannot be read hands the job every testpath, so it fails toward more."""
    if event != "pull_request" or base_branch != AFFECTED_SET_BRANCH:
        return SlowChoice(False, (), "only a pull request into dev runs them here")
    if not choice.runs_parts:
        return SlowChoice(False, (), "no test part runs")
    try:
        candidates = test_files_to_deal(root, choice)
        holding = tuple(test for test in candidates if ci_slow_tests.may_hold_slow_tests(root, test))
    except (Exception, SystemExit) as error:
        return SlowChoice(True, (), f"the test files could not be read ({error}), so it runs every slow test")
    if not holding:
        return SlowChoice(False, (), "none of the chosen test files holds a slow test it runs")
    chosen = "the whole selection's" if choice.tests is None else "the chosen"
    return SlowChoice(True, holding, f"{len(holding)} of {chosen} test files hold slow tests")


def slow_summary(slow: SlowChoice) -> str:
    if not slow.runs:
        return f"\n### Slow tests: none here\n\nThe `slow-tests` job does not run: {slow.reason}.\n"
    listing = "\n".join(f"- `{test}`" for test in slow.test_files) or "- every testpath"
    left = "\n".join(f"- `{node}`: {why}" for node, why in ci_slow_tests.LEFT_TO_VALIDATE_DEV.items())
    chromium = " It installs Playwright's Chromium first." if slow.chromium else ""
    return (
        "\n### Slow tests: the `slow-tests` job runs them\n\n"
        f"With validate-dev's markers, because {slow.reason}.{chromium}\n\n{listing}\n\n"
        f"Left to validate-dev's slow tier:\n\n{left}\n"
    )


def in_parts(choice: Choice) -> str:
    parts = len(parts_of(choice))
    return f"in {parts} part{'s' if parts > 1 else ''}"


def commit_exists(root: Path, revision: str) -> bool:
    completed = subprocess.run(
        ["git", "cat-file", "-e", f"{revision}^{{commit}}"], cwd=root, capture_output=True, check=False
    )
    return completed.returncode == 0


def summary(
    choice: Choice, deal: ci_test_durations.Deal | None = None, slow: SlowChoice | None = None
) -> str:
    dealt = "" if deal is None else f"\n{ci_test_durations.summary(deal)}"
    return chosen_summary(choice) + dealt + ("" if slow is None else slow_summary(slow))


def chosen_summary(choice: Choice) -> str:
    if not choice.runs_parts:
        return (
            "### Tests: none\n\n"
            f"No test part runs, because {choice.reason}. spec-validate still checks every document's "
            "links and descriptions.\n"
        )
    if choice.tests is None:
        return (
            "### Tests: the whole default selection\n\n"
            f"It runs {in_parts(choice)}, each its share of every test file, because {choice.reason}.\n"
        )
    listing = "\n".join(f"- `{test}`" for test in choice.tests)
    return (
        "### Tests: the affected set\n\n"
        f"{len(choice.tests)} of {choice.total} test files, {in_parts(choice)}: {choice.reason}. "
        f"Every part runs its share of them (one part per {TEST_FILES_PER_PART} test files, "
        f"at most {MOST_PARTS}).\n\n"
        f"<details><summary>The {len(choice.tests)} test files</summary>\n\n{listing}\n\n</details>\n"
    )


def github_outputs(
    choice: Choice, deal: ci_test_durations.Deal | None = None, slow: SlowChoice | None = None
) -> str:
    """The choice in `$GITHUB_OUTPUT`'s format: `run_parts`, whether the test parts run at all,
    `parts`, the matrix's part numbers as JSON, `files_to_parts`, the deal of whole files to parts
    (empty: test by test), and `test_files`, one test file per line, which is empty for the whole
    default selection. For the `slow-tests` job (v1-e41-t29): `run_slow`, whether it runs,
    `slow_chromium`, whether it installs Playwright's Chromium, and `slow_test_files`, the files it
    is handed, one per line (empty: every testpath)."""
    slow = slow or SlowChoice(False, (), "not chosen")
    delimiter = f"test_files_{uuid.uuid4().hex}"
    listing = "".join(f"{test}\n" for test in choice.tests or ())
    slow_listing = "".join(f"{test}\n" for test in slow.test_files)
    run_parts = "true" if choice.runs_parts else "false"
    parts = json.dumps(parts_of(choice))
    return (
        f"run_parts={run_parts}\nparts={parts}\n"
        f"files_to_parts={'' if deal is None else ci_test_durations.as_output(deal)}\n"
        f"test_files<<{delimiter}\n{listing}{delimiter}\n"
        f"run_slow={'true' if slow.runs else 'false'}\n"
        f"slow_chromium={'true' if slow.chromium else 'false'}\n"
        f"slow_test_files<<{delimiter}\n{slow_listing}{delimiter}\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--event", required=True, help="github.event_name")
    parser.add_argument("--base-branch", default="", help="github.base_ref: a pull request's target")
    parser.add_argument("--base-sha", default="", help="github.event.pull_request.base.sha")
    parser.add_argument("--ref-name", default="", help="github.ref_name: the branch a push went to")
    parser.add_argument(
        "--outputs", type=Path, required=True, help="where to write the choice, in $GITHUB_OUTPUT's format"
    )
    parser.add_argument("--summary", type=Path, help="a Markdown file to append the summary to")
    parser.add_argument(
        "--durations",
        type=Path,
        help="the test durations dev's push run recorded, as test-selection restored them; may be missing",
    )
    arguments = parser.parse_args(argv)

    root = affected_tests.repository_root()
    choice = choose(root, arguments.event, arguments.base_branch, arguments.base_sha, arguments.ref_name)
    deal = dealing(root, choice, arguments.durations, datetime.now(UTC))
    slow = slow_choice(root, choice, arguments.event, arguments.base_branch)
    text = summary(choice, deal, slow)
    print(text)
    if arguments.summary is not None:
        with arguments.summary.open("a", encoding="utf-8") as file:
            file.write(text)
    arguments.outputs.write_text(github_outputs(choice, deal, slow), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

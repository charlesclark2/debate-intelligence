"""Write the test files one `test` part of ci.yml runs, and say why in the job summary (v1-e01-t38).

A pull request into dev runs the tests its changes reach: `scripts/affected_tests.py`'s selection
(v1-e01-t28), read against the pull request's base commit, with its always-run list and its
whole-selection rule for shared test ground. Every other run is the whole default selection:

* a pull request into main, which is a promotion;
* a push to dev or main, which is the record that the merged result is green, and which the dev
  pre-release waits for;
* a dispatched run, and any other event;
* and, on a pull request into dev, a selection that names the whole selection, a base commit that
  is not in the checkout, a selection that fails, or one that comes back empty.

It fails toward more tests, never fewer. The output file holds one test file per line, for pytest
to read as `@FILE`. For the whole selection it is empty: pytest given no paths runs every path in
`testpaths`, which is exactly the command the parts ran before this task. If this script itself
cannot run, the workflow step empties the file, so a crash here is also the whole selection.

Each part runs this for itself and deals the same list round the parts (run_in_parts.py), so the
parts together are exactly the selection; tests/scripts/test_ci_workflow_test_job.py proves it.
Nothing here reads a secret or uses the network: the base commit comes with the checkout.

Usage, as ci.yml's `test` job runs it:
  python scripts/ci_test_selection.py --event pull_request --base-branch dev --base-sha SHA \\
      --ref-name 123/merge --output selection.txt --summary "$GITHUB_STEP_SUMMARY"
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

import affected_tests

# The one target branch whose pull requests run only the tests their changes reach.
AFFECTED_SET_BRANCH = "dev"


@dataclass(frozen=True)
class Choice:
    """The test files to run, or None for the whole default selection, and why."""

    tests: tuple[str, ...] | None
    reason: str
    total: int = 0


def whole(reason: str) -> Choice:
    return Choice(None, reason)


def choose(root: Path, event: str, base_branch: str, base_sha: str, ref_name: str) -> Choice:
    if event == "push":
        return whole(f"a push to {ref_name or 'a branch'} runs the whole selection")
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


def commit_exists(root: Path, revision: str) -> bool:
    completed = subprocess.run(
        ["git", "cat-file", "-e", f"{revision}^{{commit}}"], cwd=root, capture_output=True, check=False
    )
    return completed.returncode == 0


def summary(choice: Choice) -> str:
    if choice.tests is None:
        return (
            "### Tests: the whole default selection\n\n"
            f"Every part runs its share of every test file, because {choice.reason}.\n"
        )
    listing = "\n".join(f"- `{test}`" for test in choice.tests)
    return (
        "### Tests: the affected set\n\n"
        f"{len(choice.tests)} of {choice.total} test files: {choice.reason}. "
        "Every part runs its share of them.\n\n"
        f"<details><summary>The {len(choice.tests)} test files</summary>\n\n{listing}\n\n</details>\n"
    )


def github_outputs(choice: Choice) -> str:
    """The choice in `$GITHUB_OUTPUT`'s format: `run_parts`, whether the test parts run at all, and
    `test_files`, one test file per line, which is empty for the whole default selection."""
    delimiter = f"test_files_{uuid.uuid4().hex}"
    listing = "".join(f"{test}\n" for test in choice.tests or ())
    return f"run_parts=true\ntest_files<<{delimiter}\n{listing}{delimiter}\n"


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
    arguments = parser.parse_args(argv)

    root = affected_tests.repository_root()
    choice = choose(root, arguments.event, arguments.base_branch, arguments.base_sha, arguments.ref_name)
    text = summary(choice)
    print(text)
    if arguments.summary is not None:
        with arguments.summary.open("a", encoding="utf-8") as file:
            file.write(text)
    arguments.outputs.write_text(github_outputs(choice), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

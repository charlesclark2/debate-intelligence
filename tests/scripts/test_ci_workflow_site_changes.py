"""What ci.yml does with a change to site/ (v1-e36-t12).

Two things, each a mistake that would be silent until after a merge:

* A pull request into main that touches site/ runs the site's PROD build and the export checks
  against it, the command validate-dev's site lane runs. Before this, a `hotfix/*` change to site/
  was built only for dev, where the publishing-policy and consent guards print and carry on, and
  its first prod build was `scripts/site_deploy.sh` after the merge. The prod build runs in ci's
  `site` job, which is one of the `ci` check's needs, and `ci` is what protect-main requires, so
  no ruleset changes.
* A change only under site/ selects no Python tests, while a change under scripts/ (site_deploy.sh,
  site_smoke.py, check_promotion_source.py among it) still does. Before this, ci's python filter
  held `'**/*.md'`, so a page edit into main ran the whole Python selection.

The site job is run here as the runner runs it: each `run:` step whose `if:` holds for the event,
with bash, in a throwaway checkout holding the real site/scripts/*.sh, against stub `pnpm` and
`node` commands that log what they were asked and with which SITE_ENV. The `node` stub stands in
for `next build`'s publishing-policy guard on one rule, a `[[TBD]]` marker, which is fatal in a
prod build and printed in a dev one; the session report shows the real build doing that.

The path filters are evaluated the way dorny/paths-filter does, for the subset of picomatch the
filters use (a test below fails on any pattern outside it), and the `changes` job's outputs are
evaluated from them. Nothing here reaches GitHub or the network.
"""

from __future__ import annotations

import functools
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
VALIDATE_DEV_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "validate-dev.yml"

STUB_LOG_LINE = 'printf \'%s %s\\n\' "$(basename "$0")" "$*" >> "$STUB_LOG"\n'

PULL_REQUEST_INTO_MAIN = {"github.event_name": "pull_request", "github.base_ref": "main"}
PULL_REQUEST_INTO_DEV = {"github.event_name": "pull_request", "github.base_ref": "dev"}
PUSH = {"github.event_name": "push", "github.base_ref": ""}
DISPATCH = {"github.event_name": "workflow_dispatch", "github.base_ref": ""}

# What a page looks like with a fact still to be supplied.
PLANTED_PAGE = "---\ntitle: Results\n---\n\nThe [[TBD]] results summary.\n"
CLEAN_PAGE = "---\ntitle: Results\n---\n\nThe results summary.\n"


@functools.cache
def ci_jobs() -> dict[str, Any]:
    return yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))["jobs"]


def tracked(*pathspecs: str) -> list[str]:
    listing = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "-z", "--", *pathspecs], capture_output=True, check=True
    ).stdout
    return [name for name in listing.decode().split("\0") if name]


# --------------------------------------------------------------------------------------------
# workflow expressions: `name == 'literal'` and `name != 'literal'`, joined by && and ||
# --------------------------------------------------------------------------------------------

TERM = re.compile(r"\s*([\w.-]+)\s*(==|!=)\s*'([^']*)'\s*")


def holds(expression: str, context: Mapping[str, str]) -> bool:
    """A workflow expression as GitHub evaluates it, for the forms ci.yml's site and changes jobs use.

    && binds tighter than ||. Anything else (a function call, parentheses, a name the context does
    not give) raises, so a condition this cannot read fails the test instead of being guessed at.
    """
    text = expression.strip()
    if text.startswith("${{") and text.endswith("}}"):
        text = text[3:-2]
    return any(all(term_holds(term, context) for term in either.split("&&")) for either in text.split("||"))


def term_holds(term: str, context: Mapping[str, str]) -> bool:
    match = TERM.fullmatch(term)
    if match is None:
        raise ValueError(f"not an expression this test reads: {term!r}")
    name, operator, literal = match.groups()
    return (context[name] == literal) == (operator == "==")


# --------------------------------------------------------------------------------------------
# the site job, run with stub pnpm and node
# --------------------------------------------------------------------------------------------

# Logs its arguments with the build settings, and stands in for the publishing-policy guard on one
# rule: a [[TBD]] in a page fails a prod build and is printed by any other.
NODE_STUB = """
printf '  SITE_ENV=%s SITE_URL=%s\\n' "${SITE_ENV-}" "${SITE_URL-}" >> "$STUB_LOG"
if grep -rq '\\[\\[TBD' site/content; then
  if [ "${SITE_ENV-}" = prod ]; then
    echo "Error [PublishingPolicyError]: Content breaks docs/policies/website-publishing.md" >&2
    exit 1
  fi
  echo "Publishing policy problems, which will fail a prod build:" >&2
fi
"""


def write_stub(directory: Path, name: str, body: str) -> None:
    path = directory / name
    path.write_text("#!/usr/bin/env bash\n" + STUB_LOG_LINE + body, encoding="utf-8")
    path.chmod(0o755)


def site_checkout(tmp_path: Path, page: str) -> Path:
    """A checkout holding the real site/scripts, an installed site/ and one page."""
    root = tmp_path / "checkout"
    (root / "site" / "scripts").mkdir(parents=True)
    for script in ("pre-commit-checks.sh", "export-checks.sh"):
        shutil.copy2(REPO_ROOT / "site" / "scripts" / script, root / "site" / "scripts" / script)
    (root / "site" / "node_modules").mkdir()
    (root / "site" / "content" / "pages").mkdir(parents=True)
    (root / "site" / "content" / "pages" / "results.md").write_text(page, encoding="utf-8")
    return root


def run_site_job(tmp_path: Path, page: str, context: Mapping[str, str]) -> tuple[bool, str]:
    """Every `run:` step of the site job whose `if:` holds, in order, stopping at the first failure.

    Returns whether the job passed and what pnpm and node were asked to do. The `uses:` steps
    (checkout, pnpm and Node setup) are the runner's, and are not run.
    """
    root = site_checkout(tmp_path, page)
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    write_stub(stubs, "pnpm", "")
    write_stub(stubs, "node", NODE_STUB)
    log = tmp_path / "stub.log"
    log.touch()
    for step in ci_jobs()["site"]["steps"]:
        if "run" not in step or ("if" in step and not holds(step["if"], context)):
            continue
        result = subprocess.run(
            ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", step["run"]],
            cwd=root,
            env={
                "PATH": f"{stubs}{os.pathsep}{os.environ['PATH']}",
                "HOME": str(tmp_path),
                "STUB_LOG": str(log),
                **{name: str(value) for name, value in step.get("env", {}).items()},
            },
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if result.returncode != 0:
            return False, log.read_text(encoding="utf-8")
    return True, log.read_text(encoding="utf-8")


def builds(log: str) -> list[str]:
    """The settings of each build the job ran, in order."""
    lines = log.splitlines()
    return [
        lines[index + 1].strip()
        for index, line in enumerate(lines)
        if line.startswith("node ") and line.endswith("build-export.mjs")
    ]


PROD_BUILD = "SITE_ENV=prod SITE_URL=https://wfbdebate.com"
DEV_BUILD = "SITE_ENV=dev SITE_URL="


def test_a_planted_tbd_fails_the_site_job_on_a_pull_request_into_main(tmp_path: Path) -> None:
    passed, log = run_site_job(tmp_path, PLANTED_PAGE, PULL_REQUEST_INTO_MAIN)
    assert not passed
    assert builds(log) == [DEV_BUILD, PROD_BUILD]


def test_a_clean_page_passes_the_dev_build_then_the_prod_build_and_its_export_checks(tmp_path: Path) -> None:
    passed, log = run_site_job(tmp_path, CLEAN_PAGE, PULL_REQUEST_INTO_MAIN)
    assert passed
    assert builds(log) == [DEV_BUILD, PROD_BUILD]
    # The export checks run against each build, the prod one last.
    last = log.splitlines()[-1]
    assert last.startswith("pnpm --dir ")
    assert last.endswith("/site exec vitest run --config tests/export/vitest.config.ts")


def test_a_pull_request_into_dev_is_still_built_for_dev_only(tmp_path: Path) -> None:
    """dev's pull requests keep the dev build, whose guards print: the site lane and promotions
    are where a page meets prod, and a draft page on dev is allowed its [[TBD]]."""
    passed, log = run_site_job(tmp_path, PLANTED_PAGE, PULL_REQUEST_INTO_DEV)
    assert passed
    assert builds(log) == [DEV_BUILD]


def test_the_prod_build_is_the_one_validate_dev_runs_for_the_site_lane() -> None:
    [prod] = [step for step in ci_jobs()["site"]["steps"] if step.get("env", {}).get("SITE_ENV") == "prod"]
    lane = yaml.safe_load(VALIDATE_DEV_WORKFLOW.read_text(encoding="utf-8"))["jobs"]["site"]
    [lane_prod] = [step for step in lane["steps"] if step.get("env", {}).get("SITE_ENV") == "prod"]
    assert prod["env"] == lane_prod["env"] == {"SITE_ENV": "prod", "SITE_URL": "https://wfbdebate.com"}
    assert prod["run"] == lane_prod["run"] == "site/scripts/export-checks.sh"
    # Any pull request into main: a promotion, a hotfix/* or a site/<slug> head alike.
    assert prod["if"] == "github.base_ref == 'main'"


def test_the_site_job_gates_the_required_ci_check_so_no_ruleset_changes() -> None:
    jobs = ci_jobs()
    assert "site" in jobs["ci"]["needs"]
    assert jobs["site"]["if"] == "needs.changes.outputs.site == 'true'"
    filter_of_job = yaml.safe_load(jobs["ci"]["steps"][0]["env"]["PATH_FILTER_OF_JOB"])
    assert filter_of_job["site"] == "site"


def test_no_workflow_step_here_holds_a_secret_or_an_aws_credential() -> None:
    text = CI_WORKFLOW.read_text(encoding="utf-8")
    assert "secrets." not in text
    assert not re.search(r"AWS_|aws-actions/|id-token", text)


# --------------------------------------------------------------------------------------------
# the path filters, evaluated as dorny/paths-filter evaluates them
# --------------------------------------------------------------------------------------------

# The picomatch this test reads: literal characters, `*` within one path segment, `**` as a whole
# segment, and a leading `!`. Every pattern in ci.yml's filters has to be one of these.
SEGMENT = r"(?:\*\*|[\w.-]*\*?[\w.-]*)"
SUPPORTED_PATTERN = re.compile(rf"!?(?:{SEGMENT}/)*{SEGMENT}")


@functools.cache
def pattern_regex(pattern: str) -> re.Pattern[str]:
    """A picomatch pattern, with dorny's `dot: true`, as a regular expression over a whole path."""
    out = ""
    index = 0
    while index < len(pattern):
        if pattern.startswith("**/", index):
            out += "(?:[^/]+/)*"
            index += 3
        elif pattern.startswith("/**", index) and index + 3 == len(pattern):
            out += "(?:/.*)?"
            index += 3
        elif pattern[index] == "*":
            out += "[^/]*"
            index += 1
        else:
            out += re.escape(pattern[index])
            index += 1
    return re.compile(out)


def matches(pattern: str, path: str) -> bool:
    if pattern.startswith("!"):
        return pattern_regex(pattern[1:]).fullmatch(path) is None
    return pattern_regex(pattern).fullmatch(path) is not None


def flatten(patterns: Iterable[Any]) -> list[str]:
    """A filter's patterns, with the lists a YAML alias brings in spread out, as dorny does."""
    out: list[str] = []
    for pattern in patterns:
        out.extend(flatten(pattern) if isinstance(pattern, list) else [pattern])
    return out


@functools.cache
def filters(text: str) -> dict[str, list[str]]:
    """A paths-filter step's `filters:` block, each filter's patterns flattened."""
    return {name: flatten(patterns) for name, patterns in yaml.safe_load(text).items()}


def filter_steps() -> list[dict[str, Any]]:
    return [
        step
        for step in ci_jobs()["changes"]["steps"]
        if step.get("uses", "").startswith("dorny/paths-filter@")
    ]


def changes_outputs(changed: Iterable[str], context: Mapping[str, str]) -> dict[str, str]:
    """The `changes` job's outputs for a run whose changed files are `changed`."""
    files = list(changed)
    values = dict(context)
    for step in filter_steps():
        ran = holds(step["if"], context) if "if" in step else True
        quantifier = step["with"].get("predicate-quantifier", "some")
        combine = all if quantifier == "every" else any
        for name, patterns in filters(step["with"]["filters"]).items():
            found = any(combine(matches(p, path) for p in patterns) for path in files)
            # A skipped step's outputs read as the empty string.
            values[f"steps.{step['id']}.outputs.{name}"] = ("true" if found else "false") if ran else ""
    return {
        name: "true" if holds(expression, values) else "false"
        for name, expression in ci_jobs()["changes"]["outputs"].items()
    }


SITE_FILES = tracked("site/")
SITE_SCRIPTS = ["scripts/site_deploy.sh", "scripts/site_smoke.py", "scripts/check_promotion_source.py"]
MARKDOWN_OUTSIDE_SITE = [path for path in tracked("*.md") if not path.startswith("site/")]


def test_every_pattern_in_the_filters_is_one_this_test_reads_as_dorny_does() -> None:
    steps = filter_steps()
    assert steps
    for step in steps:
        assert set(step["with"]) <= {"filters", "predicate-quantifier"}
        assert step["with"].get("predicate-quantifier", "some") in {"some", "every"}
        for patterns in filters(step["with"]["filters"]).values():
            for pattern in patterns:
                assert SUPPORTED_PATTERN.fullmatch(pattern), pattern


@pytest.mark.parametrize(
    ("pattern", "path", "expected"),
    [
        ("**/*.md", "README.md", True),
        ("**/*.md", "docs/process/working-agreements.md", True),
        ("**/*.md", ".github/PULL_REQUEST_TEMPLATE/site.md", True),
        ("**/*.md", "docs/README.mdx", False),
        ("packages/**", "packages/debate_core/src/x.py", True),
        ("packages/**", "site/packages/x.py", False),
        ("scripts/**", "site/scripts/export-checks.sh", False),
        ("!site/**", "site/content/pages/home.md", False),
        ("!site/**", "sites/home.md", True),
        ("conftest.py", "tests/conftest.py", False),
    ],
)
def test_the_patterns_match_as_picomatch_matches_them(pattern: str, path: str, expected: bool) -> None:
    assert matches(pattern, path) is expected


@pytest.mark.parametrize(
    "context", [PULL_REQUEST_INTO_DEV, PULL_REQUEST_INTO_MAIN], ids=["into-dev", "into-main"]
)
def test_a_change_only_under_site_selects_no_python_tests_and_runs_the_site_job(
    context: dict[str, str],
) -> None:
    assert len(SITE_FILES) > 100
    new_page = "site/content/pages/new-page.md"
    outputs = changes_outputs([*SITE_FILES, new_page], context)
    assert outputs["python"] == "false"
    assert outputs["site"] == "true"
    for path in [*SITE_FILES, new_page]:
        assert changes_outputs([path], context)["python"] == "false", path


@pytest.mark.parametrize("path", SITE_SCRIPTS)
def test_a_change_under_scripts_still_selects_the_python_tests(path: str) -> None:
    assert (REPO_ROOT / path).is_file()
    assert changes_outputs([path], PULL_REQUEST_INTO_MAIN)["python"] == "true"
    assert (
        changes_outputs([path, "site/content/pages/results.md"], PULL_REQUEST_INTO_MAIN)["python"] == "true"
    )


def test_every_markdown_file_outside_site_still_selects_the_python_tests() -> None:
    """tests/docs and tests/architecture read them; leaving site/ out must not leave these out."""
    assert len(MARKDOWN_OUTSIDE_SITE) > 100
    for path in [*MARKDOWN_OUTSIDE_SITE, "a-new-top-level-folder/notes.md", "NEW.md"]:
        assert changes_outputs([path], PULL_REQUEST_INTO_DEV)["python"] == "true", path


@pytest.mark.parametrize("context", [PUSH, DISPATCH], ids=["push", "dispatch"])
def test_a_push_or_a_dispatch_still_runs_everything(context: dict[str, str]) -> None:
    outputs = changes_outputs(["site/content/pages/results.md"], context)
    assert set(outputs.values()) == {"true"}


def test_site_markdown_still_has_its_links_checked_on_every_pull_request() -> None:
    """site/README.md links into docs/ and to its own headings. With site/ out of the python filter,
    the pytest that checks every tracked Markdown file's links no longer runs for a site-only
    change, so the same script runs in spec-validate, which has no path filter."""
    spec_validate = ci_jobs()["spec-validate"]
    assert "if" not in spec_validate
    assert "spec-validate" in ci_jobs()["ci"]["needs"]
    [step] = [step for step in spec_validate["steps"] if "scripts/check_links.py" in step.get("run", "")]
    assert "if" not in step
    assert step["run"] == "uv run --frozen python scripts/check_links.py"
    listed = subprocess.run(
        [sys.executable, "scripts/check_links.py", "--list"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=True,
        text=True,
    ).stdout.split()
    assert "site/README.md" in listed

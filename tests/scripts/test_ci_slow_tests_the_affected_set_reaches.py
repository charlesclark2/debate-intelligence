"""A pull request's ci runs the slow tests its affected set reaches (v1-e41-t29).

`v1-e08-t24`'s ranking change broke `tests/integration/test_e2e_research.py`, which its affected set
had chosen; the `test` parts run `not slow`, so only validate-dev's slow tier on dev ran it, and dev
was red for a day. The PM's rulings of 2026-11-13: ci.yml's `slow-tests` job, beside the parts, on a
pull request into dev, runs the slow tests of the chosen files with validate-dev's slow-tier markers,
less four tests left to validate-dev, and a skip fails it. These tests hold:

* the four tests left to validate-dev, written here by hand, so a new one is a reviewed change, and
  each is a slow test pytest collects;
* the text check that hands the job its files finds every file pytest collects a slow test from;
* when the job runs (a pull request into dev only), which files it is handed, and when it installs
  Chromium;
* its place in ci.yml: beside the parts, one of `ci`'s needs, its skip accepted only on `run_slow`;
* the replay of v1-e08-t24's merge: its changes reach the e2e test it broke, and the job is handed it;
* a planted break that only a slow test sees: the parts' markers run none of the e2e file, and the
  slow job's command fails at the test's assertion;
* `affected_tests.py --run --slow`, and validate-dev's tiers printing their 25 slowest tests.

Nothing here reaches the network; the planted break lives in a plugin under `tmp_path`.
"""

from __future__ import annotations

import subprocess
import sys
import xml.etree.ElementTree as ElementTree
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import affected_tests  # noqa: E402
import ci_slow_tests  # noqa: E402
import ci_test_selection  # noqa: E402
import validate_dev  # noqa: E402

WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
SLOW_JOB = "slow-tests"
SELECTION_JOB = "test-selection"
#: The parts' markers, as ci.yml's `test` step spells them.
PARTS_MARKERS = "not slow and not live and not partition_proof"
E2E_RESEARCH = "tests/integration/test_e2e_research.py"
CHROMIUM_FILE = "packages/debate_api/tests/browser/test_search_pages_in_chromium.py"
PLANTED_BREAKS = "tests/scripts/test_affected_tests_planted_breaks.py"
A_FAST_TEST_FILE = "tests/scripts/test_hard_stop.py"

#: The PM's ruling of 2026-11-13, by hand: the tests a pull request leaves to validate-dev's slow tier.
RULED_LEFT_TO_VALIDATE_DEV = {
    PLANTED_BREAKS,
    "packages/debate_core/tests/evidence/test_docx_renderer.py::"
    "test_libreoffice_opens_a_rendered_document_headless_and_reads_every_paragraph",
    "packages/debate_core/tests/integrations/local/test_search_index_sqlite_features.py::"
    "test_search_index_opens_in_the_lambda_image_sqlite",
    "packages/debate_core/tests/integrations/local/test_search_index_reader_sqlite_features.py::"
    "test_search_index_reader_statements_run_in_the_lambda_image_sqlite",
}

#: v1-e08-t24's merge, 982cc154, as `git show --stat` lists it: the changes replayed below.
T24_CHANGES = (
    "config/federated_ranking.yaml",
    "docs/data/federated-ranking-labelled-searches.md",
    "docs/session-reports/v1-e08-t24-the-ranking-keeps-a-multi-query-searchs-relevant-results-up.md",
    "packages/debate_cli/tests/test_search_command.py",
    "packages/debate_core/src/debate_core/application/federated_ranking.py",
    "packages/debate_core/src/debate_core/application/federated_ranking_features.py",
    "packages/debate_core/tests/application/test_federated_ranking.py",
    "plan_specs/v1/e08-research-workflows/t24-the-ranking-keeps-a-multi-query-searchs-relevant-results-up.yaml",
)

#: A break only the e2e tests can see: the end-to-end harness's Crossref says it has no record of the
#: journal article's DOI, so its card is cut UNVERIFIED (`CITATION_UNVERIFIED`) and the search ends
#: SHORT, two VERIFIED cards of three. Only the three slow e2e files import the harness.
PLANT_MODULE = "planted_crossref_has_no_record_of_the_journal"
PLANT = (
    "from tests.fixtures.citation.citation_world import JOURNAL_DOI\n"
    "from tests.integration import e2e_harness\n\n"
    "e2e_harness.Boundaries.__post_init__ = lambda self: self.crossref.answer(JOURNAL_DOI, 404)\n"
)


def jobs() -> dict[str, Any]:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]


def collected(*arguments: str) -> list[str]:
    """The node ids pytest collects under validate-dev's slow markers, in one process, nothing run."""
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-n", "0", "-p", "no:cacheprovider"]
        + ["-m", validate_dev.SLOW.marker_expression, *arguments],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=100,
        check=False,
    )
    assert completed.returncode in (0, 5), completed.stdout + completed.stderr
    return [line for line in completed.stdout.splitlines() if "::" in line]


# --------------------------------------------------------------------------------------------
# The four tests left to validate-dev
# --------------------------------------------------------------------------------------------


def test_the_tests_left_to_validate_dev_are_the_four_the_pm_ruled_each_with_its_reason() -> None:
    assert set(ci_slow_tests.LEFT_TO_VALIDATE_DEV) == RULED_LEFT_TO_VALIDATE_DEV
    for node, reason in ci_slow_tests.LEFT_TO_VALIDATE_DEV.items():
        assert len(reason.split()) >= 5, (node, reason)


def test_each_test_left_to_validate_dev_is_a_slow_test_pytest_collects() -> None:
    files = sorted({node.partition("::")[0] for node in RULED_LEFT_TO_VALIDATE_DEV})
    nodes = collected(*files)
    for left in RULED_LEFT_TO_VALIDATE_DEV:
        if "::" in left:
            assert left in nodes, f"{left} is not a slow test pytest collects: {nodes}"
        else:
            assert any(node.startswith(f"{left}::") for node in nodes), f"{left} holds no slow test"


def test_the_slow_run_has_validate_devs_markers_and_deselects_exactly_the_four(tmp_path: Path) -> None:
    junit = tmp_path / "slow.xml"
    arguments = ci_slow_tests.pytest_arguments([E2E_RESEARCH], junit)
    assert arguments[arguments.index("-m") + 1] == validate_dev.SLOW.marker_expression
    deselected = {
        argument.removeprefix("--deselect=") for argument in arguments if argument.startswith("--deselect=")
    }
    assert deselected == RULED_LEFT_TO_VALIDATE_DEV
    assert f"--junitxml={junit}" in arguments
    assert "--durations=25" in arguments
    assert arguments[-1] == E2E_RESEARCH


# --------------------------------------------------------------------------------------------
# The text check that hands the job its files
# --------------------------------------------------------------------------------------------


def a_tree(root: Path, files: dict[str, str]) -> Path:
    for path, text in files.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(text, encoding="utf-8")
    return root


MARKED = f"import pytest\n\n\n@pytest.{ci_slow_tests.SLOW_MARK}\ndef test_it():\n    pass\n"
PLAIN = "def test_it():\n    pass\n"


def test_a_file_naming_the_slow_marker_may_hold_slow_tests_and_one_that_does_not_cannot(
    tmp_path: Path,
) -> None:
    root = a_tree(tmp_path, {"tests/a/test_marked.py": MARKED, "tests/a/test_plain.py": PLAIN})
    assert ci_slow_tests.may_hold_slow_tests(root, "tests/a/test_marked.py")
    assert not ci_slow_tests.may_hold_slow_tests(root, "tests/a/test_plain.py")


@pytest.mark.parametrize("conftest", ["tests/a/b/conftest.py", "tests/conftest.py", "conftest.py"])
def test_a_conftest_above_a_file_naming_the_slow_marker_may_give_it_slow_tests(
    tmp_path: Path, conftest: str
) -> None:
    root = a_tree(tmp_path, {"tests/a/b/test_plain.py": PLAIN, conftest: MARKED})
    assert ci_slow_tests.may_hold_slow_tests(root, "tests/a/b/test_plain.py")


def test_a_conftest_beside_another_folder_gives_a_file_no_slow_tests(tmp_path: Path) -> None:
    root = a_tree(tmp_path, {"tests/a/test_plain.py": PLAIN, "tests/b/conftest.py": MARKED})
    assert not ci_slow_tests.may_hold_slow_tests(root, "tests/a/test_plain.py")


def test_a_file_left_to_validate_dev_whole_is_never_handed_to_the_job() -> None:
    assert ci_slow_tests.may_hold_slow_tests(REPO_ROOT, E2E_RESEARCH)
    assert not ci_slow_tests.may_hold_slow_tests(REPO_ROOT, PLANTED_BREAKS)


def test_no_plugin_and_no_root_conftest_names_the_slow_marker() -> None:
    """pytest marks a test from its file, a conftest above it, or a plugin: the text check reads the
    first two, so no plugin and no root conftest may mark one. pyproject.toml only deselects them."""
    for path in [REPO_ROOT / "conftest.py", *sorted((REPO_ROOT / "tests" / "pytest_plugins").glob("*.py"))]:
        if path.exists():
            assert "slow" not in path.read_text(encoding="utf-8"), path


def test_every_file_pytest_collects_a_slow_test_from_is_one_the_text_check_finds() -> None:
    """Every test file, or a conftest above it, that holds the word, is collected under the slow
    markers; each file a slow test comes from is one the check finds, or one left to validate-dev."""
    layout = affected_tests.Layout.of(affected_tests.Tree.working(REPO_ROOT))
    holding_the_word = sorted(
        test
        for test in layout.test_files
        if any(
            "slow" in candidate.read_text(encoding="utf-8")
            for candidate in [
                REPO_ROOT / test,
                *(REPO_ROOT / folder / "conftest.py" for folder in Path(test).parents),
            ]
            if candidate.exists()
        )
    )
    files = {node.partition("::")[0] for node in collected(*holding_the_word)}
    assert E2E_RESEARCH in files and CHROMIUM_FILE in files, files
    for test in files:
        assert ci_slow_tests.may_hold_slow_tests(REPO_ROOT, test) or test in RULED_LEFT_TO_VALIDATE_DEV, test


# --------------------------------------------------------------------------------------------
# When the job runs, and what it is handed
# --------------------------------------------------------------------------------------------


def chosen(*tests: str) -> ci_test_selection.Choice:
    return ci_test_selection.Choice(tuple(sorted(tests)), "the tests a change reaches", 700)


@pytest.mark.parametrize(
    ("event", "base_branch"),
    [("push", ""), ("pull_request", "main"), ("workflow_dispatch", ""), ("schedule", "")],
)
def test_only_a_pull_request_into_dev_runs_the_slow_tests_in_ci(event: str, base_branch: str) -> None:
    slow = ci_test_selection.slow_choice(REPO_ROOT, chosen(E2E_RESEARCH), event, base_branch)
    assert not slow.runs and not slow.chromium
    assert slow.test_files == ()


def test_no_test_part_means_no_slow_tests() -> None:
    nothing = ci_test_selection.nothing("the pull request changes only the generated files")
    assert not ci_test_selection.slow_choice(REPO_ROOT, nothing, "pull_request", "dev").runs


def test_an_affected_set_reaching_an_e2e_file_hands_the_job_that_file_and_no_fast_one() -> None:
    slow = ci_test_selection.slow_choice(
        REPO_ROOT, chosen(E2E_RESEARCH, A_FAST_TEST_FILE, PLANTED_BREAKS), "pull_request", "dev"
    )
    assert slow.runs
    assert slow.test_files == (E2E_RESEARCH,)
    assert not slow.chromium


def test_an_affected_set_reaching_only_the_planted_breaks_runs_no_slow_job() -> None:
    """Every task pull request reaches them through its own spec; they are validate-dev's alone."""
    slow = ci_test_selection.slow_choice(
        REPO_ROOT, chosen(PLANTED_BREAKS, A_FAST_TEST_FILE), "pull_request", "dev"
    )
    assert not slow.runs


def test_a_chosen_browser_file_installs_chromium() -> None:
    slow = ci_test_selection.slow_choice(
        REPO_ROOT, chosen(E2E_RESEARCH, CHROMIUM_FILE), "pull_request", "dev"
    )
    assert slow.runs and slow.chromium
    assert slow.test_files == (CHROMIUM_FILE, E2E_RESEARCH)


def test_the_whole_selection_hands_the_job_every_file_that_may_hold_a_slow_test() -> None:
    whole = ci_test_selection.whole("ci.yml is shared test ground")
    slow = ci_test_selection.slow_choice(REPO_ROOT, whole, "pull_request", "dev")
    assert slow.runs and slow.chromium
    assert {E2E_RESEARCH, CHROMIUM_FILE} <= set(slow.test_files)
    assert PLANTED_BREAKS not in slow.test_files


def test_the_outputs_say_whether_the_job_runs_whether_it_needs_chromium_and_its_files() -> None:
    choice = chosen(E2E_RESEARCH, CHROMIUM_FILE)
    slow = ci_test_selection.slow_choice(REPO_ROOT, choice, "pull_request", "dev")
    text = ci_test_selection.github_outputs(choice, None, slow)
    assert "\nrun_slow=true\n" in text and "\nslow_chromium=true\n" in text
    block = text.split("slow_test_files<<", 1)[1]
    delimiter, _, rest = block.partition("\n")
    assert rest.split(f"{delimiter}\n", 1)[0].splitlines() == [CHROMIUM_FILE, E2E_RESEARCH]
    summary = ci_test_selection.summary(choice, None, slow)
    assert "### Slow tests: the `slow-tests` job runs them" in summary
    assert all(node in summary for node in RULED_LEFT_TO_VALIDATE_DEV)


def test_no_slow_job_writes_run_slow_false_and_no_files() -> None:
    choice = chosen(A_FAST_TEST_FILE)
    slow = ci_test_selection.slow_choice(REPO_ROOT, choice, "pull_request", "dev")
    text = ci_test_selection.github_outputs(choice, None, slow)
    assert "\nrun_slow=false\n" in text and "\nslow_chromium=false\n" in text
    assert "### Slow tests: none here" in ci_test_selection.summary(choice, None, slow)


# --------------------------------------------------------------------------------------------
# Its place in ci.yml
# --------------------------------------------------------------------------------------------


def test_the_slow_tests_job_runs_beside_the_parts_on_what_test_selection_hands_it() -> None:
    every_job = jobs()
    job = every_job[SLOW_JOB]
    assert sorted(job["needs"]) == sorted(["changes", SELECTION_JOB])
    assert (
        job["if"]
        == "needs.changes.outputs.python == 'true' && needs.test-selection.outputs.run_slow == 'true'"
    )
    assert job["runs-on"] == "ubuntu-24.04" and job["timeout-minutes"] == 10
    outputs = every_job[SELECTION_JOB]["outputs"]
    for name in ("run_slow", "slow_chromium", "slow_test_files"):
        assert outputs[name] == f"${{{{ steps.choose.outputs.{name} }}}}"
    steps = job["steps"]
    chromium = next(step for step in steps if "playwright install" in step.get("run", ""))
    assert chromium["if"] == "needs.test-selection.outputs.slow_chromium == 'true'"
    written = next(step for step in steps if "SLOW_TEST_FILES" in step.get("env", {}))
    assert written["env"]["SLOW_TEST_FILES"] == "${{ needs.test-selection.outputs.slow_test_files }}"
    assert '"$RUNNER_TEMP/slow-test-files.txt"' in written["run"]
    runs = [step["run"] for step in steps if "run" in step]
    assert any(
        run.startswith(
            'uv run --frozen python scripts/ci_slow_tests.py --test-files "$RUNNER_TEMP/slow-test-files.txt"'
        )
        for run in runs
    ), runs
    assert not any(" -m " in run for run in runs), "the markers are validate_dev.SLOW's, not spelled here"
    assert "secrets." not in yaml.safe_dump(job)


def test_ci_needs_the_slow_tests_job_and_accepts_its_skip_only_when_run_slow_says_false() -> None:
    ci = jobs()["ci"]
    assert SLOW_JOB in ci["needs"]
    gates = yaml.safe_load(ci["steps"][0]["env"]["GATES_OF_JOB"])
    assert gates[SLOW_JOB] == ["changes.python", "test-selection.run_slow"]


def test_the_parts_still_run_no_slow_test() -> None:
    test_steps = [step["run"] for step in jobs()["test"]["steps"] if "pytest" in step.get("run", "")]
    assert test_steps and all(f'-m "{PARTS_MARKERS}"' in run for run in test_steps)


def test_a_failed_selection_runs_every_slow_test_on_a_pull_request_into_dev_and_none_elsewhere() -> None:
    choose = next(step for step in jobs()[SELECTION_JOB]["steps"] if step.get("id") == "choose")
    fallback = [line.strip() for line in choose["run"].split("else", 1)[1].splitlines()]
    at = fallback.index('if [ "$EVENT_NAME" = pull_request ] && [ "$BASE_BRANCH" = dev ]; then')
    assert fallback[at + 1 : at + 6] == [
        'echo "run_slow=true" >> "$GITHUB_OUTPUT"',
        'echo "slow_chromium=true" >> "$GITHUB_OUTPUT"',
        "else",
        'echo "run_slow=false" >> "$GITHUB_OUTPUT"',
        "fi",
    ]


# --------------------------------------------------------------------------------------------
# The slow run's verdict: no slow test passes, a skip fails
# --------------------------------------------------------------------------------------------


def counts(
    *, tests: int = 3, failures: int = 0, errors: int = 0, skipped: int = 0
) -> validate_dev.JUnitCounts:
    names = tuple(f"tests.x::test_{index}: no soffice" for index in range(skipped))
    return validate_dev.JUnitCounts(tests, failures, errors, skipped, names)


def test_no_slow_test_left_to_run_passes() -> None:
    assert ci_slow_tests.Outcome(5, None).problems == []


def test_every_slow_test_passing_passes() -> None:
    assert ci_slow_tests.Outcome(0, counts()).problems == []


def test_a_skip_fails_the_slow_run_as_it_fails_validate_devs_tier() -> None:
    problems = ci_slow_tests.Outcome(0, counts(skipped=1)).problems
    assert len(problems) == 1
    assert problems[0].startswith("1 skipped: a skipped check did not run, so this job fails")
    assert "LEFT_TO_VALIDATE_DEV" in problems[0] and "no soffice" in problems[0]


@pytest.mark.parametrize(
    ("exit_code", "report", "first_problem"),
    [
        (1, counts(failures=1), "pytest exited 1"),
        (1, None, "pytest wrote no JUnit report (exit 1)"),
        (2, counts(tests=0), "pytest exited 2"),
    ],
)
def test_a_failure_or_a_run_with_no_report_fails(
    exit_code: int, report: validate_dev.JUnitCounts | None, first_problem: str
) -> None:
    assert ci_slow_tests.Outcome(exit_code, report).problems[0] == first_problem


# --------------------------------------------------------------------------------------------
# The replay of v1-e08-t24's merge, and a planted break only a slow test sees
# --------------------------------------------------------------------------------------------


def test_the_replay_of_v1_e08_t24s_merge_hands_the_slow_job_the_e2e_test_it_broke(tmp_path: Path) -> None:
    """t24's eight changed files, over today's tree: the affected set reaches the e2e test that broke
    on dev (through `debate_cli.exit_codes`), and the slow job is handed it and does not deselect it."""
    changes = [affected_tests.Change(path, deleted=False) for path in T24_CHANGES]
    assert all((REPO_ROOT / path).exists() for path in T24_CHANGES)
    selection = affected_tests.select(affected_tests.Tree.working(REPO_ROOT), changes)
    assert selection.whole is None
    assert E2E_RESEARCH in selection.tests, sorted(selection.tests)
    choice = ci_test_selection.Choice(tuple(sorted(selection.tests)), "t24's merge", selection.total)
    slow = ci_test_selection.slow_choice(REPO_ROOT, choice, "pull_request", "dev")
    assert slow.runs and E2E_RESEARCH in slow.test_files
    arguments = ci_slow_tests.pytest_arguments(slow.test_files, tmp_path / "slow.xml")
    assert E2E_RESEARCH in arguments
    assert not any(E2E_RESEARCH.startswith(node) for node in RULED_LEFT_TO_VALIDATE_DEV)


def failure_texts(junit: Path) -> list[str]:
    root = ElementTree.parse(junit).getroot()
    return [
        f"{failure.get('message') or ''}\n{failure.text or ''}"
        for case in root.iter("testcase")
        for failure in case.findall("failure")
    ]


def test_a_planted_break_only_a_slow_test_sees_passes_the_parts_and_fails_the_slow_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plants = tmp_path / "plants"
    plants.mkdir()
    (plants / f"{PLANT_MODULE}.py").write_text(PLANT, encoding="utf-8")
    monkeypatch.setenv("PYTHONPATH", str(plants))

    parts = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", PLANT_MODULE, "-n", "0", "-p", "no:cacheprovider"]
        + ["-m", PARTS_MARKERS, E2E_RESEARCH],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=100,
        check=False,
    )
    assert parts.returncode == 5, parts.stdout + parts.stderr  # the parts' markers run none of it

    unplanted = ci_slow_tests.run([E2E_RESEARCH], tmp_path / "unplanted.xml", root=REPO_ROOT, workers="0")
    assert unplanted.problems == [] and unplanted.counts is not None and unplanted.counts.tests == 2

    monkeypatch.setenv("PYTEST_ADDOPTS", f"-p {PLANT_MODULE}")
    junit = tmp_path / "planted.xml"
    planted = ci_slow_tests.run([E2E_RESEARCH], junit, root=REPO_ROOT, workers="0")
    assert planted.counts is not None and planted.counts.failures == 2, planted.problems
    texts = failure_texts(junit)
    for text in texts:
        assert "AssertionError" in text, text
        assert "INTERNAL_ERROR" not in text, "a crash is not a catch"
        assert "AUTO_CUT_SHORT" in text or "SHORT: 2 of 3 cards VERIFIED" in text, text
    assert any("CITATION_UNVERIFIED" in text for text in texts), texts


# --------------------------------------------------------------------------------------------
# affected_tests.py --run --slow, and validate-dev's 25 slowest tests
# --------------------------------------------------------------------------------------------


def test_affected_tests_slow_runs_only_after_the_rest_so_it_needs_run(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit):
        affected_tests.main(["--slow"])
    assert (
        "--slow runs the selection's slow tests after the rest, so it needs --run" in capsys.readouterr().err
    )


def test_affected_tests_slow_runs_nothing_when_no_selected_file_holds_a_slow_test(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def must_not_run(*arguments: object, **keywords: object) -> ci_slow_tests.Outcome:
        raise AssertionError("no slow test to run, so pytest is not started")

    monkeypatch.setattr(ci_slow_tests, "run", must_not_run)
    assert affected_tests.run_slow_tests(REPO_ROOT, [A_FAST_TEST_FILE, PLANTED_BREAKS]) == 0


@pytest.mark.parametrize(
    ("outcome", "status"),
    [(ci_slow_tests.Outcome(0, counts()), 0), (ci_slow_tests.Outcome(0, counts(skipped=1)), 1)],
)
def test_affected_tests_slow_hands_the_slow_run_the_files_that_may_hold_one(
    monkeypatch: pytest.MonkeyPatch, outcome: ci_slow_tests.Outcome, status: int
) -> None:
    handed: list[list[str]] = []

    def recorded(test_files: list[str], junit: Path, **keywords: object) -> ci_slow_tests.Outcome:
        handed.append(list(test_files))
        return outcome

    monkeypatch.setattr(ci_slow_tests, "run", recorded)
    assert (
        affected_tests.run_slow_tests(REPO_ROOT, [A_FAST_TEST_FILE, E2E_RESEARCH, PLANTED_BREAKS]) == status
    )
    assert handed == [[E2E_RESEARCH]]


def test_validate_devs_tiers_print_their_25_slowest_tests(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    printing_its_arguments = [sys.executable, "-c", "import sys; print('ARGUMENTS', sys.argv[1:])"]
    validate_dev.run_tier(
        validate_dev.SLOW, tmp_path / "junit.xml", {}, pytest_command=printing_its_arguments, cwd=tmp_path
    )
    printed = next(line for line in capfd.readouterr().out.splitlines() if line.startswith("ARGUMENTS"))
    assert "'--durations=25'" in printed

# Session report: v1-e41-t29-a-pull-requests-ci-runs-the-slow-tests-it-reaches

| | |
|---|---|
| Task | `v1-e41-t29-a-pull-requests-ci-runs-the-slow-tests-it-reaches` — A pull request's ci runs the slow tests its affected set reaches |
| Spec | [`plan_specs/v1/e41-delivery-tooling-upkeep/t29-a-pull-requests-ci-runs-the-slow-tests-it-reaches.yaml`](../../plan_specs/v1/e41-delivery-tooling-upkeep/t29-a-pull-requests-ci-runs-the-slow-tests-it-reaches.yaml) |
| Epic / release | `v1-e41-delivery-tooling-upkeep` / `v1.8` |
| Branch | `task/v1-e41-t29-a-pull-requests-ci-runs-the-slow-tests-it-reaches` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

A pull request into `dev` now runs the slow tests its affected set reaches, as the PM ruled on
2026-11-13. `ci.yml` has a new `slow-tests` job beside the test parts. `test-selection` hands it the
chosen files that may hold a slow test (`run_slow`, `slow_chromium`, `slow_test_files`). The new
`scripts/ci_slow_tests.py` runs their slow tests with validate-dev's markers, imported from
`validate_dev.SLOW`, less four tests left to validate-dev, and a skip fails it. The job is one of
`ci`'s needs, gated on `run_slow`, so a slow failure blocks the merge; the required checks and
rulesets are unchanged. A planted break that only a slow test sees passes the parts' command over
its whole affected set (788 passed) and fails the slow job's command (3 failed, at assertions). That
is a committed test, together with the replay of v1-e08-t24's merge. Also built:
`affected_tests.py --run --slow`, `--durations=25` on validate-dev's tiers, and agreements 1 and 10
plus the costs page. **Look first at** the four ids in `LEFT_TO_VALIDATE_DEV`
(`scripts/ci_slow_tests.py`) and the reworded "Not on PRs into `dev`" item in agreement 1.

## Proposal for the PM's ruling (written before any code)

### What is true today

* **The affected set already names slow files.** `scripts/affected_tests.py` chooses test files
  and never reads markers. The parts' `-m "not slow and not live and not partition_proof"` then
  drops the slow tests. v1-e08-t24's own merge, replayed
  (`uv run scripts/affected_tests.py --diff 982cc154 --explain`), chose 286 of 743 files, among
  them `tests/integration/test_e2e_research.py`, through `debate_cli.exit_codes` →
  `federated_search_types` → `federated_ranking`. The selection would have run the test that broke.
  It just ran it under a marker that dropped it.
* **The slow tier is 60 tests in 11 files** (`--collect-only` with validate-dev's markers, this
  branch).
* **How often a PR reaches each one.** A scratch script (not committed) builds today's import graph
  once and replays the selection for each of dev's last 11 non-refresh commits. The planted-break
  file was reached by 11 of 11. The three e2e files: 7–8. The two browser files: 5. The three
  environment-gated files: 7. The scale test: 2. The structural fixture: 1. The planted-break
  file is reached by every task PR, because every task PR edits its own spec, and
  `affected_tests.py` names `plan_specs/` as a path (this branch's spec-and-report-only diff
  reaches it: "imports scripts/affected_tests.py, which has a path to plan_specs/…").

### 1. Which slow files a pull request runs

**The rule: the chosen files, run a second time with validate-dev's slow-tier markers.** The
selection itself does not change. `scripts/ci_test_selection.py` hands the same list it gives the
parts to a new job. That job runs it with `validate_dev.SLOW.marker_expression`
(`slow and not live and not eval and not operator_data`), imported rather than copied, so the
PR's slow run and validate-dev's cannot drift apart. For the whole selection (shared test ground,
a failed selection) it is every slow test, as the parts run every test: it fails toward more.

**Left to validate-dev, by node id** (`--deselect`). A constant in `ci_test_selection.py` lists
them, each with its reason, and the job summary prints them:

| Test | Why it stays on validate-dev only |
|---|---|
| `tests/scripts/test_affected_tests_planted_breaks.py::test_a_planted_break_is_caught_by_a_test_the_script_selects` (14 cases) and `::test_a_break_no_selected_test_reaches_is_not_counted_as_caught` | Reached by every task PR (11 of 11), through its spec. About 4.5 minutes of the operator's Mac in v1-e08-t26's runs (70 + 43 + 40 s for 13 cases, case 12 about 123 s alone). On a runner they are most of validate-dev's 379–453-s tier (question 2). It proves the selection against the whole repository, which is the job of validate-dev's run on each pre-release. Its fast tests still run in the parts. |
| `packages/debate_core/tests/evidence/test_docx_renderer.py::test_libreoffice_opens_a_rendered_document_headless_and_reads_every_paragraph` | Needs LibreOffice, an apt install in validate-dev's slow job. |
| `packages/debate_core/tests/integrations/local/test_search_index_sqlite_features.py::test_search_index_opens_in_the_lambda_image_sqlite` and `…/test_search_index_reader_sqlite_features.py::test_search_index_reader_statements_run_in_the_lambda_image_sqlite` | Need the arm64 Lambda base image, a docker pull run under QEMU. |

Everything else that is reached runs: the three e2e files, the two browser files, the scale test
and the structural fixture. **A skip fails the job**, as it fails validate-dev's tier. A new
environment-gated slow test then goes on the list above with its reason, rather than passing
unseen. The test that guards the list collects the three named files, so a renamed or unmarked
entry fails the list's own test.

**When the job starts.** `test-selection` sets `run_slow` to `true` only on a pull request into
`dev` whose parts run, and whose chosen files, or a conftest above one of them, contain the text
`mark.slow`. That is a cheap text check over the files already chosen, and it can only choose
more than pytest would. No plugin under `tests/pytest_plugins` and no root `conftest.py` adds the
marker (checked with grep). A test pins that, so the text check cannot miss a slow test.

### 2. Measured cost, and a bound

**Per file, on the operator's Mac** (this session, load 5–13, `-p no:cacheprovider --no-cov`):

| Slow files | Tests | Time |
|---|---|---|
| `tests/integration` (the three e2e files), `-n 0` | 11 | 6.5 s (longest 1.3 s) |
| `test_evidence_search_scale.py`, `-n 0` | 1 | 52.0 s, one test, cannot be split |
| `test_structural_fixtures.py`, `-n 0` | 1 | 2.2 s |
| `packages/debate_api/tests/browser`, xdist auto | 30 | 21.4 s (about 8.5 s of Chromium setup a worker) |
| the three environment-gated files, without their environment | 3 | 3 skipped in 0.6 s |
| **Worst realistic PR: all of the above but the gated ones, at `-n 4 --dist worksteal` like a runner part** | **43** | **51.4 s**, the scale test (43.3 s) being the critical path |

**On a CI runner, from validate-dev's own logs.** The operator ran the read-only `gh` command
under **Operator follow-ups** over validate-dev's last five runs on 2026-11-13: four green, and one
with 2 failed and 58 passed. Each run had 4 xdist workers and 60 tests.

| Slow job step | Five runs |
|---|---|
| Set up job, checkout, setup-uv, Python, `uv sync` (cached) | 8–14 s together |
| Install Playwright's Chromium (`--with-deps`) | 21, 21, 21, 24, 32 s |
| Install LibreOffice | 16–40 s |
| Set up QEMU and pull the Lambda image | 18–23 s |
| pytest, the whole tier | 379, 385, 409, 439, 453 s |

The log still cannot give per-file times. The tier runs with no `--durations`, and pytest's output
reaches the log through a pipe, so its lines carry the time they were flushed, not the time they
happened. What the totals do show: the 43 tests that would run on a PR take about 51 s on the Mac at
`-n 4`, and the costs page puts a runner's part at about a Mac's speed (about 0.09 s a test against
0.099 s at `-n 4`). So most of the runner's 379–453 s is the 15 planted-break cases, probably
330–400 s of it.

**Estimated worst case on a runner** (a debate_core search change reaching the browser files and
the scale test, about 400–760 chosen files):

* job setup (checkout, uv, Python, `uv sync`): 8–14 s, measured;
* Playwright's Chromium with its system libraries: 21–32 s, measured;
* collecting the chosen files under the slow marker: about 8–15 s;
* pytest: about 50–80 s.

That makes the job about **1.5–2.5 minutes**. The parts of such a PR are eight, at 2–3 minutes
each, so `ci`'s wall clock grows by **0–30 s** in that case. For the usual reach, the e2e files
alone, the job is under a minute, under the parts, and adds nothing. Each such PR does cost one
extra runner job.

**What the left-out tests would cost on a PR,** for the options in question 1:

* **The three environment-gated tests:** LibreOffice plus QEMU and the image is 34–63 s more setup,
  measured, before their own few seconds. With the browser files as well, the job would come to
  about 2.2–3.3 minutes, which is past the parts on a mid-sized PR.
* **The planted-break cases:** about 330–400 s on a runner. Any PR that runs them would pass the
  5-minute budget.

**The bound I recommend:** the job's pytest step at most **120 s** on a runner, and the job at
most **60 s** beyond the longest test part. The job keeps the 10-minute `timeout-minutes` every
job has. The job prints `--durations=25` like the parts, so its log names the cost. If it
drifts past the bound on ordinary PRs, the browser files move into a job of their own (Playwright
leaves the other files' path) before anything else. Then the slowest test is made cheaper. Nothing
is ever taken off validate-dev's slow tier.

### 3. Where it runs, and what a failure blocks

* **Its own job, `slow-tests`, in `ci.yml`.** It needs `changes` and `test-selection`, and starts
  when the parts do, so its time adds only past the longest part. Not in the parts: they are dealt
  whole files by duration and sized at 30 files a part. The scale test alone would hold one part
  for 50 s or more, every part would need Playwright, and the parts' markers are pinned by
  `test_ci_workflow_test_job.py`.
* **Pull requests into `dev` only.** A push to `dev` or `main`, a promotion PR into `main` and a
  dispatch do not run it. validate-dev runs the whole slow tier on every dev pre-release, and
  protect-main requires that status.
* **A failure fails `ci`**, so it blocks the merge into `dev`, as a failing part does. It goes in
  `ci`'s needs and in `GATES_OF_JOB` as `["changes.python", "test-selection.run_slow"]`, and a skip
  is accepted only when one of those said `false`.
* **validate-dev is unchanged.** No test leaves its slow tier. (Optional, see question 2(c):
  `--durations=25` added to its tiers, so the next measurement can read per-file times.)

### 4. A session's own slow-tier run

**Recommended: no session runs the whole slow tier.** Agreement 10 gains three sentences:

* while working, a session runs the slow tests of the files it changes, with `-m slow`, under
  the 115-s bound like any test;
* before the report, `uv run scripts/affected_tests.py --run --slow` runs, after the usual
  affected set, the slow tests that set reaches, minus the same left-to-validate-dev list (worst
  case 51 s locally);
* the planted-break cases are never a session's. A session that changes `affected_tests.py` or that
  file runs its fast tests, and the cases its change touches by node id, each under 115 s. Case 12
  (about 123 s) is left to validate-dev.

That is the 2026-10-19 ruling applied to this file: past two minutes it goes to CI, with no
hand-off and no longer bound.

The alternative is a 240-s bound written into agreement 10 for that one file, which keeps a
session's "run the slow tier" brief possible but makes it a 5-minute local run.

### 5. The working-agreement note on ranking changes

The words, for agreement 10, as a sub-bullet of "While working, run the tests for what you are
changing":

> * **A change that moves a fixture search's ranking** (a weight, the recency rule, a tie-break,
>   a provider's order) greps `tests/integration` for the same query or fixture, and runs what it
>   finds with `-m slow`. Those end-to-end tests pin the order and the cut of the same recorded
>   searches the CLI tests do. In `v1-e08-t24` only they saw the reorder, no pull request ran
>   them, and dev was red for a day. The pull request's `slow-tests` job now runs them when its
>   affected set reaches them (`v1-e41-t29`); the grep finds them before the push.

### What the ruling also changes in `docs/process`

* **Agreement 1 says browser end-to-end suites are "Not on PRs into `dev`"**, and `ci.yml`'s
  header says they "never run here". Running the browser files on a PR contradicts both. Those
  files are offline: every page is served in-process (the PM's ruling of 2026-10-21, v1-e39-t06
  Q1). The proposal rewords that item as "browser suites against a deployed site". The
  in-process browser files then run when a PR reaches them. If the PM would rather keep them off
  the PR path, they join the left-to-validate-dev list (question 2(b)), and the worst case drops
  to the scale test, with no Playwright install.
* Agreement 1's "What runs on every PR" and agreement 10's first bullet gain the slow tests the
  affected set reaches.
* `docs/process/ci-test-part-costs.md` gains a short section with these figures.

### How the build will be shown (after the ruling)

* **A test of the selection, committed** (`tests/scripts`, offline). It holds the
  `run_slow`/`slow_test_files` outputs for each event, the deselect list, the text check, and the
  job's shape in `ci.yml` (its markers equal to `validate_dev.SLOW`'s, its needs and gates, and
  Playwright installed only when a browser file is chosen). Its file name carries "slow" and
  "affected", so the node's `-k "slow and affected"` selects it.
* **A planted break, in a scratch clone, never pushed.** The ranking weights are changed as t24
  changed them, and `ci_test_selection.py` is run in the clone. Then the parts' command over the
  chosen files passes, and the slow job's command over the same files fails at
  `test_e2e_research.py`. Both outputs are recorded here.

### The PM's ruling (2026-11-13)

1. (a): the affected set the parts run, run again with validate-dev's slow-tier markers imported from
   `validate_dev.SLOW`; the whole selection is every slow test. Four node ids stay on validate-dev
   only, each with its reason in the job summary, pinned in a test. A skip fails the job. Not (b) or
   (c).
2. (a) the bound: pytest step at most 120 s, the job at most 60 s past the longest part; past that,
   the browser files get their own job first, then the slowest test is made cheaper, and nothing
   leaves validate-dev. (b) reword agreement 1 to "browser suites against a deployed site", with a
   sentence on why the in-process browser files differ. (c) `--durations=25` on validate-dev's tiers.
3. A separate `slow-tests` job, beside the parts, on pull requests into dev only, gated on
   `test-selection.run_slow`, one of `ci`'s needs; required checks unchanged, no ruleset change.
4. (a), written into agreement 10: no session runs the whole slow tier; the slow tests of changed
   files under 115 s, then `affected_tests.py --run --slow` before the report; the planted-break
   cases are validate-dev's alone, with no hand-off.
5. The ranking note as written, under agreement 10's "While working".

Build it, shown by a planted break that only a slow test catches, in a test of the selection, with
the replay of t24's merge kept as a test.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `a-pull-requests-ci-runs-the-slow-tests-i` (Slow tests in PR ci) | Done | Commits `4241371`, `7a52e92` (outputs pin), `a7f5c33` (docs), `4d289e1`, `73acd1a`; criterion below |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the proposal is ruled on, and a PR whose affected set reaches a slow test file runs it in ci, as ruled, shown by a planted break that only a slow test catches | PASS | Ruled 2026-11-13 (above). Built as ruled: the `slow-tests` job in `ci.yml`, `scripts/ci_slow_tests.py`, the outputs from `scripts/ci_test_selection.py`. **The replay of t24's merge**, `test_the_replay_of_v1_e08_t24s_merge_hands_the_slow_job_the_e2e_test_it_broke`: t24's eight changed files over today's tree reach `tests/integration/test_e2e_research.py`, `run_slow` is true, and the job is handed that file without deselecting it. **The planted break**, `test_a_planted_break_only_a_slow_test_sees_passes_the_parts_and_fails_the_slow_job`: the end-to-end harness's Crossref answers 404 for the journal's DOI. The parts' markers over the e2e file exit 5 (none run), the slow job's command unplanted passes 2, and planted fails 2, each at an `AssertionError` with `AUTO_CUT_SHORT` or `SHORT: 2 of 3 cards VERIFIED`, never `INTERNAL_ERROR`. **That only a slow test catches it, in this session** ([The planted break, run whole](#the-planted-break-run-whole)): the parts' command over the harness change's whole affected set, planted, gave 788 passed, exit 0, and the slow job's command over the 3 files it is handed gave 3 failed. The pull request's own runner run is the operator's (`scripts/task pr`); see Follow-up work. |
| Node: Slow tests in PR ci tests pass (`uv run pytest tests/scripts -k "slow and affected"`) | PASS | `.venv/bin/python scripts/hard_stop.py 115 uv run pytest tests/scripts -k "slow and affected"` → `39 passed in 29.67s` |

## Files changed

* **`.github/workflows/ci.yml`:** the `slow-tests` job; `test-selection`'s three new outputs and
  its fallback (a failed selection runs every slow test on a pull request into dev, none
  elsewhere); `slow-tests` in `ci`'s needs and `GATES_OF_JOB`; the header's browser wording and a
  paragraph on the job.
* **`scripts/ci_slow_tests.py` (new):** the four tests left to validate-dev with their reasons, the
  text check (`may_hold_slow_tests`), when Chromium is needed, the pytest command (validate-dev's
  markers, `--deselect` per id, `--durations=25`, JUnit), and the verdict (exit 5 passes, a skip
  fails).
* **`scripts/ci_test_selection.py`:** `slow_choice`, the `run_slow`, `slow_chromium` and
  `slow_test_files` outputs, and a "Slow tests" section in the job summary.
* **`scripts/affected_tests.py`:** `--run --slow` (`run_slow_tests`), which imports
  `ci_slow_tests` where it is used.
* **`scripts/validate_dev.py`:** `--durations=25` on every tier's command.
* **`tests/scripts/test_ci_slow_tests_the_affected_set_reaches.py` (new):** 39 tests (listed in
  its docstring).
* **`tests/scripts/test_ci_workflow_test_selection.py`, `test_ci_workflow_selection_once_and_no_queue.py`:**
  the pinned output sets gain the three slow-tests outputs.
* **`docs/process/working-agreements.md`:** agreements 1 and 10 as ruled.
* **`docs/process/ci-test-part-costs.md`:** "The slow-tests job", the figures, and its docs-index
  line.
* **The spec:** phase `Succeeded`.

## Deviations from the spec

None. No test left validate-dev's slow tier (it only gained `--durations=25`), and no test makes a
live call.

## Decisions and assumptions

* **"The planted-break cases" is one node id, the file.** `--deselect` takes a node id prefix, and in
  the slow run a file's id deselects only its slow tests, since the parts run its others. The file
  has two slow tests: the 14 parametrized cases, and `test_a_break_no_selected_test_reaches_is_not_counted_as_caught`,
  which plants a break too and clones the repository. One id covers both, so the ruling's count
  of four holds. The text check also never hands the job a file left out whole, so the many PRs
  that reach only that file start no slow job.
* **The job is handed only the chosen files that may hold a slow test**, not the whole affected
  set. The proposal said it would collect the chosen files under the slow marker (8–15 s of
  collection). The text check, `mark.slow` in the file or a conftest above it, can only say yes
  more often than pytest, and a test holds that it finds every file the slow tier comes from. So
  the job collects about a dozen files. It finds `tests/evals/parser/test_parser_eval.py` too,
  which `not eval` then deselects.
* **The planted break is in the end-to-end harness, not the ranking weights** that the proposal
  named. Putting t24's recency rule back would also fail the fast CLI tests t24 updated, so it is
  not a break only a slow test sees. Only the three e2e files import
  `tests/integration/e2e_harness.py`. A Crossref 404 there gives a well-formed wrong result, a
  journal card `UNVERIFIED` with `CITATION_UNVERIFIED`. My first plant, dropping the Crossref
  answer, crashed the CLI with `INTERNAL_ERROR`, and a crash is not a catch. t24's own merge stays
  as the selection replay.
* **The replay costs about 21 s** (one build of the real import graph) in whichever part gets its
  file. It runs on every pull request that reaches the file, as `test_affected_tests.py` does.
* **`run_slow` on a failed selection** is written by the workflow step, not the script. On a pull
  request into dev it is `true` with Chromium and no file list, so every slow test runs: it fails
  toward more, as the parts do. Elsewhere it is `false`.
* **`affected_tests.py` imports `ci_slow_tests` inside `run_slow_tests`.** The partition proof
  loads `affected_tests.py` by its path with `scripts/` off `sys.path`. My first top-level import
  failed it, which its own run below caught.

## Checks before the report

All on the operator's Mac, each test run under `scripts/hard_stop.py 115`.

* `uv run scripts/affected_tests.py --run --slow` → "The whole selection is affected:
  .github/workflows/ci.yml is shared test ground." It ran nothing; that run is the pull request's
  `ci`. So, as agreement 10 says, the test directories of what changed and the always-run list:
  `pytest tests/scripts tests/docs tests/architecture tests/specs packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py packages/debate_cli/tests/test_container_factories.py -m "not slow and not live and not partition_proof"`
  → `3450 passed in 88.37s`.
* The partition proof, as its job runs it (`-m "partition_proof and not slow and not live"
  tests/scripts/test_ci_workflow_test_job.py`). First run: 1 failed, a `ModuleNotFoundError` for
  `ci_slow_tests` when it loads `affected_tests.py` by path. After the fix: `2 passed in 15.72s`.
* The new tests with `test_affected_tests.py`, after that fix → `197 passed in 33.33s`.
* The job's command over the whole selection's 11 files, as this branch's own pull request will
  hand them (`ci_test_selection.py --event pull_request --base-branch dev`, then
  `scripts/ci_slow_tests.py --test-files …`) → 43 passed, 0 skipped, 58 s wall; the four left out
  were deselected.
* `ruff format --check .` → 2107 files already formatted; `ruff check .` → all checks passed (after
  removing a duplicate import it caught); `pyright` (whole project, as CI) → 0 errors;
  `lint-imports` → 20 kept, 0 broken; `uv run scripts/validate_specs.py` → OK: 684 files, 41 epics,
  621 tasks, 22 releases; `docs_index.py --check-descriptions`, `check_links.py` and
  `check_command_blocks.py --base origin/dev` → OK. ShellCheck over the six `run:` blocks this
  changed → clean. actionlint is not run here, since it downloads itself; the pull request's
  `workflow-lint` job runs it.

### Each check fails for its reason (13 mutants)

On the committed tree, each one applied, the new test file run (the replay left out), and restored
with `git checkout HEAD --`. Every one failed at assertions, with no errors:

| Mutant | Failed |
|---|---|
| a left-out id dropped | the four pinned, the summary, the deselect list |
| a skip passes | the skip verdict, `--slow`'s status |
| no conftest read | the three conftest cases |
| the planted-break file handed to the job | 7, among them "only the planted breaks runs no slow job" |
| slow tests on a push | the four events that are not a pull request into dev |
| Chromium always | the e2e-only choice |
| the markers spelled out, not validate-dev's | the markers test |
| no exit-5 pass | "no slow test left to run passes" |
| `--slow` hands every file | the three `--slow` tests |
| validate-dev's durations dropped | the durations test |
| the gate dropped from `ci` | the gate test |
| Playwright unconditional | the job's shape |
| the fallback runs no slow test | the fallback test |

### The planted break, run whole

The plant is a `-p` plugin under the scratchpad: the harness's Crossref answers 404 for the
journal's DOI. A change to `tests/integration/e2e_harness.py` selects 24 test files:
the 3 e2e files, the always-run list, and fast files that read source as data.

* The parts' command over all 24, planted
  (`pytest -p planted… -n auto -m "not slow and not live and not partition_proof" --dist worksteal @…`)
  → `788 passed in 39.39s`, exit 0. A first try put the plant in `PYTEST_ADDOPTS`. That leaked into
  `test_affected_tests.py::test_run_runs_the_selection_and_exits_with_pytests_status`'s own inner
  pytest, in a synthetic repository where the plugin cannot import, and the test failed; it passes
  without the plant. On the command line the plant reaches the outer run only.
* The slow job's command, planted: it is handed the 3 e2e files →
  `3 failed, 8 passed in 9.87s`. The failures are
  `test_cut_writes_each_kind_of_sources_card_…[open-access journal]` (exit `CARD_UNVERIFIED`,
  `CITATION_UNVERIFIED`) and both `test_e2e_research.py` tests (exit `AUTO_CUT_SHORT`,
  "2 of 3 cards VERIFIED").

## Operator follow-ups

<!-- Commands the operator must run (anything over ~2 minutes), with where to run them, the exact
command, expected runtime and what success looks like. Also GitHub/AWS settings to change. -->

None outstanding. The one command this task asked for, now done:

**Read-only: validate-dev's slow-job timings, for the proposal's question 2** (expected runtime
under a minute). Run it on your Mac, in the task worktree. It reads the last five validate-dev
runs and changes nothing. For each run it prints the slow job's steps with their start and end
times, then the pytest lines that give the xdist worker count and the totals.

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e41-t29-a-pull-requests-ci-runs-the-slow-tests-it-reaches
for run in $(gh run list --workflow validate-dev.yml --limit 5 --json databaseId --jq '.[].databaseId'); do
  gh run view "$run" --json jobs --jq '.jobs[] | select(.name | startswith("run the offline slow tier")) | "run \(.databaseId) \(.conclusion)", (.steps[] | "  \(.name) | \(.startedAt) | \(.completedAt)")'
  job=$(gh run view "$run" --json jobs --jq '.jobs[] | select(.name | startswith("run the offline slow tier")) | .databaseId')
  gh run view --job "$job" --log | grep -E "workers|[0-9]+ passed|[0-9]+ failed" | tail -n 4
done
```

Success looks like up to five blocks, each a job line, about a dozen step lines (one of them
"Install Playwright's Chromium for the browser tests") and a line such as
"58 passed, 2 failed in 346.12s". Paste it all back into the session.

**Result (run by the operator, 2026-11-13):** five runs, 131709322369, 131708396523,
131703924425, 131700738069 and 131660741652. The first four passed; the last had 2 failed and
58 passed. Every run had 4/4 workers and 60 items, and pytest took 409.04, 439.48, 385.27, 378.79
and 453.25 s, in that order. The step timings are summarised in the proposal's question 2.

## Follow-up work

<!-- Bugs, gaps or ideas outside this task's scope, each with the task or epic it belongs to.
The PM decides whether they become spec changes or new tasks. -->

* **This branch's own pull request is the first runner measurement.** It changes `ci.yml`, so it is
  the whole selection: the `slow-tests` job gets all 11 files and installs Chromium. Its pytest
  step and job time, against the longest part, show whether the 120-s and 60-s bound holds where it
  is tightest. 58 s wall on the Mac.
* **validate-dev's per-file costs from its next runs.** Its tiers now print their 25 slowest tests,
  so the planted-break cases' share of its 379–453 s can be read rather than inferred. That belongs
  in `docs/process/ci-test-part-costs.md`, for E41.
* **The environment-gated files start the job when they are all that is reached.** The text check
  reads files, not tests. A pull request whose only slow files are `test_docx_renderer.py` or the
  two SQLite feature files starts the job, which deselects their one slow test each and passes on
  exit 5: runner minutes, no wall-clock time. A per-test check would need a collection in
  `test-selection`, on every part's path. Not worth it unless the queue says otherwise.
* **The browser files' own job**, the ruling's first step past the bound, is not built. It waits
  for a runner measurement that needs it.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

# Session report: v1-e41-t29-a-pull-requests-ci-runs-the-slow-tests-it-reaches

| | |
|---|---|
| Task | `v1-e41-t29-a-pull-requests-ci-runs-the-slow-tests-it-reaches` — A pull request's ci runs the slow tests its affected set reaches |
| Spec | [`plan_specs/v1/e41-delivery-tooling-upkeep/t29-a-pull-requests-ci-runs-the-slow-tests-it-reaches.yaml`](../../plan_specs/v1/e41-delivery-tooling-upkeep/t29-a-pull-requests-ci-runs-the-slow-tests-it-reaches.yaml) |
| Epic / release | `v1-e41-delivery-tooling-upkeep` / `v1.8` |
| Branch | `task/v1-e41-t29-a-pull-requests-ci-runs-the-slow-tests-it-reaches` |
| Session status | IN PROGRESS: stopped at the proposal for the PM's ruling, no code written <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

Stopped at the proposal, as the brief asks. No code has changed yet. The proposal: a
`slow-tests` job in `ci.yml`, beside the test parts, on pull requests into `dev` only. It runs
validate-dev's slow-tier markers over the same affected set the parts run. Four tests are left
to validate-dev, each with its reason. It is one of `ci`'s needs, so a slow failure blocks the
merge. The measurements and the open questions are below.

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
| `tests/scripts/test_affected_tests_planted_breaks.py::test_a_planted_break_is_caught_by_a_test_the_script_selects` (14 cases) and `::test_a_break_no_selected_test_reaches_is_not_counted_as_caught` | Reached by every task PR (11 of 11), through its spec. About 4.5 minutes of the operator's Mac in v1-e08-t26's runs (70 + 43 + 40 s for 13 cases, case 12 about 123 s alone). It proves the selection against the whole repository, which is the job of validate-dev's run on each pre-release. Its fast tests still run in the parts. |
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

**On a CI runner:** validate-dev's log cannot give per-file times. Its slow tier runs `-rfEs` with
no `--durations`, so only the step timings and the total are there (run 43351384277: 60 tests in
346 s). The read-only `gh` command under **Operator follow-ups** fetches the slow job's step
timings and xdist worker counts from its last runs. The figure that matters is the Playwright
install step, which this estimate guesses.

**Estimated worst case on a runner** (a debate_core search change reaching the browser files and
the scale test, about 400–760 chosen files):

* job setup (checkout, uv, Python, `uv sync`): about 15–30 s, as a part's;
* Playwright's Chromium with its system libraries: not measured; guessed at 30–60 s;
* collecting the chosen files under the slow marker: about 8–15 s;
* pytest: about 50–80 s.

That makes the job about 2–3 minutes. The parts of such a PR are eight, at 2–3 minutes each, so
`ci`'s wall clock grows by **0–60 s** in that case. For the usual reach, the e2e files alone, the
job is about a minute, under the parts, and adds nothing. Each such PR does cost one extra runner
job.

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

## Plan nodes

<!-- One row per Plan graph node, in the order they were completed. -->

| Node | Status | Notes |
|---|---|---|
| | | |

## Acceptance criteria

<!-- Goal criteria (ac1…) and every node criterion. Status: PASS / FAIL / NOT RUN. -->

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| | | |

## Files changed

<!-- Group by package or directory; one line on why each group changed. -->

## Deviations from the spec

None.

## Decisions and assumptions

<!-- Choices the spec left open, with the reasoning. -->

## Operator follow-ups

<!-- Commands the operator must run (anything over ~2 minutes), with where to run them, the exact
command, expected runtime and what success looks like. Also GitHub/AWS settings to change. -->

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

## Follow-up work

<!-- Bugs, gaps or ideas outside this task's scope, each with the task or epic it belongs to.
The PM decides whether they become spec changes or new tasks. -->

None.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

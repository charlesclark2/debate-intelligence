# Session report: v1-e41-t15-ci-selection-once-and-no-queue

| | |
|---|---|
| Task | `v1-e41-t15-ci-selection-once-and-no-queue` — CI chooses the tests once, skips the test parts when none are chosen, cancels superseded pull-request runs, and runs the partition proof only when it can change |
| Spec | [`plan_specs/v1/e41-delivery-tooling-upkeep/t15-ci-selection-once-and-no-queue.yaml`](../../plan_specs/v1/e41-delivery-tooling-upkeep/t15-ci-selection-once-and-no-queue.yaml) |
| Epic / release | `v1-e41-delivery-tooling-upkeep` / `v1.8` |
| Branch | `task/v1-e41-t15-ci-selection-once-and-no-queue` |
| Session status | COMPLETE (Goal left `InProgress`: ac3 is the PM's read after the merge) <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

`ci.yml` now chooses the tests once, in a new `test-selection` job, and hands its answer to every
part as two job outputs: `run_parts` and `test_files`. No part runs `scripts/ci_test_selection.py`
any more. A change to `ROADMAP.md` and `docs/README.md` alone chooses no test. That covers the
bot's refresh pull request and the run the bot dispatches on its branch, which is compared with
`origin/dev`. The `test` matrix is then skipped, and `ci` accepts the skip. `ci` now reads a gate
map (`GATES_OF_JOB`): a skip passes only when an output the job is gated on says `false`. A failed
or cancelled part still fails it. The partition proof carries a `partition_proof` marker that the
parts leave out. It runs in a `partition-proof` job of its own: on every push, and on a pull
request that changes what it proves.

**PM, look first at three things:**

1. **The concurrency block was cancelling push runs on dev.** The group was
   `ci-${{ github.event.pull_request.number || github.ref }}`, so every push to dev shared
   `ci-refs/heads/dev`. Without cancel-in-progress, a push run waited behind the one before it.
   GitHub keeps one pending run per group, so when a third merge landed while the first run was
   still going, the second merge's run was cancelled. The first red run shows this: three pushes,
   and run 2 cancelled, on dev and on main. Now every run that is not a pull request has a group
   of its own, its run id.
2. **The selection runs in its own job beside `changes`, not inside `changes` as item (1) said**
   (see Deviations).
3. **The test parts may now start 10 to 20 seconds later on an affected-set pull request.** They
   wait for `test-selection`, which does its own setup and the selection, and then they run their
   own setup. The runner time saved is real; the net wall time is ac3's read.

The measurements and the options for item (5) are in
[`docs/process/ci-test-part-costs.md`](../process/ci-test-part-costs.md). The relay block under
Follow-up work carries them to the PM.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `ci-selection-once-and-no-queue` (CI once) | Done | Tests red first (`a85ea4b`), implementation (`904b09a`), docs (`57da164`, `1ec3a2c`) |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the selection is chosen once and every part reads it, and an empty selection skips the matrix while `ci` still passes, by workflow tests shown failing first | PASS | See "Red, then green" and "Mutants" below. Red at the start commit: 70 failed, 48 passed. Green: 119 passed. |
| ac2: pull-request runs on the same branch cancel the superseded run while push runs never do, and the partition proof runs only on its triggers and on push runs, by tests shown failing first | PASS | Same runs. The concurrency tests were red for their own reason at the start commit: `assert [1] == []`, run 2 of three pushes cancelled, on dev and on main. |
| ac3: after merge, the PM records the operator's read of one bot pull request (no test parts) and one ordinary task pull request's `ci` wall time | NOT RUN | Can only be taken after this branch merges; the PM reads it from the public API. The Goal stays `InProgress` for it. |
| ac4: each part's fixed cost against its test time is recorded in docs/process with the options, sent to the PM | PASS | [`docs/process/ci-test-part-costs.md`](../process/ci-test-part-costs.md), plus the relay block under Follow-up work. |
| Node: `uv run pytest tests/scripts -k "ci_workflow or test_selection"` | PASS | `121 passed in 35.88s` (the two partition proofs included), run under `scripts/hard_stop.py 115` |

### Red, then green

* **Red at the start commit** (new tests, with the old `ci.yml` and script):
  `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -n 4 -p no:randomly -q --tb=line -m "not slow and not live and not partition_proof"` over the four workflow test files →
  `70 failed, 48 passed`. Grouped by reason:
  * 30 failed on the script's old interface (`--output`).
  * 17 failed on the missing `partition_proof` output and 12 on the missing `test-selection` job.
  * 1 each failed on `GATES_OF_JOB`, the parts' marker expression, the gated `if:` and the generated files' filter.
  * 2 were behavioural: push runs cancelled under the old group.
* **Red for the rules' own reasons**, after the script's interface change alone: `8 failed, 23 passed`.
  * 5 × `AssertionError: no test part runs`: generated files alone, on a pull request (both files, ROADMAP.md, docs/README.md) and on the bot's dispatch (on dev's tip, and with dev moved on).
  * `handed_to_the_parts` missing.
  * 2 whole-selection fallbacks reporting the old reason.

  Committed as `a85ea4b`.
* **Green** (`904b09a`), same command: `119 passed in 11.26s`. Partition proof, with the job's own
  command (`pytest -n auto -m "partition_proof and not slow and not live" --durations=10 tests/scripts/test_ci_workflow_test_job.py`):
  `2 passed in 55.52s`, the whole-selection proof 53.79 s.

### Mutants

There were 16 mutants: the PM's four, then the rest. Each was applied to `HEAD`, run against the
four workflow test files and restored with `git checkout HEAD --`. Every one was caught, by the
test aimed at it.

| Mutant | Caught by |
|---|---|
| `ci` reads a failed part as a skip (gated variant) | `test_ci_fails_when_a_part_failed_whatever_its_gates_say` |
| `ci` reads a failed part as a skip, gates or not | 5 tests, including `test_ci_fails_when_a_part_failed_or_was_cancelled[failure]` |
| Push runs in the cancelling group (`cancel-in-progress: true`) | 5 tests, including `test_pushes_to_dev_or_main_are_never_cancelled_however_quickly_they_land[dev]` and `[main]`, and `test_dispatched_runs_are_never_cancelled` |
| The start commit's group, per branch | the two push tests |
| Partition proof never selected on a push | `test_the_proof_runs_on_every_push_whatever_changed`, `test_a_push_still_runs_everything` |
| The proof's filter loses `tests/pytest_plugins/**` | `test_the_proof_runs_on_a_pull_request_that_changes_what_it_proves[run_in_parts.py]` and `[a_new_plugin.py]` |
| `partition-proof` gated on another output | `test_ci_reads_each_jobs_gates_from_the_jobs_own_condition`, `test_the_proof_has_a_job_of_its_own…` |
| The parts run the proof again | `test_the_parts_leave_the_proof_to_its_job` and 2 more |
| A part computes its own selection | `test_one_job_chooses_the_tests_and_no_part_chooses_its_own` |
| A failed script skips the parts (`run_parts=false`) | `test_a_script_that_fails_runs_every_part_over_the_whole_selection` |
| docs/README.md stays in the python filter | `test_the_generated_files_alone_select_no_python_job` |
| A deleted generated file chooses nothing | `test_the_generated_files_and_anything_else_still_select_tests[deleted]` |
| Any Markdown alone chooses nothing | `…[and-a-document]` |
| The bot's dispatch compares only its last commit | `test_a_dispatched_run_of_the_bots_branch_carrying_more_runs_the_whole_selection` and 1 more |
| No limit on the list handed to the parts | `test_an_affected_set_too_long_to_hand_to_the_parts_runs_the_whole_selection` |
| Any dispatch on the bot branch chooses nothing | `test_a_dispatched_run_of_the_bots_branch_carrying_more_runs_the_whole_selection` |

### The other checks before the report

| Command | Result |
|---|---|
| `uv run scripts/affected_tests.py --run` | `The whole selection is affected: .github/workflows/ci.yml is shared test ground.` Nothing run; the pull request's `ci` runs the whole selection (agreement 10). |
| Within the two minutes: the always-run list, `tests/specs`, and every test that reads the workflows, the selection script or the pytest config (17 files, among them `test_affected_tests.py`, `test_workflow_runners.py`, `test_refresh_generated_files_workflow.py`, `test_validate_dev_workflow.py`, `test_dev_prerelease_workflow.py`, `test_release_version.py`), under `hard_stop.py 115` | `1129 passed in 54.44s` |
| `.venv/bin/python -m pytest -n 4 -q tests/architecture tests/docs` (after adding the docs/process page) | `433 passed in 8.86s` |
| `uv run --frozen scripts/actionlint.sh` | exit 0, actionlint 1.7.12 with shellcheck 0.11.0. A copy of ci.yml with `test_files` misspelt `test_filez` exits 1: `property "test_filez" is not defined in object type {run_parts: string; test_files: string}`. |
| `uv run --frozen ruff format --check .` / `ruff check .` | `1805 files already formatted` / `All checks passed!` |
| `uv run --frozen pyright` over the changed script and the four test files (no package changed) | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen lint-imports` / `check_thin_handlers.py` | `Contracts: 20 kept, 0 broken.` / `OK: 71 CLI command and API route handlers within 25 statements` |
| `uv run scripts/validate_specs.py` | `OK: 576 files, 41 epics, 513 tasks, 22 releases` |
| `docs_index.py --check-descriptions` / `check_links.py` / `check_command_blocks.py --base origin/dev` | `All 67 indexed documents under docs/ have a description` / `OK: 3374 relative links and anchors in 538 Markdown files` / `OK: no # comments in 652 shell code blocks` |

## Files changed

* `.github/workflows/ci.yml`:
  * **Concurrency:** one group per pull request; a group of its own for every other run.
  * **`changes`:** a `partition_proof` filter and output; the generated files leave the Python filter.
  * **New `test-selection` job:** runs the selection once and hands it to every part.
  * **`test`:** gated on `run_parts`, writes down `test_files` for pytest, and leaves the proof's marker out.
  * **New `partition-proof` job.**
  * **`ci`:** needs both new jobs and reads `GATES_OF_JOB`.
  * **Header comment** updated.
* `scripts/ci_test_selection.py`:
  * Writes its choice in `$GITHUB_OUTPUT`'s format (`--outputs`, which replaces `--output`).
  * The generated-files rule, for a pull request and for the bot's dispatch.
  * Falls back to the whole selection when the list is longer than 100,000 bytes, because Linux refuses an environment variable over 128 KiB; all 650 test files name about 42 KB.
* `pyproject.toml`: registers the `partition_proof` marker.
* `tests/scripts/test_ci_workflow_selection_once_and_no_queue.py` (new, 38 tests): the selection job and the part's step run in bash, `ci`'s step run with jq for each case, the concurrency rule, and the partition proof's job and filter.
* `tests/scripts/test_ci_workflow_test_selection.py` (31 tests): reads the outputs file as the runner does, and adds the generated-files, bot-dispatch and size-limit cases.
* `tests/scripts/test_ci_workflow_test_job.py`: the two proofs are marked; the parts' marker expression and condition updated; the selection-step tests moved to the new file.
* `tests/scripts/test_ci_workflow_site_changes.py`: reads `GATES_OF_JOB`. The generated files select no Python job, and the test pins those two files to the script's list and the bot's workflow. A dispatch runs everything but the proof.
* `docs/process/working-agreements.md`: agreements 1 and 10 describe the selection job, the empty selection, the proof's job and the concurrency rule.
* `docs/process/ci-test-part-costs.md` (new): the measurements and options for ac4.

## Deviations from the spec

* **The selection runs in its own job, `test-selection`, beside `changes`, not inside `changes`.**
  Item (1) says "in the `changes` job". `changes` gates typecheck, import-boundaries, terraform,
  site and workflow-lint, and today it does no checkout, which makes it a few seconds long. The
  selection needs a checkout, uv, `uv sync` (affected_tests reads imports with grimp) and 17 to
  33 s of its own. Inside `changes`, all of that would delay every gated job. Beside it, only
  `test` waits for it. If the PM wants it in `changes`, the spec's wording stands and it is a
  small move.
* **Item (3)'s concurrency group already existed**, cancel-in-progress for pull requests included.
  It was wrong for pushes, as the Summary describes, so the task changed the group rather than
  adding one.
* **The partition proof's triggers are wider than the three named files.** The ruling names
  `ci.yml`, `run_in_parts.py` and the selection script. The filter also covers every file under
  `tests/pytest_plugins/`, `scripts/affected_tests.py` (its always-run list is what the
  affected-set proof checks each part holds), the proof's own file, `pyproject.toml` (addopts loads
  the plugin), the root `conftest.py` and `uv.lock` (pytest's and xdist's versions). Each fails
  toward running the proof. The proof does not run on a dispatch: the ruling says push runs, and a
  dispatch's commit either has its own push run or is the bot's, which runs no part.
* **The generated files also leave the `python` path filter**, so the bot's pull request skips
  typecheck and import-boundaries as well as the test parts. That is the spec's "runs only the doc
  checks". The bot's dispatched run still runs typecheck, import-boundaries, site, terraform and
  workflow-lint, because `changes` turns everything on for a dispatch; only its test parts go. See
  Follow-up work.
* **actionlint was run by the session.** `scripts/actionlint.sh` downloads the pinned,
  checksum-verified release from GitHub. The PM's brief for this task said to run it, which I read
  as overriding the standing "network calls go to the operator" ruling for this one read-only
  download.

## Decisions and assumptions

* **How `ci` reads a skipped `needs` result:**
  * `GATES_OF_JOB` lists, for each gated job, the `job.output` names its `if:` requires to be `'true'`.
  * A skip is accepted only when one of them is `"false"`.
  * Success is `ok`, and anything else is `FAIL`: a failed or cancelled job, including a matrix job with one failed part, and a skip with every gate open or unreadable.
  * A failed `changes` or `test-selection` job leaves its outputs empty. So every job it gates fails `ci` as well as the job itself.
  * A test pins the map to the jobs' own `if:` conditions, so the two cannot drift.
* **The choice reaches the parts as job outputs and an environment variable, not an artifact.**
  An artifact would add an upload and eight downloads. The size limit and its fallback cover the
  only risk.
* **The script writes its outputs to a file, and the step appends that file to `$GITHUB_OUTPUT`
  only when the script succeeded.** A script that fails part-way can't leave `run_parts=false`
  behind, and the fallback is `run_parts=true` with no list, which is the whole selection.
* **The bot's dispatched run is compared with `origin/dev` from a full-history checkout**
  (`fetch-depth: 0`, the same as spec-validate; the packs are about 9 MB). It is not compared with
  `HEAD^`, so a person's commit under the bot's still runs the whole selection.
* **A deleted generated file is not "generated files alone"**, because links to it would break.
  A pull request into main is still a promotion, whatever it changes.
* **Dispatched runs are never cancelled.** A superseded bot dispatch would be safe to cancel, but
  it now runs no part, so there was little to gain.
* **The bot's refresh pull requests produce both kinds of run.** They are opened with the workflow
  token, which starts no `pull_request` run, yet the PM measured `pull_request` timings for them.
  Those runs' pytest times (15 to 33 s) are an affected set, not the dispatch's whole selection.
  Presumably they come from a person updating the branch. Both routes now choose no test.

## Operator follow-ups

None. ac3 is the PM's read of the public API after the merge, so there is no block for it.

## Follow-up work

* **Relay to the PM** (the item (5) options, paste-ready):

  > v1-e41-t15 measured what a CI test part costs besides its tests (docs/process/ci-test-part-costs.md).
  > Locally, under `-n 4` with a load average of 4 to 7:
  > * Part 1 of 8 collects in about 8.3 s, and collection's wall time is 7.9 / 8.7 / 9.4 s at `-n 0` / 2 / 4. Every part and every worker collects the whole selection.
  > * 90% of the part's tests finish by 60 s. The rest is a tail of smoke and bucket-mode tests at 5–11 s each, which ran past 115 s.
  > * Fixture setup is 98 of 328 s of the part's worker time (30%). A module-scoped fixture is rebuilt in all eight parts, because every file is dealt across all of them.
  >
  > On GitHub (your figures), part pytest is 190–290 s on whole-selection runs, so collection plus setup is a tenth to a sixth of a part. On affected-set runs (pytest 15–33 s) it is half or more. The options:
  > 1. Size the matrix to the selection: test-selection hands `test` one or two parts for a small affected set and all eight for the whole selection. This saves 5–6 jobs per ordinary PR. Small. **Recommended first.**
  > 2. `--dist worksteal` in the parts: a one-flag change aimed at the tail. Measure it on one whole-selection run. **Recommended alongside 1.**
  > 3. Deal whole files by recorded durations. This cuts each part's collection to an eighth and stops rebuilding module fixtures in every part. It needs a durations file refreshed on dev's push run, and the heaviest file is about 300 s of worker time. It is the largest change. Recommended when a whole-selection part passes 2 minutes again.
  > 4. Fewer parts across the board: six parts would put whole-selection parts at about 250–390 s. Not recommended.
  > 5. A different xdist worker count: not recommended without a runner measurement.
  >
  > Also decide: keep `test-selection` beside `changes` (my choice, so path-filtered jobs don't wait about 40 s), or amend item (1).

* **Turn off the other jobs on the bot's dispatched run.** It still runs typecheck,
  import-boundaries, site, terraform-checks and workflow-lint, because `changes` turns every
  output on for a dispatch. The `changes` job could compare a dispatch of
  `bot/refresh-generated-files` with `origin/dev`, as `test-selection` now does. This belongs in
  E41.
* `dev-prerelease.yml` and `validate-dev.yml` group by commit, so they never had this task's
  push-cancelling problem; dev-prerelease's comment describes the pitfall `ci.yml` had.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-02

**Notes:**

Accepted, with the Goal `InProgress` for ac3, the PM's read after the merge. The best find is the one
the PM didn't ask for: the old concurrency group put every push to dev in one group. A third merge
landing while the first run was still going cancelled the second merge's run. Your red test shows
it, and every non-PR run now has a group of its own.

1. **ac1 and ac2:**
   * 70 tests failed at the start commit, then 8 failed for the rules' own reasons after the
     interface change, and 119 pass now.
   * The partition proof runs in its own job: 2 passed, 55 s.
   * 16 mutants, the PM's four among them, each caught by the test aimed at it.
   * `GATES_OF_JOB` is pinned to the jobs' own `if:` conditions, so the two can't drift. A failed or
     cancelled part fails `ci`; a skip passes only behind a closed gate.
2. **ac4:** `docs/process/ci-test-part-costs.md` and the relay block hold the options.
3. **Deviations accepted:**
   * **`test-selection` as a job beside `changes`.** Inside `changes`, its checkout and `uv sync`
     would delay every path-filtered job. Item (1) is amended to match in the PM's next batch.
   * **The concurrency group corrected** rather than added.
   * **The partition proof's wider triggers** (every plugin, `affected_tests.py`, `pyproject.toml`,
     the root `conftest.py`, `uv.lock`), each failing toward running it.
   * **The generated files leaving the `python` filter.**
   * **Running `actionlint.sh`.** It was in the PM's brief, so that download is covered. The standing
     rule is otherwise unchanged.
4. **Decisions accepted:**
   * outputs and an environment variable, not an artifact, with the size fallback;
   * the script's outputs appended only on success, so a failure means the whole selection;
   * the bot's dispatch compared with `origin/dev` from full history;
   * a deleted generated file not treated as "generated files alone";
   * dispatches never cancelled.
5. **The rulings on item (5)'s options:**
   * **1 (size the matrix to the selection) and 2 (`--dist worksteal`, measured on one
     whole-selection run):** the PM files them as one E41 p2 task. It also turns off the other
     Python jobs on the bot's dispatched run, by comparing a dispatch of
     `bot/refresh-generated-files` with `origin/dev` in `changes`, as `test-selection` does.
   * **3 (deal whole files by recorded durations):** deferred until a whole-selection part passes 2
     minutes again.
   * **4 and 5:** not taken.
6. **ac3:** after the merge, the PM reads one bot run (no test parts) and one ordinary task PR's `ci`
   wall time from the public API, records them in a batch, and sets the Goal `Succeeded`.
7. **Closing checks:** the affected set is the whole selection (ci.yml is shared ground), so it is
   left to this PR's `ci` (agreement 10). The bounded run (1,129 passed), architecture and docs (433),
   actionlint (with a planted misspelling caught), ruff, pyright, lint-imports, thin handlers, the
   specs and the doc checks are clean.
8. **Merge:** `scripts/task pr --partial` once `ci` is green. This PR's own `ci` runs the whole
   selection under the new workflow, which is a useful first read.

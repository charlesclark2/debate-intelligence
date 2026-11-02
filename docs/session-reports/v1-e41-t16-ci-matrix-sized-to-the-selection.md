# Session report: v1-e41-t16-ci-matrix-sized-to-the-selection

| | |
|---|---|
| Task | `v1-e41-t16-ci-matrix-sized-to-the-selection` — CI runs as many test parts as the selection needs, measures work stealing, and the bot's dispatched run runs no Python job |
| Spec | [`plan_specs/v1/e41-delivery-tooling-upkeep/t16-ci-matrix-sized-to-the-selection.yaml`](../../plan_specs/v1/e41-delivery-tooling-upkeep/t16-ci-matrix-sized-to-the-selection.yaml) |
| Epic / release | `v1-e41-delivery-tooling-upkeep` / `v1.8` |
| Branch | `task/v1-e41-t16-ci-matrix-sized-to-the-selection` |
| Session status | COMPLETE (the Goal stays `InProgress`: ac2 can only be met after the merge) |

## Summary

`ci.yml`'s `test` matrix is now as many parts as the selection needs. `test-selection` outputs
`parts`, one part per 30 test files chosen, at least one and at most eight, and eight for the whole
selection (the PM's ruling of 2026-11-02). The matrix is `fromJSON` of that list, and each part asks
for `--part K/N` with N the matrix's total. A dispatch can ask for pytest-xdist's `--dist worksteal`
through a new `xdist_dist` input (default `load`); every other run, the bot's dispatch included, runs
`load`. The bot's dispatched run of `bot/refresh-generated-files` now selects no path-filtered job
(no Python job, no Terraform, site or workflow job): `changes` compares that branch with
`origin/dev`, as `test-selection` already did. The partition proof collects the parts the rule
gives and deals the real collection at every size from one to eight, and is no slower.

**What the PM should read first:** the measurement that came before the build. Ten of the last
twelve task pull requests still get eight parts under the rule (most reach 29-96% of the suite), so
sizing saves runners and queueing on small selections but does not shorten an ordinary task pull
request's wait. The figures are in `docs/process/ci-test-part-costs.md` and under Follow-up work.
ac2 is NOT RUN: the worksteal comparison is two operator dispatches after the merge, and the three
`ci` wall times are the PM's read.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `ci-matrix-sized-to-the-selection` | Done | Item 3 (the bot's dispatch) first, then the measurement and the PM's rulings, then items 1, 2 and 4. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the matrix's size follows the selection by a stated rule, every selected test is in exactly one part at every size, and the bot's dispatch selects no Python job, by workflow tests shown failing first | PASS | **Red first.** Bot dispatch: `pytest -n 0 tests/scripts/test_ci_workflow_bot_dispatch.py …site_changes.py …selection_once_and_no_queue.py` → `14 failed, 65 passed` before the `changes` step existed. Sizing and worksteal: `pytest -n 4 -m "not partition_proof" tests/scripts/test_ci_workflow_test_selection.py …selection_once_and_no_queue.py …parts_sized_to_the_selection.py …test_job.py` → `56 failed, 72 passed` before the script and ci.yml changed (no `parts` output, no `fromJSON` matrix, no `xdist_dist` input). **Green:** the node's command below, `171 passed`. **The rule:** `scripts/ci_test_selection.py` `parts_of`, `TEST_FILES_PER_PART = 30`, `MOST_PARTS = 8`, stated in ci.yml's header, agreements 1 and 10 and the costs page. **Every size:** the partition proof (`pytest -n auto -m "partition_proof and not slow and not live" tests/scripts/test_ci_workflow_test_job.py`) → `2 passed in 18.74s`; it collects the whole selection's 8 parts, the affected set's own 1 part and its 8, and deals both real collections at sizes 1-8 with the plugin's `parts_dealt`, checked equal to the collected parts. **Mutants:** 14, 13 caught and 1 equivalent and removed, plus actionlint shown failing on two planted typos (table below). |
| ac2: worksteal is measured on a whole-selection run and kept or dropped on the figures, and three task pull requests' `ci` wall times after the merge are recorded by the PM | NOT RUN | Needs runs on GitHub after the merge. The switch is built and tested (`test_ci_workflow_parts_sized_to_the_selection.py`, including real `-n 2 --dist worksteal` and `--dist load` runs on the locked pytest-xdist 3.8.0). The operator's dispatch blocks are under Operator follow-ups; the PM reads the eight parts' pytest step times and decides the default, then reads the next three ordinary task pull requests' `ci` wall times. |
| Node `ci-matrix-sized-to-the-selection`: Matrix sized tests pass (`uv run pytest tests/scripts -k "ci_workflow or test_selection"`) | PASS | `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest tests/scripts -k "ci_workflow or test_selection" -q` → `171 passed in 31.20s` (the partition proof included). Run with the venv's python under the 115-second limit rather than `uv run`, per agreement 10. |

### Mutants

Each was applied to the committed tree, run against the workflow test files (with the partition
proof where the mutant touches dealing), and restored; `git status` was clean after each batch.

| Mutant | Caught by |
|---|---|
| The bot's dispatch still selecting Python jobs (`python` output ignores the comparison) | 4 cases of `test_the_bots_dispatch_of_the_generated_files_alone_selects_no_python_job_and_no_other`, `test_every_path_filtered_output_but_the_proof_reads_the_comparison` |
| A deleted generated file accepted | `test_a_generated_file_deleted_on_the_bots_branch_runs_everything` |
| Any file accepted on the bot's branch (a person's commit) | `test_a_persons_commit_under_the_bots_still_runs_everything` |
| A failed comparison (no `origin/dev`) writes 'true' | `test_the_bots_branch_without_origin_dev_runs_everything_and_says_why` |
| An empty diff reads as "only the generated files" | **Survived: equivalent.** An empty listing reaches the loop as one empty line, which is no generated file. The explicit check was removed (agreement 8) and a comment says why (`85fbe4c`). |
| The parts dealing by eight, not by the matrix's total (plugin `% 8`) | Partition proof: "in the selection given and in no part: 349" (the affected set's real one-part collection) and "in the default selection, in 1 parts and in no part: 17600"; also the coverage-combining test |
| The parts list repeating part 1 (`[1, 1, …, N-1]`: a test in two parts and N in none) | Both partition proofs, the script's rule tests and every whole-selection case (35 failed) |
| The size rule ignoring the selection (always 8) | `test_a_pull_request_into_dev_gets_one_part_per_30_test_files_it_reaches`, `test_the_rule_is_one_part_per_30_test_files_at_most_eight` and 6 more |
| The pull-request part asking `--part K/8` | `test_every_part_asks_for_its_number_out_of_the_matrix_total_not_a_fixed_count` and 3 more |
| The matrix left at `[1, …, 8]` | `test_the_matrix_is_the_list_of_parts_the_selection_job_gives`, `test_the_parts_are_numbered_from_one…` |
| `ci` reading a failed part as an accepted skip | `test_ci_fails_when_a_part_failed_whatever_its_gates_say` |
| The fallback for a failed script running one part | `test_a_script_that_fails_runs_every_part_over_the_whole_selection`, `test_a_selection_script_that_fails_runs_the_most_parts` |
| `worksteal` by default in the job's `XDIST_DIST` | `test_every_part_runs_with_the_distribution_the_run_asked_for`, `test_only_a_dispatch_that_asks_for_worksteal_gets_it` |
| The input defaulting to `worksteal` | `test_a_dispatch_can_ask_for_worksteal_and_load_is_the_default` |
| actionlint: `outputs.partz`, `inputs.xdist_distt` planted | `scripts/actionlint.sh` → exit 1, both named as undefined properties; clean tree exit 0 |

### Checks run before the report

| Command | Result |
|---|---|
| `.venv/bin/python scripts/hard_stop.py 115 uv run scripts/affected_tests.py --run` | "The whole selection is affected: .github/workflows/ci.yml is shared test ground." Nothing run; this PR's `ci` runs the whole selection (agreement 10, the PM's brief). |
| `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -n auto tests/scripts tests/architecture tests/specs packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py packages/debate_cli/tests/test_container_factories.py` (the changed test directory and the always-run list) | `2718 passed in 84.94s` (load average about 9) |
| `.venv/bin/python -m pytest -n 4 tests/docs tests/architecture` | `434 passed` |
| `scripts/actionlint.sh` | exit 0 |
| `uv run --frozen ruff format --check .` / `ruff check .` | `1835 files already formatted` / `All checks passed!` |
| `uv run --frozen pyright` (the whole configured tree, as the typecheck job runs it) | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen lint-imports` / `scripts/check_thin_handlers.py` | `Contracts: 20 kept, 0 broken.` / `OK: 72 … handlers within 25 statements` |
| `scripts/check_links.py`, `scripts/check_command_blocks.py`, `scripts/docs_index.py --check-descriptions` | pass; `All 68 indexed documents under docs/ have a description` |
| `uv run scripts/validate_specs.py` | `OK: 585 files, 41 epics, 522 tasks, 22 releases` |

## Measurements

On the operator's Mac, 2026-11-02, at load averages of 4.5 to 16 from other work; read the
proportions.

* **Recent affected sets.** `scripts/affected_tests.py --diff <commit>` for the last twelve task
  merges into `dev`, counted from one collection of the whole selection (20,077 tests in 654 files,
  72 s at load 7-11): two were the whole selection (shared test ground), and ten reached 46-622
  test files, 2,047-19,236 tests, 10-96% of the suite, median about 37%. The table, with the part
  counts under the rule, is in `docs/process/ci-test-part-costs.md`: 2, 4, then eight for the
  other ten.
* **Cost per test.** `fd48282`'s set (46 files, 2,047 tests) at `-n 4` with `--junitxml`:
  `2047 passed in 55.54s`, 203 s of worker time, 0.099 s a test (the costs page's whole-selection
  estimate is about 0.13 s).
* **The partition proof**, the job's own command, alternated with the pre-task proof from a
  temporary worktree at `144a612`: before 36.5 s and 18.2 s, after 18.7 s and 17.7 s.

## Files changed

* `.github/workflows/ci.yml`: `changes` checks out full history and compares the bot's branch with
  `origin/dev` on its dispatch only; every path-filtered output reads that comparison.
  `workflow_dispatch` has the `xdist_dist` input. `test-selection` outputs `parts` (the fallback
  writes eight); the `test` matrix is `fromJSON` of it; the parts pass `--dist "$XDIST_DIST"`, a
  job-level variable. The header and job comments describe all of it.
* `scripts/ci_test_selection.py`: `TEST_FILES_PER_PART`, `MOST_PARTS`, `SIZES_THE_RULE_GIVES`,
  `parts_of`, the `parts` output and the part count in the job summary.
* `tests/pytest_plugins/run_in_parts.py`: the dealing moved into `parts_dealt`, a pure function the
  hook calls, so the proof can deal the real collection at every size. It deals as before (the proof
  checks the function against the collected parts).
* `tests/scripts/`: new `test_ci_workflow_bot_dispatch.py` and
  `test_ci_workflow_parts_sized_to_the_selection.py`. Changed: `test_ci_workflow_site_changes.py`
  (the `changes` evaluator reads a `run:` step's outputs and `github.ref_name`),
  `test_ci_workflow_test_selection.py` (the `parts` output and the rule),
  `test_ci_workflow_selection_once_and_no_queue.py` (the `parts` output and the fallback), and
  `test_ci_workflow_test_job.py` (the proof at every size; `--dist no` in its one-process runs).
* `docs/process/working-agreements.md` (agreements 1 and 10) and `docs/process/ci-test-part-costs.md`
  (the rule, the twelve merges' part counts, the worksteal switch and its operator blocks).

## Deviations from the spec

* **Every path-filtered output, not only `python`, is 'false' on the bot's dispatch** when its
  branch changes only the generated files, so the dispatch selects what the bot's own pull request
  selects. The spec names Python jobs; the PM accepted the wider reading on 2026-11-02.
* **A wrong figure in the proposal.** The relay to the PM said one part per 30 test files "matches
  the 1,000-test rule on all 10 sets". I had computed 25 and 40 files a part, not 30. Recomputed,
  30 files a part gives 2, 4, 8, 8, 8, 8, 8, 8, 8, 8, where 1,000 tests a part gives 3, 5, 6, 7, 7,
  8, 8, 8, 8, 8. The two small sets get one part fewer, at about 1,020 tests a part, still near
  100 s; the 29-34% sets get one or two parts more. The ruling's reasoning holds, but the PM
  ruled on a claim that was not exact; both columns are in the costs page.

## Decisions and assumptions

* **When no part runs, `parts` is `[1]`.** GitHub refuses an empty matrix, and I could not confirm
  offline that it skips evaluating the matrix of a job whose `if:` is false, so the list is always
  a valid one. `run_parts` still decides, and `ci`'s gate is unchanged.
* **The proof covers every size by dealing, not by collecting every size.** Collecting all sizes
  would be 36 collections of the whole suite. The proof collects the parts the rule gives (8 for
  the whole selection, 1 and 8 for its affected set) and checks that the plugin's `parts_dealt`
  gives exactly those parts. It then deals the same real collection at every size from 1 to 8 and
  checks each is a partition. The dealing mutant is caught both ways.
* **`--dist` comes from a job-level variable**, `XDIST_DIST: ${{ inputs.xdist_dist || 'load' }}`,
  never spelled into the shell command, so no input text reaches the shell.
* **Test helpers that run a part's command in one process add `--dist no`.** With `-n 0`, an explicit
  `--dist load` makes pytest-cov measure as xdist's controller and keep no data. On a runner,
  `-n auto` already put pytest-cov on that path, so CI is unchanged.
* **The empty-diff check in the bot step was removed** as an equivalent mutant (agreement 8).

## Operator follow-ups

After this pull request merges, compare worksteal with load on one `dev` commit (ac2). Each
dispatch runs the whole selection in eight parts, no coverage, about 5 minutes on GitHub; nothing
is deployed or changed by them. Dispatch both, one straight after the other, with no merge into
`dev` in between:

```bash
gh workflow run ci.yml --repo charlesclark2/debate-intelligence --ref dev -f xdist_dist=load
gh workflow run ci.yml --repo charlesclark2/debate-intelligence --ref dev -f xdist_dist=worksteal
```

Then check both are of the same commit. Success is two rows with the same `headSha`; different
ones mean `dev` moved between them, and both are dispatched again. Paste the two `databaseId`s to
the PM, who reads the eight parts' pytest step times from the public API:

```bash
gh run list --repo charlesclark2/debate-intelligence --workflow ci.yml --event workflow_dispatch --branch dev --limit 2 --json databaseId,headSha,createdAt,status
```

No whole-selection run is handed over: this pull request changes `ci.yml`, so its own `ci` runs the
whole selection (the PM's brief).

## Follow-up work

* **Whole files dealt to parts by recorded durations** (the costs page's option 1), which the PM
  files as its own p1 task. The figures: ten of the last twelve task pull requests reach 29-96% of
  the suite (5,854-19,236 of 20,077 tests) and still get eight parts, each holding 731-2,404
  tests; a part's pytest step is about 15 s plus 0.09 s a test on a runner. So their wait is set by
  each part's whole-selection collection and fixtures rebuilt in every part, not by the part
  count. Whole-selection parts already take 190-290 s, over agreement 1's 2-minute line, which
  `MOST_PARTS` alone could only answer with more runners.
* **The `xdist_dist` default** is decided by the PM from the two dispatches; making `worksteal` the
  default is the input's `default` and the `'load'` in the `test` job's `XDIST_DIST`, and the two
  tests that pin `load` change with it.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

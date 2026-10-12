# Session report: v1-e01-t27-ci-test-job-within-budget

| | |
|---|---|
| Task | `v1-e01-t27-ci-test-job-within-budget` — The CI test job finishes well inside the five-minute budget |
| Spec | [`plan_specs/v1/e01-repo-foundation/t27-ci-test-job-within-budget.yaml`](../../plan_specs/v1/e01-repo-foundation/t27-ci-test-job-within-budget.yaml) |
| Epic / release | `v1-e01-repo-foundation` / `v1.0` |
| Branch | `task/v1-e01-t27-ci-test-job-within-budget` |
| Session status | PARTIAL <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The work is done and the Goal stays `InProgress`: the after-measurement (ac5, `ci` under 3 minutes
on three pull requests) can only be taken once this branch is pushed, so it is NOT RUN and is the
first operator follow-up. Merge with `--partial`.

Before the change, `ci` on a pull request took 257 to 388 s (median 329 s over nine runs), and
the `test` job was all of it: 243 to 374 s, of which about 15 s was setup. Three changes:

* **Coverage is off the pull-request path.** It is out of `addopts` and out of the `test` job. A
  push-only `coverage` job runs the old command over the whole selection.
* **The `test` job is a matrix of four parts**, each `pytest --part K/4` on its own runner. A new
  40-line plugin deals each test file's tests round the parts. There is no durations file and no
  list of directories.
* **The five tests that read the real spec tree** went from 11.3 s to 1.3 s, because the spec
  scripts now parse YAML with libyaml.

Expected `ci` on a pull request: about 1.5 to 2 minutes. That is an estimate from the before
figures, not a measurement.

Look first at:

1. **A file outside `constraints.packages` was edited**: two sentences in the root `README.md`
   that said a plain `pytest` measures coverage. See Deviations.
2. **A push now runs the suite twice** (the four parts, and the unsplit `coverage` job), and that
   job still grows with the suite. See Decision 1 and Follow-up work.
3. **Only one easy trim was found.** The other slow tests named in the spec are either reserved
   for `v1-e34-t22`, outside this task's packages, or slow for what they do. See Decision 3.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `ci-budget` (CI test job inside its budget) | Done, except the after-measurement | Its criterion passes: `uv run pytest tests/scripts -k workflow` → `56 passed`. Goal criterion ac5 is NOT RUN |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: a pull request's CI time before the change, from real runs: each job, setup against test time, the 30 slowest tests | PASS | Nine pull-request runs read with `gh run view --json jobs` and three job logs with `gh run view --log`; nothing re-run, cancelled or dispatched. See [Before the change](#before-the-change). The 30 slowest are from local `--durations` runs: CI printed no durations until this change |
| ac2: pull-request runs measure no coverage, pushes to `dev` and `main` still do with the same report, covered by the workflow's tests, shown failing first | PASS | `uv run --frozen pytest tests/scripts -k workflow` → `14 failed, 42 passed` on the unchanged workflow, `56 passed` after. One test runs both commands and reads their output. 8 mutants on this criterion, all caught. See [Coverage](#decision-1-coverage) and [Mutants](#the-tests-shown-failing). What no session can show is the `coverage` job itself running: that first happens on the push to `dev` (operator follow-up 2, Deviation 4) |
| ac3: parallel jobs whose union is exactly the default selection, by a test comparing collected node ids with an unsplit collection; `ci` needs every part | PASS | `test_the_parts_together_are_exactly_the_default_selection_and_no_test_is_in_two_of_them`: 5,829 node ids unsplit; parts of 1,452, 1,458, 1,462 and 1,457; none in two parts, none in no part. `test` is still one entry in `ci`'s needs and in `PATH_FILTER_OF_JOB`. See [The union proof](#the-union-proof) |
| ac4: the slowest tests made cheaper where that is easy, each with before and after, no change to what it asserts | PASS | Five tests, 11.3 s → 1.3 s run alone. No test file was edited. See [Decision 3](#decision-3-which-slow-tests-were-made-cheaper) |
| ac5: on at least three pull requests after the change, `ci` under 3 minutes; runner minutes before and after | NOT RUN | Needs this branch pushed and merged. The before figure for runner time is below; the after figure and the three runs are operator follow-up 1 |
| ac6: working agreement 1 and the comment at the top of `ci.yml` state the new target, how the job is split and how to rebalance | PASS | `docs/process/working-agreements.md` §1 (Target, The test job runs in parts, When it drifts, Coverage) and the second comment block of `.github/workflows/ci.yml` |
| Node criterion: `uv run pytest tests/scripts -k workflow` | PASS | `56 passed in 5.46s` |
| `scripts/actionlint.sh` | PASS | exit 0, actionlint 1.7.12 with shellcheck 0.11.0 |
| Whole default selection, in four parts, after the last edit | PASS | See [The whole suite](#the-whole-suite) |
| `uv run scripts/validate_specs.py` | PASS | `OK: 347 files, 38 epics, 289 tasks, 20 releases` |

## Before the change

**Nine pull-request runs of `ci.yml`, 2026-10-11 and 2026-10-12.** Times are seconds from the
run's start. "Setup" is the `test` job minus its pytest step: checkout, uv, Python, `uv sync`.

| Run | Branch | `ci` done | `test` job | pytest step | Setup | All jobs, runner seconds |
|---|---|---|---|---|---|---|
| 38113706414 | `task/v1-e30-t11…` | 300 | 286 | 267 | 19 | 367 |
| 38118192145 | `task/v1-e30-t10…` | 329 | 317 | 300 | 17 | 403 |
| 38119547565 | `task/v1-e34-t17…` | 257 | 243 | 228 | 15 | 338 |
| 38121297543 | `specs/close-out-2026-10-11` | 359 | 343 | 330 | 13 | 429 |
| 38168101323 | `task/v1-e29-t07…` | 263 | 249 | 236 | 13 | 332 |
| 38205846896 | `task/v1-e34-t19…` | 388 | 374 | 359 | 15 | 459 |
| 38206074076 | `task/v1-e29-t08…` | 359 | 344 | 332 | 12 | 489 |
| 38206924726 | `task/v1-e29-t08…` | 387 | 372 | 356 | 16 | 521 |
| 38207415046 | `specs/pm-batch-2026-10-12` | 302 | 289 | 275 | 14 | 391 |
| **Median** | | **329** | **317** | **300** | **15** | **403** |

**The other jobs, over the same runs.** None is near the `test` job.

| Job | Wall-clock | Done at |
|---|---|---|
| `changes` | 3 to 5 s | +6 to +8 s |
| `lint` | 14 to 18 s | +16 to +21 s |
| `spec-validate` | 14 to 20 s | +16 to +23 s |
| `import-boundaries` | 10 to 20 s | +20 to +28 s |
| `typecheck` | 27 to 37 s (pyright 13 to 21 s) | +35 to +45 s |
| `terraform-checks` (two runs) | 65 and 66 s | +74 and +76 s |
| `test` | 243 to 374 s | +251 to +382 s |
| `ci` | 2 to 4 s | +257 to +388 s |

**Inside the pytest step**, from three job logs: 4 xdist workers on the runner; 5,603 tests in
233 s, 5,747 in 355 s and 5,812 in 353 s. The same suite varies by a minute or more between runs,
so one run is not a measurement.

**Locally, at the start commit** (the operator's Mac, 11 workers, CI's command with `--cov`), in
the three parts the PM's earlier ruling asks for, then again with `--no-cov`:

| Part | Tests | With coverage | Without |
|---|---|---|---|
| `packages/debate_core/tests` | 3,989 | 75.3 s | 43.7 s |
| `packages/debate_cli/tests` | 532 | 34.3 s | 24.0 s |
| `packages/debate_api/tests packages/debate_workers/tests tests` | 1,290 and 1 skip | 72.9 s | 55.3 s |
| **Total** | **5,812** | **182.5 s** | **123.0 s** |

Coverage is a third of the local wall-clock (33%). The share on a runner is not measured.

The suite's time is concentrated: the 30 slowest tests hold 176 of 984 test-seconds, and the 300
slowest hold 663.

**The 30 slowest tests**, from `--durations=60` on each of the three parts with coverage, merged.
These are times under 11 busy workers. Tests that start processes are several times slower there
than alone, which is why the order on a runner will differ.

| Seconds | Test |
|---|---|
| 13.63 | `tests/specs/test_spec_index.py::test_the_repository_roadmap_renders_deterministically` |
| 10.74 | `tests/specs/test_validate_specs.py::test_status_reports_every_release_in_the_repository` |
| 9.96 | `packages/debate_core/tests/evidence/test_normalization_props.py::test_paragraph_ids_survive_whitespace_edits_inside_paragraphs` |
| 9.20 | `packages/debate_cli/tests/test_help_rendering.py::test_the_terminal_sensitive_tests_pass_on_a_colour_forcing_terminal_of_any_width[narrow]` |
| 8.91 | `packages/debate_cli/tests/test_help_rendering.py::test_the_terminal_sensitive_tests_pass_on_a_colour_forcing_terminal_of_any_width[wide]` |
| 8.38 | `tests/smoke/test_caselist_pull.py::test_an_expired_session_still_imports_and_what_was_removed_here_stays_out` |
| 7.98 | `tests/smoke/test_caselist_pull.py::test_a_bucket_copy_that_is_refused_unavailable_or_torn_still_fails_the_import_closed[access_denied-3-STORE_ACCESS_DENIED]` |
| 7.26 | `tests/specs/test_validate_specs.py::test_the_repository_spec_tree_is_valid` |
| 7.23 | `tests/specs/test_spec_index.py::test_every_repository_release_and_epic_appears_in_the_rendered_roadmap` |
| 7.04 | `tests/smoke/test_caselist_pull.py::test_a_weekly_archive_this_mac_cannot_read_fails_its_own_import_with_one_and_the_rest_import` |
| 6.83 | `tests/scripts/test_site_deploy.py::test_the_hashed_assets_go_up_before_the_html` |
| 6.72 | `tests/smoke/test_caselist_pull.py::test_a_bucket_copy_that_is_refused_unavailable_or_torn_still_fails_the_import_closed[unavailable-3-STORE_UNAVAILABLE]` |
| 6.68 | `tests/smoke/test_caselist_pull.py::test_a_weekly_pull_downloads_imports_publishes_and_then_finds_nothing_new` |
| 6.62 | `tests/scripts/test_site_deploy.py::test_dev_does_not_run_the_prod_guard` |
| 6.53 | `tests/smoke/test_caselist_pull.py::test_a_local_refusal_in_publish_fails_it_with_the_data_directory_fix_and_is_never_pending` |
| 6.51 | `tests/smoke/test_caselist_pull.py::test_a_weekly_run_fetches_one_complete_archive_after_its_weeklies_and_says_why` |
| 6.51 | `tests/smoke/test_caselist_pull.py::test_a_bucket_copy_that_is_refused_unavailable_or_torn_still_fails_the_import_closed[torn_line-1-UNREADABLE_APPEND_ONLY_RECORD]` |
| 6.44 | `tests/smoke/test_caselist_pull.py::test_a_camp_file_removed_from_another_machine_is_not_requested_again` |
| 6.12 | `tests/smoke/test_caselist_pull.py::test_a_manifest_this_mac_will_not_let_be_written_fails_the_import_with_three_and_the_fix` |
| 6.06 | `tests/smoke/test_caselist_pull.py::test_a_profile_the_aws_config_lacks_fails_publish_with_one_and_everything_imported_stays_owed` |
| 6.04 | `tests/specs/test_validate_specs.py::test_release_order_matches_the_repositorys_release_files` |
| 6.02 | `tests/smoke/test_caselist_pull.py::test_a_manifest_file_this_mac_will_not_open_stops_the_run_with_three_and_never_seventy` |
| 6.00 | `tests/smoke/test_caselist_pull.py::test_a_bucket_listing_that_does_not_answer_fails_publish_with_three_and_the_next_run_publishes` |
| 5.97 | `tests/scripts/test_site_deploy.py::test_prod_proceeds_from_a_clean_main` |
| 5.64 | `tests/scripts/test_install_channel.py::test_the_option_leaves_every_failure_as_it_was[doctor]` |
| 5.53 | `tests/scripts/test_site_deploy.py::test_delete_only_ever_names_this_environments_own_bucket` |
| 5.37 | `packages/debate_core/tests/evidence/test_card_mapping.py::test_card_mapping_arithmetic_exists_once_in_the_whole_tree` |
| 5.32 | `tests/scripts/test_site_deploy.py::test_the_calendar_is_uploaded_as_text_calendar_and_nothing_else_is` |
| 5.24 | `tests/smoke/test_caselist_pull.py::test_a_pending_work_file_that_cannot_be_read_fails_publish_with_one_and_is_left_for_a_person` |
| 5.22 | `tests/smoke/test_caselist_pull.py::test_a_session_that_expires_part_way_through_publish_owes_every_snapshot_it_did_not_finish` |

By file, without coverage: `tests/smoke/test_caselist_pull.py` 112 s over 21 tests,
`tests/scripts/test_install_channel.py` 78 s over 41, `tests/integration/test_launchd_install.py`
70 s over 61, `packages/debate_cli/tests/commands/test_caselist_pull.py` 51 s over 65,
`tests/scripts/test_site_deploy.py` 49 s over 22, `tests/smoke/test_caselist_remove_smoke.py` 46 s
over 21, `tests/scripts/test_task_restart.py` 41 s over 107.

## Decisions and assumptions

### Decision 1: coverage

**`--cov` and `--cov-report=term-missing` are removed from `addopts`, so a plain `uv run pytest`
no longer measures coverage either.** The alternative was to leave `addopts` alone and pass
`--no-cov` in the `test` job. I chose the removal because:

* it costs a third of every local run (182.5 s against 123.0 s) and nothing is gated on it. The
  local suite is at the two-minute line largely because of it;
* the comment in `ci.yml` says `addopts` and the pull-request command say the same thing. With
  `--no-cov` in the job they would differ, and a local run would not be what a pull request runs;
* asking for it is one flag, and `[tool.coverage]` is untouched, so
  `uv run pytest --cov --cov-report=term-missing` prints the report every run used to print.

What changes for people: session reports that quoted "coverage 97%" from a local run need the
flag now. The command sessions usually paste, `uv run --frozen pytest -n auto --cov -m "not slow
and not live"`, still measures it.

**Pushes keep it in a job of their own, `coverage`, with `if: github.event_name == 'push'`.** It
runs `uv run --frozen pytest -n auto --cov --cov-report=term-missing -m "not slow and not live"`,
which is what the old job's command and the old `addopts` added up to, over the whole selection in
one run. That is why the report is the same: one unsplit run, the same flags, the same
`[tool.coverage]`. A test holds each of those three.

Three things follow from that choice, and the PM may want any of them the other way:

* **A push runs the suite twice**: the four parts, which are the verdict on the merge, and the
  unsplit coverage run. I did not make the parts carry coverage on a push, because each part would
  then print a report of its own quarter. Combining the parts' data into one report needs artifact
  uploads and a combine job that no pull request can exercise before it merges, and a failure
  there stops `dev-prerelease`, which waits for the push's run to succeed.
* **The push's run is as long as it is today**, about 6 minutes, and `dev-prerelease` still waits
  for it. Nothing got slower, but the pull-request gain does not reach the dev chain.
* **The `coverage` job still grows with the suite.** I gave it `timeout-minutes: 20`. At 10 it
  would have started failing pushes at roughly today's suite plus two thirds.

Smaller choices:

* **A dispatched run measures no coverage.** `refresh-generated-files.yml` dispatches `ci.yml` to
  give its pull request the required check, so a dispatch is a pull request's wait in all but
  name. The old comment said "a dispatch runs every job, like a push"; that is still true of every
  job `ci` needs.
* **`coverage` is not one of `ci`'s needs.** `ci` is what a pull request waits for and this job
  never runs on one. Adding it would have meant teaching the required check a second reason a job
  may be skipped. A failure in it still fails the push's run. A test now holds the rule: `ci`
  needs every job except `coverage`.

### Decision 2: how the test job is split

**A small plugin of our own, `tests/pytest_plugins/run_in_parts.py`, adds `--part K/N`.** Each
test file's tests are dealt round the N parts in collection order, starting from a part chosen by
a CRC of the file's path. The `test` job is a matrix, `part: [1, 2, 3, 4]`, and each part runs
`--part "${{ matrix.part }}/${{ strategy.job-total }}"`.

Why this and not the alternatives, all of which I measured or tried:

| Option | Result |
|---|---|
| `pytest-split` with a committed durations file | It resolves (0.11.0 with pytest 9.1.1; dry run only, nothing installed). Rejected: it needs about 5,800 recorded durations, some 700 KB of JSON, measured on a Mac whose order differs from a runner's, and it goes stale with every task. Without the file it warns on every run and splits by count |
| Lists of directories per part | Rejected: `packages/debate_core/tests` alone is half the test time, so the lists need balancing by hand, and a new directory nobody lists is a test that does not run. The PM's own note on `--ignore` not excluding what it names is this trap |
| Hash of each test's node id | Works, and is stateless. Heaviest part 1.10 times the mean at four parts |
| **Dealing each file's tests round the parts** | Chosen. Heaviest part 1.04 times the mean at four parts (256, 247, 231, 249 test-seconds from one set of timings), 1.04 at three, 1.05 at five. Every file's cost is spread evenly, including the seven files that hold 45% of the time |

What the choice gives:

* **Nothing to maintain and nothing to forget.** There is no durations file to refresh and no list
  to add a directory to. A new test is in exactly one part the moment it is collected.
* **Rebalancing is one edit.** The parts cannot drift apart from each other; they grow together.
  The answer is another part: append `5` to `matrix.part`. `strategy.job-total` supplies N, so
  the number of parts is written once.
* **A part can be reproduced locally**: `uv run pytest --part 2/4`.
* **A wrong N fails loudly.** `--part 5/4`, `0/4` or an empty total is a usage error, so a part
  cannot quietly run nothing.

Other choices:

* **Four parts, not three.** The estimate below gives about 2 minutes at three and about 1.5 at
  four. The suite grew 10% in two days (5,244 tests on 2026-10-10, 5,812 on 2026-10-12), so the
  spare room is worth one more 15 s setup.
* **A matrix, not four jobs.** A matrix job is one entry in `needs`, and its result is a failure
  if any part failed, so `ci`'s needs and `PATH_FILTER_OF_JOB` did not change at all and cannot
  miss a part. `fail-fast: false`, so each part reports for itself.
* **The plugin lives under `tests/` and is loaded from `pyproject.toml`** (`pythonpath` plus
  `-p run_in_parts` in `addopts`). The natural home was the root `conftest.py`, which is not in
  this task's packages. pytest 9.1.1 applies `pythonpath` before it loads `-p` plugins; I read
  that in the installed source and the suite runs on it.
* **Each part prints its 25 slowest tests** (`--durations=25`). Until now nothing showed which
  tests are slow on a runner.
* **Level, not identical.** Locally the four parts took 28 to 49 s across four runs, and part 4
  alone took 45, 49, 38 and 36 s. Another session was running tests on the machine. The
  run-to-run spread is larger than the spread between parts.

### Decision 3: which slow tests were made cheaper

**One change, five tests.** `scripts/validate_specs.py` and `scripts/spec_index.py` now parse with
`yaml.CSafeLoader` (libyaml), falling back to the pure-Python safe loader. The spec tree is 3 MB of
YAML and every read of it took 1.5 s; it now takes 0.2 s. No test file was edited, so what the
tests assert is unchanged by construction.

| Test | Alone, before | Alone, after | In the suite with coverage, before |
|---|---|---|---|
| `test_spec_index.py::test_the_repository_roadmap_renders_deterministically` | 3.17, 3.11 s | 0.37, 0.37 s | 13.63 s |
| `test_validate_specs.py::test_status_reports_every_release_in_the_repository` | 3.21, 3.15 s | 0.39, 0.40 s | 10.74 s |
| `test_spec_index.py::test_every_repository_release_and_epic_appears_in_the_rendered_roadmap` | 1.69, 1.75 s | 0.18, 0.18 s | 7.23 s |
| `test_validate_specs.py::test_release_order_matches_the_repositorys_release_files` | 1.64, 1.62 s | 0.20, 0.20 s | 6.04 s |
| `test_validate_specs.py::test_the_repository_spec_tree_is_valid` | 1.58, 1.58 s | 0.20, 0.19 s | 7.26 s |
| **All of `tests/specs` (82 tests)** | **13.07, 12.42 s** | **2.08, 1.82 s** | |

"Alone" is `uv run --frozen pytest tests/specs -n 0 --durations=7`, run twice each side. In a
full part after the change the five took 0.27 to 0.63 s each. In one earlier part run, while
another session's tests had the machine busy, two of them took 2.7 and 3.4 s.

That the change is safe: all 348 YAML files under `plan_specs/` load to equal documents under both
loaders, and the roadmap renders to the same 57,781 characters. Both were checked once by script,
not left as a test, because such a test would put the 1.5 s parse back. `spec-validate` in CI and
the pre-commit hook run the same script.

**What I did not trim, and why:**

| Tests | Why not |
|---|---|
| `tests/smoke/test_caselist_pull.py`, `tests/integration/test_launchd_install.py`, the doctor tests | Reserved for `v1-e34-t22`, as instructed. They are the largest and third-largest files by time |
| `packages/debate_cli/tests/test_help_rendering.py` (the two subprocess tests) | Not easy, and not in this task's packages. Each starts a pytest that runs 16 real tests; that run takes 6.3 s alone, 5 s of it the tests themselves and 0.4 s collection. The 22 s and 13 s in the spec were under load |
| `tests/scripts/test_install_channel.py` | Each test runs the real `uv tool install` into a scratch directory. Stubbing `uv` would change what is tested |
| `tests/scripts/test_site_deploy.py`, `tests/scripts/test_task_restart.py` | 0.58 s and 0.11 s per test alone; they run a shell script and git against stubs. Their 5 to 7 s in the list above is the 11 busy workers |
| Hypothesis properties in `packages/debate_core` | Outside the packages, and fewer examples would change what is checked |

The honest summary: locally the trim removes about 10 of 984 test-seconds. The split and the
coverage change are what move `ci`. Each part's `--durations=25` is the evidence the next trim
should start from, since a runner's order will not be this Mac's.

## The union proof

`tests/scripts/test_ci_workflow_test_job.py::test_the_parts_together_are_exactly_the_default_selection_and_no_test_is_in_two_of_them`
reads the two pytest commands out of `ci.yml`, collects the `coverage` job's command unsplit and
the `test` job's command once per part, and compares node ids. It takes 2.8 s alone and 7.6 s
inside a part. The same figures, printed by a script that calls the test's own helpers:

```
unsplit command: -n auto --cov --cov-report=term-missing -m not slow and not live
part command:    -n auto -m not slow and not live --part K/4 --durations=25
unsplit collection: 5829 node ids, 5829 distinct
part 1 of 4: 1452 node ids
part 2 of 4: 1458 node ids
part 3 of 4: 1462 node ids
part 4 of 4: 1457 node ids
sum of the parts: 5829
in more than one part: 0
in the unsplit collection and in no part: 0
in a part and not in the unsplit collection: 0
union of the parts == unsplit collection, node id for node id: True
197 test files; largest difference between two parts' share of one file: 1 test
```

5,829 is the 5,812 at the start commit plus the 17 tests this task adds. Running the parts gives
the same numbers: 1,452, 1,458, 1,461 and 1 skip, and 1,457.

## The tests, shown failing

**Against the unchanged workflow and `pyproject.toml`** (test file and plugin file present, nothing
else changed): `uv run --frozen pytest tests/scripts -k workflow -n 0 --no-cov` →
`14 failed, 42 passed`. Three of the new tests passed already, because they hold things that were
true before: `ci` needs every job, the path-filter map matches the jobs' conditions, and what
coverage measures. That first red mostly says "the structure is not there yet", so the mutants
below are the real evidence.

**19 mutants against the finished work**, one at a time, each file restored from saved bytes and
compared with `HEAD` afterwards. All 19 caught, none survived, none failed to apply, none errored
before running.

| Mutant | Caught by |
|---|---|
| One part is never dealt to (`dealt_to == part`) | the union proof; the two-commands test |
| A test is dealt to several parts (`<=`) | the union proof |
| Dealing starts from `hash()`, which differs per process | the union proof |
| A whole file goes to one part | the union proof (dealt unevenly) |
| The matrix skips part 3 | parts numbered from one; the union proof |
| Each part asks for itself out of 5 | parts numbered from one; the union proof; the two-commands test |
| The parts run only `packages`, not `tests/` | four tests, in 0.24 s, on the "names no path" check |
| The `test` job measures coverage again | no coverage in the test job; the two-commands test |
| `addopts` measure coverage again | no coverage in addopts; the two-commands test |
| `PYTEST_ADDOPTS: --cov` on the `test` job | no coverage in the test job |
| The `test` job stops running on pushes | the test job runs on every event; the path-filter map |
| Coverage also runs on dispatches | coverage on pushes only |
| Coverage runs on every event | coverage on pushes only |
| The coverage job prints no missing lines | coverage on pushes only |
| The coverage job runs one part | coverage on pushes only; the union proof |
| Branch coverage switched off | what coverage measures; the two-commands test |
| `ci` no longer needs `test` | `ci` needs every job but `coverage` |
| `test` loses its path-filter entry | the path-filter map |
| `fail-fast: true` | parts numbered from one |

"The two-commands test" is
`test_a_pull_request_run_prints_no_coverage_report_and_a_push_run_prints_it`. It runs the `test`
job's command and the `coverage` job's command on one small file and reads the output: no report
from the first, the `Name Stmts Miss Branch BrPart Cover Missing` table from the second.

One thing the first mutant run taught me. With the parts restricted to `packages`, that test
started the whole of `packages` in one process, and I stopped it by hand after 100 s. I added a
check that neither command names a path, and that mutant is now caught in 0.24 s. The table is
from a complete re-run on the final test file.

## Expected `ci` time and runner minutes

**These are estimates. ac5 is the measurement.**

* Per part, pytest step: the old step (228 to 359 s) less coverage (a third locally) and divided
  by four, plus about 10 s that every part repeats for starting workers and collecting. That is
  48 to 70 s. If coverage costs less on a runner than on the Mac, say a fifth, the top is 82 s.
* Per part, job: plus 15 s of setup, so 63 to 85 s, starting at +8 to +10 s after `changes`.
* **`ci` on a pull request: about 1 min 20 s to 1 min 50 s**, against a median of 5 min 29 s. Call
  it 1.5 to 2 minutes until measured. `terraform-checks`, when it runs, ends at about +76 s and is
  no longer hidden behind the test job.

Runner time on a pull request, all jobs:

| | Before (nine runs) | After (estimate) |
|---|---|---|
| Seconds of runner time | 332 to 521, median 403 | about 340 to 425 |
| Of which `test` | 243 to 374 | four parts of 63 to 85 s: 252 to 340 |
| Minutes as GitHub rounds each job up | 11 to 15 | 14 to 16 |

So runner time is about level: dropping coverage pays for three more setups and three more
collections. Rounded per job it is one to three minutes more. The repository is public, so
neither costs money.

On a push the `coverage` job adds what the `test` job costs today, 4 to 6 minutes of runner time,
and the run takes about as long as it does now.

## The whole suite

Run as CI runs it, one part at a time, after this report was written:
`uv run --frozen pytest -n auto -m "not slow and not live" --part K/4 --durations=25`. Only this
table was filled in afterwards, and `tests/docs` and the command-block check, which read this
file, were run again after that.

| Part | Result | Wall-clock |
|---|---|---|
| 1 of 4 | `1452 passed` | 36 s |
| 2 of 4 | `1458 passed` | 33 s |
| 3 of 4 | `1461 passed, 1 skipped, 1 warning` | 32 s |
| 4 of 4 | `1457 passed` | 36 s |
| **All** | **5,828 passed, 1 skipped: 5,829, the unsplit collection** | **137 s, one part at a time** |

The skip is the parser eval waiting on human corrections, and the warning is `pytest_socket`'s,
from the smoke harness test that tries the network on purpose. Both are as before.

Also: `uv run --frozen ruff check .` and `ruff format --check .` clean; `uv run --frozen pyright`
→ `0 errors`; `uv run --frozen lint-imports` → `12 kept, 0 broken`;
`scripts/check_command_blocks.py --base origin/dev` → OK; `docs_index.py --check-descriptions` →
OK; `pre-commit run check-merge-conflict --all-files` → Passed.

## Files changed

* `.github/workflows/ci.yml`: the `test` job is a matrix of four parts with no coverage; a new
  push-only `coverage` job; the header comment states the target, the split and what to change
  when it drifts.
* `pyproject.toml`: `--cov` and `--cov-report=term-missing` leave `addopts`; `pythonpath` and
  `-p run_in_parts` load the plugin. No dependency changed, so `uv.lock` is untouched.
* `tests/pytest_plugins/run_in_parts.py` (new): `--part K/N`.
* `tests/scripts/test_ci_workflow_test_job.py` (new): 17 tests for the coverage rule, the matrix,
  `ci`'s needs and the union proof.
* `scripts/validate_specs.py`, `scripts/spec_index.py`: one shared `load_documents`, on libyaml.
* `docs/process/working-agreements.md`: §1 gains the target, the split, the rebalancing rule, the
  local use of `--part`, and the coverage rule.
* `tests/README.md`: what `pytest_plugins/` is.
* `README.md`: two sentences. See Deviations.

## Deviations from the spec

1. **`README.md` is outside `constraints.packages` and I edited it.** It said the tests run "with
   coverage" and that `pytest` runs with "coverage and sockets disabled". Taking `--cov` out of
   `addopts` made both false. I changed the two sentences and added one line on `--cov` and
   `--part`. If the PM would rather keep the README out of this task, reverting that one file
   leaves everything else working, and the README wrong.
2. **The spec's examples of slow tests are mostly ones I could not touch.** The help-rendering
   tests are in `packages/debate_cli/tests`, outside the packages; the pull smoke tests and the
   launchd tests were reserved for `v1-e34-t22`. ac4 says "where that is easy", and I read the
   list as examples. One change, five tests, is what was easy and in scope.
3. **A script changed, not only tests.** The trim is in `scripts/`, which is in the packages. It
   changes how the spec tree is parsed, not what is parsed.
4. **"The same report" on a push is argued, not observed.** The `coverage` job cannot run before
   the merge. Its command, its flags and `[tool.coverage]` are each held by a test, and the
   two-commands test prints the table from that command on a small file.
5. **The before durations are in three parts, not two halves**, following the PM's earlier
   ruling that the second half is split again. Together they are the whole selection (5,812).
6. **The spec says about 5,750 tests.** It was 5,812 at the start commit.

## Operator follow-ups

Both are read-only and run from any directory. Neither takes more than a few seconds.

**1. The after-measurement (ac5).** Once this task's pull request and at least two more task pull
requests into `dev` have finished `ci`, list the recent pull-request runs with each job's time:

```bash
for run in $(gh run list -R charlesclark2/debate-intelligence --workflow ci.yml --event pull_request --status completed --limit 8 --json databaseId --jq '.[].databaseId'); do echo "== ${run}"; gh run view "${run}" -R charlesclark2/debate-intelligence --json jobs,startedAt,headBranch --jq '.startedAt as $s | "branch \(.headBranch)", (.jobs[] | select(.conclusion != "skipped") | "\(.name)\t\((.completedAt|fromdateiso8601) - (.startedAt|fromdateiso8601)) s\tdone at +\((.completedAt|fromdateiso8601) - ($s|fromdateiso8601)) s"), "runner seconds, all jobs: \([.jobs[] | select(.conclusion != "skipped") | ((.completedAt|fromdateiso8601) - (.startedAt|fromdateiso8601))] | add)"'; done
```

What to read, for each run whose branch is a `task/` or `specs/` branch (a run on branch `dev` is
a promotion into `main`, and does not count):

* the `ci` line: `done at +N s`. **Success is N under 180 on at least three runs**, this task's
  own included. I expect 80 to 120;
* four lines `test (1)` to `test (4)`, each about 60 to 90 s. A run from before the merge has one
  `test` line of 240 s or more, which is how to tell them apart;
* `runner seconds, all jobs`, to set against the before median of 403.

Paste the output to the PM. If all three are under 180, ac5 passes and the phase goes to
`Succeeded` in a small spec pull request. If a run is over, the per-part lines say whether one
part is slow or all four are.

**2. This task's own pull request, then the first push to `dev`.** When the pull request's `ci` has
finished, check that each part announced itself and that the four counts add up to the suite:

```bash
gh run view "$(gh run list -R charlesclark2/debate-intelligence --workflow ci.yml --branch task/v1-e01-t27-ci-test-job-within-budget --limit 1 --json databaseId --jq '.[0].databaseId')" -R charlesclark2/debate-intelligence --log | grep -E "coverage: platform|TOTAL +[0-9]+|part: [0-9]+ of [0-9]+|passed.* in [0-9.]+s"
```

Success on the pull request: four `part: K of 4` lines, one for each K; four `passed` lines whose
passed and skipped counts add up to the suite (5,829 at this commit; a runner skips 7 where the
Mac skips 1); and no `coverage: platform` line and no `TOTAL` line.

After the merge, the same command on the newest push run on `dev`:

```bash
gh run view "$(gh run list -R charlesclark2/debate-intelligence --workflow ci.yml --event push --branch dev --limit 1 --json databaseId --jq '.[0].databaseId')" -R charlesclark2/debate-intelligence --log | grep -E "coverage: platform|TOTAL +[0-9]+|part: [0-9]+ of [0-9]+|passed.* in [0-9.]+s"
```

Success on the push: the four parts as above, and from the `coverage` job one
`coverage: platform linux` line, one `TOTAL` line ending near `97%`, and one `passed` line with
the whole suite's count. If the `coverage` job fails, the push's run is red and `dev-prerelease`
does not start; the fix is a pull request, and the parts' verdict on the merge is unaffected.

No GitHub setting changes: `ci` is still the only required check and was not renamed.

## Follow-up work

1. **The push's run is not faster, and runs the suite twice** (`v1-e01`). Combining the parts'
   coverage data into one report would bring the dev chain to about 3 minutes and remove the one
   job that grows with the suite. It needs two artifact actions the repository does not use yet
   and a job that only a push exercises. Worth its own task once someone wants the dev chain
   shorter.
2. **Pick the next trims from a runner's durations, not this Mac's** (`v1-e01`, after
   `v1-e34-t22` merges). Every part now prints its 25 slowest tests. The three files reserved for
   `v1-e34-t22` hold about a quarter of the local test time.
3. **The help-rendering tests** (`v1-e01`): 6 s each alone, two of them, and the 16 tests they
   start already run in the suite. Whether one width would do is a question about what they
   assert, so it is the PM's.
4. **Sessions can run the suite by `--part`** instead of by named paths. `--part 1/4` to `4/4`
   took 28 to 49 s each here (137 s for all four in the last run), and unlike the path lists the parts are proven to be the whole
   selection. Working agreement 1 now says so; the PM's "two halves" ruling and the kickoff prompt
   may want the same words.
5. **`minversion = "8.3"` in `pyproject.toml`** is older than the pytest that loads a `-p` plugin
   from `pythonpath`. The lock pins 9.1.1, so nothing is wrong today. I did not check which
   release introduced the ordering, so I left the number alone.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

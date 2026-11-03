# Session report: v1-e41-t17-ci-parts-dealt-by-recorded-durations

| | |
|---|---|
| Task | `v1-e41-t17-ci-parts-dealt-by-recorded-durations` — CI deals whole test files to its parts by their recorded durations, so an ordinary task pull request's parts finish together |
| Spec | [`plan_specs/v1/e41-delivery-tooling-upkeep/t17-ci-parts-dealt-by-recorded-durations.yaml`](../../plan_specs/v1/e41-delivery-tooling-upkeep/t17-ci-parts-dealt-by-recorded-durations.yaml) |
| Epic / release | `v1-e41-delivery-tooling-upkeep` / `v1.8` |
| Branch | `task/v1-e41-t17-ci-parts-dealt-by-recorded-durations` |
| Session status | COMPLETE (the Goal stays `InProgress`: ac2 is the PM's measurement after the merge) |

## Summary

`ci.yml`'s test parts now run whole test files, dealt by the seconds each file took on dev's last
push run. Every push part times its files (`--record-durations`, a hook in `run_in_parts.py`). A new
`test-durations` job adds the parts up on dev's push run and saves the record in GitHub's Actions
cache. `test-selection` restores the newest record once and hands every part the same deal as a new
output, `files_to_parts`; the parts never touch the cache. A file with no record counts as the
record's median. A record that is missing, unreadable or stale (over 14 days old, or with no duration
for more than a quarter of the chosen files) deals test by test as before, with the reason in the job
summary, and never fails a run. The partition proof collects the parts under a deal and under none,
and deals the real collection both ways at every size from one part to eight.

**What the PM should read first:** one rule goes beyond the ruled floor (Deviation 1). A file heavier
than a part's share is spread test by test instead of dealt whole. On invented durations, plain
longest-first put the slowest part at 2.15 to 2.52 times the mean whenever the heaviest file was in
an affected set, and the spread rule kept it at 1.06 to 1.09. The same model says today's dealing is
already level (1.01 to 1.09). So whole files gain only by building module fixtures once, and how much
of the runners' time that is was not measured. ac2 will tell.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `ci-parts-dealt-by-recorded-durations` | Done | Skeleton and tests first, the red run, then the script, the plugin and ci.yml, mutants, the invented comparison, the docs. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: whole files dealt by recorded durations refreshed on dev's push run, a stated default for a new file, every selected test in exactly one part at every size, a missing or stale record falling back to today's dealing, by workflow and plugin tests shown failing first | PASS | **Red first**, against a skeleton with the real interfaces that dealt nothing by durations (`8028f76`): `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -n 4 -q --tb=line tests/scripts/test_parts_dealt_by_durations.py tests/scripts/test_ci_workflow_durations_recorded_and_restored.py tests/scripts/test_ci_workflow_test_job.py tests/scripts/test_ci_workflow_selection_once_and_no_queue.py tests/scripts/test_ci_workflow_test_selection.py tests/scripts/test_ci_workflow_parts_sized_to_the_selection.py` → `68 failed, 127 passed`. Every test in the two new files failed except two, which pin behaviour that already existed: no deal when no part runs, and an empty deal is the old dealing. One red failure was a bug in my test (a missing `mkdir` parent), fixed before green. **Green:** the node's command below. **Refreshed on dev's push run:** the `test-durations` job (`needs: test`, push to dev only, `continue-on-error`), pinned by `test_the_record_is_made_on_devs_push_run_alone_and_never_fails_it`; its combining step runs for real over two parts' files in `test_the_parts_files_added_up_land_where_the_save_takes_the_record_from`. **Default:** the record's median, hand-worked in `test_a_file_with_no_record_counts_as_the_median_of_the_record`. **Every size:** the partition proof (`pytest -n auto -m "partition_proof and not slow and not live" tests/scripts/test_ci_workflow_test_job.py`, run within the node's command) collects the whole selection's 8 parts under a deal by invented durations, and an affected set's own parts test by test plus its 8 under a deal. It checks each against the plugin's `parts_dealt`, and deals both real collections at sizes 1 to 8, under that size's deal and under none. **Fallback:** 12 unreadable or missing cases, the 14-day and quarter boundaries, and two guards, each read back from the summary. **Mutants:** 20, all caught at an assertion (below). |
| ac2: the slowest part's pytest step on three task pull requests after the merge, recorded by the PM against the three before it | NOT RUN | Needs runs on GitHub after the merge, read by the PM from the public API. dev's first push run after the merge has no record to restore, so it deals test by test and saves the first record; the pull requests after that deal by it. Per the invented comparison, that first record (made dealt test by test) gives the least level deal, and dev's next push corrects it. |
| Node `ci-parts-dealt-by-recorded-durations`: Dealt by duration tests pass (`uv run pytest tests/scripts -k "ci_workflow or test_selection or parts"`) | PASS | `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest tests/scripts -k "ci_workflow or test_selection or parts" -q -p no:cacheprovider` → `247 passed in 69.08s`, the partition proof included. Run with the venv's python under the 115-second limit rather than `uv run`, per agreement 10. |

### Mutants

Each was applied to the committed tree, run against the test files that cover it (with the partition
proof where it touches dealing), and restored with `git checkout HEAD --`. `git status` was clean after
every batch. No Hypothesis property is involved. The first versions of two of the PM's mutants were
weak or caught only by a crash in a test, and were redone (Decisions).

| Mutant | Caught by |
|---|---|
| PM: tests dealt rather than files (the plugin ignores the deal) | `test_a_part_collects_whole_files_as_the_deal_says_and_the_rest_test_by_test`, `test_a_part_records_only_the_files_it_ran`, `test_the_deal_and_the_old_dealing_agree_on_files_in_no_deal`, the whole-selection partition proof |
| PM: a part reading the cache itself (a restore step in `test`) | `test_only_the_selection_job_restores_the_record_and_no_part_reads_the_cache` and 2 more |
| PM: a missing record failing the run (the missing-file check gone and read errors not caught) | `test_a_missing_or_stale_record_still_runs_every_part_dealt_test_by_test[missing]` (the script exits 1), `…deals_test_by_test_and_says_why[missing]` |
| PM: a missing record failing the job (the restore step without `continue-on-error`) | `test_the_restore_comes_before_the_choice_and_never_fails_the_job` |
| PM: the fallback not reported (the script's summary empty) | 14 cases of `test_a_missing_or_unreadable_record_deals_test_by_test_and_says_why` and the stale tests |
| PM: the fallback not reported (the workflow's failed-script summary) | `test_a_selection_script_that_fails_deals_test_by_test_and_says_so` |
| PM: a file in two parts (a deal file kept by every part) | Both partition proofs (`[4, 4, 4] == [0, 0, 4]`), `test_a_part_collects_whole_files…`, `test_a_part_records_only_the_files_it_ran` |
| Heaviest part chosen instead of the lightest | `test_whole_files_go_heaviest_first_onto_the_part_that_holds_least` and 13 more |
| No file spread | `test_a_file_heavier_than_a_parts_share_is_dealt_test_by_test` and 2 more |
| The median of the chosen files, not of the record | `test_a_file_with_no_record_counts_as_the_median_of_the_record` (20.0 against 40.0), the summary test |
| No age limit | `test_a_record_fourteen_days_old_is_dealt_by_and_one_a_minute_older_is_stale`, the stale end-to-end case |
| The quarter boundary as `>=` | `test_a_quarter_of_the_files_unrecorded_is_dealt_by_and_more_is_stale` and 2 more |
| No empty-part guard | `test_a_part_left_with_no_recorded_file_deals_test_by_test` |
| Only the call phase recorded | `test_a_part_records_each_files_setup_call_and_teardown_seconds[0]` and `[2]` (0.109 s against at least 0.4 s) |
| `combine` without every part | `test_combine_writes_no_record_unless_every_part_timed_its_tests[a-part-missing]` |
| `combine` overwriting instead of adding | `test_combine_adds_every_parts_seconds…`, `test_the_parts_files_added_up_land_where_the_save_takes_the_record_from` |
| The whole selection dealt no files | `test_the_whole_selection_is_dealt_by_durations_every_test_file_once`, the whole-selection partition proof |
| A part not given the deal (`--files-to-parts` gone from the step) | `test_every_part_writes_down_the_deal_and_hands_it_to_pytest`, the whole-selection proof and 2 more |
| The record saved on every push, not dev's | `test_the_record_is_made_on_devs_push_run_alone_and_never_fails_it` |
| The record job able to fail the push run | the same test |

### Checks run before the report

| Command | Result |
|---|---|
| `.venv/bin/python scripts/hard_stop.py 115 uv run scripts/affected_tests.py --run` | "The whole selection is affected: .github/workflows/ci.yml is shared test ground." Nothing run; this pull request's `ci` runs the whole selection (agreement 10, the PM's brief). |
| `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -n auto -q tests/scripts` (the changed test directory) | `2542 passed in 88.39s` (load average 15 to 21). A first run of it together with the always-run list reached its 115-second limit at about 96% (load 8 to 11), so the two were run apart. |
| `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -n auto -q tests/architecture tests/specs tests/docs packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py packages/debate_cli/tests/test_container_factories.py` (the always-run list, and the docs tests) | `556 passed in 30.71s` |
| `uv run --frozen ruff format --check .` / `ruff check .` | `1884 files already formatted` / `All checks passed!` |
| `uv run --frozen pyright` (the configured tree, as the typecheck job runs it), and pyright over the changed scripts and tests, which that tree does not include | `0 errors, 0 warnings, 0 informations`, both |
| `uv run --frozen lint-imports` / `scripts/check_thin_handlers.py` | `Contracts: 20 kept, 0 broken.` / `OK: 72 … handlers within 25 statements` |
| `scripts/check_links.py`, `scripts/check_command_blocks.py`, `scripts/docs_index.py --check-descriptions` | pass; `All 68 indexed documents under docs/ have a description` |
| `scripts/actionlint.sh` | NOT RUN: it downloads actionlint from GitHub, and the brief allows no network call. Instead the venv's ShellCheck ran over the 12 `run:` blocks of `test-selection`, `test` and `test-durations`, with expressions stubbed: clean, after one fix (Decisions). The pull request's `workflow-lint` job runs actionlint. |
| `uv run scripts/validate_specs.py` | `OK: 585 files, 41 epics, 522 tasks, 22 releases` |

## Measurements

* **The files dealt for the whole selection.** `scripts/affected_tests.py`'s listing of test files
  under `testpaths` gives 669. One collection of the parts' selection
  (`--collect-only -n 0 -m "not slow and not live and not partition_proof"`, 41 s at load 5)
  collected 20,797 tests in 662 files. All 662 are in the listing. The 7 listed files with nothing
  collected hold only slow or live tests (the browser suites, `test_evidence_search_scale.py`, three
  smoke files, one cloud smoke file). They count at the median and collect nothing, about 1% of the
  files.
* **The expected slowest part on invented durations** (ruling 8), with the repository's own
  `parts_dealt` and `by_durations`. The suite is shaped like the costs page's figures: 654 files,
  about 20,000 tests, 2,600 s of worker time with fixtures built once, five heavy files of 300, 190,
  160, 160 and 140 s, and a lognormal long tail. Two shares of module-scoped fixtures, none and 10%,
  since the real share was never measured. Worker seconds of the slowest part, over 8 parts (2 for
  the small set), for deals that read a record made dealt whole (seed 17):

  | Selection | Fixtures | Test by test (before) | Whole files, longest first | Built: a file over a share spread |
  |---|---|---|---|---|
  | Whole selection, 654 files | none | 344 s (1.06 of the mean) | 325 s (1.00) | 325 s (1.00) |
  | Affected set, 301 files, holding the heaviest | none | 145 s (1.08) | 289 s (2.15) | 143 s (1.07) |
  | Affected set, 300 files, no heavy file | none | 105 s (1.06) | 99 s (1.00) | 99 s (1.00) |
  | Small affected set, 46 files, 2 parts | none | 83 s (1.02) | 82 s (1.00) | 82 s (1.00) |
  | Whole selection, 654 files | 10% | 567 s (1.05) | 325 s (1.00) | 325 s (1.00) |
  | Affected set, 301 files, holding the heaviest | 10% | 240 s (1.04) | 289 s (2.18) | 142 s (1.07) |
  | Affected set, 300 files, no heavy file | 10% | 182 s (1.04) | 95 s (1.00) | 95 s (1.00) |
  | Small affected set, 46 files, 2 parts | 10% | 100 s (1.01) | 84 s (1.00) | 84 s (1.00) |

  Over seeds 3, 17 and 29:
  * Test by test, the parts were 1.01 to 1.09 of the mean.
  * Longest-first alone, with the heaviest file in an affected set, was 2.15 to 2.52 of the mean;
    with that file spread, 1.06 to 1.09.
  * Spreading a file only just over its share costs a little: seed 3's whole selection gave 337 s
    against longest-first's 328 s.
  * The first deal, from a record made dealt test by test, is the least level. At 10% (seed 17) it
    was 1.21 to 1.45 of the mean, 444 s for the whole selection, still under today's 567 s.

  The model was a scratch script in this session's scratchpad and is not committed. Its method is
  written in `docs/process/ci-test-part-costs.md`.

## Files changed

* `scripts/ci_test_durations.py` (new): the record's format and checks, the deal (median default,
  spread files, longest-first), the reasons it falls back, its summary, and `combine` for the push
  run's parts.
* `scripts/ci_test_selection.py`: `--durations`, `test_files_to_deal` (the chosen files, or every
  test file under `testpaths` for the whole selection), `dealing`, the `files_to_parts` output and the
  deal's paragraph in the job summary.
* `tests/pytest_plugins/run_in_parts.py`: `--files-to-parts` (read and checked once at
  configuration), `parts_dealt` with a deal, `--record-durations` (a controller-only recorder).
* `.github/workflows/ci.yml`:
  * `test-selection` restores the record (`actions/cache/restore@v5`, `continue-on-error`), passes it
    to the script, and outputs `files_to_parts`.
  * Every part writes the deal down and passes `--files-to-parts=`.
  * Push parts pass `--record-durations=` and upload their file.
  * The new `test-durations` job runs on dev's push run (`actions/cache/save@v5`).
  * `scripts/ci_test_durations.py` joins the `partition_proof` filter, and the header and comments
    describe the change.
* `tests/scripts/`:
  * New: `test_parts_dealt_by_durations.py` (the script and the plugin, on invented durations) and
    `test_ci_workflow_durations_recorded_and_restored.py` (the workflow).
  * Changed: `test_ci_workflow_test_job.py` (the proof under both dealings, the push step's extra
    option and upload, `ci`'s needs), `test_ci_workflow_selection_once_and_no_queue.py` (the new
    output, the proof trigger, the push-only job), `test_ci_workflow_test_selection.py` (`run()` takes
    `durations` and returns the deal).
* `docs/process/working-agreements.md` (agreements 1 and 10) and `docs/process/ci-test-part-costs.md`
  (the record, the deal, the invented comparison).

## Deviations from the spec

* **A file heavier than a part's share is dealt test by test, not whole.** The PM's ruling set
  greedy longest-first as the floor and asked for anything better to come with numbers; the numbers
  are under Measurements. No deal of whole files can make a part lighter than its heaviest file, and
  in the invented affected sets that held the 300 s file, longest-first alone set the slowest part at
  2.15 to 2.52 times the mean. The rule costs nothing in the plugin: a file left out of the deal is
  dealt the old way. Removing it is one line in `by_durations` (no file spread) and the three tests
  that pin it; the PM rules on it below.
* **The node's command was run with the venv's python under `hard_stop.py`**, not `uv run`, per
  agreement 10.

## Decisions and assumptions

* **The Actions cache, not an artifact** (the PM's preference): a pull request into dev restores what
  dev saved with no token, no API call and no new permission, and a miss is just an empty result.
  Each save gets a key of its own (`test-durations-<run id>-<attempt>`), since a cache entry is never
  overwritten. The restore asks for `test-durations-newest`, which no save writes and which starts no
  saved key, with `restore-keys: test-durations-`, so the newest record comes back. A record is about
  40 KB.
* **Stale** is either measure the ruling offered, both applied: older than 14 days, or no duration
  for more than a quarter of the chosen files. Two more fallbacks are mine. If every chosen file is
  heavier than a part's share, nothing is left to deal whole. If a part would hold no file with a
  recorded time, it could collect no test, pytest's exit 5.
* **The record is complete or not saved.** `combine` refuses anything but parts 1 to N of one N, as
  the coverage job does. A missing part leaves the previous record in use, rather than one that
  knows that part's files only by the median.
* **The record never fails dev's push run.** The upload step and the `test-durations` job carry
  `continue-on-error`, and the recorder prints and carries on when it cannot write. A broken record
  must not hold the dev pre-release, which waits for the run's conclusion. A pull request's summary
  says which record its deal came from and when.
* **The deal is checked once in the plugin, at configuration.** A deal for another N, or naming a
  part outside 1 to N, is a usage error (exit 4). The script never writes one, so it can only be a
  fault, and following it could put a test in two parts or none. Durations themselves never reach
  the parts, so this cannot fail a run "because of the durations".
* **The options are one word each, `--files-to-parts=PATH` and `--record-durations=PATH`.** The
  partition proof caught the two-word form: pytest takes a separate word naming an existing file as
  a candidate for its rootdir. The runner's temp directory is outside the checkout, so a
  whole-selection part, which names no test path, would have found no `pyproject.toml` and refused
  the option. A comment in ci.yml and a test say why.
* **The failed-selection fallback writes no `files_to_parts`.** An output never written reads as
  empty, which already deals test by test. The extra `echo` was the fourth redirect to
  `$GITHUB_OUTPUT` in that block, which ShellCheck reports as SC2129 and actionlint would surface.
  The line was removed (agreement 8: indistinguishable from its absence), and the test reads the
  output with `.get(..., "")`.
* **Mutants redone.** My first "missing record fails the run" mutant still caught `OSError`, so it
  only changed the reason's wording. The redone mutant makes a missing record crash the script, and
  the end-to-end test catches that by its exit status. Two `continue-on-error` checks first caught
  their mutants only through a `KeyError` in the test, so they now read the key with `.get` and fail
  at the assertion.
* **The pin `@v5`** follows the repository's major-version tags. It could not be checked offline. This
  pull request's own run resolves `actions/cache/restore@v5` when `test-selection` starts, and
  `cache/save` is the same repository at the same tag. The deal on this pull request's run is test by
  test ("no durations record was restored"), since no record exists before the merge.
* **Recording happens on every push part, saving on dev's alone.** A push to `main` uploads a file
  nobody reads (kept one day). Promotions and main's push runs restore no record, because none is
  saved on main, so they deal test by test and say so.

### Open for the PM

Paste-ready for the PM:

> **v1-e41-t17 asks three things.**
>
> 1. **Keep spreading a file heavier than a part's share?** Options: (a) keep it, as built; (b) plain
>    longest-first, as the ruling's floor. Recommendation: (a). On invented durations, longest-first
>    alone put the slowest part at 2.15 to 2.52 times the mean whenever the 300 s file was in an
>    affected set (289 to 328 s against 127 to 141 s), and spreading kept it at 1.06 to 1.09. Its one
>    cost: a file just over its share is a little worse spread (337 s against 328 s, seed 3). (b) is
>    one line and three tests.
> 2. **Save a record on main as well?** Options: (a) dev only, as built and ruled; (b) also on push
>    to main. Recommendation: (a) for now. Promotions and main's push runs deal test by test and say
>    so, which is today's behaviour, and their speed is not budgeted. (b) is the job's `if:`. Main's
>    caches are the default branch's, which every branch can restore; the restore order is the pull
>    request's base first, but that order was not checked here.
> 3. **Commit the comparison script?** It was a scratch model. Recommendation: no; its method is in
>    the costs page, and ac2's real figures replace it. Say if you want it as
>    `scripts/compare_part_dealings.py` with a test.

## Operator follow-ups

None. No whole-selection run is handed over: this pull request changes `ci.yml`, so its own `ci`
runs the whole selection (the PM's brief). After the merge, the PM reads dev's push run: its
`test-durations` job should save a record. The next task pull request's `test-selection` summary
should then say "dealt whole test files … by the durations dev's push run recorded at …".

## Follow-up work

* **Measure how much of a part is module-fixture setup**, which the gain depends on. The invented
  figures range from a few percent (no such fixtures) to the slowest part almost halved (a tenth of
  the suite). Each push part's `--durations=25` already names the heaviest setups.
* **A part could collect only its own files.** Each part still collects the whole selection and
  keeps its share. With the deal, `test-selection` could hand each part only its files, cutting
  collection from about 8 s to about 1 s a part (the costs page's option 1). That needs a deal that
  covers every collected file, which the listing nearly does (662 of 662 collected files). E41 upkeep.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-03

**Notes:**

Built carefully, and honest about what it will buy: the invented model says today's test-by-test
dealing is already level, so the gain is module fixtures built once per file, which ac2 will measure.
That matches the PM's own reading of the worksteal dispatches (parts within 1.10 of the mean).

1. **ac1 passes.** Red first (68 failing against a skeleton with the real interfaces); 247 green with
   the partition proof, which now proves every size from one to eight under a deal and under none; 20
   mutants, the PM's seven among them, all caught at an assertion after two weak ones were redone.
2. **The PM read the workflow.** Only `test-selection` restores the record, once, with
   `continue-on-error`; the parts get the deal as an output and never read the cache; the record is
   saved only on dev's push run, in a job that cannot fail it; pull requests into dev can restore
   dev's cache and cannot write it. The one-word option forms, which the proof caught, are pinned by a
   test.
3. **Questions:** (1) (a), keep spreading a file heavier than a part's share; the numbers justify it
   and it costs nothing in the plugin. (2) (a), dev only. (3) No; the costs page holds the method and
   ac2 replaces the model.
4. **Deviation accepted** (the spread rule, with its numbers). **Decisions accepted**, including both
   stale measures, the complete-or-not-saved record, and the deal checked once at configuration.
5. **Follow-ups the PM files:** parts collecting only their own files (the costs page's option 1, now
   possible with a deal covering every collected file), with the module-fixture share measured
   first from the push parts' `--durations=25` (E41, p2).
6. **ac2 is the PM's:** dev's first push run after the merge saves the first record (from a test-by-test
   run, the least level deal); the PM reads its `test-durations` job, then the slowest part of three
   task pull requests against e06-t12's 255 s, e37-t03's 189 s and e07-t03's 280 s.
7. **Closing checks:** the affected set is the whole selection (ci.yml), left to `ci` (agreement 10);
   `tests/scripts` (2,542), the always-run list with the docs tests (556), ruff, pyright over the
   configured tree and the changed files, lint-imports, thin handlers, the links and the specs are
   clean. actionlint runs in this pull request's `workflow-lint` job.
8. **Merge:** `scripts/task pr --partial` once `ci` is green. The Goal stays `InProgress` until the PM
   records ac2.

# Session report: v1-e41-t18-each-part-collects-only-its-own-files

| | |
|---|---|
| Task | `v1-e41-t18-each-part-collects-only-its-own-files` — Each CI part collects only its own test files, after measuring what module fixtures cost |
| Spec | [`plan_specs/v1/e41-delivery-tooling-upkeep/t18-each-part-collects-only-its-own-files.yaml`](../../plan_specs/v1/e41-delivery-tooling-upkeep/t18-each-part-collects-only-its-own-files.yaml) |
| Epic / release | `v1-e41-delivery-tooling-upkeep` / `v1.8` |
| Branch | `task/v1-e41-t18-each-part-collects-only-its-own-files` |
| Session status | COMPLETE (the Goal stays `InProgress`: ac2 ends with the PM's reading of three task pull requests after the merge) |

## Summary

The measurements came first and are in `docs/process/ci-test-part-costs.md` (commit `48c8d3a`,
before any code). From the `--durations=25` of three runs the operator downloaded (dev's push of
`d84cf21`, dealt test by test; dev's push of `6db251b` and a dispatch on dev at `440f797`, dealt
whole), **no module- or class-scoped fixture reaches any part's 25 slowest entries**. Every heavy
setup there is function-scoped, so whole-file dealing builds none of them once. What it did change is
where they land: all of `tests/smoke/test_caselist_remove_smoke.py`'s now sit in one part, which is
the slowest (298 s on the dispatch, against 179–229 s). On the operator's Mac, each part spent 7.2–9.0
s collecting the whole selection, against 1.1–3.2 s for its own files. Runner logs can't time
collection, because pytest's output to a pipe is buffered.

Then `tests/pytest_plugins/run_in_parts.py` was changed so that under a deal a part never collects a
file the deal gives another part. Files a part's command names are trimmed when pytest is configured,
and files found walking `testpaths` are skipped in `pytest_ignore_collect`. A file the deal doesn't
name, or every file when there is no deal, is collected and dealt test by test as before. Each part
now prints how long it took to collect. On the Mac, under `-n 4`, a part's startup and collection fell
from 12.5–19.3 s to 3.9–10.8 s, and the partition proof's whole-selection test from 25.0 s to 14.7 s.
The tests were run red against a skeleton first, and 9 mutants were caught.

The Goal stays `InProgress`, because ac2 closes with the PM's reading of three task pull requests
after the merge. This PR's own run gives the like-for-like "after" for the slowest part: a
whole-selection pull request in 8 parts, dealt by dev's record, against the dispatch's 298 s. It's
under Operator follow-ups. Two things for the PM to look at first: the slowest part's cause, which
this task doesn't touch (Follow-up work 1), and a dev test that failed dev's push run (Follow-up
work 2).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `each-part-collects-only-its-own-files` | Done | Measured and recorded before the change (`48c8d3a`), tests red against a skeleton (`4d9e3f0`, `649e4a9`), implementation (`0d42dd9`), prose (`cd6e18d`), before and after (`2fb4cb6`). |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the module-fixture share measured from the push parts' durations and recorded in `docs/process/ci-test-part-costs.md` before the change | PASS | Section "What module fixtures cost, measured before v1-e41-t18", committed in `48c8d3a`, the first commit after the task's start and before any code. Sources: the operator's `gh run view --log` and `--json jobs` of runs 41563571482 (push of `d84cf21`, test by test), 41972928347 (push of `6db251b`, whole files) and 41975449095 (dispatch at `440f797`, whole files, no coverage). The `--durations=25` sections were parsed per part. Setups among a part's 25 slowest made up 4.3–7.0% of each part's worker time before t17, and 0–22.2% since, all of them function-scoped. No module- or class-scoped setup was above a part's 25th entry (3.5–12.4 s). Collection per part on the Mac: 7.2–9.0 s whole (`pytest --collect-only -n 0 --part K/8 --files-to-parts=…`), 1.1–3.2 s for own files named as paths with no code changed. |
| ac2, first half: each part collects only its dealt files, every selected test in exactly one part at every size, a missing deal falling back to today's collection, by workflow and plugin tests shown failing first | PASS | **Red** against a skeleton (HEAD's plugin plus a `collects` that always says yes, `4d9e3f0`): `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -n 4 -q --tb=line -p no:cacheprovider -m "not slow and not live" tests/scripts/test_parts_collect_only_their_own_files.py tests/scripts/test_ci_workflow_test_job.py` → `15 failed, 25 passed`, every failure at an assertion. The partition proof (the workflow test, which reads ci.yml's commands) failed on its new bound: `part 1 of 8 of the default selection collected 21547 tests to keep 2184: more than the 77 the markers leave out and the 0 in no deal`. The plugin tests failed on imports (`part 1 of 3 imported ['test_alpha.py', 'test_beta.py', 'test_gamma.py']`). One red failure was a bug in my test: a heavy file claimed spread at 2 parts, when by hand it is spread from 3 (`649e4a9`). After the fix, that test was re-run red and failed at its import check. The `-n 2` cases had not started workers (xdist starts none under `--collect-only`). They were changed to run tests for real, re-run red against the skeleton (5 failed at assertions), and then green. **Green:** the node's command below. **Every size:** `test_every_test_is_in_exactly_one_part_at_every_size_and_each_part_imports_only_its_own` collects all 36 parts of sizes 1 to 8 for real, under the deal `ci_test_durations.py` makes for each size. The partition proof deals the real suite at every size, and checks that each test's part collects its file. **Fallback:** `test_with_no_deal_every_part_imports_every_file_as_before[no-deal-given / an-empty-deal]`. |
| ac2, second half: the PM reads three task pull requests' slowest parts after the merge | NOT RUN | Needs runs on GitHub after the merge, read by the PM. The "before" on the same kind of run is the dispatch at `440f797`: 8 parts, whole selection, no coverage, dealt by dev's record; pytest step 298, 222, 198, 224, 179, 225, 229, 226 s, slowest 298 s. This pull request's own run is a whole-selection run of the same kind (Operator follow-ups). |
| Node `each-part-collects-only-its-own-files`: Own files only tests pass (`uv run pytest tests/scripts -k "ci_workflow or test_selection or parts"`) | PASS | `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest tests/scripts -k "ci_workflow or test_selection or parts" -p no:cacheprovider -q` → `265 passed, 5 warnings in 42.75s` (includes the partition proof). |

### Mutants

Ten mutants of the new rules in `run_in_parts.py`, each run against the tests that should catch
it. Nine fail at an assertion. The tenth was equivalent, so I removed the code behind it.

| Mutant | Caught by |
|---|---|
| A file in no deal collected by no part (`get(test_file) == part`) | 10 plugin tests: `part 1 of 3 imported ['test_beta.py']` |
| Every part collects every file but its own | 11 plugin tests |
| Named paths not trimmed | 8: `part 1 of 3 imported [all three]` |
| Files found walking a directory not skipped | 2 (the `walked` cases) |
| Node ids compared whole, not by their file | 2 (the `node-ids` cases) |
| Files named by their base name, not their repository path | the partition proof (the invented suite is flat, so only the real suite shows it): `part 1 of 8 of the selection given collected 404 tests to keep 72` |
| Only part 1 trims | 10: `part 2 of 3 imported [all three]` |
| A path outside the rootdir skipped rather than collected | survived at first; `test_a_file_outside_the_rootdir_is_collected_and_dealt_test_by_test` was added, and it then failed (`[[], [], []] == [['test_outside.py'], …]`) |
| No collection time under xdist | `test_a_part_says_how_long_it_took_to_collect[2]` |
| The timer's start reset at session start removed | equivalent (configuration and session start are milliseconds apart); the reset was removed from the code |

### Closing checks

* `uv run --frozen scripts/affected_tests.py` → "The whole selection is affected: .github/workflows/ci.yml is shared test ground." Per agreement 10 nothing more was run; the PR's CI runs it. Static scan for hidden cross-file dependencies (below): none found.
* `uv run --frozen ruff format --check .` → 1952 files already formatted. `uv run --frozen ruff check .` → All checks passed.
* `uv run --frozen pyright tests/pytest_plugins/run_in_parts.py tests/scripts/test_parts_collect_only_their_own_files.py tests/scripts/test_ci_workflow_test_job.py tests/scripts/test_parts_dealt_by_durations.py scripts/ci_test_selection.py` → 0 errors.
* `uv run --frozen lint-imports` → 20 kept, 0 broken. `uv run --frozen python scripts/check_thin_handlers.py` → OK.
* `uv run --frozen python scripts/check_command_blocks.py` → OK; `scripts/check_links.py` → OK (3574 links); `tests/architecture/test_single_interpreter_source.py` → 55 passed.
* `uv run scripts/validate_specs.py` → OK: 619 files, 41 epics, 556 tasks, 22 releases.
* actionlint was not run locally: `scripts/actionlint.sh` downloads its binary. The ci.yml change is two comments; this PR's `workflow-lint` job runs it.

## Files changed

* `tests/pytest_plugins/run_in_parts.py`: `collects`, the trimming of named paths in `pytest_configure`, `pytest_ignore_collect`, the collection-time line, and a header that names the part's own files.
* `tests/scripts/test_parts_collect_only_their_own_files.py` (new): plugin tests over an invented suite whose modules record that they were imported.
* `tests/scripts/test_ci_workflow_test_job.py`: the partition proof reads each part's count collected before deselection and bounds it, and checks at every size that a test's part collects its file.
* `tests/scripts/test_parts_dealt_by_durations.py`: `run_pytest_in` takes extra environment variables.
* `.github/workflows/ci.yml`: comments only (the header and the part's pytest step).
* `scripts/ci_test_selection.py`: docstring.
* `docs/process/working-agreements.md`: agreement 1's paragraph on parts.
* `docs/process/ci-test-part-costs.md`: the measurements before, and what changed with figures after; its index line.

## Deviations from the spec

1. **One deal for every part, not a list per part.** The spec says to "let `test-selection` hand
   each part only its own files". `test-selection` already hands every part the one deal, which
   names each file's part, and the part's plugin collects only its own files from it. A list per
   part would be a second copy of the same rule in ci.yml, and it could not hold the fallback: for
   the whole selection a part's command names directories, and a file the selection's list doesn't
   hold could be collected by no part. ci.yml's commands and outputs are unchanged. If the PM wants
   the per-part lists anyway, they can be added on top.
2. **A line in each part's summary saying how long it took to collect.** The spec doesn't ask for
   it. The brief asked for each part's collection time, and runner logs can't show it, so this is
   how the "after" gets measured on runners and how the PM can read it later. It changes no
   selection.
3. **The "before" for the slowest part is a dispatched run on dev, not a pull request.** None of the
   last fourteen task merges was a whole-selection pull request, while this one will be. The
   operator dispatched `ci` on dev (run 41975449095), which, like this PR's run, is the whole
   selection in 8 parts, dealt by dev's record, without coverage.

## Decisions and assumptions

* **Why two hooks.** pytest 9.1 doesn't ask `pytest_ignore_collect` about paths the command names
  (`session.isinitpath`), and an affected set reaches a part as files named in `@FILE`. So named
  paths are trimmed from `config.args` in `pytest_configure`. xdist's workers re-parse the
  invocation's arguments and run the same hook, so the controller, every worker and `-n 0` trim
  alike. A directory is never a file the deal names, so it stays.
* **What the proof bounds.** A part's tests collected minus those it keeps can be at most what the
  markers leave out of the whole selection plus the tests in files no deal names. Collecting the
  whole selection, a part leaves out seven eighths of the suite, which is why the old code failed the
  bound by about 19,000 tests.
* **A part whose named files all belong to other parts collects nothing** (exit 5), as it did before
  when it deselected all of them. The deal never leaves a part without a file of its own; the test
  pins that it collects nothing rather than the rootdir.
* **Hidden dependencies between test files.** Until now every worker imported every test module, so
  a test could lean on another file's import-time side effects without anyone knowing. A scan of
  every test file that imports a module from `scripts/` without putting `scripts/` on `sys.path`
  found three (`tests/docs/test_check_links.py`, `tests/specs/test_spec_index.py`,
  `tests/specs/test_validate_specs.py`), each covered by its own directory's conftest. The root
  conftest always loads. Dependencies through runtime state can only show up in a whole-selection
  run, which this PR's CI is.

## Operator follow-ups

1. **After this pull request's `ci` run finishes**, download its timings for the before/after on the
   same kind of run (read-only, about a minute). Where: the task worktree.

   ```bash
   cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e41-t18-each-part-collects-only-its-own-files
   run=$(gh run list --repo charlesclark2/debate-intelligence --workflow ci.yml --branch task/v1-e41-t18-each-part-collects-only-its-own-files --event pull_request --limit 1 --json databaseId --jq '.[0].databaseId')
   gh run view "${run}" --repo charlesclark2/debate-intelligence --json jobs --jq '.jobs[] | select(.name | startswith("test (")) | [.name, (.steps[] | select(.name | startswith("pytest")) | select(.conclusion == "success") | ((.completedAt | fromdate) - (.startedAt | fromdate)))] | @tsv'
   gh run view "${run}" --repo charlesclark2/debate-intelligence --log | grep -E "collected in [0-9.]+ s"
   ```

   Success looks like: eight `test (K)` lines, each with its pytest step's seconds, and eight
   `part K of 8 collected in … s, the last of 4 workers` lines. Compare the slowest step with the
   dispatch's 298 s (parts 179–298 s). The collection lines are the first runner measurement of a
   part's collection.

## Follow-up work

1. **The slowest part is the remove smoke file dealt whole** (E41, for the PM). Its function-scoped
   `installation`, `bucket` and `published` fixtures cost 11–15 s a test, 911 s of worker time on
   `6db251b`'s push against a 775 s share. It is dealt whole whenever its recorded time falls just
   under a share, and spread when just over, so the slowest part swings by about 70 s from one run
   to the next. Options: spread a file above some fraction of a share (half?), or make that file's
   setup cheaper (a module-scoped installation, if its tests allow it).
2. **`packages/debate_cli/tests/test_search_command.py::test_on_the_committed_profile_without_a_contact_email_crossref_names_the_public_pool_in_the_footer` is timing-dependent.**
   It failed dev's push run of `6db251b` (`[dev]`: expected 1 result, got 2). It passed on the
   dispatch at `440f797`, and failed locally on this branch (`[prod]`: expected 2, got 1). The count
   depends on how many CrossRef queries fit under the public pool's one query a second. The failed
   push saved no durations record (see 3). It belongs to the task that added it, `v1-e07-t13` or
   `v1-e08-t10`.
3. **One failing test costs dev its durations refresh.** A part that fails uploads no durations
   (the upload step runs only after a passing pytest step), and `test-durations` writes nothing
   without every part, so the next pull requests deal by an older record. That is t17's rule, which
   is safe. Whether a failed part's durations should still be uploaded is the PM's call.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-05

**Notes:**

Measured first, and the measurement changed the story: the module-fixture saving the spec expected is not
there, and the report says so plainly instead of claiming it.

1. **ac1 passes.** The costs page's measurement section is committed (`48c8d3a`) before any code: no
   module- or class-scoped setup reaches any part's 25 slowest entries on three runs, every heavy setup
   is function-scoped, and collection costs 7.2 to 9.0 s a part whole against 1.1 to 3.2 s for its own
   files.
2. **ac2's first half passes.** `collects` is one line, applied in both places pytest needs it (the
   named paths in `pytest_configure`, the walked files in `pytest_ignore_collect`), so the controller,
   every worker and `-n 0` agree. A file no deal names, a path outside the rootdir and a run with no
   deal are all collected as before; a part whose named files all belong elsewhere collects nothing
   rather than falling back to the rootdir, by test. Red against a skeleton (15 failed, each at an
   assertion), the one bad test owned and re-run red, the `-n 2` cases changed to start workers for
   real, and 9 of 10 mutants caught (the tenth equivalent, its code removed). The partition proof now
   deals the real suite at every size and bounds what each part collects.
3. **Deviations accepted.** (1) One deal that each part reads, not a list per part: the same rule
   once, and the only form that keeps the fallback for a whole-selection command naming directories.
   (2) The collection-time line: it is the only way a runner can measure collection, and it selects
   nothing. (3) The "before" is the dispatched whole-selection run on dev, the same kind of run as this
   pull request's.
4. **Hidden cross-file dependencies:** the static scan found three, each covered by its directory's
   conftest. Runtime-state dependencies show only in a whole-selection run, and this pull request's
   `ci` is one, so it is the test that matters: a failure there that passes when its file runs alone
   comes back to this task.
5. **Follow-up 1 is filed by the PM** (E41, p3): the remove smoke file decides the slowest part
   (function-scoped installation, bucket and published fixtures at 11 to 15 s a test). A proposal
   first: spread a file above a fraction of a share, or a module-scoped installation if its tests
   allow it.
6. **Follow-up 2 is filed by the PM** (E07, p2): the public-pool footer test from `v1-e07-t13` counts
   results that depend on the real clock under the public pool's pace, so it fails on some runs (dev's
   push of `6db251b`). It moves to an injected clock. If this pull request's `ci` fails on that test
   alone, re-run the failed job; it is not this task's code.
7. **Follow-up 3 is declined.** A failed part keeps uploading no durations: a failing run's timings
   are not a run's normal timings, and dealing by an older record is safe (t17's rule).
8. **Closing checks:** the affected set is the whole selection (ci.yml changed), so it is the pull
   request's `ci` (agreement 10); the node's command (265 passed), ruff, pyright on the changed files,
   lint-imports, thin handlers, command blocks, links and the specs are clean.
9. **Merge:** `scripts/task pr --partial` once `ci` is green. The Goal stays `InProgress` until the PM
   reads three task pull requests' slowest parts after the merge (ac2's second half). The operator's
   timing block runs after this pull request's `ci` finishes.

## Operator records (recorded by the PM, 2026-11-09)

Added by the PM. Nothing above is changed, and this section is not a review.

| Criterion | Was | Now | Record |
|---|---|---|---|
| ac2, second half: the PM reads three task pull requests' slowest parts after the merge | NOT RUN | PASS | 2026-11-08, three task pull requests' `ci` runs after the merge, read from the operator's output: the slowest pytest part 224 s, against 298 s for the whole-selection dispatch at 440f797 before this task |

Every criterion passes, so the Goal is `Succeeded`.

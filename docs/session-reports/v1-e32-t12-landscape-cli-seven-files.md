# Session report: v1-e32-t12-landscape-cli-seven-files

| | |
|---|---|
| Task | `v1-e32-t12-landscape-cli-seven-files` — The landscape command names the seven-file bundle and counts its trends and schools |
| Spec | [`plan_specs/v1/e32-argument-landscape/t12-landscape-cli-seven-files.yaml`](../../plan_specs/v1/e32-argument-landscape/t12-landscape-cli-seven-files.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t12-landscape-cli-seven-files` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> (the Goal stays `InProgress`: ac2 is validate-dev's run, which can only happen after the merge) |

## Summary

`debate-research landscape report` now names the seven files `v1-e32-t04` made, in its module
docstring, `--help`, human output and `--json`. Each file is marked circuit-wide or school view, read
from t04's `CIRCUIT_WIDE_FILES` and `SCHOOL_VIEW_FILES`, so an operator sees which two files name
schools before publishing. `--json` gains numbers only: the trend rows by label, the rows the team
floor held back, and the school view's school, team code and row counts, all taken from the run
service's result. Under the PM's amendment from `v1-e34-t32`'s ruling 4, which is now `ac3` in the
spec, the status line ends with the hook's own `FailedSyncRun.sentence()` when the latest sync run
failed or stopped, and `--json`'s `staleness.failed_run` holds the run id and the stage names or the
error class. Only the command's text and JSON changed: no bundle file, no file's contents and nothing
in `debate_core`. The phase stays `InProgress` because ac2 asks for validate-dev's run of the smoke
check, as with `v1-e32-t05`'s ac4. Look first at where `failed_run` sits (under `staleness`; see
Decisions) and at how the help text is built (`report.__doc__` set from the constants).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `cli-seven-files` (Landscape command names seven files) | Done | Docstring, help, human output and `--json` changed, the failed-run amendment added, command tests and smoke check updated |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: on the synthetic fixture, `--json` carries the seven files marked circuit-wide or school view, the trend rows by label, the rows held back and the school view's counts; the human output and `--help` name the seven files; tests shown failing first | PASS | Red at commit `488acf2`, before the command changed: `.venv/bin/python -m pytest packages/debate_cli/tests/test_landscape_command.py -p no:randomly -q` → `11 failed, 17 passed`. Each failed for the missing feature: `KeyError: 'bundle'`, `'trends'`, `'school_view'`, `'failed_run'`; the trend, school and file-split lines missing from the human output; the dry-run line not found; the seven files missing from `--help` and the docstring. Green at `e1b2200`: same file → `28 passed` |
| ac2: the landscape smoke check passes in the validate-dev recorded tier | PASS locally; NOT RUN in validate-dev | With the recorded tier's markers against this checkout's console script: `.venv/bin/python -m pytest tests/smoke/test_landscape_smoke.py -m "not live and not in_process"` → `2 passed in 4.14s`. Failing first: run with `landscape.py` from `488acf2` → `1 failed, 1 passed`, `KeyError: 'bundle'` at `test_landscape_smoke.py:75`; restored → `2 passed`. validate-dev runs it on the pre-release the merge builds, so that run can only happen after the merge |
| ac3 (PM amendment): with a synthetic run log whose latest run failed at a stage, or stopped before its stages, the status line carries `FailedSyncRun.sentence()` and `staleness.failed_run` holds the run id and the stage names or the error class; no school, path or error message appears; tests shown failing first | PASS | Red at `488acf2`: both failed-run tests failed. The report already printed `STALE: …` (the hook's verdict), but the line had no sentence and the JSON had no `failed_run`. Green at `e1b2200`: `test_a_run_that_failed_at_a_stage_prints_the_hooks_sentence_on_the_status_line` and `test_a_run_that_stopped_before_its_stages_names_its_error_class_and_never_its_message` pass. Each record's reason or message names the fixture's fictional school and a `.docx` path, and the tests assert that neither, nor the `HTTP 403` text, reaches stdout in either mode |
| Node `cli-seven-files`: `uv run pytest packages/debate_cli/tests/test_landscape_command.py` | PASS | `28 passed` (above) |

## Files changed

* `packages/debate_cli/src/debate_cli/commands/landscape.py`: the module docstring gains "The bundle"
  and "A stale report" sections. The help text, `REPORT_HELP`, is built from t04's constants. `--json`
  gains `bundle`, `trends`, `school_view` and `staleness.failed_run`, and the human output gains the
  trend line, the school-view line, the split file list and the hook's sentence.
* `packages/debate_cli/tests/test_landscape_command.py`: eleven new tests (seven files, constants,
  trends, school view, first window, human output, dry run, help, docstring, and two failed-run
  cases), plus a `failed_run is None` assertion on a current report. The counts are worked out by
  hand in a comment above them.
* `tests/smoke/test_landscape_smoke.py`, `tests/smoke/README.md`: the smoke check asserts the file
  marks, the trend and school-view counts and `failed_run: null`. Its README row said "its three
  files" and now says seven.
* `plan_specs/v1/e32-argument-landscape/t12-landscape-cli-seven-files.yaml`: the PM's amendment, as
  a comment above a new `ac3` (checked in the parsed YAML: the comment is not in the description).

## Deviations from the spec

* `ac3` was added to the spec from the PM's context of 2026-10-24 (the failed-run amendment), as the
  PM asked. Nothing else in the spec changed.

## Decisions and assumptions

* **`failed_run` sits under `staleness`** in `--json` (`data.staleness.failed_run`), beside the
  other facts the hook decided staleness on, and not at the top level. It is `null` for a current
  report. Its keys are `FailedSyncRun`'s own: `run_id`, `stages`, `stopped_before_stages` and
  `error_class`. `stopped_before_stages` is included so a reader can tell "failed, no stage named"
  from "stopped before its stages".
* **The JSON names.** `bundle` is a list of `{name, path, view}` in upload order (`BUNDLE_FILES`),
  where `view` is `circuit_wide` or `school_view`. `trends` is `{rows_by_label: {NEW, RISING,
  FALLING, STEADY}, held_back_by_team_floor}`, and `school_view` is `{schools, team_codes, rows}`.
  `paths.files` is unchanged, so nothing that reads it breaks. Nothing outside the tests reads this
  JSON today.
* **Counts come from the result, not recomputed.** `held_back`, `schools` and `teams` are the domain
  models' own properties. A label's count is `len(trends.labelled(label))` and the row count is
  `len(schools.rows)`, which count rows the result already holds. Adding count properties to
  `debate_core` would have gone outside this task's packages.
* **A file in neither of t04's lists is a `KeyError`**, not a guess at its view. A new bundle file
  then fails every run of the command until someone says which view it is.
* **`--help` comes from the constants.** `report.__doc__` is assigned `REPORT_HELP` after the
  function, because a docstring literal cannot read the constants. The alternative was
  `command("report", help=...)` in `debate_cli/commands/__init__.py`, a hub module whose edit widens
  the affected set. The first paragraph stays the one-line summary that the `landscape` group's
  listing shows.
* **The module docstring names the files in prose**, since a docstring is a literal. A test holds it
  to `BUNDLE_FILES`: each name must appear and the old four-file sentence must not.
* **The trend and school counts were worked out by hand** from the fixture table (agreement 6) and
  match the run: 4 STEADY and 1 held back (States CP, down 100 points, read by one team against a
  floor of three), and 3 schools, 3 team codes, 7 rows. A first-window case at 2026-09-08 (4 NEW, 0
  held back, 2 schools, 2 team codes, 4 rows) checks the other branch.

A human run on the fixture, today's clock (STALE only because the fixture's snapshot is 40 days old;
paths shortened):

```text
Trends: NEW 0, RISING 0, FALLING 0, STEADY 4; 1 held back by the team floor.
School view: 3 school(s), 3 team code(s), 7 row(s).
STALE: newest snapshot 2026-09-15, 40 day(s) old, 0 archive(s) awaiting download.
Wrote 7 files to <data dir>/reports/landscape/synthetic26/2026-09-15:
  circuit-wide: positions.csv, top_cards.csv, impact_cards.csv, trends.csv, report.md
  school view, naming schools and team codes: schools.csv, schools.md
```

## Checks run before the report

* Affected set: `uv run scripts/affected_tests.py` → `152 of 454 test files (33.5%) chosen`. I ran it
  as `perl -e 'alarm 118; exec @ARGV' .venv/bin/python -m pytest -n auto -m "not slow and not live"
  <the 152 files>`. The alarm stopped it at 1:58, about 89% through, with no failure or error up to
  that point, and no workers were left running. Over two minutes, so under agreement 10 it is left
  to the pull request's `ci` check, with no hand-off.
* Within the limit, the changed package's tests and the always-run list:
  `.venv/bin/python -m pytest -n auto -m "not slow and not live" packages/debate_cli/tests tests/architecture tests/specs tests/smoke/test_landscape_smoke.py`
  → `1204 passed in 37.63s`.
* `uv run ruff format --check .` → `1254 files already formatted`. `uv run ruff check .` → `All checks
  passed!`
* `uv run pyright packages/debate_cli tests/smoke/test_landscape_smoke.py` → `0 errors, 0 warnings`.
* `uv run lint-imports` → `16 kept, 0 broken`. `uv run scripts/check_thin_handlers.py` → `OK: 50 CLI
  command and API route handlers within 25 statements`.
* `uv run scripts/validate_specs.py` → `OK: 437 files, 40 epics, 375 tasks, 22 releases`.
* `uv run scripts/check_command_blocks.py` → OK.

## Operator follow-ups

None. ac2's validate-dev run happens on its own after the merge, and the PM records it, as with
`v1-e32-t05`'s ac4.

## Follow-up work

* The running sessions: this branch touches only the landscape command, its tests, the smoke check
  and this task's spec. It does not touch `v1-e32-t11`'s report sections or `v1-e40-t04`'s run and
  removal code. If `v1-e32-t11` also adds keys to `run_summary` or lines to `_display`, a sync will
  conflict in `landscape.py`. Both sides should be kept: the additions are independent dictionary
  keys and list items.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-24

**Notes:**

A tidy, well-bounded change.
1. **ac1 and ac3 pass, red first.**
   * 11 failures at `488acf2`, each for the missing feature.
   * The seven files come from t04's constants rather than a copy, and a file in neither list is a
     `KeyError`, not a guess.
   * The counts come from the run's result, and the hand-worked fixture counts match.
   * The failed-run sentence is the hook's own. The tests plant a fictional school, a `.docx` path
     and an `HTTP 403` message in the records, and show none of them reaches stdout.
2. **Accepted as made:**
   * `failed_run` under `staleness`, with `FailedSyncRun`'s own keys, `stopped_before_stages`
     included;
   * `paths.files` left unchanged;
   * `--help` built from the constants by assigning `report.__doc__`, which keeps the hub module out
     of the affected set;
   * the docstring held to `BUNDLE_FILES` by a test;
   * the PM's amendment written as `ac3`, the only change to the spec.
3. **ac2 is validate-dev's run after the merge,** as with v1-e32-t05's ac4. It merges `--partial`
   with the phase `InProgress`, and the PM records the run and sets the Goal `Succeeded` in a PM
   batch.
4. **The affected set** stopped at its alarm about 89% through with no failure, so it is left to
   the PR's `ci` under agreement 10. The changed package and the always-run list passed (1,204).
5. **The note about `v1-e32-t11`** is right. If its sync conflicts in `landscape.py`, keep both
   sides.

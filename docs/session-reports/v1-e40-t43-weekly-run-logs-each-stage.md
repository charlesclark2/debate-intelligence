# Session report: v1-e40-t43-weekly-run-logs-each-stage

| | |
|---|---|
| Task | `v1-e40-t43-weekly-run-logs-each-stage` — The weekly run logs each stage as it starts and ends, so a run can be read while it runs |
| Spec | [`plan_specs/v1/e40-cloud-caselist-run/t43-weekly-run-logs-each-stage.yaml`](../../plan_specs/v1/e40-cloud-caselist-run/t43-weekly-run-logs-each-stage.yaml) |
| Epic / release | `v1-e40-cloud-caselist-run` / `v1.8` |
| Branch | `task/v1-e40-t43-weekly-run-logs-each-stage` |
| Session status | COMPLETE |

## Summary

`caselist pull`, the weekly run, now writes a line to stderr as each step starts and as it ends:
in bucket mode the restore, then every stage it times (select, download, import, publish, parse,
search index, landscape when one is installed, report, retention), then the bundle's two saves and
the state files' save. During the parse it writes a progress line every five minutes with the
sources done and left and the caselists done and left. Every line is `v1-e40-t32`'s, written by
t32's own code, which this task moved into two shared modules (`step_lines.py` in each package)
rather than copied; a backfile import's lines are unchanged. Lines hold step names and counts only.
The run's result is still the one line on stdout, the last line written, and, by test against the
`RunsRecorded` pattern read out of `alerts.tf`, the only line that filter counts. The runbook's
Step 8 gains "How far it has got". **Look first at:** Decisions 1 (how the PM's stage list maps onto
the run's steps) and 6 (two existing log reads that would have miscounted the new lines, both
fixed). The lines reach the cloud only in an image built after this merges (Follow-up 1).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `weekly-run-logs-each-stage` (Stage lines) | Done | t32's code moved alone first (`428c8d5`), then the stage lines; red run against a skeleton that logs nothing, then green; ten mutants, all caught at assertions |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: each stage of the weekly run logs its start and end with seconds and counts, the parse logs its progress, and no line names a school, team, file or path, by tests shown failing first | PASS | Red run (below): 20 of the 21 new tests fail against a skeleton that logs nothing. Green: `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -q -n auto packages/debate_core/tests/application/caselist/test_pull_stage_lines.py packages/debate_cli/tests/bucket_mode/test_pull_stage_lines.py tests/docs/test_weekly_run_log_reads.py <t32's three step-line files> packages/debate_cli/tests/bucket_mode/test_parse_owed.py` → `85 passed in 34.76s` |
| ac2: the final record line is unchanged and is still the only line the RunsRecorded metric filter's pattern matches, by test, and the runbook reads the last stage line | PASS | `packages/debate_cli/tests/bucket_mode/test_pull_stage_lines.py`: the pattern is read out of `infrastructure/modules/caselist_run/alerts.tf` and evaluated over every line a real bucket-mode run wrote, in the order written: exactly one counted, the result, which is the last line, for a run that succeeds and for one whose download fails; none for a dry run. The result's top-level keys and its `data` (or `error.details`) keys are pinned whole, written out at the start commit. `tests/docs/test_weekly_run_log_reads.py` runs Step 8's new read with `sh` over a synthetic log. Mutant 1 (a step line carrying a `run_record`) is caught by all three filter tests. Infrastructure untouched; the filter needed no change |
| Node: Stage lines tests pass (`uv run pytest packages/debate_core/tests packages/debate_cli/tests -k "pull and (stage or step)"`) | PASS | `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -q -n auto packages/debate_core/tests packages/debate_cli/tests -k "pull and (stage or step)"` → `100 passed in 23.28s` |

**What each test holds**, by file:

* `packages/debate_core/tests/application/caselist/test_pull_stage_lines.py` (7 tests, the run
  service over `test_inbox_retention.py`'s installation: real importers, publisher, status and parse
  pipeline against moto). The order of start and end lines, one each per stage, with no landscape
  lines when none is installed and both when one is. Each end line's seconds equal its
  `stage_times` entry and are above zero on a ticking clock; its memory is the stand-in reader's; a
  start line has neither. Counts hand-written from the fixture's table where it fixes them (2
  weeklies seen and wanted; the archives' byte sizes downloaded and freed; 2 snapshots and 2
  manifests; the parse's nine integers `1, 1, 6, 0, 2, 1, 4, 9, 0`; 2 snapshots confirmed) and equal
  to the summary's elsewhere. Outcomes `completed`, and `skipped` for the unwired search index.
  Progress worked by hand: two caselists of ten sources at 100 s against 300 s give lines at 0, 3,
  6, 9, 10 done (0, 300, 600, 900, 1000 s) each, with `caselists_done`/`caselists_left` 0/2 then
  1/1, all between the parse's start and end. A stage that fails without raising (the failure rate)
  ends `step_ended` with `failed` and the run goes on; one that raises (a cancellation, as SIGTERM
  gives) ends `step_failed` with its seconds and memory, and nothing starts after it. A dry run logs
  select and retention; `--publish-pending` logs publish and report. No line's repr holds a fixture
  school, team, tournament, the caselist, the camp, `.docx`, `.zip`, the temporary directory, `/` or
  `\`; every count is an `int`.
* `packages/debate_cli/tests/bucket_mode/test_pull_stage_lines.py` (8 tests, the real command,
  composition root and `BucketRun` over moto and the stand-in site, week three in bucket mode after
  the seed). The whole order, `restore` to `save_state_files`, hand-written; the progress lines'
  counts (one new source); the restore's counts (6 state files, the rest equal to the details); the
  parse's counts equal to the result's; memory on every end and progress line. Nothing on stderr
  holds a fixture name, the caselist, `.docx`, `.zip`, the data directory, `/` or `\`. On a
  terminal each step is a sentence. The filter tests above, and a test of the filter reader itself
  against hand-written lines: a recorded success and failure match; a dry run's result, a backfile
  import's, a non-string `run_id`, a step line and a sentence do not; a pattern mixing `&&` and `||`
  without parentheses, or using `>`, is refused rather than read.
* `tests/docs/test_weekly_run_log_reads.py` (6 tests): Step 8's "How far it has got" prints the last
  step line's event, step, seconds, outcome, counts and memory, passes over a result after it, and
  with a `DEBATE_` variable set prints its STOP line and never calls the stand-in `aws`. Step 7's
  counts block prints the result's counts once, not the select line's `"archives_wanted"`. The
  cutover's summary check, run as Python over a `filter-log-events` file, finds 1 summary line among
  step lines. The new read sits after Step 8's "Watch it" and before "Its record".

**Red run**, before the mutants: the implementation committed, then a skeleton that logs nothing
(`_RunTally.on_line` always `say_nothing` and `run_pull`'s `emit` the same, so no stage, restore,
save or progress line is written), and both runbooks at the start commit (`3d86209`).
`.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -q -n 0 -p no:cacheprovider --tb=line <the three new test files>`
→ `20 failed, 1 passed in 31.45s`. The one that passes is the filter reader's own test, which reads
no run and which only a broken reader can fail. Every failure is an assertion except one
`ValueError` in the runbook-order test, then changed to assert first and shown failing at its
assertion (`AssertionError: Step 8 reads the last step line`). Two crashes in the first red run
(`KeyError`, `IndexError`) were turned into assertions the same way before this run. Restored with
`git checkout HEAD --`.

**Mutants** (agreement 10: the module the logic lives in, the new tests only, ten). Each applied as
a one-line change, run against the 21 new tests, restored with `git checkout HEAD -- packages`:

| Mutant | Caught by (at an assertion) | Result |
|---|---|---|
| 1. Every step line carries `"run_record": {"run_id": …}` | the three filter tests (`counted(result) == [result_line]`, `== []`) and the start-line shape | 4 failed, 17 passed |
| 2. The caselist's name in each progress line's step (`parse <slug>`) | the order tests and both names tests | 4 failed, 17 passed |
| 3. No restore line | the CLI order, sentence, names (line count), filter and dry-run tests | 6 failed, 15 passed |
| 4. A stage that raised ends `step_ended` | `test_a_stage_that_raises_ends_step_failed…` | 1 failed, 20 passed |
| 5. `caselists_done` one too many | the core progress test and the CLI progress counts | 2 failed, 19 passed |
| 6. Step lines written to stdout | the CLI tests' stderr shape, and the two runbook-read tests whose step lines come from the renderer | 8 failed, 13 passed |
| 7. No outcome on an end line | the core order, failed-stage and landscape tests; the CLI end-line, sentence and failed-run tests | 6 failed, 15 passed |
| 8. Landscape lines with no landscape installed | the core order, landscape and names tests; the CLI order, names and filter tests | 6 failed, 15 passed |
| 9. No `save_state_files` line | the CLI order, sentence, names and filter tests | 4 failed, 17 passed |
| 10. Every end line's counts empty | the core order, landscape, dry-run and failed-stage tests; the CLI end-line and sentence tests | 6 failed, 15 passed |

Mutants 3 and 7 also crashed two CLI lines (an unpacking, an `["outcome"]` lookup), on top of their
assertion catches; both lines now assert first (`ee907bd`).

**The existing suites this touches**, after the last code change:

* t32's own tests after the move alone (`428c8d5`): step lines, the import command, its runbook
  reads and `test_caselist_parse.py` → `103 passed in 23.71s`.
* `packages/debate_core/tests/application/caselist` → `1867 passed in 58.91s`.
* `packages/debate_core/tests/application/test_caselist_sync.py`, `…_full_archive.py`,
  `…_index_stage.py`, `packages/debate_cli/tests/test_pull_refused_before_the_bucket_is_built.py` →
  `125 passed in 4.23s`.
* `packages/debate_cli/tests/bucket_mode` → `220 passed in 95.10s` without `test_parse_owed.py` and
  the import tests, which ran apart (`14 passed`, and in the 85 above).
* The always-run list (`tests/architecture/`, `tests/specs/`, `test_app.py`,
  `test_help_rendering.py`, `test_container_factories.py`), `tests/docs`,
  `packages/debate_cli/tests/commands`, `test_output.py`, `test_caselist_parse.py` →
  `1253 passed in 34.36s`.
* `.venv/bin/ruff format --check packages tests scripts` → `1420 files already formatted`;
  `.venv/bin/ruff check packages tests scripts` → `All checks passed!`
* `.venv/bin/pyright packages/debate_core packages/debate_cli tests/docs/test_weekly_run_log_reads.py` → `0 errors, 0 warnings, 0 informations`
* `.venv/bin/lint-imports` → `Contracts: 20 kept, 0 broken.`
* `scripts/check_thin_handlers.py` → `OK: 72 CLI command and API route handlers within 25 statements`;
  `scripts/docs_index.py --check-descriptions` → `All 68 indexed documents under docs/ have a description`;
  `scripts/check_links.py` → `OK: 3599 relative links and anchors in 610 Markdown files`;
  `scripts/check_command_blocks.py --base origin/dev` → OK.
* `uv run scripts/validate_specs.py` → `OK: 629 files, 41 epics, 566 tasks, 22 releases`
* **The affected set:** `uv run scripts/affected_tests.py` → `336 of 702 test files (47.9%) chosen
  in 16.3 s from 23 changed files`. `caselist_sync.py` and `output.py`'s neighbours reach most of the
  CLI and caselist suites, as t32's 305 did, so it is well over two minutes, and under agreement 10
  it is left to the pull request's `ci`. The runs above are what I ran within the limit.
* No smoke check changed: the smoke suite reads a `--json` run's stdout alone
  (`installed_build.py`'s `envelope()`), which this task leaves as it was.

## Files changed

* `packages/debate_core/src/debate_core/application/caselist/step_lines.py` (new): t32's
  `StepEvent`, `StepLine`, `ParseProgress` and `PARSE_PROGRESS_INTERVAL_SECONDS`, moved, plus
  `logged_step` (t32's `_step` without its report), `SourceProgress`, `say_nothing`. `StepLine` gains
  an optional `outcome`; `ParseProgress` optional extra counts (`also`). A backfile line is unchanged.
* `…/caselist/backfile_import.py`: uses and re-exports the above; `_step` is `logged_step` plus the
  report's step seconds.
* `…/application/caselist_sync.py`: `run`/`publish_pending(on_line=)`; `_timed` tells each stage's
  start and end; `_stage_counts`; the parse loop hands each caselist a `ParseProgress`; the
  after-publish bundle save is a step; `run_pull(on_line=, monotonic=, memory=)` tells the restore,
  the after-run bundle save and the state files' save; `RESTORE_STEP`, `SAVE_BUNDLE_STEP`,
  `SAVE_STATE_FILES_STEP`; "What it logs as it goes" in the module docstring.
* `…/application/caselist_pull_parse.py` and the `CaselistParseStage` protocol:
  `parse_new_sources(caselist, *, progress=None)`.
* `packages/debate_cli/src/debate_cli/step_lines.py` (new): t32's renderer, moved; the sentence
  takes the command's name; `"outcome"` written when there is one.
* `…/commands/caselist_backfile.py`: uses it. `…/commands/caselist_pull.py`: passes `on_line`; a
  docstring section.
* `docs/runbooks/caselist-cloud-run.md`: Step 8's "How far it has got"; Step 7's counts block skips
  step lines; "A failed or stopped run" points at the new read.
  `docs/runbooks/caselist-cutover.md`: the summary-line check skips step lines.
* Tests: the three new files above; `test_inbox_retention.py`'s installation takes a clock, a memory
  reader and a landscape stage; the eight parse-stage fakes and `test_parse_owed.py`'s wrapper take
  `progress`.
* `plan_specs/…/t43-weekly-run-logs-each-stage.yaml`: the phase.

## Deviations from the spec

None. Decision 1 is the one place where the spec's words needed reading.

## Decisions and assumptions

1. **The PM's stage list against the run's steps.** The spec lists "restore, select, download,
   import, parse, upload, publish, and the landscape stage". The run has no stages named upload,
   and its publish comes before its parse. I logged every step the run carries out, under the names
   it already has: `restore`; the nine `SyncStage`s in their order, `publish` being the sources'
   and manifests' upload and `parse` including the parsed store's publish per caselist; and the
   bucket-mode saves, `save_bundle` (after the publish stage and after the run) and
   `save_state_files` (at the end), which are the run's uploads of its state. So "upload" is
   `publish` and the two saves, and nothing in the list is left without a line. Search index,
   report and retention log too: a hang in any of them is as unreadable as one in the parse. The
   monitor's publish of the run record, between the last bundle save and the state files' save,
   has no line of its own (Follow-up 3).
2. **Reuse, not a copy.** t32's classes and renderer moved to `step_lines.py` in each package,
   re-exported from where they were, and the move was committed alone (`428c8d5`) with t32's tests
   passing on it, so its diff shows nothing changed. The weekly run's stage lines come from
   `_timed`, which already timed each stage for `stage_times` (`v1-e40-t03`): an end line's seconds
   and memory are that entry's, read once, so the line and the summary cannot disagree.
3. **The same line shape as t32's**, `"event"` and `"step"`, with `"step"` holding a stage's name:
   one reader for both commands' logs, and the runbook's reads differ only in `"command"`. Pull's
   end lines add `"outcome"` (`completed`, `failed`, `pending`, `skipped`): a weekly stage that
   fails is recorded and the run goes on, so its line ends `step_ended` with `failed`;
   `step_failed` keeps t32's meaning, the step raised (a SIGTERM's cancellation, an expired token).
4. **Counts per stage** (`_stage_counts`), under the summary's own names: select
   `archives_seen`, `archives_wanted`, `archives_deferred`, `openev_seen`; download
   `archives_downloaded`, `openev_downloaded`, `downloaded_bytes` (files already in the inbox not
   counted); import `snapshots_imported`, `files_imported`, `files_duplicate`, `files_skipped`,
   `blobs_stored`, `held_by_request` (summed); publish `objects_published`, `manifests_published`,
   `pending_publish`; parse the summary's nine integers; search index `documents`, `removed`;
   landscape `reports_written`; report `snapshots_confirmed`; retention `files_removed`,
   `files_kept`, `bytes_freed`; restore `state_files`, `parsed_objects`, `parsed_bytes`,
   `parsed_kept`. The saves carry no counts. Start lines carry `"counts": {}` and no memory, as t32's.
5. **Progress per caselist.** The parse plans one caselist at a time, so the run cannot know the
   total sources before it starts. Each caselist gets t32's progress (a line at 0 once it knows its
   sources, then every five minutes, then one at its last source) and each line also carries
   `caselists_done` and `caselists_left`, counts and never the caselist's name. Its clock is the
   run's (`self._clock().timestamp()`), so a test moves it.
6. **Two existing log reads would have miscounted the new lines**, so both changed. Step 7's
   rehearsal counts block (`caselist-cloud-run.md`) grepped every `caselist pull` line for
   `"archives_wanted"`, which the select line now carries too; it now drops lines with an
   `"event"`, as t32 did for the import's counts. `caselist-cutover.md`'s "Its log" check counted
   every event with `"command": "caselist pull"` as a summary line and stops on any count but 1; it
   would have printed `found: 27` for a run like the CLI test's (26 step lines and the result). It
   now skips step lines. Both are tested over synthetic logs.
7. **Stderr, flushed per line** (t32's `event_line`), so stdout keeps one result and the result is
   written after every step line: `run_pull` returns only after the state files' save, and the CLI
   then writes the result. The CLI test reads Click's combined output, in the order written, to
   hold that.
8. **The landscape stage** is timed as before whether or not a service is installed, so
   `stage_times` is unchanged, but it logs only when one is (the PM's "when installed").
9. **The restore's and the saves' seconds** come from `time.monotonic` in `run_pull` (injectable),
   the stages' from the run's clock, as `stage_times` has them.
10. **The new runbook read has a `DEBATE_` guard**, as asked, though it runs no `debate-research`,
    and its window is six hours, the run's deadline, so the same block reads a run that stopped. A
    test runs it with a variable set and shows `aws` is never called.
11. **On the Mac.** A pull on a terminal prints each step as a sentence on stderr; the launchd
    agent, `--json`, adds about 26 JSON lines a run to `caselist-sync.err.log`, which nothing parses.

## Operator follow-ups

None required. One optional read, for the PM to decide on: ac2 is held against this repository's
reader of CloudWatch's filter syntax. AWS's own matcher can confirm it in seconds, read-only, as
`v1-e40-t05`'s check G did for EventBridge. It asks CloudWatch to test the `RunsRecorded` pattern
against a step line, a recorded success and a recorded failure.

**Operator command** (expected runtime seconds)
Where: your Mac, anywhere
```bash
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set in this shell; unset it and paste again"; else aws logs test-metric-filter --profile debate-admin --region us-east-1 --filter-pattern '{ ($.command = "caselist pull") && (($.data.run_record.run_id = "*") || ($.error.details.run_record.run_id = "*")) }' --log-event-messages '{"schema_version": 1, "command": "caselist pull", "event": "step_ended", "data": {"step": "save_state_files", "seconds": 1.2, "counts": {}}}' '{"schema_version": 1, "status": "ok", "command": "caselist pull", "data": {"run_id": "20261111T090000Z", "run_record": {"run_id": "20261111T090000Z"}}, "error": null}' '{"schema_version": 1, "status": "error", "command": "caselist pull", "data": null, "error": {"code": "CASELIST_PULL_INCOMPLETE", "details": {"run_record": {"run_id": "20261111T090000Z"}}}}' --query 'matches[].eventNumber' --output text; fi
```
Success looks like `2	3`: the two results match and the step line, event 1, does not. A `1`
in the output means CloudWatch counts step lines, and goes to the PM before the image is built.

## Follow-up work

1. **The lines exist only in an image built after this merges.** If the docx-9 run image built this
   week carries this task, the run of 2026-11-11 is the first to log its steps; otherwise the first
   run on a later image. Until then Step 8's read prints nothing, and the runbook says so.
2. **The affected set** (336 files) is the pull request's `ci`, under agreement 10. Its first run
   on PR #843, run 42107028553, was red from one test outside this task and nothing else: test part
   7, 1 failed and 891 passed, the failure
   `packages/debate_cli/tests/test_search_command.py::test_on_the_committed_profile_without_a_contact_email_crossref_names_the_public_pool_in_the_footer[prod]`
   (footer `2 results from 12 queries` where the test expects 1). The test (`v1-e07-t13`, #829)
   ran Crossref's public-pool pacer on the wall clock and is timing-dependent: dev's own push runs
   failed on it 4 times in 5 on 2026-11-05. This branch changes nothing in search, Crossref or
   discovery; the affected-test selection reached the test from the caselist changes. The fix is
   `v1-e32-t49`'s commit def4453 (PR #840), which the PM ruled on 2026-11-05, so this branch leaves
   the test alone. Once #840 has merged, the operator runs `scripts/task sync
   v1-e40-t43-weekly-run-logs-each-stage` and CI runs the fixed test. If it still fails after that,
   the clock is not the cause, and the footer it printed goes to the PM.
3. **Small, if the PM wants them** (E40): the run record's publish by the monitor has no line of
   its own, and the two saves carry no counts (the bundle's `saved`/`not saved` is in the details).
   Neither was needed to tell a run that is working from one that hung.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-05

**Notes:**

Reused rather than copied, the move committed alone so its diff proves nothing changed, and the one
line that matters to the alarm held against the filter read out of Terraform itself.

1. **ac1 passes.** Red against a skeleton that logs nothing (20 of 21 failed, each at an assertion,
   the two early crashes turned into assertions first); green over the core service and the real
   command in bucket mode against moto. Ten mutants caught, including a step line carrying a
   `run_record`, a caselist's name in a progress line, and step lines on stdout.
2. **ac2 passes.** The `RunsRecorded` pattern is read out of `alerts.tf` and evaluated over every line a
   real run wrote: exactly one counted, the result, the last line, for a success and a failure, none for
   a dry run. The result's keys are pinned whole. Infrastructure untouched.
3. **Decision 1 accepted:** every step the run carries out logs under the name it already has, so
   "upload" is `publish` and the two saves, and search index, report and retention log too. Decision 6
   matters most: two existing log reads (Step 7's counts block and the cutover's summary check) would
   have miscounted the new lines, and both are fixed and tested over synthetic logs.
4. **No deviations.** The lines reach the cloud only in an image built after this merges; the docx-9 run
   image is built after it, so the run of 2026-11-11 is the first to log its steps.
5. **The optional AWS check is taken:** the operator runs `aws logs test-metric-filter` (read-only,
   seconds) before the image is built. `2	3` is the answer; a `1` comes to the PM first.
6. **Follow-up 3 declined, no task:** the run record's publish and the saves' counts were not needed to
   tell a working run from a hung one.
7. **Closing checks:** the touched suites (1,867, 125, 220, 1,253 passed), ruff, pyright, lint-imports,
   thin handlers, the docs index, links, command blocks and the specs are clean; the 336-file affected set
   is the pull request's `ci`. If `ci` fails only on
   `test_on_the_committed_profile_without_a_contact_email_crossref_names_the_public_pool_in_the_footer`
   (the real clock, v1-e07-t16), re-run the failed job.
8. **Merge:** a plain `scripts/task pr` once `ci` is green. The Goal is `Succeeded`.

## Operator records (recorded by the PM, 2026-11-05)

Added by the PM. Nothing above is changed, and this section is not a review.

| Criterion | Was | Now | Record |
|---|---|---|---|
| The optional AWS check of the RunsRecorded pattern | not run | PASS | 2026-11-05: `aws logs test-metric-filter` with the pattern from alerts.tf over a step line, a recorded success and a recorded failure answered `2 3`: the two results match and the step line does not |

The Goal stays `Succeeded`.

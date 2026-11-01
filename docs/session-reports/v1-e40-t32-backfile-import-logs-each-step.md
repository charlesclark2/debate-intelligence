# Session report: v1-e40-t32-backfile-import-logs-each-step

| | |
|---|---|
| Task | `v1-e40-t32-backfile-import-logs-each-step` — A backfile import logs each step as it ends, so a task killed part-way shows how far it got |
| Spec | [`plan_specs/v1/e40-cloud-caselist-run/t32-backfile-import-logs-each-step.yaml`](../../plan_specs/v1/e40-cloud-caselist-run/t32-backfile-import-logs-each-step.yaml) |
| Epic / release | `v1-e40-cloud-caselist-run` / `v1.8` |
| Branch | `task/v1-e40-t32-backfile-import-logs-each-step` |
| Session status | COMPLETE |

## Summary

`caselist backfile-import --execute` now writes a line to stderr as each step starts and as it ends
or fails (restore, download, import, parse, publish, publish parsed), with the step, its seconds and
its counts. During the parse it writes a progress line every five minutes with sources done and
left. Each end, failure and progress line also carries the memory high-water marks so far (the PM's
amendment of 2026-10-31, now written into the spec): the container's from its cgroup and the main
process's from `getrusage`, each left out when it cannot be read. A line has the result's shape and
`"command"`, with an `"event"` where the result has its `"status"`. It holds step names and numbers
only. Stdout still holds exactly one result, unchanged. The runbook's import section gains "How far
it got", which reads the last step line after a `STOPPED` that is not exit 0, and its counts block
now skips step lines. **Look first at:** the one change inside the parse pipeline (Decisions, item
1, for the merge with `v1-e33-t07`), and Deviation 1: AWS's documentation does not say which cgroup
version Fargate 1.4.0 gives. The lines reach the cloud only in an image built after this merges
(Follow-up 1).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `backfile-import-logs-each-step` (Import step lines) | Done | Red run against a skeleton that logs nothing, then green; five mutants, all caught |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: each step logs its start and end with seconds and counts, the parse logs its progress, no line names a school, team, file or path, and the runbook reads the last step line, by tests shown failing first | PASS | Red run (below): 20 of the 26 new tests fail against a skeleton that logs nothing. Green: `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -q -n auto -m "not slow and not live" packages/debate_cli/tests/bucket_mode/test_backfile_import.py tests/scripts/test_start_backfile_import.py` → `62 passed in 31.06s`. The always-run list, `tests/docs`, `test_output.py`, `test_caselist_parse.py`, the step-line tests and the backfile rules → `726 passed in 35.30s` |
| Node: Import step lines tests pass (`uv run pytest packages/debate_core/tests -k backfile`) | PASS | `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -q packages/debate_core/tests -k backfile` → `48 passed in 54.70s` |

**What each test holds**, by file:

* `packages/debate_core/tests/application/caselist/test_caselist_backfile_step_lines.py`: the parse's
  progress lines at the interval, on a clock the test moves. Each expected line is worked out by
  hand: ten sources of 100 s against a 300 s interval give lines at 0, 3, 6, 9 and 10 done. The
  interval counts from the last line, not from the start, and an empty parse gives one line. The
  memory reader: a stand-in cgroup v2 `memory.peak`, a v1 `memory/memory.max_usage_in_bytes`, v2
  preferred when both exist, four unreadable contents and no cgroup each left out (not zero), and
  the main process's peak in bytes (over 10 MiB, which a figure left in Linux's kibibytes would not
  reach).
* `packages/debate_core/tests/application/test_caselist_parse.py::test_progress_hears_how_many_sources_are_done_after_each_one`:
  the parse service's new callback is called with 1…n.
* `packages/debate_cli/tests/bucket_mode/test_backfile_import.py`, "What it logs as it goes": these
  go through the real command, composition root and parse pipeline over moto and the stand-in site.
  Each step's start and end line comes in order. The end lines' seconds equal the result's
  `step_seconds`. Their counts are hand-written where the archive fixes them (4 members, 0
  suppressed; 3 parsed, 1 unsupported, 0 failed, 4 cards; the archive's byte length) and equal the
  result's elsewhere. The parse's progress lines fall between its start and end: two inside five
  minutes, five with the interval at 0. No stderr line contains any planted school, team code,
  tournament or file name, the archive's name, the data directory, `/` or `\`. The memory figures
  are present on every end and progress line with a stand-in cgroup, absent from start lines, and
  only the main process's appears with no cgroup. The result line's key sets are hand-written from
  `import_as_json` at the start commit. A step that raises (a changed bundle) ends in
  `step_failed`, and no later step starts.
* `tests/docs/test_backfile_import_log_reads.py`: reads the runbook's two log reads out of the
  runbook and runs them with `sh` over a synthetic `aws logs tail` log. The step lines come from the
  CLI's own renderer; the result line and the expected output are written by hand. "How far it got"
  prints the last step line's event, step, seconds, counts and memory and passes over the result.
  The counts block prints the result's counts and none of a step line's. The new block sits after
  the import's "Watch it" and before "Its counts".

**Red run**, before any mutant: the implementation committed (`4ccb7b8`), then a skeleton that logs
nothing. `run()` ignores `on_line`, `ParseProgress` writes nothing, the memory reader returns
nothing, the parse never calls `progress`, and the runbook is the start commit's.
`.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -q -p no:randomly -n 0 --tb=line <the four test files> -k "<the new tests>"`
→ `20 failed, 6 passed, 25 deselected in 35.34s`. The 6 that pass are true of a skeleton that reads
nothing, and only a mutant can fail them: the four "left out, never zero" cases, the interval
constant, and the result line's shape. Restored with `git checkout HEAD --`.

**Mutants** (agreement 8; the PM's five). Each was run against all 26 new tests with a fresh
`HYPOTHESIS_STORAGE_DIRECTORY`, though none of them uses Hypothesis, and restored with
`git checkout HEAD -- packages`:

| Mutant | Caught by | Result |
|---|---|---|
| 1. The publish step's end line dropped (`if name != "publish"` around the end emit) | `test_each_step_logs_its_start_and_its_end_in_order…`, `test_no_line_names…` (line count), `test_the_memory_figures…` (line count) | 3 failed, 23 passed |
| 2. The source's path in each progress line's step name | `test_no_line_names_a_school_a_team_a_file_or_a_path`: `assert not ['Westfield', 'XY', 'Lakeside', 'Round', '.docx', '/']` on `"step": "parse Westfield/XY/…Round 6.docx"`. The two core progress tests also failed, but on the mutant's own `IndexError`: a crash, not a catch, and not counted | 3 failed, 23 passed |
| 3. The container figure 0 instead of absent | the four unreadable cases, the no-cgroup case (`(0, None) == (None, None)`), and `test_a_container_figure_that_cannot_be_read_is_left_out_not_zero` | 6 failed, 20 passed |
| 4. The result line's shape changed (`data["event"] = "result"`) | `test_the_result_line_keeps_its_shape` | 1 failed, 25 passed |
| 5. The progress line never written (no `start`, no `progress=`) | the two progress tests, the names test and the memory test (line counts) | 4 failed, 22 passed |

**Whole-repo checks**, after the last edit:

* `.venv/bin/ruff format --check packages tests scripts` → `1295 files already formatted`;
  `.venv/bin/ruff check packages tests scripts` → `All checks passed!`
* `.venv/bin/pyright packages/debate_core packages/debate_cli tests/docs/test_backfile_import_log_reads.py` → `0 errors, 0 warnings, 0 informations`
* `.venv/bin/lint-imports` → `Contracts: 20 kept, 0 broken.`
* `.venv/bin/python scripts/check_command_blocks.py` → `OK: no # comments in 641 shell code blocks in 203 Markdown files`
* `uv run scripts/validate_specs.py` → `OK: 554 files, 41 epics, 491 tasks, 22 releases`
* **The affected set:** `uv run scripts/affected_tests.py` → `305 of 632 test files (48.3%) chosen in 22.2 s from 12 changed files`.
  That is well over two minutes, because `output.py` and `caselist_parse.py` reach most of the CLI
  and the parse suites. Under agreement 10 it is left to the pull request's `ci`. Within the limit
  I ran the always-run list, the test directories of what changed and the files above:
  `packages/debate_core/tests/application/caselist` → `1776 passed in 110.57s`, plus the two runs in
  ac1's row.

## Files changed

* `packages/debate_core/src/debate_core/application/caselist/backfile_import.py`: `StepEvent`,
  `StepLine`, `ParseProgress` and `PARSE_PROGRESS_INTERVAL_SECONDS`. `run(caselist, *, on_line=)`
  tells each step's start, end or failure. `_step` yields a dict of counts that the step's body
  fills. `monotonic` and `memory` are injectable, defaulting to `time.monotonic` and
  `read_memory_high_water`.
* `packages/debate_core/src/debate_core/application/caselist/memory_high_water.py` (new): the cgroup
  and `getrusage` reader.
* `packages/debate_core/src/debate_core/application/caselist_parse.py`: `run(plan, *, progress=None)`,
  called with the count done after each source (Decisions, item 1).
* `packages/debate_cli/src/debate_cli/output.py`: `CliOutput.event_line`, one flushed JSON line on
  stderr in JSON mode, or a sentence in Rich mode.
* `packages/debate_cli/src/debate_cli/commands/caselist_backfile.py`: `step_line_as_json` and the
  Rich sentence; the command passes `on_line`.
* `docs/runbooks/caselist-cloud-run.md`, "Backfile imports": "How far it got", what each event
  means, how to read the memory figures; `grep -v '"event": '` in the counts block; the task's size
  now 32 GB (Decisions, item 8).
* Tests: the four files above. `plan_specs/…/t32-backfile-import-logs-each-step.yaml`: the PM's
  amendment paragraph and the phase.

## Deviations from the spec

1. **AWS's documentation does not say which cgroup version Fargate platform 1.4.0 gives.** The
   amendment asked me to say which, from AWS's docs. The platform-versions page
   (<https://docs.aws.amazon.com/AmazonECS/latest/developerguide/platform-fargate.html>) says a
   version is "a combination of the kernel and container runtime versions" and names neither. Two
   searches of docs.aws.amazon.com for Fargate with "cgroup" found no page that does. So the reader
   tries v2's `memory.peak` first, then v1's `memory/memory.max_usage_in_bytes`, and each line says
   which it read in `"cgroup"`. The first import on the new image answers the question, and the
   runbook asks the operator to report it. My belief, not from AWS's docs and not to be relied on:
   1.4.0 tasks see cgroup v1. **One risk:** if a task sees cgroup v2 on a kernel older than 5.19,
   `memory.peak` does not exist and the container figure is left out. The main process's figure
   still appears, and Follow-up 2 covers it.

## Decisions and assumptions

1. **The one change inside the parse pipeline, for the merge with `v1-e33-t07`:**
   `CaselistParseService.run` in `packages/debate_core/src/debate_core/application/caselist_parse.py`
   gains a keyword-only `progress: Callable[[int], None] | None = None`. Its loop over
   `self._runner.run(...)` becomes `for done, (job, result) in enumerate(..., start=1):`, with
   `if progress is not None: progress(done)` as the last statement of the loop body. Nothing in
   `_jobs`, `_record`, `_rebuild` or `_occurrence_rows` changed. The loop runs synchronously on the
   event loop, so a timer task could not fire during it. A per-source callback that checks the
   clock is the simplest hook that works.
2. **Stderr, not stdout.** `CliOutput` guarantees exactly one JSON object on stdout per run
   (`failure()`'s docstring), and `world.run` and the smoke harness read it. CloudWatch's awslogs
   driver records both streams, so the step lines reach the task's log. Each line is flushed at
   once, so a kill for memory (SIGKILL) loses nothing buffered. Only `caselist pull` lines feed a
   metric filter (`alerts.tf`'s `runs_recorded`), so a step line can trip no alarm. The run-stopped
   email's "the command on the last line of its log says which" still holds: every line carries the
   command.
3. **Shape:** `{"schema_version": 1, "command": "caselist backfile-import", "event": …, "data": {"step", "seconds", "counts": {…}, "memory": {…}}}`.
   Events are `step_started`, `step_ended`, `step_failed` (a refusal, a changed bundle, SIGTERM's
   `RunTerminated`; a kill for memory leaves none) and `parse_progress`. There is no `"status"`, so a
   reader of results passes over a step line. Counts and memory are nested objects so the runbook
   can print each whole (`"counts": [{][^}]*[}]`, as it already prints `held_by_request`) and later
   counts need no runbook change.
4. **Counts per step:** restore: `state_files` (a count, never their names), `parsed_objects`,
   `parsed_bytes`, `parsed_kept`. Download: `downloaded_bytes`. Import: `members`, `stored`,
   `suppressed`, `held_by_request` (summed). Parse: `parsed`, `unsupported`, `failed`, `cards`.
   Publish: `sources_uploaded`, `sources_skipped`. Publish parsed: `parsed_uploaded`. Progress:
   `sources_done`, `sources_left`. Start lines carry `"counts": {}` and no memory, since the
   amendment asks for memory on end and progress lines; failure lines carry it too.
5. **The interval is five minutes.** The parse is most of an import's estimated 1.5 to 2.5 hours, so
   that is 18 to 30 lines. It gives about a dozen points of the memory's climb before a kill like
   the one at 71 minutes, and six lines between two of the runbook's half-hourly looks at the task.
   The parse also writes one line once it has counted its sources, and one when the last is done.
   `"sources_left": 0` as the last line therefore means the kill came during the aggregates'
   rebuild, which has no progress lines of its own.
6. **Reading the memory against 32 GB.** `container_peak_bytes / 34359738368` (the task's 32768 MiB
   in bytes) is the share of the task's memory the import reached. Near 1 is where ECS stops it with
   `OutOfMemoryError`. On cgroup v1, `max_usage_in_bytes` counts page cache, which the kernel
   reclaims before it kills anything, so a figure near 1 is not a kill by itself. On v2,
   `memory.peak` also counts file-backed pages. `container_peak_bytes − main_process_peak_bytes` is
   at most what the parse workers took, since every process in the container is in its cgroup.
   `getrusage(RUSAGE_CHILDREN)` was not used: it counts only workers that have exited and been
   waited for, so with a live pool it reads near zero. The runbook says all this in "How far it
   got".
7. **Rich mode** (the Mac's terminal) prints each line as a sentence on stderr, for example
   `caselist backfile-import: parse step ended at 12.3 s; parsed 3, …`. JSON mode, which the cloud
   task uses (`start_backfile_import.py`'s `--json`), writes the JSON.
8. **The runbook's "The task" bullet** said 16 GB. Since `v1-e40-t30` it is 32 GB, and the memory
   reading in this task is read against that figure, so I changed the bullet and linked t30's
   section. The block that sets `REVISION` already says to read it again after t30's apply.
9. **No smoke check.** Every step line comes after the plan's refusals, and the smoke tier's only
   backfile check refuses at the API gate before any step. The lines are tested end to end in
   process, as the import's other rules are (`test_caselist_backfile.py`'s docstring).

## Operator follow-ups

None for this pull request. The PM is asked for one item on the first import after a new image
(Follow-up 1).

## Follow-up work

1. **The lines exist only in an image built after this merges.** The next import, `hspolicy25`
   again, runs on whichever revision `--task-definition` names. For it to log its steps, the run
   task needs an image carrying this change, through "A new image, later". Until then, "How far it
   got" prints nothing, and the runbook says so ("or the image predates `v1-e40-t32`"). The PM
   decides whether the next import waits for that image.
2. **If the first cloud import's lines carry no `"container_peak_bytes"`**, the task saw cgroup v2
   without `memory.peak` (a kernel before 5.19). A small follow-up could then record the highest
   `memory.current` seen at each line, marked as sampled rather than a true peak. It belongs in
   E40, beside this task.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-01

**Notes:**

The next import that dies will say where it died and how full the task was, which Saturday's could
not.
1. **ac1 passes.**
   * Red against a skeleton that logs nothing: 20 of 26 failed. The six that passed are "left out,
     never zero" and shape guards that only a mutant can fail, and the report says so.
   * Green: 62, and 726 with the always-run list. The node criterion passes (48).
   * All five of the PM's mutants are caught at assertions. The report also says, correctly, that
     mutant 2's two `IndexError`s in the core progress tests are crashes and were not counted: the
     catch is the names test.
   * The runbook's two reads are run with `sh` over a synthetic log, which is the right test for a
     runbook block.
2. **The PM's amendment is met.** Both memory figures appear on end, failure and progress lines and
   are absent, not zero, when unreadable. The report says how to read them against 32 GB, including
   v1's page-cache caveat and why `RUSAGE_CHILDREN` reads near zero with a live pool.
3. **Deviation 1: accepted.** AWS's documentation doesn't name the cgroup version, so the reader
   tries v2 then v1 and each line says which it read. The first import on the new image answers the
   question, and the PM records it.
4. **Decisions accepted:**
   * the one parse-pipeline change, a keyword-only `progress` callback at the end of the loop,
     described precisely for the merge with v1-e33-t07. Whichever of the two merges second rebases
     on it;
   * stderr, flushed per line, so the single result on stdout and a SIGKILL lose nothing;
   * the line shape, with no `"status"`, so result readers pass over step lines;
   * the counts per step, and five-minute progress;
   * the runbook's 32 GB bullet updated, after v1-e40-t30;
   * Rich sentences on the Mac;
   * no smoke check, since the smoke tier's backfile check refuses before any step.
5. **Follow-ups, the PM's rulings:**
   * **The next import and this image:** the hspolicy25 restart takes an image carrying this task
     if one can be applied before the import's day, after v1-e40-t30's apply and dev's function
     deploy (the image's format check needs it). Otherwise it runs on v1.1.0-dev.251 at 32 GB
     without the lines rather than wait.
   * **No `container_peak_bytes` on the first cloud lines:** filed only if it happens.
6. **Closing checks:** the affected set (305 files through `output.py` and `caselist_parse.py`) is
   left to the PR's `ci` under agreement 10. Core caselist (1,776), the import and start tests (62),
   the always-run list with docs and the step tests (726), ruff, pyright, lint-imports, command
   blocks and the specs are clean.
7. **Merge:** a plain `scripts/task pr` once `ci` is green, after `scripts/task sync`. The sweep
   batch changed this spec's `context` on dev. No operator step follows.

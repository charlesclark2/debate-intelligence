# Session report: v1-e31-t38-a-parse-workers-time-limit-starts-when-it-is-ready

| | |
|---|---|
| Task | `v1-e31-t38-a-parse-workers-time-limit-starts-when-it-is-ready` — A parse worker's time limit starts when the worker reports ready, not when it is spawned |
| Spec | [`plan_specs/v1/e31-debate-file-parsing/t38-a-parse-workers-time-limit-starts-when-it-is-ready.yaml`](../../plan_specs/v1/e31-debate-file-parsing/t38-a-parse-workers-time-limit-starts-when-it-is-ready.yaml) |
| Epic / release | `v1-e31-debate-file-parsing` / `v1.1` |
| Branch | `task/v1-e31-t38-a-parse-workers-time-limit-starts-when-it-is-ready` |
| Session status | COMPLETE |

## Summary

`ProcessPoolParseRunner` now waits for each spawned worker's ready message before handing it a
source. A worker sends that message from `_work`, after spawn has unpickled its parser and imported
the parser's modules. The source's bytes wait in the parent until then, and its time limit starts
when they are sent. So `timeout_seconds` measures the parse alone, and a slow start times out no
source.

The start has its own allowance, `WORKER_START_ALLOWANCE_SECONDS` (60 s). A worker not ready by
then is replaced, and the source it held fails as the existing `WORKER_CRASHED`, with the detail
`not ready within 60 s`. No new failure reason was added.

Four new tests were run red against the unchanged runner. Three failed for their reason; the
fourth guards a mutant. The existing time-limit test fails on the old runner once every spawned
interpreter is slowed by 2 s, and passes on the new one at 2 s and 5 s. Six mutants aimed at where
the deadline is set were each caught on a count assertion.

A real spawn on the operator's Mac is ready in 0.16 s (median of 10, one at a time) and 0.29 s
with six at once, at load average ~10. The affected set is 358 test files, so it is the pull
request's `ci` (agreement 10).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `a-parse-workers-time-limit-starts-when-i` (Limit from ready) | Done | Tests first and red (`8ce3be1`), then the fix (`071209c`), then one docstring edit reverted to shrink the affected set (`8537f3a`). |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: a worker's limit starts when it reports ready, so a slow spawn times out no source while a parse past the limit still stops, by tests shown failing first | PASS | Red, then green, below. A slow start of 2.5 s against a 1.5 s limit times out no source. A 60 s stall after the same slow start still stops as `TIMEOUT`. A worker that never starts fails its source as `WORKER_CRASHED`, and the run finishes. |
| Node criterion "Limit from ready tests pass": `uv run pytest packages/debate_core/tests/application/test_caselist_parse.py -k time_limit` | PASS | Run three times, bounded with `scripts/hard_stop.py 115`: `5 passed, 5 warnings in 9.86s`, `in 9.21s`, `in 9.24s`. |

### Red run against the unchanged runner (commit `8ce3be1`)

Command: `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests/application/test_caselist_parse.py -k time_limit -n 0 -q --tb=line`. Result: `3 failed, 2 passed in 24.44s`.

| Test | Old runner | Why |
|---|---|---|
| `test_a_worker_slow_to_start_counts_none_of_its_start_against_the_time_limit` | FAIL `{'TIMEOUT': 6} == {'NOT_A_ZIP': 1}` | The 2.5 s start was counted against the 1.5 s limit. |
| `test_a_parse_past_the_time_limit_after_a_slow_start_still_stops_as_a_timeout` | FAIL `{'TIMEOUT': 6} == {'NOT_A_ZIP': 1, 'TIMEOUT': 1}` | Same cause. |
| `test_a_worker_that_never_reports_ready_fails_its_source_on_its_start_not_the_time_limit` | FAIL `{'TIMEOUT': 6} == {'WORKER_CRASHED': 6}` | The old runner has no start allowance, so it calls a hung start a timeout. |
| `test_a_parse_past_the_time_limit_is_stopped_and_the_run_carries_on` (existing) | pass | Spawns are fast today. See the slowed-spawn run below. |
| `test_each_parse_on_a_reused_worker_gets_the_whole_time_limit` | pass | The old runner restarts the limit at each dispatch too. This test is there for the mutant `limit_not_restarted_for_a_reused_worker`. |

### The existing test made deterministic

A scratch `sitecustomize.py` sleeps `SLOW_SPAWN_SECONDS` in every process started with
`--multiprocessing-fork`. That is every spawned worker and nothing else. It is the same
measurement v1-e07-t16 made, and it ran only from the session's scratchpad, never from the
repository. The selection was the existing time-limit test plus the reused-worker test, run with
`-n 0`.

| Runner | Spawn slowed by | Result |
|---|---|---|
| old (`8ce3be1`) | 0 s | `2 passed in 4.81s` |
| old (`8ce3be1`) | 2.0 s | `2 failed`: `{'TIMEOUT': 6} == {'NOT_A_ZIP': 1, 'TIMEOUT': 1}` and `{'TIMEOUT': 6} == {'NOT_A_ZIP': 1}` |
| new (`071209c`), `-k "time_limit or worker or pool"` | 2.0 s | `8 passed in 40.40s` |
| new (`071209c`), same selection | 5.0 s | `8 passed in 62.91s` |

The new runner passed the same selection unslowed too: `8 passed in 19.47s`.

### Mutants on where the deadline is set

Each mutant was applied to the committed `parse_workers.py` with exact text replacements. Each was
run with `-k time_limit -n 5 --tb=line` and restored with `git checkout HEAD --`; `git status` was
clean after every restore. No Hypothesis property is involved. Every failure listed is a count
assertion, not a traceback.

| Mutant | Result | Caught by |
|---|---|---|
| `limit_from_dispatch`: the pre-task rule, limit set at dispatch, no start allowance | 4 failed, 1 passed | slow start `{'TIMEOUT': 6}`, slow start then stall `{'TIMEOUT': 6}`, never ready `{'TIMEOUT': 6}`, reused worker `{'NOT_A_ZIP': 1, 'TIMEOUT': 1}` |
| `limit_from_spawn`: limit set when the worker is spawned | 4 failed, 1 passed | the same four |
| `ready_deadline_from_spawn_time`: set on ready, but counted from the spawn time the start deadline implies | 2 failed, 3 passed | slow start `{'NOT_A_ZIP': 1, 'TIMEOUT': 4}`, slow start then stall `{'TIMEOUT': 6}` |
| `limit_not_restarted_for_a_reused_worker`: set once on ready, not again for the worker's next source | 1 failed, 4 passed | reused worker `{'NOT_A_ZIP': 1, 'TIMEOUT': 1}` |
| `start_allowance_is_the_parse_limit` | 2 failed, 3 passed | slow start `{'WORKER_CRASHED': 6}`, slow start then stall `{'WORKER_CRASHED': 6}` |
| `no_start_allowance_branch`: an unready worker judged by the timeout branch | 1 failed, 4 passed | never ready `{'TIMEOUT': 6} == {'WORKER_CRASHED': 6}` |

Six of six caught. One mutant is equivalent and was not run: dropping the timeout branch's
implicit ready check. The start-allowance branch above it already takes every unready worker, so
nothing reaches the timeout branch unready.

Under `-n 5`, the pre-task rule also failed the reused-worker test, which it had passed at `-n 0`.
Under load, the old limit's dependence on start time shows even in a test that is not about
starting.

### Real spawn time on the Mac

This was measured with the scratch script `measure_spawn.py`. It times `ProcessPoolParseRunner._start`
with a `DebateDocxParser` until the ready message arrives. Load average was 10.1 before the run
and 9.6 after.

* One at a time, 10 spawns: median **0.16 s**, max 0.21 s.
* Six at once (the default `worker_cap`): median **0.29 s**, max 0.30 s.
* Stopping two workers whose start never finishes: 4.01 s. That is the unchanged stop's 2 s grace
  per worker, and it is where the never-ready test's ~4 s goes.

### Closing checks

| Command | Result |
|---|---|
| `uv run scripts/affected_tests.py` | 358 test files. That is over two minutes on this machine (memory: 47 files ran 269 s), so the affected set is the pull request's `ci` (agreement 10). It was 474 before `8537f3a`; see Decisions. |
| Within the limit: the always-run list (`tests/architecture`, `tests/specs`, `test_app.py`, `test_help_rendering.py`, `test_container_factories.py`) and every test file that uses `ProcessPoolParseRunner` or `parse_workers` (14 files, from `git grep`), `-n 6 -m "not slow and not live"` | `643 passed in 93.47s` |
| `.venv/bin/python -m pytest packages/debate_core/tests/application/test_caselist_parse.py` | `57 passed in 9.94s` |
| `uv run --frozen ruff format --check .` / `ruff check .` | `2052 files already formatted` / `All checks passed!` |
| `pyright packages/debate_core` | Stopped by `hard_stop.py` at 115 s at a load average near 23, with no result. |
| `pyright packages/debate_core/src/debate_core/application/caselist packages/debate_core/tests/application/test_caselist_parse.py` | `0 errors, 0 warnings, 0 informations` (44 s) |
| `uv run --frozen lint-imports` | `Contracts: 20 kept, 0 broken.` |
| `uv run scripts/validate_specs.py` (after `set-phase … Succeeded`) | `OK: 655 files, 41 epics, 592 tasks, 22 releases` |

## Files changed

* `packages/debate_core/src/debate_core/application/caselist/parse_workers.py`: the ready message,
  `WORKER_START_ALLOWANCE_SECONDS`, bytes held until the worker is ready, the limit set in `_send`,
  and the start-allowance branch in `_collect`. The module docstring gains "When the time limit
  starts".
* `packages/debate_core/tests/application/test_caselist_parse.py`: `SlowToStartParser` and four
  tests. The existing time-limit test gets a docstring and is otherwise unchanged.
* The task spec: Goal phase `Succeeded`.

## Deviations from the spec

None.

## Decisions and assumptions

* **A source's bytes wait in the parent until its worker is ready.** The old runner sent them at
  dispatch. A send larger than the pipe's buffer blocks until the worker reads, so a worker that
  never started could hold the parent forever, and the start allowance could never fire. Each
  worker holds at most one source's bytes, as the pipe did before.
* **`WORKER_START_ALLOWANCE_SECONDS = 60`.** That is about 200 times the measured six-at-once
  spawn, and half the default 120 s parse limit. It is a module constant, not a setting, as asked;
  it exists for a worker that will never start, not a slow one.
* **`WORKER_CRASHED` for a worker that never reports ready.** No existing reason fits better.
  `TIMEOUT` is documented as a parse past its limit, and none of the source reasons applies. The
  detail tells the two cases apart: `not ready within 60 s` against `the worker exited`.
* **`PipelineFailureReason.WORKER_CRASHED`'s docstring is unchanged.** It still reads "died while
  parsing this source". I widened it in `071209c` and reverted it in `8537f3a`.
  `ports.parsed_store` reaches the root conftest, and that one line took the affected set from 358
  to 474 files. If the PM wants the wording, it is: "The worker process died while holding this
  source, or never reported ready to parse it."
* **The never-ready test uses the runner's injected clock**, which moves a day at every read. Every
  deadline the runner sets has passed by its next read, so the test waits on no real allowance or
  limit, and its outcome depends on no speed. Its ~4 s is the pool's unchanged stop: a 2 s grace for
  each of two workers that never read their stop message.
* **The slow start is a wait in `SlowToStartParser.__setstate__`.** The scenario under test is
  allowed by the PM's brief. It runs only in the worker, which unpickles the parser; the parent
  only pickles it. The class lives in the test module, and a probe showed a spawned child imports
  that module under `--import-mode=importlib`. No limit was lengthened and no sleep was added to
  make a test pass (the spec's forbidden list).
* **The reused-worker test** depends on real time like the existing one: two 1.0 s parses against
  a 1.5 s limit. It depends on parse speed (a fixture parse takes milliseconds), never on spawn
  speed, and it is the only test that catches `limit_not_restarted_for_a_reused_worker`.
* **The run's other behaviour is unchanged**: one result per source, a crashed worker replaced,
  the pool stopped at the end. `_stop` is untouched, and the existing crashed-worker and empty-pool
  tests pass.

## Operator follow-ups

None. The 358-file affected set runs in the pull request's `ci` under agreement 10.

## Follow-up work

* E31, optional: `_stop` gives each worker a 2 s grace even when it never reported ready, so a hung
  start costs 2 s at the end of a run. Terminating unready workers at once would remove that.
  I left it alone because the brief keeps the pool's stop unchanged.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-11

**Notes:**

The PM read `parse_workers.py` in the worktree.
- `_start` gives a new worker a start deadline of spawn time plus `WORKER_START_ALLOWANCE_SECONDS`.
- `_dispatch` holds the bytes in `waiting` until the worker is ready.
- The worker's first message, `_READY`, sends them.
- `_send` sets the parse deadline after the send.
- `_collect` waits only on busy workers, so the `assert worker.waiting is not None` holds: a busy,
  unready worker always holds its bytes.
- An unready worker past its allowance is replaced as `WORKER_CRASHED` before the timeout branch is
  reached.

1. **ac1 passes.**
   - The three new tests failed for their own reasons against the unchanged runner (`{'TIMEOUT': 6}`
     each). The fourth exists for a mutant, and is shown to catch it.
   - The existing test is shown to depend on spawn speed under the old runner: it fails with every
     spawn slowed by 2 s. It is independent of spawn speed under the new one, passing at 2 s and 5 s.
     That was measured with a scratch `sitecustomize.py` kept out of the repository.
   - Six of six mutants on where the deadline is set are caught at count assertions. The one left
     unrun is rightly equivalent.
2. **The decisions are accepted.**
   - The bytes wait in the parent, so a worker that never starts can't block the parent on a full
     pipe.
   - The start allowance is 60 s, against a measured 0.16 s (0.29 s for six at once).
   - A worker that never starts fails its source as `WORKER_CRASHED`, with a detail that tells it
     apart. v1-e31-t17's retry of transient failures will treat it as a crash, which is right.
   - The never-ready test runs on a clock that jumps a day a read.
   - The slow start is a wait in the test parser's `__setstate__`, which is the scenario under test,
     not a sleep added to make a test pass.
   - The docstring widening was reverted to keep the affected set at 358. The PM keeps the session's
     wording for whichever task next edits `PipelineFailureReason`.
3. **v1-e31-t27 is not covered.** This report doesn't name it, and has no run under an artificial
   load. The reused-worker test and the existing time-limit test still depend on real parse time (two
   1.0 s parses against 1.5 s, and the stall against 1.5 s), so t27's ask still stands: 20 runs under a
   busy-loop process per core, and a mutant that removes the limit. As this task's prerequisite note
   said, the PM amends t27 in the next batch to what is left, and it stays where it is.
4. **The follow-up is noted, not filed:** `_stop`'s 2 s grace for a worker that never reported ready.
   It costs 2 s once per run, and only after a hung start.
5. **Merge:** a plain `scripts/task pr` once `ci` is green. The Goal is `Succeeded`. The branch starts
   before PM batch 2026-11-09, which gave this spec its prerequisite (`v1-e31-t06`). Git merges that
   with this branch's phase change, which is a separate hunk; if `scripts/task pr` reports a conflict,
   run `scripts/task sync` first.

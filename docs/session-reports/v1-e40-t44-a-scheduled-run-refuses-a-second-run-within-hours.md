# Session report: v1-e40-t44-a-scheduled-run-refuses-a-second-run-within-hours

| | |
|---|---|
| Task | `v1-e40-t44-a-scheduled-run-refuses-a-second-run-within-hours` — A scheduled pull refuses to run when the bucket's run log shows a run started within the last hours |
| Spec | [`plan_specs/v1/e40-cloud-caselist-run/t44-a-scheduled-run-refuses-a-second-run-within-hours.yaml`](../../plan_specs/v1/e40-cloud-caselist-run/t44-a-scheduled-run-refuses-a-second-run-within-hours.yaml) |
| Epic / release | `v1-e40-cloud-caselist-run` / `v1.8` |
| Branch | `task/v1-e40-t44-a-scheduled-run-refuses-a-second-run-within-hours` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

A pull started with the new `caselist pull --scheduled` now reads the bucket's run log before
anything else. It refuses with `RecentRunRecorded` (`RECENT_RUN_RECORDED`, exit 1) when the log
records a `caselist pull` run of mode `run` that started within the last 24 hours and was not a
refusal by the lock or by this guard. The check comes before the lock is taken, the restore and the
sync service's build, so the token is never read and OpenCaselist is never called. The refusal is
recorded and announced as `RunLockHeld` is, and its notice and hint name the cure in the PM's words.
A pull without `--scheduled` is a hand run and is never asked. A run log that cannot be read lets the
run go on to the lock, with a warning. The refusal joins `landscape_staleness.LOCK_REFUSALS`, with its
parametrised case. What the PM should look at first: the guard is inert in the cloud until the
schedule passes `--scheduled`, which is the PM's next Terraform task (follow-ups, verbatim), so this
branch is safe to merge and deploy before it (ruling 2). Every criterion passed, and the Goal is
`Succeeded`. The affected set is 8,620 tests, so it was left to the PR's CI and its relevant parts
were run here (checks below).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `a-scheduled-run-refuses-a-second-run-wit` (Second run guard) | Done | Proposal, PM ruling, skeleton committed and tests run red against it, guard built, 18 planted breaks plus one plant in a test. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the proposal is ruled on by the PM | PASS | Proposal committed in `51f4569`. The PM's rulings of 2026-11-12, all five accepted, with additions to 2, 3 and 4 (Decisions below). |
| ac1: a scheduled pull with a run within N hours is refused before the lock and any OpenCaselist call, a hand run is not, by tests shown failing first | PASS | Red against the skeleton (`5b2b3b3`, a guard that refuses nothing): `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests/application/caselist/test_scheduled_pull_guard.py -n 0 -q --tb=line` → **15 failed, 11 passed**. The 15 are the three refusal tests (raised `RunStateBundleMissing`, not `RecentRunRecorded`, so the lock and the restore had run), the unreadable-log test (no warning line), 10 counting cases and the latest-run test. The 11 that passed are what must not refuse: the hand run, the run past 24 hours and the bucket with no run log, plus the 8 cases that count nothing (the 5 refusals, a `--publish-pending` pull, 24 h exactly, last week). The CLI's usage errors, red the same way: `... -m pytest packages/debate_cli/tests/bucket_mode/test_scheduled_pull_guard.py -n 0` → **3 failed, 1 passed** (exit 1, not 2). Green after: the same files → 27 passed (28 with the banner-words test) and 4 passed. Planted breaks below. |
| Node: Second run guard tests pass (`uv run pytest packages/debate_core/tests -k "pull and guard"`) | PASS | `.venv/bin/python scripts/hard_stop.py 115 uv run pytest packages/debate_core/tests -k "pull and guard"` → **28 passed in 22.06s**, exit 0. It selects exactly `test_scheduled_pull_guard.py`'s 28 tests: 11 functions, one of them with 18 cases. |

### Planted breaks

Each was applied to the committed source, run against its tests, and restored with `git checkout HEAD --`
(driver kept in the session's scratchpad; `git status` clean after). Every one failed on its own
assertion, not a crash:

| Break | Tests failed (assertion) |
|---|---|
| The guard asked of a hand run too (`if bracket is not None`) | core hand-run test; CLI hand-run half (an error envelope) |
| The guard after the lock and restore | 3 refusal tests (`RunStateBundleMissing` raised first), unreadable-log test |
| Window inclusive (`<=`) | `exactly_24_hours_ago`, the lets-through-after-24-hours test |
| Lock refusals counted | 5 refusal cases (`refused_by_*`, including this guard's own) |
| `--publish-pending` pulls counted | `a_publish_pending_pull` |
| Failed runs not counted | `failed_at_a_stage`, `stopped_on_an_expired_login`, `stopped_by_sigterm`, `lost_its_lease` |
| An unreadable log refuses | unreadable-log test ("the lock decides, as before the guard") |
| The earliest run named, not the latest | latest-run test |
| The refusal's record published (`record_stays_local = False`) | core: bucket changed; CLI: `RUN_LOCK_NOT_HELD` instead of `RECENT_RUN_RECORDED` (the lock's fence refused the publish) |
| The generic failed-run notice | notice test (`Notification` differs) |
| No hint from `fix_for` | notice test |
| No cure in the notice | notice test |
| `banner_words` without the class | **survived** at first; caught after `test_a_scheduled_pull_guard_refusal_reads_back_with_the_lock_refusals_banner_words` was added (`ec5f176`) |
| The CLI never passes `scheduled` | CLI retry half (exit 0, not refused) |
| `--scheduled` allowed in local mode | `in_local_mode` |
| `--scheduled` allowed with `--dry-run` | `beside_dry_run` |
| The container's bracket on the real clock (no `now=`) | CLI retry half (real 2026-11-12 is not within 24 h of the test clock's run) |
| A second module builds a `SyncRunMonitor` (`backfile_import.py`) | `test_the_composition_root_alone_builds_the_run_monitor` |
| (test-side plant) a pull record written into the bucket's run log after a backfile import | the run-log equality; with that line disabled, the scheduled pull straight after is refused |

Removing `RecentRunRecorded` from `LOCK_REFUSALS` → `test_landscape_staleness.py` **5 failed, 37 passed**:
both parametrised `[RecentRunRecorded]` cases, the new `test_the_lock_refusals_are_the_ones_parametrised_here`,
and the two tests that read a log of refusals. Restored → 42 passed.

### Checks before the report

| Check | Result |
|---|---|
| `uv run scripts/affected_tests.py` | 361 of 752 test files; `--collect-only -m "not slow and not live"` over them: **8,620 tests** (36 s to collect). Over two minutes, so **not run**, per the PM's rule of 2026-10-19 (v1-e31-t26). The PR's `ci` check runs it. |
| Always-run list plus the docs checks (`tests/architecture/ tests/specs/ test_app.py test_help_rendering.py test_container_factories.py tests/docs/ tests/scripts/test_check_command_blocks.py tests/scripts/test_docs_index.py`) | 735 passed in 34 s |
| `packages/debate_cli/tests/bucket_mode/` (all 19 files, in three runs; one run of all of it hit the 115 s stop) plus `test_only_caselist_pull_writes_the_run_log.py` | 88 + 87 + 120 passed |
| Every debate_core and debate_cli test file naming `run_pull`, `BucketRun`, `notifications_for`, `banner_words`, `LOCK_REFUSALS`, `RunState`, `fix_for`, `PullBracket`, `landscape_staleness` or `SyncRunMonitor` outside bucket_mode (36 files, two runs) | 289 + 493 passed |
| `packages/debate_cli/tests/commands/test_caselist_pull*.py` (3 files) | 82 passed |
| `uv run ruff check .` and `uv run ruff format --check .` | clean |
| `uv run pyright` on the 13 changed Python files | 0 errors, 0 warnings |
| `uv run lint-imports` | 20 kept, 0 broken |
| `scripts/check_thin_handlers.py`, `scripts/check_links.py`, `scripts/check_command_blocks.py`, `scripts/docs_index.py --check-descriptions` | all OK (74 handlers within 25 statements) |
| `uv run scripts/validate_specs.py` | OK: 669 files, 41 epics, 606 tasks, 22 releases |

## Files changed

* `debate_core.application.caselist.recent_run` (new): the window, the cure sentence and
  `RecentRunRecorded`.
* `debate_core.application.caselist.bucket_run`: `BucketRun.refuse_after_a_recent_run` and
  `latest_counting_run`, plus a `now` clock.
* `debate_core.application.caselist.run_state`: `RunState.recorded_runs`, the bucket's run log read
  without restoring, listed first as `parses_owed` is.
* `debate_core.application.caselist_sync`: `run_pull(scheduled=)`, which asks the bracket before the
  lock; `PullBracket` gains the method; `fix_for` gives the refusal's hint.
* `debate_core.application.sync_runs`: the notice (`RECENT_RUN_RECORDED_TITLE`) and the lock
  refusal's banner words.
* `debate_core.application.landscape_staleness`: `RecentRunRecorded` joins `LOCK_REFUSALS`.
* `debate_cli.commands.caselist_pull`: `--scheduled` and its three usage errors.
  `debate_cli.container`: the bracket's clock.
* Tests: `packages/debate_core/tests/application/caselist/test_scheduled_pull_guard.py` (new);
  `test_landscape_staleness.py` (its parametrised case and the pin on `LOCK_REFUSALS`);
  `packages/debate_cli/tests/bucket_mode/test_scheduled_pull_guard.py` (new);
  `test_backfile_import.py` (the run-log pin); `packages/debate_cli/tests/test_only_caselist_pull_writes_the_run_log.py` (new).
* `docs/runbooks/caselist-cloud-run.md`: "A scheduled run refused after a recent run", and a pointer
  to it from the retry paragraph.

## Deviations from the spec

None.

## Decisions and assumptions

### The PM's rulings of 2026-11-12, as applied

1. **N = 24 hours**, accepted. A hand run between Tuesday 06:00 and Wednesday 06:00 making that
   Wednesday's scheduled run refuse is an accepted cost: late, not lost. `RECENT_RUN_WINDOW`.
2. **`caselist pull --scheduled`, passed only by the schedule**, accepted, with the usage errors as
   proposed (beside `--dry-run` or `--publish-pending`, or in local mode: exit 2). Until the schedule
   passes it the guard is inert, so this code is safe to merge and deploy before any Terraform change.
   The Terraform change is the PM's own task in the next batch (follow-ups).
3. **Counting as proposed, plus: only `caselist pull` records count.** Checked: the run log has one
   writer, `SyncRunMonitor`, built only by the composition root and asked for only by
   `caselist pull`, and `caselist backfile-import` writes no record to it. The record has no command
   field (frozen since `v1-e34-t19`), so the guard can't filter by command; the pins are what make
   "every `run` record is a pull" true. `test_a_backfile_import_writes_no_record_a_scheduled_pull_counts`
   runs an import and then, at the same moment, a scheduled pull that runs, so the guard doesn't
   depend on the no-import window. `test_only_caselist_pull_writes_the_run_log.py` fails on any new
   builder, asker or namer of the run log.
4. **The refusal as proposed, plus the cure**: the notice and the hint both say "a hand run (the
   cloud-run runbook's Step 8) is never refused by this guard", beside the earlier run's id and start
   time (`HAND_RUN_CURE`). The runbook section says the same, and a test pins it.
5. **An unreadable run log goes on to the lock**, with the warning line, as proposed.

Choices left to me: the guard's place is `BucketRun.refuse_after_a_recent_run`, called by
`run_pull` inside the monitor before `bracket.start`, and the error class lives in its own module,
`caselist/recent_run.py`. `landscape_staleness` and `sync_runs` both import that class, and
`bucket_run` imports `LOCK_REFUSALS` from `landscape_staleness`, so a module of its own avoids an
import cycle. The bucket's run log is listed before it is read, as `parses_owed` lists, because under
a prefix-conditioned grant a missing key reads as refused. An absent log means no recorded run.

### Proposal as ruled on (2026-11-12)

**What the schedules are today** (`infrastructure/modules/caselist_run/`, read only):

* `aws_scheduler_schedule.run` (run_task.tf): `schedule_expression = "cron(0 6 ? * WED *)"`,
  `schedule_expression_timezone = "America/Chicago"`, `flexible_time_window { mode = "OFF" }`,
  `retry_policy { maximum_retry_attempts = local.schedule_retry_attempts; maximum_event_age_in_seconds = local.schedule_event_age_in_seconds }`,
  with `schedule_retry_attempts = 3` and `schedule_event_age_in_seconds = 3600` (main.tf). Its
  target sets `ecs_parameters` and no `input`: no override of any kind.
* `aws_scheduler_schedule.login` (login_task.tf): `cron(0 3 ? * WED *)`, the same zone and retry
  policy. It runs `caselist auth login`, never a pull, so the guard has nothing to do with it.
* The run task definition: `entryPoint = ["timeout", "--signal=TERM", "--kill-after=120s", "6h", "debate-research"]`,
  `command = ["--json", "caselist", "pull"]`. A hand run (runbook Step 8, "One run by hand", as on
  2026-11-05) is `aws ecs run-task ... --task-definition debate-dev-caselist-run` with no
  `--overrides`: the same command and environment as the schedule's. A backfile import is a hand
  run of the same task definition with a command override, and writes no run log.

**1. N = 24 hours.**

* A second start of one Wednesday's invocation comes from a retry, all of which land within the
  event age, 1 hour after 06:00, plus the container's own start. 24 hours covers that with room, and
  it is also Scheduler's own ceiling on `maximum_event_age_in_seconds` (86 400 s), so N holds
  whatever retry policy the schedule is later given: the timing bound is gone, not moved.
* A second run within 24 hours can only spend what the first left of the download ledger's
  5-per-rolling-24-hours allowance, so the run it refuses is the one with least to do.
* It never reaches the next Wednesday: 168 hours apart, 167 at the spring change of clocks.
  Nor the catch-up hand run after a missed Wednesday: 20261105T034547Z (21:45 CST on 2026-11-04,
  87 minutes) was 152 hours before the 2026-11-11 06:00 schedule.
* Run times do not bound it, since the guard compares start times: the runs took 56 minutes
  (2026-10-28), 87 minutes (20261105T034547Z) and 113 minutes (20261111T120101Z, a full docx-9
  parse), under the 6-hour deadline.
* Its cost: a hand run started between Tuesday 06:00 and Wednesday 06:00 makes that Wednesday's
  scheduled pull refuse. The week is then the hand run's; anything newer waits a week (late, never
  lost), and the refusal's email says how to run by hand. The runbook already says never by hand on
  a Wednesday before 07:00.
* The alternative, N = 3 hours (the 1-hour event age plus 2 hours of slack), meets no hand run but
  rests on today's event age, the bound the task removes.

**2. Telling a scheduled start from a hand run: a new `caselist pull --scheduled` option, passed
only by the schedule's container override.** Nothing the container sees today differs: no
override, the same task definition, and ECS's `startedBy` is not in the task metadata endpoint
(reading it through `ecs:DescribeTasks` would itself need an IAM change). Every start without the
option is a hand run and is never refused, whatever the time or day; a time-of-day rule would refuse
a hand run, which the spec forbids. Proposed Terraform change, for a later task with infrastructure/
in its packages (the operator applies, the PM reads the plan first, never on a Wednesday):

* resource `aws_scheduler_schedule.run`, file `infrastructure/modules/caselist_run/run_task.tf`,
  block `target`: a new attribute
  `input = jsonencode({ containerOverrides = [{ name = local.run_container_name, command = ["--json", "caselist", "pull", "--scheduled"] }] })`.
  ECS keeps the entry point (`timeout ... debate-research`) and replaces the command only.
* The apply must carry an image that knows `--scheduled`: an older image answers the option as a
  usage error (exit 2) and the week does not run. The sequence is the usual one: release, image
  push, new digest in owner.auto.tfvars, plan, apply, all in one plan.
* Not verified (no live call today): that a templated ECS target passes `input` to RunTask as
  `overrides`. AWS's EventBridge rules do; Scheduler's page should be read before the apply.
  If it does not, the universal target `arn:aws:scheduler:::aws-sdk:ecs:runTask` takes the whole
  RunTask request, `overrides` included.
* An environment-variable override was the other choice. A `DEBATE_CASELIST__*` one fails an
  older image at settings load just as the option does; one outside the settings would be read
  around them.

`--scheduled` together with `--dry-run` or `--publish-pending`, or in local mode (no bucket run
log), is refused as a usage error before anything runs, as `--dry-run --publish-pending` is.

**3. Which recorded runs count.** The bucket's run log, `reports/sync/state/caselist-sync-runs.jsonl`,
read with one GET. A record counts when its `mode` is `run` and its `started_at` is within N, unless
its `error_class` is a lock refusal (`landscape_staleness.LOCK_REFUSALS`) or this guard's own.
Every outcome counts, `completed`, `nothing_new`, `cap_deferred`, `publish_pending` (the outcome:
captured, its publish waiting), `incomplete` and `failed`:

* an `incomplete` run captured and published its week; only a later stage failed, and the next
  run (or a hand run) takes up the parse it owes;
* a `failed` run counts too, including one that raised: a raised run is recorded with no stage
  wherever it stopped (`record_for_failure`), whether at listing or at SIGTERM six hours in, so its
  record cannot tell the two apart. Counting it keeps "never twice"; the run it costs is a second
  start after an early stop, which exists only after an ambiguous launch, and a hand run, never
  refused, is the cure.
* a `--publish-pending` pull (the mode `publish_pending`) does not count: it lists and fetches nothing.

In practice the bucket's log holds only runs that held the lock, since only such a run saves the
state files (a refusal's record stays on its task). The exclusion matters for the history seeded
from the Mac, and is kept so the rule says what it means.

Limits, named and not changed (no change to the lock): the bucket's log gains a run's record only
at its end, just before the release, so while a run is going the lock is what refuses a second
start; a run killed hard (out of memory, or SIGKILL after the deadline) writes no record, and a start
after its 30-minute lease expires runs, as it does today; a run whose end-of-run save failed
releases the lock with no record in the bucket.

**4. Where the refusal sits.** In `run_pull`'s `one_run`, inside the run monitor so that it is
recorded and announced, after the no-caselist check and before `bracket.start`: before the lock's
take, the restore, and the build of the sync service, so before the token is read or OpenCaselist
called. It is `RecentRunRecorded(DomainError)` in `debate_core.application.caselist`, code
`RECENT_RUN_RECORDED`, `record_stays_local = True` (it never held the lock), exit 1. It goes as
`RunLockHeld` goes: the record is `failed` with its class, written on the task and never to the
bucket; the details carry its code; the JSON result line is in the run's CloudWatch log; the notifier
(SNS in the cloud) sends "caselist pull skipped: a run started within the last 24 hours", naming the
earlier run's id and start, with `debate-research caselist runs` as the fix; exit 1 sends the
task-stopped email too, as a lock refusal's does. It joins `LOCK_REFUSALS`, with a case in
`test_landscape_staleness.py`'s parametrisation, and gets `LOCK_BANNER_WORDS` as `RunLockHeld`
does. The runbook gets a section on it.

**5. A run log that cannot be read: proceed to the lock** (recommended), with a warning line in the
log naming the error's class. A run log the bucket does not hold is no recorded run. Reasons: the
precedent of `v1-e34-t26` ("the guard is then late, never the run"); the lock still refuses any
concurrent run; the run role reads the same prefix in the restore straight after, so a refused read
fails that run there, recorded and announced, and an unreachable bucket fails at the lock's take.
Refusing would turn a passing read error into a lost week, to prevent a second run that needs an
ambiguous launch at the same moment.

**Tests** (all offline: moto for the bucket, a sync-service factory that fails the test if it is
called, a lock that records whether it was taken), named so that the spec's `-k "pull and guard"`
selects them, run red first against a guard that refuses nothing.

## Operator follow-ups

<!-- Commands the operator must run (anything over ~2 minutes), with where to run them, the exact
command, expected runtime and what success looks like. Also GitHub/AWS settings to change. -->

None (the PM: no command today, and no deploy). The affected set, 8,620 tests, is the PR's `ci`
check's to run, as the PM's rule of 2026-10-19 says; it needs no hand-off.

## Follow-up work

<!-- Bugs, gaps or ideas outside this task's scope, each with the task or epic it belongs to.
The PM decides whether they become spec changes or new tasks. -->

* **The schedule passes `--scheduled`** (the PM files it in the next batch, with infrastructure/ in its
  packages: an image carrying `--scheduled` released, pushed and its digest pinned; the plan read by
  the PM; never applied on a Wednesday; AWS's Scheduler documentation read first for how a templated
  ECS target passes `input`, with the universal target as the fallback). The proposed resource change
  and the NOT VERIFIED note, verbatim from the proposal:

  * resource `aws_scheduler_schedule.run`, file `infrastructure/modules/caselist_run/run_task.tf`,
    block `target`: a new attribute
    `input = jsonencode({ containerOverrides = [{ name = local.run_container_name, command = ["--json", "caselist", "pull", "--scheduled"] }] })`.
    ECS keeps the entry point (`timeout ... debate-research`) and replaces the command only.
  * The apply must carry an image that knows `--scheduled`: an older image answers the option as a
    usage error (exit 2) and the week does not run. The sequence is the usual one: release, image
    push, new digest in owner.auto.tfvars, plan, apply, all in one plan.
  * Not verified (no live call today): that a templated ECS target passes `input` to RunTask as
    `overrides`. AWS's EventBridge rules do; Scheduler's page should be read before the apply.
    If it does not, the universal target `arn:aws:scheduler:::aws-sdk:ecs:runTask` takes the whole
    RunTask request, `overrides` included.

  Once it is applied, the runbook's sentence "Until the schedule passes `--scheduled`, the guard does
  nothing" comes out, in that task.
* **(Unverified) a ClientToken from the schedule.** With the universal RunTask target, the schedule
  could pass a `clientToken` built from the invocation, so that ECS never places a second task for a
  retried ambiguous call. Not verified: whether the execution id stays the same across one
  invocation's retries, and how long ECS keeps a client token.
* **Limits the guard leaves, named and not changed** (no change to the lock): a run killed hard
  writes no record, so a start after its 30-minute lease runs, as today; a run whose end-of-run save
  of the state files failed releases the lock with no record in the bucket.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

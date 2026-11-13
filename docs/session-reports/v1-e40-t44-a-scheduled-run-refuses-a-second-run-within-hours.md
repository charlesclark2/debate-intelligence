# Session report: v1-e40-t44-a-scheduled-run-refuses-a-second-run-within-hours

| | |
|---|---|
| Task | `v1-e40-t44-a-scheduled-run-refuses-a-second-run-within-hours` — A scheduled pull refuses to run when the bucket's run log shows a run started within the last hours |
| Spec | [`plan_specs/v1/e40-cloud-caselist-run/t44-a-scheduled-run-refuses-a-second-run-within-hours.yaml`](../../plan_specs/v1/e40-cloud-caselist-run/t44-a-scheduled-run-refuses-a-second-run-within-hours.yaml) |
| Epic / release | `v1-e40-cloud-caselist-run` / `v1.8` |
| Branch | `task/v1-e40-t44-a-scheduled-run-refuses-a-second-run-within-hours` |
| Session status | IN PROGRESS <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

Stopped at the proposal, as the spec asks (2026-11-12). Nothing is implemented yet. The proposal
below (N, how a scheduled start is told apart from a hand run, which recorded runs count, where the
refusal sits, and what an unreadable run log does) waits for the PM's ruling. The one fact the
PM should look at first: today the schedule passes **no** override, and a hand run starts the same
task definition with the same command, so nothing the container sees today tells the two apart. The
proposal needs a Terraform change to `aws_scheduler_schedule.run`, which this task only proposes
(infrastructure/ is read-only here), so the guard this task adds stays inert in the cloud until a
later task applies it.

## Plan nodes

<!-- One row per Plan graph node, in the order they were completed. -->

| Node | Status | Notes |
|---|---|---|
| | | |

## Acceptance criteria

<!-- Goal criteria (ac1…) and every node criterion. Status: PASS / FAIL / NOT RUN. -->

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| | | |

## Files changed

<!-- Group by package or directory; one line on why each group changed. -->

## Deviations from the spec

None.

## Decisions and assumptions

### Proposal awaiting the PM's ruling (2026-11-12)

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

None.

## Follow-up work

<!-- Bugs, gaps or ideas outside this task's scope, each with the task or epic it belongs to.
The PM decides whether they become spec changes or new tasks. -->

* The schedule's `input` override (proposal point 2) needs a task with infrastructure/ in its
  packages and an image deploy; until then the guard is inert in the cloud.
* With the universal RunTask target, the schedule could pass a `clientToken` built from the
  invocation, which would stop ECS from placing a second task for a retried ambiguous call at all.
  Not verified that the execution id stays the same across one invocation's retries.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

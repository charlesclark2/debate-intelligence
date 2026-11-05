# Session report: v1-e40-t42-schedule-retries-a-refused-launch

| | |
|---|---|
| Task | `v1-e40-t42-schedule-retries-a-refused-launch` — The run's schedule tries again when AWS refuses to launch the task, and never starts a second run |
| Spec | [`plan_specs/v1/e40-cloud-caselist-run/t42-schedule-retries-a-refused-launch.yaml`](../../plan_specs/v1/e40-cloud-caselist-run/t42-schedule-retries-a-refused-launch.yaml) |
| Epic / release | `v1-e40-cloud-caselist-run` / `v1.8` |
| Branch | `task/v1-e40-t42-schedule-retries-a-refused-launch` |
| Session status | IN PROGRESS: waiting for the PM's ruling on the dead-letter alarm (PM ruling of 2026-11-05, point 4) <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

Both caselist schedules, the run's and the login's, now try a launch ECS refused again: three times
at most, all within an hour of the scheduled time (`maximum_retry_attempts = 3`,
`maximum_event_age_in_seconds = 3600`, the PM's ruling of 2026-11-05). On 2026-11-04 the run's
RunTask was answered `ServerException` and nothing tried again; its dead letter shows
`EXHAUSTED_RETRY_CONDITION MaximumRetryAttempts`, which the PM confirmed on AWS's page means the error
was retryable. `run_task.tf` and `login_task.tf` say why a retry cannot make a second run. Because no
AWS page says whether Scheduler counts a RunTask answered with `failures` as a failed invocation, a
new CloudTrail rule, `debate-<env>-caselist-launch-refused`, emails the coach about every RunTask by
either schedule's role that ECS refused or answered with a failure. Its pattern is pinned in tftest
and checked against six invented events. Still open: the PM's ruling on an alarm that fires on each new dead
letter, the operator's purge of the 2026-11-04 message, the coach's word on the 2026-11-04 email, and
dev's plan and apply after the merge. The Goal stays `InProgress`.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `schedule-retries-a-refused-launch` | Built; the dead-letter alarm point waits for the PM's ruling | Tests changed first and shown failing against a skeleton, then the change; `scripts/terraform_checks.sh` passes |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the proposal ruled on before any change | PASS | Proposal relayed 2026-11-05 with the branch at its Start commit (`0db6804`); the PM's ruling of 2026-11-05 came back before the first change (`f756f1b`) |
| ac2: the schedules retry a refused launch as ruled, by Terraform checks shown failing first, with the comments and runbook saying why a retry cannot make a second run | PASS for the schedules, comments and runbooks; the alarm point the PM added waits for its ruling | Red, against a skeleton (retries still 0; a `launch_refused` rule and target that exist and match nothing): `terraform -chdir=infrastructure/modules/caselist_run test` → `Failure! 39 passed, 4 failed`, each an assertion failure: the login's retry (line 866), the run's retry (line 1406), the topic policy's sources (line 1595), and three of the new run's four assertions (pattern 2012, invented events 2036, target 2124). Green: `Success! 43 passed, 0 failed`. Then `bash scripts/terraform_checks.sh` → `All Terraform checks passed.` (fmt, every validate, tflint, eight module tests; 65 s) |
| ac3: the operator reads the dead letter and whether the alarm emailed the coach (before 2026-11-18), and applies dev after the PM reads the plan | Dead letter: PASS (accepted by the PM, 2026-11-05). Email to the coach: NOT RUN, the coach's answer. Plan and apply: NOT RUN, after the merge | See "The 2026-11-04 dead letter" below |
| Node: Retry a refused launch tests pass (`bash scripts/terraform_checks.sh`) | PASS | As in ac2 |

### The 2026-11-04 dead letter (operator, 2026-11-05)

* `debate-dev-caselist-run-dlq`: `ApproximateNumberOfMessages 1`. One message,
  `36c726e5-18a6-48ed-a082-1e3b6d2c9b74`, `SentTimestamp 1793793628165` (2026-11-04 12:00:28Z),
  `SCHEDULED_TIME 2026-11-04T12:00:00Z`, `ERROR_CODE ServerException`, `ERROR_MESSAGE Internal Error.`,
  `RETRY_ATTEMPTS 0`, `EXHAUSTED_RETRY_CONDITION MaximumRetryAttempts`. The body is the RunTask request
  Scheduler sent (task definition `debate-dev-caselist-run:11`, `StartedBy
  chronos-schedule/debate-dev-caselist`), with no `ClientToken`. The read used a visibility timeout of
  0, so the one poll returned the same message ten times (receive count 1 to 10); nothing was deleted.
* `debate-dev-caselist-schedule-failed`: OK to ALARM at 2026-11-04 12:07:55Z, and `Successfully executed
  action` on `debate-dev-caselist-run-alerts` in the same second. Still `ALARM` on 2026-11-05.
* The topic's email subscription is confirmed (a full subscription ARN, not `PendingConfirmation`).
  SNS keeps no record of email delivery: whether the coach received it is the coach's answer.

### Checks before the report

| Command | Result |
|---|---|
| `bash scripts/terraform_checks.sh` | `All Terraform checks passed.` |
| Seven mutants of the change, each restored with `git checkout HEAD --` | All caught: the run scheduler's prefix without its slash, the `failures` branch dropped, the `errorCode` branch dropped, the login scheduler misnamed (each fails both the pinned pattern and the invented events); retries 0 (3 runs fail); event age 86400 (2 runs); the rule left out of the topic policy (1 run) |
| `uv run scripts/affected_tests.py --run` (101 files: tests that name the two runbooks) | Stopped at its 115-second limit (`hard_stop.py`, exit 124): over two minutes, left to the pull request's `ci` (agreement 10) |
| The 16 test files that name `caselist-cloud-run.md` or `caselist-run-alerts.md` | `229 passed in 48.01s` |
| The always-run list (`tests/architecture/`, `tests/specs/`, `test_app.py`, `test_help_rendering.py`, `test_container_factories.py`) | `377 passed in 32.30s` |
| `ruff format --check .`, `ruff check .` | `1953 files already formatted`, `All checks passed!` |
| `pyright` | Not run: no Python changed |
| `lint-imports` | `Contracts: 20 kept, 0 broken.` |
| `scripts/check_links.py`, `scripts/check_command_blocks.py --base origin/dev`, `scripts/docs_index.py --check-descriptions` | All OK |
| `uv run scripts/validate_specs.py` | `OK: 629 files, 41 epics, 566 tasks, 22 releases` |
| Step 5's pattern script in `caselist-run-alerts.md`, parsed with `ast` | Compiles; 20 cases |

## Files changed

* `infrastructure/modules/caselist_run/main.tf`: `schedule_retry_attempts = 3` and
  `schedule_event_age_in_seconds = 3600`, which both schedules and the new email read.
* `infrastructure/modules/caselist_run/run_task.tf`, `login_task.tf`: the retry policy, and the
  comments on why a retry cannot make a second run (and, for the login, why a refused login is still
  never retried).
* `infrastructure/modules/caselist_run/alerts.tf`: the `launch_refused` rule and target, its pattern
  and email, the topic policy admitting it, and the dead-letter comment corrected.
* `infrastructure/modules/caselist_run/tests/caselist_run.tftest.hcl`: both retry assertions, the topic
  policy's sources, the rule's ARN override, and the run
  `a_launch_either_schedule_was_refused_emails_the_coach`.
* `infrastructure/modules/caselist_run/README.md`: "never retried" corrected, the rule listed.
* `docs/runbooks/caselist-cloud-run.md`: "A launch AWS refused", and the run schedule's row.
* `docs/runbooks/caselist-run-alerts.md`: the rule in "What this sets up" and "When an alert arrives";
  its five cases in step 5's check against AWS's matcher (15 to 20); the dead-letter read prints each
  queue's depth first and says that a repeated `MessageId` is one message.

## Deviations from the spec

* **Scope the PM added in the ruling, not yet in the spec**: the `launch-refused` CloudTrail rule
  (point 2) and the dead-letter alarm fix (point 4). The PM adds both to the spec in the next batch.
* **The invented events are judged in HCL, not by AWS's matcher.** Terraform cannot run EventBridge's
  matcher offline, so the tftest run evaluates each invented event against the pattern's own values
  with EventBridge's meaning for the operators this pattern uses (a listed value, `prefix`, `exists`,
  `$or`, a field inside an array of objects). AWS's own answer comes from step 5 of
  `caselist-run-alerts.md` after the apply, which now has the rule's five cases. Its second case, a
  `failures` entry matched inside an array of objects, is the one only AWS can settle.

## Decisions and assumptions

* **One rule for both schedules.** The email names the principal, which says whose role: the login's
  `debate-<env>-caselist-scheduler` or the run's `-run-scheduler`. The trailing slash in each prefix
  keeps a role named like one of them out (tested).
* **One email per refused try.** Each try is its own CloudTrail event, so a launch refused once and
  then started sends one email, and one refused four times sends four, then the alarm. The email says
  that the start is tried again, and the runbook says to wait until 07:00 America/Chicago before acting.
* **CloudTrail's RunTask record is assumed to carry `responseElements.failures`** for an answer with
  failures, as RunTask's own response does. If CloudTrail omitted the response, only the `errorCode`
  branch could match. Step 5 checks the pattern, not CloudTrail's record; the first real capacity
  refusal will show it.
* **No login lock.** As ruled, the login retries too. Two logins within the hour are possible only
  after an ambiguous answer, and ADR-0020 records that a new login does not end another's token.
* **The comment's facts.** As the PM corrected: a run has finished in 56 minutes (2026-10-28), inside
  the event age; the bound holds because a duplicate takes the lock only after the first run has
  finished, and three retries land far earlier than that.

## Operator follow-ups

To come once the alarm point is ruled: the purge has its block below now; dev's plan follows the merge.

**The one-time purge of the 2026-11-04 dead letter** (the PM's ruling, point 4), before 2026-11-11.
This deletes every message in `debate-dev-caselist-run-dlq`; the read above is its record. It is
`caselist-run-alerts.md`'s purge block.

**Operator command** (expected runtime ~1 min)
Where: your Mac, anywhere
```bash
QUEUE='debate-dev-caselist-run-dlq'
URL=$(aws sqs get-queue-url --profile debate-admin --region us-east-1 --queue-name "$QUEUE" --query QueueUrl --output text) && aws sqs purge-queue --profile debate-admin --region us-east-1 --queue-url "$URL" && echo "emptied $QUEUE"
```
Success looks like `emptied debate-dev-caselist-run-dlq`.

**That the alarm returned to OK**, about ten minutes after the purge. Read-only.

**Operator command** (expected runtime under 1 min)
Where: your Mac, anywhere
```bash
aws cloudwatch describe-alarms --profile debate-admin --region us-east-1 --alarm-names debate-dev-caselist-schedule-failed --query 'MetricAlarms[].[StateValue,StateUpdatedTimestamp]' --output text
```
Success looks like `OK` and a time after the purge. Still `ALARM` after twenty minutes: send the PM
the output.

**The coach**: did an email titled `ALARM: "debate-dev-caselist-schedule-failed"` arrive at about 06:07
America/Chicago on 2026-11-04?

## Follow-up work

* **The guard the PM files** (ruling, point 3): a scheduled `caselist pull` refuses when the bucket's
  run log records a run started within N hours (E40, `debate_core`).

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

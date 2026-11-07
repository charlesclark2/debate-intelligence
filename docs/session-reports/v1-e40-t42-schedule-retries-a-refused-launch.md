# Session report: v1-e40-t42-schedule-retries-a-refused-launch

| | |
|---|---|
| Task | `v1-e40-t42-schedule-retries-a-refused-launch` — The run's schedule tries again when AWS refuses to launch the task, and never starts a second run |
| Spec | [`plan_specs/v1/e40-cloud-caselist-run/t42-schedule-retries-a-refused-launch.yaml`](../../plan_specs/v1/e40-cloud-caselist-run/t42-schedule-retries-a-refused-launch.yaml) |
| Epic / release | `v1-e40-cloud-caselist-run` / `v1.8` |
| Branch | `task/v1-e40-t42-schedule-retries-a-refused-launch` |
| Session status | PARTIAL: everything ruled is built and checked; ac3's plan and apply in dev come after the merge, so the Goal stays `InProgress` <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

Both caselist schedules, the run's and the login's, now try a launch ECS refused again: three times
at most, all within an hour of the scheduled time (`maximum_retry_attempts = 3`,
`maximum_event_age_in_seconds = 3600`, the PM's ruling of 2026-11-05). On 2026-11-04 the run's
RunTask was answered `ServerException` and nothing tried again; its dead letter's
`EXHAUSTED_RETRY_CONDITION MaximumRetryAttempts` means, by AWS's page (read by the PM), that the error
was retryable. `run_task.tf` and `login_task.tf` say why a retry cannot make a second run. Because no
AWS page says whether Scheduler counts a RunTask answered with `failures` as a failed invocation, a
new CloudTrail rule, `debate-<env>-caselist-launch-refused`, emails the coach about every RunTask by
either schedule's role that ECS refused or answered with a failure; its pattern is pinned in tftest
and judged against six invented events. The dead-letter alarm counted what a queue held, so it stayed
in `ALARM` while the 2026-11-04 message waited: it now counts messages sent (`NumberOfMessagesSent`, 1
of 6 five-minute periods), in place under the same name, so each new dead letter emails. The
operator read the dead letter, the coach confirmed the 2026-11-04 email, and the operator purged the
queue. Dev's plan and apply come after the merge, so the Goal stays `InProgress`.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `schedule-retries-a-refused-launch` | Done | Every change made test-first, shown failing, then green; `scripts/terraform_checks.sh` passes |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the proposal ruled on before any change | PASS | Proposal relayed 2026-11-05 with the branch at its Start commit (`0db6804`); the PM's ruling of 2026-11-05 came before the first change (`f756f1b`), and its ruling on point 4 before the alarm's (`b30fa4b`) |
| ac2: the schedules retry a refused launch as ruled, by Terraform checks shown failing first, with the comments and runbook saying why a retry cannot make a second run | PASS | **Retries and the rule**, red against a skeleton (retries still 0; a `launch_refused` rule and target that exist and match nothing): `terraform -chdir=infrastructure/modules/caselist_run test` → `Failure! 39 passed, 4 failed`, each an assertion failure: the login's retry (line 866), the run's retry (line 1406), the topic policy's sources (line 1595), and three of the new run's four assertions (pattern 2012, invented events 2036, target 2124). Green: `Success! 43 passed, 0 failed`. **The alarm**, red with the assertion changed alone: `Failure! 42 passed, 1 failed` (line 1847); green: `Success! 43 passed, 0 failed`. Then `bash scripts/terraform_checks.sh` → `All Terraform checks passed.` |
| ac3: the operator reads the dead letter and whether the alarm emailed the coach (before 2026-11-18), and applies dev after the PM reads the plan, the plan after it saying No changes | Dead letter: PASS (the PM records it). The coach's email: PASS (the coach, 2026-11-05; the PM records it). Plan, apply and the plan after: NOT RUN, from `dev` after the merge | Below, and "Operator follow-ups" |
| Node: Retry a refused launch tests pass (`bash scripts/terraform_checks.sh`) | PASS | `All Terraform checks passed.` (fmt, every validate, tflint, the eight modules' tests), last run after the final commit |

### The 2026-11-04 dead letter and its email (2026-11-05)

* `debate-dev-caselist-run-dlq`: `ApproximateNumberOfMessages 1`. One message,
  `36c726e5-18a6-48ed-a082-1e3b6d2c9b74`, `SentTimestamp 1793793628165` (2026-11-04 12:00:28Z),
  `SCHEDULED_TIME 2026-11-04T12:00:00Z`, `ERROR_CODE ServerException`, `ERROR_MESSAGE Internal Error.`,
  `RETRY_ATTEMPTS 0`, `EXHAUSTED_RETRY_CONDITION MaximumRetryAttempts`. The body is the RunTask request
  Scheduler sent (task definition `debate-dev-caselist-run:11`, `StartedBy
  chronos-schedule/debate-dev-caselist`), with no `ClientToken`. The read used a visibility timeout of
  0, so the one poll returned the same message ten times (receive count 1 to 10); nothing was deleted.
* `debate-dev-caselist-schedule-failed`: OK to ALARM at 2026-11-04 12:07:55Z on the 12:01:00Z datapoint
  (1.0 >= 1.0, 1 of 1 periods of 300 s), and its action on `debate-dev-caselist-run-alerts` ran in the
  same second. The subscription is confirmed. **The coach confirmed the email reached the inbox**, 7.5
  minutes after the dead letter. Still `ALARM` on 2026-11-05 before the purge.
* The operator purged `debate-dev-caselist-run-dlq` on 2026-11-05 (the PM's ruling, point 4); the check
  that the alarm is back to `OK` is the operator's, below.

### Checks before the report

| Command | Result |
|---|---|
| `bash scripts/terraform_checks.sh`, after the last commit | `All Terraform checks passed.` |
| Nine mutants, each restored with `git checkout HEAD --` | All caught. The run scheduler's prefix without its slash, the `failures` branch dropped, the `errorCode` branch dropped, the login scheduler misnamed: each fails both the pinned pattern and the invented events. Retries 0: 3 runs fail. Event age 86400: 2 runs. The rule left out of the topic policy: 1 run. The alarm back on `ApproximateNumberOfMessagesVisible`: 1 run. Its `evaluation_periods` back to 1: 1 run |
| `uv run scripts/affected_tests.py --run` (101 files: tests that name the two runbooks) | Stopped at its 115-second limit (`hard_stop.py`, exit 124): over two minutes, left to the pull request's `ci` (agreement 10) |
| The 16 test files that name `caselist-cloud-run.md` or `caselist-run-alerts.md`, after the last commit | `229 passed in 44.42s` |
| The always-run list (`tests/architecture/`, `tests/specs/`, `test_app.py`, `test_help_rendering.py`, `test_container_factories.py`) | `377 passed in 32.30s` |
| `ruff format --check .`, `ruff check .` | `1953 files already formatted`, `All checks passed!` |
| `pyright` | Not run: no Python changed |
| `lint-imports` | `Contracts: 20 kept, 0 broken.` |
| `scripts/check_links.py`, `scripts/check_command_blocks.py --base origin/dev`, `scripts/docs_index.py --check-descriptions` | All OK |
| `uv run scripts/validate_specs.py` | `OK: 629 files, 41 epics, 566 tasks, 22 releases` |
| Step 5's pattern script in `caselist-run-alerts.md`, parsed with `ast` | Compiles; 20 cases |
| The plan check below, against three invented plans | The ruled shape → `PLAN OK`; the same plus an `aws_ssoadmin_account_assignment` deleted → `PLAN STOP` naming it; the run's schedule at 0 retries → `PLAN STOP` naming it |

## Files changed

* `infrastructure/modules/caselist_run/main.tf`: `schedule_retry_attempts = 3` and
  `schedule_event_age_in_seconds = 3600`, which both schedules and the new email read.
* `infrastructure/modules/caselist_run/run_task.tf`, `login_task.tf`: the retry policy, and the
  comments on why a retry cannot make a second run (and, for the login, why a refused login is still
  never retried).
* `infrastructure/modules/caselist_run/alerts.tf`: the `launch_refused` rule and target, its pattern
  and email, the topic policy admitting it; the dead-letter alarm on `NumberOfMessagesSent`, with why it
  counts arrivals and not the backlog SQS's page recommends; the dead-letter comment corrected.
* `infrastructure/modules/caselist_run/tests/caselist_run.tftest.hcl`: both retry assertions, the topic
  policy's sources, the rule's ARN override, the run
  `a_launch_either_schedule_was_refused_emails_the_coach`, and the alarm's assertion.
* `infrastructure/modules/caselist_run/README.md`: "never retried" corrected; the rule and the alarm's
  metric.
* `docs/runbooks/caselist-cloud-run.md`: "A launch AWS refused", and the run schedule's row.
* `docs/runbooks/caselist-run-alerts.md`: the rule in "What this sets up" and "When an alert arrives";
  the alarm counting arrivals, and the two schedules never sharing its window; the 2026-11-04 alert as
  the example of an arriving one and its timing; its five cases in step 5's check against AWS's
  matcher (15 to 20); the dead-letter read prints each queue's depth first and says that a repeated
  `MessageId` is one message; emptying a queue is housekeeping.

## Deviations from the spec

* **Scope the PM added in the rulings, not yet in the spec**: the `launch-refused` CloudTrail rule
  (point 2) and the dead-letter alarm counting arrivals (point 4). The PM adds both to the spec in the
  next batch.
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
* **The alarm's timing in the runbook** is the 2026-11-04 example (7.5 minutes), measured on the
  depth alarm. The arrivals alarm reads the same five-minute datapoint, so "within about ten minutes"
  holds for it; its email says `1 out of the last 6 datapoints`.
* **The `owner.auto.tfvars` check below prints each line's count** rather than one total, because
  `bedrock_invoker_user_names` (v1-e05-t08) came after the earlier runbooks' count of 8. The plan's
  `aws_ssoadmin` check is the backstop either way.

## Operator follow-ups

**Now, about ten minutes after the purge**: that the alarm returned to `OK`. Read-only.

**Operator command** (expected runtime under 1 min)
Where: your Mac, anywhere
```bash
aws cloudwatch describe-alarms --profile debate-admin --region us-east-1 --alarm-names debate-dev-caselist-schedule-failed --query 'MetricAlarms[].[StateValue,StateUpdatedTimestamp]' --output text
```
Success looks like `OK` and a time after the purge. Still `ALARM` after twenty minutes: send the PM
the output.

### Dev's plan, after this task merges into `dev`

Never on a task branch, and the apply never on a Wednesday. The plan goes to the PM before any apply.
A plan of another shape than 2 to add, 4 to change, 0 to destroy goes to the PM, and a plan that
destroys or replaces an account assignment or a permission set is never applied.

**The worktree the earlier dev applies used**, moved to `origin/dev`, and the check that this task is
merged in it. Its gitignored `owner.auto.tfvars` is the one every dev apply used.

**Operator command** (expected runtime ~1 min)
Where: your Mac
```bash
WT="$HOME/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/caselist-credentials-dev"
cd "$WT" || { echo "WT does not exist: $WT"; }
git fetch origin
git switch --detach origin/dev
grep -q 'resource "aws_cloudwatch_event_rule" "launch_refused"' infrastructure/modules/caselist_run/alerts.tf && echo "ok: $(pwd) at origin/dev $(git rev-parse --short HEAD), v1-e40-t42 merged" || echo "NOT MERGED: origin/dev has no launch_refused rule; wait for v1-e40-t42 to merge"
git status --porcelain | grep -v 'owner.auto.tfvars' | head -3
```
Success looks like `ok: <the worktree> at origin/dev <commit>, v1-e40-t42 merged`, and nothing after it.

**Sign in as break-glass**, and check `owner.auto.tfvars` still names everyone and an image.

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
aws sso login --sso-session debate
aws sts get-caller-identity --profile debate-admin --query Arn --output text
for V in owner site_publisher_user_names evidence_operator_user_names evidence_removal_user_names evidence_search_deployer_user_names evidence_search_accounts_user_names caselist_credential_writer_user_names caselist_run_deployer_user_names bedrock_invoker_user_names caselist_image_digest; do printf '%s %s\n' "$V" "$(grep -cE "^${V} +=" infrastructure/envs/dev/owner.auto.tfvars)"; done
```
Success looks like an ARN containing `AWSReservedSSO_DebateBreakGlassAdmin`, then each name followed by
`1`. A `0` means a line is missing, and a plan without it would remove someone's account assignment:
find it in the checkout that last applied dev before planning. (`bedrock_invoker_user_names 0` is
right only if dev never had a Bedrock invoker; the plan check stops on any change to an assignment.)

**The plan**, saved to a file so the apply is exactly what was read.

**Operator command** (expected runtime ~2 min)
Where: `$WT`
```bash
cd "$WT"
if env | grep -qE '^(TF_VAR_|TF_WORKSPACE=|TF_DATA_DIR=|TF_CLI_ARGS)'; then echo "STOP: a Terraform override is set in this shell"; else AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev init -input=false >/dev/null && AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev plan -input=false -no-color -out=caselist-launch-retry.tfplan | tee /tmp/caselist-launch-retry-plan.txt | tail -5; fi
grep -E '^Plan:|must be replaced|will be destroyed' /tmp/caselist-launch-retry-plan.txt
grep -c 'aws_ssoadmin' /tmp/caselist-launch-retry-plan.txt
```
Success looks like `Plan: 2 to add, 4 to change, 0 to destroy.`, nothing saying `must be replaced` or
`will be destroyed`, and `0`.

**The plan checked against exactly that shape**: the launch-refused rule and its target added; the
topic policy, both schedules and the alarm changed in place; both schedules at 3 tries within 3600 s
and the alarm on `NumberOfMessagesSent`, 1 of 6, after the apply; nothing else. It prints `PLAN STOP`
with the reason for anything else.

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev show -json caselist-launch-retry.tfplan > /tmp/caselist-launch-retry-plan.json
python3 -I - /tmp/caselist-launch-retry-plan.json <<'PLANCHECK'
import json, sys
plan = json.load(open(sys.argv[1]))
m = "module.caselist_run."
expected_creates = {m + "aws_cloudwatch_event_rule.launch_refused", m + "aws_cloudwatch_event_target.launch_refused"}
expected_updates = {m + a for a in ["aws_sns_topic_policy.alerts", "aws_scheduler_schedule.login[0]", "aws_scheduler_schedule.run[0]", "aws_cloudwatch_metric_alarm.schedule_failed"]}
changes = [c for c in plan.get("resource_changes", []) if c["change"]["actions"] not in (["no-op"], ["read"])]
by_address = {c["address"]: c for c in changes}
creates = {a for a, c in by_address.items() if c["change"]["actions"] == ["create"]}
updates = {a for a, c in by_address.items() if c["change"]["actions"] == ["update"]}
others = sorted(a + " " + "/".join(c["change"]["actions"]) for a, c in by_address.items() if a not in creates and a not in updates)
problems = []
if any("aws_ssoadmin" in a for a in by_address):
    problems.append("an account assignment or permission set changes: " + str(sorted(a for a in by_address if "aws_ssoadmin" in a)))
if others:
    problems.append("replaced or destroyed: " + str(others))
if creates - expected_creates or expected_creates - creates:
    problems.append("adds " + str(sorted(creates)) + ", expected " + str(sorted(expected_creates)))
if updates - expected_updates or expected_updates - updates:
    problems.append("changes " + str(sorted(updates)) + ", expected " + str(sorted(expected_updates)))
for which in ["login", "run"]:
    after = by_address.get(m + "aws_scheduler_schedule.%s[0]" % which, {}).get("change", {}).get("after") or {}
    policy = ((after.get("target") or [{}])[0].get("retry_policy") or [{}])[0]
    if (policy.get("maximum_retry_attempts"), policy.get("maximum_event_age_in_seconds")) == (3, 3600):
        continue
    problems.append("the %s schedule's retry policy after the apply is %s, expected 3 tries within 3600 s" % (which, policy))
alarm = by_address.get(m + "aws_cloudwatch_metric_alarm.schedule_failed", {}).get("change", {}).get("after") or {}
metrics = sorted({q["metric"][0]["metric_name"] for q in alarm.get("metric_query", []) if q.get("metric")})
if metrics == ["NumberOfMessagesSent"] and alarm.get("evaluation_periods") == 6 and alarm.get("datapoints_to_alarm") == 1:
    pass
else:
    problems.append("the alarm after the apply counts %s over %s periods, expected NumberOfMessagesSent, 1 of 6" % (metrics, alarm.get("evaluation_periods")))
print("PLAN STOP: " + "; ".join(problems) if problems else "PLAN OK: 2 to add, 4 to change, 0 to destroy, as v1-e40-t42 expects")
PLANCHECK
```
Success looks like `PLAN OK: 2 to add, 4 to change, 0 to destroy, as v1-e40-t42 expects`. Send the PM
the whole plan (`/tmp/caselist-launch-retry-plan.txt`) and this line, and apply only after the PM's word.

**The apply**, after the PM's word, from the same shell. It refuses on a Wednesday in America/Chicago.

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
if [ "$(TZ=America/Chicago date +%u)" = 3 ]; then echo "STOP: it is Wednesday in America/Chicago, the cloud run's day; apply another day"; else AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev apply -input=false -no-color caselist-launch-retry.tfplan | tail -3; fi
```
Success looks like `Apply complete` with `Resources: 2 added, 4 changed, 0 destroyed.`

**The plan after it**, which must say there is nothing left to do.

**Operator command** (expected runtime ~2 min)
Where: `$WT`
```bash
cd "$WT"
AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev plan -input=false -no-color | grep -E '^No changes|^Plan:'
```
Success looks like `No changes. Your infrastructure matches the configuration.` Any `Plan:` line goes
to the PM.

**Then the rule's pattern against AWS's own matcher**: the block in
[caselist-run-alerts.md, step 5](../runbooks/caselist-run-alerts.md#step-5--each-rules-pattern-against-awss-own-matcher),
as written there. Success looks like twenty `ok` lines and `PATTERNS OK: 20 of 20`; any `FAIL` goes to
the PM.

## Follow-up work

* **The guard the PM files** (ruling, point 3): a scheduled `caselist pull` refuses when the bucket's
  run log records a run started within N hours (E40, `debate_core`).
* **Prod**, at the pilot's promotion: the same apply against `infrastructure/envs/prod` from `main`,
  as caselist-run-alerts.md's prod section says.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-05

**Notes:**

Built exactly as ruled, and the two gaps the proposal found (a refusal no page says Scheduler retries,
and an alarm that could not fire twice) are closed in the same module rather than left as notes.

1. **ac1 passes.** The proposal came with the branch at its start commit, and both rulings came before
   the changes they govern (`f756f1b`, and `b30fa4b` for the alarm).
2. **ac2 passes.** Red against a skeleton (4 failed, each an assertion: both retries, the topic policy,
   the new run), green at 43; the alarm red alone (1 failed), green at 43; `terraform_checks.sh` passes.
   Nine mutants caught, including the trailing slash that keeps a similarly named role out, each branch
   of the `$or`, the event age, and the alarm's metric and periods. The comments in run_task.tf and
   login_task.tf carry the corrected facts (the 56-minute run of 2026-10-28; the lock as the bound).
3. **ac3, first half, passes:** the dead letter read without deleting it, the coach's confirmation that
   the 2026-11-04 email arrived (7.5 minutes after the dead letter), and the queue purged. The PM records
   all three in the next batch. The plan, apply and the plan after come from `dev` after the merge.
4. **The scope the rulings added** (the `launch-refused` rule; the alarm counting arrivals) is accepted,
   and the PM writes both into the spec in the next batch.
5. **Deviation accepted:** the invented events judged in HCL. Only AWS's matcher settles the
   array-of-objects case (`failures[].reason`), and step 5 of caselist-run-alerts.md runs it after the
   apply. A FAIL there on that case comes back to the PM before anything else changes.
6. **Two things the first real event will show, no task now:** whether CloudTrail's RunTask record
   carries `responseElements.failures` (the report's stated assumption), and how the email renders a
   path the event lacks (`<error>` on a failures refusal, `<failure>` on an error). If either reads
   badly, the PM files the fix then.
7. **The plan hand-off is right:** counts only from `owner.auto.tfvars`, the expected shape checked by
   script, `aws_ssoadmin` at 0, the apply from a saved plan, never on a Wednesday, and the plan after
   it. A `PLAN STOP` comes to the PM with the whole plan.
8. **Follow-ups:** the guard against a second scheduled run within N hours (ruling 3) is filed by the PM
   (E40). Prod at the pilot's promotion, as caselist-run-alerts.md's prod section says.
9. **Closing checks:** the Terraform checks, the 16 test files naming the two runbooks (229 passed), the
   always-run list (377), ruff, lint-imports, links, command blocks, the docs index and the specs are
   clean; the 101-file affected set is the pull request's `ci` (agreement 10).
10. **Merge:** `scripts/task pr --partial` once `ci` is green. The Goal stays `InProgress` until dev's
    apply and the plan after it are recorded.

## Operator records (recorded by the PM, 2026-11-05)

Added by the PM. Nothing above is changed, and this section is not a review.

| Criterion | Was | Now | Record |
|---|---|---|---|
| ac3, first half: the operator reads the dead letter and whether the alarm emailed the coach (before 2026-11-18) | NOT RUN (operator) | PASS | Read 2026-11-05 without deleting: one message in debate-dev-caselist-run-dlq, sent 2026-11-04 12:00:28Z, ERROR_CODE ServerException, RETRY_ATTEMPTS 0, EXHAUSTED_RETRY_CONDITION MaximumRetryAttempts, the RunTask request for debate-dev-caselist-run:11 with no ClientToken. The alarm went OK to ALARM at 12:07:55Z on the 12:01:00Z datapoint, and the coach confirmed the email reached his inbox, about 7.5 minutes after the dead letter. The operator purged the queue on 2026-11-05 as ruled, and the alarm read OK at 2026-11-05 07:06:12Z |

ac3's second half (dev's plan read by the PM, the apply, and the plan after it saying No changes) runs from `dev` after the merge, so the Goal stays `InProgress`. The guard against a second scheduled run within N hours (ruling 3) is filed as `v1-e40-t44`.

## Operator records (recorded by the PM, 2026-11-06)

Added by the PM. Nothing above is changed, and this section is not a review.

| Criterion | Was | Now | Record |
|---|---|---|---|
| ac3, second half: dev applied after the PM reads the plan, and the plan after it saying No changes | NOT RUN | PASS | 2026-11-06, in one dev plan with the docx-9 run image and v1-e32-t54's grant: Plan 4 to add, 7 to change, 2 to destroy. check_image_plan.py stopped on the changes beyond an image's, as it must, and the PM read every changed field: the launch-refused rule and its target created, the alarm summing NumberOfMessagesSent over 6 periods, the SNS policy, both schedules' maximum_retry_attempts 0 to 3 with their state unchanged. Applied; a plan after it read `No changes`, and the schedule reads ENABLED |

Every criterion passes, so the Goal is `Succeeded`.

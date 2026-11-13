# Session report: v1-e40-t48-the-schedule-passes-scheduled

| | |
|---|---|
| Task | `v1-e40-t48-the-schedule-passes-scheduled` — The weekly schedule starts its pull with --scheduled, so the recent-run guard is live |
| Spec | [`plan_specs/v1/e40-cloud-caselist-run/t48-the-schedule-passes-scheduled.yaml`](../../plan_specs/v1/e40-cloud-caselist-run/t48-the-schedule-passes-scheduled.yaml) |
| Epic / release | `v1-e40-cloud-caselist-run` / `v1.8` |
| Branch | `task/v1-e40-t48-the-schedule-passes-scheduled` |
| Session status | IN PROGRESS <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

<!-- 3-6 sentences: what was built, how it fits the epic, anything the PM should look at first. -->

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

### 1. What AWS's documentation says about Input on the templated ECS target (read 2026-11-13)

The session read these pages on 2026-11-13, before writing any change:

* **"Using templated targets in EventBridge Scheduler"**,
  <https://docs.aws.amazon.com/scheduler/latest/UserGuide/managing-targets-templated.html>. It lists
  "Amazon ECS – `RunTask`, Parameters: `EcsParameters`", and says a templated target takes "the ARN of
  the execution role, the ARN for target resource, an optional input that you want EventBridge
  Scheduler to deliver to the target, and for some templated targets, a unique set of parameters".
  Its examples are SQS, Lambda and Step Functions. It has no ECS example, and says nothing about what
  Input becomes in a RunTask.
* **"Target"** (Scheduler API reference),
  <https://docs.aws.amazon.com/scheduler/latest/APIReference/API_Target.html>, on Input: "The text, or
  well-formed JSON, passed to the target. If you are configuring a templated Lambda, AWS Step
  Functions, or Amazon EventBridge target, the input must be a well-formed JSON. For all other target
  types, a JSON is not required. If you do not specify anything for this field, EventBridge Scheduler
  delivers a default notification to the target." It says nothing about ECS. CloudFormation's
  **"AWS::Scheduler::Schedule Target"** page has the same text.
* **"EcsParameters"**, <https://docs.aws.amazon.com/scheduler/latest/APIReference/API_EcsParameters.html>:
  TaskDefinitionArn, CapacityProviderStrategy, EnableECSManagedTags, EnableExecuteCommand, Group,
  LaunchType, NetworkConfiguration, PlacementConstraints, PlacementStrategy, PlatformVersion,
  PropagateTags, ReferenceId, Tags, TaskCount. It has no overrides field and does not mention Input.
* **"Using Amazon EventBridge Scheduler to schedule Amazon ECS tasks"** (ECS developer guide),
  <https://docs.aws.amazon.com/AmazonECS/latest/developerguide/tasks-scheduled-eventbridge-scheduler.html>:
  console steps only ("Choose All APIs ... Amazon ECS ... RunTask"). Nothing on Input or overrides.
* **"Using universal targets in EventBridge Scheduler"**,
  <https://docs.aws.amazon.com/scheduler/latest/UserGuide/managing-targets-universal.html>: Arn is
  "`arn:aws:scheduler:::aws-sdk:{{service}}:{{apiAction}}`", and Input is "A well-formed JSON you
  specify with the request parameters that EventBridge Scheduler sends to the target API. The
  parameters and shape of the JSON you set in `Input` are determined by the service API your schedule
  invokes."
* **"RunTask"** (ECS API reference),
  <https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_RunTask.html>:
  `overrides.containerOverrides[].name` and `.command`. On `taskDefinition`: "The full ARN value must
  match the value that you specified as the `Resource` of the principal's permissions policy."

**The answer: no AWS page says whether a templated ECS target's Input reaches RunTask as overrides,
and none says it is ignored.** The documentation does not establish t44's proposal, so by the PM's
rule the change would use the universal target, `arn:aws:scheduler:::aws-sdk:ecs:runTask`, with
the whole RunTask request as Input. The session stopped here for the PM's word (relay below) before
writing the change.

**What the universal target changes:**

* **The scheduler role's policy: nothing.** The universal target still calls `ecs:RunTask`, on the same
  revision's ARN (Input names `taskDefinition` by the full ARN, which RunTask requires to match the
  policy's Resource). It runs on the same cluster (Input names `cluster` by its ARN, so `ecs:cluster`
  still holds), passes the same two roles (`iam:PassRole`), and sends failed starts to the same
  dead-letter queue (`sqs:SendMessage`). There are no tags and no `propagateTags`, so no `ecs:TagResource`.
* **The target block.** `arn` becomes the universal ARN and `ecs_parameters` goes. `input` carries
  `cluster`, `taskDefinition`, `count`, `launchType`, `platformVersion`, `enableExecuteCommand`,
  `enableECSManagedTags`, `networkConfiguration.awsvpcConfiguration` and
  `overrides.containerOverrides`. `retry_policy` and `dead_letter_config` stay. The two alert rules
  (launch refused, task stopped) match on the RunTask caller and the task family, so neither changes.
* **The combined plan cannot show the command.** The same plan replaces the run task definition, so
  its new ARN is unknown until the apply, and so is the whole `input` string
  ("known after apply"). The module's test pins the command instead, and a read of the schedule after
  the apply shows it. A templated target with `input` would show the command in the plan.
* **`ops/caselist_run/check_image_plan.py`.** For every later image plan, the run schedule's revision
  moves from `ecs_parameters.task_definition_arn` into the `input` string, so the check has to learn the
  new shape (`ops` is in the task's packages).
* **The Input's field casing is not settled by the documentation.** The universal page says the shape
  "is determined by the service API", which for ECS is camelCase (`cluster`, `taskDefinition`). Its own
  Step Functions example writes `"StateMachineArn"` and `"Input"`, though that API's members are
  `stateMachineArn` and `input`. A wrong guess fails every start: three retries, the dead-letter queue,
  the launch-refused email at 06:00, and no week until a hand run.

### 2. The image, and the environments (read-only, 2026-11-13)

* **Build and push:** `scripts/caselist_run_deploy.sh <dev|prod> <release tag>` (the runbook's Step 5 and
  "A new image, later"). It builds, checks and pushes, registers a run revision for hand runs, and
  writes the `caselist_image_digest` line to `/tmp/caselist-run-deploy.txt`. Prod takes only a stable
  `vX.Y.Z` from a clean `main`. The runbook's "Replacing the digest line" block changes only that line.
* **Dev pins `v1.1.0-dev.380`.** Revision 15 ran the scheduled run of 2026-11-11 (v1-e40-t09's report).
  No later image apply is recorded. From git: `--scheduled` is absent in `v1.1.0-dev.380` and
  `v1.1.0-dev.422`. It first appears in `v1.1.0-dev.423` (2026-11-12, t44's merge `b99b8d6`) and is
  present in the newest, `v1.1.0-dev.431`. The session did not read `owner.auto.tfvars`, which is not
  in the main checkout.
* **Environments:** `infrastructure/envs/dev/caselist_run.tf` and `infrastructure/envs/prod/caselist_run.tf`
  both call the module, character for character the same. Dev is the run's home (ADR-0020 (7)). Prod's
  run task and schedules exist only once prod's `caselist_image_digest` is set. The repo records no prod
  apply B ("Prod, at the pilot's promotion (follow-up)").

## Operator follow-ups

<!-- Commands the operator must run (anything over ~2 minutes), with where to run them, the exact
command, expected runtime and what success looks like. Also GitHub/AWS settings to change. -->

None.

## Follow-up work

<!-- Bugs, gaps or ideas outside this task's scope, each with the task or epic it belongs to.
The PM decides whether they become spec changes or new tasks. -->

None.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

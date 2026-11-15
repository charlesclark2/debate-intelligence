# Session report: v1-e40-t48-the-schedule-passes-scheduled

| | |
|---|---|
| Task | `v1-e40-t48-the-schedule-passes-scheduled` — The weekly schedule starts its pull with --scheduled, so the recent-run guard is live |
| Spec | [`plan_specs/v1/e40-cloud-caselist-run/t48-the-schedule-passes-scheduled.yaml`](../../plan_specs/v1/e40-cloud-caselist-run/t48-the-schedule-passes-scheduled.yaml) |
| Epic / release | `v1-e40-cloud-caselist-run` / `v1.8` |
| Branch | `task/v1-e40-t48-the-schedule-passes-scheduled` |
| Session status | COMPLETE for a session. The Goal stays `InProgress`: ac1's plan and the PM's read of it, and ac2's Wednesday run, are the operator's after the merge <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The weekly run's schedule now starts its pull as `--json caselist pull --scheduled`, so v1-e40-t44's
recent-run guard goes live at dev's next apply. AWS's Scheduler pages do not say a templated ECS
target's Input reaches RunTask as overrides (Decision 1, read 2026-11-13). By the PM's ruling of
2026-11-14 the schedule is therefore Scheduler's universal target, `arn:aws:scheduler:::aws-sdk:ecs:runTask`,
whose Input is the whole RunTask request in RunTask's camelCase. The scheduler role's policy is
unchanged, and a run started by hand keeps the task definition's command.

`ops/caselist_run/check_image_plan.py` gains `--universal-target` for the one plan that moves the
schedule, and its image and memory modes read the universal shape for every later plan. The runbook
gains the steps in run order: push, digest, one plan, apply, read-back, a one-off dry run in dev that
proves the field names, and ac2's read on Wednesday. Its sentence that the guard is inert comes out.

**The Goal stays `InProgress`.** ac1's plan diff and the PM's read of it come from the operator's
plan after this merges, and ac2 is the scheduled run of Wednesday 2026-11-18. Both are NOT RUN below.
Read first: the Input's field casing is proved only by the one-off dry run (Decision 4). A fail there
is the PM's ruling before Wednesday: the other casing, or the templated target again.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `the-schedule-passes-scheduled` (Schedule passes --scheduled) | Done | Documentation read and the PM's word (stop 1); the universal target in `run_task.tf` with its plan-time test; the image plan check's universal shape; the runbook section; the backfile test narrowed. Red runs and mutants below. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the schedule's target passes `--scheduled`, shown by the plan's diff and a plan-time test, with the documentation's answer on input recorded, and the PM has read the plan before the operator's apply | NOT RUN (the plan and the PM's read are after the merge) | **Documentation's answer: recorded** (Decision 1). **Plan-time test: PASS.** `run "the_run_schedule_starts_its_pull_with_scheduled"` in `infrastructure/modules/caselist_run/tests/caselist_run.tftest.hcl` (`command = plan`, ids given during the plan) pins the universal ARN, no `ecs_parameters`, and the whole Input by hand. Red against the module before `0864d11`: `TF_CLI_CONFIG_FILE=<mirror> TF_DATA_DIR=<scratch> terraform -chdir=infrastructure/modules/caselist_run test -no-color` → **43 passed, 1 failed** (its three target assertions; nothing skipped). Green: **44 passed, 0 failed**. Its plan-time evaluation was probed with a wrong dead-letter ARN: 43 passed, 1 failed, at that assertion. **The plan's diff and the PM's read:** the operator's plan, Operator follow-up 7; its Input shows `(known after apply)` (the PM's ruling (b)). |
| ac2: the operator's first scheduled run after the apply records a pull started with `--scheduled` | NOT RUN (Wednesday 2026-11-18) | Operator follow-ups 16 and 17: CloudTrail's RunTask by `debate-dev-caselist-run-scheduler` whose command ends in `--scheduled`, and that week's run record (the PM's ruling Q4). |
| Node: Schedule passes --scheduled tests pass (`uv run pytest tests/infrastructure -k schedule`) | PASS | `.venv/bin/python scripts/hard_stop.py 115 uv run pytest tests/infrastructure -k schedule` → **54 passed in 1.94s**. All 54 are `test_the_schedule_passes_scheduled.py`'s. |

**Red runs, each before its change.**

* The module's source tests, against `run_task.tf` before `0864d11`: `... -m pytest tests/infrastructure/test_the_schedule_passes_scheduled.py -n 0 -k "command or universal_run_task or by_hand"` → **2 failed, 1 passed**. The one that passes, `test_a_run_by_hand_keeps_the_task_definitions_command`, pins what must not change.
* The check's tests, against a skeleton that accepted `--universal-target` and checked nothing new: `... -m pytest tests/infrastructure/test_the_schedule_passes_scheduled.py -n 0` → **20 failed, 14 passed**. The 14: the 3 source tests (the module was already committed); the cases today's check already refuses with the expected message (a replace, a state, a schedule setting, the run task definition updated, Identity Center, outside the module, the flag beside `--memory`); the template's known-revision rule; and the later-plan cases "another role" and "templated ECS parameters added".
* The runbook's tests, against the runbook before `a569f8d`: the same file → **20 failed, 34 passed**.
* Green after each: **54 passed**. `tests/scripts/test_caselist_run_image_plan_check.py`, unchanged: **84 passed**, the same as before. Together they made the 118 of the first green run.

**Mutants** (agreement 10: the module that holds the logic, the test files that cover it). Each was
applied in place, both test files run with `-n 0`, then restored. No Hypothesis is involved.

| Mutant | Result |
|---|---|
| `run_task.tf`: `run_scheduled_command` without `--scheduled` (the PM's) | `terraform test`: **42 passed, 2 failed, 0 skipped** (`the_run_schedule_starts_its_pull_with_scheduled`, `no_schedule_starts_a_backfile_import`); and `test_the_schedules_command_is_the_pull_with_scheduled` reads the same line |
| check: templated parameters left beside the universal target allowed | 1 failed (`[the templated ECS parameters left beside the universal target]`) |
| check: the move's other target settings not compared | 2 failed (another role; the retries dropped) |
| check: the move's shape pair not required | 4 failed |
| check: a known Input treated as the new revision | 5 failed |
| check: a target moving between shapes allowed in the image and memory modes | 5 failed |
| check: universal targets not compared beyond the Input | 4 failed |
| check: the universal ARN matching any ECS API | 1 failed (`[a universal target for another API]`) |
| check: `--universal-target` ignored for the run schedule | 8 failed |

Every result above is an assertion failure on the check's `PLAN` line. No mutant made the script
crash: the runner asserts an empty stderr.

**Before the report** (agreement 10):

* `.venv/bin/python scripts/hard_stop.py 115 uv run scripts/affected_tests.py --run --slow` → `120 of 765 test files (15.7%) chosen`. **Stopped at its 115-second limit (exit 124) at 61% of 3,990 tests, with no failure**, at a load average near 25 from other work on the Mac. Over two minutes, so the whole affected set is left to the pull request's `ci` check, as agreement 10 says. Within the bound instead:
  * every package test that reads `caselist-cloud-run.md` (14 files) → **171 passed in 39.65s**;
  * `tests/architecture tests/specs tests/infrastructure tests/docs tests/scripts/test_caselist_run_image_plan_check.py -m "not slow and not live"` → **763 passed in 10.20s**;
  * the changed test files with `-m slow` → **158 deselected**, none slow.
* `uv run --frozen ruff format --check .` → `2114 files already formatted`; `uv run --frozen ruff check .` → `All checks passed!`
* `uv run --frozen pyright` (the whole project, as CI) → `0 errors, 0 warnings, 0 informations`. No package under `packages/` changed.
* `uv run --frozen lint-imports` → `Contracts: 20 kept, 0 broken.`
* `uv run scripts/validate_specs.py` → `OK: 685 files, 41 epics, 622 tasks, 22 releases`, no warning naming t48.
* `uv run scripts/check_command_blocks.py` → `OK: no # comments in 719 shell code blocks in 259 Markdown files`; `uv run --frozen python scripts/check_links.py` → `OK: 3880 relative links and anchors in 667 Markdown files`.
* `TF_CLI_CONFIG_FILE=<the mirror rc> bash scripts/terraform_checks.sh`, offline from the main checkout's provider mirror → `All Terraform checks passed.`, exit 0, 42 s. The `.terraform` directories it left were removed, and no lock file changed.

## Files changed

* `infrastructure/modules/caselist_run/run_task.tf`: the schedule's target is the universal RunTask target. `run_task_request` is the RunTask request in camelCase, and `run_scheduled_command` its command. The comments that called the guard a follow-up are updated.
* `infrastructure/modules/caselist_run/tests/caselist_run.tftest.hcl`: the plan-time run `the_run_schedule_starts_its_pull_with_scheduled`. Two runs that read the templated `ecs_parameters` now read the Input: `the_run_schedule_starts_after_the_login_and_is_disabled_by_default` and `no_schedule_starts_a_backfile_import`.
* `ops/caselist_run/check_image_plan.py`: `--universal-target`, the universal shape in the image and memory modes, and `known_revision` reading both shapes.
* `docs/runbooks/caselist-cloud-run.md`: the new section "The schedule passes --scheduled (`v1-e40-t48`), once". The inert-guard paragraph of "A scheduled run refused after a recent run" is removed, and the memory section's old read-back gains a note.
* `tests/infrastructure/test_the_schedule_passes_scheduled.py` (new): the module's source, the check's universal shape, and the runbook's blocks.
* `tests/docs/test_backfile_import_plan_check.py`: allows the run schedule's one input (Deviation 1).
* This report.

## Deviations from the spec

1. **`tests/docs/test_backfile_import_plan_check.py` changed, outside the task's packages.** v1-e40-t09's
   test refused any `input =` in the Terraform, as the way a schedule would start a backfile import.
   This task has to add one. It now allows exactly `input    = jsonencode(local.run_task_request)` in
   `run_task.tf`, still requires that `run_task.tf` names no backfile, and its name says so. The
   module change failed it (1 failed, 356 passed over `tests/docs` and the image check's tests). An
   input planted on the login's schedule fails it again (1 failed, 19 passed).
2. **The check's new tests are in `tests/infrastructure`, not `tests/scripts`.** `tests/scripts` is not in
   the spec's packages, so they import the existing file's synthetic plans, which stays unchanged.
3. **The plan-time test is Terraform's, and the pytest reads the source.** The spec's node runs
   `pytest tests/infrastructure -k schedule`, and the brief asks for a plan-time test "following the
   module's existing test pattern". The plan-time test is a `command = plan` run in the module's
   `.tftest.hcl`, which CI's `terraform-checks` job runs. CI's Python tests have no Terraform and no
   network, so the pytest file reads `run_task.tf` as text, the way
   `test_model_spend_budget_grants_nothing.py` reads its module, beside the check's and the
   runbook's tests.
4. **The PM's brief of 2026-11-14 forbade a plan that "replaces ... the task definition".** That wording
   is superseded by the PM's ruling Q2 the same day. The task definitions may be replaced, as every
   image plan replaces them. Their roles, the scheduler role, the schedule itself (updated in place)
   and any account assignment may not be.
5. **The image mode refuses a known revision under the universal shape only.** Under the universal
   target an Input the plan already knows names a revision registered earlier, so every mode refuses
   it. Under the ECS template the image mode still does not; that is v1-e41-t13's rule (Pending), and
   nothing the image mode passes today changes.

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
the whole RunTask request as Input. The session stopped here for the PM's word before writing the
change; the PM ruled on 2026-11-14 (Decision 3).

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

### 3. The PM's rulings of 2026-11-14, as applied

* **Q1: A, plus C.** The universal target in camelCase from the RunTask reference
  (<https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_RunTask.html>, read 2026-11-13). The
  scheduler role's policy is unchanged (a). The combined plan shows the Input as known after apply,
  and the plan-time test pins it (b). The read-back prints only the target's ARN and the Input's
  command, and runs before the next scheduled run. The check learns the universal shape, with tests
  shown failing first (c). And a one-off dry run in dev after the apply proves the field names (C).
* **Q2:** the spec's forbidden list governs (Deviation 4).
* **Q3:** dev's plan carries the image, the digest and the schedule together. The PM reads it, and the
  operator applies it on Sunday 2026-11-15 or Monday 2026-11-16, never a Wednesday. The read-back and
  the one-off follow the same day, and Tuesday is left for a fix. The home stays in dev for 2026-11-18.
  Prod's part rides in the promotion's plan if this merges before the promotion's cut, with prod's
  schedule created with the new target and disabled; otherwise it waits for the next promotion.
* **Q4:** ac2's evidence is CloudTrail's RunTask by `debate-<env>-caselist-run-scheduler` on 2026-11-18
  whose command ends in `--scheduled`, plus that week's run record. The read prints only the event's
  time, the role's name, the command and the task id, and the same read is the one-off's evidence.

### 4. The one-off dry run: what it touches, and why it does not carry `--scheduled`

Confirmed from the code before writing it. In bucket mode `PullBracket.start(dry_run=True)` restores
the bucket's copy into the task's own data directory and returns: no lock is taken
(`packages/debate_core/src/debate_core/application/caselist/bucket_run.py`, "A dry run reads and takes
nothing"). `finish` and `after_run` return at once without a lock, so no bundle or state file is saved.
`SyncService.run(dry_run=True)` plans the remaining stages instead of `_execute`, so nothing is
downloaded. The selection reads the download ledger and never spends from it, retention removes
nothing, and no summary is written (`caselist_sync.py`). `run_pull`'s dry-run branch never reaches the
monitor, so no run record ("A dry run writes nothing (v1-e34-t02 ac2), so it leaves no run record
either"). It does list OpenCaselist with the token, as Step 7's rehearsal did.

**It cannot carry `--scheduled`:** `--scheduled --dry-run` is a usage error, exit 2, before anything
runs (`debate_cli/commands/caselist_pull.py`, `_refuse_a_scheduled_pull_it_cannot_guard`; t44's ruling
2). So the one-off runs `--json caselist pull --dry-run`. It proves the Input's field names, the image
and the start; Wednesday's run proves the image accepts `--scheduled`. The target is the applied
schedule's, read back with `get-schedule`, with only the command swapped. The one-off is
`debate-dev-caselist-run-field-name-proof`, in the run's own group, with `ActionAfterCompletion DELETE`
and an `at()` about ten minutes ahead. The scheduler role trusts the group, so the one-off can assume
it. After the one-off deletes itself, the module's comment that the run's schedule is its group's only
member is true again.

### 5. What the universal request carries

Exactly what the templated target sent, in RunTask's names: `cluster` (the run cluster's ARN, so the
role's `ecs:cluster` condition holds), `taskDefinition` (Terraform's revision by full ARN, which RunTask
requires to match the policy's Resource), `count` 1, `launchType` `FARGATE`, `platformVersion` `LATEST`,
`enableExecuteCommand` false, `enableECSManagedTags` false, and
`networkConfiguration.awsvpcConfiguration`: the run's subnets, its security group, and
`assignPublicIp` `ENABLED`, the templated `assign_public_ip = true`. Its only override is the run
container's `command`. It carries no tags and no `propagateTags`, so it needs no `ecs:TagResource`.
`retry_policy` and `dead_letter_config` stay on the target.

### 6. Not verified offline: that the schedule is updated in place

The provider's schema (`terraform providers schema -json`) does not say which attributes force
replacement, so no offline run here shows the action Terraform takes. The check requires an
`update` for the run schedule, and refuses a replace by name ("the schedule replaced, not updated"
is one of its cases). The PM reads the plan before any apply.

### 7. Prod

Prod's module call is the same file as dev's. The runbook records no prod apply B ("Prod, at the
pilot's promotion (follow-up)"), so prod's promotion plan creates its run task and schedule, with
the universal target, rather than moving one. `check_image_plan.py` is not that plan's check: it
expects both schedules `ENABLED`, and prod's stays disabled until the home moves. The promotion's
plan is read by the PM by its own steps.

## Operator follow-ups

None to run before the PM's review. After the PM accepts this report and the pull request merges into
dev, these are the runbook's own blocks, in run order ("The schedule passes --scheduled
(`v1-e40-t48`), once" in `docs/runbooks/caselist-cloud-run.md`, and step 5 from "A new image, later").
`$WT` is the apply worktree of the runbook's "Before you start":

**0. Set the worktree.**

```bash
WT="$HOME/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/caselist-credentials-dev"
cd "$WT" || echo "WT does not exist: $WT"
```

**1. The apply worktree at `origin/dev`, with `v1-e40-t48` merged.**

**Operator command** (expected runtime seconds)
Where: `$WT`
```bash
cd "$WT"
git fetch origin
git switch --detach origin/dev
grep -q 'run_scheduled_command' infrastructure/modules/caselist_run/run_task.tf && grep -q -- '--universal-target' ops/caselist_run/check_image_plan.py && echo "ok: $(pwd) at origin/dev $(git rev-parse --short HEAD), v1-e40-t48 merged" || echo "NOT MERGED: origin/dev has no v1-e40-t48; wait for it to merge"
git status --porcelain | grep -v 'owner.auto.tfvars' | head -3
```
Success looks like `ok: <the worktree> at origin/dev <commit>, v1-e40-t48 merged`, and nothing after
it.

**2. A release that carries `--scheduled`.**

**Operator command** (expected runtime seconds)
Where: `$WT`
```bash
cd "$WT"
git fetch --quiet origin --tags
TAG="$(gh release list --repo charlesclark2/debate-intelligence --limit 1 --json tagName --jq '.[0].tagName')"
if [ -z "$TAG" ]; then echo "STOP: no release found"; elif git show "$TAG:packages/debate_cli/src/debate_cli/commands/caselist_pull.py" 2>/dev/null | grep -q -- '"--scheduled"'; then echo "OK: $TAG carries caselist pull --scheduled"; else echo "STOP: $TAG has no caselist pull --scheduled; use v1.1.0-dev.423 or later"; TAG=""; fi
```
Success looks like `OK: v1.1.0-dev.<n> carries caselist pull --scheduled`, with `<n>` 423 or above. If
that release's validate-dev run is not green, set an earlier green one at 423 or above in the same
shell, for example `TAG='v1.1.0-dev.431'`, and run the block's `if` line again.

**3. The image's dry run.**

**Operator command** (expected runtime ~1 min)
Where: `$WT`, in the shell that set `TAG`
```bash
cd "$WT"
if [ -z "$TAG" ]; then echo "STOP: TAG is not set; run the block above first"; elif env | grep -qE '^(CASELIST_RUN_DEPLOY_PROFILE|DEBATE_RELEASE_REPO)='; then echo "STOP: a deploy override is set in this shell"; else time scripts/caselist_run_deploy.sh dev "$TAG" --dry-run; fi
```
Success looks like seven `ok:` lines, then `Dry run complete. debate-dev-caselist-run:<tag> built and
checked`. Any `check image:` line says what is wrong, and nothing was pushed.

**4. The push.**

**Operator command** (expected runtime ~3 min)
Where: `$WT`, in the shell that set `TAG`
```bash
cd "$WT"
aws sso login --sso-session debate
if [ -z "$TAG" ]; then echo "STOP: TAG is not set; run the block above first"; elif env | grep -qE '^(CASELIST_RUN_DEPLOY_PROFILE|DEBATE_RELEASE_REPO)='; then echo "STOP: a deploy override is set in this shell"; else scripts/caselist_run_deploy.sh dev "$TAG" 2>&1 | tee /tmp/caselist-run-deploy.txt | tail -8; fi
grep -E '^pushed: |caselist_image_digest = ' /tmp/caselist-run-deploy.txt
```
Success looks like `pushed: <account>.dkr.ecr.us-east-1.amazonaws.com/debate-dev-caselist-run@sha256:<64
hex digits>`, then `caselist_image_digest = "sha256:<the same digits>"`. No `pushed:` line means the
push failed: the lines above it say why.

**5. The search index's format and the parser version (A new image, later's block): go on only after `OK:`.**

**Operator command** (expected runtime seconds)
Where: `$WT`, in the shell that ran the push
```bash
cd "$WT"
if [ -z "$TAG" ]; then echo "STOP: TAG is not set; set it to the release the push used"; else git fetch --quiet origin && git fetch --quiet origin tag "$TAG" && URI="$(AWS_PROFILE=debate-admin aws lambda get-function --region us-east-1 --function-name debate-dev-tub --query Code.ImageUri --output text)" && FUNCTION_TAG="$(AWS_PROFILE=debate-admin aws ecr describe-images --region us-east-1 --repository-name debate-dev-tub --image-ids "imageDigest=${URI##*@}" --query 'imageDetails[0].imageTags[0]' --output text)" && python3 -I - "$TAG" "${FUNCTION_TAG%%-uncommitted-*}" <<'FORMAT'
import re, subprocess, sys
def writes(commit):
    shown = subprocess.run(["git", "show", commit + ":packages/debate_core/src/debate_core/domain/search_index.py"], capture_output=True, text=True)
    found = re.search(r"^SEARCH_INDEX_FORMAT_VERSION: Final = ([0-9]+)$", shown.stdout, re.MULTILINE)
    return int(found.group(1)) if found else None
image, function = writes(sys.argv[1]), writes(sys.argv[2])
if image is None or function is None:
    print("STOP: cannot read the format of " + (sys.argv[1] if image is None else "dev's function at " + sys.argv[2]) + "; take this to the PM")
elif function < image:
    print("STOP: the image writes index format " + str(image) + " and dev's function, at " + sys.argv[2] + ", reads " + str(function) + " at most: deploy dev's function first (evidence-search.md, Moving the index to format " + str(image) + ")")
else:
    print("OK: the image writes index format " + str(image) + " and dev's function, at " + sys.argv[2] + ", reads it")
def parses(commit):
    shown = subprocess.run(["git", "show", commit + ":packages/debate_core/src/debate_core/integrations/docx_parser/parser.py"], capture_output=True, text=True)
    found = re.search(r'^DOCX_PARSER_VERSION: Final = "([^"]+)"$', shown.stdout, re.MULTILINE)
    return found.group(1) if found else None
image_parser, function_parser = parses(sys.argv[1]), parses(sys.argv[2])
if image_parser is None or function_parser is None:
    print("PARSER: cannot read the parser version of " + (sys.argv[1] if image_parser is None else "dev's function at " + sys.argv[2]) + "; take this to the PM")
elif image_parser == function_parser:
    print("PARSER: the image and dev's function both parse at " + image_parser + "; Download stays on")
else:
    print("PARSER: the image parses at " + image_parser + " and dev's function at " + function_parser + ": Download in dev is off from this image's first run until dev's function is deployed at " + image_parser + ", the day after that run records its index")
FORMAT
fi
```
Success looks like `OK: the image writes index format 3 and dev's function, at <commit>, reads it`,
then a `PARSER:` line (`v1-e40-t16`). The `PARSER:` line never stops the section. `both parse at` means
Download stays on. `the image parses at <new> and dev's function at <old>` is a parser bump. Dev's
function is not deployed with the image, which would turn Download off until the run: the run's index
is still the old version until then. It is deployed at the new version the day after the image's
first run records its index
([A new image with a new parser version](../runbooks/caselist-cloud-run.md#a-new-image-with-a-new-parser-version)). A `STOP` line stops this section: do not replace the digest line. Deploy dev's function as the line
says, run this block again, and go on only after `OK`. A failed `aws` call prints its own error and
no `OK`. For prod at the promotion the same check reads `debate-prod-tub`.

**6. The digest line in `owner.auto.tfvars`, that line only.**

**Operator command** (expected runtime under a second)
Where: `$WT`, in the shell that ran the push
```bash
cd "$WT"
NEW="$(grep -oE 'caselist_image_digest = "sha256:[0-9a-f]{64}"' /tmp/caselist-run-deploy.txt | tail -1)"
if [ -z "$NEW" ]; then echo "STOP: no digest line in /tmp/caselist-run-deploy.txt; run the push first"; else python3 -I - infrastructure/envs/dev/owner.auto.tfvars "$NEW" <<'DIGEST'
import re, sys
path, new = sys.argv[1], sys.argv[2]
text = open(path).read()
found = [line for line in text.splitlines() if re.match(r"^caselist_image_digest\s*=", line)]
if len(found) != 1:
    sys.exit("STOP: expected one caselist_image_digest line, found " + str(len(found)))
open(path, "w").write(re.sub(r"(?m)^caselist_image_digest\s*=.*$", new, text))
print("replaced: " + found[0] + "  ->  " + new)
DIGEST
fi
grep -cE '^caselist_image_digest += "sha256:[0-9a-f]{64}"$' infrastructure/envs/dev/owner.auto.tfvars
```
Success looks like `replaced: caselist_image_digest = "sha256:<old>"  ->  caselist_image_digest =
"sha256:<new>"`, then `1`.

**7. The one dev plan, checked with `--universal-target`: send the PM the check's line, the `Plan:` line and `/tmp/caselist-schedule-scheduled-plan.txt`, and stop.**

**Operator command** (expected runtime ~2 min)
Where: `$WT`, in the shell that replaced the digest line
```bash
cd "$WT"
rm -f infrastructure/envs/dev/caselist-schedule-scheduled.tfplan /tmp/caselist-schedule-scheduled-plan.json
if env | grep -qE '^(TF_VAR_|TF_WORKSPACE=|TF_DATA_DIR=|TF_CLI_ARGS)'; then echo "STOP: a Terraform override is set in this shell"; else AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev init -input=false >/dev/null && AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev plan -input=false -no-color -out=caselist-schedule-scheduled.tfplan | tee /tmp/caselist-schedule-scheduled-plan.txt | tail -3; fi
AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev show -json caselist-schedule-scheduled.tfplan > /tmp/caselist-schedule-scheduled-plan.json
python3 -I ops/caselist_run/check_image_plan.py /tmp/caselist-schedule-scheduled-plan.json infrastructure/envs/dev/owner.auto.tfvars --universal-target
```
**What to read, and what stops you.** Send the PM the check's last line, the plan's `Plan:` line, and
`/tmp/caselist-schedule-scheduled-plan.txt`. Apply only after the PM's word.
The only line that passes: `PLAN OK: 2 to add, 4 to change, 2 to destroy; the login and run task
definitions replaced with the image sha256:<new>... and nothing else in them changed; the login
schedule and the two roles' policies repointed at the new revisions; the run schedule moved onto
Scheduler's universal RunTask target, its role and every other target setting as before, and its
Input, which names the new revision, known only after the apply: read it back after the apply; both
schedules ENABLED throughout; nothing else changes`. A `PLAN STOP:` line goes to the PM before any apply.

**8. The apply, after the PM's word, on Sunday 2026-11-15 or Monday 2026-11-16.**

**Operator command** (expected runtime ~1 min)
Where: `$WT`, after the PM's word, on Sunday 2026-11-15 or Monday 2026-11-16, never a Wednesday
```bash
cd "$WT"
RUNNING="$(AWS_PROFILE=debate-admin aws ecs list-tasks --region us-east-1 --cluster debate-dev-caselist-run --desired-status RUNNING --query 'length(taskArns)' --output text)" || RUNNING="unknown"
if [ "$(TZ=America/Chicago date +%A)" = "Wednesday" ]; then echo "STOP: it is Wednesday in Chicago, the run's day; apply on another day"; elif env | grep -qE '^(TF_VAR_|TF_WORKSPACE=|TF_DATA_DIR=|TF_CLI_ARGS)'; then echo "STOP: a Terraform override is set in this shell"; elif [ "$RUNNING" = "0" ]; then AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev apply -input=false caselist-schedule-scheduled.tfplan; else echo "STOP: ${RUNNING} tasks running on debate-dev-caselist-run, or the count could not be read; apply when it is 0"; fi
AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev output caselist_run_schedule_state
```
Success looks like `Apply complete! Resources: 2 added, 4 changed, 2 destroyed.`, then `"ENABLED"`. One
`-login-task-changed` email is expected, as for any new image. If the PM allowed a plan the check
stopped, the counts are that plan's.

**9. The read-back of the schedule's target and command, before the next scheduled run.**

**Operator command** (expected runtime seconds)
Where: `$WT`, after the apply
```bash
cd "$WT"
AWS_PROFILE=debate-admin aws scheduler get-schedule --region us-east-1 --group-name debate-dev-caselist-run --name debate-dev-caselist-run --query Target --output json > /tmp/caselist-run-schedule-target.json && python3 -I - /tmp/caselist-run-schedule-target.json <<'TARGET'
import json, sys
target = json.load(open(sys.argv[1]))
arn = str(target.get("Arn", ""))
print("target: " + (arn if arn.endswith(":scheduler:::aws-sdk:ecs:runTask") else "the ECS template, not the universal RunTask target"))
try:
    command = json.loads(target["Input"])["overrides"]["containerOverrides"][0]["command"]
except (KeyError, IndexError, TypeError, ValueError):
    print("command: none: the target has no RunTask Input with a command override")
else:
    print("command: " + json.dumps(command))
TARGET
```
Success looks like `target: arn:aws:scheduler:::aws-sdk:ecs:runTask`, then `command: ["--json",
"caselist", "pull", "--scheduled"]`. Anything else goes to the PM with the two lines, before Wednesday.

**10. The one-off dry run's target.**

**Operator command** (expected runtime under a second)
Where: `$WT`, in the shell that ran the read-back
```bash
cd "$WT"
rm -f /tmp/caselist-run-oneoff-target.json
python3 -I - /tmp/caselist-run-schedule-target.json /tmp/caselist-run-oneoff-target.json <<'ONEOFF'
import json, sys
source, out = sys.argv[1], sys.argv[2]
target = json.load(open(source))
try:
    request = json.loads(target["Input"])
    [override] = request["overrides"]["containerOverrides"]
except (KeyError, TypeError, ValueError):
    sys.exit("STOP: the schedule's target has no RunTask Input with one container override; run the read-back first")
if not str(target.get("Arn", "")).endswith(":scheduler:::aws-sdk:ecs:runTask") or override.get("command") != ["--json", "caselist", "pull", "--scheduled"]:
    sys.exit("STOP: the schedule is not the applied universal target with --scheduled; run the read-back first")
override["command"] = ["--json", "caselist", "pull", "--dry-run"]
target["Input"] = json.dumps(request, separators=(",", ":"))
json.dump(target, open(out, "w"))
print("one-off target: " + target["Arn"])
print("one-off command: " + json.dumps(override["command"]))
ONEOFF
```
Success looks like `one-off target: arn:aws:scheduler:::aws-sdk:ecs:runTask`, then `one-off command:
["--json", "caselist", "pull", "--dry-run"]`. A `STOP:` line means the read-back did not show the
applied target: go back to it.

**11. Create the one-off (the same day as the apply).**

**Operator command** (expected runtime seconds)
Where: `$WT`, in the same shell, on the day of the apply
```bash
cd "$WT"
ONEOFF_AT="$(date -u -v+10M '+at(%Y-%m-%dT%H:%M:%S)')"
RUNNING="$(AWS_PROFILE=debate-admin aws ecs list-tasks --region us-east-1 --cluster debate-dev-caselist-run --desired-status RUNNING --query 'length(taskArns)' --output text)" || RUNNING="unknown"
if [ "$(TZ=America/Chicago date +%A)" = "Wednesday" ]; then echo "STOP: it is Wednesday in Chicago, the run's day"; elif [ "$RUNNING" = "0" ] && [ -s /tmp/caselist-run-oneoff-target.json ]; then AWS_PROFILE=debate-admin aws scheduler create-schedule --region us-east-1 --group-name debate-dev-caselist-run --name debate-dev-caselist-run-field-name-proof --schedule-expression "$ONEOFF_AT" --schedule-expression-timezone UTC --flexible-time-window Mode=OFF --action-after-completion DELETE --target file:///tmp/caselist-run-oneoff-target.json --query ScheduleArn --output text >/dev/null && echo "created the one-off for ${ONEOFF_AT} UTC"; elif [ "$RUNNING" = "0" ]; then echo "STOP: no one-off target; run the block above first"; else echo "STOP: ${RUNNING} tasks running on debate-dev-caselist-run, or the count could not be read; start the one-off when it is 0"; fi
```
Success looks like `created the one-off for at(<time>) UTC`. Then wait about 25 minutes: ten for the
start, a few for the dry run, and up to fifteen for CloudTrail to show the event.

**12. The proof's evidence: CloudTrail's RunTask event (about 25 minutes later).**

**Operator command** (expected runtime seconds)
Where: `$WT`, about 25 minutes after the one-off was created
```bash
cd "$WT"
rm -f /tmp/caselist-run-runtask-events.json /tmp/caselist-run-runtask-task.txt
AWS_PROFILE=debate-admin aws cloudtrail lookup-events --region us-east-1 --lookup-attributes AttributeKey=EventName,AttributeValue=RunTask --start-time "$(date -u -v-3H +%Y-%m-%dT%H:%M:%SZ)" --query 'Events[].CloudTrailEvent' --output json > /tmp/caselist-run-runtask-events.json && python3 -I - /tmp/caselist-run-runtask-events.json debate-dev-caselist-run-scheduler /tmp/caselist-run-runtask-task.txt <<'RUNTASK'
import json, sys
events_file, role, task_file = sys.argv[1], sys.argv[2], sys.argv[3]
found = []
for raw in json.load(open(events_file)) or []:
    event = json.loads(raw)
    named = str((event.get("userIdentity") or {}).get("arn", "")).partition(":assumed-role/")[2].split("/")[0]
    if named != role:
        continue
    try:
        command = json.dumps(event["requestParameters"]["overrides"]["containerOverrides"][0]["command"])
    except (KeyError, IndexError, TypeError):
        command = "(no command override)"
    tasks = (event.get("responseElements") or {}).get("tasks") or []
    task = str(tasks[0].get("taskArn", "")).rsplit("/", 1)[-1] if tasks else "(no task)"
    found.append((str(event.get("eventTime", "")), named, command, task))
for line in sorted(found):
    print("  ".join(line))
if found:
    open(task_file, "w").write(sorted(found)[-1][3] + "\n")
else:
    print("none: no RunTask by " + role + " in the window")
RUNTASK
```
Success looks like one line, `<time>  debate-dev-caselist-run-scheduler  ["--json", "caselist", "pull",
"--dry-run"]  <task id>`. `none:` means CloudTrail has not shown it yet, or the one-off never called
RunTask: run the block again ten minutes later, and if it is still `none` see "A failed proof" below.
`(no task)` means ECS refused the start: the launch-refused email says why.

**13. The proof's evidence: the task exited 0.**

**Operator command** (expected runtime seconds)
Where: `$WT`, after the CloudTrail block printed a task id
```bash
cd "$WT"
TASK_ID="$(cat /tmp/caselist-run-runtask-task.txt 2>/dev/null)"
if [ -z "$TASK_ID" ] || [ "$TASK_ID" = "(no task)" ]; then echo "STOP: no task id from the CloudTrail block; run it first"; else AWS_PROFILE=debate-admin aws ecs describe-tasks --region us-east-1 --cluster debate-dev-caselist-run --tasks "$TASK_ID" --query 'tasks[0].[lastStatus,stopCode,containers[0].exitCode]' --output text; fi
```
Success looks like `STOPPED	EssentialContainerExited	0`. `RUNNING` or `PENDING` means it is not done:
run it again in a few minutes. Send the PM the CloudTrail line and this one: the proof passed.

**14. Only on a failed proof: is the one-off still there?**

**Operator command** (expected runtime seconds)
Where: `$WT`
```bash
cd "$WT"
AWS_PROFILE=debate-admin aws scheduler get-schedule --region us-east-1 --group-name debate-dev-caselist-run --name debate-dev-caselist-run-field-name-proof --query '[Name,State,ScheduleExpression]' --output text
```
If it printed the one-off's name, delete it. The block names the one-off alone, never the weekly
schedule.

**15. Only on a failed proof, and only if the block above printed its name: delete the one-off.**

**Operator command** (expected runtime seconds)
Where: `$WT`, only after the block above printed `debate-dev-caselist-run-field-name-proof`
```bash
cd "$WT"
AWS_PROFILE=debate-admin aws scheduler delete-schedule --region us-east-1 --group-name debate-dev-caselist-run --name debate-dev-caselist-run-field-name-proof && echo "deleted the one-off"
```
Then send the PM what the proof printed, and the email if one came. The PM rules before Wednesday
whether to fix forward with the other casing or apply the templated target again.

**16. Wednesday 2026-11-18 (ac2): the schedule's RunTask.**

**Operator command** (expected runtime seconds)
Where: `$WT`, after 07:00 Chicago on Wednesday 2026-11-18
```bash
cd "$WT"
rm -f /tmp/caselist-run-runtask-events.json /tmp/caselist-run-runtask-task.txt
AWS_PROFILE=debate-admin aws cloudtrail lookup-events --region us-east-1 --lookup-attributes AttributeKey=EventName,AttributeValue=RunTask --start-time 2026-11-18T11:00:00Z --end-time 2026-11-18T14:00:00Z --query 'Events[].CloudTrailEvent' --output json > /tmp/caselist-run-runtask-events.json && python3 -I - /tmp/caselist-run-runtask-events.json debate-dev-caselist-run-scheduler /tmp/caselist-run-runtask-task.txt <<'RUNTASK'
import json, sys
events_file, role, task_file = sys.argv[1], sys.argv[2], sys.argv[3]
found = []
for raw in json.load(open(events_file)) or []:
    event = json.loads(raw)
    named = str((event.get("userIdentity") or {}).get("arn", "")).partition(":assumed-role/")[2].split("/")[0]
    if named != role:
        continue
    try:
        command = json.dumps(event["requestParameters"]["overrides"]["containerOverrides"][0]["command"])
    except (KeyError, IndexError, TypeError):
        command = "(no command override)"
    tasks = (event.get("responseElements") or {}).get("tasks") or []
    task = str(tasks[0].get("taskArn", "")).rsplit("/", 1)[-1] if tasks else "(no task)"
    found.append((str(event.get("eventTime", "")), named, command, task))
for line in sorted(found):
    print("  ".join(line))
if found:
    open(task_file, "w").write(sorted(found)[-1][3] + "\n")
else:
    print("none: no RunTask by " + role + " in the window")
RUNTASK
```
Success looks like `2026-11-18T12:00:<ss>Z  debate-dev-caselist-run-scheduler  ["--json", "caselist",
"pull", "--scheduled"]  <task id>`. **And that week's run record:**

**17. Wednesday 2026-11-18 (ac2): that week's run record.**

**Operator command** (expected runtime ~1 min)
Where: your Mac, the installed build
```bash
aws sso login --profile debate-dev-evidence
debate-research caselist runs --remote --last 1
```
Success looks like a run started on 2026-11-18 a few minutes after 12:00 UTC. The two together are
ac2. Prod's first scheduled run after the home moves gets the same read with `prod` for `dev`,
recorded beside ac2 but not part of it.

## Follow-up work

* **CloudTrail may not record a RunTask's overrides.** If the CloudTrail read prints
  `(no command override)` for a start that had one, the task's own record has it:
  `aws ecs describe-tasks ... --query 'tasks[0].overrides.containerOverrides[0].command'`. The PM's
  Q4 did not name that read, so it is the PM's choice whether it may stand in, within the hour ECS
  keeps a stopped task.
* **v1-e41-t13** (Pending) gives the image mode the known-revision rule under the ECS template. It can
  call `revision_problem`, which now reads both shapes.
* **Prod's image plans after the home moves.** `check_image_plan.py` expects both schedules
  `ENABLED`. That holds for prod only once its schedule is enabled at the move (ADR-0020 (7), the
  promotion's item 14).
* **Dev moved one commit** past this branch's base (`8e16823`, v1-e06-t17), which touches none of this
  task's files. `scripts/task sync` before the pull request, if the operator's flow asks for it.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-14

**Notes:**

Accepted for a partial merge. The session's work is done. ac1's plan read and ac2's Wednesday run are
the operator's, so the Goal stays `InProgress`.

* **Decision 1 is the documentation read the brief asked for.** It cites six pages with their URLs
  and quotes, read 2026-11-13, before any change. The finding (no page says the templated ECS
  target's Input reaches RunTask) is stated plainly, not guessed, and the universal target follows by
  the PM's rule.
* **The change is as ruled.** The universal target carries RunTask's camelCase request, with exactly
  what the template sent (Decision 5). The scheduler role's policy is unchanged, and a run started by
  hand keeps the task definition's command. `check_image_plan.py` learns the universal shape for the
  move and for every later image plan. Its known-revision rule reads both shapes, leaving
  `v1-e41-t13` an easy follow-on.
* **The evidence is thorough.**
  * The red runs: 43 of 44 Terraform tests passed with the new one failing at its three assertions,
    then 2/1, 20/14 and 20/34 for the pytest files.
  * The PM's mutant (`--scheduled` dropped) is caught by both the Terraform and the pytest tests, and
    all nine mutants on the check are caught at its `PLAN` line, none by a crash.
  * The plan-time evaluation was probed with a wrong dead-letter ARN, showing the test reads the plan
    and not only the source.
* **Decision 4 is right.** `--scheduled --dry-run` is a usage error by t44's ruling 2, so the one-off
  runs `--dry-run` alone and proves the field names, the image and the start. Wednesday's run proves
  the option. The confirmation that a dry run takes no lock, writes no run record and downloads
  nothing is read from the code, with the files named.
* **Deviations 1 to 5: accepted.**
  * 1 is the narrowest possible change to `v1-e40-t09`'s test: exactly one input, in `run_task.tf`,
    naming no backfile. A planted input on the login's schedule still fails it.
  * 4 records the PM's Q2 ruling.
  * The PM records `tests/docs` in the spec's packages in the next batch.
* **Decision 7 corrects the PM's Q3 premise.** Prod has no run task or schedule until its
  `caselist_image_digest` is set (apply B). So this weekend's promotion plan creates no prod
  schedule, and t48's universal target reaches prod when apply B creates it at the home's move
  (promotion item 14), under that move's own plan read. Nothing about t48 rides in this weekend's
  prod plan.
* **Decision 6 is acknowledged.** That the schedule is updated in place is checked by the check's
  refusal of a replace and by the PM's read of the plan.
* **The checks:**
  * The affected set (120 files) stopped at its bound under load and goes to `ci` under agreement 10,
    with the bounded subsets green.
  * `terraform_checks.sh` passed offline.
  * Dev has moved by `v1-e06-t17`: if `scripts/task pr` asks, `scripts/task sync`.
* **Follow-up 1, ruled:** if CloudTrail shows `(no command override)`, `aws ecs describe-tasks ...
  --query 'tasks[0].overrides.containerOverrides[0].command'` may stand in, for the one-off and for
  ac2. It is read while the task runs or within the hour after it stops, and prints the command alone.
* **The operator's order:**
  * blocks 0 to 7, then send the PM the check's line, the `Plan:` line and the plan text;
  * the apply (block 8) only after the PM's word, on Sunday 2026-11-15 or Monday 2026-11-16;
  * blocks 9 to 13 the same day;
  * 16 and 17 after 07:00 Chicago on Wednesday 2026-11-18.

  At block 2, the release must also be green on validate-dev.

`scripts/task pr --partial`

## Resumed 2026-11-15: the Input in the SDK's PascalCase, and the run schedule's fix plan

| | |
|---|---|
| Session status | PARTIAL, as briefed: the fix is built and tested. The Goal stays `InProgress`: ac1's apply and ac2's Wednesday read are the operator's |
| Branch | `task/v1-e40-t48-the-schedule-passes-scheduled`, recreated from `origin/dev` at `76da7c1` |
| Brief | The PM's context of 2026-11-15 (dev's apply partly failed), and the PM's note of 2026-11-15 on `v1-e05-t20` |

### Summary

Dev's apply of Sunday 2026-11-15 (image `v1.1.0-dev.439`, `sha256:764f9ba4f621...`) was refused at the
run schedule: "ValidationException: Invalid RequestJson provided. Reason Request payload is missing the
following field(s): TaskDefinition." Scheduler validates a universal target's Input against the AWS
SDK's PascalCase member names. The run schedule was left on the ECS template, starting revision `:15`,
which the apply deregistered, and the run scheduler role's policy now names `:17` alone. As it stands,
Wednesday's run would be refused.

This session fixes that:

* **The module.** The module's Input uses the SDK's names, each checked against the AWS SDK for .NET
  V3's ECS model (read 2026-11-15).
* **The check.** `check_image_plan.py` reads the Input's `TaskDefinition`. A new `--run-schedule-only`
  mode checks the fix plan: the run schedule alone, updated in place, `0 to add, 1 to change, 0 to
  destroy`. Its Input is known in this plan, so the check reads it key by key. Beside it, and only
  there, `v1-e05-t20`'s grant policy updated in place is allowed and named on a line of its own (the
  PM's note).
* **The runbook.** The read-back and the one-off builder parse PascalCase. The CloudTrail reads keep
  camelCase, which CloudTrail records as the service's API reference documents. A new section, "The
  run schedule alone, after the apply of 2026-11-15", holds the state read, the plan, the apply and the
  fallback.

The operator's blocks are in run order under Operator follow-ups below.

### Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the schedule's target passes `--scheduled`, shown by the plan's diff and a plan-time test, with the documentation's answer on input recorded, and the PM has read the plan before the operator's apply | NOT RUN (the fix plan, the PM's read and the apply are the operator's, Monday or Tuesday) | **Plan-time test: PASS on PascalCase.** `the_run_schedule_starts_its_pull_with_scheduled` now pins the PascalCase request whole. Red against the camelCase module: `TF_CLI_CONFIG_FILE=<mirror> TF_DATA_DIR=<scratch> terraform -chdir=infrastructure/modules/caselist_run test -no-color` → **41 passed, 3 failed**, nothing skipped (the three runs that read the Input). Green after `bb053e2`: **44 passed, 0 failed**. **The documentation's answer** is recorded, now with AWS's validator's answer (Decision 8). **The plan's diff:** in the fix plan the Input is known, so the PM reads the command in the diff (Operator follow-up 3). Sunday's plan was read by the PM; its apply failed at the run schedule. |
| ac2: the operator's first scheduled run after the apply records a pull started with `--scheduled` | NOT RUN (Wednesday 2026-11-18) | Operator follow-ups 12 and 13, unchanged. If the fix is not applied by Tuesday night, ac2 cannot pass this week (Decision 12). |
| Node: Schedule passes --scheduled tests pass (`uv run pytest tests/infrastructure -k schedule`) | PASS | `.venv/bin/python scripts/hard_stop.py 115 uv run pytest tests/infrastructure -k schedule` → **95 passed in 1.90s**: both files' tests. The 41 deselected are the cost-allocation and model-budget tests. |

**Red runs, each before its change:**

* **The module's source tests** against the module before `bb053e2`: `... -m pytest tests/infrastructure -n 0 -k "pull_with_scheduled or pascal_case"` → **2 failed**. Green after: **2 passed**.
* **The fixtures moved to PascalCase**, run against the check and runbook as they were: `... -m pytest tests/infrastructure -n 0` → **9 failed, 86 passed**. Eight were the check's known-revision cases and the runbook's read-back and one-off builder, which still parsed camelCase. The ninth was the source test pinning the old line.
* **The check's new mode**, against a skeleton that accepted `--run-schedule-only` and checked nothing new: `... -m pytest tests/infrastructure -n 0` → **27 failed, 102 passed**. The fix-mode cases that passed are refusals today's image check already makes with the expected words: a replace, a disabled schedule, a change outside the module, every bedrock refusal (Identity Center), the flag beside another mode, and the image check's own refusal of the fix plan.
* **The runbook's tests**, against the runbook before `441c625`: **10 failed, 126 passed**. Seven were the new section's and three the PascalCase parsers.
* **Green after each:** `tests/infrastructure` → **136 passed**. On the way, one test's own expected request (`test_the_one_off_is_the_applied_target_with_only_the_command_a_dry_run`) was still camelCase from the first session; it is corrected in `fae2516`.

**Mutants.** Each was applied in place, and three test files run with `-n 0`: the two in `tests/infrastructure` and `tests/scripts/test_caselist_run_image_plan_check.py`. The baseline is 179 passed. Every one is caught at an assertion, not by a crash.

| Mutant | Result |
|---|---|
| `run_task.tf`: `taskDefinition` in camelCase (the PM's) | `terraform test`: **41 passed, 3 failed**, 0 skipped |
| `run_task.tf`: `--scheduled` dropped (the first session's, again) | `terraform test`: **42 passed, 2 failed**, 0 skipped |
| check: the grant allowance also lets a replace through (the PM's) | **3 failed** (the replaced policy, either order, and its named line) |
| check: the grant allowance lets any field change | 1 failed (the policy moved to another permission set) |
| check: the Input's revision not compared | 1 failed |
| check: the Input's names not compared (camelCase passes) | 1 failed |
| check: the template's settings and the command not compared | 4 failed |
| check: an unknown Input accepted | 1 failed |
| check: the scheduler policy's revision not compared | 1 failed |
| check: the revision's image not compared | 1 failed |
| check: the run task definition allowed to change | 1 failed |
| check: the move's target rules skipped in the new mode | 3 failed |
| check: the known-revision rule reading camelCase | 5 failed |

**Before the report:**

* **The affected set:** `.venv/bin/python scripts/hard_stop.py 115 uv run scripts/affected_tests.py --run --slow` → `116 of 779 test files (14.9%) chosen`. It was stopped at its 115-second limit (exit 124) at 84% with no failure, the load near 24. Over two minutes, so it is left to the pull request's `ci` check (agreement 10). Within the bound instead:
  * the 15 package test files that read `caselist-cloud-run.md` → **198 passed in 43.76s**;
  * `tests/architecture tests/specs tests/infrastructure tests/docs tests/scripts/test_caselist_run_image_plan_check.py -m "not slow and not live"` → **804 passed in 17.28s**;
  * the changed test files with `-m slow` → **156 deselected**, none slow.
* **Formatting and lint:** `uv run --frozen ruff format --check .` → `2149 files already formatted`; `uv run --frozen ruff check .` → `All checks passed!`
* **Types:** `uv run --frozen pyright` (whole project) → `0 errors, 0 warnings, 0 informations`.
* **Imports:** `uv run --frozen lint-imports` → `Contracts: 20 kept, 0 broken.`
* **Specs:** `uv run scripts/validate_specs.py` → `OK: 690 files, 41 epics, 627 tasks, 22 releases`, no warning naming t48.
* **Docs:** `uv run scripts/check_command_blocks.py` → `OK: no # comments in 738 shell code blocks`; `uv run --frozen python scripts/check_links.py` → `OK: 3926 relative links and anchors`.
* **Terraform:** `TF_CLI_CONFIG_FILE=<the mirror rc> bash scripts/terraform_checks.sh` (offline) → `All Terraform checks passed.`, exit 0, 38 s. Its `.terraform` directories were removed, and no lock file changed.

### Files changed

* `infrastructure/modules/caselist_run/run_task.tf`: the Input's keys in PascalCase, and the comment saying why.
* `infrastructure/modules/caselist_run/tests/caselist_run.tftest.hcl`: the three runs that read the Input read PascalCase keys. The CloudTrail patterns' `requestParameters.taskDefinition` is unchanged.
* `ops/caselist_run/check_image_plan.py`: `TaskDefinition` in `known_revision`, and `--run-schedule-only` with the grant allowance.
* `docs/runbooks/caselist-cloud-run.md`: the PascalCase parsers, and the prose on why. The one-off's heading is now "The request, proved in dev before Wednesday". New section "The run schedule alone, after the apply of 2026-11-15 (`v1-e40-t48`)".
* `tests/infrastructure/test_the_schedule_passes_scheduled.py`: fixtures in PascalCase, and a test that the request uses the SDK's names.
* `tests/infrastructure/test_the_run_schedule_alone_after_the_failed_apply.py` (new): the fix mode, the grant allowance, and the new section's blocks.
* This report.

### Deviations from the spec

None. (`tests/docs` is in the spec's packages since the PM's batch of 2026-11-14; this session did not
change it.)

### Decisions and assumptions

**8. AWS's validator supersedes the PM's ruling Q1 (A).** Ruling Q1 (A) chose the RunTask API
reference's camelCase. Scheduler refused it at UpdateSchedule on 2026-11-15 (request ID
`40ed8070-c741-4ac1-a718-88c05243ef73`): "Request payload is missing the following field(s):
TaskDefinition". So it validates the universal target's Input against the SDK's PascalCase member
names, and Decision 1's open question is answered by AWS itself. The names are now each checked
against the AWS SDK for .NET V3's ECS model, read 2026-11-15:

* "RunTaskRequest Class" (<https://docs.aws.amazon.com/sdkfornet/v3/apidocs/items/ECS/TRunTaskRequest.html>):
  `Cluster`, `Count`, `EnableECSManagedTags`, `EnableExecuteCommand`, `LaunchType`,
  `NetworkConfiguration`, `Overrides`, `PlatformVersion`, `TaskDefinition` (and others unused).
* "NetworkConfiguration Class" (`.../ECS/TNetworkConfiguration.html`): `AwsvpcConfiguration`.
* "AwsVpcConfiguration Class" (`.../ECS/TAwsVpcConfiguration.html`): `AssignPublicIp`, `SecurityGroups`,
  `Subnets`.
* "TaskOverride Class" (`.../ECS/TTaskOverride.html`): `ContainerOverrides`.
* "ContainerOverride Class" (`.../ECS/TContainerOverride.html`): `Command`, `Name`.

The one-off dry run still runs. The validator settles the names, and a start shows that RunTask runs
the request and the image starts.

**9. CloudTrail keeps the API's camelCase, confirmed from AWS's documentation.**

* "CloudTrail record contents for management, data, and network activity events"
  (<https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-event-reference-record-contents.html>,
  read 2026-11-15), on `requestParameters`: "The parameters, if any, that were sent with the request.
  These parameters are documented in the API reference documentation for the appropriate AWS service."
* "Log Amazon ECS API calls using AWS CloudTrail"
  (<https://docs.aws.amazon.com/AmazonECS/latest/developerguide/logging-using-cloudtrail.html>, read
  2026-11-15): its example ECS event records `"requestParameters": {"clusterName": "default"}`, which is
  the API reference's camelCase.

Scheduler calls ECS's RunTask, so CloudTrail records that call's parameters (`overrides`,
`containerOverrides`, `command`), not Scheduler's Input. The CloudTrail reads, and the alert rules
that read `requestParameters.taskDefinition`, stay as they are.

**10. A mode for the fix plan.** In the fix plan the run task definition is not replaced, so its ARN,
and the whole Input, are known. The image check's known-revision rule would refuse exactly that. So
`--run-schedule-only` reads the Input instead, key by key:

* the SDK's names and no others;
* `TaskDefinition` equal to the run task definition's current ARN, which the plan shows unchanged;
* that revision runs the owner file's image;
* the run scheduler policy names that revision;
* `Cluster`, `Count`, `LaunchType`, `PlatformVersion`, `EnableExecuteCommand`, `EnableECSManagedTags` and
  the network (in any subnet order) equal to the ECS template's own values before the plan;
* `Overrides` exactly the run container's `--json caselist pull --scheduled`.

The role, the retries and the dead-letter queue must be unchanged, the templated parameters gone, the
schedule updated in place and `ENABLED` throughout, and nothing else in the module may change.

The expected counts are `0 to add, 1 to change, 0 to destroy`. The other resources of Sunday's plan
were applied: both task definitions, both policies and the login schedule. The run schedule's failed
update left its state as it was. The runbook's state read (follow-up 2) confirms the state before the
plan. The check's exact `PLAN OK` line for revision `:17` and `sha256:764f9ba4f621...` is quoted in the
runbook and held by a test to what the check prints for that state.

**11. The grant beside it** (the PM's note of 2026-11-15). Only in `--run-schedule-only`, and only
`module.bedrock_access.aws_ssoadmin_permission_set_inline_policy.invoker[0]` with actions exactly
`update` and `inline_policy` its only changed attribute, passes outside the module. Then the counts are
`0 to add, 2 to change, 0 to destroy`, and a second line reads `PLAN OK, outside module.caselist_run:
... updated in place, its inline_policy alone (v1-e05-t20's grant): read its diff in the plan`.

Anything else of `module.bedrock_access` stays an Identity Center change, which never passes: a replace
(either order), an add, a destroy, another attribute, its permission set or an account assignment. A
replaced policy is also named as more than its update in place. The image, memory and universal-target
modes never allow it.

**12. The fallback if the fix is not applied by Tuesday night.** Wednesday's 06:00 start is refused,
because the run scheduler role may run `:17` alone and the schedule asks for `:15`. Expect a
launch-refused email for each refused try (up to four within the hour), then the dead-letter queue's
alarm. After 06:00 Chicago, the operator starts the week by hand with the runbook's Step 8, "One run by
hand". It starts the family's newest ACTIVE revision, `:17` (the image with `--scheduled`), without
`--scheduled`, so the guard does not ask it. ac2 then cannot pass that week; it moves to the first
scheduled run after the fix's apply. The new runbook section says the same.

### Operator follow-ups

Nothing to run before the PM's review. After this merges into dev: steps 1 to 3, then the PM's read;
step 4 on Monday 2026-11-16 or Tuesday 2026-11-17, never a Wednesday; steps 5 to 9 the same day (10
and 11 only on a failed one-off); steps 12 and 13 after 07:00 Chicago on Wednesday 2026-11-18. If
follow-up 1 of the first PM review applies, `aws ecs describe-tasks ... --query
'tasks[0].overrides.containerOverrides[0].command'` may stand in for step 8's command. `$WT` is the
apply worktree:

**0. Set the worktree.**

```bash
WT="$HOME/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/caselist-credentials-dev"
cd "$WT" || echo "WT does not exist: $WT"
```

**1. The worktree at `origin/dev`, with the PascalCase fix merged.**

**Operator command** (expected runtime seconds)
Where: `$WT`
```bash
cd "$WT"
git fetch origin
git switch --detach origin/dev
grep -q 'TaskDefinition       = aws_ecs_task_definition.run' infrastructure/modules/caselist_run/run_task.tf && grep -q -- '--run-schedule-only' ops/caselist_run/check_image_plan.py && echo "ok: $(pwd) at origin/dev $(git rev-parse --short HEAD), the PascalCase fix merged" || echo "NOT MERGED: origin/dev has no PascalCase fix; wait for it to merge"
git status --porcelain | grep -v 'owner.auto.tfvars' | head -3
```
Success looks like `ok: <the worktree> at origin/dev <commit>, the PascalCase fix merged`, and nothing
after it.

**2. The run schedule as it stands, before the plan.**

**Operator command** (expected runtime seconds)
Where: `$WT`
```bash
cd "$WT"
AWS_PROFILE=debate-admin aws scheduler get-schedule --region us-east-1 --group-name debate-dev-caselist-run --name debate-dev-caselist-run --output json > /tmp/caselist-run-schedule-before-fix.json && python3 -I - /tmp/caselist-run-schedule-before-fix.json <<'STATE'
import json, sys
schedule = json.load(open(sys.argv[1]))
target = schedule.get("Target") or {}
arn = str(target.get("Arn", ""))
if arn.endswith(":scheduler:::aws-sdk:ecs:runTask"):
    print("target: " + arn)
    try:
        revision = str(json.loads(target["Input"]).get("TaskDefinition", ""))
    except (KeyError, TypeError, ValueError):
        revision = ""
else:
    print("target: the ECS template, cluster " + arn.rpartition("/")[2])
    revision = str((target.get("EcsParameters") or {}).get("TaskDefinitionArn", ""))
print("revision: " + (revision.rpartition("task-definition/")[2] or "(none)"))
print("state: " + str(schedule.get("State", "")))
STATE
```
Success looks like `target: the ECS template, cluster debate-dev-caselist-run`, then `revision:
debate-dev-caselist-run:15`, then `state: ENABLED`: the state the plan below is checked against. Anything
else goes to the PM before the plan.

**3. The one dev plan, checked with `--run-schedule-only`: send the PM the check's lines, the `Plan:` line and `/tmp/caselist-run-schedule-alone-plan.txt`, and stop.**

**Operator command** (expected runtime ~2 min)
Where: `$WT`
```bash
cd "$WT"
rm -f infrastructure/envs/dev/caselist-run-schedule-alone.tfplan /tmp/caselist-run-schedule-alone-plan.json
if env | grep -qE '^(TF_VAR_|TF_WORKSPACE=|TF_DATA_DIR=|TF_CLI_ARGS)'; then echo "STOP: a Terraform override is set in this shell"; else AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev init -input=false >/dev/null && AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev plan -input=false -no-color -out=caselist-run-schedule-alone.tfplan | tee /tmp/caselist-run-schedule-alone-plan.txt | tail -3; fi
AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev show -json caselist-run-schedule-alone.tfplan > /tmp/caselist-run-schedule-alone-plan.json
python3 -I ops/caselist_run/check_image_plan.py /tmp/caselist-run-schedule-alone-plan.json infrastructure/envs/dev/owner.auto.tfvars --run-schedule-only
```
**What to read, and what stops you.** Send the PM the check's lines, the plan's `Plan:` line and
`/tmp/caselist-run-schedule-alone-plan.txt`. Apply only after the PM's word. The only lines that pass:

* without `v1-e05-t20`, `Plan: 0 to add, 1 to change, 0 to destroy.` and one line:
  `PLAN OK: 0 to add, 1 to change, 0 to destroy; the run schedule alone moved onto Scheduler's universal RunTask target, starting debate-dev-caselist-run:17 with --json caselist pull --scheduled on its cluster, network and launch settings as before, and its role and every other target setting as before; the run scheduler role's policy names that revision, which runs the image sha256:764f9ba4f621...; the run schedule ENABLED throughout; nothing else changes`
* with `v1-e05-t20` merged, `Plan: 0 to add, 2 to change, 0 to destroy.` and two lines:
  `PLAN OK: 0 to add, 2 to change, 0 to destroy; the run schedule alone moved onto Scheduler's universal RunTask target, starting debate-dev-caselist-run:17 with --json caselist pull --scheduled on its cluster, network and launch settings as before, and its role and every other target setting as before; the run scheduler role's policy names that revision, which runs the image sha256:764f9ba4f621...; the run schedule ENABLED throughout; nothing else in module.caselist_run changes`
  and `PLAN OK, outside module.caselist_run: module.bedrock_access.aws_ssoadmin_permission_set_inline_policy.invoker[0] updated in place, its inline_policy alone (v1-e05-t20's grant): read its diff in the plan`.
  The PM reads both, the grant's diff included.

A `PLAN STOP:` line goes to the PM before any apply.

**4. The apply, after the PM's word, on Monday 2026-11-16 or Tuesday 2026-11-17.**

**Operator command** (expected runtime ~1 min)
Where: `$WT`, after the PM's word, on Monday 2026-11-16 or Tuesday 2026-11-17, never a Wednesday
```bash
cd "$WT"
RUNNING="$(AWS_PROFILE=debate-admin aws ecs list-tasks --region us-east-1 --cluster debate-dev-caselist-run --desired-status RUNNING --query 'length(taskArns)' --output text)" || RUNNING="unknown"
if [ "$(TZ=America/Chicago date +%A)" = "Wednesday" ]; then echo "STOP: it is Wednesday in Chicago, the run's day; apply on another day"; elif env | grep -qE '^(TF_VAR_|TF_WORKSPACE=|TF_DATA_DIR=|TF_CLI_ARGS)'; then echo "STOP: a Terraform override is set in this shell"; elif [ "$RUNNING" = "0" ]; then AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev apply -input=false caselist-run-schedule-alone.tfplan; else echo "STOP: ${RUNNING} tasks running on debate-dev-caselist-run, or the count could not be read; apply when it is 0"; fi
AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev output caselist_run_schedule_state
```
Success looks like `Apply complete! Resources: 0 added, 1 changed, 0 destroyed.` (`2 changed` beside
`v1-e05-t20`), then `"ENABLED"`. No `-login-task-changed` email is expected: the login does not change.
Then the [read-back](../runbooks/caselist-cloud-run.md#the-read-back-before-the-next-scheduled-run), which must print `target:
arn:aws:scheduler:::aws-sdk:ecs:runTask` and `command: ["--json", "caselist", "pull", "--scheduled"]`,
and the [one-off dry run](../runbooks/caselist-cloud-run.md#the-request-proved-in-dev-before-wednesday-a-one-off-dry-run) the same day,
its CloudTrail line and the task's exit `0` its evidence.

**5. The read-back: it must show the universal target with `--scheduled`.**

**Operator command** (expected runtime seconds)
Where: `$WT`, after the apply
```bash
cd "$WT"
AWS_PROFILE=debate-admin aws scheduler get-schedule --region us-east-1 --group-name debate-dev-caselist-run --name debate-dev-caselist-run --query Target --output json > /tmp/caselist-run-schedule-target.json && python3 -I - /tmp/caselist-run-schedule-target.json <<'TARGET'
import json, sys
target = json.load(open(sys.argv[1]))
arn = str(target.get("Arn", ""))
print("target: " + (arn if arn.endswith(":scheduler:::aws-sdk:ecs:runTask") else "the ECS template, not the universal RunTask target"))
try:
    command = json.loads(target["Input"])["Overrides"]["ContainerOverrides"][0]["Command"]
except (KeyError, IndexError, TypeError, ValueError):
    print("command: none: the target has no RunTask Input with a command override")
else:
    print("command: " + json.dumps(command))
TARGET
```
Success looks like `target: arn:aws:scheduler:::aws-sdk:ecs:runTask`, then `command: ["--json",
"caselist", "pull", "--scheduled"]`. Anything else goes to the PM with the two lines, before Wednesday.

**6. The one-off dry run's target.**

**Operator command** (expected runtime under a second)
Where: `$WT`, in the shell that ran the read-back
```bash
cd "$WT"
rm -f /tmp/caselist-run-oneoff-target.json
python3 -I - /tmp/caselist-run-schedule-target.json /tmp/caselist-run-oneoff-target.json <<'ONEOFF'
import json, sys
source, out = sys.argv[1], sys.argv[2]
target = json.load(open(source))
try:
    request = json.loads(target["Input"])
    [override] = request["Overrides"]["ContainerOverrides"]
except (KeyError, TypeError, ValueError):
    sys.exit("STOP: the schedule's target has no RunTask Input with one container override; run the read-back first")
if not str(target.get("Arn", "")).endswith(":scheduler:::aws-sdk:ecs:runTask") or override.get("Command") != ["--json", "caselist", "pull", "--scheduled"]:
    sys.exit("STOP: the schedule is not the applied universal target with --scheduled; run the read-back first")
override["Command"] = ["--json", "caselist", "pull", "--dry-run"]
target["Input"] = json.dumps(request, separators=(",", ":"))
json.dump(target, open(out, "w"))
print("one-off target: " + target["Arn"])
print("one-off command: " + json.dumps(override["Command"]))
ONEOFF
```
Success looks like `one-off target: arn:aws:scheduler:::aws-sdk:ecs:runTask`, then `one-off command:
["--json", "caselist", "pull", "--dry-run"]`. A `STOP:` line means the read-back did not show the
applied target: go back to it.

**7. Create the one-off (the same day as the apply).**

**Operator command** (expected runtime seconds)
Where: `$WT`, in the same shell, on the day of the apply
```bash
cd "$WT"
ONEOFF_AT="$(date -u -v+10M '+at(%Y-%m-%dT%H:%M:%S)')"
RUNNING="$(AWS_PROFILE=debate-admin aws ecs list-tasks --region us-east-1 --cluster debate-dev-caselist-run --desired-status RUNNING --query 'length(taskArns)' --output text)" || RUNNING="unknown"
if [ "$(TZ=America/Chicago date +%A)" = "Wednesday" ]; then echo "STOP: it is Wednesday in Chicago, the run's day"; elif [ "$RUNNING" = "0" ] && [ -s /tmp/caselist-run-oneoff-target.json ]; then AWS_PROFILE=debate-admin aws scheduler create-schedule --region us-east-1 --group-name debate-dev-caselist-run --name debate-dev-caselist-run-field-name-proof --schedule-expression "$ONEOFF_AT" --schedule-expression-timezone UTC --flexible-time-window Mode=OFF --action-after-completion DELETE --target file:///tmp/caselist-run-oneoff-target.json --query ScheduleArn --output text >/dev/null && echo "created the one-off for ${ONEOFF_AT} UTC"; elif [ "$RUNNING" = "0" ]; then echo "STOP: no one-off target; run the block above first"; else echo "STOP: ${RUNNING} tasks running on debate-dev-caselist-run, or the count could not be read; start the one-off when it is 0"; fi
```
Success looks like `created the one-off for at(<time>) UTC`. Then wait about 25 minutes: ten for the
start, a few for the dry run, and up to fifteen for CloudTrail to show the event.

**8. The one-off's evidence: CloudTrail's RunTask line (about 25 minutes later).**

**Operator command** (expected runtime seconds)
Where: `$WT`, about 25 minutes after the one-off was created
```bash
cd "$WT"
rm -f /tmp/caselist-run-runtask-events.json /tmp/caselist-run-runtask-task.txt
AWS_PROFILE=debate-admin aws cloudtrail lookup-events --region us-east-1 --lookup-attributes AttributeKey=EventName,AttributeValue=RunTask --start-time "$(date -u -v-3H +%Y-%m-%dT%H:%M:%SZ)" --query 'Events[].CloudTrailEvent' --output json > /tmp/caselist-run-runtask-events.json && python3 -I - /tmp/caselist-run-runtask-events.json debate-dev-caselist-run-scheduler /tmp/caselist-run-runtask-task.txt <<'RUNTASK'
import json, sys
events_file, role, task_file = sys.argv[1], sys.argv[2], sys.argv[3]
found = []
for raw in json.load(open(events_file)) or []:
    event = json.loads(raw)
    named = str((event.get("userIdentity") or {}).get("arn", "")).partition(":assumed-role/")[2].split("/")[0]
    if named != role:
        continue
    try:
        command = json.dumps(event["requestParameters"]["overrides"]["containerOverrides"][0]["command"])
    except (KeyError, IndexError, TypeError):
        command = "(no command override)"
    tasks = (event.get("responseElements") or {}).get("tasks") or []
    task = str(tasks[0].get("taskArn", "")).rsplit("/", 1)[-1] if tasks else "(no task)"
    found.append((str(event.get("eventTime", "")), named, command, task))
for line in sorted(found):
    print("  ".join(line))
if found:
    open(task_file, "w").write(sorted(found)[-1][3] + "\n")
else:
    print("none: no RunTask by " + role + " in the window")
RUNTASK
```
Success looks like one line, `<time>  debate-dev-caselist-run-scheduler  ["--json", "caselist", "pull",
"--dry-run"]  <task id>`. `none:` means CloudTrail has not shown it yet, or the one-off never called
RunTask: run the block again ten minutes later, and if it is still `none` see "A failed proof" below.
`(no task)` means ECS refused the start: the launch-refused email says why.

**9. The one-off's evidence: the task exited 0.**

**Operator command** (expected runtime seconds)
Where: `$WT`, after the CloudTrail block printed a task id
```bash
cd "$WT"
TASK_ID="$(cat /tmp/caselist-run-runtask-task.txt 2>/dev/null)"
if [ -z "$TASK_ID" ] || [ "$TASK_ID" = "(no task)" ]; then echo "STOP: no task id from the CloudTrail block; run it first"; else AWS_PROFILE=debate-admin aws ecs describe-tasks --region us-east-1 --cluster debate-dev-caselist-run --tasks "$TASK_ID" --query 'tasks[0].[lastStatus,stopCode,containers[0].exitCode]' --output text; fi
```
Success looks like `STOPPED	EssentialContainerExited	0`. `RUNNING` or `PENDING` means it is not done:
run it again in a few minutes. Send the PM the CloudTrail line and this one: the proof passed.

**10. Only on a failed one-off: is it still there?**

**Operator command** (expected runtime seconds)
Where: `$WT`
```bash
cd "$WT"
AWS_PROFILE=debate-admin aws scheduler get-schedule --region us-east-1 --group-name debate-dev-caselist-run --name debate-dev-caselist-run-field-name-proof --query '[Name,State,ScheduleExpression]' --output text
```
If it printed the one-off's name, delete it. The block names the one-off alone, never the weekly
schedule.

**11. Only on a failed one-off, and only if the block above printed its name: delete it.**

**Operator command** (expected runtime seconds)
Where: `$WT`, only after the block above printed `debate-dev-caselist-run-field-name-proof`
```bash
cd "$WT"
AWS_PROFILE=debate-admin aws scheduler delete-schedule --region us-east-1 --group-name debate-dev-caselist-run --name debate-dev-caselist-run-field-name-proof && echo "deleted the one-off"
```
Then send the PM what the proof printed, and the email if one came. The PM rules before Wednesday
whether to fix forward with the other casing or apply the templated target again.

**12. Wednesday 2026-11-18 (ac2): the schedule's RunTask.**

**Operator command** (expected runtime seconds)
Where: `$WT`, after 07:00 Chicago on Wednesday 2026-11-18
```bash
cd "$WT"
rm -f /tmp/caselist-run-runtask-events.json /tmp/caselist-run-runtask-task.txt
AWS_PROFILE=debate-admin aws cloudtrail lookup-events --region us-east-1 --lookup-attributes AttributeKey=EventName,AttributeValue=RunTask --start-time 2026-11-18T11:00:00Z --end-time 2026-11-18T14:00:00Z --query 'Events[].CloudTrailEvent' --output json > /tmp/caselist-run-runtask-events.json && python3 -I - /tmp/caselist-run-runtask-events.json debate-dev-caselist-run-scheduler /tmp/caselist-run-runtask-task.txt <<'RUNTASK'
import json, sys
events_file, role, task_file = sys.argv[1], sys.argv[2], sys.argv[3]
found = []
for raw in json.load(open(events_file)) or []:
    event = json.loads(raw)
    named = str((event.get("userIdentity") or {}).get("arn", "")).partition(":assumed-role/")[2].split("/")[0]
    if named != role:
        continue
    try:
        command = json.dumps(event["requestParameters"]["overrides"]["containerOverrides"][0]["command"])
    except (KeyError, IndexError, TypeError):
        command = "(no command override)"
    tasks = (event.get("responseElements") or {}).get("tasks") or []
    task = str(tasks[0].get("taskArn", "")).rsplit("/", 1)[-1] if tasks else "(no task)"
    found.append((str(event.get("eventTime", "")), named, command, task))
for line in sorted(found):
    print("  ".join(line))
if found:
    open(task_file, "w").write(sorted(found)[-1][3] + "\n")
else:
    print("none: no RunTask by " + role + " in the window")
RUNTASK
```
Success looks like `2026-11-18T12:00:<ss>Z  debate-dev-caselist-run-scheduler  ["--json", "caselist",
"pull", "--scheduled"]  <task id>`. **And that week's run record:**

**13. Wednesday 2026-11-18 (ac2): that week's run record.**

**Operator command** (expected runtime ~1 min)
Where: your Mac, the installed build
```bash
aws sso login --profile debate-dev-evidence
debate-research caselist runs --remote --last 1
```
Success looks like a run started on 2026-11-18 a few minutes after 12:00 UTC. The two together are
ac2. Prod's first scheduled run after the home moves gets the same read with `prod` for `dev`,
recorded beside ac2 but not part of it.

### Follow-up work

* **The runbook's first plan check (`--universal-target`) is now a past one.** It is kept for its tests
  and for the record. Prod's move onto the universal target comes at its own apply B, which creates the
  schedule (the first PM review, on Decision 7).
* **v1-e41-t13** can use `revision_problem`, which reads both shapes and now the PascalCase Input.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-16

**Notes:**

Accepted for a partial merge. The fix is built and tested. ac1's apply and ac2's Wednesday read
are the operator's, so the Goal stays `InProgress`.

* **The cause is recorded, and the PM's error with it.** Ruling Q1 (A) chose the RunTask API
  reference's camelCase, and Scheduler's validator refused it at UpdateSchedule with its request ID.
  Decision 8 records that AWS answered the open question itself, and checks every PascalCase name
  against the SDK's ECS model, with each page and the date. The failure came at apply time, before
  any run depended on it.
* **CloudTrail's casing was confirmed, not assumed** (Decision 9, two AWS pages). The reads and alert
  rules keep `requestParameters`' camelCase, because CloudTrail records ECS's RunTask call, not
  Scheduler's Input.
* **`--run-schedule-only` is the right check for the fix plan** (Decision 10). The Input is known in
  that plan, so it is read key by key:
  * the SDK's names only;
  * `TaskDefinition` equal to the current `:17`, which runs the owner file's image;
  * the policy naming that revision;
  * the template's own settings and the network unchanged;
  * the command exactly `--json caselist pull --scheduled`;
  * `0 to add, 1 to change, 0 to destroy`, nothing else in the module.

  The grant allowance (Decision 11) passes only `module.bedrock_access`'s inline policy updated in
  place, its `inline_policy` alone. Every replace, add, destroy, other attribute or assignment is
  refused, the PM's replace mutant among them.
* **The evidence.**
  * Each change has a red run: 41/3 in Terraform, then 2, 9, 27 and 10 failed, then green at 44 and
    136.
  * All 13 mutants were caught at assertions, both PM-named ones included.
  * `terraform_checks.sh` passed offline, and the bounded subsets are green. The affected set (116
    files) goes to `ci` under agreement 10.
* **The fallback is written** (Decision 12): if the fix is not applied by Tuesday night, Wednesday's
  starts are refused, the operator runs Step 8 by hand after 06:00 Chicago, and ac2 moves to the
  first scheduled run after the fix.
* **For the operator:**
  * Steps 1 to 3, then the PM's read of the plan.
  * Step 4 on Monday 2026-11-16 or Tuesday 2026-11-17, never Wednesday.
  * Steps 5 to 9 the same day.
  * Steps 12 and 13 after 07:00 Chicago on Wednesday.
* **One stale sentence:** step 11's "fix forward with the other casing or apply the templated target
  again" predates the validator's answer. On a failed one-off now, the PM rules from what it printed.
  No edit is needed.
* **Follow-ups:** none new. `v1-e41-t13` stays a ready p3.

`scripts/task pr --partial`

# Session report: v1-e40-t30-run-task-memory-fits-a-full-parse

| | |
|---|---|
| Task | `v1-e40-t30-run-task-memory-fits-a-full-parse` — The run task gets 32 GB, so a full re-parse or a backfile import is not killed for memory |
| Spec | [`plan_specs/v1/e40-cloud-caselist-run/t30-run-task-memory-fits-a-full-parse.yaml`](../../plan_specs/v1/e40-cloud-caselist-run/t30-run-task-memory-fits-a-full-parse.yaml) |
| Epic / release | `v1-e40-cloud-caselist-run` / `v1.8` |
| Branch | `task/v1-e40-t30-run-task-memory-fits-a-full-parse` |
| Session status | COMPLETE (Goal left `InProgress`: ac3 is the operator's apply, recorded by the PM) |

## Summary

The run task's memory is 32768 MiB in `infrastructure/modules/caselist_run/run_task.tf`, with 8 vCPU,
8 parse workers, the 100 GiB volume, the image digest and the login task unchanged. `terraform
validate`, `fmt -check`, tflint and the module's `terraform test` all pass. `ops/caselist_run/check_image_plan.py`
gets a `--memory` mode for this apply. It passes only the run side: the run task definition replaced
with 32768 and nothing else in it, the run schedule and its scheduler policy repointed at the new
revision (the schedule `ENABLED` throughout), and nothing touching the login, Identity Center or
anything outside the module. The image mode behaves exactly as before. The operator should see
**`Plan: 1 to add, 2 to change, 1 to destroy.`**. ADR-0020 has a dated amendment to its memory paragraph,
and the runbook has "The run task's memory" after "A new image, later". The PM should look first at
the deviation (the spec's "two schedules" is one), then at the operator blocks below, which must run
**before 2026-11-04 06:00 Chicago and not on a Wednesday**. ac3 is that apply, so the Goal stays
`InProgress`.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `run-task-memory-fits-a-full-parse` (Run task memory) | Done | Terraform at 32768; `--memory` plan check with 43 new tests (shown red first); ADR amendment; runbook section; 9 mutants caught |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the run task's memory is 32 GB in Terraform, vCPU, workers and image unchanged, and `terraform validate` passes | PASS | `run_memory = "32768"`; `run_cpu`, `run_parse_workers`, `run_ephemeral_gib`, the image expression and `login_task.tf` untouched (`git diff origin/dev -- infrastructure` shows `run_task.tf`'s comment and the one value, the module README line and the tftest pin). `TF_CLI_CONFIG_FILE=<mirror> bash scripts/terraform_checks.sh` → `All Terraform checks passed.` (fmt -check, validate for every root and module, tflint, terraform test). Separately, `terraform -chdir=infrastructure/modules/caselist_run test` → `42 passed, 0 failed`; with `run_memory` put back to `"16384"` → `41 passed, 1 failed`, the failing assertion `Fargate, 8 vCPU, 32 GB, 100 GiB of ephemeral storage, arm64 ...`, then the file restored |
| ac2: the plan check passes exactly this change's synthetic plan and refuses one that also changes the image, the login task, an assignment or a permission set, by tests shown failing first | PASS | Red, on a refuse-nothing `--memory` skeleton (commit `18d0add`): `pytest tests/scripts -k plan_check` → `40 failed, 43 passed`, every plan case failing on `AssertionError: PLAN OK: skeleton` and the 5 runbook tests on the missing section. The 2 new tests that passed on the skeleton cannot be failed by it (the image mode refusing the memory plan; an unreadable file, exit 2). Green: `uv run pytest tests/scripts -k plan_check -q` → `84 passed` (41 image-mode tests unchanged, 43 new). The refusals include an image change (three ways), each of the login's three resources, an account assignment, a permission set, an identity-store user, 16384/28672/61440 MiB, a vCPU change, and the schedule left on the old revision (unchanged, set back by name, or set to another registered revision) |
| ac3: the operator's plan prints the expected `Plan:` line and the check prints OK, read by the PM, and the apply before 2026-11-04 leaves the schedule on a 32 GB revision (operator, recorded by the PM) | NOT RUN | Needs this branch merged into dev, the operator's AWS session and the PM's reading. The blocks are under Operator follow-ups and in the runbook |
| Node: Run task memory tests pass (`uv run pytest tests/scripts -k plan_check`) | PASS | `.venv/bin/python scripts/hard_stop.py 115 uv run pytest tests/scripts -k plan_check -q` → `84 passed in 24.40s` |

**Mutants (agreement 8),** against `check_image_plan.py --memory`, each an exact substring swap. Each
ran over the whole test file with a fresh, empty `HYPOTHESIS_STORAGE_DIRECTORY` (the file uses no
Hypothesis), restored in a `finally`, and `git status` was clean after. A probe then ran each mutant's key case to confirm it really
accepts the plan (`PLAN OK`), not a reworded refusal and not a crash:

| Mutant | Result | Caught by (key case printing `PLAN OK` under the mutant) |
|---|---|---|
| 1. the login change accepted (`if login:` → `if False:`) | CAUGHT, 5 failed | `the login task definition replaced` and the login schedule/policy/update cases, `the memory check refuses an image plan` |
| 2. an image change accepted (the `image` key and the owner-digest rule both gone) | CAUGHT, 4 failed | `an image change as well`, `the digest line replaced as well`, `a run task on another image than the owner file's` |
| 2b. the `image` key alone dropped | CAUGHT, 3 failed | `the digest line replaced as well` (added for this: before it, only a message assertion caught it) |
| 3. a memory other than 32768 accepted | CAUGHT, 2 failed | `a memory of 28 GB`, `a memory of 60 GB` |
| 3b. the memory left at 16384 accepted | CAUGHT, 1 failed | `the memory left at 16 GB` |
| 3c. a vCPU change accepted | CAUGHT, 1 failed | `a vCPU change` |
| 4. an Identity Center change accepted (`forbidden = []`; such changes are already outside `rest`, so they pass silently) | CAUGHT, 7 failed | the three Identity Center cases in both modes, `an Identity Center change anywhere says never to apply` |
| 5. the schedule's old revision accepted (`known_revision` skipped) | CAUGHT, 1 failed | `the run schedule set to another revision already registered` |
| 5b. the run schedule not required to change | CAUGHT, 6 failed | `the run schedule left on the old revision`, and the OK cases |

**Before the report (agreement 10):**

* `uv run scripts/affected_tests.py --run`: 93 of 627 files chosen (the runbook and the ADR are named
  by many tests). Under `scripts/hard_stop.py 115` it was stopped at its limit, 88% through 3,185
  tests, with no failure up to there. That is over two minutes, so it is left to the pull request's `ci`, which runs the
  same set. Within the limit, before and again after the sync: the always-run list, `tests/docs`,
  `tests/infrastructure` and the caselist-run script tests (`test_caselist_run_image_plan_check.py`,
  `test_caselist_run_deploy.py`, `test_start_backfile_import.py`, `test_compare_cloud_run.py`,
  `test_check_command_blocks.py`) → `818 passed in 29.43s`, and after the sync `822 passed in 77.02s`.
* `uv run ruff format --check .` → `1735 files already formatted`; `uv run ruff check .` → `All checks passed!`
* `uv run pyright ops/caselist_run/check_image_plan.py tests/scripts/test_caselist_run_image_plan_check.py`
  → `0 errors` (neither path is in pyright's `include`, so they were named; no package changed).
* `uv run lint-imports` → `Contracts: 20 kept, 0 broken.`
* `uv run scripts/validate_specs.py` → `OK: 554 files, 41 epics, 491 tasks, 22 releases`
* `scripts/check_links.py` → `OK: 3260 relative links and anchors in 512 Markdown files`;
  `scripts/check_command_blocks.py` → no `#` comments; `scripts/docs_index.py --check-descriptions` → OK.

All counts are from this branch, rebased by `scripts/task sync` onto `origin/dev` at `d2a1c2c`. The
mutant runs and the first checks ran before the sync, on the same code (the sync changed only another
task's runbook paragraph).

## Files changed

* `infrastructure/modules/caselist_run/run_task.tf`: `run_memory` 16384 → 32768, and the two comments
  that said 16 GB. `tests/caselist_run.tftest.hcl`: the size assertion pins 32768. `README.md`: the
  file table's size.
* `ops/caselist_run/check_image_plan.py`: the shared screening (owner digest, Identity Center, outside
  the module, container comparison, `Plan` counts) pulled into helpers in its own commit (`82c8f72`,
  the 41 image tests passing on it alone); then `--memory` with `check_memory`, `memory_problems` and
  `known_revision`; the docstring describes the mode.
* `tests/scripts/test_caselist_run_image_plan_check.py`: a `--memory` section, using the file's own plan
  builders: the OK shape, 32 refusals, each mode refusing the other's plan, and 5 runbook-section tests.
* `docs/adr/0020-weekly-caselist-run-in-the-cloud.md`: a dated amendment under (1) 2's memory paragraph,
  and two rows in the AWS documentation table. The original text is unchanged.
* `docs/runbooks/caselist-cloud-run.md`: "The run task's memory", after "A new image, later".

## Deviations from the spec

1. **"The two schedules and the scheduler policies pointed at the new revision" is one schedule and one
   policy.** The spec's description asks the check for the image check's repointing, but a memory
   change replaces only the run task definition. The login's revision does not change, so its
   schedule and policy have nothing to repoint to. The PM's brief for this task says the same ("the
   run schedule repointed ... The login task definition, its schedule and policy are untouched"). The
   check implements that, and treats any change to the login schedule or policy as a refusal. The
   spec's sentence should read "the run schedule and the run scheduler's policy pointed at the new
   revision".
2. **The node's command was run under the time limit.** It was `.venv/bin/python scripts/hard_stop.py 115
   uv run pytest tests/scripts -k plan_check`, as the brief asks for every pytest.

## Decisions and assumptions

* **A mode, not a sibling.** The operator runs the check with `python3 -I`, which leaves the script's
  directory off `sys.path`, so a sibling could not import the image check's helpers. It would have
  needed a copy of them. `--memory` shares them. The image mode's `check()` keeps its behaviour, and
  its 41 tests are unchanged and pass. The refactor that made sharing possible is a commit of its own.
* **Stricter than the image check on the schedule.** The memory mode also refuses a run schedule whose
  new task definition ARN is already known when the plan is made. A known ARN is a revision registered
  earlier, not the one this apply creates, and that is the only way a repointed target could still pass
  the image check's "only `target` changed" rule. This reads `after_unknown`'s nested
  `target[0].ecs_parameters[0].task_definition_arn`, the shape Terraform documents (unknown leaves
  `true`, absent from `after`) and the shape the image check's fixtures already use. If a real plan
  differed, the check would print `PLAN STOP` naming the schedule; it fails closed. The image mode was
  not tightened the same way, to leave its behaviour untouched.
* **The image is checked too.** The run task definition's image must be the same before and after
  (the `image` key) and must be `owner.auto.tfvars`'s digest. The owner file stays the second argument.
* **The size.** At 8 vCPU, AWS's [Task CPU and memory](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-tasks-services.html#fargate-tasks-size)
  table allows "Between 16 GB and 60 GB in 4 GB increments" (Linux, platform 1.4.0 or later), read
  2026-10-31. So 32 GB is valid, and 60 GB is the ceiling without more CPU.
* **The price, from AWS's page, not memory.** [AWS Fargate pricing](https://aws.amazon.com/fargate/pricing/),
  read 2026-10-31: the region table did not load. The page's Example 2 gives Linux/ARM in US East
  (N. Virginia) memory at $0.0000009889 per GB-second, the same rate as ADR-0020 (8)'s $0.00356004
  per GB-hour. 16 GB more is $0.05696064 an hour. That is about $0.085 for a weekly run at (8)'s 1.5-hour *estimate*,
  about $0.37 a month, at most $0.34 for any one task (the 6-hour deadline), and $0.067 for the 71
  minutes of the killed import. No cloud run's duration has been measured yet, so the per-run figures
  rest on (8)'s estimate. The per-hour figure does not.
* **Reading the two public AWS pages in the session.** My standing rule hands every live network call to
  the operator. The PM's brief for this task says "public docs are fine to read", so I fetched the two
  pages directly. That is no AWS account access, which the spec forbids.
* **The deploy script needs no change.** `scripts/caselist_run_deploy.sh` registers a copy of the
  family's newest ACTIVE revision with only the image changed (`test_a_push_registers_the_current_run_definition_with_only_its_image_changed`
  pins this). It sets no size of its own. After the apply the newest is Terraform's 32 GB revision, so a
  later push carries 32 GB. A push before the apply would copy revision 10's 16 GB, so the runbook says
  to push nothing until this is applied. Revision 9 (16 GB, from the `v1.1.0-dev.251` push) is left as it is.
* **Backfile imports.** `start_backfile_import.py` starts `--task-definition "$REVISION"` from Terraform's
  output, so they get 32 GB once that is read after the apply. The runbook says a `REVISION` read
  before the apply names the deregistered revision.
* **The apply block refuses a task running on the run's cluster.** This follows agreement 11 ("no
  caselist pull is running"), because the apply deregisters the revision such a task started from. It
  fails closed when the count cannot be read. `!=` was left out of the blocks, so no `!` appears in
  them at all.
* **No `-login-task-changed` email is expected**, since nothing registers a login revision. The runbook
  says one goes to the PM.
* **After the sync.** `v1-e39-t28` merged during the session and removed the image hold paragraph.
  The section now says the hold was lifted, and that it never applied to a change with no image.

## Operator follow-ups

Run these **after this task merges into dev**, on any day but Wednesday, **before 2026-11-04 06:00
Chicago**. They are the runbook's ["The run task's memory"](../runbooks/caselist-cloud-run.md#the-run-tasks-memory)
blocks, in the worktree the runbook's "Before you start" names.

**The worktree, at dev with this task in it** (expected runtime seconds).
Where: your Mac
```bash
WT="$HOME/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/caselist-credentials-dev"
cd "$WT"
git fetch origin
git switch --detach origin/dev
grep -q '^  run_memory             = "32768"$' infrastructure/modules/caselist_run/run_task.tf && grep -q -- '"--memory"' ops/caselist_run/check_image_plan.py && echo "ok: $(git rev-parse --short HEAD), the run task at 32768 and the check's --memory mode merged" || echo "NOT MERGED: wait for v1-e40-t30 to merge into dev"
git status --porcelain | grep -v 'owner.auto.tfvars' | head -3
```
Success looks like the `ok:` line and nothing after it.

**Sign in as break-glass** (expected runtime ~1 min).
Where: your Mac, anywhere
```bash
aws sso login --sso-session debate
aws sts get-caller-identity --profile debate-admin --query Arn --output text
```
Success looks like an ARN containing `AWSReservedSSO_DebateBreakGlassAdmin`.

**The plan, saved, and the check** (expected runtime ~2 min).
Where: `$WT`
```bash
cd "$WT"
rm -f infrastructure/envs/dev/caselist-run-memory.tfplan /tmp/caselist-run-memory-plan.json
if env | grep -qE '^(TF_VAR_|TF_WORKSPACE=|TF_DATA_DIR=|TF_CLI_ARGS)'; then echo "STOP: a Terraform override is set in this shell"; else AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev init -input=false >/dev/null && AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev plan -input=false -no-color -out=caselist-run-memory.tfplan | tee /tmp/caselist-run-memory-plan.txt | tail -3; fi
AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev show -json caselist-run-memory.tfplan > /tmp/caselist-run-memory-plan.json
python3 -I ops/caselist_run/check_image_plan.py /tmp/caselist-run-memory-plan.json infrastructure/envs/dev/owner.auto.tfvars --memory
```
Success looks like `Plan: 1 to add, 2 to change, 1 to destroy.` and then `PLAN OK: 1 to add, 2 to change, 1 to
destroy; the run task definition replaced with its memory 16384 -> 32768 and nothing else in it
changed, 8192 CPU units and the image sha256:<digest>... as before; ...`. Send both lines to the PM
with `/tmp/caselist-run-memory-plan.txt`. Stop there: a `PLAN STOP` line, or any other `Plan:`
line, goes to the PM, and nothing is applied until the PM says so.

**The apply, after the PM's word** (expected runtime ~1 min). This is a separate block from the plan.
It refuses a Wednesday in Chicago, a Terraform override, and a task running on the run's cluster.
Where: `$WT`
```bash
cd "$WT"
RUNNING="$(AWS_PROFILE=debate-admin aws ecs list-tasks --region us-east-1 --cluster debate-dev-caselist-run --desired-status RUNNING --query 'length(taskArns)' --output text)" || RUNNING="unknown"
if [ "$(TZ=America/Chicago date +%A)" = "Wednesday" ]; then echo "STOP: it is Wednesday in Chicago, the run's day; apply on another day"; elif env | grep -qE '^(TF_VAR_|TF_WORKSPACE=|TF_DATA_DIR=|TF_CLI_ARGS)'; then echo "STOP: a Terraform override is set in this shell"; elif [ "$RUNNING" = "0" ]; then AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev apply -input=false caselist-run-memory.tfplan; else echo "STOP: ${RUNNING} tasks running on debate-dev-caselist-run, or the count could not be read; apply when it is 0"; fi
```
Success looks like `Apply complete! Resources: 1 added, 2 changed, 1 destroyed.` No
`-login-task-changed` email should arrive. If one does, send it to the PM.

**The read-back** (expected runtime seconds).
Where: `$WT`, after the apply
```bash
cd "$WT"
SCHEDULED="$(AWS_PROFILE=debate-admin aws scheduler get-schedule --region us-east-1 --group-name debate-dev-caselist-run --name debate-dev-caselist-run --query Target.EcsParameters.TaskDefinitionArn --output text)"
echo "scheduled: ${SCHEDULED}"
echo "terraform: $(AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev output -raw caselist_run_task_definition_arn)"
AWS_PROFILE=debate-admin aws ecs describe-task-definition --region us-east-1 --task-definition "$SCHEDULED" --query 'taskDefinition.[cpu,memory]' --output text
AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev output caselist_run_schedule_state
```
Success looks like two equal `…:task-definition/debate-dev-caselist-run:<n>` ARNs with `<n>` above 10,
then `8192	32768`, then `"ENABLED"`. The PM records the plan line, the check's line and these four
lines as ac3.

**The PR's `ci`** runs the affected set (93 files), which ran past two minutes in the session. No
operator run is needed for it.

**For the PM to relay, if useful:**

```text
v1-e40-t30 deviation, for a spec amendment: the description says the memory plan check expects "the two schedules and the scheduler policies pointed at the new revision". A memory change replaces only the run task definition, so only the run schedule and the run scheduler's policy change (Plan: 1 to add, 2 to change, 1 to destroy), and the check refuses any login schedule or policy change. Recommended amendment: "the run schedule and the run scheduler's policy pointed at the new revision". The alternative, keeping the sentence, would describe a plan this change cannot produce.
```

## Follow-up work

* **Measure the parse's memory peak at 32 GB.** Nothing records it yet. The kill left no log line,
  so it is not known whether 32 GB has wide margin or narrow. Recording the task's peak memory from
  Wednesday's run, or the re-started `hspolicy25` import, in `docs/data/caselist-backfile-seasons.md`
  or the ADR would let a later task size it from a measurement (E40, or v1-e40-t09's ac3 record).
* **The image check could take the same known-revision rule.** The `--memory` mode refuses a schedule
  repointed at a revision known before the apply. The image mode does not, because this task left its
  behaviour untouched. A small E41 upkeep task could add it to both modes.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-31

**Notes:**

This is the change Wednesday needs, built so that a plan which does anything else cannot pass.
1. **ac1 passes.**
   * `run_memory` is 32768, and vCPU, workers, volume, image and the login task are untouched.
   * `terraform_checks.sh` passes. The module's `terraform test` pins 32 GB and fails with 16384
     put back.
2. **ac2 passes.**
   * Red on a refuse-nothing skeleton: 40 failed, all at assertions. The two that passed can't be
     failed by a skeleton, and the report says why.
   * Green: 84, with the image mode's 41 unchanged.
   * All nine mutants are caught, the PM's five among them. Each was probed to confirm it really
     printed `PLAN OK`, which is the right way to read a plan-check mutant. 2b gained its own case.
3. **ac3 is the operator's**, as the report's blocks lay out, before 2026-11-04 06:00 and not on a
   Wednesday. The Goal stays `InProgress`.
4. **Deviation 1: accepted.** It is one schedule and one policy, the run's. The PM's next batch
   amends the description to "the run schedule and the run scheduler's policy pointed at the new
   revision".
5. **Decisions accepted:**
   * a `--memory` mode rather than a sibling, since `python3 -I` keeps a sibling from importing the
     helpers, with the shared screening split into its own commit;
   * the known-revision rule on the run schedule, which fails closed on an unexpected plan shape;
   * the image checked against `owner.auto.tfvars` in this mode too;
   * the sizes and the price taken from AWS's pages, read 2026-10-31, with the per-run figures
     marked as resting on ADR-0020 (8)'s estimate. Reading public docs was within the brief;
   * the deploy script needs no change, with the runbook's rule to push no image before this
     apply;
   * a `REVISION` read before the apply names the deregistered revision, and the runbook says so;
   * the apply block refuses a running task, a Wednesday and a Terraform override, and fails
     closed on an unreadable count.
6. **Follow-ups, the PM's rulings:**
   * **The parse's memory peak:** folded into v1-e40-t31 by the next batch. The run records its own
     high-water mark at the end, so the size comes from a measurement next time.
   * **The known-revision rule for the image mode:** one p3 E41 task in the next batch.
7. **Closing checks:** the affected set (93 files) stopped at 88% at its limit with nothing failing,
   and is left to the PR's `ci` under agreement 10. The always-run list, docs, infrastructure and
   the caselist-run script tests (822), ruff, pyright on the two named paths, lint-imports, the doc
   checks and the specs are clean.
8. **Merge:** `scripts/task pr --partial` once `ci` is green, because ac3, the apply, follows the
   merge. Then the report's blocks, with the plan line and the check's line sent to the PM before
   the apply.

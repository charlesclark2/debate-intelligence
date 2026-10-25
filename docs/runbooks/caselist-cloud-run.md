<!-- docs-index: The weekly cloud run's container: applying its network, cluster, repository and deployer, pushing its image, the login and run tasks with their schedules, and one run by hand -->
# Runbook: the weekly caselist run as a container on a schedule

How the weekly caselist run becomes a Fargate task in the team's AWS account: its network, cluster,
image repository and deployer permission set; its image, built from a release and pushed; the login
and run task definitions with their Wednesday schedules (apply B); and one run started by hand.
Spec: [`v1-e40-t03-run-image-and-schedule`](../../plan_specs/v1/e40-cloud-caselist-run/t03-run-image-and-schedule.yaml).
Decision: [ADR-0020](../adr/0020-weekly-caselist-run-in-the-cloud.md) (1), (5). The credentials and
the login are [caselist-cloud-credentials.md](caselist-cloud-credentials.md)'s (`v1-e40-t02`). The
module: [`infrastructure/modules/caselist_run`](../../infrastructure/modules/caselist_run/README.md).

Written for the adult maintainer with administrator access to the account. **Every step here is run
by a human.** CI builds the image and runs it against stand-ins, but has no AWS credentials, and an
agent session never applies, pushes or calls AWS.

## What this sets up

| | dev | prod |
|---|---|---|
| The run's VPC, subnets, security group | `debate-dev-caselist-run`: two public subnets, no inbound rule, outbound HTTPS, an S3 gateway endpoint | the same, `debate-prod-caselist-run`, at the promotion |
| Cluster, image repository, log group | `debate-dev-caselist-run` | `debate-prod-caselist-run` |
| Run task definition | `debate-dev-caselist-run`: Fargate, arm64, 8 vCPU, 16 GB, 100 GiB, `debate-research --json caselist pull` under a 6-hour deadline, as the run role | the same |
| Run schedule (apply B) | `debate-dev-caselist-run`, Wednesdays 06:00 America/Chicago, **created disabled** | the same |
| Login task and schedule (apply B) | t02's, Wednesdays 03:00 America/Chicago, now on this network and image | the same |
| The deployer: pushes the image, registers a run task definition, starts a run | `DebateDevCaselistRunDeployer` | `DebateProdCaselistRunDeployer` |
| Its SSO profile | `debate-dev-caselist-run-deployer` | `debate-prod-caselist-run-deployer` |

The run role (t02's `debate-<env>-caselist-run`) now holds the everyday evidence permissions, the
EvidenceOperator permission set's own document, beside its read of the token: it lists, reads and
publishes, and never deletes, and it never reads the password. The deployer may pass the run's two
roles to ECS and is refused the login's, so nobody but the schedule ever starts the login.

## The order

1. `v1-e40-t02`'s apply A in dev: the key, the secrets, the roles, the writer
   ([caselist-cloud-credentials.md](caselist-cloud-credentials.md), steps 1 to 4).
2. **This runbook's steps 1 and 2**: the network, the cluster, the repository, the run's execution
   role and log group, the run role's evidence policy and the deployer. No image is needed.
3. Steps 3 and 4: the deployer's profile, and the first image, built from a release and pushed.
4. Step 5, **apply B**: both task definitions, pinned by that image's digest, the login's schedule
   enabled and the run's disabled.
5. Step 6, **one run by hand**, after `v1-e40-t04`: until bucket mode and its lock are applied, a
   cloud run would start from an empty data directory, download every archive again and publish
   without the bucket's lock. Step 6 says so again.
6. The run's schedule is enabled at the cutover (`v1-e40-t06`), never before.

**Every dev apply here runs from `dev`, after `v1-e40-t03` has merged, never from a task branch**,
for the reason t02's runbook gives: an apply from a configuration without these resources would plan
to destroy them.

## Before you start

**The same worktree as t02's applies**, `caselist-credentials-dev`, moved to `origin/dev`, and the
check that this task's module is merged in it. Its gitignored `owner.auto.tfvars` is the one apply A
used.

```bash
WT="$HOME/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/caselist-credentials-dev"
SSO_USER_NAME='your-identity-center-user-name'

cd "$WT" || { echo "WT does not exist: $WT"; }
git fetch origin
git switch --detach origin/dev
test -f infrastructure/modules/caselist_run/run_task.tf && test -f ops/caselist_run/Dockerfile \
  && echo "ok: $(pwd) at origin/dev $(git rev-parse --short HEAD), the run merged" \
  || echo "NOT MERGED: origin/dev has no infrastructure/modules/caselist_run/run_task.tf; wait for v1-e40-t03 to merge"
git status --porcelain | grep -v 'owner.auto.tfvars' | head -3
```
Success looks like: `ok: <the worktree> at origin/dev <commit>, the run merged`, and nothing after
it. If the worktree does not exist, make it as t02's runbook does ("Before you start") and copy
`owner.auto.tfvars` from the checkout that last applied dev.

**Sign in as break-glass**, which every apply here runs as.

**Operator command** (expected runtime ~1 min)
Where: your Mac, anywhere
```bash
aws sso login --sso-session debate
aws sts get-caller-identity --profile debate-admin --query Arn --output text
```
Success looks like: an ARN containing `AWSReservedSSO_DebateBreakGlassAdmin`.

**The deployer's line in `owner.auto.tfvars`**, beside every person it already names. A plan made
without one of them would remove that person's account assignment.

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
grep -q '^caselist_run_deployer_user_names' infrastructure/envs/dev/owner.auto.tfvars \
  || printf 'caselist_run_deployer_user_names = ["%s"]\n' "$SSO_USER_NAME" >> infrastructure/envs/dev/owner.auto.tfvars
terraform fmt infrastructure/envs/dev
grep -c -E '^(owner|site_publisher_user_names|evidence_operator_user_names|evidence_removal_user_names|evidence_search_deployer_user_names|evidence_search_accounts_user_names|caselist_credential_writer_user_names|caselist_run_deployer_user_names) ' infrastructure/envs/dev/owner.auto.tfvars
grep -c '^caselist_image_digest' infrastructure/envs/dev/owner.auto.tfvars
```
Success looks like `8`, then `0`. Fewer than 8: a line is missing, so find it in the checkout that
last applied dev before planning. A `1` on the second line means an image digest is already set,
which belongs to step 5: take that line out for step 1's plan.

## Step 1 — Plan the run's network, cluster, repository and deployer

Saved to a file, so what step 2 applies is exactly what was read here.

**Operator command** (expected runtime ~2 min)
Where: `$WT`
```bash
cd "$WT"
if env | grep -qE '^(TF_VAR_|TF_WORKSPACE=|TF_DATA_DIR=|TF_CLI_ARGS)'; then echo "STOP: a Terraform override is set in this shell:"; env | grep -oE '^(TF_VAR_[A-Za-z_]*|TF_WORKSPACE|TF_DATA_DIR|TF_CLI_ARGS[A-Za-z_]*)'; else AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev init -input=false && AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev plan -input=false -no-color -out=caselist-run.tfplan | tee /tmp/caselist-run-plan.txt | tail -5; fi
grep -E '^Plan:|must be replaced|will be destroyed' /tmp/caselist-run-plan.txt
grep -E '^  # ' /tmp/caselist-run-plan.txt | grep -v 'module.caselist_run' | head
grep -E '^  # .* will be updated in-place' /tmp/caselist-run-plan.txt
```

**What to read, and what stops you.** Send the whole plan (`/tmp/caselist-run-plan.txt`) to the PM
before step 2. No `Plan:` line at all means the plan failed: read the end of the file.

* The first `grep` prints exactly `Plan: 23 to add, 1 to change, 0 to destroy.`, and **no line saying
  `must be replaced` or `will be destroyed`**. A destroyed or replaced `aws_ssoadmin_account_assignment`
  or `aws_ssoadmin_permission_set` anywhere means `owner.auto.tfvars` is missing a line: **stop, fix
  the file, plan again, never apply.**
* The second `grep` prints nothing: every change is under `module.caselist_run`.
* The third prints exactly one line, `module.caselist_run.aws_iam_role_policies_exclusive.run will be
  updated in-place`: the run role's policy list gains `everyday-evidence`.
* The 23 are: the VPC, its default security group (taken over with no rule), the internet gateway,
  two subnets, the route table, its internet route, two route table associations, the S3 gateway
  endpoint and the security group (11); the cluster, the repository and its lifecycle policy (3);
  the run's log group and its execution role with one inline policy and two exclusive-policy
  resources (5); the run role's `everyday-evidence` policy (1); the `DebateDevCaselistRunDeployer`
  permission set, its inline policy and one account assignment (3).
* `Plan: 40 to add` means t02's apply A has not been applied: stop, and do that first.
* There is no task definition and no schedule yet: those need an image (step 5).

## Step 2 — Apply the saved plan

Only after the PM's word on step 1's plan.

**Operator command** (expected runtime ~2 min)
Where: `$WT`
```bash
cd "$WT"
AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev apply -input=false caselist-run.tfplan
AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev output caselist_run_deployer_permission_set_name
AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev output caselist_run_repository_url
```
Success looks like `Apply complete! Resources: 23 added, 1 changed, 0 destroyed.`, then
`"DebateDevCaselistRunDeployer"` and the repository's URL ending `/debate-dev-caselist-run`. A stale
plan (`Saved plan is stale`) means something changed in between: go back to step 1.

## Step 3 — The deployer's SSO profile

Once per Mac.

**Operator command** (expected runtime ~1 min)
Where: your Mac, anywhere
```bash
ACCOUNT_ID=$(aws sts get-caller-identity --profile debate-admin --query Account --output text)
aws configure set profile.debate-dev-caselist-run-deployer.sso_session debate
aws configure set profile.debate-dev-caselist-run-deployer.sso_account_id "$ACCOUNT_ID"
aws configure set profile.debate-dev-caselist-run-deployer.sso_role_name DebateDevCaselistRunDeployer
aws configure set profile.debate-dev-caselist-run-deployer.region us-east-1
aws sso login --sso-session debate
aws sts get-caller-identity --profile debate-dev-caselist-run-deployer --query Arn --output text
```
Success looks like: an ARN containing `AWSReservedSSO_DebateDevCaselistRunDeployer`. Identity Center
can take a minute to provision a new set's role; if the last line says the role does not exist, wait
a minute and run it again.

## Step 4 — Build the first image and push it

The image is the installed CLI from one release, built for arm64 on this Mac (no emulation). Use a
dev pre-release that contains `v1-e40-t03`'s merge and whose validate-dev run, image job included,
is green. List the newest three, and set `TAG` in this shell to the newest:

```bash
cd "$WT"
gh release list --repo charlesclark2/debate-intelligence --limit 3 --json tagName,createdAt --jq '.[] | .tagName + " " + .createdAt'
TAG="$(gh release list --repo charlesclark2/debate-intelligence --limit 1 --json tagName --jq '.[0].tagName')"
echo "TAG=$TAG"
```
If the newest is not the one to use, set the one that is in the same shell, for example
`TAG='v1.1.0-dev.140'`. The next two blocks read `TAG` and stop if it is empty.

**The dry run first**: it downloads the release's wheels, builds the image and checks it offline
(arm64, an unprivileged user, no credential in its environment or files, `debate-research` and
`timeout` on `PATH`, the tag, SQLite with FTS5 at 3.40.0 or later). It makes no AWS call. Docker
Desktop must be running.

**Operator command** (expected runtime ~1 min: 26 s on the operator's Mac for `v1.1.0-dev.134`,
2026-10-24)
Where: `$WT`, in the shell that set `TAG`
```bash
cd "$WT"
if [ -z "$TAG" ]; then echo "STOP: TAG is not set; run the listing block first"; elif env | grep -qE '^(CASELIST_RUN_DEPLOY_PROFILE|DEBATE_RELEASE_REPO)='; then echo "STOP: a deploy override is set in this shell"; else time scripts/caselist_run_deploy.sh dev "$TAG" --dry-run; fi
```
Success looks like six `ok:` lines, the last `ok: SQLite 3.x.y with FTS5`, then `Dry run complete.
debate-dev-caselist-run:<tag> built and checked`. Any `check image:` line says what is wrong, and
nothing was pushed. Note the `real` time for the PM: it is the build's measured runtime.

**Then the push.** It pushes the image as the deployer, tagged with the release, and stops before
registering a task definition, because none exists before apply B. It prints the digest.

**Operator command** (expected runtime ~3 min)
Where: `$WT`
```bash
cd "$WT"
aws sso login --sso-session debate
if [ -z "$TAG" ]; then echo "STOP: TAG is not set; run the listing block first"; elif env | grep -qE '^(CASELIST_RUN_DEPLOY_PROFILE|DEBATE_RELEASE_REPO)='; then echo "STOP: a deploy override is set in this shell"; else scripts/caselist_run_deploy.sh dev "$TAG" 2>&1 | tee /tmp/caselist-run-deploy.txt | tail -8; fi
grep -E '^pushed: |caselist_image_digest = ' /tmp/caselist-run-deploy.txt
```
Success looks like `pushed: <account>.dkr.ecr.us-east-1.amazonaws.com/debate-dev-caselist-run@sha256:<64
hex digits>`, then the line `caselist_image_digest = "sha256:<the same digits>"` under "before the
environment's apply B". No `pushed:` line means the push failed: the lines above it say why.

## Step 5 — Apply B: the login and run tasks and their schedules

Apply B is t02's and this task's together: the login task definition and its Wednesday 03:00
schedule, and the run task definition and its Wednesday 06:00 schedule, both pinned by the digest
step 4 printed. The digest goes in the gitignored `owner.auto.tfvars`, which every later dev apply
already carries; a plan without it would destroy both tasks, and the plan check below stops that.

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
DIGEST='sha256:the-64-hex-digits-step-4-printed'
grep -q '^caselist_image_digest' infrastructure/envs/dev/owner.auto.tfvars && echo "STOP: owner.auto.tfvars already names an image digest" || printf 'caselist_image_digest = "%s"\n' "$DIGEST" >> infrastructure/envs/dev/owner.auto.tfvars
terraform fmt infrastructure/envs/dev
grep -cE '^caselist_image_digest += "sha256:[0-9a-f]{64}"$' infrastructure/envs/dev/owner.auto.tfvars
```
Success looks like `1`. `0` means the digest is not 64 hex digits: correct the line by hand.

**The plan.**

**Operator command** (expected runtime ~2 min)
Where: `$WT`
```bash
cd "$WT"
if env | grep -qE '^(TF_VAR_|TF_WORKSPACE=|TF_DATA_DIR=|TF_CLI_ARGS)'; then echo "STOP: a Terraform override is set in this shell"; else AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev plan -input=false -no-color -out=caselist-tasks.tfplan | tee /tmp/caselist-tasks-plan.txt | tail -5; fi
grep -E '^Plan:|must be replaced|will be destroyed' /tmp/caselist-tasks-plan.txt
grep -E '^  # ' /tmp/caselist-tasks-plan.txt | grep -v 'module.caselist_run' | head
grep -E '^ +[+] (schedule_expression|state) ' /tmp/caselist-tasks-plan.txt
grep -cE '^ +[+~] secrets ' /tmp/caselist-tasks-plan.txt
```

**What to read, and what stops you.** Send the plan to the PM; apply only after the PM's word.

* `Plan: 17 to add, 0 to change, 0 to destroy.`, no line saying `must be replaced` or `will be
  destroyed`, and nothing printed by the second `grep`.
* The third prints the login's `cron(0 3 ? * WED *)` with `ENABLED`, and the run's `cron(0 6 ? * WED
  *)` with **`DISABLED`**. A run schedule `ENABLED` here is wrong: stop.
* The last prints `0`: no secret reaches either task through ECS.
* The 17: t02's 11 (the login's log group, its execution role and the scheduler role, each with one
  inline policy and two exclusive-policy resources, its task definition and schedule) and the run's
  6 (its task definition, whose image ends `@` and the digest, its scheduler role with one inline
  policy and two exclusive-policy resources, and its schedule).

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev apply -input=false caselist-tasks.tfplan
AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev output caselist_run_schedule_state
```
Success looks like `Apply complete! Resources: 17 added, 0 changed, 0 destroyed.`, then
`"DISABLED"`. The first scheduled login runs the next Wednesday at 03:00 Chicago time; t02's
runbook, step 5's last block, checks it.

## Step 6 — One run by hand (after `v1-e40-t04`)

**Not before `v1-e40-t04`'s bucket mode is applied and the lock seeded.** Today a cloud run starts
from an empty data directory: it would select every week as new, spend the day's five downloads,
and publish to the dev bucket while the Mac's agent may too, with no lock between them (the PM's
ruling for this task). Once t04 is applied, a hand-started run restores the working copy and takes
the lock first.

The network a run by hand starts in is the schedule's: read it from the root's outputs.

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
SUBNETS=$(AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev output -json caselist_run_subnet_ids | tr -d '[]" \n')
SECURITY_GROUP=$(AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev output -raw caselist_run_security_group_id)
echo "subnets ${SUBNETS}; security group ${SECURITY_GROUP}"
```
Success looks like two `subnet-` ids joined by a comma, and one `sg-` id.

**Start it.** As the deployer, on the run's cluster, the newest revision of the run's family.

**Operator command** (expected runtime ~1 min to start; the run takes up to about 2.5 hours)
Where: `$WT`
```bash
cd "$WT"
TASK=$(aws ecs run-task --profile debate-dev-caselist-run-deployer --region us-east-1 --cluster debate-dev-caselist-run --task-definition debate-dev-caselist-run --launch-type FARGATE --platform-version LATEST --count 1 --network-configuration "awsvpcConfiguration={subnets=[${SUBNETS}],securityGroups=[${SECURITY_GROUP}],assignPublicIp=ENABLED}" --query 'tasks[0].taskArn' --output text)
echo "started ${TASK}"
```
Success looks like `started arn:aws:ecs:us-east-1:<account>:task/debate-dev-caselist-run/<id>`.
`None` means it did not start: run it again without `--query` to see the failure.

**Watch it**, every half hour or so. `RUNNING` while it runs; at the end, `STOPPED` with exit code
`0`. A non-zero exit, or `EssentialContainerExited` with no exit code, is a failed run: read its log.

```bash
aws ecs describe-tasks --profile debate-dev-caselist-run-deployer --region us-east-1 --cluster debate-dev-caselist-run --tasks "$TASK" --query 'tasks[0].[lastStatus,stopCode,containers[0].exitCode]' --output text
aws logs tail debate-dev-caselist-run --profile debate-dev-caselist-run-deployer --region us-east-1 --since 3h | tail -3
```

**Its record reads as a Mac run's does** (ac2). The run published its record to the bucket like any
run; `caselist runs --remote` on the Mac, with the everyday profile, lists it beside the Mac's runs,
and the record's keys are the Mac record's keys.

**Operator command** (expected runtime ~1 min)
Where: your Mac, the installed build
```bash
aws sso login --profile debate-dev-evidence
debate-research caselist runs --remote --last 3
```
Success looks like the cloud run's id (the UTC time it started) at the top, with its outcome and
counts in the same columns as the Mac's runs, and no warning that a record was skipped or unreadable.

## A new image, later

Each new release reaches the run in two steps: the deploy script builds, checks, pushes and registers
a run task definition with the new image (so a run by hand runs it), and prints the
`caselist_image_digest` line. The schedule and the login move only when that line replaces the old
one in `owner.auto.tfvars` and an apply that the PM has read puts it in both task definitions. A
task definition is replaced, never changed, so expect `Plan: 2 to add, 4 to change, 2 to destroy.`:
the login and run task definitions each replaced (a new revision, the old one deregistered, the two
`must be replaced` lines here and nowhere else), and the two schedules and the two scheduler roles'
policies pointed at the new revisions. Nothing else, and never an account assignment or a
permission set.

Keep at most four pushes between applies: the repository keeps the five newest images, and a task
definition pins one by digest.

## The deadline, and stopping a run

The run's command is `timeout --signal=TERM --kill-after=120s 6h debate-research --json caselist
pull`: at six hours the CLI gets SIGTERM, as `docker stop` would send, and SIGKILL two minutes later,
and the task stops with a non-zero exit (ADR-0020 (1) 6). To stop a run sooner, as the deployer:

```bash
aws ecs stop-task --profile debate-dev-caselist-run-deployer --region us-east-1 --cluster debate-dev-caselist-run --task "$TASK" --reason "stopped by the operator" --query 'task.desiredStatus' --output text
```
Success looks like `STOPPED`. ECS sends SIGTERM and gives the same two minutes.

## Prod, at the pilot's promotion (follow-up)

The same steps against `infrastructure/envs/prod`, from a checkout of `main`, with `prod` for `dev`
in every name (`debate-prod-caselist-run`, `DebateProdCaselistRunDeployer`, the profile
`debate-prod-caselist-run-deployer`), and a stable release: the deploy script refuses a dev
pre-release for prod. ADR-0020 (7) moves the run's home at the same time; `v1-e40-t06`'s runbook
orders the two.

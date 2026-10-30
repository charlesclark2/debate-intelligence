<!-- docs-index: The weekly cloud run's container: applying its network, cluster, repository and deployer, checking whether a new login ends the Mac's token, pushing its image, the login and run tasks with their schedules, a dry-run rehearsal, one run by hand, and the backfile imports started by hand on the run's task definition -->
# Runbook: the weekly caselist run as a container on a schedule

How the weekly caselist run becomes a Fargate task in the team's AWS account: its network, cluster,
image repository and deployer permission set; a hand login that shows whether a new login ends the
Mac's token; its image, built from a release and pushed; the login and run task definitions with
their Wednesday schedules (apply B); a dry-run rehearsal in the cloud; and one run started by hand.
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
3. Step 3, **the token check** (PM ruling, 2026-10-24): does a new login end the Mac's keychain
   token? A hand login as the writer answers it before the login's schedule exists, and puts a
   token in the secret. If it does, apply B pauses the login until `v1-e40-t06`.
4. Steps 4 and 5: the deployer's profile, and the first image, built from a release and pushed.
5. Step 6, **apply B**: both task definitions, pinned by that image's digest, the login's schedule
   enabled (unless step 3 paused it) and the run's disabled.
6. Step 7, **the cloud rehearsal**: one run started by the deployer as a dry run, which lists and
   writes nothing.
7. Step 8, at the cutover (`v1-e40-t06`), after `v1-e40-t04`: **the seed**, once the Mac's agent is
   unloaded; then the run task **in bucket mode**, applied; then **one run by hand**. Until bucket
   mode and its lock are applied, a cloud run would start from an empty data directory, download
   every archive again and publish without the bucket's lock (the PM's rulings on t04's plan,
   2026-10-24). Step 8 says so again.
8. The run's schedule is enabled at the cutover (`v1-e40-t06`), never before.

The alerts that email the coach when a run or the login fails, a run is late or a schedule cannot
start (`v1-e40-t05`) are applied after apply B, with an image that has them:
[caselist-run-alerts.md](caselist-run-alerts.md).

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
which belongs to step 6: take that line out for step 1's plan.

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
* There is no task definition and no schedule yet: those need an image (step 6).

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

## Step 3 — Does a new login end the Mac's token? (before apply B)

Apply B (step 6) creates the login's schedule enabled, and from then on the login task logs in
afresh every Wednesday at 03:00. The Mac's agent still runs the weeks on the token in its keychain.
If OpenCaselist ends a token when the same account logs in again, the Mac's next run fails with
`CASELIST_AUTH_EXPIRED`. This step finds out by hand before the schedule can (PM ruling,
2026-10-24). It checks the Mac's token, logs in once as the writer into the token secret, exactly as
the scheduled login would, and checks the Mac's token again. That hand login also puts the token in
the secret that step 7's rehearsal reads. Nothing in AWS changes but the token secret. Each check
makes one request to OpenCaselist.

**The Mac's token, as the agent runs.** The plist's `PATH` and `DEBATE_ENV` and nothing of your
shell's.

**Operator command** (expected runtime ~1 min)
Where: your Mac, anywhere
```bash
PLIST="$HOME/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist"
AGENT_PATH=$(plutil -extract EnvironmentVariables.PATH raw "$PLIST")
AGENT_ENV=$(plutil -extract EnvironmentVariables.DEBATE_ENV raw "$PLIST")
env -i HOME="${HOME}" PATH="${AGENT_PATH}" DEBATE_ENV="${AGENT_ENV}" sh -c 'debate-research --json caselist auth status --check' 2>&1 | grep -oE '"status": "(ok|error)"|"backend": "[a-z]+"|"checked_now": true|"code": "[A-Z_]+"'
```
Success looks like `"status": "ok"`, `"backend": "keyring"`, `"checked_now": true`. A
`"code": "CASELIST_AUTH_EXPIRED"` here means the Mac's token had already ended, and this step can
tell nothing: log the Mac in again (the first block under "If it does not" below), run this block
again, and go on only when it prints `"status": "ok"`.

**The hand login, as the writer, into the token secret.** It prompts for the Tabroom username and
password, as `caselist auth login` always has, and stores only the token.

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
if env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; else DEBATE_ENV=dev DEBATE_CASELIST__API_ENABLED=true uv run debate-research caselist auth login --token-backend secretsmanager --aws-profile debate-dev-caselist-writer; fi
```
Success looks like: `Logged in. The caselist_token is stored in the secretsmanager backend (Secrets
Manager secret debate-dev-caselist-token) ... The password was not stored.` An `AccessDenied` means
the writer's session has expired: `aws sso login --sso-session debate`, then run it again.

**The Mac's token again**, straight after.

**Operator command** (expected runtime ~1 min)
Where: your Mac, anywhere
```bash
PLIST="$HOME/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist"
AGENT_PATH=$(plutil -extract EnvironmentVariables.PATH raw "$PLIST")
AGENT_ENV=$(plutil -extract EnvironmentVariables.DEBATE_ENV raw "$PLIST")
env -i HOME="${HOME}" PATH="${AGENT_PATH}" DEBATE_ENV="${AGENT_ENV}" sh -c 'debate-research --json caselist auth status --check' 2>&1 | grep -oE '"status": "(ok|error)"|"backend": "[a-z]+"|"checked_now": true|"code": "[A-Z_]+"'
```

**What to read.** Either way, send the PM the three blocks' output: it answers `v1-e40-t06`'s token
question for ADR-0020.

* **`"status": "ok"`**: a new login leaves the Mac's token working. Go on to step 4, and apply B
  as written.
* **`"code": "CASELIST_AUTH_EXPIRED"`**: the new login ended the Mac's token. Do the two blocks
  below, then go on to step 4.

**If it does not: log the Mac in again**, into its keychain, as the agent runs. It prompts as above.

**Operator command** (expected runtime ~1 min)
Where: your Mac, anywhere
```bash
PLIST="$HOME/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist"
AGENT_PATH=$(plutil -extract EnvironmentVariables.PATH raw "$PLIST")
AGENT_ENV=$(plutil -extract EnvironmentVariables.DEBATE_ENV raw "$PLIST")
env -i HOME="${HOME}" PATH="${AGENT_PATH}" DEBATE_ENV="${AGENT_ENV}" sh -c 'debate-research caselist auth login'
```
Success looks like `Logged in. The caselist_token is stored in the keyring backend (...)`. Then the
check block above prints `"status": "ok"` again.

**And pause the weekly login until `v1-e40-t06`**, so it cannot end the Mac's token on Wednesday.
The line goes in the gitignored `owner.auto.tfvars`, which step 6's plan reads; t06 takes it out.

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
grep -q '^caselist_login_schedule_enabled' infrastructure/envs/dev/owner.auto.tfvars || printf 'caselist_login_schedule_enabled = false\n' >> infrastructure/envs/dev/owner.auto.tfvars
grep -cE '^caselist_login_schedule_enabled += +false$' infrastructure/envs/dev/owner.auto.tfvars
```
Success looks like `1`. `0` means the file already sets the login schedule another way: make that
line `caselist_login_schedule_enabled = false` by hand. Step 6's plan then shows the login's
schedule `DISABLED`, and step 7's rehearsal waits for t06 (it says why).

## Step 4 — The deployer's SSO profile

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

## Step 5 — Build the first image and push it

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
Success looks like seven `ok:` lines (six before `v1-e40-t06` added the base image's Python), the last `ok: SQLite 3.x.y with FTS5`, then `Dry run complete.
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

## Step 6 — Apply B: the login and run tasks and their schedules

Apply B is t02's and this task's together: the login task definition and its Wednesday 03:00
schedule, and the run task definition and its Wednesday 06:00 schedule, both pinned by the digest
step 5 printed. The digest goes in the gitignored `owner.auto.tfvars`, which every later dev apply
already carries; a plan without it would destroy both tasks, and the plan check below stops that.

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
DIGEST='sha256:the-64-hex-digits-step-5-printed'
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

* `Plan: 19 to add, 0 to change, 0 to destroy.` in a fresh environment (dev's re-plan after its
  partial apply is below), no line saying `must be replaced` or `will be destroyed`, and nothing
  printed by the second `grep`.
* The third prints the login's `cron(0 3 ? * WED *)` with `ENABLED`, and the run's `cron(0 6 ? * WED
  *)` with **`DISABLED`**. A run schedule `ENABLED` here is wrong: stop. If step 3 paused the
  login, its schedule shows `DISABLED` too; `ENABLED` then is wrong: stop.
* The last prints `0`: no secret reaches either task through ECS.
* The 19: t02's 12 and the run's 7.
  * t02's 12: the login's log group; its execution role and the scheduler role, each with one
    inline policy and two exclusive-policy resources; its task definition; its schedule group,
    `debate-dev-caselist-login`; and its schedule.
  * The run's 7: its task definition, whose image ends `@` and the digest; its scheduler role, with
    one inline policy and two exclusive-policy resources; its schedule group,
    `debate-dev-caselist-run`; and its schedule.

**In dev, re-planning after apply B's partial apply of 2026-10-24.** The first apply B in dev,
with the `v1.1.0-dev.137` digest, created 15 of the 17 resources it then planned and destroyed
nothing. It stopped at both `aws_scheduler_schedule` resources with `ValidationException: The
execution role you provide must allow AWS EventBridge Scheduler to assume the role`. Each scheduler
role trusted its schedule's own ARN (`schedule/default/<name>`). EventBridge Scheduler assumes a
schedule's role with `aws:SourceArn` set to the ARN of the schedule's **group**, never the schedule's
own ARN ("Confused deputy prevention in EventBridge Scheduler",
<https://docs.aws.amazon.com/scheduler/latest/UserGuide/cross-service-confused-deputy-prevention.html>).
Now each schedule sits alone in its own group, `debate-dev-caselist-login` and
`debate-dev-caselist-run`, and each scheduler role trusts exactly its own group's ARN.

With the fix merged, the re-plan creates the two groups and the two schedules, and updates the two
scheduler roles' trust policies in place. The plan block above still applies. Its first `grep` must
print exactly `Plan: 4 to add, 2 to change, 0 to destroy.`, with no `must be replaced` or `will be
destroyed`, and its second must print nothing. Then this block checks the plan itself. It prints
`PLAN STOP` with the reason for anything but exactly that shape. The login's schedule must be
`ENABLED`, or `DISABLED` if `owner.auto.tfvars` pauses it (step 3), and the run's `DISABLED`:

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev show -json caselist-tasks.tfplan > /tmp/caselist-tasks-plan.json
python3 -I - /tmp/caselist-tasks-plan.json infrastructure/envs/dev/owner.auto.tfvars <<'PLANCHECK'
import json, re, sys
plan = json.load(open(sys.argv[1]))
paused = re.search(r"^caselist_login_schedule_enabled\s*=\s*false\s*$", open(sys.argv[2]).read(), re.M) is not None
login_state = "DISABLED" if paused else "ENABLED"
m = "module.caselist_run."
expected_creates = {
    m + "aws_scheduler_schedule_group.login[0]",
    m + "aws_scheduler_schedule_group.run[0]",
    m + "aws_scheduler_schedule.login[0]",
    m + "aws_scheduler_schedule.run[0]",
}
expected_updates = {m + "aws_iam_role.scheduler[0]": "login", m + "aws_iam_role.run_scheduler[0]": "run"}
schedules = {"login": (login_state, "cron(0 3 ? * WED *)"), "run": ("DISABLED", "cron(0 6 ? * WED *)")}
def unknown(value):
    if value is True:
        return True
    if isinstance(value, dict):
        return any(unknown(v) for v in value.values())
    if isinstance(value, list):
        return any(unknown(v) for v in value)
    return False
def trust(policy):
    try:
        statements = json.loads(policy)["Statement"]
        return statements[0] if len(statements) == 1 else None
    except (TypeError, ValueError, KeyError, IndexError):
        return None
changes = [c for c in plan.get("resource_changes", []) if c["change"]["actions"] not in (["no-op"], ["read"])]
creates = {c["address"]: c["change"] for c in changes if c["change"]["actions"] == ["create"]}
updates = {c["address"]: c["change"] for c in changes if c["change"]["actions"] == ["update"]}
others = sorted(c["address"] + " " + "/".join(c["change"]["actions"]) for c in changes if c["change"]["actions"] not in (["create"], ["update"]))
outside = sorted(c["address"] for c in changes if not c["address"].startswith(m))
problems = []
if outside:
    problems.append("changes outside module.caselist_run " + str(outside))
if set(creates) != expected_creates:
    problems.append("creates missing " + str(sorted(expected_creates - set(creates))) + ", unexpected " + str(sorted(set(creates) - expected_creates)))
else:
    for which, (state, cron) in schedules.items():
        group = creates[m + "aws_scheduler_schedule_group." + which + "[0]"]["after"] or {}
        schedule = creates[m + "aws_scheduler_schedule." + which + "[0]"]["after"] or {}
        name = "debate-dev-caselist-" + which
        if group.get("name") != name or schedule.get("group_name") != name:
            problems.append("the " + which + " schedule is in group " + str(schedule.get("group_name")) + " of " + str(group.get("name")) + ", expected " + name)
        if schedule.get("state") != state or schedule.get("schedule_expression") != cron:
            problems.append("the " + which + " schedule is " + str(schedule.get("state")) + " " + str(schedule.get("schedule_expression")) + ", expected " + state + " " + cron)
if set(updates) != set(expected_updates):
    problems.append("updates are " + str(sorted(updates)) + ", expected only the two scheduler roles")
else:
    for address, which in expected_updates.items():
        change = updates[address]
        before, after = change["before"] or {}, change["after"] or {}
        changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
        unknowns = sorted(k for k, v in (change.get("after_unknown") or {}).items() if unknown(v))
        if changed != ["assume_role_policy"] or unknowns:
            problems.append(address + " changes " + str(changed) + " with unknown " + str(unknowns) + ", expected only assume_role_policy")
            continue
        old, new = trust(before["assume_role_policy"]), trust(after["assume_role_policy"])
        account = ((old or {}).get("Condition") or {}).get("StringEquals", {}).get("aws:SourceAccount")
        wanted = {"StringEquals": {"aws:SourceAccount": account, "aws:SourceArn": "arn:aws:scheduler:us-east-1:" + str(account) + ":schedule-group/debate-dev-caselist-" + which}}
        if account is None or new is None or new.get("Principal") != {"Service": "scheduler.amazonaws.com"} or new.get("Condition") != wanted:
            problems.append(address + " trusts " + json.dumps((new or {}).get("Condition")) + ", expected " + json.dumps(wanted))
if others:
    problems.append("other actions " + str(others))
print("PLAN OK: the two schedule groups and two schedules created, the two scheduler roles' trust updated in place to their own groups, the login's schedule " + login_state + " and the run's DISABLED, nothing else" if not problems else "PLAN STOP: " + "; ".join(problems))
PLANCHECK
```
Success looks like `PLAN OK: the two schedule groups and two schedules created, the two scheduler
roles' trust updated in place to their own groups, the login's schedule ENABLED and the run's
DISABLED, nothing else` (with `DISABLED` for the login if step 3 paused it). The 4 to add are
`aws_scheduler_schedule_group.login[0]` and `.run[0]` and `aws_scheduler_schedule.login[0]` and
`.run[0]`. The 2 to change are `aws_iam_role.scheduler[0]` and `aws_iam_role.run_scheduler[0]`, each
changing only `assume_role_policy`, to `StringEquals` on `aws:SourceAccount` and on `aws:SourceArn`,
its own group's ARN. **`PLAN STOP` stops everything**: send its line and the plan to the PM, and do
not apply.


**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev apply -input=false caselist-tasks.tfplan
AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev output caselist_run_schedule_state
```
Success looks like `Apply complete! Resources: 19 added, 0 changed, 0 destroyed.` in a fresh
environment, or `Apply complete! Resources: 4 added, 2 changed, 0 destroyed.` for dev's re-plan,
then `"DISABLED"`. The first scheduled login runs the next Wednesday at 03:00 Chicago time, unless step 3
paused it; t02's runbook, step 5's last block, checks it.

**If an apply stops partway**, recover only by re-planning from the same worktree. Move it to
`origin/dev` again ([Before you start](#before-you-start)), plan with the block above, and read the
new counts with the PM before applying. Never `-target`, and never create or delete a resource by
hand. The saved plan from the same configuration is what keeps the state and the account in step.

## Step 7 — A cloud rehearsal: one dry-run pull (after apply B)

The deployer starts the run task once, with its command overridden to `--json caselist pull
--dry-run --caselist <slug>`, under the same six-hour entry point. The image, the network, the run
role and the token read from Secrets Manager all take part. A dry run lists what it would download
and downloads, writes and records nothing, so it is safe before `v1-e40-t04` (PM ruling,
2026-10-24). It lists from an empty data directory, so it wants every week: that count is expected.

It needs a working token in the token secret: step 3's hand login put one there, and after a
Wednesday the scheduled login has. **If step 3 found that a new login ends the Mac's token, wait for
`v1-e40-t06`**: logging the Mac in again there ended the secret's token in turn, and the login
schedule is paused, so the rehearsal would stop at `CASELIST_AUTH_EXPIRED`.

**The network and one of the agent's caselists.** The network is the schedule's, from the root's
outputs; the slug is the first the Mac's agent pulls.

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
SUBNETS=$(AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev output -json caselist_run_subnet_ids | tr -d '[]" \n')
SECURITY_GROUP=$(AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev output -raw caselist_run_security_group_id)
SLUG=$(plutil -extract ProgramArguments json -o - "$HOME/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist" | python3 -c 'import json, sys; a = json.load(sys.stdin); print(a[a.index("--caselist") + 1] if "--caselist" in a else "")')
echo "subnets ${SUBNETS}; security group ${SECURITY_GROUP}; caselist ${SLUG}"
```
Success looks like two `subnet-` ids joined by a comma, one `sg-` id and one caselist slug, such as
`hsld26`. No slug means the plist names none: set one the agent pulls by hand, for example
`SLUG='hsld26'`.

**Start it**, as the deployer, on the run's cluster, the newest revision of the run's family.

**Operator command** (expected runtime ~1 min to start)
Where: `$WT`, in the shell that set `SLUG`
```bash
cd "$WT"
OVERRIDES=$(printf '{"containerOverrides":[{"name":"run","command":["--json","caselist","pull","--dry-run","--caselist","%s"]}]}' "$SLUG")
if [ -z "$SLUG" ]; then echo "STOP: SLUG is not set; run the block above first"; else TASK=$(aws ecs run-task --profile debate-dev-caselist-run-deployer --region us-east-1 --cluster debate-dev-caselist-run --task-definition debate-dev-caselist-run --launch-type FARGATE --platform-version LATEST --count 1 --network-configuration "awsvpcConfiguration={subnets=[${SUBNETS}],securityGroups=[${SECURITY_GROUP}],assignPublicIp=ENABLED}" --overrides "$OVERRIDES" --query 'tasks[0].taskArn' --output text); echo "started ${TASK}"; fi
```
Success looks like `started arn:aws:ecs:us-east-1:<account>:task/debate-dev-caselist-run/<id>`.
`None` means it did not start: run it again without `--query` to see the failure.

**Watch it** every five minutes or so; a dry run lists and stops, so it should finish in minutes,
not hours.

**Operator command** (expected runtime ~1 min each time)
Where: `$WT`, in the same shell
```bash
aws ecs describe-tasks --profile debate-dev-caselist-run-deployer --region us-east-1 --cluster debate-dev-caselist-run --tasks "$TASK" --query 'tasks[0].[lastStatus,stopCode,containers[0].exitCode]' --output text
```
Success looks like `STOPPED	EssentialContainerExited	0`. `RUNNING` (or `PENDING`) means it is not
done yet. A non-zero exit code is a failed rehearsal: read its result below.

**Its result: it listed, and downloaded, wrote and published nothing.** The pull's `--json` result is
one line in the run's log.

**Operator command** (expected runtime ~1 min)
Where: `$WT`, in the same shell
```bash
aws logs tail debate-dev-caselist-run --profile debate-dev-caselist-run-deployer --region us-east-1 --since 1h | grep '"command": "caselist pull"' | grep -oE '"status": "(ok|error)"|"dry_run": true|"archives_wanted": [0-9]+|"archives_downloaded": [0-9]+|"objects_published": [0-9]+|"code": "[A-Z_]+"'
```
Success looks like `"status": "ok"`, `"dry_run": true`, `"archives_wanted": <any count>`,
`"archives_downloaded": 0` and `"objects_published": 0`. A `"code"` line is a failure.
`CASELIST_AUTH_EXPIRED` means the secret's token does not work: go back to step 3. Any other code,
or nothing printed, goes to the PM with the log's last lines (`aws logs tail` without the `grep`s).

**It recorded nothing.** The bucket's run records end where they did: no run at the rehearsal's
start time.

**Operator command** (expected runtime ~1 min)
Where: your Mac, the installed build
```bash
aws sso login --profile debate-dev-evidence
debate-research caselist runs --remote --last 3
```
Success looks like the newest runs being the Mac's, none started at the rehearsal's time.

## Step 8 — The seed, bucket mode, and one run by hand (at the cutover, after `v1-e40-t04`)

**At the cutover, run this step through [caselist-cutover.md](caselist-cutover.md)**, steps 2 to 5.
It orders these parts with the Mac's agent, installs the build with the lock first, and checks the
image apply's plan with `IMAGEPLAN`. Since `v1-e40-t05`'s alerts apply carried bucket mode into the
run's task definition early (the PM's ruling (a)), the apply below is an image change only, with the
same counts, and since `v1-e40-t06` the dev profile sets bucket mode itself. What follows is kept as
the record of what each part does.

**Not before `v1-e40-t04` has merged and been released, and not before `v1-e40-t06`'s cutover has
unloaded the Mac's agent** (ADR-0020 (4), cutover steps 3 to 5; the PM's ruling 3(b) on t04's plan).
Without bucket mode a cloud run starts from an empty data directory: it would select every week as
new, spend the day's five downloads, and publish to the dev bucket while the Mac's agent may too,
with no lock between them. In bucket mode a run restores the working copy and takes the bucket's run
lock first, and it refuses a bucket that holds no lock object (`RUN_STATE_NOT_SEEDED`). The seed
creates that object from the Mac's state. From then on the bucket keeps the run's state, and a
local-mode command on the Mac refuses the bucket (`BUCKET_KEEPS_RUN_STATE`). That is why the agent
goes first: left loaded, it would be refused every Wednesday.

The parts, in order: the agent is unloaded; the seed's plan; the seed; the run task in bucket mode,
planned (the PM reads it) and applied; one run by hand.

**The agent is unloaded, and no pull is running.** Read-only.

**Operator command** (expected runtime ~1 min)
Where: your Mac, anywhere
```bash
if launchctl print "gui/$(id -u)/com.debate-intelligence.caselist-sync" >/dev/null 2>&1; then echo "STOP: the agent is still loaded; v1-e40-t06 unloads it first"; elif pgrep -f "caselist pull" >/dev/null; then echo "STOP: a caselist pull is running"; else echo "agent unloaded, no pull running"; fi
```
Success looks like `agent unloaded, no pull running`.

**The seed's plan.** With the installed build, a release that has `v1-e40-t04`, in bucket mode for
this command alone. It writes nothing anywhere: it lists the lock's key and heads each of the Mac's
manifests in the bucket.

**Operator command** (expected runtime ~1 min)
Where: your Mac, the installed build
```bash
aws sso login --profile debate-dev-evidence
if env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; else DEBATE_ENV=dev DEBATE_CASELIST__RUN_STATE=bucket debate-research --json caselist seed-run-state | grep -oE '"(applied|seeded_already)": (true|false)|"manifests": [0-9]+|"code": "[A-Z_]+"'; fi
```

**What to read, and what stops you.**

* Go on only with `"applied": false`, `"seeded_already": false` and `"manifests":` **above zero**
  (50 on 2026-10-24). Zero manifests is an empty data directory, not a Mac ready to seed: stop.
* `"code": "SEED_REFUSED"` stops you. Run the block again without the `grep` to read the reason.
  "already holds a run lock" means the bucket is seeded: stop and tell the PM. "not in the bucket
  with the same SHA-256" means the Mac imported something it has not published: run `caselist pull
  --publish-pending` in local mode (the bucket is not seeded yet, so local mode still publishes),
  then this block again. A manifest the publisher withholds names the removal to run again.

**The seed.** It creates the lock object with `If-None-Match: *`, so of two seeds only one gets past
its first write, uploads the run-state bundle and the five state files, checks each back against
its SHA-256, and releases the lock.

**Operator command** (expected runtime ~1 min)
Where: your Mac, the installed build
```bash
if env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; elif pgrep -f "caselist pull" >/dev/null; then echo "STOP: a caselist pull is running"; else DEBATE_ENV=dev DEBATE_CASELIST__RUN_STATE=bucket debate-research --json caselist seed-run-state --execute | grep -oE '"applied": (true|false)|"manifests": [0-9]+|"checked_back": \[[^]]*\]|"code": "[A-Z_]+"'; fi
```
Success looks like `"applied": true`, the same `"manifests":` count as the plan, above zero, and
`"checked_back":` naming six keys: `manifests/_run-state/run-state.tar.gz` and the five under
`reports/sync/state/`. Anything else: stop and send the PM the output. The seed releases the lock
whatever happened after it created it.

From here on, every command on the Mac that writes to the dev bucket runs in bucket mode
(`DEBATE_CASELIST__RUN_STATE=bucket`, which `v1-e40-t06` puts in the profile), and restores the
working copy first.

**The run task in bucket mode.** Two changes reach the run's task definition in one apply: an image
built from a release that has `v1-e40-t04`, and `DEBATE_CASELIST__RUN_STATE=bucket` in its
environment, from this module (the PM's ruling 1 on t04's plan). Build and push the image as
[A new image, later](#a-new-image-later) says, and put the digest line it prints in place of the
old one in `owner.auto.tfvars`. Then the plan.

**Operator command** (expected runtime ~2 min)
Where: `$WT`, a worktree of `dev` with `v1-e40-t04` merged
```bash
cd "$WT"
if env | grep -qE '^(TF_VAR_|TF_WORKSPACE=|TF_DATA_DIR=|TF_CLI_ARGS)'; then echo "STOP: a Terraform override is set in this shell"; else AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev plan -input=false -no-color -out=caselist-bucket-mode.tfplan | tee /tmp/caselist-bucket-mode-plan.txt | tail -5; fi
grep -E '^Plan:|must be replaced|will be destroyed' /tmp/caselist-bucket-mode-plan.txt
grep -c 'DEBATE_CASELIST__RUN_STATE' /tmp/caselist-bucket-mode-plan.txt
grep -E '^  # ' /tmp/caselist-bucket-mode-plan.txt | grep -v 'module.caselist_run' | head
grep -E '^ +[~+] state ' /tmp/caselist-bucket-mode-plan.txt
```

**What to read, and what stops you.** Send the plan to the PM; apply only after the PM's word.

* `Plan: 2 to add, 4 to change, 2 to destroy.`, as for any new image: the login and run task
  definitions each replaced (the two `must be replaced` lines), and the two schedules and their
  scheduler roles' policies repointed at the new revisions. The run schedule's revision is the one
  ruling 1 expects to see repointed.
* The second `grep` prints `1` or more: the run's new revision carries bucket mode. `0`: stop,
  unless the alerts' apply ([caselist-run-alerts.md](caselist-run-alerts.md), step 2) already
  carried bucket mode into the run's task definition, which its plan check reported as a `NOTE for
  the PM` and the PM let go on. Then the revision here changes its image alone and `0` is expected.
* Nothing printed by the third, and no schedule's `state` turning `ENABLED` in the fourth: the run's
  schedule stays `DISABLED` until `v1-e40-t06` enables it.

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev apply -input=false caselist-bucket-mode.tfplan
AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev output caselist_run_schedule_state
```
Success looks like `Apply complete! Resources: 2 added, 4 changed, 2 destroyed.`, then `"DISABLED"`.

**One run by hand.**

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

**It ran in bucket mode, and left the lock free.** Its details in the bucket say what it restored
and whether it saved the run-state bundle. Put the cloud run's id in `RUN_ID`.

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
RUN_ID='the-cloud-runs-id-caselist-runs-printed'
BUCKET=$(AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev output -raw evidence_bucket_name)
aws s3 cp "s3://${BUCKET}/reports/sync-run-details/2026/${RUN_ID}.json" - --profile debate-dev-evidence | grep -oE '"bundle": "saved[^"]*"|"took_over": (null|"[^"]*")|"parsed_objects": [0-9]+|"lock_lost": (true|false)'
aws s3 cp "s3://${BUCKET}/reports/sync/run-lock.json" - --profile debate-dev-evidence | grep -oE '"state": "[a-z]+"|"home_environment": "[a-z]+"'
```
Success looks like `"bundle": "saved, ...`, `"took_over": null`, `"parsed_objects":` above zero (the
parsed store's current version directory, about 15,000 objects at today's size), `"lock_lost":
false`, then `"state": "free"` and `"home_environment": "dev"`. The restore's start and end are in
the same file, under `bucket_run.restore`: they are the cloud figure the PM asked for in place of an
estimate (t04's plan, question 7).

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

**Replacing the digest line.** Step 6's append block stops on a line that is already there, so a new
image's line replaces the old one with this block, after the push has written
`/tmp/caselist-run-deploy.txt`. It changes that one line and nothing else, and stops when the file
holds no digest line or more than one. Then the plan below, read by the PM before the apply.

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
"sha256:<new>"`, then `1`. (Added by the PM, 2026-10-26, from `v1-e40-t13`'s review.)

**The plan, after the cutover.** Step 6's plan and the cutover runbook's image-plan check were
written for the first image apply, while the run's schedule was still `DISABLED`; since the cutover
(2026-10-26) the schedule is `ENABLED` and stays so (`v1-e31-t31`'s review). This block saves the
plan, writes it as JSON with `terraform show -json`, and checks that JSON with
`ops/caselist_run/check_image_plan.py` (`v1-e40-t15`). The check reads the plan's resource changes,
never its text: `terraform plan` prints a "Refreshing state..." line for every resource in state, so
on 2026-10-29 a count of Identity Center lines read 40 on a plan that changed none of them. The block
first removes the last plan and its JSON, so a plan that fails leaves nothing behind for the check
or the apply to read. The plan's text stays in `/tmp/caselist-new-image-plan.txt` for the PM.

**Operator command** (expected runtime ~2 min)
Where: `$WT`, in the shell that replaced the digest line
```bash
cd "$WT"
rm -f infrastructure/envs/dev/caselist-new-image.tfplan /tmp/caselist-new-image-plan.json
if env | grep -qE '^(TF_VAR_|TF_WORKSPACE=|TF_DATA_DIR=|TF_CLI_ARGS)'; then echo "STOP: a Terraform override is set in this shell"; else AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev init -input=false >/dev/null && AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev plan -input=false -no-color -out=caselist-new-image.tfplan | tee /tmp/caselist-new-image-plan.txt | tail -3; fi
AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev show -json caselist-new-image.tfplan > /tmp/caselist-new-image-plan.json
python3 -I ops/caselist_run/check_image_plan.py /tmp/caselist-new-image-plan.json infrastructure/envs/dev/owner.auto.tfvars
```

**What to read, and what stops you.** The last line is the check's. Send the PM it and the plan's
`Plan:` line above it; apply only after the PM's word.

* `PLAN OK: 2 to add, 4 to change, 2 to destroy; the login and run task definitions replaced with
  the image sha256:<new>... and nothing else in them changed; the two schedules and their roles'
  policies repointed at the new revisions; both schedules ENABLED throughout; nothing else changes`,
  with the image the digest line's: the only shape that passes. Each task definition's image
  changed to `owner.auto.tfvars`'s digest and nothing else in it; each schedule's target and each
  scheduler role's policy pointed at the new revision and nothing else in them; neither schedule's
  `state` changing.
* `PLAN STOP: ...` names each change that is not that shape, with its address and actions: an
  Identity Center change (`aws_ssoadmin_*`, `aws_identitystore_*`) anywhere, a change outside
  `module.caselist_run`, a schedule's `state`, a task definition updated rather than replaced, an
  expected change missing, or any other change in the module, such as 2026-10-29's update to
  `module.caselist_run.aws_cloudwatch_event_target.task_stopped["run"]`. A `PLAN STOP` goes to the PM
  before any apply, with the plan's text for each address it names. An Identity Center change is
  never applied.
* `PLAN STOP: the plan file is not JSON ...` or `... has no resource_changes ...` means the plan or
  its `show` failed: read the lines above it, fix that and run the block again.

If the PM allows a plan the check stopped, the apply's counts are that plan's, not the ones below.

**Operator command** (expected runtime ~1 min)
Where: `$WT`, after the PM's word, on any day but Wednesday
```bash
cd "$WT"
if [ "$(date +%A)" = "Wednesday" ]; then echo "STOP: it is Wednesday, the run's day; apply on another day"; else AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev apply -input=false caselist-new-image.tfplan; fi
AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev output caselist_run_schedule_state
```
Success looks like `Apply complete! Resources: 2 added, 4 changed, 2 destroyed.`, then `"ENABLED"`.
One `-login-task-changed` email is expected. (Added by the PM, 2026-10-27, from `v1-e31-t31`'s
review; the PM reads every plan before its apply.)

## A failed parse stage

In bucket mode the weekly run names `caselist parse --caselist <slug> --publish` for a caselist whose
parsed store it did not publish complete (`v1-e34-t31`). Never run it on the operator's Mac: there it
rebuilds the Mac's own, older working copy and publishes that over the parsed store the cloud run
owns. Until the run names a cloud cure itself (`v1-e40-t18`), the cure is the next weekly run, which
re-parses that caselist and publishes it; if that cannot wait, ask the PM for a run started by hand.
(Added by the PM, 2026-10-30, from `v1-e34-t31`'s review.)

## The deadline, and stopping a run

The run's command is `timeout --signal=TERM --kill-after=120s 6h debate-research --json caselist
pull`: at six hours the CLI gets SIGTERM, as `docker stop` would send, and SIGKILL two minutes later,
and the task stops with a non-zero exit (ADR-0020 (1) 6). To stop a run sooner, as the deployer:

```bash
aws ecs stop-task --profile debate-dev-caselist-run-deployer --region us-east-1 --cluster debate-dev-caselist-run --task "$TASK" --reason "stopped by the operator" --query 'task.desiredStatus' --output text
```
Success looks like `STOPPED`. ECS sends SIGTERM and gives the same two minutes.

## Backfile imports

The four backfile complete archives (`hspolicy25`, `hsld25`, `hspolicy24`, `hsld24`) are imported
once each by a one-off task of **the run's own task definition**, started by hand with its command
overridden to `v1-e34-t34`'s `caselist backfile-import --caselist <slug>`, and never on a schedule
(the PM's rulings of 2026-10-27 on
[`v1-e40-t09`](../../plan_specs/v1/e40-cloud-caselist-run/t09-cloud-backfile-import.yaml)). The import's
rules, its refusals and its rebuild after a removal are [caselist-backfiles.md](caselist-backfiles.md)'s;
this section is how the cloud runs it.

* **The task.** The run's task definition, the revision Terraform made and the schedule starts: 8
  vCPU, 16 GB, the run role, and the run's 6-hour deadline (an import is estimated at 1.5 to 2.5
  hours). Its 100 GiB of ephemeral storage holds the largest import, `hsld25`, which needs
  32,750,091,060 bytes free by t34's estimate with 25% headroom, beside the image and the restore.
  The module's tests hold that figure.
* **What Terraform changes.** One thing: the run-stopped alert's email now says the task may be a
  backfile import started by hand. No task definition, schedule, role, policy or permission set
  changes, and no grant is added: every call the import makes is one the run role already holds.
* **Who it runs as.** `ops/caselist_run/start_backfile_import.py` reads the bucket's run lock as the
  everyday evidence profile (`debate-dev-evidence`, one `GetObject`) and starts the task as the run
  deployer (`debate-dev-caselist-run-deployer`). **Both must be signed in.** The plan, the apply and
  the root's outputs are `debate-admin`'s, as everywhere in this runbook.
* **What refuses.** The script refuses inside the no-import window, Tuesday 06:00 to Thursday 00:00
  America/Chicago, and while a run holds the bucket's lock; nothing is started. In the task, the
  import refuses again before any download: the window, the backfile budget (one complete archive in
  any 24 hours, in the bucket's ledger), free space, and a token that is expired or missing.
* **A failed or refused import emails the coach**, as a failed weekly run does: the task stops with a
  non-zero exit and the run-stopped rule matches every task of the run's family. The email says it
  may be a backfile import. A refused dry run sends one too.
* **An import never counts as a weekly run.** The late-run alarm counts only `caselist pull` results
  that carry a run record, and an import's result is `caselist backfile-import` with none, so a
  finished import cannot hide a Wednesday with no run.

**When.** This task's pull request merges into `dev` only after Thursday 2026-10-29's image apply, so
that its plan is not part of that one. The dry run waits until Wednesday 2026-10-28's first scheduled
cloud run has succeeded. The four imports wait until the operator is back, after 2026-11-01.

### The plan, which the PM reads before the apply

**The worktree**, `$WT` from "Before you start", moved to `origin/dev` with this task merged.

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
git fetch origin
git switch --detach origin/dev
test -f ops/caselist_run/start_backfile_import.py && echo "ok: origin/dev $(git rev-parse --short HEAD), the backfile import merged" || echo "NOT MERGED: wait for v1-e40-t09 to merge"
grep -cE '^caselist_image_digest += "sha256:[0-9a-f]{64}"$' infrastructure/envs/dev/owner.auto.tfvars
```
Success looks like `ok: origin/dev <commit>, the backfile import merged`, then `1`: the digest line
Thursday's image apply left.

**The plan**, saved to a file, so that what the apply applies is what was read.

**Operator command** (expected runtime ~2 min)
Where: `$WT`
```bash
cd "$WT"
if env | grep -qE '^(TF_VAR_|TF_WORKSPACE=|TF_DATA_DIR=|TF_CLI_ARGS)'; then echo "STOP: a Terraform override is set in this shell"; else AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev init -input=false >/dev/null && AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev plan -input=false -no-color -out=caselist-backfile-alert.tfplan | tee /tmp/caselist-backfile-alert-plan.txt | tail -5; fi
grep -E '^Plan:|must be replaced|will be destroyed|will be created' /tmp/caselist-backfile-alert-plan.txt
grep -c 'aws_ssoadmin' /tmp/caselist-backfile-alert-plan.txt
grep -E '^ +~ +input_template' /tmp/caselist-backfile-alert-plan.txt
```
Expect `Plan: 0 to add, 1 to change, 0 to destroy.`, no line saying a resource is replaced, destroyed
or created, then `0`, then the one `input_template` line: the run-stopped email's text, before and
after. **The PM reads that line.** The new text is the old with one sentence added after `Task
<task>.`: `It is the weekly run, or a backfile import someone started by hand
(docs/runbooks/caselist-cloud-run.md, Backfile imports): the command on the last line of its log says
which.` **An account assignment, a permission set, a schedule or a task definition anywhere in the
plan stops everything**: never apply it.

**The plan checked against exactly that shape.** It prints `PLAN OK` only for one in-place update of
`module.caselist_run.aws_cloudwatch_event_target.task_stopped["run"]` whose text gains that sentence and
changes in nothing else, with nothing else in the plan. Anything else prints `PLAN STOP` with the
reason.

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev show -json caselist-backfile-alert.tfplan > /tmp/caselist-backfile-alert-plan.json
python3 -I - /tmp/caselist-backfile-alert-plan.json <<'BACKFILEPLAN'
import json, sys
plan = json.load(open(sys.argv[1]))
m = "module.caselist_run."
target = m + 'aws_cloudwatch_event_target.task_stopped["run"]'
added = " It is the weekly run, or a backfile import someone started by hand (docs/runbooks/caselist-cloud-run.md, Backfile imports): the command on the last line of its log says which."
changes = [c for c in plan.get("resource_changes", []) if c["change"]["actions"] not in (["no-op"], ["read"])]
problems = []
def unknown(value):
    if value is True:
        return True
    if isinstance(value, dict):
        return any(unknown(v) for v in value.values())
    if isinstance(value, list):
        return any(unknown(v) for v in value)
    return False
sso = sorted(c["address"] for c in changes if "aws_ssoadmin" in c["address"])
if sso:
    problems.append("an account assignment or permission set changes: " + str(sso))
schedules = sorted(c["address"] + " " + "/".join(c["change"]["actions"]) for c in changes if "aws_scheduler_schedule" in c["address"])
if schedules:
    problems.append("a schedule is added or changed: " + str(schedules))
outside = sorted(c["address"] for c in changes if not c["address"].startswith(m))
if outside:
    problems.append("changes outside module.caselist_run " + str(outside))
others = sorted(c["address"] + " " + "/".join(c["change"]["actions"]) for c in changes if c["address"] != target)
if others:
    problems.append("changes other than the run-stopped alert's text: " + str(others))
found = [c["change"] for c in changes if c["address"] == target]
if not found:
    problems.append("the run-stopped alert's text does not change: is v1-e40-t09 merged in this checkout?")
for change in found:
    if change["actions"] != ["update"]:
        problems.append(target + " is " + "/".join(change["actions"]) + ", expected an update in place")
    before, after = change["before"] or {}, change["after"] or {}
    unknowns = {k for k, v in (change.get("after_unknown") or {}).items() if unknown(v)}
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k) or k in unknowns)
    if changed != ["input_transformer"]:
        problems.append(target + " changes " + str(changed) + ", expected only input_transformer")
        continue
    old, new = (before.get("input_transformer") or [{}])[0], (after.get("input_transformer") or [{}])[0]
    if old.get("input_paths") != new.get("input_paths"):
        problems.append(target + " changes its input paths")
    text_before, text_after = str(old.get("input_template", "")), str(new.get("input_template", ""))
    if added not in text_after:
        problems.append("the new text does not name a hand-started backfile import as v1-e40-t09 wrote it")
    elif text_after.replace(added, "", 1) != text_before:
        problems.append("the text changes beyond the sentence naming a backfile import")
if problems:
    print("PLAN STOP: " + "; ".join(problems))
else:
    print("PLAN OK: 0 to add, 1 to change, 0 to destroy; the run-stopped alert's text names a hand-started backfile import and nothing else in it changed; no schedule, task definition, role, policy or permission set changes; nothing else")
BACKFILEPLAN
```
Success looks like `PLAN OK: 0 to add, 1 to change, 0 to destroy; the run-stopped alert's text names a
hand-started backfile import …; nothing else`. **`PLAN STOP` stops everything**: send its line and the
plan to the PM. Either way the PM reads the plan before the apply.

### The apply, after the PM's word

**Operator command** (expected runtime ~1 min)
Where: `$WT`, after the PM's word, on any day but Wednesday
```bash
cd "$WT"
if env | grep -qE '^(TF_VAR_|TF_WORKSPACE=|TF_DATA_DIR=|TF_CLI_ARGS)'; then echo "STOP: a Terraform override is set in this shell"; elif [ "$(date +%A)" = "Wednesday" ]; then echo "STOP: it is Wednesday, the run's day; apply on another day"; else AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev apply -input=false caselist-backfile-alert.tfplan; fi
```
Success looks like `Apply complete! Resources: 0 added, 1 changed, 0 destroyed.` A stale plan: plan
again. Never `-target`.

### Before each start: both profiles, the network and the revision

**Sign in.** One SSO session covers the deployer and the everyday profile; each is checked by name.

**Operator command** (expected runtime ~1 min)
Where: your Mac, anywhere
```bash
aws sso login --sso-session debate
aws sts get-caller-identity --profile debate-dev-caselist-run-deployer --query Arn --output text
aws sts get-caller-identity --profile debate-dev-evidence --query Arn --output text
```
Success looks like one ARN containing `AWSReservedSSO_DebateDevCaselistRunDeployer` and one containing
`AWSReservedSSO_DebateDevEvidenceOperator`. An error on either: that profile is not configured or not
signed in, and the script would refuse.

**The network and the revision the schedule starts**, from the root's outputs. The deployer cannot
read the schedule, so the runbook passes the script Terraform's own revision; without
`--task-definition`, the script starts the family's newest ACTIVE revision, which the deploy script
may have replaced with a later image.

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
SUBNETS=$(AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev output -json caselist_run_subnet_ids | tr -d '[]" \n')
SECURITY_GROUP=$(AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev output -raw caselist_run_security_group_id)
REVISION=$(AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev output -raw caselist_run_task_definition_arn)
DIGEST=$(grep -oE 'sha256:[0-9a-f]{64}' infrastructure/envs/dev/owner.auto.tfvars)
echo "subnets ${SUBNETS}; security group ${SECURITY_GROUP}; revision ${REVISION}; image ${DIGEST}"
```
Success looks like two `subnet-` ids joined by a comma, one `sg-` id, a
`…:task-definition/debate-dev-caselist-run:<n>` ARN, and one `sha256:` digest.

### The dry run (`v1-e40-t09` ac2)

Listings and a `HEAD` in the task, as the run role, with the run's token: nothing is downloaded,
written or locked, and no budget is spent. It also measures the free space on the task's volume.
Not inside the window, and not before Wednesday 2026-10-28's scheduled run has succeeded.

**Start it.** The caselist is the first to import.

**Operator command** (expected runtime ~1 min to start)
Where: `$WT`, in the shell that set `REVISION`
```bash
cd "$WT"
CASELIST=hspolicy25
rm -f "/tmp/backfile-${CASELIST}-dry-run.txt"
if env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; elif [ -z "$REVISION" ] || [ -z "$SUBNETS" ]; then echo "STOP: REVISION or SUBNETS is not set; run the block above first"; else python3 -I ops/caselist_run/start_backfile_import.py --env dev --caselist "$CASELIST" --subnets "$SUBNETS" --security-group "$SECURITY_GROUP" --task-definition "$REVISION" --dry-run | tee "/tmp/backfile-${CASELIST}-dry-run.txt"; fi
TASK_ID=$(sed -n 's/^task id: //p' "/tmp/backfile-${CASELIST}-dry-run.txt" 2>/dev/null)
echo "task ${TASK_ID}"
```
Success looks like `outside the no-import window`, `run lock: free`, `task definition: <REVISION>
(revision <n>)`, `image digest: <DIGEST>`, `ephemeral storage: 100 GiB`, `started arn:aws:ecs:…`, and
`task <32 hex digits>`. **Before the first import, the revision and the digest printed must be
`REVISION` and `DIGEST` above**: if either differs, stop and tell the PM. A `REFUSED:` line started
nothing; it says why. Inside the window: start it after Thursday 00:00. The lock held: a run is
working, so start it once that run's task has stopped.

**Watch it** until it stops; a dry run takes a few minutes.

**Operator command** (expected runtime ~1 min each time)
Where: `$WT`, in the same shell
```bash
aws ecs describe-tasks --profile debate-dev-caselist-run-deployer --region us-east-1 --cluster debate-dev-caselist-run --tasks "$TASK_ID" --query 'tasks[0].[lastStatus,stopCode,containers[0].exitCode]' --output text
```
Success looks like `STOPPED	EssentialContainerExited	0`. `RUNNING` or `PENDING`: not done yet. Exit
`1` is a refusal: read its result below.

**Its result**, the import's `--json` line in the task's log.

**Operator command** (expected runtime ~1 min)
Where: `$WT`, in the same shell
```bash
aws logs tail debate-dev-caselist-run --profile debate-dev-caselist-run-deployer --region us-east-1 --log-stream-names "run/run/${TASK_ID}" --since 6h | grep '"command": "caselist backfile-import"' | grep -oE '"status": "(ok|error)"|"applied": (true|false)|"archive_bytes": [0-9]+|"already_imported": (true|false)|"backfile_downloads_left": [0-9]+|"inside_no_import_window": (true|false)|"required_bytes": [0-9]+|"free_bytes": [0-9]+|"enough": (true|false)|"code": "[A-Z_]+"'
```
Success (ac2) looks like `"status": "ok"`, `"applied": false`, `"archive_bytes": 3958272657` for
`hspolicy25`, `"already_imported": false`, `"backfile_downloads_left": 1`,
`"inside_no_import_window": false`, `"required_bytes": 29687044928`, a `"free_bytes"` above it,
`"enough": true`, and **no `"code"` line**. Record the free bytes in the report: they are the task
volume's measured room. Nothing printed at all: the task did not reach the import; send the log's
last lines (`aws logs tail` without the `grep`s) to the PM.

**A `"code"` line names why it stopped**:

* `CASELIST_AUTH_EXPIRED`, `CASELIST_TOKEN_MISSING` or `CASELIST_TOKEN_UNREADABLE`: the token the run's
  login stored has expired, or there is none. **The Wednesday 03:00 login renews it. Nobody logs in by
  hand for an import**, which would be a second login: start the import again after Thursday 00:00.
  The task's own message still says to run `caselist auth login`; that wording is the Mac's, and a
  later image changes it.
* `INSIDE_NO_IMPORT_WINDOW`, `BACKFILE_BUDGET_SPENT`, `NOT_ENOUGH_FREE_SPACE`,
  `RUN_STATE_NOT_SEEDED`, `NOT_A_BACKFILE`, `NO_COMPLETE_ARCHIVE`: as
  [caselist-backfiles.md, "What each refusal means"](caselist-backfiles.md#what-each-refusal-means) says.
* `RUN_LOCK_HELD` or another lock code: a run took the lock after the script read it. Start again once
  that run's task has stopped.
* Anything else goes to the PM with the log's last lines.

### The four imports (`v1-e40-t09` ac3)

In the order of [caselist-backfiles.md](caselist-backfiles.md#the-order), **at most one a day**,
outside the window and **never on a Wednesday**, each its dry run first:

| Order | Caselist | Earliest | Its dry run's `archive_bytes` | `required_bytes` |
|---|---|---|---|---|
| 1 | `hspolicy25` | the operator's return, after 2026-11-01 | 3958272657 | 29687044928 |
| 2 | `hsld25` | the Thursday after the first import's weekly run is checked (below) | 4366678808 | 32750091060 |
| 3 | `hspolicy24` | a day after the second | 2563267685 | 19224507638 |
| 4 | `hsld24` | a day after the third | 3967721058 | 29757907935 |

**For each:** "Before each start" above (the sign-in, and the block that sets `REVISION`), then the
dry run with `CASELIST` set to this caselist, read as above. Its `archive_bytes` and `required_bytes`
are the table's, `"backfile_downloads_left": 1`, and no `"code"` line. **Only then the import**, in a
block of its own.

**Operator command** (expected runtime ~1 min to start; the import takes 1.5 to 2.5 hours)
Where: `$WT`, in the shell that ran this caselist's dry run
```bash
cd "$WT"
rm -f "/tmp/backfile-${CASELIST}-import.txt"
if env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; elif [ -z "$REVISION" ] || [ -z "$CASELIST" ]; then echo "STOP: REVISION or CASELIST is not set; run the dry run first"; else python3 -I ops/caselist_run/start_backfile_import.py --env dev --caselist "$CASELIST" --subnets "$SUBNETS" --security-group "$SECURITY_GROUP" --task-definition "$REVISION" | tee "/tmp/backfile-${CASELIST}-import.txt"; fi
TASK_ID=$(sed -n 's/^task id: //p' "/tmp/backfile-${CASELIST}-import.txt" 2>/dev/null)
echo "task ${TASK_ID}"
```
Success looks like the dry run's lines and `task <32 hex digits>`.

**Watch it** every half hour with the dry run's `describe-tasks` block, until `STOPPED
EssentialContainerExited 0`.

**Its counts.**

**Operator command** (expected runtime ~1 min)
Where: `$WT`, in the same shell
```bash
aws logs tail debate-dev-caselist-run --profile debate-dev-caselist-run-deployer --region us-east-1 --log-stream-names "run/run/${TASK_ID}" --since 6h | grep '"command": "caselist backfile-import"' | grep -oE '"status": "(ok|error)"|"applied": (true|false)|"downloaded_bytes": [0-9]+|"members": [0-9]+|"stored": [0-9]+|"suppressed": [0-9]+|"held_by_request": [{][^}]*[}]|"sources_uploaded": [0-9]+|"sources_skipped": [0-9]+|"parsed": [0-9]+|"unsupported": [0-9]+|"failed": [0-9]+|"cards": [0-9]+|"parsed_uploaded": [0-9]+|"archive_left_inbox": (true|false)|"(restore|download|import|parse|publish|publish_parsed)": [0-9.]+|"code": "[A-Z_]+"'
```
Success looks like `"status": "ok"`, `"applied": true`, `"downloaded_bytes"` equal to the dry run's
`archive_bytes`, and `"members"`, `"sources_uploaded"`, `"parsed"`, `"cards"` and `"parsed_uploaded"`
each **above zero**, `"archive_left_inbox": true`, the six step times in seconds, any `"held_by_request"` counts, and no `"code"` line.
A zero there is not a success, even with `"status": "ok"`: send the lines to the PM.
`BACKFILE_IMPORT_INCOMPLETE` or `BUNDLE_CHANGED_SINCE_RESTORE`: start it again the next day; it
resumes from what was published and does not download again. A window that opened part-way
(`INSIDE_NO_IMPORT_WINDOW`): start it again after Thursday 00:00.

**Record the counts** in
[docs/data/caselist-backfile-seasons.md, "Cloud imports"](../data/caselist-backfile-seasons.md#cloud-imports-v1-e40-t09):
paste the lines above, with the date and the revision, into a session, which commits the row. Counts
only: no school, team or file name is in them.

**The next weekly run after the first import.** The first import's manifest goes into the run-state
bundle that every weekly run restores. On the Thursday after that import's Wednesday, check that run
restored, finished, and took about as long as the weeks before it. The second import waits for this.

**Operator command** (expected runtime ~1 min)
Where: your Mac, the installed build
```bash
debate-research --json caselist runs --remote --last 4 > /tmp/caselist-runs.json
python3 -I - /tmp/caselist-runs.json <<'RUNS'
import json, sys
from datetime import datetime
for run in json.load(open(sys.argv[1]))["data"]["runs"]:
    started = datetime.fromisoformat(run["started_at"].replace("Z", "+00:00"))
    finished = datetime.fromisoformat(run["finished_at"].replace("Z", "+00:00"))
    print(run["run_id"], run["outcome"], "%.0f min" % ((finished - started).total_seconds() / 60))
RUNS
```
Success looks like four lines, newest first, the newest Wednesday's run with the outcome the weeks
before had and a time within about a quarter of theirs. A failed run, or one much slower, goes to the
PM before the second import, with its log's last lines.

**A rebuild after a whole-file removal** is this same import, dry run first, for each backfile the
removal's plan listed ([caselist-removal.md](caselist-removal.md), step 5): imported already, it
downloads nothing and spends no budget, so `"already_imported": true` and `"downloaded_bytes": 0` are
its success. The window still applies.

## Prod, at the pilot's promotion (follow-up)

The same steps against `infrastructure/envs/prod`, from a checkout of `main`, with `prod` for `dev`
in every name (`debate-prod-caselist-run`, `DebateProdCaselistRunDeployer`, the profile
`debate-prod-caselist-run-deployer`), and a stable release: the deploy script refuses a dev
pre-release for prod. ADR-0020 (7) moves the run's home at the same time; `v1-e40-t06`'s runbook
orders the two.

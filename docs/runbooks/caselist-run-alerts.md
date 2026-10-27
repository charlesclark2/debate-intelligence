<!-- docs-index: The cloud run's alerts: applying the alert topic, rules and alarms in dev, confirming the coach's email subscription, one test alert, turning the late-run alarm on at the cutover, and what to do when each alert arrives -->
# Runbook: the cloud run's alerts

How a failed or late cloud run, a failed login, a schedule that could not start its task, and any
change to who may read the Tabroom password reach the coach by email. Spec:
[`v1-e40-t05-run-alerts`](../../plan_specs/v1/e40-cloud-caselist-run/t05-run-alerts.yaml).
Decision: [ADR-0020](../adr/0020-weekly-caselist-run-in-the-cloud.md) (6) and (2). The module:
[`infrastructure/modules/caselist_run`](../../infrastructure/modules/caselist_run/README.md),
`alerts.tf`. The run itself is [caselist-cloud-run.md](caselist-cloud-run.md)'s; the credentials and
the login are [caselist-cloud-credentials.md](caselist-cloud-credentials.md)'s.

Written for the adult maintainer with administrator access to the account. **Every step here is run
by a human.** An agent session never plans, applies or calls AWS.

## What this sets up

All in the environment's own names, `debate-dev-...` in dev and `debate-prod-...` at the promotion.

| What goes wrong | What notices | What the email says |
|---|---|---|
| A run fails | The run itself: `caselist.notifier = sns` sends what the Mac's banners say, including `RUN_TERMINATED` and `RUN_LOCK_LOST` | Subject `debate dev: caselist pull failed: ...`; the run id, the environment, the failed stage and its codes, the fix |
| A run or a login stops non-zero, or never starts | The rules `debate-dev-caselist-run-stopped` and `-login-stopped` on ECS task state changes | `The dev weekly caselist run task stopped with exit code N (stop code: reason). Task <arn>.` For the run's family it adds that the task may be a backfile import started by hand (`v1-e40-t09`), whose result names its command |
| The weekly login fails | The login itself, through the same notifier | Subject `debate dev: Weekly caselist login failed`; its code and the two fixes, never the account |
| No run recorded in seven days | The alarm `debate-dev-caselist-run-late` on `RunsRecorded` from the run's log group. **Its email is off until the cutover's first recorded run** | An `ALARM` email naming the alarm |
| A schedule could not start its task | The queues `debate-dev-caselist-login-dlq` and `-run-dlq`, and the alarm `debate-dev-caselist-schedule-failed` | An `ALARM` email naming the alarm and the two queues |
| Someone changes who may read the password, or reads it | The rules `-credentials-key-changed`, `-credentials-secret-policy-changed`, `-login-role-changed`, `-login-task-changed`, and `-password-read` on CloudTrail events | The event, the principal, the time, and the error code if it was refused |

Everything goes to one SNS topic, `debate-dev-caselist-run-alerts`, whose one subscription is the
address the pilot's budget alarm writes to (`evidence_search_budget_emails` in `owner.auto.tfvars`,
else `owner`). No email names a school, a team code, a file or a card.

**Expect an email from your own applies.** Once the subscription is confirmed, an apply that
replaces the login task definition (every new image does) is a `RegisterTaskDefinition` naming the
login role, and `-login-task-changed` emails it. That is the rule working.

## The order

1. [Before you start](#before-you-start): the worktree, at `origin/dev` with this task merged.
2. [Step 1](#step-1--an-image-that-knows-the-sns-notifier): an image from a release that has this
   task, pushed, and its digest in `owner.auto.tfvars`. **Not optional**: an image without this
   task's code refuses `caselist.notifier = sns`, so the Wednesday login would fail at startup.
3. [Step 2](#step-2--the-plan-which-the-pm-reads), the plan, which the PM reads; then
   [step 3](#step-3--the-apply), the apply.
4. [Step 4](#step-4--the-coach-confirms-the-subscription): the coach confirms the subscription.
5. [Step 5](#step-5--each-rules-pattern-against-awss-own-matcher): each rule's pattern against AWS's
   own matcher.
6. [Step 6](#step-6--one-test-alert): one test alert.
7. [At the cutover](#at-the-cutover-the-late-run-alarm-emails): the late-run alarm's email, after
   the first recorded cloud run (`v1-e40-t06`).

## Before you start

**The worktree the earlier applies used**, `caselist-credentials-dev`, moved to `origin/dev`, and
the check that this task is merged in it. Its gitignored `owner.auto.tfvars` is the one every dev
apply used.

```bash
WT="$HOME/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/caselist-credentials-dev"

cd "$WT" || { echo "WT does not exist: $WT"; }
git fetch origin
git switch --detach origin/dev
test -f infrastructure/modules/caselist_run/alerts.tf && test -f packages/debate_core/src/debate_core/integrations/sns/__init__.py \
  && echo "ok: $(pwd) at origin/dev $(git rev-parse --short HEAD), the alerts merged" \
  || echo "NOT MERGED: origin/dev has no infrastructure/modules/caselist_run/alerts.tf; wait for v1-e40-t05 to merge"
git status --porcelain | grep -v 'owner.auto.tfvars' | head -3
```
Success looks like: `ok: <the worktree> at origin/dev <commit>, the alerts merged`, and nothing
after it.

**Sign in as break-glass**, which every apply here runs as, and check `owner.auto.tfvars` names
everyone it already did, and an image.

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
aws sso login --sso-session debate
aws sts get-caller-identity --profile debate-admin --query Arn --output text
grep -c -E '^(owner|site_publisher_user_names|evidence_operator_user_names|evidence_removal_user_names|evidence_search_deployer_user_names|evidence_search_accounts_user_names|caselist_credential_writer_user_names|caselist_run_deployer_user_names) ' infrastructure/envs/dev/owner.auto.tfvars
grep -cE '^caselist_image_digest += "sha256:[0-9a-f]{64}"$' infrastructure/envs/dev/owner.auto.tfvars
grep -E '^evidence_search_budget_emails|^owner ' infrastructure/envs/dev/owner.auto.tfvars
```
Success looks like an ARN containing `AWSReservedSSO_DebateBreakGlassAdmin`, then `8`, then `1`,
then the line or lines naming the address. The first address in `evidence_search_budget_emails`, or
`owner` if that line is absent, is where the alerts go: if it is not the coach's, stop and correct it
before planning. Fewer than `8`: a line is missing, and a plan without it would remove someone's
account assignment; find it in the checkout that last applied dev. `0` digests: apply B has not
happened ([caselist-cloud-run.md](caselist-cloud-run.md), step 6), so do that first.

## Step 1 — An image that knows the sns notifier

The task definitions are replaced in this apply whatever happens, so they move to an image built
from a release that has this task. Use the newest dev pre-release containing `v1-e40-t05`'s merge
whose validate-dev run, image job included, is green. Set `TAG` in this shell; the next blocks read
it and stop if it is empty.

```bash
cd "$WT"
gh release list --repo charlesclark2/debate-intelligence --limit 3 --json tagName,createdAt --jq '.[] | .tagName + " " + .createdAt'
TAG="$(gh release list --repo charlesclark2/debate-intelligence --limit 1 --json tagName --jq '.[0].tagName')"
git fetch origin tag "$TAG" --no-tags
git cat-file -e "${TAG}:packages/debate_core/src/debate_core/integrations/sns/__init__.py" && echo "TAG=$TAG has the sns notifier" || echo "STOP: $TAG has no sns notifier; use a release after v1-e40-t05's merge"
```

**The dry run**, which builds and checks the image offline and pushes nothing (Docker Desktop must be
running):

**Operator command** (expected runtime ~1 min)
Where: `$WT`, in the shell that set `TAG`
```bash
cd "$WT"
if [ -z "$TAG" ]; then echo "STOP: TAG is not set; run the listing block first"; elif env | grep -qE '^(CASELIST_RUN_DEPLOY_PROFILE|DEBATE_RELEASE_REPO)='; then echo "STOP: a deploy override is set in this shell"; else time scripts/caselist_run_deploy.sh dev "$TAG" --dry-run; fi
```
Success looks like seven `ok:` lines and `Dry run complete. debate-dev-caselist-run:<tag> built and
checked`.

**The push.** As the deployer: it pushes the image, registers a run task definition with it for a
run by hand, and prints the digest line.

**Operator command** (expected runtime ~3 min)
Where: `$WT`, in the same shell
```bash
cd "$WT"
if [ -z "$TAG" ]; then echo "STOP: TAG is not set; run the listing block first"; elif env | grep -qE '^(CASELIST_RUN_DEPLOY_PROFILE|DEBATE_RELEASE_REPO)='; then echo "STOP: a deploy override is set in this shell"; else scripts/caselist_run_deploy.sh dev "$TAG" 2>&1 | tee /tmp/caselist-run-deploy.txt | tail -8; fi
grep -E '^pushed: |^registered: |caselist_image_digest = ' /tmp/caselist-run-deploy.txt
```
Success looks like `pushed: ...@sha256:<64 hex digits>`, `registered: arn:aws:ecs:...:task-definition/debate-dev-caselist-run:<n>`
and `caselist_image_digest = "sha256:<the same digits>"`.

**The digest, in place of the old one.** Paste the digits the push printed into `DIGEST`. The old
file is kept beside `/tmp` for the comparison.

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
DIGEST='sha256:the-64-hex-digits-the-push-printed'
if ! printf '%s' "$DIGEST" | grep -qE '^sha256:[0-9a-f]{64}$'; then echo "STOP: DIGEST is not sha256: and 64 hex digits"; else cp infrastructure/envs/dev/owner.auto.tfvars /tmp/owner.auto.tfvars.before-alerts && sed -i '' -E "s/^caselist_image_digest[[:space:]]*=.*$/caselist_image_digest = \"${DIGEST}\"/" infrastructure/envs/dev/owner.auto.tfvars && grep -c "^caselist_image_digest = \"${DIGEST}\"$" infrastructure/envs/dev/owner.auto.tfvars && diff /tmp/owner.auto.tfvars.before-alerts infrastructure/envs/dev/owner.auto.tfvars | grep -c '^[<>]'; fi
```
Success looks like `1`, then `2`: the digest line is the new one, and it is the only line that
changed.

## Step 2 — The plan, which the PM reads

Saved to a file, so what step 3 applies is exactly what was read here.

**Operator command** (expected runtime ~2 min)
Where: `$WT`
```bash
cd "$WT"
if env | grep -qE '^(TF_VAR_|TF_WORKSPACE=|TF_DATA_DIR=|TF_CLI_ARGS)'; then echo "STOP: a Terraform override is set in this shell"; else AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev init -input=false >/dev/null && AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev plan -input=false -no-color -out=caselist-alerts.tfplan | tee /tmp/caselist-alerts-plan.txt | tail -5; fi
grep -E '^Plan:|must be replaced|will be destroyed' /tmp/caselist-alerts-plan.txt
grep -E '^  # ' /tmp/caselist-alerts-plan.txt | grep -v 'module.caselist_run' | head
grep -c 'aws_ssoadmin' /tmp/caselist-alerts-plan.txt
```

**What to read, and what stops you.** Send the whole plan (`/tmp/caselist-alerts-plan.txt`) to the PM
and apply only after the PM's word.

* The first `grep` prints exactly `Plan: 25 to add, 5 to change, 2 to destroy.`, and the two lines
  `module.caselist_run.aws_ecs_task_definition.login[0] must be replaced` and `...run[0] must be
  replaced`, and **nothing else saying `must be replaced` or `will be destroyed`**.
* The second prints nothing: every change is under `module.caselist_run`.
* The third prints `0`. **An account assignment or a permission set anywhere in the plan stops
  everything**: never apply it; `owner.auto.tfvars` is missing a line.
* The 25 to add: the 23 new resources (the topic, its policy and the subscription; the two
  task-state rules and their targets; the metric filter and the late-run alarm; the two queues and
  their alarm; the four write rules and the password rule with their five targets; the run role's
  `caselist-alerts` policy), and the two replacement task definitions.
* The 5 to change: the run role's exclusive policy list (gains `caselist-alerts`), the two scheduler
  roles' policies (each gains `sqs:SendMessage` on its own queue, and points at its new revision), and
  the two schedules (each gains its dead-letter queue and points at its new revision).
* The 2 to destroy: the two old task definition revisions, replaced.

**Then the plan checked against exactly that shape.** It prints `PLAN STOP` with the reason for
anything else.

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev show -json caselist-alerts.tfplan > /tmp/caselist-alerts-plan.json
python3 -I - /tmp/caselist-alerts-plan.json infrastructure/envs/dev/owner.auto.tfvars <<'PLANCHECK'
import json, re, sys
plan = json.load(open(sys.argv[1]))
owner = open(sys.argv[2]).read()
digest = re.search(r'^caselist_image_digest\s*=\s*"(sha256:[0-9a-f]{64})"\s*$', owner, re.M)
paused = re.search(r"^caselist_login_schedule_enabled\s*=\s*false\s*$", owner, re.M) is not None
m = "module.caselist_run."
writes = ["credentials-key-changed", "credentials-secret-policy-changed", "login-role-changed", "login-task-changed"]
expected_creates = {m + a for a in [
    "aws_sns_topic.alerts", "aws_sns_topic_policy.alerts", "aws_sns_topic_subscription.coach",
    'aws_cloudwatch_event_rule.task_stopped["run"]', 'aws_cloudwatch_event_rule.task_stopped["login"]',
    'aws_cloudwatch_event_target.task_stopped["run"]', 'aws_cloudwatch_event_target.task_stopped["login"]',
    "aws_cloudwatch_log_metric_filter.runs_recorded", "aws_cloudwatch_metric_alarm.late_run",
    'aws_sqs_queue.schedule_dead_letters["login"]', 'aws_sqs_queue.schedule_dead_letters["run"]',
    "aws_cloudwatch_metric_alarm.schedule_failed",
    "aws_cloudwatch_event_rule.password_read", "aws_cloudwatch_event_target.password_read",
    "aws_iam_role_policy.run_alerts",
] + ['aws_cloudwatch_event_rule.credential_write["%s"]' % w for w in writes] + ['aws_cloudwatch_event_target.credential_write["%s"]' % w for w in writes]}
expected_replaced = {m + "aws_ecs_task_definition.login[0]", m + "aws_ecs_task_definition.run[0]"}
expected_updates = {m + a for a in ["aws_iam_role_policies_exclusive.run", "aws_iam_role_policy.scheduler[0]", "aws_iam_role_policy.run_scheduler[0]", "aws_scheduler_schedule.login[0]", "aws_scheduler_schedule.run[0]"]}
changes = [c for c in plan.get("resource_changes", []) if c["change"]["actions"] not in (["no-op"], ["read"])]
creates = {c["address"]: c["change"] for c in changes if c["change"]["actions"] == ["create"]}
replaced = {c["address"]: c["change"] for c in changes if sorted(c["change"]["actions"]) == ["create", "delete"]}
updates = {c["address"]: c["change"] for c in changes if c["change"]["actions"] == ["update"]}
others = sorted(c["address"] + " " + "/".join(c["change"]["actions"]) for c in changes if c["address"] not in creates and c["address"] not in replaced and c["address"] not in updates)
problems, notes = [], []
if digest is None:
    problems.append("owner.auto.tfvars names no image digest")
if any("aws_ssoadmin" in c["address"] for c in changes):
    problems.append("an account assignment or permission set changes: " + str(sorted(c["address"] for c in changes if "aws_ssoadmin" in c["address"])))
outside = sorted(c["address"] for c in changes if not c["address"].startswith(m))
if outside:
    problems.append("changes outside module.caselist_run " + str(outside))
if set(creates) != expected_creates:
    problems.append("creates missing " + str(sorted(expected_creates - set(creates))) + ", unexpected " + str(sorted(set(creates) - expected_creates)))
if set(replaced) != expected_replaced:
    problems.append("replacements are " + str(sorted(replaced)) + ", expected only the two task definitions")
if set(updates) != expected_updates:
    problems.append("updates missing " + str(sorted(expected_updates - set(updates))) + ", unexpected " + str(sorted(set(updates) - expected_updates)))
if others:
    problems.append("other actions " + str(others))
def environment(change, side):
    try:
        definition = json.loads((change[side] or {})["container_definitions"])[0]
        return definition, {v["name"]: v["value"] for v in definition.get("environment", [])}
    except (TypeError, ValueError, KeyError, IndexError):
        return None, None
topic = None
for address in sorted(expected_replaced & set(replaced)):
    which = "run" if address.endswith("run[0]") else "login"
    change = replaced[address]
    before, old = environment(change, "before")
    after, new = environment(change, "after")
    if after is None or before is None:
        problems.append(address + ": its container definitions cannot be read from the plan")
        continue
    added = {k: new[k] for k in set(new) - set(old)}
    removed = sorted(set(old) - set(new))
    altered = sorted(k for k in set(old) & set(new) if old[k] != new[k])
    topic = added.get("DEBATE_CASELIST__ALERT_TOPIC_ARN", topic)
    allowed = {"DEBATE_CASELIST__NOTIFIER", "DEBATE_CASELIST__ALERT_TOPIC_ARN"} | ({"DEBATE_CASELIST__RUN_STATE"} if which == "run" else set())
    if added.get("DEBATE_CASELIST__NOTIFIER") != "sns" or not re.fullmatch(r"arn:aws:sns:us-east-1:[0-9]{12}:debate-dev-caselist-run-alerts", added.get("DEBATE_CASELIST__ALERT_TOPIC_ARN", "")):
        problems.append(address + " does not gain the sns notifier and the dev topic: " + json.dumps(added))
    if set(added) - allowed or removed or altered:
        problems.append(address + " environment adds " + str(sorted(set(added) - allowed)) + ", removes " + str(removed) + ", changes " + str(altered))
    if which == "run" and "DEBATE_CASELIST__RUN_STATE" in added:
        notes.append("the run's revision also gains DEBATE_CASELIST__RUN_STATE=" + str(added["DEBATE_CASELIST__RUN_STATE"]) + " (v1-e40-t04's bucket mode, not applied before)")
    if digest is not None and not str(after.get("image", "")).endswith("@" + digest.group(1)):
        problems.append(address + " image is " + str(after.get("image")) + ", expected the digest in owner.auto.tfvars")
    other_keys = sorted(k for k in ("name", "essential", "entryPoint", "command", "linuxParameters", "stopTimeout", "logConfiguration", "secrets") if before.get(k) != after.get(k))
    if other_keys:
        problems.append(address + " also changes " + str(other_keys))
    if (change["before"] or {}).get("task_role_arn") != (change["after"] or {}).get("task_role_arn"):
        problems.append(address + " changes its task role")
schedules = {"login": "DISABLED" if paused else "ENABLED", "run": "DISABLED"}
for which, state in schedules.items():
    change = updates.get(m + "aws_scheduler_schedule." + which + "[0]")
    if change is not None and ((change["after"] or {}).get("state") != state or (change["before"] or {}).get("schedule_expression") != (change["after"] or {}).get("schedule_expression")):
        problems.append("the " + which + " schedule becomes " + str((change["after"] or {}).get("state")) + " or changes its time; expected " + state + ", the same time")
states = {a: (creates[a]["after"] or {}).get("state") for a in creates if ".aws_cloudwatch_event_rule." in a}
for address, state in sorted(states.items()):
    wanted = "ENABLED_WITH_ALL_CLOUDTRAIL_MANAGEMENT_EVENTS" if address.endswith("password_read") else "ENABLED"
    if state != wanted:
        problems.append(address + " state " + str(state) + ", expected " + wanted)
late = (creates.get(m + "aws_cloudwatch_metric_alarm.late_run") or {}).get("after") or {}
if late.get("actions_enabled") is not False:
    problems.append("the late-run alarm's actions are not off")
subscription = (creates.get(m + "aws_sns_topic_subscription.coach") or {}).get("after") or {}
if subscription.get("protocol") != "email":
    problems.append("the subscription is not by email")
counts = (len(creates) + len(replaced), len(updates), len(replaced))
if problems:
    print("PLAN STOP: " + "; ".join(problems))
else:
    print("PLAN OK: %d to add, %d to change, %d to destroy; the two task definitions replaced with the new image, the sns notifier and %s; the run's schedule DISABLED and the login's %s; the late-run alarm's email off; the alerts to %s" % (counts + (topic, schedules["login"], subscription.get("endpoint"))))
    for note in notes:
        print("NOTE for the PM: " + note)
PLANCHECK
```
Success looks like `PLAN OK: 25 to add, 5 to change, 2 to destroy; ...`, naming the dev topic and
the coach's address. **`PLAN STOP` stops everything**: send its line and the plan to the PM, and do
not apply. A `NOTE for the PM` line means this apply also carries `v1-e40-t04`'s bucket mode into the
run's task definition, which [caselist-cloud-run.md](caselist-cloud-run.md) step 8 otherwise applies
after the seed. The run's schedule stays disabled, and a bucket-mode run refuses a bucket that has
not been seeded (`RUN_STATE_NOT_SEEDED`), but the PM decides whether to go on: send the note with
the plan.

## Step 3 — The apply

Only after the PM's word on step 2's plan.

**Operator command** (expected runtime ~2 min)
Where: `$WT`
```bash
cd "$WT"
if env | grep -qE '^(TF_VAR_|TF_WORKSPACE=|TF_DATA_DIR=|TF_CLI_ARGS)'; then echo "STOP: a Terraform override is set in this shell"; else AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev apply -input=false caselist-alerts.tfplan; fi
AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev output -raw caselist_alert_topic_arn; echo
AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev output caselist_run_schedule_state
AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev output caselist_run_late_alarm_actions_enabled
```
Success looks like `Apply complete! Resources: 25 added, 5 changed, 2 destroyed.`, then
`arn:aws:sns:us-east-1:<account>:debate-dev-caselist-run-alerts`, `"DISABLED"` and `false`. A stale
plan (`Saved plan is stale`) means something changed in between: go back to step 2. **If an apply
stops partway**, recover only by planning again from the same worktree and reading the new counts
with the PM; never `-target`, and never create or delete a resource by hand.

## Step 4 — The coach confirms the subscription

AWS emails the address an `AWS Notification - Subscription Confirmation` message within a few
minutes of the apply. The coach opens it and follows **Confirm subscription**, once. Until then
nothing published to the topic reaches anyone. If it is not in the inbox, look in spam; the sender is
`no-reply@sns.amazonaws.com`.

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
TOPIC=$(AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev output -raw caselist_alert_topic_arn)
aws sns list-subscriptions-by-topic --profile debate-admin --region us-east-1 --topic-arn "$TOPIC" --query 'Subscriptions[].[Protocol,SubscriptionArn]' --output text
```
Success looks like one line, `email` and an ARN ending `:debate-dev-caselist-run-alerts:<id>`.
`PendingConfirmation` in place of the ARN means the link has not been followed yet. Every alert
email carries an unsubscribe link: following it stops every alert, and only a new apply (or a
subscribe by hand) brings them back.

## Step 5 — Each rule's pattern against AWS's own matcher

The module's tests read every pattern back, but only AWS says whether EventBridge matches an event
with it. This asks AWS's matcher (`test-event-pattern`, which reads and changes nothing) for each rule,
with an event that must match and one that must not.

**Operator command** (expected runtime ~1 min)
Where: your Mac, anywhere
```bash
python3 -I - <<'PATTERNS'
import json, subprocess
def aws(*args):
    return subprocess.run(["aws", *args, "--profile", "debate-admin", "--region", "us-east-1", "--output", "text"], capture_output=True, text=True, check=True).stdout.strip()
account = aws("sts", "get-caller-identity", "--query", "Account")
prefix = "debate-dev-caselist-"
def event(source, detail_type, detail):
    return json.dumps({"id": "1", "version": "0", "detail-type": detail_type, "source": source, "account": account, "time": "2026-11-04T11:05:00Z", "region": "us-east-1", "resources": [], "detail": detail})
def stopped(family, exit_code, stop_code="EssentialContainerExited"):
    container = {} if exit_code is None else {"exitCode": exit_code}
    return event("aws.ecs", "ECS Task State Change", {"clusterArn": "arn:aws:ecs:us-east-1:%s:cluster/%srun" % (account, prefix), "lastStatus": "STOPPED", "taskDefinitionArn": "arn:aws:ecs:us-east-1:%s:task-definition/%s%s:9" % (account, prefix, family), "stopCode": stop_code, "containers": [container]})
def call(source, name, who, parameters, error=None):
    detail = {"eventSource": source.replace("aws.", "") + ".amazonaws.com", "eventName": name, "userIdentity": {"arn": who}, "requestParameters": parameters}
    if error:
        detail["errorCode"] = error
    return event(source, "AWS API Call via CloudTrail", detail)
login_session = "arn:aws:sts::%s:assumed-role/%slogin/0123456789abcdef" % (account, prefix)
admin_session = "arn:aws:sts::%s:assumed-role/AWSReservedSSO_DebateBreakGlassAdmin_0000/coach" % account
scheduler_session = "arn:aws:sts::%s:assumed-role/%sscheduler/0123456789abcdef" % (account, prefix)
cases = [
    ("run-stopped", stopped("run", 2), True), ("run-stopped", stopped("run", None, "TaskFailedToStart"), True),
    ("run-stopped", stopped("run", 0), False), ("run-stopped", stopped("login", 1), False),
    ("login-stopped", stopped("login", 1), True), ("login-stopped", stopped("run", 1), False),
    ("password-read", call("aws.secretsmanager", "GetSecretValue", admin_session, {"secretId": prefix + "tabroom-password"}), True),
    ("password-read", call("aws.secretsmanager", "GetSecretValue", admin_session, {"secretId": prefix + "tabroom-password"}, "AccessDenied"), True),
    ("password-read", call("aws.secretsmanager", "GetSecretValue", login_session, {"secretId": prefix + "tabroom-password"}), False),
    ("password-read", call("aws.secretsmanager", "GetSecretValue", admin_session, {"secretId": prefix + "token"}), False),
    ("credentials-secret-policy-changed", call("aws.secretsmanager", "PutResourcePolicy", admin_session, {"secretId": prefix + "tabroom-password"}), True),
    ("login-role-changed", call("aws.iam", "PutRolePolicy", admin_session, {"roleName": prefix + "login"}), True),
    ("login-role-changed", call("aws.iam", "PutRolePolicy", admin_session, {"roleName": prefix + "run"}), False),
    ("login-task-changed", call("aws.ecs", "RunTask", admin_session, {"taskDefinition": prefix + "login"}), True),
    ("login-task-changed", call("aws.ecs", "RunTask", scheduler_session, {"taskDefinition": "arn:aws:ecs:us-east-1:%s:task-definition/%slogin:7" % (account, prefix)}), False),
]
failures = 0
for rule, sample, expected in cases:
    pattern = aws("events", "describe-rule", "--name", prefix + rule, "--query", "EventPattern")
    result = aws("events", "test-event-pattern", "--event-pattern", pattern, "--event", sample, "--query", "Result") == "True"
    failures += result is not expected
    print(("ok  " if result is expected else "FAIL") + " " + rule + ": " + ("matched" if result else "did not match") + ", expected " + ("a match" if expected else "no match"))
print("PATTERNS OK: %d of %d" % (len(cases), len(cases)) if failures == 0 else "PATTERNS STOP: %d of %d wrong" % (failures, len(cases)))
PATTERNS
```
Success looks like fifteen `ok` lines and `PATTERNS OK: 15 of 15`. Any `FAIL` goes to the PM with the
output: that rule would miss, or wrongly send, the alert it names.

## Step 6 — One test alert

The deployer starts the run task once with a command the CLI does not have. It stops at once with
exit code 2, before it reads a setting, the token or the bucket, and `debate-dev-caselist-run-stopped`
emails the coach. It writes nothing and records no run.

**The network**, from the root's outputs.

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
SUBNETS=$(AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev output -json caselist_run_subnet_ids | tr -d '[]" \n')
SECURITY_GROUP=$(AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev output -raw caselist_run_security_group_id)
echo "subnets ${SUBNETS}; security group ${SECURITY_GROUP}"
```
Success looks like two `subnet-` ids joined by a comma, and one `sg-` id.

**Start it**, as the deployer, the newest revision of the run's family: the one step 3 made.

**Operator command** (expected runtime ~1 min to start)
Where: `$WT`, in the same shell
```bash
cd "$WT"
if [ -z "$SUBNETS" ] || [ -z "$SECURITY_GROUP" ]; then echo "STOP: run the block above first"; else TASK=$(aws ecs run-task --profile debate-dev-caselist-run-deployer --region us-east-1 --cluster debate-dev-caselist-run --task-definition debate-dev-caselist-run --launch-type FARGATE --platform-version LATEST --count 1 --network-configuration "awsvpcConfiguration={subnets=[${SUBNETS}],securityGroups=[${SECURITY_GROUP}],assignPublicIp=ENABLED}" --overrides '{"containerOverrides":[{"name":"run","command":["--json","caselist","alert-test-no-such-command"]}]}' --query 'tasks[0].taskArn' --output text); echo "started ${TASK}"; fi
```
Success looks like `started arn:aws:ecs:us-east-1:<account>:task/debate-dev-caselist-run/<id>`.

**Watch it stop**, a minute or two later.

**Operator command** (expected runtime ~1 min)
Where: `$WT`, in the same shell
```bash
aws ecs describe-tasks --profile debate-dev-caselist-run-deployer --region us-east-1 --cluster debate-dev-caselist-run --tasks "$TASK" --query 'tasks[0].[lastStatus,stopCode,containers[0].exitCode]' --output text
```
Success looks like `STOPPED	EssentialContainerExited	2`. `PENDING` or `RUNNING`: wait a minute and
run it again.

**The email.** Within a few minutes the coach's inbox has `AWS Notification Message` from
`no-reply@sns.amazonaws.com`, beginning `The dev weekly caselist run task stopped with exit code 2
(EssentialContainerExited: Essential container in task exited). Task arn:aws:ecs:...`. Record the
time it arrived beside the task's stop time for the PM: that is ac1's operator evidence. No email
after ten minutes, with step 4's subscription confirmed and step 5's patterns `OK`: send the PM step
5's output and this block's.

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
aws cloudwatch get-metric-statistics --profile debate-admin --region us-east-1 --namespace AWS/Events --metric-name Invocations --dimensions Name=RuleName,Value=debate-dev-caselist-run-stopped --start-time "$(date -u -v-1H +%Y-%m-%dT%H:%M:%SZ)" --end-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" --period 3600 --statistics Sum --query 'Datapoints[].Sum' --output text
```
Success looks like `1.0` (or more): the rule matched and handed the event to the topic. Nothing
printed means the rule did not match, which step 5 should already have shown.

## At the cutover: the late-run alarm emails

The late-run alarm's data are missing until a run records itself, and missing data breach, so it has
been in `ALARM`, silently, since step 3. ADR-0020 (4) 6: after the cutover's first recorded cloud run
(`v1-e40-t06`), its email is turned on. Check the run recorded itself first: the alarm must have
left `ALARM`.

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
aws cloudwatch describe-alarms --profile debate-admin --region us-east-1 --alarm-names debate-dev-caselist-run-late --query 'MetricAlarms[0].[StateValue,ActionsEnabled]' --output text
grep -c '^caselist_run_late_alarm_actions_enabled' infrastructure/envs/dev/owner.auto.tfvars
```
Success looks like `OK	False`, then `0`. `ALARM	False` means no run has recorded itself yet: the
metric filter has not counted the first run, so stop and send the PM the run's id and the last
lines of its log. A `1` on the second line means the switch is already in the file: read it.

**The plan.** The switch goes in the gitignored `owner.auto.tfvars`, like the image digest.

**Operator command** (expected runtime ~2 min)
Where: `$WT`
```bash
cd "$WT"
grep -q '^caselist_run_late_alarm_actions_enabled' infrastructure/envs/dev/owner.auto.tfvars || printf 'caselist_run_late_alarm_actions_enabled = true\n' >> infrastructure/envs/dev/owner.auto.tfvars
if env | grep -qE '^(TF_VAR_|TF_WORKSPACE=|TF_DATA_DIR=|TF_CLI_ARGS)'; then echo "STOP: a Terraform override is set in this shell"; else AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev plan -input=false -no-color -out=caselist-late-alarm.tfplan | tee /tmp/caselist-late-alarm-plan.txt | tail -3; fi
grep -E '^Plan:|^  # ' /tmp/caselist-late-alarm-plan.txt
grep -E '^ +~ actions_enabled' /tmp/caselist-late-alarm-plan.txt
```
**What to read, and what stops you.** Exactly `Plan: 0 to add, 1 to change, 0 to destroy.`, the one
resource `module.caselist_run.aws_cloudwatch_metric_alarm.late_run will be updated in-place`, and
`~ actions_enabled = false -> true`. Anything else: stop and send the plan to the PM. If the cutover
also enables the run's schedule in the same apply, its plan is the cutover runbook's, not this one.

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev apply -input=false caselist-late-alarm.tfplan
AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev output caselist_run_late_alarm_actions_enabled
```
Success looks like `Apply complete! Resources: 0 added, 1 changed, 0 destroyed.` and `true`.

## When an alert arrives

| The email | What to do |
|---|---|
| `caselist pull failed: will be retried` | Nothing: the next Wednesday's run retries it. If the next one says the same, read the run's log |
| `caselist pull failed: needs a person`, `...retried once fixed`, or a stopped run task | `debate-research caselist runs --remote --last 3` on the Mac, and the run's log (`aws logs tail debate-dev-caselist-run --since 1d`, as the deployer) |
| `RUN_TERMINATED` | The run hit its six-hour deadline or was stopped by hand: it saved what it may and released the lock; the next run carries on |
| `caselist pull lost the bucket's run lock` (`RUN_LOCK_LOST`) | Another runner took the lock over. Find which with `caselist runs --remote`; two runners in one week is what [caselist-cloud-run.md](caselist-cloud-run.md) and the cutover runbook exist to prevent |
| `Weekly caselist login failed` | Its fix line: `caselist auth set-password` if the password changed, or a hand login ([caselist-cloud-credentials.md](caselist-cloud-credentials.md)) |
| `ALARM: "debate-dev-caselist-run-late"` | No run recorded in seven days: was the schedule enabled, did the run start (`aws ecs list-tasks`), and did its log end with a summary? The Mac is the fallback for a week ([caselist-cloud-run.md](caselist-cloud-run.md)) |
| `ALARM: "debate-dev-caselist-schedule-failed"` | Read the message in the queue, below: it names the schedule and why its start failed. Then empty the queue, or the alarm stays in `ALARM` and the next failure sends no email |
| A credentials rule (`...key...`, `...secret...`, `...login role...`, `...login task...`, `...Tabroom password...`) | If it was your own apply or a new image (the login task definition is replaced each time), nothing. Otherwise treat it as an incident: who is the principal, and was it refused? |

**Reading a dead letter.** Read-only: it shows the message and leaves it in the queue.

**Operator command** (expected runtime ~1 min)
Where: your Mac, anywhere
```bash
for QUEUE in debate-dev-caselist-login-dlq debate-dev-caselist-run-dlq; do URL=$(aws sqs get-queue-url --profile debate-admin --region us-east-1 --queue-name "$QUEUE" --query QueueUrl --output text); echo "== $QUEUE"; aws sqs receive-message --profile debate-admin --region us-east-1 --queue-url "$URL" --max-number-of-messages 10 --visibility-timeout 0 --message-attribute-names All --query 'Messages[].[MessageAttributes,Body]' --output json; done
```
The message's attributes name the schedule's ARN and the error (`ERROR_CODE`, `ERROR_MESSAGE`).
Fix what it names first.

**Emptying the queue that held it**, after the fix. Name the queue the block above showed a message
in; this deletes every message in it.

**Operator command** (expected runtime ~1 min)
Where: your Mac, anywhere
```bash
QUEUE='debate-dev-caselist-run-dlq'
URL=$(aws sqs get-queue-url --profile debate-admin --region us-east-1 --queue-name "$QUEUE" --query QueueUrl --output text) && aws sqs purge-queue --profile debate-admin --region us-east-1 --queue-url "$URL" && echo "emptied $QUEUE"
```
Success looks like `emptied debate-dev-caselist-run-dlq`. The alarm returns to `OK` within about ten
minutes.

## Prod, at the pilot's promotion (follow-up)

The same steps against `infrastructure/envs/prod`, from a checkout of `main`, with `prod` for `dev`
in every name, at the move of the run's home (ADR-0020 (7), the cutover runbook). The late-run
alarm's email is turned on in prod after prod's first recorded run, and off in dev with dev's
schedule.

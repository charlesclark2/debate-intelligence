<!-- docs-index: The weekly cloud run's credentials: applying the key, the two secrets, the roles and the writer, writing the Tabroom password, the scheduled login, and logging in by hand -->
# Runbook: the caselist run's credentials and the scheduled login

How the weekly caselist run's credentials are set up in AWS: the key, the Tabroom password and
caselist token secrets, the login and run roles and the coach's writer permission set (apply A);
the coach writing the password once; and the login task with its Wednesday schedule (apply B). Spec:
[`v1-e40-t02-secrets-token-store-and-login`](../../plan_specs/v1/e40-cloud-caselist-run/t02-secrets-token-store-and-login.yaml).
Decision: [ADR-0020](../adr/0020-weekly-caselist-run-in-the-cloud.md) (2). Policy: the
[data-use policy](../policies/caselist-data-use.md)'s E34 gate, items 3 and 8 (version 1.12). The
module: [`infrastructure/modules/caselist_run`](../../infrastructure/modules/caselist_run/README.md).

Written for the adult maintainer with administrator access to the account, and the coach, who are
the same person today. **Every step here is run by a human.** CI has no AWS credentials, and an
agent session never applies or calls AWS.

**Nobody ever reads the password back.** Not to check it, not to debug a login. A wrong or changed
password is written again with `set-password`. Every command below that touches a secret prints its
name or a count, never its value, even if a permission is wrong and the read is allowed.

## What this sets up

| | dev | prod |
|---|---|---|
| Password secret | `debate-dev-caselist-tabroom-password` | `debate-prod-caselist-tabroom-password` |
| Token secret | `debate-dev-caselist-token` | `debate-prod-caselist-token` |
| Key | `alias/debate-dev-caselist-credentials` | `alias/debate-prod-caselist-credentials` |
| Login role, the only reader of the password | `debate-dev-caselist-login` | `debate-prod-caselist-login` |
| Run role, the only reader of the token | `debate-dev-caselist-run` | `debate-prod-caselist-run` |
| The coach's writer: writes both, reads neither | `DebateDevCaselistSecretWriter` | `DebateProdCaselistSecretWriter` |
| Its SSO profile | `debate-dev-caselist-writer` | `debate-prod-caselist-writer` |
| Login schedule (apply B) | `debate-dev-caselist-login`, Wednesdays 03:00 America/Chicago | the same, in prod, at the promotion |

ADR-0020 calls the writer `Debate<Env>CaselistCredentialWriter`; Identity Center allows a permission
set 32 characters, and that name has 33 in dev, so it is `Debate<Env>CaselistSecretWriter`.

**The order.** Apply A in dev, then the coach writes the password, now. Apply B in dev waits for
`v1-e40-t03`'s first image push, because the login task runs the run's image on the run's network.
Prod follows at the pilot's promotion (ADR-0020 (7)), by the same steps against `envs/prod`.

## Before you start

**Shell variables**, used by every block below. `WT` is the checkout holding this Terraform: the
task worktree while the task is in flight, the main clone once it has merged.

```bash
WT=/path/to/your/checkout
SSO_USER_NAME='your-identity-center-user-name'

cd "$WT" || { echo "WT does not exist: $WT"; }
test -f infrastructure/envs/dev/caselist_run.tf \
  && echo "ok: $(pwd) on branch $(git branch --show-current)" \
  || echo "WRONG CHECKOUT: $(pwd) has no infrastructure/envs/dev/caselist_run.tf"
```
Success looks like: `ok: <the checkout> on branch task/v1-e40-t02-secrets-token-store-and-login`
(or `dev` or `main` once merged). Anything else, fix `WT` before going on.

**Sign in and confirm the identity the applies run as.** Creating a permission set and the key
policy needs break-glass, and the key policy lets only `DebateBreakGlassAdmin` administer the key,
so every apply here runs as `debate-admin`.

**Operator command** (expected runtime ~1 min)
Where: your Mac, anywhere
```bash
aws sso login --sso-session debate
aws sts get-caller-identity --profile debate-admin --query Arn --output text
```
Success looks like: an ARN containing `AWSReservedSSO_DebateBreakGlassAdmin`.

**The root's `owner.auto.tfvars` must hold every person it already names, and now the writer.** The
file is gitignored, so a fresh worktree has none, and a plan made without it would remove the
website's, the evidence store's and the pilot's account assignments. Copy it from the checkout that
last applied dev (`PREVIOUS_DEV_WT`), add the writer's line, and count.

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
PREVIOUS_DEV_WT=/path/to/the/checkout/that/last/applied/dev
test -f infrastructure/envs/dev/owner.auto.tfvars || cp "${PREVIOUS_DEV_WT}/infrastructure/envs/dev/owner.auto.tfvars" infrastructure/envs/dev/
grep -q '^caselist_credential_writer_user_names' infrastructure/envs/dev/owner.auto.tfvars \
  || printf 'caselist_credential_writer_user_names = ["%s"]\n' "$SSO_USER_NAME" >> infrastructure/envs/dev/owner.auto.tfvars
terraform fmt infrastructure/envs/dev
grep -c -E '^(owner|site_publisher_user_names|evidence_operator_user_names|evidence_removal_user_names|evidence_search_deployer_user_names|evidence_search_accounts_user_names|caselist_credential_writer_user_names) ' infrastructure/envs/dev/owner.auto.tfvars
grep -h '^owner' infrastructure/envs/dev/owner.auto.tfvars
AWS_PROFILE=debate-admin aws s3api get-bucket-tagging --bucket debate-dev-site-a7508de8 --query "TagSet[?Key=='Owner'].Value" --output text
```
Success looks like: `7`, then an `owner = "..."` line and a tag value that is the same address. A
number below 7 means a line is missing: find it in the checkout that last applied dev before going
on. If the two addresses differ, set `owner` to the deployed tag's value.

## Step 1 — Plan apply A in dev

The key, the two secrets with their policies, the two roles and the writer permission set. Nothing
here needs a network or an image. The plan is saved to a file, so what is applied in step 2 is
exactly what was read here.

**Operator command** (expected runtime ~2 min)
Where: `$WT`
```bash
cd "$WT"
if env | grep -qE '^(TF_VAR_|TF_WORKSPACE=|TF_DATA_DIR=|TF_CLI_ARGS)'; then echo "STOP: a Terraform override is set in this shell:"; env | grep -oE '^(TF_VAR_[A-Za-z_]*|TF_WORKSPACE|TF_DATA_DIR|TF_CLI_ARGS[A-Za-z_]*)'; else AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev init -input=false && AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev plan -input=false -no-color -out=caselist-credentials.tfplan | tee /tmp/caselist-credentials-plan.txt | tail -5; fi
grep -E '^Plan:|must be replaced|will be destroyed' /tmp/caselist-credentials-plan.txt
grep -E '^  # ' /tmp/caselist-credentials-plan.txt | grep -v 'module.caselist_run' | head
```

**What to read, and what stops you.** Send the whole plan
(`/tmp/caselist-credentials-plan.txt`) to the PM before step 2. If the first `grep` prints no
`Plan:` line at all, the plan failed: read the end of the file, fix what it says, and plan again.

* The first `grep` must print exactly `Plan: 17 to add, 0 to change, 0 to destroy.`, and **no line
  saying `must be replaced` or `will be destroyed`**. A destroyed or replaced
  `aws_ssoadmin_account_assignment` or `aws_ssoadmin_permission_set` anywhere means
  `owner.auto.tfvars` is missing a line: **stop, fix the file, plan again, never apply.**
* The second `grep` must print nothing: every change is under `module.caselist_run`.
* The 17 are: the key and its alias; the two secrets and their two policies; the login and run roles,
  each with one inline policy and its two exclusive-policy resources (12); the
  `DebateDevCaselistSecretWriter` permission set, its inline policy and one account assignment.
* There is **no `aws_secretsmanager_secret_version`**: both secrets are created empty, and no value
  is ever in state.

## Step 2 — Apply the saved plan

Only after the PM's word on step 1's plan.

**Operator command** (expected runtime ~2 min)
Where: `$WT`
```bash
cd "$WT"
AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev apply -input=false caselist-credentials.tfplan
AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev output caselist_secret_writer_permission_set_name
```
Success looks like `Apply complete! Resources: 17 added, 0 changed, 0 destroyed.` and then
`"DebateDevCaselistSecretWriter"`. A stale plan (`Saved plan is stale`) means something changed in
between: go back to step 1.

**If the apply stops at the key** with `MalformedPolicyDocumentException` about the policy not
letting the caller update it later, the identity is not `DebateBreakGlassAdmin`'s role: check the
`sts get-caller-identity` line above. Nothing was created; plan again once it is.

## Step 3 — The coach writes the Tabroom password

Once, now, and again only after the password changes at Tabroom. `set-password` prompts for the
username and then the password twice, with hidden input, and refuses to run outside a terminal; the
password is never an argument or an environment variable. It writes the password secret and prints
the secret's name, nothing about the value.

**The writer's SSO profile**, once per Mac.

**Operator command** (expected runtime ~1 min)
Where: your Mac, anywhere
```bash
ACCOUNT_ID=$(aws sts get-caller-identity --profile debate-admin --query Account --output text)
aws configure set profile.debate-dev-caselist-writer.sso_session debate
aws configure set profile.debate-dev-caselist-writer.sso_account_id "$ACCOUNT_ID"
aws configure set profile.debate-dev-caselist-writer.sso_role_name DebateDevCaselistSecretWriter
aws configure set profile.debate-dev-caselist-writer.region us-east-1
aws sso login --sso-session debate
aws sts get-caller-identity --profile debate-dev-caselist-writer --query Arn --output text
```
Success looks like: an ARN containing `AWSReservedSSO_DebateDevCaselistSecretWriter`. Identity
Center can take a minute to provision a new set's role; if the last line says the role does not
exist, wait a minute and run it again.

**Write the password.** In a terminal window of your own, typed by hand: never piped, never pasted
from a file.

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
if env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell:"; env | grep -oE '^DEBATE_[A-Z_]*'; else DEBATE_ENV=dev uv run debate-research caselist auth set-password --aws-profile debate-dev-caselist-writer; fi
```
Success looks like: `Written to Secrets Manager secret debate-dev-caselist-tabroom-password.` An
`AccessDenied` before any prompt means the profile is not the writer's; an expired session asks for
`aws sso login` first.

**Check a value is there, without reading it.** `describe-secret` shows the secret's versions and
never its value.

```bash
aws secretsmanager describe-secret --profile debate-dev-caselist-writer --region us-east-1 \
  --secret-id debate-dev-caselist-tabroom-password --query 'length(VersionIdsToStages)' --output text
```
Success looks like `1` (one version for each time the password was written). `None` means nothing
was written: run the block above again.

## Step 4 — Check that nobody else can read it

Three refusals, each asked for **the secret's name only**, so that even a read that wrongly
succeeds prints the name and not the password. Each must fail with `AccessDeniedException`. The
writer can describe the secret but not read it, and neither the everyday `debate-dev` profile
(`DebateMaintainer`) nor break-glass can read it: the secret's own policy refuses everyone but the
login role.

**Operator command** (expected runtime ~1 min)
Where: your Mac, anywhere
```bash
for profile in debate-dev-caselist-writer debate-dev debate-admin; do
  printf '%s: ' "$profile"
  aws secretsmanager get-secret-value --profile "$profile" --region us-east-1 \
    --secret-id debate-dev-caselist-tabroom-password --query Name --output text 2>&1 | grep -oE 'AccessDeniedException|debate-dev-caselist-tabroom-password' | head -1
done
```
Success looks like three lines ending `AccessDeniedException`. A line ending in the secret's name
means that profile **can read the password**: stop, and tell the PM before anything else runs.

**Every one of those attempts is in CloudTrail.** CloudTrail delivers an event within about five
minutes.

```bash
aws cloudtrail lookup-events --profile debate-admin --region us-east-1 \
  --lookup-attributes AttributeKey=EventName,AttributeValue=GetSecretValue --max-results 20 \
  --query 'Events[].CloudTrailEvent' --output text | grep -o '"errorCode":"AccessDenied[A-Za-z]*"' | sort | uniq -c
```
Success looks like a count of at least `3` beside `"errorCode":"AccessDenied..."`. Zero means the
events have not arrived yet; wait five minutes and run it again.

## Step 5 — Apply B in dev: the login task and its schedule (follow-up, after `v1-e40-t03`)

Not now: the login task runs the run's image on the run's network, which `v1-e40-t03` builds. Once
t03 has pushed its first image, its outputs give `caselist_login_task`'s six values. Put them in a
file beside the root, `infrastructure/envs/dev/caselist-login-task.auto.tfvars` (none of it is a
secret or a person; commit it or not as t03's runbook says):

```hcl
caselist_login_task = {
  cluster_arn        = "arn:aws:ecs:us-east-1:<account>:cluster/debate-dev-caselist-run"
  subnet_ids         = ["subnet-..."]
  security_group_ids = ["sg-..."]
  repository_arn     = "arn:aws:ecr:us-east-1:<account>:repository/debate-dev-caselist-run"
  repository_url     = "<account>.dkr.ecr.us-east-1.amazonaws.com/debate-dev-caselist-run"
  image_digest       = "sha256:<64 hex digits>"
}
```

Then plan, read, and apply, as in steps 1 and 2.

**Operator command** (expected runtime ~2 min)
Where: `$WT`
```bash
cd "$WT"
if env | grep -qE '^(TF_VAR_|TF_WORKSPACE=|TF_DATA_DIR=|TF_CLI_ARGS)'; then echo "STOP: a Terraform override is set in this shell"; else AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev plan -input=false -no-color -out=caselist-login.tfplan | tee /tmp/caselist-login-plan.txt | tail -5; fi
grep -E '^Plan:|must be replaced|will be destroyed' /tmp/caselist-login-plan.txt
```

**What to read, and what stops you.** `Plan: 11 to add, 0 to change, 0 to destroy.` and no line
saying `must be replaced` or `will be destroyed`: the log group `debate-dev-caselist-login`, the
execution role and the scheduler role (each with one inline policy and two exclusive-policy
resources), the task definition `debate-dev-caselist-login` whose image ends `@sha256:` and the
digest above, and the schedule. The task definition must show **no `secrets`** in its container
definition. Send the plan to the PM; apply only after the PM's word:

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev apply -input=false caselist-login.tfplan
```
Success looks like `Apply complete! Resources: 11 added, 0 changed, 0 destroyed.`

**The first scheduled login** runs the next Wednesday at 03:00 America/Chicago. After it, the token
secret has a version written by the login role, and its log says so. Run this on the Wednesday
morning:

```bash
aws secretsmanager describe-secret --profile debate-dev-caselist-writer --region us-east-1 \
  --secret-id debate-dev-caselist-token --query '[LastChangedDate, length(VersionIdsToStages)]' --output text
aws logs tail debate-dev-caselist-login --profile debate-admin --region us-east-1 --since 12h | grep -oE '"stored": true, "location": "Secrets Manager secret debate-dev-caselist-token"|CASELIST_LOGIN_REJECTED|"status": "error"' | head -3
```
Success looks like a `LastChangedDate` that morning after 03:00 Chicago time and a version count of
at least `1`, then the line `"stored": true, "location": "Secrets Manager secret
debate-dev-caselist-token"` from the task's `--json` result. No version, or a log ending `CASELIST_LOGIN_REJECTED`,
means the login failed: the coach is emailed once `v1-e40-t05` builds the alert topic, and the fixes
are below.

## Prod, at the pilot's promotion (follow-up)

The same steps 1 to 5 against `infrastructure/envs/prod`, from a checkout of `main`, with `prod` for
`dev` in every name: `debate-prod-caselist-...`, `DebateProdCaselistSecretWriter`, the profile
`debate-prod-caselist-writer`, and `DEBATE_ENV=prod`. Prod's `owner.auto.tfvars` comes from the
checkout that last applied prod. ADR-0020 (7) moves the run's home at the same time; `v1-e40-t06`'s
runbook orders the two.

## When the weekly login fails

* **The login was refused** (`CASELIST_LOGIN_REJECTED`): the password changed at Tabroom, or is
  wrong. Write it again (step 3). The refused login is not retried; the next one is next Wednesday,
  and the run at 06:00 uses the previous token while it still works.
* **Tabroom or OpenCaselist asks for something more** than the password (a code, a CAPTCHA, new
  terms): log in by hand, on the Mac, as the writer. This prompts as `caselist auth login` always
  has and writes only the token, to the token secret; the weekly run then proceeds unchanged.

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
if env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; else DEBATE_ENV=dev DEBATE_CASELIST__API_ENABLED=true uv run debate-research caselist auth login --token-backend secretsmanager --aws-profile debate-dev-caselist-writer; fi
```
Success looks like: `Logged in. The caselist_token is stored in the secretsmanager backend (Secrets
Manager secret debate-dev-caselist-token) ... The password was not stored.`

* **`caselist auth logout` does not delete the token secret.** It refuses for the Secrets Manager
  backend: the next login replaces the token, and only `DebateBreakGlassAdmin` may delete a secret.

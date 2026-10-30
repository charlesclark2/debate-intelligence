<!-- docs-index: Building and verifying the AWS account baseline: identity, audit, budgets -->
# Runbook: AWS account baseline

How the AWS baseline for the Debate Intelligence Platform is built and verified. Spec:
[`v1-e29-t01-aws-account-baseline`](../../plan_specs/v1/e29-cloud-evidence-store/t01-aws-account-baseline.yaml).
Decision: [ADR-0010](../adr/0010-primary-aws-region.md).

Written for an adult engineer with administrator access to the account. Everything here is run by
a human operator. **No step in this runbook is ever run by CI or by an agent session**, and
`terraform apply` in particular is an operator-only command.

## What the baseline is

| | |
|---|---|
| Region | `us-east-1` for every resource ([ADR-0010](../adr/0010-primary-aws-region.md)) |
| Account structure | One existing AWS Organization management account. `dev` and `prod` are separated by tag and resource name, not by an account boundary — the fallback ADR-0010 records |
| Human access | IAM Identity Center only. No IAM users for people, no long-lived access keys |
| Permission sets | `DebateBreakGlassAdmin`, `DebateMaintainer`, `DebateReadOnly` |
| Audit | One organization-wide, multi-region CloudTrail with log-file validation |
| Cost | Per-environment monthly budgets, the model spend budget ([below](#the-model-spend-budget)), and a Cost Anomaly Detection monitor |
| CLI profiles | `debate-dev` and `debate-prod`, used by `debate-research store` (`v1-e29-t05`) |

Terraform for this baseline lives in
[`infrastructure/bootstrap/organization/`](../../infrastructure/bootstrap/organization/). It kept
**local state** while it was the only root: it runs before any remote state bucket exists.
`v1-e29-t02-terraform-bootstrap` created those buckets and moved this root's state into the prod
one — see [terraform-bootstrap.md](terraform-bootstrap.md) step 6.

Students never receive AWS console, CLI or IAM access of any kind. Some are minors
([architecture proposal §14](../architecture/architecture_proposal.md#14-security-privacy-and-student-safety)).

## Before you start

You need:

- Administrator access to the Organization's management account, through Identity Center.
- The AWS CLI v2 and Terraform ≥ 1.10 (`aws --version`, `terraform version`). The floor moved
  from 1.7 with `v1-e29-t02-terraform-bootstrap`, which needs the S3 backend's native state
  locking.
- The account id, the Organization id and the Identity Center instance — **not recorded in this
  repository**. Read them from the account itself:

  ```bash
  aws sts get-caller-identity
  aws organizations describe-organization
  aws sso-admin list-instances
  ```

Placeholders used below: `<account-id>`, `<sso-start-url>`, `<identity-center-username>`,
`<your-email>`.

## Step 1 — Lock down the root user (manual, console)

The root user cannot be managed by Terraform. In the console, signed in as root:

1. **Enable MFA** on the root user if it is not already on.
   Verify: `aws iam get-account-summary --query 'SummaryMap.AccountMFAEnabled'` returns `1`.
2. **Delete every root access key.** Root access keys are forbidden by the task spec; a root key
   in a credentials file makes every other control here decorative.
   Verify: `aws iam get-account-summary --query 'SummaryMap.AccountAccessKeysPresent'` returns `0`.
3. **Remove any `[default]` profile in `~/.aws/credentials` that holds those keys**, so day-to-day
   CLI use goes through SSO. Confirm with `aws sts get-caller-identity` that the ARN you get is an
   `assumed-role/AWSReservedSSO_...` ARN and never `:root`.
4. Confirm the root email and its recovery phone are ones you will still control in several
   years. If the account is registered to an institutional address that can be revoked, changing
   it is a manual console step and worth doing before the account holds anything real.

Then check no IAM user is carrying long-lived keys:

```bash
aws iam list-users --query 'Users[].UserName'
aws iam list-access-keys --user-name <user-name>
```

Any IAM user with an active key should be migrated to a role or Identity Center and its key
deleted. If a key belongs to a different project sharing this account, record the decision rather
than leaving it undocumented.

## Step 2 — Enable CloudTrail trusted access on the Organization (manual, CLI)

An organization trail cannot be created until CloudTrail has trusted access to the Organization.
This is deliberately not a Terraform resource: managing it would mean importing the whole
Organization into this root's state, where a mistaken `destroy` would reach unrelated projects.

```bash
aws organizations enable-aws-service-access \
  --service-principal cloudtrail.amazonaws.com
```

Verify:

```bash
aws organizations list-aws-service-access-for-organization \
  --query 'EnabledServicePrincipals[].ServicePrincipal'
```

`cloudtrail.amazonaws.com` must appear. If you skip this, `terraform plan` reports the
`cloudtrail_trusted_access_enabled` check failure that names this step.

## Step 3 — Require MFA in IAM Identity Center (manual, console)

The AWS provider has no resource for Identity Center MFA settings, so this is a console step.

IAM Identity Center → Settings → Authentication → Multi-factor authentication:

- Prompt for MFA: **Every time they sign in** (or *only when their sign-in context changes*, if
  that is too heavy for daily use — record which you chose).
- If a user does not yet have a registered MFA device: **Require them to register an MFA device
  at sign-in**.
- Who can manage MFA devices: users can add and manage their own.

## Step 4 — Apply the baseline Terraform (operator)

The editor step fills in `terraform.tfvars`, which is gitignored: it holds your emails and Identity
Center user names.

```bash
cd infrastructure/bootstrap/organization
cp terraform.tfvars.example terraform.tfvars
$EDITOR terraform.tfvars
terraform init
terraform plan -out=baseline.tfplan
terraform apply baseline.tfplan
```

Expected runtime: about 2–4 minutes. It creates roughly 25 resources: three permission sets with
their policy attachments and account assignments, the CloudTrail KMS key and log bucket with its
policies, the organization trail, three budgets, and the anomaly monitor and subscription.

`terraform.tfvars` holds your email and Identity Center user names and is gitignored. Do not
commit it, and do not put account ids in any committed file.

Notes on the apply:

- `identity_center_user_names` takes Identity Center **user names**, not emails, and adult
  maintainers only.
- `break_glass_user_names` must be a subset of `identity_center_user_names`; a check block tells
  you if it is not.
- The log bucket policy denies `s3:DeleteObject` to everything but the account root, so a
  `terraform destroy` of this root will fail on the bucket while logs are in it. That is
  intentional. To genuinely retire the trail, remove the `DenyLogDeletion` statement in a
  reviewed change first.

## Step 5 — Activate the cost allocation tags (after the apply)

Every budget and the anomaly monitor filters on the `Project` and `Environment` tags. Until those
tags are activated for billing they report **$0**, and a budget that always reads zero never
alerts.

**This step cannot come earlier.** A tag key only becomes activatable once AWS has seen a
resource carrying it, so the keys do not exist until step 4 has created the tagged resources, and
they can take up to 24 hours to appear afterwards.

Check whether the keys have surfaced yet:

```bash
aws ce list-cost-allocation-tags \
  --query 'CostAllocationTags[?TagKey==`Project` || TagKey==`Environment`].[TagKey,Status]' \
  --output text
```

Empty output means AWS has not surfaced them yet - wait and retry. Once both appear, activate them:

```bash
aws ce update-cost-allocation-tags-status --cost-allocation-tags-status \
  TagKey=Project,Status=Active TagKey=Environment,Status=Active
```

Or in the console: Billing and Cost Management -> Cost allocation tags -> User-defined cost
allocation tags -> select `Project` and `Environment` -> **Activate**.

Activation is not retroactive: spend from before activation is never attributed to these tags, so
the first days of budget figures will read low. Do not treat that as the budgets being broken.

## Step 6 — Configure the CLI SSO profiles

Two named profiles against the same account id, differing by permission set. These are what the
operator and `debate-research store sync|ls|get` (`v1-e29-t05`) use; the CLI selects the profile
from `DEBATE_ENV`.

```bash
aws configure sso
```

Answer as follows, once per profile:

| Prompt | `debate-dev` | `debate-prod` |
|---|---|---|
| SSO session name | `debate` | `debate` |
| SSO start URL | `<sso-start-url>` | same |
| SSO region | `us-east-1` | same |
| SSO registration scopes | `sso:account:access` | same |
| Account | `<account-id>` | same |
| Role (permission set) | `DebateMaintainer` | `DebateReadOnly` |
| Default client region | `us-east-1` | `us-east-1` |
| Output format | `json` | `json` |
| Profile name | `debate-dev` | `debate-prod` |

The resulting `~/.aws/config` looks like this (no secrets; SSO issues short-lived credentials):

```ini
[sso-session debate]
sso_start_url = <sso-start-url>
sso_region = us-east-1
sso_registration_scopes = sso:account:access

[profile debate-dev]
sso_session = debate
sso_account_id = <account-id>
sso_role_name = DebateMaintainer
region = us-east-1
output = json

[profile debate-prod]
sso_session = debate
sso_account_id = <account-id>
sso_role_name = DebateReadOnly
region = us-east-1
output = json
```

Sign in and verify both:

```bash
aws sso login --sso-session debate
aws sts get-caller-identity --profile debate-dev
aws sts get-caller-identity --profile debate-prod
```

Each must return an `assumed-role/AWSReservedSSO_DebateMaintainer_...` or
`.../AWSReservedSSO_DebateReadOnly_...` ARN. If either returns a `:root` ARN or an IAM user ARN,
stop and go back to step 1.

`aws sso login` is needed again whenever the session expires (8 hours for `DebateMaintainer`,
4 for `DebateReadOnly`).

**`debate-prod` is read-only today, by design.** Writing prod evidence needs the least-privilege
operator permission set that `v1-e29-t03-evidence-buckets` adds; when it lands, change
`sso_role_name` on the `debate-prod` profile to that set and update this table. Until then, a prod
write is a deliberate break-glass action through `DebateBreakGlassAdmin`.

## Step 7 — Verify the baseline

Which profile runs each check matters. `debate-dev` (`DebateMaintainer`) is **denied** every
`debate-shared-*` and `debate-prod-*` bucket by design, so the audit-bucket checks run under
`debate-prod` (`DebateReadOnly`), which has read access and no denies.

```bash
aws sso-admin list-permission-sets --instance-arn <instance-arn> --profile debate-dev

aws cloudtrail describe-trails --profile debate-dev \
  --query 'trailList[?Name==`debate-shared-organization-trail`].{Org:IsOrganizationTrail,MultiRegion:IsMultiRegionTrail,Validation:LogFileValidationEnabled,Kms:KmsKeyId}'

aws cloudtrail get-trail-status --name debate-shared-organization-trail --profile debate-dev \
  --query '{Logging:IsLogging,LastDelivery:LatestDeliveryTime}'

aws s3api get-public-access-block --bucket debate-shared-cloudtrail-<account-id> --profile debate-prod
aws s3api get-bucket-versioning   --bucket debate-shared-cloudtrail-<account-id> --profile debate-prod
aws s3api get-bucket-encryption   --bucket debate-shared-cloudtrail-<account-id> --profile debate-prod

aws budgets describe-budgets --account-id <account-id> --profile debate-dev \
  --query 'Budgets[?starts_with(BudgetName, `debate-`)].{Name:BudgetName,Limit:BudgetLimit.Amount}'
aws ce get-anomaly-monitors --profile debate-dev \
  --query 'AnomalyMonitors[?MonitorName==`debate-shared-spend-monitor`]'
```

The trail's first log delivery can take up to 15 minutes. `IsLogging` should be `true` immediately.

Trail *metadata* is readable from `debate-dev` — the maintainer denies cover `DeleteTrail`,
`StopLogging`, `UpdateTrail` and `PutEventSelectors`, not `describe-trails` or `get-trail-status`.
Seeing that the trail exists and is logging is not a privilege worth withholding.

### Verify the environment boundary actually holds

ADR-0010's single-account fallback rests on `DebateMaintainer` being unable to reach prod and
shared resources, and on it being unable to remove the guardrails. Both are worth checking on
purpose rather than assuming.

Use `iam simulate-principal-policy`, which evaluates the policies **without performing the
actions**. Do not test a deny by attempting the real call: if the deny has failed, the test
itself stops the trail or deletes the budget. Find the role, then simulate:

```bash
ROLE=$(aws iam list-roles \
  --query 'Roles[?starts_with(RoleName, `AWSReservedSSO_DebateMaintainer`)].Arn' --output text)

aws iam simulate-principal-policy --policy-source-arn "$ROLE" \
  --action-names s3:ListBucket s3:GetObject s3:PutObject \
  --resource-arns "arn:aws:s3:::debate-shared-cloudtrail-<account-id>" \
  --query 'EvaluationResults[].{Action:EvalActionName,Decision:EvalDecision}' --output table

aws iam simulate-principal-policy --policy-source-arn "$ROLE" \
  --action-names cloudtrail:StopLogging cloudtrail:DeleteTrail sso:CreateAccountAssignment iam:CreateAccessKey \
  --query 'EvaluationResults[].{Action:EvalActionName,Decision:EvalDecision}' --output table

aws iam simulate-principal-policy --policy-source-arn "$ROLE" \
  --action-names budgets:DeleteBudget budgets:ModifyBudget \
  --query 'EvaluationResults[].{Action:EvalActionName,Decision:EvalDecision}' --output table
```

Every row must read `explicitDeny`. Budgets actions go in their own call - the simulator refuses
to mix them with the others, because they use a different authorization context.

Anything reading `allowed` means the boundary is gone and the single-account fallback's premise
no longer holds: stop and fix the permission set before putting evidence in the account. Re-run
this after `v1-e29-t03-evidence-buckets` lands, against the prod evidence bucket, and after any
change to `identity.tf`.

Ordinary reads should *not* be denied. `aws organizations describe-organization`,
`aws sso-admin list-permission-sets` and `aws identitystore list-users` all work from
`debate-dev`, deliberately: a deny that shows up during routine work is one the operator learns
to ignore, and these denies need to keep meaning something.

### Confirm a budget alert actually arrives

A budget nobody receives is not a control, and email subscriptions fail silently, so prove the
delivery path once.

**Lowering one of the three real budgets does not test anything until the evidence buckets
exist.** All three filter on `Environment` = `dev` or `prod`, or on Bedrock usage. Until
`v1-e29-t03-evidence-buckets` creates dev and prod resources, those budgets correctly measure $0
and no threshold can be crossed no matter how low the limit is set. The only tagged resources the
baseline itself creates are the trail's bucket and key, both `Environment = shared`.

So test the delivery path with a throwaway budget that has no cost filters and therefore measures
total account spend. Create it outside Terraform so it never enters state:

```bash
aws budgets create-budget --account-id <account-id> --budget '{
  "BudgetName": "debate-alert-delivery-test",
  "BudgetLimit": {"Amount": "1", "Unit": "USD"},
  "TimeUnit": "MONTHLY",
  "BudgetType": "COST"
}' --notifications-with-subscribers '[{
  "Notification": {
    "NotificationType": "ACTUAL",
    "ComparisonOperator": "GREATER_THAN",
    "Threshold": 50,
    "ThresholdType": "PERCENTAGE"
  },
  "Subscribers": [{"SubscriptionType": "EMAIL", "Address": "<your-email>"}]
}]'
```

Budgets evaluate roughly three times a day, so the email lands within about 8-24 hours. Check
spam. Then remove it:

```bash
aws budgets delete-budget --account-id <account-id> --budget-name debate-alert-delivery-test
```

Record that the alert was received. Re-test the real budgets against live spend once t03 and t05
have put evidence in the dev bucket - that is the first point at which they measure anything.

The anomaly subscription confirms itself:

```bash
aws ce get-anomaly-subscriptions \
  --query 'AnomalySubscriptions[?SubscriptionName==`debate-shared-spend-alerts`].Subscribers'
```

`Status` must read `CONFIRMED`. Cost Anomaly Detection needs about 10 days of history before it
starts reporting, and it only sees spend once the cost allocation tags from step 5 are active.

## Step 8 — Confirm Bedrock model access

The account needs model access granted before any ModelRouter call works ([ADR-0010](../adr/0010-primary-aws-region.md)
records which models, and why the region is `us-east-1`).

Bedrock console → Model access → request access for the models in the ADR-0010 availability
table. Then confirm they are visible:

```bash
aws bedrock list-foundation-models --region us-east-1 --profile debate-dev \
  --query 'modelSummaries[?contains(modelId, `claude`) || contains(modelId, `titan-embed`) || contains(modelId, `rerank`)].modelId'
aws bedrock list-inference-profiles --region us-east-1 --profile debate-dev \
  --query 'inferenceProfileSummaries[?starts_with(inferenceProfileId, `us.anthropic`)].{Id:inferenceProfileId,Status:status}'
```

The Claude models are **inference-profile only** — calls must use the `us.`-prefixed profile id,
never the bare model id.

While you are here, note the current per-token rates for the ADR-0010 models from the Bedrock
pricing page. The AWS Price List API did not carry entries for them when ADR-0010 was written, so
there is no programmatic check for this; it is a judgement call about whether the budget in step 5
is sized correctly.

## The model spend budget

`debate-shared-bedrock-monthly` holds the account's model spend to the coach's ceiling: $100 a month
across dev and prod, $50 in each profile, on the condition that model work is never duplicated
between them. It sends notices at $50, $80 and $100 of actual spend and $100 of forecast spend, by
email to `model_budget_notification_emails` (the coach's address, in this root's gitignored
`terraform.tfvars`). It is [`modules/model_spend_budget`](../../infrastructure/modules/model_spend_budget/),
called from `budgets.tf`. Spec:
[`v1-e05-t16-bedrock-budget-alarm`](../../plan_specs/v1/e05-model-router/t16-bedrock-budget-alarm.yaml).

Its filter is the services and usage types model calls are billed under, as Cost Explorer reports
them, with no tag: model charges carry no cost allocation tag. Claude and Cohere models bill as AWS
Marketplace services named after the model, so **a model that has never been billed is not in the
filter**. After a new model's first billed call (the 5.5 models of prod's routes, `v1-e05-t17`),
re-run the counts below, add the new names to the module's lists and to its test, and apply. The
budget notifies; it never stops spend. What refuses a call is `models.budget_usd_monthly`
(`v1-e05-t15`).

**Never on a Wednesday.** The cloud run runs Wednesdays at 06:00 America/Chicago
([caselist-cloud-run.md](caselist-cloud-run.md)); every plan and apply block below refuses to start
on one.

### Counting what model calls are billed under

Read-only, as `debate-admin`, under a minute. It lists last month and this month so far three ways:
by service and usage type (the names the filter needs), by service and `Project` tag, and by record
type (credits would net spend away). It makes seven Cost Explorer requests and prints no account id.
If Cost Explorer cannot be read, it prints `STOP` and runs nothing more. Not on the first of a month,
when this month has no day to list yet.

**Operator command** (expected runtime under a minute)
Where: any terminal on your Mac
```bash
if ! aws ce get-cost-and-usage --profile debate-admin --time-period Start=$(date -v1d -v-1m +%F),End=$(date -v2d -v-1m +%F) --granularity MONTHLY --metrics UnblendedCost --query 'ResultsByTime[0].TimePeriod.Start' --output text; then
  echo "STOP: Cost Explorer could not be read as debate-admin (not enabled, or this role may not read it). Paste this output back and run nothing more."
else
  rows='(.ResultsByTime[].Groups[] | select((.Metrics.UnblendedCost.Amount | tonumber) != 0) | (.Keys | join("\t")) + "\t" + .Metrics.UnblendedCost.Amount), (if .NextPageToken then "INCOMPLETE: Cost Explorer returned more pages than this listing shows" else empty end)'
  for month_start month_end in "$(date -v1d -v-1m +%F)" "$(date -v1d +%F)" "$(date -v1d +%F)" "$(date +%F)"; do
    echo "== ${month_start} to ${month_end}, by service and usage type (USD, non-zero rows)"
    aws ce get-cost-and-usage --profile debate-admin --time-period Start=${month_start},End=${month_end} --granularity MONTHLY --metrics UnblendedCost --group-by Type=DIMENSION,Key=SERVICE Type=DIMENSION,Key=USAGE_TYPE --output json | jq -r "$rows" | sort
    echo "== ${month_start} to ${month_end}, by service and Project tag (USD, non-zero rows)"
    aws ce get-cost-and-usage --profile debate-admin --time-period Start=${month_start},End=${month_end} --granularity MONTHLY --metrics UnblendedCost --group-by Type=DIMENSION,Key=SERVICE Type=TAG,Key=Project --output json | jq -r "$rows" | sort
    echo "== ${month_start} to ${month_end}, by record type (USD, non-zero rows)"
    aws ce get-cost-and-usage --profile debate-admin --time-period Start=${month_start},End=${month_end} --granularity MONTHLY --metrics UnblendedCost --group-by Type=DIMENSION,Key=RECORD_TYPE --output json | jq -r "$rows" | sort
  done
fi
```
Success looks like six listings and no `INCOMPLETE` line. A model charge is a row whose service is
`Amazon Bedrock` or ends in `(Amazon Bedrock Edition)`. Record names only, never amounts, and never a
model name that is not in the output.

### Applying a change to the budget

From a worktree of its own at `origin/dev`, never in the main checkout. This root is account-wide and
its state is in the prod state bucket; it also holds the permission sets, so the plan check below
refuses any change outside the budget. The order: the worktree, the sign-in, the tfvars, the plan, the
check, **the PM's read**, the apply, and the next day, the budget's first reading.

**Shell variables**, used by every block below. `COACH_EMAIL` is where the budget's notices go.

```bash
MAIN="$HOME/Documents/debate/debate-intelligence-tool/debate-intelligence"
WT="$HOME/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/model-spend-budget-apply"
COACH_EMAIL='the-coach@example.org'
```

**Once: the worktree.** It is created detached, from the main checkout's repository, without
switching the main checkout's branch.

```bash
git -C "$MAIN" fetch origin
test -d "$WT" || git -C "$MAIN" worktree add --detach "$WT" origin/dev
```

**Every time: the worktree at `origin/dev`, with the module merged.**

```bash
cd "$WT" || echo "STOP: the worktree is missing: $WT"
git fetch origin
git switch --detach origin/dev
test -f infrastructure/modules/model_spend_budget/main.tf && echo "ok: $(pwd) at origin/dev $(git rev-parse --short HEAD), model_spend_budget merged" || echo "NOT MERGED: origin/dev has no v1-e05-t16"
git status --porcelain | grep -v 'terraform.tfvars' | head -3
```
Success looks like `ok: <the worktree> at origin/dev <commit>, model_spend_budget merged`, and
nothing after it. `NOT MERGED` means the pull request has not merged into `dev`: stop and wait.

**Sign in, and confirm the identity the plan runs as.** This root holds the permission sets, so it
is planned and applied as `debate-admin`. The block prints the role's name, not its account.

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
aws sso login --sso-session debate
aws sts get-caller-identity --profile debate-admin --query Arn --output text | cut -d/ -f2
```
Success looks like a name starting `AWSReservedSSO_DebateBreakGlassAdmin`.

**The tfvars.** The root's `terraform.tfvars` lives in the main checkout and is gitignored; this
keeps it the one copy. The block backs it up, deletes the `bedrock_monthly_budget_usd` line (the
variable is gone: the limit is fixed in the module), adds `model_budget_notification_emails` if it is
missing, and copies the file into the worktree. It prints counts, never the addresses.

**Operator command** (expected runtime under a minute)
Where: `$WT`
```bash
cd "$WT"
TFVARS="$MAIN/infrastructure/bootstrap/organization/terraform.tfvars"
if ! test -f "$TFVARS"; then
  echo "STOP: no terraform.tfvars in the main checkout's organization root: $TFVARS"
else
  mkdir -p ~/aws-backups/debate-terraform-state
  cp "$TFVARS" ~/aws-backups/debate-terraform-state/organization-tfvars-$(date +%Y%m%d-%H%M%S)
  sed -i '' '/^[[:space:]]*bedrock_monthly_budget_usd[[:space:]]*=/d' "$TFVARS"
  grep -q '^model_budget_notification_emails' "$TFVARS" || printf 'model_budget_notification_emails = ["%s"]\n' "$COACH_EMAIL" >> "$TFVARS"
  cp "$TFVARS" infrastructure/bootstrap/organization/terraform.tfvars
  echo "bedrock_monthly_budget_usd lines: $(grep -c 'bedrock_monthly_budget_usd' infrastructure/bootstrap/organization/terraform.tfvars)"
  echo "model_budget_notification_emails lines: $(grep -c '^model_budget_notification_emails' infrastructure/bootstrap/organization/terraform.tfvars)"
fi
```
Success looks like `bedrock_monthly_budget_usd lines: 0` and `model_budget_notification_emails
lines: 1`, and no `STOP` line.

**The plan**, saved to a file, so what the apply applies is exactly what the PM read. The block
refuses a Wednesday, a Terraform override in the shell, and a tfvars that still sets
`bedrock_monthly_budget_usd` or has no `model_budget_notification_emails`.

**Operator command** (expected runtime ~2 min)
Where: `$WT`
```bash
cd "$WT"
ORG=infrastructure/bootstrap/organization
PLAN_TXT=/tmp/model-spend-budget-plan.txt
rm -f "$PLAN_TXT"
if [ "$(date +%A)" = "Wednesday" ]; then
  echo "STOP: it is Wednesday, the cloud run's day; plan on another day"
elif env | grep -qE '^(TF_VAR_|TF_WORKSPACE=|TF_DATA_DIR=|TF_CLI_ARGS)'; then
  echo "STOP: a Terraform override is set in this shell"
elif grep -q 'bedrock_monthly_budget_usd' "$ORG/terraform.tfvars"; then
  echo "STOP: terraform.tfvars still sets bedrock_monthly_budget_usd; run the tfvars block again"
elif ! grep -q '^model_budget_notification_emails' "$ORG/terraform.tfvars"; then
  echo "STOP: terraform.tfvars has no model_budget_notification_emails; run the tfvars block again"
else
  AWS_PROFILE=debate-admin terraform -chdir="$ORG" init -input=false -no-color | tail -1
  AWS_PROFILE=debate-admin terraform -chdir="$ORG" plan -input=false -no-color -out=model-spend-budget.tfplan > "$PLAN_TXT" 2>&1
  tail -3 "$PLAN_TXT"
fi
grep -E '^Plan:|must be replaced|will be destroyed' "$PLAN_TXT"
grep -E '^  # ' "$PLAN_TXT" | grep -v -e '^  # module\.model_spend_budget\.aws_budgets_budget\.model_spend will be updated in-place$' -e '^  # (moved from aws_budgets_budget\.bedrock_monthly)$'
echo "permission set or assignment change lines: $(grep -E '^  # ' "$PLAN_TXT" | grep -c 'aws_ssoadmin_')"
```

**What to read, and what stops you.** The first `grep` prints exactly
`Plan: 0 to add, 1 to change, 0 to destroy.` and no `must be replaced` or `will be destroyed` line.
The second prints nothing: the plan's only change lines are the budget's own address and, the first
time, its `(moved from aws_budgets_budget.bedrock_monthly)`. The count reads
`permission set or assignment change lines: 0`. It counts change lines only (`  # <address> will
be ...`), never `Refreshing state...` lines, which name every permission set the root reads.
Anything else stops you: send `/tmp/model-spend-budget-plan.txt` to the PM and do not apply. No `Plan:`
line at all means the plan failed or was refused: read the end of the file. The plan text holds the
coach's address; it stays on your Mac.

**The plan checked against exactly that shape.** `PLAN OK` only for one change, the budget updated in
place, with the limit, the four notices and the filter this module sets, and no permission set or
account assignment changed. It prints no account id and no address.

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
AWS_PROFILE=debate-admin terraform -chdir=infrastructure/bootstrap/organization show -json model-spend-budget.tfplan > /tmp/model-spend-budget-plan.json
python3 -I - /tmp/model-spend-budget-plan.json <<'MODELBUDGETPLAN'
import json, sys
plan = json.load(open(sys.argv[1]))
address = "module.model_spend_budget.aws_budgets_budget.model_spend"
moved_from = "aws_budgets_budget.bedrock_monthly"
services = [
    "Amazon Bedrock",
    "Claude Haiku 4.5 (Amazon Bedrock Edition)",
    "Claude Sonnet 4.6 (Amazon Bedrock Edition)",
    "Cohere Rerank v3.5 (Amazon Bedrock Edition)",
]
usage_types = [
    "USE1-MP:USE1_InputTokenCount-Units",
    "USE1-MP:USE1_OutputTokenCount-Units",
    "USE1-MP:USE1_search_units-Units",
    "USE1-TitanEmbeddingV2-Text-input-tokens",
]
notices = sorted([("ACTUAL", 50.0), ("ACTUAL", 80.0), ("ACTUAL", 100.0), ("FORECASTED", 100.0)])
changes = [c for c in plan.get("resource_changes", []) if c["change"]["actions"] not in (["no-op"], ["read"])]
grants = sum(1 for c in changes if c["type"].startswith("aws_ssoadmin_"))
problems = []
others = sorted(c["address"] + " " + "/".join(c["change"]["actions"]) for c in changes if c["address"] != address)
if others:
    problems.append("other changes: " + ", ".join(others))
budget = [c for c in changes if c["address"] == address]
recipients = set()
if len(budget) != 1:
    problems.append("the budget is changed %d times, not once" % len(budget))
else:
    change = budget[0]
    actions = change["change"]["actions"]
    if actions != ["update"]:
        problems.append("the budget is " + "/".join(actions) + ", not updated in place")
    if change.get("previous_address") not in (None, moved_from):
        problems.append("the budget moves from " + str(change.get("previous_address")))
    after = change["change"].get("after") or {}
    if after.get("name") != "debate-shared-bedrock-monthly":
        problems.append("the budget is named " + str(after.get("name")))
    if (after.get("budget_type"), after.get("time_unit"), after.get("limit_unit")) != ("COST", "MONTHLY", "USD"):
        problems.append("the budget is not a monthly cost budget in USD")
    try:
        limit = float(after.get("limit_amount"))
    except (TypeError, ValueError):
        limit = None
    if limit != 100.0:
        problems.append("the limit is " + str(after.get("limit_amount")) + ", not 100")
    filters = {f.get("name"): sorted(f.get("values") or []) for f in after.get("cost_filter") or []}
    if filters != {"Service": sorted(services), "UsageType": sorted(usage_types)}:
        problems.append("the filter is " + json.dumps(filters, sort_keys=True))
    planned = after.get("notification") or []
    shape = sorted((n.get("notification_type"), float(n.get("threshold") or 0)) for n in planned)
    kinds = {(n.get("comparison_operator"), n.get("threshold_type")) for n in planned}
    if shape != notices or kinds != {("GREATER_THAN", "ABSOLUTE_VALUE")}:
        problems.append("the notices are " + "; ".join("%s %s" % s for s in shape) + " " + str(sorted(kinds)))
    recipients = {tuple(sorted(n.get("subscriber_email_addresses") or [])) for n in planned}
    if len(recipients) != 1 or not min(recipients):
        problems.append("the notices do not all go to one non-empty list of addresses")
    if any(n.get("subscriber_sns_topic_arns") for n in planned):
        problems.append("a notice goes to an SNS topic")
if problems:
    print("PLAN NOT OK: " + " | ".join(problems) + " | permission set or assignment changes: %d" % grants)
else:
    moved = "moved from " + moved_from if budget[0].get("previous_address") == moved_from else "already in the module"
    print("PLAN OK: one change, %s updated in place (%s); 100 USD a month; notices at 50, 80 and 100 actual and 100 forecast, to %d address(es); filter of %d services and %d usage types; permission set or assignment changes: %d" % (address, moved, len(min(recipients)), len(services), len(usage_types), grants))
MODELBUDGETPLAN
```
Success looks like one line, `PLAN OK: one change, module.model_spend_budget.aws_budgets_budget.model_spend
updated in place (moved from aws_budgets_budget.bedrock_monthly); ...; permission set or assignment
changes: 0`. The first apply says `moved from`; a later one (new model names) says `already in the
module`, and its lists above change with the module's. `PLAN NOT OK` names what differs: send it to
the PM and do not apply. The plan check and the plan's text both go to the PM, who reads them before
the apply.

**The apply.** Only after the PM's word on the plan, the same day, and not on a Wednesday.

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
if [ "$(date +%A)" = "Wednesday" ]; then
  echo "STOP: it is Wednesday, the cloud run's day; apply on another day"
elif env | grep -qE '^(TF_VAR_|TF_WORKSPACE=|TF_DATA_DIR=|TF_CLI_ARGS)'; then
  echo "STOP: a Terraform override is set in this shell"
else
  AWS_PROFILE=debate-admin terraform -chdir=infrastructure/bootstrap/organization apply -input=false -no-color model-spend-budget.tfplan | tail -3
  AWS_PROFILE=debate-admin terraform -chdir=infrastructure/bootstrap/organization output -no-color budget_names
fi
```
Success looks like `Apply complete! Resources: 0 added, 1 changed, 0 destroyed.`, then the three
budget names, `debate-shared-bedrock-monthly` among them. `Saved plan is stale` means something
changed in between: go back to the plan. Never `-target`, and never edit the budget in the console.

**The budget's first reading, the next day.** AWS Budgets recalculates a budget's spend a few times a
day, so read it the day after the apply, not on the first of a month (this month has no billed day
yet), and not before this month has a billed model call. The block reads the budget's limit, actual
and forecast spend and its four notices, then Cost Explorer's total for the same month under the same
filter (the same four services AND the same four usage types). It reads the account id into a shell
variable and never prints it.

**Operator command** (expected runtime under a minute)
Where: any terminal on your Mac
```bash
ACCOUNT_ID=$(aws sts get-caller-identity --profile debate-admin --query Account --output text)
echo "== the budget: limit, actual spend, forecast spend (USD)"
aws budgets describe-budget --profile debate-admin --account-id "$ACCOUNT_ID" --budget-name debate-shared-bedrock-monthly --query 'Budget.[BudgetLimit.Amount, CalculatedSpend.ActualSpend.Amount, CalculatedSpend.ForecastedSpend.Amount]' --output text
echo "== its notices"
aws budgets describe-notifications-for-budget --profile debate-admin --account-id "$ACCOUNT_ID" --budget-name debate-shared-bedrock-monthly --query 'Notifications[].[NotificationType, ComparisonOperator, Threshold, ThresholdType]' --output text | sort
echo "== Cost Explorer, this month so far, under the budget's filter (USD)"
aws ce get-cost-and-usage --profile debate-admin --time-period Start=$(date -v1d +%F),End=$(date +%F) --granularity MONTHLY --metrics UnblendedCost --filter '{"And":[{"Dimensions":{"Key":"SERVICE","Values":["Amazon Bedrock","Claude Haiku 4.5 (Amazon Bedrock Edition)","Claude Sonnet 4.6 (Amazon Bedrock Edition)","Cohere Rerank v3.5 (Amazon Bedrock Edition)"]}},{"Dimensions":{"Key":"USAGE_TYPE","Values":["USE1-MP:USE1_InputTokenCount-Units","USE1-MP:USE1_OutputTokenCount-Units","USE1-MP:USE1_search_units-Units","USE1-TitanEmbeddingV2-Text-input-tokens"]}}]}' --query 'ResultsByTime[0].Total.UnblendedCost.Amount' --output text
unset ACCOUNT_ID
```
Success looks like a limit of `100.0`; four notices, `ACTUAL GREATER_THAN 50.0 ABSOLUTE_VALUE`, the
same at `80.0` and `100.0`, and `FORECASTED GREATER_THAN 100.0 ABSOLUTE_VALUE`; and an actual spend
**above zero** that agrees with Cost Explorer's figure to the cent (the budget's may run a little
ahead, since it can include part of today). An actual spend of `0.0` while Cost Explorer's figure is
above zero means AWS Budgets does not match the filter the way Cost Explorer does: stop and send the
output to the PM. Both at zero means no model call has been billed this month yet: read again after
one has. Record the figures in the task's report.

## Recurring checks

| When | What |
|---|---|
| Monthly | Budget emails arrived and the figures look like the work actually done |
| Monthly | `aws iam get-account-summary` still shows `AccountAccessKeysPresent = 0` |
| Quarterly | Identity Center users still match the adult maintainers; remove anyone who left |
| Quarterly | Every `debate-*` resource still carries `Project` and `Environment` tags — with no account boundary, an untagged resource is outside the environment separation |
| Quarterly | No non-debate resource in the account carries an `Environment` tag. The per-environment budgets filter on `Environment` alone, because AWS Budgets ORs values within a filter key and cannot AND two tag filters |
| After any apply | `terraform plan` reports no changes. A resource that always wants replacing (the cost anomaly monitor did) never accumulates the history it needs to work |
| When E05 lands | Recheck the ADR-0010 Bedrock table against the real ModelRouter routing config |
| After a new model's first billed call | Re-run [the counts](#counting-what-model-calls-are-billed-under) and add its service and usage types to the model spend budget's filter: until then the budget does not see that model |
| Before outside student data | Revisit the single-account decision ([ADR-0010](../adr/0010-primary-aws-region.md) revisit trigger) |

## What this baseline deliberately does not do

Owned by later tasks, not here:

- Remote Terraform state and the `envs/dev` + `envs/prod` roots — `v1-e29-t02-terraform-bootstrap`.
- Evidence buckets, the evidence KMS key, and the least-privilege operator permission set that
  `debate-prod` will eventually use — `v1-e29-t03-evidence-buckets`.
- GitHub OIDC deploy roles — `v2-e10-t03`. Until they exist, CI never touches AWS.
- V2 KMS/Secrets Manager (`v2-e10-t04`) and networking (`v2-e10-t05`).

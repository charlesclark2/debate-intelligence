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
| Cost | Per-environment monthly budgets, a Bedrock budget, and a Cost Anomaly Detection monitor |
| CLI profiles | `debate-dev` and `debate-prod`, used by `debate-research store` (`v1-e29-t05`) |

Terraform for this baseline lives in
[`infrastructure/bootstrap/organization/`](../../infrastructure/bootstrap/organization/). It keeps
**local state**: it runs before the remote state bucket exists, which is
`v1-e29-t02-terraform-bootstrap`'s job. See that directory's README for how the state file is
handled.

Students never receive AWS console, CLI or IAM access of any kind. Some are minors
([architecture proposal §14](../architecture/architecture_proposal.md#14-security-privacy-and-student-safety)).

## Before you start

You need:

- Administrator access to the Organization's management account, through Identity Center.
- The AWS CLI v2 and Terraform ≥ 1.7 (`aws --version`, `terraform version`).
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

```bash
cd infrastructure/bootstrap/organization
cp terraform.tfvars.example terraform.tfvars
$EDITOR terraform.tfvars        # gitignored; holds your emails and Identity Center user names
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
shared resources. Confirm the deny is real rather than assumed - **both of these must fail**:

```bash
aws s3 ls s3://debate-shared-cloudtrail-<account-id>/ --profile debate-dev
aws s3api get-bucket-versioning --bucket debate-shared-cloudtrail-<account-id> --profile debate-dev
```

Each must return `AccessDenied ... with an explicit deny in an identity-based policy`. A success
here means the boundary is gone and the fallback's premise no longer holds: stop and fix the
permission set before putting evidence in the account. Re-run this check after
`v1-e29-t03-evidence-buckets` lands, against the prod evidence bucket.

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

## Recurring checks

| When | What |
|---|---|
| Monthly | Budget emails arrived and the figures look like the work actually done |
| Monthly | `aws iam get-account-summary` still shows `AccountAccessKeysPresent = 0` |
| Quarterly | Identity Center users still match the adult maintainers; remove anyone who left |
| Quarterly | Every `debate-*` resource still carries `Project` and `Environment` tags — with no account boundary, an untagged resource is outside the environment separation |
| When E05 lands | Recheck the ADR-0010 Bedrock table against the real ModelRouter routing config |
| Before outside student data | Revisit the single-account decision ([ADR-0010](../adr/0010-primary-aws-region.md) revisit trigger) |

## What this baseline deliberately does not do

Owned by later tasks, not here:

- Remote Terraform state and the `envs/dev` + `envs/prod` roots — `v1-e29-t02-terraform-bootstrap`.
- Evidence buckets, the evidence KMS key, and the least-privilege operator permission set that
  `debate-prod` will eventually use — `v1-e29-t03-evidence-buckets`.
- GitHub OIDC deploy roles — `v2-e10-t03`. Until they exist, CI never touches AWS.
- V2 KMS/Secrets Manager (`v2-e10-t04`) and networking (`v2-e10-t05`).

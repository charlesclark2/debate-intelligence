# Session report: v1-e29-t01-aws-account-baseline

| | |
|---|---|
| Task | `v1-e29-t01-aws-account-baseline` — AWS account baseline |
| Spec | [`plan_specs/v1/e29-cloud-evidence-store/t01-aws-account-baseline.yaml`](../../plan_specs/v1/e29-cloud-evidence-store/t01-aws-account-baseline.yaml) |
| Epic / release | `v1-e29-cloud-evidence-store` / `v1.1` |
| Branch | `task/v1-e29-t01-aws-account-baseline` |
| Session status | PARTIAL — code, ADR and runbook complete; the operator apply and its verifications have not run |

## Summary

The baseline is written and verified as far as a session can take it: ADR-0010 is Accepted,
`infrastructure/bootstrap/organization/` holds the permission sets, organization CloudTrail and
cost guardrails, and the runbook covers the manual steps and the `debate-dev` / `debate-prod` SSO
profiles that t03–t05 depend on. `terraform validate` passes and a read-only `terraform plan`
against the real account resolves cleanly to 25 resources, so the configuration is known-good
against the live API rather than only syntactically valid.

Two things the PM should look at first.

**The account is not a blank slate, and the operator chose the single-account fallback.** There
is already an Organization whose sole account is its own management account, running three
unrelated personal projects, with Identity Center enabled. Asked before planning (per the PM
note), Charlie chose environment separation by tag inside that account rather than separate dev
and prod member accounts. The spec permits this "only if recorded in ADR-0010 with strict
environment tagging", so ADR-0010 records it as a decision with five binding rules and a revisit
trigger, and `DebateMaintainer` carries explicit denies on everything named or tagged prod so the
boundary is policy, not convention. I flagged the isolation cost to Charlie before building it.

**The account currently violates a forbidden-list item.** The `default` AWS CLI profile
authenticates as the **root user** with long-lived access keys
(`AccountAccessKeysPresent = 1`). The spec forbids root access keys outright and ac2 requires
root to have none. Charlie's decision was to handle this as an operator hand-off; it is step 1 of
the runbook and the first Operator follow-up below. **ac2 does not pass until it is done.**

Nothing was applied to AWS. Every AWS call this session made was read-only (`describe`, `list`,
`get`, and `terraform plan`, which creates nothing).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `region-adr` | Done | [ADR-0010](../adr/0010-primary-aws-region.md) Accepted. Region `us-east-1`. Availability table built from live `bedrock list-foundation-models` / `list-inference-profiles` output, not from memory. |
| `org-and-identity` | Done (code) / blocked (operator) | `main.tf` + `identity.tf`; `terraform validate` passes. The custom criterion (root MFA, no root keys) currently **fails** — see Operator follow-ups. |
| `cloudtrail` | Done (code) | `cloudtrail.tf`: organization-wide, multi-region, log-file validation, KMS-encrypted private versioned bucket. Not yet applied. |
| `budgets` | Done (code) | `budgets.tf`: per-environment budgets, a Bedrock budget, anomaly monitor and subscription. Not yet applied. |
| `runbook` | Done (code) / blocked (operator) | [`docs/runbooks/aws-account-baseline.md`](../runbooks/aws-account-baseline.md). The custom criterion (operator walkthrough, test budget alert) is pending. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 — ADR-0010 Accepted, Bedrock availability table for every §10 model, S3 + OpenSearch Serverless availability and price notes | PASS | `docs/adr/0010-primary-aws-region.md`, Status `Accepted`. Availability from `aws bedrock list-foundation-models` and `list-inference-profiles` across us-east-1/us-east-2/us-west-2. Prices from `aws pricing get-products` (`AmazonS3`: $0.023/GB-mo both regions; `AmazonES`: $0.24/OCU-hour both regions). Bedrock per-token rates could not be retrieved — see Deviations. |
| ac2 — dev/prod accounts (or ADR-approved alternative) exist; root has MFA and no access keys; humans sign in only through Identity Center | **FAIL** | Single-account alternative is ADR-approved (ADR-0010). Root MFA is on: `aws iam get-account-summary` → `AccountMFAEnabled: 1`. But `AccountAccessKeysPresent: 1` — **root access keys exist and are in use as the `default` CLI profile**. Also one IAM user (`baseball-access-user`) holds an active key. Operator follow-up 1. |
| ac3 — organization-wide, multi-region CloudTrail into a private, versioned, encrypted bucket with log-file validation | NOT RUN | Defined and plan-verified (`aws_cloudtrail.organization`: `is_organization_trail`, `is_multi_region_trail`, `enable_log_file_validation` all `true`), but no trail exists yet: `aws cloudtrail describe-trails` → `trailList: []`. Needs operator follow-ups 2 and 3. |
| ac4 — per-account budgets with 50/80/100% alerts against a documented cap, a Cost Anomaly Detection monitor, notifying Charlie; a test alert was received | NOT RUN | Three budgets and the monitor are defined and plan-verified. None exist yet, and no test alert has been received. Needs operator follow-ups 3 and 4. |
| ac5 — runbook reproduces the baseline, lists every manual step, shows the SSO CLI profile setup | PASS (document) / pending walkthrough | [`docs/runbooks/aws-account-baseline.md`](../runbooks/aws-account-baseline.md) covers root lockdown, CloudTrail trusted access, Identity Center MFA, cost allocation tags, the apply, `aws configure sso` for `debate-dev`/`debate-prod`, verification commands and Bedrock model access. The operator walkthrough itself is follow-up 5. |
| node `org-and-identity` — Organization bootstrap Terraform validates | PASS | `terraform -chdir=infrastructure/bootstrap/organization validate` → `Success! The configuration is valid.` |
| node `org-and-identity` — Root MFA and no root access keys confirmed | **FAIL** | As ac2. |
| node `cloudtrail` — CloudTrail definition enables log-file validation | PASS | `grep -n "enable_log_file_validation = true" infrastructure/bootstrap/organization/cloudtrail.tf` → line 300. See the note in Decisions about `terraform fmt`. |
| node `budgets` — Budgets are defined in Terraform | PASS | `grep -c "aws_budgets_budget" infrastructure/bootstrap/organization/budgets.tf` → 2 resources (`environment_monthly` for_each over dev/prod, `bedrock_monthly`). |
| node `runbook` — Runbook exists and documents SSO profiles | PASS | `grep -n "aws configure sso" docs/runbooks/aws-account-baseline.md` → line 158. |
| node `runbook` — Operator walkthrough of the baseline | NOT RUN | Follow-up 5. |
| Spec validation | PASS | `uv run scripts/validate_specs.py` → `OK: 261 files, 35 epics, 207 tasks, 19 releases`. |

Beyond the required criteria, a read-only `terraform plan` against the live account returned
`Plan: 25 to add, 0 to change, 0 to destroy` with no errors, which confirms the data sources,
the Identity Center user lookup, the budget cost filters and the anomaly `threshold_expression`
are all accepted by the real API. `terraform plan` is not on this task's forbidden list (only
`apply` is), and it creates nothing.

## Files changed

**`docs/adr/`** — [ADR-0010](../adr/0010-primary-aws-region.md) records the region and the
single-account fallback; `README.md` moves 0010 from Reserved to the index.

**`docs/runbooks/`** — new directory. `aws-account-baseline.md` is the reproduction procedure and
the home of every manual step.

**`infrastructure/bootstrap/organization/`** — new Terraform root. `versions.tf` (pins and
`default_tags`), `variables.tf`, `main.tf` (data sources, naming locals, pre-apply check),
`identity.tf` (three permission sets and the prod-denial policy), `cloudtrail.tf` (trail, KMS key,
log bucket), `budgets.tf`, `outputs.tf`, `terraform.tfvars.example`, `README.md`, and the provider
lock file.

**Indexes and ignores** — `docs/README.md` gains a `runbooks/` row; `infrastructure/README.md`
was stale (it described `dev/stage/prod` for V2, which ADR-0013 superseded) and now describes the
two-environment, us-east-1 layout; `.gitignore` excludes `infrastructure/bootstrap/**/terraform.tfvars`
so operator-local account ids and emails cannot be committed.

## Deviations from the spec

1. **Single account instead of dev and prod member accounts.** The spec's primary path is two
   member accounts, with a single-account fallback "allowed only if recorded in ADR-0010 with
   strict environment tagging". Charlie chose the fallback when asked before planning. ADR-0010
   records it with five binding rules (tags, name prefixes, permission-set separation, a policy
   deny on prod from dev-scoped credentials, and isolation from the account's other projects) and
   a revisit trigger: split prod into its own account before the platform holds data for students
   outside Charlie's own team, or when a second maintainer needs standing access. I raised the
   isolation cost — prod student evidence sharing an account with three unrelated projects — before
   building it.

2. **ADR-0010's Bedrock table is built from the §10 model list, not the ModelRouter routing
   config.** Per the PM note, `config/model-routing` does not exist until E05 (v1.2), so the
   §10 table in the architecture proposal is the model list. The ADR says so, and the runbook's
   recurring-checks table carries "when E05 lands, recheck the ADR-0010 Bedrock table".

3. **No Bedrock price comparison in ADR-0010.** ac1 asks for price notes. S3 and OpenSearch
   Serverless are there, verified from the Price List API and identical across both candidate
   regions. The `AmazonBedrock` catalogue did not return entries for Claude Sonnet 5, Haiku 4.5 or
   Opus 5 on 2026-09-19, so rather than quote rates I could not verify, the ADR states the gap and
   why the decision does not turn on it (both surviving regions expose the identical models
   through the identical inference-profile mechanism). Confirming rates is a runbook step.

4. **CloudTrail's trusted access to the Organization is a manual step, not a resource.** Setting
   it through Terraform means managing the whole `aws_organizations_organization` resource, which
   would put an Organization shared with unrelated projects inside this root's state and within
   reach of a `terraform destroy`. It is one operator CLI command in the runbook, and a `check`
   block turns the otherwise-cryptic apply failure into a message naming that step. Verified
   working: the plan emitted exactly that message.

5. **The task Goal is left at `InProgress`, not `Succeeded`.** CLAUDE.md says to finish by setting
   the Goal to `Succeeded`, but ac2 currently **fails** (root access keys exist) and ac3/ac4
   describe resources that do not exist until the operator applies. Marking it `Succeeded` would
   misreport the state of the account. Flip it to `Succeeded` once follow-ups 1–5 are done — I can
   do that in this session when you confirm, or it can be a one-line spec change.

6. **`environment` tagging has a third value, `shared`.** ADR-0010 rule 1 requires `dev` or `prod`
   on every resource, but the organization trail, its key and bucket, the Bedrock budget and the
   anomaly monitor protect both environments and belong to neither. They are tagged
   `Environment = shared` and named `debate-shared-*`, and `DebateMaintainer` denies
   `debate-shared-*` alongside `debate-prod-*` so a dev credential cannot reach the audit trail.
   ADR-0010 states this.

## Decisions and assumptions

- **`us-east-1`.** us-east-2 is disqualified on availability (no Cohere Rerank 3.5, no substitute
  reranker). us-east-1 and us-west-2 are identical on model coverage, S3 price and OCU price, so
  the tiebreaker is that the operator's existing footprint is already in us-east-1 — which removes
  the class of mistake where a bucket or trail lands in the wrong region from an unset default.
- **Three permission sets, matching the spec's list**, named `Debate*` so they cannot collide with
  the `AdministratorAccess` set that already exists for the account's other projects. That
  pre-existing set is deliberately not managed by this root.
- **`debate-prod` maps to `DebateReadOnly` for now.** Prod writes need the least-privilege operator
  permission set that t03 owns. Until then a prod write is a deliberate break-glass action. The
  runbook says to repoint the profile when t03 lands.
- **A separate KMS key for CloudTrail**, not the evidence key t03 will create: audit logs and
  evidence have different readers, and one key would let anyone who can read evidence read the
  audit trail. Cost is about $1/month.
- **The log bucket denies `s3:DeleteObject` to everything but the account root.** This means
  `terraform destroy` of this root fails while logs exist — intentional for an audit bucket, and
  called out in both READMEs with how to retire it deliberately.
- **Budgets filter on the `Project` tag**, because the account carries unrelated spend. This makes
  activating the `Project` and `Environment` cost allocation tags a hard prerequisite: until then
  the budgets read $0 and never alert. It is a runbook step, and the test alert in follow-up 4 is
  what catches it if missed.
- **Budget sizes are guesses** — dev $25, prod $50, Bedrock $40/month — sized for S3 storage plus
  light Bedrock use. They are alert thresholds, not caps; AWS Budgets notifies and never stops
  spend. Adjust once t05 has synced real evidence volume.
- **The `contentMatch` criteria are whitespace-sensitive, and `terraform fmt` broke one.** The
  `cloudtrail` node matches the literal `enable_log_file_validation = true`, but `fmt` aligns `=`
  within a contiguous attribute block, which turned it into `enable_log_file_validation    = true`
  and silently failed the criterion. Rather than reword the spec or leave the file unformatted, the
  attribute now sits in its own alignment group behind a comment saying why — `fmt` is stable on
  it, and the criterion matches real code. Worth knowing for t02–t05, which have similar criteria.
- **No account ids, emails, org ids or Identity Center ARNs are committed anywhere.** Everything is
  a variable or a runbook placeholder, read from the account with the commands the runbook gives.

## Operator follow-ups

These are in order; 2 must precede 3.

**1. Remove the root access keys** (~5 min, blocks ac2)

Where: AWS console as root, then your Mac.

The `default` profile in `~/.aws/credentials` is authenticating as the account root user with a
long-lived key pair. Every control in this task assumes that is not true.

```bash
# before: confirm what you have
aws iam get-account-summary --query 'SummaryMap.{MFA:AccountMFAEnabled,RootKeys:AccountAccessKeysPresent}'
```

Then in the console, signed in as root: My Security Credentials → Access keys → deactivate, then
delete every root key. Afterwards remove the `[default]` block from `~/.aws/credentials`.

```bash
# after: both must be as shown
aws iam get-account-summary --query 'SummaryMap.{MFA:AccountMFAEnabled,RootKeys:AccountAccessKeysPresent}'
# → {"MFA": 1, "RootKeys": 0}
```

Separately, IAM user `baseball-access-user` holds an active access key created 2026-05-27. It
belongs to one of the other projects in this account, so it is outside this task's scope, but it
is the same class of risk — worth rotating to a role when you next touch that project.

**2. Enable CloudTrail trusted access on the Organization** (~1 min, blocks ac3)

```bash
aws organizations enable-aws-service-access --service-principal cloudtrail.amazonaws.com
aws organizations list-aws-service-access-for-organization \
  --query 'EnabledServicePrincipals[].ServicePrincipal'
```

Success: `cloudtrail.amazonaws.com` appears in the list. Without this the apply in step 3 fails,
and `terraform plan` already warns about it by name.

**3. Activate cost allocation tags, then apply the baseline** (~5 min, blocks ac3 and ac4)

First, console → Billing and Cost Management → Cost allocation tags → activate the user-defined
tags `Project` and `Environment`. No API can do this, and the budgets read $0 until it is done.

Then, in the task worktree:

```bash
cd infrastructure/bootstrap/organization
cp terraform.tfvars.example terraform.tfvars
$EDITOR terraform.tfvars   # your email, your Identity Center user name, notification email
terraform init
terraform plan -out=baseline.tfplan
terraform apply baseline.tfplan
```

Expected runtime ~2–4 minutes. Success looks like `Apply complete! Resources: 25 added, 0 changed,
0 destroyed.` Paste the last 20 lines back into the session.

Keep the resulting `terraform.tfstate` — it is local (remote state is t02's job) and losing it
means re-importing everything by hand. `terraform.tfvars` is gitignored; do not commit it.

**4. Confirm a budget alert actually arrives** (~24 h elapsed, blocks ac4)

Set `monthly_budget_usd = { dev = 1, prod = 50 }` in `terraform.tfvars`, `terraform apply`, wait
for the email (AWS evaluates several times a day; check spam), then restore the real value and
apply again. Tell me which budget the email came from and I will record it against ac4.

**5. Walk through the baseline** (~10 min, blocks ac5's custom criterion)

Follow runbook steps 3 (Identity Center MFA), 6 (`aws configure sso` for `debate-dev` and
`debate-prod`), 7 (verification commands) and 8 (Bedrock model access).

```bash
aws sso login --sso-session debate
aws sts get-caller-identity --profile debate-dev
aws sts get-caller-identity --profile debate-prod
```

Success: both return `assumed-role/AWSReservedSSO_DebateMaintainer_...` and
`.../AWSReservedSSO_DebateReadOnly_...` ARNs — never a `:root` ARN.

**6. Then flip the spec phase.** Once 1–5 pass, the Goal's `status.phase` goes to `Succeeded` and
this report's criteria table is updated with the real evidence.

## Follow-up work

- **`v1-e29-t03-evidence-buckets`** should add the least-privilege prod operator permission set
  and repoint the `debate-prod` SSO profile at it; the runbook's step 6 says so, and `DebateReadOnly`
  is a placeholder until then.
- **`v1-e29-t02-terraform-bootstrap`** should decide whether this bootstrap root migrates to the
  remote backend once one exists, and owns the `terraform-checks` CI job that will run `fmt` and
  `validate` over `infrastructure/`. Nothing in CI covers this directory yet, because no CI
  workflow exists on this branch (`v1-e01-t04-ci-pipeline` is still open).
- **Root email risk.** The Organization's management account is registered to an institutional
  address that can be revoked, which would mean losing account recovery for an account that will
  hold student data. Changing it is a manual console step outside this task. Worth a PM decision
  about whether it becomes a task.
- **IAM user `baseball-access-user`** holds a long-lived access key in the same account. Outside
  this project, but it shares the blast radius the single-account decision created.
- **Revisit the single-account decision** per ADR-0010's trigger. When it happens it is a real
  migration: an S3 bucket cannot move between accounts without copying every object and rewriting
  provenance references, so the trigger is deliberately set before prod holds outside data.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

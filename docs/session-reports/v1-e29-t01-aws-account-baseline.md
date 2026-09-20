# Session report: v1-e29-t01-aws-account-baseline

| | |
|---|---|
| Task | `v1-e29-t01-aws-account-baseline` — AWS account baseline |
| Spec | [`plan_specs/v1/e29-cloud-evidence-store/t01-aws-account-baseline.yaml`](../../plan_specs/v1/e29-cloud-evidence-store/t01-aws-account-baseline.yaml) |
| Epic / release | `v1-e29-cloud-evidence-store` / `v1.1` |
| Branch | `task/v1-e29-t01-aws-account-baseline` |
| Session status | COMPLETE — applied and verified on 2026-09-20; two operator follow-ups remain, neither blocking a criterion |

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

The baseline was applied by the operator on 2026-09-20 and verified against the live account.
`terraform plan` now reports no changes. The session itself made only read-only AWS calls
(`describe`, `list`, `get`, and `terraform plan`); every mutating command was an operator
hand-off, with one exception recorded in Deviations 9.

Planning against the applied state is what caught the substantive defects — the dev and prod
budgets measuring the same thing, and a cost anomaly monitor that would have been replaced on
every apply and so never accumulated the history it needs. Neither was visible before the apply:
`validate` passes on both and the pre-apply plan showed them as clean creates. The runbook now
requires a `plan` after every apply for that reason.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `region-adr` | Done | [ADR-0010](../adr/0010-primary-aws-region.md) Accepted. Region `us-east-1`. Availability table built from live `bedrock list-foundation-models` / `list-inference-profiles` output, not from memory. |
| `org-and-identity` | Done | `main.tf` + `identity.tf`; `terraform validate` passes and the three permission sets are live. Root is clean; the custom criterion is PARTIAL only for another project's IAM user key (Deviations 5). |
| `cloudtrail` | Done | `cloudtrail.tf`: organization-wide, multi-region, log-file validation, KMS-encrypted private versioned bucket. Applied and logging. |
| `budgets` | Done | `budgets.tf`: per-environment budgets, a Bedrock budget, anomaly monitor and subscription. Applied; filter semantics corrected after the first apply (Deviations 8). |
| `runbook` | Done | [`docs/runbooks/aws-account-baseline.md`](../runbooks/aws-account-baseline.md), executed end to end by the operator on 2026-09-20. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 — ADR-0010 Accepted, Bedrock availability table for every §10 model, S3 + OpenSearch Serverless availability and price notes | PASS | `docs/adr/0010-primary-aws-region.md`, Status `Accepted`. Availability from `aws bedrock list-foundation-models` and `list-inference-profiles` across us-east-1/us-east-2/us-west-2. Prices from `aws pricing get-products` (`AmazonS3`: $0.023/GB-mo both regions; `AmazonES`: $0.24/OCU-hour both regions). Bedrock per-token rates could not be retrieved — see Deviations. |
| ac2 — dev/prod accounts (or ADR-approved alternative) exist; root has MFA and no access keys; humans sign in only through Identity Center | PASS | Single-account alternative is ADR-approved (ADR-0010). `aws iam get-account-summary` → `{"MFA": 1, "RootKeys": 0}` (2026-09-20, after the operator deleted the root keys and removed the local `[default]` credentials). Permission sets `DebateBreakGlassAdmin` (PT1H), `DebateMaintainer` (PT8H), `DebateReadOnly` (PT4H) exist beside the pre-existing `AdministratorAccess`. Caveat: IAM user `baseball-access-user` still holds an active key — another project's, tracked under Follow-up work. The environment boundary was verified live: `debate-dev` is refused both `s3:ListBucket` and `s3:GetBucketVersioning` on `debate-shared-cloudtrail-*` with *"explicit deny in an identity-based policy"*, while `debate-prod` reads them — so ADR-0010 rule 4 is enforced, not merely declared. |
| ac3 — organization-wide, multi-region CloudTrail into a private, versioned, encrypted bucket with log-file validation | PASS | `aws cloudtrail describe-trails` → `{Org: true, Multi: true, Validation: true, Kms: arn:...key/c274276f...}`. `get-trail-status` → `{Logging: true, LastDelivery: 2026-09-20T00:11:34, LastError: null}`. Bucket `debate-shared-cloudtrail-<account-id>`: versioning `Enabled`, all four public-access blocks `true`, SSE-KMS with `BucketKeyEnabled`. |
| ac4 — per-account budgets with 50/80/100% alerts against a documented cap, a Cost Anomaly Detection monitor, notifying Charlie; a test alert was received | PASS | Budgets `debate-dev-monthly` ($25), `debate-prod-monthly` ($50), `debate-shared-bedrock-monthly` ($40) exist, each with 50/80/100% ACTUAL plus a FORECASTED alert. Monitor `debate-shared-spend-monitor` (CUSTOM) and subscription `debate-shared-spend-alerts` (DAILY) exist, subscriber `CONFIRMED`. **Test alert received 2026-09-20** via an unfiltered throwaway budget ($1 limit against $64.29 actual account spend), then removed. Caveat in Deviations 7: the three real budgets measure $0 until the cost allocation tags are active (Follow-up 1) and t03 creates dev/prod resources. |
| ac5 — runbook reproduces the baseline, lists every manual step, shows the SSO CLI profile setup | PASS | [`docs/runbooks/aws-account-baseline.md`](../runbooks/aws-account-baseline.md) covers root lockdown, CloudTrail trusted access, Identity Center MFA, the apply, cost allocation tags, `aws configure sso` for `debate-dev`/`debate-prod`, verification, the boundary simulation and Bedrock model access. The operator executed it end to end on 2026-09-20 — it is a reproduced procedure, not a reviewed document. Four defects it surfaced are in Deviations 8. |
| node `org-and-identity` — Organization bootstrap Terraform validates | PASS | `terraform -chdir=infrastructure/bootstrap/organization validate` → `Success! The configuration is valid.` |
| node `org-and-identity` — Root MFA and no root access keys confirmed | PARTIAL | Root: `{"MFA": 1, "RootKeys": 0}` — passes. The criterion also says *"no IAM users with access keys exist"*, and `baseball-access-user` still holds an `Active` key. It belongs to one of the account's other projects, outside this task's `packages` scope, and Charlie chose on 2026-09-19 to leave it and track it. Recorded as a documented exception, not a silent pass — see Follow-up work. |
| node `cloudtrail` — CloudTrail definition enables log-file validation | PASS | `grep -n "enable_log_file_validation = true" infrastructure/bootstrap/organization/cloudtrail.tf` → line 300. See the note in Decisions about `terraform fmt`. |
| node `budgets` — Budgets are defined in Terraform | PASS | `grep -c "aws_budgets_budget" infrastructure/bootstrap/organization/budgets.tf` → 2 resources (`environment_monthly` for_each over dev/prod, `bedrock_monthly`). |
| node `runbook` — Runbook exists and documents SSO profiles | PASS | `grep -n "aws configure sso" docs/runbooks/aws-account-baseline.md` → line 158. |
| node `runbook` — Operator walkthrough of the baseline | PASS | `aws sts get-caller-identity` returns `assumed-role/AWSReservedSSO_DebateMaintainer_.../ccl1196` for `debate-dev` and `.../AWSReservedSSO_DebateReadOnly_...` for `debate-prod`; budget alert email received 2026-09-20. Bedrock access additionally proven by a live `invoke-model` against `us.anthropic.claude-haiku-4-5-20251001-v1:0` returning a completion (8 in / 5 out tokens) — the listings alone do not show whether model access is granted. |
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

5. **One node criterion is only partly met, by the operator's decision.** `org-and-identity`'s
   custom criterion ends *"and that no IAM users with access keys exist"*. Root is clean, but the
   IAM user `baseball-access-user` still holds an active key from 2026-05-27. It belongs to one of
   the three unrelated projects sharing this account and sits outside this task's `packages`
   scope, so Charlie chose to leave it and track it rather than touch another project's
   credentials from this task. Recorded here rather than quietly passed: in a single-account
   setup, a long-lived key in the same account is inside the blast radius the fallback created.

6. **`environment` tagging has a third value, `shared`.** ADR-0010 rule 1 requires `dev` or `prod`
   on every resource, but the organization trail, its key and bucket, the Bedrock budget and the
   anomaly monitor protect both environments and belong to neither. They are tagged
   `Environment = shared` and named `debate-shared-*`, and `DebateMaintainer` denies
   `debate-shared-*` alongside `debate-prod-*` so a dev credential cannot reach the audit trail.
   ADR-0010 states this.

8. **Three defects found by planning against the applied state, fixed in a follow-up apply.**
   `terraform plan` after the operator's apply was not clean, and each difference was a real bug
   rather than drift:

   - **The dev and prod budgets measured the same thing.** AWS Budgets stores every `TagKeyValue`
     filter under one key and ORs the values, so two `cost_filter` blocks collapsed into
     `Environment=dev OR Project=debate-intelligence` — widening each budget to all debate spend
     instead of narrowing it to one environment. The legacy `CostFilters` API cannot AND two tag
     filters and the provider exposes no `filter_expression`, so the per-environment budgets now
     filter on `Environment` alone. If another project in this account ever adopts an `Environment`
     tag these over-count and alert early, which is the safe direction; the runbook's quarterly
     tag check is where that surfaces. The Bedrock budget keeps both filters because `Service` and
     `TagKeyValue` are different keys and those *are* AND'd.
   - **The cost anomaly monitor was replaced on every plan.** Cost Explorer stores user-defined tag
     keys as `user:<key>` and returns every unused expression member explicitly, while the config
     sent a bare `Project` and omitted the nulls. The provider compares the encoded JSON as a
     string, so it never matched. Replacing the monitor discards the roughly ten days of history
     Cost Anomaly Detection needs before it can detect anything, so this would have kept the
     monitor permanently useless.
   - **`DenyTamperingWithGuardrails` denied reads, not just tampering.** `sso:*`,
     `organizations:*` and `sso-directory:*` blocked `list-permission-sets`,
     `describe-organization` and `list-users` from `debate-dev`. Narrowed to mutating actions.
     The point is not convenience: the denies that matter are the ones separating dev from prod,
     and `AccessDenied` during ordinary work trains the operator to wave the next one through.

   Applied by the operator on 2026-09-20: `0 added, 3 changed, 0 destroyed`, after which
   `terraform plan` reports **no changes** — the first point at which the configuration and the
   account actually agree. `debate-dev-monthly` now filters on `user:Environment$dev` alone.

   Re-verified after the policy change, with `iam simulate-principal-policy` so nothing is
   actually attempted: `s3:ListBucket`, `s3:GetObject`, `s3:PutObject` on the shared bucket,
   `cloudtrail:StopLogging`, `cloudtrail:DeleteTrail`, `sso:CreateAccountAssignment`,
   `iam:CreateAccessKey`, `budgets:DeleteBudget` and `budgets:ModifyBudget` all return
   `explicitDeny` for `DebateMaintainer`, while `describe-organization`, `list-permission-sets`
   and `list-users` now succeed. The boundary held; only the reads widened.

7. **ac4's test alert cannot use the real budgets yet, so the runbook tests the delivery path
   instead.** All three budgets filter on `Environment` = `dev`/`prod` or on Bedrock usage, and the
   only tagged resources the baseline creates are the trail's bucket and key, tagged
   `Environment = shared`. Until `v1-e29-t03-evidence-buckets` creates dev and prod resources the
   budgets correctly measure $0, so lowering a threshold fires nothing — my first version of this
   step would not have worked. The runbook now proves email delivery with a throwaway unfiltered
   budget created outside Terraform, and says to re-test the real budgets against live spend once
   t03/t05 have put evidence in the dev bucket.

9. **I verified two denies by attempting them, which was the wrong method.** Checking that the
   narrowed policy still blocked tampering, I invoked `cloudtrail:StopLogging` and
   `budgets:DeleteBudget` from `debate-dev`. Both were refused — the organization trail records
   the `DeleteBudget` AccessDenied at `2026-09-20T05:49:19Z` against user `ccl1196` — so nothing
   changed. But had the deny been broken, the test itself would have stopped the audit trail or
   deleted a budget. `iam simulate-principal-policy` evaluates the same policies with no side
   effects and is what the runbook now specifies; the re-verification after the policy change used
   it for all nine actions.

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
  activating the `Project` and `Environment` cost allocation tags mandatory: until then the budgets
  read $0 and never alert. It cannot be done up front — a tag key is only activatable once AWS has
  seen a resource carrying it — so it is a post-apply runbook step, and the test alert in follow-up
  5 is what catches it if missed.
- **Budget sizes are guesses** — dev $25, prod $50, Bedrock $40/month — sized for S3 storage plus
  light Bedrock use. They are alert thresholds, not caps; AWS Budgets notifies and never stops
  spend. Adjust once t05 has synced real evidence volume.
- **Deny checks use `iam simulate-principal-policy`, not real calls.** I first verified the
  tampering denies by actually invoking `cloudtrail:StopLogging` and `budgets:DeleteBudget` from
  `debate-dev`. They were refused, so nothing happened — but had the deny been broken, the test
  would have stopped the audit trail or deleted a budget. The simulator evaluates the same
  policies with no side effects, and that is what the runbook now specifies. Budgets actions need
  their own simulate call; the API refuses to mix authorization contexts.
- **Verification commands have to pick the right profile, and my first draft did not.** Step 7
  originally ran the audit-bucket checks under `debate-dev`, which `DebateMaintainer` denies by
  design; the operator hit three `AccessDenied` errors. They now run under `debate-prod`
  (`DebateReadOnly`), and step 7 gained an explicit boundary check that *asserts* `debate-dev` is
  refused — a deny that stops failing is the signal that the single-account fallback has quietly
  lost its premise, so it is worth testing on purpose rather than discovering by accident.
- **The `contentMatch` criteria are whitespace-sensitive, and `terraform fmt` broke one.** The
  `cloudtrail` node matches the literal `enable_log_file_validation = true`, but `fmt` aligns `=`
  within a contiguous attribute block, which turned it into `enable_log_file_validation    = true`
  and silently failed the criterion. Rather than reword the spec or leave the file unformatted, the
  attribute now sits in its own alignment group behind a comment saying why — `fmt` is stable on
  it, and the criterion matches real code. Worth knowing for t02–t05, which have similar criteria.
- **No account ids, emails, org ids or Identity Center ARNs are committed anywhere.** Everything is
  a variable or a runbook placeholder, read from the account with the commands the runbook gives.

## Operator follow-ups

Steps 1-9 of the runbook were completed by the operator on 2026-09-20: root keys deleted,
CloudTrail trusted access enabled, Identity Center MFA configured, the baseline applied, SSO
profiles created, the baseline verified, Bedrock access confirmed by live invocation, and a budget
alert email received. Two items remain. Neither blocks a Goal criterion.

**1. Activate the `Project` and `Environment` cost allocation tags** (~1 min, once AWS surfaces them)

**The three budgets measure $0 until this is done.** They exist and alert correctly - the delivery
path is proven - but with the tags inactive they have nothing to measure, so they will never fire
on real spend. A tag key only becomes activatable after AWS has seen a resource carrying it, which
is why it could not be done before the apply; as of 2026-09-20 they had not yet surfaced.

```bash
aws ce list-cost-allocation-tags \
  --query 'CostAllocationTags[?TagKey==`Project` || TagKey==`Environment`].[TagKey,Status]' \
  --output text
aws ce update-cost-allocation-tags-status --cost-allocation-tags-status \
  TagKey=Project,Status=Active TagKey=Environment,Status=Active
```

Both must read `Active`. If they have not appeared within 48 hours of the apply, that is worth
investigating rather than waiting on - it would mean no billed usage is being attributed to the
tagged resources.

**2. Delete the alert-delivery test budget** (~10 seconds)

Created outside Terraform, so it never entered state, but it will keep emailing until removed.

```bash
aws budgets delete-budget --account-id <account-id> --budget-name debate-alert-delivery-test
```

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
- **IAM user `baseball-access-user`** holds an active long-lived access key (created 2026-05-27)
  in the same account. Outside this project, but it shares the blast radius the single-account
  decision created, and it is the one part of the `org-and-identity` node criterion left unmet
  (Deviations 5). Worth a decision from the PM: either migrate it to a role and delete the key, or
  record it as an accepted exception in ADR-0010.
- **The budgets are inert until the cost allocation tags are active.** They alert correctly — the
  delivery path is proven — but measure $0 until Operator follow-up 1 completes, and will only
  measure anything meaningful once t03 and t05 put evidence in the dev bucket. Worth re-testing
  the real budgets against live spend at that point rather than assuming they work.
- **Revisit the single-account decision** per ADR-0010's trigger. When it happens it is a real
  migration: an S3 bucket cannot move between accounts without copying every object and rewriting
  provenance references, so the trigger is deliberately set before prod holds outside data.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

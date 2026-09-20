# Account baseline bootstrap

Identity, audit and cost guardrails for the account the Debate Intelligence Platform runs in.
Spec: [`v1-e29-t01-aws-account-baseline`](../../../plan_specs/v1/e29-cloud-evidence-store/t01-aws-account-baseline.yaml).
Decision: [ADR-0010](../../../docs/adr/0010-primary-aws-region.md).
How to run it: [docs/runbooks/aws-account-baseline.md](../../../docs/runbooks/aws-account-baseline.md).

| File | What it defines |
|---|---|
| `versions.tf` | Terraform and provider pins, and the `default_tags` every resource inherits |
| `variables.tf` | Inputs; the real values live in a gitignored `terraform.tfvars` |
| `main.tf` | Data sources for the existing Organization and Identity Center instance, naming locals, pre-apply checks |
| `identity.tf` | The three permission sets, their policies, and account assignments |
| `cloudtrail.tf` | Organization trail, its KMS key, and its log bucket |
| `budgets.tf` | Per-environment budgets, the Bedrock budget, cost anomaly detection |

## Operator-only

`terraform apply` here is an operator step. CI never runs plan or apply against this root, and
neither does an agent session — there are no OIDC deploy roles until `v2-e10-t03`, and this root
holds the controls that would be used to grant them.

## Why local state

This root runs *before* the remote state bucket exists; creating that bucket is
`v1-e29-t02-terraform-bootstrap`. So `terraform.tfstate` is a local file, excluded by
`.gitignore` along with every other `*.tfstate`.

That state is worth keeping: losing it means re-importing the permission sets, the trail and the
budgets by hand. Back it up somewhere durable after each apply — it contains resource ids and
policy documents, no secrets, but treat it as sensitive anyway. `v1-e29-t02-terraform-bootstrap`
decides whether this root migrates to the remote backend once one exists.

## What is deliberately not managed here

The Organization and the IAM Identity Center instance predate this project and are read through
data sources, never adopted as resources. Both are shared with unrelated projects in the same
account, and a `terraform destroy` in this root must not be able to reach them. For the same
reason the pre-existing `AdministratorAccess` permission set is left alone; this root adds its
own `Debate*` sets beside it.

Enabling CloudTrail's trusted access to the Organization is likewise a one-line operator command
rather than a resource, for the same reason. A `check` block in `main.tf` turns the resulting
apply failure into a readable message pointing at the runbook step.

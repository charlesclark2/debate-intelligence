# infrastructure

Terraform for the platform's AWS resources. Applies are operator-run; CI only runs `fmt` and
`validate` (see [working agreements](../docs/process/working-agreements.md)).

There are exactly two environments, `dev` and `prod` ([ADR-0013](../docs/adr/0013-two-environments-and-dev-main-promotion.md)),
both in `us-east-1` ([ADR-0010](../docs/adr/0010-primary-aws-region.md)). ADR-0010 also records
that they are separated by tag and resource name inside one account rather than by an account
boundary, and the rules that keeps binding.

| Directory | What | Owning spec |
|---|---|---|
| [`bootstrap/organization/`](bootstrap/organization/) | Identity Center permission sets, organization CloudTrail, budgets and cost anomaly detection | `v1-e29-t01-aws-account-baseline` |

Added by later tasks: `bootstrap/state/` (remote state), `modules/` and `envs/{dev,prod}/`
(`v1-e29-t02-terraform-bootstrap`), then the evidence buckets in `v1-e29-t03-evidence-buckets`.

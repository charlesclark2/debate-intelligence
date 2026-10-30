# `model_spend_budget` module

The account's model spend budget, `debate-shared-bedrock-monthly`, held to the coach's ceiling. Spec:
[`v1-e05-t16-bedrock-budget-alarm`](../../../plan_specs/v1/e05-model-router/t16-bedrock-budget-alarm.yaml).
Operator steps: [docs/runbooks/aws-account-baseline.md](../../../docs/runbooks/aws-account-baseline.md#the-model-spend-budget).

Called once, from [`bootstrap/organization`](../../bootstrap/organization/budgets.tf): AWS Budgets
are account-wide, and dev and prod share one account (ADR-0010). A `moved` block there carries the
budget `v1-e29-t01` created into this module, so it is updated in place under its old name.

## What it creates

One `aws_budgets_budget`, and nothing else; `tests/infrastructure/test_model_spend_budget_grants_nothing.py`
holds that.

| | |
|---|---|
| Limit | 100 USD a month: the ceiling across dev and prod, $50 in each profile, on the condition that model work is never duplicated between them |
| Notices | Actual spend above $50, $80 and $100; forecast spend above $100. In dollars, by email to `notification_emails` (the coach's address, from the root's gitignored `terraform.tfvars`) |
| Filter | Service AND usage type, below |

AWS Budgets notifies; it never stops spend. What refuses a call is `models.budget_usd_monthly`
(`v1-e05-t15`), from the usage log.

## The filter

Read from Cost Explorer by the operator on 2026-10-29. Claude and Cohere models bill as AWS
Marketplace services named after the model; Titan bills under Amazon Bedrock.

| Service | Usage types |
|---|---|
| `Claude Haiku 4.5 (Amazon Bedrock Edition)`, `Claude Sonnet 4.6 (Amazon Bedrock Edition)` | `USE1-MP:USE1_InputTokenCount-Units`, `USE1-MP:USE1_OutputTokenCount-Units` |
| `Cohere Rerank v3.5 (Amazon Bedrock Edition)` | `USE1-MP:USE1_search_units-Units` |
| `Amazon Bedrock` | `USE1-TitanEmbeddingV2-Text-input-tokens` |

AWS Budgets ORs the values inside one filter key and ANDs different keys, so a charge counts when its
service is one of the four and its usage type one of the four. The usage type is what leaves out
other Amazon Bedrock spend in the account that is not this project's. There is no `Project` tag in
the filter: model charges carry none, and with one the budget would read $0.

**A model never billed has no name here.** A new model (the 5.5 models of prod's routes, through
`v1-e05-t17`) is added after its first billed call: re-run the counts in the runbook, add the names
to `local.model_services` and `local.model_usage_types`, and to the test's hand-written lists.

# `bedrock_access` module

The permission set one environment's model calls are made with, `Debate<Env>BedrockInvoker`, and
its account assignment. Spec:
[`v1-e05-t08-bedrock-invoke-access`](../../../plan_specs/v1/e05-model-router/t08-bedrock-invoke-access.yaml).
Decision: [ADR-0005](../../../docs/adr/0005-bedrock-behind-model-router.md) and the region pin of
[ADR-0010](../../../docs/adr/0010-primary-aws-region.md). Operator steps:
[docs/runbooks/bedrock-access.md](../../../docs/runbooks/bedrock-access.md).

Called once from [`envs/dev`](../../envs/dev/bedrock_access.tf) and once from
[`envs/prod`](../../envs/prod/bedrock_access.tf), with the same arguments. It holds no account id
and no model identifier: the account comes from the provider, and every identifier from the routing
files it is given.

## What it creates

| Resource | What it is |
|---|---|
| `aws_ssoadmin_permission_set.invoker` | `DebateDevBedrockInvoker` / `DebateProdBedrockInvoker`, eight-hour sessions |
| `aws_ssoadmin_permission_set_inline_policy.invoker` | `bedrock:InvokeModel` only, in at most three statements (below) |
| `aws_ssoadmin_account_assignment.invokers` | One per name in `invoker_user_names`, from the gitignored `owner.auto.tfvars` |

Nothing exists without an Identity Center instance (`identity_center_instance_arn = null`), which is
how the module stays testable.

## What the set may call

Read from `routing_files`, which both roots set to `config/model_routing.dev.yaml` and
`config/model_routing.prod.yaml`:

| Statement | Resources | Condition |
|---|---|---|
| `InvokeTheRoutedInferenceProfiles` | Each route's inference profile in the route's region: today prod's `us.anthropic.claude-{haiku,sonnet,opus}-5-5` and dev's `us.anthropic.claude-haiku-4-5-20251001-v1:0` and `us.anthropic.claude-sonnet-4-6` (while the account's 5.5 quotas are held at zero, `v1-e05-t13`) in us-east-1 | none: it is what a call names |
| `InvokeTheModelsBehindTheProfilesThroughThemOnly` | The model behind each profile in us-east-1, us-east-2 and us-west-2, the regions a `us.` profile sends calls to | `bedrock:InferenceProfileArn` equals one of the profiles above |
| `InvokeTheModelsRoutedWithoutAProfile` | Each route with no profile, on its model in its region: Titan Text Embeddings V2 and Cohere Rerank 3.5 in us-east-1 | none |

A routing file that names a profile of another geography is refused by a validation, because the
regions behind a profile are written in the module for `us.` alone. A statement with nothing to grant
is left out, since IAM refuses an empty one.

**A routing change is a grant change.** A new model or profile in either routing file shows up in the
next plan of both roots as an update to the inline policy, and the module's tests, which pin the
twenty-two resources the committed files name (five profiles, the five Claude models behind them in
three regions, and the two scoring models), fail until they are updated with it.

## Tests

```bash
terraform -chdir=infrastructure/modules/bedrock_access init -backend=false
terraform -chdir=infrastructure/modules/bedrock_access test
```

Offline, under `mock_provider "aws"`, against the committed routing files and two synthetic ones in
`tests/routing_files/`.

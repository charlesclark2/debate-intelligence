<!-- docs-index: Calling the routed Bedrock models: the BedrockInvoker permission set's plan and apply, its SSO profile, the account's one-time model access, the data-use checks, the first real call and zero-retention mode -->
# Runbook: calling the routed Bedrock models

How a model call gets a credential: the `Debate<Env>BedrockInvoker` permission set and its account
assignment (Terraform), the SSO profile `models.aws_profile` names, the account's one-time model
access (not Terraform), the two data-use checks the policy's open question 4 needs, the first
real call on each Claude route, and the account's zero-retention mode in the three regions. Spec:
[`v1-e05-t08-bedrock-invoke-access`](../../plan_specs/v1/e05-model-router/t08-bedrock-invoke-access.yaml).
Module: [`infrastructure/modules/bedrock_access`](../../infrastructure/modules/bedrock_access/README.md).
Decisions: [ADR-0005](../adr/0005-bedrock-behind-model-router.md),
[ADR-0010](../adr/0010-primary-aws-region.md).

Written for the adult maintainer with administrator access to the account. **Every step here is run
by a human.** CI has no AWS credentials, and an agent session never applies or calls AWS. The PM reads
each plan before its apply.

## What this sets up

| | dev | prod |
|---|---|---|
| Permission set | `DebateDevBedrockInvoker` | `DebateProdBedrockInvoker` |
| Its SSO profile, `models.aws_profile` in `config/profiles/<env>.toml` | `debate-dev-bedrock` | `debate-prod-bedrock` |
| What it may do | `bedrock:InvokeModel`, nothing else | the same |

**What it may call** is read from `config/model_routing.dev.yaml` and `config/model_routing.prod.yaml`
by both roots, so both sets grant the same twenty-two resources:

* the five `us.` inference profiles in us-east-1: prod's `us.anthropic.claude-haiku-5-5`,
  `us.anthropic.claude-sonnet-5-5` and `us.anthropic.claude-opus-5-5`, and dev's
  `us.anthropic.claude-haiku-4-5-20251001-v1:0` and `us.anthropic.claude-sonnet-4-6`, which dev routes
  to while the account's 5.5 quotas are held at zero (`v1-e05-t13`);
* the five Claude models behind them, in us-east-1, us-east-2 and us-west-2, and only through those
  profiles (the condition `bedrock:InferenceProfileArn`);
* `amazon.titan-embed-text-v2:0` and `cohere.rerank-v3-5:0` in us-east-1.

When dev goes back to the 5.5 models, the grant shrinks to the fourteen resources of prod's three
profiles again, and the counts below change with it.

**Every Bedrock call is signed with `models.aws_profile`, never with `AWS_PROFILE`.** The client
reads no profile from the environment, so a shell left holding `debate-dev-evidence`, or the other
environment's profile, cannot decide which role a model call runs as.
`debate-research doctor --evidence-profiles` reports the profile on a `Model profile` row, in the same
words as the evidence profiles, and never fails on it.

**The order.** Dev: plan, the PM's word, apply, the profile, the account's model access, the data-use
checks, the first call. Prod: plan and apply after the release carrying this task is promoted to
`main` ([Prod](#prod)). In dev the apply comes after the caselist cutover's step 9
([caselist-cutover.md](caselist-cutover.md)), from the same worktree, so its plan holds this task's
resources alone.

## Before you start

**Shell variables**, used by every block below, and the check that the worktree is `origin/dev` with
this task merged and the cutover's step 9 applied. `SSO_USER_NAME` is your Identity Center user name.

```bash
WT="$HOME/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/caselist-credentials-dev"
ENVIRONMENT=dev
SSO_USER_NAME='your-identity-center-user-name'

cd "$WT" || echo "STOP: the worktree is missing: $WT"
git fetch origin
git switch --detach origin/dev
test -f infrastructure/envs/dev/bedrock_access.tf && echo "ok: $(pwd) at origin/dev $(git rev-parse --short HEAD), bedrock_access merged" || echo "NOT MERGED: origin/dev has no v1-e05-t08"
git status --porcelain | grep -v 'owner.auto.tfvars' | head -3
```
Success looks like `ok: <the worktree> at origin/dev <commit>, bedrock_access merged`, and nothing
after it. `NOT MERGED` means the pull request has not merged into `dev`: stop and wait.

**Sign in, confirm the identity the apply runs as, and that the cutover's step 9 is done.** Creating
a permission set needs break-glass, so the apply runs as `debate-admin`.

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
aws sso login --sso-session debate
aws sts get-caller-identity --profile debate-admin --query Arn --output text
AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev output caselist_run_late_alarm_actions_enabled
```
Success looks like an ARN containing `AWSReservedSSO_DebateBreakGlassAdmin`, then `true`. `false`
means the cutover's step 9 has not been applied: stop, and run this after it.

**The root's `owner.auto.tfvars` gains one line.** It already holds every person the root names
(the cutover's applies read it); this adds you to the new set. A plan made without the file would
remove every existing account assignment, which the plan check below refuses.

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
test -f "infrastructure/envs/${ENVIRONMENT}/owner.auto.tfvars" || echo "STOP: no owner.auto.tfvars in this worktree; copy it from the checkout that last applied ${ENVIRONMENT}"
grep -q '^bedrock_invoker_user_names' "infrastructure/envs/${ENVIRONMENT}/owner.auto.tfvars" || printf 'bedrock_invoker_user_names = ["%s"]\n' "$SSO_USER_NAME" >> "infrastructure/envs/${ENVIRONMENT}/owner.auto.tfvars"
terraform fmt "infrastructure/envs/${ENVIRONMENT}"
grep -c '^bedrock_invoker_user_names' "infrastructure/envs/${ENVIRONMENT}/owner.auto.tfvars"
```
Success looks like `1`, and no `STOP` line.

## Step 1 — The plan

Saved to a file, so what step 3 applies is exactly what the PM read.

**Operator command** (expected runtime ~2 min)
Where: `$WT`
```bash
cd "$WT"
if env | grep -qE '^(TF_VAR_|TF_WORKSPACE=|TF_DATA_DIR=|TF_CLI_ARGS)'; then echo "STOP: a Terraform override is set in this shell"; else AWS_PROFILE=debate-admin terraform -chdir="infrastructure/envs/${ENVIRONMENT}" init -input=false && AWS_PROFILE=debate-admin terraform -chdir="infrastructure/envs/${ENVIRONMENT}" plan -input=false -no-color -out=bedrock-access.tfplan | tee "/tmp/bedrock-access-${ENVIRONMENT}-plan.txt" | tail -5; fi
grep -E '^Plan:|must be replaced|will be destroyed' "/tmp/bedrock-access-${ENVIRONMENT}-plan.txt"
grep -E '^  # ' "/tmp/bedrock-access-${ENVIRONMENT}-plan.txt" | grep -v 'module.bedrock_access' | head
```

**What to read, and what stops you.** The first `grep` prints exactly
`Plan: 3 to add, 0 to change, 0 to destroy.` and no `must be replaced` or `will be destroyed` line.
The second prints nothing: every change is under `module.bedrock_access`. The three are the
permission set, its inline policy and your account assignment. Anything else stops you: send the
plan (`/tmp/bedrock-access-dev-plan.txt`) to the PM and do not apply. No plan line at all means the
plan failed: read the end of the file.

**When the set already exists** (a routing change after the first apply, such as `v1-e05-t13`'s), the
first `grep` prints exactly `Plan: 0 to add, 1 to change, 0 to destroy.` instead, and the rest reads
the same: the one change is the inline policy, updated in place. Step 2 then has a block of its own.

## Step 2 — The plan checked against exactly that shape

**The first apply.** `PLAN OK` only for those three resources created, nothing else in the account
changed, and a policy of `bedrock:InvokeModel` alone on twenty-two resources, fifteen of them through
the five profiles. It prints no account id. When the set already exists, skip this block and run
[the next one](#when-the-set-already-exists-one-inline-policy-updated).

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
AWS_PROFILE=debate-admin terraform -chdir="infrastructure/envs/${ENVIRONMENT}" show -json bedrock-access.tfplan > "/tmp/bedrock-access-${ENVIRONMENT}-plan.json"
python3 -I - "/tmp/bedrock-access-${ENVIRONMENT}-plan.json" "$ENVIRONMENT" "$SSO_USER_NAME" <<'BEDROCKPLAN'
import json, sys
plan = json.load(open(sys.argv[1]))
environment, user = sys.argv[2], sys.argv[3]
prefix = "module.bedrock_access."
expected = {
    prefix + "aws_ssoadmin_permission_set.invoker[0]",
    prefix + "aws_ssoadmin_permission_set_inline_policy.invoker[0]",
    prefix + 'aws_ssoadmin_account_assignment.invokers["' + user + '"]',
}
changes = [c for c in plan.get("resource_changes", []) if c["change"]["actions"] not in (["no-op"], ["read"])]
problems = []
creates = {c["address"] for c in changes if c["change"]["actions"] == ["create"]}
others = sorted(c["address"] + " " + "/".join(c["change"]["actions"]) for c in changes if c["change"]["actions"] != ["create"])
if creates != expected:
    problems.append("creates missing " + str(sorted(expected - creates)) + ", unexpected " + str(sorted(creates - expected)))
if others:
    problems.append("other changes " + str(others))
by_address = {c["address"]: c["change"] for c in changes}
name = (by_address.get(prefix + "aws_ssoadmin_permission_set.invoker[0]") or {}).get("after") or {}
if name.get("name") != "Debate" + environment.title() + "BedrockInvoker":
    problems.append("the set is named " + str(name.get("name")))
policy_change = by_address.get(prefix + "aws_ssoadmin_permission_set_inline_policy.invoker[0]") or {}
policy_text = (policy_change.get("after") or {}).get("inline_policy")
if not isinstance(policy_text, str):
    problems.append("the inline policy is not known at plan time")
    statements = []
else:
    statements = json.loads(policy_text)["Statement"]
actions = sorted({a for s in statements for a in ([s["Action"]] if isinstance(s["Action"], str) else s["Action"])})
resources = [r for s in statements for r in ([s["Resource"]] if isinstance(s["Resource"], str) else s["Resource"])]
conditioned = [r for s in statements if "Condition" in s for r in s["Resource"]]
profiles = [r for r in resources if ":inference-profile/" in r]
if actions != ["bedrock:InvokeModel"]:
    problems.append("actions are " + str(actions))
if len(resources) != 22 or len(set(resources)) != 22 or any("*" in r for r in resources):
    problems.append(str(len(resources)) + " resources, " + str(len(set(resources))) + " distinct, expected 22 and no wildcard")
if len(profiles) != 5 or len(conditioned) != 15 or not all(":foundation-model/anthropic." in r for r in conditioned):
    problems.append(str(len(profiles)) + " profiles and " + str(len(conditioned)) + " models through them, expected 5 and 15")
if any(s.get("Effect") != "Allow" or "NotAction" in s or "NotResource" in s for s in statements):
    problems.append("a statement that is not a plain Allow")
print("PLAN OK: 3 to create, nothing else; bedrock:InvokeModel on 22 resources, 15 Claude models through the 5 profiles" if not problems else "PLAN STOP: " + "; ".join(problems))
BEDROCKPLAN
```
Success looks like `PLAN OK: 3 to create, nothing else; bedrock:InvokeModel on 22 resources, 15
Claude models through the 5 profiles`. **`PLAN STOP` stops everything**: send its line and the plan
to the PM. Either way the PM reads the plan before step 3.

### When the set already exists: one inline policy updated

A routing change after the first apply changes the grant and nothing else. `PLAN OK` only for exactly
one change in the account, the set's inline policy updated in place; a new policy of
`bedrock:InvokeModel` alone on twenty-two resources, fifteen of them through the five profiles, each
of those models conditioned on exactly those profiles; every resource the old policy granted still
granted; and exactly the eight resources `v1-e05-t13` adds: the Haiku 4.5 and Sonnet 4.6 profiles in
us-east-1, and those two models in us-east-1, us-east-2 and us-west-2. It prints the account id as
`<account-id>`.

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
AWS_PROFILE=debate-admin terraform -chdir="infrastructure/envs/${ENVIRONMENT}" show -json bedrock-access.tfplan > "/tmp/bedrock-access-${ENVIRONMENT}-plan.json"
python3 -I - "/tmp/bedrock-access-${ENVIRONMENT}-plan.json" <<'BEDROCKPOLICYUPDATE'
import json, re, sys
plan = json.load(open(sys.argv[1]))
policy_address = "module.bedrock_access.aws_ssoadmin_permission_set_inline_policy.invoker[0]"
expected_added = sorted(
    ["arn:aws:bedrock:us-east-1:<account-id>:inference-profile/us.anthropic." + m for m in ("claude-haiku-4-5-20251001-v1:0", "claude-sonnet-4-6")]
    + ["arn:aws:bedrock:" + r + "::foundation-model/anthropic." + m for r in ("us-east-1", "us-east-2", "us-west-2") for m in ("claude-haiku-4-5-20251001-v1:0", "claude-sonnet-4-6")]
)
def masked(arns):
    return sorted(re.sub(r":[0-9]{12}:", ":<account-id>:", a) for a in arns)
def listed(value):
    return [value] if isinstance(value, str) else list(value or [])
def statements_of(change, side):
    text = (change.get(side) or {}).get("inline_policy")
    return json.loads(text)["Statement"] if isinstance(text, str) else None
changes = [c for c in plan.get("resource_changes", []) if c["change"]["actions"] not in (["no-op"], ["read"])]
problems = []
summary = sorted(c["address"] + " " + "/".join(c["change"]["actions"]) for c in changes)
if summary != [policy_address + " update"]:
    problems.append("changes are " + str(masked(summary)) + ", expected the inline policy's update alone")
change = next((c["change"] for c in changes if c["address"] == policy_address), {})
before, after = statements_of(change, "before"), statements_of(change, "after")
if after is None:
    problems.append("the new inline policy is not known at plan time")
    after = []
if before is None:
    problems.append("the policy it replaces is not in the plan")
    before = []
actions = sorted({a for s in after for a in listed(s.get("Action"))})
resources = [r for s in after for r in listed(s.get("Resource"))]
old_resources = [r for s in before for r in listed(s.get("Resource"))]
conditioned = [r for s in after if "Condition" in s for r in listed(s.get("Resource"))]
profiles = sorted(r for r in resources if ":inference-profile/" in r)
through = sorted({p for s in after if "Condition" in s for p in listed(s["Condition"].get("StringEquals", {}).get("bedrock:InferenceProfileArn"))})
if actions != ["bedrock:InvokeModel"]:
    problems.append("actions are " + str(actions))
if len(resources) != 22 or len(set(resources)) != 22 or any("*" in r for r in resources):
    problems.append(str(len(resources)) + " resources, " + str(len(set(resources))) + " distinct, expected 22 and no wildcard")
if len(profiles) != 5 or len(conditioned) != 15 or not all(":foundation-model/anthropic." in r for r in conditioned):
    problems.append(str(len(profiles)) + " profiles and " + str(len(conditioned)) + " models through them, expected 5 and 15")
if through != profiles:
    problems.append("the models are conditioned on " + str(masked(through)) + ", not on the profiles granted")
if any(s.get("Effect") != "Allow" or "NotAction" in s or "NotResource" in s for s in after):
    problems.append("a statement that is not a plain Allow")
removed = masked(set(old_resources) - set(resources))
added = masked(set(resources) - set(old_resources))
if removed:
    problems.append("no longer granted " + str(removed))
if added != expected_added:
    problems.append("added " + str(added) + ", expected " + str(expected_added))
print("PLAN OK: 1 to update, nothing else; bedrock:InvokeModel on 22 resources, 15 Claude models through the 5 profiles; 8 added, none removed" if not problems else "PLAN STOP: " + "; ".join(problems))
BEDROCKPOLICYUPDATE
```
Success looks like `PLAN OK: 1 to update, nothing else; bedrock:InvokeModel on 22 resources, 15
Claude models through the 5 profiles; 8 added, none removed`. **`PLAN STOP` stops everything**: send
its line and the plan to the PM. Either way the PM reads the plan before step 3. A later routing
change adds or removes other resources, so its task rewrites `expected_added` and the counts here.

## Step 3 — The apply

Only after the PM's word on steps 1 and 2.

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
if env | grep -qE '^(TF_VAR_|TF_WORKSPACE=|TF_DATA_DIR=|TF_CLI_ARGS)'; then echo "STOP: a Terraform override is set in this shell"; else AWS_PROFILE=debate-admin terraform -chdir="infrastructure/envs/${ENVIRONMENT}" apply -input=false bedrock-access.tfplan; fi
AWS_PROFILE=debate-admin terraform -chdir="infrastructure/envs/${ENVIRONMENT}" output bedrock_invoker_permission_set_name
AWS_PROFILE=debate-admin terraform -chdir="infrastructure/envs/${ENVIRONMENT}" output bedrock_profile_name
```
Success looks like `Apply complete! Resources: 3 added, 0 changed, 0 destroyed.`, then
`"DebateDevBedrockInvoker"` and `"debate-dev-bedrock"`. When the set already existed, it reads
`Apply complete! Resources: 0 added, 1 changed, 0 destroyed.` instead, with the same two names, and
steps 4 to 6 are not repeated: go on to step 7. `Saved plan is stale` means something changed
in between: go back to step 1. Never `-target`, and never create a permission set by hand.

## Step 4 — The profile

Once per Mac, after the apply. The profile's name is what `models.aws_profile` names, so nothing else
is configured. The account id is read from the admin profile into a shell variable and never printed.

**Operator command** (expected runtime ~1 min)
Where: your Mac, anywhere
```bash
ACCOUNT_ID=$(aws sts get-caller-identity --profile debate-admin --query Account --output text)
aws configure set "profile.debate-${ENVIRONMENT}-bedrock.sso_session" debate
aws configure set "profile.debate-${ENVIRONMENT}-bedrock.sso_account_id" "$ACCOUNT_ID"
aws configure set "profile.debate-${ENVIRONMENT}-bedrock.sso_role_name" "Debate${(C)ENVIRONMENT}BedrockInvoker"
aws configure set "profile.debate-${ENVIRONMENT}-bedrock.region" us-east-1
aws sso login --sso-session debate
aws sts get-caller-identity --profile "debate-${ENVIRONMENT}-bedrock" --query Arn --output text | grep -o 'AWSReservedSSO_[A-Za-z]*'
```
Success looks like `AWSReservedSSO_DebateDevBedrockInvoker`. Identity Center can take a minute to
provision a new set's role; if the last line says the role does not exist, wait a minute and run it
again. `${(C)ENVIRONMENT}` is zsh for the capitalised name, `Dev`.

**What the build sees.** In `$WT`, `doctor` reports the profile on its `Model profile` row.

**Operator command** (expected runtime ~1 min)
Where: `$WT`
```bash
cd "$WT"
uv sync --all-packages
if env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell:"; env | grep -oE '^DEBATE_[A-Z_]*'; else DEBATE_ENV="$ENVIRONMENT" uv run debate-research doctor --evidence-profiles | grep -A1 'Model profile'; fi
```
Success looks like `Model profile debate-dev-bedrock (models.aws_profile): defined, and signed in as
DebateDevBedrockInvoker` (the table may wrap it over two lines).

## Step 5 — The account's one-time model access

Not Terraform: these are done once for the account, as break-glass, and the permission set does none
of them. Its one action is `bedrock:InvokeModel`.

**The Anthropic use-case form.** Anthropic's models need it submitted once per account before the
first call. As `debate-admin`, in the console at us-east-1: Amazon Bedrock, then **Model catalog**,
then any Anthropic Claude model, then **Open in playground**. If a use-case form appears, fill it in
for the team's research tool and submit it; if none appears, the account has already submitted it.
It can take about 15 minutes to reach every model. Record the date for the PM. (Dev's form was
submitted on 2026-10-27.)

**Marketplace subscriptions are made by a first call.** Since October 2025 Bedrock has no model-access
page and shows no offer to accept: a model sold through AWS Marketplace (Anthropic, Cohere) is
subscribed by the first call from a principal with Marketplace permissions. The invoker set has none,
so that first call is made once as `debate-admin`, with a few dozen tokens. `end_turn` (or
`application/json` for the reranker) means the call was answered and the subscription now exists.
Replace the profile ids with the routing files' if they differ.

**Operator command** (expected runtime ~1 min)
Where: your Mac, anywhere
```bash
aws sso login --sso-session debate
for m in us.anthropic.claude-haiku-5-5 us.anthropic.claude-sonnet-5-5 us.anthropic.claude-opus-5-5; do echo "== $m"; aws bedrock-runtime converse --profile debate-admin --region us-east-1 --model-id "$m" --messages '[{"role":"user","content":[{"text":"Reply with the word OK."}]}]' --inference-config '{"maxTokens":512}' --query 'stopReason' --output text; done
echo "== cohere.rerank-v3-5:0"
aws bedrock-runtime invoke-model --profile debate-admin --region us-east-1 --model-id cohere.rerank-v3-5:0 --cli-binary-format raw-in-base64-out --body '{"query":"debate","documents":["policy debate","a recipe"],"top_n":1,"api_version":2}' /tmp/rerank-first-call.json --query 'contentType' --output text
```

**When a Claude call is refused:**

* "Model use case details have not been submitted": the form has not reached that model yet. Wait
  15 minutes and run it again.
* "is not available for this account … contact AWS Sales": read the account's applied quotas. A
  model whose cross-region tokens-per-minute quota is `0.0` while AWS's default is not is held at zero
  for the account. That is lifted by a support case (Support Center, Service limit increase, Amazon
  Bedrock), not by a quota request, which refuses any value at or below the default. Dev's 5.5 quotas
  were held at zero on 2026-10-27, and dev routes to Haiku 4.5 and Sonnet 4.6 until they are restored
  (`v1-e05-t13`).

**Operator command** (expected runtime ~1 min)
Where: your Mac, anywhere
```bash
aws service-quotas list-service-quotas --profile debate-admin --region us-east-1 --service-code bedrock --query "Quotas[?contains(QuotaName, 'Cross-region model inference tokens per minute for Anthropic Claude')].[QuotaName, Value]" --output text
```

**What the account says about each model**, read-only, after the first calls. Each line is one
model and four fields.

**Operator command** (expected runtime ~1 min)
Where: your Mac, anywhere
```bash
for model in anthropic.claude-haiku-5-5 anthropic.claude-sonnet-5-5 anthropic.claude-opus-5-5 amazon.titan-embed-text-v2:0 cohere.rerank-v3-5:0; do echo "== $model"; aws bedrock get-foundation-model-availability --profile debate-admin --region us-east-1 --model-id "$model" --query '[agreementAvailability.status, authorizationStatus, entitlementAvailability, regionAvailability]' --output text; done
```
Each model is followed by `AVAILABLE AUTHORIZED AVAILABLE AVAILABLE` once its first call has been
answered. `NOT_AVAILABLE` agreement before then is expected. `Invalid choice` or an
unknown-operation error means this AWS CLI is older than the command: update it, or skip this block.

## Step 6 — The data-use checks (the policy's open question 4)

[The data-use policy](../policies/caselist-data-use.md)'s open question 4 needs two things before
the first full-corpus classification run. Recording them in the policy is the PM's; this step only
collects them.

**The AWS documentation.** Read **Data protection** in the Amazon Bedrock User Guide,
<https://docs.aws.amazon.com/bedrock/latest/userguide/data-protection.html>, and send the PM the date
you read it and the sentences that say Bedrock does not store or log prompts and completions, does not
use them to train models, and does not share them with model providers.

**The account's model-invocation logging**, read-only, in the three regions a call can run in. It
prints only where logs would go, never a role.

**Operator command** (expected runtime ~1 min)
Where: your Mac, anywhere
```bash
for region in us-east-1 us-east-2 us-west-2; do printf '%s ' "$region"; aws bedrock get-model-invocation-logging-configuration --profile debate-admin --region "$region" --query '[loggingConfig.cloudWatchConfig.logGroupName, loggingConfig.s3Config.bucketName, loggingConfig.cloudWatchConfig.largeDataDeliveryS3Config.bucketName]' --output text; done
```
Success looks like each region followed by `None None None`: no invocation logging anywhere, so
nothing a call sends is written down by the account either. A name instead of `None` is a destination:
send the PM the region and the names. A log group is always in this account; for a bucket, the next
block says whether this account owns it, with `BUCKET` set to the name printed.

**Operator command** (expected runtime ~1 min)
Where: your Mac, anywhere
```bash
BUCKET='the-bucket-name-printed-above'
ACCOUNT_ID=$(aws sts get-caller-identity --profile debate-admin --query Account --output text)
aws s3api head-bucket --profile debate-admin --bucket "$BUCKET" --expected-bucket-owner "$ACCOUNT_ID" && echo "owned by this account" || echo "NOT this account's: tell the PM"
```

## Step 7 — The first real call on each Claude route

The spec's ac5, with the new profile, after steps 4 and 5. One run over both routing files: each model
is asked its questions once, however many routes name it, so it asks the five Claude models seven
requests each (the adapter's own call, then `toolChoice any`, `toolChoice tool`, `temperature 0.5`,
`effort low`, `structured output` and `strict tool`), one embedding and one rerank: 37 requests.

**What it costs.** Each request is about 400 input tokens with a 2,048-token output cap. A probe
answer is a few dozen tokens, plus whatever the model thinks first (Opus 5.5 always thinks), and a
request Bedrock refuses as invalid is refused before the model runs. At Anthropic's list prices (Opus
5.5 $4 and $20, Sonnet 5.5 $2 and $10, Haiku 5.5 $0.10 and $0.50 per million input and output tokens),
with 300 output tokens a request, the three 5.5 models' requests are under ten cents; every request
at its output cap would be about 45. Dev's Haiku 4.5 and Sonnet 4.6 add fourteen requests at
Bedrock's $1 and $5, and $3 and $15 (`config/model_pricing.yaml`): about five cents at 300 output
tokens a request, about 30 at the cap. Bedrock bills by its own price list, which may differ; the
line under the table counts the tokens actually billed.

**Operator command** (expected runtime ~2 min)
Where: `$WT`
```bash
cd "$WT"
aws sso login --sso-session debate
if env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell:"; env | grep -oE '^DEBATE_[A-Z_]*'; else env -u AWS_PROFILE DEBATE_ENV="$ENVIRONMENT" uv run python -m debate_core.integrations.bedrock.first_call --routing-file config/model_routing.dev.yaml --routing-file config/model_routing.prod.yaml > "/tmp/bedrock-first-call-${ENVIRONMENT}.md"; echo "first call exit=$?"; cat "/tmp/bedrock-first-call-${ENVIRONMENT}.md"; fi
```

**What success looks like.** The first line is `Signed with AWS profile debate-dev-bedrock
(models.aws_profile, DEBATE_ENV=dev).` Then a Markdown table: for each Claude model, seven rows, each
`accepted` or `refused` with Bedrock's code and message and the routes it serves; then one row for
embeddings and one for rerank; then the line counting accepted requests and tokens. `first call
exit=0` means every probe got an answer: **a refusal is a finding, not a failure.** Exit 1 means a
probe could not run (access denied, or no answer). Send the PM the whole file,
`/tmp/bedrock-first-call-dev.md`, which is what the block printed after the exit line; account ids in Bedrock's messages are already masked as
`<account-id>`.

**While the account's 5.5 quotas are held at zero** (from 2026-10-27, `v1-e05-t13`), the run is read
differently. The rows that matter are dev's: for `us.anthropic.claude-haiku-4-5-20251001-v1:0` and
`us.anthropic.claude-sonnet-4-6`, the adapter's own call reads `accepted`, and the other six rows are
`accepted` or `refused` (a refused probe is a finding). The three 5.5 models' rows are refused as "not
available for this account", which is expected until the support case clears. If Bedrock sends that
refusal as `AccessDeniedException`, each 5.5 model's six probes read `not tried` and the block prints
`first call exit=1`: that exit is expected here, and the run is good when dev's two adapter calls are
`accepted` and every 5.5 refusal names the account rather than `bedrock:InvokeModel`. Send the PM the
whole file either way.

**When the adapter's own call is refused:**

* `AccessDeniedException` naming `aws-marketplace` or a subscription: the model's Marketplace offer is
  not accepted; see step 5, then run this block again.
* `AccessDeniedException` naming `bedrock:InvokeModel` on a `foundation-model` ARN in a region other
  than the three: the profile sends calls to a region the grant does not name. Send the PM the line;
  the module's region list is what changes, never a wildcard.
* `ResourceNotFoundException` or `ValidationException` naming the model id: an identifier in the
  routing file does not resolve. That is a finding for the routing file's owner.
* `the AWS profile models.aws_profile names is not defined`: step 4 was not run on this Mac.

## Step 8 — Zero-retention mode, in the three regions

The coach's decision of 2026-10-27: Bedrock's data retention mode is `none` (zero retention) in
us-east-1, us-east-2 and us-west-2, the three regions a call through the inference profiles can run
in. The mode is set per region for the whole account, prod's calls included, so it is the account's
step, done once, as `debate-admin`. It uses the Bedrock control plane's `get-account-data-retention`
and `put-account-data-retention` (AWS's Data retention page in the Bedrock User Guide, read by the PM
on 2026-10-27), signed with the admin profile's own credentials, so no API key is made.

**The catch, and why step 7 runs again.** Under `none`, Bedrock refuses a call to any model whose
allowed modes do not include `none`, and AWS's page says zero-retention eligibility for Claude models
is managed by Anthropic. The control plane cannot say which modes a model allows, so the mode is set
and step 7 is run again: a model that needs retention answers with a `ValidationException` naming
data retention. If any of dev's models does, the mode goes back to what it was, and the PM brings the
choice to the coach before anything else is set.

**What the account is set to now**, read-only.

**Operator command** (expected runtime ~1 min)
Where: your Mac, anywhere
```bash
aws sso login --sso-session debate
for region in us-east-1 us-east-2 us-west-2; do printf '%s ' "$region"; aws bedrock get-account-data-retention --profile debate-admin --region "$region" --query mode --output text; done
```
Success looks like each region followed by its mode: `inherit` where nothing was ever set. Send the PM
the three lines, since a refusal later puts each region back to exactly this. `Invalid choice` means
this AWS CLI is older than the command: update it (`brew upgrade awscli`) and run the block again.
`AccessDeniedException` means the admin role may not read the setting: stop and send the PM the line.

**Set `none` in the three regions.**

**Operator command** (expected runtime ~1 min)
Where: your Mac, anywhere
```bash
for region in us-east-1 us-east-2 us-west-2; do printf '%s ' "$region"; aws bedrock put-account-data-retention --profile debate-admin --region "$region" --mode none --query mode --output text; done
```
Success looks like each region followed by `none`. Then run step 7's block again, as written, and
send the PM the whole file.

**Reading step 7 under `none`.** Every row that was accepted before is accepted again, and nothing
else matters here: dev's two adapter calls, their probes (`effort low` stays refused, as on
2026-10-27), the embedding and the rerank. The 5.5 models' rows stay refused as "not available for
this account" while the quota case is open; that is the quota, not the mode. A row refused with a
`ValidationException` that names data retention is the model needing retention: put the mode back,
below, and send the PM the file.

**Only if a row names data retention: the mode put back.** Replace `inherit` with what the first block
printed for each region, if it printed something else.

**Operator command** (expected runtime ~1 min)
Where: your Mac, anywhere
```bash
for region in us-east-1 us-east-2 us-west-2; do printf '%s ' "$region"; aws bedrock put-account-data-retention --profile debate-admin --region "$region" --mode inherit --query mode --output text; done
```
Success looks like each region followed by `inherit`. Run step 7 once more to see the rows accepted
again.

**What the models cost after that.** Every call a command makes in record or live mode is logged to `<data_dir>/usage/YYYY-MM-DD.jsonl`, priced from `config/model_pricing.yaml`, and refused before it is made when it could take the run, the day or the calendar month in America/Chicago past `models.budget_usd_per_run`, `models.budget_usd_daily` or `models.budget_usd_monthly` (an unpriced model is refused whenever a limit is set). A refusal names the limit it hit, `per-run`, `per-day` or `per-month`, and what remains of it. `debate-research usage --date YYYY-MM-DD` shows a day's calls, tokens and cost, the month's spend under them, and both limits. The probe above calls the adapter directly and is not logged.

## Prod

After the release carrying this task is promoted to `main`, from a worktree at `origin/main`, with the
prod root's `owner.auto.tfvars` copied from the checkout that last applied prod. Set the variables,
then run steps 1 to 4 as written: every block reads `$WT` and `$ENVIRONMENT`. Step 1 expects the same
`Plan: 3 to add, 0 to change, 0 to destroy.`, step 2 the same `PLAN OK`, and step 3 prints
`"DebateProdBedrockInvoker"` and `"debate-prod-bedrock"`. Steps 5, 6 and 8 are the account's and are not
repeated; step 7 is run again only if the PM asks for prod's own answers.

```bash
WT="$HOME/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/bedrock-access-prod"
ENVIRONMENT=prod
SSO_USER_NAME='your-identity-center-user-name'

cd "$WT" || echo "STOP: the worktree is missing: $WT"
git fetch origin
git switch --detach origin/main
test -f infrastructure/envs/prod/bedrock_access.tf && echo "ok: $(pwd) at origin/main $(git rev-parse --short HEAD), bedrock_access promoted" || echo "NOT PROMOTED: origin/main has no v1-e05-t08"
git status --porcelain | grep -v 'owner.auto.tfvars' | head -3
```
Success looks like `ok: <the worktree> at origin/main <commit>, bedrock_access promoted`, and nothing
after it. Make the worktree first, if `git worktree list` does not show it, from the kept `dev-preview`
worktree: `git worktree add --detach ../bedrock-access-prod origin/main`.

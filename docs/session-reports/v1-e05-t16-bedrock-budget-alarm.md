# Session report: v1-e05-t16-bedrock-budget-alarm

| | |
|---|---|
| Task | `v1-e05-t16-bedrock-budget-alarm` — An AWS budget alarm on the account's model spend, $100 a month with a first notice at $50 |
| Spec | [`plan_specs/v1/e05-model-router/t16-bedrock-budget-alarm.yaml`](../../plan_specs/v1/e05-model-router/t16-bedrock-budget-alarm.yaml) |
| Epic / release | `v1-e05-model-router` / `v1.2` |
| Branch | `task/v1-e05-t16-bedrock-budget-alarm` |
| Session status | PARTIAL: everything a session can run passes; ac3 (the PM's read of the plan, the apply and the budget's first reading) is the operator's, after the merge <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The account's model spend now has a budget at the coach's ceiling, in a tested module:
`infrastructure/modules/model_spend_budget` holds `debate-shared-bedrock-monthly` at $100 a month, with
notices at $50, $80 and $100 of actual spend and $100 of forecast, in dollars, by email to the coach's
address (`model_budget_notification_emails`, gitignored). Its filter is what the operator's Cost
Explorer counts found model calls billed under: four services AND four usage types, so Claude and
Cohere's Marketplace charges count, Titan's Amazon Bedrock charge counts, and the account's Nova
Micro spend, which is not ours, does not; there is no `Project` tag, which model charges never carry.
`bootstrap/organization` calls the module and moves v1-e29-t01's budget into it, so the apply updates
that budget in place, and `bedrock_monthly_budget_usd` is gone. **The Goal stays `InProgress`**: ac3 is
the operator's after the merge, so this merges `--partial`. Look first at **Counts**, then at the plan
check in the runbook (the PM's read of the plan rests on it) and **Decisions** 1 and 2.

## Counts (ac1)

Read by the operator on 2026-10-29 as `debate-admin`, with the block under Operator follow-ups
(Cost Explorer, unblended cost, monthly, 2026-09-01 to 2026-10-29). Names only; no amounts are
recorded here.

**What this project's model calls are billed under** (all in October; none in September, which is
before `v1-e05-t08` gave any profile `bedrock:InvokeModel`):

| Model (route) | Service | Usage types |
|---|---|---|
| Claude Haiku 4.5 (dev) | `Claude Haiku 4.5 (Amazon Bedrock Edition)` | `USE1-MP:USE1_InputTokenCount-Units`, `USE1-MP:USE1_OutputTokenCount-Units` |
| Claude Sonnet 4.6 (dev) | `Claude Sonnet 4.6 (Amazon Bedrock Edition)` | `USE1-MP:USE1_InputTokenCount-Units`, `USE1-MP:USE1_OutputTokenCount-Units` |
| Cohere Rerank v3.5 | `Cohere Rerank v3.5 (Amazon Bedrock Edition)` | `USE1-MP:USE1_search_units-Units` |
| Titan Text Embeddings V2 | `Amazon Bedrock` | `USE1-TitanEmbeddingV2-Text-input-tokens` |

**Model spend that is not this project's:** `Amazon Bedrock` / `USE1-NovaMicro-input-tokens` and
`USE1-NovaMicro-output-tokens`, in September and October. No routing file and no grant names a Nova
model, and September predates the project's Bedrock access, so a filter on the `Amazon Bedrock`
service alone would count it.

**Not yet billed, so not named:** the three 5.5 models of prod's routes (Claude Haiku, Sonnet and
Opus 5.5). They have never been called (their quotas are held at zero, `v1-e05-t13`), so Cost
Explorer has no service name for them yet.

**The `Project` tag:** every row in both months, for every service, groups under an empty
`Project` value. That includes S3, KMS, Secrets Manager and ECS spend that this project's Terraform
tags. Cost Explorer shows no spend under `Project=debate-intelligence` at all.

**Record types:** `Usage` and `Other` only. There are no credits, so none are netting the spend.

## Plan nodes

<!-- One row per Plan graph node, in the order they were completed. -->

| Node | Status | Notes |
|---|---|---|
| `budget-alarm` (Model spend alarm) | Done, except the operator's apply | Counts first (`d339f93`, `a56d3fe`), the PM's ruling, tests red against a skeleton of today's budget (`658183f`), the module and the root (`b11a7e5`), the runbook's blocks and their tested plan check (`7851bcb`), formatting (`a062c43`) |

## Acceptance criteria

<!-- Goal criteria (ac1…) and every node criterion. Status: PASS / FAIL / NOT RUN. -->

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: counts first: the services and usage types model calls are billed under, read by the operator, recorded as names only, before the filter is written | PASS | The operator's read-only Cost Explorer block (Operator follow-ups) on 2026-10-29, before any Terraform was written; names in **Counts**, no amounts. |
| ac2: Terraform tests show one budget of 100 USD a month, the filter, its notifications (actual $50, $80, $100; forecast $100) and no grant, shown failing first | PASS | **Red**, at `658183f` (the module holding v1-e29-t01's budget as it stands: $40, percentages, forecast at 80%, `Amazon Bedrock` AND the `Project` tag): `terraform -chdir=infrastructure/modules/model_spend_budget test` → `Failure! 1 passed, 3 failed.`, 0 skipped, each failure `Test assertion failed`: the limit (`one_budget_of_100_usd_a_month`), the filter's keys, services and usage types (`the_filter_is_the_counted_services_and_usage_types`), the notices (`four_notices_in_dollars`). **Green**, at `b11a7e5`: `Success! 4 passed, 0 failed.` **No grant**: `tests/infrastructure/test_model_spend_budget_grants_nothing.py` (the module's `.tf` files declare one `aws_budgets_budget` and no other resource, data source or module call) → `2 passed`; shown failing by mutants 15 to 17 below. |
| ac3: the PM reads the plan, the operator applies it, and the budget reads its first month's spend | NOT RUN | Needs the operator's credentials, an apply and the PM's read, after the merge: no session can close it. The blocks are under Operator follow-ups (and in `docs/runbooks/aws-account-baseline.md`, "The model spend budget"). |
| Node `budget-alarm`: Terraform checks pass (`uv run bash scripts/terraform_checks.sh`) | PASS | Run offline against the main checkout's provider mirror (`TF_CLI_CONFIG_FILE` naming a `filesystem_mirror` on its `envs/dev/.terraform/providers`, hashicorp/aws 5.100.0), at the final tree: `All Terraform checks passed.`, exit 0, 33 `ok` lines, among them `validate infrastructure/bootstrap/organization`, `validate infrastructure/modules/model_spend_budget`, `tflint config infrastructure/modules/model_spend_budget`, `test infrastructure/modules/model_spend_budget`. No lock file changed; the new module's `.terraform.lock.hcl` is `bedrock_access`'s, byte for byte. |

### Mutation run (agreement 8)

17 mutants, one at a time on the committed tree, each against the module's Terraform tests and
`tests/infrastructure`, each restored after its run, `git status` clean after the batch. Neither suite
uses Hypothesis; each run still had `HYPOTHESIS_STORAGE_DIRECTORY` set to a new, empty directory.
Script: a throwaway in the session's scratchpad, not committed.

| # | Mutant | Result |
|---|---|---|
| 1 | PM 1: an actual threshold changed, $80 to $90 | Caught: `four_notices_in_dollars`, `3 passed, 1 failed`, assertion |
| 2 | PM 1: the forecast threshold changed, $100 to $120 | Caught: `four_notices_in_dollars`, assertion |
| 3 | PM 1: the limit changed, $100 to $150 | Caught: `one_budget_of_100_usd_a_month`, assertion |
| 4 | PM 2: the forecast notification dropped | Caught: `four_notices_in_dollars`, assertion |
| 5 | PM 3: a model service missing (Cohere Rerank) | Caught: `the_filter_is_the_counted_services_and_usage_types`, assertion |
| 6 | PM 3: a model usage type missing (Titan embeddings) | Caught: the filter run, assertion |
| 7 | PM 4: a non-model service added (`Amazon Simple Storage Service`) | Caught: the filter run, assertion |
| 8 | PM 4: a non-model usage type added (`USE1-NovaMicro-input-tokens`) | Caught: the filter run, assertion |
| 9 | The `Project` tag filter added back | Caught: the filter run, assertion |
| 10 | The usage-type key dropped (service alone) | Caught: the filter run, assertion |
| 11 | Notices as percentages | Caught: `four_notices_in_dollars`, assertion |
| 12 | A notice also sent to an SNS topic | Caught: `four_notices_in_dollars`, assertion |
| 13 | The budget renamed (it would be replaced) | Caught: `one_budget_of_100_usd_a_month`, assertion |
| 14 | The empty-address validation disarmed (`>= 0`) | Caught: `a_budget_nobody_receives_is_refused`, `Missing expected failure` |
| 15 | PM 5: a permission set added in `main.tf` | Caught by the pytest: `1 failed, 1 passed` (assertion); the Terraform tests pass, as expected |
| 16 | PM 5: an account assignment added in a new `grants.tf` | Caught by the pytest: `1 failed, 1 passed` (assertion). The Terraform run errored on the provider's argument check, which is not counted |
| 17 | PM 5: a module call added | Caught by the pytest: `1 failed, 1 passed` (assertion). The Terraform run errored (`Module not installed`), not counted |

Every catch counted is a failing assertion with nothing skipped. Mutant 14's first form,
`condition = true`, made Terraform reject the validation itself (an error, not a catch), so it was
redone with a condition that still reads the variable, and caught.

### The plan check, red first

The runbook's `MODELBUDGETPLAN` check is tested on hand-written synthetic plans by
`tests/docs/test_model_spend_budget_plan_check.py`. Against a check that refuses nothing (the heredoc
replaced by one `print("PLAN OK: ...")`, then restored with `git checkout HEAD --`): `23 failed, 3 passed`;
the three that pass are the OK plan, decimal amounts, and no address printed. At `a062c43`: `26 passed`.
The plan block's text filter was checked against a real Terraform 1.16.3 plan of a moved and updated
`terraform_data` (local state, no provider, in the scratchpad): the change lines are exactly
`  # module.<...> will be updated in-place` and `  # (moved from <old address>)`, and `show -json`
gives `previous_address` and `["update"]`, the shape the check reads.

### Before the report

| Command | Result |
|---|---|
| `uv run scripts/affected_tests.py --run` | `82 of 566 test files (14.5%) chosen`; `3041 passed in 189.15s`; `Affected set: 82 test files, pytest exited 0 after 192 s`. Over the two-minute line (3 min 23 s in all): see Deviations |
| `uv run pytest -q -n 0 -p no:randomly tests/infrastructure tests/docs/test_model_spend_budget_plan_check.py` (after formatting) | `28 passed` |
| `uv run ruff format --check .` / `uv run ruff check .` | `1583 files already formatted` / `All checks passed!` |
| `uv run pyright tests/infrastructure tests/docs/test_model_spend_budget_plan_check.py` | `0 errors, 0 warnings, 0 informations` (no package source changed) |
| `uv run lint-imports` | `Contracts: 18 kept, 0 broken.` |
| `uv run scripts/validate_specs.py` | `OK: 492 files, 40 epics, 430 tasks, 22 releases` |
| `uv run python scripts/check_command_blocks.py --base origin/dev` | `OK: no '#' comments in 577 shell code blocks in 198 Markdown files`; every new runbook block also passes `zsh -n` |

## Files changed

<!-- Group by package or directory; one line on why each group changed. -->

- **`infrastructure/modules/model_spend_budget/`** (new): the budget, its README, its Terraform tests,
  the shared `.tflint.hcl` and a lock file copied from `bedrock_access`.
- **`infrastructure/bootstrap/organization/`**: `budgets.tf` calls the module with a `moved` block
  and drops the unused `budget_project_filter`; `variables.tf` drops `bedrock_monthly_budget_usd` and
  adds `model_budget_notification_emails`; `outputs.tf`, `terraform.tfvars.example` and `README.md`
  follow. `identity.tf`, `cloudtrail.tf` and `main.tf` are untouched.
- **`infrastructure/README.md`**: the layout table's row for the module.
- **`docs/runbooks/aws-account-baseline.md`**: "The model spend budget": the counts, and plan, check,
  apply and first reading.
- **`tests/infrastructure/test_model_spend_budget_grants_nothing.py`** (new) and
  **`tests/docs/test_model_spend_budget_plan_check.py`** (new): the no-grant check and the plan
  check's tests.
- **This report.**

## Deviations from the spec

1. **Two test files outside the spec's packages** (`infrastructure`, `docs/runbooks`, `docs/data`):
   `tests/infrastructure/test_model_spend_budget_grants_nothing.py`, which the PM accepted at the
   counts checkpoint as the "no grant" check a Terraform test cannot make, and
   `tests/docs/test_model_spend_budget_plan_check.py`, which tests the runbook's plan check the way
   `tests/docs/test_cutover_plan_checks.py` tests the cutover's. Neither touches shared test ground.
2. **The affected set ran 3 min 23 s**, past the two-minute line I expected it to stay under (82
   files, at load average 3 to 6). It passed; under agreement 10 a set this long would be left to the
   pull request's `ci` check, which runs the same files.

## Decisions and assumptions

<!-- Choices the spec left open, with the reasoning. -->

The PM's ruling at the counts checkpoint (2026-10-29) settled the filter (service AND usage type, no
`Project` tag), the names (only those counted; `v1-e05-t17` adds the 5.5 models'), the root
(`bootstrap/organization`, the module, the `moved` block, `bedrock_monthly_budget_usd` removed), the
recipients (the budget's own email subscribers, `model_budget_notification_emails`), and accepted
three decisions: dollar thresholds, the pytest for "no grant", and ac3's comparison with Cost
Explorer. What I chose within that:

1. **The limit, notices and filter are locals in the module, not inputs.** The tests then hold
   exactly what the root applies, and no tfvars line can raise the limit past the coach's ceiling.
   The module's only inputs are the name prefix and the addresses.
2. **The plan check is a tested script in the runbook, and the report copies the runbook's blocks.**
   `v1-e05-t17` re-runs the counts and re-applies, so the blocks belong in the runbook. The check
   accepts the budget already in the module (no `previous_address`) as well as moved into it, so it
   serves that later apply; its lists change with the module's. It prints no address and no account
   id.
3. **The apply runs from a worktree of its own at `origin/dev`, after the merge,** as ac3 says. The
   root is account-wide, not dev; if the PM wants this root applied only from `main`, the same blocks
   run from a `main` worktree after the promotion by setting `WT` and the `git switch` there.
4. **The root's `terraform.tfvars` stays one copy, in the main checkout.** The tfvars block backs it
   up to `~/aws-backups/debate-terraform-state/`, edits it there and copies it into the worktree, so
   the next apply from anywhere reads the same values. It is gitignored, so the main checkout's git
   state is untouched.
5. **The budget keeps its name and tags**, so the plan is one in-place update; mutant 13 shows a
   rename is caught before it could replace the budget.
6. **The counts block in the runbook computes last month and this month**, with a first request on a
   fixed past day that only checks Cost Explorer can be read. The session's own block named
   September and October 2026.
7. **Nothing under `docs/data/`.** The counts are names only and live in this report and the
   module's README; there was no operator-run data job's aggregate to record.

## Operator follow-ups

<!-- Commands the operator must run (anything over ~2 minutes), with where to run them, the exact
command, expected runtime and what success looks like. Also GitHub/AWS settings to change. -->

### Done: the counts (ac1), read-only, before the filter is written

Run by the operator on 2026-10-29; the names are in **Counts**.


Where: any terminal on your Mac, signed in as `debate-admin` (`aws sso login --profile debate-admin`
first if the session has expired). Expected runtime: under a minute. It makes seven Cost Explorer
requests, all reads, and changes nothing. The first request only checks that Cost Explorer can be
read; if it cannot (not enabled, or the role may not read it), the block prints `STOP` and runs
nothing more. It prints no account id.

```bash
if ! aws ce get-cost-and-usage --profile debate-admin --time-period Start=2026-10-01,End=2026-10-02 --granularity MONTHLY --metrics UnblendedCost --query 'ResultsByTime[0].TimePeriod.Start' --output text; then
  echo "STOP: Cost Explorer could not be read as debate-admin (not enabled, or this role may not read it). Paste this output back and run nothing more."
else
  rows='(.ResultsByTime[].Groups[] | select((.Metrics.UnblendedCost.Amount | tonumber) != 0) | (.Keys | join("\t")) + "\t" + .Metrics.UnblendedCost.Amount), (if .NextPageToken then "INCOMPLETE: Cost Explorer returned more pages than this listing shows" else empty end)'
  for month_start month_end in 2026-09-01 2026-10-01 2026-10-01 "$(date +%F)"; do
    echo "== ${month_start} to ${month_end}, by service and usage type (USD, non-zero rows)"
    aws ce get-cost-and-usage --profile debate-admin --time-period Start=${month_start},End=${month_end} --granularity MONTHLY --metrics UnblendedCost --group-by Type=DIMENSION,Key=SERVICE Type=DIMENSION,Key=USAGE_TYPE --output json | jq -r "$rows" | sort
    echo "== ${month_start} to ${month_end}, by service and Project tag (USD, non-zero rows)"
    aws ce get-cost-and-usage --profile debate-admin --time-period Start=${month_start},End=${month_end} --granularity MONTHLY --metrics UnblendedCost --group-by Type=DIMENSION,Key=SERVICE Type=TAG,Key=Project --output json | jq -r "$rows" | sort
    echo "== ${month_start} to ${month_end}, by record type (USD, non-zero rows)"
    aws ce get-cost-and-usage --profile debate-admin --time-period Start=${month_start},End=${month_end} --granularity MONTHLY --metrics UnblendedCost --group-by Type=DIMENSION,Key=RECORD_TYPE --output json | jq -r "$rows" | sort
  done
fi
```

Success looks like: three listings for September and three for October so far, each a list of
tab-separated names and amounts, and no `INCOMPLETE` line. Paste the whole output back into the
session; the report records the names only.

### To do after the merge (ac3): plan, the PM's read, apply, the budget's first reading

Copied from `docs/runbooks/aws-account-baseline.md`, "Applying a change to the budget". Never on a
Wednesday, the cloud run's day; the plan and apply blocks refuse one. The Goal stays `InProgress`
until the last block's figures are recorded here.

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

## Follow-up work

<!-- Bugs, gaps or ideas outside this task's scope, each with the task or epic it belongs to.
The PM decides whether they become spec changes or new tasks. -->

1. **The empty `Project` tag** (v1-e29-t01's account baseline). Every Cost Explorer row in September
   and October, for every service, grouped under an empty `Project`, including spend this project's
   Terraform tags. That suggests the cost allocation tags were never activated (the runbook's Step 5).
   If so, the environment budgets (filtered on `Environment`) and the anomaly monitor (filtered on
   `Project`) read $0 too; I did not group by `Environment`, so that part is an inference. The
   operator's read-only check, any terminal on the Mac, under a minute:

   ```bash
   aws ce list-cost-allocation-tags --profile debate-admin --query 'CostAllocationTags[?TagKey==`Project` || TagKey==`Environment`].[TagKey,Status]' --output text
   ```

   Both keys reading `Active` means the tags are on and the empty rows need another explanation;
   `Inactive`, or no line for a key, means those budgets and the monitor have been reading $0. The
   PM decides what follows.
2. **The Nova Micro spend.** `Amazon Bedrock` / `USE1-NovaMicro-input-tokens` and
   `USE1-NovaMicro-output-tokens`, in September and October, counted and not this project's (names
   only). Left to the PM, with the coach and the operator; not investigated here.
3. **The 5.5 models' names** (`v1-e05-t17`, the PM's next batch): after their first billed call,
   re-run the runbook's counts, add the names to `local.model_services` / `local.model_usage_types`,
   the test's hand-written lists and the plan check's lists (and the first-reading block's filter),
   then plan and apply. Until then the budget does not see 5.5 spend, which today can only be prod's.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-30

**Notes:**

The coach's ceiling is a tested budget, filtered on what the bill actually says.
1. **ac1 passes.** The operator read Cost Explorer before any Terraform was written. The counts are
   names only, and they found what a guess would have missed: Claude and Cohere bill as Marketplace
   services, and `Amazon Bedrock` also carries spend that isn't this project's.
2. **ac2 passes.** Red against today's budget held in the module: 3 failed, each an assertion (the
   limit, the filter and the notices). Green: 4 passed, plus the no-grant pytest. The Terraform checks
   pass offline, with no lock file changed.
3. **Mutants:** the PM's five, each in several forms, plus the `Project` tag back, the usage-type key
   dropped, percentages, an SNS notice, a rename and the empty-address validation. All 17 are caught
   by assertions. Mutant 14 was redone when its first form errored instead of failing. Good.
4. **The plan check is the right shape.** It reads the saved plan's JSON. It counts permission set
   changes on change lines only, the lesson from 2026-10-29's image plan. It refuses any change but
   the budget, and it is tested red first (23 failed against a check that refuses nothing).
5. **Deviation 1 (two test files outside the packages): accepted.** The PM's next batch adds
   `tests/infrastructure` and `tests/docs` to the spec's packages. **Deviation 2 (3 min 23 s): noted**;
   it passed.
6. **Decisions 1 to 7: accepted.**
   * Locals, not inputs, so no tfvars line can raise the limit.
   * The plan check lives in the runbook for v1-e05-t17's re-apply.
   * The apply runs from an `origin/dev` worktree. The plan check refusing anything but the budget
     is what makes an account-wide root safe to apply from `dev`'s copy.
   * One tfvars copy, backed up before each edit.
   * The name kept, so the update is in place.
   * The counts block dated relative to today.
   * Nothing under `docs/data`.
7. **One guard to add:** the tfvars block appends `COACH_EMAIL`, whose shown value is the placeholder
   `the-coach@example.org`, and the plan check accepts any non-empty address. The PM's next batch adds
   a refusal of the placeholder to the tfvars block. Until then, the PM gives the operator the blocks
   with the address to set.
8. **The Nova Micro spend is explained.** The operator's other project, which shares this AWS account,
   generates text through Bedrock with `amazon.nova-micro-v1:0` (in that project's own code, read by
   the PM on 2026-10-30). It is not this project's, and the filter rightly leaves it out. No CloudTrail
   lookup is needed.
9. **Follow-up work:**
   * 1, the empty `Project` tag: the PM gives the operator the read-only check now, and the result
     decides whether a task follows;
   * 2: closed by note 8;
   * 3: the PM's next batch amends v1-e05-t17 as written.
10. **Merge `--partial`,** any time. ac3 is the operator's, after the merge and never on a Wednesday.
    The PM reads the plan and the plan check's line before the apply.

## Operator records (recorded by the PM, 2026-10-30)

Added by the PM. Nothing above is changed, and this section is not a review.

| Criterion | Was | Now | Record |
|---|---|---|---|
| ac3, plan, the PM's read and the apply | NOT RUN | PASS | 2026-10-30, from `model-spend-budget-apply` at `origin/dev` `9299ce8`: `Plan: 0 to add, 1 to change, 0 to destroy.`, no other change line, 0 permission set or assignment change lines; the plan check `PLAN OK … moved from aws_budgets_budget.bedrock_monthly … to 1 address(es)`; applied; `describe-budget` reads `100.0 USD MONTHLY` with notices at 50, 80 and 100 actual and 100 forecast, `ABSOLUTE_VALUE` |
| ac3, the first month's reading | NOT RUN | NOT RUN | Read the day after the apply, against Cost Explorer under the same filter |
| Follow-up 1, the cost allocation tags |  | Done | `aws ce list-cost-allocation-tags`: `Environment` and `Project` were `Inactive`; both set `Active` by the operator on 2026-10-30, no errors. Tagged spend reaches the environment budgets and the anomaly monitor from then on |
| Follow-up 2, the Nova Micro spend |  | Explained | The operator's other project, which shares the account, calls `amazon.nova-micro-v1:0` in us-east-1 (read by the PM in that project's code). Not this project's |

The Goal stays `InProgress` until the first reading is recorded.

## Operator records (recorded by the PM, 2026-10-31)

Added by the PM. Nothing above is changed, and this section is not a review.

| Criterion | Was | Now | Record |
|---|---|---|---|
| ac3, the first month's reading | NOT RUN | PASS | `describe-budget`, the day after the apply: limit `100.0`, actual spend `0.05`, forecast `None` (too early in the month). Cost Explorer under the same four services and four usage types, the month to yesterday: `0.02457124`. The budget reads spend above zero, so AWS Budgets matches the Marketplace service names as Cost Explorer does; the difference is the budget's rounding to cents and its counting part of today |

Every criterion passes, so the Goal is `Succeeded`.


# Session report: v1-e05-t13-dev-routes-to-callable-claude-models

| | |
|---|---|
| Task | `v1-e05-t13-dev-routes-to-callable-claude-models` — Dev routes to Claude models this account can call while the 5.5 quotas are held at zero |
| Spec | [`plan_specs/v1/e05-model-router/t13-dev-routes-to-callable-claude-models.yaml`](../../plan_specs/v1/e05-model-router/t13-dev-routes-to-callable-claude-models.yaml) |
| Epic / release | `v1-e05-model-router` / `v1.2` |
| Branch | `task/v1-e05-t13-dev-routes-to-callable-claude-models` |
| Session status | COMPLETE (the Goal stays `InProgress`: ac2 is the operator's plan, the PM's reading of it, the apply and step 7) |

## Summary

Dev's three Claude routes now go to models the account can call: `complex_reasoning` and
`high_volume` to Claude Haiku 4.5 (`anthropic.claude-haiku-4-5-20251001-v1:0`, profile
`us.anthropic.claude-haiku-4-5-20251001-v1:0`), and `deep_audit` to Claude Sonnet 4.6
(`anthropic.claude-sonnet-4-6`, profile `us.anthropic.claude-sonnet-4-6`). Each route keeps its region,
max_tokens and timeout, and the routing file's comment records the zero quotas, the support case and
the switch back. Prod's routing is unchanged. Both models are priced at the operator's 2026-10-27
reading, per 1,000 tokens. The invoker policy that both roots build from both routing files grows from 14
resources to 22: 5 profiles, the 15 Claude models behind them in the three destination regions, and the
2 scoring models. The module's Terraform tests pin those exactly, and the runbook gains a plan check of
its own for an update of the one inline policy, with the first-apply check kept and recounted.
**Look first at** the two questions for the PM under [Follow-up work](#follow-up-work): Haiku 4.5
costs ten times Haiku 5.5, and v1-e32-t07 classifies on `high_volume` under dev's $2 daily budget; and
nobody has checked yet whether the two new profiles send calls only to the three regions the grant
names. ac2 is the operator's, so the Goal stays `InProgress`.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `dev-fallback-routes` (Dev fallback routes) | Done | Tests first (commit `f047f21`, red), then the routing, pricing, module README and runbook (commit `83ba519`, green). 21 mutants, all caught. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| Node `dev-fallback-routes`: Routing and pricing tests pass | PASS | `uv run pytest packages/debate_core/tests/integrations/models -k "routing or pricing"` → `99 passed in 6.71s` (red at `f047f21`: `3 failed, 96 passed`, below). |
| ac1: Dev's routing names Haiku 4.5 and Sonnet 4.6 as above, both are priced, the module's Terraform tests pin the new policy exactly, and every pinned test passes; tests shown failing first where a rule changed | PASS | Routing and pricing tests as above. `uv run pytest packages/debate_core/tests/application/test_settings_environments.py` → `30 passed` (the family test, unchanged). `terraform -chdir=infrastructure/modules/bedrock_access test` → `Success! 9 passed, 0 failed.` (red at `f047f21`: `Failure! 7 passed, 2 failed.`). `scripts/terraform_checks.sh` → `All Terraform checks passed.`, exit 0 in 32 s. Red runs and mutants below. |
| ac2: The operator's Bedrock plan updates only the inline policy, read by the PM before the apply, and step 7's first call answers on both dev models (operator) | NOT RUN | It needs this branch merged into `dev`, the operator's AWS credentials, the PM's reading of the plan, and an apply. Commands under [Operator follow-ups](#operator-follow-ups). The update-case plan check was run against synthetic plans built from the module's real policies (below): `PLAN OK` for this change, `PLAN STOP` for each of ten wrong ones. |

### Red runs

At `f047f21`, the tests committed before the config change:

* `uv run pytest packages/debate_core/tests/integrations/models -k "routing or pricing" -p no:randomly -n 0 --tb=short`
  → `3 failed, 96 passed, 425 deselected`. Each test fails on its own assertion:
  * `test_pricing_file_has_an_entry_for_every_model_the_routing_files_route`: the dev routes differ.
    The test reads `{'complex_reasoning': 'anthropic.claude-haiku-5-5', …}` where it expects
    `'anthropic.claude-haiku-4-5-20251001-v1:0'`.
  * `test_pricing_every_committed_price_is_set_and_well_formed`: `anthropic.claude-haiku-4-5-20251001-v1:0`,
    `assert None is not None` (no entry).
  * `test_pricing_the_committed_prices_price_each_kind_of_call`: `assert None == 0.004 ± 4.0e-09`.
  * Already passing, as it should: `test_dev_routes_differ_from_prod_in_the_model_alone`, the new
    identifier-free rule. The rule did not change, because dev already kept prod's region,
    max_tokens and timeout. It is there so a change that breaks it is caught (mutants below).
* `terraform -chdir=infrastructure/modules/bedrock_access test` → `Failure! 7 passed, 2 failed.`, none
  skipped. Three assertions fail on their conditions, not on errors: the 22 resources (line 84), the
  five-profile condition (line 114) in `the_set_may_invoke_and_do_nothing_else`, and the count of 22 in
  `prod_names_its_own_set_and_grants_the_same_models` (`- 14 + 22`).

### Mutants

Twenty-one mutants, each planted alone in the committed file, run against the three Python test files
(`test_routing_policy.py`, `test_usage.py`, `test_settings_environments.py`; `-n 0 -p no:randomly`) and
the module's `terraform test`, then restored byte for byte (checked with `cmp`, and `git status` clean
afterwards). Each pytest run had a new, empty `HYPOTHESIS_STORAGE_DIRECTORY` (working agreement 8),
although none of these tests generate examples. The whole run took 40 s. All 21 were caught.

| Mutant | Caught by |
|---|---|
| **Prod's routing changed** (the PM's): prod `high_volume` to Haiku 4.5 | `test_pricing_file_has_an_entry_for_every_model_the_routing_files_route`; terraform (Haiku 5.5 no longer named: 2 runs fail) |
| prod `complex_reasoning` to Haiku 4.5 | the routed-models test and the family test `test_dev_routes_every_text_class_to_a_cheaper_model_than_prod`; terraform |
| prod `deep_audit` to Sonnet 4.6 | the routed-models test, the family test; terraform |
| prod `deep_audit` max_tokens 16384 to 8192 | `test_dev_routes_differ_from_prod_in_the_model_alone` (terraform passes: not a grant change) |
| prod `high_volume` timeout 60 to 120 | `test_dev_routes_differ_from_prod_in_the_model_alone` |
| **A wildcard in the policy** (the PM's): `*` region on the models behind the profiles | terraform, 3 runs fail, 0 skipped |
| `foundation-model/*` on the routes without a profile | terraform, 2 runs fail |
| `inference-profile/*` added beside the profiles | terraform, 3 runs fail |
| `bedrock:*` as the profiles' action | terraform, `the_set_may_invoke_and_do_nothing_else` |
| The condition names the first three profiles only | terraform: `Test assertion failed` at line 114 ("StringEquals the five profiles"). The later 5 skips follow from the mutant's own `slice` erroring on the one-profile fixture file, not from the catch. |
| A fourth destination region (`us-west-1`) | terraform, 3 runs fail |
| dev `deep_audit` to Haiku 4.5 | the routed-models test, the family test; terraform |
| dev `high_volume` left on Haiku 5.5 | the routed-models test (terraform passes: every ARN is still named by another route) |
| dev `high_volume` max_tokens 2048 to 4096 | `test_dev_routes_differ_from_prod_in_the_model_alone` |
| dev `deep_audit` timeout 600 to 300 | `test_dev_routes_differ_from_prod_in_the_model_alone` |
| dev `complex_reasoning` profile without its version | the routing policy refuses the file at load (5 tests); terraform |
| Haiku 4.5 input price per million (1.0), not per 1K | `test_pricing_every_committed_price_is_set_and_well_formed`, `…_price_each_kind_of_call` |
| Sonnet 4.6 input and output swapped | the same two |
| Sonnet 4.6 `as_of` 2026-10-26 | `test_pricing_every_committed_price_is_set_and_well_formed` |
| Haiku 5.5 `as_of` moved to 2026-10-27 | the same (per-entry `as_of`) |
| Haiku 4.5's entry removed | all three pricing tests |

### The runbook's plan checks, run against synthetic plans

The two Python checks in the runbook's step 2 were extracted from the runbook as written and run against
plan JSON built from the module's real policy output. That output came from a copy of the module in the
scratchpad under `mock_provider`, once with `566f9b8`'s dev routing and prod's, once with this branch's.
No account id appeared unmasked in any output.

* The update-case check: `PLAN OK: 1 to update, nothing else; bedrock:InvokeModel on 22 resources, 15
  Claude models through the 5 profiles; 8 added, none removed` for the real change. `PLAN STOP`, naming
  its reason, for each of ten wrong plans:
  * a wildcard model;
  * a wildcard profile;
  * a 5.5 model dropped;
  * an extra action;
  * a condition missing a profile;
  * a fourth region;
  * no policy change at all;
  * an unrelated resource deleted;
  * the policy replaced rather than updated;
  * a `NotResource` statement.
* The first-apply check: `PLAN OK: 3 to create, nothing else; bedrock:InvokeModel on 22 resources, 15
  Claude models through the 5 profiles` for the new grant. `PLAN STOP` for the old 14-resource grant
  and for a wildcard.

### Before the report

| Command | Result |
|---|---|
| `uv run scripts/affected_tests.py` | `161 of 541 test files (29.8%) chosen in 8.1 s from 9 changed files.` |
| `uv run scripts/affected_tests.py --run` | Stopped after about 3 minutes at 59%, with no failure in what had run, because it was past the two-minute line (the Mac's load average was 16). Under working agreement 10 the affected set is left to the pull request's `ci` check. |
| The changed tests' directories, what reads the changed config, the always-run list and the docs-check tests: `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest -n auto -m "not slow and not live"` over `packages/debate_core/tests/integrations/models`, `…/integrations/bedrock`, `…/application/test_settings_environments.py`, `test_settings.py`, `test_budget.py`, `tests/architecture`, `tests/specs`, `packages/debate_cli/tests/test_app.py`, `test_help_rendering.py`, `tests/docs`, `tests/scripts/test_check_command_blocks.py`, `tests/scripts/test_docs_index.py` | `1267 passed in 28.61s`, exit 0 |
| `uv run --frozen ruff check .` / `ruff format --check .` | `All checks passed!` / `1513 files already formatted` |
| `.venv/bin/pyright packages/debate_core` | `0 errors, 0 warnings, 0 informations` (23 s) |
| `uv run --frozen lint-imports` | `Contracts: 18 kept, 0 broken.` |
| `uv run --frozen python scripts/check_thin_handlers.py` | `OK: 67 CLI command and API route handlers within 25 statements` |
| `uv run --frozen python scripts/docs_index.py --check-descriptions` | `All 55 indexed documents under docs/ have a description` |
| `uv run --frozen python scripts/check_command_blocks.py --base origin/dev` | ``OK: no `#` comments in 510 shell code blocks in 189 Markdown files (1 session reports changed since origin/dev)`` |
| `TF_CLI_CONFIG_FILE=<the main checkout's provider mirror> bash scripts/terraform_checks.sh` | `All Terraform checks passed.`, exit 0, 32 s, offline; the `.terraform` directories it left were removed |
| `uv run scripts/validate_specs.py` | `OK: 480 files, 40 epics, 418 tasks, 22 releases` (the Goal stays `InProgress`) |

## Files changed

* `config/model_routing.dev.yaml`: the three Claude routes go to Haiku 4.5 and Sonnet 4.6, and a
  comment says why, until when, and what that costs.
* `config/model_pricing.yaml`: the two prices, `as_of: 2026-10-27`, with the per-million figures in
  the header comment.
* `infrastructure/modules/bedrock_access/tests/bedrock_access.tftest.hcl`: the exact 22 ARNs, the five
  profiles in the condition, and prod's count, written out by hand (working agreement 6).
* `infrastructure/modules/bedrock_access/README.md`: the grant's profiles and its count.
* `docs/runbooks/bedrock-access.md`: twenty-two resources; step 1's line for an existing set; step 2's
  first-apply check recounted (22, 5, 15) and a new block, "When the set already exists: one inline
  policy updated"; step 3's update line; step 7's request count (37), its cost, and how to read a run
  while the 5.5 quotas are held at zero.
* `packages/debate_core/tests/integrations/models/test_usage.py`: the routed models per file and class
  (prod's and the example's included), the committed prices with each entry's `as_of`, the two new
  models' costs, and a check that every committed price is for a routed model.
* `packages/debate_core/tests/integrations/models/test_routing_policy.py`: a new test,
  `test_dev_routes_differ_from_prod_in_the_model_alone`.

## Deviations from the spec

None.

## Decisions and assumptions

* **Where the prod pin lives.** No test pinned prod's routes, so "prod's routing changed" would have
  survived as a mutant before this task (prod's `high_volume` to Haiku 4.5, for instance, breaks no
  family assertion). `test_routing_policy.py` records the PM's ruling of 2026-10-16 that tests of the
  committed routing files assert families, not identifiers, so the identifiers went into the
  routed-model set in `test_usage.py`, which already pinned identifiers. That set is now a table per
  file and class. The routing tests gained one identifier-free rule instead: dev's routes equal prod's
  apart from `model_id` and `inference_profile`. That is the spec's "keeping each route's region,
  max_tokens and timeout", and it catches a prod max_tokens or timeout change too.
* **Every committed price is for a routed model.** The routed-models test now also asserts that
  `COMMITTED_PRICES` covers exactly the routed set. When dev goes back to the 5.5 models, the change that
  does it either removes the 4.x prices or loosens this assert. That is a choice for that change, and it
  is flagged here so it doesn't surprise anyone.
* **The first-apply check is recounted, not frozen at 14.** Prod's first apply comes after promotion and
  reads both routing files, so it will grant the 22 resources unless dev has gone back by then.
* **The update-case check pins the eight added resources by name** (account id masked), so it holds for
  this change only, and says so. A later routing change rewrites `expected_added`.
* **Step 7 may exit 1 and still be right.** `first_call` marks the other six probes `not tried` after an
  `AccessDeniedException` on the adapter's call, and exits 1 on any `not tried` row. It is not known
  whether Bedrock sends the zero-quota refusal as `AccessDeniedException` or as a `ValidationException`,
  so the runbook says what to read either way: dev's two adapter calls `accepted`, and every 5.5 refusal
  naming the account rather than `bedrock:InvokeModel`.
* **No price was written from memory.** The four figures are the spec's, from the operator's reading of
  2026-10-27, converted per 1,000 tokens.

## Operator follow-ups

All after this branch merges into `dev`, in the `caselist-credentials-dev` worktree, from
[`docs/runbooks/bedrock-access.md`](../runbooks/bedrock-access.md) at `origin/dev`. Steps 4 to 6 are not
repeated: the set, its profile and the account's model access already exist (v1-e05-t08's PM record).

**1. Variables, the worktree at `origin/dev` with this task merged.** `SSO_USER_NAME` is your Identity
Center user name, as in the runbook.

```bash
WT="$HOME/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/caselist-credentials-dev"
ENVIRONMENT=dev
SSO_USER_NAME='your-identity-center-user-name'

cd "$WT" || echo "STOP: the worktree is missing: $WT"
git fetch origin
git switch --detach origin/dev
grep -q 'claude-haiku-4-5-20251001-v1:0' config/model_routing.dev.yaml && echo "ok: $(pwd) at origin/dev $(git rev-parse --short HEAD), v1-e05-t13 merged" || echo "NOT MERGED: origin/dev has no v1-e05-t13"
git status --porcelain | grep -v 'owner.auto.tfvars' | head -3
```
Success looks like `ok: … v1-e05-t13 merged`, and nothing after it.

**2. Where the two new profiles send calls** (read-only, a few seconds, recommended before the plan).
The grant names the models in us-east-1, us-east-2 and us-west-2 only. This asks Bedrock which regions
each new profile actually uses. A foundation-model ARN names no account.

```bash
cd "$WT"
aws sso login --sso-session debate
for p in us.anthropic.claude-haiku-4-5-20251001-v1:0 us.anthropic.claude-sonnet-4-6; do echo "== $p"; aws bedrock get-inference-profile --profile debate-admin --region us-east-1 --inference-profile-identifier "$p" --query 'models[].modelArn' --output text | tr '\t' '\n' | sort; done
```
Success looks like three ARNs under each profile, in `us-east-1`, `us-east-2` and `us-west-2`. Any other
region (`us-west-1`, say) stops you: send the PM the lines, because calls routed there would be refused
and the module's region list has to change first, never with a wildcard.

**3. Sign in and the plan:** the runbook's "Sign in…" block, its `owner.auto.tfvars` block (it prints
`1` and changes nothing), and step 1, as written. **What to read:** the first `grep` prints exactly
`Plan: 0 to add, 1 to change, 0 to destroy.`, with no `must be replaced` or `will be destroyed` line, and
the second prints nothing. Anything else stops you: send `/tmp/bedrock-access-dev-plan.txt` to the PM.

**4. The check:** the runbook's step 2 block "When the set already exists: one inline policy updated", as
written (~1 min). Success looks like `PLAN OK: 1 to update, nothing else; bedrock:InvokeModel on 22
resources, 15 Claude models through the 5 profiles; 8 added, none removed`. Send the PM the plan file and
that line either way. **The PM reads both before step 5** (ac2).

**5. The apply**, only after the PM's word: the runbook's step 3, as written. Success looks like
`Apply complete! Resources: 0 added, 1 changed, 0 destroyed.`, then `"DebateDevBedrockInvoker"` and
`"debate-dev-bedrock"`. `Saved plan is stale` means go back to 3.

**6. The first call:** the runbook's step 7, as written (~2 min, about five cents for dev's two models).
Read it as that step's "While the account's 5.5 quotas are held at zero" says. Dev's Haiku 4.5 and
Sonnet 4.6 adapter calls read `accepted`; the 5.5 rows are refused as "not available for this account"
(expected); `first call exit=1` is expected if those refusals arrive as `AccessDeniedException`. Send
the PM `/tmp/bedrock-first-call-dev.md`.

## Follow-up work

**Questions for the PM**, paste-ready:

> **v1-e05-t13: two questions before v1-e32-t07's live run in dev**
>
> 1. **Dev's budget against Haiku 4.5's price.** v1-e32-t07 classifies on `high_volume`
>    (`CLASSIFICATION_TASK_CLASS` in `landscape_model_stage.py`). In dev that is now Haiku 4.5 at $1 and
>    $5 per million tokens, ten times Haiku 5.5's $0.10 and $0.50, under dev's `budget_usd_daily = 2.0`.
>    One `high_volume` call's ceiling is up to 2,048 output tokens, about $0.01 on Haiku 4.5, and
>    `BudgetGuard` charges actual spend plus the ceilings of calls in flight. As a rough estimate, not a
>    measurement: a 20-card batch of about 3,000 tokens in and 1,000 out costs about $0.008, so $2 is
>    roughly 250 batches, about 5,000 cards a day, against about 50,000 on Haiku 5.5. If the newest
>    hspolicy26 snapshot leaves more unmatched cards than that, the run stops at the day's limit, with
>    what it has written kept.
>    Options: (a) leave $2 and run in daily parts, or with `max_model_items`; (b) raise dev's daily
>    budget for the quota window in `config/profiles/dev.toml`, which is a v1-e01-t09 channel value, so
>    a PM batch or a task of its own; (c) run t07's live pass on prod's routing.
>    **Recommendation: (a)** unless the unmatched count is known to be large. The run already resumes
>    and caps, and (b) changes a ceiling the spec set at "at most $2" for a temporary price.
> 2. **The two new profiles' regions are not yet checked.** The grant names Haiku 4.5 and Sonnet 4.6 in
>    us-east-1, us-east-2 and us-west-2, the regions the 5.5 profiles use. Nobody has asked Bedrock
>    whether these two profiles route anywhere else; if either does, calls served there would be refused. Operator follow-up 2
>    is a read-only check of this before the plan. If it shows a fourth region, the module's
>    `profile_destination_regions` gains it (a reviewed change, never a wildcard), and the counts in the
>    tests and the runbook change with it.
>    **Recommendation:** run that check before the plan. It takes seconds and decides whether this
>    branch is enough as it stands.

**The PM's rulings, 2026-10-27** (with the review below):

* **Question 1: (a).** Dev's daily budget stays at $2. v1-e32-t07's first live pass in dev is a
  capped sample (`max_model_items`, about 500 cards), so its usage log gives a measured cost per card.
  The PM re-scopes v1-e05-t14 to project that sample's tokens at both Haiku 4.5's and Haiku 5.5's
  prices, against the coach's ceiling of $50 a month across dev and prod.
* **Question 2: yes.** The operator runs follow-up 2 (the two profiles' regions) before the plan. A
  fourth region stops everything and comes back to the PM.

* When the support case restores the 5.5 quotas, the PM files the task that switches dev back to
  Haiku 5.5 and Sonnet 5.5, takes the grant back to 14 resources, updates the update-case check's
  expected resources (as removals), and decides whether the 4.x prices stay in `config/model_pricing.yaml` (the routed-models test asserts
  they do not; [Decisions](#decisions-and-assumptions)). Epic `v1-e05-model-router`.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-27

**Notes:**

Dev's fallback built tightly: prod untouched and now pinned, the grant exact at 22 resources, and a
plan check of its own for the update.
1. **ac1 and the node's criterion pass.**
   * Red first in both Python and Terraform, each failing on its own assertion.
   * `terraform test` reads 9 of 9 passed, and `scripts/terraform_checks.sh` passes offline.
   * The new identifier-free rule (dev equals prod apart from the model) closes a gap no test covered
     before.
2. **Mutants: 21, the PM's two among them, all caught.** They include five wildcard and region
   variants, and a prod max_tokens or timeout change.
3. **Both runbook checks were run against synthetic plans** built from the module's real policies:
   `PLAN OK` for this change, and `PLAN STOP` for ten wrong ones.
4. **Ruling on question 1: (a).**
   * Dev's $2 daily budget stays.
   * v1-e32-t07's first live pass runs capped with `max_model_items` at a sample (about 500 cards),
     so its usage log gives a measured cost per card.
   * The coach's ceiling is $50 a month across dev and prod. The PM re-scopes v1-e05-t14 to project
     that sample's tokens at both Haiku 4.5's and Haiku 5.5's prices, since the fallback costs ten
     times the intended model.
5. **Ruling on question 2: yes.** The operator runs follow-up 2 (the profiles' regions) before the
   plan. A fourth region stops everything and comes back to the PM.
6. **Decisions accepted:**
   * the prod pin in the routed-models table;
   * every committed price for a routed model, flagged for the switch back;
   * the first-apply check recounted;
   * the update check pinned to this change's eight additions;
   * step 7's exit 1 read by its rows.
7. **The switch back** is filed by the PM when the support case restores the 5.5 quotas.
8. **The affected set** (161 files) passed what ran before the two-minute line, and the rest is left to
   the PR's `ci` under agreement 10. The changed directories, the config readers, the always-run list
   and the static checks are clean.

No re-review is needed. The PR merges `--partial`, phase `InProgress`, until ac2's plan, apply and
first call. The PM reads the plan before the apply.

## PM record, 2026-10-27

Added by the PM. Nothing above is changed, and this section is not a review.

ac2, from the `caselist-credentials-dev` worktree at `origin/dev` `7d66965`, on 2026-10-27:

* **Follow-up 2, the profiles' regions:** both inference profiles route only to us-east-1,
  us-east-2 and us-west-2.
* **Step 1, the plan:** `Plan: 0 to add, 1 to change, 0 to destroy.`, the invoker set's inline
  policy updated in place and nothing else. The PM read it before the apply.
* **Step 2, the check:** `PLAN OK: 1 to update … 22 resources, 15 Claude models through the 5
  profiles; 8 added, none removed`.
* **Step 3, the apply:** `Apply complete! Resources: 0 added, 1 changed, 0 destroyed.`, then
  `"DebateDevBedrockInvoker"` and `"debate-dev-bedrock"`.
* **Step 7, the first call** (the runbook's `first_call` probe over both routing files):
  * **Haiku 4.5** (`us.anthropic.claude-haiku-4-5-20251001-v1:0`) and **Sonnet 4.6**
    (`us.anthropic.claude-sonnet-4-6`): the adapter's own call, `toolChoice any`, `toolChoice tool`,
    `temperature 0.5`, structured output and the strict tool were all accepted. `effort low` was
    refused on both: `ValidationException`, "This model doesn't support the effort field".
  * **Titan** embeddings answered with 1,024 dimensions, and **Cohere Rerank 3.5** answered.
  * **Haiku, Sonnet and Opus 5.5** were refused as "not available for this account"
    (`AccessDeniedException`, the zero quota), so their other probes read `not tried`.
  * `first call exit=1`, as the runbook says to expect while the 5.5 quotas are held at zero. The
    summary line: 14 requests accepted and billed, 6,861 input and 484 output tokens; 5 refused.
    Priced at Sonnet 4.6's rates throughout, that is under 3 cents.

Both dev models answered, so ac2 passes and the Goal is `Succeeded`. The `effort` refusal touches no
route today, since dev's routes set no effort; `v1-e05-t11` carries it. The switch back to the 5.5
models is `v1-e05-t17`.

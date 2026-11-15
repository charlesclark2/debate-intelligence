# Session report: v1-e05-t20-prod-routes-on-the-4x-models

| | |
|---|---|
| Task | `v1-e05-t20-prod-routes-on-the-4x-models` — Prod's model routes, grant and first calls on the models dev already uses |
| Spec | [`plan_specs/v1/e05-model-router/t20-prod-routes-on-the-4x-models.yaml`](../../plan_specs/v1/e05-model-router/t20-prod-routes-on-the-4x-models.yaml) |
| Epic / release | `v1-e05-model-router` / `v1.2` |
| Branch | `task/v1-e05-t20-prod-routes-on-the-4x-models` |
| Session status | PARTIAL: the session's work is done and ready for review, with the PM's rulings of 2026-11-15 recorded; ac3 is the operator's, so the Goal stays `InProgress` |

## Summary

Prod's routing (`config/model_routing.prod.yaml`) now routes every task class to the model dev routes
it to: `complex_reasoning` and `high_volume` to Claude Haiku 4.5, `deep_audit` to Claude Sonnet 4.6, and
embeddings and rerank unchanged. Every route keeps its region, `max_tokens` and timeout. The operator's
quota reading of 2026-11-15, taken before the change, shows both models non-zero in all three regions.
Both are already priced in `config/model_pricing.yaml`, and prod's $50 monthly limit is unchanged. The
Bedrock invoker grant is read from both routing files, so it narrows in both roots from twenty-two
resources to ten. The module's tests pin the ten at apply and at plan time, and were shown failing
first, along with the Python pins. Seven mutants were all caught: prod sent back to a 5.5 model, and
five ways of widening the grant. **What the PM should read first:** prod's set already exists. It was
created on 2026-11-03 with nobody assigned, and it already grants Haiku 4.5 and Sonnet 4.6, so for prod
this change is a narrowing plus your account assignment. It rides in the promotion's prod plan if
this merges before the cut (ruling Q3). Dev's matching update rides in `v1-e40-t48`'s Monday dev plan
if t48 has not been applied by then. One check in step 2 of the runbook reads every case. **PM rulings
of 2026-11-15:**
* ac2 is NOT APPLICABLE until a landscape model stage is on in prod (Q1).
* `complex_reasoning` on Haiku 4.5 is confirmed for now; v1-e09-t03/t04's golden evaluation decides it
  before the student release (Q2).
* The grant rides in the promotion's prod plan, and dev's in t48's plan when it has not been applied
  (Q3).
* Your assignment is created in the same plan as the grant change (Q4).

ac3 is the operator's, and the Goal stays `InProgress`.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `prod-routes-on-the-4x-models` (Prod on 4.x) | Session part done | Quotas read first (operator), red tests committed (`e6c77b8`), routing and grant (`52be95c`), runbook (`c415f38`), the PM's rulings (this report's last commit). The node criterion passes; ac2 is NOT APPLICABLE by ruling, ac3 is open |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: prod's routing names the models dev routes to (or the PM's ruling for a class that differs), the grant names exactly what the routing files route to, the prices are from the pricing file, and the module's tests pin it, shown failing first | PASS | **Quotas first** (operator, 2026-11-15, the block in Operator follow-ups): Haiku 4.5 `5000000.0` and Sonnet 4.6 `6000000.0`, cross-region and global cross-region, in each of us-east-1, us-east-2 and us-west-2; none zero. **Red** (`e6c77b8`, routing unchanged): `pytest test_settings_environments.py test_usage.py -k "prod_routes or quota_is_held or pricing_file_has"` → `3 failed, 1 passed`, each at its assertion (prod's routes, the 5.5 models found in prod, the routed-models table). `terraform test` (offline mirror) → `Failure! 7 passed, 4 failed`, all 7 errors `Test assertion failed`: the ten resources (apply, prod's count, the two plan-time runs), the two conditioned profiles, and no wildcard or 5.5 resource. **Green** (`52be95c`): `terraform test` → `Success! 11 passed, 0 failed`; `pytest test_settings_environments.py integrations/models/` → `604 passed in 4.06s`. **Prices:** both models were already in `config/model_pricing.yaml` (operator reading of 2026-10-27), and `test_pricing_file_has_an_entry_for_every_model_the_routing_files_route` holds every routed model priced. **No class differs from dev's** (Decisions 1). **Mutants:** 7 of 7 caught (table below) |
| ac2: prod makes no model call for an item dev has classified at the same prompt version and model, by test, before prod's first live call | NOT APPLICABLE | The PM's ruling of 2026-11-15 (Q1): not applicable until a landscape model stage is on in prod; the PM amends ac2 in the next batch. Nothing in V1 calls the stage. The reuse becomes a condition of `v1-e32-t66` before any prod live call: the model in `ClassificationKey`, and prod reading dev's classifications. A test is not cheap with today's cache: Deviations 1 |
| ac3: prod's plan and apply, the PM reading the plan, the first call answered on each prod route, and the spend budget's lists checked after the first billed calls (operator) | NOT RUN | The operator's and the PM's, after the merge and the promotion's cut. The order and the blocks are in Operator follow-ups |
| Node: `uv run pytest packages/debate_core/tests -k "routing or bedrock or budget"` | PASS | `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests -k "routing or bedrock or budget" -q` → `287 passed in 55.17s` |

**Mutants.** Each one was applied to the committed tree, its tests were run, and then it was restored
with `git checkout HEAD --`. Every failure was `Test assertion failed`, with no other error.

| # | Mutant | Caught by |
|---|---|---|
| 1 | prod's `complex_reasoning` back to Sonnet 5.5 (`config/model_routing.prod.yaml`) | Python: prod's routes, the zero-quota check, the routed-models table (3 failed). Terraform: 4 runs (the apply and plan pins, prod's count, dev's plan) |
| 2 | prod's `deep_audit` back to Opus 5.5 | the same 3 Python tests and 4 Terraform runs |
| 3 | grant: a wildcard `foundation-model/*` for the routes without a profile (`main.tf`) | 4 Terraform runs |
| 4 | grant: a fourth destination region, us-west-1 | 5 Terraform runs |
| 5 | grant: the models behind the profiles without the `bedrock:InferenceProfileArn` condition | 2 Terraform runs (the condition assertions at apply and at plan) |
| 6 | grant: `inference-profile/*` beside the routed profiles | 5 Terraform runs |
| 7 | grant: the Opus 5.5 profile kept beside the routed ones | 5 Terraform runs |

**Before the report:**

* `uv run scripts/affected_tests.py` → `227 of 777 test files (29.2%) chosen`. With `--run --slow`
  under `hard_stop.py 115`, it was stopped at its limit (exit 124) at 54%, with no failure or error
  mark up to that point. Under agreement 10, an affected set over about two minutes is left to the
  pull request's `ci` check. The test directories of what changed ran within the limit (604 and 287
  above), and so did the always-run list: `pytest tests/architecture tests/specs
  packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py
  packages/debate_cli/tests/test_container_factories.py tests/smoke/test_usage_smoke.py` →
  `382 passed in 20.21s`.
* `ruff format --check .` → `2147 files already formatted`; `ruff check .` → `All checks passed!`;
  `pyright` (whole project, as CI runs it) → `0 errors, 0 warnings, 0 informations`; `lint-imports`
  → `Contracts: 20 kept, 0 broken.`; `uv run scripts/validate_specs.py` → `OK: 690 files, 41 epics,
  627 tasks, 22 releases`.
* Terraform: `TF_CLI_CONFIG_FILE=<offline mirror> bash scripts/terraform_checks.sh` →
  `All Terraform checks passed.` (36 ok, 40 s), with no lock file changed and the `.terraform`
  directories it left removed. `terraform fmt -check` is clean on both modules.
* Docs: `scripts/check_command_blocks.py` → `OK: no # comments in 735 shell code blocks`;
  `scripts/check_links.py` → `OK: 3921 relative links and anchors`; `scripts/docs_index.py
  --check-descriptions` → all 72 described.
* **Step 2's update check, exercised offline**, after the rulings. The check is lifted from the
  runbook and run on eight synthetic plans:
  * `PLAN OK` for dev's update alone;
  * `PLAN OK` for dev's update inside a plan shaped like t48's (two task definitions replaced, four
    updates), with 6 counted outside;
  * `PLAN OK` for prod's update with your assignment inside a promotion that creates another
    assignment, with 2 outside and 2 created in the whole plan;
  * `PLAN STOP` for a permission set replaced elsewhere in the plan;
  * `PLAN STOP` for an account assignment destroyed elsewhere, printing its key as `["<name>"]`;
  * `PLAN STOP` for another user's assignment, also masked;
  * `PLAN STOP` for a wildcard added and for a 5.5 profile kept.

  After the routing file's comment change: `terraform test` → `Success! 11 passed, 0 failed`;
  `pytest test_settings_environments.py integrations/models/` → `604 passed in 4.32s`.
  The spend-names block below was exercised the same way: `SPEND NAMES OK: nothing to add` for prod
  on dev's names, and `NOT LISTED` for a new usage type and for a new service.

## Files changed

* **`config/model_routing.prod.yaml`**: the three Claude routes go to dev's models, and the header
  says why, with the quota reading. It also says that `complex_reasoning` on Haiku 4.5 is confirmed
  for now, not final: v1-e09-t03's and v1-e09-t04's golden evaluation decides whether it moves to
  Sonnet 4.6 before the student release, a routing change only, since the grant names both (ruling Q2). **`config/model_routing.dev.yaml`**: only its header comment
  changed. It said dev runs one tier cheaper than prod and that prod was unchanged, which is no longer
  true.
* **`infrastructure/modules/bedrock_access/tests/bedrock_access.tftest.hcl`**: the hand-written pins go
  from 22 resources to 10, and from five conditioned profiles to two. Two new `command = plan` runs pin
  prod's and dev's grant at plan time, including no wildcard and no 5.5 resource.
  **`README.md`**: the counts.
* **`packages/debate_core/tests/application/test_settings_environments.py`**:
  `test_dev_routes_every_text_class_to_a_cheaper_model_than_prod` is replaced by
  `test_prod_routes_each_class_to_the_model_dev_routes_it_to` and
  `test_no_environment_routes_to_a_model_whose_quota_is_held_at_zero`.
  **`.../integrations/models/test_usage.py`**: prod's row of `ROUTED_MODELS`.
* **`docs/runbooks/bedrock-access.md`**:
  * what the sets grant (ten resources);
  * step 2's update check, rewritten for this change. It reads `module.bedrock_access` alone, and over
    the whole plan refuses a permission set or account assignment destroyed or replaced (ruling Q4).
    It has one short block per plan it can read: a plan of its own, t48's Monday dev plan, or the
    promotion's prod plan (ruling Q3);
  * the first-apply check's counts;
  * `--no-cli-pager` and the 2026-11-15 reading on the quota command;
  * the order for prod, dev's either-case rule, prod's first-call block and how to read it.
* **`infrastructure/modules/model_spend_budget/{main.tf,README.md}`** and
  **`docs/runbooks/aws-account-baseline.md`**: comments only. They said `v1-e05-t17` would add "the
  5.5 models of prod's routes". They now say prod's routes are the names already listed, and that
  the 5.x models come with `v1-e41-t20`. The budget's resources do not change.

## Deviations from the spec

1. **ac2 is NOT APPLICABLE until a landscape model stage is on in prod (the PM's ruling of 2026-11-15,
   Q1); it is not tested here, and the PM amends ac2 in the next batch.** A test
   of the reuse rule is not cheap with the existing classification cache:
   * `ClassificationKey` is topic, taxonomy version, override digest, prompt version and item
     fingerprint, with **no model id**. "Classified at the same prompt version and model" cannot be
     expressed in it. Today a cache hit ignores the model, so after a route change it would reuse
     another model's answers.
   * Each environment's cache is a file under its own data directory,
     `<data_dir>/landscape/classifications/<caselist>.jsonl`, and **no prod run reads dev's**.

   A test of prod reusing dev's results would first need a feature: the model in the key, and a way
   for prod to read or import dev's cache. By the ruling no task is filed now: that reuse becomes a
   condition of `v1-e32-t66` before any prod live call, written into t66's description by the PM.
2. **The spec's description says "Then prod's plan and apply"**, as if prod's grant were new. Prod's set
   has existed since 2026-11-03 with nobody assigned and the 22-resource grant of the time (the
   evidence-search runbook's step 11 record, main at `3f827613`). So prod's plan is one policy update,
   twelve resources removed, plus the operator's first assignment, which comes from `owner.auto.tfvars`
   and not from code. Nothing in the spec changes; this is how ac3 reads now.

## Decisions and assumptions

1. **Class for class, confirmed for now (the PM's ruling of 2026-11-15, Q2).** Prod sent `deep_audit`
   to Opus 5.5, and dev routes it to Sonnet 4.6, so prod now does too. Nothing in V1 calls
   `deep_audit`: no `TaskClass.DEEP_AUDIT` appears in any caller. `complex_reasoning`, card selection for
   `cut` and auto-cut, goes to Haiku 4.5 in prod, as in dev. This is not final: card selection is the
   core of what students get, so v1-e09-t03's and v1-e09-t04's golden evaluation decides whether it
   moves to Sonnet 4.6 before the student release. The grant names both models, so that move would be
   a routing change only. The routing file's comment says so.
2. **The quota read covers prod.** Dev and prod are one account (ADR-0010), so there is one set of quotas.
   It was read anyway, as the PM asked, in the three regions a `us.` profile sends calls to.
3. **`test_dev_routes_differ_from_prod_in_the_model_alone`** (test_routing_policy.py) is kept. It passes
   trivially now that the files are equal, and it will hold again when they part.
4. **The prod first call runs from a source checkout of `origin/main`**, with `DEBATE_ENV=prod`. That is
   neither an installed stable build nor the dev build: it is the stable build's code and routing file,
   signed with `debate-prod-bedrock`. Step 7's probe is a module (`debate_core.integrations.bedrock.first_call`)
   run with `uv run`, and installs nothing. It reads prod's routing file alone: 16 requests. Computed at
   the pricing file's prices with 400 input tokens a request, that is $0.053 at 300 output tokens a
   request and $0.298 at the 2,048 cap. The probe calls the adapter directly, so it is billed by AWS but
   is not in the usage log.
5. **The spend check prints names, not amounts.** The baseline runbook's block prints amounts, and the
   operator is told to record names only; output shown only in the terminal tends to get pasted. The
   block below reads the same Cost Explorer grouping and prints only names, each marked `listed` or
   `NOT LISTED` against `model_spend_budget`'s own lists. Amazon Bedrock rows for Nova Micro, which is
   not this project's, would show as `NOT LISTED` usage types; that is expected, and the budget leaves
   them out on purpose.

## Operator follow-ups

The order. **Never on a Wednesday, and never two prod plans the same weekend.** Every plan is read by
the PM before its apply.

1. **Done 2026-11-15: the quota read**, before the routing change, with the result in ac1. This is the
   block as run; `--no-cli-pager` is added because the answer opened in a pager:

   ```bash
   aws sso login --sso-session debate
   for region in us-east-1 us-east-2 us-west-2; do echo "== $region"; aws service-quotas list-service-quotas --no-cli-pager --profile debate-admin --region "$region" --service-code bedrock --query "Quotas[?contains(QuotaName, 'tokens per minute') && (contains(QuotaName, 'Haiku 4.5') || contains(QuotaName, 'Sonnet 4.6'))].[QuotaName, Value]" --output text; done
   ```

2. **Dev's plan for the same policy update, after this merges into `dev`** (ruling Q3). Never a
   second dev plan the same day, never on a Wednesday. Use exactly one of these two cases.

   **(a) `v1-e40-t48`'s fix has not been applied yet: dev's change rides in t48's Monday dev plan.**
   The PM tells the t48 session to expect an in-place update of `module.bedrock_access` in it. t48's
   own check passes only when nothing outside its change moves, so it is widened there. Run t48's
   blocks 0 to 7 as written; its block 1 switches the worktree to `origin/dev`, which then carries this
   task. Then, in t48's worktree and shell, after its block 7 has written its plan's JSON, run this
   (seconds):

   ```bash
   cd "$WT"
   grep -q 'claude-haiku-4-5' config/model_routing.prod.yaml && echo "ok: $(git rev-parse --short HEAD) carries v1-e05-t20" || echo "STOP: this worktree has no v1-e05-t20; its plan holds no bedrock change"
   PLAN_JSON=/tmp/caselist-schedule-scheduled-plan.json
   ```

   Then run the check block of [bedrock-access.md step 2](../runbooks/bedrock-access.md#when-the-set-already-exists-one-inline-policy-updated),
   the one that starts `test -s "$PLAN_JSON"`, in the same shell. It should print `PLAN OK:
   module.bedrock_access: 1 policy update, no assignment created; bedrock:InvokeModel on 10 resources,
   6 Claude models through the 2 profiles; 12 removed, none added; changes outside
   module.bedrock_access: <t48's count>; permission sets or account assignments created in the whole
   plan: 0, none destroyed or replaced`. t48's `Plan:` line then has one change more than t48 alone.
   Send the PM both checks' lines with t48's plan. t48's apply, its block 8, applies both, and
   bedrock-access.md's step 3 is not run.

   **(b) t48's fix is already applied: dev's plan of its own.** In the dev apply worktree at
   `origin/dev`, run [bedrock-access.md](../runbooks/bedrock-access.md) Before you start with
   `ENVIRONMENT=dev`, then step 1. The plan should read `Plan: 0 to add, 1 to change, 0 to destroy.`.
   Then run this (seconds):

   ```bash
   cd "$WT"
   PLAN_JSON="/tmp/bedrock-access-${ENVIRONMENT}-plan.json"
   AWS_PROFILE=debate-admin terraform -chdir="infrastructure/envs/${ENVIRONMENT}" show -json bedrock-access.tfplan > "$PLAN_JSON"
   ```

   Then run the same check block. It should print the line above, with `changes outside
   module.bedrock_access: 0`. After the PM's word, run step 3; it should read `0 added, 1 changed`.
3. **Before the promotion's prod plan** (ruling Q4): add your `bedrock_invoker_user_names` line to prod's
   `owner.auto.tfvars`, with Before you start's second block and `ENVIRONMENT=prod`, in the worktree
   the promotion plans prod from. It should print `1`. The value is never pasted into a session or a
   chat; the block prints only the count.
4. **The promotion's prod plan carries this change** if this merges into `dev` before the cut. No
   separate prod plan is made. In the promotion's worktree, with `PROMOTION_PLAN` set to that plan's
   saved file, relative to `infrastructure/envs/prod`, run this (seconds):

   ```bash
   PROMOTION_PLAN='the-promotions-saved-plan.tfplan'
   PLAN_JSON=/tmp/bedrock-access-prod-plan.json
   AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/prod show -json "$PROMOTION_PLAN" > "$PLAN_JSON"
   ```

   Then run step 2's check block in the same shell, with `SSO_USER_NAME` set as Before you start sets
   it. It should print `PLAN OK: module.bedrock_access: 1 policy update, and your assignment created;
   ...; 12 removed, none added; changes outside module.bedrock_access: <the promotion's count>;
   permission sets or account assignments created in the whole plan: <at least 1>, none destroyed or
   replaced`. A destroyed or replaced permission set or account assignment anywhere is `PLAN STOP`.
   Creating one is expected, and is what the PM reads for. If this merges after the cut, the change
   waits for the next promotion. Prod's current set already grants both 4.x models, and prod's routes
   reach the stable build only with a promotion anyway.
5. **After the apply: prod's profile**, step 4 with `ENVIRONMENT=prod`. It should print
   `AWSReservedSSO_DebateProdBedrockInvoker`.
6. **Prod's first calls**, from the same `origin/main` worktree after the promotion (`$WT`, per the
   runbook's Prod section). Expected runtime is about 2 minutes, and it makes 16 billed requests, about
   five cents.

   ```bash
   cd "$WT"
   aws sso login --sso-session debate
   if env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell:"; env | grep -oE '^DEBATE_[A-Z_]*'; else env -u AWS_PROFILE DEBATE_ENV=prod uv run python -m debate_core.integrations.bedrock.first_call --routing-file config/model_routing.prod.yaml > /tmp/bedrock-first-call-prod.md; echo "first call exit=$?"; cat /tmp/bedrock-first-call-prod.md; fi
   ```

   Success looks like the first line `Signed with AWS profile debate-prod-bedrock (models.aws_profile,
   DEBATE_ENV=prod).`, the adapter's own call `accepted` for `us.anthropic.claude-haiku-4-5-20251001-v1:0`
   and for `us.anthropic.claude-sonnet-4-6`, the embedding and the rerank accepted, and `first call
   exit=0`. A refused probe other than the adapter's call is a finding; `effort low` was refused in dev.
   Send the PM the whole file, `/tmp/bedrock-first-call-prod.md`; account ids in it are already masked.
7. **The day after the first calls: the spend names.** Cost Explorer lags by up to a day. This block
   is read-only and runs in under a minute in `$WT`, which holds `model_spend_budget/main.tf`. It
   prints service and usage-type names and counts only, never an amount or an account id. It is not
   for the first of a month.

   ```bash
   cd "$WT"
   aws sso login --sso-session debate
   rm -f /tmp/model-spend-names.json
   if [ "$(date +%d)" = "01" ]; then echo "STOP: the first of a month has no day to list yet; run this tomorrow"; else aws ce get-cost-and-usage --no-cli-pager --profile debate-admin --time-period Start=$(date -v1d +%F),End=$(date +%F) --granularity MONTHLY --metrics UnblendedCost --group-by Type=DIMENSION,Key=SERVICE Type=DIMENSION,Key=USAGE_TYPE --output json > /tmp/model-spend-names.json; fi
   python3 -I - /tmp/model-spend-names.json infrastructure/modules/model_spend_budget/main.tf <<'SPENDNAMES'
   import json, os, re, sys
   if not os.path.exists(sys.argv[1]) or os.path.getsize(sys.argv[1]) == 0:
       sys.exit("STOP: Cost Explorer was not read; paste the lines above")
   listing = json.load(open(sys.argv[1]))
   module = open(sys.argv[2]).read()
   def listed(name):
       body = re.search(name + r"\s*=\s*\[(.*?)\]", module, re.S).group(1)
       return set(re.findall(r'"([^"]+)"', body))
   services, usage_types = listed("model_services"), listed("model_usage_types")
   rows = set()
   for period in listing.get("ResultsByTime", []):
       for group in period.get("Groups", []):
           service, usage_type = group["Keys"]
           if float(group["Metrics"]["UnblendedCost"]["Amount"]) == 0:
               continue
           if service == "Amazon Bedrock" or service.endswith("(Amazon Bedrock Edition)"):
               rows.add((service, usage_type))
   missing_services = sorted({s for s, _ in rows} - services)
   missing_types = sorted({(s, u) for s, u in rows if u not in usage_types})
   print("model charge rows this month: %d; services listed in the budget: %d; usage types listed: %d" % (len(rows), len(services), len(usage_types)))
   for s in sorted({s for s, _ in rows}):
       print(("listed     " if s in services else "NOT LISTED ") + "service: " + s)
   for s, u in sorted(rows):
       print(("listed     " if u in usage_types else "NOT LISTED ") + "usage type: " + s + " | " + u)
   if listing.get("NextPageToken"):
       print("INCOMPLETE: Cost Explorer returned more pages than this listing shows")
   print("SPEND NAMES OK: nothing to add" if rows and not missing_services and not missing_types else ("SPEND NAMES: no model charge this month yet" if not rows else "SPEND NAMES: %d service(s) and %d usage type(s) not listed; paste this output to the session" % (len(missing_services), len(missing_types))))
   SPENDNAMES
   ```

   Success looks like `SPEND NAMES OK: nothing to add`, expected since prod's calls bill under the
   same names as dev's. Anything `NOT LISTED` other than an Amazon Bedrock Nova usage type means the
   name is added to `model_spend_budget`'s two lists and its test, and the organization root is planned
   and applied as [aws-account-baseline.md](../runbooks/aws-account-baseline.md#applying-a-change-to-the-budget)
   says. That root is account-wide, not a prod plan. Paste back the whole output; it holds no amounts.

**The PM's rulings of 2026-11-15**, as recorded above:

* **Q1 (a):** ac2 is NOT APPLICABLE until a landscape model stage is on in prod.
* **Q2 (a):** `complex_reasoning` stays on Haiku 4.5 for now; v1-e09-t03/t04 decide it.
* **Q3 (a):** the grant rides in the promotion's prod plan; dev's in t48's Monday plan if t48 is
  unapplied.
* **Q4 (a):** your assignment is created in the promotion's prod plan; a destroyed or replaced
  permission set or assignment is refused.

## Follow-up work

1. **No task is filed for ac2's reuse** (ruling Q1). The model in `ClassificationKey`, and prod reading
   dev's classifications, become a condition of `v1-e32-t66` before any prod live call, written into
   t66's description by the PM.
2. **The `doctor --routing-file` row on an installed stable build** would show the bundled prod routes
   without a model call. Nothing here needs it, but the PM may want it in the promotion's smoke list.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

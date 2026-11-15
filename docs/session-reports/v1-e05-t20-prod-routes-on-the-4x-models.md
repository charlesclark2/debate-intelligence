# Session report: v1-e05-t20-prod-routes-on-the-4x-models

| | |
|---|---|
| Task | `v1-e05-t20-prod-routes-on-the-4x-models` — Prod's model routes, grant and first calls on the models dev already uses |
| Spec | [`plan_specs/v1/e05-model-router/t20-prod-routes-on-the-4x-models.yaml`](../../plan_specs/v1/e05-model-router/t20-prod-routes-on-the-4x-models.yaml) |
| Epic / release | `v1-e05-model-router` / `v1.2` |
| Branch | `task/v1-e05-t20-prod-routes-on-the-4x-models` |
| Session status | PARTIAL: the session's work is done; ac3 is the operator's and ac2 waits on the PM's ruling |

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
this change is a narrowing plus your account assignment. It can ride in the promotion's prod plan.
ac2, prod reusing dev's classifications, is proposed NOT APPLICABLE until a landscape model stage is
on (Q1). ac3 is the operator's, and the Goal stays `InProgress`.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `prod-routes-on-the-4x-models` (Prod on 4.x) | Session part done | Quotas read first (operator), red tests committed (`e6c77b8`), routing and grant (`52be95c`), runbook (`c415f38`). The node criterion passes; the Goal's ac2 and ac3 are open |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: prod's routing names the models dev routes to (or the PM's ruling for a class that differs), the grant names exactly what the routing files route to, the prices are from the pricing file, and the module's tests pin it, shown failing first | PASS | **Quotas first** (operator, 2026-11-15, the block in Operator follow-ups): Haiku 4.5 `5000000.0` and Sonnet 4.6 `6000000.0`, cross-region and global cross-region, in each of us-east-1, us-east-2 and us-west-2; none zero. **Red** (`e6c77b8`, routing unchanged): `pytest test_settings_environments.py test_usage.py -k "prod_routes or quota_is_held or pricing_file_has"` → `3 failed, 1 passed`, each at its assertion (prod's routes, the 5.5 models found in prod, the routed-models table). `terraform test` (offline mirror) → `Failure! 7 passed, 4 failed`, all 7 errors `Test assertion failed`: the ten resources (apply, prod's count, the two plan-time runs), the two conditioned profiles, and no wildcard or 5.5 resource. **Green** (`52be95c`): `terraform test` → `Success! 11 passed, 0 failed`; `pytest test_settings_environments.py integrations/models/` → `604 passed in 4.06s`. **Prices:** both models were already in `config/model_pricing.yaml` (operator reading of 2026-10-27), and `test_pricing_file_has_an_entry_for_every_model_the_routing_files_route` holds every routed model priced. **No class differs from dev's** (Decisions 1). **Mutants:** 7 of 7 caught (table below) |
| ac2: prod makes no model call for an item dev has classified at the same prompt version and model, by test, before prod's first live call | NOT RUN | Proposed NOT APPLICABLE until a landscape model stage is on, under the PM's amendment of 2026-11-14 (none is on in V1). A test is not cheap with today's cache: Deviations 1, relay Q1 |
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
* **Step 2's new plan check, exercised offline.** The block is lifted from the runbook and run on six
  synthetic plan files:
  * `PLAN OK` for dev's policy update alone, and for prod's update with the assignment inside a
    promotion with two other changes (it counts those as 2);
  * `PLAN STOP` for a wildcard added, a 5.5 profile kept, another user's assignment, and the set
    replaced.

  The spend-names block below was exercised the same way: `SPEND NAMES OK: nothing to add` for prod
  on dev's names, and `NOT LISTED` for a new usage type and for a new service.

## Files changed

* **`config/model_routing.prod.yaml`**: the three Claude routes go to dev's models, and the header
  says why, with the quota reading. **`config/model_routing.dev.yaml`**: only its header comment
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
  * step 2's update check, rewritten for this change and reading `module.bedrock_access` alone, so
    it runs on a promotion's prod plan;
  * the first-apply check's counts;
  * `--no-cli-pager` and the 2026-11-15 reading on the quota command;
  * the order for prod, prod's first-call block and how to read it.
* **`infrastructure/modules/model_spend_budget/{main.tf,README.md}`** and
  **`docs/runbooks/aws-account-baseline.md`**: comments only. They said `v1-e05-t17` would add "the
  5.5 models of prod's routes". They now say prod's routes are the names already listed, and that
  the 5.x models come with `v1-e41-t20`. The budget's resources do not change.

## Deviations from the spec

1. **ac2 is proposed NOT APPLICABLE until a landscape model stage is on; it is not tested here.** A test
   of the reuse rule is not cheap with the existing classification cache:
   * `ClassificationKey` is topic, taxonomy version, override digest, prompt version and item
     fingerprint, with **no model id**. "Classified at the same prompt version and model" cannot be
     expressed in it. Today a cache hit ignores the model, so after a route change it would reuse
     another model's answers.
   * Each environment's cache is a file under its own data directory,
     `<data_dir>/landscape/classifications/<caselist>.jsonl`, and **no prod run reads dev's**.

   A test of prod reusing dev's results would first need a feature: the model in the key, and a way
   for prod to read or import dev's cache. That is a task of its own, and it belongs with the stage
   that turns on. The PM amends the spec (relay Q1).
2. **The spec's description says "Then prod's plan and apply"**, as if prod's grant were new. Prod's set
   has existed since 2026-11-03 with nobody assigned and the 22-resource grant of the time (the
   evidence-search runbook's step 11 record, main at `3f827613`). So prod's plan is one policy update,
   twelve resources removed, plus the operator's first assignment, which comes from `owner.auto.tfvars`
   and not from code. Nothing in the spec changes; this is how ac3 reads now.

## Decisions and assumptions

1. **Class for class, with no ruling needed.** Prod sent `deep_audit` to Opus 5.5, and dev routes it to
   Sonnet 4.6, so prod now does too. Nothing in V1 calls `deep_audit` (no `TaskClass.DEEP_AUDIT` in any
   caller), so I found no reason it needs another model. Class for class also puts prod's
   `complex_reasoning`, card selection for `cut` and auto-cut, on Haiku 4.5 rather than prod's former
   Sonnet tier. That is what dev routes and what the spec asks; it is in relay Q2 only for confirmation.
   Keeping prod's routes equal to dev's also means a classification ever shared between them would be
   at the same model.
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

2. **After this merges into `dev`: dev's plan and apply.** Dev's set gets the same policy update, and
   it is a dev plan, not a prod one. In a dev worktree at `origin/dev`, run
   [bedrock-access.md](../runbooks/bedrock-access.md) Before you start with `ENVIRONMENT=dev`, then
   step 1. The plan should read `Plan: 0 to add, 1 to change, 0 to destroy.`
   Then step 2's **update** block, which should print `PLAN OK: module.bedrock_access: 1 policy update,
   no assignment created; bedrock:InvokeModel on 10 resources, 6 Claude models through the 2 profiles;
   12 removed, none added; changes outside module.bedrock_access: 0`. Then the PM's read, then step 3:
   `0 added, 1 changed`.
3. **Before the promotion's prod plan:** prod's `owner.auto.tfvars` gains your
   `bedrock_invoker_user_names` line, from Before you start's second block with `ENVIRONMENT=prod`, in
   the worktree the promotion plans prod from. It should print `1`.
4. **The promotion's prod plan carries this change** if this merges into `dev` before the cut. That is
   the PM's preference; no separate prod plan is made. Run step 2's update block on that plan, with the
   promotion's saved plan file in place of `bedrock-access.tfplan`. It should print `PLAN OK:
   module.bedrock_access: 1 policy update, and your assignment created; ... 12 removed, none added;
   changes outside module.bedrock_access: <the promotion's own count>`. If this merges after the cut,
   the change waits for the next promotion: prod's current set already grants both 4.x models, and
   prod's routes reach the stable build only with a promotion anyway.
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

**Relay prompt for the PM** (paste-ready):

> v1-e05-t20: the session's part is done; ac3 is the operator's. Four questions.
>
> Q1. **ac2 (prod reusing dev's classifications).** A test isn't cheap today. `ClassificationKey` has
> no model id, and each environment's cache lives in its own data directory, which no prod run reads.
> (a) Amend ac2 to NOT APPLICABLE until a landscape model stage is on, and file a task, with the
> stage that turns on, that adds the model to the key and lets prod read dev's cache (recommended:
> nothing in V1 calls the stage, and the test would need that feature first). (b) Build it in this task.
>
> Q2. **Class for class puts prod's `complex_reasoning` (cut and auto-cut card selection) on Haiku
> 4.5**, as dev, rather than prod's former Sonnet tier. `deep_audit` goes to Sonnet 4.6, and nothing in
> V1 calls it. (a) Confirm (recommended: it is what dev measured and what the spec says, at a third of
> Sonnet 4.6's price). (b) Rule `complex_reasoning` to Sonnet 4.6 in prod: a separate change, and the
> grant is unchanged, since both models are routed.
>
> Q3. **Prod's grant change rides in the promotion's prod plan** if this merges before the cut, with
> step 2's new update block run on that plan, reading `module.bedrock_access` alone (recommended). If
> it misses the cut, it waits for the next promotion. Dev's plan for the same policy update is made
> on its own after the merge.
>
> Q4. **Prod's set has nobody assigned.** The operator's `bedrock_invoker_user_names` line goes into
> prod's `owner.auto.tfvars` before the promotion's prod plan, so the assignment is in the same plan
> (recommended). The alternative is a later prod plan, which would be the weekend's second.

## Follow-up work

1. **The classification cache's key gains the model id, and prod can read dev's results.** This is ac2's
   precondition, filed with whichever landscape model stage turns on (E32). It is not V1.
2. **The `doctor --routing-file` row on an installed stable build** would show the bundled prod routes
   without a model call. Nothing here needs it, but the PM may want it in the promotion's smoke list.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

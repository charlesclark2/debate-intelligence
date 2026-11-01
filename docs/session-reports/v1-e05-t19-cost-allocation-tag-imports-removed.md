# Session report: v1-e05-t19-cost-allocation-tag-imports-removed

| | |
|---|---|
| Task | `v1-e05-t19-cost-allocation-tag-imports-removed` — The cost allocation tags' import blocks are removed once both tags are in state |
| Spec | [`plan_specs/v1/e05-model-router/t19-cost-allocation-tag-imports-removed.yaml`](../../plan_specs/v1/e05-model-router/t19-cost-allocation-tag-imports-removed.yaml) |
| Epic / release | `v1-e05-model-router` / `v1.2` |
| Branch | `task/v1-e05-t19-cost-allocation-tag-imports-removed` |
| Session status | COMPLETE (Goal left `InProgress`: the operator's plan after the merge is still to run) <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The two `import` blocks that adopted the `Project` and `Environment` cost allocation tags
(`v1-e05-t18`, applied on 2026-10-31) are gone from `infrastructure/bootstrap/organization/budgets.tf`.
Their comment now says they were removed once both tags were in state. The module call, the module
and the root's `check` are byte for byte as they were. The runbook records the import apply as done,
with its plan line and the "No changes" plan after it. Step 5 no longer tells a new account to take
the blocks out.

As the PM suspected, the `COSTTAGSPLAN` check as written would have refused the plan this root now
gives. It looked for the tags only among change entries, and an unchanged tag is `no-op` with no
`importing`, so it printed `the Project tag is in the plan 0 times, not once`. It now finds the tags
among all of the plan's resources and accepts each one unchanged, imported unchanged or created. It
keeps every refusal it had, and now also refuses a third cost allocation tag that is merely unchanged.

The structural test now refuses any `import` block that names a cost allocation tag. The plan-check
test tries every refusal on both the plan after the imports and t18's import plan. The tests were
shown failing first, all four mutants were caught, and `terraform_checks.sh` passes offline.

The Goal stays `InProgress`. ac1 ends with the operator's plan of the root after the merge, read by
the PM, and no session can run that.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `cost-allocation-tag-imports-removed` | Done | Import blocks removed, runbook updated, `COSTTAGSPLAN` accepts both tags unchanged, structural and plan-check tests updated; red run, four mutants, `terraform_checks.sh` |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| Node `cost-allocation-tag-imports-removed`: Import blocks removed tests pass (`uv run pytest tests/infrastructure -k cost_allocation`) | PASS | `.venv/bin/python scripts/hard_stop.py 115 uv run pytest tests/infrastructure -k cost_allocation` → `39 passed in 10.03s`, at `4d6e21c`. |
| ac1: the two import blocks are gone | PASS | `git diff a638f6d -- infrastructure/bootstrap/organization/budgets.tf` removes the two `import` blocks and their seven-line comment, and adds a four-line comment saying they were removed. `test_no_import_block_adopts_a_cost_allocation_tag` checks every `import` block under `infrastructure/`. |
| ac1: the module, resources and check are unchanged | PASS | `git diff --quiet a638f6d -- infrastructure/modules` exits 0 (module untouched, its resource included). The `budgets.tf` diff is the one hunk at old lines 94–109, between the `module "cost_allocation_tags"` block and `check "anomaly_monitor_tag_is_kept_active"`, and touches neither of them. |
| ac1: the tests and runbook say the imports are done | PASS | Runbook: step 5, "Applying the cost allocation tags" (now history, dated 2026-10-31, with t18's plan line, its `PLAN OK` and the after-plan's `No changes`) and a new "Planning this root after the imports". Tests: both docstrings, `unchanged_plan()` as the base plan, `test_a_plan_with_both_tags_unchanged_is_ok`. |
| ac1: `scripts/terraform_checks.sh` passes | PASS | `TF_CLI_CONFIG_FILE=<scratchpad mirror.tfrc> .venv/bin/python scripts/hard_stop.py 115 bash scripts/terraform_checks.sh` runs offline, the CLI config naming a `filesystem_mirror` on the main checkout's `infrastructure/envs/dev/.terraform/providers` (hashicorp/aws 5.100.0), as t18 ran it. Result: `All Terraform checks passed.`, exit 0, 36 `ok` lines in 43 s. Among them: `validate infrastructure/bootstrap/organization`, `validate infrastructure/modules/cost_allocation_tags`, `tflint --recursive infrastructure` and `test infrastructure/modules/cost_allocation_tags`. No lock file changed (`git status --porcelain` showed only the two edited files), and the `.terraform` directories it left were removed. |
| ac1: the operator's plan of the root then shows no change to the tags (operator, read by the PM) | NOT RUN | It needs the merge into `dev`, the operator's credentials and the PM's read. See Operator follow-ups. |

### The red run

The tests were committed alone (`63a29f7`) against the code as t18 left it. The import blocks were
still in, and the runbook check unchanged:
`.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest tests/infrastructure -k cost_allocation -p no:randomly -q --tb=line`
→ `12 failed, 27 passed in 3.40s`. The failures, grouped by reason:

* `test_no_import_block_adopts_a_cost_allocation_tag`: the two blocks were there;
* `test_a_plan_with_both_tags_unchanged_is_ok`, and the "planned Inactive", "key in another case"
  and "imported as Environment" refusals on the plan after the imports: the check printed `the
  Project tag is in the plan 0 times, not once | the Environment tag is in the plan 0 times, not
  once`. That is what the operator's next plan would have got;
* `a third tag unchanged`, on both base plans: today's check let it through;
* the two OK tests, the create test and the destroy and imported-as-Environment reasons: the new
  wording (`PLAN OK: the two tags, …`, `not unchanged, imported unchanged or created`).

### Mutants

Each mutant was applied to the committed tree (`4d6e21c`) and run against both test files with
`-n 0 -p no:randomly`, then restored with `git checkout HEAD --`. Each run used a fresh, empty
`HYPOTHESIS_STORAGE_DIRECTORY`, though neither file uses Hypothesis. Every catch is an assertion
failure; none crashed or failed at collection. The worktree was clean afterwards.

| Mutant | Result | Caught by |
|---|---|---|
| An import block left (`import { to = …this["Project"] … }` after the module call) | caught, 1 failed | `test_no_import_block_adopts_a_cost_allocation_tag`: `assert [('infrastruc...["Project"]')] == []` |
| The module call removed | caught, 1 failed | `test_the_organization_root_calls_the_module_once`: `assert 0 == 1` |
| The plan check accepting a tag destroyed (`if actions == ["delete"]: how.append(key + " destroyed"); continue`) | caught, 2 failed | `a tag destroyed`, on both base plans: `assert line.startswith("PLAN NOT OK: ")` is false, so the check printed `PLAN OK` |
| The plan check refusing the clean no-op plan (the tags looked up among change entries again, as t18 had it) | caught, 3 failed | `test_a_plan_with_both_tags_unchanged_is_ok`, `the Project tag planned Inactive` and `a tag key in another case` on the plan after the imports |

### Before the report

* `uv run scripts/affected_tests.py --run`, under `hard_stop.py 115`: 95 of 611 test files from 6
  changed files. The run was **stopped at its 115-second limit at 47%**, with no failure printed up
  to there (load average 7, then 25 from another session). Under agreement 10 that run is left to the
  pull request's `ci` check. The edges are real: 43 selections come through the runbook's path and 14
  through `budgets.tf`'s.
* Within two minutes instead:
  * the 16 files that name `docs/runbooks/aws-account-baseline.md` or `budgets.tf` by path, plus
    `tests/infrastructure`, `tests/docs`, `tests/architecture` and `tests/specs`, run with
    `-m "not slow and not live" -n auto` → `919 passed in 27.49s`;
  * the rest of the always-run list (`packages/debate_cli/tests/test_app.py`,
    `test_help_rendering.py`, `test_container_factories.py`) → `40 passed in 25.20s`;
  * `tests/docs/test_model_spend_budget_plan_check.py`, the other check read out of this runbook →
    `26 passed`.
* `ruff format --check tests/infrastructure` → `3 files already formatted`; `ruff check
  tests/infrastructure` → `All checks passed!`; `pyright` on the two changed test files → `0
  errors`. No file under `packages/` changed.
* `uv run --frozen lint-imports` → `Contracts: 19 kept, 0 broken.`
* `scripts/check_command_blocks.py` → `OK: no '#' comments in 625 shell code blocks in 203 Markdown
  files`. `docs_index.py --check-descriptions` → `All 61 indexed documents under docs/ have a
  description`. `check_links.py` → `OK: 3167 relative links and anchors in 494 Markdown files`.
  `check_thin_handlers.py` → `OK: 68 CLI command and API route handlers within 25 statements`.
* `uv run scripts/validate_specs.py` → `OK: 539 files, 41 epics, 476 tasks, 22 releases`. The spec
  differs from `origin/dev` only in its phase.

## Files changed

* `infrastructure/bootstrap/organization/budgets.tf`: the two `import` blocks and their comment
  removed, and a comment saying when and why put in their place.
* `docs/runbooks/aws-account-baseline.md`:
  * Step 5: the tags were adopted on 2026-10-31 and the blocks removed. A new account's step 4
    fails on the two tags, and once the keys are listed it plans and applies again, which creates
    them. Nothing is taken out of `budgets.tf` any more.
  * "Applying the cost allocation tags" is now the record of 2026-10-31.
  * The new "Planning this root after the imports" keeps the blocks: shell variables, worktree,
    sign-in, tfvars, plan and `COSTTAGSPLAN`. The worktree check now looks for the import blocks
    removed (`NOT MERGED: origin/dev has no v1-e05-t19`). The plan's `grep` and its reading now
    expect `No changes. Your infrastructure matches the configuration.`
  * The check accepts both tags unchanged and prints `PLAN OK: the two tags, Project unchanged and
    Environment unchanged, …`.
  * The apply block is replaced by "No apply follows".
* `tests/infrastructure/test_cost_allocation_tags_are_the_only_ones_managed.py`:
  `test_no_import_block_adopts_a_cost_allocation_tag`, and the docstring.
* `tests/infrastructure/test_cost_allocation_tags_plan_check.py`:
  * the plan after the imports (`unchanged_plan()`) is the base plan, and every refusal runs on it
    and on t18's import plan;
  * the shape "both tags unchanged, nothing else" is accepted;
  * a third tag is refused when unchanged and when created, as well as when imported;
  * "a plan with nothing to do" is now "a plan without the tags".

## Deviations from the spec

None. Some choices the PM may want to look at first are under Decisions.

## Decisions and assumptions

* **The plan check's success line now starts `PLAN OK: the two tags,`** instead of `PLAN OK: two
  changes,`. Two unchanged tags are not two changes. The runbook's history quotes t18's line as it
  was printed.
* **The import shape is still accepted.** The brief asked for the unchanged shape to be added, and
  for every refusal to be kept. It did not ask for import acceptance to go, so it stays and is still
  tested. Since the structural test forbids the blocks, a plan from `origin/dev` can no longer
  contain an import. If the PM would rather refuse an import from now on, that is a two-line change
  (drop the `imported` branch and its test).
* **A third cost allocation tag is refused even when unchanged.** The old check saw only change
  entries. A third tag already in state is `no-op` and would have passed once the base plan was the
  unchanged one. It is now listed under `other changes:` with its action, `no-op`.
* **The apply block is gone from the runbook.** In this account a plan the check passes has no
  changes, so there is nothing to apply. The old block's success line, `Resources: 2 imported`,
  described the done apply and would mislead. What it printed is kept in the history paragraph. "No
  apply follows" sends any other plan to the PM.
* **Terraform's shape for an unchanged resource was measured, not assumed.** In a scratch directory,
  Terraform 1.16.3 applied two `terraform_data` resources (built in, so no provider and no network),
  then ran `plan -out` and `show -json`. Both resources were in `resource_changes` with `actions:
  ["no-op"]`, no `importing` key, and `after` holding their state. The text plan printed `No changes.
  Your infrastructure matches the configuration.` at the start of a line, which is what the runbook's
  new `grep` expects. That probe used a root-level built-in resource, not the AWS provider's
  `aws_ce_cost_allocation_tag` inside a module. The operator's plan after the merge is what confirms
  it for the real root.

## Operator follow-ups

**After the merge into `dev`: a plan of the organization root, the check, the PM's read, and no
apply.** The blocks are in
[docs/runbooks/aws-account-baseline.md, "Planning this root after the imports"](../runbooks/aws-account-baseline.md#planning-this-root-after-the-imports).
Run them in order:

1. the shell variables;
2. the worktree at `origin/dev` (every time), in the existing `cost-allocation-tags-apply` worktree;
3. the sign-in as `debate-admin`;
4. the tfvars copy;
5. the plan (~2 min), whose block refuses a Wednesday, a Terraform override and AWS keys in the
   shell;
6. the `COSTTAGSPLAN` check;
7. **the PM's read**.

Success looks like this:

* the worktree block prints `ok: <the worktree> at origin/dev <commit>, import blocks removed`;
* the plan's `grep` prints exactly `No changes. Your infrastructure matches the configuration.`, and
  no `Plan:`, `Error:`, `will be destroyed` or `must be replaced` line;
* the check prints `PLAN OK: the two tags, Project unchanged and Environment unchanged, each Active;
  nothing else changes; permission set or assignment changes: 0; budget changes: 0`.

There is no apply. Once the PM has read the plan and the check, ac1's last clause is met and the Goal
can be set `Succeeded`. A `PLAN NOT OK`, or a `Plan:` line, goes to the PM and nothing is applied.

From this merge on, a plan of `bootstrap/organization` for another change, such as the model spend
budget's, no longer shows the two `will be imported` lines that t18's report warned about.

## Follow-up work

* **The module's README still says "two `import` blocks in the root adopt them without changing
  them"** (`infrastructure/modules/cost_allocation_tags/README.md`, its second paragraph). That is no
  longer true. The spec forbids "a change to … the module", and the brief asked for the module to be
  kept byte for byte, so I left the README alone. If the PM rules the README outside "the module",
  the fix is one sentence in a later task, or in this one on the PM's word, for example: "The
  operator activated both by hand on 2026-10-30, and two `import` blocks in the root adopted them on
  2026-10-31; they were removed once both tags were in state (`v1-e05-t19`)."

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

# Session report: v1-e05-t18-cost-allocation-tags-in-terraform

| | |
|---|---|
| Task | `v1-e05-t18-cost-allocation-tags-in-terraform` — The cost allocation tags are active by Terraform, so the budgets that filter on them never read zero again |
| Spec | [`plan_specs/v1/e05-model-router/t18-cost-allocation-tags-in-terraform.yaml`](../../plan_specs/v1/e05-model-router/t18-cost-allocation-tags-in-terraform.yaml) |
| Epic / release | `v1-e05-model-router` / `v1.2` |
| Branch | `task/v1-e05-t18-cost-allocation-tags-in-terraform` |
| Session status | PARTIAL: everything a session can run passes; ac1's second half (the plan against the account, read by the PM, and the apply) is the operator's, after the merge. The Goal stays InProgress <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The `Project` and `Environment` cost allocation tags are now managed in Terraform by a new module,
[`infrastructure/modules/cost_allocation_tags`](../../infrastructure/modules/cost_allocation_tags/),
which keeps both `Active` (`aws_ce_cost_allocation_tag`, present in the root's locked
hashicorp/aws 5.100.0). The module is called from `bootstrap/organization/budgets.tf`. Two `import`
blocks there adopt the tags the operator activated by hand on 2026-10-30. The plan reads each tag
from AWS and shows it imported with nothing to change (`Plan: 2 to import, 0 to add, 0 to change, 0
to destroy.`), and the apply makes no Cost Explorer call. That much was seen with the real provider
against a loopback stand-in for Cost Explorer (below). The module's Terraform tests hold the two keys
and their status, shown failing first. A Python test holds that no other cost allocation tag is
managed anywhere under `infrastructure/`. The runbook gains the plan, a JSON plan check that prints
`PLAN OK` only for exactly these two tags, and the apply. **The PM should look first at the
new-account consequence of the import blocks** (Decisions, and Follow-up work 1).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `cost-allocation-tags-in-terraform` | Done | Module, root wiring, Terraform tests, structural and plan-check tests, runbook section; `terraform_checks.sh` passes |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 (first half): Terraform tests show both tags Active, shown failing first | PASS | **Red**, at a skeleton module managing no tag (`for_each = toset([])`, `status = "Inactive"`), before `d869f47`: `terraform -chdir=infrastructure/modules/cost_allocation_tags test` → `Failure! 0 passed, 2 failed.`, 0 skipped, every failure `Test assertion failed` (keys `[]` against `["Environment", "Project"]`, the Project and Environment status `""` against `"Active"`). **Green**, at `d869f47`: `Success! 2 passed, 0 failed.` (`exactly_the_project_and_environment_tags`, `both_tags_active`). **No other tag**: `tests/infrastructure/test_cost_allocation_tags_are_the_only_ones_managed.py` → `3 passed`; its root-call test was red at the skeleton (`1 failed, 2 passed`: the root called no `../../modules/cost_allocation_tags`); its other two are shown failing by mutants 3b and 3c. |
| ac1 (second half): the plan against the account shows them already Active (operator, read by the PM) | NOT RUN | Needs the operator's credentials, a plan of the organization root after the merge, and the PM's read; no session can close it. The blocks are in `docs/runbooks/aws-account-baseline.md`, "Applying the cost allocation tags" (Operator follow-ups below). |
| Node `cost-allocation-tags-in-terraform`: Cost allocation tags tests pass (`uv run bash scripts/terraform_checks.sh`) | PASS | Run offline against the main checkout's provider mirror (`TF_CLI_CONFIG_FILE` naming a `filesystem_mirror` on its `infrastructure/envs/dev/.terraform/providers`, hashicorp/aws 5.100.0), at `d869f47`: `All Terraform checks passed.`, exit 0, 36 `ok` lines in 47 s, among them `validate infrastructure/bootstrap/organization` (the import blocks and the `check`), `validate infrastructure/modules/cost_allocation_tags`, `tflint config infrastructure/modules/cost_allocation_tags`, `tflint --recursive infrastructure`, `test infrastructure/modules/cost_allocation_tags`. No lock file changed. The new module's `.terraform.lock.hcl` is `model_spend_budget`'s byte for byte (`cmp`), and its `.tflint.hcl` is the shared one. The `.terraform` directories the script left were removed afterwards. |

### The pinned provider has the resource, and how it behaves

* **The version.** The organization root's `.terraform.lock.hcl` pins hashicorp/aws `5.100.0`
  (constraint `~> 5.70`). `terraform providers schema -json` on that exact binary (from the mirror,
  offline) has `aws_ce_cost_allocation_tag`: `tag_key` and `status` required, `type` and `id`
  computed, no `tags`. No provider bump. I could not fetch the provider's docs or changelog: a live
  fetch is the operator's (Operator follow-ups, the optional citation block). The schema above is
  the locked binary's own.
* **Create versus import.** The binary's function names (`strings`) are
  `resourceCostAllocationTagRead`, `…Update`, `…Delete` and `updateCostAllocationTagStatus`, with no
  `…Create`. Creating calls the same status update as a change. Observed with Terraform 1.16.3 and
  that provider binary, against a loopback HTTP stand-in for Cost Explorer that logged every request
  (scratchpad only, not committed; no external network):

  | Case | Plan | Calls Cost Explorer saw |
  |---|---|---|
  | The two `import` blocks, both tags Active | `Plan: 2 to import, 0 to add, 0 to change, 0 to destroy.`; JSON `actions: ["no-op"]`, `importing: {"id": "<key>"}`, status `Active` before and after | plan: `ListCostAllocationTags` once per key; **apply: none** (`Apply complete! Resources: 2 imported, 0 added, 0 changed, 0 destroyed.`) |
  | Import, `Environment` found Inactive | `2 to import, 0 to add, 1 to change`; JSON `actions: ["update"]` with `importing`, `Inactive -> Active` | — |
  | No `import` blocks, both Active | `Plan: 2 to add`; JSON `actions: ["create"]`; the plan reads nothing | apply: `UpdateCostAllocationTagsStatus` `Active` per key, then a read. **It adopts an Active tag without an import** |
  | Destroy | — | `UpdateCostAllocationTagsStatus` **`Inactive`** per key |
  | A key AWS has never listed | import: `Error: Cannot import non-existent remote object` | create: the apply fails (`reading Cost Explorer Cost Allocation Tag (Environment): empty result`, against the stand-in's answer, whose error shape I wrote) |

  So the resource does adopt an existing Active tag on create, and no `import` block is *needed*. I
  used import blocks anyway: only an import makes the plan read the tag from AWS, so only an import
  plan shows the PM, before the apply, that both are already Active. A create plan shows `2 to add`
  whatever their status is.
* **The root's `check`** (`anomaly_monitor_tag_is_kept_active`) cannot run in a Terraform test, since
  the root reads live data sources. Against the stand-in, copied into a scratch root: with
  `project_tag_key = "Project"` no warning; with `"Owner"`, `Warning: Check block assertion failed …
  modules/cost_allocation_tags does not keep Active, so the monitor reads $0.`

### The runbook's plan check

`tests/infrastructure/test_cost_allocation_tags_plan_check.py` reads the Python between the runbook's
`COSTTAGSPLAN` markers and runs it as the operator does, on hand-written plans in the JSON shape
observed above → `17 passed`. It accepts the import plan (and a create plan), and refuses 13 shapes,
each with its reason: a tag found Inactive, a tag planned Inactive, a tag missing, a third tag, a tag
imported under the other key, replaced, destroyed, a wrong-case key, a permission set changed, an
account assignment added, the model spend budget changed, an environment budget destroyed, the
anomaly monitor replaced. It counts change entries in the JSON, not text lines. One test adds 26
unchanged `aws_ssoadmin_*` entries plus a data-source read and still reads `permission set or
assignment changes: 0`. That is the PM's point about the 2026-11-01 run-lock plan's text count of 26.

### Mutation run (agreement 8)

15 mutants, one at a time on the committed tree (`d869f47`), each restored with `git checkout HEAD
--` after its run, `git status` clean after the batch. No suite here uses Hypothesis, so the
database rule has nothing to isolate. Every catch is an assertion failure: no Terraform run errored
or was skipped. Script: a throwaway in the session's scratchpad.

| # | Mutant | Result |
|---|---|---|
| 1 | (PM's 1) both tags `Inactive` | Caught: Terraform test `1 passed, 1 failed` (`both_tags_active`) |
| 1b | only `Project` `Inactive` | Caught: `1 passed, 1 failed` |
| 2 | (PM's 2) the `Environment` tag missing | Caught: `0 passed, 2 failed` |
| 3 | (PM's 3) a third tag, `Owner`, in the module's key list | Caught: `0 passed, 2 failed` |
| 3b | a third tag as a second resource block in the module | Terraform tests **pass** (`2 passed`), as expected: they cannot see it. Caught by the structural test: `2 failed, 1 passed` |
| 3c | a third tag as a resource in the organization root | Caught by the structural test: `1 failed, 2 passed` |
| 4 | `tag_key = lower(each.key)` | Caught: `1 passed, 1 failed` (`exactly_the_project_and_environment_tags`) |
| 5 | the root's module call removed | Caught by the structural test: `1 failed, 2 passed` |
| R1 | the plan check refuses nothing | Caught: `14 failed, 3 passed` |
| R2 | the plan check counts every entry, `no-op` and `read` included | Caught: `10 failed, 7 passed` |
| R3 | the plan check accepts a tag updated on import | Caught: `1 failed` (the Environment tag found Inactive) |
| R4 | the plan check drops the `Active` test | Caught: `1 failed` (the Project tag planned Inactive) |
| R5 | the plan check ignores other changes | Caught: `6 failed` |
| R6 | the plan check ignores imports (filters `no-op` with `importing` out) | Caught: `5 failed` |

(Mutant 5 replaced a first version that put a trailing slash on `source`. The structural test caught
that too, but a trailing slash is not a defect, so it was not evidence.)

### Before the report

* `uv run scripts/affected_tests.py` → `93 of 596 test files (15.6%) chosen`. They are mostly tests
  that name `docs/runbooks/aws-account-baseline.md` directly or through a script, and source walkers
  picking up the two new test files. `--run`, bounded by `scripts/hard_stop.py 115`, reached 50% at
  115 s (load average about 7) and was stopped (exit 124). Nothing had failed up to then. Over two
  minutes, so per agreement 10 the whole affected set is left to the pull request's `ci` check.
* Within the limit instead, 38 files: those of the affected set that name a changed file directly,
  the always-run list and `tests/infrastructure`: `.venv/bin/python scripts/hard_stop.py 115
  .venv/bin/python -m pytest -n auto -m "not slow and not live" <the 38 files>` → `1617 passed in
  70.00s`.
* `uv run ruff check .` → `All checks passed!`; `uv run ruff format --check .` → `1664 files already
  formatted`; `uv run pyright tests/infrastructure` → `0 errors` (no package changed);
  `uv run lint-imports` → `19 kept, 0 broken`; `scripts/check_thin_handlers.py` → OK;
  `scripts/docs_index.py --check-descriptions` → OK; `scripts/check_links.py` → `OK: 3101 relative
  links and anchors` (the runbook's new anchors among them); `scripts/check_command_blocks.py --base
  origin/dev` → OK; `uv run scripts/validate_specs.py` → `OK: 530 files, 41 epics, 467 tasks, 22
  releases`.
* The spec against `origin/dev`: no amendment (the only difference is this branch's `InProgress`).

## Files changed

* `infrastructure/modules/cost_allocation_tags/` (new): the two tags, `Active`; the `tag_keys`
  output; Terraform tests; README; the shared `.tflint.hcl` and `model_spend_budget`'s lock file.
* `infrastructure/bootstrap/organization/budgets.tf`: the module call, the two `import` blocks, and
  a `check` that the anomaly monitor's `project_tag_key` is one the module keeps Active. Header
  comment corrected.
* `infrastructure/bootstrap/organization/main.tf`, `README.md`: corrected the comment that said no
  provider resource can activate the tags. Table row.
* `tests/infrastructure/test_cost_allocation_tags_are_the_only_ones_managed.py`,
  `tests/infrastructure/test_cost_allocation_tags_plan_check.py` (new).
* `docs/runbooks/aws-account-baseline.md`: step 5 rewritten (Terraform keeps the tags Active; a new
  account's order; never activate by hand); the new section "The cost allocation tags", with its
  plan, `COSTTAGSPLAN` check and apply blocks; the baseline table and step 4's resource list.

## Deviations from the spec

1. **A module, called from the root, rather than resources in the root itself.** The spec says
   "manage their status in `infrastructure/bootstrap/organization`". `scripts/terraform_checks.sh`
   runs `terraform test` only for directories under `infrastructure/modules/`, so t16's pattern
   (a module called from that root) is what gives the tests a place to run. The resources are still
   planned and applied from the organization root, and the module is within the task's
   `infrastructure` package.
2. **The plan-check test is in `tests/infrastructure`, not `tests/docs`** where t16's lives, because
   the task's packages list `tests/infrastructure` and not `tests/docs`.
3. **The runbook's step 5 no longer gives the hand activation command.** Once Terraform manages the
   tags, a hand change is drift. That command's only remaining use was a new account, which now goes
   through the apply (step 5 says how).

## Decisions and assumptions

* **Import blocks rather than create.** Both adopt the tags without changing them in AWS (table
  above), but only the import plan shows the PM that they are already Active. ac1 asks the plan to
  show exactly that. If the plan finds a tag Inactive, it shows `1 to change`, and the plan check says
  `PLAN NOT OK: the <key> tag is update on import`: the PM decides.
* **The import blocks stay in `budgets.tf`.** They are inert once the tags are in state. They have
  one cost: in an account where AWS has not yet listed both keys (a new account, within 24 hours of
  its first tagged resource), the whole root's plan fails with `Cannot import non-existent remote
  object`. Without them, only the apply of the two tags would fail. Step 5 of the runbook tells a new
  account to take them out of its copy for step 4. Follow-up work 1 proposes removing them after this
  apply.
* **The tag keys are fixed in the module, not a variable**, so the tests read the real values (as
  t16's budget did). The anomaly monitor's key is still the root variable `project_tag_key`; the
  root's `check` warns at plan time if it ever names a key the module does not keep Active.
* **No `prevent_destroy`.** Destroying either tag sets it Inactive (observed), which is the outage
  this task exists to prevent. Instead the plan check refuses a destroy, and step 5 says a plan that
  destroys one is never applied. `prevent_destroy` would also need checking against the module
  tests' teardown under `mock_provider`. Follow-up work 2.
* **The plan block's guards** follow the model spend budget's: no Wednesday, no Terraform override.
  It adds a refusal of `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` and `AWS_SESSION_TOKEN` in the
  shell, because keys in the environment win over `AWS_PROFILE`. The text plan is judged only by its
  `Plan:` line and error, destroy and replace lines, never by counting `aws_ssoadmin` text lines.

## Operator follow-ups

**After the merge into `dev`: the plan, the PM's read, the apply.** The blocks are in
[docs/runbooks/aws-account-baseline.md, "Applying the cost allocation tags"](../runbooks/aws-account-baseline.md#applying-the-cost-allocation-tags),
in order: the shell variables, the worktree (`cost-allocation-tags-apply`, once), the worktree at
`origin/dev` (every time), the sign-in as `debate-admin`, the tfvars copy, the plan (~2 min), the
`COSTTAGSPLAN` check, **the PM's read**, the apply (~1 min). Success looks like this:

* the plan prints `Plan: 2 to import, 0 to add, 0 to change, 0 to destroy.`;
* the check prints `PLAN OK: two changes, Project imported and Environment imported, each Active;
  nothing else changes; permission set or assignment changes: 0; budget changes: 0`;
* the apply prints `Apply complete! Resources: 2 imported, 0 added, 0 changed, 0 destroyed.`,
  `cost allocation tags in state: 2`, `Environment Active` and `Project Active`.

Once the PM has read the plan and it has been applied, the Goal can be set `Succeeded`.

**Ordering with any other apply of this root.** Until this apply has run, any plan of
`bootstrap/organization` from a `dev` that includes this task (a model spend budget change through
`v1-e05-t17`, say) also shows the two imports. The model spend budget's text check stops on them:
its second `grep` prints the `will be imported` lines. Apply this one first.

**Optional: the provider's own docs, at the pinned version.** This is the one-line fetch the PM asked
for as a citation. It prints only the matching lines: the resource's docs page and its source at tag
`v5.100.0`, showing the import form, that create is wired to the update function, and that delete
sets `Inactive`. Expected runtime: seconds.

**Operator command** (expected runtime under a minute)
Where: any terminal on your Mac
```bash
curl -fsS https://raw.githubusercontent.com/hashicorp/terraform-provider-aws/v5.100.0/website/docs/r/ce_cost_allocation_tag.html.markdown | grep -nE 'terraform import|import \{|id *= *"' | head -5
curl -fsS https://raw.githubusercontent.com/hashicorp/terraform-provider-aws/v5.100.0/internal/service/ce/cost_allocation_tag.go | grep -nE 'WithoutTimeout:|StatusInactive' | head -8
```
Success looks like an import line keyed by the tag key, `CreateWithoutTimeout:
resourceCostAllocationTagUpdate`, and a `CostAllocationTagStatusInactive` in the delete path. Paste
it into the PM review if it is wanted as the citation.

## Follow-up work

1. **Remove the two `import` blocks after the apply** (`v1-e05`, a one-line change; the PM decides).
   Once the tags are in state, the blocks' only remaining effect is on a new account, where they
   fail the whole root's plan until AWS has listed both keys. Without them, a new account's step 4
   apply fails only on the two tags, and a second apply after step 5 completes it.
2. **`prevent_destroy` on the tags** (`v1-e05`, optional). A destroy deactivates them. Today the plan
   check and the PM's read stand in the way; `prevent_destroy` would stop it in Terraform itself, if
   the module tests' teardown under `mock_provider` allows it.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-01

**Notes:**

The Project and Environment tags are now held Active by Terraform. A reset shows as drift, and a
destroy is refused before it can zero the budgets.
1. **ac1, first half: passes.**
   * Red at a skeleton that manages no tag: 0 passed, 2 failed, every failure an assertion.
     Green at `d869f47`: 2 passed.
   * The structural test covers what the Terraform tests cannot see: a third tag elsewhere in the
     module or in the root, and the root's module call. Mutants 3b, 3c and 5 show it.
   * 15 mutants, every catch an assertion. You dropped the first mutant 5, a trailing slash,
     because it is not a defect. That is the right standard.
   * `terraform_checks.sh` passes offline against the mirror, and no lock file changed.
   * ac1's second half stays open (point 5).
2. **The provider claims check out.**
   * Your loopback stand-in ran the locked 5.100.0 binary and is the strongest evidence here. It
     shows:
     * create calls the same `UpdateCostAllocationTagsStatus` as a change;
     * an import plan reads each tag and shows it no-op with `importing`;
     * the apply makes no call;
     * a destroy sends `Inactive`.
   * The provider's generated docs (the Pulumi mirror of this resource) agree that the import id is
     the tag key.
   * I could not fetch the GitHub source from here. The optional curl citation block is not needed,
     so the operator can skip it.
3. **Deviations and decisions accepted:**
   * the module called from the root, since that is the only place `terraform test` runs;
   * the plan-check test in `tests/infrastructure`;
   * the hand activation command taken out of step 5;
   * import blocks rather than create, because only an import plan shows the PM that both tags are
     already Active;
   * the tag keys fixed in the module, with the root's `check` for the monitor's key;
   * the plan block refusing AWS keys in the shell.

   The JSON plan check counts change entries rather than text lines, and its 26-unchanged-`aws_ssoadmin`
   test is exactly the run-lock lesson.
4. **Follow-up rulings:**
   * **Follow-up 1 (remove the import blocks after the apply): yes.** It becomes a p3 E05 task in
     the next PM batch, after this Goal is Succeeded. After the apply, the blocks' only remaining
     effect is to fail a new account's whole-root plan.
   * **Follow-up 2 (`prevent_destroy`): declined, not filed.**
     * `terraform test` destroys what it created at teardown, so `prevent_destroy` would make the
       module's own tests fail.
     * It would also block any deliberate change to the key list.
     * The plan check's destroy refusal, the PM's read and step 5 are enough.
5. **Merge and what comes next.**
   * Merge `--partial` once the PR's `ci` is green. The Goal stays InProgress for ac1's second half.
   * After the merge, the operator runs the runbook's "Applying the cost allocation tags":
     * the plan;
     * `COSTTAGSPLAN`, which must print `PLAN OK`;
     * the PM's read;
     * the apply.
   * The expected plan is `Plan: 2 to import, 0 to add, 0 to change, 0 to destroy.`
   * This apply comes before any other apply of `bootstrap/organization`, e05-t17's included.
   * Not on a Wednesday.

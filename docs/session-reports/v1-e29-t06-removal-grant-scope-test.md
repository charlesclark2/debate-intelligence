# Session report: v1-e29-t06-removal-grant-scope-test

| | |
|---|---|
| Task | `v1-e29-t06-removal-grant-scope-test` — Removal grants: the scope is tested, and a plan can count versions |
| Spec | [`plan_specs/v1/e29-cloud-evidence-store/t06-removal-grant-scope-test.yaml`](../../plan_specs/v1/e29-cloud-evidence-store/t06-removal-grant-scope-test.yaml) |
| Epic / release | `v1-e29-cloud-evidence-store` / `v1.1` |
| Branch | `task/v1-e29-t06-removal-grant-scope-test` |
| Session status | PARTIAL <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

Every statement in both evidence permission sets now has its Resource and its `s3:prefix`
condition asserted, and EvidenceOperator gains the one read-only statement from v1-e30-t07's
Operator follow-up 2. Before any change, the tests stayed green with EvidenceRemoval's
`ListBucketVersions` pointed at an object ARN, with its prefix condition removed, and with
EvidenceOperator's `ListBucket` pointed at an object ARN. All three are now red, and so are the
same two mutants on the new operator statement and a new statement the rule cannot classify.
Coverage is one assertion per policy. It classifies each statement by the resource shape its
actions need and fails on a count when any statement goes unclassified; I showed that count is
load-bearing by removing it. **ac1–ac5 pass. ac6 is NOT RUN**: it needs the dev and prod applies,
which are operator steps (below), so the Goal stays `InProgress`. Merge with
`scripts/task pr --partial`; the PM records ac6 and closes the task. The first thing to look at is
**Decisions 1**, on what "uncovered" means for a rule that classifies by action.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `show-the-gap` | Done | Both EvidenceRemoval mutants, and the EvidenceOperator `ListBucket` one, green against the test at `5b5e1b4` (outputs below), before anything changed. |
| `coverage` | Done | `0f91b1e`. One assertion per policy over every statement, with shared hand-written expectations in the test file's `variables`. |
| `grant` | Done | `63101df`. The statement from v1-e30-t07 follow-up 2, verbatim in substance; exact action set updated by hand. |
| `mutation` | Done | Seven mutants red, plus the count-removed control. Each restored, tree clean after each. |
| `apply` | Not run (operator) | Operator follow-ups 1–5. |

## Acceptance criteria

`terraform test` takes about 5 s here (`terraform -chdir=infrastructure/modules/evidence_bucket
test`, Terraform 1.16.3, `mock_provider "aws"`). No Python test was touched, so no run involved
Hypothesis and working agreement 8's database rule had nothing to apply to.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1** — every EvidenceRemoval statement's Resource asserted by shape, with a count that fails on any uncovered statement | PASS | `removal_permission_set_deletes_disclosed_material_and_nothing_else`, assertion at `tests/evidence_bucket.tftest.hcl:599`. Mutant *removal-list-versions-object-arn* → `Failure! 10 passed, 1 failed`, on line 600. The count, shown load-bearing on the operator twin (identical expression): with it removed, the uncovered-statement mutant → `Success! 11 passed, 0 failed`. |
| **ac2** — the EvidenceRemoval `ListBucketVersions` `s3:prefix` condition is asserted | PASS | Same assertion: a bucket-level statement must carry exactly `list_prefixes_of_action[action]`. Mutant *removal-list-versions-no-condition* → `Failure! 10 passed, 1 failed`, line 600. |
| **ac3** — both mutations red now, green before; restored, tree clean | PASS | Before (HEAD `5b5e1b4`, test unchanged): both mutants `terraform test exit 0`, `Success! 11 passed, 0 failed`. After (HEAD `63101df`): both `exit 1`, `Failure! 10 passed, 1 failed`. After each run, `git checkout -- operator_access.tf` and `git status --porcelain` empty (`restored; tree clean`). |
| **ac4** — the same coverage on EvidenceOperator; its `ListBucket` resource mutation red | PASS | `operator_permission_set_reads_and_publishes_but_cannot_delete`, assertion at line 479. Mutant *operator-list-bucket-object-arn*: green before (`5b5e1b4`, 11 passed), red after (`Failure! 10 passed, 1 failed`, line 480). |
| **ac5** — EvidenceOperator `s3:ListBucketVersions` on the bucket ARN under the removable-prefix condition, nothing else changes; covered and in the exact action set; object ARN and dropped condition red | PASS | `operator_access.tf` Sid `ListEvidenceObjectVersionsForRemovalPlans`. The exact action set (now eight) went red when the grant was added before the set was updated (line 438, `Failure! 10 passed, 1 failed`), green after. Mutants *operator-list-versions-object-arn* and *operator-list-versions-no-condition* → each `Failure! 10 passed, 1 failed`, line 480. Diff vs `5b5e1b4`: one statement in `operator_policy` plus comments; permission-set description, session duration, assignments and the removal policy unchanged. |
| **ac6** — applied dev then prod by the runbook, dates recorded; dev dry run under the everyday profile counts versions | NOT RUN | Needs `debate-admin` and two applies, which are operator steps (spec: forbidden; working agreement 2). Operator follow-ups 1–5. The **before** half was measured in this session, read-only, under the everyday profile only, on 2026-10-08: see "The before state of ac6". |
| `show-the-gap`: the wrong resource shown passing before the fix | PASS | ac3 row; outputs below. |
| `coverage`: `terraform -chdir=infrastructure/modules/evidence_bucket test` passes on the unmodified module | PASS | At `0f91b1e`: `Success! 11 passed, 0 failed.` |
| `grant`: `terraform test` passes with the new grant | PASS | At `63101df`: `Success! 11 passed, 0 failed.` |
| `mutation`: each mutation red, EvidenceRemoval pair green before, all restored, tree clean | PASS | Table under "Proving it by mutation". |
| `apply`: applied in dev and prod; the dry run counts versions | NOT RUN | As ac6. |

Also run: `terraform -chdir=infrastructure/modules/evidence_bucket validate` → `Success! The
configuration is valid.`; `scripts/terraform_checks.sh` (fmt, validate, tflint and `terraform test`
for every root and module) → `All Terraform checks passed.` in 1 min 29 s;
`uv run python scripts/check_links.py` → `OK: 1265 relative links and anchors in 173 Markdown
files`; `uv run scripts/validate_specs.py` → `OK`.

## Showing the gap (before any change)

The mutator is a short script keyed on statement Sids (it rewrites one statement's `Resource` to
`"${aws_s3_bucket.evidence.arn}/raw/*"`, or deletes its `Condition`). The first attempt at the
condition mutant raised in the mutator before writing anything, and `terraform test` then ran on
the unmodified module and passed. That run is **not counted** (working agreement 8: an attempt that
errors before it runs is not a result). The runner was changed to refuse to test when the mutation
did not apply, and the mutant was redone:

```
=== mutant: removal-list-versions-object-arn (baseline, HEAD 5b5e1b4)
@@ -118,3 +118,3 @@ locals {
         Action   = "s3:ListBucketVersions"
-        Resource = aws_s3_bucket.evidence.arn
+        Resource = "${aws_s3_bucket.evidence.arn}/raw/*"
         Condition = {
terraform test exit 0
Success! 11 passed, 0 failed.
restored; tree clean

=== mutant: removal-list-versions-no-condition (baseline, HEAD 5b5e1b4)
@@ -119,5 +119,2 @@ locals {
         Resource = aws_s3_bucket.evidence.arn
-        Condition = {
-          StringLike = { "s3:prefix" = local.removable_list_prefix_conditions }
-        }
       },
terraform test exit 0
Success! 11 passed, 0 failed.
restored; tree clean

=== mutant: operator-list-bucket-object-arn (baseline, HEAD 5b5e1b4)
@@ -75,3 +75,3 @@ locals {
         Action   = "s3:ListBucket"
-        Resource = aws_s3_bucket.evidence.arn
+        Resource = "${aws_s3_bucket.evidence.arn}/raw/*"
         Condition = {
terraform test exit 0
Success! 11 passed, 0 failed.
restored; tree clean
```

## Proving it by mutation

At `63101df` (coverage and grant in place). Each run started from a clean tree, applied one
mutant, ran `terraform test`, restored with `git checkout -- operator_access.tf` and confirmed
`git status --porcelain` empty. Line 480 is the condition of the operator coverage assertion and
line 600 the removal one. Every red run failed on that assertion alone, with its own message
("Every operator statement must be covered and scoped to its shape: …" / "Every takedown
statement …").

| Mutant | Before (`5b5e1b4`) | After (`63101df`) |
|---|---|---|
| EvidenceRemoval `ListBucketVersions` → object ARN under `raw/` | green, 11 passed | **red**, 10 passed 1 failed, line 600 |
| EvidenceRemoval `ListBucketVersions` condition removed | green, 11 passed | **red**, line 600 |
| EvidenceOperator `ListBucketVersions` → object ARN under `raw/` | (statement did not exist) | **red**, line 480 |
| EvidenceOperator `ListBucketVersions` condition removed | (statement did not exist) | **red**, line 480 |
| EvidenceOperator `ListBucket` → object ARN under `raw/` | green, 11 passed | **red**, line 480 |
| A new EvidenceOperator statement: `Action = ["s3:ListBucketVersions", "s3:GetObjectVersion"]`, `Resource = [bucket ARN, "<bucket>/raw/*"]`, no condition | (not applicable: the action set had no `ListBucketVersions`) | **red**, line 480 |
| `uploads/` dropped from the `ListBucket` prefix condition (checks the Sid-keyed assertion I removed is still covered, Decisions 2) | (old Sid-keyed assertion) | **red**, line 480 |

**The count is what catches the uncovered statement.** The new statement mixes a bucket action and
an object action, so the rule cannot classify it and the per-statement half skips it. To show the
count is not redundant, I removed only the `length(...) == length(statements) &&` clause from the
operator assertion and applied the same mutant: `terraform test exit 0`, `Success! 11 passed, 0
failed`. Without the count, a statement granting `ListBucketVersions` over the whole bucket with no
condition passes the exact action set, the "own bucket or key" assertion and everything else. Both
files were restored and the tree confirmed clean.

## The before state of ac6

Measured in this session on 2026-10-08, read-only, with the everyday profile only (`AWS_PROFILE`
and `DEBATE_REMOVAL_PROFILE` unset). The account id and the SSO session name are redacted here.

```
$ aws sts get-caller-identity --profile debate-dev-evidence --query Arn --output text
arn:aws:sts::<account>:assumed-role/AWSReservedSSO_DebateDevEvidenceOperator_<suffix>/<session>
$ aws s3api list-object-versions --profile debate-dev-evidence --bucket debate-dev-evidence-a7508de8 --prefix raw/caselist/testcl26/ --max-items 1 --query 'length(Versions)'
An error occurred (AccessDenied) when calling the ListObjectVersions operation: User: arn:aws:sts::<account>:assumed-role/AWSReservedSSO_DebateDevEvidenceOperator_<suffix>/<session> is not authorized to perform: s3:ListBucketVersions on resource: "arn:aws:s3:::debate-dev-evidence-a7508de8" because no identity-based policy allows the s3:ListBucketVersions action
```

`DEBATE_ENV=dev uv run --frozen debate-research caselist remove --source 000…0 (64 zeros)
--request RM-2026-99 --reason POLICY` (16 s, exit 0) printed `DRY RUN: nothing was changed`, the
digest as *held nowhere in this environment: it is only suppressed*, and:

```
Versions not counted: the everyday profile may not list object versions. --execute lists and
deletes every version with the takedown profile, and reports how many.
```

With `--json`: `"status": "ok"`, `"applied": false`, `"versions_counted": false`, 0 objects. The
plan always lists versions under `parsed/openev/`, plus `raw/caselist/<c>/` and `parsed/<c>/` for
every caselist with a manifest locally or in the bucket. So even a digest held nowhere makes real
`ListBucketVersions` calls under removable prefixes, and `versions_counted` reflects the grant
rather than an empty plan. `git status` stayed clean.

## Files changed

- `infrastructure/modules/evidence_bucket/tests/evidence_bucket.tftest.hcl`: the two
  expectations tables (`resource_shape_of_action`, `list_prefixes_of_action`) in the file-level
  `variables`; the statement-coverage assertion in the operator and removal runs; the operator's
  exact action set now eight, by hand. The Sid-keyed `ListDocumentedEvidencePrefixes` condition
  assertion is removed (Decisions 2).
- `infrastructure/modules/evidence_bucket/operator_access.tf`: the
  `ListEvidenceObjectVersionsForRemovalPlans` statement, and the header comment on what
  EvidenceOperator does.
- `infrastructure/modules/evidence_bucket/README.md`: the grants table, and how the coverage
  expects a new action or statement to be added.
- `docs/runbooks/evidence-store.md`: the operator credential's description; a version-listing
  check in step 5 (allowed under a removable prefix, refused under `reports/` and at the root); a
  *Later applies* table for this change's dates (ac6); and what to do if the listing is refused
  just after an apply.
- `docs/runbooks/caselist-removal.md`: the dry run shows version counts once the grant is applied
  in that environment, and says *Versions not counted* before then.

## Deviations from the spec

None. Every changed path is in `constraints.packages` (`infrastructure/modules/evidence_bucket`,
`docs`). The only grant change is the one the spec allows.

## Decisions and assumptions

1. **What "uncovered" means for this rule.** The forbidden list rules out naming statements by
   hand. The assertion instead classifies every statement by the resource shape its actions need,
   from a hand-written table of **actions** (`resource_shape_of_action`). A statement is uncovered,
   and fails the count, when an action is not in the table or its actions need different shapes.
   A statement added later whose actions are all known and of one shape is not uncovered: it is
   covered from the moment it exists, and its resource and condition are checked by the same rule.
   That is why the "new uncovered statement" mutant is a mixed one. A same-shape statement would
   have been checked and caught (an object ARN, a missing condition) or rightly passed. The table is
   the one place a person must act on purpose, and the test says so.
2. **The Sid-keyed `ListBucket` condition assertion is removed.** It named one statement by Sid and
   duplicated the prefix list now held in `list_prefixes_of_action`. The coverage assertion does its
   job for every listing statement; the `uploads/`-dropped mutant shows it, red on line 480. Its
   explanation ("a prefix missing here is a prefix the CLI cannot see") moved into the table's
   comment.
3. **Expectations are test-file variables, not module inputs.** Terraform 1.16 lets an assertion
   read a file-level `variables` value the module does not declare, with no warning; I checked
   that on a throwaway module first. It keeps the two assertions reading one table rather than two
   copies that could drift. The values are written by hand (working agreement 6), not read from
   the module's locals.
4. **No condition outside listing statements.** The rule also requires object and key statements
   to carry no `Condition`. An `s3:prefix` condition on an object statement can never match, so
   "every `s3:prefix` condition is asserted" means that one must fail as well. Nothing in either
   policy has one today.
5. **Where the applies run from.** The roots are shared, and the runbook says to apply from a
   checkout with every merged task. Dev therefore plans and applies from the `dev-preview` worktree
   (detached at `origin/dev`) after this task merges with `--partial`. Prod plans and applies from
   `prod-deploy` on `main`, after the promotion that carries this change: `main` is production
   (ADR-0013), and applying prod from `dev` would also apply anything unpromoted. Both are the
   worktrees `docs/runbooks/team-website.md` keeps for this.
6. **Read-only AWS calls in the session.** The PM ruled out admin credentials and applies. The two
   before-state calls above used the everyday profile and changed nothing; no `terraform plan` was
   run, because the plan runs as `debate-admin`.

## Operator follow-ups

All five come after the PM review and `scripts/task pr --partial`. The plan, the apply and the
checks run as the runbook's procedure (steps 1, 3, 5 and 6), narrowed to this change. A permission
set change usually takes effect within seconds of the apply and occasionally a few minutes. Terraform
waits for Identity Center to provision the set into the account, IAM then propagates it, and sessions
already signed in pick it up without signing in again. If the first check is still refused,
wait two minutes and retry, then follow the runbook's *If something is wrong*, "`AccessDenied` on
`s3:ListBucketVersions` with the everyday profile". It checks read-only that provisioning succeeded
and that the role's inline policy carries the Sid, and says when to stop and send the output.

1. **Dev plan** (expected runtime ~2 min). Where: the `dev-preview` worktree, after this task has
   merged into `dev`. `-input=false` turns a missing `owner.auto.tfvars` into an error instead of a
   prompt for `var.owner`. Without that file the plan would propose destroying every account
   assignment in the root.

   ```bash
   cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/dev-preview
   git fetch origin
   git switch --detach origin/dev
   git log --oneline -1
   grep -c ListEvidenceObjectVersionsForRemovalPlans infrastructure/modules/evidence_bucket/operator_access.tf
   test -f infrastructure/envs/dev/owner.auto.tfvars && echo "owner.auto.tfvars present" || echo "owner.auto.tfvars MISSING: stop"
   aws sso login --sso-session debate
   aws sts get-caller-identity --profile debate-admin --query Arn --output text
   export AWS_PROFILE=debate-admin
   terraform -chdir=infrastructure/envs/dev init -input=false
   terraform -chdir=infrastructure/envs/dev plan -input=false -out=/tmp/evidence-dev-t06.tfplan
   ```

   If the file is missing, copy it from the checkout the last evidence apply ran from (it is
   gitignored, so a worktree does not get it), then run the block again.

   Success looks like: `grep -c` prints `1`, `owner.auto.tfvars present`, an ARN containing
   `AWSReservedSSO_DebateBreakGlassAdmin`, and **exactly this diff**:

   ```
     # module.evidence_store.aws_ssoadmin_permission_set_inline_policy.evidence_operator[0] will be updated in-place
     ~ resource "aws_ssoadmin_permission_set_inline_policy" "evidence_operator" {
         ~ inline_policy = jsonencode(
             ~ {
                 ~ Statement = [
                       { ... Sid = "ListDocumentedEvidencePrefixes" ... unchanged },
                     + {
                         + Action    = "s3:ListBucketVersions"
                         + Condition = {
                             + StringLike = {
                                 + "s3:prefix" = [ "raw/", "raw/*", "parsed/", "parsed/*", "files/", "files/*",
                                                   "manifests/", "manifests/*", "quarantine/", "quarantine/*" ]
                               }
                           }
                         + Effect    = "Allow"
                         + Resource  = "arn:aws:s3:::debate-dev-evidence-a7508de8"
                         + Sid       = "ListEvidenceObjectVersionsForRemovalPlans"
                       },
                       # (2 unchanged elements hidden)
                   ]
               }
           )
       }

   Plan: 0 to add, 1 to change, 0 to destroy.
   ```

   That is one policy statement added to one permission set's inline policy, and nothing else.
   Terraform may lay the list out differently, for example as changed elements after the first
   rather than one inserted element. Either way, the only new content must be that one statement.
   **Stop and send the plan** if it shows anything more: another resource, a change to
   `DebateDevEvidenceRemoval`, to a permission set's description or session duration, to an
   account assignment, to the bucket or the key, or any destroy. That would be another task's
   unapplied change, or a stale checkout, and it is not this task's to apply.

2. **Dev apply** (expected runtime ~2 min). Where: the same `dev-preview` worktree, straight after
   follow-up 1 shows the expected plan.

   ```bash
   cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/dev-preview
   export AWS_PROFILE=debate-admin
   terraform -chdir=infrastructure/envs/dev apply -input=false /tmp/evidence-dev-t06.tfplan
   unset AWS_PROFILE
   ```

   Success looks like: `Apply complete! Resources: 0 added, 1 changed, 0 destroyed.` Note the date
   for the runbook's *Later applies* table.

3. **The ac6 check: the dry run counts versions** (expected runtime ~1 min, longer on the first
   `uv run` in this worktree if it has to build the environment). Where: the `dev-preview`
   worktree. Everyday profile only: neither `AWS_PROFILE` nor `DEBATE_REMOVAL_PROFILE` is set, and
   a dry run never builds the takedown client. The digest is held nowhere, so nothing can be
   removed, and the dry run writes nothing.

   ```bash
   cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/dev-preview
   unset AWS_PROFILE DEBATE_REMOVAL_PROFILE
   aws sts get-caller-identity --profile debate-dev-evidence --query Arn --output text
   DEBATE_ENV=dev uv run --frozen debate-research caselist remove --source 0000000000000000000000000000000000000000000000000000000000000000 --request RM-2026-99 --reason POLICY
   DEBATE_ENV=dev uv run --frozen debate-research --json caselist remove --source 0000000000000000000000000000000000000000000000000000000000000000 --request RM-2026-99 --reason POLICY | grep -o '"versions_counted": *[a-z]*'
   ```

   Success looks like: an ARN containing `AWSReservedSSO_DebateDevEvidenceOperator`; a plan that
   starts `DRY RUN: nothing was changed. dev, bucket debate-dev-evidence-a7508de8.`, reports the
   digest as held nowhere, and **has no "Versions not counted" paragraph**; and the last line
   `"versions_counted": true`. Before the apply, on 2026-10-08, the same commands printed the
   paragraph and `"versions_counted": false` (see "The before state of ac6"). Paste both outputs
   back for the record.

4. **Version listing with the everyday profile, read-only** (expected runtime ~1 min). Where:
   anywhere. The first call failed with `AccessDenied` on 2026-10-08. The second and third must
   still fail: they show the prefix condition working in the real account, not only in the test.

   ```bash
   aws s3api list-object-versions --profile debate-dev-evidence --bucket debate-dev-evidence-a7508de8 --prefix raw/caselist/testcl26/ --query 'length(Versions)'
   aws s3api list-object-versions --profile debate-dev-evidence --bucket debate-dev-evidence-a7508de8 --prefix reports/ --max-items 1
   aws s3api list-object-versions --profile debate-dev-evidence --bucket debate-dev-evidence-a7508de8 --max-items 1
   ```

   Success looks like: a number for the first (11 after v1-e30-t07's exercise, unless testcl26 has
   changed since), and `AccessDenied` naming `s3:ListBucketVersions` for the second and third. A
   second or third call that succeeds means the condition did not reach the account: stop before
   prod.

5. **Prod plan and apply** (expected runtime ~5 min). Where: the `prod-deploy` worktree on `main`,
   after the promotion PR that carries this change has merged, and only after follow-ups 3 and 4
   passed in dev.

   ```bash
   cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/prod-deploy
   git branch --show-current
   git pull --ff-only
   git log --oneline -1
   grep -c ListEvidenceObjectVersionsForRemovalPlans infrastructure/modules/evidence_bucket/operator_access.tf
   test -f infrastructure/envs/prod/owner.auto.tfvars && echo "owner.auto.tfvars present" || echo "owner.auto.tfvars MISSING: stop"
   aws sso login --sso-session debate
   export AWS_PROFILE=debate-admin
   terraform -chdir=infrastructure/envs/prod init -input=false
   terraform -chdir=infrastructure/envs/prod plan -input=false -out=/tmp/evidence-prod-t06.tfplan
   ```

   Success looks like: `main`, `grep -c` prints `1`, the file present, and the same diff as dev with
   `Resource = "arn:aws:s3:::debate-prod-evidence-a7508de8"`: `Plan: 0 to add, 1 to change, 0 to
   destroy.` **Stop and send the plan** if it shows anything more. If it is right:

   ```bash
   cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/prod-deploy
   export AWS_PROFILE=debate-admin
   terraform -chdir=infrastructure/envs/prod apply -input=false /tmp/evidence-prod-t06.tfplan
   unset AWS_PROFILE
   aws s3api list-object-versions --profile debate-prod-evidence --bucket debate-prod-evidence-a7508de8 --prefix raw/ --max-items 1 --query 'Versions[0].Key' --output text
   aws s3api list-object-versions --profile debate-prod-evidence --bucket debate-prod-evidence-a7508de8 --prefix reports/ --max-items 1
   ```

   Success looks like: `Apply complete! Resources: 0 added, 1 changed, 0 destroyed.`; a key under
   `raw/` (or `None` if prod has nothing there yet) from the first listing; and `AccessDenied`
   naming `s3:ListBucketVersions` from the second.

Then fill in both dates in the *Later applies* table of
[docs/runbooks/evidence-store.md](../runbooks/evidence-store.md#later-applies), on a branch. That
row and the follow-up 3 output are what ac6 asks for.

## Follow-up work

1. **E30 / debate_core: two docstrings go stale when the grant is applied.**
   `removal_plan.py` (module docstring: "which the everyday profile does not have today") and
   `integrations/s3/version_store.py` (line 13: "says 'not counted' until then") describe the state
   before this task. The CLI's "Versions not counted" message itself stays correct: it prints
   only when listing is refused. Both are `debate_core`, outside this task's packages.
2. **E30 (v1-e30-t07 Follow-up 6): a read-only report of noncurrent residue in `caselist status`**
   becomes possible once this is applied, as the spec notes. That is `debate_core` work.
3. **Docs (working agreement 9): `docs/runbooks/evidence-store.md` still has `#` comments inside
   command blocks** that predate this task: `WT=/path/to/your/checkout  # e.g. …`, the
   `terraform fmt` explanation in *Before you start*, `AWS_PAGER=""  # …` and the `KEY_ID` note in
   step 5. Pasted into zsh, the first runs `#` as a command (`command not found: #`) with `WT`
   set only for that command, so `WT` is left unset for every block after it. I added none and
   changed none. They belong with `v1-e01-t19`'s check, or a small
   docs fix.
4. **`v1-e29-t03` ac3's "grants only" list** is superseded by this task, as the spec says; that
   spec is the PM's to amend.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-08

**Notes:**

Accepted as a partial merge: `scripts/task pr --partial`. ac1–ac5 pass; ac6 waits for the operator's applies, and the Goal stays `InProgress` until the PM records them.

- **Checked against the branch** (`feae041`, tree clean). `operator_access.tf` gains exactly one statement, `ListEvidenceObjectVersionsForRemovalPlans`: `s3:ListBucketVersions` on the bucket ARN under `local.removable_list_prefix_conditions`. Nothing else in either policy changes. Both coverage assertions iterate over every rendered statement. They classify each statement by `resource_shape_of_action` and fail on the count when a statement is unclassified. They check the bucket ARN plus the exact `s3:prefix` set for listing actions, object ARNs in this bucket, and this key. The test changed in no other way, apart from the exact action set going from seven to eight.
- **The baseline is what makes this credible.** It shows three mutants green at `5b5e1b4` before anything changed. The count is shown to be load-bearing by removing it. The mutator now refuses to test a mutation that did not apply, and the discarded first attempt is reported as such. Both are right under working agreement 8.
- **Decisions 1–6 are accepted.**
  - Decision 1: classifying by action is the right reading of "no hand-listed statements". The table of actions is where a person has to act on purpose.
  - Decision 4: if an object statement ever needs a condition (an SSE condition on `PutObject`, say), this test will fail loudly. That is intended. Whoever adds it changes the rule and the table in the same commit.
  - Decision 5: dev plans and applies from `dev-preview` after this merges. Prod plans and applies from `prod-deploy` only after the promotion that carries this change.
  - Decision 6: read-only calls under the everyday profile were within the instruction.
- **Follow-up work.**
  - Item 1, the two stale `debate_core` docstrings: the PM files them at close-out, together with v1-e30-t07 follow-up 6 (the noncurrent-residue report).
  - Item 3, the `#` comments in `evidence-store.md`: already in scope for `v1-e01-t19-paste-safe-command-blocks`, which fixes every instance. Nothing changes here.
  - Item 4: `v1-e29-t03` already carries the "superseded by v1-e29-t06" comment above ac3, so no amendment is needed.
- **The PM's close-out after the operator's follow-ups 1–5:**
  - record the dev and prod dates in *Later applies*;
  - record follow-up 3's output against ac6;
  - add `unset AWS_PROFILE` to the end of the new step-5 version-listing block, which leaves the everyday profile exported;
  - set the Goal to `Succeeded`.

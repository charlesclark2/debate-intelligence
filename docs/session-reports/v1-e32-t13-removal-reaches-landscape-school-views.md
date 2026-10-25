# Session report: v1-e32-t13-removal-reaches-landscape-school-views

| | |
|---|---|
| Task | `v1-e32-t13-removal-reaches-landscape-school-views` — A removal and the annual purge reach the landscape bundles' school views |
| Spec | [`plan_specs/v1/e32-argument-landscape/t13-removal-reaches-landscape-school-views.yaml`](../../plan_specs/v1/e32-argument-landscape/t13-removal-reaches-landscape-school-views.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t13-removal-reaches-landscape-school-views` |
| Session status | COMPLETE |

## Summary

`caselist remove` now reaches the landscape bundles' school views. The plan lists, under *LANDSCAPE
SCHOOL VIEWS*, every `schools.csv` and `schools.md` of every bundle of each caselist the removal
touches, on this machine and in the bucket. `--execute` deletes them under the removal profile,
every version included. The plan names the newest bundle to republish and never republishes.
`caselist status` reports a school view a removal should have deleted as `REMOVAL_RESIDUE` until it
is gone. The plan, the execution and status all choose files by one function,
`removal_school_views.is_school_view`, built on t04's constants: an unknown file is an error, and
the caselist segment is matched whole. The removal credential's inline policy gains one delete
statement and one listing prefix, proved by the module's Terraform test. The removal runbook's
manual section is replaced, and the annual purge has school-view steps. Every criterion passed, so
the Goal is `Succeeded`.

**Look at first:** the lock question has a short answer. `caselist remove --execute` already holds
the run lock (since `v1-e40-t04`, #480; see the relay block under Decisions). The other thing to
check is the rule for re-runs and residue. A re-run, and status, reach a caselist an earlier run
touched only for views written before that run completed, so a republished view is never taken or
counted.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `removal-landscape` — Removal reaches school views | Done | Plan, execute, status residue, Terraform grant, runbooks; tests shown red first, 12 Python and 4 Terraform mutants caught |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 — on a synthetic store with two caselists' bundles, the plan lists exactly the removed caselist's `schools.csv`/`schools.md`, local and bucket; `--execute` deletes them and their noncurrent versions; circuit-wide files and the other caselist's bundles byte-identical; tests shown failing first, against moto | PASS | `packages/debate_core/tests/application/caselist/test_removal_reaches_landscape_school_views.py` (moto, `testcl26` ×2 snapshots, `othercl26`, and `testcl26b` for the prefix case). Red against a refuse-nothing skeleton: `pytest -n 0 -p no:randomly <that file> test_removal_school_view_selection.py` → **21 failed, 28 passed**, every failure an `AssertionError` or `DID NOT RAISE UnknownLandscapeFile`, none an error. Green: **14 passed** (that file) and **35 passed** (selection file). `TestTheExecution::…byte_for_byte` compares every `(key, version id) → bytes` under `reports/` and every local file before and after |
| ac2 — `caselist status` reports a school view a removal should have deleted as residue, and clears once it is gone | PASS | `TestStatus::test_it_reports_views_a_removal_should_have_deleted_as_residue_and_clears_once_they_are_gone` (4 bucket + 4 local, `RemovalCompletion(RM-2026-01, 2026-09-30 18:00Z)`, `in_sync` false; after the same removal again, none). Red: failed against the skeleton (`assert () == (OlderVersions…`). CLI text and JSON: `packages/debate_cli/tests/commands/test_caselist_remove_school_view_output.py` → **12 passed** |
| ac3 — the removal credential's Terraform policy allows deleting those keys and nothing else new, by Terraform test; the removal runbook's manual landscape section is replaced; the annual purge's steps cover school views | PASS | `terraform test` in `infrastructure/modules/evidence_bucket` (offline provider mirror) → **13 passed, 0 failed**. Red: the new test file against `e747b7a`'s `operator_access.tf` → **12 passed, 1 failed** (assertions at lines 748, 786, 847), nothing skipped. `scripts/terraform_checks.sh` (offline) → *All Terraform checks passed* (42 s). Runbook: `docs/runbooks/caselist-removal.md`, "Argument landscape bundles (E32)" rewritten, and new "The annual purge: landscape school views" (dry-run and delete blocks; its script was run on synthetic data, see Decisions). `check_command_blocks.py` → OK. "Nothing else new": see Decisions, the listing prefix |
| Node `removal-landscape` — `uv run pytest packages/debate_core/tests -k removal` | PASS | verbatim → **398 passed in 39.45s**; again after the PM's ruling 4 → **399 passed in 36.00s** |
| PM ruling 2 (2026-10-24) — deletes granted only on `reports/landscape/*/schools.csv` and `…/schools.md`, pinned by a Terraform test that a widening or circuit-wide mutant fails | PASS | Assertions at `evidence_bucket.tftest.hcl` 748 (every delete resource, exactly) and 786 (the one statement reaching `reports/landscape/` deletes those two ARNs and nothing else). Mutants in the table below: *a whole bundle deletable* (`reports/landscape/*`) and *`report.md` added* both fail the run (12 passed, 1 failed, nothing skipped). Expected plan: see Decisions |
| PM ruling 4 (2026-10-24) — after deleting, `--execute` lists versions again under the removal credential and confirms no version or marker of the school views remains; an existing test cited or one added, shown failing first | PASS | No existing test covered it, and no code did it (see Deviations 3). Added `TestTheExecution::test_it_lists_again_after_deleting_and_a_view_still_there_leaves_the_removal_incomplete`: a removal credential that answers a delete of one key without doing it. Red → `Failed: DID NOT RAISE RemovalIncomplete`. Green after `_delete_bucket_school_views` re-lists and raises `SchoolViewsLeft` (`SCHOOL_VIEWS_LEFT`, counts only): new file **15 passed**; with the selection, removal-service and CLI output files **82 passed**; `tests/smoke/test_caselist_remove_smoke.py` and `bucket_mode/test_bucket_mode_removal.py` **46 passed in 96.09 s** |

### Mutants (fresh `HYPOTHESIS_STORAGE_DIRECTORY` per run; no Hypothesis property in these files)

Each mutant was one textual replacement, asserted to apply exactly once, run against the three new
test files (`-n 0 -p no:randomly`), then restored from git. `git status` was clean afterwards.

| Mutant (where) | Result | Caught by (first few) |
|---|---|---|
| Another caselist: the caselist check removed (`is_school_view`) | CAUGHT, 18 failed | `TestThePlan::…exactly_the_removed_caselists…`, `…another_caselists_bundle_is_left_alone`, the execution tests |
| A circuit-wide file counted as a school view | CAUGHT, 11 failed | `TestThePlan::…exactly…`, `TestTheExecution::…byte_for_byte`, `TestIsSchoolView::test_a_circuit_wide_file_never_is[*]` |
| A prefix slug: `startswith` instead of whole-segment match | CAUGHT, 13 failed | `TestThePlan::…exactly…` (the `testcl26b` bundle), `TestTheExecution::…byte_for_byte` |
| An unknown file guessed (`return False` for `raise`) | CAUGHT, 9 failed | `TestThePlan::…stops_the_plan`, `…one_in_the_bucket_stops_it_too`, `TestIsSchoolView::…never_a_guess[*]` |
| Noncurrent versions skipped (bucket delete keeps only latest, no markers) | CAUGHT, 6 failed | `TestTheExecution::…byte_for_byte`, `…a_version_the_dry_run_could_not_see…` |
| Local copies skipped | CAUGHT, 5 failed | `TestTheExecution::…byte_for_byte`, `TestARerun::*` |
| A re-run ignores the age (`reached` always true) | CAUGHT, 2 failed | `TestARerun::…republished_one`, `TestTheAgeRule::…only_before_that_run` |
| Cutoff per request, not per run | CAUGHT, 1 failed | `TestTheCutoffs::test_a_rerun_that_did_not_touch_a_caselist…` |
| A re-run forgets earlier runs (reach drops earlier scopes) | CAUGHT, 3 failed | `TestARerun::*`, `TestStatus::…clears_once_they_are_gone` |
| Status ignores the age | CAUGHT, 1 failed | `TestStatus::test_a_view_written_after_the_removal_is_not_residue` |
| Status ignores this machine | CAUGHT, 1 failed | `TestStatus::…clears_once_they_are_gone` |
| The 15-minute margin dropped | CAUGHT, 2 failed | `TestTheAgeRule::test_within_the_margin_or_after_is_not[*]` |
| Terraform: a whole bundle deletable (`reports/landscape/*`) | CAUGHT, 12 passed 1 failed | assertions 748, 766, 786, 803 |
| Terraform: `report.md` added to `school_view_files` | CAUGHT, 12 passed 1 failed | assertions 748, 766, 786, 803 (and the Python pin `TestTheRemovalCredentialsGrant`) |
| Terraform: the `reports/landscape/` listing prefix dropped | CAUGHT, 12 passed 1 failed | assertion 847 (listing shape) |
| Terraform: `s3:GetObjectVersion` added to the school-view statement | CAUGHT, 12 passed 1 failed | assertion 786 |

### Checks before the report

| Command | Result |
|---|---|
| `uv run ruff format --check packages tests` / `uv run ruff check packages tests` | clean |
| `uv run pyright packages/debate_core packages/debate_cli` | 0 errors, 0 warnings |
| `uv run --frozen lint-imports` | 16 kept, 0 broken |
| `uv run --frozen python scripts/check_thin_handlers.py` | OK: 51 handlers within 25 statements |
| `uv run scripts/validate_specs.py` | OK: 439 files, 40 epics, 377 tasks, 22 releases |
| `uv run --frozen python scripts/docs_index.py --check-descriptions` | all 47 indexed documents described |
| `uv run --frozen python scripts/check_command_blocks.py` | OK |
| `uv run scripts/affected_tests.py` | **326 of 463 test files (70.4 %)** from 24 changed files. The `ObjectInfo` port and the landscape constants are hub modules |
| The affected set, `.venv/bin/python -m pytest -n auto -m "not slow and not live"` under `perl -e 'alarm 115'` | **stopped by the alarm at 63 %** (exit 142, load average 9). The part that ran found one failure (a whole-`CaselistResidue` equality in `test_manifest_and_aggregate_residue.py`), which was fixed in code (see Decisions). **The whole affected set is left to the PR's `ci`** (agreement 10, PM ruling 2026-10-19) |
| The changed directories and always-run list, each under 115 s: `packages/debate_core/tests/application/caselist` | 1613 passed in 95.81 s |
| `packages/debate_cli/tests/commands`, `bucket_mode`, and the CLI tests naming the removal, status or landscape services | 635 passed in 54.75 s (the whole `packages/debate_cli/tests` was stopped by the alarm at load average 31) |
| `packages/debate_core/tests/integrations/s3`, `…/integrations/local`, `…/contracts`, `test_landscape_{report,run,scan,schools}.py`, `tests/architecture`, `tests/specs` | 1041 passed in 16.40 s |
| `tests/smoke/test_caselist_remove_smoke.py` | 42 passed in 108.30 s (after the eight whole-JSON pins gained the two new keys, see Files changed) |

## Files changed

* **`packages/debate_core/src/debate_core/application/caselist/removal_school_views.py`** (new):
  the selection (`is_school_view`, `UnknownLandscapeFile`), the reach and age rule (`SchoolViewReach`,
  `reached`, `written_before`), the cutoffs status and a re-run share (`school_view_cutoffs`) and
  status's count (`school_views_left`).
* **`application/landscape_bundle_files.py`** (new): the one definition of `REPORTS_PREFIX`,
  `CIRCUIT_WIDE_FILES` and `SCHOOL_VIEW_FILES`, moved unchanged from `landscape_run` and
  `landscape_report`, which still export them. See Decisions.
* **`removal_plan.py`**: `SchoolViewRemoval`, and the plan's `school_view_reach`, `school_views`,
  `school_view_versions_counted` and `republish`. `nothing_to_do` counts school views. The planner
  takes `local_reports` and reads the log and scopes once.
* **`removal_service.py`**: two steps, the bucket's views (after `raw/`/`parsed/`) and this machine's
  (after its blobs and parsed files). The bucket step lists again after deleting and raises
  `SchoolViewsLeft` if any version or marker it reached is still there (PM ruling 4). Display counts
  on `RemovalReport`; the log line is unchanged.
* **`removal_residue.py`, `status_service.py`**: `CaselistResidue.school_views` and
  `school_views_older_than`, part of `found`. Status takes `local_reports`.
* **`ports/evidence_store.py`, `integrations/s3/object_store.py`**: `ObjectInfo.last_modified`
  (optional, `compare=False`), filled by the S3 listing. **`integrations/local/fs_version_store.py`**:
  each version dated by the file's modification time.
* **`debate_cli`**: `container.py` wiring; `caselist_remove.py` (*LANDSCAPE SCHOOL VIEWS*,
  *REPUBLISH*, the confirmation line, the `DONE` line, JSON `school_views` and `school_views_deleted`);
  `caselist.py` status text and JSON.
* **Tests**: the two new core files above; `commands/test_caselist_remove_school_view_output.py`;
  `conftest.py` (the world passes `local_reports`, signature-guarded like `removal_log`);
  `test_caselist_remove_output_loose_ends.py` (the pinned plan JSON keys gain `school_views` and,
  after an execution, `school_views_deleted`); `tests/smoke/test_caselist_remove_smoke.py` (a new end
  to end check, and the three pinned residue JSON shapes gain `school_views` and
  `school_views_older_than`).
* **`infrastructure/modules/evidence_bucket`**: `operator_access.tf`, with `landscape_prefix`,
  `school_view_files`, the `DeleteLandscapeSchoolViews` statement and the listing prefix pair; the
  Terraform test's removal run.
* **`docs/runbooks/caselist-removal.md`**: the landscape section rewritten, the annual-purge
  section, a step 6 check, a residue line and the "Landscape school views" subsection.
  **`docs/runbooks/evidence-store.md`**: a "Later applies" row, not applied yet.

## Deviations from the spec

1. **The annual purge has no runbook to add steps to.** The spec says "the annual purge's runbook
   steps". The policy names the purge, but no runbook exists for it (`v1-e30-t01`'s follow-up 4, "no
   owner"). The school-view steps are a section of their own in `caselist-removal.md`, "The annual
   purge: landscape school views", which says the purge's other steps have no runbook yet. Writing
   the rest of the purge was out of scope.
2. **"Nothing else new" in ac3.** *(Ruled (A) by the PM on 2026-10-24, on the condition in ruling 2,
   which the existing assertions and mutants meet.)* The removal credential gains one delete statement, exactly
   `reports/landscape/*/schools.csv` and `…/schools.md`. Its version-listing condition also gains
   `reports/landscape/` and `reports/landscape/*`. That is listing, not deleting, and without it
   `--execute` cannot find a school view's noncurrent versions, which the spec requires it to
   delete. The PM should confirm this reading (relay question 2).

3. **The PM's ruling 4 says "as the removal does for `raw/` and `parsed/`", but it does not.**
   `_delete_bucket_objects` lists each `raw/`/`parsed/` key's versions once and deletes them; it
   never lists again afterwards. Only the preflight's probe (`removal_service.py`, "a version survived
   the delete") and the run-state bundle's save are confirmed, and `caselist status`'s version listing
   is the check for `raw/` and `parsed/` afterwards. The school views now get the confirmation the
   ruling describes. Whether `raw/` and `parsed/` should get it too is a follow-up, below.

## PM rulings of 2026-10-24

Recorded as a comment above the spec's `acceptanceCriteria` (checked: the parsed spec's
description, context and criteria are unchanged; `validate_specs.py` OK).

1. Run lock (A): no change.
2. Listing accepted (A), conditional on the delete grant being exactly the two school-view ARNs,
   pinned by a Terraform test with mutants. Met by the existing assertions and mutants (Acceptance
   criteria table).
3. Annual purge (A): the school-view steps stay their own section in `caselist-removal.md`. The PM
   files the purge-runbook task.
4. Status sees current views only (A), conditional on `--execute` re-listing after deleting.
   Implemented, test-first (Acceptance criteria table, Deviations 3).

## Decisions and assumptions

* **The run lock (the PM's question, answered first).** `caselist remove --execute` already runs
  inside `run_holding_the_bucket_lock(cli, "caselist remove", …)`, the same guard `caselist retire
  --bucket --execute` and `landscape report --publish` use. It was added by `v1-e40-t04` (#480),
  which is on this branch, and ADR-0020 (4) lists `caselist remove`. The test
  `test_each_bucket_writing_command_takes_the_lock_in_bucket_mode_and_releases_it` covers it. In
  bucket mode a removal and a publish are serialised. In local mode no command takes a lease; each
  refuses a seeded bucket, by ADR-0020's ruling 3(a). The race the PM described could only occur
  between two local-mode commands run at once by the operator. This task changed nothing about the
  lock.
* **Which views a removal reaches.** It reaches every view of each caselist it touches now
  (`touched_caselists`, OpenEv apart). For a re-run it also reaches each caselist that an earlier
  *completed run* of the same request touched (from the scopes beside the log), but only the views
  written before that run completed, by the residue check's 15-minute margin. Without this, a re-run
  of a completed removal plans nothing and status residue could never clear. Without the age rule, a
  re-run would delete the republished view.
* **Per run, not per request.** `school_view_cutoffs` takes, per caselist, the latest completed run
  whose *own* scope names it. The existing `completed_removals` takes the request's latest
  completion over all its scopes. With that rule, a re-run that did not touch a caselist would move
  the cutoff past a republish, and status would flag the republished view. The mutant table shows
  the per-run rule is tested.
* **Status sees the bucket's current school views only.** The everyday profile may list `reports/`
  but not its versions, and the PM ruled that only the removal credential's policy changes. Status
  therefore reads a plain listing, dated by the new `ObjectInfo.last_modified`. A noncurrent version
  left under a newer one is not counted; the runbook says so, and the re-run's `--execute` deletes
  those by the same rule.
* **`school_views_older_than` is set only when views are left.** Setting it whenever a cutoff
  existed broke an existing whole-object equality (`test_manifest_and_aggregate_residue.py:779`).
  The field explains found views, so it is `None` when none are found and no pinned expectation
  changed. The JSON keys are always present; the smoke file's pinned shapes gained them.
* **The constants moved to a leaf module.** `removal_school_views` importing `landscape_report`
  closed a cycle: `status_service` → `landscape_report` → `landscape_staleness` → `caselist_sync` →
  `status_service`. The one definition of each constant now lives in `landscape_bundle_files.py`,
  unchanged. `landscape_report` and `landscape_run` import and re-export them, so t12's import in
  the CLI still works and nothing is copied.
* **Bucket deletion re-lists at execution.** The plan lists what the everyday profile sees. The
  execution lists every version under `reports/landscape/` with the removal profile and deletes what
  the same selection and age rule reach, delete markers included. A view hidden under a marker,
  which the dry run cannot see, still goes (`…a_version_the_dry_run_could_not_see…`, 9 versions).
  The plan's text says so. This follows the manifest sweep's precedent.
* **Unknown files.** A file in a reached caselist's bundle that is neither a school view nor a
  circuit-wide file, or that is not `<caselist>/<snapshot>/<file>`, stops the plan with
  `UNKNOWN_LANDSCAPE_FILE` and its key; nothing is deleted. That includes a `.schools.csv.incoming`
  left by an interrupted `landscape report`. The runbook says to delete that one locally and run the
  dry run again. An unknown file in another caselist's bundle is ignored.
* **The prefix-slug fixture.** No valid slug (`^[a-z]+[0-9]{2}$`) can be a string prefix of another,
  so the fixture uses a `testcl26b` directory to stand in for one. The prefix mutant shows the
  fixture catches it.
* **Counts only in the log and register.** A removal-log line's keys are pinned across installed
  builds, so school-view deletions count into `local_files_deleted` and `s3_versions_deleted`; the
  `DONE` line and `--json` say how many were school views. A test reads every log and scope line
  after a removal and finds no `reports/`, `schools` or school name. The runbook's register line
  asks for counts only.
* **`--out`.** A bundle written with `landscape report --out <dir>` outside the data directory is
  not reached. That directory is the operator's choice, and nothing records it.
* **The purge script was exercised** on synthetic files and a synthetic version listing in the
  scratchpad. It took the in-season school views (bucket versions, a delete marker, local files),
  kept circuit-wide files and an out-of-season bundle, and stopped on a stray `notes.txt` before
  writing anything.
* **Expected Terraform plan, per environment** (not run: the apply is the operator's after the
  merge, and the PM reads the plan first):
  `module.evidence_store.aws_ssoadmin_permission_set_inline_policy.evidence_removal[0]` will be
  updated in place. *Plan: 0 to add, 1 to change, 0 to destroy.* The permission set's description is
  left alone, so it does not become a second change (follow-up below).

### Relay for the PM

```text
v1-e32-t13: questions for the PM (session report, "Decisions and assumptions")

1. Run lock. caselist remove --execute already takes reports/sync/run-lock.json: since v1-e40-t04
   (#480) it runs in run_holding_the_bucket_lock(cli, "caselist remove", ...), the guard retire
   --bucket and landscape report --publish use; ADR-0020 (4) lists it, and
   test_each_bucket_writing_command_takes_the_lock_in_bucket_mode_and_releases_it covers it.
   Cost of taking it in remove --execute: none, it is taken. Local mode takes no lease for any
   command (ruling 3(a)), so only two local-mode commands run at once by the operator could race.
   Options: (A) no change. (B) a local-mode lease too, which is an ADR-0020 change.
   Recommendation: A.

2. ac3's "nothing else new". The removal credential gains exactly one delete (schools.csv and
   schools.md under reports/landscape/), plus a version-listing prefix pair, reports/landscape/ and
   reports/landscape/*, so --execute can find a view's noncurrent versions. Options: (A) accept the
   listing as part of "deleting those keys". (B) narrow the listing to the two file names, which loses
   a view the dry run could not see (one hidden under a delete marker).
   Recommendation: A.

3. Annual purge. No annual-purge runbook exists. The school-view steps are their own section in
   caselist-removal.md. Options: (A) keep them there until a purge runbook task exists. (B) file a
   task for the whole purge runbook and move them into it then.
   Recommendation: A now, and B as a follow-up.

4. Status sees the bucket's current school views only (the everyday profile lists no versions under
   reports/, and you ruled the removal policy is the only one to change). Options: (A) accept, as
   the runbook says. (B) a later task grants the everyday profile ListBucketVersions under
   reports/landscape/. Recommendation: A.
```

## Operator follow-ups

After the merge into `dev`, and only once the PM has read the plan, apply the removal credential's
policy in dev, then prod. Until it is applied in an environment, `caselist remove --execute` there
stops `INCOMPLETE` with `STORE_ACCESS_DENIED` at the school views, after the suppression entries
and the `raw/`/`parsed/` deletes; running the same command again after the apply finishes it. The
blocks follow `docs/runbooks/evidence-store.md` step 3 ("apply from a checkout that has every merged
task", with its `owner.auto.tfvars`).

**Operator command** (expected runtime ~2 min; reads only): the plan, dev. Set `WT` to a checkout
of `dev` after this merges.
```bash
WT=/path/to/a/checkout/of/dev
cd "$WT" || echo "WT does not exist: $WT"
git -C "$WT" pull --ff-only
test -f infrastructure/envs/dev/owner.auto.tfvars && echo "ok: owner.auto.tfvars present" || echo "STOP: no owner.auto.tfvars in this checkout"
export AWS_PROFILE=debate-admin
terraform -chdir=infrastructure/envs/dev init
terraform -chdir=infrastructure/envs/dev plan -out=/tmp/evidence-dev-t13.tfplan
```
Success looks like `module.evidence_store.aws_ssoadmin_permission_set_inline_policy.evidence_removal[0]`
*will be updated in-place*, with the diff adding `reports/landscape/` and `reports/landscape/*` to
`ListEvidenceObjectVersionsForTakedown` and a `DeleteLandscapeSchoolViews` statement, and *Plan: 0 to
add, 1 to change, 0 to destroy*. Anything else, an account assignment above all, means stop and send
the plan to the PM.

**Operator command** (expected runtime ~1 min; applies): only after the PM has read the plan.
```bash
cd "$WT"
export AWS_PROFILE=debate-admin
terraform -chdir=infrastructure/envs/dev apply /tmp/evidence-dev-t13.tfplan
```
Success looks like *Apply complete! Resources: 0 added, 1 changed, 0 destroyed.*

**Operator command** (expected runtime ~1 min; reads only): the grant, simulated.
```bash
export AWS_PROFILE=debate-admin
BUCKET=debate-dev-evidence-a7508de8
REMOVER=$(aws iam list-roles --query 'Roles[?starts_with(RoleName, `AWSReservedSSO_DebateDevEvidenceRemoval`)].Arn' --output text)
aws iam simulate-principal-policy --policy-source-arn "$REMOVER" --action-names s3:DeleteObjectVersion \
  --resource-arns "arn:aws:s3:::$BUCKET/reports/landscape/hspolicy26/2026-10-19/schools.csv" \
  "arn:aws:s3:::$BUCKET/reports/landscape/hspolicy26/2026-10-19/report.md" \
  --query 'EvaluationResults[].{Resource:EvalResourceName,Decision:EvalDecision}' --output table
unset AWS_PROFILE
```
Success looks like `allowed` for `schools.csv` and `implicitDeny` for `report.md`. Then the same
three blocks for prod, with `envs/prod`, `/tmp/evidence-prod-t13.tfplan`, prod's bucket and
`DebateProdEvidenceRemoval`. Fill in the dates in `evidence-store.md`'s "Later applies" row.

## Follow-up work

* **`docs/architecture/evidence-store-layout.md`** (outside this task's packages): its `reports/`
  row says "Kept; regenerable". It should say that the landscape bundles' school views are deleted
  with their sources and by the annual purge. Belongs to E32 or E30's docs.
* **The removal permission set's description** still lists the prefixes it deletes under and omits
  the school views. Changing it would make the plan two changes, so it was left. Fold it into the
  next change to that permission set.
* **An annual-purge runbook** for the rest of the purge (blobs, manifests, parsed store, OpenEv),
  which would take in the school-view section. The PM files it (ruling 3).
* **A noncurrent school view under a newer one** is invisible to status (relay question 4, ruled
  (A)); `--execute` now confirms none is left after it runs.
* **Confirm `raw/` and `parsed/` deletes the same way** (Deviations 3): after deleting, list each
  key's versions again and stop `INCOMPLETE` if any survived. E30, if the PM wants it.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-24

**Notes:**

Thorough, and safe in the direction that matters.
1. **ac1 to ac3 pass, red first.**
   * Selection is one function on t04's constants. An unknown file stops the plan; it is never
     guessed. The caselist segment is matched whole, shown with the `testcl26b` stand-in.
   * The byte-for-byte comparison covers every `(key, version)` under `reports/` and every local
     file.
   * Status residue clears after the same removal runs again.
   * 12 Python and 4 Terraform mutants were caught, including each one named in the PM's context.
2. **The grant matches ruling 2.** I read the diff: one `DeleteLandscapeSchoolViews` statement with
   `s3:DeleteObject` and `s3:DeleteObjectVersion` on `reports/landscape/*/schools.csv` and
   `…/schools.md` only, plus the listing prefix pair. A test ties the Terraform list to
   `SCHOOL_VIEW_FILES`. The expected plan is one in-place update of the removal permission set's
   inline policy: 0 to add, 1 to change, 0 to destroy. The PM reads it before any apply.
3. **Deviation 3 is right, and the error was mine.** Ruling 4 claimed the removal re-lists `raw/` and
   `parsed/` after deleting. It does not; only the preflight probe and status check those. The
   school views now get the confirmation, test-first, and the PM files the same check for `raw/` and
   `parsed/` as an E30 follow-up.
4. **Accepted as made:**
   * re-runs reach an earlier completed run's caselists only for views written before that run
     completed, cut off per run rather than per request. A republished view is never deleted or
     counted. That leaves residue rather than deleting the wrong file, which is the right side to
     err on;
   * `ObjectInfo.last_modified` with `compare=False`;
   * the constants moved to `landscape_bundle_files.py` to break the import cycle, re-exported and
     not copied;
   * execution re-listing under the removal profile, so a view under a delete marker still goes;
   * counts only in the log and register, with the log line's keys unchanged;
   * `--out` bundles not reached;
   * the annual-purge section (Deviation 1, ruling 3), exercised on synthetic data;
   * the permission set's description left alone, so the plan stays one change.
5. **The affected set** stopped at 63% under load. The one failure it found was fixed in code
   (`school_views_older_than` is set only when views are left), and the rest is left to the PR's
   `ci` under agreement 10. The changed directories and the always-run list passed.
6. **The PM files these in a PM batch:** the annual-purge runbook task; re-list confirmation for
   `raw/` and `parsed/` (E30); the `evidence-store-layout.md` `reports/` row; and the permission
   set's description, folded into its next change.

**After the merge:** the operator's three blocks, plan then apply then simulate, in dev and then
prod. The PM reads each plan first. Until the apply, `remove --execute` stops `INCOMPLETE` at the
school views, and running it again afterwards finishes it. No re-review is needed.

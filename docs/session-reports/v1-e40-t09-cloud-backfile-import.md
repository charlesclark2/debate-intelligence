# Session report: v1-e40-t09-cloud-backfile-import

| | |
|---|---|
| Task | `v1-e40-t09-cloud-backfile-import` — The backfile imports run once each in the cloud, not on the operator's machine |
| Spec | [`plan_specs/v1/e40-cloud-caselist-run/t09-cloud-backfile-import.yaml`](../../plan_specs/v1/e40-cloud-caselist-run/t09-cloud-backfile-import.yaml) |
| Epic / release | `v1-e40-cloud-caselist-run` / `v1.8` |
| Branch | `task/v1-e40-t09-cloud-backfile-import` |
| Session status | COMPLETE for a session. The Goal stays `InProgress`: ac2 (the cloud dry run) and ac3 (the four imports) are operator runs after this merges <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

Each backfile import is a task of **the weekly run's own task definition**, started by hand with its
command overridden to `v1-e34-t34`'s `caselist backfile-import --caselist <slug>`, as the PM ruled on
2026-10-27 after the checkpoint. A separate task definition family could not be started from the run
deployer's permission set without changing it. The pieces:

* **`ops/caselist_run/start_backfile_import.py`**, standard library only, run with `python3 -I`. It
  refuses inside the no-import window (its window is t34's own, checked at every quarter hour of
  2026). It also refuses while a run holds the bucket's lock, read with one `GetObject` as
  `debate-<env>-evidence`. It starts only a revision of the run's family that runs as the run role,
  with one container `run` and an image pinned by digest, as `debate-<env>-caselist-run-deployer`.
  It prints the revision, the digest, the task's id and the two commands that watch it. 29 tests
  against a stand-in `aws`.
* **One Terraform change**: the run-stopped alert's email gains one sentence saying the task may be a
  backfile import started by hand. Nothing else changes: no task definition, schedule, role, policy
  or permission set. Five new `terraform test` runs hold the run's storage to the largest import, no
  schedule input, the run role's policies exactly, the alert for an import, and the late-run filter
  that never counts one.
* **`BACKFILEPLAN`** in the runbook, in t06's style: `PLAN OK` only for that one in-place update and
  nothing else. 20 tests run it on synthetic plans. They also check two things a Terraform test cannot
  see: that no third schedule or ECS-target rule exists, and that the storage figure is t34's own
  `space_needed`.
* **The started command, stubbed** (ac1): the script's own container command, run through the CLI
  over moto and the stand-in site, refuses inside the window and without budget before any download.
  Its result is `caselist backfile-import` with no run record.
* **[`docs/runbooks/caselist-cloud-run.md`, "Backfile imports"](../runbooks/caselist-cloud-run.md#backfile-imports)**:
  the plan the PM reads, its check, the apply, both profiles, the network and Terraform's revision,
  the dry run (ac2), the four imports with their counts and the next weekly run's check (ac3). The
  backfiles, removal and alerts runbooks point at it, and docs/data has the empty table.

**What the PM should read first:** the masking check the ruling asked for (Decisions 1). Then the
storage figure's allowances, which are not measured (Decisions 3). Then the draft policy sentence
(Data-use policy 1.18 below).

## Checkpoint: t34's AWS calls against the run role (accepted by the PM, 2026-10-27)

Every call t34's backfile-import steps make, against the run role's policies in `roles.tf` and the
everyday evidence document (`evidence_bucket/operator_access.tf`):

| Step | Call | Covered by |
|---|---|---|
| Seeded? Take, renew, release the lock | `GetObject` and conditional `PutObject` (`If-None-Match`, `If-Match`) on `reports/sync/run-lock.json`, a listing of that key when a read is refused | `s3:GetObject`, `s3:PutObject` on the bucket; `s3:ListBucket` under `reports/` |
| Already imported? | `HeadObject manifests/<slug>/<date>.jsonl` | `s3:GetObject` |
| The backfile ledger | `HeadObject`/`GetObject`, then `PutObject` on `reports/sync/state/caselist-backfile-download-starts.json` | the same, and the evidence key's `GenerateDataKey`/`Decrypt` |
| Restore, the bundle check, publish of sources, manifest, bundle and parsed store | reads and writes under `reports/`, `raw/`, `manifests/`, `parsed/`; prefix listings | the same grants, the weekly run's own calls |
| The token | `secretsmanager:GetSecretValue` on the token, `kms:Decrypt` through Secrets Manager | `caselist-credentials` |
| A failure | `sns:Publish` to the alert topic; the task-stopped rule | `caselist-alerts`; `alerts.tf` |

No delete anywhere. A read of a missing key under this document may answer 403 rather than 404. t34's
Mac dry run, under the same document, read the absent manifest and ledger as absent, so in practice
it works. **No new run-role grant.** What the checkpoint found besides: the deployer's `ecs:RunTask`
is held to `task-definition/debate-<env>-caselist-run:*`, so it can start only the run's family. That
decided Q1.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `cloud-backfile-import` | Done | Its criterion, `scripts/terraform_checks.sh`, passes. The four imports in its description are ac3's, operator runs |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: Terraform tests show the task's ephemeral storage, no schedule, and the run role unchanged; the started command refuses inside the window or without budget, by a stubbed run; tests shown failing first | PASS | **Terraform**: `TF_CLI_CONFIG_FILE=<mirror> TF_DATA_DIR=<scratch> terraform -chdir=infrastructure/modules/caselist_run test` → red before the alert edit `Failure! 41 passed, 1 failed.` (the alert-text assertion, line 2130); green `Success! 42 passed, 0 failed.` The run role is unchanged: no grant added. **Stubbed run**: `pytest packages/debate_cli/tests/bucket_mode/test_backfile_import.py -k "cloud_task or cloud_import"` → 3 passed (inside the window `INSIDE_NO_IMPORT_WINDOW`, budget spent `BACKFILE_BUDGET_SPENT`, nothing fetched; result `caselist backfile-import` with no `run_record`). **Red runs**: script tests against a refuse-nothing skeleton, 13 failed, 16 passed; `BACKFILEPLAN` tests against an always-OK skeleton, 15 failed, 5 passed (below). **Mutants**: 14 of 14 caught |
| ac2: a dry run on Fargate in dev exits 0 after the PM reads the plan and the operator applies it (operator) | NOT RUN | An operator run on dev's AWS account after this merges (after Thursday 2026-10-29's image apply) and after Wednesday 2026-10-28's scheduled run has succeeded: [the runbook's dry run](../runbooks/caselist-cloud-run.md#the-dry-run-v1-e40-t09-ac2) |
| ac3: the four imports, at most one a day, counts in docs/data, the next weekly run restores and finishes in its usual time (operator) | NOT RUN | Operator runs after the operator's return after 2026-11-01: [the four imports](../runbooks/caselist-cloud-run.md#the-four-imports-v1-e40-t09-ac3); the table in [docs/data](../data/caselist-backfile-seasons.md#cloud-imports-v1-e40-t09) is empty until then |
| Node: Terraform checks pass (`bash scripts/terraform_checks.sh`) | PASS | `TF_CLI_CONFIG_FILE=<the main checkout's provider mirror> bash scripts/terraform_checks.sh` → `All Terraform checks passed.`, 30 `ok` lines, 0 `FAIL`, 31 s, offline. The `.terraform` directories it left were removed |

### The red runs

* **Script** (`tests/scripts/test_start_backfile_import.py`), against a copy of the script with
  `window_refusal`, `lock_refusal` and `definition_problems` refusing nothing: **13 failed, 16
  passed**. The 13 are the three window cases, the five lock cases and the five revision cases. The 16
  that pass are the starts, the argument checks, the window agreeing with t34's (a pure function the
  skeleton kept), a lease past its margin, ECS refusing the start, and the run as the runbook runs it.
  The script was restored and `cmp` showed it identical.
* **Terraform**, before `alerts.tf` was edited: 41 passed, 1 failed (above). The storage, schedule,
  role and late-run runs pass on the unchanged module, because the ruling puts the import on the
  run's own definition, which already had them. The mutants show those runs biting.
* **`BACKFILEPLAN`** (`tests/docs/test_backfile_import_plan_check.py`), with the runbook's check
  replaced by `print("PLAN OK: …")`: **15 failed, 5 passed**. All 15 `PLAN STOP` cases fail. The 5
  that pass are the OK plan, the block's shape, the module's text, the schedule scan and the storage
  figure, none of which runs the check's logic. The runbook was restored and `cmp` showed it identical.
* **The stubbed runs** passed at first run: the refusals are t34's, already built. The mutant that
  drops `--execute` from the script's command shows them biting (below).

### Mutants (agreement 8)

Each was applied to a committed file, its tests run, and the file restored with `git checkout`. Every
pytest run had a new, empty `HYPOTHESIS_STORAGE_DIRECTORY` (none of these tests uses Hypothesis).
Every Terraform catch is a failed assertion: each summary is `N passed, M failed` with nothing
skipped.

| Mutant | Caught by |
|---|---|
| **PM 1a**: a schedule added for the import (a third `aws_scheduler_schedule`, with an input) | `test_no_schedule_but_the_logins_and_the_runs_is_declared…` (1 failed, 19 passed). `terraform test` stays green: it cannot list a module's resources. On a real plan, `BACKFILEPLAN` stops it ("a schedule is added or changed") |
| **PM 1b**: the run's schedule given an input aimed at the import | `no_schedule_starts_a_backfile_import` (41 passed, 1 failed); the schedule scan |
| **PM 2**: the run role gains a grant the report does not name (`s3:GetObject` on another bucket, in its credentials policy) | `a_backfile_import_needs_no_grant_the_run_role_lacks` and t02's `the_run_role_reads_the_token_and_never_the_password` (40 passed, 2 failed). t03's action-set run does not see it: the action is already in the set |
| **PM 3**: ephemeral storage 36 GiB | `the_runs_storage_holds_the_largest_backfile_import…` and t03's exact-100 run (40 passed, 2 failed) |
| **PM 4**: the script's window check removed | 3 failed, 26 passed: the three window cases |
| `DescribeSecret` added to the token's read | three runs, mine among them |
| The run-stopped rule narrowed to the schedule's starts (`startedBy` prefix `chronos`) | `a_backfile_import_that_stops_non_zero_emails_the_coach…` and t05's pattern run |
| The alert's backfile sentence dropped | my alert run; `test_the_text_the_check_expects_is_the_modules_own` |
| The late-run filter counting any command | `a_backfile_import_never_counts_as_a_weekly_run` and t05's filter run |
| The script's lock check removed | 5 failed, 24 passed |
| The script starting the family rather than the revision it printed | 2 failed |
| The script accepting another task role | 1 failed |
| The script's command losing `--execute` | 2 script tests; the stubbed budget run (1 failed, 2 passed) |
| `BACKFILEPLAN`'s schedule clause removed | 2 failed (the two schedule cases' reasons) |

## Files changed

* **`ops/caselist_run/start_backfile_import.py`** (new), and **`ops/README.md`**: the script, and its line.
* **`infrastructure/modules/caselist_run/alerts.tf`**: the run-stopped email's one sentence.
  **`tests/caselist_run.tftest.hcl`**: five runs under "A backfile import, started by hand…".
* **`docs/runbooks/caselist-cloud-run.md`**: "Backfile imports", and its docs-index line.
  **`caselist-backfiles.md`**: where an import runs, the first scheduled run's date, the dry run and
  the rebuild pointing at it. **`caselist-removal.md`**: the backfile rebuild is the cloud task.
  **`caselist-run-alerts.md`**: the run-stopped row.
* **`docs/data/caselist-backfile-seasons.md`**: "Cloud imports (v1-e40-t09)", every row not yet run.
* **Tests**: `tests/scripts/test_start_backfile_import.py` (new, 29),
  `tests/docs/test_backfile_import_plan_check.py` (new, 20),
  `packages/debate_cli/tests/bucket_mode/test_backfile_import.py` (3 more).

## Deviations from the spec

1. **The shape is the PM's ruling Q1, not a task definition of its own.** The run's task definition
   with a command override; its 100 GiB already covers the largest import, so there is no storage
   override either. The PM's amendment of 2026-10-27, now on dev, records it, and this branch is
   rebased onto it.
2. **Tests outside `constraints.packages`.** The script's tests are in `tests/scripts/`, beside
   `compare_cloud_run.py`'s. The plan check's are in `tests/docs/`, beside t06's. The stubbed runs
   are in `packages/debate_cli/tests/bucket_mode/test_backfile_import.py`, which has the stand-in
   bucket and site. No code changed in `debate_core.application`.
3. **The script uses two profiles** (ruling Q2): it reads the lock as the everyday evidence profile,
   because the deployer holds no S3 read.
4. **No new smoke check.** No user-facing surface changed: the CLI command is t34's, unchanged, with
   its smoke check, and the script is an operator tool like `compare_cloud_run.py`. Its test
   `test_it_runs_as_the_runbook_runs_it_isolated_with_aws_from_path` runs it as the runbook does.
5. **The first scheduled run's date in `caselist-backfiles.md`** went from Wednesday 2026-11-04 (t34's
   runbook) to Wednesday 2026-10-28, with the imports after the operator's return after 2026-11-01,
   as the PM's context of 2026-10-27 says. The PM may want the earlier date kept.

## Decisions and assumptions

1. **The masking check (required by the ruling): an import cannot count as a weekly run.** By code
   and Terraform:
   * the late-run alarm reads `RunsRecorded`, written only by `aws_cloudwatch_log_metric_filter.runs_recorded`.
     Its pattern needs `$.command = "caselist pull"` and a `run_record.run_id`. An import's envelope says
     `caselist backfile-import` and carries no run record (the stubbed test), so it writes no data
     point. Terraform test `a_backfile_import_never_counts_as_a_weekly_run`; the late-run mutant;
   * run records (the run log, `reports/sync-runs/`, the envelope's `run_record`) are written only by
     `SyncRunMonitor.watch`, which only `caselist pull` calls (`caselist_sync.py`). `backfile_import.py`
     imports nothing from `sync_runs`, and t34's test shows `reports/sync-runs/` unchanged;
   * the run-stopped rule fires once for each task that stops non-zero. A successful import is no
     event, so it cannot cancel a Wednesday run's email. The schedule's dead-letter alarm reads only
     the schedules' queues.

   Nothing would count it, so nothing was built around it.
2. **"Held" is the lock's own rule**: `state: held` with a lease not yet expired by more than the
   5-minute skew margin. A lease long expired is taken over by the task's first locked step, as any
   runner takes it over. A missing or unreadable lock, a lock homed in another environment, or one
   moved away (`kind: moved`) refuses.
3. **The storage figure**: 32,750,091,060 bytes (`space_needed` on hsld25's 4,366,678,808), plus
   allowances of **5 GiB for the image, which is not measured**, and 1 GiB for the restore (the bundle
   measured 9 MB at the cutover). That makes 39.2 GB, about 36.5 GiB, against 100 GiB. The real
   measurement is the dry run's `free_bytes` on the task's volume, which the runbook asks to have
   recorded.
4. **Which revision.** The deployer holds no `scheduler:GetSchedule`, so the script starts the family's
   newest ACTIVE revision by default. The runbook instead passes Terraform's own
   `caselist_run_task_definition_arn` with `--task-definition`: the revision the schedule targets. The
   script prints that revision and its digest, and the runbook compares the digest with
   `owner.auto.tfvars` before the first import.
5. **The alert text** keeps the opening that t05's test and the alerts runbook quote, and adds one
   sentence. `BACKFILEPLAN` requires the new text to be the old with exactly that sentence added.
6. **`startedBy` is `backfile-import`**, so the console and ECS events tell an import from a run. No
   rule reads it.
7. **The token's codes** in the runbook are `CASELIST_AUTH_EXPIRED`, `CASELIST_TOKEN_MISSING` and their
   sibling `CASELIST_TOKEN_UNREADABLE`.
8. **The apply block refuses a Wednesday**, as dev's new image-apply block does.
9. The script takes `--env prod` with `--confirm-prod` (passed on to the CLI), but the runbook covers
   dev only. Backfiles in prod are not in this task.

## Data-use policy 1.18: the sentence for the PM

Policy 1.18 already names a one-off backfile import's working copy in Scope, in "Where personal data
is allowed to live", in the Retention table and in the student pilot's three locations. One place
still names the weekly run's alone: Prohibited uses 10. Proposed, with the added words in bold:

> 10. **Keeping copies outside the sanctioned stores.** The corpus lives in the operator's local
> evidence store and the dev and prod evidence buckets, and, while the weekly cloud run **or a one-off
> backfile import** runs, in its task's ephemeral storage, which is deleted when the task stops
> (ADR-0020**, version 1.18**). Not in email, not in a personal Drive, not on a USB stick, not in a chat
> thread, not in a container image.

The import's task is the run's own definition and role, so its working copy is held exactly as the
weekly run's is.

## Operator follow-ups

**Merge order: this PR merges into `dev` only after Thursday 2026-10-29's image apply**, so that its
Terraform is not part of that plan.

Then, each as
[`docs/runbooks/caselist-cloud-run.md`, "Backfile imports"](../runbooks/caselist-cloud-run.md#backfile-imports)
writes it, with where it runs, its runtime and what success looks like:

1. **The plan** (~2 min, `$WT` at `origin/dev`), its `BACKFILEPLAN` check (~1 min, expect `PLAN OK: 0
   to add, 1 to change, 0 to destroy; …`), **read by the PM**, then the apply (~1 min, not on a
   Wednesday, expect `Apply complete! Resources: 0 added, 1 changed, 0 destroyed.`).
2. **The dry run (ac2)**, after Wednesday 2026-10-28's scheduled run has succeeded and outside the
   window. Both profiles signed in, `hspolicy25`, a few minutes: the result line `"status": "ok"`,
   `"archive_bytes": 3958272657`, `"required_bytes": 29687044928` and a `"free_bytes"` above it, no
   `"code"`. Send the PM the printed revision, digest and free bytes.
3. **The four imports (ac3)**, after the operator's return after 2026-11-01. One a day, never on a
   Wednesday, each about 1.5 to 2.5 h. Then the Thursday check that the next weekly run restored and
   finished in its usual time, before the second import. Each import's counts go to a session for
   docs/data.

The pull request's `ci` runs the affected set (below).

## Verification

| Command | Result |
|---|---|
| `uv run scripts/affected_tests.py` | 86 test files. **The run was stopped by its 115 s alarm at 88%** with no failure in what ran: the machine's load average was 13 to 27 from other work, and `test_ci_workflow_test_job`'s collection subprocesses are in the selection. Its orphaned workers were stopped. Left to the pull request's `ci` under agreement 10 |
| Instead, within two minutes: `pytest -n auto -m "not slow and not live" tests/architecture tests/specs tests/docs packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py tests/scripts/test_check_command_blocks.py tests/scripts/test_docs_index.py tests/scripts/test_start_backfile_import.py packages/debate_cli/tests/bucket_mode/test_backfile_import.py tests/smoke/test_caselist_backfile.py` | after the sync: **627 passed** in 35 s (before it, with `test_compare_cloud_run.py`: 635 passed) |
| `terraform test` (module), `scripts/terraform_checks.sh` | 42 passed; `All Terraform checks passed.` |
| `uv run --frozen ruff check .`; `ruff format --check .` | `All checks passed!`; `1537 files already formatted` |
| `uv run --frozen pyright packages/debate_cli` | `0 errors, 0 warnings, 0 informations` (pyright's `include` is `packages`; `ops/` and `tests/` are outside it) |
| `uv run --frozen lint-imports`; `scripts/check_thin_handlers.py` | `Contracts: 18 kept, 0 broken.`; `OK: 67 … within 25 statements` |
| `scripts/check_command_blocks.py --base origin/dev`; `scripts/check_links.py`; `scripts/docs_index.py --check-descriptions` | `OK: no # comments in 525 shell code blocks in 190 Markdown files (1 session reports changed since origin/dev)`; `OK: 2762 relative links and anchors in 421 Markdown files`; `All 55 indexed documents under docs/ have a description` |
| `scripts/task sync v1-e40-t09-cloud-backfile-import` | rebased onto `9a14b07` (the PM's amendment), no conflict |
| `uv run scripts/validate_specs.py` | `OK: 490 files, 40 epics, 428 tasks, 22 releases`, the Goal left `InProgress` |

## Follow-up work

1. **The in-image token wording** (ruling Q3), for the next image: in the cloud,
   `CASELIST_AUTH_EXPIRED` and `CASELIST_TOKEN_MISSING` should say the Wednesday 03:00 login renews
   the token, not "run `caselist auth login`". It belongs to the next image's task under E40.
2. **`scheduler:GetSchedule` for the deployer** would let the script read the schedule's revision
   itself. That is a permission-set change, so it is the PM's to file if wanted.
3. **A plan check for a new image after the cutover**: dev's batch notes that step 6's check predates
   the enabled schedule (`v1-e31-t31`'s review). Not this task's.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-27

**Notes:**

Built to the checkpoint's rulings with the smallest footprint available: one sentence of Terraform,
an operator script, and a plan check that passes only that one sentence.
1. **ac1 passes.**
   * Terraform: red 41 passed, 1 failed on the alert assertion; green 42 of 42.
   * The run role is unchanged, and the stubbed runs refuse inside the window and without budget
     before any download.
   * Red skeletons for the script (13 failed) and for `BACKFILEPLAN` (15 failed). The passes on each
     skeleton are explained, and they're the cases that don't run the logic.
   * `scripts/terraform_checks.sh` passes offline.
2. **Mutants: 14 of 14, the PM's four among them.** PM 1a (a third schedule) is invisible to
   `terraform test`. The report says so and catches it with the declared-schedule scan and
   `BACKFILEPLAN`. That's the right answer, not a gap.
3. **The masking check is done as ruled, and nothing needed building.**
   * `RunsRecorded` needs `caselist pull` and a run record.
   * Run records come only from `SyncRunMonitor.watch`, which only the pull calls.
   * A successful import is no stop event.
4. **Deviations 1 to 5 accepted.** Deviation 5's date (the first scheduled run on 2026-10-28) is the
   true one.
5. **Decisions accepted:**
   * the lock's own "held" rule;
   * Terraform's revision passed explicitly, with its digest compared before the first import;
   * `startedBy` `backfile-import`;
   * the Wednesday refusal on the apply;
   * prod accepted by the script but not in the runbook.
   * The storage figure (about 36.5 GiB against 100 GiB) rests on an unmeasured 5 GiB image
     allowance. The dry run's `free_bytes` is the measurement, and the PM records it.
6. **One watch item for ac2.** The checkpoint notes that a missing key may answer 403 rather than
   404 under the run role's document. The dry run reads an absent manifest and ledger as the first
   import would. If it refuses with an access denial on a key that doesn't exist yet, stop: that is a
   named grant (a listing), and it comes back to the PM before any import.
7. **Data-use policy 1.18's sentence is accepted** as drafted, for Prohibited uses 10. The PM writes
   it into the policy's next version, with the zero-retention decision.
8. **Follow-ups:**
   * 1 (the in-image token wording) goes to the next image's E40 task;
   * 2 (`scheduler:GetSchedule`) is not filed, since Terraform's revision is enough;
   * 3 is `v1-e40-t15`, already filed.
9. **The affected set** (86 files) was stopped at 88% by the alarm under load, with no failure, and is
   left to the PR's `ci` under agreement 10. The always-run list, the docs and the changed tests
   passed (627), as did the static checks.

**Merge order:** after Thursday 2026-10-29's image apply. Then the plan, `BACKFILEPLAN` and the apply,
the PM reading the plan, then the dry run outside the window. The four imports wait for the
operator's return. The PR merges `--partial`, with the Goal `InProgress`, until ac2 and ac3. No
re-review is needed.

## Operator records (recorded by the PM, 2026-11-01)

Added by the PM. Nothing above is changed, and this section is not a review.

| Criterion | Was | Now | Record |
|---|---|---|---|
| ac2, the dry run on Fargate in dev | NOT RUN | PASS | 2026-11-01, `hspolicy25`, a task of `debate-dev-caselist-run` revision 8 (image `sha256:81656bbf…`, `v1.1.0-dev.164`), started by hand from `caselist-credentials-dev`: stopped `EssentialContainerExited`, exit `0`; the result line `"status": "ok"`, `"applied": false`, `"archive_bytes": 3958272657`, `"already_imported": false`, `"backfile_downloads_left": 1`, `"inside_no_import_window": false`, `"required_bytes": 29687044928`, `"free_bytes": 105463214080`, `"enough": true`. Recorded in `docs/data/caselist-backfile-seasons.md` |

ac2 passes. The Goal stays `InProgress` for ac3, the four imports: `hspolicy25` after Monday 2026-11-02's image apply, then one a day outside the no-import window.

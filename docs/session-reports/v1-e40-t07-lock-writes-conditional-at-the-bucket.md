# Session report: v1-e40-t07-lock-writes-conditional-at-the-bucket

| | |
|---|---|
| Task | `v1-e40-t07-lock-writes-conditional-at-the-bucket` — The evidence bucket itself refuses an unconditional write of the run lock |
| Spec | [`plan_specs/v1/e40-cloud-caselist-run/t07-lock-writes-conditional-at-the-bucket.yaml`](../../plan_specs/v1/e40-cloud-caselist-run/t07-lock-writes-conditional-at-the-bucket.yaml) |
| Epic / release | `v1-e40-cloud-caselist-run` / `v1.8` |
| Branch | `task/v1-e40-t07-lock-writes-conditional-at-the-bucket` |
| Session status | PARTIAL: the code, its tests and the runbook are done; ac2 (the operator's dev apply and the live proof) is open, so the Goal stays `InProgress` |

## Summary

The evidence bucket's policy gains one statement, `DenyUnconditionalWritesOfTheRunLock`. It denies
`s3:PutObject` on `reports/sync/run-lock.json`, and on no other key, to every principal, when the
request carries neither `s3:if-match` nor `s3:if-none-match`. Both environments call the module, so
both get it. Terraform tests pin the statement whole, keep the requirement out of every other
statement and pin the policy's statements by Sid, in dev and in prod. 21 mutants were caught, with no
errors and no skips, and the red run against the start commit failed two runs for their reason.

**The PM should look first at the writer inventory.** Every lock write the cloud run and the Mac's
locked commands make is conditional, traced in code and measured through the existing suites
(273 writes in `test_bucket_mode_lock.py`, every one `If-Match` or `If-None-Match`). I found **one
writer that is not**: `store sync --push` in bucket mode, after a `store sync --pull` has left a copy of
the lock in `objects/`. It sends the stale copy as a blind `PutObject`, which today overwrites its own
live lease and ends `RUN_LOCK_LOST`. It is not on Wednesday's path: the cloud task runs only
`caselist pull` and `caselist auth renew`. As the brief asked, I did not widen the deny for it
([PM question 1](#pm-questions)).

`docs/runbooks/run-lock-conditional-writes.md` holds ac2's operator blocks: a probe before the apply,
the plan with a `PLAN OK`/`PLAN STOP` check, the apply after the PM's word, the probe again, a real
take and release, and the next Wednesday's record. The probe's three requests cannot store anything
whatever the policy says. Nothing was applied from the branch, so ac2 is `NOT RUN` and the Goal stays
`InProgress`.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `lock-bucket-policy` (Conditional lock writes at the bucket) | Code and tests done; its criterion PASS; the operator's apply (ac2) open | The statement and tests in `infrastructure/modules/evidence_bucket`, the runbook, and the inventory of writers below |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: Terraform's tests show a deny of an unconditional `s3:PutObject` on `reports/sync/run-lock.json` and on no other key, with a mutant for each widening caught | PASS | `terraform -chdir=infrastructure/modules/evidence_bucket test` → `Success! 15 passed, 0 failed.`, two runs new: `bucket_policy_refuses_an_unconditional_write_of_the_run_lock_and_nothing_else` and `prod_refuses_an_unconditional_write_of_the_run_lock_too`. **Red run:** the same test file against the start commit's `main.tf` (`git show e1e9b6f:…/main.tf` into a scratch copy of the module) → `Failure! 13 passed, 2 failed.`, both failures `Test assertion failed`, nothing skipped. **Mutants:** 21 of 21 caught, none erroring or skipping ([the table](#mutants)) |
| ac2: the operator applies dev, the PM having read the plan, and an unconditional put of the lock is refused while a conditional one succeeds (operator) | NOT RUN | An operator criterion: an apply against the account, after the PM reads the plan, from a checkout of `origin/dev` once this merges. The blocks are [the runbook](../runbooks/run-lock-conditional-writes.md), listed under [Operator follow-ups](#operator-follow-ups). Their logic was exercised offline only (below) |
| Node criterion: Terraform checks pass (`bash scripts/terraform_checks.sh`) | PASS | `TF_CLI_CONFIG_FILE=<the main checkout's provider mirror> bash scripts/terraform_checks.sh` → `All Terraform checks passed.`, exit 0, in 36 s: fmt, validate of all 13 roots and modules, tflint, and the tests of all 7 modules. Run offline through the main checkout's `.terraform/providers` mirror; no lock file changed (`cmp` against the committed `.terraform.lock.hcl`), and the `.terraform` directories it left were removed |

### Mutants

Each mutant was applied to `main.tf` in a scratch copy of the module, and the whole test file run
against it (`terraform test`, about 2 s each, harness in the session scratchpad). There is no
Hypothesis here, so agreement 8's empty database does not apply. "Lines" are the assertions that
failed:

* 242 is the whole-statement assertion (dev);
* 265 is "no other statement requires a conditional write or names the lock";
* 277 is the policy's Sids and statement count;
* 300 is prod's whole statement;
* 200 and 602 are the existing "no Allow" assertions.

| Mutant | Result | Lines |
|---|---|---|
| Resource the `reports/sync/` prefix | `13 passed, 2 failed` | 242, 300 |
| Resource the whole bucket (`/*`) | `13 passed, 2 failed` | 242, 300 |
| A wildcard after the key | `13 passed, 2 failed` | 242, 300 |
| A different key (`run-lock.jsonl`) | `13 passed, 2 failed` | 242, 300 |
| A second resource, `reports/sync/state/*` | `13 passed, 2 failed` | 242, 300 |
| `NotResource` instead of `Resource` | `13 passed, 2 failed` | 242, 300 |
| No condition | `13 passed, 2 failed` | 242, 300 |
| Only `s3:if-match` tested (would refuse the seed) | `13 passed, 2 failed` | 242, 300 |
| Only `s3:if-none-match` tested (would refuse every renewal) | `13 passed, 2 failed` | 242, 300 |
| The `Null` test inverted | `13 passed, 2 failed` | 242, 300 |
| A condition key added (`s3:ObjectCreationOperation`) | `13 passed, 2 failed` | 242, 300 |
| Action `s3:*` | `13 passed, 2 failed` | 242, 300 |
| `s3:DeleteObject` added to the actions | `13 passed, 2 failed` | 242, 300 |
| The wrong action, `s3:DeleteObject` | `13 passed, 2 failed` | 242, 300 |
| `NotAction` instead of `Action` | `13 passed, 2 failed` | 242, 300 |
| One principal instead of every one | `13 passed, 2 failed` | 242, 300 |
| `Allow` instead of `Deny` | `11 passed, 4 failed` | 200, 242, 300, 602 |
| A second deny on `reports/sync/state/*` | `14 passed, 1 failed` | 265, 277 |
| The requirement moved into another statement (`DenyUploadsUnderAnotherKey` gains `s3:if-match`) | `14 passed, 1 failed` | 265 |
| A second statement under the same Sid, on the whole bucket | `14 passed, 1 failed` | 242, 277 |
| The statement dropped | `13 passed, 2 failed` | 277, 300 |

Each of the three dev assertions catches a mutant the other two let through:

* 242: the prefix mutants;
* 265: the requirement moved into another statement;
* 277: the statement dropped, which 242 passes unread because it finds the statement by Sid.

The first draft also checked Resource, Action and Condition one at a time, and counted the statement.
The first mutation run showed the whole-statement assertion caught everything those four did, so they
could not be told apart from their absence, and I removed them (agreement 8).

## Files changed

* `infrastructure/modules/evidence_bucket/main.tf`: `local.run_lock_key`, and the bucket policy's new
  statement with its reasoning. One statement in one JSON document. Nothing else in the module
  changes, and no input or output is added.
* `infrastructure/modules/evidence_bucket/tests/evidence_bucket.tftest.hcl`: the two runs, and the
  hand-written `run_lock_object_arn`.
* `infrastructure/modules/evidence_bucket/README.md`: the bucket policy's row says what it now denies.
* `docs/runbooks/run-lock-conditional-writes.md` (new): the operator's blocks for ac2, the AWS
  citation, and the record table.
* `docs/runbooks/evidence-store.md`: one "Later applies" row pointing at the new runbook.
* `infrastructure/envs/`: unchanged. Both roots already call the module
  (`envs/*/evidence_store.tf`), so the statement reaches both environments with no root edit.

## The condition keys, from AWS's documentation

Read 2026-10-31:
[Enforce conditional writes on Amazon S3 buckets](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes-enforce.html).

* **The keys** are `s3:if-match` and `s3:if-none-match`, tested with `Null` in AWS's examples.
* **Which operations.** "All `PutObject` and `CompleteMultipartUpload` requests … must include the …
  header". Both are authorised as `s3:PutObject`, so the deny covers both.
* **Multipart.** "you must specify the `s3:ObjectCreationOperation` condition key to exempt the
  `CreateMultipartUpload`, `UploadPart`, and `UploadPartCopy` operations, as these APIs don't accept
  conditional headers." I left that key out on purpose. A multipart upload onto the lock is refused at
  `CreateMultipartUpload`, so none can complete around the deny. Nothing writes the lock in parts:
  `S3LockObject._put` is a single `put_object` (`run_lock_object.py:125`).
* **Copy.** "If you use a bucket policy to enforce conditional writes, you can't perform copy
  operations to the bucket or prefix specified in your bucket policy. `CopyObject` requests without an
  `If-None-Match` or `If-Match` HTTP header fail with a `403 Access Denied` error. `CopyObject`
  requests made with those HTTP headers fail with a `501 Not Implemented` response." So no copy writes
  the lock, conditional or not. Nothing in the repository copies onto it (grep for `copy_object` in
  package sources: none).

[Conditional writes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html)
is the page t04 relied on for `412` and `409`. I fetched the enforcement page myself with a web
fetch, as t02 to t04 did for their AWS pages. [PM question 4](#pm-questions) asks whether a
documentation read should go to the operator like other live calls.

## Every writer of the lock

Every non-test file that names the key or `RUN_LOCK_KEY`:

* `run_lock.py`;
* `ports/run_lock.py`;
* `integrations/s3/run_lock_object.py`;
* `container.py:1562-1601`;
* `settings.py` (help text);
* `ops/caselist_run/start_backfile_import.py`, which reads it with `get-object` (`:133-143`);
* runbooks, which read it with `aws s3 cp … -` and `list-objects-v2`.

None of the runbooks uploads it.

**The one write path.** `BucketRunLock` is the only code that writes the lock, through its
`LockObjectStore`. The only implementation of that store is `S3LockObject`, built only in
`container.py:1574-1601` on a client of its own that the write fence never touches.
`S3LockObject.create` sends `IfNoneMatch: "*"` and `replace` sends `IfMatch: <etag>`
(`run_lock_object.py:108-112`). It has no other write method.

| Writer | Where it writes | Condition |
|---|---|---|
| The seed, `caselist seed-run-state` (first write) | `run_state_seed.py:148` → `BucketRunLock.create` → `run_lock.py:557` `store.create` | `If-None-Match: *` |
| The seed's release | `run_state_seed.py:157` → `release` → `run_lock.py:645` | `If-Match` |
| The cloud run, `caselist pull`: take | `bucket_run.py:126` → `take` → `run_lock.py:527` `store.replace` | `If-Match` |
| Its renewals, every 5 minutes, and before each named write (the fence) | `bucket_run.py:131` `start_renewing` → `_renew_once` → `run_lock.py:697` | `If-Match` |
| Its release | `bucket_run.py:211` → `run_lock.py:645` | `If-Match` (a release is `state: free`, never a delete, rule 5) |
| Every other bucket-writing command (`restore-run-state`, `landscape report --publish`, `caselist publish`, `parse --publish`, `remove`, `unsuppress`, `retire --bucket`, `tub index publish` and `prune`, `files publish`, `store sync --push`, `backfile-import`'s locked steps) | `BucketWriteGuard.held`, `run_lock.py:758-763` → `take`, `start_renewing`, `release` | `If-Match` |

**Measured, not only read.** A scratch pytest plugin wrapped botocore's `_make_api_call`. It counted
every non-read call on the lock's key by condition, and told package-source calls from the tests' own
"another runner" writes by the innermost non-library frame. Runs used `-n 0`, each under a 115 s
process-group kill. The plugin was not committed.

* `test_bucket_mode_lock.py`, 30 passed: 246 `If-Match` and 27 `If-None-Match`, all from
  `run_lock_object.py:_put`, and 0 from source without a condition. 15 unconditional, all from test
  code. This file covers the pull, the seed, and its table of every other bucket-writing command.
* `test_landscape_command.py` and `test_tub_index_prune.py`, `-k "lock or bucket"`, 9 passed: 20
  `If-Match` from source, and 9 unconditional, all from test code.
* `test_backfile_import.py::test_the_lock_is_the_weekly_runs_taken_for_each_step_and_free_during_the_download`,
  1 passed: 23 `If-Match` and 1 `If-None-Match` from source. The whole file did not finish in 115 s
  at load 25 and was killed.

**The one writer that sends no condition: `store sync --push` of a pulled copy.**
`EvidenceSyncService` plans `reports/` like any named-object prefix and has no rule for
`reports/sync/`. It skips only `manifests/_run-state/`, `manifests/_suppression/` and `parsed/`. So
the following happens:

1. `store sync --pull` copies the lock (and the five state files) into `<data_dir>/objects/reports/sync/`.
2. Once any run has moved the lock, a later bucket-mode `store sync --push --apply` plans it
   `changed`.
3. The push uploads the stale copy with `upload_file`, which sends no condition.

A throwaway probe test showed it end to end. It seeded a moto bucket, pulled `reports/sync/`, ran a
week, then pushed `reports/`. The push sent `PutObject` of the lock with no condition, after its own
`If-Match` take. It ended `RUN_LOCK_LOST` and left the bucket's lock as the pulled `state: free` copy.
The probe test was deleted. Where this can happen:

* **Not on Wednesday's path.** The run task's command is `--json caselist pull`
  (`caselist_run/run_task.tf:85`), and the login task's is `caselist auth renew`.
* **Not on the Mac today.** The Mac is in local mode, so a push against the seeded dev bucket is
  refused with `BUCKET_KEEPS_RUN_STATE` before it writes anything.
* **In bucket mode, after the apply,** the stale copy's `PutObject` is refused with `AccessDenied`.
  That error is one of the store errors "true of every object", so the push stops at that object.
  Today it silently overwrites the lock instead.
* The same push also overwrites the five state files under `reports/sync/state/` with the pulled
  copies. Those are not the lock, and this task does not touch them ([Follow-up work](#follow-up-work)).

## Deviations from the spec

* **A writer without a condition exists, and I did not widen the deny for it.** It is
  `store sync --push` in bucket mode, of a copy an earlier pull left (above). The brief said to stop and
  report rather than widen the deny's exceptions. I finished the statement, its tests and the runbook,
  because none of them applies anything. Whether the apply waits for a fix to `store sync` is
  [PM question 1](#pm-questions).
* **No change under `infrastructure/envs/`.** The spec lists it in `packages` and says "in both
  environments". Both roots already call the one module, so the statement reaches both without an edit
  there, and a prod-inputs test run asserts it.
* **The deny does not exempt multipart parts.** AWS's examples add `s3:ObjectCreationOperation` so
  that `CreateMultipartUpload`, `UploadPart` and `UploadPartCopy` pass. Here a multipart upload onto
  the lock is refused outright, which is stricter and still covers `s3:PutObject` alone, on one key.

## Decisions and assumptions

* **Release is a conditional put, not a delete.** `BucketRunLock.release` writes `state: free` with
  `If-Match` (`run_lock.py:619-645`): "The object is never deleted." So the `PutObject`-only deny
  covers every write the lock's holders make. Whether an unconditional delete deserves its own
  statement is [PM question 2](#pm-questions).
* **`Principal: {"AWS": "*"}`**, as the bucket's other three denies have. An explicit deny in a
  bucket policy reaches the break-glass admin and every role alike, which is the point: "a tool or a
  hand command" is usually an admin's.
* **The tests compare the statement whole.** They do not check it field by field, so a field nobody
  reads (`NotResource`, `NotAction`, a narrower principal) cannot change it unseen. The expected
  statement and the lock's ARN are written by hand in the test file, from AWS's condition keys and
  t04's key (agreement 6).
* **The Terraform literal and `RUN_LOCK_KEY` are not tied by a test.** Both say
  `reports/sync/run-lock.json` and each names the other in a comment. A test that read `main.tf` from
  `debate_core`, as `ports/version_directories.py`'s test reads the retirement tag, belongs in
  `packages/debate_core`, outside this task's packages ([Follow-up work](#follow-up-work)). If the code
  moved the key, the deny would protect nothing and refuse nothing: it fails open, never closed.
* **The proof writes nothing at the real key, and shows it can fail.** It uses three requests:
  * an unconditional put with a `Content-MD5` that does not match its body, to a scratch key beside
    the lock: `BadDigest`;
  * the same to the lock: `AccessDenied` after the apply, `BadDigest` before;
  * an `If-Match` naming a tag nothing has: `PreconditionFailed`.

  None can store an object whatever the policy says. The probe assumes S3 authorises a request before
  it checks the digest. If that were wrong, step 4 would report the deny missing; it could never write.
  Run before the apply, request 2 answers `BadDigest`, so the probe is shown failing before it is
  trusted. Every block refuses a Wednesday, `DEBATE_` overrides, a running pull and a held lock. In
  dev it also refuses a lock it cannot read.
* **"A conditional one succeeds" is shown by the code's own path** (runbook step 5): a no-op
  bucket-mode `store sync --push --prefix quarantine/_probe/` takes and releases the lock with
  `If-Match`. It is a real write at the lock's key, as every runner makes, run only while the lock is
  free, with a dry run first. The `quarantine/_probe/` prefix selects nothing from the blob keyspace,
  so it asks for no `--blob-prefix` (`evidence_sync.py:1446-1459`). Step 6, Wednesday's own record, is
  the last proof ([PM question 3](#pm-questions)).
* **What I could check of the runbook offline:**
  * Its plan check, pulled out of the runbook and fed hand-made plan JSON, prints `PLAN OK` for the
    expected shape and for one whose "before" policy AWS normalised (`Principal: "*"`). It prints
    `PLAN STOP` for six bad ones: an account assignment deleted, the deny on the `reports/sync/*`
    prefix, another statement changed, two statements added, nothing changed, and a task definition
    replaced.
  * Every block parses under `zsh -n`.
  * The probe and the take blocks were run under zsh with `aws`, `pgrep`, `date` and `debate-research`
    stubbed. They gave the expected lines before and after the apply, and stopped on a held lock, a
    Wednesday, a `DEBATE_` override and (the take) prod.

## Operator follow-ups

All of these come after this branch merges into `dev`, and none on a Wednesday. The blocks are in
[docs/runbooks/run-lock-conditional-writes.md](../runbooks/run-lock-conditional-writes.md) and are
not repeated here, so there is one copy to keep right.

1. **Before you start** and **Sign in**: a checkout of `origin/dev` with the last applier's
   `owner.auto.tfvars`, and a CLI that knows `--if-match` (a few seconds, then about 1 min).
2. **Step 1, the probe before the apply** (about 1 min). Expect `BadDigest`, `BadDigest`,
   `PreconditionFailed`, and `lock unchanged`.
3. **Step 2, the plan** (about 2 min), then its check (about 1 min). Expect
   `Plan: 0 to add, 1 to change, 0 to destroy.`, `0` `aws_ssoadmin` lines, and `PLAN OK`.
   **Send the plan and the `PLAN` line to the PM and wait.**
4. **Step 3, the apply**, after the PM's word (about 1 min). Expect
   `Apply complete! Resources: 0 added, 1 changed, 0 destroyed.`
5. **Step 4, the probe again** (about 1 min). Expect `BadDigest`,
   `AccessDenied … explicit deny in a resource-based policy`, `PreconditionFailed`, and
   `lock unchanged`.
6. **Step 5, a take and a release**, dry run first (about 1 min each). Expect `exit 0`,
   `transferred 0`, `state free | released after this block started: True`, and
   `the lock was written`.
7. **Step 6, on the Thursday after**: `caselist runs --remote --last 1` shows Wednesday's run
   `succeeded`.
8. Prod after the PM's word on dev, with the pilot's promotion: steps 1 to 4 with `ENVIRONMENT=prod`.

The runbook's record table and `evidence-store.md`'s row are filled in with the dates afterwards.

## Follow-up work

* **`store sync` should never move `reports/sync/`** (the lock and the five state files), either way
  and on either side, as it already never moves `manifests/_run-state/`. A push of pulled copies
  overwrites the run's live state files with stale ones (no deny covers them), and tries to overwrite
  the lock, which this task's deny now refuses. It belongs to `debate_core/application/evidence_sync.py`
  and its tests, for E40 or E41.
* **A test tying `RUN_LOCK_KEY` to the Terraform literal**, in `packages/debate_core`, reading
  `infrastructure/modules/evidence_bucket/main.tf`'s `run_lock_key`.
* `docs/architecture/evidence-store-layout.md`'s row for the lock could say the bucket refuses an
  unconditional write of it. That file is outside this task's packages.

## PM questions

To be pasted to the PM as one block.

```text
v1-e40-t07 (run lock conditional at the bucket): four questions before ac2's apply.

1. A lock writer that sends no condition exists: `store sync --push` in bucket mode, of a copy an
   earlier `store sync --pull` left in objects/reports/sync/run-lock.json. It is off Wednesday's path
   (the task runs only `caselist pull`), and refused on the Mac today (local mode against a seeded
   bucket). Today it overwrites its own lease (RUN_LOCK_LOST) and leaves a stale lock. After the apply
   that one PutObject is AccessDenied and the push stops. I did not widen the deny.
   Options: (a) apply as is, and file a follow-up to make store sync skip reports/sync/ either way;
   (b) hold the apply until that follow-up merges.
   Recommendation: (a). The deny turns a silent clobber of the lock into a refusal, the writer is
   not one the run uses, and holding the deny leaves the lock unguarded against every other blind
   write meanwhile.

2. A delete of the lock is not covered (the deny is PutObject only, as the spec says). Release is a
   conditional PutObject of state "free", never a delete. No everyday or takedown grant can delete
   under reports/sync/; only the break-glass admin can. A deleted lock fails closed: the next take
   refuses with RUN_STATE_NOT_SEEDED before writing anything, and a holder's next renewal gets 404
   and ends RUN_LOCK_LOST.
   Options: (a) no statement; (b) deny s3:DeleteObject on the key to every principal, unless
   s3:if-match is present (S3 supports conditional deletes in general purpose buckets), leaving
   s3:DeleteObjectVersion alone so that an admin can still remove a delete marker to recover.
   Recommendation: (a). The failure is closed and only an admin can cause it. (b) would be a second
   statement with its own tests, its own apply and a new recovery path to document.

3. ac2's "a conditional one succeeds" is shown in runbook step 5 by the code's own take and release
   (a no-op bucket-mode store sync over quarantine/_probe/): a real write at the lock's key, while
   free. Steps 1 and 4 write nothing. Options: (a) keep step 5; (b) drop it, and take step 6
   (Wednesday's run, which takes, renews and releases) as the success proof.
   Recommendation: (a). It shows the success within minutes of the apply, by the run's own code,
   rather than days later.

4. I read AWS's documentation page myself with a web fetch, as t02 to t04 did. The standing rule
   says live calls go to the operator. Should documentation reads go to the operator too?
   Recommendation: no. A documentation read touches nothing of ours, and the spec asks the session to
   read and cite the page.
```

## Checks before the report

Each was run once, after the last code change:

* `bash scripts/terraform_checks.sh` (offline, via the mirror) → `All Terraform checks passed.`, exit 0, 36 s.
* `uv run scripts/validate_specs.py` → `OK: 524 files, 41 epics, 461 tasks, 22 releases`.
* `uv run --frozen ruff format --check .` → `1642 files already formatted`.
* `uv run --frozen ruff check .` → `All checks passed!`
* `uv run --frozen lint-imports` → `Contracts: 19 kept, 0 broken.`
* `pyright`: not run. No Python package changed (the diff is Terraform, a module README and two
  runbooks).
* `uv run scripts/check_command_blocks.py` → `OK: no # comments in 601 shell code blocks in 199
  Markdown files`.
* `uv run --frozen python scripts/docs_index.py --check-descriptions` → `All 60 indexed documents
  under docs/ have a description`.
* `uv run --frozen python scripts/check_links.py` → `OK: 3051 relative links and anchors in 473
  Markdown files`.
* The affected set: see [The affected set](#the-affected-set).

### The affected set

`uv run scripts/affected_tests.py --run` chose `87 of 585 test files (14.9%) … from 7 changed files`
and said `infrastructure/ changed: scripts/terraform_checks.sh is the real check for it.` The
selection's edges are path strings, not code. Tests and scripts that name
`docs/runbooks/evidence-store.md` account for 56 of them, `infrastructure/modules/evidence_bucket/README.md`
for 13, and the spec and this report for the rest. No Python changed.

**It takes more than two minutes**, so the run is left to the pull request's `ci` check
(agreement 10). Under a 115 s process-group kill, at load 3 to 11, it reached about 90% with
2,592 passed and no failure or error printed, then was killed (`exit 124`, no worker left behind).
Within the two minutes I ran the always-run list and the tests that read this task's files by path:

`perl <process-group kill> 115 .venv/bin/python -m pytest -n auto -q -m "not slow and not live" tests/architecture tests/specs tests/infrastructure packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_container_factories.py packages/debate_cli/tests/test_help_rendering.py packages/debate_api/tests/test_exposure.py`
→ `379 passed in 22.26s`, exit 0.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-01

**Notes:**

The bucket now refuses an unconditional write of the run lock and nothing else. The writer inventory
behind it found a real flaw that the deny turns from a silent clobber into a refusal.
1. **ac1 passes.**
   * 15 runs pass; red, 2 failed against the start commit's module.
   * 21 mutants were caught, with no errors and no skips. Each of the three dev assertions catches a
     mutant the others let through.
   * Dropping the four field-by-field assertions that the whole-statement check made redundant is
     agreement 8 applied properly.
   * `terraform_checks.sh` passes offline, with no lock file changed.
2. **The writer inventory is the most valuable part.** Every writer was traced in code with file and
   line, then measured through botocore: 273 lock writes in the lock suite, every one conditional,
   and the same in the landscape, prune and backfile paths. The one blind writer, `store sync --push`
   of a pulled copy, was shown end to end in a throwaway probe and correctly left out of the deny.
3. **The PM's answers:**
   * **Question 1: (a).** Apply as is. One follow-up, p2 in the next PM batch: `store sync` never moves
     `reports/sync/` either way. It also takes the test tying `RUN_LOCK_KEY` to the Terraform literal.
     The stale state files that the same push overwrites are the bigger risk, and that task fixes
     both.
   * **Question 2: (a).** No delete statement. A deleted lock fails closed, and only the break-glass
     admin can delete it.
   * **Question 3: (a).** Keep step 5. It shows a conditional write succeeding by the run's own code,
     within minutes of the apply.
   * **Question 4:** no. Reading a public documentation page touches nothing of ours, and the spec
     asks for a citation. The operator rule covers calls to our accounts and services.
4. **Deviations accepted:** the blind writer reported, not exempted; no edit under `infrastructure/envs/`,
   since both roots call the module; multipart refused outright.
5. **Decisions accepted:**
   * release as a conditional put;
   * every principal;
   * the statement compared whole;
   * a proof that cannot write at the real key and is shown failing before the apply;
   * the plan check exercised offline against hand-made plans.
6. **When to apply (ac2), as the PM rules it.** After this merges, on Monday 2026-11-02 or Tuesday
   2026-11-03, never within the hour before Wednesday's 06:00 run. Wednesday 2026-11-04's run, on the
   unchanged image dev.164, is then step 6's proof of the deny alone. The parse-owed image
   (v1-e40-t08) follows on Thursday, with its own plan and apply, so each plan shows one change and
   the next week's run tests one new thing.
7. **Closing checks:** the affected set (87 files, path edges only, no Python changed) is left to the
   PR's `ci` under agreement 10. The always-run list and the infrastructure tests pass.
8. **Merge `--partial`.** ac2 is the operator's, so the Goal stays `InProgress`.

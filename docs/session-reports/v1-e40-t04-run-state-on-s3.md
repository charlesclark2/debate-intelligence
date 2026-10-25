# Session report: v1-e40-t04-run-state-on-s3

| | |
|---|---|
| Task | `v1-e40-t04-run-state-on-s3` — A cloud run keeps its state in the evidence bucket |
| Spec | [`plan_specs/v1/e40-cloud-caselist-run/t04-run-state-on-s3.yaml`](../../plan_specs/v1/e40-cloud-caselist-run/t04-run-state-on-s3.yaml) |
| Epic / release | `v1-e40-cloud-caselist-run` / `v1.8` |
| Branch | `task/v1-e40-t04-run-state-on-s3` |
| Session status | COMPLETE, for the PM's review. The Goal stays `InProgress`: the Terraform change merges `--partial`, as the PM ruled <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

Bucket mode is built, as the plan the PM accepted on 2026-10-24 describes it. With
`caselist.run_state = "bucket"`, a run restores a working copy from the evidence bucket, saves its
state back, and holds the bucket's run lock while it writes. Only the cloud run sets bucket mode
until `v1-e40-t06`. The pieces:

* **The lock** is `reports/sync/run-lock.json`, changed only by S3 conditional writes, with a
  30-minute lease renewed every 5 minutes. Every write of a named object waits for a renewal that
  started after it asked, and writers waiting together share one.
* **The fence** is one hook on every S3 client a bucket-mode command builds. It asks the lease before
  each write, so a command that forgot the lock is refused rather than writing unfenced.
* **Every bucket-writing command takes the lock**, the two the PM added (`caselist retire
  --bucket`, `landscape report --publish`) included. A test classifies every registered command,
  so a new one cannot slip past.
* **Local mode** refuses a bucket that holds a lock object (ruling 3(a)), and with no lock object
  nothing changes.
* **The restore** is one-way and checked against the publisher's SHA-256. It refuses a bundle
  holding a manifest the publisher withholds, using the publisher's own rule. It fetches raw sources
  only as the parse needs them, and restores no gzip of the index.
* **The save** writes each state file as it is written: the download ledger before each download,
  and a removed file as an empty object. It saves the bundle only when every manifest is confirmed
  and none is withheld.
* **SIGTERM** records `RUN_TERMINATED`, saves what ADR-0020 (3) allows and releases the lock.
* **`caselist seed-run-state`** is built and tested, and never run here.
* **A removal** in bucket mode plans on a restored copy under the lock, rewrites the bundle, and
  purges its old versions with the takedown credential only after the rewrite is confirmed.
* **`store sync`** skips `manifests/_run-state/`.
* **Terraform:** the run task gains `DEBATE_CASELIST__RUN_STATE=bucket`, and a new test run,
  `the_run_role_never_deletes`, checks the role's policies.

All four acceptance criteria pass by test, and ac4's two halves were shown red first. 21 mutants
were all caught; the one that first survived was the reason for a new test.

Three things the PM should read first:

1. **The bundle's database copy is `VACUUM INTO`, not an online backup** (a change from the plan). I
   checked on this Mac that SQLite keeps a deleted row in the file's free pages, and an online
   backup copies them. So a removal's rewritten bundle would still have held the removed rows.
   `VACUUM INTO` writes a compacted copy without them, and ac4's test checks the removed file's
   digest is in no byte of the remaining bundle version.
2. **A run killed after its publish stage leaves that week's parse late**, never lost, exactly as a
   Mac run does. The bundle saved after the publish records the week as imported. The next run finds
   nothing new, and the parse stage parses only what its own run imported. The week is parsed by
   the next pull that imports into the caselist, or by `caselist parse --publish` by hand. ac2's
   tests show both halves. A "parse owed" marker would close it; it is listed as follow-up work.
3. **Phase.** All four criteria pass, but the PM ruled that a Terraform change merges `--partial`,
   with the plan read and the apply after the seed. So the phase stays `InProgress`, and the PM
   decides when it becomes `Succeeded`.

As the PM asked me to say: a `RUN_LOCK_LOST` run reads stale under `v1-e34-t32`'s rule until the
record of the run that took over lands. A `SIGTERM`'d run's failed record (`RunTerminated`) also
reads stale until a later run's record lands. Both are as they should be.

## PM rulings on the plan (2026-10-24), and where each is

| Ruling | Where |
|---|---|
| 1. Packages gain `infrastructure/modules/caselist_run`; the one environment line and its assertion; `--partial` | Spec comment and `packages` (896bd82); `run_task.tf` and the run task test's environment map (f8fb163) |
| 2. `caselist retire --bucket` and `landscape report --publish` take the lock | `caselist_retire._execute`, `landscape.report` (091fb2d); tests in `bucket_mode/test_bucket_mode_lock.py` and `test_landscape_command.py` |
| 3(a). Local mode refuses a seeded bucket | `BucketWriteGuard.refuse_a_seeded_bucket`; `BucketKeepsRunState` keeps a pull's record local |
| 3(b). The seed is t06's cutover step; t03's step 8 follows | `docs/runbooks/caselist-cloud-run.md` step 8: the agent check, the seed's dry run, the seed, the bucket-mode apply, then the run by hand |
| 4. `caselist seed-run-state` as named | `commands/caselist_seed.py`, `run_state_seed.py` |
| 5. Shared renewals, and a test that a write arriving during an in-flight renewal waits for the next | `BucketRunLock.renew`; `test_a_write_that_arrives_during_an_in_flight_renewal_waits_for_the_next_one` |
| 6. No gzip restore; a manifest-only directory never published from; a changed digest rebuilds; both tested | `search_index_refresh.RESTORED_INDEX_MARKER`; three tests in `test_search_index_stage.py`, two in `bucket_mode/test_bucket_mode_restore.py` |
| 7. No restore timing now | The first bucket-mode run's details carry `bucket_run.restore`; step 8's last block reads it |
| The bucket-policy deny is the evidence bucket module's, filed by the PM | Not built (filed on dev as `v1-e40-t07`) |
| Mutants as listed, plus the local-mode refusal | [Mutants](#mutants) |

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `state` — Run state on S3 | Done | Built in the plan's order: setting, lock, fence, commands, restore, save, SIGTERM, seed, removal, store sync and layout, Terraform, runbooks, mutants, checks |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 — a run on an empty data directory restores from a stubbed bucket and produces the same parse and index as a run on a full one | PASS | `pytest packages/debate_cli/tests/bucket_mode/test_bucket_mode_restore.py` → `7 passed`. Two copies of one seeded moto bucket: week 3 pulled on the Mac's full directory against one, on an empty directory against the other. Equal `parse` counts, equal parsed-store file digests, byte-equal published index manifests, equal evidence key by key. A second test does it where the bucket holds no parsed store (a full parse from `raw/`, 7 sources). Also tested: a changed parsed file stops the restore (`BLOB_INTEGRITY_ERROR`); a withheld manifest is never restored, in the publisher's words; an unchanged store is not rebuilt and its restored index holds the manifest alone; `tub index publish --newest` refuses a restored directory; the saved state files and bundle are the run's own |
| ac2 — a run killed at each stage leaves the bucket readable by the next run | PASS | `pytest packages/debate_cli/tests/bucket_mode/test_bucket_mode_kills.py` → `21 passed`. A hard kill at the start of each of 8 stages, after the 1st, 2nd, 4th, 8th, 12th, 16th and 20th bucket write, and at the very end; a real SIGTERM at 5 stages. After each, a fresh run on an empty directory (36 minutes later after a hard kill) takes over and finishes. The bucket then equals what an uninterrupted run leaves on a copy, key by key and ETag by ETag, but for the late parse in finding 2, which the by-hand catch-up closes in the same test. A SIGTERM'd run records `failed`/`RunTerminated` locally and in the bucket, saves its state files and releases the lock |
| ac3 — a second runner refused while live; an expired lease taken over and said; a runner whose lease was taken writes nothing more and ends `RUN_LOCK_LOST`; every bucket-writing command takes the lock | PASS | `pytest packages/debate_core/tests/application/test_caselist_sync_run_lock.py` → `18 passed` (moto, conditional writes): refusal, takeover and its message, the skew margin, wrong home, an unreadable lock, the first-writer race, lost lease, release without delete, shared renewals, the 403 listing rule, the fence on a real client. `pytest packages/debate_cli/tests/bucket_mode/test_bucket_mode_lock.py` → `26 passed`: the same at the command, with the bucket unchanged byte for byte for a refused runner; `RUN_LOCK_LOST` with nothing written after the takeover, and with nothing left to write; no lock object never started on; each of 8 commands takes and releases the lock and is refused under another's lease; every registered command classified; local mode's refusal and its no-lock case. `test_landscape_command.py` → `19 passed`, its 2 new tests for `landscape report --publish` |
| ac4 — a removal leaves no noncurrent version of the bundle holding the removed rows and purges only after its rewrite is confirmed; the run role's policy has no `s3:DeleteObject`/`s3:DeleteObjectVersion`; both shown failing first | PASS | Removal: `pytest packages/debate_cli/tests/bucket_mode/test_bucket_mode_removal.py` → `4 passed`, after its red run (below). Terraform: `terraform test` in `infrastructure/modules/caselist_run` → `Success! 27 passed, 0 failed.`, `run "the_run_role_never_deletes"... pass`, after its red run against four mutated policies (below) |
| Node `state`: `uv run pytest packages/debate_core/tests/application -k caselist_sync` | PASS | `219 passed in 8.54s` |

### The red runs (ac4)

**The removal half**, against the removal before its bundle step: the tests at 865db31 (b4a2511
before the sync onto `dev` at `cd56754`), on the code of the commit before it.
`perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest -q -p no:randomly -n 0 packages/debate_cli/tests/bucket_mode/test_bucket_mode_removal.py`:

```text
FAILED test_bucket_mode_removal.py::test_a_removal_leaves_one_version_of_the_bundle_and_it_does_not_hold_the_removed_file
  AssertionError: every noncurrent version purged, and no delete marker left; assert 3 == 1
FAILED test_bucket_mode_removal.py::test_the_purge_comes_after_the_rewrite_is_written
  assert [] == ['put']
FAILED test_bucket_mode_removal.py::test_a_rewrite_the_bucket_does_not_confirm_purges_nothing_and_the_removal_is_incomplete
  assert 0 != <ExitCode.OK: 0>
3 failed, 1 passed in 18.87s
```

The one that passed is the premise, that every version of the bundle names the file before the
removal. After 5f9b171, `4 passed`.

**The Terraform half**, against `roles.tf` mutated four ways. Each time, one statement was added to
the run role's credentials policy, which `evidence_policy_json`'s plan-time validation does not
read, and the file was restored from git afterwards:

```text
MUTANT s3:DeleteObjectVersion by name: Failure! 24 passed, 3 failed.  run "the_run_role_never_deletes"... fail
MUTANT s3:Delete* by wildcard:         Failure! 24 passed, 3 failed.  run "the_run_role_never_deletes"... fail
MUTANT s3:*Object* by wildcard:        Failure! 24 passed, 3 failed.  run "the_run_role_never_deletes"... fail
MUTANT an Allow with NotAction:        Failure! 5 passed, 2 failed, 20 skipped.  run "the_run_role_never_deletes"... fail
```

Each failure is the new run's own assertion message, not an error. Under the NotAction mutant
another run errors and skips the rest of the file, which is why the new run is the file's first
(d6b43d5). Without the environment line, the run task's test fails (`Failure! 26 passed, 1
failed.`, `the_run_task_runs_the_pinned_image_as_the_run_role_under_its_deadline`), and with it, it
passes.

### Mutants

By hand, under working agreement 10, each against the test files that cover it, with the source
restored after each. 21 mutants, all caught. "Caught" means a named test failed on an assertion.
The first batch printed `ERRORED` only because `-x` under xdist exits with code 2; each of its lines
names a failing test.

| Mutant | Caught by |
|---|---|
| Lease 30 → 60 minutes | `test_a_renewal_moves_the_lease_on_and_release_frees_it_without_deleting` and 3 more |
| Renewal every 5 → 15 minutes | `test_the_lease_is_thirty_minutes_renewed_every_five_with_five_minutes_for_clock_skew` |
| Skew margin ignored | `test_a_second_runner_is_refused_while_the_lease_is_live_and_writes_nothing` |
| Skew comparison `>=` | the same |
| Shared renewal: an in-flight renewal counts | `test_a_write_that_arrives_during_an_in_flight_renewal_waits_for_the_next_one` and 6 more |
| A content-addressed write renews | `test_a_content_addressed_write_needs_a_held_lease_and_no_renewal` |
| A named write skips its renewal | `test_a_renewal_the_store_did_not_answer_lets_no_write_through_and_keeps_the_lease` and 4 more |
| The takeover's `If-Match` matches any version | `test_a_runner_whose_lease_was_taken_over_...` and 6 more |
| `took_over_from` not written | `test_an_expired_lease_is_taken_over_and_the_new_holder_says_so` |
| A 412 on renewal does not mark the lease lost | `test_a_runner_whose_lease_was_taken_over_loses_it_at_its_next_renewal_and_writes_nothing_more` |
| The fence lets a lost lease write | the same |
| `RUN_LOCK_LOST`: the run's end never asks the lease | First **survived**: the fence refused the bundle's write, so the run still ended `RUN_LOCK_LOST`. That masks a run whose bundle save writes nothing. The new `test_a_run_whose_lease_is_taken_ends_run_lock_lost_even_with_nothing_left_to_write` (071e4b5) catches it |
| No lock object: the run creates one itself | `test_a_bucket_with_no_lock_object_is_never_started_on` (run alone too) |
| A refused read of the lock is taken for absence | `test_a_read_refused_for_a_missing_key_is_absence_and_for_a_present_one_is_a_refusal` |
| Local mode: a seeded bucket is not refused | `test_in_local_mode_a_bucket_writing_command_refuses_a_bucket_that_holds_a_lock_object` |
| The bundle saved with a manifest unconfirmed | `test_the_bundle_is_not_saved_while_a_manifest_is_unconfirmed_in_the_bucket` |
| The withheld check skipped on save | `test_a_bundle_holding_a_manifest_the_publisher_withholds_is_not_saved_in_the_publishers_words` |
| The withheld check skipped on restore | `test_a_bundle_holding_a_manifest_the_publisher_withholds_is_never_restored` |
| The confirm compares the version and not the digest | `test_a_bundle_the_bucket_holds_with_another_digest_than_was_written_is_not_confirmed` |
| The purge despite an unconfirmed rewrite | `test_a_rewrite_the_bucket_does_not_confirm_purges_nothing_and_the_removal_is_incomplete` |
| The purge before the rewrite | the same, and `test_the_purge_comes_after_the_rewrite_is_written` |

Two tests were added before the run, because no test could catch their mutants: the lease's
numbers (every test overrides the interval), and the confirm's digest (37cf831).

### What was run, and what was left to CI

`uv run scripts/affected_tests.py` chose **371 of 460 test files (80.7%)** from 52 changed files.
The reasons are new modules in `debate_core.application.ports`, which the root conftest imports,
and `settings.py`. That is the whole selection in all but name, well past two minutes. So under
working agreement 10 (the PM's ruling of 2026-10-19) it is left to the pull request's `ci` check
and not handed to the operator. Within the two minutes I ran the test files of what changed and the
always-run list, once before and once after the sync onto `dev` at `cd56754`. After the sync:

| Run | Result |
|---|---|
| Core: `test_caselist_sync*`, `test_sync_runs`, `test_search_index_stage`, `test_store_sync_skips_parsed`, `test_settings*`, `test_port_conformance`, `test_landscape_staleness`, `integrations/s3`, `integrations/local`, `tests/architecture`, `tests/specs`, `tests/docs`, the docs-check scripts' tests, `test_app.py`, `test_help_rendering.py` | `1249 passed in 27.53s` |
| Core: the removal, pending-work, sync, inbox-retention and parsed-removal tests under `caselist/`, `test_evidence_sync*`, `test_caselist_parse*`, `caselist/test_pull*` (43 files) | `800 passed in 76.37s`. A first try passed two files twice, through overlapping globs, and three tests of one file then could not find their conftest's fixtures. With each path once, all pass, and that file passes alone, serially and in parallel |
| CLI: `bucket_mode/`, `commands/test_caselist_pull*`, `test_store`, `test_doctor`, `test_caselist_runs`, `test_pull_refused_before_the_bucket_is_built`, `test_installation`, `test_app`, `test_config_command` | `340 passed in 63.80s` |
| CLI: `commands/test_caselist_remove*`, `test_caselist_publish`, `test_caselist_parse*`, `test_caselist_retire`, `test_tub_index`, `test_landscape_command`, `test_recorded_failure_codes`, `test_retryable_store_failures`, `test_missing_profile_and_missing_grant`, `test_help_rendering`, `test_output` | `323 passed in 51.78s` |
| `terraform test` in `infrastructure/modules/caselist_run` (offline, through the main checkout's provider mirror) | `Success! 27 passed, 0 failed.` |
| `TF_CLI_CONFIG_FILE=<mirror> bash scripts/terraform_checks.sh` (before the sync) | `All Terraform checks passed.` in 29 s; the `.terraform` directories it left were removed, and no lock file changed |
| `uv run --frozen ruff format --check .` / `ruff check .` | `1273 files already formatted` / `All checks passed!` |
| `uv run --frozen pyright` (the workspace, as CI runs it) | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen lint-imports` / `scripts/check_thin_handlers.py` | `Contracts: 16 kept, 0 broken.` / `OK: 51 CLI command and API route handlers within 25 statements` |
| `scripts/validate_specs.py` / `docs_index.py --check-descriptions` / `check_command_blocks.py --base origin/dev` / `check_links.py` / `pre-commit run check-merge-conflict` | `OK: 439 files ...` / `All 47 indexed documents ... have a description` / `OK: no # comments in 424 shell code blocks ...` / `OK: 2301 relative links ...` / `Passed` |

**CI time.** The new end-to-end tests under `packages/debate_cli/tests/bucket_mode/` add about 380
test-seconds, measured at load 10 on this Mac, so likely about half that idle. ac2's 21 kill runs
make up most of it, at three pulls each. CI deals them across its parts. If one part's pytest step
passes two minutes, agreement 1's fix is another part.

## Files changed

* **`debate_core.application`**:
  * `settings.py`: `caselist.run_state`.
  * `ports/run_lock.py`: `LockObjectStore`, `LockObjectChanged`, `WriteFence`.
  * `ports/run_state.py`: `RunStateFiles` and the bundle's keys.
  * `caselist/run_lock.py`: the lease, its errors, `RunTerminated`, `BucketWriteGuard`.
  * `caselist/run_state.py`: the restore and the saves.
  * `caselist/bucket_run.py`: one pull's lock, restore, saves and stop.
  * `caselist/run_state_seed.py`: the seed.
  * `caselist/removal_service.py`: the bundle's rewrite and purge, `on_the_working_copy`.
  * `caselist_sync.py`: state-file hooks, the ledger before a download in bucket mode, the save
    after the publish, `PullBracket`.
  * `caselist_parse.py`: `fetch_missing`.
  * `sync_runs.py`: `BucketRunDetails`, local-only records, three notifications.
  * `search_index_refresh.py`: the restored-index rules.
  * `evidence_sync.py`: skips `manifests/_run-state/`.
* **`debate_core.integrations`**:
  * `s3/run_lock_object.py`: the lock by conditional writes.
  * `s3/fencing.py`: the fence.
  * `local/run_state_files.py`: the bundle's files, `VACUUM INTO`.
* **`debate_cli`**:
  * `bucket_lock.py`: the lock around a command; SIGTERM.
  * `commands/caselist_seed.py` and its registration.
  * The lock at each command's write: `caselist`, `caselist_parse`, `caselist_remove`,
    `caselist_retire`, `landscape`, `tub_index` and `store`.
  * `caselist_pull`: SIGTERM and the bracket.
  * `container.py`: the lock, the guard, the fence, the run state, the seed and the bucket run.
* **Tests**:
  * `debate_core/tests/application/test_caselist_sync_run_lock.py` and
    `test_caselist_sync_run_state.py`.
  * Three runs in `test_search_index_stage.py`.
  * The details' pinned keys in two `caselist/` tests.
  * `debate_cli/tests/bucket_mode/`: a conftest and four test modules.
  * Two tests in `test_landscape_command.py`.
  * The pinned integration and service lists in `test_doctor.py`, `test_installation.py` and
    `test_app.py`; the details in `test_pull_refused_before_the_bucket_is_built.py`.
* **`infrastructure/modules/caselist_run`**: `run_task.tf`, the bucket-mode line; `README.md`;
  `tests/caselist_run.tftest.hcl`, `the_run_role_never_deletes` and the environment assertion.
* **Docs**:
  * `docs/architecture/evidence-store-layout.md`: the three prefixes.
  * `docs/runbooks/caselist-cloud-run.md`: step 8's seed, bucket mode and checks.
  * `docs/runbooks/caselist-removal.md`: bucket mode.
* **Spec**: `constraints.packages` amended under its PM-ruling comment (ruling 1).

## Deviations from the spec

1. **`constraints.packages` gains `infrastructure/modules/caselist_run`** for the one environment
   line and its assertion: the PM's ruling 1, amended in the spec under its comment.
2. **Two more bucket-writing commands take the lock** than ADR-0020 (4) listed: ruling 2. The ADR
   now lists them (dev's PM batch 2026-10-24k).
3. **The download ledger in bucket mode is recorded and saved before each download starts.**
   ADR-0020 (3) says "before each download starts, as the local file is today", but the local file
   is written after a download finishes. In local mode nothing changes. In bucket mode a failed
   download now counts against the five a day: conservative, and never an extra download.
4. **The bundle's database copy is `VACUUM INTO`, where the plan said an online backup**: finding 1.

## Decisions and assumptions

* **Which commands restore.**
  * `caselist pull` restores everything: the bundle, the state files, the index manifest and the
    parsed store.
  * A dry run restores the bundle and the state files to this machine, and takes no lock.
  * `--publish-pending` restores no parsed store.
  * `caselist remove` restores the bundle and the state files, under the lock when it executes,
    before the removal service opens the database: building the service opens it, and the restore
    replaces the file whole.
  * The other bucket-writing commands take the lock and work on this machine's data directory as
    it is.
  * `v1-e40-t06`'s comparison and a hand publish to prod may want a `caselist restore-run-state`
    command. The service exists; adding the command is follow-up work.
* **The run record's schema is frozen**, so `RUN_LOCK_LOST`, `RUN_TERMINATED`, `RUN_STATE_NOT_SEEDED`
  and the rest are error classes and codes, and the takeover, the restore's counts and times, and
  the bundle's outcome go in the details' new `bucket_run`. Builds before it pass over `bucket_run`
  (`extra="ignore"`).
* **Records that stay on this machine:** a run another runner's lease refused, a lost lease, no
  lock object, a wrong home, an unreadable lock, a missing bundle, and local mode's refusal. None of
  those runs held the lock, so none writes to the bucket, and none is owed to it later.
* **The holder** is `cloud` when ECS's `ECS_CONTAINER_METADATA_URI_V4` is set, `mac` otherwise. The
  task is that address's last segment, which names the container, since reading the task's ARN
  would mean a request to the metadata endpoint.
* **SIGTERM outside `caselist pull`** raises `RunTerminated` in the main thread, so the lock is
  released. The pull's own SIGTERM is installed only in bucket mode, so the Mac's agent behaves as
  before. A thread already uploading when the stop arrives may finish its one request. A process-pool
  parse may not stop at once, and ECS's SIGKILL at 120 seconds is then the end (follow-up).
* **The seed requires bucket mode**, and refuses an unconfirmed or withheld manifest. Its dry run
  reads only a listing of the lock's key and a `HeadObject` per manifest.
* **No IAM grant changed**, as the plan's table shows. `the_run_role_never_deletes` covers the
  role's policies by IAM's own wildcard matching, `NotAction` included.

## Operator follow-ups

None to run now. After the merge, step 8 of `docs/runbooks/caselist-cloud-run.md`, at the cutover
(`v1-e40-t06`), in this order and coordinated by the PM block by block:

1. Check that the Mac's agent is unloaded (one read-only block). Unloading it is `v1-e40-t06`'s
   step 3.
2. The seed's dry run, then, on its own, `caselist seed-run-state --execute`. Working agreement 11:
   two blocks, each guarded against `DEBATE_` overrides and a running pull, each with a count that
   must be above zero.
3. A new image from a release with t04, then the plan of the run task in bucket mode, for the PM to
   read. Expect `Plan: 2 to add, 4 to change, 2 to destroy.`, both task definitions replaced and
   both schedules repointed, `DEBATE_CASELIST__RUN_STATE` in the run's new revision, and its
   schedule still `DISABLED`. Then the apply.
4. One run by hand (t03's ac2), and the block that reads its `bucket_run` details: the bundle saved,
   no takeover, the restore's counts and times, and the lock `free` after it.

## Follow-up work

* **The parse of a week a killed run published** (finding 2). A small "parse owed" record would let
  the next run parse that week instead of waiting for the next import into the caselist. Today it
  is late exactly as on the Mac. For the PM: `v1-e40-t06`, or an E34 task.
* **`caselist restore-run-state`**, for `v1-e40-t06`'s comparison and a hand publish to prod from a
  restored copy (ADR-0020 (4) and (7)). The service, `RunState.restore`, is built.
* **SIGTERM during a process-pool parse.** The cancellation reaches the run, but whether the pool's
  workers stop inside 120 seconds is not tested, because the tests use the in-process runner. ECS's
  SIGKILL then ends it, as a hard kill, and the next run takes over. This is for the first cloud
  run's logs to show, or for an E31 task.
* **The bucket-policy deny on unconditional lock writes** is filed by the PM as `v1-e40-t07`.

## The plan, as the PM accepted it (2026-10-24)

Kept as it was sent, for the record. What changed in the building is under [Deviations from the spec](#deviations-from-the-spec) and [Decisions and assumptions](#decisions-and-assumptions).

### What is added or changed

Everything below is in `debate_core.application`, `debate_core.integrations` and `debate_cli`. New
logic goes into new modules, not into `caselist_sync.py`, which is a hub module and would widen the
affected test set. Only thin wiring touches it.

**1. Bucket mode: a setting.** `caselist.run_state`, `"local"` (the default) or `"bucket"`, in
`CaselistSettings`. `config show` and `doctor` show it. Nothing in the bundled profiles changes;
until `v1-e40-t06` only the cloud task's environment sets it.

**2. The lock and its lease** (`application/caselist/run_lock.py`, with a port for a conditional
object and an S3 adapter in `integrations/s3/`). This is ADR-0020 (4) exactly:

* The lock is `reports/sync/run-lock.json`, with the ADR's body. `holder.kind` is `cloud` in ECS and
  `mac` otherwise. `moved` is reserved for t06.
* **Never start without a lock object.** Existence is answered by listing the prefix
  `reports/sync/run-lock.json`, which the everyday grant allows. A `GetObject` of a missing key
  under a prefix-conditioned `ListBucket` answers 403, not 404, as the removal found on 2026-10-01.
  So "absent" and "cannot read" are told apart, and both refuse: `RUN_STATE_NOT_SEEDED`, or the
  existing expired-session failure. Nothing is restored and nothing is written.
* **Taking it:** read the body and its ETag. Refuse when `home_environment` is not this environment
  (`RUN_LOCK_WRONG_HOME`). When the lock is `free`, or `held` with `lease_expires_at` more than five
  minutes past, write the new holder with `If-Match`. A `412` means another runner moved first, and
  this one stops.
* **A live lease held by another runner:** a refused second runner ends `skipped`, with the holder's
  run id and lease in its notification. It writes its record locally only, as ADR-0020 (4) says.
* **Takeover:** a lease expired past the skew margin is taken automatically. The new body records
  `took_over_from`, and the run's details, its summary and its notification say "took over an
  expired lease from run X, expired at T". The record's own schema is frozen (`sync_runs.py`), so
  this goes in the details and the notification text, not in a new record field.
* **The lease:** 30 minutes, renewed every 5 by a background thread with `If-Match` on the ETag it
  last wrote, using the injected clock.
* **Fencing:** one chokepoint, a botocore `before-call` handler registered on every S3 client the
  CLI container builds in bucket mode, the everyday client and the removal client alike. Before
  each write it checks the lease. A write is a `PutObject`, `CompleteMultipartUpload`, `CopyObject`,
  `PutObjectTagging`, `DeleteObject` or `DeleteObjects`. For a named key, the handler renews first.
  For a content-addressed key (`raw/.../sha256/...`), it only checks that the lease is not lost.
  With no lease held in bucket mode, the write is refused. So a command that forgets to take the
  lock fails closed instead of writing unfenced.
* **Renewal cost:** concurrent writers that are waiting share one in-flight renewal, but only one
  that started after their request. That keeps "renewed before every named-object write" true
  without one serial conditional PUT per parsed file (question 5).
* **Lock lost** (a renewal gets `412` or `404`): every later write is refused. The run ends with the
  code `RUN_LOCK_LOST`, writes its record locally only, saves nothing to the bucket, and is notified.
  Under v1-e34-t32's rule, a RUN_LOCK_LOST run reads stale until the record of the run that took
  over lands. The PM noted this is acceptable, and this report records it.
* **Release:** write `state: free` with `If-Match`. The lock is never deleted.
* **Who takes it in bucket mode:**
  * `caselist pull` (every non-dry mode)
  * `caselist publish`
  * `caselist parse --publish`, including `--publish-only`
  * `caselist remove --execute`
  * `caselist unsuppress`
  * `caselist retire --bucket --execute`, and `--restore`
  * `landscape report --publish`
  * `tub index publish`
  * `store sync --push`
  * the seed (item 6), which creates the lock

  A dry run reads and takes nothing. The local `flock` stays.
* **A guard against a new command slipping through:** a test enumerates every registered Typer
  command and requires each to be classified as bucket-writing or not.

**3. The restore** (`application/caselist/run_state.py`; `parsed_restore.py` for the parsed store).
It runs after the lock is taken, before the select stage. A dry run restores the bundle and state
files only, without the lock, and never the parsed store.

* **Run-state bundle.** Download it, check it against the publisher's recorded SHA-256, and unpack
  it into a staging directory under the data directory. Then ask the publisher's own withholding
  rule (`withheld_manifest_reason`, the callable `store sync --push` uses, through the same
  `WithheldManifests` type) about each manifest in it. If any is withheld, the run refuses with the
  publisher's message and installs nothing. There is no second copy of the rule. Otherwise it
  replaces `objects/manifests/` and `debate.sqlite3` by rename.
* **State files** under `reports/sync/state/`: list the prefix, then fetch what is there. A file the
  bucket does not hold is one the Mac never wrote, and is treated as the local code treats a missing
  file today.
* **Suppression list:** reconcile the local copy from the bucket's, as the search index stage
  already does, before anything imports.
* **Published index:** fetch `current.json` and that build's `manifest.json` into
  `tub-index/<id>/manifest.json`. The stage keeps the newest local index current when the digests
  match and nothing is published. For a manifest-only directory I make two rules explicit, by test:
  it is never published from, and a changed digest rebuilds. Without a gzip object it cannot be
  published, so the gzip object is not restored (question 6).
* **Parsed store:** list `parsed/<caselist>/<version>/` for each configured caselist and `openev`,
  with the version this build's parser and profile versions name. Download each object, and check
  the bytes against the SHA-256 in the object's metadata, which `GetObject` returns. A mismatch
  stops the run (`RESTORE_DIGEST_MISMATCH`). On the Mac, a file whose local SHA-256 already matches
  is skipped after a `HeadObject`. The restore never writes `parsed/` in the bucket. A version the
  bucket does not hold is a full parse.
* **Raw sources on demand:** in bucket mode the parse's blob store reads through to `raw/` for a
  digest it lacks. The key is the digest, so the check is the key itself. It writes the fetched
  bytes into `blobs/`. The publish plan already verifies a source the bucket lists before asking
  for local bytes (`publish_plan.py:775`), and the importer re-stores bytes it does not hold, so
  an empty `blobs/` needs no other change.

**4. The save** (`run_state.py`):

* **State files**, each written as ADR-0020 (3)'s table says:
  * the download ledger before each download starts, as the local file is written today;
  * the OpenEv deliveries file when an import completes;
  * the pending-work file whenever the local copy is written;
  * the run log and details at the end of the run. Their records are still published to
    `reports/sync-runs/` and `reports/sync-run-details/` as today.
* **The bundle**, saved only when both checks pass:
  * every local manifest is in the bucket with the same SHA-256 (about 50 `HeadObject` calls);
  * no local manifest is one the publisher withholds (the same callable).

  It is attempted after a publish stage that confirmed everything, and at the end of the run.
  Otherwise the previous bundle stays, and the summary says why. The database is copied with
  SQLite's online backup API, not tarred live, because the agent's database has a WAL. The key is
  `manifests/_run-state/run-state.tar.gz`, which holds no school, team code or file name.

**5. SIGTERM** (from t03's follow-up). The CLI installs a SIGTERM handler for `caselist pull`, and
for every other bucket-writing command in bucket mode. The handler cancels the run's task. The
cancellation becomes `RunTerminated` (`RUN_TERMINATED`), which unwinds through `SyncRunMonitor`, so
a failed record is written. In the remaining time the run then:

1. saves the state files;
2. saves the bundle, only if item 4's checks pass;
3. publishes the record and details;
4. releases the lock.

It has an internal 90-second budget inside ECS's 120 seconds. When the budget runs out, the bundle
is the first thing skipped, and the release is always attempted. A hard kill (SIGKILL, or the second
signal from `timeout`) skips all of this. The lease then expires, and the next run takes over with
the message above.

**6. The seed:** `debate-research caselist seed-run-state`. It is a dry run by default. With
`--execute` it seeds, and prod also needs `--confirm-prod`. It refuses unless every local manifest
is confirmed in the bucket and none is withheld (the save's two checks). Then it:

1. creates the lock with `If-None-Match: *` and takes it, so a bucket already seeded refuses;
2. uploads the bundle and the five state files;
3. checks each one back against its SHA-256;
4. releases the lock.

It is built and tested here, never run in this session. Its two runbook blocks follow working
agreement 11: a dry run, then `--execute`.

**7. The removal** (`removal_service.py`). In bucket mode `caselist remove --execute` restores the
working copy under the lock. It then runs as today, and after the local records step it:

1. rebuilds the bundle from the rewritten manifests and database;
2. writes it with the everyday profile;
3. confirms it: a `HeadObject` shows the new version is current and its recorded SHA-256 is the
   local digest;
4. only then lists `manifests/_run-state/` versions with the removal credential and deletes every
   noncurrent one.

An unconfirmed rewrite purges nothing and ends `INCOMPLETE`, and running it again finishes it. The
removal log's scope records the bundle's new version. The runbook's removal page gains the step.

**8. store sync and the layout document.** `store sync` skips `manifests/_run-state/` as it skips
`manifests/_suppression/`, with a new skip reason. `docs/architecture/evidence-store-layout.md`
gains three prefixes:

* `reports/sync/run-lock.json` (no personal data, never deleted);
* `reports/sync/state/` (no personal data);
* `manifests/_run-state/` (personal data, removal-reachable).

**9. Terraform** (question 1). `run_task.tf` gains `DEBATE_CASELIST__RUN_STATE=bucket`. A new test
run, `the_run_role_never_deletes`, covers every inline policy the exclusive set names. It matches
IAM wildcards too (`s3:Delete*`, `s3:*Object*`), not only the literal names t03's assertion lists.
Its red run is against a mutated `roles.tf`: an extra run-role statement, which the variable's
validation cannot see. No apply from the branch. The change merges `--partial`, and the PM reads
the plan of the new task definition revision.

### IAM: what each principal needs, and holds today

| Principal | Bucket mode needs | Granted today by | New grant |
|---|---|---|---|
| Run role (`debate-<env>-caselist-run`) | List `reports/sync/run-lock.json`, `reports/sync/state/`, `parsed/<c>/<v>/` | `ListDocumentedEvidencePrefixes` (`reports/*`, `parsed/*`) | None |
| | Get and conditional Put of the lock; Get and Put of the state files and the bundle | `ReadAndPublishEvidenceObjects` (`s3:GetObject`, `s3:PutObject` on `<bucket>/*`); `If-Match` and `If-None-Match` need no other action | None |
| | Get `raw/`, `parsed/`, `reports/tub/search/` | The same statement | None |
| | Use the evidence key | `UseEvidenceKey` | None |
| Operator (`Debate<Env>EvidenceOperator`): seed, fallback week, the removal's everyday half | The same as the run role | The same document | None |
| Removal (`Debate<Env>EvidenceRemoval`) | List versions under `manifests/_run-state/` | `ListEvidenceObjectVersionsForTakedown` (`manifests/*`) | None |
| | Delete the bundle's noncurrent versions | `DeleteDisclosedMaterialOnRequest` (`s3:DeleteObjectVersion`, `s3:GetObjectVersion` on `manifests/*`) | None |
| | Read and write the bundle and the lock | Not needed: the everyday profile does both, as it writes rewritten manifests today | None |

The run role never gets `s3:DeleteObject` or `s3:DeleteObjectVersion`, and gets no inline policy.
One option that is not in this task's packages: a bucket-policy deny on a `PutObject` of
`reports/sync/run-lock.json` without `s3:if-match` or `s3:if-none-match`. That would make every
lock write conditional at the bucket. It belongs to the evidence bucket module, so it is listed
under follow-up work.

### Measurements, read-only on the operator's Mac, 2026-10-24

Taken from `~/.debate-research/dev`. Another session's work had the Mac at load 8.8 to 10.2 on 11
cores, so the times run high. Nothing was written to the data directory or kept: the tar streams
went to `wc`, and the hashing script printed counts only.

| What | Command | Result | Time |
|---|---|---|---|
| Manifests | `find objects/manifests -type f`, sizes summed | 50 files, 18,655,784 bytes | under 1 s |
| Database | `stat` of `debate.sqlite3` (the WAL was 0 bytes) | 42,803,200 bytes | — |
| **Bundle, gzip -6** | `tar -cf - -C $D objects/manifests debate.sqlite3 \| gzip -6 \| wc -c` | **9,882,693 bytes** (manifests alone 1,933,827; the database alone 7,948,800) | 0.55 s |
| Bundle, unpacked | the same stream through `gunzip \| wc -c` | 61,624,320 bytes | 0.74 s |
| Parsed store, SHA-256 of every file | a Python `hashlib` walk over `parsed/` (script in the session scratchpad, run with `-I`) | 15,344 files, 9,140,691,684 bytes. By caselist: hsld26 6,125 files, 3.15 GB, 4.5 s; hspf26 5,237 files, 1.53 GB, 2.8 s; hspolicy26 3,872 files, 4.27 GB, 5.2 s; openev 107 files, 0.20 GB, 0.2 s; testcl26 3 files, 0 bytes | 12.7 s |

**A restore of today's state, estimated.** The bundle, the state files and the index manifest take
seconds. The parsed store's transfer is the cost, and it cannot be measured without AWS reads,
which are the operator's.

* **In region, the cloud run** (*estimate*): 15,344 GETs moving 9.14 GB. At 100 MB/s with 16 to 32
  concurrent requests, that is about 3 to 6 minutes, with the hash check overlapped. ADR-0020 said
  under 10.
* **From the Mac, a fallback week** (*estimate*): about 12 minutes at 100 Mbit/s and about 4
  minutes at 300 Mbit/s, depending on the home connection.

The cloud figure is measured by the first bucket-mode run. The restore's start and end go into the
run's details, beside t03's stage times. They do not become a new `SyncStage`: the record's stage
list is read by installed builds, and an unknown stage name would make them skip the record.
Question 7 offers a hand-off that times the Mac figure now.

### Tests (offline: moto 5.2.3 for S3)

moto here answers `If-Match` with `412`, a missing key under `If-Match` with `404`, and
`If-None-Match: *` with `412` on `PutObject` and `CompleteMultipartUpload`. I read this in
`moto/s3/responses.py`. The tests:

* **ac1:** a run on an empty data directory against a seeded moto bucket. Its parse counts, its
  parsed files' digests and the index's document count and digests equal those of the same run on
  a full directory. Run separately, a full re-parse fetches raw on demand.
* **ac2:** a fault injector that "kills" the run after each stage, and after the Nth bucket write
  inside the publish, parse and index stages. From the bucket's side, a dropped process is all
  later writes failing and no cleanup running. Each kill is followed by a fresh run on an empty
  directory with the clock past the lease. That run must take over, complete, and leave a bucket
  that store status, `caselist status` and the index pointer read as whole. The same matrix runs
  for SIGTERM: the handler path saves, records `failed` and releases. One subprocess test sends a
  real SIGTERM to the CLI entry point.
* **ac3:**
  * live lease → refused, skipped, nothing written to the bucket (object versions unchanged);
  * expired lease → taken over, and the message names the old run;
  * renewal answered `412` → `RUN_LOCK_LOST`, and no bucket write after it;
  * no lock object → refused before any restore;
  * wrong home → refused;
  * one parametrised test per bucket-writing command: the lock versions show held, then free, and
    a held lock refuses the command;
  * the classification test over every registered command.
* **ac4:** a removal against moto leaves no noncurrent version of the bundle holding the removed
  rows. A fake that fails the rewrite's confirmation shows no purge, and an ordered call log shows
  the purge after the confirm. The Terraform test is `the_run_role_never_deletes`. **The red runs
  come first:** the removal test against today's removal service, which leaves the bundle alone,
  and the Terraform test against a mutated `roles.tf`. Both go in this report.
* **Mutants**, about 20 by hand under working agreement 10, in `run_lock.py`, `run_state.py` and
  the removal's purge step:
  * the lease length and renewal interval;
  * the skew margin's comparison;
  * takeover's `If-Match` dropped;
  * `took_over_from` not written;
  * the lost flag not set, or not checked by the fence;
  * a content-addressed key fenced as named, and the reverse;
  * the no-lock refusal inverted, or skipped when the listing answers 403;
  * the purge before the confirm;
  * the confirm comparing the version and not the digest;
  * the bundle saved with one manifest unconfirmed;
  * the withheld check skipped on save, and on restore.

### Order of work

1. The setting.
2. The lock: port, adapter and service, with its tests.
3. The fence on the container's S3 clients.
4. The lock taken in each command.
5. The restore.
6. The save and the bundle.
7. SIGTERM.
8. The seed.
9. The removal: red run first.
10. store sync and the layout document.
11. Terraform, after question 1: red run first.
12. The runbooks: t03's step 8 gains the seed before it, and the removal runbook gains the bundle.
13. Mutants.
14. The affected set, ruff, pyright, lint-imports, `check_thin_handlers.py`, validate_specs.

### The questions, as sent

Ruled by the PM on 2026-10-24: 1 yes, 2 yes, 3 (a) and (b), 4 as named, 5 yes with a test, 6 as planned with both rules tested, 7 skip. Kept as sent.

```text
v1-e40-t04 questions (session report: docs/session-reports/v1-e40-t04-run-state-on-s3.md, "Plan for the PM's ruling")

1. Bucket mode in the task definition. ADR-0020 (5) puts bucket mode in the run task's environment,
   but run_task.tf is outside constraints.packages (only infrastructure/modules/caselist_run/tests
   is in). Recommend: amend packages to add infrastructure/modules/caselist_run, for one line
   (DEBATE_CASELIST__RUN_STATE=bucket) and its test assertion. Merge --partial. You read the plan
   (expect the run task definition replaced and the run schedule repointed), applied after the
   seed. No new IAM grant anywhere (the report's IAM table), so no policy changes.

2. Two more bucket-writing commands. ADR-0020 (4)'s list leaves out `caselist retire --bucket`
   (--execute and --restore write object tags) and `landscape report --publish`. The forbidden
   list says no command writes a bucket without the lock in bucket mode. Recommend: both take the
   lock, and the ADR's list gains them in your next batch.

3. A local-mode Mac on a seeded bucket. Between the seed and t06, a Mac in local mode that pulls
   would download against a ledger the bucket does not share and publish from state older than the
   bucket's. Recommend two things:
   (a) in local mode, a bucket-writing command with a session refuses once the bucket holds a lock
       object ("this bucket keeps its run state; set caselist.run_state = bucket"). With no lock
       object, nothing changes;
   (b) the seed runs only after the Mac's agent is unloaded (ADR-0020 (4) cutover step 3). So the
       seed is t06's step 4, and t03's step 8 (the first bucket-mode run) follows it.
   This also settles the removal: once seeded, a removal always runs in bucket mode and rewrites
   the bundle.

4. The seed's name and shape: `debate-research caselist seed-run-state`, a dry run by default,
   `--execute` to seed, `--confirm-prod` in prod. It refuses unless every local manifest is
   confirmed in the bucket and none is withheld. Recommend as named.

5. Fencing's cost. "Renewed before every named-object write" over about 2,700 parsed-store and
   manifest writes a run is about 2,700 conditional PUTs, serial by ETag. Recommend: writers waiting
   at the same moment share one renewal, but only one that started after their request. Each write
   is then still preceded by a confirmed renewal. Recommend yes.

6. The index stage's restore. It compares digests with the newest local index's manifest, so a
   restored tub-index/<id>/manifest.json is enough. The gzip object (312 MB) is not restored. A
   manifest-only directory is never published from, and a changed digest rebuilds (about 305 s).
   Recommend as planned.

7. Restore timing. The cloud figure comes from the first bucket-mode run's restore times, in its
   details. If you want the Mac's fallback-week figure now, it is a one-block hand-off: time a
   download of parsed/hspf26/<version>/ (5,237 objects, 1.53 GB) into a directory under the data
   directory, then remove that directory. Recommend: skip it, since the fallback week is rare and
   its time is the home connection's.
```

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-24

**Notes:**

The largest task in E40, built as the accepted plan said, and checked hard.

1. **All four criteria pass by test, and ac4's halves were red first.**
   * ac1 compares an empty-directory run with a full one key by key, digest by digest and manifest
     by manifest, and again with no parsed store in the bucket.
   * ac2 kills at the start of each of 8 stages, after 7 counts of bucket writes and at the end,
     plus 5 real SIGTERMs. Each next run takes over and leaves the bucket equal to an uninterrupted
     run's, ETag for ETag, apart from the late parse in finding 2.
   * ac3 covers the lease, the takeover, the skew margin, the first-writer race, `RUN_LOCK_LOST`,
     the never-start-without-a-lock refusal, all 8 commands and the classification of every
     command.
   * ac4's removal and Terraform red runs are in the report. `the_run_role_never_deletes` matches
     IAM wildcards and `NotAction`, not just names.
2. **21 mutants were caught.** The one that survived (a run's end not asking the lease) was masked
   by the fence, and it got its own test. Two tests were added up front where no test could catch a
   mutant. That is the right instinct.
3. **Finding 1 (`VACUUM INTO`, not an online backup): accepted, and a good catch.** The online backup
   would have copied a removed row's free pages into the rewritten bundle, and a removal must not
   leave the removed rows in any version. ac4 now checks the removed file's digest is in no byte of
   the remaining version.
4. **Finding 2 (a run killed after its publish leaves that week's parse late): accepted** as the
   Mac's behaviour, never a loss. The "parse owed" record is a small new E34 task in the PM's next
   batch.
5. **Accepted as made:**
   * the packages amendment (ruling 1);
   * the two extra lock-takers (ruling 2), the local-mode refusal (3(a)) and the seed at t06's step
     4 (3(b));
   * deviation 3, the ledger recorded before a download in bucket mode: conservative, and never an
     extra download;
   * deviation 4, `VACUUM INTO`;
   * which commands restore;
   * records that stay local for runs that never held the lock;
   * the holder from ECS's metadata variable;
   * SIGTERM in the main thread outside `pull`, and only in bucket mode inside it.
6. **The stale readings** under v1-e34-t32 for `RUN_LOCK_LOST` and `RunTerminated` are recorded,
   as asked.
7. **Folded into `v1-e40-t06` in the PM's next batch:**
   * `caselist restore-run-state`, for the comparison and a hand publish to prod;
   * a JSON plan check for the bucket-mode apply, in the style of t02's and t03's. It must allow
     exactly the two task definitions replaced and the two schedules repointed (`2 to add, 4 to
     change, 2 to destroy`), with the run's schedule still `DISABLED`;
   * reading the first cloud run's logs for a process-pool parse stopping within 120 s of SIGTERM.
8. **CI:** about 380 more test-seconds in `bucket_mode/`. If one part's pytest step passes two
   minutes, agreement 1's fix is another part.

**The PR** merges `--partial`, with the phase `InProgress`. Nothing is applied before the cutover.
The PM sets the Goal `Succeeded` once t06's step 4 has seeded dev and the bucket-mode task
definition is applied. After this merges, `v1-e32-t13`'s removal work can start.

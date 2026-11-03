# Session report: v1-e40-t12-held-upload-records-reach-the-bucket

| | |
|---|---|
| Task | `v1-e40-t12-held-upload-records-reach-the-bucket` — A held upload a cloud task records reaches the bucket, not only its working copy |
| Spec | [`plan_specs/v1/e40-cloud-caselist-run/t12-held-upload-records-reach-the-bucket.yaml`](../../plan_specs/v1/e40-cloud-caselist-run/t12-held-upload-records-reach-the-bucket.yaml) |
| Epic / release | `v1-e40-cloud-caselist-run` / `v1.8` |
| Branch | `task/v1-e40-t12-held-upload-records-reach-the-bucket` |
| Session status | COMPLETE |

## Summary

In bucket mode, every save of the run-state bundle now does one thing first, under the run's lock.
It appends to `manifests/_suppression/held-digests.jsonl` every held-upload line the working copy
holds and the bucket lacks, before the bundle, whether or not the bundle is then saved
(`RunState.save_held_digests`). The append only adds lines: a removal's line already there stays
byte for byte. No reader, format or IAM grant changed. This is what the PM ruled on 2026-10-27.

Against moto, two cases are found from another data directory by both `caselist status` and the
removal run again: a cloud task that refuses an upload at a held path and then dies, and a backfile
import that does the same. The re-run's `--execute` then suppresses the upload. All of these tests
failed first. Of 9 mutants, 8 were caught, including the PM's three and the PM's sixth. The survivor
is equivalent, for a reason given below. ADR-0020 (3) has its dated amendment, and the layout
document, the removal runbook (steps 8 and 9) and the docstrings say who writes the key.

**Look first at:** Deviation 1. My ac1 counts missed a writer: the pull's search index stage already
reconciles the held-digest record to the bucket. The change still closes two real gaps, but they are
narrower than the counts implied. A task that dies between its publish stage and its index stage
loses the record for good on `dev` today, and the backfile import never carries it at all.

## The build, against the rulings

| Ruling | What was done |
|---|---|
| The existing key, no reader or format change | `manifests/_suppression/held-digests.jsonl`. Readers, `HeldDigestEntry` and IAM are untouched. |
| `save_bundle` first gives the bucket the working copy's lines, under the lease, at every save site | [run_state.py](../../packages/debate_core/src/debate_core/application/caselist/run_state.py) `save_held_digests`, called first in `save_bundle`, before the withheld and confirmed checks. All four save sites (pull, seed, backfile step 3, removal rewrite) hold the lease, and the write goes through the fenced adapter. |
| Append only what the bucket lacks; never rewrite or drop a line; test it | Through the list's own set-union append (`ObjectStoreAppendOnlyRecord`: read, extend, write, check the old bytes are still the prefix). Tested: a removal's line stays byte for byte, the bucket keeps both versions, and a line already present is not written again. |
| Say what a run killed before any save leaves | Tested: the next run redoes the week and meets the upload again. The known edge is under Decisions. |
| Amend the rule | ADR-0020 (3), a dated amendment; the three named docstrings; evidence-store-layout.md's "Who may touch what". |
| Local mode unchanged; `caselist import` local-only; status's inbox section this machine's | No code path changed in local mode. A local-mode pull that dies before its index stage leaves the bucket without the record, as before (test). `caselist import` is untouched. The runbook line is in step 9. |

## Counts (ac1), as sent to the PM

The counts and proposal below are as they went to the PM at the checkpoint (commit `88e5dcc`, whose
version of this report also holds the relay prompt). **Correction:** there is a fourth writer, the
pull's search index stage. See Deviation 1.

Read on 2026-10-27 from `dev` at `877f49d`, on this branch.

### What the record holds, field by field

`HeldDigestEntry` ([ports/suppression.py:364](../../packages/debate_core/src/debate_core/application/ports/suppression.py#L364)),
one JSON line per upload an import refused because a removal holds its path (`v1-e30-t23`):

| Field | What it is | Personal data |
|---|---|---|
| `schema_version` | `1` | None |
| `sha256` | The refused upload's bytes | None: a content digest |
| `disclosure` | The held path, as the hold's own `PathHoldEntry.disclosure`: a digest of caselist and path | None: the path is hashed |
| `request_id` | The removal request holding the path (`RM-…`) | None |

There is no date, so the same upload held twice makes one line, and a set-union append adds it
once. No field can hold a school, a team code, a path or a file name. Locally the file is
`<data_dir>/suppression/held-digests.jsonl`. In the bucket it is
`manifests/_suppression/held-digests.jsonl` (`HELD_DIGESTS_KEY`,
[suppression.py:120](../../packages/debate_core/src/debate_core/application/caselist/suppression.py#L120)),
and neither name identifies anyone.

### Every writer (3 code sites)

| # | Writer | Which copies | Under the lock in bucket mode? |
|---|---|---|---|
| W1 | The import pipeline, as it meets a member at a held path, unless it is a dry run ([pipeline.py:354-366](../../packages/debate_core/src/debate_core/application/caselist/pipeline.py#L354-L366), `record_held_digests`) | Whatever suppression object the importer holds. See the next table | Depends on the caller. See the next table |
| W2 | `caselist remove --execute`, first act: `append_held_digests(())` on the union of local and bucket, with the takedown credential ([removal_service.py:748-751](../../packages/debate_core/src/debate_core/application/caselist/removal_service.py#L748-L751)) | Gives the bucket the lines this machine has, and gives this machine the lines the bucket has | Yes: the takedown client is fenced in bucket mode |
| W3 | `RecordedSuppressionList.reconcile()`, called only by `caselist restore-run-state` ([run_state_restore.py:137-140](../../packages/debate_core/src/debate_core/application/caselist/run_state_restore.py#L137-L140)) | Gives the new copy the bucket's lines. The copy starts empty, so it writes only the copy | Yes: it is called holding the lock |

W1, by the command that reaches it ([container.py](../../packages/debate_cli/src/debate_cli/container.py)):

| Command | Suppression object | Where W1's line goes | Lock at the moment of the write, in bucket mode |
|---|---|---|---|
| `caselist pull` (the weekly run, a cloud task) | `LocalFallbackSuppressionList(union, local=…)` (container.py:1664-1670) | Local only, whatever the session: `LocalFallbackSuppressionList.append_held_digests` ([suppression.py:436-443](../../packages/debate_core/src/debate_core/application/caselist/suppression.py#L436-L443)) | Held: the pull holds the lease from restore to release |
| `caselist backfile-import --execute` (`v1-e40-t09`'s cloud task) | The same object (container.py:2004-2009) | Local only | **Not held**: the import is step 2, "not locked" ([backfile_import.py:31-44](../../packages/debate_core/src/debate_core/application/caselist/backfile_import.py#L31-L44)). A bucket write here would be refused `RUN_LOCK_NOT_HELD` by the fenced client ([fencing.py](../../packages/debate_core/src/debate_core/integrations/s3/fencing.py)) |
| `caselist import` (offline, the Mac) | `local_suppression_list()` (container.py:1036) | Local only | Not applicable: classified as never writing a bucket (`NEVER_WRITE_A_BUCKET`, test_bucket_mode_lock.py:216) |
| `caselist import-openev`, OpenEv in the pull | Same objects | None: a camp import passes no `disclosure_scope`, so `_path_hold` returns `None` ([pipeline.py:584](../../packages/debate_core/src/debate_core/application/caselist/pipeline.py#L584)) | Not applicable |

### Every reader (2 that report, 2 that reconcile)

| # | Reader | Copies it reads | What it does in bucket mode today |
|---|---|---|---|
| R1 | The removal plan's *REFUSED AT IMPORT AT A HELD PATH* (`RemovalPlanner`, [removal_plan.py:1024-1027](../../packages/debate_core/src/debate_core/application/caselist/removal_plan.py#L1024-L1027) → `_refused_at_import`, line 2122) | `container.suppression_list()`: this data directory's copy and the bucket's | It restores the bundle (`removal_run_state`) and reads both. A line that is only in a stopped task's working copy is in neither, so the held upload is not planned |
| R2 | `caselist status`'s *REFUSED AT IMPORT AT A HELD PATH* and `removals_owed` (`CaselistStatusService._refused_at_import`, [status_service.py:696-711](../../packages/debate_core/src/debate_core/application/caselist/status_service.py#L696-L711)), asked with `held_in_inbox=True`, as the CLI asks (commands/caselist.py:545) | The same union | It reads both and restores nothing. The cloud task's line is in neither, so nothing is reported as owed |
| R3 | W2's union read, before it writes | Union | Reconciles the copies. It can carry only lines that some surviving copy holds |
| R4 | W3's union read | Union | The same |

`LocalFallbackSuppressionList.held_digests` exists, but no production code calls it: the only callers
of `read_held_digests` are R1 and R2, and each holds the plain union.

The **held-in-inbox checks** are a separate source and do not read the record. Status's
`held_in_inbox` (status_service.py:658-664) and the plan's *in the download inbox* holdings
(removal_plan.py:1006-1007) read the archives in **this machine's** inbox. ADR-0020 (3) does not save
the inbox, so in bucket mode, from another data directory, these checks never see a cloud task's
download. The record is the only thing that outlives the archive, which is the case the runbook
already describes ("whether or not its archive is still in the inbox").

### Does the run-state bundle carry it?

**No.** `LocalRunStateFiles.pack` puts the manifests directory and a `VACUUM INTO` copy of the
database into the bundle, and nothing else. `_check`
([run_state_files.py:110-122](../../packages/debate_core/src/debate_core/integrations/local/run_state_files.py#L110-L122))
refuses every other member with "a member is neither a manifest nor the database", so a build from
before this task would refuse a bundle that held the record. `RunState.restore` does not touch
`suppression/`, and `install` replaces only the manifests and the database.

### The tests that touch it

13 test files mention the record by name (`held-digests`, `HeldDigestEntry`, `read_held_digests`,
`record_held_digests`, `refused_at_import`). The moto harness that the build would use is
`packages/debate_cli/tests/bucket_mode/conftest.py`. Its `world.use(<directory>)` already switches
data directories between a "cloud task" and "the Mac's copy". `test_backfile_import.py:539` already
has a backfile import meet a held upload (`held_by_request == {"RM-2026-06": 1}`), but it asserts
nothing about the record.

### The proposed place, and the alternatives

| | (a) `manifests/_suppression/held-digests.jsonl`, the existing key (**recommended**) | (b) Inside the run-state bundle | (c) A new key under `reports/sync/state/` |
|---|---|---|---|
| Readers | R1 and R2 already read it. No reader code changes | R1 sees it after its restore. R2 restores nothing, so it would need to download the 15 MB bundle on every `status`, or it misses the record | Both would need a third copy added to their union |
| Older builds | Unaffected: this key exists since `v1-e30-t23` | A build from before this task refuses the bundle (`_check`), which breaks a Mac fallback week and an image rollback | Unaffected |
| Removal | W2 already reconciles it | The removal's bundle rewrite must carry it, which makes two bucket copies of one record | Two bucket copies of one record |
| Class (ADR-0020 (3)) | The suppression prefix, beside the path holds that it joins | The personal-data class, and the record holds no personal data | The no-personal-data class, but the record names removed bytes |
| Lock | Written only at a bundle save. All four save sites already hold the lease | The same | Saved "as the local file is written", which for a backfile is the unlocked import |

**When the write happens (recommended):** `RunState.save_bundle` would first call
`append_held_digests(())` on its own suppression list, the union. That gives the bucket's object every
line the working copy holds, and it happens before the withheld check and the confirmed-manifests
check, so a bundle that is not saved still leaves the record behind. The four save sites are the
pull after its publish stage, at its end and on SIGTERM; the backfile import's locked step 3; the
seed; and the removal's rewrite. All four hold the lease, and the client is fenced. The invariant is
that **no bundle that records a snapshot is in the bucket without the held uploads its import
refused**. A task killed before its first save leaves the previous bundle, the next run redoes the
week, and its import meets the upload again (ADR-0020 (3): late, never lost). The other route would
be to write each line as the pull meets it, through the union. The pull holds the lock, so that
works there, but the backfile import's step 2 would get `RUN_LOCK_NOT_HELD`, so the backfile would
need a second path.

**Local mode is unchanged:** `save_bundle` runs only in bucket mode. In local mode the pull still
appends to this machine's copy alone, and the next removal from that machine gives the bucket its
lines (W2), as it does today.

**What each reader does in bucket mode after the build:** R1 (removal from another data directory)
reads the bucket's line and plans the upload under *REFUSED AT IMPORT AT A HELD PATH*. R2 (`caselist
status` from another data directory) names it under *REFUSED AT IMPORT AT A HELD PATH in `<caselist>`*
and says *RM-… is owed again*. *HELD UPLOADS IN THE DOWNLOAD INBOX* still reads only this machine's
inbox. R3 and R4 are unchanged.

**Rule 3:** the key is the fixed `manifests/_suppression/held-digests.jsonl`. Its metadata is what
every `put_file` sets: the content digest. Its lines are three digests or ids. The build would include
a test that lists every key and every metadata value the scenario leaves in the moto bucket and finds
no school, team code or path.


## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `held-upload-records` | Done | Counts and a relay prompt to the PM; then, after the rulings: the save, the tests (red first), 9 mutants, the ADR amendment, the docs and the runbook lines. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: counts first (what the record holds, its readers, whether the bundle carries it), sent to the PM with the proposed place in the bucket | PASS, with a correction | Sent at the checkpoint (commit `88e5dcc`), and the PM ruled on 2026-10-27. The counts missed one writer, the pull's search index stage (Deviation 1). The place and the timing the PM chose are unaffected. |
| ac2: against moto, a held upload one task records is found by a removal run and by `caselist status` from another data directory in bucket mode; tests shown failing first | PASS | **Red**, with `run_state.py` at the task's start commit (`git show 9a20f23:…`), every other file as built: `.venv/bin/python -m pytest packages/debate_core/tests/application/test_run_state_saves_held_digests.py packages/debate_cli/tests/bucket_mode/test_bucket_mode_held_uploads.py "packages/debate_cli/tests/bucket_mode/test_backfile_import.py::test_an_upload_a_backfile_import_refused_at_a_held_path_is_found_from_another_data_directory" -n 4 -p no:randomly -q --tb=line` → `10 failed, 4 passed in 15.49s`. Each failure was the record's absence from the bucket: `assert None == b'{…}'` (core ×4), `NoSuchKey` (record and rule 3), `the task uploaded the record` (lock), `KeyError: '1ec6eecb…'` (the re-run's plan lacks the upload), and `{'uploads': 0, …}` (status, pull and backfile). The 4 that passed hold either way: a line already in the bucket is not written again; an empty copy creates nothing; local mode; and a task killed before any save, whose next full run carries the record through its index stage on `dev` too. **Green**, the same command → `14 passed`. |
| Node `held-upload-records`: `uv run pytest packages/debate_core/tests/application -k held` | PASS | Run as `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest packages/debate_core/tests/application -k held -q -p no:randomly` (agreement 10: the alarm goes on the interpreter) → `211 passed in 87.58s`. |

### The tests

[test_run_state_saves_held_digests.py](../../packages/debate_core/tests/application/test_run_state_saves_held_digests.py)
covers the save's rules on their own, against moto:

- the held lines are written before the bundle (the upload order is recorded);
- a removal's line already in the bucket stays byte for byte, and the bucket keeps two versions;
- a line already present is not written again;
- an unconfirmed manifest, or a withheld one, stops the bundle but not the record;
- an empty copy creates nothing.

[test_bucket_mode_held_uploads.py](../../packages/debate_cli/tests/bucket_mode/test_bucket_mode_held_uploads.py)
runs the whole week through the CLI over moto. The Mac pulls two weeks, seeds the bucket and removes
a file by `--source`, which holds its path. A later weekly carries new bytes at that path. A cloud
task refuses them, publishes, and is hard-killed at the start of its parse stage, the way
`test_bucket_mode_kills.py` kills one. Its directory is then deleted. From the Mac's data directory:

- the record is in the bucket;
- `caselist status` names the upload under refused-at-import;
- the removal's dry run plans it as `held_at_import`, and `--execute` puts it on the list, after
  which status says nothing is owed;
- every upload of the record happened while the lock was `held` by the pull;
- no key or metadata value in the bucket holds a school, a team code, a path, the working copy's
  directory or `cloud-task`, and each line of the record has exactly its four fields.

The same file holds two further cases. In the known edge, a task killed before any save, the next
run meets the upload again. In local mode, a pull that dies before its index stage leaves the
bucket without the record.

[test_backfile_import.py](../../packages/debate_cli/tests/bucket_mode/test_backfile_import.py) gains
the backfile case: the import runs unlocked, the record reaches the bucket at the locked step's save,
and status and the re-run find it from the Mac's copy.

### Mutants (working agreement 8)

9 runs, each through
`/private/tmp/claude-501/-Users-charlesclark-Documents-debate-debate-intelligence-tool-debate-intelligence-worktrees-v1-e40-t12-held-upload-records-reach-the-bucket/640d9673-e78a-4ffb-a227-a4f1d67b3c54/scratchpad/run_mutant.sh`.
The script refuses a dirty tree, applies one named mutant
(`/private/tmp/claude-501/-Users-charlesclark-Documents-debate-debate-intelligence-tool-debate-intelligence-worktrees-v1-e40-t12-held-upload-records-reach-the-bucket/640d9673-e78a-4ffb-a227-a4f1d67b3c54/scratchpad/mutate.py`),
and runs the three covering files with `-n 4 -p no:randomly` and a fresh
`HYPOTHESIS_STORAGE_DIRECTORY` (none of these files uses Hypothesis). It then restores from git, and
the tree was clean after each run.

| # | Mutant | Result |
|---|---|---|
| 1 | **PM 1**, the record written outside the lock: the write moved out of `save_bundle` to after the lease's release in `BucketRun.finish` | CAUGHT: 10 failed. The record was missing, and the lock test failed with `the task uploaded the record` |
| 2 | **PM 1**, sharper: the save still writes, and an extra write follows the release | **SURVIVED** (14 passed), equivalent. By the release, the save has already given the bucket every line, so the extra write finds nothing missing and sends nothing. In bucket mode the fence would refuse it anyway (`RUN_LOCK_NOT_HELD`). Mutant 7 is the realistic way to write outside the lock |
| 3 | **PM 2**, a removal reads only the local record in bucket mode (the planner built over the local copy) | CAUGHT: 2 failed (the re-run from another directory, pull and backfile) |
| 4 | **PM 2**, its status half: `caselist status` reads only the local record in bucket mode | CAUGHT: 2 failed (status, pull and backfile) |
| 5 | **PM 3**, a path reaches a key: the record keyed under the working copy's directory, `manifests/_suppression/cloud-task/held-digests.jsonl` | CAUGHT: 10 failed. The rule-3 scan names the key: `AssertionError: ('manifests/_suppression/cloud-task/held-digests.jsonl', {'sha256': …})`. The save site holds no school, team code or member path to leak, and the record's lines hold none; the scan covers every key, metadata value and line regardless |
| 6 | Mine: the write skipped when the bundle is not saved (moved below the confirmed check) | CAUGHT: 2 failed (unconfirmed, withheld) |
| 7 | Mine: local mode writes the bucket. The import appends to every copy, whatever the mode | CAUGHT: 3 failed. Local mode found the key; the backfile import failed `RUN_LOCK_NOT_HELD` ("in bucket mode a write to the evidence bucket needs the bucket's run lock, and this command does not hold it"), the import being its unlocked step; and the before-any-save case found the record written before any save |
| 8 | **PM 6**, an append that rewrites the key whole: the local file uploaded over it | CAUGHT: 2 failed (the removal's line dropped; a line written again) |
| 9 | Mine: the record written after the bundle rather than before it | CAUGHT: 3 failed (the upload order, the unconfirmed and the withheld cases) |

### Before the report

- **Affected set:** `uv run scripts/affected_tests.py` → `340 of 546 test files (62.3%) chosen in
  7.4 s from 12 changed files`. The docstrings the ruling asked for sit in hub modules
  (`suppression.py`, `ports/suppression.py`, `status_service.py`), which widens the selection. At
  62% of a roughly six-minute suite this is over the two-minute line, so under agreement 10 it is
  left to the pull request's `ci` check and not handed to the operator. Within the line I ran the
  following, each `.venv/bin/python -m pytest … -m "not slow and not live"` under a 110 s alarm:
  - `tests/specs tests/docs tests/scripts/test_check_command_blocks.py tests/scripts/test_docs_index.py packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py` → `307 passed in 10.74s`
  - `tests/architecture` → `209 passed in 6.20s`
  - the 11 test files that read the removal runbook, the layout document or ADR-0020, plus `test_caselist_sync_run_state.py` → `225 passed in 104.59s`
  - `packages/debate_cli/tests/bucket_mode` except the kills suite → `90 passed in 61.64s`; `test_bucket_mode_kills.py` → `21 passed in 33.45s`
  - `packages/debate_core/tests/application/caselist` → `1625 passed in 75.33s`

  A first attempt to run the always-run list and the document readers in one command was stopped
  by its alarm at 115 s. Another worktree's tests had the load at 26, and nothing was reported. I
  checked that no worker was orphaned, then ran the batches above.
- `uv run ruff format --check .` → `1524 files already formatted`; `uv run ruff check .` → `All checks passed!`
- `uv run pyright packages/debate_core packages/debate_cli` → `0 errors, 0 warnings, 0 informations`
- `uv run lint-imports` → `Contracts: 18 kept, 0 broken.`; `uv run python scripts/check_thin_handlers.py` → `OK: 67 … handlers within 25 statements`
- `uv run python scripts/check_command_blocks.py --base origin/dev` → OK; `uv run python scripts/docs_index.py --check-descriptions` → `All 55 indexed documents under docs/ have a description`
- `uv run scripts/validate_specs.py` → `OK: 480 files, 40 epics, 418 tasks, 22 releases`

## Files changed

- `packages/debate_core/src/debate_core/application/caselist/run_state.py`: `save_held_digests`,
  called first in `save_bundle`; the module docstring's "What is saved".
- `packages/debate_core/src/debate_core/application/caselist/suppression.py`,
  `application/ports/suppression.py`, `application/caselist/status_service.py`: docstrings only.
  They now say who writes the bucket's held-digest record.
- `packages/debate_core/tests/application/test_run_state_saves_held_digests.py` (new),
  `packages/debate_cli/tests/bucket_mode/test_bucket_mode_held_uploads.py` (new),
  `packages/debate_cli/tests/bucket_mode/test_backfile_import.py` (one test added).
- `docs/adr/0020-weekly-caselist-run-in-the-cloud.md`: the dated amendment in (3).
- `docs/architecture/evidence-store-layout.md`: the exception under "Who may touch what"
  (pre-approved by the PM).
- `docs/runbooks/caselist-removal.md`: step 8's "who writes the bucket's copy", and step 9's line on
  how a cloud task's held upload is found.
- `plan_specs/v1/e40-cloud-caselist-run/t12-held-upload-records-reach-the-bucket.yaml`: phase
  `Succeeded`.

## Deviations from the spec

1. **The ac1 counts missed a writer.** The pull's search index stage reconciles every copy of the
   suppression list before it publishes, held-digest record included (`v1-e39-t09`;
   `search_index_refresh.py`, step 1 of `_keep_current`). It is wired as
   `reconcile=self.suppression_list().reconcile` (container.py:1761). My search looked for
   `.reconcile()` calls and so missed the bound method passed in. I found it when the first
   local-mode test failed: the bucket held the record after a plain local pull at the task's start
   commit, with no change of mine. What follows from it:
   - On `dev`, a pull that reaches its index stage with a session already carries the record to the
     bucket, in either mode. The cloud gap this task closes is narrower than the counts said. First,
     a task that stops after its post-publish save of the bundle and before its index stage: the
     bundle records the week, so no later run meets the upload again, and the record is lost for
     good. The pull test is that case. Second, the backfile import, which never runs the index stage.
   - My Q4 answer for local mode was incomplete. There, the same pull's index stage carries the
     record too, not only the next removal. "Local mode unchanged" holds for this change: no local
     path was touched, and a test pins it.
   - The rule the PM amended ("only remove and unsuppress write `manifests/_suppression/`") had not
     been true since `v1-e39-t09`, because the index stage already wrote `held-digests.jsonl` with
     the everyday credential. The amendment and the layout document now name both writers.
2. **`docs/architecture` is not yet in `constraints.packages`.** The PM pre-approved it and will add it
   in the next batch.
3. **Docstrings beyond the three named.** These said only a removal writes the bucket's copy, and are
   now true again: `HELD_DIGESTS_KEY`, the "And the held-digest record" paragraph of
   `suppression.py`, `RecordedSuppressionList.append_held_digests` and `status_service.py`'s "What an
   import refused". All are inside `debate_core.application`.

## Decisions and assumptions

- **Before both checks.** `save_held_digests` runs before the withheld check and the confirmed-manifest
  check, so a bundle that is refused or not yet confirmed still leaves the record behind. The record
  holds no personal data and depends on no snapshot.
- **Through the union's own append.** `append_held_digests(())` on `RecordedSuppressionList` is the
  removal's existing set-union append. It also gives the working copy the bucket's lines, which is
  harmless. No second implementation of "append what is missing" was written.
- **What a run killed before any save leaves.** A hard kill, or a lost lease, between the import and
  the save after the publish stage leaves the previous bundle. The next run redoes the week and its
  import meets the upload again (tested), late but never lost, within the ledger's five downloads a
  day. **Known edge (one):** if the redone download no longer carries the upload, because the team
  took it down or the weekly is no longer listed, the line is never written. Those bytes never
  entered the store or the bucket either, so the state matches an upload that was never seen. If the
  same bytes later arrive at a path no removal holds, they are imported, as they would have been
  before `v1-e30-t23`. Nothing is built around this, as ruled.
- **`caselist status` from a stale copy reports drift.** The Mac's copy lacks the week the task
  published, so `status` exits 1 (`CASELIST_DRIFT`) with its report in the error's details. The test
  reads refused-at-import there. That is existing behaviour, and a restore closes it.
- **Shared test helper.** The kill switch in `test_bucket_mode_held_uploads.py` repeats about 30
  lines of `test_bucket_mode_kills.py`'s. A test module cannot import another under this repo's
  import mode.

## Operator follow-ups

None for this task. The change reaches the cloud only with a new run image, through the steps in
`docs/runbooks/caselist-cloud-run.md`, "A new image, later". If this merges before Thursday's deploy
for `v1-e40-t13`, it rides in the same image. No deploy commands are drafted here.

## Follow-up work

1. **Add `docs/architecture` to this task's `constraints.packages`.** The PM will, in the next batch
   (Deviation 2).
2. **The writer count, for the next record of this kind.** The search index stage's reconcile writes
   every record beside the list in the bucket, not only this one (path holds, withdrawals), with the
   everyday credential. That is intended by `v1-e39-t09`, and here it is said only for the
   held-digest record. The PM may want the layout document's exception to say it of the whole
   prefix's beside-records. Out of this task's scope.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-27

**Notes:**

Built as ruled. The most useful part is the correction the session found for itself.
1. **ac1 passes, with its correction.** The counts missed the search index stage's bound-method
   reconcile (`v1-e39-t09`). The session found it when a local-mode test passed that should have
   failed, and reported it first rather than burying it. The ruling stands: the gaps this closes are
   narrower but real. A task that stops between its post-publish save and its index stage loses the
   record for good, and the backfile import never runs the index stage.
2. **ac2 passes.** Red with `run_state.py` at the start commit: 10 failed, each on the record's
   absence. The 4 that passed hold either way, and the report says why. Green: 14 passed. The
   whole-week CLI test over moto covers status, the removal's dry run and `--execute` from another
   data directory, the lock held at every upload, and a rule-3 scan of every key, metadata value and
   line.
3. **Mutants: 9, the PM's four among them.** 8 were caught. Mutant 2 is accepted as equivalent:
   after the save, an extra write finds nothing missing, and in bucket mode the fence refuses it.
   Mutant 1 is the version of that write that matters, and it was caught.
4. **Deviations 1 to 3 accepted.**
   * The amended rule now names both writers of `manifests/_suppression/`, which had not been true
     since `v1-e39-t09`.
   * The PM adds `docs/architecture` to `constraints.packages` in the next batch.
   * The extra docstrings sit inside `debate_core.application` and correct what had become false.
5. **Decisions accepted:**
   * the record is written before the withheld and confirmed checks;
   * it goes through the union's existing set-union append, with no second implementation;
   * the one known edge (a redone download no longer carries the upload) matches an upload never
     seen, as ruled;
   * a failed record write stops that save, like any other bucket write under the same lease.
6. **Follow-ups:**
   * 1 is the PM's (packages).
   * 2 is taken: the PM's next batch has the layout document's exception name every record beside
     the list that the index stage reconciles, not only this one.
   * The kill switch repeated from `test_bucket_mode_kills.py` could move to a helper module beside
     the tests, as `tests/smoke/installed_build.py` is. Noted, not filed.
7. **The affected set** (340 files, widened by hub-module docstrings) is left to the PR's `ci` under
   agreement 10. Five batches within the line and the static checks passed.

No re-review is needed. The Goal is `Succeeded`, and the PR merges in full. If it merges before
Thursday 2026-10-29, it rides in `v1-e40-t13`'s image.

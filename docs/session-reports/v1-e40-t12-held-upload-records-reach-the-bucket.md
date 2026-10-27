# Session report: v1-e40-t12-held-upload-records-reach-the-bucket

| | |
|---|---|
| Task | `v1-e40-t12-held-upload-records-reach-the-bucket` — A held upload a cloud task records reaches the bucket, not only its working copy |
| Spec | [`plan_specs/v1/e40-cloud-caselist-run/t12-held-upload-records-reach-the-bucket.yaml`](../../plan_specs/v1/e40-cloud-caselist-run/t12-held-upload-records-reach-the-bucket.yaml) |
| Epic / release | `v1-e40-cloud-caselist-run` / `v1.8` |
| Branch | `task/v1-e40-t12-held-upload-records-reach-the-bucket` |
| Session status | PARTIAL: stopped at the counts checkpoint (ac1), waiting for the PM's ruling. Nothing is built. |

## Summary

This session stopped at the counts checkpoint, as the PM's brief asks. The counts were read from code
and tests only, with no store and no AWS. The held-upload record is `held-digests.jsonl`. It has
four fields and no date, and its one writer is the import pipeline. Today, in every bucket-capable
command, that writer appends to this machine's copy only. Both readers, the removal plan and
`caselist status`, already read this machine's copy and `manifests/_suppression/held-digests.jsonl`
together. So in the cloud the readers are already looking in the right place, but nothing puts the
line there: the line is written into the task's working copy and is lost when the task stops. The
run-state bundle does not carry the record, and its member check refuses anything but the manifests
and the database. **Recommendation:** keep the record at its existing key under
`manifests/_suppression/`. In bucket mode, every save of the run-state bundle first gives that key
the lines the working copy holds. Every save already runs under the run's lock, and the backfile
import's import step does not. Readers change in no code. The relay prompt below asks for that
ruling, plus three smaller questions.

**Look first at:** Q1 and Q2 in the relay prompt (the place, and when the write happens), and
Deviation candidate 1. The rule "only the takedown credential writes under `manifests/_suppression/`"
is a code convention, not IAM.

## Counts (ac1)

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

## Relay prompt for the PM

```text
PM: v1-e40-t12 (held upload records reach the bucket) stopped at the counts checkpoint. The counts
are in docs/session-reports/v1-e40-t12-held-upload-records-reach-the-bucket.md under "Counts (ac1)".
Nothing is built. Four questions; a recommendation leads each.

Facts. The record is held-digests.jsonl: schema_version, sha256, disclosure (a digest of the held
path), request_id. No date, no name, no path. Its one writer (the import pipeline) appends to the
working copy alone in every command, the cloud pull and the backfile import included. Both readers
(the removal plan and caselist status, "REFUSED AT IMPORT AT A HELD PATH") already read the working
copy AND manifests/_suppression/held-digests.jsonl as one. Today only caselist remove --execute
writes that bucket key, and only with lines its own machine has. The run-state bundle does not
carry the record, and its member check refuses anything but manifests and the database.

Q1. Where in the bucket?
  (a) RECOMMENDED: the existing key, manifests/_suppression/held-digests.jsonl. No reader changes,
      no format change, and builds older than this task are unaffected.
  (b) Inside the run-state bundle: builds older than this task refuse such a bundle (fallback week,
      image rollback), caselist status would have to download the bundle, and the removal's rewrite
      would carry a second copy.
  (c) A new key under reports/sync/state/: both readers gain a third copy, and the state files are
      saved as written, which in the backfile import is outside the lock.

Q2. When is it written?
  (a) RECOMMENDED: in bucket mode, RunState.save_bundle first gives the bucket's held-digest record
      the lines the working copy holds, before its withheld and confirmed checks. Every save site
      (pull after publish, at the end and on SIGTERM; backfile step 3; seed; removal rewrite) already
      holds the lease through the fenced client. A bundle that records a snapshot is never in the
      bucket without the held uploads its import refused.
  (b) As the import meets each upload, through the union: this works in the pull, which holds the
      lock, but the backfile import imports unlocked (its step 2), so its write would be refused
      RUN_LOCK_NOT_HELD, and the backfile would need a second path.

Q3. The everyday credential (the run role) then writes one key under manifests/_suppression/.
  IAM already allows it: the run role holds exactly the EvidenceOperator document, PutObject on
  every key, and the store layout document's table says the same ("Write: Any object"). But the
  code says otherwise in three places: the ports/suppression.py docstring, the docstring of
  LocalFallbackSuppressionList.append_held_digests ("may not write under manifests/_suppression/"),
  and is_suppression_key ("which only remove and unsuppress may write"). store sync still skips the
  prefix.
  RECOMMENDED: amend the rule to "held-digests.jsonl is also appended by a bucket-mode run under
  its lock"; write that in ADR-0020 (3) as an amendment and in those docstrings; IAM unchanged.
  This needs docs/architecture added to the spec's constraints.packages, for one line in
  evidence-store-layout.md's table of what writes where. Or tell me to leave the layout document
  alone and say it in the ADR only.

Q4. Confirm the edges. RECOMMENDED: yes to each.
  - Local mode unchanged: the import still writes this machine's copy only, and the next removal
    from that machine carries it to the bucket.
  - caselist import (never writes a bucket) stays local-only in both modes.
  - caselist status keeps reading only this machine's inbox for "HELD UPLOADS IN THE DOWNLOAD
    INBOX". A cloud task's held upload shows under "REFUSED AT IMPORT AT A HELD PATH" and
    "RM-... is owed again"; one runbook line in caselist-removal.md step 9 says so.

After the ruling: moto only, red first; then mutants under agreement 8, including your three
(written outside the lock; a removal reading only the local record in bucket mode; a path or team
code reaching a key), plus "save_bundle skips the write when the bundle is not saved" and "local
mode writes the bucket". The change reaches the cloud with t13's image (caselist-cloud-run.md,
"A new image, later"); I draft no deploy commands.
```

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `held-upload-records` | In progress | Counts done and the relay prompt written. The build waits for the PM's ruling. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: counts first (what the record holds, its readers, whether the bundle carries it), sent to the PM with the proposed place in the bucket | PASS (pending the PM's ruling) | Read-only, from code and tests: see "Counts (ac1)". The relay prompt above carries it to the PM. |
| ac2: against moto, a held upload one task records is found by a removal run and by `caselist status` from another data directory in bucket mode; tests shown failing first | NOT RUN | Nothing is built before the ruling (the PM's brief). |
| Node `held-upload-records`: `uv run pytest packages/debate_core/tests/application -k held` | NOT RUN | The same reason. |

## Files changed

- `docs/session-reports/v1-e40-t12-held-upload-records-reach-the-bucket.md`: this report, with the
  counts and the relay prompt.

## Deviations from the spec

None yet. Two candidates are raised in the relay prompt (Q3) for the PM to rule on, not acted on:

1. **The "takedown credential alone" rule for `manifests/_suppression/` is a code convention.** IAM
   lets the everyday credential, and so the run role, write every key. The recommended place means
   the run writes `held-digests.jsonl` there with that credential. ADR-0020 (3) and three docstrings
   would be amended.
2. **`docs/architecture` is not in `constraints.packages`.** The store layout document's table of
   writers would need one line if the PM wants it there.

## Decisions and assumptions

- The counts are from code and tests only, as the brief asks. No store, bucket or AWS call was made,
  and no test was run, because nothing changed.
- `v1-e40-t09-cloud-backfile-import` is still `Pending`, but its service (`BackfileImportService`,
  `v1-e34-t34`) is on `dev`, so the counts cover it as the spec asks.

## Operator follow-ups

None at this checkpoint. After the build, the change reaches the cloud only with a new run image:
`docs/runbooks/caselist-cloud-run.md`, "A new image, later". If this merges before Thursday's t13
deploy, it rides in the same image.

## Follow-up work

None.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

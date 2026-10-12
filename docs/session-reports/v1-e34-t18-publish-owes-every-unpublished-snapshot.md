# Session report: v1-e34-t18-publish-owes-every-unpublished-snapshot

| | |
|---|---|
| Task | `v1-e34-t18-publish-owes-every-unpublished-snapshot` — A publish stopped by an expired session still owes every snapshot it did not finish |
| Spec | [`plan_specs/v1/e34-caselist-sync/t18-publish-owes-every-unpublished-snapshot.yaml`](../../plan_specs/v1/e34-caselist-sync/t18-publish-owes-every-unpublished-snapshot.yaml) |
| Epic / release | `v1-e34-caselist-sync` / `v1.1` |
| Branch | `task/v1-e34-t18-publish-owes-every-unpublished-snapshot` |
| Session status | COMPLETE |

## Summary

The defect is as you read it on `dev`, in both shapes. The publish stage's expired-session exit
merged only the snapshots it had not reached into the pending-work file, where every other exit
rewrote the file. One function, `snapshots_still_owed`, now says what is owed, and the stage writes
its answer on every ending: everything owed before and everything the stage set out to publish,
less what the publisher confirmed complete. A snapshot with no manifest on this machine is reported
and no longer owed. A pending-work file that cannot be read is `PENDING_WORK_UNREADABLE`: the stage
fails on it, names it by role, and never writes over it. The runbook has a section on the file.
The Goal is `Succeeded`: every criterion passed, including the `ac5` you added, and there is no
operator step.

**Read first:**

- **Deviation 1: your decision 3 and the spec's first forbidden entry disagree, and I followed the
  decision.** The entry forbids "dropping a snapshot from the pending-work file before the bucket
  has confirmed it complete". A snapshot with no local manifest is dropped without the bucket
  confirming it. The entry needs an exception in its wording, or the decision needs reversing.
- **Deviation 3: the stage also writes the file before its first upload.** You asked for one
  computation on every way the stage ends. A run that is killed has no ending, and until now it
  left what it had imported written down nowhere. This goes past your list; it is one more call of
  the same function.
- **Deviation 4: with an unreadable file, the run still publishes what it imported itself.** You
  said to fail the stage and leave the file. The stage does fail, and the file is untouched. I did
  not stop the run's own snapshots from being published, because they need nothing from the file.
- **An expiry after an incomplete snapshot is still `pending`, exit `0`, with no code**, as
  `v1-e34-t13` left it. The incomplete snapshot is now owed, but if it failed on a verdict, such as
  a checksum mismatch, nobody is told until the retry. See Follow-up work.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `owed-snapshots`: Every unconfirmed snapshot stays owed | Done | Tests were written and committed before any code (`604b0bf`): 52 red. The fix is `6b48332`, the runbook `ab0de17`. 28 of 28 mutants are caught. |

## Acceptance criteria

Results are from `6d47d58`, the branch tip before this report. `origin/dev` was still at `7ca98e0`,
the commit the branch started from, when I checked after the last test run, so there was nothing to
sync and `v1-e31-t09` has not merged.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1**: against moto, one snapshot ends incomplete and the session then expires on a later one; both are in the pending-work file. Shown failing first | PASS | `test_a_snapshot_left_incomplete_before_the_session_expired_is_owed_beside_the_one_it_expired_on`, two cases: an upload answered `503`, and an upload not taken over other bytes. Before: the file held `['testcl26 2026-09-08']`. After: both weeks, in the file and in `pending_publish`. The same through the command: smoke `test_a_session_that_expires_part_way_through_publish_owes_every_snapshot_it_did_not_finish`, five snapshots owed where four were. |
| **ac2**: `--publish-pending` after a fresh session publishes every owed snapshot and empties the file only of the ones the bucket confirmed, including a second expiry part-way through the retry | PASS | `test_publish_pending_after_a_fresh_session_publishes_every_snapshot_the_stage_left`: three manifests and the fixture's 14 source objects in the bucket, no file. `test_a_second_expiry_part_way_through_the_retry_takes_only_the_confirmed_snapshots_off_the_file`: after the second expiry the file is weeks two and three (before: all three); the next retry removes it. |
| **ac3**: a test walks every way the publish stage can end and checks the file holds exactly the snapshots not confirmed complete | PASS | `test_however_the_publish_stage_ends_the_file_holds_exactly_the_snapshots_not_confirmed`, 10 endings: completed; failed on a code five ways; pending four ways. Each checks the hand-written list against the file and against the bucket's own manifests. [The endings](#the-endings-ac3) lists them. A second test over the same 10 replaces the one function and checks that the file is its answer. |
| **ac4**: the runbook says what the pending-work file holds and how to check it is empty after a retry | PASS | New section "The pending-work file" in `docs/runbooks/caselist-scheduled-sync.md`. `test_the_runbook_names_the_pending_work_file_and_its_example_is_one_the_sync_reads` reads the runbook's JSON example with the sync's own reader. I ran the section's two check commands in `zsh` against a scratch data directory: with a file they list and print it, without one `ls` says `No such file or directory`. `check_command_blocks.py --base origin/dev` → OK, this report included. |
| **ac5** (added by the PM, 2026-10-10): an unreadable pending-work file is never read as nothing owed and never overwritten; the stage fails with a code and a hint naming it by role; the write is atomic. Shown failing first | PASS | 12 malformed shapes each raise `PendingWorkUnreadable` and leave the bytes as they were (before: `DID NOT RAISE` for all 12). In a run: publish `failed`, `PENDING_WORK_UNREADABLE`, hint contains "the pending-work file under storage.data_dir" and no path, file byte-identical (before: publish `completed`). Through the command: exit `1` (CLI and smoke). `_write_json` already wrote to a second file and renamed it; `test_a_write_that_dies_part_way_leaves_the_file_as_it_was` pins that. |
| Node `owed-snapshots`: `uv run pytest packages/debate_core/tests/application -k "pull or sync or pending"` | PASS | `316 passed in 19.87s` |
| Forbidden: dropping a snapshot from the file before the bucket has confirmed it complete | PASS, with Deviation 1 | A snapshot leaves the file on `report.succeeded` and on nothing weaker (mutant "confirmed means attempted": caught, 15 cases). The one exception is your decision 3. |
| Forbidden: changing `v1-e34-t13`'s exit-code rule or a stage's recorded codes | PASS | `exit_codes.py` and `caselist_pull.py` are unchanged. Every `v1-e34-t13` test passes unedited. The one new code is on no retryable list, so the unchanged rule gives it exit `1`. |
| Retention holds as the safety net (your decision 6) | PASS | `test_a_snapshot_left_owed_by_an_expiry_keeps_its_zip_through_the_next_runs_retention`: both zips are kept as `not_confirmed` through a second run that still has no session, and leave only when a third run publishes and confirms them. |
| Default suite, in two commands so each stays under two minutes | PASS | `uv run pytest -m "not slow and not live" packages --no-cov -q` → `3908 passed in 58.74s`. The same over `tests` → `1258 passed, 1 skipped, 1 warning in 62.88s`. The skip is the parser eval waiting on human corrections; the warning is the smoke harness's blocked-socket check. |
| Static checks | PASS | `ruff format --check .` 578 files formatted; `ruff check .` all passed; `pyright` 0 errors; `lint-imports` 12 kept, 0 broken; `check_thin_handlers.py` OK, 21 handlers; `check_links.py` OK, 1366 links; `docs_index.py --check-descriptions` OK. |
| `uv run scripts/validate_specs.py` after `set-phase … Succeeded` | PASS | `OK: 327 files, 38 epics, 269 tasks, 20 releases` |

### Shown failing first

The tests were committed before any code, at `604b0bf`. Against the source as it was: 49 of 58 core
tests failed, and so did both smoke checks and the command's own check.

I added two tests after the fix. So I also ran the final set against the start commit's
`caselist_sync.py`, the only source file this task changes. I wrote that file over a clean,
committed tree, ran the tests, restored my copy from saved bytes and confirmed `git diff --quiet
HEAD` held. Result: **53 failed, 10 passed**.

| Shape | Test | Before | After |
|---|---|---|---|
| Incomplete, then expiry (your first shape) | ac1's test, both cases | file is `[09-08]` | `[09-01, 09-08]` |
| The same, with a third week never reached | `…publishes_every_snapshot_the_stage_left` | file is `[09-08, 09-15]` | all three, and the retry publishes all three |
| A drain that publishes one, then expires (your second shape) | `…second_expiry_part_way…` | file is all three | `[09-08, 09-15]` |
| A malformed file, in a run | `…leaves_it_and_fails_publish_naming_it_by_role`, 3 cases | publish `completed` in two; in the third, `failed` on `NOTHING_TO_PUBLISH` for the one entry it could read | `failed`, `PENDING_WORK_UNREADABLE`, file untouched |
| A malformed file and an expired session | `…fail_publish_and_name_what_could_not_be_recorded` | `pending` | `failed`, file untouched, the week named in the reason |
| A malformed file, `--publish-pending` | core, CLI | `skipped`, exit `0` | `failed`, exit `1` |
| An owed snapshot with no manifest | `…reported_once_and_owed_no_longer` | still in the file after the run | reported, gone |
| A publish killed part-way | `…killed_part_way…` | no file at all | both weeks in the file |
| Retention after the first shape | `…keeps_its_zip…` | zips kept, but week one never published | kept, then published and removed |

What the red does not prove, so that the count is not read for more than it is:

- **21 of the 53 fail on `AttributeError`**, because `snapshots_still_owed` did not exist: the 11
  cases of its table and the 10 that replace it. That proves only that the function is new. The
  mutants are what prove those tests.
- **Two rows of the walk are red only on order.** "Expired before the first upload" and "incomplete,
  then a refusal" had the right snapshots in the file before. They fail on `pending_publish`, which
  listed this run's snapshots first and now lists them as the file does.
- **Six rows of the walk pass before and after**, as they must: completed, the three failures that
  already rewrote the file, the outage, and an expiry with nothing confirmed from the file.
- **Three other tests pass before and after.** The write was already atomic. The file's shape did
  not change. A snapshot the stage never reached stayed owed.
- **The runbook test passes against the old source**, because I did not revert the runbook for that
  run. Two mutants of the runbook show it failing.

### The endings (ac3)

Every ending starts from the same place. An earlier run imported weeks one and two with the session
expired, so both are owed. This run imports week three. The stage publishes week three, then one,
then two. A snapshot's manifest is the one upload that belongs to it alone, so each ending breaks a
manifest's upload.

| Ending | Outcome | Codes | File afterwards |
|---|---|---|---|
| Nothing goes wrong | `completed` | | none |
| Week one's upload answered `503`, the others confirmed | `failed` | `STORE_UNAVAILABLE` | 09-01 |
| Other bytes under a key only week one has | `failed` | `CHECKSUM_MISMATCH` | 09-01 |
| The bucket refuses the profile at week one | `failed` | `STORE_ACCESS_DENIED` | 09-01, 09-08 |
| The bucket stops answering after week three | `failed` | `STORE_UNAVAILABLE` | 09-01, 09-08 |
| Week three incomplete, then a refusal at week one | `failed` | `STORE_UNAVAILABLE`, `STORE_ACCESS_DENIED` | 09-01, 09-08, 09-15 |
| The session had expired before the first upload | `pending` | | 09-01, 09-08, 09-15 |
| The session expires after week three is confirmed | `pending` | | 09-01, 09-08 |
| The session expires after weeks three and one are confirmed | `pending` | | 09-08 |
| Week three incomplete, then the session expires | `pending` | | 09-01, 09-08, 09-15 |

Each row also checks that the bucket holds the manifest of exactly the weeks not in the file.

### Mutation testing

A driver applied each mutant to a clean, committed tree, ran the tests, restored the file from
saved bytes and checked `git diff --quiet HEAD`. A mutant whose target text is not found exactly
once aborts and is not counted; none did. Each run had its own new, empty
`HYPOTHESIS_STORAGE_DIRECTORY`. The suite was 254 tests in six files, about 20 s a run. The 28
mutants ran in 8 batches, the longest 1 min 37 s.

All 28 were caught by assertion failures, none by a collection error. No catching test is
property-based, so Hypothesis generated nothing and there are no statistics to report.

The runs were made at `ab0de17`. The only source change since is a local variable renamed in
`publish_pending`; I ran the mutant beside it again afterwards and it is still caught.

| Mutant | Caught | Cases failing | Caught by |
|---|---|---|---|
| **The expiry ending saves only the untried targets again** (your 1) | yes | 7 | ac1, ac2, the walk, retention, smoke |
| **The drain leaves published snapshots in the file** (your 2) | yes | 6 | the second-expiry test, the walk, the replaced-function test |
| Both, as the old code had it word for word | yes | 14 | all of the above |
| **A snapshot with no local manifest stays owed** (your 3) | yes | 1 | `…reported_once_and_owed_no_longer` |
| **A malformed file read as empty and overwritten** (your 4): not JSON | yes | 10 | the unit cases, three run tests, CLI, smoke |
| The same: no `publish` list | yes | 3 | the unit cases |
| The same: an unreadable entry skipped | yes | 4 | the unit cases, the run test's "one entry readable and one not" |
| The same: bytes that cannot be read | yes | 1 | the unit case "not UTF-8" |
| The same: the stage writes although it could not read | yes | 6 | the three run tests, smoke |
| **A write in place** (your 5) | yes | 1 | `test_a_write_that_dies_part_way_leaves_the_file_as_it_was` |
| **Confirmed means attempted** (your 6) | yes | 15 | ac1, ac2, the walk, retention, two `v1-e34-t13` tests |
| Nothing is written before the first upload (mine) | yes | 1 | the killed-publish test |
| What was owed before is not among the targets (mine) | yes | 32 | every retry test, old and new |
| The function forgets what was owed and not targeted (mine) | yes | 5 | its table, the walk |
| Newly owed goes in front of what was owed before (mine) | yes | 4 | its table, the walk |
| The summary's `pending_publish` is not what the file holds (mine) | yes | 29 | the walk, `v1-e34-t13`'s tests |
| An unreadable file with nothing else to publish is skipped (mine) | yes | 2 | `--publish-pending`, core and CLI |
| An unreadable file has no hint (mine) | yes | 5 | the run tests, CLI, smoke |
| The error names the file by its path (mine) | yes | 3 | the unit cases |
| An unreadable file and an expired session is `pending` (mine) | yes | 1 | its own test |
| The reason does not name what could not be recorded (mine) | yes | 2 | the two tests of that sentence |
| A name with no place in the store is read as owed (mine) | yes | 2 | the unit cases |
| `--publish-pending` raises on an unreadable file (mine) | yes | 2 | core and CLI |
| A snapshot with no local manifest is not reported (mine) | yes | 2 | mine and `v1-e34-t13`'s |
| The file's code is not recorded beside an outage (mine) | yes | 1 | its own test |
| An incomplete snapshot's code is dropped after a refusal (mine) | yes | 1 | the walk |
| The runbook gives the file another name (mine) | yes | 1 | the runbook test |
| The runbook's example is not the file's shape (mine) | yes | 1 | the runbook test |

Twelve mutants are caught by a single test. Each guards one branch, with a test written for it.
The first of your mutants was not caught by the replaced-function test, because my mutant called
the function again with fewer targets. The word-for-word version is, which is why I added it.

`--cov-report=term-missing` over the node's command shows no uncovered line in `PendingWork`,
`snapshots_still_owed`, `publish_pending`, `_publish_stage`, `_fix_for` or `_write_json`.

## Files changed

- `packages/debate_core/src/debate_core/application/caselist_sync.py`, the only source file:
  - `snapshots_still_owed`: the one computation.
  - `_publish_stage`: reads the file once, writes the function's answer before the first upload
    and when the loop ends, and only then decides the outcome. The `drain_pending` argument is
    gone; both callers passed `True`.
  - `PendingWork.read` refuses a file it cannot read. `PendingWork.add` is removed.
  - `PendingWorkUnreadable`, and its fix in `_fix_for`.
  - `publish_pending` leaves an unreadable file to the publish stage.
  - Docstrings: a new section of the module docstring, "What the pending-work file holds".
- `docs/runbooks/caselist-scheduled-sync.md`: the new section, two rows of the exit-code table, the
  `pending_publish` row, and two entries under "When something goes wrong".
- `packages/debate_cli/README.md`: three sentences on the file under the pull's exit codes.
- Tests, new: `test_pending_work_owes_every_unpublished_snapshot.py` (60).
- Tests, extended: the CLI's `test_caselist_pull.py` (1) and `test_output.py` (2 rows of the exit
  table); `tests/smoke/test_caselist_pull.py` (2).
- Tests, removed: `test_an_unreadable_pending_work_file_reads_as_nothing_owed` in
  `test_caselist_sync.py`. It pinned the behaviour ac5 reverses. The 12 cases in the new file
  replace it.
- `plan_specs/…/t18-publish-owes-every-unpublished-snapshot.yaml`: `ac5`, and the phase.

## Deviations from the spec

1. **A snapshot with no local manifest leaves the file without the bucket confirming it.** Your
   decision 3 says it is not owed. The spec forbids "dropping a snapshot from the pending-work file
   before the bucket has confirmed it complete". Both cannot hold for a snapshot that was owed from
   before. I followed the decision, because it is the later and more specific of the two and gives
   its reason. The stage reports the snapshot with `NOTHING_TO_PUBLISH`, exit `1`, in the run that
   finds it. A snapshot the stage never reached stays owed, since nobody has yet learnt that it has
   no manifest. I left the forbidden entry as written for you to amend.
2. **`ac5` is added to the spec**, on your instruction, with the line "Added by the PM, 2026-10-10".
3. **The stage writes the file before its first upload**, with nothing yet confirmed. The spec says
   "whatever ended it", and a kill is one of the things that ends it: the agent's Mac shutting down
   mid-publish sends no exception for any code to catch. Until now such a run left its imported
   snapshots written down nowhere. The cost is that after a kill the file can name a snapshot the
   bucket did confirm. The next run finds it complete and takes it off. An exception that escapes
   the stage leaves the same superset.
4. **With an unreadable file, the run's own snapshots are still published.** The stage fails with
   `PENDING_WORK_UNREADABLE` whatever else happens, and the file is not written. The alternative
   was to publish nothing, which would leave the run's own imports both unpublished and unrecorded.
   When the bucket does not confirm one of them, it can be written nowhere, so the stage's reason
   ends with `not recorded as owed:` and its name, and `pending_publish` lists it. With an expired
   session the stage is `failed`, not `pending`: pending means recorded for a later run.
5. **"An upload refused" in ac1 is read as "an upload the bucket did not take".** A refusal in
   `v1-e34-t13`'s sense, `StoreAccessDenied`, stops the stage, so it cannot be followed by an
   expiry on a later snapshot. The two cases are a `503` and other bytes under the key.

## Decisions and assumptions

- **The function is "everything, less what is settled".** You described it as previously owed, plus
  incomplete, plus not attempted, minus confirmed. I wrote it as previously owed plus every target,
  minus confirmed and minus no-manifest. The two agree on every outcome that exists. Mine keeps an
  outcome nobody has modelled owed, which is the safe direction.
- **What counts as unreadable.** Not JSON, not UTF-8, no `publish` list, any entry that is not a
  caselist and a snapshot, and any entry `caselist publish` would refuse by name. One bad entry
  refuses the whole file: skipping it would lose it at the next write. A name the store has no
  place for would, by my reading of the old code, have escaped the stage as
  `InvalidPublishTarget`; I did not run that. It is now the file's failure. An
  `OSError` on the read is unreadable too, and is not translated to `STORE_ACCESS_DENIED`.
- **An unreadable file fails the stage even when there is nothing else to publish, and in an
  environment with no bucket.** A person has to look either way.
- **Exit `1`.** The code is on no retryable list, and should not be: the file is the same next week.
- **The hint names the file by role and points at the runbook for its name.** It does not print the
  file name. The runbook gives the name, the shape and what to do when the file cannot be repaired.
- **`pending_publish` in the summary is now exactly what the file holds, in the file's order.**
  Snapshots owed from before come first. Before, the expiry exit listed only the untried ones.
- **The pending stage's reason now includes any incomplete snapshot**, where it said nothing of it.
- **The write was already atomic, so I changed nothing there.** It renames without an `fsync`. A
  killed process cannot tear the file. A power cut between the write and the disk in principle
  could. I did not add an `fsync`, because no test here could tell it from its absence (working
  agreement 8). See Follow-up work.
- **The file's shape is unchanged**, so this build and the installed agent's read each other's.
- **Nothing of yours was touched.** Every test uses `tmp_path`, fakes, respx and moto. I did not
  read or write the data directory, the installed agent or its pending-work file. I fetched
  `origin/dev` once, to see whether it had moved.

## Operator follow-ups

None. No command here needs credentials or runs longer than about two minutes.

For information: the installed agent keeps the old behaviour until it is reinstalled.

## Follow-up work

- **An expiry hides an earlier verdict for one run** (E34). When a snapshot ends incomplete on a
  checksum mismatch and the session then expires, the stage is `pending`, exit `0`, with no code.
  The snapshot is owed now, so the retry reports it. Recording the code on a pending stage would
  change `v1-e34-t13`'s rule that pending carries none, so I left it.
- **Other publisher errors still escape the publish stage** (E34): an `UnreadableManifest` from the
  plan, for one. The run ends on the exception with no summary. Since this task the file already
  holds everything, so nothing is lost; the run is just reported less well than a failed stage.
- **No `fsync` before the rename in `_write_json`** (E34, p3). It covers all four state files.
- **Pre-existing, noticed:** the notification for a failed publish cannot carry the stage's hint,
  so an unreadable file notifies as "caselist pull failed" and the fix is in the summary. This is
  the run-record gap already filed from `v1-e34-t13`.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-10

**Notes:**

Accepted in full, phase `Succeeded`. The defect was real in both shapes. It is now fixed by one
function that every ending uses, and the file that records owed work can no longer lose it.

* **"Everything, less what is settled" is the better form of my rule.** It agrees with mine on
  every outcome that exists, and it keeps an outcome nobody has modelled owed rather than
  dropped. That is the safe direction for a ledger of unfinished work.
* **The walk over ten endings checks the file against the bucket's own manifests,** not only
  against a hand-written list. So each row proves the file and the bucket agree about what is
  done. The second test, over the same endings, replaces the function and checks the file is
  its answer. That shows there is one computation, not ten that happen to match.
* **Honest red.** 21 of the 53 failures were `AttributeError` on a new function. Two walk rows
  were red only on order, and six passed both ways. You said which is which and let the mutants
  carry the proof. You also noticed that your first version of my mutant was not caught by the
  replacement test, and added the word-for-word version. That is the habit working agreement 8
  is after.

**Rulings:**

* **Deviation 1:** my decision 3 stands. The forbidden entry was mine and contradicted it. I
  have amended it in this branch: a snapshot with no local manifest is the one exception, and it
  is reported with its code.
* **Deviation 3, writing the file before the first upload:** accepted. It goes past my list, and
  rightly. A killed run has no ending for any code to catch, and the cost is an over-full file
  that the next run trims.
* **Deviation 4, publishing the run's own snapshots when the file is unreadable:** accepted.
  Failing the stage while still publishing what needs nothing from the file, and naming in the
  reason anything that could not be recorded, loses the least. `failed` rather than `pending`
  for an expiry in that state is correct, because pending means recorded.
* **Deviations 2 and 5:** accepted.
* **No `fsync`:** accepted for this task. A killed process cannot tear the file, and no test
  could tell an `fsync` from its absence.

**Follow-up work, folded by the PM into `v1-e34-t19` in the next spec batch:**

* other publisher errors escaping the stage (`UnreadableManifest` from the plan);
* the `fsync` before rename for the four state files;
* the notification's missing hint.

These sit beside t19's direct manifest reads and notification codes. "An expiry hides an earlier
verdict for one run" waits on the run-record change t19 makes. Whether a pending stage may carry
the codes of incomplete snapshots is decided there.

**No operator steps.** The installed agent keeps the old behaviour until it is reinstalled after
the 2026-10-14 scheduled run.

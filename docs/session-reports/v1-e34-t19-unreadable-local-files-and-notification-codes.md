# Session report: v1-e34-t19-unreadable-local-files-and-notification-codes

| | |
|---|---|
| Task | `v1-e34-t19-unreadable-local-files-and-notification-codes` — Unreadable local files fail a stage, and a notification says whether a failure is transient |
| Spec | [`plan_specs/v1/e34-caselist-sync/t19-unreadable-local-files-and-notification-codes.yaml`](../../plan_specs/v1/e34-caselist-sync/t19-unreadable-local-files-and-notification-codes.yaml) |
| Epic / release | `v1-e34-caselist-sync` / `v1.1` |
| Branch | `task/v1-e34-t19-unreadable-local-files-and-notification-codes` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

**Look at Deviation 1 first.** No compatible shape exists inside the run record, so nothing was
added to it. The codes, hints, earlier findings and parse counts are kept in a second file and a
second bucket prefix, keyed by run id, which no older build opens. ac3 and ac9 say "the run record
carries"; they pass on the reading the kickoff allowed and not on their own words. I set the phase
to `Succeeded` on that reading. If you rule against the design, the phase is wrong too.

What was built:

* A manifest file this Mac will not open or let be written is `LocalStoreAccessDenied` naming the
  manifest directory, in every reader of a manifest by its path. Through `caselist pull` it is exit
  `3`, where it was `70`.
* A weekly or complete archive that cannot be read fails its own import. The run's other archives
  are imported.
* An error the publisher raises outside its per-object loop fails the publish stage on its own
  code, and the run finishes.
* `_write_json` fsyncs the second file before the rename and the directory after it.
* A failed run's notification says whether the next scheduled run should retry it or a person
  should look, by the command's own exit-code rule, and carries the failed stage's hint. A publish
  left pending names what it found before the session expired.
* `caselist runs` shows each run's nine parse counts in its table.

All nine criteria were shown failing on the start commit's source and pass now. 87 mutants were
run; the three that survived are dealt with below. The full suite passes: 5,745 passed, 1 skipped.

**Synced onto `v1-e29-t07` on 2026-10-11, after this report was first written.** The branch is
rebased on `dev` at `d01d4ac` with `scripts/task sync`, both sides kept. Everything below is as it
stands after that. [After the sync](#after-the-sync-onto-v1-e29-t07) lists what the sync changed.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `local-files-and-codes` | Done | `uv run pytest packages/debate_core/tests/application -k "pull or sync or manifest"` → `514 passed in 13.16s` |

## The compatibility design

### Why nothing could go inside the record

`SyncRunRecord` and `StageEntry` both set `extra="forbid"`, and `schema_version` is `Literal[1]`.
That is true of the commit on `dev` this task started from (`0a9c1e6`, `v1-e34-t17`'s build; "the
start commit" below) and of the build the agent runs: `0.1.0.dev60`, installed 2026-10-07. It predates `v1-e34-t12`; its summary schema
is `2`. I read its version and model read-only. The two builds' record classes, log reader and
bucket reader are textually identical, and the JSON Schema each prints for the record is the same
file byte for byte.

I gave both builds' real readers each way of putting the codes inside the record:

```text
reader: debate-core 0.1.0.dev60
  the record as it is (control)                                  2 of 2 run(s) read
  a new field on the record: failure_codes                       0 of 1 run(s) read   <- the run is skipped
  a new field on each stage: error_codes                         0 of 1 run(s) read   <- the run is skipped
  error_codes written only when a stage has some, a failed run   0 of 1 run(s) read   <- the run is skipped
  error_codes written only when a stage has some, a clean run    1 of 1 run(s) read
  a new field on the record: parse (nine counts)                 0 of 1 run(s) read   <- the run is skipped
  parse written as null when the stage did not run               0 of 1 run(s) read   <- the run is skipped
  schema_version 2                                               0 of 1 run(s) read   <- the run is skipped
```

The start commit's code gives the same eight lines. A skipped line is not only a row missing from
`caselist runs`. The older build also loses it from the backlog history, and drops its run id from
the list of records still owed to the bucket without publishing it.

Writing a field only when it is set does not help: it is set on exactly the runs that matter, and
`parse` is set on every run that imports. The only places an older build accepts new content are
the free-text fields (`reason`, `error_class`) and the string lists. `v1-e34-t17` used `reason` for
the parse counts, and ac9 exists to stop reading them from a sentence. `v1-e34-t13` took codes out
of sentences for the same reason. So I did not use them.

### What I built instead

| | On this machine | In the bucket |
|---|---|---|
| The record, unchanged | `<data_dir>/caselist-sync-runs.jsonl` | `reports/sync-runs/<yyyy>/<run-id>.json` |
| The run's **details** | `<data_dir>/caselist-sync-run-details.jsonl` | `reports/sync-run-details/<yyyy>/<run-id>.json` |

`SyncRunDetails` holds, per run id: each failed stage's `error_codes` and `hint`, a pending stage's
`earlier_findings`, `failure_codes` (the codes the exit status was decided from, or the code of the
error that ended the run), a `hint` for a run that stopped on an error, and `parse` (nine integers
or `null`).

Choices inside that design:

* **The details prefix is beside the records' prefix, not under it.** An older build's
  `caselist runs --remote` lists `reports/sync-runs/` and reads every `.json` there. Another kind
  of object under it would be skipped with a warning and would take a record's place among the
  last N. `reports/` is already a granted prefix, so no infrastructure changes.
* **Details are read by ignoring unknown keys** (`extra="ignore"`). A later build adds to them
  without a third file. Their `schema_version` moves only for a change of meaning, and a build that
  does not know the version reads those details as absent.
* **Locally the record is written first; in the bucket the details go first.** A run whose details
  cannot be written still has its record and its notification. A record in the bucket never waits
  for its details: if the details upload fails, the run stays owed as a whole.
* **A record with no details reads as "an older build wrote this".** `caselist runs` says
  `not recorded` for it, which is different from `did not run`.

One gap I know of: a record that an *older* build publishes from the owed list goes up without its
details, because that build knows nothing of them. They stay on this machine. It ends when the
agent is reinstalled.

### Evidence, older builds reading this build

The stored fixtures are in
`packages/debate_core/tests/application/caselist/stored_run_records/`. None is written by hand;
its `README.md` gives the commands. The start commit's code wrote the run log and bucket objects
for nine scenarios (`run_record_scenarios.py`, run by `write_stored_run_records.py` with
`PYTHONPATH` on a `git archive` of `0a9c1e6`).

| Check | Result |
|---|---|
| This build's `SyncRunRecord` schema equals the schema each older build printed (prose stripped) | Equal to both |
| For each of 9 scenarios, every run-log line this build writes validates against that schema and equals the start commit's line, field for field and key order | 9 of 9 |
| The same for every object under `reports/sync-runs/`, and no other object is there | 9 of 9 |
| The run logs and bucket objects are byte-identical to the start commit's (one-off: the generator run against this build's source rewrote all 18 stored files and changed none) | 9 of 9 |
| A refused publish with the adapter's fix in the refusal (`v1-e29-t07`): the record is the stored one but for the words of the publish stage's reason, and validates against both older schemas | Pass |

The real readers, run once over what this build wrote (run log with the details file beside it,
and the bucket with both prefixes):

```text
reader: debate-core 0.1.0.dev60; knows of details: False
  ...
TOTAL: log lines read 10/10; bucket records read 10/10; warnings logged: 0 []
```

The start commit's code printed the same totals. Neither fetched a details object. I ran the
installed build's interpreter with `-B -I` against scratch files only; nothing of the installed
agent, its launchd job or its data directory was touched. This one-off was run before the sync and
not again: the records this build writes for those scenarios are the same bytes after it.

### Evidence, this build reading older builds

| Check | Result |
|---|---|
| Each stored run log reads whole, with no warning, and each record serialises back to the stored line | 9 of 9 |
| Each stored bucket object reads through `read_remote_runs`, and serialises back to the stored body | 9 of 9 |
| Each such run has `details` of `None` | 9 of 9 |
| `caselist runs` over `v1-e34-t13`'s stored schema-3 log shows the row and `not recorded` | Pass |

## Acceptance criteria

"Red" is the test run against the start commit's source (`PYTHONPATH` on a `git archive` of it),
so the tests are the task's and only the source is old. The red runs were made before the sync.
The green counts are from after it.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1** unreadable manifest file is `LocalStoreAccessDenied` naming the role, read and write; exit 3 with the data-directory hint, never 70 | PASS (see Deviation 2) | Red: 10 tests fail on `PermissionError: [Errno 13] ... manifests/testcl26/2026-09-01.jsonl` and `.incoming-manifest-*.tmp`. Through the command: `assert <ExitCode.INTERNAL_ERROR: 70> == <ExitCode.RETRIEVAL_FAILURE: 3>`, twice. Green: `test_pull_contains_unreadable_local_files.py` → `20 passed`; smoke `test_a_manifest_this_mac_will_not_let_be_written_...` and `..._will_not_open_stops_the_run_with_three_and_never_seventy` pass |
| **ac2** unreadable weekly archive fails its own import; the others import; exit by `v1-e34-t13`'s rule | PASS | Red: `PermissionError ... inbox/testcl26-weekly-2026-09-01.zip` ends the run, and the same for `testcl26-all-2026-09-01.zip` and an injected `OSError: [Errno 28]`; through the command `70 == 1` fails. Green: import fails with `["UNREADABLE_ARCHIVE"]`, `snapshots_imported == ("othercl26 2026-09-01", "openev 2026-policy")`, the same caselist's week two held back, exit `1`; the next run imports both weeks from the inbox with no download |
| **ac3** record carries the failed stages' codes; both builds read each other, by test | PASS as amended, FAIL as written (Deviation 1) | Red: `AttributeError: ... no attribute 'read_remote_runs'` and `FileNotFoundError ... caselist-sync-run-details.jsonl`, 57 failed. Green: `test_pull_run_record_is_read_by_every_build.py` → `61 passed`. See the compatibility section |
| **ac4** notification says retry or person; runbook shows both wordings | PASS | Red: `'caselist pull failed' == 'caselist pull failed: will be retried'` and `... needs a person`. Green: `test_pull_notification_says_retry_or_person.py` → `24 passed`. Through the real composition root: exit `3` with title `caselist pull failed: will be retried`, exit `1` with `... needs a person`. `test_the_runbook_shows_both_wordings_...` holds the runbook to the code's constants |
| **ac5** publisher error outside its loop fails publish on its code; run finishes; pending file as `v1-e34-t18` left it | PASS | Red: `UnreadableManifest: manifests/testcl26/2026-09-01.jsonl line 9 is not a usable manifest row: not JSON` ends the run. Green: publish `failed`, `["UNREADABLE_MANIFEST"]`, week two confirmed in the bucket, file holds `["testcl26 2026-09-01"]`, summary file written, record `failed` with no `error_class`, one notification. Also in a whole run, and through the command (exit `1`) |
| **ac6** `_write_json` flush, fsync, rename, directory fsync, for every state file; a failing fsync is the write's error | PASS | Red: `['rename .caselist-sync-pending.json.incoming to ...'] == ['fsync a file of 96 bytes', 'rename ...', 'fsync the directory of the renamed file']` for all four files, and `DID NOT RAISE OSError` twice. Green: `test_sync_state_files_are_written_durably.py` → `6 passed` |
| **ac7** notification carries the stage's hint, parse's included; both wordings hold with a hint; no hint names a path | PASS | Red: `Notification.__init__() got an unexpected keyword argument 'hint'`, `'Notification' object has no attribute 'hint'`. Green: the adapter's grant and missing-profile hints (`v1-e29-t07`), the data-directory and pending-work hints and both parse hints, each asserted equal to a hand-written sentence and to the summary's `hint`; `assert_names_no_path` on each; the Mac's body holds the longest hint whole |
| **ac8** pending publish records the earlier code; summary shows it; notification names it; not in the exit | PASS | Red: `KeyError: 'earlier_findings'`, and the login message lacks the sentence. Green: `earlier_findings == ["CHECKSUM_MISMATCH"]`, `error_codes == []`, `failure_codes == ()`, exit `0`; message ends "A person should look as well: before the session expired a snapshot ended incomplete on CHECKSUM_MISMATCH, which the login will not fix." The red here is the missing field: the exit was already `0`. The mutant "earlier findings count as failure codes" is what proves the guard |
| **ac9** record carries the nine parse counts or null, same compatibility; `caselist runs` shows them in its table | PASS as amended, FAIL as written (Deviation 1) | Red: `KeyError: 'details'`, `KeyError: 'run_details'`, `'Parse stage' in '...'` fails. Green: `details.parse` equals `v1-e34-t17`'s hand-written counts; the table shows nine distinct hand-written numbers each under its own name; `did not run` and `not recorded` both shown |
| Node: `uv run pytest packages/debate_core/tests/application -k "pull or sync or manifest"` | PASS | `514 passed in 13.16s` |

Red runs, final lines: `15 failed, 2 passed` (ac1, ac2, ac5; the two that pass pin behaviour that
must not change), `10 failed` (ac6, ac8's summary half), `57 failed, 21 passed` (ac3, ac4, ac7, ac8,
ac9 in core; the 21 are the "this build writes what the start commit wrote" checks, which are
trivially true of the start commit), `9 failed` (through the command).

Full suite, in three commands that together are the whole default selection:

| Paths | Result |
|---|---|
| `packages/debate_core/tests` | `3929 passed in 62.94s` |
| `packages/debate_cli/tests` | `529 passed in 42.50s` |
| `packages/debate_api/tests packages/debate_workers/tests tests` | `1287 passed, 1 skipped, 1 warning in 68.55s` |

These are from the final tree, on `dev` at `d01d4ac`. Before the sync the three were 3,903, 505
and 1,283 passed with 1 skipped.

Also clean: `ruff check .`, `ruff format --check .`, `pyright` (0 errors), `lint-imports` (12 kept),
`check_thin_handlers.py`, `validate_specs.py`, `docs_index.py --check-descriptions`,
`check_command_blocks.py`.

## Mutation results

87 mutants, each run alone against the tests that should catch it, with a fresh
`HYPOTHESIS_STORAGE_DIRECTORY` (no property test is in these selections). The script refused to
start on a dirty tree and restored each file from a saved copy.

| Area | Mutants | Caught on the first run |
|---|---|---|
| Code mapping: manifests (ac1) | 10 | 10 |
| Code mapping: archives (ac2) | 8 | 7 |
| Code mapping: the publisher (ac5) | 4 | 4 |
| fsync order (ac6) | 9 | 9 |
| An earlier finding in the summary and the exit (ac8) | 4 | 4 |
| Notification: retry against a person | 15 | 14, and 1 did not apply |
| Notification: with and without a hint | 6 | 6 |
| Notification: an earlier finding | 4 | 3 |
| Record compatibility: the record model | 5 | 5 |
| Record compatibility: where details go and in what order | 5 | 4 |
| Record compatibility: reading and content of details | 11 | 10, and 1 did not apply |
| `caselist runs` table | 6 | 6 |

82 caught on the first run. The other five:

| Mutant | First run | What I did |
|---|---|---|
| A complete archive's catch narrowed back to `DomainError` | Survived | A real gap. The only `OSError` a test gave that loop was the archive's own, which is translated before it arrives. Added a test with a disk-full error; caught on re-run |
| The details written before the record | Survived | A real gap: nothing asserted the order I documented. Added a test that kills the process as the details are appended; caught on re-run |
| Earlier findings read from stages that are not pending | Survived | Equivalent: only a pending stage ever records one. I removed the check rather than keep one mutation cannot tell from its absence |
| The stage's codes left out of the sentence | Did not apply | The formatter had re-wrapped the line. Fixed the mutant; caught |
| Details read back with another run's | Did not apply | Same cause; caught |

The runner first counted every catch as an error, because `pytest -x` exits `2`. I caught that on
the first batch and reclassified from each run's summary line. No mutant errored before running.

After the sync I ran the mutants again on the rebased code: 86 of 86 applied and were caught. The
87th is the equivalent one, which went with the check it mutated.

Coverage of the changed lines found 16 untested ones before the mutation runs (unreadable details,
details gone from the bucket, both length limits, a reader that refuses when called). Each now has
a test.

## After the sync onto `v1-e29-t07`

`scripts/task sync` stopped on three files, and I kept both sides in each:

* `caselist_sync.py`: `fix_for`'s docstring. The function keeps this task's public name and
  `v1-e29-t07`'s body, so a stage's hint for a refusal or a missing profile is the adapter's.
* `tests/smoke/test_caselist_pull.py`: both tasks appended checks. All 20 are there (15 and 5).
* `tests/smoke/README.md`: one row, both tasks' sentences.

Five tests then failed, all on wording `v1-e29-t07` changed, none on behaviour:

* **The notification's title in `v1-e29-t07`'s own test.** It asserted `caselist pull failed`.
  A missing profile is not retryable, so the title is `caselist pull failed: needs a person`. I
  changed that one assertion.
* **The grant hint.** Two of this task's tests quoted the sentence the sync used to write. They
  quote the adapter's now.
* **Three stored-record comparisons for the refused publish.** The adapter's refusal carries its
  fix, and a stage's reason quotes the refusal, so the record's reason grew. The shape did not.
  The stored scenario now raises the refusal the start commit's tests raised, so both builds
  record the same run and the comparison is like for like again. The adapter's refusal is a second
  scenario with its own test (see the evidence table).

Added: a notification test for a missing profile (`needs a person`, with the adapter's fix and no
path), and the two docstring sentences you asked for (Deviation 5).

One thing the sync broke that no test showed: a test module the scenarios import from now names
`StoreProfileNotConfigured`, so the generator of the stored records no longer imported under the
start commit's source. It now supplies that one name in memory. Run against the start commit's
source after the sync, it rewrote all 18 stored files and changed none. The README's command also
named `ccc5153`, the task's first start commit, which the rebase left on no branch; it names
`0a9c1e6` now, whose source is the same.

On a real installation a missing profile ends the run before any stage, with no record and no
notification, as `v1-e29-t07`'s runbook section says. The `needs a person` banner is for the case
its core test covers, where the bucket's adapter raises it during the publish.

## Files changed

* **`debate_core.application`**: `caselist/manifest.py` (the translation, `read_manifest_file`);
  `caselist/evidence_listing.py`, `caselist/parse_sources.py`, `caselist/removal_plan.py` (read
  through it); `caselist_sync.py` (import and publish containment, `_write_json`,
  `earlier_findings`, `fix_for` made public); `sync_runs.py` (details, their log and bucket
  reading, the notification); `errors.py` (the hint sentence moved here);
  `ports/notifier.py` (`Notification.hint`).
* **`debate_core.integrations.local`**: `refusals.py` (takes the hint from `errors`);
  `macos_notifier.py` (body limit 240 → 1500; title and subtitle unchanged).
* **`debate_cli`**: `exit_codes.py` (`codes_exit_as_a_retrieval_failure`); `container.py` (hands it
  to the monitor); `commands/caselist_runs.py` (the column, `details` in `--json`);
  `commands/caselist_pull.py` (`run_details` in the payload).
* **Tests**: five new files and the stored fixtures under
  `packages/debate_core/tests/application/caselist/`; additions to the CLI's
  `test_caselist_pull.py` and `test_caselist_runs.py`; five new smoke checks and one extended.
* **Docs**: `docs/runbooks/caselist-scheduled-sync.md` (new sections "What a notification says"
  and "The record, and the details beside it"; the exit-code table; three troubleshooting
  entries); `tests/smoke/README.md`.
* **Spec**: ac5 to ac9 added verbatim as the first commit; phase.

## Deviations from the spec

1. **ac3 and ac9: the codes and counts are beside the record, not in it.** The forbidden list
   ("a run record a build released before this task cannot read") and the criteria's words ("the
   run record carries") cannot both hold. I followed the forbidden list, as the kickoff said to.
   The criteria need amending to say "the run's details" if you accept this.
2. **ac1, "fails its stage with exit 3".** True when the refusal is met in the import stage. In
   the selection there is no stage to fail: the run stops on the same error and exits `3`, which
   is what `v1-e34-t13` does for an unreadable manifest directory, for the reason it gave. In
   retention the stage fails with the hint and the exit is `0`, because retention decides no exit.
3. **ac1 covers more than the two functions the description names.** Three other places read a
   local manifest by its path: `read_local_snapshots` (the selection, the publisher's plan and
   status), the parse pipeline's source listing, and the removal planner. An unreadable weekly
   manifest reached the first of these before either named function, so translating only the two
   would have left exit `70` in place. All five go through one reader now, each with a test.
4. **Earlier tasks' tests changed.** `v1-e34-t18`'s half-written-file test injects its fault at the
   opened stream, not `Path.write_text`; its assertions are unchanged. Four exact key sets of a
   stage gain `earlier_findings`. Six assertions on the title `caselist pull failed` now name the
   verdict. `v1-e34-t17`'s check that the caption is silent matches the caption's sentence, since
   the table now has a `Parse stage` column. After the sync, one more: `v1-e29-t07`'s
   missing-profile test asserted the old title, and now names `needs a person`.
5. **Two docstring sentences from `v1-e29-t07`'s Follow-up 3**, at your request with the sync. The
   module docstring's "Only an expired session is pending" paragraph and `_publish_stage`'s
   docstring each say that a profile missing from the AWS config fails the stage with
   `STORE_PROFILE_NOT_CONFIGURED` and is not pending. No behaviour changed.

## Decisions and assumptions

* **The retry rule stays in `debate_cli`.** `v1-e34-t13` put it there. The composition root hands
  the monitor `codes_exit_as_a_retrieval_failure`, which is `exit_code_for_failure_codes` asked as
  a question, so the notification and the exit code are one decision. A monitor built without it
  calls nothing transient. Core tests cannot import the CLI, so they carry the five codes by hand;
  a CLI test holds the real rule to the same five.
* **The verdict is in the title.** `caselist pull failed: will be retried` and
  `caselist pull failed: needs a person`. A banner shows the title whole and only the start of the
  body.
* **A failed parse stage gets neither wording.** The run exits `0`, and the next scheduled run
  does not retry a parse. Its banner carries the stage's hint and command.
* **A refusal says "will be retried" with its hint.** `STORE_ACCESS_DENIED` exits `3`, and ac7
  says both wordings hold with a hint present. The runbook says the hint is what to do first.
* **An earlier finding is named on the login banner only if the rule does not call it transient.**
  A `503` before the expiry is cured by the drain, so it adds no sentence. It is still recorded.
* **An unreadable archive is `UNREADABLE_ARCHIVE`, not `INTERNAL_ERROR`.** A download in the inbox
  whose bytes cannot be hashed already had that code. The translation is around the reader only,
  so a full disk under the blob store is still recorded by its class. Camp downloads keep
  `v1-e34-t12`'s behaviour; see Follow-up 5.
* **`earlier_findings` is added to every stage of the summary and the version stays `5`.** By
  `v1-e34-t07`'s rule for an additive key. You moved the version for `error_codes` because the exit
  is decided from them; nothing is decided from this. Say if you want `6`.
* **A hint is not put through `redact`.** That would remove `docs/runbooks/...`. Hints go through a
  backstop that removes registered secrets and absolute paths only.
* **`Notification` gains a `hint` field**, and the Mac's body limit goes from 240 to 1,500
  characters so the longest hint (a parse stage's two, about 400) is never cut.

## Operator follow-ups

Nothing has to be run for this task. One check is worth making after Wednesday's reinstall, because
no test may post a real banner: see how much of a long body Notification Centre shows.

**Operator command** (expected runtime ~2 s)
Where: your Mac, any directory

```bash
osascript -e 'on run argv' -e 'display notification (item 1 of argv) with title (item 2 of argv) subtitle (item 3 of argv)' -e 'end run' "Run 20261014T100000Z (prod): the publish stage failed on STORE_ACCESS_DENIED. The next scheduled run should retry it: every failure here is one a later run may not meet. What was captured is kept. This machine refused the blob directory: check that this user can read and write it, under the environment's data directory (storage.data_dir). It is a permission on this machine, not the AWS session. Fix: debate-research caselist pull --publish-pending" "caselist pull failed: will be retried" "debate-research caselist pull --publish-pending"
```

Success looks like: a banner whose title is the verdict and whose body, opened, shows the sentence
about the blob directory. If the body is cut before it, tell the PM; the whole text is always in
`caselist runs --json`.

The reinstall needs no migration. The details file appears with the new build's first run, and
runs recorded before it show `not recorded`.

## Follow-up work

1. **The report stage loses what it found when the session expires** (E34). The same defect as
   ac8, one stage over: drift found before the expiry is dropped, and `--publish-pending` only
   re-checks what it publishes itself.
2. **A record an older build publishes from the owed list goes up without its details** (E34).
   Nothing backfills them. It stops at the reinstall.
3. **`_PendingRecords.write` and the two log appends are not fsynced** (E34, p3). ac6 is
   `_write_json` only.
4. **`caselist runs` could show each run's codes and verdict** (E34). The details hold them.
5. **A camp download that cannot be read is still `INTERNAL_ERROR` by class** (E34), as
   `v1-e34-t12` left it, while a weekly is now `UNREADABLE_ARCHIVE`.
6. **A weekly manifest with a torn line still stops the run at the selection** (E34), exit `1`,
   recorded and notified but with no stage. ac5 fixed the publish stage's meeting of it.
7. **A run refused because another holds the lock notifies as "needs a person"** (E34). True by
   the rule, and probably wants words of its own.
8. **When no machine runs a build older than this one**, the record could be allowed to change
   again. `stored_run_records/README.md` says what goes with it.
9. **A refused publish's reason in the run record reads "[redacted] lists what each profile is
   granted"** (E34 or E29, p3). `v1-e29-t07` put the fix into the refusal's message, the stage's
   reason quotes the message, and the record's redaction takes `docs/runbooks/evidence-store.md`
   for a path. The stage's `hint` in the details is whole. Seen in the comparison above; not
   changed here, because it is the record's redaction and `v1-e29-t07`'s wording.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-11

**Notes:**

Accepted, with the phase `Succeeded`. I have amended ac3 and ac9 in this branch to say "the run's
details", so they now pass as written.

**Deviation 1 is the design I hoped for, and you proved it rather than assumed it.** My brief
offered a sidecar keyed by run id as the fallback. Every one of the following would have lost runs
silently on the build installed today:

* a new field on the record;
* a new field on each stage;
* a field written only when set;
* `schema_version` 2.

The eight-way table run through both builds' real readers is what shows it. So is the finding that
a skipped line also drops its run id from the list of records owed to the bucket. That consequence
makes "it only hides a row" the wrong reading. The rest of the design follows from it:

* **The details prefix sits beside `reports/sync-runs/`, not under it,** so an older reader's
  listing never meets them.
* **The write order differs on each side, and both directions are right.** Locally the record goes
  first. In the bucket the details go first, and the run stays owed as a whole.
* **"Not recorded" is told from "did not run".**

The stored fixtures are written by the older code, not by hand, and regenerating them changed no
byte.

**Rulings:**

* **Deviation 2, the selection stopping with exit 3:** accepted. It is `v1-e34-t13`'s treatment of
  an unreadable manifest directory.
* **Deviation 3, five readers through one, not two:** accepted, and better than the spec. Two would
  have left exit 70 in place.
* **Deviations 4 and 5:** accepted.
* **`earlier_findings` additive with the summary staying at version 5:** accepted. Nothing is
  decided from it.
* **The retry rule staying in `debate_cli`, handed to the monitor:** accepted. One decision for
  the exit and the banner.
* **"Will be retried" for a refusal that carries a hint:** accepted as the rule reads today. But
  a refusal needs a fix before the retry can succeed, and the banner should say so. Filed below.

**The mutation run:** 82 of 87 mutants were caught on the first run. The two real survivors became
tests: the disk-full error, and the kill between record and details. Removing the equivalent check
rather than keeping it is the right call.

**Follow-up work, filed by the PM in the next spec batch:**

* **One E34 p3 task for your 1, 3, 4, 5, 6, 7 and 9:**
  * the report stage loses what it found on expiry;
  * the remaining fsyncs;
  * codes and verdict in `caselist runs`;
  * a camp download's class;
  * a torn weekly manifest at the selection;
  * the lock refusal's words;
  * the redaction that eats the runbook pointer.

  Add to them the banner for a refusal that is retried but needs its fix first.
* **Your 2** ends at the reinstall, and **your 8** waits until no machine runs an older build.
  Neither gets a task now.
* **The E34 p2 task for `v1-e29-t07`'s silent failure** can start once this merges. Recording a
  refusal to start fits this design: the record as it is, plus details.

**Operator follow-up:** the banner check (`osascript`) joins the steps after Wednesday's
reinstall.

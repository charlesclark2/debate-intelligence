# Session report: v1-e34-t26-pending-work-and-banner-words

| | |
|---|---|
| Task | `v1-e34-t26-pending-work-and-banner-words` — A drifted snapshot is owed again, and the banner and run list say what is pending |
| Spec | [`plan_specs/v1/e34-caselist-sync/t26-pending-work-and-banner-words.yaml`](../../plan_specs/v1/e34-caselist-sync/t26-pending-work-and-banner-words.yaml) |
| Epic / release | `v1-e34-caselist-sync` / `v1.1` |
| Branch | `task/v1-e34-t26-pending-work-and-banner-words` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

All four items are done. Each new behaviour has a test that was run against unchanged code and
failed first.

* **Item 2.** The report stage now puts a snapshot back into the pending-work file when the bucket's
  manifest is the only thing that differs from this machine's. The next run, or `--publish-pending`,
  publishes it again. A snapshot that was already owed again for that, was republished, was
  confirmed, and then drifts again is not owed a third time. The run asks for a person instead,
  naming the snapshot by caselist and date. The guard reads only what the run log and the details
  already hold.
* **Item 1.** A report-only pending run's login banner now says what waits.
* **Item 3.** `caselist runs` shows `skipped` and `retry once fixed` beside the verdict.
* **Item 4.** This was already true on `dev`, done by `v1-e34-t23`'s Decision 2. It now has the test
  the spec asks for, and the test was shown to catch each wording it rules out.

The exit-code rule, the record, the details and the pending-work file's shape are all unchanged.
The agent's build `v1.1.0-dev.18` and `dev`'s readers read every file this build writes, and both
of their own `--publish-pending` runs published the new entry. Every criterion passed, so the Goal
is `Succeeded`.

**Look first at:**

* Decision 1, which drift is owed again;
* Decision 2, how "drifted again" is told from a first drift;
* Decision 5, the record's outcome, which this change would have moved without a fix;
* Deviation 1, item 1's banner, which tells you something the spec's wording did not expect.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `pending-and-banner` (Pending work and banner words) | Done | All four items, the runbook, t18's spec amendment, the smoke check, and the cross-build proof |

## Acceptance criteria

"The start commit" is `4dcdfb8`, this branch's first commit (`dev` at `55d0b4b` plus the phase
change). "The agent's build" is `v1.1.0-dev.18` (`0268cf7`), the build the PM's notes name. I
exported each one with `git archive` into the session's scratch directory and put it first on
`PYTHONPATH`. I did not open or run any installed build. "Red" means the test as first committed
(`55e0f0c`), run against unchanged source before the change it tests.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1**: (1) a report-only pending run's banner names what waits, by test shown failing first | PASS | `test_sync_runs_banners_say_what_waits.py`, item 1 section. **Red:** 3 failed on the old text, `… kept everything it fetched; 0 snapshot(s) and the run record wait to be published.` (once with the parse sentence after it). The two guards passed both ways: a pending publish still counts its snapshots, and a failed publish with one owed. **Green:** a pull against moto. Both weeks were published and the session expired at the report stage's first comparison. The banner reads `Run 20260916T060000Z (dev) kept everything it fetched; no snapshot waits to be published, only the run record. The report stage's check that the bucket holds what this run published was cut short; caselist pull --publish-pending does not make it again, and debate-research caselist status does, after the login.` See Deviation 1 for why the banner names `caselist status` |
| **ac2**: (2) a drifted snapshot is in the pending-work file after the report stage and published by the next run, by test shown failing first; t18's spec and the runbook say what is owed now | PASS | `test_caselist_sync_owes_a_drifted_manifest_again.py`. The comparison is the real one, against moto. Just before the report stage compares week one, the test writes other bytes over that week's manifest in the bucket. **Red:** `9 failed, 3 passed`, for example `owed(...) == []` where `['testcl26 2026-09-01']` was expected, the next run's publish `skipped` where `completed` was expected, and the reason missing `; owed again, …`. The 3 that passed are the "drift only" guards, which must pass both ways. **Green:** `21 passed` (12 scenarios and 9 cases of the history rule). After the first pull the file holds `testcl26 2026-09-01`, and so do the record's `pending_publish` and the summary's. The reason ends `; owed again, for the next run to publish: testcl26 2026-09-01`. The exit is still `0` and the record is `incomplete`. The second pull's publish is `completed`, its report says `1 snapshot(s) confirmed in the bucket`, the bucket's manifest equals this machine's byte for byte, and the file is gone. `--publish-pending` does the same. The other scenarios in the file cover: a drift found just before the session expired; the guard ("drifted again", not owed a third time, and the third pull publishes nothing); the guard looking past a run that waited for a login; a first drift of a snapshot that was owed for another reason; drift-only (a lost manifest, a source mismatch, a manifest mismatch beside a source mismatch); and a pending-work file that cannot be read, which is left byte for byte as it was. The nine history-rule cases use records written by hand. **The spec:** `t18-publish-owes-every-unpublished-snapshot.yaml` has the comment `# Amended by the PM, 2026-10-16 (v1-e34-t26): …`. **The runbook:** "The pending-work file" has the new section "A manifest that drifted is owed again, once", and "What a notification says" has both banners. `test_the_runbook_shows_…` holds the wordings to the runbook letter for letter |
| **ac3**: (3) `caselist runs` shows the banner's words in its table and JSON, by test | PASS | `test_caselist_runs.py::test_runs_shows_the_banners_own_words_beside_the_verdict`. **Red:** the table had no `person (skipped)`. **Green:** five runs. Lock: `│ SYNC_RUN_IN_PROGRESS │ person (skipped) │`. A refused publish with a hint, and a run stopped by a refusal with a hint: `│ STORE_ACCESS_DENIED │ retry (retry once fixed) │`. A retry with no hint: `│ retry │`. An older build's lock run with no details: `not recorded`. `--json` gives `banner` as `skipped`, `retry once fixed`, `retry once fixed`, `None`, `None`. In the core, `test_sync_runs_banners_say_what_waits.py` (item 3 section) checks `banner_words` against the banner titles `notifications_for` sends for the same runs. **Smoke:** `tests/smoke/test_caselist_runs.py` gained a pull the lock refused, run against this workspace's binary: `2 passed in 7.11s` |
| **ac4**: (4) a stage reason for an OSError names its class and errno, never its message, by test | PASS | `test_caselist_sync_names_an_os_error_by_class_and_errno.py`, `4 passed`. A parse stage raises `PermissionError(13, …, <data dir>/parsed/testcl26/Bayview Camp Aff - Lab Leak.docx)`, then `FileNotFoundError` (errno 2), an `OSError` with no errno, and a `RuntimeError`. The reasons end `testcl26: PermissionError (errno 13); the parsed store of testcl26 is not published`, then `(errno 2)`, then `OSError`, then `RuntimeError`, with no message, path or title in any reason or banner. The test passes on the start commit, because t23 made the change. **Shown failing** by putting each ruled-out wording back into `_failure`. The class alone: `2 failed, 2 passed` (the two errno cases fail; the no-errno cases read the same either way). The error's own text: `4 failed`, for example `testcl26: [Errno 13] Permission denied: 'the data directory/parsed/testcl26/Bayview Camp Aff - Lab Leak.docx'`, which leaks the camp file's title. The file was restored from a byte-checked copy after each run |
| Node `pending-and-banner`: `uv run pytest packages/debate_core/tests -k "caselist_sync or sync_runs"` | PASS | Run as written: `155 passed in 16.32s` (115 on the start commit). Every new test file's name contains `caselist_sync` or `sync_runs`, so this selector runs it |
| Forbidden: a change to v1-e34-t13's exit-code rule | PASS | `git diff 4dcdfb8 -- packages/debate_cli/src/debate_cli/exit_codes.py` → no output. The tests assert the exits are unchanged: `0` for a drift owed again and for a drift again (the report stage decides nothing), `1` for the lock refusal in the smoke check |
| Forbidden: a new field on the run record, or a record or details file an earlier build cannot read | PASS | No field was added to the record, the details or the pending-work file. `test_this_builds_record_model_is_the_one_both_older_builds_read_with` passes in the full suite. Each build read this build's files with its own readers ("Every build reads, and acts on, this build's files" below): exit 0, `refused or skipped: 0`, and the three outputs are identical but for the reader line. Each older build's own `--publish-pending` published the entry this build wrote |
| Forbidden: a path from the operator's machine in a record, notification or log | PASS | `assert_names_nothing_of_this_machine` runs on the drift tests and on ac4's tests, and ac4's tests also check every banner. The new reasons and banners name only caselist slugs, snapshot dates and commands |
| Mutants on the drift-owed rule, the drifted-again guard and each banner word | PASS | 27 mutants, every one caught. Table below. No property tests are involved; each run still set `HYPOTHESIS_STORAGE_DIRECTORY` to a fresh directory |
| Fakes, moto and a temporary HOME; never the operator's files | PASS | Every new test builds its installation under `tmp_path`, against moto. The 7 touched test files, run with `HOME` set to an empty scratch directory → `85 passed in 8.79s`. The only thing that appeared under that HOME was `.cache/uv`. I did not read the data directory, `~/.aws` or LaunchAgents |
| Default suite in four parts (`uv run --frozen pytest -n auto -m "not slow and not live" --part K/4`) | PASS | Part 1: `1974 passed` (55 s). Part 2: `1984 passed, 1 xfailed` (48 s). Part 3: `1984 passed, 1 skipped, 2 warnings` (47 s). Part 4: `1978 passed, 1 xfailed, 1 warning` (53 s). Each part ran under a hard stop, at load averages from 6 to 13. The warnings are pytest-socket's `getaddrinfo` notice (`v1-e34-t22`'s Follow-up 8) |
| ruff, pyright, lint-imports and the docs checks | PASS | `ruff format`, then `ruff check packages tests`: all passed. `uv run --frozen pyright`: `0 errors, 0 warnings` (project-wide, after the last format). `lint-imports`: `12 kept, 0 broken`. `check_thin_handlers.py`: 22 within 25. `check_command_blocks.py --base origin/dev`: 276 blocks, no `#`. `check_links.py`: 1631 links OK. `docs_index.py --check-descriptions`: 35 described. `validate_specs.py`: `OK: 362 files, 38 epics, 304 tasks, 20 releases` |

### Mutants

Each mutant was applied to a copy of the file, run against the tests named, and restored. The
restore was checked byte for byte. The driver was a scratch script (not committed), run in two
batches of 30 s and 38 s. "Caught by" is the first test that failed.

| Mutant | Caught by |
|---|---|
| Owe a manifest mismatch beside any other drift | `test_a_manifest_mismatch_beside_a_source_mismatch_is_not_owed` |
| Owe any drift at all | `test_a_manifest_the_bucket_lost_is_not_owed_by_the_report_stage` |
| Owe nothing (the start commit's behaviour) | `test_a_manifest_that_drifted_is_owed_again_and_the_next_run_publishes_it` |
| Do not write the file | the same |
| Write the file but do not list it in the record | the same |
| Write over a file that cannot be read | `test_a_drift_is_not_written_over_a_pending_work_file_that_cannot_be_read` |
| Owe only on a failed report, not on a drift found before an expiry | `test_a_drift_found_before_the_session_expired_is_owed_again` |
| Never refuse a third time | `test_a_manifest_that_drifts_again_after_its_republish_is_not_owed_a_third_time` |
| Refuse anything owed before, whatever the reason | `test_a_first_drift_of_a_snapshot_owed_for_another_reason_is_owed_again` |
| `run_pull` hands the service no history | `test_a_manifest_that_drifts_again_after_its_republish_is_not_owed_a_third_time` |
| History: a later run need not owe it | `test_a_later_run_that_did_not_owe_it_ends_it` |
| History: a run with no stages breaks the chain | `test_a_run_with_no_stages_is_passed_over` |
| History: any drift that includes a manifest counts | `test_a_drift_of_another_kind_beside_the_manifest_was_not_owed_for_drift` |
| History: the drift run need not have owed it | `test_a_drift_the_run_did_not_owe_was_not_owed_again` |
| Login banner: never says the check was cut short | `test_a_report_only_pending_run_says_the_run_record_waits_and_the_check_was_cut_short` |
| Login banner: says it even when the publish pends | `test_a_pending_publish_still_counts_its_snapshots_and_the_check_waits_with_them` |
| Login banner: the old `0 snapshot(s)` | `test_a_report_only_pending_run_…` |
| Notification: everything found counts as owed | `test_a_manifest_not_owed_again_needs_a_person_named_by_caselist_and_date` |
| Notification: nothing found counts as owed | the same |
| Words: never `skipped` | `test_a_run_the_lock_refused_says_skipped` |
| Words: `retry once fixed` without the retry | `test_a_retry_with_no_fix_and_a_person_have_no_words_of_their_own` |
| Words: never `retry once fixed` | `test_a_failed_stage_refused_with_a_fix_says_retry_once_fixed` |
| Words: a hint on any failed stage counts | `test_a_fix_on_a_stage_the_exit_is_not_decided_from_is_not_a_retry_once_fixed` |
| Words: a stopped run's hint ignored | `test_a_run_stopped_with_a_fix_says_retry_once_fixed` |
| Runs table: no words in the cell | `test_runs_shows_the_banners_own_words_beside_the_verdict` |
| Runs JSON: no `banner` | the same |
| Record outcome: `publish_pending` whenever something is owed (the code before Decision 5) | `test_a_manifest_that_drifted_is_owed_again_…`, red in the tree before the fix: `assert <SyncRunOutcome…publish_pending'> == 'incomplete'` |

The six banner-word tests in the core were also red on `AttributeError` before `banner_words`
existed. That red shows only that the function was missing, so I count the mutants above as
their proof.

### Every build reads, and acts on, this build's files

`write_drift_owed_again_files.py` is not collected and is run by its path. It writes what this
build leaves after two scenarios, each run through the real run monitor against moto: a drift owed
again, and a drift again after the republish. For each scenario it writes the run log, the details,
the pending-work file and every object under `reports/`. `read_sync_run_files.py` is t23's reader
script, now extended to read the pending-work file with the build's own `PendingWork`.
`check_an_older_build_publishes_a_manifest_owed_again.py` is not collected either. It runs the agent
cycle with the source in front of it: pull and publish two weeks; overwrite week one's manifest in
the bucket; put this build's pending-work file in place; run that source's own `--publish-pending`.
Run from the worktree, with `S` the session's scratch directory and `S/start` and `S/agent` the two
exported sources:

```bash
WRITE_DRIFT_OWED_AGAIN_FILES="${S}/files/this-build" uv run --frozen pytest packages/debate_core/tests/application/caselist/write_drift_owed_again_files.py -p no:cacheprovider --no-cov -n 0 -q
uv run --frozen python -I packages/debate_core/tests/application/caselist/read_sync_run_files.py "${S}/files/this-build" this-build
PYTHONPATH="${S}/start/packages/debate_core/src" uv run --frozen python packages/debate_core/tests/application/caselist/read_sync_run_files.py "${S}/files/this-build" start-commit
PYTHONPATH="${S}/agent/packages/debate_core/src" uv run --frozen python packages/debate_core/tests/application/caselist/read_sync_run_files.py "${S}/files/this-build" agent-build
CHECK_AN_OLDER_BUILD_PUBLISHES="${S}/files/this-build/drift_owed_again/caselist-sync-pending.json" PYTHONPATH="${S}/agent/packages/debate_core/src:${S}/agent/packages/debate_cli/src" uv run --frozen pytest packages/debate_core/tests/application/caselist/check_an_older_build_publishes_a_manifest_owed_again.py -p no:cacheprovider --no-cov -n 0 -q -s
```

The last command was also run with `S/start` and with no `PYTHONPATH`. All three reads exited 0.
Past the first line, the three outputs are byte for byte the same. The agent build's:

```text
reader: agent-build (sync_runs from …/scratchpad/agent)
files written by: this-build
drift_owed_again:
  record 20260916T060000Z: incomplete; select completed, download completed, import completed, publish completed, parse skipped, landscape skipped, report failed, retention completed
    error_class None
  details 20260916T060000Z: read, failure_codes [], 1 stage(s)
  pending-work file: ['testcl26 2026-09-01']
  record 20260916T060000Z pending_publish: ['testcl26 2026-09-01']
  bucket reports/sync-run-details/2026/20260916T060000Z.json: read as SyncRunDetails
  bucket reports/sync-runs/2026/20260916T060000Z.json: read as SyncRunRecord
drifted_again:
  record 20260916T060000Z: incomplete; … report failed, retention completed
  record 20260923T060000Z: incomplete; select completed, download skipped, import skipped, publish completed, parse skipped, landscape skipped, report failed, retention completed
  details 20260916T060000Z: read, failure_codes [], 1 stage(s)
  details 20260923T060000Z: read, failure_codes [], 1 stage(s)
  record 20260916T060000Z pending_publish: ['testcl26 2026-09-01']
  bucket …: read as SyncRunDetails / read as SyncRunRecord, four objects
refused or skipped: 0
```

In the second scenario there is no pending-work file after the second run, and that run's record
lists nothing as owed: the guard held. The check printed the same for the agent's build and the
start commit, apart from the reader line (`agent`, `start`):

```text
reader: the debate_core source at agent
its own pull: publish completed
the bucket's week one manifest, drifted: same as this machine's: False
placed: caselist-sync-pending.json, 96 bytes
read by this source: [('testcl26', '2026-09-01')]
--publish-pending: publish completed (0 object(s) uploaded across 1 snapshot(s))
--publish-pending: report completed (1 snapshot(s) confirmed in the bucket)
the bucket's week one manifest now the same as this machine's: True
pending-work file left: False
1 passed
```

## Files changed

* **`debate_core.application.caselist_sync`**:
  * `_owe_drifted_manifests_again`, called on every way out of the report stage that found drift;
  * `owed_for_drift` on `run`, on `publish_pending` and on the tally, which `run_pull` reads from the
    monitor;
  * the module docstring's "What the pending-work file holds".
* **`debate_core.application.sync_runs`**:
  * `snapshots_owed_again_for_drift` and the monitor method that reads it;
  * `banner_words`, with `_a_fix_comes_first` shared with `notifications_for`;
  * the login banner's account of what waits;
  * the owed-again and drifted-again banners (`DRIFTED_AGAIN_TITLE`; `MANIFEST_PUBLISHED_AGAIN`
    reworded);
  * `_outcome_of` decides on the publish stage itself (Decision 5).
* **`debate_cli.commands.caselist_runs`**: the banner's words in the `Verdict` cell and as `banner`
  in `--json`.
* **Tests in `packages/debate_core/tests/application/caselist/`**:
  * three new test files;
  * t23's report-stage and banner tests updated to the amended rule;
  * the cross-build writer and checker, and the extended reader.
* **`packages/debate_cli/tests/commands/test_caselist_runs.py`**: the banner-words test.
* **`tests/smoke/test_caselist_runs.py`**: `banner` is `null` on an ordinary run, and a pull the lock
  refused shows `person (skipped)` (Deviation 2).
* **`docs/runbooks/caselist-scheduled-sync.md`**:
  * the `caselist runs` columns;
  * the `pending_publish` row;
  * the notification table, and the owed-again, drifted-again and what-waits paragraphs;
  * "The pending-work file";
  * a troubleshooting entry for `pending_publish` with a completed publish.
* **`plan_specs/…/t18-publish-owes-every-unpublished-snapshot.yaml`**: the PM's amendment, as a
  comment (Deviation 2).

`publish_service.py` is untouched (`git diff 4dcdfb8 -- …/publish_service.py` is empty), so this
task does not collide with `v1-e30-t22`.

## Deviations from the spec

1. **Item 1: the confirmation does not wait. Nothing makes it again.** The spec says only the
   confirmation waits. In fact `--publish-pending` and the next scheduled run never redo the report
   stage's check for a run whose publish completed. Each one compares only what it publishes
   itself, and nothing of that run is owed. So the banner says the run record waits, that the check
   was cut short, that `--publish-pending` does not make it again, and that `caselist status` does.
   The alternative was to make `--publish-pending` compare again what an earlier run published.
   That is a behaviour change beyond item 1, so I did not make it. See Follow-up work 1.
2. **Two files outside `constraints.packages`.**
   * `plan_specs/…/t18-…yaml`: the PM's notes ask for the amendment there.
   * `tests/smoke/test_caselist_runs.py`: `plan_specs/README.md` asks for a smoke check when a
     user-facing surface changes, and `caselist runs --json` gained `banner`.

## Decisions and assumptions

1. **Which drift is owed again: a manifest mismatch with nothing else beside it.** That means drift
   kinds exactly `["manifest"]`. It is the one drift the publisher is known to clear, and the one
   t23 already announced as cleared by publishing again.
   * A manifest the bucket lacks is `missing`, so it is not owed. The PM said not to double-count
     it.
   * A source with other bytes needs a person, alone or beside a manifest mismatch. Owing it would
     turn a report finding into a failed publish, and exit `1`, every week until someone fixed it.
   * One snapshot's manifest mismatch is owed even when another snapshot in the same run has a
     source mismatch. That run's banner is still the generic failed-stage one, for the source.
2. **"Drifted again" comes from the run log and the details as they are.** A snapshot counts as owed
   again for drift if two things hold:
   * some run's report stage found its manifest, and nothing else, differing (details `drift`, kind
     `manifest` alone), and that run's record lists it in `pending_publish`;
   * every later run's record lists it too.

   A run with no stages is passed over: the lock, a refused start, or an error that escaped all
   touched nothing. A run whose details are missing says nothing about drift, so in that one case
   the guard is one run late (the snapshot is owed a third time) and the next run stops it. Nothing
   is added to any file. `run_pull` reads the history inside the monitor and hands it to the run,
   because the service cannot import `sync_runs`.
3. **What happens after the guard fires.** The snapshot is left out of the file. The report stage's
   reason ends `drifted again after it was owed again and published, so not owed a third time; a
   person should look:` with the snapshots. The banner is `caselist pull: a manifest drifted again`,
   and its command is `caselist status --caselist <slug>`. The notification tells "owed again"
   apart from "not" by whether the record lists the snapshot as owed. A pending-work file that
   could not be read also leaves it unlisted, and that case needs a person too.
4. **The owed-again banner keeps its title.** Its sentence now says the next scheduled run
   publishes the snapshot again. Its command is `caselist pull --publish-pending`, which drains the
   file now. Before, the command was `caselist publish --caselist <slug>`, which would have left the
   entry for the next run to republish anyway.
5. **The record's outcome does not move.** `_outcome_of` called a run `publish_pending` ("waits for
   an AWS login") whenever `pending_publish` was non-empty. Before this task that could happen only
   with the publish stage pending: a failed publish is `failed` first, and a completed one leaves
   nothing owed. Once the report stage could owe again, a drift-owed run became `publish_pending`. I
   found that in the cross-build output. It now decides on the publish stage, so every run keeps the
   outcome it had before, and a drift-owed run is `incomplete`. The runbook's troubleshooting
   section covers `pending_publish` with a completed publish.
6. **The banner's words sit in the verdict cell.** The cell reads `person (skipped)` and
   `retry (retry once fixed)`, which keeps t23's two-valued verdict. `--json` gets a separate
   `banner` key. A run with no details has no known words, because the banner an older build showed
   was its own. The words are decided by `banner_words`, which uses `_a_fix_comes_first`, the same
   helper the banner titles now use, so the two cannot drift apart.
7. **The check sentence ends with words, not a command.** It reads `…, and debate-research
   caselist status does, after the login.` A sentence that may follow it would otherwise run into
   the command.
8. **What I did not touch.** The publisher's upload rule, the exit codes, the record, the details
   schema, and the pending-work file's shape.

## Operator follow-ups

None. No command here needs credentials or runs longer than about two minutes.

For information: the weekly agent keeps the old behaviour until it is reinstalled. The cross-build
check shows that the agent publishes any entry this build writes after the reinstall, and that it
reads this build's run files.

## Follow-up work

1. **Nothing redoes a report-stage check cut short by an expired session** (E34, p3). See Deviation 1.
   `--publish-pending` could also compare the snapshots the newest run published but did not
   confirm. Their names are in the publish stage's work, not in any file today.
2. **The publish stage's count leaves out a manifest it uploads** (E34, p3). A republish that uploads
   only the manifest says `0 object(s) uploaded across 1 snapshot(s)`. The test in
   `test_caselist_sync_owes_a_drifted_manifest_again.py` records this, with a comment.
3. **A report-only pending run's record outcome is still `completed`** (E34, p3). This is
   pre-existing (t23's Follow-up 2). Item 1 fixed the banner and left the outcome alone.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

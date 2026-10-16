# Session report: v1-e34-t23-sync-loose-ends

| | |
|---|---|
| Task | `v1-e34-t23-sync-loose-ends` — Loose ends in the weekly sync's findings, records and notifications |
| Spec | [`plan_specs/v1/e34-caselist-sync/t23-sync-loose-ends.yaml`](../../plan_specs/v1/e34-caselist-sync/t23-sync-loose-ends.yaml) |
| Epic / release | `v1-e34-caselist-sync` / `v1.1` |
| Branch | `task/v1-e34-t23-sync-loose-ends` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

All fourteen loose ends are fixed, each by a test written first and shown failing. The report stage
now keeps what it found before a session expired, and each finding carries its kind. A run whose
only drift is a manifest mismatch is announced with `caselist publish`. A camp download that cannot
be read is `UNREADABLE_ARCHIVE`. A torn weekly manifest fails the stage that reads it, not the
selection. The run log, the run details and the owed-records file are fsynced. `caselist runs` shows
each run's codes and verdict. The lock refusal, and a refusal that a retry gets past only once its
fix is made, have banners of their own, and no banner names an exception class. A banner's fix
command is now the first thing in its body, so the limits observed on 2026-10-15 show it whole.
A held path's refusals are counted by request. The download allowance's two guards are tested. A
complete archive's snapshot name and a runbook path survive the record's redaction.

The exit-code rule is untouched (`exit_codes.py` has no diff). The record is unchanged, and this
build's records and details are read without a skip by the agent's build `v0.1.0-dev.122`, by the
start commit, and by this build. Every criterion passed, so the Goal is `Succeeded`. The operator
follow-up below (the banner check on the Mac) is not a criterion. **Look first at** Decisions 3, 4
and 7: how item 11's "retryable" is worded, what the selection still reads, and the five banners'
words.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `sync-loose-ends`: Sync loose ends fixed | Done | Items 1–14 in eight commits, one per theme. Its criterion passes: `499 passed in 17.20s` |

## Acceptance criteria

"The start commit" is `837edf5`, this branch's first commit (`dev` at `fea1807` plus the status
change). "The agent's build" is `v0.1.0-dev.122` (`d87febd`), which the PM's notes name. Each was
exported with `git archive` into the session's scratch directory and put first on `PYTHONPATH`. I
did not open or run any installed build. "Red" means the test as finally committed, or as first
written, run against source that did not yet have the fix. Each red run below was made before the
change it tests.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1**: (1), (4), (5) and (7) each have a test shown failing first, and are fixed | PASS | **(1)** `test_sync_report_stage_keeps_what_it_found_and_its_kind.py`. Red in the tree before the change: `6 failed`. The source-mismatch test failed on `assert [] == ['CASELIST_DRIFT']`: the earlier finding was lost. The others failed on `KeyError: 'drift'`. Green: `6 passed`. A source mismatch found at week one, with the session expiring at week two, leaves the stage `pending` with `earlier_findings == ["CASELIST_DRIFT"]` and the finding's kind in the details. The login banner says "A person should look as well…". **(4)** `test_pull_fails_a_stage_not_the_run_on_what_it_cannot_read.py::…camp_download_that_cannot_be_read…`, a single document and a release zip. Red: `assert ['INTERNAL_ERROR'] == ['UNREADABLE_ARCHIVE']`, twice. Green, by hand: `openev-512 (sha256 …): the download cannot be read as an archive: the file in the inbox could not be read (PermissionError (errno 13))`, with the title absent. **(5)** The same file, two tests. Red: `UnreadableManifest: manifests/testcl26/2026-09-01.jsonl line 9 is not a usable manifest row` raised out of `run()`, twice. Green: the selection `completed`, week one not fetched again, and the publish stage failed on `UNREADABLE_MANIFEST` (week one still owed, week two confirmed). With the composition root's first-seen measurement, the import of week two fails on it instead. A guard keeps `v1-e34-t19`'s rule that a manifest this user cannot open still stops the selection. **(7)** `test_sync_run_record_redaction_keeps_what_is_not_a_path.py::test_a_refused_publish_keeps_the_runbook_its_reason_points_at`. Red: the reason ended `… [redacted] lists what each profile is granted`. Green: `docs/runbooks/evidence-store.md lists what each profile is granted`. **The final files against the start commit's source**: `27 failed, 35 passed, 1 error` (the banner file cannot be collected there; it imports `DriftFinding`). The 35 that pass are guards for what must not change: the cases that must still be redacted, the allowance tests (see ac8), the refusal that still stops the selection, and the earlier durability cases |
| **ac2**: every state-file write and log append is fsynced as `v1-e34-t19`'s ac6 does, by a test recording the order of calls | PASS | `test_sync_state_files_are_written_durably.py`, which now has 13 tests. Red: `7 failed, 6 passed`, each failure a missing fsync. The owed-records file: `['rename …']` where three calls were expected. Each append: `[] == ['fsync a file of N bytes', 'fsync its directory', …]`. The fsync-failure tests: `DID NOT RAISE OSError`. Each removal: the directory not fsynced after the name went. Green: `13 passed`. The owed-records file now goes through `write_state_file` (the renamed `_write_json`), with byte-identical content. Each append is one `O_APPEND` write, then an fsync of the file, then of its directory. A state file removed because nothing is owed has its directory fsynced |
| **ac3**: `caselist runs` shows each run's codes and verdict, retry or person, from the details, and `not recorded` for a run with none | PASS | `packages/debate_cli/tests/commands/test_caselist_runs.py::test_runs_shows_each_runs_codes_and_verdict_from_its_details`. Red: `'Failed on' in …` false. Green: `│ failed │ STORE_UNAVAILABLE │ retry │`, `│ failed │ UNREADABLE_ARCHIVE, STORE_UNAVAILABLE │ person │`, `│ completed │ none │ none │`, `│ failed │ not recorded │ not recorded │`. `--json` gives `verdict` as `retry`, `person`, `None`, `None`. The verdict uses `codes_exit_as_a_retrieval_failure`, the rule the exit code and the banner use. Smoke: `tests/smoke/test_caselist_runs.py` against the installed binary → `1 passed in 5.17s` |
| **ac4**: a lock refusal and a refusal that needs its fix first each have a banner wording of their own, shown in the runbook's section on what a notification says, by test | PASS | `test_sync_banner_says_what_happened_and_shows_its_fix_whole.py`. Red in the tree, before the change: `18 failed, 4 passed`. Examples: the lock run titled `needs a person`; the refusal titled `will be retried`; `module 'sync_runs' has no attribute 'RETRIED_AFTER_ITS_FIX_TITLE'`. Green: `22 passed`. Lock: title `caselist pull skipped: another was running`, message `Run … (dev): Another caselist pull held the run lock, so this one did nothing. That run records and announces its own outcome.`, command `debate-research caselist runs`, exit still `1`. Fix first: title `caselist pull failed: retried once fixed`, sentence `The next scheduled run retries it, and is refused the same way until the fix that follows is made.`, exit still `3`. `test_the_runbook_shows_the_lock_and_the_fix_first_wordings_and_they_are_the_ones_used` holds the runbook's section to both, letter for letter, with a quoted example of each |
| **ac5**: no banner names an exception class, and the fix command fits where the banner shows it whole, by a test applying the observed limits | PASS | Same file. `as_the_banner_shows` cuts the subtitle at 40 characters, wraps the body at the spaces into 45-character lines, and keeps ten of them. Every notification of the ten `run_record_scenarios` and every kind built at its longest must show its command whole in those ten lines: the longest hints together, the login banner with both added sentences and the prod login command, the backlog, held uploads and a manifest to publish again. No word of any banner may be the name of a `debate_core` exception class or an `OSError` subclass. `test_the_banner_the_operator_saw_hid_its_command_and_now_shows_it` rebuilds the banner of 2026-10-15 and checks the old layout first. The old subtitle is exactly `debate-research caselist pull --publish-` and the old ten lines miss the command. The new layout shows it. Words in place of a class: `stopped: the AWS profile it publishes with is not one this machine's AWS config defines.`, `stopped: an error nobody modelled, most likely a bug.`, `stopped: this machine or the bucket refused it.`, and for a code with no words, `stopped: an error recorded as <CODE>.` |
| **ac6**: a pull that met a held path says how many uploads the hold refused, by request id, in the details and the notification, with no path and no new record field | PASS | `test_sync_held_path_refusals_are_counted_by_request.py`. Red: `KeyError: 'held_by_request'`, twice. The record guard passed, as it should. Green: `3 passed`. With `v1-e30-t21`'s Bayview world: summary `held_by_request == {"RM-2026-01": 1}`, the import stage's reason `… 1 upload(s) refused at a path a removal holds (RM-2026-01: 1)`, and the same count in the details. One banner, `caselist pull: uploads held by a removal`: `Run … (dev): the import refused 1 upload(s) at a path a removal holds, by request: RM-2026-01 1. Nothing of them was stored.`, command `debate-research caselist status`. The banner names no path, school, file or digest. The record's keys equal `SyncRunRecord.model_fields` |
| **ac7**: the report stage's finding carries the mismatch kind in the details, and a run whose only drift is a manifest mismatch is announced as retryable with the publish command | PASS | `test_sync_report_stage_keeps_what_it_found_and_its_kind.py`. Red: `KeyError: 'drift'`. Green: `drift == [{"caselist": "testcl26", "snapshot": "2026-09-01", "kinds": ["manifest"]}]`, in the summary and in the details. The reason reads `not in sync: testcl26 2026-09-01 (manifest mismatch)`. The banner is `caselist pull: publish a manifest again`, with the command `debate-research caselist publish --caselist testcl26` and `Publishing again should clear it: … Nothing here needs a person.` The exit stays `0`. A source mismatch, or a manifest mismatch beside one, keeps `caselist pull finished with a failed stage` (two tests). Found before an expiry, the login banner names the publish instead of a person. See Decision 3 on "retryable" |
| **ac8**: six starts against a limit of five leave 0, never negative, in the decision and the summary; the service's `min()` removed or tested directly, and the report says which | PASS | `test_sync_download_allowance_is_never_negative.py`, `6 passed`. Six starts: `remaining_at == 0`, the plan's `bulk_downloads_allowed == 0` and both weeks `OVER_DAILY_BUDGET`, `allowance_after_weeklies == 0`. In the summary: `bulk_downloads_allowed == 0` and the select stage's reason `6 of 5 bulk download(s) spent … 0 left`, with nothing fetched. Five spent with the setting lowered to three gives 0. **The `min()` is kept and tested** by building the service directly with six a day, which plans five (Decision 1). These guards existed, so the tests pass on the start commit too. They bite: with `max(…, 0)` removed, `4 failed` (`assert -1 == 0`, `assert -2 == 0`); with the `min()` removed, `1 failed`. Each mutant was restored with `git checkout --` of the committed file |
| **ac9**: a snapshot name and a runbook path survive the redaction, a real path is still redacted, by a test shown failing first | PASS | `test_sync_run_record_redaction_keeps_what_is_not_a_path.py`. Red in the tree: `6 failed, 9 passed`. Each keep case failed: `full/2026-09-15:`, a snapshot before a comma, the runbook, the runbook in brackets, through `record_for_summary`, and the refused publish. Green: `15 passed`. Still redacted: `/Users/…/inbox/….zip`, `~/.debate-research/…`, a quoted disclosure path with spaces, an unquoted one, a runbook's name inside a path on this machine, `full/<date>` inside one, `docs/../../Users/…`, `full/2026-09-15/School/…` and `docs/runbooks/x.md.docx`. The allowance is `[(\[]?(?:full/\d{4}-\d{2}-\d{2}\|docs/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+\.md)[)\]:;,.]*`, matched against the whole token |
| Node `sync-loose-ends`: `uv run pytest packages/debate_core/tests/application -k "pull or sync or runs"` | PASS | Run as written: `499 passed in 17.20s`. The new test files are named `test_sync_…` or `test_pull_…` so that this selector runs them |
| No change to `v1-e34-t13`'s exit-code rule (forbidden) | PASS | `git diff 837edf5 -- packages/debate_cli/src/debate_cli/exit_codes.py` → 0 lines. Every new wording is chosen by the same rule (`may_succeed_on_retry`) from the same codes. The tests assert the exit statuses are unchanged: lock `1`, refusal `3`, manifest drift `0` |
| No new record field, and no record or details file an earlier build cannot read (forbidden) | PASS | `test_this_builds_record_model_is_the_one_both_older_builds_read_with` passes, schema for schema. Read by each build: see "Every build reads this build's run files" below. Three reads, each exit 0, `refused or skipped: 0`, and the three outputs are identical but for the reader line |
| No path from the operator's machine in a record, notification or log (forbidden) | PASS | `assert_names_nothing_of_this_machine` on every new pull test, `assert_names_no_path` on the notification tests, the redaction cases above, and ac6's forbidden list |
| Tests use fakes and a temporary HOME, and never read the real `~/.debate-research` | PASS | Every new test builds its installation under `tmp_path`. The 22 new and changed test files, run with `HOME` set to an empty scratch directory → `473 passed in 44.36s` (a library left an empty `.cache` there). Nothing here reads the operator's data directory or LaunchAgents |
| Full suite, four parts (`uv run --frozen pytest -n auto -m "not slow and not live" --part K/4`) | PASS | `1825 passed` (66 s); `1831 passed, 1 xfailed` (66 s); `1836 passed, 1 skipped, 2 warnings` (54 s); `1830 passed, 1 xfailed, 1 warning` (73 s). Each part ran under a hard stop at load averages 4 to 8. The warnings are pytest-socket's `getaddrinfo` notice, which `v1-e34-t22` filed as its Follow-up 8 |
| Lint, types, contracts, docs | PASS | `ruff check packages tests`: all passed. `ruff format --check`: 486 files formatted. `uv run --frozen pyright`: `0 errors` (project-wide, 12 s; the 7 errors in this task's tests were fixed first). `lint-imports`: `12 kept, 0 broken`. `check_thin_handlers.py`: 21 within 25. `docs_index.py --check-descriptions`: 34 described. `check_command_blocks.py --base origin/dev`: 262 blocks in 118 files, no `#`. `validate_specs.py`: `OK: 355 files, 38 epics, 297 tasks, 20 releases` |

### Every build reads this build's run files

`write_sync_loose_ends_files.py` (run by path; not collected) writes what this build leaves after
seven pulls through the real run monitor. For each: the run log, the run's details, the
owed-records file when there is one, and every object under `reports/` in the bucket. The pulls are
the report stage pending with its drift, a manifest mismatch alone, an upload a hold refused, a run
refused by the lock, a refused publish whose reason keeps its runbook, a complete archive imported
(`full/2026-09-01` in the import reason), and a run refused before its bucket could be built (its
record owed). `read_sync_run_files.py` is a plain script that imports nothing from the test suite.
It reads each set with the build's own `SyncRunLog` (which skips and logs a line it cannot
validate), `SyncRunDetailsLog`, owed-records reader, and record and details models. Run from the
worktree, with `S` the session's scratch directory, where `S/start` and `S/agent` hold the two
exported sources:

```bash
WRITE_SYNC_LOOSE_ENDS_FILES="${S}/files/this-build" uv run --frozen pytest packages/debate_core/tests/application/caselist/write_sync_loose_ends_files.py -p no:cacheprovider --no-cov -n 0 -q
uv run --frozen python -I packages/debate_core/tests/application/caselist/read_sync_run_files.py "${S}/files/this-build" this-build
PYTHONPATH="${S}/start/packages/debate_core/src" uv run --frozen python packages/debate_core/tests/application/caselist/read_sync_run_files.py "${S}/files/this-build" start-commit
PYTHONPATH="${S}/agent/packages/debate_core/src" uv run --frozen python packages/debate_core/tests/application/caselist/read_sync_run_files.py "${S}/files/this-build" agent-build
```

All three exited 0. Each printed `sync_runs from` its own tree (`…/scratchpad/agent`,
`…/scratchpad/start`, the worktree). Past that first line the three outputs are byte for byte the
same. The agent build's:

```text
reader: agent-build (sync_runs from …/scratchpad/agent)
files written by: this-build
bucket_not_built:
  record 20260916T060000Z: failed; no stage
    error_class StoreProfileNotConfigured
  details 20260916T060000Z: read, failure_codes ['STORE_PROFILE_NOT_CONFIGURED'], 0 stage(s)
  records still owed: ['20260916T060000Z']
complete_archive_imported:
  record 20260916T060000Z: completed; select completed, download completed, import completed, publish completed, parse skipped, landscape skipped, report completed, retention completed
    error_class None
    import reason: 2 snapshot(s) imported, 4 new file(s) stored; complete archive testcl26 full/2026-09-01: 0 withdrawn, 0 superseded against 0 earlier snapshot(s)
    retention reason: 2 file(s) removed, 9916 bytes freed: testcl26 full/2026-09-01, testcl26 2026-09-01
  details 20260916T060000Z: read, failure_codes [], 0 stage(s)
  bucket reports/sync-run-details/2026/20260916T060000Z.json: read as SyncRunDetails
  bucket reports/sync-runs/2026/20260916T060000Z.json: read as SyncRunRecord
held_upload_refused:
  record 20260916T060000Z: completed; …
    import reason: 1 snapshot(s) imported, 1 new file(s) stored; 1 upload(s) refused at a path a removal holds (RM-2026-01: 1)
  details 20260916T060000Z: read, failure_codes [], 0 stage(s)
  bucket …: read as SyncRunDetails / read as SyncRunRecord
lock_held_by_another_run:
  record 20260916T060000Z: failed; no stage
    error_class SyncRunInProgress
  details 20260916T060000Z: read, failure_codes ['SYNC_RUN_IN_PROGRESS'], 0 stage(s)
  bucket …: read as SyncRunDetails / read as SyncRunRecord
manifest_mismatch_alone:
  record 20260916T060000Z: incomplete; … report failed, retention completed
  details 20260916T060000Z: read, failure_codes [], 1 stage(s)
  bucket …: read as SyncRunDetails / read as SyncRunRecord
publish_refused_with_its_runbook:
  record 20260916T060000Z: failed; … publish failed, …
    publish reason: 0 object(s) published; 1 snapshot(s) left for a later run: not allowed to ListObjectsV2 [redacted] the AWS profile debate-dev-evidence is signed in and lacks a grant for this; it is not an expired session, and logging in again changes nothing. docs/runbooks/evidence-store.md lists what each profile is granted
  details 20260916T060000Z: read, failure_codes ['STORE_ACCESS_DENIED'], 1 stage(s)
  bucket …: read as SyncRunDetails / read as SyncRunRecord
report_drift_before_an_expiry:
  record 20260916T060000Z: completed; … report pending, retention completed
  details 20260916T060000Z: read, failure_codes [], 1 stage(s)
  bucket …: read as SyncRunDetails / read as SyncRunRecord
refused or skipped: 0
```

(Shortened here with `…` where the lines repeat. The scratch files hold every line.) The agent's
build reads the details' new keys, `drift` on a stage and `held_by_request`, by passing over them:
its `StageDetails` and `SyncRunDetails` are `extra="ignore"`. The `[redacted]` that remains in the
refused publish's reason is the bucket's key in `not allowed to ListObjectsV2 <key>`, which the
redaction takes as it always did.

## Files changed

* **`debate_core.application`**
  * `caselist_sync.py`:
    * `DriftKind` and `SnapshotDrift`, and `StageRecord.drift`. The report stage keeps findings
      through an expiry, with their kind (items 1 and 11).
    * `held_by_request` on the tally and the summary (item 10).
    * `_openev_entries` reads through `_entries_of`; one wording, `reported_error_message`, for every
      non-domain error in a stage's reason (item 4).
    * The selection learns the newest week held from the manifest's name (item 5).
    * `write_state_file` (renamed from `_write_json`), `append_state_line` and `remove_state_file`
      (item 2).
  * `sync_runs.py`:
    * `redact` keeps `full/<date>` and a runbook (items 7 and 14).
    * Durable appends and the owed-records file (item 2).
    * `DriftFinding`, `StageDetails.drift` and `SyncRunDetails.held_by_request` (items 10 and 11).
    * Five wordings: lock, fix first, words for a stopped run, publish again, and held uploads.
      Every notification's subtitle is its run (items 6, 8, 9, 10, 11, 12).
  * `ports/notifier.py`: `Notification.subtitle` and `Notification.body`, which puts the fix first
    (item 12). `text` is unchanged.
* **`debate_core.integrations.local`**: `macos_notifier.py` sends `body` and `subtitle` (item 12).
* **`debate_cli`**: `commands/caselist_runs.py`, the `Failed on` and `Verdict` columns and
  `verdict` in `--json` (item 3).
* **Tests, new**:
  * The seven files above.
  * `write_sync_loose_ends_files.py` and `read_sync_run_files.py`, the cross-build evidence.
* **Tests, extended**: `test_inbox_retention.Installation.sync` takes `bulk_downloads_per_day`,
  `measure_first_seen` and `status`.
* **Tests, changed because the spec changed the behaviour they pinned** (each expectation written
  again by hand):
  * the new `drift` and `held_by_request` keys in eight whole-dict expectations;
  * the runbook kept in the refusal's recorded message (core and CLI);
  * `stopped with <Class>` replaced by words (four tests, two of them in smoke);
  * `will be retried` replaced by `retried once fixed` for a refusal with a fix (five tests);
  * the banner layout (two tests);
  * `PermissionError` replaced by `PermissionError (errno 13)` and `OSError` by `OSError (errno 28)`
    (five expectations);
  * the camp download now `UNREADABLE_ARCHIVE` (`test_summary_names_no_camp_file.py`, `v1-e34-t12`'s
    test of the defect itself);
  * `caselist runs`'s row for a schema-3 run.
* **Cross-build comparison**: `test_pull_run_record_is_read_by_every_build.py` reads the refusal
  scenario's stored files with the one phrase this build keeps (`WORDS_THIS_BUILD_KEEPS`), and the
  CLI's byte-for-byte check does the same. The stored files are unchanged, and
  `stored_run_records/README.md` says why.
* **`tests/smoke`**: `test_caselist_runs.py` checks the two columns.
  `test_caselist_pull_in_process.py` takes the new wording and keys. `README.md` updated.
* **`docs/runbooks/caselist-scheduled-sync.md`**:
  * What a notification says: the layout and its limits, four new titles, and the lock, fix-first,
    publish-again and held-upload wordings, each quoted;
  * a profile the config lacks;
  * `caselist runs`'s columns;
  * the details' and summary's new keys;
  * a camp download's `UNREADABLE_ARCHIVE`;
  * the troubleshooting entries that quoted the old banners.
* **`plan_specs/.../t23-sync-loose-ends.yaml`**: items (13) and (14), and ac8 and ac9, as the PM's
  notes of 2026-10-16 asked, committed first.

## Deviations from the spec

None in scope. Two things were done at the PM's direction rather than the spec's text, and are
recorded here so the spec can be read with them. Items (13) and (14), and ac8 and ac9, were written
into the spec by this session, from the PM's notes, in its first commit. And `reported_error_message`
is used for every non-domain error a stage's reason words, not only item 4's. That changed five
existing expectations from `PermissionError` to `PermissionError (errno 13)` and the like (Decision 2).

## Decisions and assumptions

1. **Item 13: the service's `min()` is kept and tested, not removed.** The five a day is the site
   maintainer's limit, and policy-bound (`docs/policies/caselist-data-use.md`). A second guard on it
   costs one comparison. A service built directly, as a test or a later composition root may build
   it, is the one place the settings validator does not stand in front of it. The test builds the
   service directly with six and with three; removing the `min()` fails it.
2. **One wording for a non-domain error in every stage's reason.** The PM's note asks that one
   `OSError` read the same way everywhere. Item 4 words a camp download's read failure with
   `reported_error_message`. Leaving `_failure` and the camp download's fetch failure on the bare
   class would have made the same `PermissionError` read two ways in one summary, so both use it too.
3. **Item 11's "retryable".** A manifest mismatch alone is announced as cleared by running the
   publish again, with `caselist publish --caselist <slug>` as the command. Its title is
   `caselist pull: publish a manifest again`. It does **not** say the next scheduled run retries it,
   because it does not. The snapshot was published, so nothing owes it, and neither the next pull
   nor `--publish-pending` touches it. Making the report stage put a drifted snapshot back into the
   pending-work file would make that true, but it changes `v1-e34-t18`'s one rule for what is owed.
   It is Follow-up 3.
4. **Item 5: the selection still opens each weekly manifest, and no longer parses its rows.** The
   date comes from the key. The open stays so that a manifest this user cannot open still stops the
   run before anything is fetched, as `v1-e34-t19` decided and tested. A run that cannot open a
   week's manifest cannot claim the week is held, and a torn line is not that. With the selection
   past it, the stage that reads the rows fails on them under `UNREADABLE_MANIFEST`. That is the
   publish of an owed week, or the next weekly's import: the composition root measures first-seen
   against every earlier manifest.
5. **Drift kinds.** `manifest` and `source` are `v1-e30-t12`'s `MismatchKind`. `missing` and
   `suppressed_rows` were added because "a manifest mismatch alone" needs every other cause of
   drift to have a name. They are the same distinctions `caselist status` draws (`incomplete`,
   `suppressed_rows`).
6. **Where the new keys go.**
   * `drift` is on each stage entry of the summary and on `StageDetails`.
   * `held_by_request` is at the top of the summary and of `SyncRunDetails`.
   * Both are additive, so the summary stays at schema version 5 (`v1-e34-t07`'s rule, noted in
     `RUN_SUMMARY_SCHEMA_VERSION`) and the details at version 1.
   * The record is unchanged. The held count also reaches every build's `caselist runs` through
     the import stage's reason, which is not a new field.
7. **The five banners' words**, each also quoted in the runbook:
   * The **lock**: `caselist pull skipped: another was running`, pointing at `caselist runs`.
   * **Fix first**: the rule's first verdict, used when a failed required stage carries a hint, or
     when the error that stopped the run does: `caselist pull failed: retried once fixed`.
   * A **stopped run**: `stopped: <words>`, from a table by error code. A code with no words of its
     own is named by its code, never its class.
   * **Held uploads**: `caselist pull: uploads held by a removal`, pointing at `caselist status`,
     which says whether the removal is owed again (`v1-e30-t21`).
   * The **layout**: the subtitle is `Run <id> (<environment>)`, at most 27 characters. The body is
     `Fix: <command> — ` followed by the message and the hint. The dash keeps a pasted command from
     picking up a full stop. `Notification.text`, for an adapter with one field, reads as before.
8. **`caselist runs`'s verdict has two values, as the spec says.**
   * The lock refusal shows `person`, because it exits `1`. A refusal with a fix shows `retry`,
     because it exits `3`.
   * The banner's own words for those two are not repeated in the table (Follow-up 4).
   * `none` for a run that failed on nothing, `not recorded` for a run with no details.
9. **Test file names** start `test_sync_` or `test_pull_`, so that the node's selector,
   `-k "pull or sync or runs"`, runs them.

## Operator follow-ups

**The banner, on this Mac** (not a criterion; ac5 is the test with the observed limits). The same
check as `v1-e34-t19`'s, with this build's layout. Set Script Editor's notifications to stay on
screen, as on 2026-10-15, and run this from any directory. It takes a second.

```bash
osascript -e 'on run argv' -e 'display notification (item 1 of argv) with title (item 2 of argv) subtitle (item 3 of argv)' -e 'end run' "Fix: debate-research caselist pull --publish-pending — Run 20261014T100000Z (prod): the publish stage failed on STORE_ACCESS_DENIED. The next scheduled run retries it, and is refused the same way until the fix that follows is made. What was captured is kept. This machine refused the blob directory: check that this user can read and write it, under the environment's data directory (storage.data_dir). It is a permission on this machine, not the AWS session." "caselist pull failed: retried once fixed" "Run 20261014T100000Z (prod)"
```

Success looks like this:

* the title `caselist pull failed: retried once fixed`;
* the subtitle `Run 20261014T100000Z (prod)`, whole;
* a body whose first lines read `Fix: debate-research caselist pull --publish-pending` whole.

Paste what the banner shows back into the review.

The weekly agent shows these banners only after it is reinstalled with a build that has this task,
as usual (`docs/runbooks/caselist-scheduled-sync.md`, "Reinstalling the agent").

## Follow-up work

1. **A manifest write fsyncs the file and not its directory** (E30 or E34, p3).
   `caselist.manifest.write_manifest_lines` renames into place after an fsync of the file. The rename
   itself can be lost to a power cut. That is the store's writer, outside item 2's list.
2. **A run whose only pending stage is the report** (E34, p3). Its record's outcome is `completed`.
   Its login banner says `0 snapshot(s) and the run record wait to be published`, though only the
   confirmation waits. This was so before this task; item 1 made that banner say what was found.
3. **A drifted snapshot is owed by nothing** (E34, a ruling first). If the report stage put a
   drifted snapshot back into the pending-work file, the next run would publish it again, and a
   manifest mismatch would be retried by itself. That changes `v1-e34-t18`'s rule for what is owed
   (Decision 3).
4. **`caselist runs` could show the banner's own words** (E34, p3): `skipped` for a lock refusal and
   `retry once fixed` for a refusal with a fix, beside the two-valued verdict the spec asked for.
5. **A torn manifest of a quiet week waits.** A torn line in a week's manifest is now found by the
   stage that reads the rows. In a week that imports and publishes nothing, nothing reads them, and
   the run says nothing until a later import measures against it or `caselist status` or
   `caselist publish` reads it (E34, p3). Before this task such a run stopped at the selection, so
   the line was loud but the run did nothing.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

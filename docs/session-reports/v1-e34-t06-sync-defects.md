# Session report: v1-e34-t06-sync-defects

| | |
|---|---|
| Task | `v1-e34-t06-sync-defects` — Defects found by operating the sync |
| Spec | [`plan_specs/v1/e34-caselist-sync/t06-sync-defects.yaml`](../../plan_specs/v1/e34-caselist-sync/t06-sync-defects.yaml) |
| Epic / release | `v1-e34-caselist-sync` / `v1.1` |
| Branch | `task/v1-e34-t06-sync-defects` |
| Session status | COMPLETE |

## Summary

All three defects are fixed, each with a regression test that fails on the code as the task found
it for the reason the spec names. The phase is `Succeeded`.

1. **The failed-import retry (ac1, which gates `v1-e34-t05`).** A run now imports what is in the
   inbox and not yet in a manifest, whether or not that run downloaded it, and spends no download
   doing so. The fix also covers a second road to the same gap that the spec did not name: an
   older week fails, a newer week imports past it, and the older week then counts as
   `already_imported` for good. A caselist now stops at its first gap.
2. **The download budget (ac2, ac2b).** The budget is now a rolling 24 hours over recorded start
   times, as `RequestPacer` does per minute. The old calendar ledger is read on every run, never
   written, and counted from its mtime, so the first run after the upgrade gets no free five. An
   unreadable ledger counts as fully spent.
3. **OpenEv selection (ac3).** Selection now matches on what the release manifest records, so a
   camp file imported by hand is `already_imported`. The match is built never to claim a file
   nobody imported.

Look first at three things:

* **The PM brief's premise about run summaries does not hold.** The summaries carry no
  `schema_version`, and `caselist runs` does not read them. See the first Decision below.
* **The deep property runs found two weaknesses in my own window test.** Both are reported under
  "What the deep property runs found", not quietly fixed.
* **One file outside the listed packages changed.** `debate_cli/container.py` now has a clock
  seam, which ac2b requires. See Deviations.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `retry-failed-import` — A failed import is retried by the next run | Done | Commit `7cf5c2c`. Three regression tests failed on `2b248e3` before the fix. A fourth guards against a new gap the fix could open. OpenEv covered too. |
| `download-window` — The download budget is a rolling 24-hour window | Done | Commits `f044c71` and `af44619`. New ledger file. The old one is read as a conservative source. The run summary and the select stage report the window. The container has one clock, which the CLI tests pin. |
| `openev-already-held` — OpenEv selection sees hand-imported camp files | Done | Commit `167b6cf`. Matches by id prefix, or by a unique longest path tail. A tie holds neither file. |
| `runbook-correction` — Correct the scheduled-sync runbook | Done | Commit `743153e`. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 — a failed import is retried by the next run, spending no download | PASS | Against `2b248e3`, `pytest …test_caselist_sync.py -k "retry and not retry_after"` → `3 failed, 1 passed`, each failing for the defect: `assert () == ('testcl26 2026-09-15',)` (the retry imported nothing); `a newer week was imported past a failed one`; the camp file likewise `()`. The 1 pass is the guard test, which passes on old code only because old code never imports from the inbox. After the fix, the same four pass. The retry spends no download: `source.archive_fetches` is unchanged across the retry run. |
| ac2 — rolling 24-hour window; the ledger records timestamps | PASS | `test_window_a_second_run_forty_minutes_later_across_utc_midnight_gets_no_fresh_allowance`, against `2b248e3`: `AssertionError: a new date handed out a fresh allowance … Left contains one more item: 'testcl26-weekly-2026-09-15.zip'`. After the fix it passes. That run needed inert shims (see Decisions). The ledger file is `{"schema_version": 1, "bulk_download_starts": [ISO UTC…]}`: `test_window_the_ledger_keeps_only_what_is_inside_the_window`. |
| ac2b — one window everywhere; pinned clocks; the summary reports window start and spend | PASS | Service, container, test helpers and runbook all count one rolling window. Pinned-clock tests: five at T are counted at T+23h59m and released at T+24h01m; five at T then five at T+40m are refused across a midnight in UTC, America/Chicago, Pacific/Kiritimati, Etc/GMT+12, Asia/Kolkata and Europe/London. The summary (`schema_version` 2) carries `bulk_download_window_start` and `bulk_downloads_spent_in_window`, and the select stage states both on every run. The four time-of-day failures: reproduced before the fix with `TZ=Etc/GMT+12 pytest …/test_caselist_runs.py` → `2 failed, 7 passed`. After the fix both modules pass under `TZ=` Etc/GMT+12, Pacific/Kiritimati, America/Chicago and UTC (81 of 81 each). |
| ac3 — a hand-imported camp file is `ALREADY_IMPORTED` and costs no download | PASS | Before the fix, `test_openev_a_camp_file_imported_by_hand_is_already_imported_and_costs_no_download` → `AssertionError: a camp file already held was downloaded again`. After the fix it passes, and the release manifest's rows are unchanged by the run. |
| ac4 — each defect has a regression test that fails before and passes after; the runbook no longer says "re-run" | PASS | Rows ac1, ac2 and ac3 above. The runbook's "Run the same command again" is gone. "A download failed" and a new "An import failed" entry describe what the fixed run does and what the operator still has to fix. |
| Node `retry-failed-import`: `uv run pytest packages/debate_core/tests/application/test_caselist_sync.py -k retry` | PASS | `6 passed`: the 4 new tests, plus 2 older ones whose names contain `retry_after`. |
| Node `download-window`: `… -k window` | PASS | `32 passed`. |
| Node `openev-already-held`: `… -k openev` | PASS | `12 passed`. |
| Node `runbook-correction`: `uv run scripts/check_links.py` | PASS | `OK: 1052 relative links and anchors in 138 Markdown files`. |

Beyond the spec's criteria:

* CI's own pytest selection, `uv run --frozen pytest -n auto --cov -m "not slow and not live"` →
  `2956 passed, 1 skipped in 37.76s`, total coverage 96%. Measured at 39 s, so run in session.
  That was before the last test was added; the module then passed `85 passed`.
* `ruff check .` and `ruff format --check .`: clean.
* `pyright`: `0 errors` (4 s).
* `lint-imports`: `10 kept, 0 broken`.
* `uv run scripts/validate_specs.py` → `OK: 288 files, 38 epics, 230 tasks, 20 releases`.

### Breaking the fix on purpose

Each break was applied to the finished code, the module run, and the file restored. The harness
lives in the session scratchpad, not the repository.

| Fix | Deliberate break | Caught by |
|---|---|---|
| ac1 | import only what this run fetched (the original defect) | `test_retry_an_archive_whose_import_failed_…` |
| ac1 | a failed import does not stop its caselist | `test_retry_a_failed_import_holds_back_the_newer_weeks_…` |
| ac1 | a week not obtained is skipped rather than treated as a gap | `test_retry_an_inbox_archive_waits_behind_an_older_week_the_cap_deferred` |
| ac1 | cap-deferred weeks not counted as candidates | same |
| ac1 | camp files in the inbox are not imported | `test_retry_a_camp_file_whose_import_failed_…` |
| ac1 | an imported camp zip left in the inbox is not recognised by its digest | `test_an_openev_release_that_is_a_zip_is_read_as_one` (extended) |
| ac1 | weeks imported newest first | `test_a_run_downloads_the_new_weeklies_oldest_first_…` |
| ac2 | `>=` at the boundary; a 23-hour window; back to a UTC-date key; future starts ignored | boundary, carried-over and clock-set-back tests |
| ac2 | old ledger not read; unreadable old ledger read as nothing spent; unrecognised new ledger read as nothing spent | upgrade and unreadable-ledger tests |
| ac2 | old ledger counted from its date's midnight rather than its mtime | `test_window_an_old_ledger_counts_from_when_it_was_written_not_from_its_date` |
| ac2 | `already_present` downloads not recorded; ledger never pruned; summary omits the window | one dedicated test each |
| ac2 | the container does not pass its clock to the sync | the pinned CLI test |
| ac3 | back to the sync's inbox name (the original defect) | the hand-import regression test |
| ac3 | any same-named file held; a tie broken by taking the first; folders ignored | folder and tie tests |
| ac3 | names compared exactly; skipped junk rows count; id rule dropped; unlisted id ends the match | one dedicated test each |

Result: 7 of 7 breaks caught for ac1, 12 of 12 for ac2, and 8 of 8 for ac3.

### What the deep property runs found

Two property tests:

* `test_window_no_24_hours_ever_holds_more_than_five_starts`. Runs at random gaps, each reading
  the ledger afresh as a separate process would, with an optional old-format ledger planted at a
  random age.
* `test_openev_matching_never_holds_a_listed_file_nobody_imported`. Soundness of the OpenEv
  matcher over a deliberately tiny alphabet, so names collide often.

CI runs 150 and 300 examples respectively. I ran them deep from a scratch script, and also ran
them against the unsafe breaks to check each property has teeth. **The deep runs found weaknesses
in my tests, not in the code:**

1. **The window property's oracle read the ledger back through the code under test.** It
   collected the starts to check from `DownloadLedger.starts()`. A ledger that dropped the old
   file's downloads therefore dropped them from the check too. 2,000 examples against "old ledger
   read as nothing spent" found no counterexample. Fixed: the test now keeps its own account of
   every start it records and every old-ledger download it plants. With that change it finds
   counterexamples for four breaks: the calendar key, the ignored old ledger, the old ledger
   stamped at midnight, and `record` losing entries.
2. **The same property took its window length from the module.** It imported
   `BULK_DOWNLOAD_WINDOW`, so a 23-hour window passed 2,000 examples. Fixed: the test writes its
   own `A_ROLLING_DAY = timedelta(hours=24)` (working agreements §6), and the 23-hour break now
   fails.

On the final code:

* Window property: 30,000 examples, no counterexample (68 s).
* Matcher property: 100,000 examples, no counterexample (101 s).

The matcher property catches "no tie check" (`held [101] that nobody imported`) and "tie broken
by first" (`held [100] …`). It does not catch "folders ignored", and should not: that break makes
the matcher hold *less*, not wrongly. The folder example test catches it.

## Files changed

* `packages/debate_core/src/debate_core/application/caselist_sync.py`: all three fixes.
  * The import stage works from the inbox against the manifests (import queues, first-gap rule).
  * The OpenEv selection order changes, and an inbox file whose bytes a manifest records counts
    as imported.
  * `DownloadLedger` is rewritten for the rolling window, with conservative reading of the old
    and unrecognised formats.
  * `SyncPlan` and `RunSummary` gain window fields, and the summary gets `schema_version` 2.
  * The manifest-based OpenEv matcher (`_held_openev_ids`) is new.
  * Module docstring sections "What is imported" and "The daily download budget".
* `packages/debate_core/tests/application/test_caselist_sync.py`: the regression, guard,
  boundary, upgrade and property tests above. Calendar-day tests and helpers are replaced by
  pinned-clock ones.
* `packages/debate_cli/src/debate_cli/container.py`: one `clock()` seam, used by the sync
  service and the run monitor.
* `packages/debate_cli/tests/commands/test_caselist_runs.py`: the two time-of-day-flaky tests
  now run on a pinned clock, 40 minutes after a spend at 23:45 CDT. The pinned-clock tests replace
  them rather than sitting beside them.
* `packages/debate_cli/src/debate_cli/commands/caselist_pull.py`: the dry-run caption says
  "24-hour download cap", not "today's".
* `docs/runbooks/caselist-scheduled-sync.md`: the rolling window and old-ledger reading, the two
  new summary fields, and the corrected failure entries.

## Deviations from the spec

* **`debate_cli/container.py` is outside `constraints.packages`**, which lists
  `debate_cli.commands`. ac2b requires "the CLI container" to agree on the window, and "a test
  pins a clock to prove it". The CLI tests could only pin a clock the container builds the service
  with, and it had none. The change is one method plus two keyword arguments. The PM may want to
  add `debate_cli.container` to the spec's packages.
* **ac1 is applied to OpenEv camp files as well as archives.** The spec names archives. A camp
  file whose import failed had the identical defect (`already_in_inbox`, never imported), and
  ac1's own rule ("a run imports what is in the inbox and not yet in a manifest") covers it.
* **ac1 also stops a caselist at its first gap.** The spec does not ask for this. Without it the
  retry is not guaranteed: a failed 09-08 followed by a successful 09-15 left 09-08
  `already_imported` for good, which is the same silent gap. This is shown failing on the original
  code.
* **A small fix outside the three defects.** `_import_openev` compared the bare release name to
  `"openev <release>"` labels, so two camp files in one run listed the release twice in
  `snapshots_imported`. It sits in the code ac1 rewrote.

## Decisions and assumptions

* **The PM brief's premise about the six run summaries does not hold, so no compatibility shim
  was needed.** I read the operator's files (read-only).
  * `~/.debate-research/dev/caselist-sync-runs/*.json` are `RunSummary.as_json` files. They carry
    `bulk_downloads_allowed` and `bulk_downloads_spent_today` but **no `schema_version`**, and
    **nothing reads them back**.
  * `caselist runs` reads the JSONL run log (`caselist-sync-runs.jsonl`, 3 records), whose
    `SyncRunRecord` has `schema_version: 1` and **neither bulk field**.
  * So I left the record schema alone. Adding a field there would break the installed
    `v0.1.0-dev.5` build, whose `extra="forbid"` would skip new lines. The summary now starts at
    `schema_version: 2`, with unversioned files counting as version 1. `test_sync_runs.py` and
    the smoke tests for `caselist runs` pass unchanged.
* **A new ledger file name.** The new ledger is `caselist-sync-download-starts.json`, and the old
  `caselist-sync-downloads.json` is read on every run and never written. The backfill runs from
  an installed old-format build against the same state directory. With one shared file, each
  build would overwrite the other's format: the old build would read the new file as "nothing
  spent", and the new build would lose its own timestamps. With two files, the new build counts
  everything. The old build can still overspend what the new one spent, which cannot be fixed
  from new code, but the server's limiter absorbs that as a deferral.
* **The old ledger is migrated to N starts at its mtime, not "fully spent".** Every write replaced
  the file, so each counted download started at or before that moment. The mtime is the latest any
  of them can be, which keeps them in the window longest. It is also independent of which timezone
  its `date` was keyed in. Checked against a `cp -p` copy of the operator's real file:
  `{"bulk_downloads": 5, "date": "2026-09-29"}` became five starts at
  `2026-09-29T04:45:11Z`. Forty minutes later: spent 5, remaining 0. At +23h59m: 0 remaining. At
  +24h01m: 5 remaining. An unreadable file of either kind is `limit` starts at its mtime: fully
  spent for 24 hours, then released, so it cannot block for good.
* **A download is recorded at the moment it started, including `already_present` ones.** The
  client streams the whole archive before it can tell, and the server has counted it. A download
  that raises is not recorded, as before (see Follow-up work).
* **A start later than "now" counts.** A clock set back must not hand out an allowance.
* **The OpenEv match is built to fail safe.** A recorded path names a listed file either by an
  `openev-<id>-` prefix, or by the longest tail of components it shares with the listed path,
  compared case-, spacing- and punctuation-insensitively. A tie holds neither. Wrongly holding a
  file loses it for good, while wrongly missing one costs a download and a `DUPLICATE` row. The
  property test above checks that the matcher never holds a file nobody imported. Only rows the
  importer classified count, because `__MACOSX/…/._<name>.docx` junk normalises to the real
  file's name.
* **"No test may derive the window from the machine's real clock or timezone."** Every test that
  asserts on the window or seeds a spend now pins its clock. Other `caselist pull` tests still run
  on the real clock through the container, but assert nothing about the window. Their two runs,
  seconds apart, are inside 24 hours whenever the suite runs, so they cannot become
  time-of-day-flaky.
* **How ac2's "fails on the current code" was run.** The new test module imports names the
  original module lacks. So I checked the test against `git show 2b248e3:…/caselist_sync.py`,
  with four inert definitions appended (`LEGACY_DOWNLOAD_LEDGER_FILENAME`,
  `RUN_SUMMARY_SCHEMA_VERSION`, `BULK_DOWNLOAD_WINDOW`, `_held_openev_ids`). None is reached by
  the test run. The file was restored and the tree confirmed clean.
* **The operator's store has no live ac1 gap today.** Every archive in the dev inbox has a
  manifest. `hspolicy26` has 07-07, 07-14 and 07-28 without 07-21, but the run summaries show
  OpenCaselist never listed a 07-21 for it, so that is not a gap.

## Operator follow-ups

None required for acceptance.

Nothing here reaches the backfill, which runs from the installed `v0.1.0-dev.5`. The first build
with this change needs no preparation. Leave `<data_dir>/caselist-sync-downloads.json` where it
is: the new build reads it and stops counting it 24 hours after its last write.

## Follow-up work

* **`v1-e34-t05-enable-schedule`:** ac1, the criterion it waits on, is in this branch.
* **E34 (a possible later task):**
  * A download that raises mid-stream is not recorded in the ledger, though the server may have
    counted it. Recording the start before the request would be stricter.
  * An old-format build can still spend downloads the new build already spent. That lasts until
    the backfill moves to a build with this change.
* **E34 / `v1-e34-t04`:**
  * OpenEv matching cannot see content: the listing carries no digest. So a camp file revised
    upstream under an unchanged path is held and not re-fetched. `v1-e34-t04` refreshes full
    caselist archives, so it may be the place to decide an OpenEv refresh too.
  * An OpenEv camp release that is a zip is recognised as imported only while its zip is in the
    inbox, by digest. Its manifest names its members, not the zip.
* **Container housekeeping, v1-e01:** the container's module docstring shows `clock=SystemClock()`
  in its example, and no `SystemClock` exists. This predates the task.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-09-30

**Notes:**

Accepted in full, phase `Succeeded`. All three defects fixed, each shown failing first for the
reason the spec names, and the two places the session went beyond the spec are both places the
spec was incomplete rather than the session over-reaching.

**My brief was wrong about the run summaries, and the correction is worth more than the shim it
replaced.** I told the session the `caselist-sync-runs/*.json` files carry `schema_version` and are
read back by `caselist runs`, and asked for a compatibility shim. Neither half holds: those files
are `RunSummary.as_json` with no version field, and `caselist runs` reads
`caselist-sync-runs.jsonl` through `SyncRunLog`. I conflated two artifacts - and the
`KeyError: 'outcome'` the operator hit on 09-29 running my one-liner over those files was that same
confusion showing itself, which I did not follow through. Verified: `SyncRunRecord` carries
`model_config = ConfigDict(frozen=True, extra="forbid")` and `schema_version: Literal[1]`.

The session's conclusion is sharper than my premise. Because `extra="forbid"` and the version is a
`Literal[1]`, adding a field to `SyncRunRecord` - or bumping its version - would make the installed
`v0.1.0-dev.5` build reject records a newer build writes into the log they share. **The JSONL run
log is a cross-version interface between an installed build and whatever writes beside it**, and
nothing in the codebase says so. Leaving the record untouched and versioning only the summary was
therefore not the conservative option, it was the correct one. That property should be written
down; see the follow-ups below.

**Two files rather than one is the right call for the same reason.** The backfill runs from the
installed old-format build against the same state directory, so one shared ledger would have each
build reading the other's format as "nothing spent" - the old build silently, every run. Two files
means the new build counts everything; the residual (an old build overspending what the new one
spent) is real, is named, and is absorbed by the server's own limiter. This only became visible by
taking seriously that the deployed artefact and the working tree are different things, which is the
same fact that let me lift t13's merge hold.

**The old ledger migrated to N starts at its mtime is the detail I would have got wrong.** Every
write replaced the file, so each counted download started at or before that moment; the mtime is
the latest any of them can be, which keeps them inside the window longest and is therefore the
conservative reading. It is also independent of which timezone the old `date` was keyed in, which
is the whole defect. And bounding the unreadable case at `limit` starts from the mtime - fully
spent for 24 hours, then released - is better than the "treat it as fully spent" I asked for, which
would have blocked forever on a corrupt file. Checking it against a `cp -p` of the operator's real
ledger rather than a fixture is what makes it evidence.

**Deviations accepted, all four.** `debate_cli/container.py` is outside the package list because I
wrote a criterion naming the CLI container and a package list excluding it; I have amended the spec
in this branch rather than asking for a change. Extending ac1 to camp files follows from ac1's own
rule. The `_import_openev` double-listing fix sits inside the code ac1 rewrote.

**The first-gap rule is the most valuable thing here and it was not asked for.** The spec's ac1
describes one road to the silent gap. The session found a second - an older week fails, a newer
week imports past it, and the older week is `already_imported` for good - and showed it failing on
the original code. Without that, ac1's guarantee is not actually delivered: the retry works only
when nothing newer has landed since. A criterion that can be satisfied while the defect it names
survives is a criterion I wrote badly, and finding that is worth more than fixing what I did write.

**The property-test findings are the standard.** Two textbook ways a property test becomes
decorative - an oracle that reads back through the code under test, and importing the constant
under test as the expected value - each of which made a real break pass 2,000 examples. Both found
by deep runs, both reported rather than quietly fixed, and both shown to catch specific breaks
afterwards. The note that the matcher property does *not* catch "folders ignored", with the reason
that the break makes the matcher hold less rather than wrongly, is the kind of negative result that
tells me the properties are understood and not just passing.

**On the inert shims used to prove ac2 fails on the original code.** Appending four unreached
definitions to `2b248e3`'s module so the new test could import is the right technique: the
alternative, backporting the test, would have demonstrated something other than the test that
ships. Stating it, naming the four, asserting none is reached and confirming the tree clean
afterwards is what keeps it evidence rather than a footnote.

**Two follow-ups I am adding, neither blocking.**

1. *The legacy-ledger read is a migration shim with no removal date.* `caselist-sync-downloads.json`
   will be read on every run forever, contributing nothing 24 hours after the backfill last touches
   it. Shims without a trigger become permanent. I have added the removal to `v1-e34-t05` as a
   cleanup criterion, because enabling the schedule on a build carrying this change is exactly the
   moment it stops being needed.
2. *Write down that the run log is a cross-version interface.* A future task adding a field to
   `SyncRunRecord` will break installed builds reading the same log, and nothing warns it. This
   belongs in `sync_runs.py`'s module docstring. Filed against E34 rather than reopening this task.

**The remaining known gap is correctly filed and correctly left.** A download that raises
mid-stream is not recorded although the server may have counted it - the one place the accounting
is still optimistic. Recording the start before the request is stricter and is the right change,
but it is a different decision from this task's and belongs with the one that makes the schedule
unattended.

**Sync before opening the PR.** This branch reports `288 files, 230 tasks`; `origin/dev` is at
`289 / 231` after `v1-e01-t14` and the `t05` dependency edge merged on 09-29. Nothing conflicts
with this work, but run `scripts/task sync v1-e34-t06-sync-defects` so the PR is built on current
`dev`.

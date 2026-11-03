# Session report: v1-e30-t21-held-path-loose-ends

| | |
|---|---|
| Task | `v1-e30-t21-held-path-loose-ends` — Loose ends of the removed-path hold: status, the publisher and the inbox |
| Spec | [`plan_specs/v1/e30-caselist-ingestion/t21-held-path-loose-ends.yaml`](../../plan_specs/v1/e30-caselist-ingestion/t21-held-path-loose-ends.yaml) |
| Epic / release | `v1-e30-caselist-ingestion` / `v1.1` |
| Branch | `task/v1-e30-t21-held-path-loose-ends` |
| Session status | COMPLETE. Every criterion passed; the Goal is `Succeeded` |

## Summary

`caselist status` now reports two things that mean a removal is owed again: a stored manifest row
at a path a removal holds, and an upload at a held path in an archive in the download inbox. Each
is named by the first twelve characters of its sha256 and the request id holding the path, with the
hint to run that removal again. Neither changes the exit code. The publisher withholds a manifest
with a row at a held path exactly as it withholds one with a suppressed row: same outcome, same
code, same counts. In the inbox, `caselist pull` now takes out a weekly archive whose every member
was removed or held as soon as the import that met the hold finishes. The removal's rewrite of an
archive still waiting to be imported now drops a skipped member at a held path, such as a symbolic
link named as the removed file. Anything else that holds a held upload stays for retention, for
the reasons under ac3.

**Four things to look at first:**

1. **I read "exit codes unchanged" as: the held report sits beside the verdict and never in it**
   (Decision 1). A held row or held inbox upload does not make a snapshot drift, so `caselist
   status` exits 0 when the bucket agrees. The pull's report and retention stages, which ask the
   same comparison, behave exactly as before.
2. **Under ac3, most inbox copies still wait for retention.** A weekly window normally holds other
   teams' files beside the held upload, and the forbidden list keeps those. So the immediate
   take-out fires only for an archive that held nothing else. The usual case leaves with retention
   at the end of the same pull, once its publish is confirmed. `caselist status` names it until then.
3. **Once the copy is gone, running the removal again cannot put the held upload's sha256 on the
   list.** That was already so whenever retention removed the copy first. The path entry still
   refuses the upload at that path. The runbook now says so (Follow-up work 2).
4. **Mutation removed two rules I had written** (Decision 9). Of 27 mutants, 23 were caught on the
   first pass. The 4 survivors each showed a missing test, which I added, and all 27 are now
   caught. Two other rules could not be told apart from their absence, so I deleted them before
   running any mutant.

`v1-e29-t09` has not merged yet (`git ls-remote origin dev` still gives the start commit,
`1261b3d`), so if this merges first, `t09` syncs. The one file both tasks change is
`publish_service.py`. This task changes only the suppressed-row branch of `_publish_snapshot`, and
adds `_withheld_for_rows`, whose message holds digests and request ids and no error text.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `held-path`: Held-path loose ends | Done | Status, the publisher's refusal, the inbox, the runbook, and the cross-build evidence. Its criterion passes: 234 tests. |

## Acceptance criteria

"The start commit" is `1261b3d`, the `dev` this branch was cut from (four commits after tag
`v1.1.0-dev.2`). "The agent's build" is `v0.1.0-dev.122` (`d87febd`), which the PM's notes name.
Each build's source is exported with `git archive` into the scratch directory and put first on
`PYTHONPATH`. I did not open or run any installed build.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1**: status reports a held upload in the inbox and a row at a held path, by count and digest prefix, with the hint to run the removal again; exit codes unchanged; shown failing first | PASS | **Red first, through the command**: `packages/debate_cli/tests/test_caselist_publish.py::TestStatusOfAHeldPath` against the start commit's source → **3 failed, each an assertion**, after the old build's own exit code (0) had already matched: `assert None == []` (`removals_owed`), `{'2026-09-08': (None, None, None)} != {'2026-09-08': (1, ['29969bed5e6c'], ['RM-2026-09'])}` (held rows), and the table's `HELD PATH ROWS…` line missing. That test sets the hold up with nothing the start commit lacks: the path entry as a removal appends it, and next week's archive in the inbox. **Red first, the services**: the two new application test files and the CLI renderer file against the start commit → `15 failed, 5 passed, 1 error`. The ac1 tests fail on `CaselistStatusService.__init__() got an unexpected keyword argument 'inbox'` or `'SnapshotPlan' object has no attribute 'held_rows'`. The renderer file fails at collection (`cannot import name 'HeldRow'`). The 5 that pass are guards for what must not change (Decision 7, ac3), and mutants 15, 16 and 20 show they bite. **Green**: `test_held_path_loose_ends.py`, 22 tests, most of them ac1's: the row an older build imported (`[(UPLOADED_AFTER, 'RM-2026-01')]` in `2026-10-08`), a held row in a complete archive, each held inbox upload by caselist, snapshot, digest and request (three, written by hand from t13's fixture), not the removed file itself, not a link, not another caselist's, the re-run clearing both, the inbox read only when asked, and no archive opened when no path is held. Exit codes: `test_a_held_row_does_not_change_the_verdict` (`report.in_sync` is true), `test_a_report_with_both_kinds_of_hold_is_still_in_sync`, `test_a_drifted_report_still_fails_as_drift_and_its_hint_names_the_removal_owed` (still `CASELIST_DRIFT`, with one sentence added to the hint), and through the command, `exit_code == 0` with both kinds present. No path, school, team code or file name: the status, publisher, command and smoke tests check what they print for the fixture's names and the held path, and the status tests for `.zip` and `.docx` too. Smoke: `tests/smoke/test_caselist_remove_smoke.py::test_a_removed_path_holds_next_weeks_upload_and_the_same_removal_run_again_finishes_it` → `1 passed in 27.16s`: status exits 0, names the upload by prefix and `RM-2026-03`, names no one, and says nothing is owed after the re-run |
| **ac2**: the publisher withholds a manifest with a row at a held path, as it does one with a suppressed row, by test | PASS | `test_the_publisher_withholds_a_manifest_with_a_held_row_exactly_as_one_with_a_suppressed_row`: the older build imports 2026-10-08, and two plans of that snapshot come from one listing, one where the hold stops the row and one where a withdrawn disclosure does. Planned, dry, and carried out, every outcome and count is equal (`succeeded`, `failed_sha256`, `failure_codes`, the manifest outcome `withheld`, `MANIFEST_NAMES_SUPPRESSED_SOURCE`, the per-result counts and the planned counts), and no manifest reaches the bucket. Only the message differs: `1 row(s) at a path a removal holds: <digest> (RM-2026-01)`. Red on the start commit: `assert {'succeeded':…} == {'succeeded':…}`, because the old publisher uploaded the manifest. Also `test_status_and_the_publisher_find_a_held_row_in_a_complete_archive_too`, `test_after_the_removal_alone_nothing_is_withheld` (the earlier version in `2026-09-01` is not held), and `…once_the_removed_file_is_let_back_in`. **Which older builds could have written such a row**: every build before `v0.1.0-dev.126` (`fd72c8c`, `v1-e30-t13`'s merge, 2026-10-13), the last being `v0.1.0-dev.125`. That includes `0.1.0.dev60`, the agent until 2026-10-14, `v0.1.0-dev.119`, and `v0.1.0-dev.122`, the agent now. They read the list and no path entry. Shown directly: each build's importer, given this build's records with the path entry and next week's archive, dry into an empty store. This build → `{'NEW': 2, 'SUPPRESSED': 1}`; the start commit → `{'NEW': 2, 'SUPPRESSED': 1}`; `v0.1.0-dev.122` → `{'NEW': 3}`, so it stores the upload at the held path. A build from `v0.1.0-dev.126` on refuses it at import, and a removal leaves no such row |
| **ac3**: the inbox copy is taken out when the import that met the hold has finished, or the report says why it stays, by test | PASS | **Taken out**: `test_held_path_inbox_copies.py`, 6 tests, through the pull. Week four holds only the re-upload at the held path and the AppleDouble file naming it. With the bucket's session expired, so that nothing is published or confirmed, the archive is gone after the import stage, whose reason says `1 archive(s) taken out of the inbox, which held only files removed or held at a removed path`. The next pull does not fetch it again. A copy whose bytes changed after its import is left. Red on the start commit: `AssertionError: the archive stayed in the inbox`. **The skipped member**: `test_the_removal_rewrites_a_waiting_archive_without_a_link_named_as_the_removed_file` (the rewrite keeps `[KEPT_PATH]`, and the link's body was the file's name). Red on the start commit: `AssertionError: assert [] == [(<InboxActio...2.docx',), 1)]`, because the old removal left the archive alone. **Stays, by test**: an archive that also holds another team's file (`kept: not_confirmed`; status names its held upload; the next logged-in pull's retention removes it); one with junk the hold does not explain; one holding only the removed file itself (no hold met); an imported archive holding a link at the held path among other files (not deleted); a link in a waiting archive dated before the hold; and a held upload another request's removal does not take. **Why each stays** is under "What stays in the inbox, and why" below |
| **ac4**: archives and records written by the build at the start commit and by the build the agent runs are read unchanged | PASS | See "Every build reads every build's files" below: each build's files from the same two scenarios, read by this build, the start commit and `v0.1.0-dev.122`. Six reads, every one exit 0. The only differences are what the files hold |
| Node `held-path`: `uv run pytest packages/debate_core/tests/application -k "hold or held or status"` | PASS | `234 passed in 17.69s`, run as the spec writes it (206 before this task) |
| Full suite, four parts (`uv run --frozen pytest -n auto -m "not slow and not live" --part K/4`) | PASS | `1797 passed` (61 s); `1804 passed, 1 xfailed` (53 s); `1807 passed, 1 skipped, 2 warnings` (51 s); `1802 passed, 1 xfailed, 1 warning` (85 s). Each part ran under a hard stop at load averages 8 to 22, with the corpus re-parse running. The skip is the parser eval waiting on human corrections. I did not open the warnings |
| Lint, types, contracts, docs | PASS | `ruff format --check .`: 708 files formatted. `ruff check .`: clean. `uv run --frozen pyright`: `0 errors`. `lint-imports`: `12 kept, 0 broken`. `check_thin_handlers.py`: 21 within 25 statements. `docs_index.py --check-descriptions`: 34 described. `check_command_blocks.py --base origin/dev`: OK. `validate_specs.py`: `OK: 355 files, 38 epics, 297 tasks, 20 releases` |

### What stays in the inbox, and why

The forbidden list says never to remove an inbox file that holds anything not removed or held.
Under that rule, these copies stay:

| Copy | Why it stays | What takes it out |
|---|---|---|
| A weekly holding a held upload and anything else: another team's file, or junk not withheld with a removed file | It holds things that are neither removed nor held. Retention keeps an imported archive until its publish is confirmed, so that a failed publish can import it again. A copy rewritten without the held upload would match no manifest's `archive_sha256`, so retention could never remove it, and nothing would import it | Retention, once the snapshot is confirmed (normally the same pull), or the same removal run again, which deletes an imported archive |
| A complete archive | It holds the whole caselist, so never removed or held files alone. The pull does not ask it (Decision 9) | Retention, as before |
| An archive imported by hand with `caselist import` | The command never deletes the file it was given, which may be the operator's own copy outside the inbox | Retention at the next pull, or the removal run again |
| A copy whose bytes changed after its import, or that the file system refuses to remove | Only the bytes imported are taken out | Retention judges it |
| An archive holding only files the list stops, with no hold met | Outside "the import that met the hold" | Retention, as before |
| An imported archive whose only link to the removal is a skipped member at the held path | The rest is other teams' disclosures, and the removal deletes an imported archive rather than rewriting it (`v1-e30-t09`) | Retention |

### Every build reads every build's files (ac4)

`write_held_path_files.py` (run by path) writes what a build leaves after this task's two
scenarios. The removal scenario: the revised-path store, a waiting weekly with a link at the
removed path, the `--source` removal, and the arriving weekly of 2026-10-08 imported afterwards.
It writes the waiting archive, the takedown's records here and in the bucket, and every manifest.
The pull scenario: the Bayview negative removed, week four pulled with the bucket's session
expired. It writes the run record, its details and what is left in the inbox. It ran with this
task's source and with the start commit's, the same file against both:

```bash
WRITE_HELD_PATH_FILES="${OUT}/this-build" uv run --frozen pytest packages/debate_core/tests/application/caselist/write_held_path_files.py -p no:cacheprovider --no-cov -n 0 -q
WRITE_HELD_PATH_FILES="${OUT}/start-commit" PYTHONPATH="${START}/packages/debate_core/src:${START}/packages/debate_cli/src" uv run --frozen pytest packages/debate_core/tests/application/caselist/write_held_path_files.py -p no:cacheprovider --no-cov -n 0 -q
```

Compared byte for byte, the two builds wrote the same manifests (all nine), the same suppression
list, path entries and withdrawals, and the same run details. What differs is what this task
changes. The waiting archive: this build's has no link. The removal log line: the same keys, and
one more `inbox_rewrites` pair, for that archive. The scope record: only moto's random version
ids. The run record: the import stage's reason, and a retention stage `skipped` because the
inbox was empty. The inbox after the run: empty here, the week-four archive at the start commit.

`read_held_path_files.py` is a plain script that imports nothing from the test suite. Each record is
read with the build's own reader, which refuses a whole record at a line it cannot validate:

```bash
PYTHONPATH="${BUILD}/packages/debate_core/src:${BUILD}/packages/debate_cli/src" uv run --frozen python packages/debate_core/tests/application/caselist/read_held_path_files.py "${OUT}/this-build" agent-build
```

All six reads exited 0. This build's files, read by `v0.1.0-dev.122`:

```text
reader: agent-build (debate_core from agent-build)
files written by: this-build
archive testcl26-weekly-2026-10-11.zip: 1 member(s), 0 skipped
  imported dry into an empty store: {'NEW': 1}, skipped 0
suppression list: 4 line(s); 3 whole file(s) and 1 disclosure(s) suppressed
path holds: this source reads no path-hold record
removal log: 1 entry(ies)
removal scopes: this source reads no removal-scope record
files here: path-holds.jsonl, removal-log.jsonl, removal-scopes.jsonl, suppression-list.jsonl, withdrawals.jsonl; in the bucket: path-holds.jsonl, removal-log.jsonl, removal-scopes.jsonl, suppression-list.jsonl, withdrawals.jsonl
manifest 2026-09-01.jsonl: 2 source(s), 2 stored row(s), classifications {'NEW': 2}
manifest 2026-09-08.jsonl: 2 source(s), 2 stored row(s), classifications {'NEW': 1, 'SUPPRESSED': 1, 'UNCHANGED': 1}
manifest 2026-09-15.jsonl: 1 source(s), 1 stored row(s), classifications {'REMOVED': 1, 'SUPPRESSED': 1, 'UNCHANGED': 1}
manifest 2026-09-22.jsonl: 1 source(s), 1 stored row(s), classifications {'UNCHANGED': 1}
manifest 2026-09-29.jsonl: 1 source(s), 1 stored row(s), classifications {'SUPPRESSED': 1, 'UNCHANGED': 1}
manifest 2026-10-06.jsonl: 2 source(s), 2 stored row(s), classifications {'DUPLICATE': 1, 'SUPPRESSED': 1, 'UNCHANGED': 1}
manifest 2026-10-08.jsonl: 2 source(s), 2 stored row(s), classifications {'NEW': 1, 'REMOVED': 1, 'SUPPRESSED': 1, 'UNCHANGED': 1}
manifest full/2026-09-05.jsonl: 2 source(s), 2 stored row(s), classifications {'NEW': 2}
manifest full/2026-10-03.jsonl: 1 source(s), 1 stored row(s), classifications {'SUPPRESSED': 1, 'UNCHANGED': 1}
run record: outcome publish_pending, stages {'completed': 3, 'pending': 2, 'skipped': 3}
  import stage: 1 snapshot(s) imported, 0 new file(s) stored; 1 archive(s) taken out of the inbox, which held only files removed or held at a removed path
run details: read, run id matches
inbox after the run: empty
```

The other five reads printed the same lines, except where the files or the reader differ:

- **The start commit and this build, reading this build's files.** Each printed `path holds: 1
  read` and `removal scopes: 1 read`, because both read those records. The agent's build reads
  neither.
- **The start commit's files, by every reader.** Every reader printed `1 member(s), 1 skipped`
  and `skipped 1` for the archive, which still holds the link, and the same counts otherwise. The
  run record had `{'completed': 4, 'pending': 2, 'skipped': 2}` and an import stage without the
  take-out, and the inbox held `testcl26-weekly-2026-09-22.zip`.

Run record and details: no key changed. The take-out is a phrase in a stage's reason, and its
counter is on the run's tally, not on `RunSummary`, so the record's schema is the start
commit's.

### Mutation runs

Each run applied one textual change to committed source, ran the 176 to 180 tests of eleven files
(the four with this task's tests, `test_caselist_publish.py`, and the removal, hold, inbox,
retention, publish and status files) with `--no-cov -p no:randomly` and `-n 6` (`-n 3` for the last two, at a load average of 45), and restored
the file from a byte copy, checking its sha256 and `git diff --quiet`. The driver refuses a mutant
whose target is not there exactly once. Each run set `HYPOTHESIS_STORAGE_DIRECTORY` to a new
directory made with `mkdtemp` and checked empty (working agreement 8); none of these tests is a
Hypothesis property. Every catch is a failing test; none errored at collection.

| # | Mutation | Result | First failing test |
|---|---|---|---|
| 1 | A row the list already stops is counted as held too | **SURVIVED, then CAUGHT** | `test_a_held_row_the_list_now_names_is_a_suppressed_row_and_not_a_held_one` |
| 2 | A complete archive's snapshot gives no date | CAUGHT, 1 failed | `test_status_and_the_publisher_find_a_held_row_in_a_complete_archive_too` |
| 3 | The plan's withholding rows leave out held rows | CAUGHT, 2 failed | the same, and the ac2 comparison |
| 4 | The publisher withholds for suppressed rows only | CAUGHT, 1 failed | the ac2 comparison |
| 5 | A dry run's success ignores held rows | CAUGHT, 1 failed | the ac2 comparison |
| 6 | Status reports no held row | CAUGHT, 6 failed | `test_status_reports_a_row_an_older_build_imported_at_a_held_path` |
| 7 | **A held row makes its snapshot drift** (the exit code changes) | CAUGHT, 7 failed | `test_a_report_with_both_kinds_of_hold_is_still_in_sync` |
| 8 | The inbox report ignores the snapshot asked about | CAUGHT, 1 failed | `test_an_upload_this_build_refused_at_import_is_still_reported_while_its_archive_waits_in_the_inbox` |
| 9 | The inbox report ignores the caselist asked about | **SURVIVED, then CAUGHT** | `test_an_upload_another_caselist_holds_is_reported_only_for_that_caselist` |
| 10 | The inbox is read with no path held | CAUGHT, 1 failed | `test_with_no_path_held_no_archive_in_the_inbox_is_opened` |
| 11 | An upload the list stops is reported as held | CAUGHT, 1 failed | `test_the_removed_file_itself_in_a_later_archive_is_the_lists_and_not_reported_as_held` |
| 12 | A skipped member is reported as a held upload | **SURVIVED, then CAUGHT** | `test_a_link_at_the_held_path_is_not_a_held_upload` |
| 13 | A complete archive's upload is named as the weekly of its date | CAUGHT, 2 failed | `test_status_reports_each_upload_held_in_the_inbox…` |
| 14 | The removal's rewrite keeps a skipped member at a held path | CAUGHT, 1 failed | `test_the_removal_rewrites_a_waiting_archive_without_a_link…` |
| 15 | **The forbidden list**: such a member is dropped from an imported archive too, which deletes it | CAUGHT, 1 failed | `test_an_imported_archive_holding_only_such_a_link_and_other_files_is_not_deleted` |
| 16 | A real member at a held path is dropped though the list does not name it | CAUGHT, 1 failed | `test_another_requests_removal_leaves_a_held_upload_in_a_waiting_archive_for_its_own_request` |
| 17 | An archive that met no hold counts as removed or held alone | CAUGHT, 1 failed | `test_an_archive_holding_only_the_removed_file_itself_is_left_for_retention` |
| 18 | **The forbidden list**: any skipped member counts as removed or held | **SURVIVED, then CAUGHT** | `test_an_archive_with_junk_the_hold_does_not_explain_is_left_for_retention` |
| 19 | **The forbidden list**: a stored member counts as removed or held | CAUGHT, 1 failed | `test_an_archive_that_also_holds_another_teams_file_stays_until_its_publish_is_confirmed` |
| 20 | The take-out does not check the bytes are the ones imported | CAUGHT, 1 failed | `test_a_copy_that_changed_after_its_import_is_left_for_retention` |
| 21 | The pull never takes a copy out | CAUGHT, 1 failed | `test_an_archive_holding_only_the_held_upload_leaves_the_inbox_when_its_import_finishes` |
| 22 | The import stage does not say it took a copy out | CAUGHT, 1 failed | the same |
| 23 | `caselist status` does not ask about the inbox | CAUGHT, 2 failed | `test_status_names_the_held_rows_and_the_held_upload_and_still_exits_zero` |
| 24 | The container builds status without the inbox | CAUGHT, 15 failed | every status command test |
| 25 | A drift's hint leaves out the removal owed | CAUGHT, 1 failed | `test_a_drifted_report_still_fails_as_drift_and_its_hint_names_the_removal_owed` |
| 26 | The table leaves out the removal owed | CAUGHT, 2 failed | `test_the_table_says_every_snapshot_agrees_then_what_is_held…` |
| 27 | The JSON counts no held row | CAUGHT, 2 failed | `test_the_json_counts_each_held_row_by_prefix_and_request` |

Rows 1 to 27 ran on `7005102`. The four survivors ran again on `5148534`, each caught by the test
named. Each survivor was a missing test, not a defect. One run of the second pass hit the
command's hard stop before the driver restored its file. Its diff was exactly mutant 18, and I
restored the file from git, where it was committed.

## Files changed

- **`debate_core.application`**
  - `caselist/publish_plan.py`: `HeldRow`, `held_rows()`, `snapshot_date()`, and
    `SnapshotPlan.held_rows` and `withholding_rows`; the "withheld" section of the docstring.
  - `caselist/publish_service.py`: a manifest is withheld for any withholding row, with the same
    outcome and code; `_withheld_for_rows` writes the message; `PublishReport.held_rows`.
  - `caselist/status_service.py`: `SnapshotStatus.held_rows`, `HeldInboxUpload`, the `InboxHolds`
    protocol, `CaselistStatusReport.held_in_inbox`, `held_snapshots` and `removals_owed`, and
    `status(held_in_inbox=)`; a new docstring section, "What a removal's hold says is owed".
  - `caselist/inbox_purge.py`: `CaselistInbox.held_uploads()`; `entries_to_drop(snapshot=)` drops a
    skipped member at a held path from a waiting archive.
  - `caselist/import_service.py`: `ImportReport.removed_or_held_alone`.
  - `caselist_sync.py`: after a weekly's import, the copy is taken out if it held only removed or
    held files; the import stage's reason counts it; "What leaves the inbox" says so.
- **`debate_cli`**: `commands/caselist.py`, where status renders held rows, held inbox uploads and
  the removals owed in the JSON, the table and a drift's hint; and `container.py`, where status is
  given the inbox.
- **Tests**
  - New: `packages/debate_core/tests/application/caselist/test_held_path_loose_ends.py` (22) and
    `test_held_path_inbox_copies.py` (6); `packages/debate_cli/tests/commands/test_caselist_status_held_paths.py` (6).
  - `packages/debate_cli/tests/test_caselist_publish.py`: `TestStatusOfAHeldPath` (3), and three keys
    added to `test_status_after_a_publish_exits_zero` (Deviation 2).
  - `tests/smoke/test_caselist_remove_smoke.py`, and its row in `tests/smoke/README.md` (Deviation 1).
  - Run by path, not collected: `write_held_path_files.py` and `read_held_path_files.py` (ac4).
- **Docs**: `docs/runbooks/caselist-removal.md`, step 9: where the held upload is, what status says,
  the publisher's withholding, the re-run's limit once the copy is gone, and the link.

## Deviations from the spec

1. **`tests/smoke/` is outside `constraints.packages`**, as it was for `v1-e30-t18` (its Deviation 1,
   accepted). Working agreement 5 asks a task that changes a user-facing surface to update its smoke
   checks, and `caselist status` changed. I added assertions to `v1-e30-t13`'s smoke check for the
   hold, between its import and its re-run, and a clause to its README row.
2. **One hand-written expectation of an earlier task gained three keys.** `v1-e30-t12`'s
   `test_status_after_a_publish_exits_zero` lists every key of a status snapshot. It now lists
   `held_rows`, `held_row_prefixes` and `held_row_requests` and checks they are `0, [], []`. Nothing
   else in it changed. This is the same kind of change as `v1-e30-t13`'s Deviation 3.

## Decisions and assumptions

1. **The held report is beside the verdict.** "Exit codes unchanged" could mean "no new exit code".
   I read it as: reporting a held item changes no exit code. A held row is not a difference between
   this machine and the bucket, and an older build that imported one usually published it too, so
   the bucket agrees. Making it drift would also change the pull's report and retention stages.
   `caselist status` exits 0 then, and its table and JSON say what is owed. Mutant 7 is the rule
   broken. The alternative is drift, `1`, and a pull that keeps every archive until the removal is
   run again.
2. **A held row is withheld like a withdrawn disclosure.** A hold is on a path and not on the bytes,
   like a disclosure-scoped entry, so the row withholds the manifest and the source's action follows
   the table as before. The bytes are uploaded under their digest before the manifest is withheld,
   exactly as a withdrawn copy's are, and running the removal again takes them out of the bucket.
   That is what makes the counts the same. The alternative, uploading nothing a held row names,
   would differ from a suppressed row's counts and could hold back another team's copy of the same
   bytes. The code is `MANIFEST_NAMES_SUPPRESSED_SOURCE`, as the PM asked ("same outcome"). The
   message names the held rows on their own, with their request.
3. **Status reads the inbox only when asked.** It means opening every archive there and hashing its
   members, which the pull's two comparisons have no use for. `caselist status` asks; the pull never
   does. With no path held it opens nothing. An archive it cannot read is passed over, because the
   removal's dry run already names it.
4. **A held upload in the inbox is a real member.** It sits at a held path, in an archive dated after
   the hold's date, and the list does not already stop it. A file the list stops is the removal's
   inbox step's (`v1-e30-t09`). A skipped member is never imported, so it is not an upload.
5. **Status names a held inbox upload by caselist and snapshot, never by archive.** An archive's name
   is a file name, which the forbidden list rules out of status output. Its caselist and date are
   already in every status line.
6. **Request ids are in the output.** They are already in every takedown record, they cannot hold a
   name (`REQUEST_ID_PATTERN`), and they are what tells the operator which removal to run again.
7. **The removal drops only a skipped member for the hold alone.** A held upload's bytes go on the
   list, under the request holding its path, when that removal is run again. A removal for another
   request that dropped it from a waiting archive first would leave that request nothing to find.
   Mutant 16 is that rule broken. An imported archive is never deleted for a skipped member alone
   (mutant 15).
8. **The pull takes out a weekly only if its import met a hold and stored nothing.** Every member is
   `SUPPRESSED`, at least one by a hold, every skipped member is junk withheld with them, and the
   copy is the bytes imported. It happens after the later manifests are measured again, so a failure
   there still leaves the copy for a re-import (`v1-e30-t18`).
9. **Two rules I first wrote are gone.** (a) The take-out also counted a skipped member at a held
   path. Only an archive with two held paths can exercise that, and dropping the rule only keeps an
   archive retention removes anyway. (b) The pull also asked a complete archive's import, which never
   holds removed or held files alone. Working agreement 8: a check that mutation cannot tell from its
   absence is removed.
10. **The probe of the agent's build was a one-off** in the scratch directory. It ran that build's
    importer over this build's records and is not committed. The cross-build scripts are committed,
    so the PM can run them again.
11. **Nothing read a real store or called AWS.** Every test, script and probe used fixtures, moto and
    temporary directories.

## Operator follow-ups

None. No command here is over two minutes, needs a credential, or changes anything outside the
worktree.

## Follow-up work

1. **The import writes a manifest row for a skipped member at a held path** (E30). Run on this
   build, the import of an archive holding a symbolic link at the removed path wrote a `member` row
   with `skip_reason` `SYMLINK` at that path. So the removed file's path, with its school and team
   code, is in the new manifest, and the publisher publishes it: its check reads stored rows only.
   The importer could withhold that row, as it withholds junk beside a suppressed file
   (`withheld_skipped_paths`). The removal's manifest rewrite and status would then need the same
   rule.
2. **Once a held upload's archive leaves the inbox, running the removal again cannot list its
   sha256** (E30; a ruling first). Retention or the take-out removes the copy, the import stored
   nothing, and the import writes no takedown record (`v1-e30-t13`'s Deviation 2, accepted). The path
   entry still refuses the upload at that path, but if the same bytes come back at another path, the
   list does not stop them. The runbook now says so. Closing it needs a record of the held digests
   that the weekly import may write, which is the question `v1-e30-t13` ruled on.
3. **Status's inbox read is unmeasured against a real inbox** (E30, the operator's). With a path held,
   `caselist status` opens every weekly and complete archive in the inbox and hashes their members.
   The fixtures take milliseconds. A real complete archive is hundreds of megabytes. Measuring it is
   a read-only run on the operator's data directory, which I did not touch.
4. **The pull's run record does not carry the held count**: still `v1-e34-t23`'s, as the PM filed it.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-16

**Notes:**

Accepted in full, with the phase `Succeeded`. The spec is unchanged. This merges before
`v1-e29-t09`, which then syncs.

**Decision 1 is the right reading of "exit codes unchanged".** A held row is not a difference
between this machine and the bucket, so it is reported beside the verdict, never in it. Making it
drift would have changed the pull's report and retention stages too. Mutant 7 holds the rule.

**Decision 2 is what I asked for, and it shows a gap in what I asked.** "Same outcome, same
counts" means a held row's bytes are uploaded under their digest before the manifest is withheld,
as a withdrawn copy's are. For a withdrawn disclosure that is right: the bytes are public
evidence that another team may hold. A held path is a privacy removal, and its bytes should not
reach the bucket on a held row's account alone. Today such a row exists only where a build before
`v0.1.0-dev.126` imported it, and that build will usually have published the bytes already. So
this is not a reason to hold the merge. It is filed as an E30 task (below), beside your
Follow-up 1, which is the same kind of leak.

**The work itself:**

* **The ac2 comparison builds both plans from one listing,** a held row and a withdrawn
  disclosure, and compares every outcome and count planned, dry and carried out. That makes
  "exactly as" a test rather than a claim.
* **Naming which older builds could write such a row, shown by running each one's importer:**
  `v0.1.0-dev.122`, the agent's build now, stores the held upload (`{'NEW': 3}`). That is the
  evidence that ac1 and ac2 guard something real.
* **The inbox table under ac3** answers "or the report says why it stays" case by case. The
  forbidden list is held by mutants 15, 18 and 19.
* **The ac4 scripts,** writing each build's files and reading them with each build's own reader,
  are committed, so they can be run again.
* **Working agreement 8 applied twice:** two rules deleted because mutation could not tell them
  from their absence, and four survivors turned into four tests. 27 of 27 are now caught.

**Rulings:**

* **Deviations 1 and 2:** accepted, as for `v1-e30-t18` and `v1-e30-t13`.
* **Decisions:** accepted. Request ids in status output (Decision 6) are right: they identify no
  one and are what tells the operator which removal to run again.
* **Follow-up 1 (the import writes a row at a held path for a skipped member, and the publisher
  publishes the path):** filed in the next PM batch as an E30 p2 task. It also covers Decision 2's
  gap: no bytes are uploaded, and no row at a held path is published, on a held row's account
  alone.
* **Follow-up 2 (a held upload's digest cannot be listed once its copy is gone):** filed as an
  E30 p3 task for a ruling. I will rule on it when the batch is written, against
  `v1-e30-t13`'s Deviation 2.
* **Follow-up 3 (status's inbox read, unmeasured):** no task now. With no path held it opens
  nothing, and the dev store holds no removal. It is measured the first time a real removal leaves
  a hold.
* **Follow-up 4:** still `v1-e34-t23`'s.

**Operator follow-ups:** none.

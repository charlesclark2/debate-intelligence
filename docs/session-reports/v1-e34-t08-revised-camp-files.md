# Session report: v1-e34-t08-revised-camp-files

| | |
|---|---|
| Task | `v1-e34-t08-revised-camp-files` — A camp file uploaded again upstream is fetched |
| Spec | [`plan_specs/v1/e34-caselist-sync/t08-revised-camp-files.yaml`](../../plan_specs/v1/e34-caselist-sync/t08-revised-camp-files.yaml) |
| Epic / release | `v1-e34-caselist-sync` / `v1.1` |
| Branch | `task/v1-e34-t08-revised-camp-files` |
| Session status | COMPLETE |

## Summary

`caselist pull` now fetches a camp file that a camp uploaded again. Under your definition, a listed
id that no row holds is a **revision** only when a release-manifest row at the same path names its
own OpenEv id (`openev-<id>-…`, the name the sync gives a download) and that id is missing from the
whole upstream listing. The revision is fetched like any other camp file. The run summary names it
by ids alone: `revision_of` on its selection, and `openev-512 -> openev-640` in the select stage's
reason, which the run log keeps. The old version's row, blob and delivery entry stay as they were.
A hand-import row, or a row whose id is still listed, holds the file exactly as before. The
removed-path hold is decided first and wins. It now also asks the suppression list about the old
row's own bytes, so a removal made on another machine (old row still here) holds the revision too.
A camp release holding only junk is now imported once and not again (ac5).

**Read first:** Deviation 1. A second test, from `v1-e34-t06`, pinned the same old behaviour, and I
inverted it as well. Then Deviation 3, on "both download caps".

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `invert` — Invert the pinned behaviour | Done | Commit `badffc3`: t07's pinned test inverted (and t06's sibling, Deviation 1), plus every new test, all red against the unchanged selection code. |
| `revision` — Fetch revisions, keep the earlier holds | Done | Commit `e44fe6e`, then `586d489` (a filter mutation showed did nothing, deleted) and `73e466f` (runbook). |

## Acceptance criteria

All test runs below are on the final tree (`73e466f`) unless they are marked red.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1** — A new id at the path of a camp file whose old id is no longer listed is downloaded and imported, and the run summary records it as a revision | PASS | **Red first**, on `badffc3` against the unchanged code: `uv run pytest packages/debate_core/tests/application/caselist/test_sync_skips_suppressed_downloads.py -k fetched_as_a_revision --no-cov` → `AssertionError: the revised camp file was not fetched` / `assert [512] == [512, 640]` / `1 failed in 2.54s`. **Green** in the full run below. The test checks: 640 fetched and stored (`blobs_stored == 1`); `revision_of == 512` on the selection and in the JSON; `1 taken as a revision of an id no longer listed (openev-512 -> openev-640)` in the select reason; both rows in the release manifest; 640 not fetched again on the next run. `test_a_revision_is_named_by_openev_ids_alone_in_the_summary_and_the_run_log` checks that the reason and the run-log record carry no word of the camp file's path or title. |
| **ac2** — A hand-imported camp file still listed under its id is not fetched again, and an id already imported by the sync is not fetched again | PASS | `test_revision_rule_leaves_a_hand_imported_file_still_listed_under_its_id_held` (no fetch, `already_imported`). `test_revision_rule_needs_a_row_naming_its_own_id_and_a_hand_import_names_none`: the hand-imported file's original id is gone and 640 sits at its path; still held, nothing fetched (your "nothing is re-downloaded on a guess"). The inverted ac1 test's second run: 640, imported by the sync, is `already_imported` and not fetched. `v1-e34-t06`'s own tests (`test_openev_a_camp_file_imported_by_hand_…`, `…_matched_through_spelling_differences`, `…_the_folder_decides_…`, `…_matched_by_its_id`, the property `test_openev_matching_never_holds_a_listed_file_nobody_imported`) pass unchanged. |
| **ac3** — A new id at the path of a removed file is still held back as `same_path_as_a_removed_file`, and after unsuppress it is fetched | PASS | t07's `test_a_removed_file_uploaded_again_under_a_new_id_is_held_back` passes unchanged. New tests: `test_a_revision_of_a_file_removed_on_another_machine_is_held_back_as_removed` (old row still here, removal only in the bucket's list: held, not fetched); `…_the_delivery_record_forgot_is_held_back_by_its_old_row` (record deleted too: held through the row's own digest); `test_after_unsuppress_a_revision_of_a_file_removed_on_another_machine_is_fetched` (fetched, `revision_of == 512`); `test_after_unsuppress_a_new_id_at_the_path_of_a_file_removed_here_is_fetched` (a local removal takes the old row out, so 640 is held and then fetched as a plain new file). |
| **ac4** — t07's pinned test is inverted rather than deleted, the change is shown failing first, and each guard is mutated and shown caught | PASS | Inverted in place, renamed `…_is_fetched_as_a_revision`. Its docstring names the old test. Red output is under ac1. Mutation table below: 5 of 5 guards caught on `73e466f`, each run on a fresh `HYPOTHESIS_STORAGE_DIRECTORY`, in two batches of 44 s and 28 s. |
| **ac5** — A camp release holding only junk is recognised as handled: imported once, then not again, shown failing first | PASS | **Red first**, on `badffc3`: `uv run pytest packages/debate_core/tests/application/caselist/test_sync_fetches_revised_camp_files.py -k junk --no-cov` → `[inbox-copy-gone] AssertionError: the junk-only release was downloaded again / assert [950, 950] == [950]` and `[inbox-copy-kept] AssertionError: the junk-only release was imported again / assert ('openev 2026-policy',) == ()`, `2 failed in 7.37s`. The retention test showed the same on a second run, red: `assert ('openev 2026-policy',) == ()`. **Green** after `e44fe6e`. Retention before and after: see Decisions. |
| Node `invert`: the revision test is shown failing before the change (custom) | PASS | The ac1 red output above. t06's inverted sibling, red on `badffc3`: `At index 0 diff: <SelectionDecision.ALREADY_IMPORTED: 'already_imported'> != <SelectionDecision.DOWNLOAD: 'download'>`, `1 failed in 3.41s`. |
| Node `revision`: `uv run pytest packages/debate_core/tests/application/caselist -k "revision or removed"` | PASS | `29 passed in 8.17s`. Those 29 include the 9 new revision and removed-path tests and the inverted one. |

### Mutation results

The mutant script (scratchpad, not committed) refuses to run unless `caselist_sync.py` is committed.
It applies one textual change, runs `packages/debate_core/tests/application/caselist` and
`packages/debate_core/tests/application/test_caselist_sync.py` (541 tests, `-n auto`) with
`HYPOTHESIS_STORAGE_DIRECTORY` set to a new, empty directory, then restores the file from a saved
copy and checks its sha256. Every catch below was a failing assertion; none was an error at
collection. No catch depended on the one Hypothesis property in these files, and I don't offer that
property as evidence for this task.

| Guard | Mutant | Result on `73e466f` | Failing for its reason |
|---|---|---|---|
| The old id is no longer listed | `named is not None and named not in listed_anywhere` → `named is not None` | CAUGHT, 1 failed, 18.3 s | `test_revision_rule_needs_the_old_id_gone_from_the_whole_listing_not_only_its_release`: `assert [512, 640] == [512]` |
| The old row names its own id | → `named not in listed_anywhere` (a hand-import row counts) | CAUGHT, 8 failed, 13.8 s | Both new hand-import tests and six of `v1-e34-t06`'s: `a camp file imported by hand was fetched again`, `assert [512] == []`, `assert [640] == []` |
| The removed-path hold comes first | the revision fetched without `_judge_unrecorded` being asked | CAUGHT, 4 failed, 14.2 s | Both removed-on-another-machine tests: `a new id at the path of a removed file was fetched`, `assert [512, 640] == [512]`. Also the unsuppress test (its first, held run) and the unreadable-list test |
| ac5: a junk-only release is handled | the `not delivery.member_sha256` return deleted | CAUGHT, 3 failed, 14.0 s | Both ac5 cases and the retention test: `the junk-only release was imported again`, `assert ('openev 2026-policy',) == ()` |
| The hold asks the old rows' own bytes (mine) | the `earlier.extend(…digests_named_by_id…)` line deleted | CAUGHT, 1 failed, 13.8 s | `…_the_delivery_record_forgot_is_held_back_by_its_old_row`: `a new id at the path of a removed file was fetched` |

**One check was deleted instead of tested.** On `e44fe6e`, `_match_listed_openev` also left held ids
out of `revisions`. Removing that filter: SURVIVED, 541 passed, 15.3 s, fresh database. The
selection asks `held` first, so a held id among the revisions is still held. I deleted the filter
in `586d489` and the docstrings now say that `held` decides first (working agreement 8). The first
mutation run, on `e44fe6e`, also caught the other five guards, with the same tests failing.

### Checks on the final tree (`73e466f`, report commit aside)

| Command | Result |
|---|---|
| `uv run pytest -m "not slow and not live" packages tests -n auto` | `4510 passed, 1 skipped, 1 warning in 94.92s`; a second run `in 65.97s`. The skip is the existing parser eval. The warning is `pytest_socket`'s `A test tried to use socket.getaddrinfo` from `tests/smoke/test_smoke_harness.py::test_pytests_own_process_has_no_network_in_an_offline_check`, which tries the network on purpose to show it is blocked |
| `uv run pyright` | `0 errors, 0 warnings, 0 informations` |
| `uv run ruff check .` / `uv run ruff format --check .` | `All checks passed!` / `523 files already formatted` |
| `uv run lint-imports` | `Contracts: 11 kept, 0 broken.` |
| `uv run scripts/check_command_blocks.py --base origin/dev` | `OK: no '#' comments in 185 shell code blocks in 107 Markdown files (1 session reports changed since origin/dev)` |
| `uv run scripts/validate_specs.py` (after setting the phase) | `OK: 310 files, 38 epics, 252 tasks, 20 releases`; `--require-succeeded v1-e34-t08-revised-camp-files` → `v1-e34-t08-revised-camp-files: Succeeded` |
| `scripts/task sync v1-e34-t08-revised-camp-files` | `Current branch task/v1-e34-t08-revised-camp-files is up to date.` (I checked first that the branch is not on the remote, so the sync could not push.) |

## Files changed

- **`debate_core.application`**: `caselist_sync.py`.
  - `_held_openev_ids` becomes `_match_listed_openev`, which returns the held ids and the revisions.
  - `_RecordedOpenEv.digests_named_by_id`.
  - The revision and junk-only branches in `_select_openev` and `_judge_unrecorded`.
  - `OpenEvSelection.revision_of`, `_revision_sentence`.
  - The module docstring gains "A camp file that changed upstream", and the `RUN_SUMMARY_SCHEMA_VERSION` docstring records the additive keys.
- **Tests** (`packages/debate_core/tests/application`):
  - `caselist/test_sync_fetches_revised_camp_files.py`: new, 12 tests.
  - `caselist/test_sync_skips_suppressed_downloads.py`: the pinned test inverted, a `release_member_paths` helper, and one vacuous assertion corrected (Deviation 2).
  - `caselist/test_inbox_retention.py`: two tests, a revision's retention and the junk-only release's.
  - `test_caselist_sync.py`: t06's sibling test inverted (Deviation 1); the property test calls the renamed function.
- **Docs**: `docs/runbooks/caselist-scheduled-sync.md`. What the select stage's revision sentence means; the removed-path hold wins over a revision, including a removal made on another machine; the junk-only release in the inbox.

## Deviations from the spec

1. **A second test pinned the old behaviour, and I inverted it too.** `v1-e34-t06`'s
   `test_openev_a_sync_named_file_whose_id_is_no_longer_listed_is_matched_by_its_path` asserted
   that a row `openev-417-…` holds a new id 999 at its path while 417 is listed nowhere. That is
   your definition of a revision, word for word, so it could not pass beside ac1. The forbidden list
   names only t07's test. I inverted this one in place as well, renamed
   `…_marks_a_revision_at_its_path`, now asserting `download` with `revision_of == 417`, and showed
   it red first. It is not one of the cases ac2 protects: its old id is not listed.
2. **One t07 assertion could not fail, and I corrected it.**
   `assert not world.local.blob_path_for(ESTUARY_SHA256).exists()`
   (`test_with_the_skip_blind_the_importer_still_refuses_the_removed_file`) looks for a blob at
   `blobs/<sha>`. The snapshot store keeps blobs at `blobs/sha256/<2>/<2>/<sha>`, so the path never
   exists and the check passed whatever the importer stored. I found it because my own
   positive version of the check failed while the blob existed. It now reads
   `FsSnapshotStore(world.data_dir).path_for(ESTUARY_SHA256)`. The same expression, unnegated, passes
   in `test_a_revision_leaves_the_old_versions_row_and_delivery_entry_as_they_were`, where the blob
   is present, so it tracks the file in both directions. No other test uses `blob_path_for` with a
   bare digest.
3. **"Both download caps."** A revision is an ordinary `download` decision and goes through the same
   download loop as every camp file, with no path of its own. The limits on that loop are the
   transport's two pacing rules: a minimum interval between requests, and at most
   `downloads_per_minute` downloads in any rolling 60 seconds, which archive and OpenEv downloads
   share (`integrations/opencaselist/pacing.py`). The daily bulk-download ledger (5 per rolling 24
   hours, upstream's `weeklyLimiter`) counts weekly-archive downloads only, and no camp download has
   ever counted against it. So a revision counts against exactly what any camp download counts
   against. If "both caps" meant the daily ledger, that would change every camp download, not this
   task's, and I have not done it.

## Decisions and assumptions

- **How the release manifest and the delivery record represent the old and new versions: no change
  to either.**
  - *Manifest.* The importer keys a release's rows by path. The new id's row,
    `openev-640-TSF-…`, lands beside `openev-512-TSF-…`, and the old row is neither deleted nor
    rewritten. Each row names its own id, and ids are `AUTO_INCREMENT`, so the manifest already
    says which version came later. I added no key. The manifest is published to the bucket and read
    by publish, status, removal and retention, and later by E31 and E32. A new key there changes
    every reader's contract, and nothing in this task would read it.
  - *Delivery record.* 512's entry is untouched (asserted). 640's entry is written by its import
    like any other. When the paths are the same, both entries carry the same `path_sha256`, which
    already links them as a recorded fact rather than a claim. I added no `revision_of` key there.
    That would be a field nothing reads, and an older build rewriting the file would drop it.
  - *The link that is recorded* is in the run summary and the run log: `revision_of` on the
    selection, and `openev-<old> -> openev-<new>` in the select reason. Ids only.
  - **Schema versions:** `RUN_SUMMARY_SCHEMA_VERSION` stays 2. `revision_of` is an additive key
    (`null` when the file is not a revision), under t07's rule: it changes no existing key, and
    nothing reads a summary back. The constant's docstring now lists every key added under that
    rule. `OPENEV_DELIVERIES_SCHEMA_VERSION` stays 1, since the file is unchanged. A bump there
    would also make an older build discard the whole record and fetch removed files again.
- **The removed-path hold also asks about the old rows' bytes.** t07's hold asks the list about
  what the delivery record remembers at the new id's exact path. A revision has one more source of
  truth: the old row's own `sha256`. Without it, an old id the record does not know (imported before
  `v1-e34-t07`, or the record lost), removed on another machine, would let the revision be fetched,
  which the forbidden list rules out. `test_…_the_delivery_record_forgot_is_held_back_by_its_old_row`
  is the case. A mutation deleting it is caught.
- **"No longer listed" means the whole listing,** as you wrote it, not the release's own part of it.
  The difference is real: an id whose tags no longer name an event is in no release this run reads,
  but upstream still lists it. That id was not deleted, so a file at its path is not its revision.
  This is the only case that catches the "no longer listed" mutant. While an old id is listed in the
  same release, its row holds it by id and never reaches the path match. The test's setup (an id's
  tags changing) may not happen upstream, and the docstring says so.
- **A revision with the list unreadable waits** as `suppression_list_unreadable`. Before this task
  it was held as `already_imported`. Whether the old version was removed on another machine cannot
  be known, so it is not fetched on a guess, as t07 does for any re-upload. An expired SSO session
  does not cause this: the pull falls back to this machine's copy.
- **Several old versions at one path** (a file revised twice): every unlisted id whose row matches
  is recorded. The hold asks about each one, and `revision_of` is the highest id, the upload the new
  one most recently replaced.
- **ac5's rule:** a remembered id whose delivery entry names no member is `already_imported`. An
  entry is written only once an import completes, and an empty member set means the importer
  classified nothing: junk alone. Same id, same bytes, because upstream has no update route.
- **Inbox retention and the junk-only release (your question):** no retention change. ac5 does not
  need one, and t11's tests pass unchanged.
  - *Before this task:* retention kept it as `not_imported` on every run, because no row with a
    classification came from its bytes. With the copy kept, every pull imported it again (and
    reported `nothing_new: false`). With the copy gone, every pull downloaded it again.
  - *After:* retention still keeps it as `not_imported`, and no pull imports or fetches it again.
    `test_retention_keeps_a_camp_release_of_junk_alone_and_the_next_pull_does_not_import_it_again`
    pins both halves.
  - It therefore stays in the inbox for good (Follow-up 1).
- **A revised camp file leaves the inbox only on t11's conditions.**
  `test_retention_removes_a_revised_camp_file_only_on_the_conditions_any_camp_download_meets`: with
  its release not confirmed in the bucket, 640 stays `not_confirmed`; confirmed, it is removed,
  named `sha256 <prefix>`. 512, whose copy had already gone, is not fetched again.
- **Naming.** Nothing added carries a title or an inbox name. The selection's existing `inbox_name`
  does, and `v1-e34-t12` removes it.

## Operator follow-ups

None. No command here needs credentials or runs longer than about 2 minutes. The full fast suite took
95 s.

## Follow-up work

1. **A junk-only camp release stays in the inbox for good** (E34, `v1-e34-t11`'s conditions). It is
   kept as `not_imported` in every summary, which reads as though a later run might import it; none
   will. It may hold a Word `~$` lock file, which stores the name of whoever had a document open
   (`v1-e30-t09` Decision 5). Whether retention should remove a camp download whose delivery entry
   names no member is your call. It would be a new removal condition, so I did not add one.
2. **A new id at a removed file's path whose copy is already in the inbox is imported, not held**
   (E34, `v1-e34-t07`'s hold). In `_judge_unrecorded`, an id with an inbox copy and no record entry
   returns before the path hold is asked. The copy can only be there if it was downloaded before
   this machine knew of the removal. This predates this task and applies to any new id, revisions
   included. I left it, because changing it changes t07's hold.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

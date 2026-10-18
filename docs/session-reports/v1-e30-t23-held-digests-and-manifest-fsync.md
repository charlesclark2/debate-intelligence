# Session report: v1-e30-t23-held-digests-and-manifest-fsync

| | |
|---|---|
| Task | `v1-e30-t23-held-digests-and-manifest-fsync` — Held digests are remembered once the copy is gone, and a manifest write survives a power cut |
| Spec | [`plan_specs/v1/e30-caselist-ingestion/t23-held-digests-and-manifest-fsync.yaml`](../../plan_specs/v1/e30-caselist-ingestion/t23-held-digests-and-manifest-fsync.yaml) |
| Epic / release | `v1-e30-caselist-ingestion` / `v1.1` |
| Branch | `task/v1-e30-t23-held-digests-and-manifest-fsync` |
| Session status | COMPLETE but for one sign-off. ac3's policy sentence is yours to approve, so the Goal stays `InProgress` and ac3 is NOT RUN |

## Summary

**(1) Held digests.** The import now writes each upload it refuses at a held path to
`held-digests.jsonl`, beside `path-holds.jsonl`. A line holds the upload's sha256, the held path's
digest and the request holding the path, and nothing else. Running the same removal again reads the
record and lists each digest under its request, even when the archive has left the inbox. The
holder rule is t16's and t22's: bytes held at no other path are suppressed whole; bytes another live
path holds are withdrawn from the held path only. After the re-run, the same bytes arriving at
another path are stopped at import. `v1.1.0-dev.18`, the agent's build, reads a data directory and a
bucket holding the record and ignores it.

**(2) The directory fsync.** `write_manifest_text` now fsyncs the directory after the rename. Every
manifest writer on this machine goes through it.

**(3) PM amendment 2026-10-18.** The publisher withholds a manifest with a skipped member's row at
a held path, with the outcome and code of a held stored row. `caselist status` gives the removal
hint for it with no change to status: `BESIDE_THE_REWRITE["a held skipped row"]` is now `True`, and
the test failed until the publisher changed.

**Four things to look at first:**

1. **ac3 is NOT RUN, by your notes.** The runbook is changed. The policy sentence I propose is under
   PM questions, with the runbook text I removed. The Goal stays `InProgress` until you approve or
   reword it.
2. **The import writes this machine's copy alone, and the removal writes the bucket's** (Decision
   3). Only the takedown credential writes under `manifests/_suppression/`. The pull's list appends
   locally even with a live session. The first thing a removal's execution does is give the bucket's
   copy what this machine's holds.
3. **`withholding_rows` now names a held skipped row by its request id** (Decision 9). A held
   skipped row has no digest. This kept status untouched, as your notes expected, at the cost of a
   tuple that holds digests and request ids together.
4. **One of my commits went in with a pyright error** (Deviation 2). I piped pyright into `tail`
   inside an `&&` chain, the mistake t19 reported. It was fixed one commit later, and no reported
   run was made at that commit.

Known, not mine: `tests/evals/parser/test_parser_eval.py::test_the_labeled_pr_subset_holds_the_baseline`
fails on this Mac until the parser-evaluation baseline is written. I did not investigate it.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `held-digests`: Held digests and manifest fsync | Done | Items (1), (2) and (3), the runbook, and the cross-build check. Its criterion passes: `508 passed` |

## Acceptance criteria

Commit ids are relative to `dev` at `5d3d398`, after `scripts/task sync`. Before the sync, the start
commit was `3ebeaab`; the sync changed only `ROADMAP.md` under it. "The start commit's source" is
`git archive 3ebeaab packages/debate_core/src packages/debate_cli/src`, put first on `PYTHONPATH`.
Before each red run I checked that a module's `__file__` resolved to that copy. Every test uses moto
or a directory standing in for the bucket, temporary data directories and, in the new files, a
temporary `HOME`. No test or command read the operator's `~/.debate-research`, `~/.aws` or
LaunchAgents, and none touched AWS or the network.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1**: after a held upload's copy is gone, running the removal again lists its digest under its request, by test shown failing first; an earlier build reading the data directory still works, by test | PASS | **Red first.** The red commit is `2d3345a`. Its three new core test files and the CLI hint test, run on the start commit's source → `18 failed, 12 passed in 8.36s`, every failure an assertion. The item (1) failures: no record (`assert [] == [{'schema_version': 1, 'sha256': 'c8c495e6…', 'disclosure': 'de162f10…', 'request_id': 'RM-2026-01'}]`); the re-run does not list it (`AssertionError: the re-run does not list the held upload / assert None is not None`); the same bytes at another path come back (`AssertionError: the bytes came back in at another path / assert 0 == 1`); a record that cannot be written does not fail the import (`Failed: DID NOT RAISE OSError`). The 12 that pass are the "must not" cases (a dry run, a path no removal holds, another request) and the hint test's three other cases. The pull test, added later, was red on that source the same way (`assert [] == [{…'RM-2026-01'}]`). **Green.** `test_removal_lists_held_digests.py` (17 tests) covers these. *The point*: `test_running_the_removal_again_lists_a_held_upload_whose_archive_has_left_the_inbox` plans the upload as `held_at_import`/`remove` with one whole-file entry under `RM-2026-01`. `…executing_it_puts_the_digest_on_the_list_in_both_copies_and_the_record_in_the_bucket` checks both copies. `test_after_the_re_run_the_same_bytes_at_another_path_are_stopped_at_import` gets `SUPPRESSED 1`, with no blob. *The holder rule*: `test_bytes_another_path_holds_are_withdrawn_from_the_held_path_only` gives one entry, disclosure the held path's digest, and `kept_in == ("testcl26",)`. `…are_never_put_on_the_list_whole` shows no whole entry; the other team's row and blob stay; `withdrawals.jsonl` names `testcl26`. `…still_import_at_a_path_nothing_holds` shows the other team's bytes are not stopped. *The record*: idempotent on re-import, nothing on a dry run, named no one. A pull writes this machine's copy and not the bucket's. The record's own 17 tests are in `test_removal_held_digest_record.py`. **Earlier build.** `check_an_older_build_reads_this_builds_files.py`, against `v1.1.0-dev.18` (`0268cf7`, by `git archive`): five checks, exit 0. With the record in both places, the first check prints `import of the next week: SUPPRESSED 4, completed` and `publish: succeeded True; status in sync: True`. The new check prints `removal of RM-2026-02 run again beside the record: 1 source(s) planned; the same plan as without it: True` and `executed: completed True; the record as placed, both copies: True`. The start commit prints the same. This build prints `2 source(s)` and `False`, because it lists the upload. t13's `written_by_this_build/` was not regenerated, because its history writes no record (Decision 10). Its byte-for-byte test still passes |
| **ac2**: the manifest writer fsyncs the directory after the rename, by test | PASS | `test_manifest_write_fsyncs_its_directory.py` uses a recording `os.fsync`, `os.open` and `os.replace`, with no real power cut. It asserts the exact sequence `fsync file (inode N)`, `replace <manifest>`, `open <directory>`, `fsync directory <directory>`, for `write_manifest_lines` and `write_manifest_text`. Further tests cover a rewrite over an existing manifest, and a directory fsync that fails raising `OSError`. Red on the start commit: `Right contains 2 more items, first extra item: ('open', …/manifests/testcl26)`, and `Failed: DID NOT RAISE OSError`. No `F_FULLFSYNC` |
| **ac3**: the runbook's note that the list cannot stop such bytes is removed, and the policy's list of sidecar records names the new one, in a sentence the PM approves | NOT RUN (runbook part done) | The runbook's note is removed, and the new text says where the import records the bytes and what the re-run lists (Files changed). The policy is yours: my proposed sentences and the removed runbook text are under PM questions. This closes when you approve or reword them |
| **ac4**: (3) by tests shown failing first, (a) such a manifest is withheld with that code and nothing of it reaches the bucket, and (b) status gives the removal hint, not the publish hint | PASS | **Red first** (same run as ac1): `assert <ManifestOutcome.UPLOADED: 'uploaded'> is <ManifestOutcome.WITHHELD: 'withheld'>`; the dry run `assert True is False`; status `manifest_withheld=False`; and `test_the_hint_is_the_removals_exactly_when_the_publish_withholds_the_manifest[a held skipped row]` failed. **(a)** `test_held_skipped_rows_withhold_the_manifest.py`. An earlier build imports the week with a link at the held path, and this build's publisher gives `WITHHELD`, `MANIFEST_NAMES_SUPPRESSED_SOURCE`, `failure_codes == (that code,)` and `succeeded False`. The manifest is absent from the bucket, and every key and version in the bucket is what it was before the publish. The message is `1 skipped member row(s) at a path a removal holds (RM-2026-01)` with the re-run fix, and names no one. A link at a path nothing holds still publishes, and the re-run lets the week publish without the row. **(b)** `BESIDE_THE_REWRITE["a held skipped row"]` is `True`, and that case now passes; status's `manifest_withheld` is `True`. No status code changed |
| Node `held-digests`: `uv run pytest packages/debate_core/tests -k "caselist and (removal or manifest)"` | PASS | `508 passed in 32.45s`, as the spec writes it, after the sync |
| Full suite, in eighths (`uv run --frozen pytest -n auto -m "not slow and not live" --part K/8`), at load 4 to 11 | PASS but for the known failure | Each part ran under a hard stop at 110 s and finished in 31 to 39 s: `1035 passed`; `1039 passed`; `1036 passed, 2 warnings`; `1031 passed, 1 warning`; `1027 passed`; `1036 passed, 1 xfailed`; `1 failed, 1036 passed`; `1034 passed, 1 xfailed`. The one failure is the known parser-evaluation test. The warnings are `pytest_socket`'s |
| Lint, types, contracts, docs | PASS | `ruff format --check .`: 810 files already formatted. `ruff check .`: all checks passed. `uv run --frozen pyright`: `0 errors`. `lint-imports`: `12 kept, 0 broken`. `check_thin_handlers.py`: 22 within 25 statements. `docs_index.py --check-descriptions`: 35 described. `check_command_blocks.py --base origin/dev`: OK. `validate_specs.py`: OK |

### Mutation runs

Each run applied one textual change to committed source and ran the 107 tests of nine selections
(108 after the test added for row 15):

- the six new or changed core files, with `test_held_rows_publish_nothing.py` and
  `test_removal_path_hold_plan.py`;
- the CLI renderer file;
- the CLI hint test class.

Flags: `-p no:randomly -p no:cacheprovider --no-cov -n 4`. The unmutated selection took 13 s. The
driver refuses a mutant whose text is not there exactly once. It gives every run a new, empty
`HYPOTHESIS_STORAGE_DIRECTORY` (working agreement 8; none of these tests is a Hypothesis property).
It restores the file from a byte copy in a `finally`, then checks its sha256 and `git diff --quiet`.
`git status --porcelain` was empty after every batch. Every catch below is a failing assertion; only
row 26 also had errors.

| # | Mutation | Result | First failing test |
|---|---|---|---|
| 1 | The import records no held upload | CAUGHT, 12 failed | `test_the_import_records_the_upload_it_holds_by_digest_and_request` |
| 2 | A dry run records it | CAUGHT, 1 failed | `test_a_dry_run_import_records_nothing` |
| 3 | The line carries the removed file's sha256, not the upload's | CAUGHT, 9 failed | the same as row 1 |
| 4 | A list of another kind drops the entry | CAUGHT, 1 failed | `test_a_list_of_another_kind_refuses_an_entry_too` |
| 5 | A copy keeping no record drops the entry | CAUGHT, 1 failed | `test_a_list_that_keeps_no_record_beside_it_refuses_an_entry_rather_than_dropping_it` |
| 6 | **The pull's list appends to the union**, the bucket included | CAUGHT, 4 failed | `test_the_pulls_list_appends_to_this_machines_copy_alone_with_a_login` |
| 7 | The pull's list reads this machine's copy alone, even with a login | CAUGHT, 2 failed | `test_the_pulls_list_appends_without_a_login_and_reads_this_machines_copy` |
| 8 | **The re-run reads no record** | CAUGHT, 6 failed | `test_running_the_removal_again_lists_a_held_upload_whose_archive_has_left_the_inbox` |
| 9 | Any request's record is this request's | CAUGHT, 1 failed | `test_another_requests_removal_does_not_list_it` |
| 10 | A hold on any file stands for the named one's | CAUGHT, 1 failed | `test_a_removal_of_another_file_under_the_same_request_does_not_list_it` |
| 11 | A digest the list already stops is planned again | CAUGHT, 1 failed | `test_running_it_a_third_time_has_nothing_left_to_do_for_it` |
| 12 | **A held path the record names makes no withdrawal** | CAUGHT, 2 failed | `test_bytes_another_path_holds_are_withdrawn_from_the_held_path_only` |
| 13 | A withdrawal appends no entry for that path | CAUGHT, 2 failed | the same |
| 14 | **That path counts as a live one, so nothing is removed whole** | CAUGHT, 4 failed | the row 8 test |
| 15 | A path the inbox also shows is appended a second time | **SURVIVED, then CAUGHT** | `test_a_held_copy_the_inbox_still_shows_is_withdrawn_from_the_held_path_once` |
| 16 | The withdrawal record leaves that path out | CAUGHT, 2 failed | `test_bytes_another_path_holds_are_never_put_on_the_list_whole` |
| 17 | The execution gives the bucket's copy nothing | CAUGHT, 2 failed | `…executing_it_puts_the_digest_on_the_list_in_both_copies_and_the_record_in_the_bucket` |
| 18 | The plan prints them among the files the request names | CAUGHT, 1 failed | `test_they_are_not_counted_among_the_files_the_request_names` |
| 19 | The plan prints no section for them | CAUGHT, 1 failed | `test_they_have_a_section_of_their_own_with_what_happens_to_each` |
| 20 | The JSON leaves the held path out of a withdrawal | CAUGHT, 1 failed | `test_the_json_names_them_by_inclusion_and_a_withdrawal_by_the_held_paths_digest` |
| 21 | **No directory fsync** | CAUGHT, 4 failed | `test_rewriting_a_manifest_fsyncs_its_directory_too` |
| 22 | The directory fsync comes before the rename | CAUGHT, 2 failed | `test_the_file_is_fsynced_then_renamed_then_its_directory_is_fsynced[write_manifest_lines]` |
| 23 | A failed directory fsync is swallowed | CAUGHT, 1 failed | `test_a_directory_fsync_that_fails_is_a_write_that_failed` |
| 24 | **A held skipped row withholds nothing** | CAUGHT, 5 failed | `test_the_publisher_withholds_a_manifest_with_a_links_row_at_the_held_path` |
| 25 | The plan carries no held skipped row | CAUGHT, 5 failed | the same |
| 26 | Every skipped row counts as held | CAUGHT, 11 failed and 2 errors | `test_a_manifest_with_a_links_row_at_a_path_no_removal_holds_is_published` |
| 27 | The message leaves the skipped row out | CAUGHT, 1 failed | `test_its_message_names_the_request_and_the_fix_and_no_one` |

Row 15's survivor was a missing test, as I expected when I wrote the mutant. No test had an upload
that both the record and a waiting inbox archive show at the held path. The effect is real but
cosmetic: identical suppression lines merge on disk, but the plan counted the entry twice and
printed the path twice. The test was seen passing unmutated, then the mutant was run again.

Before this table I removed three checks of my own that decided nothing (`b2d3965`, now `468f049`):

- **`HeldDigestEntry.refused_by`.** It repeated the planner's own filters: the hold is found by the
  entry's path digest, and both the entry and the hold are this request's.
- **The held path's caselist among `touched_caselists`.**
- **The held path's caselist among `_objects`' withdrawal caselists.** A digest known only from the
  record has no stored copy at its held path, so neither caselist addition changed anything.

## Files changed

- **`debate_core.application`**
  - `ports/suppression.py`: `HELD_DIGESTS_FILENAME`, `HeldDigestEntry` (sha256, the held path's
    digest, request id; extra keys forbidden), the `HeldDigestList` protocol, and the module
    docstring's sixth record.
  - `caselist/suppression.py`: the record beside every copy in `RecordedSuppressionList`
    (`held_digests`, `append_held_digests`, `reconcile`). `LocalFallbackSuppressionList` reads it
    with the path holds' fallback and appends to this machine's copy alone. Also `HELD_DIGESTS_KEY`,
    `read_held_digests` and `record_held_digests`.
  - `caselist/pipeline.py`: a held member's line is appended as it is met, never on a dry run.
  - `caselist/removal_plan.py`: `Inclusion.HELD_AT_IMPORT`, `PlannedSource.held_at_import`, and
    `_refused_at_import`. `_plan_other_source(refused_at=…)` withdraws from a path known by its
    digest alone, the withdrawal record names its caselist, and there is a new docstring section.
  - `caselist/removal_service.py`: the execution's first step gives every copy what another holds.
  - `caselist/manifest.py`: `write_manifest_text` fsyncs the directory after the rename.
  - `caselist/publish_plan.py`: `SnapshotPlan.held_skipped_rows`, which counts in
    `withholding_rows`, and a docstring paragraph.
  - `caselist/publish_service.py`: the withheld message's clause for a held skipped row.
- **`debate_cli`**: `commands/caselist_remove.py`, the plan's *REFUSED AT IMPORT AT A HELD PATH*
  section. The other changes there:
  - those files are kept out of the named files' sections;
  - each withdrawal names its held path by digest;
  - the covers line and the confirmation count them;
  - the JSON's `withdrawn_disclosures` holds such a path. No new JSON key.
- **Tests**
  - New: `test_removal_lists_held_digests.py` (17), `test_removal_held_digest_record.py` (17),
    `test_held_skipped_rows_withhold_the_manifest.py` (6), `test_manifest_write_fsyncs_its_directory.py`
    (4), `test_removal_held_digest_files_are_this_builds.py` (3), and in `debate_cli`,
    `test_caselist_remove_held_at_import_output.py` (4).
  - Changed: `test_removal_path_hold_plan.py` (Deviation 1) and `test_caselist_publish.py` (the
    flip).
  - Not collected: `held_digest_scenario.py` and `write_held_digest_files.py`.
    `check_an_older_build_reads_this_builds_files.py` places the record in every check and has one
    check more.
  - Stored: `stored_suppression_lists/held_digests_written_by_this_build/{local,bucket}/held-digests.jsonl`,
    written by this build. The directory's README gives the command and the results.
- **Docs**: `docs/runbooks/caselist-removal.md`. Step 8 checks the record in both places, and step 9
  says the import records the bytes. Step 9 also says a manifest with a held skipped row is now
  withheld, and the re-run lists *REFUSED AT IMPORT AT A HELD PATH*. The note that the list cannot
  stop bytes whose archive has gone is removed (PM questions).
- **Spec**: item (3) and ac4, the PM's amendment, in the first commit.

## Deviations from the spec

1. **One of `v1-e30-t13`'s hand-written expectations changed, because the ruling reverses its
   premise.** `test_the_import_appends_nothing_to_the_list_or_beside_it` asserted that the import
   left every file under `suppression/` byte for byte as it was, which was t13's Deviation 2. It is
   now `…appends_nothing_to_the_list_and_beside_it_only_the_upload_it_held`. Every other file is
   still byte for byte as it was, and `held-digests.jsonl` holds one line with exactly the four keys.
2. **One commit went in with a pyright error.** At `38294f3` (now `b11b0be`), ruff split an import
   and left its `# pyright: ignore` on the wrong line. I had piped pyright into `tail` inside the
   commit's `&&` chain, so its failure did not stop the commit. I fixed it in the next commit
   (`b8ebf20`) and made no reported run at that commit. Every check since ran bare.

## Decisions and assumptions

1. **The file is `held-digests.jsonl`.** It sits beside `path-holds.jsonl`, in both places, and
   pairs with it: a path hold holds a path, and these are the digests it held there. "Held" is the
   word the import report (`held_at_removed_paths`), status (*HELD UPLOADS*) and the runbook already
   use for an upload refused at a held path. I did not choose `held-uploads.jsonl`, because an
   upload suggests a file and its name, which the record must never hold. A new line shape inside
   `path-holds.jsonl` was not an option: every build since t13 reads that file, and its model
   forbids unknown keys.
2. **A line is the upload's sha256, the held path's digest and the request: no caselist, no
   date.** The hold that refused the upload gives the caselist. Without a date, the same upload held
   again is the same line, so **re-importing an archive appends nothing new**: the set-union append
   adds a line once. That is idempotence by construction, and it is tested.
3. **The import writes this machine's copy; the removal writes the bucket's.** `caselist import`
   holds only this machine's list. The pull's `LocalFallbackSuppressionList` appends to this
   machine's copy whether or not the session is live, because only the takedown credential may
   write under `manifests/_suppression/`. That covers t13's Deviation 2 reasons 1 and 2. The
   removal's execution first gives every copy what another holds, which writes the bucket's copy
   before anything is deleted. The copies differ only between an import and the next removal, and
   the removal, the record's one reader, reads them as one. Following path-holds exactly would have
   had the import write the union. That fails on the everyday credential, so I took this one
   difference from the path holds.
4. **When it is written: as the member is met, before the run goes on.** The archive cannot leave
   the inbox until the import has finished: the pull's take-out comes after the import, and
   retention later. An import that cannot write the line fails, with nothing of the held upload
   stored, rather than losing the only record of the bytes. A dry run writes nothing.
5. **The holder rule is the later uploads' own function**, `_plan_other_source`, given the record's
   paths as taken paths known by digest alone.
   - Held at no live path, the bytes are removed and suppressed whole.
   - Held at another live path, in a manifest, a record or a waiting archive, they are withdrawn
     from the held path. That means one disclosure entry and a withdrawal line naming the hold's
     caselist. Nothing else is deleted, because nothing of them is stored at that path.
   - A digest that a waiting archive or a manifest still shows at the path is planned as the later
     upload it is. The record's path is folded into that plan's and never appended twice (row 15).
6. **Which lines a re-run reads.** Those under this request, at a path one of its holds in force
   holds for a file the selector names: `_recorded_paths`' rule for a row. A hold an un-suppress
   lifted is not in force, so its uploads are not listed. A `--source` of another file under the
   same request does not list them. A digest the list already stops at that path is not planned
   again, so a third run has nothing to do.
7. **A new plan inclusion, `held_at_import`, with a section of its own.** These files are not
   counted as files the request names, nor as `later_uploads_added`, so t11's counts are unchanged.
   The plan JSON gains a value of `inclusion` and no key. A withdrawal's held path is in
   `withdrawn_disclosures`, by its digest, as a path withdrawn by text is.
8. **(2) `write_manifest_text` is the helper, and it is manifest.py's alone.** No atomic-write helper
   is shared with other writers, so I fixed `write_manifest_text` and no other writer. Every
   manifest writer on this machine goes through it:
   - `write_manifest`: `caselist import` (`debate_cli`'s `commands/caselist.py`), and the pull's
     archive imports (`caselist_sync.py`);
   - `write_manifest_lines`: the OpenEv import and its metadata re-import (`commands/caselist.py`),
     the pull's camp release manifest (`caselist_sync.py`), and the re-measuring of a later
     manifest (`later_manifests.py`).

   The removal's local rewrite goes through `FsEvidenceObjectStore`, whose `atomic_replacement`
   already fsyncs the directory. A directory fsync that fails is raised, as `caselist_sync`'s state
   files raise it. I did not add `F_FULLFSYNC`.
9. **(3) `withholding_rows` names a held skipped row by the request holding its path.** Status asks
   `withholding_rows` for its hint (t19), so extending it moved the hint with no status change, as
   your notes expected. The cost is a tuple of digests and request ids together; a request id cannot
   be mistaken for a digest. The alternative was a boolean `withholds_manifest` beside it, plus a
   one-line change in status's `_publisher_withholds`. No new key in the publish JSON.
10. **t13's `written_by_this_build/` was not regenerated.** Its history has no import at a held
    path, so it writes no record, and the sidecar does not belong there. The record has its own
    stored directory, written by this build with one more step of history, and a collected test
    holds it to what this build writes.
11. **I stayed out of store sync**, as you asked. `store sync` skips every key under
    `manifests/_suppression/`, so it never copies the record either way.

## Operator follow-ups

None to run now. Nothing in this task is over two minutes, needs a credential, or changes anything
outside the worktree. I ran `scripts/task sync` myself, which rebased this unpushed branch onto
`origin/dev` at `5d3d398`.

After this merges, the weekly agent should be reinstalled from a build that has it, as you planned
for t22. Until then, the agent's `v1.1.0-dev.18` refuses a held upload but writes no record. An
upload it refuses whose archive then leaves the inbox stays unlisted, as before this task.

## Follow-up work

1. **Rename-into-place writers with no directory fsync** (from item (2)). Each fsyncs its file,
   renames it into place and stops:
   - `caselist/inbox_purge.py`'s rewrite of an inbox archive (E30);
   - `integrations/opencaselist/token_store.py`'s `write` (E34);
   - `integrations/models/_recorded_files.py`'s `write_pretty_json`, the recordings tool, which
     fsyncs nothing (low stakes).

   Already correct: `file_streaming.atomic_replacement` (every `FsEvidenceObjectStore` put),
   `fs_blob_store`, `suppression_list`, `caselist_sync`'s state files and `inbox_writer`.
2. **`caselist status` does not read the record** (E30). It says a removal is owed for a held upload
   while the archive is in the inbox. Once the archive has gone, it says nothing, though the record
   holds a digest the re-run has not yet listed. The pull's notification still names the refusal
   when it happens.
3. **Agent reinstall after merge** (the operator's; E34). See Operator follow-ups.

### PM questions

```text
v1-e30-t23 asks the PM, 2026-10-18:

1. ac3, the policy sentence (docs/policies/caselist-data-use.md). I changed only the runbook.
   Proposed, for you to approve or reword:

   (a) Personal data, rule 6. Its last sentence now ends "... and the caselist a withdrawn copy was
       taken from, by its slug, `openev` for a camp path (v1-e30-t16, v1-e30-t14)." Proposed new
       ending: "... and the caselist a withdrawn copy was taken from, by its slug, `openev` for a
       camp path (v1-e30-t16, v1-e30-t14); and the sha256 of each upload an import refused at a
       held path, beside that path's digest and the request holding it (v1-e30-t23)."

   (b) The table row "Removal log and suppression list (v1-e30-t07), and the records beside them
       (v1-e30-t13, t14, t15, t16)": add t23 to the list. The cell's content (sha256, request id,
       a held path's digest) already covers the new record.

   (c) What removal does, after "... and the caselist each withdrawn copy was taken from, by its
       slug (`openev` for a camp path).": "An import that refuses an upload at a held path records
       its sha256 there in the same way, under the request, so that the same removal run again puts
       those bytes on the list after the archive they came in has gone."

   (d) Optional, in the bullet "Covers later uploads at the removed path", after "a new upload at
       that path is refused when it is imported, and one already downloaded and waiting is taken
       out with the removal.": "Its sha256 is put on the list when the same removal is run again,
       whether or not its archive is still waiting."

   The runbook text I removed (docs/runbooks/caselist-removal.md, step 9, in the bullet "in the
   download inbox ..., not in the store"): "If the archive has already left the inbox, the plan
   cannot see the upload's bytes, so its sha256 is never put on the list; the path entry still
   refuses it there."

   Recommendation: (a), (b) and (c). (d) only if you want the removal section to say what the
   runbook says. The Goal stays InProgress until you approve; ac3 is the one criterion not run.

2. FYI, done unless you say otherwise: the import writes this machine's copy of the record alone,
   even with a live session, and the removal writes the bucket's (Decision 3). The record is the
   only takedown record not written to every copy at once, because only the takedown credential
   writes under manifests/_suppression/.

Reply with: the sentences you approve (or your wording) for 1, and "ok" or a ruling for 2.
```

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

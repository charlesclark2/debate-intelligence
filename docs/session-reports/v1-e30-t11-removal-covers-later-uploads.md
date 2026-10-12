# Session report: v1-e30-t11-removal-covers-later-uploads

| | |
|---|---|
| Task | `v1-e30-t11-removal-covers-later-uploads` — A removal also takes down later uploads at the removed path |
| Spec | [`plan_specs/v1/e30-caselist-ingestion/t11-removal-covers-later-uploads.yaml`](../../plan_specs/v1/e30-caselist-ingestion/t11-removal-covers-later-uploads.yaml) |
| Epic / release | `v1-e30-caselist-ingestion` / `v1.1` |
| Branch | `task/v1-e30-t11-removal-covers-later-uploads` |
| Session status | COMPLETE. The Goal is left `InProgress`: one clause of ac5 is not true of a caselist file (Summary, Deviation 1) |

## Summary

`caselist remove --source <sha256>` now finds every later upload the store holds at each path it
takes the named file from, lists them in a section of their own, and includes them in the plan the
operator confirms. A later upload goes through what the named file goes through. One held at
another live path too keeps its blob and that path's rows, and only its rows at the removed path
go. An earlier version is listed and left alone. `--only-named` plans the named files alone. For a
camp file a later upload is a higher OpenEv id at the same camp path, by the identity `v1-e34-t08`
uses, which the sync and the planner now share as one function. 33 mutations were run: 32 caught
(three only after I added the tests they showed were missing) and one equivalent survivor.

**The phase is `InProgress`, and that is the first thing to look at.** ac5 asks the runbook to say
that the pull's hold and this plan together cover a later upload whether or not it was imported.
That is true of a camp file and the runbook says so. It is not true of a caselist file: nothing
holds a revision that reaches the store after the removal, and a `--source` re-run cannot find it
(Deviation 1, Follow-up 1). The runbook says what is true. If you amend ac5 to camp files, or accept
the runbook as written, the phase is one command: `uv run scripts/task_helper.py set-phase
v1-e30-t11-removal-covers-later-uploads Succeeded`.

**Then Deviation 2:** the forbidden list says no school, team code, path or file name in the plan's
JSON. The JSON `v1-e30-t07` and `t09` built already carried all four, so I changed five existing
keys as well as keeping them out of the new ones.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `later-uploads-in-plan`: Later uploads at a removed path join the removal plan | Done | The planner change, `--only-named`, the caselist and camp tests, and the runbook. Its criterion passes: 234 tests. |

## Acceptance criteria

Commit ids are relative to `origin/dev` at `1448452`, which had not moved when this was written
(`git ls-remote origin dev`), so no sync was needed. `v1-e31-t09` had not merged.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1**: a fixture holds A at path P in one snapshot and revision B at P in a later one; the dry run of `--source <A>` lists B as a later upload by digest and snapshot, and `--execute` removes both from the local store and the bucket, every version; shown failing first against today's planner | PASS | Fixture `tests/fixtures/caselist/build_revised_path_archives.py`: six weekly windows and two complete archives, with the answer worked out in its docstring. **Red first:** `test_removal_covers_later_uploads.py` and `test_removal_covers_later_camp_uploads.py` ask the planner for nothing this task added, so they ran against the start commit's source (`git archive 82b38fc` into a scratch directory, put first on `PYTHONPATH`): **14 failed, 7 passed**, every failure an assertion and none a collection error. The later revision's blob was still there (`AssertionError: a11c0de3…`), its manifest row (`{'2026-09-15': [0, 0]} == {'2026-09-15': [1, 1]}`), its parsed file, the imported weekly in the inbox, and it was not on the list. **Green** on `c1729cf`: 21 passed. Listing: `test_the_plan_lists_each_later_upload_by_digest_caselist_and_snapshot`; through the command, `tests/smoke/test_caselist_remove_smoke.py::test_the_dry_run_lists_a_later_upload_by_digest_caselist_and_snapshot_and_execute_removes_both` (the JSON entry is written out in full by hand). Every version: the later revision's raw object and the manifest naming it were given a second version first, and afterwards have 0 and 1. |
| **ac2**: if B's bytes are also disclosed at another live path Q, B's blob and Q's rows stay and only P's rows go; a digest at P from before A is listed as an earlier version and left untouched; both by test | PASS | `test_a_later_upload_another_path_also_holds_keeps_its_blob_and_that_paths_rows` (blob, raw object, parsed file, Q's row on both sides and Q's disclosure record stay; P's row and record go; the list gets one entry for that path of it). `test_a_later_upload_that_is_also_a_camp_file_keeps_its_blob_and_the_camp_file` (the other holder is a camp release). `test_the_waiting_weekly_in_the_inbox_keeps_the_other_paths_copy`. Earlier version: `test_an_earlier_version_at_the_path_is_left_exactly_as_it_was` (blob, raw object, both manifests byte for byte with their version ids unchanged, records, not on the list) and `test_the_earlier_version_is_listed_and_is_not_in_the_plan`. |
| **ac3**: the limiting flag removes only the named digests, by test; without it the plan includes later uploads, and the confirmation prompt states how many it adds | PASS, with a reading of "confirmation prompt" (Deviation 3) | `--only-named`. `test_only_named_plans_the_named_file_alone_and_still_lists_what_it_leaves`, `test_only_named_removes_the_named_file_and_leaves_every_later_upload_as_it_was`, and through the command `test_only_named_removes_the_named_version_and_leaves_the_later_upload`. The count: `test_the_confirmation_says_how_many_later_uploads_the_plan_adds` asserts the line above the `--execute` command, `This plan covers the 1 file(s) named, and adds 1 later upload(s) at the removed path(s) (1 more is shared and kept).`; `test_the_done_line_says_what_the_run_covered`; the smoke test asserts the same sentence in the command's own output. |
| **ac4**: for a camp file, a later OpenEv id at the same camp path is included the same way, by test on the openev fixture | PASS | `test_removal_covers_later_camp_uploads.py`, built by the real pull over the synthetic camp files: 512 pulled, deleted upstream and uploaded again as 640, pulled as a revision. Removing 512's bytes removes 640's too: both release rows on both sides, blobs, raw objects (640's given a second version first), camp-file records, inbox copies, both on the list. Red first on the start commit: `assert [{'openev-640-…': 'cd2a…'}] == [{}, {}]`. The plan: `test_the_plan_lists_the_later_openev_id_by_digest_release_and_id`. |
| **ac5**: `docs/runbooks/caselist-removal.md` says what the plan now lists, when to use the limiting flag, and that Step 8's hold and this plan together cover a later upload whether or not it was imported | **Not met as written. PASS if amended to camp files** (Deviation 1) | The runbook says what the plan lists and how to read each section (step 4), and when `--only-named` is right (step 3). Step 8 says the hold and the plan between them cover a camp file's later upload either way. For a caselist file it says the opposite, because that is the case: nothing holds one that arrives after the removal. Step 9 gains a check for it. `uv run scripts/check_command_blocks.py --base origin/dev` → OK. |
| Node `later-uploads-in-plan`: `uv run pytest packages/debate_core/tests -k "removal or remove"` | PASS | `234 passed in 33.51s`. It was `171 passed in 46.59s` on the unchanged branch. |

### What one later upload goes through

The PM asked to see each step for one later upload, against moto and a local store, failing first.
The later upload is `later-revision`, the fixture's file at the removed path in the weekly of
2026-09-15. Each row is one test in `test_removal_covers_later_uploads.py`, red on the start
commit's source and green now.

| Step | Test | What it checks |
|---|---|---|
| Blob, every version | `test_the_later_revision_is_deleted_here_and_in_the_bucket_every_version` | Local blob gone; the raw object's two versions gone with no delete marker; source and disclosure records gone |
| Manifest rows, both sides | `test_each_manifest_loses_the_rows_the_table_says_on_both_sides` | Rows dropped per manifest equal the fixture's hand-written table, on this machine and in the bucket; each rewritten manifest has one version; no version of any manifest names a removed digest |
| Parsed file and aggregates | `test_its_parsed_file_and_the_caselists_aggregates_are_deleted_here_and_in_the_bucket` | The per-source file and the three aggregates, here and both bucket versions of each |
| Inbox purge | `test_the_imported_weekly_in_the_inbox_that_holds_it_is_deleted` | The imported weekly that holds it is deleted; the one holding only the earlier version is untouched |
| Suppression list | `test_it_is_on_the_suppression_list_in_both_copies`, `test_reimporting_the_weeks_that_held_them_brings_none_of_them_back` | Whole-file entries for the three removed, one path entry for the shared one, in both copies; a re-import counts each as `SUPPRESSED` |

One thing in that table was already true before the task. The red run failed on the parsed
per-source file, not on the aggregates: removing the named file already deletes every caselist's
aggregates. That is also why mutant 11 below is equivalent.

### Mutation runs

Each run applied one textual change to committed source, ran 150 tests (152 after `c1729cf`: the
seven new test files' worth plus `test_removal_plan.py`, `test_removal_service.py`,
`test_removal_reaches_full_archives.py`, `test_removal_purges_inbox.py` and
`test_parsed_store_removal.py`) with `-n auto --no-cov -p no:randomly`, and restored the file from
a byte copy it had saved, checking the sha256 and `git diff --quiet`. The driver refuses to run a
mutant whose target text is not found exactly once. Each run set `HYPOTHESIS_STORAGE_DIRECTORY` to
a new directory made with `mkdtemp` and checked empty (working agreement 8). None of these tests is
a Hypothesis property, so the fresh database is to follow the agreement and
`--hypothesis-show-statistics` does not apply. Seven batches, the longest 111 s; each run took 14
to 24 s. Every catch is a failing assertion; none errored at collection. Rows 1 to 29 and 31 ran on
`fa17a16`; rows 30, 32 and 33 on `c1729cf`.

The eight kinds the PM named, with the variants I ran of each: what "later" means (1 to 3), an
earlier version (4), caselists (5), the list (6, 7), a shared blob (8, 9), parsed files (10 to 12),
the flag (13 to 15) and the JSON (16 to 21).

| # | Mutation | Result | What caught it (first of the failing tests) |
|---|---|---|---|
| 1 | "Later" is any snapshot: the date comparison dropped | CAUGHT, 22 failed | `test_a_file_only_in_snapshots_dated_before_it_is_an_earlier_version`; `test_an_earlier_version_at_the_path_is_left_exactly_as_it_was` |
| 2 | "Later" is after the named file's *latest* snapshot | CAUGHT, 18 failed | `test_it_is_the_named_files_earliest_snapshot_that_counts_so_a_revert_still_makes_it_later`; `test_the_later_revision_is_deleted_here_and_in_the_bucket_every_version` |
| 3 | A complete archive ordered by its name, not its date | CAUGHT, 17 failed | `test_a_complete_archive_is_ordered_by_its_date_not_by_its_name` |
| 4 | An earlier version included | CAUGHT, 16 failed | `test_an_earlier_version_at_the_path_is_left_exactly_as_it_was`; `test_the_earlier_version_is_listed_and_is_not_in_the_plan` |
| 5 | Paths compared across caselists | CAUGHT, 15 failed | `test_the_same_spelling_of_the_path_in_another_caselist_is_another_path` |
| 6 | A later upload not put on the list (whole file) | CAUGHT, 10 failed | `test_it_is_on_the_suppression_list_in_both_copies`; `test_reimporting_the_weeks_that_held_them_brings_none_of_them_back` |
| 7 | A shared later upload's path not put on the list | CAUGHT, 7 failed | the same two, and `test_the_waiting_weekly_in_the_inbox_keeps_the_other_paths_copy` |
| 8 | A shared blob deleted: a later upload treated as held nowhere else | CAUGHT, 14 failed | `test_a_later_upload_another_path_also_holds_keeps_its_blob_and_that_paths_rows` |
| 9 | A withdrawal takes every file at the path, not the one file | CAUGHT, 3 failed | `test_an_earlier_version_at_the_path_is_left_exactly_as_it_was` |
| 10 | A later upload's parsed file left | CAUGHT, 1 failed | `test_its_parsed_file_and_the_caselists_aggregates_are_deleted_here_and_in_the_bucket` |
| 11 | A later upload's aggregates left | **SURVIVED: equivalent** | See below |
| 12 | No aggregate deleted for anything | CAUGHT, 3 failed | the same test, and two of `v1-e31-t06`'s |
| 13 | `only_named` ignored by the planner | CAUGHT, 4 failed | the three `only_named` tests and the smoke test |
| 14 | `--only-named` not passed on by the command | CAUGHT, 1 failed | `test_only_named_removes_the_named_version_and_leaves_the_later_upload` (smoke) |
| 15 | `--only-named` missing from the printed `--execute` command | CAUGHT, 2 failed | `test_with_only_named_the_confirmation_and_the_command_say_so` |
| 16 | A later upload's path in the JSON | CAUGHT, 4 failed | `test_the_json_names_no_school_team_code_path_camp_title_or_file`; `test_the_plans_json_names_no_school_team_path_or_file` (smoke) |
| 17 | A disclosure's path in the JSON | CAUGHT, 3 failed | the same two |
| 18 | A withdrawn path in the JSON | CAUGHT, 3 failed | the same two |
| 19 | The team in the JSON selector | CAUGHT, 3 failed | the same two |
| 20 | An inbox file's name in the JSON | CAUGHT, 2 failed | the first, on a hand-built plan with a camp download in the inbox |
| 21 | Camp and title in the JSON | CAUGHT, 2 failed | the first |

**Mutant 11 is equivalent.** A later upload exists only beside a named file the plan removes, and
removing a file deletes the aggregates of every caselist the store knows, so the later upload's own
aggregates are always a subset of what is already planned. Nothing observable changes. Mutant 12
shows the test does fail when aggregates are left.

The rest, one per rule the plan adds:

| # | Mutation | Result | What caught it |
|---|---|---|---|
| 22 | A path logged at `WARNING` by the planner | CAUGHT, 1 failed | `test_nothing_logged_at_info_or_above_names_a_path_a_school_or_a_team` |
| 23 | Named files reported as versions of each other | CAUGHT, 9 failed | `test_a_team_removal_names_every_version_at_the_teams_paths_from_every_snapshot` and eight more |
| 24 | A withdrawal asked about every path of the file | CAUGHT, 1 failed | `test_a_team_removal_withdrawing_a_shared_file_has_no_later_uploads` |
| 25 | The same, with a skipped shared file too | CAUGHT, 1 failed | the same test |
| 26 | An unfinished source never planned | CAUGHT, 2 failed | `test_a_run_stopped_among_the_records_is_finished_…` (both parameters) |
| 27 | An unfinished source planned with nothing left | CAUGHT, 1 failed | `test_a_second_source_under_the_same_request_does_not_plan_the_first_again` |
| 28 | Paths the list already stops not taken | CAUGHT, 2 failed | `test_a_run_stopped_among_the_records_is_finished_…` |
| 29 | The delivery record not asked | CAUGHT, 2 failed | `test_another_camps_file_of_the_same_name_is_left_where_the_delivery_record_knows_its_path` |
| 30 | A camp row naming no id treated as a version | **SURVIVED, then CAUGHT** after a test change | `test_a_camp_row_that_names_no_openev_id_is_not_a_later_upload_and_has_none` |
| 31 | A kept shared file counted as added | CAUGHT, 4 failed | `test_the_confirmation_says_how_many_later_uploads_the_plan_adds` |
| 32 | A skipped shared file alone has later uploads | CAUGHT, 1 failed, by a test added for it | `test_a_shared_file_named_by_source_and_skipped_has_no_later_uploads` |
| 33 | A later upload's camp holder not counted as a holder | **SURVIVED, then CAUGHT** after a test was added | `test_a_later_upload_that_is_also_a_camp_file_keeps_its_blob_and_the_camp_file` |

Two survivors found real holes in the tests, both fixed in `c1729cf`:

- **Mutant 30.** The test of the hand-import guard used a row inside its camp folder
  (`Tamarack/TSF-…`), whose folder already made it a different path. The guard itself was never
  exercised. A hand import from a flat directory reads exactly as an `openev-<id>-` row's name
  does, and the test now includes one.
- **Mutant 33.** No test had a later upload whose other holder is a camp release rather than a
  team. With the mutant, such a file would have been removed from the camp release too.

Mutant 25 was caught only by the withdrawal test, so it did not show the skipped case on its own.
Mutant 32 and its test do.

### Checks CI runs

On `c1729cf`, with the report and the spec unchanged since:

| Command | Result |
|---|---|
| `uv run --frozen pytest -n auto --cov -m "not slow and not live"` | `5244 passed, 1 skipped, 1 warning in 120.78s`, 122.6 s wall clock, coverage 97%. The skip is the parser eval waiting on human corrections. The warning is `pytest_socket`'s, from the smoke harness test that tries the network on purpose. See Decision 12 on the runtime. |
| `uv run --frozen pyright` | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen ruff check .` / `ruff format --check .` | `All checks passed!` / `587 files already formatted` |
| `uv run --frozen lint-imports` | `Contracts: 12 kept, 0 broken.` |
| `uv run scripts/check_thin_handlers.py` | `OK: 21 CLI command and API route handlers within 25 statements` |
| `uv run scripts/check_command_blocks.py --base origin/dev` | `OK`, this report included |
| `uv run scripts/docs_index.py --check-descriptions` | `All 34 indexed documents under docs/ have a description` |
| `uv run scripts/validate_specs.py` | `OK: 327 files, 38 epics, 269 tasks, 20 releases` |

Coverage of the changed modules under the removal tests, with branches, on `c1729cf`:
`removal_path_versions.py` 100%, `removal_plan.py` 97%, `removal_service.py` 96%,
`caselist_remove.py` 90%. I read the uncovered lines. All but one are lines this task did not write;
the one is a `continue` in the earlier-versions listing that needs a plan with two earlier files.
The first measurement, before `fa17a16`, showed the camp wording and the `DONE` line untested in
the command, which is why the hand-built plan tests exist.

## Files changed

- **`debate_core.application`**
  - `caselist/removal_path_versions.py` (new): which other files sit at a removed file's paths, and
    which came later. A function of manifest rows; it reads and logs nothing.
  - `caselist/removal_plan.py`: the planner asks it, plans each later upload
    (`_plan_other_source`), and plans again what a stopped run left. `Inclusion`,
    `LaterUploadOutcome`, `RemovalPlan.later_uploads`, `.earlier_versions`, `.only_named`. A
    withdrawal now drops one file's row at a path, not every row at that path.
  - `caselist/removal_service.py`: `plan(..., only_named=)`. The executor is unchanged: it carries
    out whatever plan it is given.
  - `caselist_sync.py`: `camp_path_of_manifest_row`, the part of `_match_listed_openev` that reads
    a release row's OpenEv id and its path as names, moved into a public function so the planner
    uses the sync's identity and not a copy of it. `_match_listed_openev` calls it. No behaviour
    change; the 130 tests of the sync's revision and hold rules pass unchanged.
- **`debate_cli.commands`**: `caselist_remove.py`. `--only-named`; the two new sections; the count
  above the `--execute` command, on the line `--execute` starts with and on the `DONE` line; JSON
  without names.
- **Tests**
  - `packages/debate_core/tests/application/caselist/`: `test_removal_covers_later_uploads.py`
    (16) and `test_removal_covers_later_camp_uploads.py` (5), which check the store and use only
    what existed before; `test_removal_later_uploads_plan.py` (16) and
    `test_removal_later_camp_uploads_plan.py` (5), which check the plan; and
    `test_removal_path_versions.py` (21), the ordering rules on a few rows each.
  - `packages/debate_cli/tests/commands/test_caselist_remove_plan_output.py` (10): text and JSON
    of plans built field by field.
  - `tests/smoke/test_caselist_remove_smoke.py`: four checks through the command, and its row in
    `tests/smoke/README.md`.
  - `tests/fixtures/caselist/build_revised_path_archives.py` (new): the fixture and its
    hand-written answer.
- **Docs**: `docs/runbooks/caselist-removal.md`.

## Deviations from the spec

1. **ac5's last clause is not true of a caselist file, and the runbook says so.** The spec's
   description says "`v1-e34-t14` enforces that for files not yet imported: the sync holds a later
   upload at a removed path", and ac5 asks the runbook to say the hold and the plan "together cover
   a later upload whether or not it was imported". The hold is for camp files only: it asks about a
   new OpenEv id at a removed camp path. The caselist importer asks the list about a member's bytes
   and its withdrawn disclosures, and nothing else (`pipeline.py`, `_is_suppressed`). So a revision
   of a removed caselist file that reaches the store after the removal is imported. The plan covers
   what the store held when it ran. I wrote the runbook to say this, rather than the sentence ac5
   asks for, and left the phase `InProgress`. See Follow-up 1 for the two cases and what closing
   them would take.
2. **The plan's JSON lost five existing kinds of name, not only the new ones.** The forbidden list
   says "A school, team code, path or file name in the plan's JSON output". The PM's brief says the
   same of the later-uploads section. Counting from the code, the JSON already carried:
   `sources[].disclosures[].path`; `sources[].camp_files[].camp` and `.title`;
   `sources[].withdrawn_paths`; `selector.value`, which for `--team` is the school and team code;
   and `inbox[].name`, which for a camp download is the camp file's name. A later upload is a
   source, so the first three would have carried its path. I followed the forbidden list:
   - `disclosures[]` is `{caselist, snapshot, disclosure}`, the digest the suppression list uses;
   - `camp_files[]` is `{year, event}`;
   - `withdrawn_paths` became `withdrawn_disclosures`, `{caselist, disclosure}`;
   - `selector` is `{kind, sha256}` or `{kind, caselist}`;
   - `inbox[].name` is the file's label: a weekly archive's own name, or `openev-<id>`.

   Nothing in the repository read the changed keys (I searched tests, scripts, runbooks and
   guides). The existing smoke assertion on `inbox[].name` holds, because a weekly archive's label
   is its name. The text of the plan is unchanged in what it names. `inbox_directory` is still
   there: it is a directory on this machine, not a disclosure's path. If you wanted only the new
   section kept clean, the five are one function each to put back.
3. **There is no confirmation prompt, so the count is where the operator confirms.** ac3 and the
   brief say "the confirmation prompt states how many it adds". `caselist remove` has never asked a
   question: the operator confirms by reading the dry run and running the printed `--execute`
   command. I did not add an interactive prompt, because it would change how the command is run
   from the runbook and from every test. The count is stated in three places: above the command
   under *TO CARRY IT OUT*, on the line `--execute` prints as it starts, and on the `DONE` line. If
   you meant a real prompt, that is a change to the command's contract and I would want it specified.
4. **`tests/fixtures/caselist/` is outside `constraints.packages`.** The fixture is used by tests
   in two packages' test trees and belongs where every other caselist fixture is.

## Decisions and assumptions

1. **"The same camp path", in code terms.** Two stored rows of one release manifest
   (`manifests/openev/<year>-<event>.jsonl`), each of whose file names starts `openev-<id>-`, with
   different ids, for which `camp_path_of_manifest_row(path)` returns equal component tuples. That
   function takes the id prefix off and compares what is left as names, component by component:
   case-folded, with every run of punctuation or spacing as one separator. It is the comparison
   `_match_listed_openev` makes for a revision, now literally the same code. The later upload is
   the higher id, because upstream assigns ids in upload order (`v1-e34-t08`'s reading) and a
   release manifest is one accumulating file with no dates to order by. A row that names no id, a
   hand import, has no version in either direction, which is `v1-e34-t08`'s rule too.
2. **The delivery record decides where it can, and the plan says which it used.** A release row
   keeps no camp folder, so two camps' files of one file name read as one camp path. Where this
   machine's delivery record knows the upstream path digest of both ids, different digests are
   different paths (`same_path_by: upstream_path_digest`). That is the identity `v1-e34-t07`'s hold
   uses. Where it does not, as in prod, which never pulls, the rows' names are all there is
   (`row_name`), and the text says "matched by file name alone … so check it". So a prod plan can
   list a file the dev plan did not. The runbook says to compare the sha256 values and to use
   `--only-named` in prod if they differ. I chose to include on a name match rather than leave it
   out: leaving it out would fail silently in the environment that most needs the removal.
3. **A file in another snapshot of the same date is neither.** The brief defines later (after the
   named file's earliest) and earlier (only before it). A weekly and a complete archive of one day
   that disagree, or this machine's manifest and the bucket's, fit neither. I list it with the
   earlier versions, marked `same_date`, and do nothing to it.
4. **A shared later upload is withdrawn the way `--team` withdraws a shared file.** Its rows and
   disclosure records at the removed path go, and one entry suppresses that path of it, so the next
   import cannot record it there again. The existing rule dropped *every* row at a withdrawn path,
   which was harmless while only `--team` withdrew. It would have taken an earlier version's row
   too, so a withdrawal is now `(caselist, path, sha256)`. Mutant 9 shows the difference.
5. **`--include-shared` does not widen a later upload.** It is the operator's decision about the
   files the request names. A shared later upload is withdrawn from the removed path either way; to
   remove it for everyone, name it.
6. **A camp file's later upload that another holder has is kept.** The list has no entry that stops
   one camp path of a file, and I checked what would happen without one: the next pull would find
   the id unrecorded and unsuppressed and fetch it again. So it is planned as `SKIP_SHARED`, the
   disposition `--source` already gives a shared file, and the plan says how to remove it. This is
   the shared-blob rule unchanged; Follow-up 2 is what would let it be withdrawn.
7. **`--team`, checked.** It already reached every digest at the team's own paths, revisions
   included: it collects every digest any record or any manifest row on either side holds under the
   team's directories. `test_a_team_removal_names_every_version_at_the_teams_paths_from_every_snapshot`
   pins it on the window fixture, uses nothing new, and passed on the start commit. It did not
   reach one place: with `--include-shared` a shared file goes from the *other* holders' paths too,
   and what followed it there was left. The same rule now applies there
   (`test_a_team_removal_with_include_shared_adds_the_later_upload_at_the_other_holders_path`).
   There is no other path-based selector.
8. **A re-run finishes later uploads even when no manifest shows them.** Records are deleted last.
   If a run stops among them, every manifest is already rewritten, so nothing shows what was at the
   removed path, and a `--source` re-run would have left the later uploads' records behind. The
   planner now plans again any file this request suppressed that still has a record or its blob
   here (`Inclusion.UNFINISHED`), with or without `--only-named`. A file with nothing left is not
   planned again, so two `--source` commands under one request id do not list each other. `--team`
   already did this for everything the request suppressed and is unchanged.
9. **The removal log's format is unchanged.** Later uploads are in `removed_sha256` and
   `withdrawn_sha256` with the named files. The log does not say which were named; the plan does.
10. **The parsed files in the tests are written by hand at the parsed store's keys**, not produced
    by the parser, so nothing here depends on the code `v1-e31-t09` is revising. A removal deletes
    them by key.
11. **Two expectations I wrote were wrong, and both were about existing output.** I expected
    `selector.kind` to be `team`; it is `TEAM`, as it always was. And I first put
    `later_uploads_added` inside `counts`, which broke `v1-e30-t07`'s exact assertion on that
    object, so it is a key of its own. Every expectation about the new behaviour passed as written.
12. **The full suite now takes two minutes.** I started it expecting about 105 s, the figure in
    `v1-e34-t04`'s report. It took 122.6 s. It is at the hand-off line now, and the next session
    should hand it over or run it in two halves.
13. **Cost on a corpus-sized input.** 104,000 rows and 304 named digests take 0.82 s in
    `other_versions`, measured on synthetic rows. Nothing was run against real data.
14. **Limits.** A camp release that is a zip records its members' paths, which name no id, and a
    re-upload replaces those rows in place, so there is never a second row to find. A caselist path
    is compared exactly as written; a file re-uploaded under a new name (`… (1).docx`) is another
    path, as it is everywhere else in the importer.

## Operator follow-ups

None. No command here needs credentials, and nothing was run against a real bucket or the real
data directory.

## Follow-up work

1. **A revision of a removed caselist file that is not yet imported is covered by nothing** (E30
   and E34; a ruling first). Two cases:
   - *Downloaded, waiting in the inbox when the removal runs.* The plan could see it: the inbox
     inventory gives each waiting archive's paths and digests. Today the plan reports this only for
     `--team` (the `NOTE`). The fix for `--source` is small, but once the removal has run a re-run
     cannot find the file, so the note would have to say "run `caselist pull` first".
   - *Published after the removal.* The next weekly imports it. A `--team` re-run finds it. A
     `--source` re-run cannot, because the removed file's path is recorded nowhere once its rows
     are gone. Holding it at import, as the pull does for a camp file, needs the list to carry the
     removed path's digest for a whole-file removal, which is a change to what the list means and
     to the importer. The spec puts the list's format out of scope.

   The runbook's step 9 has a manual check meanwhile.
2. **A camp path cannot be withdrawn on its own** (E30). A camp file's later upload that a team
   also disclosed is kept whole (Decision 6). Withdrawing it needs a scope for camp paths in the
   list and the OpenEv importer and the sync reading it.
3. **Prod matches camp uploads by file name alone** (E34). The delivery record is this machine's.
   `v1-e34-t08` decided against a manifest key for the upstream path digest. That key is what
   would let a prod plan tell two camps' same-named files apart.
4. **The policy's "What removal does" list does not mention later uploads** (Charlie's;
   `docs/policies/caselist-data-use.md`).
5. **`--source` says "also held by 1 other team(s)" of a file one team holds** (E30, `v1-e30-t10`
   is already in these docstrings). For a `--source` removal the planner counts every holding team,
   the only one included, and the text calls them "other". It predates this task. I saw it in the
   output and left it.

## After the PM review: synced onto dev

Written by the session on 2026-10-11, after the verdict below. Nothing the PM reviewed changed: no
source file, test or runbook line is different. What changed is the branch's base.

- **The PM's review and spec amendments are committed as written** (`482064d`): the verdict, ac3
  and ac5 as amended, and the phase `Succeeded`.
- **`v1-e31-t09-first-corpus-parse-findings` had merged** (#218, then the generated-files refresh
  #219), so `scripts/task pr` would have refused the branch. I ran
  `scripts/task sync v1-e30-t11-removal-covers-later-uploads`. The branch was not on origin, so it
  rebased and pushed nothing. The rebase was clean: the two sides have no file in common. The
  branch is now on `origin/dev` at `5a05711`.
- **The commit ids quoted above are from before the rebase.** The same commits, in order, are now:

  | Before | After | Commit |
  |---|---|---|
  | `9882817` | `7318478` | The fixture and the outcome tests, red |
  | `b550004` | `04be988` | The planner change |
  | `0fc95c5` | `9abf910` | The command: sections, count, `--only-named`, JSON |
  | `23d28bc` | `f5ff0d9` | The plan, ordering, camp and re-run tests |
  | `c7873ac` | `e4a4487` | Runbook and smoke checks |
  | `fa17a16` | `2361601` | Hand-built plan tests |
  | `c1729cf` | `35a9f1f` | The tests the surviving mutants called for |
  | `c9abe0f` | `c17952f` | The report |

- **Everything was run again on the synced branch**, as the brief asked if `v1-e31-t09` merged.
  That task changed `ports/parsed_store.py` and the local parsed store, which the removal tests
  read.

  | Command | Result |
  |---|---|
  | `uv run pytest packages/debate_core/tests -k "removal or remove"` (the node's criterion) | `234 passed in 31.57s` |
  | `uv run --frozen pytest -n auto --cov -m "not slow and not live" packages/debate_core` | `3733 passed in 81.99s` |
  | `uv run --frozen pytest -n auto --cov -m "not slow and not live" --ignore=packages/debate_core` | `5462 passed, 1 skipped, 1 warning in 125.25s`, 126.75 s wall clock |
  | `uv run --frozen pyright` | `0 errors, 0 warnings, 0 informations` |
  | `uv run --frozen ruff check .` / `ruff format --check .` | `All checks passed!` / `592 files already formatted` |
  | `uv run --frozen lint-imports` | `Contracts: 12 kept, 0 broken.` |
  | `uv run scripts/check_thin_handlers.py` | `OK: 21 CLI command and API route handlers within 25 statements` |
  | `uv run scripts/validate_specs.py --require-succeeded v1-e30-t11-removal-covers-later-uploads` | `Succeeded` |

- **The second half was not a half.** I meant to run the suite in two halves, as the PM ruled.
  `--ignore=packages/debate_core` excluded nothing, so that command ran the whole selection: 5462
  of the 5463 tests collected passed and one skipped, which is CI's own result, but it took 126.75 s
  in one command. The second half should name its paths: `packages/debate_cli/tests
  packages/debate_api/tests packages/debate_workers/tests tests`.
- **The mutation runs were not repeated.** The rebase changed none of the three files the mutants
  edit, and the tests that caught them pass on the synced branch.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-10

**Notes:**

Accepted in full. I have amended ac3 and ac5 in this branch and set the phase to `Succeeded`.

**Deviation 1 is my spec's error.** I generalised `v1-e34-t14`'s hold to caselist files, and it
asks only about a new OpenEv id at a removed camp path. You read the importer to check rather than
writing the sentence ac5 asked for. A runbook that tells an operator a removal is complete when it
is not would be worse than no runbook. ac5 now asks for what is true, and the gap is a task of its
own. The amended ac5 matches what you wrote:

* for a camp file, the hold and the plan cover a later upload either way;
* for a caselist file, the plan covers what the store holds when it runs, and step 9 gives the
  manual check.

**The work itself:**

* **The table of what one later upload goes through** is the evidence I asked for. Each step is a
  test, red against the start commit's source and green now.
* **"Later" is pinned on a hand-worked fixture,** including the revert case, a complete archive
  ordered by date, and the same path spelled in another caselist. Mutants 1 to 5 show each rule
  carries weight.
* **Two survivors, 30 and 33, found real holes in the tests, and you closed both.** Mutant 33 in
  particular would have removed a file from a camp release because a team also held it. Mutant 11
  is properly argued as equivalent, with mutant 12 to show that the test does bite.
* **Decision 4, a withdrawal scoped to `(caselist, path, sha256)`,** fixes a latent bug: the old
  rule would have taken an earlier version's row along with it.
* **Decision 7** found that `--team --include-shared` missed what followed a shared file at the
  other holders' paths, and fixed it with the same rule.
* **Decision 8,** re-planning a stopped run's unfinished files, fixes another latent gap.
* **Sharing `camp_path_of_manifest_row` with the sync,** rather than copying it, means one
  identity for "the same camp path".

**Rulings:**

* **Deviation 2, the five existing JSON keys:** accepted. The forbidden list applies to the plan's
  JSON as a whole, and nothing read those keys. Pseudonymous disclosure digests are what the
  suppression list already uses.
* **Deviation 3:** accepted, and ac3 is amended to say "the plan's confirmation text".
* **Deviation 4:** accepted.
* **Decision 2, including a camp file in prod on a name match:** accepted. On a removal, being
  wrong by including too much is the safer error. The plan says which match it used, and the
  runbook says what to compare.
* **Decision 12, the suite at 122 s:** noted. Sessions run it in two halves from now on.

**Follow-up work, filed by the PM:**

* **Your 1, a caselist revision that is not yet imported (E30, p2):** a removal by `--source`
  holds future uploads at the removed path. The suppression list gains a path entry for a
  whole-file removal, and the importer consults it. The plan also notes, and covers, a waiting
  archive in the inbox. The list's format is in scope there.
* **Your 2, withdrawing a camp path (E30, p3)** and **your 3, prod matching by name (E34, p3):**
  filed together as "camp-path identity in manifests".
* **Your 4:** the policy's "What removal does" gains later uploads in the next PM close-out. It
  tightens the policy, so it takes effect on merge.
* **Your 5, "other team(s)" for a file one team holds:** folded into `v1-e30-t10`, which is
  already in these docstrings and the removal output.

`v1-e30-t10` can start once this merges.

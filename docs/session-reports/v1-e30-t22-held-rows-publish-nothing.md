# Session report: v1-e30-t22-held-rows-publish-nothing

| | |
|---|---|
| Task | `v1-e30-t22-held-rows-publish-nothing` — A held path's bytes and skipped rows never reach the bucket |
| Spec | [`plan_specs/v1/e30-caselist-ingestion/t22-held-rows-publish-nothing.yaml`](../../plan_specs/v1/e30-caselist-ingestion/t22-held-rows-publish-nothing.yaml) |
| Epic / release | `v1-e30-caselist-ingestion` / `v1.1` |
| Branch | `task/v1-e30-t22-held-rows-publish-nothing` |
| Session status | COMPLETE. Every criterion passed; the Goal is `Succeeded` |

## Summary

The importer no longer writes a manifest row for a skipped member (such as a symbolic link) at a
path a removal holds, in a snapshot the hold covers. It is still counted as skipped, as junk beside
a suppressed file is. The removal's manifest rewrite drops such a row that an earlier build wrote,
here and in the bucket, the first run included. `caselist status` names it by the request holding
the path and leaves the exit code alone. The publisher now leaves a digest that only held rows of a
manifest name out of that snapshot's plan, so its bytes are never uploaded. Bytes that an unheld row
also names are planned as before, in the same manifest or in a later one. The manifest is withheld
with the same outcome, the same code (`MANIFEST_NAMES_SUPPRESSED_SOURCE`) and the same held count.

**Four things to look at first:**

1. **`store sync` was a second way for the bytes to reach the bucket** (Decision 3). Its push
   compared every local blob with the bucket and planned a missing one as `new`. After this change
   the publisher leaves the held-only bytes out, but `store sync --apply` would still have pushed
   them. A push now plans them `skipped`. That is one change outside what the spec names: you asked
   me to find every comparison and show that such a digest is neither drift nor owed.
2. **Status had the same problem in a narrower case** (Decision 2). With the manifest in the bucket
   and the held-only bytes not, the start commit's status counted them missing and exited with
   drift. They are now outside what the bucket is expected to hold. In the realistic case (this
   build's publish, manifest withheld) the snapshot differs exactly as before. The only change there
   is that `missing_sources` no longer lists the bytes.
3. **The publisher still publishes an earlier build's manifest that has a skipped row at a held
   path** (Decision 5, PM question 1). The spec and your notes name the importer, the rewrite and
   status, and say the exit codes stay as they are. Withholding that manifest would change a
   publish that succeeds today into one that fails. Status names the row, and the removal run again
   drops it, here and in the bucket, which is ac3.
4. **The local copy of held-only bytes goes when the removal is run again** (your question). The
   re-run finds the held row as a later upload at no other path and removes it whole: its sha256 goes
   on the list, the local blob is deleted, and the manifest is rewritten. Bytes another team's row
   also names are withdrawn from the held path only, and their blob and object stay. Both are shown
   by test (ac3 below).

The installed agent's build, `v1.1.0-dev.7` (`fea1807`), includes `v1-e30-t13` and `v1-e30-t21`.
It refuses a held upload, so it writes no held stored row. It does write the skipped row this task
withholds, and its publisher publishes it. Until the agent runs a build with this task, status and
the re-run are what take that row out. The agent's build reads every file this build writes (ac4-style
evidence below).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `held-rows`: Held rows publish nothing | Done | The importer's withheld rows, the publisher's upload rule, status, `store sync`, the rewrite of an earlier build's manifests, the runbook. Its criterion passes: 435 tests. |

## Acceptance criteria

"The start commit" is `ff4ca36`, this branch's first commit (`dev` at `0268cf7` plus the phase).
Each build's source is exported with `git archive` into the scratch directory and put first on
`PYTHONPATH`; the tests are this branch's. "The agent's build" is `v1.1.0-dev.7`. Every test uses
moto, temporary data directories and, in the new files, a temporary `HOME`. No test or command
read the operator's `~/.debate-research`, `~/.aws` or LaunchAgents.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1**: an archive with a skipped member at a held path imports with no row at that path, and the removal's rewrite and status agree, by tests shown failing first | PASS | **Red first**: `test_held_rows_publish_nothing.py` against the unchanged code at its first commit (`c756955`) → `11 failed, 8 passed`. One of the 11 was a bug in the test, which I fixed before writing any code: the week-boundary test read the `REMOVED` entry at the same path too. Then every new and changed test against the start commit's source, five files → `17 failed, 99 passed`. The ac1 failures are assertions: the link's row present after import (`assert [{'byte_size'…}] == []`), the removal's first run and its re-run each keeping the row. **Green**: `test_a_link_at_the_held_path_imports_with_no_row_at_that_path` (no row at the held path, `skipped` still `{"SYMLINK": 1}`, the entry `withheld`); `test_a_link_at_a_path_no_removal_holds_keeps_its_row`; `…in_the_week_the_hold_dates_from_keeps_its_row` (the hold covers snapshots after its date, not on it); `test_the_removal_drops_a_links_row_at_the_path_it_holds_the_first_time_it_runs`; `test_the_removal_keeps_a_links_row_at_a_path_it_does_not_hold`. **They agree**: `test_the_removals_rewrite_and_this_builds_import_leave_the_same_manifest`. The week the removal rewrote and the same archive imported again by this build are byte for byte the same file. Status: `test_status_names_an_earlier_builds_row_for_a_link_at_the_held_path` and `test_status_does_not_name_a_link_at_a_path_no_removal_holds`. The rule is one function, `hold_on_skipped_member`, shared by the importer, the manifest rewrite, `t21`'s inbox rewrite and status. Through the binary: `tests/smoke/test_caselist_remove_smoke.py::test_a_link_at_a_held_path_imports_with_no_row_and_nothing_is_owed_for_it` → passed with `t21`'s check, `2 passed in 15.88s` |
| **ac2**: a digest named only by held rows is not uploaded, and one also named by an unheld row is, by moto tests shown failing first; the publish output's held counts are unchanged | PASS | **Red first**: on the start commit, `test_bytes_only_a_held_row_names_are_not_uploaded` → `AssertionError: bytes only a held row names were uploaded`, and the dry-run test lists them among the planned uploads. **Held only**: that test. The held-only bytes are absent from the bucket, the other team's file in the same week is uploaded, and the manifest is not in the bucket. The outcome is `withheld`, the code `MANIFEST_NAMES_SUPPRESSED_SOURCE`, `failure_codes` that code alone, `failed_sha256` empty, `held_rows` the one digest. The message still says `1 row(s) at a path a removal holds: <digest> (RM-2026-01)` and now adds `, whose bytes no other row names and were not uploaded (1)`. **Held plus unheld, one manifest**: `test_bytes_a_held_row_and_another_teams_row_name_are_uploaded`. **Held in one week, unheld in a later one**: `test_bytes_a_later_week_names_at_another_teams_path_are_uploaded_with_that_week`. One publish of the caselist uploads the bytes for the later week, completes it, and withholds the earlier one. **Dry run**: `test_a_dry_run_plans_no_upload_of_bytes_only_a_held_row_names` (planned uploads and bytes leave them out; `succeeded` is `False` as before). **Held counts unchanged**: `t21`'s like-for-like test (the held row against a withdrawn disclosure, from one listing) still has every outcome, code, `failed_sha256`, `failure_codes` and `succeeded` equal. Exactly one count differs: one `uploaded` and one planned `upload` fewer, the held-only bytes (Deviation 1). No new key in the publish JSON: no source action or result was added (Decision 1). **Mutants on the upload rule**: rows 1 to 4 of the mutation table, all caught |
| **ac3**: a manifest an earlier build wrote with such a row is named by `caselist status`, and running the removal again takes it out, by test | PASS | `test_status_names_an_earlier_builds_row_for_a_link_at_the_held_path`. An earlier build imports and publishes the link's week after the removal. Status names `held_skipped_rows == ("RM-2026-01",)`, puts the request in `removals_owed`, and still has `in_sync` true. Its report names no path, school, team code or file name, and no `.zip` or `.docx`. `test_running_the_removal_again_takes_the_links_row_out_here_and_in_the_bucket`: after the re-run, neither copy of the manifest has the row, the rest of it stays, and status owes nothing and agrees. Red on the start commit: the re-run keeps the row (`assert [{…}] == []`), and status has no such field (`AttributeError`). That red is shown instead by mutants 13 and 15, which keep the field and drop the rule. **The local copy** (your question): `test_running_the_removal_again_takes_the_held_only_bytes_off_this_machine_as_well`. After this build's publish left them off the bucket, the re-run puts the sha256 on the list as a whole file under the request and deletes the local blob. The row goes, and the next publish completes with nothing owed. `test_running_the_removal_again_keeps_bytes_another_teams_row_names`: only the row at the held path goes; the other team's row, blob and object stay |
| **Neither drift nor owed** (your check before building) | PASS | Every comparison of local blobs with the bucket, found by searching for `local_blob_sizes`, `list_remote_evidence`, `missing_sources` and `EvidenceSyncService(`. **`caselist status`** (also what the pull's report and retention stages ask, `CaselistStatusService`): `test_a_bucket_without_bytes_only_a_held_row_names_still_agrees`. Red on the start commit: the snapshot drifted. `test_status_does_not_count_bytes_the_publisher_left_out_as_missing`: `missing_sources == ()`, with the manifest still absent, as before. `test_a_bucket_without_bytes_another_teams_row_names_still_differs`: a copy another row names is still owed. **`store sync` push**: `test_store_sync_does_not_push_bytes_only_a_held_row_names` (`skipped`, reason `named only by manifest rows at a path a removal holds`, absent after `--apply`, the run `succeeded`); `…_pushes_bytes_another_teams_row_names` and `…_pushes_bytes_another_weeks_row_names_at_a_path_nothing_holds`. Through the composition root: `test_store.py::…::test_a_push_leaves_out_bytes_only_a_row_at_a_held_path_names`. Red on the start commit: `assert (2, 0) == (1, 1)`. The publisher's own invariant check never meets them, because they are not among the plan's sources. **Exit codes**: no comparison above changes one; mutant 14 is a held skipped row made drift |
| **Every build reads what this build writes** (the PM's notes: no new manifest field, no new sidecar) | PASS | `write_held_rows_files.py` (run by path, not collected) writes this task's scenario. An earlier build imports the held row's week and the link's week. This build publishes, the removal is run again, and the link's week is imported again. Written with this build and with the start commit; `t21`'s `write_held_path_files.py -k pull` wrote the `run/` part into each set. Each set was read with `t21`'s `read_held_path_files.py` by this build, the start commit and the agent's build: **six reads, every one exit 0**, every line the same but the header naming the writer. Compared directly: every manifest row and summary has the same keys in both builds. The link's week has one row fewer here and an identical summary. The removal log line has the same keys; only `manifest_rows_dropped` (5 here, 3 at the start commit: the link row in both copies) and `s3_versions_deleted` (1 here, 2 there: the held-only bytes were never uploaded) differ. The removal scopes differ only in moto's version ids. No file is new: the same five records here and in the bucket. After the publish, the start commit's bucket held one more source object, the held-only bytes (`sha256 c8c495e62ab0`). After the re-run the two buckets were the same |
| Node `held-rows`: `uv run pytest packages/debate_core/tests -k "caselist and (hold or held or publish)"` | PASS | `435 passed in 29.53s`, run as the spec writes it (414 before this task) |
| Full suite, four parts (`uv run --frozen pytest -n auto -m "not slow and not live" --part K/4`) | PASS | `1934 passed` (65 s); `1942 passed, 1 xfailed` (62 s); `1945 passed, 1 skipped, 2 warnings` (53 s); `1942 passed, 1 xfailed, 1 warning` (61 s). Each part ran under a hard stop. The skip is the parser eval waiting on human corrections. The warnings are `pytest_socket`'s, from the network-guard smoke checks |
| Lint, types, contracts, docs | PASS | `ruff format --check .`: 762 files formatted. `ruff check .`: clean. `uv run --frozen pyright`: `0 errors`. `lint-imports`: `12 kept, 0 broken`. `check_thin_handlers.py`: 22 within 25 statements. `docs_index.py --check-descriptions`: 35 described. `check_command_blocks.py --base origin/dev`: OK. `validate_specs.py`: `OK: 362 files, 38 epics, 304 tasks, 20 releases` |

### Mutation runs

Each run applied one textual change to committed source and ran the 122 to 123 tests of six files:
this task's file, `t21`'s two, the CLI status renderer file, `test_store.py` and
`test_caselist_publish.py`. Flags: `-p no:randomly -p no:cacheprovider --no-cov -n 4`. The driver
refuses a mutant whose target is not there exactly once, gives every run a new empty
`HYPOTHESIS_STORAGE_DIRECTORY` (working agreement 8; none of these tests is a Hypothesis property),
and restores the file from a byte copy in a `finally`, checking its sha256 and `git diff --quiet`.
Rows 1 to 20 ran on `1181216`, row 19 again and rows 21 to 24 on `75b15b2`. Every catch
below is a failing assertion; only row 6 also had errors.

| # | Mutation | Result | First failing test |
|---|---|---|---|
| 1 | **Upload rule, held only**: bytes only held rows name are uploaded | CAUGHT, 3 failed | `test_bytes_only_a_held_row_names_are_not_uploaded` |
| 2 | **Upload rule, held plus unheld**: bytes a held and an unheld row both name are held back | CAUGHT, 3 failed | `test_a_bucket_without_bytes_another_teams_row_names_still_differs` |
| 3 | **Upload rule, unheld only**: every source of a snapshot with held-only bytes is held back | CAUGHT, 4 failed | `test_bytes_only_a_held_row_names_are_not_uploaded` |
| 4 | Upload rule across the plan: a digest held only in one week is held back in every week | CAUGHT, 1 failed | `test_bytes_a_later_week_names_at_another_teams_path_are_uploaded_with_that_week` |
| 5 | The importer gives a skipped member at a held path a row | CAUGHT, 2 failed | `test_a_link_at_the_held_path_imports_with_no_row_at_that_path` |
| 6 | The importer withholds every skipped member's row | CAUGHT by 15 failures of earlier tests, with 41 setup errors | `test_an_archive_with_junk_the_hold_does_not_explain_is_left_for_retention` (`t21`). This task's guards errored in setup, because the shared store's own archives hold junk, so row 7 is the narrower mutant they run against |
| 7 | A skipped member is held wherever it is, once any path of its caselist is held | CAUGHT, 3 failed | `test_a_link_at_a_path_no_removal_holds_keeps_its_row` |
| 8 | A skipped member's hold is asked without the snapshot's date | CAUGHT, 2 failed | `test_a_link_at_the_held_path_in_the_week_the_hold_dates_from_keeps_its_row` |
| 9 | The inbox rewrite keeps a skipped member at a held path (`t21`'s rule, now through the shared function) | CAUGHT, 1 failed | `test_the_removal_rewrites_a_waiting_archive_without_a_link_named_as_the_removed_file` |
| 10 | The manifest rewrite keeps a skipped member's row at a held path | CAUGHT, 3 failed | `test_the_removal_drops_a_links_row_at_the_path_it_holds_the_first_time_it_runs` |
| 11 | The manifest rewrite drops every skipped member's row | CAUGHT, 1 failed | `test_the_removal_keeps_a_links_row_at_a_path_it_does_not_hold` |
| 12 | The plan's state after it holds none of the holds it is about to record | CAUGHT, 2 failed | the same first-run test |
| 13 | Status does not report a held skipped row | CAUGHT, 1 failed | `test_status_names_an_earlier_builds_row_for_a_link_at_the_held_path` |
| 14 | **A held skipped row makes its snapshot drift** (the exit code changes) | CAUGHT, 4 failed | the same |
| 15 | The removals owed leave out a held skipped row's request | CAUGHT, 5 failed | the same |
| 16 | **Status expects held-only bytes in the bucket** | CAUGHT, 2 failed | `test_a_bucket_without_bytes_only_a_held_row_names_still_agrees` |
| 17 | Status leaves out every held row's bytes, another team's copy included | CAUGHT, 1 failed | `test_a_bucket_without_bytes_another_teams_row_names_still_differs` |
| 18 | **A push sends bytes only held rows name** | CAUGHT, 2 failed | `test_store_sync_does_not_push_bytes_only_a_held_row_names` |
| 19 | A push holds back bytes another manifest's row names at a path nothing holds | **SURVIVED, then CAUGHT** | `test_store_sync_pushes_bytes_another_weeks_row_names_at_a_path_nothing_holds` |
| 20 | The held-back digests are asked on a pull, not on a push | CAUGHT, 2 failed | `test_store_sync_does_not_push_bytes_only_a_held_row_names` |
| 21 | The composition root builds `store sync` without them | CAUGHT, 1 failed | `test_store.py::…::test_a_push_leaves_out_bytes_only_a_row_at_a_held_path_names` |
| 22 | The status JSON counts no held skipped row | CAUGHT, 1 failed | `test_the_json_counts_each_held_skipped_row_by_request` |
| 23 | The status table leaves out its line | CAUGHT, 2 failed | `test_the_table_names_a_held_skipped_row_by_its_request_alone` |
| 24 | The withheld message does not say the bytes were not uploaded | CAUGHT, 1 failed | `test_bytes_only_a_held_row_names_are_not_uploaded` |

Row 16 is also the red I owed `test_status_does_not_count_bytes_the_publisher_left_out_as_missing`.
On the start commit that test passes, because the bytes were uploaded, so its red needs the
publisher fixed and status not. Row 19's survivor was a missing test: my push test's bytes were held
and unheld in the same manifest, so the per-manifest rule passed them and the cross-manifest step
was never exercised. I added the test and the mutant was caught. The message assertion behind row
24 was added before the runs (`1181216`), when I saw nothing read the new clause.

## Files changed

- **`debate_core.application`**
  - `caselist/pipeline.py`: `hold_on_skipped_member()`, the shared rule. A skipped member at a held
    path is `withheld`, so it gets no row; the module docstring says why.
  - `caselist/publish_plan.py`: `held_only_digests()`, `held_skipped_rows()`,
    `skipped_paths_in_manifest()`, `LocalSnapshot.skipped_paths`, `SnapshotPlan.held_back`. The plan
    leaves held-only digests out of a snapshot's sources. New docstring section, "Bytes only held
    rows name are not uploaded".
  - `caselist/publish_service.py`: the withheld message says how many bytes were not uploaded.
  - `caselist/status_service.py`: `SnapshotStatus.held_skipped_rows`, counted in `held_snapshots`
    and `removals_owed`. A snapshot's `sources` leaves out held-only digests; `suppressed` is counted
    on its own. New docstring section, "Bytes the publisher does not upload".
  - `caselist/removal_plan.py`: the manifest rewrite drops a skipped member's row at a held path.
  - `caselist/inbox_purge.py`: `t21`'s inbox rule now calls the shared function.
  - `caselist/evidence_listing.py`: `held_back_digests()` for `store sync`; snapshots carry their
    skipped rows' paths.
  - `evidence_sync.py`: `HeldBackDigests`, `EvidenceSyncService(held_back=)`, and a push plans
    those blobs `skipped`.
- **`debate_cli`**: `commands/caselist.py`, where status's JSON gains `held_skipped_rows` and
  `held_skipped_row_requests`, and the table one line per kind of held row; `container.py`, which
  builds `store sync` with the held-back digests.
- **Tests**
  - New: `packages/debate_core/tests/application/caselist/test_held_rows_publish_nothing.py` (21).
  - Run by path, not collected: `write_held_rows_files.py`.
  - `test_held_path_loose_ends.py`: `t21`'s like-for-like publish test (Deviation 1).
  - `packages/debate_cli/tests/commands/test_caselist_status_held_paths.py`: 4 renderer tests.
    `test_store.py`: 1 through the composition root. `test_caselist_publish.py`: two keys in the
    every-key list (Deviation 2).
  - `tests/smoke/test_caselist_remove_smoke.py` and its row in `tests/smoke/README.md` (Deviation 3).
- **Docs**: `docs/runbooks/caselist-removal.md`, step 9. The held-row bullet no longer implies the
  bytes go up: the publisher and `store sync` leave them out, and bytes an older build published
  stay until the re-run. There is a new bullet for the skipped row, the two JSON fields, and what
  the re-run takes, the local blob included.

## Deviations from the spec

1. **One hand-written expectation of `v1-e30-t21`'s changed, because your ruling replaced its
   premise.** `test_the_publisher_withholds_a_manifest_with_a_held_row_exactly_as_one_with_a_suppressed_row`
   compared every count of a held row's publish with a withdrawn disclosure's (`t21`'s Decision 2).
   It is renamed without "exactly", and its counts now differ by exactly one: the held-only bytes,
   one `uploaded` and one planned `upload` fewer. Every outcome, code, `failed_sha256`,
   `failure_codes` and `succeeded` is still equal, and it asserts `held_back` on both plans.
2. **`v1-e30-t12`'s every-key status test gained two keys**, `held_skipped_rows` and
   `held_skipped_row_requests`, checked as `0, []`. The same kind of change as `t21`'s Deviation 2.
3. **`tests/smoke/` is outside `constraints.packages`**, as it was for `v1-e30-t18` and `v1-e30-t21`
   (accepted both times). Working agreement 5 asks for a smoke check when a user-facing surface
   changes, and `caselist import` and `caselist status` did. One new check, and a clause in its
   README row.
4. **`evidence_sync.py` is in `debate_core.application`, but the spec does not name `store sync`.**
   Your notes asked me to find every comparison of local blobs with the bucket and show that a
   held-only digest is neither drift nor owed. A push that planned it `new` owed it, and `--apply`
   would have uploaded it. See Decision 3.

## Decisions and assumptions

1. **A held-only digest leaves the plan's sources rather than getting a new action.** A new
   `SourceAction` or `SourceResult` would add a key to every count dictionary in the publish JSON
   and change "the publish output's held counts". Marking it `suppressed` would misreport it as a
   suppressed source. Left out, it is neither uploaded nor verified, whatever the bucket holds. No
   count includes it. `SnapshotPlan.held_back` names it in memory, and the withheld message counts
   it. Every source count is one smaller for each such digest. That is the ruling, and nothing else
   moves.
2. **"Held only" is per manifest; "another row" is any row not at a held path.** A digest is held
   back from a snapshot when every stored row of that manifest naming it is held. A row whose own
   disclosure the list withdrew counts as another row, so a withdrawn copy's bytes go up as they
   always did. Per manifest, because a later week whose own row names the bytes uploads them as its
   own; row 4 is the plan-wide alternative, which held them back. Status uses the same rule: a
   held-only digest is not among the snapshot's `sources`, so its absence from either side is not
   missing. `suppressed` is now counted from suppressed sources alone, rather than as everything the
   count leaves out.
3. **A `store sync` push skips held-only bytes, across every manifest on this machine.** A blob names
   no corpus or snapshot, and the operator picks its prefix, so a row in any other manifest (another
   week, another caselist, a camp release) is another holder's copy and the push sends it. With no
   path held, nothing is read. The service takes the rule as an optional argument, which the
   composition root always passes (row 21). A pull is unchanged. `store sync` still pushes a manifest
   that has a held or suppressed row; that is older than this task, and is Follow-up 2.
4. **A skipped member is withheld only when it sits at the held path itself**, the rule `t21` gave
   the inbox rewrite. Junk that shadows a held link, such as an AppleDouble file of it, keeps its
   row, as it does in `t21`'s inbox rewrite: neither held-path rule reads a skipped member as a real
   file for the shadow check. Follow-up 3.
5. **The publisher does not withhold a manifest for a held skipped row** (PM question 1). The spec's
   description and your notes give the rule to the importer, the rewrite and status, and keep the
   exit codes. An earlier build's manifest with only such a row publishes today. Withholding it
   would make that publish fail, and the code it would fail with is the one for a suppressed row.
   Status names it, and the re-run takes it out of both copies.
6. **A held skipped row is named by request alone.** It has no digest. Status, the JSON and the table
   give the request holding the path and a count, never the path. Request ids were accepted as
   output under `t21`'s Decision 6.
7. **What the re-run takes is what `v1-e30-t13` already planned.** No removal code changed for the
   bytes. A held row is a later upload at the held path. Held nowhere else, it is removed whole: the
   list, the local blob, every object version and the row. Held at another live path, it is withdrawn
   from the held path only. Nothing is deleted from the bucket that this build did not upload, and
   the removal log says so (`s3_versions_deleted` 1, against 2 at the start commit).
8. **The removal rewrite asks the plan's state after it,** so the first run drops a link's row in a
   week already imported, as it does a row the list already stops (row 12).
9. **Nothing read a real store or called AWS.** Every test, script and cross-build read used
   fixtures, moto and temporary directories. The machine's load average was 5 to 144 while I worked;
   every long command ran under a hard stop and none hit it.

## Operator follow-ups

None. No command here is over two minutes, needs a credential, or changes anything outside the
worktree.

## Follow-up work

1. **PM question 1: should the publisher withhold a manifest with a held skipped row?** (E30). See
   Decision 5. Until the agent runs a build with this task, `v1.1.0-dev.7` writes such rows and its
   own publisher publishes them. That is a path, with its school and team code, in the bucket until
   the removal is run again. My recommendation is yes, with the same outcome and code as a held
   stored row, accepting that such a publish then fails where it succeeds today. The PM's notes ruled
   the other way on exit codes, so I did not.
2. **`store sync` pushes manifests the publisher withholds** (E29 or E30). A push sends every local
   manifest, including one with a suppressed row (since `v1-e30-t07`), a held row (`t21`) or a held
   skipped row. Only `_suppression/` records and suppressed blobs are skipped. The publisher's
   withholding rule could be asked of the `manifests/` keyspace too.
3. **Junk shadowing a held link keeps its row** (E30). See Decision 4. `__MACOSX/<dir>/._<name>`
   beside a link at the held path names the same file. Both held-path rules, the import's and the
   inbox rewrite's, would need it.
4. **The parsed store is not asked about held-only bytes** (E31). If an older build stored a held
   upload and `caselist parse` parsed it, `caselist parse --publish` sends its per-source file and its
   aggregate rows. The parser skips only whole-source suppression. This is not a comparison of blobs
   with the bucket, so it was outside your check, but it is the same bytes in another form.
5. **The evidence store guide's `skipped` row** (`docs/guides/evidence-store-cli.md`, "What the
   summary means") does not list the new reason. `docs/guides/` is outside this task's packages.

### PM questions

```text
v1-e30-t22 asks the PM, 2026-10-17:

1. The publisher still publishes an earlier build's manifest that has a skipped member's row (a
   symbolic link) at a held path. The agent's v1.1.0-dev.7 writes such rows and publishes them
   itself; this build's status names the row and the removal run again drops it, here and in the
   bucket. Options:
   (a) leave it, as the spec and your notes list only the importer, the rewrite and status (done);
   (b) withhold such a manifest as a held stored row's is, same outcome and code
       MANIFEST_NAMES_SUPPRESSED_SOURCE, so such a publish fails where it succeeds today.
   Recommendation: (b), filed as a small E30 task. A held path's name reaching the bucket is what
   this task exists to stop, and the failing publish names its fix, the removal run again.

2. store sync pushes a local manifest the publisher withholds (a suppressed, held or held skipped
   row). It has done so since v1-e30-t07. File it (E29 or E30), or is store sync of manifests
   meant to stay a raw mirror?
```

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

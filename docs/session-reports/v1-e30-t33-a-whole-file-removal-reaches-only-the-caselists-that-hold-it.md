# Session report: v1-e30-t33-a-whole-file-removal-reaches-only-the-caselists-that-hold-it

| | |
|---|---|
| Task | `v1-e30-t33-a-whole-file-removal-reaches-only-the-caselists-that-hold-it` — A whole-file removal deletes only the aggregates of the caselists that hold the file, and its rebuild works in bucket mode |
| Spec | [`plan_specs/v1/e30-caselist-ingestion/t33-a-whole-file-removal-reaches-only-the-caselists-that-hold-it.yaml`](../../plan_specs/v1/e30-caselist-ingestion/t33-a-whole-file-removal-reaches-only-the-caselists-that-hold-it.yaml) |
| Epic / release | `v1-e30-caselist-ingestion` / `v1.1` |
| Branch | `task/v1-e30-t33-a-whole-file-removal-reaches-only-the-caselists-that-hold-it` |
| Session status | COMPLETE, with the Goal left `InProgress`: ac3 is the operator's run in dev, after merge and the PM's word <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

Built as the PM ruled on 2026-11-05. A whole-file removal, and now a withdrawal too, reaches only
the version directories, on each side, that hold a per-source parsed file of what it takes out.
It rewrites each of their aggregates in place without those rows, keeping every other line byte for
byte, and checks each rewrite before writing it. In the bucket it purges every other version. A
retired (tagged) directory's aggregates are deleted instead. Nothing is rebuilt afterwards, from
the Mac or in the cloud, backfiles included. The plan shows the aggregates in a section of their own,
with row counts and bytes, and `--json` carries them. Each execution records the aggregates it left
clean beside the log, and `caselist status` counts residue only there. The runbooks follow: step 5
and P1b, J7, the backfile runbook and the parsed-store doc. Every session-runnable criterion passed:
the red run was 25 failed and 1 passed against a refuse-nothing skeleton, and all 21 mutants were
caught, 6 of them after adding five tests and strengthening one. The Goal stays `InProgress`
because ac3 is the operator's rerun of J4 to J9 in dev, which waits for this branch to merge and for
the PM's word on `--execute`. Look first at Decisions 2 and 3 (a re-run purges older versions of
tables its request reached before; a table that held no row is recorded clean), Follow-up 1 (the
parse owed a removal still clears) and the files outside the task's packages under Deviations.

## The PM's ruling (2026-11-05), as the build reads it

* **(a)** As proposed, with one addition: a version directory retention has tagged
  (`debate-retention=superseded`, parsed-store-retention.md) is not rewritten. Its reached aggregates
  are deleted with their versions, as before, and the plan says so per directory; nothing is rebuilt.
* **(b)** As proposed, with row counts in the dry run and each table's bytes; tagged directories under
  their own heading as deleted; the new `--json` key with the smoke pins updated.
* **(c) Q1** The rewrite in place, under the bucket's run lock (say where it is taken and held); each
  rewrite checked before it is written (rows after = rows before less the rows naming the removed file,
  every kept line byte-identical, an unreadable line stops the run `INCOMPLETE` with nothing written);
  and every file a version directory holds listed first, saying what each carries from one source.
  **Q2** Withdrawals use the same rewrite, in this task. **Q3** Surviving clusters keep their ids and
  membership. **Q4** A new record beside the log; residue counts only older versions other than the
  rewrite, in the directories reached; the runbooks say `caselist status` runs from a build carrying
  this task. **Q5** Withdrawals stay in; the PM sets the estimate to 8h.
* **(d)** As proposed; promotion item 8 uses the same check, and prod's removal runs from a build
  carrying this task.
* Tests on synthetic stores with moto, shown failing first, covering the eight cases the ruling lists;
  mutants on the rules. No `--execute` outside tests until the PM's word.

## Proposal for the PM's ruling (ac1)

Read first: `removal_plan.py` (`_objects`, the `REMOVE` branch at `parsed_caselists = [*disclosing, OPENEV]`
and the aggregate loop after it), `removal_service.py` (`execute`'s order), `removal_residue.py`
("Manifests and aggregates"), `caselist_parse.py` (`_rebuild`, `_occurrence_rows`), `near_duplicates.py`
(the cluster id), `search_index_build.py` (`_clusters`, `_card_of`), `ports/parsed_store.py`,
caselist-removal.md step 5 and P1b, evidence-search.md J7, v1-e39-t10's operator record of 2026-11-05,
v1-e40-t10's restore and policy 1.18.

### (a) Which aggregates a whole-file removal plans

**The rule.** On each side, the bucket and this machine, the aggregates (`index.jsonl`, `failures.jsonl`,
`occurrences.jsonl`, and `camp_paths.jsonl` in `openev`) of exactly the `(caselist, version directory)`
pairs where that side holds a per-source file of the digest, current or in any version
(`parsed/<caselist>/<version>/sha256/ab/cd/<digest>.jsonl`). Nothing else.

**Why the per-source file is the right witness.** A version directory's aggregates are rebuilt from that
directory's own per-source files and nothing else (`_rebuild` reads `read_entries(caselist, version)`), and
`parse --publish` sends the per-source files before the aggregates. So an aggregate that names the digest
has the digest's per-source file beside it, in the same directory on the same side. A caselist whose
manifest holds the file but never parsed it has no per-source file and no row to remove. The plan already
lists every known caselist's `parsed/` prefix to find the per-source files, so this costs no new listing.

**The executor's order changes so that the witness outlives the rows.** For each reached directory: the
aggregates are handled first, then the per-source file is deleted with all its versions. A run that stops
in between leaves the per-source file, and a re-run finds the directory by it.

**Re-runs (v1-e30-t19).** A first run by an earlier build deleted per-source files before aggregates, so
its per-source files may be gone while its aggregates remain. For a request with an earlier run in the
log, the plan therefore also reads the current aggregates of every version directory of (1) each
caselist that request's scopes name and (2) each caselist the withdrawal record names for the file. It
plans each one that still names the digest.

**The seed's case.** The plan reaches only the bucket's `parsed/testcl26/2026.10.27-docx-7/`
aggregates. It reaches nothing on this machine, whose own store never held the seed. It does not reach
`testcl26`'s older directory (RM-2026-90's weeks) or any other caselist.

**Withdrawals** already plan only the caselists they withdraw from, and get the same per-directory rule.

### (b) The plan's text

The file's own objects stay under **WILL BE REMOVED**: the local blob, the `raw/` objects and the
per-source parsed files. Aggregate lines leave that section for one of their own, **AGGREGATES REWRITTEN
WITHOUT THE REMOVED ROWS**, grouped by side and version directory. Each line gives the key, the rows
that name the file (counted from the current object, which the dry run downloads) and the older versions
to be purged (or "versions not counted"). **TO CARRY IT OUT** adds: "N aggregates in M version
directories are rewritten in place; nothing is rebuilt afterwards". `--json` gets the same section as a
new key. The smoke and loose-ends pins hold removal JSON shapes whole, so they are updated in the same
change.

### (c) How the aggregates come back in bucket mode

| Option | Holds? | Why |
|---|---|---|
| Delete, then `parse --publish` from a copy restored under the dev lock (v1-e40-t10) | Partly | The restore brings each caselist's *current* directory only, so an older directory the removal reached stays without aggregates. It also means a restore (J2 took 351.8 s) plus a clusterer rebuild (536 to 741 s recorded for a large caselist), and the aggregates are absent from the delete until the publish. A backfile still needs its cloud task |
| Delete, then the removal rebuilds from the bucket's per-source files | No | A rebuild needs every per-source file of the directory, about 4.7 GB for `hspolicy26` under `docx-6`, plus the manifests and the clusterer, all on the Mac |
| Delete, then a cloud task rebuilds | Works, slowly | It needs a new task entry point. A backfile rebuild ran about 95 min on 2026-11-02, the gap stays, and it has to fit around the cloud run's day and lock |
| **The removal rewrites each reached aggregate without the rows that name the removed digest, and purges the older versions, as it does for manifests** | **Yes** | See below |

**What each aggregate's rows carry:**

* `index.jsonl`: one `SourceEntry` per source, with `source_sha256`. Its fields are the store record,
  the format, size, outcome, reason, detail and that source's card count. Every field is the source's
  own.
* `failures.jsonl`: the same entries, for sources that have no document.
* `occurrences.jsonl`: one row per card per disclosure. Each row has `source_sha256`, `disclosure` (the
  disclosure digest, or `None` for a camp row), the span, `snapshot`/`last_snapshot` (per disclosure),
  `exact_fingerprint`, `completeness`, and two fields worked out across the whole directory:
  `cluster_id` and `membership`.
* `camp_paths.jsonl` (openev only): one line per camp path, with `source_sha256` and
  `occurrence_table_sha256`, the SHA-256 of the `occurrences.jsonl` bytes it was written beside.

**Where the rewrite is exact.** Every row names its source digest, so every removed row goes. For
`index.jsonl` and `failures.jsonl` the result is byte for byte what a rebuild gives: each row is decided
for its own source alone. No aggregate stores a statistic. Totals and cluster counts are run outputs,
and the index build recomputes its own counts and `occurrences_sha256`.

**Where it differs from a rebuild: the surviving rows' `cluster_id` and `membership`.** They were worked
out with the removed cards present:

1. The cluster id is the smallest exact fingerprint in the cluster. If a removed card held the
   smallest, the survivors keep its fingerprint as their id.
2. Two clusters joined through a removed body (a copy, or the one witness for a cut) stay joined.
   Every two bodies in a cluster still overlap, because `overlap_throughout` is checked pairwise.
   Clusters a removed body kept apart, as a second witness, stay apart.
3. An abbreviated card linked to a removed full card keeps `ABBREVIATED_LINK`, in a cluster with no
   full card left. One left `UNLINKED` because it matched a removed card and another stays `UNLINKED`.

**I do not think this makes the rewrite wrong.** These are not the removed file's rows, and no removed
text survives. The surviving table is the one every reader already sees right after a removal: the
index build drops suppressed rows and keeps the cluster ids (`_clusters`). So the index built from a
rewritten table is the one the pilot serves today between a removal and its rebuild. No reader assumes
a cluster id is one of its rows' fingerprints: `_card_of` picks the representative from the rows and
checks that row's own fingerprint. The caselist's next ordinary rebuild recomputes both fields.

**Mechanics.**

* Each reached table is streamed. Each line is parsed as JSON only to read `source_sha256` (and
  `disclosure` for a withdrawal). A line that is kept keeps its bytes, so a newer build's rows survive
  unchanged and the sort order holds. A line that is not a JSON object with a source digest stops the
  run `INCOMPLETE` before anything is written.
* The rewrite goes up through `put_file`, which records the SHA-256 as the publisher does, so a later
  restore's digest check passes. Once the bucket confirms the rewrite as the current version, the
  takedown credential deletes every other version. On this machine the rewrite is an atomic replace.
* `camp_paths.jsonl` is rewritten after its table, without the removed digest's lines and with the new
  table's SHA-256. Without that, every camp row would lose its camp path digests.
* In bucket mode all of this runs under the run lock that `--execute` already holds.
* A backfile such as `hspolicy25` goes the same way, with no cloud task.
* Cost: each reached table is downloaded and uploaded once. This Mac's stale tables measure up to
  95.0 MB (`hspolicy26` occurrences, sizes read with `stat` only). I have not measured the bucket's.
* No rebuild, no restored copy and no cloud task follow the removal. A table whose only rows were the
  removed file's is rewritten empty, which is also what a rebuild would give.

**What else has to change with it.**

* `caselist status` counts every aggregate version older than the removal's completion, in every
  caselist the removal touched, as residue. So it would count the rewrite itself, and every directory
  (a) leaves alone.
* The fix is to record each rewrite (key and version id) and count only the older versions other than
  the rewrite, in the reached directories.
* `removal-scopes.jsonl` is read by the installed build under `extra="forbid"`
  (`test_suppression_list_is_read_by_every_build.py`), so a new field there would make that build
  refuse the file. The record goes in a file of its own beside the log, for the reason the scopes went
  beside the log.
* An installed build older than this one will report the rewrite as residue until it is upgraded.

### (d) The runbooks

* **caselist-removal.md, step 5.** Drop "Then rebuild the parsed card store's aggregates" and the
  backfile paragraph. Say instead that the removal rewrites each aggregate the plan lists, in the bucket
  and here, purges the older versions, and prints the count. Nothing is rebuilt afterwards, backfiles
  included.
* **P1b.** Becomes "Right after `DONE`: the aggregates were rewritten": `DONE`'s aggregate count must
  equal the plan's, and no parse runs. P3's sentence on "aggregates hold no occurrence rows" now means
  the store's only rows were the removed file's.
* **caselist-backfiles.md.** "A removal adds a rebuild for each backfile" goes, since there is no
  rebuild.
* **evidence-search.md, J7.**
  * The dry run goes on only if **WILL BE REMOVED** lists the one file, its object under
    `raw/caselist/testcl26/` and its parsed file under `parsed/testcl26/2026.10.27-docx-7/`.
  * **AGGREGATES REWRITTEN** must list exactly that directory's three aggregates, in the bucket only.
  * Then step 5's `--execute`, as its own block, guarded on a set `DEBATE_` variable and a running pull.
  * No P1b parse.
  * J8 and J9 stay as they are. J9's check holds, since no other store's `occurrences_sha256` changes.
* **parsed-card-store.md and the module docstrings.** Every sentence that says a removal deletes the
  aggregates "until the next run" is corrected: `removal_plan`, `removal_residue`, and the port's
  `read_index`.

### Effort

This is more than the spec's 4h: the planner, a new plan section and JSON key, the executor's
rewrite, order and purge, the rewrite record and the residue rule, the CLI text, and three runbooks.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `a-whole-file-removal-reaches-only-the-ca`: Removal reaches its caselists | Done | Its criterion passes (468 tests); red run against a refuse-nothing skeleton, then 21 mutants |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the proposal ((a) which aggregates, (b) the plan's text, (c) the rebuild in bucket mode, backfiles included, (d) the runbooks) is ruled on by the PM before any code | PASS | The proposal was committed (`6577c13`) before any code. The PM's ruling of 2026-11-05 is recorded above (`98aba1c`), and the first code commit (`260dcf1`) follows it |
| ac2: one caselist's file plans only that caselist's aggregates, in the version directories holding its parsed file; two caselists plan both; a re-run plans what a first run left; the ruled rebuild restores the aggregates without the removed rows; on synthetic stores, shown failing first | PASS | `test_removal_rewrites_aggregates.py` (17 tests), `test_removal_rewrites_camp_path_aggregates.py` (1) and `test_removal_aggregates_rewrite.py` (14), on moto with synthetic stores. Against the skeleton: `25 failed, 1 passed in 5.42s` (below). Against the build: `.venv/bin/python scripts/hard_stop.py 100 .venv/bin/python -m pytest <the three files> -q -n 4` → `31 passed in 8.85s`. Coverage, by the ruling's list: one caselist (`test_a_file_one_caselist_holds_reaches_only_the_directories_holding_its_parsed_file`), two (`..._two_caselists_hold_reaches_both`), a backfile (`test_a_backfile_held_only_in_the_bucket_...`), a tagged directory deleted, not rewritten (`test_a_retired_directory_...`), a stopped run found again by its per-source file (`test_a_run_stopped_after_the_aggregates_...`), a team withdrawal and a camp-path withdrawal (`test_a_team_withdrawal_...`, the camp-path module), an unreadable line stopping the run with nothing written (`test_an_unreadable_line_...`), and the residue check after a rewrite (`test_status_counts_...`, two tests) |
| ac3: the operator reruns J4 to J9 in dev with J7's `--execute` and the ruled rebuild, the card gone in J8, and the PM records it (operator) | NOT RUN | Needs this branch merged into `dev`, a dev build carrying it installed, the AWS profiles, and the PM's word on `--execute` (the ruling's last line). The blocks are evidence-search.md's J2 to J10, with J7 as rewritten (Operator follow-ups) |
| Node: Removal reaches its caselists tests pass (`uv run pytest packages/debate_core/tests -k removal`) | PASS | `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests -k removal -q -p no:cacheprovider -W ignore` → `468 passed in 103.02s` (468 of 14,682 collected) |

### The red run

The skeleton took every rule out:

* every version directory of every caselist was reached;
* no row of any table was dropped;
* a line that could not be read was read as a row;
* the check before a write passed anything;
* no directory was ever retired;
* residue used the old rule.

The API and wiring were as built. Script: the scratchpad's `skeleton.py`, applied to the committed
build `260dcf1` and restored with `git checkout HEAD --`.

Against it: `25 failed, 1 passed in 5.42s`. By kind:

* 13 failed an `assert`, 8 raised `DID NOT RAISE`, and 2 failed on an `index.jsonl` comparison and 1
  on an "after the aggregates" assertion.
* 1 is a `KeyError`. It is the skeleton's own artifact: reading an unreadable `{"no_source": ...}` line
  as a row let it reach the row rule, which indexes `source_sha256`. The real code refuses that line
  first.
* The one pass is `test_a_surviving_cluster_keeps_the_id_a_removed_card_gave_it`. A rule that drops
  nothing keeps every id, so that test guards Q3, not a rule.

### Mutants

21 mutants on the rules, in `removal_aggregates.py`, `removal_plan.py`, `removal_service.py` and
`removal_residue.py`. Script: the scratchpad's `mutants.py`. Each run used a fresh
`HYPOTHESIS_STORAGE_DIRECTORY`, though none of these tests uses Hypothesis. Each ran `-x` against the
new test files, plus the residue files for residue mutants. All 21 are caught.

15 were caught at once, each by an assertion or a `DID NOT RAISE`:

* every directory reached;
* an index row dropped for a withdrawal;
* an emptied release ignored;
* a camp path line's own path ignored;
* no re-stamp;
* a row without a source accepted;
* the count check skipped;
* never retired;
* aggregates written after the per-source deletes;
* an unreadable plan not refused;
* residue by the old rule;
* residue counting the clean version;
* a withdrawn copy never taken whole;
* a re-run skipping older versions of tables reached before;
* a table that held no row not recorded.

6 survived or were masked, each fixed by a test, then caught:

| Mutant | Why it survived | Now caught by |
|---|---|---|
| reach by current per-source files only | no test hid a per-source file under a delete marker | `test_a_per_source_file_left_only_as_an_older_version_still_reaches_its_directory` |
| camp rows asked by disclosure only | no camp row had every camp path stopped without its release emptied | `test_a_camp_row_whose_every_camp_path_is_stopped_goes_though_no_release_was_emptied` |
| the check's byte comparison skipped | the digest check refused the tampered file first (a fallback masking it) | `test_the_check_refuses_a_kept_line_that_is_not_the_tables_bytes`, now given a report whose digest matches the tampered file |
| no changed-since-plan check | no table changed between the plan and the execution | `test_a_table_changed_since_the_plan_stops_the_run_with_nothing_written` |
| a rewrite purging only what a re-run purges | the two rules agree on a first run | `test_rows_put_back_after_a_completed_removal_are_taken_again_with_the_version_that_held_them` |
| the purge ignoring clean versions | no re-run of a completed request reached its directory again | `test_a_rerun_of_a_completed_withdrawal_leaves_the_version_it_left_clean` |

### Before the report

The affected set selects **491 test files**. The root conftest imports
`debate_core.application.ports.parsed_store` (a docstring changed) and `ports.version_directories`
(the new `RetirementTags` protocol), through `cassette_filing`. That is far over two minutes, so
under agreement 10 it is left to the pull request's `ci` check, and it was not handed to the
operator. What ran instead, each bounded with `scripts/hard_stop.py 115`:

| Run | Result |
|---|---|
| The changed test directory, `packages/debate_core/tests/application/caselist/`, in two runs: the removal, residue, status, parsed-store, withdrawal and sweep files, then the rest | `472 passed in 66.99s`; `1427 passed in 51.33s` |
| The always-run list (`tests/architecture`, `tests/specs`, the CLI's `test_app.py`, `test_help_rendering.py`, `test_container_factories.py`) and `tests/docs` | `562 passed in 44.16s` |
| `packages/debate_cli/tests/commands` and `bucket_mode/test_bucket_mode_removal.py` | `560 passed in 39.34s` |
| The parsed-store and S3 integration tests, `test_search_index_store_check.py`, `test_caselist_parse*.py`, `test_camp_path_on_occurrence_rows.py` | `334 passed in 7.28s` |
| `tests/smoke/test_caselist_remove_smoke.py` | `42 passed in 76.30s` |
| `uv run ruff format --check .`; `uv run ruff check .` | `1973 files already formatted`; `All checks passed!` |
| `uv run pyright packages/debate_core packages/debate_cli` | `0 errors, 0 warnings, 0 informations` |
| `uv run lint-imports`; `uv run python scripts/check_thin_handlers.py` | `Contracts: 20 kept, 0 broken.`; `OK: 72 ... handlers within 25 statements` |
| `uv run python scripts/check_command_blocks.py`; `uv run python scripts/check_links.py` | `OK: no # comments in 678 shell code blocks`; `OK: 3615 relative links and anchors` |
| `uv run scripts/validate_specs.py` | `OK: 637 files, 41 epics, 574 tasks, 22 releases` |
| The installed build's own code (`v1.1.0-dev.342`, `git archive` to the scratchpad) reading what this build writes beside the log: `CHECK_AN_OLDER_BUILD_READS=this-builds-files PYTHONPATH=... pytest check_an_older_build_reads_this_builds_files.py` | `5 passed`. *status with the residue check: completed; caselists checked: openev, testcl26*, *removals not checked: 0*: the new `removal-aggregates.jsonl` is ignored by that build, as designed |

**After the PM review: the pull request's CI.** Part 3 of 8 failed one test that none of the runs
above reached: `bucket_mode/test_backfile_import.py`, whose
`test_running_it_again_rebuilds_the_aggregates_after_a_removal_with_no_second_download` pinned the
old behaviour (*assert not ['parsed/testcl25/2026.11.03-docx-9/occurrences.jsonl']*). It is renamed
`test_a_removal_rewrites_the_aggregates_in_the_bucket_and_running_it_again_leaves_them_without_the_rows`.
It now asserts that the removal leaves the backfile's table without the removed file's rows and with
the other two sources' rows. It keeps the part where running the import again downloads nothing a
second time and leaves the rows out. A mutant in which `occurrence_goes` keeps a whole-file row
fails it at the new assertion. Three docstrings that said a removal deletes the aggregates until the
next parse now name the retired directory (`file_recipes.py`, `search_index_build.py`,
`test_caselist_parse_newer_fingerprint_table.py`).

| Run | Result |
|---|---|
| `packages/debate_cli/tests/bucket_mode/test_backfile_import.py` | `33 passed in 108.22s` |
| `test_caselist_parse_newer_fingerprint_table.py` | `13 passed in 2.19s` |
| ruff format and check, pyright on the two test files | unchanged, `All checks passed!`, `0 errors` |

## Files changed

* **`debate_core/application/caselist/removal_aggregates.py`** (new). The inventory of a version
  directory, the row rule (`RowsRemoved`), the streaming rewrite (`rewrite_table`,
  `rewrite_directory`) and the check before a write (`check_rewrite`).
* **`removal_plan.py`**. `AggregateAction` and `AggregateChange`, the plan's `aggregates`, the reach,
  and `rows_removed` and `purges`. `ObjectKind.PARSED_AGGREGATE` is gone: aggregates are no longer
  objects the plan deletes. The constructor takes `local_parsed_objects` and `retirement`.
* **`removal_service.py`**. Aggregates are staged and checked before anything is written. Bucket
  aggregates are handled before the per-source deletes, local ones before the local files.
  `AggregatesLeft`. The record beside the log. The report's counts.
* **`removal_residue.py` and `status_service.py`**. `AggregateReach`: residue is counted within a
  build-carrying-this-task removal's record, and by the old rule for older ones.
* **`ports/suppression.py` and `caselist/suppression.py`**. `RemovalAggregatesEntry` and
  `AggregateRewriteRecord`, `removal-aggregates.jsonl` beside the log, read and appended with the
  scopes.
* **`ports/version_directories.py` and `integrations/s3/version_directories.py`**. `RetirementTags`,
  and `S3VersionDirectories.retired`.
* **`ports/parsed_store.py` and `caselist_parse.py`**. Docstrings only.
* **`debate_cli`**. The plan's sections, the `DONE` line, the `aggregates` and `aggregates_done`
  JSON keys, and the container's wiring.
* **Tests.** Three new core files and one new CLI file. The shared world passes the two new
  constructor arguments only to a build that takes them. Tests that pinned the old behaviour now pin
  the ruled one (Deviations). The stored records `written_by_this_build/` gained
  `removal-aggregates.jsonl`, written by `write_stored_suppression_lists.py`.
* **Docs.** `caselist-removal.md` (step 4's plan sections and checklist; step 5; step 6; step 7's
  prod rebuild removed; P1b; P3's sentence; the residue section), `evidence-search.md` (J7 and
  promotion item 8), `caselist-backfiles.md`, `caselist-scheduled-sync.md` (one table row) and
  `docs/data/parsed-card-store.md`.

## Deviations from the spec

1. **Files outside `constraints.packages`.**
   * `tests/smoke/test_caselist_remove_smoke.py`: the ruling's (b) asked for the smoke pins to be
     updated. Its removal fixture now parses the removed file, so the removal reaches a directory as
     in production.
   * `docs/runbooks/caselist-scheduled-sync.md`: one table row linked to the old P1b heading. It is
     `docs/runbooks`, so inside; listed for completeness.
   * `docs/guides/parsed-store-publish-only.md` says an aggregate can be *gone: a removal*. That is
     still true of a removal by an older build, so I left it.
2. **Existing tests whose expectations changed with the ruling.**
   * `test_parsed_store_removal.py`: the older directory's tables are rewritten, not deleted.
   * `test_removal_covers_later_uploads.py`: its placeholder aggregates are now readable rows, and
     its aggregates test checks the rewrite.
   * `test_manifest_and_aggregate_residue.py`: its `removed` fixture parses the removed file in both
     directories. "Deletes every version of every aggregate" became "leaves every aggregate of a
     directory holding no parsed file of it", and a test of the rewrite to one version was added.
   * `test_residue_clearing_gaps.py`: its fixture parses the shared file. "Without a withdrawal
     record the re-run has no caselist to plan aggregates for" became "still finds the directory by
     its parsed file". That is stronger than the record, because the per-source file stays while
     other teams hold the file.
   * `test_caselist_remove_output_loose_ends.py`: the pinned JSON key sets gained `aggregates` and
     `aggregates_done`.
   * `test_suppression_list_is_read_by_every_build.py`: this build adds four files beside the list
     and log, not three.
3. **The estimate.** The work took more than the spec's 4h; the PM said the next batch sets it to 8h.

## Decisions and assumptions

1. **The row rule** is a rebuild's own rule, asked of each row alone, and only of a source the plan
   names:
   * A source removed whole, or a withdrawn copy no other holder in the caselist keeps, loses every
     row.
   * A withdrawal whose copy stays loses the occurrence rows the list will stop
     (`occurrence_is_stopped`, with the row's camp paths from `camp_paths.jsonl`).
   * A camp file loses a release's rows when the plan deletes that release's camp-file record, which
     it does only when no other row of the release holds the file.

   The caselists a withdrawal's rows are asked in include a held path an import refused it at
   (`v1-e30-t23`). The raw-copy rule is unchanged.
2. **A re-run purges older versions of tables its request reached before.** The runbook says running
   the same request again clears residue. After a completed run the per-source file may be gone and
   the current table clean, so a re-run reading a directory by its scope also takes it when a table
   the request's records name has an older version its purge should have taken. Those are the
   versions `caselist status` counts: older than the run's completion less 15 minutes, and not the
   version the run left clean. It never touches other directories' history.
3. **A table of a reached directory that held no row is recorded clean** (its current version), so a
   stale version of it found later is residue, and the same request run again takes it.
4. **What is written, and how.**
   * The rewrite goes up with the everyday profile's `put_file`, as the manifests' do, so the SHA-256
     is recorded where a restore's check reads it.
   * The bucket must confirm it by `head` before any version is deleted.
   * Deletes use the takedown profile, and a version still listed afterwards stops the run
     `INCOMPLETE` (`AGGREGATES_LEFT`).
5. **Retirement tags.**
   * A directory is retired when any of its current aggregates carries the tag, because retiring
     tags one object at a time.
   * Tags that cannot be read (`StoreAccessDenied`) leave the directory taken as live and rewritten,
     and the plan says so.
   * A directory with no current aggregate has its versions purged.
6. **Nothing written before the checks.** Every rewrite is downloaded, rewritten and checked into a
   temporary directory before the suppression entries are appended. An `UNREADABLE` line in the plan,
   one found then, or a table whose bytes are not the ones the plan counted stops the run `INCOMPLETE`
   with nothing written but the log entry, its scope and its aggregate record.
7. **The run lock.** `caselist remove --execute` takes the bucket's run lock in
   `caselist_remove.remove` (`run_holding_the_bucket_lock(cli, "caselist remove", ...)`, which
   enters `BucketWriteGuard.held`). It holds it across `plan_and_execute`, the plan, the staging and
   every write. The weekly run's parse publish takes the same lock, so they never write a table at
   once. In local mode the guard takes no lease (ruling 3(a) of 2026-10-24); a table changed between
   the plan and the staging is refused by its digest, as Decision 6 says.

8. **Test data.** Every school, team code and file in the new tests is invented (`Alpha School`/`AlOn`,
   `Bravo School`/`BrTw`, synthetic PDF bytes), as the existing fixtures' are. The parsed stores are
   planted from the store's own record models; no real disclosure is in any of them.

## Operator follow-ups

Nothing is to be run until this branch has merged into `dev`, a dev build carrying it is installed,
and the PM has said `--execute` may run (the ruling: *No --execute outside tests until the PM's
word*). Then the operator reruns the signed-in journey, `docs/runbooks/evidence-search.md`, "The
signed-in journey on dev". That is J2 to J6 as written, from a fresh copy with the seed published
again; then J7 as rewritten here; then J8, J9 and J10. Expected runtime is J2's several minutes and
J5's few, the rest seconds. J7's two blocks, as the runbook now has them:

```bash
REMOVE_SHA=b3afe1c4f57df962b3200ec08b3d1efe023c0243a9b31154f787348864036fa8
PULL=$(pgrep -fl 'debate-research( --json)? caselist pull')
OVERRIDES=$(env | grep '^DEBATE_' | cut -d= -f1 | tr '\n' ' ')
if [[ -n "$PULL" || -n "$OVERRIDES" || "$(date +%u)" = 3 ]]; then
  echo "STOP: a pull is running, a DEBATE_ override is set, or it is Wednesday"
else
  aws sso login --profile debate-dev-evidence
  cd "$WT" && DEBATE_ENV=dev uv run debate-research caselist remove --source "$REMOVE_SHA" --request RM-2026-91 --reason POLICY
fi
```

The dry run is correct only if:

* *WILL BE REMOVED* lists the one file, its object under `raw/caselist/testcl26/` and its parsed
  file under `parsed/testcl26/2026.10.27-docx-7/`.
* *AGGREGATES REWRITTEN WITHOUT THE REMOVED ROWS* lists exactly those three tables, all `bucket`:
  `index.jsonl` *-1 of 3*, `failures.jsonl` *holds none*, `occurrences.jsonl` *-2 of 4*. Those counts
  are worked out by hand from the seed: three files, and four occurrence rows, two of them the
  removed file's.
* There is no retired-directories section and no *UNREADABLE* line.

The operator writes down each table's bytes; the PM records them, as the ruling's (b) asks. Then, in
the same window:

```bash
REMOVE_SHA=b3afe1c4f57df962b3200ec08b3d1efe023c0243a9b31154f787348864036fa8
PULL=$(pgrep -fl 'debate-research( --json)? caselist pull')
OVERRIDES=$(env | grep '^DEBATE_' | cut -d= -f1 | tr '\n' ' ')
if [[ -n "$PULL" || -n "$OVERRIDES" || "$(date +%u)" = 3 ]]; then
  echo "STOP: a pull is running, a DEBATE_ override is set, or it is Wednesday"
else
  aws sso login --profile debate-dev-evidence
  aws sso login --profile debate-dev-evidence-removal
  cd "$WT" && DEBATE_ENV=dev DEBATE_REMOVAL_PROFILE=debate-dev-evidence-removal uv run debate-research caselist remove --source "$REMOVE_SHA" --request RM-2026-91 --reason POLICY --execute
fi
```

Success looks like `DONE in dev` and *Parsed store: 2 aggregate(s) rewritten without 3 row(s); 0 in
retired directories deleted. Nothing is to be rebuilt.* Then P1b's read-only check prints `0` for
`parsed/testcl26/2026.10.27-docx-7/occurrences.jsonl`, and J8 passes.

## Follow-up work

1. **The parse owed a removal clears** (`removal_service._clear_parses_owed`, `v1-e40-t08`). It was
   cleared because the runbook's rebuild after a removal parsed whatever was unparsed. No rebuild
   follows a removal now, so a snapshot that was owed a parse when a removal rewrote its manifest may
   wait for the caselist's next import. Unchanged here, and its docstring says so. For the PM: keep
   the entry, or keep clearing it.
2. **Other removals in dev's log.** Removals made by older builds (`RM-2026-90` among them) have no
   aggregate record, so status compares them by the old rule. Nothing changes for them. A re-run of
   one by this build reads its scope's caselists and takes any directory still holding a row.
3. **An installed build older than this one** reads `removal-aggregates.jsonl` as an unknown file and
   ignores it (checked against `v1.1.0-dev.342`), so its `caselist status` counts a newer removal's
   rewrites as residue. The runbooks say status runs from a build carrying this task. Both the
   weekly agent and prod need such a build before their next removal, which promotion item 8 now
   says.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-05

**Notes:**

The defect J7 found is fixed at its root: a removal now reaches a version directory only by the witness
that it holds the file (a per-source parsed file, in any version), and it repairs what it reaches in
place instead of leaving every caselist waiting on a rebuild the cloud can no longer do from this Mac.

1. **ac1 passes.** The proposal was committed before any code (`6577c13`), and the ruling is recorded
   ahead of the first code commit.
2. **ac2 passes.** All eight cases the ruling listed are tested on moto with synthetic stores, among
   them a backfile, a retired directory deleted rather than rewritten, a stopped run found again by its
   per-source file, both withdrawal kinds and an unreadable line stopping the run with nothing written.
   Red was 25 failed and 1 passed against the refuse-nothing skeleton. The one pass is Q3's
   cluster-id test, which a drop-nothing rule cannot fail, and the report says so. All 21 mutants are
   caught, and the 6 that first survived each got the test that was missing. The one masked by a
   fallback (the byte comparison behind the digest check) is the kind that matters most here.
3. **The execution order is right.** Each directory's aggregates are handled before its per-source file
   is deleted, so the witness outlives the rows. Every rewrite is staged and checked before the first
   write; a table changed since the plan stops the run. In bucket mode the lock is held from the plan to
   the last write, which keeps the weekly parse publish out.
4. **Deviations accepted.** The smoke pins and the removal fixture follow the ruling's (b). The existing
   tests whose expectations changed now pin the ruled behaviour, and `test_residue_clearing_gaps.py`
   pins a stronger one. `parsed-store-publish-only.md` is left as written because it is still true of an
   older build's removal. The estimate is already 8h in the PM's batch.
5. **Decisions accepted.** 2, a re-run purging the older versions of tables its request reached before,
   is bounded by the residue rule's own window (older than the completion less 15 minutes, never the
   clean version) and touches no other directory's history. 3, an empty table recorded clean, closes
   the gap a later stale version would otherwise leave. 5, unreadable tags taken as live, is the safe way
   round, and the plan says so.
6. **Follow-up 1, the parse owed a removal clears: keep the entry.** The clearing existed only because
   the runbook's rebuild parsed whatever was unparsed, and nothing follows a removal now. The next
   parse stage reads the manifests as the removal rewrote them, so keeping the entry cannot bring a
   removed file back. The PM files it in the next batch (E30, p2), with this ruling. Its proposal
   first says whether the next run's parse picks those sources up anyway; if it does, the task is
   a docstring change and a test. It does not hold up J7, because the seed's caselist owes no parse.
7. **Follow-ups 2 and 3 accepted.** Older removals keep the old residue rule. The docx-9 run image is
   built from a `dev` that carries this task, so the weekly agent carries it before its next removal,
   and promotion item 8 already says prod's removal runs from such a build.
8. **ac3 is the operator's, and here is the PM's word on `--execute`.** It runs in dev only, for
   RM-2026-91 and the seed's one file, from `$WT` pulled to a `dev` that carries this merge. It runs
   only when the dry run reads as the Operator follow-ups say: one file under WILL BE REMOVED; exactly
   the three `bucket` tables of `parsed/testcl26/2026.10.27-docx-7/` (`-1 of 3`, `holds none`,
   `-2 of 4`); no retired-directories section; and no `UNREADABLE` line. Anything else stops the
   journey and comes to the PM. No removal runs in prod under this word. The operator sends each table's
   bytes from the dry run, and the PM records them, ac3 and the J4–J10 rerun in a batch. The PM's batch
   also amends ac3's wording: no rebuild follows a removal.
9. **Merge:** `scripts/task pr --partial` once `ci` is green. The Goal stays `InProgress` until ac3 is
   recorded.

## Operator records (recorded by the PM, 2026-11-06)

Added by the PM. Nothing above is changed, and this section is not a review.

| Criterion | Was | Now | Record |
|---|---|---|---|
| ac3: the journey's J4 to J9 in dev with J7's --execute (operator) | NOT RUN | J4 to J8 PASS; J9 recorded next | 2026-11-06/07, from $WT at a2324c2 (dev.380). J2 restored a docx-7 copy (18,345 objects, 500.9 s); J3 imported the seed (3 first seen); J4 published nothing new (the seed's objects were in the bucket since 2026-11-05) and parsed it (3 sources, 4 cards, 2 clusters); J5 built ab5dd9d3ac95d07b from dev's four stores and testcl26, checked OK, published; J6 passed every step. J7's dry run planned exactly the one file and the three bucket tables of parsed/testcl26/2026.10.27-docx-7/: index.jsonl -1 of 3 (1,158 bytes), failures.jsonl holds none (0 bytes), occurrences.jsonl -2 of 4 (2,728 bytes). --execute: DONE, 14 bucket object versions deleted, 1 manifest rewritten, 2 aggregates rewritten without 3 rows, nothing rebuilt; P1b printed 0 for both tables; J8 passed (the removed card's page refuses, it is not in the results) |

J9 (the seed out of dev's index) and J10 ran the same night; the PM records them and closes the Goal in the next batch. Promotion item 9 no longer waits on this task's code.

## Operator records (recorded by the PM, 2026-11-07)

Added by the PM. Nothing above is changed, and this section is not a review.

| Criterion | Was | Now | Record |
|---|---|---|---|
| ac3, the rest: J9 and J10 | J4 to J8 PASS; J9 recorded next | PASS | 2026-11-07. J9 rebuilt dev's index from the copy without testcl26: e95f10c1a8fda754, the index dev held before the journey, its stores equal to J5's before-manifest; published past the shrink guard with --allow-shrink, which named testcl26 alone (0 documents against 2). J10 deleted the copy and the seed, and the leftover search read 0 restored copies |

Every criterion passes, so the Goal is `Succeeded`.

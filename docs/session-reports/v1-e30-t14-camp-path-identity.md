# Session report: v1-e30-t14-camp-path-identity

| | |
|---|---|
| Task | `v1-e30-t14-camp-path-identity` — A camp file is identified by its upstream record, and a camp path can be withdrawn on its own |
| Spec | [`plan_specs/v1/e30-caselist-ingestion/t14-camp-path-identity.yaml`](../../plan_specs/v1/e30-caselist-ingestion/t14-camp-path-identity.yaml) |
| Epic / release | `v1-e30-caselist-ingestion` / `v1.1` |
| Branch | `task/v1-e30-t14-camp-path-identity` |
| Session status | COMPLETE. The Goal is left `InProgress`: ac1's real-environment half is the operator's (Summary, Operator follow-ups) |

## Summary

Every camp-file row that `caselist pull` writes into a release manifest now carries `openev_id`
and `upstream_path_sha256`. The second is the SHA-256 of the file's upstream path, the same digest
the delivery record keeps, never the path itself. A removal plan matches a camp file's later upload
by what the rows say as well as by this machine's delivery record. Prod's plan, which has no
delivery record, now matches as dev's does, and no longer says *matched by file name alone* for
rows that carry the identity.

A camp file's later upload that another release or a team also holds is now withdrawn from its camp
path, as `v1-e30-t11` withdraws a caselist path. Its row in that release goes, along with that
release's camp-file record and its year's `raw/openev/<year>/` copy, unless something else in that
release or year holds the bytes. One suppression entry stops the file at
`openev/<release>/<row path>`, and `withdrawals.jsonl` records the withdrawal under `openev`. The
importer, the pull, the publisher, status and the removal's sweep all honour that entry.

**Three things to look at first.**

1. **The phase is `InProgress`, because of ac1's "in both environments".** The code half passes,
   shown failing first, through the services and through the commands. But the rows already in dev
   and prod were written before this task, and code alone cannot change them. They gain the
   identity when the operator re-derives the release in dev's data directory and publishes it to
   both buckets: Operator follow-up 1, which the runbook also describes. Until then a prod plan over
   them still says *matched by file name alone*, and the runbook now says to stop when it does. If
   you accept the code half and the procedure, the phase is one command away; otherwise this is a
   `--partial` merge with that follow-up open.
2. **Compatibility (ac3) holds without a new record.** No reader in either older build refuses an
   unknown key in a manifest row. Each one either ignores it or keeps it byte for byte, so the
   identity is two additive keys on the row itself. Each older build's own code, exported with
   `git archive`, ran over this build's manifest: it published it, pulled into it, re-derived it,
   removed from it, and reported status in sync. This build's code ran over theirs. The table is
   under "The compatibility finding".
3. **I read the forbidden item "A camp title, school or file name in a manifest row or a plan
   line" as applying to what this task adds (Deviation 1).** Taken literally it also forbids
   fields every manifest row and many plan lines already carry, which older builds read. Counted
   from the code below.

33 mutants were run. 23 were caught on the first run, 8 only after the test each showed was
missing, one check was deleted as redundant, and one mutant is equivalent.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `camp-identity`: Camp files carry their upstream identity | Done | The manifest fields, the plan's matching, the withdrawal, compatibility and the runbook. Its criterion passes: 411 tests. |

## Acceptance criteria

Commit ids are on the branch after `scripts/task sync v1-e30-t14-camp-path-identity`, onto
`origin/dev` at `e52d014`. `dev` had moved by one generated-files refresh that touches only
`ROADMAP.md`, the rebase was clean, and the branch is not on origin, so nothing was pushed. The red
runs were made before the sync, at the start commit's source, which the rebase did not change.
"The start commit" is `53a8743` (now `e6af2e9`), whose source is `7de7191`'s. "The installed
build" is `v0.1.0-dev.122` (`d87febd`), the build the weekly agent is installed from. Neither older
build was opened or run as installed: each source was exported with `git archive` into the
scratchpad.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1**: a camp file's manifest row carries its upstream identity in both environments, and the prod removal plan matches a later upload by it; the plan no longer says it matched by file name alone; shown failing first | **Code: PASS, shown failing first. Real environments: NOT RUN** (Operator follow-up 1) | Fixture: 512 pulled, then uploaded again at its path as 640, beside 700, another camp's file of the same name. **Red**, against the start commit's source: `test_camp_rows_carry_upstream_identity.py` → every row `(None, None)` where `(512, '9039…')` etc. were expected; prod's plan `[('55f3…', (700,), ROW_NAME), ('cd2a…', (640,), ROW_NAME)]` where only `('cd2a…', (640,), UPSTREAM_PATH_DIGEST)` was expected; the prod removal took the other camp's row too, `{}` where `{'openev-700-…': '55f3…'}` was expected. Through the command, `tests/smoke/test_caselist_camp_identity_smoke.py` against the same source: **4 failed**, with prod's dry run printing `as openev-700 (matched by file name alone: no delivery record here knows both ids, so check it): removed everywhere`. **Green**: the core module `10 passed`, the smoke module `4 passed`. Prod is simulated as a data directory of its own, empty, with a bucket of its own, published from dev's data directory with `caselist publish --confirm-prod` exactly as the backfill runbook publishes prod. Prod's dry run then says `(matched by upstream path: both ids were uploaded at one upstream path): removed everywhere`, contains no `file name alone`, and does not name 700. The re-derive that gives older rows their identity, with status naming the manifest mismatch and the publish clearing it, is tested in core and through the commands. Those tests use what this task added, so they could not run red. |
| **ac2**: a removal can withdraw one camp path, leaving the file for the release that still holds it, with the suppression entry scoped as `v1-e30-t11`'s withdrawal of a caselist path is; by test | PASS | `test_removal_withdraws_one_camp_path.py`, 16 tests. Fixture: 640's bytes also released in `2027-policy` as 800. **Red** against the start commit's source, in the same run as ac1: **13 failed, 3 passed** across the two modules. Every failure is an assertion, or `DID NOT RAISE` in the stopped-run test, because the start commit plans no record for 640 to stop on. The three that passed hold on the start commit as well: a guard that the identity names no title, `--only-named`, and the import control. **Green**: `2026-policy` loses both rows on both sides and `2027-policy` keeps 800's byte for byte. The camp-file records go from `[(2026, POLICY), (2027, POLICY)]` to `[(2027, POLICY)]`. The blob and the source record stay. `raw/openev/2026/…`, given a second version first, has none left; `raw/openev/2027/…` keeps its one. **The scope:** both copies of the list hold `{(512, None), (640, sha256("openev/2026-policy/openev-640-…"))}`, which is `disclosure_digest("openev", "<release>/<row path>")`, the caselist form with the release in the path. Re-importing 640's download into `2026-policy` gives `SUPPRESSED 1` and no row; the same bytes at 800's row in `2027-policy` stay `UNCHANGED`. The next pull reports 640 as `skipped_as_removed` and fetches nothing. The team-holds case is covered too. |
| PM brief 4: a camp withdrawal records itself in `withdrawals.jsonl`, consistent with `v1-e30-t16`'s joins; tested | PASS | One line, `{"caselist":"openev","disclosure":<the camp path's digest>,"reason":"REQUESTED_BY_CAMP","request_id":"RM-2026-01",…}`, on this machine and in the bucket. `caselist_withdrawn_from` gives `"openev"` for the scoped entry, and `caselists_withdrawn_by` gives `{640: ("openev",)}` for the log entry, with t16's joins unchanged. Through the command, the *WITHDRAWALS* line is checked field by field. |
| **ac3**: manifests written by this build are read by the build at the start commit, and the reverse | PASS | "The compatibility finding" below. Each older build's own code ran over this build's manifest and over this build's camp-withdrawal records, and this build's code ran over each older build's manifest: `test_camp_manifest_is_read_by_every_build.py`, 15 tests, over files each build's own pull wrote (`stored_camp_manifests/`). |
| **ac4**: the removal runbook's step 7 drops the by-hand comparison of a camp file's later uploads | PASS | Step 7 no longer says to compare sha256 values with dev's. It says prod's lines read *matched by upstream path*, and to stop if one says *matched by file name alone*, which points to the new section *Camp rows that carry no upstream identity*. t15's section *When `caselist status` reports removal residue* is unchanged (`git diff` shows no line of it). `uv run scripts/check_command_blocks.py --base origin/dev` → `OK: no '#' comments in 255 shell code blocks`. `uv run scripts/check_links.py` → `OK: 1530 relative links and anchors in 218 Markdown files`. |
| Node `camp-identity`: `uv run pytest packages/debate_core/tests/application -k "removal or camp"` | PASS | `411 passed in 20.75s` on the synced branch (`f626f2a`). |

### Red, then green

The red runs used the worktree at the start commit with only the new test files added, which is
the start commit's source (commit `6f4a18f` adds tests only). Load average 13.7.

```bash
uv run --frozen pytest packages/debate_core/tests/application/caselist/test_camp_rows_carry_upstream_identity.py packages/debate_core/tests/application/caselist/test_removal_withdraws_one_camp_path.py -p no:randomly --no-cov -q -n 4 -rA
```

```text
E       {'openev-512-TSF-Estuary_Solvency_Advocate.docx': (None, None)} != {'openev-512-TSF-Estuary_Solvency_Advocate.docx': (512, '9039ceb2…')}
E       At index 0 diff: ('55f32b57…', (700,), <SamePathEvidence.ROW_NAME: 'row_name'>) != ('cd2a7acd…', (640,), <SamePathEvidence.UPSTREAM_PATH_DIGEST: 'upstream_path_digest'>)
E       AssertionError: 512 removed, and 640's row withdrawn, on both sides
E       assert <LaterUploadOutcome.KEPT_SHARED: 'kept_shared'> is <LaterUploadOutcome.WITHDRAWN_FROM_THE_PATH: 'withdrawn_from_the_path'>
E       assert <SelectionDecision.ALREADY_IMPORTED: 'already_imported'> is <SelectionDecision.SKIPPED_AS_REMOVED: 'skipped_as_removed'>
E       assert (0, ['openev-...vocate.docx']) == (1, [])
13 failed, 3 passed in 23.56s
```

The smoke module ran against the exported start-commit source, put first on `PYTHONPATH`. `BUILD`
is the scratch directory holding it:

```bash
PYTHONPATH="${BUILD}/packages/debate_core/src:${BUILD}/packages/debate_cli/src" uv run --frozen pytest tests/smoke/test_caselist_camp_identity_smoke.py -p no:randomly --no-cov -q -n 0
```

```text
E       {'openev-640-TSF-Estuary_Solvency_Advocate.docx': (None, None)} != {'openev-640-TSF-Estuary_Solvency_Advocate.docx': (640, 'd1b8ac53…')}
E       AssertionError: assert '     later upload of sha256 2b912c191a8a in openev 2026-policy as openev-640 (matched by upstream path: …): removed everywhere' in 'DRY RUN: nothing was changed. prod …
E       AssertionError: assert '     withdraw openev  2026-policy openev-640' in ['     later upload of … (the delivery record puts both ids at o…: KEPT: another holder has it too, and one camp path of a file cannot be w…
E       KeyError: 'identities_added'
4 failed in 23.89s
```

That prod dry run, read in full with `-vv`, printed
`as openev-700 (matched by file name alone: no delivery record here knows both ids, so check it): removed everywhere`:
the other camp's file of the same name, planned for removal.

Two more tests were red before the code they test. The re-run of a removal after an older build
re-records the row failed on `assert None is not None`, because the re-run planned nothing for 640.
The inbox test failed on a missing `('openev-640-…', 'delete', 'its camp path is withdrawn: …')`.

### The compatibility finding

**How each build reads a manifest row.** I listed every reader of a release-manifest row in both
older builds' source. They are the same set in both, and none validates a row against a model that
forbids extra keys:

| Reader | Where | An unknown key is |
|---|---|---|
| The import's merge, `read_recorded_release` (`caselist import-openev` and the pull) | `openev_manifest.py` | **kept**: the row is held as a mapping, and an unchanged path's row is written back byte for byte. It refuses only a line that is not JSON, not an object, not `schema_version` 1, or not a member with a path |
| The metadata re-derive, `rederive_release` | `openev_metadata_reimport.py` | **kept**: `row.update(…)` of four fields |
| The removal plan and its rewrite (`_copy`, `_rewritten`) | `removal_plan.py` | **kept**: kept rows are written as the lines they were read from |
| Publish and status (`sources_in_manifest`, `stored_rows_in_manifest`) | `publish_plan.py` | **ignored**: reads `kind`, `classification`, `sha256`, `byte_size`, `path` |
| The pull's already-imported check and summary read | `caselist_sync.py` | **ignored** |
| The parser's source list | `parse_sources.py` | **ignored** |
| The removal's sweep of noncurrent versions | `removal_service.py` | **ignored** |

None refuses. So the identity goes on the row as two additive keys, as `v1-e30-t08` added
`first_seen` to a summary. No record beside the manifest is needed.

**An older build's own code over this build's manifest.**
`check_an_older_build_reads_this_builds_camp_manifests.py` runs against an older build's source
(`stored_camp_manifests/README.md` has the commands). It carries out the history with that source,
puts this build's manifest in place, and does everything that build does with one. Against
`v0.1.0-dev.122` and against the start commit it printed the same lines but for the source's name:

```text
reader: the debate_core source at dev122
placed: this build's manifest; its rows are this source's own but for the two keys: True
publish: succeeded True; status in sync: True
next pull: openev-640 already_imported, openev-700 already_imported, openev-900 download
its merge: this build's rows kept byte for byte (16 row(s)); the new row True, with the keys False
metadata re-import: this build's rows kept the two keys as written: True; the same as its re-derive of its own manifest but for the two keys: True
removal of 512: completed True; later upload(s) openev-640; rows it kept kept byte for byte (15 row(s)); 512 and 640 gone True
publish again: succeeded True; status in sync: True
```

**An older build's own code over this build's camp-withdrawal records.** The second check puts
this build's `suppression-list.jsonl` and `withdrawals.jsonl` in place, as left after 640's camp
path was withdrawn, on this machine and in the bucket. The start commit printed:

```text
list read: 1 whole file(s) and 1 disclosure(s)
next pull: openev-640 already_imported, openev-700 already_imported
the same removal: COMPLETED; removed 2 file(s), withdrew 0
publish: succeeded True; status in sync: True
status with the residue check: completed; in sync True
the withdrawal record read by this source's own model: UnreadableAppendOnlyRecord at line 1; no command of this source reads it
the withdrawal record afterwards: this build's line kept True
```

`v0.1.0-dev.122` printed the same, with `status with the residue check: this source reads no
removal log` and `the withdrawal record: this source has no reader of it`. The camp-path entry is an
ordinary disclosure-scoped line, so every build reads the list. The `openev` line in
`withdrawals.jsonl` is refused by the start commit's `WithdrawalEntry` if it is parsed, but nothing
in that build parses it. Searching its source for `withdrawals()`, `_read_withdrawals`,
`caselist_withdrawn_from` and `caselists_withdrawn_by` finds only their definitions, and its append
reads lines without validating them. Every check ran in under 2 s.

**This build's code over theirs** (`test_camp_manifest_is_read_by_every_build.py`, each test run
over both older files). Their rows are this build's byte for byte once the two keys are removed,
and the summary is identical. This build's pull keeps their rows byte for byte and writes the keys
on the new row. Its plan matches by the delivery record where there is one, and by name with none,
as before this task. Its removal rewrites their manifest and keeps the other rows byte for byte.
Its re-derive gives all 16 rows the keys and changes no field outside them and t08's four. Publish
and status read it in sync. A last test holds the stored file of this build to what its pull
writes now.

### Mutation runs

* **The driver.** A script in the scratchpad. It refuses a dirty tree and a target that does not
  occur exactly once, restores the file with `git checkout`, and checks `git status --porcelain`
  is empty after each mutant.
* **Each run.** The task's tests and the earlier ones they touch: the three new core modules, the
  smoke module, t11's camp modules and path-version rules, the OpenEv import and re-derive, the
  pull's revision and skip modules, t16's holder module, t13's list compatibility, the inbox purge,
  status mismatch kinds, and the plan-output command tests. That is 226 tests, 230 after
  `a220e12`. Each ran with `-n auto --no-cov -p no:randomly`, under `perl -e 'alarm 118'`, with a
  new `HYPOTHESIS_STORAGE_DIRECTORY` made by `mkdtemp` and checked empty. None of these tests is a
  Hypothesis property, so the fresh database follows working agreement 8 and
  `--hypothesis-show-statistics` does not apply. Baseline `226 passed` in 17 s; runs took 17 to
  34 s.
* **What ran on which commit.** The first run of every mutant was on `8414d99`. The re-runs were on
  `a220e12`, after the tests the survivors called for.
* **One interruption.** One batch overran its alarm while W9 was running. The alarm killed the
  driver before it could restore the file, so I restored it with `git checkout` and checked the
  tree clean. That run was not counted, and W9 was run again.
* **Validity.** No mutant failed at collection. Every catch is a failing assertion, except W10's:
  the import raises `SuppressedRowRefused` and writes no manifest, which is the failure that rule
  exists to prevent.

| # | Mutation | Result | Caught by (first of the failing tests) |
|---|---|---|---|
| **The identity match** | | | |
| I1 | The plan ignores the identity the rows carry | CAUGHT, 6 failed | `test_executed_in_prod_it_leaves_the_other_camps_file_of_the_same_name` |
| I2 | No row is read as carrying an identity | CAUGHT, 6 failed | the same |
| I3 | The pull passes no upstream identity to the import | CAUGHT, 11 failed | `test_each_row_the_pull_writes_carries_its_openev_id_and_upstream_path_digest_here_and_in_dev` |
| I4 | A pulled row carries its id and not its path digest | CAUGHT, 11 failed | the same |
| I5 | A new row carries neither key | CAUGHT, 16 failed | the same |
| I6 | The re-derive ignores the delivery record | CAUGHT, 5 failed | `test_re_deriving_the_release_gives_older_rows_their_identity_and_a_publish_takes_it_to_prod` |
| I7 | The re-derive does not read the id from the row's name | CAUGHT, 5 failed | the same |
| I8 | The plan says *matched by file name alone* whatever matched | CAUGHT, 2 failed | `test_a_camp_match_by_upstream_path_says_so`, and the smoke prod dry run |
| I9 | A row's digest is not checked to be one | **SURVIVED, then CAUGHT** after a test was added | `test_a_row_whose_upstream_digest_is_not_one_carries_no_identity` |
| I10 | A row's id is not checked to be a positive integer | **SURVIVED: check deleted** | See below |
| I11 | The re-derive does not count a row it gives `null` keys | CAUGHT, 2 failed | `test_this_builds_re_derive_gives_every_row_the_keys_and_changes_nothing_else` |
| **The camp-path withdrawal's scope** | | | |
| W1 | A camp path's scope leaves out its release | CAUGHT, 4 failed | `test_the_next_pull_neither_fetches_nor_imports_it_at_that_camp_path_again` |
| W2 | No camp path is taken | CAUGHT, 21 failed | `test_the_plan_withdraws_it_from_the_camp_path_and_says_the_other_release_keeps_it` |
| W3 | The release keeps its camp-file record | CAUGHT, 6 failed | the same |
| W4 | The record goes though another row of the release holds the file | **SURVIVED, then CAUGHT** after a test was added | `test_a_camp_path_withdrawn_where_another_row_of_its_release_holds_the_file_keeps_record_and_copy` |
| W5 | The year's raw copy goes though another release of that year holds the file | **SURVIVED, then CAUGHT** by the same test | the same |
| W6 | No `raw/openev/` copy is deleted | CAUGHT, 5 failed | `test_a_later_openev_id_a_team_also_disclosed_is_withdrawn_from_its_camp_path_for_that_team` |
| W7 | `kept_in` leaves out `openev` when another release keeps the file | CAUGHT, 2 failed | the plan test, and the smoke check |
| W8 | A withdrawn camp row is matched without its release | **SURVIVED: equivalent** | See below |
| W9 | The OpenEv importer asks about the whole file only | CAUGHT, 1 failed | `test_its_download_imported_again_is_refused_at_that_camp_path_and_imports_in_the_other_release` |
| W10 | A recorded row the list stops at its camp path is carried forward | **SURVIVED, then CAUGHT** after a test was added | `test_a_row_carried_forward_at_a_withdrawn_camp_path_is_dropped_and_a_rerun_sweeps_its_old_version` |
| W11 | The pull asks about the whole file only | CAUGHT, 2 failed | `test_the_next_pull_neither_fetches_nor_imports_it_at_that_camp_path_again` |
| W12 | The publisher and status check a camp row by its file alone | **SURVIVED, then CAUGHT** after an assertion was added | `test_a_row_an_older_build_records_again_is_taken_by_running_the_same_removal_again` |
| W13 | The removal's sweep reads a camp row by its file alone | **SURVIVED, then CAUGHT** after a test was added | the carried-forward test above, at its sweep assertion |
| W14 | The withdrawn camp path's download stays in the inbox | CAUGHT, 1 failed | `test_its_download_is_taken_out_of_the_inbox_and_the_record_of_what_it_delivered_stays` |
| W15 | A re-run does not find a camp row an older build recorded again | CAUGHT, 1 failed | `test_a_row_an_older_build_records_again_is_taken_by_running_the_same_removal_again` |
| W16 | A re-run does not find a record a stopped run left | CAUGHT, 1 failed | `test_a_run_stopped_among_the_records_leaves_the_camp_file_record_and_a_rerun_takes_it` |
| W17 | A re-run finds it and does not take it | CAUGHT, 1 failed | the same |
| **The record and what is printed** | | | |
| R1 | The withdrawal record takes a caselist slug alone, as before | CAUGHT, 13 failed | `test_the_stored_withdrawal_records_attribute_the_camp_path_to_openev` |
| R2 | A camp path is taken without its release | CAUGHT, 15 failed | the plan test |
| R3 | The withdraw line names the row's file | CAUGHT, 1 failed | the smoke check |
| R4 | A withdrawn copy's record line names the camp and the title | **SURVIVED, then CAUGHT** after an assertion was added | the smoke check |
| R5 | An inbox copy is deleted by its name, whatever its bytes | **SURVIVED, then CAUGHT** after a test was added | `test_a_file_at_the_withdrawn_downloads_name_with_other_bytes_stays_in_the_inbox` |

What the survivors changed:

- **I10 was a check that decided nothing, and I deleted it** (`a220e12`). `row_upstream_identity`
  refused a `bool` or non-positive id. The id it returns is only a key into the digests by id, and
  every id it is looked up by comes from an `openev-<id>-` name, which is 1 or more. Its type check
  stays.
- **I9 found a missing test.** Without the format check, rows whose digests are all `""` would read
  as one upstream path, the other camp's file included. The new test pins that.
- **W4 and W5 found that no fixture had another row of the same release holding the withdrawn
  bytes.** One camp-file record and one `raw/openev/2026/` copy then serve both rows, and must
  stay. The new test has 701, another camp's file in `2026-policy` with 640's bytes.
- **W10 and W13 found a case nothing exercised.** An older build records the withdrawn row again
  and publishes it. This build's next import of the release must then drop the row, not refuse to
  write the manifest. The bucket is left with a noncurrent version naming the row, and the same
  removal run again must sweep it. The new test does both.
- **W12 and R4 each needed one more assertion.** Status names the re-recorded row as a suppressed
  row; the record line of a withdrawn copy reads `the camp-file record of the withdrawn copy`.
- **R5 found a guard with no test.** The inbox step takes a withdrawn download by its name *and*
  its bytes, so a file of the same name and other bytes stays.

**W8 is equivalent.** `_dropped` checks a row against the plan's `withdrawn` set and then against
the list as it will read. For every path a withdrawal takes, the plan appends the `(sha256,
disclosure)` entry unless the list already holds it, so the list as it will read always stops the
row. With the mutant, the withdrawn-set check misses the camp row and the list check drops it
anyway. The same holds for caselist rows since `v1-e30-t11`; I left that code as it is.

### Checks CI runs

On the synced branch at `f626f2a`. The load average was checked before each part.

| Command | Result |
|---|---|
| `uv run --frozen pytest -n auto -m "not slow and not live" --part 1/4` | `1737 passed in 38.79s` (load 4.9) |
| `… --part 2/4` | `1750 passed, 1 xfailed in 38.91s` (load 11.0). The xfail is `v1-e31-t12`'s labelled small-print cite line |
| `… --part 3/4` | `1751 passed, 1 skipped, 1 warning in 36.11s` (load 17.0). The skip is the parser eval waiting on human corrections; the warning is `pytest_socket`'s, from the smoke harness test that tries the network on purpose |
| `… --part 4/4` | `1747 passed, 1 xfailed in 37.78s` (load 16.7), the same xfail |
| `uv run --frozen ruff format --check .` / `ruff check .` | `674 files already formatted` / `All checks passed!` |
| `uv run --frozen pyright` | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen lint-imports` | `Contracts: 12 kept, 0 broken.` |
| `uv run scripts/check_command_blocks.py --base origin/dev` | `OK: no '#' comments in 255 shell code blocks in 117 Markdown files` |
| `uv run scripts/check_thin_handlers.py` | `OK: 21 CLI command and API route handlers within 25 statements` |
| `uv run scripts/check_links.py` | `OK: 1530 relative links and anchors in 218 Markdown files` |
| `uv run scripts/validate_specs.py` | `OK: 348 files, 38 epics, 290 tasks, 20 releases` |

That is 6,985 passed, 1 skipped and 2 xfailed in all. The last commit, `73d3e28`, adds one test,
which passes: `uv run --frozen pytest packages/debate_core/tests/application/caselist/test_removal_withdraws_one_camp_path.py` → `16 passed`.

## Files changed

- **`debate_core.application`**
  - `caselist/openev_manifest.py`: `openev_id` and `upstream_path_sha256` on every member row
    (`OpenEvUpstream`, `upstream_fields`, `row_upstream_identity`). The merge drops a recorded row
    the list stops at its camp path, and renders under the camp scope.
  - `caselist/openev_import_service.py`: `import_release(upstream=…)`, and the pipeline asked under
    the release's camp scope. `reimport_metadata(upstream_paths=…)`.
  - `caselist/openev_metadata_reimport.py`: the re-derive writes the two keys on every row, from
    the row's name and this machine's delivery record, and counts them (`identities_added`).
  - `caselist/removal_plan.py`: the digests by id from the rows and the record. A shared camp later
    upload is `WITHDRAW`n from its camp path (`taken_path`), with its release's record and its
    year's raw copy where nothing else holds them. A re-run finds a record a stopped run left, and a
    row an older build recorded again. The withdrawn download goes to the inbox step.
  - `caselist/removal_service.py`: the sweep reads a camp row at its camp path.
  - `caselist/publish_plan.py`: `suppressed_rows` checks a camp row at its camp path, so status and
    the publisher do.
  - `caselist/inbox_purge.py`: `THE_COPY_IS_WITHDRAWN`; a withdrawn camp path's download is deleted
    by its name and bytes.
  - `caselist_sync.py`: the pull passes the upstream identity to the import; an id whose bytes the
    list stops at its row path is `SKIPPED_AS_REMOVED`; `OpenEvDeliveries.upstream_paths()`.
  - `ports/suppression.py`: `camp_path_scope`, `camp_path_disclosure`; `WithdrawalEntry.caselist`
    takes `openev`; the module docstring's scopes.
  - `ports/caselist_source.py`: `openev_id_of_inbox_name` and the prefix moved here from the sync,
    beside `openev_inbox_name`, so the manifest module can read an id without importing the sync.
- **`debate_cli`**: `commands/caselist_remove.py` (the matching line's wording, a withdrawn camp
  path as `<release> openev-<id>`, its record line without camp or title); `commands/caselist.py`
  and `container.py` (the re-derive reads the delivery record and reports `identities_added`).
- **Tests**
  - New: `test_camp_rows_carry_upstream_identity.py` (10), `test_removal_withdraws_one_camp_path.py`
    (16), `test_camp_manifest_is_read_by_every_build.py` (15), and
    `tests/smoke/test_caselist_camp_identity_smoke.py` (4, `in_process`), with its README row.
  - The compatibility files: `camp_manifest_scenario.py`, `write_stored_camp_manifests.py` and
    `check_an_older_build_reads_this_builds_camp_manifests.py` (run by path, never collected), and
    `stored_camp_manifests/` with its README.
  - Changed: three of t11's tests and two of its command-output strings, and t04's row-layout test
    (Deviation 2).
- **Docs**: `docs/runbooks/caselist-removal.md`. Step 4's camp later uploads, step 7, step 8, a new
  section *Camp rows that carry no upstream identity*, and the references. t15's residue section is
  unchanged.
- **Spec**: none beyond the phase the task started with.

## Deviations from the spec

1. **The forbidden item "A camp title, school or file name in a manifest row or a plan line" is
   applied to what this task adds.** Counted from the code, before this task:
   - every release-manifest row carries `camp`, `lab`, `file_title` and `path`, and `path` is the
     file name;
   - the plan's text names schools, team codes and paths (`record` and `withdraw` lines of a
     caselist file), and a removed camp file's camp and title (`record openev 2026-policy TSF:
     Estuary Solvency Advocate`).

   Taking those out of the rows is impossible under the other forbidden item. The older builds read
   them: the re-derive reads `row["camp"]` and `row["file_title"]`, and the parser reads `camp`.
   The data-use policy also names the manifests as a place this information may live. The plan's
   text is the operator's own terminal, as `v1-e30-t11`'s ruling put it. So:
   - the identity is an id and a digest, never the upstream path;
   - every plan line this task adds or changes names a release and an OpenEv id only. That is the
     `withdraw openev 2026-policy openev-640` line, the `record` line of a withdrawn copy, and the
     matching line;
   - the suppression entry, the withdrawal record and the plan's JSON carry digests and the slug.

   If you meant the literal reading for the plan text, that is a change to every existing plan line
   and needs its own task.
2. **Earlier tasks' tests changed, to the behaviour this task specifies.**
   - t11 `test_a_later_openev_id_a_team_also_disclosed_is_kept_for_that_team` and
     `…_is_listed_as_kept`: now withdrawn from the camp path. Renamed `…_is_withdrawn_from_its_camp_path_for_that_team`
     and `…_is_listed_as_withdrawn_from_its_camp_path`.
   - t11 `test_without_the_delivery_record_it_is_matched_by_name_and_the_plan_says_so`: rows now
     carry the identity, so it is split into "matched by the rows' identity" and "rows an older
     build wrote are matched by name and it says so".
   - t11's command-output test strings: the two lines whose wording changed.
   - t04 `test_every_row_has_the_caselist_row_layout_plus_the_camp_fields`: the hand-written field
     set gains the two keys, and a hand import's values are written out.
3. **ac1's "in both environments" is not met for rows already in dev and prod** (Summary point 1).
   The session cannot rewrite them: that is a re-derive in the operator's data directory and two
   publishes with the operator's profiles. Operator follow-up 1.

## Decisions and assumptions

1. **The identity is `openev_id` and `upstream_path_sha256`, two keys on every member row.** The
   digest is `sha256(OpenEvFile.path)`, the value the delivery record already keeps as
   `path_sha256`. `null` where it is not known: a hand import knows the id only from an
   `openev-<id>-` name, and never the path. A zip release's member rows carry the zip's id and
   path. The keys are additive, so `schema_version` stays 1, as for `first_seen` (`v1-e30-t08`).
2. **The plan takes the digests from the rows and from the delivery record, the rows winning.** The
   two agree by construction. The rows are what both environments read.
3. **A camp path's scope is the release and the row path,
   `disclosure_digest("openev", "<release>/<row path>")`, not the upstream path.** The row path can
   be computed in every state: an import of an inbox copy by hand, rows written before this task,
   either environment. A re-import or a re-fetch of the same download produces the same row path.
   The release is in it so that a withdrawal from one release leaves another. What it does not
   stop: the same bytes uploaded again under a new id at that upstream path. That is the hold
   (Decision 9).
4. **The withdrawal record says `openev`, and `WithdrawalEntry.caselist` accepts it.** The joins
   are t16's, unchanged, and the digest carries the release. The start commit's model would refuse
   the line, but no command of that build parses the record, and the evidence above shows both
   older builds working with it in place.
5. **What a withdrawn camp path takes:**
   - its row in that release, on both sides;
   - that release's camp-file record, unless another row of the release holds the bytes;
   - `raw/openev/<year>/`, every version, unless another release of that year holds them;
   - `parsed/openev/` per-source objects, unless another release keeps the file (`kept_in`
     includes `openev`);
   - the `openev` aggregates, as any withdrawal deletes the touched caselist's;
   - its download in the inbox, after its delivery is recorded.

   It does not take the blob, the source record, or the other holder's rows, records and objects.
6. **Everything that consults the list asks about a camp row at its camp path:** the OpenEv
   importer, its merge, the re-derive's render, the pull's skip, the publisher and status, and the
   removal's rewrite and sweep. Without the pull, a withdrawn id would be fetched every week for
   the importer to refuse.
7. **The same removal run again finishes a camp path's withdrawal.** It finds a release's
   camp-file record with no row of the file left, which is what a run stopped among the records
   leaves. It also finds a row an older build recorded again, because a build from before this
   task asks the list about a camp file's whole source only. This follows `v1-e30-t11` Decision 8
   and `v1-e30-t13` Decision 7.
8. **Older builds do not apply a camp-path withdrawal.** That was the cost of `v1-e30-t13`'s
   record too. The weekly agent runs `v0.1.0-dev.122`, so until it runs a build with this task, its
   pull may fetch a withdrawn id again and record its row, and its new rows carry no identity. The
   runbook says to run the same removal again after each pull, and to re-derive before a removal
   of a camp file pulled since. Dev has had one synthetic removal and prod none, so nothing is
   exposed meanwhile.
9. **The PM's question: should a camp path hold later uploads?** Yes, and for the only case this
   task creates, it already does. A camp path is withdrawn only as a later upload of a file removed
   whole, and that file's upstream path is the same. The pull's hold (`v1-e34-t14`) holds a new id
   at the upstream path of a removed file.
   `test_a_new_id_at_the_withdrawn_camp_path_is_held_by_the_pulls_hold_on_the_removed_files_path`
   pins it: 641, uploaded at that path after the removal, is `same_path_as_a_removed_file` and is
   not fetched. That test passes on the start commit too; it pins existing behaviour. What is not
   held is Follow-up 2.
10. **The matching line's wording.** *Matched by upstream path: both ids were uploaded at one
    upstream path* when the rows or the record agree. *Matched by file name alone: no row and no
    delivery record here knows both ids' upstream path, so check it* otherwise. The JSON's
    `same_path_by` values are unchanged.
11. **`identities_added` counts every row whose keys the re-derive wrote or changed**, `null`
    included, so on a release from before this task it is every member row. I first counted only
    rows whose value changed; I11 shows why it is counted this way.
12. **Prod in the tests is a data directory of its own and a bucket of its own,** published from
    dev's data directory with the same publish the backfill runbook uses for prod.
13. **No AWS call and nothing of the operator's touched.** The only network calls were
    `git fetch origin dev` and the sync's own fetch. Every bucket here is moto's. The older builds
    were exported with `git archive` and never installed.

## Operator follow-ups

1. **Give the rows already in dev and prod their upstream identity** (closes ac1's real-environment
   half). After this task merges. Where: a checkout of `dev` that includes this task, at the
   repository root. The dev profile's data directory is `~/.debate-research/dev`, which is where the
   pull imports and the delivery record is. Runtime: seconds for the re-derive, about a minute for
   each publish, and a few seconds for each status of `openev`. The same commands are in the
   runbook's new section *Camp rows that carry no upstream identity*. Do it for each release under
   `manifests/openev/`; today that is `2026-policy`.

   The dry run, which writes nothing:

   ```bash
   DEBATE_ENV=dev uv run debate-research caselist reimport-openev-metadata --year 2026 --event policy --dry-run
   ```

   Its caption says `N row(s) given their upstream identity`, where N is every member row of the
   release. Camps before and after should match, and titles changed should be 0. If either does
   not, stop and send me the caption: the alias table has changed since the last re-derive. Then:

   ```bash
   aws sso login --profile debate-dev-evidence
   DEBATE_ENV=dev uv run debate-research caselist reimport-openev-metadata --year 2026 --event policy
   DEBATE_ENV=dev uv run debate-research caselist status --caselist openev
   DEBATE_ENV=dev uv run debate-research caselist publish --caselist openev --snapshot 2026-policy
   DEBATE_ENV=dev uv run debate-research caselist status --caselist openev
   ```

   What you should see:
   - The first `status` exits 1 with `CASELIST_DRIFT`, naming `openev 2026-policy (manifest
     mismatch)`, with the hint *A manifest mismatch is this machine's copy rewritten since its
     last publish, by a camp metadata re-import or a removal. Run `caselist publish --caselist
     openev` to upload it.* That is the re-derive; it is expected.
   - The publish uploads the manifest and no source.
   - The second `status` exits 0.

   Then prod, from the same data directory:

   ```bash
   aws sso login --profile debate-prod-evidence
   DEBATE_ENV=prod DEBATE_STORAGE__DATA_DIR="$HOME/.debate-research/dev" uv run debate-research caselist publish --caselist openev --snapshot 2026-policy --dry-run
   DEBATE_ENV=prod DEBATE_STORAGE__DATA_DIR="$HOME/.debate-research/dev" uv run debate-research caselist publish --caselist openev --snapshot 2026-policy --confirm-prod
   DEBATE_ENV=prod DEBATE_STORAGE__DATA_DIR="$HOME/.debate-research/dev" uv run debate-research caselist status --caselist openev
   ```

   The prod dry run plans 0 source uploads and the manifest, the real run uploads the manifest, and
   `status` exits 0. Paste back the re-derive's caption and the two status results.

   **What it changes:** only `manifests/openev/2026-policy.jsonl` in dev's data directory and in
   each bucket. The previous version stays as a noncurrent version for the bucket's retention.
   Hand-imported rows carry `null` for the path digest, and that is expected: they are never a
   later upload. Rows a pull added since will carry their identity if the pull's build has this
   task. If it does not, run this follow-up again before a removal of a camp file pulled since.

## Follow-up work

1. **Prod's plan cannot match a hand-imported camp file to the id the pull later sees for it**
   (E34, low). The pull holds a hand-imported row's file by its path tail (`v1-e34-t06`). Such a
   row carries no identity, because nothing at import time knows its id or upstream path. The pull
   does know them at match time, and could record them. Today it does not matter: a hand-imported
   row has no OpenEv id, so it is never a later upload and never has one.
2. **A camp path withdrawn other than as a later upload has no hold for a new id there** (E30/E34;
   a ruling first). No path to such a withdrawal exists today: a `--source` on a shared camp file
   is `SKIP_SHARED`, and `--team` withdraws caselist paths. If one is added, the pull's hold would
   need to ask the camp-path entry. On another machine, the hold reads a delivery record that may
   not know the removed id. The rows of the removed file are gone by then, so the identity this
   task adds cannot help there.
3. **`_dropped`'s withdrawn-path check is redundant with its list check** (E30, tidy-up; your
   call). W8 shows it for camp rows, and the same argument holds for caselist rows since
   `v1-e30-t11`. Removing it would leave one rule.
4. **The data-use policy's removal records** (the PM's, with t16's Follow-up 1 at the next
   close-out). A camp path's withdrawal records `openev` beside the list. It identifies no one.
5. **Coordination.** I did not edit `tests/smoke/test_caselist_remove_smoke.py`, which
   `v1-e01-t21` is converting. Its t16 camp-file checks pass unchanged. I added one row to
   `tests/smoke/README.md`, which `v1-e01-t21` may also touch; the two rows are independent.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

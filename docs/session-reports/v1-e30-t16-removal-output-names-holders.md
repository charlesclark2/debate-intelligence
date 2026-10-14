# Session report: v1-e30-t16-removal-output-names-holders

| | |
|---|---|
| Task | `v1-e30-t16-removal-output-names-holders` — The removal plan names holders correctly in every case |
| Spec | [`plan_specs/v1/e30-caselist-ingestion/t16-removal-output-names-holders.yaml`](../../plan_specs/v1/e30-caselist-ingestion/t16-removal-output-names-holders.yaml) |
| Epic / release | `v1-e30-caselist-ingestion` / `v1.1` |
| Branch | `task/v1-e30-t16-removal-output-names-holders` |
| Session status | COMPLETE. The Goal is `Succeeded`. Read Deviation 1 before accepting that |

## Summary

A `caselist remove` plan now counts only holders other than the one removed, and a `--source` plan
never says "this team's". The three defects:

* A file only one camp file holds no longer reads "also held by 1 camp file(s)".
* A later upload the same team holds at a second path no longer reads "1 other team(s)".
* The four `--source` lines that said "this team's" now say what happens at the removed path.

A withdrawal now records which caselist it took the file from, by slug, in a new append-only record,
`withdrawals.jsonl`. It is kept beside the suppression list and the removal log, on this machine and
in the bucket. The list's reader and the log's reader both find it. 31 mutants were run and all 31
are caught: 29 on their first run, and two only after the test or the simplification each showed
was missing.

**Three things to look at first.**

1. **ac3's record is beside the log and the list, not inside them (Deviation 1).** No reader
   anywhere accepts a new field. Both older builds refuse the list and the log at an unknown key, as
   `v1-e30-t13` found. t15's removal-scope record cannot carry it either. Run against the start
   commit's own code, its log reader refuses the scope record whether the caselist is added as a
   field or as a line of its own, and its `caselist status` then fails on every run. So the
   caselist is in a file of its own, joined to each suppression entry and each log entry. Every
   older build's own code reads the list, imports, publishes and reports in sync with that file in
   place. I set the phase to `Succeeded` on that reading of ac3. If you read "in the removal log and
   in the suppression entry" literally, the phase is yours to set back.
2. **Two earlier tasks' tests changed, one assertion each (Deviations 2 and 3).**
   * t10's camp-only test asserted the count case (1) calls a defect.
   * t07's refused-append test named the suppression list as the first failing write. A withdrawing
     removal now writes its withdrawal record first, and nothing is deleted either way.
3. **Case (3) was failing, as the spec predicted (ac2).** With the same team at a second path, the
   later upload read `other_teams` 1, and with a second team beside it, 2.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `holder-wording`: Holders named correctly | Done | The three wording fixes, the attribution record and their fixtures. Its criterion passes: `252 passed`. All four Goal criteria pass. |

## Acceptance criteria

Commit ids are on the branch after `scripts/task sync`, onto `origin/dev` at `f2ba37b`. That brought
in `v1-e30-t12` and the PM's 2026-10-14 batch, and the rebase was clean. The only file both sides
touched is the removal runbook. The red runs were made before the sync, at the commits now called
`dd32e2f`, `d595651`, `1245dcc` and `ee96642`. Each of those adds tests only, so their source is the
start commit's, `686b9b1`. The branch is not on origin.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1**: each of (1) to (3) has a fixture shown failing first; the text and JSON name only holders other than the one removed; a file no other holder has says nothing of other holders | PASS | **Red first**, all on the start commit's source; see "Red, then green" below. (1): `2 failed`, with `(0, 1) == (0, 0)` for one release and `(0, 2) == (0, 1)` for two. (2): `4 failed` (hand-built plans) and the smoke walk failing on `1 of this team's path(s)`. (3): `2 failed` (ac2). Through the command, one test each: (1) `test_a_camp_file_only_one_camp_file_holds_names_no_other_holder` and `…_two_releases_hold_names_one_other_camp_file`; (3) `test_a_later_upload_the_team_also_holds_at_a_second_path_names_no_other_team`. Each asserts the numbered text line and the JSON counts, and the JSON keys are t11's fourteen. **Nothing of other holders:** the one-camp-file line has no "also held" and no "camp file(s)", with JSON `(0, 0)`. The case (3) plan has no "other team" or "another team" anywhere in its text. The bayview file's JSON is `(0, 0)`. t10's one-team test still passes. **Green:** `uv run --frozen pytest packages/debate_core/tests/application/caselist/test_removal_names_other_holders.py` → `11 passed`; the smoke file → `31 passed`. |
| **ac2**: case (3) built first as a fixture of a later upload at a second path of the same team, and its result recorded whether or not it was failing | PASS, and it was failing | First commit after the start, `dd32e2f`, before any code. Weekly window 2026-09-22 revises the Bayview negative at its own path and at the same team's `… (1).docx` path. **Result on the start commit:** the plan withdrew the revision from the removed path, kept its copy in `testcl26` and said why. Every assertion about that held. `other_teams` was **1** where the right count is **0**. With Cedar Hollow/ZaLu also holding it, it was **2** where the right count is **1**. Exact output under "Red, then green". |
| **ac3**: a withdrawal records which caselist it took the file from, by slug, in the removal log and in the suppression entry, readable by the build at the start commit | PASS, by a record beside both (Deviation 1) | **Where:** `withdrawals.jsonl`, one `WithdrawalEntry` per suppressed disclosure, beside the list and the log: `<data_dir>/suppression/` and `manifests/_suppression/`. Fields: sha256, the entry's disclosure digest, the caselist slug, the entry's `recorded_at`, reason, request id. **The suppression entry:** `caselist_withdrawn_from(entry, await listed.withdrawals())`, joined by sha256, disclosure and request. **The log entry:** `caselists_withdrawn_by(entry, await log.withdrawals())`, joined by request and sha256 from withdrawals recorded by then. **Red:** `-k Withdrawal` → `4 failed, 1 passed` (below). **Green:** `TestAWithdrawalRecordsItsCaselist` (5) and `TestTheJoins` (2). They cover: both places, written out by hand; a file kept in `testclb26` attributed to `testcl26` only; a `--team` withdrawal's two paths; no record when nothing is withdrawn; each reader's join. **No names:** each record test checks for none of the fixture's school, team, tournament, round or `.docx`. **Readable by older builds:** "The compatibility evidence" below, against the start commit and `v0.1.0-dev.122`, by each one's own code from `git archive`. |
| **ac4**: no plan line says "this team's" where the removal names no team, by a test that walks every line of a `--source` plan | PASS | Two walks, both red first. **Through the command, real planner** (`test_no_line_of_a_source_plan_says_this_team_in_the_dry_run_the_execution_or_a_rerun`): every printed line of the case (3) dry run, its `--execute` output and a re-run, confirmation to the requester included, and every string in the dry run's and the re-run's JSON. 100 or more lines; none contains "this team". **Hand-built** (`test_no_line_of_a_source_plan_or_its_execution_says_this_team`): a `--source` plan holding every kind of source. That is the named file removed, a shared file skipped, a later upload removed and one withdrawn, and a withdrawal a stopped run left, the one source that prints *SHARED, KEPT* under `--source`. Its dry run and executed text and both JSON documents are walked. The same sources under `--team` keep their wording, t17's four requester-line forms included (`test_a_team_removal_still_says_this_teams_where_a_team_asked`, and t17's five tests unchanged and passing). |
| Node `holder-wording`: `uv run pytest packages/debate_core/tests/application -k removal` | PASS | `252 passed in 17.64s` on the synced branch, load average 6. |

### Red, then green

**Case (3), ac2.** Commit `dd32e2f`, the test file only:

```bash
uv run --frozen pytest packages/debate_core/tests/application/caselist/test_removal_names_other_holders.py -p no:randomly --no-cov -q
```

```text
>       assert (revision.other_teams, revision.camp_file_holders) == (0, 0)
E       assert (1, 0) == (0, 0)
>       assert (revision.other_teams, revision.camp_file_holders) == (1, 0), "Cedar Hollow/ZaLu alone"
E       assert (2, 0) == (1, 0)
2 failed in 3.36s
```

**Case (1).** Commit `d595651`, the same file with `-k Camp`:

```text
E       assert (0, 2) == (0, 1)
E       assert (0, 1) == (0, 0)
2 failed in 3.18s
```

**ac3.** The same commit, `-k Withdrawal`: `4 failed, 1 passed`.

* Three were assertions that the record was empty, for example
  `assert {'local': [], 'bucket': []} == {'local': [{…'caselist': 'testcl26', …}]}`.
* The fourth, the two readers' joins, failed on `ImportError: cannot import name
  'caselist_withdrawn_from'`. That is not an assertion, so I do not count it as red evidence. Its
  join rules are held by `TestTheJoins` and mutants A5 to A11 below.
* The test that passed is the guard that a removal withdrawing nothing writes no record, which
  cannot fail before there is one. Mutants A1 and A12 below show the record tests bite.

**Case (2) and ac4, through the command.** Commit `1245dcc`:

```bash
uv run --frozen pytest tests/smoke/test_caselist_remove_smoke.py -p no:randomly --no-cov -q -n 4 -k "second_path or this_team or camp_file"
```

`4 failed`, one for each of the four new tests:

* the case (3) line read `… 68 bytes; also held by 1 other team(s))`;
* the one-camp-file line read `… 963 bytes; also held by 1 camp file(s))`;
* the two-release line read `… also held by 2 camp file(s))`;
* the walk failed at its first exact line, the suppression entries' count.

Every line containing "this team" that the start code printed for that `--source` plan, collected
with a temporary edit of the test that was then restored with `git checkout`:

```text
  1 whole file(s), and 1 of this team's path(s) to a shared file. Each
  - Removed from this environment: 1 file(s), and this team's copies of 0 shared file(s).
  - Suppressed, so no later archive, weekly or complete, can bring back a removed file, or this team's copy of a shared file at the path it was taken from.
```

The dry run and the `--execute` output printed all three. The re-run printed the first two, the
count reading `0 whole file(s), and 0 of this team's path(s)`. The JSON held none.

**ac4, hand-built.** Commit `ee96642`: `4 failed, 2 passed`. The two that passed are the `--team`
control and a check of the fixture itself, which assert what was already true.

**Green.** After the changes, on the synced branch: the core module `11 passed`, the CLI module
`9 passed`, the remove smoke file `31 passed`.

### The compatibility evidence (ac3)

**The scope record cannot carry the caselist.** I exported each build's source with
`git archive <commit> packages/debate_core/src packages/debate_cli/src` into the scratchpad. I then
ran `check_an_older_build_reads_this_builds_files.py` by its path with that source first on
`PYTHONPATH`, as `stored_suppression_lists/README.md` describes. Its new third check runs the
history with the source under test, then writes that source's last scope line again with one more
field, `withdrawn_from`, and then instead a line of a new kind. Each time it asks that source's log
reader and its residue status for the scopes.

```text
reader: the debate_core source at start-686b9b1
a withdrawal's caselist in the scope record, as one more field of its line: UnreadableAppendOnlyRecord at line 3
a withdrawal's caselist in the scope record, as a line of its own: UnreadableAppendOnlyRecord at line 3
so `caselist status` with the residue check fails on every run until the line is gone
```

`v0.1.0-dev.122` printed `removal scopes: this source reads no removal-scope record, so nothing
added to one is read`: it predates `v1-e30-t15`.

**Every older build reads what this build writes.** The first and fourth checks put
`written_by_this_build/` in place, regenerated with the README's own command, `withdrawals.jsonl`
included in both places. The first then runs the weekly agent's path: read the list, import next
week, publish, ask for the status. The fourth runs the source's own `caselist status` with the
residue check, the one reader of the log and the scopes:

| Source | First check | Fourth check |
|---|---|---|
| Start commit `686b9b1` | placed 10 files; `list read: 3 whole file(s) and 2 disclosure(s) suppressed`; `import of the next week: SUPPRESSED 4, completed`; `publish: succeeded True; status in sync: True` | `status with the residue check: completed; caselists checked: openev, testcl26`; `removals not checked: 0` |
| `v0.1.0-dev.122` | the same four lines, `knows of path holds: False` | `status: this source reads no removal log, so nothing beside one is read` |
| `origin/dev` `f2ba37b`, after the sync (t12's status) | the same as the start commit | the same as the start commit |

Each run took under 3 s. They were made before the sync and again after it, with the same output.
The installed agent, its data directory and the AWS config were not touched.

**Inside this build's test suite**, t13's `test_suppression_list_is_read_by_every_build.py` now
holds the following:

* The list and the log this build writes are still both older builds' files byte for byte, as
  before.
* What this build adds is three files in each place.
* The two withdrawal lines, written out by hand, are the team's two paths of the shared file in
  `testcl26`, and name no one.
* A withdrawal line is refused by both older builds' list and log schemas, which is why it is
  beside them.
* This build attributes its own entries through both readers.
* The older builds' stored records attribute nothing and invent no caselist.

The regenerated scope files differed only by the version ids moto assigns at random, which the test
masks. I restored the committed ones so the diff carries none.

### Mutation runs

31 mutants, each one textual change to committed source, in `removal_plan.py`,
`caselist_remove.py`, `removal_service.py`, `caselist/suppression.py` and `ports/suppression.py`.

* **The driver.** A script in the scratchpad. It refuses a dirty tree and a target that does not
  occur exactly once. It restores the file with `git checkout`, checks its bytes, and checks
  `git status --porcelain` is empty after every mutant.
* **Each run.** 170 or 171 tests: the new core, CLI and smoke tests, t10's and t11's plan tests,
  t13's compatibility test, the removal service tests, and the CLI plan, requester-line and
  path-hold output tests. Run with `-n auto --no-cov -p no:randomly`, each with a new, empty
  `HYPOTHESIS_STORAGE_DIRECTORY` made by `mkdtemp` and checked empty. None of these tests is a
  Hypothesis property, so that is to follow working agreement 8, and
  `--hypothesis-show-statistics` does not apply.
* **Timing.** Baseline `170 passed` in 24 s. Batches of three or four, each under
  `perl -e 'alarm 115'`, 18 to 45 s a run. Another session pushed the load average to 51 during
  batches 2 to 5.
* **Validity.** No mutant failed at collection; every catch is a failing assertion.
* **Commits.** H1 to W9 and the first W7 ran on `da8603a`; the second W7, W10, A1, A2 and the first
  A3 on `0234da9`; the second A3 and A4 to A13 on `0710fc8`.

| # | Mutation | Result | Caught by (first of the failing tests) |
|---|---|---|---|
| **Holder counting** | | | |
| H1 | `--source` counts every camp release as another holder (the old count) | CAUGHT, 10 failed | `test_a_file_two_releases_hold_counts_one_other_camp_file` |
| H2 | `--source` leaves a release out even when a team holds the file | CAUGHT, 1 failed | t10's `test_a_shared_file_named_by_source_is_skipped_without_include_shared` |
| H3 | The teams-first rule reversed | CAUGHT, 11 failed | the two-release test |
| H4 | `--team` leaves one release out | CAUGHT, 1 failed | t10's `test_the_teams_own_files_are_removed_and_the_shared_one_withdrawn` |
| H5 | "Shared" ignores camp holders | CAUGHT, 2 failed | the two-release test, core and smoke |
| H6 | A later upload's other teams keep the removed path's team (the old count) | CAUGHT, 3 failed | `test_no_other_team_holds_it_though_its_copy_in_the_caselist_stays` |
| H7 | A later upload's other teams leave out every team | CAUGHT, 3 failed | `test_another_team_at_a_live_path_is_still_counted_once` |
| H8 | `camp_file_holders` reported as every release | CAUGHT, 5 failed | the two-release test |
| **"This team's" and the other holder lines** | | | |
| W1 | Every plan names a team | CAUGHT, 5 failed | `test_a_source_removal_that_withdraws_nothing_says_only_what_it_removed` |
| W2 | No plan names a team | CAUGHT, 3 failed | `test_a_team_removal_still_says_this_teams_where_a_team_asked`, and two of t17's |
| W3 | `--source` suppression count says "of this team's path(s)" | CAUGHT, 4 failed | `test_each_line_that_said_this_team_now_says_what_a_source_removal_did` |
| W4 | `--source` confirmation says "this team's copies of 0" | CAUGHT, 2 failed | the hand-built and the smoke walks |
| W5 | `--source` suppressed line says "this team's copy" | CAUGHT, 3 failed | the same |
| W6 | Every `kept in` line says another team | CAUGHT, 2 failed | `test_a_withdrawn_copy_kept_for_another_path_does_not_claim_another_team`, and the case (3) smoke test |
| W7 | A `--team` plan's later upload is kept "for another team" | **SURVIVED, then CAUGHT** after a test change | `test_a_team_removal_still_says_this_teams_where_a_team_asked` |
| W8 | `--source` Kept line claims another team | CAUGHT, 1 failed | `test_a_withdrawn_copy_kept_for_another_path_does_not_claim_another_team` |
| W9 | `--source` confirmation drops the withdrawn copies it removed | CAUGHT, 1 failed | `test_each_line_that_said_this_team_now_says_what_a_source_removal_did` |
| W10 | `--source` *SHARED, KEPT* heading claims another team | CAUGHT, 2 failed | the same |
| **The attribution record** | | | |
| A1 | The executor appends no withdrawal | CAUGHT, 6 failed | `test_a_team_removal_records_each_path_it_withdraws_a_shared_file_from` |
| A2 | Withdrawals appended after the entries they attribute | CAUGHT, 1 failed | t07's `test_an_append_that_fails_says_nothing_was_deleted_and_names_the_first_failure` (Deviation 3) |
| A3 | Each withdrawal of a source records one of its caselists | **SURVIVED as first written, then CAUGHT** after a code change | `test_a_copy_withdrawn_from_two_caselists_records_each_its_own_caselist` |
| A4 | Only a source's first entry gets a withdrawal | CAUGHT, 3 failed | the `--team` record test |
| A5 | A suppression entry attributed by its file alone | CAUGHT, 1 failed | `test_a_suppression_entry_is_attributed_by_its_file_its_disclosure_and_its_request` |
| A6 | `attributes` ignores the disclosure | CAUGHT, 1 failed | the same |
| A7 | `attributes` ignores the request | CAUGHT, 1 failed | the same |
| A8 | A log entry names caselists withdrawn after it | CAUGHT, 1 failed | `test_a_log_entry_names_the_caselists_its_request_had_withdrawn_each_file_from_by_then` |
| A9 | A log entry names another request's withdrawals | CAUGHT, 1 failed | the same |
| A10 | A log entry names files it did not withdraw | CAUGHT, 1 failed | the same |
| A11 | The log's reader finds no withdrawal record | CAUGHT, 2 failed | t13's compatibility test and the ac3 joins test |
| A12 | The record kept beside the first copy only | CAUGHT, 5 failed | the `--team` record test |
| A13 | The plan does not print its withdrawals | CAUGHT, 1 failed | `test_the_withdrawal_record_lines_are_printed_as_appended_by_slug_and_name_no_one` |

What the run changed:

- **W7 found a missing test.** The `--team` control asserted that a team line exists, not that the
  later upload's line says *another path*. It now pins both `kept in` lines (`0234da9`).
- **A3 found redundant code.** As first written the mutation (`if entry.disclosure == digest` →
  `is not None`) survived. `withdrawals` matched every taken path with every entry, so the mutant
  only made duplicates that the record's set-union append drops. Every entry of one disclosure is
  planned from a path in `requester_paths`, so I replaced the matching with a lookup by digest,
  which fails loudly on a planner bug. I added a test of a copy withdrawn from two caselists in one
  plan and pinned the `--team` plan's count (`b2274bc`). A3 and A4 in the table are the mutants of
  the code as it is.
- **Two checks removed before the run, rather than tested:**
  - `attributes` checked the entry was a `SUPPRESS`. An un-suppress may name no disclosure and a
    withdrawal always names one, so the check could never decide anything (`a0326b7`).
  - `_teams_at` had a `known_only` branch. It mattered only for a path filed under no team's
    directories, which no fixture has (`176c6e0`; Decision 5).
- **A5 to A10 are caught only by `TestTheJoins`, which I wrote before the run.** I expected those
  mutants. I did not run them against the suite without those tests.

### Checks CI runs

On the synced branch, `f2ba37b` plus this branch, with the report and the phase uncommitted. Load
average checked before each part.

| Command | Result |
|---|---|
| `uv run --frozen pytest -n auto -m "not slow and not live" --part 1/4` | `1691 passed in 45.94s` (load 8.2) |
| `… --part 2/4` | `1703 passed, 1 xfailed in 35.73s` (load 15.3) |
| `… --part 3/4` | `1705 passed, 1 skipped, 1 warning in 34.75s` (load 16.3). The skip is the parser eval waiting on human corrections. The warning is `pytest_socket`'s, from `test_pytests_own_process_has_no_network_in_an_offline_check` |
| `… --part 4/4` | `1702 passed, 1 xfailed in 37.01s` (load 14.8). Both xfails are `v1-e31-t12`'s labelled small-print cite line |
| `uv run --frozen ruff format --check .` / `ruff check .` | `660 files already formatted` / `All checks passed!` |
| `uv run --frozen pyright` | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen lint-imports` | `Contracts: 12 kept, 0 broken.` |
| `uv run scripts/check_command_blocks.py --base origin/dev` | OK, this report included |
| `uv run scripts/check_thin_handlers.py` | `OK: 21 CLI command and API route handlers within 25 statements` |
| `uv run scripts/check_links.py` | `OK: 1523 relative links and anchors in 212 Markdown files` |
| `uv run scripts/docs_index.py --check-descriptions` | `All 34 indexed documents under docs/ have a description` |
| `uv run scripts/validate_specs.py` | `OK: 348 files, 38 epics, 290 tasks, 20 releases`, after the phase was set |

6,801 passed, 1 skipped and 2 xfailed in all.

## Files changed

- **`debate_core.application`**
  - `caselist/removal_plan.py`: the `--source` camp count and the later upload's other teams (one
    rule, `_teams_at`). `RemovalPlan.withdrawals`. Docstrings of `other_teams`,
    `camp_file_holders` and `kept_in`.
  - `ports/suppression.py`: `WithdrawalEntry`, `WITHDRAWALS_FILENAME`, `WithdrawalList`, and the
    module docstring's fifth record. `SuppressionEntry`, `RemovalLogEntry` and `RemovalScopeEntry`
    are unchanged. Two existing constants' docstrings sat in the wrong order and now each follows
    its own constant.
  - `caselist/suppression.py`: the list and the log each read `withdrawals.jsonl` beside them; the
    list appends and reconciles it; the two joins.
  - `caselist/removal_service.py`: appends the withdrawals just before the suppression entries;
    docstring.
- **`debate_core.integrations.local`**: `suppression_list.py`, its docstring's list of files only
  (Deviation 4).
- **`debate_cli`**: `commands/caselist_remove.py`. The `--source` wording of the suppression
  count, the confirmation's first and *Kept* lines, the suppressed line and the *SHARED, KEPT*
  heading. The `kept in` reason. The *WITHDRAWALS* section. The module docstring.
- **Tests**
  - `test_removal_names_other_holders.py` (11, new): the case (1) and case (3) fixtures, the
    record, and the joins.
  - `test_caselist_remove_source_plan_names_no_team.py` (9, new): the hand-built walk and wording.
  - `tests/smoke/test_caselist_remove_smoke.py`: 4 new tests, and its README row.
  - t13's compatibility test, `stored_suppression_lists/README.md` and `written_by_this_build/`
    (two new files), and `check_an_older_build_reads_this_builds_files.py` (two new checks).
  - One assertion each in t10's `test_removal_plan.py` and t07's `test_removal_service.py`
    (Deviations 2 and 3).
- **Docs**: `docs/runbooks/caselist-removal.md`, step 4 and step 8. t15's section *When `caselist
  status` reports removal residue* is unchanged.
- **Spec**: the phase.

## Deviations from the spec

1. **ac3's caselist is in a record beside the log and the list, not in either.** ac3 says "in the
   removal log and in the suppression entry". A suppression entry and a log line forbid unknown
   keys and pin `schema_version` to 1, and both older builds refuse the whole record at a line they
   cannot read (`v1-e30-t13`'s finding; its guard test still holds both byte for byte). The brief
   asked whether t15's removal scope could carry it, and the evidence above says no. So
   `withdrawals.jsonl` sits in the same place as both. Each record's own reader finds it, and each
   entry is joined to it: a suppression entry by its sha256, disclosure and request, and a log
   entry by its request and the sha256 values it lists as withdrawn. What it costs: a removal made
   by an earlier build has no withdrawal recorded, and its entries attribute to nothing. If you
   want the words of ac3 met literally, that needs a list and log format change once no machine
   runs a build from before it. That is the condition the stored files' README already names.
2. **t10's camp-only assertion changed.**
   `test_a_source_removal_of_a_file_no_team_holds_counts_no_other_team` asserted
   `camp_file_holders == 1` for a camp file no team holds. That is case (1)'s defect, pinned. It now
   asserts the file's one camp-file record is still in the plan and that no holder is another.
   t10's Decision 8 had said `camp_file_holders` is "holders, not other holders". ac1 makes it
   other holders for `--source`, as `other_teams` already was.
3. **t07's refused-append assertion changed.**
   `test_an_append_that_fails_says_nothing_was_deleted_and_names_the_first_failure` named the
   suppression list's `PutObject` as the first failure. For a team removal that withdraws a shared
   file the first write is now `withdrawals.jsonl`, so it names that. "Nothing was deleted" and
   the other assertions are unchanged. Decision 2 says why the order is this way round.
4. **One docstring outside `constraints.packages`.** `debate_core/integrations/local/suppression_list.py`
   lists the files under `<data_dir>/suppression/`. It now names `removal-scopes.jsonl`, which t15
   did not add, and `withdrawals.jsonl`. No code there changed.

## Decisions and assumptions

1. **A new record, not the scope record.** Three reasons, in order:
   - The start commit refuses the scope record at either shape, and its `caselist status --residue`
     then fails every run (evidence above).
   - The scope is written at the end of a run, after the deletions. The caselist belongs with the
     suppression entry, which is appended first, before anything is deleted.
   - A scope joins one execution's log entry. A suppression entry has no execution identity to
     join it by.
2. **The withdrawals go just before the entries they attribute.** A re-run plans no suppression
   entry that is already on the list. If the entries went first and the withdrawal append then
   failed, no later run would ever record their caselist. This way round, a record without its
   entry, from a run stopped between the two, joins nothing and harms nothing. The re-run appends
   the entry and a matching record. This is t15's order for scopes and the log, for the same
   reason.
3. **The joins.**
   - A suppression entry joins by sha256, disclosure and request. The disclosure digest already
     covers the caselist, so any record with the same pair names the same caselist.
   - A log entry joins by request and sha256, taking the withdrawals recorded no later than the
     entry. A log entry has no run identity a record could carry, since it is written last.
   - So where one request withdrew a file in two runs, each run's entry names every caselist the
     request had withdrawn it from by then. `TestTheJoins` pins exactly that.
4. **"The one removed" under `--source` is a team first.** `other_teams` already left one holding
   team out (t10). For a file no team holds, the one removed is one camp file. With a team and a
   camp file, the camp file is the other holder, as it always was. Which file is "shared" is
   unchanged: more than one holder in all.
5. **A path filed under no team's directories is no team's**, for a later upload's other teams as
   for a named file's (`_holdings`, t10). Before, a later upload counted such a path as a team. No
   fixture has one, so this is untested and was chosen to make one rule, not to change an
   observed case.
6. **What a `--source` line says instead of "this team's".**
   - The suppression count: *N path(s) a shared file is withdrawn from*.
   - The confirmation: *Removed from this environment: N file(s).* When a stopped run's withdrawal
     is in the plan, it adds *and the copies at the removed path(s) of M shared file(s)*.
   - The suppressed line: *the copy of a shared file at the path it was withdrawn from*.
   - The *SHARED, KEPT* heading: *a path this removal does not take them from also holds*.
   - The *Kept* line: *another path or a camp file also holds*.

   The walk found the last one: the brief's list did not name it, and it said "another team" of a
   copy the same team may keep. `--team` is unchanged.
7. **`kept in … (another path there still holds it)` for a later upload**, under `--team` as well,
   since the holder kept for may be the same team at its own second path. The `kept_in` value is
   unchanged, since it decides which caselist's copy stays, so the JSON is unchanged too.
8. **No JSON key added.** The forbidden list keeps t11's keys, and I read adding one as changing
   them. The withdrawals are printed in the text, line by line as written, under *WITHDRAWALS*,
   and only when there are any. The JSON's `suppression_entries` already carry the digests. Adding
   a `withdrawals` key is your call (Follow-up 3).
9. **Nothing of `caselist status` was edited**, as briefed. v1-e30-t12 merged during the session;
   the sync brought it in, and the older-build checks were run against it too.
10. **No AWS call, and nothing of the operator's touched.** The only network calls were
    `git fetch origin dev` and the sync's own fetch. The older builds were not installed or run:
    their source was exported with `git archive` into the scratchpad.
11. **One commit was made with a test failing.** `b2274bc` added the two-caselist test with a
    helper misuse, and a chained command did not stop on the failure. `0710fc8` fixed it. No run
    reported above was made at `b2274bc`.

## Operator follow-ups

None. Nothing here needs a credential, nothing was run against a real bucket or the real data
directory, and the full suite ran here in four parts. The first removal made by a build with this
task writes `withdrawals.jsonl` only if it withdraws a copy; until then the file does not exist,
which every reader takes as no withdrawal recorded.

## Follow-up work

1. **The data-use policy's removal records (the PM's; `docs/policies/caselist-data-use.md`).**
   - Personal-data rule 6, the report table's *Removal log and suppression list* row, and *What
     removal does* ("Records the removal with request id, date, reason code, environment and
     sha256 values") list what the log and the list hold.
   - None names the three records kept beside them since `v1-e30-t13`: path holds, removal scopes
     and withdrawals. So none names the caselist slug a withdrawal now records.
   - It identifies no one, so rule 6 still holds. I propose adding to *What removal does*: "Beside
     the suppression list and the removal log it keeps, in the same way and with no school, team
     code or name, the paths a removal holds, what each removal reached, and the caselist each
     withdrawn copy was taken from, by its slug."
2. **`caselist status` could attribute a withdrawn file's residue (E30, after `v1-e30-t12`).**
   t10's Deviation 1 left "a shared file withdrawn from one caselist and kept elsewhere" out of the
   residue report because nothing said which caselist. The withdrawal record now says it. I did
   not edit status, as briefed.
3. **The plan's JSON carries no withdrawal lines (E30; your call).** Decision 8. One more
   top-level key, `withdrawals`, would match `path_holds`.
4. **A `--team --include-shared` plan's later upload at another holder's path** is still called
   "this team's copy" in the suppressed line and "this team's path(s)" in the count (E30). It is
   the other holder's path. ac4 is about `--source` only, and the brief limited the suppressed
   line's change to what ac4 needs, so I left it.
5. **A re-run's confirmation says "Removed from this environment: 1 file(s)" under "Nothing is
   left to remove"** (E30). It is what the start code printed too, in the re-run captured above.
   The confirmation counts the sources a re-run plans again, not what it removes.
6. **A removal made before this build has no withdrawal recorded, and a re-run does not add one**
   (E30; your call, likely no task). Its entries are already on the list, so a re-run plans none.
   Dev's only logged removal, RM-2026-90, is the synthetic exercise; prod has none.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-14

**Notes:**

Accepted in full, with the phase `Succeeded`. I have amended ac3 in this branch to the record
beside the log and the list, as Deviation 1 describes.

**Deviation 1 is the answer the brief asked for, and it is proven.** The brief asked whether t15's
removal scope could carry the caselist or whether a new record was needed. You ran the start
commit's own code over both shapes of the scope record, and it refused both and would have failed
`caselist status` on every run. A third record beside the log and the list, joined to each, follows
`v1-e30-t13` and `t15`, and every older build reads, imports, publishes and reports in sync with it
in place. ac3's words were written before that pattern was settled; the amendment makes them match
it. A removal from an earlier build attributing to nothing is the honest cost, and only dev's
synthetic RM-2026-90 has one.

**The work itself:**

* **ac2 did what it was for.** Case (3) was built first and was failing, 1 for 0 and 2 for 1.
* **Writing the withdrawals before the entries they attribute (Decision 2)** is the right order for
  the same reason as t15's scopes: a record without its entry harms nothing, and an entry without
  its record would never get one.
* **The joins (Decision 3)** are exact and pinned by `TestTheJoins`, including a request that
  withdrew a file in two runs.
* **The walk found a line the brief missed,** the *Kept* line's "another team", and fixed it.
* **The mutation run did its job twice:** W7 found a missing assertion and A3 found redundant
  matching code, replaced by a lookup that fails loudly. 31 of 31 caught.
* **Decision 11** (one commit with a failing test, no run reported at it) is noted, and saying so
  was right.

**Rulings:**

* **Deviations 1 to 4:** accepted. ac3 amended.
* **Decisions 1 to 11:** accepted. Decision 5 (a path under no team's directories is no team's) is
  accepted as the one rule, untested because no fixture has one.

**Follow-up work, filed by the PM:**

* **Your 1, the data-use policy:** the PM writes it at the next close-out, as policy 1.9, together
  with `v1-e30-t17`'s wording correction. It describes records that identify no one, so it does
  not tighten the policy.
* **Your 2:** joins the E30 p3 task "residue clearing gaps".
* **Your 3, 4 and 5:** one E30 p3 task, "removal output loose ends": a `withdrawals` key in the
  plan's JSON beside `path_holds` (yes, add it); the `--team --include-shared` later-upload wording;
  and the re-run's confirmation counting what it plans again rather than what it removes.
* **Your 6:** no task. Revisit if a real removal from an earlier build ever needs attributing.

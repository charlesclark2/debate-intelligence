# Session report: v1-e30-t20-removal-output-loose-ends

| | |
|---|---|
| Task | `v1-e30-t20-removal-output-loose-ends` — Loose ends in what a removal plan prints and how it decides what to drop |
| Spec | [`plan_specs/v1/e30-caselist-ingestion/t20-removal-output-loose-ends.yaml`](../../plan_specs/v1/e30-caselist-ingestion/t20-removal-output-loose-ends.yaml) |
| Epic / release | `v1-e30-caselist-ingestion` / `v1.1` |
| Branch | `task/v1-e30-t20-removal-output-loose-ends` |
| Session status | COMPLETE. Every criterion passed and the Goal is `Succeeded`. Read Deviation 1 first |

## Summary

All six items are done, each shown failing first.

* **(1)** The plan's JSON has a `withdrawals` list.
* **(2)** A `--team --include-shared` plan no longer calls another holder's path "this team's".
* **(3)** A re-run that removes nothing now says so.
* **(4)** `_dropped` decides by one rule.
* **(5)** No output of `caselist remove` names a path on this machine.
* **(6)** The JSON carries the sweep's count.

25 mutants were run and all 25 are caught. One (T4) was caught only after a test it showed was
missing.

**Four things to look at first.**

1. **Three assertions changed for item (5) (Deviation 1).** Item (4) was committed alone, at
   `a59c6d1`. At that commit every removal test passed unchanged: core 691, the node's selection
   330, CLI 96, smoke 36. ac3 is measured there. Item (5) then changes the very value three older
   assertions pinned: t09's `inbox_directory == str(inbox)` (twice) and a smoke check of
   `DOWNLOAD INBOX (<absolute path>)`. Each now expects the relative form, and nothing else in
   those tests changed. Your notes said to stop if a test failed for (4). These failed for (5),
   whose amendment changes exactly that value, so I changed them and am telling you here.
2. **An inbox outside the data directory has no relative path (Decision 1, PM question 1).** The
   inbox can be put anywhere with `caselist.inbox_dir`. In that case the value is the setting's
   name, `caselist.inbox_dir`, and the plan prints *the directory caselist.inbox_dir names*. That
   is my choice; your ruling covers the case where the inbox is inside the data directory.
3. **What a `withdrawals` entry holds (Decision 2).** Each entry is `{sha256, disclosure,
   caselist}`. The file's digest, the path's digest and the slug: nothing else from the record's
   line.
4. **`manifest_versions_swept` is an object, or the string `"not counted"` (Decision 3).** The
   object is `{"total": N, "by_manifest": {key: count}}`.

Known, not mine: `tests/evals/parser/test_parser_eval.py::test_the_labeled_pr_subset_holds_the_baseline`
fails on this Mac until the parser-evaluation baseline is written. I did not investigate it.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `removal-output`: Removal output loose ends | Done | Items (1) to (6), the runbook and the module docstring. Its criterion passes: `330 passed` |

## Acceptance criteria

Red runs were made on the start commit's code: the red tests were committed before any source
change (`02c780b`, `363be28`, `ae2ef63`), and the source was still `18d5af4`'s. Every test uses moto
in-process or the smoke suite's moto server, temporary data directories and, in the probe, a
temporary `HOME`. Nothing read the operator's `~/.debate-research`, `~/.aws` or LaunchAgents, and
nothing touched AWS or the network.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1**: the plan's JSON has `withdrawals`, one entry per withdrawal by digest and caselist slug, and an empty list when there are none, by test | PASS | **Red** (`02c780b`): `assert None == [{'sha256': '5555…', 'disclosure': 'de16…', …}]` and `assert None == []`; smoke: `AssertionError: assert [] == [{'sha256': '…', 'caselist': 'testcl26'}]`. **Green**: `test_the_json_has_one_withdrawal_for_each_the_plan_makes_by_digest_and_caselist`. It covers a team's two paths of a shared file and t23's held-path withdrawal, known by the held path's digest, in plan order. `test_a_plan_that_withdraws_nothing_has_an_empty_list` gives `[]`. `test_the_jsons_withdrawals_are_the_lines_the_plan_prints_under_withdrawals` checks the entries match the text. `test_the_plans_keys_are_t11s_and_the_two_this_task_adds` checks the keys are the start commit's 22, written by hand, plus `withdrawals` and `manifest_versions_swept`, and nothing else. Through the installed build, `test_the_jsons_withdrawals_are_the_plans_lines_and_what_the_execution_records` checks four things. The dry run's entries are the *WITHDRAWALS* lines. The execution's are the same. They match `withdrawals.jsonl` as the execution wrote it, by `(sha256, disclosure, caselist)`, with digests worked out by hand from the fixture's paths. The re-run's list is `[]` |
| **ac2**: (2) and (3), each wording shown failing first and corrected; the confirmation of a re-run that removes nothing says so | PASS | **(2) red**: `assert '  4 whole fi...ed file. Each' == '  4 whole fi...wn from. Each'`, i.e. the real plan printed `  4 whole file(s), and 1 of this team's path(s) to a shared file.` for Cedar Hollow/ZaLu's path. The hand-built plans failed on the count and on `…or another holder's copy of a later upload at the path it was withdrawn from.` **(3) red**, through the installed build: the `--team` re-run printed `  - Removed from this environment: 3 file(s), and this team's copies of 1 shared file(s).` under *Nothing is left to remove*. The hand-built plans failed the same way for the dry run and for the execution. **Green**: the count reads `N whole file(s), and 1 path(s) of another holder a later upload is withdrawn from` and the line on what the list stops reads `another holder's copy of a later upload at the path it was withdrawn from`. That holds in the dry run and in the execution, and no line says "this team's path" or "this team's copy". A plan with both kinds names both. A team plan withdrawing only from its own paths reads exactly as before. A re-run confirms `  - Removed from this environment: nothing; this run found nothing left to remove.`, in the dry run and in the execution, and no line of its confirmation counts a file as removed. What I checked is under "Every 'this team' wording" below |
| **ac3**: (4) the withdrawn-set check is removed from `_dropped`, and every removal test passes unchanged, with the mutant that removed it before now the code | PASS (see Deviation 1) | **First, did t23 change `_dropped`?** `git log -L '/^def _dropped(/,/^def _scope(/:…/removal_plan.py'` names t07, t11 and t14 only, so t23 did not. Nor did t23's held-path withdrawals go into the withdrawn set: they take paths by digest, and the list check alone has always dropped their rows. **The change** (`a59c6d1`) deletes `or (*taken_path(caselist, copy.release, path), digest) in withdrawn` and the `withdrawn` parameter through `_manifest_rewrites` and `_rows_to_drop`. That is t14's mutant W8, now the code. **Unchanged tests, at `a59c6d1`**: `pytest packages/debate_core/tests -k "removal or (caselist and manifest) or inbox or withdraw or suppression"` → `691 passed`; the node's selection → `330 passed in 23.88s`; CLI removal tests → `96 passed`; `tests/smoke/test_caselist_remove_smoke.py` and the camp-identity smoke file → `36 passed`. **Why the check decided nothing:** under "Item (4)" below. Mutants D1 to D3 show the remaining rule is load-bearing |
| **ac4**: (5) PM amendment, by tests shown failing first, no plan line, JSON value or refusal from `caselist remove` holds the data directory's absolute path, HOME or the user name | PASS | **Red** (`363be28`): `3 failed, 2 passed`. Every dry run, execution and re-run was flagged: `"the data directory's probe"`, `"the temporary directory"`, `"the user's name"`, `"an absolute path at 3248: '…DOWNLOAD INBOX (/private/var/folders/…/T/pytest-of-ch'"`, and in the JSON `"inbox_directory": "/private/var/…"`. The run a pull's lock stopped was flagged with `'rt-way (INBOX_IN_USE): a caselist pull is running (it holds /private/var/folders/…'`. An inbox a profile puts under `HOME` was flagged as `"the home directory's probe"`. The two that passed are the probe's test of itself and `caselist unsuppress`, which named no path. **Green**: `test_caselist_remove_names_no_path.py`, `5 passed`. The probe's method is under "The probe" below |
| **ac5**: (6) PM amendment, by test, the JSON's count equals the plan line's count and what the execution deletes; a plan that cannot list says not counted | PASS | **Red**: `assert None == {'total': 3, 'by_manifest': {…: 2, …: 1}}`, `assert None == {'total': 0, 'by_manifest': {}}`, `assert None == 'not counted'`; smoke `assert None == {'total': 1, 'by_manifest': {'manifests/testcl26/2026-09-01.jsonl': 1}}` and `assert None == 'not counted'`. **Green**, hand-built: the JSON's total and per-key counts are parsed back out of the printed *MANIFEST VERSIONS SWEPT* lines and compared. A plan with nothing to sweep gives `{"total": 0, "by_manifest": {}}`, and one that could not list gives `"not counted"`, never 0. Through the installed build, with t19's old manifest version, `test_the_jsons_sweep_count_is_the_plan_lines_and_what_the_execution_deletes` checks the JSON is `{"total": 1, "by_manifest": {<key>: 1}}`. The plan line says `1 noncurrent version(s) of 1 manifest(s)`, the manifest's line says `(1 version(s))`, and the execution deletes exactly that many versions of the key: its version ids before less after. With the bucket refusing `ListObjectVersions`, `test_a_plan_that_may_not_list_versions_says_the_sweep_was_not_counted` gives `"not counted"` and the plan line says `not counted.` |
| Node `removal-output`: `uv run pytest packages/debate_core/tests/application -k removal` | PASS | `330 passed in 24.22s`, as the spec writes it, at load 6.9 |
| Full suite, in eighths (`uv run --frozen pytest -n auto -m "not slow and not live" --part K/8`), each under a hard stop at 112 s, load 6.8 to 10.5 | PASS but for the known failure | `1039 passed`; `1042 passed`; `1041 passed, 2 warnings`; `1035 passed, 1 warning`; `1031 passed`; `1039 passed, 1 xfailed`; `1 failed, 1039 passed` (the known parser-evaluation test); `1037 passed, 1 xfailed`. 8,303 passed, 2 xfailed. Each part took 31 to 37 s |
| Lint, types, contracts, docs | PASS | `ruff format --check .`: 813 files already formatted. `ruff check .`: all checks passed. `uv run --frozen pyright`: `0 errors`. `lint-imports`: `12 kept, 0 broken`. `check_thin_handlers.py`: 22 within 25 statements. `check_links.py`: 1650 links in 248 files. `docs_index.py --check-descriptions`: 35 described. `check_command_blocks.py --base origin/dev`: OK. `validate_specs.py`: `OK: 366 files, 38 epics, 308 tasks, 20 releases`, after the phase was set |

### Item (4): why the withdrawn-set check decided nothing

For every `(caselist, path)` a `WITHDRAW` source takes, `_plan_source` and `_plan_other_source`
append `(sha256, disclosure_digest(caselist, path))` unless the list already stops the file there.
`after` is the list with those entries. So for every member of the withdrawn set,
`after.suppresses(sha256, disclosure=…)` is true. That held before this task too.

The list check asks under `_scope(copy)`. For a caselist row that is the caselist. For a camp row
it is `openev/<release>`, and `camp_path_disclosure(release, path)` is defined as
`disclosure_digest("openev", f"{release}/{path}")`. That is the digest of the camp path
`taken_path` gives, so camp rows match as well. Appending a `SUPPRESS` entry never takes a pair out
of the state.

The one way the two could differ is an un-suppress recorded *after* the plan's own clock (a clock
skewed between machines). There, the list as it will read lets the file back in at that path, and
the old code dropped its row anyway. Now the list decides, which is what your notes asked for. No
test makes such a list.

### Every "this team" wording (item 2)

I read every string in `caselist_remove.py` that says "this team", "the team's" or "another team".
I also grepped `debate_core/application` and `debate_cli/src` for the same: no message in core
says "this team". Under `--team`, later uploads and refused uploads are the only sources whose
paths can belong to someone else. `--team` names every file at the team's own paths, so a later
upload is only ever at a path the plan took from another holder, by `--include-shared`.

| Wording | Where | Can it name another holder's path or copy? |
|---|---|---|
| `N of this team's path(s) to a shared file` | suppression count | **Yes**: it counted every disclosure entry. Fixed |
| `this team's copy of a shared file at the path it was taken from` | the confirmation's *Suppressed* line | **Yes**: it was said of every withdrawal. Fixed |
| `Only this team's copies are withdrawn and suppressed` | *SHARED, KEPT* heading | No: it heads the named withdrawals only, which `_plan_source` takes from the team's own paths |
| `this team's copies of N shared file(s)` | confirmation's *Removed* line | No: it counts the named withdrawals only. Later uploads are counted on the *Also removed* line, which names no team |
| `kept in … (another team there still holds it)` | a withdrawn file's line | No: t16 already says *another path* for later uploads and refused uploads |
| `holds N file(s) under this team's directory` | inbox *NOTE* | No: it counts files under the team's own directories |
| `Kept: N file(s) another team disclosed too or a camp released` | confirmation | No: the holder kept for is someone other than the requesting team |
| `a --team removal holds no path` | *PATH ENTRIES* | No team's path or copy |

### The probe (item 5)

`v1-e34-t16`'s method, reused (its `Probe` copied into the new CLI test):

* **Directories.** The data directory is `<tmp>/Zqxdataprobe/.debate-research/dev`, and `HOME` is
  `<tmp>/Zqxhomeprobe/operator`. `Path.home()` is asserted to be the latter.
* **What it looks for**, case-insensitively: either probe name, `str(tmp_path)` and its resolved
  form, `getpass.getuser()` as a whole word, and any `~/` or `/Users/`, `/home/`, `/private/`,
  `/var/`, `/tmp/`, `/Volumes/`, `/opt/` or `/etc/` that does not follow a word, dot, colon or
  slash.
* **The probe tested on itself.** It must find an inbox path, a lock path under `HOME` and a `~/`
  path. It must pass the new wording and a `docs/runbooks/…` citation.

What it reads, all through the real composition root against moto, with `COLUMNS=1000`:

* **Outputs.** Stdout and stderr of every run, as text with `--verbose` and as `--json`:
  * a dry run before any pull, when there is no inbox;
  * a dry run with four inbox archives, three deleted and one rewritten;
  * `--execute` without `DEBATE_REMOVAL_PROFILE`, refused;
  * two runs under a pull's `RunLock`, which stop `INCOMPLETE` with `INBOX_IN_USE`;
  * the run that finishes;
  * the re-run's dry run, and its `--execute`;
  * a dry run with `caselist.inbox_dir` set to a directory under `HOME`;
  * `caselist unsuppress`, dry run and execution.
* **Records.** Every file under `<data_dir>/suppression/`, and every object under
  `manifests/_suppression/` in the bucket.

Mutant P4 builds the inbox's name from `Path.home()`. A separate run with it applied failed with
`"the home directory's probe"` and not the data directory's, so the home probe catches a string
built from `HOME`.

### Mutation runs

25 mutants, each one textual change to committed source, in `removal_plan.py`, `inbox_purge.py`
and `caselist_remove.py`.

* **The driver**, a script in the scratchpad:
  * it refuses a dirty tree, and a target that does not occur exactly once;
  * it restores the file from a byte copy in a `finally`, then checks its sha256 and that
    `git status --porcelain` is empty;
  * it gives each run a new, empty `HYPOTHESIS_STORAGE_DIRECTORY`, made by `mkdtemp` and checked
    empty (working agreement 8). None of these tests is a Hypothesis property, so
    `--hypothesis-show-statistics` does not apply.
* **Each run, two invocations** with `-p no:randomly -p no:cacheprovider --no-cov -n 8`:
  * the removal tests: the eight CLI removal output files, including both new ones, and
    `packages/debate_core/tests/application/caselist/` with `-k "removal or remove or inbox"`.
    472 tests, 473 after the test added for T4;
  * seven smoke checks: this task's five, t09's inbox check and t16's `--source` walk.
* **Timing.** The unmutated selection gave `472 passed | 7 passed` in 42 s. Batches of two, each
  under `perl -e 'alarm 118'`, 43 to 50 s a mutant, at load 6 to 11.
* **Validity.** No mutant failed at collection; every catch is a failing assertion.
* **Commits.** Every mutant ran on `8f4d15c`. T4 was run again on `9cbb9ba`.

| # | Mutation | Result | Caught by (first of the failing tests) |
|---|---|---|---|
| **(4) `_dropped`'s one rule** | | | |
| D1 | The list check ignores the row's path (`disclosure=None`) | CAUGHT, 37 failed | t21's `test_after_the_removal_alone_nothing_is_withheld`, t11's manifest-rewrite table |
| D2 | No list check | CAUGHT, 37 failed | the same, and t22's held-row re-run test |
| D3 | A camp row asked under `openev`, not `openev/<release>` | CAUGHT, 17 failed | t14's `test_a_later_upload_a_team_disclosed_too_is_withdrawn_from_its_camp_path_and_kept_for_the_team` |
| **(5) No path on this machine** | | | |
| P1 | `inbox_directory` back to the absolute path | CAUGHT, 6 failed | the three probe tests, t09's dry-run test |
| P2 | The lock refusal names the lock's path | CAUGHT, 1 failed | `test_no_output_of_a_removal_names_a_path_on_this_machine` |
| P3 | An inbox outside the data directory named by its path | CAUGHT, 1 failed | `test_an_inbox_a_profile_puts_outside_the_data_directory_is_named_by_its_setting` |
| P4 | The text's inbox built from `Path.home()` | CAUGHT, 3 failed | the probe's dry-run tests (`"the home directory's probe"`), t09's smoke check |
| P5 | Inside and outside the data directory swapped | CAUGHT, 22 failed | the probe tests, t09's inbox tests |
| **(1) `withdrawals`** | | | |
| J1 | Always empty | CAUGHT, 3 failed | `test_the_json_has_one_withdrawal_for_each_the_plan_makes_by_digest_and_caselist`, the smoke check |
| J2 | An entry's disclosure is the file's sha256 | CAUGHT, 3 failed | the same |
| J3 | An entry is the record's whole line | CAUGHT, 3 failed | the same |
| J4 | A held path's withdrawal left out | CAUGHT, 2 failed | the same |
| **(6) `manifest_versions_swept`** | | | |
| S1 | *Not counted* given as 0 | CAUGHT, 2 failed | `test_a_plan_that_could_not_list_says_not_counted_and_never_zero`, the smoke check |
| S2 | The total counts manifests, not versions | CAUGHT, 1 failed | `test_the_json_counts_the_sweep_in_all_and_by_manifest_as_the_plan_line_does` |
| S3 | Nothing to sweep given as *not counted* | CAUGHT, 1 failed | `test_a_plan_with_nothing_to_sweep_counts_none` |
| S4 | Every manifest counted as one version | CAUGHT, 1 failed | the per-manifest test |
| **(2) Another holder's path** | | | |
| T1 | Every withdrawn path is the team's | CAUGHT, 4 failed | `test_the_count_does_not_call_another_holders_path_this_teams`, the smoke check |
| T2 | No withdrawn path is the team's | CAUGHT, 3 failed | `test_a_team_removal_withdrawing_only_from_its_own_paths_reads_as_before`, t16's `test_a_team_removal_still_says_this_teams_where_a_team_asked` |
| T3 | The suppressed line never names another holder's copy | CAUGHT, 3 failed | `test_the_list_line_does_not_call_another_holders_copy_this_teams` |
| T4 | A refused upload's held digest is not looked at | **SURVIVED, then CAUGHT** after a test was added | `test_an_upload_refused_at_another_holders_held_path_is_that_holders_copy` |
| T5 | A withdrawal with no path to show is nobody's | CAUGHT, 3 failed | `test_a_withdrawal_an_earlier_run_left_no_path_of_is_still_called_this_teams`, two of t17's requester-line tests |
| T6 | Every disclosure entry counted as the team's | CAUGHT, 4 failed | the count test |
| T7 | A plan with both kinds drops the team's count | CAUGHT, 1 failed | `test_a_plan_withdrawing_from_both_kinds_of_path_names_each` |
| **(3) A re-run that removes nothing** | | | |
| R1 | The confirmation counts what it plans again | CAUGHT, 3 failed | `test_the_dry_run_of_a_rerun_that_removes_nothing_says_so_and_counts_nothing_removed`, the smoke check |
| R2 | It counts later uploads planned again as removed | CAUGHT, 2 failed | the same, dry run and execution |

What the run changed:

* **T4 found a missing test.** Two other cases already gave the same output: a refused upload at
  the team's own held path, and one with no digest at all, which counts as the team's (T5). No
  test had a refused upload at *another* holder's held path under `--team`. That is reachable: a
  `--source --include-shared` removal holds every holder's path, and then a `--team` removal runs
  under the same request. The new test pins it, and was seen passing unmutated (`17 passed`)
  before T4 was run again.
* **Two branches deleted before the run, rather than tested** (`8f4d15c`):
  * The no-path fallback first split by inclusion. That branch can never be taken: a later upload
    or a refused upload always carries its paths or its held digest.
  * The *Also stopped* line had a "not nothing to do" guard. It can never fire: a refused upload is
    planned only when its entry is not on the list, so its plan always has something to do.

## Files changed

- **`debate_core.application`**
  - `caselist/removal_plan.py`:
    - `_dropped`, `_rows_to_drop` and `_manifest_rewrites` lose the withdrawn set (item 4), with
      the docstring saying why;
    - `RemovalPlan.inbox_directory` is the inbox relative to the data directory (item 5).
  - `caselist/inbox_purge.py`:
    - `inbox_directory_named` and `INBOX_SETTING`;
    - `InboxInUse` names the lock as `caselist-sync.lock in the data directory`.
- **`debate_cli`**: `commands/caselist_remove.py`:
  - `withdrawals` and `manifest_versions_swept` in `plan_summary`;
  - the suppression count and the *Suppressed* line by whose path each withdrawal takes;
  - a re-run's *Removed* line, and its *Also removed* line;
  - the inbox by its place in the data directory;
  - the module docstring.
- **Tests**
  - `test_caselist_remove_output_loose_ends.py` (CLI, 17, new): items (1), (2), (3) and (6) on
    hand-built plans.
  - `test_caselist_remove_names_no_path.py` (CLI, 5, new): the probe.
  - `tests/smoke/test_caselist_remove_smoke.py`: 5 new checks, and t09's one assertion
    (Deviation 1). Its README row.
  - `test_removal_purges_inbox.py`: two assertions (Deviation 1).
- **Docs**: `docs/runbooks/caselist-removal.md`:
  - step 4's paragraph on the JSON: the new keys, and that neither form names a path on this
    machine;
  - step 4's *Other holders* check: the `--team --include-shared` wording;
  - step 10: a re-run's confirmation.
- **Spec**: the PM amendment (description, the forbidden entry, ac4 and ac5) and the phase.

## Deviations from the spec

1. **Three earlier assertions changed for item (5), none for item (4).** ac3's "every removal test
   passes unchanged" was met at `a59c6d1`, which holds item (4) alone; the counts are in the table.
   Item (5) changes the value of `inbox_directory` and the inbox's text, which these pinned:
   * t09's `test_the_plan_lists_every_inbox_file_holding_a_removed_file_and_what_happens_to_it`:
     `plan.inbox_directory == str(inbox)` is now `== "inbox"`.
   * t09's `test_a_removal_where_there_is_no_inbox_completes_and_creates_none`: the same, inside a
     tuple.
   * t09's smoke `test_the_download_inbox_is_listed_by_the_dry_run_and_purged_by_the_execution`:
     `DOWNLOAD INBOX ({inbox}): …` is now `DOWNLOAD INBOX (inbox in the data directory): …`.

   Each changed only its expected value, to the form the amendment rules.
2. **The forbidden entry was edited, as the amendment says.** It now allows `withdrawals`,
   `manifest_versions_swept` and the form of `inbox_directory`'s value. This came with the
   amendment in the first commit (`a58d79f`).

## Decisions and assumptions

1. **The inbox outside the data directory is named by its setting.** `caselist.inbox_dir` may name
   any directory. When it is not inside the data directory, no path relative to it exists without
   `..`. Such a path would name the directories above the data directory, a volume, or under the
   probe's layout the home directory's own name. So the value is `"caselist.inbox_dir"`, and the
   text says *the directory caselist.inbox_dir names*. Inside the data directory, the default, it
   is the relative path (`inbox`), as `summary_written_to` is. The runbook documents no profile
   that sets the setting, so the agent's setup gives `inbox`. PM question 1 asks whether you want
   this or the `..` path.
2. **A `withdrawals` entry is `{sha256, disclosure, caselist}`.** I read "by digest and caselist
   slug only" as: the file's digest, the path's digest and the slug, with no time, reason or
   request. The path's digest is what identifies one withdrawal. The file's digest says which file,
   as `sources[].withdrawn_disclosures` already does beside its source. The time, reason and
   request are on the matching `suppression_entries` line. The entries are the ones the plan
   appends: what *WITHDRAWALS* prints and the execution writes. A re-run that appends none has
   `[]`, as `path_holds` does.
3. **`manifest_versions_swept` is `{"total": N, "by_manifest": {key: count}}`, or `"not
   counted"`.** Your notes asked for "not counted" in the JSON as the plan line says it, and never
   0. A program tells the two apart by type, which no other key of the plan does. I preferred that
   to adding a third key such as `swept_counted`. Nothing to sweep is `{"total": 0, "by_manifest":
   {}}`: counted, and none. The execution's JSON carries the plan's count, the everyday profile's.
   The execution's own sweep count is not reported separately: it is inside
   `s3_versions_deleted`, as before.
4. **Whose path a withdrawal takes is read from its paths, not inferred.** The team's own paths
   are the disclosure digests of the withdrawals' `(caselist, path)` that `TeamSelector.holds`.
   A held-path withdrawal is judged by its digest against those. A withdrawal with no path left to
   show is the team's, as the plan always called it.
5. **The other-holder wording.** The count reads *N path(s) of another holder a later upload is
   withdrawn from*, and the list line *another holder's copy of a later upload at the path it was
   withdrawn from*. A plan with both kinds names both, and a team plan with only its own paths
   reads exactly as before. "Later upload" covers refused uploads too: the plan says each "goes
   through what a later upload goes through".
6. **"Removes nothing" is the plan's `nothing_to_do`, not a per-file judgement.** A partial re-run
   finishing a stopped run still counts the request's files in its confirmation, as before. Telling
   per file whether a re-run removes anything would need knowing which manifest rows each rewrite
   drops, which the plan does not keep. The *Also removed* line is left out with the *Removed*
   line. *Held: N path(s)* stays, because it describes holds in force, not what this run did.
7. **The probe test runs in-process**, with moto and the real composition root, as
   `test_os_error_text_in_results.py` and the pull's in-process smoke checks do. This task's other checks run against the installed build, through the smoke
   suite.
8. **No AWS or network call, and nothing of the operator's touched.** `check_command_blocks.py
   --base origin/dev` compares against the local `origin/dev` ref, with no fetch.

## Operator follow-ups

None. Nothing here needs a credential, nothing ran against a real bucket or the real data
directory, and the full suite ran here in eighths. If you want to see item (5) in your own dev
environment, this dry run plans a removal and changes nothing. It uses the everyday profile.
First put any file's sha256 in a variable, such as one from your register, in place of the
placeholder:

```bash
export ANY_SHA256=paste-a-sha256-here
```

Then, in this task's worktree, `grep -c` prints how many lines of the output hold your home
directory:

```bash
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e30-t20-removal-output-loose-ends
DEBATE_ENV=dev uv run debate-research caselist remove --source "${ANY_SHA256}" --request RM-2026-90 --reason REQUESTED_BY_TEAM | grep -c "${HOME}"
```

Success looks like `0`.

## Follow-up work

1. **A `--team` re-run of a `--team --include-shared` removal (E30, low).** If the first run
   withdrew a later upload from another team's path, the re-run plans it again as one of the
   request's own: `_plan_source` with no path, since the first run deleted the rows. Its
   *Suppressed* line then says *this team's copy*, as it did before this task. No path or record
   says whose the path was. Only a request that names both a `--source --include-shared` and a
   `--team` reaches it.
2. **The data-use policy (the PM's).** No record changes here, so the list of sidecar records in
   rule 6 and *What removal does* stays true.

## PM questions

Paste-ready for the PM:

````text
v1-e30-t20, PM question 1: what should inbox_directory be when caselist.inbox_dir puts the inbox
outside the data directory?

Your ruling made inbox_directory a path relative to the data directory. That exists only when
the inbox is inside it: the default, <data_dir>/inbox, which is what every documented setup has.

Options:
(a) The setting's name, "caselist.inbox_dir", with the text "the directory caselist.inbox_dir
    names". What I built. It names no directory on the machine. A program cannot join it to the
    data directory, but nothing reads the key, and the same was true of summary_written_to.
(b) A ".." path, e.g. "../../Downloads/inbox". Joinable, but it names the directories above the
    data directory: a volume (/Volumes/…), or for an inbox under another tree, the tree's names.
(c) null. A type change, which your ruling ruled out.

Recommendation: (a). It keeps the one promise the runbook makes, that the output names no path
on this machine, in every configuration, and the value is still a string.
````

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

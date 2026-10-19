# Session report: v1-e30-t24-status-residue-and-held-digests

| | |
|---|---|
| Task | `v1-e30-t24-status-residue-and-held-digests` — caselist status fails on every removal left unfinished, and reports a held digest the re-run has not listed |
| Spec | [`plan_specs/v1/e30-caselist-ingestion/t24-status-residue-and-held-digests.yaml`](../../plan_specs/v1/e30-caselist-ingestion/t24-status-residue-and-held-digests.yaml) |
| Epic / release | `v1-e30-caselist-ingestion` / `v1.1` |
| Branch | `task/v1-e30-t24-status-residue-and-held-digests` |
| Session status | COMPLETE. Every criterion passed and the Goal is `Succeeded`. Read Deviation 1 first |

## Summary

All four items are done, each shown failing first.

1. **A withdrawn copy left fails status.** It is `REMOVAL_RESIDUE`, exit 1 when every snapshot
   agrees, as a removed file's residue is. This follows your ruling on t19's question 1.
   *Withdrawals NOT ATTRIBUTED* is still reported beside the verdict and changes nothing.
2. **One predicate.** `removal_residue.purge_should_have_taken` is what status counts and what the
   same removal run again sweeps, for a run that completed. The rule: a noncurrent version of the
   rewritten key, other than the rewrite, older than that run's completion less fifteen minutes. A
   run that stopped keeps the sweep's strictly-older-than-its-rewrite rule (Decision 1). A property
   over generated listings holds that after the sweep, status counts no manifest version.
3. **Held digests in status.** Status reads `held-digests.jsonl` from both copies. It names under
   `removals_owed` each upload the same removal run again has not yet listed, whether or not its
   archive is still in the inbox. The new line is *REFUSED AT IMPORT AT A HELD PATH*, and the JSON
   key is `refused_at_import`.
4. **The short panel.** The `CASELIST_DRIFT` panel prints counts and digest prefixes of at most twelve
   characters, one line per snapshot that differs. `REMOVAL_RESIDUE`, the only other panel status
   raises with the whole record, does the same. `--json` is unchanged.

**Four things to look at first:**

1. **Status no longer counts a *current* manifest version as older than a removal (Deviation 1).**
   That is a narrowing of status, which your notes forbid, and it is what the predicate you wrote
   down does ("never takes the current version"). Without it the property is false: neither rule may
   take a current version, so status would count one forever. Nothing is lost. A current version
   that differs from this machine's manifest is a manifest mismatch in the same report, and fails
   it as `CASELIST_DRIFT`. One that does not differ is this machine's own manifest. A test walks the
   whole cycle: mismatch, publish, counted, re-run, clean.
2. **One t19 survivor test changed (Deviation 2).** It covered a completed run's key whose rewrite
   the bucket no longer holds. The rule is now against the completion, which the log records, so
   that old version goes. Its protection still stands for a stopped run, in a test of its own.
3. **Held digests are read when the inbox is (Decision 3).** That is `held_in_inbox=True`, which
   `caselist status` passes and `caselist pull` does not, so the pull reads nothing more.
4. **The cross-build check ran against `v1.1.0-dev.18`, and against `v1.1.0-dev.19` as well,**
   which is tagged now. I did not read your installation to see which one the agent runs. Both
   read every file this build writes.

Known, not mine: `tests/evals/parser/test_parser_eval.py::test_the_labeled_pr_subset_holds_the_baseline`
fails on this Mac until the parser-evaluation baseline is written. I did not investigate it.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `status-residue`: Status residue and held digests | Done | Items (1) to (4), the runbook, the smoke checks, the cross-build check. Its criterion passes: `418 passed` |

## Acceptance criteria

The red commit is `9137cf4`: tests only, with the source still the start commit's (`f5025a6`). Each
failure quoted below is an assertion, unless it is marked as a test naming `RefusedAtImport` or
`refused_at_import`, which this task adds; those I do not count as red evidence, and mutants show
they bite. Every test uses moto, the smoke suite's moto server, temporary data directories and, in
the held-digest tests, a temporary `HOME`. Nothing read the operator's `~/.debate-research`,
`~/.aws` or LaunchAgents, and nothing called AWS or the network.

Two red tests changed after `9137cf4`, each below the line its red run failed at:
- the window test's republish helper now uploads this machine's manifest, not the bucket's current
  bytes, for its final `in_sync`;
- the held-digest test publishes the imported week before its `in_sync` assertion.

Both red failures (the version still there, and `removals_owed == ()`) came first.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1**: a withdrawn copy left in a caselist that keeps no holder fails status as `REMOVAL_RESIDUE`, exit 1, by test shown failing first; a withdrawal not attributed does not | PASS | **Red, through the CLI**: `tests/smoke/test_caselist_remove_smoke.py::test_a_withdrawn_copy_left_in_a_caselist_that_keeps_no_holder_fails_status_as_removal_residue`, the installed command against the stand-in, failed with `assert 0 == <ExitCode.DOMAIN_FAILURE: 1>` (status `"ok"`). **Red in core**: `test_withdrawn_copies_fail_status.py`, t19's world (`RM-2026-07` withdrew the revision from `testcl26`, a current object of it put back): `AssertionError: assert not True` on `report.in_sync`, for a current object and for a version under a delete marker. In the CLI renderer: `'withdrawn from testcl26 (sha256 c0ffee000000, RM-2026-07)' in 'the bucket still holds versions of 1 removed file(s): …'` failed. **Green**: the command exits 1, `error.code == "REMOVAL_RESIDUE"`, `error.details.withdrawn_copies_left` names `testcl26`, the 12-character prefix, `RM-2026-07` and the counts. The message reads `the bucket still holds copies of 1 file(s) withdrawn from a caselist that keeps no holder of them: testcl26: 1 current object(s), 0 noncurrent version(s) and 0 delete marker(s) of 1 file(s) withdrawn from testcl26 (sha256 <12>, RM-2026-07)`. No whole digest is printed. The same removal run again clears it, and status is in sync. **Not attributed**: with `withdrawals.jsonl` gone from both places, `withdrawals_not_attributed == ("RM-2026-07",)` and `in_sync` holds. Through the installed command it exits 0 (`test_a_withdrawal_no_record_attributes_is_reported_and_status_still_exits_zero`, which passed on the start commit too, as it should) |
| **ac2**: one predicate decides a rewritten manifest's older versions for status and the sweep; a property test over fixture states (a run carrying on more than 15 minutes after its rewrite, a version in the same second) shows that after the same removal runs again status counts no manifest version | PASS | **The predicate**: `removal_residue.purge_should_have_taken`, called by status's `_older_versions` and by the sweep's `left_by_earlier_runs` for a completed run. **Red**, `test_status_and_the_sweep_share_one_rule.py` against moto with the real planner, executor and status, the run's rewrite forty minutes before its completion. *A noncurrent version written in the window* (another machine's publish thirty minutes before the completion, a publish on top): status counted `manifest 1`, and after the re-run the version was still there, `At index 1 diff: … Left contains one more item`. *A version in the same second as the rewrite*: `Extra items in the left set`, the same. **Green**: both are counted, then cleared, and status counts no manifest version. *A later publish whose version becomes noncurrent* stays, with the rewrite. *A version inside the margin* is neither counted nor taken. *A current version in the window* is a manifest mismatch until it is published over, then counted, then cleared (Deviation 1). *A stopped run* keeps strictly-older: a version a day before its rewrite goes, one half an hour after stays. **The property**: `test_one_rule_for_rewritten_manifests_property.py`, 500 examples, fresh `HYPOTHESIS_STORAGE_DIRECTORY`, `--hypothesis-show-statistics`: `500 passing, 0 failing, and 16 invalid`. Events: 47.29% *a completed run carries on more than the margin after its rewrite*; 17.64% *a noncurrent version in that window, which the strictly-older rule kept*; 12.40% *a version in the same second as a rewrite*; 2.91% *a current version older than a completed run's completion less the margin*; 32.17% *a rewrite the bucket no longer holds*; 68.80% *a run that stopped*. It also holds that the sweep names no current version, delete marker, other key, latest rewrite or later publish, and that another request's or environment's records change nothing it names. Mutant S1, the sweep's rule before this task, fails it, as do P2, P5 and S6. **t19's survivor tests**: all pass but one, changed and argued in Deviation 2 |
| **ac3**: a held digest the re-run has not listed is named under `removals_owed`, with the archive in the inbox and after it has gone, by test shown failing first; once listed it is not | PASS | **Red, through the CLI**: `tests/smoke/test_caselist_remove_smoke.py::test_an_upload_refused_at_a_held_path_is_owed_after_its_archive_has_gone_until_the_rerun_lists_it` failed with `assert (True, [], 0) == (True, ['RM-2026-03'], 0)`. The archive was imported from outside the inbox and the week published. **Red in core**, `test_status_reports_held_digests.py`, t23's world: *once its archive has left the inbox* `assert () == ('RM-2026-01',)`; *a line only the bucket's copy holds* the same; *a comparison of `testcl26`* the same. **Green**: owed after the archive has gone, and while it waits in the inbox (which passed on the start commit through the inbox, as before). It is named `RefusedAtImport(testcl26, <digest>, RM-2026-01)`, with no path, school, team or file. The bucket's copy is read too. **Not owed**: once the same removal run again lists it; once bytes another path holds are withdrawn from the held path; when an un-suppress lifted its hold; when another request holds the same path; when the same request holds another path; in a comparison of another caselist; and from a call that does not ask (`caselist pull`'s). The smoke check then shows the re-run planning it as `held_at_import`, the execution, and `removals_owed == []`. t15's smoke check of what status reads (only `manifests/_suppression/` objects, the everyday profile alone) passes unchanged |
| **ac4**: the `CASELIST_DRIFT` panel prints no full sha256 and no more than one line per differing snapshot; `--json` keeps every field, by test | PASS | **Red, through the CLI**: `packages/debate_cli/tests/test_caselist_publish.py::TestStatus::test_the_panel_before_a_publish_counts_each_week_on_one_line_and_names_no_whole_digest`, `caselist status` before a publish, failed with `Left contains 27 more items, first extra item: '3d4b59df70f7…'`. **Red in the renderer**: three unpublished weeks of 250 sources each, `Left contains 750 more items`. No snapshot had a line of its own (`assert 0 == 1`). The `REMOVAL_RESIDUE` panel printed `snapshots: [{'caselist': 'testcl26', …` (*the record, dumped*). **Green**: the panel is the message, then `environment`, `bucket`, `snapshots: N compared, M differ`. Next comes one line per differing snapshot, e.g. `testcl26 2026-09-29: no manifest in the bucket, 250 source(s) not in the bucket (sha256 <12>, <12>, <12> and 247 more)`, then `every digest: in full under error.details of --json`, then the hint. No 64-character digest, and no prefix over 12. `failure.details` is still the whole `status_summary`, and the `--json` envelope's `error.details` has every snapshot's `missing_sources` in full (`test_status_before_a_publish_exits_non_zero_with_every_snapshot_reported`, unchanged). Decision 7 lists the other panels status can raise |
| **ac5**: an earlier build (the agent's at the time) reads every file this build writes, by the cross-build check | PASS | This task adds no stored file, field or line shape (Decision 8). **This build writes the same records**: `WRITE_STORED_SUPPRESSION_LISTS=this-build` and `WRITE_HELD_DIGEST_FILES=this-build` regenerated the stored files, and with moto's random version ids masked every line was identical; I restored the committed files. **Older builds read them**: `git archive v1.1.0-dev.18` (`0268cf782cdc`) and, since it is tagged now, `v1.1.0-dev.19` (`1e633638cbd6`), each put first on `PYTHONPATH` for `CHECK_AN_OLDER_BUILD_READS=this-builds-files … check_an_older_build_reads_this_builds_files.py`: `5 passed` each, printing `reader: the debate_core source at v1.1.0-dev.18` (and `.19`), `import of the next week: SUPPRESSED 4, completed`, `publish: succeeded True; status in sync: True`, `status with the residue check: completed; caselists checked: openev, testcl26`, and `removal of RM-2026-02 run again beside the record: … the same plan as without it: True`. The two refusals it prints (a path entry inside the list, a caselist in the scope record) are the shapes no build writes, as for every older build |
| Node `status-residue`: `uv run pytest packages/debate_core/tests/application -k "status or residue or removal"` | PASS | `418 passed in 50.22s`, run as the spec writes it, at load 19 |
| The final set, run once as the PM's note of 2026-10-19 asks: `uv run --frozen pytest packages/debate_core/tests packages/debate_cli/tests tests/smoke tests/architecture tests/specs -n auto -m "not slow and not live"` | PASS | `7250 passed, 2 xfailed, 3 warnings in 197.35s`. `tests/smoke` is in it because this task changes it. Before the note arrived, the whole default selection had already run once, in parts, at loads of 13 to 47 from other sessions: 8,804 passed and 2 xfailed, with the one known failure, `test_the_labeled_pr_subset_holds_the_baseline`. It was not run again |
| Lint, types, contracts, docs | PASS | `ruff format --check .`: `834 files already formatted`. `ruff check .`: `All checks passed!` `uv run --frozen pyright packages/debate_core packages/debate_cli`: `0 errors, 0 warnings, 0 informations` (the project includes `packages` only; Follow-up 2). `lint-imports`: `Contracts: 12 kept, 0 broken.` `check_thin_handlers.py`: `OK: 22 … within 25 statements`. `docs_index.py --check-descriptions`: `All 36 indexed documents under docs/ have a description`. `check_links.py`: `OK: 1695 relative links and anchors in 254 Markdown files`. `check_command_blocks.py --base origin/dev`: OK. `validate_specs.py`: `OK: 377 files, 38 epics, 319 tasks, 20 releases`, after the phase was set |

### Mutation runs

The driver is a scratchpad script.

* **Each mutant** is one textual change to committed source. The driver refuses a dirty tree and a
  target that is not there exactly once.
* **Each run** has a new, empty `HYPOTHESIS_STORAGE_DIRECTORY` (working agreement 8): one property
  is among the tests. Flags: `-n 6 -p no:randomly -p no:cacheprovider --no-cov`, under
  `perl -e 'alarm 110'`.
* **Restoring** is from a byte copy, then the driver checks the file's sha256 and `git diff --quiet`.
* **The selection** is 134 to 136 tests:
  - this task's core files: withdrawn copies, one rule, the property, held digests;
  - t19's residue-gaps tests, t15's residue tests and t21's held-path tests;
  - the CLI panel, residue-clearing and held-path renderer tests;
  - `test_caselist_publish.py`'s `TestStatus` and its removal-hint class.

  The unmutated selection passed in 17 s.

Every mutant ran against the final source. No source file changed after `77aeb3f`, only tests,
the docs and the phase. One run was killed by an outer stop I had wrapped round the driver, which
left mutant W1 in the tree. I checked the diff was exactly W1, restored the file from git, and then
ran W1 again. No outer stop was used after that.

| # | Mutation | Result | First failing test |
|---|---|---|---|
| **The shared predicate** | | | |
| P1 | A current version is taken | CAUGHT, 2 failed | `test_a_version_the_store_lists_as_current_is_kept_whatever_its_time` |
| P2 | A delete marker is taken | CAUGHT, 2 failed | the property |
| P3 | The rewrite itself is taken | CAUGHT, 5 failed | `test_a_version_in_the_same_second_as_the_rewrite_is_counted_and_then_cleared` |
| P4 | Any key's version is taken | CAUGHT, 5 failed | `test_its_rewrites_older_versions_go_and_one_after_its_rewrite_stays` |
| P5 | Status keeps t15's rule, current versions counted | **SURVIVED, then CAUGHT**, 2 failed | `test_a_current_version_written_in_the_window_is_a_manifest_mismatch_until_published_over`, and the property |
| **The sweep** | | | |
| S1 | A completed run keeps the strictly-older rule (the start commit's sweep) | CAUGHT, 5 failed | `test_a_rewrite_the_bucket_no_longer_holds_leaves_what_status_counts_to_be_cleared` |
| S2 | A stopped run's rewrite sweeps nothing | CAUGHT, 1 failed | `test_its_rewrites_older_versions_go_and_one_after_its_rewrite_stays` |
| S3 | Every run counts as completed | CAUGHT, 2 failed | `test_a_rewrite_the_bucket_no_longer_holds_sweeps_nothing_of_its_key` |
| S4 | A stopped log entry counts as completed | CAUGHT, 2 failed | the same |
| S5 | Another request's scopes are this request's | CAUGHT, 2 failed | `test_a_key_only_another_requests_or_environments_run_rewrote_is_not_this_requests[another request]` |
| S6 | Another environment's scopes are this one's | CAUGHT, 2 failed | the property |
| S7 | A key the run rewrites now is swept too | CAUGHT, 1 failed | `test_a_manifest_the_plan_rewrites_again_is_counted_as_rewritten_and_not_swept` |
| S8 | The planner reads no log entries | CAUGHT, 4 failed | `test_a_rewrite_the_bucket_no_longer_holds_leaves_what_status_counts_to_be_cleared` |
| **A withdrawn copy left** | | | |
| W1 | Withdrawn copies are not `found` | CAUGHT, 7 failed | `test_a_withdrawn_copy_left_in_a_caselist_that_keeps_no_holder_is_not_in_sync` |
| W2 | The message leaves the withdrawn copies out | CAUGHT, 2 failed | `test_beside_a_removed_files_residue_both_are_named` |
| W3 | A withdrawn-only caselist gets an empty *REMOVAL RESIDUE* line | CAUGHT, 1 failed | `test_the_table_no_longer_says_the_clean_line_and_says_what_to_run` |
| W4 | The clean line printed beside a withdrawn copy | CAUGHT, 2 failed | the same |
| W5 | A withdrawn-only message says *versions older than a removal* | **SURVIVED, then CAUGHT**, 1 failed | `test_it_is_removal_residue_named_by_caselist_prefix_and_request` |
| **Held digests** | | | |
| H1 | The record is not read | CAUGHT, 6 failed | `test_a_line_only_the_buckets_copy_holds_is_read_too` |
| H2 | One the list stops at the held path is still owed | CAUGHT, 1 failed | `test_bytes_withdrawn_from_the_held_path_alone_are_not_owed_once_withdrawn` |
| H3 | Any request's hold at the path will do | CAUGHT, 1 failed | `test_another_requests_hold_at_the_same_path_does_not_make_it_owed` |
| H4 | Any caselist's hold will do | CAUGHT, 1 failed | `test_a_comparison_of_another_caselist_does_not_report_it` |
| H5 | A hold of any path will do | **SURVIVED, then CAUGHT**, 1 failed | `test_the_same_requests_hold_of_another_path_does_not_make_it_owed` |
| H6 | `removals_owed` leaves them out | CAUGHT, 7 failed | `test_a_line_only_the_buckets_copy_holds_is_read_too` |
| H7 | The record is read when not asked | CAUGHT, 1 failed | `test_a_comparison_that_does_not_ask_reads_no_record` |
| H8 | The hint keeps the old wording | CAUGHT, 1 failed | `test_the_table_names_it_by_caselist_prefix_and_request_and_says_what_to_run` |
| H9 | The table prints no line for them | CAUGHT, 1 failed | the same |
| H10 | The JSON counts the inbox's instead | CAUGHT, 1 failed | `test_the_json_gives_one_entry_per_caselist_by_count_prefix_and_request` |
| **The panel** | | | |
| D1 | The panel ignores `panel_details` | CAUGHT, 5 failed | `test_it_prints_no_whole_digest` |
| D2 | The drift failure gives no `panel_details` | CAUGHT, 4 failed | `test_it_prints_at_most_one_line_per_differing_snapshot` |
| D3 | The residue failure gives none | CAUGHT, 1 failed | `test_it_prints_counts_and_prefixes_and_keeps_every_field_in_the_json` |
| D4 | Whole digests instead of prefixes | CAUGHT, 3 failed | `test_a_snapshots_line_says_each_kind_of_difference_by_count` |
| D5 | Every digest by prefix, none counted | CAUGHT, 2 failed | `test_it_prints_at_most_one_line_per_differing_snapshot` |
| D6 | A line for every snapshot, agreeing ones too | CAUGHT, 2 failed | the same |
| D7 | The JSON's details are the panel's | CAUGHT, 1 failed | `test_it_prints_counts_and_prefixes_and_keeps_every_field_in_the_json` |
| D8 | *no manifest in the bucket* is not said | CAUGHT, 1 failed | `test_the_panel_before_a_publish_counts_each_week_on_one_line_and_names_no_whole_digest` |

36 of 36 caught. They all ran before the PM's note of 2026-10-19 capped mutation runs at about 20; none has run since. Three survived first, and each was a missing test, now written and seen passing
unmutated before the mutant ran again:

* **P5**: no state had a current version in a long run's window. That is now a moto test (the
  whole cycle), and the property generates it (2.91% of examples, up from 0.77% before I gave it
  another machine's publish during the last run).
* **W5**: the start of a withdrawn-only message.
* **H5**: the same request holding another path.

No mutant failed at collection, and every catch is a failing assertion.

## Files changed

- **`debate_core.application`**
  - `caselist/removal_residue.py`: `purge_should_have_taken`; `CaselistResidue.found` counts
    withdrawn copies; the module docstring, "One rule with the sweep".
  - `caselist/manifest_sweep.py`: `EarlierRewrite`, `earlier_rewrites`, `left_by_earlier_runs` (was
    `older_than_their_rewrite`), and the stopped run's rule; the module docstring.
  - `caselist/removal_plan.py`: `RemovalPlan.earlier_rewrites` is `EarlierRewrite`s; the planner
    reads the log's entries too; docstrings.
  - `caselist/status_service.py`: `RefusedAtImport`, `CaselistStatusReport.refused_at_import` and
    `refused_at_import_of`, `removals_owed`, `_refused_at_import`, and docstrings ("What an import
    refused").
  - `ports/suppression.py`: `RemovalLogWithScopes`.
- **`debate_cli`**
  - `output.py`: `CommandFailure.panel_details`, printed by the panel in place of `details`.
  - `commands/caselist.py`: `_status_panel`, `_what_differs`, `_some_prefixes`, `_residue_held`,
    `_withdrawn_counts`; the withdrawn copy in the residue message; the *REFUSED AT IMPORT AT A
    HELD PATH* line and hint; the `refused_at_import` JSON key; docstrings.
- **Tests**
  - New: `test_withdrawn_copies_fail_status.py` (4), `test_status_and_the_sweep_share_one_rule.py`
    (7), `test_one_rule_for_rewritten_manifests_property.py` (1 property),
    `test_status_reports_held_digests.py` (11), `commands/test_caselist_status_panels.py` (11).
  - Changed: `test_residue_clearing_gaps.py` and `test_caselist_residue_clearing_output.py`
    (Deviations 2 and 3); `test_caselist_publish.py`, one panel test.
  - Smoke: three checks in `tests/smoke/test_caselist_remove_smoke.py`, and the README's row.
- **Docs**: `docs/runbooks/caselist-removal.md`. *WITHDRAWN COPIES LEFT* exits 1. The panel. The
  *REFUSED AT IMPORT* line in step 9. The sweep's rule. "A manifest count that stays" should no
  longer happen. A current version is a manifest mismatch.
- **Spec**: the phase.

## Deviations from the spec

1. **Status no longer counts a current manifest version as older than a removal.** Your notes say
   "it does not narrow status", and that the one predicate "never takes the current version". Both
   cannot hold for one function both call, and I followed the predicate. Under t15's rule, status
   counted a current version too, if it was not the rewrite and was older than the completion less
   the margin. No rule may take a current version (the forbidden list), so such a version was
   counted and never cleared, which is the gap this task closes. It cannot be residue the report
   misses:
   - where it is not this machine's manifest, the comparison reports it as a manifest mismatch,
     and the command fails as `CASELIST_DRIFT` with the publish hint;
   - the publish makes it noncurrent, status then counts it, and the re-run clears it;
   - where it is this machine's manifest, it holds no removed row.

   `test_a_current_version_written_in_the_window_is_a_manifest_mismatch_until_published_over`
   walks that cycle. Mutant P5 restores t15's rule in status, and that test and the property catch
   it. No other status count changed: aggregates keep t15's rule, current versions included.
2. **One survivor test t19 wrote changed, and its protection moved.**
   `test_a_rewrite_the_bucket_no_longer_holds_orders_nothing_and_sweeps_nothing_of_its_key` held
   that, for a completed run, nothing of a key whose rewrite is gone is swept. Status counted that
   old version all the same (t15's rule never needed the rewrite), so it was counted and never
   cleared. The run's completion is what versions are compared with now, and the log records it, so
   the version goes. The test is now
   `test_a_rewrite_the_bucket_no_longer_holds_leaves_what_status_counts_to_be_cleared`: counted
   before, gone after, status clean. The old protection still stands for a stopped run, in
   `test_a_rewrite_the_bucket_no_longer_holds_sweeps_nothing_of_its_key`. Every other t19 survivor
   test passes unchanged: the current version, the rewrite, newer versions, the same second inside
   the margin, delete markers, a prefix-only key, and another request or environment.
3. **Two t19 assertions flip by your ruling**, each with a comment: the core status test's
   `assert report.in_sync` is now `not`, and the CLI's
   `test_it_does_not_change_whether_the_command_succeeds` is
   `test_it_fails_the_command_as_residue`. A report with only *not attributed* still exits 0, and
   that is asserted beside it.
4. **One commit's pyright check went through `| tail` inside an `&&` chain** (`77aeb3f`). It printed
   `0 errors`, so nothing failing was committed, but it is the pattern the PM named. Every check
   since ran bare.

## Decisions and assumptions

1. **A stopped run keeps the strictly-older-than-its-rewrite rule.** Status compares nothing with a
   stopped run (`completed_removals` takes `COMPLETED` entries only), so nothing it reports waits on
   that rule. A scope records a rewrite only once its purge is done, so a version older than the
   rewrite is one that purge should have taken. A stopped run has no completion that bounds what
   came after its rewrite: a version written after a stopped run's rewrite may be a publish made
   after the run stopped, and the strictly-older rule never takes it. So does a scope whose log entry
   the log does not hold.
2. **"Completed" is the scope's own join.** `manifest_sweep.earlier_rewrites` gives a rewrite its
   run's completion when a `COMPLETED` log entry is the one its scope joins
   (`RemovalScopeEntry.joins`: environment, request and moment). `completed_removals` reads the log
   the same way for status. The planner's removal log is now typed `RemovalLogWithScopes`, a
   protocol for the entries and the scopes together. `RecordedRemovalLog` is one, and it is the only
   implementation.
3. **Held digests are read with the inbox, under `held_in_inbox=True`.** Your notes put them beside
   the inbox ("whether or not the archive is still in the inbox"), and `caselist pull`, which asks
   for neither, reads no more than before: `test_a_comparison_that_does_not_ask_reads_no_record`.
   A new keyword would have meant a third flag that is always passed with the second.
4. **What counts as owed.** A line of the record whose request holds that path (a hold in force at
   the line's path digest, under the same request) in a caselist compared, and which the list does
   not stop there, whole or as that path's disclosure. That is the re-run's own condition
   (`_refused_at_import` and its "listed already" check). So:
   - a hold an un-suppress lifted makes nothing owed, since the re-run lists nothing for it;
   - another request's hold at the same path makes nothing owed either;
   - nor does the same request's hold of another path.

   The record holds no date, so `--snapshot` does not narrow it.
5. **An upload is named twice while its archive waits**, under *HELD UPLOADS IN THE DOWNLOAD INBOX*
   and under *REFUSED AT IMPORT AT A HELD PATH*. Each line says what one source holds. The request
   is owed once.
6. **The panel.** `CommandFailure.panel_details` is what the panel prints in place of `details`, and
   the JSON envelope never carries it. For status it holds the environment and bucket, then
   `snapshots: N compared, M differ`. Next comes one line per differing snapshot, counting what
   differs: no manifest on either side, a manifest mismatch, sources missing on either side, source
   mismatches and suppressed rows. Up to three digests per kind are named by twelve-character
   prefix, with *and N more* for the rest. The last line says every digest is in `--json`. The
   table above it already counts every snapshot.
7. **The panels status can raise, checked for the same dump.** Two passed the whole report as
   `details`: `CASELIST_DRIFT` and `REMOVAL_RESIDUE`, and both now print the summary. The others
   print scalars only, so they have nothing to fix:
   - `NoCaselistEvidence`, `InvalidStatusRequest`, and the store errors through
     `CommandFailure.from_exception`;
   - `EVIDENCE_STORE_NOT_CONFIGURED` (the environment's name).

   Outside status, `caselist publish`, `verify`, `caselist parse` and `caselist pull` also pass a
   whole payload as `details` (Follow-up 1).
8. **No stored file, field or line shape is added.** The new things are `RefusedAtImport`,
   `CaselistStatusReport.refused_at_import`, `EarlierRewrite`, the protocol, a `CommandFailure`
   field, and one JSON key in `caselist status`: `refused_at_import`, one object per caselist
   compared, shaped as `held_in_inbox` is. `RemovalPlan.earlier_rewrites` changed type in memory.
   The plan's JSON is unchanged.

## Operator follow-ups

None blocks the merge. After it, run one read-only `caselist status` in each environment, as after
t19. They use your everyday profiles, so they are yours to run. Run them from any checkout of `dev`
that has the merge, or from this task's worktree before `scripts/task finish`. Each takes a few
seconds per caselist.

Dev:

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e30-t24-status-residue-and-held-digests
aws sso login --profile debate-dev-evidence
DEBATE_ENV=dev uv run debate-research caselist status
```

Prod, against the dev data directory, as the removal runbook says:

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e30-t24-status-residue-and-held-digests
aws sso login --profile debate-prod-evidence
DEBATE_ENV=prod DEBATE_STORAGE__DATA_DIR="$HOME/.debate-research/dev" uv run debate-research caselist status
```

What each result means:

- **Dev exits 1 with `CASELIST_DRIFT` on `testcl26` alone**: expected, as you said. The panel under
  the table is now one line per differing snapshot, with counts and prefixes, not the whole report.
- **Prod exits 1 with `CASELIST_DRIFT`** for the weeks it lags dev: the same as on 2026-10-18 until
  the next promotion. Its panel should be a few lines, not about 1,000.
- **Any *REMOVAL RESIDUE in …* or *WITHDRAWN COPIES LEFT in …* line**, or a failure with the code
  `REMOVAL_RESIDUE`: paste the lines under the table back. They hold caselists, roles, counts,
  digest prefixes and request ids only. A *WITHDRAWN COPIES LEFT* line was not on 2026-10-18's
  outputs, so none is expected now either. It would now fail the command where before it did not.
- ***REFUSED AT IMPORT AT A HELD PATH in …***: an upload the agent refused at a held path that the
  same removal has not yet listed. Neither environment has had a `--source` removal with a hold, so
  none is expected. Paste it back if it appears.
- ***Manifest and aggregate versions NOT CHECKED against RM-2026-90*** (dev): expected, as since
  t15.

One question for you, not a command: **which tag does the weekly agent run now?** I checked against
`v1.1.0-dev.18`, as your notes said, and `v1.1.0-dev.19`, which is tagged. Both read every file. If
it runs another, tell me, and I will run the check against that one.

## Follow-up work

1. **Other commands' panels print a whole report as `details`** (E01 or each command's epic). Four
   do: `caselist publish` (`_publish_failure`, both failures), `verify`, `caselist parse` (both
   failures) and `caselist pull`. `CommandFailure.panel_details` is there for them now. None is a
   `caselist status` panel, so I left them, as your notes asked.
2. **Pyright does not check `tests/smoke`** (E01). The project includes `packages` only. Named
   explicitly, it reports 19 errors in smoke files this task does not touch, such as
   `test_caselist_pull.py`, `test_cli_smoke.py` and `test_site.py`. CI does not see them.
3. **The parser-evaluation baseline** (E31): the known failure, unchanged.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-19

**Notes:**

Accepted, with the phase `Succeeded`. The branch must sync before its pull request: v1-e30-t25 has
merged, and the two touch the same removal smoke file and its README row. Keep both tasks' checks,
then run the affected set (agreement 10) and the smoke file.

**The work itself:**

* **One predicate for status and the sweep,** with a property over generated listings whose events
  show it reaches the states that matter: a long run's window, the same second, a current version
  in the window. P5 survived until the property was taught another machine's publish, and that is
  the right fix.
* **A stopped run keeps the old rule, for a reason written down** (Decision 1): it has no
  completion to bound what came after its rewrite.
* **Held digests read only when the inbox is,** so `caselist pull` reads nothing more, shown by
  test.
* **The panel now prints a summary, and `--json` keeps every field.** It also catches the second
  panel (`REMOVAL_RESIDUE`) that dumped the record.
* **The `| tail` slip in `77aeb3f` was reported** and did not hide a failure.

**Rulings:**

1. **Deviation 1 is accepted.** My two notes contradicted each other, and the session followed the
   right one. A current version can never be swept, so counting it was permanent residue. A current
   version that is not this machine's manifest already fails status as `CASELIST_DRIFT`, and the
   cycle test shows it is then counted and cleared. That is not a narrowing in what status catches.
2. **Deviations 2 to 4 and Decisions 1 to 8: accepted.** Decision 5's double naming while an
   archive waits is right: each line says what one source holds.
3. **The agent's tag:** `v1.1.0-dev.18` until tonight's reinstall (A12 of v1-e31-t20's list), which
   moves it to the newest pre-release, one that will hold this task. The check against dev.18 is the
   one that matters, and it passed.
4. **Follow-up 1** (other commands dump a whole payload in their panels): next PM batch, p3, using
   `panel_details`.
5. **Follow-up 2** (pyright does not check `tests/smoke`): joins `tests/scripts` on the deferred
   tooling list; one task will widen pyright to the test trees.
6. **The operator's status runs** are folded into A13, together with v1-e30-t25's check for an
   earlier build's junk row at a held path. One status run per environment covers both.

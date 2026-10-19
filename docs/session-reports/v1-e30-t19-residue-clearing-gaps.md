# Session report: v1-e30-t19-residue-clearing-gaps

| | |
|---|---|
| Task | `v1-e30-t19-residue-clearing-gaps` — Removal residue the status reports can always be cleared, and says whose it is |
| Spec | [`plan_specs/v1/e30-caselist-ingestion/t19-residue-clearing-gaps.yaml`](../../plan_specs/v1/e30-caselist-ingestion/t19-residue-clearing-gaps.yaml) |
| Epic / release | `v1-e30-caselist-ingestion` / `v1.1` |
| Branch | `task/v1-e30-t19-residue-clearing-gaps` |
| Session status | COMPLETE. Every criterion passed and the Goal is `Succeeded`. Read Deviation 1 and the PM questions first |

## Summary

What `caselist status` reports after a removal can now be cleared by running the same removal again,
and status says whose a withdrawn copy's residue is. The six items:

1. **A rewritten manifest's older version.** The sweep now has two rules, in one function
   (`manifest_sweep.py`) that the dry run and `--execute` share:
   - the old rule: a version that names a removed file;
   - the new rule: a version of a key an earlier run *of the same request* rewrote, strictly older
     than that rewrite. The rewrite is the one recorded in that run's scope.

   It never takes the current version, the rewrite, a newer version, a delete marker, or another
   request's or environment's key.
2. **A withdrawal-only request.** Its re-run reads `withdrawals.jsonl` for the caselist each copy
   was taken from, and plans that caselist's aggregates again (and the copy there, where no holder
   keeps it).
3. **The dry run** counts what the sweep will delete (*MANIFEST VERSIONS SWEPT … N noncurrent
   version(s) of M manifest(s)*). It never says *Nothing is left to remove* when the sweep would act.
4. **The hint.** A manifest mismatch whose manifest the publisher withholds gets the removal's hint
   and not the publish hint. Status asks the publisher's own `SnapshotPlan.withholding_rows`.
5. **Attribution.** Status names a withdrawn copy's residue by the caselist it was withdrawn from
   and the request, from the withdrawal record. A withdrawal with no record is *NOT ATTRIBUTED*.
6. **The smoke check** runs against an installed build of this branch and `s3_stand_in`.

No exit code changed, and no stored file, field or record shape was added. The agent's
`v1.1.0-dev.18` reads everything this build writes.

**Look at these first:**

1. **Withdrawn-copy residue does not fail `caselist status` (Deviation 1, PM question 1).** It is a
   new finding of something left in the bucket. The forbidden list forbids changing any exit code
   status returns, so it is reported beside the exit code, like t21's held rows. Whether it should
   fail as `REMOVAL_RESIDUE` is your call.
2. **(2) cannot find the team's paths, and does not need them (Decision 2).** No record anywhere
   holds a path; that is the policy. What the re-run needs from the paths is the caselist, and the
   withdrawal record holds exactly that.
3. **The hint follows the publisher's rule, so a held *skipped* row still gets the publish hint
   today (Deviation 2).** Your notes say "since t22, that includes … held skipped rows". t22's
   publisher does not withhold for those (t22 Decision 5); `v1-e30-t23` makes it. A test ties the
   hint to what the publish actually does, so the hint changes with t23 with no change here.
4. **A parser-evaluation test fails on `dev` itself, not on this branch's account.**
   `tests/evals/parser/test_parser_eval.py::test_the_labeled_pr_subset_holds_the_baseline` says
   *no baseline is established for the pr-subset tier*. Before the sync it was skipped. `dev`'s
   `b935530 labels/2026 10 18 (#308)` committed labels without a baseline. This branch touches no
   parser, eval or label file (`git diff --name-only origin/dev...HEAD`).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `residue-gaps`: Residue can be cleared and is attributed | Done | The two re-run cases, the dry-run line, the hint, the attribution and the smoke check. Its criterion passes: `355 passed`. All five Goal criteria pass. |

## Acceptance criteria

Commit ids are on the branch after `scripts/task sync`, onto `origin/dev` at `b935530`. The rebase
was clean. The red runs were made before the sync, at the commit now called `6e7520a`, which adds
tests only; its source is the start commit's. The branch is not on origin. Every test uses moto,
fakes and temporary directories, and the CLI tests a temporary `HOME`. Nothing read the operator's
`~/.debate-research`, `~/.aws` or LaunchAgents, and nothing called AWS.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1**: (1) and (2) are each built as a fixture against moto, shown failing first, and the same removal run again clears it | PASS | **Red**, `6e7520a`: `uv run --frozen pytest packages/debate_core/tests/application/caselist/test_residue_clearing_gaps.py -n 4 -p no:randomly --no-cov` → `11 failed, 5 passed`. (1): `test_one_that_names_nothing_removed_is_cleared_by_the_same_removal_run_again` failed with `assert '09de22b5…' not in ['c1658cef…', '09de22b5…']`, the old version still there after the re-run; the survivors test failed the same way. (2): `test_its_aggregate_residue_is_cleared_by_the_same_removal_run_again` failed with `assert [] == ['parsed/testcl26/2026.10.10-docx-2/index.jsonl']`, no aggregate planned. **Green** (now 25 tests): for (1), status counts `manifest 1`; the same `--source` request re-run deletes that version; status then has no older version and is in sync. For (2), Oak Ridge/LmNo's `--team` request withdraws one shared file and removes nothing; status counts `index.jsonl 1` older than `RM-2026-11`; the same `--team` command run again plans that index and deletes it; status is in sync; and the copy in `testcl26` stays for Maple Grove/QX and Cedar Hollow/ZaLu. **What survives the sweep**, each by its own test: the current version (and a store that lists an old version as current), the rewrite, a version newer than it, one in the same second, a delete marker, the week never rewritten, the camp release's manifest, a key that only begins with the rewritten one (`….jsonl.bak`), a key whose rewrite the bucket no longer holds, and another request's or another environment's rewrite. |
| **ac2**: (3) a dry run whose execution would sweep a version says so in a plan line | PASS | **Red**, `6e7520a`: the core test `assert not True` on `plan.nothing_to_do`. Through the command, `tests/smoke/test_caselist_remove_smoke.py::test_an_old_manifest_version_alone_is_counted_by_the_dry_run_and_cleared_by_its_execution` failed with `'Nothing is left to remove' is contained here`. **Green**: the dry run prints `MANIFEST VERSIONS SWEPT from the bucket by --execute: 1 noncurrent version(s) of 1 manifest(s).`, then `  bucket manifests/testcl26/<date>.jsonl  (1 version(s))` and *TO CARRY IT OUT*. In core, the two rules are counted once each. The execution deletes exactly the versions the dry run counted. A manifest the re-run rewrites again is not counted twice. A plan with nothing to sweep is still *nothing left*. A sweep the profile may not list is *not counted*, and never *nothing left*. Renderer tests on hand-built plans pin the line, the per-manifest counts and the not-counted wording. |
| **ac3**: (4) a snapshot with a manifest mismatch and suppressed rows gets the removal hint and not the publish hint | PASS | **Red**, `6e7520a`: `uv run --frozen pytest packages/debate_cli/tests/test_caselist_publish.py -k TestStatusHintsTheRemoval` → `4 failed, 2 passed`. The failures were assertions: the publish hint was present (`'caselist publish --caselist' is contained here`), the new sentence was absent. The two that passed are the cases the publisher uploads, whose hint was already right. **Green**: with a suppressed row and a mismatch in 2026-09-15, the message reads `… testcl26 2026-09-15 (manifest mismatch, 1 suppressed row(s))`. The hint has no `caselist publish --caselist` and says *A manifest mismatch in testcl26 2026-09-15 is not cleared by a publish … Finish the removal first*. With 2026-09-01 mismatched too, both hints appear. A test parametrised over nothing, a suppressed row, a held row and a held skipped row runs status, then the publish, and asserts the removal hint appears exactly when the publish withholds the manifest. |
| **ac4**: (5) status names the caselist a withdrawn file's residue belongs to, from the withdrawal record, and says *not attributed* for an earlier build's removal | PASS | **Red**, `6e7520a`: the re-run test failed with `assert ['58c7fff5…'] == []`, the copy still in the bucket. The status tests failed at the missing field (`AttributeError`), which I do not count as red evidence; mutants A1 to A10 show those tests bite. **Green**: `RM-2026-07` withdrew the Bayview revision from `testcl26` and kept it in `testclb26`, and a current object of it is back under `testcl26`. Status gives `WithdrawnCopy(sha256=<revision>, request_id="RM-2026-07", current_objects=1)` under `testcl26`, nothing under `testclb26`, and `in_sync` stays true. With `withdrawals.jsonl` gone from both places: `withdrawals_not_attributed == ("RM-2026-07",)` and nothing named. A caselist another holder keeps the file in (Oak Ridge's copy in `testcl26`) reports nothing. A withdrawn row still on this machine is no holder. An un-suppressed withdrawal is not reported. The same removal run again takes the copy, for a caselist and for a camp path. The table line reads `WITHDRAWN COPIES LEFT in testcl26: … of 1 file(s) withdrawn from testcl26 (sha256 <12>, RM-2026-07).`, the JSON `withdrawn_copies_left` and `withdrawals_not_attributed`, and neither names a whole digest, path, school, team code or file name. |
| **ac5**: (6) a recorded smoke check, against the installed build and `s3_stand_in`, shows a rewritten manifest named as a manifest mismatch with its publish hint, a suppressed row, and a clean status after the publish | PASS | `tests/smoke/test_caselist_publish_smoke.py::test_status_names_a_rewritten_manifest_and_a_suppressed_row_and_is_clean_after_the_publish`, recorded in `tests/smoke/README.md`. **Red**, `6e7520a`, on the workspace build: every step the start build has passed (mismatch, publish hint, clean after the publish, suppressed row), then `KeyError: 'withdrawals_not_attributed'`. **Against an installed build**: before the sync, I exported the branch at `6b4fccc` (rebased by the sync to `b6326db`, the same changes on the newer `dev`) with `git archive`, stamped it with `scripts/stamp_build.py stamp --version 1.1.0.dev900 --tag v1.1.0-dev.900 --channel dev`, built both wheels offline (`check-wheels`: publishable), and installed them with `uv tool install --offline --managed-python --python 3.12` into a scratch tool directory outside the checkout. `debate-research --version --json` reported commit `6b4fccc…` on channel `dev`. `DEBATE_SMOKE_BIN=<that binary> DEBATE_SMOKE_EXPECT_SHA=<HEAD> uv run --frozen pytest tests/smoke/test_caselist_publish_smoke.py tests/smoke/test_caselist_remove_smoke.py -m "not live and not in_process"` → `35 passed in 70.92s`. What it shows: a manifest rewritten here is `(manifest mismatch)` with `caselist publish --caselist testcl26` in the hint and `differs` in the table; after that publish the status exits 0 and is in sync. Then a disclosure suppressed on the bucket's copy of the list, as a removal from another machine leaves it, is `(1 suppressed row(s))`, with the removal runbook in the hint, no publish hint, and `withdrawals_not_attributed: ["RM-2026-01"]`. That snapshot rewritten too gets *not cleared by a publish* and no publish hint. Nothing identifying is printed. After the sync both files passed again on the workspace build, inside the full suite below. `validate-dev` runs them against the pre-release after the merge. |
| Node `residue-gaps`: `uv run pytest packages/debate_core/tests/application -k "removal or status or residue"` | PASS | `355 passed in 35.81s`, run as the spec writes it (330 on the start commit). |

### Mutation runs

The driver is a scratchpad script.

* **Each mutant** is one textual change to committed source. The driver refuses a dirty tree and a
  target that is not there exactly once.
* **Each run** has a new, empty `HYPOTHESIS_STORAGE_DIRECTORY` (working agreement 8; none of these
  tests is a Hypothesis property). It runs under `perl -e 'alarm 110'` with
  `-n 6 -p no:randomly -p no:cacheprovider --no-cov`.
* **Restoring** is from a byte copy, then the driver checks the file's sha256 and `git diff --quiet`.
* **The selection**: this task's core and renderer tests; t15's residue tests; t11's later-upload
  plan tests; t16's holder tests; the removal service tests; and the two status classes of the CLI
  publish tests. That is 116 tests at the end, 13 to 40 s a run.
* **Validity.** No mutant failed at collection, and every catch is a failing assertion.

The final pass ran all 40 on `fe4a583`. No source file changed after it, only tests and the phase.

| # | Mutation | Result (final pass) | First failing test |
|---|---|---|---|
| **The sweep's key guard** | | | |
| K1 | A key the run rewrites now is swept by the new rule too | CAUGHT, 1 failed | `test_a_manifest_the_plan_rewrites_again_is_counted_as_rewritten_and_not_swept` |
| K2 | Another request's rewrites are this request's | CAUGHT, 1 failed | `test_a_key_only_another_requests_or_environments_run_rewrote_is_not_this_requests[another request]` |
| K3 | Another environment's rewrites are this one's | CAUGHT, 1 failed | the same, `[another environment]` |
| K4 | A listing of the key's prefix is taken as the key's | CAUGHT, 1 failed | `test_a_key_that_only_begins_with_the_rewritten_one_is_another_key` |
| K5 | No earlier rewrite is swept (the rule before this task) | CAUGHT, 3 failed | `test_a_plan_whose_execution_would_sweep_a_version_is_not_nothing_left` |
| C1 | The rule that reads each version names nothing | CAUGHT, 3 failed | the same |
| **The sweep's version guard** | | | |
| V1 | Older *or the same moment* as the rewrite | CAUGHT, 2 failed | `test_a_version_stamped_in_the_same_moment_as_the_rewrite_is_not_older_than_it` |
| V2 | Newer than the rewrite instead of older | CAUGHT, 3 failed | `test_a_plan_whose_execution_would_sweep_a_version_is_not_nothing_left` |
| V3 | The current version is swept too | CAUGHT, 1 failed | `test_a_version_the_store_lists_as_current_is_kept_whatever_its_time` |
| V4 | A delete marker is swept too | CAUGHT, 1 failed | `test_a_delete_marker_older_than_the_rewrite_is_left` |
| V5 | A rewrite the bucket no longer holds is taken as the current version | CAUGHT, 1 failed | `test_a_rewrite_the_bucket_no_longer_holds_orders_nothing_and_sweeps_nothing_of_its_key` |
| **The dry run's line** | | | |
| D1 | A plan with versions to sweep is nothing to do | CAUGHT, 4 failed | `test_a_sweep_the_profile_may_not_list_is_not_counted_and_never_nothing_left` |
| D2 | A sweep not counted is nothing to do | CAUGHT, 2 failed | the same |
| D3 | The dry run counts no sweep | CAUGHT, 3 failed | the same |
| D4 | A refused listing counted as nothing to sweep | CAUGHT, 1 failed | the same |
| D5 | The plan prints no sweep line | CAUGHT, 1 failed | `test_a_plan_whose_execution_would_sweep_versions_counts_them_by_manifest` |
| D6 | The line counts versions as manifests | CAUGHT, 1 failed | the same |
| **The hint rule** | | | |
| H1 | The publish hint names a caselist whose manifest is withheld | CAUGHT, 3 failed | `test_a_manifest_mismatch_with_a_suppressed_row_gets_the_removal_hint_and_not_the_publish_hint` |
| H2 | No hint to finish the removal first | CAUGHT, 4 failed | the same |
| H3 | Status never asks the publisher | CAUGHT, 4 failed | the same |
| H4 | Status restates the rule, suppressed rows only | CAUGHT, 1 failed | `test_the_hint_is_the_removals_exactly_when_the_publish_withholds_the_manifest[a held row]` |
| H5 | Status restates the rule, held skipped rows added | CAUGHT, 1 failed | the same, `[a held skipped row]` |
| **The attribution** | | | |
| A1 | No withdrawal is attributed | CAUGHT, 4 failed | `test_a_copy_withdrawn_from_a_caselist_another_holder_keeps_is_not_reported` |
| A2 | A withdrawal no record attributes is not named | CAUGHT, 1 failed | `test_a_withdrawal_an_earlier_build_made_is_not_attributed` |
| A3 | A caselist that still holds the file is reported | CAUGHT, 1 failed | `test_a_copy_withdrawn_from_a_caselist_another_holder_keeps_is_not_reported` |
| A4 | A suppressed row on this machine counts as a holder | CAUGHT, 1 failed | `test_a_withdrawn_row_still_on_this_machine_is_no_holder_of_the_copy` |
| A5 | A whole file's entry in force is read as a withdrawal | CAUGHT, 2 failed | `test_a_withdrawal_since_unsuppressed_is_not_reported` |
| A6 | A withdrawal since lifted is still attributed | CAUGHT, 1 failed | the same |
| A7 | The residue check counts no withdrawn copy | CAUGHT, 3 failed | `test_a_withdrawn_row_still_on_this_machine_is_no_holder_of_the_copy` |
| A8 | Status gives the residue check no withdrawals | CAUGHT, 3 failed | the same |
| A9 | The table prints no withdrawn-copy line | CAUGHT, 2 failed | `test_the_table_names_its_caselist_its_request_and_twelve_characters` |
| A10 | The clean line printed beside a withdrawn copy left | CAUGHT, 1 failed | the same |
| **The re-run's withdrawal record** | | | |
| R1 | No re-planned withdrawal gets its recorded caselists | CAUGHT, 4 failed | `test_the_same_removal_run_again_takes_it` |
| R2 | A recorded caselist's aggregates are not planned | CAUGHT, 1 failed | `test_its_aggregate_residue_is_cleared_by_the_same_removal_run_again` |
| R3 | A recorded caselist's copy is not planned | CAUGHT, 1 failed | `test_the_same_removal_run_again_takes_it` |
| R4 | The record may have a file removed whole | CAUGHT, 1 failed | `test_it_never_has_a_file_removed_whole` |
| R5 | A copy a holder keeps is planned again | CAUGHT, 1 failed | t11's `test_a_second_source_under_the_same_request_does_not_plan_the_first_again` |
| R6 | Another request's withdrawals are this request's | CAUGHT, 1 failed | `test_another_requests_withdrawal_of_the_same_file_is_not_this_requests` |
| R8 | A file the record alone names is skipped as shared | CAUGHT, 2 failed | `test_the_same_removal_run_again_takes_it` |
| R9 | No camp year's copy planned for a recorded camp withdrawal | CAUGHT, 1 failed | `test_status_names_it_under_openev_and_the_same_removal_run_again_takes_it` |

40 of 40 caught on the final pass. Getting there took eight changes:

- **K1, K4, R6 and R9 survived first; each was a missing test**, and the test was written:
  - the dry run's count for a key rewritten again;
  - a key that only begins with the rewritten one;
  - another request's withdrawal of the same file;
  - the camp-path case.
- **Three checks could decide nothing, so they were removed, as working agreement 8 says:**
  - the sweep's `version_id != rewrite` (strictly older already keeps the rewrite, and V1 now
    shows the strictness bites);
  - status's `disclosure is None` (A5, first form: a whole entry is passed over by the whole-source
    check while in force, and by the in-force check once lifted);
  - the planner's "still suppressed" on recorded withdrawals (R7: a recorded caselist only joins a
    file this plan withdraws again under the same request).
- **R5 was caught by t11's own test on its first run.** That is how I found the first form of the
  `--source` re-plan was wrong: it re-planned a copy another path keeps.

The first-pass times and results are in the scratchpad log, and the table gives the final pass only.

### Checks CI runs

On the synced branch, `b935530` plus this branch.

| Command | Result |
|---|---|
| `uv run --frozen pytest -n auto -m "not slow and not live" --part K/8`, K = 1 to 8 | `1027`, `1032`, `1029 passed, 2 warnings`, `1022 passed, 1 warning`, `1018`, `1025 passed, 1 xfailed`, `1 failed, 1026 passed`, `1025 passed, 1 xfailed`. 8204 passed in all. The one failure is the parser evaluation's, which comes from `dev` (Summary, item 4) |
| `ruff format --check .` / `ruff check .` | `800 files already formatted` / `All checks passed!` |
| `uv run --frozen pyright` | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen lint-imports` | `Contracts: 12 kept, 0 broken.` |
| `uv run scripts/check_thin_handlers.py` | `OK: 22 CLI command and API route handlers within 25 statements` |
| `uv run scripts/docs_index.py --check-descriptions` | `All 35 indexed documents under docs/ have a description` |
| `uv run scripts/check_links.py` | `OK: 1646 relative links and anchors in 245 Markdown files` |
| `uv run scripts/check_command_blocks.py --base origin/dev` | OK, this report included |
| `uv run scripts/validate_specs.py` | `OK: 366 files, 38 epics, 308 tasks, 20 releases` |

**Why eighths.** I ran the suite in quarters before the sync: `--part 1/4` passed 2029 in 101 s.
Part 2 then hit its hard stop when the load average reached 73 from another session. The plugin
deals `(crc32(file) % N + index) % N`, so quarter K is exactly eighths K and K+4. I ran eighths
from there, and the synced run in eighths throughout. Before the sync it was 8138 passed, 1 skipped
and 2 xfailed, with no failure.

### Nothing an earlier build cannot read

This task adds no stored file, field or line shape. The new things are `RemovalPlan` and
`PlannedSource` fields in memory, and two top-level keys in `caselist status --json`.

- **This build writes the same records.** `WRITE_STORED_SUPPRESSION_LISTS=this-build` regenerated
  t13's `written_by_this_build/`. With moto's random version ids masked, every line was identical.
  I restored the committed files.
- **`v1.1.0-dev.18` reads them**, the build the installed agent runs. I exported it with
  `git archive v1.1.0-dev.18` and ran `check_an_older_build_reads_this_builds_files.py` with that
  source first on `PYTHONPATH`, after the sync:

  ```text
  reader: the debate_core source at dev18
  placed: suppression/path-holds.jsonl, suppression/removal-log.jsonl, suppression/removal-scopes.jsonl, suppression/suppression-list.jsonl, suppression/withdrawals.jsonl, s3://<bucket>/manifests/_suppression/… (the same five)
  list read: 3 whole file(s) and 2 disclosure(s) suppressed
  knows of path holds: True
  import of the next week: SUPPRESSED 4, completed
  publish: succeeded True; status in sync: True
  status with the residue check: completed; caselists checked: openev, testcl26
  removals not checked: 0
  ```

  The second and third checks printed what they print for every older build: a path entry in the
  list and a caselist in the scope record are each refused. Those are the shapes this task does
  not add. The same check with this branch's source printed the same lines.
- **The check needed one change to this branch's test code.** It runs this checkout's `conftest.py`
  against the older source, so `RemovalWorld.planner()` passes the removal log only to a planner
  that takes one (`b6326db`).

## Files changed

- **`debate_core.application`**
  - `caselist/manifest_sweep.py` (new): the sweep's two rules, shared by the dry run and the
    execution. Its module docstring says what it never takes.
  - `caselist/removal_plan.py`:
    - `PlannedSource.withdrawn_earlier_from`, and `RemovalPlan.earlier_rewrites` and
      `superseded_versions`;
    - `RemovalPlan.swept_from()`, and `names_removed()`, moved here from the service;
    - `nothing_to_do` counts the sweep, and `touched_caselists` the recorded caselists;
    - the planner takes the removal log (required), reads the scopes and the withdrawal record, and
      re-plans a withdrawal from the record;
    - `_objects` plans a recorded caselist's copy, aggregates and, for `openev`, every year;
    - module docstring, "Re-running".
  - `caselist/removal_service.py`: the sweep goes through `plan.swept_from(access.versions)`.
    Docstring step 2.
  - `caselist/removal_residue.py`: `WithdrawnCopy`, `CaselistResidue.withdrawn_copies`, the count,
    and a docstring section.
  - `caselist/status_service.py`:
    - `SnapshotStatus.manifest_withheld`, asked of `build_publish_plan`;
    - `CaselistStatusReport.withdrawals_not_attributed` and `withdrawn_copies_left`;
    - the attribution, and two docstring sections.
  - `caselist/publish_plan.py`: the `withholding_rows` docstring says status asks it. No code.
  - `caselist/suppression.py`: `read_withdrawals()`.
- **`debate_cli`**
  - `commands/caselist_remove.py`: the *MANIFEST VERSIONS SWEPT* line, the re-planned withdrawal's
    line, and a docstring section.
  - `commands/caselist.py`: the withheld-manifest hint, the two status lines, the two JSON keys, and
    the docstring.
  - `container.py`: the planner gets both copies of the removal log, everyday profile.
- **Tests**
  - New: `test_residue_clearing_gaps.py` (25) and `commands/test_caselist_residue_clearing_output.py`
    (9).
  - `test_caselist_publish.py`: 6 hint tests.
  - `conftest.py`: the planner's removal log.
  - `tests/smoke/test_caselist_publish_smoke.py`: one check.
  - `tests/smoke/test_caselist_remove_smoke.py`: one test rewritten (Deviation 3).
  - `tests/smoke/README.md`: two rows.
- **Docs**
  - `docs/runbooks/caselist-removal.md`: the residue section's two new lines, the dry run's sweep
    line, how a withdrawal-only request is cleared, the two cases still left to you, and *What the
    report does not see*.
  - `docs/runbooks/caselist-backfill.md`: the drift row.
- **Spec**: the phase.

## Deviations from the spec

1. **Withdrawn-copy residue does not change the exit code.** It is something a removal left in the
   bucket, as a removed file's residue is, and that fails `caselist status` as `REMOVAL_RESIDUE`.
   But status has never reported it, so failing on it would change the exit code for a bucket that
   exits 0 today, and the forbidden list forbids that. It is reported in the text and the JSON, as
   t21's held rows are, and not part of `in_sync`. While one is shown, the clean line is not
   printed. PM question 1.
2. **(4): a held skipped row gets the publish hint today.** Your notes say the removal hint's case
   "includes held rows and held skipped rows". The publisher withholds a manifest for a suppressed
   or held row, and not yet for a held skipped row (t22 Decision 5; your ruling put that in
   `v1-e30-t23`, which I stayed out of). Status asks the publisher's rule as you asked, so the
   hint is what the publish then does. `test_the_hint_is_the_removals_exactly_when_the_publish_withholds_the_manifest`
   holds the two together for all four cases. When t23 extends `withholding_rows`, the
   held-skipped-row case flips with it. That test's hand-written `withheld_by_this_build` for that
   case then becomes `True`.
3. **One earlier task's smoke test was rewritten, because (3) reverses its premise.**
   `test_an_old_manifest_version_alone_is_cleared_by_executing_a_plan_that_says_nothing_is_left`
   (t15) asserted the dry run said *Nothing is left to remove*. It is now
   `…_is_counted_by_the_dry_run_and_cleared_by_its_execution`, asserting the sweep line, and was the
   red run for ac2 through the command. The runbook's reference was updated.
4. **Two commits were made with a check failing**, both because I piped a check into `tail` inside
   an `&&` chain:
   - `645a594`: a docstring line too long for ruff, fixed in `e5a0579`;
   - `fbd056b`: two pyright errors in a test, fixed in `a3b81f7`.

   No run reported here was made at either. Since then the checks run without pipes.

## Decisions and assumptions

1. **(1) Older than the rewrite, by the store's time, strictly.**
   - The rewrite is the version the scope records. A version older than it is one the run's purge
     should have taken, so status counts it, and it belongs to a key the removal rewrote: inside the
     forbidden list.
   - Strictly older keeps the rewrite itself, and a version stamped in the same second (S3 states
     times to the second).
   - Where the bucket no longer holds the rewrite, nothing of that key is swept: nothing can be
     shown older than it.
   - Every run of the request counts, stopped or completed: a scope records a rewrite only after its
     purge.
   - Another request's or environment's rewrites are not this request's (the same separation as
     t15's `completed_removals`).
   - The current version is never swept, though no reachable S3 state makes one older than the
     rewrite. A store whose order and times disagree is tested.
2. **(2) Which record, and why it is enough: the withdrawal record.**
   - **Why the record.** The suppression list holds a disclosure digest, which is one-way and names
     no caselist. A scope names a run's caselists, not a file's, and is written last, after the
     deletions. The withdrawal record names each withdrawn copy's caselist by file and request. It
     is written just before the suppression entry it attributes (t16 Decision 2), so every copy a
     build since t16 withdrew is in it.
   - **What is recovered.** The team's *paths* are recovered from nothing: the first run deleted the
     records and rows, and no record holds a path, by policy. Clearing needs the caselist, not the
     path, and the re-run plans exactly what the first run did for that caselist: its aggregates,
     and its copy when no other holder there keeps the file.
   - **Why it is enough for what status reports.** Status reports aggregate residue against a
     request only for a caselist its scope names. For a withdrawal-only request those are its
     withdrawals' caselists. Status's withdrawn-copy residue is attributed by the same record.
   - **The gap.** A build between t15 and t16 wrote a scope and no withdrawal record. Its re-run
     plans nothing for that caselist, and the plan says *no withdrawal record names the caselist*.
     Prod has had no removal, and dev's only one, RM-2026-90, is from before t15.
3. **A `--source` re-run re-plans a withdrawn later upload from the record** only when a copy is
   still in a caselist the record names that keeps no holder of it, and only as a withdrawal, never
   a whole-file removal. It is needed so the same `--source` command clears what (5) reports. Two
   tests hold it:
   - t11's "a second `--source` under one request does not plan the first again" (R5);
   - `test_it_never_has_a_file_removed_whole` (R4).
4. **(3) The dry run now reads noncurrent manifest versions,** with the everyday profile, which
   holds `s3:ListBucketVersions` and `s3:GetObjectVersion` (`operator_access.tf`). The execution
   read them already. It costs a download per noncurrent version of each affected caselist's
   manifests, on every dry run that plans anything. That cost on the real corpus is unmeasured
   (Follow-up 3).
5. **No new key in the plan's JSON.** ac2 asks for a plan line. `v1-e30-t20` adds the plan JSON's
   `withdrawals` key, and the count could go beside it (Follow-up 4).
6. **(4) Per snapshot, as the publisher decides.** A caselist with one publishable mismatch and one
   withheld gets both hints, the removal one naming the withheld snapshots. Status asks the plan of
   one snapshot, from the listing it already made, and no extra request is made.
7. **(5) A caselist keeps a holder where a manifest of it on this machine names the file at a path
   the list does not stop.** That is the removal's own `kept_in`, from the rows status reads. A
   whole-removed file stays the residue check's own. A withdrawal since lifted is not reported. For
   `openev`, a release keeping the file is a holder, so a camp copy is reported only when no
   release holds it, and then the re-run plans every year's copy.
8. **Status still never uses the takedown profile and never downloads.** The attribution reads the
   withdrawal record under `manifests/_suppression/` (one more `GetObject` there) and this machine's
   manifests. t15's smoke test, which asserts the only objects status reads are under
   `manifests/_suppression/` and that it lists with the everyday profile alone, passes unchanged.

## Operator follow-ups

None blocks the merge. After the merge, one read-only status in each environment, as you asked.
They use your everyday profiles, so they are yours to run. Run them from this task's worktree
before `scripts/task finish`, or afterwards from any checkout of `dev` that has the merge. Each
takes a few seconds per caselist.

**Dev:**

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e30-t19-residue-clearing-gaps
aws sso login --profile debate-dev-evidence
DEBATE_ENV=dev uv run debate-research caselist status
```

**Prod**, against the dev data directory, as the removal runbook says:

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e30-t19-residue-clearing-gaps
aws sso login --profile debate-prod-evidence
DEBATE_ENV=prod DEBATE_STORAGE__DATA_DIR="$HOME/.debate-research/dev" uv run debate-research caselist status
```

What each result means, in dev and in prod:

- **The clean line**, *No version of a removed file is left … (N caselist(s) checked)*. Nothing to
  do.
- **A dev status that exits 1 with `CASELIST_DRIFT` naming `testcl26`.** That caselist is kept by
  your decision, and is not this task's concern. A manifest mismatch there now says
  *Finish the removal first* only if that snapshot has a suppressed or held row.
- ***Manifest and aggregate versions NOT CHECKED against RM-2026-90*** (dev): expected, as since
  t15.
- ***Withdrawals NOT ATTRIBUTED to a caselist: RM-2026-90*** (dev): expected if that synthetic
  exercise withdrew a copy. It means what is left of those copies is not checked, not that nothing
  is. Prod should show none: it has had no removal.
- ***REMOVAL RESIDUE in …*** or ***WITHDRAWN COPIES LEFT in …***: something to clear. Paste the
  lines under the table back. They hold caselists, roles, counts, digest prefixes and request ids
  only. Then clear it as below, in the environment that reported it, dev before prod.

**Clearing residue: the removal run again, operator-run only, with the takedown profile.** Look up
the request's removal-log line. It holds sha256 values, counts and codes only:

```bash
grep '"request_id":"RM-2026-NN"' "$HOME/.debate-research/dev/suppression/removal-log.jsonl"
```

Put the request id the residue line names in place of `RM-2026-NN`. Then set three variables in
the same shell, once per clearing. `REQUEST_ID` is that id and `REASON` the line's `reason`. For a
line with a `removed_sha256`, `SELECTOR` is `--source` and `VALUE` is one of those sha256 values.
For a withdrawal-only line, `SELECTOR` is `--team` and `VALUE` is the team as the register
records it, `<caselist>/<school>/<team code>`. Keep the single quotes: a school name has spaces.

```bash
export REQUEST_ID=RM-2026-NN REASON=REQUESTED_BY_TEAM SELECTOR=--source VALUE='the-sha256-or-the-team'
```

The dry run, with the everyday profile. Check its plan as the runbook's step 4 says. A plan for a
withdrawal-only request names each file *withdrawn earlier from `<caselist>`* and lists that
caselist's aggregates. A plan that the sweep acts in prints *MANIFEST VERSIONS SWEPT*. Neither
should say *Nothing is left to remove*:

```bash
DEBATE_ENV=dev uv run debate-research caselist remove "${SELECTOR}" "${VALUE}" --request "${REQUEST_ID}" --reason "${REASON}"
```

Then the execution, with the takedown profile, and the status again, which should exit 0 with the
clean line:

```bash
aws sso login --profile debate-dev-evidence-removal
DEBATE_ENV=dev DEBATE_REMOVAL_PROFILE=debate-dev-evidence-removal uv run debate-research caselist remove "${SELECTOR}" "${VALUE}" --request "${REQUEST_ID}" --reason "${REASON}" --execute
DEBATE_ENV=dev uv run debate-research caselist status
```

If its plan listed a `parsed/<caselist>/<version>/index.jsonl`, rebuild that caselist's aggregates
as the removal runbook's step 5 says. In prod the commands are the same with three changes:
`DEBATE_ENV=prod`, the `debate-prod-evidence-removal` profile, and `--confirm-prod` after
`--execute`. Every prod `caselist status` runs with
`DEBATE_STORAGE__DATA_DIR="$HOME/.debate-research/dev"`. Two results mean stop and tell the PM,
and delete nothing by hand:

- a manifest count that stays after the re-run;
- a plan that says *no withdrawal record names the caselist it was withdrawn from*.

## Follow-up work

1. **PM question 1: should a withdrawn copy's residue fail `caselist status`?** (E30.) See
   Deviation 1.
2. **When `v1-e30-t23` makes the publisher withhold a manifest for a held skipped row**, the hint
   follows with no code change here. The hint test's hand-written `BESIDE_THE_REWRITE["a held
   skipped row"]` in `test_caselist_publish.py` must then become `True`, and the test fails until
   it does. That is how t23 will see that the hint moved with it.
3. **The dry run's sweep cost on the real corpus is unmeasured** (E30). The operator's next dry run
   in dev will show it.
4. **The plan's JSON could carry the sweep's count** (E30, `v1-e30-t20`'s area), beside its new
   `withdrawals` key.
5. **The parser evaluation's PR-subset baseline** (E31). Since `#308` the gate test fails on `dev`
   for want of a baseline. That is not this task's, but `ci` on this PR, and on every PR into
   `dev`, will show it until the baseline is committed.
6. **The data-use policy needs no change.** No record was added, and the two new status lines name
   caselists, digest prefixes and request ids only.

### PM questions

```text
v1-e30-t19 asks the PM, 2026-10-18:

1. caselist status now names what is left of a copy withdrawn from a caselist that keeps no
   holder of it (WITHDRAWN COPIES LEFT, by caselist, digest prefix and request). It does not
   change the exit code, because the spec forbids changing any exit code status returns, and today
   such a bucket exits 0. Options:
   (a) leave it as reported, outside the exit code (done);
   (b) make it fail as REMOVAL_RESIDUE, exit 1, like a removed file's residue, in a small E30 task
       that lifts that one forbidden entry.
   Recommendation: (b). It is a removal left unfinished, and the same removal run again clears it;
   a status that exits 0 over it lets the scheduled checks miss it.

2. The parser evaluation gate test fails on dev since #308 (labels committed, no pr-subset
   baseline). Every PR into dev will show it in ci until a baseline is written and committed with a
   coach-reviewed report. Who runs scripts/run_parser_eval.py --write-baseline, and when?
```

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-18

**Notes:**

Accepted, with the phase `Succeeded`. One gap between status and the sweep is found below. It
goes to a follow-up task rather than holding the merge, because no removal so far can reach it.

**The work itself:**

* **Red first, and honest about what counts as red.** An `AttributeError` on a missing field is
  not counted as red evidence, and mutants A1 to A10 are used to show those tests bite instead.
* **The sweep is one function** shared by the dry run and `--execute`, so the count the dry run
  prints is the set the execution deletes. There is a test for that.
* **Its guards are each pinned by their own test:** the current version, the rewrite, newer, same
  second, delete markers, a prefix-only key, a rewrite no longer held, and another request or
  environment.
* **40 of 40 mutants caught.** The four that first survived each led to a missing test, and three
  checks that decided nothing were removed.
* **The hint asks the publisher's own rule.** The hint therefore cannot drift from what the
  publish does, and the test over the four row kinds ties the two together.
* **The smoke check ran against an installed, stamped build.** `v1.1.0-dev.18` reads this build's
  files.

**Rulings:**

* **Deviation 1, and PM question 1: (b).** A withdrawn copy left in the bucket is an unfinished
  removal, the same as a removed file's residue. It should fail `caselist status` as
  `REMOVAL_RESIDUE`. A new E30 task in the next PM batch lifts that one forbidden entry.
  *Withdrawals NOT ATTRIBUTED* stays reported and outside the exit code, like *NOT CHECKED*: it says
  what was not looked at, not that something was found.
* **Deviation 2, held skipped rows get the publish hint until t23:** accepted. Following the
  publisher's rule is what the notes asked for, and the notes' wording ran ahead of t22's
  publisher. Follow-up 2 goes into `v1-e30-t23`'s notes: t23 flips
  `BESIDE_THE_REWRITE["a held skipped row"]`.
* **Deviation 3, t15's smoke test rewritten:** accepted. (3) reverses its premise.
* **Deviation 4, two commits with a failing check:** accepted. No reported run was made at either,
  and running checks without pipes is the right lesson.
* **Decisions 1 to 8:** accepted. Decision 2's gap (a build between t15 and t16) holds no real
  removal: prod has had none, and dev's RM-2026-90 predates t15.
* **PM question 2, the parser-evaluation gate:** a correction first. The gate does not fail in
  `ci`. `_run_real_tier` skips wherever there is no path map or digest key, and by policy neither
  reaches a runner. It fails only on the operator's Mac, where the corpus is. The PR subset (six
  files) has been fully corrected since `#308`, and the baseline is not written yet. The baseline is
  written at the labelling finish (step 6 of the labels guide): three coach reviews, then
  `scripts/run_parser_eval.py --write-baseline`, run by the operator. Until then, task sessions
  treat that one failure as known and do not investigate it. It goes in the PM notes.

**A gap for the new task: status can count a manifest version the sweep never takes.** For a
manifest the run rewrote:

* status counts a noncurrent version other than the rewrite if it is older than *the run's
  completion minus 15 minutes* (`removal_residue._older_versions`);
* the sweep takes it only if it is strictly older than *the rewrite*
  (`manifest_sweep.older_than_their_rewrite`).

So a version stamped between the rewrite and completion minus 15 minutes is counted, never swept,
and "can always be cleared" fails for it. Examples are a version in the same second as the rewrite,
or a publish from another machine during the run. It can only happen when a run carries on more than
15 minutes after its own rewrite, which no removal so far has done. That is why this is accepted
now.

The new task makes the two one rule:

* one predicate, shared by status and the sweep, for completed runs;
* the property tested over the fixture states: after the same removal runs again, status counts no
  manifest version. The states include a run that carries on more than 15 minutes past its rewrite,
  and a same-second version.

Narrowing status to the sweep's rule is not the fix. Status cannot read a version's contents, so it
would stop reporting a version in that window that names a removed file.

**Follow-ups:**

* 1: the new E30 task (above).
* 2: `v1-e30-t23`'s notes.
* 3: shown by the operator's next dev dry run.
* 4: added to `v1-e30-t20`.
* 5: covered by PM question 2.
* 6: noted.

### Operator follow-ups run, 2026-10-18 (recorded by the PM)

The read-only `caselist status` after the merge, from a detached worktree of `origin/dev` holding
this task:

* **Dev:** *No version of a removed file is left under raw/ or parsed/, and no manifest or
  aggregate version is older than a removal that touched its caselist.* *Manifest and aggregate
  versions NOT CHECKED against RM-2026-90*, as expected since `v1-e30-t15`. No *Withdrawals NOT
  ATTRIBUTED* line: RM-2026-90 withdrew no copy. No *REMOVAL RESIDUE* or *WITHDRAWN COPIES LEFT*.
  Exit 1 for `CASELIST_DRIFT` on `testcl26` alone (5 snapshots), the caselist kept by the operator's
  decision.
* **Prod**, against the dev data directory: the same clean line, 4 caselists checked,
  `removals_not_checked: []`, every `removal_residue` entry empty. Exit 1 for `CASELIST_DRIFT` only:
  the 2026-10-13 week unpublished in prod for hsld26, hspf26 and hspolicy26, and openev 2026-ld (2
  files). Prod lags dev until the next promotion; not this task's.
* The drift panel printed the whole details record, about 1,000 lines of sha256. Filed as item (4)
  of `v1-e30-t24`.

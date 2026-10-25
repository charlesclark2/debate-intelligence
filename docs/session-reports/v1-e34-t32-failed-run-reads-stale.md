# Session report: v1-e34-t32-failed-run-reads-stale

| | |
|---|---|
| Task | `v1-e34-t32-failed-run-reads-stale` — The staleness hook reports a caselist stale when its latest run failed |
| Spec | [`plan_specs/v1/e34-caselist-sync/t32-failed-run-reads-stale.yaml`](../../plan_specs/v1/e34-caselist-sync/t32-failed-run-reads-stale.yaml) |
| Epic / release | `v1-e34-caselist-sync` / `v1.1` |
| Branch | `task/v1-e34-t32-failed-run-reads-stale` |
| Session status | COMPLETE |

## Summary

v1-e34-t03's staleness hook (`LandscapeStalenessCheck`) has a third rule. When the latest run that
listed the caselist ended in failure, the caselist reads stale and the banner names the run's id
and its failed stage. A later run that listed the caselist and did not fail clears it. This is the
record v1-e32-t05's cap-bound rule already reads (`SyncRunLog.latest_listing`), so the two rules
can never disagree about which run is "latest", and both are found with one read of the log. The
snapshot-age and cap-bound rules are unchanged. The report's banner, `stale=true` in the CSV
header and the "Data freshness" row all read the hook, so none of them gained code.
**Look at Question 1 first.** The PM's rule ("the latest run that listed the caselist", reason
"run id and failed stage") does not cover a run that *raised*: an expired caselist_token, a provider
error while listing, a refused start. Such a run lists no archive and records no stage. The code
follows the rule as written, a test pins that behaviour, and the question gives the options.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `failed-run-stale` (Failed run reads stale) | Done | Red then green, 11 mutants all caught; the node's criterion passes. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: with synthetic run logs, the hook reports stale when the latest run that listed the caselist failed, names the run id and stage, reports current after a later success; another caselist's failed run changes nothing; tests shown failing first | PASS | Red at `626dc70`: `.venv/bin/python -m pytest packages/debate_core/tests/application/test_landscape_staleness.py packages/debate_core/tests/application/test_landscape_run.py -p no:randomly -n 0` → **8 failed, 41 passed**, each red an `AssertionError` (list below). Green at `2d00be0`, same command → **49 passed**. Tests: `test_a_failed_latest_run_makes_a_fresh_snapshot_stale_naming_the_run_and_its_stage`, `test_a_later_successful_run_makes_it_current_again`, `test_a_failed_run_of_another_caselist_does_not_make_this_one_stale`, `test_a_successful_run_of_another_caselist_does_not_make_this_one_current`, plus the seven listed under Decisions. |
| ac2: a landscape report built over a failed latest run carries the stale banner and `stale=true`, by test through v1-e32-t05's run service | PASS | `test_a_failed_latest_run_makes_the_report_stale_and_a_later_success_clears_it` (in `test_landscape_run.py`, on `synthetic26`): the run service's `report.header.stale` is true, `report.md` starts with the banner and names `20260916T060000Z` and the download stage, and `positions.csv` has `# stale=true`. After a later successful run is appended: not stale, no banner, `# stale=false`. Red at `626dc70`, green at `2d00be0`. |
| Node `failed-run-stale`: Staleness tests pass (`uv run pytest packages/debate_core/tests -k stale`) | PASS | `.venv/bin/python -m pytest packages/debate_core/tests -k stale -q` → **44 passed in 22.42s**. A `--co` count confirms all 12 new tests are in the selection. |

**The red run, by test** (each an `AssertionError` or a false `assert`, against a skeleton with the
new field and type, where `latest_run_failed` is always `False` and `check()` never sets the field):

* `test_a_failed_latest_run_makes_a_fresh_snapshot_stale_naming_the_run_and_its_stage`: `latest_run_failed` false
* `test_a_successful_run_of_another_caselist_does_not_make_this_one_current`: `failed_run` is `None`
* `test_a_failed_run_of_both_caselists_makes_each_stale`: `latest_run_failed` false
* `test_a_failed_publish_pending_run_changes_nothing`: the earlier failed run is not seen
* `test_a_run_with_no_end_recorded_never_flips_the_hook`: the earlier failed run is not seen
* `test_when_every_rule_applies_the_banner_names_each`: `latest_run_failed` false
* `test_the_reason_names_no_school_and_no_path_from_the_stage_details`: no "failed at its import stage."
* `test_a_failed_latest_run_makes_the_report_stale_and_a_later_success_clears_it`: `report.header.stale` false

The other four new tests passed at red by design. Each is a case that must change nothing: a later
success, another caselist's failed run, an `incomplete` run, and a run that raised before listing.
The mutants below are what show those four bite.

**Mutants** (11, each against the two test files, `-n 0 -p no:randomly`, no Hypothesis in these
tests; the file was restored from the commit after each):

| Mutant | Result | Caught by |
|---|---|---|
| `stale` ignores a failed run | caught (3 failed) | the fresh-snapshot test, the redaction test, ac2's test |
| The banner omits the failed-run sentence | caught (4) | the fresh-snapshot, all-rules, redaction and ac2 tests |
| The `SyncStage` name filter is removed | caught (1) | the redaction test (a stage named `Harrowgate Prep`) |
| The sentence uses the stage's reason in place of its name | caught (7) | the redaction test and six others |
| `incomplete` counts as failed | caught (1) | `test_a_run_that_failed_only_after_publishing_is_not_a_failed_run` |
| Every stage is named, failed or not | caught (7) | the stage-naming assertions |
| The hook reads the newest record, whether it listed the caselist or not | caught (5) | the other-caselist tests, publish-pending, the raised run, redaction |
| The hook reads the newest record naming the caselist in `caselists` | caught (1) | `test_a_run_that_stopped_on_an_error_before_listing_changes_nothing` |
| The hook reads the first failed listing ever, not the latest | caught (4) | the cap-bound tests (t05's and t03's) and ac2's clearing half |
| Two stages joined with a comma alone | caught (1) | the all-rules test |
| The cap-bound count is zeroed when the run failed | caught (1) | the all-rules test |

**Before the report** (agreement 10):

* `uv run scripts/affected_tests.py` → **156 of 450 test files (34.7%)**, 49 of them `debate_cli`
  tests reached through the container. On this machine (load average 10 to 15) that would be over
  the two-minute line, so I did not run it and leave it to the PR's `ci` check. It was 222 files
  while I had a docstring edit in `sync_runs.py`, so I reverted that edit (`547a779`) and measured
  again. Within the two minutes I ran:
  * the changed module's test directory: `.venv/bin/python -m pytest packages/debate_core/tests/application -n auto -m "not slow and not live" -q` → **3457 passed in 84.74s**;
  * the always-run list plus the hook's readers (the renderer, the golden landscape files via
    `test_render.py`, the CLI's landscape command): `.venv/bin/python -m pytest tests/architecture tests/specs packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py packages/debate_cli/tests/test_landscape_command.py packages/debate_core/tests/arguments/landscape -n auto -m "not slow and not live" -q` → **810 passed in 25.29s**.
* `uv run --frozen ruff check .` → All checks passed. `uv run --frozen ruff format --check .` → 1247 files already formatted.
* `uv run --frozen pyright packages/debate_core` → 0 errors, 0 warnings, 0 informations.
* `uv run --frozen lint-imports` → Contracts: 16 kept, 0 broken. `scripts/check_thin_handlers.py` → OK (no handler touched).
* `uv run --frozen python scripts/validate_specs.py` → OK: 437 files, 40 epics, 375 tasks, 22 releases (after setting the phase to Succeeded).

## Files changed

* `packages/debate_core/src/debate_core/application/landscape_staleness.py`: the third rule.
  `FailedSyncRun` (run id and failed stage names) and its one sentence, `_failed_run_of`, the
  `failed_run` field, `latest_run_failed`, and `stale` and the banner reading it. `check()` reads
  `latest_listing` once for both run-log rules, where t05's `_awaiting` read it itself. The module
  docstring states the rule and what changes nothing.
* `packages/debate_core/tests/application/test_landscape_staleness.py`: ac1's eleven tests.
* `packages/debate_core/tests/application/test_landscape_run.py`: ac2's test through the run service.
* `plan_specs/v1/e34-caselist-sync/t32-failed-run-reads-stale.yaml`: phase Succeeded.

## Deviations from the spec

1. **The spec says "the E39 pilot's freshness line" reads the hook. Nothing in the repo does.**
   `git grep -l "LandscapeStalenessCheck\|landscape_staleness"` finds the landscape report and
   run service, the testing helpers and two scripts. Neither the search pilot (`search_index_holder`,
   whose "freshness" is its five-minute index re-read, ADR-0019) nor `site/` reads it. I added no
   reader, because the brief says none gains code of its own. When an E39 freshness line is built
   on the hook, it gets this rule unchanged. Question 3.

## Decisions and assumptions

**What a run record can carry** (counted from `SyncRunRecord`, `record_for_summary`,
`record_for_failure`, `_outcome_of` and `SyncRunMonitor.watch`). Every record has `finished_at`
(required by the schema) and one of six outcomes:

| Outcome | Written by | Lists the caselist? | This rule |
|---|---|---|---|
| `completed` | a summary | yes, when select listed its archives | clears |
| `nothing_new` | a summary | yes (also a rate-limited select, which lists nothing) | clears when listed |
| `cap_deferred` | a summary | yes | clears this rule; t05's rule makes it stale |
| `publish_pending` | a summary: publish, parse, search index or report pending a login | yes for a pull; never for `--publish-pending` (`caselists=()`) | clears when listed |
| `incomplete` | a summary: a required stage succeeded, and parse, search_index, landscape, report or retention failed | yes | clears (Question 2) |
| `failed`, from a summary | a download, import or publish stage failed. Select never records FAILED: it completes, is skipped when rate limited, or raises | yes for a pull (select had listed the archives); never for `--publish-pending` | **stale**, naming the failed stages |
| `failed`, raised | `record_for_failure`: the pull raised. An expired caselist_token, a provider error while listing, the run lock (`SyncRunInProgress`), `NoCaselistsConfigured`, `FullArchiveRefused`, a store refused (`LocalStoreAccessDenied`, `ManifestsNotWritable`), the API not turned on, a bucket that cannot be built (v1-e34-t22), or any bug. `stages=()`, `deferred_by_caselist={}`, `error_class` set | no | changes nothing (Question 1) |

**What a killed run leaves behind.** `SyncRunMonitor.watch` writes a record only when the pull
returns or raises an `Exception`. A run killed by SIGKILL or by launchd's SIGTERM (no handler is
installed anywhere in `packages/*/src`), or stopped by Ctrl-C or a cancellation (`BaseException`,
which the monitor does not catch), leaves **no record**. It also leaves no details line, no bucket
object, no per-run summary JSON (written after the lock is released) and no notification. In the
run log it looks like nothing at all: the newest line is the run before it. What it does leave is
the lock file (the kernel drops the `flock`, so the next run is not blocked), the download ledger's
entries for the bulk downloads it started, files in the inbox, and whatever it had imported. That
can include new local manifests, so the snapshot-age rule may already see the newer snapshot. A
line with no `finished_at`, or one cut off mid-append, fails validation and `SyncRunLog.read` skips
it with a warning. So such a run never flips the hook in either direction, and
`test_a_run_with_no_end_recorded_never_flips_the_hook` pins both lines. Whether a killed Mac run
needs a rule of its own is the PM's to decide. Nothing in this log could drive one: a run that
never finished is visible only as the absence of a record for its scheduled week. (For a cloud
run, v1-e40-t05's alarms cover a run that dies.)

**"Ended in failure" is the outcome `failed`** (`record.succeeded` false), the run log's own word.
It is what `caselist runs`, the exit status and the "needs a person" notification already use. An
`incomplete` run captured and published the snapshot, so the data the other rules read is in place.

**"Listed the caselist" is t05's meaning**, the caselist being in `deferred_by_caselist`
(`latest_listing`). This gives the PM's "a run that never listed the caselist changes nothing" for
another caselist's run and for `--publish-pending`. It also means both run-log rules read the same
record. A failed run is a run-level failure: the record does not say which caselist's archive
failed, so a failed run over two caselists makes both stale
(`test_a_failed_run_of_both_caselists_makes_each_stale`).

**The reason text.** The banner gains one sentence: "The latest sync run of this caselist,
`<run id>`, failed at its `<stage>` stage." With two stages it says "at its download and publish
stages", and with no failed stage recorded just "failed". The run id is held by the schema to
`^\d{8}T\d{6}Z$`. A stage is named only when it is one of `SyncStage`'s values, so a stage string
in the log that no build writes is not repeated, and a stage's `reason` is never read.
`test_the_reason_names_no_school_and_no_path_from_the_stage_details` builds a log whose stage
reasons hold a fictional school (`Harrowgate Prep`) and a disclosure-shaped path, and one with a
stage literally named `Harrowgate Prep`. It checks the banner and the CSV metadata for the school,
its parts, the path, `.docx` and `/`. When several rules apply, the banner's sentences name each:
age, the cap's backlog, then the failed run (`test_when_every_rule_applies_the_banner_names_each`).

**The CSV header block is unchanged apart from `stale=`.** Adding a key such as `failed_run=`
would change `tests/fixtures/landscape/golden/*.csv`, which is outside this task's packages. The
CSV carries `stale=true`, as ac2 asks, and the banner carries the reason.

**`_awaiting` became a module function over the record `check()` already read.** t05's rule is the
same, and its tests (`test_a_cap_bound_run_makes_a_fresh_snapshot_stale`,
`test_a_later_run_that_fetched_the_backlog_makes_it_current_again`,
`test_a_run_the_download_cap_held_back_makes_the_report_stale`) pass unchanged.

## Questions for the PM

```text
PM questions from v1-e34-t32-failed-run-reads-stale (failed run reads stale). Code is committed;
these do not block the criteria, which pass as written.

1. A run that RAISED is not covered by the rule as written.
   Facts: SyncRunMonitor.watch records a pull that raised with record_for_failure: outcome
   "failed", stages=(), deferred_by_caselist={}, caselists = the requested slugs, error_class set.
   Causes: expired caselist_token (policy E34 gate 5), a provider error while listing (anything
   but rate limiting), the run lock (SyncRunInProgress), a refused start (API not turned on,
   bucket adapter unbuildable), a store refused, FullArchiveRefused, or a bug. Such a run listed
   no archive and has no stage, so "the latest run that listed the caselist" passes over it and
   the reason "run id and failed stage" has no stage to name. Today an expired-token weekly run
   still reads Current until the snapshot ages out (pinned by
   test_a_run_that_stopped_on_an_error_before_listing_changes_nothing).
   Options:
   (a) Keep the rule as written. Notifications already announce these runs.
   (b) Also count a raised run whose `caselists` names the caselist, except a SyncRunInProgress
       refusal (the run holding the lock is the one that counts). Reason: "<run id> stopped
       before its stages (<error class>)". The error class is a class name, never a message.
       About 15 lines and 3 tests, in this module only.
   (c) As (b), with the lock refusal counting too.
   Recommendation: (b). An expired token is the likeliest way a weekly run "fails outright", which
   is the case the spec's description opens with. The class name is safe (no message is read), and
   excluding the lock keeps a harmless second launch from flipping the report.

2. An "incomplete" run (required stages fine; parse, search index, landscape, report or retention
   failed) does not count as failed. That is the run log's own definition of failure. A landscape
   report built after a failed parse can trail the newest manifest, but that is about which
   snapshot the report reads, not this hook's rule.
   Recommendation: keep it so; reply only if incomplete should read stale.

3. FYI, a Deviation: the spec names "the E39 pilot's freshness line" as a reader of the hook.
   Nothing in the repo reads LandscapeStalenessCheck except the landscape report, its run service
   and two scripts. I added no reader. Recommendation: amend the description, or file the reader
   with E39 when it is wanted.

4. FYI, follow-up: `debate-research landscape report` prints its own status line from the hook's
   fields (debate_cli/commands/landscape.py:434), "STALE: newest snapshot ..., N day(s) old, 0
   archive(s) awaiting download.", and its JSON has no failed-run field. For a failed run it says
   STALE without the reason. debate_cli is outside this task's packages. Recommendation: a small
   E34 or E32 task to print FailedSyncRun.sentence() there.

Reply with: 1 (a|b|c), 2 (keep|stale), and whether 3 and 4 become spec edits or tasks.
```

## Operator follow-ups

None. The affected set (156 files) runs in the PR's `ci` check (agreement 10).

## Follow-up work

* The CLI's `landscape report` status line and JSON should name the failed run (Question 4;
  `packages/debate_cli`, E32 or E34).
* If Question 1 is answered (b) or (c), a run that raised before listing gets a rule of its own,
  in `landscape_staleness.py` only.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

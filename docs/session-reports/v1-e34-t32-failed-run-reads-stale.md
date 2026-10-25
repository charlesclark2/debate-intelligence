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
can never disagree about which listing run is "latest". (Since ruling 1 the failed-run rule also
weighs a later run that stopped naming the caselist, and the log is read once for each rule.) The
snapshot-age and cap-bound rules are unchanged. The report's banner, `stale=true` in the CSV
header and the "Data freshness" row all read the hook, so none of them gained code.
**The PM's condition is closed (ruling 1, (b)).** A run that *raised* before listing anything (an
expired caselist_token, a provider error while listing, a refused start) also counts, when its
record's `caselists` names the caselist and it is later than the latest listing run. The banner
says "`<run id>`, stopped before its stages (`<error class>`)". The class is named only when it is
an identifier, and the error's message is never read. A run the run lock refused
(`SyncRunInProgress`) changes nothing. A later run that listed the caselist and did not fail clears
it. Shown red first; the PM's four mutants and four more are all caught. Nothing came out
differently from the ruling. One test was added beyond the condition's list: a mutant reading the
cap-bound count from the stopped run, rather than the latest listing, survived until it existed.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `failed-run-stale` (Failed run reads stale) | Done | Red then green, 11 mutants all caught; the node's criterion passes. |
| PM condition: ruling 1 (a run that raised reads stale) | Done | Red at `2c20e43` (8 failed), green at `fa450fd`, one more test at `0d2c148`; the 4 named mutants and 4 more all caught. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: with synthetic run logs, the hook reports stale when the latest run that listed the caselist failed, names the run id and stage, reports current after a later success; another caselist's failed run changes nothing; tests shown failing first | PASS | Red at `626dc70`: `.venv/bin/python -m pytest packages/debate_core/tests/application/test_landscape_staleness.py packages/debate_core/tests/application/test_landscape_run.py -p no:randomly -n 0` → **8 failed, 41 passed**, each red an `AssertionError` (list below). Green at `2d00be0`, same command → **49 passed**. Tests: `test_a_failed_latest_run_makes_a_fresh_snapshot_stale_naming_the_run_and_its_stage`, `test_a_later_successful_run_makes_it_current_again`, `test_a_failed_run_of_another_caselist_does_not_make_this_one_stale`, `test_a_successful_run_of_another_caselist_does_not_make_this_one_current`, plus the seven listed under Decisions. |
| ac2: a landscape report built over a failed latest run carries the stale banner and `stale=true`, by test through v1-e32-t05's run service | PASS | `test_a_failed_latest_run_makes_the_report_stale_and_a_later_success_clears_it` (in `test_landscape_run.py`, on `synthetic26`): the run service's `report.header.stale` is true, `report.md` starts with the banner and names `20260916T060000Z` and the download stage, and `positions.csv` has `# stale=true`. After a later successful run is appended: not stale, no banner, `# stale=false`. Red at `626dc70`, green at `2d00be0`. |
| Node `failed-run-stale`: Staleness tests pass (`uv run pytest packages/debate_core/tests -k stale`) | PASS | `.venv/bin/python -m pytest packages/debate_core/tests -k stale -q` → **44 passed in 22.42s**. A `--co` count confirms all 12 new tests are in the selection. After the condition, at `0d2c148`: **54 passed in 6.52s**. |
| PM condition (ruling 1): a raised run naming the caselist reads stale with the class name; a later listing that did not fail clears it; a `SyncRunInProgress` refusal changes nothing; a raised run naming another caselist changes nothing; an error class that is not an identifier is left out | PASS | Red at `2c20e43`, same two-file command as ac1 → **8 failed, 50 passed**, all `AssertionError` (list below). Green at `fa450fd` → **58 passed**; at `0d2c148` → **59 passed**. Tests in order: `test_a_run_that_stopped_on_an_error_naming_the_caselist_makes_it_stale`, `test_a_later_run_that_listed_the_caselist_clears_a_run_that_stopped`, `test_a_run_the_lock_refused_changes_nothing`, `test_a_run_that_stopped_naming_another_caselist_changes_nothing`, `test_an_error_class_that_is_not_an_identifier_is_left_out` (five classes: the fictional school, the disclosure path, `Expired-Token`, empty, `1Expired`), plus `test_the_class_is_named_and_the_message_is_not` and `test_a_run_that_stopped_after_a_cap_bound_run_leaves_the_backlog_counted`. |

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
The mutants below are what show those four bite. (The PM's ruling 1 replaced the last of these;
see the condition's red run below.)

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
| The hook reads the newest record naming the caselist in `caselists` | caught (1) | `test_a_run_that_stopped_on_an_error_before_listing_changes_nothing` (since replaced: ruling 1 makes most of this the rule) |
| The hook reads the first failed listing ever, not the latest | caught (4) | the cap-bound tests (t05's and t03's) and ac2's clearing half |
| Two stages joined with a comma alone | caught (1) | the all-rules test |
| The cap-bound count is zeroed when the run failed | caught (1) | the all-rules test |

**The condition's red run** (`2c20e43`), a skeleton with `FailedSyncRun`'s two new fields and no
behaviour. Each failure is an `AssertionError`:

* `test_a_run_that_stopped_on_an_error_naming_the_caselist_makes_it_stale`: `stale` false
* `test_a_run_that_stopped_naming_another_caselist_changes_nothing`: the other caselist's `failed_run` is `None`
* `test_an_error_class_that_is_not_an_identifier_is_left_out`, all five: `failed_run` is `None`
* `test_the_class_is_named_and_the_message_is_not`: no banner

Passing at red by design, because the old code ignores every raised run:
`test_a_later_run_that_listed_the_caselist_clears_a_run_that_stopped` and
`test_a_run_the_lock_refused_changes_nothing`. The mutants show both bite.

**The condition's mutants** (each against the same two test files, `-n 0 -p no:randomly`, file
restored after each, `git status` clean afterwards). The PM's four come first:

| Mutant | Result | Caught by |
|---|---|---|
| The lock refusal counted | caught (1) | `test_a_run_the_lock_refused_changes_nothing` |
| The error message used in place of the class | caught (8) | the stopped-run tests, all five non-identifier cases, `test_the_class_is_named_and_the_message_is_not` |
| `caselists` ignored | caught (1) | `test_a_run_that_stopped_naming_another_caselist_changes_nothing` |
| The raised rule winning over a later success (latest stopped run first, listing runs after) | caught (1) | `test_a_later_run_that_listed_the_caselist_clears_a_run_that_stopped` |
| The identifier filter removed | caught (5) | the five non-identifier cases |
| The hook reads the newest record, listed or not (re-aimed at the new lookup) | caught (6) | the other-caselist tests and others |
| The hook reads the first failed listing ever (re-aimed) | caught (3) | the clearing tests |
| The cap-bound count is zeroed when the run failed (re-aimed) | caught (2) | the all-rules test and the backlog test |
| The cap-bound count read from the deciding record, not the latest listing | **survived at `fa450fd`**, caught (1) at `0d2c148` | `test_a_run_that_stopped_after_a_cap_bound_run_leaves_the_backlog_counted`, added for it |

The first session's other seven mutants were run again on the new code, and all were caught. Their
anchor text still matched.

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

**Again after the condition** (at `0d2c148`):

* The affected set is still 156 files. Load had dropped to about 4, so I tried it once:
  `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest $(cat affected.txt) -n auto -m "not slow and not live" -q`
  hit the alarm at 1:55, unfinished, and left no workers behind (`pgrep` found none). So it is over
  two minutes even on a quiet machine, and it stays with the PR's `ci` check.
* The module's test directory → **3467 passed in 91.90s**. The always-run list plus the hook's
  readers (same command as above) → **810 passed in 22.48s**.
* ruff check: all checks passed. ruff format --check: 1247 files already formatted. pyright on
  `packages/debate_core`: 0 errors. lint-imports: 16 kept, 0 broken. validate_specs: OK, 437 files.

## Files changed

* `packages/debate_core/src/debate_core/application/landscape_staleness.py`: the third rule.
  `FailedSyncRun` (run id and failed stage names) and its one sentence, `_failed_run_of`, the
  `failed_run` field, `latest_run_failed`, and `stale` and the banner reading it. `check()` reads
  `latest_listing` itself and hands it to `_awaiting`, which had read it on its own in t05. The module
  docstring states the rule and what changes nothing. For ruling 1: `FailedSyncRun` gains
  `stopped_before_stages` and `error_class`, and `_stopped_naming` and `_latest_run_of` choose
  between the latest listing run and a later run that stopped naming the caselist. `check()` gives
  the cap-bound count `latest_listing` and the failed-run rule `_latest_run_of`.
* `packages/debate_core/tests/application/test_landscape_staleness.py`: ac1's tests (the pinned
  "changes nothing" test replaced by ruling 1's), and the condition's seven test functions.
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
| `failed`, raised | `record_for_failure`: the pull raised. An expired caselist_token, a provider error while listing, the run lock (`SyncRunInProgress`), `NoCaselistsConfigured`, `FullArchiveRefused`, a store refused (`LocalStoreAccessDenied`, `ManifestsNotWritable`), the API not turned on, a bucket that cannot be built (v1-e34-t22), or any bug. `stages=()`, `deferred_by_caselist={}`, `error_class` set | no, but its `caselists` names the slugs it was asked for (`[]` for `--publish-pending`, `caselist_pull.py:192`) | **stale** when `caselists` names it and it is later than the latest listing, "stopped before its stages (`<class>`)"; a `SyncRunInProgress` refusal changes nothing (ruling 1) |

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

**A run that stopped on an error (ruling 1).** The rule reads the latest record that either listed
the caselist or stopped naming it. "Stopped naming it" means outcome `failed`, `error_class` set,
not `SyncRunInProgress`, and the caselist among `caselists`. A raised record lists no archive, so
the two kinds never overlap. When that record is a stopped run, the banner says "The latest sync
run of this caselist, `<run id>`, stopped before its stages (`<class>`)." It ends at "stages."
when the class is not an identifier (`str.isidentifier()`). `error_message` is never read, even
though a `DomainError`'s message is already redacted. The cap-bound count still comes from
`latest_listing` alone, so a stopped run after a cap-bound run leaves the backlog in the banner
beside the stopped run. A `--publish-pending` run that raises passes no caselists, so it never
counts, as before.

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

Answered by the PM, 2026-10-24 (see PM review):

1. A run that raised: **(b)**, implemented as the condition (above).
2. `incomplete` runs: **keep**. They do not read stale.
3. The E39 freshness line: the PM amends the description in the next batch.
4. The CLI's status line and JSON: folded into `v1-e32-t12-landscape-cli-seven-files`, with no new
   task. It prints `FailedSyncRun.sentence()`, and the JSON gains the run id and stages, or the error
   class (`FailedSyncRun.error_class`).

No open questions.

## Operator follow-ups

None. The affected set (156 files) runs in the PR's `ci` check (agreement 10).

## Follow-up work

* The CLI's `landscape report` status line and JSON name the failed run: folded by the PM into
  `v1-e32-t12-landscape-cli-seven-files` (ruling 4).

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED, with one condition to close in this session
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-24

**Notes:**

A small rule done properly.
* The outcomes a run record can carry were counted from the code before choosing, as asked, and
  the table is the clearest account of the run log we have.
* What a killed run leaves behind is answered: no record at all, so it can never flip the hook.
* Both run-log rules now read the one record (`latest_listing`), so they cannot disagree about which
  run is latest.
* The reason names only a schema-held run id and `SyncStage` values. A stage literally named after a
  school is not repeated.
* 11 mutants were caught, and the four tests that pass at red by design are shown to bite.

**Rulings**

1. **(b).** Count a run that raised, when its record's `caselists` names the caselist, except a
   `SyncRunInProgress` refusal. The run holding the lock is the one that counts, and a second launch
   must not flip the report. The reason is "`<run id>` stopped before its stages (`<error class>`)".
   It is the class name only, never the message, and the class name passes the same kind of filter
   as the stage names: it must be an identifier, or it is left out. This is the condition below.
   An expired token is the likeliest way a weekly run fails outright, which is the case this task
   exists for.
2. **Keep it.** An `incomplete` run captured and published its snapshot, and the run log does not
   call it failed.
3. **The PM amends the description** in the next batch: no E39 freshness line reads the hook today,
   and the sentence goes. If one is built, it reads the hook unchanged.
4. **No new task.** The PM folds it into `v1-e32-t12-landscape-cli-seven-files`, which already
   changes that command's output: the status line prints the hook's failed-run sentence, and the
   JSON gains the failed run's id and stages, or its error class.

**Accepted as made:**
* "ended in failure" is the `failed` outcome;
* "listed" in t05's meaning;
* a run-level failure makes every caselist it listed stale;
* the CSV header changed only by `stale=`;
* `_awaiting` made a module function;
* the deviation about E39 (ruling 3).

**A killed Mac run leaves no record.** Nothing in this log could drive a rule for it. A missed week
shows only as an absent record. Recorded here, with no task for now. For the cloud run,
`v1-e40-t05`'s late-run alarm covers it.

**Condition, to close in this session (no re-review needed):**

* **Implement ruling 1** in `landscape_staleness.py`, with tests shown failing first:
  * a raised run naming the caselist reads stale with the class name;
  * a later run that listed the caselist and did not fail clears it;
  * a `SyncRunInProgress` refusal changes nothing;
  * a raised run naming another caselist changes nothing;
  * an error class that is not an identifier is left out of the sentence.
* **Mutants, each caught:** the lock refusal counted; the error message used in place of the class;
  `caselists` ignored; the raised rule winning over a later success.
* Update `test_a_run_that_stopped_on_an_error_before_listing_changes_nothing` to the new behaviour,
  and update the summary, Decisions and Questions here. Commit.

If anything comes out differently, stop and ask for another review.

## PM review, second

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-24

**Notes:**

The condition is closed as ruled.
1. **The rule.**
   * A raised run whose `caselists` names the caselist, later than the latest listing, reads stale:
     "stopped before its stages (`<class>`)".
   * The class is named only when `str.isidentifier()`, and `error_message` is never read.
   * A `SyncRunInProgress` refusal and a `--publish-pending` raise change nothing.
   * A later listing that did not fail clears it.
2. **Red, then green.** The red run shows 8 `AssertionError`s. Both pass-at-red tests are shown to
   bite. The PM's four mutants and four more were caught, and the first session's seven still
   catch on the new code.
3. **The extra test is right, and it is accepted.** The surviving mutant read the cap-bound count
   from the stopped run, so the session added a test, and the backlog now stays counted from
   `latest_listing` beside a stopped run.
4. **The affected set** (156 files) hit the alarm even on a quiet machine, so it stays with the
   PR's `ci`, under agreement 10.

Nothing else changes from the first review. The Goal is `Succeeded`. The PM's next batch amends the
description (ruling 3) and folds ruling 4 into `v1-e32-t12`.

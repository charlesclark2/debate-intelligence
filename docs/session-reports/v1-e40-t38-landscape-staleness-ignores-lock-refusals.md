# Session report: v1-e40-t38-landscape-staleness-ignores-lock-refusals

| | |
|---|---|
| Task | `v1-e40-t38-landscape-staleness-ignores-lock-refusals` — A lock refusal is not reported as a run that stopped before its stages |
| Spec | [`plan_specs/v1/e40-cloud-caselist-run/t38-landscape-staleness-ignores-lock-refusals.yaml`](../../plan_specs/v1/e40-cloud-caselist-run/t38-landscape-staleness-ignores-lock-refusals.yaml) |
| Epic / release | `v1-e40-cloud-caselist-run` / `v1.8` |
| Branch | `task/v1-e40-t38-landscape-staleness-ignores-lock-refusals` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The landscape's staleness check now skips any record of a pull the run lock refused. That covers
another runner's live lease (`RunLockHeld`), the lock held for good by the move of the weekly run's
home (`RunHomeMoved`) and a lock naming another home (`RunLockWrongHome`). The local lock
(`SyncRunInProgress`) was already skipped. The report's freshness now comes from the last run that
ran: current, cap-bound or failed, as that run left it. A run that held the lock and then failed
(`RunLockLost`, `RunTerminated`) still reads "stopped before its stages". The change is one rule in
`landscape_staleness.py`, under a public `LOCK_REFUSALS` set. The `STALE:` line and `--json`'s
`staleness` key show the hook's result unchanged, so they follow it with no CLI change.

**What dev's landscape reads today** (read-only, from the local copies, no AWS call): **current** for
hsld26, hspf26 and hspolicy26. The cloud run's three records since the cutover are all runs that ran,
and none is a refusal. By design none can be, because a refused record stays on the machine that was
refused. Details are [below](#what-devs-landscape-reads-today).

The Goal is set to `Succeeded`.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `landscape-staleness-ignores-lock-refusal` (Staleness ignores refusals) | Done | Tests red at `2393538`, the rule at `196d277`; 11 mutants, all caught |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1**: a lock refusal leaves the landscape's staleness as the last real run made it, while a run that failed after starting still reads stopped, by tests shown failing first | PASS | **Red** at `2393538`, source unchanged: `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests/application/test_landscape_staleness.py -n 0 -p no:randomly -q --tb=line` → `8 failed, 31 passed`. Every failure was an assertion that read the refusal as the latest run. For example, `assert FailedSyncRun(run_id='20260918T060000Z', stages=(), stopped_before_stages=True, error_class='RunLockHeld') is None`, and the failed run's `FailedSyncRun(... stages=('download',))` was expected where the refusal's came back. The new tests that passed at red were the `SyncRunInProgress` cases (exempt before this task) and the guards `RunLockLost` and `RunTerminated` (they must read stopped before and after). **Green** at `196d277`: the same command → `39 passed in 0.40s` |
| Node: Staleness ignores refusals tests pass (`uv run pytest packages/debate_core/tests -k staleness`) | PASS | `.venv/bin/python scripts/hard_stop.py 115 uv run --frozen pytest packages/debate_core/tests -k staleness -q` → `39 passed in 30.57s` |

### The tests

All of them are in `packages/debate_core/tests/application/test_landscape_staleness.py`. Each record
is written by `record_for_failure`, the function the monitor uses, from a real refusal built with
invented values: holder run id `20260918T055500Z`, task `invented-task-7f3e`, build `v0.0.0-x`, lock
file `invented-sync.lock`, and a move dated 2026-09-10.

| Test | What it pins |
|---|---|
| `test_a_lock_refusal_after_a_completed_run_leaves_the_report_as_that_run_made_it[×4]` | After a completed run, a refusal leaves the report current: no banner, `stale=false`. After a cap-bound completed run, the 2 deferred archives are still counted and there is no "stopped" sentence |
| `test_a_lock_refusal_after_a_failed_run_leaves_it_failed[×4]` | After a run that failed at its download stage, and after one that stopped on `CaselistAuthExpired`, a refusal leaves that run as the failed run. The refusal's class is never in the banner |
| `test_a_run_that_failed_after_it_started_still_reads_stopped[RunLockLost, RunTerminated]` | Both read "stopped before its stages (<class>)". `RunLockLost` is the lock's own error and its record stays local too, which is why it is pinned |
| `test_a_log_holding_only_lock_refusals_reads_as_no_run` | Four refusals, one of each class, give a `LandscapeStaleness` equal to the one from no run log at all |
| `test_refusals_after_a_failed_run_and_before_a_completed_one_change_nothing_either_way` | A run of four refusals is skipped back to the failed run, and a later completed run clears it |

The former `test_a_run_the_lock_refused_changes_nothing` covered `SyncRunInProgress` alone. Its two
cases (after a success, after a failure) are now the `SyncRunInProgress` cases of the first two tests.

### Mutation run

11 mutants on the refusal rule in `landscape_staleness.py`. The harness was a scratchpad script. It
applied each mutant, ran the staleness test file in one process (`-n 0 -p no:randomly`, under
`scripts/hard_stop.py 115`) with a new empty `HYPOTHESIS_STORAGE_DIRECTORY` each time (the file uses no
Hypothesis), and then restored the module from saved bytes and checked its SHA-256. The module matched
`HEAD` afterwards and `git status` was clean. Every catch was an assertion failure, not a crash.

| Mutant | Result | Caught by |
|---|---|---|
| 1. `RunLockHeld` left out of the refusals | CAUGHT (4) | its two parametrised cases, the refusals-only log, the run of refusals |
| 2. `RunHomeMoved` left out | CAUGHT (4) | the same, for `RunHomeMoved` |
| 3. `RunLockWrongHome` left out | CAUGHT (4) | the same, for `RunLockWrongHome` |
| 4. `SyncRunInProgress` left out | CAUGHT (4) | the same, for `SyncRunInProgress` |
| 5. The rule disabled (no refusal skipped: the old behaviour without even its one exemption) | CAUGHT (10) | every refusal case |
| 6. Every error class starting `Run` counted as a refusal | CAUGHT (2) | `..._still_reads_stopped[RunLockLost, RunTerminated]` |
| 7. `RunLockLost` counted as a refusal | CAUGHT (1) | `..._still_reads_stopped[RunLockLost]` |
| 8. A refusal as the latest record clears the whole history | CAUGHT (5) | the four after-a-failed-run cases, the run of refusals |
| 9. A refusal counted as the latest run, and as a run that did not fail | CAUGHT (5) | the same |
| 10. Only the last record skipped when refused, not a run of refusals | CAUGHT (2) | the refusals-only log, the run of refusals |
| 11. Refusals recognised by lower-cased text, and only the two "held" ones | CAUGHT (6) | the `RunHomeMoved` and `RunLockWrongHome` cases, the refusals-only log, the run of refusals |

Mutant 10 survived the first run. The harness had built it wrong: it kept the per-record filter, so the
mutant was the real code. I rebuilt it to drop the filter and skip only the last record, and it was
caught. The table gives the second run, which re-ran all 11.

Not run, because they are equivalent: dropping `not record.succeeded` from the refusal test (a
completed record never carries an error class), and skipping a refusal only when it names the caselist
(a refusal that names a different caselist matches nothing here anyway).

## What dev's landscape reads today

The PM asked what dev's landscape reads under the rule as built, from the cloud run's records since
the cutover, with no AWS call. I read two local copies, read-only:

* `~/.debate-research/dev-journey-copy`, a copy restored from the dev bucket. Its marker says it was
  restored at `2026-11-07T04:11:26Z` by `v1.1.0-dev.342`.
* `~/.debate-research/dev`, the Mac's data directory.

Their `caselist-sync-runs.jsonl` files are **byte-identical** (SHA-256 `62cc6277…5c4`, 18 records),
and so are their details files. Only ids, outcomes, error classes and caselist slugs were printed.

**The cloud run's records since the cutover:**

| Run | Outcome | What it was |
|---|---|---|
| `20261026T040426Z` | `incomplete` | The cutover's dev cloud run started by hand (`docs/data/caselist-cloud-run-comparison.md`) |
| `20261028T110536Z` | `completed` | The first scheduled dev cloud run. `t06`'s report has the schedule in dev from Wednesday 2026-10-28, 06:00 Chicago |
| `20261105T034547Z` | `completed` | The operator's hand run of the same task definition after ECS refused the 2026-11-04 launch (`v1-e40-t42`'s spec) |

**Refused records among them: none.** None of the 18 records, all of which are older, is a lock refusal
either. The only failed record, `20261021T110004Z` (`KeyringError`), is a Mac run that started. The
three cloud records have bucket details with no `held_by`. This is by design: every lock refusal is
`record_stays_local`, so it is written only on the machine that was refused. In the cloud that is the
container, which is discarded. The bucket's run log can never hold a refusal. That log is what a
restored copy holds and what `landscape report --restored-copy` reads (`v1-e40-t17`), and what the
weekly run's landscape stage will read once `v1-e40-t19` (still Pending) is built.

**What the check gives**, with `LandscapeStalenessCheck` over each copy's manifests and run log, report
date 2026-11-06 (scratchpad script, 0.4 s):

| Caselist | Stale | Newest snapshot | Age | Awaiting download | Failed run |
|---|---|---|---:|---:|---|
| hsld26 | no | 2026-11-03 | 3 days | 0 | none |
| hspf26 | no | 2026-11-04 | 2 days | 0 | none |
| hspolicy26 | no | 2026-11-03 | 3 days | 0 | none |

Both copies give the same answer. So does the pre-task rule, which I loaded from the start commit
`4377073` and ran over the same copy: with no refusal on record, both rules pick the same latest run.
**This task changes nothing in what dev reads today.** It matters where refusals are recorded, which is
the Mac's own run log:

* **While dev's cloud run holds the lock**, a Mac pull is refused with `RunLockHeld`, and that record
  lands in the Mac's log. Before this task, a landscape report or dry run without `--restored-copy`,
  which reads the Mac's data directory, then read
  "stopped before its stages (RunLockHeld)". Now it reads as the last run that ran left it.
* **After the move of the run's home to prod**, which has not happened (dev's schedule still ran on
  2026-11-04), every Mac pull is `RunHomeMoved`. Before this task, each one made the Mac's dev landscape
  read "stopped before its stages (RunHomeMoved)". Now the last dev run that ran decides. No dev run
  follows the move, so the report turns stale by age 9 days after dev's newest snapshot, and the banner
  gives the snapshot's age as the reason, not a refusal. That is `v1-e40-t29`'s follow-up 2, closed.

## Tests and checks run

| What | Command | Result |
|---|---|---|
| Red | above | `8 failed, 31 passed` |
| Green | above | `39 passed in 0.40s` |
| Node criterion | above | `39 passed in 30.57s` |
| Affected set | `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python scripts/affected_tests.py --run` | `147 of 717 test files (20.5%)` chosen; **stopped at its 115 s limit** (exit 124) at a load near 9. Under agreement 10 it is left to the pull request's `ci` check, with no hand-off |
| Instead, within the limit: every landscape file that reads staleness, the CLI's `STALE:` line and `--json`, the API pages, and the landscape smoke check | `pytest test_landscape_staleness.py test_landscape_run.py test_landscape_report.py test_landscape_restored_copy.py test_landscape_dry_run_text_caches.py debate_cli/tests/test_landscape_command.py debate_api/tests/test_landscape_pages.py tests/smoke/test_landscape_smoke.py -n auto -m "not slow and not live"` | `486 passed in 18.69s` |
| The always-run list | `pytest tests/architecture/ tests/specs/ debate_cli/tests/test_app.py test_help_rendering.py test_container_factories.py -n auto -m "not slow and not live"` | `378 passed in 21.50s` |
| Format and lint | `uv run --frozen ruff format --check .` / `uv run --frozen ruff check .` | `1997 files already formatted` / `All checks passed!` |
| Types | `uv run --frozen pyright packages/debate_core` | `0 errors, 0 warnings, 0 informations` |
| Import boundaries | `uv run --frozen lint-imports` / `uv run --frozen python scripts/check_thin_handlers.py` | `Contracts: 20 kept, 0 broken.` / `OK: 72 CLI command and API route handlers within 25 statements` |
| Specs | `uv run scripts/validate_specs.py` | `OK: 643 files, 41 epics, 580 tasks, 22 releases` |

## Files changed

* `packages/debate_core/src/debate_core/application/landscape_staleness.py`: the `LOCK_REFUSALS` set,
  `_refused_by_the_lock`, `_latest_run_of` skipping a refused record, `_stopped_naming` without its old
  single exemption, and the module docstring's rule.
* `packages/debate_core/tests/application/test_landscape_staleness.py`: the tests above. The old
  `SyncRunInProgress` test is folded into them.
* The task spec's phase.

## Deviations from the spec

None.

## Decisions and assumptions

* **A refusal is recognised by the error class its record carries.** That is all the record has, and
  the landscape reads the record only. `v1-e40-t29`'s `"skipped"` key is in the details, and only for
  `RunHomeMoved`.
* **A refused record is skipped entirely**, not just for the "stopped" rule. In practice it never lists
  archives, so this matters only as a guarantee that a refusal never decides the report.
* **Only the three refusals the spec names join `SyncRunInProgress`.** The lock's setup refusals keep
  reading stopped: an unseeded bucket (`RunStateNotSeeded`), an unreadable lock (`RunLockUnreadable`)
  and a seeded bucket in local mode (`BucketKeepsRunState`). They also did nothing, but they mean that
  no runner refreshes this store until a person acts, so "stale" with their class is true and useful.
  No test pins them either way. If the PM wants them skipped too, adding them to `LOCK_REFUSALS` is
  enough.
* **`RunLockLost` is pinned as a run, not a refusal.** It is the lock's own error and its record stays
  local as a refusal's does, but the run held the lock and began. A rule built on "the lock's errors" or
  `record_stays_local` would skip it, and mutants 6 and 7 show the tests catch that.
* **`LOCK_REFUSALS` is public**, so the refusal `v1-e40-t44` adds can join it (Follow-up 1).

## Operator follow-ups

None.

## Follow-up work

1. **`v1-e40-t44`'s refusal should join `LOCK_REFUSALS`** (that task, E40). Its spec has a scheduled
   pull refuse when the bucket's run log shows a recent start, "recording and announcing the refusal as
   a lock refusal is". If its record names a caselist and its class is not in `LOCK_REFUSALS`, the
   landscape will read "stopped before its stages" for it on the machine that recorded it. Adding the
   class to the set, with a case in `test_landscape_staleness.py`'s parametrisation, is enough.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-07

**Notes:**

One rule, pinned from both sides: the refusals are skipped, and the run that held the lock and then
failed is not.

1. **ac1 passes.** Red was 8 failed, each an assertion that read the refusal as the latest run; green
   39. Every record is written by the monitor's own `record_for_failure` from a real refusal built with
   invented values, so the tests read what production writes.
2. **Mutants.** All 11 are caught. Mutants 6 and 7, every `Run…` class and `RunLockLost` counted as a
   refusal, are the ones that matter, and they are caught. The harness error on mutant 10 is reported
   and its rebuilt mutant was caught. The two equivalent mutants are correctly set aside.
3. **What dev reads today is accepted as written:** current for the three followed caselists, and no
   change from the old rule, because the bucket's run log can never hold a refusal
   (`record_stays_local`). The task matters on the Mac's own log, and after the move of the run's home,
   which closes v1-e40-t29's follow-up 2. The session read only the run logs of the journey's restored
   copy and printed only ids, outcomes and classes, which is acceptable here. In future, ask before
   reading inside a restored copy.
4. **Decisions accepted.** The setup refusals (`RunStateNotSeeded`, `RunLockUnreadable`,
   `BucketKeepsRunState`) keep reading stopped, because each means no runner refreshes the store until
   a person acts. `LOCK_REFUSALS` is public.
5. **Follow-up 1:** the PM amends v1-e40-t44's spec in the next batch, so its refusal class joins
   `LOCK_REFUSALS` with a case in this file's parametrisation.
6. **Merge:** a plain `scripts/task pr` once `ci` is green. The Goal is `Succeeded`.

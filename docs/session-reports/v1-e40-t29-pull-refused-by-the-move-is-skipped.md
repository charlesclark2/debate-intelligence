# Session report: v1-e40-t29-pull-refused-by-the-move-is-skipped

| | |
|---|---|
| Task | `v1-e40-t29-pull-refused-by-the-move-is-skipped` — A Mac pull refused because the weekly run moved to prod is recorded as skipped, with its own notice |
| Spec | [`plan_specs/v1/e40-cloud-caselist-run/t29-pull-refused-by-the-move-is-skipped.yaml`](../../plan_specs/v1/e40-cloud-caselist-run/t29-pull-refused-by-the-move-is-skipped.yaml) |
| Epic / release | `v1-e40-cloud-caselist-run` / `v1.8` |
| Branch | `task/v1-e40-t29-pull-refused-by-the-move-is-skipped` |
| Session status | COMPLETE |

## Summary

A `caselist pull` refused with `RUN_HOME_MOVED` is now recorded as skipped. It gets its own banner,
`caselist pull skipped: the weekly run moved to prod`, which says the weekly run now runs from prod,
this pull did nothing and nothing needs a person. It names no person, school or path. **Look at
Deviation 1 first.** `skipped` did not exist as a run outcome, and it cannot be added to the record:
both earlier builds refuse a record whose `outcome` is a value they don't know. So the skip is recorded
in the run's details (`"skipped": "RUN_HOME_MOVED"`, no failure code). Earlier builds pass that key over,
and it is written only on a skipped run. The record itself stays `failed` / `RunHomeMoved`. `caselist
runs` shows `skipped (RUN_HOME_MOVED)`. A refusal because a runner holds the lock keeps its record and
wording word for word, as do a lock naming another home and local mode's seeded-bucket refusal. The
offline builds of `v1.1.0-dev.251` and `v1.1.0-dev.200` read every line this build writes. Goal set to
`Succeeded`.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `pull-refused-by-the-move-is-skipped` (Skipped after the move) | Done | Tests red at `742d0f3`, green at `b4f3b78`; runbooks at `0f8b3c8`; the bucket assertion tightened at `353adc8` |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1**: a pull refused by the move records skipped with `RUN_HOME_MOVED` and gives its own notice; a pull refused by a runner's hold is unchanged; by tests shown failing first | PASS | **Red** at `742d0f3`, unchanged source: `test_pull_after_the_run_home_moved_is_skipped.py` gave `4 failed, 4 passed`, each failure at an assertion (`assert None == 'RUN_HOME_MOVED'`, the details had `failure_codes: ['RUN_HOME_MOVED']` and no `skipped`). The 4 that passed at red are the guards that must hold before and after: the record every earlier build reads, a runner's hold (its notice pinned word for word), a lock naming another home, and local mode's seeded bucket. The CLI test `test_runs_shows_a_pull_after_the_run_home_moved_as_skipped_and_a_runners_hold_as_before` failed at red at `assert (None, ['RUN_HOME_MOVED']) == ('RUN_HOME_MOVED', [])`. **Green** at `b4f3b78`: those 9 tests passed, and the neighbouring suites gave `216 passed`. Each pull goes through `run_pull` inside a real `SyncRunMonitor`, with the real `BucketRun` bracket over a real `BucketRunLock` on moto. Its lock was moved by `RunHomeMove.move()`, t11's own code, with the `moved` holder. In both modes. Notices go to a `RecordingNotifier` |
| Node: Skipped after the move tests pass (`uv run pytest packages/debate_core/tests -k run_home_moved`) | PASS | `.venv/bin/python scripts/hard_stop.py 115 uv run pytest packages/debate_core/tests -k run_home_moved` → `9 passed in 17.83s` (at `353adc8`) |

## What the readers of a run record do with it

The PM asked first whether `skipped` already exists as a run status. **Not as an outcome.**
`SyncRunOutcome` is `completed`, `nothing_new`, `cap_deferred`, `publish_pending`, `incomplete` and
`failed`. Both stored record schemas (`record_schema_of_the_start_commit.json`,
`record_schema_of_the_cloud_image.json`) and the offline builds hold the same six. `skipped` exists
only as the **banner words** `LOCK_BANNER_WORDS` (`v1-e34-t26`): `caselist runs` shows `person
(skipped)` beside a run the lock refused (`SyncRunInProgress`, `RunLockHeld`), and `--json` gives
`banner: "skipped"`. I reused that word for the banner and added nothing to the record. Each reader
of a pull refused by the move, before and after:

| Reader | Before | After |
|---|---|---|
| The run record (`caselist-sync-runs.jsonl`) | `failed`, `RunHomeMoved` | Unchanged: `failed`, `RunHomeMoved`. Every earlier build reads it |
| The run's details (`caselist-sync-run-details.jsonl`) | `failure_codes: ["RUN_HOME_MOVED"]` | `"skipped": "RUN_HOME_MOVED"`, `failure_codes: []`, `hint: null`. The key is written only when set (`Field(exclude_if=...)`), so every other run's details are byte for byte what they were |
| The Mac's banner (`notifications_for`) | `caselist pull failed: needs a person`, "stopped: an error recorded as RUN_HOME_MOVED" | `caselist pull skipped: the weekly run moved to prod`; `Run <id> (dev) skipped: the weekly run now runs from prod, so this pull did nothing. Nothing here needs a person.`; fix `none: prod's weekly cloud run records and announces its own runs`; no hint. The same in local and bucket mode |
| `caselist runs` table | `failed (RunHomeMoved)` / `RUN_HOME_MOVED` / `person` | `skipped (RUN_HOME_MOVED)` / `none` / `none (skipped)` |
| `caselist runs --json` | record fields, `verdict: "person"`, `banner: null` | Record fields unchanged (`outcome: "failed"`), `details.skipped: "RUN_HOME_MOVED"`, `verdict: null`, `banner: "skipped"` |
| The cloud's late-run alarm (`runs_recorded` filter, `alerts.tf`) | Not counted | Not counted, and it cannot trip the alarm. The filter counts `caselist pull` envelopes carrying `data.run_record` or `error.details.run_record`. A refused pull raises, so its envelope has neither (the CLI test asserts it). Its record is `record_stays_local` too: it reaches no bucket and no cloud log. A Mac pull writes to no CloudWatch log at all, and prod's alarm reads prod's log group |
| `caselist runs` caption (days since the newest run, overdue) | Counts it as a run | Unchanged: it counts every record, failed ones included, as before. After the move dev's schedule is gone, so this only affects dev's local caption |
| Landscape staleness (`landscape_staleness.py`, reads the record only) | A run that stopped naming the caselist: stale, "stopped before its stages (RunHomeMoved)" | Unchanged, since the record is unchanged. A runner's hold (`RunLockHeld`) does the same today; only `SyncRunInProgress` is exempt. See Follow-up 2 |
| `caselist status` | Reads no run record | Unchanged |
| An earlier build (`v1.1.0-dev.251`, `v1.1.0-dev.200`) reading these files | n/a | Reads 2 of 2 records and 2 of 2 details. Its table shows `failed (RunHomeMoved)` / `none` / `none`, and the runner's hold row exactly as this build does |

### The cross-build check

Both earlier builds were built offline from their tags, as `v1-e33-t07` did: `git archive`,
`scripts/stamp_build.py stamp`, `uv build --offline` of `debate-core` and `debate-cli`, `uv venv
--offline`, `uv pip install --offline --no-deps`, and a plain-path `.pth` to the worktree's
site-packages for third-party dependencies only. `debate_core.__file__` resolved under each venv's
site-packages. The data directory came from this build: a pull refused by a cloud runner's live
lease, then `RunHomeMove.move()`, then a pull refused by the move (moto in-process). The read step ran
each build's own `SyncRunLog`, `SyncRunDetailsLog` and `banner_words`, then its own `debate-research
caselist runs`:

```text
=== v1.1.0-dev.251   (v1.1.0-dev.200 printed the same lines)
details model has skipped: False
records read: 2 of 2
details read: 2 of 2
20261104T110005Z failed RunLockHeld failure_codes ('RUN_LOCK_HELD',) banner skipped
20261104T113005Z failed RunHomeMoved failure_codes () banner None
planted outcome=skipped: records read 1 of 2
planted outcome=skipped refused: ValidationError 1 validation error for SyncRunRecord
│ 20261104T113005Z │ 2026-11-04 11:30 │ failed (RunHomeMoved) │ none          │ none             │ …
│ 20261104T110005Z │ 2026-11-04 11:00 │ failed (RunLockHeld)  │ RUN_LOCK_HELD │ person (skipped) │ …
=== this build
│ 20261104T113005Z │ 2026-11-04 11:30 │ skipped (RUN_HOME_MOVED) │ none          │ none (skipped)   │ …
│ 20261104T110005Z │ 2026-11-04 11:00 │ failed (RunLockHeld)     │ RUN_LOCK_HELD │ person (skipped) │ …
```

The "planted" lines are mutant 5 under the earlier builds: a record with `outcome: "skipped"`. Each
build's run log logged `line 2 is not a valid run record; skipped` and returned one record of two. That
is the run vanishing from their `caselist runs`, which is why the record stays `failed`. The committed
test `test_a_pull_after_the_run_home_moved_keeps_the_record_every_earlier_build_reads` validates this
build's record against both stored record schemas, and its details against both stored details
schemas (dev.155/164's and dev.200's).

### Tests and checks run

| What | Command | Result |
|---|---|---|
| New tests, red | `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests/application/caselist/test_pull_after_the_run_home_moved_is_skipped.py -n 0 -p no:randomly -q --tb=line` | `4 failed, 4 passed` (above) |
| New tests, green, plus neighbours | the same over the new file, `test_sync_runs.py`, the cross-build test, the banner, token and auth-expired notice tests, `test_caselist_sync_run_state.py`, `test_run_state_home_moved.py`, `test_caselist_runs.py`, `test_bucket_mode_lock.py` | `216 passed in 24.96s` |
| Affected set | `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python scripts/affected_tests.py --run` | **Stopped at its 115 s limit** (exit 124). `sync_runs.py` is a hub module: `304 of 638 test files (47.6%)`. Per agreement 10 it is left to the pull request's `ci` check, with no hand-off |
| Instead, within the limit: every test file that names `sync_runs`, `caselist_runs`, `run_home_move` or the two changed runbooks (52 files), and the always-run list | the 52 in two halves, then `tests/architecture/ tests/specs/` and the three CLI wiring files, each with `-n auto -m "not slow and not live"` | `504 passed in 79.12s`, `460 passed in 26.68s`, `374 passed in 32.23s` (load 6 to 13 from other sessions) |
| Lint and format | `uv run --frozen ruff check .` / `uv run --frozen ruff format --check .` | `All checks passed!` / `1760 files already formatted` |
| Types | `uv run --frozen pyright packages/debate_core packages/debate_cli` | `0 errors, 0 warnings, 0 informations` |
| Import boundaries | `uv run --frozen lint-imports`, `uv run --frozen python scripts/check_thin_handlers.py` | `Contracts: 20 kept, 0 broken.` / `OK: 70 CLI command and API route handlers within 25 statements` |
| Docs | `scripts/docs_index.py --check-descriptions`, `scripts/check_links.py`, `scripts/check_command_blocks.py --base origin/dev` | All OK |
| Specs | `uv run scripts/validate_specs.py` | `OK: 558 files, 41 epics, 495 tasks, 22 releases` |

### Mutation run

The PM's five, plus eight aimed at the new readers: 13 mutants in all. Each one was applied to
`sync_runs.py`, and the 6 files covering it (123 tests) ran under the 115 s limit with a new empty
`HYPOTHESIS_STORAGE_DIRECTORY` each time (none of these files uses Hypothesis). The harness restored
the file from saved bytes and checked its SHA-256 after each one; `git status` was clean afterwards.
Every mutant failed at an assertion of the tests named, not at a crash. For mutant 5 I added the enum
value as well, so that the record could be built at all.

| Mutant | Result | Caught by |
|---|---|---|
| 1. A moved refusal recorded `failed` (no skip in the details) | CAUGHT (4) | `..._is_recorded_skipped_with_its_own_notice[bucket_mode, local_mode]`, `..._reads_back_as_skipped_beside_its_banner`, the CLI `caselist runs` test |
| 2. A runner's hold recorded `skipped` | CAUGHT (2) | `test_a_pull_a_runners_hold_refused_keeps_its_record_and_wording_not_run_home_moved`, the CLI test |
| 3. The generic notice kept | CAUGHT (2) | `..._is_recorded_skipped_with_its_own_notice` (both modes) |
| 4a. The holder, build and lock wording in the notice (`record.error_message` appended) | CAUGHT (2) | the same, by the exact message and `assert_names_no_person_school_or_path` |
| 4b. A path in the notice (the runbook's path in the fix) | CAUGHT (3) | the same, and the runbook-quote test |
| 5. An earlier build refusing the new record (`SyncRunOutcome.SKIPPED` in the record) | CAUGHT (3) | `test_a_pull_after_the_run_home_moved_keeps_the_record_every_earlier_build_reads`, `test_this_builds_record_model_is_the_one_both_older_builds_read_with`, the CLI test; and by the cross-build check above |
| 6. The `skipped` key written on every run's details | CAUGHT (16) | `test_details_with_no_skip_write_no_skipped_key...`, the three other-refusal tests, 10 scenarios of `test_the_codes_and_the_parse_counts_travel_beside_the_record_keyed_by_run_id`, `test_the_earlier_builds_read_every_bucket_mode_record_and_details_line_this_build_writes` |
| 7. The failure code kept on a skipped run | CAUGHT (3) | `..._is_recorded_skipped_with_its_own_notice` (both modes), the CLI test |
| 8. A lock naming another home recorded skipped | CAUGHT (1) | `test_a_pull_a_lock_naming_another_home_refused_is_failed_not_skipped_as_run_home_moved_is` |
| 9. The banner words dropped for a skipped run | CAUGHT (2) | `..._reads_back_as_skipped_beside_its_banner`, the CLI test |
| 10. `caselist runs` showing the record's outcome | CAUGHT (1) | the CLI test |
| 11. The notice reworded, the runbook left stale | CAUGHT (3) | `test_the_runbook_quotes_the_notice_of_a_pull_after_the_run_home_moved_word_for_word`, and the exact message |
| 12. A hint (the release and the runbook path) on the notice | CAUGHT (2) | `..._is_recorded_skipped_with_its_own_notice` (both modes) |

## Files changed

* `packages/debate_core/src/debate_core/application/sync_runs.py`: `SyncRunDetails.skipped` (written
  only when set); `SKIPPED_REFUSALS = (RunHomeMoved,)`; `details_for_failure` records the skip with no
  failure code or hint; the notice (`RUN_HOME_MOVED_TITLE`, `_NOTICE`, `_FIX`, built from t11's
  `NEW_HOME`); `banner_words` gives `skipped` for it; `outcome_shown` for the table; docstrings.
* `packages/debate_cli/src/debate_cli/commands/caselist_runs.py`: the Outcome cell from
  `outcome_shown`; a docstring section on a skipped run.
* `packages/debate_core/tests/application/caselist/test_pull_after_the_run_home_moved_is_skipped.py`
  (new): the tests above.
* `packages/debate_cli/tests/bucket_mode/test_bucket_mode_lock.py`: `caselist runs` after a runner's
  hold and the move, through the CLI, plus the envelope the late-run filter reads.
* `docs/runbooks/caselist-scheduled-sync.md`: the banner's row in the notification table and a
  paragraph quoting it (held to the code by the new runbook test).
* `docs/runbooks/caselist-cutover.md`: the promotion section's "What a Mac pull shows after the move".
* The task spec's phase.

## Deviations from the spec

1. **The record still says `failed`; `skipped` is in the run's details.** The spec says the run
   record "says failed … Record it as skipped". The run record proper (`SyncRunRecord`) cannot say
   `skipped`. Its `outcome` is a closed enum, and every installed build validates it (`v1-e34-t19`),
   so the PM's own rule ("a stored record an earlier build can't read is forbidden") rules a new
   value out. The planted record shows both earlier builds dropping such a line. What this build
   writes instead is the rule the details were made for. They carry `"skipped": "RUN_HOME_MOVED"` and
   no failure code, they are written only on a skipped run, and earlier builds pass them over. Every
   reader this build has (banner, table, `--json`) says skipped from them. If the spec should say
   this, a wording would be: "Record it as skipped in the run's details, with `RUN_HOME_MOVED` as the
   reason; its record stays the one every installed build reads."

## Decisions and assumptions

* **The exit code is unchanged** (`1`, `DOMAIN_FAILURE`, `RUN_HOME_MOVED`). The spec asked about the
  record and the notice only, and t11's tests pin the exit. So a skipped run's details have no
  failure code, though the command exits as refused; `SyncRunDetails.skipped`'s docstring says so.
* **Only `RunHomeMoved` skips** (`SKIPPED_REFUSALS`). `RunLockHeld`, `SyncRunInProgress`,
  `RunLockWrongHome`, `BucketKeepsRunState` and `RunLockUnreadable` keep their records and wording
  (spec's forbidden list). The runner's hold keeps its existing banner word `skipped` and its
  `person (skipped)` verdict, as `v1-e34-t26` gave it. "Unchanged" includes that word.
* **One notice in both modes.** The mode-aware pattern of t35, t36 and t33 changes a fix that differs
  by mode. Here it doesn't: in either mode dev's lock is held for good and nothing in dev is the
  weekly run's. The test runs both modes and pins the same words.
* **The wording**, in t35's shape (the run, what it did, the verdict): "Run <id> (dev) skipped: the
  weekly run now runs from prod, so this pull did nothing. Nothing here needs a person." The fix line,
  which a `Notification` must have: "none: prod's weekly cloud run records and announces its own runs".
  It has no hint, because the error's own hint names the release and a runbook path.
* **`prod` comes from t11's `NEW_HOME`**, not from the lock: the notice is built from the record and
  details only, and `move-run-home` only ever names `NEW_HOME`.

## Operator follow-ups

None. The affected set (304 files) runs in the pull request's `ci` check.

## Follow-up work

1. **t11's `RunHomeMoved` record message is mangled by `redact`** (E40, a small follow-up to
   `v1-e40-t11`). The stored `error_message` reads "the weekly run now runs from prod: this
   bucket[redacted]s home to prod (`caselist move-run-home`, …)". `_QUOTED_PATH` takes the apostrophes
   of "bucket's" and "run's" as quotes around a path, and removes the lock key between them. Nothing
   leaks, and this task's notice doesn't use the message, but `caselist runs --json` shows the
   mangled text. `RunLockHeld`'s message is unaffected. Seen in the cross-build data above.
2. **Landscape staleness counts lock refusals** (E40 or E34, PM's call). `landscape_staleness.py`
   exempts only `SyncRunInProgress`. A `RunLockHeld` or `RunHomeMoved` record naming a caselist makes
   the Mac's dev landscape read "stopped before its stages". After the move, "stale" is true of dev,
   but the reason it gives is a refusal. Unchanged here, because it reads only the record.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

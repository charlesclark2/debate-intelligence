# Session report: v1-e30-t30-inbox-deletions-fsync-the-directory

| | |
|---|---|
| Task | `v1-e30-t30-inbox-deletions-fsync-the-directory` — Inbox deletions fsync the inbox directory, so a removed archive cannot come back after a power cut |
| Spec | [`plan_specs/v1/e30-caselist-ingestion/t30-inbox-deletions-fsync-the-directory.yaml`](../../plan_specs/v1/e30-caselist-ingestion/t30-inbox-deletions-fsync-the-directory.yaml) |
| Epic / release | `v1-e30-caselist-ingestion` / `v1.1` |
| Branch | `task/v1-e30-t30-inbox-deletions-fsync-the-directory` |
| Session status | COMPLETE |

## Summary

A removal's deletions from the sync's inbox are now durable. `inbox_purge._carry_out` calls
`durable_files.fsync_directory(path.parent)` after each `path.unlink()`, and counts the file as
deleted only after that. The rewrite now removes its emptied staging directory right after the
rename and before the directory fsync t26 added, so one fsync of the inbox puts both entries on the
disk. A fsync that fails raises the operating system's `OSError`, which stops the removal
`INCOMPLETE`; re-running it finishes the rest. A new recording test was run red against dev's
`inbox_purge.py` (3 failed), and six mutants, the PM's three among them, were each caught. Look
first at the error-path cleanup, which is still not fsynced (Decisions). After the PM's review,
the review's condition closed Follow-up 1 in-session (see "The condition"): every purge now ends
with one fsync of the inbox under the run lock, an empty purge included, so a re-run after an `EIO`
makes the earlier delete durable.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `inbox-deletions-fsync-the-directory` (Inbox deletion fsync) | Done | Directory fsync after each delete and after the staging directory's removal; recording test red first, then six mutants |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| Goal ac1: each inbox deletion is followed by a directory fsync, and a failed one raises, by a recording test shown failing first | PASS | Red against dev's `inbox_purge.py` (`git show c9711f2:<path>`), final tests: `.venv/bin/python -m pytest packages/debate_core/tests/application/test_inbox_purge_deletions_fsync_the_directory.py packages/debate_core/tests/application/test_rename_into_place_writers_fsync_their_directory.py -n 0 -p no:randomly` → `3 failed, 9 passed` (all three new tests: no fsync after an unlink, the staging `rmdir` after the fsync, `DID NOT RAISE OSError`). Green at the commit: `12 passed`. Mutants below. |
| Node: Inbox deletion fsync tests pass | PASS | `uv run pytest packages/debate_core/tests -k inbox_purge` → `6 passed in 9.68s` (the three new tests, which `-k` selects by module name, and t26's three `inbox_purge rewrite` cases) |

### The recording test

[`test_inbox_purge_deletions_fsync_the_directory.py`](../../packages/debate_core/tests/application/test_inbox_purge_deletions_fsync_the_directory.py)
wraps `os.unlink`, `os.rmdir`, `os.replace`, `os.open` and `os.fsync`. It records each call after
it succeeds, and only calls in the inbox, so the run lock and the delivery record in the state
directory don't appear. It drives `purge_inbox` with plans written by hand:

* three deletes (two imported weeklies and a removed camp download, whose delivery record is
  written first): exactly `unlink, open, fsync directory` three times, in that order;
* a rewrite: exactly `replace, rmdir <staging directory>, open, fsync directory`, and nothing left
  in the inbox but the rewritten archive;
* `EIO` from the first directory fsync: `OSError` raised, the first file gone but not counted
  (`deleted == 0`), the second untouched byte for byte; purging the second (what a re-plan holds)
  then deletes it.

My first green run failed on the recorder, not the code: it named a fsynced directory by its
descriptor number, and a later file reused that number. It now goes by the inode
(`os.path.samestat`).

### Mutants (agreement 8)

Run against the two recording test files, each with a new empty `HYPOTHESIS_STORAGE_DIRECTORY`
(neither file uses Hypothesis), `-n 0 -p no:randomly`. Each mutant was written over the committed
file by a script and restored with `git checkout HEAD --`; `git status` was clean afterwards.

| Mutant | Caught by | Result |
|---|---|---|
| The directory fsync after a delete dropped | each-deleted-file test; failed-fsync test | 2 failed |
| The fsync before the unlink | each-deleted-file test (order); failed-fsync test (raises before the delete, so both files remain) | 2 failed |
| A failed fsync after a delete swallowed (`contextlib.suppress(OSError)`) | failed-fsync test | 1 failed |
| The delete counted before the fsync | failed-fsync test (`deleted == 0`) | 1 failed |
| The staging directory removed after the fsync (the order before this task) | rewrite test | 1 failed |
| A failed fsync after the rewrite swallowed | t26's `test_a_directory_fsync_that_fails_is_a_write_that_failed[inbox_purge rewrite]` | 1 failed |

### Checks before the report

| Command | Result |
|---|---|
| `uv run scripts/affected_tests.py` (list only) | 246 test files. Not run: see below |
| `.venv/bin/python -m pytest -n auto -m "not slow and not live"` over the always-run list (`tests/architecture`, `tests/specs`, `debate_cli/tests/test_app.py`, `test_help_rendering.py`, `test_container_factories.py`) and every test file that imports `inbox_purge` (the two recording tests, `caselist/test_held_path_loose_ends.py`, `test_removal_purges_inbox.py`, `test_held_path_inbox_copies.py`, `test_junk_beside_a_held_link.py`, `test_removal_path_hold_plan.py`, `debate_cli/tests/commands/test_caselist_remove_plan_output.py`), under `perl -e 'alarm 115'` | `475 passed in 40.07s` |
| `uv run ruff format --check .` | `1611 files already formatted` |
| `uv run ruff check .` | `All checks passed!` |
| `uv run pyright packages/debate_core` | `0 errors, 0 warnings, 0 informations` |
| `uv run lint-imports` | `Contracts: 18 kept, 0 broken.` |
| `uv run --frozen python scripts/check_thin_handlers.py` | `OK: 68 CLI command and API route handlers within 25 statements` |
| `uv run scripts/validate_specs.py` | `OK: 509 files, 40 epics, 447 tasks, 22 releases` |

**The affected set was not run here.** It is 246 test files, and the load average was 18 while
other sessions ran. Earlier sets of 47 to 222 files took minutes, so this one would run past the
two-minute line. Under agreement 10 (the PM's ruling of 2026-10-19) it is left to the pull
request's `ci` check, which runs the same selection, and the always-run list and the tests that
import the changed module were run instead (above).

### The condition

The PM's review (2026-10-30) accepted the task on one condition: close Follow-up 1 in-session.

**What changed.** `purge_inbox` no longer returns early for an empty plan. It takes the sync's run
lock, carries out the plan, and then calls `fsync_directory(inbox.directory)` once more, at the end
of every purge, an empty one included (fb1051d). One case still returns before the lock:
nothing planned and no inbox directory (fa9ab6e). That is a prod takedown, where
`TestAnEnvironmentWithNoInbox` (`v1-e30-t09`) pins that the inbox step does nothing at all, not
even make `caselist-sync.lock`. fb1051d broke that test, and the importer run below caught it;
see Decisions. A failed closing fsync raises, like any other.

**Tests** (in the recording test file):

* `test_a_rerun_with_nothing_planned_puts_the_earlier_delete_down`: a delete whose fsync gets
  `EIO` stops the purge (recorded: `unlink`, `open`, with the refused fsync not recorded). A re-run
  with an empty plan then records exactly `open, fsync directory` of the inbox and counts nothing.
* `test_nothing_planned_is_still_done_under_the_run_lock`: with a pull holding the lock, an empty
  purge raises `InboxInUse` and records no fsync.
* `test_nothing_planned_and_no_inbox_yet_does_nothing`: no inbox and nothing planned, so no error
  and neither the inbox nor the lock file is created.
* The pinned event lists gained the closing `open, fsync directory`: two in this file, and t26's two
  `inbox_purge rewrite` cases in `test_rename_into_place_writers_fsync_their_directory.py`, through
  a `closing(writer, path)` helper that is empty for the other two writers.

**Red** against 4a8d38c (the early return), `.venv/bin/python -m pytest
<the two recording test files> -n 0 -p no:randomly`: `6 failed, 9 passed`. The re-run test
failed only at the re-run (`assert [] == [('open', …), ('fsync directory', …)]`), the lock test
with `DID NOT RAISE InboxInUse`, and the four pinned lists for the missing closing fsync. The
no-inbox test passed there, as a guard should. Its lock-file assertion was then shown red against
fb1051d (`1 failed, 5 passed`, `assert not True` at the lock file) before fa9ab6e fixed it.
**Green** at fa9ab6e: `15 passed`, and with `TestAnEnvironmentWithNoInbox`, `16 passed`.

**Mutants** (agreement 8; a new empty `HYPOTHESIS_STORAGE_DIRECTORY` for each, `-n 0 -p
no:randomly`, run over the two recording files and `TestAnEnvironmentWithNoInbox`, each restored
with `git checkout HEAD --` and `git status` clean afterwards):

| Mutant | Caught by | Result |
|---|---|---|
| The closing fsync skipped when nothing is planned (`if planned:`), the PM's | re-run test | 1 failed |
| The old early return for an empty plan restored | re-run test; lock test | 2 failed |
| The closing fsync made before the lock is taken | both pinned-list tests in each file, the failed-fsync test, the re-run test, the lock test | 7 failed |
| The no-inbox early return dropped | no-inbox test (`FileNotFoundError`); t09's `TestAnEnvironmentWithNoInbox` (lock file made) | 2 failed |

**Re-runs after the condition:**

| Command | Result |
|---|---|
| `.venv/bin/python -m pytest -n auto -m "not slow and not live"` over the always-run list and every test file that imports `inbox_purge` (the same eight as above), under `perl -e 'alarm 115'` | first at fb1051d: `1 failed, 477 passed` (t09's no-inbox test, fixed in fa9ab6e); at fa9ab6e: `478 passed in 21.97s` |
| The same, over the 26 `debate_cli/tests/commands/test_caselist_remove*.py` and `debate_core/tests/application/caselist/test_removal*.py` files not in that list: an empty purge now takes the lock, and these exercise removals, one under a pull's lock | `320 passed in 30.05s` |
| `uv run pytest packages/debate_core/tests -k inbox_purge` | `9 passed in 10.34s` |
| `ruff format --check .`, `ruff check .`, `pyright packages/debate_core`, `lint-imports`, `check_thin_handlers.py`, `validate_specs.py` | formatted; all checks passed; 0 errors; 18 contracts kept; 68 handlers within 25 statements; `OK: 509 files, 40 epics, 447 tasks, 22 releases` |

The affected set is still left to the pull request's `ci` check, for the reason given above.

## Files changed

* `packages/debate_core/src/debate_core/application/caselist/inbox_purge.py`: the directory fsync
  after a delete; the staging directory removed before the rewrite's directory fsync; the module,
  `purge_inbox` and `_rewrite` docstrings say so.
* `packages/debate_core/tests/application/test_inbox_purge_deletions_fsync_the_directory.py`
  (new): the recording test. It sits beside t26's, not under `caselist/`, whose conftest builds the
  moto bucket world the test does not need.
* `packages/debate_core/tests/application/test_rename_into_place_writers_fsync_their_directory.py`:
  t26's two `inbox_purge rewrite` event lists end with the closing fsync (the condition).
* `plan_specs/.../t30-inbox-deletions-fsync-the-directory.yaml`: Goal phase `Succeeded`.
* This report.

## Deviations from the spec

None.

## Decisions and assumptions

* **One fsync for the rewrite, not two.** The PM's note asked for a fsync after the staging
  directory's removal, on its parent. On the success path the staging directory is empty once the
  rename has moved the staged file out, so `_rewrite` now removes it right after `os.replace` and
  before the existing `fsync_directory`. That one fsync puts down both the rename and the removal.
  t26's pinned order (file fsync, rename, directory fsync) is unchanged, and t26's test passes
  without edits.
* **The error-path cleanup is not fsynced.** When a rewrite fails before its rename, the `finally`
  still unlinks the staged file and removes the staging directory, with no fsync after.
  The original archive is still in place unchanged and the removal has already stopped
  `INCOMPLETE`, so a staging directory brought back by a power cut adds no removed bytes the inbox
  does not still hold, and the re-run rewrites the original. A fsync there that failed would also
  replace the error that explains the stop (an `InboxRewriteFailed`) with an `EIO`.
* **A delete is counted after its fsync**, as t26 counts a rewrite only after its fsync. A file
  whose fsync failed is gone, but not durably, and is not in `deleted`.
* **An empty purge takes the run lock now (the condition), which changes one behaviour.** Before,
  a removal with nothing in the inbox to change never looked at the lock, so it completed while a
  `caselist pull` ran. Now the inbox step raises `InboxInUse` and the removal stops `INCOMPLETE`
  until the pull ends, as a removal with inbox files already did. This follows the PM's "under the
  run lock", and the 26 removal test files above pass with it.
* **No inbox, nothing planned: still nothing at all.** The condition says "including a purge with
  nothing planned". Read literally, that would also make `caselist-sync.lock` in prod's data
  directory on every takedown, which `v1-e30-t09` pins against. With no inbox directory there is no
  earlier delete to put down, so that case returns before the lock. Every purge in an inbox that
  exists, empty or not, takes the lock and ends with the fsync, and the `EIO` re-run is always one
  of those.
* **The `durable_files` docstring was left alone.** It lists the rename-into-place writers, which
  are unchanged. The new caller is described in `inbox_purge`'s own docstrings. `durable_files` is
  imported by four writers, and an optional docstring edit there would widen the affected set.

## Operator follow-ups

None.

## Follow-up work

1. **Closed in-session by the PM's condition** (see "The condition"); left here as filed.
   **A re-run does not repeat a failed directory fsync** (`v1-e30`, next to this task). After an
   `EIO` from the fsync that follows a delete (or a t26 rewrite), the file is gone (or rewritten)
   but not durably. A re-run plans from what the inbox holds, so it has nothing to do to that file
   and never fsyncs the inbox again. "Re-running finishes it" holds for the rest of the removal,
   not for that one entry. One fix: `purge_inbox` fsyncs the inbox once under the run lock even
   when nothing is planned, or the removal service does that before it reports `COMPLETE`. The
   window is small (an `EIO` and then a power cut before the kernel writes the directory out), but
   it is a takedown that may not hold.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED, with one condition to close in-session before the pull request
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-30

**Notes:**

The inbox's deletions are now durable, in the order the spec asked.
1. **ac1 passes.** Red against dev's `inbox_purge.py`: 3 failed (no fsync after an unlink, the staging
   `rmdir` after the fsync, and `DID NOT RAISE OSError`). Green: 12 passed with t26's cases.
2. **Mutants:** the PM's three and three more, all caught. "The delete counted before the fsync" and
   "the staging directory removed after the fsync" are the two that make the counting and the order
   real. The recorder's descriptor-reuse bug, found and fixed by inode, is noted.
3. **Decisions accepted:**
   * one fsync for the rename and the staging directory's removal;
   * the error-path cleanup not fsynced, for the reason you give: the original is intact, the run has
     stopped, and an `EIO` would hide the real error;
   * a delete counted after its fsync;
   * `durable_files`' docstring left alone.
4. **The condition, your Follow-up 1, closed in this task rather than filed.** After an `EIO` from a
   directory fsync, the file is gone but not durably, and a re-run has nothing planned for it, so it
   never fsyncs the inbox again. That is a takedown that may not hold, the very thing this task
   exists to prevent. Make `purge_inbox` fsync the inbox directory once, under the run lock, at the end
   of every purge, including one with nothing planned. Then a re-run after the `EIO` makes the earlier
   deletion durable.
   * A test: after the `EIO` stop, a re-run with an empty plan fsyncs the inbox, recorded.
   * A mutant: skip that fsync when nothing is planned, which must be caught.
   * Record it in this report under a "### The condition" note in Plan nodes or Acceptance criteria,
     and the PM adds a short note below once it's in.
5. **The affected set** (246 files) is left to the PR's `ci`. The always-run list and every file that
   imports `inbox_purge` passed (475), as did ruff, pyright, lint-imports, the thin-handler check and
   the specs.
6. **Merge:** after the condition.

### The condition, closed (PM, 2026-10-30)

The condition is met, so the review's ACCEPTED stands and the pull request may open.
* Every purge in an inbox that exists, an empty one included, now takes the run lock and ends with
  one fsync of the inbox. A re-run after the `EIO` records exactly `open, fsync directory` and
  counts nothing.
* Red: 6 failed against the early return. Green: 15, and 16 with t09's no-inbox test.
* Four mutants are caught, the PM's among them.
* **The no-inbox exception: accepted.** With no inbox directory there is no earlier delete to put
  down, and `v1-e30-t09` pins that a takedown in prod's data directory makes no lock file. Your
  importer run caught that break before it shipped.
* **The behaviour change: accepted.** An empty purge stops `INCOMPLETE` while a pull holds the lock,
  as a purge with files already did. Since the cutover no pull runs on the operator's Mac, so it
  should not arise. The 26 removal test files pass with it.

**Merge:** any time.

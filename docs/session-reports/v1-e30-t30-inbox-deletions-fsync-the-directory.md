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
first at the error-path cleanup, which is still not fsynced (Decisions), and at Follow-up 1: a
re-run does not repeat the fsync for a file it already deleted.

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

## Files changed

* `packages/debate_core/src/debate_core/application/caselist/inbox_purge.py`: the directory fsync
  after a delete; the staging directory removed before the rewrite's directory fsync; the module,
  `purge_inbox` and `_rewrite` docstrings say so.
* `packages/debate_core/tests/application/test_inbox_purge_deletions_fsync_the_directory.py`
  (new): the recording test. It sits beside t26's, not under `caselist/`, whose conftest builds the
  moto bucket world the test does not need.
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
* **The `durable_files` docstring was left alone.** It lists the rename-into-place writers, which
  are unchanged. The new caller is described in `inbox_purge`'s own docstrings. `durable_files` is
  imported by four writers, and an optional docstring edit there would widen the affected set.

## Operator follow-ups

None.

## Follow-up work

1. **A re-run does not repeat a failed directory fsync** (`v1-e30`, next to this task). After an
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

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

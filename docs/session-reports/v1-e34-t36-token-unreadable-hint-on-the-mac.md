# Session report: v1-e34-t36-token-unreadable-hint-on-the-mac

| | |
|---|---|
| Task | `v1-e34-t36-token-unreadable-hint-on-the-mac` — A Mac run stopped for an unreadable token says to log out and log in again |
| Spec | [`plan_specs/v1/e34-caselist-sync/t36-token-unreadable-hint-on-the-mac.yaml`](../../plan_specs/v1/e34-caselist-sync/t36-token-unreadable-hint-on-the-mac.yaml) |
| Epic / release | `v1-e34-caselist-sync` / `v1.1` |
| Branch | `task/v1-e34-t36-token-unreadable-hint-on-the-mac` |
| Session status | COMPLETE |

## Summary

A run on the Mac stopped by `CASELIST_TOKEN_UNREADABLE` now says what stopped it in words ("the
caselist_token stored on this machine could not be read") and carries the error's own fix as its
hint: log out with `debate-research caselist auth logout`, then log in again with
`debate-research caselist auth login`. Before, it read "stopped: an error recorded as
CASELIST_TOKEN_UNREADABLE" with no hint. This follows `v1-e34-t35`'s pattern: a `fix_for` branch
outside bucket mode (`caselist_sync.py`), and words in `_WHAT_STOPPED_A_RUN` listed in
`_WORDS_OUTSIDE_BUCKET_MODE_ONLY` (`sync_runs.py`). Bucket mode is unchanged byte for byte, asserted
by the old text, and `v1-e40-t33`'s bucket-mode pin for this code passes unedited. **Look first at
how `fix_for` recognises the error** (Decisions, first item): the application layer may not import
the token store's `CaselistTokenUnreadable`, so the branch matches the error's code, not its type.
The affected set (303 of 636 files) is over the two-minute line and is left to the pull request's
`ci` check (agreement 10).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `token-unreadable-hint-on-the-mac` (Token unreadable hint) | Done | Tests committed failing first (`9170191`), then the code and runbook line (`2fa3f40`); six mutants, all caught |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: Outside bucket mode a run stopped for an unreadable token names logout then login and has its own words; in bucket mode the notice is unchanged, asserted by its old text; by tests shown failing first | PASS | Red at `9170191` (tests only, code unchanged): `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -n 0 -p no:randomly -q --tb=no -rA <new file> <t35's file>` → `2 failed, 5 passed`. Failing: `test_a_mac_run_stopped_by_token_unreadable_says_to_log_out_and_log_in_again` (`assert None == 'The caselist_token stored on this machine …'`, the hint absent) and t35's `…given_to_no_other_code_on_the_mac[token-unreadable]` (message still `an error recorded as CASELIST_TOKEN_UNREADABLE`). Passing at red, pinning today's text: `test_a_bucket_mode_run_stopped_by_token_unreadable_is_unchanged` and `test_a_mac_run_stopped_by_token_missing_is_not_told_to_log_out`. Green at `2fa3f40`, the same files plus `test_pull_auth_expired_notice_names_the_wednesday_login.py` (unedited) → `15 passed in 2.07s`, its `[token-unreadable]` bucket-mode case among them |
| Node criterion "Token unreadable hint tests pass": `uv run pytest packages/debate_core/tests -k token_unreadable` | PASS | Run as `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests -k token_unreadable -q` → `3 passed in 46.62s`, exit 0 (collection of the whole package is most of the time) |

### What the tests run

`packages/debate_core/tests/application/caselist/test_pull_token_unreadable_hint_on_the_mac.py`, in
t35's file's style: `run_pull` inside a real `SyncRunMonitor`, against moto, with t40-t18's
bucket-mode bracket stand-in for bucket mode. The token is read by a real `CaselistTokenStore` over
`KeyringTokenBackend`, whose keychain stand-in returns an item that is not a record this program
wrote, so the store itself raises `CaselistTokenUnreadable`. Every expected sentence is written by
hand.

* **On the Mac:** the run record (`failed`, `CaselistTokenUnreadable`), its details
  (`failure_codes`, the hint, no `bucket_run`), the notification (title, message, hint,
  `fix_command` still `debate-research caselist pull`, no code, no path) and the banner `osascript`
  would show, with the logout before the login in it.
* **Token missing keeps t35's login:** a Mac run with no token has `v1-e34-t35`'s hint, and no
  logout or unreadable words.
* **In bucket mode:** the message is the old `an error recorded as CASELIST_TOKEN_UNREADABLE`, no
  hint, `v1-e40-t28`'s unfinished-run cure as the fix, and no logout, login or words.

### Mutants (agreement 8)

Each run set `HYPOTHESIS_STORAGE_DIRECTORY` to a fresh empty directory (these tests use no
Hypothesis), ran the new file, t35's and t40-t33's with `-n 0 -p no:randomly`, and restored the
source after. Every catch below failed at an `AssertionError` on an expected sentence, not at a
crash; the tree was clean after the run.

| Mutant | Result | Caught by |
|---|---|---|
| The hint given in bucket mode (`and not bucket_mode` removed) | Caught, 1 failed | `test_a_bucket_mode_run_stopped_by_token_unreadable_is_unchanged` (line 175, hint not `None`) |
| The hint dropped on the Mac (the branch removed) | Caught, 1 failed | `test_a_mac_run_…_says_to_log_out_and_log_in_again` (line 129) |
| The words dropped (the `_WHAT_STOPPED_A_RUN` entry removed) | Caught, 2 failed | the Mac test (line 134, message) and t35's `[token-unreadable]` case |
| Logout and login in the wrong order in the hint | Caught, 1 failed | the Mac test (line 129, hint text) |
| `CASELIST_TOKEN_MISSING` given this hint | Caught, 2 failed | `test_a_mac_run_stopped_by_token_missing_is_not_told_to_log_out` (line 152) and t35's own Mac test |
| The words said in bucket mode (code left out of `_WORDS_OUTSIDE_BUCKET_MODE_ONLY`), added beyond the PM's five | Caught, 1 failed | the bucket-mode test (line 180, message) |

### Before the report

| Check | Result |
|---|---|
| `uv run scripts/affected_tests.py` (listing only) | `303 of 636 test files (47.6%) chosen in 15.9 s from 7 changed files`. `sync_runs.py` and `caselist_sync.py` are hub modules; the whole default selection is about six minutes, so this is well over the two-minute line. **Not run; left to the pull request's `ci` check**, which runs the same affected set (agreement 10, the PM's ruling of 2026-10-19). |
| The changed modules' test directory: `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -n auto -m "not slow and not live" -q packages/debate_core/tests/application/caselist` | `1791 passed in 110.16s` |
| The always-run list: `… -m "not slow and not live" tests/architecture/ tests/specs/ packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py packages/debate_cli/tests/test_container_factories.py` | `374 passed in 35.86s` |
| `uv run ruff format --check .` | `1756 files already formatted` |
| `uv run ruff check .` | `All checks passed!` |
| `uv run pyright packages/debate_core` | `0 errors, 0 warnings, 0 informations` (37 s) |
| `uv run lint-imports` | `Contracts: 20 kept, 0 broken.` |
| `uv run --frozen python scripts/check_thin_handlers.py` | `OK: 70 CLI command and API route handlers within 25 statements` |
| `uv run scripts/check_command_blocks.py` | `OK: no '#' comments in 641 shell code blocks in 203 Markdown files` |
| `uv run scripts/validate_specs.py` (after `set-phase … Succeeded`) | `OK: 558 files, 41 epics, 495 tasks, 22 releases` |

## Files changed

* `packages/debate_core/src/debate_core/application/caselist_sync.py`: `fix_for` gives
  `CASELIST_TOKEN_UNREADABLE` the logout-then-login hint outside bucket mode only
  (`_TOKEN_UNREADABLE_ON_THIS_MACHINE_FIX`); its docstring says why bucket mode gets none.
* `packages/debate_core/src/debate_core/application/sync_runs.py`: the code's words in
  `_WHAT_STOPPED_A_RUN`, and the code in `_WORDS_OUTSIDE_BUCKET_MODE_ONLY`.
* `packages/debate_core/tests/application/caselist/test_pull_token_unreadable_hint_on_the_mac.py`:
  new, the tests above.
* `packages/debate_core/tests/application/caselist/test_pull_token_missing_hint_on_the_mac.py`: its
  "given to no other code" case for the unreadable token expected the old Mac text; see Decisions.
* `docs/runbooks/caselist-scheduled-sync.md`, "When something goes wrong": the code's line in the
  keychain table beside t35's, and the paragraph under it says both lines are for a run on this
  Mac, the cloud run naming the code as before.
* The task spec's phase, and this report.

## Deviations from the spec

None. One mechanism differs from t35's, within scope; it is the first decision below.

## Decisions and assumptions

* **`fix_for` recognises the error by its code, not by `isinstance`.** `CaselistTokenUnreadable`
  is defined in `debate_core.integrations.opencaselist.token_store`, and the layers contract
  ("integrations and testing above application") forbids `caselist_sync.py` from importing it.
  t35's `CaselistTokenMissing` and t33's `KeychainFailure` are both in application ports, which is
  why their branches could use `isinstance`. The branch reads
  `reported_error_code(error) == "CASELIST_TOKEN_UNREADABLE"`: the code comes from the class name,
  it is the same code `failure_codes` records and `_WHAT_STOPPED_A_RUN` is keyed by, and
  `banner_words` already tells an expired login apart by `CaselistAuthExpired.__name__`. It is
  still decided by the error's type, never its message, as `fix_for`'s docstring asks. A rename of
  the class would silently stop the hint; the Mac test uses the real class, so it would fail. The
  alternative, moving the class into `application/ports/caselist_session.py` beside
  `KeychainFailure` and re-exporting it from `token_store`, edits `debate_core.integrations`,
  outside this task's packages; it is listed under Follow-up work for the PM to choose.
* **t35's test file was edited, in one case.** Its
  `test_token_missing_hint_and_words_are_given_to_no_other_code_on_the_mac[token-unreadable]`
  pinned the Mac's old message (`an error recorded as CASELIST_TOKEN_UNREADABLE`) and `hint is
  None`, which is exactly what this task changes. The case now expects the new words, and the test
  asserts what its name says: neither neighbour is given t35's login hint (`!= LOG_IN_AGAIN`). The
  expired login's `hint is None` on the Mac stays pinned by `v1-e40-t33`'s
  `test_a_mac_run_refused_for_auth_expired_keeps_its_notice_word_for_word`. It was edited in the
  tests commit, so it was red with the new test. `v1-e40-t33`'s file is unedited.
* **The hint's wording** follows t35's sentence shape (what is wrong on this machine, a colon, then
  the commands in full): "The caselist_token stored on this machine for the environment cannot be
  read: log out with `debate-research caselist auth logout`, then log in again with
  `debate-research caselist auth login`." I checked that the cure works on such a record:
  `KeyringTokenBackend.delete` and the file backend's `delete` read the raw value or unlink the
  file, and never parse the record, so logout clears an unreadable one.
* **`fix_command` stays `debate-research caselist pull`** on the Mac, as for t35: the hint carries
  the logout and login, and the pull is what runs once they are done.
* **No smoke check was added.** The spec has no smoke node and t35 added none for the same surface;
  the behaviour is the text of a stopped run's notification, covered here end to end through
  `run_pull` and the real monitor.

## Operator follow-ups

None. The affected set is left to the pull request's `ci` check under agreement 10, not handed over.

## Follow-up work

* **Move `CaselistTokenUnreadable` into an application port**, beside `KeychainFailure` in
  `debate_core.application.ports.caselist_session`, re-exported from `token_store`, so `fix_for`
  can tell it apart by `isinstance` like its neighbours. It touches `debate_core.integrations`,
  which this task's packages leave out. E34, if the PM wants it; the behaviour is the same either
  way.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

# Session report: v1-e34-t33-keychain-errors-named

| | |
|---|---|
| Task | `v1-e34-t33-keychain-errors-named` — A keychain failure under launchd names its cause, and clearing a token already gone is no error |
| Spec | [`plan_specs/v1/e34-caselist-sync/t33-keychain-errors-named.yaml`](../../plan_specs/v1/e34-caselist-sync/t33-keychain-errors-named.yaml) |
| Epic / release | `v1-e34-caselist-sync` / `v1.1` |
| Branch | `task/v1-e34-t33-keychain-errors-named` |
| Session status | COMPLETE |

## Summary

A keychain refusal no longer reaches the CLI or a run as `INTERNAL_ERROR`, "a bug in
debate-research". `keyring`'s macOS backend raises a bare `KeyringError` for nearly everything the
keychain answers, but it chains the Security framework's error, whose first argument is the OSStatus.
`KeyringTokenBackend` now reads that number, and never the message. It reports four causes, each with
its own error code and hint: `KEYCHAIN_INTERACTION_NOT_ALLOWED` (-25308, a locked keychain under
launchd), `NO_KEYCHAIN` (nobody logged in), `KEYCHAIN_DENIED` (-128) and `KEYCHAIN_REFUSED_PROGRAM`.
Every other answer is raised as `keyring` raised it and stays `INTERNAL_ERROR`. A delete that finds the
item already gone returns quietly. A scheduled run that meets one of these records the code, and its
notification says in words what stopped the run and carries the hint. All of this is shown by test
against a stand-in keychain and was shown failing first. **Look first at** the ac1 count below. -25308
is defined in `keyring`'s macOS module but never mapped there, so it arrives as a bare `KeyringError`
"Unknown Error". That fits the 2026-10-21 run, though nothing here proves which status that run met.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `keychain-errors` (Keychain errors named) | Done | Counted (ac1), then error classes and failing tests (`8996058`), then the rule (`c1be5a5`), then the runbooks (`8971606`) |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: counts before any rule, from the library's documentation and code, with sources | PASS | [The count](#ac1-the-count-what-keyringtokenbackends-three-calls-can-raise-on-macos), below: read from `.venv/lib/python3.12/site-packages/keyring` at 25.7.0 (the `uv.lock` pin), its README (the wheel's `METADATA`) and Apple's `SecBase.h`/`CSCommon.h` |
| ac2: with a stand-in keyring, a missing item, a locked keychain, a refused program and no keychain each give their own code and hint and quote no message; deleting a token already gone succeeds; an unexpected error is still `INTERNAL_ERROR`; tests shown failing first | PASS | Red run against the skeleton (classes defined, nothing raising them): `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest <the three new test files> -p no:randomly -n 0 -q --tb=no -rfp` → `32 failed, 33 passed`. The failures were every named cause on each of read, store and delete (21), the delete raced by another process (1), `NoKeyringError` (3), all four scheduled runs (4) and three CLI cases (3); the CLI's red output was the 2026-10-21 report word for word, `stopped on an unexpected KeyringError` with the "This is a bug in debate-research" hint. The same tests green after `c1be5a5`: `65 passed in 1.17s` |
| ac3: a scheduled run that fails on a named error records the named code, and its notice gives the hint rather than "a bug" | PASS | `test_pull_names_a_keychain_failure.py`, four runs (-25308, -25307, -128, -25293) as the Mac's agent makes them (`run_pull` in a real `SyncRunMonitor`, moto bucket): the record's `error_class`, the details' `failure_codes` and `hint`, the notification's title, message (written by hand), hint and no "bug"; no keychain message in the run log, the details, the bucket's copies or the notification → `4 passed` (inside the 65 above) |
| Node: Token store tests pass (`uv run pytest packages/debate_core/tests/integrations/opencaselist`) | PASS | `.venv/bin/python scripts/hard_stop.py 115 uv run pytest packages/debate_core/tests/integrations/opencaselist` → `233 passed in 2.24s` |

### ac1: the count, what `KeyringTokenBackend`'s three calls can raise on macOS

Sources: the installed `keyring` 25.7.0, under `.venv/lib/python3.12/site-packages/keyring/`
(`uv.lock` line 1049), its README as shipped in `keyring-25.7.0.dist-info/METADATA`
(<https://pypi.org/project/keyring/25.7.0/>), and Apple's headers in
`/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk/System/Library/Frameworks/Security.framework/Headers/`.

**How the macOS backend raises.** `keyring/backends/macOS/api.py` calls the Security framework, and
`Error.raise_for_status` (lines 111-126) turns a non-zero OSStatus into `api.Error(status, text)`:
`NotFound` for -25300, `KeychainDenied` for -128, `SecAuthFailure` for -25293 and -67030, and a plain
`Error(status, "Unknown Error")` for any other. Lines 17-22 also define
`sec_interaction_not_allowed = -25308`, but nothing maps it, so it is an "Unknown Error".
`keyring/backends/macOS/__init__.py` then wraps these, always `from e`:

| Call | Raises | Source |
|---|---|---|
| `get_password` (the store's read) | `NotFound` → returns `None`; `KeychainDenied` → `KeyringLocked`; any other `api.Error` → bare `KeyringError` | `__init__.py` lines 55-67 |
| `set_password` (the store's write) | `KeychainDenied` → `KeyringLocked`; any other `api.Error` → `PasswordSetError`. Its delete-first ignores `NotFound` | `__init__.py` lines 43-53; `api.py` lines 161-173 |
| `delete_password` (the store's delete) | every `api.Error`, `NotFound` included → `PasswordDeleteError` | `__init__.py` lines 69-77; `api.py` lines 176-184 |
| any call, when `keyring` has no backend | `NoKeyringError` (`KeyringError`, `RuntimeError`) | `backends/fail.py` lines 21-30; `errors.py` line 25 |

The README documents `KeyringError`, `InitError`, `PasswordSetError` and `PasswordDeleteError`, and
that "`delete_password` ... If the password does not exist, it will raise an exception" (`METADATA`
lines 462-477). It does not mention `KeyringLocked` or `NoKeyringError` (`errors.py` lines 21-26).
`InitError` is not raised by the macOS backend.

**The cases the spec names, by OSStatus** (Apple's descriptions from `SecBase.h`, with line numbers;
-67030 from `CSCommon.h` line 108):

| Case | OSStatus | read | store | delete | Code now |
|---|---|---|---|---|---|
| A missing item | -25300 `errSecItemNotFound` (353) | `None` | none (ignored) | `PasswordDeleteError` | none: reads as no token (`CASELIST_TOKEN_MISSING` where a token is needed); a delete returns `False` |
| A keychain a background process may not use, locked or needing a prompt | -25308 `errSecInteractionNotAllowed` (361), "User interaction is not allowed" | `KeyringError` | `PasswordSetError` | `PasswordDeleteError` | `KEYCHAIN_INTERACTION_NOT_ALLOWED` |
| No keychain at all | -25291 `errSecNotAvailable` (344), -25294 `errSecNoSuchKeychain` (347), -25307 `errSecNoDefaultKeychain` (360) | `KeyringError` | `PasswordSetError` | `PasswordDeleteError` | `NO_KEYCHAIN` |
| A prompt answered no, to unlock or to allow the program | -128 `errSecUserCanceled` (335) | `KeyringLocked` | `KeyringLocked` | `PasswordDeleteError` | `KEYCHAIN_DENIED` |
| A refused program | -25293 `errSecAuthFailed` (346), -67030 `errSecCSInfoPlistFailed`; `keyring`'s own text says "make sure executable is signed with codesign util" (`api.py` lines 120-125) | `KeyringError` | `PasswordSetError` | `PasswordDeleteError` | `KEYCHAIN_REFUSED_PROGRAM` |
| `keyring` with no backend | none | `NoKeyringError` | same | same | `KEYRING_UNAVAILABLE` (the store's existing code) |

**What tells them apart.** The exception class distinguishes only two things: `KeyringLocked`, which
is -128 and only on a read or a store, and `NoKeyringError`. Everything else arrives as a bare
`KeyringError`, `PasswordSetError` or `PasswordDeleteError`, whatever the cause. The OSStatus, the
`int` at `__cause__.args[0]`, separates every case in the table on all three calls, and that is what
the store reads. It reads no message, even one that holds a number (a test raises
`ValueError("-25308")` as the cause and gets `INTERNAL_ERROR`).

**Not told apart even by the OSStatus**, so each pair shares one code and its hint covers both:

* a locked keychain whose unlock prompt was cancelled, and a program refused at the access prompt:
  both are -128 (`KEYCHAIN_DENIED`);
* under launchd, a locked keychain and an item whose access list does not yet name this program:
  both need a prompt that cannot be shown, so both are -25308 (`KEYCHAIN_INTERACTION_NOT_ALLOWED`).

**What the count rests on, and what it does not.** The mapping from exception to OSStatus is
`keyring`'s code, read, and the tests run it: the stand-in keychain is `keyring`'s own
`macOS.Keyring` with only its `api` module replaced. The descriptions of what each OSStatus means are
Apple's header text. Which OSStatus a real Mac returns in each situation, for example that no one
logged in gives -25307 rather than -25291, was not measured, because no test may touch a real
keychain. The run of 2026-10-21 raised a bare `KeyringError`, so it met one of -25308, -25291,
-25294, -25307, -25293, -67030 or an unlisted status, and nothing recorded then can say which. From
now on the CLI's `--json` failure shows `details.os_status`, and a run records the code.

## Files changed

* `packages/debate_core/src/debate_core/application/ports/caselist_session.py`: `KeychainFailure` and
  its four causes, each with its `CAUSE` and `HINT`. They live in the token store's port so that
  `fix_for` can give the hint without the application layer importing the adapter. The module
  docstring lists the codes and their OSStatus.
* `packages/debate_core/src/debate_core/integrations/opencaselist/token_store.py`: `KeyringTokenBackend`
  translates by OSStatus on read, store and delete (`_os_status`, `_named_keychain_failure`,
  `_KEYCHAIN_FAILURES`). `NoKeyringError` becomes `KeyringUnavailable`. A delete answered -25300
  returns `False`.
* `packages/debate_core/src/debate_core/application/caselist_sync.py`: `fix_for` returns a
  `KeychainFailure`'s hint, for a stopped run and for a stage alike.
* `packages/debate_core/src/debate_core/application/sync_runs.py`: words for the four codes in
  `_WHAT_STOPPED_A_RUN`.
* Tests: `packages/debate_core/tests/integrations/opencaselist/stand_in_keychain.py` (the stand-in
  Security API under `keyring`'s own macOS backend) and `test_keychain_errors_named.py` (ac2, 57
  tests); `packages/debate_core/tests/application/caselist/test_pull_names_a_keychain_failure.py`
  (ac3); `packages/debate_cli/tests/commands/test_caselist_auth_keychain_errors.py` (the CLI's
  envelope through the real composition root).
* `docs/runbooks/caselist-scheduled-sync.md`, "When something goes wrong": the codes, their OSStatus
  and their fixes. `docs/runbooks/caselist-cutover.md`, the fallback week's token check: a pointer
  there.

## Deviations from the spec

None.

## Decisions and assumptions

* **Where the codes are named and documented.** A code is the `DomainError` class name in upper snake
  case, as `debate_core.application.errors.error_code_of` and `debate_cli.exit_codes.error_code_for`
  name every other. They are documented in the `caselist_session` module docstring and in the
  scheduled-sync runbook's table. They exit `1` (`DOMAIN_FAILURE`). None is on a retry list, so the
  banner says `needs a person`: a run cannot log the Mac in.
* **A missing item gets no new code.** `keyring` reads it as no password, and the store already turns
  that into `CASELIST_TOKEN_MISSING`, whose message says to run `caselist auth login`. That is the
  spec's first hint, so the missing-item case is the existing code.
* **The delete keeps its read first**, which already made a delete of a missing item quiet.
  What could still raise was an item deleted between the read and the delete (`PasswordDeleteError`
  from -25300), and that now returns `False`. Removing the read was not needed.
* **`NoKeyringError` maps to `KeyringUnavailable`**, the store's existing code for "no usable
  keychain", because the class alone identifies it. A `KeyringLocked` with no OSStatus (from
  `keyring`'s Linux backends) stays `INTERNAL_ERROR`, since only the macOS backend was counted.
* **The keyring's error is not chained** (`raise ... from None`), so `--verbose` cannot print its
  message beneath a named failure. `details.os_status` keeps the number. An unexpected error is
  re-raised as it came, with its chain intact, so `--verbose` still shows it.
* **Shared with the cloud runner, unchanged in behaviour.** `fix_for` and `_WHAT_STOPPED_A_RUN`
  serve the cloud run too. The four new codes cannot arise there, because the cloud's token store
  is Secrets Manager and never calls `keyring`, so its notifications are unchanged. The Secrets
  Manager backend was not touched.
* **No smoke check.** A smoke check runs an installed build against this machine's real keychain, or
  on CI with none, and a refusal cannot be staged there without one. The CLI test covers the surface
  through the real composition root instead.
* **Mutants** (agreement 8; no Hypothesis in these tests, and each run still had a fresh
  `HYPOTHESIS_STORAGE_DIRECTORY`): each mutant was applied to `c1be5a5`, the three new test files were
  run, and the file was restored from HEAD. All eight were caught at an assertion:

  | Mutant | Result |
  |---|---|
  | 1. A named error falls back to `INTERNAL_ERROR` (-25308 unmapped) | caught, 5 failed |
  | 2. The keychain's message quoted in the named error | caught, 23 failed |
  | 2b. The keychain's error kept as the named error's `__cause__` | caught, 7 failed |
  | 3. Deleting a token already gone raises | caught, 2 failed |
  | 4. Two codes swapped (-128 and -25293) | caught, 9 failed |
  | 5. An unexpected status given a named code | caught, 16 failed |
  | 6. `fix_for` gives no keychain hint | caught, 25 failed |
  | 7. A stopped run's words for `NO_KEYCHAIN` dropped | caught, 1 failed |

### Checks run before this report

* **Affected set**: `uv run scripts/affected_tests.py` selected 303 of 624 test files, 7,060 tests,
  because `caselist_sync.py` and `sync_runs.py` are hub modules.
  `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python scripts/affected_tests.py --run` was
  stopped at its 115-second limit with about 3% done (exit 124). Under agreement 10 that run is left
  to the pull request's `ci`, with no hand-off. Within the limit I ran:
  * the always-run list (`tests/architecture/`, `tests/specs/`, `test_app.py`,
    `test_help_rendering.py`, `test_container_factories.py`), `integrations/opencaselist`, and the
    CLI's `caselist auth`, `auth` Secrets Manager, keychain and `caselist pull` tests: `701 passed in
    31.89s`;
  * every test file that imports `sync_runs`, `fix_for`, `caselist_session` or `token_store` (48
    files, `git grep -l -E "sync_runs|fix_for|caselist_session|token_store"`): `954 passed in 94.32s`.
* `ruff format --check .` → `1727 files already formatted`; `ruff check .` → `All checks passed!`
* `pyright packages/debate_core packages/debate_cli` → `0 errors, 0 warnings, 0 informations`
* `lint-imports` → `Contracts: 20 kept, 0 broken.`; `scripts/check_thin_handlers.py` → OK
* `scripts/check_command_blocks.py --base origin/dev` → OK; `scripts/docs_index.py
  --check-descriptions` → OK; `scripts/check_links.py` → OK
* `uv run scripts/validate_specs.py` → `OK: 545 files, 41 epics, 482 tasks, 22 releases`
* The spec on `origin/dev` differs from this branch's only in `status.phase`, and the two merges into
  dev during the session (#718, #719) touch none of this task's files.

## Operator follow-ups

None. The full affected set is left to the pull request's `ci` under agreement 10, with no hand-off.

## Follow-up work

* **A run stopped by `CASELIST_TOKEN_MISSING` still has no hint.** Its banner reads "stopped: an
  error recorded as CASELIST_TOKEN_MISSING" with `caselist pull` as the fix command. The code is
  shared with the cloud run, whose missing token is in Secrets Manager and whose fix is the renew
  task, so it was left alone as the PM asked. A Mac-only hint ("log in again with `caselist auth
  login`", in `fix_for` when not `bucket_mode`) and words for the code would be a small task in E34
  or E40.
* **Which OSStatus a real Mac returns under launchd** is not measured (see ac1). The next refusal
  records its code, and `caselist auth status --json` shows `details.os_status`. Reading it once, by
  hand, the next time the Mac is logged out would confirm the table. It is not a test.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-31

**Notes:**

The count is the useful finding. -25308 is defined in `keyring` but never mapped, so a locked
keychain under launchd has always reached us as "a bug". That fits 2026-10-21, though nothing can now
prove which status that run met.
1. **ac1 passes.**
   * Every row cites the installed `keyring` 25.7.0 at file and line, its shipped README, and
     Apple's headers.
   * The report says plainly what the count rests on (the code's mapping, run by the tests) and what
     it doesn't (which OSStatus a real Mac returns in each case).
2. **ac2 passes.**
   * Red: 32 failed against classes nothing raised, and the CLI's red output was the 2026-10-21
     report word for word.
   * Green: 65.
   * The stand-in is `keyring`'s own macOS backend with only its `api` module replaced. That is the
     strongest stand-in available without a real keychain.
   * The PM read `token_store.py`: only an `int` at `__cause__.args[0]` is read, a message never
     (a test proves `ValueError("-25308")` stays `INTERNAL_ERROR`), and an unmodelled status is
     re-raised as it came.
3. **ac3 passes.** Four scheduled runs, each with its code, its words, its hint and no "bug", and no
   keychain message in the log, the details, the bucket copies or the notification.
4. **Mutants:** all eight are caught, the PM's five plus 2b (the cause chain kept), 6 and 7.
5. **Decisions accepted:**
   * codes named as every other `DomainError`'s, and documented in the port and the scheduled-sync
     runbook;
   * a missing item keeps `CASELIST_TOKEN_MISSING`, which already gives the spec's first hint;
   * the two pairs that even the OSStatus can't separate share one code, with a hint covering both;
   * `NoKeyringError` mapped to `KeyringUnavailable`;
   * a Linux `KeyringLocked` with no status left as `INTERNAL_ERROR`, since only macOS was counted;
   * `raise ... from None` on a named failure, with `details.os_status` keeping the number;
   * the shared `fix_for` and run words leave the cloud run unchanged, since Secrets Manager never
     calls `keyring`;
   * no smoke check, since no refusal can be staged without a real keychain. The CLI test covers
     the composition root.
6. **Follow-ups, the PM's rulings:**
   * **The Mac-only hint for `CASELIST_TOKEN_MISSING`:** one p3 E34 task in the PM's next batch.
     Outside bucket mode the hint is `caselist auth login`, and bucket mode keeps its renew-task
     fix.
   * **Measuring the real OSStatus:** not a task. The next refusal records its code, and the PM
     reads it then.
7. **Closing checks:** the affected set (303 files through two hub modules) is left to the PR's
   `ci` under agreement 10. The always-run list with the auth and pull tests (701), every importer
   of the four changed modules (954), ruff, pyright, lint-imports, thin handlers, the doc checks and
   the specs are clean.
8. **Merge:** a plain `scripts/task pr` once `ci` is green. No operator step follows. This is v1.1
   work.

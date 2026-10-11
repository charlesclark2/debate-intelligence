# Session report: v1-e29-t07-missing-profile-not-retryable

| | |
|---|---|
| Task | `v1-e29-t07-missing-profile-not-retryable` — A profile missing from the AWS config is a configuration error, not an expired session |
| Spec | [`plan_specs/v1/e29-cloud-evidence-store/t07-missing-profile-not-retryable.yaml`](../../plan_specs/v1/e29-cloud-evidence-store/t07-missing-profile-not-retryable.yaml) |
| Epic / release | `v1-e29-cloud-evidence-store` / `v1.1` |
| Branch | `task/v1-e29-t07-missing-profile-not-retryable` |
| Session status | COMPLETE |

## Summary

A profile the AWS config does not define is now its own error, `StoreProfileNotConfigured`, with
the code `STORE_PROFILE_NOT_CONFIGURED`. It exits 1 in every command, names the setting the
profile's name came from, and never offers a login or names the AWS config's path. A bucket's
`AccessDenied` now gets its hint in the S3 adapter, so `caselist publish`, `caselist status`,
`store sync` and `caselist remove` show it, and `caselist pull` reads it from the error. All four
Goal criteria pass and the phase is `Succeeded`.

**Read this first: the kickoff brief's picture of today's pull was half right.** I measured both
ways a missing profile can reach `caselist pull`:

* **A setting that names no profile, which is the real misconfiguration.** boto3 refuses to build
  a session, so the bucket's adapter cannot be built, and the run ends before any stage. Before
  this task that was exit 3 under `STORE_CREDENTIALS_EXPIRED`; it is now exit 1 under
  `STORE_PROFILE_NOT_CONFIGURED`. In both cases nothing is fetched and **no run is recorded and no
  notification is sent**, because the run's monitor publishes run records through the same
  profile and cannot be built either. So the weekly agent never reported "pending, log in" for a
  misspelt profile: it reported nothing. That silence is unchanged and is the first item under
  Follow-up work.
* **botocore's `ProfileNotFound` arriving inside the publish stage**, which a test can produce and
  a real machine cannot once its client is built. This is the case the brief describes. Before:
  publish `pending`, exit 0. Now: publish `failed` with the new code, exit 1, every imported
  snapshot still owed.

One thing got more conservative: a missing profile no longer falls back to this machine's copy of
the suppression list, as an expired session does. It fails the import closed (Decision 6).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `profile-not-found`: its own error and exit 1 | Done | Adapter translation, the setting name passed from the composition root, the exit mapping, the `AccessDenied` hint's move, tests and docs. |

## Acceptance criteria

The error code is `STORE_PROFILE_NOT_CONFIGURED`. Its retryability is defined in
`packages/debate_cli/src/debate_cli/exit_codes.py`, by `RETRYABLE_STORE_FAILURES`: the class is
deliberately not on that list, and the list's docstring now says so. No list in
`debate_core.application` decides retryability, so nothing was added there for it.

"Red" below is a run against the source as it was before this task. The first red run was made
before any implementation and is the first commit on the branch, "Add failing tests…". The final
red run used the finished tests against the pre-task source, which was then restored.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: `store sync` with a profile the config lacks, and `caselist remove --execute` with `DEBATE_REMOVAL_PROFILE` naming one, exit 1 with a message naming the setting, shown failing first | PASS | `uv run pytest packages/debate_cli/tests/test_missing_profile_and_missing_grant.py -k TestAProfileTheAwsConfigLacks` and `tests/smoke/test_caselist_remove_smoke.py::test_a_removal_profile_missing_from_the_aws_config_is_refused_with_nothing_changed`. Red: `assert 3 == 1` for `store sync`, `store sync --apply`, `store ls`, `store get`, `caselist publish`, `caselist status`, `caselist runs --remote`, `caselist remove`, `caselist unsuppress` and `caselist remove --execute`; the code was `STORE_CREDENTIALS_EXPIRED`. Green: all pass. The message begins `AWS profile '<name>', named by storage.s3.aws_profile, is not defined in this machine's AWS config`, or `named by DEBATE_REMOVAL_PROFILE` for the takedown. |
| ac2: an expired SSO session still exits 3 with the `aws sso login` hint, by the existing tests | PASS | `uv run pytest packages/debate_cli/tests/test_retryable_store_failures.py packages/debate_cli/tests/commands/test_store.py -k expired` → 10 passed. Neither file is changed by this branch (`git diff` against the start commit is empty for both). |
| ac3: v1-e01-t20's consumer table is updated for the changed code, and the CLI README says what the new error means | PASS | [`v1-e01-t20`'s report](v1-e01-t20-retryable-failures-exit-3.md#updated-by-v1-e29-t07-missing-profile-not-retryable-2026-10-11) has a dated section under its consumer table, one row per consumer; nothing already in that report is edited. `packages/debate_cli/README.md`, "Exit codes", has a paragraph on what `STORE_PROFILE_NOT_CONFIGURED` means. |
| ac4: a bucket's `AccessDenied` gets its hint in the S3 adapter; the four commands show it; the sync uses the adapter's hint; code and exit unchanged; shown failing first for `caselist publish` and `store sync` | PASS | `uv run pytest packages/debate_cli/tests/test_missing_profile_and_missing_grant.py -k TestABucketThatRefusesTheProfile`. Red: `caselist publish`, `store sync`, `store sync --apply`, `store get`, `caselist status` and a planned `caselist remove` had `hint: null`; `caselist remove --execute` had the hint `aws sso login --profile debate-dev-evidence-removal` for a refusal. Green: all pass, each still `STORE_ACCESS_DENIED` with exit 3. The sync's own sentence is deleted and `_fix_for` reads `error.hint`. |
| The pull case from the brief: a missing profile fails the publish stage with the new code and exits 1, the pending-work file is as v1-e34-t18 settled it; expiry beside it | PASS, with the measurement in the Summary | `uv run pytest tests/smoke/test_caselist_pull.py -k "profile or answered_by_botocore"`. Red: `test_a_profile_the_aws_config_lacks_fails_publish_with_one_and_everything_imported_stays_owed` got exit 0 with publish `pending`; `test_a_profile_setting_that_names_no_profile_in_the_aws_config_ends_the_pull_with_one` got exit 3. Green: both pass. `test_an_expired_session_answered_by_botocore_still_leaves_publish_pending_with_the_login` passed before and after. |
| Node criterion: store and CLI tests pass | PASS | `uv run pytest packages/debate_core/tests/integrations packages/debate_cli/tests` → 1345 passed in 46 s. |
| Forbidden: mapping an expired, unavailable or refused store to anything but exit 3 | PASS | ac2's tests, plus `test_output.py`'s retryable list, unchanged. |
| Forbidden: a path from the operator's machine in the message | PASS | The CLI, adapter and smoke tests each assert that the test's own AWS config path, its file name, the installation directory and the home directory are absent from the whole envelope. |

Totals: first red run, 41 failed and 28 passed across the adapter and CLI files, and 2 failed and
1 passed for the pull. Final red run over the criteria's tests: 21 failed, 2 passed (the expiry
test and a control). The same selection on the finished code: 23 passed.

**The whole suite**, after rebasing on `dev`, as three commands that together are the default
selection (`-n auto --cov -m "not slow and not live"`):

| Paths | Result |
|---|---|
| `packages/debate_core/tests` | 3814 passed in 52 s |
| `packages/debate_cli/tests` | 506 passed in 29 s |
| `packages/debate_api/tests packages/debate_workers/tests tests` | 1281 passed, 1 skipped in 74 s |

The skip is the parser evaluation's existing one. `ruff check`, `ruff format --check`, `pyright`,
`lint-imports`, `check_thin_handlers.py`, `validate_specs.py`, `docs_index.py --check-descriptions`,
`check_command_blocks.py --base origin/dev` and `check_links.py` all pass.

### Mutation results

Each mutant was applied to committed code, run against the S3 adapter's test directory and the
ten other test files that cover the change (391 tests), and restored with `git checkout`, with the
tree checked clean afterwards. Every run set `HYPOTHESIS_STORAGE_DIRECTORY` to a new, empty
directory. No run errored at collection, so every catch below is a test that ran and failed. The
runs were made before the rebase on `dev`, which brought specs and documents only.

| What was changed | Caught | Tests that failed |
|---|---|---|
| **The `ProfileNotFound` branch.** Translated to `StoreCredentialsExpired` again | Yes | 27 |
| The branch removed, so it falls through to `StoreUnavailable` | Yes | 28 |
| **The retryability entry.** `StoreProfileNotConfigured` added to `RETRYABLE_STORE_FAILURES` | Yes | 21 |
| **The hint text: the setting is named.** The setting not passed to the error | Yes | 21 |
| The hint no longer names the setting | Yes | 18 |
| The composition root swaps the two settings' names | Yes | 14 |
| The adapters drop the setting for an error raised by a call | Yes | 5 |
| **The hint text: the path is absent.** The hint ends with the AWS config's path | Yes | 16 |
| The message says where the AWS config is | Yes | 19 |
| The hint offers `aws sso login` | Yes | 17 |
| **The `AccessDenied` hint's move.** The adapter gives a denial no hint | Yes | 19 |
| The adapter's general denial sentence removed | Yes | 17 |
| The denial hint loses the runbook | Yes | 18 |
| The denial hint offers `aws sso login` | Yes | 16 |
| The denial hint drops the profile's name | Yes | 11 |
| The sync ignores the adapter's hint | Yes | 5 |
| The sync writes its own grant sentence again | **No, then yes** | 0, then 4 |
| **The sync and the new error.** The publish stage does not catch it | Yes | 2 |
| The sync gives it no hint | Yes | 2 |

The one survivor mattered. The stage tests only looked for words that the adapter's sentence and
a sentence written in the sync both contain, so they could not tell which one they were reading.
They now require the adapter's hint verbatim, and the profile's name, which only the adapter is
told.

## Files changed

* `packages/debate_core/src/debate_core/integrations/s3/`:
  * `errors.py`: the `ProfileNotFound` branch, `S3Call.profile_setting`, the denial hint, and
    `GRANTS_ARE_LISTED_IN`.
  * `client.py`, `object_store.py`, `snapshot_store.py`, `version_store.py`: a `profile_setting`
    argument, carried to every `S3Call`.
* `packages/debate_core/src/debate_core/application/errors.py`: the `StoreProfileNotConfigured`
  class (Deviation 1).
* `packages/debate_core/src/debate_core/application/caselist_sync.py`: the lines listed under
  [Lines changed in `caselist_sync.py`](#lines-changed-in-caselist_syncpy) (Deviation 2).
* `packages/debate_cli/src/debate_cli/`:
  * `container.py` passes each adapter the name of the setting its profile came from.
  * `exit_codes.py`, `output.py`, `commands/store.py`, `commands/caselist.py`,
    `commands/caselist_pull.py`: docstrings only. The mapping needed no code change, because the
    new class is on no retryable list.
* Tests:
  * New: `packages/debate_cli/tests/test_missing_profile_and_missing_grant.py` and
    `packages/debate_core/tests/integrations/s3/test_s3_missing_profile.py`.
  * Extended: `test_s3_error_mapping.py`, `test_errors.py`, `test_output.py`,
    `test_pull_stage_failure_codes.py`, `test_pull_parses_new_sources.py`,
    `test_sync_skips_suppressed_downloads.py`, `tests/smoke/test_caselist_pull.py`.
  * One assertion changed from 3 to 1: `tests/smoke/test_caselist_remove_smoke.py`.
  * The fakes that raised a bare `StoreAccessDenied` for a missing grant now build it with the
    adapter's own translation, so the stage tests read the adapter's hint and not a stub's.
* Docs: `packages/debate_cli/README.md`, `packages/debate_core/README.md`,
  `docs/guides/evidence-store-cli.md`, `docs/runbooks/caselist-scheduled-sync.md`,
  `tests/smoke/README.md`, and the dated section in `v1-e01-t20`'s report.

### Lines changed in `caselist_sync.py`

For `v1-e34-t19`. Line numbers are on this branch, rebased on `dev` at `653a398`. Nine lines
added and ten removed; `sync_runs.py` and the run record are untouched.

| Lines | Change |
|---|---|
| 456 | `StoreProfileNotConfigured` added to the import from `application.errors`. |
| 3248, in `_publish_stage` | `except (StoreAccessDenied, StoreUnavailable)` also names `StoreProfileNotConfigured`, so the stage fails on it instead of the error ending the run. |
| 4307 to 4312, removed | The `_MISSING_GRANT_FIX` constant. |
| 4322 to 4324, in `_fix_for`'s docstring | One sentence: the fix is the adapter's. |
| 4332 to 4335, in `_fix_for` | The `StoreAccessDenied` branch returns `f"The bucket refused {error.operation}: {error.hint}."` when the error has a hint, and a new branch does the same for `StoreProfileNotConfigured`. An error with no hint gets none. |

`v1-e34-t19`'s ac7 gives each failed stage's notification the stage's hint. That hint is still
`StageRecord.hint`, built by `_RunTally.fail` exactly as before; only the text inside it changed.

## Deviations from the spec

1. **`debate_core.application.errors` is outside `constraints.packages`.** The brief allowed it:
   the class `StoreProfileNotConfigured`, its entry in the hierarchy diagram and `__all__`, and two
   words of `StoreError`'s docstring ("The three errors below" became "The errors below"). The
   code's retryability did not need a change there (see Acceptance criteria).
2. **`debate_core.application.caselist_sync` is outside `constraints.packages` too.** ac4 requires
   the sync to use the adapter's hint, and the brief asked for as few lines as possible. I also
   added the new class to the publish stage's `except`, which ac4 does not ask for: without it a
   `ProfileNotFound` inside the stage would end the run as a raised error, not as a failed stage,
   which is what the brief asks the pull to show.
3. **The brief said an expired store "still exits 3" through `caselist pull`.** Inside the publish
   stage it does not and did not: the stage is `pending` and the run exits 0, which is the
   v1-e34-t13 rule. The new expiry test asserts that. Exit 3 is what an expired session gives every
   other command, which ac2's tests show.
4. **The brief said today's stage "is pending and exits 0 or 3".** Measured: pending and 0 when the
   error arrives in the stage; no stage at all and 3 when the setting names no profile. See the
   Summary.

## Decisions and assumptions

1. **The name.** `StoreProfileNotConfigured` and `STORE_PROFILE_NOT_CONFIGURED`. The alternative
   was `StoreProfileNotFound`, which reads like `NotFound`, an answer about a record.
2. **Who knows the setting.** The adapters read no settings, so the composition root passes the
   setting's name beside the profile: `storage.s3.aws_profile` or `DEBATE_REMOVAL_PROFILE`. With no
   profile passed, the name came from botocore's own chain and the error names `AWS_PROFILE`. A
   profile passed without its setting claims none. The alternative was a default in the adapter,
   which would name the everyday setting for a takedown's profile.
3. **The hint is a sentence, not a command.** It says to correct the setting or add the profile,
   and points at `docs/runbooks/evidence-store.md`. The old hint was `aws configure sso --profile
   …`, a command that writes to the AWS config. botocore's own message is not passed on.
4. **The real misconfiguration still ends the pull before any stage.** The conservative choice.
   The alternative is to defer the error to first use, so that download and import run and only
   publish fails, or to let the monitor record the run. Either changes when and whether the weekly
   run captures and notifies, which touches the run record `v1-e34-t19` is changing.
5. **`caselist remove --execute` raises the new error bare.** `removal_service` wraps only
   `StoreCredentialsExpired` in `TakedownPreflightFailed`, and I may not edit it. Exit 1 either
   way. The message no longer says "nothing was deleted"; the tests prove nothing was.
6. **A missing profile does not fall back to the local suppression list.** As
   `StoreCredentialsExpired` it did. It now fails the import closed, like a refusal. The
   alternative was to keep the fallback, which is an extension of a PM decision (v1-e34-t07) to a
   case where no login is coming. Reachable only when the error arrives in a call.
7. **Every denial code gets a hint.** KMS denials and a bucket-root listing keep their specific
   first sentence and gain the runbook pointer. The rest, including `InvalidAccessKeyId` and
   `SignatureDoesNotMatch`, get "lacks a grant", as the sync already said of every bucket refusal.
   The hint names the profile when the adapter has one, because a takedown holds two.
8. **v1-e01-t20's table gets a dated section, not edited rows.** That report is reviewed history.
9. **The suite ran as three commands, not two.** The second half was measured at 105 s earlier
   today and this branch adds tests to it.
10. **`scripts/task sync` was run once.** `dev` moved by the PM's close-out commit (`653a398`),
    not by `v1-e34-t19`. The rebase was clean and nothing was pushed, because the branch is not on
    `origin`. The whole suite was run after it. `v1-e34-t19` had not merged when this was written.

## Operator follow-ups

None.

## Follow-up work

* **A misspelt profile makes the weekly agent fail silently (E34).** The pull ends before its
  monitor is built, so there is no run record and no notification; only launchd's exit code, now 1,
  and the error on the agent's stdout log. Worth settling before the agent is relied on after
  Wednesday's reinstall. Two ways: build the monitor's bucket lazily so the refusal is recorded and
  announced like the other refusals to start, or have `doctor` and `install.sh --check-launchd`
  confirm that the configured profile is defined. Until then, any bucket command in the agent's
  environment shows it: `caselist runs --remote` exits 1 with this error when the profile is
  missing, and 3 with the login hint when it exists and the session has expired.
* **`removal_service._authorised` and the new error (E30).** Wrap it in
  `TakedownPreflightFailed` like an expired session, or leave it bare. Wrapped, the message would
  say "nothing was deleted" again; `exit_codes` already keeps a wrapped one at 1 (tested).
* **`caselist_sync.py`'s docstrings do not mention the new error (E34).** The module docstring's
  "Only an expired session is pending" paragraph and `_publish_stage`'s docstring were left alone
  to keep the diff small for `v1-e34-t19`. One sentence each, after it merges.
* **Services that end a run on a session error do not name the new class (E29, E30).**
  `evidence_sync`, `publish_service` and `parsed_publish` re-raise `StoreCredentialsExpired` and
  `StoreAccessDenied` so that one failure is not reported once per object. The new error arriving
  in a call would be recorded per object instead, and the pull's parse stage would try every
  caselist. No real machine can produce that once its client is built.
* **`InvalidAccessKeyId` and `SignatureDoesNotMatch` are told "lacks a grant" (E29).** They are
  credential faults, not grants. Not reachable with SSO profiles; a sentence of their own if static
  keys are ever used.
* **v1-e01-t20's Decisions asked whether a missing profile should stay a 3.** This task answers it.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

# Session report: v1-e34-t13-pull-stage-failure-classes

| | |
|---|---|
| Task | `v1-e34-t13-pull-stage-failure-classes` — A pull stage that fails on a retryable cause ends the run with exit 3 |
| Spec | [`plan_specs/v1/e34-caselist-sync/t13-pull-stage-failure-classes.yaml`](../../plan_specs/v1/e34-caselist-sync/t13-pull-stage-failure-classes.yaml) |
| Epic / release | `v1-e34-caselist-sync` / `v1.1` |
| Branch | `task/v1-e34-t13-pull-stage-failure-classes` |
| Session status | COMPLETE |

## Summary

A failed stage of `caselist pull` now records the error code of every failure behind it, the same
code `error_code_for` gives that exception, and the command decides its exit from the codes of the
failed required stages with `v1-e01-t20`'s `exit_code_for_failure_codes`. A run exits 3 only when
every one is retryable, 1 as soon as one is not, and 0 when no required stage failed. Only an
expired session is "pending". A store that refused fails its stage, exits 3, and carries a `hint`
naming the fix: a permission under `storage.data_dir` for this machine, or a grant the profile
lacks for the bucket. Neither hint mentions `aws sso login`. The three remaining filesystem stores
translate `PermissionError`, a listing of an unreadable tree raises instead of listing nothing, and
`caselist publish` reads a failed manifest's code from `manifest_error_code`. The Goal is
`Succeeded`: every criterion passed and no operator step is needed.

**Read first:**

- **Deviation 1: a refusal in the report stage alone exits 0, not 1 or 3.** Your rule says "0 when
  no required stage failed", and report is not a required stage. ac2's text reads as "exit 1 or 3".
  I followed your rule. The stage still fails, names the fix and never pends.
- **Deviation 2: a bucket that does not answer the publish stage's listing is now a failed stage,
  not an exception.** `v1-e01-t20` let it escape as exit 3. Nothing then recorded the imported
  snapshots as owed, so no later pull would have published them. It is still exit 3, but
  `error.code` is `CASELIST_PULL_INCOMPLETE` where it was `STORE_UNAVAILABLE`, and the next run
  publishes what was left.
- **Deviation 3: the daily cap on a camp download needed a class of its own**,
  `DailyDownloadLimitReached`. It arrives as the same `ProviderRateLimited` a burst limit does, so
  under the one rule it would have carried the retryable code and exited 3.
- **`v1-e31-t06` merged during the session.** I ran `scripts/task sync`; the rebase was clean and
  nothing was pushed. Its publisher does not read the prefix, so none of its files changed. It
  added two callers of the local store, both in the callers table and both tested.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `stage-classes`: Classified stage failures and the remaining stores | Done | The core sync tests were written and run red before any code (24 failed, 2 passed). The whole test set was then run against the start commit's source: 100 failed, 232 passed. On the branch every test passes, and 33 of 33 mutants are caught. |

## Acceptance criteria

Results are from the branch tip `d377c52`, rebased onto `origin/dev` at `a1cb396`, plus this report.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1**: a pull whose import or publish fails only because the store did not answer, or whose download fails only on a 5xx or non-daily 429, exits 3; any deterministic stage failure exits 1; each shown failing first | PASS | [Shown failing first](#shown-failing-first). Through the real OpenCaselist client and respx: 503 past the retries, a timeout, a refused connection and a 429 with `Retry-After: 600` each exit 3; a 404, a size ceiling, a 401 and the daily cap on a camp file each exit 1; one 503 beside one unreadable zip exits 1. Against moto: a bucket that does not answer the suppression list or the publish listing exits 3; a torn list exits 1. |
| **ac2**: a local `PermissionError` and a missing grant in publish or report fail that stage and name the fix, never `aws sso login`; an expired session still marks publish pending with exit 0; shown failing first | PASS, with Deviation 1 | `test_a_local_refusal_in_publish_…` (core and smoke): publish `failed`, `STORE_ACCESS_DENIED`, exit 3, hint names "the blob directory" and `storage.data_dir`, snapshots still owed. `test_a_missing_grant_in_report_…` (core and smoke): report `failed`, hint says the profile lacks a grant and points at `docs/runbooks/evidence-store.md`. `test_an_expired_session_still_leaves_publish_pending_…`: `pending`, exit 0, one notification naming `aws sso login … && … --publish-pending`. No stage text or notification of the two refusals contains `aws sso login`. |
| **ac3**: the three filesystem stores turn a `PermissionError` into `StoreAccessDenied` naming the directory's role, `list_objects` raises instead of listing nothing, and `caselist publish` reads a manifest failure's code from a structured field | PASS | `uv run pytest packages/debate_core/tests/integrations/local/test_refused_directories.py` → 16 passed. [Callers of the local stores](#callers-of-the-local-stores-ac3). `test_a_failed_manifests_code_is_read_from_its_field_never_from_its_sentence` (2 cases) and `test_a_manifest_that_fails_on_its_own_states_its_code_in_a_field_of_its_own`. |
| **ac4**: `v1-e01-t20`'s consumer table is brought up to date for every changed code, and each new guard is mutated and shown caught | PASS | [Exit-code and error-code consumers](#exit-code-and-error-code-consumers-ac4). [Mutation testing](#mutation-testing): 33 of 33 caught. |
| Node `stage-classes`: `uv run pytest packages/debate_core/tests/application/caselist packages/debate_cli/tests` | PASS | `1022 passed in 48.80s` |
| Forbidden: mapping a deterministic outcome to exit 3 | PASS | The retryable codes are an allow-list of five store and provider classes. `test_the_exit_code_is_three_only_when_every_required_failure_is_retryable` (10 hand-written cases) and 12 new cases of `exit_code_for_failure_codes`. A code on no list, an unmodelled error and a failed stage with no code all exit 1. |
| Forbidden: reporting a local refusal or a missing grant as waiting for an AWS login | PASS | Publish and report pend only on `StoreCredentialsExpired`. The report stage pends only when publish is pending. Both "routed back to pending" mutants are caught. |
| Forbidden: a path, camp title or inbox file name in a stage reason, error code or hint | PASS | `assert_names_nothing_of_this_machine` runs in 14 of the core scenarios. It searches every stage's reason, codes and hint for the data directory, the temporary directory, the home directory, a probe camp title and two inbox names. `test_a_torn_local_suppression_list_…` shows the one message that did carry the data directory's path. |
| The run summary: schema bumped from 3, and schema-3 records still read | PASS | `RUN_SUMMARY_SCHEMA_VERSION` is 4. The run log's record schema is unchanged. Three tests read a stored record written by the build at the start commit, and pass on that source and on the branch: `test_runs_still_reads_the_run_log_a_schema_3_build_wrote` (CLI), `test_the_run_monitor_still_reads_…` and `test_the_stored_summary_is_a_schema_3_one` → `3 passed` both times. |
| Default suite, in two commands so each stays under two minutes | PASS | `uv run pytest -m "not slow and not live" packages --no-cov -q` → `3748 passed in 57.52s`. The same over `tests` → `1244 passed, 1 skipped, 1 warning in 47.30s`. The skip is the parser eval waiting on human corrections; the warning is the smoke harness's blocked-socket check. |
| Static checks | PASS | `ruff format --check .` 573 files formatted; `ruff check .` all passed; `pyright` 0 errors; `lint-imports` 12 kept, 0 broken; `check_thin_handlers.py` OK, 21 handlers; `check_links.py` OK; `docs_index.py --check-descriptions` OK. |
| `uv run scripts/validate_specs.py` after `set-phase … Succeeded` | PASS | `OK: 323 files, 38 epics, 265 tasks, 20 releases`; `--require-succeeded` → `Succeeded`. |

### Shown failing first

The core sync tests were written before any code and run at the start commit: 24 failed and 2
passed. The 2 are the stored-record tests, which must pass before and after.

For the full set I checked out the start commit's `packages/debate_core/src` and
`packages/debate_cli/src` over a clean, committed tree, ran the tests, restored with
`git checkout HEAD --` and confirmed `git status --porcelain` was empty and `git diff --quiet HEAD`
held. Result: **100 failed, 232 passed, 1 error in 16.41s**. The error is
`test_recorded_failure_codes.py`, which cannot be collected because it imports the functions this
task adds. On the branch all of them pass.

| Scenario (your list) | Test | Before | After |
|---|---|---|---|
| Store outage in import → 3 | smoke `…refused_unavailable_or_torn…[unavailable]` | exit 1 | exit 3, `STORE_UNAVAILABLE` |
| Store outage in publish → 3 (the listing) | smoke `test_a_bucket_listing_that_does_not_answer_…` | exit 3 by escaping, `error.code` `STORE_UNAVAILABLE`, no summary, nothing owed | exit 3, publish `failed`, 5 snapshots owed, next run publishes them |
| Store outage in publish → 3 (the uploads) | core `test_uploads_the_bucket_did_not_take_…` | publish `failed` with no code, report `pending`, a notification naming `aws sso login` | `STORE_UNAVAILABLE`, report `skipped`, one notification |
| Download 5xx after retries → 3 | CLI `test_a_download_answered_503_past_the_retries_…` | exit 1 | exit 3, `PROVIDER_UNAVAILABLE`, two requests, next run fetches the one week |
| One retryable and one deterministic → 1 | CLI `test_one_retryable_and_one_deterministic_failure_exit_one` | exit 1 already; failed on `KeyError: 'error_codes'` | exit 1, both codes recorded |
| Local refusal in publish → failed, data-directory hint | smoke `test_a_local_refusal_in_publish_…` | exit 1, every source "missing from this machine", no hint | exit 3, `STORE_ACCESS_DENIED`, hint, still owed |
| S3 `AccessDenied` in report → failed, grant hint | smoke and core `test_a_missing_grant_in_report_…` | report `pending` | report `failed`, hint |
| Expired session → pending, exit 0 | core `test_an_expired_session_still_leaves_…`, smoke `test_an_expired_session_still_imports_…` | `pending` and exit 0 already; failed only on the missing `error_codes` | unchanged, `error_codes` `[]` |

Two rows are honest about what "failing first" could show. The mixed case and the expired session
already had the right exit code, so their red is the missing field. The mutants are what prove
those two guards.

The other reds, by kind:

- **The stores.** 11 of 16 adapter tests failed: `DID NOT RAISE StoreAccessDenied` for the
  listings, and a raw `PermissionError` for the rest. The 5 that passed are the ones that must hold
  both ways (a missing root still lists nothing, an unreadable `reports/` does not stop a listing of
  `manifests/`).
- **The callers.** All 10 failed: `DID NOT RAISE`, or `NothingToPublish` for an imported caselist.
- **The CLI families.** `store sync` exited 0 with an empty plan, `caselist status` reported drift,
  `caselist remove` exited 0 with a plan that found nothing here, `caselist import` exited 70.

### Mutation testing

A driver applied each mutant to a clean, committed tree, ran the tests, restored the files with
`git checkout HEAD --` and checked `git status --porcelain` and `git diff --quiet HEAD`. A mutant
whose target text is not found exactly once aborts and is not counted; none did. Each run had its
own new, empty `HYPOTHESIS_STORAGE_DIRECTORY`. The suite was 538 tests across 14 paths, about 20 s
a run. The 33 mutants ran in 9 batches, the longest 1 min 45 s.

All 33 were caught by assertion failures, none by a collection error. No catching test is
property-based, so Hypothesis generated nothing for them and there are no statistics to report.

The runs below were made at `e91101d`, after the rebase. The four later commits add tests only;
`git diff e91101d d377c52 -- 'packages/*/src' ops docs` is empty.

| Mutant | Caught | Tests failing | Examples |
|---|---|---|---|
| **A refused archive recorded as retryable**: the sync records it under the provider's code | yes | 7 | the 404, size-ceiling, 401 and integrity cases |
| **A refused archive recorded as retryable**: the CLI's list gains the archive codes | yes | 9 | the 404 and mixed CLI tests, the exit table |
| **`StoreAccessDenied` routed back to pending**, in publish | yes | 3 | local refusal and missing grant in publish |
| **`StoreAccessDenied` routed back to pending**, in report | yes | 2 | missing grant in report, core and smoke |
| **An unmapped code treated as retryable**: a deny-list instead of the allow-list | yes | 8 | "a code on no list", "an error nobody modelled", `None` |
| **An unmapped code treated as retryable**: a failed stage with no code | yes | 1 | "a failed stage that recorded no code" |
| **`list_objects` swallowing the refusal** | yes | 24 | adapters, every caller, four CLI families, the pull |
| **The publish CLI parsing the prefix again** | yes | 3 | the manifest 503 test, both field-against-sentence cases |
| The same, with the service writing the prefix back | yes | 4 | both field-against-sentence cases |
| **Mixed failures exiting 3**: `any` instead of `all` | yes | 6 | the mixed CLI test, the exit table |
| **Mixed failures exiting 3**: a stage records only its first failure | yes | 1 | "in one stage are both recorded" |
| **Mixed failures exiting 3**: only the first failed stage is read | yes | 3 | "in two stages are both recorded" |
| The daily cap on a camp download recorded as a rate limit (mine) | yes | 2 | core and CLI daily-cap tests |
| Provider failures not retryable (mine) | yes | 7 | 503, timeout, connection, 429 |
| A local refusal given the grant fix (mine) | yes | 4 | local refusal in publish, retention |
| A bucket refusal given the data-directory fix (mine) | yes | 4 | missing grant in publish and report |
| The filesystem stores raise the parent class (mine) | yes | 25 | adapters, callers, `verify` |
| The subclass reported under its own code (mine) | yes | 22 | every refused-directory CLI test |
| An unmodelled error recorded by its class name (mine) | yes | 3 | the `PermissionError` and full-disk cases |
| Report pends after a failed publish (mine) | yes | 5 | the outage and refusal tests |
| A stopped publish leaves nothing owed (mine) | yes | 4 | "the next run publishes" |
| `StoreUnavailable` escapes the publish stage (mine) | yes | 2 | core and smoke outage tests |
| Local paths left in a stage reason (mine) | yes | 1 | the torn local list |
| Schema version left at 3 (mine) | yes | 3 | the version test and two pins |
| Retention raises instead of reporting (mine) | yes | 1 | the refused release manifests |
| The listing opens directories that could hold no match (mine) | yes | 2 | the unreadable `reports/` test |
| The version store's listing not translated (mine) | yes | 4 | the removal's blob check |
| The append-only file's read not translated (mine) | yes | 1 | its adapter test |
| The append-only file's write not translated (mine) | yes | 1 | its adapter test |
| Pull ignores a stage's own fix (mine) | yes | 4 | the hint tests |
| A suppressed-row manifest has no code (mine) | yes | 1 | the publish service's suppression test |
| A withheld manifest counted beside its sources (mine) | yes | 2 | the failed-upload tests |
| A failed manifest's code not set (mine) | yes | 2 | the manifest 503 tests, core and CLI |

Seven mutants are caught by one test each. Each guards a single branch with one test written for it.

## Callers of the local stores (ac3)

Every caller of `FsEvidenceObjectStore`, `FsEvidenceVersionStore` and `LocalAppendOnlyFile`, found
by grep for `list_objects`, `list_versions`, `read_lines`, `append_lines` and the stores' names.
"Stops" means the refusal ends the command with exit 3 and `STORE_ACCESS_DENIED`. "Reported" means
a stage records it and the run goes on.

| Caller | Before: what an unreadable directory did | Now | Tested |
|---|---|---|---|
| Pull, select: `_latest_imported_snapshot`, `_newest_full_archive` (manifest listings) | Listed nothing, took every listed week for new and fetched them again, spending the day's five | **Stops** before any download | core |
| Pull, import: the importers' suppression list (`LocalAppendOnlyFile`) | Exit 70, path in the message | **Reported**: import `failed`, `STORE_ACCESS_DENIED`, hint, exit 3 | adapter; the stage path through the blob store in smoke |
| Pull, import: first-seen digests and the complete archive's baseline (`read_local_snapshots`) | Counted against nothing | **Reported**: import `failed`. Select reads the same directory first, so this needs the directory to turn unreadable mid-run | not exercised |
| Pull, publish: plan and uploads | Every source "missing from this machine", exit 1 | **Reported**: publish `failed`, hint, exit 3, snapshots owed | core, smoke |
| Pull, report and retention's confirmation (`CaselistStatusService`) | False drift | **Reported**: report `failed` with the hint; retention logs it and removes nothing | core (bucket refusal), retention existing |
| Pull, retention: `_openev_releases_by_download` | Found no release, judged camp downloads on that | **Reported**: retention `failed`, nothing removed, run otherwise intact | core |
| `caselist publish` | `PUBLISH_BLOCKED` or `NothingToPublish`, exit 1 | **Stops** | core ×2, CLI |
| `caselist status` | Drift for every snapshot, exit 1 | **Stops** | core, CLI |
| `store sync` plan | An empty plan, exit 0: nothing to push, or pull everything | **Stops** | core ×2, CLI |
| `store sync --apply`, one object | A failed object with code `PERMISSION_ERROR`, exit 1 | **Stops** the run: the sync already re-raises `StoreAccessDenied` | not exercised |
| `caselist remove`, plan (`removal_plan.py`, unchanged) | Found no manifest and no blob here, planned to remove nothing local | **Stops** | core ×2, CLI |
| `caselist remove --execute`, part-way | `RemovalIncomplete` from a `PermissionError`, exit 1, log code `PERMISSION_ERROR` | **Stops** as before, now exit 3 by `v1-e01-t20`'s rule, log code `STORE_ACCESS_DENIED` | core, CLI rule |
| `caselist import`, `import-openev`: local suppression list | Exit 70 | **Stops** | CLI |
| `v1-e31-t06`: `enumerate_sources` (parse) | "Nothing to parse" | **Stops** | core |
| `v1-e31-t06`: `ParsedStorePublisher` | Published nothing and reported success | **Stops** | core |
| The inbox and `caselist remove`'s inbox purge | Read the inbox directory and its zips directly, through none of the three stores | Unchanged | — |
| `landscape_staleness.newest_snapshot` | Takes any object store; no command wires it yet | Would stop | — |
| `read_remote_records` (`caselist runs --remote`) | The bucket only | Unchanged | — |

`removal_plan.py`'s one `except StoreAccessDenied` is around the bucket's version listing, so it
does not swallow a local refusal.

A listing only opens directories that could hold a matching key. An unreadable `reports/` does not
stop a listing of `manifests/hsld26/`.

## Exit-code and error-code consumers (ac4)

`v1-e01-t20`'s table, row by row, for everything this task changed. "Before" is the state t20 left.

| Consumer | Before | After |
|---|---|---|
| `ops/launchd/run-caselist-sync.sh` | `exec`s the command. Its comment said 3 was "the bucket did not answer before any stage could record the failure". | Still `exec`s; no logic added. The comment now lists 0, 3, 1 and 70, and says 3 is transient and next week's run retries it. The wrapper posts no notification of its own, so the comment is the only wording there was to fix. |
| launchd, through the plist | Records the last exit code. No `KeepAlive`. | Records 3 where it recorded 1 for a stage that failed on a store or provider not answering. Still no retry; t20's test of that still passes. |
| `install.sh --check-launchd` | Runs `--version` only. | Unchanged. |
| Run summary, `<data_dir>/caselist-sync-runs/<run_id>.json` | Schema 3. Not written when the run raised. | Schema 4: each stage gains `error_codes` and `hint`. Now also written for a publish whose listing did not answer. Nothing reads a summary back. |
| Run record (run log and `reports/sync-runs/`) | Schema 1. | **Schema unchanged**, so either build reads the other's records. Content changes: a publish listing 503 is `failed` with stages, where it was `failed` with `error_class` `StoreUnavailable`; a refused session is `failed` (publish) or `incomplete` (report), where it was `publish_pending`; a run stopped at select by an unreadable manifest directory is `failed` with `error_class` `LocalStoreAccessDenied`. |
| Notifications | Built from the record. A refused session sent "caselist publish waiting for an AWS login" with `aws sso login`. So did any publish that failed on its own sources, because report pended behind it. | A refusal sends "caselist pull failed" (publish) or "caselist pull finished with a failed stage" (report). A publish that failed on its sources no longer sends the login notification. The text does not say transient or verdict: it is built from the record, whose schema is out of scope. |
| `caselist runs` | Exit 0; reads the run log. | Unchanged; reads records from both builds (tested with the stored record). |
| `caselist pull --json` | `error.code` `CASELIST_PULL_INCOMPLETE`, exit 1 for any failed stage. | Same code; `exit_code` 3 or 1 by the rule; `error.hint` is the stage's fix when it has one; `stages[]` carry the two new fields; `schema_version` 4. The publish listing 503 changes `error.code` from `STORE_UNAVAILABLE` to `CASELIST_PULL_INCOMPLETE`, still exit 3. |
| `caselist publish --json` | The code at the front of `manifest_error`. | Adds `snapshots[].manifest_error_code`. `manifest_error` keeps its key and loses the `CODE: ` prefix. A manifest withheld for a suppressed row has code `MANIFEST_NAMES_SUPPRESSED_SOURCE`. An unreadable local directory is exit 3 `STORE_ACCESS_DENIED`, where it was exit 1. |
| `caselist status` | Unreadable local directory: `CASELIST_DRIFT`, exit 1. | Exit 3, `STORE_ACCESS_DENIED`. |
| `store sync` | Unreadable local directory: an empty plan, exit 0. | Exit 3, `STORE_ACCESS_DENIED`. |
| `caselist remove`, `unsuppress` | Unreadable local directory: a plan that found nothing here, exit 0; part-way, exit 1. | Exit 3 in both. The removal log's `error_code` for the part-way case is `STORE_ACCESS_DENIED`, where it was `PERMISSION_ERROR`. |
| `caselist import` | Unreadable suppression directory: exit 70. | Exit 3, `STORE_ACCESS_DENIED`. |
| `verify` | Exit 3, `details.cause` `StoreAccessDenied`. | Exit 3; `details.cause` is `LocalStoreAccessDenied`, because the cause is named by its class. |
| `scripts/validate_dev.py`, `install_channel.sh`, `.github/workflows/*` | Read no store command's exit code. | Unchanged. |
| `tests/smoke/test_caselist_pull.py` | Listing 503: exit 3, `STORE_UNAVAILABLE`. Bucket copy refused or torn: `!= 0`. Unreadable blob directory: exit 1. | Listing 503: exit 3, `CASELIST_PULL_INCOMPLETE`. Refused or unavailable: exactly 3; torn: exactly 1. Unreadable blob directory: exit 3. Two new checks for the refusals. |
| `test_verify_command.py` | Asserted cause `StoreAccessDenied`. | Asserts `LocalStoreAccessDenied`. |
| `test_caselist_sync.py`, `test_summary_names_no_camp_file.py` | Pinned schema 3 and three stage keys. | Pin 4 and five keys; t12's version test now asserts `>= 3`. |
| `test_caselist_pull.py`'s 404 test, `test_output.py`, `test_retryable_store_failures.py` | 404 → 1; the three store codes → 3. | Unchanged, plus the new cases. |
| `packages/debate_cli/README.md` | Said pull's failed stage exits 1 whatever caused it, and that a refused session is pending. | Says how the three commands decide from recorded codes, and that a refusal is not pending. |
| `docs/runbooks/caselist-scheduled-sync.md` | Exit 1 for any failed stage; `pending_publish` meant an expired session. | A new section, "What the exit code says", with a table of each failure, its code and its exit. `pending_publish` is split by whether publish is `pending` or `failed`. |
| `docs/runbooks/caselist-backfill.md`, `docs/guides/evidence-store-cli.md` | — | A row for exit 3 and the `pending_publish` row; a paragraph on this computer refusing a folder. |
| Docstrings: `exit_codes.py`, `caselist_pull.py`, `caselist.py` | Described the t20 state. | Updated. |
| `v1-e31-t06`'s `parsed_publish.py` | Imports `error_code_of` from `publish_service`. | Still works: `publish_service` re-exports it. |

**OpenCaselist failures, which is which** (the runbook carries the same table):

| Failure | Recorded code | Exit |
|---|---|---|
| Download 5xx, timeout or connection error past the retries | `PROVIDER_UNAVAILABLE` | 3 |
| Download 429 that is not the daily cap | `PROVIDER_RATE_LIMITED` | 3 |
| Daily cap on a weekly archive | none; the week is deferred | 0 (unchanged) |
| Daily cap on a camp download | `DAILY_DOWNLOAD_LIMIT_REACHED` | 1 (unchanged) |
| Download 401 or 403 from the API | `CASELIST_AUTH_EXPIRED` | 1 |
| File host 403 or 404 | `ARCHIVE_UNAVAILABLE` | 1 |
| Size ceiling | `ARCHIVE_TOO_LARGE` | 1 |
| `--full-archive` the allowance cannot cover | raised before any stage, `FULL_ARCHIVE_REFUSED` | 1 |
| Listing 5xx or timeout | escapes the run, `PROVIDER_UNAVAILABLE` | 3 (unchanged) |

The transport already raised the right errors for the first two rows, so
`debate_core.integrations.opencaselist` is unchanged.

## Files changed

- `packages/debate_core/src/debate_core/application/`
  - `errors.py`: **where the error code now lives.** `error_code_of`, `error_code_of_class`,
    `reported_error_code`, `UNMODELLED_ERROR_CODE`, and `LocalStoreAccessDenied`.
  - `caselist_sync.py`: `StageRecord.error_codes` and `hint`, `RunSummary.failure_codes`, schema 4,
    `DailyDownloadLimitReached`, and the download, import, publish, report, retention, parse and
    landscape stages recording their failures.
  - `caselist/publish_service.py`: `manifest_error_code`, `failure_codes`, and no code prefix in
    `manifest_error`. `caselist/status_service.py`: `CASELIST_DRIFT`. `evidence_sync.py`: uses the
    shared code function.
- `packages/debate_core/src/debate_core/integrations/local/`
  - `refusals.py`: raises `LocalStoreAccessDenied`; `files_under`, a walk that raises on a refusal.
  - `fs_object_store.py`, `fs_version_store.py`, `suppression_list.py`: the translation.
- `packages/debate_cli/src/debate_cli/`
  - `exit_codes.py`: `RETRYABLE_PROVIDER_FAILURES`; reads the code from `debate_core`.
  - `commands/caselist_pull.py`: the exit rule and the hint. `commands/caselist.py`:
    `manifest_error_code` in the JSON, and no parsing.
- `ops/launchd/run-caselist-sync.sh`: comment only.
- Docs: the CLI README, the scheduled-sync and backfill runbooks, the evidence-store guide.
- Tests, new: `test_pull_stage_failure_codes.py` (33), `test_refused_local_store_callers.py` (10),
  `test_refused_directories.py` (16), `test_recorded_failure_codes.py` (16), and the stored records
  under `stored_run_records/`.
- Tests, extended: the CLI's `test_caselist_pull.py`, `test_caselist_runs.py`,
  `test_retryable_store_failures.py` and `test_output.py`; the core's `test_publish_service.py` and
  `test_caselist_sync.py`; `tests/smoke/test_caselist_pull.py`.

## Deviations from the spec

1. **A refusal in the report stage alone exits 0.** ac2 says a refusal "in publish or report"
   fails the stage "with exit 1 or 3". Your rule reads the codes of the failed *required* stages
   and says "0 when no required stage failed". Report is not required: it puts no bytes anywhere,
   and `v1-e34-t02` made that the definition of a failed run. So a missing grant that stops only
   the comparison exits 0, with report `failed`, the hint, a notification, and nothing leaving the
   inbox. If you read ac2 the other way, the change is to have `RunSummary.failure_codes` read the
   report stage too. That would also make drift found by the report stage exit 1, which it does
   not today.
2. **A bucket that does not answer the publish stage is a failed stage, not an escaping
   exception.** This is the listing 503 that `v1-e01-t20` fixed as exit 3 by letting it escape. It
   escaped past the pending-work file, so the snapshots the run had just imported were owed by
   nothing: the next pull would find them already imported and publish nothing. That makes "exit 3,
   the next run retries" untrue for the case it was written for. The stage now catches
   `StoreAccessDenied` and `StoreUnavailable`, records the code and keeps what is left owed. The
   exit is still 3. `error.code` changes; the consumer table says so.
3. **`DailyDownloadLimitReached` is a new class.** You asked for no new class name and for the
   daily cap to stay 1. Both cannot hold for a camp download: the cap arrives as
   `ProviderRateLimited`, the same error and code as a burst limit, and the code is all the CLI
   sees. A weekly archive over the cap is deferred, so it never needed a code. The class is not a
   `ProviderError`, so it is a 1 by either route.
4. **`ops/launchd/run-caselist-sync.sh` is outside `constraints.packages`.** Changed on your
   instruction; the comment only.
5. **The report stage no longer pends behind a failed publish.** It pended whenever anything was
   owed, so a publish that failed on a checksum mismatch also sent the "waiting for an AWS login"
   notification. It now pends only when publish is pending, and after a failed publish it confirms
   what did publish. This is the same line that would have reported a refusal as a login, so I
   could not fix one without the other.

## Decisions and assumptions

- **The code moved to `debate_core.application.errors`.** There were three copies of "class name
  in upper snake case": the CLI's, `publish_service`'s and `evidence_sync`'s. There is now one.
  `debate_core` still imports nothing from `debate_cli`; a CLI test pins that the word
  `INTERNAL_ERROR` is the same in both.
- **`error_codes` is a list.** A stage can fail on several things, and one deterministic failure
  among them has to decide. Each distinct code is recorded once, in the order met.
- **A local refusal is told from a bucket's by type**: `LocalStoreAccessDenied`, a subclass the
  filesystem stores raise. It declares its parent's code, so `error.code` is still
  `STORE_ACCESS_DENIED` and t20's list is unchanged. The cost is that the two places that name an
  error by class now show the subclass: `verify`'s `details.cause` and the run record's
  `error_class`.
- **The sync writes the grant hint itself.** The S3 adapter is outside this task's packages and
  gives most denials no hint. So `caselist publish`, `status` and `store sync` still show a bucket
  refusal without one. See Follow-up work.
- **Outcomes that are not exceptions have codes too**, so that no failure is uncounted:
  `CASELIST_DRIFT`, the code `caselist status` already used, and `MANIFEST_NAMES_SUPPRESSED_SOURCE`.
  Both are deterministic.
- **`manifest_error` loses its prefix.** The key stays, as you asked; its value is now only the
  sentence. I dropped the prefix so that nothing can go on parsing it without a test noticing.
- **An `OSError` in the parse or landscape stage is given by its class alone**, as `v1-e34-t12`
  did for camp downloads, because its message can quote a path. A `DomainError` keeps its message.
- **Paths in stage reasons.** A failed stage's sentence has the inbox's and the data directory's
  paths replaced by those names. The one message that needed it today is a torn local suppression
  list, which names the copy it is in.
- **Select stops on an unreadable manifest directory.** It is a consequence of ac3, and the right
  one: the alternative is the old behaviour of fetching every listed week again.
- **Nothing of yours was touched.** Every test uses `tmp_path`, fakes, respx and moto. I did not
  read or write the data directory, the installed agent or its logs.

## Operator follow-ups

None. No command here needs credentials or runs longer than about two minutes; I ran the default
suite as two commands of about a minute each.

For information: the installed agent runs the build it was installed with. Until it is reinstalled
it keeps the old behaviour, exit 1 for any failed stage and a login notification for a refusal.
After a reinstall with a build containing this task, `launchctl print` may show a last exit code
of 3. That means transient, and the runbook's new section says what to check.

## Follow-up work

- **The parsed store's `PermissionError`** (E31). `LocalParsedStore` walks and reads
  `<data_dir>/parsed` itself and is not translated, as you ruled. Its publisher is, through the
  object store.
- **`caselist parse --publish` exits 1 for any incomplete publish** (E31, relevant to
  `v1-e34-t17`). Its per-object codes are this same vocabulary, so `exit_code_for_failure_codes`
  would apply as it stands.
- **The grant hint belongs in the S3 adapter** (E29), so that every command shows it, not only
  pull.
- **Manifest files read by path** (E34). `read_manifest_lines` and `write_manifest` open the file
  directly. An unreadable manifest *file*, in a readable directory, is still a raw
  `PermissionError` and exit 70.
- **The notification cannot say "transient"** (E34). It is built from the run record, which has no
  codes. Carrying them needs a record schema change that both builds can read; the record forbids
  unknown fields today.
- **A weekly archive's `OSError` still ends the run** (E34, noted by `v1-e34-t12`).
- **`UnreadableAppendOnlyRecord` carries the local copy's absolute path** (E30). Stage reasons no
  longer show it; `caselist import`'s own error still does.
- **Pre-existing, noticed:** when the session expires part-way through the publish stage, snapshots
  that had already ended incomplete earlier in the same stage are not written to the pending-work
  file (E34).

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

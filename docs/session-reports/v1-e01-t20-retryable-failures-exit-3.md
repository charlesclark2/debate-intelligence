# Session report: v1-e01-t20-retryable-failures-exit-3

| | |
|---|---|
| Task | `v1-e01-t20-retryable-failures-exit-3` — A failure that may succeed on retry never shares an exit code with a verdict |
| Spec | [`plan_specs/v1/e01-repo-foundation/t20-retryable-failures-exit-3.yaml`](../../plan_specs/v1/e01-repo-foundation/t20-retryable-failures-exit-3.yaml) |
| Epic / release | `v1-e01-repo-foundation` / `v1.0` |
| Branch | `task/v1-e01-t20-retryable-failures-exit-3` |
| Session status | PARTIAL |

## Summary

`StoreUnavailable`, `StoreCredentialsExpired` and `StoreAccessDenied` now end every command that
raises them with exit 3, never 1:

* `store`, `caselist publish | status | runs --remote | remove | unsuppress`, and `caselist pull`
  when the failure escapes the run.
* `caselist remove`, when one of the three is what stopped its preflight or its run.
* `store sync --apply` and `caselist publish`, when every per-object failure was one of the three.
  One deterministic failure (a mismatch, a missing file) keeps the run at 1.

`FsSnapshotStore` turns a `PermissionError` into `StoreAccessDenied` naming "the blob directory",
never its path. So `verify` against an unreadable blob directory exits 3, not 70, and so does
`caselist import`.

ac3's inventory is below. No consumer reads exit 1 as a verdict and an outage now arrives there.

**The phase stays `InProgress`**, because two parts of the criteria need code outside this task's
packages (Deviations 1 and 2):

* `caselist pull` folds a store failure *inside a stage* into a failed stage, which exits 1, and
  its stage records carry only a sentence.
* The three other filesystem stores have the same gap. Translating it now would turn a local
  refusal into pull's "waiting for an AWS login" (exit 1 becomes 0, with the wrong fix command).

Both are one decision for the PM about `debate_core.application.caselist_sync`.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `exit-codes`: Retryable failures exit 3 | Done, with two parts left open (Deviations 1 and 2) | Inventory first (below). Then the translation (`66c492c`), the mapping (`70dacff`), the per-family tests (`e2cd8e3`, `7f7785f`), and the docs and wrapper (`ce4901d`). Every test was shown failing on the pre-task code, then passing. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: every command maps the three to exit 3, the README says so, a test per family, `verify` unchanged | **FAIL (partial)**: met everywhere except `caselist pull`'s failures that a stage records itself | **Mapping:** `uv run pytest packages/debate_cli/tests/test_output.py`, 54 passed. The three map to 3; NotFound, AlreadyExists, RevisionMismatch, BlobIntegrityError, SnapshotIntegrityError and ArchiveTooLarge stay 1. Per-item codes are 3 only when all of them are store failures. The removal wrappers are 3 only when caused by one of the three; `RemovalCompletedUnlogged` stays 1.<br>**Per family:** `uv run pytest packages/debate_cli/tests/test_retryable_store_failures.py`, 12 passed. Covers `store sync`, `ls` and `get`; `store sync --apply` all-503 → 3, and with a mismatch → 1; `caselist import` with an unreadable blob directory → 3; `caselist publish` and `status` with an expired session → 3; publish whose manifests got a 503 → 3; `runs --remote` → 3; `remove` and `unsuppress` plans → 3.<br>**Pull:** `tests/smoke/test_caselist_pull.py::test_a_bucket_listing_that_does_not_answer_ends_the_run_with_three` → 3. The existing `test_an_expired_session_still_imports…` still asserts 0 (publish pending).<br>**Remove execute:** `tests/smoke/test_caselist_remove_smoke.py::test_a_removal_profile_missing_from_the_aws_config…` → 3.<br>**`verify`:** `commands/verify.py` is untouched; `test_verify_command.py` passes (19).<br>**README:** the exit-code table and mapping paragraph in `packages/debate_cli/README.md`.<br>**Not met:** in `caselist pull`, a store failure inside the import stage (the bucket's suppression list refused or unavailable) or inside publish's execute (`StoreUnavailable`) is a failed stage, so exit 1. Deviation 1. |
| ac2: filesystem stores turn PermissionError into StoreAccessDenied naming the role; `verify` against an unreadable blob directory exits 3, not 70; shown failing first | **FAIL (partial)**: met for `FsSnapshotStore` and `verify`; the other three filesystem stores are deliberately not changed | **Before:** `test_an_unreadable_blob_directory_exits_three_and_names_its_role` failed with `INTERNAL_ERROR`, exit 70. The message held the absolute blob path `…/data/blobs/sha256/e6/cd/e6cd…`. The two `test_fs_blob_store.py` refusal tests failed with a raw `PermissionError`.<br>**After:** `uv run pytest packages/debate_cli/tests/test_verify_command.py packages/debate_core/tests/integrations/local/test_fs_blob_store.py`, 39 passed. `verify` exits 3 with `VERIFICATION_COULD_NOT_RUN`, cause `StoreAccessDenied`, message "…the blob directory…", and no path on stdout or stderr. `get`, `exists` and `put` each raise `StoreAccessDenied("read"/"write", "the blob directory")` with the `PermissionError` on `__cause__`.<br>**Not met:** `FsEvidenceObjectStore`, `FsEvidenceVersionStore` and `LocalAppendOnlyFile` have the same gap, and are left alone. Deviation 2. |
| ac3: every consumer listed with what it now sees; nothing that treats exit 1 as a verdict reads an outage | PASS | [Exit-code consumers](#exit-code-consumers-ac3) below. Three existing tests asserted 1 for a store failure and now assert 3. Nothing else in the repository branches on 1 versus 3. |
| Node `exit-codes`: an expired session and an unreadable blob directory each exit 1 or 70 today and 3 after, with every consumer listed | **FAIL (partial)**: every family shown failing then passing; `caselist pull`'s unreadable blob directory goes 70 → 1, not 3 | [Shown failing first](#shown-failing-first-then-passing) below. `pull` is Deviation 1. |
| Forbidden: changing an exit code without listing every consumer | PASS | The inventory below. |
| Forbidden: mapping a deterministic outcome to 3 | PASS | `test_a_deterministic_answer_stays_a_domain_failure` (six classes). The `not-found-to-3` mutant is caught by 9 tests. Item failures with any non-store code stay 1. `RemovalCompletedUnlogged` stays 1. `PUBLISH_BLOCKED`, a mismatch, an UNVERIFIED card and an invalid manifest are untouched. |

### Shown failing first, then passing

The new tests ran against the pre-task source. These four files were checked out from `9448a9a`, the
task's start commit, then restored and byte-checked:

* `exit_codes.py`
* `commands/store.py`
* `commands/caselist.py`
* `fs_blob_store.py`

The run took 5.4 s: 13 failed and 1 passed. The test that passed is the guard that a mismatch keeps
a run at 1, which must pass before and after. After the change, the same 14 tests pass in 4.8 s.

| Family | Failure | Test | Before | After |
|---|---|---|---|---|
| `store sync`, `store ls`, `store get` | expired session | `TestStoreFamily::test_an_expired_session_exits_three[…]` (3) | 1 | 3 |
| `store sync --apply` | every upload answers 503 | `test_an_apply_whose_every_failure_is_the_store_not_answering_exits_three` | 1 | 3 |
| `store sync --apply` | a mismatch among the 503s | `test_a_mismatch_among_the_failures_keeps_the_run_a_one` | 1 | 1 |
| `store` | unreadable blob directory | none: read through `FsEvidenceObjectStore` (Deviation 2) | — | — |
| `caselist import` | unreadable blob directory | `TestImportFamily::test_an_unreadable_blob_directory_exits_three_naming_its_role` | 70 | 3 |
| `caselist import` | expired session | none: import never reads the bucket | — | — |
| `caselist publish` | expired session | `test_publish_with_an_expired_session_exits_three` | 1 | 3 |
| `caselist publish` | manifests answer 503 | `test_publish_whose_only_failures_are_manifests_the_store_did_not_take_exits_three` (added after the batch; caught by the `publish-manifest-code-ignored` mutant) | 1 | 3 |
| `caselist status` | expired session | `test_status_with_an_expired_session_exits_three` | 1 | 3 |
| `caselist runs --remote` | expired session | `test_reading_the_buckets_run_records_with_an_expired_session_exits_three` | 1 | 3 |
| `caselist remove`, `unsuppress` | expired session (plan) | `TestRemovalFamily::…` (2) | 1 | 3 |
| `caselist remove --execute` | session for a profile missing from the AWS config | existing smoke test, assertion changed | 1 | 3 |
| `caselist pull` | bucket listing answers 503 | `test_a_bucket_listing_that_does_not_answer_ends_the_run_with_three` | 1 | 3 |
| `caselist pull` | expired session | existing `test_an_expired_session_still_imports…`, publish pending | 0 | 0 (unchanged by ruling) |
| `caselist pull` | unreadable blob directory | `test_an_unreadable_blob_directory_fails_the_import_stage_and_names_its_role` | 70 | 1 (Deviation 1) |
| `verify` | unreadable blob directory | `test_an_unreadable_blob_directory_exits_three_and_names_its_role` | 70 | 3 |
| `verify` | store unavailable | existing `test_a_store_that_cannot_be_read_exits_three…` | 3 | 3 (unchanged) |

### Mutation testing

The runner applied each mutant, ran the tests, restored the file and checked its bytes. Each run had
its own fresh, empty `HYPOTHESIS_STORAGE_DIRECTORY` (a new `mkdtemp`). None of the tests involved
is property-based, so Hypothesis generated nothing; `--hypothesis-show-statistics` has nothing to
report here.

The suite for every run:

* `packages/debate_cli/tests`
* `test_fs_blob_store.py`
* `tests/smoke/test_caselist_pull.py`
* `tests/smoke/test_caselist_remove_smoke.py`
* `tests/integration/test_verify_cli.py`

That is 400 tests, or 401 for the last run. They ran in four batches, each under two minutes
(56 s, 40 s, 56 s, 20 s).

Every mutant was caught with the code ending in failures, never errors at collection. The
`not-found-to-3` mutant also adds the import its change needs, so that it is the mutation and not a
`NameError`.

| Mutant | Caught | Time | Tests failing | Examples |
|---|---|---|---|---|
| `StoreUnavailable` mapped back to 1 | yes | 17 s | 8 | the store-sync and publish 503 tests, pull's listing 503, the mapping tests |
| `StoreCredentialsExpired` mapped back to 1 | yes | 17 s | 16 | every expired-session family test, the store test, the remove smoke |
| `StoreAccessDenied` mapped back to 1 | yes | 21 s | 5 | `caselist import`'s unreadable blob directory, the mapping tests |
| `NotFound` mapped to 3 | yes | 18 s | 9 | `store get` of a missing object, `test_a_domain_error_exits_one…`, the deterministic list |
| `PermissionError` translation removed | yes | 22 s | 5 | `verify`, `caselist import` and `caselist pull` with an unreadable blob directory; both store tests |
| The removal-wrapper rule removed (mine) | yes | 18 s | 7 | the six wrapper cases, the remove smoke |
| Per-item failures: `any` instead of `all` (mine) | yes | 19 s | 2 | the mixed-code cases |
| `store sync`: a mismatch no longer decides (mine) | yes | 19 s | 1 | `test_a_mismatch_among_the_failures_keeps_the_run_a_one` |
| `caselist publish`: a failed manifest's code ignored (mine) | yes | 19 s | 1 | `test_publish_whose_only_failures_are_manifests…` |

Two mutants are caught by one test each: the mismatch override and the manifest code. Each guards a
single branch, and each has exactly one test written for it.

The `StoreAccessDenied` mutant does not fail `verify`'s unreadable-directory test. That is by
design: `verify` reports any `DomainError` from the verifier as "could not run" (3) itself, and its
mapping is unchanged.

## Exit-code consumers (ac3)

Everything in the repository that reads, records or documents a CLI exit code. I found it with a
grep for `exit_code`, `returncode`, `$?` and "exit", across:

* `scripts/`, `ops/` and `tests/`
* `docs/runbooks/` and `docs/guides/`
* the package READMEs and `.github/workflows/`

"Before" is what each consumer does with 1, 3 and 70 today. "After" is what it sees once this
merges.

| Consumer | Before: what it does with 1 / 3 / 70 | After |
|---|---|---|
| `ops/launchd/run-caselist-sync.sh` | Nothing. It `exec`s `debate-research --json caselist pull`, so the code is the command's, untouched. Its comment listed 0 and 1. | Unchanged code. The comment now lists 3 (the bucket did not answer before a stage recorded it) and 70, and says launchd never re-runs on any of them. New test: the installed wrapper hands launchd 0, 1, 3 and 70 unchanged. |
| launchd, through the agent's plist | Records the last exit code (`launchctl print`). There is no `KeepAlive`, `SuccessfulExit` or `StartInterval`, so no exit code makes it run again before the next weekly slot. | It can now record 3 for a pull whose store failure escaped the run. Still no retry. New test: the rendered plist has no `KeepAlive` or `StartInterval`, only the weekly calendar slot. |
| `ops/launchd/install.sh --check-launchd` | Reads the last exit code of the one-off `.check` label, which runs the wrapper's `--check`, which runs only `debate-research --version`. 0 passes; anything else fails. Never runs a command that touches a store. | Unchanged. I did not run it against the real install. |
| Run summary, `<data_dir>/caselist-sync-runs/<run_id>.json` | Stores no exit code: `succeeded` and per-stage `{stage, outcome, reason}`. It is not written when the run raises. | Unchanged. A pull that ends with 3 raised, so it writes no summary, as before when it ended with 1. |
| Run record, the run log and the bucket's `reports/sync-runs/` (v1-e34-t03) | Stores no exit code. Its outcome is completed, nothing_new, cap_deferred, publish_pending, incomplete or failed, plus `error_class` when the run raised. | Unchanged. An escaping store failure is `failed` with `error_class` `StoreUnavailable` (or similar), as before. |
| macOS notifications (`caselist.notifier`) | Built from the run record's outcome, not the exit code. | Unchanged. |
| `caselist runs` | Exits 0 whatever the records say. `--remote` with a store failure exited 1. | `--remote` with a store failure exits 3 (tested). |
| `scripts/validate_dev.py` | Reads pytest's exit code per tier and `install_channel.sh`'s; 0 versus non-zero. Runs no store command. | Unchanged. |
| `scripts/install_channel.sh` | Runs `python -m debate_cli.installation` and `debate-research doctor`; any non-zero fails the install. Neither touches a store. | Unchanged. `doctor`'s 1 and 70 keep their meanings. |
| `.github/workflows/*` | No workflow runs a CLI command and branches on its exit code (`validate-dev.yml` runs the smoke tiers through pytest). | Unchanged. |
| `tests/smoke/test_caselist_remove_smoke.py`, the missing-removal-profile test | Asserted 1. The S3 adapter reports a profile missing from the AWS config as `StoreCredentialsExpired`, which `TakedownPreflightFailed` wraps. | Asserts 3 (changed). See Decisions on whether that should stay so. |
| `packages/debate_cli/tests/commands/test_store.py`, the expired-session test | Asserted 1. | Asserts 3 (changed). |
| `packages/debate_cli/tests/test_caselist_publish.py`, the failed-upload test | Asserted 1 for a run whose only failure was a 503 on one source. | Asserts 3 (changed). |
| `tests/smoke/test_caselist_pull.py`, the bucket copy refused or torn | Asserts `!= 0` for an import stage that failed on the bucket's suppression list (1). | Still 1 (Deviation 1). The assertion still holds. |
| `tests/smoke/test_caselist_pull.py`, the expired-session test | Asserts 0 with publish `pending`. | Unchanged (the PM's partial-pull ruling, below). |
| `tests/smoke/test_cli_smoke.py`, `tests/integration/test_verify_cli.py`, `test_verify_command.py` | `verify`'s 0, 1, 2 and 3. | Unchanged. |
| `test_app.py`, `test_output.py` | `NotFound` → 1, provider → 3, a bug → 70. | Unchanged, plus the new mapping tests. |
| `packages/debate_cli/README.md` | The table said 3 was a provider failure, and the mapping was "any other `DomainError` → 1". | The table and mapping now name the three store failures and the removal wrappers, and say how `store sync`, `caselist publish` and `caselist pull` decide. `verify`'s and `doctor`'s tables are unchanged. |
| `docs/guides/evidence-store-cli.md` | "`1` a failure you have to deal with, `3` a provider failure." | 3 now includes the bucket not answering, with when a re-run helps. |
| `docs/runbooks/caselist-scheduled-sync.md` | Exit 0 is success; `doctor`'s table; 126 for privacy protection; 70 for a build without boto3. | It now says what pull's 0 with publish pending, 1, 3 and 70 mean, and that the agent never retries. `doctor`'s table is unchanged. |
| `docs/runbooks/caselist-removal.md` | "`caselist status` is clean (exit 0)". | Unchanged. |
| Command docstrings: `store.py`, `caselist.py`, `caselist_pull.py`, `caselist_remove.py` | Listed 1 for these failures. | Updated. `--help` texts carry no exit codes except `verify`'s, which is unchanged. |
| The `--json` envelope | `error.code` is `STORE_UNAVAILABLE` or similar; `error.exit_code` equals the process's exit status. | Same codes. `error.exit_code` follows the new status, which every changed test asserts. |

**The partial caselist pull** (imported, but publish waits on an expired SSO session) exits 0 today
and still does. No consumer misreads it:

* The run record says `publish_pending`.
* The notification names `aws sso login … && debate-research caselist pull --publish-pending`.
* launchd only records the 0.

This is the "keep it" case. A refused session (`StoreAccessDenied`) takes the same pending path in
pull's publish and report stages, and also stays 0.

**OpenCaselist-side failures** are out of scope. They are listed here with their current codes and
are unchanged:

| Failure | Where | Exit today |
|---|---|---|
| Listing rate-limited (429) | Select stage `SKIPPED` | 0 |
| Listing 5xx or timeout (`ProviderUnavailable`) | Escapes the run | 3 |
| Listing or download 401/403 (`CaselistAuthExpired`) | Escapes the run (policy E34 gate 5: never retried) | 1 |
| The site's daily download cap (`ProviderRateLimited`, the daily limiter) | Download `COMPLETED`, the rest deferred | 0 |
| A download 5xx, a non-daily 429, `ArchiveUnavailable` 403/404, `DownloadIntegrityError` | Download `FAILED` | 1 |

The download 5xx and non-daily 429 row is retryable and exits 1. See Follow-up work.

## Files changed

* `packages/debate_core/src/debate_core/integrations/local/`:
  * `refusals.py` (new) is the translation: a `PermissionError` becomes `StoreAccessDenied` naming
    the directory's role, with a hint that names `storage.data_dir`, never a path.
  * `fs_blob_store.py`: `get`, `exists` and `put` use it.
* `packages/debate_cli/src/debate_cli/exit_codes.py`: `RETRYABLE_STORE_FAILURES`,
  `STOPPED_BY_A_STORE` (the two removal wrappers), `exit_code_for_failure_codes`,
  `is_retryable_store_failure`, and the 3 in the module docstring.
* `packages/debate_cli/src/debate_cli/commands/`:
  * `store.py` and `caselist.py` choose 1 or 3 from their per-item failure codes.
  * `caselist_pull.py` and `caselist_remove.py` change docstrings only.
* `ops/launchd/run-caselist-sync.sh`: comment only.
* Docs: `packages/debate_cli/README.md`, `docs/guides/evidence-store-cli.md`,
  `docs/runbooks/caselist-scheduled-sync.md`.
* Tests:
  * `packages/debate_cli/tests/test_retryable_store_failures.py` (new), the per-family tests.
  * `test_output.py`: mapping, wrapper and per-item-code tests.
  * `test_verify_command.py`, `test_fs_blob_store.py`, `tests/smoke/test_caselist_pull.py`: the
    unreadable blob directory.
  * `tests/integration/test_launchd_install.py`: wrapper passthrough and no relaunch.
  * Three existing assertions changed from 1 to 3: `test_store.py`, `test_caselist_publish.py`,
    `test_caselist_remove_smoke.py`.
  * `tests/fixtures/permissions.py` (new): `refused(directory)` (`chmod 000`, restored afterwards)
    and `needs_permissions`, which skips under root, where modes are ignored.
* The spec's Goal phase was set to `InProgress` at the start, and stays so.

## Deviations from the spec

1. **`caselist pull`: a store failure that a stage records still exits 1 (ac1 and the node criterion
   are partial).**
   * What happens: the import stage, a publish execute, and an unreadable blob directory during
     import each fold the failure into `StageRecord(stage, FAILED, reason)`. A failed required stage
     exits 1.
   * Why it is not fixed here: the record carries a sentence and no error class, so the CLI cannot
     tell a store failure from a refused archive without parsing English. Recording a class is a
     change to `debate_core.application.caselist_sync`, which is not in this task's
     `constraints.packages`, so I did not make it.
   * What is fixed: what escapes the run (a refused or unavailable bucket listing, building the S3
     client) is 3.
   * Who reads pull's 1: no consumer treats it as a verdict. launchd only records it; notifications
     and the run log read the run record, not the code. So ac3 holds.
   * The PM decides whether to widen this task's packages or file the change (Follow-up work).
2. **`FsEvidenceObjectStore`, `FsEvidenceVersionStore` and `LocalAppendOnlyFile` keep the gap (ac2
   is partial).** They raise a raw `PermissionError` just as `FsSnapshotStore` did, and
   `FsEvidenceObjectStore.list_objects` is worse: `Path.rglob` silently lists nothing under an
   unreadable directory, which I measured. Translating them would be easy and wrong today:
   * `caselist pull`'s publish and report stages catch every `StoreAccessDenied` as an expired
     login: the publish is marked *pending*, the run exits 0, and the notification says
     `aws sso login`.
   * Pull's publish reads the blob and object trees through `FsEvidenceObjectStore`. A local
     permission problem there exits 1 today, as a failed source. After a translation it would exit
     0 and send the operator to log in, which fixes nothing.
   * `FsSnapshotStore` is wired only into `verify` and the import paths, never into publish, so it
     is safe and is done.
   * The others need `caselist_sync` to tell a local refusal from a remote one first (Follow-up
     work).
3. **Tests outside the listed packages.** Tests went into the following:
   * `tests/fixtures/` (a shared `chmod` helper)
   * `tests/smoke/` (pull, and one changed remove assertion)
   * `tests/integration/` (the launchd wrapper)
   * `packages/debate_core/tests/integrations/local/`

   All are test-only and sit beside the code they test.

## Decisions and assumptions

* **The three errors are named one by one**, in `RETRYABLE_STORE_FAILURES`, rather than mapping the
  `StoreError` base class, so that a future subclass is a decision, not an inheritance accident.
* **The removal wrappers.** `caselist remove` and `unsuppress` wrap what stopped them, with the cause
  only on `__cause__`. `exit_code_for` maps `TakedownPreflightFailed` and `RemovalIncomplete` to 3
  when that cause is one of the three, and to 1 otherwise.
  * `RemovalCompletedUnlogged` is deliberately not on the list. The removal finished, and its own
    message says re-running would log zero counts, so a script must not read it as "try again".
  * A generic "caused by a store failure" rule would have got that one wrong, which is why the
    wrappers are named.
  * `exit_codes.py` therefore imports `debate_core.application.caselist.removal_service`; the import
    contracts still pass (11 kept).
* **Per-item failures are all-or-nothing.** `store sync --apply` and `caselist publish` exit 3 only
  when every failure code is a store failure. A failure with no code counts as not retryable.
  * `store sync`: a mismatch anywhere makes it 1, and which failure the envelope names first is
    unchanged.
  * `caselist publish`: a withheld manifest counts through its sources' codes. A manifest that
    failed on its own counts through the code `publish_service` puts at the front of
    `manifest_error` (`"STORE_UNAVAILABLE: …"`). That string format is the one thing the CLI reads
    out of a message, and a test pins it.
* **A typo'd profile is now 3.** The S3 adapter reports a profile missing from the AWS config
  (`ProfileNotFound`) as `StoreCredentialsExpired`. So `store sync` with a typo'd profile, and a
  removal whose `DEBATE_REMOVAL_PROFILE` names one, now exit 3, though re-running cannot fix a typo.
  * I followed the spec's class-based rule rather than second-guess the adapter.
  * An *unset* `DEBATE_REMOVAL_PROFILE` is `TakedownNotConfigured` and stays 1.
  * Splitting "no such profile" from "expired" is in Follow-up work.
* **`StoreAccessDenied` from S3 is 3** even though it is usually a missing grant, because the spec
  and the PM put it on the list.
* **Only `PermissionError` is translated.** A missing blob is still `NotFound`. A full disk or an I/O
  error is left alone: it is not a refusal, and the spec does not say what it is.
* **What the refusal names.** It names a role: "the blob directory", or "the manifest directory"
  where a key's first segment says so. The hint names the setting `storage.data_dir`, never a path.
  The `PermissionError` stays on `__cause__` for a `--verbose` traceback, as the S3 adapter keeps its
  `ClientError`.
* **`exists` raises rather than answering `False`** for a refused directory: "cannot look" is not
  "not there".
* **The wrapper is unchanged.** It never treated exit codes; it `exec`s the command. Nothing was
  added that could make launchd retry. The tests use a fake home under `tmp_path`.
  `--check-launchd`, `~/.local`, `~/Library/LaunchAgents` and the real data directory were not
  touched.
* `scripts/task sync` rebased the branch onto `origin/dev`, including t19 (`763bfc6`), with no
  conflicts. The branch is not on origin, so nothing was pushed.
  `scripts/check_command_blocks.py --base origin/dev` reported no `#` comments in 186 shell blocks, this report included.
  This report's only command block has none.

**Other checks, run on the rebased branch:**

* `uv run ruff check .`: all checks passed.
* `uv run ruff format --check .`: 522 files formatted.
* `uv run pyright`: 0 errors.
* `uv run lint-imports`: 11 kept, 0 broken.
* `uv run scripts/check_thin_handlers.py`: OK, 19 handlers.

**Tests run:**

* The CLI suite, smoke, integration, local adapters, and `tests/scripts/test_check_command_blocks.py`:
  742 passed in 43 s.
* `debate_core`'s local, contract, integration, verify-manifest, caselist-sync and caselist tests,
  plus `tests/architecture` and the `install_channel`/`validate_dev` script tests: 1,238 passed in
  45 s, before the rebase.

## Operator follow-ups

The whole suite is 4,462 tests, past the two-minute line for a session.

**Operator command** (expected runtime about 3 to 5 minutes)

Where: your Mac, in the task worktree `debate-intelligence-worktrees/v1-e01-t20-retryable-failures-exit-3`

```bash
uv run pytest -q
```

Success looks like no failures. The last line reads `N passed`, with N about 4,460. Paste the last
20 lines back.

## Follow-up work

* **`caselist_sync`: make pull's stage failures and refusals classifiable** (E34, the caselist
  sync lineage, `debate_core.application`). Two changes would close Deviations 1 and 2:
  * Record the error class on a failed `StageRecord`, so pull exits 3 when a required stage failed
    only because the store did not answer.
  * Stop treating every `StoreAccessDenied` in publish and report as an expired login. A local
    refusal is not one, and a missing grant is not one either: pull reports it as pending, with an
    `aws sso login` notification.

  Then the remaining filesystem stores can be translated: `FsEvidenceObjectStore`, including a
  `list_objects` that raises instead of silently listing nothing; `FsEvidenceVersionStore`; and
  `LocalAppendOnlyFile`.
* **The S3 adapter: a profile missing from the AWS config** (E29). It is reported as
  `StoreCredentialsExpired`, so it exits 3 though re-running cannot fix it. If the PM wants it to be
  1, it needs its own error, or a `ConfigurationError`, in `integrations/s3/client.py`.
* **OpenCaselist download failures** (E34, out of scope by ruling): a 5xx or a non-daily 429 during
  download is a failed download stage, which exits 1, though it is retryable.
* **Not examined:** SQLite opening an unreadable data directory (`sqlite3.OperationalError`, not a
  `PermissionError`), and `read_archive` meeting an unreadable archive (an input, not a store).
  Neither was translated.
* **Pre-existing, noticed:** the `caselist remove` plan swallows `StoreAccessDenied` on
  `list_versions` and reports "versions not counted". That is v1-e29-t06's deliberate behaviour,
  listed here only because it is a fourth way a refusal is handled.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

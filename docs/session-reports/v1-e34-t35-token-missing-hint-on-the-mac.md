# Session report: v1-e34-t35-token-missing-hint-on-the-mac

| | |
|---|---|
| Task | `v1-e34-t35-token-missing-hint-on-the-mac` — A Mac run stopped for a missing token says to log in again |
| Spec | [`plan_specs/v1/e34-caselist-sync/t35-token-missing-hint-on-the-mac.yaml`](../../plan_specs/v1/e34-caselist-sync/t35-token-missing-hint-on-the-mac.yaml) |
| Epic / release | `v1-e34-caselist-sync` / `v1.1` |
| Branch | `task/v1-e34-t35-token-missing-hint-on-the-mac` |
| Session status | COMPLETE |

## Summary

A run on the Mac that stops because no caselist_token is stored now says so in words, "stopped: no
caselist_token was stored on this machine", and carries the hint "No caselist_token is stored on
this machine for the environment: log in again with `debate-research caselist auth login`." In
bucket mode nothing changes: the notice still reads "stopped: an error recorded as
CASELIST_TOKEN_MISSING", with no hint and the next cloud run as its fix. A test pins that text, and
it passed on the start commit. `fix_for` already took `bucket_mode`, which both of its callers pass
from what they already know, so it needed no new parameter. The words are keyed on mode too:
`_what_stopped_it` serves the cloud notice as well, so adding the code to `_WHAT_STOPPED_A_RUN`
alone would have changed the cloud's text. **Look first at** the
[check of the two neighbouring codes](#the-two-neighbouring-codes-checked-and-not-fixed).
`CASELIST_TOKEN_UNREADABLE` has the same gap on the Mac. `CASELIST_AUTH_EXPIRED` has none on the
Mac, but its cloud notice names the Mac's `caselist auth login`. I reported both and changed neither.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `token-missing-hint-on-the-mac` (Token missing hint) | Done | Failing tests first (`fa22b5e`), then the hint, the words and the runbook line (`42b05c3`) |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: outside bucket mode a run stopped for a missing token names `caselist auth login` and has its own words; in bucket mode the notice is unchanged; by tests shown failing first | PASS | Red, at `fa22b5e` (tests only): `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests/application/caselist/test_pull_token_missing_hint_on_the_mac.py -p no:randomly -n 0 -q --tb=line -rfp` → `1 failed, 3 passed`. The Mac run failed on `assert None == 'No caselist_token is stored on this machine …'`, so the start commit gave it no hint. The bucket-mode test passed there, which shows the old text I wrote by hand is the start commit's, word for word. The two other-code cases also passed, as guards. Green after `42b05c3`: `4 passed in 1.57s` |
| Node: Token missing hint tests pass (`uv run pytest packages/debate_core/tests -k token_missing`) | PASS | `.venv/bin/python scripts/hard_stop.py 115 uv run pytest packages/debate_core/tests -k token_missing -q` → `4 passed in 30.09s` |

What the tests assert. Each is `caselist pull` run the way the command runs it: `run_pull` inside a
real `SyncRunMonitor`, against moto. The token is read when the first request needs it, as the
client's token source reads it, from `keyring`'s macOS backend reading an item that is not there
(`None`). Bucket mode comes from the details' `bucket_run`, which `v1-e40-t18`'s stand-in bracket
writes. Every expected sentence is written out by hand.

* **On the Mac** (`test_a_mac_run_stopped_by_token_missing_says_to_log_in_again`):
  * the record: `error_class` and `failed`;
  * the details: `failure_codes` and `hint`;
  * the notification: title, message, hint and fix command, with no code in its text and no path;
  * the banner as `osascript` is asked to show it: its title, and its body naming
    `` `debate-research caselist auth login` `` and the new words.
* **In bucket mode** (`test_a_bucket_mode_run_stopped_by_token_missing_is_unchanged`):
  * the record, as above;
  * the details: no hint, and a `bucket_run`;
  * the notification: the old title, the old message, no hint, the cloud cure as its fix, and
    neither `caselist auth login` nor the new words anywhere in its text.
* **No other code gets the hint or the words**
  (`test_token_missing_hint_and_words_are_given_to_no_other_code_on_the_mac`, for
  `CASELIST_TOKEN_UNREADABLE` and `CASELIST_AUTH_EXPIRED` on the Mac): the details carry no hint,
  the notification has no hint and not the new words, and the unreadable run's message stays as it
  was.

**Mutants** (agreement 8). Each mutant was applied to `42b05c3`, the new test file was run with a
fresh `HYPOTHESIS_STORAGE_DIRECTORY` (there is no Hypothesis in it), and the source file was
restored with `git checkout HEAD --`. All seven were caught at an assertion; none was caught by a
crash or a collection error:

| Mutant | Result |
|---|---|
| 1. The hint given in bucket mode too (`and not bucket_mode` removed) | caught, 1 failed: the bucket-mode details carry the hint |
| 1b. The words given in bucket mode too (the mode-only set emptied) | caught, 1 failed: the bucket-mode message |
| 2. The hint dropped on the Mac (`return None`) | caught, 1 failed: the Mac details' hint |
| 3. The words dropped (the `_WHAT_STOPPED_A_RUN` entry removed) | caught, 1 failed: the Mac message |
| 4. Another code given this hint (`CaselistTokenUnreadable` matched too) | caught, 1 failed: `[token-unreadable]` |
| 4b. Another code given this hint (`CaselistAuthExpired` matched too) | caught, 1 failed: `[auth-expired]` |
| 4c. Another code given these words (`CASELIST_TOKEN_UNREADABLE` in the dict with them) | caught, 1 failed: `[token-unreadable]` |

### The two neighbouring codes, checked and not fixed

I called `fix_for` and `notifications_for` for each code in both modes, at `42b05c3`:

| Code | On the Mac | In bucket mode | Gap |
|---|---|---|---|
| `CASELIST_TOKEN_UNREADABLE` | "stopped: an error recorded as CASELIST_TOKEN_UNREADABLE", no hint, fix `debate-research caselist pull` | the same message and no hint, with the cloud cure as its fix | **The same Mac-only gap as MISSING.** The Mac's fix is the error's own message: `caselist auth logout`, then `caselist auth login`. `StoredCaselistToken.from_json` raises it for every backend, Secrets Manager included (`token_store.py` line 221), and `caselist-cloud-run.md` (line 1383) puts it beside MISSING, with the Wednesday login as the cloud's fix. So the same branch on bucket mode would fit it |
| `CASELIST_AUTH_EXPIRED` | its own notification: "caselist pull stopped: OpenCaselist login expired", fix `debate-research caselist auth login` | **the same notification, naming `debate-research caselist auth login`** | None on the Mac. The cloud notice names a login on this machine, which `caselist-cloud-run.md` says not to make ("Nobody logs in by hand for an import"; the Wednesday 03:00 login renews it). The branch at `sync_runs.py` (`record.error_class == CaselistAuthExpired.__name__`) does not look at `bucket` |

The spec covers MISSING only, so I changed neither. See Follow-up work.

## Files changed

* `packages/debate_core/src/debate_core/application/caselist_sync.py`: `fix_for` returns
  `_TOKEN_MISSING_ON_THIS_MACHINE_FIX` for `CaselistTokenMissing` when not `bucket_mode`. Its
  docstring says why bucket mode keeps nothing.
* `packages/debate_core/src/debate_core/application/sync_runs.py`: words for `CASELIST_TOKEN_MISSING`
  in `_WHAT_STOPPED_A_RUN`, and `_WORDS_OUTSIDE_BUCKET_MODE_ONLY`, which `_what_stopped_it` now
  reads with a required `bucket_mode`. The stopped-run notification passes `bucket is not None`, the
  same test it already uses for its fix command.
* `packages/debate_core/tests/application/caselist/test_pull_token_missing_hint_on_the_mac.py`: the
  four tests above.
* `docs/runbooks/caselist-scheduled-sync.md`, "When something goes wrong", t33's keychain table: a
  `CASELIST_TOKEN_MISSING` line with its fix on the Mac. The sentence under the table now says the
  line is the Mac's and that a cloud run's notice is as before.
* The spec's `status.phase`, set to `Succeeded`.

## Deviations from the spec

None.

## Decisions and assumptions

* **How `fix_for` learns the mode.** It needed nothing new. It has taken `bucket_mode` since
  `v1-e40-t22`. The run monitor passes `bucket is not None` (from `BucketRun.details()`, which is
  `None` exactly when not in bucket mode), and a stage passes the service's own `_bucket_mode`. The
  cloud path is untouched: in bucket mode, `fix_for` reaches the new branch, fails its
  `not bucket_mode` test and returns `None`, as before.
* **The words are mode-only too.** `_what_stopped_it` builds the stopped-run message in both modes.
  An entry in `_WHAT_STOPPED_A_RUN` alone would have changed the cloud's notice from "an error
  recorded as CASELIST_TOKEN_MISSING", which is forbidden. So the entry sits in the dict, as the PM
  asked, and a set of codes whose words are said outside bucket mode only makes a bucket-mode run
  name them by code. Mutant 1b shows the test sees the difference.
* **The fix command stays `debate-research caselist pull`.** The login is in the hint. A Mac
  stopped-run notification is built the same way for t33's keychain codes (pull as the command,
  the fix as the hint), and the spec asks for the hint and the words, not a new fix command. After
  the login, the pull is what finishes the run. The title stays "needs a person", since the code
  is not one a retry may cure, so `caselist runs`' `banner_words` is unchanged too (`None`).
* **The hint's wording** follows t33's "log in again with `debate-research caselist auth login`",
  after a clause saying what is missing, as t33's hints do. I wrote "on this machine" rather than
  "on this Mac", because local mode is any machine that is not in bucket mode.
* **No smoke check.** A smoke check runs an installed build, which would need a real keychain with
  no item, or a run against OpenCaselist. The test runs the command's own `run_pull` inside a real
  monitor instead. No CLI surface changed: the CLI's envelope for this code already names the login.

### Checks run before this report

* **Affected set**: `uv run scripts/affected_tests.py` selected 298 of 629 test files from 6 changed
  files, because `caselist_sync.py` and `sync_runs.py` are hub modules (t33 measured 303).
  `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python scripts/affected_tests.py --run` was
  stopped at its 115-second limit about 11% of the way through (exit 124), with no failure in what
  had run. The machine's load average was 12 to 41 during these runs. Under agreement 10 the rest is
  left to the pull request's `ci`, with no hand-off. Within the limit I ran:
  * the always-run list (`tests/architecture/`, `tests/specs/`, `test_app.py`,
    `test_help_rendering.py`, `test_container_factories.py`): `374 passed in 41.77s`;
  * every test file that names `sync_runs`, `fix_for`, `notifications_for` or a stopped run's
    message (43 files, from `` git grep -l -E "sync_runs|fix_for|notifications_for|stopped: " ``),
    `tests/smoke/test_caselist_pull_in_process.py` among them: `802 passed in 89.18s`.
* `ruff format --check .` → `1739 files already formatted`; `ruff check .` → `All checks passed!`
* `pyright packages/debate_core` → `0 errors, 0 warnings, 0 informations`
* `lint-imports` → `Contracts: 20 kept, 0 broken.`; `scripts/check_thin_handlers.py` → OK
* `scripts/check_command_blocks.py --base origin/dev` → OK; `scripts/docs_index.py
  --check-descriptions` → OK; `scripts/check_links.py` → `OK: 3242 relative links and anchors`
* `uv run scripts/validate_specs.py` → `OK: 554 files, 41 epics, 491 tasks, 22 releases`
* The spec on `origin/dev` differs from this branch's only in `status.phase`. The one merge into dev
  since the branch started (#728, `v1-e39-t28`) adds a test file in the same test directory and
  touches none of this task's files. I compared against the local `origin/dev` ref and did not fetch.

## Operator follow-ups

None. The full affected set is left to the pull request's `ci` under agreement 10, with no hand-off.

## Follow-up work

* **`CASELIST_TOKEN_UNREADABLE` has the same Mac-only gap** (see the check above). On the Mac its
  fix is `caselist auth logout` and then `caselist auth login`. In the cloud it is the Wednesday
  login, as `caselist-cloud-run.md` says. The change would follow this task's pattern: a
  `fix_for` branch when not `bucket_mode`, and an entry in `_WHAT_STOPPED_A_RUN` added to
  `_WORDS_OUTSIDE_BUCKET_MODE_ONLY`. A small E34 task, for the PM to file.
* **`CASELIST_AUTH_EXPIRED`'s cloud notice names the Mac's login.** A bucket-mode run refused with
  401/403 is announced "OpenCaselist login expired" with fix `debate-research caselist auth login`,
  which the cloud runbook tells the operator not to run for a cloud run. It is a cloud-side wording
  question, the reverse of this task's, and it touches the cloud's notice. That is forbidden here,
  so it is for the PM to rule on (E40, beside `v1-e40-t28`'s cures).

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-31

**Notes:**

This is small and exact, and the check of the two neighbouring codes is worth more than its size.
1. **ac1 passes.**
   * Red: 1 failed at the Mac hint's assertion.
   * The bucket-mode test passed on the start commit, which proves the hand-written old text is the
     cloud's, word for word. That is the right way to pin "unchanged".
   * Green: 4, and the node criterion passes (4).
   * All seven mutants are caught: the PM's four plus 1b and the 4b/4c variants. 1b shows the words
     needed their own mode guard.
2. **Decisions accepted:**
   * `fix_for`'s existing `bucket_mode`, with no new parameter;
   * the words in `_WHAT_STOPPED_A_RUN` behind a mode-only set, since `_what_stopped_it` also builds
     the cloud's message;
   * the fix command staying `caselist pull`, with the login in the hint, as t33's keychain codes do;
   * "on this machine" rather than "on this Mac";
   * no smoke check, since a real monitor around `run_pull` covers the surface.
3. **The neighbouring codes, the PM's rulings:**
   * **`CASELIST_TOKEN_UNREADABLE` (the same Mac-only gap):** one p3 E34 task in the next batch,
     following this task's pattern (logout, then login, outside bucket mode only).
   * **`CASELIST_AUTH_EXPIRED`'s cloud notice naming the Mac's login:** one p2 E40 task in the next
     batch. It tells the operator to do the one thing the cloud runbook forbids (a second login), so
     it outranks the cosmetic gaps. In bucket mode the cure is the Wednesday login, as
     `caselist-cloud-run.md` says.
4. **Closing checks:** the affected set (298 files through two hub modules) stopped at 11% at its
   limit with nothing failing, and is left to the PR's `ci` under agreement 10. The always-run list
   (374), every file naming the run-notice code (802), ruff, pyright, lint-imports, thin handlers,
   the doc checks and the specs are clean.
5. **Merge:** a plain `scripts/task pr` once `ci` is green. No operator step follows. This is v1.1
   work.

# Session report: v1-e40-t33-expired-login-cloud-notice-names-the-wednesday-login

| | |
|---|---|
| Task | `v1-e40-t33-expired-login-cloud-notice-names-the-wednesday-login` — A cloud run refused for an expired login says the Wednesday login renews it, not to log in by hand |
| Spec | [`plan_specs/v1/e40-cloud-caselist-run/t33-expired-login-cloud-notice-names-the-wednesday-login.yaml`](../../plan_specs/v1/e40-cloud-caselist-run/t33-expired-login-cloud-notice-names-the-wednesday-login.yaml) |
| Epic / release | `v1-e40-cloud-caselist-run` / `v1.8` |
| Branch | `task/v1-e40-t33-expired-login-cloud-notice-names-the-wednesday-login` |
| Session status | COMPLETE |

## Summary

In bucket mode, a run that OpenCaselist refused with 401 or 403 (`CASELIST_AUTH_EXPIRED`) no longer
gives `debate-research caselist auth login` as its fix. It gives the cloud's cure,
`CLOUD_AUTH_EXPIRED_CURE` in `sync_runs.py`. The cure says the next Wednesday 03:00 login renews the
token and the run after it takes up the rest, and that a backfile import refused for it starts again
after Thursday 00:00. It also says never to log in by hand, because that would be a second login. On
the Mac every word is unchanged, and a test pins that by the old text. The SNS email is built from the
notification, so it changed with it. A test pins the whole email body through the real `SnsNotifier`.
`caselist-cloud-run.md` has a new section that the cure names, and `caselist-run-alerts.md` has a row
for the email. The PM should look first at two places. One is the cure's wording and the structure it
follows (under "Decisions"). The other is the two notices this task found still naming the login in
the cloud but left alone because they are outside its packages: the run's own log and
`caselist runs --json`'s `error_message` (under "Follow-up work").

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `expired-login-cloud-notice-names-the-wed` (Expired login in the cloud) | Done | Tests committed red first (`c1ebdbb`), then the code and runbooks (`3120ab5`) |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: in bucket mode a run refused for an expired login names the Wednesday login and not `caselist auth login`; on the Mac the notice is unchanged, asserted by its old text; by tests shown failing first | PASS | **Red**, at `c1ebdbb` before the code: `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests/application/caselist/test_pull_auth_expired_notice_names_the_wednesday_login.py -q -p no:randomly -n 0 --tb=no -rA` → `4 failed, 4 passed in 1.88s`. The bucket-mode notification and email tests failed because the fix was still `debate-research caselist auth login`. The two runbook tests failed because the section and the row did not exist yet. The Mac pin and the three neighbour-code cases passed, as they should before the change. **Green**, at `3120ab5`: the same file → `8 passed in 0.71s`. |
| Node: "Expired login in the cloud tests pass" (`uv run pytest packages/debate_core/tests -k auth_expired`) | PASS | Run as `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests -k auth_expired -q` (the same pytest, bounded, without uv's sync) → `10 passed in 47.87s` |

### The surfaces the cloud run speaks through

| Surface | Changed? | Why |
|---|---|---|
| The notification (`notifications_for`, the `CaselistAuthExpired` arm) | **Changed** in bucket mode | `fix_command=CLOUD_AUTH_EXPIRED_CURE if bucket is not None else AUTH_LOGIN_COMMAND`. Bucket mode is read from the details' `bucket_run`, as in t22, t25, t28 and t35. The title and message are unchanged in both modes. |
| The email the alert topic sends (`caselist.notifier = sns`) | **Changed**, with the notification | `alert_message` lays out the notification and puts `Fix: <fix_command>` on its own line. Nothing in the adapter is code-specific, so the adapter itself did not change. `test_the_alert_email_of_a_bucket_mode_run_refused_for_auth_expired_names_the_wednesday_login` pins the whole body, and the Mac test pins the Mac's body and subject word for word. |
| The run-stopped email from the task-state rule (`debate-dev-caselist-run-stopped`) | Already right | `infrastructure/modules/caselist_run/alerts.tf:180` names the exit code, the task, the log and `caselist runs --remote`. It names no fix. |
| `caselist runs`' banner words | Already right | `banner_words` returns `None` for `CaselistAuthExpired` in both modes, and the title did not change. The new tests assert `None` from the record and details each run wrote. The table shows `failed (CaselistAuthExpired)`. **But** `caselist runs --json` dumps the record whole, and its `error_message` is the exception's own sentence, which says `Run debate-research caselist auth login again` in both modes. See "Follow-up work". |
| The login task's own failure notice (`Weekly caselist login failed`, `login_failure_notification`) | Already right, not changed | A refused login gives `caselist auth set-password`, with a hand login (`--token-backend secretsmanager`) as the hint. Any other failure gives the hand login, with set-password as the hint. Both are what `caselist-run-alerts.md` and `caselist-cloud-credentials.md` say. A hand login after a failed weekly login replaces the login that failed, so it is not a second login, and the new runbook section says so. |

## Files changed

* `packages/debate_core/src/debate_core/application/sync_runs.py`: `CLOUD_AUTH_EXPIRED_RUNBOOK` and
  `CLOUD_AUTH_EXPIRED_CURE` beside t22's `CLOUD_NO_SESSION_CURE`, the mode branch in the
  `CaselistAuthExpired` arm, and a paragraph in `notifications_for`'s docstring.
* `packages/debate_core/tests/application/caselist/test_pull_auth_expired_notice_names_the_wednesday_login.py`:
  new. It uses a real `SyncRunMonitor`, moto, and t18's `BucketModeBracket`, as t35's
  `test_pull_token_missing_hint_on_the_mac.py` does. The monitor's notifier is the Mac's recording
  notifier together with the real `SnsNotifier`, whose client records the publish in-process. The
  file has 8 tests: the Mac pinned word for word, notification and email; bucket mode, notification
  and email; three neighbouring codes in bucket mode (`CASELIST_TOKEN_MISSING`,
  `CASELIST_TOKEN_UNREADABLE`, `STORE_UNAVAILABLE`) that name no Wednesday login; and the two
  runbooks.
* `docs/runbooks/caselist-cloud-run.md`: a new section, "A run refused for an expired login", placed
  after "A failed or stopped run". It quotes the fix line and says what the notice means. It names
  the two cases that go to the PM: the weekly login failed as well, or a Wednesday run was refused
  hours after a login that succeeded (policy clause 10). It ends with "Never run `debate-research
  caselist auth login` on the operator's Mac", in the style of the sections t22, t25 and t28 wrote.
* `docs/runbooks/caselist-run-alerts.md`: a row for `caselist pull stopped: OpenCaselist login
  expired` in "When an alert arrives".
* The spec: `status.phase` set to `Succeeded`.

## Deviations from the spec

None.

## Decisions and assumptions

* **Which cure's structure I followed: t22's (`CLOUD_NO_SESSION_CURE`), not t28's `next_cloud_run`.**
  t22's shape is "what puts it right (runbook section); never X". `next_cloud_run` says "the next cloud
  run …: the weekly run, or one started by hand (…); never a publish from the operator's Mac". That
  does not fit this code for two reasons. A run started by hand before the Wednesday login is refused
  again. And the thing to warn against is a login by hand, not a publish. The cure does reuse t28's
  words for what the next run does ("takes up what this run did not finish, from the run state saved
  in the bucket"), so a cloud run's failures still say the same thing about the bucket's run state.
* **The title and message are unchanged in bucket mode.** "was refused by OpenCaselist and fetched
  nothing more" is true in the cloud as well. Keeping the title keeps `banner_words` and the email
  subject as they were. Only the fix differs, as with t28's stopped run.
* **The backfile import's clause is in the cure** because the spec and the PM asked for it. A backfile
  import does not go through the run monitor (`caselist_backfile.py` builds none), so it sends no
  notification of its own. Its refusal shows only in its log's `"code"` line and in the task-state
  email. The clause sends whoever reads the pull's email to the same rule that the import refusal
  list in `caselist-cloud-run.md` already gives.
* **Policy clause 10** (`docs/policies/caselist-data-use.md`) says a 401/403 "stops the run and is
  escalated to Charlie, never worked around". I treated the alert email as that escalation and the
  Wednesday login as the schedule working, not as a workaround. The runbook sends to the PM the one
  case clause 10 most clearly covers: a Wednesday run refused hours after a login that succeeded.
  If the PM reads the clause as requiring more than the email, the policy is the PM's to change.
* **The mode branch is one conditional expression**, the same idiom as the arm beside it
  (`CLOUD_UNFINISHED_RUN_CURE if bucket is not None else PULL_COMMAND`). t36 (the unreadable-token
  hint) can extend it the same way. One thing for t36: the new neighbour test pins
  `CASELIST_TOKEN_UNREADABLE` in bucket mode to t28's unfinished-run cure and to "no Wednesday". If
  t36 gives that code the Wednesday login, it changes that case deliberately.

### Mutants (agreement 8; the tests use no Hypothesis, so there is no example database to isolate)

Each mutant was applied to the committed code (`3120ab5`), run against the new test file with
`hard_stop.py 115 … pytest <file> -n 0 -p no:randomly`, and restored with `git checkout HEAD --`.
`git status` was clean afterwards. Every catch was an assertion failure, not a crash. The mutation script was a scratch file outside the repository,
and its output is quoted here.

| Mutant | Result | Caught by |
|---|---|---|
| 1. The Mac's notice changed: the cloud cure in both modes | 1 failed, 7 passed | `test_a_mac_run_refused_for_auth_expired_keeps_its_notice_word_for_word` |
| 1b. The Mac's fix changed to `… auth login --token-backend secretsmanager` | 1 failed, 7 passed | the same |
| 2. Bucket mode still naming `caselist auth login` (the arm as it was before this task) | 2 failed, 6 passed | the bucket-mode notification and email tests |
| 2b. The bucket-mode cure with `(debate-research caselist auth login)` appended | 2 failed, 6 passed | the same |
| 3. The cloud cure given to every stopped run in bucket mode | 3 failed, 5 passed | all three neighbour-code cases |
| 3b. The cloud cure given to `CASELIST_TOKEN_MISSING` alone | 1 failed, 7 passed | the `token-missing` case |
| 4. The SNS email left with the old fix (`alert_message` writes the Mac's fix for this message) | 1 failed, 7 passed | `test_the_alert_email_of_a_bucket_mode_run_refused_for_auth_expired_names_the_wednesday_login` |

### Tests and checks run before this report

`uv run scripts/affected_tests.py` chose **301 of 634 test files** from 6 changed files (17.4 s).
`sync_runs.py` is a hub module, so that set is well over two minutes. Per agreement 10 I did not run
it and leave it to the pull request's `ci`. Within the limit I ran the changed areas and the always-run
list, each run bounded at 115 s with `-m "not slow and not live"` and `-n auto`:

| Run | Result |
|---|---|
| `packages/debate_core/tests/application/caselist`, `packages/debate_core/tests/integrations/sns`, `packages/debate_core/tests/application/test_caselist_sync.py` | `1889 passed in 87.12s` |
| The always-run list: `tests/architecture`, `tests/specs`, `packages/debate_cli/tests/test_app.py`, `test_help_rendering.py`, `test_container_factories.py` | `374 passed in 19.20s` |
| `packages/debate_cli/tests/bucket_mode` (the CLI's bucket-mode cures, read from `sync_runs`) | `230 passed in 105.41s` |
| `packages/debate_cli/tests/commands/test_caselist_runs.py`, `test_recorded_failure_codes.py`, `test_output.py` | `120 passed in 6.16s` |
| `packages/debate_cli/tests/commands/test_caselist_pull.py` | `68 passed in 10.40s` |
| `tests/docs/test_backfile_import_log_reads.py`, `test_backfile_import_plan_check.py`, `tests/scripts/test_caselist_run_image_plan_check.py`, `test_check_command_blocks.py`, `test_docs_index.py` (the tests that read the two runbooks) | `219 passed in 6.13s` |

Two earlier combined runs of the last four rows hit the 115-second limit (exit 124) under a load of
10 to 15. Neither had a failure before it was stopped. I split them into the four runs above, which
all passed.

The whole-repo checks: `ruff format --check .` → `1750 files already formatted`; `ruff check .` →
`All checks passed!`; `pyright packages/debate_core` → `0 errors, 0 warnings, 0 informations`;
`lint-imports` → `Contracts: 20 kept, 0 broken.`; `scripts/check_thin_handlers.py` → `OK: 70 … within
25 statements`; `scripts/docs_index.py --check-descriptions` → `All 61 indexed documents under docs/
have a description`; `scripts/check_links.py` → `OK: 3282 relative links and anchors in 515 Markdown
files`; `scripts/check_command_blocks.py` → `OK: no # comments in 641 shell code blocks`;
`uv run scripts/validate_specs.py` → `OK: 558 files, 41 epics, 495 tasks, 22 releases`.

## Operator follow-ups

None.

## Follow-up work

* **A cloud run's own log and its record still name `caselist auth login`** (E40). The
  `CaselistAuthExpired` message (`ports/caselist_source.py`) says "Run `debate-research caselist auth
  login` again" in both modes. The CLI prints it as the command's error, so it appears in the cloud
  run's log. The monitor keeps it as the record's `error_message`, so it appears in `caselist runs
  --json`. The error is raised by the transport, which does not know the mode. Changing the message
  would change the Mac's output too, which this spec forbids for the notice, and the CLI is outside
  this task's packages. The import refusal list in `caselist-cloud-run.md` already says "a later
  image changes it", and this task does not do that. The new section says the rule holds for the
  log as well. A follow-up could give the CLI's bucket-mode output for this code the cure, as
  `caselist_pull._hint_for` does for the other bucket-mode next steps.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

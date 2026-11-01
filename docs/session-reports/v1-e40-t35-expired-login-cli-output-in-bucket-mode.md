# Session report: v1-e40-t35-expired-login-cli-output-in-bucket-mode

| | |
|---|---|
| Task | `v1-e40-t35-expired-login-cli-output-in-bucket-mode` — A cloud run refused for an expired login names the Wednesday login in its own output too |
| Spec | [`plan_specs/v1/e40-cloud-caselist-run/t35-expired-login-cli-output-in-bucket-mode.yaml`](../../plan_specs/v1/e40-cloud-caselist-run/t35-expired-login-cli-output-in-bucket-mode.yaml) |
| Epic / release | `v1-e40-cloud-caselist-run` / `v1.8` |
| Branch | `task/v1-e40-t35-expired-login-cli-output-in-bucket-mode` |
| Session status | COMPLETE |

## Summary

In bucket mode, `caselist pull` and `caselist backfile-import` no longer print "Run `debate-research
caselist auth login` again" when OpenCaselist refuses them with 401 or 403 (`CASELIST_AUTH_EXPIRED`).
The output keeps the error's code, details and exit status. Its message is now only what was refused,
for example `OpenCaselist refused list archives for hsld26 with HTTP 401; the caselist_token has
expired or been revoked.`. Its hint is t33's cure in `_hint_for`'s idiom: `In bucket mode the next
Wednesday 03:00 login renews the caselist_token, … never a login by hand, which would be a second
login.` The run record's `error_message` keeps the same refusal sentence and is still a string, so
`caselist runs --json` no longer names the login either. The task also covers a camp download that a
401 fails partway through a run, since that path also printed the hand-login sentence (in the stage's
reason). On the Mac every word is unchanged, pinned by the old text, through the real command. The PM
should look first at "Decisions": the message is replaced rather than given an added hint, and the
clause-10 sentence is dropped in bucket mode.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `expired-login-cli-output-in-bucket-mode` (Expired login output) | Done | Red tests `baa94a2`, implementation `7f172bd`, runbook `9d48259`. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: in bucket mode the command's output for an expired login names the Wednesday login and not `caselist auth login`; on the Mac it is unchanged, asserted by its old text; by tests shown failing first | PASS | Red at `baa94a2` against the start code: `hard_stop.py 115 … pytest packages/debate_cli/tests/bucket_mode/test_bucket_mode_auth_expired_names_the_wednesday_login.py -n 4 -p no:randomly` → `7 failed, 7 passed`. Every bucket-mode test failed on an assertion: the message still carried "… (policy clause 10).", the panel or JSON still held `auth login`, or the hint was t28's unfinished-run cure. All seven Mac pins and neighbour cases passed. Green after `7f172bd`: `14 passed in 16.33s`. With the runbook pin added: 15 tests. |
| Node: "Expired login output tests pass" (`uv run pytest packages/debate_cli/tests -k auth_expired`) | PASS | `hard_stop.py 115 .venv/bin/python -m pytest packages/debate_cli/tests -k auth_expired -q` → `17 passed in 12.79s` (this task's 15 and two existing tests the keyword matches). |

## Files changed

* **`debate_core.application`**:
  * `ports/caselist_source.py`: `CaselistAuthExpired.refusal` is a property holding the message's
    first sentence. The message is built from it and is byte-identical. A property is not an instance
    attribute, so the CLI's `details` (built from `vars()`) are unchanged.
  * `caselist_sync.py`: new `message_for(error, bucket_mode=)`. It is `reported_error_message`, except
    that an expired login in bucket mode returns `refusal`. A stage's failure (`_failure`) and a camp
    download's reason (`_camp_download_refused`) use it.
  * `sync_runs.py`: `record_for_failure(..., bucket_mode=)` uses `message_for` for `error_message`.
    `watch` now asks `bucket_run()` before it builds the record, not after; it is still asked once,
    after the run has raised. Module docstring: one bullet under "What a record may hold".
  * `caselist/backfile_import.py`: a public `bucket_mode` property, so the CLI asks the service the
    same question the service answers.
* **`debate_cli`**:
  * new `caselist_auth_expired.py`: `CLOUD_AUTH_EXPIRED_HINT` (`f"In bucket mode {CLOUD_AUTH_EXPIRED_CURE}."`)
    and the context manager `cloud_cure_for_an_expired_login`. In bucket mode it catches only
    `CaselistAuthExpired` and reports `CommandFailure.from_exception(...)` with the message and hint
    replaced. Anything else, in either mode, goes on to the root handler.
  * `commands/caselist_pull.py`: the run is inside the context manager. `_hint_for` returns the cure in
    bucket mode when a failed stage records `CASELIST_AUTH_EXPIRED`.
  * `commands/caselist_backfile.py`: the dry run and `--execute` are each inside the context manager.
* **`packages/debate_cli/tests/bucket_mode/test_bucket_mode_auth_expired_names_the_wednesday_login.py`**:
  15 tests through the real application (Typer `CliRunner`, moto, and the respx stand-in site of
  `conftest.py` answering 401). Every expected sentence is written by hand.
* **`docs/runbooks/caselist-cloud-run.md`**: in the import refusal list, "a later image changes it"
  now says the change is in `v1-e40-t35`, and that the other two codes' messages still name the login.
  "A run refused for an expired login" says what the log and `error_message` show since this task.

## Deviations from the spec

None. Everything is inside the spec's packages: `debate_cli`, `debate_core.application`, their tests,
and `docs/runbooks`. The transport (`debate_core.integrations.opencaselist`) is not in the spec's
packages and is unchanged.

## Decisions and assumptions

* **Replaced, not added to.** The PM preferred this, and a log that said "log in again" beside a hint
  that said "don't" would be worse than either alone. In bucket mode the message is
  `CaselistAuthExpired.refusal` and the hint is the cure. The code (`CASELIST_AUTH_EXPIRED`), the
  details (`status_code`, `operation`) and the exit status (1) are as before.
* **The clause-10 sentence goes too in bucket mode.** "If it happens straight after a login, stop and
  tell the operator: access may have been suspended (policy clause 10)" is part of the Mac's
  instruction. In the cloud it is carried by the runbook section the cure names, which sends a
  Wednesday run refused hours after a login to the PM. I did not write a second wording of it (the PM:
  "don't write a second wording"). If the PM wants the escalation in the log as well, it belongs in
  the cure, so the notice gets it too.
* **`error_message`, today and now.** Before this task it was `redact(str(error))` in both modes,
  which is the whole sentence with the hand login. On the Mac it still is, word for word. In bucket
  mode it is `redact(error.refusal)`, a different string in the same field with the same type, so every
  build reads it. It does not carry the cure, for two reasons. The record keeps no fix for any code
  (the notice and the details do). And the cure (about 390 characters) with the refusal would pass the
  record's message limit and be cut. The details' `hint` stays `None` for this code, as t33's tests
  pin.
* **What "bucket mode" means here** is what t33 and `_hint_for` already use: `caselist.run_state =
  "bucket"` with a bucket named (`bracket.bucket_mode`, the service's `bucket_mode`). That includes a
  bucket-mode command run by hand on the Mac, as for t33's notice. ECS is not consulted, unlike t28's
  S3 login hint. A bucket-mode run reads the token the Wednesday login writes, whichever machine
  started it.
* **The download stage.** A 401 on an API download (a camp file) fails the download stage rather than
  ending the run. Its reason, which the record keeps and the command prints, quoted the whole sentence,
  and its hint was t28's "the next cloud run … or one started by hand". A run started by hand before
  Wednesday would be refused again. So in bucket mode the reason is the refusal and the hint is the
  same cure. When a stage fails on this code, `_hint_for` returns the cure alone, leaving out any other
  failed stage's own fix. Both together would be an expired login and a store refusal in one run; I
  judged that rare enough to keep the hint to one cure.
* **The backfile import showed the hand-login sentence** (the PM asked me to check). Its 401 escapes
  `plan()` (the dry run and the first thing `--execute` does) to the root handler, which printed the
  error's message. It now goes through the same context manager. In local mode the import lists
  archives before it returns its `NOT_IN_BUCKET_MODE` refusal, so a 401 there ends it as before, and a
  test pins that.

### Mutants (agreement 8)

No test here uses Hypothesis, so there is no example database to replay. Each run still set
`HYPOTHESIS_STORAGE_DIRECTORY` to a new empty directory. Each mutant was applied to the committed code
by a scratch script outside the repository, which ran the new test file with `hard_stop.py 115 …
pytest <file> -n 4 -p no:randomly` and restored the code with `git checkout HEAD --`. `git status` was
empty after every batch. Every catch was an assertion failure, never a crash or a collection error.
One attempt at 4b first failed to apply, because ruff had split the `with` across lines. Nothing was
changed and nothing ran; it was redone with the formatted text.

| Mutant | Result | Caught by |
|---|---|---|
| 1. The Mac's output changed: `message_for` gives the refusal in both modes | 2 failed, 13 passed | the Mac's record pin and the Mac's download pin |
| 1b. The Mac's output changed: the CLI's cure in both modes | 3 failed, 12 passed | the Mac's pull JSON and panel pins, and the Mac's backfile pin |
| 2. Bucket mode still says to log in by hand: `message_for` without its bucket-mode arm | 7 failed, 8 passed | every bucket-mode output, record and download test |
| 2b. The CLI keeps the exception's message (only the hint added) | 5 failed, 10 passed | the bucket-mode pull and backfile message and panel tests |
| 2c. The record not told the mode (`record_for_failure` without `bucket_mode`) | 1 failed, 14 passed | `test_a_bucket_mode_run_refused_for_auth_expired_records_no_login` |
| 2d. A camp download's reason keeps the exception's text | 1 failed, 14 passed | `test_a_bucket_mode_download_refused_for_auth_expired_names_the_wednesday_login` |
| 3. The cure given to another code: the CLI catches any `DomainError` | 1 failed, 14 passed | `test_a_bucket_mode_pull_stopped_by_another_code_than_auth_expired_names_no_wednesday_login` (404) |
| 3b. The cure given to any failed stage in bucket mode | 1 failed, 14 passed | `test_a_bucket_mode_download_failed_on_another_code_than_auth_expired_keeps_the_next_cloud_run` (404) |
| 4. The import's output left with the old sentence: `caselist_backfile.py` as at the start commit | 3 failed, 12 passed | the three bucket-mode backfile tests |
| 4b. The import's `--execute` left unwrapped | 2 failed, 13 passed | the `--execute` JSON test and the panel test |

The runbook pin was checked against the start commit's runbook: that file still says "a later image
changes it" and has no `v1-e40-t35` line, so the pin fails on it.

### Tests and checks run before this report

`uv run scripts/affected_tests.py` chose **361 of 643 test files (56.1%)** from 11 changed files
(15.3 s). `sync_runs.py` and `caselist_sync.py` are hub modules, so that set is well over two minutes.
Per agreement 10 I did not run it and leave it to the pull request's `ci`. Within the limit I ran the
changed areas and the always-run list. Each run was bounded at 115 s, with `-m "not slow and not
live" -n auto`:

| Run | Result |
|---|---|
| `packages/debate_core/tests/application/caselist` (t33's notice tests among them) | `1860 passed in 84.74s` |
| `packages/debate_core/tests/application/test_caselist_backfile_rules.py`, `test_caselist_backfile_survey.py`, every `test_caselist_sync*.py`, `test_sync_runs.py`, and `packages/debate_core/tests/integrations/opencaselist` | `444 passed in 6.04s` |
| `packages/debate_cli/tests/bucket_mode`, first half (backfile import, this task's file, held sources and uploads, kills, lock, login hint) | `138 passed in 94.38s` |
| `packages/debate_cli/tests/bucket_mode`, second half (OpenEv re-import, parse fix, publish hint, removal, rerun hint, restore, parse owed, restore run state) | `129 passed in 55.52s` |
| The always-run list (`tests/architecture`, `tests/specs`, `packages/debate_cli/tests/test_app.py`, `test_help_rendering.py`, `test_container_factories.py`), `commands/test_caselist_pull.py`, `commands/test_caselist_runs.py`, `test_output.py`, `tests/docs`, `tests/scripts/test_caselist_run_image_plan_check.py`, `test_check_command_blocks.py` | `892 passed in 59.67s` |

Whole-repo checks: `ruff format --check .` → `1777 files already formatted`; `ruff check .` → `All
checks passed!`; `pyright packages/debate_cli packages/debate_core` → `0 errors, 0 warnings, 0
informations`; `lint-imports` → `Contracts: 20 kept, 0 broken.`; `scripts/check_thin_handlers.py` →
`OK: 70 … within 25 statements`; `scripts/docs_index.py --check-descriptions` → `All 62 indexed
documents under docs/ have a description`; `scripts/check_links.py` → `OK: 3343 relative links and
anchors in 526 Markdown files`; `scripts/check_command_blocks.py` → `OK: no # comments in 646 shell
code blocks`; `uv run scripts/validate_specs.py` → `OK: 567 files, 41 epics, 504 tasks, 22 releases`.
`git diff origin/dev -- <this spec>` after a fetch shows only the phase change, so the PM has not
amended the spec on dev.

## Operator follow-ups

None. This build reaches the cloud run with the next caselist-run image, as every CLI change does.

## Follow-up work

* **`CASELIST_TOKEN_MISSING` and `CASELIST_TOKEN_UNREADABLE` still name `caselist auth login` in a
  bucket-mode command's output** (E40). Their messages are "no caselist_token is stored; run
  `debate-research caselist auth login` first" and "… run `debate-research caselist auth logout` and
  then `caselist auth login`", and the root handler prints them in either mode. The runbook's import
  refusal list says so. This task left them alone because its spec is `CASELIST_AUTH_EXPIRED`, and its
  mutant 3 forbids giving the cure to another code. A follow-up could give each its cloud cure through
  the same context manager, for example by widening it to a table of code → cure.
* **The notice of a bucket-mode run whose download stage failed on `CASELIST_AUTH_EXPIRED`** (E40,
  `sync_runs.py`'s failed-stage arm) still gives t28's "the next cloud run … or one started by hand".
  That is not a login by hand, but a run started by hand before Wednesday is refused again. The
  command's own hint for it now names the Wednesday login. t33's arm covers only a run the error ended,
  and this task does not change notifications, per the PM's context.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-01

**Notes:**

The fix t33 started is now complete. A bucket-mode run refused for an expired login no longer tells
anyone to log in by hand: not in the command's output, the CloudWatch log or `caselist runs --json`.
On the Mac every word is unchanged.

1. **ac1:** 7 of the new file's tests failed against the start code, each on an assertion, while
   the seven Mac pins passed. All 15 pass now, through the real command (CliRunner, moto and the
   respx stand-in answering 401). Every expected sentence is written by hand.
2. **Decisions accepted:**
   * **Replaced, not added to:** the refusal as the message and t33's cure as the hint. The code,
     details and exit status are unchanged.
   * **The clause-10 sentence dropped in bucket mode** is right. The runbook section the cure names
     carries the escalation, and a second wording would drift. If the escalation should reach the
     log, it goes into `CLOUD_AUTH_EXPIRED_CURE`, so the notice gets it too.
   * **`error_message`** is still a string, so every build reads it. The cure stays out of it
     because of the message limit and because the record holds no fixes.
   * **"Bucket mode"** means exactly what t33 and `_hint_for` mean by it.
   * **The camp download path** and **the backfile import** are both covered. Good catches.
   * **`CaselistAuthExpired.refusal` as a property** keeps the CLI's `details` (built from `vars()`)
     unchanged.
3. **Checked by the PM:**
   * `_camp_download_refused` moved from `str(refused)` to `message_for`, which falls through to
     `reported_error_message`. For a `DomainError` that is the same text, except that an empty
     message now gives the class name, which is better.
   * The context manager catches only `CaselistAuthExpired`, and only in bucket mode (mutant 3).
4. **Mutants:** 10, the PM's three kinds among them, all caught at assertions. The 4b slip was
   noticed and redone properly.
5. **Closing checks:** the affected set (361 files) is left to the PR's `ci` under agreement 10. The
   bounded groups (1,860, 444, 138, 129 and 892 passed), ruff, pyright, lint-imports, thin handlers
   and the doc and spec checks are clean.
6. **Follow-ups:** the PM files both in the next batch as one E40 p3 task, a table of code → cloud
   cure:
   * `CASELIST_TOKEN_MISSING` and `CASELIST_TOKEN_UNREADABLE` get their cloud cures in a bucket-mode
     command's output;
   * the notice's failed-stage arm names the Wednesday login for a download that failed on
     `CASELIST_AUTH_EXPIRED`.
7. **Merge:** a plain `scripts/task pr` once `ci` is green. The Goal is `Succeeded`, and there is no
   operator follow-up.

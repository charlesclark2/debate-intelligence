# Session report: v1-e40-t40-token-errors-name-the-cloud-cure

| | |
|---|---|
| Task | `v1-e40-t40-token-errors-name-the-cloud-cure` — In bucket mode a missing or unreadable token, and a download refused for an expired login, give the cloud's cure, not a login by hand |
| Spec | [`plan_specs/v1/e40-cloud-caselist-run/t40-token-errors-name-the-cloud-cure.yaml`](../../plan_specs/v1/e40-cloud-caselist-run/t40-token-errors-name-the-cloud-cure.yaml) |
| Epic / release | `v1-e40-cloud-caselist-run` / `v1.8` |
| Branch | `task/v1-e40-t40-token-errors-name-the-cloud-cure` |
| Session status | PARTIAL: built and tested; waiting for one PM ruling (the wording of the cure for the two token codes) |

## Summary

In bucket mode, `CASELIST_TOKEN_MISSING` and `CASELIST_TOKEN_UNREADABLE` no longer print the hand login
(or the logout and then the login). This holds for `caselist pull`'s and `caselist backfile-import`'s
output, the CloudWatch log and the run record. The message is now what happened (`no caselist_token is
stored`, `the caselist_token stored in the secretsmanager backend is not readable`), and the hint is a
Wednesday-login cure. A bucket-mode download refused for an expired login now carries t33's
Wednesday-login cure as its notice's fix line, where it used to give t28's "the next cloud run … or one
started by hand". t35's context manager is widened into one table of code → cloud cure,
`sync_runs.CLOUD_TOKEN_CURES`, and every cure is read from it: the output, the pull's failed-stage hint
and the notice. On the Mac every word is unchanged, pinned by its old text before anything changed.
**The PM's ruling is needed on one thing:** the runbook had no section for a cloud run stopped on these
two codes, so their cure's wording and its new runbook section are my proposal (Questions for the PM).
Everything else is built on that proposal, so the ruling changes two strings and the runbook section
at most. The Goal stays `InProgress` until the ruling.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `token-errors-name-the-cloud-cure` (Token cures) | Done, pending the wording ruling | Red tests `6ef985d`, implementation `45f1a34`, runbook `d848ec8` (after the sync onto dev with t44; before it they were `90f19c4`, `df62006`, `7ad057e`). |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: in bucket mode each code in the table prints its cloud cure and never a hand login, a download refused for an expired login gets the Wednesday-login cure in its notice, the Mac's output is unchanged and pinned by its old text, by tests shown failing first | PASS (on the proposed wording) | **Red** at `90f19c4` against the start code: `hard_stop.py 115 … pytest packages/debate_cli/tests/bucket_mode/test_bucket_mode_token_errors_name_the_cloud_cure.py -n 4 -p no:randomly` → `14 failed, 9 passed`. The 9 that passed are the seven Mac pins (pull JSON, panel and record for each token code, the backfile import for each, the notice of a refused download), the out-of-table code and the other-code download. Of the 14 failures, 13 were assertion failures: the message still carried the login, the hint was `None`, the email's fix line was t28's, or the runbook section was missing. One, the table test, failed on `ImportError` of the not-yet-existing `CLOUD_TOKEN_CURES`. **Green** after the implementation and the runbook: `38 passed` (this file's 23 and t35's 15). After the sync: `158 passed` (this file, t35's and every test file t44 changed). |
| Node: "Token cures tests pass" (`uv run pytest packages/debate_cli/tests -k token or auth_expired`) | PASS | `hard_stop.py 115 .venv/bin/python -m pytest packages/debate_cli/tests -k "token or auth_expired" -q -p no:randomly` → `55 passed in 24.87s`, after the sync `55 passed in 28.62s`: this task's 23, t35's 15, and 17 existing tests the keywords match. |

## Files changed

* **`debate_core.application`**:
  * `sync_runs.py`: `CLOUD_NO_TOKEN_RUNBOOK` and `CLOUD_NO_TOKEN_CURE` (the proposed wording);
    `CLOUD_TOKEN_CURES`, a read-only table mapping `CASELIST_AUTH_EXPIRED` to t33's cure and both token
    codes to the new one; `cloud_cure_for(codes)`. In `notifications_for`'s failed-stage arm, in bucket
    mode only, a stage that failed on a code in the table takes that code's cure as `fix_command`. Title,
    message and hint are unchanged. Docstring paragraph added.
  * `caselist_sync.py`: `message_for` in bucket mode returns `CaselistTokenMissing.finding` and, for
    `CASELIST_TOKEN_UNREADABLE`, the store's first clause worded from the error's `backend`.
    `_TOKEN_UNREADABLE_CODE` is now public as `TOKEN_UNREADABLE_CODE`, which the table uses.
  * `ports/caselist_source.py`: `CaselistTokenMissing.finding`, a property like `CaselistAuthExpired.refusal`.
    The message is built from it and is byte-identical. A property is not an instance attribute, so the
    CLI's `details` are unchanged (`{}`).
* **`debate_cli`**:
  * `caselist_auth_expired.py` → **`caselist_token_cures.py`**, renamed because it now covers three codes.
    `cloud_cure_for_a_token_error` catches a `DomainError` only in bucket mode, and only when the code the
    CLI reports for it is in the table. Anything else is re-raised unchanged. `in_bucket_mode(cure)`
    replaces `CLOUD_AUTH_EXPIRED_HINT`, with the same words.
  * `commands/caselist_pull.py` and `commands/caselist_backfile.py`: use the widened context manager.
    `_hint_for` asks the table instead of naming `CASELIST_AUTH_EXPIRED`.
* **`packages/debate_cli/tests/bucket_mode/test_bucket_mode_token_errors_name_the_cloud_cure.py`**: 23 tests
  through the real command (Typer `CliRunner`, moto, the respx stand-in site). In bucket mode the token
  is moto's Secrets Manager secret, as in the cloud. On the Mac it is the file backend's 0600 file. The
  notice is read as the coach's email: the real `sns` notifier publishes to a moto topic with a moto queue
  subscribed. Every expected sentence is written by hand.
* **`docs/runbooks/caselist-cloud-run.md`**: new section "A run with no readable caselist_token" (proposed,
  see the question). The import refusal list now says what t40 changed for the other two codes.
  **`docs/runbooks/caselist-scheduled-sync.md`**: one sentence saying the cloud run's own output now names
  the Wednesday login. Its notice is unchanged.

## Deviations from the spec

None. Everything is inside the spec's packages. `CaselistTokenUnreadable` lives in
`debate_core.integrations.opencaselist.token_store`, which is not one of them and is unchanged. So the
application words its bucket-mode clause from the error's `backend`, and a test ties the two sentences
together (below).

## Decisions and assumptions

* **One cure for both token codes.** The token secret is written by the Wednesday login, which replaces
  whatever it held (`put_secret_value`; caselist-cloud-credentials.md: "the next login replaces the
  token"). So an empty secret and an unreadable one have the same cure. The runbook's import refusal list
  already treats all three codes as one ("the token the run's login stored has expired, or there is
  none. The Wednesday 03:00 login renews it. Nobody logs in by hand").
* **Replaced, not added to**, as t35 did: in bucket mode the message is what happened, without the
  Mac's command, and the hint is the cure. The code, the details (`{}`, `{"backend": "secretsmanager"}`)
  and the exit status (1) are as before.
* **The record too.** `message_for` also writes the record's `error_message`, so `caselist runs --json`
  and the bucket's reports carry no hand login for these codes in bucket mode either. The record holds no
  cure, as for t35.
* **The table is keyed by the code the CLI reports** (`CommandFailure.from_exception(error).code`), so a
  cure can only appear beside the code it belongs to. The table test pins its keys to exactly these three.
* **`CaselistTokenUnreadable`'s clause is worded in the application.** The adapter is outside the spec's
  packages and the application may not import it. `_unreadable_token` builds `the caselist_token stored
  in the <backend> backend is not readable` from `backend`. A test asserts, for three backends, that the
  store's own message starts with that clause followed by its logout, so the two cannot drift apart
  unnoticed (mutant 12).
* **The stopped-run notice for the token codes is unchanged.** A bucket-mode run that stops on either
  code still emails `stopped: an error recorded as CASELIST_TOKEN_MISSING` with t28's "the next cloud
  run … or one started by hand". The PM's ruling limits the notice change to the failed-stage arm, and the
  spec's part (2) is the download only. The runbook section says so. See Follow-up work.
* **A code outside the table stays as it was.** `INSECURE_TOKEN_FILE` (a file backend whose token file
  others can read) is a token error that names `caselist auth login`, but it is not in the spec's table.
  In bucket mode it keeps its words, pinned. The cloud uses the Secrets Manager backend, so it should not
  meet it.
* **t44's overlap.** The sync conflicted in one hunk of `caselist_pull.py`: t44's
  `_refuse_a_scheduled_pull_it_cannot_guard` call before the run, and this task's renamed context manager
  around it. Both are kept, the guard first, as on dev. `fix_for`, the run-log notice title and the
  `RECENT_RUN_RECORDED` words merged cleanly and are unchanged. t44's tests pass beside these (`158 passed`
  above, and both halves of `bucket_mode`).

### Mutants (agreement 8)

No test here uses Hypothesis. Each run still set `HYPOTHESIS_STORAGE_DIRECTORY` to a new empty
directory. A scratch script outside the repository applied each mutant to the committed code (before
the sync, at `df62006`/`7ad057e`), ran this file and t35's with `hard_stop.py 115 … pytest -n 4 -p
no:randomly`, and restored with `git checkout HEAD --`. `git status` was empty after both batches. All
14 were caught, every one at an assertion, none by a crash or a collection error.

| Mutant | Result | Caught by |
|---|---|---|
| 1. The Mac's record changed: the no-token finding in both modes | 1 failed | the Mac's no-token panel-and-record pin |
| 2. The same for an unreadable token | 2 failed | the Mac's unreadable panel-and-record pin; the store-clause tie |
| 3. The Mac's output changed: the CLI's cure in both modes | 9 failed | every Mac output pin, t35's three among them |
| 4. The table without `CASELIST_TOKEN_MISSING` | 5 failed | the bucket-mode no-token output, panel and both backfile runs; the table pin |
| 5. The table without `CASELIST_TOKEN_UNREADABLE` | 5 failed | the same for an unreadable token |
| 6. A cure for a code outside the table | 4 failed | the `INSECURE_TOKEN_FILE` pin, both 404-download tests, t35's 404-listing test |
| 7. Bucket mode keeps the Mac's message for both token codes | 11 failed | every bucket-mode output, panel, record and backfile test |
| 8. The failed-stage arm without the table | 1 failed | the bucket-mode refused-download email |
| 9. The notice's token cure in both modes | 1 failed | the Mac's refused-download email pin |
| 10. The Wednesday cure for any failed stage in bucket mode | 1 failed | the bucket-mode 404-download email |
| 11. The pull's failed-stage hint: cure in both modes | 1 failed | t35's Mac download pin |
| 12. The unreadable clause drifts from the store's words | 6 failed | the bucket-mode unreadable tests; the store-clause tie |
| 13. The backfile dry run left unwrapped | 3 failed | the three bucket-mode dry-run backfile tests |
| 14. The unreadable code given the expired-login cure | 4 failed | the bucket-mode unreadable output, panel and backfile tests |

### Tests and checks run before this report

`uv run scripts/affected_tests.py` chose **417 of 755 test files (55.2%)** after the sync (413 of 750
before it) from 12 changed files. `sync_runs.py` and `caselist_sync.py` are hub modules, so that set is
well over two minutes. Under agreement 10 I did not run it and leave it to the pull request's `ci`.
Within the limit I ran the changed areas and the always-run list, after the sync. Each run was bounded
at 115 s, with `-m "not slow and not live" -n auto -p no:randomly`:

| Run | Result |
|---|---|
| `packages/debate_core/tests/application/caselist` (t33's and t44's notice tests among them) | `1955 passed in 104.39s` |
| every `packages/debate_core/tests/application/test_caselist_sync*.py`, `test_sync_runs*.py`, `test_caselist_backfile*.py`, and `packages/debate_core/tests/integrations/opencaselist` | `451 passed in 5.94s` |
| `packages/debate_cli/tests/bucket_mode`, first ten files | `169 passed in 104.15s` |
| `packages/debate_cli/tests/bucket_mode`, last ten files (this task's and t44's `test_scheduled_pull_guard.py` among them) | `146 passed in 61.13s` |
| every test file t44 changed, with this task's and t35's | `158 passed in 51.33s` |
| the always-run list (`tests/architecture`, `tests/specs`, `packages/debate_cli/tests/test_app.py`, `test_help_rendering.py`, `test_container_factories.py`), `commands/test_caselist_pull.py`, `commands/test_caselist_runs.py`, `test_output.py`, `tests/docs`, `tests/scripts/test_check_command_blocks.py` | `880 passed in 44.12s` |

Whole-repo checks, after the sync: `ruff format --check .` → `2090 files already formatted`; `ruff check
.` → `All checks passed!`; `pyright packages/debate_cli packages/debate_core` → `0 errors, 0 warnings, 0
informations`; `lint-imports` → `Contracts: 20 kept, 0 broken.`; `scripts/check_thin_handlers.py` → `OK: 74
CLI command and API route handlers within 25 statements`; `scripts/check_links.py` → `OK: 3813 relative
links and anchors in 657 Markdown files`; `scripts/check_command_blocks.py` → `OK: no # comments in 703
shell code blocks`; `scripts/docs_index.py --check-descriptions` → `All 71 indexed documents under docs/
have a description`; `uv run scripts/validate_specs.py` → `OK` (run again after this report, below).
`git diff origin/dev -- <this spec>` after a fetch shows only the phase change, so the PM has not amended
the spec on dev.

`scripts/task sync` rebased the branch onto `origin/dev` at `2d4a097` (t44 is `b99b8d6`). It stopped on
the one conflict above, which I resolved and continued. The branch has never been pushed (`git ls-remote
--heads origin <branch>` prints nothing), so the push the stopped sync skipped has nothing to update.

## Questions for the PM

One ruling. The runbook has a section for an expired login, and an import refusal bullet covering all
three codes, but no section for a cloud **run** stopped on `CASELIST_TOKEN_MISSING` or
`CASELIST_TOKEN_UNREADABLE`. So, as the ruling says, I propose the wording and the section that would hold
it, and built everything on that proposal:

```text
PM question from v1-e40-t40-token-errors-name-the-cloud-cure (2026-11-12)

The cloud runbook has no section for a cloud run stopped on CASELIST_TOKEN_MISSING or
CASELIST_TOKEN_UNREADABLE (only the import refusal bullet, which covers all three token codes for an
import). Proposed: one cure for both codes, and one new section in caselist-cloud-run.md, placed
after "A run refused for an expired login":

  Section: "A run with no readable caselist_token" (written on the branch, d848ec8)

  Cure (CLOUD_NO_TOKEN_CURE), shown as the command's hint "In bucket mode <cure>.":
  the next Wednesday 03:00 login writes a new caselist_token to the token secret, and the run after
  it takes up what this run did not finish, from the run state saved in the bucket; a backfile import
  refused for it starts again after Thursday 00:00 (caselist-cloud-run.md, "A run with no readable
  caselist_token"); never a login by hand, which would be a second login

  It is t33's cure with "renews the caselist_token" replaced by "writes a new caselist_token to the
  token secret" (an empty or unreadable secret is not renewed but replaced), and its own section.

Options:
  A. Accept the wording and the section as written.            (recommended)
  B. One section for all three codes: widen "A run refused for an expired login" and point both
     token codes at it with t33's cure word for word. Renaming that heading changes t33's runbook
     reference and its pinned email text, so it would be a wider change.
  C. Different words: give the cure text and the section heading.

Why A: the login task replaces whatever the secret holds, so both codes share a cure; the cure keeps
t33's shape (what puts it right, the section, what never to do); and its section sends the two real
escalations (the Wednesday login failed; a Wednesday run stopped although its login sent no failure
email) to the PM, as t33's does.

On A, the session sets the Goal to Succeeded and finishes the report. On B or C it changes
CLOUD_NO_TOKEN_CURE / CLOUD_NO_TOKEN_RUNBOOK, the test's two pinned strings and the runbook, reruns
the file, and finishes.
```

## Operator follow-ups

None. This reaches the cloud run with the next caselist-run image, as every CLI change does. No command
today and no deploy.

## Follow-up work

* **The stopped-run notice for the two token codes** (E40, `sync_runs.py`'s "stopped on an error" arm).
  A bucket-mode run that stops on `CASELIST_TOKEN_MISSING` or `CASELIST_TOKEN_UNREADABLE` still emails
  t28's "the next cloud run … the weekly run, or one started by hand". A run started by hand before the
  Wednesday login stops again. Its log's hint now names the Wednesday login, so the email and the log
  disagree. A follow-up could give that arm the table's cure for a code in it, as t33's arm does for an
  expired login. That would take a decision on the title, since t33 gave the expired login a title of
  its own. This task did not touch it, per the ruling that the notice change is in the failed-stage arm.
* **`INSECURE_TOKEN_FILE`** names `caselist auth login` in bucket mode too. It is outside the table by
  the spec. The cloud's backend never raises it, so I judge it not worth a cure unless a bucket-mode run
  on the Mac with the file backend is a case the PM wants covered.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

# Session report: v1-e40-t50-a-stopped-run-notice-for-a-token-error-gives-the-cloud-cure

| | |
|---|---|
| Task | `v1-e40-t50-a-stopped-run-notice-for-a-token-error-gives-the-cloud-cure` — A cloud run stopped on a token error, or refused its secret, emails the cure a person can act on |
| Spec | [`plan_specs/v1/e40-cloud-caselist-run/t50-a-stopped-run-notice-for-a-token-error-gives-the-cloud-cure.yaml`](../../plan_specs/v1/e40-cloud-caselist-run/t50-a-stopped-run-notice-for-a-token-error-gives-the-cloud-cure.yaml) |
| Epic / release | `v1-e40-cloud-caselist-run` / `v1.8` |
| Branch | `task/v1-e40-t50-a-stopped-run-notice-for-a-token-error-gives-the-cloud-cure` |
| Session status | COMPLETE |

## Summary

In bucket mode, a cloud run that stops on `CASELIST_TOKEN_MISSING` or `CASELIST_TOKEN_UNREADABLE` now
emails `caselist pull stopped: no readable caselist_token`. Its fix line is t40's table cure, the Wednesday
login, and it has no verdict sentence. Before, it emailed t28's "the next cloud run … or one started by
hand".

A run whose read of the token secret is refused (`STORE_ACCESS_DENIED` at `GetSecretValue`, an IAM or a
decrypt refusal alike) now emails `caselist pull stopped: token secret refused, needs a person`. Its fix
line sends the PM the run's id and the code. Before, it emailed `will be retried` and blamed "this machine
or the bucket". It is told apart from a bucket's refusal by the error's structured `operation`, and the
same escalation is the run's log hint and its details' hint, from one `fix_for`.

The Mac's words are pinned and unchanged, and so are the exit codes. I measured first and proposed. The PM
ruled on 2026-11-14 and reworded the fix line to name the code, never the class. Then came the red tests
(21 failed at assertions), the code, the runbooks, and 12 mutants, all caught at assertions. The Goal is
`Succeeded`.

The PM should look first at the three existing tests rewritten because they pinned the old notice
(Decisions). The branch's affected set (366 files) is left to the pull request's `ci` under agreement
10, and one larger local run was denied by the permission classifier (Tests and checks).

## Measured before any change

A scratch test, never committed and deleted after one run, put the real command (`caselist pull` through
Typer's `CliRunner`) on `packages/debate_cli/tests/bucket_mode/conftest.py`'s world, at `42f1c3d`:
moto's bucket, and the coach's inbox read as t40's tests read it (the real `sns` notifier publishing to a
moto topic with a moto queue subscribed). Two weeks were seeded and a third listed, then the run was a
cloud task in bucket mode on its own empty data directory. No AWS, and no notice actually sent.

* **The two token codes.** The token was moto's Secrets Manager secret `debate-dev-caselist-token`, with
  no value (`CASELIST_TOKEN_MISSING`) or holding `not a record this program wrote`
  (`CASELIST_TOKEN_UNREADABLE`).
* **The refused secret.** A stand-in Secrets Manager client (`build_secrets_manager_client` replaced)
  whose `get_secret_value` raises botocore's `ClientError` with `AccessDeniedException` (IAM denied) or
  `DecryptionFailure` (decrypt refused). Moto cannot refuse a KMS decrypt.

Command: `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest <scratch file> -n 0 -q` →
`4 passed in 14.91s`. Each email below is the queue message's body exactly, with `\n` as line breaks. The
run id was `20261021T110005Z` in every case.

| Case | Exit | Code (`--json` `error.code`) | `error.hint` | Record `error_class` | Details `hint` |
|---|---|---|---|---|---|
| `CASELIST_TOKEN_MISSING` | `1` | `CASELIST_TOKEN_MISSING` | t40's no-token cure, `In bucket mode the next Wednesday 03:00 login …` | `CaselistTokenMissing` | `null` |
| `CASELIST_TOKEN_UNREADABLE` | `1` | `CASELIST_TOKEN_UNREADABLE` | the same | `CaselistTokenUnreadable` | `null` |
| `AccessDeniedException` at `GetSecretValue` | `3` | `STORE_ACCESS_DENIED` | `null` | `StoreAccessDenied` | `null` |
| `DecryptionFailure` at `GetSecretValue` | `3` | `STORE_ACCESS_DENIED` | `null` | `StoreAccessDenied` | `null` |

The two refused cases print the same message, `not allowed to GetSecretValue secret
debate-dev-caselist-token`, with details `{"operation": "GetSecretValue", "resource": "secret
debate-dev-caselist-token"}`. As v1-e40-t40 established, a decrypt failure is `STORE_ACCESS_DENIED`.

**The email for `CASELIST_TOKEN_MISSING`** (and the same for `…_UNREADABLE`, with that code):

```text
caselist pull failed: needs a person
Run 20261021T110005Z (dev)

Run 20261021T110005Z (dev) stopped: an error recorded as CASELIST_TOKEN_MISSING. A person should look: at least one failure here will be the same on the next scheduled run.

Fix: the next cloud run takes up what this run did not finish, from the run state saved in the bucket: the weekly run, or one started by hand (caselist-cloud-run.md, "A failed or stopped run"); never a publish from the operator's Mac
```

**The email for a refused secret read**, the same for `AccessDeniedException` and `DecryptionFailure`:

```text
caselist pull failed: will be retried
Run 20261021T110005Z (dev)

Run 20261021T110005Z (dev) stopped: this machine or the bucket refused it. The next scheduled run should retry it: every failure here is one a later run may not meet.

Fix: the next cloud run takes up what this run did not finish, from the run state saved in the bucket: the weekly run, or one started by hand (caselist-cloud-run.md, "A failed or stopped run"); never a publish from the operator's Mac
```

That email is wrong three ways for the refused secret. It says `will be retried` where a person is needed.
It blames "this machine or the bucket" when the secret refused the read. It offers "one started by hand",
which is refused the same way.

## Plan nodes

<!-- One row per Plan graph node, in the order they were completed. -->

| Node | Status | Notes |
|---|---|---|
| `a-stopped-run-notice-for-a-token-error-g` (Stopped-run cures) | Done | Measurements `6ef65c3`, proposal `473300f`, red tests `6e47f91`, implementation `e4700a6`, runbooks `4c2a8b6`, a pyright fix in a test `e33f4f0`; the phase and this report in the last commit. |

## Acceptance criteria

<!-- Goal criteria (ac1…) and every node criterion. Status: PASS / FAIL / NOT RUN. -->

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the proposal is ruled on, and the stopped-run notice for the two token codes and the refused-secret run give the ruled cure in bucket mode only, by tests shown failing first | PASS | **Ruled**: the PM's ruling of 2026-11-14, below. **Red** at `6e47f91` against the unchanged code: `hard_stop.py 115 … pytest <the five test files below> -n 4 -p no:cacheprovider --tb=line` → `21 failed, 44 passed in 23.98s`. Every failure was at an assertion: the old title or fix line, a `None` hint, or a runbook section or row not yet there. The 44 passes include the new Mac pins (five in the core file, three in the CLI file) and the two S3-refusal pins, all of which must hold before and after. **Green** after the code and the runbooks: `65 passed` over the same files. **Bucket mode only**: the Mac pins pass at red and at green, and mutants 2a, 2b and 2c (a cure on the Mac) are each caught by them. |
| Node: "Stopped-run cures tests pass" (`uv run pytest packages/debate_core/tests packages/debate_cli/tests -k "token or access_denied"`) | PASS | `hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests packages/debate_cli/tests -k "token or access_denied" -n auto -q -p no:cacheprovider` → `270 passed in 65.26s`. |

## Files changed

* **`debate_core.application`**:
  * `caselist_sync.py`: `TOKEN_SECRET_READ` (`"GetSecretValue"`), `CLOUD_REFUSED_TOKEN_SECRET_RUNBOOK` and
    `CLOUD_REFUSED_TOKEN_SECRET_CURE` (the ruled words), and `refused_its_token_secret(error)`. That is a
    `StoreAccessDenied`, not a `LocalStoreAccessDenied`, whose `operation` is `GetSecretValue`. `fix_for`
    returns the cure for one in bucket mode only, before every other branch. Docstring paragraph added.
  * `sync_runs.py`: `NO_READABLE_TOKEN_TITLE` and `REFUSED_TOKEN_SECRET_TITLE` (exported), the predicates
    `_no_readable_token_code` and `_refused_its_token_secret`, and two arms in `notifications_for` after
    the expired login's.
    * The token arm's fix is `CLOUD_TOKEN_CURES[code]`, and its message comes from `_what_stopped_it`
      with no verdict.
    * The refused-secret arm fires when the details' hint is the cure, which only `fix_for` writes.
    * `banner_words` gives `None` for both, since neither title is a verdict.
    * Docstring paragraph added.
* **`debate_cli`**: `caselist_auth_cures.py`'s context manager also catches a refused token-secret read
  in bucket mode. The message is unchanged, the hint is `In bucket mode <fix_for's cure>.`, and the exit
  stays 3. It wraps `caselist pull` and `caselist backfile-import`, as for the token codes.
* **`packages/debate_core/tests`**:
  * New: `application/caselist/test_stopped_run_notices_for_a_token_code_or_a_refused_token_secret.py`,
    20 tests. They build a stopped run as the monitor does (`record_for_failure`, `details_for_failure`,
    the details' `bucket_run`, then `notifications_for` with the command's retry rule) and cover:
    * the Mac pins;
    * both arms in `dev` and `prod`;
    * the S3 refusal keeping today's notice;
    * no exception class name in the notice;
    * `fix_for`, and the runbooks.
  * Rewritten to the ruled notice (Decisions): the bucket-mode tests in `test_pull_token_missing_hint_on_the_mac.py`
    and `test_pull_token_unreadable_hint_on_the_mac.py`, and the two token params of
    `test_pull_auth_expired_notice_names_the_wednesday_login.py`'s neighbouring-codes test.
* **`packages/debate_cli/tests`**: a new section of
  `bucket_mode/test_bucket_mode_token_errors_name_the_cloud_cure.py` (9 tests, reusing t40's helpers),
  run through the real command. It holds:
  * the Mac's refused-secret output and email, and the Mac's no-token email;
  * the bucket-mode token emails;
  * the refused secret's output, details, email and panel for both `AccessDeniedException` and
    `DecryptionFailure` (a stand-in client raising botocore's `ClientError`);
  * a bucket-mode backfile import refused its secret.
* **`docs/runbooks`**:
  * `caselist-cloud-run.md`:
    * "A run with no readable caselist_token" quotes the new email.
    * The new section "A run refused its token secret" holds t40's `STORE_ACCESS_DENIED` paragraph,
      rewritten, with a pointer left behind. It tells the person to read `error_class` from
      `debate-research caselist runs --remote --json`.
    * "A failed or stopped run" names both exceptions.
  * `caselist-run-alerts.md`: two rows in "When an alert arrives".
  * `caselist-scheduled-sync.md`: its sentence that the cloud notice "names the code and the next cloud
    run … as before" now says what t50 changed. The Mac's title table is untouched, as ruled.

## Deviations from the spec

None. Everything is inside the spec's packages. Two places where the ruling was met in a way the PM
may want to check are under Decisions: the `prod` environment is pinned at the notice-building level,
not through the CLI, and the backfile import shares the refused secret's hint.

## Decisions and assumptions

* **Three existing tests pinned the old bucket-mode token notice, and are rewritten.**
  `test_a_bucket_mode_run_stopped_by_token_missing_is_unchanged` and its unreadable twin asserted t28's
  fix line, the `needs a person` title and the verdict sentence, word for word. t33's neighbouring-codes
  test asserted no "Wednesday" for both token codes. The ruling changes exactly that. The first two
  become `…_names_the_wednesday_login` with the ruled title, message and cure. The third keeps its
  `STORE_UNAVAILABLE` case, and its docstring points to the new file. They were rewritten in the red
  commit, and their two rewritten cases are among its 21 failures.
* **How the notice knows it was the secret.** `fix_for` (bucket mode) decides from the error's
  `operation`, and `details_for_failure` already writes `fix_for` as the details' hint, so the arm
  compares the details' hint with the cure. That is a comparison with a constant this project wrote,
  never the error's message. `hint_for_a_record` leaves the cure unchanged: it has no absolute path,
  single spaces, and is under 1200 characters. A test pins `details.hint` to the cure. No
  `SyncRunDetails` key was added (its top-level keys are pinned).
* **`prod` is pinned where the environment enters the notice.** `where` is `record.environment`, so the
  core file runs both arms for `dev` and `prod` through `record_for_failure`, which is the monitor's own
  path. The CLI's bucket-mode world is wired for dev only: one `dev.toml` profile and `DEBATE_ENV=dev`.
  So the CLI tests run in dev. Mutant 5, which writes `(dev)` literally, is caught by the three `prod`
  cases.
* **The log's hint uses t40's idiom**: `In bucket mode <cure>.`, the same words as the email's fix line
  and the details' hint. The message stays `not allowed to GetSecretValue secret debate-<env>-caselist-token`.
* **The backfile import gets it too.** The context manager wraps both `caselist pull` and `caselist
  backfile-import`, as it does for the token codes. A backfile import is also a cloud task the token
  secret can refuse, so its log gives the same escalation. One test pins it. The ruling said "the run's
  output". If the PM wants only the pull, it is a `bucket_mode` flag on that one call site.
* **The no-class-name test** collects every exception class loaded in the process, botocore's
  `ClientError` among them, plus AWS's `AccessDeniedException` and `DecryptionFailure`. It asserts that
  no word of the notice's title, message, hint or fix is one of them. It checks that `StoreAccessDenied`
  is in the set, so it cannot pass vacuously. The CLI test also checks the email for those three names.
* **Exit codes are unchanged** (ruling 3): `1` for the token codes and `3` for the refused secret,
  asserted in the CLI tests.
* **The measurement probe** was an uncommitted scratch test in `packages/debate_cli/tests/bucket_mode`,
  run once and deleted; `git status --porcelain` was empty after.

### Mutants

No test here uses Hypothesis. Each run still set `HYPOTHESIS_STORAGE_DIRECTORY` to a new empty directory.
A scratch script outside the repository applied each mutant to the committed code at `4c2a8b6`. It ran
the five test files with `hard_stop.py 115 … pytest -n 4 -p no:cacheprovider --tb=line` in three
batches of four, and restored each with `git checkout HEAD --`. `git status --porcelain` was empty after
every batch. All 12 were caught, every one at an assertion: none by a crash or a collection error.

| Mutant | Result | Caught by |
|---|---|---|
| 1. A token code gets the old "next cloud run" fix line (the PM's) | 10 failed | both arms' core tests (dev, prod), the no-run-by-hand test, both CLI emails, both rewritten tests |
| 2a. A cure on the Mac: the token-code notice in either mode (the PM's) | 7 failed | the Mac's no-token and unreadable notice pins in the core file, the CLI and t34-35/t36's Mac tests |
| 2b. A cure on the Mac: `fix_for` escalates a refused secret in either mode (the PM's) | 5 failed | the Mac refused-secret pins (both CLI codes, both core cases) and the `fix_for` Mac test |
| 2c. A cure on the Mac: the CLI gives the hint in either mode (the PM's) | 8 failed | the Mac refused-secret CLI pins and t40's six Mac output pins |
| 3. A refused S3 read gets the secret's notice: `operation` not checked (the PM's) | 2 failed | both S3-refusal pins |
| 4. The class name in the notice: "its error class, StoreAccessDenied" (the PM's) | 8 failed | the no-class-name test, at `assert {'StoreAccessDenied'} == set()`, and every exact-text test |
| 4b. The class name added beside the code, every other word kept | 1 failed | the no-class-name test, at the same assertion (run on its own) |
| 5. The environment written as `(dev)` | 3 failed | the three `prod` cases |
| 6. `banner_words` not told of the new titles | 1 failed | the core record-and-hint test (`retry once fixed` instead of `None`) |
| 7. The log's hint stays `null` for a refused secret | 4 failed | the CLI output, panel and backfile tests |
| 8. The token notice keeps the person verdict | 10 failed | every bucket-mode token test |
| 9. The refused-secret notice repeats its hint | 4 failed | the core notice test (dev, prod) and both CLI emails |
| 10. A token code given the expired login's cure | 8 failed | every exact fix-line test of the token arm |

### Tests and checks run before this report

`uv run scripts/affected_tests.py` chose **366 test files** from the branch's changes. `sync_runs.py` and
`caselist_sync.py` are hub modules, and t40's set of 417 files was well over two minutes. Under agreement
10 I did not run it, and I leave it to the pull request's `ci`. Within the limit I ran the changed areas
and the always-run list. Each run was bounded at 115 s, with `-m "not slow and not live" -n auto -p
no:cacheprovider`:

| Run | Result |
|---|---|
| the node's command (`packages/debate_core/tests packages/debate_cli/tests -k "token or access_denied"`) | `270 passed in 65.26s` |
| the 33 test files that call `notifications_for`, `banner_words`, `fix_for`, `SyncRunMonitor`, `cloud_cure_for` or the CLI's cure module, with every `application/test_caselist_sync*.py` and `test_sync_runs*.py` | `543 passed in 80.96s` |
| `packages/debate_cli/tests/bucket_mode`, first ten files | `169 passed in 80.84s` |
| `packages/debate_cli/tests/bucket_mode`, last ten files (this task's among them) | `155 passed in 49.86s` |
| the always-run list (`tests/architecture`, `tests/specs`, `packages/debate_cli/tests/test_app.py`, `test_help_rendering.py`, `test_container_factories.py`), `tests/docs`, `tests/scripts/test_check_command_blocks.py` | `707 passed in 36.27s` |

**Not run:** the whole of `packages/debate_core/tests/application/caselist` in one command (t40's run:
`1955 passed in 104.39s`). The permission classifier denied that command, so I ran the 33 files above
instead. The pull request's `ci` runs it within the affected set. None of the changed test files holds a
slow test.

Whole-repo checks, after the last commit:
* `ruff format --check .` → `2125 files already formatted`
* `ruff check .` → `All checks passed!`
* `pyright packages/debate_cli packages/debate_core` → `0 errors, 0 warnings, 0 informations` (the first
  run found one unread variable in a new test, fixed in `e33f4f0`)
* `lint-imports` → `Contracts: 20 kept, 0 broken.`
* `scripts/check_thin_handlers.py` → `OK: 74 CLI command and API route handlers within 25 statements`
* `scripts/check_links.py` → `OK: 3893 relative links and anchors in 673 Markdown files`
* `scripts/check_command_blocks.py` → `OK: no # comments in 719 shell code blocks`
* `scripts/docs_index.py --check-descriptions` → `All 72 indexed documents under docs/ have a description`
* `uv run scripts/validate_specs.py` → `OK: 685 files, 41 epics, 622 tasks, 22 releases`

`git diff origin/dev -- <this spec>` shows only the phase change, against the local `origin/dev` ref
(2026-11-14 21:41) without a fetch, so the PM had not amended the spec on dev as of that ref.

## Questions for the PM

Proposed 2026-11-14 after the measurements above. **Ruled by the PM the same day**, and built as
ruled:

1. Token codes: accepted as proposed. `(dev)` must be the run's own environment, pinned in both
   environments: the core file runs `dev` and `prod`.
2. Refused secret: accepted, with the fix line reworded for item 4 to `send the PM the run's id and its
   code, STORE_ACCESS_DENIED; the error class is in caselist runs --remote --json (caselist-cloud-run.md,
   "A run refused its token secret"); never an IAM or key-policy change by hand`. The runbook section,
   the move of t40's paragraph and the two alert rows are accepted. The Mac's title table is left alone.
3. Exit codes: no change.
4. **B**: v1-e34-t19's rule stands. The notice names the code and points to `caselist runs --remote
   --json` for the class, with a test that no exception class name is in it.
5. In bucket mode the run's output and record carry the same escalation as their hint, from the same
   `fix_for`. The Mac stays byte-identical.

The proposal as sent:

**1. The two token codes, bucket mode, a run stopped on either.** This is a new arm before the
generic stopped-run arm, keyed on the run's failure code being one of the two.

* Title: `caselist pull stopped: no readable caselist_token`. It is named after the runbook section
  the cure points to, as t33's title is.
* Message: `Run <id> (dev) stopped: an error recorded as CASELIST_TOKEN_MISSING, so it fetched
  nothing from OpenCaselist.` (or `…_UNREADABLE`). The code stays named, as bucket mode names these
  two today (`_WORDS_OUTSIDE_BUCKET_MODE_ONLY`). There is no verdict sentence. Today's "at least one
  failure here will be the same on the next scheduled run" is untrue: the Wednesday login comes before
  that run and cures it. t33's expired-login notice has no verdict either.
* Fix line: `CLOUD_TOKEN_CURES[code]`, which is t40's `CLOUD_NO_TOKEN_CURE`, read from the table and not
  reworded.
* No hint (the details' hint is `null` for these in bucket mode). `caselist runs`' banner words are
  unchanged (`None`). The Mac is unchanged.

**2. The refused secret, bucket mode, a run stopped on `StoreAccessDenied` at `GetSecretValue`.**

* Title: `caselist pull stopped: token secret refused, needs a person`.
* Message: `Run <id> (dev) was refused its read of the caselist_token secret (GetSecretValue) and
  fetched nothing. A person is needed: the next login does not cure it, and every run is refused the
  same way until the run role can read the secret again.`
* Fix line: `send the PM the run's id and its error class, StoreAccessDenied (caselist-cloud-run.md,
  "A run refused its token secret"); never an IAM or key-policy change by hand`.
* How the notice knows it was the secret: in bucket mode, `fix_for` gives this cure for a
  `StoreAccessDenied` whose `operation` is `GetSecretValue`. That is a structured field of the error,
  not its message. `details_for_failure` already writes `fix_for` as the details' hint, and the new arm
  fires when the details' hint is this cure. A bucket (S3) refusal keeps today's notice. A new
  `SyncRunDetails` field was rejected because the details' top-level keys are pinned by the
  dev.200-schema test.
* `banner_words` gives `None` for it, since the title is not a verdict.
* Runbook: a new section `## A run refused its token secret` after "A run with no readable
  caselist_token". t40's `STORE_ACCESS_DENIED` paragraph moves there, and a one-line pointer stays.
* Notice table: two rows in `caselist-run-alerts.md`'s "When an alert arrives". The Mac's title table in
  `caselist-scheduled-sync.md` is left alone, because the Mac never sends these titles.

**3. Exit codes: no change (recommended).** `debate_cli.exit_codes` is shared with the Mac. Changing
`STORE_ACCESS_DENIED`'s exit would change the Mac's exit for every store refusal, which is forbidden.
A split for bucket mode only buys nothing: the cloud's task-stopped alarm fires on any nonzero exit
(`alerts.tf`, `anything-but 0`) and quotes the exit code. Both new titles are titles of their own, as
t33's is, not the verdict titles, so exit 3 with "needs a person" in a title does not break
v1-e34-t19's rule that the verdict and the exit are one decision.

**4. Naming the class.** `notifications_for`'s docstring says no notification names an exception's
class (v1-e34-t19). Item 2 names `StoreAccessDenied` in the fix line, as the PM's brief asks and as the
runbook's escalation already does. A: name the class as written (recommended). B: name the code
`STORE_ACCESS_DENIED` and say the class is in `caselist runs --remote --json`'s `error_class`.

**5. The run's log for a refused secret.** Its hint stays `null` (recommended: the spec covers the
email, and nothing contradicts it). Alternatively the CLI could print the same escalation as its hint.

## Operator follow-ups

<!-- Commands the operator must run (anything over ~2 minutes), with where to run them, the exact
command, expected runtime and what success looks like. Also GitHub/AWS settings to change. -->

None.

## Follow-up work

<!-- Bugs, gaps or ideas outside this task's scope, each with the task or epic it belongs to.
The PM decides whether they become spec changes or new tasks. -->

* **The CLI's bucket-mode test world runs dev only** (`packages/debate_cli/tests/bucket_mode/conftest.py`:
  one `dev.toml`, `DEBATE_ENV=dev`). As prod takes the run over, a prod variant of the world would let a
  test run the real command as prod. Every notice's environment is pinned in the core tests meanwhile.
  E40 or E41's upkeep.
* **The refused secret sends two emails.** One is this notice. The other is the task-stopped alarm's
  "stopped with exit code 3" (`alerts.tf`, which fires on any nonzero exit), as every stopped run does.
  That was the case before. The alerts runbook's row for the new email does not mention the second. I
  judge it not worth a task unless the PM wants the row to say so.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

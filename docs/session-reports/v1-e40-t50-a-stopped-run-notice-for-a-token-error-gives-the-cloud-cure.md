# Session report: v1-e40-t50-a-stopped-run-notice-for-a-token-error-gives-the-cloud-cure

| | |
|---|---|
| Task | `v1-e40-t50-a-stopped-run-notice-for-a-token-error-gives-the-cloud-cure` — A cloud run stopped on a token error, or refused its secret, emails the cure a person can act on |
| Spec | [`plan_specs/v1/e40-cloud-caselist-run/t50-a-stopped-run-notice-for-a-token-error-gives-the-cloud-cure.yaml`](../../plan_specs/v1/e40-cloud-caselist-run/t50-a-stopped-run-notice-for-a-token-error-gives-the-cloud-cure.yaml) |
| Epic / release | `v1-e40-cloud-caselist-run` / `v1.8` |
| Branch | `task/v1-e40-t50-a-stopped-run-notice-for-a-token-error-gives-the-cloud-cure` |
| Session status | IN PROGRESS <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

Step 1 (measure, no code change) is done; the proposal is with the PM for a ruling before any code.

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
| | | |

## Acceptance criteria

<!-- Goal criteria (ac1…) and every node criterion. Status: PASS / FAIL / NOT RUN. -->

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| | | |

## Files changed

<!-- Group by package or directory; one line on why each group changed. -->

## Deviations from the spec

None.

## Decisions and assumptions

<!-- Choices the spec left open, with the reasoning. -->

## Questions for the PM

Proposed 2026-11-14 after the measurements above. Awaiting the ruling; no code yet.

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

None.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

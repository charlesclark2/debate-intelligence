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

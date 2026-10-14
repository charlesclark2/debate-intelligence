# Session report: v1-e99-t01-partly-merged

| | |
|---|---|
| Task | `v1-e99-t01-partly-merged` — A task merged with --partial |
| Spec | `plan_specs/v1/e99-fixture/t01-partly-merged.yaml` |
| Epic / release | `v1-e99-fixture` / `v1.0` |
| Branch | `task/v1-e99-t01-partly-merged` |
| Session status | PARTIAL |

## Summary

The first session's work is done. The Goal stays InProgress because ac2 needs the operator.

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 | PASS | `true` → exit 0 |
| ac2 | NOT RUN | needs the operator's device |

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-09-23

**Notes:**

Accepted for a --partial merge. ac2 stays NOT RUN until the operator has the device.

### Operator follow-up 1, recorded (PM, 2026-09-30)

**Follow-up 1: FAIL.** The device was not reachable, so ac2 is still open and the Goal stays
InProgress.

## Resumed 2026-10-08: the second session

| | |
|---|---|
| Session status | COMPLETE |

### Summary

The second session ran ac2 on the device. Everything above is the first session's report, its
review and the PM's record, unchanged.

### Acceptance criteria, as they stand

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 | PASS | unchanged from the first session |
| ac2 | PASS | `device-check` → exit 0 |

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-09

**Notes:**

Accepted. ac2 passes on the device.

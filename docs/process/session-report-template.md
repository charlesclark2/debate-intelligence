# Session report template

`scripts/task start` copies everything below the marker into
`docs/session-reports/<task>.md` and fills in the placeholders. The implementation session
completes every section except **PM review**; the PM completes that section. The report is
committed on the task branch and merged with the work, so `docs/session-reports/` is the
permanent record of what each session did and why it was accepted.

Rules for the session:

* Evidence, not assertion: every acceptance criterion lists the command that was run and its
  result (exit code, test counts, or the relevant output line).
* `NOT RUN` is an honest answer; say why (for example, handed to the operator because it runs
  longer than 2 minutes) and put the command under **Operator follow-ups**.
* Anything that differs from the spec goes under **Deviations**, with the reason. Do not edit the
  spec to match the code without saying so here.

<!-- TEMPLATE START -->
# Session report: {{TASK}}

| | |
|---|---|
| Task | `{{TASK}}` — {{TITLE}} |
| Spec | [`{{SPEC}}`](../../{{SPEC}}) |
| Epic / release | `{{EPIC}}` / `{{RELEASE}}` |
| Branch | `task/{{TASK}}` |
| Session status | IN PROGRESS <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

<!-- 3-6 sentences: what was built, how it fits the epic, anything the PM should look at first. -->

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

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

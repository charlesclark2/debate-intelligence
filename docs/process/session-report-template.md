<!-- docs-index: Template for session reports -->
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
* **A later review is appended; no earlier review is ever renamed or edited.** When work comes back
  for a second review, after `CHANGES_REQUESTED` or in a task restarted with `scripts/task resume`
  after a `--partial` merge, the session leaves everything already in the report as it is, adds its
  own dated section after it (for example `## Resumed 2026-10-08: <what this session did>`), and
  ends the report with a new, empty **PM review** section copied from below. `scripts/task` reads
  the last verdict line in the report, so that new review decides and the earlier ones are history
  ([task-workflow.md](task-workflow.md#4-pm-review)).

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

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

# Session report: v1-e01-t40-planted-break-nearest-ordering

| | |
|---|---|
| Task | `v1-e01-t40-planted-break-nearest-ordering` — The planted-break check runs the tests nearest a break by what reads it, not by path |
| Spec | [`plan_specs/v1/e01-repo-foundation/t40-planted-break-nearest-ordering.yaml`](../../plan_specs/v1/e01-repo-foundation/t40-planted-break-nearest-ordering.yaml) |
| Epic / release | `v1-e01-repo-foundation` / `v1.0` |
| Branch | `task/v1-e01-t40-planted-break-nearest-ordering` |
| Session status | PARTIAL: waiting on the PM's ruling on durations <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

Interim, 2026-10-30. The planted-break check now orders a break's traced tests by a mention of a
changed name, then by whether the route `--explain` gives reads every file on it by a path, then by
chain and path. `scripts/affected_tests.py --explain` says `has a path to` for a path literal (the
selector already told it from a word; selection is unchanged). Every planted break is caught and
the unreached one is not, each in 14 to 28 s, and t39's break is caught without `read_by`, which is
removed. **Ordering by durations is not done:** no test durations are recorded anywhere a session
can read offline, so per the PM's instruction the session stopped and asked (below, Deviations).

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

* **No recorded durations to order by (open, asked of the PM).** The spec says "then the fastest by
  the last recorded durations". Nothing records them where the harness can read them offline:
  validate-dev's tiers write JUnit XML into a temporary work directory on the runner and upload
  nothing (`scripts/validate_dev.py` `run_tier`); ci.yml uploads only coverage data, kept one day,
  and its `--durations=25` is in the job log; the pytest cache holds `lastfailed` and `nodeids`;
  no durations plugin is locked (`uv.lock`: pytest, pytest-cov, pytest-socket, pytest-xdist); and
  `tests/pytest_plugins/run_in_parts.py` declined a recorded-durations file as one "that would go
  stale". The session stopped and asked, as the PM's context said to.
* **`scripts/affected_tests.py` changed, its labels only.** `--explain` lumped a path literal that
  denotes a file (`denoters`) with a word that matches its name into `names`. A path literal now
  reads `has a path to`. Same mentioners, same reach order, neither label a fixture edge: the
  selected sets of all 14 breaks are byte-identical before and after (`cmp` of each selection).

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

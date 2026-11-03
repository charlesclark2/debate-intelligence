# Session report: v1-e31-t23-in-round-markers

| | |
|---|---|
| Task | `v1-e31-t23-in-round-markers` — In-round markers kept in a card's evidence text |
| Spec | [`plan_specs/v1/e31-debate-file-parsing/t23-in-round-markers.yaml`](../../plan_specs/v1/e31-debate-file-parsing/t23-in-round-markers.yaml) |
| Epic / release | `v1-e31-debate-file-parsing` / `v1.1` |
| Branch | `task/v1-e31-t23-in-round-markers` |
| Session status | IN PROGRESS: counts recorded, waiting on the PM's ruling <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

Step 1 of the PM's flow is done. `scripts/count_in_round_markers.py` (logic in
`debate_core.evidence.in_round_markers`) counts marker-shaped lines by form id, reading and place,
the lines read as nothing between body paragraphs by the same form ids, and the clusters each set of
marker forms splits today. The operator ran it on 2026-11-02 (661 s, 13,518 sources, 287,545 cards),
and the counts are in
[docs/data/caselist-parse-report.md](../data/caselist-parse-report.md#in-round-markers-and-the-short-lines-between-body-paragraphs-v1-e31-t23).
A marker is read three ways today: as body, as nothing, and as a cite (`Marked 10:42` is taken for a
name and a two-digit year, which divides its card). The proposal has gone to the PM; no parser or
fingerprint rule has changed yet.

## Plan nodes

<!-- One row per Plan graph node, in the order they were completed. -->

| Node | Status | Notes |
|---|---|---|
| `markers`: In-round markers | IN PROGRESS | Counts done and recorded; ruling pending |

## Acceptance criteria

<!-- Goal criteria (ac1…) and every node criterion. Status: PASS / FAIL / NOT RUN. -->

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: operator-run counts of marker lines by form and position per caselist, and the clusters they split | PASS | `uv run python scripts/count_in_round_markers.py` (operator, 2026-11-02, 661 s) → recorded in the parse report's `v1-e31-t23` section |
| ac2: the PM's ruling written into the spec and built with fixtures shown failing first | NOT RUN | Waiting on the ruling |
| ac3: version bump and before/after re-parse counts if parser or fingerprint changes | NOT RUN | Depends on the ruling |
| ac4: the ruling on short plain lines, built, and evidence precision does not fall | NOT RUN | M3's part measured: the operator's `uv run pytest tests/evals/parser -m "eval and slow"` → `1 passed in 4.16s`; `run_parser_eval.py --tier both` on `docx-8` and again with M3 switched off (a scratch runner) → both gates PASSED, and the two reports' groups, files and targets differ in nothing: EVIDENCE precision 0.9708 (930 right, 28 wrong) on the full tier and 0.9433 on the PR subset, both ways. The short-lines ruling waits on the coach's sample |

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

# Session report: v1-e32-t06-ld-de-extinction-taxonomy

| | |
|---|---|
| Task | `v1-e32-t06-ld-de-extinction-taxonomy` — LD de-extinction position taxonomy |
| Spec | [`plan_specs/v1/e32-argument-landscape/t06-ld-de-extinction-taxonomy.yaml`](../../plan_specs/v1/e32-argument-landscape/t06-ld-de-extinction-taxonomy.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t06-ld-de-extinction-taxonomy` |
| Session status | IN PROGRESS <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Counts taken before any rule (2026-11-05)

Counts only, read-only over v1-e40-t17's restored copy of hsld26 (restored 2026-11-05, 19 manifests,
7,030 sources fetched of 7,030 named, 0 suppressed, parsed store `2026.10.27-docx-7` restored with
7,141 objects, so the parse had nothing to do). The copy is the state of the operator's hand run
`20261105T034547Z` (2026-11-05 03:45 to 05:12 UTC, `completed`), which imported **hsld26
2026-11-03**: the snapshot this report means by "the 2026-11-03 snapshot (the run of 2026-11-04)".
The scheduled run of 2026-11-04 failed to launch on an AWS-side error. The script is a session
scratch file, not committed; each run took 2 to 7 s.

* **What a stored disclosure carries to decide by.** Its snapshot date (a weekly Tuesday), the
  tournament as the filename spells it, and a round label. 9,700 live hsld26 disclosures in 18
  snapshots: 9,700 with tournament text, 9,700 with a round (9,494 read as a known round). No stored
  field holds a tournament date or a round date (`caselist_disclosures`, `caselist_sources`,
  `caselist_snapshots`, the manifests), so a per-tournament rule can only match the tournament text,
  with the snapshot.
* **Florida Blue Key in the 2026-11-03 snapshot** (902 live disclosures, 810 sources). The tournament
  text, lower-cased with everything but letters and digits removed, holding `bluekey` or `fbk`
  (12 spellings): **292 disclosures, 257 sources, 27 schools**. The four spellings two or more schools
  wrote for the tournament itself: 243 disclosures, 214 sources. The round robin's spelling: 11
  disclosures, 9 sources, 2 schools. No disclosure in any earlier snapshot holds `bluekey` or `fbk`.
* **Topic words as a check on the rule**, by source, in cards' tags and headings (`de-extinct` against
  `space col`/`coloniz`): Florida Blue Key's 257 sources: 184 de-extinction only, 4 both, 2 space only,
  66 neither, 1 not parsed. The snapshot's other 554 sources: 2 de-extinction only, 490 space only,
  55 neither, 7 not parsed.
* **Disclosures in snapshots from 2026-11-10 naming a tournament from before 2026-11-06: NOT RUN.** No
  such snapshot exists on 2026-11-05. The nearest measure is a ceiling, not the count: in the 2026-11-03
  snapshot, 246 of 902 disclosures name a tournament spelling first seen two or more snapshots earlier,
  which counts real late disclosures and spellings that recur (two tournaments, one word) alike.
* **Disclosures naming no tournament:** 0 in the 2026-11-03 snapshot (the path parser gives every
  disclosure some tournament text).

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

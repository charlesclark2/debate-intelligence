# Session report: v1-e39-t17-landscape-pages

| | |
|---|---|
| Task | `v1-e39-t17-landscape-pages` — The landscape report and its school view on the pilot, for signed-in team members |
| Spec | [`plan_specs/v1/e39-evidence-search-pilot/t17-landscape-pages.yaml`](../../plan_specs/v1/e39-evidence-search-pilot/t17-landscape-pages.yaml) |
| Epic / release | `v1-e39-evidence-search-pilot` / `v1.7` |
| Branch | `task/v1-e39-t17-landscape-pages` |
| Session status | IN PROGRESS <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

<!-- 3-6 sentences: what was built, how it fits the epic, anything the PM should look at first. -->

## Counts before building (ac1)

Measured 2026-10-25, read-only, from the operator's local copy of the newest hspolicy26 bundle,
`~/.debate-research/dev/reports/landscape/hspolicy26/2026-10-20/` (the PM named it; the bucket copy
was not read, since every AWS call is the operator's). Rendered with markdown-it-py 4.2.0 as the
pages will render it: `MarkdownIt("commonmark", {"html": False}).enable("table")`. Gzip at level 6.
Two scratch scripts, under one second each, no network.

This report.md predates `v1-e32-t20`: it has one `#` heading and no contents list. `t20` adds the
three `#` parts (Affirmative, Negative, Neither side) and a `## Contents` list of about 1 KB (from
the golden fixture's diff), and moves sections but adds none, so the sizes below hold within about
1 KB. The hspolicy26 report was not re-rendered in the `t20` shape.

**The line.** ADR-0019 (b) 1: one HTML page under 150 KB. `v1-e39-t06` measures it as the page's
uncompressed bytes plus `app.js` (12,828 B) and `app.css` (10,090 B), against 150 × 1024 = 153,600 B
(`PAGE_BUDGET` in `packages/debate_api/tests/test_search_pages.py`). That leaves about 128 KB for a
page's HTML, the base template's chrome (about 2 KB) included.

| File | Markdown | Rendered HTML | Gzipped HTML | Headings `#` / `##` / `###` / `####` | Tables | Table data rows | Links out |
|---|---|---|---|---|---|---|---|
| report.md | 41,881 B | 66,015 B | 12,571 B | 1 / 11 / 18 / 10 | 70 | 329 | 0 |
| schools.md | 330,863 B | 568,067 B | 41,400 B | 1 / 2 / 164 / 97 | 253 | 4,226 | 2,109 |

report.md as one page: 66,015 B of HTML plus the two assets is about 89 KB, about 91 KB with the
chrome and 94 KB with a contents list: about 61% of the line. Its largest `##` section, Negative
positions, renders to 18,341 B; by `t20`'s parts, Affirmative is about 24 KB, Negative about 29 KB,
Neither side about 9 KB.

schools.md as one page is 3.7 times the line uncompressed, though 41 KB gzipped. Neither of its two
`##` sections fits on its own:

| schools.md piece | Count | Rendered HTML |
|---|---|---|
| Header and metadata table | 1 | 1,221 B |
| `## By school` | 1 | 205,546 B |
| One school under By school (`###`) | 155 | median 761 B, largest 10,082 B (117 rows) |
| `## By position` | 1 | 361,300 B |
| One kind under By position (`###`) | 9 | largest 135,124 B (Affirmative side: Advantages, 810 rows), next 80,733 B (Disadvantages) |
| One position under By position (`####`) | 97 | largest 34,302 B |

Every school's 2,109 rows appear twice, once by school and once by position. All 475 team codes
have a team-page link (the view's own count), and every link is on a By position row. Rendering
takes 17 ms for report.md and 203 ms for schools.md on the operator's Mac.

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

# Session report: v1-e37-t10-coach-edits-need-no-test-edit

| | |
|---|---|
| Task | `v1-e37-t10-coach-edits-need-no-test-edit` — A coach's schedule or results edit passes the site's tests without editing a test |
| Spec | [`plan_specs/v1/e37-calendar-and-announcements/t10-coach-edits-need-no-test-edit.yaml`](../../plan_specs/v1/e37-calendar-and-announcements/t10-coach-edits-need-no-test-edit.yaml) |
| Epic / release | `v1-e37-calendar-and-announcements` / `v1.6` |
| Branch | `task/v1-e37-t10-coach-edits-need-no-test-edit` |
| Session status | IN PROGRESS <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

<!-- 3-6 sentences: what was built, how it fits the epic, anything the PM should look at first. -->

## Counts first: the site tests that pin the shipped schedule and results (ac1)

Taken at `b4bcbbb` (dev at `fb1009e` plus the start commit), before any test changed. A test is
counted when it reads `site/content/tournaments.yaml` or `site/content/results.yaml` for an exact
entry, count or order: an id, name, date, field value, position ("entry 6"), a number of entries,
the order of entries, the `revised` date, an id it relies on being absent, or a fixture edit that
needs a particular shipped entry to exist (`editEntry('blake-2026', ...)`, a results fixture's
`scheduleId: west-bend-2026`). A test that holds for any valid content (unique UIDs, CRLF line
endings, no WCAG violation, no address in the copy) is not counted. Each `it.each` case is one
test, as vitest counts them.

The count is by reading every test in the files that load either file. Three probe edits,
uncommitted and reverted, cross-check it:

* **Coach's edit**: the PM's edit of 2026-10-30 (Ronald Reagan off the schedule, its two results
  moved to `tournament`/`date`, `revised: 2026-10-30` in both files).
* **Add**: a tournament (`marquette-2027`, 2027-02-06) and a team-level result at
  `west-bend-online-2026` added, `revised` updated.
* **End of season**: only `nsda-nationals-2027` left on the schedule and `results: []`, the shape
  the files reach in June. (An empty schedule is not a valid edit: the schema needs one tournament.)

| File | Tests in file | Pin the shipped content | Failed: coach's edit | Failed: add | Failed: end of season |
|---|---|---|---|---|---|
| `site/tests/tournaments.test.ts` | 63 | 34 | 24 | 4 | 32 |
| `site/tests/icalendar.test.ts` | 33 | 21 | 3 | 2 | 33 (file fails to load) |
| `site/tests/results.test.tsx` | 70 | 20 | 1 | 3 | 70 (file fails to load) |
| `site/tests/schedule.test.tsx` | 34 | 17 | 5 | 4 | 16 |
| `site/tests/layout-guard.test.ts` | 9 | 1 | 1 | 0 | 1 |
| `site/tests/content-policy.test.ts` | 63 | 1 | 1 | 0 | 1 |
| `site/tests/export/schedule.export-test.ts` | 8 | 1 | 0 | not run | 1 |
| Every other site test file (19 unit, 11 export) | | 0 | 0 | 0 | 0 |
| **Total** | | **95** | **35** | **13** | |

The coach's-edit column reproduces the PM's trial exactly: 35 of 921 failed, in the same six
files. The export checks were not run in that trial; run on the same edit
(`SITE_ENV=prod SITE_URL=https://wfbdebate.com site/scripts/export-checks.sh`), all 109 passed.
They compute from the content, with one exception that the coach's edit does not reach: the
schedule's overlap check asserts the shipped schedule has at least one overlap, so it fails once
the last same-day pair (the January 9 qualifiers) is in the past.

What each counted test pins, by file:

* **`tournaments.test.ts` (34).** "The seed data": 9 of its 10 tests (every entry against a
  hand-copied list of 16, the season label `2026-27`, the two nationals by name, how three ids are
  held, Glenbrooks's one arrangement, the byEvent split built from Glenbrooks, overnight for four
  ids, the tentative and conditional ids, the order of all 16). The build-date test (14 season
  entries). Overlaps: 3 (the two hand-counted pairs, `overlaps.size` equal to 16, two ids with no
  overlap). Invalid entries: all 14 (each edits a shipped entry and expects its position, such as
  `"blake-2026" (entry 9)`). Publishing policy: all 6 (the same). The acronym test (needs a shipped
  tournament named "NSDA"). Not counted: "names no student", unique UIDs, the date and overlap
  arithmetic, the schedule.yaml labels.
* **`icalendar.test.ts` (21).** 16 events, 7 hand-copied date ranges, the month-boundary edit to
  Blake, the 3 UID-identity edits, the folded condition of the home tournament, the round trip
  through Blake's notes, all 6 "what a parent sees" tests, 16 DTSTAMPs of `20261022`. The whole
  calendar is built from the shipped file at module level, so with no Glenbrooks or West Bend the
  file fails to load and all 33 fail.
* **`results.test.tsx` (20).** The season fixture names two shipped schedule ids
  (`west-bend-2026`, `badgerland-2026`), so the 14 tests rendered from it pin those entries' names
  and dates (5 loader tests, 5 page tests, 4 home-band tests). A schedule id with a name, using
  `west-bend-2026`; the off-schedule test asserting "Neenah" is not on the shipped schedule; the
  unknown-id test relying on `fort-atkinson-2026` being absent. "The results this site ships": 3 of
  its 4 tests (the two tournaments in order with their schedule id, Fort Atkinson's two placings,
  Ronald Reagan's two). The fixture is loaded at module level, so with no West Bend the file fails
  to load.
* **`schedule.test.tsx` (17).** The order of 14 season ids, the two nationals ids, 14 list items,
  16 entries with Ronald Reagan's date, Blake's facts, West Bend's sign-up row, the two online ids,
  Glenbrooks, the split built from Glenbrooks, the home tournament's condition, the tentative
  qualifier, the 4 overlap pairs and "exactly those four", and "last updated Thursday, October 22,
  2026".
* **`layout-guard.test.ts` (1)** and **`content-policy.test.ts` (1).** Each expects
  `tournament "glenbrooks-2026" (entry 6), field notes` among the guarded fields (layout-guard
  also `"whitefish-bay-home-2026" (entry 7)` and at least 16 entries).
* **`export/schedule.export-test.ts` (1).** "Lists every tournament on the page": the overlap
  markers are computed from the content, but `expect(overlapping.length).toBeGreaterThan(0)`
  pins that one exists, and `html.match(...)` gives `null`, not `[]`, when none does.

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

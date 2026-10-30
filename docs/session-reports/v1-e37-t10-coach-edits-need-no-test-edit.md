# Session report: v1-e37-t10-coach-edits-need-no-test-edit

| | |
|---|---|
| Task | `v1-e37-t10-coach-edits-need-no-test-edit` — A coach's schedule or results edit passes the site's tests without editing a test |
| Spec | [`plan_specs/v1/e37-calendar-and-announcements/t10-coach-edits-need-no-test-edit.yaml`](../../plan_specs/v1/e37-calendar-and-announcements/t10-coach-edits-need-no-test-edit.yaml) |
| Epic / release | `v1-e37-calendar-and-announcements` / `v1.6` |
| Branch | `task/v1-e37-t10-coach-edits-need-no-test-edit` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The site's tests no longer read the shipped schedule or results for an entry, a count or an
order. Behaviour tests run on a synthetic season of their own (`site/tests/fixtures/season/`:
twelve invented tournaments, five results, invented students), and a new suite,
`site/tests/shipped-content.test.ts`, checks the shipped files only for what must always hold
(schema, one season, unique ids, dates inside the season, publishing policy, consent). Each of
those checks is shown refusing a break planted in a copy of the shipped files. ac1 counted 95
tests that pinned the shipped content, in seven files. The coach's edit of 2026-10-30 is commit
`0b09eb3`, which changes only `site/content/tournaments.yaml` and `site/content/results.yaml`;
after it eslint, tsc, vitest (935/935) and the prod export checks (109/109) pass. A scratch edit
adding a tournament and a result passes the same way, and so does the end-of-season shape of
the files, which broke 50 tests and two whole files before. The coach's guide now says a content
edit needs no test edit, and that a test failing after one is a bug to report. Look first at
the two guards I carried over unchanged that refuse things the build accepts (Follow-up work).

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
| `content-independent-tests` (Content-independent site tests) | Done | Counts first (`778e5d1`), tests on the synthetic season and the shipped-content checks (`eb7004e`), the coach's edit alone (`0b09eb3`), the guide (`d555fea`). Hashes after the sync onto dev at `f86de80`. |

## Acceptance criteria

<!-- Goal criteria (ac1…) and every node criterion. Status: PASS / FAIL / NOT RUN. -->

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: counts first, by file, of every site test reading the shipped tournaments.yaml or results.yaml for exact entries, count or order, before any test changes | PASS | [Counts first](#counts-first-the-site-tests-that-pin-the-shipped-schedule-and-results-ac1), committed as `778e5d1`, before the test commit `eb7004e`: 95 tests in 7 files, by reading, cross-checked by three probe edits run with `pnpm --dir site exec vitest run --reporter=json` (35, 13 and 50 failures plus 2 files failing to load) and the export checks (0, not run, 1). |
| ac2: the coach's edit is one commit that changes no test file; eslint, tsc, vitest and the prod export checks pass after it; a second scratch edit adding a tournament and a result also passes unchanged tests | PASS | `git show --stat 0b09eb3` → `site/content/results.yaml`, `site/content/tournaments.yaml` only; `git diff --name-only HEAD~1 HEAD \| grep -c '^site/tests/'` at that commit → `0`. At it: `pnpm --dir site lint && pnpm --dir site typecheck && pnpm --dir site test` → exit 0, eslint and tsc silent, `Test Files 27 passed (27)`, `Tests 935 passed (935)`; `SITE_ENV=prod SITE_URL=https://wfbdebate.com site/scripts/export-checks.sh` → exit 0, `Test Files 12 passed (12)`, `Tests 109 passed (109)`. Scratch edit on top, uncommitted and reverted (`marquette-2027` added on 2027-02-06, a team-level quarterfinalist at `west-bend-online-2026` added, `revised: 2026-10-31` in both): the same four commands → exit 0, 935/935 and 109/109. The diff is under [Decisions](#decisions-and-assumptions). |
| ac3: an invalid entry, a policy breach and an unconsented name planted in a copy of the shipped content each fail; new tests shown failing first; the guide says a content edit needs no test edit | PASS | `pnpm --dir site exec vitest run tests/shipped-content.test.ts` with every check written as a no-op → `Tests 9 failed \| 7 passed (16)`, every failure `expected [Function] to throw an error`; with the checks → `Tests 16 passed (16)`. Planted in `shippedContentWith(...)` copies: a misspelt tournament field and a record as a placing (schema), a results file for the next season (one season), two tournaments with one id (unique ids), a tournament in the season before and a result in the season after (season dates), a phone number in a tournament's notes and an email address in a result's tournament (publishing policy), a result naming a student with no consent entry (consent). Each is refused by its own check. Guide: `docs/guides/coach-website-editing.md`, "Check a change" and a row in "When something goes wrong". |
| Node `content-independent-tests`: Site tests pass (`pnpm --dir site test`) | PASS | `pnpm --dir site test` → `Test Files 27 passed (27)`, `Tests 935 passed (935)` (at `0b09eb3`, and again at the head after the sync, below). |
| Mutants (the PM's list, agreement 8) | PASS | Each applied in the working tree, its covering files run, then restored with `git checkout --`: (1) `contentWith` copying no fixture season, so every behaviour test reads the shipped files → 47 assertion failures in tournaments and schedule tests (icalendar, results and layout-guard also fail to load, which agreement 8 does not count as catches); (1, narrow) the schedule page rendered without the fixture root → 15 of 34 fail; (2) the schema check emptied → its 2 planted cases fail; (3) the consent check emptied → its planted case fails; (4) the loader's duplicate-id refusal disabled (`src/lib/tournaments.ts`) → "a second entry with an id already in use" fails; (4, test side) the unique-ids check emptied → its planted case fails. Also each other shipped-content check emptied: season dates → 2 fail, publishing policy → 2 fail, one season → 1 fails. vitest has no Hypothesis database, so agreement 8's fresh-database rule has nothing to apply to. |
| Affected set, after the sync (agreement 10) | PASS | `uv run scripts/affected_tests.py --run` → `35 of 571 test files (6.1%) chosen ... from 18 changed files`, `1856 passed in 162.68s`, `Affected set: 35 test files, pytest exited 0 after 167 s`. It also printed `site/ changed: the site's own pnpm checks test it; pytest does not.` The 35 are the always-run list and the docs and script tests that `docs/guides/` reaches. It ran past the two-minute line (167 s, with the machine's load average about 16 from other sessions); it had already finished when I saw that, so it is recorded here and not handed over. Site checks at the head after the sync: `pnpm --dir site lint && pnpm --dir site typecheck && pnpm --dir site test` → 935/935. |
| Whole-repo checks | PASS | `uv run --frozen ruff format --check` → `1601 files already formatted`; `uv run --frozen ruff check` → `All checks passed!`; `uv run --frozen pyright packages` → `0 errors, 0 warnings, 0 informations` (no Python package changed); `uv run --frozen lint-imports` → `Contracts: 18 kept, 0 broken`; `uv run --frozen python scripts/check_thin_handlers.py` → OK; `uv run --frozen python scripts/check_command_blocks.py` → OK, 576 blocks; `uv run --frozen python scripts/check_links.py` → OK, 2939 links; `uv run --frozen python scripts/docs_index.py --check-descriptions` → all 58 described; `uv run scripts/validate_specs.py` → `OK: 493 files, 40 epics, 431 tasks, 22 releases` (after setting the Goal to Succeeded). |

## Files changed

<!-- Group by package or directory; one line on why each group changed. -->

* **`site/tests/fixtures/season/`** (new): `tournaments.yaml` and `results.yaml`, the synthetic
  season every behaviour test reads. Invented tournaments, deliberately out of date order, with
  one entry for each case the tests need (online at school, byEvent, conditional, tentative, two
  overlapping pairs, two nationals). The results' students are invented.
* **`site/tests/content-fixture.ts`** (new): `contentWith` copies `site/content/`, swaps in the
  synthetic season, sets the consent manifest's season and students to the fixture's, and adds the
  fixture's tournament names to `permittedNamePhrases`. `shippedContentWith` copies the shipped
  content as it is, for planted breaks only. `STUDENTS`, `withConsent` and `replaceOnce` moved here
  from the two older fixture modules.
* **`site/tests/shipped-content.test.ts`** (new): the six checks on the shipped files, each run on
  `content/` and on a planted copy, plus the schedule's no-`@`-no-phone check moved from
  `tournaments.test.ts`.
* **`site/tests/tournaments.test.ts`, `schedule.test.tsx`, `icalendar.test.ts`,
  `results.test.tsx`, `results-fixture.ts`, `schedule-fixture.ts`**: the same behaviour tests,
  with expected values written by hand from the synthetic season. "The results this site ships"
  is gone; its season check is now the one-season check. The byEvent tests use the fixture's own
  split entry instead of `splitGlenbrooksByEvent`.
* **`site/tests/layout-guard.test.ts`, `content-policy.test.ts`**: the `glenbrooks-2026 (entry 6)`
  pins become a check, for every shipped tournament, worked out from its own fields. layout-guard
  also builds the layout over the fixture root, where it counts the fields by hand (29 tournament
  fields, the 5 results and the labels).
* **`site/tests/export/schedule.export-test.ts`**: the overlap count accepts none.
* **`site/content/tournaments.yaml`, `site/content/results.yaml`**: the coach's edit of 2026-10-30,
  commit `0b09eb3` alone.
* **`docs/guides/coach-website-editing.md`**: a content edit needs no test edit; a failing test
  after one is a bug to report to Charlie.
* **`plan_specs/.../t10-coach-edits-need-no-test-edit.yaml`**: Goal phase only.
* No dependency manifest or lockfile under `site/` changed (`git diff --stat f86de80 HEAD --
  site/package.json site/pnpm-lock.yaml` is empty). The dependencies were installed into the
  worktree with `pnpm --dir site install --frozen-lockfile --offline`, which writes neither.

## Deviations from the spec

* **Started on the PM's `--force`.** The PM's note of 2026-10-30: this task depends on
  `v1-e37-t06-season-results`, which is `InProgress` (`uv run scripts/validate_specs.py
  --require-succeeded v1-e37-t06-season-results` → `InProgress`). Its only open criterion is ac5's
  prod half, its first result on the public site, which the site lane's first use completes
  tonight; its code has been on dev since 2026-10-23. `v1-e37-t02-events-calendar` is `Succeeded`.
* **One comment beyond the PM's edit, in the coach's commit.** `# Ronald Reagan, from Charlie on
  2026-10-27.` gained `Off the schedule since 2026-10-30.`, as the Fort Atkinson results' comment
  reads. A comment only; the entries are exactly the PM's edit.
* **Two guards beyond the PM's list stay, unchanged.** The list was schema, publishing policy and
  consent, unique ids, dates in the season. Two existing tests on the shipped files checked more,
  and since no guard may be weakened, both are kept as they were, moved to
  `shipped-content.test.ts`: the three files are for one season (from "the results this site
  ships"), and the schedule's text holds no `@` and no phone number (from `tournaments.test.ts`).
  Both refuse something the build accepts. See Follow-up work.
* **`scripts/task sync` was run once**, as the PM asked: dev had the lane's back-merge (#605) and
  three more merges, with no difference under `site/` or `docs/guides/`. The branch is not on the
  remote, so the sync rebased and pushed nothing. The `site/` and `docs/guides/` trees are
  byte-identical before and after (`git diff a61906a d555fea -- site docs/guides` is empty).

## Decisions and assumptions

<!-- Choices the spec left open, with the reasoning. -->

* **A fixture overlay, not a whole fixture site.** `contentWith` still copies `site/content/` and
  replaces only the season's two files and the consent manifest's season and students. The pages,
  events and schedule labels stay the shipped copy, because the tests render the real frame and
  the guard reads every page. Those files are not the coach's weekly edit, and tests read them
  only for their own words (labels, titles), never for an entry. The results fixture carries its
  own copy of the labels, so its em-dash and acronym cases edit a file the coach never touches.
* **Invented tournament names everywhere except the two nationals.** "NCFL Nationals" and "NSDA
  Nationals" are the organisations' national tournaments, which the shipped `schedule.yaml` names
  in its nationals intro. The acronym test needs a tournament name using "NSDA". Places are real
  towns; no person is named. The planted policy cases in `tournaments.test.ts` now plant names that
  have no consent entry at all (Taylor Brooks, Quinn Harlow, Rowan Ellis). The fixture's students
  have consent, so a planted Jordan Rivera would pass the guard, as a consented name does.
* **One check per guarantee, each needed.** The schema check calls the loaders, and the other five
  read the files as typed, through `readYaml`, so each check stands without the loaders' own. That
  is why mutants (2) to (4) are each caught by one planted case and not masked by another check,
  and why the loader's duplicate-id refusal and the test's own check are separate mutants.
* **The shipped-content checks refuse nothing the build accepts that they didn't refuse before.**
  The one-season check, and the no-`@` and no-phone check, are the two exceptions, and both are
  carried over unchanged (Deviations).
* **The plants are added beside whatever the shipped files hold** (`appendTo`, dated from the
  shipped file's own season), so ac3's cases run the same in June, at a season change or on an
  empty results list. A plant that cannot find the list's end fails loudly; it never tests the
  unedited copy.
* **The scratch edit for ac2**, run on top of `0b09eb3` and reverted:

  ```diff
  -revised: 2026-10-30
  +revised: 2026-10-31
  +
  +  - id: marquette-2027
  +    name: Marquette University High School
  +    start: 2027-02-06
  +    events: [policy, lincoln-douglas, public-forum]
  +    held: in-person
  +    where: Milwaukee, Wisconsin
  +    overnight: no
  +    status: confirmed
  +    notes: Bus leaves the high school at 6:30 AM.
  ```

  and in `results.yaml`, `revised: 2026-10-31` and:

  ```diff
  +
  +  - scheduleId: west-bend-online-2026
  +    event: public-forum
  +    division: novice
  +    placing: quarterfinalist
  ```

* **The end-of-season probe was run again on the new suite**, before the coach's commit: only
  `nsda-nationals-2027` on the schedule, `results: []` → 0 of 935 failed, export checks 109/109.

## Operator follow-ups

<!-- Commands the operator must run (anything over ~2 minutes), with where to run them, the exact
command, expected runtime and what success looks like. Also GitHub/AWS settings to change. -->

None.

## Follow-up work

<!-- Bugs, gaps or ideas outside this task's scope, each with the task or epic it belongs to.
The PM decides whether they become spec changes or new tasks. -->

* **Two kept guards refuse an edit the build accepts (v1-e37, the PM's ruling).** (a) The
  schedule's no-`@` check refuses the allowlisted coach address in a tournament's notes, which the
  build lets through and `tournaments.test.ts` asserts it lets through. A coach who writes "Questions
  to charles.clark@wfbschools.com" in a note would pass the build and fail this test. (b) The
  one-season check refuses a schedule moved to `2027-28` before the results and consent files are,
  which the build accepts. The guide's start-of-season steps for the schedule do not say to change
  all three together. Either the guide gains that sentence, or the check is ruled out. I left both
  alone because the forbidden list says no guard on the shipped files may be weakened.
* **One media-consent pin remains, outside this task's two files.** `content-policy.test.ts`, "has a
  media-consent manifest for the current season, with no photograph in it yet", expects
  `images: []`. The first consented photograph will fail it, which is a content edit (Charlie's, after
  a consent check) that needs a test edit. A candidate for the same treatment if photos are planned.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

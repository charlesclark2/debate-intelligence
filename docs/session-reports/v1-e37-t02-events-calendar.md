# Session report: v1-e37-t02-events-calendar

| | |
|---|---|
| Task | `v1-e37-t02-events-calendar` — Events and tournaments calendar |
| Spec | [`plan_specs/v1/e37-calendar-and-announcements/t02-events-calendar.yaml`](../../plan_specs/v1/e37-calendar-and-announcements/t02-events-calendar.yaml) |
| Epic / release | `v1-e37-calendar-and-announcements` / `v1.6` |
| Branch | `task/v1-e37-t02-events-calendar` |
| Session status | COMPLETE |

## Summary

The season's tournaments are now one validated file, `site/content/tournaments.yaml`, seeded with
all 20 entries in `docs/data/2026-27-tournament-schedule.md`. Two things are built from it: a
`/schedule/` page and a `/schedule.ics` calendar file. `/schedule/` shows the whole season in date
order, with nationals in their own section. `/schedule.ics` is generated at build time by a static
route handler. Overlaps are computed from the dates, and **there are four, not the three the brief
listed**: the two January 9 qualifiers share a day. Both entries of each pair are marked on the page
and in the calendar. Each entry has an explicit id, and its iCalendar UID is derived from that id
alone. Tournament text goes through the existing publishing-policy checker and fails the build in
every environment, naming the entry and the field. The coach guide's events section is rewritten,
and Schedule is in the navigation after Events. As authorised, the home page's October 1 panel is
replaced by a pointer to the schedule; the exact removed text is under Decisions. **Look first at
the Deviations**: I edited the smoke check outside this task's packages, because removing the panel
would otherwise have failed `validate-dev`.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `data`: Tournament schema and seed data | Done | `src/lib/tournaments.ts`, `content/tournaments.yaml`, `content/schedule.yaml`, `content/pages/schedule.md`; 16 tournament and place phrases added to `permittedNamePhrases` |
| `page`: The schedule page | Done | `src/app/schedule/page.tsx`, styles in `sections.css`, navigation entry, home panel replaced |
| `ical`: The iCalendar file and subscribe links | Done | `src/lib/icalendar.ts`, `src/app/schedule.ics/route.ts`; round trip through `ical.js` (devDependency) |
| `guide`: Rewrite the events section of the coach guide | Done | `docs/guides/coach-website-editing.md` |

## Acceptance criteria

All commands run from the worktree root on 2026-10-01, with no network access needed. `pnpm`
commands run against the lockfile install.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1**: `tournaments.yaml` validated by a schema at build time, holds every entry in the schedule doc; an invalid entry fails naming entry and field; the policy validator rejects an email, a phone number or a non-allowlisted name in any text field | PASS | `pnpm --dir site exec vitest run tests/tournaments.test.ts` → 62 passed. The seed is compared with a **hand-written** copy of all 20 rows of the doc. 14 kinds of invalid entry each fail with `tournament "<id>" (entry N), field <field>: ...`. Five policy cases (an email in notes, a phone number in where, a student name in notes, condition and name) fail **with `SITE_ENV=dev`**, e.g. `content/tournaments.yaml, tournament "blake-2026" (entry 13), field notes: publishes the email address "jordan.parent@example.com"` |
| **ac2**: `pnpm --dir site build` produces /schedule: whole season in date order, nationals separately; dates, name, where, how held, events, overnight, status, sign-up-by where set; overlaps visibly marked; reachable from the navigation | PASS | `pnpm --dir site build` → `○ /schedule`, `○ /schedule.ics` (6 s). `tests/schedule.test.tsx` → 37 passed: the order matches a hand-written list, the two nationals sit in `#nationals`, the facts on MinneApple, Glenbrooks' two arrangements, the condition shown in full, the eight entries in overlapping pairs each with a "Same dates as" link to the other (and no others marked), sign-up-by present when set and absent when not. Navigation: `tests/navigation.test.tsx` and `tests/export/navigation.export-test.ts` |
| **ac3**: the build publishes an iCalendar file, one event per entry; a test parses it back and checks all-day and multi-day dates (exclusive ends) and that a UID is unchanged when notes are edited; the page offers webcal:// and https links | PASS | `pnpm --dir site exec vitest run tests/icalendar.test.ts` → 34 passed, parsed with `ical.js` 2.2.1. It checks 20 events, all `VALUE=DATE`, and exclusive ends hand-computed for 9 entries (e.g. Iowa Caucus 2026-10-23 → 2026-10-26), including across a year boundary. UIDs are unchanged when notes are edited, added or removed and when a date is corrected. It also checks CRLF only, no line over 75 octets, and that commas, semicolons, backslashes, newlines and 2-, 3- and 4-byte characters round-trip through a fold. The links are checked in `tests/schedule.test.tsx` (`webcal://…/schedule.ics` and `https://…/schedule.ics`) and, in the export, by `tests/export/schedule.export-test.ts` |
| **ac4**: the guide explains add, change and remove, the two publish paths under ADR-0015 point 4, and what may never be written; no longer describes Google Calendar | PASS | `docs/guides/coach-website-editing.md`, section "Events: the tournament schedule file". `grep -n "Google Calendar" docs/guides/coach-website-editing.md` → one line, the sentence saying there is none. `uv run scripts/check_links.py` → `OK: 1182 relative links and anchors in 161 Markdown files` |
| **ac5**: lint, typecheck, test and build pass offline; the export's accessibility checks cover /schedule | PASS | `site/scripts/pre-commit-checks.sh` (CI's entry point) → exit 0 in 15 s: lint clean, typecheck clean, `Test Files 24 passed, Tests 815 passed`, build, then the export checks `Test Files 11 passed, Tests 92 passed`, including `every built page in site/out/ > schedule has no WCAG 2.1 AA violation`. Prod mode: `SITE_ENV=prod SITE_URL=https://wfbdebate.com site/scripts/export-checks.sh` → 92 passed. That the axe pass really covers /schedule is shown by a mutation below |
| Node `data`: `site/content/tournaments.yaml` exists containing "Wisconsin State Debate Tournament" | PASS | `grep -c "Wisconsin State Debate Tournament" site/content/tournaments.yaml` → 1 |
| Node `page`: `pnpm --dir site build` | PASS | As ac2 |
| Node `ical`: `pnpm --dir site test` | PASS | 815 passed |
| Node `guide`: `docs/guides/coach-website-editing.md` contains "tournaments.yaml" | PASS | `grep -c "tournaments.yaml" docs/guides/coach-website-editing.md` → 3 |
| Spec validation | PASS | `uv run scripts/validate_specs.py` → `OK: 302 files, 38 epics, 244 tasks, 20 releases`; `--require-succeeded v1-e37-t02-events-calendar` → `Succeeded` |
| Smoke-check tests (outside packages, see Deviations) | PASS | `uv run pytest -q tests/scripts/test_site_smoke.py` → 37 passed; `uv run ruff check` and `ruff format --check` on both files clean |

### Mutation runs: each check shown red, then restored

A script (`mutate.py`, kept in the session scratchpad) applied each mutant to committed code and
ran the full `pnpm test` (CI's invocation). It restored the file from a saved byte copy, never with
`git checkout`, and asserted byte equality afterwards. There is no Hypothesis in the site suite, so
the empty-database rule in working agreement 8 does not apply; every run was a fresh process.

| # | Mutant | Result |
|---|---|---|
| 0 | overlap: `<=` becomes `<`, so a shared first or last day is missed | **caught**: 12 failed (2 files), e.g. `overlaps > the same single day`, `tournaments on the same dates > marks exactly those eight entries and no others` |
| 1 | overlap: only the earlier entry of a pair is marked | **caught**: 8 failed (3 files), incl. `tells both entries of an overlap about the other` (calendar) |
| 2 | overlap: nothing is ever marked | **caught**: 12 failed (3 files) |
| 3 | UID: derived from the id **and the start date** | **caught**: 19 failed, incl. `calendar identity > does not change when the dates change`, `keeps the UID when the dates are corrected` |
| 4 | UID: a hash of the whole entry | **caught**: 25 failed, incl. `does not change when the notes change` and the ical.js round trip `keeps every UID when notes are edited, added or removed` |
| 5 | policy: the loader never calls the guard | **caught**: 5 failed, every case in `the publishing policy rejects what may never be written in tournament data` |
| 6 | policy: `notes` not offered to the guard | **caught**: 4 failed: the email and name cases in notes, the guarded-files test, and `an em dash` (the em-dash check reads the same field list, so it fails too) |
| 7 | policy: the guard fails only a prod build | **caught**: 5 failed, because the policy tests run with `SITE_ENV=dev` |
| 8 | policy: the layout stops passing the schedule files to the build guard | **survived** at first (815 passed). Fixed by `tests/layout-guard.test.ts`, which calls `RootLayout` and reads the guard's argument. Rerun: **caught**, 2 failed |
| 9 | policy, **existing wiring**: the layout stops passing `loadGuardedContent()` | **caught** by the new test: 6 failed. Before this task, nothing in the suite would have noticed (no test called the layout) |
| export | an overlap link in `/schedule/` rendered with no text | `site/scripts/export-checks.sh` → **caught**: `every built page in site/out/ > schedule has no WCAG 2.1 AA violation` with `link-name (serious)` on `a[href="#last-chance-qualifier-2027"]`. Restored with `cmp`, then 92 passed |
| smoke | `check_calendar` returns pass without fetching | `uv run pytest tests/scripts/test_site_smoke.py` → **caught**: 4 failed. Restored, 37 passed |

After every mutant: `restored tree exit 0: Test Files 24 passed | Tests 815 passed`, `git status clean: True`.

Two more instances of "a check earns trust by failing" came up without a deliberate mutant:

- **The export pass caught what the source guard cannot see.** The page title "Tournament
  Schedule" is title case, which the guard reads as a possible name. The source guard never reads
  page titles, so a prod build passed while `content-policy.export-test.ts` failed on `/schedule/`.
  It is now a reviewed phrase, beside "Debate Events Offered".
- **A dev build prints policy findings instead of failing on them.** My first dev build passed while
  `content/schedule.yaml` named "Google Calendar", "Apple's Calendar" and "Outlook". The source
  test of the shipped content then failed. These are product names, now reviewed.

## Files changed

- **`site/content/`**: `tournaments.yaml` (new, the data) and `schedule.yaml` (new, the page's
  labels, headings, subscribe steps and calendar name). `pages/schedule.md` is new and carries the
  title, the description and the notification rules from the schedule doc. `site.yaml` adds
  Schedule to the navigation. `home.yaml` replaces the panel. `pages/join.md` drops a link to the
  removed panel. `media-consent.yaml` adds the reviewed phrases (tournaments, schools, towns,
  calendar apps, the page heading).
- **`site/src/lib/`**: `tournaments.ts` is new: schema, per-entry errors, overlaps, UID, date
  formatting, the policy hookup and the page/calendar view. `icalendar.ts` is new: RFC 5545
  serialisation. `content.ts` exports three house-style helpers, defines `SCHEDULE_SLUG`, swaps the
  `parentSession` schema for `seasonSchedule`, and `announcementFields()` now returns nothing.
- **`site/src/app/`**: `schedule/page.tsx` and `schedule.ics/route.ts` are new. `page.tsx` renders
  the new panel. `layout.tsx` passes the schedule files to the build guard.
- **`site/src/styles/`**: schedule styles (the warm accent appears only as a border). The dead
  `.parent-session__*` rules are removed. The navigation gap is tightened between 48 and 64 rem.
- **`site/tests/`**: four new suites (`tournaments`, `icalendar`, `schedule`, `layout-guard`), the
  `schedule-fixture.ts` helper and a new export check. The existing suites are updated for the
  panel, the navigation, the routes and the a11y sweep.
- **`site/package.json`, `site/pnpm-lock.yaml`**: `ical.js` 2.2.1 as an exact **devDependency**.
  It is MPL-2.0, has no dependencies, and is never imported by `src/`. There is no new production
  dependency.
- **`docs/guides/`**: the coach guide is rewritten for the file. `parent-email-updates.md`: two
  mentions of "under the parent session" now say "under the tournament-schedule panel".
- **Outside the stated packages** (see Deviations): `scripts/site_smoke.py`,
  `tests/scripts/test_site_smoke.py`, `tests/smoke/test_site.py`, `tests/smoke/README.md`,
  `docs/adr/0015-website-content-editing.md` (one link).

## Deviations from the spec

1. **Four overlapping weekends, not three.** The brief named Oct 23–25/Oct 24, Nov 7/Nov 7–9 and
   Nov 21/Nov 21–23. Computing from the dates also finds the two January 9 qualifiers (Southern
   Wisconsin NSDA Qualifier and Last Chance Qualifier, both in Brookfield). Both are marked, as the
   rule "compute, don't hand-mark" requires. Their notes explain why two qualifiers run that day.
   The tests' expected pairs are hand-written with all four.
2. **Smoke checks edited outside `constraints.packages`.** `scripts/site_smoke.py` checked for
   `id="parent-session"` on the home page. The authorised home change removes that panel, so the
   next `validate-dev` would have failed. The check now looks for `id="season-schedule"`. I also
   added a `calendar file` check: `/schedule.ics` answers 200 as `text/calendar` and starts with
   `BEGIN:VCALENDAR`. It is not in the sitemap, so no page check reaches it. I updated its tests and
   the two smoke docs to match. Working agreement 5 and `plan_specs/README.md` require a task that
   changes a user-facing surface to update its smoke checks; this spec has no node for it. The PM
   may want to add one to the spec.
3. **One link edited in ADR-0015.** The not-adopted Google proposal linked to the guide's
   `#events-the-team-calendar`, which the rewrite removes, so the repository link check failed.
   Re-pointing it at the new section would have made the record describe conventions that section
   does not contain. It now links to the guide as it stood at `2a7ba08`, on GitHub. No reasoning in
   the ADR changed.
4. **Tournament policy findings fail the build in every environment.** ac1 says an invalid entry
   "fails the build", and `pnpm --dir site build` is a dev build by default. The existing guard only
   prints in dev, so that a preview can show unfilled `[[TBD]]` markers for review. Tournament data
   has no placeholders (a `[[TBD]]` in it is rejected; "To be announced" is the answer), so the
   loader throws in any environment. Page copy keeps its existing dev leniency.
5. **`pages/join.md` edited.** It invited parents to "the [parent information session](/) on
   October 1", a link to the panel being removed. The brief did not mention it; the edit removes
   only that clause (quoted under Decisions).
6. **Nationals list all three events.** The schedule doc's nationals table has no events column.
   The schema requires events and ac2 requires them on every entry, so both nationals list Policy,
   Lincoln-Douglas and Public Forum, which both national tournaments offer, with the note "For
   students who qualify." Charlie should confirm.

## Decisions and assumptions

**Exactly what was removed from the home page (Charlie-approved text).** The whole `parentSession`
block in `site/content/home.yaml`, which rendered as the navy panel under the hero:

- eyebrow "For parents"; title "Parent information session";
- intro "Come and hear how a season works: what the events are, what a tournament weekend looks
  like, what it costs, and what the team asks of a family.";
- facts: Date "Thursday, October 1, 2026"; Time "6:00 PM"; Place "Whitefish Bay High School";
  Room "Room 264";
- the four "what to expect" items: "The three events the team competes in, explained in plain
  language." / "What a tournament weekend actually looks like, from Friday to Sunday." / "What a
  season costs, and what help is available." / "What the team asks of a family, and what it does
  not.";
- note "Bring your questions. You do not need to know anything about debate to come, and your
  student does not have to have decided anything yet.";
- the button "Read the questions parents ask" (to `/faq/`).

And from `site/content/pages/join.md`: ", and welcome to come to the [parent information
session](/) on October 1." The sentence now ends "Parents are welcome to email on a student's
behalf."

**New text for Charlie to review** (it is mine, not his):

- **The home panel**: eyebrow "For parents", title "The season's tournaments", intro "Every
  tournament this season in one place: the dates, where each one is, whether your student debates
  in person, from the high school or from home, and whether it is overnight. Add it to your own
  calendar and changes reach you without checking back.", and the button "See the tournament
  schedule". The email signup band directly under it is unchanged.
- **The rest**: the opening of `pages/schedule.md` (the notification rules come from the schedule
  doc), all of `schedule.yaml`, the condition sentence for December 5, and three wording choices.
  The doc's "Our tournament (hosted)" became the entry name "Whitefish Bay home tournament".
  "(varsity)" became the note "Varsity only.". "(coach invitation)" became "By coach invitation.".
  Abbreviations are written out (WFB HS, HS, WI, MN, IL, AZ) for plain language.

**Modelling choices:**

- **Identity.** `id` is required, unique and must end in a four-digit year (so it can never
  collide with the page's section anchors). The UID is `tournament-<id>@wfbdebate.com`. The domain
  is fixed, not read from `SITE_URL`, so the dev preview, prod and any future domain change all
  give the same UIDs.
- **How it is held.** The common case is four flat fields: `events`, `held`, `where`, `overnight`.
  A tournament held differently per event uses `byEvent` instead, a list of groups that each carry
  those four fields. Mixing the two forms, naming an event in two groups, giving a place to an
  online kind, or leaving the place off `in-person` all fail the build. `held` is `in-person`,
  `online-at-school` or `online-from-home`. The page's label for `online-at-school` must name
  Whitefish Bay High School; the schema refuses any other.
- **Status.** `confirmed`, `tentative` or `conditional`. A condition is required with
  `conditional` and refused otherwise. The page prints the condition in full under the badge. In
  the calendar, a non-confirmed entry gets `STATUS:TENTATIVE` **and** a title prefix ("Tentative:",
  "Conditional:"), because Google Calendar ignores `STATUS`.
- **No build-date logic.** No code reads the clock. Two tests move the system date to July 2027
  and confirm the page still lists all 20 entries in the same order.
- **Dates.** The YAML parser silently turns an unquoted `2026-02-30` into March 2, so bare dates
  are quoted before parsing and validated as typed. Dates must fall inside the declared season
  (1 August to 31 July), which catches a year carried over from last season.

**iCalendar:**

- **Why a static route handler** (`src/app/schedule.ics/route.ts`, `force-static`) and not a step
  in the build script:
  - It reads the data through the same loader, in the same process, as the page, so the two can
    never disagree.
  - A rejected schedule fails `next build` itself.
  - `build-export.mjs`, the export fingerprint, the export checks and `site_deploy.sh` all pick the
    file up without a change.
  - A separate Node script would need a TypeScript runner added as a dependency.
- **`DTSTAMP`.** RFC 5545 requires it on every event. A build-time stamp would make every rebuild
  of an unchanged schedule a different file. So it is the `revised:` date at the top of
  `tournaments.yaml`: the day the schedule last changed. The page also shows it as "Schedule last
  updated", which matters because deploys are manual. Two builds are byte-identical (tested). The
  cost: whoever edits the file must update `revised`. The guide says so, and a forgotten update
  makes the date stale, not the data.
- **Other properties.** All-day `VALUE=DATE` with `DTEND` the day after the last day,
  `TRANSP:TRANSPARENT`, `REFRESH-INTERVAL` and `X-PUBLISHED-TTL` of one day, a `URL` back to the
  entry on the page, and a `LOCATION` that is the physical place a student goes (Whitefish Bay High
  School for `online-at-school`).

**Navigation.** Schedule sits straight after Events. A parent who has just read what the events
are asks next when they are, and putting the two side by side keeps them distinct. With seven
items, "Parent FAQ" wrapped onto two lines at 768 px (seen in a headless Chromium screenshot of the
export). The gap between items is tighter from 48 to 64 rem. I checked the screenshots at 768,
1024 and 390 px; the result is one row, with no sideways scroll on a phone.

**`announcementFields()` now returns `[]`.** The October 1 panel was the only announcement with
required facts. The guard, its tests and the layout wiring stay for `v1-e37-t03`. Two tests of the
removed `parentSessionFactSchema` were deleted with the schema.

## Operator follow-ups

Nothing below is needed to merge this task. These are the steps that put it on the live site.
Each block starts with its own `cd`. The sequence follows
[`docs/runbooks/team-website.md`](../runbooks/team-website.md), "Deploying the site" and
"Promotion checklist". The branch reaches `dev` the usual way: PM review, then
`scripts/task pr`, then merge.

**1. Deploy `dev` to the preview** (expected runtime about 4 minutes, most of it the CloudFront
invalidation). Where: a worktree checked out at the head of `dev`. Create one once if you have
none; never switch the main checkout.

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence
git fetch origin
git worktree add --detach ../debate-intelligence-worktrees/dev-preview origin/dev   # once; later: cd there and git checkout --detach origin/dev
cd ../debate-intelligence-worktrees/dev-preview
git log --oneline -1                      # should be the merge of v1-e37-t02
pnpm --dir site install                   # once per worktree
terraform -chdir=infrastructure/envs/dev init -reconfigure   # once per worktree
aws sso login --sso-session debate
scripts/site_deploy.sh dev
```

Success looks like: three `aws s3 sync` passes and `Deployed <sha> to dev: https://dev.wfbdebate.com`.

**2. Check /schedule and the calendar on the preview** (about 2 minutes), in the same worktree:

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/dev-preview
uv run scripts/site_smoke.py --env dev --url https://dev.wfbdebate.com --expect-sha "$(git rev-parse HEAD)"
curl -sS -o /dev/null -w '%{http_code} %{content_type}\n' https://dev.wfbdebate.com/schedule.ics
curl -sS https://dev.wfbdebate.com/schedule.ics | grep -c 'BEGIN:VEVENT'
```

Success looks like:

- the smoke check says `All N checks passed.`, including `season schedule panel` and
  `calendar file: text/calendar, 20 events`;
- the first `curl` prints `200 text/calendar`; the second prints `20`.

If the content type is `binary/octet-stream`, the AWS CLI did not recognise `.ics` (Python's
`mimetypes` maps it to `text/calendar` on this Mac). Stop and tell the PM: the fix is a
content-type flag in `scripts/site_deploy.sh`.

Then by hand:

- Open `https://dev.wfbdebate.com/schedule/` on a phone. Check:
  - Schedule is in the menu;
  - the Iowa Caucus says "Online, debated at Whitefish Bay High School";
  - Glenbrooks shows two lines, one per arrangement;
  - December 5 shows its condition;
  - the four pairs carry "Same dates as".
- Press **Subscribe in your calendar app** on an iPhone or Mac. Apple Calendar should offer to
  subscribe and then show the season.
- Optionally, paste the https address into Google Calendar ("Other calendars", "From URL").
- Remove the test subscription afterwards; the preview is not for parents.

**3. Promote and deploy prod** (about 5 minutes), after the promotion pull request `dev` → `main`
has merged. Where: a worktree on `main`, not a task worktree and not a switch in the main checkout.

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence
git fetch origin
git worktree add ../debate-intelligence-worktrees/prod-deploy main   # once; later: cd there and git pull --ff-only
cd ../debate-intelligence-worktrees/prod-deploy
git branch --show-current                 # must print: main
git pull --ff-only
git status --porcelain                    # must print nothing
pnpm --dir site install                   # once per worktree
terraform -chdir=infrastructure/envs/prod init -reconfigure   # once per worktree
aws sso login --sso-session debate
scripts/site_deploy.sh prod
uv run scripts/site_smoke.py --env prod --url https://wfbdebate.com --expect-sha "$(git rev-parse HEAD)"
```

Success looks like: `clean, on main, and equal to origin/main.`, then `All N checks passed.`,
including `calendar file`. Then open `https://wfbdebate.com/schedule/` once more.

## Follow-up work

- **Runbook text describes the removed panel** (`docs/runbooks/team-website.md`, outside this
  task's packages).
  - Promotion checklist precondition 1 (line 850) still requires "The October 1 room is filled in".
    That fact no longer exists, so the row can go.
  - Step 2 (line 890) says the smoke check confirms the October 1 panel. It now confirms the
    season-schedule panel and the calendar file.
  - Step 3 (line 895) asks the reader to open "the October 1 panel". It should name the schedule
    page.
  - Lines 1006 to 1028 are the record of the first launch and should stay as written.
  - Belongs to the PM, or to whichever task next edits the runbook.
- **`site/README.md`** still cites the October 1 panel as its example at lines 94 and 264, and
  does not mention `tournaments.yaml` or `schedule.yaml` among the content files. `site/README.md`
  is not in this task's packages. It suits `v1-e37-t03`, which adds the next content file.
- **The emergency lever** in the runbook deletes one page's `index.html`. For anything in the
  schedule, the same text is also in `schedule/index.txt` and `schedule.ics`. The coach guide now
  says to remove the schedule files, but the runbook's lever should name them too.
- **The source guard never reads page titles** (`ContentPage.guardedHtml` covers the lead,
  at-a-glance and body). Only the export pass sees a title. That is acceptable while every prod
  deploy runs the export checks first, but a title naming a student would get through a prod build.
  This is a candidate for `v1-e37-t03`'s published-names allowlist work.
- **Spec**: consider adding a smoke-check node to this spec, retroactively, to record Deviation 2.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

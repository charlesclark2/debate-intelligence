# Session report: v1-e37-t06-season-results

| | |
|---|---|
| Task | `v1-e37-t06-season-results` — Season results: how the team's students placed at each tournament |
| Spec | [`plan_specs/v1/e37-calendar-and-announcements/t06-season-results.yaml`](../../plan_specs/v1/e37-calendar-and-announcements/t06-season-results.yaml) |
| Epic / release | `v1-e37-calendar-and-announcements` / `v1.6` |
| Branch | `task/v1-e37-t06-season-results` |
| Session status | PARTIAL: built, reviewed and conditions closed; only ac5's publication through dev and prod remains, after the merge and the next promotion |

## Summary

The public site has a **Season results** page, `/results/`, built from a new
`site/content/results.yaml`. It is in the primary navigation straight after the schedule, lists
tournaments newest first with every placing under each one, and puts the three newest placings on
the home page with a link to the page. `src/lib/results.ts` holds the file to the publishing
policy's Results and awards section in every environment. It refuses a name with no consent
entry, half a partnership, a loss, a record, a capitalised name in a free-text field (an
opponent, as far as the build can tell), and any contact detail. Each refusal names the entry, the
field and the rule, and never the student. The build publishes a result in team-level form
whenever a named student's entry is lapsed or first-name-only (ac2 as amended by the PM). The
coach's first result (Fort Atkinson, 2026-10-17, Varsity Lincoln-Douglas, first place and top
speaker) names the student, under the consent reference the coach assigned in this session against
the form the activities office confirmed on 2026-10-01. A prod build now completes with no
finding. The PM review's four conditions are closed. The Goal stays **InProgress**: ac5's
publication through dev and prod follows the merge and the next promotion, and the PM records it.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `results` (Season results page) | Done, except ac5's publication | Schema and fixtures, the policy checks shown failing first, the page and the home band, the guide, then the coach's result. Its criterion `pnpm --dir site test` passes |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: with fixture content, the page lists results newest first, grouped by tournament, with the tournament, date, event and division and placing; the home page shows the three newest and links to the page; the page is in the primary navigation with no WCAG 2.1 AA violation | PASS | `pnpm --dir site exec vitest run tests/results.test.tsx` → 67 passed. The expected page is written out by hand from `SEASON_FIXTURE` (five placings at four tournaments, two on the schedule and two off it). Covered by "lists every tournament, newest first...", "shows the three newest...", "links to the results page", "is in the primary navigation, straight after the schedule" and axe on the page and on the home band. `tests/pages-a11y.test.tsx` now renders the results route module in the sweep, and `tests/export/pages-a11y.export-test.ts` sweeps the exported page |
| ac2 (as amended by the PM, ruling 1): the build refuses, naming the entry and the rule: a named student with no consent entry; a partner-event result naming one partner; a loss or a record; an opponent student's name; an email address or phone number. A named student whose entry is not current, or first-name-only, is published in team-level form by the build. A team-level result always publishes. Tests shown failing first | PASS | Same run. "what the build refuses" covers every case, and each assertion matches the entry, the field and the rule, for example `result 1 (Fort Atkinson, 2026-10-17), field students: names one partner of a partnership ... (docs/policies/website-publishing.md, Results and awards 1 and 2)`. A name with **no consent entry** is refused. A name whose entry is **from a previous season** (or first-name-only) is published in team-level form by the build (four tests: last season's entry, first-name-only, a partnership with one such partner, an entry that lapses with no edit to the result). **Red run**, against a refuse-nothing skeleton of `src/lib/results.ts`: `24 failed, 43 passed (67)`. The 24 are all 18 refusal tests, the 4 team-level-choice tests, the unknown schedule id, and the shipped-results test (no result in the content yet). The 43 that passed check rendering and shape, which the skeleton kept, plus "always publishes a team-level result", which a refuse-nothing skeleton cannot fail by construction |
| ac3: a result whose tournament has come off the schedule still shows its name and date; a result naming a schedule id that does not exist fails the build | PASS | Same run: "shows the name and date of a tournament that has come off the schedule" (Neenah, not in `tournaments.yaml`) and "fails the build on a schedule id that does not exist" → `result 1 (fort-atkinson-2026), field scheduleId: "fort-atkinson-2026" is not a tournament in content/tournaments.yaml. A tournament that has come off the schedule is written with tournament and date instead.` That test failed on the skeleton. The shipped result uses the name-and-date form |
| ac4: the coach guide explains how to add, correct and take down a result, when to use the team-level form, and the 24-hour rule | PASS | `docs/guides/coach-website-editing.md`, "Results: the season's results file", with sections Add a result, The team-level form, Correct a result, Take a result down (24 hours, hotfix path, which files the emergency lever must cover), What the build refuses, and Results in an email (an email names no student and links to `/results/`). `uv run --frozen python scripts/check_command_blocks.py --base origin/dev` → `OK: no # comments in 359 shell code blocks`. `scripts/docs_index.py --check-descriptions` → `All 44 indexed documents under docs/ have a description` |
| ac5: `pnpm --dir site lint`, `typecheck`, `test` and `build` pass offline | PASS | `site/scripts/pre-commit-checks.sh` in full after the conditions (23 s, exit 0): lint clean, typecheck clean, `Test Files 25 passed (25) / Tests 905 passed (905)`, dev build `recorded 80 exported files` with no publishing-policy finding, export checks `Test Files 12 passed (12) / Tests 102 passed (102)`. The suite stubs `fetch` to throw, so it ran offline. The prod build: `SITE_ENV=prod SITE_URL=https://wfbdebate.com pnpm --dir site build` → exit 0, no publishing-policy finding, `/results` generated; `site/out/results/index.html` carries 2 `results-group__result` lines and no `placeholder` |
| ac5: the coach's first result is published through dev and then prod with his consent reference in the manifest, and the report records it without the student's name | **NOT RUN** | The result is committed in individual form, and the manifest entry has the student's name, graduation year, season `2026-27`, `dateChecked: 2026-10-01` and the reference the coach assigned in this session. Dev: after the merge, from `dev-preview` (Operator follow-ups 1). Prod: after the next promotion (follow-up 4); the PM records it from that `curl` count |
| Node `results`: `pnpm --dir site test` | PASS | 905 passed, as above |

**Other red runs** (each test shown failing for its own reason, then green):

| Test | Run against | Result |
|---|---|---|
| "reads an unquoted dateChecked as the date that was typed" | the consent loader at the branch start | failed: `invalid manifest (students.0.dateChecked: Invalid input: expected string, received Date)` |
| "refuses a full-name entry with no graduation year to print" | the loader with the date fix but without the new rule | failed: `expected [Function] to throw an error` |
| "names a lapsed student entry by its consent reference, never by the name" | the guard with the old warning text | failed: `expected 'consent for "Jordan Rivera" was last …' to match /consent MC-2025-003 .../` |
| "a consent reference still to come": the position-and-note report, and failing prod while letting dev come up | `consentPlaceholders` reporting nothing | 2 failed, 1 passed. The passing one ("is quiet once the reference is filled in") cannot fail on a report-nothing skeleton |
| "keeps the label and the note in one run of text, so the space between them is rendered" (condition 3) | `EmailUpdates` with the note in its own `<span>` | failed: the link had 2 child nodes. Then green; a headless Chrome screenshot of the prod build shows "updates (opens Buttondown's site)" |

**Repository checks before the report:**

| Command | Result |
|---|---|
| `uv run scripts/affected_tests.py` | 114 files. Nearly all come through one false edge: `tests/evals/parser/docx_render.py` names `layout.css` as a word, and through it everything under `packages/debate_api/tests/conftest.py` is selected. No Python changed on this branch |
| `.venv/bin/python -m pytest -n auto -m "not slow and not live" <those 114 files>`, under `perl -e 'alarm 115'` | Stopped by the limit at 98%, every test so far passing and no failure printed (load average 8). Per agreement 10 the full set is left to the pull request's `ci`. No orphaned pytest process afterwards |
| always-run list: `pytest -n auto tests/architecture tests/specs packages/debate_cli/tests/test_app.py` | `279 passed in 6.41s` |
| `uv run --frozen ruff check .` / `ruff format --check .` | `All checks passed!` / `1158 files already formatted` |
| `uv run --frozen lint-imports` | `Contracts: 16 kept, 0 broken.` |
| `uv run --frozen python scripts/validate_specs.py` | `OK: 430 files, 40 epics, 368 tasks, 22 releases` |
| pyright | Not run: no Python package changed |

**Where the name is.** `git grep -i` for the student's surname and given name outside the two
content files finds nothing: the only hit is an unrelated substring in a public-suffix data file.
`git log --format=%B origin/dev..HEAD` contains neither. Neither does the output of
`pre-commit-checks.sh`, because every build finding names a consent entry by position.

## Files changed

- **`site/content/`**: `results.yaml` (new: the field guide in comments, the page labels, the
  coach's two placings); `pages/results.md` (new: title, description, navigation label and order,
  lead); `site.yaml` (Results after Schedule in `primaryNavigation`); `home.yaml` (the
  `recentResults` band's words); `media-consent.yaml` (the first student entry, and the
  division-and-event phrases a result line prints, added as whole phrases such as "Varsity
  Lincoln").
- **`site/src/lib/results.ts`** (new): schema, loader, the policy checks, newest-first grouping,
  the team-level choice, and the guard's view of the results.
- **`site/src/lib/media-consent.ts`**: bare dates read as typed; a full-name entry must carry its
  graduation year; `consentPlaceholders` and `consentGuardedContent` report an unfilled reference.
- **`site/src/lib/content.ts`**: `RESULTS_SLUG` (a composed page); the home band's schema; the
  bare-date quoting moved here from `tournaments.ts` so all three YAML loaders share it.
- **`site/src/lib/publishing-policy.ts`**: `contactDetails()`, used by the results checks; a lapsed
  student's warning names the consent reference instead of the student.
- **`site/src/lib/tournaments.ts`**: `readYaml` exported; the quoting imported from `content.ts`.
- **`site/src/app/results/page.tsx`** and **`site/src/components/ResultLine.tsx`** (new);
  **`site/src/app/page.tsx`** (the newest-results band); **`site/src/app/layout.tsx`** (results
  and consent gaps in the build guard).
- **`site/src/styles/`**: the results styles; the navigation's link padding between 48rem and
  64rem, so eight links fit one row at 768px.
- **`site/tests/`**: `results.test.tsx`, `results-fixture.ts` and `export/results.export-test.ts`
  (new). `content-policy.test.ts`: consent entries checked by shape and season, not "empty"; every
  printed name has a current consent entry; consent dates; consent gaps; the warning text.
  `navigation.test.tsx`: order relations instead of a pinned list. `routes.test.ts` and
  `export/routes.export-test.ts`: results is a core page. `pages-a11y.test.tsx`: the results route
  in the sweep.
- **`docs/guides/coach-website-editing.md`**: the results section, and the table and trouble rows.
- After the PM review: **`docs/runbooks/team-website.md`** (the emergency lever's results
  paragraph, condition 2); **`site/src/components/EmailUpdates.tsx`** and its test (condition 3);
  **`plan_specs/v1/e37-calendar-and-announcements/t06-season-results.yaml`** (ac2 amended with a
  PM-ruling comment, condition 4); `site/content/media-consent.yaml` and
  `site/tests/content-policy.test.ts` (the reference, and an empty `STILL_WAITING_ON_CHARLIE`,
  condition 1).

## Deviations from the spec

All accepted in the PM review of 2026-10-23.

1. **ac2 and the PM's ruling disagreed on one case; ac2 is now amended to match the code** (PM
   ruling 1). A name with **no consent entry at all** is refused. A name whose entry exists but is
   not current (lapsed at the season's start, or first-name-only) is **published in team-level
   form** by the build, so a lapsed form or a reduced-name request comes off every result with an
   edit to the manifest alone.
2. **The consent reference.** The coach first had none, and the session wrote a `[[TBD]]` marker
   that failed every prod build. The PM ruled that no `[[TBD]]` reaches dev, and that the coach,
   who holds the mapping from an opaque reference to a student, assigns the reference himself
   against the form the office confirmed on 2026-10-01 (ruling 2). He did, in this session. The
   placeholder check stays, tested with an invented student, so a future unfilled reference fails
   prod like any other gap.
3. **Two files outside the stated work, inside the stated packages.** The consent loader read
   `dateChecked: 2026-09-18`, written exactly as the manifest's own example comment shows, as a
   Date and refused it, so the first real entry would have failed the build. It now reads bare
   dates the way the schedule loader does. The stale-consent warning printed the student's name in
   every build log (Students 10); it now prints the reference. Both have red-then-green tests.
4. **No smoke-check change.** The spec's packages leave out `scripts/`, and `site_smoke.py`
   already fetches every page in the sitemap, which now includes `/results/`. The PM files the
   home-band smoke check as a small E37 task.
5. **`docs/runbooks/team-website.md` changed, outside `constraints.packages`**, as the PM accepted
   (ruling 3, condition 2). The paragraph follows the schedule's, with one addition under working
   agreement 11: a `--dryrun` block before the pattern deletion of the root `__next.*.txt` files,
   because a wrong pattern there deletes from the bucket root. The commands were not run: they act
   on the prod bucket.

## Decisions and assumptions

- **Two awards are two rows** under one tournament (the PM left this to the session). The spec says
  "one entry per placing", and a row per award keeps each line a single placing.
- **Placings are a closed list**: first to tenth place, top speaker and second to tenth speaker,
  champion, and finalist down to triple-octofinalist. A free-text field would take "went 5-1" as
  readily as "quarterfinalist". Anything else is refused, and a loss or a record is named as such.
- **Grouped by tournament, never by student.** A student's placings gathered into one list would
  be the record rule 3 rules out.
- **A capitalised name in `tournament` or `placing` is treated as an opponent student** (rule 5),
  because the build cannot tell an opponent from anyone else. A school or a town goes into
  `permittedNamePhrases`, as for the schedule.
- **Events:** Lincoln-Douglas is individual; Policy and Public Forum are partner events
  (`INDIVIDUAL_EVENTS` and `PARTNER_EVENTS`). An event in `events.yaml` that is in neither list
  fails the build rather than being guessed at.
- **The home band is left out until the season has a result**, so the front page never says
  "nothing yet". It sits after the email-updates band and before the entry points, so the existing
  rules (email band straight after the schedule panel, academic case last) still hold.
- **Copy rewritten to satisfy the guard**: "Where Whitefish Bay debaters placed" read as an
  unreviewed name, so the description and home intro say "The placings Whitefish Bay debaters won".
  No phrase was added to the allowlist for it.
- **Navigation at 768px**: measured with headless Chrome against a local build. With eight items
  "Parent FAQ" broke over two lines. Narrowing the links' side padding between 48rem and 64rem put
  it back on one row (screenshots at 768 and 1000px). Headless Chrome cannot lay out narrower than
  about 500px, and the schedule page clips the same way there, so the 390px check is the operator's
  visual QA run (follow-up 2).
- **Fixtures replace the manifest's student list** rather than adding to it, so no test reads, or
  could print, the real entry.

## Operator follow-ups

**1. Preview the result on dev after this branch merges.** Two blocks (working agreement 11).

**Operator command**: the dry run (expected runtime ~1 min)
Where: the `dev-preview` worktree
```bash
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/dev-preview
git fetch origin
git switch --detach origin/dev
pnpm --dir site install --frozen-lockfile
aws sso login --sso-session debate
env | grep -E '^(DEBATE_|SITE_)' && echo "Stop: unset the variables printed above, then run this block again" || scripts/site_deploy.sh dev --dry-run
```
Read before going on: `git log -1 --oneline` in this worktree names the merge of
`v1-e37-t06-season-results`, and the build prints no "Publishing policy problems" block at all.
Any finding there, or a printed `DEBATE_`/`SITE_` variable, stops here.

**Operator command**: the deploy (expected runtime ~4 min, most of it the invalidation)
Where: the `dev-preview` worktree
```bash
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/dev-preview
env | grep -E '^(DEBATE_|SITE_)' && echo "Stop: unset the variables printed above, then run this block again" || scripts/site_deploy.sh dev
uv run scripts/site_smoke.py --env dev --url https://dev.wfbdebate.com --expect-sha "$(git rev-parse HEAD)"
```
Success looks like: `Deployed <sha> to dev: https://dev.wfbdebate.com` and `All N checks passed.`,
with N one page more than the last dev smoke check. Then open `https://dev.wfbdebate.com/results/`
and the home page on a phone. Results is in the menu after Schedule. The Fort Atkinson card says
"Saturday, October 17, 2026", with two lines, "First place, Varsity Lincoln-Douglas:" and "Top
speaker, Varsity Lincoln-Douglas:", each followed by the student's name and "(2027)". The home
page's "The newest results" band shows the same two lines and links to the page. The coach reads
the exact lines (Pre-publication checklist item 16).

**2. The browser QA run on that build** (expected runtime ~3 min; needs `site/scripts/visual-qa-tools`
installed once, as the runbook describes). It covers the 390px phone width this session could not
measure.

**Operator command**
Where: the `dev-preview` worktree, straight after follow-up 1
```bash
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/dev-preview
pnpm --dir site qa -- --min-accessibility 95 --min-best-practices 95
```
Success looks like: exit 0, `/results/` in the score table at 95 or above, axe clean at 390, 768
and 1280px, nothing scrolling sideways. Paste the table back.

**3. The consent reference**: closed in this session by condition 1 (the coach assigned it).

**4. Prod, after the next promotion.** The runbook's
[Before a prod deploy](../runbooks/team-website.md#before-a-prod-deploy-the-build-has-to-be-clean)
build from `dev-preview` must complete first; then its [Deploy prod](../runbooks/team-website.md#deploy-prod)
block from `prod-deploy`, unchanged. Then this read-only check:

**Operator command** (expected runtime a few seconds)
Where: any shell
```bash
curl -sS https://wfbdebate.com/results/ | grep -c 'class="results-group__result"'
```
Success looks like: `2`. That closes ac5; the PM then sets the Goal to Succeeded.

## Follow-up work

- **Smoke check: the home results band** (`scripts/site_smoke.py`): filed by the PM as a small E37
  task.
- **Graduated students at the 2027-28 rollover** (policy, Charlie): recorded by the PM (ruling 4),
  who files a task for before August 2027. From 1 August 2027 every 2026-27 result naming a student
  turns team-level until that student's entry is renewed, which for a graduate is not what the
  policy says.
- **The runbook's emergency lever** and **the email-updates button's missing space**: closed in this
  session (conditions 2 and 3).
- **The consent reference in the PM review.** The review's example reference happens to be the one
  the coach assigned, so it also appears in the PM review section, which a session does not edit.
  It is opaque without the coach's own records; the PM may want to reword the example.

**Questions for the PM:** all answered in the PM review of 2026-10-23 (rulings 1 to 4).

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED, with conditions closed in-session
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-23

**Notes:**

Careful work on content that names a child.
* The name is checked to be in the two content files only.
* The placings are a closed list, so a record cannot be typed.
* Results are grouped by tournament, never by student.
* Refusals name an entry by position, and the stale-consent warning no longer prints a name.
* The consent loader's date bug would have failed the first real entry.

**Rulings**

1. **(a).** ac2 becomes: no consent entry is refused; an entry that is lapsed or first-name-only is
   published in team-level form by the build. Amend ac2's wording in the spec with a PM-ruling
   comment.
2. **No `[[TBD]]` reaches `dev`.** It would fail every prod build, and with it the pilot's
   promotion. The policy makes the reference opaque, and makes the mapping from a reference to a
   student Charlie's, kept with the activities office's records. So the coach can assign the
   reference himself (for example `MC-2026-001`) against the form the office confirmed on file on
   2026-10-01, and record that mapping in his own records. That is not a policy change. Condition 1
   below.
3. **The runbook's emergency lever** gets its results paragraph here (condition 2), accepted
   outside `constraints.packages` as a deviation.
4. **Graduated students at the 2027-28 rollover:** recorded. The PM files a task for before
   August 2027, after Charlie rules on the wording.

**Deviations 1 to 4 and the Decisions are accepted**, including two rows for two awards and the
navigation padding.

**Conditions, to close in this session before the PR:**

1. **The coach gives you the consent reference in this session.** Write it into the manifest entry,
   set `STILL_WAITING_ON_CHARLIE` to an empty list, and show that a prod build
   (`SITE_ENV=prod SITE_URL=https://wfbdebate.com pnpm --dir site build`) completes with no
   finding. **If he will not have one before the PR,** take the name off instead: delete the
   consent entry and `students` from both placings, so they publish in team-level form, and record
   in the guide how to put it back. Either way, nothing on `dev` blocks a prod build.
2. **Add the results paragraph to the runbook's emergency lever.** List the files it must cover,
   meaning `results/` and, while a result is among the newest three, the home page's root
   `index.html`, `index.txt` and `__next.*.txt`, in the same form as the schedule's paragraph.
3. **Fix the email-updates button's missing space** before "(opens Buttondown's site)". It is one
   character in `site/`, accepted here.
4. **Amend ac2 (ruling 1), then update the stale parts of this report.** No re-review is needed.

**The PR:** opened with `--partial`. ac5's prod half follows the next `dev` to `main` promotion,
and the PM records it from follow-up 4's `curl` count and sets the Goal `Succeeded`. Follow-up 3,
the reference, is closed by condition 1.

**Follow-up work:** the smoke check for the home results band is filed by the PM as a small E37
task. The rollover is ruling 4.

If anything comes out differently, stop and ask for another review.

## Resumed 2026-10-23: the coach's copy changes from the dev preview

| | |
|---|---|
| Session status | PARTIAL: the copy changes are done and checked; ac5's publication through dev and prod is still open |
| Resumed with | `scripts/task resume v1-e37-t06-season-results --launch none`, after `finish --partial` |

### Summary

The first merge was deployed to the dev preview (`bcafa7e`). The operator's dry run was clean, and
`site_smoke.py --env dev` passed 38 of 38 checks, `/results/` at 200 among them. Reading it on a
phone, the coach asked for three changes, all made in this session:

1. **The page's opening paragraph** no longer explains the page. It now reads as he chose from
   three drafts: "Our debaters compete all season long, and we're proud of every result they bring
   home. Here's where we share their success as the year goes on." The links to the events and
   schedule pages went with the old paragraph.
2. **The correction line** ("To correct a result, or to have one taken down, email Coach
   Clark...") is removed, at his choice.
3. **"Newest tournament first. Each result says the event, the division and the placing."** is
   gone from under "Results from the 2026-27 season", and its label (`seasonIntro`) is gone from
   `site/content/results.yaml`, the schema in `site/src/lib/results.ts` and the page.

The Goal stays **InProgress**: nothing in this session closes ac5's publication.

### Acceptance criteria touched

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 (the page with fixture content, the home band, the navigation, no WCAG 2.1 AA violation) | PASS | `pnpm --dir site exec vitest run tests/results.test.tsx` → `67 passed`. New test: "opens the season band straight into the results, with no intro paragraph under its title". **Red run** against the previous page, schema and content (`git show HEAD~1:` of the three files): `1 failed`, `expected <p class="section__intro"></p> to be null`; the files were restored with `git checkout`. The em-dash and acronym tests now edit the `empty` label, since the one they edited is gone |
| ac5: `lint`, `typecheck`, `test` and `build` pass offline | PASS | `site/scripts/pre-commit-checks.sh` in full (23 s, exit 0): `Test Files 25 passed (25) / Tests 905 passed (905)`, the dev build with no publishing-policy finding, export checks `Test Files 12 passed (12) / Tests 102 passed (102)`. `SITE_ENV=prod SITE_URL=https://wfbdebate.com pnpm --dir site build` → exit 0, no publishing-policy finding |
| ac5: the coach's first result is published through dev and then prod with his consent reference in the manifest | **NOT RUN** | On the dev preview since `bcafa7e`, in the wording before this session. The reworded page reaches dev after this branch merges (follow-up 1 below), and prod after the next promotion (follow-up 4 of the first session, the `curl` count of 2) |

**Repository checks:**

| Command | Result |
|---|---|
| `uv run scripts/affected_tests.py` | 51 files, none of them changed by this session (only `site/` changed) |
| `.venv/bin/python -m pytest -n auto -m "not slow and not live" <those 51 files>`, under `perl -e 'alarm 115'` | Stopped by the limit with load average 9; the `OSError: cannot send` at the end is xdist's teardown after the alarm, not a failure. Left to the pull request's `ci` (agreement 10). No orphaned pytest process afterwards |
| always-run list: `pytest -n auto tests/architecture tests/specs packages/debate_cli/tests/test_app.py` | `279 passed in 5.84s` |
| `uv run --frozen ruff check .` | `All checks passed!` |
| `uv run --frozen lint-imports` | `Contracts: 16 kept, 0 broken.` |
| `uv run --frozen python scripts/validate_specs.py` | `OK: 431 files, 40 epics, 369 tasks, 22 releases` |

### Files changed

- `site/content/pages/results.md`: the new opening paragraph, and nothing else in the body.
- `site/content/results.yaml`, `site/src/lib/results.ts`, `site/src/app/results/page.tsx`: the
  `seasonIntro` label removed.
- `site/tests/results.test.tsx`: the new test, the copy list, and the two tests that edited the
  removed label.

### Deviations from the spec

None.

### Decisions and assumptions

- **Removing the correction line leaves the removal path intact.** The policy's route for a
  correction or a takedown is an email to Charlie, and the Contact page in every page's footer
  carries his address. Pre-publication checklist item 15 (everything about a person can be taken
  down by a content edit) is unaffected. The coach guide still tells coaches how to take a result
  down.
- **The page's description** (its search-result and link-preview text) is unchanged. It is not on
  the page, and it describes the page to someone who has not opened it.

### Operator follow-ups

1. **After this branch merges, redeploy the dev preview and read `/results/` again on a phone**:
   the first session's follow-up 1, both blocks, unchanged. The opening paragraph is the new one,
   no correction line follows it, and "Results from the 2026-27 season" goes straight to the Fort
   Atkinson card.
2. **The browser QA run** on that build: the first session's follow-up 2, unchanged. It was held
   until now so that it measures the final copy.
3. **Prod**: the first session's follow-up 4, after the next promotion.

### Follow-up work

None new.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-23

**Notes:**

1. **The coach's three copy changes are accepted as made.** They are the new opening paragraph, the
   correction line removed, and `seasonIntro` removed from the content, the schema and the page.
   The red run and the single new test are proportionate.
2. **Removing the correction line is within the policy.** The policy's route for a removal request
   is the Contact page (Removal on request), which every page's footer links to, and a takedown is
   still a content edit. The coach guide keeps the takedown steps.
3. **The consent reference in the first review's example.** It is opaque without the coach's own
   records, which is the policy's design, so nothing about the student is exposed by it. A review
   is never edited, and no change is needed.

**The PR:** open it with `scripts/task pr --partial`, as before. ac5's prod half still follows the
next promotion, and the PM records it from the `curl` count of 2. After this merge, the operator
runs the first session's follow-up 1 (dev preview) and follow-up 2 (the browser QA run, now on the
final copy), and pastes the QA table to the PM.
